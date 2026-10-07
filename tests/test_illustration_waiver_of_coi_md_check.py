"""Waiver of COI (premium pay status 34): the recorded monthliversary AV is pre-deduction.

CyberLife records LH_POL_MVRY_VAL.CSV_AMT before the monthly deduction while the
policy is on Waiver of COI; the fund value (LH_POL_FND_VAL_TOT) is after it.
26/000173969 on 10/03/2026: CSV_AMT 91,372.92 = fund 91,231.52 + CINS_AMT 138.90 +
EXP_CRG_AMT 2.50, and NAR_AMT 175,819.20 = discounted DB 267,192.12 - 91,372.92.
Offline: rates are a small fake and target premiums (unused by the MD check) are stubbed.
"""

import copy
from datetime import date

import pytest

from suiteview.core.rates import Rates
from suiteview.illustration.core import calc_engine
from suiteview.illustration.core.bonus_rates import BonusConfig
from suiteview.illustration.core.rate_loader import IllustrationRates
from suiteview.illustration.core.target_premium import TargetPremiumResult
from suiteview.illustration.models.policy_data import CoverageSegment, IllustrationPolicyData


def _segment(phase, face, original, issue, issue_age):
    return CoverageSegment(
        coverage_phase=phase, issue_date=issue, issue_age=issue_age, rate_sex="M",
        rate_class="H", face_amount=face, original_face_amount=original, units=face / 1000.0)


def _policy(status):
    """000173969's base phase and first COLA phase on the 10/03/2026 monthliversary."""
    return IllustrationPolicyData(
        policy_number="000173969", company_code="26", plancode="NU1FU200",
        premium_pay_status_code=status, issue_date=date(1986, 4, 3),
        valuation_date=date(2026, 10, 3), issue_age=22, attained_age=62, rate_sex="M",
        rate_class="H", maturity_age=95, policy_year=41, policy_month=7, duration=487,
        face_amount=115_650.0, units=115.65, db_option="A", band=2,
        account_value=91_372.92, system_coi_charge=18.84, system_expense_charge=2.50,
        system_monthly_deduction=21.34, current_interest_rate=0.045,
        guaranteed_interest_rate=0.045,
        segments=[
            _segment(1, 105_410.0, 100_000.0, date(1986, 4, 3), 22),
            _segment(6, 10_240.0, 10_240.0, date(1989, 4, 3), 25),
        ])


@pytest.fixture
def project(monkeypatch):
    rates = IllustrationRates(
        segment_coi={1: [None] + [0.79] * 60, 6: [None] + [0.79] * 60},
        mfee=[None] + [2.5] * 60)
    monkeypatch.setattr(calc_engine, "load_bonus_config", lambda *_: BonusConfig())
    monkeypatch.setattr(calc_engine.IllustrationEngine, "_load_rates", lambda *_: rates)
    monkeypatch.setattr(Rates, "get_band", lambda *_a, **_k: None)
    monkeypatch.setattr(calc_engine, "compute_target_premiums", lambda *_a, **_k: TargetPremiumResult())
    monkeypatch.setattr(calc_engine, "build_target_detail_snapshots", lambda *_a, **_k: ({}, {}))

    def run(status):
        return calc_engine.IllustrationEngine().project(copy.deepcopy(_policy(status)), months=0)[0]
    return run


def test_waiver_of_coi_recorded_av_already_includes_the_deduction(project):
    state = project("34")
    assert state.md_check_av_before_deduction == pytest.approx(91_372.92)
    # NAR 105,024.06 - 91,372.92 = 13,651.14 at 0.79 -> 10.78; COLA 8.06; fee 2.50.
    assert state.md_check_calculated_deduction == pytest.approx(21.34)
    assert state.md_check_av_variance == pytest.approx(0.0, abs=0.005)


def test_other_statuses_add_the_recorded_deduction_back(project):
    state = project("22")
    assert state.md_check_av_before_deduction == pytest.approx(91_372.92 + 21.34)
    assert state.md_check_calculated_deduction == pytest.approx(21.33)
