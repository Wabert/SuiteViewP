"""Solve the "Solve" premium — the minimum level modal premium that carries a
chosen policy value (Account Value, Surrender Value, or Shadow Account Value)
to a target amount at a target age.

The "At Age" is the age at the BEGINNING of a policy year, so the criterion is
the ENDING value of the year before it: solving for age 100 checks the ending
value at attained age 99, end of policy month 12 — the last month before the
anniversary that attains 100.

The premium pays level at the row's mode from its start year through its span
(end year), honoring the prior premium rows / lumpsum / policy changes in the
base inputs, under the SAME run options as the displayed run (guideline and
TAMRA toggles as the user set them) — or the solved premium would not behave
as solved when the run renders it.

The ending value is monotone nondecreasing in the level premium (the guideline
cap can only plateau it, never reverse it), so the solve brackets and bisects
on the real engine, exactly like Prem to Maturity. If even the bracket ceiling
cannot reach the target (guideline cap, policy charges, or a lapse before the
target age), the solve raises with the best value it could reach so the UI can
say so.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
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

# Target keys → (MonthlyState field, display label).
TARGET_FIELDS = {
    "av": ("av_end_of_month", "Account Value"),
    "sv": ("ending_sv", "Surrender Value"),
    "shadow": ("shadow_eav", "Shadow Account Value"),
}

# Backstop so a pathological policy can never loop the upper-bracket search.
_MAX_BRACKET_DOUBLINGS = 30


class PremiumTargetError(ValueError):
    """The target cannot be met (or the request is invalid for this policy).

    ``best_value`` carries the highest value the bracket ceiling reached (None
    when the request never projected), so the UI can report how far short the
    policy falls.
    """

    def __init__(self, message: str, best_value: Optional[float] = None):
        super().__init__(message)
        self.best_value = best_value


@dataclass
class PremiumTargetResult:
    premium: float                 # solved modal level premium, rounded up
    mode: str                      # M / Q / S / A
    target: str                    # av / sv / shadow
    at_age: int                    # beginning-of-year target age
    achieved_value: float          # ending value at the target month
    iterations: int                # engine projections spent solving


def _default_mode(policy: IllustrationPolicyData) -> str:
    return _MODE_FROM_FREQ.get(int(policy.billing_frequency or 1), "M")


def solve_premium_to_target(
    policy: IllustrationPolicyData,
    *,
    target: str,
    amount: float,
    at_age: int,
    mode: Optional[str] = None,
    start_policy_year: int = 1,
    end_policy_year: Optional[int] = None,
    base_future_inputs: Optional[IllustrationInputSet] = None,
    resolution: float = 0.01,
    base_options: Optional[IllustrationOptions] = None,
    engine: Optional[IllustrationEngine] = None,
) -> PremiumTargetResult:
    """Minimum level premium whose ending ``target`` value at ``at_age``
    (beginning-of-year age → prior year's month-12 ending value) reaches
    ``amount``.

    Args:
        target: "av", "sv", or "shadow" (see ``TARGET_FIELDS``).
        amount: the value to reach (>= 0).
        at_age: beginning-of-year age; must be after the premium start and at
            most the maturity age.
        end_policy_year: last policy year the level premium pays (the row's
            For Years / To Age span); None pays to maturity.
        base_options: the displayed run's options — used AS-IS so the solved
            premium behaves identically when the run renders it.
    """
    field_and_label = TARGET_FIELDS.get(target)
    if field_and_label is None:
        raise PremiumTargetError(f"Unknown solve target {target!r}.")
    field, label = field_and_label
    if amount is None or float(amount) < 0.0:
        raise PremiumTargetError("Enter a Solve amount of at least 0.")
    amount = float(amount)
    at_age = int(at_age)
    issue_age = int(policy.issue_age or 0)
    # The criterion month: month 12 of the policy year that BEGINS at
    # at_age − 1 (its ending value is the value AT at_age).
    target_year = at_age - issue_age
    if target_year < int(start_policy_year):
        raise PremiumTargetError(
            f"Solve age {at_age} is before the premium's start year — pick an "
            f"age after age {issue_age + int(start_policy_year) - 1}.")
    if at_age > int(policy.maturity_age or 0):
        raise PremiumTargetError(
            f"Solve age {at_age} is past the maturity age "
            f"({policy.maturity_age}).")
    if target == "shadow" and not getattr(policy, "has_shadow_account", False):
        raise PremiumTargetError(
            "This policy has no active shadow account to solve on.")

    mode = (mode or _default_mode(policy)).upper()
    options = base_options if base_options is not None else IllustrationOptions()
    engine = engine or IllustrationEngine()
    base = base_future_inputs

    def project(premium: float) -> List[MonthlyState]:
        scheds = list(base.scheduled_transactions) if base is not None else []
        scheds.append(ScheduledTransaction(
            kind=TransactionKind.PREMIUM, policy_year=int(start_policy_year),
            amount=float(premium), mode=mode))
        if end_policy_year is not None:
            scheds.append(ScheduledTransaction(
                kind=TransactionKind.PREMIUM,
                policy_year=int(end_policy_year) + 1, amount=0.0, mode="A"))
        future = IllustrationInputSet(
            scheduled_transactions=scheds,
            dated_transactions=list(base.dated_transactions) if base is not None else [],
            policy_changes=list(base.policy_changes) if base is not None else [],
        )
        return engine.project(policy, options=options, future_inputs=future)

    def measure(states: List[MonthlyState]) -> Optional[float]:
        """Ending value at the target month, or None if the projection never
        got there (lapsed first)."""
        for state in states:
            if (int(state.policy_year or 0) == target_year
                    and int(state.policy_month or 0) == 12):
                return float(getattr(state, field) or 0.0)
        return None

    def met(value: Optional[float]) -> bool:
        # Half-resolution slack so a value the engine rounds to the target
        # (e.g. 100,000.004 vs 100,000.01) doesn't chase the bracket upward.
        return value is not None and value >= amount - resolution / 2.0

    iterations = 0

    zero_value = measure(project(0.0))
    iterations += 1
    if met(zero_value):
        return PremiumTargetResult(
            premium=0.0, mode=mode, target=target, at_age=at_age,
            achieved_value=float(zero_value), iterations=iterations)

    # Exponentially grow an upper bracket that meets the target. The guideline
    # cap / charges may plateau the value below the target — the backstop then
    # reports the best the policy could do.
    lo = 0.0
    hi = max(float(policy.modal_premium or 0.0), 1.0)
    best: Optional[float] = zero_value
    doublings = 0
    while True:
        value = measure(project(hi))
        iterations += 1
        if value is not None and (best is None or value > best):
            best = value
        if met(value):
            break
        lo = hi
        hi *= 2.0
        doublings += 1
        if doublings > _MAX_BRACKET_DOUBLINGS:
            reached = f"{best:,.2f}" if best is not None else "no target-age value"
            raise PremiumTargetError(
                f"No level premium reaches {label} of {amount:,.2f} at age "
                f"{at_age} — the best this policy reaches is {reached} "
                f"(the guideline premium cap and policy charges limit what "
                f"can be funded).",
                best_value=best)

    # Bisect the not-met ↔ met boundary until the bracket is narrower than
    # HALF the resolution, then test the rounded candidate directly. Ceiling
    # the raw ``hi`` (which can sit up to a full step above the boundary)
    # overshoots by a penny whenever the boundary lies just under a grid
    # point; with the half-step bracket the answer is provably either the
    # first step at/above ``lo`` or the one after it.
    while hi - lo > resolution / 2.0:
        mid = (lo + hi) / 2.0
        if met(measure(project(mid))):
            hi = mid
        else:
            lo = mid
        iterations += 1

    premium = round(math.ceil(lo / resolution - 1e-9) * resolution, 2)
    achieved = measure(project(premium))
    iterations += 1
    if not met(achieved):
        premium = round(premium + resolution, 2)
        achieved = measure(project(premium))
        iterations += 1
    return PremiumTargetResult(
        premium=premium, mode=mode, target=target, at_age=at_age,
        achieved_value=float(achieved or 0.0), iterations=iterations)
