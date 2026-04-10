"""
Rate Reformatter — Convert Cyberlife IAF rates to UL_Rates database format.

Takes a ParseResult (from IAFParser) and produces three CSV files:
  1. Current COI rates  (RATE table, Scale=1..N) — one scale per start date,
     Scale 1 = most recent, Scale 2 = next most recent, etc.
     Select+ultimate expanded to fully select.
  2. Guaranteed COI rates (RATE table, Scale=0)  — ultimate expanded to fully select
  3. Target premiums     (RATE_TRGPRM table)     — CTP, TBL1CTP, MTP, TBL1MTP

Also produces a POINTER table CSV mapping (Sex, RateClass, Band) → Index.

Key transformations:
  - Select+Ultimate → Fully Select:  durations beyond the select period
    are filled with the ultimate rate at the corresponding attained age.
  - Table 4 target rates (plan_option='E*') are divided by 4 to get Table 1.
  - Guaranteed COI (pure ultimate) is expanded to fully select for all
    issue ages, using the ultimate rate at attained_age = issue_age + duration.
  - Multiple start dates for type C rates produce multiple scales
    (e.g. 01/01/2015 → Scale 1, 01/01/1900 → Scale 2).
"""

import csv
import os
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, List, Optional, Tuple, Callable

from suiteview.ratemanager.parser import ParseResult, RateRecord


# ---------------------------------------------------------------------------
# Data types
# ---------------------------------------------------------------------------

@dataclass
class PointerRecord:
    """One row of the POINTER table."""
    index: int
    plancode: str
    issue_version: str
    sex: str
    rate_class: str
    band: str


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
    ):
        self.result = parse_result
        self.starting_index = starting_index
        self._progress = progress_callback

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
            _guar_ultimate[combo][attained_age]        = rate
            _ctp_base[combo][attained_age]             = rate   (T, opt='**')
            _ctp_tbl4[combo][attained_age]             = rate   (T, opt='E*')
            _mtp_base[combo][attained_age]             = rate   (M, opt='**')
            _mtp_tbl4[combo][attained_age]             = rate   (M, opt='E*')
        """
        # Current COI indexed by date
        self._coi_select_by_date: Dict[str, Dict[ComboKey, Dict[Tuple[int, int], float]]] = defaultdict(lambda: defaultdict(dict))
        self._coi_ultimate_by_date: Dict[str, Dict[ComboKey, Dict[int, float]]] = defaultdict(lambda: defaultdict(dict))
        self._coi_dur0_by_date: Dict[str, Dict[ComboKey, Dict[int, float]]] = defaultdict(lambda: defaultdict(dict))
        self._guar_ultimate: Dict[ComboKey, Dict[int, float]] = defaultdict(dict)
        self._ctp_base: Dict[ComboKey, Dict[int, float]] = defaultdict(dict)
        self._ctp_tbl4: Dict[ComboKey, Dict[int, float]] = defaultdict(dict)
        self._mtp_base: Dict[ComboKey, Dict[int, float]] = defaultdict(dict)
        self._mtp_tbl4: Dict[ComboKey, Dict[int, float]] = defaultdict(dict)

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
                # Guaranteed COI — always ultimate (dur=99)
                self._guar_ultimate[combo][r.attained_age] = r.rate

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

        # Build sorted list of current COI scale dates (most recent first → Scale 1)
        all_c_dates = set()
        all_c_dates.update(self._coi_select_by_date.keys())
        all_c_dates.update(self._coi_ultimate_by_date.keys())
        all_c_dates.update(self._coi_dur0_by_date.keys())
        self._coi_dates: List[str] = sorted(
            all_c_dates, key=self._parse_scale_date, reverse=True
        )
        # Scale mapping: Scale 1 = most recent, Scale 2 = next, etc.
        self._scale_for_date: Dict[str, int] = {
            dt: i + 1 for i, dt in enumerate(self._coi_dates)
        }

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
    # Public: run the full reformat
    # ------------------------------------------------------------------

    def reformat(self, output_dir: str) -> ReformatResult:
        """Generate all four CSV files in *output_dir*.

        Returns a ReformatResult with paths and row counts.
        """
        os.makedirs(output_dir, exist_ok=True)
        res = ReformatResult()

        try:
            # 1. Build POINTER
            combos = self._get_banded_combos()
            pointer: Dict[ComboKey, int] = {}
            for i, combo in enumerate(combos):
                pointer[combo] = self.starting_index + i
            res.combo_count = len(combos)

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
            self._write_pointer_csv(res.pointer_csv, combos, pointer)
            step += 1
            if self._progress:
                self._progress(step, total_steps)

            # 3. Current COI (all scales in one file)
            res.current_coi_csv = os.path.join(output_dir, "RATE_COI_CURRENT.csv")
            res.current_coi_rows = self._write_current_coi(
                res.current_coi_csv, combos, pointer,
                select_period, ia_min, ia_max,
            )
            step += 1
            if self._progress:
                self._progress(step, total_steps)

            # 4. Guaranteed COI
            res.guaranteed_coi_csv = os.path.join(output_dir, "RATE_COI_GUARANTEED.csv")
            res.guaranteed_coi_rows = self._write_guaranteed_coi(
                res.guaranteed_coi_csv, combos, pointer,
                ia_min, ia_max,
            )
            step += 1
            if self._progress:
                self._progress(step, total_steps)

            # 5. Target premiums
            res.target_csv = os.path.join(output_dir, "RATE_TRGPRM.csv")
            res.target_rows = self._write_target_premiums(
                res.target_csv, combos, pointer,
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
        pointer: Dict[ComboKey, int],
    ):
        with open(filepath, 'w', newline='') as f:
            w = csv.writer(f)
            w.writerow(["Index", "Plancode", "IssueVersion", "Sex", "RateClass", "Band"])
            for combo in combos:
                w.writerow([
                    pointer[combo],
                    self.plancode,
                    self.issue_version,
                    combo[0],   # sex / gender
                    combo[1],   # rate_class
                    combo[2],   # band
                ])

    # ------------------------------------------------------------------
    # Current COI (RATE table, Scale=1..N for each start date)
    # ------------------------------------------------------------------

    def _write_current_coi(
        self,
        filepath: str,
        combos: List[ComboKey],
        pointer: Dict[ComboKey, int],
        select_period: int,
        ia_min: int,
        ia_max: int,
    ) -> int:
        """Expand select+ultimate C rates into fully select format.

        Multiple start dates produce multiple scales:
          Scale 1 = most recent start date
          Scale 2 = next most recent
          ...etc.

        For each scale, combo and issue_age:
          - dur 1..select_period  →  use select rate from data
          - dur select_period+1.. →  use ultimate rate at att_age
          - att_age = issue_age + duration - 1  (age 55 dur 1 = attained 55)
          - max_dur such that att_age <= max_att_age
        """
        row_count = 0

        with open(filepath, 'w', newline='') as f:
            w = csv.writer(f)
            w.writerow(["Index", "Scale", "IssueAge", "Duration", "Rate"])

            for dt in self._coi_dates:
                scale = self._scale_for_date[dt]
                # Use per-date select period if it differs
                dt_select_period = self._get_select_period(dt) or select_period

                for combo in combos:
                    idx = pointer[combo]
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
                                w.writerow([idx, scale, ia, dur, f"{rate:.6f}"])
                                row_count += 1

        return row_count

    # ------------------------------------------------------------------
    # Guaranteed COI (RATE table, Scale=0)
    # ------------------------------------------------------------------

    def _write_guaranteed_coi(
        self,
        filepath: str,
        combos: List[ComboKey],
        pointer: Dict[ComboKey, int],
        ia_min: int,
        ia_max: int,
    ) -> int:
        """Expand G ultimate rates into fully select format.

        G rates exist only at band='0' (class-level).  For each banded
        combo we look up the class-level guaranteed rate and replicate it.
        """
        row_count = 0
        scale = 0

        with open(filepath, 'w', newline='') as f:
            w = csv.writer(f)
            w.writerow(["Index", "Scale", "IssueAge", "Duration", "Rate"])

            for combo in combos:
                idx = pointer[combo]
                guar_combo = self._guar_class_combo(combo)
                ult_rates = self._guar_ultimate.get(guar_combo, {})

                if not ult_rates:
                    continue  # no guaranteed rates for this class

                for ia in range(ia_min, ia_max + 1):
                    # att_age = ia + dur - 1
                    max_dur = self.max_att_age - ia + 1
                    if max_dur < 1:
                        continue

                    for dur in range(1, max_dur + 1):
                        att_age = ia + dur - 1
                        rate = ult_rates.get(att_age)

                        if rate is not None:
                            w.writerow([idx, scale, ia, dur, f"{rate:.6f}"])
                            row_count += 1

        return row_count

    # ------------------------------------------------------------------
    # Target premiums (RATE_TRGPRM)
    # ------------------------------------------------------------------

    def _write_target_premiums(
        self,
        filepath: str,
        combos: List[ComboKey],
        pointer: Dict[ComboKey, int],
        ia_min: int,
        ia_max: int,
    ) -> int:
        """Write target premium data.

        Columns:
          CTP      = T rate (opt='**') at class-level band='0'
          TBL1CTP  = T rate (opt='E*') / 4  (Table 4 → Table 1)
          MTP      = M rate (opt='**') at band level
          TBL1MTP  = M rate (opt='E*') / 4
        """
        row_count = 0

        with open(filepath, 'w', newline='') as f:
            w = csv.writer(f)
            w.writerow(["Index", "IssueAge", "CTP", "TBL1CTP", "MTP", "TBL1MTP"])

            for combo in combos:
                idx = pointer[combo]

                # CTP comes from the class-level (band='0') T rates
                ctp_combo = self._ctp_class_combo(combo)
                ctp_rates = self._ctp_base.get(ctp_combo, {})

                # TBL1CTP from table-4 T rates at the banded combo level
                tbl1ctp_rates = self._ctp_tbl4.get(combo, {})

                # MTP at the banded combo level
                mtp_rates = self._mtp_base.get(combo, {})

                # TBL1MTP from table-4 M rates
                tbl1mtp_rates = self._mtp_tbl4.get(combo, {})

                # Only write rows where at least one value exists
                for ia in range(ia_min, ia_max + 1):
                    ctp = ctp_rates.get(ia)
                    tbl1ctp = tbl1ctp_rates.get(ia)
                    mtp = mtp_rates.get(ia)
                    tbl1mtp = tbl1mtp_rates.get(ia)

                    # Divide table-4 values by 4 to get table-1
                    tbl1ctp_val = tbl1ctp / 4.0 if tbl1ctp is not None else None
                    tbl1mtp_val = tbl1mtp / 4.0 if tbl1mtp is not None else None

                    # Skip if nothing to write
                    if ctp is None and tbl1ctp_val is None and mtp is None and tbl1mtp_val is None:
                        continue

                    w.writerow([
                        idx,
                        ia,
                        f"{ctp:.6f}" if ctp is not None else "",
                        f"{tbl1ctp_val:.6f}" if tbl1ctp_val is not None else "",
                        f"{mtp:.6f}" if mtp is not None else "",
                        f"{tbl1mtp_val:.6f}" if tbl1mtp_val is not None else "",
                    ])
                    row_count += 1

        return row_count
