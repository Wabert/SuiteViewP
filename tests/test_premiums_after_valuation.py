"""Include Prem after Val date: post-valuation receipts join the starting values."""

import os
from copy import deepcopy
from dataclasses import replace
from datetime import date
from types import SimpleNamespace

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from suiteview.illustration.core.premiums_after_valuation import (
    account_value_with_receipts,
    capture_premiums_after_valuation,
    forecast_date,
    include_premiums_after_valuation,
    premiums_after_valuation_unavailable_reason,
    shadow_value_with_receipts,
)
from suiteview.illustration.core.rate_loader import IllustrationRates
from suiteview.illustration.core.scenario_builder import build_illustration_scenario
from suiteview.illustration.models.input_set import RollbackOverrideSet
from suiteview.illustration.models.plancode_config import PlancodeConfig
from suiteview.illustration.models.policy_data import (
    CoverageSegment,
    IllustrationPolicyData,
    PremiumAfterValuation,
)

VALUATION = date(2026, 9, 15)
RECEIVED = date(2026, 10, 4)


def _policy(**overrides):
    values = dict(
        policy_number="PAV001", company_code="01", plancode="1U145700",
        issue_date=date(2018, 1, 15), issue_age=54, attained_age=62,
        valuation_date=VALUATION, policy_year=9, policy_month=9, duration=105,
        face_amount=100_000.0, units=100.0, db_option="A",
        account_value=4_456.10, shadow_account_value=11_103.10,
        premiums_paid_to_date=19_115.25, premiums_ytd=900.0, cost_basis=19_115.25,
        tamra_7pay_start_date=date(2024, 1, 15),
        tamra_7year_contributions=[100.0, 200.0, 300.0, 0.0, 0.0, 0.0, 0.0],
        segments=[CoverageSegment(
            face_amount=100_000.0, original_face_amount=100_000.0, units=100.0,
            issue_date=date(2018, 1, 15), issue_age=54)],
        premiums_after_valuation=[PremiumAfterValuation(RECEIVED, 300.0, 225.0)],
    )
    values.update(overrides)
    return IllustrationPolicyData(**values)


def _shadow_basis(**config):
    rates = IllustrationRates(
        shadow_tpr=[None, 10.0], shadow_tpr_tbl1=[None, 0.0],
        shadow_tpp=[None, 0.05], shadow_epp=[None, 0.10])
    return PlancodeConfig(**config), rates


# ── capture ──────────────────────────────────────────────────────────

def _transaction(when, gross, net, processed="0", **row):
    return SimpleNamespace(
        trans_date=when, gross_amount=gross, net_amount=net, trans_code="PR",
        raw_data={"FBB3_PROCD_IND": processed, "FEB3_1035_EXCH_IND": "0", **row})


def _pi(*transactions, error=None):
    return SimpleNamespace(
        activity=SimpleNamespace(get_premium_transactions=lambda: list(transactions)),
        table_error=lambda table: error)


def test_capture_keeps_pending_receipts_after_the_valuation_date_only():
    premiums, error = capture_premiums_after_valuation(_pi(
        _transaction(VALUATION, 182.05, 136.54, processed="1"),
        _transaction(RECEIVED, 150, 138),
    ), _policy())
    assert error == ""
    assert premiums == [PremiumAfterValuation(RECEIVED, 150.0, 138.0, "PR")]


@pytest.mark.parametrize("transaction, message", [
    (_transaction(RECEIVED, 150, 138, processed="1"), "already processed"),
    (_transaction(RECEIVED, 150, 138, processed=""), "processing indicator"),
    (_transaction(RECEIVED, 150, None), "no net amount"),
    (_transaction(date(2026, 10, 15), 150, 138), "10/15/2026 monthliversary"),
    (_transaction(RECEIVED, 150, 138, FEB3_1035_EXCH_IND="1"), "1035 exchange"),
    (_transaction(RECEIVED, -150, -138), "negative"),
])
def test_capture_reports_why_receipts_cannot_be_included(transaction, message):
    premiums, error = capture_premiums_after_valuation(_pi(transaction), _policy())
    assert premiums == []
    assert message in error


def test_capture_surfaces_unavailable_financial_history():
    premiums, error = capture_premiums_after_valuation(_pi(error="SQL0204N"), _policy())
    assert premiums == [] and "FH_FIXED" in error and "SQL0204N" in error


# ── starting values ──────────────────────────────────────────────────

def test_receipts_add_gross_to_accumulators_and_keep_the_valuation_av():
    policy = _policy()
    include_premiums_after_valuation(policy)
    # The net is credited by the engine on the forecast date, not at valuation.
    assert policy.account_value == 4_456.10
    assert account_value_with_receipts(policy) == 4_681.10
    assert forecast_date(policy) == date(2026, 10, 15)
    assert policy.premiums_paid_to_date == 19_415.25
    assert policy.premiums_ytd == 1_200.0
    assert policy.cost_basis == 19_415.25
    assert policy.tamra_7year_contributions == [100.0, 200.0, 600.0, 0.0, 0.0, 0.0, 0.0]
    # No shadow account: no shadow net.
    assert policy.shadow_account_value == 11_103.10
    assert policy.premiums_after_valuation_shadow_net == 0.0
    assert policy.premiums_after_valuation_included
    with pytest.raises(ValueError, match="already included"):
        include_premiums_after_valuation(policy)


def test_shadow_takes_gross_less_shadow_load_against_prior_totals():
    # Target 100,000 / 1000 x 10 = 1,000; YTD 900 leaves 100 under target.
    policy = _policy(ccv_active=True)
    config, rates = _shadow_basis()
    include_premiums_after_valuation(policy, config=config, rates=rates)
    assert policy.premiums_after_valuation_shadow_net == 275.0  # 300 - 100 x 5% - 200 x 10%
    assert policy.shadow_account_value == 11_103.10
    assert shadow_value_with_receipts(policy) == 11_378.10


def test_shadow_load_at_an_anniversary_uses_the_new_years_totals():
    policy = _policy(ccv_active=True, policy_month=12, premiums_ytd=5_000.0)
    config, rates = _shadow_basis()
    include_premiums_after_valuation(policy, config=config, rates=rates)
    assert policy.premiums_after_valuation_shadow_net == 285.0  # all under the new target


def test_forgiveness_plans_load_in_the_receipt_month():
    policy = _policy(ccv_active=True, policy_month=12)
    config, rates = _shadow_basis(shadow_late_payment_forgiveness=True)
    include_premiums_after_valuation(policy, config=config, rates=rates)
    assert policy.premiums_after_valuation_shadow_net == 275.0


@pytest.mark.parametrize("overrides, message", [
    ({"premiums_after_valuation": []}, "No premiums were received after the 09/15/2026"),
    ({"premiums_after_valuation_error": "Premium is a 1035 exchange."}, "1035 exchange"),
    ({"rollback_date": date(2026, 8, 15)}, "loaded inforce valuation"),
])
def test_unavailable_reasons_are_explicit(overrides, message):
    policy = _policy(**overrides)
    assert message in premiums_after_valuation_unavailable_reason(policy)
    with pytest.raises(ValueError, match="cannot be included"):
        include_premiums_after_valuation(policy)


# ── scenario ─────────────────────────────────────────────────────────

def test_scenario_includes_receipts_on_a_copy_and_manual_av_is_a_valuation_amount():
    source = _policy()
    scenario = build_illustration_scenario(source, include_premiums_after_valuation=True)
    assert scenario.projectable_policy.premiums_after_valuation_included
    assert account_value_with_receipts(scenario.projectable_policy) == 4_681.10
    assert source.premiums_paid_to_date == 19_115.25 and not source.premiums_after_valuation_included
    edited = build_illustration_scenario(
        source, include_premiums_after_valuation=True,
        rollback_overrides=RollbackOverrideSet(valuation_date=VALUATION, account_value=5_000.0))
    assert edited.projectable_policy.account_value == 5_000.0
    assert account_value_with_receipts(edited.projectable_policy) == 5_225.0
    assert edited.projectable_policy.premiums_paid_to_date == 19_415.25


def test_scenario_refuses_historical_and_issue_bases():
    source = _policy()
    with pytest.raises(ValueError, match="loaded inforce valuation"):
        build_illustration_scenario(
            source, include_premiums_after_valuation=True,
            rollback_overrides=RollbackOverrideSet(valuation_date=date(2026, 8, 15)))
    with pytest.raises(ValueError, match="loaded inforce valuation"):
        build_illustration_scenario(source, include_premiums_after_valuation=True, run_from_issue=True)


def test_run_request_passes_the_option_to_the_scenario_builder():
    from suiteview.illustration.core.run_service import (
        EngineServices, PolicyBasis, PreparedPolicyData, RunControls, RunRequest,
        SolveRequestSet, build_run_scenario,
    )
    from suiteview.illustration.models.input_set import IllustrationInputSet, IllustrationOptions

    calls = []

    def builder(policy, **kwargs):
        calls.append(kwargs)
        return build_illustration_scenario(policy, **kwargs)

    request = RunRequest(
        basis=PolicyBasis("PAV001"), inputs=IllustrationInputSet(),
        controls=RunControls(IllustrationOptions(), 12, "for 1 year", True),
        solves=SolveRequestSet(), include_premiums_after_valuation=True)
    run = build_run_scenario(
        request, PreparedPolicyData(_policy()), replace(EngineServices(), scenario_builder=builder))
    assert calls[0]["include_premiums_after_valuation"] is True
    assert run.scenario.projectable_policy.premiums_after_valuation_included


@pytest.fixture
def engine_basis(monkeypatch):
    from suiteview.illustration.core import calc_engine
    from suiteview.illustration.core.bonus_rates import BonusConfig

    config = PlancodeConfig(plancode="GLPTEST", dbd=0.0, gint=0.0, prem_flat_load=0.0,
                            lapse_value="SV")
    rates = IllustrationRates(coi=[0.0, 0.0], segment_coi={1: [0.0, 0.0]})
    monkeypatch.setattr(calc_engine, "load_plancode", lambda _p: config)
    monkeypatch.setattr(calc_engine, "load_bonus_config", lambda *_: BonusConfig())
    monkeypatch.setattr(calc_engine.IllustrationEngine, "_load_rates", lambda *_: rates)
    return calc_engine


def _project(calc_engine, policy):
    from suiteview.illustration.models.input_set import IllustrationInputSet

    return calc_engine.IllustrationEngine().project(
        deepcopy(policy), months=2, future_inputs=IllustrationInputSet(), stop_on_lapse=False)


def test_engine_credits_the_net_on_the_forecast_date_without_valuation_month_interest(
        engine_basis):
    source = _policy(plancode="GLPTEST", current_interest_rate=0.04, modal_premium=0.0,
                     tamra_7pay_start_date=None, tamra_7year_contributions=[])
    included = build_illustration_scenario(
        source, include_premiums_after_valuation=True).projectable_policy
    on_valuation = deepcopy(source)
    on_valuation.account_value += 225.0

    base = _project(engine_basis, source)
    received = _project(engine_basis, included)
    at_valuation = _project(engine_basis, on_valuation)

    # The valuation month is untouched: no interest on the receipt before the forecast date.
    assert received[0].date == VALUATION
    assert received[0].av_end_of_month == base[0].av_end_of_month
    assert received[0].interest_credited == base[0].interest_credited
    assert received[0].premiums_to_date == base[0].premiums_to_date + 300.0
    assert received[1].date == date(2026, 10, 15)
    # From the forecast date it earns one month's interest, like a premium paid then...
    from_forecast = received[1].av_end_of_month - base[1].av_end_of_month
    assert 225.0 < from_forecast < 226.0
    # ...not the extra valuation-month interest of adding it at the valuation date.
    from_valuation = at_valuation[1].av_end_of_month - base[1].av_end_of_month
    assert from_valuation == pytest.approx(from_forecast * from_forecast / 225.0, rel=5e-4)
    assert from_valuation > from_forecast + 0.5
    # Credited once: later months grow by the same amount with no second credit.
    later = received[2].av_end_of_month - base[2].av_end_of_month
    assert from_forecast < later < from_forecast * 1.01


# ── outputs ──────────────────────────────────────────────────────────

def test_report_cover_discloses_the_added_receipts():
    from suiteview.illustration.core.report_builder import build_ul_report
    from suiteview.illustration.models.calc_state import MonthlyState

    policy = build_illustration_scenario(
        _policy(), include_premiums_after_valuation=True).projectable_policy
    report = build_ul_report(policy, [MonthlyState(date=VALUATION)])
    assert "$4,456.10 AS OF 09/15/2026. $225.00 OF NET PREMIUM RECEIVED AFTER THAT DATE " \
           "IS CREDITED ON 10/15/2026" in report.av_basis_line
    status = " ".join(report.policy_status_lines)
    assert "PREMIUMS OF $300.00 RECEIVED AFTER THE 09/15/2026 VALUATION DATE (10/04/2026)" in status
    assert ("$225.00 NET OF PREMIUM LOAD CREDITED TO THE ACCUMULATION VALUE ON 10/15/2026, "
            "WITH NO INTEREST BEFORE THAT DATE") in status
    assert any("ACTUAL PREMIUMS PAID:" in right and "$19,415.25" in right
               for _left, right in report.policy_block)
    assert any("PLUS LATER RECEIPTS" in right for _left, right in report.policy_block)

    plain = build_ul_report(_policy(), [MonthlyState(date=VALUATION)])
    assert "NET PREMIUM" not in plain.av_basis_line
    assert not any("RECEIVED AFTER" in line for line in plain.policy_status_lines)


def test_captured_receipts_round_trip_in_saved_case_snapshots():
    from suiteview.illustration.models.case_store import (
        decode_policy_snapshot, encode_policy_snapshot,
    )

    policy = _policy(premiums_after_valuation_error="")
    decoded = decode_policy_snapshot(encode_policy_snapshot(policy))
    assert decoded == policy
    assert decoded.premiums_after_valuation == [PremiumAfterValuation(RECEIVED, 300.0, 225.0)]


# ── window ───────────────────────────────────────────────────────────

_APP = None


@pytest.fixture
def app():
    from PyQt6.QtWidgets import QApplication

    global _APP
    _APP = QApplication.instance() or QApplication([])
    return _APP


@pytest.fixture
def window(app, monkeypatch):
    from PyQt6.QtCore import QCoreApplication, QEvent
    from PyQt6.QtWidgets import QMessageBox
    from suiteview.illustration.ui import main_window

    win = main_window.IllustrationWindow()
    win._test_warnings = []
    monkeypatch.setattr(QMessageBox, "warning", lambda *args: win._test_warnings.append(args[-1]))
    policy = _policy()
    win._illustration_data = policy
    win.policy_tab.load_data_from_snapshot(policy)
    win.inputs_tab.load_data_from_policy(policy)
    win._set_active_inputs_tab(win.inputs_tab)
    win._refresh_rollback_controls()
    yield win, policy
    win.close()
    win.deleteLater()
    QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)


def _shown(group, attr):
    return group.get_value(attr)


def test_checkbox_sits_on_the_tab_bar_and_updates_the_policy_tab(window):
    from PyQt6.QtCore import Qt

    win, source = window
    check = win.include_premiums_check
    assert win.tabs.cornerWidget(Qt.Corner.TopRightCorner).isAncestorOf(check)
    assert check.text() == "Include Prem after Val date"
    assert check.isEnabled() and not check.isChecked()
    assert "10/04/2026 PR $300.00 gross, $225.00 net" in check.toolTip()

    check.setChecked(True)
    assert win.inputs_tab.include_premiums_after_valuation_enabled()
    assert _shown(win.policy_tab.fund_values, "fund_account_value") == "$4,681.10"
    assert _shown(win.policy_tab.premium_values, "premium_td") == "$19,415.25"
    assert _shown(win.policy_tab.premium_values, "premium_ytd") == "$1,200.00"
    assert "INCLUDES PREMIUMS RECEIVED AFTER THE 09/15/2026 VALUATION DATE" in (
        win.policy_tab.snapshot_banner_text())
    assert "10/15/2026 forecast date" in win.policy_tab.snapshot_banner_text()
    assert "valuation date" in win.projection_mode_notice.text()
    assert "INCL PREMS AFTER VAL DATE" in win._title_label.text()
    assert source.account_value == 4_456.10

    draft = win.inputs_tab.read_draft()
    assert draft.include_premiums_after_valuation
    assert draft.case_inputs["include_premiums_after_valuation"] is True

    check.setChecked(False)
    assert _shown(win.policy_tab.fund_values, "fund_account_value") == "$4,456.10"
    assert win.policy_tab.snapshot_banner_text() is None


def test_saved_case_inputs_restore_the_choice(window):
    win, _source = window
    win.include_premiums_check.setChecked(True)
    state = deepcopy(win.inputs_tab.capture_case_inputs())
    win.include_premiums_check.setChecked(False)
    warnings = win.inputs_tab.apply_case_inputs(state)
    assert not any("Include Prem" in warning for warning in warnings)
    assert win.inputs_tab.include_premiums_after_valuation_enabled()
    assert win.include_premiums_check.isChecked()


def test_from_issue_turns_the_choice_off_and_greys_the_box(window):
    win, _source = window
    win.include_premiums_check.setChecked(True)
    win.inputs_tab.run_from_issue_btn.setChecked(True)
    if not win.inputs_tab.run_from_issue_enabled():
        pytest.skip("Policy fixture cannot enter From Issue mode.")
    assert not win.inputs_tab.include_premiums_after_valuation_enabled()
    assert not win.include_premiums_check.isChecked()
    assert not win.include_premiums_check.isEnabled()
    assert "Inforce mode only" in win.include_premiums_check.toolTip()


def test_unavailable_policy_keeps_the_box_visible_but_greyed(window):
    win, _source = window
    win._illustration_data = _policy(premiums_after_valuation=[])
    win._refresh_rollback_controls()
    assert not win.include_premiums_check.isEnabled()
    assert "No premiums were received" in win.include_premiums_check.toolTip()
