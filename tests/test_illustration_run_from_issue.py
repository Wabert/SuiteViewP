import os
from datetime import date
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
    CoverageSegment,
    IllustrationPolicyData,
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
