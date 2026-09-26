"""QueryObject Viewer SourceActionsMixin methods."""
from __future__ import annotations

import os
from datetime import datetime
from pathlib import Path

from PyQt6.QtWidgets import (
    QDialog,
    QFileDialog,
    QInputDialog,
    QMessageBox,
    QTreeWidgetItem,
)

from suiteview.audit import data_source_store, file_query_runner, file_source_store
from suiteview.audit.adhoc_source_intake import fixed_width_spec
from suiteview.audit.data_source import KIND_ACCESS
from suiteview.audit.file_source import SOURCE_TYPE_EXCEL, SOURCE_TYPE_FIXED_WIDTH
from suiteview.audit.file_source_format_dialogs import (
    DialogCancelled,
    establish_source_from_first_file,
    prompt_format_spec_for_source,
)
from suiteview.audit.file_source_intake import (
    FileValidationError,
    add_member_file,
    apply_column_names,
    infer_file_source_from_file,
    parse_column_spec_text,
    validate_member_file,
)
from suiteview.audit.query_object_viewer.common import (
    _FILE_SOURCE_FILE_FILTER,
    _payload,
    logger,
)

from .dialogs import _RegisterAccessDialog, _RegisterOdbcDialog


class QueryObjectViewerSourceActionsMixin:
    def _on_source_test(self) -> None:
        """Re-evaluate the selected source's health (re-render its detail).

        ODBC sources do a *live* connection probe here (``probe=True``)."""
        payload = self._current_source_payload
        kind = self._current_source_kind
        if kind == "file_data_source":
            self._show_file_data_source_detail(payload)
        elif kind == "file_source":
            self._show_file_source_detail(payload)
        elif kind == "registered_odbc":
            self._show_registered_odbc_detail(payload, probe=True)
        elif kind == "access_source":
            self._show_access_source_detail(payload, probe=True)
        elif kind == "odbc_source":
            self._show_odbc_source_detail(payload, probe=True)

    def _on_source_register(self) -> None:
        """Promote a discovered DSN to a registered (named, pinned) source."""
        if self._current_source_kind != "odbc_source":
            return
        self._register_odbc_dsn(dsn=str(self._current_source_payload.get("dsn", "")))

    # ── Tables tab: preview / remove / per-file open-folder ────────────

    def _on_dashboard_preview(self, table_name: str, rows: int) -> None:
        """Preview N rows of the selected member table (File Sources only)."""
        if self._current_source_kind != "file_data_source" or self._current_file_source is None:
            return
        member = self._current_file_source.find_member_by_table(table_name)
        if member is None:
            return
        try:
            result = file_query_runner.run_sql(
                self._current_file_source, f'SELECT * FROM "{table_name}"',
                limit=rows, table_names=[table_name])
            self._source_dashboard.set_preview(result.dataframe)
        except Exception as exc:
            logger.warning("File Source preview failed for %s: %s", table_name, exc)
            self._source_dashboard.clear_preview()

    def _on_dashboard_remove_table(self, table_name: str) -> None:
        """Remove a member file (table) from a File Source."""
        if self._current_source_kind != "file_data_source" or self._current_file_source is None:
            return

        fds = self._current_file_source
        member = fds.find_member_by_table(table_name)
        if member is None:
            return
        # A *saved* source must keep at least one file — delete the source instead.
        # A *new* (unsaved) source may drop its last file, reverting to empty.
        if not self._file_source_is_new and len(fds.members) <= 1:
            QMessageBox.information(
                self, "Cannot Remove",
                "A File Source needs at least one file. Delete the whole source instead.")
            return
        reply = QMessageBox.question(
            self,
            "Remove Table",
            f"Remove table \"{table_name}\" ({Path(member.path).name}) from this "
            "File Source?\n\nThis removes the file from the source definition, "
            "not from disk.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return
        fds.members = [m for m in fds.members if m is not member]
        if self._file_source_is_new:
            # Stay in the in-memory draft; never touch the store until Save.
            if not fds.members:
                self._current_file_source = None
                self._render_file_source(None, self._current_source_payload, new=True)
            else:
                self._refresh_file_source_tables(fds)
                self._source_dashboard.set_dirty(True)
            return
        fds.updated_at = datetime.now()
        file_source_store.save_file_source(fds)
        self.refresh()
        self._select_file_source(fds.id)

    # ── File Source editing (the canonical add/edit/view screen) ───────

    def _on_source_save(self) -> None:
        """Persist the editable File Source draft shown in the dashboard."""
        if self._current_source_kind != "file_data_source":
            return
        fds = self._current_file_source
        dash = self._source_dashboard
        if fds is None or not fds.members:
            QMessageBox.information(self, "Add a File First",
                                   "Add at least one file before saving.")
            return
        name = dash.editable_name()
        if not name:
            QMessageBox.information(self, "Name Required",
                                   "Give the File Source a name before saving.")
            return

        draft_cols = dash.editable_columns()
        if len(draft_cols) == len(fds.columns):
            names = [c[0].strip() for c in draft_cols]
            if fds.source_type != SOURCE_TYPE_EXCEL and dash.names_editable:
                if any(not n for n in names):
                    QMessageBox.warning(self, "Invalid Column Names",
                                       "Column names cannot be blank.")
                    return
                if len({n.lower() for n in names}) != len(names):
                    QMessageBox.warning(self, "Invalid Column Names",
                                       "Column names must be unique.")
                    return
                try:
                    apply_column_names(fds, names)
                except ValueError as exc:
                    QMessageBox.warning(self, "Invalid Column Names", str(exc))
                    return
            for col, (_, data_type) in zip(fds.columns, draft_cols):
                col.data_type = data_type
        fds.name = name
        fds.description = dash.editable_description()
        fds.updated_at = datetime.now()
        file_source_store.save_file_source(fds)
        self._file_source_is_new = False
        dash.set_dirty(False)
        self.refresh()
        self._select_file_source(fds.id)

    def _on_edit_file_source_format(self) -> None:
        """Re-open the format/layout dialog and re-read the columns.

        Fixes a mis-detected text file (wrong delimiter, or it's really
        fixed-width) and lets fixed-width column definitions be changed after the
        fact. The schema is re-inferred from the first member; the change is
        staged (Save persists it)."""
        if self._current_source_kind != "file_data_source" or self._current_file_source is None:
            return
        fds = self._current_file_source
        if not fds.members:
            QMessageBox.information(self, "Add a File First",
                                   "Add a file before editing its format.")
            return

        try:
            new_spec = prompt_format_spec_for_source(self, fds)
        except DialogCancelled:
            return
        first = fds.members[0].path
        try:
            fresh = infer_file_source_from_file(first, name=fds.name, format_spec=new_spec)
        except Exception as exc:  # noqa: BLE001 — surface any read error
            QMessageBox.warning(self, "Could Not Apply Format", f"{exc}")
            return
        # Adopt the new format + columns; keep identity, name, description, members.
        fds.source_type = fresh.source_type
        fds.parse_spec = fresh.parse_spec
        fds.columns = fresh.columns
        # Warn if any existing member no longer matches the new format.
        mismatched = []
        for member in fds.members:
            try:
                if validate_member_file(fds, member.path):
                    mismatched.append(Path(member.path).name)
            except Exception:  # noqa: BLE001 — unreadable under the new format
                mismatched.append(Path(member.path).name)
        self._render_file_source(
            fds, self._current_source_payload, new=self._file_source_is_new)
        self._source_dashboard.set_dirty(True)
        self._source_dashboard.tabs.setCurrentIndex(0)  # show the re-read columns
        if mismatched:
            QMessageBox.warning(
                self, "Format Changed",
                "These files no longer match the new format and may fail to "
                "query:\n• " + "\n• ".join(mismatched))

    def _on_bulk_edit_columns(self) -> None:
        """Multi-line column entry: a list of names, or name,start,width rows.

        A names list renames the draft columns in place (Save persists). A
        name,start,width block redefines a fixed-width layout — the format is
        re-applied and the columns re-read, mirroring Edit Format."""
        if (self._current_source_kind != "file_data_source"
                or self._current_file_source is None):
            return

        fds = self._current_file_source
        if fds.source_type == SOURCE_TYPE_EXCEL:
            QMessageBox.information(
                self, "Excel Columns",
                "Excel columns follow the sheet's header row and can't be "
                "entered here.")
            return
        if not fds.members:
            QMessageBox.information(self, "Add a File First",
                                   "Add a file before entering its columns.")
            return

        prefill = self._column_spec_prefill(fds)
        message = (
            "Enter one column name per line, or name,start,width for a "
            "fixed-width layout.\n\nNames:\n  Policy\n  Company\n\n"
            "Fixed width (name,start,width):\n  Policy,1,10\n  Company,11,2")
        text, ok = QInputDialog.getMultiLineText(
            self, "Enter Columns", message, prefill)
        if not ok:
            return
        try:
            mode, parsed = parse_column_spec_text(text)
        except ValueError as exc:
            QMessageBox.warning(self, "Invalid Columns", str(exc))
            return
        if mode == "fixed_width":
            self._apply_fixed_width_columns(fds, parsed)
        else:
            self._apply_bulk_column_names(fds, parsed)

    @staticmethod
    def _column_spec_prefill(fds) -> str:
        """Current columns as editable text for the multi-line box."""
        if fds.source_type == SOURCE_TYPE_FIXED_WIDTH:
            specs = fds.parse_spec.get("columns", [])
            if specs:
                return "\n".join(
                    f"{s.get('name', '')},{s.get('start', '')},{s.get('width', '')}"
                    for s in specs)
        return "\n".join(c.name for c in fds.columns)

    def _apply_bulk_column_names(self, fds, names: list) -> None:
        """Fill the editable columns table from a pasted name list.

        Count must match the current columns; types are preserved and nothing
        persists until Save."""
        dash = self._source_dashboard
        if not dash.names_editable:
            QMessageBox.information(
                self, "Names Fixed",
                "This source's column names follow its file header and can't be "
                "renamed here.")
            return
        draft = dash.editable_columns()
        if len(names) != len(draft):
            QMessageBox.warning(
                self, "Column Count Mismatch",
                f"The source has {len(draft)} columns but you entered "
                f"{len(names)} names.\n\nEnter exactly {len(draft)} names, or use "
                "name,start,width on every line to redefine a fixed-width layout.")
            return
        dash.set_editable_columns(
            [(name, data_type) for name, (_, data_type) in zip(names, draft)],
            names_editable=True)
        dash.set_dirty(True)
        dash.tabs.setCurrentIndex(0)

    def _apply_fixed_width_columns(self, fds, columns: list) -> None:
        """Re-apply a fixed-width layout from pasted name,start,width rows.

        Reuses the format re-inference path so columns are re-read from the first
        member; the change is staged (Save persists)."""

        skip_rows = int(fds.parse_spec.get("skip_rows", 0) or 0)
        spec = fixed_width_spec(columns, skip_rows=skip_rows)
        first = fds.members[0].path
        try:
            fresh = infer_file_source_from_file(first, name=fds.name, format_spec=spec)
        except Exception as exc:  # noqa: BLE001 — surface any read error
            QMessageBox.warning(self, "Could Not Apply Columns", f"{exc}")
            return
        fds.source_type = fresh.source_type
        fds.parse_spec = fresh.parse_spec
        fds.columns = fresh.columns
        mismatched = []
        for member in fds.members:
            try:
                if validate_member_file(fds, member.path):
                    mismatched.append(Path(member.path).name)
            except Exception:  # noqa: BLE001 — unreadable under the new format
                mismatched.append(Path(member.path).name)
        self._render_file_source(
            fds, self._current_source_payload, new=self._file_source_is_new)
        self._source_dashboard.set_dirty(True)
        self._source_dashboard.tabs.setCurrentIndex(0)
        if mismatched:
            QMessageBox.warning(
                self, "Columns Changed",
                "These files no longer match the new layout and may fail to "
                "query:\n• " + "\n• ".join(mismatched))

    def _on_pick_files_for_source(self) -> None:
        """Add File(s)… button — pick member files for the current File Source."""
        if self._current_source_kind != "file_data_source":
            return
        paths, _ = QFileDialog.getOpenFileNames(
            self, "Add File(s) to Source", "", _FILE_SOURCE_FILE_FILTER)
        if paths:
            self._on_add_files_to_source(paths)

    def _on_add_files_to_source(self, paths: list) -> None:
        """Add member files (button or drag-drop). The first file of a new source
        establishes its format; later files are validated against it. Nothing is
        persisted until Save."""
        if self._current_source_kind != "file_data_source":
            return

        fds = self._current_file_source
        established_new = False
        errors: list[str] = []
        added = 0
        for path in paths:
            if fds is None:
                try:
                    fds = establish_source_from_first_file(
                        self, path, self._source_dashboard.editable_name())
                except DialogCancelled:
                    break
                if fds is None:
                    continue  # unreadable file; a warning was already shown
                self._current_file_source = fds
                established_new = True
                added += 1
            else:
                try:
                    add_member_file(fds, path)
                    added += 1
                except FileValidationError as exc:
                    errors.append(f"• {Path(path).name}: {exc}")
        if fds is None:
            return
        if established_new:
            self._render_file_source(
                fds, self._current_source_payload, new=self._file_source_is_new)
            # First file just set the format + columns — show them on Overview.
            self._source_dashboard.tabs.setCurrentIndex(0)
        else:
            self._refresh_file_source_tables(fds)
        if added:
            self._source_dashboard.set_dirty(True)
        if errors:
            QMessageBox.warning(self, "Some files were not added", "\n\n".join(errors))

    def _select_file_source(self, file_source_id: str) -> None:
        """Select the tree node for a File Source so its dashboard re-renders."""
        if not file_source_id or not hasattr(self, "source_tree"):
            return

        def _find(item: QTreeWidgetItem):
            if _payload(item).get("file_source_id") == file_source_id:
                return item
            for index in range(item.childCount()):
                found = _find(item.child(index))
                if found is not None:
                    return found
            return None

        for i in range(self.source_tree.topLevelItemCount()):
            node = _find(self.source_tree.topLevelItem(i))
            if node is not None:
                self.source_tree.setCurrentItem(node)
                return

    def _open_path_folder(self, path: str) -> None:
        """Open the folder containing a specific file (resolves multi-folder sources)."""
        folder = str(Path(path).parent) if path else ""
        if not folder:
            return
        if self._open_folder_in_suiteview_file_nav(folder):
            return
        try:
            os.startfile(folder)
        except OSError as exc:
            QMessageBox.warning(self, "Open Folder Failed", str(exc))

    def _on_add_odbc_source(self) -> None:
        """Add Data Source → ODBC DSN: register a new ODBC source."""
        self._register_odbc_dsn()

    def _on_add_access_source(self) -> None:
        """Add Data Source → MS Access: register a new Access file source."""
        self._register_access_file()

    def _register_odbc_dsn(self, *, dsn: str = "", existing=None) -> None:

        dialog = _RegisterOdbcDialog(self, dsn=dsn, existing=existing)
        if dialog.exec() != QDialog.DialogCode.Accepted or dialog.result_source is None:
            return
        data_source_store.save_data_source(dialog.result_source)
        self.refresh()
        self._select_registered_source(dialog.result_source.id)

    def _register_access_file(self, *, path: str = "", existing=None) -> None:

        dialog = _RegisterAccessDialog(self, path=path, existing=existing)
        if dialog.exec() != QDialog.DialogCode.Accepted or dialog.result_source is None:
            return
        data_source_store.save_data_source(dialog.result_source)
        self.refresh()
        self._select_registered_source(dialog.result_source.id)

    def _select_registered_source(self, data_source_id: str) -> None:
        """After save, select the source's tree node so its dashboard shows."""
        if not hasattr(self, "source_tree"):
            return

        def _find(item: QTreeWidgetItem):
            if _payload(item).get("data_source_id") == data_source_id:
                return item
            for index in range(item.childCount()):
                found = _find(item.child(index))
                if found is not None:
                    return found
            return None

        for i in range(self.source_tree.topLevelItemCount()):
            node = _find(self.source_tree.topLevelItem(i))
            if node is not None:
                self.source_tree.setCurrentItem(node)
                return

    def _on_source_edit_setup(self) -> None:
        # File Sources are edited in place on the dashboard (no "Edit Setup"
        # button is shown for them). ODBC / Access edit via their dialog.
        if self._current_source_kind == "registered_odbc" and self._current_data_source is not None:
            self._register_odbc_dsn(existing=self._current_data_source)
        elif self._current_source_kind == "access_source" and self._current_data_source is not None:
            self._register_access_file(existing=self._current_data_source)

    def _on_source_new_query(self, mode: str) -> None:
        if self._current_source_kind != "file_data_source" or self._current_file_source is None:
            return
        parent = self._audit_window_for_builder()
        opener = getattr(parent, "new_query_on_file_source", None)
        if opener is None:
            QMessageBox.information(
                self, "Builder Unavailable",
                "Could not open a query on this File Source.")
            return
        opener(self._current_file_source.id, mode=mode)

    def _on_source_delete(self) -> None:
        if (self._current_source_kind in {"registered_odbc", "access_source"}
                and self._current_data_source is not None):
            self._delete_registered_source()
            return
        if self._current_source_kind != "file_data_source" or self._current_file_source is None:
            return

        fds = self._current_file_source
        objects = self._objects_from_payload(self._current_source_payload)
        extra = (f"\n\n{len(objects)} query object(s) target it and will stop "
                 "resolving.") if objects else ""
        reply = QMessageBox.question(
            self,
            "Delete File Source",
            f"Delete File Source \"{fds.name}\"?{extra}\n\n"
            "This removes the source definition, not the underlying files.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return
        file_source_store.delete_file_source_by_id(fds.id)
        self.refresh()
        self._reset_current_source()
        self._source_dashboard.show_empty("Select a data source")

    def _delete_registered_source(self) -> None:

        ds = self._current_data_source
        if ds.kind == KIND_ACCESS:
            target, underlying = ds.path, "Access file"
        else:
            target, underlying = f"DSN {ds.dsn}", "Windows DSN"
        reply = QMessageBox.question(
            self,
            "Unregister Data Source",
            f"Unregister data source \"{ds.name}\" ({target})?\n\n"
            f"This removes the registration only — the {underlying} and any "
            "queries that use it are untouched.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return
        data_source_store.delete_data_source_by_id(ds.id)
        self.refresh()
        self._reset_current_source()
        self._source_dashboard.show_empty("Select a data source")

    def _set_editor_read_only(self, read_only: bool) -> None:
        for edit in (self.edit_name, self.edit_origin, self.edit_tags, self.edit_description):
            edit.setReadOnly(read_only)
