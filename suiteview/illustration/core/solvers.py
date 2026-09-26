"""Shared bracket-and-bisect routines for illustration goal seeks.

Strategy table:

| Caller | Predicate/measure | Bracket | Stop | Rounding |
| --- | --- | --- | --- | --- |
| Premium to target | target-age value reached | modal premium or $1, ×2, 30 tries | half-cent bracket | round up to cent and verify |
| Lumpsum to next premium | bridge window survives | seed shortfall/load gross-up, ×2, 24 tries | half-cent bracket | round up to cent and verify |
| Loan payoff | check-date balance paid off | balance spread over payments, ×2, 24 tries | half-cent bracket | round up to cent and verify |
| Level to exception | horizon survives / clean transition | modal premium or $1, ×2, 24 tries | half-cent bracket | round up to cent and verify |
| Premium duration | target value reached | integer duration 1..maturity | integer lower-bound bisection | no money rounding |
| Guideline search | endowment AV reaches face | face/10 or $100, ×2, 40 tries | value tolerance or max iterations | unrounded midpoint |

The helper is intentionally small: it owns only monotone bracketing, bisection
and the caller-selected rounding convention. Callers still own projection setup,
error wording and any final output fields.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Callable


@dataclass(frozen=True)
class BracketBisectResult:
    """Result of a monotone bracket-and-bisect solve."""

    value: float
    evaluations: int
    bracketed: bool = True
    lower: float = 0.0


@dataclass(frozen=True)
class IntegerBisectResult:
    """Result of an integer lower-bound bisection."""

    value: int
    evaluations: int


def bracket_and_bisect(
    predicate: Callable[[float], bool],
    lo: float,
    hi_seed: float,
    *,
    growth: float = 2.0,
    tol: float = 0.005,
    max_iter: int = 24,
    round_to: float | None = 0.01,
    round_up: bool = True,
    bracket_max_iter: int | None = None,
    value_of: Callable[[float], float] | None = None,
    target: float | None = None,
    value_tolerance: float | None = None,
    carry_lower: bool = True,
) -> BracketBisectResult:
    """Return the first monotone value satisfying ``predicate``.

    ``predicate`` must be false at ``lo`` and monotone nondecreasing. The high
    side starts at ``hi_seed`` and grows by ``growth`` until it satisfies the
    predicate or the bracket limit is exhausted. ``round_to`` selects the final
    grid; ``round_up=True`` uses the existing actuarial solvers' convention of
    ceiling the false boundary and verifying the rounded candidate. Passing
    ``round_to=None`` returns the raw midpoint.

    ``value_of``/``target``/``value_tolerance`` preserve the guideline search's
    value-based early exit while still sharing the same bracketing mechanics.
    """
    if growth <= 1.0:
        raise ValueError("growth must be greater than 1.")
    if target is not None and value_of is None:
        raise ValueError("target searches require value_of.")
    bracket_limit = max_iter if bracket_max_iter is None else bracket_max_iter
    evaluations = 0
    hi = float(hi_seed)
    lo = float(lo)

    bracket = _bracket(
        predicate,
        lo,
        hi,
        growth=growth,
        max_iter=bracket_limit,
        value_of=value_of,
        target=target,
    )
    evaluations += bracket.evaluations
    if not bracket.bracketed:
        return BracketBisectResult(bracket.value, evaluations, bracketed=False)
    if carry_lower:
        lo = bracket.lower
    hi = bracket.value

    if target is not None and value_of is not None:
        return _bisect_to_target(
            value_of,
            lo,
            hi,
            target=target,
            value_tolerance=value_tolerance if value_tolerance is not None else tol,
            max_iter=max_iter,
            evaluations=evaluations,
        )

    while hi - lo > tol:
        mid = (lo + hi) / 2.0
        if predicate(mid):
            hi = mid
        else:
            lo = mid
        evaluations += 1

    if round_to is None:
        return BracketBisectResult((lo + hi) / 2.0, evaluations)
    candidate = _rounded_candidate(lo, hi, step=round_to, round_up=round_up)
    if predicate(candidate):
        evaluations += 1
        return BracketBisectResult(candidate, evaluations)
    evaluations += 1
    candidate = round(candidate + round_to if round_up else candidate - round_to, 2)
    predicate(candidate)
    evaluations += 1
    return BracketBisectResult(candidate, evaluations)


def bisect_min_integer(predicate: Callable[[int], bool], lo: int, hi: int) -> IntegerBisectResult:
    """Return the smallest integer in ``[lo, hi]`` satisfying ``predicate``."""
    evaluations = 0
    while lo < hi:
        mid = (lo + hi) // 2
        if predicate(mid):
            hi = mid
        else:
            lo = mid + 1
        evaluations += 1
    return IntegerBisectResult(lo, evaluations)


def _rounded_candidate(lo: float, hi: float, *, step: float, round_up: bool) -> float:
    if round_up:
        return round(math.ceil(lo / step - 1e-9) * step, 2)
    return round(math.floor(hi / step + 1e-9) * step, 2)


def _bracket(
    predicate: Callable[[float], bool],
    lo: float,
    hi: float,
    *,
    growth: float,
    max_iter: int,
    value_of: Callable[[float], float] | None,
    target: float | None,
) -> BracketBisectResult:
    evaluations = 0
    lower = lo
    for _ in range(max_iter + 1):
        ok = value_of(hi) >= target if value_of is not None and target is not None else predicate(hi)
        evaluations += 1
        if ok:
            return BracketBisectResult(hi, evaluations, lower=lower)
        lower = hi
        hi *= growth
    return BracketBisectResult(hi, evaluations, bracketed=False, lower=lower)


def _bisect_to_target(
    value_of: Callable[[float], float],
    lo: float,
    hi: float,
    *,
    target: float,
    value_tolerance: float,
    max_iter: int,
    evaluations: int,
) -> BracketBisectResult:
    for _ in range(max_iter):
        mid = (lo + hi) / 2.0
        value = value_of(mid)
        evaluations += 1
        if abs(value - target) <= value_tolerance:
            return BracketBisectResult(mid, evaluations)
        if value < target:
            lo = mid
        else:
            hi = mid
    return BracketBisectResult((lo + hi) / 2.0, evaluations)
