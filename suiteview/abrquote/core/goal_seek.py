"""
ABR Quote — Goal Seek module.

Replaces Excel's Goal Seek with scipy.optimize.brentq for finding:
    1. Table rating from medical assessment survival rates
    2. Flat extra from target survival probability
    3. Life expectancy computation

These functions bridge the medical assessment inputs (5yr survival,
10yr survival, life expectancy) to the substandard mortality parameters
(table rating, flat extra) used by the mortality engine.
"""

from __future__ import annotations

import logging
from dataclasses import replace
from typing import Callable, Tuple

from ..models.abr_data import MedicalAssessment, MortalityParams
from .mortality_engine import MortalityEngine

logger = logging.getLogger(__name__)

# Try importing scipy; provide fallback if not available
try:
    from scipy.optimize import brentq
    HAS_SCIPY = True
except ImportError:
    HAS_SCIPY = False
    logger.warning("scipy not available — goal seek will use bisection fallback")


def _bisect_fallback(
    func: Callable[[float], float],
    a: float,
    b: float,
    xtol: float = 1e-6,
    maxiter: int = 200,
) -> float:
    """Simple bisection method as fallback when scipy is not available."""
    fa = func(a)
    fb = func(b)

    if fa * fb > 0:
        # Try to find a sign change by expanding the bracket
        for _ in range(20):
            a -= (b - a) * 0.5
            b += (b - a) * 0.5
            fa = func(a)
            fb = func(b)
            if fa * fb <= 0:
                break
        else:
            raise ValueError(f"No sign change in interval [{a}, {b}]")

    for _ in range(maxiter):
        mid = (a + b) / 2.0
        fm = func(mid)
        if abs(fm) < xtol or (b - a) / 2.0 < xtol:
            return mid
        if fa * fm < 0:
            b = mid
            fb = fm
        else:
            a = mid
            fa = fm

    return (a + b) / 2.0


def _root_find(
    func: Callable[[float], float],
    a: float,
    b: float,
    xtol: float = 1e-6,
) -> float:
    """Find root using scipy.brentq or bisection fallback."""
    if HAS_SCIPY:
        try:
            return brentq(func, a, b, xtol=xtol, maxiter=200)
        except ValueError:
            logger.warning("brentq failed, trying bisection fallback")
            return _bisect_fallback(func, a, b, xtol=xtol)
    else:
        return _bisect_fallback(func, a, b, xtol=xtol)


def find_table_rating(
    base_params: MortalityParams,
    target_survival: float,
    years: int = 5,
) -> float:
    """Find the continuous table rating that produces the target survival.

    The VBA workbook uses Excel GoalSeek with no bounds on the table rating
    cell. For terminally ill young insureds, the table rating can be in the
    thousands (producing very high mortality multipliers).

    The table rating formula: qx_rated = qx × (1 + table_rating × 0.25)

    Args:
        base_params: Base mortality parameters (with table_rating_1=0).
        target_survival: Target survival probability.
        years: Survival horizon (5 or 10 years).

    Returns:
        Continuous table rating (float, unbounded).
    """
    def objective(table_rating: float) -> float:
        params = replace(base_params, table_rating_1=table_rating)
        engine = MortalityEngine(params)
        computed_survival = engine.compute_survival_probability(years)
        return computed_survival - target_survival

    # Start with a wide search range; narrow if needed
    max_search = 50000.0
    try:
        result = _root_find(objective, 0.0, max_search, xtol=1e-6)
        return max(0.0, result)
    except Exception as e:
        logger.error(f"Table rating goal seek failed: {e}")
        # Fall back to iterative search
        return float(_iterative_table_search(base_params, target_survival))


def find_combined_substandard(
    base_params: MortalityParams,
    assessment: MedicalAssessment,
    assessment_index: int = 1,
) -> Tuple[float, float, float]:
    """Find table rating and flat extra from medical assessment.

    Matches the VBA Goal_Seek_Table_Rating behavior:
    - Assessment Index 1 or 2: Table rating from 5-year survival
    - Assessment Index 3 or 4: Table rating from 10-year survival
    - Assessment Index 5: Table rating from life expectancy
    - Assessment Index 6: Table rating = direct input
    - Assessment Index 7: Table rating = increased_decrement / 25

    After finding table rating, flat extra is zero (matching VBA which
    zeroes Table_2 but does not goal-seek flat extra in this sub).
    The user's existing policy flat extra (if any) is separate.

    Args:
        base_params: Base mortality parameters (standard rates).
        assessment: Medical assessment with survival targets.
        assessment_index: 1-7, determines which metric to match.

    Returns:
        Tuple of (table_rating, flat_extra, computed_life_expectancy).
    """
    table_rating = 0.0
    flat_extra = 0.0

    if assessment_index in (1, 2):
        # Goal seek table rating from 5-year survival
        table_rating = find_table_rating(
            base_params, assessment.five_year_survival, years=5
        )
    elif assessment_index in (3, 4):
        # Goal seek table rating from 10-year survival
        table_rating = find_table_rating(
            base_params, assessment.ten_year_survival, years=10
        )
    elif assessment_index == 5:
        # Goal seek table rating from life expectancy
        table_rating = _find_table_from_le(
            base_params, assessment.life_expectancy_years
        )
    elif assessment_index == 6:
        # Direct input — use LE to derive table rating
        # In VBA: Table_1 = Table_Rating_Input
        table_rating = assessment.derived_table_rating
    elif assessment_index == 7:
        # Increased decrement formula: Table_1 = B39 / 25
        table_rating = assessment.derived_increased_decrement / 25.0

    # Compute resulting life expectancy with the found table rating
    final_params = replace(base_params, table_rating_1=table_rating)
    engine = MortalityEngine(final_params)
    life_expectancy = engine.compute_life_expectancy()

    return table_rating, flat_extra, life_expectancy


def find_table_rating_period2(
    base_params: MortalityParams,
    target_survival: float,
    table_1: float,
    period_1_months: int = 60,
    total_years: int = 10,
) -> float:
    """Find a table rating for period 2 that achieves the target cumulative survival.

    Period 1 uses `table_1` for the first `period_1_months` months (relative to
    the current policy month).  Period 2 table rating is solved for — it starts
    immediately after period 1 and runs through `total_years * 12` months from
    the current policy month.

    All month boundaries are **absolute** (anchored to policy_month from
    base_params) so that the mortality engine's loop — which starts at
    policy_month — applies the ratings over the correct window.

    Args:
        base_params: Base mortality parameters (standard rates).
        target_survival: Target cumulative survival probability over `total_years`.
        table_1: The already-solved table rating for period 1.
        period_1_months: Duration of period 1 in months (default 60 = 5 years).
        total_years: Total survival horizon in years (default 10).

    Returns:
        Continuous table rating for period 2.
    """
    pm = base_params.policy_month
    p1_start = pm                       # first month the engine will process
    p1_end   = pm + period_1_months - 1 # last month of period 1
    p2_start = p1_end + 1               # first month of period 2
    p2_end   = pm + total_years * 12 - 1  # last month of period 2

    def objective(table_rating_2: float) -> float:
        params = replace(
            base_params,
            table_rating_1=table_1,
            table_1_start_month=p1_start,
            table_1_last_month=p1_end,
            table_rating_2=table_rating_2,
            table_2_start_month=p2_start,
            table_2_last_month=p2_end,
        )
        engine = MortalityEngine(params)
        computed_survival = engine.compute_survival_probability(total_years)
        return computed_survival - target_survival

    try:
        result = _root_find(objective, 0.0, 50000.0, xtol=1e-6)
        return max(0.0, result)
    except Exception as e:
        logger.error(f"Period 2 table rating goal seek failed: {e}")
        return 0.0


def find_dual_table_ratings(
    base_params: MortalityParams,
    five_yr_survival: float,
    ten_yr_survival: float,
    return_after_10yr: bool = False,
) -> Tuple[float, float, float]:
    """Solve for two table ratings: one for years 1-5 and one for years 6-10.

    Step 1: Solve for table_rating_1 to hit the 5-year survival.
            Applied from the current policy month for 60 months.
    Step 2: Holding table_rating_1 fixed, solve for table_rating_2
            (next 60 months) to hit the 10-year cumulative survival.

    All month boundaries are **absolute** (anchored to the policy_month in
    base_params) so the mortality engine applies them correctly.

    Args:
        base_params: Base mortality params (standard, no table/flat).
        five_yr_survival: Target 5-year survival probability.
        ten_yr_survival: Target 10-year cumulative survival probability.
        return_after_10yr: If True, period 2 table drops after year 10.

    Returns:
        Tuple of (table_rating_5yr, table_rating_10yr, life_expectancy).
    """
    pm = base_params.policy_month
    p1_start = pm                # absolute month: start of 5yr window
    p1_end   = pm + 59           # absolute month: end of 5yr window
    p2_start = pm + 60           # absolute month: start of 6-10yr window
    p2_end   = pm + 119          # absolute month: end of 10yr window

    # Solve period 1: table rating for 5-year window
    params_p1 = replace(
        base_params,
        table_1_start_month=p1_start,
        table_1_last_month=p1_end,
    )
    table_5yr = find_table_rating(params_p1, five_yr_survival, years=5)

    # Solve period 2: table rating for months p2_start..p2_end
    # to hit 10yr cumulative survival
    table_10yr = find_table_rating_period2(
        base_params,
        ten_yr_survival,
        table_1=table_5yr,
        period_1_months=60,
        total_years=10,
    )

    # Compute LE using the dual table structure
    last_month_p2 = p2_end if return_after_10yr else 9999
    final_params = replace(
        base_params,
        table_rating_1=table_5yr,
        table_1_start_month=p1_start,
        table_1_last_month=p1_end,
        table_rating_2=table_10yr,
        table_2_start_month=p2_start,
        table_2_last_month=last_month_p2,
    )
    engine = MortalityEngine(final_params)
    life_expectancy = engine.compute_life_expectancy()

    return table_5yr, table_10yr, life_expectancy


def _find_table_from_le(
    base_params: MortalityParams,
    target_le: float,
) -> float:
    """Find table rating that produces a target life expectancy."""
    def objective(table_rating: float) -> float:
        params = replace(base_params, table_rating_1=table_rating)
        engine = MortalityEngine(params)
        computed_le = engine.compute_life_expectancy()
        return computed_le - target_le

    try:
        return max(0.0, _root_find(objective, 0.0, 50000.0, xtol=1e-6))
    except Exception as e:
        logger.error(f"LE goal seek failed: {e}")
        return 0.0


def compute_assessment_index(table_rating: float) -> int:
    """Map continuous table rating to assessment index (1-7).

    For display purposes, the continuous table rating from goal seek
    is classified into letter ratings A-G (1-7).
    The mapping uses the standard insurance convention:
    0 = Standard, 1-4 = A(1), 5-8 = B(2), 9-12 = C(3),
    13-16 = D(4), 17-20 = E(5), 21-24 = F(6), 25+ = G(7).
    """
    if table_rating <= 0:
        return 0
    # Clamp to effective range for letter classification
    clamped = min(25, int(round(table_rating)))
    index = min(7, (clamped - 1) // 4 + 1)
    return max(1, index)


def _iterative_table_search(
    base_params: MortalityParams,
    target_survival: float,
) -> int:
    """Fallback: brute-force search for table rating.

    Tests each integer table rating 0-25 and returns the one
    producing survival closest to target.
    """
    best_rating = 0
    best_diff = float("inf")

    for rating in range(26):
        params = replace(base_params, table_rating_1=rating)
        engine = MortalityEngine(params)
        survival = engine.compute_survival_probability(5)
        diff = abs(survival - target_survival)
        if diff < best_diff:
            best_diff = diff
            best_rating = rating

    return best_rating
