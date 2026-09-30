"""Guaranteed-assumption projection — RERUN's LockValues mechanism.

When an illustration runs, the CURRENT side runs first. The applied premiums,
net withdrawals, loans, and GP exception premiums are then hard-copied
("locked") per month — RERUN's LockValues tab. The guaranteed side re-projects
with guaranteed COIs and the guaranteed interest rate using those cash flows as
its requested inputs. It does not re-limit distributions with its own surrender
value, but it does honor the same TEFRA and TAMRA settings as the current side:
premium limits and guideline force-outs are independently applied to the
guaranteed projection. This allows guaranteed values to satisfy the selected
definition-of-life-insurance tests and lapse sooner when appropriate.
"""
from __future__ import annotations

import copy
from dataclasses import replace
from typing import List, Optional

from dateutil.relativedelta import relativedelta

from suiteview.illustration.core.bonus_rates import load_bonus_config
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
from suiteview.illustration.models.index_strategies import (
    guaranteed_blended_rate,
    load_index_strategies,
)
from suiteview.illustration.models.policy_data import IllustrationPolicyData

_EPS = 0.005


def lock_values(
    policy: IllustrationPolicyData,
    current_results: List[MonthlyState],
    base_future_inputs: Optional[IllustrationInputSet] = None,
    *,
    iswl: bool = False,
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
    ``iswl`` locks the requested billed payments instead of the gross premium.
    """
    dated: list[DatedTransaction] = []
    # ISWL premiums are whole billed payments of the policy's billed premium (the
    # bill drops when a benefit ceases), so the requested payments are locked.
    for state in current_results[1:]:
        month_date = policy.issue_date + relativedelta(months=state.duration - 1)
        premium = (
            state.requested_premium if iswl and state.gross_premium > _EPS
            else state.gross_premium + state.gp_exception_prem + state.md_premium
        )
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
        # The applied total already includes premium dollars diverted to the loan.
        repayment = state.applied_loan_repayment
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
    """Run options preserving the selected regulatory conformance settings."""
    if base is None:
        base = IllustrationOptions()
    return replace(
        base,
        allow_exception_prems=False,     # exception premium already locked in
        pay_monthly_deduction=False,     # MD premium already locked in
        billable_to_md_windows=None,     # Billable-to-MD premiums locked in too
        apply_prem_to_loan=False,        # diverted dollars locked as repayments
        apply_excess_repayment_as_premium=False,
        levelizing_premium=False,
        restrict_loans_to_sv=False,      # do not re-limit locked distributions
        guaranteed_assumption=True,      # sAssumptionCode=3 — caps the IUL WAIR
                                         # at the declared rate (RERUN VK)
    )


def _guaranteed_crediting_rate(
    policy: IllustrationPolicyData,
    gint: float,
    base_options: Optional[IllustrationOptions],
) -> float:
    """The free-AV crediting rate for the guaranteed side.

    Declared-rate plans (and IUL runs using the WAIR method, where the
    guaranteed basis is enforced by the WAIR cap — RERUN VK) credit the plan
    guaranteed interest rate directly. An IUL plan illustrated with the
    **blended** method blends the guaranteed rate the same way the current side
    blends its crediting rate: index strategies guarantee only a 0% floor, so
    the guaranteed blend is the fixed-strategy allocation × GINT (RERUN
    INPUT!B53). Loan collateral is credited separately in ``core/interest_calc``
    at the guaranteed loan credit rate, so it keeps earning interest regardless
    of how far this blend floors.
    """
    plan = load_index_strategies(policy.plancode)
    wair = bool(getattr(base_options, "iul_wair_crediting", False)) if base_options else False
    if plan is not None and not wair and policy.premium_allocations:
        return guaranteed_blended_rate(policy.premium_allocations, gint)
    return gint


def run_guaranteed_projection(
    policy: IllustrationPolicyData,
    current_results: List[MonthlyState],
    *,
    base_options: Optional[IllustrationOptions] = None,
    base_future_inputs: Optional[IllustrationInputSet] = None,
    engine=None,
) -> List[MonthlyState]:
    """Project the guaranteed side from a finished current-assumption run.

    Guaranteed assumptions: guaranteed maximum COI (rate scale 0), guaranteed
    PoAV, guaranteed EPU (scale 0 — its expense charges continue to maturity,
    unlike the current schedule that drops after the level period), the
    guaranteed interest rate, and any explicitly configured guaranteed bonus.
    Missing ``BonusDurRateGuar`` / ``BonusAVRateGuar`` values default to zero.
    For an IUL plan
    illustrated with the blended method the guaranteed interest rate is itself
    blended (fixed allocation × GINT; index strategies floor at 0%) — loan
    collateral still earns its guaranteed loan credit rate. Cash flows come
    verbatim from ``lock_values``. Guideline force-outs are recalculated on the
    guaranteed values rather than locked; acceptance capping stays off so the
    locked premium itself is never altered. Projects the same number of months
    as the current run, stopping on lapse (later report years render as zero).
    """
    if engine is None:
        from suiteview.illustration.core.calc_engine import IllustrationEngine
        engine = IllustrationEngine()

    months = max(len(current_results) - 1, 0)
    if months == 0:
        return []

    gpolicy = copy.deepcopy(policy)
    config = load_plancode(policy.plancode)
    if not config.is_iswl:
        # ISWL keeps its billed premium: locked premiums are counted in billed payments.
        gpolicy.modal_premium = 0.0
    gint = policy.guaranteed_interest_rate or 0.0
    if gint > 0.0:
        gpolicy.current_interest_rate = _guaranteed_crediting_rate(
            policy, gint, base_options)
    # IUL WAIR declared rate reverts to the plan guaranteed rate on the
    # guaranteed side (None → the engine's GINT fallback).
    gpolicy.iul_declared_rate = None

    guaranteed_rates = load_rates(
        gpolicy,
        config,
        coi_scale=0,
        expense_scale=0,
    )
    valuation_date = (
        policy.illustration_date
        if policy.run_from_issue and policy.illustration_date
        else policy.valuation_date or policy.issue_date
    )
    guaranteed_bonus = load_bonus_config(
        policy.plancode, valuation_date).guaranteed()

    return engine.project(
        gpolicy,
        months=months,
        future_inputs=lock_values(policy, current_results, base_future_inputs, iswl=config.is_iswl),
        options=guaranteed_options(base_options),
        bonus_override=guaranteed_bonus,
        rates_override=guaranteed_rates,
        stop_on_lapse=True,
    )
