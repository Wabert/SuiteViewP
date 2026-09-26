import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
from PyQt6.QtWidgets import QApplication
from suiteview.audit.cyberlife_query import build_cyberlife_sql
from suiteview.audit.tabs.adv_tab import AdvTab
from suiteview.audit.tabs.benefits_tab import BenefitsTab
from suiteview.audit.tabs.coverages_tab import CoveragesTab
from suiteview.audit.tabs.display_tab import DisplayTab
from suiteview.audit.tabs.plancode_tab import PlancodeTab
from suiteview.audit.tabs.policy2_tab import Policy2Tab
from suiteview.audit.tabs.policy_tab import PolicyTab
from suiteview.audit.tabs.transaction_tab import TransactionTab
from tests.audit_criteria_helpers import collect_audit_criteria
_QT_APP = None

def _app():
    global _QT_APP
    _QT_APP = QApplication.instance() or QApplication([])
    return _QT_APP

def _build(coverages_tab):
    return build_cyberlife_sql(collect_audit_criteria('DB2TAB', '', '25', policy_tab=PolicyTab(), display_tab=DisplayTab(), policy2_tab=Policy2Tab(), adv_tab=AdvTab(), coverages_tab=coverages_tab, plancode_tab=PlancodeTab(), benefits_tab=BenefitsTab(), transaction_tab=TransactionTab()))

def test_cease_code_widget_present_in_all_three_columns():
    _app()
    cov = CoveragesTab()
    assert 'cease_code' in cov.base_cov_widgets
    assert 'cease_code' in cov.rider1_widgets
    assert 'cease_code' in cov.rider2_widgets
    ms = cov.base_cov_widgets['cease_code']
    assert ms.list_widget.count() == 10
    assert ms.list_widget.item(0).text() == ''

def test_base_cease_code_adds_in_predicate():
    _app()
    cov = CoveragesTab()
    cov.base_cov_widgets['cease_code'].setText('L, Q')
    sql = _build(cov)
    assert "COVERAGE1.CEA_REA_CD IN ('L', 'Q')" in sql

def test_base_cease_code_blank_matches_no_cease():
    _app()
    cov = CoveragesTab()
    cov.base_cov_widgets['cease_code'].setText('')
    ms = cov.base_cov_widgets['cease_code']
    ms.list_widget.item(0).setSelected(True)
    ms._update_display_text()
    sql = _build(cov)
    assert "TRIM(COVERAGE1.CEA_REA_CD) = ''" in sql

def test_base_cease_code_blank_plus_codes_ored():
    _app()
    cov = CoveragesTab()
    ms = cov.base_cov_widgets['cease_code']
    ms.setText('M')
    ms.list_widget.item(0).setSelected(True)
    ms._update_display_text()
    sql = _build(cov)
    assert "(COVERAGE1.CEA_REA_CD IN ('M') OR TRIM(COVERAGE1.CEA_REA_CD) = '')" in sql

def test_rider_cease_code_adds_join_condition():
    _app()
    cov = CoveragesTab()
    cov.rider1_widgets['cease_code'].setText('P')
    sql = _build(cov)
    assert "AND (RIDER1.CEA_REA_CD IN ('P'))" in sql

def test_no_cease_selection_adds_no_predicate():
    _app()
    cov = CoveragesTab()
    sql = _build(cov)
    assert 'CEA_REA_CD' not in sql

def test_cease_code_round_trips_in_state():
    _app()
    cov = CoveragesTab()
    cov.base_cov_widgets['cease_code'].setText('L, S')
    restored = CoveragesTab()
    restored.set_state(cov.get_state())
    vals = set(restored.base_cov_widgets['cease_code'].selected_values())
    assert vals == {'L', 'S'}
