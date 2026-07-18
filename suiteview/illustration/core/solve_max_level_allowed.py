"""Solve the "Max Level Allowed" premium — the largest modal level premium a
GPT policy can pay, level from its start year to age 100 (or maturity if
sooner), without the 7702 guideline/TAMRA acceptance chain ever cutting a
payment back.

Historically this was a closed form off the inforce guidelines: remaining
guideline room at age 100 divided by the modal payments to get there. That form
cannot see mid-projection guideline changes — an illustrated face decrease or
DB-option change recalculates GLP/GSP (and the AccumGLP stream) from that point
on, so the real constraint is the FULL cumulative allowance chain: at every
payment date the cumulative premiums (net of withdrawals) may not exceed
max(AccumGLP, GSP) as they stand THEN — through the final GSP / AccumGLP at age
100 after any changes along the way. The binding point may be mid-projection (a
guideline drop can make an intermediate year tighter than the endpoint), and a
"max level" premium that gets silently clipped later isn't level — so the solve
demands the projection never caps or rejects a requested premium.

The acceptance chain is premium-independent (guideline premiums depend on face,
DB option and rates — not the account value), so "never capped" is monotone in
the level premium: bracket and bisect on the real engine, exactly like the
Min-to-Maturity solve. The premium schedule stops at age 100 — AccumGLP stops
growing there, so payments past it would always cap.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import List, Optional

from suiteview.illustration.core.calc_engine import IllustrationEngine
from suiteview.illustration.core.solve_level_to_exception import (
    level_to_exception_options,
)
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
_MAX_BRACKET_DOUBLINGS = 30


class MaxLevelAllowedError(ValueError):
    """The solve cannot run for this policy (CVAT, base inputs already over the
    guideline limit, or the guideline never caps the premium)."""


@dataclass
class MaxLevelAllowedResult:
    premium: float                 # solved modal level premium, rounded down
    mode: str                      # M / Q / S / A
    survives_to_maturity: bool     # in force at maturity at the solved premium
    end_age: int                   # attained age the projection reached
    maturity_av: float             # account value at the projection's last month
    total_premium_paid: float      # lifetime premiums at the solved premium
    iterations: int                # engine projections spent solving


def _default_mode(policy: IllustrationPolicyData) -> str:
    return _MODE_FROM_FREQ.get(int(policy.billing_frequency or 1), "M")


def solve_max_level_allowed(
    policy: IllustrationPolicyData,
    *,
    mode: Optional[str] = None,
    start_policy_year: int = 1,
    base_future_inputs: Optional[IllustrationInputSet] = None,
    allow_exceptions: bool = True,
    resolution: float = 0.01,
    base_options: Optional[IllustrationOptions] = None,
    engine: Optional[IllustrationEngine] = None,
) -> MaxLevelAllowedResult:
    """Largest modal level premium the guideline chain accepts in full.

    Args:
        mode: modal cadence of the solved premium (M/Q/S/A); defaults to the
            policy's billing frequency.
        start_policy_year: policy year the level premium begins. Earlier years
            are governed by ``base_future_inputs`` (the honored prior premium
            rows); the level premium runs from this year to age 100 (or
            maturity if sooner), then stops.
        base_future_inputs: prior premium schedule AND any policy changes (face
            amount / DB option) to honor — every projection in the solve
            carries them, so the solved maximum reflects the changed
            guidelines.
        allow_exceptions: whether the projection may ride GP exception premiums
            (follows the user's Allow GP Exception toggle so the solve basis
            matches the displayed run).
        resolution: rounding granularity; the result is rounded DOWN to this so
            it lands on the accepted side of the guideline cap.
        base_options: only ``exact_days_interest``, ``levelizing_premium`` and
            ``apply_prem_to_loan`` are read from it; the guideline and TAMRA
            conformance toggles are forced on (there is no premium cap to solve
            against without them).
    """
    if policy.is_cvat:
        raise MaxLevelAllowedError("Max Level Allowed applies to GPT policies only.")

    mode = (mode or _default_mode(policy)).upper()
    options = level_to_exception_options(base_options, allow_exceptions)
    engine = engine or IllustrationEngine()
    base = base_future_inputs

    # Premiums stop at age 100 — AccumGLP freezes there (CalcEngine KU), so any
    # level payment past it would always be capped and no positive premium
    # could ever pass. Maturity before 100 needs no stop: the engine collects
    # no premium on or after the maturity date.
    stop_year: Optional[int] = None
    if policy.maturity_age > 100:
        stop_year = 100 - int(policy.issue_age or 0) + 1
        if stop_year <= int(start_policy_year):
            raise MaxLevelAllowedError(
                "No level-premium window remains — the policy is at or past "
                "the age-100 premium limit.")

    def project(premium: float) -> List[MonthlyState]:
        scheds = list(base.scheduled_transactions) if base is not None else []
        scheds.append(ScheduledTransaction(
            kind=TransactionKind.PREMIUM, policy_year=int(start_policy_year),
            amount=float(premium), mode=mode))
        if stop_year is not None:
            scheds.append(ScheduledTransaction(
                kind=TransactionKind.PREMIUM, policy_year=int(stop_year),
                amount=0.0, mode="A"))
        future = IllustrationInputSet(
            scheduled_transactions=scheds,
            dated_transactions=list(base.dated_transactions) if base is not None else [],
            policy_changes=list(base.policy_changes) if base is not None else [],
        )
        return engine.project(policy, options=options, future_inputs=future)

    def accepted(states: List[MonthlyState]) -> bool:
        return not any(s.premium_capped for s in states)

    iterations = 0

    # Zero premium must pass — if the base inputs alone are already capped
    # (e.g. a lumpsum over the guideline room) there is nothing to solve.
    if not accepted(project(0.0)):
        raise MaxLevelAllowedError(
            "The base inputs already exceed the guideline premium limit — "
            "no additional level premium is allowed.")
    iterations += 1
    lo = 0.0

    # Exponentially grow an upper bracket the guideline cap rejects. The
    # cumulative guideline limit is finite for a GPT policy, so doubling from
    # the modal premium reaches it quickly.
    hi = max(float(policy.modal_premium or 0.0), 1.0)
    doublings = 0
    while accepted(project(hi)):
        iterations += 1
        lo = hi
        hi *= 2.0
        doublings += 1
        if doublings > _MAX_BRACKET_DOUBLINGS:
            raise MaxLevelAllowedError(
                "The guideline limit never caps the premium — "
                "no finite maximum level premium exists.")
    iterations += 1

    # Bisect the accepted↔capped boundary to the resolution.
    while hi - lo > resolution:
        mid = (lo + hi) / 2.0
        if accepted(project(mid)):
            lo = mid
        else:
            hi = mid
        iterations += 1

    premium = math.floor(lo / resolution) * resolution
    return _build_result(premium, mode, policy, project(premium), iterations)


def _build_result(
    premium: float,
    mode: str,
    policy: IllustrationPolicyData,
    states: List[MonthlyState],
    iterations: int,
) -> MaxLevelAllowedResult:
    end_age = int(states[-1].attained_age) if states else int(policy.attained_age or 0)
    survives = bool(states) and states[-1].attained_age >= policy.maturity_age
    maturity_av = float(states[-1].av_end_of_month) if states else 0.0
    applied_to_date = float(states[-1].premiums_to_date) if states else 0.0
    exception_paid = sum(float(s.gp_exception_prem_gross or 0.0) for s in states)
    loan_repaid = sum(float(s.applied_loan_repayment or 0.0) for s in states)
    return MaxLevelAllowedResult(
        premium=round(premium, 2),
        mode=mode,
        survives_to_maturity=survives,
        end_age=end_age,
        maturity_av=maturity_av,
        total_premium_paid=round(applied_to_date + exception_paid + loan_repaid, 2),
        iterations=iterations,
    )
