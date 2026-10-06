"""GP exception premium — Robert's rule of 10/6/2026.

The GP exception premium is computed *after* the monthly deduction:

    required net = MD0 - AV available

where MD0 is the monthly deduction as if the account value were 0 (the NAR is
the full discounted death benefit) and the AV available is the account value
before the deduction (a negative AV raises the premium, a positive one lowers
it). The required net is grossed up for the plan's actual premium load (TPP up
to the commission target, EPP above it, plus any flat per-premium load) and
rounded up to the cent. The account value then sits at 0 after every deduction
and the premium is level within a policy year.
"""
from datetime import date

import pytest

from suiteview.illustration.core import calc_engine
from suiteview.illustration.core.bonus_rates import BonusConfig
from suiteview.illustration.core.calc_engine import IllustrationEngine
from suiteview.illustration.core.premium_handler import (
    gross_up_for_premium_load,
    split_premium_load,
)
from suiteview.illustration.core.rate_loader import IllustrationRates
from suiteview.illustration.models.input_set import (
    IllustrationInputSet,
    IllustrationOptions,
    ScheduledTransaction,
    TransactionKind,
)
from suiteview.illustration.models.plancode_config import PlancodeConfig
from suiteview.illustration.models.policy_data import CoverageSegment, IllustrationPolicyData

TPP, EPP, FLAT, CTP = 0.08, 0.04, 1.50, 1_200.0


# ── Gross-up ────────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("net", "ytd", "expected_gross"),
    [
        # Entirely under target: (100 + 1.50) / 0.92 = 110.326 -> 110.33
        (100.0, 0.0, 110.33),
        # Entirely over target: (100 + 1.50) / 0.96 = 105.729 -> 105.73
        (100.0, 5_000.0, 105.73),
        # Straddles the target: 50 at TPP nets 46; the rest at EPP:
        # 50 + (500 + 1.50 - 46) / 0.96 = 524.479 -> 524.48
        (500.0, CTP - 50.0, 524.48),
    ],
)
def test_gross_up_tiered_and_flat_load(net, ytd, expected_gross):
    split = gross_up_for_premium_load(
        net, premiums_ytd=ytd, ctp=CTP, tpp=TPP, epp=EPP, flat=FLAT)
    assert split.gross == pytest.approx(expected_gross)
    assert net <= split.net < net + 0.01
    assert split.flat_load == FLAT
    assert split.under_target + split.over_target == pytest.approx(split.gross)
    # Same split the ordinary premium path charges.
    again = split_premium_load(
        split.gross, premiums_ytd=ytd, ctp=CTP, tpp=TPP, epp=EPP, flat=FLAT)
    assert again == split


@pytest.mark.parametrize("net", [0.01, 3.33, 575.95, 4_168.59, 12_345.67])
@pytest.mark.parametrize("ytd", [0.0, 1_000.0, 1_199.99, 9_999.0])
def test_gross_up_nets_the_requirement_within_a_cent(net, ytd):
    split = gross_up_for_premium_load(
        net, premiums_ytd=ytd, ctp=CTP, tpp=TPP, epp=EPP, flat=FLAT)
    assert round(split.gross, 2) == split.gross
    assert net - 1e-9 <= split.net < net + 0.01


def test_gross_up_of_nothing_is_no_premium():
    split = gross_up_for_premium_load(
        0.0, premiums_ytd=0.0, ctp=CTP, tpp=TPP, epp=EPP, flat=FLAT)
    assert split.gross == 0.0 and split.flat_load == 0.0


# ── Engine ──────────────────────────────────────────────────────────────────


def _config():
    return PlancodeConfig(
        plancode="MDPREM", dbd=0.0, gint=0.0, prem_flat_load=FLAT,
        snet_by_issue_age={age: 5 for age in range(0, 122)},
    )


def _rates(tpp: float = TPP, epp: float = TPP):
    # COI per 1,000 rising each policy year so the premium steps at the anniversary.
    # TPP == EPP by default so the premium is level within the year; the target
    # crossing has its own test.
    coi = [0.0] + [0.5 + 0.05 * year for year in range(1, 60)]
    return IllustrationRates(
        coi=coi, segment_coi={1: coi},
        tpp=[0.0] + [tpp] * 60, epp=[0.0] + [epp] * 60,
    )


def _policy(account_value: float) -> IllustrationPolicyData:
    # 25 years in (past the safety net), guideline room used up (GSP 0, GLP not
    # yet accumulated), so the GP exception fires as soon as the AV runs short.
    return IllustrationPolicyData(
        plancode="MDPREM",
        issue_date=date(2000, 6, 15),
        valuation_date=date(2025, 6, 15),
        issue_age=45,
        attained_age=70,
        maturity_age=121,
        policy_year=26,
        policy_month=1,
        duration=300,
        face_amount=100_000.0,
        units=100.0,
        db_option="A",
        def_of_life_ins="GPT",
        glp=12.0,
        gsp=0.0,
        ctp=CTP,
        account_value=account_value,
        current_interest_rate=0.0,
        guaranteed_interest_rate=0.0,
        segments=[CoverageSegment(coverage_phase=1, issue_date=date(2000, 6, 15),
                                  face_amount=100_000.0, units=100.0)],
    )


@pytest.fixture
def engine_env(monkeypatch):
    monkeypatch.setattr(calc_engine, "load_plancode", lambda _p: _config())
    monkeypatch.setattr(calc_engine, "load_bonus_config", lambda *_: BonusConfig())


def _project(policy, months=24, inputs=None, rates=None, **option_kwargs):
    options = IllustrationOptions(
        allow_exception_prems=True, conform_to_tefra=True, **option_kwargs)
    return IllustrationEngine().project(
        policy, months=months, options=options, future_inputs=inputs,
        rates_override=rates or _rates(), bonus_override=BonusConfig(),
    )


def _expected_premium(state, md0: float, av_available: float, epp: float = TPP) -> float:
    return gross_up_for_premium_load(
        md0 - av_available,
        premiums_ytd=state.premiums_ytd_after_exception - state.gp_exception_prem,
        ctp=CTP, tpp=TPP, epp=epp, flat=FLAT,
    ).gross


def test_negative_av_catch_up_then_level_within_the_year(engine_env):
    states = _project(_policy(-500.0))
    first = states[1]
    # Catch-up: MD0 plus the 500 deficit, grossed up for the load.
    assert first.gp_exception_prem == pytest.approx(
        _expected_premium(first, first.total_deduction, -500.0))
    assert first.gp_exception_prem_discount == 0.0
    for state in states[1:]:
        assert state.gp_exception_mode
        assert state.av_after_exception == 0.0
        assert state.interest_credited == 0.0
        assert state.gross_premium == 0.0
    premiums = [round(s.gp_exception_prem, 2) for s in states[2:]]
    changes = [i for i in range(1, len(premiums)) if premiums[i] != premiums[i - 1]]
    assert changes, premiums
    # Level for twelve months at a time; it steps up with the yearly COI rate.
    assert all(b - a == 12 for a, b in zip(changes, changes[1:])), premiums
    assert all(premiums[i] > premiums[i - 1] for i in changes)
    # Each level premium is MD0 grossed up for the load.
    for state in states[2:]:
        assert state.gp_exception_prem == pytest.approx(
            _expected_premium(state, state.total_deduction, 0.0))


def test_positive_av_reduces_the_premium(engine_env):
    states = _project(_policy(300.0), months=6)
    paid = [s for s in states[1:] if s.gp_exception_prem > 0.0]
    first = paid[0]
    available = first.av_after_premium
    assert 0.0 < available < first.total_deduction
    md0 = calc_engine.calculate_deduction(
        0.0, _policy(300.0), _config(), _rates(), first.policy_year,
        first.attained_age, first.premiums_to_date, projection_date=first.date,
    ).total_deduction
    assert md0 > first.total_deduction  # a positive AV lowers the actual NAR
    assert first.gp_exception_prem == pytest.approx(
        _expected_premium(first, md0, available))
    # The AV left is only MD0 - MD (the COI on the AV that was available).
    assert first.av_after_exception == pytest.approx(md0 - first.total_deduction, abs=0.01)
    # It runs off to zero and the premium settles to the level MD0 premium.
    assert states[-1].av_after_exception == 0.0
    assert states[-1].gp_exception_prem == pytest.approx(
        _expected_premium(states[-1], states[-1].total_deduction, 0.0))


def test_guideline_cap_and_levelizing_do_not_touch_the_exception_premium(engine_env):
    policy = _policy(-200.0)
    inputs = IllustrationInputSet(scheduled_transactions=[ScheduledTransaction(
        kind=TransactionKind.PREMIUM, policy_year=26, amount=2_000.0, mode="M")])
    states = _project(policy, months=14, inputs=inputs, levelizing_premium=True)
    for state in states[1:]:
        assert state.gp_exception_mode
        assert state.gross_premium == 0.0  # no room: the schedule never pays
        assert state.av_after_exception == 0.0
        # The exception premium is uncapped, whatever the guideline room.
        assert state.gp_exception_prem == pytest.approx(
            _expected_premium(
                state, state.total_deduction,
                state.av_after_premium if state is states[1] else 0.0))
    # Once latched the schedule is no longer requested, so nothing is "capped".
    assert all(not s.premium_capped for s in states[2:])
    assert all(s.requested_premium == 0.0 for s in states[2:])


def test_latched_exception_replaces_a_schedule_with_guideline_room(engine_env):
    # UL082161: levelizing spreads the remaining guideline room over the year's
    # payments, the binding cap latches "guideline limit reached", and the GP
    # exception fires in month 1 while room remains. The levelized scheduled
    # premium must not then be paid on top of the zero account value.
    policy = _policy(-500.0)
    policy.gsp = 3_000.0
    policy.premiums_paid_to_date = 0.0
    inputs = IllustrationInputSet(scheduled_transactions=[ScheduledTransaction(
        kind=TransactionKind.PREMIUM, policy_year=26, amount=900.0, mode="M")])
    states = _project(policy, months=8, inputs=inputs, levelizing_premium=True)
    first = states[1]
    assert first.gross_premium > 0.0
    assert first.gp_exception_mode and first.gp_exception_prem > 0.0
    assert first.premiums_to_date < 3_000.0  # guideline room still left
    for state in states[2:]:
        assert state.gross_premium == 0.0
        assert state.av_after_exception == 0.0
    assert len({round(s.gp_exception_prem, 2) for s in states[2:]}) == 1


def test_target_and_excess_load_tiers_apply_to_the_exception_premium(engine_env):
    # TPP 8% up to the 1,200 CTP and EPP 4% above it: the exception premium is
    # level at the target rate, then (after one straddling payment) level at the
    # lower excess rate once the year's premiums pass the CTP.
    states = _project(_policy(0.0), months=11, rates=_rates(TPP, EPP))
    for state in states[1:]:
        assert state.av_after_exception == 0.0
        assert state.gp_exception_prem == pytest.approx(
            _expected_premium(state, state.total_deduction, 0.0, epp=EPP))
    premiums = [round(s.gp_exception_prem, 2) for s in states[1:]]
    at_target = (states[1].total_deduction + FLAT) / (1 - TPP)
    over_target = (states[1].total_deduction + FLAT) / (1 - EPP)
    assert premiums[0] == pytest.approx(at_target, abs=0.01)
    assert premiums[-1] == pytest.approx(over_target, abs=0.01)
    assert len(set(premiums)) == 3  # target rate, one straddle, excess rate
