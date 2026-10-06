"""Interest credit — Stage 3 of the monthly pipeline.

Follows RERUN CalcEngine cols 548-585.
"""
from __future__ import annotations

import calendar
from dataclasses import dataclass
from datetime import date

from suiteview.illustration.constants import DAYS_PER_YEAR, MONTHS_PER_YEAR
from suiteview.illustration.core.bonus_rates import BonusConfig
from suiteview.illustration.core.rate_loader import IllustrationRates
from suiteview.illustration.models.plancode_config import PlancodeConfig
from suiteview.illustration.models.policy_data import INITIAL_GUARANTEE_YEARS, IllustrationPolicyData


@dataclass
class InterestResult:
    """Intermediate output of credit_interest()."""

    days_in_month: float = 0.0
    actual_days_in_month: int = 0
    # Day count for the loan accrual to the next monthliversary. In CyberLife
    # timing ``days_in_month`` is the prior span (E01); loans still accrue over
    # the forward span, which is this calendar month's day count.
    loan_accrual_days: float = 0.0
    # Fixed (regular/preferred) loan accrual days: actual days on the plancode-driven
    # path whatever the crediting method (CyberLife); ``loan_accrual_days`` stays the
    # variable-loan day count.
    fixed_loan_accrual_days: float = 0.0
    annual_interest_rate: float = 0.0
    bonus_interest_rate: float = 0.0
    effective_annual_rate: float = 0.0
    monthly_interest_rate: float = 0.0
    reg_loan_credit_rate: float = 0.0
    pref_loan_credit_rate: float = 0.0
    reg_impaired_int: float = 0.0    # Interest on AV backing regular loans
    pref_impaired_int: float = 0.0   # Interest on AV backing preferred loans
    unimpaired_int: float = 0.0      # Interest on AV not backing loans
    interest_credited: float = 0.0
    av_end_of_month: float = 0.0


def credit_interest(
    av_after_deduction: float,
    policy: IllustrationPolicyData,
    config: PlancodeConfig,
    rates: IllustrationRates,
    bonus: BonusConfig,
    rate_year: int,
    attained_age: int,
    month_date: date,
    reg_loan_balance: float = 0.0,
    pref_loan_balance: float = 0.0,
    exact_days_interest: bool | None = None,
    period_days: float | None = None,
    exact_days_override: int | None = None,
) -> InterestResult:
    """Credit interest to account value.

    When loans exist, AV is split into free and loaned portions.
    The loaned portion earns a reduced loan credit rate; the free
    portion earns the full declared + bonus rate.

    ``period_days`` credits a partial period of that many days at
    ``(1 + rate) ** (days / 365) - 1`` instead of a whole monthiversary span
    (interim roll-forwards between monthliversaries); it overrides the
    exact-days / monthly-compounding choice.
    ``exact_days_override`` changes only the whole-span day count used by
    ExactDays plans; monthly-compounding plans still use ``(1 + i) ** (1/12)``.

    Args:
        av_after_deduction: AV after monthly deduction.
        policy: Policy data (for current_interest_rate).
        config: Plancode configuration.
        rates: Pre-loaded rate arrays.
        bonus: Resolved bonus configuration from tRates_IntBonus.
        rate_year: Current policy year for bonus lookup.
        attained_age: Current attained age.
        month_date: Calendar date of this monthiversary.
        reg_loan_balance: Regular loan principal + accrued.
        pref_loan_balance: Preferred loan principal + accrued.

    Returns:
        InterestResult with all interest-stage outputs.
    """
    # ── 3.3.1 Base crediting rate ─────────────────────────────
    annual_rate = policy.current_interest_rate
    if policy.ultimate_interest_rate is not None and rate_year > INITIAL_GUARANTEE_YEARS:
        annual_rate = policy.ultimate_interest_rate

    # ── 3.3.2 Bonus interest ─────────────────────────────────
    bonus_rate = 0.0

    # Duration bonus — the latest tier started (a later tier replaces an earlier
    # one), capped at the tier the policy has earned; zero starts immediately.
    bonus_rate += bonus.duration_bonus(rate_year)

    # AV bonus — when AV exceeds threshold
    if bonus.bonus_av_threshold > 0 and bonus.bonus_av_rate > 0:
        if av_after_deduction >= bonus.bonus_av_threshold:
            bonus_rate += bonus.bonus_av_rate

    effective_annual_rate = annual_rate + bonus_rate

    # ── 3.3.3 Monthly rate calculation ────────────────────────
    actual_days = _days_in_month(month_date)
    exact_days = exact_days_override if exact_days_override is not None else actual_days
    use_exact_days = config.interest_method == "ExactDays" if exact_days_interest is None else exact_days_interest
    # CyberLife accrues fixed (regular/preferred) loan interest on actual days even where
    # the fund credits 1/12 of a year (DIFFCMPD 2: 1S135A00 S1376650, 1S133K29 S1338936
    # loan steps follow month length). An explicit what-if choice still drives both;
    # variable (IUL) loans keep the crediting day count (no CyberLife evidence).
    fixed_loan_exact_days = True if exact_days_interest is None else exact_days_interest
    display_days = float(exact_days) if use_exact_days else DAYS_PER_YEAR / MONTHS_PER_YEAR
    loan_accrual_days = float(actual_days) if use_exact_days else DAYS_PER_YEAR / MONTHS_PER_YEAR
    fixed_loan_accrual_days = (
        float(actual_days) if fixed_loan_exact_days else DAYS_PER_YEAR / MONTHS_PER_YEAR)
    if period_days is not None:
        display_days = float(period_days)
        loan_accrual_days = float(period_days)
        fixed_loan_accrual_days = float(period_days)

    def period_rate(annual: float) -> float:
        if period_days is not None:
            return (1.0 + annual) ** (period_days / DAYS_PER_YEAR) - 1.0
        if use_exact_days:
            # Exact-days: credit interest on the ACTUAL calendar days in the month
            # (matches CyberLife / RERUN, and the shadow side, which already use
            # days/365).
            return (1.0 + annual) ** (exact_days / DAYS_PER_YEAR) - 1.0
        return (1.0 + annual) ** (1.0 / MONTHS_PER_YEAR) - 1.0

    monthly_rate = period_rate(effective_annual_rate)

    # ── 3.3.4 Interest on AV (split free / loaned) ─────────
    total_loaned = reg_loan_balance + pref_loan_balance
    reg_credit_annual = config.loan_charge_rate_curr or config.loan_charge_rate_guar or policy.guaranteed_interest_rate
    pref_credit_annual = (
        config.pref_loan_charge_rate_curr
        or config.pref_loan_charge_rate_guar
        or policy.guaranteed_interest_rate
    )
    reg_impaired_int = 0.0
    pref_impaired_int = 0.0
    free_interest = 0.0

    if total_loaned > 0.0 and av_after_deduction > 0.0:
        loaned_av = min(total_loaned, av_after_deduction)
        free_av = av_after_deduction - loaned_av

        # Proportional split of loaned AV between reg and pref
        if total_loaned > 0:
            reg_loaned_av = loaned_av * (reg_loan_balance / total_loaned)
            pref_loaned_av = loaned_av * (pref_loan_balance / total_loaned)
        else:
            reg_loaned_av = 0.0
            pref_loaned_av = 0.0

        reg_credit_monthly = period_rate(reg_credit_annual)
        pref_credit_monthly = period_rate(pref_credit_annual)

        reg_impaired_int = reg_loaned_av * reg_credit_monthly
        pref_impaired_int = pref_loaned_av * pref_credit_monthly
        free_interest = free_av * monthly_rate
        interest = free_interest + reg_impaired_int + pref_impaired_int
    else:
        free_interest = av_after_deduction * monthly_rate
        interest = free_interest

    interest = max(interest, 0.0)
    free_interest = max(free_interest, 0.0)

    # ── 3.3.5 End-of-month AV ────────────────────────────────
    av_end = av_after_deduction + interest

    return InterestResult(
        days_in_month=display_days,
        actual_days_in_month=actual_days,
        loan_accrual_days=loan_accrual_days,
        fixed_loan_accrual_days=fixed_loan_accrual_days,
        annual_interest_rate=annual_rate,
        bonus_interest_rate=bonus_rate,
        effective_annual_rate=effective_annual_rate,
        monthly_interest_rate=monthly_rate,
        reg_loan_credit_rate=reg_credit_annual,
        pref_loan_credit_rate=pref_credit_annual,
        reg_impaired_int=reg_impaired_int,
        pref_impaired_int=pref_impaired_int,
        unimpaired_int=free_interest,
        interest_credited=interest,
        av_end_of_month=av_end,
    )


def _days_in_month(d: date) -> int:
    """ExactDays day count for the monthiversary span starting at ``d``.

    RERUN (CalcEngine UB = C13−C12 − LeapDayRemoval): the days from this
    month-date to the next, EXCLUDING Feb 29 — CyberLife works on a 365-day
    year, so the leap day never earns interest. For day-of-month ≤ 28 the span
    equals the calendar days of the month containing ``d``; the leap-day
    removal turns Feb 2028's 29 into 28.
    """
    days = calendar.monthrange(d.year, d.month)[1]
    if _leap_day_in_span(d):
        days -= 1
    return days


def _leap_day_in_span(d: date) -> bool:
    """True when Feb 29 falls inside (d, d + 1 month] (CalcEngine U)."""
    return calendar.isleap(d.year) and d.month == 2 and d.day < 29


def interest_days(start: date, end: date) -> int:
    """Interest-earning days in ``(start, end]`` on CyberLife's 365-day year.

    Feb 29 never earns interest, matching :func:`_days_in_month`.
    """
    if end <= start:
        return 0
    days = (end - start).days
    for year in range(start.year, end.year + 1):
        if calendar.isleap(year) and start < date(year, 2, 29) <= end:
            days -= 1
    return days
