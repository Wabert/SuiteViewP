"""Shared saved-case materialization for Compare and Regression."""
from __future__ import annotations

from copy import deepcopy

from suiteview.illustration.core.compare_runner import ScenarioSpec
from suiteview.illustration.core.scenario_builder import build_illustration_scenario
from suiteview.illustration.models.app_settings import get_illustration_settings
from suiteview.illustration.models.case_store import CaseStoreError, SavedCase


def build_spec_from_tab(label: str, inputs_tab, policy_data) -> ScenarioSpec:
    """Read the same complete input surface used by Run Values."""
    scenario = build_illustration_scenario(
        policy_data,
        inforce_overrides=inputs_tab.export_inforce_overrides(),
        future_inputs=inputs_tab.export_input_set(),
    )
    return ScenarioSpec(
        label=label,
        scenario=scenario,
        months=inputs_tab.projection_months(scenario.projectable_policy),
        options=inputs_tab.export_options(),
        stop_on_lapse=inputs_tab.stop_on_lapse_enabled(),
        lumpsum_to_next=inputs_tab.lumpsum_to_next_enabled(),
        max_level=inputs_tab.max_level_request(),
        min_level=inputs_tab.min_level_request(),
        shadow_level=inputs_tab.shadow_level_request(),
        payoff_requests=inputs_tab.loan_payoff_requests(),
    )


def materialize_saved_case(
    case: SavedCase,
    *,
    warning_prefix: str = "",
    strict: bool = False,
    spec_builder=build_spec_from_tab,
) -> ScenarioSpec:
    """Build a frozen schema-v2 case without live DB access.

    The throwaway Inputs tab sees the complete premium-type surface regardless
    of the current session preference. Signals are blocked while the temporary
    preference is changed, so open user tabs are not modified.
    """
    if getattr(case, "schema_version", 2) != 2 or case.policy_snapshot is None:
        raise CaseStoreError(
            f"Case '{case.name}' has no frozen schema-v2 policy snapshot.")

    from .inputs_tab import IllustrationInputsTab

    settings = get_illustration_settings()
    previous_setting = settings.additional_premium_types
    previously_blocked = settings.blockSignals(True)
    tab = None
    try:
        settings.set_additional_premium_types(True)
        tab = IllustrationInputsTab()
        snapshot = deepcopy(case.policy_snapshot)
        tab.load_data_from_policy(
            snapshot,
            has_shadow=bool(getattr(snapshot, "has_shadow_account", False)),
            shadow_ceased=bool(getattr(snapshot, "ccv_ceased", False)),
        )
        warnings = tab.apply_case_inputs(case.inputs)
        if strict and warnings:
            raise CaseStoreError(
                f"Case '{case.name}' could not be reproduced exactly:\n"
                + "\n".join(warnings)
            )
        spec = spec_builder(case.name, tab, snapshot)
        spec.apply_warnings = [
            f"{warning_prefix}{warning}" for warning in warnings
        ]
        return spec
    finally:
        if tab is not None:
            tab.deleteLater()
        settings.set_additional_premium_types(previous_setting)
        settings.blockSignals(previously_blocked)
