"""COVSALL is an unrestricted LH_COV_PHA join and multiplies the row count by
the coverage count, so it must only appear when a filter actually binds to it.
"""
import os
import pytest
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

def _build(coverage_level=False, plancodes=(), product_line=False, cov_gio=False, policy_plancode='', cov1_only=False):
    plancode_tab = PlancodeTab()
    plancode_tab.chk_cov1_plancode_match_only.setChecked(cov1_only)
    for code in plancodes:
        plancode_tab.plancodes.list_values.addItem(code)
    policy_tab = PolicyTab()
    policy_tab.txt_plancode.setText(policy_plancode)
    if product_line:
        policy_tab.chk_product_line.setChecked(True)
        policy_tab.list_product_line.item(0).setSelected(True)
    coverages_tab = CoveragesTab()
    if cov_gio:
        coverages_tab.chk_cov_gio.setChecked(True)
    return build_cyberlife_sql(collect_audit_criteria('DB2TAB', '', '25', policy_tab=policy_tab, display_tab=DisplayTab(), policy2_tab=Policy2Tab(), adv_tab=AdvTab(), coverages_tab=coverages_tab, plancode_tab=plancode_tab, benefits_tab=BenefitsTab(), transaction_tab=TransactionTab(), coverage_level=coverage_level))

def test_no_covsall_join_when_nothing_references_it():
    _app()
    sql = _build()
    assert 'LH_COV_PHA COVSALL' not in sql

def test_covsall_joined_for_any_coverage_plancode():
    _app()
    sql = _build(plancodes=['8N562900'])
    assert 'LH_COV_PHA COVSALL' in sql
    assert "COVSALL.PLN_DES_SER_CD IN ('8N562900')" in sql

def test_coverage_level_binds_plancode_to_resultcov_without_covsall():
    _app()
    sql = _build(coverage_level=True, plancodes=['8N562900'])
    assert 'COVSALL' not in sql
    assert "RESULTCOV.PLN_DES_SER_CD IN ('8N562900')" in sql

def test_coverage_level_drops_covsall_for_product_line():
    _app()
    sql = _build(coverage_level=True, product_line=True)
    assert 'COVSALL' not in sql
    assert 'RESULTCOV.PRD_LIN_TYP_CD IN (' in sql


@pytest.mark.parametrize('coverage_level,alias', [(False, 'COVERAGE1'), (True, 'RESULTCOV')])
def test_product_line_criterion_adds_result_column_after_company(coverage_level, alias):
    _app()
    lines = [line.strip() for line in _build(coverage_level=coverage_level, product_line=True).splitlines()]
    company = lines.index(', POLICY1.CK_CMP_CD CompanyCode')
    assert lines[company + 1] == f', {alias}.PRD_LIN_TYP_CD ProductLineCode'


def test_no_product_line_result_column_without_criterion():
    _app()
    assert 'ProductLineCode' not in _build()

def test_covsall_kept_when_modcovsall_needs_it():
    _app()
    sql = _build(coverage_level=True, cov_gio=True)
    assert 'LH_COV_PHA COVSALL' in sql
    assert 'MODCOVSALL.CK_SYS_CD = COVSALL.CK_SYS_CD' in sql

@pytest.mark.parametrize('coverage_level,cov1_only,alias', [(False, False, 'COVSALL'), (True, False, 'RESULTCOV'), (False, True, 'COVERAGE1'), (True, True, 'COVERAGE1')])
def test_policy_plancode_exact_match_preserves_coverage_scope(coverage_level, cov1_only, alias):
    _app()
    sql = _build(coverage_level=coverage_level, cov1_only=cov1_only, policy_plancode='  u1f4  ')
    column = f'{alias}.PLN_DES_SER_CD'
    assert f"{column} = 'U1F4'" in sql
    assert ('LH_COV_PHA COVSALL' in sql) == (alias == 'COVSALL')

def test_empty_policy_plancode_adds_no_filter_or_join():
    _app()
    assert _build(policy_plancode='  ') == _build()

def test_exact_plancode_escapes_quotes_and_combines_with_plancode_list():
    _app()
    sql = _build(policy_plancode="a'_%", plancodes=['8N562900'])
    assert "COVSALL.PLN_DES_SER_CD IN ('A''_%', '8N562900')" in sql
    assert "COVSALL.PLN_DES_SER_CD = " not in sql
