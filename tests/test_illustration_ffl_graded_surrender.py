"""Company-26 FFL UL per-unit surrender charges are graded monthly between coverage years.

Every case is a live CyberLife full surrender (CKPR ``FH_FIXED`` TRANS 'SF', not reversed,
no loan, dated between monthliversaries). The schedules hold the plan's loaded per-unit
``SCR`` for the two coverage years involved; CyberLife's charge is the graded rate x units,
truncated to cents.
"""
from datetime import date
from decimal import ROUND_DOWN, Decimal

import pytest

from suiteview.illustration.core import calc_engine
from suiteview.illustration.core.rate_loader import IllustrationRates
from suiteview.illustration.models.plancode_config import PlancodeConfig
from suiteview.illustration.models.policy_data import CoverageSegment, IllustrationPolicyData

FFL = PlancodeConfig(company_sub="FFL")


def _schedule(year: int, rate: float, prior: float) -> list:
    """Per-unit SCR by coverage year with ``prior`` in year - 1 and ``rate`` in year."""
    values = [None] + [0.0] * (year + 5)
    values[year - 1], values[year] = prior, rate
    return values


def _charge(policy, rates, on, config=FFL) -> Decimal:
    _, _, rate_by, _ = calc_engine._calculate_surrender_charge(
        policy, rates, 1, on, config, account_value=0.0)
    segments = [s for s in policy.segments if s is not None]
    total = sum((Decimal(repr(rate_by[f"cov{i}"])) * Decimal(repr(s.units))
                 for i, s in enumerate(segments, start=1)), Decimal(0))
    return total.quantize(Decimal("0.01"), rounding=ROUND_DOWN)


def _single(issue, units, year, rate, prior, company="26"):
    policy = IllustrationPolicyData(company_code=company, issue_date=issue, segments=[
        CoverageSegment(coverage_phase=1, issue_date=issue, units=units)])
    return policy, IllustrationRates(segment_scr={1: _schedule(year, rate, prior)})


@pytest.mark.parametrize("policy_id, issue, on, units, year, rate, prior, charge", [
    # 1U14L400: 7.29 + 0.52 x trunc5(7/12) = 7.593
    ("UFF90027", date(2016, 5, 16), date(2021, 11, 15), 100.0, 6, 7.29, 7.81, "759.30"),
    # NU1F3G00: 2.98 + 0.75 x 0.91666 = 3.667495 -> 3.667 (trunc5 of 11/12, then round3)
    ("000282603", date(2002, 5, 17), date(2017, 7, 10), 250.0, 16, 2.98, 3.73, "916.75"),
    # NU1F3G00: the charge runs a year past the last nonzero rate; 0.3975 -> 0.398
    ("000285396", date(2002, 11, 26), date(2022, 3, 14), 500.0, 20, 0.0, 0.53, "199.00"),
    # NU1F3M00: 3.607 x 325 = 1,172.275, truncated to cents
    ("000299253", date(2006, 2, 25), date(2018, 2, 19), 325.0, 12, 3.57, 4.02, "1172.27"),
    ("000304204", date(2007, 3, 19), date(2021, 5, 13), 100.0, 15, 11.0, 13.2, "1301.70"),
    # 1U14I400: 16.182 x 274 = 4,433.868, truncated
    ("000344453", date(2015, 12, 26), date(2023, 3, 13), 274.0, 8, 15.39, 16.34, "4433.86"),
])
def test_ffl_graded_charge_matches_cyberlife_full_surrenders(
        policy_id, issue, on, units, year, rate, prior, charge):
    policy, rates = _single(issue, units, year, rate, prior)
    assert _charge(policy, rates, on) == Decimal(charge), policy_id


def test_increase_segment_grades_with_the_policy_months():
    """NU1F3N00 000271576 (2018-07-10): base year 19 and a 2002-09-03 increase in its year 16
    both grade with the policy's 7 months; COLA segments stay free. CyberLife: 280.80."""
    issue = date(1999, 12, 3)
    policy = IllustrationPolicyData(company_code="26", issue_date=issue, segments=[
        CoverageSegment(coverage_phase=1, issue_date=issue, units=100.0),
        CoverageSegment(coverage_phase=7, issue_date=date(2002, 9, 3), units=50.0),
        CoverageSegment(coverage_phase=8, issue_date=date(2002, 12, 3), units=12.062, is_cola=True),
    ])
    rates = IllustrationRates(segment_scr={
        1: _schedule(19, 0.71, 1.41), 7: _schedule(16, 3.27, 4.09), 8: _schedule(16, 3.27, 4.09)})
    assert _charge(policy, rates, date(2018, 7, 10)) == Decimal("280.80")


def test_increase_segment_past_its_schedule_keeps_the_graded_tail():
    """NU1FU200 000170364 (2018-11-14): only the 2010-06-19 increase still charges, year 9 of
    its schedule (0 after 0.55 in year 8), graded with the policy's 11 months. CyberLife: 2.30."""
    issue = date(1985, 11, 19)
    policy = IllustrationPolicyData(company_code="26", issue_date=issue, segments=[
        CoverageSegment(coverage_phase=1, issue_date=issue, units=50.0),
        CoverageSegment(coverage_phase=14, issue_date=date(2010, 6, 19), units=50.0),
    ])
    rates = IllustrationRates(segment_scr={1: [None] + [0.0] * 40, 14: _schedule(9, 0.0, 0.55)})
    assert _charge(policy, rates, date(2018, 11, 14)) == Decimal("2.30")


def test_graded_rate_steps_monthly_and_year_1_is_flat():
    policy, rates = _single(date(2016, 5, 16), 1.0, 6, 7.29, 7.81)
    rate = lambda on: calc_engine._segment_surrender_rate(  # noqa: E731
        policy, policy.segments[0], rates, 1, on, FFL)
    assert rate(date(2021, 5, 17)) == 7.81            # year 6, m 0: rate(5)
    assert rate(date(2021, 6, 17)) == 7.767           # 7.29 + 0.52 x 0.91666
    assert rate(date(2022, 4, 17)) == 7.333           # m 11
    year_1, rates_1 = _single(date(2016, 5, 16), 1.0, 2, 5.0, 9.0)
    assert calc_engine._segment_surrender_rate(
        year_1, year_1.segments[0], rates_1, 1, date(2016, 9, 16), FFL) == 9.0


def test_feb_29_issue_starts_each_year_after_the_feb_28_monthliversary():
    policy, rates = _single(date(2024, 2, 29), 1.0, 3, 6.0, 7.2)
    rate = lambda on: calc_engine._segment_surrender_rate(  # noqa: E731
        policy, policy.segments[0], rates, 1, on, FFL)
    assert rate(date(2026, 3, 1)) == 7.2              # year 3, m 0
    assert rate(date(2026, 3, 30)) == 7.1             # year 3, m 1
    assert rate(date(2026, 3, 29)) == 7.2             # the m-1 monthliversary itself: m 0


def _full_schedule(rates_by_year: dict) -> list:
    values = [None] + [0.0] * 40
    for year, rate in rates_by_year.items():
        values[year] = rate
    return values


@pytest.mark.parametrize("policy_id, issue, on, units, schedule, charge", [
    # Monthliversary-dated: valued before that monthliversary is processed (m - 1).
    # 1U1F4L00, year 15 m 1 -> m 0: rate(14) = 4.38 (graded at m 1 would be 4.319).
    ("000315549", date(2009, 8, 4), date(2023, 9, 4), 250.0, {13: 5.11, 14: 4.38, 15: 3.65}, "1095.00"),
    # 1U1F4L00, year 14 m 2 -> m 1: 4.80 + 0.80 x 0.91666 = 5.533.
    ("000308327", date(2008, 4, 4), date(2021, 6, 4), 100.0, {12: 6.40, 13: 5.60, 14: 4.80}, "553.30"),
    # Anniversary-dated: the prior coverage year's last month (year d - 1, m 11).
    # NU1F3M00, 3.95 + 0.66 x 0.08333 = 4.005 (graded year 15 m 0 would be 3.95).
    ("000299327", date(2006, 3, 28), date(2020, 3, 28), 450.0, {13: 4.61, 14: 3.95, 15: 3.29}, "1802.25"),
    ("000299329", date(2006, 3, 28), date(2020, 3, 28), 450.0, {13: 3.91, 14: 3.35, 15: 2.79}, "1528.65"),
    # NU1F3M00, 1.23 + 0.31 x 0.08333 = 1.256.
    ("000297901", date(2005, 10, 25), date(2021, 10, 25), 50.0, {15: 1.54, 16: 1.23, 17: 0.92}, "62.80"),
])
def test_monthliversary_dated_surrender_takes_the_step_before_it_is_processed(
        policy_id, issue, on, units, schedule, charge):
    """Robert's 10/5/2026 ruling: match CyberLife, which values a surrender dated on a
    monthliversary (or anniversary) before it processes that monthliversary. Live CKPR
    FH_FIXED SF charges; the schedule's later-year rate only matters from the next day."""
    policy = IllustrationPolicyData(company_code="26", issue_date=issue, segments=[
        CoverageSegment(coverage_phase=1, issue_date=issue, units=units)])
    rates = IllustrationRates(segment_scr={1: _full_schedule(schedule)})
    assert _charge(policy, rates, on) == Decimal(charge), policy_id


def test_increase_segment_on_a_policy_monthliversary_steps_back_with_the_policy():
    """An increase issued on a policy monthliversary: on its own anniversary both counts step
    back one month, so the segment is in its prior year at the policy's prior month."""
    issue = date(2010, 1, 10)
    policy = IllustrationPolicyData(company_code="26", issue_date=issue, segments=[
        CoverageSegment(coverage_phase=1, issue_date=issue, units=1.0),
        CoverageSegment(coverage_phase=2, issue_date=date(2012, 7, 10), units=1.0),
    ])
    rates = IllustrationRates(segment_scr={1: _full_schedule({1: 9.0}),
                                           2: _full_schedule({1: 12.0, 2: 10.0, 3: 8.0})})
    rate = lambda on: calc_engine._segment_surrender_rate(  # noqa: E731
        policy, policy.segments[1], rates, 1, on, FFL)
    assert rate(date(2014, 7, 11)) == 9.0             # segment year 3, policy m 6: 8 + 2 x 0.5
    assert rate(date(2014, 7, 10)) == 11.167          # segment year 2, policy m 5: 10 + 2 x 0.58333


@pytest.mark.parametrize("company, config", [
    ("01", FFL),                                                        # not company 26
    ("26", PlancodeConfig(company_sub="ANICO")),                        # 1U144-1U147: annual step
    ("26", PlancodeConfig(company_sub="FFL", product_family="ISWL")),
    ("26", PlancodeConfig(company_sub="FFL", scr_pct_of_surrender_target=(0.5, 0.4))),
    ("26", None),
])
def test_annual_step_is_unchanged_without_grading_evidence(company, config):
    policy, rates = _single(date(2016, 5, 16), 100.0, 6, 7.29, 7.81, company=company)
    if config is None:
        policy.plancode = "UNUSED"
    _, total, _, _ = calc_engine._calculate_surrender_charge(
        policy, rates, 6, date(2021, 11, 15), config, account_value=0.0)
    assert total == pytest.approx(729.0)


def test_graded_rate_without_dates_falls_back_to_the_annual_step():
    policy, rates = _single(date(2016, 5, 16), 100.0, 6, 7.29, 7.81)
    segment = policy.segments[0]
    assert calc_engine._segment_surrender_rate(policy, segment, rates, 6, None, FFL) == 7.29
    segment.issue_date = None
    assert calc_engine._segment_surrender_rate(
        policy, segment, rates, 6, date(2021, 11, 15), FFL) == 7.29
