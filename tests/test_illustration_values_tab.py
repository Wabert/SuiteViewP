import os
from dataclasses import replace

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtWidgets import QApplication

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


def test_values_tab_uses_one_tab_per_group_each_leading_with_locators():
    _app()
    tab = IllustrationValuesTab()

    tab.display_projection(_policy(), [_state()])

    titles = [tab.tabs.tabText(index) for index in range(tab.tabs.count())]
    assert titles == [
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
    ]

    for title, grid in tab._tab_grids.items():
        columns = list(grid.df.columns)
        assert columns[:4] == ["Date", "Year", "Month", "Attained Age"], title


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

    tab.display_projection(_policy(), [_state()])

    summary = tab._tab_grids["Summary"]
    columns = list(summary.df.columns)
    assert columns == ["Date", "Year", "Month", "Attained Age"] + tab.SUMMARY_COLUMNS

    from PyQt6.QtCore import Qt as QtCore

    model = summary.model

    def header(name: str) -> str:
        index = model._original_df.columns.get_loc(name)
        return model.headerData(index, QtCore.Orientation.Horizontal, QtCore.ItemDataRole.DisplayRole)

    assert header("PolicyDebt") == "Loan Balance"
    assert header("Monthly Deduction") == "MD"
    assert header("EA") == "EAV"
    assert "Loan Int" in columns
    assert "New Loan" in columns


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
    assert year_item.text(2) == "140.00"
    assert year_item.child(0).text(2) == "125.00"
    assert year_item.child(1).text(2) == "15.00"


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
