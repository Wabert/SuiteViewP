"""GEP v2 premium-schedule projections using the real compiler, solver and engine."""
from datetime import date
from types import SimpleNamespace

import pytest

from suiteview.illustration.core import calc_engine
from suiteview.illustration.core.bonus_rates import BonusConfig
from suiteview.illustration.core.rate_loader import IllustrationRates
from suiteview.illustration.models.plancode_config import PlancodeConfig
from suiteview.illustration.models.policy_data import CoverageSegment, IllustrationPolicyData
from suiteview.polview.services import gep_v2
from suiteview.polview.services import guideline_exception_adjustment as gea
from suiteview.polview.services.glp_exception import GlpForecastAvailability


@pytest.fixture
def quote(monkeypatch):
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
        plancode="GLPTEST", dbd=0.0, gint=0.0, prem_flat_load=0.0, lapse_value="SV")
    rates = IllustrationRates(coi=[0.0, 2.7], segment_coi={1: [0.0, 2.7]})
    monkeypatch.setattr(calc_engine, "load_plancode", lambda _p: config)
    monkeypatch.setattr(calc_engine, "load_bonus_config", lambda *_: BonusConfig())
    monkeypatch.setattr(calc_engine.IllustrationEngine, "_load_rates", lambda *_: rates)
    monkeypatch.setattr(gea, "check_forecast_availability",
                        lambda _: GlpForecastAvailability(True, "test", policy, rates, config))

    def run(target=date(2027, 1, 15), quote_date=None, premiums=()):
        return gep_v2.project_gep_v2(
            source(policy, premiums), target, quote_date=quote_date or policy.valuation_date)

    return policy, config, rates, run


def source(policy, premiums=()):
    return SimpleNamespace(
        policy_number="GLPTEST", company_code="01",
        accumulated_glp_target=policy.accumulated_glp,
        premium_td=policy.premiums_paid_to_date,
        total_withdrawals=policy.withdrawals_to_date,
        get_premium_transactions=lambda: list(premiums),
    )


def _premium(when, gross, net):
    return SimpleNamespace(trans_date=when, trans_code="PR", gross_amount=gross, net_amount=net)


def _two_anniversary_policy(policy):
    """AV runs out; GLP $1,200/yr; $100 of room left in the current year."""
    policy.account_value = 100.0
    policy.glp = 1_200.0
    policy.accumulated_glp = policy.gsp = 1_000.0
    policy.premiums_paid_to_date = 900.0
    policy.withdrawals_to_date = 0.0


def test_no_premium_before_target_and_target_month_is_projected(quote):
    _, _, _, run = quote
    result = run()
    assert result.premium_dates == (date(2027, 1, 15),)
    assert result.premium_date == date(2027, 1, 15)
    for scenario in result.scenarios:
        states = scenario.states
        assert states[0].date == date(2026, 2, 15)
        assert states[-1].date == date(2027, 1, 15)
        assert len(states) == 12  # valuation snapshot + 3/15 .. 1/15
        # The 300 billed premium never reappears before the target.
        assert all(s.gross_premium == 0 for s in states[:-1])
        assert not any(s.lapsed for s in states)
        assert [p.date for p in scenario.payments] == [date(2027, 1, 15)]


def test_healthy_policy_needs_no_minimum_and_max_pays_gpt_room(quote):
    policy, _, _, run = quote
    result = run()
    room = policy.accumulated_glp - (policy.premiums_paid_to_date - policy.withdrawals_to_date)
    (maximum,) = result.max_premium.payments
    (minimum,) = result.min_premium_no_outs.payments
    assert maximum.requested_premium == maximum.applied_premium == pytest.approx(room)
    assert result.max_premium.total_premium == pytest.approx(room)
    assert minimum.requested_premium == minimum.applied_premium == 0.0
    assert result.min_premium_no_outs.total_premium == 0.0
    assert result.min_premium_forceouts.total_premium == 0.0
    assert all(scenario.in_force for scenario in result.scenarios)
    assert maximum.av_before_md == pytest.approx(
        maximum.av_entering + maximum.state.net_premium)
    assert maximum.av_before_md == pytest.approx(
        minimum.av_before_md + maximum.state.net_premium)
    assert result.gep_exception_no_outs == 0.0
    assert result.gep_exception_forceouts == 0.0


def test_account_value_runs_negative_and_minimum_restores_zero(quote):
    policy, _, _, run = quote
    policy.account_value = 100.0
    result = run()
    (minimum,) = result.min_premium_no_outs.payments
    assert any(s.av_end_of_month < 0 for s in result.min_premium_no_outs.states[:-1])
    assert not any(s.lapsed for s in result.min_premium_no_outs.states)
    assert minimum.requested_premium > 0
    assert minimum.applied_premium == minimum.requested_premium
    assert 0.0 <= minimum.av_before_md < 0.01
    assert minimum.in_force and minimum.shortfall == 0.0
    # One cent less leaves the target-date AV negative.
    basis = gea.prepare_target_projection(source(policy), date(2027, 1, 15), policy.valuation_date)
    runner = gep_v2._ScenarioRunner(basis)
    options = gep_v2._min_options(basis, forceouts=False)
    states = runner.project(options, {minimum.date: minimum.requested_premium - 0.01})
    assert states[-1].guideline_av_before_monthly_deduction < 0


def test_minimum_over_maximum_is_the_gep_exception_required(quote):
    policy, _, _, run = quote
    policy.account_value = 100.0
    policy.accumulated_glp = policy.gsp = policy.premiums_paid_to_date = 1_000.0
    policy.withdrawals_to_date = 0.0
    result = run()
    (maximum,) = result.max_premium.payments
    assert maximum.requested_premium == maximum.applied_premium == 0.0
    assert not result.max_premium.in_force
    assert result.max_premium.first_failure is maximum
    assert maximum.shortfall == pytest.approx(-maximum.av_before_md)
    (minimum,) = result.min_premium_no_outs.payments
    assert minimum.requested_premium == pytest.approx(maximum.shortfall, abs=0.01)
    assert minimum.applied_premium == minimum.requested_premium
    assert result.min_premium_no_outs.in_force
    assert all(s.guideline_forceout == 0 for s in result.min_premium_no_outs.states)
    assert result.gep_exception_no_outs == pytest.approx(minimum.applied_premium)
    # Nothing is over the limit, so forceouts change nothing.
    assert result.min_premium_forceouts.total_premium == pytest.approx(
        result.min_premium_no_outs.total_premium)
    assert result.gep_exception_forceouts == result.gep_exception_no_outs


@pytest.mark.parametrize("valuation_month", [11, 12])
def test_target_anniversary_uses_the_ending_years_limit(quote, valuation_month):
    policy, _, _, run = quote
    policy.valuation_date = date(2026, valuation_month, 15)
    policy.duration = 504 + valuation_month
    policy.policy_month = valuation_month
    policy.account_value = 2_000.0
    policy.glp = policy.accumulated_glp = policy.gsp = 1_000.0
    policy.premiums_paid_to_date = 900.0
    policy.withdrawals_to_date = 0.0
    result = run(date(2027, 1, 15))  # the target is the policy anniversary
    (payment,) = result.max_premium.payments
    assert payment.state.is_anniversary
    # The engine still accrues the new year's GLP (83.33 x 12) on the anniversary,
    # but the premium arrives just before it, under the ending year's limit.
    assert payment.state.accumulated_glp == pytest.approx(1_999.96)
    assert payment.guideline_limit == 1_000.0
    assert payment.premiums_less_withdrawals == 900.0
    assert payment.requested_premium == payment.applied_premium == 100.0


def test_two_anniversaries_pay_two_premiums_figured_the_same_way(quote):
    policy, _, _, run = quote
    _two_anniversary_policy(policy)
    result = run(date(2028, 1, 15))
    assert result.premium_dates == (date(2027, 1, 15), date(2028, 1, 15))
    for scenario in result.scenarios:
        assert [p.date for p in scenario.payments] == list(result.premium_dates)
        paid = {s.date for s in scenario.states if s.gross_premium > 0}
        assert paid <= set(result.premium_dates)
        assert not any(s.lapsed for s in scenario.states)

    first, second = result.max_premium.payments
    # Each premium uses the limit just before its own anniversary: the first is
    # the current year's remaining room, the second the GLP the first added.
    assert first.guideline_limit == 1_000.0
    assert first.premiums_less_withdrawals == 900.0
    assert first.applied_premium == 100.0
    assert second.guideline_limit == pytest.approx(2_200.0)
    assert second.premiums_less_withdrawals == pytest.approx(1_000.0)
    assert second.applied_premium == pytest.approx(1_200.0)
    assert result.max_premium.total_premium == pytest.approx(1_300.0)
    assert result.max_premium.first_failure is first

    first, second = result.min_premium_no_outs.payments
    for payment in (first, second):
        assert payment.applied_premium > 0
        assert 0.0 <= payment.av_before_md < 0.01
    assert result.min_premium_no_outs.in_force
    assert result.min_premium_no_outs.total_premium == pytest.approx(
        first.applied_premium + second.applied_premium)
    # The second premium is the minimum given the first: one cent less fails.
    basis = gea.prepare_target_projection(source(policy), date(2028, 1, 15), policy.valuation_date)
    runner = gep_v2._ScenarioRunner(basis)
    options = gep_v2._min_options(basis, forceouts=False)
    states = runner.project(options, {
        first.date: first.requested_premium, second.date: second.requested_premium - 0.01})
    assert states[-1].guideline_av_before_monthly_deduction < 0
    assert result.gep_exception_no_outs == pytest.approx(
        result.min_premium_no_outs.total_premium - 1_300.0)


def test_non_anniversary_target_adds_a_final_premium(quote):
    policy, _, _, run = quote
    _two_anniversary_policy(policy)
    result = run(date(2027, 6, 1))
    assert result.premium_dates == (date(2027, 1, 15), date(2027, 6, 15))
    (_, last) = result.max_premium.payments
    # No anniversary in between, so the room left is the GLP added on 01/15/2027.
    assert last.guideline_limit == pytest.approx(2_200.0)
    assert last.applied_premium == pytest.approx(1_200.0)


def test_max_forces_out_premium_over_the_limit(quote):
    policy, _, _, run = quote
    policy.account_value = 2_000.0
    policy.accumulated_glp = policy.gsp = 1_000.0
    policy.premiums_paid_to_date = 1_100.0  # 100 over the guideline limit
    policy.withdrawals_to_date = 0.0
    result = run(date(2026, 4, 15))
    assert sum(s.guideline_forceout for s in result.max_premium.states) == pytest.approx(100.0)
    assert result.max_premium.total_premium == 0.0
    assert sum(
        s.guideline_forceout for s in result.min_premium_forceouts.states) == pytest.approx(100.0)
    assert all(s.guideline_forceout == 0 for s in result.min_premium_no_outs.states)


def test_min_with_forceouts_overdraws_av_and_pays_the_forceout_back(quote):
    policy, _, _, run = quote
    policy.account_value = 100.0
    policy.accumulated_glp = policy.gsp = 1_000.0
    policy.premiums_paid_to_date = 1_500.0  # 500 over the limit, only 100 of AV
    policy.withdrawals_to_date = 0.0
    result = run()
    forced = result.min_premium_forceouts
    # The full 500 comes out in the first projected month though only 100 is there.
    first = forced.states[1]
    assert first.guideline_forceout == pytest.approx(500.0)
    assert first.withdrawals_to_date == pytest.approx(500.0)
    assert first.guideline_av_before_monthly_deduction == pytest.approx(-400.0)
    assert sum(s.guideline_forceout for s in forced.states) == pytest.approx(500.0)
    # The AV-capped Max run only manages the 100 there is.
    assert result.max_premium.states[1].guideline_forceout == pytest.approx(100.0)
    (with_outs,) = forced.payments
    (no_outs,) = result.min_premium_no_outs.payments
    assert with_outs.in_force and 0.0 <= with_outs.av_before_md < 0.01
    assert with_outs.applied_premium > no_outs.applied_premium + 499.99
    assert result.gep_exception_forceouts == pytest.approx(with_outs.applied_premium)
    assert result.gep_exception_no_outs == pytest.approx(no_outs.applied_premium)


def test_min_with_forceouts_never_forces_out_its_own_premiums(quote):
    """A negative GLP shrinks AccumGLP at each anniversary; only that is forced out."""
    policy, _, _, run = quote
    policy.account_value = 100.0
    policy.glp = -240.0
    policy.gsp = 500.0
    policy.accumulated_glp = policy.premiums_paid_to_date = 1_000.0
    policy.withdrawals_to_date = 0.0
    result = run(date(2028, 1, 15))
    assert result.premium_dates == (date(2027, 1, 15), date(2028, 1, 15))
    assert result.max_premium.total_premium == 0.0
    forced = result.min_premium_forceouts
    outs = {s.date: s.guideline_forceout for s in forced.states if s.guideline_forceout}
    assert outs == {date(2027, 1, 15): pytest.approx(240.0), date(2028, 1, 15): pytest.approx(240.0)}
    assert all(s.guideline_forceout == 0 for s in result.min_premium_no_outs.states)
    assert forced.in_force
    # Each premium covers exactly that anniversary's forceout on top of the
    # no-forceout minimum (no loads, no interest in this fixture).
    for with_outs, no_outs in zip(forced.payments, result.min_premium_no_outs.payments):
        assert with_outs.applied_premium == pytest.approx(no_outs.applied_premium + 240.0, abs=0.02)
    assert result.gep_exception_forceouts == pytest.approx(
        result.gep_exception_no_outs + 480.0, abs=0.04)
    assert forced.total_forceouts == pytest.approx(480.0)
    assert result.min_premium_no_outs.total_forceouts == 0.0
    assert result.current_accum_glp == 1_000.0
    assert result.new_accum_glp == pytest.approx(1_000.0 + result.gep_exception_forceouts)


def test_interim_quote_opens_on_quote_date(quote):
    policy, config, _, run = quote
    policy.current_interest_rate = 0.04
    config.interest_method = "ExactDays"
    quote_date = date(2026, 2, 25)
    result = run(quote_date=quote_date, premiums=[_premium(date(2026, 2, 20), 300.0, 271.5)])
    assert result.interim is not None and result.interim.gross_premium == 300.0
    for scenario in result.scenarios:
        assert scenario.states[0].date == quote_date
        assert scenario.states[0].premiums_to_date == policy.premiums_paid_to_date + 300.0
    assert result.max_premium.total_premium == pytest.approx(
        policy.accumulated_glp - (policy.premiums_paid_to_date + 300.0
                                  - policy.withdrawals_to_date))


def test_mid_month_target_pays_on_next_monthliversary(quote):
    _, _, _, run = quote
    result = run(date(2026, 6, 1))
    assert result.premium_date == date(2026, 6, 15)
    assert result.max_premium.states[-1].date == date(2026, 6, 15)


def test_target_on_or_before_valuation_is_rejected(quote):
    _, _, _, run = quote
    with pytest.raises(ValueError, match="after the current valuation date"):
        run(date(2026, 2, 15))


_QT_APP = None


@pytest.fixture
def qt_app(monkeypatch):
    from PyQt6.QtWidgets import QApplication

    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    # Keep the application alive for the session: collecting it deletes Qt
    # singletons that later tests in the same process still use.
    global _QT_APP
    _QT_APP = QApplication.instance() or QApplication([])
    return _QT_APP


def test_page_renders_projections_summary_and_export(quote, qt_app, monkeypatch):
    from suiteview.illustration.ui.values_overview import monthly_ledger_cells
    from suiteview.polview.ui.tabs import gep_v2_page as page_module

    policy, _, _, _ = quote
    _two_anniversary_policy(policy)
    monkeypatch.setattr(page_module.GepV2Page, "quote_date",
                        staticmethod(lambda: policy.valuation_date))
    monkeypatch.setattr(page_module, "is_glp_exception_eligible", lambda _p: True)
    monkeypatch.setattr(page_module, "check_forecast_availability",
                        lambda _p: GlpForecastAvailability(True, "Data for forecasting is available"))
    page = page_module.GepV2Page()
    try:
        loaded = source(policy)
        loaded.exists = True
        page.set_policy(loaded, cache_key=("CKPR", "I", "01", "GLPTEST"),
                        default_target_text="01/15/2028")
        page.refresh()
        assert page._target_date.text() == "01/15/2028"
        assert page._calculate_btn.isEnabled()
        page._on_calculate()
        result = page.result
        assert result is not None
        columns = page_module.GEP_V2_COLUMNS
        assert columns.index("AV bf MD") == columns.index("MD") - 1
        for table, scenario in zip(page._tables, result.scenarios):
            assert table.rowCount() == len(scenario.states) == 24
            for payment in scenario.payments:
                row = next(i for i, s in enumerate(scenario.states) if s.date == payment.date)
                assert table.item(row, columns.index("Date")).text() == f"{payment.date:%m/%d/%Y}"
                cell = table.item(row, columns.index("AV bf MD"))
                assert cell.text() == f"{payment.av_before_md:,.2f}"
                assert cell.font().bold()
            assert not table.item(1, columns.index("AV bf MD")).font().bold()
            shared = [table.item(1, j).text() for j in range(len(columns))]
            del shared[columns.index("AV bf MD")]
            assert shared == monthly_ledger_cells(
                scenario.states[1], scenario.states[0].withdrawals_to_date)
        # Min w Forceouts is the second tab; the no-forceout minimum is third.
        assert page._tabs.count() == 3
        assert page._tabs.tabText(0) == "Max Premium Projection ($1,300.00)"
        assert page._tabs.tabText(1) == (
            f"Min Prem w Forceouts (${result.min_premium_forceouts.total_premium:,.2f})")
        assert page._tabs.tabText(2) == (
            f"Min Prem No outs (${result.min_premium_no_outs.total_premium:,.2f})")

        # The summary: scenario lines on the left, GEP / AccumGLP / premium on the right.
        left, right = page_module.summary_blocks(result)
        assert [line.label for line in left] == list(page_module.SCENARIO_TABS)
        assert [[item.label for item in line.items] for line in (*left, *right)] == [
            list(items) for block in page_module._SUMMARY_LAYOUT for _, items in block]
        forced, no_outs = result.min_premium_forceouts, result.min_premium_no_outs
        assert page.summary_value("Max Premium Projection", "Prem") == "$1,300.00"
        assert page.summary_value("Max Premium Projection", "AV bf MD") == (
            page_module._money(result.max_premium.target_av_before_md))
        assert result.max_premium.target_av_before_md < 0  # Max fails at the target
        assert page.summary_value("Min Prem w Forceouts", "Prem") == (
            f"${forced.total_premium:,.2f}")
        assert page.summary_value("Min Prem w Forceouts", "Force outs") == "$0.00"
        assert page.summary_value("Min Prem No outs", "AV bf MD") in ("$0.00", "-$0.00")
        assert result.gep_exception_no_outs > 0
        assert page.summary_value("GEP Exception Required", "Without Forceouts") == (
            f"${result.gep_exception_no_outs:,.2f}")
        assert page.summary_value("GEP Exception Required", "With Forceouts") == (
            f"${result.gep_exception_forceouts:,.2f}")
        assert page.summary_value("AccumGLP", "Current") == "$1,000.00"
        assert result.new_accum_glp == pytest.approx(1_000.0 + result.gep_exception_forceouts)
        assert page.summary_value("AccumGLP", "New") == f"${result.new_accum_glp:,.2f}"
        assert page.summary_value("Premium to Target Date", "With Forceouts") == (
            f"${forced.total_premium:,.2f}")
        assert page.summary_value("Premium to Target Date", "Without Forceouts") == (
            f"${no_outs.total_premium:,.2f}")
        # Three lines tall: the two blocks sit side by side.
        assert page._summary.layout().rowCount() == 3
        rows = page_module.summary_rows(result)
        assert rows[0] == ["Max Premium Projection: Prem", "$1,300.00"]
        assert ["AccumGLP: New", f"${result.new_accum_glp:,.2f}"] in rows

        sheets = page.export_sheets()
        assert [name for name, _, _ in sheets] == [
            "GEP v2 Summary", "Max Premium", "Min Prem w Forceouts", "Min Prem No outs"]
        assert sheets[0][2][:len(rows)] == rows
        assert all(sheet[1] == columns and len(sheet[2]) == 24 for sheet in sheets[1:])
        assert page._export_btn.isEnabled()

        # A cached quote is restored when the page is shown again.
        page.set_policy(loaded, cache_key=("CKPR", "I", "01", "GLPTEST"),
                        default_target_text="01/15/2028")
        assert page.result is None
        page.refresh()
        assert page.result is result

        page._target_date.setText("01/15/2020")
        page._on_calculate()
        assert page.result is None
        assert all(table.rowCount() == 0 for table in page._tables)
        assert page._tabs.tabText(1) == "Min Prem w Forceouts"
        assert page.summary_value("Max Premium Projection", "Prem") == ""
        assert not page._export_btn.isEnabled()
        assert "after the current valuation date" in page._status_label.text()
    finally:
        page.close()
        page.deleteLater()
        qt_app.processEvents()


def test_summary_shows_not_required_when_the_limit_covers_the_minimum(quote):
    from suiteview.polview.ui.tabs import gep_v2_page as page_module

    _, _, _, run = quote
    result = run()
    left, right = page_module.summary_blocks(result)
    (gep, accum, premium) = right
    assert [(item.text, item.muted, item.alert) for item in gep.items] == [
        ("Not required", True, False), ("Not required", True, False)]
    current, new = accum.items
    assert current.text == new.text and not new.alert
    assert [item.text for item in premium.items] == ["$0.00", "$0.00"]


def test_policy_support_tab_exposes_gep_v2_section(qt_app):
    from suiteview.polview.ui.tabs.policy_support_tab import PolicySupportTab

    tab = PolicySupportTab()
    try:
        assert tab._btn_mode_gep_v2.text() == "GEP v2"
        tab._btn_mode_gep_v2.setEnabled(False)
        tab.open_section("gep_v2")  # ignored while unavailable
        assert tab._content_stack.currentWidget() is not tab._gep_v2_page
        tab._btn_mode_gep_v2.setEnabled(True)
        tab.open_section("gep_v2")
        assert tab._content_stack.currentWidget() is tab._gep_v2_page
        # The original GLP Exception tool is still its own section.
        assert tab._glp_exception_page is not tab._gep_v2_page
    finally:
        tab.close()
        tab.deleteLater()
        qt_app.processEvents()
