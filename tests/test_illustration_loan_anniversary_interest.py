"""Anniversary-month loan-collateral interest under CyberLife monthliversary timing.

CyberLife credits the month that ends on a policy anniversary on the loan
principal that was collateral during that month (the pre-capitalization
principal); the interest capitalized at the anniversary (arrears accrued or the
next year's advance interest) becomes collateral from the anniversary on.
History replay 2026-10-07: V0835562 (advance), U0340373 and UL037038 (arrears).
"""
from __future__ import annotations

from datetime import date

import pytest

from suiteview.illustration.core import calc_engine
from suiteview.illustration.core.bonus_rates import BonusConfig
from suiteview.illustration.core.calc_engine import IllustrationEngine, ProjectionTiming
from suiteview.illustration.core.rate_loader import IllustrationRates
from suiteview.illustration.core.target_premium import TargetPremiumResult
from suiteview.illustration.models.input_set import IllustrationOptions
from suiteview.illustration.models.plancode_config import PlancodeConfig
from suiteview.illustration.models.policy_data import CoverageSegment, IllustrationPolicyData

ISSUE = date(1983, 9, 6)
VALUATION = date(2026, 8, 6)       # policy year 43, month 12; next monthliversary is the anniversary
ANNIVERSARY = date(2026, 9, 6)
DAYS = (ANNIVERSARY - VALUATION).days


def _rates() -> IllustrationRates:
    zero = [0.0] * 240
    return IllustrationRates(coi=zero, segment_coi={1: zero}, epu=zero, segment_epu={1: zero},
                             scr=zero, segment_scr={1: zero}, tpp=zero, epp=zero)


def _rate(annual: float, days: int = DAYS) -> float:
    return (1.0 + annual) ** (days / 365.0) - 1.0


def _project(monkeypatch, config: PlancodeConfig, policy: IllustrationPolicyData, months: int = 2):
    rates = _rates()
    monkeypatch.setattr(calc_engine, "load_plancode", lambda _plancode: config)
    monkeypatch.setattr(calc_engine, "load_bonus_config", lambda *_args: BonusConfig())
    monkeypatch.setattr(calc_engine.IllustrationEngine, "_load_rates", lambda *_args: rates)
    monkeypatch.setattr(calc_engine, "compute_target_premiums", lambda *_a, **_k: TargetPremiumResult())
    monkeypatch.setattr(calc_engine, "build_target_detail_snapshots", lambda *_a, **_k: ({}, {}))
    monkeypatch.setattr(calc_engine, "_coverage_after_change_snapshot", lambda *_a, **_k: {})
    return IllustrationEngine().project(
        policy, months=months, timing=ProjectionTiming.CYBERLIFE_MONTHLIVERSARY,
        stop_on_lapse=False,
        options=IllustrationOptions(conform_to_tefra=False, conform_to_tamra=False),
        rates_override=rates, bonus_override=BonusConfig(),
    )


def _policy(**loan) -> IllustrationPolicyData:
    fields = dict(
        policy_number="LOANANNIV", plancode="LOANANNIV", def_of_life_ins="GPT",
        issue_date=ISSUE, valuation_date=VALUATION, issue_age=16, attained_age=58,
        maturity_age=95, policy_year=43, policy_month=12, duration=516,
        face_amount=100_000.0, units=100.0, db_option="A",
        current_interest_rate=0.04, guaranteed_interest_rate=0.04,
        glp=1_000_000.0, gsp=1_000_000.0, preferred_loans_available=True,
        segments=[CoverageSegment(coverage_phase=1, issue_date=ISSUE, issue_age=16, rate_sex="F",
                                  rate_class="A", face_amount=100_000.0,
                                  original_face_amount=100_000.0, units=100.0)],
    )
    fields.update(loan)
    return IllustrationPolicyData(**fields)


def test_advance_anniversary_month_credits_pre_capitalization_collateral(monkeypatch):
    # V0835562 (1A130E29): CyberLife credited 112.63 at 9/6/2026 on reg 8,512.57 and
    # pref 15,939.48; the 680.27 + 956.30 advance interest capitalized that day.
    config = PlancodeConfig(
        plancode="LOANANNIV", prem_flat_load=0.0, gint=0.04, dbd=0.0, lapse_value="AV",
        interest_method="ExactDays", loan_type="Advance",
        loan_charge_rate_guar=0.074, loan_charge_rate_curr=0.04,
        pref_loan_charge_rate_guar=0.0566, pref_loan_charge_rate_curr=0.0566,
    )
    policy = _policy(account_value=27_304.69, regular_loan_principal=8_512.57,
                     preferred_loan_principal=15_939.48,
                     regular_loan_charge_rate=0.074, preferred_loan_charge_rate=0.0566)
    states = _project(monkeypatch, config, policy)
    anniv = states[1]
    assert anniv.date == ANNIVERSARY
    free = 27_304.69 - 8_512.57 - 15_939.48
    expected = free * _rate(0.04) + 8_512.57 * _rate(0.04) + 15_939.48 * _rate(0.0566)
    assert anniv.interest_credited == pytest.approx(expected, abs=1e-6)
    assert round(anniv.interest_credited, 2) == 112.63
    # Capitalization itself is unchanged: the advance interest still lands at the anniversary.
    assert anniv.rg_loan_princ == pytest.approx(9_192.84, abs=0.005)
    assert anniv.pf_loan_princ == pytest.approx(16_895.78, abs=0.005)


def test_arrears_capitalized_interest_becomes_collateral_the_month_after(monkeypatch):
    config = PlancodeConfig(
        plancode="LOANANNIV", prem_flat_load=0.0, gint=0.03, dbd=0.0, lapse_value="AV",
        interest_method="ExactDays", loan_type="Arrears",
        loan_charge_rate_guar=0.08, loan_charge_rate_curr=0.05,
        pref_loan_charge_rate_guar=0.06, pref_loan_charge_rate_curr=0.06,
    )
    policy = _policy(account_value=30_000.0, current_interest_rate=0.03, guaranteed_interest_rate=0.03,
                     regular_loan_principal=10_000.0, regular_loan_accrued=700.0,
                     preferred_loan_principal=5_000.0, preferred_loan_accrued=280.0,
                     regular_loan_charge_rate=0.08, preferred_loan_charge_rate=0.06)
    states = _project(monkeypatch, config, policy, months=2)
    anniv, after = states[1], states[2]

    # Anniversary month: collateral is the pre-capitalization principal, not principal + accrued.
    free = 30_000.0 - 15_000.0
    expected = free * _rate(0.03) + 10_000.0 * _rate(0.05) + 5_000.0 * _rate(0.06)
    assert anniv.interest_credited == pytest.approx(expected, abs=1e-6)

    # The accrued interest (with the valuation month's accrual) capitalizes at the anniversary...
    rg_cap, pf_cap = anniv.rg_loan_princ, anniv.pf_loan_princ
    assert rg_cap == pytest.approx(10_700.0 + 10_000.0 * 0.08 * DAYS / 365.0)
    assert pf_cap == pytest.approx(5_280.0 + 5_000.0 * 0.06 * DAYS / 365.0)
    # ...and is collateral for the following month.
    days_after = (after.date - anniv.date).days
    free_after = anniv.av_end_of_month - rg_cap - pf_cap
    expected_after = (free_after * _rate(0.03, days_after) + rg_cap * _rate(0.05, days_after)
                      + pf_cap * _rate(0.06, days_after))
    assert after.interest_credited == pytest.approx(expected_after, abs=1e-6)
