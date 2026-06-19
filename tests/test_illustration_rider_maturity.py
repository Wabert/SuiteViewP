from datetime import date

import pytest

from suiteview.illustration.core.calc_engine import _primary_insured_rider_face
from suiteview.illustration.core.monthly_deduction import calculate_deduction
from suiteview.illustration.core.rate_loader import IllustrationRates
from suiteview.illustration.models.plancode_config import PlancodeConfig
from suiteview.illustration.models.policy_data import (
    CoverageSegment,
    IllustrationPolicyData,
    RiderInfo,
    rider_effective_maturity_date,
)
from suiteview.illustration.models.rider_config import load_rider_config


def _policy_with_ctr() -> IllustrationPolicyData:
    rider_config = load_rider_config("1A532000")
    assert rider_config is not None
    rider = RiderInfo(
        coverage_phase=2,
        plancode="1A532000",
        occurrence=1,
        issue_date=date(2020, 1, 20),
        issue_age=8,
        face_amount=10_000.0,
        units=10.0,
        maturity_date=date(2050, 1, 20),
        premium_rate=2.0,
        is_active=True,
        on_primary_insured=True,
        cov_type=rider_config.cov_type,
        cease_age_dur=rider_config.cease_age_dur,
        cease_use_code=rider_config.cease_use_code,
    )
    return IllustrationPolicyData(
        plancode="1U135D00",
        db_option="A",
        issue_date=date(2011, 9, 1),
        issue_age=35,
        face_amount=100_000.0,
        account_value=10_000.0,
        segments=[
            CoverageSegment(
                issue_date=date(2011, 9, 1),
                issue_age=35,
                face_amount=100_000.0,
                units=100.0,
            )
        ],
        riders=[rider],
    )


def test_ctr_effective_maturity_uses_first_coverage_attained_age_anniversary():
    policy = _policy_with_ctr()
    rider = policy.riders[0]

    assert rider_effective_maturity_date(rider, policy) == date(2041, 9, 1)


def test_ctr_charge_and_primary_insured_face_stop_on_cease_age_anniversary():
    policy = _policy_with_ctr()
    config = PlancodeConfig(
        plancode="1U135D00",
        dbd=0.04,
        gint=0.03,
        corridor_code=None,
        epu_code="0",
        mfee="0",
        table_rating_factor=0.0,
    )
    rates = IllustrationRates()

    before_maturity = calculate_deduction(
        10_000.0,
        policy,
        config,
        rates,
        rate_year=1,
        attained_age=64,
        premiums_to_date=0.0,
        projection_date=date(2041, 8, 1),
    )
    at_maturity = calculate_deduction(
        10_000.0,
        policy,
        config,
        rates,
        rate_year=1,
        attained_age=65,
        premiums_to_date=0.0,
        projection_date=date(2041, 9, 1),
    )

    assert before_maturity.rider_charges == pytest.approx(20.0)
    assert _primary_insured_rider_face(policy, date(2041, 8, 1)) == pytest.approx(10_000.0)
    assert at_maturity.rider_charges == pytest.approx(0.0)
    assert _primary_insured_rider_face(policy, date(2041, 9, 1)) == pytest.approx(0.0)