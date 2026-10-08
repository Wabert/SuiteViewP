"""CyberLife-timing months process dated premiums and withdrawals in date order.

Robert's decision #88 (option 3, 2026-10-07): under CYBERLIFE_MONTHLIVERSARY
timing a premium received on or before the month's withdrawal date is applied
before the withdrawal, so it counts in the maximum withdrawal (01_U1008132:
premium 9/9, maximum withdrawal 9/15, both bucketed to the 9/17 monthiversary).
ILLUSTRATION timing keeps the RERUN withdrawal-first order.
"""
from __future__ import annotations

from datetime import date

import pytest

from suiteview.illustration.core import calc_engine
from suiteview.illustration.core.bonus_rates import BonusConfig
from suiteview.illustration.core.calc_engine import (
    CYBERLIFE_MONTHLIVERSARY_TIMING,
    ILLUSTRATION_TIMING,
    IllustrationEngine,
    ProjectionTiming,
)
from suiteview.illustration.core.rate_loader import IllustrationRates
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

ISSUE = date(2026, 8, 16)
BUCKET = date(2026, 9, 16)
FEE = 25.0


def _rates() -> IllustrationRates:
    zero = [0.0] * 240
    return IllustrationRates(
        coi=zero, segment_coi={1: zero}, epu=zero, segment_epu={1: zero},
        scr=zero, segment_scr={1: zero}, tpp=zero, epp=zero,
    )


def _policy(*, glp: float = 1_000_000.0, premiums_paid: float = 0.0) -> IllustrationPolicyData:
    return IllustrationPolicyData(
        policy_number="DATEORDER",
        plancode="DATEORDER",
        def_of_life_ins="GPT",
        issue_date=ISSUE,
        valuation_date=ISSUE,
        issue_age=45,
        attained_age=45,
        maturity_age=121,
        policy_year=1,
        policy_month=1,
        duration=1,
        face_amount=100_000.0,
        units=100.0,
        db_option="B",
        account_value=1_000.0,
        current_interest_rate=0.06,
        guaranteed_interest_rate=0.02,
        glp=glp,
        gsp=glp,
        premiums_paid_to_date=premiums_paid,
        cost_basis=premiums_paid,
        rollback_date=ISSUE,
        segments=[CoverageSegment(
            coverage_phase=1, issue_date=ISSUE, issue_age=45, rate_sex="M",
            rate_class="N", face_amount=100_000.0, original_face_amount=100_000.0,
            units=100.0,
        )],
    )


@pytest.fixture
def rates(monkeypatch):
    config = PlancodeConfig(
        plancode="DATEORDER", prem_flat_load=0.0, gint=0.02, dbd=0.0,
        lapse_value="AV", interest_method="ExactDays", withdrawal_fee=FEE,
    )
    rates = _rates()
    monkeypatch.setattr(calc_engine, "load_plancode", lambda _plancode: config)
    monkeypatch.setattr(calc_engine, "load_bonus_config", lambda *_args: BonusConfig())
    monkeypatch.setattr(calc_engine.IllustrationEngine, "_load_rates", lambda *_args: rates)
    monkeypatch.setattr(calc_engine, "compute_target_premiums", lambda *_a, **_k: TargetPremiumResult())
    monkeypatch.setattr(calc_engine, "build_target_detail_snapshots", lambda *_a, **_k: ({}, {}))
    monkeypatch.setattr(calc_engine, "_coverage_after_change_snapshot", lambda *_a, **_k: {})
    return rates


def _flow(kind: TransactionKind, actual: date, amount: float) -> DatedTransaction:
    return DatedTransaction(kind, BUCKET, amount, metadata={"actual_date": actual.isoformat()})


def _project(rates, flows, *, timing=ProjectionTiming.CYBERLIFE_MONTHLIVERSARY,
             policy=None, tefra=False):
    return IllustrationEngine().project(
        policy or _policy(),
        months=1,
        future_inputs=IllustrationInputSet(dated_transactions=list(flows)),
        timing=timing,
        stop_on_lapse=False,
        options=IllustrationOptions(conform_to_tefra=tefra, conform_to_tamra=False),
        rates_override=rates,
        bonus_override=BonusConfig(),
    )[1]


def _withdrawal_first(monkeypatch, rates, flows, **kwargs):
    with monkeypatch.context() as patch:
        patch.setattr(calc_engine, "premium_precedes_withdrawal", lambda *_a: False)
        return _project(rates, flows, **kwargs)


def _comparable(state) -> dict:
    return {
        key: value for key, value in vars(state).items()
        if isinstance(value, (int, float)) and not isinstance(value, bool)
    }


def test_only_cyberlife_timing_orders_cash_flows_by_date():
    assert CYBERLIFE_MONTHLIVERSARY_TIMING.cash_flows_in_date_order is True
    assert ILLUSTRATION_TIMING.cash_flows_in_date_order is False


@pytest.mark.parametrize("premium_day", [date(2026, 9, 1), date(2026, 9, 10)])
def test_premium_on_or_before_withdrawal_counts_in_maximum(monkeypatch, rates, premium_day):
    flows = [
        _flow(TransactionKind.PREMIUM, premium_day, 500.0),
        _flow(TransactionKind.WITHDRAWAL, date(2026, 9, 10), 1_300.0),
    ]
    state = _project(rates, flows)
    old = _withdrawal_first(monkeypatch, rates, flows)

    interest_av = old.av_post_withdrawal + old.gross_withdrawal
    assert old.max_net_withdrawal == pytest.approx(interest_av - FEE)
    assert old.applied_net_withdrawal == pytest.approx(interest_av - FEE)  # capped

    assert state.max_net_withdrawal == pytest.approx(1_300.0)  # DBO B: min(CSV - fee, request)
    assert interest_av + 500.0 - FEE > 1_300.0 > interest_av - FEE
    assert state.applied_net_withdrawal == pytest.approx(1_300.0)
    assert state.gross_withdrawal == pytest.approx(1_300.0 + FEE)
    assert state.av_post_withdrawal == pytest.approx(interest_av + 500.0 - 1_325.0)
    assert state.av_after_premium == pytest.approx(state.av_post_withdrawal)
    assert state.net_premium == pytest.approx(500.0)
    # The premium enters the cost basis before the withdrawal reduces it.
    assert state.cost_basis_before_wd == pytest.approx(500.0)
    assert state.cost_basis_after_wd == pytest.approx(500.0 - 1_300.0)
    assert state.cost_basis == pytest.approx(500.0 - 1_300.0)
    assert state.premiums_to_date == pytest.approx(500.0)
    assert state.withdrawals_to_date == pytest.approx(1_300.0)


def test_uncapped_month_ends_with_the_same_values_in_either_order(monkeypatch, rates):
    flows = [
        _flow(TransactionKind.PREMIUM, date(2026, 9, 1), 500.0),
        _flow(TransactionKind.WITHDRAWAL, date(2026, 9, 10), 300.0),
    ]
    state = _project(rates, flows)
    old = _withdrawal_first(monkeypatch, rates, flows)
    for field in ("av_end_of_month", "interest_credited", "net_premium",
                  "gross_withdrawal", "premiums_to_date", "withdrawals_to_date",
                  "cost_basis", "total_deduction"):
        assert getattr(state, field) == pytest.approx(getattr(old, field)), field
    assert state.max_net_withdrawal == pytest.approx(300.0)


def test_maximum_withdrawal_gains_the_earlier_net_premium(monkeypatch, rates):
    flows = [
        _flow(TransactionKind.PREMIUM, date(2026, 9, 1), 500.0),
        _flow(TransactionKind.WITHDRAWAL, date(2026, 9, 10), 5_000.0),
    ]
    state = _project(rates, flows)
    old = _withdrawal_first(monkeypatch, rates, flows)
    assert state.max_net_withdrawal == pytest.approx(old.max_net_withdrawal + 500.0)
    assert state.applied_net_withdrawal == pytest.approx(state.max_net_withdrawal)
    assert state.av_post_withdrawal == pytest.approx(0.0, abs=1e-9)


@pytest.mark.parametrize("flows", [
    # Premium after the withdrawal.
    [_flow(TransactionKind.PREMIUM, date(2026, 9, 12), 500.0),
     _flow(TransactionKind.WITHDRAWAL, date(2026, 9, 10), 1_300.0)],
    # One premium before and one after: the month keeps the RERUN order.
    [_flow(TransactionKind.PREMIUM, date(2026, 9, 1), 250.0),
     _flow(TransactionKind.PREMIUM, date(2026, 9, 12), 250.0),
     _flow(TransactionKind.WITHDRAWAL, date(2026, 9, 10), 1_300.0)],
    # A loan repayment after the withdrawal holds the premium back too.
    [_flow(TransactionKind.PREMIUM, date(2026, 9, 1), 500.0),
     _flow(TransactionKind.LOAN_REPAYMENT, date(2026, 9, 12), 10.0),
     _flow(TransactionKind.WITHDRAWAL, date(2026, 9, 10), 1_300.0)],
])
def test_premium_after_withdrawal_keeps_withdrawal_first(monkeypatch, rates, flows):
    state = _project(rates, flows)
    old = _withdrawal_first(monkeypatch, rates, flows)
    assert _comparable(state) == _comparable(old)
    assert state.applied_net_withdrawal < 1_300.0


def test_illustration_timing_keeps_withdrawal_first(monkeypatch, rates):
    flows = [
        _flow(TransactionKind.PREMIUM, date(2026, 9, 1), 500.0),
        _flow(TransactionKind.WITHDRAWAL, date(2026, 9, 10), 1_300.0),
    ]
    calls = []
    real = calc_engine.premium_precedes_withdrawal

    def spy(ctx, convention):
        calls.append(real(ctx, convention))
        return calls[-1]

    monkeypatch.setattr(calc_engine, "premium_precedes_withdrawal", spy)
    state = _project(rates, flows, timing=ProjectionTiming.ILLUSTRATION)
    assert calls and not any(calls)
    old = _withdrawal_first(monkeypatch, rates, flows, timing=ProjectionTiming.ILLUSTRATION)
    assert _comparable(state) == _comparable(old)
    assert state.applied_net_withdrawal < 1_300.0


def test_premium_first_uses_guideline_room_before_the_withdrawal(monkeypatch, rates):
    # GSP/GLP 2,400 with 2,100 paid: 300 of room before the withdrawal and
    # 300 + 1,000 after it. CyberLife received the premium first.
    policy_kwargs = dict(glp=2_400.0, premiums_paid=2_100.0)
    flows = [
        _flow(TransactionKind.PREMIUM, date(2026, 9, 1), 500.0),
        _flow(TransactionKind.WITHDRAWAL, date(2026, 9, 10), 1_000.0),
    ]
    state = _project(rates, flows, policy=_policy(**policy_kwargs), tefra=True)
    old = _withdrawal_first(
        monkeypatch, rates, flows, policy=_policy(**policy_kwargs), tefra=True)
    assert old.gross_premium == pytest.approx(500.0)
    assert state.gross_premium == pytest.approx(300.0)
    assert state.guideline_forceout == pytest.approx(0.0)
    assert state.applied_net_withdrawal == pytest.approx(1_000.0)
