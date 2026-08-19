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

_QT_APP = None


def _app():
    global _QT_APP
    _QT_APP = QApplication.instance() or QApplication([])
    return _QT_APP


def _build(display_tab):
    return build_cyberlife_sql(
        "DB2TAB",
        "",
        "25",
        policy_tab=PolicyTab(),
        display_tab=display_tab,
        policy2_tab=Policy2Tab(),
        adv_tab=AdvTab(),
        coverages_tab=CoveragesTab(),
        plancode_tab=PlancodeTab(),
        benefits_tab=BenefitsTab(),
        transaction_tab=TransactionTab(),
    )


def test_no_active_columns_when_unchecked():
    _app()
    sql = _build(DisplayTab())
    assert "ActiveBenefits" not in sql
    assert "ActiveRiders" not in sql


def test_active_benefits_list_adds_correlated_subquery():
    _app()
    dt = DisplayTab()
    dt.chk_active_benefits.setChecked(True)
    sql = _build(dt)

    # Correlated scalar subquery, not a whole-table LISTAGG CTE
    assert "ACTIVE_BENEFITS AS (" not in sql
    assert "LISTAGG(TRIM(BNF.SPM_BNF_TYP_CD) || TRIM(BNF.SPM_BNF_SBY_CD)" in sql
    assert "FROM DB2TAB.LH_SPM_BNF BNF" in sql
    # correlated to the outer policy
    assert "BNF.TCH_POL_ID = POLICY1.TCH_POL_ID" in sql
    assert ") ActiveBenefits" in sql
    # riders unaffected
    assert "ActiveRiders" not in sql


def test_active_rider_list_adds_correlated_subquery():
    _app()
    dt = DisplayTab()
    dt.chk_active_riders.setChecked(True)
    sql = _build(dt)

    assert "ACTIVE_RIDERS AS (" not in sql
    assert "FROM DB2TAB.LH_COV_PHA RIDER" in sql
    assert "RIDER.COV_PHA_NBR > 1" in sql
    # correlated to the outer policy
    assert "RIDER.TCH_POL_ID = POLICY1.TCH_POL_ID" in sql
    # excludes base plancode increases
    assert "TRIM(RIDER.PLN_DES_SER_CD) <> TRIM(COVERAGE1.PLN_DES_SER_CD)" in sql
    assert ") ActiveRiders" in sql
    # benefits unaffected
    assert "ActiveBenefits" not in sql


def test_both_lists_together():
    _app()
    dt = DisplayTab()
    dt.chk_active_benefits.setChecked(True)
    dt.chk_active_riders.setChecked(True)
    sql = _build(dt)

    assert ") ActiveBenefits" in sql
    assert ") ActiveRiders" in sql
    # No JOINs added for these (correlated subqueries live in the SELECT list)
    assert "LEFT OUTER JOIN ACTIVE_BENEFITS" not in sql
    assert "LEFT OUTER JOIN ACTIVE_RIDERS" not in sql


def test_new_checkboxes_persist_in_state():
    _app()
    dt = DisplayTab()
    dt.chk_active_benefits.setChecked(True)
    state = dt.get_state()
    assert state["chk_active_benefits"] is True

    restored = DisplayTab()
    restored.set_state(state)
    assert restored.chk_active_benefits.isChecked() is True
    assert restored.chk_active_riders.isChecked() is False
