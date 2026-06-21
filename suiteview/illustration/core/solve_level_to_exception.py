"""Solve the "Max Level Premium to Exception" — the minimum modal level premium
that keeps a GPT policy in force all the way to maturity.

Paid level from the first forecast month (nothing else: no other premiums,
withdrawals, loans, or face changes), this is the lowest premium at which the
policy never lapses early. One of two things happens at that premium:

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

from suiteview.illustration.core.calc_engine import IllustrationEngine
from suiteview.illustration.models.calc_state import MonthlyState
from suiteview.illustration.models.input_set import (
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


class LevelToExceptionError(ValueError):
    """The solve cannot run for this policy (CVAT, carries a loan, or no solution)."""


@dataclass
class LevelToExceptionResult:
    premium: float                   # solved modal level premium, rounded up
    mode: str                        # M / Q / S / A
    enters_exception: bool           # rode a GLP Exception period to maturity
    exception_start: Optional[date]  # first month of that exception period
    maturity_av: float               # account value at maturity at the solved premium
    iterations: int                  # engine projections spent solving


def _default_mode(policy: IllustrationPolicyData) -> str:
    return _MODE_FROM_FREQ.get(int(policy.billing_frequency or 1), "M")


def _solve_options(base: Optional[IllustrationOptions]) -> IllustrationOptions:
    """Guideline-conforming basis with exception premiums forced on.

    The exception premium is the whole point of the solve — and what guarantees a
    high-enough premium always survives — so it is enabled regardless of the
    caller's toggle. Only the interest-day convention is inherited.
    """
    exact = getattr(base, "exact_days_interest", None) if base is not None else None
    return IllustrationOptions(
        conform_to_tefra=True,
        conform_to_tamra=True,
        allow_exception_prems=True,
        exact_days_interest=exact,
    )


def solve_level_to_exception(
    policy: IllustrationPolicyData,
    *,
    mode: Optional[str] = None,
    resolution: float = 0.01,
    base_options: Optional[IllustrationOptions] = None,
    engine: Optional[IllustrationEngine] = None,
) -> LevelToExceptionResult:
    """Minimum modal level premium that keeps ``policy`` in force to maturity.

    Args:
        mode: modal cadence of the solved premium (M/Q/S/A); defaults to the
            policy's billing frequency.
        resolution: rounding granularity; the result is rounded UP to this so it
            lands on the in-force side of the lapse boundary.
        base_options: only ``exact_days_interest`` is read from it; the guideline
            and exception toggles are forced on for the solve.
    """
    if policy.is_cvat:
        raise LevelToExceptionError("Level-to-Exception applies to GPT policies only.")
    if policy.has_loans:
        raise LevelToExceptionError(
            "Level-to-Exception is unavailable while the policy carries a loan.")

    mode = (mode or _default_mode(policy)).upper()
    options = _solve_options(base_options)
    engine = engine or IllustrationEngine()

    def project(premium: float) -> List[MonthlyState]:
        future = IllustrationInputSet(scheduled_transactions=[
            ScheduledTransaction(
                kind=TransactionKind.PREMIUM, policy_year=1,
                amount=float(premium), mode=mode),
        ])
        return engine.project(policy, options=options, future_inputs=future)

    def survives(states: List[MonthlyState]) -> bool:
        # stop_on_lapse truncates a lapsing run before maturity; a surviving run
        # (endow or exception) reaches the maturity age.
        return bool(states) and states[-1].attained_age >= policy.maturity_age

    iterations = 0

    # Zero premium already endows? Nothing to solve.
    if survives(project(0.0)):
        return _build_result(0.0, mode, project(0.0), iterations)
    lo = 0.0

    # Exponentially grow an upper bracket that survives. With exception premiums
    # on, a high-enough premium is always rescued at the guideline limit, so this
    # terminates quickly.
    hi = max(policy.modal_premium, 1.0)
    doublings = 0
    while not survives(project(hi)):
        iterations += 1
        hi *= 2.0
        doublings += 1
        if doublings > _MAX_BRACKET_DOUBLINGS:
            raise LevelToExceptionError(
                "No level premium keeps this policy in force to maturity.")
    iterations += 1

    # Bisect the lapse↔survive boundary to the resolution.
    while hi - lo > resolution:
        mid = (lo + hi) / 2.0
        if survives(project(mid)):
            hi = mid
        else:
            lo = mid
        iterations += 1

    premium = math.ceil(hi / resolution) * resolution
    return _build_result(premium, mode, project(premium), iterations)


def _build_result(
    premium: float, mode: str, states: List[MonthlyState], iterations: int,
) -> LevelToExceptionResult:
    exc_start = next((s.date for s in states if s.exception_prem_mode), None)
    maturity_av = states[-1].av_end_of_month if states else 0.0
    return LevelToExceptionResult(
        premium=round(premium, 2),
        mode=mode,
        enters_exception=exc_start is not None,
        exception_start=exc_start,
        maturity_av=maturity_av,
        iterations=iterations,
    )
