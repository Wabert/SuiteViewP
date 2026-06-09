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