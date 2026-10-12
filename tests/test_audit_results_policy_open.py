"""Double-click / "Open in Rerun" behaviour shared by Results and Build SQL Results."""
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pandas as pd
import pytest
from PyQt6.QtWidgets import QApplication, QMenu

from suiteview.audit import audit_window
from suiteview.audit.tabs.build_sql_results_tab import BuildSqlResultsTab
from suiteview.audit.tabs.results_tab import ResultsTab


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


def _double_click(tab, row=0, column=0):
    view = tab.table.table_view
    view.doubleClicked.emit(view.model().index(row, column))


@pytest.mark.parametrize("tab_cls", [ResultsTab, BuildSqlResultsTab])
@pytest.mark.parametrize("columns,expected", [
    ({"ISSUESTATE": ["TX"], "POLICYNUMBER": [" 1U144200 "], "COMPANYCODE": ["01"]}, ("1U144200", "01")),
    ({"Pol": ["123"], "Co": ["26"]}, ("123", "26")),
    ({"CK_POLICY_NBR": ["UE000123  "], "CK_CMP_CD": ["04"]}, ("UE000123", "04")),
    ({"PolicyNumber": ["123"]}, ("123", "")),
])
def test_double_click_emits_policy_and_company(app, tab_cls, columns, expected):
    tab = tab_cls()
    emitted = []
    tab.policy_double_clicked.connect(lambda *args: emitted.append(args))
    tab.set_results(pd.DataFrame(columns))
    _double_click(tab, column=len(columns) - 1)
    assert emitted == [expected]


@pytest.mark.parametrize("tab_cls", [ResultsTab, BuildSqlResultsTab])
def test_double_click_without_policy_column_does_nothing(app, tab_cls):
    tab = tab_cls()
    emitted = []
    tab.policy_double_clicked.connect(lambda *args: emitted.append(args))
    tab.set_results(pd.DataFrame({"PLANCODE": ["1U144200"]}))
    _double_click(tab)
    assert emitted == []


@pytest.mark.parametrize("tab_cls", [ResultsTab, BuildSqlResultsTab])
@pytest.mark.parametrize("is_ul", [True, False])
def test_context_menu_offers_rerun_only_for_ul(app, tab_cls, is_ul):
    tab = tab_cls()
    opened = []
    tab.open_in_rerun.connect(lambda *args: opened.append(args))
    tab.set_ul_checker(lambda policy, company: is_ul)
    tab.set_results(pd.DataFrame({"PolicyNumber": ["123"], "CompanyCode": ["01"]}))
    menu = QMenu()
    tab.table.context_menu_hook(menu, tab.table.table_view.model().index(0, 0))
    action = [a for a in menu.actions() if "Open in Rerun" in a.text()][0]
    assert action.isEnabled() is is_ul
    action.trigger()
    assert opened == ([("123", "01")] if is_ul else [])


def test_audit_window_build_sql_results_opens_polview_and_rerun(app, monkeypatch):
    opened, reruns = [], []
    monkeypatch.setattr(audit_window, "load_ui_settings", lambda: {})
    monkeypatch.setattr(audit_window, "save_ui_settings", lambda settings: None)
    monkeypatch.setattr(audit_window.AuditWindow, "_open_polview_with_policy",
                        lambda self, policy, company: opened.append((policy, company)))
    monkeypatch.setattr(audit_window.AuditWindow, "_open_rerun_with_policy",
                        lambda self, policy, company: reruns.append((policy, company)))
    monkeypatch.setattr(audit_window.AuditWindow, "_is_policy_ul",
                        lambda self, policy, company: True)
    window = audit_window.AuditWindow()
    try:
        tab = window.build_sql_results_tab
        tab.set_results(pd.DataFrame({"POLICYNUMBER": ["1U144200"], "COMPANYCODE": ["01"]}))
        _double_click(tab)
        assert opened == [("1U144200", "01")]
        menu = QMenu()
        tab.table.context_menu_hook(menu, tab.table.table_view.model().index(0, 0))
        [a for a in menu.actions() if a.text() == "📈 Open in Rerun"][0].trigger()
        assert reruns == [("1U144200", "01")]
    finally:
        window.close()
        window.deleteLater()
