"""Edit Record contracts across capture, scenarios, persistence and projection."""

import json
import os
from copy import deepcopy
from datetime import date

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PyQt6.QtWidgets import QApplication

from suiteview.illustration.core.scenario_builder import build_illustration_scenario
from suiteview.illustration.models.input_set import (
    InforceOverrideSet, RECORD_FIELD_SPECS, RollbackOverrideSet,
)
from suiteview.illustration.models.policy_data import CoverageSegment, IllustrationPolicyData


WHEN = date(2026, 6, 15)
ISSUE = date(2020, 6, 15)


@pytest.fixture
def policy():
    return IllustrationPolicyData(
        policy_number="RECORD", plancode="1U135D00", issue_date=ISSUE,
        valuation_date=WHEN, illustration_date=WHEN, issue_age=40, attained_age=46,
        policy_year=7, policy_month=1, duration=73, maturity_age=100,
        face_amount=100_000, units=100, account_value=11_500,
        premium_pay_status_code="22", cost_basis=2_000,
        tamra_7pay_start_date=ISSUE, map_cease_date=date(2040, 6, 15),
        fund_values={"SW": 3_000, "M1": 7_000, "ZERO": 0},
        impaired_fund_values={"SW": 1_000},
        premium_allocations={"SW": 0.25, "M1": 0.75, "ZERO": 0},
        segments=[CoverageSegment(
            coverage_phase=1, issue_date=ISSUE, issue_age=40,
            face_amount=100_000, units=100, vpu=1_000)],
    )


def _scenario(policy, **kwargs):
    return build_illustration_scenario(
        policy, rollback_overrides=RollbackOverrideSet(WHEN, **kwargs)).projectable_policy


def _all_record_values():
    values = {
        name: index + 0.25 for index, name in enumerate(RECORD_FIELD_SPECS)
        if RECORD_FIELD_SPECS[name].kind == "amount"
    }
    values.update(
        premium_pay_status_code="54", is_mec=True,
        map_cease_date=None, tamra_7pay_start_date=date(2025, 6, 15),
        regular_loan_charge_rate=0.06, preferred_loan_charge_rate=0.04,
        variable_loan_charge_rate=0.07,
    )
    assert values.keys() == RECORD_FIELD_SPECS.keys()
    return values


def test_every_scalar_reaches_starting_policy_without_mutating_source_or_coverages(policy):
    untouched = deepcopy(policy)
    values = _all_record_values()
    contributions = [0, 1, -2, 3, 4, 5, 6]
    candidate = _scenario(
        policy, record_values=values, tamra_7year_contributions=contributions)
    for name, value in values.items():
        assert getattr(candidate, name) == value
    assert candidate.tamra_7pay_start_av == values["tamra_7pay_cash_value"]
    assert candidate.segments == policy.segments
    assert candidate.premium_transactions == policy.premium_transactions
    assert candidate.starting_record_fields == [*values, "tamra_7year_contributions"]
    assert "54 - Lapsing" in " ".join(candidate.starting_basis_assumptions)
    assert "waiver rules" in " ".join(candidate.starting_basis_assumptions)
    assert policy == untouched
    contributions[0] = 900
    assert candidate.tamra_7year_contributions[0] == 0


def test_explicit_null_dates_and_zero_and_false_survive(policy):
    policy.is_mec = True
    candidate = _scenario(policy, record_values={
        "tamra_7pay_start_date": None, "map_cease_date": None,
        "is_mec": False, "mtp": 0, "regular_loan_charge_rate": 0,
    })
    assert candidate.tamra_7pay_start_date is None
    assert candidate.map_cease_date is None
    assert candidate.is_mec is False
    assert candidate.mtp == candidate.regular_loan_charge_rate == 0
    assert _scenario(policy).tamra_7pay_start_date == ISSUE


@pytest.mark.parametrize("values", [
    {"status_code": "0"}, {"segments": []}, {"unknown": 0}, [],
    {"premium_pay_status_code": "0"}, {"premium_pay_status_code": 22},
    {"is_mec": 1}, {"is_mec": "false"}, {"is_mec": None},
    {"mtp": None}, {"mtp": True}, {"ctp": "10"},
    {"glp": float("nan")}, {"gsp": float("inf")},
    {"glp": 10 ** 400},
    {"map_cease_date": "2026-06-15"}, {"map_cease_date": True},
    {"regular_loan_charge_rate": -0.01}, {"preferred_loan_charge_rate": 1.1},
    {"variable_loan_charge_rate": None},
])
def test_invalid_record_values_fail_without_changing_source(policy, values):
    untouched = deepcopy(policy)
    with pytest.raises(ValueError):
        _scenario(policy, record_values=values)
    assert policy == untouched


@pytest.mark.parametrize("contributions", [
    [], [0] * 6, [0] * 8, [0] * 6 + [True],
    [0] * 6 + [float("nan")], "invalid",
])
def test_invalid_contributions_fail_without_changing_source(policy, contributions):
    untouched = deepcopy(policy)
    with pytest.raises(ValueError):
        _scenario(policy, tamra_7year_contributions=contributions)
    assert policy == untouched


def test_fund_edits_preserve_full_ids_and_independent_aggregate_av(policy):
    candidate = _scenario(
        policy, fund_values={"SW": 4_000, "M1": 7_000, "ZERO": -25},
        impaired_fund_values={"SW": 900},
        premium_allocations={"SW": 0.20, "M1": 0.70, "ZERO": 0.10})
    assert candidate.account_value == policy.account_value
    assert not candidate.starting_account_value_is_manual
    assert candidate.regular_loan_principal == policy.regular_loan_principal
    assert candidate.premium_allocations == {"SW": 0.20, "M1": 0.70, "ZERO": 0.10}
    assert "remains independent" in " ".join(candidate.starting_basis_assumptions)
    assert policy.fund_values == {"SW": 3_000, "M1": 7_000, "ZERO": 0}


def test_explicit_av_is_independent_of_fund_edits(policy):
    candidate = _scenario(
        policy, account_value=1_000, fund_values={"SW": 3_100, "M1": 7_000, "ZERO": 0})
    assert candidate.account_value == 1_000
    assert "remains independent" in " ".join(candidate.starting_basis_assumptions)
    assert _scenario(policy, account_value=1_000).account_value == 1_000
    assert _scenario(policy, account_value=1_000).fund_values == policy.fund_values


@pytest.mark.parametrize("kwargs", [
    {"fund_values": {"SW": 3_000, "M1": 7_000}},
    {"fund_values": {"SW": 3_000, "M1": 7_000, "NEW": 0}},
    {"fund_values": {"SW": float("nan"), "M1": 7_000, "ZERO": 0}},
    {"impaired_fund_values": {"SW": "900"}},
    {"impaired_fund_values": {"SW": True}},
    {"impaired_fund_values": {}},
    {"fund_values": []},
    {"premium_allocations": {"SW": 25, "M1": 75, "ZERO": 0}},
    {"premium_allocations": {"SW": 0.25, "M1": 0.7, "ZERO": 0}},
    {"premium_allocations": {"SW": 0.25, "M1": 0.85, "ZERO": -0.1}},
    {"premium_allocations": {"SW": 0.25, "M1": 0.75}},
])
def test_invalid_fund_and_allocation_batches_are_atomic(policy, kwargs):
    untouched = deepcopy(policy)
    with pytest.raises(ValueError):
        _scenario(policy, **kwargs)
    assert policy == untouched


def test_fund_key_validation_uses_captured_not_forward_allocation_ids(policy):
    with pytest.raises(ValueError, match="fund ID"):
        build_illustration_scenario(
            policy, InforceOverrideSet(premium_allocations={"NEW": 1.0}),
            rollback_overrides=RollbackOverrideSet(
                WHEN, premium_allocations={"NEW": 1.0}))


def test_missing_historical_buckets_never_inherit_current_impaired_funds():
    from tests.test_value_rollback_data import _policy, _complete_snapshot, WHEN as HISTORICAL
    from suiteview.illustration.core.value_rollback import apply_value_rollback

    policy = _policy()
    policy.impaired_fund_values = {"SW": 500}
    snapshot = _complete_snapshot()
    snapshot.fund_values = None
    policy.rollback_snapshots = [snapshot]
    candidate = apply_value_rollback(policy, HISTORICAL)
    assert candidate.fund_values == candidate.impaired_fund_values == {}
    with pytest.raises(ValueError, match="fund ID"):
        build_illustration_scenario(
            policy, rollback_overrides=RollbackOverrideSet(
                HISTORICAL, impaired_fund_values={"SW": 300}))
    assert policy.impaired_fund_values == {"SW": 500}


def test_historical_total_is_not_synthesized_as_an_existing_single_fund():
    from tests.test_value_rollback_data import _policy, _Source
    from suiteview.illustration.core.value_rollback import build_value_rollback_snapshots

    policy = _policy()
    policy.fund_values = {"SW": policy.account_value}
    snapshots = build_value_rollback_snapshots(_Source(), policy)
    assert snapshots and all(snapshot.fund_values is None for snapshot in snapshots)


def test_canonical_capture_keeps_status_split_funds_rates_and_tamra(monkeypatch):
    from tests.test_illustration_policy_service import _FakePolicyInfo, _FakeRates
    from suiteview.illustration.core import illustration_policy_service as service
    from suiteview.illustration.models.plancode_config import PlancodeConfig
    from types import SimpleNamespace

    pi = _FakePolicyInfo()
    pi.status.premium_pay_status_code = "22"
    pi.loans.fixed_loan_interest_rate = 0.5
    pi.loans.preferred_loan_interest_rate = 6
    pi.values.tamra_7pay_av = 1_234.56
    pi.values.tamra_7pay_specified_amount = 80_000
    pi.values.get_fund_values_dict = lambda: {"SW": 8_000, "ZERO": 0}
    def buckets(*, current_only):
        assert current_only is True
        return [
            SimpleNamespace(fund_id="SW", csv_amount=3_000),
            SimpleNamespace(fund_id="SW", csv_amount=5_000),
            SimpleNamespace(fund_id="ZERO", csv_amount=None),
        ]
    pi.values.get_fund_buckets = buckets
    pi.values.get_loan_values_dict = lambda: {"SW": 2_000}
    pi.values.get_premium_allocation_dict = lambda: {"SW": 75, "M1": 25, "ZERO": 0}
    monkeypatch.setattr(service, "get_policy_info", lambda *_args: pi)
    monkeypatch.setattr(service, "Rates", _FakeRates)
    monkeypatch.setattr(service, "load_plancode", lambda _: PlancodeConfig(plancode="TESTUL"))
    policy = service.build_illustration_data("RECORD")
    assert policy.premium_pay_status_code == "22"
    assert policy.fund_values == {"SW": 8_000, "ZERO": 0}
    assert policy.impaired_fund_values == {"SW": 2_000}
    assert policy.premium_allocations == {"SW": 0.75, "M1": 0.25, "ZERO": 0}
    assert policy.regular_loan_charge_rate == 0.005
    assert policy.preferred_loan_charge_rate == 0.06
    assert policy.tamra_7pay_cash_value == policy.tamra_7pay_start_av == 1_234.56
    assert policy.tamra_7year_lowest_db == 80_000


def test_failed_fund_capture_is_not_silently_replaced_with_empty_maps(monkeypatch):
    from tests.test_illustration_policy_service import _FakePolicyInfo, _FakeRates
    from suiteview.illustration.core import illustration_policy_service as service
    from suiteview.illustration.models.plancode_config import PlancodeConfig

    pi = _FakePolicyInfo()

    def failed():
        raise RuntimeError("Fund source unavailable")

    pi.values.get_loan_values_dict = failed
    monkeypatch.setattr(service, "get_policy_info", lambda *_args: pi)
    monkeypatch.setattr(service, "Rates", _FakeRates)
    monkeypatch.setattr(service, "load_plancode", lambda _: PlancodeConfig(plancode="TESTUL"))
    with pytest.raises(RuntimeError, match="Fund source unavailable"):
        service.build_illustration_data("RECORD")


@pytest.fixture(scope="session")
def record_app():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def tab(policy, record_app):
    from suiteview.illustration.models.app_settings import get_illustration_settings
    from suiteview.illustration.ui.inputs_tab import IllustrationInputsTab
    from PyQt6.QtCore import QCoreApplication, QEvent

    settings = get_illustration_settings()
    prior = settings.rollback_enabled, settings.abr_quote_mode
    settings.set_rollback_enabled(True)
    settings.set_abr_quote_mode(False)
    widget = IllustrationInputsTab()
    widget.load_data_from_policy(policy)
    yield widget
    widget.deleteLater()
    QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
    settings.set_rollback_enabled(prior[0])
    settings.set_abr_quote_mode(prior[1])


def test_full_case_json_and_compare_roundtrip(tab, policy):
    from suiteview.illustration.models.case_store import decode_policy_snapshot, encode_policy_snapshot
    from suiteview.illustration.ui.saved_case_scenario import build_spec_from_tab
    from suiteview.illustration.core.report_builder import rollback_output_basis

    override = RollbackOverrideSet(
        WHEN, record_values=_all_record_values(),
        tamra_7year_contributions=[0, 1, -2, 3, 4, 5, 6],
        fund_values={"SW": 3_100, "M1": 7_000, "ZERO": 0},
        impaired_fund_values={"SW": 950},
        premium_allocations={"SW": 0.4, "M1": 0.6, "ZERO": 0},
    )
    candidate = tab.set_value_rollback(override)
    payload = json.loads(json.dumps(tab.capture_case_inputs(), allow_nan=False))
    assert payload["value_rollback"]["record_values"]["map_cease_date"] is None
    assert payload["value_rollback"]["record_values"]["tamra_7pay_start_date"] == "2025-06-15"
    tab.set_value_rollback(None)
    assert tab.apply_case_inputs(payload) == []
    assert tab.export_rollback_overrides() == override
    spec = build_spec_from_tab("Edited record", tab, policy)
    assert spec.scenario.projectable_policy.tamra_7year_contributions == [0, 1, -2, 3, 4, 5, 6]
    assert spec.scenario.projectable_policy.premium_pay_status_code == "54"
    assert spec.scenario.projectable_policy.account_value == candidate.account_value
    decoded = decode_policy_snapshot(encode_policy_snapshot(candidate))
    assert decoded == candidate
    basis = " ".join(rollback_output_basis(decoded))
    assert "54 - Lapsing" in basis and "7-pay contributions" in basis
    assert "Regular loan charge rate" in basis and "remains independent" in basis


def test_invalid_imported_record_leaves_applied_basis_intact(tab):
    tab.set_value_rollback(RollbackOverrideSet(WHEN, record_values={"mtp": 25}))
    before = tab.capture_case_inputs()
    corrupted = deepcopy(before)
    corrupted["value_rollback"]["premium_allocations"] = {"NEW": 1.0}
    with pytest.raises(ValueError):
        tab.apply_case_inputs(corrupted)
    assert tab.capture_case_inputs() == before


def test_edited_loan_rates_and_balances_drive_engine_without_mutating_shared_plan(monkeypatch):
    from tests.test_illustration_iul_crediting import _iul_policy, _patch_config, _test_config
    from suiteview.illustration.core.calc_engine import IllustrationEngine
    from suiteview.illustration.core.rate_loader import IllustrationRates

    source = _iul_policy(plancode="TEST")
    config = _test_config(loan_charge_rate_guar=0.01, pref_loan_charge_rate_guar=0.02)
    original_config = deepcopy(config)
    _patch_config(monkeypatch, config)
    candidate = build_illustration_scenario(
        source, rollback_overrides=RollbackOverrideSet(source.valuation_date, record_values={
            "regular_loan_principal": 1_000, "regular_loan_accrued": 10,
            "preferred_loan_principal": 2_000, "preferred_loan_accrued": 20,
            "variable_loan_principal": 300, "variable_loan_accrued": 3,
            "regular_loan_charge_rate": 0.06, "preferred_loan_charge_rate": 0.04,
            "variable_loan_charge_rate": 0.07,
        })).projectable_policy
    engine = IllustrationEngine()
    edited = engine.project(candidate, months=1, rates_override=IllustrationRates())
    baseline = deepcopy(candidate)
    baseline.starting_record_fields = []
    unedited_rates = engine.project(baseline, months=1, rates_override=IllustrationRates())
    assert config == original_config
    assert len(edited) == len(unedited_rates) == 2
    assert edited[-1].policy_debt > unedited_rates[-1].policy_debt
    assert edited[-1].reg_loan_charge > unedited_rates[-1].reg_loan_charge
    assert edited[-1].pref_loan_charge > unedited_rates[-1].pref_loan_charge
    assert source.regular_loan_principal == 0


def test_tax_premium_and_target_edits_reach_engine_opening_state(monkeypatch):
    from tests.test_illustration_iul_crediting import _iul_policy, _patch_config, _test_config
    from suiteview.illustration.core.calc_engine import IllustrationEngine
    from suiteview.illustration.core.rate_loader import IllustrationRates
    from suiteview.illustration.core.target_premium import floor_monthly_cent

    source = _iul_policy(plancode="TEST")
    _patch_config(monkeypatch, _test_config())
    values = {
        "premiums_ytd": 2_000, "premiums_paid_to_date": 20_000,
        "withdrawals_to_date": 300, "cost_basis": 19_000,
        "accumulated_mtp": 5_000, "mtp": 30, "ctp": 600,
        "glp": 5_000, "gsp": 25_000, "accumulated_glp": 30_000,
        "is_mec": True, "tamra_7pay_start_date": date(2023, 6, 1),
        "tamra_7pay_cash_value": 1234, "tamra_7pay_level": 6_000,
        "tamra_7year_lowest_db": 0,
    }
    candidate = build_illustration_scenario(
        source, rollback_overrides=RollbackOverrideSet(
            source.valuation_date, record_values=values,
            tamra_7year_contributions=[500, 700, 900, 200, 0, 0, 0],
        )).projectable_policy
    opening, *_ = IllustrationEngine().project(
        candidate, months=1, rates_override=IllustrationRates())
    for name in (
        "premiums_ytd", "withdrawals_to_date", "cost_basis", "accumulated_mtp",
        "ctp", "glp", "gsp", "accumulated_glp", "is_mec",
        "tamra_7pay_start_date", "tamra_7pay_level",
    ):
        expected = floor_monthly_cent(values[name]) if name in ("glp", "gsp") else values[name]
        assert getattr(opening, name) == expected
    assert opening.premiums_to_date == values["premiums_paid_to_date"]
    assert opening.monthly_mtp == values["mtp"]
    assert opening.lowest_7yr_face == 0
