"""Receipt-date premium posting between ordinary illustration deductions.

The existing engine owns all monthliversary processing. This helper splits its
compounding factor at the actual receipt date, applies the shared premium
allowance/load routines, then resumes the unmodified monthly pipeline. It never
changes opening values or applies a later receipt to an earlier deduction.
"""
from __future__ import annotations

import copy
from dataclasses import dataclass
from datetime import date

from suiteview.illustration.api import project_policy
from suiteview.illustration.core.calc_engine import (
    IllustrationEngine, _premium_allowances, _tamra_month_of_year, _tamra_year,
)
from suiteview.illustration.core.interest_calc import credit_interest
from suiteview.illustration.core.input_compiler import CompiledMonthInputs
from suiteview.illustration.core.premium_handler import apply_premium
from suiteview.illustration.core.shadow_calc import calculate_shadow
from suiteview.illustration.models.input_set import IllustrationInputSet


@dataclass(frozen=True)
class ReceiptAmounts:
    date: date
    gross: float
    loads: float
    shadow_loads: float


def _partial_interest(av, fraction, policy, config, rates, bonus, state):
    whole = credit_interest(
        av, policy, config, rates, bonus, state.policy_year, state.attained_age,
        state.date, state.rg_loan_princ + state.rg_loan_accrued,
        state.pf_loan_princ + state.pf_loan_accrued,
    )
    def portion(interest, factor):
        return interest * (((1 + factor) ** fraction - 1) / factor) if factor else 0.0
    return sum((
        portion(whole.unimpaired_int, whole.monthly_interest_rate),
        portion(whole.reg_impaired_int,
                (1 + whole.reg_loan_credit_rate) ** (whole.days_in_month / 365) - 1),
        portion(whole.pref_impaired_int,
                (1 + whole.pref_loan_credit_rate) ** (whole.days_in_month / 365) - 1),
    ))


def project_receipt(
    policy, config, rates, bonus, options, receipt_date: date, pay_to: date,
    next_date: date, prior_months: int, premium: float,
):
    """Return monthly states plus separately dated receipt cash flows.

    ``prior_months`` stops at the latest issue-anchored monthliversary <= receipt.
    The pay-to row's period interest includes both subintervals, but its opening
    value and deduction remain untouched. Receipt amounts are not represented
    as a backdated monthliversary premium.
    """
    engine = IllustrationEngine()
    p = copy.deepcopy(policy)
    p.modal_premium = p.annual_premium = 0.0
    states = project_policy(
        p, months=prior_months, inputs=IllustrationInputSet(),
        options=options, rates=rates, config=config, bonus_override=bonus,
        stop_on_lapse=False, engine=engine,
    ).states
    if not states or states[-1].date != pay_to:
        raise ValueError("Receipt projection did not reach its pay-to monthliversary.")
    state = states[-1]
    fraction = (receipt_date - pay_to).days / (next_date - pay_to).days
    before_interest = _partial_interest(
        state.av_after_deduction, fraction, p, config, rates, bonus, state)
    receipt_av = state.av_after_deduction + before_interest
    tamra_year = _tamra_year(p, receipt_date)
    allowances = _premium_allowances(
        options, p, guideline_limit=state.guideline_limit,
        premiums_to_date=state.premiums_to_date_after_exception,
        withdrawals_before_forceout=state.withdrawals_to_date, force_out=0.0,
        amount_in_7pay=state.accumulated_7pay, tamra_year=tamra_year,
        tamra_month_of_year=_tamra_month_of_year(p, receipt_date),
        policy_month=state.policy_month, tamra_reset=False,
        requested_scheduled=0.0, requested_lumpsum=premium,
        payment_count_policy_year=0, payment_count_tamra_year=0,
        has_loan_balance=p.has_loans, beginning_of_year=False,
        policy_anniversary=False, prior_scheduled_prem_cap=state.scheduled_prem_cap,
    )
    prem = apply_premium(
        receipt_av, p, config, rates, state.policy_year,
        state.premiums_ytd_after_exception, state.premiums_to_date_after_exception,
        state.cost_basis_after_exception,
        gross_premium_override=allowances.applied_total_premium,
    )
    after_interest = _partial_interest(
        prem.av_after_premium, 1 - fraction, p, config, rates, bonus, state)
    without_receipt_interest = _partial_interest(
        receipt_av, 1 - fraction, p, config, rates, bonus, state)
    incremental_interest = after_interest - without_receipt_interest
    state.interest_credited += incremental_interest
    state.av_end_of_month += prem.net_premium + incremental_interest
    state.premiums_ytd_after_exception = prem.premiums_ytd
    state.premiums_to_date_after_exception = prem.premiums_to_date
    state.cost_basis_after_exception = prem.cost_basis
    if tamra_year <= 7:
        state.accumulated_7pay += prem.gross_premium

    shadow_load = 0.0
    if p.has_shadow_account:
        shd = calculate_shadow(
            prev_shadow_eav=state.shadow_av, gross_premium=prem.gross_premium,
            premiums_ytd=prem.premiums_ytd, policy=p, config=config, rates=rates,
            rate_year=state.policy_year, attained_age=state.attained_age,
            days_in_month=0, policy_debt=0.0, projection_date=receipt_date,
            display_days_in_month=0,
        )
        shadow_load = shd.shadow_prem_load
        factor = state.shadow_eff_rate
        shadow_before = max(0.0, state.shadow_av * ((1 + factor) ** fraction - 1))
        shadow_before_receipt = state.shadow_av + shadow_before
        shadow_at_receipt = shadow_before_receipt + shd.shadow_net_prem
        shadow_after = max(0.0, shadow_at_receipt * ((1 + factor) ** (1 - fraction) - 1))
        shadow_without = max(0.0, shadow_before_receipt * ((1 + factor) ** (1 - fraction) - 1))
        increment = shadow_after - shadow_without
        state.shadow_interest += increment
        state.shadow_eav = round(state.shadow_eav + shd.shadow_net_prem + increment, 2)
    final = engine.process_month(
        state, p, config, rates, bonus, options=options,
        month_inputs=CompiledMonthInputs(scheduled_premium=0.0),
    )
    states.append(final)
    return states, ReceiptAmounts(receipt_date, prem.gross_premium, prem.total_premium_load, shadow_load)
