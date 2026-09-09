import os
from dataclasses import replace
from datetime import date

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtWidgets import QApplication, QTabWidget
from PyQt6.QtGui import QFontMetrics

from suiteview.illustration.models.calc_state import MonthlyState
from suiteview.illustration.models.policy_data import CoverageSegment, IllustrationPolicyData
from suiteview.illustration.ui.values_tab import IllustrationValuesTab
from suiteview.illustration.ui.values_overview import (
    FROZEN_LEDGER_COLUMN_COUNT,
    LEDGER_COLUMNS,
    SPACER_COLUMN,
    ValuesOverview,
    _status_text,
    build_charge_bands,
    build_chart_series,
)


_QT_APP = None


def test_overview_status_includes_permanent_mec_state():
    assert _status_text(MonthlyState(is_mec=True)) == "MEC"
    assert _status_text(MonthlyState(is_mec=True, lapsed=True)) == "MEC LAPSED"
    assert _status_text(
        MonthlyState(is_mec=True, lapsed=True, matured=True)
    ) == "MEC Maturity"


def test_overview_excludes_post_maturity_row():
    _app()
    overview = ValuesOverview()
    policy = _policy()
    policy.maturity_age = 95
    inforce = MonthlyState(policy_year=0, policy_month=0, attained_age=94)
    maturity = MonthlyState(
        policy_year=58,
        policy_month=12,
        attained_age=94,
        av_end_of_month=1000.0,
    )
    post_maturity = MonthlyState(
        policy_year=59,
        policy_month=1,
        attained_age=95,
        av_end_of_month=-25.0,
        matured=True,
    )

    overview.display(policy, [inforce, maturity, post_maturity])

    assert overview.ledger.topLevelItemCount() == 1
    assert overview.ledger.topLevelItem(0).text(LEDGER_COLUMNS.index("Year")) == "58"
    assert overview.kpi_av.value.text() == "1,000"


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


@pytest.mark.parametrize("coverage_count", [1, 2, 3, 7, 12])
def test_policy_values_shows_every_coverage_in_numeric_order(coverage_count):
    _app()
    tab = IllustrationValuesTab()
    slots = list(range(1, coverage_count + 1))
    state = MonthlyState(
        scr_rates_by_coverage={f"cov{i}": i + 0.123456 for i in reversed(slots)},
        surrender_charges_by_coverage={f"cov{i}": i * 100.0 for i in reversed(slots)},
        surrender_charge=sum(i * 100.0 for i in slots),
        surrender_value=12345.0,
    )
    policy = IllustrationPolicyData(
        segments=[CoverageSegment(face_amount=100000) for _ in slots],
    )

    tab.display_projection(policy, [state])

    grid = tab._tab_grids["Policy Values"]
    columns = list(grid.df.columns)
    scr_columns = [f"SCR Cov {i}" for i in slots]
    sc_columns = [f"SC Cov {i}" for i in slots]
    assert columns == [
        "Date", "Year", "Month", "Attained Age", "AV",
        *scr_columns, *sc_columns,
        "FullSC", "LapseSV", "Requested Loan", "Loan Mode Effective",
        "Scheduled Loan Amount", "Remaining Distribution", "vAppliedLoan", "Gain",
        "New Reg LN", "New Pref LN", "AdvRegLNInt", "PrefRegLNInt",
        "Total Rg Ln Princ", "Total Pref Ln Princ", "Total Vbl Ln Princ", "AV Display",
    ]
    assert grid.df.iloc[0][scr_columns].tolist() == [i + 0.123456 for i in slots]
    assert grid.df.iloc[0][sc_columns].tolist() == [i * 100.0 for i in slots]
    assert grid.df.iloc[0]["FullSC"] == state.surrender_charge
    assert grid.df.iloc[0]["LapseSV"] == 12345.0
    assert grid.model.data(grid.model.index(0, columns.index(scr_columns[-1]))) == (
        f"{coverage_count}.123456"
    )


def test_policy_values_coverage_columns_stay_stable_across_months_and_reset_on_reload():
    _app()
    tab = IllustrationValuesTab()
    first = MonthlyState(
        scr_rates_by_coverage={"cov2": 2.0},
        surrender_charges_by_coverage={"cov2": 200.0},
    )
    second = MonthlyState(
        scr_rates_by_coverage={"cov1": 1.0},
        surrender_charges_by_coverage={"cov7": 700.0},
    )

    tab.display_projection(_policy(), [first, second])

    grid = tab._tab_grids["Policy Values"]
    assert grid.df[["SCR Cov 1", "SCR Cov 2", "SCR Cov 3"]].values.tolist() == [
        [0.0, 2.0, 0.0], [1.0, 0.0, 0.0],
    ]
    assert grid.df[["SC Cov 1", "SC Cov 2", "SC Cov 3"]].values.tolist() == [
        [0.0, 200.0, 0.0], [0.0, 0.0, 700.0],
    ]
    assert "SCR Cov 4" not in grid.df.columns
    assert "SC Cov 4" not in grid.df.columns

    tab.display_projection(_policy(), [_state()])

    assert "SCR Cov 3" not in grid.df.columns
    assert "SC Cov 3" not in grid.df.columns


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


def test_view_toggle_defaults_to_current_and_hides_until_guaranteed_run():
    _app()
    tab = IllustrationValuesTab()

    # Mutually-exclusive segmented pair; Current Values is the default.
    assert tab.view_toggle_group.exclusive()
    assert tab.current_toggle.isChecked()
    assert not tab.guaranteed_toggle.isChecked()
    assert not tab.current_toggle.isVisibleTo(tab)
    assert not tab.guaranteed_toggle.isVisibleTo(tab)

    # A current-only run keeps the pair hidden — no guaranteed side to offer.
    tab.display_projection(_policy(), [_state()])
    assert not tab.current_toggle.isVisibleTo(tab)
    assert not tab.guaranteed_toggle.isVisibleTo(tab)
    assert tab.current_toggle.isChecked()


def test_view_toggle_switches_between_current_and_guaranteed_projections():
    _app()
    tab = IllustrationValuesTab()
    current = replace(_state(), av_end_of_month=9990.0)
    guaranteed = replace(_state(), av_end_of_month=5555.0)

    tab.display_projection(_policy(), [current])
    tab.set_guaranteed_results(_policy(), [guaranteed])

    # The pair appears once a guaranteed run exists; Current stays selected.
    assert tab.current_toggle.isVisibleTo(tab)
    assert tab.guaranteed_toggle.isVisibleTo(tab)
    assert tab.current_toggle.isChecked()
    assert tab._tab_grids["Summary"].df.iloc[0]["EAV"] == 9990.0

    # Guaranteed Values: the exclusive group unchecks Current and the grids
    # re-render from the guaranteed run.
    tab.guaranteed_toggle.setChecked(True)
    assert not tab.current_toggle.isChecked()
    assert tab._tab_grids["Summary"].df.iloc[0]["EAV"] == 5555.0
    assert tab.status_label.text().startswith("GUARANTEED")

    # Current Values: back to the current-assumption projection.
    tab.current_toggle.setChecked(True)
    assert not tab.guaranteed_toggle.isChecked()
    assert tab._tab_grids["Summary"].df.iloc[0]["EAV"] == 9990.0
    assert tab.status_label.text().startswith("Showing valuation snapshot")


def test_new_projection_resets_view_toggle_to_current():
    _app()
    tab = IllustrationValuesTab()
    tab.display_projection(_policy(), [_state()])
    tab.set_guaranteed_results(_policy(), [_state()])
    tab.guaranteed_toggle.setChecked(True)

    tab.display_projection(_policy(), [_state()])

    assert tab.current_toggle.isChecked()
    assert not tab.guaranteed_toggle.isChecked()
    assert not tab.current_toggle.isVisibleTo(tab)
    assert not tab.guaranteed_toggle.isVisibleTo(tab)


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
        "accum_glp_prior_amount": 4500.0,
        "accum_glp_months_prior": 4,
        "accum_glp_months_after": 8,
        "accum_glp_prorata_delta": 125.0,
        "accum_glp_new_amount": 4625.0,
        "seven_pay_prior": 80.0,
        "seven_pay_before": 80.0,
        "seven_pay_after": 95.0,
        "seven_pay_new": 95.0,
        "tamra_case": "within_period",
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
    _app()
    tab = IllustrationValuesTab()

    seed = _state()
    seed.date = date(2026, 6, 1)
    seed.glp = 90.0
    seed.gsp = 1100.0
    seed.accumulated_glp = 4500.0
    seed.tamra_7pay_start_date = date(2026, 1, 1)
    seed.tamra_7pay_level = 80.0
    seed.tamra_year = 1
    recalc = _recalc_state()
    recalc.accumulated_glp = 4625.0

    tab.display_projection(_policy(), [seed, recalc])

    summary = tab.recalc_view.summary_grid.df
    assert list(summary.columns) == [
        "Effective Date", "GLP", "GSP", "AccumGLP",
        "7-Pay Premium", "7-Pay Start Date",
    ]

    # Row 0 is the valuation baseline.
    base = summary.iloc[0]
    assert base["Effective Date"] == "06/01/2026"
    assert base["GLP"] == 90.0 and base["GSP"] == 1100.0
    assert base["AccumGLP"] == 4500.0
    assert base["7-Pay Start Date"] == "01/01/2026" and base["7-Pay Premium"] == 80.0

    # Row 1 shows the resulting values plus the active seven-pay period.
    row = summary.iloc[1]
    assert row["Effective Date"] == "05/15/2026"
    assert (row["GLP"], row["GSP"], row["AccumGLP"]) == (115.0, 1050.0, 4625.0)
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


def test_tefra_tamra_recalc_summary_hides_inactive_seven_pay_values():
    _app()
    tab = IllustrationValuesTab()
    seed = _state()
    seed.tamra_year = 8
    seed.tamra_7pay_start_date = date(2018, 1, 1)
    seed.tamra_7pay_level = 80.0
    recalc = _recalc_state()
    recalc.guideline_recalc["tamra_case"] = "no_recalc"

    tab.display_projection(_policy(), [seed, recalc])

    summary = tab.recalc_view.summary_grid.df
    assert summary["7-Pay Start Date"].tolist() == ["", ""]
    assert summary["7-Pay Premium"].isna().all()


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
    assert detail_view.accum_glp_grid.df.iloc[0].to_dict() == {
        "Premium": "AccumGLP",
        "Prior Amount": 4500.0,
        "New GLP - Old GLP": 25.0,
        "Months Remaining": 8,
        "AccumGLP Adj.": 125.0,
        "New Amount": 4625.0,
    }
    tamra = summary.iloc[2]
    assert tamra["Premium"] == "7-Pay"
    assert tamra["Prior Prem"] == 80.0
    assert tamra["New Prem"] == 95.0
    assert tamra[
        ["Before Change", "After Change", "Δ (After − Before)"]
    ].isna().all()

    recalc_tabs = detail_view.tabs
    assert [recalc_tabs.tabText(index) for index in range(recalc_tabs.count())] == [
        "Summary", "GLP Before", "GLP After", "GSP Before", "GSP After",
        "TAMRA Calc", "MEC Back-Test", "New 7-Pay Period",
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
    # MTP/CTP list every base coverage segment (like Monthly Deduction), so
    # both segments of the 2-segment policy show regardless of the active flags.
    mtp_columns = list(tab._tab_grids["MTP"].df.columns)
    assert "MTP Cov 1" in mtp_columns
    assert "MTP Cov 2" in mtp_columns
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


def test_mtp_ctp_show_all_segments_and_rider_columns():
    _app()
    tab = IllustrationValuesTab()

    state = _state()
    state.mtp_detail = {
        "MTP Cov 1": 100.0,
        "MTP Cov 2": 50.0,
        "MTP Rider R1_1": 7.8,
        "vMTP": 1200.0,
    }
    state.ctp_detail = {
        "CTP Cov 1": 120.0,
        "CTP Cov 2": 60.0,
        "CTP Rider R1_1": 9.0,
        "vCTP": 1440.0,
    }
    tab.display_projection(_policy(), [state])

    mtp_columns = list(tab._tab_grids["MTP"].df.columns)
    assert "MTP Cov 1" in mtp_columns
    assert "MTP Cov 2" in mtp_columns
    assert "MTP Rider R1_1" in mtp_columns

    ctp_columns = list(tab._tab_grids["CTP"].df.columns)
    assert "CTP Cov 1" in ctp_columns
    assert "CTP Cov 2" in ctp_columns
    assert "CTP Rider R1_1" in ctp_columns


def test_mtp_shows_ffl_waiver_intermediates_before_mtp_wo_pw():
    _app()
    tab = IllustrationValuesTab()

    state = _state()
    state.mtp_detail = {
        "MTP Cov 1": 100.0,
        "Min_Base": 120.0,
        "Min_Base_Table": 60.0,
        "Min_Base_Flat": 5.0,
        "PWoC_MinBasis": 185.42,
        "PWoT_MinBasis": 2012.40,
        "MTP w/o PW": 2000.0,
        "vMTP": 1200.0,
    }
    tab.display_projection(_policy(), [state])

    mtp_columns = list(tab._tab_grids["MTP"].df.columns)
    for column in ("Min_Base", "Min_Base_Table", "Min_Base_Flat",
                   "PWoC_MinBasis", "PWoT_MinBasis"):
        assert column in mtp_columns
        assert mtp_columns.index(column) < mtp_columns.index("MTP w/o PW")


def test_mtp_omits_ffl_intermediates_for_non_ffl():
    _app()
    tab = IllustrationValuesTab()

    state = _state()
    state.mtp_detail = {"MTP Cov 1": 100.0, "MTP w/o PW": 2000.0, "vMTP": 1200.0}
    tab.display_projection(_policy(), [state])

    mtp_columns = list(tab._tab_grids["MTP"].df.columns)
    assert "Min_Base" not in mtp_columns
    assert "PWoC_MinBasis" not in mtp_columns


def test_mtp_headers_drop_the_v_prefix():
    _app()
    tab = IllustrationValuesTab()

    # The DataFrame keys stay vMTP/vMonthlyMTP/vAccumMTP (so they never collide
    # with the Summary/Overview MTP columns), but the MTP tab displays them
    # without the "v" prefix.
    labels = tab._header_labels_for_tab(tab.MTP_GROUP)
    assert labels["vMTP"] == "MTP"
    assert labels["vMonthlyMTP"] == "MonthlyMTP"
    assert labels["vAccumMTP"] == "AccumMTP"


def test_change_groups_carry_total_sa_on_every_month():
    _app()
    tab = IllustrationValuesTab()
    first = _state()
    first.coverage_after_change = {"CurrentSA": 100000.0}
    second = _state()
    second.coverage_after_change = {"CurrentSA": 75000.0}
    second.face_change_detail = {
        "Input Face": 75000.0,
        "Total SA": 75000.0,
    }

    tab.display_projection(_policy(), [first, second])

    for group in ("DB Option Change", "Increase/Decrease"):
        assert list(tab._tab_grids[group].df["Total SA"]) == [100000.0, 75000.0]


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


def test_av_column_shows_zero_when_exception_holds_account_value_flat():
    # When the MD / GP exception premium holds the account value at exactly 0,
    # the AV column must show 0 — not the negative pre-exception (after-deduction)
    # value. Regression for the "AV negative while AV Display is 0" display bug.
    _app()
    tab = IllustrationValuesTab()
    state = _state()
    state.av_after_deduction = -512.0
    state.av_after_exception = 0.0
    state.exception_prem_mode = True
    state.gp_exception_prem = 524.0

    tab.display_projection(_policy(), [state])

    assert tab._tab_grids["Summary"].df.iloc[0]["AV"] == 0.0


def test_premium_outlay_includes_exception_premium_in_ending_values():
    _app()
    tab = IllustrationValuesTab()
    state = _state()
    state.gross_premium = 100.0
    state.gp_exception_prem = 25.0

    tab.display_projection(_policy(), [state])

    ending = tab._tab_grids["Ending Values"].df
    assert ending.iloc[0]["PremiumOutlay"] == 125.0


def test_exception_premium_grid_exposes_percentage_and_flat_loads():
    state = MonthlyState(
        gp_exception_prem_gross=462.01,
        gp_exception_prem_discount=4.25,
        gp_exception_percentage_load=24.18,
        gp_exception_flat_load=1.65,
        gp_exception_prem=483.59,
    )

    values = IllustrationValuesTab._exception_premium_values(state)

    assert values["Exception_Percent_Load"] == 24.18
    assert values["Exception_Flat_Load"] == 1.65
    assert (
        values["GP_Exception_Prem_Gross"]
        - values["Exception_Prem_Discount"]
        + values["Exception_Percent_Load"]
        + values["Exception_Flat_Load"]
    ) == pytest.approx(values["vGP_Exception_Prem"])


def test_chart_cumulative_premium_uses_premium_outlay():
    # The cumulative-premium line reads premiums_to_date_after_exception, which
    # already folds in the MD and GP exception premiums (carried forward).
    first = MonthlyState(policy_year=1, policy_month=1, gross_premium=100.0,
                         gp_exception_prem=25.0, premiums_to_date=10_000.0,
                         premiums_to_date_after_exception=10_025.0)
    second = MonthlyState(policy_year=1, policy_month=2, gross_premium=10.0,
                          gp_exception_prem=5.0, premiums_to_date=20_000.0,
                          premiums_to_date_after_exception=20_030.0)

    series = build_chart_series([first, second])
    cum_premium = next(entry for entry in series if entry.name == "Cum Premium")

    assert cum_premium.points == [(1.0, 10_025.0), (1 + 1 / 12, 20_030.0)]


def test_chart_accum_7pay_uses_7702a_annual_limit_not_premiums_paid():
    states = [
        MonthlyState(
            policy_year=3,
            policy_month=12,
            tamra_year=3,
            tamra_7pay_level=8_000.0,
            accumulated_7pay=1_500.0,
        ),
        MonthlyState(
            policy_year=4,
            policy_month=12,
            tamra_year=4,
            tamra_7pay_level=8_000.0,
            accumulated_7pay=30_000.0,
        ),
        MonthlyState(
            policy_year=8,
            policy_month=12,
            tamra_year=8,
            tamra_7pay_level=8_000.0,
            accumulated_7pay=35_000.0,
        ),
    ]

    series = build_chart_series(states)
    accumulated_limit = next(
        entry for entry in series if entry.name == "Accum 7-Pay Prem"
    )

    assert accumulated_limit.points == [
        (3 + 11 / 12, 24_000.0),
        (4 + 11 / 12, 32_000.0),
    ]


def test_chart_accum_7pay_restarts_with_new_tamra_period():
    states = [
        MonthlyState(
            policy_year=10,
            policy_month=5,
            tamra_year=6,
            tamra_7pay_level=5_000.0,
        ),
        MonthlyState(
            policy_year=10,
            policy_month=6,
            tamra_year=1,
            tamra_7pay_level=7_500.0,
        ),
    ]

    series = build_chart_series(states)
    accumulated_limit = next(
        entry for entry in series if entry.name == "Accum 7-Pay Prem"
    )

    assert accumulated_limit.points == [
        (10 + 4 / 12, 30_000.0),
        (10 + 5 / 12, 7_500.0),
    ]


def test_chart_adds_policy_debt_series_when_projection_has_a_loan():
    # policy_debt is the end-of-month total of all six loan buckets (principal
    # + accrued interest) — the same figure as the ledger LN / Ending LB.
    first = MonthlyState(policy_year=1, policy_month=1, policy_debt=0.0)
    second = MonthlyState(policy_year=1, policy_month=2, policy_debt=1_250.75)

    series = build_chart_series([first, second])
    debt = next(entry for entry in series if entry.name == "Policy Debt")

    assert debt.points == [(1.0, 0.0), (1 + 1 / 12, 1_250.75)]
    assert debt.visible


def test_chart_omits_policy_debt_series_when_never_borrowed():
    # No loan at any point (existing or illustrated) → no series, no dead
    # legend chip.
    first = MonthlyState(policy_year=1, policy_month=1, policy_debt=0.0)
    second = MonthlyState(policy_year=1, policy_month=2, policy_debt=0.0)

    series = build_chart_series([first, second])

    assert all(entry.name != "Policy Debt" for entry in series)


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
    assert by_name["SIGTERM"] == 7.0  # 1U536C00 CovType in rider_table.json
    assert 999.0 not in by_name.values()


def test_charge_chart_sums_same_label_rider_keys_into_one_band():
    # Two occurrences of the same rider plancode share a display label and
    # must stack into a single summed band, not two identically-named ones.
    first = MonthlyState(
        policy_year=1,
        policy_month=1,
        rider_charge_detail={"1U538229_1": 3.0, "1U538229_2": 5.0},
    )
    second = MonthlyState(
        policy_year=1,
        policy_month=2,
        rider_charge_detail={"1U538229_1": 2.0, "1U538229_2": 4.0},
    )

    bands = build_charge_bands([first, second])
    ctr_bands = [band for band in bands if band.name == "CTR"]

    assert len(ctr_bands) == 1
    assert ctr_bands[0].points[-1][1] == 14.0  # 3+5 then +2+4, cumulative


def test_charge_chart_labels_riders_by_full_plancode_from_rider_table():
    # Policy U0356726: 1U538F00 is a Children's Term Rider, 1U538I00 a Spouse
    # Term Rider — the label is the CovType from rider_table.json keyed by the
    # FULL plancode (a 1U538-prefix guess showed both as "CTR"). Plancodes not
    # in the rider table fall back to the honest "Rider <plancode>".
    state = MonthlyState(
        policy_year=1,
        policy_month=1,
        rider_charge_detail={"1U538F00_1": 0.5, "1U538I00_1": 3.8, "9ZZZZZ99_1": 1.1},
    )

    bands = build_charge_bands([state])
    by_name = {band.name: band.points[-1][1] for band in bands}

    assert by_name["CTR"] == 0.5
    assert by_name["STR"] == 3.8
    assert by_name["Rider 9ZZZZZ99"] == 1.1


def test_charge_chart_uses_legacy_coi_when_no_base_breakout_exists():
    state = MonthlyState(policy_year=1, policy_month=1, coi_charge=12.5)

    bands = build_charge_bands([state])

    assert [(band.name, band.points[-1][1]) for band in bands] == [("Base COI", 12.5)]


def test_overview_prem_column_excludes_gp_exception_premium():
    # Prem = premium_outlay − GP exception prem (gross + MD premium only);
    # the exception premium has its own column, so Prem + Exception Prem
    # reconstructs the full outlay with no double count.
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
    exc_col = LEDGER_COLUMNS.index("Exception Prem")
    year_item = overview.ledger.topLevelItem(0)
    assert year_item.text(prem_col) == "110.00"           # outlay 140 − exc 30
    assert year_item.child(0).text(prem_col) == "100.00"  # outlay 125 − exc 25
    assert year_item.child(1).text(prem_col) == "10.00"   # outlay 15 − exc 5
    assert year_item.text(exc_col) == "30.00"
    assert year_item.child(0).text(exc_col) == "25.00"
    assert year_item.child(1).text(exc_col) == "5.00"


def test_overview_ledger_shows_glp_gsp_totalgp_and_subject_payments():
    # GLP / GSP / TotalGP / SubjectPayments sit just before the Withdrawals
    # column. SubjectPayments is the amount tested against the total-GP limit:
    # accumulated premiums paid less accumulated withdrawals.
    _app()
    overview = ValuesOverview()
    inforce = MonthlyState(policy_year=0, policy_month=0, attained_age=44)
    final = replace(
        _state(), glp=1_234.56, gsp=23_456.78, accumulated_glp=8_641.92,
        guideline_limit=23_456.78, premiums_to_date_after_exception=20_000.0,
        withdrawals_to_date=1_000.0)

    overview.display(_policy(), [inforce, final])

    glp_col = LEDGER_COLUMNS.index("GLP")
    gsp_col = LEDGER_COLUMNS.index("GSP")
    total_gp_col = LEDGER_COLUMNS.index("TotalGP")
    subject_col = LEDGER_COLUMNS.index("SubjectPayments")
    # The new columns land immediately before Withdrawals.
    assert subject_col == LEDGER_COLUMNS.index("Withdrawals") - 1
    year_item = overview.ledger.topLevelItem(0)
    assert year_item.text(glp_col) == "1,234.56"
    assert year_item.text(gsp_col) == "23,456.78"
    assert year_item.text(total_gp_col) == "23,456.78"
    # SubjectPayments = prem-to-date − wd-to-date (20,000 − 1,000).
    assert year_item.text(subject_col) == "19,000.00"


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
        # Ending SV = EAV − SC − Ending LB (1000 − 90 − 72); deliberately
        # distinct from the lapse-check surrender_value above.
        ending_sv=838.0,
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
        ending_sv=940.0,           # EAV − SC − Ending LB (1200 − 80 − 180)
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
        "Interest Rate": 0.049, "Interest": 4.0, "EAV": 1000.0, "SC": 90.0,
        "ESV": 838.0, "Var Loan": 36.0, "Pref Loan": 24.0, "Reg Loan": 12.0,
        "Ending LB": 72.0, "IllustratedDB": 150000.0,
    }
    assert summary.df.iloc[1]["AV"] == 1050.0
    assert summary.df.iloc[1]["Interest Rate"] == 0.05
    assert summary.df.iloc[1]["EAV"] == 1200.0
    # ESV is the ENDING surrender value (EAV − SC − Ending LB), not the
    # lapse-check surrender_value.
    assert summary.df.iloc[1]["ESV"] == 940.0


def test_overview_ledger_restores_compact_values_order():
    _app()
    overview = ValuesOverview()
    inforce = MonthlyState(date=date(2025, 12, 15), policy_year=0, policy_month=0,
                           attained_age=44)
    first = MonthlyState(
        date=date(2026, 1, 15),
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
        surrender_value=880.0,
        ending_sv=900.0,           # EAV − SC − LN (1000 − 90 − 10)
        ending_db=150000.0,
    )
    second = MonthlyState(
        date=date(2026, 2, 15),
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
        surrender_value=1080.0,
        ending_sv=1100.0,          # EAV − SC − LN (1200 − 80 − 20)
        ending_db=151000.0,
        lapsed=True,
    )

    overview.display(_policy(), [inforce, first, second])

    headers = [overview.ledger.headerItem().text(index) for index in range(overview.ledger.columnCount())]
    assert headers == [
        "Year", "Month", "Age", "Age EOY", "Date",
        "Distributions", "Contributions",
        "MD", "AV", "SV", "Interest", "EAV", "SC", "LN", "ESV", "Shadow EAV",
        "Death Benefit", "Status",
        "",
        "GLP", "GSP", "TotalGP", "SubjectPayments",
        "Withdrawals", "ForceOuts", "Loan Repay", "Prem", "Exception Prem", "New Loan",
    ]
    # Shadow EAV only shows for shadow-account products.
    assert overview.ledger.isColumnHidden(LEDGER_COLUMNS.index("Shadow EAV"))
    year_item = overview.ledger.topLevelItem(0)
    assert [year_item.text(index) for index in range(overview.ledger.columnCount())] == [
        "1", "0", "45", "46", "12/15/2025",    # first year row anchors to the valuation date
        "60.00", "185.00",     # 45+5+10 out (wd net of force-out)  |  45+110+30 in
        "23.00", "1,150.00", "1,050.00", "10.00", "1,200.00", "80.00",
        "20.00", "1,100.00", "0.00",
        "151,000", "LAPSED",
        "",
        "0.00", "0.00", "0.00", "-50.00",      # GLP | GSP | TotalGP | SubjectPayments (0 − 50 wd)
        "45.00", "5.00", "45.00", "110.00", "30.00", "10.00",
    ]


def _overview_two_month_projection():
    """inforce + two projected months with distinct cash flows and dates."""
    inforce = MonthlyState(date=date(2025, 12, 15), policy_year=0, policy_month=0,
                           attained_age=44)
    first = MonthlyState(
        date=date(2026, 1, 15), policy_year=1, policy_month=1, attained_age=45,
        gross_premium=100.0, gp_exception_prem=25.0,
        withdrawals_to_date=20.0, guideline_forceout=3.0,
        applied_regular_loan=6.0, applied_loan_repayment=30.0,
    )
    second = MonthlyState(
        date=date(2026, 2, 15), policy_year=1, policy_month=2, attained_age=45,
        gross_premium=10.0, gp_exception_prem=5.0,
        withdrawals_to_date=50.0, guideline_forceout=2.0,
        applied_regular_loan=4.0, applied_loan_repayment=15.0,
    )
    return [inforce, first, second]


def test_overview_date_column_follows_age_with_row_dates():
    _app()
    overview = ValuesOverview()

    overview.display(_policy(), _overview_two_month_projection())

    date_col = LEDGER_COLUMNS.index("Date")
    assert date_col == LEDGER_COLUMNS.index("Age EOY") + 1 == 4
    year_item = overview.ledger.topLevelItem(0)
    # The first (inforce) year row carries the valuation date; its months are
    # kept as children since none of them repeats the valuation date.
    assert year_item.text(date_col) == "12/15/2025"
    assert year_item.child(0).text(date_col) == "01/15/2026"
    assert year_item.child(1).text(date_col) == "02/15/2026"


def test_overview_year_rows_anchor_to_beginning_of_year_without_duplication():
    _app()
    overview = ValuesOverview()
    inforce = MonthlyState(date=date(2025, 4, 15), policy_year=0, policy_month=0,
                           attained_age=44)
    y1m1 = MonthlyState(date=date(2025, 5, 15), policy_year=1, policy_month=1,
                        attained_age=45)
    y1m2 = MonthlyState(date=date(2025, 6, 15), policy_year=1, policy_month=2,
                        attained_age=45)
    y2m1 = MonthlyState(date=date(2026, 5, 15), policy_year=2, policy_month=1,
                        attained_age=46)
    y2m2 = MonthlyState(date=date(2026, 6, 15), policy_year=2, policy_month=2,
                        attained_age=46)

    overview.display(_policy(), [inforce, y1m1, y1m2, y2m1, y2m2])

    date_col = LEDGER_COLUMNS.index("Date")
    year1 = overview.ledger.topLevelItem(0)
    year2 = overview.ledger.topLevelItem(1)
    # First year row = valuation date; its months are all kept as children.
    assert year1.text(date_col) == "04/15/2025"
    assert [year1.child(i).text(date_col) for i in range(year1.childCount())] == [
        "05/15/2025", "06/15/2025",
    ]
    # A full year's row IS its beginning-of-year (anniversary) month; that month
    # is not repeated as a child.
    assert year2.text(date_col) == "05/15/2026"
    assert [year2.child(i).text(date_col) for i in range(year2.childCount())] == [
        "06/15/2026",
    ]
    # Fully expanded, the dates form one clean monthliversary sequence.
    fully_expanded = [year1.text(date_col)]
    fully_expanded += [year1.child(i).text(date_col) for i in range(year1.childCount())]
    fully_expanded += [year2.text(date_col)]
    fully_expanded += [year2.child(i).text(date_col) for i in range(year2.childCount())]
    assert fully_expanded == [
        "04/15/2025", "05/15/2025", "06/15/2025", "05/15/2026", "06/15/2026",
    ]
    assert len(fully_expanded) == len(set(fully_expanded))


def test_overview_year_row_swaps_annual_totals_for_the_month_when_expanded():
    _app()
    overview = ValuesOverview()
    inforce = MonthlyState(date=date(2025, 4, 15), policy_year=0, policy_month=0,
                           attained_age=44)
    y1m1 = MonthlyState(date=date(2025, 5, 15), policy_year=1, policy_month=1,
                        attained_age=45)
    y2m1 = MonthlyState(date=date(2026, 5, 15), policy_year=2, policy_month=1,
                        attained_age=46, gross_premium=100.0,
                        withdrawals_to_date=10.0, av_end_of_month=1000.0)
    y2m2 = MonthlyState(date=date(2026, 6, 15), policy_year=2, policy_month=2,
                        attained_age=46, gross_premium=40.0,
                        withdrawals_to_date=25.0, av_end_of_month=1100.0)

    overview.display(_policy(), [inforce, y1m1, y2m1, y2m2])

    contrib = LEDGER_COLUMNS.index("Contributions")
    distrib = LEDGER_COLUMNS.index("Distributions")
    eav = LEDGER_COLUMNS.index("EAV")
    year2 = overview.ledger.topLevelItem(1)

    # Collapsed → the full policy year's roll-up.
    assert (year2.text(contrib), year2.text(distrib), year2.text(eav)) == (
        "140.00", "25.00", "1,100.00")
    # Expanded → just the beginning-of-year month the row now represents.
    year2.setExpanded(True)
    assert (year2.text(contrib), year2.text(distrib), year2.text(eav)) == (
        "100.00", "10.00", "1,000.00")
    # Collapsing restores the annual roll-up.
    year2.setExpanded(False)
    assert (year2.text(contrib), year2.text(distrib), year2.text(eav)) == (
        "140.00", "25.00", "1,100.00")


def test_overview_contributions_and_distributions_roll_up_cash_flows():
    _app()
    overview = ValuesOverview()

    overview.display(_policy(), _overview_two_month_projection())

    contrib = LEDGER_COLUMNS.index("Contributions")
    distrib = LEDGER_COLUMNS.index("Distributions")
    assert (distrib, contrib) == (5, 6)  # Distributions first, right after locators

    year_item = overview.ledger.topLevelItem(0)
    # Contributions = Loan Repay + Prem + Exception Prem, same aggregation as
    # those columns. Prem excludes the GP exception premium (broken out in its
    # own column), so this is true money-in with no double count.
    assert year_item.text(contrib) == "185.00"           # 45 + 110 + 30
    assert year_item.child(0).text(contrib) == "155.00"  # 30 + 100 + 25
    assert year_item.child(1).text(contrib) == "30.00"   # 15 + 10 + 5
    # Distributions = Withdrawals + ForceOuts + New Loan, displayed positive
    # (Withdrawals are net of the force-out, so it is not double-counted).
    assert year_item.text(distrib) == "60.00"            # 45 + 5 + 10
    assert year_item.child(0).text(distrib) == "26.00"   # 17 + 3 + 6
    assert year_item.child(1).text(distrib) == "34.00"   # 28 + 2 + 4


def test_overview_relocated_cashflow_columns_sit_after_spacer():
    _app()
    overview = ValuesOverview()

    overview.display(_policy(), _overview_two_month_projection())

    assert LEDGER_COLUMNS[SPACER_COLUMN] == ""
    assert SPACER_COLUMN == LEDGER_COLUMNS.index("Status") + 1
    assert LEDGER_COLUMNS[SPACER_COLUMN + 1:] == [
        "GLP", "GSP", "TotalGP", "SubjectPayments",
        "Withdrawals", "ForceOuts", "Loan Repay", "Prem", "Exception Prem", "New Loan",
    ]
    year_item = overview.ledger.topLevelItem(0)
    assert year_item.text(SPACER_COLUMN) == ""
    assert year_item.text(LEDGER_COLUMNS.index("Withdrawals")) == "45.00"
    assert year_item.text(LEDGER_COLUMNS.index("New Loan")) == "10.00"


def test_overview_freeze_pane_sits_right_after_date():
    _app()
    overview = ValuesOverview()

    # Year | Month | Age | Age EOY | Date stay put; everything after scrolls.
    assert FROZEN_LEDGER_COLUMN_COUNT == LEDGER_COLUMNS.index("Date") + 1 == 5
    for column in range(FROZEN_LEDGER_COLUMN_COUNT):
        assert not overview.frozen_ledger.isColumnHidden(column), column
        assert overview.ledger.isColumnHidden(column), column
    for column in range(FROZEN_LEDGER_COLUMN_COUNT, len(LEDGER_COLUMNS)):
        assert overview.frozen_ledger.isColumnHidden(column), column
        assert not overview.ledger.isColumnHidden(column), column
    # The panes share the model and selection model so rows stay in lockstep.
    assert overview.frozen_ledger.model() is overview.ledger.model()
    assert overview.frozen_ledger.selectionModel() is overview.ledger.selectionModel()


def test_ending_values_floor_illustration_sv_but_not_esv():
    row = IllustrationValuesTab._ending_values(MonthlyState(
        av_end_of_month=50.0,
        policy_debt=0.0,
        surrender_value=-999.0,    # lapse-check SV — must NOT feed ES
        ending_sv=-125.0,          # ending SV (EAV − SC − LN)
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


# ── Not-yet-computed placeholder columns ────────────────────────────────


def _cell(grid, column_name: str, role, row: int = 0):
    model = grid.model
    column = model._original_df.columns.get_loc(column_name)
    return model.data(model.index(row, column), role)


def test_placeholder_columns_render_greyed_not_computed_markers():
    from PyQt6.QtCore import Qt as QtCore

    from suiteview.illustration.ui.values_tab import (
        NOT_COMPUTED_COLUMNS,
        NOT_COMPUTED_NOTE,
    )

    _app()
    tab = IllustrationValuesTab()
    tab.display_projection(_policy(), [_state()])

    # One representative placeholder per affected group — cells show an em
    # dash on a grey background (never a formatted zero) with the note as a
    # cell and header tooltip.
    representative = {
        "Testing": "7-Pay Yr 1",
        "TEFRA and TAMRA": "NPT_Premium",
        "Requested Premium": "1035_Amount",
        "Policy Values": "Requested Loan",
        "Accumulation": "Blended Index Rate",
        "Shadow Account": "Shadow_TPR",
        "Ending Values": "IllustrationGCO",
    }
    for title, column_name in representative.items():
        grid = tab._tab_grids[title]
        assert column_name in NOT_COMPUTED_COLUMNS, column_name
        assert _cell(grid, column_name, QtCore.ItemDataRole.DisplayRole) == "—", column_name
        assert _cell(grid, column_name, QtCore.ItemDataRole.BackgroundRole) is not None, column_name
        assert _cell(grid, column_name, QtCore.ItemDataRole.ToolTipRole) == NOT_COMPUTED_NOTE
        font = _cell(grid, column_name, QtCore.ItemDataRole.FontRole)
        assert font is not None and font.italic(), column_name
        header_index = grid.model._original_df.columns.get_loc(column_name)
        assert grid.model.headerData(
            header_index, QtCore.Orientation.Horizontal, QtCore.ItemDataRole.ToolTipRole
        ) == NOT_COMPUTED_NOTE, column_name

    # Computed columns keep the normal treatment: real values, no grey, no note.
    summary = tab._tab_grids["Summary"]
    assert _cell(summary, "EAV", QtCore.ItemDataRole.DisplayRole) == "9,990.00"
    assert _cell(summary, "EAV", QtCore.ItemDataRole.BackgroundRole) is None
    assert _cell(summary, "EAV", QtCore.ItemDataRole.ToolTipRole) is None


def test_placeholder_dataframe_values_stay_raw_for_copy_and_export():
    # The grey em-dash treatment is display-only — the DataFrame (feeding
    # clipboard copy and comparisons) still carries the raw placeholder values.
    _app()
    tab = IllustrationValuesTab()

    tab.display_projection(_policy(), [_state()])

    assert tab._tab_grids["Testing"].df.iloc[0]["7-Pay Yr 1"] == 0.0
    assert tab._tab_grids["Ending Values"].df.iloc[0]["IllustrationGCO"] == 0.0


def test_adv_reg_ln_int_shows_only_interest_in_advance():
    from PyQt6.QtCore import Qt as QtCore

    # The Policy Values "Adv Reg Ln Int" / "Pref Ln Int" columns are for
    # interest-in-advance only. An arrears loan accrues loan interest into the
    # Accumulation accrued buckets (reg_loan_charge) and must NOT leak it here.
    _app()
    tab = IllustrationValuesTab()
    arrears = replace(_state(), reg_loan_charge=0.67, pref_loan_charge=0.4,
                      adv_reg_ln_int=0.0, adv_pref_ln_int=0.0)

    tab.display_projection(_policy(), [arrears])

    policy_values = tab._tab_grids["Policy Values"]
    assert _cell(policy_values, "AdvRegLNInt", QtCore.ItemDataRole.DisplayRole) == "0.00"
    assert _cell(policy_values, "PrefRegLNInt", QtCore.ItemDataRole.DisplayRole) == "0.00"

    # An advance loan surfaces the prepaid interest folded into principal.
    advance = replace(_state(), reg_loan_charge=0.0, pref_loan_charge=0.0,
                      adv_reg_ln_int=5.25, adv_pref_ln_int=1.75)
    tab.display_projection(_policy(), [advance])
    policy_values = tab._tab_grids["Policy Values"]
    assert _cell(policy_values, "AdvRegLNInt", QtCore.ItemDataRole.DisplayRole) == "5.25"
    assert _cell(policy_values, "PrefRegLNInt", QtCore.ItemDataRole.DisplayRole) == "1.75"


def test_remaining_distribution_not_computed_only_on_policy_values_tab():
    from PyQt6.QtCore import Qt as QtCore

    # The shared "Remaining Distribution" key carries the withdrawal block's
    # computed value; only the Policy Values tab's loan-side column (not yet
    # computed by the engine) gets the placeholder treatment.
    _app()
    tab = IllustrationValuesTab()
    state = replace(_state(), remaining_distribution=123.45)

    tab.display_projection(_policy(), [state])

    withdrawals = tab._tab_grids["Withdrawals"]
    assert _cell(withdrawals, "Remaining Distribution", QtCore.ItemDataRole.DisplayRole) == "123.45"
    assert _cell(withdrawals, "Remaining Distribution", QtCore.ItemDataRole.BackgroundRole) is None
    policy_values = tab._tab_grids["Policy Values"]
    assert _cell(policy_values, "Remaining Distribution", QtCore.ItemDataRole.DisplayRole) == "—"
    assert _cell(policy_values, "Remaining Distribution", QtCore.ItemDataRole.BackgroundRole) is not None


# ── Guaranteed-run failure banner ───────────────────────────────────────


def test_guaranteed_failure_shows_banner_and_keeps_toggle_hidden():
    _app()
    tab = IllustrationValuesTab()
    tab.display_projection(_policy(), [_state()])
    assert not tab.guaranteed_warning.isVisibleTo(tab)

    tab.set_guaranteed_failure("no guaranteed COI rates for plancode")

    assert tab.guaranteed_warning.isVisibleTo(tab)
    text = tab.guaranteed_warning.text()
    assert "Guaranteed projection failed" in text
    assert "guaranteed values unavailable" in text
    assert "no guaranteed COI rates for plancode" in text
    # No guaranteed view exists, so the Current | Guaranteed pair stays hidden.
    assert not tab.current_toggle.isVisibleTo(tab)
    assert not tab.guaranteed_toggle.isVisibleTo(tab)


def test_guaranteed_failure_banner_clears_on_new_projection_or_success():
    _app()
    tab = IllustrationValuesTab()
    tab.display_projection(_policy(), [_state()])
    tab.set_guaranteed_failure("boom")
    assert tab.guaranteed_warning.isVisibleTo(tab)

    # A fresh current run resets the banner…
    tab.display_projection(_policy(), [_state()])
    assert not tab.guaranteed_warning.isVisibleTo(tab)
    assert tab._guaranteed_error is None

    # …and a successful guaranteed run clears any prior failure.
    tab.set_guaranteed_failure("boom again")
    tab.set_guaranteed_results(_policy(), [_state()])
    assert not tab.guaranteed_warning.isVisibleTo(tab)
    assert tab._guaranteed_error is None

    # clear_results also drops the banner.
    tab.set_guaranteed_failure("boom once more")
    tab.clear_results()
    assert not tab.guaranteed_warning.isVisibleTo(tab)


def test_guaranteed_failure_survives_session_capture_and_restore():
    _app()
    tab = IllustrationValuesTab()
    tab.display_projection(_policy(), [_state()])
    tab.set_guaranteed_failure("rate table missing")
    snapshot = tab.capture_session_state()
    assert snapshot["guaranteed_error"] == "rate table missing"

    restored = IllustrationValuesTab()
    assert restored.restore_session_state(snapshot)
    assert restored.guaranteed_warning.isVisibleTo(restored)
    assert "rate table missing" in restored.guaranteed_warning.text()


def test_report_tab_shows_guaranteed_failure_banner():
    from suiteview.illustration.core.report_builder import IllustrationReport
    from suiteview.illustration.ui.report_tab import IllustrationReportTab

    _app()
    report_tab = IllustrationReportTab()

    # Guaranteed side failed → loud banner naming the reason; the printed
    # pages themselves are untouched.
    report_tab.display_report(
        IllustrationReport(), guaranteed_error="lock values failed")
    assert report_tab.guaranteed_warning.isVisibleTo(report_tab)
    assert "GUARANTEED VALUES" in report_tab.guaranteed_warning.text()
    assert "lock values failed" in report_tab.guaranteed_warning.text()

    # Guaranteed side present → no banner.
    report_tab.display_report(IllustrationReport(has_guaranteed_values=True))
    assert not report_tab.guaranteed_warning.isVisibleTo(report_tab)

    report_tab.clear()
    assert not report_tab.guaranteed_warning.isVisibleTo(report_tab)
