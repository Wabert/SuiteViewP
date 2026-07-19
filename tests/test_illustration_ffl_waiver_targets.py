"""FFL premium waiver target basis (RERUN CalcEngine IW..JD, sblnFFL).

FFL products (plancode CompanySub = "FFL") replace both waiver targets:

    PWoC (benefit type 3, IV) = JB = TRUNC(pwRate·IZ·(1+factor·table), 2)
    PWoT (benefit type 4, IK) = JD = TRUNC(JA·JC, 2)
    PWoT CTP (KE)             = JC·vMTP

Non-FFL products keep units×rate (IK) and rate×IT (IV). The fake rates DB
below pins every lookup so the expected values are hand-computable.
"""
from __future__ import annotations

from datetime import date

import pytest

import suiteview.core.rates as rates_module
from suiteview.illustration.core.target_premium import compute_target_premiums
from suiteview.illustration.models.plancode_config import PlancodeConfig
from suiteview.illustration.models.policy_data import (
    BenefitInfo,
    CoverageSegment,
    IllustrationPolicyData,
)


class _FakeRates:
    """Pinned rate lookups for a single-coverage FFL test policy."""

    MTP_RATE = 20.0        # HO — coverage MTP per 1000
    CTP_RATE = 24.0        # coverage CTP per 1000
    PW_RATE = 0.06         # IU — PWoC MTPR (benefit "39")
    PWST_RATE = 8.0        # IJ — PWoT MTPR per 100 (benefit "49")
    PWST_CTP_RATE = 9.0    # KD
    ADB_RATE = 0.5         # generic benefit (units × rate)
    COI_YEAR1 = 1.2        # current COI select rate, duration 1
    MFEE_YEAR1 = 3.0       # monthly fee, duration 1

    def get_band(self, plancode, specified_amount, issue_date=None):
        return 1

    def get_mtp(self, *args):
        return self.MTP_RATE

    def get_tbl1_mtp(self, *args):
        return 0.0

    def get_ctp(self, *args):
        return self.CTP_RATE

    def get_tbl1_ctp(self, *args):
        return 0.0

    def get_ben_mtp(self, plancode, issue_age, sex, rateclass, band, benefit_type):
        return {"39": self.PW_RATE, "49": self.PWST_RATE, "71": self.ADB_RATE}.get(
            benefit_type, 0.0
        )

    def get_ben_ctp(self, plancode, issue_age, sex, rateclass, band, benefit_type):
        return {"39": self.PW_RATE, "49": self.PWST_CTP_RATE, "71": self.ADB_RATE}.get(
            benefit_type, 0.0
        )

    def get_rates(self, table, *args, **kwargs):
        # 1-indexed by duration (index 0 is unused key slot).
        if table == "COI":
            return [None, self.COI_YEAR1, 1.4, 1.6]
        if table == "MFEE":
            return [None, self.MFEE_YEAR1, 3.0, 3.0]
        return []


@pytest.fixture
def fake_rates(monkeypatch):
    fake = _FakeRates()
    monkeypatch.setattr(rates_module, "Rates", lambda: fake)
    return fake


def _make_policy() -> IllustrationPolicyData:
    seg = CoverageSegment(
        coverage_phase=1,
        issue_date=date(2020, 6, 9),
        issue_age=45,
        rate_sex="M",
        rate_class="N",
        face_amount=100_000.0,
        original_face_amount=100_000.0,
        band=1,
        original_band=1,
    )
    policy = IllustrationPolicyData(
        plancode="NU1F3A00",
        issue_date=date(2020, 6, 9),
        issue_age=45,
    )
    policy.segments = [seg]
    policy.benefits = [
        BenefitInfo(benefit_type="3", benefit_subtype="9", units=0.0),
        BenefitInfo(benefit_type="4", benefit_subtype="9", units=50.0),
        BenefitInfo(benefit_type="7", benefit_subtype="1", units=10.0),
    ]
    return policy


def _config(company_sub: str) -> PlancodeConfig:
    return PlancodeConfig(
        plancode="NU1F3A00",
        company_sub=company_sub,
        mfee="Table",
        premium_cease_age=100,
        dynamic_banding=3,
        table_rating_factor=0.25,
    )


def test_ffl_waiver_targets_use_cost_bases(fake_rates):
    policy = _make_policy()
    result = compute_target_premiums(policy, _config("FFL"), as_of=date(2020, 6, 9))

    # Coverage MTP (HW): 100000·20/1000 = 2000; generic benefit: 10·0.5 = 5.
    assert result.mtp_by_coverage[1] == pytest.approx(2000.0)

    # IW: 1.2·100000/1000 = 120; IX/IY = 0 (no table, no flat).
    assert result.ffl_min_base == pytest.approx(120.0)
    # IZ = 5/12 + 120 + 3 = 123.41666...
    iz = 5.0 / 12.0 + 120.0 + 3.0
    assert result.ffl_pwoc_basis == pytest.approx(iz)
    # JB = TRUNC(0.06·IZ, 2) = TRUNC(7.405, 2) = 7.40.
    assert result.pw_component == pytest.approx(7.40)
    # JA = 2000 + 5 + 7.40 = 2012.40.
    assert result.ffl_pwot_basis == pytest.approx(2012.40)
    # JC = TRUNC(0.08/(1-0.08), 5) = TRUNC(0.086956..., 5) = 0.08695.
    assert result.ffl_pwot_factor == pytest.approx(0.08695)
    # JD = TRUNC(2012.40·0.08695, 2) = TRUNC(174.978..., 2) = 174.97.
    assert result.pwst_component == pytest.approx(174.97)

    # JG = 2000 + 5 + 174.97 + 7.40 = 2187.37.
    assert result.mtp_annual == pytest.approx(2187.37)

    # KE = JC·JG = 0.08695·2187.37; KQ = cov CTP + generic + KE + ROUND(JB, 2).
    ke = 0.08695 * 2187.37
    assert result.pwst_ctp_component == pytest.approx(ke)
    assert result.ctp_annual == pytest.approx(2400.0 + 5.0 + ke + 7.40)


def test_non_ffl_waiver_targets_use_units_times_rate(fake_rates):
    policy = _make_policy()
    result = compute_target_premiums(policy, _config("ANICO"), as_of=date(2020, 6, 9))

    # IK = units·rate = 50·8 = 400 (no table rating).
    assert result.pwst_component == pytest.approx(400.0)
    # IT = 2000 + 5 + 400 = 2405; IV = 0.06·2405 = 144.30.
    assert result.mtp_wo_pw == pytest.approx(2405.0)
    assert result.pw_component == pytest.approx(144.30)
    assert result.mtp_annual == pytest.approx(2549.30)
    # KE = 50·9 = 450; vCTP = 2400 + 5 + 450 + 144.30.
    assert result.pwst_ctp_component == pytest.approx(450.0)
    assert result.ctp_annual == pytest.approx(2999.30)
    # No FFL bases populated.
    assert result.ffl_pwoc_basis == 0.0
    assert result.ffl_pwot_basis == 0.0


def test_ffl_table_rating_flows_through_waiver_bases(fake_rates):
    policy = _make_policy()
    policy.segments[0].table_rating = 2  # Table B
    result = compute_target_premiums(policy, _config("FFL"), as_of=date(2020, 6, 9))

    # IX = 1.2·2·100000·0.25/1000 = 60; IZ = 5/12 + 120 + 60 + 3.
    iz = 5.0 / 12.0 + 120.0 + 60.0 + 3.0
    assert result.ffl_pwoc_basis == pytest.approx(iz)
    # JB = TRUNC(0.06·IZ·(1 + 0.25·2), 2) = TRUNC(16.5075, 2) = 16.50.
    assert result.pw_component == pytest.approx(16.50)
    # JC: x = 0.08·1.5 = 0.12 → TRUNC(0.12/0.88, 5) = 0.13636.
    assert result.ffl_pwot_factor == pytest.approx(0.13636)


def test_plancode_table_carries_company_sub():
    from suiteview.illustration.models.plancode_config import load_plancode

    assert load_plancode("NU1F3A00").is_ffl
    assert not load_plancode("1U143900").is_ffl
