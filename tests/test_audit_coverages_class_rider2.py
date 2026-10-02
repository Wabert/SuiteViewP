"""Coverages tab: per-coverage Class (02), optional Rider 2 and Total Curr Spec Amt."""
import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
from PyQt6.QtWidgets import QApplication, QGroupBox
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


def _build(coverages_tab, coverage_level=False):
    return build_cyberlife_sql(collect_audit_criteria(
        'DB2TAB', '', '25', policy_tab=PolicyTab(), display_tab=DisplayTab(),
        policy2_tab=Policy2Tab(), adv_tab=AdvTab(), coverages_tab=coverages_tab,
        plancode_tab=PlancodeTab(), benefits_tab=BenefitsTab(),
        transaction_tab=TransactionTab(), coverage_level=coverage_level))


def test_base_class_lives_in_base_column_and_filters_coverage1():
    _app()
    cov = CoveragesTab()
    assert cov.grp_base_cov.isAncestorOf(cov.val_class)
    assert 'class_code' not in cov.base_cov_widgets
    cov.val_class.setText('1, 2')
    sql = _build(cov)
    assert "COVERAGE1.INS_CLS_CD IN ('1', '2')" in sql
    assert 'COVERAGE1.INS_CLS_CD ValClass' in sql


def test_rider_class_filters_rider_join_and_displays_at_coverage_level():
    _app()
    cov = CoveragesTab()
    cov.rider1_widgets['class_code'].setText('5')
    cov.rider2_widgets['class_code'].setText('6, 8')
    sql = _build(cov, coverage_level=True)
    assert "AND RIDER1.INS_CLS_CD IN ('5')" in sql
    assert "AND RIDER2.INS_CLS_CD IN ('6', '8')" in sql
    assert 'RIDER1.INS_CLS_CD Rider1Class' in sql
    assert 'RIDER2.INS_CLS_CD Rider2Class' in sql
    assert 'COVERAGE1.INS_CLS_CD' not in sql


def test_no_class_selection_adds_no_class_predicate():
    _app()
    assert 'INS_CLS_CD' not in _build(CoveragesTab())


def test_rider2_hidden_until_plus_and_remove_clears_it():
    _app()
    cov = CoveragesTab()
    assert not cov.rider2_visible()
    assert not cov.btn_add_rider2.isHidden()
    cov.btn_add_rider2.click()
    assert cov.rider2_visible()
    assert cov.btn_add_rider2.isHidden()
    cov.rider2_widgets['plancode'].setText('1U535A00')
    cov.rider2_widgets['class_code'].setText('5')
    assert 'RIDER2' in _build(cov)
    cov.grp_rider2.btn_remove.click()
    assert not cov.rider2_visible()
    assert not cov.btn_add_rider2.isHidden()
    assert cov.rider2_widgets['plancode'].text() == ''
    assert 'RIDER2' not in _build(cov)


def test_saved_state_restores_rider2_visibility_and_class():
    _app()
    cov = CoveragesTab()
    cov.btn_add_rider2.click()
    cov.rider1_widgets['class_code'].setText('2')
    cov.rider2_widgets['class_code'].setText('5')
    state = cov.get_state()
    assert state['rider1']['class_code'] == '2'
    restored = CoveragesTab()
    restored.set_state(state)
    assert restored.rider2_visible()
    assert restored.rider2_widgets['class_code'].selected_values() == ['5']
    restored.set_state({})
    assert not restored.rider2_visible()


def test_saved_val_class_key_still_restores_base_class():
    _app()
    restored = CoveragesTab()
    restored.set_state({'val_class': '1, 2, 3, 4'})
    assert set(restored.val_class.selected_values()) == {'1', '2', '3', '4'}


def test_total_curr_specified_amount_sums_base_coverages():
    _app()
    cov = CoveragesTab()
    titles = {box.title() for box in cov.findChildren(QGroupBox)}
    assert 'Total Curr Specified Amt (Sum 02)' in titles
    cov.txt_spec_amt_lo.setText('100000')
    sql = _build(cov)
    assert 'SUM(ALL_BASE_COVS.SPECAMT) TOTAL_SA' in sql
    assert 'COVSUMMARY.TOTAL_SA >= 100000' in sql
