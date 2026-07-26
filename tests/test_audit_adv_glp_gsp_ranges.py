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


def _build(adv_tab: AdvTab, display_tab: DisplayTab | None = None):
    return build_cyberlife_sql(
        "DB2TAB",
        "",
        "25",
        policy_tab=PolicyTab(),
        display_tab=display_tab or DisplayTab(),
        policy2_tab=Policy2Tab(),
        adv_tab=adv_tab,
        coverages_tab=CoveragesTab(),
        plancode_tab=PlancodeTab(),
        benefits_tab=BenefitsTab(),
        transaction_tab=TransactionTab(),
    )


def _select_head(sql: str) -> str:
    return sql.split("\nFROM ", 1)[0]


def test_glp_range_adds_where_join_and_result_column():
    _app()
    adv = AdvTab()
    adv.rng_glp[0].setText("100")
    adv.rng_glp[1].setText("500")

    sql = _build(adv)
    head = _select_head(sql)

    assert "GLP.GLP_VALUE >= 100.0" in sql
    assert "GLP.GLP_VALUE <= 500.0" in sql
    assert "INNER JOIN GLP" in sql
    assert "  , GLP.GLP_VALUE" in head


def test_gsp_range_adds_where_join_and_result_column():
    _app()
    adv = AdvTab()
    adv.rng_gsp[0].setText("1000")

    sql = _build(adv)
    head = _select_head(sql)

    assert "GSP.GSP_VALUE >= 1000.0" in sql
    assert "INNER JOIN GSP" in sql
    assert "  , GSP.GSP_VALUE" in head


def test_adv_tab_state_round_trips_glp_and_gsp_ranges():
    _app()
    adv = AdvTab()
    adv.rng_glp[0].setText("123")
    adv.rng_glp[1].setText("456")
    adv.rng_gsp[0].setText("789")
    adv.rng_gsp[1].setText("987")

    restored = AdvTab()
    restored.set_state(adv.get_state())

    assert restored.rng_glp[0].text() == "123"
    assert restored.rng_glp[1].text() == "456"
    assert restored.rng_gsp[0].text() == "789"
    assert restored.rng_gsp[1].text() == "987"
