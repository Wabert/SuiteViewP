import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

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


def test_transaction_types_support_multiple_selections():
    _app()
    tab = TransactionTab()

    tab.transaction_types.setText("SI, SF")

    assert set(tab.transaction_types.selected_values()) == {"SI", "SF"}
    assert set(tab.get_state()["transaction_types"].split(", ")) == {"SI", "SF"}


def test_transaction_types_restore_saved_selection():
    _app()
    tab = TransactionTab()

    tab.set_state({"transaction_types": "TD, TM"})

    assert set(tab.transaction_types.selected_values()) == {"TD", "TM"}


def test_termination_display_includes_effective_date_and_transaction_types():
    _app()
    display_tab = DisplayTab()
    display_tab.chk_termination_date.setChecked(True)

    sql = build_cyberlife_sql(
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

    assert "VARCHAR_FORMAT(TD.TERM_ENTRY_DT, 'MM/DD/YYYY') TERM_ENTRY_DT" in sql
    assert "VARCHAR_FORMAT(TD.TERM_EFFECTIVE_DT, 'MM/DD/YYYY') TERM_EFFECTIVE_DT" in sql
    assert "TD.TERM_TRANS_TYPES" in sql
    assert "LISTAGG" not in sql
    assert "MAX(CASE WHEN TRANS = 'TD' THEN 1 ELSE 0 END) AS HAS_TD" in sql
    assert "SUBSTR(" in sql


def test_plancode_list_defaults_to_all_coverages_match():
    _app()
    plancode_tab = PlancodeTab()
    plancode_tab.list_plancodes.addItem("ABC123")

    sql = build_cyberlife_sql(
        "DB2TAB",
        "",
        "25",
        policy_tab=PolicyTab(),
        display_tab=DisplayTab(),
        policy2_tab=Policy2Tab(),
        adv_tab=AdvTab(),
        coverages_tab=CoveragesTab(),
        plancode_tab=plancode_tab,
        benefits_tab=BenefitsTab(),
        transaction_tab=TransactionTab(),
    )

    assert "COVSALL.PLN_DES_SER_CD IN ('ABC123')" in sql


def test_plancode_list_can_force_cov1_only_match():
    _app()
    plancode_tab = PlancodeTab()
    plancode_tab.list_plancodes.addItem("ABC123")
    plancode_tab.chk_cov1_plancode_match_only.setChecked(True)

    sql = build_cyberlife_sql(
        "DB2TAB",
        "",
        "25",
        policy_tab=PolicyTab(),
        display_tab=DisplayTab(),
        policy2_tab=Policy2Tab(),
        adv_tab=AdvTab(),
        coverages_tab=CoveragesTab(),
        plancode_tab=plancode_tab,
        benefits_tab=BenefitsTab(),
        transaction_tab=TransactionTab(),
    )

    assert "COVERAGE1.PLN_DES_SER_CD IN ('ABC123')" in sql
    assert "COVSALL.PLN_DES_SER_CD IN ('ABC123')" not in sql


def test_plancode_tab_state_persists_cov1_only_flag():
    _app()
    plancode_tab = PlancodeTab()
    plancode_tab.chk_cov1_plancode_match_only.setChecked(True)

    state = plancode_tab.get_state()
    restored = PlancodeTab()
    restored.set_state(state)

    assert restored.chk_cov1_plancode_match_only.isChecked()