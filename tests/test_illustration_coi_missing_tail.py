"""A COI source that ends before maturity loads; reaching an unloaded year stops loudly.

80110529/81110329: the IAF prints ages 0-99, PLAN_DEF maturity 103. The policies are at
attained ages 67-84 and CyberLife's current MD matches the loaded rates, so the valuation
month calculates; a projection that reaches attained 100 raises (no extrapolation, no 0).
"""
from datetime import date
from types import SimpleNamespace

import pytest

from suiteview.core.rates_schema import CellAssignment, RateSetInfo, ScheduleWindow
from suiteview.illustration.core import iswl_rates
from suiteview.illustration.core.monthly_deduction import _rate_from_schedule
from suiteview.illustration.core.rate_loader import MissingRate, RateLookupError

CELL = CellAssignment("", "F", "B", "1", "**", "", "COI", 1)


class _Reader:
    def __init__(self, durations):
        self.values = {(42, d): 1.0 + d for d in durations}

    def schedule_windows(self, _schedule_id):
        return [ScheduleWindow(1, "C", date(1900, 1, 1), None, 10)]

    def rate_sets(self, _ids):
        return {10: RateSetInfo(10, "COI", "IA_DUR", "", "")}

    def rate_values(self, _ids, _issue_age):
        return {10: dict(self.values)}


def _load(durations, **kwargs):
    return iswl_rates._schedule(
        _Reader(durations), CELL, "C", issue_age=42, issue_date=date(1984, 6, 25), years=61,
        calendar=True, label="80110529 COI", **kwargs)


def test_missing_tail_loads_the_loaded_years_and_marks_the_rest():
    schedule = _load(range(1, 59), missing_tail=True)

    assert len(schedule) == 62
    assert schedule[58] == 59.0
    assert all(isinstance(rate, MissingRate) for rate in schedule[59:])
    with pytest.raises(RateLookupError, match="policy year 59 .*attained age 100"):
        _rate_from_schedule(schedule, 59)
    with pytest.raises(RateLookupError, match="policy year 61"):
        schedule[61] / 12


def test_without_missing_tail_the_gap_still_fails_at_load():
    with pytest.raises(RateLookupError, match="no rate for policy year 59"):
        _load(range(1, 59))


def test_interior_gap_fails_even_with_missing_tail():
    with pytest.raises(RateLookupError, match="after unloaded years"):
        _load([d for d in range(1, 62) if d != 30], missing_tail=True)


def test_missing_year_one_is_not_a_tail():
    with pytest.raises(RateLookupError, match="no rate for policy year 1 "):
        _load([], missing_tail=True)


def test_current_policy_year_must_be_loaded():
    schedule = _load(range(1, 59), missing_tail=True)
    segment = SimpleNamespace(issue_age=42)

    iswl_rates._require_current_year(schedule, SimpleNamespace(policy_year=43), segment, "80110529 COI")
    with pytest.raises(RateLookupError, match="policy year 59"):
        iswl_rates._require_current_year(schedule, SimpleNamespace(policy_year=59), segment, "80110529 COI")
