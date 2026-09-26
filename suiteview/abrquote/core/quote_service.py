"""Core ABR quote calculation service.

The dedicated ABR window and automation entry point both gather plain
``ABRQuoteInputs`` and call :func:`calculate_abr_quote`.  The service owns the
calculation chain: interest lookup, mortality table, premium schedule, APV,
full/partial benefits, per-diem lookup and validation messages.  It does not
import or construct Qt widgets.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from ..models.abr_constants import MODAL_LABELS
from ..models.abr_data import ABRPolicyData, ABRQuoteResult, MedicalAssessment
from ..models.abr_database import get_abr_database, using_quote_database
from .abr_policy_service import PremiumScheduleResult, premium_schedule_for_quote
from .apv_engine import APVEngine
from .assessment_solver import assessment_to_mortality_params
from .mortality_engine import MortalityEngine
from .premium_calc import PremiumCalculator


@dataclass(frozen=True)
class ABRQuoteInputs:
    """All non-widget inputs required to calculate an ABR quote."""

    policy: ABRPolicyData
    assessment: MedicalAssessment
    quote_date: date
    min_face_amount: float
    interest_rate_override: float | None = None
    level_annual_premium: float | None = None
    loan_payoff: float = 0.0
    surrender_value: float | None = None


@dataclass(frozen=True)
class QuoteCalculationSnapshot:
    """Complete quote calculation output and audit-detail tables."""

    inputs: ABRQuoteInputs
    result: ABRQuoteResult
    mortality_detail: list[dict]
    apv_detail: list[dict]
    apv_summary: dict
    premium_schedule: PremiumScheduleResult
    partial_premium_breakdown: dict
    policy_info: str


def _interest_rate(quote_date: date, override: float | None) -> float:
    if override is not None:
        return override
    rate_info = get_abr_database().get_effective_interest_rate(
        quote_date.strftime("%Y-%m")
    )
    if rate_info is None:
        raise ValueError("No ABR interest rate data available.")
    return rate_info[1]


def build_quote_messages(snapshot: QuoteCalculationSnapshot) -> list[str]:
    """Build warning/review messages for a completed ABR quote."""
    policy = snapshot.inputs.policy
    assessment = snapshot.inputs.assessment
    result = snapshot.result
    messages: list[str] = []

    if result.full_accel_benefit > 100_000:
        messages.append(
            "Heads up! Payout exceeds $100,000 — "
            "Medical Directors should review."
        )
    if policy.face_amount > 2_000_000:
        messages.append(
            "Face amount over $2M — check the Data Page "
            "for the maximum acceleration amount."
        )
    if policy.face_amount < snapshot.inputs.min_face_amount:
        messages.append(
            f"Face amount (${policy.face_amount:,.0f}) is below the "
            f"minimum of ${snapshot.inputs.min_face_amount:,.0f} "
            "for partial acceleration."
        )
    if (
        assessment.life_expectancy_years <= 2.0
        and assessment.rider_type != "Terminal"
    ):
        messages.append(
            "Life expectancy is ≤ 2 years — confirm with "
            "Medical Directors if this qualifies for a Terminal rider."
        )
    if (
        assessment.rider_type == "Chronic"
        and result.per_diem_annual > 0
        and result.full_accel_benefit > result.per_diem_annual
    ):
        messages.append(
            f"Full acceleration (${result.full_accel_benefit:,.2f}) exceeds "
            f"the Chronic annual limit (${result.per_diem_annual:,.2f})."
        )
    return messages


def _calculate(inputs: ABRQuoteInputs) -> QuoteCalculationSnapshot:
    policy = inputs.policy
    assessment = inputs.assessment
    db = get_abr_database()
    annual_rate = _interest_rate(inputs.quote_date, inputs.interest_rate_override)
    is_terminal = assessment.rider_type == "Terminal"

    mort_params = assessment_to_mortality_params(policy, assessment)
    mort_engine = MortalityEngine(mort_params)
    mortality_detail = mort_engine.compute_detailed_table()
    monthly_qx = [row["qx_monthly"] for row in mortality_detail]

    premium_schedule = premium_schedule_for_quote(
        policy,
        inputs.quote_date,
        level_annual_premium=inputs.level_annual_premium,
    )
    prem_calc = PremiumCalculator(policy)
    projected_death_benefit = policy.default_death_benefit
    apv_engine = APVEngine(annual_rate, policy)
    apv_detail, apv_summary = apv_engine.compute_detailed_table(
        monthly_qx,
        premium_schedule.premium_schedule,
        is_terminal=is_terminal,
        death_benefit=projected_death_benefit,
    )

    admin_fee = db.get_admin_fee(policy.issue_state)
    policy.min_face_amount = inputs.min_face_amount
    surrender_value = (
        float(inputs.surrender_value)
        if inputs.surrender_value is not None
        else float(policy.surrender_value or 0.0)
    )
    full = apv_engine.compute_full_acceleration(
        admin_fee=admin_fee,
        apv_summary=apv_summary,
        loan_repayment=inputs.loan_payoff,
        surrender_value=surrender_value if policy.product_type in {"UL", "IUL", "ISWL"} else 0.0,
        eligible_death_benefit=projected_death_benefit,
    )
    partial = apv_engine.compute_partial_acceleration(
        full,
        min_face=inputs.min_face_amount,
        admin_fee=admin_fee,
    )
    min_face_prem = prem_calc.compute_min_face_premium(
        inputs.min_face_amount,
        policy_year=premium_schedule.start_year,
    )
    from dataclasses import replace as _replace

    reduced_policy = _replace(policy, face_amount=inputs.min_face_amount)
    partial_prem_breakdown = PremiumCalculator(reduced_policy).build_coverage_breakdown(
        policy_year=premium_schedule.start_year,
        prem_result=min_face_prem,
        modal_factor=premium_schedule.modal_factor,
    )
    per_diem = db.get_per_diem(inputs.quote_date.year)
    pd_daily = per_diem[0] if per_diem else 0.0
    pd_annual = per_diem[1] if per_diem else 0.0
    modal_label = MODAL_LABELS.get(policy.billing_mode, "")
    is_ul = policy.product_type in {"UL", "IUL", "ISWL"}

    result = ABRQuoteResult(
        full_eligible_db=full["eligible_db"],
        full_actuarial_discount=full["actuarial_discount"],
        full_admin_fee=full["admin_fee"],
        full_loan_repayment=full.get("loan_repayment", 0.0),
        full_accel_benefit=full["accelerated_benefit"],
        full_accelerated_benefit=full.get(
            "final_accelerated_benefit",
            full["accelerated_benefit"],
        ),
        full_benefit_ratio=full["benefit_ratio"],
        full_surrender_value=full.get("surrender_value", 0.0),
        partial_eligible_db=partial["eligible_db"],
        partial_actuarial_discount=partial["actuarial_discount"],
        partial_admin_fee=partial["admin_fee"],
        partial_loan_repayment=partial.get("loan_repayment", 0.0),
        partial_accel_benefit=partial["accelerated_benefit"],
        partial_accelerated_benefit=partial.get(
            "final_accelerated_benefit",
            partial["accelerated_benefit"],
        ),
        partial_benefit_ratio=partial["benefit_ratio"],
        partial_surrender_value=partial.get("surrender_value", 0.0),
        premium_before=(
            f"${policy.monthly_deduction:,.2f}"
            if is_ul
            else f"${premium_schedule.current_modal_premium:,.2f} {modal_label}"
        ),
        premium_after_full=0.0,
        premium_after_partial=(
            f"${min_face_prem.modal_premium:,.2f}"
            if is_ul
            else f"${min_face_prem.modal_premium:,.2f} {modal_label}"
        ),
        plan_description=PremiumCalculator.get_plan_description(policy.plan_code),
        abr_interest_rate=annual_rate,
        quote_date=inputs.quote_date,
        apv_fb=apv_summary.get("pvfb_adjusted", 0.0),
        apv_fp=apv_summary.get("pvfp", 0.0),
        apv_fd=0.0,
        per_diem_daily=pd_daily,
        per_diem_annual=pd_annual,
    )
    snapshot = QuoteCalculationSnapshot(
        inputs=inputs,
        result=result,
        mortality_detail=mortality_detail,
        apv_detail=apv_detail,
        apv_summary=apv_summary,
        premium_schedule=premium_schedule,
        partial_premium_breakdown=partial_prem_breakdown,
        policy_info=f"{policy.policy_number} — {policy.insured_name}",
    )
    result.messages = build_quote_messages(snapshot)
    return snapshot


def calculate_abr_quote(
    inputs: ABRQuoteInputs,
    rate_source=None,
) -> QuoteCalculationSnapshot:
    """Calculate an ABR quote using the supplied rate source when provided."""
    if rate_source is not None:
        with using_quote_database(rate_source):
            return _calculate(inputs)
    return _calculate(inputs)
