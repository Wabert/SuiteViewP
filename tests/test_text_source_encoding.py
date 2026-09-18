"""Unicode file sources use the same strict decoding for intake, preview and SQL."""
import codecs
from pathlib import Path
from unittest.mock import patch

import pytest

from suiteview.audit import file_query_runner, file_source_store
from suiteview.audit.adhoc_source_intake import (
    _sniff_delimiter,
    dataframe_from_adhoc_metadata,
    delimited_text_spec,
    fixed_width_spec,
)
from suiteview.audit.file_source_intake import (
    add_member_file,
    infer_file_source_from_file,
    validate_member_file,
)


@pytest.mark.parametrize("codec,bom,expected", [
    ("utf-8", b"", "utf-8-sig"),
    ("utf-8", codecs.BOM_UTF8, "utf-8-sig"),
    ("utf-16-le", codecs.BOM_UTF16_LE, "utf-16"),
    ("utf-16-be", codecs.BOM_UTF16_BE, "utf-16"),
    ("utf-32-le", codecs.BOM_UTF32_LE, "utf-32"),
    ("utf-32-be", codecs.BOM_UTF32_BE, "utf-32"),
])
@pytest.mark.parametrize("delimiter,suffix", [(",", ".csv"), ("\t", ".txt"), ("|", ".psv")])
def test_unicode_source_round_trip(tmp_path, monkeypatch, codec, bom, expected, delimiter, suffix):
    path = tmp_path / ("claims" + suffix)
    text = delimiter.join(["policy", "name", "amount"]) + "\n"
    text += delimiter.join(["P1", "Ren\u00e9e", "125"]) + "\n"
    path.write_bytes(bom + text.encode(codec))
    source = infer_file_source_from_file(path)
    assert source.parse_spec["encoding"] == expected
    assert source.parse_spec["delimiter"] == delimiter
    assert source.column_names == ["policy", "name", "amount"]
    assert validate_member_file(source, path) == []

    monkeypatch.setenv("SUITEVIEW_FILE_SOURCES_DIR", str(tmp_path / "sources"))
    file_source_store.save_file_source(source)
    loaded = file_source_store.load_file_source_by_id(source.id)
    assert loaded.parse_spec == source.parse_spec
    preview = dataframe_from_adhoc_metadata(
        loaded.source_type, loaded.member_metadata(loaded.members[0]), nrows=100)
    result = file_query_runner.run_sql(loaded, 'SELECT name, amount FROM "claims"')
    assert preview["name"].tolist() == ["Ren\u00e9e"]
    assert result.dataframe.iloc[0].tolist() == ["Ren\u00e9e", 125]


def test_default_specs_detect_encoding_with_skip_rows_and_no_header(tmp_path):
    path = tmp_path / "claims.txt"
    path.write_text("Report\nP1|Ren\u00e9e|125\n", encoding="utf-16")
    spec = delimited_text_spec(
        delimiter="|", has_header=False, skip_rows=1,
        column_names=["policy", "name", "amount"])
    source = infer_file_source_from_file(path, format_spec=spec)
    assert source.parse_spec["encoding"] == "utf-16"
    assert spec["encoding"] == "auto"  # inference must not mutate the caller's spec
    assert file_query_runner.run_sql(source, 'SELECT name FROM "claims"').dataframe.iloc[0, 0] == "Ren\u00e9e"


def test_fixed_width_unicode_source(tmp_path):
    path = tmp_path / "claims.txt"
    path.write_text("Report\nP1Ren\u00e9e125\n", encoding="utf-16")
    source = infer_file_source_from_file(path, format_spec=fixed_width_spec([
        {"name": "policy", "start": 1, "width": 2},
        {"name": "name", "start": 3, "width": 5},
        {"name": "amount", "start": 8, "width": 3},
    ], skip_rows=1))
    assert source.parse_spec["encoding"] == "utf-16"
    assert validate_member_file(source, path) == []
    result = file_query_runner.run_sql(source, 'SELECT name, amount FROM "claims"')
    assert result.dataframe.iloc[0].tolist() == ["Ren\u00e9e", 125]


def test_add_unicode_member_and_query_both_files(tmp_path):
    first = tmp_path / "june.txt"
    second = tmp_path / "july.txt"
    first.write_text("policy\tamount\nP1\t125\n", encoding="utf-16")
    second.write_bytes(codecs.BOM_UTF16_BE + "policy\tamount\nP2\t175\n".encode("utf-16-be"))
    source = infer_file_source_from_file(first)
    add_member_file(source, second)
    result = file_query_runner.run_sql(
        source, 'SELECT SUM(amount) FROM (SELECT * FROM "june" UNION ALL SELECT * FROM "july")')
    assert result.dataframe.iloc[0, 0] == 300


def test_explicit_encoding_is_honored(tmp_path):
    path = tmp_path / "claims.txt"
    path.write_text("name|amount\nRen\u00e9e|125\n", encoding="cp1252")
    source = infer_file_source_from_file(
        path, format_spec=delimited_text_spec(delimiter="|", encoding="cp1252"))
    assert source.parse_spec["encoding"] == "cp1252"
    assert file_query_runner.run_sql(source, 'SELECT name FROM "claims"').dataframe.iloc[0, 0] == "Ren\u00e9e"

    path.write_text("name|amount\nRen\u00e9e|125\n", encoding="utf-16")
    with pytest.raises(UnicodeDecodeError):
        infer_file_source_from_file(
            path, format_spec=delimited_text_spec(delimiter="|", encoding="utf-8-sig"))


def test_invalid_encoding_is_not_silently_replaced(tmp_path):
    path = tmp_path / "claims.txt"
    path.write_bytes(b"policy|name\nP1|Ren\xe9e\n")
    with pytest.raises(UnicodeDecodeError):
        infer_file_source_from_file(path)


def test_delimiter_sniff_is_bounded_and_propagates_io_errors(tmp_path):
    path = tmp_path / "large.txt"
    path.write_bytes(b"policy|amount\n" * 10000 + b"\xff")
    with patch.object(Path, "read_text", side_effect=AssertionError("Whole-file read")):
        assert _sniff_delimiter(path, "utf-8-sig") == "|"
    with pytest.raises(FileNotFoundError):
        _sniff_delimiter(tmp_path / "missing.txt", "utf-8-sig")


@pytest.mark.parametrize("mode", ["Auto-detect delimited", "Delimited", "Fixed width"])
def test_add_file_dialog_path_detects_unicode(tmp_path, mode):
    from PyQt6.QtWidgets import QInputDialog, QMessageBox
    from suiteview.audit.file_source_format_dialogs import establish_source_from_first_file

    path = tmp_path / "claims.txt"
    text = "P1TX125\n" if mode == "Fixed width" else "policy|state|amount\nP1|TX|125\n"
    path.write_text(text, encoding="utf-16")
    with (
        patch.object(QInputDialog, "getItem", return_value=(mode, True)),
        patch.object(QInputDialog, "getText", return_value=("|", True)),
        patch.object(QInputDialog, "getInt", return_value=(0, True)),
        patch.object(QInputDialog, "getMultiLineText",
                     return_value=("policy,1,2\nstate,3,2\namount,5,3", True)),
        patch.object(QMessageBox, "question", return_value=QMessageBox.StandardButton.Yes),
        patch.object(QMessageBox, "warning") as warning,
    ):
        source = establish_source_from_first_file(None, str(path), "Claims")
    warning.assert_not_called()
    assert source.parse_spec["encoding"] == "utf-16"
    assert source.column_names == ["policy", "state", "amount"]


def test_edit_delimited_format_keeps_explicit_encoding(tmp_path):
    from PyQt6.QtWidgets import QInputDialog, QMessageBox
    from suiteview.audit.file_source_format_dialogs import prompt_format_spec_for_source

    path = tmp_path / "claims.txt"
    path.write_text("name|amount\nRen\u00e9e|125\n", encoding="cp1252")
    source = infer_file_source_from_file(
        path, format_spec=delimited_text_spec(delimiter="|", encoding="cp1252"))
    with (
        patch.object(QInputDialog, "getText", return_value=("|", True)),
        patch.object(QInputDialog, "getInt", return_value=(0, True)),
        patch.object(QMessageBox, "question", return_value=QMessageBox.StandardButton.Yes),
    ):
        spec = prompt_format_spec_for_source(None, source)
    assert spec["encoding"] == "cp1252"
