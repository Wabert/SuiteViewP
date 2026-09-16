"""Policy Support service tests using the real compiler, solver and engine."""
import copy
from datetime import date
from types import SimpleNamespace

import pytest

from suiteview.illustration.core import calc_engine
from suiteview.illustration.core.bonus_rates import BonusConfig
from suiteview.illustration.core.rate_loader import IllustrationRates
from suiteview.illustration.models.plancode_config import PlancodeConfig
from suiteview.illustration.models.policy_data import CoverageSegment, IllustrationPolicyData
from suiteview.polview.services import guideline_exception_adjustment as gea
from suiteview.polview.services.glp_exception import GlpForecastAvailability


_QT_APP = None


@pytest.fixture
def forecast(monkeypatch):
    policy = IllustrationPolicyData(
        plancode="GLPTEST", def_of_life_ins="GPT",
        issue_date=date(1984, 1, 15), valuation_date=date(2026, 2, 15),
        issue_age=30, attained_age=72, maturity_age=121,
        policy_year=43, policy_month=2, duration=506,
        face_amount=100_000.0, units=100.0, db_option="A",
        account_value=4_780.24, modal_premium=300.0, billing_frequency=1,
        glp=0.0, gsp=77_435.75, accumulated_glp=77_435.75,
        premiums_paid_to_date=77_735.75, withdrawals_to_date=17_912.72,
        current_interest_rate=0.0, guaranteed_interest_rate=0.0,
        segments=[CoverageSegment(
            coverage_phase=1, issue_date=date(1984, 1, 15),
            face_amount=100_000.0, units=100.0)],
    )
    config = PlancodeConfig(
        plancode="GLPTEST", dbd=0.0, gint=0.0, corridor_code=None,
        epu_code="0", mfee="0", premium_load="0", prem_flat_load=0.0,
        lapse_value="SV",
    )
    rates = IllustrationRates(coi=[0.0, 2.7], segment_coi={1: [0.0, 2.7]})
    monkeypatch.setattr(calc_engine, "load_plancode", lambda _p: config)
    monkeypatch.setattr(calc_engine, "load_bonus_config", lambda *_: BonusConfig())
    monkeypatch.setattr(calc_engine.IllustrationEngine, "_load_rates",
                        lambda *_: rates)
    monkeypatch.setattr(gea, "check_forecast_availability",
                        lambda _: GlpForecastAvailability(True, "test", policy))

    def run(target=date(2027, 1, 15)):
        source = SimpleNamespace(
            accumulated_glp_target=policy.accumulated_glp,
            premium_td=policy.premiums_paid_to_date,
            total_withdrawals=policy.withdrawals_to_date,
            fetch_table=lambda _: [],
        )
        return gea.project_guideline_exception_target_forecast(source, target)

    return policy, config, rates, run


def test_zero_solve_never_reinstates_300_billing(forecast):
    _, _, _, run = forecast
    result = run()
    assert result.premium == 0.0
    assert all(row.premium == 0.0 for row in result.rows)
    assert result.rows[-1].account_value > 0.0
    assert result.rows[-1].surrender_value > 0.0
    assert result.zero_glp.premium == 0.0
    assert result.zero_glp.rows == result.rows
    assert result.no_forceout.premium == 0.0
    assert result.no_forceout.rows == result.rows


def test_valuation_snapshot_and_monthly_interest_match_rerun(forecast):
    policy, config, _, _ = forecast
    policy.account_value = 4494.38
    policy.current_interest_rate = 0.04
    config.interest_method = "ExactDays"
    source = SimpleNamespace(
        accumulated_glp_target=policy.accumulated_glp,
        premium_td=policy.premiums_paid_to_date,
        total_withdrawals=policy.withdrawals_to_date,
        fetch_table=lambda _: [{
            "ENTRY_DT": "2026-03-01", "TRN_TYP_CD": "PR",
            "GROSS_AMT": 300.0, "NET_AMT": 271.5,
        }],
    )
    result = gea.project_guideline_exception_target_forecast(source, date(2027, 1, 15))
    for scenario in (result, result.zero_glp, result.no_forceout):
        opening = scenario.rows[0].state
        assert opening.av_after_deduction == 4494.38
        assert opening.premiums_to_date == policy.premiums_paid_to_date
        assert opening.interest_credited == pytest.approx(14.71, abs=0.005)
        assert opening.av_end_of_month == pytest.approx(4509.09, abs=0.005)
        assert scenario.rows[1].state.av_after_premium == pytest.approx(opening.av_end_of_month)
        assert all(r.premium == 0.0 for r in scenario.rows)


def test_target_month_deduction_is_not_projected(forecast):
    _, _, _, run = forecast
    result = run()
    assert result.rows[-1].date == date(2026, 12, 15)
    assert len(result.rows) == 11  # valuation snapshot + ten deductions


def test_regular_premium_funds_positive_surrender_value(forecast):
    policy, _, _, run = forecast
    policy.account_value = 1_000.0
    result = run()
    assert result.premium > 0.0
    assert result.rows[-1].account_value > 0.0
    assert all(row.account_value > 0.0 for row in result.rows)
    assert result.zero_glp.premium == result.premium
    assert result.no_forceout.premium == result.premium
    assert result.no_forceout.rows == result.rows
    for row in result.no_forceout.rows[1:]:
        assert row.state.applied_scheduled_premium == pytest.approx(result.no_forceout.premium)
        assert row.surrender_value > 0
        assert not row.state.lapsed


def test_surrender_charge_is_not_treated_as_available_cash(forecast):
    policy, config, rates, run = forecast
    policy.account_value = 1_000.0
    config.lapse_value = "AV"  # AV-based protection is insufficient for this solve.
    rates.scr = [0.0, 5.0]  # 100 units: $500 surrender charge
    result = run()
    assert result.rows[-1].surrender_value > 0.0
    assert result.rows[-1].account_value > 500.0
    assert result.zero_glp.premium == result.premium


def test_no_target_deduction_even_when_it_would_cause_lapse(forecast):
    policy, _, _, run = forecast
    policy.account_value = 300.0  # covers March's charge, not April's
    result = run(date(2026, 4, 15))
    assert result.premium == 0.0
    assert result.rows[-1].date == date(2026, 3, 15)
    assert result.rows[-1].surrender_value > 0.0
    later = run(date(2026, 4, 16))
    assert later.premium > 0
    assert later.rows[-1].date == date(2026, 4, 15)
    assert later.rows[-1].surrender_value > 0.0


def test_month_end_target_uses_policy_monthliversary(forecast):
    policy, _, _, run = forecast
    policy.issue_date = date(1984, 1, 31)
    policy.valuation_date = date(2026, 2, 28)
    result = run(date(2026, 3, 30))
    assert result.premium == 0.0
    assert len(result.rows) == 1  # next deduction is March 31, not March 28


def test_exception_on_target_does_not_trigger_adjustment(forecast):
    policy, _, _, run = forecast
    policy.account_value = 300.0
    policy.accumulated_glp = policy.gsp = policy.premiums_paid_to_date = 1_000.0
    policy.withdrawals_to_date = 0.0
    result = run(date(2026, 4, 15))
    assert result.premium == 0.0
    assert result.zero_glp.exception_start is None
    assert not any(row.exception_premium for row in result.rows)


def test_exception_premiums_and_adjustment_exclude_target(forecast):
    policy, _, _, run = forecast
    policy.account_value = 100.0
    policy.accumulated_glp = policy.gsp = policy.premiums_paid_to_date = 1_000.0
    policy.withdrawals_to_date = 0.0
    result = run()
    assert result.exception_before_target
    summary = result.zero_glp.summary
    rows = result.zero_glp.rows
    assert all(row.date < date(2027, 1, 15) for row in rows)
    assert summary.total_premium_needed == pytest.approx(sum(r.premium for r in rows))
    assert summary.adjustment_to_accum_glp > 0
    assert summary.new_accum_glp == pytest.approx(
        summary.premiums_to_date_on_target - summary.accumulated_withdrawals)
    assert all(row.glp == 0 for row in rows)


def test_adjustment_uses_zero_glp_without_changing_source(forecast):
    policy, _, _, run = forecast
    policy.account_value = 100.0
    policy.accumulated_glp = policy.gsp = policy.premiums_paid_to_date = 1_000.0
    policy.withdrawals_to_date = 0.0
    policy.glp = 12.0
    result = run(date(2027, 2, 15))  # includes a policy anniversary
    assert result.current_glp == policy.glp == 12.0
    assert all(row.glp == 0 for row in result.zero_glp.rows)
    s = result.zero_glp.summary
    assert s.adjustment_to_accum_glp == pytest.approx(
        max(0, s.premiums_to_date_on_target - s.accumulated_withdrawals - s.accumulated_glp))


@pytest.mark.parametrize("excess", [0.0, 100.0])
def test_independent_glp_zero_solve_crosses_anniversary_with_enforcement(
    forecast, monkeypatch, excess,
):
    policy, _, _, run = forecast
    policy.valuation_date = date(2026, 12, 15)
    policy.duration = 516
    policy.policy_month = 12
    policy.account_value = 100.0
    policy.glp = policy.accumulated_glp = policy.gsp = 1_000.0
    policy.premiums_paid_to_date = 1_000.0 + excess
    policy.withdrawals_to_date = 0.0
    original = copy.deepcopy(policy)
    options_seen = []
    project = calc_engine.IllustrationEngine.project

    def checked_project(engine, projected_policy, **kwargs):
        options_seen.append(kwargs["options"])
        assert kwargs["months"] == 2
        return project(engine, projected_policy, **kwargs)

    monkeypatch.setattr(calc_engine.IllustrationEngine, "project", checked_project)
    result = run(date(2027, 3, 15))
    assert policy == original
    assert result.premium > result.zero_glp.premium == 0.0
    assert result.exception_before_target
    assert result.zero_glp.exception_start == date(2027, 1, 15)
    # The engine accumulates the rounded monthly GLP (83.33 × 12).
    assert result.rows[-1].accumulated_glp == pytest.approx(1_999.96)
    assert all(row.accumulated_glp == 1_000.0 for row in result.zero_glp.rows)
    assert result.rows[-1].exception_premium > 0
    assert result.zero_glp.rows[-1].exception_premium > 0
    assert result.zero_glp.rows[-1].surrender_value == 0
    assert sum(row.force_out for row in result.zero_glp.rows) == pytest.approx(excess)
    assert all(row.force_out == 0 and row.glp == 0 for row in result.no_forceout.rows)
    assert result.no_forceout.exception_start is not None
    assert result.no_forceout.rows[-1].exception_premium > 0
    assert result.no_forceout.rows[-1].surrender_value == 0
    for scenario in (result, result.zero_glp, result.no_forceout):
        assert scenario.rows[-1].date == date(2027, 2, 15)
        assert not any(row.state.lapsed for row in scenario.rows)
    assert options_seen
    assert all(option.conform_to_tefra and option.conform_to_tamra
               and option.guideline_cap_enabled and option.tamra_cap_enabled
               and option.allow_exception_prems
               and not option.billable_to_md_windows for option in options_seen)
    assert {option.force_out_enabled for option in options_seen} == {True, False}


@pytest.mark.parametrize("timing", list(calc_engine.ProjectionTiming))
@pytest.mark.parametrize("forceouts", [True, False])
def test_forceout_switch_preserves_acceptance_caps_and_exception_rescue(forecast, timing, forceouts):
    from suiteview.illustration.models.input_set import (
        IllustrationInputSet, IllustrationOptions, ScheduledTransaction, TransactionKind,
    )

    policy, _, _, _ = forecast
    policy.glp = 12.0  # A future exception, not a policy already in its exception period.
    policy.account_value = 100.0
    policy.accumulated_glp = policy.gsp = 1_000.0
    policy.premiums_paid_to_date = 1_100.0
    policy.withdrawals_to_date = 0.0
    original = copy.deepcopy(policy)
    options = gea.level_to_exception_options(IllustrationOptions(guideline_forceouts=forceouts))
    states = calc_engine.IllustrationEngine().project(
        copy.deepcopy(policy), months=2, options=options, timing=timing,
        future_inputs=IllustrationInputSet(scheduled_transactions=[
            ScheduledTransaction(
                kind=TransactionKind.PREMIUM, policy_year=policy.policy_year,
                amount=5_000.0, mode="M"),
        ]))
    assert policy == original
    assert sum(s.guideline_forceout for s in states) == pytest.approx(100 if forceouts else 0)
    assert all(s.gross_premium == 0 for s in states)  # Requested $5,000 is not admitted.
    assert any(s.gp_exception_prem > 0 for s in states)
    assert not any(s.lapsed for s in states)


def test_no_forceout_still_enforces_tamra_acceptance(forecast):
    from suiteview.illustration.models.input_set import (
        IllustrationInputSet, IllustrationOptions, ScheduledTransaction, TransactionKind,
    )

    policy, _, _, _ = forecast
    policy.tamra_7pay_start_date = policy.valuation_date
    policy.tamra_7pay_level = 100.0
    policy.tamra_7year_contributions = [100.0] + [0.0] * 6
    future = IllustrationInputSet(scheduled_transactions=[
        ScheduledTransaction(kind=TransactionKind.PREMIUM, policy_year=policy.policy_year,
                             amount=5_000.0, mode="M"),
    ])
    projections = [
        calc_engine.IllustrationEngine().project(
            copy.deepcopy(policy), months=2, future_inputs=future,
            options=gea.level_to_exception_options(IllustrationOptions(guideline_forceouts=enabled)))
        for enabled in (True, False)
    ]
    assert projections[0] == projections[1]
    assert all(s.gross_premium == 0 for s in projections[1])


def test_shared_ledger_matches_rerun_and_keeps_cashflows_distinct(forecast, monkeypatch):
    from PyQt6.QtWidgets import QApplication
    from suiteview.illustration.models.calc_state import MonthlyState
    from suiteview.illustration.ui.values_overview import LEDGER_COLUMNS, ValuesOverview
    from suiteview.polview.ui.tabs.policy_support_tab import PolicySupportTab

    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    global _QT_APP
    _QT_APP = app = QApplication.instance() or QApplication([])
    policy, _, _, _ = forecast
    initial = MonthlyState(
        date=date(2026, 2, 15), policy_year=43, policy_month=2,
        attained_age=72, withdrawals_to_date=100)
    state = MonthlyState(
        date=date(2026, 3, 15), policy_year=43, policy_month=3, attained_age=72,
        withdrawals_to_date=160, guideline_forceout=10,
        gross_premium=75, gp_exception_prem=25,
        applied_loan_repayment=30, applied_regular_loan=40,
        total_deduction=20, av_after_exception=1000, interest_credited=5,
        av_end_of_month=1005, policy_debt=200, surrender_charge=100,
        ending_sv=705, shadow_eav=90, ending_db=100_000,
        glp=20, gsp=2000, guideline_limit=2100,
        premiums_to_date_after_exception=3000, exception_prem_mode=True, is_mec=True)
    overview = ValuesOverview()
    tab = PolicySupportTab()
    try:
        overview.display(policy, [initial, state])
        tab._display_glp_forecast_rows(
            tab._glp_target_table, [gea._forecast_row(initial), gea._forecast_row(state)])
        rerun = overview.ledger.topLevelItem(0).child(0)
        displayed = [tab._glp_target_table.item(1, i).text() for i in range(len(LEDGER_COLUMNS))]
        assert displayed == [rerun.text(i) for i in range(len(LEDGER_COLUMNS))]
        cells = dict(zip(LEDGER_COLUMNS, displayed))
        assert cells["Prem"] == "75.00"
        assert cells["Exception Prem"] == "25.00"
        assert cells["Contributions"] == "130.00"
        assert cells["Withdrawals"] == "50.00"
        assert cells["Distributions"] == "100.00"
        assert cells["AV"] == "1,000.00"
        assert cells["SV"] == "700.00"
        assert cells["EAV"] == "1,005.00"
        assert cells["ESV"] == "705.00"
        assert cells["SubjectPayments"] == "2,840.00"
        assert "MEC" in cells["Status"]
        assert cells["Age"] == "72" and cells["Age EOY"] == "73"
    finally:
        overview.close()
        tab.close()
        overview.deleteLater()
        tab.deleteLater()
        app.processEvents()


def test_calculate_renders_and_exports_zero_after_exception_quote(forecast, monkeypatch):
    from PyQt6.QtWidgets import QApplication
    from suiteview.polview.ui.tabs.policy_support_tab import PolicySupportTab
    from suiteview.illustration.ui.values_overview import LEDGER_COLUMNS, monthly_ledger_cells

    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    global _QT_APP
    _QT_APP = app = QApplication.instance() or QApplication([])
    policy, _, _, _ = forecast
    tab = PolicySupportTab()
    tab._glp_target_date.setText("01/15/2027")
    try:
        policy.account_value = 100.0
        policy.accumulated_glp = policy.gsp = policy.premiums_paid_to_date = 1_000.0
        policy.withdrawals_to_date = 0.0
        tab._policy = SimpleNamespace(
            policy_number="GLPTEST", company_code="01",
            accumulated_glp_target=1_000.0, premium_td=1_000.0,
            total_withdrawals=0.0, fetch_table=lambda _: [],
        )
        tab._on_calculate_glp_exception()
        assert tab._glp_zero_glp_table.rowCount() > 0
        assert tab._glp_no_forceout_table.rowCount() > 0
        assert "Accum GLP Increase" in tab._glp_summary_copy_text()

        policy.account_value = 4_780.24
        tab._on_calculate_glp_exception()
        table = tab._glp_target_table
        assert table.rowCount() == 11
        assert all(table.item(i, LEDGER_COLUMNS.index("Prem")).text() == "0.00" for i in range(11))
        assert table.item(10, LEDGER_COLUMNS.index("Date")).text() == "12/15/2026"
        assert float(table.item(10, LEDGER_COLUMNS.index("ESV")).text().replace(",", "")) > 0
        assert table.item(10, LEDGER_COLUMNS.index("ESV")).font().bold()
        assert tab._glp_zero_glp_table.rowCount() == 11
        assert tab._glp_no_forceout_table.rowCount() == 11
        assert [tab._glp_forecast_tabs.tabText(i) for i in range(3)] == [
            "Min Prem To Target", "Min Prem To Target (GLP=0)",
            "Min Prem to Target (no forceout)"]
        for display, scenario in ((table, tab._glp_result),
                                  (tab._glp_zero_glp_table, tab._glp_result.zero_glp),
                                  (tab._glp_no_forceout_table, tab._glp_result.no_forceout)):
            assert [display._data_table.horizontalHeaderItem(i).text()
                    for i in range(display.columnCount())] == LEDGER_COLUMNS
            previous_wd = scenario.rows[0].state.withdrawals_to_date
            for i, row in enumerate(scenario.rows):
                assert [display.item(i, j).text() for j in range(display.columnCount())] == (
                    monthly_ledger_cells(row.state, previous_wd))
                previous_wd = row.state.withdrawals_to_date
        assert "DO NOT ADJUST" in tab._glp_summary_copy_text()
        wb = tab._build_glp_quote_workbook()
        try:
            rows = list(wb.active.values)
            forecast_rows = [r for r in rows if r[4] in ("03/15/2026", "12/15/2026")]
            assert len(forecast_rows) == 6
            assert all(r[LEDGER_COLUMNS.index("Prem")] == "0.00" for r in forecast_rows)
            assert not any("0 - MD Prem" in str(r[0]) for r in rows)
            assert sum(list(r) == LEDGER_COLUMNS for r in rows) == 3
            assert any("Min Prem to Target (no forceout)" in str(r[0]) for r in rows)
        finally:
            wb.close()

        # A zero-GLP exception need must not override the original's no-adjust outcome.
        policy.valuation_date = date(2026, 12, 15)
        policy.duration = 516
        policy.policy_month = 12
        policy.account_value = 100.0
        policy.glp = 12_000.0
        tab._glp_target_date.setText("03/15/2027")
        tab._on_calculate_glp_exception()
        assert not tab._glp_result.exception_before_target
        assert tab._glp_result.zero_glp.exception_start is not None
        assert "DO NOT ADJUST" in tab._glp_summary_copy_text()
        assert tab._glp_zero_glp_table.rowCount() == 3
        assert tab._glp_no_forceout_table.rowCount() == 3
        assert tab._glp_forecast_tabs.count() == 3
        summary = tab._glp_summary_copy_text()
        tab._glp_forecast_tabs.setCurrentIndex(2)
        assert tab._glp_summary_copy_text() == summary
        tip = tab._glp_forecast_tabs.tabToolTip(2)
        assert "GLP=0; no forceout" in tip and "comparison only" in tip
        wb = tab._build_glp_quote_workbook()
        try:
            assert any("DO NOT ADJUST" in str(row[0]) for row in wb.active.values)
            assert sum(list(row) == LEDGER_COLUMNS for row in wb.active.values) == 3
        finally:
            wb.close()
        tab._glp_target_date.setText("01/15/2020")
        tab._on_calculate_glp_exception()
        for display in (tab._glp_target_table, tab._glp_zero_glp_table, tab._glp_no_forceout_table):
            assert display.rowCount() == 0
            assert not tab._glp_forecast_tabs.tabToolTip(tab._glp_forecast_tabs.indexOf(display))
        assert tab._glp_result is None
        assert not tab._glp_export_btn.isEnabled()
    finally:
        tab.close()
        tab.deleteLater()
        app.processEvents()
