import os
import json
import pytest
from datetime import date, datetime
from types import SimpleNamespace

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtWidgets import QApplication

from suiteview.illustration.core import calc_engine
from suiteview.illustration.core.bonus_rates import BonusConfig
from suiteview.illustration.core.calc_engine import IllustrationEngine
from suiteview.illustration.core.scenario_builder import build_illustration_scenario
from suiteview.illustration.core.target_premium import TargetPremiumResult
from suiteview.illustration.models.input_set import (
    IllustrationInputSet,
    ScheduledTransaction,
    TransactionKind,
)
from suiteview.illustration.models.plancode_config import PlancodeConfig
from suiteview.illustration.models.policy_data import (
    BenefitInfo,
    CoverageSegment,
    IllustrationPolicyData,
    RiderInfo,
)
from suiteview.illustration.core.rate_loader import IllustrationRates
from suiteview.illustration.ui.inputs_tab import IllustrationInputsTab


_QT_APP = None


def _app():
    global _QT_APP
    _QT_APP = QApplication.instance() or QApplication([])
    return _QT_APP


def _current_policy():
    return IllustrationPolicyData(
        policy_number="U1234567",
        plancode="1U135D00",
        issue_date=date(2010, 5, 15),
        issue_age=40,
        attained_age=56,
        valuation_date=date(2026, 5, 15),
        illustration_date=date(2026, 8, 27),
        policy_year=17,
        policy_month=1,
        duration=193,
        maturity_age=121,
        face_amount=100_000.0,
        account_value=25_000.0,
        cost_basis=18_000.0,
        premiums_paid_to_date=30_000.0,
        premiums_ytd=1_200.0,
        accumulated_glp=40_000.0,
        accumulated_mtp=22_000.0,
        regular_loan_principal=5_000.0,
        withdrawals_to_date=2_000.0,
        is_mec=True,
        segments=[
            CoverageSegment(
                coverage_phase=1,
                issue_date=date(2010, 5, 15),
                issue_age=40,
                face_amount=100_000.0,
                original_face_amount=100_000.0,
                units=100.0,
            )
        ],
    )


def test_issue_scenario_resets_inforce_balances_without_mutating_policy_tab_data():
    current = _current_policy()

    scenario = build_illustration_scenario(current, run_from_issue=True)
    projected = scenario.projectable_policy

    assert scenario.run_from_issue is True
    assert current.account_value == 25_000.0
    assert current.valuation_date == date(2026, 5, 15)
    assert projected.run_from_issue is True
    assert projected.valuation_date == date(2010, 4, 15)
    assert projected.duration == 0
    assert projected.account_value == 0.0
    assert projected.cost_basis == 0.0
    assert projected.premiums_paid_to_date == 0.0
    assert projected.accumulated_glp == 0.0
    assert projected.regular_loan_principal == 0.0
    assert projected.withdrawals_to_date == 0.0
    assert projected.is_mec is False


def test_issue_mode_runs_full_first_month_on_policy_issue_date(monkeypatch):
    scenario = build_illustration_scenario(_current_policy(), run_from_issue=True)
    policy = scenario.projectable_policy
    config = PlancodeConfig(
        plancode="TEST", epu_code="0", mfee="0", corridor_code=None)
    monkeypatch.setattr(calc_engine, "load_plancode", lambda _plan: config)
    monkeypatch.setattr(
        calc_engine,
        "compute_target_premiums",
        lambda *_args, **_kwargs: TargetPremiumResult(),
    )
    monkeypatch.setattr(
        calc_engine,
        "_solve_guideline_state",
        lambda *_args, **_kwargs: SimpleNamespace(
            glp=1_200.0, gsp=2_400.0, seven_pay=3_600.0),
    )
    inputs = IllustrationInputSet(scheduled_transactions=[
        ScheduledTransaction(
            kind=TransactionKind.PREMIUM,
            policy_year=1,
            amount=100.0,
            mode="M",
        )
    ])

    states = IllustrationEngine().project(
        policy,
        months=1,
        future_inputs=inputs,
        stop_on_lapse=False,
        rates_override=IllustrationRates(),
        bonus_override=BonusConfig(),
    )

    assert states[0].duration == 0
    assert states[0].date == date(2010, 4, 15)
    assert states[1].duration == 1
    assert states[1].date == policy.issue_date
    assert states[1].policy_year == 1
    assert states[1].policy_month == 1
    assert states[1].gross_premium == 100.0
    assert states[1].premiums_to_date == 100.0


def test_issue_toggle_round_trips_and_recolors_internal_controls():
    _app()
    tab = IllustrationInputsTab()
    tab.load_data_from_policy(_current_policy())

    tab.run_from_issue_btn.setChecked(True)
    state = tab.capture_case_inputs()

    assert tab.run_from_issue_enabled() is True
    assert tab.banner_valuation_label.text() == "Not applicable"
    assert tab.banner_first_forecast_label.text() == "5/15/2010"
    assert "#EAF4FA" in tab.styleSheet()
    assert state["controls"]["run_from_issue"] is True

    restored = IllustrationInputsTab()
    restored.load_data_from_policy(_current_policy())
    restored.apply_case_inputs(state)
    assert restored.run_from_issue_enabled() is True
    assert restored.dynamic_panel._ctx.forecast_date == date(2010, 5, 15)


def _policy_with_later_additions():
    policy = _current_policy()
    policy.modal_premium = 100.0
    policy.current_interest_rate = 0.0475
    policy.segments.append(CoverageSegment(
        coverage_phase=2, issue_date=date(2015, 5, 15), issue_age=45,
        face_amount=50_000, original_face_amount=50_000, units=50, is_cola=True))
    policy.face_amount = 150_000
    policy.riders = [
        RiderInfo(coverage_phase=3, plancode="TEST-RIDER",
                  issue_date=policy.issue_date, face_amount=20_000, units=20),
        RiderInfo(coverage_phase=4, plancode="LATER-RIDER",
                  issue_date=date(2015, 5, 15), face_amount=10_000, units=10),
    ]
    policy.benefits = [
        BenefitInfo(coverage_phase=1, benefit_type="W", benefit_subtype="1",
                    issue_date=policy.issue_date, benefit_amount=100_000),
    ]
    return policy


def test_issue_conditions_edit_issue_basis_and_exclude_riders_without_policy_mutation():
    _app()
    policy = _policy_with_later_additions()
    tab = IllustrationInputsTab()
    tab.load_data_from_policy(policy)
    tab.run_from_issue_btn.setChecked(True)
    panel = tab.issue_conditions
    assert panel.face_edit.value() == 100_000
    assert not panel._rider_checks[4].isEnabled()
    panel.face_edit.setValue(85_000)
    panel.dbo_combo.setCurrentIndex(panel.dbo_combo.findData("B"))
    panel._rider_checks[3].setChecked(False)
    panel._benefit_checks[(1, "W", "1")].setChecked(False)

    from suiteview.illustration.ui.saved_case_scenario import build_spec_from_tab
    spec = build_spec_from_tab("From issue", tab, policy)
    projected = spec.scenario.projectable_policy
    assert projected.face_amount == 85_000
    assert projected.segments[0].face_amount == 85_000
    assert projected.db_option == "B"
    assert len(projected.segments) == 1
    assert projected.riders == []
    assert projected.benefits == []
    assert policy.face_amount == 150_000
    assert policy.db_option == "A"
    assert len(policy.riders) == 2
    assert tab.dynamic_panel.illustrated_rate() == 0.0475


def test_mode_switches_preserve_separate_inputs_and_saved_issue_conditions(tmp_path):
    _app()
    policy = _policy_with_later_additions()
    tab = IllustrationInputsTab()
    tab.load_data_from_policy(policy)
    tab.dynamic_panel.lumpsum_edit.setText("1234")
    inforce_dynamic = tab.dynamic_panel.capture_state()
    tab.run_from_issue_btn.setChecked(True)
    assert tab.dynamic_panel.lumpsum_edit.text() == ""
    assert tab.dynamic_panel._ctx.forecast_year == 1
    tab.dynamic_panel.lumpsum_edit.setText("987")
    tab.issue_conditions.face_edit.setValue(75_000)
    tab.issue_conditions.dbo_combo.setCurrentIndex(1)
    tab.issue_conditions._rider_checks[3].setChecked(False)
    issue_dynamic = tab.dynamic_panel.capture_state()

    from suiteview.illustration.models.case_store import save_case, load_case
    save_case("Issue assumptions", policy_number=policy.policy_number, region="CKPR",
              inputs=tab.capture_case_inputs(), policy_snapshot=policy, directory=tmp_path)
    saved = load_case("Issue assumptions", directory=tmp_path)
    restored = IllustrationInputsTab()
    restored.load_data_from_policy(saved.policy_snapshot)
    assert restored.apply_case_inputs(json.loads(json.dumps(saved.inputs))) == []
    assert restored.run_from_issue_enabled()
    assert restored.issue_conditions.face_edit.value() == 75_000
    assert restored.issue_conditions.dbo_combo.currentData() == "B"
    assert not restored.issue_conditions._rider_checks[3].isChecked()
    assert restored.dynamic_panel.capture_state() == issue_dynamic

    restored.run_from_issue_btn.setChecked(False)
    assert restored.dynamic_panel.capture_state() == inforce_dynamic
    assert restored.export_issue_overrides() is None
    restored.run_from_issue_btn.setChecked(True)
    assert restored.dynamic_panel.capture_state() == issue_dynamic


def test_month_end_issue_context_starts_on_issue_not_truncated_prior_month_day():
    _app()
    policy = _current_policy()
    policy.issue_date = date(2010, 3, 31)
    policy.segments[0].issue_date = policy.issue_date
    tab = IllustrationInputsTab()
    tab.load_data_from_policy(policy)
    tab.run_from_issue_btn.setChecked(True)
    assert tab.dynamic_panel._ctx.forecast_date == date(2010, 3, 31)
    assert tab.dynamic_panel.premium_section.rows()[0].year() == 1


def test_issue_mode_changes_window_header_notice_and_invalidates_results():
    _app()
    from suiteview.illustration.ui.main_window import IllustrationWindow
    from suiteview.illustration.ui.styles import (
        ILLUSTRATION_HEADER_COLORS, ILLUSTRATION_ISSUE_HEADER_COLORS,
    )
    window = IllustrationWindow()
    tab = window.inputs_tab
    tab.load_data_from_policy(_policy_with_later_additions())
    window._set_active_inputs_tab(tab)
    window._last_scenario = object()
    tab.run_from_issue_btn.setChecked(True)
    assert "NEW BUSINESS" in window._title_label.text()
    assert "scale 1" in window.projection_mode_notice.text()
    assert window._header_colors == ILLUSTRATION_ISSUE_HEADER_COLORS
    assert window._last_scenario is None
    window._last_scenario = object()
    tab.issue_conditions.face_edit.setValue(90_000)
    assert window._last_scenario is None
    tab.run_from_issue_btn.setChecked(False)
    assert window._header_colors == ILLUSTRATION_HEADER_COLORS
    assert "INFORCE" in window.projection_mode_notice.text()
    window.close()


def test_issue_face_editor_requires_positive_values_and_rejects_invalid_saved_values():
    _app()
    tab = IllustrationInputsTab()
    tab.load_data_from_policy(_current_policy())
    tab.run_from_issue_btn.setChecked(True)
    assert tab.issue_conditions.face_edit.minimum() > 0
    tab.run_from_issue_btn.setChecked(False)
    assert not tab.run_from_issue_enabled()
    assert tab.export_issue_overrides() is None
    restored = IllustrationInputsTab()
    restored.load_data_from_policy(_current_policy())
    assert restored.apply_case_inputs(tab.capture_case_inputs()) == []
    assert restored.export_issue_overrides() is None
    state = tab.capture_case_inputs()
    state["issue_conditions"]["face_amount"] = 0
    with pytest.raises(ValueError, match="editor limits"):
        restored.apply_case_inputs(state)


@pytest.mark.parametrize("target, months", [
    (date(2010, 3, 30), 0), (date(2010, 3, 31), 1),
    (date(2010, 4, 29), 1), (date(2010, 4, 30), 2),
    (date(2011, 2, 28), 12), (date(2011, 3, 30), 12),
    (date(2011, 3, 31), 13),
])
def test_issue_projection_to_date_never_runs_past_requested_month_end_date(target, months):
    policy = _current_policy()
    policy.issue_date = date(2010, 3, 31)
    policy.segments[0].issue_date = policy.issue_date
    projected = build_illustration_scenario(policy, run_from_issue=True).projectable_policy
    assert IllustrationInputsTab._months_to_date(projected, target) == months


def test_loading_second_case_for_same_policy_rebuilds_issue_editor_from_its_snapshot(tmp_path):
    _app()
    from copy import deepcopy
    from suiteview.illustration.models.case_store import SavedCase
    from suiteview.illustration.ui.main_window import IllustrationWindow

    first = _policy_with_later_additions()
    second = deepcopy(first)
    second.riders = [second.riders[1]]
    second.segments[0].original_face_amount = 80_000
    window = IllustrationWindow()
    for index, policy in enumerate((first, second)):
        source = IllustrationInputsTab()
        source.load_data_from_policy(policy)
        source.run_from_issue_btn.setChecked(True)
        case = SavedCase(
            name=f"Case {index}", policy_number=policy.policy_number,
            region="CKPR", company_code="01", saved_at=datetime.now(),
            app_version="test", schema_version=2, inputs=source.capture_case_inputs(),
            path=tmp_path / f"case-{index}.json", policy_snapshot=policy)
        window._load_case_snapshot(case)
    assert window.inputs_tab.issue_conditions.face_edit.value() == 80_000
    assert 3 not in window.inputs_tab.issue_conditions._rider_checks
    assert window.inputs_tab._loaded_policy == second
    assert "NEW BUSINESS" in window._title_label.text()
    assert "Case 1" in window._title_label.text()
    window.close()
