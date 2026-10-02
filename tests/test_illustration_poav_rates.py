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
        return [None, 0.0] if rate_type == "COI" else []

    def get_band(self, plancode, face, issue_date=None, **_kwargs):
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
    monkeypatch.setattr(rate_loader, "ULRates", lambda *_args, **_kwargs: fake)
    config = PlancodeConfig(plancode="TESTPOAV", poav_table="1")

    current = load_rates(_policy(), config)
    statutory = load_rates(_policy(), config, coi_scale=0)
    guaranteed = load_rates(_policy(), config, coi_scale=0, expense_scale=0)

    assert current.poav[1] == pytest.approx(0.0004)
    assert current.poav[11] == pytest.approx(0.0)
    assert statutory.poav[11] == pytest.approx(0.0)
    assert guaranteed.poav[1] == pytest.approx(0.0004)
    assert guaranteed.poav[11] == pytest.approx(0.0004)
    assert all(call[0] != "POAV" for call in fake.calls)


def test_rate_loader_expense_scale_governs_all_expense_rates(monkeypatch):
    """The expense scale (EPU, MFEE, TPP target load, EPP excess load, PoAV)
    is 1 by default — including for the 7702 guideline basis where COI is
    guaranteed (coi_scale=0) but fees stay current — and only 0 for the
    guaranteed illustration side, where the guaranteed expense schedules run
    their charges to maturity."""
    config = PlancodeConfig(plancode="TESTPOAV", poav_table="0")
    expense_types = {"EPU", "MFEE", "TPP", "EPP"}

    def _expense_scales(fake):
        return {scale for rate_type, scale, _band in fake.calls
                if rate_type in expense_types}

    # Current run: all expense rates at scale 1.
    fake = _FakeRates()
    monkeypatch.setattr(rate_loader, "ULRates", lambda *_args, **_kwargs: fake)
    load_rates(_policy(), config)
    assert _expense_scales(fake) == {1}

    # Guideline/TAMRA basis (coi_scale=0, default expense_scale): fees stay current.
    fake = _FakeRates()
    monkeypatch.setattr(rate_loader, "ULRates", lambda *_args, **_kwargs: fake)
    load_rates(_policy(), config, coi_scale=0)
    assert _expense_scales(fake) == {1}
    assert ("COI", 0, 1) in fake.calls

    # Guaranteed illustration side: all expense rates at the guaranteed scale.
    fake = _FakeRates()
    monkeypatch.setattr(rate_loader, "ULRates", lambda *_args, **_kwargs: fake)
    load_rates(_policy(), config, coi_scale=0, expense_scale=0)
    assert _expense_scales(fake) == {0}


def test_rate_loader_rejects_invalid_expense_scale(monkeypatch):
    fake = _FakeRates()
    monkeypatch.setattr(rate_loader, "ULRates", lambda *_args, **_kwargs: fake)
    config = PlancodeConfig(plancode="TESTPOAV", poav_table="0")
    with pytest.raises(ValueError, match="Expense scale must be 0 or 1"):
        load_rates(_policy(), config, expense_scale=2)


def test_monthly_deduction_applies_poav_rate_to_positive_account_value():
    policy = _policy()
    config = PlancodeConfig(
        plancode="TESTPOAV",
        poav_table="2",
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
    from suiteview.illustration.core import ul_rates as ul_rates_module

    fake = _FakeRates()
    monkeypatch.setattr(ul_rates_module, "ULRates", lambda *_args, **_kwargs: fake)
    rates = IllustrationRates(expense_scale=0)

    _reload_policy_band_rates(
        rates,
        _policy(band=1),
        PlancodeConfig(plancode="TESTPOAV", poav_table="1"),
    )

    assert rates.poav[11] == pytest.approx(0.0004)
    assert all(call[0] != "POAV" for call in fake.calls)
    # TPP/EPP/MFEE reloaded on a band change must preserve the guaranteed
    # expense scale, not revert to current fees.
    reload_scales = {scale for rate_type, scale, _band in fake.calls
                     if rate_type in {"TPP", "EPP", "MFEE"}}
    assert reload_scales == {0}


def test_plancode_config_reads_poav_table_code():
    config = load_plancode("1U144600")

    assert config.poav_table == "1"
