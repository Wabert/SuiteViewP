"""Visual Query UI: SQL Assist file datasets, the Joins canvas and query wiring."""
from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from types import SimpleNamespace
from unittest.mock import patch

import pytest
from PyQt6.QtCore import QMimeData, QPointF
from PyQt6.QtWidgets import QApplication, QMenu

from suiteview.audit.dataforge.join_canvas_view import JoinLineItem
from suiteview.audit.dynamic_group import DynamicQuery
from suiteview.audit.field_picker_panel import FIELD_DRAG_MIME, FieldPickerPanel
from suiteview.audit.file_source import SOURCE_TYPE_CSV
from suiteview.audit.query_sources import TABLE_DRAG_MIME
from suiteview.audit.tabs.visual_joins_tab import ADD_KIND_FILES, VisualJoinsTab

TOKEN = "file:fds1"
CSV = "UL_SLR_202606"
POL = "DB2TAB.LH_BAS_POL"
COV = "DB2TAB.LH_COV_PHA"


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


@pytest.fixture()
def file_source():
    fds = SimpleNamespace(
        id="fds1", name="UL_SLR", source_type=SOURCE_TYPE_CSV,
        parse_spec={"delimiter": ","},
        members=[SimpleNamespace(resolved_table_name=lambda: CSV)],
        columns=[SimpleNamespace(name="PolicyId", data_type="TEXT"),
                 SimpleNamespace(name="SLR Output[Source.Name]", data_type="TEXT")],
    )
    with patch("suiteview.audit.file_source_store.list_file_sources", return_value=[fds]), \
            patch("suiteview.audit.file_query_runner.resolve_file_source",
                  side_effect=lambda ref: fds if ref == "fds1" else None):
        yield fds


def _table_names(picker):
    names = []
    for row in range(picker.list_tables.count()):
        value = picker.list_tables.item(row).data(0x0100)
        if value and value != "__separator__":
            names.append(value)
    return names


def test_sql_assist_holds_database_tables_and_file_datasets(app, file_source):
    picker = FieldPickerPanel(multi_source=True)
    events = []
    picker.table_sources_changed.connect(lambda d: events.append(("sources", dict(d))))
    picker.tables_changed.connect(lambda t: events.append(("tables", list(t))))
    try:
        picker._load_fields = lambda table: None
        picker.set_connection_options([("Neon", "NEON_DSN"), ("Model", "NEON_DSNM")], "NEON_DSN")
        picker.set_group("NEON_DSN", [POL], {}, pinned_tables=[POL, CSV],
                         table_sources={CSV: TOKEN})
        assert _table_names(picker) == [POL, CSV]
        assert picker.btn_add_table.isEnabled()

        # Files mode only chooses what +Table browses: the list is unchanged.
        picker.btn_source_kind.click()
        assert picker.btn_source_kind.text() == "Files"
        assert picker.current_connection() == TOKEN
        assert picker.btn_add_table.isEnabled()
        assert _table_names(picker) == [POL, CSV]
        assert picker.query_dsn() == "NEON_DSN"
        assert events == []

        # A different database drops its old tables but keeps the file dataset,
        # announcing the sources before the table list.
        picker.btn_source_kind.click()
        picker.cmb_connection.setCurrentIndex(1)
        assert picker.query_dsn() == "NEON_DSNM"
        assert _table_names(picker) == [CSV]
        assert events == [("sources", {CSV: TOKEN}), ("tables", [CSV])]
    finally:
        picker.close()


def test_add_file_datasets_dialog_adds_to_query(app, file_source):
    picker = FieldPickerPanel(multi_source=True)
    sources = []
    picker.table_sources_changed.connect(sources.append)
    try:
        picker._load_fields = lambda table: None
        picker.set_connection_options([("Neon", "NEON_DSN")], "NEON_DSN")
        picker.set_group("NEON_DSN", [POL], {}, pinned_tables=[POL])
        with patch("suiteview.audit.dialogs.add_file_tables_dialog.AddFileTablesDialog.exec",
                   return_value=1), \
                patch("suiteview.audit.dialogs.add_file_tables_dialog.AddFileTablesDialog.get_selected",
                      return_value=[(TOKEN, CSV)]):
            assert picker.request_add_tables("files") == [CSV]
        assert _table_names(picker) == [POL, CSV]
        assert sources[-1] == {CSV: TOKEN}
        assert [c[0] for c in picker._field_cache[CSV]] == ["PolicyId", "SLR Output[Source.Name]"]
    finally:
        picker.close()


def test_same_named_datasets_picked_together_are_refused(app, file_source):
    picker = FieldPickerPanel(multi_source=True)
    try:
        picker._load_fields = lambda table: None
        picker.set_connection_options([("Neon", "NEON_DSN")], "NEON_DSN")
        picker.set_group("NEON_DSN", [POL], {}, pinned_tables=[POL])
        with patch("suiteview.audit.dialogs.add_file_tables_dialog.AddFileTablesDialog.exec",
                   return_value=1), \
                patch("suiteview.audit.dialogs.add_file_tables_dialog.AddFileTablesDialog.get_selected",
                      return_value=[(TOKEN, CSV), ("file:other", CSV.lower())]), \
                patch("suiteview.audit.field_picker_panel.QMessageBox.warning") as warn:
            assert picker.request_add_tables("files") == [CSV]
        assert picker.table_sources() == {CSV: TOKEN}
        assert CSV.lower() in warn.call_args[0][2]
    finally:
        picker.close()


def test_table_list_drags_table_names(app):
    picker = FieldPickerPanel(multi_source=True)
    try:
        picker._load_fields = lambda table: None
        picker.set_connection_options([("Neon", "NEON_DSN")], "NEON_DSN")
        picker.set_group("NEON_DSN", [POL], {})
        picker.list_tables.setCurrentRow(0)
        captured = {}

        def fake_exec(self, *_args):
            captured["mime"] = bytes(self.mimeData().data(TABLE_DRAG_MIME)).decode()
            return 0

        with patch("suiteview.audit.field_picker_panel.QDrag.exec", fake_exec):
            picker.list_tables.startDrag(None)
        assert captured["mime"] == POL
    finally:
        picker.close()


def _canvas_with_tables(file_source):
    canvas = VisualJoinsTab(tables=[POL, COV, CSV], dsn="")
    canvas.set_table_columns(POL, ["CK_POLICY_NBR", "TCH_POL_ID"])
    canvas.set_table_columns(COV, ["TCH_POL_ID", "COV_PHA_NBR"])
    canvas.set_local_tables({CSV: TOKEN})
    return canvas


def test_canvas_places_tables_by_drop_and_add_menu(app, file_source):
    canvas = _canvas_with_tables(file_source)
    try:
        assert canvas.canvas_tables() == []
        mime = QMimeData()
        mime.setData(TABLE_DRAG_MIME, f"{POL}\n{CSV}".encode())
        assert canvas._accepts_external_drop(mime)
        canvas._handle_external_drop(mime, QPointF(300, 120))
        assert canvas.canvas_tables() == [POL, CSV]
        assert canvas.model.get_source(POL).x == 300
        assert canvas.scene.box_items[CSV].tag == "CSV"
        assert canvas.scene.box_items[CSV].fields == ["PolicyId", "SLR Output[Source.Name]"]

        # A field dragged from SQL Assist places its table too.
        field_mime = QMimeData()
        field_mime.setData(FIELD_DRAG_MIME, f"{COV}|COV_PHA_NBR|SMALLINT|COV".encode())
        canvas._handle_external_drop(field_mime, QPointF(40, 40))
        assert COV in canvas.canvas_tables()

        canvas.scene.remove_source(COV)
        menu = QMenu()
        requested = []
        canvas.add_tables_requested.connect(requested.append)
        canvas._populate_add_menu(menu, QPointF(0, 0))
        labels = [a.text() for a in menu.actions() if a.text()]
        assert labels[0] == COV
        assert "Browse file datasets\u2026" in labels
        next(a for a in menu.actions() if a.text() == "Browse file datasets\u2026").trigger()
        assert requested == [ADD_KIND_FILES]
        next(a for a in menu.actions() if a.text() == COV).trigger()
        assert COV in canvas.canvas_tables()
    finally:
        canvas.close()


def test_join_line_menu_sets_type_and_marks_keys(app, file_source):
    canvas = _canvas_with_tables(file_source)
    try:
        canvas.ensure_on_canvas(CSV)
        canvas.ensure_on_canvas(POL)
        assert canvas.scene.add_link(CSV, "PolicyId", POL, "CK_POLICY_NBR")
        line = next(i for i in canvas.scene.items() if isinstance(i, JoinLineItem))
        assert canvas.scene.box_items[CSV].key_fields == {"PolicyId"}

        menu = canvas._build_join_menu(line)
        texts = [a.text() for a in menu.actions() if a.text()]
        assert texts[0] == f"{CSV}.PolicyId  =  {POL}.CK_POLICY_NBR"
        left = next(a for a in menu.actions() if a.text().startswith("Left join"))
        assert f"all rows from {CSV}" in left.text()
        assert next(a for a in menu.actions() if a.text().startswith("Inner")).isChecked()
        left.trigger()
        assert canvas.get_join_infos()[0]["join_type"] == "LEFT OUTER JOIN"

        next(a for a in canvas._build_join_menu(line).actions()
             if a.text() == "Delete this key").trigger()
        assert canvas.get_join_infos() == []
        assert canvas.scene.box_items[CSV].key_fields == set()
    finally:
        canvas.close()


def _mixed_query(file_source):
    group = DynamicQuery("\u25b8 Mixed", "NEON_DSN", [POL])
    group.set_pinned_tables([POL, CSV])
    group.set_table_sources({CSV: TOKEN})
    group.joins_tab.set_table_columns(POL, ["CK_POLICY_NBR", "TCH_POL_ID"])
    tab = group._criteria_tabs[0]
    tab.add_field_auto(CSV, "SLR Output[Source.Name]", "TEXT", "Source")
    tab.add_field_auto(POL, "TCH_POL_ID", "CHAR", "Tch")
    tab.grid.field(f"{CSV}.SLR Output[Source.Name]").txt.setText("UL")
    tab.grid.field(f"{POL}.TCH_POL_ID").txt.setText("Q")
    return group


def test_placing_fields_puts_tables_on_canvas_and_requires_join(app, file_source):
    group = _mixed_query(file_source)
    try:
        assert group.joins_tab.canvas_tables() == [CSV, POL]
        assert group.source_for(CSV) == TOKEN and group.source_for(POL) == "NEON_DSN"
        row = group._criteria_tabs[0].grid.field(f"{CSV}.SLR Output[Source.Name]")
        assert row._registry_info[3] == TOKEN

        with patch("suiteview.audit.dynamic_group.QMessageBox.warning") as warn:
            assert group._prepare_query() is None
        assert warn.call_args[0][1] == "Joins Required"
        assert group.tab_widget.currentWidget() is group.joins_tab
    finally:
        group.close()


def test_mixed_query_compiles_federated_plan_and_round_trips(app, file_source):
    group = _mixed_query(file_source)
    try:
        assert group.joins_tab.scene.add_link(CSV, "PolicyId", POL, "CK_POLICY_NBR")
        prepared = group._prepare_query()
        assert prepared is not None and prepared.plan is not None
        step = prepared.plan.steps[0]
        assert step.pushdowns[0].from_table == CSV
        assert "\"TCH_POL_ID\" LIKE '%Q%'" in step.render()
        assert "\"SLR Output[Source.Name]\" LIKE '%UL%'" in prepared.plan.final_sql
        assert prepared.sql.startswith("-- Mixed-source query")
        assert group.is_mixed_source()

        config = group.get_config()
        assert config["table_sources"] == {CSV: TOKEN}
        restored = DynamicQuery("\u25b8 Mixed 2", config["dsn"], config["tables"])
        try:
            restored.set_config(config)
            assert restored.table_sources == {CSV: TOKEN}
            assert restored.joins_tab.canvas_tables() == [CSV, POL]
            assert restored.joins_tab.get_join_infos()[0]["on_pairs"] == [
                ("PolicyId", "CK_POLICY_NBR")]
        finally:
            restored.close()
    finally:
        group.close()


def test_file_query_gaining_a_database_keeps_its_file_tables(app, file_source):
    group = DynamicQuery("\u25b8 File", TOKEN, [])
    try:
        group.set_pinned_tables([CSV])
        group.set_source_dsn("NEON_DSN")
        assert group.dsn == "NEON_DSN"
        assert group.table_sources == {CSV: TOKEN}
        assert group.source_for(CSV) == TOKEN
    finally:
        group.close()
