from datetime import date

from suiteview.illustration.core import calc_engine
from suiteview.illustration.core.rate_loader import IllustrationRates, load_benefit_schedule
from suiteview.illustration.core.rate_validation import (
    benefit_rate_override_warnings,
    missing_required_rate_warnings,
)
from suiteview.illustration.models.policy_data import (
    BenefitInfo,
    CoverageSegment,
    IllustrationPolicyData,
    RiderInfo,
)


class _FakeBenefitRates:
    """BENCOI lookups keyed by rate class; records every request."""

    def __init__(self, by_class):
        self.by_class = by_class
        self.requests = []

    def get_rates(self, rate_type, plancode, issue_age, sex, rateclass, scale=1, band=1, **kwargs):
        self.requests.append((rate_type, plancode, issue_age, sex, rateclass, band, kwargs))
        return list(self.by_class.get(rateclass, []))


def _ccv_policy(stored_rate, *, benefit_type="A", rate_class="N"):
    issue = date(2016, 1, 5)
    segment = CoverageSegment(
        coverage_phase=1, issue_date=issue, issue_age=59, rate_sex="M",
        rate_class=rate_class, band=3, face_amount=100_000.0, units=100.0)
    benefit = BenefitInfo(
        coverage_phase=1, benefit_type=benefit_type, benefit_subtype="1", units=100.0,
        issue_date=issue, issue_age=59, coi_rate=stored_rate, is_active=True)
    policy = IllustrationPolicyData(
        plancode="1U143900", issue_date=issue, issue_age=59, rate_sex="M",
        rate_class=rate_class, band=3, policy_year=11, valuation_date=date(2026, 9, 5),
        segments=[segment], benefits=[benefit])
    return policy, benefit, segment


_LEVEL_N = [None] + [0.75] * 41
_LEVEL_S = [None] + [0.87] * 41


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


def test_ccv_rate_on_policy_record_overrides_database_rate_class_schedule():
    """UIP73567: nonsmoker coverage, CCV still charged at the smoker 0.87 rate."""
    policy, benefit, segment = _ccv_policy(0.87)
    rates_db = _FakeBenefitRates({"N": _LEVEL_N, "S": _LEVEL_S})
    rates = IllustrationRates()

    load_benefit_schedule(rates, rates_db, policy, benefit, segment, "A1")

    assert rates.benefit_coi["A1"] == [None] + [0.87] * 41
    override = rates.benefit_rate_overrides["A1"]
    assert (override.database_rate, override.policy_rate, override.rate_class) == (0.75, 0.87, "N")
    assert rates_db.requests[0][4] == "N"
    assert benefit_rate_override_warnings(rates) == [
        "CCV benefit A1 rate on the policy record (0.87) does not match the rates database "
        "(0.75 for rate class N); the coverage rate class may have changed since the CCV was "
        "issued. The illustration uses the policy record rate for the CCV charge."
    ]


def test_ccv_rate_matching_database_keeps_database_schedule_without_notice():
    policy, benefit, segment = _ccv_policy(0.75)
    rates = IllustrationRates()

    load_benefit_schedule(rates, _FakeBenefitRates({"N": _LEVEL_N}), policy, benefit, segment, "A1")

    assert rates.benefit_coi["A1"] == _LEVEL_N
    assert rates.benefit_rate_overrides == {}
    assert benefit_rate_override_warnings(rates) == []


def test_ccv_without_stored_charge_keeps_database_schedule():
    """No stored CCV rate (uncharged CCV, or an issue/edited-amount run) means no override."""
    for stored_rate in (None, 0.0):
        policy, benefit, segment = _ccv_policy(stored_rate)
        rates = IllustrationRates()

        load_benefit_schedule(rates, _FakeBenefitRates({"N": _LEVEL_N}), policy, benefit, segment, "A1")

        assert rates.benefit_coi["A1"] == _LEVEL_N
        assert rates.benefit_rate_overrides == {}


def test_non_ccv_benefit_rate_mismatch_keeps_database_schedule():
    policy, benefit, segment = _ccv_policy(0.87, benefit_type="7")
    rates = IllustrationRates()

    load_benefit_schedule(rates, _FakeBenefitRates({"N": _LEVEL_N}), policy, benefit, segment, "71")

    assert rates.benefit_coi["71"] == _LEVEL_N
    assert rates.benefit_rate_overrides == {}


def test_reband_keeps_ccv_schedule_pinned_to_policy_record_rate(monkeypatch):
    policy, benefit, segment = _ccv_policy(0.87)
    rates = IllustrationRates()
    load_benefit_schedule(rates, _FakeBenefitRates({"N": _LEVEL_N}), policy, benefit, segment, "A1")
    monkeypatch.setattr(
        "suiteview.illustration.core.ul_rates.ULRates",
        lambda *_a, **_k: _FakeBenefitRates({"N": [None] + [0.70] * 41}))

    calc_engine._reband_benefits(rates, policy)

    assert rates.benefit_coi["A1"] == [None] + [0.87] * 41