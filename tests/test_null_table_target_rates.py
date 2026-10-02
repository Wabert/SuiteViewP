"""Unavailable table-rating targets are not zero-valued rates.

The dbo ``Rates`` cases cover PolView's legacy reader; the target premium and
shadow cases run RERUN's schema ``rates`` reader (``ULRates``)."""
from datetime import date
from decimal import Decimal

import pytest

from suiteview.core.rates import Rates
from suiteview.core.rates_errors import RatesError
from suiteview.illustration.core import rate_loader
from suiteview.illustration.core.rate_loader import RateLookupError
from suiteview.illustration.core.target_premium import compute_target_premiums
from suiteview.illustration.core.ul_rates import ULRates
from suiteview.illustration.models.plancode_config import PlancodeConfig
from suiteview.illustration.models.policy_data import CoverageSegment, IllustrationPolicyData
from tests.schema_rates_fake import FakeSchemaRepo


@pytest.fixture
def rates(monkeypatch):
    instance = Rates()
    monkeypatch.setattr(instance, "_cache", {})
    return instance


@pytest.mark.parametrize("kind", ["TBL1MTP", "TBL1CTP"])
def test_null_table_target_is_unavailable_and_cached(rates, monkeypatch, kind):
    calls = []

    def fetch(*args):
        calls.append(args)
        return [(None,), (None,), (None,)]

    monkeypatch.setattr(rates, "_fetch_rates", fetch)
    assert rates.get_rates(kind, "TEST", 28, "M", "E", band=4) is None
    getter = rates.get_tbl1_mtp if kind == "TBL1MTP" else rates.get_tbl1_ctp
    assert getter("TEST", 28, "M", "E", 4) is None
    assert len(calls) == 1


@pytest.mark.parametrize("kind", ["TBL1MTP", "TBL1CTP"])
def test_zero_table_target_remains_a_rate(rates, monkeypatch, kind):
    monkeypatch.setattr(rates, "_fetch_rates", lambda *args: [(Decimal("0.00"),)])
    assert rates.get_rates(kind, "TEST", 28, "M", "E", band=4) == [None, 0.0]


def test_mixed_null_table_targets_are_explicit_error(rates, monkeypatch):
    monkeypatch.setattr(rates, "_fetch_rates", lambda *args: [(None,), (1.0,)])
    with pytest.raises(RatesError, match="TBL1MTP.*TEST"):
        rates.get_rates("TBL1MTP", "TEST", 28, "M", "E", band=4)
    assert not rates._cache


@pytest.mark.parametrize("rating, cease_date", [
    (0, None),
    (2, date(2026, 1, 1)),
])
def test_unrated_or_ceased_coverage_does_not_need_table_targets(monkeypatch, rating, cease_date):
    policy, config = _target_fixture(monkeypatch, rating, cease_date)
    result = compute_target_premiums(policy, config, as_of=date(2026, 9, 1))
    assert result.mtp_annual == 734.0
    assert result.ctp_annual == 734.0


@pytest.mark.parametrize("missing", ["TBL1CTP"])
def test_active_table_rating_requires_its_target_rate(monkeypatch, missing):
    policy, config = _target_fixture(monkeypatch, 2, None, missing=missing)
    with pytest.raises(RateLookupError, match=f"{missing}.*TEST.*phase 1"):
        compute_target_premiums(policy, config, as_of=date(2026, 9, 1))


def test_missing_mtp_table_rate_uses_the_ctp_table_rate(monkeypatch):
    # Rule 2: CyberLife copies a T-only E* into the second M row, so a missing
    # TBL1MTP is not an error while TBL1CTP exists (here a stored 0.0 rate).
    policy, config = _target_fixture(monkeypatch, 2, None, missing="TBL1MTP")
    result = compute_target_premiums(policy, config, as_of=date(2026, 9, 1))
    assert result.mtp_annual == result.ctp_annual == 734.0


def test_active_table_rating_accepts_stored_zero_rates(monkeypatch):
    policy, config = _target_fixture(monkeypatch, 2, None, missing="")
    result = compute_target_premiums(policy, config, as_of=date(2026, 9, 1))
    assert result.mtp_annual == result.ctp_annual == 734.0


@pytest.mark.parametrize("rating, value, raises", [
    (0, None, False), (2, None, True), (2, 0.0, False), (2, 1.25, False),
])
def test_shadow_table_target_applicability(monkeypatch, rating, value, raises):
    rates = ULRates(repository=FakeSchemaRepo())
    monkeypatch.setattr(rate_loader, "ULRates", lambda *_args, **_kwargs: rates)
    monkeypatch.setattr(rates, "get_rates", lambda *args, **kwargs: [None, 1.0])
    monkeypatch.setattr(rates, "get_mtp", lambda *args, **kwargs: 7.34)
    monkeypatch.setattr(rates, "get_tbl1_mtp", lambda *args, **kwargs: value)
    policy = IllustrationPolicyData(
        plancode="TEST", ccv_active=True,
        segments=[CoverageSegment(face_amount=100_000, table_rating=rating)],
    )
    config = PlancodeConfig(
        plancode="TEST", shadow_plancode="SHADOW", 
        poav_table="0", dynamic_banding=0,
    )
    if raises:
        with pytest.raises(RateLookupError, match="shadow MTP_TBL1.*TEST.*scale S"):
            rate_loader.load_rates(policy, config)
    else:
        result = rate_loader.load_rates(policy, config)
        assert result.shadow_tpr_tbl1 == ([] if value is None else [None, value])


def _target_fixture(monkeypatch, rating, cease_date, missing=None):
    """Plan TEST in schema ``rates``: MTP/CTP 7.34 per unit; table add-ons 0 unless ``missing``."""
    repo = FakeSchemaRepo()
    repo.add_band("4", None)
    cell = dict(sex="M", rate_class="E", band="4", grain="IA")
    for rate_type in ("MTP", "CTP"):
        repo.add_cell(rate_type, [(date(1900, 1, 1), None, {(28, 0): 7.34})], **cell)
    for kind, rate_type in (("TBL1MTP", "MTP_TBL1"), ("TBL1CTP", "CTP_TBL1")):
        if missing not in (None, kind):
            repo.add_cell(rate_type, [(date(1900, 1, 1), None, {(28, 0): 0.0})], **cell)
    rates = ULRates(repository=repo)
    monkeypatch.setattr("suiteview.illustration.core.ul_rates.ULRates", lambda *_args, **_kwargs: rates)
    monkeypatch.setattr(rates, "get_band", lambda *args, **kwargs: 4)
    segment = CoverageSegment(
        coverage_phase=1, issue_age=28, rate_sex="M", rate_class="E",
        face_amount=100_000, original_face_amount=100_000,
        band=4, original_band=4, table_rating=rating, table_cease_date=cease_date,
    )
    policy = IllustrationPolicyData(
        plancode="TEST", issue_age=28, face_amount=100_000, segments=[segment])
    return policy, PlancodeConfig(plancode="TEST")
