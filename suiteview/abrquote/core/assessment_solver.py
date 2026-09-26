"""Core medical-assessment solver for the dedicated ABR Quote tool.

The UI supplies an :class:`AssessmentInputs` value object; this module performs
the same substandard goal-seek and mortality projection that previously lived in
``AssessmentPanel._on_calculate``.  Returned values include both the domain
``MedicalAssessment`` and the display strings the panel needs to render without
repeating actuarial decisions.
"""

from __future__ import annotations

from dataclasses import dataclass, replace

from ..models.abr_constants import (
    MATURITY_AGE,
    MORTALITY_IMPROVEMENT_CAP,
    MORTALITY_IMPROVEMENT_RATE,
    MORTALITY_MULTIPLIER,
    MORTALITY_MULTIPLIER_TERMINAL,
)
from ..models.abr_data import ABRPolicyData, MedicalAssessment, MortalityParams
from .goal_seek import (
    compute_assessment_index,
    find_combined_substandard,
    find_dual_table_ratings,
)
from .mortality_engine import MortalityEngine


@dataclass(frozen=True)
class AssessmentInputs:
    """User-selected ABR medical-assessment inputs.

    Year ranges use the UI convention: start year is inclusive and stop year is
    exclusive, relative to the quote date/current policy duration.
    """

    rider_type: str = "Terminal"
    use_five_year: bool = False
    use_ten_year: bool = False
    use_le: bool = False
    use_table: bool = False
    use_flat: bool = False
    use_increased_decrement: bool = False
    use_table_2: bool = False
    use_flat_2: bool = False
    use_return_5yr: bool = False
    use_return_10yr: bool = False
    in_lieu_of: bool = True
    five_year_survival: float = 0.0
    ten_year_survival: float = 0.0
    life_expectancy_years: float = 0.0
    direct_increased_decrement: float = 0.0
    incr_decrement_start_year: int = 1
    incr_decrement_stop_year: int = 99
    direct_table_rating: float = 0.0
    table_start_year: int = 1
    table_stop_year: int = 99
    direct_flat_extra: float = 0.0
    flat_start_year: int = 1
    flat_stop_year: int = 99
    direct_table_rating_2: float = 0.0
    table_2_start_year: int = 1
    table_2_stop_year: int = 99
    direct_flat_extra_2: float = 0.0
    flat_2_start_year: int = 1
    flat_2_stop_year: int = 99


@dataclass(frozen=True)
class AssessmentResultViewModel:
    """Display-ready text derived from a substandard solve."""

    std_survival_5yr: str
    std_survival_10yr: str
    std_le: str
    std_table_rating: str
    std_flat_extra: str
    mod_survival_5yr: str
    mod_survival_10yr: str
    mod_le: str
    table_rating: str
    flat_extra: str

    def as_labels(self) -> dict[str, str]:
        """Return label-key text used by the existing assessment panel."""
        return {
            "std_survival_5yr": self.std_survival_5yr,
            "std_survival_10yr": self.std_survival_10yr,
            "std_le": self.std_le,
            "std_table_rating": self.std_table_rating,
            "std_flat_extra": self.std_flat_extra,
            "mod_survival_5yr": self.mod_survival_5yr,
            "mod_survival_10yr": self.mod_survival_10yr,
            "mod_le": self.mod_le,
            "table_rating": self.table_rating,
            "flat_extra": self.flat_extra,
        }


@dataclass(frozen=True)
class SubstandardSolveResult:
    """Complete result of an ABR medical substandard solve."""

    assessment: MedicalAssessment
    base_params: MortalityParams
    mortality_params: MortalityParams
    standard_le: float
    standard_survival_5yr: float
    standard_survival_10yr: float
    view_model: AssessmentResultViewModel

    @property
    def derived_values(self) -> dict[str, str]:
        """Existing workbook/export label mapping."""
        return self.view_model.as_labels()


def _abs_policy_month(policy: ABRPolicyData) -> int:
    return (policy.policy_year - 1) * 12 + policy.policy_month


def _year_range(abs_policy_month: int, start_year: int, stop_year: int) -> tuple[int, int]:
    start_month = abs_policy_month + (start_year - 1) * 12
    stop_month = abs_policy_month + (stop_year - 1) * 12 - 1
    return start_month, stop_month


def build_base_mortality_params(
    policy: ABRPolicyData,
    inputs: AssessmentInputs | str,
) -> MortalityParams:
    """Build clean mortality parameters for the current assessment rider."""
    rider_type = inputs if isinstance(inputs, str) else inputs.rider_type
    is_terminal = rider_type == "Terminal"
    return MortalityParams(
        issue_age=policy.issue_age,
        sex=policy.rate_sex or policy.sex,
        rate_class=policy.rate_class,
        policy_month=_abs_policy_month(policy),
        maturity_age=policy.maturity_age or MATURITY_AGE,
        table_rating_1=0.0,
        table_1_start_month=1,
        table_1_last_month=9999,
        flat_extra_1=0.0,
        flat_1_start_month=1,
        flat_1_duration=9999,
        mortality_multiplier=(
            MORTALITY_MULTIPLIER_TERMINAL if is_terminal else MORTALITY_MULTIPLIER
        ),
        improvement_rate=0.0 if is_terminal else MORTALITY_IMPROVEMENT_RATE,
        improvement_cap=MORTALITY_IMPROVEMENT_CAP,
        is_terminal=is_terminal,
    )


def _standard_projection(base_params: MortalityParams) -> tuple[float, float, float]:
    standard_params = replace(
        base_params,
        mortality_multiplier=MORTALITY_MULTIPLIER,
        improvement_rate=MORTALITY_IMPROVEMENT_RATE,
        is_terminal=False,
    )
    engine = MortalityEngine(standard_params)
    return (
        engine.compute_life_expectancy(),
        engine.compute_survival_probability(5),
        engine.compute_survival_probability(10),
    )


def _rating_addons(
    policy: ABRPolicyData,
    inputs: AssessmentInputs,
    has_survival_solve: bool,
) -> tuple[list[tuple[float, int, int]], list[tuple[float, int, int]]]:
    abs_month = _abs_policy_month(policy)
    additional_tables: list[tuple[float, int, int]] = []
    additional_flats: list[tuple[float, int, int]] = []

    if not inputs.in_lieu_of:
        if policy.table_rating > 0:
            additional_tables.append((float(policy.table_rating), 1, 9999))
        if policy.table_rating_2 > 0:
            additional_tables.append((float(policy.table_rating_2), 1, 9999))
        if policy.flat_extra > 0:
            flat_last = 9999
            if policy.flat_to_age > 0:
                remaining = max(0, policy.flat_to_age - policy.attained_age) * 12
                flat_last = abs_month + remaining
            additional_flats.append((policy.flat_extra, 1, flat_last))

    if inputs.use_table and inputs.direct_table_rating > 0 and has_survival_solve:
        additional_tables.append(
            (inputs.direct_table_rating, *_year_range(abs_month, inputs.table_start_year, inputs.table_stop_year))
        )
    if inputs.use_flat and inputs.direct_flat_extra > 0:
        additional_flats.append(
            (inputs.direct_flat_extra, *_year_range(abs_month, inputs.flat_start_year, inputs.flat_stop_year))
        )
    if inputs.use_table_2 and inputs.direct_table_rating_2 > 0:
        additional_tables.append(
            (
                inputs.direct_table_rating_2,
                *_year_range(abs_month, inputs.table_2_start_year, inputs.table_2_stop_year),
            )
        )
    if inputs.use_flat_2 and inputs.direct_flat_extra_2 > 0:
        additional_flats.append(
            (
                inputs.direct_flat_extra_2,
                *_year_range(abs_month, inputs.flat_2_start_year, inputs.flat_2_stop_year),
            )
        )
    if inputs.use_increased_decrement and inputs.direct_increased_decrement > 0:
        additional_tables.append(
            (
                inputs.direct_increased_decrement / 25.0,
                *_year_range(
                    abs_month,
                    inputs.incr_decrement_start_year,
                    inputs.incr_decrement_stop_year,
                ),
            )
        )
    return additional_tables, additional_flats


def _solve_primary_tables(
    base_params: MortalityParams,
    inputs: AssessmentInputs,
) -> tuple[float, float, float, float]:
    table_rating = 0.0
    table_rating_5yr = 0.0
    table_rating_10yr = 0.0
    computed_le = 0.0

    if inputs.use_five_year and inputs.use_ten_year:
        table_rating_5yr, table_rating_10yr, computed_le = find_dual_table_ratings(
            base_params,
            inputs.five_year_survival,
            inputs.ten_year_survival,
            return_after_10yr=inputs.use_return_10yr,
        )
        table_rating = table_rating_5yr
    elif inputs.use_five_year:
        table_rating, _, computed_le = find_combined_substandard(
            base_params,
            MedicalAssessment(five_year_survival=inputs.five_year_survival),
            assessment_index=1,
        )
        table_rating_5yr = table_rating
        if inputs.use_return_5yr:
            final_p = replace(
                base_params,
                table_rating_1=table_rating,
                table_1_start_month=base_params.policy_month,
                table_1_last_month=base_params.policy_month + 59,
            )
            computed_le = MortalityEngine(final_p).compute_life_expectancy()
    elif inputs.use_ten_year:
        table_rating, _, computed_le = find_combined_substandard(
            base_params,
            MedicalAssessment(ten_year_survival=inputs.ten_year_survival),
            assessment_index=3,
        )
        if inputs.use_return_10yr:
            final_p = replace(
                base_params,
                table_rating_1=table_rating,
                table_1_start_month=base_params.policy_month,
                table_1_last_month=base_params.policy_month + 119,
            )
            computed_le = MortalityEngine(final_p).compute_life_expectancy()
    elif inputs.use_le:
        table_rating, _, computed_le = find_combined_substandard(
            base_params,
            MedicalAssessment(life_expectancy_years=inputs.life_expectancy_years),
            assessment_index=5,
        )
    elif inputs.use_table:
        table_rating = inputs.direct_table_rating
    return table_rating, table_rating_5yr, table_rating_10yr, computed_le


def _mortality_params_from_components(
    base_params: MortalityParams,
    inputs: AssessmentInputs,
    table_rating: float,
    table_rating_5yr: float,
    table_rating_10yr: float,
    additional_tables: list[tuple[float, int, int]],
    additional_flats: list[tuple[float, int, int]],
) -> MortalityParams:
    abs_month = base_params.policy_month
    has_survival_solve = inputs.use_five_year or inputs.use_ten_year or inputs.use_le
    is_dual_solve = inputs.use_five_year and inputs.use_ten_year
    if is_dual_solve:
        return replace(
            base_params,
            table_rating_1=table_rating_5yr,
            table_1_start_month=abs_month,
            table_1_last_month=abs_month + 59,
            table_rating_2=table_rating_10yr,
            table_2_start_month=abs_month + 60,
            table_2_last_month=abs_month + 119 if inputs.use_return_10yr else 9999,
            additional_tables=additional_tables,
            additional_flats=additional_flats,
        )
    if has_survival_solve:
        if inputs.use_five_year and inputs.use_return_5yr:
            t1_last = abs_month + 59
        elif inputs.use_ten_year and inputs.use_return_10yr:
            t1_last = abs_month + 119
        else:
            t1_last = 9999
        return replace(
            base_params,
            table_rating_1=table_rating,
            table_1_start_month=abs_month,
            table_1_last_month=t1_last,
            additional_tables=additional_tables,
            additional_flats=additional_flats,
        )
    table_start, table_stop = _year_range(abs_month, inputs.table_start_year, inputs.table_stop_year)
    return replace(
        base_params,
        table_rating_1=table_rating,
        table_1_start_month=table_start,
        table_1_last_month=table_stop,
        additional_tables=additional_tables,
        additional_flats=additional_flats,
    )


def assessment_to_mortality_params(
    policy: ABRPolicyData,
    assessment: MedicalAssessment,
) -> MortalityParams:
    """Convert a completed assessment to mortality-engine parameters."""
    inputs = AssessmentInputs(
        rider_type=assessment.rider_type,
        use_five_year=assessment.use_five_year,
        use_ten_year=assessment.use_ten_year,
        use_le=assessment.use_le,
        use_table=assessment.use_table,
        use_flat=assessment.use_flat,
        use_increased_decrement=assessment.use_increased_decrement,
        use_table_2=assessment.use_table_2,
        use_flat_2=assessment.use_flat_2,
        use_return_5yr=assessment.use_return_5yr,
        use_return_10yr=assessment.use_return_10yr,
        in_lieu_of=assessment.in_lieu_of,
        five_year_survival=assessment.five_year_survival,
        ten_year_survival=assessment.ten_year_survival,
        life_expectancy_years=assessment.life_expectancy_years,
        direct_increased_decrement=assessment.direct_increased_decrement,
        incr_decrement_start_year=assessment.incr_decrement_start_year,
        incr_decrement_stop_year=assessment.incr_decrement_stop_year,
        direct_table_rating=assessment.direct_table_rating,
        table_start_year=assessment.table_start_year,
        table_stop_year=assessment.table_stop_year,
        direct_flat_extra=assessment.direct_flat_extra,
        flat_start_year=assessment.flat_start_year,
        flat_stop_year=assessment.flat_stop_year,
        direct_table_rating_2=assessment.direct_table_rating_2,
        table_2_start_year=assessment.table_2_start_year,
        table_2_stop_year=assessment.table_2_stop_year,
        direct_flat_extra_2=assessment.direct_flat_extra_2,
        flat_2_start_year=assessment.flat_2_start_year,
        flat_2_stop_year=assessment.flat_2_stop_year,
    )
    base = build_base_mortality_params(policy, inputs)
    has_survival_solve = inputs.use_five_year or inputs.use_ten_year or inputs.use_le
    additional_tables, additional_flats = _rating_addons(policy, inputs, has_survival_solve)
    return _mortality_params_from_components(
        base,
        inputs,
        assessment.derived_table_rating,
        assessment.derived_table_rating_5yr,
        assessment.derived_table_rating_10yr,
        additional_tables,
        additional_flats,
    )


def _standard_text(policy: ABRPolicyData, standard_le: float, surv5: float, surv10: float) -> dict[str, str]:
    table_text = "None"
    if policy.table_rating > 0 or policy.table_rating_2 > 0:
        parts = []
        if policy.table_rating > 0:
            parts.append(f"Table {policy.table_rating}")
        if policy.table_rating_2 > 0:
            parts.append(f"Table {policy.table_rating_2}")
        table_text = "  |  ".join(parts)
    flat_text = "None"
    if policy.flat_extra > 0:
        flat_text = f"${policy.flat_extra:.3f}/1000"
        if policy.flat_to_age > 0:
            flat_text += f" (to age {policy.flat_to_age})"
    return {
        "std_survival_5yr": f"{surv5:.4f}  ({surv5 * 100:.2f}%)",
        "std_survival_10yr": f"{surv10:.4f}  ({surv10 * 100:.2f}%)",
        "std_le": f"{standard_le:.1f} years (age {policy.attained_age + round(standard_le)})",
        "std_table_rating": table_text,
        "std_flat_extra": flat_text,
    }


def _modified_text(
    policy: ABRPolicyData,
    inputs: AssessmentInputs,
    assessment: MedicalAssessment,
) -> dict[str, str]:
    table_parts = _modified_table_parts(policy, inputs, assessment)
    flat_parts = _modified_flat_parts(policy, inputs)
    return {
        "mod_survival_5yr": (
            f"{assessment.computed_survival_5yr:.4f}  "
            f"({assessment.computed_survival_5yr * 100:.2f}%)"
        ),
        "mod_survival_10yr": (
            f"{assessment.computed_survival_10yr:.4f}  "
            f"({assessment.computed_survival_10yr * 100:.2f}%)"
        ),
        "mod_le": (
            f"{assessment.computed_le:.1f} years "
            f"(age {policy.attained_age + round(assessment.computed_le)})"
        ),
        "table_rating": "  |  ".join(table_parts) if table_parts else "None",
        "flat_extra": "  |  ".join(flat_parts) if flat_parts else "None",
    }


def _modified_table_parts(
    policy: ABRPolicyData,
    inputs: AssessmentInputs,
    assessment: MedicalAssessment,
) -> list[str]:
    yrs_to_maturity = (policy.maturity_age or MATURITY_AGE) - policy.attained_age
    has_survival_solve = inputs.use_five_year or inputs.use_ten_year or inputs.use_le
    table_parts: list[str] = []
    if not inputs.in_lieu_of and policy.table_rating > 0:
        table_parts.append(f"Policy Tbl {policy.table_rating} (existing)")
    if not inputs.in_lieu_of and policy.table_rating_2 > 0:
        table_parts.append(f"Policy Tbl {policy.table_rating_2} (existing)")
    if inputs.use_five_year and inputs.use_ten_year:
        table_parts.append(f"5yr: {assessment.derived_table_rating_5yr:.2f} (yrs 1-5)")
        p2_label = "yrs 6-10" if inputs.use_return_10yr else f"yrs 6-{yrs_to_maturity}"
        table_parts.append(f"6-10yr: {assessment.derived_table_rating_10yr:.2f} ({p2_label})")
    elif assessment.derived_table_rating > 0 and has_survival_solve:
        if inputs.use_five_year and inputs.use_return_5yr:
            yr_label = "yrs 1-5"
        elif inputs.use_ten_year and inputs.use_return_10yr:
            yr_label = "yrs 1-10"
        else:
            yr_label = f"yrs 1-{yrs_to_maturity}"
        table_parts.append(f"{assessment.derived_table_rating:.2f} ({yr_label})")
    if inputs.use_table and inputs.direct_table_rating > 0:
        table_parts.append(
            f"Tbl {inputs.direct_table_rating:.0f} "
            f"(yr {inputs.table_start_year}-{inputs.table_stop_year - 1})"
        )
    if inputs.use_table_2 and inputs.direct_table_rating_2 > 0:
        table_parts.append(
            f"Tbl2 {inputs.direct_table_rating_2:.0f} "
            f"(yr {inputs.table_2_start_year}-{inputs.table_2_stop_year - 1})"
        )
    if inputs.use_increased_decrement and inputs.direct_increased_decrement > 0:
        id_table = inputs.direct_increased_decrement / 25.0
        table_parts.append(
            f"ID {inputs.direct_increased_decrement:.0f}% "
            f"(Tbl {id_table:.0f}, yr "
            f"{inputs.incr_decrement_start_year}-{inputs.incr_decrement_stop_year - 1})"
        )
    return table_parts


def _modified_flat_parts(policy: ABRPolicyData, inputs: AssessmentInputs) -> list[str]:
    flat_parts: list[str] = []
    if not inputs.in_lieu_of and policy.flat_extra > 0:
        text = f"Policy ${policy.flat_extra:.3f}"
        text += f" (to age {policy.flat_to_age})" if policy.flat_to_age > 0 else " (existing)"
        flat_parts.append(text)
    if inputs.use_flat and inputs.direct_flat_extra > 0:
        flat_parts.append(
            f"${inputs.direct_flat_extra:.3f} "
            f"(yr {inputs.flat_start_year}-{inputs.flat_stop_year - 1})"
        )
    if inputs.use_flat_2 and inputs.direct_flat_extra_2 > 0:
        flat_parts.append(
            f"${inputs.direct_flat_extra_2:.3f} "
            f"(yr {inputs.flat_2_start_year}-{inputs.flat_2_stop_year - 1})"
        )
    return flat_parts


def _build_result(
    policy: ABRPolicyData,
    inputs: AssessmentInputs,
    base_params: MortalityParams,
    mortality_params: MortalityParams,
    table_rating: float,
    table_rating_5yr: float,
    table_rating_10yr: float,
    computed_le: float,
) -> SubstandardSolveResult:
    engine = MortalityEngine(mortality_params)
    final_le = engine.compute_life_expectancy()
    survival_5yr = engine.compute_survival_probability(5)
    survival_10yr = engine.compute_survival_probability(10)
    standard_le, standard_5yr, standard_10yr = _standard_projection(base_params)
    if not computed_le:
        computed_le = final_le
    assessment = MedicalAssessment(
        rider_type=inputs.rider_type,
        use_five_year=inputs.use_five_year,
        use_ten_year=inputs.use_ten_year,
        use_le=inputs.use_le,
        use_increased_decrement=inputs.use_increased_decrement,
        use_table=inputs.use_table,
        use_flat=inputs.use_flat,
        use_table_2=inputs.use_table_2,
        use_flat_2=inputs.use_flat_2,
        use_return_5yr=inputs.use_return_5yr,
        use_return_10yr=inputs.use_return_10yr,
        in_lieu_of=inputs.in_lieu_of,
        five_year_survival=inputs.five_year_survival,
        ten_year_survival=inputs.ten_year_survival,
        life_expectancy_years=inputs.life_expectancy_years or computed_le,
        life_expectancy_rounded=round(inputs.life_expectancy_years or computed_le),
        direct_increased_decrement=inputs.direct_increased_decrement,
        incr_decrement_start_year=inputs.incr_decrement_start_year,
        incr_decrement_stop_year=inputs.incr_decrement_stop_year,
        direct_table_rating=inputs.direct_table_rating,
        table_start_year=inputs.table_start_year,
        table_stop_year=inputs.table_stop_year,
        direct_flat_extra=inputs.direct_flat_extra,
        flat_start_year=inputs.flat_start_year,
        flat_stop_year=inputs.flat_stop_year,
        direct_table_rating_2=inputs.direct_table_rating_2,
        table_2_start_year=inputs.table_2_start_year,
        table_2_stop_year=inputs.table_2_stop_year,
        direct_flat_extra_2=inputs.direct_flat_extra_2,
        flat_2_start_year=inputs.flat_2_start_year,
        flat_2_stop_year=inputs.flat_2_stop_year,
        derived_table_rating=table_rating,
        derived_table_rating_5yr=table_rating_5yr,
        derived_table_rating_10yr=table_rating_10yr,
        derived_flat_extra=inputs.direct_flat_extra if inputs.use_flat else 0.0,
        derived_increased_decrement=(
            inputs.direct_increased_decrement if inputs.use_increased_decrement else 0.0
        ),
        assessment_index=compute_assessment_index(table_rating),
        computed_survival_5yr=survival_5yr,
        computed_survival_10yr=survival_10yr,
        computed_le=final_le,
    )
    labels = {
        **_standard_text(policy, standard_le, standard_5yr, standard_10yr),
        **_modified_text(policy, inputs, assessment),
    }
    return SubstandardSolveResult(
        assessment=assessment,
        base_params=base_params,
        mortality_params=mortality_params,
        standard_le=standard_le,
        standard_survival_5yr=standard_5yr,
        standard_survival_10yr=standard_10yr,
        view_model=AssessmentResultViewModel(**labels),
    )


def terminal_substandard(policy: ABRPolicyData) -> SubstandardSolveResult:
    """Return the fixed 50% annual-mortality terminal assessment."""
    inputs = AssessmentInputs(rider_type="Terminal")
    base_params = build_base_mortality_params(policy, inputs)
    terminal_params = base_params
    term_engine = MortalityEngine(terminal_params)
    standard_le, standard_5yr, standard_10yr = _standard_projection(base_params)
    term_le = term_engine.compute_life_expectancy()
    assessment = MedicalAssessment(
        rider_type="Terminal",
        computed_survival_5yr=term_engine.compute_survival_probability(5),
        computed_survival_10yr=term_engine.compute_survival_probability(10),
        computed_le=term_le,
    )
    labels = {
        **_standard_text(policy, standard_le, standard_5yr, standard_10yr),
        "mod_survival_5yr": (
            f"{assessment.computed_survival_5yr:.4f}  "
            f"({assessment.computed_survival_5yr * 100:.2f}%)"
        ),
        "mod_survival_10yr": (
            f"{assessment.computed_survival_10yr:.4f}  "
            f"({assessment.computed_survival_10yr * 100:.2f}%)"
        ),
        "mod_le": f"{term_le:.1f} years (age {policy.attained_age + round(term_le)})",
        "table_rating": "Annual Mortality = 0.5000",
        "flat_extra": "\u2014",
    }
    return SubstandardSolveResult(
        assessment=assessment,
        base_params=base_params,
        mortality_params=terminal_params,
        standard_le=standard_le,
        standard_survival_5yr=standard_5yr,
        standard_survival_10yr=standard_10yr,
        view_model=AssessmentResultViewModel(**labels),
    )


def solve_substandard(
    policy: ABRPolicyData,
    inputs: AssessmentInputs,
) -> SubstandardSolveResult:
    """Solve an ABR assessment into mortality substandard values."""
    if inputs.rider_type == "Terminal":
        return terminal_substandard(policy)
    base_params = build_base_mortality_params(policy, inputs)
    table_rating, table_rating_5yr, table_rating_10yr, computed_le = _solve_primary_tables(
        base_params,
        inputs,
    )
    has_survival_solve = inputs.use_five_year or inputs.use_ten_year or inputs.use_le
    additional_tables, additional_flats = _rating_addons(policy, inputs, has_survival_solve)
    final_params = _mortality_params_from_components(
        base_params,
        inputs,
        table_rating,
        table_rating_5yr,
        table_rating_10yr,
        additional_tables,
        additional_flats,
    )
    return _build_result(
        policy,
        inputs,
        base_params,
        final_params,
        table_rating,
        table_rating_5yr,
        table_rating_10yr,
        computed_le,
    )
