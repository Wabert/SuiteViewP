"""Per-policy session persistence in the Illustration window.

Policy-list switching preserves each policy's Illustration Inputs and last
computed Values for the session: coming back restores the exact inputs widget
and re-renders the cached projection without any engine run. Explicitly clicking
Get resets that policy to fresh defaults.
"""
import os
from datetime import date
from types import SimpleNamespace

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtWidgets import QApplication

from suiteview.illustration.core.rate_loader import IllustrationRates
from suiteview.illustration.core.report_builder import IllustrationReport, LedgerRow
from suiteview.illustration.models.calc_state import MonthlyState
from suiteview.illustration.models.plancode_config import PlancodeConfig
from suiteview.illustration.models.policy_data import CoverageSegment, IllustrationPolicyData
from suiteview.illustration.ui.main_window import IllustrationWindow
from suiteview.illustration.ui.policy_tab import IllustrationPolicyTab
from suiteview.illustration.ui.styles import ISSUE_BLUE_BG
from suiteview.illustration.ui.values_tab import IllustrationValuesTab

_QT_APP = None


def _app():
    global _QT_APP
    _QT_APP = QApplication.instance() or QApplication([])
    return _QT_APP


def _policy_data() -> IllustrationPolicyData:
    return IllustrationPolicyData(
        face_amount=150000,
        segments=[CoverageSegment(face_amount=150000)],
    )


def _state() -> MonthlyState:
    return MonthlyState(
        policy_year=1,
        policy_month=2,
        attained_age=45,
        days_in_month=365.0 / 12.0,
        av_after_premium=10000,
        standard_db=150000,
        gross_db=150000,
        av_end_of_month=9990,
    )


def _report() -> IllustrationReport:
    return IllustrationReport(
        company_name="Test Co",
        policy_number="POLA",
        ledger=[LedgerRow(eoy_age=46, year=1, accum_value=9990.0)],
    )


# ── Values tab snapshot/restore ──────────────────────────────────────


def test_values_tab_capture_is_none_until_a_projection_is_shown():
    _app()
    tab = IllustrationValuesTab()
    assert tab.capture_session_state() is None
    assert tab.restore_session_state(None) is False
    assert tab.restore_session_state({"current_view": None}) is False


def test_values_tab_session_state_round_trips_without_engine():
    _app()
    tab = IllustrationValuesTab()
    tab.display_projection(_policy_data(), [_state()], months=1)
    tab.set_guaranteed_results(_policy_data(), [_state()])
    # Leave the tab showing the guaranteed side — restore must come back on
    # Current Values, the default for a fresh render.
    tab.guaranteed_toggle.setChecked(True)

    snapshot = tab.capture_session_state()
    assert snapshot is not None

    tab.clear_results("cleared for another policy")
    assert tab._results == []
    assert tab._current_view is None

    assert tab.restore_session_state(snapshot) is True
    assert len(tab._results) == 1
    assert tab._current_view is not None
    # The guaranteed side re-attaches: the Current | Guaranteed pair is offered
    # again, reset to its Current Values default.
    assert tab._guaranteed_view is not None
    assert tab.current_toggle.isVisibleTo(tab)
    assert tab.guaranteed_toggle.isVisibleTo(tab)
    assert tab.current_toggle.isChecked()
    assert not tab.guaranteed_toggle.isChecked()
    # Grids repopulated from the snapshot.
    assert len(tab._tab_grids["Summary"].df) == 1
    assert tab.status_label.text() == "Showing valuation snapshot plus 1 projected months."


# ── Window-level policy switching ────────────────────────────────────


class _StubPolicy:
    """Minimal PolicyInformation stand-in for the load path."""

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


class _EngineBomb:
    """Any engine construction during a session restore is a failure."""

    def __init__(self, *args, **kwargs):
        raise AssertionError("IllustrationEngine must not run on a session restore")


def _fake_policy_load_checks(self, policy_number, region, company_code):
    self._illustration_data = None
    return [], None


def _make_window(monkeypatch) -> IllustrationWindow:
    _app()
    monkeypatch.setattr(
        "suiteview.illustration.ui.main_window.PolicyInformation",
        lambda policy_number, company_code=None, system_code="I", region="CKPR":
            _StubPolicy(policy_number, company_code),
    )
    monkeypatch.setattr("suiteview.illustration.ui.main_window.DB2Connection", _StubDB)
    monkeypatch.setattr("suiteview.illustration.core.run_service.IllustrationEngine", _EngineBomb)
    monkeypatch.setattr(IllustrationWindow, "_policy_load_checks", _fake_policy_load_checks)
    window = IllustrationWindow()
    # The Policy tab render needs the full PolicyInformation surface — out of
    # scope here, the session cache never touches it.
    window.policy_tab.load_data_from_policy = lambda *a, **kw: None
    window.policy_tab.set_rate_warnings = lambda *a, **kw: None
    return window


def test_live_policy_refresh_retains_calculated_md_and_validation_warnings(monkeypatch):
    window = _make_window(monkeypatch)
    tab = window.policy_tab
    tab.load_data_from_policy = IllustrationPolicyTab.load_data_from_policy.__get__(tab)
    tab.set_rate_warnings = IllustrationPolicyTab.set_rate_warnings.__get__(tab)
    monkeypatch.setattr(_StubPolicy, "get_coverages", lambda self: [], raising=False)
    monkeypatch.setattr(_StubPolicy, "get_benefits", lambda self: [], raising=False)
    monkeypatch.setattr(tab, "_populate_policy_info", lambda *_: None)
    monkeypatch.setattr(tab, "_populate_value_groups", lambda *_: None)
    monkeypatch.setattr(tab, "_populate_fund_values", lambda *_: None)
    monkeypatch.setattr(tab, "_populate_coverage_buttons", lambda: None)
    checks = []
    results = {
        "POLA": (["MD validation warning for POLA"], MonthlyState(
            system_monthly_deduction=18.70, md_check_calculated_deduction=19.25)),
        "POLB": ([], MonthlyState(
            system_monthly_deduction=0.0, md_check_calculated_deduction=0.0)),
        "POLC": (["Unable to validate monthly deduction: missing rates"], None),
    }

    def load_checks(self, policy_number, region, company_code):
        checks.append(policy_number)
        self._illustration_data = IllustrationPolicyData(
            policy_number=policy_number, company_code=company_code, region=region,
            issue_date=date(2010, 5, 15), valuation_date=date(2026, 6, 15),
            face_amount=150_000, account_value=10_000, db_option="A",
        )
        return results[policy_number]

    monkeypatch.setattr(IllustrationWindow, "_policy_load_checks", load_checks)
    try:
        for number, expected in (
            ("POLA", "$19.25"), ("POLB", "$0.00"), ("POLC", ""), ("POLA", "$19.25"),
        ):
            window._on_get_policy(number, "CKPR", "01")
            assert tab.policy_info.get_value("calculated_md") == expected
            assert tab.rate_warning_label.text() == "\n".join(results[number][0])
            count = len(checks)
            window._refresh_policy_basis()
            assert len(checks) == count
            assert tab.policy_info.get_value("calculated_md") == expected
            assert tab.rate_warning_label.text() == "\n".join(results[number][0])

        window._policy = _StubPolicy("UNCHECKED")
        window._refresh_policy_basis()
        assert tab.policy_info.get_value("calculated_md") == ""
        assert tab.rate_warning_label.text() == ""

        window._policy = None
        window._refresh_policy_basis()
        assert tab.policy_info.get_value("calculated_md") == ""
        assert tab.rate_warning_label.text() == ""
    finally:
        window.close()


def test_switching_policies_preserves_inputs_and_values_per_policy(monkeypatch):
    window = _make_window(monkeypatch)

    window._on_get_policy("POLA", "CKPR", "01")
    key_a = ("POLA", "CKPR", "01")
    assert window._current_key == key_a
    tab_a = window.inputs_tab
    assert window._session_states[key_a].input_draft is not None

    # Non-trivial inputs: premium row amount, a control toggle, grid cells,
    # and a face-change row on the dynamic panel.
    premium_row = tab_a.dynamic_panel.premium_section.rows()[0]
    premium_row.amount_edit.setText("250.00")
    tab_a.exact_days_check.setChecked(True)
    tab_a.unscheduled_premium_table.item(0, 0).setText("06/15/2027")
    tab_a.unscheduled_premium_table.item(0, 1).setText("1,000")
    face_row = tab_a.dynamic_panel.face_section.rows()[0]
    face_row.year_edit.setText("18")
    face_row.amount_edit.setText("50000")

    # Simulate a completed Run Values (the engine itself is out of scope):
    # rendered projection + report + the status banner.
    window.values_tab.display_projection(_policy_data(), [_state()], months=1)
    window.report_tab.display_report(_report())
    run_status = "Values ready for POLA - valuation snapshot plus 1 projected months"
    window._show_status(run_status)

    # Switch to another policy: fresh inputs, cleared values.
    window._on_get_policy("POLB", "CKPR", "01")
    tab_b = window.inputs_tab
    assert tab_b is not tab_a
    assert tab_b.dynamic_panel.premium_section.rows()[0].amount_edit.text() != "250.00"
    assert tab_b.exact_days_check.isChecked() is False
    assert window.values_tab._current_view is None
    assert window.report_tab.current_report() is None

    # Back to POLA: a fresh inputs widget renders the plain draft, values
    # re-render from the snapshot (the engine bomb proves no recalculation),
    # and the status banner comes back.
    window._on_get_policy("POLA", "CKPR", "01")
    restored = window.inputs_tab
    assert restored is not tab_a
    assert restored.dynamic_panel.premium_section.rows()[0].amount_edit.text() == "250.00"
    assert restored.exact_days_check.isChecked() is True
    assert restored.unscheduled_premium_table.item(0, 0).text() == "06/15/2027"
    assert restored.unscheduled_premium_table.item(0, 1).text() == "1,000"
    restored_face = restored.dynamic_panel.face_section.rows()[0]
    assert restored_face.year_edit.text() == "18"
    assert restored_face.amount_edit.text() == "50000"
    assert len(window.values_tab._results) == 1
    report = window.report_tab.current_report()
    assert report is not None and report.policy_number == "POLA"
    assert window._status_label.text() == run_status
    assert window.run_values_btn.isEnabled()

    window.close()


def test_revisiting_issue_mode_policy_restores_issue_styling(monkeypatch):
    def load_checks(self, policy_number, region, company_code):
        self._illustration_data = IllustrationPolicyData(
            policy_number=policy_number,
            company_code=company_code,
            region=region,
            issue_date=date(2010, 5, 15),
            issue_age=40,
            attained_age=56,
            valuation_date=date(2026, 6, 15),
            policy_year=17,
            policy_month=1,
            duration=193,
            maturity_age=121,
            face_amount=150_000,
            segments=[
                CoverageSegment(
                    issue_date=date(2010, 5, 15),
                    issue_age=40,
                    face_amount=150_000,
                    original_face_amount=150_000,
                    units=150,
                )
            ],
        )
        return [], None

    window = _make_window(monkeypatch)
    monkeypatch.setattr(IllustrationWindow, "_policy_load_checks", load_checks)

    window._on_get_policy("POLA", "CKPR", "01")
    window.inputs_tab.run_from_issue_btn.setChecked(True)
    assert window.inputs_tab.run_from_issue_enabled() is True
    assert ISSUE_BLUE_BG in window.tabs_container.styleSheet()

    window._on_get_policy("POLB", "CKPR", "01")
    assert window.inputs_tab.run_from_issue_enabled() is False
    assert ISSUE_BLUE_BG not in window.tabs_container.styleSheet()

    window._on_get_policy("POLA", "CKPR", "01")

    assert window.inputs_tab.run_from_issue_enabled() is True
    assert ISSUE_BLUE_BG in window.tabs_container.styleSheet()

    window.close()


def test_revisit_without_a_run_restores_inputs_and_empty_values(monkeypatch):
    window = _make_window(monkeypatch)

    window._on_get_policy("POLA", "CKPR", "01")
    tab_a = window.inputs_tab
    tab_a.dynamic_panel.premium_section.rows()[0].amount_edit.setText("777.00")

    window._on_get_policy("POLB", "CKPR", "01")
    window._on_get_policy("POLA", "CKPR", "01")

    assert window.inputs_tab is not tab_a
    assert window.inputs_tab.dynamic_panel.premium_section.rows()[0].amount_edit.text() == "777.00"
    # Never ran → values stay empty, no phantom projection.
    assert window.values_tab._current_view is None
    assert window.report_tab.current_report() is None

    window.close()


def test_policy_load_checks_uses_data_loader_before_projection(monkeypatch):
    calls = []
    policy_data = IllustrationPolicyData(
        policy_number="POLA",
        plancode="TEST",
        face_amount=150_000,
        segments=[CoverageSegment(face_amount=150_000)],
    )
    harness = SimpleNamespace(
        _policy=object(),
        _illustration_data=None,
        _definition_of_life_warnings=lambda _policy: [],
        _monthly_deduction_warnings=lambda _state: [],
    )

    monkeypatch.setattr(
        "suiteview.illustration.ui.main_window.coverage_segment_data_warnings",
        lambda _policy: [],
    )
    monkeypatch.setattr(
        "suiteview.illustration.ui.main_window.load_policy_data",
        lambda *args, **kwargs: calls.append(("load_policy_data", args, kwargs)) or policy_data,
        raising=False,
    )
    monkeypatch.setattr(
        "suiteview.illustration.ui.main_window.load_plancode",
        lambda _plancode: PlancodeConfig(plancode="TEST"),
    )
    monkeypatch.setattr(
        "suiteview.illustration.ui.main_window.load_rates",
        lambda _policy, _config: IllustrationRates(),
    )

    def project(policy_or_number, **_kwargs):
        calls.append(("project_policy", policy_or_number))
        return SimpleNamespace(policy=policy_data, states=[MonthlyState()])

    monkeypatch.setattr(
        "suiteview.illustration.ui.main_window.project_policy",
        project,
    )

    warnings, md_check = IllustrationWindow._policy_load_checks(
        harness, "POLA", "CKPR", "01")

    assert warnings == []
    assert md_check is not None
    assert harness._illustration_data is policy_data
    assert calls == [
        ("load_policy_data", ("POLA",), {"region": "CKPR", "company_code": "01"}),
        ("project_policy", policy_data),
    ]


def test_policy_load_surfaces_illustration_data_error(monkeypatch):
    window = _make_window(monkeypatch)
    warnings = []

    class MessageBoxSpy:
        @staticmethod
        def warning(_parent, title, text):
            warnings.append((title, text))

        @staticmethod
        def critical(_parent, title, text):
            warnings.append((title, text))

    monkeypatch.setattr("suiteview.illustration.ui.main_window.QMessageBox", MessageBoxSpy)

    def failed_checks(self, policy_number, region, company_code):
        self._illustration_data = None
        self._illustration_load_error = "Unable to load illustration data/rates: boom"
        return [self._illustration_load_error], None

    monkeypatch.setattr(IllustrationWindow, "_policy_load_checks", failed_checks)

    try:
        window._on_get_policy("POLA", "CKPR", "01")

        assert window._status_label.text() == "Unable to load illustration data/rates: boom"
        assert warnings == [
            ("Illustration Data", "Unable to load illustration data/rates: boom")
        ]
    finally:
        window.close()


def test_clicking_get_reloads_same_policy_with_default_inputs(monkeypatch):
    window = _make_window(monkeypatch)
    window.lookup_bar.region_input.setText("CKPR")
    window.lookup_bar.company_input.setText("01")
    window.lookup_bar.policy_input.setText("POLA")

    window.lookup_bar.get_button.click()
    original_tab = window.inputs_tab
    original_tab.dynamic_panel.premium_section.rows()[0].amount_edit.setText("777.00")
    original_tab.exact_days_check.setChecked(True)
    window.values_tab.display_projection(_policy_data(), [_state()], months=1)
    window.report_tab.display_report(_report())

    window.lookup_bar.get_button.click()

    assert window.inputs_tab is not original_tab
    assert window.inputs_tab.dynamic_panel.premium_section.rows()[0].amount_edit.text() != "777.00"
    assert window.inputs_tab.exact_days_check.isChecked() is False
    assert window.values_tab._current_view is None
    assert window.report_tab.current_report() is None

    window.close()


def test_removing_a_policy_from_the_list_drops_its_session(monkeypatch):
    window = _make_window(monkeypatch)

    window._on_get_policy("POLA", "CKPR", "01")
    tab_a = window.inputs_tab
    tab_a.dynamic_panel.premium_section.rows()[0].amount_edit.setText("321.00")
    window._on_get_policy("POLB", "CKPR", "01")

    window._on_policy_removed_from_list("POLA", "CKPR")
    assert ("POLA", "CKPR", "01") not in window._session_states

    # Revisiting builds a fresh inputs tab with policy defaults.
    window._on_get_policy("POLA", "CKPR", "01")
    assert window.inputs_tab is not tab_a
    assert window.inputs_tab.dynamic_panel.premium_section.rows()[0].amount_edit.text() != "321.00"

    window.close()


def test_switching_policies_clears_compare_results(monkeypatch):
    """A rendered comparison must never survive a policy switch — the old
    policy's KPIs/ledger would sit mislabeled under the new policy's pickers."""
    from suiteview.illustration.core.compare_runner import (
        ComparisonResult, ScenarioOutcome,
    )
    import pandas as pd

    window = _make_window(monkeypatch)
    window._on_get_policy("POLA", "CKPR", "01")

    # Render a (failed-side) comparison — visible banner + status marker.
    result = ComparisonResult(
        outcomes=[ScenarioOutcome(label="Opt A", error="x"),
                  ScenarioOutcome(label="Opt B", error="y")],
        kpis=[], ledger=pd.DataFrame())
    window.compare_tab.populate_comparison(result)
    assert window.compare_tab._result is result
    assert not window.compare_tab.banner_a.isHidden()

    # Switching to a different policy wipes the comparison...
    window._on_get_policy("POLB", "CKPR", "01")
    assert window.compare_tab._result is None
    assert window.compare_tab.banner_a.isHidden()
    assert window.compare_tab.banner_b.isHidden()
    assert window.compare_tab.status_label.text().startswith("Load a policy")

    # ...and re-loading the SAME policy leaves a fresh comparison alone.
    window.compare_tab.populate_comparison(result)
    window._on_get_policy("POLB", "CKPR", "01")
    assert window.compare_tab._result is result

    window.close()


def test_clear_all_policies_drops_every_session_entry(monkeypatch):
    window = _make_window(monkeypatch)

    window._on_get_policy("POLA", "CKPR", "01")
    window._on_get_policy("POLB", "CKPR", "01")
    assert len(window._session_states) == 2

    window._on_all_policies_removed()
    assert window._session_states == {}

    # The active widget stays on screen until the next switch, which cleans
    # up the now-unregistered tab.
    active = window.inputs_tab
    window._on_get_policy("POLC", "CKPR", "01")
    assert window.inputs_tab is not active

    window.close()
