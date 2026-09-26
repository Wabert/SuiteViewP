from __future__ import annotations

import json
import os
import runpy
from collections.abc import Callable
from pathlib import Path

import pandas as pd
import pytest
from pandas.testing import assert_frame_equal

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

QtWidgets = pytest.importorskip("PyQt6.QtWidgets")
QApplication = QtWidgets.QApplication
_QT_APP = QApplication.instance() or QApplication([])

from suiteview.audit import common_table_store, query_object_store, saved_query_store
from suiteview.audit.common_table import CommonTable
from suiteview.audit.dataforge import dataforge_group, dataforge_store
from suiteview.audit.dataforge.dataforge_group import DataForgeGroup
from suiteview.audit.dataforge.dataforge_model import DataForge
from suiteview.audit.dataforge.forge_engine import FilterSpec
from suiteview.audit.dataforge.services import run_visual_forge
from suiteview.audit.qdefinition import QDefinition
from suiteview.audit.query_object import QueryObject
from suiteview.audit.saved_query import SavedQuery
from suiteview.core import sql_permissions
from suiteview.core.access_control import EffectiveAccess
from suiteview.core.build_env import ReadOnlyDataError


def _app() -> QApplication:
    return _QT_APP


def _json(path: Path, data) -> None:
    path.write_text(json.dumps(data), encoding="utf-8")


def _source(name: str = "Source") -> QDefinition:
    return QDefinition(
        name=name,
        sql=f"SELECT * FROM {name}",
        dsn="FAKE_DSN",
        result_columns=["value"],
        column_types={"value": "TEXT"},
    )


def _group_with_source(name: str = "Source") -> DataForgeGroup:
    _app()
    group = DataForgeGroup("⚙ Regression Forge", saved_forge_name="Regression Forge")
    group._sources[name] = _source(name)
    return group


def test_visual_forge_regex_filter_runs_for_user_role_without_user_sql_guard(monkeypatch):
    def user_access(*, refresh: bool = False) -> EffectiveAccess:
        return EffectiveAccess(
            actor_id="USER1",
            role_code="USER",
            all_apps=True,
            can_update_database=False,
            can_write_support_files=False,
        )

    monkeypatch.setattr(sql_permissions.access_control, "get_access", user_access)
    frame = pd.DataFrame({"value": ["Alpha", "beta", "ALP-2"]})

    result = run_visual_forge(
        {"Source": frame},
        [],
        filters=[FilterSpec("Source", "value", "regex", value="^alp")],
    )

    assert result.dataframe["value"].tolist() == ["Alpha", "ALP-2"]


def test_dataforge_run_shows_unexpected_visual_execution_error(monkeypatch):
    group = _group_with_source()
    messages: list[tuple[str, str]] = []

    def warning(_parent, title: str, message: str) -> None:
        messages.append((title, message))

    def fail_visual_run(*_args, **_kwargs):
        raise ValueError("visual boom")

    def immediate_worker(**kwargs):
        payload = kwargs["work"]()
        try:
            kwargs["on_success"](payload)
        except Exception:
            pass
        return None

    monkeypatch.setattr(group, "_load_source_dataframe", lambda _sq: pd.DataFrame({"value": ["x"]}))
    monkeypatch.setattr(dataforge_group, "run_visual_forge", fail_visual_run)
    monkeypatch.setattr(dataforge_group, "run_query_async", immediate_worker)
    monkeypatch.setattr(dataforge_group.QMessageBox, "warning", warning)

    group._run_forge()

    assert messages == [("DataForge Error", "visual boom")]


@pytest.mark.parametrize(
    ("method_name", "exception_factory"),
    [
        ("_run_single_query", lambda: OSError("snapshot missing")),
        ("_run_single_query", lambda: ReadOnlyDataError("read-only SQL")),
        ("_view_query_results", lambda: OSError("snapshot missing")),
        ("_view_query_results", lambda: ReadOnlyDataError("read-only SQL")),
    ],
)
def test_query_dialog_actions_restore_cursor_and_show_loader_errors(
    monkeypatch,
    method_name: str,
    exception_factory: Callable[[], Exception],
):
    group = _group_with_source("Broken")
    messages: list[tuple[str, str]] = []

    def warning(_parent, title: str, message: str) -> None:
        messages.append((title, message))

    def fail_load(_sq):
        raise exception_factory()

    monkeypatch.setattr(group, "_load_source_dataframe", fail_load)
    monkeypatch.setattr(dataforge_group.QMessageBox, "warning", warning)

    try:
        getattr(group, method_name)("Broken")
        assert QApplication.overrideCursor() is None
    finally:
        while QApplication.overrideCursor() is not None:
            QApplication.restoreOverrideCursor()

    assert messages
    assert messages[0][0] == "Query Error"
    assert "Failed to execute \"Broken\"" in messages[0][1]


def test_generated_visual_script_preserves_like_escape_backslashes(tmp_path):
    group = _app_dataforge_with_csv_source(tmp_path)
    filters = group._engine_filter_specs()
    source_frame = pd.DataFrame({"value": ["A_B", "AxB", "zz"]})
    app_result = run_visual_forge(
        {"CSV Source": source_frame},
        [],
        filters=filters,
    )
    expected = app_result.dataframe.reset_index(drop=True)

    script = tmp_path / "generated_dataforge.py"
    script.write_text(
        group._generate_python_code(
            {"CSV Source": "Ad hoc source: csv"},
            app_result.sql,
        ),
        encoding="utf-8",
    )

    actual = runpy.run_path(str(script))["result"].reset_index(drop=True)

    assert_frame_equal(actual, expected)
    assert actual["value"].tolist() == ["A_B"]


def test_sql_generators_embed_sql_with_repr_for_backslashes():
    group = _group_with_source("ODBC Source")
    sql = r"SELECT * FROM T WHERE C ILIKE '%a\_b%' ESCAPE '\'"

    load_code = "\n".join(group._generate_load_code({"ODBC Source": sql}))
    manual_code = group._generate_manual_python_code({"ODBC Source": "SELECT 1"}, sql, None)

    assert f"pd.read_sql({sql!r}, conn_" in load_code
    assert f"con.execute({sql!r}).df()" in manual_code
    assert 'pd.read_sql("""' not in load_code
    assert 'con.execute("""' not in manual_code


def _app_dataforge_with_csv_source(tmp_path: Path) -> DataForgeGroup:
    group = DataForgeGroup("⚙ CSV Forge", saved_forge_name="CSV Forge")
    csv_path = tmp_path / "source.csv"
    csv_path.write_text("value\nA_B\nAxB\nzz\n", encoding="utf-8")

    qd = QDefinition(
        name="CSV Source",
        source_design="csv",
        result_columns=["value"],
        column_types={"value": "TEXT"},
    )
    qd.query_object_kind = "adhoc_source"
    qd.query_object_source_metadata = {"path": str(csv_path), "has_header": True}
    group._sources[qd.name] = qd

    tab = group._filter_tabs[0]
    tab.add_field_auto(qd.name, "value")
    row = tab.grid.field(f"{qd.name}.value")
    assert row is not None
    row.set_mode_idx(0)
    row.txt.setText("a_b")
    return group


@pytest.mark.parametrize(
    ("store_name", "save_valid", "list_valid_names", "load_missing_key"),
    [
        (
            "saved_query",
            lambda: saved_query_store.save_query(SavedQuery("Valid query")),
            lambda: [item.name for item in saved_query_store.list_queries()],
            lambda: saved_query_store.load_query("missing_key"),
        ),
        (
            "common_table",
            lambda: common_table_store.save_table(CommonTable("Valid table")),
            lambda: [item.name for item in common_table_store.list_tables()],
            lambda: common_table_store.load_table("missing_key"),
        ),
        (
            "dataforge",
            lambda: dataforge_store.save_forge(DataForge("Valid forge")),
            lambda: [item.name for item in dataforge_store.list_forges()],
            lambda: dataforge_store.load_forge("missing_key"),
        ),
        (
            "query_object",
            lambda: query_object_store.save_object(QueryObject("Valid object")),
            lambda: [item.name for item in query_object_store.list_objects()],
            lambda: query_object_store.load_object("missing_key"),
        ),
    ],
)
def test_user_json_stores_skip_missing_key_and_list_top_level_files(
    store_name: str,
    save_valid,
    list_valid_names,
    load_missing_key,
):
    save_valid()
    root = _store_root(store_name)
    _json(root / "missing_key.json", {})
    _json(root / "list_top_level.json", [])

    names = list_valid_names()

    assert any(name.startswith("Valid ") for name in names)
    assert load_missing_key() is None


def _store_root(store_name: str) -> Path:
    if store_name == "saved_query":
        return saved_query_store._queries_dir()
    if store_name == "common_table":
        return common_table_store._tables_dir()
    if store_name == "dataforge":
        return dataforge_store._forges_dir()
    if store_name == "query_object":
        return query_object_store._objects_dir()
    raise AssertionError(store_name)
