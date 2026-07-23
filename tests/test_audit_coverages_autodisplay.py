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


def _build(coverages_tab, display_tab=None):
    return build_cyberlife_sql(
        "DB2TAB",
        "",
        "25",
        policy_tab=PolicyTab(),
        display_tab=display_tab or DisplayTab(),
        policy2_tab=Policy2Tab(),
        adv_tab=AdvTab(),
        coverages_tab=coverages_tab,
        plancode_tab=PlancodeTab(),
        benefits_tab=BenefitsTab(),
        transaction_tab=TransactionTab(),
    )


def _select_head(sql: str) -> str:
    """Return only the SELECT column list (before FROM)."""
    return sql.split("\nFROM ", 1)[0]


def test_vpu_criteria_adds_display_column():
    _app()
    cov = CoveragesTab()
    cov.base_cov_widgets["vpu_lo"].setText("1000")
    cov.base_cov_widgets["vpu_hi"].setText("2000")

    head = _select_head(_build(cov))

    assert "COVERAGE1.COV_VPU_AMT VPU" in head


def test_specified_amount_criteria_adds_display_column():
    _app()
    cov = CoveragesTab()
    cov.base_cov_widgets["spec_amt_lo"].setText("50000")

    head = _select_head(_build(cov))

    assert (
        "ROUND(REAL(COVERAGE1.COV_UNT_QTY) * REAL(COVERAGE1.COV_VPU_AMT), 2) "
        "SpecifiedAmount" in head
    )


def test_valuation_single_value_fields_add_display_columns():
    _app()
    cov = CoveragesTab()
    cov.val_base.setText("A")
    cov.val_sub.setText("B")

    head = _select_head(_build(cov))

    assert "COVERAGE1.PLN_BSE_SRE_CD ValBase" in head
    assert "COVERAGE1.LIF_PLN_SUB_SRE_CD ValSub" in head


def test_init_term_list_adds_display_column():
    _app()
    cov = CoveragesTab()
    cov.chk_init_term.setChecked(True)
    cov.list_init_term.item(0).setSelected(True)

    head = _select_head(_build(cov))

    assert "COVERAGE1.INT_RNL_PER InitTermPeriod" in head


def test_table_checkbox_adds_display_column():
    _app()
    cov = CoveragesTab()
    cov.base_cov_widgets["table_03"].setChecked(True)

    head = _select_head(_build(cov))

    assert "TABLE_RATING1.SST_XTR_RT_TBL_CD TableRating" in head


def test_pure_condition_flags_do_not_add_display_columns():
    _app()
    cov = CoveragesTab()
    cov.chk_multiple_base.setChecked(True)

    head = _select_head(_build(cov))

    assert " VPU" not in head
    assert "ValClass" not in head
    assert "Base" not in head


def test_val_class_ne_plan_shows_both_classes():
    _app()
    cov = CoveragesTab()
    cov.chk_val_class_ne_plan.setChecked(True)

    head = _select_head(_build(cov))

    assert "COVERAGE1.INS_CLS_CD ValClass" in head
    assert "SUBSTR(COVERAGE1.PLN_DES_SER_CD, 3, 1) PlanDescClass" in head


def test_cov_gio_shows_gio_ind():
    _app()
    cov = CoveragesTab()
    cov.chk_cov_gio.setChecked(True)

    head = _select_head(_build(cov))

    assert "MODCOVSALL.OPT_EXER_IND GioInd" in head


def test_cov_cola_shows_cola_ind():
    _app()
    cov = CoveragesTab()
    cov.chk_cov_cola.setChecked(True)

    head = _select_head(_build(cov))

    assert "MODCOVSALL.COLA_INCR_IND ColaInd" in head


def test_cv_rate_gt_zero_shows_cv_rate():
    _app()
    cov = CoveragesTab()
    cov.chk_cv_rate_gt_zero.setChecked(True)

    head = _select_head(_build(cov))

    assert "COVERAGE1.LOW_DUR_1_CSV_AMT CVRate1" in head
    assert "COVERAGE1.LOW_DUR_2_CSV_AMT CVRate2" in head


def test_gcv_gt_cv_shows_gcv_and_current_cv():
    _app()
    cov = CoveragesTab()
    cov.chk_gcv_gt_cv.setChecked(True)

    head = _select_head(_build(cov))

    assert "ISWL_INTERPOLATED_GCV.ISWL_GCV GCV" in head
    assert "MVVAL.CSV_AMT CurrentCV" in head


def test_gcv_lt_cv_shows_gcv_and_current_cv():
    _app()
    cov = CoveragesTab()
    cov.chk_gcv_lt_cv.setChecked(True)

    head = _select_head(_build(cov))

    assert "ISWL_INTERPOLATED_GCV.ISWL_GCV GCV" in head
    assert "MVVAL.CSV_AMT CurrentCV" in head


def test_criteria_column_suppressed_when_display_checkbox_covers_it():
    _app()
    cov = CoveragesTab()
    cov.base_cov_widgets["prod_line"].setCurrentIndex(1)

    disp = DisplayTab()
    disp.chk_prod_line_code.setChecked(True)

    head = _select_head(_build(cov, disp))

    # Display tab already shows PRD_LIN_TYP_CD; don't duplicate it.
    assert "BaseProdLine" not in head
    assert "PRD_LIN_TYP_CD" in head


def test_no_criteria_means_no_extra_columns():
    _app()
    head = _select_head(_build(CoveragesTab()))
    assert " VPU" not in head
    assert "ValClass" not in head


def test_prod_ind_criteria_column_has_backing_join():
    _app()
    cov = CoveragesTab()
    cov.base_cov_widgets["prod_ind"].setCurrentIndex(1)

    sql = _build(cov)

    assert "MODCOV1.AN_PRD_ID ProdInd" in _select_head(sql)
    assert "JOIN DB2TAB.TH_COV_PHA MODCOV1" in sql


def test_rateclass_criteria_column_has_backing_join():
    _app()
    cov = CoveragesTab()
    cov.base_cov_widgets["rateclass"].setCurrentIndex(1)

    sql = _build(cov)

    assert "COV1_RENEWALS.RT_CLS_CD BaseRateClass" in _select_head(sql)
    assert "JOIN DB2TAB.LH_COV_INS_RNL_RT COV1_RENEWALS" in sql


def test_curr_spec_amt_criteria_column_has_covsummary_cte():
    _app()
    cov = CoveragesTab()
    cov.txt_spec_amt_lo.setText("10000")

    sql = _build(cov)

    assert "COVSUMMARY.TOTAL_SA CurrSpecAmt" in _select_head(sql)
    assert "COVSUMMARY AS" in sql or ", COVSUMMARY" in sql


def test_aliases_have_no_crit_prefix():
    _app()
    cov = CoveragesTab()
    cov.val_class.setText("1") if hasattr(cov.val_class, "setText") else None
    cov.base_cov_widgets["vpu_lo"].setText("100")
    cov.base_cov_widgets["spec_amt_lo"].setText("100")

    head = _select_head(_build(cov))

    assert "Crit" not in head
