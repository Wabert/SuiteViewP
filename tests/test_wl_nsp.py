"""Explicit-basis NSP imports cannot relabel unrelated source rates."""

import csv
from datetime import date
from decimal import Decimal

import pytest

from suiteview.ratemanager.database_loader import PackageValidationError
from suiteview.ratemanager.whole_life import parsers
from suiteview.ratemanager.whole_life.schema import TABLES
from suiteview.ratemanager.whole_life.service import parse_sources


def source(tmp_path, rows=None, columns=parsers.NSP_COLUMNS):
    path = tmp_path / "verified_nsp.csv"
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns)
        writer.writeheader()
        if rows is not None:
            writer.writerows(rows)
    return path


def record(**overrides):
    return {
        "USER_CODE": "06", "RATE_KEY": "test", "BASIS_ID": "basis1",
        "BASIS_DESCRIPTION": "Synthetic test basis; not a live rate",
        "SEX": "m", "RATECLASS": "n", "ISSUE_AGE": "40", "DURATION": "1",
        "EFFECTIVE_DATE": "2026-01-01", "RATE_PER": "1000", "RATE": "123.45678901",
        **overrides,
    }


def test_all_four_parser_definitions_match_physical_schemas():
    for table, prefix in (
        ("WL_RATE_CV", "CV"), ("WL_RATE_NSP", "NSP"),
        ("WL_RATE_PUI", "PUI"), ("WL_RATE_PREM", "IAF"),
    ):
        assert TABLES[table].spec.columns == getattr(parsers, prefix + "_COLUMNS")
        assert TABLES[table].keys == getattr(parsers, prefix + "_KEYS")
        assert TABLES[table].create


def test_nsp_preserves_basis_units_dates_and_decimal_precision(tmp_path):
    rows = parsers.parse_nsp(source(tmp_path, [record()]))
    assert rows[0]["RATE_KEY"] == "TEST"
    assert rows[0]["BASIS_ID"] == "BASIS1"
    assert rows[0]["SEX"] == "M"
    assert rows[0]["BASIS_DESCRIPTION"] == record()["BASIS_DESCRIPTION"]
    assert rows[0]["RATE"] == Decimal("123.45678901")
    assert rows[0]["RATE_PER"] == Decimal("1000")
    assert rows[0]["EFFECTIVE_DATE"] == date(2026, 1, 1)


def test_nsp_package_preserves_zero_and_deduplicates_identical_keys(tmp_path):
    row = record(RATE="0", SEX="", RATECLASS="")
    package = parse_sources("NSP", [str(source(tmp_path, [row, row]))])
    assert package.row_counts == {"WL_RATE_NSP": 1}
    data = package.tables["WL_RATE_NSP"]
    assert data.rows[0][data.spec.column_index("RATE")] == Decimal(0)
    assert data.rows[0][data.spec.column_index("SEX")] == ""


@pytest.mark.parametrize("change", [
    {"BASIS_ID": ""}, {"BASIS_DESCRIPTION": ""}, {"RATE_KEY": ""},
    {"RATE_PER": ""}, {"RATE_PER": "0"}, {"RATE_PER": "-1"},
    {"RATE": "-1"}, {"RATE": "NaN"}, {"RATE": "1.000000001"},
    {"EFFECTIVE_DATE": "2026-02-30"}, {"EFFECTIVE_DATE": "01/01/2026"},
    {"USER_CODE": "6"}, {"DURATION": "1.5"}, {"ISSUE_AGE": "-1"},
])
def test_nsp_invalid_or_unqualified_values_fail(tmp_path, change):
    with pytest.raises(PackageValidationError):
        parsers.parse_nsp(source(tmp_path, [record(**change)]))


def test_nsp_conflicting_basis_or_rate_for_same_key_fails(tmp_path):
    with pytest.raises(PackageValidationError, match="Conflicting duplicate"):
        parsers.parse_nsp(source(tmp_path, [record(), record(RATE="999")]))


def test_nsp_distinct_basis_remains_distinct(tmp_path):
    rows = parsers.parse_nsp(source(
        tmp_path, [record(), record(BASIS_ID="basis2", RATE="999")]
    ))
    assert len(rows) == 2


def test_nsp_empty_template_is_not_a_successful_load(tmp_path):
    with pytest.raises(PackageValidationError, match="No supported rate"):
        parsers.parse_nsp(source(tmp_path))


def test_nsp_missing_basis_column_is_not_accepted(tmp_path):
    with pytest.raises(PackageValidationError, match="canonical CSV header"):
        parsers.parse_nsp(source(tmp_path, columns=("RATE_KEY", "RATE")))
