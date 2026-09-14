import json
import os
from datetime import date
from types import SimpleNamespace

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtWidgets import QApplication

from suiteview.illustration.core import calc_engine
from suiteview.illustration.core.bonus_rates import BonusConfig
from suiteview.illustration.core.lapse import (
    default_issue_no_lapse_years, lapse_value_for_month,
)
from suiteview.illustration.core.rate_loader import IllustrationRates
from suiteview.illustration.core.report_builder import issue_output_basis, issue_output_conditions
from suiteview.illustration.core.scenario_builder import build_illustration_scenario
from suiteview.illustration.core.target_premium import TargetPremiumResult
from suiteview.illustration.models.input_set import (
    IllustrationInputSet, IllustrationOptions, IssueOverrideSet,
    ScheduledTransaction, TransactionKind,
)
from suiteview.illustration.models.plancode_config import PlancodeConfig
from suiteview.illustration.models.policy_data import CoverageSegment, IllustrationPolicyData


_QT_APP = None


def _policy():
    issue = date(2010, 3, 31)
    return IllustrationPolicyData(
        policy_number="ISSUE-TEST", plancode="1U135D00", issue_date=issue,
        issue_age=40, attained_age=56, policy_year=17, policy_month=1,
        duration=193, valuation_date=date(2026, 3, 31), face_amount=100_000,
        segments=[CoverageSegment(
            issue_date=issue, issue_age=40, face_amount=100_000,
            original_face_amount=100_000, units=100)],
    )


@pytest.fixture
def engine_basis(monkeypatch):
    config = PlancodeConfig(
        plancode="1U135D00", snet_period=0, lapse_value="SV",
        epu_code="0", mfee="0", corridor_code=None,
    )
    monkeypatch.setattr(calc_engine, "load_plancode", lambda _: config)
    monkeypatch.setattr(calc_engine, "compute_target_premiums",
                        lambda *args, **kwargs: TargetPremiumResult())
    monkeypatch.setattr(calc_engine, "_solve_guideline_state",
                        lambda *args, **kwargs: SimpleNamespace(glp=10_000, gsp=20_000, seven_pay=30_000))
    monkeypatch.setattr(calc_engine, "_calculate_surrender_charge",
                        lambda *args, **kwargs: (0.0, 1000.0, {}, {}))
    return config


def _project(years, *, premium=1.0, options=None, months=13):
    policy = build_illustration_scenario(
        _policy(), run_from_issue=True,
        issue_overrides=IssueOverrideSet(no_lapse_years=years),
    ).projectable_policy
    states = calc_engine.IllustrationEngine().project(
        policy, months=months, options=options,
        future_inputs=IllustrationInputSet(scheduled_transactions=[
            ScheduledTransaction(TransactionKind.PREMIUM, policy_year=1, amount=premium, mode="M")]),
        rates_override=IllustrationRates(), bonus_override=BonusConfig(),
    )
    return policy, states


@pytest.mark.parametrize("guaranteed", [False, True])
def test_negative_surrender_value_survives_period_then_normal_lapse_resumes(engine_basis, guaranteed):
    options = IllustrationOptions(guaranteed_assumption=guaranteed)
    _, states = _project(0.5, options=options)
    assert len(states) == 8  # opening + six protected months + terminal lapse
    assert all(not state.lapsed for state in states[1:7])
    assert all(state.surrender_value < 0 for state in states[1:7])
    assert all(state.av_end_of_month > 0 for state in states[1:7])
    assert states[-1].duration == 7 and states[-1].lapsed


def test_zero_override_retains_normal_first_month_sv_lapse(engine_basis):
    _, states = _project(0)
    assert len(states) == 2
    assert states[-1].lapsed and states[-1].duration == 1


def test_period_does_not_protect_unfunded_account_value(engine_basis):
    _, states = _project(100, premium=0)
    assert len(states) == 2
    assert states[-1].lapsed


def test_billable_to_md_probe_uses_the_same_temporary_av_basis(engine_basis):
    _, states = _project(
        0.5, options=IllustrationOptions(billable_to_md_windows=[(1, None)]))
    assert all(not state.billable_md_switched for state in states[1:7])
    assert states[7].billable_md_switched


def test_default_period_uses_plan_safety_net_and_does_not_modify_config(engine_basis):
    engine_basis.snet_period = 2
    policy, states = _project(None, months=25)
    assert policy.issue_no_lapse_years == 2
    assert not states[24].lapsed and states[25].lapsed
    assert engine_basis.snet_period == 2 and engine_basis.lapse_value == "SV"


def test_table_based_default_uses_recorded_minimum_premium_cease_date():
    policy = _policy()
    policy.map_cease_date = date(2015, 3, 30)
    config = PlancodeConfig(snet_period=0)
    assert default_issue_no_lapse_years(policy, config) == 5
    assert default_issue_no_lapse_years(policy, PlancodeConfig(snet_period=10)) == 5
    policy.map_cease_date = date(2011, 2, 28)
    assert default_issue_no_lapse_years(policy, config) == 1
    policy.map_cease_date = None
    assert default_issue_no_lapse_years(policy, config) == 0


def test_inforce_ignores_issue_period_and_fractional_years_round_to_months():
    config = PlancodeConfig(snet_period=0, lapse_value="SV")
    policy = _policy()
    policy.issue_no_lapse_years = 100
    assert lapse_value_for_month(policy, config, 1) == "SV"
    policy.run_from_issue = True
    policy.issue_no_lapse_years = 1 / 12
    assert lapse_value_for_month(policy, config, 1) == "AV"
    assert lapse_value_for_month(policy, config, 2) == "SV"
    assert lapse_value_for_month(policy, config, 0) == "SV"


@pytest.mark.parametrize("years", [-1, float("inf"), float("nan"), "5", True])
def test_invalid_period_is_rejected(years):
    with pytest.raises(ValueError, match="No Lapse Period"):
        build_illustration_scenario(
            _policy(), run_from_issue=True,
            issue_overrides=IssueOverrideSet(no_lapse_years=years))


def test_period_round_trips_through_saved_inputs_and_compare_scenario(monkeypatch):
    global _QT_APP
    _QT_APP = QApplication.instance() or QApplication([])
    from suiteview.illustration.ui import issue_conditions
    from suiteview.illustration.ui.inputs_tab import IllustrationInputsTab
    from suiteview.illustration.ui.saved_case_scenario import build_spec_from_tab

    monkeypatch.setattr(issue_conditions, "load_plancode",
                        lambda _: PlancodeConfig(snet_period=7))
    tab = IllustrationInputsTab()
    tab.load_data_from_policy(_policy())
    assert tab.issue_conditions.no_lapse_years_edit.value() == 7
    tab.run_from_issue_btn.setChecked(True)
    tab.issue_conditions.no_lapse_years_edit.setValue(7.5)
    state = json.loads(json.dumps(tab.capture_case_inputs()))
    restored = IllustrationInputsTab()
    restored.load_data_from_policy(_policy())
    assert restored.apply_case_inputs(state) == []
    spec = build_spec_from_tab("Issue", restored, _policy())
    assert spec.scenario.projectable_policy.issue_no_lapse_years == 7.5
    assert "7.5 YEARS" in "\n".join(issue_output_basis(spec.scenario.projectable_policy))
    assert ("No Lapse Period", "7.5 YEARS") in issue_output_conditions(spec.scenario.projectable_policy)
    restored.run_from_issue_btn.setChecked(False)
    assert restored.export_issue_overrides() is None
    restored.run_from_issue_btn.setChecked(True)
    assert restored.issue_conditions.no_lapse_years_edit.value() == 7.5
    state["issue_conditions"]["no_lapse_years"] = -1
    with pytest.raises(ValueError, match="No Lapse Period"):
        restored.apply_case_inputs(state)
