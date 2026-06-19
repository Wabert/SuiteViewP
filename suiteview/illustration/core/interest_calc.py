"""Interest credit — Stage 3 of the monthly pipeline.

Follows RERUN CalcEngine cols 548-585.
"""
from __future__ import annotations

import calendar
from dataclasses import dataclass
from datetime import date

from suiteview.illustration.core.bonus_rates import BonusConfig
from suiteview.illustration.core.rate_loader import IllustrationRates
from suiteview.illustration.models.plancode_config import PlancodeConfig
from suiteview.illustration.models.policy_data import IllustrationPolicyData


@dataclass
class InterestResult:
    """Intermediate output of credit_interest()."""

    days_in_month: float = 0.0
    actual_days_in_month: int = 0
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
) -> InterestResult:
    """Credit interest to account value.

    When loans exist, AV is split into free and loaned portions.
    The loaned portion earns a reduced loan credit rate; the free
    portion earns the full declared + bonus rate.

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

    # ── 3.3.2 Bonus interest ─────────────────────────────────
    bonus_rate = 0.0

    # Duration bonus — added after threshold year
    if bonus.bonus_dur_threshold > 0 and bonus.bonus_dur_rate > 0:
        if rate_year > bonus.bonus_dur_threshold:
            bonus_rate += bonus.bonus_dur_rate

    # AV bonus — when AV exceeds threshold
    if bonus.bonus_av_threshold > 0 and bonus.bonus_av_rate > 0:
        if av_after_deduction >= bonus.bonus_av_threshold:
            bonus_rate += bonus.bonus_av_rate

    effective_annual_rate = annual_rate + bonus_rate

    # ── 3.3.3 Monthly rate calculation ────────────────────────
    actual_days = _days_in_month(month_date)
    use_exact_days = config.interest_method == "ExactDays" if exact_days_interest is None else exact_days_interest
    display_days = float(actual_days) if use_exact_days else 365.0 / 12.0

    if use_exact_days:
        # Exact-days: credit interest on the ACTUAL calendar days in the month
        # (matches CyberLife / RERUN, and the shadow side, which already use
        # days/365). Previously this used a fixed 365/12 exponent and ignored the
        # real day count, drifting ~0.3/mo vs RERUN on 28/31-day months.
        monthly_rate = (1.0 + effective_annual_rate) ** (actual_days / 365.0) - 1.0
    else:
        # Monthly compounding
        monthly_rate = (1.0 + effective_annual_rate) ** (1.0 / 12.0) - 1.0

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

        if use_exact_days:
            reg_credit_monthly = (1.0 + reg_credit_annual) ** (actual_days / 365.0) - 1.0
            pref_credit_monthly = (1.0 + pref_credit_annual) ** (actual_days / 365.0) - 1.0
        else:
            reg_credit_monthly = (1.0 + reg_credit_annual) ** (1.0 / 12.0) - 1.0
            pref_credit_monthly = (1.0 + pref_credit_annual) ** (1.0 / 12.0) - 1.0

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
