import os
from dataclasses import replace
from datetime import date

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtWidgets import QApplication, QTabWidget

from suiteview.illustration.models.calc_state import MonthlyState
from suiteview.illustration.models.policy_data import CoverageSegment, IllustrationPolicyData
from suiteview.illustration.ui.values_tab import IllustrationValuesTab
from suiteview.illustration.ui.values_overview import ValuesOverview, build_charge_bands, build_chart_series


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
        "Guideline Recalc",
    ]
    recalc_tabs = tab.recalc_view.tabs
    assert tab.findChildren(QTabWidget) == [recalc_tabs]
    assert [recalc_tabs.tabText(index) for index in range(recalc_tabs.count())] == [
        "Summary",
        "GLP Before",
        "GLP After",
        "GSP Before",
        "GSP After",
    ]

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


def test_values_group_navigator_is_permanent():
    _app()
    tab = IllustrationValuesTab()

    assert not hasattr(tab, "nav_toggle")
    assert tab.nav_header.text() == "Values Group"
    assert not tab.navigator.isHidden()


def test_guideline_recalc_group_renders_summary_and_pv_tabs():
    _app()
    tab = IllustrationValuesTab()

    def detail(label, premium):
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

    state = _state()
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
            "before": {"glp": detail("GLP", 100.0), "gsp": detail("GSP", 1000.0)},
            "after": {"glp": detail("GLP", 125.0), "gsp": detail("GSP", 950.0)},
        },
        "monthly_pv": detail("GLP", 125.0),
    }

    tab.display_projection(_policy(), [state])

    summary = tab.recalc_view.summary_grid.df
    assert list(summary.columns) == [
        "Premium", "Prior Prem", "Before Change", "After Change",
        "Δ (After − Before)", "New Prem",
    ]
    assert summary.iloc[0].to_dict() == {
        "Premium": "GLP", "Prior Prem": 90.0, "Before Change": 100.0,
        "After Change": 125.0, "Δ (After − Before)": 25.0, "New Prem": 115.0,
    }
    assert tab.recalc_view.pv_views[("glp", "before")]._detail["premium_label"] == "GLP"
    assert tab.recalc_view.pv_views[("gsp", "after")]._detail["premium_label"] == "GSP"
    assert "GSP =" in tab.recalc_view.pv_views[("gsp", "after")].header.text()
    assert not tab.recalc_view.pv_views[("gsp", "after")].grid.search_bar.isVisible()


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

    year_item = overview.ledger.topLevelItem(0)
    assert year_item.text(3) == "140.00"
    assert year_item.child(0).text(3) == "125.00"
    assert year_item.child(1).text(3) == "15.00"


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
        "MonthlyMTP", "Accum MTP", "GLP", "GSP", "AccumGLP", "Loan Int",
        "Loan Balance", "Loan Repay", "Premium", "PremTD", "Prem Load", "mAV",
        "NAAR", "Base COI", "Rider COI", "Benefit COI", "EPU", "MFEE", "MD",
        "Exception Prem", "AV", "New Loan", "Interest Rate", "Interest", "EAV",
        "SC", "ESV", "Var Loan", "Pref Loan", "Reg Loan", "Ending LB", "IllustratedDB",
    ]

    assert summary.df.iloc[0].to_dict() == {
        "Date": date(2026, 1, 15), "Year": 1, "Month": 1, "Attained Age": 45,
        "GrossWD": 20.0, "DBO": "B", "TotalSA": 150000.0, "PSC": 6.0,
        "MonthlyMTP": 100.0, "Accum MTP": 500.0, "GLP": 1000.0, "GSP": 2000.0,
        "AccumGLP": 3000.0, "Loan Int": 6.0, "Loan Balance": 66.0,
        "Loan Repay": 12.0, "Premium": 100.0, "PremTD": 20000.0,
        "Prem Load": 7.5, "mAV": 900.0, "NAAR": 50000.0, "Base COI": 20.0,
        "Rider COI": 2.0, "Benefit COI": 4.0, "EPU": 6.0, "MFEE": 8.0,
        "MD": 11.0, "Exception Prem": 25.0, "AV": 950.0, "New Loan": 6.0,
        "Interest Rate": 4.0, "Interest": 4.0, "EAV": 1000.0, "SC": 90.0,
        "ESV": 900.0, "Var Loan": 36.0, "Pref Loan": 24.0, "Reg Loan": 12.0,
        "Ending LB": 72.0, "IllustratedDB": 150000.0,
    }
    assert summary.df.iloc[1]["AV"] == 1050.0
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
        total_deduction=11.0,
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
        total_deduction=12.0,
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
        "Year", "Month", "Age", "Prem", "PremLoad", "Withdrawals", "ForceOuts",
        "MD", "Interest", "EAV", "SC", "LN", "ESV", "Death Benefit", "Status",
    ]
    year_item = overview.ledger.topLevelItem(0)
    assert [year_item.text(index) for index in range(overview.ledger.columnCount())] == [
        "1", "2", "45", "140.00", "9.00", "50.00", "5.00",
        "23.00", "10.00", "1,200.00", "80.00", "20.00", "1,100.00",
        "151,000", "LAPSED",
    ]


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
