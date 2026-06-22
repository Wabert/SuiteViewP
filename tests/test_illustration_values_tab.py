import os
from dataclasses import replace
from datetime import date

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtWidgets import QApplication, QTabWidget
from PyQt6.QtGui import QFontMetrics

from suiteview.illustration.models.calc_state import MonthlyState
from suiteview.illustration.models.policy_data import CoverageSegment, IllustrationPolicyData
from suiteview.illustration.ui.values_tab import IllustrationValuesTab
from suiteview.illustration.ui.values_overview import (
    LEDGER_COLUMNS,
    ValuesOverview,
    build_charge_bands,
    build_chart_series,
)


_QT_APP = None


def _app():
    global _QT_APP
    _QT_APP = QApplication.instance() or QApplication([])
    return _QT_APP


def _policy() -> IllustrationPolicyData:
    return IllustrationPolicyData(
        face_amount=150000,
        segments=[
            CoverageSegment(face_amount=100000),
            CoverageSegment(face_amount=50000),
        ],
    )


def _state() -> MonthlyState:
    return MonthlyState(
        policy_year=1,
        policy_month=2,
        attained_age=45,
        days_in_month=365.0 / 12.0,
        shadow_days=365.0 / 12.0,
        av_after_premium=10000,
        nar_av=10000,
        standard_db=150000,
        corridor_rate=2.5,
        gross_db=150000,
        corr_amount=2500,
        db_by_coverage={"cov1": 100000, "cov2": 50000},
        discounted_db_by_coverage={"cov1": 99500, "cov2": 49750},
        discounted_db_corr=2488,
        total_discounted_db=151738,
        nar_by_coverage={"cov1": 89500, "cov2": 49750},
        nar_corr=2488,
        total_nar=141738,
        coi_rates_by_coverage={"cov1": 0.1, "cov2": 0.2},
        coi_rate=0.3,
        coi_charges_by_coverage={"cov1": 8.95, "cov2": 9.95},
        coi_charge_corr=0.75,
        total_coi_charge=19.65,
        epu_rate=0.05,
        epu_rates_by_coverage={"cov1": 0.05, "cov2": 0.06},
        epu_charges_by_coverage={"cov1": 5.0, "cov2": 3.0},
        epu_charge=8.0,
        mfee_charge=5.0,
        av_charge=2.0,
        pw_charge=1.0,
        benefit_amounts={"3": 125.0},
        benefit_rates={"3": 0.01},
        benefit_charge_detail={"3": 1.25},
        benefit_charges=1.25,
        rider_amounts={"R1_1": 10000},
        rider_rates={"R1_1": 0.12},
        rider_charge_detail={"R1_1": 1.2},
        rider_charges=1.2,
        total_deduction=38.1,
        av_after_deduction=9961.9,
        reg_loan_credit_rate=0.02,
        pref_loan_credit_rate=0.04,
        unimpaired_int=17.5,
        av_end_of_month=9990,
    )


def test_values_tab_uses_one_content_page_per_group_each_leading_with_locators():
    _app()
    tab = IllustrationValuesTab()

    tab.display_projection(_policy(), [_state()])

    assert tab._content_titles == [
        "Overview",
        "Chart",
        "Charges",
        "Summary",
        "Withdrawals",
        "DB Option Change",
        "Increase/Decrease",
        "Cov After Change",
        "MTP",
        "CTP",
        "TEFRA and TAMRA",
        "Requested Premium",
        "Loan Capitalize and Repay",
        "Apply Premium",
        "Monthly Deduction",
        "Exception Premiums",
        "Policy Values",
        "Accumulation",
        "Ending Values",
        "Shadow Account",
        "Testing",
        "TEFRA/TAMRA Recalc",
    ]
    # No recalc in this projection → no per-date detail pages (and no QTabWidget).
    assert tab.recalc_view.detail_views == []
    assert tab.findChildren(QTabWidget) == []

    for title, grid in tab._tab_grids.items():
        columns = list(grid.df.columns)
        assert columns[:4] == ["Date", "Year", "Month", "Attained Age"], title


def test_values_group_grids_freeze_lead_locator_columns():
    _app()
    tab = IllustrationValuesTab()

    tab.display_projection(_policy(), [_state()])

    for title in ("Summary", "Monthly Deduction", "Ending Values"):
        grid = tab._tab_grids[title]
        assert grid._frozen_column_count == 4
        assert not grid.frozen_table_view.isHidden(), title
        for column_index in range(4):
            assert grid.table_view.isColumnHidden(column_index), title
            assert not grid.frozen_table_view.isColumnHidden(column_index), title
            assert grid.frozen_table_view.columnWidth(column_index) < 100, title
        assert not grid.table_view.isColumnHidden(4), title
        assert grid.frozen_table_view.isColumnHidden(4), title


def test_values_group_copy_includes_frozen_locator_columns():
    _app()
    tab = IllustrationValuesTab()

    tab.display_projection(_policy(), [_state()])

    grid = tab._tab_grids["Monthly Deduction"]
    copied_header = grid._dataframe_to_clipboard_text(grid.df).splitlines()[0].split("\t")
    assert copied_header[:4] == ["Date", "Year", "Month", "Attained Age"]


def test_accumulation_values_group_shows_loan_credit_rates_before_impaired_interest():
    _app()
    tab = IllustrationValuesTab()

    tab.display_projection(_policy(), [_state()])

    grid = tab._tab_grids["Accumulation"]
    columns = list(grid.df.columns)
    assert columns[columns.index("Reg Impaired Int") - 1] == "RegLn Credit Rt"
    assert columns[columns.index("Pref Impaired Int") - 1] == "PrefLn Credit Rt"
    assert grid.df.iloc[0]["RegLn Credit Rt"] == 2.0
    assert grid.df.iloc[0]["PrefLn Credit Rt"] == 4.0


def test_accumulation_values_group_shows_unimpaired_interest():
    _app()
    tab = IllustrationValuesTab()

    tab.display_projection(_policy(), [_state()])

    assert tab._tab_grids["Accumulation"].df.iloc[0]["Unimpaired Int"] == 17.5


def test_loan_capitalize_and_accumulation_show_inforce_loan_buckets():
    _app()
    tab = IllustrationValuesTab()
    state = replace(
        _state(),
        # MS..MX — post-repay beginning buckets.
        rg_loan_princ=4784.51,
        rg_loan_accrued=32.48,
        pf_loan_princ=123.45,
        pf_loan_accrued=6.78,
        vbl_loan_princ=98.76,
        vbl_loan_accrued=5.43,
        # LX..MC — pre-repay capitalized buckets carried on loan_cap_repay.
        loan_cap_repay={
            "Advance - Rg Ln Princ/Total": 4784.51,
            "Advance - Rg Ln Int Accrued": 32.48,
            "Advance - Pf Ln Princ/Total": 123.45,
            "Advance - Pf Ln Int Accrued": 6.78,
            "Advance - Var Ln Princ/Total": 98.76,
            "Advance - Var Ln Int Accrued": 5.43,
        },
        end_rg_loan_princ=4784.51,
        end_rg_loan_accrued=64.38,
        end_pf_loan_princ=123.45,
        end_pf_loan_accrued=9.87,
        end_vbl_loan_princ=98.76,
        end_vbl_loan_accrued=7.65,
    )

    tab.display_projection(_policy(), [state])

    loan_cap = tab._tab_grids["Loan Capitalize and Repay"].df.iloc[0]
    assert loan_cap["Advance - Rg Ln Princ/Total"] == 4784.51
    assert loan_cap["Advance - Rg Ln Int Accrued"] == 32.48
    assert loan_cap["Advance - Pf Ln Princ/Total"] == 123.45
    assert loan_cap["Advance - Pf Ln Int Accrued"] == 6.78
    assert loan_cap["Advance - Var Ln Princ/Total"] == 98.76
    assert loan_cap["Advance - Var Ln Int Accrued"] == 5.43
    # Post-repay buckets (MS..MX) come from the loan fields directly.
    assert loan_cap["Rg Ln Princ"] == 4784.51
    assert loan_cap["Pf Ln Princ"] == 123.45

    accumulation = tab._tab_grids["Accumulation"].df.iloc[0]
    assert accumulation["Reg Ln Princ"] == 4784.51
    assert accumulation["Accrued Reg Ln Int"] == 64.38
    assert accumulation["Pref Ln Princ"] == 123.45
    assert accumulation["Accrued Pref Ln Int"] == 9.87
    assert accumulation["Vbl Ln Princ"] == 98.76
    assert accumulation["Accured Vbl Ln Int"] == 7.65


def test_values_groups_show_average_days_when_exact_days_is_off():
    _app()
    tab = IllustrationValuesTab()

    tab.display_projection(_policy(), [_state()])

    assert tab._tab_grids["Accumulation"].df.iloc[0]["# of Days"] == 365.0 / 12.0
    assert tab._tab_grids["Shadow Account"].df.iloc[0]["Shadow # of Days"] == 365.0 / 12.0


def test_summary_values_group_allows_wider_autofit_for_long_values():
    _app()
    tab = IllustrationValuesTab()
    state = replace(_state(), db_option="X" * 80)

    tab.display_projection(_policy(), [state])

    grid = tab._tab_grids["Summary"]
    dbo_column = list(grid.df.columns).index("DBO")
    assert grid.table_view.columnWidth(dbo_column) > 260


def test_summary_values_group_autofit_leaves_room_for_gsp_decimals():
    _app()
    tab = IllustrationValuesTab()
    state = replace(_state(), gsp=123456789.12)

    tab.display_projection(_policy(), [state])

    grid = tab._tab_grids["Summary"]
    gsp_column = list(grid.df.columns).index("GSP")
    metrics = QFontMetrics(grid.table_view.font())
    assert grid.table_view.columnWidth(gsp_column) >= metrics.horizontalAdvance("123,456,789.12") + 36


def test_values_group_navigator_is_permanent():
    _app()
    tab = IllustrationValuesTab()

    assert not hasattr(tab, "nav_toggle")
    assert tab.nav_header.text() == "Values Group"
    assert not tab.navigator.isHidden()


def _recalc_pv_detail(label, premium):
    return {
        "premium_label": label,
        "attained_age": 45,
        "specified_amount": 100000.0,
        "db_option": "A",
        "glp_rate": 0.04 if label == "GLP" else 0.06,
        "glp_rows": [
            {"Policy Month": 1, "Age": 45, "q'x": 0.001, "p'x": 0.999,
             "tp'x": 1.0, "v^t": 1.0, "v^(t+1)": 0.9967,
             "Death Benefit": 100000.0, "Charges": 12.0,
             "PVDB": 99.67, "PV Charges": 11.96, "PV Annuity": 1.0},
        ],
        "glp_rollup": {
            "PV death benefit": 99.67,
            "PV maturity endowment": 1000.0,
            "PVDB (= SA endowment)": 1099.67,
            "PV Charges": 11.96,
            "load $ term": 0.0,
            "PV Annuity (gross)": 1.0,
            "load %": 0.0,
            "PV Annuity (net of load)": 1.0,
            "numerator": premium,
            "denominator": 1.0,
            "premium": premium,
        },
    }


def _recalc_state():
    """A projection-month state carrying a full guideline re-solve."""
    state = _state()
    state.tamra_7pay_start_date = date(2026, 5, 15)
    state.tamra_7pay_level = 95.0
    state.guideline_recalc = {
        "change_kind": "Specified Amount Change",
        "change_date": date(2026, 5, 15),
        "glp_before": 100.0,
        "glp_after": 125.0,
        "gsp_before": 1000.0,
        "gsp_after": 950.0,
        "glp_prior": 90.0,
        "glp_new": 115.0,
        "gsp_prior": 1100.0,
        "gsp_new": 1050.0,
        "monthly_pv_recalc": {
            "before": {"glp": _recalc_pv_detail("GLP", 100.0),
                       "gsp": _recalc_pv_detail("GSP", 1000.0)},
            "after": {"glp": _recalc_pv_detail("GLP", 125.0),
                      "gsp": _recalc_pv_detail("GSP", 950.0)},
        },
        "monthly_pv": _recalc_pv_detail("GLP", 125.0),
    }
    return state


def test_tefra_tamra_recalc_summary_table_leads_with_valuation_baseline():
    import pandas as pd

    _app()
    tab = IllustrationValuesTab()

    seed = _state()
    seed.date = date(2026, 6, 1)
    seed.glp = 90.0
    seed.gsp = 1100.0
    seed.tamra_7pay_start_date = date(2026, 1, 1)
    seed.tamra_7pay_level = 80.0

    tab.display_projection(_policy(), [seed, _recalc_state()])

    summary = tab.recalc_view.summary_grid.df
    assert list(summary.columns) == [
        "Effective Date",
        "GLPb", "GLPa", "GLP Delta", "GLP", "blank1",
        "GSPb", "GSPa", "GSP Delta", "GSP", "blank2",
        "7-Pay Start Date", "7-Pay Premium",
    ]
    # Two columns each share a display label (Delta / blank) yet keep unique keys.
    assert tab.recalc_view.summary_grid.model._header_labels == {
        "GLP Delta": "Delta", "GSP Delta": "Delta", "blank1": "", "blank2": "",
    }

    # Row 0 is the valuation baseline: only GLP/GSP/7-pay are populated.
    base = summary.iloc[0]
    assert base["Effective Date"] == "06/01/2026"
    assert base["GLP"] == 90.0 and base["GSP"] == 1100.0
    assert base["7-Pay Start Date"] == "01/01/2026" and base["7-Pay Premium"] == 80.0
    for blank in ("GLPb", "GLPa", "GLP Delta", "GSPb", "GSPa", "GSP Delta"):
        assert pd.isna(base[blank]), blank

    # Row 1 is the recalc: before/after/Δ/new for both premiums plus the 7-pay.
    row = summary.iloc[1]
    assert row["Effective Date"] == "05/15/2026"
    assert (row["GLPb"], row["GLPa"], row["GLP Delta"], row["GLP"]) == (100.0, 125.0, 25.0, 115.0)
    assert (row["GSPb"], row["GSPa"], row["GSP Delta"], row["GSP"]) == (1000.0, 950.0, -50.0, 1050.0)
    assert row["7-Pay Start Date"] == "05/15/2026" and row["7-Pay Premium"] == 95.0

    # The navigator gets a TEFRA/TAMRA Recalc parent with a child per recalc date.
    assert tab.recalc_view.recalc_dates == [date(2026, 5, 15)]
    recalc_item = next(
        tab.nav_tree.topLevelItem(i)
        for i in range(tab.nav_tree.topLevelItemCount())
        if tab.nav_tree.topLevelItem(i).text(0) == "TEFRA/TAMRA Recalc"
    )
    assert [recalc_item.child(i).text(0) for i in range(recalc_item.childCount())] == [
        "Recalc 05/15/2026",
    ]


def test_tefra_tamra_recalc_detail_page_renders_summary_and_pv_tabs():
    _app()
    tab = IllustrationValuesTab()

    tab.display_projection(_policy(), [_state(), _recalc_state()])

    assert len(tab.recalc_view.detail_views) == 1
    detail_view = tab.recalc_view.detail_views[0]

    summary = detail_view.summary_grid.df
    assert list(summary.columns) == [
        "Premium", "Prior Prem", "Before Change", "After Change",
        "Δ (After − Before)", "New Prem",
    ]
    assert summary.iloc[0].to_dict() == {
        "Premium": "GLP", "Prior Prem": 90.0, "Before Change": 100.0,
        "After Change": 125.0, "Δ (After − Before)": 25.0, "New Prem": 115.0,
    }

    recalc_tabs = detail_view.tabs
    assert [recalc_tabs.tabText(index) for index in range(recalc_tabs.count())] == [
        "Summary", "GLP Before", "GLP After", "GSP Before", "GSP After",
    ]
    assert detail_view.pv_views[("glp", "before")]._detail["premium_label"] == "GLP"
    assert detail_view.pv_views[("gsp", "after")]._detail["premium_label"] == "GSP"
    assert "GSP =" in detail_view.pv_views[("gsp", "after")].header.text()
    assert not detail_view.pv_views[("gsp", "after")].grid.search_bar.isVisible()


def test_cov_slot_groups_show_only_active_coverages():
    _app()
    tab = IllustrationValuesTab()

    single = _state()
    single.coverage_after_change = {
        "Cov 1 Active": True, "Cov 2 Active": False, "Cov 3 Active": False,
        "APB Active": False, "Current SA Cov 1": 100000.0,
        "Current SA Cov 2": 0.0, "Current SA Cov 3": 0.0,
        "CurrentSA": 100000.0,
    }
    single.mtp_detail = {"MTP Cov 1": 100.0, "MTP Cov 2": 0.0, "vMTP": 1200.0}
    single.ctp_detail = {"CTP Cov 1": 120.0, "CTP Cov 2": 0.0, "vCTP": 1440.0}
    tab.display_projection(_policy(), [single])

    cov_columns = list(tab._tab_grids["Cov After Change"].df.columns)
    assert "Current SA Cov 1" in cov_columns
    assert "Current SA Cov 2" not in cov_columns
    assert "Original SA APB" not in cov_columns
    mtp_columns = list(tab._tab_grids["MTP"].df.columns)
    assert "MTP Cov 1" in mtp_columns
    assert "MTP Cov 2" not in mtp_columns
    assert "WD SA Change Cov 2" not in list(tab._tab_grids["Withdrawals"].df.columns)

    # A coverage activated mid-run (face increase) brings its slot in.
    second = _state()
    second.coverage_after_change = dict(
        single.coverage_after_change,
        **{"Cov 2 Active": True, "Current SA Cov 2": 50000.0},
    )
    second.mtp_detail = dict(single.mtp_detail, **{"MTP Cov 2": 50.0})
    second.ctp_detail = dict(single.ctp_detail)
    tab.display_projection(_policy(), [single, second])

    assert "Current SA Cov 2" in list(tab._tab_grids["Cov After Change"].df.columns)
    assert "MTP Cov 2" in list(tab._tab_grids["MTP"].df.columns)
    assert "Cov 3 Active" not in list(tab._tab_grids["Cov After Change"].df.columns)


def test_summary_tab_columns_and_relabels():
    _app()
    tab = IllustrationValuesTab()
    state = _state()
    state.av_after_exception = 9_975.25
    state.av_end_of_month = 9_990.00

    tab.display_projection(_policy(), [state])

    summary = tab._tab_grids["Summary"]
    columns = list(summary.df.columns)
    assert columns == ["Date", "Year", "Month", "Attained Age"] + tab.SUMMARY_COLUMNS

    from PyQt6.QtCore import Qt as QtCore

    model = summary.model

    def header(name: str) -> str:
        index = model._original_df.columns.get_loc(name)
        return model.headerData(index, QtCore.Orientation.Horizontal, QtCore.ItemDataRole.DisplayRole)

    assert header("Attained Age") == "Age"
    assert "Loan Int" in columns
    assert "New Loan" in columns
    assert summary.df.iloc[0]["AV"] == 9_975.25
    assert summary.df.iloc[0]["EAV"] == 9_990.00


def test_premium_outlay_includes_exception_premium_in_ending_values():
    _app()
    tab = IllustrationValuesTab()
    state = _state()
    state.gross_premium = 100.0
    state.gp_exception_prem = 25.0

    tab.display_projection(_policy(), [state])

    ending = tab._tab_grids["Ending Values"].df
    assert ending.iloc[0]["PremiumOutlay"] == 125.0


def test_chart_cumulative_premium_uses_premium_outlay():
    first = MonthlyState(policy_year=1, policy_month=1, gross_premium=100.0,
                         gp_exception_prem=25.0, premiums_to_date=10_000.0)
    second = MonthlyState(policy_year=1, policy_month=2, gross_premium=10.0,
                          gp_exception_prem=5.0, premiums_to_date=20_000.0)

    series = build_chart_series([first, second])
    cum_premium = next(entry for entry in series if entry.name == "Cum Premium")

    assert cum_premium.points == [(1.0, 10_025.0), (1 + 1 / 12, 20_030.0)]


def test_charge_chart_separates_base_coi_from_riders_and_benefits():
    state = MonthlyState(
        policy_year=1,
        policy_month=1,
        coi_charge=999.0,
        total_coi_charge=20.0,
        epu_charge=5.0,
        mfee_charge=3.0,
        pw_charge=4.0,
        benefit_charges=10.0,
        benefit_charge_detail={"39": 4.0, "76": 6.0},
        rider_charges=7.0,
        rider_charge_detail={"1U536C00_1": 7.0},
        total_deduction=45.0,
    )

    bands = build_charge_bands([state])
    by_name = {band.name: band.points[-1][1] for band in bands}

    assert by_name["Base COI"] == 20.0
    assert by_name["Expense / Unit"] == 5.0
    assert by_name["Monthly Fee"] == 3.0
    assert by_name["Premium Waiver"] == 4.0
    assert by_name["GIO"] == 6.0
    assert by_name["LTR"] == 7.0
    assert 999.0 not in by_name.values()


def test_charge_chart_uses_legacy_coi_when_no_base_breakout_exists():
    state = MonthlyState(policy_year=1, policy_month=1, coi_charge=12.5)

    bands = build_charge_bands([state])

    assert [(band.name, band.points[-1][1]) for band in bands] == [("Base COI", 12.5)]


def test_overview_premium_column_uses_premium_outlay():
    _app()
    overview = ValuesOverview()
    inforce = MonthlyState(policy_year=0, policy_month=0, attained_age=44,
                           premiums_to_date=10_000.0)
    first = replace(_state(), policy_year=1, policy_month=1, gross_premium=100.0,
                    gp_exception_prem=25.0, premiums_to_date=20_000.0)
    second = replace(_state(), policy_year=1, policy_month=2, gross_premium=10.0,
                     gp_exception_prem=5.0, premiums_to_date=30_000.0)

    overview.display(_policy(), [inforce, first, second])

    prem_col = LEDGER_COLUMNS.index("Prem")
    year_item = overview.ledger.topLevelItem(0)
    assert year_item.text(prem_col) == "140.00"
    assert year_item.child(0).text(prem_col) == "125.00"
    assert year_item.child(1).text(prem_col) == "15.00"


def test_summary_tab_uses_requested_illustration_values_order():
    _app()
    tab = IllustrationValuesTab()
    first = MonthlyState(
        date=date(2026, 1, 15),
        policy_year=1,
        policy_month=1,
        attained_age=45,
        gross_withdrawal=20.0,
        wd_partial_sc=1.0,
        dbo_change_detail={"Total PSC DBO": 2.0},
        face_change_detail={"Total PSC Spec Dec": 3.0},
        coverage_after_change={"CurrentSA": 150000.0},
        db_option="B",
        monthly_mtp=100.0,
        accumulated_mtp=500.0,
        glp=1000.0,
        gsp=2000.0,
        accumulated_glp=3000.0,
        rg_loan_princ=10.0,
        rg_loan_accrued=1.0,
        pf_loan_princ=20.0,
        pf_loan_accrued=2.0,
        vbl_loan_princ=30.0,
        vbl_loan_accrued=3.0,
        applied_loan_repayment=12.0,
        gross_premium=100.0,
        gp_exception_prem=25.0,
        premiums_to_date=20000.0,
        total_premium_load=7.5,
        av_after_premium=900.0,
        total_nar=50000.0,
        total_coi_charge=20.0,
        rider_charges=2.0,
        benefit_charges=4.0,
        epu_charge=6.0,
        mfee_charge=8.0,
        total_deduction=11.0,
        av_after_exception=950.0,
        applied_regular_loan=1.0,
        applied_preferred_loan=2.0,
        applied_variable_loan=3.0,
        annual_interest_rate=0.04,
        bonus_interest_rate=0.009,
        effective_annual_rate=0.049,
        interest_credited=4.0,
        av_end_of_month=1000.0,
        surrender_charge=90.0,
        end_rg_loan_princ=11.0,
        end_rg_loan_accrued=1.0,
        end_pf_loan_princ=22.0,
        end_pf_loan_accrued=2.0,
        end_vbl_loan_princ=33.0,
        end_vbl_loan_accrued=3.0,
        reg_loan_charge=1.0,
        pref_loan_charge=2.0,
        vbl_loan_charge=3.0,
        policy_debt=72.0,
        surrender_value=900.0,
        ending_db=150000.0,
    )
    second = MonthlyState(
        date=date(2026, 2, 15),
        policy_year=1,
        policy_month=2,
        attained_age=45,
        gross_withdrawal=30.0,
        wd_partial_sc=4.0,
        coverage_after_change={"CurrentSA": 151000.0},
        db_option="B",
        monthly_mtp=101.0,
        accumulated_mtp=601.0,
        glp=1100.0,
        gsp=2100.0,
        accumulated_glp=3100.0,
        rg_loan_princ=40.0,
        rg_loan_accrued=4.0,
        pf_loan_princ=50.0,
        pf_loan_accrued=5.0,
        vbl_loan_princ=60.0,
        vbl_loan_accrued=6.0,
        applied_loan_repayment=8.0,
        gross_premium=10.0,
        gp_exception_prem=5.0,
        premiums_to_date=30000.0,
        total_premium_load=1.5,
        av_after_premium=1000.0,
        total_nar=60000.0,
        total_coi_charge=30.0,
        rider_charges=3.0,
        benefit_charges=5.0,
        epu_charge=7.0,
        mfee_charge=9.0,
        total_deduction=12.0,
        av_after_exception=1050.0,
        applied_regular_loan=4.0,
        applied_preferred_loan=5.0,
        applied_variable_loan=6.0,
        annual_interest_rate=0.045,
        bonus_interest_rate=0.005,
        effective_annual_rate=0.05,
        interest_credited=6.0,
        av_end_of_month=1200.0,
        surrender_charge=80.0,
        end_rg_loan_princ=44.0,
        end_rg_loan_accrued=5.0,
        end_pf_loan_princ=55.0,
        end_pf_loan_accrued=6.0,
        end_vbl_loan_princ=63.0,
        end_vbl_loan_accrued=7.0,
        reg_loan_charge=4.0,
        pref_loan_charge=5.0,
        vbl_loan_charge=6.0,
        policy_debt=180.0,
        surrender_value=1100.0,
        ending_db=151000.0,
    )

    tab.display_projection(_policy(), [first, second])

    summary = tab._tab_grids["Summary"]
    assert list(summary.df.columns) == ["Date", "Year", "Month", "Attained Age"] + [
        "GrossWD", "DBO", "TotalSA", "PSC",
        "MonthlyMTP", "Accum MTP", "GLP", "GSP", "AccumGLP", "ForceOut", "Loan Int",
        "Loan Balance", "Loan Repay", "Premium", "PremTD", "Prem Load", "mAV",
        "NAAR", "Base COI", "Rider COI", "Benefit COI", "EPU", "MFEE", "MD",
        "Exception Prem", "AV", "New Loan", "Interest Rate", "Interest", "EAV",
        "SC", "ESV", "Var Loan", "Pref Loan", "Reg Loan", "Ending LB", "IllustratedDB",
    ]

    assert summary.df.iloc[0].to_dict() == {
        "Date": date(2026, 1, 15), "Year": 1, "Month": 1, "Attained Age": 45,
        "GrossWD": 20.0, "DBO": "B", "TotalSA": 150000.0, "PSC": 6.0,
        "MonthlyMTP": 100.0, "Accum MTP": 500.0, "GLP": 1000.0, "GSP": 2000.0,
        "AccumGLP": 3000.0, "ForceOut": 0.0, "Loan Int": 6.0, "Loan Balance": 66.0,
        "Loan Repay": 12.0, "Premium": 100.0, "PremTD": 20000.0,
        "Prem Load": 7.5, "mAV": 900.0, "NAAR": 50000.0, "Base COI": 20.0,
        "Rider COI": 2.0, "Benefit COI": 4.0, "EPU": 6.0, "MFEE": 8.0,
        "MD": 11.0, "Exception Prem": 25.0, "AV": 950.0, "New Loan": 6.0,
        "Interest Rate": 4.9, "Interest": 4.0, "EAV": 1000.0, "SC": 90.0,
        "ESV": 900.0, "Var Loan": 36.0, "Pref Loan": 24.0, "Reg Loan": 12.0,
        "Ending LB": 72.0, "IllustratedDB": 150000.0,
    }
    assert summary.df.iloc[1]["AV"] == 1050.0
    assert summary.df.iloc[1]["Interest Rate"] == 5.0
    assert summary.df.iloc[1]["EAV"] == 1200.0


def test_overview_ledger_restores_compact_values_order():
    _app()
    overview = ValuesOverview()
    inforce = MonthlyState(policy_year=0, policy_month=0, attained_age=44)
    first = MonthlyState(
        policy_year=1,
        policy_month=1,
        attained_age=45,
        gross_premium=100.0,
        gp_exception_prem=25.0,
        total_premium_load=7.5,
        withdrawals_to_date=20.0,
        guideline_forceout=3.0,
        applied_regular_loan=6.0,
        applied_loan_repayment=30.0,
        total_deduction=11.0,
        av_after_exception=950.0,
        interest_credited=4.0,
        av_end_of_month=1000.0,
        surrender_charge=90.0,
        policy_debt=10.0,
        surrender_value=900.0,
        ending_db=150000.0,
    )
    second = MonthlyState(
        policy_year=1,
        policy_month=2,
        attained_age=45,
        gross_premium=10.0,
        gp_exception_prem=5.0,
        total_premium_load=1.5,
        withdrawals_to_date=50.0,
        guideline_forceout=2.0,
        applied_regular_loan=4.0,
        applied_loan_repayment=15.0,
        total_deduction=12.0,
        av_after_exception=1150.0,
        interest_credited=6.0,
        av_end_of_month=1200.0,
        surrender_charge=80.0,
        policy_debt=20.0,
        surrender_value=1100.0,
        ending_db=151000.0,
        lapsed=True,
    )

    overview.display(_policy(), [inforce, first, second])

    headers = [overview.ledger.headerItem().text(index) for index in range(overview.ledger.columnCount())]
    assert headers == [
        "Year", "Month", "Age", "Withdrawals", "ForceOuts", "Loan Repay", "Prem",
        "MD", "Exception Prem", "AV", "SV", "Interest", "EAV", "SC",
        "New Loan", "LN", "ESV", "Death Benefit", "Status",
    ]
    year_item = overview.ledger.topLevelItem(0)
    assert [year_item.text(index) for index in range(overview.ledger.columnCount())] == [
        "1", "2", "45", "50.00", "5.00", "45.00", "140.00",
        "23.00", "30.00", "1,150.00", "1,050.00", "10.00", "1,200.00", "80.00",
        "10.00", "20.00", "1,100.00",
        "151,000", "LAPSED",
    ]


def test_ending_values_floor_illustration_sv_but_not_esv():
    row = IllustrationValuesTab._ending_values(MonthlyState(
        av_end_of_month=50.0,
        policy_debt=0.0,
        surrender_value=-125.0,
        ending_db=100_000.0,
    ))

    assert row["ES"] == -125.0
    assert row["IllustrationSV"] == 0.0


def test_testing_tab_columns_and_relabels():
    _app()
    tab = IllustrationValuesTab()

    tab.display_projection(_policy(), [_state()])

    testing = tab._tab_grids["Testing"]
    columns = list(testing.df.columns)
    assert columns == ["Date", "Year", "Month", "Attained Age"] + tab.TESTING_COLUMNS
    assert "Inforce?" in columns
    assert "7-Pay Yr 1" in columns

    from PyQt6.QtCore import Qt as QtCore

    model = testing.model

    def header(name: str) -> str:
        index = model._original_df.columns.get_loc(name)
        return model.headerData(index, QtCore.Orientation.Horizontal, QtCore.ItemDataRole.DisplayRole)

    assert header("SNET Active") == "SNET"
    assert header("Exception Protection") == "Exc Prem Protect"


def test_monthly_deduction_tab_follows_rerun_order():
    _app()
    tab = IllustrationValuesTab()

    tab.display_projection(_policy(), [_state()])

    columns = list(tab._tab_grids["Monthly Deduction"].df.columns)
    expected_block = [
        "mAV",
        "NAAR AV",
        "Face Amount",
        "Standard DB",
        "Corridor Rate",
        "Death Benefit",
        "Corridor Amount",
        "DB Cov1",
        "DB Cov2",
        "DB Corr",
        "Disc DB Cov1",
        "Disc DB Cov2",
        "Disc DB Corr",
        "Total Discounted DB",
        "NAR Cov1",
        "NAR Cov2",
        "NAR Corr",
        "NAR",
        "COI Rate Cov1",
        "COI Rate Cov2",
        "COI Rate Corr",
        "COI Charge Cov1",
        "COI Charge Cov2",
        "COI Charge Corr",
        "Total Base COI Charge",
        "COI Charge",
        "EPU Rate Cov1",
        "EPU Charge Cov1",
        "EPU Rate Cov2",
        "EPU Charge Cov2",
        "EPU Rate",
        "EPU Fee",
        "Monthly Fee",
        "AV Charge",
        "PW Charge",
        "Benefit Amount 3",
        "Benefit Rate 3",
        "Benefit Charge 3",
        "Benefit Charges",
        "Rider Amount R1_1",
        "Rider Rate R1_1",
        "Rider Charge R1_1",
        "Rider Charge",
        "Monthly Deduction",
        "AV after MD",
    ]
    start = columns.index("mAV")
    assert columns[start : start + len(expected_block)] == expected_block


def _ratchet_state() -> MonthlyState:
    # cov1 NAR (89,500) straddles the 50k break; cov2 NAR (49,750) all band 2.
    return replace(
        _state(),
        ratchet_active=True,
        band_break=50000.0,
        coi_band1_nar_by_coverage={"cov1": 50000.0, "cov2": 0.0, "corr": 0.0},
        coi_band1_rates_by_coverage={"cov1": 0.5, "cov2": 0.5, "corr": 0.4},
        coi_band2_nar_by_coverage={"cov1": 39500.0, "cov2": 49750.0, "corr": 0.0},
        coi_band2_rates_by_coverage={"cov1": 0.2, "cov2": 0.2, "corr": 0.15},
    )


def test_monthly_deduction_swaps_coi_rate_for_band_detail_when_ratchet():
    _app()
    tab = IllustrationValuesTab()

    tab.display_projection(_policy(), [_ratchet_state()])

    grid = tab._tab_grids["Monthly Deduction"]
    columns = list(grid.df.columns)
    # The single COI-rate column per coverage is swapped for the band split.
    swapped_block = [
        "NAR",
        "Band Break",
        "NAR B1 Cov1",
        "COI Rate B1 Cov1",
        "NAR B2 Cov1",
        "COI Rate B2 Cov1",
        "NAR B1 Cov2",
        "COI Rate B1 Cov2",
        "NAR B2 Cov2",
        "COI Rate B2 Cov2",
        "COI Rate Corr",
        "COI Charge Cov1",
    ]
    start = columns.index("NAR", columns.index("NAR Corr"))
    assert columns[start : start + len(swapped_block)] == swapped_block
    assert "COI Rate Cov1" not in columns  # swapped out of the MD group

    row = grid.df.iloc[0]
    assert row["Band Break"] == 50000.0
    assert row["NAR B1 Cov1"] == 50000.0
    assert row["COI Rate B1 Cov1"] == 0.5
    assert row["NAR B2 Cov1"] == 39500.0
    assert row["COI Rate B2 Cov2"] == 0.2
    # The combined per-coverage charge column is retained.
    assert row["COI Charge Cov1"] == 8.95


def test_monthly_deduction_keeps_single_coi_rate_when_not_ratchet():
    _app()
    tab = IllustrationValuesTab()

    tab.display_projection(_policy(), [_state()])

    columns = list(tab._tab_grids["Monthly Deduction"].df.columns)
    assert "COI Rate Cov1" in columns
    assert "Band Break" not in columns
    assert "NAR B1 Cov1" not in columns


def test_values_groups_cleanup_populate_and_drop_columns():
    _app()
    tab = IllustrationValuesTab()
    state = replace(
        _state(),
        coverage_after_change={
            "Cov 1 Active": True,
            "Cov 1 Issue Date": date(1985, 7, 23),
            "Cov 1 Months from Issue": 491,
            "CurrentSA": 25000.0,
        },
        tamra_7pay_start_date=date(2026, 1, 15),
        tamra_month_of_year=5,
        tamra_year=1,
        lowest_7yr_face=100000.0,
        unscheduled_premium=250.0,
        planned_premium_mode="Q",
        payment_count_policy_year=4,
        payment_count_tamra_year=3,
        requested_premium=49.23,
    )

    tab.display_projection(_policy(), [state])

    # Cov After Change: Cov 1 populates.
    cov = tab._tab_grids["Cov After Change"]
    assert "Cov 1 Active" in cov.df.columns
    assert bool(cov.df.iloc[0]["Cov 1 Active"]) is True
    assert cov.df.iloc[0]["Cov 1 Months from Issue"] == 491

    # TEFRA and TAMRA: new fields populate; retired columns are gone.
    tt = tab._tab_grids["TEFRA and TAMRA"]
    assert tt.df.iloc[0]["7PayStartDate"] == date(2026, 1, 15)
    assert tt.df.iloc[0]["TAMRA_MonthOfYear"] == 5
    assert tt.df.iloc[0]["Lowest7YearFace"] == 100000.0
    assert "New TAMRA Period" not in tt.df.columns
    assert "TAMRAMonth" not in tt.df.columns

    # Requested Premium: Lumpsum repurposed, mode + counts populate, columns dropped.
    rp = tab._tab_grids["Requested Premium"]
    assert rp.df.iloc[0]["Lumpsum"] == 250.0
    assert rp.df.iloc[0]["PlannedPremiumMode"] == "Q"
    assert rp.df.iloc[0]["Payment Count For Policy Year"] == 4
    assert rp.df.iloc[0]["Payment Count for TAMRA Year"] == 3
    for gone in ("Premium Frequency", "Premium Period", "Scheduled Premium Due", "Scheduled Premium"):
        assert gone not in rp.df.columns


def test_summary_tab_shows_forceout_after_accum_glp():
    _app()
    tab = IllustrationValuesTab()
    state = replace(_state(), accumulated_glp=9000.0, guideline_forceout=321.0)

    tab.display_projection(_policy(), [state])

    columns = list(tab._tab_grids["Summary"].df.columns)
    assert "ForceOut" in columns
    assert columns.index("ForceOut") == columns.index("AccumGLP") + 1
    assert tab._tab_grids["Summary"].df.iloc[0]["ForceOut"] == 321.0
