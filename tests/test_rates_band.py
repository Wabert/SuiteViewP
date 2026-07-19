"""Rates.get_band — issue-date-dependent band boundary (RERUN Rates_Control CZ).

The 14 plancodes in Rates_Control!CZ12:CZ32 ("Use Band Table 2 by Issue Date")
band with mBandTable2 (band 3 starts at 250,000 — the UL_Rates BANDSPECS
thresholds) when the POLICY issue date is on/after CZ9 = 2018-10-01, and with
mBandTable1 (band 3 starts at 250,001) when issued before it. All other
plancodes band with their BANDSPECS thresholds regardless of issue date.
Thresholds are inclusive (face >= threshold), matching RERUN's approximate
VLOOKUP in CalcEngine vCurrentBand.
"""
from __future__ import annotations

from datetime import date, datetime

import pytest

from suiteview.core.rates import Rates

# UL_Rates BANDSPECS for the IUL14 family (= RERUN mBandTable2).
_BANDSPECS_5 = [[0, 1], [100000, 2], [250000, 3], [500000, 4], [1000000, 5]]

CZ_PLANCODE = "1U145500"      # in Rates_Control CZ12:CZ32, BandTable2IssueDate=2018-10-01
NON_CZ_PLANCODE = "1U143900"  # in plancode_table.json, no BandTable2IssueDate
UNKNOWN_PLANCODE = "ZZTRAD00"  # not in plancode_table.json at all

CUTOFF = date(2018, 10, 1)


@pytest.fixture()
def rates(monkeypatch):
    r = Rates()
    monkeypatch.setattr(
        Rates, "get_rates",
        lambda self, rate_type, plancode, *a, **k: list(_BANDSPECS_5),
    )
    return r


def test_plancode_table_carries_cz_rule():
    """The CZ plancodes carry the cutoff in plancode_table.json; others don't."""
    from suiteview.illustration.models.plancode_config import load_plancode

    assert load_plancode(CZ_PLANCODE).band_table2_issue_date == CUTOFF
    assert load_plancode(NON_CZ_PLANCODE).band_table2_issue_date is None


def test_cz_plancode_on_or_after_cutoff_is_inclusive_band3(rates):
    """(a) CZ plancode issued on/after 2018-10-01: face 250,000 -> band 3."""
    assert rates.get_band(CZ_PLANCODE, 250000, issue_date=CUTOFF) == 3
    assert rates.get_band(CZ_PLANCODE, 250000, issue_date=date(2019, 5, 1)) == 3


def test_cz_plancode_before_cutoff_band3_starts_at_250001(rates):
    """(b) CZ plancode issued before 2018-10-01: band 3 starts at 250,001.

    UE013383 (1U145500, issued 2017, face exactly 250,000) — the admin system
    and RERUN band it 2, proven by the stored monthly COI matching band 2.
    """
    assert rates.get_band(CZ_PLANCODE, 250000, issue_date=date(2017, 6, 1)) == 2
    assert rates.get_band(CZ_PLANCODE, 250000.5, issue_date=date(2017, 6, 1)) == 2
    assert rates.get_band(CZ_PLANCODE, 250001, issue_date=date(2017, 6, 1)) == 3
    # datetime issue dates normalize to date
    assert rates.get_band(CZ_PLANCODE, 250000, issue_date=datetime(2017, 6, 1)) == 2


def test_non_cz_plancode_thresholds_inclusive_regardless_of_date(rates):
    """(c) Non-CZ plancodes: inclusive BANDSPECS thresholds, date irrelevant."""
    for plancode in (NON_CZ_PLANCODE, UNKNOWN_PLANCODE):
        assert rates.get_band(plancode, 250000) == 3
        assert rates.get_band(plancode, 250000, issue_date=date(2017, 6, 1)) == 3
        assert rates.get_band(plancode, 249999, issue_date=date(2017, 6, 1)) == 2


def test_cz_plancode_without_issue_date_uses_raw_bandspecs(rates):
    """No issue date supplied -> raw BANDSPECS (band-table-2) thresholds."""
    assert rates.get_band(CZ_PLANCODE, 250000) == 3


def test_faces_inside_bands_unchanged_by_date_rule(rates):
    """(d) Faces not on the band-3 boundary band identically pre/post cutoff."""
    for issue in (None, date(2017, 6, 1), date(2019, 5, 1)):
        assert rates.get_band(CZ_PLANCODE, 50000, issue_date=issue) == 1
        assert rates.get_band(CZ_PLANCODE, 100000, issue_date=issue) == 2
        assert rates.get_band(CZ_PLANCODE, 300000, issue_date=issue) == 3
        assert rates.get_band(CZ_PLANCODE, 500000, issue_date=issue) == 4
        assert rates.get_band(CZ_PLANCODE, 2000000, issue_date=issue) == 5
