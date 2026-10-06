"""Build projectable illustration scenarios from loaded policy data.

Copy/mutation rules:

* `build_illustration_scenario` always deep-copies the loaded baseline before
  applying inforce, issue or rollback assumptions.
* Rollback overrides edit only the selected starting basis. They do not
  reconstruct future events, mutate the source `PolicyInformation`, or change
  shared plancode/rate data.
* Fund edits must retain exactly the captured fund IDs. Aggregate account value
  and individual fund balances are separate assumptions unless the caller edits
  both explicitly.
* Coverage, benefit and record edits are recorded in
  `starting_basis_assumptions`/`starting_record_fields` so reports can disclose
  what was manually supplied.
"""
from __future__ import annotations

from copy import deepcopy
from dataclasses import replace
from datetime import date
from math import isfinite
from dateutil.relativedelta import relativedelta

from suiteview.illustration.constants import DB_OPTION_RETURN_OF_PREMIUM
from suiteview.illustration.core.lapse import validate_no_lapse_years
from suiteview.illustration.core.skipped_coverage import skipped_option_c_note
from suiteview.illustration.core.withdrawal_handler import reset_ffl_withdrawal_state
from suiteview.illustration.models.input_set import (
    IllustrationInputSet,
    IllustrationScenario,
    InforceOverrideSet,
    IssueOverrideSet,
    RollbackOverrideSet,
    RECORD_FIELD_SPECS,
    record_number,
    validate_record_values,
    validate_tamra_contributions,
)
from suiteview.illustration.models.policy_data import CoverageSegment, IllustrationPolicyData


def build_illustration_scenario(
    base_policy: IllustrationPolicyData,
    inforce_overrides: InforceOverrideSet | None = None,
    future_inputs: IllustrationInputSet | None = None,
    run_from_issue: bool = False,
    issue_overrides: IssueOverrideSet | None = None,
    *,
    rollback_overrides: RollbackOverrideSet | None = None,
    allow_missing_shadow: bool = False,
) -> IllustrationScenario:
    """Clone the baseline policy, apply overrides, and select the projection start."""
    overrides = inforce_overrides or InforceOverrideSet()
    input_set = future_inputs or IllustrationInputSet()
    if rollback_overrides is not None and run_from_issue:
        raise ValueError("Value Rollback cannot be combined with New Business - From Issue.")
    current_basis = (
        rollback_overrides is not None
        and base_policy.rollback_date is None
        and rollback_overrides.valuation_date == base_policy.valuation_date
    )
    if rollback_overrides is not None and not current_basis:
        from suiteview.illustration.core.value_rollback import apply_value_rollback

        projectable_policy = apply_value_rollback(
            base_policy, rollback_overrides.valuation_date,
            allow_missing_shadow=allow_missing_shadow,
            shadow_account_value=rollback_overrides.shadow_account_value)
    else:
        projectable_policy = deepcopy(base_policy)
    captured_funds = {
        name: deepcopy(getattr(projectable_policy, name))
        for name in ("fund_values", "impaired_fund_values", "premium_allocations")
    }
    historical = projectable_policy.rollback_date is not None
    if run_from_issue or historical:
        # Crediting assumptions are shared; live face, DBO, risk class and
        # balances must not leak into issue or historical starting values.
        assumptions = InforceOverrideSet(**{
            name: getattr(overrides, name)
            for name in (
                "current_interest_rate", "sweep_account_min", "iul_declared_rate",
                "iul_asset_charge_rate", "premium_allocations",
                "index_illustration_rates", "deemed_cash_value",
            )
        })
        apply_inforce_overrides(projectable_policy, assumptions)
        if run_from_issue:
            prepare_policy_for_issue_projection(projectable_policy, issue_overrides)
        else:
            apply_rollback_overrides(
                projectable_policy, rollback_overrides, captured_funds=captured_funds)
    else:
        apply_inforce_overrides(projectable_policy, overrides)
        if rollback_overrides is not None:
            apply_rollback_overrides(
                projectable_policy, rollback_overrides, captured_funds=captured_funds)
    return IllustrationScenario(
        base_policy=base_policy,
        projectable_policy=projectable_policy,
        inforce_overrides=overrides,
        future_inputs=input_set,
        run_from_issue=run_from_issue,
        issue_overrides=issue_overrides or IssueOverrideSet(),
        rollback_overrides=deepcopy(rollback_overrides),
    )


def apply_rollback_overrides(
    policy: IllustrationPolicyData,
    overrides: RollbackOverrideSet,
    *,
    captured_funds: dict[str, dict[str, float]] | None = None,
) -> IllustrationPolicyData:
    """Edit the selected starting basis, not future events or shared plan data."""
    assumptions = policy.starting_basis_assumptions
    record_values = validate_record_values(overrides.record_values)
    contributions = _validated_tamra_override(overrides)
    fund_edits = _collect_fund_edits(policy, overrides, captured_funds)
    _apply_manual_amounts(policy, overrides, assumptions)
    _apply_record_values(policy, record_values, assumptions)
    _apply_tamra_contributions(policy, contributions, assumptions)
    _apply_fund_edits(policy, fund_edits, assumptions)
    _apply_coverage_amounts(policy, overrides, assumptions)
    _apply_benefit_amounts(policy, overrides, assumptions)
    _refresh_base_amounts(policy)
    _apply_rollback_db_option(policy, overrides, assumptions)
    _apply_manual_option_c_totals(policy, record_values, assumptions)
    return policy


def _validated_tamra_override(overrides: RollbackOverrideSet) -> list[float] | None:
    return (
        validate_tamra_contributions(overrides.tamra_7year_contributions)
        if overrides.tamra_7year_contributions is not None else None
    )


def _collect_fund_edits(
    policy: IllustrationPolicyData,
    overrides: RollbackOverrideSet,
    captured_funds: dict[str, dict[str, float]] | None,
) -> dict[str, dict[str, float]]:
    fund_edits = {}
    for name, label in (
        ("fund_values", "Unimpaired fund balances"),
        ("impaired_fund_values", "Impaired fund balances"),
        ("premium_allocations", "Premium allocations"),
    ):
        values = getattr(overrides, name)
        if values is None:
            continue
        source = captured_funds[name] if captured_funds is not None else getattr(policy, name)
        if (not isinstance(values, dict) or not source or set(values) != set(source)):
            raise ValueError(
                f"{label} must retain every existing captured fund ID; "
                "fund IDs cannot be added, changed or removed.")
        normalized = {fund: record_number(value, f"{label} {fund}")
                      for fund, value in values.items()}
        if name == "premium_allocations" and (
            any(not 0 <= value <= 1 for value in normalized.values())
            or abs(sum(normalized.values()) - 1.0) > 1e-8
        ):
            raise ValueError("Premium allocations must be fractions totaling 100%.")
        fund_edits[name] = normalized
    return fund_edits


def _apply_manual_amounts(policy, overrides, assumptions: list[str]) -> None:
    for name, label in (
        ("account_value", "Account value"),
        ("shadow_account_value", "Shadow account value"),
    ):
        amount = getattr(overrides, name)
        if amount is None:
            continue
        if (isinstance(amount, bool) or not isinstance(amount, (int, float))
                or not isfinite(amount)):
            raise ValueError(f"{label} must be a finite numeric amount.")
        setattr(policy, name, float(amount))
        assumptions.append(
            f"{label} was entered manually as {amount:,.2f}; "
            "this is a starting-basis assumption, not a recovered CyberLife value.")
        if name == "account_value":
            policy.starting_account_value_is_manual = True
            if policy.fund_values or policy.impaired_fund_values:
                assumptions.append(
                    "Manual account value is a total-only assumption; captured individual "
                    "fund balances are retained independently, not reconciled to that total.")


def _apply_record_values(policy, record_values: dict, assumptions: list[str]) -> None:
    for name, value in record_values.items():
        spec = RECORD_FIELD_SPECS[name]
        setattr(policy, name, deepcopy(value))
        if name not in policy.starting_record_fields:
            policy.starting_record_fields.append(name)
        assumptions.append(f"{spec.label} was entered manually as {_record_value_text(spec, value)}.")
    if "premium_pay_status_code" in record_values:
        assumptions.append(
            "Premium-paying status is an explicit record assumption only; coverage activity, "
            "waiver rules and transaction history have not been reconstructed.")
    if "glp" in record_values:
        policy.glp_is_known = True
    if "withdrawals_to_date" in record_values:
        # An entered total is the NET withdrawals: no recorded withdrawal fee is
        # subtracted again for the option C death benefit.
        policy.inforce_withdrawal_fees = 0.0
        assumptions.append(
            "Withdrawals to date is taken as net of withdrawal fees for the return-of-premium "
            "(option C) death benefit.")
    if "tamra_7pay_cash_value" in record_values:
        policy.tamra_7pay_start_av = policy.tamra_7pay_cash_value


def _apply_manual_option_c_totals(policy, record_values: dict, assumptions: list[str]) -> None:
    """Entered premiums/withdrawals totals are the full option C basis: the recorded
    exclusion of pre-reinstatement premiums no longer reconciles with them. The periods
    stay (they still shift the EPU schedule)."""
    if not {"premiums_paid_to_date", "withdrawals_to_date"} & set(record_values):
        return
    latest = policy.latest_skipped_coverage_period
    if latest is None or latest.option_c_excluded_amount == 0.0:
        return
    policy.skipped_coverage_periods = [
        replace(period, option_c_excluded_amount=0.0) for period in policy.skipped_coverage_periods]
    if policy.db_option == DB_OPTION_RETURN_OF_PREMIUM:
        assumptions.append(skipped_option_c_note(latest))


def _record_value_text(spec, value) -> str:
    if spec.kind == "date":
        return value.isoformat() if value is not None else "Not set"
    if spec.kind == "rate":
        return f"{value:.4%}"
    if spec.kind == "status":
        from suiteview.polview.models.cl_polrec.policy_translations import PREMIUM_PAY_STATUS_CODES
        return f"{value} - {PREMIUM_PAY_STATUS_CODES[value]}"
    return str(value) if spec.kind == "bool" else f"{value:,.2f}"


def _apply_tamra_contributions(policy, contributions, assumptions: list[str]) -> None:
    if contributions is None:
        return
    policy.tamra_7year_contributions = contributions
    if "tamra_7year_contributions" not in policy.starting_record_fields:
        policy.starting_record_fields.append("tamra_7year_contributions")
    assumptions.append(
        "7-pay contributions were entered manually as "
        + ", ".join(f"year {index + 1}: {amount:,.2f}"
                    for index, amount in enumerate(contributions)) + ".")


def _apply_fund_edits(policy, fund_edits: dict, assumptions: list[str]) -> None:
    for name, values in fund_edits.items():
        setattr(policy, name, values)
        if name == "fund_values":
            # Edited balances replace the record's open index segments; each
            # edited index fund opens as one segment under segment crediting.
            policy.fund_segments = []
        assumptions.append(
            f"{name.replace('_', ' ').capitalize()} entered manually: "
            + ", ".join(
                f"{fund}={value:.4%}" if name == "premium_allocations"
                else f"{fund}={value:,.2f}" for fund, value in values.items()) + ".")
    if any(name in fund_edits for name in ("fund_values", "impaired_fund_values")):
        assumptions.append(
            "Aggregate account value remains independent of edited fund balances; "
            "set Account Value separately to change the projection's starting total. "
            "Impaired fund edits do not change the separately editable loan principal.")


def _apply_coverage_amounts(policy, overrides, assumptions: list[str]) -> None:
    faces = overrides.coverage_amounts
    coverages = [*policy.segments, *policy.riders]
    segments = {segment.coverage_phase: segment for segment in coverages}
    if len(segments) != len(coverages):
        raise ValueError("Value Rollback requires unique coverage phase numbers.")
    if set(faces) - segments.keys():
        raise ValueError(f"Unknown rollback coverage phases: {set(faces) - segments.keys()}")
    for phase, face in faces.items():
        segment = segments[phase]
        _validate_amount(face, "Rollback specified amounts must be finite and nonnegative.")
        if not isfinite(segment.vpu) or segment.vpu <= 0:
            raise ValueError(f"Coverage {phase} requires a positive value per unit.")
        segment.face_amount = face
        segment.units = face / segment.vpu
        if hasattr(segment, "coi_renewal_rate"):
            segment.coi_renewal_rate = None
        else:
            segment.coi_rate = None
    if faces:
        policy.starting_coverage_amounts_are_manual = True
        assumptions.append("Coverage and/or benefit amounts were entered manually as starting-basis assumptions.")


def _apply_benefit_amounts(policy, overrides, assumptions: list[str]) -> None:
    benefits = {
        (benefit.coverage_phase, benefit.benefit_type, benefit.benefit_subtype): benefit
        for benefit in policy.benefits
    }
    if len(benefits) != len(policy.benefits):
        raise ValueError("Value Rollback requires unique benefit keys.")
    if set(overrides.benefit_amounts) - benefits.keys():
        raise ValueError(f"Unknown rollback benefits: {set(overrides.benefit_amounts) - benefits.keys()}")
    for key, amount in overrides.benefit_amounts.items():
        benefit = benefits[key]
        _validate_amount(amount, "Rollback benefit amounts must be finite and nonnegative.")
        if not isfinite(benefit.vpu) or benefit.vpu <= 0:
            raise ValueError(f"Benefit {key} requires a positive value per unit.")
        benefit.benefit_amount = amount
        benefit.units = amount / benefit.vpu
        benefit.coi_rate = None
        if benefit.benefit_type == "A":
            policy.ccv_units = benefit.units
    if overrides.benefit_amounts:
        assumptions.append("Coverage and/or benefit amounts were entered manually as starting-basis assumptions.")


def _validate_amount(value, message: str) -> None:
    if (isinstance(value, bool) or not isinstance(value, (int, float))
            or not isfinite(value) or value < 0):
        raise ValueError(message)


def _refresh_base_amounts(policy: IllustrationPolicyData) -> None:
    base_segments = [segment for segment in policy.segments if segment.is_base]
    total = sum(segment.face_amount for segment in base_segments)
    if not isfinite(total) or total <= 0:
        raise ValueError("Rollback total base specified amount must be finite and positive.")
    policy.face_amount = total
    policy.units = sum(segment.units for segment in base_segments)


def _apply_rollback_db_option(policy, overrides, assumptions: list[str]) -> None:
    if overrides.db_option is None:
        return
    if overrides.db_option not in ("A", "B", "C"):
        raise ValueError("Rollback death-benefit option must be A, B or C.")
    policy.db_option = overrides.db_option
    assumptions.append(
        f"Death-benefit option {policy.db_option} was selected manually as a starting-basis assumption.")
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


def _issue_exclusions(
    policy: IllustrationPolicyData,
    overrides: IssueOverrideSet,
) -> tuple[set[int], set[tuple]]:
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
    return excluded_riders, excluded_benefits


def _original_issue_faces(segments: list[CoverageSegment]) -> list[float]:
    faces = [
        s.original_face_amount if s.original_face_amount > 0 else s.face_amount
        for s in segments
    ]
    if any(not isfinite(face) or face <= 0 for face in faces):
        raise ValueError("Original issue-date base face amounts must be finite and positive.")
    return faces


def _issue_total_and_dbo(
    policy: IllustrationPolicyData,
    overrides: IssueOverrideSet,
    original_total: float,
) -> tuple[float, str]:
    total = overrides.face_amount if overrides.face_amount is not None else original_total
    if not isfinite(total) or total <= 0:
        raise ValueError("Issue face amount must be finite and positive.")
    dbo = overrides.db_option if overrides.db_option is not None else policy.db_option
    if dbo not in ("A", "B", "C"):
        raise ValueError(f"Invalid issue death-benefit option: {dbo!r}. Expected A, B or C.")
    return total, dbo


def _rebase_issue_segments(
    policy: IllustrationPolicyData,
    segments: list[CoverageSegment],
    faces: list[float],
    total: float,
) -> None:
    policy.segments = segments
    original_total = sum(faces)
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


def _retain_issue_riders_and_benefits(
    policy: IllustrationPolicyData,
    segments: list[CoverageSegment],
    excluded_riders: set[int],
    excluded_benefits: set[tuple],
) -> None:
    policy.riders = [
        r for r in policy.riders
        if r.issue_date == policy.issue_date and r.coverage_phase not in excluded_riders
    ]
    retained_phases = {s.coverage_phase for s in segments} | {
        r.coverage_phase for r in policy.riders
    }
    policy.benefits = [
        b for b in policy.benefits
        if b.issue_date == policy.issue_date
        and b.coverage_phase in retained_phases
        and (b.coverage_phase, b.benefit_type, b.benefit_subtype) not in excluded_benefits
    ]


def _activate_issue_coverages(policy: IllustrationPolicyData) -> None:
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


def _set_issue_projection_dates(policy: IllustrationPolicyData) -> None:
    policy.run_from_issue = True
    if policy.illustration_date is None:
        policy.illustration_date = date.today()
    policy.valuation_date = policy.issue_date - relativedelta(months=1)
    policy.policy_year = 1
    policy.policy_month = 1
    policy.duration = 0
    policy.attained_age = policy.issue_age


def _reset_issue_values(policy: IllustrationPolicyData) -> None:
    # Joint survivor MTP/CTP are VP/MS values that cannot be recalculated from
    # rate tables at issue, so the record targets stay.
    held_targets = ("mtp", "ctp") if policy.is_joint_survivor else ()
    for name in (
        "account_value", "swam", "glp", "gsp", "mtp", "ctp",
        "tamra_7pay_level", "_debug_csv", "cost_basis",
        "system_coi_charge", "system_expense_charge", "system_other_charge",
        "system_monthly_deduction", "premiums_paid_to_date", "premiums_ytd",
        "withdrawals_to_date", "inforce_withdrawal_fees", "accumulated_glp", "accumulated_mtp",
        "regular_loan_principal", "regular_loan_accrued",
        "preferred_loan_principal", "preferred_loan_accrued",
        "variable_loan_principal", "variable_loan_accrued",
        "shadow_account_value", "deemed_cash_value", "tamra_7pay_start_av",
        "tamra_7pay_cash_value", "tamra_7year_lowest_db",
    ):
        if name not in held_targets:
            setattr(policy, name, 0.0)
    policy.fund_values = {fund: 0.0 for fund in policy.fund_values}
    policy.impaired_fund_values = {fund: 0.0 for fund in policy.impaired_fund_values}
    policy.is_mec = False
    policy.tamra_7pay_start_date = policy.issue_date
    policy.tamra_7year_contributions = [0.0] * 7
    policy.skipped_coverage_periods = []
    reset_ffl_withdrawal_state(policy)


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
    excluded_riders, excluded_benefits = _issue_exclusions(policy, overrides)
    faces = _original_issue_faces(segments)
    total, dbo = _issue_total_and_dbo(policy, overrides, sum(faces))
    _rebase_issue_segments(policy, segments, faces, total)
    policy.db_option = dbo
    _retain_issue_riders_and_benefits(
        policy, segments, excluded_riders, excluded_benefits)
    _activate_issue_coverages(policy)
    _set_issue_projection_dates(policy)
    _reset_issue_values(policy)
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
    # The DCV is never in DB2: the entered value (or None — unknown) is always
    # the starting DCV, so a stale policy/snapshot value can never be reused.
    policy.deemed_cash_value = overrides.deemed_cash_value

    if overrides.face_amount is not None:
        policy.face_amount = overrides.face_amount
        policy.units = overrides.face_amount / 1000.0 if overrides.face_amount else 0.0
        if len(policy.segments) == 1:
            policy.segments[0].face_amount = overrides.face_amount
            policy.segments[0].units = policy.units

    return policy