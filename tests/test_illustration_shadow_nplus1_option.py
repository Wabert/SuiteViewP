"""Shadow N+1 target relief is a user setting in illustrations (Robert, 10/8/2026).

ILLUSTRATION timing loads shadow premium above each policy year's target unless
``IllustrationOptions.shadow_nplus1_relief`` is on; with it on the forecast keeps
CyberLife's N+1 rule (SGUL ``ShadowNPlus1Relief`` and the LTGUL APS205 cumulative
test). CyberLife timing always applies it (it reproduces CyberLife history).
"""
from __future__ import annotations

from datetime import date
from types import SimpleNamespace

import pytest

from suiteview.illustration.core import calc_engine
from suiteview.illustration.core.bonus_rates import BonusConfig
from suiteview.illustration.core.calc_engine import IllustrationEngine, ProjectionTiming
from suiteview.illustration.core.rate_loader import IllustrationRates
from suiteview.illustration.core.target_premium import TargetPremiumResult
from suiteview.illustration.models.input_set import (
    DatedTransaction,
    IllustrationInputSet,
    IllustrationOptions,
    TransactionKind,
)
from suiteview.illustration.models.plancode_config import PlancodeConfig
from suiteview.illustration.models.policy_data import CoverageSegment, IllustrationPolicyData
from tests.corridor_fixtures import CORRIDOR_1

TPP, EPP = 0.04, 0.30
# Shadow target 3.00 per 1000 on 100,000: 300 a year.
TARGET = 300.0


def _policy() -> IllustrationPolicyData:
    return IllustrationPolicyData(
        policy_number="NPLUS1", plancode="CHARSHD", def_of_life_ins="GPT",
        issue_date=date(2016, 4, 15), valuation_date=date(2026, 4, 15),
        issue_age=45, attained_age=55, maturity_age=121, policy_year=11, policy_month=1,
        duration=121, face_amount=100_000.0, units=100.0, db_option="A",
        account_value=20_000.0, current_interest_rate=0.04,
        ccv_active=True, ccv_units=100.0, shadow_account_value=2_500.0,
        # Ten years at one target each: premium to date 3,000 = 10 targets.
        premiums_paid_to_date=3_000.0, premiums_ytd=0.0, cost_basis=3_000.0,
        glp=5_000.0, gsp=50_000.0, accumulated_glp=50_000.0, mtp=40.0, ctp=700.0,
        segments=[CoverageSegment(
            coverage_phase=1, issue_date=date(2016, 4, 15), issue_age=45, rate_sex="M",
            rate_class="N", face_amount=100_000.0, original_face_amount=100_000.0, units=100.0)],
    )


def _rates() -> IllustrationRates:
    flat = [0.0] + [2.0] * 180
    zero = [0.0] * 181
    return IllustrationRates(
        coi=flat, segment_coi={1: flat}, epu=zero, segment_epu={1: zero},
        scr=zero, segment_scr={1: zero}, mfee=[0.0] + [5.0] * 180,
        tpp=[0.0] + [0.05] * 180, epp=[0.0] + [0.05] * 180,
        shadow_coi=[0.0] + [1.5] * 180, shadow_epu=zero,
        shadow_tpp=[0.0] + [TPP] * 180, shadow_epp=[0.0] + [EPP] * 180,
        shadow_tpr=[0.0] + [3.0] * 180, shadow_tpr_tbl1=zero,
        shadow_int=[0.0] + [0.04] * 180, shadow_dbd=zero,
    )


def _config(family: str) -> PlancodeConfig:
    flags = (
        {"shadow_nplus1_relief": True} if family == "sgul"
        else {"shadow_aps205_load_relief": True}
    )
    return PlancodeConfig(
        plancode="CHARSHD", corridor_by_age=CORRIDOR_1, gint=0.02, dbd=0.0, lapse_value="SV",
        interest_method="MonthlyCompounding", **flags,
    )


def _inputs() -> IllustrationInputSet:
    # Year 11: one target in month 2, then 200 more in month 9 (8 full months done).
    # YTD 500 is within 2 targets and premium to date 3,500 within (11+1) targets.
    return IllustrationInputSet(dated_transactions=[
        DatedTransaction(kind=TransactionKind.PREMIUM, effective_date=date(2026, 5, 15), amount=TARGET),
        DatedTransaction(kind=TransactionKind.PREMIUM, effective_date=date(2026, 12, 15), amount=200.0),
    ])


def _project(monkeypatch, family: str, options: IllustrationOptions, timing=ProjectionTiming.ILLUSTRATION):
    config = _config(family)
    rates = _rates()
    monkeypatch.setattr(calc_engine, "load_plancode", lambda _plancode: config)
    monkeypatch.setattr(calc_engine, "load_bonus_config", lambda *_args: BonusConfig())
    monkeypatch.setattr(calc_engine.IllustrationEngine, "_load_rates", lambda *_args: rates)
    monkeypatch.setattr(calc_engine.IllustrationEngine, "_guaranteed_rates", lambda *_args: rates)
    monkeypatch.setattr(calc_engine, "compute_target_premiums", lambda *_a, **_k: TargetPremiumResult())
    monkeypatch.setattr(calc_engine, "build_target_detail_snapshots", lambda *_a, **_k: ({}, {}))
    monkeypatch.setattr(calc_engine, "_reload_policy_band_rates", lambda *_a, **_k: None)
    monkeypatch.setattr(
        calc_engine, "_solve_guideline_state",
        lambda *_a, **_k: SimpleNamespace(glp=5_000.0, gsp=50_000.0, seven_pay=50_000.0))
    return IllustrationEngine().project(
        _policy(), months=12, future_inputs=_inputs(), timing=timing, stop_on_lapse=False,
        options=options, rates_override=rates, bonus_override=BonusConfig())


def _month(states, when: date):
    return next(s for s in states if s.date == when)


@pytest.mark.parametrize("family", ["sgul", "aps205"])
def test_illustration_default_loads_premium_above_the_yearly_target(monkeypatch, family):
    states = _project(monkeypatch, family, IllustrationOptions())
    first = _month(states, date(2026, 5, 15))
    second = _month(states, date(2026, 12, 15))
    assert first.shadow_target_prem == TARGET
    assert first.shadow_prem_load == pytest.approx(TARGET * (TPP if family == "sgul" else 0.0))
    # The 200 above the year's one target is excess: EPP, no N+1 relief.
    assert second.shadow_prem_load == pytest.approx(200.0 * EPP)
    assert second.shadow_net_prem == pytest.approx(200.0 * (1 - EPP))


@pytest.mark.parametrize("family", ["sgul", "aps205"])
def test_setting_on_reproduces_the_nplus1_relief(monkeypatch, family):
    states = _project(monkeypatch, family, IllustrationOptions(shadow_nplus1_relief=True))
    second = _month(states, date(2026, 12, 15))
    # SGUL: within 2 targets and (N+1) targets to date, so TPP; APS205: no load at all.
    assert second.shadow_prem_load == pytest.approx(200.0 * (TPP if family == "sgul" else 0.0))


@pytest.mark.parametrize("family", ["sgul", "aps205"])
def test_setting_changes_only_the_shadow(monkeypatch, family):
    off = _project(monkeypatch, family, IllustrationOptions())
    on = _project(monkeypatch, family, IllustrationOptions(shadow_nplus1_relief=True))
    for a, b in zip(off, on):
        assert a.av_end_of_month == b.av_end_of_month
        assert a.surrender_value == b.surrender_value
    assert _month(on, date(2027, 4, 15)).shadow_eav > _month(off, date(2027, 4, 15)).shadow_eav
