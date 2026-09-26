"""Regression tests for ABR behavior restored after the core-service split."""

from __future__ import annotations

import os
from datetime import date
from types import SimpleNamespace
from unittest.mock import MagicMock, Mock

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtWidgets import QApplication, QDialog, QMessageBox, QWidget

from suiteview.abrquote.automation import QuoteError, QuoteRequest, _assessment_port
from suiteview.abrquote.core import abr_policy_service
from suiteview.abrquote.core.assessment_solver import (
    AssessmentInputs,
    solve_substandard,
    terminal_substandard,
)
from suiteview.abrquote.core.quote_service import build_quote_messages
from suiteview.abrquote.models.abr_data import ABRPolicyData
from suiteview.abrquote.models.abr_database import using_quote_database
from suiteview.abrquote.ui.email_print_dialog import EmailPrintDialog


class Rates:
    def get_vbt_qx(self, *args):
        return 10.0

    def get_effective_interest_rate(self, month):
        return (month, 0.05)

    def get_term_rate(self, *args):
        return 2.0

    def get_term_rate_schedule(self, *args):
        return [2.0] * 82

    def get_band(self, *args):
        return "A"

    def get_policy_fee(self, *args):
        return 60.0

    def get_modal_factor(self, *args):
        return 0.0875

    def get_modal_fee_factor(self, *args):
        return 1.0

    def get_admin_fee(self, *args):
        return 250.0

    def get_per_diem(self, *args):
        return (420.0, 153300.0)

    def get_prem_cease_age(self, *args):
        return 95

    def reset_query_stats(self):
        pass

    def dump_query_stats(self):
        pass


@pytest.fixture
def policy() -> ABRPolicyData:
    return ABRPolicyData(
        policy_number="SYNTHETIC",
        company="01",
        region="CKPR",
        product_type="TERM",
        plan_code="TEST",
        issue_state="TX",
        issue_date=date(2026, 1, 1),
        maturity_date=date(2055, 1, 1),
        face_amount=100000,
        min_face_amount=50000,
        issue_age=40,
        attained_age=46,
        maturity_age=75,
        sex="F",
        rate_sex="F",
        rate_class="N",
        policy_year=1,
        policy_month=3,
        reinsurers="(none)",
        billing_mode=4,
    )


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


def test_premium_schedule_current_year_proration_uses_python_round(monkeypatch, policy):
    class PremiumCalculator:
        def __init__(self, _policy):
            pass

        def compute(self, policy_year):
            return SimpleNamespace(modal_premium=0.0)

        def get_base_annual_premium_schedule(self):
            return [1002.0] * 10

        def get_annual_premium_schedule(self):
            return [1002.0] * 10

    monkeypatch.setattr(
        "suiteview.abrquote.core.premium_calc.PremiumCalculator",
        PremiumCalculator,
    )
    with using_quote_database(Rates()):
        schedule = abr_policy_service.premium_schedule_for_quote(
            policy,
            date(2026, 3, 1),
        )

    assert schedule.remaining_payments == 9
    assert schedule.premium_schedule[0] == pytest.approx(789.03)


def test_policy_panel_current_year_proration_keeps_display_rounding(monkeypatch, policy):
    from suiteview.abrquote.ui.policy_panel import PolicyPanel

    class PremiumCalculator:
        def __init__(self, _policy):
            pass

        def compute(self, policy_year):
            return SimpleNamespace(modal_premium=87.68)

        def get_base_annual_premium_schedule(self):
            return [1002.0] * 10

        def get_annual_premium_schedule(self):
            return [1002.0] * 10

        def build_coverage_breakdown(self, **_kwargs):
            return []

    class Label:
        def setText(self, text):
            self.text = text

    class Button:
        def setVisible(self, visible):
            self.visible = visible

    monkeypatch.setattr(
        "suiteview.abrquote.core.premium_calc.PremiumCalculator",
        PremiumCalculator,
    )
    owner = SimpleNamespace(
        _policy=policy,
        _detail_labels={"calc_premium": Label()},
        _calc_detail_btn=Button(),
        _render_premium_warning=Mock(),
        _render_premium_schedule_rows=Mock(),
        get_quote_date=lambda: date(2026, 3, 1),
    )

    with using_quote_database(Rates()):
        PolicyPanel._populate_premium_schedule(owner)

    schedule = owner._render_premium_schedule_rows.call_args.args[0]
    assert schedule.premium_schedule[0] == pytest.approx(789.12)


def test_assessment_final_life_expectancy_includes_direct_addons(policy):
    inputs = AssessmentInputs(
        rider_type="Chronic",
        use_five_year=True,
        five_year_survival=0.8,
        use_flat=True,
        direct_flat_extra=25.0,
        flat_start_year=1,
        flat_stop_year=99,
    )

    with using_quote_database(Rates()):
        result = solve_substandard(policy, inputs)

    assessment = result.assessment
    assert assessment.life_expectancy_years == pytest.approx(assessment.computed_le)
    assert assessment.life_expectancy_rounded == round(assessment.computed_le)


def test_terminal_warning_uses_final_life_expectancy_after_addons(policy):
    inputs = AssessmentInputs(
        rider_type="Chronic",
        use_five_year=True,
        five_year_survival=0.8,
        use_flat=True,
        direct_flat_extra=1000.0,
        flat_start_year=1,
        flat_stop_year=99,
    )

    with using_quote_database(Rates()):
        assessment = solve_substandard(policy, inputs).assessment

    assert assessment.computed_le <= 2.0
    snapshot = SimpleNamespace(
        inputs=SimpleNamespace(
            policy=policy,
            assessment=assessment,
            min_face_amount=50000,
        ),
        result=SimpleNamespace(
            full_accel_benefit=0,
            per_diem_annual=0,
        ),
    )

    assert any("Life expectancy is" in msg for msg in build_quote_messages(snapshot))


def test_email_summary_uses_final_life_expectancy_after_addons(policy):
    inputs = AssessmentInputs(
        rider_type="Chronic",
        use_five_year=True,
        five_year_survival=0.8,
        use_flat=True,
        direct_flat_extra=25.0,
        flat_start_year=1,
        flat_stop_year=99,
    )

    with using_quote_database(Rates()):
        assessment = solve_substandard(policy, inputs).assessment

    class SummaryPort:
        def __init__(self):
            self.values = {}

        def _set(self, key, value):
            self.values[key] = value

    port = SummaryPort()
    EmailPrintDialog._populate_assessment_summary(port, assessment)

    assert port.values["life_expectancy"] == f"{assessment.computed_le:.1f}"


def test_automation_rejects_goal_seek_warning_fallback(policy):
    request = QuoteRequest.from_dict(
        {
            "policy_number": "SYNTHETIC",
            "company_code": "01",
            "region": "CKPR",
            "quote_date": "2026-09-03",
            "effective_date": "2026-09-03",
            "assessment": {
                "rider_type": "Chronic",
                "five_year_survival": 0.9999,
                "flat": {"value": 25.0, "start_year": 1, "stop_year": 99},
            },
            "options": {"min_face_amount": 50000},
            "input_provenance": {"source": "synthetic regression"},
        }
    )

    with using_quote_database(Rates()):
        with pytest.raises(QuoteError, match="Lookup failed; default result rejected"):
            _assessment_port(policy, request)


def test_terminal_standard_text_ignores_second_table_rating(policy):
    policy.table_rating = 1
    policy.table_rating_2 = 2

    with using_quote_database(Rates()):
        result = terminal_substandard(policy)

    assert result.derived_values["std_table_rating"] == "Table 1"


@pytest.mark.parametrize(
    ("method", "row", "warning_text"),
    [
        (
            "_edit_interest_rate_dialog",
            ["2026-09-01", "4.5", "5.6%"],
            "ABR Rate must be a number.",
        ),
        (
            "_edit_state_variation_dialog",
            ["TX", "TX", "Texas", "A", "250", "", "", "", ""],
            "CL State Code must be an integer.",
        ),
    ],
)
def test_rate_edit_dialog_aborts_nonempty_optional_number_parse_errors(
    method,
    row,
    warning_text,
    app,
    monkeypatch,
):
    from suiteview.abrquote.ui import rate_viewer_dialog as abr

    owner = QWidget()
    owner._status_label = Mock()
    owner._type_combo = Mock()
    owner._on_type_changed = Mock()
    database = MagicMock()
    get_database = Mock(return_value=database)
    guard = Mock()
    warning = Mock()
    monkeypatch.setattr(abr, "get_abr_database", get_database)
    monkeypatch.setattr(abr, "guard_data_writable", guard)
    monkeypatch.setattr(QMessageBox, "warning", warning)
    monkeypatch.setattr(QMessageBox, "critical", Mock())
    monkeypatch.setattr(QDialog, "exec", lambda *_args: QDialog.DialogCode.Accepted)

    try:
        getattr(abr.RateViewerDialog, method)(owner, row)
        warning.assert_called_with(owner, "Validation", warning_text)
        guard.assert_not_called()
        get_database.assert_not_called()
        database.connect.assert_not_called()
    finally:
        owner.close()
        owner.deleteLater()
