"""Native Reinstatement UI and Policy Support routing without database access."""
from datetime import date
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QTabWidget, QWidget

from suiteview.polview.services.reinstatement import ReinstatementError
from suiteview.polview.ui import main_window
from suiteview.polview.ui.main_window import GetPolicyWindow
from suiteview.polview.ui.tabs import reinstatement_tab
from suiteview.polview.ui.tabs.policy_support_tab import PolicySupportTab
from suiteview.polview.ui.tabs.reinstatement_tab import ReinstatementTab


@pytest.fixture
def summary():
    return SimpleNamespace(
        last_entry_code="Q", last_entry_description="Termination - Lapse",
        termination_date=date(2024, 7, 15), current_date=date(2026, 9, 14),
        terminated_years=2, terminated_months=1, eligible=True, message="Eligible",
        quote_pay_to_date=date(2026, 8, 15), next_monthliversary=date(2026, 9, 15),
    )


@pytest.fixture
def quote(summary):
    return SimpleNamespace(
        summary=summary, premium=251.23, basis="Surrender value",
        breakdown=[
            ("Starting account value", "-100.00"),
            ("Total monthly deductions", "150.00"),
            ("Next monthliversary debt", "1.22"),
            ("Required gross premium", "251.23"),
        ],
        explanation="Fund the next monthliversary after its monthly deduction.",
    )


@pytest.fixture
def calculation(monkeypatch, summary, quote):
    monkeypatch.setattr(reinstatement_tab, "reinstatement_summary", Mock(return_value=summary))
    solve = Mock(return_value=quote)
    monkeypatch.setattr(reinstatement_tab, "calculate_home_office_reinstatement", solve)
    return solve


@pytest.fixture
def tab(qtbot, calculation):
    widget = ReinstatementTab()
    qtbot.addWidget(widget)
    return widget


@pytest.fixture
def host(qtbot, calculation):
    class Host(QWidget):
        _show_reinstatement_tab = GetPolicyWindow._show_reinstatement_tab
        _clear_reinstatement_tab = GetPolicyWindow._clear_reinstatement_tab
        _insert_aux_tab = GetPolicyWindow._insert_aux_tab

    widget = Host()
    qtbot.addWidget(widget)
    widget._policy = SimpleNamespace(exists=True, product_type="UL")
    widget._show_status = Mock()
    widget.tabs = QTabWidget(widget)
    widget.policy_support_tab = PolicySupportTab()
    widget.raw_table_tab = QWidget()
    widget.reinstatement_tab = None
    widget.tabs.addTab(widget.policy_support_tab, "Policy Support")
    widget.tabs.addTab(widget.raw_table_tab, "Raw Table")
    widget.policy_support_tab.reinstatement_requested.connect(widget._show_reinstatement_tab)
    return widget


def test_button_opens_one_top_level_tab_and_repeat_click_refreshes(host, qtbot, calculation):
    button = host.policy_support_tab._btn_reinstatement
    assert button.text() == "UL Reinstatement"
    qtbot.mouseClick(button, Qt.MouseButton.LeftButton)
    tab = host.reinstatement_tab
    assert host.tabs.currentWidget() is tab
    assert host.tabs.tabText(host.tabs.indexOf(tab)) == "Reinstatement"
    assert host.tabs.indexOf(tab) == host.tabs.indexOf(host.raw_table_tab) - 1
    qtbot.mouseClick(button, Qt.MouseButton.LeftButton)
    assert host.tabs.count() == 3
    assert host.reinstatement_tab is tab
    assert calculation.call_count == 2


@pytest.mark.parametrize("product", ["WL", "TERM", "ISWL", "VUL", "ANNUITY"])
def test_non_ul_click_shows_popup_without_creating_tab(host, monkeypatch, product, calculation):
    host._policy.product_type = product
    popup = Mock()
    monkeypatch.setattr(main_window.QMessageBox, "information", popup)
    host.policy_support_tab._btn_reinstatement.click()
    assert popup.call_args.args[2] == (
        "Currently reinstatement quotes are only available for ULs"
    )
    assert host.reinstatement_tab is None
    assert host.tabs.count() == 2
    calculation.assert_not_called()


def test_no_policy_prompts_without_creating_tab(host, monkeypatch, calculation):
    host._policy = None
    popup = Mock()
    monkeypatch.setattr(main_window.QMessageBox, "information", popup)
    host.policy_support_tab._btn_reinstatement.click()
    assert "load a policy" in popup.call_args.args[2]
    assert host.reinstatement_tab is None
    calculation.assert_not_called()


def test_summary_dates_breakdown_and_skipped_section_visible(tab, quote):
    tab.load_policy(SimpleNamespace(exists=True, product_type="UL"))
    tab.show()
    assert tab.summary_group.entry.text() == "Q - Termination - Lapse"
    assert tab.summary_group.termination.text() == "7/15/2024"
    assert tab.summary_group.today.text() == "9/14/2026"
    assert tab.summary_group.elapsed.text() == "2 years, 1 month"
    assert tab.home_group.pay_to.text() == "8/15/2026"
    assert tab.home_group.next_date.text() == "9/15/2026"
    assert tab.home_group.premium.text() == "$251.23"
    assert tab.home_group.basis.text() == quote.basis
    assert tab.home_group.table.rowCount() == len(quote.breakdown)
    assert tab.home_group.table._data_table.horizontalHeaderItem(0).text() == "Calculation breakdown"
    assert tab.home_group.isVisible() and tab.skipped_group.isVisible()
    assert tab.skipped_note.isVisible()
    assert "not been specified" in tab.skipped_note.text()


def test_non_lapsed_policy_displays_summary_but_never_quotes(tab, summary, calculation):
    summary.eligible = False
    summary.last_entry_code = "P"
    summary.last_entry_description = "Termination - Surrender"
    summary.message = "Only lapsed policies may be reinstated; surrendered policies are not eligible."
    tab.load_policy(SimpleNamespace(exists=True, product_type="UL"))
    assert tab.summary_group.entry.text() == "P - Termination - Surrender"
    assert tab.home_group.premium.text() == "Not eligible"
    assert "surrendered" in tab.status_label.text()
    assert not tab.calculate_button.isEnabled()
    calculation.assert_not_called()


def test_zero_quote_remains_explicit(tab, quote):
    quote.premium = 0
    tab.load_policy(SimpleNamespace(exists=True, product_type="UL"))
    assert tab.home_group.premium.text() == "$0.00"
    assert tab._result is quote


def test_failed_recalculation_clears_previous_quote_and_allows_retry(tab, calculation, caplog):
    tab.load_policy(SimpleNamespace(exists=True, product_type="UL"))
    calculation.side_effect = ReinstatementError("Required COI rates are missing.")
    tab.calculate_button.click()
    assert tab._result is None
    assert tab.home_group.premium.text() == "Unavailable"
    assert tab.home_group.table.rowCount() == 0
    assert tab.explanation_label.text() == ""
    assert "Required COI rates are missing" in tab.status_label.text()
    assert "Reinstatement quote unavailable" in caplog.text
    assert tab.calculate_button.isEnabled()


def test_policy_reload_closes_and_clears_old_quote(host):
    host._show_reinstatement_tab()
    tab = host.reinstatement_tab
    # _load_all_tabs clears before validating/loading the replacement policy.
    host._policy = None
    GetPolicyWindow._load_all_tabs(host)
    assert host.tabs.indexOf(tab) == -1
    assert tab._result is None and tab._policy is None
    assert tab.home_group.premium.text() == ""
    assert tab.summary_group.entry.text() == ""


def test_calculation_uses_one_current_date_for_summary_and_solve(tab, calculation):
    tab.load_policy(SimpleNamespace(exists=True, product_type="UL"))
    assert calculation.call_args.kwargs["today"] == (
        reinstatement_tab.reinstatement_summary.call_args.kwargs["today"]
    )
