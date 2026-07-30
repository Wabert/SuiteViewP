from datetime import date

import pytest

from tools.create_sv_index_benchmark_minmax import (
    CREATE_SQL,
    TABLE_NAME,
    parse_config,
    parse_rate,
    parse_rows,
    summarize,
)


def test_benchmark_rates_are_normalized_from_percent_numbers():
    assert parse_rate("7.56") == pytest.approx(0.0756)
    assert parse_rate("3.88%") == pytest.approx(0.0388)


def test_benchmark_loader_supports_dry_run_and_windows_friendly_live_flags():
    assert parse_config([]) == {"dry_run": True, "dsn": "UL_Rates"}
    assert parse_config(["--live"]) == {"dry_run": False, "dsn": "UL_Rates"}
    assert parse_config(["--dsn=OtherRates"]) == {
        "dry_run": False,
        "dsn": "OtherRates",
    }


def test_benchmark_source_parses_without_conflicts_and_collapses_exact_duplicates():
    rows, errors, duplicates = parse_rows()
    summary = summarize(rows, duplicates)

    assert errors == []
    assert all(row[4] >= row[5] for row in rows)
    assert summary == {
        "source_row_count": 275,
        "unique_row_count": 258,
        "exact_duplicates_collapsed": 17,
        "distinct_plancodes": [
            "1U144600",
            "1U144700",
            "1U144800",
            "1U145500",
            "1U145600",
            "1U145800",
            "1U145900",
            "1U146400",
            "1U146500",
            "1U146800",
            "1U146900",
            "1U147400",
            "1U147500",
            "1U147800",
            "1U147900",
            "1U148000",
            "1U148100",
        ],
        "distinct_rein_block_ind": ["", "R"],
        "distinct_funds": ["IP", "IR", "IX"],
        "effective_date_range": ["1900-01-01", "2026-03-01"],
        "minimum_rate": 0.0234,
        "maximum_rate": 0.0987,
    }


def test_benchmark_source_preserves_reinsurance_and_date_specific_values():
    rows, errors, _duplicates = parse_rows()
    assert errors == []
    by_key = {row[:4]: row[4:] for row in rows}

    assert by_key[("1U145600", "R", "IX", date(2026, 3, 1))] == pytest.approx(
        (0.0704, 0.0397)
    )
    assert by_key[("1U146800", "", "IP", date(2023, 2, 1))] == pytest.approx(
        (0.0886, 0.0439)
    )
    assert by_key[("1U148100", "", "IX", date(2017, 1, 1))] == pytest.approx(
        (0.0765, 0.0456)
    )


def test_benchmark_table_uses_requested_columns_and_composite_key():
    assert TABLE_NAME == "SV_INDEX_BENCHMARK_MINMAX"
    for column in (
        "PLAN_ID",
        "REIN_BLOCK_IND",
        "FUND_ID",
        "EFFECTIVE_DATE",
        "MAX_GEOMETRIC_AVG",
        "MIN_GEOMETRIC_AVG",
    ):
        assert f"[{column}]" in CREATE_SQL

    assert (
        "([PLAN_ID], [REIN_BLOCK_IND], [FUND_ID], [EFFECTIVE_DATE])"
        in CREATE_SQL
    )
