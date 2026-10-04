"""Non-renewing benefits (LH_SPM_BNF.RNL_RT_IND 0) keep their issue rate for life.

CyberLife evidence (4,000-case MD matrix, 10/3/2026):
- NU1L2A00 000209639 WPLA 4P: BENCOI 0.0166, stored BNF_ANN_PPU_AMT 0.02; CyberLife
  charges 50 units x 0.02 = 1.00.
- 1A130A29 V8620875 3I: no stored rate; CyberLife charges 0.0117 (the issue-age-31
  rate) on the deduction basis, not the attained-age-71 0.0967.
"""
from datetime import date
from types import SimpleNamespace

from suiteview.illustration.core import calc_engine
from suiteview.illustration.core.illustration_policy_service import build_benefits
from suiteview.illustration.core.rate_loader import IllustrationRates, load_benefit_schedule
from suiteview.illustration.models.policy_data import BenefitInfo, CoverageSegment, IllustrationPolicyData


class _FakeBenefitRates:
    def __init__(self, schedule):
        self.schedule = schedule

    def get_rates(self, *_args, **_kwargs):
        return list(self.schedule)


_ATTAINED_AGE_SCHEDULE = [None, 0.0117, 0.0125, 0.0133, 0.0967]


def _policy(*, renews, stored_rate, benefit_type="3", subtype="I"):
    issue = date(1986, 1, 13)
    segment = CoverageSegment(
        coverage_phase=1, issue_date=issue, issue_age=31, rate_sex="M", rate_class="N",
        band=3, face_amount=100_000.0, units=100.0)
    benefit = BenefitInfo(
        coverage_phase=1, benefit_type=benefit_type, benefit_subtype=subtype, units=100.0,
        issue_date=issue, issue_age=31, coi_rate=stored_rate, is_active=True, renews=renews)
    policy = IllustrationPolicyData(
        plancode="1A130A29", issue_date=issue, issue_age=31, rate_sex="M", rate_class="N", band=3,
        policy_year=41, valuation_date=date(2026, 9, 13), segments=[segment], benefits=[benefit])
    return policy, benefit, segment


def _load(policy, benefit, segment, key="3I"):
    rates = IllustrationRates()
    load_benefit_schedule(rates, _FakeBenefitRates(_ATTAINED_AGE_SCHEDULE), policy, benefit, segment, key)
    return rates


def test_non_renewing_benefit_without_stored_rate_keeps_issue_year_rate():
    policy, benefit, segment = _policy(renews=False, stored_rate=None)

    assert _load(policy, benefit, segment).benefit_coi["3I"] == [None] + [0.0117] * 4


def test_non_renewing_benefit_charges_its_stored_rate():
    policy, benefit, segment = _policy(renews=False, stored_rate=0.02, benefit_type="4", subtype="P")

    assert _load(policy, benefit, segment, "4P").benefit_coi["4P"] == [None] + [0.02] * 4


def test_renewing_benefit_follows_the_database_schedule():
    policy, benefit, segment = _policy(renews=True, stored_rate=0.04)

    assert _load(policy, benefit, segment).benefit_coi["3I"] == _ATTAINED_AGE_SCHEDULE


def test_reband_keeps_non_renewing_rate_level(monkeypatch):
    policy, benefit, segment = _policy(renews=False, stored_rate=None)
    rates = _load(policy, benefit, segment)
    monkeypatch.setattr(
        "suiteview.illustration.core.ul_rates.ULRates",
        lambda *_a, **_k: _FakeBenefitRates([None, 0.5, 0.6, 0.7, 0.8]))

    calc_engine._reband_benefits(rates, policy)

    assert rates.benefit_coi["3I"] == [None] + [0.0117] * 4


def test_build_benefits_maps_the_renewal_indicator():
    def raw(indicator):
        return SimpleNamespace(
            cov_pha_nbr=1, form_number="WPLA", benefit_type_cd="4", benefit_subtype_cd="P",
            benefit_amount=49.5, units=50.0, vpu=0.99, issue_date=date(1990, 9, 13), issue_age=18,
            pay_up_date=date(2032, 9, 13), cease_date=date(2032, 9, 13),
            orig_cease_date=date(2032, 9, 13), rating_factor=1.0,
            coi_rate=0.02, renewal_indicator=indicator)

    assembly = build_benefits(SimpleNamespace(
        raw_benefits=[raw("0"), raw("1"), raw("")], as_of_date=date(2026, 9, 13)))

    assert [b.renews for b in assembly.benefits] == [False, True, True]
