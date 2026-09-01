"""COVSALL is an unrestricted LH_COV_PHA join and multiplies the row count by
the coverage count, so it must only appear when a filter actually binds to it.
"""
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


def _build(coverage_level=False, plancodes=(), product_line=False, cov_gio=False):
    plancode_tab = PlancodeTab()
    for code in plancodes:
        plancode_tab.list_plancodes.addItem(code)
    policy_tab = PolicyTab()
    if product_line:
        policy_tab.chk_product_line.setChecked(True)
        policy_tab.list_product_line.item(0).setSelected(True)
    coverages_tab = CoveragesTab()
    if cov_gio:
        coverages_tab.chk_cov_gio.setChecked(True)
    return build_cyberlife_sql(
        "DB2TAB",
        "",
        "25",
        policy_tab=policy_tab,
        display_tab=DisplayTab(),
        policy2_tab=Policy2Tab(),
        adv_tab=AdvTab(),
        coverages_tab=coverages_tab,
        plancode_tab=plancode_tab,
        benefits_tab=BenefitsTab(),
        transaction_tab=TransactionTab(),
        coverage_level=coverage_level,
    )


def test_no_covsall_join_when_nothing_references_it():
    _app()
    sql = _build()
    assert "LH_COV_PHA COVSALL" not in sql


def test_covsall_joined_for_any_coverage_plancode():
    _app()
    sql = _build(plancodes=["8N562900"])
    assert "LH_COV_PHA COVSALL" in sql
    assert "COVSALL.PLN_DES_SER_CD IN ('8N562900')" in sql


def test_coverage_level_binds_plancode_to_resultcov_without_covsall():
    _app()
    sql = _build(coverage_level=True, plancodes=["8N562900"])
    assert "COVSALL" not in sql
    assert "RESULTCOV.PLN_DES_SER_CD IN ('8N562900')" in sql


def test_coverage_level_drops_covsall_for_product_line():
    _app()
    sql = _build(coverage_level=True, product_line=True)
    assert "COVSALL" not in sql
    assert "RESULTCOV.PRD_LIN_TYP_CD IN (" in sql


def test_covsall_kept_when_modcovsall_needs_it():
    _app()
    sql = _build(coverage_level=True, cov_gio=True)
    assert "LH_COV_PHA COVSALL" in sql
    assert "MODCOVSALL.CK_SYS_CD = COVSALL.CK_SYS_CD" in sql
