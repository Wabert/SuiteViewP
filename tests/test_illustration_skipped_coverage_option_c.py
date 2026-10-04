"""Option C after a skipped-coverage reinstatement returns only the premiums since the latest REN_DT.

Evidence (CyberLife stored NAR, RERUN coverage push 2026-10-04): on all 6 option C policies
with an LH_COV_SKIPPED_PER lapse gap the implied return of premium is the live premiums paid
on or after the latest REN_DT (PB included, PU excluded) less withdrawals since then.
UIP88048 and UE182343 were each reinstated twice and only the latest REN_DT matches.
Continuous reinstatements (no skipped-period row) and never-reinstated policies keep the
lifetime premiums less net withdrawals.
"""
from datetime import date
from types import SimpleNamespace

import pytest

from suiteview.illustration.core import calc_engine
from suiteview.illustration.core.calc_engine import _ending_death_benefit
from suiteview.illustration.core.guideline_calc import calculate_glp_iterative
from suiteview.illustration.core.monthly_deduction import _build_death_benefit_basis
from suiteview.illustration.core.scenario_builder import _reset_issue_values, build_illustration_scenario
from suiteview.illustration.core.skipped_coverage import build_skipped_coverage_periods
from suiteview.illustration.models.case_store import decode_policy_snapshot, encode_policy_snapshot
from suiteview.illustration.models.input_set import RollbackOverrideSet
from suiteview.illustration.models.plancode_config import PlancodeConfig
from suiteview.illustration.models.policy_data import (
    CoverageSegment,
    IllustrationPolicyData,
    SkippedCoveragePeriod,
)


def _txn(day, code, amount, processed="1"):
    raw = {} if processed is None else {"FBB3_PROCD_IND": processed}
    return SimpleNamespace(trans_date=day, trans_code=code, gross_amount=amount, raw_data=raw)


def _period(lapse, reinstated):
    return SimpleNamespace(lapse_date=lapse, reinstatement_date=reinstated)


def _periods(periods, transactions, premiums, withdrawals=0.0, fees=0.0, fee=25.0):
    return build_skipped_coverage_periods(
        periods, transactions, premiums_to_date=premiums, withdrawals_to_date=withdrawals,
        inforce_withdrawal_fees=fees, withdrawal_fee=fee)


def _policy(face, premiums, periods=(), *, valuation=date(2026, 9, 5), withdrawals=0.0, fees=0.0):
    segment = CoverageSegment(
        coverage_phase=1, issue_date=date(2016, 8, 5), issue_age=45, rate_sex="M", rate_class="N",
        face_amount=face, original_face_amount=face, units=face / 1000.0)
    return IllustrationPolicyData(
        plancode="1U145800", db_option="C", face_amount=face, segments=[segment],
        issue_date=date(2016, 8, 5), valuation_date=valuation, illustration_date=valuation,
        policy_year=11, premiums_paid_to_date=premiums, withdrawals_to_date=withdrawals,
        inforce_withdrawal_fees=fees, withdrawal_fee=25.0, skipped_coverage_periods=list(periods))


# UIP88048 (1U145800, face 250,001): lapses 2019-10-06..2019-11-05 and 2020-11-06..2021-01-05.
UIP88048_PERIODS = (
    _period(date(2019, 10, 6), date(2019, 11, 5)),
    _period(date(2020, 11, 6), date(2021, 1, 5)),
)
UIP88048_TRANSACTIONS = (
    _txn(date(2019, 9, 5), "PR", 6_886.16),
    _txn(date(2019, 11, 5), "PU", 1_219.04),
    _txn(date(2019, 11, 5), "PB", 2_363.84),
    _txn(date(2021, 1, 5), "PU", 1_652.84),
    _txn(date(2021, 1, 5), "PB", 1_187.50),
    _txn(date(2021, 2, 5), "PA", 16_000.00),
)


def _uip88048(**kwargs):
    periods = _periods(UIP88048_PERIODS, UIP88048_TRANSACTIONS, 26_437.50)
    return _policy(250_001.0, 26_437.50, periods, **kwargs)


def test_uip88048_option_c_returns_the_premiums_since_the_latest_reinstatement():
    policy = _uip88048()

    assert policy.latest_skipped_coverage_period.reinstatement_date == date(2021, 1, 5)
    assert policy.option_c_premium_base(26_437.50, 0.0) == pytest.approx(17_187.50)
    basis = _build_death_benefit_basis(10_000.0, policy, PlancodeConfig(), 55, 26_437.50)
    # CyberLife's implied DB: face 250,001 + 17,187.50 (SuiteView had + 26,437.50).
    assert round(basis.standard_db, 2) == 267_188.50
    assert round(basis.db_by_coverage["cov1"], 2) == 267_188.50


def test_ue182343_latest_reinstatement_wins_over_the_first():
    """UE182343: 9,983.86 lifetime, 4,454.44 since the first REN_DT, 3,343.67 since the
    latest (= CyberLife's implied ROP)."""
    periods = _periods(
        (_period(date(2024, 8, 22), date(2024, 12, 21)), _period(date(2025, 5, 21), date(2025, 7, 21))),
        (_txn(date(2024, 1, 1), "PR", 5_529.42),
         _txn(date(2024, 12, 21), "PB", 1_110.77), _txn(date(2024, 12, 21), "PU", 3_226.47),
         _txn(date(2025, 7, 21), "PB", 343.67), _txn(date(2025, 7, 21), "PU", 3_900.35),
         _txn(date(2026, 1, 21), "PR", 3_000.00)),
        9_983.86)
    policy = _policy(249_000.0, 9_983.86, periods, valuation=date(2026, 9, 21))

    assert [p.option_c_excluded_amount for p in periods] == [5_529.42, 6_640.19]
    assert policy.option_c_premium_base(9_983.86, 0.0) == pytest.approx(3_343.67)


def test_projected_premiums_and_withdrawals_accumulate_on_top_of_the_reset_base():
    policy = _uip88048(withdrawals=0.0)

    assert policy.option_c_premium_base(26_437.50 + 1_200.0, 0.0) == pytest.approx(18_387.50)
    assert policy.option_c_premium_base(26_437.50 + 1_200.0, 500.0) == pytest.approx(17_887.50)


def test_ending_death_benefit_uses_the_reset_base():
    policy = _uip88048()
    work = SimpleNamespace(
        month_date=date(2026, 10, 5), av=10_000.0,
        prem=SimpleNamespace(premiums_to_date=26_437.50 + 1_200.0), withdrawals_to_date=0.0,
        ded=SimpleNamespace(corridor_rate=0.0), accrual_loan=SimpleNamespace(policy_debt=0.0))

    assert _ending_death_benefit(SimpleNamespace(policy=policy), work) == pytest.approx(250_001.0 + 18_387.50)


def test_withdrawals_since_the_reinstatement_are_subtracted_net_of_fee():
    """Assumption (no evidence case has a withdrawal): withdrawals on or after REN_DT are
    subtracted net of the plan fee; earlier withdrawals belong to the excluded history."""
    periods = _periods(
        (_period(date(2020, 1, 1), date(2020, 3, 1)),),
        (_txn(date(2019, 6, 1), "PR", 4_000.0), _txn(date(2019, 7, 1), "SG", 2_000.0),
         _txn(date(2020, 3, 1), "PB", 500.0), _txn(date(2021, 3, 1), "PR", 3_000.0),
         _txn(date(2022, 3, 1), "SN", 1_000.0)),
        7_500.0, withdrawals=3_000.0, fees=50.0)
    policy = _policy(100_000.0, 7_500.0, periods, withdrawals=3_000.0, fees=50.0)

    # Since REN: premiums 3,500 less the 1,000 withdrawal net of its 25 fee.
    assert policy.option_c_premium_base(7_500.0, 3_000.0) == pytest.approx(2_525.0)


def test_an_unapplied_premium_since_the_reinstatement_is_not_in_the_base():
    """FH_FIXED can hold the next receipt before it is applied (FBB3_PROCD_IND 0, UE000576);
    LH_POL_TOTALS does not count it, so neither does the since-REN sum."""
    pending = UIP88048_TRANSACTIONS + (_txn(date(2026, 9, 20), "PR", 500.0, processed="0"),)
    periods = _periods(UIP88048_PERIODS, pending, 26_437.50)

    assert periods[-1].option_c_excluded_amount == 9_250.00
    assert _policy(250_001.0, 26_437.50, periods).option_c_premium_base(
        26_437.50, 0.0) == pytest.approx(17_187.50)


def test_a_premium_without_the_processed_flag_is_raised():
    rows = UIP88048_TRANSACTIONS + (_txn(date(2026, 9, 20), "PR", 500.0, processed=None),)

    with pytest.raises(ValueError, match="FBB3_PROCD_IND"):
        _periods(UIP88048_PERIODS, rows, 26_937.50)


def test_a_withdrawal_spanning_several_values_phases_is_one_event_with_one_fee():
    """One SN request posts a row per values phase; TOT_WTD_QTY counts it once and
    TOT_WTD_AMT is the GROSS_AMT sum (400-policy read-only check, 2026-10-04)."""
    rows = (
        _txn(date(2019, 6, 1), "PR", 4_000.0), _txn(date(2020, 3, 1), "PB", 500.0),
        _txn(date(2021, 3, 1), "PR", 3_000.0),
        _txn(date(2022, 3, 1), "SN", 600.0), _txn(date(2022, 3, 1), "SN", 425.0),
        _txn(date(2023, 3, 1), "SG", 300.0), _txn(date(2023, 3, 1), "SG", 200.0),
    )
    periods = _periods((_period(date(2020, 1, 1), date(2020, 3, 1)),), rows,
                       7_500.0, withdrawals=1_525.0, fees=50.0)
    policy = _policy(100_000.0, 7_500.0, periods, withdrawals=1_525.0, fees=50.0)

    # Two events (not four rows): 1,525 gross - 2 x 25 = 1,475 net since REN.
    assert periods[0].option_c_excluded_amount == pytest.approx(4_000.0)
    assert policy.option_c_premium_base(7_500.0, 1_525.0) == pytest.approx(3_500.0 - 1_475.0)


def test_continuous_and_never_reinstated_policies_keep_the_lifetime_basis():
    never = _policy(50_000.0, 10_331.0, withdrawals=14_390.0, fees=25.0)
    continuous = _policy(200_000.0, 43_390.34, withdrawals=8_025.0, fees=25.0)

    assert never.latest_skipped_coverage_period is None
    assert never.option_c_premium_base(30_000.0, 14_390.0) == pytest.approx(15_635.0)
    # U0489443: a $0 PB on a reversed lapse, no skipped-period row: lifetime - net WD.
    assert continuous.option_c_premium_base(43_390.34, 8_025.0) == pytest.approx(35_390.34)


def test_a_rollback_before_the_latest_reinstatement_uses_the_history_as_of_that_date():
    """The exclusion of each reinstatement does not depend on the valuation date, so the
    period selected by the (rolled-back) valuation date reproduces CyberLife's basis then."""
    policy = _uip88048(valuation=date(2020, 10, 5))
    assert policy.latest_skipped_coverage_period.reinstatement_date == date(2019, 11, 5)
    # Premiums to date at 2020-10-05: 6,886.16 + 2,363.84; option C = the PB since 2019-11-05.
    assert policy.option_c_premium_base(9_250.00, 0.0) == pytest.approx(2_363.84)

    policy.valuation_date = date(2019, 9, 5)
    assert policy.latest_skipped_coverage_period is None
    assert policy.option_c_premium_base(6_886.16, 0.0) == pytest.approx(6_886.16)


def test_run_from_issue_projects_continuous_coverage():
    policy = _uip88048()
    policy.run_from_issue = True
    assert policy.latest_skipped_coverage_period is None

    policy = _uip88048()
    _reset_issue_values(policy)
    assert policy.skipped_coverage_periods == []


def test_manual_premium_total_is_the_full_option_c_basis():
    policy = _uip88048()

    candidate = build_illustration_scenario(
        policy, rollback_overrides=RollbackOverrideSet(
            policy.valuation_date, record_values={"premiums_paid_to_date": 20_000.0})).projectable_policy

    assert candidate.option_c_premium_base(20_000.0, 0.0) == 20_000.0
    assert [p.reinstatement_date for p in candidate.skipped_coverage_periods] == [
        date(2019, 11, 5), date(2021, 1, 5)]
    assert any("01/05/2021 skipped-coverage reinstatement" in note
               for note in candidate.starting_basis_assumptions)
    assert policy.option_c_premium_base(26_437.50, 0.0) == pytest.approx(17_187.50)


def test_guideline_projection_copy_drops_the_reinstatement_history(monkeypatch):
    seen = []

    class _Engine:
        def project(self, gpolicy, **_kwargs):
            seen.append(gpolicy)
            return [SimpleNamespace(av_end_of_month=gpolicy.face_amount)]

    monkeypatch.setattr(calc_engine, "IllustrationEngine", _Engine)
    policy = _uip88048()
    policy.attained_age, policy.maturity_age = 55, 121

    calculate_glp_iterative(policy, guaranteed_rates=None)

    assert seen and all(g.skipped_coverage_periods == [] for g in seen)
    assert policy.skipped_coverage_periods


def test_skipped_coverage_periods_round_trip_in_a_saved_snapshot():
    policy = _uip88048()

    restored = decode_policy_snapshot(encode_policy_snapshot(policy))

    assert restored.skipped_coverage_periods == policy.skipped_coverage_periods
    assert isinstance(restored.skipped_coverage_periods[0], SkippedCoveragePeriod)
