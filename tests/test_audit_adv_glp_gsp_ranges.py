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


def test_prem_wd_gt_face_adds_where_joins_and_result_columns():
    _app()
    adv = AdvTab()
    adv.chk_prem_wd_gt_face.setChecked(True)

    sql = _build(adv)
    head = _select_head(sql)

    # WHERE: PremTD - AccumWD > active TotalFace
    assert ("((POLICY_TOTALS.TOT_REG_PRM_AMT + POLICY_TOTALS.TOT_ADD_PRM_AMT"
            " - POLICY_TOTALS.TOT_WTD_AMT) > PREMWD_FACE.TOTAL_FACE)") in sql
    # Dedicated active-coverage face CTE + JOINs
    assert "PREMWD_FACE AS (" in sql
    assert "INNER JOIN PREMWD_FACE" in sql
    assert "LH_POL_TOTALS POLICY_TOTALS" in sql
    assert "LH_NON_TRD_POL NONTRAD" in sql
    # Death Benefit needs MVVAL (Option B/C additional amount)
    assert "MVVAL AS (" in sql
    # Active-only filter: terminated coverages excluded (app convention)
    assert "TEMPCOVALL.NXT_CHG_TYP_CD <> '0'" in sql
    assert "TEMPCOVALL.NXT_CHG_DT > CURRENT DATE" in sql
    # 1U144A00 rider always included for this query
    assert "1U144A00" in sql
    # Result columns
    assert "  , (POLICY_TOTALS.TOT_REG_PRM_AMT + POLICY_TOTALS.TOT_ADD_PRM_AMT) PremTD" in head
    assert "  , POLICY_TOTALS.TOT_WTD_AMT AccumWD" in head
    assert "  , PREMWD_FACE.TOTAL_FACE TotalFace" in head
    assert "REAL(PREMWD_FACE.TOTAL_FACE) + COALESCE(REAL(MVVAL.OPTDB), 0)" in head
    assert "DeathBenefit" in head
    assert "  , NONTRAD.DTH_BNF_PLN_OPT_CD DBOpt" in head


def test_prem_wd_gt_face_dboption_not_duplicated_with_display():
    _app()
    from suiteview.audit.tabs.display_tab import DisplayTab

    adv = AdvTab()
    adv.chk_prem_wd_gt_face.setChecked(True)
    disp = DisplayTab()
    disp.chk_death_benefit_opt.setChecked(True)

    sql = _build(adv, disp)
    head = _select_head(sql)

    # DBOpt appears exactly once even when the Display DB Option is also on
    assert head.count("DTH_BNF_PLN_OPT_CD DBOpt") == 1


def test_prem_wd_gt_face_round_trips_in_state():
    _app()
    adv = AdvTab()
    adv.chk_prem_wd_gt_face.setChecked(True)

    restored = AdvTab()
    restored.set_state(adv.get_state())

    assert restored.chk_prem_wd_gt_face.isChecked() is True
