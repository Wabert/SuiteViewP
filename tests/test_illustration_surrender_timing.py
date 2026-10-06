"""Surrender charge on a monthliversary- or anniversary-dated surrender (Robert, 10/5/2026: "match CyberLife").

CyberLife values a surrender dated on a monthliversary before it processes that monthliversary.
Annual-step per-unit plans therefore charge the prior coverage year's rate on the anniversary date
(CKPR ``FH_FIXED`` TRANS 'SF', 10/5/2026: of 346 anniversary-date surrenders whose two years' rates
differ, 331 match the prior year's rate and none the new year's). The monthly-graded charges are covered in
``test_illustration_ffl_graded_surrender.py`` and ``test_illustration_iswl.py``.
"""
from datetime import date, timedelta
from decimal import ROUND_HALF_UP, Decimal

import pytest

from suiteview.illustration.core import calc_engine
from suiteview.illustration.core.rate_loader import IllustrationRates
from suiteview.illustration.models.plancode_config import PlancodeConfig
from suiteview.illustration.models.policy_data import CoverageSegment, IllustrationPolicyData

ANICO = PlancodeConfig(company_sub="ANICO")


def _policy(issue, units, company="01"):
    return IllustrationPolicyData(company_code=company, issue_date=issue, segments=[
        CoverageSegment(coverage_phase=1, issue_date=issue, units=units)])


def _schedule(rates_by_year: dict) -> list:
    values = [None] + [0.0] * 40
    for year, rate in rates_by_year.items():
        values[year] = rate
    return values


def _charge(policy, rates, on, config=ANICO) -> Decimal:
    _, total, _, _ = calc_engine._calculate_surrender_charge(
        policy, rates, 1, on, config, account_value=0.0)
    return Decimal(repr(total)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


@pytest.mark.parametrize("policy_id, issue, on, units, schedule, charge, next_day", [
    # 1U143800, year 11 starts: CyberLife charged year 10's 39.03 per unit.
    ("U0586699", date(2007, 11, 5), date(2017, 11, 5), 100.0, {10: 39.03, 11: 31.25}, "3903.00", "3125.00"),
    # 1U143800: the schedule ends after year 15, but the year-16 anniversary still charges year 15.
    ("U0583960", date(2007, 8, 2), date(2022, 8, 2), 200.0, {15: 3.26}, "652.00", "0.00"),
    # 1U143900, 185 units: 6.12 (year 14), not 3.01 (year 15).
    ("U0625449", date(2010, 11, 1), date(2024, 11, 1), 185.0, {14: 6.12, 15: 3.01}, "1132.20", "556.85"),
])
def test_anniversary_dated_surrender_takes_the_prior_years_annual_rate(
        policy_id, issue, on, units, schedule, charge, next_day):
    policy = _policy(issue, units)
    rates = IllustrationRates(segment_scr={1: _schedule(schedule)})
    assert _charge(policy, rates, on) == Decimal(charge), policy_id
    assert _charge(policy, rates, on + timedelta(days=1)) == Decimal(next_day), policy_id


def test_annual_step_is_unchanged_on_other_monthliversaries():
    policy = _policy(date(2010, 11, 1), 1.0)
    rates = IllustrationRates(segment_scr={1: _schedule({14: 6.12, 15: 3.01})})
    rate = lambda on: calc_engine._segment_surrender_rate(  # noqa: E731
        policy, policy.segments[0], rates, 1, on, ANICO)
    assert rate(date(2024, 10, 1)) == 6.12            # year 14, m 11
    assert rate(date(2024, 12, 1)) == 3.01            # year 15, m 1
    assert rate(date(2025, 10, 31)) == 3.01


@pytest.mark.parametrize("on, year", [
    (date(2026, 2, 28), 2),       # the clamped anniversary: still year 2
    (date(2026, 3, 1), 3),
    (date(2028, 2, 29), 4),       # leap-year anniversary: still year 4
    (date(2028, 3, 1), 5),
])
def test_feb_29_issue_annual_year_starts_the_day_after_the_anniversary(on, year):
    policy = _policy(date(2024, 2, 29), 1.0)
    rates = IllustrationRates(segment_scr={1: _schedule({y: float(y) for y in range(1, 10)})})
    assert calc_engine._segment_surrender_rate(
        policy, policy.segments[0], rates, 1, on, ANICO) == float(year)


def test_increase_segment_takes_its_own_prior_year_on_its_anniversary():
    policy = IllustrationPolicyData(company_code="01", issue_date=date(2010, 1, 10), segments=[
        CoverageSegment(coverage_phase=1, issue_date=date(2010, 1, 10), units=1.0),
        CoverageSegment(coverage_phase=2, issue_date=date(2013, 6, 10), units=1.0),
    ])
    rates = IllustrationRates(segment_scr={1: _schedule({4: 7.0, 5: 6.0}), 2: _schedule({1: 20.0, 2: 18.0})})
    rate_by = calc_engine._calculate_surrender_charge(
        policy, rates, 1, date(2014, 6, 10), ANICO, account_value=0.0)[2]
    assert rate_by == {"cov1": 6.0, "cov2": 20.0}     # base mid-year 5; the increase's anniversary: year 1
    rate_by = calc_engine._calculate_surrender_charge(
        policy, rates, 1, date(2014, 6, 11), ANICO, account_value=0.0)[2]
    assert rate_by == {"cov1": 6.0, "cov2": 18.0}


def test_no_dates_falls_back_to_the_rate_year():
    policy = _policy(date(2010, 11, 1), 1.0)
    rates = IllustrationRates(segment_scr={1: _schedule({14: 6.12, 15: 3.01})})
    assert calc_engine._segment_surrender_rate(policy, policy.segments[0], rates, 15, None, ANICO) == 3.01
    policy.segments[0].issue_date = None
    assert calc_engine._segment_surrender_rate(
        policy, policy.segments[0], rates, 15, date(2024, 11, 1), ANICO) == 3.01
