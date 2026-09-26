import json
import os
import sqlite3
import pytest
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
from PyQt6.QtCore import QMimeData, Qt
from PyQt6.QtWidgets import QApplication, QCheckBox
from suiteview.audit.cyberlife_query import build_cyberlife_sql
from suiteview.audit.tabs.adv_tab import AdvTab
from suiteview.audit.tabs.benefits_tab import BenefitsTab
from suiteview.audit.tabs.coverages_tab import CoveragesTab
from suiteview.audit.tabs.display_tab import DisplayTab
from suiteview.audit.tabs.plancode_tab import PlancodeTab
from suiteview.audit.tabs.policy2_tab import Policy2Tab
from suiteview.audit.tabs.policy_tab import PolicyTab
from suiteview.audit.tabs.transaction_tab import TransactionTab
from suiteview.audit.cyberlife_criteria import collect_audit_criteria

@pytest.fixture
def tab(qtbot):
    widget = PlancodeTab()
    qtbot.addWidget(widget)
    return widget

@pytest.fixture
def clipboard(qapp):
    clipboard = QApplication.clipboard()
    saved = QMimeData()
    original = clipboard.mimeData()
    if original is not None:
        for fmt in original.formats():
            saved.setData(fmt, original.data(fmt))
    yield clipboard
    clipboard.setMimeData(saved)

@pytest.fixture
def build(tab, qtbot):
    tabs = {'policy_tab': PolicyTab(), 'display_tab': DisplayTab(), 'policy2_tab': Policy2Tab(), 'adv_tab': AdvTab(), 'coverages_tab': CoveragesTab(), 'plancode_tab': tab, 'benefits_tab': BenefitsTab(), 'transaction_tab': TransactionTab()}
    for name, widget in tabs.items():
        if name != 'plancode_tab':
            qtbot.addWidget(widget)

    def make(**kwargs):
        return build_cyberlife_sql(collect_audit_criteria('DB2TAB', '', '25', **tabs, **kwargs))
    return make

@pytest.mark.parametrize('name', ['plancodes', 'policies'])
def test_add_enter_remove_selected_and_remove_all(tab, qtbot, name):
    panel = getattr(tab, name)
    panel.input.setText('  ab001  ')
    assert panel.input.text() == '  AB001  '
    panel.btn_add.click()
    panel.input.setText('ab001')
    qtbot.keyClick(panel.input, Qt.Key.Key_Return)
    panel.input.setText('000289393')
    qtbot.keyClick(panel.input, Qt.Key.Key_Return)
    assert panel.values() == ['AB001', '000289393']
    assert not panel.input.text()
    panel.list_values.item(0).setSelected(True)
    panel.btn_remove_selected.click()
    assert panel.values() == ['000289393']
    panel.btn_remove_all.click()
    assert panel.values() == []
    assert not getattr(tab, 'policies' if name == 'plancodes' else 'plancodes').values()

@pytest.mark.parametrize('name', ['plancodes', 'policies'])
def test_clipboard_excel_delimiters_case_duplicates_and_zeros(tab, clipboard, name):
    panel = getattr(tab, name)
    panel.input.setText('existing')
    panel.btn_add.click()
    clipboard.setText(' ab001\t000289393\r\nAB001\n ; c003,d004 e005\nEXISTING\n')
    panel.btn_paste.click()
    expected = ['EXISTING', 'AB001', '000289393', 'C003', 'D004', 'E005']
    assert panel.values() == expected
    panel.btn_paste.click()
    assert panel.values() == expected
    panel.list_values.item(1).setSelected(True)
    panel.list_values.item(4).setSelected(True)
    panel.btn_remove_selected.click()
    assert panel.values() == ['EXISTING', '000289393', 'C003', 'E005']
    clipboard.setText(' \r\n\t,; ')
    panel.btn_paste.click()
    assert len(panel.values()) == 4

def test_policy_panel_has_no_cov1_checkbox(tab):
    assert not tab.policies.findChildren(QCheckBox)
    assert tab.plancodes.findChildren(QCheckBox) == [tab.chk_cov1_plancode_match_only]

def test_round_trip_and_new_clear_both_lists_and_drafts(tab):
    tab.set_state({'plancodes': ['plan001'], 'policies': ['000289393', 'u0123456'], 'cov1_plancode_match_only': True})
    state = json.loads(json.dumps(tab.get_state()))
    assert state['policies'] == ['000289393', 'U0123456']
    tab.set_state({})
    tab.set_state(state)
    assert tab.get_state() == state
    for panel in (tab.plancodes, tab.policies):
        panel.input.setText('draft')
    tab.set_state({})
    assert tab.get_state() == {'plancodes': [], 'policies': [], 'cov1_plancode_match_only': False}
    assert not tab.plancodes.input.text() and (not tab.policies.input.text())

def test_loading_without_policies_does_not_keep_previous_list(tab):
    tab.set_state({'policies': ['OLD']})
    tab.set_state({'plancodes': ['plan001']})
    assert tab.get_policies() == []
    assert tab.get_plancodes() == ['PLAN001']

@pytest.mark.parametrize('coverage_level', [False, True])
@pytest.mark.parametrize('scope', ['All Covs', 'Cov 1 only', 'Covs 2+ only'])
@pytest.mark.parametrize('cov1_only', [False, True])
def test_policy_list_is_exact_policy_filter_independent_of_coverage(tab, build, coverage_level, scope, cov1_only):
    baseline = build(coverage_level=coverage_level, coverage_scope=scope)
    assert 'POLICY1.CK_POLICY_NBR IN (' not in baseline
    tab.set_state({'policies': ['  u0123456 ', '000289393'], 'cov1_plancode_match_only': cov1_only})
    sql = build(coverage_level=coverage_level, coverage_scope=scope)
    assert "POLICY1.CK_POLICY_NBR IN ('U0123456', '000289393')" in sql
    assert 'COVSALL' not in sql

@pytest.mark.parametrize('coverage_level,cov1_only,alias', [(False, False, 'COVSALL'), (True, False, 'RESULTCOV'), (False, True, 'COVERAGE1'), (True, True, 'COVERAGE1')])
def test_policies_and_plans_are_combined_with_and(tab, build, coverage_level, cov1_only, alias):
    tab.set_state({'plancodes': ['PLAN001'], 'policies': ['U0123456'], 'cov1_plancode_match_only': cov1_only})
    sql = build(coverage_level=coverage_level)
    assert f"{alias}.PLN_DES_SER_CD IN ('PLAN001')" in sql
    assert "\n  AND POLICY1.CK_POLICY_NBR IN ('U0123456')" in sql

def test_policy_list_escapes_quotes_and_keeps_wildcards_literal(tab, build):
    requested = ['000289393', "a'_%"]
    tab.set_state({'policies': requested})
    sql = build()
    predicate = next((line.strip().removeprefix('WHERE ').removeprefix('AND ') for line in sql.splitlines() if 'POLICY1.CK_POLICY_NBR IN (' in line))
    assert "'A''_%'" in predicate
    with sqlite3.connect(':memory:') as db:
        db.execute('CREATE TABLE policies (CK_POLICY_NBR TEXT)')
        db.executemany('INSERT INTO policies VALUES (?)', [('000289393',), ("A'_%",), ("A'XYZ",), ('289393',), ('UNLISTED',)])
        rows = db.execute(f'SELECT CK_POLICY_NBR FROM policies POLICY1 WHERE {predicate}').fetchall()
    assert rows == [('000289393',), ("A'_%",)]

def test_large_clipboard_list_is_not_truncated(tab, clipboard, build):
    policies = [f'U{i:07d}' for i in range(2000)]
    clipboard.setText('\r\n'.join(policies))
    tab.policies.btn_paste.click()
    assert tab.get_policies() == policies
    sql = build()
    assert all((f"'{policy}'" in sql for policy in policies))
