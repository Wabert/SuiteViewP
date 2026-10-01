"""Prem-to-Maturity solve funds the transition year cleanly.

The minimum-survival premium only limps into the GP exception period: the level
premium can no longer keep the account value positive between modal payments, so
a GP exception premium fires WHILE guideline room still remains (the ragged
transition year). ``fund_transition_cleanly`` (default on) instead solves for the
slightly higher premium whose first exception cannot fire until the guideline
room is exhausted — the "perfectly level right up to the exception period"
contract — while never returning less than the survive-minimum.

These use a stub engine so the solve's bracket/bisect mechanics are exercised
without a rates database: the projected stream is a deterministic function of the
level premium.
"""
from datetime import date
from types import SimpleNamespace

import pytest

from suiteview.illustration.core.solve_level_to_exception import (
    solve_level_to_exception,
)
from suiteview.illustration.models.input_set import (
    IllustrationInputSet,
    TransactionKind,
)
from suiteview.illustration.models.policy_data import IllustrationPolicyData

_MATURITY = 121
_GUIDELINE_LIMIT = 100_000.0


def _st(**kw) -> SimpleNamespace:
    """A MonthlyState stand-in with the fields the solve/_build_result read."""
    base = dict(
        attained_age=60,
        policy_year=1,
        date=date(2030, 6, 6),
        exception_prem_mode=False,
        gp_exception_prem_gross=0.0,
        guideline_limit=_GUIDELINE_LIMIT,
        prem_less_wd=0.0,
        applied_scheduled_premium=0.0,
        applied_lumpsum=0.0,
        av_end_of_month=1.0,
        premiums_to_date=0.0,
        applied_loan_repayment=0.0,
    )
    base.update(kw)
    return SimpleNamespace(**base)


def _level_premium(future_inputs: IllustrationInputSet) -> float:
    amounts = [
        t.amount for t in future_inputs.scheduled_transactions
        if t.kind == TransactionKind.PREMIUM and t.policy_year == 1
    ]
    return max(amounts) if amounts else 0.0


class _StubEngine:
    """Projects a premium-dependent stream.

    * premium < ``p_survive`` → lapses (final attained age below maturity).
    * ``p_survive`` ≤ premium < ``p_clean`` → survives but the first GP exception
      fires with guideline room still remaining (premature — ragged year).
    * premium ≥ ``p_clean`` → survives and the first GP exception fires only once
      the guideline room is exhausted (clean transition).
    """

    def __init__(self, p_survive: float, p_clean: float):
        self.p_survive = p_survive
        self.p_clean = p_clean

    def project(self, _policy, *, options=None, future_inputs=None, **_kw):
        premium = _level_premium(future_inputs)
        if premium < self.p_survive - 1e-9:
            # Lapses before maturity.
            return [_st(), _st(attained_age=70, policy_year=5)]
        room_at_exception = 0.0 if premium >= self.p_clean - 1e-9 else 500.0
        # prem_less_wd chosen so room after this month's (zero) applied premium
        # equals the target: room = guideline_limit - prem_less_wd.
        exc = _st(
            attained_age=90, policy_year=6, exception_prem_mode=True,
            gp_exception_prem_gross=250.0,
            prem_less_wd=_GUIDELINE_LIMIT - room_at_exception,
        )
        return [
            _st(),                                    # inforce seed
            _st(attained_age=80, policy_year=3),
            exc,
            _st(attained_age=_MATURITY, policy_year=7, exception_prem_mode=True,
                gp_exception_prem_gross=250.0, premiums_to_date=premium),
        ]


def _policy() -> IllustrationPolicyData:
    return IllustrationPolicyData(
        def_of_life_ins="GPT", maturity_age=_MATURITY, issue_age=50,
        billing_frequency=1, modal_premium=100.0, glp=1200.0)


def test_clean_transition_prefers_the_higher_fully_funded_premium():
    engine = _StubEngine(p_survive=2000.0, p_clean=2500.0)
    result = solve_level_to_exception(
        _policy(), mode="A", engine=engine,
        base_future_inputs=IllustrationInputSet())
    # Not the bare survive-minimum (~2000) — the clean-transition premium (~2500).
    assert result.premium == pytest.approx(2500.0, abs=0.01)
    assert result.enters_exception is True


def test_fund_transition_cleanly_off_returns_the_survive_minimum():
    engine = _StubEngine(p_survive=2000.0, p_clean=2500.0)
    result = solve_level_to_exception(
        _policy(), mode="A", engine=engine, fund_transition_cleanly=False,
        base_future_inputs=IllustrationInputSet())
    assert result.premium == pytest.approx(2000.0, abs=0.01)


def test_clean_solve_never_returns_less_than_survive_minimum():
    # When the transition can never be funded cleanly (every surviving premium
    # still fires an exception with room remaining), fall back to survive-min —
    # never below it.
    class _NeverClean(_StubEngine):
        def project(self, _policy, *, options=None, future_inputs=None, **_kw):
            premium = _level_premium(future_inputs)
            if premium < self.p_survive - 1e-9:
                return [_st(), _st(attained_age=70, policy_year=5)]
            exc = _st(
                attained_age=90, policy_year=6, exception_prem_mode=True,
                gp_exception_prem_gross=250.0,
                prem_less_wd=_GUIDELINE_LIMIT - 500.0,   # room always remains
            )
            return [
                _st(), exc,
                _st(attained_age=_MATURITY, policy_year=7,
                    exception_prem_mode=True, gp_exception_prem_gross=250.0),
            ]

    engine = _NeverClean(p_survive=2000.0, p_clean=9_999_999.0)
    result = solve_level_to_exception(
        _policy(), mode="A", engine=engine,
        base_future_inputs=IllustrationInputSet())
    assert result.premium == pytest.approx(2000.0, abs=0.01)


def test_endowing_policy_stays_clean_without_a_bump():
    # A policy that simply endows (no exception ever) is already clean; the clean
    # solve must not inflate its premium above the survive-minimum.
    class _Endows(_StubEngine):
        def project(self, _policy, *, options=None, future_inputs=None, **_kw):
            premium = _level_premium(future_inputs)
            if premium < self.p_survive - 1e-9:
                return [_st(), _st(attained_age=70, policy_year=5)]
            return [
                _st(),
                _st(attained_age=_MATURITY, policy_year=7,
                    av_end_of_month=5000.0, premiums_to_date=premium),
            ]

    engine = _Endows(p_survive=1500.0, p_clean=0.0)
    result = solve_level_to_exception(
        _policy(), mode="A", engine=engine,
        base_future_inputs=IllustrationInputSet())
    assert result.premium == pytest.approx(1500.0, abs=0.01)
    assert result.enters_exception is False


def test_clean_is_not_found_far_above_in_a_guideline_clipped_premium():
    # "Clean" is not monotone: a far higher premium that the guideline cap clips
    # payment after payment can look clean by coincidence (exception fires with
    # no room left). The solve must not jump to it — it stays with the level
    # survive-minimum.
    class _FarClean(_StubEngine):
        def project(self, _policy, *, options=None, future_inputs=None, **_kw):
            premium = _level_premium(future_inputs)
            if premium < self.p_survive - 1e-9:
                return [_st(), _st(attained_age=70, policy_year=5)]
            clipped = [_st(premium_capped=True) for _ in range(12)]
            room = 0.0 if premium >= 4000.0 else 500.0
            exc = _st(
                attained_age=90, policy_year=6, exception_prem_mode=True,
                gp_exception_prem_gross=250.0,
                prem_less_wd=_GUIDELINE_LIMIT - room,
            )
            if premium >= 4000.0:
                return [_st(), *clipped, exc, _st(attained_age=_MATURITY)]
            return [_st(), exc, _st(attained_age=_MATURITY)]

    engine = _FarClean(p_survive=2000.0, p_clean=4000.0)
    result = solve_level_to_exception(
        _policy(), mode="A", engine=engine,
        base_future_inputs=IllustrationInputSet())
    assert result.premium == pytest.approx(2000.0, abs=0.01)
