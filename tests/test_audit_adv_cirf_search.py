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

def _build(adv_tab: AdvTab):
    return build_cyberlife_sql(collect_audit_criteria('DB2TAB', '', '25', policy_tab=PolicyTab(), display_tab=DisplayTab(), policy2_tab=Policy2Tab(), adv_tab=adv_tab, coverages_tab=CoveragesTab(), plancode_tab=PlancodeTab(), benefits_tab=BenefitsTab(), transaction_tab=TransactionTab()))

def test_cirf_contains_builds_exists_like_predicate():
    _app()
    adv = AdvTab()
    adv.cbo_cirf_match.setCurrentText('Contains')
    adv.txt_cirf.setText('abc')
    sql = _build(adv)
    assert 'EXISTS (SELECT 1 FROM DB2TAB.LH_COV_FXD_FND_CTL FFC_SRCH' in sql
    assert 'FFC_SRCH.TCH_POL_ID = POLICY1.TCH_POL_ID' in sql
    assert "UPPER(TRIM(FFC_SRCH.CUR_ITS_RT_SER_NBR)) LIKE '%ABC%'" in sql

def test_cirf_exact_builds_exists_equals_predicate():
    _app()
    adv = AdvTab()
    adv.cbo_cirf_match.setCurrentText('Exact')
    adv.txt_cirf.setText('XY12')
    sql = _build(adv)
    assert "UPPER(TRIM(FFC_SRCH.CUR_ITS_RT_SER_NBR)) = 'XY12'" in sql

def test_cirf_empty_adds_no_predicate():
    _app()
    adv = AdvTab()
    sql = _build(adv)
    assert 'FFC_SRCH' not in sql

def test_cirf_state_round_trips():
    _app()
    adv = AdvTab()
    adv.cbo_cirf_match.setCurrentText('Exact')
    adv.txt_cirf.setText('Z9')
    restored = AdvTab()
    restored.set_state(adv.get_state())
    assert restored.cbo_cirf_match.currentText() == 'Exact'
    assert restored.txt_cirf.text() == 'Z9'
