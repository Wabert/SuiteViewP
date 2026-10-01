"""Conservative repayment priority shared by inputs, solves and projections."""

from copy import deepcopy
from datetime import date

import pytest

from suiteview.illustration.core import calc_engine, guaranteed_projection
from suiteview.illustration.core.bonus_rates import BonusConfig
from suiteview.illustration.core.loan_handler import (
    LoanState,
    LoanStepInput,
    repay_loan,
)
from suiteview.illustration.core.rate_loader import IllustrationRates
from suiteview.illustration.core.solve_loan_payoff import solve_loan_payoff
from suiteview.illustration.core.target_premium import TargetPremiumResult
from suiteview.illustration.models.input_set import (
    DatedTransaction,
    IllustrationInputSet,
    IllustrationOptions,
    TransactionKind,
)
from suiteview.illustration.models.plancode_config import PlancodeConfig
from suiteview.illustration.models.policy_data import (
    CoverageSegment,
    IllustrationPolicyData,
)


def _buckets(loan):
    return (
        loan.pf_loan_accrued, loan.rg_loan_accrued,
        loan.pf_loan_princ, loan.rg_loan_princ,
        loan.vbl_loan_accrued, loan.vbl_loan_princ,
    )


@pytest.mark.parametrize("amount,expected", [
    (0, (10, 20, 40, 100, 5, 30)),
    (5, (5, 20, 40, 100, 5, 30)),
    (10, (0, 20, 40, 100, 5, 30)),
    (15, (0, 15, 40, 100, 5, 30)),
    (30, (0, 0, 40, 100, 5, 30)),
    (50, (0, 0, 20, 100, 5, 30)),
    (70, (0, 0, 0, 100, 5, 30)),
    (100, (0, 0, 0, 70, 5, 30)),
    (170, (0, 0, 0, 0, 5, 30)),
    (173, (0, 0, 0, 0, 2, 30)),
    (175, (0, 0, 0, 0, 0, 30)),
    (200, (0, 0, 0, 0, 0, 5)),
    (205, (0, 0, 0, 0, 0, 0)),
    (250, (0, 0, 0, 0, 0, 0)),
])
@pytest.mark.parametrize("source", ["input", "lumpsum", "scheduled", "mixed"])
def test_repayment_priority_at_every_bucket_boundary(amount, expected, source):
    cap = LoanState(
        pf_loan_accrued=10, rg_loan_accrued=20,
        pf_loan_princ=40, rg_loan_princ=100,
        vbl_loan_accrued=5, vbl_loan_princ=30,
    )
    original = deepcopy(cap)
    requested, lump, scheduled = {
        "input": (amount, 0, 0),
        "lumpsum": (0, amount, 0),
        "scheduled": (0, 0, amount),
        "mixed": (amount / 2, amount / 4, amount / 4),
    }[source]
    result = repay_loan(LoanStepInput(
        loan=cap, requested_amount=requested, config=PlancodeConfig(loan_type="Arrears"),
        adv_reg_factor=0, adv_pref_factor=0,
        prem_to_loan_from_lumpsum=lump, prem_to_loan_from_scheduled=scheduled,
    ))
    assert _buckets(result.loan_state) == expected
    assert result.applied_repayment == min(amount, 205)
    assert result.detail["LNRepayLeftOver"] == max(0, amount - 205)
    assert result.detail["TotalLoanReduction"] == result.applied_repayment
    assert result.loan_state.policy_debt == 205 - result.applied_repayment
    assert cap == original


@pytest.mark.parametrize("amount,expected", [
    (30, (10, 20, 10, 100, 5, 30)),
    (140, (10, 20, 0, 0, 5, 30)),
    (150, (0, 20, 0, 0, 5, 30)),
    (170, (0, 0, 0, 0, 5, 30)),
    (190, (0, 0, 0, 0, 5, 10)),
    (205, (0, 0, 0, 0, 0, 0)),
])
def test_principal_first_repayment_pays_principal_before_accrued(amount, expected):
    # E03: CyberLife applies a PL repayment to principal while the accrued
    # interest keeps running; the option is off by default (interest first).
    cap = LoanState(
        pf_loan_accrued=10, rg_loan_accrued=20,
        pf_loan_princ=40, rg_loan_princ=100,
        vbl_loan_accrued=5, vbl_loan_princ=30,
    )
    result = repay_loan(LoanStepInput(
        loan=cap, requested_amount=amount, config=PlancodeConfig(loan_type="Arrears"),
        principal_first=True,
    ))
    assert _buckets(result.loan_state) == expected
    assert result.applied_repayment == amount
    assert IllustrationOptions().loan_repay_principal_first is False


def test_principal_first_option_reaches_the_projection(projection_basis):
    policy, _ = projection_basis
    inputs = IllustrationInputSet(dated_transactions=[
        DatedTransaction(TransactionKind.LOAN_REPAYMENT, date(2026, 7, 15), 50),
    ])
    options = IllustrationOptions(
        conform_to_tefra=False, conform_to_tamra=False, loan_repay_principal_first=True,
    )
    states = calc_engine.IllustrationEngine().project(
        policy, months=1, future_inputs=inputs, options=options)
    assert _buckets(states[1]) == (10, 20, 0, 90, 5, 30)


@pytest.fixture
def projection_basis(monkeypatch):
    config = PlancodeConfig(
        plancode="LOANORDER", loan_type="Arrears",
        loan_charge_rate_guar=0, pref_loan_charge_rate_guar=0,
        premium_load="0", epu_code="0", mfee="0", poav_code="0",
        corridor_code=None, snet_period=0,
    )
    rates = IllustrationRates()
    monkeypatch.setattr(calc_engine, "load_plancode", lambda _: config)
    monkeypatch.setattr(calc_engine, "load_rates", lambda *a, **kw: rates)
    monkeypatch.setattr(calc_engine, "load_bonus_config", lambda *a: BonusConfig())
    monkeypatch.setattr(
        calc_engine, "compute_target_premiums", lambda *a, **kw: TargetPremiumResult(),
    )
    monkeypatch.setattr(guaranteed_projection, "load_plancode", lambda _: config)
    monkeypatch.setattr(guaranteed_projection, "load_rates", lambda *a, **kw: rates)
    policy = IllustrationPolicyData(
        plancode="LOANORDER", issue_date=date(2020, 1, 15),
        valuation_date=date(2026, 6, 15), duration=78,
        issue_age=40, attained_age=46, maturity_age=95,
        policy_year=7, policy_month=6, face_amount=25000, units=25,
        db_option="A", account_value=10000, glp=1000,
        regular_loan_principal=100, regular_loan_accrued=20,
        preferred_loan_principal=40, preferred_loan_accrued=10,
        variable_loan_principal=30, variable_loan_accrued=5,
        current_interest_rate=0, guaranteed_interest_rate=0,
        segments=[CoverageSegment(
            coverage_phase=1, issue_date=date(2020, 1, 15),
            face_amount=25000, units=25,
        )],
    )
    return policy, config


@pytest.mark.parametrize("timing", list(calc_engine.ProjectionTiming))
@pytest.mark.parametrize("premium", [0, 20, 50])
def test_current_and_guaranteed_share_repayment_priority(projection_basis, timing, premium):
    policy, _ = projection_basis
    original = deepcopy(policy)
    inputs = IllustrationInputSet(dated_transactions=[
        DatedTransaction(TransactionKind.PREMIUM, date(2026, 7, 15), premium),
        DatedTransaction(TransactionKind.LOAN_REPAYMENT, date(2026, 7, 15), 50 - premium),
    ])
    options = IllustrationOptions(
        apply_prem_to_loan=True, conform_to_tefra=False, conform_to_tamra=False,
    )
    engine = calc_engine.IllustrationEngine()
    current = engine.project(policy, months=2, future_inputs=inputs, options=options, timing=timing)
    locked = guaranteed_projection.lock_values(policy, current, inputs)
    guaranteed = engine.project(
        policy, months=2, future_inputs=locked, timing=timing,
        options=guaranteed_projection.guaranteed_options(options),
    )
    for states in (current, guaranteed):
        assert _buckets(states[0]) == (10, 20, 40, 100, 5, 30)
        assert _buckets(states[1]) == (0, 0, 20, 100, 5, 30)
        assert states[1].applied_loan_repayment == 50
        assert states[1].loan_cap_repay["TotalLoanReduction"] == 50
    assert policy == original


def test_payoff_solve_uses_preferred_first_with_unequal_rates(projection_basis):
    policy, config = projection_basis
    config.loan_charge_rate_guar = 0.12
    config.pref_loan_charge_rate_guar = 0.04
    original = deepcopy(policy)
    dates = [date(2026, 7, 15), date(2026, 8, 15)]
    check = date(2026, 9, 15)
    result = solve_loan_payoff(policy, repayment_dates=dates, check_date=check)

    def project(amount):
        return calc_engine.IllustrationEngine().project(
            policy, months=3, future_inputs=IllustrationInputSet(dated_transactions=[
                DatedTransaction(TransactionKind.LOAN_REPAYMENT, when, amount)
                for when in dates
            ]), stop_on_lapse=False,
        )

    solved = project(result.repayment)
    first = solved[1]
    assert first.pf_loan_accrued == 0
    assert first.rg_loan_accrued == 0
    assert first.pf_loan_princ == 0
    assert first.rg_loan_princ > 0
    assert sum(_buckets(solved[-1])) == pytest.approx(0, abs=0.005)
    assert sum(_buckets(project(result.repayment - 0.02)[-1])) > 0.005
    assert policy == original
