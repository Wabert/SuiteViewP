"""QueryObject Viewer ObjectActionsMixin methods."""
from __future__ import annotations

import os
from datetime import datetime
from pathlib import Path

from PyQt6.QtWidgets import (
    QApplication,
    QFileDialog,
    QInputDialog,
    QMessageBox,
    QTableWidget,
    QTableWidgetItem,
)

from suiteview.audit import qdef_store, query_object_store
from suiteview.audit.adhoc_source_intake import (
    promote_adhoc_source,
    query_object_from_file,
)
from suiteview.audit.dataforge import dataforge_store
from suiteview.audit.query_object import (
    OBJECT_KIND_ADHOC_SOURCE,
    OBJECT_KIND_CYBERLIFE,
    OBJECT_KIND_EXECUTABLE,
    OBJECT_KIND_MANUAL_SQL,
    OBJECT_KIND_VISUAL,
    QueryObject,
)
from suiteview.audit.query_object_viewer.common import (
    _SENSITIVE_ODBC_KEYS,
    _dataforge_display_name,
    _dataforge_info,
    _display_dsn_for_definition,
    _display_dsn_for_object,
    _kind_label,
    logger,
)
from suiteview.audit.query_organizer import get_query_organizer
from suiteview.core.app_launcher import AppLauncherError, launch_app
from suiteview.core.access_control import guard_app_access
from suiteview.core.odbc_utils import UNKNOWN, detect_dialect, get_dsn_details
from suiteview.ui.access_control import requires_app_access

from .dialogs import FileObjectPreviewDialog


class QueryObjectViewerObjectActionsMixin:
    @staticmethod
    def _objects_from_payload(payload: dict) -> list[QueryObject]:
        objects: list[QueryObject] = []
        for object_id in payload.get("object_ids", []) or []:
            obj = query_object_store.load_object_by_id(object_id)
            if obj is not None:
                objects.append(obj)
        return sorted(objects, key=lambda item: item.name.lower())

    @staticmethod
    def _source_query_rows(objects: list[QueryObject]) -> list[list[object]]:
        return [[obj.name, _kind_label(obj.kind), obj.source_design or obj.kind, len(obj.fields)]
                for obj in objects]

    @staticmethod
    def _odbc_detail_rows(dsn: str) -> list[list[object]]:
        try:
            details = get_dsn_details(dsn)
        except Exception as exc:
            details = {"DSN": dsn, "Error": str(exc)}
        details = dict(details or {})
        details.setdefault("DSN", dsn)
        details["Dialect"] = detect_dialect(dsn) if dsn else UNKNOWN

        priority = [
            "DSN", "Scope", "Driver", "Description", "Server", "Database",
            "Host", "Port", "Port Number", "Subsystem", "Dialect", "Error",
        ]
        keys: list[str] = []
        for key in priority:
            if key in details and key not in keys:
                keys.append(key)
        keys.extend(sorted(key for key in details if key not in keys))

        rows: list[list[object]] = []
        for key in keys:
            value = details.get(key, "")
            if value in (None, ""):
                continue
            display_value = "(hidden)" if key.strip().lower() in _SENSITIVE_ODBC_KEYS else value
            rows.append([key, display_value])
        return rows

    @staticmethod
    def _file_detail_rows(payload: dict, objects: list[QueryObject]) -> list[list[object]]:
        path = str(payload.get("path", "")).strip()
        metadata = dict(payload.get("metadata", {}) or {})
        source_type = str(payload.get("source_type", "")).strip()
        rows: list[list[object]] = [
            ["File Name", payload.get("label", "")],
            ["Full Path", path or "(not saved)"],
            ["Folder", str(Path(path).parent) if path else ""],
            ["Source Type", source_type or "File"],
            ["Query Objects", len(objects)],
        ]
        for key in sorted(metadata):
            if key == "path":
                continue
            rows.append([key, metadata[key]])
        return rows

    @staticmethod
    def _definition_source_label(definition: dict, fallback: str) -> str:
        config = definition.get("config", {}) if isinstance(definition, dict) else {}
        dataforge = config.get("dataforge", {}) if isinstance(config, dict) else {}
        return str(dataforge.get("source_name", "")).strip() or fallback

    def _query_objects_for_forge(self, forge_name: str) -> list[QueryObject]:
        objects = []
        for obj in query_object_store.list_objects():
            info = _dataforge_info(obj)
            if info is not None and info[0] == forge_name:
                objects.append(obj)
        return sorted(objects, key=lambda item: item.name.lower())

    def _forge_source_rows(self, forge, forge_objects: list[QueryObject]) -> list[list[object]]:
        rows: list[list[object]] = []
        seen = set()
        objects_by_name = {obj.name: obj for obj in forge_objects}
        if forge is not None:
            for source in forge.sources:
                definition = source.definition or {}
                copy_name = str(definition.get("name", "")).strip() or source.query_name
                source_label = self._definition_source_label(definition, source.query_name)
                fields = definition.get("fields") or []
                result_columns = definition.get("result_columns") or []
                column_count = len(fields) or len(result_columns)
                snapshot = "Stale" if source.snapshot.stale else source.snapshot.created_at or "Not refreshed"
                dsn_label = _display_dsn_for_definition(definition)
                source_object = objects_by_name.get(copy_name) or objects_by_name.get(source.query_name)
                if source_object is not None and not dsn_label:
                    dsn_label = _display_dsn_for_object(source_object)
                rows.append([
                    source_label,
                    copy_name,
                    _kind_label(str(definition.get("kind", "executable_query"))),
                    dsn_label,
                    column_count,
                    snapshot,
                    source.snapshot.row_count or "",
                ])
                seen.add(copy_name)
        for obj in forge_objects:
            if obj.name in seen:
                continue
            info = _dataforge_info(obj)
            rows.append([
                info[1] if info else obj.name,
                obj.name,
                _kind_label(obj.kind),
                _display_dsn_for_object(obj),
                len(obj.fields),
                "",
                "",
            ])
        return rows

    def _forge_field_rows(self, forge, forge_objects: list[QueryObject]) -> tuple[list[list[object]], list[list[object]]]:
        display_state = (forge.config or {}).get("display_tab", {}) if forge is not None else {}
        selected = set(display_state.get("selected", []))
        display_all = display_state.get("display_all", True)
        output_rows: list[list[object]] = []
        all_rows: list[list[object]] = []

        def add_field(field_name: str, data_type: str, role: str, source: str, display_name: str = ""):
            all_rows.append([field_name, data_type, role, source])
            if display_all or not selected or field_name in selected or f"{source}.{field_name}" in selected:
                if role in {"", "output"}:
                    output_rows.append([field_name, display_name or field_name, source, data_type])

        for obj in forge_objects:
            info = _dataforge_info(obj)
            source_label = info[1] if info else obj.name
            for field in obj.fields:
                add_field(field.name, field.data_type, field.role, source_label, field.display_name)

        if forge is not None and not all_rows:
            for source in forge.sources:
                definition = source.definition or {}
                source_label = self._definition_source_label(definition, source.query_name)
                column_types = definition.get("column_types", {}) or {}
                for field_name in definition.get("result_columns", []) or []:
                    add_field(field_name, column_types.get(field_name, ""), "output", source_label)
        return output_rows, all_rows

    @staticmethod
    def _forge_filter_rows(forge) -> list[list[object]]:
        if forge is None:
            return []
        rows: list[list[object]] = []
        modes = ["contains", "regex", "combo", "list", "range"]
        for tab in (forge.config or {}).get("filter_tabs", []) or []:
            tab_name = tab.get("tab_name", "Filter")
            fields = (tab.get("grid", {}) or {}).get("fields", {}) or {}
            for field_key, state in fields.items():
                mode_idx = int(state.get("mode", 0) or 0)
                mode = modes[mode_idx] if 0 <= mode_idx < len(modes) else str(mode_idx)
                if mode == "range":
                    value = f"{state.get('val', '')} to {state.get('hi', '')}".strip()
                elif mode == "list":
                    value = ", ".join(str(v) for v in state.get("list_selected", []))
                else:
                    value = state.get("val", "")
                rows.append([tab_name, field_key, mode, value])
        return rows

    @staticmethod
    def _forge_join_rows(forge) -> list[list[object]]:
        if forge is None:
            return []
        joins_state = (forge.config or {}).get("joins_tab", {}) or {}
        joins = joins_state.get("joins", []) or []
        rows: list[list[object]] = []
        for join in joins:
            keys = join.get("keys", []) or []
            left_fields = [key.get("left_field", "") for key in keys]
            right_fields = [key.get("right_field", "") for key in keys]
            rows.append([
                join.get("left_source", ""),
                ", ".join(left_fields),
                join.get("right_source", ""),
                ", ".join(right_fields),
                join.get("how", "inner"),
            ])
        for join in (forge.config or {}).get("joins", []) or []:
            rows.append([
                join.get("left_source", ""),
                ", ".join(join.get("left_keys", [])),
                join.get("right_source", ""),
                ", ".join(join.get("right_keys", [])),
                join.get("how", "inner"),
            ])
        return rows

    @staticmethod
    def _forge_sql_text(forge, forge_objects: list[QueryObject]) -> str:
        chunks: list[str] = []
        if forge is not None:
            for source in forge.sources:
                definition = source.definition or {}
                sql = str(definition.get("sql", "")).strip()
                if sql:
                    label = definition.get("name", source.query_name)
                    chunks.append(f"-- Source: {label}\n{sql}")
        for obj in forge_objects:
            if obj.sql.strip() and all(f"-- Source: {obj.name}\n" not in chunk for chunk in chunks):
                chunks.append(f"-- Source: {obj.name}\n{obj.sql.strip()}")
        return "\n\n".join(chunks)

    def _populate_role_table(self, table: QTableWidget, obj: QueryObject, roles: set[str]):
        fields = [field for field in obj.fields if field.role in roles]
        table.setRowCount(len(fields))
        for row, field in enumerate(fields):
            values = [field.name, field.data_type, field.display_name, field.source]
            for col, value in enumerate(values):
                table.setItem(row, col, QTableWidgetItem(str(value)))
        table.resizeColumnsToContents()
        table.setColumnWidth(0, max(table.columnWidth(0), 180))
        table.setColumnWidth(1, max(table.columnWidth(1), 110))

    def _on_open_source_folder(self) -> None:
        path_text = self._current_source_path.strip()
        if not path_text:
            return
        path = Path(path_text)
        folder = path.parent if path.suffix else path
        folder_text = str(folder)
        if self._open_folder_in_suiteview_file_nav(folder_text):
            return
        try:
            os.startfile(folder_text)
        except OSError as exc:
            QMessageBox.warning(self, "Open Folder Failed", str(exc))

    @requires_app_access("FILENAV")
    def _open_folder_in_suiteview_file_nav(self, folder: str) -> bool:
        launcher = self._find_file_nav_launcher()
        if launcher is not None:
            if hasattr(launcher, "_open_file_nav_at"):
                launcher._open_file_nav_at(folder)
                return True
            if hasattr(launcher, "_open_file_nav"):
                launcher._open_file_nav()
                file_nav = getattr(launcher, "file_nav_window", None)
                if file_nav is not None and hasattr(file_nav, "add_new_tab"):
                    file_nav.add_new_tab(path=folder)
                    return True
        existing = self._find_existing_file_nav_window()
        if existing is not None:
            existing.show()
            existing.raise_()
            existing.activateWindow()
            existing.add_new_tab(path=folder)
            return True
        if self._file_nav_window is not None:
            try:
                _ = self._file_nav_window.isVisible()
            except RuntimeError:
                self._file_nav_window = None
        if self._file_nav_window is None:
            try:
                self._file_nav_window = launch_app("FILENAV", parent_bar=None)
            except AppLauncherError:
                logger.warning("No FileNav launcher registered")
                return False
            except Exception:
                logger.exception("Failed to open standalone File Nav")
                return False
        self._file_nav_window.show()
        self._file_nav_window.raise_()
        self._file_nav_window.activateWindow()
        if hasattr(self._file_nav_window, "add_new_tab"):
            self._file_nav_window.add_new_tab(path=folder)
            return True
        return False

    def _find_file_nav_launcher(self):
        current = self._audit_parent
        seen: set[int] = set()
        while current is not None and id(current) not in seen:
            seen.add(id(current))
            if hasattr(current, "_open_file_nav_at") or hasattr(current, "_open_file_nav"):
                return current
            parent_bar = getattr(current, "_parent_bar", None) or getattr(current, "parent_bar", None)
            if parent_bar is not None and id(parent_bar) not in seen:
                current = parent_bar
                continue
            current = current.parent() if hasattr(current, "parent") else None
        for window in QApplication.topLevelWidgets():
            try:
                _ = window.isVisible()
            except RuntimeError:
                continue
            if hasattr(window, "_open_file_nav_at") or hasattr(window, "_open_file_nav"):
                return window
        return None

    def _find_existing_file_nav_window(self):
        for window in QApplication.topLevelWidgets():
            try:
                _ = window.isVisible()
            except RuntimeError:
                continue
            if window is self:
                continue
            if window.__class__.__name__ == "FileNavWindow" and hasattr(window, "add_new_tab"):
                return window
            file_nav = getattr(window, "file_nav_window", None)
            if file_nav is not None and hasattr(file_nav, "add_new_tab"):
                return file_nav
        return None

    def _on_save_changes(self):
        if self._current is None or self._loading_detail:
            return
        old_name = self._current.name
        new_name = self.edit_name.text().strip()
        if not new_name:
            QMessageBox.warning(self, "Name Required", "Object name cannot be blank.")
            return
        # Duplicate names are legal now (ids disambiguate) — except visual
        # queries, whose designer snapshots are still name-keyed.
        if (new_name != old_name
                and self._current.kind == OBJECT_KIND_VISUAL
                and query_object_store.object_exists(new_name)):
            QMessageBox.warning(
                self,
                "Name Already Exists",
                f"A visual Query Object named \"{new_name}\" already exists.",
            )
            return

        updated_fields = []
        for row, field in enumerate(self._current.fields):
            role = self._normalize_role(self._table_text(self.tbl_fields, row, 2))
            if not role:
                QMessageBox.warning(
                    self,
                    "Invalid Field Role",
                    f"Role for \"{field.name}\" must be output, input, or join key.",
                )
                return
            field.data_type = self._table_text(self.tbl_fields, row, 1)
            field.role = role
            field.display_name = self._table_text(self.tbl_fields, row, 3) or field.name
            field.source = self._table_text(self.tbl_fields, row, 4)
            updated_fields.append(field)

        self._current.description = self.edit_description.text().strip()
        self._current.tags = [tag.strip() for tag in self.edit_tags.text().split(",") if tag.strip()]
        self._current.source_design = self.edit_origin.text().strip()
        self._current.sql = self.txt_sql.toPlainText().strip()
        self._current.fields = updated_fields
        self._current.updated_at = datetime.now()

        if new_name != old_name:
            # Rename across every store so it sticks (the SavedQuery design and
            # any old-name QDefinition would otherwise resurrect the old name).
            query_object_store.rename_object(self._current, new_name)
        else:
            query_object_store.save_object(self._current)
        self.refresh()
        QMessageBox.information(self, "Query Object Saved", f"Saved \"{new_name}\".")

    def _on_open_builder(self):
        if self._current_forge_name:
            self._open_dataforge_builder(self._current_forge_name)
            return
        if self._current is None:
            return
        self._open_query_object_builder(self._current.name)

    def _open_query_object_builder(self, object_name: str):
        parent = self._audit_window_for_builder()
        opener = getattr(parent, "open_query_object_in_builder", None)
        if opener is None:
            QMessageBox.information(
                self,
                "Builder Unavailable",
                "Could not open the Audit builder for this Query Object.",
            )
            return
        opener(object_name)

    @requires_app_access("QUERY")
    def _open_query_object_in_new_builder(self, object_name: str):
        """Open a Query Object in a brand-new builder window.

        Unlike ``_open_query_object_builder`` this never reuses an existing
        Audit builder — it always spins up a fresh window so several query
        builders can be open side by side.
        """
        try:
            # Deferred to avoid an AuditWindow <-> QueryObjectViewer import cycle.
            from suiteview.audit.main import create_audit_window
            window = create_audit_window()
        except Exception:
            logger.exception("Failed to create AuditWindow for new builder window")
            QMessageBox.information(
                self,
                "Builder Unavailable",
                "Could not open a new Audit builder window.",
            )
            return
        self._audit_builder_windows.append(window)
        window.destroyed.connect(lambda _=None, win=window: self._forget_audit_window(win))
        opener = getattr(window, "open_query_object_in_builder", None)
        if opener is None:
            QMessageBox.information(
                self,
                "Builder Unavailable",
                "Could not open the Audit builder for this Query Object.",
            )
            return
        opener(object_name)
        try:
            window.raise_()
            window.activateWindow()
        except RuntimeError:
            logger.debug("Audit builder window disappeared before activation", exc_info=True)

    def _on_add_file_source(self):
        """Add a File Source — open the editable dashboard in 'new' mode.

        Same screen used to view/edit; the first file added sets the format."""
        self._offer_to_save_file_source_edits()
        # Clear the tree selection first: that routes the canvas to "empty" via
        # the selection handler, so set our new-source state *after* it.
        self.source_tree.setCurrentItem(None)
        self._current = None
        self._current_forge_name = ""
        self._current_source_kind = "file_data_source"
        self._current_source_payload = {}
        self._current_file_source = None
        self._current_data_source = None
        self._current_source_path = ""
        self._file_source_is_new = True
        self._browser_canvas_stack.setCurrentWidget(self._source_dashboard)
        self._render_file_source(None, {}, new=True)

    def _open_dataforge_builder(self, forge_name: str):
        parent = self._audit_window_for_builder()
        opener = getattr(parent, "open_dataforge_in_builder", None)
        if opener is None:
            QMessageBox.information(
                self,
                "Builder Unavailable",
                "Could not open the Audit DataForge builder.",
            )
            return
        opener(forge_name)

    @requires_app_access("QUERY")
    def _audit_window_for_builder(self):
        for candidate in (self._audit_parent, self.parent(), self._find_audit_window()):
            if not self._is_audit_window(candidate):
                continue
            if self._show_audit_window(candidate):
                return candidate
        try:
            # Deferred to avoid an AuditWindow <-> QueryObjectViewer import cycle.
            from suiteview.audit.main import create_audit_window
            window = create_audit_window()
        except Exception:
            logger.exception("Failed to create AuditWindow for QueryObject builder")
            return None
        self._audit_parent = window
        self._audit_builder_windows.append(window)
        window.destroyed.connect(lambda _=None, win=window: self._forget_audit_window(win))
        return window

    @staticmethod
    def _is_audit_window(candidate) -> bool:
        if candidate is None:
            return False
        try:
            return (
                hasattr(candidate, "open_query_object_in_builder")
                or hasattr(candidate, "open_dataforge_in_builder")
            )
        except RuntimeError:
            return False

    def _show_audit_window(self, window) -> bool:
        guard_app_access("QUERY")
        try:
            restore = getattr(window, "restore_window", None)
            if callable(restore):
                restore()
            else:
                if not window.isVisible():
                    window.show()
                if window.isMinimized():
                    window.showNormal()
                window.raise_()
                window.activateWindow()
            return True
        except RuntimeError:
            if self._audit_parent is window:
                self._audit_parent = None
            return False

    def _forget_audit_window(self, window):
        if window in self._audit_builder_windows:
            self._audit_builder_windows.remove(window)
        if self._audit_parent is window:
            self._audit_parent = None

    @staticmethod
    def _find_audit_window():
        app = QApplication.instance()
        if app is None:
            return None
        for widget in app.topLevelWidgets():
            if hasattr(widget, "open_query_object_in_builder"):
                return widget
        return None

    @staticmethod
    def _table_text(table: QTableWidget, row: int, col: int) -> str:
        item = table.item(row, col)
        return item.text().strip() if item is not None else ""

    @staticmethod
    def _normalize_role(value: str) -> str:
        normalized = value.strip().lower().replace(" ", "_").replace("-", "_")
        aliases = {
            "": "output",
            "output": "output",
            "select": "output",
            "input": "input",
            "where": "input",
            "filter": "input",
            "join": "join_key",
            "join_key": "join_key",
            "joinkey": "join_key",
            "key": "join_key",
        }
        return aliases.get(normalized, "")

    def _on_delete(self):
        if self._current_forge_name:
            self._delete_dataforge(self._current_forge_name)
            return
        if self._current is None:
            return
        name = self._current.name
        reply = QMessageBox.question(
            self,
            "Delete Query Object",
            f"Delete query object \"{name}\"?\n\nThis does not delete the original SavedQuery or QDefinition.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return
        query_object_store.delete_object_by_id(self._current.id)
        organizer = get_query_organizer()
        organizer.remove_query(self._current.id)
        organizer.save()
        self.refresh()
        self._clear_detail()

    def _delete_dataforge(self, forge_name: str):

        display_name = _dataforge_display_name(forge_name)
        forge_objects = self._query_objects_for_forge(forge_name)
        reply = QMessageBox.question(
            self,
            "Delete DataForge",
            f"Delete DataForge \"{display_name}\"?\n\n"
            "This deletes the saved forge, snapshots, and its DataForge query copies. "
            "Original query objects remain.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return
        self._delete_dataforge_records(forge_name, forge_objects)
        parent = self._audit_parent or self.parent() or self._find_audit_window()
        handler = getattr(parent, "_on_forge_deleted_from_group", None)
        if callable(handler):
            handler(forge_name)
        refresher = getattr(parent, "_refresh_picker_forge_list", None)
        if callable(refresher):
            refresher()
        self.refresh()
        self._clear_detail()

    @staticmethod
    def _delete_dataforge_records(forge_name: str, forge_objects: list[QueryObject]) -> None:

        dataforge_store.delete_forge(forge_name)
        for obj in forge_objects:
            try:
                qdef_store.delete_qdef(obj.name, forge_name=forge_name)
            except Exception:
                logger.exception("Failed to delete DataForge QDefinition: %s", obj.name)
            query_object_store.delete_object_by_id(obj.id)

    def _on_promote(self):
        if self._current is None:
            return
        name = self._current.name
        try:
            promote_adhoc_source(self._current)
            query_object_store.save_object(self._current)
        except Exception as exc:
            logger.exception("Ad hoc source promotion failed: %s", name)
            QMessageBox.warning(
                self,
                "Promotion Failed",
                f"Could not promote this object:\n\n{exc}",
            )
            return
        self.refresh()
        QMessageBox.information(
            self,
            "Object Promoted",
            f"Promoted \"{name}\" to registered metadata.",
        )

    def _on_preview_file(self):
        if self._current is None:
            return
        dlg = FileObjectPreviewDialog(self._current, self)
        dlg.exec()

    @staticmethod
    def _can_open_in_builder(obj: QueryObject) -> bool:
        if (obj.config or {}).get("dataforge") and obj.kind == OBJECT_KIND_EXECUTABLE:
            return True
        return obj.kind in {
            OBJECT_KIND_VISUAL,
            OBJECT_KIND_CYBERLIFE,
            OBJECT_KIND_MANUAL_SQL,
            OBJECT_KIND_ADHOC_SOURCE,
        }

    @staticmethod
    def _can_preview_object(obj: QueryObject) -> bool:
        if obj.kind == OBJECT_KIND_ADHOC_SOURCE:
            return True
        return bool(obj.sql.strip() and obj.dsn.strip())

    def _on_import_file(self):
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Import Ad Hoc Source",
            "",
            "Data Files (*.csv *.xlsx *.xlsm *.xls);;CSV Files (*.csv);;Excel Files (*.xlsx *.xlsm *.xls)",
        )
        if not path:
            return
        default_name = path.rsplit("/", 1)[-1].rsplit("\\", 1)[-1].rsplit(".", 1)[0]
        name, ok = QInputDialog.getText(
            self,
            "Ad Hoc Source Name",
            "Name:",
            text=default_name,
        )
        if not ok or not name.strip():
            return
        try:
            obj = query_object_from_file(path, name=name.strip())
            query_object_store.save_object(obj)
        except Exception as exc:
            logger.exception("Ad hoc source import failed: %s", path)
            QMessageBox.warning(
                self,
                "Import Failed",
                f"Could not import ad hoc source:\n\n{exc}",
            )
            return
        self.refresh()
        QMessageBox.information(
            self,
            "Source Imported",
            f"Imported \"{obj.name}\" with {len(obj.fields)} fields.",
        )
