"""Benefits the plan's CyberLife PDF constructs at zero premium are charged $0.

DSB segment DSBPRUSE 0 means the premium is DSBPRAMT per unit monthly (CyberDoc D10
p.119); DSBPRAMT 0 with construct rule 2 is a zero-premium benefit (1U143900 3D LPW84,
NU1F* 3L PWD). CyberLife's MD carries no charge for them (1U132100 U0164393 MD = COI +
expense), and UL_Rates has no BENCOI for them.
"""
from datetime import date

import pytest

from suiteview.core.rates_schema import PdfBenefitPremium, RatesSchemaRepository
from suiteview.illustration.core import calc_engine
from suiteview.illustration.core.rate_loader import (
    IllustrationRates,
    RateLookupError,
    _load_benefit_rates,
    load_benefit_schedule,
)
from suiteview.illustration.core.ul_rates import ULRates
from suiteview.illustration.models.policy_data import BenefitInfo, CoverageSegment, IllustrationPolicyData


def _segment(occurrence, benefit, use, amount):
    return PdfBenefitPremium("00", "A", "01011900", occurrence, benefit, use, amount)


class _PdfRepo:
    def __init__(self, segments):
        self.segments = segments

    def pdf_benefit_premiums(self, _plancode):
        return list(self.segments)


def test_zero_premium_benefits_need_every_segment_at_zero():
    repo = _PdfRepo([
        _segment(1, "32", "2", ""),
        _segment(2, "39", "2", ""),
        _segment(3, "3D", "0", "0000"),
        _segment(4, "3L", "0", "0000"),
        _segment(5, "3L", "0", "0150"),     # another segment charges 3L
        _segment(6, "3X", "0", ""),         # no amount on record: not provably zero
    ])

    assert ULRates(repository=repo).zero_premium_benefits("1u132100") == frozenset({"3D"})


class _QueryRepo(RatesSchemaRepository):
    def __init__(self, rows):
        super().__init__(connection=object())
        self.rows = rows

    def _query(self, sql, params=()):
        assert "dbo.CYBERLIFE_PDF" in sql and params == ["1U132100"]
        return self.rows


def test_repository_groups_pdf_fields_by_segment():
    rows = [
        ("00", "A         ", "01011900  ", "DSBTYPCD-TYPE-CODE (003)    ", "3  "),
        ("00", "A         ", "01011900  ", "DSBSBTYP-SUBTYPE (003)      ", "D  "),
        ("00", "A         ", "01011900  ", "DSBPRUSE-PREMIUM-USE (003)  ", "0  "),
        ("00", "A         ", "01011900  ", "DSBPRAMT-PREMIUM-AMOUNT (003)", "0000"),
        ("00", "A         ", "01011900  ", "DSBTYPCD-TYPE-CODE (001)    ", "3  "),
        ("00", "A         ", "01011900  ", "DSBSBTYP-SUBTYPE (001)      ", "2  "),
        ("00", "A         ", "01011900  ", "DSBPRUSE-PREMIUM-USE (001)  ", "2  "),
    ]

    assert _QueryRepo(rows).pdf_benefit_premiums("1U132100") == [
        _segment(1, "32", "2", ""),
        _segment(3, "3D", "0", "0000"),
    ]


class _FakeRates:
    def __init__(self, zero=frozenset(), schedule=None):
        self.zero = zero
        self.schedule = schedule
        self.requests = []

    def zero_premium_benefits(self, _plancode):
        return self.zero

    def get_rates(self, rate_type, *_args, benefit_type="", **_kwargs):
        self.requests.append((rate_type, benefit_type))
        return list(self.schedule or [])


def _policy(*benefits):
    issue = date(1991, 4, 1)
    segment = CoverageSegment(
        coverage_phase=1, issue_date=issue, issue_age=24, rate_sex="M", rate_class="N",
        band=2, face_amount=50_000.0, units=50.0)
    return IllustrationPolicyData(
        plancode="1U132100", issue_date=issue, issue_age=24, rate_sex="M", rate_class="N", band=2,
        policy_year=36, valuation_date=date(2026, 10, 1), segments=[segment], benefits=list(benefits)), segment


def _benefit(subtype):
    return BenefitInfo(
        coverage_phase=1, benefit_type="3", benefit_subtype=subtype, units=50.0,
        issue_date=date(1991, 4, 1), issue_age=24, pay_up_date=date(2080, 4, 1),
        cease_date=date(2080, 4, 1), is_active=True)


def test_zero_premium_benefit_loads_an_explicit_zero_schedule_without_bencoi():
    policy, segment = _policy(_benefit("D"))
    rates_db = _FakeRates(zero=frozenset({"3D"}))
    rates = IllustrationRates()

    load_benefit_schedule(rates, rates_db, policy, policy.benefits[0], segment, "3D")

    assert rates.benefit_coi["3D"] == [None, 0.0]
    assert rates.zero_premium_benefits == {"3D"}
    assert rates_db.requests == []


def test_chargeable_benefit_without_bencoi_still_raises():
    policy, segment = _policy(_benefit("D"))

    with pytest.raises(RateLookupError, match="No BENCOI rates"):
        _load_benefit_rates(IllustrationRates(), policy, _FakeRates(), segment)


def test_reband_leaves_a_zero_premium_benefit_at_zero(monkeypatch):
    policy, segment = _policy(_benefit("D"))
    rates = IllustrationRates()
    load_benefit_schedule(rates, _FakeRates(zero=frozenset({"3D"})), policy, policy.benefits[0], segment, "3D")
    monkeypatch.setattr(
        "suiteview.illustration.core.ul_rates.ULRates",
        lambda *_a, **_k: _FakeRates(schedule=[None, 0.5]))

    calc_engine._reband_benefits(rates, policy)

    assert rates.benefit_coi["3D"] == [None, 0.0]
