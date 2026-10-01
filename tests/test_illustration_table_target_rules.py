"""CyberLife's table-rating target rules (Robert, 10/1/2026).

Production evidence: ZZTaskRepo S0503253-table-rated-target-premiums (S0503253,
U0609076, UE000157).

* both CTP_TBL1 and MTP_TBL1 present -> per-table rates (unchanged);
* only CTP_TBL1 present              -> the MTP uses the CTP_TBL1 rate;
* neither present                    -> table % x COI (CTP: COI at the as-of
  coverage year; MTP: COI frozen at the MAP end).
"""
from datetime import date

import pytest

from suiteview.illustration.core.rate_loader import RateLookupError
from suiteview.illustration.core.target_premium import (
    TABLE_METHOD_COI,
    TABLE_METHOD_CTP_FOR_MTP,
    TABLE_METHOD_RATE,
    compute_target_premiums,
)
from suiteview.illustration.models.plancode_config import PlancodeConfig
from suiteview.illustration.models.policy_data import CoverageSegment, IllustrationPolicyData


class _Rates:
    """Schema-rates stand-in: per-unit target rates and a COI schedule by duration."""

    def __init__(self, *, mtp, ctp, tbl_mtp=None, tbl_ctp=None, coi=None):
        self._v = {"mtp": mtp, "ctp": ctp, "tbl_mtp": tbl_mtp, "tbl_ctp": tbl_ctp}
        self._coi = coi
        self.coi_lookups = []

    def get_band(self, *args, **kwargs):
        return 1

    def get_mtp(self, *args, **kwargs):
        return self._v["mtp"]

    def get_ctp(self, *args, **kwargs):
        return self._v["ctp"]

    def get_tbl1_mtp(self, *args, **kwargs):
        return self._v["tbl_mtp"]

    def get_tbl1_ctp(self, *args, **kwargs):
        return self._v["tbl_ctp"]

    def get_rates(self, kind, plancode, issue_age, sex, rateclass, scale=1, band=None, **_kw):
        assert kind == "COI" and scale == 1
        self.coi_lookups.append((plancode, issue_age, sex, rateclass, band))
        return self._coi

    def is_loaded(self, _plancode):
        return True


def _coi(**by_duration):
    """1-indexed COI schedule from ``d1=0.11, d42=0.77392`` keywords (gaps repeat)."""
    last = max(int(key[1:]) for key in by_duration)
    schedule, value = [None], 0.0
    for duration in range(1, last + 1):
        value = by_duration.get(f"d{duration}", value)
        schedule.append(value)
    return schedule


def _project(monkeypatch, rates, *, plancode, issue, age, sex, units, table, as_of,
             map_end=None, band=1):
    monkeypatch.setattr("suiteview.illustration.core.ul_rates.ULRates", lambda *_a, **_k: rates)
    face = units * 1000.0
    segment = CoverageSegment(
        coverage_phase=1, issue_date=issue, issue_age=age, rate_sex=sex, rate_class="N",
        face_amount=face, original_face_amount=face, band=band, original_band=band,
        table_rating=table,
    )
    policy = IllustrationPolicyData(
        plancode=plancode, issue_date=issue, issue_age=age, face_amount=face,
        segments=[segment], map_cease_date=map_end,
    )
    config = PlancodeConfig(plancode=plancode, table_rating_factor=0.25, dynamic_banding=0)
    return compute_target_premiums(policy, config, as_of=as_of)


def test_no_tbl1_rates_use_table_percent_of_coi_s0503253(monkeypatch):
    # 1S135M0X, M17 class N, 25 units, Table B (2 x 25% = 50%), MAP end 7/16/1986.
    rates = _Rates(mtp=5.62, ctp=5.62, coi=_coi(d1=0.11, d42=0.77392))
    result = _project(
        monkeypatch, rates, plancode="1S135M0X", issue=date(1985, 7, 16), age=17, sex="M",
        units=25, table=2, as_of=date(2026, 9, 10), map_end=date(1986, 7, 16))
    # CTP: 5.62 x 25 = 140.50 + ROUND(25 x 0.77392 x 12 x 0.5, 2) = 116.09
    assert result.ctp_annual == pytest.approx(256.59)
    # MTP: (140.50 + 25 x 0.11 x 12 x 0.5 = 16.50) / 12 = 13.0833 -> TRUNC 13.08
    assert result.mtp_annual == pytest.approx(157.0)
    assert result.mtp_monthly == 13.08
    assert result.table_target_method[1] == TABLE_METHOD_COI
    assert result.mtp_coi_rates_by_coverage[1] == 0.11
    assert result.ctp_coi_rates_by_coverage[1] == 0.77392


def test_ctp_follows_the_coi_but_the_mtp_stays_frozen_at_the_map_end(monkeypatch):
    rates = _Rates(mtp=5.62, ctp=5.62, coi=_coi(d1=0.11, d41=0.70, d42=0.77392))
    kwargs = dict(plancode="1S135M0X", issue=date(1985, 7, 16), age=17, sex="M",
                  units=25, table=2, map_end=date(1986, 7, 16))
    first = _project(monkeypatch, rates, as_of=date(2026, 7, 16), **kwargs)
    year_before = _project(monkeypatch, rates, as_of=date(2026, 7, 15), **kwargs)
    assert first.ctp_annual == pytest.approx(140.50 + round(25 * 0.77392 * 12 * 0.5, 2))
    assert year_before.ctp_annual == pytest.approx(140.50 + round(25 * 0.70 * 12 * 0.5, 2))
    assert first.mtp_monthly == year_before.mtp_monthly == 13.08


def test_mtp_is_truncated_not_rounded_s0500179_shape(monkeypatch):
    # (M rate x units + units x COI x 12 x 50%) / 12 = 42.375 -> stored 42.37.
    rates = _Rates(mtp=9.21, ctp=9.21, coi=_coi(d1=0.16))
    result = _project(
        monkeypatch, rates, plancode="1S135X2X", issue=date(1985, 1, 16), age=40, sex="M",
        units=50, table=2, as_of=date(1985, 1, 16), map_end=date(1990, 1, 16))
    assert result.mtp_annual / 12 == pytest.approx(42.375)
    assert result.mtp_monthly == 42.37


def test_ctp_only_tbl1_is_used_for_the_mtp_u0609076(monkeypatch):
    # 1U144500, F39, 100.05 units, Table F = 6 tables; CTP_TBL1 1.34, no MTP_TBL1.
    rates = _Rates(mtp=5.12, ctp=7.88, tbl_ctp=1.34)
    result = _project(
        monkeypatch, rates, plancode="1U144500", issue=date(2020, 1, 15), age=39, sex="F",
        units=100.05, table=6, as_of=date(2026, 9, 15))
    # MT: 512.26 + 804.40 = 1,316.66 / 12 -> 109.72; CT: 788.39 + 804.40 = 1,592.79
    assert result.mtp_monthly == 109.72
    assert result.ctp_annual == pytest.approx(1592.79)
    assert result.table_target_method[1] == TABLE_METHOD_CTP_FOR_MTP
    assert result.mtp_tbl_rates_by_coverage[1] == 1.34
    assert rates.coi_lookups == []


def test_both_tbl1_rates_keep_the_per_table_method_ue000157(monkeypatch):
    # 1U145500, Table B (2): E* M 5.84/4, T 2.24/4 per table per unit.
    rates = _Rates(mtp=9.72, ctp=11.15, tbl_mtp=1.46, tbl_ctp=0.56)
    result = _project(
        monkeypatch, rates, plancode="1U145500", issue=date(2016, 11, 15), age=40, sex="M",
        units=25, table=2, as_of=date(2026, 9, 15))
    assert result.ctp_annual == pytest.approx(306.75)
    assert result.mtp_monthly == 26.33
    assert result.table_target_method[1] == TABLE_METHOD_RATE
    assert rates.coi_lookups == []


def test_mtp_tbl1_without_ctp_tbl1_is_still_an_error(monkeypatch):
    rates = _Rates(mtp=5.12, ctp=7.88, tbl_mtp=1.0)
    with pytest.raises(RateLookupError, match="TBL1CTP.*1U144500.*phase 1"):
        _project(monkeypatch, rates, plancode="1U144500", issue=date(2020, 1, 15), age=39,
                 sex="F", units=100, table=2, as_of=date(2026, 9, 15))


def test_coi_method_fails_loudly_without_a_coi_schedule(monkeypatch):
    rates = _Rates(mtp=5.62, ctp=5.62, coi=None)
    with pytest.raises(RateLookupError, match="COI rate schedule"):
        _project(monkeypatch, rates, plancode="1S135M0X", issue=date(1985, 7, 16), age=17,
                 sex="M", units=25, table=2, as_of=date(2026, 9, 10))


def test_unrated_coverage_needs_no_table_rates_or_coi(monkeypatch):
    rates = _Rates(mtp=5.62, ctp=5.62, coi=None)
    result = _project(monkeypatch, rates, plancode="1S135M0X", issue=date(1985, 7, 16), age=17,
                      sex="M", units=25, table=0, as_of=date(2026, 9, 10))
    assert result.ctp_annual == pytest.approx(140.5)
    assert result.table_target_method[1] == TABLE_METHOD_RATE
    assert rates.coi_lookups == []
