"""Solve the "Min Level to Maturity" premium — the minimum modal level premium
that keeps a policy in force all the way to maturity.

Pass ``horizon_months`` to stop short of maturity and solve the minimum level
premium that keeps the policy in force only that far (the Policy Support GLP
Exception screen solves to a user-supplied target date). The answer may be $0
when the account value alone carries the policy that far.

For GPT policies the solve rides the GLP exception period when the guideline
caps further funding (when exceptions are allowed). CVAT policies have no
guideline premium cap and no exception machinery, so their solve always runs
with exceptions off and the level premium simply endows.

Paid level from its start year (honoring any prior premium rows), this is the
lowest premium at which the policy never lapses early. One of two things happens
at that premium:

  * the policy endows with a non-negative account value (a healthy policy that
    simply needs a sustaining premium), or
  * it reaches the GLP Exception period and rides at zero to maturity on
    exception premiums (a policy the guideline won't let you fund any further).

Below this premium the policy lapses with guideline room still unused. Above it
the premium is eventually clipped by the guideline cap — the "pay more, then
less, then more" pattern the client experiences. The minimum is therefore the
single premium that stays perfectly level right up to the exception period.

The account value is piecewise-nonlinear in the premium (the guideline cap is a
MIN, the exception premium a MAX), so there is no closed form. "In force at
maturity" is monotone in the premium, though, so we bracket and bisect on the
real engine.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import date
from typing import List, Optional

from dateutil.relativedelta import relativedelta

from suiteview.illustration.core.calc_engine import IllustrationEngine
from suiteview.illustration.core.input_compiler import compile_month_inputs
from suiteview.illustration.core.solvers import bracket_and_bisect
from suiteview.illustration.models.calc_state import MonthlyState
from suiteview.illustration.models.input_set import (
    DatedTransaction,
    IllustrationInputSet,
    IllustrationOptions,
    ScheduledTransaction,
    TransactionKind,
)
from suiteview.illustration.models.policy_data import IllustrationPolicyData

# Months-between-payments → RERUN modal code.
_MODE_FROM_FREQ = {1: "M", 3: "Q", 6: "S", 12: "A"}

# Backstop so a pathological policy can never loop the upper-bracket search.
_MAX_BRACKET_DOUBLINGS = 24

# Clean-transition search: a modest window above the survive-minimum (start at
# +1%, grow 5% per step, 6 steps → at most about +35%), and at most one payment
# clipped by the guideline cap (the one that exhausts the room) before the
# exception period begins.
_CLEAN_WINDOW_START = 1.01
_CLEAN_WINDOW_GROWTH = 1.05
_CLEAN_WINDOW_STEPS = 6
_MAX_CLIPPED_PAYMENTS = 1


class LevelToExceptionError(ValueError):
    """The solve cannot run for this policy (no level premium solution)."""


@dataclass
class LevelToExceptionResult:
    premium: float                   # solved modal level premium, rounded up
    mode: str                        # M / Q / S / A
    enters_exception: bool           # rode a GLP Exception period to the horizon
    exception_start: Optional[date]  # first month of that exception period
    exception_duration: Optional[int]  # policy year that exception period begins
    ending_av: float                 # account value at the last projected month
                                     # (maturity, or ``horizon_months`` when set)
    total_premium_paid: float        # premiums over the projection at the solved
                                     # premium — applied premium + GP exception
                                     # premium + loan repayments
    iterations: int                  # engine projections spent solving


def default_premium_mode(policy: IllustrationPolicyData) -> str:
    return _MODE_FROM_FREQ.get(int(policy.billing_frequency or 1), "M")


def level_to_exception_options(
    base: Optional[IllustrationOptions], allow_exceptions: bool = True,
    apply_prem_to_loan: Optional[bool] = None,
    conform_to_tamra: bool = True,
) -> IllustrationOptions:
    """Guideline-conforming basis for the solve.

    ``allow_exceptions`` selects the regime: True lets the policy ride the GLP
    exception period to maturity — and guarantees a high-enough premium always
    survives; False requires the level premium to endow on its own, with no
    exception rescue (the solve then reports no solution for a guideline-bound
    policy). The
    interest-day convention, interim opening value, forceout choice and
    premium-levelizing choice are inherited so
    the applied premium is shown consistently with the rest of the app; both the
    solve and the displayed run must use this same basis, or the solved premium
    won't behave as solved. Levelizing also applies in the first guideline-capped
    year; the transition-year dollar-for-dollar option must not override it.

    ``apply_prem_to_loan`` (sInput_ApplyPremToLoan) makes the level premium repay
    the policy loan before funding the account value — required to solve a policy
    that carries a loan. ``None`` inherits it from ``base`` (e.g. the UI's "Apply
    Premium to Loan First" toggle); a bool forces it.

    ``conform_to_tamra`` keeps the 7-pay (TAMRA/MEC) cap on by default; a batch
    caller can turn it off to solve on a guideline-only basis.
    """
    exact = getattr(base, "exact_days_interest", None) if base is not None else None
    levelizing = bool(getattr(base, "levelizing_premium", False)) if base is not None else False
    if apply_prem_to_loan is None:
        apply_prem_to_loan = bool(getattr(base, "apply_prem_to_loan", False)) if base is not None else False
    return IllustrationOptions(
        conform_to_tefra=True,
        conform_to_tamra=conform_to_tamra,
        allow_exception_prems=allow_exceptions,
        exact_days_interest=exact,
        levelizing_premium=levelizing,
        dollar_for_dollar_in_transition_year=not levelizing,
        apply_prem_to_loan=apply_prem_to_loan,
        guideline_forceouts=base.guideline_forceouts if base is not None else True,
        recognize_inforce_exception_period=(
            base.recognize_inforce_exception_period if base is not None else True),
        interim_opening=base.interim_opening if base is not None else None,
    )


def solve_level_to_exception(
    policy: IllustrationPolicyData,
    *,
    mode: Optional[str] = None,
    start_policy_year: int = 1,
    base_future_inputs: Optional[IllustrationInputSet] = None,
    allow_exceptions: bool = True,
    apply_prem_to_loan: Optional[bool] = None,
    conform_to_tamra: bool = True,
    resolution: float = 0.01,
    fund_transition_cleanly: bool = True,
    horizon_months: Optional[int] = None,
    base_options: Optional[IllustrationOptions] = None,
    engine: Optional[IllustrationEngine] = None,
    first_month_premium_floor: float = 0.0,
    single_premium: bool = False,
) -> LevelToExceptionResult:
    """Minimum modal level premium that keeps ``policy`` in force to maturity.

    Args:
        mode: modal cadence of the solved premium (M/Q/S/A); defaults to the
            policy's billing frequency.
        start_policy_year: policy year the solved level premium begins. Earlier
            years are governed by ``base_future_inputs`` (the honored prior
            premium rows); the level premium takes over from this year to
            maturity. ``1`` means "from the first projected month."
        base_future_inputs: prior premium schedule to honor. The level premium is
            layered on top at ``start_policy_year`` (a later same-or-greater year
            schedule wins in the compiler), so the years before it keep whatever
            these inputs specify.
        first_month_premium_floor: optional gross first-month funding floor.
            Any amount above that month's scheduled premium is paid once, not
            repeated as part of the solved level premium.
        single_premium: solve a single first-month payment instead of recurring
            premiums, for an initial bridge before regular modal billing resumes.
        resolution: rounding granularity; the result is rounded UP to this so it
            lands on the in-force side of the lapse boundary.
        fund_transition_cleanly: prefer a (slightly higher) premium that keeps
            the policy fully self-funded until the guideline room is exhausted, so
            no GP exception premium fires while room remains — the "perfectly level
            right up to the exception period" contract. Only a modest window above
            the survive-minimum is searched, and a premium the guideline cap clips
            payment after payment is never accepted (the pattern must stay level).
            Never returns less than the plain survive-minimum; falls back to it
            when no clean level premium is in the window. Turn off to solve only
            for bare survival.
        horizon_months: stop the projection this many months out and solve only
            for staying in force that far, instead of to maturity. The minimum is
            then often $0 — a policy whose account value alone carries it to the
            horizon needs no premium at all. Use it to answer "what is the least
            this policy must take in between now and <date>?"
            A finite horizon requires positive ending surrender value and no
            lapse, or the engine's zero-value GP exception protection.
        apply_prem_to_loan: make the level premium repay the policy loan before
            funding the account value (sInput_ApplyPremToLoan) — needed to solve a
            policy that carries a loan. ``None`` inherits it from ``base_options``;
            a bool forces it.
        base_options: only ``exact_days_interest``, ``levelizing_premium``,
            ``apply_prem_to_loan``, ``guideline_forceouts``,
            ``recognize_inforce_exception_period`` and ``interim_opening``
            are read from it; the guideline and exception toggles are forced on.
    """
    if horizon_months is not None and horizon_months < 0:
        raise LevelToExceptionError("The projection horizon cannot be negative.")

    # CVAT policies have no guideline premium cap and no GLP exception machinery:
    # the solve runs with exceptions off and the level premium simply endows.
    # TAMRA conformance is also forced off. The CVAT TAMRA cap past the 7-pay
    # window is the necessary-premium test (vNPT_Premium, deemed_cash_value.py),
    # which needs a user-entered deemed cash value; the solve does not demand it.
    if policy.is_cvat:
        allow_exceptions = False
        conform_to_tamra = False

    mode = (mode or default_premium_mode(policy)).upper()
    options = level_to_exception_options(
        base_options, allow_exceptions, apply_prem_to_loan, conform_to_tamra)
    engine = engine or IllustrationEngine()

    base = base_future_inputs

    def project(premium: float) -> List[MonthlyState]:
        future = level_to_exception_inputs(
            policy, premium, mode, start_policy_year,
            base_future_inputs=base,
            first_month_premium_floor=first_month_premium_floor,
            single_premium=single_premium,
        )
        return engine.project(policy, options=options, future_inputs=future,
                              months=horizon_months)

    def survives(states: List[MonthlyState]) -> bool:
        # stop_on_lapse truncates a lapsing run before its horizon; a surviving
        # run (endow or exception) reaches every month that was asked for.
        if not states:
            return False
        if horizon_months is not None:
            # The engine includes the lapse row, even when it is the last month.
            last = states[-1]
            reached = (len(states) > horizon_months
                       or last.attained_age >= policy.maturity_age)
            if not reached or any(s.lapsed for s in states):
                return False
            # Ordinary funding must leave positive surrender value, not merely
            # positive AV or safety-net protection. GP exceptions instead fund
            # the engine's zero-value boundary after guideline room is exhausted.
            return last.ending_sv > 0.0 or (
                allow_exceptions and last.gp_exception_mode
                and last.ending_sv >= -0.0001)
        return states[-1].attained_age >= policy.maturity_age

    def cleanly_funded(states: List[MonthlyState]) -> bool:
        # The stricter target the module contract promises: a premium that stays
        # "perfectly level right up to the exception period." A premium that only
        # just survives limps into the exception period under-funded — the level
        # premium can no longer keep the account value positive between modal
        # payments, so a GP exception premium fires WHILE guideline room still
        # remains (the ragged transition year). Require instead that the FIRST GP
        # exception premium cannot fire until the guideline room is genuinely
        # exhausted; a run that simply endows (no exception at all) is clean too.
        if not survives(states):
            return False
        if (options.recognize_inforce_exception_period
                and policy.in_exception_period):
            return True
        clipped_months = 0
        for s in states:
            if float(getattr(s, "gp_exception_prem_gross", 0.0) or 0.0) > 1e-9:
                # Guideline room left AFTER this month's billable premium: the
                # limit less premiums-paid-net-of-withdrawals (prem_less_wd is the
                # pre-premium figure, so add what was accepted this month). Room
                # essentially gone (≤ $1) means the exception is legitimate.
                room = s.guideline_limit - (
                    s.prem_less_wd
                    + s.applied_scheduled_premium
                    + s.applied_lumpsum)
                return room <= 1.0 and clipped_months <= _MAX_CLIPPED_PAYMENTS
            if getattr(s, "premium_capped", False):
                clipped_months += 1
        return clipped_months <= _MAX_CLIPPED_PAYMENTS

    iterations = 0

    def solve_for(predicate) -> Optional[float]:
        """Minimum modal premium (rounded up to ``resolution``) satisfying
        ``predicate``, or None when no premium in the bracket does."""
        nonlocal iterations
        if predicate(project(0.0)):
            return 0.0
        solved = bracket_and_bisect(
            lambda premium: predicate(project(premium)),
            0.0,
            max(policy.modal_premium, 1.0),
            growth=2.0,
            tol=resolution / 2.0,
            max_iter=_MAX_BRACKET_DOUBLINGS,
            round_to=resolution,
            round_up=True,
            carry_lower=False,
        )
        iterations += solved.evaluations
        return solved.value if solved.bracketed else None

    # Baseline: the lowest premium that stays in force to the horizon.
    survive_premium = solve_for(survives)
    if survive_premium is None:
        raise LevelToExceptionError(
            "No level premium keeps this policy in force to the target date."
            if horizon_months is not None else
            "No level premium keeps this policy in force to maturity.")

    premium = survive_premium
    if fund_transition_cleanly:
        # Prefer a slightly higher premium that funds the transition year cleanly
        # (no GP exception premium while guideline room remains) while still
        # paying level. "Clean" is NOT monotone in the premium: far above the
        # survive-minimum the guideline cap clips payment after payment and some
        # high premium can look clean by coincidence, so search only a modest
        # window above the survive-minimum and never accept a clipped pattern.
        # Falls back to the survive-minimum when no clean premium is in the
        # window; never returns LESS than it, so it can only ADD funding.
        clean_premium = survive_premium
        if not cleanly_funded(project(survive_premium)):
            iterations += 1
            found = bracket_and_bisect(
                lambda candidate: cleanly_funded(project(candidate)),
                survive_premium,
                max(round(survive_premium * _CLEAN_WINDOW_START, 2),
                    round(survive_premium + resolution, 2)),
                growth=_CLEAN_WINDOW_GROWTH,
                tol=resolution / 2.0,
                round_to=resolution,
                round_up=True,
                bracket_max_iter=_CLEAN_WINDOW_STEPS,
            )
            iterations += found.evaluations
            clean_premium = found.value if found.bracketed else survive_premium
            if not cleanly_funded(project(clean_premium)):
                clean_premium = survive_premium
            iterations += 1
        premium = max(survive_premium, clean_premium)

    states = project(premium)
    iterations += 1
    if horizon_months is not None and not survives(states):
        raise LevelToExceptionError(
            "The rounded premium did not meet the target-date surrender-value requirement.")
    return _build_result(premium, mode, states, iterations)


def level_to_exception_inputs(
    policy: IllustrationPolicyData, premium: float, mode: str,
    start_policy_year: int, *,
    base_future_inputs: Optional[IllustrationInputSet] = None,
    first_month_premium_floor: float = 0.0,
    single_premium: bool = False,
) -> IllustrationInputSet:
    """Share the exact level/one-time funding schedule between solve and display."""
    if not math.isfinite(first_month_premium_floor) or first_month_premium_floor < 0:
        raise LevelToExceptionError("The first-month premium floor must be finite and non-negative.")
    base = base_future_inputs
    future = IllustrationInputSet(
        scheduled_transactions=list(base.scheduled_transactions) if base is not None else [],
        dated_transactions=list(base.dated_transactions) if base is not None else [],
        policy_changes=list(base.policy_changes) if base is not None else [],
    )
    future.scheduled_transactions.append(ScheduledTransaction(
        kind=TransactionKind.PREMIUM, policy_year=int(start_policy_year),
        amount=0.0 if single_premium else float(premium), mode=mode))
    if single_premium:
        first_month_premium_floor = max(first_month_premium_floor, premium)
    if first_month_premium_floor > 0:
        if policy.issue_date is None:
            raise LevelToExceptionError("An issue date is required for the one-time premium.")
        first = compile_month_inputs(policy, future, 1)[policy.duration + 1]
        top_up = round(max(
            0.0, first_month_premium_floor
            - (first.scheduled_premium or 0.0) - first.unscheduled_premium), 2)
        if top_up > 0:
            future.dated_transactions.append(DatedTransaction(
                kind=TransactionKind.PREMIUM,
                effective_date=policy.issue_date + relativedelta(months=policy.duration),
                amount=top_up,
                subtype="initial_shortfall",
            ))
    return future


def _build_result(
    premium: float, mode: str, states: List[MonthlyState], iterations: int,
) -> LevelToExceptionResult:
    exc_state = next((s for s in states if s.exception_prem_mode), None)
    exc_start = exc_state.date if exc_state is not None else None
    exc_duration = exc_state.policy_year if exc_state is not None else None
    ending_av = states[-1].av_end_of_month if states else 0.0
    # Premiums over the projection: the cumulative applied premium
    # (premiums_to_date already includes the inforce history and projected
    # scheduled/unscheduled premium) plus the GP exception premium and any loan
    # repayments, neither of which flows through premiums_to_date.
    applied_to_date = float(states[-1].premiums_to_date) if states else 0.0
    exception_paid = sum(float(s.gp_exception_prem_gross or 0.0) for s in states)
    loan_repaid = sum(float(s.applied_loan_repayment or 0.0) for s in states)
    return LevelToExceptionResult(
        premium=round(premium, 2),
        mode=mode,
        enters_exception=exc_start is not None,
        exception_start=exc_start,
        exception_duration=exc_duration,
        ending_av=ending_av,
        total_premium_paid=round(applied_to_date + exception_paid + loan_repaid, 2),
        iterations=iterations,
    )
