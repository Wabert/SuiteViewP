"""Guideline Exception Adjustment solve.

Answers, for a UL/GPT policy and a target inforce date: *if* the policy will
need guideline exception premiums to reach that date, how much premium is
needed, and how much room the AccumGLP must gain to admit that premium.

The solve runs the policy on the new **INPUT to MD** premium type
(:mod:`suiteview.illustration.ui.inputs_dynamic`) with an input premium of 0 and
a Lumpsum-to-Next-Premium bridge on a **monthly** cadence, forecasting to the
target date with **TEFRA limit enforcement OFF**. The engine pays 0 until the
policy can no longer carry itself, bridges to the next (monthly) premium, then
hands off to the Monthly Deduction premium — so the projected premium outlay is
exactly the premium the policy needs to stay in force.

Room and adjustment:

* ``room = max(0, AccumGLP - PremiumsPaidToDate + AccumWDs)`` — the same
  "Prem Allowed by GPT" figure shown on the Targets & Accumulators tab, but with
  ``PremiumsPaidToDate`` brought current by adding premiums paid *since* the
  valuation date (mirroring the existing GLP-Exception solve).
* ``total_premium_needed`` — the gross premium actually paid into the policy
  (bridge lumpsum + monthly Monthly-Deduction / exception premiums), summed for
  every projected month **strictly before** the target date (the target date
  itself is excluded).
* ``adjustment_to_accum_glp = max(0, total_premium_needed - room)`` — the
  increase the AccumGLP needs to admit all of that premium under the guideline.

This is a single-target-date solve: it uses the policy's current AccumGLP and
does not chain intermediate anniversary adjustments.
"""
from __future__ import annotations

import copy
from dataclasses import dataclass
from datetime import date

from suiteview.illustration.core.calc_engine import IllustrationEngine
from suiteview.illustration.models.input_set import (
    DatedTransaction,
    IllustrationInputSet,
    IllustrationOptions,
    ScheduledTransaction,
    TransactionKind,
)
from suiteview.illustration.models.policy_data import IllustrationPolicyData

from .glp_exception import (
    PremiumAdjustmentSinceValuation,
    _months_between_exclusive,
    _policy_with_post_valuation_premiums,
    _premium_adjustment_since_valuation,
    check_forecast_availability,
)


@dataclass
class GuidelineExceptionAdjustmentResult:
    """Outcome of a Guideline Exception Adjustment solve."""

    current_valuation_date: date | None
    target_date: date
    months_to_target: int
    premiums_since_valuation_date: float
    total_premium_needed: float
    room_available: float
    accumulated_glp: float
    premiums_paid_to_date: float
    accumulated_withdrawals: float
    adjustment_to_accum_glp: float
    new_accum_glp: float
    message: str


def solve_guideline_exception_adjustment(
    policy,
    target_date: date,
) -> GuidelineExceptionAdjustmentResult:
    """Solve the AccumGLP adjustment needed to admit exception premiums.

    Args:
        policy: a :class:`PolicyInformation` (UL / GPT). Availability and data
            loading are gated through :func:`check_forecast_availability`.
        target_date: the inforce date the policy must reach.
    """
    availability = check_forecast_availability(policy)
    if not availability.available or availability.policy is None:
        raise ValueError(availability.message)

    ill_policy = availability.policy
    valuation_date = ill_policy.valuation_date
    if valuation_date is None:
        raise ValueError("Current valuation date was not found")
    if target_date <= valuation_date:
        raise ValueError("Target inforce date must be after the current valuation date")

    # Premiums paid SINCE the valuation date roll the projection's starting state
    # forward (account value, premiums paid, cost basis) — mirrors the existing
    # GLP-Exception solve so the two agree on the policy's current position.
    premium_adjustment = _premium_adjustment_since_valuation(policy, valuation_date)
    ill_policy = _policy_with_post_valuation_premiums(ill_policy, premium_adjustment)

    months_to_target = _months_between_exclusive(valuation_date, target_date)
    if months_to_target <= 0:
        raise ValueError("Target date must leave at least one monthly deduction before the target")

    total_premium_needed = _project_input_to_md_premium(
        ill_policy, target_date, months_to_target)

    accum_glp = _f(getattr(policy, "accumulated_glp_target", None))
    accum_wds = _f(getattr(policy, "total_withdrawals", None))
    # Premiums paid to date, brought current with post-valuation premiums — the
    # DB2 accumulator is as-of the valuation snapshot, so add anything paid since.
    premiums_paid = _f(getattr(policy, "premium_td", None)) + premium_adjustment.gross_premium

    room = max(0.0, accum_glp - premiums_paid + accum_wds)
    adjustment = max(0.0, total_premium_needed - room)
    message = (
        "No adjustment needed" if adjustment <= 0.0
        else f"Increase AccumGLP by {adjustment:,.2f}")

    return GuidelineExceptionAdjustmentResult(
        current_valuation_date=valuation_date,
        target_date=target_date,
        months_to_target=months_to_target,
        premiums_since_valuation_date=premium_adjustment.gross_premium,
        total_premium_needed=total_premium_needed,
        room_available=room,
        accumulated_glp=accum_glp,
        premiums_paid_to_date=premiums_paid,
        accumulated_withdrawals=accum_wds,
        adjustment_to_accum_glp=adjustment,
        new_accum_glp=accum_glp + adjustment,
        message=message,
    )


def _project_input_to_md_premium(
    policy: IllustrationPolicyData,
    target_date: date,
    months_to_target: int,
    engine: IllustrationEngine | None = None,
) -> float:
    """Total gross premium the INPUT-to-MD run pays strictly before the target.

    Builds the INPUT-to-MD run (input premium 0, monthly, Lumpsum-to-Next-Premium
    bridge, TEFRA off), projects past the target date, and sums the premium
    outlay (bridge lumpsum + Monthly-Deduction / GP exception premiums) of every
    projected month whose date is strictly before ``target_date``.
    """
    engine = engine or IllustrationEngine()

    future, options = _input_to_md_run(policy)
    future, options = _apply_lumpsum_to_next(policy, future, options, engine)

    states = engine.project(
        copy.deepcopy(policy),
        options=options,
        future_inputs=future,
        months=months_to_target + 2,
        stop_on_lapse=False,
    )

    return sum(
        state.premium_outlay
        for state in states
        if state.date is not None and state.date < target_date
    )


def _input_to_md_run(
    policy: IllustrationPolicyData,
) -> tuple[IllustrationInputSet, IllustrationOptions]:
    """Future inputs + options for an INPUT-to-MD run with a 0 input premium.

    Silences the default modal billing (input premium is 0) and lets the engine
    hand off from the (zero) premium to the Monthly Deduction premium — then GP
    exceptions — across the whole remaining policy life. TEFRA enforcement is
    OFF so the guideline never caps the Monthly Deduction premium: the outlay is
    the raw premium the policy needs to stay in force.
    """
    issue_age = int(policy.issue_age or 0)
    maturity_age = int(policy.maturity_age or 121)
    forecast_year = int(policy.policy_year or 1)
    maturity_year = max(1, maturity_age - issue_age)

    scheduled = [ScheduledTransaction(
        kind=TransactionKind.PREMIUM, policy_year=forecast_year,
        amount=0.0, mode="A")]
    future = IllustrationInputSet(scheduled_transactions=scheduled)
    options = IllustrationOptions(
        # TEFRA limit enforcement OFF — the whole point of the solve is to size
        # the premium the policy needs regardless of the guideline cap.
        conform_to_tefra=False,
        conform_to_tamra=False,
        # INPUT to MD always allows GP exceptions — the billable → MD → exception
        # sequence is the mechanism.
        allow_exception_prems=True,
        billable_to_md_windows=[(forecast_year, maturity_year)],
    )
    return future, options


def _apply_lumpsum_to_next(
    policy: IllustrationPolicyData,
    future: IllustrationInputSet,
    options: IllustrationOptions,
    engine: IllustrationEngine,
) -> tuple[IllustrationInputSet, IllustrationOptions]:
    """Solve the Lumpsum-to-Next-Premium bridge on a MONTHLY cadence and layer it in.

    Forces a monthly billing cadence for the bridge (the requirement's "mode
    beginning monthly") so the bridge targets the next monthly premium, funds the
    policy up to it, and suppresses the MD hand-off until then — mirroring the
    Billable-to-MD batch run. A failed or unneeded bridge leaves the run
    unchanged.
    """
    from dataclasses import replace

    from suiteview.illustration.core.solve_lumpsum_to_next_premium import (
        LUMPSUM_SUBTYPE,
        solve_lumpsum_to_next_premium,
    )

    bridge_policy = copy.deepcopy(policy)
    bridge_policy.billing_frequency = 1  # monthly cadence for the bridge

    try:
        lump = solve_lumpsum_to_next_premium(
            bridge_policy,
            base_future_inputs=future,
            base_options=options,
            engine=engine)
    except Exception:  # bridge solve failed — run without it
        lump = None

    if lump is None or lump.lumpsum <= 0:
        return future, options

    dated = list(future.dated_transactions)
    dated.append(DatedTransaction(
        kind=TransactionKind.PREMIUM,
        effective_date=lump.forecast_date,
        amount=lump.lumpsum,
        subtype=LUMPSUM_SUBTYPE))
    future = IllustrationInputSet(
        scheduled_transactions=list(future.scheduled_transactions),
        dated_transactions=dated,
        policy_changes=list(future.policy_changes))
    options = replace(options, billable_to_md_no_latch_before=lump.next_premium_date)
    return future, options


def _f(value) -> float:
    """Coerce a possibly-Decimal / None DB value to float."""
    try:
        return float(value or 0.0)
    except (TypeError, ValueError):
        return 0.0
