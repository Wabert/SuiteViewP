"""Source-keyed WL schema and transaction safety without a live database."""

from collections import OrderedDict
from decimal import Decimal
import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from suiteview.core.build_env import ReadOnlyDataError
from suiteview.core import access_control
from suiteview.ratemanager.database_loader import (
    PackageValidationError, RateDatabaseError, StaleAnalysisError, UnsafeOperationError,
)
from suiteview.ratemanager.whole_life import service
from suiteview.ratemanager.whole_life.schema import Column, WholeLifeTable
from suiteview.ratemanager.whole_life.service import (
    TableComparison, WholeLifeAnalysis, WholeLifePackage, WholeLifeRepository,
)


DEFINITION = WholeLifeTable(
    "TEST_RATE",
    (Column("UserCode", "varchar(2)"), Column("Duration", "smallint"),
     Column("Rate", "decimal(18,6)")),
    ("UserCode", "Duration"), True,
)


def package(rate="12.345678"):
    data = DEFINITION.data([
        {"UserCode": "06", "Duration": 1, "Rate": rate},
    ])
    return WholeLifePackage(OrderedDict(TEST_RATE=data))


def test_precision_and_source_key_are_preserved():
    row = package().tables["TEST_RATE"].rows[0]
    assert row == ("06", 1, Decimal("12.345678"))
    assert DEFINITION.spec.key(row) == ("06", 1)
    assert "decimal(18,6)" in DEFINITION.ddl()
    assert "PRIMARY KEY ([UserCode], [Duration])" in DEFINITION.ddl()


@pytest.mark.parametrize("rate", ["NaN", "Infinity", "0.1234567", "1000000000000"])
def test_values_cannot_be_silently_rounded_or_coerced(rate):
    with pytest.raises(PackageValidationError):
        package(rate)


def test_exact_duplicates_deduplicate_but_conflicts_fail():
    row = {"UserCode": "06", "Duration": 1, "Rate": "1"}
    assert len(DEFINITION.data([row, row]).rows) == 1
    with pytest.raises(PackageValidationError, match="conflicting"):
        DEFINITION.data([row, {**row, "Rate": "2"}])


@pytest.mark.parametrize("row", [
    {"UserCode": "006", "Duration": 1, "Rate": "1"},
    {"UserCode": "06", "Duration": 40000, "Rate": "1"},
    {"UserCode": "06", "Duration": 1, "Rate": None},
    {"UserCode": "06", "Duration": 1, "Rate": "1", "Extra": "ignored"},
])
def test_invalid_schema_values_fail(row):
    with pytest.raises(PackageValidationError):
        DEFINITION.data([row])


def test_empty_table_fails():
    with pytest.raises(PackageValidationError, match="no rate rows"):
        DEFINITION.data([])


def analysis_for(source, changed=0):
    return WholeLifeAnalysis(
        source, (TableComparison("TEST_RATE", 1, 1 - changed, 0, changed),),
        source.digest, "UL_Rates",
    )


def test_read_only_blocks_ddl_and_writes_before_connect(monkeypatch):
    monkeypatch.setattr(access_control, "get_access", lambda **_: SimpleNamespace(can_update_database=False))
    with patch("suiteview.ratemanager.database_loader.connect_dsn") as connect:
        with WholeLifeRepository() as repository:
            with pytest.raises(ReadOnlyDataError):
                repository.create_tables()
            with pytest.raises(ReadOnlyDataError):
                repository.apply(analysis_for(package()), set())
        connect.assert_not_called()


@pytest.mark.parametrize("apply,was_nullable", [(False, False), (True, False), (True, True)])
def test_explicit_cvf_zero_schema_setup_changes_only_nullability(
    monkeypatch, capsys, apply, was_nullable,
):
    from tools.rates import configure_wl_cv_zero_null as tool

    monkeypatch.setattr(tool.sys, "argv", ["configure", json.dumps({"apply": apply})])
    repository = MagicMock()
    repository.__enter__.return_value = repository
    repository.test_connection.return_value = "UL_Rates"
    cursor = repository.connect.return_value.cursor.return_value
    cursor.columns.return_value = [
        SimpleNamespace(column_name="DURATION_ZERO_VALUE", nullable=was_nullable),
    ]
    monkeypatch.setattr(tool, "WholeLifeRepository", lambda dsn: repository)
    tool.main()
    changed = apply and not was_nullable
    assert json.loads(capsys.readouterr().out)["schema_changed"] == changed
    assert repository.commit.call_count == int(changed)
    first_definition = repository._validate_table.call_args_list[0].args[0]
    assert next(c for c in first_definition.columns if c.name == "DURATION_ZERO_VALUE").nullable == was_nullable
    if changed:
        assert cursor.execute.call_args.args == (
            "ALTER TABLE [dbo].[WL_RATE_CV] "
            "ALTER COLUMN [DURATION_ZERO_VALUE] decimal(7,2) NULL",
        )
    else:
        cursor.execute.assert_not_called()
    repository.rollback.assert_called_once()


def test_cvf_zero_schema_setup_respects_read_only_before_connect(monkeypatch):
    from tools.rates import configure_wl_cv_zero_null as tool

    monkeypatch.setattr(access_control, "get_access", lambda **_: SimpleNamespace(can_update_database=False))
    monkeypatch.setattr(tool.sys, "argv", ["configure", '{"apply": true}'])
    with patch.object(tool, "WholeLifeRepository") as connect:
        with pytest.raises(ReadOnlyDataError):
            tool.main()
        connect.assert_not_called()


def test_changed_rows_need_explicit_table_approval():
    repository = WholeLifeRepository()
    with pytest.raises(UnsafeOperationError, match="Approve changed rows"):
        repository.apply(analysis_for(package(), changed=1), set())


def test_source_mutation_after_analysis_is_rejected():
    source = package()
    analysis = analysis_for(source)
    source.tables["TEST_RATE"] = package("9").tables["TEST_RATE"]
    with pytest.raises(StaleAnalysisError, match="Source package changed"):
        WholeLifeRepository().apply(analysis, set())


def test_unrelated_replacement_approval_is_rejected():
    with pytest.raises(UnsafeOperationError, match="unrelated"):
        WholeLifeRepository().apply(analysis_for(package()), {"WL_RATE_DIV"})


def test_browse_identifiers_are_allowlisted_before_connection():
    repository = WholeLifeRepository()
    with pytest.raises(PackageValidationError):
        repository.browse("WL_RATE_DIV; DELETE anything", {}, 10)
    with pytest.raises(PackageValidationError):
        repository.browse("WL_RATE_DIV", {"x] OR 1=1": "x"}, 10)
    with pytest.raises(PackageValidationError):
        repository.browse("WL_RATE_DIV", {}, 10001)


def test_browse_values_are_bound_not_interpolated():
    repository = WholeLifeRepository()
    repository._connection = MagicMock()
    cursor = repository._connection.cursor.return_value
    cursor.fetchall.return_value = []
    value = "' OR 1=1 --"
    repository.browse("WL_RATE_DIV", {"HEADER_ID": value}, 20)
    sql, params = cursor.execute.call_args.args
    assert value not in sql
    assert "[HEADER_ID] = ?" in sql
    assert params == (20, value)


def test_database_change_after_review_rolls_back_before_write(tmp_path):
    source = package()
    analysis = analysis_for(source)
    repository = WholeLifeRepository(receipt_root=tmp_path)
    repository._connection = MagicMock()
    repository.test_connection = MagicMock(return_value="UL_Rates")
    repository._stage = MagicMock(return_value={"TEST_RATE": "#wl_stage_1"})
    repository._compare = MagicMock(return_value=(
        TableComparison("TEST_RATE", 1, 0, 1, 0),
    ))
    with pytest.raises(StaleAnalysisError, match="Database rows changed"):
        repository.apply(analysis, set())
    repository._connection.rollback.assert_called_once()
    repository._connection.commit.assert_not_called()
    assert not list(tmp_path.iterdir())


def test_success_writes_receipt_and_verifies_before_and_after_commit(tmp_path, monkeypatch):
    provenance = {
        "path": "cash.txt",
        "cvf_inference": {
            "enabled": True, "rule": "negative-header-initial-decline-v1",
            "adjusted_rows": 1,
            "adjustments": [{"DURATION": 1, "printed_rate": "22.27", "loaded_rate": "0.00"}],
        },
    }
    source = WholeLifePackage(package().tables, (provenance,))
    analysis = analysis_for(source)
    repository = WholeLifeRepository(receipt_root=tmp_path)
    repository._connection = MagicMock()
    repository.test_connection = MagicMock(return_value="UL_Rates")
    repository._stage = MagicMock(return_value={"TEST_RATE": "#wl_stage_1"})
    matched = (TableComparison("TEST_RATE", 1, 0, 1, 0),)
    repository._compare = MagicMock(side_effect=[analysis.tables, matched, matched])
    monkeypatch.setitem(service.TABLES, "TEST_RATE", DEFINITION)
    result = repository.apply(analysis, set())
    assert result["inserted"] == {"TEST_RATE": 1}
    assert result["updated"] == {"TEST_RATE": 0}
    repository._connection.commit.assert_called_once()
    assert repository._compare.call_count == 3
    assert json.loads(Path(result["receipt"]).read_text())["status"] == "committed and verified"
    assert json.loads(Path(result["receipt"]).read_text())["sources"] == [provenance]


def test_verification_failure_rolls_back(tmp_path, monkeypatch):
    source = package()
    analysis = analysis_for(source)
    repository = WholeLifeRepository(receipt_root=tmp_path)
    repository._connection = MagicMock()
    repository.test_connection = MagicMock(return_value="UL_Rates")
    repository._stage = MagicMock(return_value={"TEST_RATE": "#wl_stage_1"})
    repository._compare = MagicMock(return_value=analysis.tables)
    monkeypatch.setitem(service.TABLES, "TEST_RATE", DEFINITION)
    with pytest.raises(RateDatabaseError, match="rolling back"):
        repository.apply(analysis, set())
    repository._connection.commit.assert_not_called()
    repository._connection.rollback.assert_called_once()


def test_backup_failure_prevents_all_rate_writes(tmp_path, monkeypatch):
    source = package()
    analysis = analysis_for(source)
    repository = WholeLifeRepository(receipt_root=tmp_path)
    repository._connection = MagicMock()
    repository.test_connection = MagicMock(return_value="UL_Rates")
    repository._stage = MagicMock(return_value={"TEST_RATE": "#wl_stage_1"})
    repository._compare = MagicMock(return_value=analysis.tables)
    monkeypatch.setitem(service.TABLES, "TEST_RATE", DEFINITION)
    with patch.object(service, "write_json", side_effect=OSError("disk full")):
        with pytest.raises(OSError, match="disk full"):
            repository.apply(analysis, set())
    statements = [
        call.args[0]
        for call in repository._connection.cursor.return_value.execute.call_args_list
    ]
    assert not any(sql.startswith(("UPDATE", "INSERT")) for sql in statements)
    repository._connection.commit.assert_not_called()
    repository._connection.rollback.assert_called_once()


def test_schema_mismatch_rolls_back_table_creation(monkeypatch):
    repository = WholeLifeRepository()
    repository._connection = MagicMock()
    repository._connection.cursor.return_value.execute.return_value.fetchone.return_value = (None,)
    repository._validate_table = MagicMock(
        side_effect=RateDatabaseError("unexpected schema")
    )
    monkeypatch.setattr(service, "TABLES", OrderedDict(TEST_RATE=DEFINITION))
    with pytest.raises(RateDatabaseError, match="unexpected schema"):
        repository.create_tables()
    repository._connection.commit.assert_not_called()
    repository._connection.rollback.assert_called_once()


def test_database_before_images_distinguish_null_empty_and_whitespace():
    fingerprints = {
        service._before_digest("TEST_RATE", ((value,),))
        for value in (None, "", " ", "X", "X ")
    }
    assert len(fingerprints) == 5


def test_backup_preserves_null_empty_and_fixed_width_values(tmp_path, monkeypatch):
    source = package()
    before = (None, "", "X  ")
    comparison = TableComparison("TEST_RATE", 1, 0, 0, 1, "before", (before,))
    analysis = WholeLifeAnalysis(source, (comparison,), source.digest, "UL_Rates")
    repository = WholeLifeRepository(receipt_root=tmp_path)
    repository._connection = MagicMock()
    repository.test_connection = MagicMock(return_value="UL_Rates")
    repository._stage = MagicMock(return_value={"TEST_RATE": "#wl_stage_1"})
    matched = (TableComparison("TEST_RATE", 1, 0, 1, 0),)
    repository._compare = MagicMock(side_effect=[analysis.tables, matched, matched])
    monkeypatch.setitem(service.TABLES, "TEST_RATE", DEFINITION)
    result = repository.apply(analysis, {"TEST_RATE"})
    receipt = json.loads(Path(result["receipt"]).read_text())
    assert receipt["before_rows"]["TEST_RATE"] == [
        {"UserCode": None, "Duration": "", "Rate": "X  "}
    ]


def test_staged_dates_use_iso_strings_for_legacy_sql_server_driver():
    definition = service.TABLES["WL_RATE_PUI"]
    data = definition.data([{
        "USER_CODE": "06", "PLANCODE": "TEST", "SEX": "1", "RATECLASS": "N",
        "ATTAINED_AGE": 40, "TABLE_RATING": "", "RATE": "123.456789",
        "AUDIT_NUMBER": "TEST", "CHANGED_DATE": "2026-01-01",
    }])
    repository = WholeLifeRepository()
    repository._connection = MagicMock()
    repository._validate_table = MagicMock()
    repository._stage(WholeLifePackage(OrderedDict(WL_RATE_PUI=data)))
    cursor = repository._connection.cursor.return_value
    sql, rows = cursor.executemany.call_args.args
    assert "CONVERT(date, ?, 23)" in sql
    assert rows[0][-1] == "2026-01-01"
    assert cursor.setinputsizes.call_args_list[0].args[0][-1] == (
        service.pyodbc.SQL_VARCHAR, 10, 0
    )


def test_cvf_range_contraction_cannot_leave_stale_rates():
    definition = service.TABLES["WL_RATE_CV"]
    data = definition.data([{
        "USER_CODE": "06", "RATE_KEY": "1ABC00", "CLASS": "1", "BASE_SERIES": "ABC",
        "SUBSERIES": "00", "USER_DEFINED": "", "ISSUE_AGE": 40,
        "PREMIUM_YEARS": 0, "BENEFIT_YEARS": 0,
        "FIRST_DURATION": 0, "LAST_DURATION": 0, "DURATION_ZERO_VALUE": "0",
        "DURATION": 0, "RATE": "0",
    }])
    repository = WholeLifeRepository()
    repository._connection = MagicMock()
    repository._connection.cursor.return_value.execute.return_value.fetchone.return_value = ("1ABC00", 40)
    with pytest.raises(UnsafeOperationError, match="outside the new duration range"):
        repository._validate_cvf_ranges(
            WholeLifePackage(OrderedDict(WL_RATE_CV=data)), {"WL_RATE_CV": "#wl_stage_1"}
        )
