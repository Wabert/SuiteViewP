"""``horizon_months`` solves the minimum level premium to a date, not to maturity.

The Policy Support GLP Exception screen asks "what is the least this policy must
take in between now and the target date?" — the answer is often $0, and it is
always less than the premium that would sustain the policy to maturity. Solving
to maturity instead would demand guideline room the policy never actually needs
by the target, and so would wrongly call for an AccumGLP adjustment.

A stub engine models the account value as a simple run-down (``burn`` per month,
topped up by the level premium) that lapses — truncating the run — the month it
goes negative, so the solve's bracket/bisect mechanics are exercised without a
rates database.
"""
from datetime import date
from types import SimpleNamespace

import pytest

from suiteview.illustration.core.solve_level_to_exception import (
    LevelToExceptionError,
    level_to_exception_options,
    solve_level_to_exception,
)
from suiteview.illustration.models.input_set import (
    IllustrationInputSet,
    IllustrationOptions,
    TransactionKind,
)
from suiteview.illustration.models.policy_data import IllustrationPolicyData

_ISSUE_AGE = 50
_START_AGE = 60
_MATURITY = 121
# Months for the stub to carry a never-lapsing policy from _START_AGE to maturity.
_MONTHS_TO_MATURITY = (_MATURITY - _START_AGE) * 12


def _st(**kw) -> SimpleNamespace:
    """A MonthlyState stand-in with the fields the solve/_build_result read."""
    base = dict(
        attained_age=_START_AGE,
        policy_year=1,
        date=date(2030, 6, 6),
        exception_prem_mode=False,
        gp_exception_prem_gross=0.0,
        guideline_limit=100_000.0,
        prem_less_wd=0.0,
        applied_scheduled_premium=0.0,
        applied_lumpsum=0.0,
        av_end_of_month=1.0,
        ending_sv=1.0,
        lapsed=False,
        gp_exception_mode=False,
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


class _BurnEngine:
    """Account value falls by ``burn`` a month and is topped up by the premium.

    The run truncates the month the account value goes negative — the same shape
    ``stop_on_lapse`` produces — so a run that comes back the full length asked
    for is exactly a run that stayed in force.
    """

    def __init__(self, account_value: float, burn: float):
        self.account_value = account_value
        self.burn = burn

    def project(self, _policy, *, options=None, future_inputs=None,
                months=None, **_kw):
        premium = _level_premium(future_inputs)
        horizon = _MONTHS_TO_MATURITY if months is None else months
        av = self.account_value
        states = [_st(av_end_of_month=av)]
        for month in range(1, horizon + 1):
            av += premium - self.burn
            states.append(_st(
                attained_age=_START_AGE + month // 12,
                policy_year=1 + month // 12,
                av_end_of_month=av,
                ending_sv=av,
                lapsed=av <= 0.0,
                premiums_to_date=premium * month,
            ))
            if av <= 0.0:
                break
        return states


def _policy() -> IllustrationPolicyData:
    return IllustrationPolicyData(
        def_of_life_ins="GPT", maturity_age=_MATURITY, issue_age=_ISSUE_AGE,
        billing_frequency=1, modal_premium=100.0)


def _solve(engine, **kw):
    return solve_level_to_exception(
        _policy(), mode="M", engine=engine,
        base_future_inputs=IllustrationInputSet(), **kw)


def test_zero_premium_when_account_value_alone_reaches_the_horizon():
    # 1,000 of account value against 100/month covers 10 months, so a 9-month
    # horizon needs nothing at all.
    result = _solve(_BurnEngine(account_value=1_000.0, burn=100.0),
                    horizon_months=9)

    assert result.premium == 0.0
    assert result.enters_exception is False


def test_solves_the_shortfall_when_the_account_value_runs_out_first():
    # 20 months of 100/month burn = 2,000; the 1,000 account value covers half,
    # leaving 1,000 to be funded over 20 months = 50.00/month.
    result = _solve(_BurnEngine(account_value=1_000.0, burn=100.0),
                    horizon_months=20)

    assert result.premium == 50.01  # strictly positive surrender value


def test_target_horizon_solves_far_less_than_the_maturity_solve():
    """The regression this parameter exists for.

    Solving to maturity demands nearly the full monthly burn forever; solving to
    a near target date demands only the shortfall over those few months. Using
    the maturity figure to judge a target date overstates the premium — and so
    the guideline room — the policy actually needs.
    """
    engine = _BurnEngine(account_value=1_000.0, burn=100.0)

    to_target = _solve(engine, horizon_months=20).premium
    to_maturity = _solve(engine).premium

    assert to_target == 50.01
    # 732 months of burn less the 1,000 already in the policy, spread over 732.
    assert to_maturity == pytest.approx(98.64, abs=0.01)
    assert to_target < to_maturity


def test_horizon_solve_still_reports_a_policy_it_cannot_fund():
    """A bracket that never survives raises, with target-date wording."""

    class _AlwaysLapses(_BurnEngine):
        def project(self, _policy, *, options=None, future_inputs=None,
                    months=None, **_kw):
            return [_st(), _st(attained_age=_START_AGE + 1)]

    with pytest.raises(LevelToExceptionError, match="target date"):
        _solve(_AlwaysLapses(account_value=0.0, burn=1.0), horizon_months=12)


@pytest.mark.parametrize("horizon", [None, 20])
@pytest.mark.parametrize("forceouts", [False, True])
@pytest.mark.parametrize("levelizing", [False, True])
def test_solve_and_display_preserve_forceouts_without_relaxing_caps(horizon, forceouts, levelizing):
    from dataclasses import asdict

    base = IllustrationOptions(
        guideline_forceouts=forceouts, exact_days_interest=False,
        levelizing_premium=levelizing, apply_prem_to_loan=True)
    original = asdict(base)
    display_options = level_to_exception_options(base)

    class CheckedEngine(_BurnEngine):
        calls = 0

        def project(self, policy, *, options, **kwargs):
            self.calls += 1
            assert options == display_options
            assert options.force_out_enabled is forceouts
            assert options.conform_to_tefra and options.conform_to_tamra
            assert options.guideline_cap_enabled and options.tamra_cap_enabled
            assert options.allow_exception_prems
            assert options.levelizing_premium is levelizing
            assert options.dollar_for_dollar_in_transition_year is not levelizing
            return super().project(policy, options=options, **kwargs)

    engine = CheckedEngine(account_value=1000.0, burn=100.0)
    assert _solve(engine, horizon_months=horizon, base_options=base).premium > 0
    assert engine.calls > 1
    assert asdict(base) == original
    assert IllustrationOptions(**asdict(display_options)) == display_options


def test_forceout_default_and_tefra_gate_are_unchanged():
    assert IllustrationOptions().force_out_enabled
    assert level_to_exception_options(None).force_out_enabled
    assert not IllustrationOptions(conform_to_tefra=False).force_out_enabled
    options = IllustrationOptions(guideline_forceouts=False)
    assert not options.force_out_enabled
    assert options.guideline_cap_enabled and options.tamra_cap_enabled
