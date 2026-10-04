"""EPU schedule duration after a skipped-coverage reinstatement.

CyberLife's EPU schedule month is the calendar coverage month less the monthliversaries in
(LAP_DT, REN_DT] of the MOST RECENT LH_COV_SKIPPED_PER period only. Evidence (RERUN coverage
push 2026-10-04, 1U145500/1U145800 plans with a 120-month EPU): 111 of 111 lapse-gap policies
past the EPU period are on/off as predicted and all 13 observed end months match; excluding
every gap gets 109 (fails UIP53849 and UIP76119). COI, the monthly fee and the %-of-AV charge
are not shifted.
"""
from datetime import date

import pytest

from suiteview.illustration.core.monthly_deduction import _calculate_epu_charges
from suiteview.illustration.core.rate_loader import IllustrationRates
from suiteview.illustration.core.skipped_coverage import epu_schedule_year, skipped_monthliversaries
from suiteview.illustration.models.plancode_config import PlancodeConfig
from suiteview.illustration.models.policy_data import (
    CoverageSegment,
    IllustrationPolicyData,
    SkippedCoveragePeriod,
)

# A 10-year (120-month) EPU: 0.235 per 1,000 a month, then 0.
EPU_SCHEDULE = [None] + [0.235] * 10 + [0.0] * 111


def _gap(lapse, reinstated):
    return SkippedCoveragePeriod(lapse_date=lapse, reinstatement_date=reinstated)


def _policy(issue, face, periods, valuation):
    segment = CoverageSegment(
        coverage_phase=1, issue_date=issue, issue_age=45, rate_sex="M", rate_class="N",
        face_amount=face, original_face_amount=face, units=face / 1000.0)
    return IllustrationPolicyData(
        plancode="1U145500", db_option="A", face_amount=face, segments=[segment],
        issue_date=issue, valuation_date=valuation, skipped_coverage_periods=list(periods))


def _epu(policy, when):
    rates = IllustrationRates(epu=EPU_SCHEDULE, segment_epu={1: EPU_SCHEDULE})
    return _calculate_epu_charges(
        policy.segments, policy.face_amount, policy, PlancodeConfig(), rates, 1, when).epu_charge


def _month_date(issue, month):
    from dateutil.relativedelta import relativedelta

    return issue + relativedelta(months=month - 1)


def _last_epu_month(policy):
    """Last calendar coverage month that still charges the EPU."""
    months = [m for m in range(100, 200) if _epu(policy, _month_date(policy.issue_date, m)) > 0]
    return max(months)


# UIP88048 (1U145800, issued 2016-08-05, face 250,001): gaps of 1 and 2 months.
UIP88048 = dict(
    issue=date(2016, 8, 5), face=250_001.0, valuation=date(2026, 9, 5),
    periods=(_gap(date(2019, 10, 6), date(2019, 11, 5)), _gap(date(2020, 11, 6), date(2021, 1, 5))))
# UIP53849 (issued 2015-01-26): gaps of 7, 4, 2 and 15 months; EPU ended after month 135.
UIP53849 = dict(
    issue=date(2015, 1, 26), face=56_596.0, valuation=date(2026, 9, 26),
    periods=(_gap(date(2018, 8, 26), date(2019, 3, 26)), _gap(date(2019, 11, 26), date(2020, 3, 26)),
             _gap(date(2022, 2, 27), date(2022, 4, 26)), _gap(date(2022, 11, 26), date(2024, 2, 26))))
# UIP76119 (issued 2016-04-11): gaps of 5, 1 and 2 months; EPU ended after month 122.
UIP76119 = dict(
    issue=date(2016, 4, 11), face=118_936.0, valuation=date(2026, 9, 11),
    periods=(_gap(date(2016, 9, 11), date(2017, 2, 11)), _gap(date(2017, 12, 12), date(2018, 1, 12)),
             _gap(date(2018, 5, 12), date(2018, 7, 11))))
# UE182343 (1U147500, issued 2022-03-21): gaps of 4 and 2 months, still inside the EPU period.
UE182343 = dict(
    issue=date(2022, 3, 21), face=249_000.0, valuation=date(2026, 9, 21),
    periods=(_gap(date(2024, 8, 22), date(2024, 12, 21)), _gap(date(2025, 5, 21), date(2025, 7, 21))))


@pytest.mark.parametrize("case,expected", [
    (UIP88048, [1, 2]), (UIP53849, [7, 4, 2, 15]), (UIP76119, [5, 1, 2]), (UE182343, [4, 2]),
])
def test_skipped_monthliversaries_match_the_research_counts(case, expected):
    assert [skipped_monthliversaries(case["issue"], p.lapse_date, p.reinstatement_date)
            for p in case["periods"]] == expected


def test_uip88048_charges_the_epu_through_month_122_and_stops_on_2026_10_05():
    policy = _policy(**UIP88048)

    # Valuation 2026-09-05 is calendar month 122: CyberLife charged 0.235 x 250.001 = 58.75.
    assert _epu(policy, date(2026, 9, 5)) == pytest.approx(58.75)
    assert _epu(policy, date(2026, 10, 5)) == 0.0
    assert _last_epu_month(policy) == 122


@pytest.mark.parametrize("case,last_month", [(UIP53849, 135), (UIP76119, 122), (UIP88048, 122)])
def test_only_the_latest_gap_extends_the_epu(case, last_month):
    """Excluding every gap would predict 148 (UIP53849), 128 (UIP76119) and 123 (UIP88048)."""
    assert _last_epu_month(_policy(**case)) == last_month


def test_uip53849_and_uip76119_are_off_at_their_valuation():
    assert _epu(_policy(**UIP53849), UIP53849["valuation"]) == 0.0
    assert _epu(_policy(**UIP76119), UIP76119["valuation"]) == 0.0


def test_ue182343_inside_the_epu_period_keeps_charging():
    policy = _policy(**UE182343)

    assert _epu(policy, UE182343["valuation"]) == pytest.approx(58.52)   # 0.235 x 249 half-up
    assert _last_epu_month(policy) == 122


def test_policies_without_a_skipped_period_keep_calendar_duration():
    never = _policy(date(2016, 8, 5), 250_001.0, (), date(2026, 9, 5))

    assert _last_epu_month(never) == 120
    assert _epu(never, date(2026, 8, 5)) == 0.0
    assert epu_schedule_year(date(2016, 8, 5), None, date(2026, 9, 5), 11) == 11


def test_coverage_issued_after_the_lapse_is_not_shifted():
    gap = _gap(date(2019, 10, 6), date(2019, 11, 5))

    assert epu_schedule_year(date(2020, 1, 5), gap, date(2030, 1, 5), 11) == 11
    assert epu_schedule_year(date(2016, 8, 5), gap, date(2026, 8, 5), 11) == 10


def test_a_rollback_before_the_latest_gap_uses_the_earlier_one():
    policy = _policy(**UIP88048)
    policy.valuation_date = date(2020, 10, 5)

    assert policy.latest_skipped_coverage_period.reinstatement_date == date(2019, 11, 5)
    assert _last_epu_month(policy) == 121


def test_run_from_issue_keeps_calendar_duration():
    policy = _policy(**UIP88048)
    policy.run_from_issue = True

    assert _last_epu_month(policy) == 120
