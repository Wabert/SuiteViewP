import os
import re
import sqlite3
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
from suiteview.audit.cyberlife_criteria import collect_audit_criteria
_QT_APP = None

def _app():
    global _QT_APP
    _QT_APP = QApplication.instance() or QApplication([])
    return _QT_APP

def _build(adv_tab: AdvTab, display_tab: DisplayTab | None=None):
    return build_cyberlife_sql(collect_audit_criteria('DB2TAB', '', '25', policy_tab=PolicyTab(), display_tab=display_tab or DisplayTab(), policy2_tab=Policy2Tab(), adv_tab=adv_tab, coverages_tab=CoveragesTab(), plancode_tab=PlancodeTab(), benefits_tab=BenefitsTab(), transaction_tab=TransactionTab()))

def _select_head(sql: str) -> str:
    return sql.split('\nFROM ', 1)[0]

@pytest.mark.parametrize('less,greater,operators,matching', [(False, False, [], ['less', 'equal', 'greater', 'unknown']), (True, False, ['<'], ['less']), (False, True, ['>'], ['greater']), (True, True, ['<', '>'], [])])
def test_current_original_sa_comparisons_are_strict_and_independent(less, greater, operators, matching):
    _app()
    adv = AdvTab()
    adv.chk_sa_lt_orig.setChecked(less)
    adv.chk_sa_gt_orig.setChecked(greater)
    sql = _build(adv)
    predicates = re.findall('\\(COVSUMMARY\\.TOTAL_SA ([<>=]+) COVSUMMARY\\.TOTAL_ORIGINAL_SA\\)', sql)
    assert predicates == operators
    if operators:
        assert 'COVSUMMARY AS (' in sql
        assert 'JOIN COVSUMMARY' in sql
    restored = AdvTab()
    restored.set_state(adv.get_state())
    assert _build(restored) == sql
    where = ' AND '.join((f'COVSUMMARY.TOTAL_SA {op} COVSUMMARY.TOTAL_ORIGINAL_SA' for op in predicates)) or '1=1'
    with sqlite3.connect(':memory:') as db:
        db.execute('CREATE TABLE COVSUMMARY (name TEXT, TOTAL_SA REAL, TOTAL_ORIGINAL_SA REAL)')
        db.executemany('INSERT INTO COVSUMMARY VALUES (?, ?, ?)', [('less', 99.99, 100), ('equal', 100, 100), ('greater', 100.01, 100), ('unknown', None, 100)])
        assert [row[0] for row in db.execute(f'SELECT name FROM COVSUMMARY WHERE {where}')] == matching

def test_switching_sa_comparison_rebuilds_in_the_correct_direction():
    _app()
    adv = AdvTab()
    adv.chk_sa_lt_orig.setChecked(True)
    assert '(COVSUMMARY.TOTAL_SA < COVSUMMARY.TOTAL_ORIGINAL_SA)' in _build(adv)
    adv.chk_sa_lt_orig.setChecked(False)
    adv.chk_sa_gt_orig.setChecked(True)
    sql = _build(adv)
    assert '(COVSUMMARY.TOTAL_SA > COVSUMMARY.TOTAL_ORIGINAL_SA)' in sql
    assert '(COVSUMMARY.TOTAL_SA <' not in sql
    adv.set_state({})
    assert 'COVSUMMARY.TOTAL_ORIGINAL_SA)' not in _build(adv)

def test_glp_range_adds_where_join_and_result_column():
    _app()
    adv = AdvTab()
    adv.rng_glp[0].setText('100')
    adv.rng_glp[1].setText('500')
    sql = _build(adv)
    head = _select_head(sql)
    assert 'GLP.GLP_VALUE >= 100.0' in sql
    assert 'GLP.GLP_VALUE <= 500.0' in sql
    assert 'INNER JOIN GLP' in sql
    assert '  , GLP.GLP_VALUE' in head

def test_gsp_range_adds_where_join_and_result_column():
    _app()
    adv = AdvTab()
    adv.rng_gsp[0].setText('1000')
    sql = _build(adv)
    head = _select_head(sql)
    assert 'GSP.GSP_VALUE >= 1000.0' in sql
    assert 'INNER JOIN GSP' in sql
    assert '  , GSP.GSP_VALUE' in head

def test_adv_tab_state_round_trips_glp_and_gsp_ranges():
    _app()
    adv = AdvTab()
    adv.rng_glp[0].setText('123')
    adv.rng_glp[1].setText('456')
    adv.rng_gsp[0].setText('789')
    adv.rng_gsp[1].setText('987')
    restored = AdvTab()
    restored.set_state(adv.get_state())
    assert restored.rng_glp[0].text() == '123'
    assert restored.rng_glp[1].text() == '456'
    assert restored.rng_gsp[0].text() == '789'
    assert restored.rng_gsp[1].text() == '987'

def test_prem_wd_gt_face_adds_where_joins_and_result_columns():
    _app()
    adv = AdvTab()
    adv.chk_prem_wd_gt_face.setChecked(True)
    sql = _build(adv)
    head = _select_head(sql)
    assert '((POLICY_TOTALS.TOT_REG_PRM_AMT + POLICY_TOTALS.TOT_ADD_PRM_AMT - POLICY_TOTALS.TOT_WTD_AMT) > PREMWD_FACE.TOTAL_FACE)' in sql
    assert 'PREMWD_FACE AS (' in sql
    assert 'INNER JOIN PREMWD_FACE' in sql
    assert 'LH_POL_TOTALS POLICY_TOTALS' in sql
    assert 'LH_NON_TRD_POL NONTRAD' in sql
    assert 'MVVAL AS (' in sql
    assert "TEMPCOVALL.NXT_CHG_TYP_CD <> '0'" in sql
    assert 'TEMPCOVALL.NXT_CHG_DT > CURRENT DATE' in sql
    assert '1U144A00' in sql
    assert '  , (POLICY_TOTALS.TOT_REG_PRM_AMT + POLICY_TOTALS.TOT_ADD_PRM_AMT) PremTD' in head
    assert '  , POLICY_TOTALS.TOT_WTD_AMT AccumWD' in head
    assert '  , PREMWD_FACE.TOTAL_FACE TotalFace' in head
    assert 'REAL(PREMWD_FACE.TOTAL_FACE) + COALESCE(REAL(MVVAL.OPTDB), 0)' in head
    assert 'DeathBenefit' in head
    assert '  , NONTRAD.DTH_BNF_PLN_OPT_CD DBOpt' in head

def test_prem_wd_gt_face_dboption_not_duplicated_with_display():
    _app()
    from suiteview.audit.tabs.display_tab import DisplayTab
    adv = AdvTab()
    adv.chk_prem_wd_gt_face.setChecked(True)
    disp = DisplayTab()
    disp.chk_death_benefit_opt.setChecked(True)
    sql = _build(adv, disp)
    head = _select_head(sql)
    assert head.count('DTH_BNF_PLN_OPT_CD DBOpt') == 1

def test_prem_wd_gt_face_round_trips_in_state():
    _app()
    adv = AdvTab()
    adv.chk_prem_wd_gt_face.setChecked(True)
    restored = AdvTab()
    restored.set_state(adv.get_state())
    assert restored.chk_prem_wd_gt_face.isChecked() is True
