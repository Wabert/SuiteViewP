"""Guaranteed-assumption projection — RERUN's LockValues mechanism.

When an illustration runs, the CURRENT side runs first. The applied premiums,
net withdrawals, loans, and GP exception premiums are then hard-copied
("locked") per month — RERUN's LockValues tab. The guaranteed side re-projects
with guaranteed COIs and the guaranteed interest rate using those locked cash
flows verbatim: it does NOT re-limit distributions with its own surrender
value, and it does NOT re-cap premiums with its own recalculated guideline /
TAMRA limits. This keeps a single column of premiums and distributions on the
illustration while showing both guaranteed and current values.
"""
from __future__ import annotations

import copy
from dataclasses import replace
from typing import List, Optional

from dateutil.relativedelta import relativedelta

from suiteview.illustration.core.bonus_rates import BonusConfig
from suiteview.illustration.core.rate_loader import load_rates
from suiteview.illustration.models.calc_state import MonthlyState
from suiteview.illustration.models.input_set import (
    DatedTransaction,
    IllustrationInputSet,
    IllustrationOptions,
    ScheduledTransaction,
    TransactionKind,
)
from suiteview.illustration.models.plancode_config import load_plancode
from suiteview.illustration.models.policy_data import IllustrationPolicyData

_EPS = 0.005


def lock_values(
    policy: IllustrationPolicyData,
    current_results: List[MonthlyState],
    base_future_inputs: Optional[IllustrationInputSet] = None,
) -> IllustrationInputSet:
    """Hard-copy the current run's applied cash flows (LockValues columns).

    Locked per month: AppliedTotalPremium (plus the GP exception / Monthly
    Deduction premium, injected as premium since the guaranteed side runs with
    the exception machinery off), AppliedNetWithdrawal, AppliedLoan, and loan
    repayments (including premium dollars diverted to the loan — locked as an
    explicit repayment so the destination of every dollar is preserved).

    A zero premium schedule anchors month 1 so the engine never falls back to
    billing the modal premium on months with no locked premium. Policy changes
    (face / DBO) carry over so the guaranteed side alters coverage identically.
    """
    dated: list[DatedTransaction] = []
    for state in current_results[1:]:
        month_date = policy.issue_date + relativedelta(months=state.duration - 1)
        premium = state.gross_premium + state.gp_exception_prem + state.md_premium
        if premium > _EPS:
            dated.append(DatedTransaction(
                kind=TransactionKind.PREMIUM, effective_date=month_date,
                amount=premium, subtype="locked"))
        withdrawal = state.applied_net_withdrawal
        if withdrawal > _EPS:
            dated.append(DatedTransaction(
                kind=TransactionKind.WITHDRAWAL, effective_date=month_date,
                amount=withdrawal, subtype="locked"))
        fixed_loan = state.applied_regular_loan + state.applied_preferred_loan
        if fixed_loan > _EPS:
            dated.append(DatedTransaction(
                kind=TransactionKind.LOAN, effective_date=month_date,
                amount=fixed_loan, subtype="locked"))
        if state.applied_variable_loan > _EPS:
            dated.append(DatedTransaction(
                kind=TransactionKind.LOAN, effective_date=month_date,
                amount=state.applied_variable_loan, subtype="variable"))
        repayment = state.applied_loan_repayment + state.loan_repay_from_prem
        if repayment > _EPS:
            dated.append(DatedTransaction(
                kind=TransactionKind.LOAN_REPAYMENT, effective_date=month_date,
                amount=repayment, subtype="locked"))

    return IllustrationInputSet(
        # Zero-amount monthly schedule: makes every month's premium explicit so
        # the modal-premium fallback never fires on the guaranteed side.
        scheduled_transactions=[ScheduledTransaction(
            kind=TransactionKind.PREMIUM, policy_year=1, amount=0.0, mode="M")],
        dated_transactions=dated,
        policy_changes=list(base_future_inputs.policy_changes) if base_future_inputs else [],
    )


def guaranteed_options(base: Optional[IllustrationOptions] = None) -> IllustrationOptions:
    """Run options for the guaranteed side: locked inputs pass through as-is."""
    if base is None:
        base = IllustrationOptions()
    return replace(
        base,
        conform_to_tefra=False,          # no guideline cap / force-out re-check
        conform_to_tamra=False,          # no 7-pay re-check
        allow_exception_prems=False,     # exception premium already locked in
        pay_monthly_deduction=False,     # MD premium already locked in
        apply_prem_to_loan=False,        # diverted dollars locked as repayments
        apply_excess_repayment_as_premium=False,
        levelizing_premium=False,
        restrict_loans_to_sv=False,      # do not re-limit locked distributions
        cap_premiums_at_acceptance=None,
        guaranteed_assumption=True,      # sAssumptionCode=3 — caps the IUL WAIR
                                         # at the declared rate (RERUN VK)
    )


def run_guaranteed_projection(
    policy: IllustrationPolicyData,
    current_results: List[MonthlyState],
    *,
    base_options: Optional[IllustrationOptions] = None,
    base_future_inputs: Optional[IllustrationInputSet] = None,
    engine=None,
) -> List[MonthlyState]:
    """Project the guaranteed side from a finished current-assumption run.

    Guaranteed assumptions: guaranteed maximum COI (rate scale 0), the
    guaranteed interest rate, no interest bonus. Cash flows come verbatim from
    ``lock_values``. Projects the same number of months as the current run,
    stopping on lapse (later report years render as zero).
    """
    if engine is None:
        from suiteview.illustration.core.calc_engine import IllustrationEngine
        engine = IllustrationEngine()

    months = max(len(current_results) - 1, 0)
    if months == 0:
        return []

    gpolicy = copy.deepcopy(policy)
    gpolicy.modal_premium = 0.0
    if (policy.guaranteed_interest_rate or 0.0) > 0.0:
        gpolicy.current_interest_rate = policy.guaranteed_interest_rate
    # IUL WAIR declared rate reverts to the plan guaranteed rate on the
    # guaranteed side (None → the engine's GINT fallback).
    gpolicy.iul_declared_rate = None

    config = load_plancode(policy.plancode)
    guaranteed_rates = load_rates(gpolicy, config, coi_scale=0)

    return engine.project(
        gpolicy,
        months=months,
        future_inputs=lock_values(policy, current_results, base_future_inputs),
        options=guaranteed_options(base_options),
        bonus_override=BonusConfig(),
        rates_override=guaranteed_rates,
        stop_on_lapse=True,
    )
