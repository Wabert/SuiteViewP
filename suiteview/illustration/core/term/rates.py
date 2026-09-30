"""Indeterminate premium term rates from UL_Rates schema ``rates`` (never the dbo rate tables).

Per coverage phase, the ``PREM`` cell (sex / class / band / state, PolView's lookup)
by policy year, on two scales:

* ``C`` - the current premium scale, from the schedule window in effect on the
  valuation date (a rerated plan's newest current rates);
* ``G`` - the guaranteed maximum scale, from the window in effect at issue.

B15TG100 (D0194819, male standard nicotine, issue age 62): 23.36 on both scales for
the ten level years, then 130.63 / 139.92 at duration 11 up to 843.06 at 33.
Supplemental benefits with premiums (premium waiver ``30``, ``3G``...) read the
benefit's own ``PREM`` cell the same way. Plan level: the base plancode's mode
factors (``RATE_MODEFACT``). A base plan that is not a TERM family plan or has no
``PREM`` raises ``TermRateError`` naming the item; nothing is guessed. Riders whose
plancode is not loaded keep their stored premium per unit (a note says so).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Dict, List, Optional, Sequence, Tuple

from suiteview.core.rates_schema import PlanDef
from suiteview.illustration.core.fixed_premium import (
    BILL_FORM_FAMILY,
    ModeFactors,
    coverage_band,
    plan_mode_factors,
    resolve_rate_plan,
    window_values,
)
from suiteview.illustration.core.schema_reader import SchemaReader, open_schema_reader
from suiteview.illustration.models.term import (
    ROLE_BASE,
    SCALE_CURRENT,
    SCALE_GUARANTEED,
    TermBenefit,
    TermCoverage,
    TermPolicy,
)
from suiteview.polview.models.schema_rates import RateKey, choose_cell, last_year, rate_at


class TermRateError(ValueError):
    """A rate the indeterminate premium term run needs is not in schema ``rates``."""


@dataclass(frozen=True)
class PremiumSchedule:
    """Annual premium rates per unit by policy year (index 0 unused) on both scales."""

    source: str
    current: Tuple[Optional[float], ...]
    guaranteed: Tuple[Optional[float], ...]

    def rate(self, scale: str, year: int) -> Optional[float]:
        values = self.current if scale == SCALE_CURRENT else self.guaranteed
        return values[year] if 0 < year < len(values) else None

    @property
    def last_year(self) -> int:
        return max(len(self.current), len(self.guaranteed)) - 1


@dataclass
class TermRates:
    """Everything the term engine reads from schema ``rates`` for one policy."""

    coverages: Dict[int, PremiumSchedule]
    benefits: Dict[Tuple[int, str], PremiumSchedule] = field(default_factory=dict)
    mode_factors: Tuple[ModeFactors, ...] = ()
    plan_facts: Dict[str, object] = field(default_factory=dict)
    notes: List[str] = field(default_factory=list)
    # Mode factor sets to try, as (source, factors), when the plan has none of its own.
    mode_factor_candidates: Tuple = ()

    def mode_factor(self, mode: str) -> Optional[ModeFactors]:
        rows = [m for m in self.mode_factors if m.mode == mode]
        return rows[0] if rows else None


def _schedule(reader: SchemaReader, assignment, issue_age: int, issue_date: date, valuation_date: date,
              source: str) -> Optional[PremiumSchedule]:
    by_scale = {}
    for scale, on in ((SCALE_CURRENT, valuation_date), (SCALE_GUARANTEED, issue_date)):
        grain, values = window_values(reader, assignment, scale, on, issue_age)
        if not values:
            by_scale[scale] = (None,)
            continue
        last = last_year(grain, values, issue_age)
        by_scale[scale] = (None,) + tuple(
            (float(v) if (v := rate_at(grain, values, issue_age, year)) is not None else None)
            for year in range(1, last + 1))
    if by_scale[SCALE_CURRENT] == (None,) and by_scale[SCALE_GUARANTEED] == (None,):
        return None
    return PremiumSchedule(source, by_scale[SCALE_CURRENT], by_scale[SCALE_GUARANTEED])


def _cell(rows: Sequence, key: RateKey, notes: List[str], label: str):
    assignment, cell_notes = choose_cell(rows, "PREM", key)
    if cell_notes:
        notes.append(f"{label} PREM: {'; '.join(cell_notes)}")
    return assignment


def _coverage_schedule(reader: SchemaReader, plan: PlanDef, coverage: TermCoverage, policy: TermPolicy,
                       notes: List[str]) -> Optional[PremiumSchedule]:
    band = coverage_band(reader, plan, coverage.band_code, coverage.issue_date, coverage.face_amount)
    key = RateKey(coverage.rate_sex, coverage.rate_class, band, policy.issue_state)
    rows = [a for a in reader.cell_assignments(plan.company, plan.plancode) if not a.benefit]
    assignment = _cell(rows, key, notes, coverage.plancode)
    if assignment is None:
        return None
    source = f"{plan.plancode} PREM {key.sex}/{key.rate_class}/{band}"
    return _schedule(reader, assignment, coverage.issue_age, coverage.issue_date, policy.valuation_date, source)


def _benefit_schedule(reader: SchemaReader, plan: PlanDef, benefit: TermBenefit, coverage: TermCoverage,
                      policy: TermPolicy, notes: List[str]) -> Optional[PremiumSchedule]:
    rows = [a for a in reader.cell_assignments(plan.company, plan.plancode) if a.benefit == benefit.code]
    if not rows:
        return None
    band = coverage_band(reader, plan, coverage.band_code, coverage.issue_date, coverage.face_amount)
    key = RateKey(coverage.rate_sex, coverage.rate_class, band, policy.issue_state)
    assignment = _cell(rows, key, notes, f"{plan.plancode} benefit {benefit.code}")
    if assignment is None:
        return None
    issue_age = benefit.issue_age if benefit.issue_age is not None else coverage.issue_age
    issue_date = benefit.issue_date or coverage.issue_date
    source = f"{plan.plancode} benefit {benefit.code} PREM"
    return _schedule(reader, assignment, issue_age, issue_date, policy.valuation_date, source)


def load_term_rates(policy: TermPolicy, repo=None) -> TermRates:
    """Load the premium schedules and mode factors for ``policy`` from schema ``rates``."""
    notes: List[str] = []
    coverages: Dict[int, PremiumSchedule] = {}
    benefits: Dict[Tuple[int, str], PremiumSchedule] = {}
    plans: Dict[int, PlanDef] = {}
    with open_schema_reader(repo) as reader:
        for coverage in policy.coverages:
            if coverage.role == ROLE_BASE:
                plan, plan_note = resolve_rate_plan(reader, coverage.plancode, policy.company_code, TermRateError)
                if not str(plan.product_family or "").startswith("TERM"):
                    raise TermRateError(
                        f"{coverage.plancode} is {plan.product_family or 'unclassified'} in schema rates PLAN_DEF, "
                        "not a term plan.")
            else:
                found = [p for p in reader.plan_defs(coverage.plancode)]
                if not found:
                    notes.append(f"Rider {coverage.plancode} is not loaded in schema rates; its stored premium "
                                 f"per unit {coverage.annual_premium_per_unit:,.2f} is used for every year.")
                    continue
                plan, plan_note = resolve_rate_plan(reader, coverage.plancode, policy.company_code, TermRateError)
            if plan_note:
                notes.append(f"{coverage.plancode}: plan row company {plan.company} ({plan_note})")
            plans[coverage.phase] = plan
            schedule = _coverage_schedule(reader, plan, coverage, policy, notes)
            if schedule is None:
                if coverage.role == ROLE_BASE:
                    raise TermRateError(f"{coverage.plancode} has no PREM rates for this insured in schema rates.")
                notes.append(f"Rider {coverage.plancode} has no PREM rates; its stored premium per unit is used.")
                continue
            coverages[coverage.phase] = schedule
        for benefit in policy.benefits:
            coverage = next((c for c in policy.coverages if c.phase == benefit.phase), policy.base)
            plan = plans.get(coverage.phase)
            if plan is None or not (benefit.annual_premium_per_unit or benefit.renews):
                continue
            schedule = _benefit_schedule(reader, plan, benefit, coverage, policy, notes)
            if schedule is not None:
                benefits[(benefit.phase, benefit.code)] = schedule
            elif benefit.annual_premium_per_unit:
                notes.append(f"Benefit {benefit.code} ({benefit.description}) has no PREM rates in schema rates; its "
                             f"stored premium per unit {benefit.annual_premium_per_unit:,.2f} is used for every year.")
        base_plan = plans[policy.base.phase]
        candidates: Tuple = ()
        if reader.modal_factors(base_plan.company, base_plan.plancode):
            mode_factors = plan_mode_factors(reader, base_plan, policy.bill_form, policy.base.units, notes)
        else:
            mode_factors, candidates = (), _shared_mode_factors(reader, base_plan, policy)
            if not candidates:
                notes.append(f"{base_plan.plancode} has no mode factors in schema rates (RATE_MODEFACT); the "
                             "billed premium is used as is.")
    return TermRates(coverages=coverages, benefits=benefits, mode_factors=mode_factors,
                     plan_facts=dict(base_plan.facts or ()), notes=notes, mode_factor_candidates=candidates)


def _shared_mode_factors(reader: SchemaReader, plan: PlanDef, policy: TermPolicy) -> Tuple:
    """Candidate mode factors for a plan with no ``PLAN_MODEFACT`` rows (``MODE_PREM_TABLE``
    0: CyberLife takes them from the plan description, which schema ``rates`` does not hold):
    each distinct set the loaded plans of the same plancode family (first four characters)
    use for the policy's bill form, the most common first, then for the other bill form
    (company 26 monthly direct SIGTERM bills at the PAC 0.0864: 000332291 (1,432 + 60) x
    0.0864 = 128.91), as ``(source, factors)``. The engine uses the first that reproduces
    the policy's billed premium - B15TI300 bills like mode table 352 (FF905195: (300 x 0.55
    + 300 x 0.39 + 60) x 0.0864 = 29.55) - and refuses when none does."""
    prefix = plan.plancode[:4]
    own = str(policy.bill_form or "").strip().upper() or "0"
    other_form = "0" if BILL_FORM_FAMILY.get(own) == "PAC" else "G"
    ranked = []
    for bill_form, label in ((own, ""), (other_form, f", {BILL_FORM_FAMILY[other_form]} factors")):
        sets = {}
        for candidate in reader.modal_factor_plancodes(plan.company, prefix):
            other = next((p for p in reader.plan_defs(candidate) if p.company == plan.company), None)
            if other is None:
                continue
            factors = plan_mode_factors(reader, other, bill_form, policy.base.units, [])
            if factors:
                sets.setdefault(factors, []).append(candidate)
        ranked += [(f"{plancodes[0]} (shared by {len(plancodes)} {prefix} plans{label})", factors)
                   for factors, plancodes in sorted(sets.items(), key=lambda item: -len(item[1]))]
    return tuple(ranked)
