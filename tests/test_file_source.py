"""Unit tests for the File Source backbone (Phase 1).

Covers the pure model + id-keyed store, the new DUCKDB SQL dialect, and the
DuckDB-over-member-files runner — including the "each file is its own table"
decision (2026-06-22). Self-contained: writes small temp files and queries them
via DuckDB, so it runs on the minipc with no live DB2/SQL Server.

Run via pytest, or directly: ``venv\\Scripts\\python.exe -m pytest tests/test_file_source.py -v``
"""
import os
import sys

import pytest

project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, project_root)

from suiteview.audit import file_source_store  # noqa: E402
from suiteview.audit.adhoc_source_intake import (  # noqa: E402
    delimited_text_spec, fixed_width_spec,
)
from suiteview.audit.dynamic_query import (  # noqa: E402
    DUCKDB, build_dynamic_sql, build_join_sql,
)
from suiteview.audit.file_source import (  # noqa: E402
    FileColumn, FileDataSource, FileMember, datasource_label,
)
from suiteview.audit import file_query_runner  # noqa: E402


# ── Model ────────────────────────────────────────────────────────────────

def test_model_round_trips_and_stamps_id():
    fds = FileDataSource(
        name="Claims",
        source_type="csv",
        parse_spec=delimited_text_spec(delimiter="|"),
        columns=[FileColumn("policy", "TEXT"), FileColumn("amount", "INTEGER")],
        members=[FileMember(path="/data/CLAIMS.txt", table_name="CLAIMS")],
    )
    restored = FileDataSource.from_dict(fds.to_dict())
    assert restored.name == "Claims"
    assert restored.source_type == "csv"
    assert restored.parse_spec["delimiter"] == "|"
    assert restored.column_names == ["policy", "amount"]
    assert restored.table_names == ["CLAIMS"]
    assert restored.id == fds.id


def test_legacy_dict_without_id_gets_one():
    obj = FileDataSource.from_dict({"name": "NoId", "source_type": "csv"})
    assert obj.id  # stamped on load


def test_member_table_name_defaults_to_file_stem():
    member = FileMember(path=r"C:\some\folder\RGACLAIMS.txt")
    assert member.resolved_table_name() == "RGACLAIMS"
    explicit = FileMember(path="/x/CLAIMS.txt", table_name="MyClaims")
    assert explicit.resolved_table_name() == "MyClaims"


def test_member_metadata_merges_parse_spec_and_path():
    fds = FileDataSource(
        name="C", source_type="csv",
        parse_spec=delimited_text_spec(delimiter=","),
        members=[FileMember(path="/data/a.csv")],
    )
    meta = fds.member_metadata(fds.members[0])
    assert meta["path"] == "/data/a.csv"
    assert meta["delimiter"] == ","
    # The shared parse_spec must not be mutated by per-member metadata.
    assert "path" not in fds.parse_spec


def test_datasource_label():
    assert datasource_label(FileDataSource(name="x", source_type="csv")) == "CSV"
    assert datasource_label(
        FileDataSource(name="x", source_type="fixed_width")) == "Fixed Width"
    assert datasource_label(FileDataSource(name="x", source_type="excel")) == "Excel"


# ── Store ────────────────────────────────────────────────────────────────

@pytest.fixture
def store_dir(tmp_path, monkeypatch):
    monkeypatch.setenv("SUITEVIEW_FILE_SOURCES_DIR", str(tmp_path))
    return tmp_path


def _sample_source(name="Claims"):
    return FileDataSource(
        name=name,
        source_type="csv",
        parse_spec=delimited_text_spec(),
        columns=[FileColumn("policy"), FileColumn("amount", "INTEGER")],
        members=[FileMember(path="/data/CLAIMS.txt", table_name="CLAIMS")],
    )


def test_store_save_and_load_by_id(store_dir):
    fds = _sample_source()
    file_source_store.save_file_source(fds)
    loaded = file_source_store.load_file_source_by_id(fds.id)
    assert loaded is not None
    assert loaded.name == "Claims"
    assert loaded.members[0].resolved_table_name() == "CLAIMS"


def test_store_load_by_name_returns_newest(store_dir):
    import datetime as _dt
    older = _sample_source("Dup")
    older.updated_at = _dt.datetime(2020, 1, 1)
    newer = _sample_source("Dup")
    newer.description = "the newer one"
    newer.updated_at = _dt.datetime(2026, 1, 1)
    file_source_store.save_file_source(older)
    file_source_store.save_file_source(newer)
    got = file_source_store.load_file_source("Dup")
    assert got is not None and got.description == "the newer one"
    assert len(file_source_store.list_file_sources()) == 2  # duplicate names legal


def test_store_delete_and_exists(store_dir):
    fds = _sample_source()
    file_source_store.save_file_source(fds)
    assert file_source_store.file_source_exists("Claims")
    file_source_store.delete_file_source_by_id(fds.id)
    assert not file_source_store.file_source_exists("Claims")


def test_store_rename_leaves_no_stale_file(store_dir):
    fds = _sample_source()
    file_source_store.save_file_source(fds)
    fds.name = "Renamed"
    file_source_store.save_file_source(fds)
    sources = file_source_store.list_file_sources()
    assert len(sources) == 1
    assert sources[0].name == "Renamed"


# ── DUCKDB dialect ─────────────────────────────────────────────────────────

def test_duckdb_dialect_quotes_and_limits_dynamic_sql():
    sql = build_dynamic_sql(
        '"CLAIMS"', "10",
        [{"column": "state", "mode": "combo", "value": "TX"}],
        select_columns=[{"column": "state", "aggregate": "display"}],
        dialect=DUCKDB,
    )
    assert '"state"' in sql          # double-quoted identifiers
    assert "LIMIT 10" in sql         # DuckDB row cap
    assert "TOP" not in sql
    assert "FETCH FIRST" not in sql
    assert "[state]" not in sql      # not bracket-quoted


def test_duckdb_dialect_join_sql_uses_limit_and_double_quotes():
    sql = build_join_sql(
        "CLAIMS", "5", [],
        join_infos=[],
        select_columns=[{"column": "amount", "aggregate": "display",
                         "field_key": "CLAIMS.amount"}],
        dialect=DUCKDB,
    )
    assert '"amount"' in sql
    assert "LIMIT 5" in sql
    assert "TOP" not in sql and "FETCH FIRST" not in sql


# ── Runner: DuckDB over member files ───────────────────────────────────────

def _write(path, text):
    path.write_text(text, encoding="utf-8")
    return str(path)


def test_each_file_is_its_own_table_and_unions_in_sql(tmp_path):
    claims = _write(tmp_path / "CLAIMS.txt",
                    "policy,state,amount\nP1,TX,100\nP2,CA,200\n")
    rga = _write(tmp_path / "RGACLAIMS.txt",
                 "policy,state,amount\nR1,TX,500\n")
    fds = FileDataSource(
        name="Claims", source_type="csv",
        parse_spec=delimited_text_spec(delimiter=","),
        columns=[FileColumn("policy"), FileColumn("state"),
                 FileColumn("amount", "INTEGER")],
        members=[FileMember(path=claims, table_name="CLAIMS"),
                 FileMember(path=rga, table_name="RGACLAIMS")],
    )

    # Each file is queryable on its own.
    one = file_query_runner.run_sql(fds, 'SELECT * FROM "CLAIMS"').dataframe
    assert len(one) == 2

    # And combined only when the SQL UNIONs them.
    both = file_query_runner.run_sql(
        fds,
        'SELECT policy FROM "CLAIMS" UNION ALL SELECT policy FROM "RGACLAIMS"',
    ).dataframe
    assert sorted(both["policy"].tolist()) == ["P1", "P2", "R1"]


def test_run_query_returns_odbc_shaped_result(tmp_path):
    claims = _write(tmp_path / "CLAIMS.txt",
                    "policy,state,amount\nP1,TX,100\nP2,CA,200\n")
    fds = FileDataSource(
        name="Claims", source_type="csv",
        parse_spec=delimited_text_spec(),
        members=[FileMember(path=claims, table_name="CLAIMS")],
    )
    columns, rows, types = file_query_runner.run_query(
        fds, 'SELECT policy, amount FROM "CLAIMS" WHERE state = \'TX\'')
    assert columns == ["policy", "amount"]
    assert rows == [("P1", 100)]
    assert types["amount"] == "INTEGER"
    assert types["policy"] == "TEXT"


def test_fixed_width_member_parses_and_queries(tmp_path):
    path = _write(tmp_path / "FW.txt", "PROD1TX0100\nPROD2CA0200\n")
    fds = FileDataSource(
        name="FW", source_type="fixed_width",
        parse_spec=fixed_width_spec([
            {"name": "code", "start": 1, "width": 5},
            {"name": "state", "start": 6, "width": 2},
            {"name": "amt", "start": 8, "width": 4},
        ]),
        members=[FileMember(path=path, table_name="FW")],
    )
    df = file_query_runner.run_sql(fds, 'SELECT * FROM "FW"').dataframe
    assert list(df.columns) == ["code", "state", "amt"]
    assert df["code"].tolist() == ["PROD1", "PROD2"]
    assert df["state"].tolist() == ["TX", "CA"]


def test_headerless_delimited_uses_declared_column_names(tmp_path):
    path = _write(tmp_path / "NH.txt", "X1,99\nX2,88\n")
    fds = FileDataSource(
        name="NH", source_type="csv",
        parse_spec=delimited_text_spec(
            delimiter=",", has_header=False, column_names=["key", "val"]),
        members=[FileMember(path=path, table_name="NH")],
    )
    df = file_query_runner.run_sql(fds, 'SELECT key, val FROM "NH"').dataframe
    assert df["key"].tolist() == ["X1", "X2"]
    assert df["val"].tolist() == [99, 88]


def test_limit_caps_rows(tmp_path):
    path = _write(tmp_path / "BIG.txt",
                  "n\n" + "\n".join(str(i) for i in range(50)) + "\n")
    fds = FileDataSource(
        name="Big", source_type="csv",
        parse_spec=delimited_text_spec(),
        members=[FileMember(path=path, table_name="BIG")],
    )
    df = file_query_runner.run_sql(fds, 'SELECT * FROM "BIG"', limit=5).dataframe
    assert len(df) == 5


def test_run_sql_without_members_raises(tmp_path):
    from suiteview.audit.dataforge.forge_engine import ForgeEngineError

    fds = FileDataSource(name="Empty", source_type="csv",
                         parse_spec=delimited_text_spec())
    with pytest.raises(ForgeEngineError):
        file_query_runner.run_sql(fds, 'SELECT 1')


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
