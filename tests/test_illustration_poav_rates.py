import pytest

from suiteview.illustration.core import rate_loader
from suiteview.illustration.core.calc_engine import _reload_policy_band_rates
from suiteview.illustration.core.monthly_deduction import calculate_deduction
from suiteview.illustration.core.poav_rates import load_poav_schedule
from suiteview.illustration.core.rate_loader import IllustrationRates, load_rates
from suiteview.illustration.models.plancode_config import PlancodeConfig, load_plancode
from suiteview.illustration.models.policy_data import (
    CoverageSegment,
    IllustrationPolicyData,
)


class _FakeRates:
    def __init__(self):
        self.calls = []

    def get_rates(
        self,
        rate_type,
        plancode,
        issue_age=None,
        sex=None,
        rateclass=None,
        scale=1,
        band=None,
        **kwargs,
    ):
        self.calls.append((rate_type, scale, band))
        return []

    def get_band(self, plancode, face, issue_date=None):
        return 2

    def get_mtp(self, *args, **kwargs):
        return 0.0

    def get_ctp(self, *args, **kwargs):
        return 0.0


def _policy(*, band=1):
    segment = CoverageSegment(
        coverage_phase=1,
        issue_age=40,
        rate_sex="M",
        rate_class="N",
        face_amount=100_000.0,
        original_face_amount=100_000.0,
        units=100.0,
        band=band,
        original_band=band,
    )
    return IllustrationPolicyData(
        plancode="TESTPOAV",
        db_option="A",
        face_amount=100_000.0,
        segments=[segment],
    )


@pytest.mark.parametrize("band", range(1, 6))
def test_poav_table_one_current_rate_ceases_in_year_eleven(band):
    schedule = load_poav_schedule("1", band, scale=1)

    assert schedule[1] == pytest.approx(0.0004)
    assert schedule[10] == pytest.approx(0.0004)
    assert schedule[11] == pytest.approx(0.0)
    assert schedule[121] == pytest.approx(0.0)


@pytest.mark.parametrize(
    ("table_code", "scale", "expected"),
    [
        ("1", 0, 0.0004),
        ("2", 1, 0.0001),
        ("2", 0, 0.0004),
        ("3", 1, 0.0002),
        ("3", 0, 0.0004),
    ],
)
@pytest.mark.parametrize("band", range(1, 6))
def test_poav_tables_fill_forward_for_every_band(table_code, scale, expected, band):
    schedule = load_poav_schedule(table_code, band, scale=scale)

    assert schedule[1] == pytest.approx(expected)
    assert schedule[11] == pytest.approx(expected)
    assert schedule[121] == pytest.approx(expected)


def test_poav_loader_rejects_unknown_table_or_band():
    with pytest.raises(ValueError, match="Unknown PoAV table code"):
        load_poav_schedule("4", 1)

    with pytest.raises(ValueError, match="has no rates for band 6"):
        load_poav_schedule("1", 6)


def test_rate_loader_uses_local_poav_table_for_current_and_guaranteed(monkeypatch):
    fake = _FakeRates()
    monkeypatch.setattr(rate_loader, "Rates", lambda: fake)
    config = PlancodeConfig(plancode="TESTPOAV", poav_table="1")

    current = load_rates(_policy(), config)
    statutory = load_rates(_policy(), config, coi_scale=0)
    guaranteed = load_rates(_policy(), config, coi_scale=0, poav_scale=0)

    assert current.poav[1] == pytest.approx(0.0004)
    assert current.poav[11] == pytest.approx(0.0)
    assert statutory.poav[11] == pytest.approx(0.0)
    assert guaranteed.poav[1] == pytest.approx(0.0004)
    assert guaranteed.poav[11] == pytest.approx(0.0004)
    assert all(call[0] != "POAV" for call in fake.calls)


def test_monthly_deduction_applies_poav_rate_to_positive_account_value():
    policy = _policy()
    config = PlancodeConfig(
        plancode="TESTPOAV",
        poav_table="2",
        epu_code="0",
        mfee="0",
        corridor_code=None,
        dbd=0.0,
    )
    rates = IllustrationRates(poav=load_poav_schedule("2", 1))

    result = calculate_deduction(
        10_000.0,
        policy,
        config,
        rates,
        rate_year=1,
        attained_age=40,
        premiums_to_date=0.0,
    )

    assert result.av_charge == pytest.approx(1.0)
    assert result.total_deduction == pytest.approx(1.0)
    assert result.av_after_deduction == pytest.approx(9_999.0)


def test_policy_band_reload_keeps_guaranteed_poav_basis(monkeypatch):
    from suiteview.core import rates as core_rates

    fake = _FakeRates()
    monkeypatch.setattr(core_rates, "Rates", lambda: fake)
    rates = IllustrationRates(poav_scale=0)

    _reload_policy_band_rates(
        rates,
        _policy(band=1),
        PlancodeConfig(plancode="TESTPOAV", poav_table="1"),
    )

    assert rates.poav[11] == pytest.approx(0.0004)
    assert all(call[0] != "POAV" for call in fake.calls)


def test_plancode_config_reads_poav_table_code():
    config = load_plancode("1U144600")

    assert config.poav_table == "1"
