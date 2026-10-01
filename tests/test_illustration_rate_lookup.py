import pytest

from suiteview.illustration.core.rate_loader import (
    IllustrationRates,
    RateLookupError,
    load_coverage_coi_rates,
)
from suiteview.illustration.core import calc_engine
from suiteview.illustration.models.policy_data import CoverageSegment


class _FakeRates:
    def __init__(self, schedules):
        self.schedules = schedules
        self.calls = []

    def get_rates(
        self, rate_type, plancode, issue_age, sex, rateclass, scale=1, band=None, **_kwargs
    ):
        self.calls.append(
            (rate_type, plancode, issue_age, sex, rateclass, scale, band)
        )
        return self.schedules.get(rateclass)

    def is_loaded(self, _plancode):
        return True


@pytest.mark.parametrize("preferred_class", ["R", "P", "T"])
def test_preferred_nonsmoker_falls_back_to_n(preferred_class):
    rates = _FakeRates({"N": [None, 1.25]})

    schedule = load_coverage_coi_rates(
        rates,
        plancode="1U143900",
        issue_age=78,
        sex="M",
        rateclass=preferred_class,
        scale=1,
        band=2,
    )

    assert schedule == [None, 1.25]
    assert [call[4] for call in rates.calls] == [preferred_class, "N"]


def test_preferred_smoker_falls_back_to_s():
    rates = _FakeRates({"S": [None, 2.5]})

    schedule = load_coverage_coi_rates(
        rates,
        plancode="1U143900",
        issue_age=78,
        sex="M",
        rateclass="Q",
        scale=1,
        band=2,
    )

    assert schedule == [None, 2.5]
    assert [call[4] for call in rates.calls] == ["Q", "S"]


def test_exact_preferred_schedule_wins_without_fallback():
    rates = _FakeRates({"R": [None, 0.75], "N": [None, 1.25]})

    schedule = load_coverage_coi_rates(
        rates,
        plancode="1U143900",
        issue_age=78,
        sex="M",
        rateclass="R",
        scale=1,
        band=2,
    )

    assert schedule == [None, 0.75]
    assert [call[4] for call in rates.calls] == ["R"]


def test_missing_coi_raises_detailed_lookup_error():
    rates = _FakeRates({})
    rates.is_loaded = lambda _plancode: False

    with pytest.raises(RateLookupError) as exc_info:
        load_coverage_coi_rates(
            rates,
            plancode="1U143900",
            issue_age=78,
            sex="M",
            rateclass="R",
            scale=1,
            band=2,
        )

    message = str(exc_info.value)
    for detail in (
        "COI",
        "plancode 1U143900",
        "issue age 78",
        "sex M",
        "rate class R then rate class N",
        "band 2",
        "scale 1",
        "not loaded in UL_Rates schema rates",
    ):
        assert detail in message


def test_face_decrease_reband_uses_preferred_class_fallback(monkeypatch):
    class _RebandRates(_FakeRates):
        def get_band(self, _plancode, _face, issue_date=None, **_kwargs):
            return 2

    rates_db = _RebandRates({"N": [None, 1.25]})
    monkeypatch.setattr("suiteview.illustration.core.ul_rates.ULRates", lambda *_args, **_kwargs: rates_db)
    segment = CoverageSegment(
        coverage_phase=1,
        issue_age=45,
        rate_sex="M",
        rate_class="R",
        face_amount=50_000.0,
        band=1,
    )
    rates = IllustrationRates(
        segment_coi={1: [None, 0.75]},
        segment_epu={1: []},
    )

    calc_engine._reband_segment(
        rates, segment, "1U143900", band=2
    )

    assert segment.band == 2
    assert rates.segment_coi[1] == [None, 1.25]
    assert [call[4] for call in rates_db.calls[:2]] == ["R", "N"]


def test_face_decrease_reband_never_keeps_a_zero_coi_on_missing_rate(monkeypatch):
    class _RebandRates(_FakeRates):
        def get_band(self, _plancode, _face, issue_date=None, **_kwargs):
            return 2

    monkeypatch.setattr(
        "suiteview.illustration.core.ul_rates.ULRates",
        lambda *_args, **_kwargs: _RebandRates({}),
    )
    segment = CoverageSegment(
        coverage_phase=1,
        issue_age=45,
        rate_sex="M",
        rate_class="R",
        face_amount=50_000.0,
        band=1,
    )
    rates = IllustrationRates(segment_coi={1: [None, 0.75]})

    with pytest.raises(RateLookupError, match="band 2"):
        calc_engine._reband_segment(
            rates, segment, "1U143900", band=2
        )


class _FakeBenefitRates:
    """BENCOI lookups keyed by benefit type."""

    def __init__(self, schedules):
        self.schedules = schedules

    def get_rates(self, rate_type, plancode, benefit_type=None, **_kwargs):
        assert rate_type == "BENCOI"
        return self.schedules.get(benefit_type)


def _benefit_policy(*benefits):
    from datetime import date

    from suiteview.illustration.models.policy_data import IllustrationPolicyData

    segment = CoverageSegment(
        coverage_phase=1, issue_age=45, rate_sex="M", rate_class="N",
        face_amount=100_000.0, band=1, issue_date=date(2020, 1, 15),
    )
    return IllustrationPolicyData(
        plancode="1U1F4L00", issue_date=date(2020, 1, 15),
        valuation_date=date(2026, 1, 15), segments=[segment], benefits=list(benefits),
    ), segment


def test_chargeable_benefit_without_bencoi_raises_instead_of_charging_zero():
    from suiteview.illustration.core.rate_loader import _load_benefit_rates
    from suiteview.illustration.models.policy_data import BenefitInfo

    policy, segment = _benefit_policy(
        BenefitInfo(coverage_phase=1, benefit_type="3", benefit_subtype="F", is_active=True))

    with pytest.raises(RateLookupError, match="chargeable benefit 3F on plancode 1U1F4L00"):
        _load_benefit_rates(IllustrationRates(), policy, _FakeBenefitRates({}), segment)


def test_non_charging_and_paid_up_benefits_may_have_no_bencoi():
    from datetime import date

    from suiteview.illustration.core.rate_loader import _load_benefit_rates
    from suiteview.illustration.models.policy_data import BenefitInfo

    policy, segment = _benefit_policy(
        BenefitInfo(coverage_phase=1, benefit_type="A", benefit_subtype="0", is_active=True),
        BenefitInfo(coverage_phase=1, benefit_type="V", benefit_subtype="1", is_active=True),
        BenefitInfo(coverage_phase=1, benefit_type="1", benefit_subtype="0", is_active=True,
                    pay_up_date=date(2025, 1, 15)),
        BenefitInfo(coverage_phase=1, benefit_type="3", benefit_subtype="9", is_active=True),
    )
    rates = IllustrationRates()

    _load_benefit_rates(rates, policy, _FakeBenefitRates({"39": [None, 0.05]}), segment)

    assert rates.benefit_coi["39"] == [None, 0.05]
    assert rates.benefit_coi["A0"] == []
    assert rates.benefit_coi["10"] == []
