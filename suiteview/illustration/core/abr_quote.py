"""ABR Quote — the theoretical annual level premium behind an ABR quote.

An Accelerated Benefit Rider quote needs the annual level premium that would
carry the policy to maturity under the ABR interest rate — a THEORETICAL
funding figure, not an inforce illustration. The run therefore reshapes the
illustration deliberately:

* Illustrated rate — the ABR interest rate the user entered (it may exceed the
  current credited rate; the inforce-override path already carried it onto
  ``policy.current_interest_rate`` before this module runs).
* Conform to TEFRA/DEFRA and Conform to TAMRA are OFF — nothing may limit the
  annual premium. Guideline premiums are not used for an ABR quote.
* The lapse test is OFF (``IllustrationOptions.no_lapse``): the policy is
  never lapsed for failing the minimum-premium (safety net), surrender-value,
  or AV-less-loans tests, so the account value and surrender value may run
  negative until the first annual premium lands.
* Premium mode is ANNUAL — the solved premium pays on policy anniversaries
  only, starting at the next anniversary after the forecast date. No premium
  is collected between the forecast date and that first payment.
* A policy loan is retired up front: the account value is reduced by the
  current policy debt and every loan bucket is zeroed before projecting.
* An Option B policy switches to Option A on the first forecast month. The
  engine's DBO change keeps the death benefit LEVEL at the switch, so the new
  level death benefit equals the specified amount plus the account value at
  the change.
* The regular solve targets a $1,000 surrender value at maturity. When the
  policy has a shadow account, a second solve targets a $1,000 shadow account
  value at maturity. The lower annual premium is the official ABR premium.
"""
from __future__ import annotations

import copy
from dataclasses import dataclass, replace
from datetime import date
from typing import List, Optional

from dateutil.relativedelta import relativedelta

from suiteview.illustration.api import project_policy
from suiteview.illustration.core.calc_engine import IllustrationEngine
from suiteview.illustration.core.face_minimum import PLAN_MINIMUM_EXEMPT_KEY
from suiteview.illustration.core.solve_premium_to_target import solve_premium_to_target
from suiteview.illustration.models.calc_state import MonthlyState
from suiteview.illustration.models.input_set import (
    IllustrationInputSet,
    IllustrationOptions,
    PolicyChangeEvent,
    PolicyChangeKind,
    ScheduledTransaction,
    TransactionKind,
)
from suiteview.illustration.models.policy_data import IllustrationPolicyData

# The solve target: a $1,000 surrender value at maturity.
ABR_TARGET_SV = 1000.0

_LOAN_BUCKETS = (
    "regular_loan_principal", "regular_loan_accrued",
    "preferred_loan_principal", "preferred_loan_accrued",
    "variable_loan_principal", "variable_loan_accrued",
)


@dataclass
class AbrQuoteRun:
    premium: float                     # solved annual level premium
    regular_premium: float             # annual premium from the surrender-value solve
    shadow_premium: Optional[float]     # annual premium from the shadow-value solve
    premium_basis: str                 # "regular" or "shadow"
    start_policy_year: int             # schedule start (first payment = next anniversary)
    first_payment_date: Optional[date]
    achieved_sv: float                 # surrender value reached at maturity
    achieved_shadow: Optional[float]   # shadow account value reached at maturity
    illustrated_rate: float            # annual ABR rate the run credited
    loan_retired: float                # policy debt netted out of the AV up front (0 = loan-free)
    db_option_switched: bool           # True when an Option B policy was switched to A
    max_partial: Optional["AbrMaxPartialResult"]
    policy: IllustrationPolicyData     # the adjusted (loan-retired) policy the run projected
    results: List[MonthlyState]        # the displayed projection (to maturity)
    options: IllustrationOptions       # the reshaped options the run used
    future_inputs: IllustrationInputSet


@dataclass
class AbrMaxPartialResult:
    minimum_face_amount: float
    locked_death_benefit: float
    reduction_ratio: float
    proportional_account_value: float
    account_value_used: float
    monthly_deduction: float
    monthly_deduction_date: date
    band: int


def abr_quote_options(base: Optional[IllustrationOptions] = None) -> IllustrationOptions:
    """Reshape the run options for an ABR quote: no premium limits, no lapse
    test, and none of the per-month premium modes (MD / Billable-to-MD) that
    would fight the annual level solve.

    On an IUL, ``iul_wair_crediting`` and the development-only
    ``iul_segment_crediting`` are forced off so the engine credits the
    single declared rate (``current_interest_rate`` = the entered ABR rate);
    combined with the 100%-fixed-fund allocation the Inputs tab supplies, the
    IP/IR asset charge drops to zero and the account credits exactly the ABR
    rate.
    """
    base = base if base is not None else IllustrationOptions()
    return replace(
        base,
        conform_to_tefra=False,
        conform_to_tamra=False,
        no_lapse=True,
        allow_exception_prems=False,
        pay_monthly_deduction=False,
        monthly_deduction_windows=None,
        billable_to_md_windows=None,
        billable_to_md_no_latch_before=None,
        iul_wair_crediting=False,
        iul_segment_crediting=False,
    )


def run_abr_quote(
    policy: IllustrationPolicyData,
    *,
    minimum_face_amount: Optional[float] = None,
    base_options: Optional[IllustrationOptions] = None,
    engine: Optional[IllustrationEngine] = None,
) -> AbrQuoteRun:
    """Solve and project the ABR quote premium for ``policy``.

    Raises ``PremiumTargetError`` (from ``solve_premium_to_target``) when even
    an unbounded premium cannot reach the target — e.g. the policy matures
    before its next anniversary, so the annual schedule never pays.
    """
    # Loan retirement mutates — never touch the caller's policy.
    policy = copy.deepcopy(policy)
    engine = engine or IllustrationEngine()
    options = abr_quote_options(base_options)

    loan_retired = float(policy.total_loan_balance or 0.0)
    if loan_retired > 0.0:
        policy.account_value = float(policy.account_value or 0.0) - loan_retired
        for bucket in _LOAN_BUCKETS:
            setattr(policy, bucket, 0.0)

    # First forecast month (the engine's month 1) — where the Option B -> A
    # switch lands so the whole solve runs on a level death benefit.
    forecast_date = policy.issue_date + relativedelta(months=int(policy.duration))
    db_option_switched = str(policy.db_option or "").upper() == "B"
    policy_changes: list[PolicyChangeEvent] = []
    if db_option_switched:
        policy_changes.append(PolicyChangeEvent(
            kind=PolicyChangeKind.DB_OPTION,
            effective_date=forecast_date,
            value="A",
        ))

    # Annual schedule starting in the CURRENT policy year: the anniversary
    # month of the current year is already behind the forecast date, so the
    # first payment lands on the NEXT anniversary — the policy coasts
    # (possibly negative, with the lapse test off) until then. The active
    # schedule also suppresses the engine's modal-premium fallback billing.
    start_policy_year = int(policy.duration) // 12 + 1
    solve_inputs = IllustrationInputSet(policy_changes=list(policy_changes))
    regular_solved = solve_premium_to_target(
        policy,
        target="sv",
        amount=ABR_TARGET_SV,
        at_age=int(policy.maturity_age),
        mode="A",
        start_policy_year=start_policy_year,
        base_future_inputs=solve_inputs,
        base_options=options,
        engine=engine,
    )
    shadow_solved = None
    if policy.has_shadow_account:
        shadow_solved = solve_premium_to_target(
            policy,
            target="shadow",
            amount=ABR_TARGET_SV,
            at_age=int(policy.maturity_age),
            mode="A",
            start_policy_year=start_policy_year,
            base_future_inputs=solve_inputs,
            base_options=options,
            engine=engine,
        )

    premium_basis = "regular"
    premium = regular_solved.premium
    if shadow_solved is not None and shadow_solved.premium < premium:
        premium_basis = "shadow"
        premium = shadow_solved.premium

    future_inputs = IllustrationInputSet(
        scheduled_transactions=[ScheduledTransaction(
            kind=TransactionKind.PREMIUM,
            policy_year=start_policy_year,
            amount=premium,
            mode="A",
        )],
        policy_changes=list(policy_changes),
    )
    results = project_policy(
        policy,
        inputs=future_inputs,
        options=options,
        stop_on_lapse=False,
        engine=engine,
    ).states
    first_payment_date = next(
        (state.date for state in results[1:] if int(state.policy_month or 0) == 1),
        None,
    )
    achieved_sv = _maturity_value(results, policy, "ending_sv")
    achieved_shadow = (
        _maturity_value(results, policy, "shadow_eav")
        if policy.has_shadow_account else None
    )

    max_partial = None
    if minimum_face_amount is not None:
        max_partial = _calculate_max_partial_deduction(
            policy,
            minimum_face_amount=float(minimum_face_amount),
            options=options,
            engine=engine,
            forecast_date=forecast_date,
            locked_death_benefit=_locked_death_benefit(policy, results),
        )

    return AbrQuoteRun(
        premium=premium,
        regular_premium=regular_solved.premium,
        shadow_premium=shadow_solved.premium if shadow_solved is not None else None,
        premium_basis=premium_basis,
        start_policy_year=start_policy_year,
        first_payment_date=first_payment_date,
        achieved_sv=achieved_sv,
        achieved_shadow=achieved_shadow,
        illustrated_rate=float(policy.current_interest_rate or 0.0),
        loan_retired=loan_retired,
        db_option_switched=db_option_switched,
        max_partial=max_partial,
        policy=policy,
        results=results,
        options=options,
        future_inputs=future_inputs,
    )


def _maturity_value(
    states: List[MonthlyState],
    policy: IllustrationPolicyData,
    field: str,
) -> float:
    target_year = int(policy.maturity_age) - int(policy.issue_age or 0)
    for state in states:
        if state.policy_year == target_year and state.policy_month == 12:
            return float(getattr(state, field) or 0.0)
    return float(getattr(states[-1], field) or 0.0)


def _locked_death_benefit(
    policy: IllustrationPolicyData,
    states: List[MonthlyState],
) -> float:
    if str(policy.db_option or "").upper() != "B":
        return float(policy.total_face)
    if len(states) < 2:
        raise ValueError("Unable to determine the locked level death benefit.")
    locked = states[1].coverage_after_change.get("CurrentSA")
    if locked is None:
        raise ValueError("The first forecast month did not produce a locked death benefit.")
    return float(locked)


def _calculate_max_partial_deduction(
    policy: IllustrationPolicyData,
    *,
    minimum_face_amount: float,
    options: IllustrationOptions,
    engine: IllustrationEngine,
    forecast_date: date,
    locked_death_benefit: float,
) -> AbrMaxPartialResult:
    """Project next-month's deduction after a hypothetical max acceleration."""
    if minimum_face_amount <= 0.0:
        raise ValueError("Minimum Face Amount Allowed must be greater than $0.")

    adjusted = copy.deepcopy(policy)
    if str(adjusted.db_option or "").upper() == "B":
        locked_increase = locked_death_benefit - float(adjusted.total_face)
        base = adjusted.base_segment
        if base is None:
            raise ValueError("Cannot determine the level death benefit without a base coverage.")
        base.face_amount += locked_increase
        base.units += locked_increase / float(base.vpu or 1000.0)
        adjusted.face_amount = float(adjusted.total_face)
        adjusted.units = sum(float(segment.units or 0.0) for segment in adjusted.segments)
        adjusted.db_option = "A"

    if minimum_face_amount > locked_death_benefit:
        raise ValueError(
            "Minimum Face Amount Allowed cannot exceed the locked level death "
            f"benefit of ${locked_death_benefit:,.2f}."
        )

    reduction_ratio = minimum_face_amount / locked_death_benefit
    proportional_account_value = float(adjusted.account_value or 0.0) * reduction_ratio
    adjusted.account_value = proportional_account_value

    changes = [PolicyChangeEvent(
        kind=PolicyChangeKind.FACE_AMOUNT,
        effective_date=forecast_date,
        value=minimum_face_amount,
        metadata={
            "charge_surrender": False,
            "change_label": "ABR Max Partial Acceleration",
            PLAN_MINIMUM_EXEMPT_KEY: True,
        },
    )]
    zero_premium = ScheduledTransaction(
        kind=TransactionKind.PREMIUM,
        policy_year=int(adjusted.duration) // 12 + 1,
        amount=0.0,
        mode="A",
    )
    states = project_policy(
        adjusted,
        months=1,
        inputs=IllustrationInputSet(
            scheduled_transactions=[zero_premium],
            policy_changes=changes,
        ),
        options=options,
        stop_on_lapse=False,
        engine=engine,
    ).states
    if len(states) < 2 or states[1].date is None:
        raise ValueError("Unable to calculate the next monthly deduction.")
    next_state = states[1]

    return AbrMaxPartialResult(
        minimum_face_amount=minimum_face_amount,
        locked_death_benefit=locked_death_benefit,
        reduction_ratio=reduction_ratio,
        proportional_account_value=proportional_account_value,
        account_value_used=float(next_state.av_after_premium or 0.0),
        monthly_deduction=float(next_state.total_deduction or 0.0),
        monthly_deduction_date=next_state.date,
        band=int(next_state.coverage_after_change.get("CurrentBand", 0) or 0),
    )
