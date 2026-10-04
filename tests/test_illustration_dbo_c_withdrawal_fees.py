"""Option C (return of premium) adds premiums less NET withdrawals.

CyberLife's LH_POL_TOTALS.TOT_WTD_AMT is gross of the per-withdrawal fee; its option C
death benefit is not (1U145500 UIP50722: six withdrawals, CyberLife's stored NAR implies
premiums 42,723.00 - withdrawals 23,972.55 + 6 x 25 = 18,900.45).
"""
from datetime import date

from suiteview.illustration.core.monthly_deduction import _build_death_benefit_basis
from suiteview.illustration.core.scenario_builder import _reset_issue_values, build_illustration_scenario
from suiteview.illustration.models.input_set import RollbackOverrideSet
from suiteview.illustration.models.plancode_config import PlancodeConfig
from suiteview.illustration.models.policy_data import CoverageSegment, IllustrationPolicyData


def _policy(fees):
    segment = CoverageSegment(
        coverage_phase=1, issue_date=date(2015, 2, 2), issue_age=64, rate_sex="M", rate_class="N",
        face_amount=50_000.0, original_face_amount=50_000.0, units=50.0)
    return IllustrationPolicyData(
        plancode="1U145500", db_option="C", face_amount=50_000.0, segments=[segment],
        withdrawals_to_date=23_972.55, inforce_withdrawal_fees=fees)


def test_option_c_adds_premiums_less_net_withdrawals():
    basis = _build_death_benefit_basis(
        1108.60, _policy(150.0), PlancodeConfig(), 76, 42_723.00, corridor_rate=1.05)

    assert round(basis.standard_db, 2) == 68_900.45
    assert round(basis.db_by_coverage["cov1"], 2) == 68_900.45


def test_option_c_without_withdrawal_fees_is_unchanged():
    basis = _build_death_benefit_basis(
        1108.60, _policy(0.0), PlancodeConfig(), 76, 42_723.00, corridor_rate=1.05)

    assert round(basis.standard_db, 2) == 68_750.45


def test_net_withdrawals_never_go_below_zero():
    policy = _policy(150.0)

    assert policy.net_withdrawals(23_972.55) == 23_822.55
    assert policy.net_withdrawals(100.0) == 0.0
    basis = _build_death_benefit_basis(
        1108.60, _policy(150.0), PlancodeConfig(), 76, 42_723.00, corridor_rate=1.05)
    policy.withdrawals_to_date = 0.0
    zero = _build_death_benefit_basis(1108.60, policy, PlancodeConfig(), 76, 42_723.00, corridor_rate=1.05)
    assert round(basis.standard_db, 2) == 68_900.45
    assert round(zero.standard_db, 2) == 92_723.00   # face + premiums, not + premiums + fees


def test_manual_withdrawals_to_date_is_net_of_fees():
    """An Edit Record total is the net withdrawals: the recorded fees are not subtracted again."""
    when = date(2026, 10, 2)
    policy = _policy(150.0)
    policy.valuation_date = policy.illustration_date = when
    policy.issue_date, policy.policy_year = date(2015, 2, 2), 12

    candidate = build_illustration_scenario(
        policy, rollback_overrides=RollbackOverrideSet(
            when, record_values={"withdrawals_to_date": 0.0})).projectable_policy

    assert candidate.withdrawals_to_date == 0.0
    assert candidate.inforce_withdrawal_fees == 0.0
    assert candidate.net_withdrawals(candidate.withdrawals_to_date) == 0.0
    assert any("net of withdrawal fees" in note for note in candidate.starting_basis_assumptions)
    assert policy.inforce_withdrawal_fees == 150.0


def test_run_from_issue_clears_the_inforce_withdrawal_fees():
    policy = _policy(150.0)

    _reset_issue_values(policy)

    assert (policy.withdrawals_to_date, policy.inforce_withdrawal_fees) == (0.0, 0.0)
