"""Safety and validation tests for the Rate Manager UL_Rates loader."""

from __future__ import annotations

import csv
from collections import defaultdict

import pytest

from suiteview.ratemanager.database_loader import (
    _database_row,
    LoadAction,
    PackageValidationError,
    RateDatabaseError,
    TABLE_SPECS,
    WorkupPackage,
    _chunks,
    analyze_package,
    coerce_row,
    create_execution_plan,
    verify_package_state,
)


def _base_rows():
    return {
        "POINT_PVSRB": [[
            "PLAN1", 1, "M", "N", 1, "AA",
            None, None, None, None, 10, None, None, None, None, None,
        ]],
        "RATE_COI": [[10, 1, 20, 1, "0.125000"]],
        "RATE_TRGPREM": [],
        "RATE_SCR": [],
        "RATE_EPU": [],
        "POINT_BENEFIT": [[
            "PLAN1", "21", None, 1, "M", "N", 1, 2100, 2100,
        ]],
        "RATE_BENCOI": [[2100, 1, 20, 1, "0.250000"]],
        "RATE_BENTRG": [[2100, 20, "1.100000", "1.000000"]],
    }


def _write_package(tmp_path, rows=None):
    rows = rows or _base_rows()
    for table_name, spec in TABLE_SPECS.items():
        path = tmp_path / f"{table_name}.csv"
        with path.open("w", newline="", encoding="utf-8-sig") as handle:
            writer = csv.writer(handle)
            writer.writerow(spec.columns)
            writer.writerows(rows[table_name])
    return WorkupPackage.load(tmp_path)


class FakeRepository:
    def __init__(self, rows=None, references=None):
        self.rows = {
            name: [
                coerce_row(TABLE_SPECS[name], row, source="fake database")
                for row in table_rows
            ]
            for name, table_rows in (rows or {}).items()
        }
        self.references = references or {}

    def validate_schema(self):
        return None

    def fetch_pointer_rows(self, table_name, plancode):
        spec = TABLE_SPECS[table_name]
        pos = spec.column_index("Plancode")
        return [
            tuple(row) for row in self.rows.get(table_name, [])
            if row[pos] == plancode
        ]

    def fetch_existing_indexes(self, table_name, indexes):
        spec = TABLE_SPECS[table_name]
        wanted = set(indexes)
        return {
            spec.index_value(tuple(row))
            for row in self.rows.get(table_name, [])
            if spec.index_value(tuple(row)) in wanted
        }

    def fetch_rate_rows(self, table_name, indexes):
        spec = TABLE_SPECS[table_name]
        wanted = set(indexes)
        return [
            tuple(row) for row in self.rows.get(table_name, [])
            if spec.index_value(tuple(row)) in wanted
        ]

    def fetch_index_references(self, table_name, indexes):
        wanted = set(indexes)
        return {
            index: set(plancodes)
            for index, plancodes in self.references.get(table_name, {}).items()
            if index in wanted
        }


def _all_insert_actions():
    return {name: LoadAction.INSERT for name in TABLE_SPECS}


def test_csv_headers_map_to_physical_ul_rates_columns():
    assert TABLE_SPECS["RATE_COI"].columns[0] == "Index(COI)"
    assert TABLE_SPECS["RATE_SCR"].columns[0] == "Index(SCR)"
    assert TABLE_SPECS["RATE_EPU"].columns[0] == "Index(EPU)"
    assert TABLE_SPECS["RATE_BENCOI"].columns[0] == "Index(BENCOI)"
    assert TABLE_SPECS["RATE_BENTRG"].columns == (
        "Index(BENTRG)", "IssueAge", "Rate(MTP)", "Rate(CTP)",
    )


def test_database_row_binds_rate_decimals_as_sql_floats():
    spec = TABLE_SPECS["RATE_BENTRG"]
    row = coerce_row(
        spec,
        [2100, 20, "1.123456789", "0.987654321"],
        source="test",
    )

    bound = _database_row(spec, row)

    assert bound == (2100, 20, 1.123456789, 0.987654321)
    assert all(isinstance(value, float) for value in bound[2:])


@pytest.mark.parametrize("value", ["NaN", "Infinity", "-Infinity"])
def test_rate_values_must_be_finite(value):
    with pytest.raises(PackageValidationError, match="finite number"):
        coerce_row(
            TABLE_SPECS["RATE_COI"],
            [10, 1, 20, 1, value],
            source="test",
        )


def test_workup_package_accepts_blank_benefit_key_value(tmp_path):
    package = _write_package(tmp_path)

    assert package.plancode == "PLAN1"
    assert package.tables["POINT_BENEFIT"].rows[0][2] == ""


def test_workup_package_rejects_duplicate_primary_key(tmp_path):
    rows = _base_rows()
    rows["RATE_COI"].append(list(rows["RATE_COI"][0]))

    with pytest.raises(PackageValidationError, match="duplicate key"):
        _write_package(tmp_path, rows)


def test_new_package_builds_safe_all_table_insert_plan(tmp_path):
    package = _write_package(tmp_path)
    analysis = analyze_package(package, FakeRepository())

    plan = create_execution_plan(package, analysis, _all_insert_actions())

    assert plan.is_safe
    assert plan.insert_rows["POINT_PVSRB"] == package.tables["POINT_PVSRB"].rows
    assert plan.insert_rows["RATE_COI"] == package.tables["RATE_COI"].rows


def test_analysis_reports_each_database_recheck_phase(tmp_path):
    package = _write_package(tmp_path)
    messages = []

    analyze_package(package, FakeRepository(), messages.append)

    assert messages[0] == "Validating UL_Rates table schemas..."
    assert any("Rechecking RATE_COI" in message for message in messages)
    assert any("Rechecking RATE_TRGPREM" in message for message in messages)


def test_chunks_supports_batched_rate_rows():
    rows = tuple((index, index / 10) for index in range(5))

    assert list(_chunks(rows, size=2)) == [
        ((0, 0.0), (1, 0.1)),
        ((2, 0.2), (3, 0.3)),
        ((4, 0.4),),
    ]


def test_existing_plancode_requires_explicit_pointer_replace(tmp_path):
    package = _write_package(tmp_path)
    existing = _base_rows()
    repository = FakeRepository(existing)

    analysis = analyze_package(package, repository)
    plan = create_execution_plan(package, analysis, _all_insert_actions())

    messages = defaultdict(list)
    for issue in plan.issues:
        messages[issue.table_name].append(issue.message)
    assert any("explicitly choose Replace" in msg for msg in messages["POINT_PVSRB"])
    assert any("explicitly choose Replace" in msg for msg in messages["POINT_BENEFIT"])
    assert plan.insert_rows["RATE_COI"] == ()


def test_owned_different_index_requires_pointer_and_rate_replace(tmp_path):
    package = _write_package(tmp_path)
    existing = _base_rows()
    existing["RATE_COI"] = [[10, 1, 20, 1, "0.999000"]]
    repository = FakeRepository(
        existing,
        references={"RATE_COI": {10: {"PLAN1"}}},
    )
    analysis = analyze_package(package, repository)

    actions = {name: LoadAction.SKIP for name in TABLE_SPECS}
    actions["RATE_COI"] = LoadAction.REPLACE
    missing_pointer_plan = create_execution_plan(package, analysis, actions)
    assert any(
        issue.table_name == "RATE_COI"
        and "POINT_PVSRB to use Replace" in issue.message
        for issue in missing_pointer_plan.issues
    )

    actions["POINT_PVSRB"] = LoadAction.REPLACE
    safe_plan = create_execution_plan(package, analysis, actions)
    assert safe_plan.is_safe
    assert safe_plan.delete_indexes["RATE_COI"] == frozenset({10})
    assert safe_plan.insert_rows["RATE_COI"] == package.tables["RATE_COI"].rows
    assert "POINT_PVSRB" in safe_plan.delete_pointer_plancodes


def test_cross_plancode_index_collision_is_never_replaceable(tmp_path):
    package = _write_package(tmp_path)
    existing = _base_rows()
    existing["RATE_COI"] = [[10, 1, 20, 1, "0.999000"]]
    repository = FakeRepository(
        existing,
        references={"RATE_COI": {10: {"PLAN1", "OTHER_PLAN"}}},
    )
    analysis = analyze_package(package, repository)
    actions = {name: LoadAction.SKIP for name in TABLE_SPECS}
    actions["POINT_PVSRB"] = LoadAction.REPLACE
    actions["RATE_COI"] = LoadAction.REPLACE

    plan = create_execution_plan(package, analysis, actions)

    assert not plan.is_safe
    assert any(
        issue.table_name == "RATE_COI" and "OTHER_PLAN" in issue.message
        for issue in plan.issues
    )


def test_pointer_load_blocks_when_referenced_rate_index_is_missing(tmp_path):
    package = _write_package(tmp_path)
    repository = FakeRepository()
    analysis = analyze_package(package, repository)
    actions = {name: LoadAction.SKIP for name in TABLE_SPECS}
    actions["POINT_PVSRB"] = LoadAction.INSERT

    plan = create_execution_plan(package, analysis, actions)

    assert any(
        issue.table_name == "POINT_PVSRB"
        and "missing RATE_COI index(es): 10" in issue.message
        for issue in plan.issues
    )


def test_pointer_cannot_reuse_index_whose_existing_data_differs(tmp_path):
    package = _write_package(tmp_path)
    existing = _base_rows()
    existing["RATE_COI"] = [[10, 1, 20, 1, "9.999000"]]
    repository = FakeRepository(
        existing,
        references={"RATE_COI": {10: {"OTHER_PLAN"}}},
    )
    analysis = analyze_package(package, repository)
    actions = {name: LoadAction.SKIP for name in TABLE_SPECS}
    actions["POINT_PVSRB"] = LoadAction.REPLACE

    plan = create_execution_plan(package, analysis, actions)

    assert any(
        issue.table_name == "POINT_PVSRB"
        and "differs from this workup" in issue.message
        for issue in plan.issues
    )


def test_post_commit_verification_requires_exact_selected_index_content(tmp_path):
    package = _write_package(tmp_path)
    repository = FakeRepository(_base_rows())
    actions = {name: LoadAction.INSERT for name in TABLE_SPECS}

    verify_package_state(package, repository, actions)

    repository.rows["RATE_COI"].append(
        coerce_row(
            TABLE_SPECS["RATE_COI"],
            [10, 1, 20, 2, "0.500000"],
            source="fake database",
        )
    )
    with pytest.raises(RateDatabaseError, match="RATE_COI"):
        verify_package_state(package, repository, actions)
