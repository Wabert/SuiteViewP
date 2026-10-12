"""ISWL reduced paid-up projection: CyberLife's NSP roll-forward beside the endowment NSP.

**CyberLife basis.** The NSP per $1,000 at each anniversary: the three stored values at
``LOW_DUR_PER``, +1, +2, then one ``nsp_roll.roll_step`` per anniversary from the third
(S45 p.519: "anniversary processing uses the 3rd NSP value"), carried to 6 decimals and
used in cents (CyberLife's first two fields hold cents). The cash value on a
monthliversary is PolView's (``rates.guaranteed_cash_value``)::

    round_half_up(units x (NSP(d) x (12 - m) + NSP(d + 1) x m) / 12, 2)

with ``d`` the completed policy years and ``m`` the completed months since the
anniversary; the starting value ties to PolView's NSP cash value. The death benefit is
the level paid-up face (units x value per unit).

**Negative values.** B10 p.57: "when the value in the third values field becomes
negative, the net single premiums are no longer updated by anniversary processing". The
first negative rolled value (duration ``k``) is shown; from the anniversary at ``k - 1``
on the illustration holds the last non-negative NSP and marks the values frozen. What
CyberLife pays after it stops updating is not verified.

**Comparison.** The NSP of the paid-up benefit itself, an endowment at the coverage's
maturity age (``nsp_roll.endowment_nsp``, the same table, interest and claims factor - the
coverage's ``MTL_FUN_CD``), at the
attained age and interpolated monthly. CyberLife sets the RPU face and the first stored
values on this basis at conversion; the comparison shows where the stored roll-forward
departs from it.
"""
from __future__ import annotations

from datetime import date
from decimal import ROUND_HALF_UP, Decimal
from typing import Dict, List, Optional, Tuple

from dateutil.relativedelta import relativedelta

from suiteview.illustration.core.iswl_rpu.nsp_roll import endowment_nsp, half_up, roll_step
from suiteview.illustration.core.parwl.nsp import NSPError
from suiteview.illustration.models.iswl_rpu import (
    SOURCE_NEGATIVE,
    SOURCE_ROLLED,
    SOURCE_STORED,
    STORED_NSP_COLUMNS,
    ISWLRPUInputs,
    ISWLRPUMonth,
    ISWLRPUPolicy,
    ISWLRPUResult,
    ISWLRPUYear,
    NSPValue,
)

CENT = Decimal("0.01")
MATERIAL_DIFFERENCE = 0.05      # the bases "diverge materially" past 5% of the endowment NSP


class ISWLRPUError(ValueError):
    """The projection cannot be made (explains why)."""


def completed_parts(issue_date: date, when: date) -> Tuple[int, int]:
    """(completed policy years, completed months since the anniversary), PolView's way."""
    delta = relativedelta(when, issue_date)
    return delta.years, delta.months


def comparison_nsp(policy: ISWLRPUPolicy, age: int) -> Optional[float]:
    """The paid-up endowment's NSP per $1,000 at ``age`` (None if the table does not reach)."""
    try:
        return endowment_nsp(policy.nsp_table, policy.nsp_interest, age, policy.maturity_age,
                             policy.mortality_function_code)
    except NSPError:
        return None


def nsp_schedule(policy: ISWLRPUPolicy) -> List[NSPValue]:
    """CyberLife's NSP per $1,000 from ``LOW_DUR_PER`` to maturity, or to the first negative value."""
    low = policy.low_duration
    last = policy.maturity_duration
    values: List[NSPValue] = []

    def add(duration: int, carry: float, per_unit: float, source: str, column: str = "") -> None:
        age = policy.issue_age + duration
        values.append(NSPValue(duration, policy.issue_date + relativedelta(years=duration), age, carry, per_unit,
                               SOURCE_NEGATIVE if carry < 0 else source, column, comparison_nsp(policy, age)))

    s1, s2, s3 = policy.stored_nsp
    add(low, s1, s1, SOURCE_STORED, STORED_NSP_COLUMNS[0])
    add(low + 1, s2, s2, SOURCE_STORED, STORED_NSP_COLUMNS[1])
    add(low + 2, s3, half_up(s3), SOURCE_STORED, STORED_NSP_COLUMNS[2])
    carry, duration = s3, low + 2
    while carry >= 0 and duration < last:
        step = roll_step(carry, policy.nsp_table, policy.nsp_interest, policy.issue_age, duration,
                         policy.mortality_function_code)
        carry, duration = step.carried, duration + 1
        add(duration, carry, half_up(carry), SOURCE_ROLLED)
    return values


class ISWLRPUEngine:
    """Monthly projection from PolView's valuation date to maturity (or the illustrate-to age)."""

    def __init__(self, policy: ISWLRPUPolicy, inputs: Optional[ISWLRPUInputs] = None):
        self.policy = policy
        self.inputs = inputs or ISWLRPUInputs()
        self.schedule = nsp_schedule(policy)
        self._by_duration: Dict[int, NSPValue] = {v.duration: v for v in self.schedule}
        self.negative = next((v for v in self.schedule if v.source == SOURCE_NEGATIVE), None)
        if self.negative is not None and self.negative.duration - 1 < policy.low_duration:
            raise ISWLRPUError(f"The first stored NSP ({policy.stored_nsp[0]:,.2f}) is negative; there is no "
                               "value to illustrate from.")

    @property
    def freeze_duration(self) -> Optional[int]:
        """The anniversary from which the illustration holds the last non-negative NSP."""
        return self.negative.duration - 1 if self.negative is not None else None

    def nsp_at(self, duration: int) -> Tuple[float, bool]:
        """(NSP per $1,000 the cash value uses at ``duration``, frozen)."""
        freeze = self.freeze_duration
        if freeze is not None and duration > freeze:
            return self._by_duration[freeze].per_unit, True
        value = self._by_duration.get(duration)
        if value is None:
            raise ISWLRPUError(f"No NSP for duration {duration}: the stored values start at duration "
                               f"{self.policy.low_duration} (LOW_DUR_PER).")
        return value.per_unit, False

    def cash_value(self, duration: int, months: int) -> Tuple[float, float, float, float, bool]:
        """(cash value, interpolated NSP, BOY NSP, EOY NSP, frozen) after ``months`` of year ``duration + 1``."""
        boy, frozen_boy = self.nsp_at(duration)
        try:
            eoy, frozen_eoy = self.nsp_at(duration + 1)
        except ISWLRPUError:
            if months:
                raise
            eoy, frozen_eoy = boy, frozen_boy        # the maturity anniversary needs no next value
        weighted = Decimal(repr(boy)) * (12 - months) + Decimal(repr(eoy)) * months
        nsp = weighted / 12
        scale = Decimal(repr(self.policy.value_per_unit)) / 1000
        value = (Decimal(repr(self.policy.units)) * weighted / 12 * scale).quantize(CENT, rounding=ROUND_HALF_UP)
        frozen = frozen_boy or (months > 0 and frozen_eoy)
        return float(value), float(nsp), boy, eoy, frozen

    def comparison(self, duration: int, months: int) -> Tuple[Optional[float], Optional[float]]:
        """(endowment NSP per $1,000 interpolated monthly, its cash value)."""
        age = self.policy.issue_age + duration
        start, end = comparison_nsp(self.policy, age), comparison_nsp(self.policy, age + 1)
        if start is None or end is None:
            return None, None
        nsp = (start * (12 - months) + end * months) / 12.0
        return nsp, half_up(self.policy.units * nsp * self.policy.value_per_unit / 1000.0)

    def _end_date(self) -> date:
        policy = self.policy
        end_age = self.inputs.end_age
        if end_age is None:
            return policy.maturity_date
        start_age = policy.issue_age + completed_parts(policy.issue_date, policy.valuation_date)[0]
        if end_age <= start_age:
            raise ISWLRPUError(f"Illustrate to age must be after the attained age ({start_age}).")
        if end_age >= policy.maturity_age:
            return policy.maturity_date
        return policy.issue_date + relativedelta(years=end_age - policy.issue_age)

    def run(self) -> ISWLRPUResult:
        policy = self.policy
        if policy.run_block:
            raise ISWLRPUError(policy.run_block)
        start = policy.valuation_date
        if start >= policy.maturity_date:
            raise ISWLRPUError(f"The coverage matured on {policy.maturity_date:%m/%d/%Y}.")
        start_duration, _ = completed_parts(policy.issue_date, start)
        low = policy.low_duration
        if not low <= start_duration <= low + 1:
            raise ISWLRPUError(
                f"The stored NSPs cover durations {low}-{low + 2}, but the valuation date "
                f"{start:%m/%d/%Y} is in duration {start_duration}; PolView cannot value it either.")
        end = self._end_date()
        loan = policy.loan_balance
        months: List[ISWLRPUMonth] = []
        first = completed_parts(policy.issue_date, start)
        n = first[0] * 12 + first[1]
        while True:
            when = policy.issue_date + relativedelta(months=n)
            if when < start:
                n += 1
                continue
            if when > end:
                break
            duration, month = completed_parts(policy.issue_date, when)
            value, nsp, boy, eoy, frozen = self.cash_value(duration, month)
            comp_nsp, comp_cv = self.comparison(duration, month)
            notes = []
            if when == policy.maturity_date:
                notes.append("Coverage maturity; the maturity benefit is not illustrated")
            months.append(ISWLRPUMonth(
                index=len(months), when=when, policy_year=duration + 1, month_of_year=month, duration=duration,
                attained_age=policy.issue_age + duration, boy_nsp=boy, eoy_nsp=eoy, nsp=nsp,
                cash_value=max(value - loan, 0.0), comparison_nsp=comp_nsp,
                comparison_cash_value=None if comp_cv is None else max(comp_cv - loan, 0.0),
                death_benefit=max(policy.face_amount - loan, 0.0), loan=loan, frozen=frozen,
                notes="; ".join(notes)))
            n += 1
        years = self._years(months)
        result = ISWLRPUResult(policy, self.inputs, list(self.schedule), months, years, negative=self.negative)
        self._findings(result)
        return result

    def _years(self, months: List[ISWLRPUMonth]) -> List[ISWLRPUYear]:
        years = []
        for month in months[1:]:
            if month.month_of_year != 0:
                continue
            notes = [month.notes] if month.notes else []
            if month.frozen:
                notes.append("held at the last non-negative NSP (unverified)")
            years.append(ISWLRPUYear(
                policy_year=month.duration, end_date=month.when, age=month.attained_age, nsp=month.nsp,
                cash_value=month.cash_value, comparison_nsp=month.comparison_nsp,
                comparison_cash_value=month.comparison_cash_value, death_benefit=month.death_benefit,
                loan=month.loan, frozen=month.frozen, notes="; ".join(notes)))
        return years

    def _findings(self, result: ISWLRPUResult) -> None:
        policy, months = result.policy, result.months
        start_duration = months[0].duration if months else policy.low_duration
        ahead = [v for v in result.schedule if v.duration >= start_duration and v.source != SOURCE_NEGATIVE]
        if ahead:
            result.peak = max(ahead, key=lambda v: v.per_unit)
        if months and policy.polview_cash_value is not None:
            difference = round(months[0].cash_value + policy.loan_balance - policy.polview_cash_value, 2)
            if abs(difference) >= 0.005:
                result.warnings.append(
                    f"The starting cash value {months[0].cash_value:,.2f} differs from PolView's NSP cash value "
                    f"{policy.polview_cash_value:,.2f} by {difference:,.2f}.")
            else:
                result.notes.append(f"The starting cash value {months[0].cash_value:,.2f} on "
                                    f"{months[0].when:%m/%d/%Y} ties to PolView's NSP cash value.")
        elif months:
            result.warnings.append(f"PolView has no NSP cash value to tie to: {policy.polview_reason or 'none'}.")
        if result.peak is not None and result.peak.duration > start_duration:
            result.notes.append(
                f"The CyberLife-basis NSP peaks at {result.peak.per_unit:,.2f} per $1,000 at age {result.peak.age} "
                f"({result.peak.anniversary:%m/%d/%Y}) and declines after; the endowment NSP keeps rising to "
                f"1,000 at maturity.")
        for year in result.years:
            if year.comparison_nsp and abs(year.nsp - year.comparison_nsp) > MATERIAL_DIFFERENCE * year.comparison_nsp:
                result.divergence_from = year.policy_year
                result.warnings.append(
                    f"From year {year.policy_year} (age {year.age}, {year.end_date:%m/%d/%Y}) the CyberLife-basis "
                    f"cash value differs from the endowment NSP value by more than "
                    f"{MATERIAL_DIFFERENCE:.0%} ({year.cash_value:,.2f} against {year.comparison_cash_value:,.2f}).")
                break
        negative = result.negative
        if negative is not None:
            freeze = self._by_duration[self.freeze_duration]
            result.freeze_from = freeze.anniversary
            shown = negative.anniversary <= (months[-1].when if months else negative.anniversary)
            result.warnings.append(
                f"CyberLife's roll-forward NSP turns negative at duration {negative.duration} (age {negative.age}, "
                f"{negative.anniversary:%m/%d/%Y}): {negative.carry:,.6f} per $1,000. CyberLife then stops updating "
                "the NSPs (CyberDoc B10 p.57); what it pays as a cash value after that is not verified. From "
                f"{freeze.anniversary:%m/%d/%Y} the illustration holds {freeze.per_unit:,.2f} per $1,000 and marks "
                "the values frozen." + ("" if shown else " (after the last year illustrated)"))
        if any(m.notes.startswith("Coverage maturity") for m in months):
            result.notes.append(f"The coverage matures on {policy.maturity_date:%m/%d/%Y} (age {policy.maturity_age}); "
                                "what CyberLife pays at maturity on ISWL RPU is not verified and is not illustrated.")
        result.notes.extend(policy.notes)
