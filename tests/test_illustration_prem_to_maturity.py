"""Prem to Maturity always allows GP exception premiums.

The premium type formerly called "Min to Maturity" solves the minimum level
premium that keeps the policy in force to maturity. The solve — and the
displayed run built from it — must run with allow_exception_prems=True
UNCONDITIONALLY, ignoring the Allow GP Exception Premium checkbox (which
still governs ordinary INPUT-premium runs and Max Level).
"""
import os
from datetime import date
from types import SimpleNamespace

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtWidgets import QApplication

from suiteview.illustration.models.app_settings import get_illustration_settings
from suiteview.illustration.models.calc_state import MonthlyState
from suiteview.illustration.models.input_set import IllustrationInputSet, TransactionKind
from suiteview.illustration.models.policy_data import CoverageSegment, IllustrationPolicyData
from suiteview.illustration.ui.main_window import IllustrationWindow

_QT_APP = None


@pytest.fixture(autouse=True)
def _full_premium_type_surface():
    """Enable the app-wide "Additional Premium Types" option so the advanced
    types (e.g. Max Level) are selectable in these tests. Reset afterwards so
    the singleton never leaks between tests."""
    settings = get_illustration_settings()
    settings.set_additional_premium_types(True)
    yield
    settings.set_additional_premium_types(False)


def _app():
    global _QT_APP
    _QT_APP = QApplication.instance() or QApplication([])
    return _QT_APP


class _StubPolicy:
    """Minimal PolicyInformation stand-in for the load path (GPT by default)."""

    available_companies: list = []
    exists = True
    system_code = "I"

    def __init__(self, policy_number, company_code="01", **_kwargs):
        self.policy_number = policy_number
        self.company_code = company_code or "01"
        self.policy_id = f"{policy_number}  QXXX"
        self.status_description = "Active"
        self.status_code = "0"
        self.issue_date = date(2010, 5, 15)
        self.base_issue_age = 40
        self.valuation_date = date(2026, 6, 15)
        self.maturity_age = 121
        self.attained_age = 56
        self.policy_year = 17
        self.policy_month = 1
        self.billing_frequency = 1
        self.modal_premium = 100.0
        self.base_plancode = ""
        self.total_loan_balance = 0


class _StubDB:
    def __init__(self, region):
        self.region = region

    def connect(self):
        pass

    def close(self):
        pass


class _RecordingEngine:
    """Records every project() call's options; returns a maturity-age state."""

    calls: list = []

    def __init__(self, *args, **kwargs):
        pass

    def project(self, policy, **kwargs):
        _RecordingEngine.calls.append(kwargs)
        return [MonthlyState(
            policy_year=17,
            policy_month=1,
            attained_age=56,
            days_in_month=365.0 / 12.0,
            av_after_premium=10000,
            standard_db=150000,
            gross_db=150000,
            av_end_of_month=9990,
        )]


class _MessageBoxSpy:
    """Never block a headless run on a modal box; record what was shown."""

    shown: list = []

    @classmethod
    def information(cls, *args, **kwargs):
        cls.shown.append(("information", args))

    @classmethod
    def warning(cls, *args, **kwargs):
        cls.shown.append(("warning", args))

    @classmethod
    def critical(cls, *args, **kwargs):
        cls.shown.append(("critical", args))


def _fake_policy_load_checks(self, policy_number, region, company_code):
    self._illustration_data = None
    return [], None


def _policy_data() -> IllustrationPolicyData:
    return IllustrationPolicyData(
        face_amount=150000,
        segments=[CoverageSegment(face_amount=150000)],
    )


def test_prem_to_maturity_forces_exceptions_on_for_solve_and_displayed_run(monkeypatch):
    _app()
    _RecordingEngine.calls = []
    _MessageBoxSpy.shown = []

    policy_data = _policy_data()

    monkeypatch.setattr(
        "suiteview.illustration.ui.main_window.PolicyInformation",
        lambda policy_number, company_code=None, system_code="I", region="CKPR":
            _StubPolicy(policy_number, company_code),
    )
    monkeypatch.setattr("suiteview.illustration.ui.main_window.DB2Connection", _StubDB)
    monkeypatch.setattr("suiteview.illustration.ui.main_window.IllustrationEngine", _RecordingEngine)
    monkeypatch.setattr("suiteview.illustration.ui.main_window.QMessageBox", _MessageBoxSpy)
    monkeypatch.setattr(IllustrationWindow, "_policy_load_checks", _fake_policy_load_checks)
    monkeypatch.setattr(
        "suiteview.illustration.ui.main_window.build_illustration_data",
        lambda policy_number, region=None, company_code=None: policy_data,
    )
    monkeypatch.setattr(
        "suiteview.illustration.ui.main_window.build_illustration_scenario",
        lambda pd, inforce_overrides=None, future_inputs=None: SimpleNamespace(
            projectable_policy=pd,
            future_inputs=future_inputs or IllustrationInputSet(),
            inforce_overrides=None,
        ),
    )

    solve_calls = []

    def _fake_solve(policy, **kwargs):
        solve_calls.append(kwargs)
        return SimpleNamespace(premium=150.0, mode="M")

    monkeypatch.setattr(
        "suiteview.illustration.core.solve_level_to_exception.solve_level_to_exception",
        _fake_solve,
    )

    window = IllustrationWindow()
    window.policy_tab.load_data_from_policy = lambda *a, **kw: None
    window.policy_tab.set_rate_warnings = lambda *a, **kw: None
    window._on_get_policy("POLA", "CKPR", "01")

    tab = window.inputs_tab
    tab.projection_months = lambda p: 0
    tab.projection_duration_label = lambda p: "(0 months)"

    # The user UNCHECKS Allow GP Exception Premium — the Prem to Maturity run
    # must ignore that and force exceptions on anyway.
    tab.exception_prem_check.setChecked(False)
    assert tab.export_options().allow_exception_prems is False

    tab.dynamic_panel.premium_section.rows()[0].type_combo.setCurrentText(
        "Prem to Maturity")
    assert tab.min_level_request() is not None

    window._on_run_values()

    # The solve itself received allow_exceptions=True despite the checkbox.
    assert solve_calls, "the Prem to Maturity solve never ran"
    assert solve_calls[0]["allow_exceptions"] is True

    # The displayed run (first engine projection) used the same basis — the
    # solved premium is layered in and exceptions stay allowed.
    assert _RecordingEngine.calls, "the displayed projection never ran"
    displayed = _RecordingEngine.calls[0]
    assert displayed["options"].allow_exception_prems is True
    solved_premiums = [
        t for t in displayed["future_inputs"].scheduled_transactions
        if t.kind == TransactionKind.PREMIUM and t.amount == 150.0
    ]
    assert solved_premiums, "the solved premium was not layered into the displayed run"

    # The solved amount is filled back into the (disabled) row display.
    assert tab.dynamic_panel.premium_section.rows()[0].amount() == 150.0

    window.close()


def test_max_level_still_honors_the_exception_checkbox(monkeypatch):
    # Max Level keeps reading the checkbox — only Prem to Maturity
    # forces exceptions on.
    _app()
    _RecordingEngine.calls = []
    _MessageBoxSpy.shown = []

    policy_data = _policy_data()

    monkeypatch.setattr(
        "suiteview.illustration.ui.main_window.PolicyInformation",
        lambda policy_number, company_code=None, system_code="I", region="CKPR":
            _StubPolicy(policy_number, company_code),
    )
    monkeypatch.setattr("suiteview.illustration.ui.main_window.DB2Connection", _StubDB)
    monkeypatch.setattr("suiteview.illustration.ui.main_window.IllustrationEngine", _RecordingEngine)
    monkeypatch.setattr("suiteview.illustration.ui.main_window.QMessageBox", _MessageBoxSpy)
    monkeypatch.setattr(IllustrationWindow, "_policy_load_checks", _fake_policy_load_checks)
    monkeypatch.setattr(
        "suiteview.illustration.ui.main_window.build_illustration_data",
        lambda policy_number, region=None, company_code=None: policy_data,
    )
    monkeypatch.setattr(
        "suiteview.illustration.ui.main_window.build_illustration_scenario",
        lambda pd, inforce_overrides=None, future_inputs=None: SimpleNamespace(
            projectable_policy=pd,
            future_inputs=future_inputs or IllustrationInputSet(),
            inforce_overrides=None,
        ),
    )

    max_level_calls = []

    def _fake_max_level(policy, **kwargs):
        max_level_calls.append(kwargs)
        return SimpleNamespace(premium=999.0, mode="M")

    monkeypatch.setattr(
        "suiteview.illustration.core.solve_max_level_allowed.solve_max_level_allowed",
        _fake_max_level,
    )

    window = IllustrationWindow()
    window.policy_tab.load_data_from_policy = lambda *a, **kw: None
    window.policy_tab.set_rate_warnings = lambda *a, **kw: None
    window._on_get_policy("POLB", "CKPR", "01")

    tab = window.inputs_tab
    tab.projection_months = lambda p: 0
    tab.projection_duration_label = lambda p: "(0 months)"
    tab.exception_prem_check.setChecked(False)

    tab.dynamic_panel.premium_section.rows()[0].type_combo.setCurrentText(
        "Max Level")
    assert tab.max_level_request() is not None

    window._on_run_values()

    assert max_level_calls, "the Max Level solve never ran"
    assert max_level_calls[0]["allow_exceptions"] is False
    displayed = _RecordingEngine.calls[0]
    assert displayed["options"].allow_exception_prems is False

    window.close()
