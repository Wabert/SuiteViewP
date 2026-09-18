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
        self, rate_type, plancode, issue_age, sex, rateclass, scale=1, band=None
    ):
        self.calls.append(
            (rate_type, plancode, issue_age, sex, rateclass, scale, band)
        )
        return self.schedules.get(rateclass)


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
    ):
        assert detail in message


def test_face_decrease_reband_uses_preferred_class_fallback(monkeypatch):
    class _RebandRates(_FakeRates):
        def get_band(self, _plancode, _face, issue_date=None):
            return 2

    rates_db = _RebandRates({"N": [None, 1.25]})
    monkeypatch.setattr("suiteview.core.rates.Rates", lambda: rates_db)
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
        def get_band(self, _plancode, _face, issue_date=None):
            return 2

    monkeypatch.setattr(
        "suiteview.core.rates.Rates", lambda: _RebandRates({})
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
