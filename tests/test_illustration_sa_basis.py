"""SA_Basis drives specified amounts and locks only MTP rate bands.

For plancodes whose ``SA_Basis`` is ``"OriginalSA"`` (the SkippedCovRein
IUL family) the EPU charge, the MTP/CTP target premiums, and the surrender
charge (SCR) are all computed on each coverage's ORIGINAL specified amount /
original units. Every other plan (``"CurrentSA"``) uses the current specified
amount — the historical default.

SA_Basis also controls partial surrender charge eligibility: CurrentSA
plans assess PSC on withdrawals and specified decreases; OriginalSA plans do
not. The full surrender charge schedule remains based on original units for
OriginalSA plans.

Each fixture uses a segment whose original SA (200,000) differs from its
current SA (100,000) so the two bases produce distinct, hand-computable values.
"""
from __future__ import annotations

from datetime import date
from dataclasses import fields

import pytest

import suiteview.core.rates as rates_module
from suiteview.illustration.core.calc_engine import _calculate_surrender_charge
from suiteview.illustration.core.monthly_deduction import calculate_deduction
from suiteview.illustration.core.monthly_guideline import build_guideline_basis
from suiteview.illustration.core.rate_loader import IllustrationRates
from suiteview.illustration.core.target_premium import compute_target_premiums
from suiteview.illustration.models.plancode_config import PlancodeConfig
from suiteview.illustration.models.policy_data import (
    BenefitInfo,
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


def _config(sa_basis: str) -> PlancodeConfig:
    return PlancodeConfig(
        plancode="TEST0001",
        epu_code="Table",
        mfee="0",
        dbd=0.0,
        gint=0.0,
        corridor_code=None,
        premium_cease_age=121,
        maturity_age=121,
        sa_basis=sa_basis,
    )


# ── EPU (monthly deduction path) ────────────────────────────────────────────


@pytest.mark.parametrize(
    "sa_basis, expected_sa",
    [("CurrentSA", CURRENT_SA), ("OriginalSA", ORIGINAL_SA)],
)
@pytest.mark.parametrize("epu_code", ["Table", "0.5"])
def test_epu_charge_follows_sa_basis(sa_basis, expected_sa, epu_code):
    rates = IllustrationRates(
        coi=[None] + [0.0] * 80,
        segment_coi={1: [None] + [0.0] * 80},
        epu=[None] + [0.5] * 80,
        segment_epu={1: [None] + [0.5] * 80},
    )
    config = _config(sa_basis)
    config.epu_code = epu_code
    result = calculate_deduction(
        50_000.0,
        _policy(),
        config,
        rates,
        rate_year=1,
        attained_age=45,
        premiums_to_date=0.0,
    )
    # EPU charge = round((SA / 1000) * rate, 2), rate = 0.5.
    assert result.epu_charge == pytest.approx(expected_sa / 1000.0 * 0.5)


# ── EPU (guideline basis path) ──────────────────────────────────────────────


@pytest.mark.parametrize(
    "sa_basis, expected_sa",
    [("CurrentSA", CURRENT_SA), ("OriginalSA", ORIGINAL_SA)],
)
def test_guideline_epu_follows_sa_basis(sa_basis, expected_sa):
    rates = IllustrationRates(
        coi=[None] + [1.0] * 80,
        segment_coi={1: [None] + [1.0] * 80},
        epu=[None] + [0.3] * 80,
        segment_epu={1: [None] + [0.3] * 80},
    )
    basis = build_guideline_basis(
        _policy(),
        _config(sa_basis),
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
    "sa_basis, expected_sa",
    [("CurrentSA", CURRENT_SA), ("OriginalSA", ORIGINAL_SA)],
)
def test_mtp_ctp_follow_sa_basis(monkeypatch, sa_basis, expected_sa):
    monkeypatch.setattr(rates_module, "Rates", lambda: _FakeRates())
    result = compute_target_premiums(
        _policy(), _config(sa_basis), as_of=date(2020, 6, 1)
    )
    # Coverage target = round(SA * rate / 1000, 2), no table/flat.
    assert result.mtp_by_coverage[1] == pytest.approx(expected_sa * 20.0 / 1000.0)
    assert result.ctp_by_coverage[1] == pytest.approx(expected_sa * 24.0 / 1000.0)


# ── SCR (surrender charge units) ────────────────────────────────────────────


@pytest.mark.parametrize(
    "sa_basis, expected_units",
    [
        ("CurrentSA", CURRENT_SA / 1000.0),
        ("OriginalSA", ORIGINAL_SA / 1000.0),
    ],
)
def test_scr_units_follow_sa_basis(sa_basis, expected_units):
    scr_rate = 10.0
    rates = IllustrationRates(
        scr=[None] + [scr_rate] * 80,
        segment_scr={1: [None] + [scr_rate] * 80},
    )
    _, surrender_charge, _, _ = _calculate_surrender_charge(
        _policy(), rates, rate_year=1, projection_date=None,
        config=_config(sa_basis),
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


def test_shipped_configs_use_one_explicit_sa_basis(monkeypatch):
    from suiteview.illustration.models import plancode_config as pc

    monkeypatch.setattr(pc, "_CONFIG_CACHE", {})
    table = pc._load_plancode_table()
    assert table
    for code, row in table.items():
        assert row["SA_Basis"] in ("CurrentSA", "OriginalSA")
        assert not {"Expense_Basis", "Target_SA_Basis", "Target_BandLock"} & row.keys()
        assert pc.load_plancode(code).sa_basis == row["SA_Basis"]
    names = {field.name for field in fields(PlancodeConfig)}
    assert not {"expense_basis", "target_sa_basis", "target_band_lock"} & names


@pytest.mark.parametrize("value", ["originalsa", "", None, "Invalid"])
def test_invalid_sa_basis_is_explicit(value):
    with pytest.raises(ValueError, match="invalid SA_Basis"):
        PlancodeConfig(sa_basis=value)


def test_missing_basis_does_not_infer_from_skipped_reinstatement(monkeypatch):
    from suiteview.illustration.models import plancode_config as pc

    monkeypatch.setattr(pc, "_CONFIG_CACHE", {})
    monkeypatch.setattr(pc, "_TABLE_CACHE", {"TEST": {"SkippedCovRein": True}})
    with pytest.raises(KeyError, match="SA_Basis"):
        pc.load_plancode("TEST")


class _BandedRates(_FakeRates):
    def get_band(self, plancode, specified_amount, issue_date=None):
        return 3 if specified_amount >= 250_000 else 2

    def get_mtp(self, *args):
        return args[-1] * 10.0

    def get_ctp(self, *args):
        return args[-1] * 20.0

    def get_tbl1_mtp(self, *args):
        return args[-1] * 1.0

    def get_tbl1_ctp(self, *args):
        return args[-1] * 2.0

    def get_ben_mtp(self, *args):
        return args[-2] * 1.0

    def get_ben_ctp(self, *args):
        return args[-2] * 2.0


@pytest.mark.parametrize("basis", ["CurrentSA", "OriginalSA"])
def test_only_mtp_band_locks_per_coverage_after_face_changes(monkeypatch, basis):
    monkeypatch.setattr(rates_module, "Rates", _BandedRates)
    policy = _policy()
    policy.segments.append(CoverageSegment(
        coverage_phase=5, issue_date=date(2021, 6, 1), issue_age=46,
        face_amount=100_000, original_face_amount=100_000,
        units=100, band=2, original_band=3, table_rating=1,
    ))
    policy.segments[0].table_rating = 1
    policy.benefits = [BenefitInfo(benefit_type="G", units=2)]
    config = _config(basis)
    for current_face in (100_000, 200_000, 50_000):
        policy.segments[0].face_amount = current_face
        current_band = 3 if policy.total_face >= 250_000 else 2
        result = compute_target_premiums(policy, config)
        for seg in policy.segments:
            mtp_band = seg.original_band if basis == "OriginalSA" else current_band
            sa = seg.original_face_amount if basis == "OriginalSA" else seg.face_amount
            phase = seg.coverage_phase
            assert result.mtp_rates_by_coverage[phase] == mtp_band * 10
            assert result.ctp_rates_by_coverage[phase] == current_band * 20
            assert result.mtp_tbl_rates_by_coverage[phase] == mtp_band
            assert result.ctp_tbl_rates_by_coverage[phase] == current_band * 2
            assert result.mtp_by_coverage[phase] == sa / 1000 * mtp_band * 11
            assert result.ctp_by_coverage[phase] == sa / 1000 * current_band * 22
        ben_band = 1 if basis == "OriginalSA" else current_band
        assert result.mtp_benefits["G"] == 2 * ben_band
        assert result.ctp_benefits["G"] == 4 * current_band
        assert [seg.original_band for seg in policy.segments] == [1, 3]


@pytest.mark.parametrize("scale", [0, 1])
def test_rate_loading_locks_mtp_but_not_charge_schedules(monkeypatch, scale):
    from unittest.mock import Mock
    from suiteview.illustration.core import rate_loader

    db = Mock()
    db.get_rates.return_value = []
    db.get_mtp.return_value = 10
    db.get_ctp.return_value = 40
    monkeypatch.setattr(rate_loader, "Rates", lambda: db)
    coi = Mock(return_value=[])
    monkeypatch.setattr(rate_loader, "load_coverage_coi_rates", coi)
    policy = _policy()
    policy.segments[0].band = 2
    loaded = rate_loader.load_rates(
        policy, _config("OriginalSA"), coi_scale=scale, expense_scale=scale,
    )
    assert loaded.mtp == 10
    assert loaded.ctp == 40
    assert db.get_mtp.call_args.args[-1] == 1
    assert db.get_ctp.call_args.args[-1] == 2
    assert coi.call_args.kwargs["band"] == 2
    assert coi.call_args.kwargs["scale"] == scale
    for call in db.get_rates.call_args_list:
        if call.args[0] in ("EPU", "TPP", "EPP", "SCR"):
            assert call.kwargs["band"] == 2
            assert call.kwargs["scale"] == (1 if call.args[0] == "SCR" else scale)


def test_increase_then_decrease_preserves_mtp_issue_bands_only(monkeypatch):
    from suiteview.illustration.core import calc_engine

    class Rates(_BandedRates):
        def get_rates(self, kind, *args, **kwargs):
            if kind == "SCR":
                return [None, 10.0]
            return [None, float(kwargs.get("band", 1))]

    monkeypatch.setattr(rates_module, "Rates", Rates)
    policy = _policy()
    config = _config("OriginalSA")
    rates = IllustrationRates(
        segment_coi={1: [None, 1.0]},
        segment_epu={1: [None, 1.0]},
        segment_scr={1: [None, 10.0]},
    )
    when = date(2026, 6, 1)
    calc_engine._append_face_increase_segment(
        policy, rates, 200_000, 51, when, config,
    )
    calc_engine._reload_policy_band_rates(rates, policy, config)
    assert [seg.original_band for seg in policy.segments] == [1, 3]
    assert [seg.band for seg in policy.segments] == [3, 3]
    assert rates.segment_epu == {1: [None, 3.0], 2: [None, 3.0]}
    targets = compute_target_premiums(policy, config, as_of=when)
    assert targets.mtp_rates_by_coverage == {1: 10.0, 2: 30.0}
    assert targets.ctp_rates_by_coverage == {1: 60.0, 2: 60.0}
    assert targets.mtp_by_coverage == {1: 2000.0, 2: 6000.0}
    calc_engine._reduce_base_face(
        policy, 100_000, rates, when, 1, charge_scr=False, config=config,
    )
    calc_engine._reload_policy_band_rates(rates, policy, config)
    assert [seg.original_band for seg in policy.segments] == [1, 3]
    assert [seg.band for seg in policy.segments] == [2, 2]
    assert rates.segment_coi == {1: [None, 2.0], 2: [None, 2.0]}
    assert rates.segment_epu == {1: [None, 2.0], 2: [None, 2.0]}
    assert rates.tpp == rates.epp == [None, 2.0]
    assert rates.segment_scr == {1: [None, 10.0], 2: [None, 10.0]}
    targets = compute_target_premiums(policy, config, as_of=when)
    assert targets.mtp_rates_by_coverage == {1: 10.0, 2: 30.0}
    assert targets.ctp_rates_by_coverage == {1: 40.0, 2: 40.0}
    assert targets.mtp_by_coverage == {1: 2000.0, 2: 6000.0}
