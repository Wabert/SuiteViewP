"""In-memory UL_Rates schema ``rates`` for ``ULRates`` unit tests.

``FakeSchemaRepo`` answers the ``RatesSchemaRepository`` reads that
``suiteview.illustration.core.ul_rates.ULRates`` makes, from cells and plan rates the
test adds, so rate-reader behavior is tested without UL_Rates.
"""
from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Dict, List, Optional, Sequence, Tuple

from suiteview.core.rates_schema import (
    BandSpec,
    CellAssignment,
    PlanAssignment,
    PlanDef,
    RateSetInfo,
    RateTypeDef,
    ScheduleWindow,
)

CALENDAR_TYPES = frozenset({"COI", "EPU", "MFEE", "PREMLOAD_PCT", "PREMLOAD_EXS", "PREMLOAD_FLAT"})


class FakeSchemaRepo:
    """One or more plans with the cells, windows and rate values a test adds."""

    def __init__(self, plancode: str = "TEST", company: str = "00"):
        self.plans: Dict[str, PlanDef] = {}
        self.cells: List[CellAssignment] = []
        self.cell_plans: Dict[int, str] = {}
        self.windows: List[ScheduleWindow] = []
        self.sets: Dict[int, RateSetInfo] = {}
        self.values: Dict[int, Dict[Tuple[int, int], Decimal]] = {}
        self.plan_rates: List[Tuple[str, PlanAssignment]] = []
        self.bands: Dict[str, List[BandSpec]] = {}
        self.queries: List[str] = []
        self.add_plan(plancode, company)

    def add_plan(self, plancode: str, company: str = "00") -> None:
        self.plans[plancode] = PlanDef(company, plancode, company, "UL", "BASE", f"{plancode} test", ())

    def _rate_set(self, rate_type: str, grain: str, values: Dict[Tuple[int, int], float]) -> int:
        rate_set_id = len(self.sets) + 1
        self.sets[rate_set_id] = RateSetInfo(rate_set_id, rate_type, grain, "", "")
        self.values[rate_set_id] = {key: None if v is None else Decimal(str(v)) for key, v in values.items()}
        return rate_set_id

    def add_cell(self, rate_type: str, windows: Sequence[Tuple[date, Optional[date], dict]], *,
                 plancode: str = "TEST", sex: str = "M", rate_class: str = "N", band: str = "1",
                 state: str = "**", benefit: str = "", scale: str = "G", grain: str = "IA_DUR") -> None:
        """``windows`` is ``[(effective_from, effective_to, {(issue_age, duration): rate}[, scale])]``;
        a window without its own scale is on ``scale``."""
        schedule_id = len(self.cells) + 1
        self.cells.append(CellAssignment(benefit, sex, rate_class, band, state, "", rate_type, schedule_id))
        self.cell_plans[schedule_id] = plancode
        for start, end, values, *window_scale in windows:
            self.windows.append(ScheduleWindow(schedule_id, window_scale[0] if window_scale else scale,
                                               start, end, self._rate_set(rate_type, grain, values)))

    def add_plan_rate(self, rate_type: str, values: dict, *, plancode: str = "TEST", scale: str = "G",
                      grain: str = "DUR", state: str = "**") -> None:
        rate_set_id = self._rate_set(rate_type, grain, values)
        self.plan_rates.append((plancode, PlanAssignment(state, rate_type, scale, rate_set_id)))

    def add_band(self, band: str, upper_limit, *, plancode: str = "TEST", start: date = date(1900, 1, 1),
                 source_band: str = "") -> None:
        limit = None if upper_limit is None else Decimal(str(upper_limit))
        self.bands.setdefault(plancode, []).append(BandSpec(band, start, "", limit, source_band))

    # -- RatesSchemaRepository reads -------------------------------------------------

    def rate_types(self):
        return {t: RateTypeDef(t, "", "CELL", "", "CALENDAR" if t in CALENDAR_TYPES else "ISSUE", "UL")
                for t in {c.rate_type for c in self.cells} | CALENDAR_TYPES}

    def plan_defs(self, plancode):
        self.queries.append(f"plan_defs {plancode}")
        return [self.plans[plancode]] if plancode in self.plans else []

    def plan_attrs(self, company, plancode):
        return []

    def plan_bands(self, company, plancode):
        return list(self.bands.get(plancode, []))

    def plan_subseries(self, company, plancode):
        return []

    def cell_assignments(self, company, plancode):
        return [c for c in self.cells if self.cell_plans.get(c.schedule_id) == plancode]

    def schedule_windows(self, schedule_ids):
        return [w for w in self.windows if w.schedule_id in set(schedule_ids)]

    def rate_sets(self, rate_set_ids):
        return {i: self.sets[i] for i in rate_set_ids if i in self.sets}

    def rate_values(self, rate_set_ids, issue_age):
        result = {}
        for i in rate_set_ids:
            grain = self.sets[i].grain
            result[i] = {key: v for key, v in self.values.get(i, {}).items()
                         if grain not in ("IA", "IA_DUR") or key[0] == issue_age}
        return result

    def plan_assignments(self, company, plancode):
        return [a for p, a in self.plan_rates if p == plancode]

    def fund_assignments(self, company, plancode):
        return []

    def fund_rates(self, fund_keys):
        return []

    def close(self):
        pass
