"""
File Source editor — define a flat-file *data source* (not a query).

Replaces the old single-file ``CsvExcelObjectEditor``: you set the format +
column schema once (established by the first file), then manage a LIST of member
files that all share that type. Files can be added via the button or by
**dragging them onto the Member Files list** — each is validated against the
source's format/schema before being added. Saving writes a ``FileDataSource``
(via ``file_source_store``), which the query builders target like a DSN.

Querying lives in the Visual/Manual builders, not here — this editor's job is to
*define the source*. A small per-file preview is offered for a sanity check.
"""
from __future__ import annotations

from datetime import datetime
from pathlib import Path

import pandas as pd
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QFont
from PyQt6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QDialog,
    QFileDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QInputDialog,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QSplitter,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from suiteview.audit import file_query_runner, file_source_store
from suiteview.audit.adhoc_source_intake import delimited_text_spec, fixed_width_spec
from suiteview.audit.file_source import (
    SOURCE_TYPE_CSV,
    SOURCE_TYPE_EXCEL,
    SOURCE_TYPE_FIXED_WIDTH,
    FileColumn,
    FileDataSource,
    datasource_label,
)
from suiteview.audit.file_source_intake import (
    FileValidationError,
    add_member_file,
    infer_file_source_from_file,
)
from suiteview.ui.widgets.filter_table_view import FilterTableView
from suiteview.ui.widgets.frameless_window import FramelessWindowBase

# Declarative column types the user can assign (DuckDB infers actual types at
# query time; this is the schema label shown in pickers and the source dashboard).
_DATA_TYPES = ["TEXT", "INTEGER", "BIGINT", "DOUBLE", "DECIMAL", "DATE",
               "TIMESTAMP", "BOOLEAN"]

_FONT = QFont("Segoe UI", 9)
_FONT_BOLD = QFont("Segoe UI", 9, QFont.Weight.Bold)

_FILE_FILTER = (
    "Data Files (*.csv *.txt *.dat *.psv *.tsv *.xlsx *.xlsm *.xls);;"
    "Text Files (*.csv *.txt *.dat *.psv *.tsv);;"
    "Excel Files (*.xlsx *.xlsm *.xls);;All Files (*.*)"
)

_SAVE_BTN_STYLE = (
    "QPushButton { background-color: #0A2A5C; color: #D4AF37;"
    " border: 2px solid #D4AF37; border-radius: 3px;"
    " padding: 1px 4px; font-size: 8pt; font-weight: bold; }"
    "QPushButton:hover { background-color: #123C69; color: #F4D03F; }"
    "QPushButton:disabled { background-color: #6B7A90; color: #E6D8A6;"
    " border-color: #C9B46B; }"
)

_ACTION_BTN_STYLE = (
    "QPushButton { background-color: #1E5BA8; color: white;"
    " border: 1px solid #14407A; border-radius: 3px; padding: 2px 10px; }"
    "QPushButton:hover { background-color: #2A6BC4; }"
)


class FileDropList(QListWidget):
    """A list that accepts OS file drops, emitting their local paths."""

    files_dropped = pyqtSignal(list)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAcceptDrops(True)
        self.setDragDropMode(QAbstractItemView.DragDropMode.DropOnly)

    def dragEnterEvent(self, event):  # noqa: N802 (Qt signature)
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
        else:
            super().dragEnterEvent(event)

    def dragMoveEvent(self, event):  # noqa: N802
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
        else:
            super().dragMoveEvent(event)

    def dropEvent(self, event):  # noqa: N802
        paths = [u.toLocalFile() for u in event.mimeData().urls() if u.isLocalFile()]
        if paths:
            event.acceptProposedAction()
            self.files_dropped.emit(paths)
        else:
            super().dropEvent(event)


class FileSourceEditor(QWidget):
    """Define and save a FileDataSource (format + schema + member files)."""

    saved = pyqtSignal(str)  # file source name
    query_requested = pyqtSignal(str)  # file source id — open a Manual SQL query on it
    visual_query_requested = pyqtSignal(str)  # file source id — open a Visual query on it

    def __init__(self, parent=None):
        super().__init__(parent)
        self._fds: FileDataSource | None = None
        self._original_name = ""
        self._loading_columns = False
        self._build_ui()
        self._refresh_all()

    # ── UI ─────────────────────────────────────────────────────────────────

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(4, 4, 4, 4)
        root.setSpacing(6)
        self.setStyleSheet(
            "QWidget { background-color: #F6F8FB; color: #111; }"
            "QLineEdit { background: white; border: 1px solid #9FB4CC; padding: 4px; }"
            "QListWidget { background: white; border: 1px solid #9FB4CC; }"
            "QListWidget::item { padding: 0px 3px; }"
            "QListWidget::item:selected { background: #DCEAFB; color: #0D3A7A; }"
            "QTableWidget { background: white; border: 1px solid #9FB4CC;"
            " gridline-color: #EAEFF6; }"
            "QGroupBox { border: 1px solid #AFC3DA; margin-top: 8px;"
            " padding: 8px 6px 6px 6px; font-weight: bold; }"
            "QGroupBox::title { subcontrol-origin: margin; left: 8px; padding: 0 4px; }"
        )

        header = QHBoxLayout()
        self.lbl_heading = QLabel("File Source: (new)")
        self.lbl_heading.setFont(QFont("Segoe UI", 12, QFont.Weight.Bold))
        self.lbl_heading.setStyleSheet("color: #1E5BA8;")
        header.addWidget(self.lbl_heading)
        header.addStretch()
        self.lbl_status = QLabel("Add a file to set the format, then add more of the same type")
        self.lbl_status.setFont(_FONT)
        self.lbl_status.setStyleSheet("color: #4B5563;")
        header.addWidget(self.lbl_status)
        root.addLayout(header)

        # Object meta + format summary
        top = QHBoxLayout()
        top.setSpacing(6)
        meta_box = QGroupBox("Source")
        meta_layout = QFormLayout(meta_box)
        self.txt_name = QLineEdit()
        self.txt_name.setPlaceholderText("File source name")
        self.txt_description = QLineEdit()
        self.txt_description.setPlaceholderText("Optional description")
        self.txt_tags = QLineEdit()
        self.txt_tags.setPlaceholderText("Optional comma-separated tags")
        meta_layout.addRow("Name", self.txt_name)
        meta_layout.addRow("Description", self.txt_description)
        meta_layout.addRow("Tags", self.txt_tags)
        top.addWidget(meta_box, 2)

        fmt_box = QGroupBox("Format")
        fmt_layout = QVBoxLayout(fmt_box)
        self.lbl_format = QLabel()
        self.lbl_format.setWordWrap(True)
        self.lbl_format.setFont(_FONT)
        fmt_layout.addWidget(self.lbl_format)
        fmt_layout.addStretch()
        self.lbl_format_hint = QLabel(
            "The first file sets the format and columns. Later files must match.")
        self.lbl_format_hint.setWordWrap(True)
        self.lbl_format_hint.setStyleSheet("color: #6B7280; font-style: italic;")
        fmt_layout.addWidget(self.lbl_format_hint)
        top.addWidget(fmt_box, 3)
        root.addLayout(top)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.setHandleWidth(4)

        # Left: column schema
        cols_panel = QWidget()
        cols_layout = QVBoxLayout(cols_panel)
        cols_layout.setContentsMargins(0, 0, 0, 0)
        cols_layout.setSpacing(4)
        cols_header = QLabel("Columns  (click a Type to change it)")
        cols_header.setFont(_FONT_BOLD)
        cols_header.setStyleSheet(
            "background: #1E5BA8; color: white; padding: 3px 5px;")
        cols_layout.addWidget(cols_header)
        self.tbl_columns = QTableWidget(0, 2)
        self.tbl_columns.setHorizontalHeaderLabels(["Column", "Type"])
        self.tbl_columns.verticalHeader().setVisible(False)
        self.tbl_columns.verticalHeader().setDefaultSectionSize(20)
        self.tbl_columns.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.tbl_columns.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)
        self.tbl_columns.setFont(_FONT)
        hdr = self.tbl_columns.horizontalHeader()
        hdr.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        hdr.setSectionResizeMode(1, QHeaderView.ResizeMode.Fixed)
        self.tbl_columns.setColumnWidth(1, 96)
        cols_layout.addWidget(self.tbl_columns, 1)
        self.btn_name_columns = QPushButton("Name Columns")
        self.btn_name_columns.setFont(_FONT)
        self.btn_name_columns.setFixedHeight(24)
        self.btn_name_columns.clicked.connect(self._edit_column_names)
        cols_layout.addWidget(self.btn_name_columns)
        splitter.addWidget(cols_panel)

        # Right: member files + preview
        right = QWidget()
        right_layout = QVBoxLayout(right)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.setSpacing(4)

        files_box = QGroupBox("Member Files  (each is its own table — drag files here to add)")
        files_layout = QVBoxLayout(files_box)
        self.list_members = FileDropList()
        self.list_members.setFont(_FONT)
        self.list_members.setFixedHeight(140)
        self.list_members.files_dropped.connect(self._add_files)
        files_layout.addWidget(self.list_members)
        file_btns = QHBoxLayout()
        self.btn_add_file = QPushButton("Add File(s)…")
        self.btn_add_file.setFont(_FONT_BOLD)
        self.btn_add_file.setFixedHeight(26)
        self.btn_add_file.setStyleSheet(_ACTION_BTN_STYLE)
        self.btn_add_file.clicked.connect(self._pick_files)
        self.btn_remove_file = QPushButton("Remove")
        self.btn_remove_file.setFont(_FONT)
        self.btn_remove_file.setFixedHeight(26)
        self.btn_remove_file.clicked.connect(self._remove_selected_member)
        file_btns.addWidget(self.btn_add_file)
        file_btns.addWidget(self.btn_remove_file)
        file_btns.addStretch()
        files_layout.addLayout(file_btns)
        right_layout.addWidget(files_box)

        prev_controls = QHBoxLayout()
        prev_controls.setSpacing(6)
        self.btn_preview = QPushButton("Preview selected file")
        self.btn_preview.setFont(_FONT_BOLD)
        self.btn_preview.setFixedHeight(28)
        self.btn_preview.setStyleSheet(_ACTION_BTN_STYLE)
        self.btn_preview.clicked.connect(self._preview_selected)
        self.txt_limit = QLineEdit("100")
        self.txt_limit.setFixedWidth(60)
        prev_controls.addWidget(self.btn_preview)
        prev_controls.addWidget(QLabel("Rows"))
        prev_controls.addWidget(self.txt_limit)
        prev_controls.addStretch()
        right_layout.addLayout(prev_controls)

        self.preview_table = FilterTableView(self)
        tv = self.preview_table.table_view
        tv.setShowGrid(False)
        tv.setAlternatingRowColors(False)
        tv.verticalHeader().setVisible(False)
        tv.verticalHeader().setDefaultSectionSize(16)
        right_layout.addWidget(self.preview_table, 1)
        splitter.addWidget(right)

        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)
        splitter.setSizes([280, 840])
        root.addWidget(splitter, 1)

        # Footer actions
        footer = QHBoxLayout()
        self.btn_visual_query = QPushButton("Visual Query →")
        self.btn_visual_query.setFixedSize(130, 34)
        self.btn_visual_query.setStyleSheet(_ACTION_BTN_STYLE)
        self.btn_visual_query.setToolTip(
            "Save this source and open the Visual Query designer over it (DuckDB)")
        self.btn_visual_query.clicked.connect(self._emit_visual_query_requested)
        footer.addWidget(self.btn_visual_query)
        self.btn_query = QPushButton("SQL Query →")
        self.btn_query.setFixedSize(120, 34)
        self.btn_query.setStyleSheet(_ACTION_BTN_STYLE)
        self.btn_query.setToolTip(
            "Save this source and open the Manual SQL editor to query it (DuckDB)")
        self.btn_query.clicked.connect(self._emit_query_requested)
        footer.addWidget(self.btn_query)
        footer.addStretch()
        self.btn_open_existing = QPushButton("Open…")
        self.btn_open_existing.setFixedSize(70, 34)
        self.btn_open_existing.setStyleSheet(_SAVE_BTN_STYLE)
        self.btn_open_existing.setToolTip("Open a saved File Source to edit")
        self.btn_open_existing.clicked.connect(self._open_existing)
        footer.addWidget(self.btn_open_existing)
        self.btn_new = QPushButton("New")
        self.btn_new.setFixedSize(70, 34)
        self.btn_new.setStyleSheet(_SAVE_BTN_STYLE)
        self.btn_new.clicked.connect(self._confirm_new)
        self.btn_save_as = QPushButton("Save As")
        self.btn_save_as.setFixedSize(80, 34)
        self.btn_save_as.setStyleSheet(_SAVE_BTN_STYLE)
        self.btn_save_as.clicked.connect(self._save_as)
        self.btn_save = QPushButton("Save File Source")
        self.btn_save.setFixedSize(130, 34)
        self.btn_save.setStyleSheet(_SAVE_BTN_STYLE)
        self.btn_save.clicked.connect(self._save)
        footer.addWidget(self.btn_new)
        footer.addWidget(self.btn_save_as)
        footer.addWidget(self.btn_save)
        root.addLayout(footer)

    # ── State / refresh ─────────────────────────────────────────────────────

    def new_object(self):
        self._fds = None
        self._original_name = ""
        self.txt_name.clear()
        self.txt_description.clear()
        self.txt_tags.clear()
        self.preview_table.set_dataframe(pd.DataFrame(), limit_rows=False)
        self.lbl_status.setText("Add a file to set the format, then add more of the same type")
        self._refresh_all()

    def load_file_source(self, fds: FileDataSource):
        """Load an existing FileDataSource for editing."""
        self._fds = fds
        self._original_name = fds.name
        self.txt_name.setText(fds.name)
        self.txt_description.setText(fds.description or "")
        self.txt_tags.setText(", ".join(fds.tags or []))
        self.preview_table.set_dataframe(pd.DataFrame(), limit_rows=False)
        self.lbl_status.setText(
            f"Loaded {len(fds.members)} file(s), {len(fds.columns)} columns")
        self._refresh_all()

    def _refresh_all(self):
        self._refresh_heading()
        self._refresh_format()
        self._refresh_columns()
        self._refresh_members()
        self._update_buttons()

    def _refresh_heading(self):
        name = self._original_name.strip() or "(new)"
        suffix = f"  [{datasource_label(self._fds)}]" if self._fds else ""
        self.lbl_heading.setText(f"File Source: {name}{suffix}")

    def _refresh_format(self):
        self.lbl_format.setText(self._format_summary())

    def _format_summary(self) -> str:
        if self._fds is None:
            return "No format yet."
        st = self._fds.source_type
        ps = self._fds.parse_spec
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

    def _refresh_columns(self):
        self._loading_columns = True
        self.tbl_columns.setRowCount(0)
        if self._fds is None:
            self._loading_columns = False
            return
        self.tbl_columns.setRowCount(len(self._fds.columns))
        for row, col in enumerate(self._fds.columns):
            name_item = QTableWidgetItem(col.name)
            name_item.setFlags(name_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            self.tbl_columns.setItem(row, 0, name_item)
            combo = QComboBox()
            combo.addItems(_DATA_TYPES)
            data_type = (col.data_type or "TEXT").upper()
            if data_type not in _DATA_TYPES:
                combo.addItem(data_type)
            combo.setCurrentText(data_type)
            combo.currentTextChanged.connect(
                lambda text, r=row: self._on_column_type_changed(r, text))
            self.tbl_columns.setCellWidget(row, 1, combo)
        self._loading_columns = False

    def _on_column_type_changed(self, row: int, data_type: str):
        if self._loading_columns or self._fds is None:
            return
        if 0 <= row < len(self._fds.columns):
            self._fds.columns[row].data_type = data_type
            self.lbl_status.setText(
                f"{self._fds.columns[row].name} → {data_type}  (Save to persist)")

    def _refresh_members(self):
        self.list_members.clear()
        if self._fds is None or not self._fds.members:
            placeholder = QListWidgetItem("Drag files here, or click Add File(s)…")
            placeholder.setFlags(Qt.ItemFlag.NoItemFlags)
            placeholder.setForeground(Qt.GlobalColor.gray)
            self.list_members.addItem(placeholder)
            return
        for idx, member in enumerate(self._fds.members):
            item = QListWidgetItem(
                f"{member.resolved_table_name()}      —      {member.path}")
            item.setData(Qt.ItemDataRole.UserRole, idx)
            self.list_members.addItem(item)

    def _update_buttons(self):
        has_source = self._fds is not None and bool(self._fds.members)
        self.btn_save.setEnabled(has_source)
        self.btn_save_as.setEnabled(has_source)
        self.btn_name_columns.setEnabled(self._fds is not None)
        self.btn_preview.setEnabled(has_source)
        self.btn_remove_file.setEnabled(has_source)
        self.btn_query.setEnabled(has_source)
        self.btn_visual_query.setEnabled(has_source)

    # ── Adding files ────────────────────────────────────────────────────────

    def _pick_files(self):
        paths, _ = QFileDialog.getOpenFileNames(
            self, "Add File(s) to Source", "", _FILE_FILTER)
        if paths:
            self._add_files(paths)

    def _add_files(self, paths: list[str]):
        errors: list[str] = []
        added = 0
        for path in paths:
            if self._fds is None:
                fds = self._establish_source_from_first_file(path)
                if fds is None:
                    return  # user cancelled the format dialog
                self._fds = fds
                added += 1
            else:
                try:
                    add_member_file(self._fds, path)
                    added += 1
                except FileValidationError as exc:
                    errors.append(f"• {Path(path).name}: {exc}")
        self._refresh_all()
        if added:
            self.lbl_status.setText(f"Added {added} file(s)")
        if errors:
            QMessageBox.warning(
                self, "Some files were not added", "\n\n".join(errors))

    def _establish_source_from_first_file(self, path: str) -> FileDataSource | None:
        format_spec = self._text_format_spec_for_path(path)
        if format_spec is False:
            return None  # cancelled
        name = self.txt_name.text().strip() or Path(path).stem
        try:
            return infer_file_source_from_file(
                path, name=name, format_spec=format_spec)
        except Exception as exc:
            QMessageBox.warning(self, "Could Not Read File", f"{exc}")
            return None

    def _remove_selected_member(self):
        if self._fds is None:
            return
        rows = sorted(
            (item.data(Qt.ItemDataRole.UserRole)
             for item in self.list_members.selectedItems()
             if item.data(Qt.ItemDataRole.UserRole) is not None),
            reverse=True,
        )
        for idx in rows:
            if 0 <= idx < len(self._fds.members):
                del self._fds.members[idx]
        self._refresh_all()

    # ── Format dialogs (ported from the CSV/Excel editor) ───────────────────

    def _text_format_spec_for_path(self, path: str):
        """None = auto/CSV/Excel; dict = explicit text spec; False = cancelled."""
        suffix = Path(path).suffix.lower()
        if suffix not in {".txt", ".dat", ".psv", ".tsv"}:
            return None
        default_mode = "Delimited" if suffix in {".psv", ".tsv"} else "Auto-detect delimited"
        mode, ok = QInputDialog.getItem(
            self, "Text File Layout", "How should this text file be parsed?",
            [default_mode, "Delimited", "Fixed width"], 0, False)
        if not ok:
            return False
        if mode == "Fixed width":
            return self._fixed_width_spec_from_user()
        if mode == "Delimited":
            return self._delimited_spec_from_user(path)
        return None

    def _delimited_spec_from_user(self, path: str):
        suffix = Path(path).suffix.lower()
        default_delimiter = {".tsv": "\\t", ".psv": "|"}.get(suffix, ",")
        delimiter_text, ok = QInputDialog.getText(
            self, "Delimited Text Settings", "Delimiter (use \\t for tab):",
            text=default_delimiter)
        if not ok:
            return False
        delimiter = delimiter_text or default_delimiter
        delimiter = "\t" if delimiter == "\\t" else delimiter
        has_header = QMessageBox.question(
            self, "Delimited Text Settings",
            "Does the first row contain column names?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.Yes) == QMessageBox.StandardButton.Yes
        skip_rows, ok = QInputDialog.getInt(
            self, "Delimited Text Settings", "Rows to skip before reading:",
            0, 0, 100000, 1)
        if not ok:
            return False
        return delimited_text_spec(
            delimiter=delimiter, has_header=has_header, skip_rows=skip_rows)

    def _fixed_width_spec_from_user(self):
        message = ("Enter one column per line as: name,start,width\n"
                   "Example:\nPolicy,1,10\nCompany,11,2\nAmount,13,9")
        text, ok = QInputDialog.getMultiLineText(
            self, "Fixed Width Layout", message, "")
        if not ok:
            return False
        try:
            columns = self._parse_fixed_width_columns(text)
        except ValueError as exc:
            QMessageBox.warning(self, "Invalid Fixed Width Layout", str(exc))
            return False
        skip_rows, ok = QInputDialog.getInt(
            self, "Fixed Width Layout", "Rows to skip before reading:",
            0, 0, 100000, 1)
        if not ok:
            return False
        return fixed_width_spec(columns, skip_rows=skip_rows)

    @staticmethod
    def _parse_fixed_width_columns(text: str) -> list[dict]:
        columns = []
        for line in text.splitlines():
            stripped = line.strip()
            if not stripped:
                continue
            parts = [part.strip() for part in stripped.split(",")]
            if len(parts) != 3:
                raise ValueError("Each fixed-width line must be: name,start,width")
            name, start, width = parts
            try:
                columns.append({"name": name, "start": int(start), "width": int(width)})
            except ValueError as exc:
                raise ValueError("Fixed-width start and width must be numbers.") from exc
        if not columns:
            raise ValueError("Enter at least one fixed-width column.")
        return columns

    # ── Column naming ───────────────────────────────────────────────────────

    def _edit_column_names(self):
        if self._fds is None:
            QMessageBox.information(self, "Add a File First",
                                   "Add a file so its columns can be named.")
            return
        if self._fds.source_type == SOURCE_TYPE_EXCEL:
            QMessageBox.information(
                self, "Excel Columns",
                "Excel columns follow the sheet's header row and can't be renamed here.")
            return
        current = [c.name for c in self._fds.columns]
        text, ok = QInputDialog.getMultiLineText(
            self, "Name Columns",
            "Enter one column name per line, or comma-separated names:",
            "\n".join(current))
        if not ok:
            return
        try:
            names = self._parse_column_names(text)
        except ValueError as exc:
            QMessageBox.warning(self, "Invalid Column Names", str(exc))
            return
        if len(names) != len(current):
            QMessageBox.warning(
                self, "Invalid Column Names",
                f"Enter exactly {len(current)} names. You entered {len(names)}.")
            return
        self._apply_column_names(names)
        self._refresh_all()
        self.lbl_status.setText(f"Named {len(names)} columns")

    def _apply_column_names(self, names: list[str]):
        """Rename schema columns and push the rename into the parse spec.

        Delimited: the readers rename via ``column_names`` (works with or without
        a header). Fixed-width: rename each column spec. Both keep the schema and
        the data the readers produce in agreement.
        """
        for col, new_name in zip(self._fds.columns, names):
            col.name = new_name
        if self._fds.source_type == SOURCE_TYPE_CSV:
            self._fds.parse_spec["column_names"] = list(names)
        elif self._fds.source_type == SOURCE_TYPE_FIXED_WIDTH:
            for spec, new_name in zip(self._fds.parse_spec.get("columns", []), names):
                spec["name"] = new_name

    @staticmethod
    def _parse_column_names(text: str) -> list[str]:
        raw_parts: list[str] = []
        for line in text.splitlines():
            raw_parts.extend(line.split(","))
        names = [part.strip() for part in raw_parts if part.strip()]
        if not names:
            raise ValueError("Enter at least one column name.")
        lowered = [name.lower() for name in names]
        if len(lowered) != len(set(lowered)):
            raise ValueError("Column names must be unique.")
        return names

    # ── Preview ─────────────────────────────────────────────────────────────

    def _preview_selected(self):
        if self._fds is None or not self._fds.members:
            return
        idx = self._selected_member_index()
        if idx is None:
            idx = 0
        member = self._fds.members[idx]
        table = member.resolved_table_name()
        try:
            limit = int(self.txt_limit.text().strip() or "100")
        except ValueError:
            QMessageBox.warning(self, "Invalid Rows", "Rows must be a number.")
            return
        try:
            result = file_query_runner.run_sql(
                self._fds, f'SELECT * FROM "{table}"',
                limit=limit, table_names=[table])
        except Exception as exc:
            QMessageBox.warning(self, "Preview Failed", str(exc))
            return
        df = result.dataframe
        self.preview_table.set_dataframe(df, limit_rows=False)
        self.lbl_status.setText(
            f"Preview of {table}: {len(df)} rows × {len(df.columns)} columns")

    def _selected_member_index(self):
        for item in self.list_members.selectedItems():
            idx = item.data(Qt.ItemDataRole.UserRole)
            if idx is not None:
                return idx
        return None

    # ── Save ────────────────────────────────────────────────────────────────

    def _save(self):
        if not self._original_name:
            self._save_as()
            return
        self._save_source(self._original_name)

    def _save_as(self):
        default = self.txt_name.text().strip()
        name, ok = QInputDialog.getText(
            self, "Save File Source", "File source name:", text=default)
        if ok and name.strip():
            self._save_source(name.strip(), save_as=True)

    def _save_source(self, name: str, *, save_as: bool = False):
        if self._fds is None or not self._fds.members:
            QMessageBox.information(
                self, "Add a File First", "Add at least one file before saving.")
            return
        if save_as:
            # A "Save As" is a new, independent source.
            from uuid import uuid4
            self._fds.id = uuid4().hex
        self._fds.name = name
        self._fds.description = self.txt_description.text().strip()
        self._fds.tags = [t.strip() for t in self.txt_tags.text().split(",") if t.strip()]
        self._fds.updated_at = datetime.now()
        file_source_store.save_file_source(self._fds)
        self._original_name = name
        self.txt_name.setText(name)
        self._refresh_all()
        self.saved.emit(name)
        QMessageBox.information(self, "File Source Saved", f'Saved "{name}".')

    def _ensure_saved_for_query(self) -> bool:
        """Persist the source so a query runs against what's on disk."""
        if self._fds is None or not self._fds.members:
            QMessageBox.information(self, "Add a File First",
                                   "Add at least one file before querying.")
            return False
        self._save()
        return bool(self._original_name and self._fds.id)

    def _emit_query_requested(self):
        """Save the source, then ask the app to open a Manual SQL query on it."""
        if self._ensure_saved_for_query():
            self.query_requested.emit(self._fds.id)

    def _emit_visual_query_requested(self):
        """Save the source, then ask the app to open a Visual query on it."""
        if self._ensure_saved_for_query():
            self.visual_query_requested.emit(self._fds.id)

    def _open_existing(self):
        """Pick a saved File Source from the browser and load it for editing."""
        from suiteview.audit.dialogs.file_source_browser import FileSourceBrowserDialog

        dlg = FileSourceBrowserDialog(self)
        if dlg.exec() == QDialog.DialogCode.Accepted and dlg.selected_id:
            fds = file_source_store.load_file_source_by_id(dlg.selected_id)
            if fds is not None:
                self.load_file_source(fds)

    def _confirm_new(self):
        reply = QMessageBox.question(
            self, "Start New File Source?",
            "This clears the current file source. Continue?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No)
        if reply == QMessageBox.StandardButton.Yes:
            self.new_object()


class FileSourceEditorWindow(FramelessWindowBase):
    """Standalone window that hosts the File Source editor.

    Defining a flat-file data source is its own task, not a build mode inside the
    Audit tool — so it gets a dedicated frameless window (Blue/Gold). The hosted
    editor is exposed as ``self.editor`` so callers can drive it (``new_object``,
    ``load_file_source``) and connect its signals (``saved``, ``query_requested``,
    ``visual_query_requested``).
    """

    def __init__(self, parent=None):
        super().__init__(
            title="File Source Editor",
            default_size=(1140, 720),
            min_size=(900, 560),
            parent=parent,
            header_colors=("#1E5BA8", "#0D3A7A", "#082B5C"),
            border_color="#D4A017",
        )

    def build_content(self) -> QWidget:
        self.editor = FileSourceEditor()
        return self.editor

    def new_source(self):
        self.editor.new_object()
        self._set_title_for(None)

    def edit_source(self, fds: FileDataSource):
        self.editor.load_file_source(fds)
        self._set_title_for(fds)

    def _set_title_for(self, fds: FileDataSource | None):
        name = fds.name if fds is not None else "New"
        self._title_label.setText(f"File Source Editor — {name}")
