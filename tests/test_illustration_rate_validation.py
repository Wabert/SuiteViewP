from suiteview.illustration.core.rate_loader import IllustrationRates
from suiteview.illustration.core.rate_validation import missing_required_rate_warnings
from suiteview.illustration.models.policy_data import BenefitInfo, IllustrationPolicyData, RiderInfo


def test_missing_required_rate_warnings_flags_active_riders_and_required_benefits():
    policy = IllustrationPolicyData(
        benefits=[
            BenefitInfo(benefit_type="3", benefit_subtype="9", is_active=True),
            BenefitInfo(benefit_type="A", benefit_subtype="", is_active=True),
            BenefitInfo(benefit_type="7", benefit_subtype="6", is_active=False),
        ],
        riders=[
            RiderInfo(plancode="1U536C00", occurrence=1, is_active=True),
            RiderInfo(plancode="1U777D00", occurrence=1, is_active=False),
        ],
    )

    warnings = missing_required_rate_warnings(policy, IllustrationRates())

    assert warnings == [
        "Missing illustration rates for active rider/benefit charges: Benefit 39, Rider 1U536C00_1"
    ]


def test_missing_required_rate_warnings_is_clear_when_required_schedules_are_loaded():
    policy = IllustrationPolicyData(
        benefits=[BenefitInfo(benefit_type="4", benefit_subtype="1", is_active=True)],
        riders=[RiderInfo(plancode="1U536C00", occurrence=1, is_active=True)],
    )
    rates = IllustrationRates(
        benefit_coi={"41": [None, 0.1]},
        rider_rates={"1U536C00_1": [None, 0.2]},
    )

    assert missing_required_rate_warnings(policy, rates) == []