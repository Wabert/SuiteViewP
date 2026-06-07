from types import SimpleNamespace

from suiteview.illustration.core.calc_engine import _shadow_rider_charges_from_deduction
from suiteview.illustration.core.shadow_calc import calculate_shadow
from suiteview.illustration.models.plancode_config import PlancodeConfig
from suiteview.illustration.models.policy_data import BenefitInfo, CoverageSegment, IllustrationPolicyData
from suiteview.illustration.core.rate_loader import IllustrationRates


def test_shadow_rider_charges_use_regular_charges_less_ccv():
    policy = IllustrationPolicyData(
        benefits=[
            BenefitInfo(benefit_type="A", benefit_subtype=""),
            BenefitInfo(benefit_type="3", benefit_subtype="9"),
        ]
    )
    deduction = SimpleNamespace(
        rider_charges=12.0,
        benefit_charges=18.0,
        benefit_charge_detail={"A": 5.0, "39": 7.0},
    )

    assert _shadow_rider_charges_from_deduction(policy, deduction) == 25.0


def test_shadow_calculation_applies_regular_rider_charges():
    policy = IllustrationPolicyData(
        face_amount=100_000.0,
        db_option="A",
        ccv_active=True,
        segments=[CoverageSegment(face_amount=100_000.0, original_face_amount=100_000.0)],
    )
    config = PlancodeConfig(
        shadow_epu_code="0",
        shadow_mfee=2.0,
        shadow_dbd_rate="0",
        shadow_int_rate_code="0",
    )

    result = calculate_shadow(
        prev_shadow_eav=100.0,
        gross_premium=0.0,
        premiums_ytd=0.0,
        policy=policy,
        config=config,
        rates=IllustrationRates(shadow_coi=[0.0, 0.0]),
        rate_year=1,
        attained_age=40,
        days_in_month=30,
        policy_debt=0.0,
        shadow_rider_charges=7.5,
    )

    assert result.shadow_rider_charges == 7.5
    assert result.shadow_md == 9.5