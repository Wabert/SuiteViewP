"""CVAT net single premium (CyberLife NS target), Fackler roll and the CVAT corridor."""
from __future__ import annotations

import math
from datetime import date

import pytest

from suiteview.illustration.core.cvat_nsp import (
    CvatCorridor,
    IswlNspBasis,
    UlNspBasis,
    backward_step,
    fackler_step,
    immediate_claims_factor,
    monthly_death_rate,
    nsp_at,
    present_value,
    substandard_in_nsp,
)
from suiteview.illustration.core.monthly_deduction import calculate_deduction
from suiteview.illustration.core.rate_loader import IllustrationRates
from suiteview.illustration.models.plancode_config import PlancodeConfig
from suiteview.illustration.models.policy_data import CoverageSegment, IllustrationPolicyData

# UE000140 (01, 1U145700): guaranteed COI (schema rates COI scale G) per $1,000 per month by
# policy year from issue age 63 to attained age 100.
UE000140_GCOI = [
    1.0496, 1.1714, 1.3001, 1.4307, 1.5633, 1.7063, 1.8547, 2.035, 2.2372, 2.5036, 2.7856,
    3.0834, 3.4102, 3.7682, 4.1859, 4.6766, 5.2472, 5.8741, 6.5942, 7.3512, 8.1759, 9.0994,
    10.1442, 11.3189, 12.6224, 14.0439, 15.5722, 17.1996, 18.7618, 20.4241, 22.2165, 24.1551,
    26.2442, 28.2056, 30.352, 32.7087, 35.3034, 38.1751, 40.53, 43.1177, 45.9663, 49.112,
    52.5488, 56.3707, 60.6405, 65.4382, 70.8624, 77.04, 83.3333, 83.3333,
]


def _ue000140(**overrides):
    segment = dict(coverage_phase=1, issue_date=date(2016, 8, 26), issue_age=63, rate_sex="M",
                   rate_class="N", face_amount=25_000.0, original_face_amount=25_000.0, units=25.0)
    segment.update(overrides.pop("segment", {}))
    data = dict(
        policy_number="UE000140", plancode="1U145700", def_of_life_ins="CVAT",
        issue_date=date(2016, 8, 26), valuation_date=date(2026, 9, 26), issue_age=63,
        attained_age=73, policy_year=11, policy_month=2, duration=122, maturity_age=121,
        face_amount=25_000.0, units=25.0, db_option="A", guaranteed_interest_rate=0.025,
        segments=[CoverageSegment(**segment)],
    )
    data.update(overrides)
    policy = IllustrationPolicyData(**data)
    rates = IllustrationRates(coi=[None] + UE000140_GCOI, segment_coi={1: [None] + UE000140_GCOI})
    return policy, PlancodeConfig(plancode=policy.plancode, table_rating_factor=0.25), rates


def _monthly_qs(first_year: int, last_year: int) -> list[float]:
    return [monthly_death_rate(min(rate, 1000 / 12))
            for rate in UE000140_GCOI[first_year - 1:last_year] for _ in range(12)]


# ── Recursions ─────────────────────────────────────────────────────────────


def test_monthly_death_rate_from_coi_on_discounted_nar():
    assert monthly_death_rate(2.7856) == pytest.approx(2.7856 / 1.0027856)


def test_fackler_step_inverts_the_backward_step():
    v = 1.04 ** (-1 / 12)
    for q, factor in ((2.5, 1.0), (40.0, 1.0), (12.0, immediate_claims_factor(0.04))):
        start = backward_step(612.34, q, v, factor)
        assert fackler_step(start, q, v, factor) == pytest.approx(612.34, abs=1e-9)


def test_present_value_then_fackler_reaches_the_later_present_value():
    v = 1.04 ** (-1 / 12)
    qs = _monthly_qs(1, 37)
    value = present_value(qs, v)
    for q in qs[:120]:
        value = fackler_step(value, q, v)
    assert value == pytest.approx(present_value(qs[120:], v), abs=1e-8)


def test_immediate_claims_factor_rounds_the_force_of_interest_to_7_places():
    assert immediate_claims_factor(0.04) == pytest.approx(0.04 / 0.0392207, abs=1e-12)
    assert immediate_claims_factor(0.04) != pytest.approx(0.04 / math.log(1.04), abs=1e-8)
    assert immediate_claims_factor(0.0) == 1.0


# ── UL basis: UE000140 reproduces CyberLife's NS ───────────────────────────


def test_ue000140_ns_present_value_matches_cyberlife():
    """NS 16,378.11 at 2026-08-26 (age 73): 4% (GINT 2.5% < 7702 4%), endowment at 100."""
    assert round(present_value(_monthly_qs(11, 37), 1.04 ** (-1 / 12)) * 25 + 1e-9, 2) == 16378.11
    policy, config, rates = _ue000140()
    ns = nsp_at(policy, config, rates, date(2026, 8, 26))
    assert ns.annual_rate == 0.04
    assert round(ns.amount + 1e-9, 2) == 16378.11
    assert ns.per_thousand == pytest.approx(655.1245, abs=1e-4)


def test_ue000140_fackler_roll_from_issue_matches_cyberlife():
    policy, config, rates = _ue000140()
    corridor = CvatCorridor(UlNspBasis(policy, config, rates))
    corridor.nsp_by_coverage(date(2016, 8, 26))
    assert round(corridor.ns_amount(date(2026, 8, 26)) + 1e-9, 2) == 16378.11


def test_ul_corridor_holds_the_anniversary_ns_for_the_policy_year():
    policy, config, rates = _ue000140()
    corridor = CvatCorridor(UlNspBasis(policy, config, rates))
    held = corridor.corridor_rate(date(2026, 9, 26))
    assert held == pytest.approx(25_000.0 / 16378.1125, rel=1e-6)
    assert corridor.corridor_rate(date(2027, 7, 26)) == held
    next_year = nsp_at(policy, config, rates, date(2027, 8, 26))
    assert corridor.corridor_rate(date(2027, 8, 26)) == pytest.approx(25_000.0 / next_year.amount, rel=1e-12)


def test_post_2020_contract_uses_the_2_percent_statutory_rate():
    policy, config, rates = _ue000140(issue_date=date(2021, 3, 1), guaranteed_interest_rate=0.01,
                                      segment={"issue_date": date(2021, 3, 1)})
    assert UlNspBasis(policy, config, rates).annual_rate == 0.02


def test_guaranteed_rate_above_statutory_is_used():
    policy, config, rates = _ue000140(guaranteed_interest_rate=0.045)
    assert UlNspBasis(policy, config, rates).annual_rate == 0.045


@pytest.mark.parametrize("plancode, table_included", [("1U145700", False), ("1U147400", True),
                                                     ("1U148100", True), ("1U147600", False)])
def test_table_ratings_follow_the_plan_rule_and_flat_extras_never_count(plancode, table_included):
    policy, config, rates = _ue000140(plancode=plancode,
                                      segment={"table_rating": 4, "flat_extra": 5.0})
    standard, _, _ = _ue000140(plancode=plancode)
    rated = nsp_at(policy, config, rates, date(2026, 8, 26)).amount
    plain = nsp_at(standard, config, rates, date(2026, 8, 26)).amount
    assert substandard_in_nsp(policy).flat is False
    assert (rated > plain + 1.0) is table_included
    if not table_included:
        assert rated == pytest.approx(plain, abs=1e-9)


# ── ISWL basis: valuation mortality table ──────────────────────────────────


def _iswl(plancode, issue, age, face, table, rate):
    return IllustrationPolicyData(
        policy_number="ISWL", plancode=plancode, def_of_life_ins="CVAT", issue_date=issue,
        issue_age=age, face_amount=face, maturity_age=121,
        segments=[CoverageSegment(coverage_phase=1, issue_date=issue, issue_age=age,
                                  face_amount=face, units=face / 1000.0,
                                  nsp_mortality_table=table, nsp_interest_rate=rate)],
    )


@pytest.mark.parametrize("plancode, issue, age, face, table, rate, as_of, expected", [
    # immediate claims (B11SB600, 80136200) and curtate (B11SP400) — CyberLife NS targets
    ("B11SB600", date(2013, 12, 28), 53, 132_933.0, "NK", 0.04, date(2025, 12, 28), 71558.92),
    ("80136200", date(2007, 12, 20), 11, 25_000.0, "LP", 0.05, date(2025, 12, 20), 3004.20),
    ("B11SP400", date(2018, 11, 16), 63, 19_895.0, "NK", 0.04, date(2025, 11, 16), 11922.10),
])
def test_iswl_ns_matches_cyberlife(plancode, issue, age, face, table, rate, as_of, expected):
    policy = _iswl(plancode, issue, age, face, table, rate)
    config = PlancodeConfig(plancode=plancode, product_family="ISWL")
    assert round(nsp_at(policy, config, None, as_of).amount + 1e-9, 2) == expected
    corridor = CvatCorridor(IswlNspBasis(policy))
    corridor.nsp_by_coverage(issue)
    assert round(corridor.ns_amount(as_of) + 1e-9, 2) == expected
    # Mid-year months use the anniversary NSP.
    assert corridor.ns_amount(date(as_of.year + 1, as_of.month, 1)) == pytest.approx(
        corridor.ns_amount(as_of))


def test_iswl_without_mortality_table_fails_loud():
    policy = _iswl("80136200", date(2007, 12, 20), 11, 25_000.0, "", None)
    with pytest.raises(ValueError, match="valuation mortality"):
        IswlNspBasis(policy)


# ── Corridor in the monthly deduction ──────────────────────────────────────


def test_cvat_corridor_rate_raises_the_death_benefit_to_av_times_mdbr():
    policy, config, rates = _ue000140(account_value=20_000.0)
    mdbr = 25_000.0 / 16_378.11
    result = calculate_deduction(
        20_000.0, policy, config, rates, rate_year=11, attained_age=73, premiums_to_date=0.0,
        projection_date=date(2026, 9, 26), corridor_rate=mdbr)
    assert result.corridor_rate == mdbr
    assert result.gross_db == math.floor(mdbr * 20_000.0)
    assert result.corr_amount == result.gross_db - 25_000.0
    plain = calculate_deduction(
        20_000.0, policy, config, rates, rate_year=11, attained_age=73, premiums_to_date=0.0,
        projection_date=date(2026, 9, 26))
    assert plain.gross_db == 25_000.0
