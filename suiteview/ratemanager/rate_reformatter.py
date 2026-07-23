"""
Rate Reformatter — Convert Cyberlife IAF rates to UL_Rates database format.

Takes a ParseResult (from IAFParser) and produces three CSV files:
  1. Current COI rates  (RATE table, Scale=1..N) — one scale per start date,
     Scale 1 = most recent, Scale 2 = next most recent, etc.
     Select+ultimate expanded to fully select.
  2. Guaranteed COI rates (RATE table, Scale=0)  — ultimate expanded to fully select
  3. Target premiums     (RATE_TRGPRM table)     — MTP, CTP, TBL4PREM,
     TBL1MTP, TBL1CTP

Also produces a POINTER table CSV mapping (Sex, RateClass, Band) →
  Index(COI) and Index(TRGPREM).  IssueVersion is always 1 and State is "AA".
  Index(COI) keys the current + guaranteed COI tables; Index(TRGPREM) keys
  the target-premium table.  Each index space starts at *starting_index* and
  increments per distinct rate table (combos with identical rates share one
  index), matching the benefit-DB convention.

Key transformations:
  - Select+Ultimate → Fully Select:  durations beyond the select period
    are filled with the ultimate rate at the corresponding attained age.
  - Table 4 target rates (plan_option='E*') are divided by 4 to get Table 1.
  - Guaranteed COI is expanded to fully select the same way as current:
    select-period G rates (durations 1..N) are used where present, ultimate
    G rates fill the rest at attained_age = issue_age + duration - 1.
  - Duration-00-only rates (no select rows, no duration-99 ultimate) act as
    ultimate rates keyed by attained age — some plans (e.g. 1A130D29,
    NU1F3B00) store their entire rate table this way.
  - Multiple start dates for type C rates produce multiple scales
    (e.g. 01/01/2015 → Scale 1, 01/01/1900 → Scale 2).

Anything the reformat cannot map (unknown rate types like N/W, duration-00
rows alongside a select table) is counted in ``self.warnings`` — never
silently dropped.
"""

import csv
import os
from collections import defaultdict, OrderedDict
from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, List, Optional, Tuple, Callable

from suiteview.ratemanager.parser import ParseResult


# ---------------------------------------------------------------------------
# Data types
# ---------------------------------------------------------------------------

@dataclass
class PointerRecord:
    """One row of the POINTER table."""
    plancode: str
    issue_version: str
    sex: str
    rate_class: str
    band: str
    state: str
    index_coi: Optional[int]
    index_trgprem: Optional[int]


@dataclass
class ReformatResult:
    """Paths produced by a reformat run."""
    pointer_csv: str = ""
    current_coi_csv: str = ""
    guaranteed_coi_csv: str = ""
    target_csv: str = ""
    combo_count: int = 0
    current_coi_rows: int = 0
    guaranteed_coi_rows: int = 0
    target_rows: int = 0
    error: Optional[str] = None
    # Distinct index counts (after dedup) per index space.
    coi_index_count: int = 0
    trg_index_count: int = 0
    # Multi-scale current COI info: list of (scale_number, date_string) pairs
    # Scale 0 = Guaranteed, Scale 1 = most recent current, Scale 2 = next, etc.
    current_scales: List[Tuple[int, str]] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Combo key type alias
# ---------------------------------------------------------------------------

ComboKey = Tuple[str, str, str]   # (gender, rate_class, band)


# ---------------------------------------------------------------------------
# Main reformatter
# ---------------------------------------------------------------------------

class RateReformatter:
    """Convert parsed IAF data into UL_Rates database CSV files.

    Parameters
    ----------
    parse_result : ParseResult
        Output from IAFParser.parse().
    starting_index : int
        First POINTER index to assign (increments per combo).
    progress_callback : callable, optional
        Called with (current_step, total_steps) for progress reporting.
    """

    def __init__(
        self,
        parse_result: ParseResult,
        starting_index: int = 13400,
        progress_callback: Optional[Callable[[int, int], None]] = None,
        trg_starting_index: Optional[int] = None,
    ):
        self.result = parse_result
        self.starting_index = starting_index
        self.trg_starting_index = (
            trg_starting_index if trg_starting_index is not None else starting_index
        )
        self._progress = progress_callback
        self.warnings: List[str] = []

        # Derived from product info
        self.pay_age: int = self._get_pay_age()
        self.max_att_age: int = self.pay_age - 1          # e.g. 120
        self.plancode: str = self._get_plancode()
        self.issue_version: str = self._get_issue_version()

        # Pre-index all rates by type / combo / plan_option for fast lookup
        self._index_rates()

    # ------------------------------------------------------------------
    # Internal: extract product-level info
    # ------------------------------------------------------------------

    def _get_pay_age(self) -> int:
        """Extract PAY-AGE from the first ProductInfo record."""
        if self.result.products:
            return self.result.products[0].pay_age
        return 121  # sensible default for UL products

    def _get_plancode(self) -> str:
        if self.result.products:
            return self.result.products[0].plancode.strip()
        return ""

    def _get_issue_version(self) -> str:
        if self.result.products:
            return self.result.products[0].version.strip()
        return ""

    # ------------------------------------------------------------------
    # Internal: build lookup dictionaries
    # ------------------------------------------------------------------

    @staticmethod
    def _parse_scale_date(date_str: str) -> datetime:
        """Parse a scale_start date string (MM/DD/YYYY) for sorting."""
        try:
            return datetime.strptime(date_str.strip(), "%m/%d/%Y")
        except (ValueError, TypeError):
            return datetime(1900, 1, 1)

    def _index_rates(self):
        """Build nested dicts for O(1) rate lookups.

        Current COI rates (type 'C') are indexed *per scale_start date*
        so that multiple vintages of current rates are kept separate.

        Structure per rate type:
            _coi_select_by_date[date][combo][(issue_age, duration)] = rate
            _coi_ultimate_by_date[date][combo][attained_age]        = rate
            _coi_dur0_by_date[date][combo][attained_age]             = rate
            _guar_select[combo][(issue_age, duration)] = rate
            _guar_ultimate[combo][attained_age]        = rate
            _guar_dur0[combo][attained_age]            = rate
            _ctp_base[combo][attained_age]             = rate   (T, opt='**')
            _ctp_tbl4[combo][attained_age]             = rate   (T, opt='E*')
            _mtp_base[combo][attained_age]             = rate   (M, opt='**')
            _mtp_tbl4[combo][attained_age]             = rate   (M, opt='E*')
        """
        # Current COI indexed by date
        self._coi_select_by_date: Dict[str, Dict[ComboKey, Dict[Tuple[int, int], float]]] = defaultdict(lambda: defaultdict(dict))
        self._coi_ultimate_by_date: Dict[str, Dict[ComboKey, Dict[int, float]]] = defaultdict(lambda: defaultdict(dict))
        self._coi_dur0_by_date: Dict[str, Dict[ComboKey, Dict[int, float]]] = defaultdict(lambda: defaultdict(dict))
        self._guar_select: Dict[ComboKey, Dict[Tuple[int, int], float]] = defaultdict(dict)
        self._guar_ultimate: Dict[ComboKey, Dict[int, float]] = defaultdict(dict)
        self._guar_dur0: Dict[ComboKey, Dict[int, float]] = defaultdict(dict)
        self._ctp_base: Dict[ComboKey, Dict[int, float]] = defaultdict(dict)
        self._ctp_tbl4: Dict[ComboKey, Dict[int, float]] = defaultdict(dict)
        self._mtp_base: Dict[ComboKey, Dict[int, float]] = defaultdict(dict)
        self._mtp_tbl4: Dict[ComboKey, Dict[int, float]] = defaultdict(dict)
        unmapped_types: Dict[str, int] = defaultdict(int)

        for r in self.result.rates:
            combo: ComboKey = (r.gender, r.rate_class, r.band)
            opt = r.plan_option.strip()

            if r.rate_type == 'C' and opt == '**':
                dt = r.scale_start
                if r.duration == 99:
                    self._coi_ultimate_by_date[dt][combo][r.attained_age] = r.rate
                elif r.duration == 0:
                    self._coi_dur0_by_date[dt][combo][r.attained_age] = r.rate
                else:
                    self._coi_select_by_date[dt][combo][(r.issue_age, r.duration)] = r.rate

            elif r.rate_type == 'G' and opt == '**':
                # Guaranteed COI — usually ultimate (dur=99) but some plans
                # carry a full select+ultimate guaranteed table (1U135D00)
                # or duration-00-only rates (NU1F3B00).
                if r.duration == 99:
                    self._guar_ultimate[combo][r.attained_age] = r.rate
                elif r.duration == 0:
                    self._guar_dur0[combo][r.attained_age] = r.rate
                else:
                    self._guar_select[combo][(r.issue_age, r.duration)] = r.rate

            elif r.rate_type == 'T':
                if opt == '**':
                    self._ctp_base[combo][r.attained_age] = r.rate
                elif opt == 'E*':
                    self._ctp_tbl4[combo][r.attained_age] = r.rate

            elif r.rate_type == 'M':
                if opt == '**':
                    self._mtp_base[combo][r.attained_age] = r.rate
                elif opt == 'E*':
                    self._mtp_tbl4[combo][r.attained_age] = r.rate

            elif r.rate_type not in ('C', 'G', 'T', 'M') and opt in ('**', 'E*'):
                unmapped_types[r.rate_type] += 1

        # Duration-00-only rates act as ultimate rates keyed by attained age.
        # If a combo has select or dur-99 ultimate rates too, the dur-0 rows
        # are ambiguous — leave them out and warn instead of guessing.
        unused_dur0 = 0
        for dt in list(self._coi_dur0_by_date.keys()):
            for combo, dur0 in list(self._coi_dur0_by_date[dt].items()):
                has_other = (
                    bool(self._coi_select_by_date.get(dt, {}).get(combo))
                    or bool(self._coi_ultimate_by_date.get(dt, {}).get(combo))
                )
                if has_other:
                    unused_dur0 += len(dur0)
                else:
                    self._coi_ultimate_by_date[dt][combo] = dur0
        if unused_dur0:
            self.warnings.append(
                f"{unused_dur0:,} duration-00 current-COI rows coexist with a "
                "select/ultimate table and were not used (ambiguous).")

        unused_g_dur0 = 0
        for combo, dur0 in list(self._guar_dur0.items()):
            has_other = (
                bool(self._guar_select.get(combo))
                or bool(self._guar_ultimate.get(combo))
            )
            if has_other:
                unused_g_dur0 += len(dur0)
            else:
                self._guar_ultimate[combo] = dur0
        if unused_g_dur0:
            self.warnings.append(
                f"{unused_g_dur0:,} duration-00 guaranteed-COI rows coexist "
                "with a select/ultimate table and were not used (ambiguous).")

        for rt, count in sorted(unmapped_types.items()):
            if rt == 'W':
                # W = surrender target — no longer used; intentionally skipped.
                self.warnings.append(
                    f"Rate type 'W' (surrender target — not used): "
                    f"{count:,} rows skipped.")
            else:
                self.warnings.append(
                    f"Rate type '{rt}': {count:,} base-plan rows are not "
                    "mapped to any output table (unhandled type).")

        # Build sorted list of current COI scale dates (most recent first → Scale 1)
        all_c_dates = set()
        all_c_dates.update(self._coi_select_by_date.keys())
        all_c_dates.update(self._coi_ultimate_by_date.keys())
        self._coi_dates: List[str] = sorted(
            all_c_dates, key=self._parse_scale_date, reverse=True
        )
        # Scale mapping: Scale 1 = most recent, Scale 2 = next, etc.
        self._scale_for_date: Dict[str, int] = {
            dt: i + 1 for i, dt in enumerate(self._coi_dates)
        }

        # Guaranteed select period (0 when G is ultimate-only).
        self._guar_select_period: int = max(
            (dur for rates in self._guar_select.values() for (_ia, dur) in rates),
            default=0,
        )

    # ------------------------------------------------------------------
    # Determine combos & select period
    # ------------------------------------------------------------------

    def _get_banded_combos(self) -> List[ComboKey]:
        """Return sorted list of banded combos that have current COI rates."""
        combos = set()
        for dt in self._coi_dates:
            combos.update(self._coi_select_by_date.get(dt, {}).keys())
            combos.update(self._coi_ultimate_by_date.get(dt, {}).keys())
            combos.update(self._coi_dur0_by_date.get(dt, {}).keys())
        return sorted(combos)

    def _get_select_period(self, date_str: str = None) -> int:
        """Determine the select period length from the data.

        If date_str is given, only consider that date's data.
        Otherwise consider all dates.
        """
        max_dur = 0
        dates_to_check = [date_str] if date_str else self._coi_dates
        for dt in dates_to_check:
            for key_map in self._coi_select_by_date.get(dt, {}).values():
                for (ia, dur) in key_map:
                    if dur > max_dur:
                        max_dur = dur
        return max_dur  # e.g. 24

    def _get_issue_age_range(self, date_str: str = None) -> Tuple[int, int]:
        """Determine min/max issue age from dur=0 data (or select data).

        If date_str is given, only consider that date's data.
        Otherwise consider all dates.
        """
        ages = set()
        dates_to_check = [date_str] if date_str else self._coi_dates
        for dt in dates_to_check:
            for age_map in self._coi_dur0_by_date.get(dt, {}).values():
                ages.update(age_map.keys())
        if not ages:
            for dt in dates_to_check:
                for key_map in self._coi_select_by_date.get(dt, {}).values():
                    for (ia, _dur) in key_map:
                        ages.add(ia)
        if not ages:
            return (0, 85)
        return (min(ages), max(ages))

    # ------------------------------------------------------------------
    # Guaranteed COI: map band→class for band=0 lookup
    # ------------------------------------------------------------------

    def _guar_class_combo(self, combo: ComboKey) -> ComboKey:
        """Map a banded combo to its class-level band=0 combo for G rates.

        G rates only exist at band='0' (class-level).  A banded combo like
        ('Y','N','A') maps to ('Y','N','0').
        """
        return (combo[0], combo[1], '0')

    # ------------------------------------------------------------------
    # CTP: map banded combo to class-level band=0 for base CTP
    # ------------------------------------------------------------------

    def _ctp_class_combo(self, combo: ComboKey) -> ComboKey:
        """T(opt='**') rates exist only at band='0'."""
        return (combo[0], combo[1], '0')

    # ------------------------------------------------------------------
    # Guaranteed COI lookup (band-robust)
    # ------------------------------------------------------------------

    def _guar_rates_for(self, combo: ComboKey) -> Dict[int, float]:
        """Return the guaranteed ultimate rates for *combo*.

        Guaranteed rates are usually unbanded (stored at band='0').  Try the
        combo's own band first, then fall back to the class-level band='0'
        table so banded combos still resolve to the shared guaranteed rates
        via the POINTER mapping.
        """
        rates = self._guar_ultimate.get(combo)
        if rates:
            return rates
        return self._guar_ultimate.get(self._guar_class_combo(combo), {})

    def _guar_select_for(self, combo: ComboKey) -> Dict[Tuple[int, int], float]:
        """Guaranteed select rates for *combo* (same band='0' fallback)."""
        rates = self._guar_select.get(combo)
        if rates:
            return rates
        return self._guar_select.get(self._guar_class_combo(combo), {})

    # ------------------------------------------------------------------
    # Index assignment (dedup: identical rate tables share an index)
    # ------------------------------------------------------------------

    def _coi_signature(self, combo: ComboKey) -> tuple:
        """Signature of a combo's COI content (current across scales + guar)."""
        parts = []
        for dt in self._coi_dates:
            sel = self._coi_select_by_date.get(dt, {}).get(combo, {})
            ult = self._coi_ultimate_by_date.get(dt, {}).get(combo, {})
            parts.append((
                dt,
                tuple(sorted(sel.items())),
                tuple(sorted(ult.items())),
            ))
        parts.append(('G', tuple(sorted(self._guar_rates_for(combo).items()))))
        parts.append(('Gsel', tuple(sorted(self._guar_select_for(combo).items()))))
        return tuple(parts)

    def _trg_signature(self, combo: ComboKey) -> tuple:
        """Signature of a combo's target-premium content."""
        class_combo = self._ctp_class_combo(combo)
        ctp_rates = self._ctp_base.get(combo)
        if not ctp_rates:
            ctp_rates = self._ctp_base.get(class_combo, {})
        return (
            tuple(sorted(ctp_rates.items())),
            tuple(sorted(self._ctp_tbl4.get(class_combo, {}).items())),
            tuple(sorted(self._mtp_base.get(combo, {}).items())),
            tuple(sorted(self._mtp_tbl4.get(class_combo, {}).items())),
        )

    def _assign_coi_indices(
        self, combos: List[ComboKey],
    ) -> Tuple[Dict[ComboKey, int], List[Tuple[int, ComboKey]]]:
        """Assign Index(COI) per distinct COI rate table.

        Returns ``(combo→index, [(index, representative_combo)])``.  Combos
        with identical COI content share one index; each distinct table is
        emitted once using its representative combo.
        """
        coi_index: Dict[ComboKey, int] = {}
        groups: "OrderedDict[tuple, int]" = OrderedDict()
        reps: List[Tuple[int, ComboKey]] = []
        next_idx = self.starting_index
        for combo in combos:
            sig = self._coi_signature(combo)
            idx = groups.get(sig)
            if idx is None:
                idx = next_idx
                groups[sig] = idx
                reps.append((idx, combo))
                next_idx += 1
            coi_index[combo] = idx
        return coi_index, reps

    def _assign_trg_indices(
        self, combos: List[ComboKey],
    ) -> Tuple[Dict[ComboKey, int], List[Tuple[int, ComboKey]]]:
        """Assign Index(TRGPREM) per distinct target-premium table.

        Combos without any target content are omitted (blank Index(TRGPREM)).
        """
        trg_index: Dict[ComboKey, int] = {}
        groups: "OrderedDict[tuple, int]" = OrderedDict()
        reps: List[Tuple[int, ComboKey]] = []
        next_idx = self.trg_starting_index
        for combo in combos:
            sig = self._trg_signature(combo)
            if not any(sig):
                continue
            idx = groups.get(sig)
            if idx is None:
                idx = next_idx
                groups[sig] = idx
                reps.append((idx, combo))
                next_idx += 1
            trg_index[combo] = idx
        return trg_index, reps

    # ------------------------------------------------------------------
    # Artifact issue-age filtering
    # ------------------------------------------------------------------

    @staticmethod
    def filter_artifact_issue_ages(rows, removed: Optional[set] = None):
        """Drop ``(index, scale, issue_age)`` series whose first duration > 1.

        Some IAFs pad issue ages outside the product's true issue range with
        default rates (below the real minimum, and sometimes above the real
        maximum). The giveaway is a rate series that does not start at
        duration 1 — e.g. issue age 0 whose first rate is at duration 17 on
        a 16+ plan. Those series are meaningless and are removed; removed
        keys are collected into ``removed`` when given.
        """
        current = None
        skipping = False
        for row in rows:
            key = (row[0], row[1], row[2])     # (index, scale, issue_age)
            if key != current:
                current = key
                skipping = row[3] > 1
                if skipping and removed is not None:
                    removed.add(key)
            if not skipping:
                yield row

    # ------------------------------------------------------------------
    # Public: compute combos + index assignments (no files written)
    # ------------------------------------------------------------------

    def compute(self) -> dict:
        """Return the pointer combos and index assignments for this IAF.

        Used by the Rate Workup builder, which writes its own merged output
        files from the row generators. Keys:
          combos, coi_index, coi_reps, trg_index, trg_reps,
          select_period, ia_min, ia_max, current_scales
        """
        combos = self._get_banded_combos()
        coi_index, coi_reps = self._assign_coi_indices(combos)
        trg_index, trg_reps = self._assign_trg_indices(combos)
        ia_min, ia_max = self._get_issue_age_range()
        return {
            "combos": combos,
            "coi_index": coi_index,
            "coi_reps": coi_reps,
            "trg_index": trg_index,
            "trg_reps": trg_reps,
            "select_period": self._get_select_period(),
            "ia_min": ia_min,
            "ia_max": ia_max,
            "current_scales": [
                (self._scale_for_date[dt], dt) for dt in self._coi_dates
            ],
        }

    # ------------------------------------------------------------------
    # Public: run the full reformat
    # ------------------------------------------------------------------

    def reformat(self, output_dir: str) -> ReformatResult:
        """Generate all four CSV files in *output_dir*.

        Returns a ReformatResult with paths and row counts.
        """
        os.makedirs(output_dir, exist_ok=True)
        res = ReformatResult()

        try:
            # 1. Build POINTER + per-table index assignments (with dedup).
            combos = self._get_banded_combos()
            coi_index, coi_reps = self._assign_coi_indices(combos)
            trg_index, trg_reps = self._assign_trg_indices(combos)
            res.combo_count = len(combos)
            res.coi_index_count = len(coi_reps)
            res.trg_index_count = len(trg_reps)

            select_period = self._get_select_period()
            ia_min, ia_max = self._get_issue_age_range()

            # Record current COI scale → date mapping
            res.current_scales = [
                (self._scale_for_date[dt], dt) for dt in self._coi_dates
            ]

            total_steps = 4
            step = 0

            # 2. POINTER CSV
            res.pointer_csv = os.path.join(output_dir, "POINTER.csv")
            self._write_pointer_csv(res.pointer_csv, combos, coi_index, trg_index)
            step += 1
            if self._progress:
                self._progress(step, total_steps)

            # 3. Current COI (all scales in one file)
            res.current_coi_csv = os.path.join(output_dir, "RATE_COI_CURRENT.csv")
            res.current_coi_rows = self._write_current_coi(
                res.current_coi_csv, coi_reps,
                select_period, ia_min, ia_max,
            )
            step += 1
            if self._progress:
                self._progress(step, total_steps)

            # 4. Guaranteed COI
            res.guaranteed_coi_csv = os.path.join(output_dir, "RATE_COI_GUARANTEED.csv")
            res.guaranteed_coi_rows = self._write_guaranteed_coi(
                res.guaranteed_coi_csv, coi_reps,
                ia_min, ia_max,
            )
            step += 1
            if self._progress:
                self._progress(step, total_steps)

            # 5. Target premiums
            res.target_csv = os.path.join(output_dir, "RATE_TRGPRM.csv")
            res.target_rows = self._write_target_premiums(
                res.target_csv, trg_reps,
                ia_min, ia_max,
            )
            step += 1
            if self._progress:
                self._progress(step, total_steps)

        except Exception as exc:
            res.error = str(exc)

        return res

    # ------------------------------------------------------------------
    # POINTER CSV
    # ------------------------------------------------------------------

    def _write_pointer_csv(
        self,
        filepath: str,
        combos: List[ComboKey],
        coi_index: Dict[ComboKey, int],
        trg_index: Dict[ComboKey, int],
    ):
        with open(filepath, 'w', newline='') as f:
            w = csv.writer(f)
            w.writerow([
                "Plancode", "IssueVersion", "Sex", "RateClass", "Band",
                "State", "Index(COI)", "Index(TRGPREM)",
            ])
            for combo in combos:
                ci = coi_index.get(combo)
                ti = trg_index.get(combo)
                w.writerow([
                    self.plancode,
                    "1",                                  # IssueVersion always 1
                    combo[0],                             # sex / gender
                    combo[1],                             # rate_class
                    combo[2],                             # band
                    "AA",                                 # State always AA
                    ci if ci is not None else "",
                    ti if ti is not None else "",
                ])

    # ------------------------------------------------------------------
    # Current COI (RATE table, Scale=1..N for each start date)
    # ------------------------------------------------------------------

    def _write_current_coi(
        self,
        filepath: str,
        coi_reps: List[Tuple[int, ComboKey]],
        select_period: int,
        ia_min: int,
        ia_max: int,
    ) -> int:
        row_count = 0
        removed: set = set()
        with open(filepath, 'w', newline='') as f:
            w = csv.writer(f)
            w.writerow(["Index(COI)", "Scale", "IssueAge", "Duration", "Rate"])
            for idx, scale, ia, dur, rate in self.filter_artifact_issue_ages(
                    self.current_coi_rows(coi_reps, select_period, ia_min, ia_max),
                    removed):
                w.writerow([idx, scale, ia, dur, f"{rate:.6f}"])
                row_count += 1
        if removed:
            self.warnings.append(
                f"Current COI: dropped {len(removed)} artifact issue-age "
                "series (first duration > 1 — outside the true issue range).")
        return row_count

    def current_coi_rows(
        self,
        coi_reps: List[Tuple[int, ComboKey]],
        select_period: int,
        ia_min: int,
        ia_max: int,
    ):
        """Yield ``(index, scale, issue_age, duration, rate)`` for current COI.

        Expands select+ultimate C rates into fully select format. Multiple
        start dates produce multiple scales:
          Scale 1 = most recent start date, Scale 2 = next most recent, etc.

        For each scale, combo and issue_age:
          - dur 1..select_period  →  use select rate from data
          - dur select_period+1.. →  use ultimate rate at att_age
          - att_age = issue_age + duration - 1  (age 55 dur 1 = attained 55)
          - max_dur such that att_age <= max_att_age
        """
        for dt in self._coi_dates:
            scale = self._scale_for_date[dt]
            # Use per-date select period if it differs
            dt_select_period = self._get_select_period(dt) or select_period

            for idx, combo in coi_reps:
                sel_rates = self._coi_select_by_date.get(dt, {}).get(combo, {})
                ult_rates = self._coi_ultimate_by_date.get(dt, {}).get(combo, {})

                if not sel_rates and not ult_rates:
                    continue  # no C rates for this combo at this date

                for ia in range(ia_min, ia_max + 1):
                    # att_age = ia + dur - 1, so max dur where att_age <= max_att_age
                    max_dur = self.max_att_age - ia + 1
                    if max_dur < 1:
                        continue

                    for dur in range(1, max_dur + 1):
                        att_age = ia + dur - 1
                        if dur <= dt_select_period:
                            rate = sel_rates.get((ia, dur))
                        else:
                            rate = ult_rates.get(att_age)

                        if rate is not None:
                            yield idx, scale, ia, dur, rate

    # ------------------------------------------------------------------
    # Guaranteed COI (RATE table, Scale=0)
    # ------------------------------------------------------------------

    def _write_guaranteed_coi(
        self,
        filepath: str,
        coi_reps: List[Tuple[int, ComboKey]],
        ia_min: int,
        ia_max: int,
    ) -> int:
        row_count = 0
        removed: set = set()
        with open(filepath, 'w', newline='') as f:
            w = csv.writer(f)
            w.writerow(["Index(COI)", "Scale", "IssueAge", "Duration", "Rate"])
            for idx, scale, ia, dur, rate in self.filter_artifact_issue_ages(
                    self.guaranteed_coi_rows(coi_reps, ia_min, ia_max), removed):
                w.writerow([idx, scale, ia, dur, f"{rate:.6f}"])
                row_count += 1
        if removed:
            self.warnings.append(
                f"Guaranteed COI: dropped {len(removed)} artifact issue-age "
                "series (first duration > 1 — outside the true issue range).")
        return row_count

    def guaranteed_coi_rows(
        self,
        coi_reps: List[Tuple[int, ComboKey]],
        ia_min: int,
        ia_max: int,
    ):
        """Yield ``(index, 0, issue_age, duration, rate)`` for guaranteed COI.

        Expands G rates into fully select format exactly like current COI:
        select-period G rates are used where present (some plans carry a full
        select+ultimate guaranteed table), the ultimate rate at attained age
        fills the rest. G rates are usually stored at band='0' (class-level);
        each banded combo falls back to the class-level table.
        """
        scale = 0
        for idx, combo in coi_reps:
            sel_rates = self._guar_select_for(combo)
            ult_rates = self._guar_rates_for(combo)

            if not sel_rates and not ult_rates:
                continue  # no guaranteed rates for this class

            for ia in range(ia_min, ia_max + 1):
                # att_age = ia + dur - 1
                max_dur = self.max_att_age - ia + 1
                if max_dur < 1:
                    continue

                for dur in range(1, max_dur + 1):
                    att_age = ia + dur - 1
                    if dur <= self._guar_select_period:
                        rate = sel_rates.get((ia, dur))
                        if rate is None:
                            rate = ult_rates.get(att_age)
                    else:
                        rate = ult_rates.get(att_age)

                    if rate is not None:
                        yield idx, scale, ia, dur, rate

    # ------------------------------------------------------------------
    # Target premiums (RATE_TRGPRM)
    # ------------------------------------------------------------------

    def _write_target_premiums(
        self,
        filepath: str,
        trg_reps: List[Tuple[int, ComboKey]],
        ia_min: int,
        ia_max: int,
    ) -> int:
        row_count = 0
        with open(filepath, 'w', newline='') as f:
            w = csv.writer(f)
            w.writerow([
                "Index(TRGPREM)", "IssueAge", "Rate(MTP)", "Rate(CTP)",
                "Rate(TBL4PREM)", "Rate(TBL1MTP)", "Rate(TBL1CTP)",
            ])
            for idx, ia, ctp, tbl1ctp, mtp, tbl1mtp, tbl4prem in self.target_rows(
                    trg_reps, ia_min, ia_max):
                w.writerow([
                    idx,
                    ia,
                    f"{mtp:.6f}" if mtp is not None else "",
                    f"{ctp:.6f}" if ctp is not None else "",
                    f"{tbl4prem:.6f}" if tbl4prem is not None else "",
                    f"{tbl1mtp:.6f}" if tbl1mtp is not None else "",
                    f"{tbl1ctp:.6f}" if tbl1ctp is not None else "",
                ])
                row_count += 1
        return row_count

    def target_rows(
        self,
        trg_reps: List[Tuple[int, ComboKey]],
        ia_min: int,
        ia_max: int,
    ):
        """Yield target-premium values, including the raw Table-4 premium.

        Values are floats or None:
          CTP      = T rate (opt='**') at class-level band='0'
          TBL4PREM = M/T rate (opt='E*'); both types must agree when present
          TBL1CTP  = T rate (opt='E*') / 4  (Table 4 → Table 1)
          MTP      = M rate (opt='**') at band level
          TBL1MTP  = M rate (opt='E*') / 4
        """
        for idx, combo in trg_reps:
            class_combo = self._ctp_class_combo(combo)
            # Main T/** rates are normally banded; some plans use band 0.
            ctp_rates = self._ctp_base.get(combo)
            if not ctp_rates:
                ctp_rates = self._ctp_base.get(class_combo, {})
            # E* Table-4 rates are unbanded and apply to every base band.
            tbl4ctp_rates = self._ctp_tbl4.get(class_combo, {})
            # MTP at the banded combo level
            mtp_rates = self._mtp_base.get(combo, {})
            # Table-4 M rates
            tbl4mtp_rates = self._mtp_tbl4.get(class_combo, {})

            for ia in range(ia_min, ia_max + 1):
                ctp = ctp_rates.get(ia)
                tbl4ctp = tbl4ctp_rates.get(ia)
                mtp = mtp_rates.get(ia)
                tbl4mtp = tbl4mtp_rates.get(ia)

                if (tbl4ctp is not None and tbl4mtp is not None
                        and tbl4ctp != tbl4mtp):
                    raise ValueError(
                        "M and T Table-4 premium rates disagree for "
                        f"sex={combo[0]}, class={combo[1]}, band={combo[2]}, "
                        f"issue age={ia}: M={tbl4mtp}, T={tbl4ctp}."
                    )

                tbl4prem = tbl4mtp if tbl4mtp is not None else tbl4ctp
                tbl1ctp_val = (
                    round(tbl4ctp / 4.0, 2) if tbl4ctp is not None else None
                )
                tbl1mtp_val = (
                    round(tbl4mtp / 4.0, 2) if tbl4mtp is not None else None
                )

                if ctp is None and tbl1ctp_val is None and mtp is None and tbl1mtp_val is None:
                    continue

                yield idx, ia, ctp, tbl1ctp_val, mtp, tbl1mtp_val, tbl4prem
