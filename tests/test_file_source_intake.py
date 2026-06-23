"""Unit tests for File Source intake + drag-drop validation (Phase 2 backbone).

Self-contained (writes temp files, no DB2), runs on the minipc.
"""
import os
import sys

import pytest

project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, project_root)

from suiteview.audit.adhoc_source_intake import (  # noqa: E402
    fixed_width_spec, query_object_from_file,
)
from suiteview.audit.file_source_intake import (  # noqa: E402
    FileValidationError, add_member_file, apply_column_names,
    infer_file_source_from_file, migrate_adhoc_to_file_source,
    parse_column_names, unique_table_name, validate_member_file,
)


def _write(path, text):
    path.write_text(text, encoding="utf-8")
    return str(path)


# ── Inference ──────────────────────────────────────────────────────────────

def test_infer_csv_builds_source_with_schema_and_member(tmp_path):
    path = _write(tmp_path / "CLAIMS.csv",
                  "policy,state,amount\nP1,TX,100\nP2,CA,200\n")
    fds = infer_file_source_from_file(path)
    assert fds.source_type == "csv"
    assert fds.column_names == ["policy", "state", "amount"]
    assert fds.parse_spec.get("format") == "delimited"
    assert "path" not in fds.parse_spec  # parse spec is reusable, not per-file
    assert fds.table_names == ["CLAIMS"]


def test_infer_fixed_width_source(tmp_path):
    path = _write(tmp_path / "FW.txt", "PROD1TX0100\nPROD2CA0200\n")
    spec = fixed_width_spec([
        {"name": "code", "start": 1, "width": 5},
        {"name": "state", "start": 6, "width": 2},
        {"name": "amt", "start": 8, "width": 4},
    ])
    fds = infer_file_source_from_file(path, format_spec=spec)
    assert fds.source_type == "fixed_width"
    assert fds.column_names == ["code", "state", "amt"]


# ── Validation ─────────────────────────────────────────────────────────────

def test_validate_matching_file_has_no_missing_columns(tmp_path):
    a = _write(tmp_path / "CLAIMS.csv", "policy,state,amount\nP1,TX,100\n")
    fds = infer_file_source_from_file(a)
    b = _write(tmp_path / "RGACLAIMS.csv", "policy,state,amount\nR1,TX,500\n")
    assert validate_member_file(fds, b) == []


def test_validate_reports_missing_columns(tmp_path):
    a = _write(tmp_path / "CLAIMS.csv", "policy,state,amount\nP1,TX,100\n")
    fds = infer_file_source_from_file(a)
    wrong = _write(tmp_path / "OTHER.csv", "foo,bar\n1,2\n")
    missing = validate_member_file(fds, wrong)
    assert set(missing) == {"policy", "state", "amount"}


# ── Adding members ─────────────────────────────────────────────────────────

def test_add_member_file_appends_matching_file(tmp_path):
    a = _write(tmp_path / "CLAIMS.csv", "policy,state,amount\nP1,TX,100\n")
    fds = infer_file_source_from_file(a)
    b = _write(tmp_path / "RGACLAIMS.csv", "policy,state,amount\nR1,TX,500\n")
    member = add_member_file(fds, b)
    assert member.resolved_table_name() == "RGACLAIMS"
    assert fds.table_names == ["CLAIMS", "RGACLAIMS"]


def test_add_member_rejects_mismatched_file(tmp_path):
    a = _write(tmp_path / "CLAIMS.csv", "policy,state,amount\nP1,TX,100\n")
    fds = infer_file_source_from_file(a)
    wrong = _write(tmp_path / "OTHER.csv", "foo,bar\n1,2\n")
    with pytest.raises(FileValidationError):
        add_member_file(fds, wrong)
    assert len(fds.members) == 1  # not added


def test_add_member_rejects_duplicate_path(tmp_path):
    a = _write(tmp_path / "CLAIMS.csv", "policy,state,amount\nP1,TX,100\n")
    fds = infer_file_source_from_file(a)
    with pytest.raises(FileValidationError):
        add_member_file(fds, a)


def test_table_names_dedupe_across_folders(tmp_path):
    a = _write(tmp_path / "CLAIMS.csv", "policy,state,amount\nP1,TX,100\n")
    fds = infer_file_source_from_file(a)
    sub = tmp_path / "rga"
    sub.mkdir()
    b = _write(sub / "CLAIMS.csv", "policy,state,amount\nR1,TX,500\n")
    member = add_member_file(fds, b)
    # Same stem in a different folder gets a unique table name.
    assert member.resolved_table_name() == "CLAIMS_2"
    assert fds.table_names == ["CLAIMS", "CLAIMS_2"]


def test_unique_table_name_helper(tmp_path):
    a = _write(tmp_path / "CLAIMS.csv", "policy\nP1\n")
    fds = infer_file_source_from_file(a)
    assert unique_table_name(fds, "CLAIMS") == "CLAIMS_2"
    assert unique_table_name(fds, "NEW") == "NEW"


# ── Column naming (parse + apply) ──────────────────────────────────────────

def test_parse_column_names_lines_and_commas():
    assert parse_column_names("a\nb\nc") == ["a", "b", "c"]
    assert parse_column_names("a, b , c") == ["a", "b", "c"]
    assert parse_column_names("a, b\nc") == ["a", "b", "c"]


def test_parse_column_names_rejects_empty_and_dupes():
    with pytest.raises(ValueError):
        parse_column_names("   ")
    with pytest.raises(ValueError):
        parse_column_names("a\nA")  # case-insensitive collision


def test_apply_column_names_renames_csv_and_updates_parse_spec(tmp_path):
    # No header, so the schema names are the only names the readers know.
    path = _write(tmp_path / "NOHDR.csv", "P1,TX,100\nP2,CA,200\n")
    from suiteview.audit.adhoc_source_intake import delimited_text_spec
    fds = infer_file_source_from_file(
        path, format_spec=delimited_text_spec(has_header=False))
    apply_column_names(fds, ["policy", "state", "amount"])
    assert fds.column_names == ["policy", "state", "amount"]
    assert fds.parse_spec["column_names"] == ["policy", "state", "amount"]
    # The rename is reflected in the data the runner produces.
    from suiteview.audit import file_query_runner
    df = file_query_runner.run_sql(fds, 'SELECT * FROM "NOHDR"').dataframe
    assert list(df.columns) == ["policy", "state", "amount"]


def test_apply_column_names_fixed_width_renames_specs(tmp_path):
    path = _write(tmp_path / "FW.txt", "PROD1TX0100\n")
    fds = infer_file_source_from_file(path, format_spec=fixed_width_spec([
        {"name": "a", "start": 1, "width": 5},
        {"name": "b", "start": 6, "width": 2},
        {"name": "c", "start": 8, "width": 4},
    ]))
    apply_column_names(fds, ["code", "state", "amt"])
    assert fds.column_names == ["code", "state", "amt"]
    assert [c["name"] for c in fds.parse_spec["columns"]] == ["code", "state", "amt"]


def test_apply_column_names_rejects_wrong_count(tmp_path):
    path = _write(tmp_path / "CLAIMS.csv", "policy,state,amount\nP1,TX,100\n")
    fds = infer_file_source_from_file(path)
    with pytest.raises(ValueError):
        apply_column_names(fds, ["only", "two"])


# ── Migration (legacy adhoc_source -> FileDataSource) ──────────────────────

def test_migrate_adhoc_source_to_file_source(tmp_path):
    path = _write(tmp_path / "CLAIMS.csv",
                  "policy,state,amount\nP1,TX,100\nP2,CA,200\n")
    obj = query_object_from_file(path, name="Legacy Claims")
    obj.description = "imported long ago"
    obj.tags = ["legacy"]

    fds = migrate_adhoc_to_file_source(obj)
    assert fds.name == "Legacy Claims"
    assert fds.source_type == "csv"
    assert fds.column_names == ["policy", "state", "amount"]
    assert fds.description == "imported long ago"
    assert fds.tags == ["legacy"]
    assert fds.table_names == ["CLAIMS"]
    assert "path" not in fds.parse_spec
    # The migrated source actually runs (schema + parse spec carried over).
    from suiteview.audit import file_query_runner
    df = file_query_runner.run_sql(fds, 'SELECT * FROM "CLAIMS"').dataframe
    assert len(df) == 2


def test_migrate_rejects_non_adhoc():
    from suiteview.audit.query_object import manual_sql_query_object

    obj = manual_sql_query_object("X", sql="SELECT 1", dsn="D", result_columns=["a"])
    with pytest.raises(FileValidationError):
        migrate_adhoc_to_file_source(obj)


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
