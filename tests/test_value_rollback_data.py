"""Historical values must be sourced, date-consistent and safe before projection."""
from copy import deepcopy
from dataclasses import asdict
from datetime import date
from types import SimpleNamespace

import pytest

from suiteview.illustration.core.value_rollback import (
    apply_value_rollback,
    available_rollback_dates,
    build_value_rollback_snapshots,
)
from suiteview.illustration.models.policy_data import (
    CoverageSegment, IllustrationPolicyData, ValueRollbackSnapshot,
)


WHEN = date(2026, 8, 15)
ANCHOR = date(2026, 9, 15)


def _policy():
    return IllustrationPolicyData(
        issue_date=date(2020, 1, 15), issue_age=40, attained_age=46,
        valuation_date=ANCHOR, illustration_date=date(2026, 9, 20),
        policy_year=7, policy_month=9, duration=81,
        account_value=20_000, premiums_paid_to_date=11_000,
        cost_basis=9_000, product_type="UL", def_of_life_ins="GPT",
        mtp=100, glp=1200,
        segments=[CoverageSegment(issue_date=date(2020, 1, 15), face_amount=100_000)],
    )


def _complete_snapshot(when=WHEN):
    return ValueRollbackSnapshot(
        valuation_date=when, source_valuation_date=ANCHOR,
        account_value=10_000, premiums_paid_to_date=10_400, premiums_ytd=400,
        accumulated_mtp=2_500, accumulated_glp=15_000, cost_basis=8_400,
        withdrawals_to_date=2_000, tamra_7year_contributions=[0, 0, 0, 400, 0, 0, 0],
        regular_loan_principal=0, regular_loan_accrued=0,
        preferred_loan_principal=0, preferred_loan_accrued=0,
        variable_loan_principal=0, variable_loan_accrued=0,
        system_coi_charge=20, system_expense_charge=5,
        system_other_charge=0, system_monthly_deduction=25,
        limitations=["Coverage amounts remain an explicit current assumption."],
    )


def _transaction(day, code, amount, sequence):
    return {
        "ASOF_DT": day, "ENTRY_DT": day, "TRANS": code, "GROSS_AMT": amount,
        "SEQ_NO": sequence, "FCB0_REV_IND": "0", "FCB2_REV_APPL_IND": "0",
        "FEB3_1035_EXCH_IND": "0", "FBB3_PROCD_IND": "1",
    }


class _Source:
    def __init__(self):
        self.errors = {}
        self.coverages = SimpleNamespace(get_coverages=lambda: self.get_coverages())
        self.tables = {
            "LH_POL_MVRY_VAL": [{
                "MVRY_DT": WHEN, "CSV_AMT": 10_000, "POL_DUR_NBR": 7,
                "CINS_AMT": 20, "EXP_CRG_AMT": 5, "OTH_PRM_AMT": 0,
            }],
            "LH_POL_TOTALS": [{
                "TOT_REG_PRM_AMT": 10_000, "TOT_ADD_PRM_AMT": 1_000,
                "POL_CST_BSS_AMT": 9_000, "TOT_WTD_AMT": 2_000, "TOT_WTD_QTY": 2,
            }],
            "LH_POL_YR_TOT": [{
                "POL_YR_DUR": 7, "YTD_TOT_PMT_AMT": 1_000, "YTD_ADD_PRM_AMT": 0,
            }],
            "LH_POL_TARGET": [
                {"TAR_TYP_CD": "MA", "TAR_PRM_AMT": 5_000, "TAR_DT": date(2030, 1, 15)},
                {"TAR_TYP_CD": "TA", "TAR_PRM_AMT": 15_000, "TAR_DT": date(2020, 1, 15)},
                {"TAR_TYP_CD": "MT", "TAR_PRM_AMT": 100, "TAR_DT": date(2020, 1, 15)},
            ],
            "LH_COV_INS_GDL_PRM": [{"PRM_RT_TYP_CD": "A", "GDL_PRM_AMT": 1200}],
            "LH_TAMRA_7_PY_PER": [{"SVPY_PER_STR_DT": date(2023, 1, 15)}],
            "LH_TAMRA_7_PY_YR": [
                {"SVPY_YR_SEQ_NBR": year, "SVPY_PRM_PAY_AMT": 1_000 if year == 4 else 0,
                 "SVPY_WTD_AMT": 0}
                for year in reversed(range(1, 8))
            ],
            "LH_FND_VAL_LOAN": [],
            "FH_FIXED": [
                _transaction(WHEN, "PR", 100, 100),
                _transaction(WHEN, "CD", 25, 101),
                _transaction(date(2026, 8, 16), "PR", 500, 102),
                _transaction(date(2026, 10, 1), "PR", 100, 103),
            ],
        }

    def fetch_table(self, table):
        return self.tables[table]

    def table_error(self, table):
        return self.errors.get(table, "")

    def get_coverages(self):
        return [SimpleNamespace(
            issue_date=date(2020, 1, 15), orig_amount=100_000, face_amount=100_000,
        )]


def test_dates_are_recorded_prior_dates_in_six_calendar_months():
    policy = _policy()
    policy.valuation_date = date(2026, 8, 31)
    policy.issue_date = date(2020, 1, 31)
    dates = [
        date(2026, 7, 31), date(2026, 2, 28), date(2026, 2, 27),
        date(2026, 8, 31), date(2026, 9, 30), date(9999, 12, 31),
        date(2026, 7, 31),
    ]
    policy.rollback_snapshots = [ValueRollbackSnapshot(valuation_date=when) for when in dates]
    assert available_rollback_dates(policy) == [date(2026, 7, 31), date(2026, 2, 28)]


def test_complete_snapshot_is_deep_copied_post_deduction_and_duration_consistent():
    policy = _policy()
    policy.rollback_snapshots = [_complete_snapshot()]
    original = deepcopy(policy)
    result = apply_value_rollback(policy, WHEN)
    assert policy == original
    assert result.account_value == 10_000  # NOT 9,975: MD already taken in U1MV
    assert (result.policy_year, result.policy_month, result.duration, result.attained_age) == (7, 8, 80, 46)
    assert result.rollback_date == result.valuation_date == WHEN
    assert result.rollback_source_date == ANCHOR
    assert result.illustration_date == policy.illustration_date
    assert result.cost_basis == 8_400
    result.segments[0].face_amount = 1
    result.tamra_7year_contributions[3] = 5
    assert policy.segments[0].face_amount == 100_000
    assert policy.rollback_snapshots[0].tamra_7year_contributions[3] == 400


def test_month_end_anniversary_uses_issue_day_anchor_and_updates_attained_age():
    policy = _policy()
    policy.issue_date = date(2020, 1, 31)
    policy.rollback_snapshots = [_complete_snapshot(date(2026, 2, 28))]
    # Expand the legitimate source window without changing the snapshot date.
    policy.valuation_date = date(2026, 8, 31)
    policy.rollback_snapshots[0].source_valuation_date = policy.valuation_date
    result = apply_value_rollback(policy, date(2026, 2, 28))
    assert (result.policy_year, result.policy_month, result.duration, result.attained_age) == (7, 2, 74, 46)


@pytest.mark.parametrize("field,value", [
    ("account_value", None), ("cost_basis", float("nan")),
    ("accumulated_mtp", None), ("accumulated_glp", float("inf")),
    ("regular_loan_principal", None), ("system_monthly_deduction", None),
])
def test_missing_or_nonfinite_amount_never_inherits_current_values(field, value):
    policy = _policy()
    snapshot = _complete_snapshot()
    setattr(snapshot, field, value)
    policy.rollback_snapshots = [snapshot]
    with pytest.raises(ValueError, match=field):
        apply_value_rollback(policy, WHEN)


def test_zero_is_a_real_recorded_amount():
    policy = _policy()
    snapshot = _complete_snapshot()
    snapshot.account_value = snapshot.cost_basis = snapshot.accumulated_glp = 0
    policy.rollback_snapshots = [snapshot]
    result = apply_value_rollback(policy, WHEN)
    assert result.account_value == result.cost_basis == result.accumulated_glp == 0


def test_unsafe_date_duplicate_snapshot_and_issue_mode_are_rejected():
    policy = _policy()
    policy.rollback_snapshots = [_complete_snapshot()]
    with pytest.raises(ValueError, match="No recorded"):
        apply_value_rollback(policy, date(2025, 1, 1))
    policy.rollback_snapshots.append(_complete_snapshot())
    with pytest.raises(ValueError, match="Multiple"):
        apply_value_rollback(policy, WHEN)
    policy.run_from_issue = True
    with pytest.raises(ValueError, match="From Issue"):
        apply_value_rollback(policy, WHEN)


def test_snapshots_serialize_as_typed_ordinary_nested_dataclasses():
    policy = _policy()
    policy.rollback_snapshots = [_complete_snapshot()]
    encoded = asdict(policy)["rollback_snapshots"][0]
    decoded = ValueRollbackSnapshot(**encoded)
    assert decoded == policy.rollback_snapshots[0]
    assert encoded["valuation_date"] == WHEN
    assert isinstance(encoded["tamra_7year_contributions"], list)


def test_eager_capture_standard_ul_is_usable_with_disclosed_target_derivation():
    source, policy = _Source(), _policy()
    before = deepcopy(policy)
    snapshot, = build_value_rollback_snapshots(source, policy)
    assert policy == before
    assert snapshot.account_value == 10_000
    assert snapshot.premiums_paid_to_date == 10_400
    assert snapshot.cost_basis == 8_400
    assert snapshot.premiums_ytd == 400
    assert snapshot.withdrawals_to_date == 2_000
    assert snapshot.tamra_7year_contributions == [0, 0, 0, 400, 0, 0, 0]
    assert snapshot.regular_loan_principal == 0
    assert snapshot.accumulated_mtp == 4900
    assert snapshot.accumulated_glp == 15000
    assert snapshot.blocking_errors == []
    assert any("derived, not archived" in note for note in snapshot.limitations)
    policy.rollback_snapshots = [snapshot]
    assert available_rollback_dates(policy) == [WHEN]
    result = apply_value_rollback(policy, WHEN)
    assert result.account_value == 10_000
    assert result.accumulated_mtp == 4900


def test_rollback_withdrawal_fees_come_from_the_same_totals_row():
    """TOT_WTD_QTY 2 x the plan's $25 fee, with TOT_WTD_AMT from the same row; the
    current policy's fee total (4 withdrawals) is not carried into the rollback."""
    source, policy = _Source(), _policy()
    policy.withdrawal_fee = 25.0
    policy.withdrawals_to_date, policy.inforce_withdrawal_fees = 4_000.0, 100.0
    snapshot, = build_value_rollback_snapshots(source, policy)
    assert (snapshot.withdrawals_to_date, snapshot.inforce_withdrawal_fees) == (2_000, 50.0)
    policy.rollback_snapshots = [snapshot]

    result = apply_value_rollback(policy, WHEN)

    assert (result.withdrawals_to_date, result.inforce_withdrawal_fees) == (2_000, 50.0)
    assert result.net_withdrawals(result.withdrawals_to_date) == 1_950.0


def test_rollback_snapshot_without_fees_does_not_inherit_current_fees():
    policy = _policy()
    policy.inforce_withdrawal_fees = 100.0
    policy.rollback_snapshots = [_complete_snapshot()]

    assert apply_value_rollback(policy, WHEN).inforce_withdrawal_fees == 0.0


def test_rollback_monthly_mtp_preserves_recorded_cents():
    source = _Source()
    for row in source.tables["LH_POL_TARGET"]:
        if row["TAR_TYP_CD"] == "MT":
            row["TAR_PRM_AMT"] = 32.66
    snapshot, = build_value_rollback_snapshots(source, _policy())
    assert snapshot.blocking_errors == []
    assert snapshot.accumulated_mtp == 4967.34


def test_missing_target_amount_stays_unavailable():
    source = _Source()
    source.tables["LH_POL_TARGET"][0]["TAR_PRM_AMT"] = None
    snapshot, = build_value_rollback_snapshots(source, _policy())
    assert snapshot.accumulated_mtp is None
    assert any("TAR_PRM_AMT" in error for error in snapshot.blocking_errors)


def test_glp_undoes_anniversaries_not_months_and_stops_at_age_100():
    source = _Source()
    policy = _policy()
    policy.valuation_date = date(2027, 1, 15)
    snapshot, = build_value_rollback_snapshots(source, policy)
    assert snapshot.accumulated_mtp == 4500
    assert snapshot.accumulated_glp == 13800
    policy.issue_age = 93  # Destination anniversary attains age 100.
    snapshot, = build_value_rollback_snapshots(source, policy)
    assert snapshot.accumulated_glp == 15000


def test_no_tamra_subsystem_is_distinct_from_missing_year_amounts():
    source = _Source()
    source.tables["LH_TAMRA_7_PY_PER"] = []
    source.tables["LH_TAMRA_7_PY_YR"] = []
    policy = _policy()
    snapshot, = build_value_rollback_snapshots(source, policy)
    assert snapshot.tamra_7year_contributions == [0.0] * 7
    assert any("NoTAMRAValues" in note for note in snapshot.limitations)
    policy.rollback_snapshots = [snapshot]
    assert apply_value_rollback(policy, WHEN).account_value == 10000


def test_ui_only_charge_component_does_not_disable_sourced_total_projection():
    source = _Source()
    source.tables["LH_POL_MVRY_VAL"][0]["OTH_PRM_AMT"] = None
    policy = _policy()
    snapshot, = build_value_rollback_snapshots(source, policy)
    assert snapshot.system_other_charge is None
    assert snapshot.system_monthly_deduction == 25  # Recorded CD, NOT a guessed sum.
    policy.rollback_snapshots = [snapshot]
    result = apply_value_rollback(policy, WHEN)
    assert result.system_monthly_deduction == 25
    assert any("diagnostic zero placeholders" in note for note in result.rollback_limitations)


def test_observed_coverage_change_blocks_unchanged_target_reconstruction():
    source = _Source()
    source.get_coverages = lambda: [SimpleNamespace(issue_date=date(2026, 9, 1))]
    snapshot, = build_value_rollback_snapshots(source, _policy())
    assert snapshot.accumulated_mtp is None
    assert any("coverage change crosses" in error for error in snapshot.blocking_errors)


def test_same_day_premium_after_recorded_deduction_is_reversed():
    source = _Source()
    source.tables["FH_FIXED"][0]["SEQ_NO"] = 104
    snapshot, = build_value_rollback_snapshots(source, _policy())
    assert snapshot.premiums_paid_to_date == 10_300
    assert snapshot.tamra_7year_contributions[3] == 300


def test_pending_premium_is_excluded_only_after_current_total_reconciliation():
    source = _Source()
    pending = _transaction(date(2026, 10, 4), "PR", 150, 104)
    pending["FBB3_PROCD_IND"] = "0"
    source.tables["FH_FIXED"].extend([
        _transaction(date(2020, 1, 15), "PR", 10_300, 1), pending,
    ])
    snapshot, = build_value_rollback_snapshots(source, _policy())
    assert snapshot.premiums_paid_to_date == 10_400
    assert snapshot.cost_basis == 8_400
    assert snapshot.blocking_errors == []
    assert any("Pending premiums" in note for note in snapshot.limitations)


def test_pending_premium_cannot_be_silently_excluded_from_incomplete_history():
    source = _Source()
    source.tables["FH_FIXED"][2]["FBB3_PROCD_IND"] = "0"
    snapshot, = build_value_rollback_snapshots(source, _policy())
    assert snapshot.premiums_paid_to_date is None
    assert any("does not reconcile" in error for error in snapshot.blocking_errors)


@pytest.mark.parametrize("product,plancode", [
    ("IUL", "TEST"), ("Advanced", "1U145500"),
])
@pytest.mark.parametrize("account_value", [0, 10_000])
def test_iul_rolls_back_total_av_and_targets_without_reconstructing_buckets(
    product, plancode, account_value,
):
    from suiteview.illustration.models.case_store import (
        decode_policy_snapshot, encode_policy_snapshot,
    )

    source = _Source()
    source.tables["LH_POL_MVRY_VAL"][0]["CSV_AMT"] = account_value
    policy = _policy()
    policy.product_type = product
    policy.plancode = plancode
    policy.fund_values = {"SW": 2_000, "M1": 18_000}
    policy.premium_allocations = {"M1": 0.6, "IR": 0.4}
    policy.current_interest_rate = 0.0625
    policy.iul_declared_rate = 0.02
    policy.rollback_snapshots = build_value_rollback_snapshots(source, policy)
    original = deepcopy(policy)
    snapshot, = policy.rollback_snapshots
    assert snapshot.blocking_errors == []
    assert snapshot.fund_values is None
    restored = decode_policy_snapshot(encode_policy_snapshot(policy))
    result = apply_value_rollback(restored, WHEN)
    assert result.account_value == account_value
    assert result.fund_values == {}
    assert result.accumulated_mtp == 4_900
    assert result.accumulated_glp == 15_000
    assert result.premium_allocations == policy.premium_allocations
    assert result.current_interest_rate == 0.0625
    assert result.iul_declared_rate == 0.02
    assert any("total account value only" in note for note in result.rollback_limitations)
    assert policy == original


def test_iul_target_rollbacks_still_reverse_anniversary_glp():
    source = _Source()
    policy = _policy()
    policy.product_type = "IUL"
    policy.valuation_date = date(2027, 1, 15)
    snapshot, = build_value_rollback_snapshots(source, policy)
    assert snapshot.blocking_errors == []
    assert snapshot.accumulated_mtp == 4_500
    assert snapshot.accumulated_glp == 13_800


def test_iul_target_recovery_reports_its_cause_not_missing_loaded_accumulators():
    source = _Source()
    policy = _policy()
    policy.product_type = "IUL"
    source.get_coverages = lambda: [SimpleNamespace(issue_date=date(2026, 9, 1))]
    policy.rollback_snapshots = build_value_rollback_snapshots(source, policy)
    with pytest.raises(ValueError, match="coverage change crosses") as exc:
        apply_value_rollback(policy, WHEN)
    assert "accumulated_mtp is missing" not in str(exc.value)
    assert "accumulated_glp is missing" not in str(exc.value)
    assert "IUL fund" not in str(exc.value)


@pytest.mark.parametrize("mutation,expected", [
    (lambda rows: rows.pop(1), "Same-day"),
    (lambda rows: rows[2].update(TRANS="SN"), "transaction SN"),
    (lambda rows: rows[2].update(FCB0_REV_IND="1"), "Reversed"),
    (lambda rows: rows[2].update(FCB2_REV_APPL_IND=None), "reversal flags"),
    (lambda rows: rows[2].update(GROSS_AMT=None), "GROSS_AMT"),
    (lambda rows: rows[2].update(FEB3_1035_EXCH_IND="1"), "1035"),
    (lambda rows: rows[2].update(ASOF_DT=date(2026, 8, 14)), "Backdated"),
])
def test_unsupported_transaction_or_boundary_blocks_instead_of_guessing(mutation, expected):
    source = _Source()
    mutation(source.tables["FH_FIXED"])
    snapshot, = build_value_rollback_snapshots(source, _policy())
    assert snapshot.premiums_paid_to_date is None
    assert snapshot.cost_basis is None
    assert any(expected in error for error in snapshot.blocking_errors)


def test_database_errors_are_not_converted_to_empty_history():
    source = _Source()
    source.errors["LH_FND_VAL_LOAN"] = "Communication link failure"
    with pytest.raises(RuntimeError, match="LH_FND_VAL_LOAN.*Communication link failure"):
        build_value_rollback_snapshots(source, _policy())


def test_missing_zero_tamra_year_is_not_invented():
    source = _Source()
    source.tables["LH_TAMRA_7_PY_YR"].pop()
    snapshot, = build_value_rollback_snapshots(source, _policy())
    assert snapshot.tamra_7year_contributions is None
    assert any("missing years are not zero" in error for error in snapshot.blocking_errors)


def _loan(fund, preferred, status, principal, interest, when=WHEN):
    return {
        "MVRY_DT": when, "FND_ID_CD": fund, "FND_VAL_PHA_NBR": 1,
        "PRF_LN_IND": preferred, "LN_ITS_AMT_TYP_CD": status,
        "LN_PRI_AMT": principal, "POL_LN_ITS_AMT": interest, "LN_CRG_ITS_RT": 5.7,
    }


def test_exact_dated_loans_keep_regular_preferred_variable_and_interest_status():
    source = _Source()
    source.tables["LH_FND_VAL_LOAN"] = [
        _loan("U1", "0", "0", 100, 5),
        _loan("U2", "1", "0", 200, 10),
        _loan("LZ", "1", "0", 300, 15),
        _loan("U3", "0", "1", 20, None),  # status 1 interest is already principal
        _loan("U1", "0", "0", 9999, 999, date(9999, 12, 31)),
    ]
    snapshot, = build_value_rollback_snapshots(source, _policy())
    assert (snapshot.regular_loan_principal, snapshot.regular_loan_accrued) == (120, 5)
    assert (snapshot.preferred_loan_principal, snapshot.preferred_loan_accrued) == (200, 10)
    assert (snapshot.variable_loan_principal, snapshot.variable_loan_accrued) == (300, 15)
    assert snapshot.variable_loan_charge_rate == pytest.approx(0.057)


def test_sentinel_loan_is_not_a_historical_fallback():
    source = _Source()
    source.tables["LH_FND_VAL_LOAN"] = [
        _loan("U1", "0", "0", 0, 0, date(9999, 12, 31)),
    ]
    snapshot, = build_value_rollback_snapshots(source, _policy())
    assert snapshot.regular_loan_principal is None
    assert any("Exact-date loan" in error for error in snapshot.blocking_errors)


@pytest.mark.parametrize("field", ["ccv_active", "deemed_cash_value"])
def test_other_balance_dependent_products_cannot_reuse_current_state(field):
    policy = _policy()
    setattr(policy, field, 100)
    policy.rollback_snapshots = [_complete_snapshot()]
    with pytest.raises(ValueError, match="Historical"):
        apply_value_rollback(policy, WHEN)


def test_repeated_rollback_keeps_original_six_month_anchor():
    policy = _policy()
    policy.rollback_snapshots = [_complete_snapshot(), _complete_snapshot(date(2026, 7, 15))]
    first = apply_value_rollback(policy, WHEN)
    second = apply_value_rollback(first, date(2026, 7, 15))
    assert second.rollback_source_date == ANCHOR
    assert available_rollback_dates(first) == [WHEN, date(2026, 7, 15)]


def test_service_attaches_captured_snapshots(monkeypatch):
    from tests.test_illustration_policy_service import _FakePolicyInfo, _FakeRates
    from suiteview.illustration.core import illustration_policy_service as service
    from suiteview.illustration.models.plancode_config import PlancodeConfig

    pi = _FakePolicyInfo()
    expected = [_complete_snapshot()]
    monkeypatch.setattr(service, "get_policy_info", lambda *_args: pi)
    monkeypatch.setattr(service, "ULRates", lambda *_args, **_kwargs: _FakeRates())
    monkeypatch.setattr(service, "IndexAssumptionTables", _FakeRates)
    monkeypatch.setattr(service, "load_plancode", lambda _code: PlancodeConfig())
    monkeypatch.setattr(service, "build_value_rollback_snapshots", lambda source, _: expected if source is pi else [])
    result = service.build_illustration_data("TEST", illustration_date=date(2026, 7, 29))
    assert result.rollback_snapshots == expected


def test_cvat_shadow_policy_displays_recoverable_values_but_requires_manual_shadow():
    from suiteview.illustration.core.calc_engine import IllustrationEngine

    source = _Source()
    policy = _policy()
    policy.def_of_life_ins = "CVAT"
    policy.ccv_active = True
    policy.shadow_account_value = 12_345
    source.tables["LH_POL_TARGET"] = [
        row for row in source.tables["LH_POL_TARGET"] if row["TAR_TYP_CD"] != "TA"]
    source.tables["LH_COV_INS_GDL_PRM"] = []
    policy.rollback_snapshots = build_value_rollback_snapshots(source, policy)
    with pytest.raises(ValueError, match="shadow"):
        apply_value_rollback(policy, WHEN)
    preview = apply_value_rollback(policy, WHEN, allow_missing_shadow=True)
    assert preview.account_value == 10_000
    assert preview.accumulated_mtp == 4_900
    assert preview.accumulated_glp == 0
    assert preview.deemed_cash_value is None   # not in DB2 — never faked from the AV
    assert preview.rollback_requires_shadow_value
    with pytest.raises(ValueError, match="shadow"):
        IllustrationEngine().project(preview, months=1)
    supplied = apply_value_rollback(policy, WHEN, shadow_account_value=11_500)
    assert not supplied.rollback_requires_shadow_value
    assert supplied.shadow_account_value == 11_500
    assert any("entered manually" in note for note in supplied.rollback_limitations)
    assert policy.shadow_account_value == 12_345
    assert policy.rollback_snapshots[0].shadow_account_value is None
