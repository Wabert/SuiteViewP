"""Indeterminate premium term projection: current and guaranteed premiums by due date.

Rules (reproduced from CyberLife's billed premiums and the illustration team's review of
D0194819, "Re: D0194819 - ART Policy Illustration", 8/27/2026):

* **Due dates** - a premium is due every ``billing_frequency`` months from the paid-to
  date until the coverage matures; the first ledger year holds only the premiums still
  due in it (D0194819: 4 x 202.00 = 808.00 in year 10).
* **Rates** - the current renewal period (before the coverage's ``NXT_CHG_DT``) bills the
  stored ``ANN_PRM_UNT_AMT`` on both scales: a period's premium is set, so the guaranteed
  premium in the level period is the current premium (808.00, not CyberLife's 2,396).
  The next period's current rate is the stored renewal rate (segment 67), later years
  the ``C`` schedule; the guaranteed scale uses the ``G`` schedule after the current
  period (and the current rates through ``IDT_PRM_GUA_PER`` months from issue).
* **Modal premium** - every element at the policy's own mode: coverage, benefit and
  extra ``units x round(rate x factor, 2)`` (``MULTIPLY_ORDER`` 2; order 1 rounds
  ``units x rate x factor`` once) plus ``round(fee x fee factor, 2)``. D0194819 year 11:
  100 x round(139.92 x 0.08333, 2) + 7.00 = 1,173.00 a month, 14,076 a year; CyberLife's
  14,052 annualized at the annual mode.
* **Substandard** - a table extra (``SST_XTR_PCT``) is the coverage rate times
  ``(percent - 1)`` per unit, re-rated with the coverage rate after the current period
  (stored ``SST_XTR_UNT_AMT`` within it: IP020873 4.00 x (2 - 1)); a flat extra keeps its
  stored amount per unit until its cease date.
* **Benefits** - premium per unit x rating factor on the benefit's units, its stored rate
  in the current period and its own ``PREM`` schedule after (level when it has none).
"""
from __future__ import annotations

import calendar
from dataclasses import dataclass
from datetime import date
from typing import List, Optional, Tuple

from dateutil.relativedelta import relativedelta

from suiteview.core.modal_premium import POLICY_FEE_ADD_MODES
from suiteview.illustration.core.fixed_premium import (
    FEE_IN_ANNUAL_PREMIUM,
    MODES_BY_FREQUENCY,
    ModeFactors,
    cents,
)
from suiteview.illustration.core.term.rates import PremiumSchedule, TermRates
from suiteview.illustration.models.term import (
    SCALE_CURRENT,
    SCALE_GUARANTEED,
    TermBenefit,
    TermCoverage,
    TermExtra,
    TermInputs,
    TermMonth,
    TermPolicy,
    TermPremiumPart,
    TermResult,
    TermYear,
)


class TermProjectionError(ValueError):
    """The projection cannot continue (a missing rate, an unsupported mode...)."""


def completed_months(start: date, end: date) -> int:
    months = (end.year - start.year) * 12 + end.month - start.month
    if end.day < start.day and end.day != calendar.monthrange(end.year, end.month)[1]:
        months -= 1
    return months


def add_months(start: date, months: int) -> date:
    return start + relativedelta(months=months)


def policy_year(issue_date: date, when: date) -> int:
    return completed_months(issue_date, when) // 12 + 1


@dataclass(frozen=True)
class RateChoice:
    rate: float
    source: str


class TermEngine:
    """Projects an indeterminate premium term policy's premiums on both scales."""

    def __init__(self, policy: TermPolicy, rates: TermRates, inputs: Optional[TermInputs] = None):
        self.policy = policy
        self.rates = rates
        self.inputs = inputs or TermInputs()
        self.notes: List[str] = list(policy.notes) + list(rates.notes)
        self.frequency = int(self.inputs.billing_frequency or policy.billing_frequency)
        self.mode = MODES_BY_FREQUENCY.get(self.frequency, "")
        if not self.mode:
            raise TermProjectionError(f"Billing every {self.frequency} months is not illustrated.")
        self.coverages = tuple(c for c in policy.coverages if c.phase not in set(self.inputs.drop_riders)
                               or c.phase == policy.base.phase)
        self.benefits = tuple(b for b in policy.benefits if b.code not in set(self.inputs.drop_benefits))
        self._record_rates_only = False
        self.blocking_error = ""        # set when the premiums cannot be calculated at all
        self.mode_factors_source = ""
        self.factors: Optional[ModeFactors] = rates.mode_factor(self.mode)
        if not rates.mode_factors and rates.mode_factor_candidates:
            self._choose_borrowed_mode_factors()
        elif self.factors is None:
            self.notes.append(f"No {self.mode} mode factors for bill form {policy.bill_form}: premiums are "
                              f"annual premiums x {self.frequency}/12.")
        self.premium_adjustment = 0.0 if self.blocking_error else self._premium_adjustment()

    # -- premium periods --------------------------------------------------------------

    @staticmethod
    def period_start_year(coverage: TermCoverage, year: int) -> int:
        """The policy year the premium period containing ``year`` starts in.

        CyberDoc D10 renewal fields: an initial period of ``INT_RNL_PER`` years (repeated
        until ``SBQ_RNL_STR_DUR``), then periods of ``SBQ_RNL_PER`` years. D0194819 (10 /
        10 / 1): years 1-10, then 11, 12, ...; B75TL500 (1-year level): every year."""
        level = coverage.initial_renewal_period
        start = coverage.renewal_start_duration or level
        every = coverage.renewal_period
        if level <= 0 and every <= 0:
            return 1
        if year <= start or every <= 0:
            if level <= 0:
                return 1 if year <= start else start + 1
            return ((year - 1) // level) * level + 1 if year <= max(start, level) else max(start, level) + 1
        return start + 1 + ((year - start - 1) // every) * every

    def record_year(self, coverage: TermCoverage) -> int:
        """The coverage's policy year at the last processed anniversary: its stored premium
        per unit is the rate of the period containing it (NLP00116, paid only to 10/2025,
        still stores the year-11 rate after the 08/14/2026 anniversary)."""
        return policy_year(coverage.issue_date, max(self.policy.last_anniversary, coverage.issue_date))

    def _period_index(self, coverage: TermCoverage, when: date) -> int:
        """0 in the record's current premium period, 1 in the next one, 2 after."""
        if self._record_rates_only:
            return 0
        year = policy_year(coverage.issue_date, when)
        current = self.period_start_year(coverage, self.record_year(coverage))
        start = self.period_start_year(coverage, year)
        if start <= current:
            return 0
        following = self.period_start_year(coverage, self._period_end_year(coverage, current) + 1)
        return 1 if start == following else 2

    def _period_end_year(self, coverage: TermCoverage, start: int) -> int:
        year = start
        while self.period_start_year(coverage, year + 1) == start and year < 200:
            year += 1
        return year

    def next_premium_change(self, coverage: TermCoverage) -> date:
        """The anniversary the next premium period starts on."""
        current = self.period_start_year(coverage, self.record_year(coverage))
        return add_months(coverage.issue_date, self._period_end_year(coverage, current) * 12)

    # -- rates ------------------------------------------------------------------------

    def coverage_rate(self, coverage: TermCoverage, scale: str, when: date) -> RateChoice:
        """The annual premium rate per unit ``coverage`` bills on ``when`` on ``scale``."""
        year = policy_year(coverage.issue_date, when)
        stored = coverage.annual_premium_per_unit
        period = self._period_index(coverage, when)
        if period == 0:
            return RateChoice(stored, "stored premium per unit (current period)")
        schedule: Optional[PremiumSchedule] = self.rates.coverages.get(coverage.phase)
        guaranteed_until = add_months(coverage.issue_date, coverage.guaranteed_period_months)
        effective_scale = SCALE_CURRENT if (scale == SCALE_GUARANTEED and when < guaranteed_until) else scale
        if effective_scale == SCALE_CURRENT and period == 1 and coverage.next_renewal_rate is not None:
            return RateChoice(coverage.next_renewal_rate, "renewal rate on the record (next period)")
        if schedule is None:
            return RateChoice(stored, "stored premium per unit (no schema rates)")
        rate = schedule.rate(effective_scale, year)
        if rate is None:
            raise TermProjectionError(
                f"{coverage.plancode} has no {effective_scale} premium rate for policy year {year} ({schedule.source}).")
        return RateChoice(rate, f"{schedule.source} scale {effective_scale} year {year}")

    def extra_rate(self, extra: TermExtra, coverage: TermCoverage, coverage_rate: float, when: date) -> float:
        if extra.percent is not None and extra.percent > 1.0:
            if self._period_index(coverage, when) == 0 and extra.per_unit is not None:
                return extra.per_unit
            return cents(coverage_rate * (extra.percent - 1.0))
        return extra.per_unit or 0.0

    def benefit_rate(self, benefit: TermBenefit, coverage: TermCoverage, scale: str, when: date) -> RateChoice:
        """A benefit's rate: its stored rate in the current period, and for good when it does
        not renew (``RNL_RT_IND`` 0: FF902782's ADB 0.77 is level to its cease date); a renewing
        benefit (the premium waiver, ``RNL_RT_IND`` 1) follows its own ``PREM`` schedule after."""
        stored = benefit.annual_premium_per_unit
        schedule = self.rates.benefits.get((benefit.phase, benefit.code))
        if not benefit.renews or self._period_index(coverage, when) == 0 or schedule is None:
            return RateChoice(stored, "stored benefit premium per unit")
        year = policy_year(benefit.issue_date or coverage.issue_date, when)
        rate = schedule.rate(scale, year)
        if rate is None and scale == SCALE_GUARANTEED and not any(schedule.guaranteed[1:]):
            rate = schedule.rate(SCALE_CURRENT, year)
            note = (f"Benefit {benefit.code} has only a current premium scale in schema rates; its current rates "
                    "are its guaranteed rates.")
            if note not in self.notes:
                self.notes.append(note)
        if rate is None:
            raise TermProjectionError(f"Benefit {benefit.code} has no {scale} premium rate for year {year}.")
        return RateChoice(rate, f"{schedule.source} scale {scale} year {year}")

    # -- modal premium ----------------------------------------------------------------

    def _modal(self, units: float, rate: float) -> float:
        """One element's modal premium. Order 1 modalizes the element's annual premium in cents
        (E0041873: round(500.019 x 1.84, 2) = 920.03)."""
        factors = self.factors
        factor = factors.prem_factor if factors is not None else self.frequency / 12.0
        if factors is not None and factors.multiply_order == "2":
            return cents(units * cents(rate * factor))
        return cents(cents(units * rate) * factor)

    def _fee_annual(self) -> float:
        factors = self.factors
        if factors is None or not factors.policy_fee_annual:
            return 0.0
        if self.mode not in POLICY_FEE_ADD_MODES.get(factors.fee_add, frozenset()):
            return 0.0
        return factors.policy_fee_annual

    def _fee(self) -> float:
        fee = self._fee_annual()
        return cents(fee * self.factors.fee_factor) if fee else 0.0

    @staticmethod
    def _active(start: Optional[date], end: Optional[date], when: date) -> bool:
        return (start is None or start <= when) and (end is None or when < end)

    def premium_parts(self, when: date) -> List[TermPremiumPart]:
        """Each element of the modal premium due on ``when`` on both scales.

        ``POLICY_FEE_RULE`` Z with ``MULTIPLY_ORDER`` 1 (B15TD300, B75TL300...) modalizes the
        annual total once, fee included: E0000485 (500 x 0.67 + 60) x 0.0864 = 34.13; the
        cent that single rounding moves is a ``rounding`` part."""
        parts: List[TermPremiumPart] = []
        annual = {SCALE_CURRENT: 0.0, SCALE_GUARANTEED: 0.0}
        for coverage in self.coverages:
            if not self._active(coverage.issue_date, coverage.maturity_date, when):
                continue
            current = self.coverage_rate(coverage, SCALE_CURRENT, when)
            guaranteed = self.coverage_rate(coverage, SCALE_GUARANTEED, when)
            label = f"{coverage.plancode} ({coverage.form_number or coverage.role.lower()})"
            parts.append(TermPremiumPart(label, "coverage", coverage.phase, current.rate,
                                         self._modal(coverage.units, current.rate),
                                         self._modal(coverage.units, guaranteed.rate)))
            annual[SCALE_CURRENT] += cents(coverage.units * current.rate)
            annual[SCALE_GUARANTEED] += cents(coverage.units * guaranteed.rate)
            for extra in coverage.extras:
                if not self._active(None, extra.cease_date, when):
                    continue
                cur = self.extra_rate(extra, coverage, current.rate, when)
                gua = self.extra_rate(extra, coverage, guaranteed.rate, when)
                kind = "table" if extra.percent else "flat"
                parts.append(TermPremiumPart(f"{coverage.plancode} {kind} extra {extra.table_code}".rstrip(), "extra",
                                             coverage.phase, cur, self._modal(coverage.units, cur),
                                             self._modal(coverage.units, gua)))
                annual[SCALE_CURRENT] += cents(coverage.units * cur)
                annual[SCALE_GUARANTEED] += cents(coverage.units * gua)
        for benefit in self.benefits:
            if not benefit.annual_premium_per_unit and not self.rates.benefits.get((benefit.phase, benefit.code)):
                continue
            if not self._active(benefit.issue_date, benefit.pay_up_date or benefit.cease_date, when):
                continue
            coverage = next((c for c in self.coverages if c.phase == benefit.phase), self.policy.base)
            current = self.benefit_rate(benefit, coverage, SCALE_CURRENT, when)
            guaranteed = self.benefit_rate(benefit, coverage, SCALE_GUARANTEED, when)
            parts.append(TermPremiumPart(
                f"benefit {benefit.code} {benefit.form_number}".rstrip(), "benefit", benefit.phase, current.rate,
                self._modal(benefit.units, current.rate * benefit.rate_factor),
                self._modal(benefit.units, guaranteed.rate * benefit.rate_factor)))
            annual[SCALE_CURRENT] += cents(benefit.units * current.rate * benefit.rate_factor)
            annual[SCALE_GUARANTEED] += cents(benefit.units * guaranteed.rate * benefit.rate_factor)
        if not parts:
            return parts
        fee = self._fee()
        if fee:
            parts.append(TermPremiumPart("policy fee", "fee", 0, 0.0, fee, fee))
        factors = self.factors
        if factors is not None and self._rounds_once(factors):
            fee_annual = self._fee_annual()
            once = {scale: cents(amount * factors.prem_factor + fee_annual * factors.fee_factor)
                    for scale, amount in annual.items()}
            current = cents(once[SCALE_CURRENT] - sum(p.current for p in parts))
            guaranteed = cents(once[SCALE_GUARANTEED] - sum(p.guaranteed for p in parts))
            if current or guaranteed:
                parts.append(TermPremiumPart("rounding (fee in annual premium)", "rounding", 0, 0.0,
                                             current, guaranteed))
        return parts

    @staticmethod
    def _rounds_once(factors: ModeFactors) -> bool:
        """``MULTIPLY_ORDER`` 1 modalizes the annual total once, fee included, when the fee is
        modalized at the premium factor (fee rule 3, B15TD300 E0000485: (500 x 0.67 + 60) x
        0.0864 = 34.13, not 28.94 + 5.18) or the fee rule adds it to the annual premium (Z)."""
        if factors.multiply_order == "2":
            return False
        return (factors.policy_fee_rule == FEE_IN_ANNUAL_PREMIUM
                or abs(factors.fee_factor - factors.prem_factor) < 1e-9)

    def modal_premium(self, when: date) -> Tuple[float, float]:
        parts = self.premium_parts(when)
        return cents(sum(p.current for p in parts)), cents(sum(p.guaranteed for p in parts))

    def record_premium_date(self) -> date:
        """The date the billed ``POL_PRM_AMT`` is due: the paid-to date (15044388, paid to its
        04/01/2027 anniversary, bills year 12's 0.37 renewal rate: 250 x 0.37 + 60 = 152.50)."""
        return self.policy.paid_to_date or self.policy.valuation_date

    def record_rate_parts(self, when: date) -> List[TermPremiumPart]:
        """The premium due on ``when`` with every element at its stored (record) rate.

        CyberLife bills a premium due at a renewal anniversary at the new rate once it has
        rerated the policy for that anniversary (15044388, E0243681), and at the stored rate
        until then (E0096685 paid to its 09/30/2026 renewal: (350 x 0.63 + 60) x 0.0864 =
        24.24, the 0.72 renewal rate not yet applied). The in-force check accepts either."""
        self._record_rates_only = True
        try:
            return self.premium_parts(when)
        finally:
            self._record_rates_only = False

    def billed_parts(self) -> Tuple[List[TermPremiumPart], str]:
        """The calculation that reproduces the billed premium: renewal rates at the paid-to
        date, else the stored rates (a renewal not yet billed)."""
        when = self.record_premium_date()
        parts = self.premium_parts(when)
        billed = cents(self.policy.modal_premium)
        if abs(cents(sum(p.current for p in parts)) - billed) >= 0.005:
            stored = self.record_rate_parts(when)
            if abs(cents(sum(p.current for p in stored)) - billed) < 0.005:
                return stored, "stored rates (the renewal is not billed yet)"
        return parts, "rates due at the paid-to date"

    def _premium_adjustment(self) -> float:
        """Billed premium less the calculated one (a forced premium), kept for its premium period."""
        policy = self.policy
        if self.frequency != policy.billing_frequency or not policy.premium_paying or not policy.modal_premium:
            return 0.0
        calculated = cents(sum(p.current for p in self.billed_parts()[0]))
        difference = cents(policy.modal_premium - calculated)
        if abs(difference) < 0.005:
            return 0.0
        self.notes.append(
            f"Billed premium {policy.modal_premium:,.2f} differs from the calculated {calculated:,.2f} by "
            f"{difference:,.2f}{' (forced premium)' if policy.forced_premium else ''}; the billed premium is kept "
            "for its premium period.")
        return difference

    def _billed_with(self, factors: Tuple[ModeFactors, ...]) -> float:
        """The billed premium (policy mode, paid-to date) calculated with ``factors``."""
        policy = self.policy
        saved = (self.factors, self.frequency, self.mode)
        self.frequency = policy.billing_frequency
        self.mode = MODES_BY_FREQUENCY.get(self.frequency, "")
        self.factors = next((f for f in factors if f.mode == self.mode), None)
        try:
            return cents(sum(p.current for p in self.billed_parts()[0]))
        finally:
            self.factors, self.frequency, self.mode = saved

    def _choose_borrowed_mode_factors(self) -> None:
        """Mode factors for a plan with none in schema rates (``rates._shared_mode_factors``):
        the first candidate set that reproduces the billed premium; a policy with nothing
        billed takes the most common set with a note. None reproducing is an error."""
        policy = self.policy
        candidates = self.rates.mode_factor_candidates
        billed = cents(policy.modal_premium) if policy.premium_paying else 0.0
        chosen = None
        if billed:
            chosen = next((c for c in candidates if abs(self._billed_with(c[1]) - billed) < 0.005), None)
            if chosen is None:
                tried = ", ".join(f"{source} {self._billed_with(factors):,.2f}" for source, factors in candidates)
                self.blocking_error = (
                    f"{policy.base.plancode} has no mode factors in schema rates (RATE_MODEFACT), and none of the "
                    f"{policy.base.plancode[:4]} plans' factors reproduce the billed premium {billed:,.2f} ({tried}); "
                    "the premiums cannot be illustrated.")
                return
            verified = f"reproduce the billed premium {billed:,.2f}"
        else:
            chosen = candidates[0]
            verified = "not verified against a billed premium"
        source, factors = chosen
        self.mode_factors_source = source
        self.factors = next((f for f in factors if f.mode == self.mode), None)
        self.notes.append(f"{policy.base.plancode} has no mode factors in schema rates; those of {source} "
                          f"({verified}) are used.")

    def _adjusts(self, when: date) -> bool:
        base = self.policy.base
        return (self.premium_adjustment != 0.0
                and self._period_index(base, when) == self._period_index(base, self.record_premium_date()))

    # -- projection -------------------------------------------------------------------

    def _end_date(self) -> date:
        base = self.policy.base
        end = base.maturity_date or add_months(base.issue_date, (100 - base.issue_age) * 12)
        if self.inputs.end_age is not None:
            end = min(end, add_months(base.issue_date, (int(self.inputs.end_age) - base.issue_age) * 12))
        if self.inputs.stop_at is not None:
            end = min(end, self.inputs.stop_at)
        return end

    def _first_due(self) -> date:
        """The first premium due on or after the valuation date. Premiums in arrears (paid to
        before the valuation date) are not illustrated; a note says so."""
        policy = self.policy
        due = policy.paid_to_date or policy.valuation_date
        if due < policy.valuation_date:
            self.notes.append(f"Premiums are paid only to {due:%m/%d/%Y}; the premiums in arrears are not "
                              "illustrated.")
            while due < policy.valuation_date:
                due = add_months(due, self.frequency)
        return due

    def _period(self, coverage: TermCoverage, year: int) -> str:
        if coverage.initial_renewal_period and year <= coverage.initial_renewal_period:
            return "level"
        if coverage.renewal_period == 1:
            return "ART"
        return "renewal"

    def project(self) -> List[TermMonth]:
        policy = self.policy
        base = policy.base
        end = self._end_date()
        start = policy.valuation_date
        next_due = self._first_due()
        paying = policy.premium_paying
        rows: List[TermMonth] = []
        index = 0
        when = start
        while when <= end:
            year = policy_year(base.issue_date, when)
            row = TermMonth(index=index, when=when, policy_year=year,
                            month_of_year=completed_months(base.issue_date, when) % 12,
                            attained_age=base.issue_age + year - 1, period=self._period(base, year))
            if paying and when >= next_due and when < end:
                row.premium_due = True
                row.parts = self.premium_parts(when)
                current = cents(sum(p.current for p in row.parts))
                guaranteed = cents(sum(p.guaranteed for p in row.parts))
                if self._adjusts(when):
                    current = cents(current + self.premium_adjustment)
                    if self._period_index(base, when) == 0:
                        guaranteed = cents(guaranteed + self.premium_adjustment)
                row.current_premium = current
                row.guaranteed_premium = guaranteed
                if policy.is_waiver:
                    row.notes = "premium waived"
                next_due = add_months(next_due, self.frequency)
            row.death_benefit = base.face_amount if when < (base.maturity_date or date.max) else 0.0
            riders = [c for c in self.coverages
                      if c.phase != base.phase and self._active(c.issue_date, c.maturity_date, when)]
            row.rider_death_benefit = cents(sum(c.face_amount for c in riders))
            rows.append(row)
            index += 1
            when = add_months(start, index)
        return rows

    def run(self) -> TermResult:
        if self.blocking_error:
            raise TermProjectionError(self.blocking_error)
        months = self.project()
        years = build_years(months, self.policy)
        return TermResult(self.policy, self.inputs, months, years, notes=list(dict.fromkeys(self.notes)))


def build_years(months: List[TermMonth], policy: TermPolicy) -> List[TermYear]:
    """Annual ledger: each policy year's premiums (due dates in the year) and the death benefit."""
    base = policy.base
    years: List[TermYear] = []
    by_year = {}
    for row in months:
        by_year.setdefault(row.policy_year, []).append(row)
    for year in sorted(by_year):
        rows = by_year[year]
        end_date = add_months(base.issue_date, year * 12)
        if base.maturity_date is not None and end_date > base.maturity_date:
            continue
        in_force = [r for r in rows if r.death_benefit > 0]
        years.append(TermYear(
            policy_year=year,
            end_date=end_date,
            age=base.issue_age + year,
            current_premium=cents(sum(r.current_premium for r in rows)),
            guaranteed_premium=cents(sum(r.guaranteed_premium for r in rows)),
            death_benefit=in_force[-1].death_benefit if in_force else 0.0,
            rider_death_benefit=in_force[-1].rider_death_benefit if in_force else 0.0,
            period=rows[0].period,
        ))
    return years


def project_term(policy: TermPolicy, rates: TermRates, inputs: Optional[TermInputs] = None) -> TermResult:
    return TermEngine(policy, rates, inputs).run()
