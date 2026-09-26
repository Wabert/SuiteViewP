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

def _build(coverage_level=False, coverage_scope='All Covs'):
    return build_cyberlife_sql(collect_audit_criteria('DB2TAB', '', '25', policy_tab=PolicyTab(), display_tab=DisplayTab(), policy2_tab=Policy2Tab(), adv_tab=AdvTab(), coverages_tab=CoveragesTab(), plancode_tab=PlancodeTab(), benefits_tab=BenefitsTab(), transaction_tab=TransactionTab(), coverage_level=coverage_level, coverage_scope=coverage_scope))

def test_all_covs_adds_no_scope_filter():
    _app()
    sql = _build(coverage_level=True, coverage_scope='All Covs')
    assert 'RESULTCOV.COV_PHA_NBR = 1' not in sql
    assert 'RESULTCOV.COV_PHA_NBR > 1' not in sql

def test_cov1_only_filters_to_base_coverage():
    _app()
    sql = _build(coverage_level=True, coverage_scope='Cov 1 only')
    assert 'RESULTCOV.COV_PHA_NBR = 1' in sql

def test_covs_2plus_only_filters_to_riders():
    _app()
    sql = _build(coverage_level=True, coverage_scope='Covs 2+ only')
    assert 'RESULTCOV.COV_PHA_NBR > 1' in sql

def test_scope_ignored_when_coverage_level_off():
    _app()
    sql = _build(coverage_level=False, coverage_scope='Cov 1 only')
    assert 'RESULTCOV' not in sql
    assert 'COV_PHA_NBR = 1' not in sql.replace('C1.COV_PHA_NBR = 1', '')

def test_default_scope_is_all_covs():
    _app()
    sql = _build(coverage_level=True)
    assert 'RESULTCOV.COV_PHA_NBR = 1' not in sql
    assert 'RESULTCOV.COV_PHA_NBR > 1' not in sql
