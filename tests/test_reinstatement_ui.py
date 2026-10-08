"""Native Reinstatement tab and Policy Support routing without database access."""
from datetime import date
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QComboBox, QLabel, QTabWidget, QWidget

from suiteview.illustration.core.rate_loader import IllustrationRates
from suiteview.illustration.models.plancode_config import PlancodeConfig
from suiteview.illustration.models.policy_data import CoverageSegment, IllustrationPolicyData
from suiteview.polview.services import reinstatement as rein
from suiteview.polview.ui import main_window
from suiteview.polview.ui.main_window import GetPolicyWindow
from suiteview.polview.ui.tabs import reinstatement_tab
from suiteview.polview.ui.tabs.policy_support_tab import PolicySupportTab
from suiteview.polview.ui.tabs.reinstatement_tab import ReinstatementTab

YEARS = 40
TODAY = date(2026, 10, 7)


def synthetic_basis(code="1", **policy_changes):
    values = dict(
        policy_number="SYNTHETIC", plancode="SYNTHETIC", product_type="UL",
        issue_date=date(2015, 3, 15), valuation_date=date(2026, 2, 15),
        issue_age=40, maturity_age=121, face_amount=100000.0, units=100.0,
        account_value=-25.0, premiums_paid_to_date=12000.0, ctp=1200.0,
        map_cease_date=date(2025, 3, 15),
        segments=[CoverageSegment(
            issue_date=date(2015, 3, 15), issue_age=40, face_amount=100000.0,
            original_face_amount=100000.0, units=100.0, rate_sex="M", rate_class="N")],
    )
    values.update(policy_changes)
    rates = IllustrationRates(
        segment_coi={1: [None] + [0.12] * YEARS},
        segment_epu={1: [None] + [0.05] * YEARS},
        segment_scr={1: [None] + [10.0 - 0.5 * year for year in range(YEARS)]},
        mfee=[None] + [7.5] * YEARS,
        tpp=[None] + [0.05] * YEARS,
        epp=[None] + [0.05] * YEARS,
    )
    return rein.build_reinstatement_basis(
        IllustrationPolicyData(**values), PlancodeConfig(plancode="SYNTHETIC"), rates,
        eligibility=rein.ReinstatementEligibility("Q", "Termination - Lapse", True, "Eligible"),
        lapse_date=date(2026, 3, 15), today=TODAY, reinstatement_code=code,
    )


def lapsed_policy(**changes):
    values = dict(exists=True, product_type="UL", last_entry_code="Q", policy_number="SYNTHETIC")
    values.update(changes)
    return SimpleNamespace(**values)


@pytest.fixture
def loader(monkeypatch):
    load = Mock(side_effect=lambda *_a, **_k: synthetic_basis())
    monkeypatch.setattr(reinstatement_tab, "load_reinstatement_basis", load)
    return load


@pytest.fixture
def tab(qtbot, loader):
    widget = ReinstatementTab()
    qtbot.addWidget(widget)
    return widget


@pytest.fixture
def host(qtbot, loader):
    class Host(QWidget):
        _show_reinstatement_tab = GetPolicyWindow._show_reinstatement_tab
        _clear_reinstatement_tab = GetPolicyWindow._clear_reinstatement_tab
        _insert_aux_tab = GetPolicyWindow._insert_aux_tab

    widget = Host()
    qtbot.addWidget(widget)
    widget._policy = lapsed_policy()
    widget._show_status = Mock()
    widget.tabs = QTabWidget(widget)
    widget.policy_support_tab = PolicySupportTab()
    widget.raw_table_tab = QWidget()
    widget.reinstatement_tab = None
    widget.tabs.addTab(widget.policy_support_tab, "Policy Support")
    widget.tabs.addTab(widget.raw_table_tab, "Raw Table")
    widget.policy_support_tab.reinstatement_requested.connect(widget._show_reinstatement_tab)
    return widget


def test_button_opens_one_top_level_tab_and_repeat_click_reloads(host, qtbot, loader):
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
    assert loader.call_count == 2


@pytest.mark.parametrize("product", ["WL", "TERM", "ISWL", "VUL", "ANNUITY"])
def test_non_ul_click_shows_popup_without_creating_tab(host, monkeypatch, product, loader):
    host._policy.product_type = product
    popup = Mock()
    monkeypatch.setattr(main_window.QMessageBox, "information", popup)
    host.policy_support_tab._btn_reinstatement.click()
    assert popup.call_args.args[2] == "Currently reinstatement quotes are only available for ULs"
    assert host.reinstatement_tab is None
    loader.assert_not_called()


def test_no_policy_prompts_without_creating_tab(host, monkeypatch, loader):
    host._policy = None
    popup = Mock()
    monkeypatch.setattr(main_window.QMessageBox, "information", popup)
    host.policy_support_tab._btn_reinstatement.click()
    assert "load a policy" in popup.call_args.args[2]
    assert host.reinstatement_tab is None
    loader.assert_not_called()


def test_lapse_values_deduction_and_premium_are_displayed(tab):
    tab.load_policy(lapsed_policy(), today=TODAY)
    assert tab.entry_label.text() == "Last entry: Q - Termination - Lapse"
    lapse = tab.lapse_panel
    assert lapse.text("lapse_date") == "3/15/2026"
    assert lapse.text("account_value") == "-25.00"
    assert lapse.text("loan_balance") == "0.00"
    assert lapse.text("surrender_charge") == "500.00"
    assert lapse.text("snet_expiry") == "3/15/2025"
    assert lapse.text("ccv_cease") == "N/A"
    assert tab.selected_date() == date(2026, 9, 15)
    assert isinstance(tab.date_edit, QComboBox)
    assert [tab.date_edit.itemText(i) for i in range(tab.date_edit.count())] == [
        "04/15/2026", "05/15/2026", "06/15/2026", "07/15/2026", "08/15/2026", "09/15/2026",
        "10/15/2026"]
    assert tab.date_edit.currentText() == "09/15/2026"
    deduction = tab.deduction_panel
    assert deduction.title() == "Monthly Deduction"
    assert deduction.text("deduction_date") == "9/15/2026"
    assert deduction.text("base_coi") == "12.00"
    assert deduction.text("fee_total") == "12.50"
    assert deduction.text("total") == "24.50"
    premium = tab.premium_panel
    assert [premium.labels[key].text() for key in premium.values] == [
        "Account value", "Policy debt", "Surrender charge", "2 \u00d7 COI", "2 \u00d7 Fees",
        "Subtotal", "Premium load (5.00%)",
    ]
    assert premium.text("surrender_charge") == "450.00"
    assert premium.text("subtotal") == "524.00"
    assert premium.text("premium_load") == "27.58"
    assert tab.premium_label.text() == "$551.58"
    assert "02/15/2026" in tab.notes_label.text()


def test_choosing_another_monthliversary_reprices_without_reloading(tab, loader):
    tab.load_policy(lapsed_policy(), today=TODAY)
    tab.date_edit.setCurrentIndex(tab.date_edit.findText("04/15/2026"))
    assert loader.call_count == 1
    assert tab.selected_date() == date(2026, 4, 15)
    assert tab.deduction_panel.text("deduction_date") == "4/15/2026"
    assert tab.deduction_panel.text("duration") == "12 / 2"
    tab.date_edit.setCurrentIndex(tab.date_edit.findText("10/15/2026"))
    assert tab.deduction_panel.text("duration") == "12 / 8"


def test_non_lapsed_policy_never_loads_or_quotes(tab, loader):
    tab.load_policy(lapsed_policy(last_entry_code="P", get_live_transactions=lambda codes: [
        SimpleNamespace(trans_code="SF", trans_date=date(2026, 1, 1), gross_amount=Decimal("1"))]),
        today=TODAY)
    assert "Termination - Surrender" in tab.entry_label.text()
    assert "full surrender" in tab.status_label.text()
    assert not tab.date_edit.isEnabled() and not tab.calculate_button.isEnabled()
    assert tab.premium_label.text() == ""
    loader.assert_not_called()


def test_load_failure_is_explained_and_shows_no_values(tab, loader, caplog):
    loader.side_effect = rein.ReinstatementError("The lapse date is not available")
    tab.load_policy(lapsed_policy(), today=TODAY)
    assert "lapse date is not available" in tab.status_label.text()
    assert tab.lapse_panel.text("account_value") == ""
    assert not tab.date_edit.isEnabled()
    assert "Reinstatement basis unavailable" in caplog.text


def test_quote_failure_clears_the_previous_quote(tab, monkeypatch, caplog):
    tab.load_policy(lapsed_policy(), today=TODAY)
    monkeypatch.setattr(tab._basis.__class__, "quote",
                        Mock(side_effect=rein.ReinstatementError("rates are missing")))
    tab.calculate_button.click()
    assert tab._quote is None
    assert tab.premium_label.text() == "Unavailable"
    assert tab.premium_panel.text("subtotal") == ""
    assert tab.lapse_panel.text("account_value") == "-25.00"
    assert "rates are missing" in tab.status_label.text()
    assert "Reinstatement quote unavailable" in caplog.text


def test_zero_premium_remains_explicit(tab, loader):
    loader.side_effect = lambda *_a, **_k: synthetic_basis(account_value=5000.0)
    tab.load_policy(lapsed_policy(), today=TODAY)
    assert tab.premium_label.text() == "$0.00"
    assert "no reinstatement premium" in tab.notes_label.text()


def test_skipped_coverage_panel_mirrors_values_after_reinstatement(tab):
    tab.load_policy(lapsed_policy(), today=TODAY)
    panel = tab.skipped_panel
    assert panel.title() == "Skipped Coverage Reinstatement"
    assert "does not apply if you do a home office reinstatement" in panel.findChild(
        QLabel, options=Qt.FindChildOption.FindChildrenRecursively).text()
    assert panel.text("code") == "1"
    assert "effective_date" not in panel.values
    assert panel.labels["values_date"].text() == "Values as of Reinstatement Date"
    assert panel.text("values_date") == "9/15/2026"
    assert [panel.labels[key].text() for key in ("net_premium", "monthly_deduction", "account_value")] == [
        "Reinstatement premium (net)", "Approx monthly deduction", "Approx account value (after MD)"]
    assert list(panel.values)[:8] == [
        "code", "values_date", "net_premium", "monthly_deduction",
        "account_value", "loan_balance", "surrender_charge", "surrender_value"]
    for key in ("account_value", "surrender_value"):
        assert "bold" in panel.labels[key].styleSheet() and "bold" in panel.values[key].styleSheet()
    assert "bold" not in panel.labels["loan_balance"].styleSheet()
    assert panel.text("net_premium") == "524.00"  # premium 551.58 less load 27.58
    assert panel.text("monthly_deduction") == "24.50"
    assert panel.text("account_value") == "474.50"  # -25.00 + 524.00 - 24.50
    assert panel.text("loan_balance") == "0.00"
    assert panel.text("surrender_charge") == "450.00"
    assert panel.text("surrender_value") == "24.50"  # 474.50 - 450.00 - 0.00
    # Code <> 3: SNET (3/15/2025) was already past termination; CCV is N/A (no CCV benefit).
    assert panel.text("snet_expiry") == "3/15/2025"
    assert panel.text("ccv_cease") == "N/A"
    assert panel.text("terminated_months") == "6"
    assert tab.findChildren(QComboBox) == [tab.date_edit]  # the code is not user-selectable


def test_code_three_from_segment_66_extends_snet_by_the_terminated_months(tab, loader):
    loader.side_effect = lambda *_a, **_k: synthetic_basis(code="3")
    tab.load_policy(lapsed_policy(), today=TODAY)
    assert tab.skipped_panel.text("code") == "3"
    assert tab.skipped_panel.text("snet_expiry") == "9/15/2025"


def test_copy_text_contains_the_whole_quote(tab):
    tab.load_policy(lapsed_policy(), today=TODAY)
    text = tab.copy_text()
    assert "Values at Lapse" in text and "Reinstatement Premium" in text
    assert "Subtotal: 524.00" in text and "Reinstatement premium: $551.58" in text
    assert tab.premium_panel.values["subtotal"]._copy_text_provider() == text


def test_policy_reload_closes_and_clears_old_quote(host):
    host._show_reinstatement_tab()
    tab = host.reinstatement_tab
    host._policy = None
    GetPolicyWindow._prepare_policy_tabs(host)
    assert host.tabs.indexOf(tab) == -1
    assert tab._quote is None and tab._basis is None and tab._policy is None
    assert tab.premium_label.text() == ""
    assert tab.lapse_panel.text("lapse_date") == ""
