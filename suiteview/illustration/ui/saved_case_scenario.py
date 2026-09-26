"""Shared saved-case materialization for Compare and Regression."""
from __future__ import annotations

from copy import deepcopy

from suiteview.illustration.core.compare_runner import ScenarioSpec
from suiteview.illustration.core.run_input_compiler import compile_input_set, compile_options
from suiteview.illustration.core.scenario_builder import build_illustration_scenario
from suiteview.illustration.models.app_settings import get_illustration_settings
from suiteview.illustration.models.case_store import CaseStoreError, SavedCase
from suiteview.ui.signals import muted_signals


def build_spec_from_tab(label: str, inputs_tab, policy_data) -> ScenarioSpec:
    """Read the same complete input surface used by Run Values."""
    draft = inputs_tab.read_draft()
    scenario = build_illustration_scenario(
        policy_data,
        inforce_overrides=draft.inforce_overrides,
        future_inputs=compile_input_set(draft),
        run_from_issue=draft.controls.run_from_issue,
        issue_overrides=draft.issue_overrides,
        rollback_overrides=draft.rollback_overrides,
    )
    return ScenarioSpec(
        label=label,
        scenario=scenario,
        months=inputs_tab.projection_months(scenario.projectable_policy),
        options=compile_options(draft),
        stop_on_lapse=draft.controls.stop_on_lapse,
        lumpsum_to_next=draft.lumpsum_to_next,
        max_level=draft.max_level,
        min_level=draft.min_level,
        shadow_level=draft.shadow_level,
        payoff_requests=list(draft.loan_payoffs),
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
    tab = None
    try:
        with muted_signals(settings):
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
        with muted_signals(settings):
            settings.set_additional_premium_types(previous_setting)
