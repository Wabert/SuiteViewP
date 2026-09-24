"""Raw waiver target percentages must not become 100-fold target charges."""

from copy import deepcopy
from datetime import date

import pytest

import suiteview.core.rates as rates_module
from suiteview.illustration.core.target_premium import (
    build_target_detail_snapshots,
    compute_target_premiums,
)
from suiteview.illustration.models.plancode_config import PlancodeConfig
from suiteview.illustration.models.policy_data import (
    BenefitInfo, CoverageSegment, IllustrationPolicyData, RiderInfo,
)


class _Rates:
    pw_rate = 5.5

    def get_band(self, plancode, specified_amount, issue_date=None):
        return 3 if specified_amount >= 100_000 else 2

    def get_mtp(self, plancode, issue_age, sex, rateclass, band):
        return (3.6 if issue_age == 25 else 4.54) if band == 3 else 5.0

    def get_ctp(self, plancode, issue_age, sex, rateclass, band):
        return (3.6 if issue_age == 25 else 5.76) if band == 3 else 5.0

    def get_tbl1_mtp(self, plancode, issue_age, sex, rateclass, band):
        return (0.9 if issue_age == 25 else 1.14) if band == 3 else 1.25

    get_tbl1_ctp = get_tbl1_mtp

    def get_ben_mtp(self, *args):
        return self.pw_rate

    def get_ben_ctp(self, *args):
        return self.pw_rate


def _policy(increased=False, benefit_key="39"):
    policy = IllustrationPolicyData(
        plancode="1U143900", issue_date=date(2014, 11, 26), issue_age=25,
        face_amount=100_000.0 if increased else 50_000.0,
        segments=[CoverageSegment(
            coverage_phase=1, issue_age=25, issue_date=date(2014, 11, 26),
            rate_sex="F", rate_class="N", face_amount=50_000,
            original_face_amount=50_000, band=2, original_band=2,
            table_rating=2,
        )],
        benefits=[BenefitInfo(
            benefit_type=benefit_key[0], benefit_subtype=benefit_key[1],
            is_active=True, pay_up_date=date(2049, 11, 26),
        )],
        riders=[RiderInfo(
            coverage_phase=2, occurrence=1, plancode="1U538F00",
            cov_type="CTR", units=10, is_active=True,
        )],
    )
    if increased:
        policy.segments.append(CoverageSegment(
            coverage_phase=2, issue_age=36, issue_date=date(2026, 9, 26),
            rate_sex="F", rate_class="N", face_amount=50_000,
            original_face_amount=50_000, band=3, original_band=3,
            table_rating=2,
        ))
    return policy


@pytest.fixture
def rates(monkeypatch):
    rates = _Rates()
    monkeypatch.setattr(rates_module, "Rates", lambda: rates)
    return rates


@pytest.mark.parametrize("benefit_key", ["39", "3#"])
@pytest.mark.parametrize("increased, annual, monthly, ctp, pw", [
    (False, 490.3725, 40.86, 490.37, 37.3725),
    (True, 745.8425, 62.15, 806.84, 56.8425),
])
def test_uip45890_target_reconciliation(rates, benefit_key, increased, annual, monthly, ctp, pw):
    policy = _policy(increased, benefit_key)
    original = deepcopy(policy)
    result = compute_target_premiums(
        policy, PlancodeConfig(), as_of=date(2026, 9, 26),
    )
    assert result.pw_rate == 5.5
    assert result.pw_component == pytest.approx(pw)
    assert result.mtp_annual == pytest.approx(annual)
    assert result.mtp_monthly == monthly
    assert result.ctp_annual == pytest.approx(ctp)
    mtp_detail, ctp_detail = build_target_detail_snapshots(policy, result)
    assert mtp_detail["PW MTPR"] == 5.5
    assert mtp_detail["PW MTP"] == pytest.approx(pw)
    assert mtp_detail["vMTP"] == pytest.approx(annual)
    assert ctp_detail["vCTP"] == pytest.approx(ctp)
    assert policy == original


@pytest.mark.parametrize("rate", [0.0, 0.5, 5.5])
@pytest.mark.parametrize("benefit_key, divisor", [("39", 100), ("3#", 100), ("3F", 1)])
def test_conversion_uses_benefit_units_not_rate_magnitude(rates, rate, benefit_key, divisor):
    rates.pw_rate = rate
    result = compute_target_premiums(_policy(benefit_key=benefit_key), PlancodeConfig())
    assert result.pw_rate == rate
    assert result.pw_component == pytest.approx(453 * rate / divisor * 1.5)


@pytest.mark.parametrize("inactive", [False, True])
def test_ceased_or_inactive_waiver_has_no_target(rates, inactive):
    policy = _policy()
    policy.benefits[0].is_active = not inactive
    result = compute_target_premiums(
        policy, PlancodeConfig(), as_of=date(2049, 11, 26),
    )
    assert result.pw_component == 0
    assert result.pw_rate == 0
