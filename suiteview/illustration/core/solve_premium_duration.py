"""Solve the whole-year duration for a fixed modal premium and value target."""
from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional

from suiteview.illustration.core.calc_engine import IllustrationEngine
from suiteview.illustration.core.solvers import bisect_min_integer
from suiteview.illustration.core.solve_premium_to_target import (
    PremiumTargetError,
    TARGET_FIELDS,
)
from suiteview.illustration.models.calc_state import MonthlyState
from suiteview.illustration.models.input_set import (
    IllustrationInputSet,
    IllustrationOptions,
    ScheduledTransaction,
    TransactionKind,
)
from suiteview.illustration.models.policy_data import IllustrationPolicyData


@dataclass
class PremiumDurationResult:
    duration_years: int
    end_policy_year: int
    premium: float
    mode: str
    target: str
    at_age: int
    achieved_value: Optional[float]
    reached_target: bool
    iterations: int


def solve_premium_duration(
    policy: IllustrationPolicyData,
    *,
    premium: float,
    mode: str,
    target: str,
    amount: float,
    at_age: int,
    start_policy_year: int = 1,
    base_future_inputs: Optional[IllustrationInputSet] = None,
    base_options: Optional[IllustrationOptions] = None,
    engine: Optional[IllustrationEngine] = None,
) -> PremiumDurationResult:
    """Find the fewest whole years of premium that reach the target value.

    When paying through maturity still misses the target, the maturity duration
    is returned with ``reached_target=False`` so the illustration can show the
    best available result instead of stopping.
    """
    context = _duration_context(
        policy, premium, target, amount, at_age, start_policy_year)
    field = context["field"]
    premium = context["premium"]
    amount = context["amount"]
    at_age = context["at_age"]
    start_policy_year = context["start_policy_year"]
    maturity_year = context["maturity_year"]
    target_year = context["target_year"]

    mode = (mode or "M").strip().upper()
    options = base_options if base_options is not None else IllustrationOptions()
    engine = engine or IllustrationEngine()
    base = base_future_inputs
    max_duration = maturity_year - start_policy_year + 1
    iterations = 0

    def project(duration_years: int) -> List[MonthlyState]:
        end_year = start_policy_year + duration_years - 1
        schedules = list(base.scheduled_transactions) if base is not None else []
        schedules.append(ScheduledTransaction(
            kind=TransactionKind.PREMIUM,
            policy_year=start_policy_year,
            amount=premium,
            mode=mode,
        ))
        if end_year < maturity_year:
            schedules.append(ScheduledTransaction(
                kind=TransactionKind.PREMIUM,
                policy_year=end_year + 1,
                amount=0.0,
                mode="A",
            ))
        future = IllustrationInputSet(
            scheduled_transactions=schedules,
            dated_transactions=list(base.dated_transactions) if base is not None else [],
            policy_changes=list(base.policy_changes) if base is not None else [],
        )
        return engine.project(policy, options=options, future_inputs=future)

    def measure(duration_years: int) -> Optional[float]:
        nonlocal iterations
        iterations += 1
        for state in project(duration_years):
            if (
                int(state.policy_year or 0) == target_year
                and int(state.policy_month or 0) == 12
            ):
                return float(getattr(state, field) or 0.0)
        return None

    maturity_value = measure(max_duration)
    if maturity_value is None or maturity_value < amount:
        return PremiumDurationResult(
            duration_years=max_duration,
            end_policy_year=maturity_year,
            premium=premium,
            mode=mode,
            target=target,
            at_age=at_age,
            achieved_value=maturity_value,
            reached_target=False,
            iterations=iterations,
        )

    solved = bisect_min_integer(
        lambda duration_years: (
            (value := measure(duration_years)) is not None and value >= amount
        ),
        1,
        max_duration,
    )
    duration_years = solved.value
    achieved = (
        maturity_value
        if duration_years == max_duration
        else measure(duration_years)
    )
    return PremiumDurationResult(
        duration_years=duration_years,
        end_policy_year=start_policy_year + duration_years - 1,
        premium=premium,
        mode=mode,
        target=target,
        at_age=at_age,
        achieved_value=achieved,
        reached_target=True,
        iterations=iterations,
    )


def _duration_context(
    policy: IllustrationPolicyData,
    premium,
    target: str,
    amount,
    at_age,
    start_policy_year,
) -> dict:
    field_and_label = TARGET_FIELDS.get(target)
    if field_and_label is None:
        raise PremiumTargetError(f"Unknown solve target {target!r}.")
    if premium is None or float(premium) < 0.0:
        raise PremiumTargetError("Enter a Solve for Duration premium of at least 0.")
    if amount is None or float(amount) < 0.0:
        raise PremiumTargetError("Enter a Solve amount of at least 0.")
    premium = float(premium)
    amount = float(amount)
    at_age = int(at_age)
    start_policy_year = int(start_policy_year)
    issue_age = int(policy.issue_age or 0)
    maturity_age = int(policy.maturity_age or 0)
    maturity_year = max(1, maturity_age - issue_age)
    target_year = at_age - issue_age
    _validate_duration_years(
        policy, target, at_age, start_policy_year, issue_age,
        maturity_age, maturity_year, target_year)
    return {
        "field": field_and_label[0],
        "premium": premium,
        "amount": amount,
        "at_age": at_age,
        "start_policy_year": start_policy_year,
        "maturity_year": maturity_year,
        "target_year": target_year,
    }


def _validate_duration_years(
    policy: IllustrationPolicyData,
    target: str,
    at_age: int,
    start_policy_year: int,
    issue_age: int,
    maturity_age: int,
    maturity_year: int,
    target_year: int,
) -> None:
    if target_year < start_policy_year:
        raise PremiumTargetError(
            f"Solve age {at_age} is before the premium's start year - pick an "
            f"age after age {issue_age + start_policy_year - 1}.")
    if at_age > maturity_age:
        raise PremiumTargetError(
            f"Solve age {at_age} is past the maturity age ({maturity_age}).")
    if target == "shadow" and not getattr(policy, "has_shadow_account", False):
        raise PremiumTargetError(
            "This policy has no active shadow account to solve on.")
    if start_policy_year > maturity_year:
        raise PremiumTargetError(
            "The premium start year is after the policy's maturity year.")
