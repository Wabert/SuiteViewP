from __future__ import annotations

from datetime import date

import pytest

from suiteview.illustration.core import calc_engine
from suiteview.illustration.core.bonus_rates import BonusConfig
from suiteview.illustration.core.calc_engine import (
    IllustrationEngine,
    ProjectionTiming,
)
from suiteview.illustration.core.interest_calc import interest_days
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


def _config(*, interest_method: str = "ExactDays") -> PlancodeConfig:
    return PlancodeConfig(
        plancode="TIMING",
        premium_load="0",
        prem_flat_load=0.0,
        epu_code="0",
        mfee="0",
        poav_code="0",
        corridor_code=None,
        gint=0.02,
        dbd=0.0,
        snet_period=0,
        lapse_value="AV",
        interest_method=interest_method,
    )


def _rates() -> IllustrationRates:
    zero = [0.0] * 240
    return IllustrationRates(
        coi=zero,
        segment_coi={1: zero},
        epu=zero,
        segment_epu={1: zero},
        scr=zero,
        segment_scr={1: zero},
        mfee=zero,
        tpp=zero,
        epp=zero,
    )


def _segment(issue: date) -> CoverageSegment:
    return CoverageSegment(
        coverage_phase=1,
        issue_date=issue,
        issue_age=45,
        rate_sex="M",
        rate_class="N",
        face_amount=100_000.0,
        original_face_amount=100_000.0,
        units=100.0,
    )


def _policy(
    *,
    issue: date = date(2020, 3, 7),
    valuation: date = date(2026, 3, 7),
    account_value: float = 1_000.0,
    run_from_issue: bool = False,
    rollback_date: date | None = None,
) -> IllustrationPolicyData:
    months = (
        (valuation.year - issue.year) * 12
        + valuation.month - issue.month
    )
    return IllustrationPolicyData(
        policy_number="TIMING",
        plancode="TIMING",
        def_of_life_ins="GPT",
        issue_date=issue,
        valuation_date=valuation,
        issue_age=45,
        attained_age=45 + months // 12,
        maturity_age=121,
        policy_year=months // 12 + 1,
        policy_month=months % 12 + 1,
        duration=months + 1,
        face_amount=100_000.0,
        units=100.0,
        db_option="A",
        account_value=account_value,
        current_interest_rate=0.06,
        guaranteed_interest_rate=0.02,
        glp=1_000_000.0,
        gsp=1_000_000.0,
        run_from_issue=run_from_issue,
        rollback_date=rollback_date,
        segments=[_segment(issue)],
    )


@pytest.fixture
def patched_engine(monkeypatch):
    config = _config()
    rates = _rates()
    monkeypatch.setattr(calc_engine, "load_plancode", lambda _plancode: config)
    monkeypatch.setattr(calc_engine, "load_bonus_config", lambda *_args: BonusConfig())
    monkeypatch.setattr(calc_engine.IllustrationEngine, "_load_rates", lambda *_args: rates)
    monkeypatch.setattr(calc_engine, "compute_target_premiums", lambda *_a, **_k: TargetPremiumResult())
    monkeypatch.setattr(calc_engine, "build_target_detail_snapshots", lambda *_a, **_k: ({}, {}))
    monkeypatch.setattr(calc_engine, "_coverage_after_change_snapshot", lambda *_a, **_k: {})
    return config, rates


@pytest.mark.parametrize(
    ("start", "end", "opening", "expected"),
    [
        (date(2026, 3, 7), date(2026, 4, 7), 16_517.67, 81.95),
        (date(2026, 4, 7), date(2026, 5, 7), 16_587.19, 79.63),
        (date(2026, 5, 7), date(2026, 6, 7), 16_654.35, 82.62),
        (date(2026, 6, 7), date(2026, 7, 7), 16_724.44, 80.29),
        (date(2026, 7, 7), date(2026, 8, 7), 16_792.15, 83.31),
        (date(2026, 8, 7), date(2026, 9, 7), 16_862.81, 83.66),
    ],
)
def test_cyberlife_timing_uses_prior_span_days(
    patched_engine, start, end, opening, expected,
):
    _config_obj, rates = patched_engine
    policy = _policy(issue=date(2020, 3, 7), valuation=start, account_value=opening)
    states = IllustrationEngine().project(
        policy,
        months=1,
        timing=ProjectionTiming.CYBERLIFE_MONTHLIVERSARY,
        stop_on_lapse=False,
        options=IllustrationOptions(conform_to_tefra=False, conform_to_tamra=False),
        rates_override=rates,
        bonus_override=BonusConfig(),
    )
    assert round(states[1].interest_credited, 2) == expected
    assert states[1].days_in_month == interest_days(start, end)


def test_monthly_interest_method_keeps_monthly_compounding(monkeypatch, patched_engine):
    config, rates = patched_engine
    monkeypatch.setattr(config, "interest_method", "MonthlyCompounding")
    policy = _policy(valuation=date(2026, 3, 7), account_value=16_517.67)
    states = IllustrationEngine().project(
        policy,
        months=1,
        timing=ProjectionTiming.CYBERLIFE_MONTHLIVERSARY,
        stop_on_lapse=False,
        options=IllustrationOptions(conform_to_tefra=False, conform_to_tamra=False),
        rates_override=rates,
        bonus_override=BonusConfig(),
    )
    monthly_interest = 16_517.67 * ((1.06) ** (1 / 12) - 1)
    assert states[1].interest_credited == pytest.approx(monthly_interest)


def test_day_31_monthliversaries_are_issue_anchored(patched_engine):
    _config_obj, rates = patched_engine
    policy = _policy(
        issue=date(2023, 7, 31),
        valuation=date(2024, 3, 31),
    )
    states = IllustrationEngine().project(
        policy,
        months=5,
        timing=ProjectionTiming.CYBERLIFE_MONTHLIVERSARY,
        stop_on_lapse=False,
        options=IllustrationOptions(conform_to_tefra=False, conform_to_tamra=False),
        rates_override=rates,
        bonus_override=BonusConfig(),
    )
    assert [state.date for state in states[1:]] == [
        date(2024, 4, 30),
        date(2024, 5, 31),
        date(2024, 6, 30),
        date(2024, 7, 31),
        date(2024, 8, 31),
    ]


@pytest.mark.parametrize("timing", list(ProjectionTiming))
def test_clamped_valuation_month_is_not_repeated(patched_engine, timing):
    # Issue 7/31, valuation on the clamped monthliversary 2/29. The loader once
    # counted only 6 completed months there (duration 7), so the first projected
    # month landed on 2/29 again with 0 interest days and a second deduction.
    from suiteview.illustration.core.illustration_policy_service import _completed_months

    _config_obj, rates = patched_engine
    issue, valuation = date(2023, 7, 31), date(2024, 2, 29)
    assert _completed_months(issue, valuation) == 7
    assert _completed_months(issue, date(2024, 2, 28)) == 6
    policy = _policy(issue=issue, valuation=valuation)
    assert policy.duration == _completed_months(issue, valuation) + 1
    if timing is ProjectionTiming.CYBERLIFE_MONTHLIVERSARY:
        policy.duration = 7  # a stale duration must not drive the next MV date
    states = IllustrationEngine().project(
        policy,
        months=2,
        timing=timing,
        stop_on_lapse=False,
        options=IllustrationOptions(conform_to_tefra=False, conform_to_tamra=False),
        rates_override=rates,
        bonus_override=BonusConfig(),
    )
    assert [state.date for state in states] == [
        date(2024, 2, 29), date(2024, 3, 31), date(2024, 4, 30)]
    assert all(state.days_in_month > 0 for state in states[1:])


@pytest.mark.parametrize(
    ("issue", "valuation", "expected"),
    [
        (
            date(2024, 1, 29),
            date(2024, 1, 29),
            [date(2024, 2, 29), date(2024, 3, 29)],
        ),
        (
            date(2023, 1, 30),
            date(2023, 1, 30),
            [date(2023, 2, 28), date(2023, 3, 30)],
        ),
    ],
)
def test_february_monthliversaries_are_issue_anchored(
    patched_engine, issue, valuation, expected,
):
    _config_obj, rates = patched_engine
    policy = _policy(issue=issue, valuation=valuation)
    states = IllustrationEngine().project(
        policy,
        months=2,
        timing=ProjectionTiming.CYBERLIFE_MONTHLIVERSARY,
        stop_on_lapse=False,
        options=IllustrationOptions(conform_to_tefra=False, conform_to_tamra=False),
        rates_override=rates,
        bonus_override=BonusConfig(),
    )
    assert [state.date for state in states[1:]] == expected


def test_historical_dated_premium_gets_receipt_to_mv_interest(patched_engine):
    _config_obj, rates = patched_engine
    policy = _policy(
        issue=date(2026, 8, 16),
        valuation=date(2026, 8, 16),
        rollback_date=date(2026, 8, 16),
    )
    inputs = IllustrationInputSet(dated_transactions=[
        DatedTransaction(
            TransactionKind.PREMIUM,
            date(2026, 9, 16),
            100.0,
            metadata={"actual_date": "2026-08-25"},
        )
    ])
    states = IllustrationEngine().project(
        policy,
        months=1,
        future_inputs=inputs,
        timing=ProjectionTiming.CYBERLIFE_MONTHLIVERSARY,
        stop_on_lapse=False,
        options=IllustrationOptions(conform_to_tefra=False, conform_to_tamra=False),
        rates_override=rates,
        bonus_override=BonusConfig(),
    )
    base = 1_000.0 * ((1.06) ** (interest_days(date(2026, 8, 16), date(2026, 9, 16)) / 365) - 1)
    stub_days = interest_days(date(2026, 8, 24), date(2026, 9, 16))
    premium_stub = 100.0 * ((1.06) ** (stub_days / 365) - 1)
    assert states[1].interest_credited == pytest.approx(base + premium_stub)


def test_inforce_dated_premium_does_not_get_receipt_stub(patched_engine):
    _config_obj, rates = patched_engine
    policy = _policy(issue=date(2026, 8, 16), valuation=date(2026, 8, 16))
    inputs = IllustrationInputSet(dated_transactions=[
        DatedTransaction(
            TransactionKind.PREMIUM,
            date(2026, 9, 16),
            100.0,
            metadata={"actual_date": "2026-08-25"},
        )
    ])
    states = IllustrationEngine().project(
        policy,
        months=1,
        future_inputs=inputs,
        timing=ProjectionTiming.CYBERLIFE_MONTHLIVERSARY,
        stop_on_lapse=False,
        options=IllustrationOptions(conform_to_tefra=False, conform_to_tamra=False),
        rates_override=rates,
        bonus_override=BonusConfig(),
    )
    base = 1_000.0 * ((1.06) ** (interest_days(date(2026, 8, 16), date(2026, 9, 16)) / 365) - 1)
    assert states[1].interest_credited == pytest.approx(base)
