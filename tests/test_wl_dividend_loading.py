"""Dividend service integration with synthetic print files and mocked SQL calls."""

from dataclasses import replace
from decimal import Decimal
from unittest.mock import MagicMock, patch

import pytest

from suiteview.ratemanager.database_loader import (
    PackageValidationError,
    UnsafeOperationError,
)
from suiteview.ratemanager.whole_life import service
from suiteview.ratemanager.whole_life.dividend import DividendValidationError
from suiteview.ratemanager.whole_life.schema import TABLES
from suiteview.ratemanager.whole_life.service import (
    TableComparison,
    WholeLifeAnalysis,
    WholeLifeRepository,
    parse_sources,
)
from tests.test_wl_dividend import PAGE, _record, _write_map


STAGES = {"WL_DIV_HEADER": "#div_header", "WL_RATE_DIV": "#div_rates"}


def _source(tmp_path, *records):
    path = tmp_path / "synthetic-dividend-import.txt"
    path.write_text(PAGE + "".join(records or [_record()]), encoding="utf-8")
    return path


def _package(tmp_path, *records):
    return parse_sources("Dividend", [str(_source(tmp_path, *records))])


def _records(package, table):
    data = package.tables[table]
    return [dict(zip(data.spec.columns, row)) for row in data.rows]


def _replace_records(package, table, records):
    tables = package.tables.copy()
    tables[table] = TABLES[table].data(records)
    return replace(package, tables=tables)


def _repository(tmp_path, *, outside=None, missing_parent=None):
    repository = WholeLifeRepository(receipt_root=tmp_path / "receipts")
    repository._connection = MagicMock()
    cursor = repository._connection.cursor.return_value
    cursor.execute.return_value = cursor

    def execute(sql, *args):
        cursor.fetchone.return_value = (
            outside if "WHERE d.[DURATION] <" in sql
            else missing_parent if "SELECT TOP (1) other.[HEADER_ID]" in sql
            else None
        )
        return cursor

    cursor.execute.side_effect = execute
    return repository, cursor


def _statements(cursor):
    return [call.args[0] for call in cursor.execute.call_args_list]


@pytest.fixture(autouse=True)
def prohibit_live_database_and_enable_full_build(monkeypatch):
    monkeypatch.delenv("SUITEVIEW_LIGHT", raising=False)
    with patch(
        "suiteview.ratemanager.database_loader.pyodbc.connect",
        side_effect=AssertionError("Dividend integration tests must never access a live database"),
    ):
        yield


def test_parser_integration_preserves_dates_keys_decimals_and_provenance(tmp_path):
    path = _source(tmp_path, _record(user="ABC"))
    package = parse_sources("Dividend", [str(path)])
    header = _records(package, "WL_DIV_HEADER")[0]
    rate = _records(package, "WL_RATE_DIV")[0]
    assert header["MAINT_DT"] is None
    assert header["ISSUE_DATE"] == "01/01/2000"
    assert header["EFFECTIVE_DATE"] == "04/01/2024"
    assert header["END_DATE"] == "00/00/0000"
    assert header["HEADER_ID"] == "00_D_A_TST_N1_1_ABC    _020_20000101_20240401"
    assert rate["HEADER_ID"] == header["HEADER_ID"]
    assert rate["CASH_RATE"] == Decimal("1.25")
    assert package.sources[0]["path"] == str(path.resolve())
    assert len(package.sources[0]["sha256"]) == 64
    assert package.sources[0]["size"] == path.stat().st_size


def test_parser_integration_preserves_zero_effective_dates_not_report_run_date(tmp_path):
    package = _package(tmp_path, _record(issue="00/00/1900", effective="00/00/1900"))
    header = _records(package, "WL_DIV_HEADER")[0]
    assert header["ISSUE_DATE"] == header["EFFECTIVE_DATE"] == "00/00/1900"
    assert header["HEADER_ID"].endswith("_19000000_19000000")


def test_mapping_parser_interface_and_blank_zero_distinction(tmp_path):
    path = _write_map(tmp_path, [
        ("PLAN0001", "M", "N", "A1", "(blank)", "ATSTA1"),
        ("PLAN0002", "M", "N", "A1", "00", "ATSTA1"),
    ])
    package = parse_sources("Dividend map", [str(path)])
    assert list(package.tables) == ["WL_DIV_PLANKEY_MAP"]
    assert [row["USER_KEY"] for row in _records(package, "WL_DIV_PLANKEY_MAP")] == [None, "00"]


def test_identical_files_deduplicate_after_independent_parsing(tmp_path):
    path = _source(tmp_path)
    package = parse_sources("Dividend", [str(path), str(path)])
    assert package.row_counts == {"WL_DIV_HEADER": 1, "WL_RATE_DIV": 2}
    assert len(package.sources) == 2


def test_maintenance_date_is_not_part_of_semantic_comparison():
    expression = service._different(TABLES["WL_DIV_HEADER"])
    assert "MAINT_DT" not in expression
    assert "d.[EFFECTIVE_DATE]" in expression
    assert "d.[PUA_KEY_USER_DEFINED]" in expression
    assert "d.[HEADER_ID]" not in expression


def test_stage_binds_physical_date_text_and_maintenance_null(tmp_path):
    package = _package(tmp_path)
    repository, cursor = _repository(tmp_path)
    repository._validate_table = MagicMock()
    repository._stage(package)
    header_insert = next(
        call for call in cursor.executemany.call_args_list
        if "[MAINT_DT]" in call.args[0]
    )
    bound = dict(zip(package.tables["WL_DIV_HEADER"].spec.columns, header_insert.args[1][0]))
    assert bound["MAINT_DT"] is None
    assert bound["ISSUE_DATE"] == "01/01/2000"
    assert bound["EFFECTIVE_DATE"] == "04/01/2024"
    assert bound["END_DATE"] == "00/00/0000"
    assert isinstance(bound["PUA_INTEREST"], float)
    repository._connection.commit.assert_called_once()


def test_complete_zero_schedules_validate_without_defaults(tmp_path):
    package = _package(tmp_path, _record(values=["0.00", "0.00"]))
    repository, cursor = _repository(tmp_path)
    repository._validate_dividend_schedules(package, STAGES)
    assert len(_records(package, "WL_RATE_DIV")) == 2
    assert all(row["CASH_RATE"] == Decimal("0.00") for row in _records(package, "WL_RATE_DIV"))
    assert len(_statements(cursor)) == 2
    cursor.close.assert_called_once()


@pytest.mark.parametrize("missing", ["WL_DIV_HEADER", "WL_RATE_DIV"])
def test_dependency_tables_cannot_be_loaded_separately(tmp_path, missing):
    package = _package(tmp_path)
    tables = package.tables.copy()
    del tables[missing]
    repository, cursor = _repository(tmp_path)
    with pytest.raises(PackageValidationError, match="must load together"):
        repository._validate_dividend_schedules(replace(package, tables=tables), STAGES)
    cursor.execute.assert_not_called()


@pytest.mark.parametrize("mutation", ["missing-duration", "extra-duration", "wrong-type", "orphan"])
def test_missing_extra_or_mismatched_schedule_rows_fail_before_sql(tmp_path, mutation):
    package = _package(tmp_path)
    rows = _records(package, "WL_RATE_DIV")
    if mutation == "missing-duration":
        rows.pop()
    elif mutation == "extra-duration":
        rows.append({**rows[-1], "DURATION": 3})
    elif mutation == "wrong-type":
        rows[0]["RECORD_TYPE"] = "R"
    else:
        rows[0]["HEADER_ID"] = "ORPHAN"
    package = _replace_records(package, "WL_RATE_DIV", rows)
    repository, cursor = _repository(tmp_path)
    with pytest.raises(PackageValidationError):
        repository._validate_dividend_schedules(package, STAGES)
    cursor.execute.assert_not_called()


def test_every_header_requires_its_own_complete_schedule(tmp_path):
    package = _package(tmp_path, _record(age=20), _record(age=21))
    rows = _records(package, "WL_RATE_DIV")[:2]
    package = _replace_records(package, "WL_RATE_DIV", rows)
    repository, cursor = _repository(tmp_path)
    with pytest.raises(PackageValidationError, match="incomplete"):
        repository._validate_dividend_schedules(package, STAGES)
    cursor.execute.assert_not_called()


def test_contraction_checks_all_existing_rows_not_only_incoming_duration_keys(tmp_path):
    package = _package(tmp_path)
    header_id = _records(package, "WL_DIV_HEADER")[0]["HEADER_ID"]
    repository, cursor = _repository(tmp_path, outside=(header_id,))
    with pytest.raises(UnsafeOperationError, match="Range contraction"):
        repository._validate_dividend_schedules(package, STAGES)
    query = _statements(cursor)[0]
    assert "JOIN #div_header s ON d.[HEADER_ID] = s.[HEADER_ID]" in query
    assert "d.[DURATION] < s.[FIRST_DURATION]" in query
    assert "d.[DURATION] > s.[LAST_DURATION]" in query
    assert "#div_rates" not in query
    assert len(_statements(cursor)) == 1
    cursor.close.assert_called_once()


def test_expansion_with_complete_incoming_range_is_allowed(tmp_path):
    package = _package(tmp_path, _record(last=12))
    repository, _ = _repository(tmp_path)
    repository._validate_dividend_schedules(package, STAGES)
    assert package.row_counts["WL_RATE_DIV"] == 12


def test_missing_affected_shared_pua_parent_blocks_the_load(tmp_path):
    package = _package(
        tmp_path,
        _record(age=2, par="2", pua_key="ZREFN1"),
        _record(plan="Z-REF-N1", age=0, last=4, user="TST"),
    )
    repository, cursor = _repository(tmp_path, missing_parent=("UNLOADED_SHARED_PARENT",))
    with pytest.raises(UnsafeOperationError, match="complete affected parent"):
        repository._validate_dividend_schedules(package, STAGES)
    query = _statements(cursor)[1]
    assert "other.[USER_CODE] = h.[USER_CODE]" in query
    assert "other.[PUA_KEY] = h.[PUA_KEY]" in query
    assert "COALESCE(other.[PUA_KEY_USER_DEFINED], '')" in query
    assert "other.[PUA_PARTICIPATING] = '2'" in query
    for column in ("PUA_DIV_CASH", "PUA_DIV_PUA", "PUA_DIV_OYT"):
        assert f"d.[{column}]" in query and f"s.[{column}]" in query
    assert "NOT EXISTS (SELECT 1 FROM #div_header included" in query
    cursor.close.assert_called_once()


def test_complete_shared_pua_parent_group_passes(tmp_path):
    package = _package(
        tmp_path,
        _record(age=1, par="2", pua_key="ZREFN1"),
        _record(age=2, par="2", pua_key="ZREFN1"),
        _record(plan="Z-REF-N1", age=0, last=4, user="TST"),
    )
    repository, _ = _repository(tmp_path)
    repository._validate_dividend_schedules(package, STAGES)
    assert package.row_counts == {"WL_DIV_HEADER": 2, "WL_RATE_DIV": 4}


def test_multi_user_dividends_keep_company_specific_factors_in_import_package(tmp_path):
    source_records = []
    for user_code, value in (("01", "11.00"), ("26", "26.00")):
        source_records.extend((
            _record(age=2, par="2", pua_key="ZREFN1", user_code=user_code),
            _record(
                plan="Z-REF-N1", age=0, last=4,
                user_code=user_code, values=[value] * 4,
            ),
        ))
    package = _package(tmp_path, *source_records)
    headers = {header["HEADER_ID"]: header for header in _records(package, "WL_DIV_HEADER")}
    assert {header["USER_CODE"] for header in headers.values()} == {"01", "26"}
    for row in _records(package, "WL_RATE_DIV"):
        user_code = headers[row["HEADER_ID"]]["USER_CODE"]
        expected = Decimal("11.00") if user_code == "01" else Decimal("26.00")
        assert row["PUA_DIV_CASH"] == expected
    repository, _ = _repository(tmp_path)
    repository._validate_dividend_schedules(package, STAGES)


def test_missing_user_specific_reference_is_rejected_before_loading(tmp_path):
    with pytest.raises(DividendValidationError, match="missing or ambiguous PUA reference"):
        _package(
            tmp_path,
            _record(age=2, par="2", pua_key="ZREFN1", user_code="01"),
            _record(plan="Z-REF-N1", age=0, last=4, user_code="00"),
        )


def test_mapping_only_does_not_require_dividend_dependency_tables(tmp_path):
    path = _write_map(tmp_path, [("PLAN0001", "M", "N", "A1", None, "ATSTA1")])
    package = parse_sources("Dividend map", [str(path)])
    repository, cursor = _repository(tmp_path)
    repository._validate_dividend_schedules(package, {})
    cursor.execute.assert_not_called()


def _analysis(package, action):
    comparisons = tuple(
        TableComparison(
            name, len(data.rows),
            len(data.rows) if action == "insert" else 0,
            len(data.rows) if action == "unchanged" else 0,
            len(data.rows) if action == "update" else 0,
        )
        for name, data in package.tables.items()
    )
    return WholeLifeAnalysis(package, comparisons, package.digest, "UL_Rates")


@pytest.mark.parametrize("approved", [set(), {"WL_DIV_HEADER"}, {"WL_RATE_DIV"}])
def test_each_changed_dependency_table_requires_explicit_approval(tmp_path, approved):
    analysis = _analysis(_package(tmp_path), "update")
    repository, cursor = _repository(tmp_path)
    with pytest.raises(UnsafeOperationError, match="Approve changed rows"):
        repository.apply(analysis, approved)
    cursor.execute.assert_not_called()


@pytest.mark.parametrize("action", ["insert", "update", "unchanged"])
def test_apply_stamps_only_written_headers_and_never_deletes_missing_rows(tmp_path, action):
    package = _package(tmp_path)
    analysis = _analysis(package, action)
    matched = _analysis(package, "unchanged").tables
    repository, cursor = _repository(tmp_path)
    repository.test_connection = MagicMock(return_value="UL_Rates")
    repository._stage = MagicMock(return_value=STAGES)
    repository._compare = MagicMock(side_effect=[analysis.tables, matched, matched])
    approvals = set(package.tables) if action == "update" else set()
    with patch.object(service, "write_json") as write_receipt:
        repository.apply(analysis, approvals)
    queries = _statements(cursor)
    assert not any(sql.startswith("DELETE") for sql in queries)
    mutations = [sql for sql in queries if sql.startswith(("UPDATE", "INSERT"))]
    if action == "unchanged":
        assert mutations == []
    else:
        assert len(mutations) == 2
        assert "[dbo].[WL_DIV_HEADER]" in mutations[0]
        assert "[dbo].[WL_RATE_DIV]" in mutations[1]
        assert "CONVERT(varchar(10), GETDATE(), 101)" in mutations[0]
        assert "GETDATE" not in mutations[1]
        if action == "insert":
            assert all("WHERE NOT EXISTS" in sql for sql in mutations)
        else:
            assert all("WHERE EXISTS (SELECT" in sql for sql in mutations)
    repository._connection.commit.assert_called_once()
    repository._connection.rollback.assert_called_once()
    assert write_receipt.call_count == 2
    assert write_receipt.call_args.args[1]["status"] == "committed and verified"


def test_apply_rechecks_shared_parent_completeness_inside_transaction(tmp_path):
    package = _package(tmp_path)
    analysis = _analysis(package, "update")
    repository, cursor = _repository(tmp_path, missing_parent=("NEWLY_AFFECTED_PARENT",))
    repository.test_connection = MagicMock(return_value="UL_Rates")
    repository._stage = MagicMock(return_value=STAGES)
    repository._compare = MagicMock()
    with pytest.raises(UnsafeOperationError, match="complete affected parent"):
        repository.apply(analysis, set(package.tables))
    repository._compare.assert_not_called()
    repository._connection.commit.assert_not_called()
    repository._connection.rollback.assert_called_once()
    assert not any(sql.startswith(("UPDATE", "INSERT", "DELETE")) for sql in _statements(cursor))
