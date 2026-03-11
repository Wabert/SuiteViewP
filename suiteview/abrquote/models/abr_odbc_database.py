"""
ABR Quote — ODBC data access layer for the UL_Rates SQL Server database.

Provides the same public interface as ABRDatabase (abr_database.py)
but reads all rate data from the shared UL_Rates ODBC DSN.

Premium / product tables (TERM_ prefix — pointer-based architecture):
    TERM_POINT_PV           — plancode/version → modefact, bandspec indexes + fee
    TERM_POINT_PVSRB        — plancode/version/sex/rateclass/band → premium rate index
    TERM_POINT_BENEFIT      — plancode/version/benefit → benefit rate index
    TERM_RATE_MODEFACT      — modal factors (PAC/DIR × S/Q/M, plus fee variants)
    TERM_RATE_BANDSPECS     — face-amount band breakpoints
    TERM_RATE_PREM          — pre-compiled premium rates (by issue age + duration)
    TERM_RATE_BEN           — pre-compiled benefit/rider rates (by issue age + duration)

Non-premium tables (SV_ prefix — still used as-is):
    SV_ABR_INTEREST_RATES   — monthly ABR interest rates
    SV_ABR_PER_DIEM         — annual per diem limits
    SV_ABR_STATE_VARIATIONS — state-specific forms and admin fees
    SV_ABR_VBT_2008         — 2008 VBT Select mortality rates

This module provides full read access.  Schema is managed externally
in SQL Server.
"""

import logging
import time
from pathlib import Path
from typing import Optional, List, Tuple, Dict

import pyodbc

logger = logging.getLogger(__name__)

ODBC_DSN = "UL_Rates"

# IssueVersion — always 1 per business rule
ISSUE_VERSION = 1

# Scale: 1 = current rates, 0 = guaranteed rates.
# We prefer current (1) and fall back to guaranteed (0).
SCALE_CURRENT = 1
SCALE_GUARANTEED = 0

# Billing mode → (premium_column, fee_column) in TERM_RATE_MODEFACT.
# Annual (mode 1) is always 1.0 — no lookup needed.
_MODEFACT_COLUMN_MAP: Dict[int, Tuple[str, str]] = {
    2: ("DIRS", "DIRS_FEE"),    # Semi-Annual, Direct
    3: ("DIRQ", "DIRQ_FEE"),    # Quarterly, Direct
    4: ("DIRM", "DIRM_FEE"),    # Monthly, Direct
    5: ("PACM", "PACM_FEE"),    # PAC Monthly
    6: ("PACM", "PACM_FEE"),    # Bi-Weekly → same as PAC Monthly
}


class ABROdbcDatabase:
    """Read-only ABR data access from the UL_Rates SQL Server database.

    Provides the same public method signatures as ABRDatabase so the
    rest of the codebase can use either backend interchangeably.
    """

    def __init__(self, dsn: str = ODBC_DSN):
        self._dsn = dsn
        self._conn: Optional[pyodbc.Connection] = None
        self.backend = "odbc"  # identifier for logging/diagnostics
        self._vbt_cache: Optional[dict] = None  # lazy-loaded VBT data
        # Per-plancode pointer caches (cleared on close)
        self._pv_cache: Dict[str, dict] = {}
        self._modefact_cache: Dict[str, dict] = {}
        self._pvsrb_cache: Dict[tuple, Optional[dict]] = {}
        self._band_cache: Dict[tuple, str] = {}
        # Bulk-loaded rate caches (per index, loaded on first access)
        # _prem_rate_cache[index] = {(issue_age, duration): rate} for best scale
        self._prem_rate_cache: Dict[str, Dict[tuple, float]] = {}
        # _ben_rate_cache[index] = {(issue_age, duration): rate} for best scale
        self._ben_rate_cache: Dict[str, Dict[tuple, float]] = {}
        # Query timing stats: {method_name: {calls, time, cache_hits}}
        self._query_stats: Dict[str, dict] = {}

    # ── Connection management ────────────────────────────────────────────

    def connect(self) -> pyodbc.Connection:
        """Open (or return cached) ODBC connection."""
        if self._conn is None:
            self._conn = pyodbc.connect(f"DSN={self._dsn}")
            self._conn.autocommit = False
        return self._conn

    def close(self):
        """Close ODBC connection."""
        if self._conn:
            self._conn.close()
            self._conn = None
        self._pv_cache.clear()
        self._modefact_cache.clear()
        self._pvsrb_cache.clear()
        self._band_cache.clear()
        self._prem_rate_cache.clear()
        self._ben_rate_cache.clear()

    # ── Query timing helpers ──────────────────────────────────────────────

    def _record_query(self, method: str, elapsed: float, cache_hit: bool = False):
        """Record a query timing stat."""
        if method not in self._query_stats:
            self._query_stats[method] = {"calls": 0, "time": 0.0, "cache_hits": 0}
        s = self._query_stats[method]
        s["calls"] += 1
        s["time"] += elapsed
        if cache_hit:
            s["cache_hits"] += 1

    def reset_query_stats(self):
        """Clear query timing stats (call before a new policy load)."""
        self._query_stats.clear()

    def dump_query_stats(self):
        """Write a summary table of all query timings to ~/.suiteview/timing.log."""
        log_path = Path.home() / ".suiteview" / "timing.log"
        log_path.parent.mkdir(parents=True, exist_ok=True)
        with open(log_path, "a", encoding="utf-8") as f:
            import datetime
            f.write(f"\n{'='*80}\n")
            f.write(f"[TIMING] {datetime.datetime.now():%Y-%m-%d %H:%M:%S}\n")
            if not self._query_stats:
                f.write("No query stats recorded.\n")
                return
            total_time = sum(s["time"] for s in self._query_stats.values())
            total_calls = sum(s["calls"] for s in self._query_stats.values())
            f.write(f"{'Method':<30} {'Calls':>6} {'Cache':>6} {'DB':>6} {'Total(s)':>10} {'Avg(ms)':>10}\n")
            f.write(f"{'-'*80}\n")
            for method, s in sorted(self._query_stats.items(), key=lambda x: -x[1]["time"]):
                db_calls = s["calls"] - s["cache_hits"]
                avg_ms = (s["time"] / s["calls"] * 1000) if s["calls"] else 0
                f.write(
                    f"{method:<30} {s['calls']:>6} {s['cache_hits']:>6} {db_calls:>6} "
                    f"{s['time']:>10.4f} {avg_ms:>10.2f}\n"
                )
            f.write(f"{'-'*80}\n")
            f.write(f"{'TOTAL':<30} {total_calls:>6} {'':>6} {'':>6} {total_time:>10.4f}\n")
            f.write(f"{'='*80}\n")

    # ── Pointer resolution (internal) ────────────────────────────────────

    def _resolve_pv(self, plancode: str) -> Optional[dict]:
        """Look up TERM_POINT_PV for plancode + IssueVersion=1.

        Returns dict with keys:
            modefact_index, bandspec_index, fee
        Cached per plancode.
        """
        t0 = time.perf_counter()
        key = plancode.upper()
        if key in self._pv_cache:
            self._record_query("_resolve_pv", time.perf_counter() - t0, cache_hit=True)
            return self._pv_cache[key]

        cursor = self.connect().cursor()
        cursor.execute(
            "SELECT [Index(MODEFACT)], [Index(BANDSPEC)], [FEE] "
            "FROM [TERM_POINT_PV] "
            "WHERE [Plancode] = ? AND [IssueVersion] = ?",
            (key, ISSUE_VERSION),
        )
        row = cursor.fetchone()
        cursor.close()

        if row is None:
            logger.warning(f"TERM_POINT_PV not found: plancode={key}, version={ISSUE_VERSION}")
            self._record_query("_resolve_pv", time.perf_counter() - t0)
            return None

        result = {
            "modefact_index": row[0],
            "bandspec_index": row[1],
            "fee": float(row[2]) if row[2] is not None else 60.0,
        }
        self._pv_cache[key] = result
        self._record_query("_resolve_pv", time.perf_counter() - t0)
        return result

    def get_prem_cease_age(self, plancode: str) -> int:
        """Return the premium cease age for a plancode.

        With the pre-compiled rate tables, premium cessation is implicit:
        the rate lookup returns None when no rate exists for a given duration.
        This method returns a high default so the caller's attained-age check
        does not prematurely stop premium — the actual cessation is handled
        by the rate lookup returning None.
        """
        return 95

    def _resolve_pvsrb(self, plancode: str, sex: str,
                       rateclass: str, band: str) -> Optional[dict]:
        """Look up TERM_POINT_PVSRB for premium rate index.

        Returns dict with prem_index.  Cached per key.
        """
        t0 = time.perf_counter()
        cache_key = (plancode.upper(), sex.upper(), rateclass.upper(), str(band))
        if cache_key in self._pvsrb_cache:
            self._record_query("_resolve_pvsrb", time.perf_counter() - t0, cache_hit=True)
            return self._pvsrb_cache[cache_key]

        cursor = self.connect().cursor()
        cursor.execute(
            "SELECT [Index(PREM)] "
            "FROM [TERM_POINT_PVSRB] "
            "WHERE [Plancode] = ? AND [IssueVersion] = ? "
            "AND [Sex] = ? AND [Rateclass] = ? AND [Band] = ?",
            (cache_key[0], ISSUE_VERSION,
             cache_key[1], cache_key[2], cache_key[3]),
        )
        row = cursor.fetchone()
        cursor.close()

        if row is None:
            logger.warning(
                f"TERM_POINT_PVSRB not found: {plancode} {sex} {rateclass} band={band}"
            )
            self._pvsrb_cache[cache_key] = None
            self._record_query("_resolve_pvsrb", time.perf_counter() - t0)
            return None
        result = {"prem_index": row[0]}
        self._pvsrb_cache[cache_key] = result
        self._record_query("_resolve_pvsrb", time.perf_counter() - t0)
        return result

    def _resolve_benefit(self, plancode: str, benefit_type: str,
                         benefit: str, sex: str, rateclass: str,
                         band: str) -> Optional[dict]:
        """Look up TERM_POINT_BENEFIT for benefit rate index.

        Returns dict with ben_index.
        """
        cursor = self.connect().cursor()
        cursor.execute(
            "SELECT [Index(BEN)] "
            "FROM [TERM_POINT_BENEFIT] "
            "WHERE [Plancode] = ? AND [IssueVersion] = ? "
            "AND [BenefitType] = ? AND [Benefit] = ? "
            "AND [Sex] = ? AND [Rateclass] = ? AND [Band] = ?",
            (plancode.upper(), ISSUE_VERSION,
             str(benefit_type), str(benefit),
             sex.upper(), rateclass.upper(), str(band)),
        )
        row = cursor.fetchone()
        cursor.close()

        if row is None:
            logger.debug(
                f"TERM_POINT_BENEFIT not found: {plancode} {benefit_type}/{benefit} "
                f"{sex} {rateclass} band={band}"
            )
            return None
        return {"ben_index": row[0]}

    def _get_modefact_row(self, plancode: str) -> Optional[dict]:
        """Get the full modefact row for a plancode (cached)."""
        key = plancode.upper()
        if key in self._modefact_cache:
            return self._modefact_cache[key]

        pv = self._resolve_pv(key)
        if pv is None:
            self._modefact_cache[key] = None
            return None

        cursor = self.connect().cursor()
        cursor.execute(
            "SELECT [PACS], [PACQ], [PACM], [DIRS], [DIRQ], [DIRM], "
            "[PACS_FEE], [PACQ_FEE], [PACM_FEE], [DIRS_FEE], [DIRQ_FEE], [DIRM_FEE] "
            "FROM [TERM_RATE_MODEFACT] "
            "WHERE [Index(MODEFACT)] = ?",
            (pv["modefact_index"],),
        )
        row = cursor.fetchone()
        cursor.close()

        if row is None:
            logger.warning(f"TERM_RATE_MODEFACT not found: index={pv['modefact_index']}")
            self._modefact_cache[key] = None
            return None

        result = {
            "PACS": row[0], "PACQ": row[1], "PACM": row[2],
            "DIRS": row[3], "DIRQ": row[4], "DIRM": row[5],
            "PACS_FEE": row[6], "PACQ_FEE": row[7], "PACM_FEE": row[8],
            "DIRS_FEE": row[9], "DIRQ_FEE": row[10], "DIRM_FEE": row[11],
        }
        self._modefact_cache[key] = result
        return result

    # ── Pre-compiled rate lookup (bulk-cached) ────────────────────────────

    def _ensure_prem_cache(self, index: str):
        """Bulk-load all premium rates for a given index on first access.

        Loads ALL (Scale, IssueAge, Duration, Rate) rows for this index
        from TERM_RATE_PREM, preferring Scale=1 (current) over Scale=0
        (guaranteed).  Stores as {(issue_age, duration): rate}.
        """
        if index in self._prem_rate_cache:
            return
        t0 = time.perf_counter()
        cursor = self.connect().cursor()
        cursor.execute(
            "SELECT [Scale], [IssueAge], [Duration], [Rate] "
            "FROM [TERM_RATE_PREM] "
            "WHERE [Index(PREM)] = ? "
            "ORDER BY [Scale] ASC",   # guaranteed (0) first, current (1) overwrites
            (index,),
        )
        cache: Dict[tuple, float] = {}
        for row in cursor:
            # Scale=0 (guaranteed) loaded first; Scale=1 (current) overwrites
            cache[(row[1], row[2])] = float(row[3])
        cursor.close()
        self._prem_rate_cache[index] = cache
        self._record_query("_bulk_load_prem", time.perf_counter() - t0)

    def _lookup_prem_rate(self, index: str, issue_age: int,
                          duration: int) -> Optional[float]:
        """Look up a premium rate from bulk-cached TERM_RATE_PREM data.

        Tries exact (issue_age, duration) first, then falls back to
        max Duration <= requested (for flat-rate/level plans).
        """
        t0 = time.perf_counter()
        self._ensure_prem_cache(index)
        cache = self._prem_rate_cache.get(index, {})

        # Try exact duration first (common case)
        rate = cache.get((issue_age, duration))
        if rate is not None:
            self._record_query("_lookup_prem_rate", time.perf_counter() - t0, cache_hit=True)
            return rate

        # Fall back to max duration <= requested (for flat-rate level plans)
        best_rate = None
        best_dur = -1
        for (ia, dur), r in cache.items():
            if ia == issue_age and dur <= duration and dur > best_dur:
                best_dur = dur
                best_rate = r
        self._record_query("_lookup_prem_rate", time.perf_counter() - t0, cache_hit=True)
        return best_rate

    def _ensure_ben_cache(self, index: str):
        """Bulk-load all benefit rates for a given index on first access.

        Loads ALL (Scale, IssueAge, Duration, Rate) rows for this index
        from TERM_RATE_BEN, preferring Scale=1 (current) over Scale=0
        (guaranteed).  Stores as {(issue_age, duration): rate}.
        """
        if index in self._ben_rate_cache:
            return
        t0 = time.perf_counter()
        cursor = self.connect().cursor()
        cursor.execute(
            "SELECT [Scale], [IssueAge], [Duration], [Rate] "
            "FROM [TERM_RATE_BEN] "
            "WHERE [Index(BEN)] = ? "
            "ORDER BY [Scale] ASC",   # guaranteed (0) first, current (1) overwrites
            (index,),
        )
        cache: Dict[tuple, float] = {}
        for row in cursor:
            cache[(row[1], row[2])] = float(row[3])
        cursor.close()
        self._ben_rate_cache[index] = cache
        self._record_query("_bulk_load_ben", time.perf_counter() - t0)

    def _lookup_ben_rate(self, index: str, issue_age: int,
                         duration: int) -> Optional[float]:
        """Look up a benefit rate from bulk-cached TERM_RATE_BEN data.

        Same fallback logic as _lookup_prem_rate.
        """
        t0 = time.perf_counter()
        self._ensure_ben_cache(index)
        cache = self._ben_rate_cache.get(index, {})

        rate = cache.get((issue_age, duration))
        if rate is not None:
            self._record_query("_lookup_ben_rate", time.perf_counter() - t0, cache_hit=True)
            return rate

        best_rate = None
        best_dur = -1
        for (ia, dur), r in cache.items():
            if ia == issue_age and dur <= duration and dur > best_dur:
                best_dur = dur
                best_rate = r
        self._record_query("_lookup_ben_rate", time.perf_counter() - t0, cache_hit=True)
        return best_rate

    # ── Term rates (public) ──────────────────────────────────────────────

    def get_term_rate(self, plancode: str, sex: str, rate_class: str,
                      band: str, issue_age: int, policy_year: int) -> Optional[float]:
        """Look up a single term premium rate.

        Uses the TERM pointer tables to resolve the rate index, then
        queries TERM_RATE_PREM by (Index, IssueAge, Duration).

        Args:
            band: BandCode string (e.g. 'A', 'B', 'C') from get_band().
        """
        if policy_year < 1 or policy_year > 82:
            return None

        # Check if plancode is in TERM tables
        pv = self._resolve_pv(plancode)
        if pv is None:
            return None

        ptrs = self._resolve_pvsrb(plancode, sex, rate_class, band)
        if ptrs is None:
            return None

        rate = self._lookup_prem_rate(
            ptrs["prem_index"], issue_age, policy_year
        )

        if rate is None:
            logger.warning(
                f"Term rate not found: {plancode} {sex} {rate_class} "
                f"band={band} age={issue_age} yr={policy_year}"
            )
        return rate

    def get_term_rate_schedule(self, plancode: str, sex: str, rate_class: str,
                               band: str, issue_age: int) -> Optional[List[float]]:
        """Return full rate schedule (years 1-82) for a key.

        Queries TERM_RATE_PREM for each duration.

        Args:
            band: BandCode string (e.g. 'A', 'B', 'C') from get_band().
        """
        pv = self._resolve_pv(plancode)
        if pv is None:
            return None

        ptrs = self._resolve_pvsrb(plancode, sex, rate_class, band)
        if ptrs is None:
            return None

        schedule = []
        found_any = False

        for yr in range(1, 83):
            rate = self._lookup_prem_rate(
                ptrs["prem_index"], issue_age, yr
            )
            if rate is not None:
                found_any = True
            schedule.append(rate if rate is not None else 0.0)

        return schedule if found_any else None

    def term_rate_count(self) -> int:
        """Return count of rows in TERM_RATE_PREM."""
        cursor = self.connect().cursor()
        cursor.execute("SELECT COUNT(*) FROM [TERM_RATE_PREM]")
        count = cursor.fetchone()[0]
        cursor.close()
        return count

    # ── Benefit rates (public) ───────────────────────────────────────────

    def get_benefit_rate(self, plancode: str, benefit_type: str,
                         benefit: str, sex: str, rate_class: str,
                         band: str, issue_age: int,
                         policy_year: int) -> Optional[float]:
        """Look up a single benefit/rider rate from TERM tables.

        Args:
            plancode: base plancode (PLN_BSE_SRE_CD)
            benefit_type: CyberLife SPM_BNF_TYP_CD
            benefit: CyberLife SPM_BNF_SBY_CD
            sex, rate_class: rating dimensions
            band: BandCode string from get_band()
            issue_age: benefit issue age
            policy_year: policy year (1-based)
        """
        if policy_year < 1:
            return None

        ptrs = self._resolve_benefit(
            plancode, benefit_type, benefit, sex, rate_class, str(band)
        )
        if ptrs is None:
            return None

        return self._lookup_ben_rate(
            ptrs["ben_index"], issue_age, policy_year
        )

    def get_benefit_rate_schedule(self, plancode: str, benefit_type: str,
                                  benefit: str, sex: str, rate_class: str,
                                  band: str,
                                  issue_age: int) -> Optional[List[float]]:
        """Return full benefit rate schedule (years 1-82)."""
        ptrs = self._resolve_benefit(
            plancode, benefit_type, benefit, sex, rate_class, str(band)
        )
        if ptrs is None:
            return None

        schedule = []
        found_any = False
        for yr in range(1, 83):
            rate = self._lookup_ben_rate(
                ptrs["ben_index"], issue_age, yr
            )
            if rate is not None:
                found_any = True
            schedule.append(rate if rate is not None else 0.0)
        return schedule if found_any else None

    # ── Interest rates ───────────────────────────────────────────────────

    def get_latest_interest_rate(self) -> Optional[Tuple[str, float]]:
        """Return the most recent (date, rate_decimal) tuple."""
        cursor = self.connect().cursor()
        cursor.execute(
            "SELECT TOP 1 effective_date, iul_var_loan_rate "
            "FROM [SV_ABR_INTEREST_RATES] ORDER BY effective_date DESC"
        )
        row = cursor.fetchone()
        cursor.close()
        if row is None:
            return None
        return (row[0], row[1] / 100.0)

    def get_interest_rate_by_date(self, dt: str) -> Optional[float]:
        """Return ABR interest rate (as decimal) for a specific YYYY-MM date."""
        cursor = self.connect().cursor()
        cursor.execute(
            "SELECT iul_var_loan_rate FROM [SV_ABR_INTEREST_RATES] "
            "WHERE effective_date = ?", (dt,)
        )
        row = cursor.fetchone()
        cursor.close()
        return row[0] / 100.0 if row else None

    def get_effective_interest_rate(self, as_of: str) -> Optional[Tuple[str, float]]:
        """Return the ABR rate effective for a given YYYY-MM date."""
        cursor = self.connect().cursor()
        cursor.execute(
            "SELECT TOP 1 effective_date, iul_var_loan_rate "
            "FROM [SV_ABR_INTEREST_RATES] "
            "WHERE effective_date <= ? ORDER BY effective_date DESC", (as_of,)
        )
        row = cursor.fetchone()
        cursor.close()
        if row is None:
            return None
        return (row[0], row[1] / 100.0)

    def interest_rate_count(self) -> int:
        """Return count of interest rate rows."""
        cursor = self.connect().cursor()
        cursor.execute("SELECT COUNT(*) FROM [SV_ABR_INTEREST_RATES]")
        row = cursor.fetchone()
        cursor.close()
        return row[0] if row else 0

    # ── Per diem ─────────────────────────────────────────────────────────

    def get_per_diem(self, year: int) -> Optional[Tuple[float, float]]:
        """Return (daily_limit, annual_limit) for a given year."""
        cursor = self.connect().cursor()
        cursor.execute(
            "SELECT daily_limit, annual_limit FROM [SV_ABR_PER_DIEM] "
            "WHERE year = ?", (year,)
        )
        row = cursor.fetchone()
        if row:
            cursor.close()
            return (row[0], row[1])

        # Fall back to most recent year <= requested
        cursor.execute(
            "SELECT TOP 1 daily_limit, annual_limit FROM [SV_ABR_PER_DIEM] "
            "WHERE year <= ? ORDER BY year DESC", (year,)
        )
        row = cursor.fetchone()
        cursor.close()
        if row:
            return (row[0], row[1])
        return None

    # ── State Variations ─────────────────────────────────────────────────

    def get_admin_fee(self, state: str) -> float:
        """Return the administrative fee for a state."""
        cursor = self.connect().cursor()
        cursor.execute(
            "SELECT admin_fee FROM [SV_ABR_STATE_VARIATIONS] "
            "WHERE state_abbr = ?", (state.upper(),)
        )
        row = cursor.fetchone()
        cursor.close()
        if row and row[0] is not None:
            return float(row[0])
        return 250.0

    # ── Min Face ─────────────────────────────────────────────────────────

    def get_min_face(self, plancode: str) -> float:
        """Return the minimum face amount (hardcoded $50,000)."""
        return 50_000.0

    # ── Modal Factors ────────────────────────────────────────────────────

    def get_modal_factor(self, plancode: str, mode_code: int) -> float:
        """Return premium modal factor for a plancode + billing mode.

        Annual (mode 1) is always 1.0. Other modes look up the TERM_RATE_MODEFACT
        table via the plancode's TERM_POINT_PV pointer.
        """
        if mode_code == 1:
            return 1.0

        cols = _MODEFACT_COLUMN_MAP.get(mode_code)
        if cols is None:
            return 1.0

        mf_row = self._get_modefact_row(plancode)
        if mf_row is None:
            return 1.0

        val = mf_row.get(cols[0])  # premium column
        return float(val) if val is not None else 1.0

    def get_modal_fee_factor(self, plancode: str, mode_code: int) -> float:
        """Return fee modal factor for a plancode + billing mode.

        Same structure as get_modal_factor but uses the _FEE column variants.
        """
        if mode_code == 1:
            return 1.0

        cols = _MODEFACT_COLUMN_MAP.get(mode_code)
        if cols is None:
            return 1.0

        mf_row = self._get_modefact_row(plancode)
        if mf_row is None:
            return 1.0

        val = mf_row.get(cols[1])  # fee column
        return float(val) if val is not None else 1.0

    # ── Band Amounts ─────────────────────────────────────────────────────

    def get_band(self, plancode: str, face_amount: float) -> str:
        """Return BandCode (letter) for a given plancode and face amount.

        Looks up TERM_RATE_BANDSPECS via the plancode's TERM_POINT_PV pointer.
        Returns the BandCode string (e.g. 'A', 'B', 'C', 'D', 'E').  Cached.
        """
        t0 = time.perf_counter()
        cache_key = (plancode.upper(), face_amount)
        if cache_key in self._band_cache:
            self._record_query("get_band", time.perf_counter() - t0, cache_hit=True)
            return self._band_cache[cache_key]

        pv = self._resolve_pv(plancode)
        if pv is None:
            self._record_query("get_band", time.perf_counter() - t0)
            return 'A'  # plancode not in TERM tables

        cursor = self.connect().cursor()
        cursor.execute(
            "SELECT [Band], [SpecifiedAmount], [BandCode] FROM [TERM_RATE_BANDSPECS] "
            "WHERE [Index(BANDSPEC)] = ? ORDER BY [SpecifiedAmount] ASC",
            (pv["bandspec_index"],),
        )
        rows = cursor.fetchall()
        cursor.close()

        if not rows:
            self._record_query("get_band", time.perf_counter() - t0)
            return 'A'  # default band code

        band_code = rows[0][2] or 'A'  # default to first band
        for r in rows:
            if face_amount >= r[1]:
                band_code = r[2] or str(r[0])
        self._band_cache[cache_key] = band_code
        self._record_query("get_band", time.perf_counter() - t0)
        return band_code



    # ── Policy Fees ──────────────────────────────────────────────────────

    def get_policy_fee(self, plancode: str) -> float:
        """Return the annual policy fee for a plancode.

        Read directly from TERM_POINT_PV.FEE.
        """
        pv = self._resolve_pv(plancode)
        if pv is None:
            return 60.0  # default fee if plancode not in TERM tables
        return pv["fee"]



    # ── VBT 2008 mortality ───────────────────────────────────────────────

    def _ensure_vbt_cache(self):
        """Bulk-load VBT table into an in-memory dict on first access.

        Structure: {block: {(duration_year, issue_age): rate_per_1000}}
        This avoids ~1000+ individual ODBC round trips per mortality calc.
        """
        if self._vbt_cache is not None:
            return
        logger.info("Loading VBT 2008 cache from SQL Server ...")
        cursor = self.connect().cursor()
        cursor.execute(
            "SELECT block, duration_year, issue_age, rate_per_1000 "
            "FROM [SV_ABR_VBT_2008]"
        )
        cache: dict = {}
        count = 0
        for row in cursor:
            blk = row[0]
            if blk not in cache:
                cache[blk] = {}
            cache[blk][(row[1], row[2])] = row[3]
            count += 1
        cursor.close()
        self._vbt_cache = cache
        logger.info(f"VBT cache loaded: {count:,} rates")

    def get_vbt_qx(self, block: str, issue_age: int,
                   duration_year: int) -> float:
        """Look up annual mortality rate (qx) from cached 2008 VBT data.

        Args:
            block: "MN", "FN", "MS", or "FS"
            issue_age: 0-99
            duration_year: 1-121

        Returns:
            Mortality rate per 1,000 lives.
            Returns 1000.0 (certainty of death) if out of range.
        """
        if duration_year >= 121 or issue_age >= 100:
            return 1000.0
        if duration_year < 1 or issue_age < 0:
            return 0.0

        self._ensure_vbt_cache()
        blk = block.upper()
        if blk not in self._vbt_cache:
            raise ValueError(
                f"Unknown VBT block: {block!r}. Use MN, FN, MS, or FS."
            )
        rate = self._vbt_cache[blk].get((duration_year, issue_age))
        if rate is None:
            raise ValueError(
                f"VBT rate not found: block={block}, dur={duration_year}, age={issue_age}"
            )
        return rate

    # ── Rate Viewer helpers ──────────────────────────────────────────────
    # These methods provide the data the RateViewerDialog needs in
    # (headers, rows) tuple format.

    def load_interest_rates_for_viewer(self) -> tuple:
        """Return (headers, rows) for interest rates viewer."""
        cursor = self.connect().cursor()
        cursor.execute(
            "SELECT effective_date, rate, iul_var_loan_rate "
            "FROM [SV_ABR_INTEREST_RATES] ORDER BY effective_date DESC"
        )
        rows = cursor.fetchall()
        cursor.close()
        headers = ["Effective Date", "Moody Ave Yield (%)", "ABR Rate (%)"]
        return headers, [tuple(r) for r in rows]

    def load_term_rates_for_viewer(self) -> tuple:
        """Return (headers, rows) for term rates viewer.

        Shows plancode, fee, and rate table indexes.
        """
        cursor = self.connect().cursor()
        cursor.execute("""
            SELECT [Plancode], [IssueVersion],
                   [FEE],
                   [Index(MODEFACT)], [Index(BANDSPEC)]
            FROM [TERM_POINT_PV]
            ORDER BY [Plancode]
        """)
        rows = cursor.fetchall()
        cursor.close()
        headers = [
            "Plancode", "Version",
            "Fee", "ModeFact Index", "BandSpec Index",
        ]
        return headers, [tuple(r) for r in rows]

    def load_per_diem_for_viewer(self) -> tuple:
        cursor = self.connect().cursor()
        cursor.execute(
            "SELECT year, daily_limit, annual_limit "
            "FROM [SV_ABR_PER_DIEM] ORDER BY year DESC"
        )
        rows = cursor.fetchall()
        cursor.close()
        headers = ["Year", "Daily Limit ($)", "Annual Limit ($)"]
        return headers, [tuple(r) for r in rows]

    def load_state_variations_for_viewer(self) -> tuple:
        cursor = self.connect().cursor()
        cursor.execute("""
            SELECT cl_state_code, state_abbr, state_name, state_group,
                   admin_fee, election_form, disclosure_form_critical,
                   disclosure_form_chronic, disclosure_form_terminal
            FROM [SV_ABR_STATE_VARIATIONS]
            ORDER BY cl_state_code ASC
        """)
        rows = cursor.fetchall()
        cursor.close()
        headers = [
            "CL_State_Code", "StateAbbr", "State", "StateGroup",
            "Admin Fee", "Election_Form", "Disclosure_Form_Critical",
            "Disclosure_Form_Chronic", "Disclosure_Form_Terminal"
        ]
        return headers, [tuple(r) for r in rows]

    def load_min_face_for_viewer(self) -> tuple:
        """Min face is now hardcoded — return a single informational row."""
        headers = ["Plancode", "Min Face Amount ($)"]
        return headers, [("(All Plans)", 50_000.0)]

    def load_modal_factors_for_viewer(self) -> tuple:
        """Return modal factors from TERM_RATE_MODEFACT."""
        cursor = self.connect().cursor()
        cursor.execute(
            "SELECT [Index(MODEFACT)], "
            "[PACS], [PACQ], [PACM], [DIRS], [DIRQ], [DIRM], "
            "[PACS_FEE], [PACQ_FEE], [PACM_FEE], [DIRS_FEE], [DIRQ_FEE], [DIRM_FEE] "
            "FROM [TERM_RATE_MODEFACT] ORDER BY [Index(MODEFACT)]"
        )
        rows = cursor.fetchall()
        cursor.close()
        headers = [
            "Index", "PAC-S", "PAC-Q", "PAC-M", "DIR-S", "DIR-Q", "DIR-M",
            "PAC-S Fee", "PAC-Q Fee", "PAC-M Fee", "DIR-S Fee", "DIR-Q Fee", "DIR-M Fee",
        ]
        return headers, [tuple(r) for r in rows]

    def load_band_amounts_for_viewer(self) -> tuple:
        """Return band specs from TERM_RATE_BANDSPECS."""
        cursor = self.connect().cursor()
        cursor.execute(
            "SELECT [Index(BANDSPEC)], [Band], [SpecifiedAmount], [BandCode] "
            "FROM [TERM_RATE_BANDSPECS] ORDER BY [Index(BANDSPEC)], [Band]"
        )
        rows = cursor.fetchall()
        cursor.close()
        headers = ["BandSpec Index", "Band", "Specified Amount ($)", "Band Code"]
        return headers, [tuple(r) for r in rows]

    def load_policy_fees_for_viewer(self) -> tuple:
        """Return policy fees from TERM_POINT_PV."""
        cursor = self.connect().cursor()
        cursor.execute(
            "SELECT [Plancode], [FEE] FROM [TERM_POINT_PV] "
            "ORDER BY [Plancode]"
        )
        rows = cursor.fetchall()
        cursor.close()
        headers = ["Plancode", "Annual Fee ($)"]
        return headers, [tuple(r) for r in rows]
