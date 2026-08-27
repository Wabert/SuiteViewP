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


def _build(policy2_tab: Policy2Tab, display_tab: DisplayTab | None = None) -> str:
    return build_cyberlife_sql(
        "DB2TAB",
        "",
        "25",
        policy_tab=PolicyTab(),
        display_tab=display_tab or DisplayTab(),
        policy2_tab=policy2_tab,
        adv_tab=AdvTab(),
        coverages_tab=CoveragesTab(),
        plancode_tab=PlancodeTab(),
        benefits_tab=BenefitsTab(),
        transaction_tab=TransactionTab(),
    )


def test_preferred_loan_filter_returns_regular_and_preferred_debt_columns():
    _app()
    policy2 = Policy2Tab()
    policy2.chk_has_loan.setChecked(True)
    policy2.chk_has_preferred_loan.setChecked(True)

    sql = _build(policy2)

    assert "AND ALL_LOANS.PRF_LN_IND = '1'" in sql
    assert "\n  , POLICYDEBT.REG_LOAN_PRINCIPLE" in sql
    assert "\n  , POLICYDEBT.REG_LOAN_ACCRUED" in sql
    assert "\n  , POLICYDEBT.PREF_LOAN_PRINCIPLE" in sql
    assert "\n  , POLICYDEBT.PREF_LOAN_ACCRUED" in sql
    assert "THEN ALL_LOANS.LN_PRI_AMT ELSE 0 END) REG_LOAN_PRINCIPLE" in sql
    assert "THEN ALL_LOANS.LN_INT ELSE 0 END) PREF_LOAN_ACCRUED" in sql


def test_policy_debt_display_keeps_total_columns_without_preferred_filter():
    _app()
    display = DisplayTab()
    display.chk_policy_debt.setChecked(True)

    sql = _build(Policy2Tab(), display)

    assert "\n  , POLICYDEBT.LOAN_PRINCIPLE" in sql
    assert "\n  , POLICYDEBT.LOAN_ACCRUED" in sql
    assert "\n  , POLICYDEBT.REG_LOAN_PRINCIPLE" not in sql
    assert "\n  , POLICYDEBT.PREF_LOAN_PRINCIPLE" not in sql
