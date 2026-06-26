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
        # TEFRA off disables the guideline cap, so the MD premium is never
        # capped and the AV stays flat at its pre-deduction value.
        options=IllustrationOptions(pay_monthly_deduction=True, conform_to_tefra=False),
        rates_override=_rates(), bonus_override=BonusConfig(),
    )
    projected = states[1:]  # states[0] is the inforce (month-0) snapshot
    assert len(projected) == 6
    for s in projected:
        assert s.total_deduction > 0
        assert s.md_premium_mode is True
        assert s.md_premium > 0.0
        assert s.md_premium_capped is False
        # The MD premium restores the full deduction (zero interest).
        assert s.md_premium_gross == pytest.approx(s.total_deduction)
        # Discount = the COI-saving portion of the AV bump (no load here).
        assert s.md_premium_discount == pytest.approx(s.md_premium_gross - s.md_premium)
        # Monthly Deduction is NOT the GP exception — it must not flip the
        # exception display mode or the force-out-bypassing GP exception flag.
        assert s.exception_prem_mode is False
        assert s.gp_exception_mode is False
        assert s.gp_exception_prem == 0.0
        # The premium counts toward premiums paid / cost basis (carried forward).
        assert s.premiums_to_date_after_exception == pytest.approx(
            s.premiums_to_date + s.md_premium)
        # Zero interest: the premium restores the AV to its pre-deduction value.
        assert s.av_end_of_month == pytest.approx(s.guideline_av_before_monthly_deduction)
    # The account value is held flat at its starting value across all months.
    assert projected[-1].av_end_of_month == pytest.approx(states[0].av_end_of_month)


def test_monthly_deduction_premium_capped_at_guideline(monkeypatch):
    # A GPT policy with no guideline room: the MD premium is capped to zero
    # in-month (it never over-funds, so there is no force-out claw-back) and the
    # account value declines by the deduction. With exceptions off it just runs
    # down — MD is subject to the guideline, unlike the GP exception.
    _patch(monkeypatch)
    states = IllustrationEngine().project(
        _md_policy(), months=6,
        options=IllustrationOptions(pay_monthly_deduction=True, conform_to_tefra=True),
        rates_override=_rates(), bonus_override=BonusConfig(),
    )
    projected = states[1:]
    for s in projected:
        assert s.md_premium_capped is True
        assert s.md_premium == 0.0
        assert s.gp_exception_mode is False     # exceptions not allowed
        assert s.guideline_forceout == 0.0      # capped in-month, nothing to claw back
    assert projected[-1].av_end_of_month < states[0].av_end_of_month


def test_md_premium_hands_off_to_gp_exception_when_capped(monkeypatch):
    # Thin AV + tiny guideline room + exceptions allowed: the MD premium spends
    # the last of the room (capped), then the GP exception covers the residual
    # past the guideline — in the SAME month. Once latched the exception holds
    # the AV at zero and the MD premium goes silent.
    _patch(monkeypatch)
    policy = _md_policy()
    policy.account_value = 200.0   # thin → goes negative in month 1
    policy.gsp = 50.0              # tiny guideline room → partial MD, then exception
    states = IllustrationEngine().project(
        policy, months=6,
        options=IllustrationOptions(
            pay_monthly_deduction=True, conform_to_tefra=True,
            allow_exception_prems=True),
        rates_override=_rates(), bonus_override=BonusConfig(),
    )
    projected = states[1:]
    first = projected[0]
    # Same-month hand-off — both premiums non-zero.
    assert first.md_premium > 0.0
    assert first.md_premium_capped is True
    assert first.md_premium_discount > 0.0
    assert first.gp_exception_prem > 0.0
    assert first.gp_exception_prem_discount > 0.0
    assert first.exception_prem_mode is True    # the GP exception (not MD) flips this
    assert first.gp_exception_mode is True
    for s in projected:
        assert s.gp_exception_mode is True       # latched
        assert s.av_end_of_month == pytest.approx(0.0, abs=0.05)
    for s in projected[1:]:
        assert s.md_premium == 0.0               # no room left once over the guideline
        assert s.gp_exception_prem > 0.0


def test_account_value_declines_without_monthly_deduction_premium(monkeypatch):
    _patch(monkeypatch)
    states = IllustrationEngine().project(
        _md_policy(), months=6,
        options=IllustrationOptions(),  # default: no Monthly Deduction premium
        rates_override=_rates(), bonus_override=BonusConfig(),
    )
    projected = states[1:]
    # Healthy policy, so neither premium triggers; with no premium the account
    # value falls by each month's deduction.
    assert all(s.md_premium == 0.0 and s.gp_exception_prem == 0.0 for s in projected)
    assert projected[-1].av_end_of_month < states[0].av_end_of_month


def test_option_b_shrinks_the_coi_feedback_discount(monkeypatch):
    # With an increasing death benefit (Option B) a premium also raises the DB,
    # so the COI saving is only the level-DB feedback scaled by (1 − 1/(1+dbd)^(1/12)).
    dbd = 0.03
    monkeypatch.setattr(
        calc_engine, "load_plancode",
        lambda _p: PlancodeConfig(
            plancode="MDPREM", dbd=dbd, gint=0.0, corridor_code=None,
            epu_code="0", mfee="0", premium_load="0", prem_flat_load=0.0,
        ),
    )
    monkeypatch.setattr(calc_engine, "load_bonus_config", lambda _p, _d: BonusConfig())

    def feedback_for(db_option: str) -> float:
        policy = _md_policy()
        policy.db_option = db_option
        s = IllustrationEngine().project(
            policy, months=1,
            options=IllustrationOptions(pay_monthly_deduction=True, conform_to_tefra=False),
            rates_override=_rates(), bonus_override=BonusConfig(),
        )[1]
        assert s.md_premium > 0.0
        # discount / AV-restoration = the COI saving per dollar of AV bump (phi).
        return s.md_premium_discount / s.md_premium_gross

    phi_a = feedback_for("A")
    phi_b = feedback_for("B")
    df = round((1.0 + dbd) ** (1.0 / 12.0), 7)
    assert phi_b == pytest.approx(phi_a * (1.0 - 1.0 / df), rel=1e-6)
    # Option C is treated like Option B here (conservative).
    assert feedback_for("C") == pytest.approx(phi_b, rel=1e-6)
