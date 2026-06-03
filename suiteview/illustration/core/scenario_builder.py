from __future__ import annotations

from copy import deepcopy

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
) -> IllustrationScenario:
    """Clone the baseline policy, apply valuation-date overrides, and bundle future inputs."""
    overrides = inforce_overrides or InforceOverrideSet()
    input_set = future_inputs or IllustrationInputSet()
    projectable_policy = deepcopy(base_policy)
    apply_inforce_overrides(projectable_policy, overrides)
    return IllustrationScenario(
        base_policy=base_policy,
        projectable_policy=projectable_policy,
        inforce_overrides=overrides,
        future_inputs=input_set,
    )


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

    if overrides.face_amount is not None:
        policy.face_amount = overrides.face_amount
        policy.units = overrides.face_amount / 1000.0 if overrides.face_amount else 0.0
        if len(policy.segments) == 1:
            policy.segments[0].face_amount = overrides.face_amount
            policy.segments[0].units = policy.units

    return policy