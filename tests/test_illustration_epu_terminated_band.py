"""The EPU band counts terminated base-plan phases still on the record.

1U145500 UIP61566: phases 56,347 (2015) and 53,653 (2023) in force, phase 2 of 143,566
terminated on its 2023 issue date. CyberLife charges phase 3's EPU at band 3 (0.771 x
original 143.653 = 110.76; in-force 110,000 alone is band 2, 0.766), while its stored
COI rows stay band B. UE000135 (+0.26) and UIP69169 (+0.58) reproduce the same way.
"""
from datetime import date

from suiteview.illustration.core import calc_engine
from suiteview.illustration.core.rate_loader import IllustrationRates, epu_band
from suiteview.illustration.models.policy_data import CoverageSegment, IllustrationPolicyData

ISSUE = date(2015, 7, 1)


class _BandRates:
    """Pre-2018 1U145500 band limits: 99,999.99 / 250,000.99 / 499,999.99."""

    def __init__(self):
        self.amounts = []
        self.epu_bands = []

    def get_band(self, _plancode, amount, issue_date=None, **_kwargs):
        self.amounts.append(amount)
        return 1 if amount < 100_000 else 2 if amount <= 250_000.99 else 3

    def get_rates(self, kind, *_args, band=None, **_kwargs):
        if kind == "EPU":
            self.epu_bands.append(band)
        return [None, {1: 0.7, 2: 0.766, 3: 0.771}.get(band, 0.0)]


def _policy(terminated):
    segments = [
        CoverageSegment(coverage_phase=1, issue_date=ISSUE, issue_age=51, rate_sex="M", rate_class="N",
                        face_amount=56_347.0, original_face_amount=50_000.0, units=56.347, band=2),
        CoverageSegment(coverage_phase=3, issue_date=date(2023, 10, 1), issue_age=59, rate_sex="M",
                        rate_class="N", face_amount=53_653.0, original_face_amount=143_653.0,
                        units=53.653, band=2),
    ]
    return IllustrationPolicyData(plancode="1U145500", issue_date=ISSUE, band=2, segments=segments,
                                  terminated_base_face=terminated)


def test_epu_band_counts_terminated_base_phases():
    rates_db = _BandRates()
    policy = _policy(143_566.0)

    assert policy.epu_band_specified_amount == 253_566.0
    assert epu_band(rates_db, policy, policy.band) == 3
    assert rates_db.amounts == [253_566.0]


def test_without_terminated_phases_the_epu_band_is_the_policy_band():
    rates_db = _BandRates()

    assert epu_band(rates_db, _policy(0.0), 2) == 2
    assert rates_db.amounts == []


def test_increase_segment_epu_uses_the_terminated_inclusive_band(monkeypatch):
    rates_db = _BandRates()
    monkeypatch.setattr("suiteview.illustration.core.ul_rates.ULRates", lambda *_a, **_k: rates_db)
    monkeypatch.setattr(calc_engine, "load_segment_coi", lambda *_a, **_k: [None, 0.3])
    monkeypatch.setattr(calc_engine, "load_segment_scr", lambda *_a, **_k: [None, 0.0])
    policy = _policy(143_566.0)
    rates = IllustrationRates()

    calc_engine._load_segment_rates(rates, policy.segments[1], "1U145500", object(), policy=policy)

    assert rates_db.epu_bands == [3]
    assert rates.segment_epu[3] == [None, 0.771]
    assert rates.segment_epu_band[3] == 3


def _reband(monkeypatch, policy, loaded_epu_band):
    rates_db = _BandRates()
    coi_loads = []
    monkeypatch.setattr("suiteview.illustration.core.ul_rates.ULRates", lambda *_a, **_k: rates_db)
    monkeypatch.setattr(calc_engine, "load_segment_coi", lambda *_a, **_k: coi_loads.append(1) or [None, 0.3])
    segment = policy.segments[1]
    rates = IllustrationRates(segment_coi={3: [None, 0.3]}, segment_epu={3: [None, 0.771]},
                              segment_epu_band={3: loaded_epu_band})
    calc_engine._reband_segment(rates, segment, "1U145500", band=segment.band, policy=policy)
    return rates, rates_db, coi_loads


def test_reband_reloads_epu_when_only_the_epu_band_crosses(monkeypatch):
    """150,000 terminated; in-force 110,000 -> 100,000 keeps COI band 2 but moves the EPU
    basis 260,000 -> 250,000 (band 3 -> 2)."""
    policy = _policy(150_000.0)
    policy.segments[0].face_amount = 46_347.0

    rates, rates_db, coi_loads = _reband(monkeypatch, policy, loaded_epu_band=3)

    assert coi_loads == []
    assert rates_db.epu_bands == [2]
    assert rates.segment_epu[3] == [None, 0.766]
    assert rates.segment_epu_band[3] == 2


def test_reband_keeps_epu_when_its_band_is_unchanged(monkeypatch):
    policy = _policy(150_000.0)

    rates, rates_db, coi_loads = _reband(monkeypatch, policy, loaded_epu_band=3)

    assert (coi_loads, rates_db.epu_bands) == ([], [])
    assert rates.segment_epu[3] == [None, 0.771]
