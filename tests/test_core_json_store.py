from __future__ import annotations

import pytest

from suiteview.audit import (
    common_table_store,
    data_source_store,
    file_source_store,
    group_config,
    qdef_store,
    query_object_store,
    saved_query_store,
)
from suiteview.audit.dataforge import dataforge_store
from suiteview.core import json_store


@pytest.mark.parametrize(
    ("name", "expected"),
    [
        ("Plain Name", "Plain Name"),
        ('a<b>c:d"e/f\\g|h?i*j', "a_b_c_d_e_f_g_h_i_j"),
        ("spaces and unicode é", "spaces and unicode é"),
        ("[glob]*name?.json", "[glob]_name_.json"),
        ("", ""),
    ],
)
def test_safe_filename_matches_legacy_audit_regex(name, expected):
    assert json_store.safe_filename(name) == expected


def test_audit_stores_use_shared_safe_filename():
    stores = [
        common_table_store,
        data_source_store,
        file_source_store,
        qdef_store,
        query_object_store,
        saved_query_store,
        dataforge_store,
    ]
    for store in stores:
        assert store._safe_filename is json_store.safe_filename
        assert store._safe_filename('bad/name*') == "bad_name_"


def test_ensure_dir_creates_and_returns_path(tmp_path):
    target = tmp_path / "nested" / "folder"
    assert json_store.ensure_dir(target) == target
    assert target.is_dir()


def test_write_json_failure_leaves_existing_file_intact(tmp_path, monkeypatch):
    target = tmp_path / "state.json"
    original = '{"old": true}'
    target.write_text(original, encoding="utf-8")

    def fail_after_partial_write(data, handle, **kwargs):
        handle.write('{"new":')
        raise RuntimeError("simulated mid-write failure")

    monkeypatch.setattr(json_store.json, "dump", fail_after_partial_write)

    with pytest.raises(RuntimeError, match="simulated mid-write failure"):
        json_store.write_json(target, {"new": True}, ensure_ascii=True)

    assert target.read_text(encoding="utf-8") == original
    assert list(tmp_path.glob(".state.json.*.tmp")) == []


def test_write_json_can_preserve_ascii_escaping(tmp_path):
    target = tmp_path / "escaped.json"
    json_store.write_json(target, {"label": "é"}, ensure_ascii=True)
    assert target.read_text(encoding="utf-8") == '{\n  "label": "\\u00e9"\n}'
