import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtWidgets import QApplication

from suiteview.illustration.models.calc_state import MonthlyState
from suiteview.illustration.models.policy_data import CoverageSegment, IllustrationPolicyData
from suiteview.illustration.ui.values_tab import IllustrationValuesTab


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
        "Summary",
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
