import pytest
from datetime import date

from suiteview.illustration.core.monthly_deduction import calculate_deduction
from suiteview.illustration.core.rate_loader import IllustrationRates
from suiteview.illustration.models.plancode_config import PlancodeConfig
from suiteview.illustration.models.policy_data import BenefitInfo, CoverageSegment, IllustrationPolicyData, RiderInfo


def test_death_benefit_discount_uses_plancode_dbd_not_policy_interest_rate():
    policy = IllustrationPolicyData(
        plancode="1U135D00",
        db_option="A",
        face_amount=100_000.0,
        account_value=10_000.0,
        guaranteed_interest_rate=0.03,
        current_interest_rate=0.03,
        segments=[CoverageSegment(face_amount=100_000.0, units=100.0)],
    )
    config = PlancodeConfig(
        plancode="1U135D00",
        dbd=0.04,
        gint=0.03,
        corridor_code=None,
        epu_code="0",
        mfee="0",
    )

    result = calculate_deduction(
        10_000.0,
        policy,
        config,
        IllustrationRates(),
        rate_year=1,
        attained_age=45,
        premiums_to_date=0.0,
    )

    expected_discount_factor = round((1.0 + 0.04) ** (1.0 / 12.0), 7)
    expected_discounted_db = 100_000.0 / expected_discount_factor
    assert result.discounted_db_cov1 == pytest.approx(expected_discounted_db)
    assert result.discounted_db_cov1 != pytest.approx(100_000.0 / round((1.0 + 0.03) ** (1.0 / 12.0), 7))


def _minimal_policy_with_riders_and_benefits(*, riders=None, benefits=None):
    return IllustrationPolicyData(
        plancode="1U135D00",
        db_option="A",
        face_amount=100_000.0,
        account_value=10_000.0,
        segments=[CoverageSegment(face_amount=100_000.0, units=100.0)],
        riders=riders or [],
        benefits=benefits or [],
    )


def _minimal_config_and_rates():
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
    return config, rates


def test_rider_charge_stops_on_rider_maturity_date():
    rider = RiderInfo(
        plancode="LTR",
        occurrence=1,
        face_amount=50_000.0,
        units=50.0,
        maturity_date=date(2041, 9, 1),
        premium_rate=2.0,
        is_active=True,
    )
    policy = _minimal_policy_with_riders_and_benefits(riders=[rider])
    config, rates = _minimal_config_and_rates()

    before_maturity = calculate_deduction(
        10_000.0,
        policy,
        config,
        rates,
        rate_year=1,
        attained_age=45,
        premiums_to_date=0.0,
        projection_date=date(2041, 8, 1),
    )
    at_maturity = calculate_deduction(
        10_000.0,
        policy,
        config,
        rates,
        rate_year=1,
        attained_age=45,
        premiums_to_date=0.0,
        projection_date=date(2041, 9, 1),
    )
    after_maturity = calculate_deduction(
        10_000.0,
        policy,
        config,
        rates,
        rate_year=1,
        attained_age=45,
        premiums_to_date=0.0,
        projection_date=date(2041, 10, 1),
    )

    assert before_maturity.rider_charges == pytest.approx(100.0)
    assert at_maturity.rider_charges == pytest.approx(0.0)
    assert after_maturity.rider_charges == pytest.approx(0.0)


def test_benefit_charge_stops_on_benefit_cease_date():
    benefit = BenefitInfo(
        benefit_type="2",
        benefit_subtype="1",
        benefit_amount=25_000.0,
        units=25.0,
        cease_date=date(2041, 9, 1),
        coi_rate=1.5,
        is_active=True,
    )
    policy = _minimal_policy_with_riders_and_benefits(benefits=[benefit])
    config, rates = _minimal_config_and_rates()

    before_cease = calculate_deduction(
        10_000.0,
        policy,
        config,
        rates,
        rate_year=1,
        attained_age=45,
        premiums_to_date=0.0,
        projection_date=date(2041, 8, 1),
    )
    at_cease = calculate_deduction(
        10_000.0,
        policy,
        config,
        rates,
        rate_year=1,
        attained_age=45,
        premiums_to_date=0.0,
        projection_date=date(2041, 9, 1),
    )

    assert before_cease.benefit_charges == pytest.approx(37.5)
    assert at_cease.benefit_charges == pytest.approx(0.0)