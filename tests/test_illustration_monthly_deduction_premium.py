"""Monthly Deduction premium type — engine integration.

The Monthly Deduction premium reuses the GP exception premium machinery,
retargeted: instead of grossing the after-charge account value back up to zero,
it grosses it back up by the full monthly deduction so the ending account value
equals where it stood just *before* the deduction. With zero interest and no
other premium the account value therefore stays flat at its pre-deduction value
every month, and the (reused) exception-premium gross equals the full deduction.
"""
from datetime import date

import pytest

from suiteview.illustration.core import calc_engine
from suiteview.illustration.core.bonus_rates import BonusConfig
from suiteview.illustration.core.calc_engine import IllustrationEngine
from suiteview.illustration.core.rate_loader import IllustrationRates
from suiteview.illustration.models.input_set import IllustrationOptions
from suiteview.illustration.models.plancode_config import PlancodeConfig
from suiteview.illustration.models.policy_data import (
    CoverageSegment,
    IllustrationPolicyData,
)


def _md_policy():
    # Healthy policy, 25 years in (past the safety net), positive account value.
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
        account_value=50_000.0,
        current_interest_rate=0.0,
        guaranteed_interest_rate=0.0,
        segments=[CoverageSegment(coverage_phase=1, issue_date=date(2000, 6, 15),
                                  face_amount=100_000.0, units=100.0)],
    )


def _patch(monkeypatch):
    monkeypatch.setattr(
        calc_engine, "load_plancode",
        lambda _p: PlancodeConfig(
            plancode="MDPREM", dbd=0.0, gint=0.0, corridor_code=None,
            epu_code="0", mfee="0", premium_load="0", prem_flat_load=0.0,
        ),
    )
    monkeypatch.setattr(calc_engine, "load_bonus_config", lambda _p, _d: BonusConfig())


def _rates():
    # 6 per 1,000 COI so the monthly deduction is non-trivial (~300/month).
    return IllustrationRates(coi=[0.0, 6.0], segment_coi={1: [0.0, 6.0]})


def test_monthly_deduction_premium_holds_account_value_flat(monkeypatch):
    _patch(monkeypatch)
    states = IllustrationEngine().project(
        _md_policy(), months=6,
        # TEFRA off isolates the MD math from guideline force-out, so the premium
        # is never clawed back and the AV stays flat.
        options=IllustrationOptions(pay_monthly_deduction=True, conform_to_tefra=False),
        rates_override=_rates(), bonus_override=BonusConfig(),
    )
    projected = states[1:]  # states[0] is the inforce (month-0) snapshot
    assert len(projected) == 6
    for s in projected:
        assert s.total_deduction > 0
        # The reused gross target is the full deduction, not a deficit to zero.
        assert s.gp_exception_prem_gross == pytest.approx(s.total_deduction)
        assert s.gp_exception_prem > 0.0
        assert s.exception_prem_mode is True
        # Monthly Deduction is NOT the GP exception — it must not latch the
        # force-out-bypassing GP exception mode.
        assert s.gp_exception_mode is False
        # The premium counts toward premiums paid and cost basis (carried forward).
        assert s.premiums_to_date_after_exception == pytest.approx(
            s.premiums_to_date + s.gp_exception_prem)
        # Zero interest: the premium restores the AV to its pre-deduction value.
        assert s.av_end_of_month == pytest.approx(s.guideline_av_before_monthly_deduction)
    # The account value is held flat at its starting value across all months.
    assert projected[-1].av_end_of_month == pytest.approx(states[0].av_end_of_month)


def test_monthly_deduction_premium_is_subject_to_forceout(monkeypatch):
    # A GPT policy with no guideline room: the MD premium counts toward premiums
    # paid, so once it pushes cumulative premium over the (zero) guideline limit
    # the force-out claws it back — MD does NOT bypass force-out, unlike the GP
    # exception. The account value therefore still declines.
    monkeypatch.setattr(
        calc_engine, "load_plancode",
        lambda _p: PlancodeConfig(
            plancode="MDPREM", dbd=0.0, gint=0.0, corridor_code=None,
            epu_code="0", mfee="0", premium_load="0", prem_flat_load=0.0,
        ),
    )
    monkeypatch.setattr(calc_engine, "load_bonus_config", lambda _p, _d: BonusConfig())

    policy = _md_policy()
    policy.def_of_life_ins = "GPT"  # subject to the guideline-premium force-out
    states = IllustrationEngine().project(
        policy, months=6,
        options=IllustrationOptions(pay_monthly_deduction=True, conform_to_tefra=True),
        rates_override=_rates(), bonus_override=BonusConfig(),
    )
    projected = states[1:]
    assert any(s.guideline_forceout > 0 for s in projected)
    assert all(s.gp_exception_mode is False for s in projected)
    assert projected[-1].av_end_of_month < states[0].av_end_of_month


def test_account_value_declines_without_monthly_deduction_premium(monkeypatch):
    _patch(monkeypatch)
    states = IllustrationEngine().project(
        _md_policy(), months=6,
        options=IllustrationOptions(),  # default: no Monthly Deduction premium
        rates_override=_rates(), bonus_override=BonusConfig(),
    )
    projected = states[1:]
    # Healthy policy, so the GP exception never triggers; with no premium the
    # account value falls by each month's deduction.
    assert all(s.gp_exception_prem_gross == 0.0 for s in projected)
    assert projected[-1].av_end_of_month < states[0].av_end_of_month
