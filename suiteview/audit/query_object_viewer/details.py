"""QueryObject Viewer DetailsMixin methods."""
from __future__ import annotations

import json
import os
from pathlib import Path

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QTableWidgetItem

from suiteview.audit import data_source_store, file_source_store
from suiteview.audit.dataforge import dataforge_store
from suiteview.audit.file_source import (
    SOURCE_TYPE_CSV,
    SOURCE_TYPE_EXCEL,
    SOURCE_TYPE_FIXED_WIDTH,
    datasource_label,
)
from suiteview.audit.query_object import OBJECT_KIND_ADHOC_SOURCE, QueryObject
from suiteview.audit.query_object_viewer.common import (
    _dataforge_display_name,
    _display_dsn_for_object,
    _file_source_type_label,
    _filename_from_path,
    _kind_label,
)
from suiteview.core.odbc_utils import (
    UNKNOWN,
    access_driver,
    detect_dialect,
    get_dsn_details,
    list_access_tables,
    probe_access_connection,
    probe_dsn_connection,
)


class QueryObjectViewerDetailsMixin:
    """Requires BrowserState current/detail attrs; provides detail rendering."""

    def _clear_detail(self):
        self._current = None
        self._current_forge_name = ""
        self._current_source_path = ""
        self._set_editor_read_only(False)
        self._configure_object_tables()
        self.lbl_name.setText("Select a QueryObject")
        self.lbl_kind.setText("")
        self.lbl_status.setText("")
        self.edit_name.clear()
        self.edit_origin.clear()
        self.edit_tags.clear()
        self.edit_description.clear()
        self.tbl_sources.setRowCount(0)
        self.tbl_outputs.setRowCount(0)
        self.tbl_inputs.setRowCount(0)
        self.tbl_joins.setRowCount(0)
        self.tbl_fields.setRowCount(0)
        self.txt_sql.clear()
        self.txt_config.clear()
        self.btn_open_builder.setEnabled(False)
        self.btn_preview_file.setEnabled(False)
        self.btn_open_source_folder.setEnabled(False)
        self.btn_open_source_folder.setVisible(False)
        self.btn_promote.setEnabled(False)
        self.btn_promote.setVisible(False)
        self.btn_delete.setEnabled(False)
        self.btn_save.setEnabled(False)
        if hasattr(self, "left_tabs"):
            if self.left_tabs.tabText(self.left_tabs.currentIndex()) == "Data Sources":
                self._update_data_sources_canvas_title()
            else:
                self._update_queried_canvas_title()

    def _show_detail(self, obj: QueryObject):
        self._loading_detail = True
        self._current = obj
        self._current_forge_name = ""
        self._current_source_path = ""
        self._set_editor_read_only(False)
        self._configure_object_tables()
        if hasattr(self, "left_tabs") and self.left_tabs.tabText(self.left_tabs.currentIndex()) == "Data Sources":
            self._set_canvas_title(f"Data Sources: {obj.name}")
        else:
            self._set_canvas_title(f"{_kind_label(obj.kind)}: {obj.name}")
        self.lbl_name.setText(obj.name)
        self.lbl_kind.setText(_kind_label(obj.kind))
        self.lbl_status.setText(f"Status: {obj.metadata_status}    DSN: {_display_dsn_for_object(obj) or '-'}")
        self.btn_delete.setEnabled(True)
        self.btn_save.setEnabled(True)
        self.btn_open_builder.setEnabled(self._can_open_in_builder(obj))
        self.btn_preview_file.setEnabled(self._can_preview_object(obj))
        self.btn_open_source_folder.setEnabled(False)
        self.btn_open_source_folder.setVisible(False)
        self.btn_promote.setEnabled(obj.kind == OBJECT_KIND_ADHOC_SOURCE)
        self.btn_promote.setVisible(obj.kind == OBJECT_KIND_ADHOC_SOURCE)
        self.edit_name.setText(obj.name)
        self.edit_origin.setText("File Source" if obj.kind == OBJECT_KIND_ADHOC_SOURCE else obj.source_design or obj.kind)
        self.edit_tags.setText(", ".join(obj.tags))
        self.edit_description.setText(obj.description)

        self.tbl_sources.setRowCount(len(obj.sources))
        for row, source in enumerate(obj.sources):
            dsn = _file_source_type_label(source.source_type, source.metadata) if obj.kind == OBJECT_KIND_ADHOC_SOURCE else source.dsn
            values = [source.name, source.source_type, dsn, source.status]
            for col, value in enumerate(values):
                self.tbl_sources.setItem(row, col, QTableWidgetItem(str(value)))
        self.tbl_sources.resizeColumnsToContents()
        self.tbl_sources.setColumnWidth(0, max(self.tbl_sources.columnWidth(0), 240))
        self.tbl_sources.setColumnWidth(1, max(self.tbl_sources.columnWidth(1), 80))

        self._populate_role_table(self.tbl_outputs, obj, {"output"})
        self._populate_role_table(self.tbl_inputs, obj, {"input"})
        self._populate_role_table(self.tbl_joins, obj, {"join_key"})

        self.tbl_fields.setRowCount(len(obj.fields))
        for row, field in enumerate(obj.fields):
            values = [field.name, field.data_type, field.role, field.display_name, field.source]
            for col, value in enumerate(values):
                item = QTableWidgetItem(str(value))
                if col == 0:
                    item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
                self.tbl_fields.setItem(row, col, item)
        self.tbl_fields.resizeColumnsToContents()
        self.tbl_fields.setColumnWidth(0, max(self.tbl_fields.columnWidth(0), 180))
        self.tbl_fields.setColumnWidth(1, max(self.tbl_fields.columnWidth(1), 110))

        self.txt_sql.setPlainText(obj.sql or "")
        self.txt_config.setPlainText(json.dumps({
            "config": obj.config,
            "manual_layers": obj.manual_layers,
            "source_design": obj.source_design,
            "created_at": obj.created_at.isoformat(),
            "updated_at": obj.updated_at.isoformat(),
        }, indent=2))
        self._loading_detail = False

    def _show_forge_detail(self, forge_name: str):

        self._loading_detail = True
        self._current = None
        self._current_forge_name = forge_name
        self._current_source_path = ""
        self._set_editor_read_only(False)
        self._configure_forge_tables()

        forge = dataforge_store.load_forge(forge_name)
        forge_objects = self._query_objects_for_forge(forge_name)
        display_name = _dataforge_display_name(forge_name)

        self._set_canvas_title(f"DataForge: {display_name}")
        self.lbl_name.setText(f"Forge: {display_name}")
        self.lbl_kind.setText("DataForge")
        saved_text = "Saved" if forge is not None else "Query copies only"
        source_count = len(forge.sources) if forge is not None else len(forge_objects)
        self.lbl_status.setText(f"Status: {saved_text}    Sources: {source_count}")
        self.btn_delete.setEnabled(True)
        self.btn_save.setEnabled(False)
        self.btn_open_builder.setEnabled(forge is not None)
        self.btn_preview_file.setEnabled(False)
        self.btn_open_source_folder.setEnabled(False)
        self.btn_open_source_folder.setVisible(False)
        self.btn_promote.setEnabled(False)
        self.btn_promote.setVisible(False)
        self.edit_name.setText(display_name)
        self.edit_origin.setText("DataForge")
        self.edit_tags.clear()
        self.edit_description.setText(
            "Saved DataForge definition and its forge-local query copies." if forge is not None
            else "Forge-local query copies without a saved DataForge definition.")

        source_rows = self._forge_source_rows(forge, forge_objects)
        self._set_table_rows(self.tbl_sources, source_rows)
        self.tbl_sources.setColumnWidth(0, max(self.tbl_sources.columnWidth(0), 180))
        self.tbl_sources.setColumnWidth(1, max(self.tbl_sources.columnWidth(1), 220))

        output_rows, all_field_rows = self._forge_field_rows(forge, forge_objects)
        self._set_table_rows(self.tbl_outputs, output_rows)
        self._set_table_rows(self.tbl_fields, all_field_rows)
        self._set_table_rows(self.tbl_inputs, self._forge_filter_rows(forge))
        self._set_table_rows(self.tbl_joins, self._forge_join_rows(forge))
        self.txt_sql.setPlainText(self._forge_sql_text(forge, forge_objects))
        self.txt_config.setPlainText(json.dumps(
            forge.to_dict() if forge is not None else {
                "name": forge_name,
                "query_objects": [obj.to_dict() for obj in forge_objects],
            },
            indent=2,
        ))
        self._loading_detail = False

    def _show_odbc_source_detail(self, payload: dict, *, probe: bool = False) -> None:
        """A DSN discovered from queries (not registered). Read-only + Register."""
        dsn = str(payload.get("dsn", "")).strip()
        objects = self._objects_from_payload(payload)
        self._current = None
        self._current_forge_name = ""
        self._current_source_kind = "odbc_source"
        self._current_source_payload = payload
        self._current_file_source = None
        self._current_data_source = None
        self._current_source_path = ""

        dialect = detect_dialect(dsn) if dsn else UNKNOWN
        dash = self._source_dashboard
        dash.set_editable(False)
        dash.set_title(dsn or "ODBC")
        dash.set_badge(dialect if dialect != UNKNOWN else "ODBC", "#1E5BA8")
        dash.set_health(*self._odbc_health(dsn, probe))
        # Discovered DSN: read-only, but offer to Register it (pin + name it).
        dash.set_actions(test=True, register=True, edit=False, new_query=False,
                         open_folder=False, delete=False)
        dash.set_test_button("Test", "Test the ODBC DSN connection")
        dash.set_panel("setup", ["Property", "Value"], self._odbc_detail_rows(dsn))
        dash.set_panel("columns", [], [], visible=False)
        dash.set_tables([], removable=False)
        dash.set_tables_tab_visible(False)
        dash.set_panel("usedby", ["Query Object", "Kind", "Source", "Fields"],
                       self._source_query_rows(objects))
        self._set_canvas_title(f"Data Sources: {dsn}" if dsn else "Data Sources")

    def _show_registered_odbc_detail(self, payload: dict, *, probe: bool = False) -> None:

        ds = data_source_store.load_data_source_by_id(str(payload.get("data_source_id", "")))
        self._current = None
        self._current_forge_name = ""
        self._current_source_kind = "registered_odbc"
        self._current_source_payload = payload
        self._current_file_source = None
        self._current_data_source = ds
        self._current_source_path = ""
        if ds is None:
            self._reset_current_source()
            self._source_dashboard.show_empty("This data source could not be found.")
            return

        objects = self._objects_from_payload(payload)
        dash = self._source_dashboard
        dash.set_editable(False)
        dash.set_title(ds.name)
        dash.set_badge(ds.dialect or "ODBC", "#1E5BA8")
        dash.set_health(*self._odbc_health(ds.dsn, probe))
        dash.set_actions(test=True, register=False, edit=True, new_query=False,
                         open_folder=False, delete=True)
        dash.set_test_button("Test", "Test the ODBC DSN connection")
        setup = [
            ["Name", ds.name],
            ["DSN", ds.dsn],
            ["Dialect", ds.dialect or "—"],
            ["Notes", ds.notes or "—"],
            ["Registered", ds.created_at.strftime("%Y-%m-%d %H:%M")],
        ]
        # Append the live DSN details, but not the keys we already show above.
        shown = {"dsn", "dialect"}
        setup.extend(row for row in self._odbc_detail_rows(ds.dsn)
                     if str(row[0]).strip().lower() not in shown)
        dash.set_panel("setup", ["Property", "Value"], setup)
        dash.set_panel("columns", [], [], visible=False)
        dash.set_tables([], removable=False)
        dash.set_tables_tab_visible(False)
        dash.set_panel("usedby", ["Query Object", "Kind", "Source", "Fields"],
                       self._source_query_rows(objects))
        self._set_canvas_title(f"Data Sources: {ds.name}")

    def _odbc_health(self, dsn: str, probe: bool) -> tuple[str, str]:
        """Health pill for an ODBC DSN. ``probe`` does a live connection test
        (Test button); otherwise just report whether the DSN is configured."""
        if not dsn:
            return "No DSN", "warn"
        if probe:
            ok, message = probe_dsn_connection(dsn)
            return ("Connected", "ok") if ok else (f"Unreachable — {message[:60]}", "bad")
        details = self._safe_dsn_details(dsn)
        if "__error__" in details or "Error" in details:
            return "DSN not found on this machine", "bad"
        return "Configured", "neutral"

    def _show_access_source_detail(self, payload: dict, *, probe: bool = False) -> None:

        ds = data_source_store.load_data_source_by_id(str(payload.get("data_source_id", "")))
        self._current = None
        self._current_forge_name = ""
        self._current_source_kind = "access_source"
        self._current_source_payload = payload
        self._current_file_source = None
        self._current_data_source = ds
        if ds is None:
            self._reset_current_source()
            self._source_dashboard.show_empty("This data source could not be found.")
            return

        self._current_source_path = ds.path
        objects = self._objects_from_payload(payload)
        dash = self._source_dashboard
        dash.set_editable(False)
        dash.set_title(ds.name)
        dash.set_badge("MS Access", "#8B5E00")
        dash.set_health(*self._access_health(ds.path, probe))
        dash.set_actions(test=True, register=False, edit=True, new_query=False,
                         open_folder=bool(ds.path), delete=True)
        dash.set_test_button("Test", "Open the Access file to test the connection")
        setup = [
            ["Name", ds.name],
            ["File", ds.path],
            ["Folder", str(Path(ds.path).parent) if ds.path else ""],
            ["Driver", access_driver() or "Access ODBC driver not installed"],
            ["Notes", ds.notes or "—"],
            ["Registered", ds.created_at.strftime("%Y-%m-%d %H:%M")],
        ]
        dash.set_panel("setup", ["Property", "Value"], setup)
        tables = list_access_tables(ds.path)
        # Each Access table lives in the one .accdb file, so they share its path.
        dash.set_tables([(name, "", ds.path) for name in tables], removable=False)
        dash.set_tables_tab_visible(bool(tables))
        dash.set_panel("columns", [], [], visible=False)
        dash.set_panel("usedby", ["Query Object", "Kind", "Source", "Fields"],
                       self._source_query_rows(objects))
        self._set_canvas_title(f"Data Sources: {ds.name}")

    @staticmethod
    def _access_health(path: str, probe: bool) -> tuple[str, str]:

        if not path:
            return "No file", "warn"
        if not os.path.exists(path):
            return "File not found", "bad"
        if probe:
            ok, message = probe_access_connection(path)
            return ("Connected", "ok") if ok else (f"Unreachable — {message[:60]}", "bad")
        return "File OK", "ok"

    def _show_file_data_source_detail(self, payload: dict) -> None:
        """Render a saved File Source in the editable dashboard (view = edit)."""

        fs_id = str(payload.get("file_source_id") or payload.get("key", "")).strip()
        fds = file_source_store.load_file_source_by_id(fs_id)
        self._current = None
        self._current_forge_name = ""
        self._current_source_kind = "file_data_source"
        self._current_source_payload = payload
        self._current_file_source = fds
        self._file_source_is_new = False
        if fds is None:
            self._reset_current_source()
            self._source_dashboard.show_empty("This File Source could not be found.")
            return
        self._render_file_source(fds, payload, new=False)

    def _render_file_source(self, fds, payload: dict, *, new: bool) -> None:
        """Fill the editable dashboard for a File Source (``fds=None`` = brand new).

        Drives the single canonical screen: Setup name/description + Columns
        (name/type) editable, member files on the Tables tab, Save in the header.
        ``new`` sources hide query/delete/refresh until first saved.
        """

        dash = self._source_dashboard
        dash.set_editable(True)
        objects = self._objects_from_payload(payload) if payload else []

        if fds is None:
            self._current_source_path = ""
            dash.set_title("New File Source")
            dash.set_badge("", "")
            dash.set_health("Add a file to set the format", "warn")
            dash.set_actions(test=False, edit=False, new_query=False,
                             open_folder=False, delete=False, save=True)
            dash.set_editable_setup(
                "", "",
                "Add a file (drag it onto the Tables tab, or Add File(s)…) to set "
                "the format and columns. Later files must match.")
            dash.set_editable_columns([])
            dash.set_tables([], removable=False)
            dash.set_tables_tab_visible(True)
            dash.set_panel("usedby", ["Query Object", "Kind", "Fields"], [])
            dash.set_dirty(False)
            dash.btn_save.setEnabled(False)
            dash.tabs.setCurrentIndex(1)  # land on the Tables tab to add a file
            self._set_canvas_title("Data Sources: New File Source")
            return

        self._current_source_path = fds.members[0].path if fds.members else ""
        dash.set_title("New File Source" if new else fds.name)
        dash.set_badge(datasource_label(fds), "#B58900")
        missing = [m for m in fds.members if not Path(m.path).exists()]
        if not fds.members:
            dash.set_health("No files", "warn")
        elif missing:
            dash.set_health(f"{len(missing)} of {len(fds.members)} files missing", "bad")
        else:
            dash.set_health(f"{len(fds.members)} files OK", "ok")
        if new:
            dash.set_actions(test=False, edit=False, new_query=False,
                             open_folder=False, delete=False, save=True,
                             edit_format=True)
        else:
            dash.set_actions(test=False, edit=False, new_query=False,
                             open_folder=False, delete=False, save=True,
                             edit_format=True)
        dash.set_test_button("Refresh", "Re-check that the member files still exist")
        dash.set_editable_setup(
            fds.name, fds.description, self._file_source_info_text(fds))
        dash.set_editable_columns(
            [(c.name, c.data_type) for c in fds.columns],
            names_editable=fds.source_type != SOURCE_TYPE_EXCEL)
        dash.set_tables([
            (m.resolved_table_name(),
             "OK" if Path(m.path).exists() else "missing", m.path)
            for m in fds.members
        ], removable=True)
        dash.set_tables_tab_visible(True)
        dash.set_panel("usedby", ["Query Object", "Kind", "Fields"], [
            [obj.name, _kind_label(obj.kind), len(obj.fields)] for obj in objects
        ])
        dash.set_dirty(bool(new))
        self._set_canvas_title(
            "Data Sources: New File Source" if new else f"Data Sources: {fds.name}")

    def _refresh_file_source_tables(self, fds) -> None:
        """Update only the Tables list + info line (preserves in-progress edits)."""
        dash = self._source_dashboard
        dash.set_tables([
            (m.resolved_table_name(),
             "OK" if Path(m.path).exists() else "missing", m.path)
            for m in fds.members
        ], removable=True)
        dash.set_tables_tab_visible(True)
        dash.lbl_setup_info.setText(self._file_source_info_text(fds))
        missing = [m for m in fds.members if not Path(m.path).exists()]
        if missing:
            dash.set_health(f"{len(missing)} of {len(fds.members)} files missing", "bad")
        elif fds.members:
            dash.set_health(f"{len(fds.members)} files OK", "ok")
        else:
            dash.set_health("No files", "warn")

    def _file_source_info_text(self, fds) -> str:

        return "\n".join([
            f"Type: {datasource_label(fds)}",
            f"Format: {self._file_source_format_summary(fds)}",
            f"Member files: {len(fds.members)}    Columns: {len(fds.columns)}",
            f"Updated: {fds.updated_at.strftime('%Y-%m-%d %H:%M')}",
        ])

    @staticmethod
    def _file_source_format_summary(fds) -> str:

        st = fds.source_type
        ps = fds.parse_spec or {}
        if st == SOURCE_TYPE_CSV:
            delim = ps.get("delimiter", ",")
            delim_disp = "\\t (tab)" if delim == "\t" else f"'{delim}'"
            header = "header row" if ps.get("has_header", True) else "no header"
            skip = ps.get("skip_rows", 0)
            extra = f", skip {skip}" if skip else ""
            return f"Delimited — delimiter {delim_disp}, {header}{extra}"
        if st == SOURCE_TYPE_FIXED_WIDTH:
            return f"Fixed width — {len(ps.get('columns', []))} columns"
        if st == SOURCE_TYPE_EXCEL:
            return f"Excel — sheet {ps.get('sheet_name', 0)}"
        return st

    def _show_file_source_detail(self, payload: dict) -> None:
        path = str(payload.get("path", "")).strip()
        label = str(payload.get("label", "")).strip() or _filename_from_path(path)
        source_type = str(payload.get("source_type", "")).strip()
        objects = self._objects_from_payload(payload)
        self._current = None
        self._current_forge_name = ""
        self._current_source_kind = "file_source"
        self._current_source_payload = payload
        self._current_file_source = None
        self._current_source_path = path

        dash = self._source_dashboard
        dash.set_editable(False)
        dash.set_title(label)
        dash.set_badge(_file_source_type_label(source_type, payload.get("metadata", {})), "#8B6914")
        if path and Path(path).exists():
            dash.set_health("File OK", "ok")
        elif path:
            dash.set_health("File missing", "bad")
        else:
            dash.set_health("Path not saved", "warn")
        dash.set_actions(test=True, edit=False, new_query=False,
                         open_folder=bool(path), delete=False)
        dash.set_test_button("Refresh", "Re-check that the file still exists")
        dash.set_panel("setup", ["Property", "Value"],
                       self._file_detail_rows(payload, objects))
        dash.set_panel("columns", [], [], visible=False)
        dash.set_tables([], removable=False)
        dash.set_tables_tab_visible(False)
        dash.set_panel("usedby", ["Query Object", "Kind", "Source", "Fields"],
                       self._source_query_rows(objects))
        self._set_canvas_title(f"Data Sources: {label}" if label else "Data Sources")

    @staticmethod
    def _safe_dsn_details(dsn: str) -> dict:
        if not dsn:
            return {"__error__": "no dsn"}
        try:
            details = dict(get_dsn_details(dsn) or {})
        except Exception as exc:
            return {"__error__": str(exc)}
        return details or {"__error__": "not found"}

    # ── Data Source dashboard actions ─────────────────────────────────
