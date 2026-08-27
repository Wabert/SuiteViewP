from __future__ import annotations

from copy import deepcopy
from datetime import date
from dateutil.relativedelta import relativedelta

from suiteview.illustration.models.input_set import (
    IllustrationInputSet,
    IllustrationScenario,
    InforceOverrideSet,
)
from suiteview.illustration.models.policy_data import IllustrationPolicyData


def build_illustration_scenario(
    base_policy: IllustrationPolicyData,
    inforce_overrides: InforceOverrideSet | None = None,
    future_inputs: IllustrationInputSet | None = None,
    run_from_issue: bool = False,
) -> IllustrationScenario:
    """Clone the baseline policy, apply overrides, and select the projection start."""
    overrides = inforce_overrides or InforceOverrideSet()
    input_set = future_inputs or IllustrationInputSet()
    projectable_policy = deepcopy(base_policy)
    apply_inforce_overrides(projectable_policy, overrides)
    if run_from_issue:
        prepare_policy_for_issue_projection(projectable_policy)
    return IllustrationScenario(
        base_policy=base_policy,
        projectable_policy=projectable_policy,
        inforce_overrides=overrides,
        future_inputs=input_set,
        run_from_issue=run_from_issue,
    )


def prepare_policy_for_issue_projection(
    policy: IllustrationPolicyData,
) -> IllustrationPolicyData:
    """Rebase a current policy snapshot to a true pre-issue opening state."""
    if policy.issue_date is None:
        raise ValueError("Run from Policy Issue requires a policy issue date.")

    policy.run_from_issue = True
    policy.illustration_date = date.today()
    policy.valuation_date = policy.issue_date - relativedelta(months=1)
    policy.policy_year = 1
    policy.policy_month = 1
    policy.duration = 0
    policy.attained_age = policy.issue_age

    policy.account_value = 0.0
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