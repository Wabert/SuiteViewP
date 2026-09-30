"""Par WL rates from UL_Rates schema ``rates`` (never the dbo rate tables).

Per coverage phase:

* **Cash values** - the ``CV`` cell (scale G, sub-series keyed) per unit by duration,
  point in time: ``values[d]`` is the tabular value at the end of policy year ``d``.
  Checked against CyberLife's stored ``LOW_DUR_*_CSV_AMT`` by ``inforce_checks``.
* **Premium** - the ``PREM`` cell at the issue age (cross-check only: CyberLife bills
  the coverage's stored ``ANN_PRM_UNT_AMT``).
* **Dividends** - ``RATE_ASSIGN_DIV`` -> ``RATE_SCHEDULE_DATE_DIV`` -> ``RATE_VALUE_DIV``
  with PolView's lookup (``choose_div``): per record type (D premium paying, R reduced
  paid-up), the issue-date cohort and the scale in effect on each anniversary. PUAs
  earn the base rates (participation 1) or the PUA key's rates read at issue age 0 and
  duration = attained age at the anniversary (participation 2), as ``rates.fn_DIV_RATE``.
* **PUI** - paid-up insurance purchase rates per $1,000 by attained age for PUA riders.

Plan level: the regular loan rate (``LOAN_REG_CHG``) and the mode factors
(``RATE_MODEFACT``) of the base plancode. Anything missing that a run needs raises
``ParWLRateError`` naming the item; nothing is guessed.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from decimal import ROUND_DOWN, Decimal
from typing import Dict, List, Optional, Sequence, Tuple

from suiteview.core.rates_schema import DivSchedule, PlanDef
from suiteview.illustration.core.fixed_premium import (
    ModeFactors,
    coverage_band,
    plan_mode_factors,
    resolve_rate_plan,
    window_values,
)
from suiteview.illustration.core.schema_reader import SchemaReader, open_schema_reader
from suiteview.illustration.models.parwl import (
    ROLE_PUA_RIDER,
    ROLE_TERM_RIDER,
    ParWLCoverage,
    ParWLPolicy,
)
from suiteview.polview.models.schema_rates import (
    RateKey,
    choose_cell,
    choose_div,
)

PAR_WL_FAMILIES = frozenset({"PAR_WL", "PUA_RIDER"})
PUI_TABLE_TYPES = {0: "PUI", 1: "PUI_A", 2: "PUI_B", 3: "PUI_C", 4: "PUI_D", 5: "PUI_E", 6: "PUI_F"}


class ParWLRateError(ValueError):
    """A rate the par WL run needs is not in schema ``rates``."""


def ratio4(numerator, multiplier, denominator) -> float:
    """The additions' per-unit PUA/OYT face: ``trunc4(PUA div x trunc7(base PUA / base div))``.

    CyberLife divides first, keeps 7 decimals, multiplies and truncates to 4 (178 placed
    values in the sample; e.g. 0.33 x 1.12 / 0.06 is stored 6.1599, not 6.16). When the
    additions earn the base rate itself the base per-unit value is used as is.
    """
    den = Decimal(str(denominator))
    if den == 0:
        return 0.0
    num = Decimal(str(numerator))
    mult = Decimal(str(multiplier))
    if num == den:
        return float(mult)
    per_cash = (mult / den).quantize(Decimal("0.0000001"), rounding=ROUND_DOWN)
    return float((num * per_cash).quantize(Decimal("0.0001"), rounding=ROUND_DOWN))


@dataclass(frozen=True)
class DividendRateSet:
    """The per-unit dividend values for one anniversary."""

    record: str
    duration: int
    scale_from: date
    base_div: float          # cash per unit of coverage
    base_pua: float          # PUA face per unit that the cash buys
    base_oyt: float          # OYT face per unit that the cash buys
    pua_div: float           # cash per $1,000 of paid-up additions
    pua_pua: float           # PUA face per $1,000 of additions (truncated to 4 decimals)
    pua_oyt: float


@dataclass(frozen=True)
class DividendScale:
    """One dated dividend scale of a coverage cell (one issue-date cohort, one record type).

    ``values`` hold the per-unit (cash, PUA, OYT) values by duration at the coverage's
    issue age; ``pua_values`` the PUA key's windows of (cash, OYT) per $1,000 of
    additions by attained age (participation 2)."""

    effective_from: date
    effective_to: Optional[date]
    values: Dict[int, Tuple[float, float, float]]
    participation: str
    pua_values: Tuple[Tuple[date, Optional[date], Dict[int, Tuple[float, float]]], ...] = ()

    def covers(self, on: date) -> bool:
        return self.effective_from <= on and (self.effective_to is None or on < self.effective_to)


@dataclass
class CoverageDividendRates:
    """Dividend scales of one coverage cell: record type -> dated scales."""

    plancode: str
    cell: str
    scales: Dict[str, List[DividendScale]]
    notes: List[str] = field(default_factory=list)

    def records(self) -> List[str]:
        return sorted(self.scales)

    def rates(self, record: str, anniversary: date, duration: int, issue_age: int) -> DividendRateSet:
        """Per-unit dividend values earned at ``anniversary`` for policy year ``duration``."""
        scales = self.scales.get(record)
        if not scales:
            raise ParWLRateError(
                f"{self.plancode} has no '{record}' dividend scale in schema rates ({self.cell}).")
        scale = next((s for s in scales if s.covers(anniversary)), None)
        if scale is None:
            first = min(s.effective_from for s in scales)
            if anniversary < first:
                raise ParWLRateError(
                    f"{self.plancode} '{record}' dividends start {first:%m/%d/%Y}; none for {anniversary:%m/%d/%Y}.")
            scale = max(scales, key=lambda s: s.effective_from)
        values = scale.values.get(duration)
        if values is None:
            raise ParWLRateError(
                f"{self.plancode} '{record}' scale from {scale.effective_from:%m/%d/%Y} has no dividend "
                f"for issue age {issue_age}, duration {duration}.")
        base_div, base_pua, base_oyt = values
        pua_div = 0.0
        if scale.participation == "1":
            pua_div = base_div
        elif scale.participation == "2":
            window = next((w for w in scale.pua_values
                           if w[0] <= anniversary and (w[1] is None or anniversary < w[1])), None)
            if window is None and scale.pua_values:
                window = max(scale.pua_values, key=lambda w: w[0])
            if window is None:
                raise ParWLRateError(f"{self.plancode} '{record}' PUA dividend key has no scale.")
            attained = issue_age + duration
            pua = window[2].get(attained)
            if pua is None:
                raise ParWLRateError(
                    f"{self.plancode} '{record}' PUA dividend key has no rate at attained age {attained}.")
            pua_div, _pua_key_oyt = pua
        pua_pua = ratio4(pua_div, base_pua, base_div)
        pua_oyt = ratio4(pua_div, base_oyt, base_div)
        return DividendRateSet(record, duration, scale.effective_from, base_div, base_pua, base_oyt,
                               pua_div, pua_pua, pua_oyt)


@dataclass
class CoverageRates:
    """Rates of one coverage phase."""

    phase: int
    plancode: str
    plan_company: str
    plan_note: str
    cash_values: Tuple[float, ...] = ()          # per unit, index = duration (end of year)
    premium_per_unit: Optional[float] = None     # schema PREM (cross-check)
    dividends: Optional[CoverageDividendRates] = None
    pui: Dict[int, float] = field(default_factory=dict)   # attained age -> per $1,000
    notes: List[str] = field(default_factory=list)

    def cash_value_per_unit(self, duration: int) -> float:
        if not self.cash_values:
            raise ParWLRateError(f"{self.plancode} has no CV (tabular cash value) rates in schema rates.")
        if duration < 0:
            return 0.0
        if duration >= len(self.cash_values):
            return float(self.cash_values[-1])
        return float(self.cash_values[duration])


@dataclass
class ParWLRates:
    """Everything the par WL engine reads from schema ``rates`` for one policy."""

    coverages: Dict[int, CoverageRates]
    loan_rate: Optional[float] = None
    mode_factors: Tuple[ModeFactors, ...] = ()
    notes: List[str] = field(default_factory=list)

    def coverage(self, phase: int) -> CoverageRates:
        try:
            return self.coverages[phase]
        except KeyError:
            raise ParWLRateError(f"No rates were loaded for coverage phase {phase}.") from None

    def mode_factor(self, mode: str) -> Optional[ModeFactors]:
        rows = [m for m in self.mode_factors if m.mode == mode]
        return rows[0] if rows else None


# -- loading ----------------------------------------------------------------------

def _cash_values(reader: SchemaReader, plan: PlanDef, coverage: ParWLCoverage, key: RateKey,
                 notes: List[str]) -> Tuple[float, ...]:
    rows = [a for a in reader.cell_assignments(plan.company, plan.plancode) if a.benefit == ""]
    subseries = reader.plan_subseries(plan.company, plan.plancode)
    assignment, cell_notes = choose_cell(rows, "CV", key, subseries)
    if assignment is None:
        if cell_notes:
            notes.append(f"CV: {'; '.join(cell_notes)}")
        return ()
    if cell_notes:
        notes.append(f"CV: {'; '.join(cell_notes)}")
    grain, values = window_values(reader, assignment, "G", coverage.issue_date, coverage.issue_age)
    if grain != "IA_DUR" or not values:
        notes.append(f"CV: no issue-age {coverage.issue_age} values")
        return ()
    last = max(d for (_age, d) in values)
    return tuple(float(values.get((coverage.issue_age, d), 0) or 0) for d in range(last + 1))


def _premium(reader: SchemaReader, plan: PlanDef, coverage: ParWLCoverage, key: RateKey,
             notes: List[str]) -> Optional[float]:
    rows = [a for a in reader.cell_assignments(plan.company, plan.plancode) if a.benefit == ""]
    assignment, cell_notes = choose_cell(rows, "PREM", key)
    if assignment is None:
        return None
    if cell_notes:
        notes.append(f"PREM: {'; '.join(cell_notes)}")
    grain, values = window_values(reader, assignment, "G", coverage.issue_date, coverage.issue_age)
    value = values.get((coverage.issue_age, 0))
    return float(value) if value is not None else None


def _pui(reader: SchemaReader, plan: PlanDef, coverage: ParWLCoverage, key: RateKey,
         notes: List[str]) -> Dict[int, float]:
    rate_type = PUI_TABLE_TYPES.get(int(coverage.table_rating or 0))
    if rate_type is None:
        raise ParWLRateError(f"{plan.plancode}: table rating {coverage.table_rating} has no PUI table.")
    rows = [a for a in reader.cell_assignments(plan.company, plan.plancode) if a.benefit == ""]
    assignment, cell_notes = choose_cell(rows, rate_type, key)
    if assignment is None:
        return {}
    if cell_notes:
        notes.append(f"{rate_type}: {'; '.join(cell_notes)}")
    windows = [w for w in reader.schedule_windows(assignment.schedule_id) if w.scale == "G"]
    window = next((w for w in windows if w.covers(coverage.issue_date)), None) or (windows[0] if windows else None)
    if window is None:
        return {}
    values = reader.rate_values((window.rate_set_id,), None).get(window.rate_set_id, {})
    return {int(age): float(rate) for (age, _d), rate in values.items()}


def _cohort(schedules: Sequence[DivSchedule], issue_date: date) -> List[DivSchedule]:
    starts = [s.issue_date_from for s in schedules if s.issue_date_from <= issue_date]
    if not starts:
        return []
    start = max(starts)
    return sorted((s for s in schedules if s.issue_date_from == start), key=lambda s: s.effective_from)


def _choose_dividend_cell(assignments, coverage: ParWLCoverage, key: RateKey, rein: str):
    """The coverage's dividend assignment: by CyberLife's own key (class + base series +
    sub-series) when the plan carries it, else PolView's sex/class/band lookup.

    Rider 08129700 on 12213682 is keyed ``1297..`` by sub-series, not by the insured's sex,
    so the key decides (its male/female/unisex rows point at different scales)."""
    by_key = [a for a in assignments if coverage.dividend_key and a.div_key == coverage.dividend_key]
    if by_key:
        chosen, notes = choose_div(by_key, key, rein)
        if chosen is not None:
            return chosen, [f"dividend key {coverage.dividend_key}"]
        for rein_value in dict.fromkeys([rein, ""]):
            rows = [a for a in by_key if a.rein == rein_value and a.state in (key.state, "**")]
            if rows:
                chosen = min(rows, key=lambda a: (a.state != key.state, a.user_key))
                notes = [f"dividend key {coverage.dividend_key} (sex/class/band not on its rows)"]
                if rein_value != rein:
                    notes.append(f"REIN '{rein_value}' (policy {rein})")
                return chosen, notes
    return choose_div(assignments, key, rein)


def _dividends(reader: SchemaReader, plan: PlanDef, coverage: ParWLCoverage, key: RateKey, rein: str,
               notes: List[str]) -> Optional[CoverageDividendRates]:
    assignments = reader.div_assignments(plan.company, plan.plancode)
    if not assignments:
        return None
    chosen, choice_notes = _choose_dividend_cell(assignments, coverage, key, rein)
    if chosen is None:
        raise ParWLRateError(f"{plan.plancode}: {'; '.join(choice_notes)} in schema rates.")
    div_key, user_key = chosen.div_key, chosen.user_key
    if coverage.dividend_key and div_key != coverage.dividend_key:
        # The coverage's own key (e.g. a converted policy's 1E1526 on 8X1D1500 14456194)
        # is what CyberLife reads; use its schedules when schema rates holds them.
        own = [s for s in reader.div_schedules((coverage.dividend_key,)) if s.user_key == user_key] \
            or [s for s in reader.div_schedules((coverage.dividend_key,)) if s.user_key == ""]
        if own:
            choice_notes = [f"coverage dividend key {coverage.dividend_key} (the plan assigns {div_key})"]
            div_key, user_key = coverage.dividend_key, own[0].user_key
    cell = f"{div_key} '{user_key}'"
    if choice_notes:
        notes.append(f"DIV {cell}: {'; '.join(choice_notes)}")
    schedules = [s for s in reader.div_schedules((div_key,)) if s.user_key == user_key]
    by_record: Dict[str, List[DivSchedule]] = {}
    for schedule in schedules:
        by_record.setdefault(schedule.record_type, []).append(schedule)
    cohorts = {record: _cohort(rows, coverage.issue_date) for record, rows in by_record.items()}
    set_ids = tuple(sorted({s.rate_set_id for rows in cohorts.values() for s in rows}))
    values = reader.div_values(set_ids, (coverage.issue_age,)) if set_ids else {}
    pua_keys = sorted({(s.pua_key, s.pua_user_key or "") for rows in cohorts.values() for s in rows
                       if s.pua_participating == "2" and s.pua_key})
    pua_schedules: List[DivSchedule] = []
    if pua_keys:
        pua_schedules = [s for s in reader.div_schedules(tuple(sorted({k for k, _ in pua_keys})))
                         if (s.div_key, s.user_key) in set(pua_keys)]
    pua_set_ids = tuple(sorted({s.rate_set_id for s in pua_schedules}))
    pua_values = reader.div_values(pua_set_ids, (0,)) if pua_set_ids else {}
    scales: Dict[str, List[DividendScale]] = {}
    for record, cohort in cohorts.items():
        built = []
        for schedule in cohort:
            data = values.get(schedule.rate_set_id, {})
            by_duration = {
                int(d): (float(v.div_rate or 0), float(v.pua_rate or 0), float(v.oyt_rate or 0))
                for (age, d), v in data.items() if int(age) == coverage.issue_age
            }
            pua_windows: List[tuple] = []
            if schedule.pua_participating == "2":
                rows = [s for s in pua_schedules if s.div_key == schedule.pua_key
                        and s.user_key == (schedule.pua_user_key or "") and s.record_type == record]
                for pua_schedule in _cohort(rows, coverage.issue_date):
                    pdata = pua_values.get(pua_schedule.rate_set_id, {})
                    pua_windows.append((
                        pua_schedule.effective_from, pua_schedule.effective_to,
                        {int(d): (float(v.div_rate or 0), float(v.oyt_rate or 0))
                         for (age, d), v in pdata.items() if int(age) == 0},
                    ))
            built.append(DividendScale(schedule.effective_from, schedule.effective_to, by_duration,
                                       str(schedule.pua_participating or "0"), tuple(pua_windows)))
        if built:
            scales[record] = built
    return CoverageDividendRates(plan.plancode, cell, scales, notes=list(choice_notes))


def _plan_rate(reader: SchemaReader, plan: PlanDef, rate_type: str, state: str) -> Optional[float]:
    rows = [a for a in reader.plan_assignments(plan.company, plan.plancode)
            if a.rate_type == rate_type and a.state in (state, "**")]
    if not rows:
        return None
    row = sorted(rows, key=lambda a: a.state != state)[0]
    values = reader.rate_values((row.rate_set_id,), None).get(row.rate_set_id, {})
    value = values.get((0, 0))
    return float(value) if value is not None else None


def load_parwl_rates(policy: ParWLPolicy, repo=None) -> ParWLRates:
    """Load every coverage's rates for ``policy`` from schema ``rates``."""
    notes: List[str] = []
    coverages: Dict[int, CoverageRates] = {}
    with open_schema_reader(repo) as reader:
        base_plan: Optional[PlanDef] = None
        for coverage in policy.coverages:
            if coverage.role == ROLE_TERM_RIDER:
                # Term riders bill their stored premium and pay their face to expiry; no rates are read.
                coverages[coverage.phase] = CoverageRates(coverage.phase, coverage.plancode, "", "")
                continue
            plan, plan_note = resolve_rate_plan(reader, coverage.plancode, policy.company_code, ParWLRateError)
            if plan.product_family not in PAR_WL_FAMILIES:
                raise ParWLRateError(
                    f"{coverage.plancode} is {plan.product_family or 'unclassified'} in schema rates PLAN_DEF, "
                    "not a participating whole life plan.")
            if coverage.phase == policy.base.phase:
                base_plan = plan
            cov_notes: List[str] = [f"plan row company {plan.company}: {plan_note}"] if plan_note else []
            band = coverage_band(reader, plan, coverage.band_code, coverage.issue_date, coverage.face_amount)
            key = RateKey(coverage.rate_sex, coverage.rate_class, band, policy.issue_state, coverage.subseries)
            rates = CoverageRates(coverage.phase, coverage.plancode, plan.company, plan_note, notes=cov_notes)
            if coverage.role == ROLE_PUA_RIDER:
                rates.pui = _pui(reader, plan, coverage, key, cov_notes)
            else:
                rates.cash_values = _cash_values(reader, plan, coverage, key, cov_notes)
                rates.premium_per_unit = _premium(reader, plan, coverage, key, cov_notes)
            rates.dividends = _dividends(reader, plan, coverage, key, policy.reinsurance_key, cov_notes)
            coverages[coverage.phase] = rates
        loan_rate = None
        mode_factors: Tuple[ModeFactors, ...] = ()
        if base_plan is not None:
            loan_rate = _plan_rate(reader, base_plan, "LOAN_REG_CHG", policy.issue_state)
            mode_factors = plan_mode_factors(reader, base_plan, policy.bill_form, policy.base.units, notes)
    return ParWLRates(coverages=coverages, loan_rate=loan_rate, mode_factors=mode_factors, notes=notes)
