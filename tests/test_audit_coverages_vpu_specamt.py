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


def _build(coverages_tab):
    return build_cyberlife_sql(
        "DB2TAB",
        "",
        "25",
        policy_tab=PolicyTab(),
        display_tab=DisplayTab(),
        policy2_tab=Policy2Tab(),
        adv_tab=AdvTab(),
        coverages_tab=coverages_tab,
        plancode_tab=PlancodeTab(),
        benefits_tab=BenefitsTab(),
        transaction_tab=TransactionTab(),
    )


def test_base_coverage_vpu_range_emitted():
    _app()
    cov = CoveragesTab()
    cov.base_cov_widgets["vpu_lo"].setText("100")
    cov.base_cov_widgets["vpu_hi"].setText("500")

    sql = _build(cov)

    assert "COVERAGE1.COV_VPU_AMT >= 100.0" in sql
    assert "COVERAGE1.COV_VPU_AMT <= 500.0" in sql


def test_base_coverage_specified_amount_range_emitted():
    _app()
    cov = CoveragesTab()
    cov.base_cov_widgets["spec_amt_lo"].setText("50000")
    cov.base_cov_widgets["spec_amt_hi"].setText("250000")

    sql = _build(cov)

    assert (
        "(REAL(COVERAGE1.COV_UNT_QTY) * REAL(COVERAGE1.COV_VPU_AMT)) >= 50000.0"
        in sql
    )
    assert (
        "(REAL(COVERAGE1.COV_UNT_QTY) * REAL(COVERAGE1.COV_VPU_AMT)) <= 250000.0"
        in sql
    )


def test_rider_vpu_and_specified_amount_range_emitted():
    _app()
    cov = CoveragesTab()
    cov.rider1_widgets["vpu_lo"].setText("10")
    cov.rider1_widgets["spec_amt_hi"].setText("75000")

    sql = _build(cov)

    assert "RIDER1.COV_VPU_AMT >= 10.0" in sql
    assert (
        "(REAL(RIDER1.COV_UNT_QTY) * REAL(RIDER1.COV_VPU_AMT)) <= 75000.0" in sql
    )
