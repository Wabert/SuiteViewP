"""Guaranteed cash flows must count premium-diverted loan repayments once."""
from copy import deepcopy
from datetime import date

import pytest

from suiteview.illustration.core import calc_engine, guaranteed_projection
from suiteview.illustration.core.bonus_rates import BonusConfig
from suiteview.illustration.core.input_compiler import compile_month_inputs
from suiteview.illustration.core.rate_loader import IllustrationRates
from suiteview.illustration.models.input_set import (
    DatedTransaction,
    IllustrationInputSet,
    IllustrationOptions,
    ScheduledTransaction,
    TransactionKind,
)
from suiteview.illustration.models.plancode_config import PlancodeConfig
from suiteview.illustration.models.policy_data import CoverageSegment, IllustrationPolicyData


@pytest.mark.parametrize("loan_type", ["Arrears", "Advance"])
@pytest.mark.parametrize(
    ("principal", "lumpsum", "explicit_repayment", "divert"),
    [
        (1000.0, 0.0, 0.0, True),
        (1000.0, 20.0, 10.0, True),
        (25.0, 0.0, 0.0, True),
        (1000.0, 0.0, 10.0, False),
    ],
)
def test_guaranteed_replays_actual_loan_cash_once(
    monkeypatch, loan_type, principal, lumpsum, explicit_repayment, divert,
):
    config = PlancodeConfig(
        plancode="LOANLOCK", loan_type=loan_type,
        loan_charge_rate_guar=0.06, pref_loan_charge_rate_guar=0.05,
        premium_load="0", epu_code="0", mfee="0", poav_code="0",
        corridor_code=None, snet_period=0,
    )
    rates = IllustrationRates()
    monkeypatch.setattr(calc_engine, "load_plancode", lambda _: config)
    monkeypatch.setattr(guaranteed_projection, "load_plancode", lambda _: config)
    monkeypatch.setattr(guaranteed_projection, "load_rates", lambda *a, **kw: rates)
    policy = IllustrationPolicyData(
        plancode="LOANLOCK", issue_date=date(2000, 4, 6),
        valuation_date=date(2029, 3, 6), duration=348,
        issue_age=43, attained_age=71, maturity_age=95,
        policy_year=29, policy_month=12, face_amount=25000.0, units=25.0,
        db_option="A", account_value=10000.0, glp=1000.0,
        regular_loan_principal=principal, modal_premium=33.25,
        billing_frequency=1, current_interest_rate=0.0,
        guaranteed_interest_rate=0.0,
        segments=[CoverageSegment(
            coverage_phase=1, issue_date=date(2000, 4, 6),
            face_amount=25000.0, units=25.0,
        )],
    )
    original = deepcopy(policy)
    inputs = IllustrationInputSet(
        scheduled_transactions=[ScheduledTransaction(
            kind=TransactionKind.PREMIUM, policy_year=1, amount=33.25, mode="M",
        )],
        dated_transactions=[
            DatedTransaction(
                kind=TransactionKind.PREMIUM,
                effective_date=date(2029, 4, 6), amount=lumpsum,
            ),
            DatedTransaction(
                kind=TransactionKind.LOAN_REPAYMENT,
                effective_date=date(2029, 4, 6), amount=explicit_repayment,
            ),
        ],
    )
    options = IllustrationOptions(
        apply_prem_to_loan=divert, conform_to_tefra=False, conform_to_tamra=False,
    )
    engine = calc_engine.IllustrationEngine()
    for timing in calc_engine.ProjectionTiming:
        current = engine.project(
            policy, months=6, future_inputs=inputs, timing=timing,
            options=options, rates_override=rates, bonus_override=BonusConfig(),
        )
        assert len(current) == 7
        first = current[1]
        if principal == 1000.0:
            expected = (33.25 + lumpsum if divert else 0.0) + explicit_repayment
            assert first.applied_loan_repayment == pytest.approx(expected)
            assert first.loan_repay_from_prem == pytest.approx(
                33.25 + lumpsum if divert else 0.0)
        else:
            assert 0 < first.applied_loan_repayment < 33.25
            assert first.gross_premium == pytest.approx(33.25 - first.applied_loan_repayment)
        locked = guaranteed_projection.lock_values(policy, current, inputs)
        compiled = compile_month_inputs(policy, locked, 6)
        for row in current[1:]:
            assert compiled[row.duration].loan_repayment == pytest.approx(row.applied_loan_repayment)

        guaranteed = engine.project(
            policy, months=6, future_inputs=locked, timing=timing,
            options=guaranteed_projection.guaranteed_options(options),
            rates_override=rates, bonus_override=BonusConfig(),
        )
        if timing == calc_engine.ProjectionTiming.ILLUSTRATION:
            guaranteed = guaranteed_projection.run_guaranteed_projection(
                policy, current, base_options=options, base_future_inputs=inputs,
                engine=engine,
            )
        assert len(guaranteed) == len(current)
        for cur, guar in zip(current[1:], guaranteed[1:]):
            assert guar.applied_loan_repayment == pytest.approx(cur.applied_loan_repayment)
            assert guar.gross_premium == pytest.approx(cur.gross_premium)
            assert guar.rg_loan_princ == pytest.approx(cur.rg_loan_princ)
            assert guar.rg_loan_accrued == pytest.approx(cur.rg_loan_accrued)
            assert guar.loan_repay_from_prem == 0.0
            assert guar.loan_cap_repay["Arrears - Requested Loan Repayment"] == pytest.approx(
                cur.applied_loan_repayment)
            assert guar.loan_cap_repay["TotalLoanReduction"] == pytest.approx(
                cur.loan_cap_repay["TotalLoanReduction"])
            assert guar.premium_outlay + guar.applied_loan_repayment == pytest.approx(
                cur.premium_outlay + cur.applied_loan_repayment)
    assert policy == original
