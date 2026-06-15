import pytest

from suiteview.illustration.core.monthly_deduction import calculate_deduction
from suiteview.illustration.core.rate_loader import IllustrationRates
from suiteview.illustration.models.plancode_config import PlancodeConfig
from suiteview.illustration.models.policy_data import CoverageSegment, IllustrationPolicyData


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