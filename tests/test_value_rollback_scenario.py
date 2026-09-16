"""Historical basis integration without live policy or rates access."""

import json
import os
from copy import deepcopy
from datetime import date

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PyQt6.QtWidgets import QApplication

from suiteview.illustration.core.scenario_builder import build_illustration_scenario
from suiteview.illustration.models.app_settings import get_illustration_settings
from suiteview.illustration.models.input_set import (
    DatedTransaction, IllustrationInputSet, InforceOverrideSet,
    RollbackOverrideSet, TransactionKind,
)
from suiteview.illustration.models.policy_data import (
    BenefitInfo, CoverageSegment, IllustrationPolicyData, RiderInfo,
    ValueRollbackSnapshot,
)
from suiteview.illustration.ui.inputs_tab import IllustrationInputsTab
from suiteview.illustration.ui.saved_case_scenario import build_spec_from_tab


ISSUE = date(2020, 5, 15)
LIVE = date(2026, 5, 15)
EARLIER = date(2026, 3, 15)


@pytest.fixture
def policy():
    return IllustrationPolicyData(
        policy_number="ROLLBACK", plancode="1U135D00",
        issue_date=ISSUE, issue_age=40, attained_age=46,
        valuation_date=LIVE, illustration_date=date(2026, 6, 1),
        policy_year=7, policy_month=1, duration=73, maturity_age=100,
        face_amount=150_000, units=125, db_option="A",
        account_value=25_000, regular_loan_principal=300,
        premiums_paid_to_date=40_000, accumulated_glp=100_000,
        cost_basis=38_000, accumulated_mtp=15_000,
        modal_premium=250, current_interest_rate=0.05,
        segments=[
            CoverageSegment(
                coverage_phase=1, issue_date=ISSUE, issue_age=40,
                face_amount=100_000, original_face_amount=100_000,
                units=100, vpu=1_000, coi_renewal_rate=99),
            CoverageSegment(
                coverage_phase=2, issue_date=ISSUE, issue_age=40,
                face_amount=50_000, original_face_amount=50_000,
                units=25, vpu=2_000),
        ],
        riders=[RiderInfo(
            coverage_phase=3, issue_date=ISSUE, plancode="RIDER",
            face_amount=10_000, units=10, vpu=1_000)],
        benefits=[BenefitInfo(
            coverage_phase=1, benefit_type="W", benefit_subtype="1",
            issue_date=ISSUE, benefit_amount=100_000, units=100, vpu=1_000)],
    )


@pytest.fixture
def historical(monkeypatch):
    from suiteview.illustration.core import value_rollback

    def apply(source, when, **kwargs):
        if when != EARLIER:
            raise ValueError("No reliable recorded rollback values on this date.")
        result = deepcopy(source)
        result.valuation_date = result.rollback_date = when
        result.rollback_source_date = source.valuation_date
        result.rollback_limitations = ["Current rate assumptions are retained."]
        result.policy_year, result.policy_month, result.duration = 6, 11, 71
        result.attained_age = 45
        result.account_value = 22_000
        result.regular_loan_principal = 100
        result.premiums_paid_to_date = 39_500
        result.cost_basis = 37_500
        result.accumulated_glp = 90_000
        result.accumulated_mtp = 14_500
        result.modal_premium = 200
        return result

    monkeypatch.setattr(value_rollback, "apply_value_rollback", apply)
    return apply


@pytest.fixture(scope="session")
def app():
    return QApplication.instance() or QApplication([])


@pytest.fixture(autouse=True)
def rollback_option(app):
    settings = get_illustration_settings()
    previous = settings.rollback_enabled
    settings.set_rollback_enabled(True)
    yield
    from PyQt6.QtCore import QCoreApplication, QEvent
    QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
    settings.set_rollback_enabled(previous)


@pytest.fixture
def tab(app, policy, historical):
    settings = get_illustration_settings()
    previous = settings.abr_quote_mode
    settings.set_abr_quote_mode(False)
    widget = IllustrationInputsTab()
    widget.load_data_from_policy(policy)
    yield widget
    widget.deleteLater()
    settings.set_abr_quote_mode(previous)


def test_rollback_uses_historical_values_before_assumptions_without_live_balance_leak(
    policy, historical,
):
    untouched = deepcopy(policy)
    inputs = IllustrationInputSet(dated_transactions=[
        DatedTransaction(TransactionKind.PREMIUM, date(2026, 4, 15), 123)])
    override = RollbackOverrideSet(EARLIER, {1: 80_000, 2: 40_000}, db_option="B")
    scenario = build_illustration_scenario(
        policy, InforceOverrideSet(
            account_value=99_999, regular_loan_principal=888,
            face_amount=900_000, db_option="C", current_interest_rate=0.06),
        future_inputs=inputs, rollback_overrides=override,
    )
    projected = scenario.projectable_policy
    assert projected.account_value == 22_000
    assert projected.regular_loan_principal == 100
    assert projected.premiums_paid_to_date == 39_500
    assert projected.cost_basis == 37_500
    assert projected.accumulated_glp == 90_000
    assert projected.accumulated_mtp == 14_500
    assert projected.current_interest_rate == 0.06
    assert projected.face_amount == 120_000 and projected.units == 100
    assert [s.units for s in projected.segments] == [80, 20]
    assert projected.segments[0].original_face_amount == 100_000
    assert projected.segments[0].coi_renewal_rate is None
    assert projected.db_option == "B"
    assert scenario.future_inputs == inputs and not inputs.policy_changes
    assert scenario.rollback_overrides == override
    override.coverage_amounts[1] = 1
    assert scenario.rollback_overrides.coverage_amounts[1] == 80_000
    assert policy == untouched


def test_rollback_rider_and_benefit_units_follow_their_own_vpu(policy, historical):
    candidate = build_illustration_scenario(
        policy, rollback_overrides=RollbackOverrideSet(
            EARLIER, coverage_amounts={3: 15_000},
            benefit_amounts={(1, "W", "1"): 20_000}),
    ).projectable_policy
    assert candidate.face_amount == 150_000
    assert candidate.riders[0].units == 15
    assert candidate.benefits[0].benefit_amount == 20_000
    assert candidate.benefits[0].units == 20
    assert policy.riders[0].face_amount == 10_000


@pytest.mark.parametrize("amounts", [
    {99: 1}, {1: -1}, {1: float("nan")}, {1: float("inf")},
    {1: 0, 2: 0}, {1: True}, {1: "invalid"},
])
def test_invalid_rollback_amounts_are_rejected_without_mutation(policy, historical, amounts):
    untouched = deepcopy(policy)
    with pytest.raises(ValueError):
        build_illustration_scenario(
            policy, rollback_overrides=RollbackOverrideSet(EARLIER, amounts))
    assert policy == untouched


@pytest.mark.parametrize("dbo", ["", "D", "b"])
def test_invalid_rollback_dbo_is_rejected(policy, historical, dbo):
    with pytest.raises(ValueError, match="death-benefit"):
        build_illustration_scenario(
            policy, rollback_overrides=RollbackOverrideSet(EARLIER, db_option=dbo))


def test_rollback_and_issue_are_exclusive_before_historical_lookup(policy):
    with pytest.raises(ValueError, match="cannot be combined"):
        build_illustration_scenario(
            policy, run_from_issue=True, rollback_overrides=RollbackOverrideSet(EARLIER))


def test_real_recorded_snapshot_flows_through_scenario_and_input_context(app, policy):
    policy.rollback_snapshots = [ValueRollbackSnapshot(
        valuation_date=EARLIER, source_valuation_date=LIVE,
        account_value=22_000, premiums_paid_to_date=39_500,
        premiums_ytd=2_000, accumulated_mtp=14_500, accumulated_glp=90_000,
        cost_basis=37_500, withdrawals_to_date=2_000,
        tamra_7year_contributions=[1_000] * 7,
        regular_loan_principal=100, regular_loan_accrued=3,
        preferred_loan_principal=0, preferred_loan_accrued=0,
        variable_loan_principal=0, variable_loan_accrued=0,
        system_coi_charge=12, system_expense_charge=4,
        system_other_charge=1, system_monthly_deduction=17,
    )]
    original = deepcopy(policy)
    widget = IllustrationInputsTab()
    try:
        widget.load_data_from_policy(policy)
        widget.set_value_rollback(RollbackOverrideSet(EARLIER))
        spec = build_spec_from_tab("Recorded rollback", widget, policy)
        candidate = spec.scenario.projectable_policy
        assert candidate.valuation_date == EARLIER
        assert candidate.account_value == 22_000
        assert candidate.regular_loan_principal + candidate.regular_loan_accrued == 103
        assert candidate.system_monthly_deduction == 17
        assert candidate.duration == 71
        assert widget.dynamic_panel._ctx.forecast_date == date(2026, 4, 15)
        assert policy == original
    finally:
        widget.deleteLater()


def test_clearing_unapplied_rollback_does_not_rebase_issue_mode(tab):
    tab.run_from_issue_btn.setChecked(True)
    before = tab.capture_case_inputs()
    emissions = []
    tab.rollback_changed.connect(lambda: emissions.append(True))
    tab.set_value_rollback(None)
    assert tab.capture_case_inputs() == before
    assert tab.dynamic_panel._ctx.forecast_date == ISSUE
    assert emissions == []


def test_default_inputs_reanchor_to_historical_year_premium_and_horizon(tab, policy):
    assert tab.dynamic_panel._ctx.billable_premium == 250
    candidate = tab.set_value_rollback(RollbackOverrideSet(EARLIER))
    assert tab._loaded_policy is policy
    assert tab._valuation_date == EARLIER
    assert tab.dynamic_panel._ctx.forecast_date == date(2026, 4, 15)
    row = tab.dynamic_panel.premium_section.rows()[0]
    assert row.year() == 6
    assert tab.dynamic_panel._ctx.billable_premium == 200
    assert candidate.account_value == 22_000
    assert tab._months_to_date(candidate, LIVE) == 2
    assert tab._months_to_maturity(candidate) == tab._months_to_maturity(policy) + 2
    projected = build_spec_from_tab("Rollback", tab, policy)
    assert projected.scenario.projectable_policy.valuation_date == EARLIER
    assert projected.scenario.rollback_overrides == RollbackOverrideSet(EARLIER)
    tab.set_value_rollback(None)
    assert tab._valuation_date == LIVE
    assert tab.dynamic_panel._ctx.billable_premium == 250


def test_explicit_schedules_survive_rollback_no_history_is_replayed(tab, policy):
    row = tab.dynamic_panel.premium_section.rows()[0]
    row.type_combo.setCurrentText("INPUT")
    row.amount_edit.setText("321")
    tab.dynamic_panel.lumpsum_edit.setText("777")
    prior = tab.dynamic_panel.capture_state()
    tab.set_value_rollback(RollbackOverrideSet(EARLIER))
    assert tab.dynamic_panel.capture_state() == prior
    exported = tab.export_input_set()
    assert exported.policy_changes == []
    assert any(
        transaction.amount == 321
        for transaction in exported.scheduled_transactions
        if transaction.kind == TransactionKind.PREMIUM)
    tab.dynamic_panel.lumpsum_edit.setText("999")
    tab.set_value_rollback(None)
    assert tab.dynamic_panel.capture_state() == prior


def test_rollback_case_roundtrip_restores_applied_basis_and_original_live_inputs(
    tab, app, policy,
):
    live_inputs = tab.dynamic_panel.capture_state()
    tab.set_value_rollback(RollbackOverrideSet(
        EARLIER, coverage_amounts={1: 80_000}, db_option="B",
        benefit_amounts={(1, "W", "1"): 50_000}, account_value=12_345))
    tab.dynamic_panel.lumpsum_edit.setText("654")
    applied = tab.capture_case_inputs()
    restored = IllustrationInputsTab()
    try:
        restored.load_data_from_policy(policy)
        assert restored.apply_case_inputs(json.loads(json.dumps(applied))) == []
        assert restored.export_rollback_overrides() == tab.export_rollback_overrides()
        assert restored.capture_case_inputs() == applied
        scenario = build_spec_from_tab("Saved rollback", restored, policy).scenario
        assert scenario.projectable_policy.valuation_date == EARLIER
        assert scenario.projectable_policy.face_amount == 130_000
        assert scenario.projectable_policy.account_value == 12_345
        restored.set_value_rollback(None)
        assert restored.dynamic_panel.capture_state() == live_inputs
    finally:
        restored.deleteLater()


def test_current_date_noop_needs_no_historical_snapshot(policy):
    original = deepcopy(policy)
    candidate = build_illustration_scenario(
        policy, rollback_overrides=RollbackOverrideSet(LIVE)).projectable_policy
    assert candidate == original
    assert candidate is not policy
    assert candidate.rollback_date is None
    assert candidate.starting_basis_assumptions == []
    assert policy == original


def test_current_manual_balances_and_amounts_are_independent_of_live_overrides(policy):
    original = deepcopy(policy)
    candidate = build_illustration_scenario(
        policy,
        inforce_overrides=InforceOverrideSet(account_value=999_999, current_interest_rate=0.06),
        rollback_overrides=RollbackOverrideSet(
            LIVE, coverage_amounts={1: 80_000}, benefit_amounts={(1, "W", "1"): 20_000},
            db_option="B", account_value=0, shadow_account_value=0),
    ).projectable_policy
    assert candidate.valuation_date == LIVE
    assert candidate.rollback_date is None
    assert candidate.account_value == candidate.shadow_account_value == 0
    assert candidate.face_amount == 130_000
    assert candidate.benefits[0].benefit_amount == 20_000
    assert candidate.db_option == "B"
    assert candidate.regular_loan_principal == policy.regular_loan_principal
    assert candidate.current_interest_rate == 0.06
    assert candidate.starting_account_value_is_manual
    assert "manually" in " ".join(candidate.starting_basis_assumptions)
    assert policy == original


@pytest.mark.parametrize("amount", [True, "100", float("nan"), float("inf")])
@pytest.mark.parametrize("field", ["account_value", "shadow_account_value"])
def test_current_invalid_balance_cannot_change_source(policy, amount, field):
    original = deepcopy(policy)
    with pytest.raises(ValueError):
        build_illustration_scenario(
            policy, rollback_overrides=RollbackOverrideSet(LIVE, **{field: amount}))
    assert policy == original


def test_current_date_saved_compare_preserves_manual_zero_and_reset_inputs(app, policy):
    settings = get_illustration_settings()
    previous = settings.abr_quote_mode
    settings.set_abr_quote_mode(False)
    source, restored = IllustrationInputsTab(), IllustrationInputsTab()
    try:
        source.load_data_from_policy(policy)
        source.dynamic_panel.lumpsum_edit.setText("321")
        live_inputs = source.dynamic_panel.capture_state()
        source.set_value_rollback(RollbackOverrideSet(
            LIVE, account_value=0, shadow_account_value=0, db_option="C"))
        source.dynamic_panel.lumpsum_edit.setText("654")
        saved = json.loads(json.dumps(source.capture_case_inputs()))
        restored.load_data_from_policy(policy)
        assert restored.apply_case_inputs(saved) == []
        assert restored.capture_case_inputs() == saved
        spec = build_spec_from_tab("Current manual", restored, policy)
        candidate = spec.scenario.projectable_policy
        assert candidate.account_value == candidate.shadow_account_value == 0
        assert candidate.db_option == "C"
        assert candidate.rollback_date is None
        assert spec.scenario.rollback_overrides.account_value == 0
        restored.set_value_rollback(None)
        assert restored.dynamic_panel.capture_state() == live_inputs
        assert restored.export_rollback_overrides() is None
        assert restored._loaded_policy.account_value == 25_000
    finally:
        source.deleteLater()
        restored.deleteLater()
        settings.set_abr_quote_mode(previous)


def test_manual_av_does_not_unlock_missing_historical_shadow():
    from tests.test_value_rollback_data import _policy, _complete_snapshot, WHEN

    policy = _policy()
    policy.ccv_active = True
    policy.shadow_account_value = 12_000
    policy.rollback_snapshots = [_complete_snapshot()]
    overrides = RollbackOverrideSet(WHEN, account_value=0)
    preview = build_illustration_scenario(
        policy, rollback_overrides=overrides, allow_missing_shadow=True).projectable_policy
    assert preview.account_value == 0
    assert preview.rollback_requires_shadow_value
    with pytest.raises(ValueError, match="shadow"):
        build_illustration_scenario(policy, rollback_overrides=overrides)
    overrides.shadow_account_value = 0
    supplied = build_illustration_scenario(
        policy, rollback_overrides=overrides).projectable_policy
    assert supplied.shadow_account_value == 0
    assert not supplied.rollback_requires_shadow_value
    assert policy.rollback_snapshots[0].shadow_account_value is None


@pytest.mark.parametrize("historical", [False, True])
def test_signed_starting_balances_are_valid_for_current_and_historical_dates(historical):
    from tests.test_value_rollback_data import _policy, _complete_snapshot, WHEN

    policy = _policy()
    policy.ccv_active = True
    policy.shadow_account_value = 12_000
    policy.rollback_snapshots = [_complete_snapshot()]
    when = WHEN if historical else policy.valuation_date
    candidate = build_illustration_scenario(
        policy, rollback_overrides=RollbackOverrideSet(
            when, account_value=-123.45, shadow_account_value=-678.90),
    ).projectable_policy
    assert candidate.account_value == -123.45
    assert candidate.shadow_account_value == -678.90
    assert not candidate.rollback_requires_shadow_value
    assert candidate.rollback_date == (WHEN if historical else None)
    assert policy.account_value == 20_000
    assert policy.shadow_account_value == 12_000


def test_current_manual_av_retains_independent_captured_fund_balances(policy):
    policy.fund_values = {"SW": 5_000, "M1": 20_000}
    policy.premium_allocations = {"M1": 1.0}
    candidate = build_illustration_scenario(
        policy, rollback_overrides=RollbackOverrideSet(LIVE, account_value=10_000),
    ).projectable_policy
    assert candidate.fund_values == policy.fund_values
    assert candidate.premium_allocations == policy.premium_allocations
    assert "total-only" in " ".join(candidate.starting_basis_assumptions)
    assert policy.fund_values == {"SW": 5_000, "M1": 20_000}


def test_failed_update_keeps_applied_state_and_does_not_emit(tab):
    tab.set_value_rollback(RollbackOverrideSet(EARLIER))
    before = tab.capture_case_inputs()
    emissions = []
    tab.rollback_changed.connect(lambda: emissions.append(True))
    with pytest.raises(ValueError, match="No reliable"):
        tab.set_value_rollback(RollbackOverrideSet(date(2025, 1, 1)))
    assert tab.capture_case_inputs() == before
    assert tab._valuation_date == EARLIER and emissions == []


def test_rollback_issue_and_abr_inputs_are_mutually_exclusive(tab):
    tab.set_value_rollback(RollbackOverrideSet(EARLIER))
    tab.run_from_issue_btn.setChecked(True)
    assert not tab.run_from_issue_enabled()
    assert tab.export_rollback_overrides() is not None
    settings = get_illustration_settings()
    settings.set_abr_quote_mode(True)
    assert tab.export_rollback_overrides() is None
    with pytest.raises(ValueError, match="ABR Quote"):
        tab.set_value_rollback(RollbackOverrideSet(EARLIER))
    settings.set_abr_quote_mode(False)
    tab.run_from_issue_btn.setChecked(True)
    with pytest.raises(ValueError, match="Inforce mode"):
        tab.set_value_rollback(RollbackOverrideSet(EARLIER))


def test_report_labels_historical_basis_and_retains_recorded_limits(policy, historical):
    from suiteview.illustration.core.report_builder import build_ul_report
    from suiteview.illustration.models.calc_state import MonthlyState
    from suiteview.illustration.ui.report_tab import format_report_pages

    candidate = build_illustration_scenario(
        policy, rollback_overrides=RollbackOverrideSet(EARLIER)).projectable_policy
    report = build_ul_report(candidate, [MonthlyState(date=EARLIER)])
    pages = format_report_pages(report)
    assert report.as_of_date == EARLIER
    for page in pages:
        text = "\n".join(page)
        assert "VALUE ROLLBACK" in text
        assert "VALUES AS OF: 03/15/2026" in text
        assert "NOT A HISTORICAL TRANSACTION REPLAY" in text
        assert "Current rate assumptions are retained." in text


@pytest.mark.parametrize("payload", [
    [], {},
    {"valuation_date": "not-a-date"},
    {"valuation_date": EARLIER.isoformat(), "coverage_amounts": []},
    {"valuation_date": EARLIER.isoformat(), "benefit_amounts": {}},
    {"valuation_date": EARLIER.isoformat(), "benefit_amounts": [[1, "W"]]},
    {"valuation_date": EARLIER.isoformat(),
     "benefit_amounts": [[1, "W", "1", 100], [1, "W", "1", 200]]},
])
def test_malformed_saved_rollback_is_rejected_before_changing_applied_state(tab, payload):
    tab.set_value_rollback(RollbackOverrideSet(EARLIER))
    original = tab.capture_case_inputs()
    state = deepcopy(original)
    state["value_rollback"] = payload
    with pytest.raises(ValueError, match="Saved Edit Record"):
        tab.apply_case_inputs(state)
    assert tab.capture_case_inputs() == original
