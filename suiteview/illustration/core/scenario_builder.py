from __future__ import annotations

from copy import deepcopy
from datetime import date
from math import isfinite
from dateutil.relativedelta import relativedelta

from suiteview.illustration.core.lapse import validate_no_lapse_years
from suiteview.illustration.models.input_set import (
    IllustrationInputSet,
    IllustrationScenario,
    InforceOverrideSet,
    IssueOverrideSet,
)
from suiteview.illustration.models.policy_data import CoverageSegment, IllustrationPolicyData


def build_illustration_scenario(
    base_policy: IllustrationPolicyData,
    inforce_overrides: InforceOverrideSet | None = None,
    future_inputs: IllustrationInputSet | None = None,
    run_from_issue: bool = False,
    issue_overrides: IssueOverrideSet | None = None,
) -> IllustrationScenario:
    """Clone the baseline policy, apply overrides, and select the projection start."""
    overrides = inforce_overrides or InforceOverrideSet()
    input_set = future_inputs or IllustrationInputSet()
    projectable_policy = deepcopy(base_policy)
    if run_from_issue:
        # Crediting assumptions are shared; valuation-date face, DBO, risk class
        # and balances must not leak into a separately edited new-business basis.
        assumptions = InforceOverrideSet(**{
            name: getattr(overrides, name)
            for name in (
                "current_interest_rate", "sweep_account_min", "iul_declared_rate",
                "iul_asset_charge_rate", "premium_allocations",
                "index_illustration_rates",
            )
        })
        apply_inforce_overrides(projectable_policy, assumptions)
        prepare_policy_for_issue_projection(projectable_policy, issue_overrides)
    else:
        apply_inforce_overrides(projectable_policy, overrides)
    return IllustrationScenario(
        base_policy=base_policy,
        projectable_policy=projectable_policy,
        inforce_overrides=overrides,
        future_inputs=input_set,
        run_from_issue=run_from_issue,
        issue_overrides=issue_overrides or IssueOverrideSet(),
    )


def issue_base_segments(policy: IllustrationPolicyData) -> list[CoverageSegment]:
    """Return recorded original-date base segments, without reconstructing history."""
    if policy.issue_date is None:
        raise ValueError("Run from Policy Issue requires a policy issue date.")
    segments = [
        segment for segment in policy.segments
        if segment.is_base and not segment.is_cola
        and segment.issue_date == policy.issue_date
    ]
    if not segments:
        raise ValueError("Run from Policy Issue requires recorded original issue-date base coverage.")
    return segments


def prepare_policy_for_issue_projection(
    policy: IllustrationPolicyData,
    issue_overrides: IssueOverrideSet | None = None,
) -> IllustrationPolicyData:
    """Rebase in place without database IO; bands resolve when rates are loaded."""
    segments = issue_base_segments(policy)
    overrides = issue_overrides or IssueOverrideSet()
    policy.issue_no_lapse_years = (
        validate_no_lapse_years(overrides.no_lapse_years)
        if overrides.no_lapse_years is not None else None)
    excluded_riders = set(overrides.excluded_rider_phases)
    excluded_benefits = {tuple(key) for key in overrides.excluded_benefit_keys}
    rider_phases = {r.coverage_phase for r in policy.riders}
    benefit_keys = {
        (b.coverage_phase, b.benefit_type, b.benefit_subtype)
        for b in policy.benefits
    }
    if excluded_riders - rider_phases:
        raise ValueError(f"Unknown rider exclusions: {excluded_riders - rider_phases}")
    if excluded_benefits - benefit_keys:
        raise ValueError(f"Unknown benefit exclusions: {excluded_benefits - benefit_keys}")
    faces = [
        s.original_face_amount if s.original_face_amount > 0 else s.face_amount
        for s in segments
    ]
    if any(not isfinite(face) or face <= 0 for face in faces):
        raise ValueError("Original issue-date base face amounts must be finite and positive.")
    original_total = sum(faces)
    total = overrides.face_amount if overrides.face_amount is not None else original_total
    if not isfinite(total) or total <= 0:
        raise ValueError("Issue face amount must be finite and positive.")
    dbo = overrides.db_option if overrides.db_option is not None else policy.db_option
    if dbo not in ("A", "B", "C"):
        raise ValueError(f"Invalid issue death-benefit option: {dbo!r}. Expected A, B or C.")

    policy.segments = segments
    assigned = 0.0
    for index, (segment, original_face) in enumerate(zip(segments, faces)):
        face = (
            total - assigned if index == len(segments) - 1
            else total * original_face / original_total
        )
        segment.face_amount = segment.original_face_amount = face
        segment.units = face / (segment.vpu or 1000.0)
        segment.status = "A"
        segment.months_since_terminated = 0
        segment.coi_renewal_rate = None
        assigned += face
    policy.face_amount = total
    policy.units = sum(segment.units for segment in segments)
    policy._issue_bands_initialized = False
    policy.db_option = dbo
    policy.riders = [
        r for r in policy.riders
        if r.issue_date == policy.issue_date and r.coverage_phase not in excluded_riders
    ]
    retained_phases = {s.coverage_phase for s in segments} | {
        r.coverage_phase for r in policy.riders
    }
    policy.benefits = [
        b for b in policy.benefits
        if b.issue_date == policy.issue_date and b.coverage_phase in retained_phases
        and (b.coverage_phase, b.benefit_type, b.benefit_subtype) not in excluded_benefits
    ]
    for rider in policy.riders:
        rider.status = "A"
        rider.is_active = True
        rider.units = rider.face_amount / (rider.vpu or 1000.0)
        rider.coi_rate = None
    for benefit in policy.benefits:
        benefit.is_active = True
        benefit.coi_rate = None
    ccv = next((b for b in policy.benefits if b.benefit_type == "A"), None)
    policy.ccv_active = ccv is not None
    policy.ccv_units = ccv.units if ccv else 0.0
    policy.ccv_ceased = False
    policy.ccv_coi_rate = None

    policy.run_from_issue = True
    if policy.illustration_date is None:
        policy.illustration_date = date.today()
    policy.valuation_date = policy.issue_date - relativedelta(months=1)
    policy.policy_year = 1
    policy.policy_month = 1
    policy.duration = 0
    policy.attained_age = policy.issue_age

    policy.account_value = 0.0
    policy.fund_values = {fund: 0.0 for fund in policy.fund_values}
    policy.swam = 0.0
    policy.glp = 0.0
    policy.gsp = 0.0
    policy.mtp = 0.0
    policy.ctp = 0.0
    policy.tamra_7pay_level = 0.0
    policy._debug_csv = 0.0
    policy.cost_basis = 0.0
    policy.system_coi_charge = 0.0
    policy.system_expense_charge = 0.0
    policy.system_other_charge = 0.0
    policy.system_monthly_deduction = 0.0
    policy.premiums_paid_to_date = 0.0
    policy.premiums_ytd = 0.0
    policy.withdrawals_to_date = 0.0
    policy.accumulated_glp = 0.0
    policy.accumulated_mtp = 0.0
    policy.regular_loan_principal = 0.0
    policy.regular_loan_accrued = 0.0
    policy.preferred_loan_principal = 0.0
    policy.preferred_loan_accrued = 0.0
    policy.variable_loan_principal = 0.0
    policy.variable_loan_accrued = 0.0
    policy.shadow_account_value = 0.0
    policy.deemed_cash_value = 0.0
    policy.is_mec = False
    policy.tamra_7pay_start_date = policy.issue_date
    policy.tamra_7pay_start_av = 0.0
    policy.tamra_7pay_cash_value = 0.0
    policy.tamra_7year_lowest_db = 0.0
    policy.tamra_7year_contributions = [0.0] * 7
    return policy


def apply_inforce_overrides(
    policy: IllustrationPolicyData,
    overrides: InforceOverrideSet,
) -> IllustrationPolicyData:
    """Apply simple valuation-date overrides in place.

    Structural month-by-month events stay outside this function. This layer only
    adjusts the starting inforce state before projection begins.
    """
    if overrides.account_value is not None:
        policy.account_value = overrides.account_value
    if overrides.db_option is not None:
        policy.db_option = overrides.db_option
    if overrides.rate_class is not None:
        policy.rate_class = overrides.rate_class
    if overrides.regular_loan_principal is not None:
        policy.regular_loan_principal = overrides.regular_loan_principal
    if overrides.regular_loan_accrued is not None:
        policy.regular_loan_accrued = overrides.regular_loan_accrued
    if overrides.preferred_loan_principal is not None:
        policy.preferred_loan_principal = overrides.preferred_loan_principal
    if overrides.preferred_loan_accrued is not None:
        policy.preferred_loan_accrued = overrides.preferred_loan_accrued
    if overrides.variable_loan_principal is not None:
        policy.variable_loan_principal = overrides.variable_loan_principal
    if overrides.variable_loan_accrued is not None:
        policy.variable_loan_accrued = overrides.variable_loan_accrued
    if overrides.current_interest_rate is not None:
        policy.current_interest_rate = overrides.current_interest_rate
    if overrides.sweep_account_min is not None:
        policy.sweep_account_min = overrides.sweep_account_min
    if overrides.iul_declared_rate is not None:
        policy.iul_declared_rate = overrides.iul_declared_rate
    if overrides.iul_asset_charge_rate is not None:
        policy.iul_asset_charge_rate = overrides.iul_asset_charge_rate
    if overrides.premium_allocations is not None:
        policy.premium_allocations = dict(overrides.premium_allocations)
    if overrides.index_illustration_rates is not None:
        policy.index_illustration_rates = dict(overrides.index_illustration_rates)

    if overrides.face_amount is not None:
        policy.face_amount = overrides.face_amount
        policy.units = overrides.face_amount / 1000.0 if overrides.face_amount else 0.0
        if len(policy.segments) == 1:
            policy.segments[0].face_amount = overrides.face_amount
            policy.segments[0].units = policy.units

    return policy