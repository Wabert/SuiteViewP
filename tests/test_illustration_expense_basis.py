"""Expense_Basis drives the specified-amount basis for the SA-based charges.

For plancodes whose ``Expense_Basis`` is ``"OriginalSA"`` (the SkippedCovRein
IUL family) the EPU charge, the MTP/CTP target premiums, and the surrender
charge (SCR) are all computed on each coverage's ORIGINAL specified amount /
original units. Every other plan (``"CurrentSA"``) uses the current specified
amount — the historical default.

Expense_Basis also controls partial surrender charge eligibility: CurrentSA
plans assess PSC on withdrawals and specified decreases; OriginalSA plans do
not. The full surrender charge schedule remains based on original units for
OriginalSA plans.

Each fixture uses a segment whose original SA (200,000) differs from its
current SA (100,000) so the two bases produce distinct, hand-computable values.
"""
from __future__ import annotations

from datetime import date

import pytest

import suiteview.core.rates as rates_module
from suiteview.illustration.core.calc_engine import _calculate_surrender_charge
from suiteview.illustration.core.monthly_deduction import calculate_deduction
from suiteview.illustration.core.monthly_guideline import build_guideline_basis
from suiteview.illustration.core.rate_loader import IllustrationRates
from suiteview.illustration.core.target_premium import compute_target_premiums
from suiteview.illustration.models.plancode_config import PlancodeConfig
from suiteview.illustration.models.policy_data import (
    CoverageSegment,
    IllustrationPolicyData,
)

CURRENT_SA = 100_000.0
ORIGINAL_SA = 200_000.0


def _segment() -> CoverageSegment:
    return CoverageSegment(
        coverage_phase=1,
        issue_date=date(2020, 6, 1),
        issue_age=45,
        rate_sex="M",
        rate_class="N",
        face_amount=CURRENT_SA,
        original_face_amount=ORIGINAL_SA,
        units=CURRENT_SA / 1000.0,
        band=1,
        original_band=1,
    )


def _policy() -> IllustrationPolicyData:
    seg = _segment()
    policy = IllustrationPolicyData(
        plancode="TEST0001",
        issue_date=date(2020, 6, 1),
        issue_age=45,
        db_option="A",
        face_amount=seg.face_amount,
        segments=[seg],
    )
    return policy


def _config(expense_basis: str) -> PlancodeConfig:
    return PlancodeConfig(
        plancode="TEST0001",
        epu_code="Table",
        mfee="0",
        dbd=0.0,
        gint=0.0,
        corridor_code=None,
        premium_cease_age=121,
        maturity_age=121,
        expense_basis=expense_basis,
    )


# ── EPU (monthly deduction path) ────────────────────────────────────────────


@pytest.mark.parametrize(
    "expense_basis, expected_sa",
    [("CurrentSA", CURRENT_SA), ("OriginalSA", ORIGINAL_SA)],
)
def test_epu_charge_follows_expense_basis(expense_basis, expected_sa):
    rates = IllustrationRates(
        coi=[None] + [0.0] * 80,
        segment_coi={1: [None] + [0.0] * 80},
        epu=[None] + [0.5] * 80,
        segment_epu={1: [None] + [0.5] * 80},
    )
    result = calculate_deduction(
        50_000.0,
        _policy(),
        _config(expense_basis),
        rates,
        rate_year=1,
        attained_age=45,
        premiums_to_date=0.0,
    )
    # EPU charge = round((SA / 1000) * rate, 2), rate = 0.5.
    assert result.epu_charge == pytest.approx(expected_sa / 1000.0 * 0.5)


# ── EPU (guideline basis path) ──────────────────────────────────────────────


@pytest.mark.parametrize(
    "expense_basis, expected_sa",
    [("CurrentSA", CURRENT_SA), ("OriginalSA", ORIGINAL_SA)],
)
def test_guideline_epu_follows_expense_basis(expense_basis, expected_sa):
    rates = IllustrationRates(
        coi=[None] + [1.0] * 80,
        segment_coi={1: [None] + [1.0] * 80},
        epu=[None] + [0.3] * 80,
        segment_epu={1: [None] + [0.3] * 80},
    )
    basis = build_guideline_basis(
        _policy(),
        _config(expense_basis),
        rates,
        attained_age=45,
        as_of=date(2020, 6, 1),
    )
    assert basis.months[0].epu == pytest.approx(expected_sa / 1000.0 * 0.3)


# ── MTP / CTP (target premium) ──────────────────────────────────────────────


class _FakeRates:
    MTP_RATE = 20.0
    CTP_RATE = 24.0

    def get_band(self, plancode, specified_amount, issue_date=None):
        return 1

    def get_mtp(self, *args):
        return self.MTP_RATE

    def get_tbl1_mtp(self, *args):
        return 0.0

    def get_ctp(self, *args):
        return self.CTP_RATE

    def get_tbl1_ctp(self, *args):
        return 0.0

    def get_ben_mtp(self, *args, **kwargs):
        return 0.0

    def get_ben_ctp(self, *args, **kwargs):
        return 0.0

    def get_rates(self, *args, **kwargs):
        return []


@pytest.mark.parametrize(
    "expense_basis, expected_sa",
    [("CurrentSA", CURRENT_SA), ("OriginalSA", ORIGINAL_SA)],
)
def test_mtp_ctp_follow_expense_basis(monkeypatch, expense_basis, expected_sa):
    monkeypatch.setattr(rates_module, "Rates", lambda: _FakeRates())
    result = compute_target_premiums(
        _policy(), _config(expense_basis), as_of=date(2020, 6, 1)
    )
    # Coverage target = round(SA * rate / 1000, 2), no table/flat.
    assert result.mtp_by_coverage[1] == pytest.approx(expected_sa * 20.0 / 1000.0)
    assert result.ctp_by_coverage[1] == pytest.approx(expected_sa * 24.0 / 1000.0)


# ── SCR (surrender charge units) ────────────────────────────────────────────


@pytest.mark.parametrize(
    "expense_basis, expected_units",
    [
        ("CurrentSA", CURRENT_SA / 1000.0),
        ("OriginalSA", ORIGINAL_SA / 1000.0),
    ],
)
def test_scr_units_follow_expense_basis(expense_basis, expected_units):
    scr_rate = 10.0
    rates = IllustrationRates(
        scr=[None] + [scr_rate] * 80,
        segment_scr={1: [None] + [scr_rate] * 80},
    )
    _, surrender_charge, _, _ = _calculate_surrender_charge(
        _policy(), rates, rate_year=1, projection_date=None,
        config=_config(expense_basis),
    )
    assert surrender_charge == pytest.approx(scr_rate * expected_units)


def test_scr_defaults_to_current_units_when_config_missing():
    """No config supplied → current units (back-compatible default)."""
    scr_rate = 10.0
    rates = IllustrationRates(
        scr=[None] + [scr_rate] * 80,
        segment_scr={1: [None] + [scr_rate] * 80},
    )
    _, surrender_charge, _, _ = _calculate_surrender_charge(
        _policy(), rates, rate_year=1, projection_date=None,
    )
    assert surrender_charge == pytest.approx(scr_rate * CURRENT_SA / 1000.0)
