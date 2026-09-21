"""Other Data navigation, lazy queries and per-policy restoration without live data."""

from datetime import date
from types import SimpleNamespace
from unittest.mock import Mock

import pandas as pd
import pytest
from PyQt6.QtCore import QCoreApplication, QEvent
from PyQt6.QtWidgets import QPushButton

from suiteview.polview.ui.main_window import GetPolicyWindow
from suiteview.polview.ui.tabs import claims_tab, cyberlife_pdf_tab, orion_pcr_tab, sap_tab, tai_fd_tab
from suiteview.polview.ui.tabs.other_data_tab import OtherDataTab


@pytest.fixture
def sources(monkeypatch):
    for module in (cyberlife_pdf_tab, orion_pcr_tab, tai_fd_tab):
        monkeypatch.setattr(module, "_ul_rates_available", lambda: True)
    monkeypatch.setattr(sap_tab, "_vrd_prod_available", lambda: True)
    claims = Mock(return_value=pd.DataFrame({
        "Policy_Number": ["SYNTHETIC", "SECOND"],
        "Claim_number": ["DEMO-1", "DEMO-2"],
    }))
    pdf = Mock(return_value=pd.DataFrame({
        "FieldName": ["UserID", "Demo field"], "DEMO": ["TEST", "123"],
    }))
    monkeypatch.setattr(claims_tab.ClaimsTab, "_read_claims_file", claims)
    monkeypatch.setattr(cyberlife_pdf_tab.CyberlifePdfTab, "_run_query", pdf)
    calls = {"CLAIMSFILE": claims, "CYBERLIFE_PDF": pdf}
    for title, cls in (
        ("SAP", sap_tab.SapTab), ("TAICyberTAIFd", tai_fd_tab.TaiFdTab),
        ("orion_pcr3_r", orion_pcr_tab.OrionPcrTab),
    ):
        calls[title] = Mock(return_value=pd.DataFrame({"Demo": ["result"]}))
        monkeypatch.setattr(cls, "_run_query", calls[title])
    return calls


@pytest.fixture
def policy():
    return SimpleNamespace(
        exists=True, policy_number="SYNTHETIC", company_code="01",
        valuation_date=date(2026, 9, 18),
        get_coverages=lambda: [SimpleNamespace(plancode="DEMO")],
    )


@pytest.fixture
def tab(qtbot, sources, policy):
    widget = OtherDataTab()
    qtbot.addWidget(widget)
    widget.resize(1100, 650)
    widget.reset(policy)
    widget.show()
    yield widget
    widget.close()
    widget.deleteLater()
    QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)


def test_sources_embed_without_querying_until_selected(tab, sources):
    assert tab.stack.currentWidget() is tab.empty_page
    for query in sources.values():
        query.assert_not_called()
    for title in ("SAP", "TAICyberTAIFd", "orion_pcr3_r"):
        tab.buttons[title].click()
        page = tab.pages[title]
        assert tab.stack.currentWidget() is page
        assert page.date_from.isVisible() and page.date_to.isVisible()
        assert page.date_from.text()
        sources[title].assert_not_called()
        page.query_btn.click()
        sources[title].assert_called_once()
        assert len(page.grid.model.get_original_data()) == 1
    for title in ("CLAIMSFILE", "CYBERLIFE_PDF"):
        sources[title].assert_not_called()
        tab.buttons[title].click()
        page = tab.pages[title]
        sources[title].assert_called_once()
        assert tab.stack.currentWidget() is page
        assert not page.isWindow()
        assert not page.grid.model.get_original_data().empty
        assert page.query_btn.text() == "Refresh"
        tab.buttons["SAP"].click()
        tab.buttons[title].click()
        sources[title].assert_called_once()
        page.query_btn.click()
        assert sources[title].call_count == 2
    assert sum(button.isChecked() for button in tab.buttons.values()) == 1


def test_restore_retains_inputs_results_and_selection_without_queries(tab, sources, policy):
    tab.buttons["SAP"].click()
    sap = tab.pages["SAP"]
    sap.date_from.setText("01/01/2020")
    sap.date_to.setText("09/01/2026")
    sap.query_btn.click()
    tab.buttons["CLAIMSFILE"].click()
    saved = tab.export_state()
    second = SimpleNamespace(**vars(policy))
    second.policy_number = "SECOND"
    tab.reset(second)
    assert tab.stack.currentWidget() is tab.empty_page
    assert not any(button.isChecked() for button in tab.buttons.values())
    assert all(page.grid.model.get_original_data().empty for page in tab.pages.values())
    tab.buttons["CLAIMSFILE"].click()
    assert tab.pages["CLAIMSFILE"].grid.model.get_original_data()["Claim_number"].tolist() == ["DEMO-2"]
    tab.restore_state(policy, saved)
    assert sources["CLAIMSFILE"].call_count == 2
    assert sources["SAP"].call_count == 1
    assert tab.stack.currentWidget() is tab.pages["CLAIMSFILE"]
    assert tab.pages["CLAIMSFILE"].grid.model.get_original_data()["Claim_number"].tolist() == ["DEMO-1"]
    tab.buttons["SAP"].click()
    assert sap.date_from.text() == "01/01/2020"
    assert sap.date_to.text() == "09/01/2026"
    assert sap.grid.model.get_original_data()["Demo"].tolist() == ["result"]


@pytest.mark.parametrize("title", ["CLAIMSFILE", "CYBERLIFE_PDF", "TAICyberTAIFd", "orion_pcr3_r"])
def test_hidden_page_access_notice_survives_snapshot(tab, policy, title):
    tab.buttons[title].click()
    page = tab.pages[title]
    page._show_no_access()
    tab.buttons["SAP"].click()
    tab.hide()
    state = tab.export_state()
    assert state["pages"][title]["no_access"]
    tab.restore_state(policy, state)
    tab.show()
    tab.buttons[title].click()
    assert page._no_access_label.isVisible()
    assert not page.grid.isVisible()


def test_no_policy_does_not_query_and_new_policy_clears_selection(tab, sources, policy):
    tab.reset()
    for button in tab.buttons.values():
        button.click()
    for query in sources.values():
        query.assert_not_called()
    tab.reset(policy)
    tab.buttons["CYBERLIFE_PDF"].click()
    sources["CYBERLIFE_PDF"].assert_called_once_with(["DEMO"])


def test_empty_and_failed_immediate_sources_show_explicit_states(tab, sources):
    sources["CLAIMSFILE"].return_value = pd.DataFrame()
    tab.buttons["CLAIMSFILE"].click()
    page = tab.pages["CLAIMSFILE"]
    assert "No records" in page.grid.model.get_original_data().iloc[0, 0]
    sources["CLAIMSFILE"].side_effect = PermissionError("Unavailable")
    page.query_btn.click()
    assert page._no_access_label.isVisible()
    sources["CYBERLIFE_PDF"].side_effect = RuntimeError("Synthetic query failure")
    tab.buttons["CYBERLIFE_PDF"].click()
    assert "Synthetic query failure" in tab.pages["CYBERLIFE_PDF"]._status_label.text()


def test_window_has_permanent_other_data_tab_and_policy_scoped_state(qtbot, sources, policy):
    window = GetPolicyWindow(enable_policy_list=False)
    qtbot.addWidget(window)
    tab = window.other_data_tab
    titles = [window.tabs.tabText(i) for i in range(window.tabs.count())]
    assert titles.index("Other Data") == titles.index("Policy Support") + 1
    support_buttons = {b.text() for b in window.policy_support_tab.findChildren(QPushButton)}
    assert not set(tab.pages).intersection(support_buttons)
    window._policy = policy
    window._current_policy = policy.policy_number
    window._current_region = "CKPR"
    window._policy_info = {"CompanyCode": "01"}
    window._reset_aux_tabs()
    tab.buttons["CLAIMSFILE"].click()
    key = window._current_aux_key()
    window._save_current_aux_state()
    tab.reset()
    window._restore_aux_tabs(key)
    assert tab.stack.currentWidget() is tab.pages["CLAIMSFILE"]
    sources["CLAIMSFILE"].assert_called_once()
    assert [window.tabs.tabText(i) for i in range(window.tabs.count())] == titles
    window._reset_aux_tabs(key)
    assert key not in window._aux_tab_state
    assert tab.stack.currentWidget() is tab.empty_page
