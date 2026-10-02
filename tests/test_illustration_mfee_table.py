"""Schema-driven monthly fee (MFEE) that varies by rate class.

Plancode 1U146800's monthly fee is $5 for males/females but $10 for the unisex
"Y" class. That variation comes from schema ``rates`` MFEE cells; a plancode
fallback applies only when a plan has no MFEE cells.

These tests pin down each link in that chain:
  1. the plancode data has no flat MFEE fallback,
  2. the MFEE SQL filters by Sex AND Rateclass,
  3. the monthly deduction consumes the loaded fee schedule, and
  4. the loader hands the segment's rate class to the MFEE lookup, so two
     otherwise-identical policies get $5 vs $10 purely from their rate class.
"""
from __future__ import annotations

from datetime import date

import pytest

import suiteview.illustration.core.rate_loader as rate_loader
from suiteview.core.rates import Rates
from suiteview.illustration.core.monthly_deduction import calculate_deduction
from suiteview.illustration.core.rate_loader import IllustrationRates, load_rates
from suiteview.illustration.models.plancode_config import PlancodeConfig, load_plancode
from suiteview.illustration.models.policy_data import (
    CoverageSegment,
    IllustrationPolicyData,
)

FACE = 100_000.0


def _segment(rate_sex: str, rate_class: str) -> CoverageSegment:
    return CoverageSegment(
        coverage_phase=1,
        issue_date=date(2020, 6, 1),
        issue_age=45,
        rate_sex=rate_sex,
        rate_class=rate_class,
        face_amount=FACE,
        original_face_amount=FACE,
        units=FACE / 1000.0,
        band=1,
        original_band=1,
    )


def _policy(rate_sex: str = "M", rate_class: str = "N") -> IllustrationPolicyData:
    seg = _segment(rate_sex, rate_class)
    return IllustrationPolicyData(
        plancode="1U146800",
        issue_date=date(2020, 6, 1),
        issue_age=45,
        db_option="A",
        face_amount=seg.face_amount,
        segments=[seg],
    )


def _config(mfee_fallback: float | None = None) -> PlancodeConfig:
    return PlancodeConfig(
        plancode="1U146800",
        mfee_fallback=mfee_fallback,
        dbd=0.0,
        gint=0.0,
        corridor_code=None,
        premium_cease_age=121,
        maturity_age=121,
        poav_table="0",
    )


# ── 1. Plancode data ────────────────────────────────────────────────────────


def test_1u146800_mfee_has_no_flat_fallback():
    config = load_plancode("1U146800")
    assert config.mfee_fallback is None


# ── 2. MFEE SQL links to Select_RATE_MFEE by Sex AND Rateclass ──────────────


def test_mfee_sql_filters_by_sex_and_rate_class():
    sql, params = Rates()._create_sql(
        "MFEE", "1U146800", issue_age=45, sex="U", rateclass="Y",
        scale=1, band=1,
    )
    assert "Select_RATE_MFEE" in sql
    assert "Sex=?" in sql and "Rateclass=?" in sql
    # Params carry the rate class through to the lookup.
    assert "Y" in params and "U" in params


# ── 3. Monthly deduction consumes the table fee when MFEE == "Table" ────────


@pytest.mark.parametrize("table_fee", [5.0, 10.0])
def test_deduction_uses_loaded_mfee_schedule(table_fee):
    rates = IllustrationRates(mfee=[None] + [table_fee] * 80)
    result = calculate_deduction(
        50_000.0, _policy(), _config(), rates,
        rate_year=1, attained_age=45, premiums_to_date=0.0,
    )
    assert result.mfee_charge == pytest.approx(table_fee)


def test_loaded_mfee_schedule_wins_over_flat_fallback():
    """The table fallback is only used by the loader when schema MFEE is absent."""
    rates = IllustrationRates(mfee=[None] + [10.0] * 80)
    result = calculate_deduction(
        50_000.0, _policy(), _config(mfee_fallback=5.0), rates,
        rate_year=1, attained_age=45, premiums_to_date=0.0,
    )
    assert result.mfee_charge == pytest.approx(10.0)


# ── 4. Loader passes the segment's rate class → $5 M/F vs $10 unisex ────────


class _FakeRates:
    """Minimal stand-in that returns a rate-class-varying MFEE.

    $10/month for the unisex "Y" class, $5/month otherwise — mirroring
    1U146800's Select_RATE_MFEE data.
    """

    def __init__(self):
        self.mfee_calls = []

    def get_rates(self, rate_type, plancode, issue_age=None, sex=None,
                  rateclass=None, scale=1, band=None, specified_amount=0,
                  benefit_type="", state=None, **_kwargs):
        if rate_type.upper() == "MFEE":
            self.mfee_calls.append((sex, rateclass))
            fee = 10.0 if rateclass == "Y" else 5.0
            return [None] + [fee] * 80
        return [None] + [0.0] * 80

    def get_mtp(self, *args, **kwargs):
        return 0.0

    def get_ctp(self, *args, **kwargs):
        return 0.0


def test_loader_mfee_varies_by_rate_class(monkeypatch):
    fake = _FakeRates()
    monkeypatch.setattr(rate_loader, "ULRates", lambda *_args, **_kwargs: fake)

    male = load_rates(_policy(rate_sex="M", rate_class="N"), _config())
    female = load_rates(_policy(rate_sex="F", rate_class="N"), _config())
    unisex = load_rates(_policy(rate_sex="U", rate_class="Y"), _config())

    assert male.mfee[1] == pytest.approx(5.0)
    assert female.mfee[1] == pytest.approx(5.0)
    assert unisex.mfee[1] == pytest.approx(10.0)
    # The unisex rate class was actually forwarded to the MFEE lookup.
    assert ("U", "Y") in fake.mfee_calls
