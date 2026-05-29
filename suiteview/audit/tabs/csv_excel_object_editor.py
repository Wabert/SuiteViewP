"""File source Query Object editor."""
from __future__ import annotations

from datetime import datetime
from pathlib import Path
import time

import pandas as pd
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QFont
from PyQt6.QtWidgets import (
    QAbstractItemView,
    QFileDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QSplitter,
    QVBoxLayout,
    QWidget,
)

from suiteview.audit import query_object_store
from suiteview.audit.adhoc_source_intake import (
    delimited_text_spec,
    fixed_width_spec,
    query_object_from_file,
    query_adhoc_object,
    replace_adhoc_source_path,
)
from suiteview.audit.query_object import QueryObject
from suiteview.audit.query_object import fields_from_columns
from suiteview.audit.sql_helpers import fmt_time
from suiteview.audit.ui.bottom_bar import AuditBottomBar, FOOTER_BG
from suiteview.ui.widgets.filter_table_view import FilterTableView


_FONT = QFont("Segoe UI", 9)
_FONT_BOLD = QFont("Segoe UI", 9, QFont.Weight.Bold)

_SAVE_OBJECT_BTN_STYLE = (
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


class CsvExcelObjectEditor(QWidget):
    """Landing page and light query surface for file-backed QueryObjects."""

    saved = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._obj: QueryObject | None = None
        self._original_name = ""
        self._path = ""
        self._fields_sort_ascending = True
        self._build_ui()

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(4, 4, 4, 4)
        root.setSpacing(6)
        self.setStyleSheet(
            "QWidget { background-color: #F6F8FB; color: #111; }"
            "QLineEdit { background: white; border: 1px solid #9FB4CC; padding: 4px; }"
            "QListWidget { background: white; border: 1px solid #9FB4CC; }"
            "QGroupBox { border: 1px solid #AFC3DA; margin-top: 8px;"
            " padding: 8px 6px 6px 6px; font-weight: bold; }"
            "QGroupBox::title { subcontrol-origin: margin; left: 8px; padding: 0 4px; }"
        )

        header = QHBoxLayout()
        self.lbl_object_heading = QLabel("File Source Object: (new)")
        self.lbl_object_heading.setFont(QFont("Segoe UI", 12, QFont.Weight.Bold))
        self.lbl_object_heading.setStyleSheet("color: #1E5BA8;")
        header.addWidget(self.lbl_object_heading)
        header.addStretch()
        self.lbl_status = QLabel("Choose a CSV, Excel, or text file")
        self.lbl_status.setFont(_FONT)
        self.lbl_status.setStyleSheet("color: #4B5563;")
        header.addWidget(self.lbl_status)
        root.addLayout(header)

        top = QHBoxLayout()
        top.setContentsMargins(0, 0, 0, 0)
        top.setSpacing(6)
        meta_box = QGroupBox("Object")
        meta_layout = QFormLayout(meta_box)
        self.txt_name = QLineEdit()
        self.txt_name.setPlaceholderText("Object name")
        self.txt_description = QLineEdit()
        self.txt_description.setPlaceholderText("Optional description")
        self.txt_tags = QLineEdit()
        self.txt_tags.setPlaceholderText("Optional comma-separated tags")
        meta_layout.addRow("Name", self.txt_name)
        meta_layout.addRow("Description", self.txt_description)
        meta_layout.addRow("Tags", self.txt_tags)
        top.addWidget(meta_box, 2)

        file_box = QGroupBox("File")
        file_layout = QVBoxLayout(file_box)
        self.txt_path = QLineEdit()
        self.txt_path.setReadOnly(True)
        self.txt_path.setPlaceholderText("No file selected")
        file_layout.addWidget(self.txt_path)
        self.btn_pick_file = QPushButton("Pick File")
        self.btn_pick_file.setFont(_FONT_BOLD)
        self.btn_pick_file.setFixedHeight(28)
        self.btn_pick_file.setStyleSheet(_ACTION_BTN_STYLE)
        self.btn_pick_file.clicked.connect(self._pick_file)
        file_layout.addWidget(self.btn_pick_file)
        self.btn_change_file = QPushButton("Change Source File")
        self.btn_change_file.setFont(_FONT_BOLD)
        self.btn_change_file.setFixedHeight(28)
        self.btn_change_file.setStyleSheet(_ACTION_BTN_STYLE)
        self.btn_change_file.clicked.connect(self._change_source_file)
        file_layout.addWidget(self.btn_change_file)
        top.addWidget(file_box, 3)
        root.addLayout(top)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.setHandleWidth(4)

        assist = QWidget()
        assist_layout = QVBoxLayout(assist)
        assist_layout.setContentsMargins(0, 0, 0, 0)
        assist_layout.setSpacing(4)
        self.btn_fields_header = QPushButton("Fields ↑")
        self.btn_fields_header.setFont(_FONT_BOLD)
        self.btn_fields_header.setFixedHeight(24)
        self.btn_fields_header.setStyleSheet(
            "QPushButton { background: #1E5BA8; color: white; padding: 3px 5px;"
            " border: none; text-align: left; }"
            "QPushButton:hover { background: #2A6BC4; }"
        )
        self.btn_fields_header.clicked.connect(self._toggle_fields_sort)
        assist_layout.addWidget(self.btn_fields_header)
        self.txt_field_search = QLineEdit()
        self.txt_field_search.setPlaceholderText("Search fields...")
        self.txt_field_search.setClearButtonEnabled(True)
        self.txt_field_search.textChanged.connect(self._filter_fields)
        assist_layout.addWidget(self.txt_field_search)
        self.list_fields = QListWidget()
        self.list_fields.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.list_fields.itemDoubleClicked.connect(lambda _: self._insert_selected_columns())
        assist_layout.addWidget(self.list_fields, 1)
        self.btn_insert_columns = QPushButton("Use Selected")
        self.btn_insert_columns.setFont(_FONT)
        self.btn_insert_columns.setFixedHeight(24)
        self.btn_insert_columns.clicked.connect(self._insert_selected_columns)
        assist_layout.addWidget(self.btn_insert_columns)
        self.btn_edit_columns = QPushButton("Name Columns")
        self.btn_edit_columns.setFont(_FONT)
        self.btn_edit_columns.setFixedHeight(24)
        self.btn_edit_columns.clicked.connect(self._edit_column_names)
        assist_layout.addWidget(self.btn_edit_columns)
        splitter.addWidget(assist)

        query_panel = QWidget()
        query_layout = QVBoxLayout(query_panel)
        query_layout.setContentsMargins(0, 0, 0, 0)
        query_layout.setSpacing(6)
        controls = QHBoxLayout()
        controls.setContentsMargins(0, 0, 0, 0)
        controls.setSpacing(6)
        self.txt_columns = QLineEdit()
        self.txt_columns.setPlaceholderText("Columns, comma-separated. Blank = all")
        self.txt_filter = QLineEdit()
        self.txt_filter.setPlaceholderText("Pandas filter expression, optional")
        self.txt_limit = QLineEdit("500")
        self.txt_limit.setFixedWidth(70)
        self.btn_preview = QPushButton("Preview / Run")
        self.btn_preview.setFont(_FONT_BOLD)
        self.btn_preview.setFixedSize(120, 30)
        self.btn_preview.setStyleSheet(_ACTION_BTN_STYLE)
        self.btn_preview.clicked.connect(self._preview)
        controls.addWidget(QLabel("Columns"))
        controls.addWidget(self.txt_columns, 2)
        controls.addWidget(QLabel("Filter"))
        controls.addWidget(self.txt_filter, 2)
        controls.addWidget(QLabel("Rows"))
        controls.addWidget(self.txt_limit)
        controls.addWidget(self.btn_preview)
        query_layout.addLayout(controls)
        self.results_table = FilterTableView(self)
        tv = self.results_table.table_view
        tv.setShowGrid(False)
        tv.setAlternatingRowColors(False)
        tv.verticalHeader().setVisible(False)
        tv.verticalHeader().setDefaultSectionSize(16)
        query_layout.addWidget(self.results_table, 1)
        splitter.addWidget(query_panel)
        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)
        splitter.setSizes([280, 840])
        root.addWidget(splitter, 1)

        self.bottom_bar = AuditBottomBar(bg_color=FOOTER_BG, run_label="Run")
        self.bottom_bar.btn_all.setVisible(False)
        self.bottom_bar.txt_max_count.setVisible(False)
        self.bottom_bar.lbl_max_count.setVisible(False)
        self.btn_new_query = QPushButton("New Query")
        self.btn_new_query.setFont(_FONT_BOLD)
        self.btn_new_query.setFixedSize(78, 36)
        self.btn_new_query.setStyleSheet(_SAVE_OBJECT_BTN_STYLE)
        self.btn_new_query.clicked.connect(self._confirm_new_object)
        self.btn_save = QPushButton("Save")
        self.btn_save.setFont(_FONT_BOLD)
        self.btn_save.setFixedSize(60, 36)
        self.btn_save.setStyleSheet(_SAVE_OBJECT_BTN_STYLE)
        self.btn_save.clicked.connect(self._save)
        self.btn_save_as = QPushButton("Save As")
        self.btn_save_as.setFont(_FONT_BOLD)
        self.btn_save_as.setFixedSize(60, 36)
        self.btn_save_as.setStyleSheet(_SAVE_OBJECT_BTN_STYLE)
        self.btn_save_as.clicked.connect(self._save_as)
        self.bottom_bar.action_layout.addWidget(self.btn_new_query)
        self.bottom_bar.action_layout.addWidget(self.btn_save_as)
        self.bottom_bar.action_layout.addWidget(self.btn_save)
        self.bottom_bar.btn_run.clicked.connect(self._preview)
        root.addWidget(self.bottom_bar)
        self._update_save_state()

    def new_object(self):
        self._obj = None
        self._original_name = ""
        self._path = ""
        self.txt_name.clear()
        self.txt_description.clear()
        self.txt_tags.clear()
        self.txt_path.clear()
        self.txt_columns.clear()
        self.txt_filter.clear()
        self.txt_limit.setText("500")
        self.list_fields.clear()
        self.results_table.set_dataframe(pd.DataFrame(), limit_rows=False)
        self.bottom_bar.reset_timing()
        self.lbl_status.setText("Choose a CSV, Excel, or text file")
        self._update_heading()
        self._update_save_state()

    def _confirm_new_object(self):
        reply = QMessageBox.question(
            self,
            "Start New Query?",
            "This will clear the current file source query. Continue?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if reply == QMessageBox.StandardButton.Yes:
            self.new_object()

    def load_object(self, obj: QueryObject):
        """Load an existing file-backed QueryObject into the editor."""
        self._obj = obj
        self._original_name = obj.name
        self._path = ""
        if obj.sources:
            self._path = obj.sources[0].metadata.get("path", "")
        self.txt_name.setText(obj.name)
        self.txt_description.setText(obj.description or "")
        self.txt_tags.setText(", ".join(obj.tags or []))
        self.txt_path.setText(self._path)
        self.txt_columns.clear()
        self.txt_filter.clear()
        self.txt_limit.setText("500")
        self.results_table.set_dataframe(pd.DataFrame(), limit_rows=False)
        self.bottom_bar.reset_timing()
        self._populate_fields()
        self.lbl_status.setText(f"Loaded {len(obj.fields)} fields")
        self._update_heading()
        self._update_save_state()

    def _pick_file(self):
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Choose File Source",
            "",
            "Data Files (*.csv *.txt *.dat *.psv *.tsv *.xlsx *.xlsm *.xls);;Text Files (*.csv *.txt *.dat *.psv *.tsv);;Excel Files (*.xlsx *.xlsm *.xls);;All Files (*.*)",
        )
        if not path:
            return
        default_name = path.rsplit("/", 1)[-1].rsplit("\\", 1)[-1].rsplit(".", 1)[0]
        name = self.txt_name.text().strip() or default_name
        format_spec = self._text_format_spec_for_path(path)
        if format_spec is False:
            return
        try:
            self._obj = query_object_from_file(path, name=name, format_spec=format_spec)
        except Exception as exc:
            QMessageBox.warning(self, "Import Failed", f"Could not read file:\n\n{exc}")
            return
        self._path = path
        self.txt_name.setText(name)
        self.txt_path.setText(path)
        self._populate_fields()
        self.lbl_status.setText(f"Loaded {len(self._obj.fields)} fields")
        self._update_heading()
        self._update_save_state()
        self._preview()

    def _change_source_file(self):
        if self._obj is None:
            self._pick_file()
            return
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Choose Replacement Source File",
            self._path or "",
            "Data Files (*.csv *.txt *.dat *.psv *.tsv *.xlsx *.xlsm *.xls);;Text Files (*.csv *.txt *.dat *.psv *.tsv);;Excel Files (*.xlsx *.xlsm *.xls);;All Files (*.*)",
        )
        if not path:
            return
        try:
            replace_adhoc_source_path(self._obj, path)
        except Exception as exc:
            QMessageBox.warning(self, "Source File Not Changed", str(exc))
            return
        self._path = path
        self.txt_path.setText(path)
        self.txt_columns.clear()
        self.lbl_status.setText("Source file changed; parser settings and columns kept")
        self._update_save_state()
        self._preview()

    def _text_format_spec_for_path(self, path: str) -> dict | None | bool:
        suffix = Path(path).suffix.lower()
        if suffix not in {".txt", ".dat", ".psv", ".tsv"}:
            return None

        default_mode = "Delimited" if suffix in {".psv", ".tsv"} else "Auto-detect delimited"
        mode, ok = QInputDialog.getItem(
            self,
            "Text File Layout",
            "How should this text file be parsed?",
            [default_mode, "Delimited", "Fixed width"],
            0,
            False,
        )
        if not ok:
            return False
        if mode == "Fixed width":
            return self._fixed_width_spec_from_user()
        if mode == "Delimited":
            return self._delimited_spec_from_user(path)
        return None

    def _delimited_spec_from_user(self, path: str) -> dict | bool:
        suffix = Path(path).suffix.lower()
        default_delimiter = {".tsv": "\\t", ".psv": "|"}.get(suffix, ",")
        delimiter_text, ok = QInputDialog.getText(
            self,
            "Delimited Text Settings",
            "Delimiter (use \\t for tab):",
            text=default_delimiter,
        )
        if not ok:
            return False
        delimiter = delimiter_text or default_delimiter
        delimiter = "\t" if delimiter == "\\t" else delimiter
        has_header = QMessageBox.question(
            self,
            "Delimited Text Settings",
            "Does the first row contain column names?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.Yes,
        ) == QMessageBox.StandardButton.Yes
        skip_rows, ok = QInputDialog.getInt(
            self,
            "Delimited Text Settings",
            "Rows to skip before reading:",
            0,
            0,
            100000,
            1,
        )
        if not ok:
            return False
        return delimited_text_spec(
            delimiter=delimiter,
            has_header=has_header,
            skip_rows=skip_rows,
        )

    def _fixed_width_spec_from_user(self) -> dict | bool:
        message = (
            "Enter one column per line as: name,start,width\n"
            "Example:\nPolicy,1,10\nCompany,11,2\nAmount,13,9"
        )
        text, ok = QInputDialog.getMultiLineText(
            self,
            "Fixed Width Layout",
            message,
            "",
        )
        if not ok:
            return False
        try:
            columns = self._parse_fixed_width_columns(text)
        except ValueError as exc:
            QMessageBox.warning(self, "Invalid Fixed Width Layout", str(exc))
            return False
        skip_rows, ok = QInputDialog.getInt(
            self,
            "Fixed Width Layout",
            "Rows to skip before reading:",
            0,
            0,
            100000,
            1,
        )
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

    def _populate_fields(self):
        self.list_fields.clear()
        if self._obj is None:
            return
        fields = sorted(
            self._obj.fields,
            key=lambda field: field.name.lower(),
            reverse=not self._fields_sort_ascending,
        )
        for field in fields:
            item = QListWidgetItem(field.name)
            self.list_fields.addItem(item)

    def _toggle_fields_sort(self):
        self._fields_sort_ascending = not self._fields_sort_ascending
        self.btn_fields_header.setText("Fields ↑" if self._fields_sort_ascending else "Fields ↓")
        self._populate_fields()

    def _filter_fields(self, text: str):
        filt = text.strip().lower()
        for row in range(self.list_fields.count()):
            item = self.list_fields.item(row)
            item.setHidden(filt not in item.text().lower() if filt else False)

    def _insert_selected_columns(self):
        selected = [item.text() for item in self.list_fields.selectedItems()]
        if selected:
            self.txt_columns.setText(", ".join(selected))

    def _edit_column_names(self):
        if self._obj is None or not self._obj.sources:
            QMessageBox.information(self, "File Required", "Choose a file source first.")
            return
        current_names = [field.name for field in self._obj.fields]
        text, ok = QInputDialog.getMultiLineText(
            self,
            "Name Columns",
            "Enter one column name per line, or comma-separated names:",
            "\n".join(current_names),
        )
        if not ok:
            return
        try:
            names = self._parse_column_names(text)
        except ValueError as exc:
            QMessageBox.warning(self, "Invalid Column Names", str(exc))
            return
        if len(names) != len(current_names):
            QMessageBox.warning(
                self,
                "Invalid Column Names",
                f"Enter exactly {len(current_names)} names. You entered {len(names)}.",
            )
            return
        old_types = {field.name: field.data_type for field in self._obj.fields}
        column_types = {
            new_name: old_types.get(old_name, "")
            for old_name, new_name in zip(current_names, names)
        }
        source = self._obj.sources[0]
        source.metadata["column_names"] = names
        self._obj.config["source_metadata"] = source.metadata
        self._obj.fields = fields_from_columns(names, column_types, source=self._obj.name)
        self._obj.updated_at = datetime.now()
        self.txt_columns.clear()
        self._populate_fields()
        self.lbl_status.setText(f"Named {len(names)} columns")
        self._preview()

    @staticmethod
    def _parse_column_names(text: str) -> list[str]:
        raw_parts = []
        for line in text.splitlines():
            raw_parts.extend(line.split(","))
        names = [part.strip() for part in raw_parts if part.strip()]
        if not names:
            raise ValueError("Enter at least one column name.")
        lowered = [name.lower() for name in names]
        if len(lowered) != len(set(lowered)):
            raise ValueError("Column names must be unique.")
        return names

    def _preview(self):
        if self._obj is None:
            QMessageBox.information(self, "File Required", "Choose a file source first.")
            return
        columns = [c.strip() for c in self.txt_columns.text().split(",") if c.strip()]
        try:
            limit = int(self.txt_limit.text().strip() or "500")
        except ValueError:
            QMessageBox.warning(self, "Invalid Rows", "Rows must be a number.")
            return
        try:
            t0 = time.time()
            df = query_adhoc_object(
                self._obj,
                columns=columns,
                filter_expr=self.txt_filter.text().strip(),
                limit=limit,
            )
            t_query = time.time() - t0
        except Exception as exc:
            QMessageBox.warning(self, "Preview Failed", str(exc))
            return
        t1 = time.time()
        self.results_table.set_dataframe(df, limit_rows=False)
        t_print = time.time() - t1
        self.bottom_bar.lbl_result_count.setText(f"Result count: {len(df)}")
        self.bottom_bar.lbl_query_time.setText(f"Query time: {fmt_time(t_query)}")
        self.bottom_bar.lbl_print_time.setText(f"Print time: {fmt_time(t_print)}")
        self.bottom_bar.lbl_total_time.setText(f"Total time: {fmt_time(t_query + t_print)}")
        self.lbl_status.setText(f"{len(df)} rows x {len(df.columns)} columns")

    def _save(self):
        if not self._original_name:
            self._save_as()
            return
        self._save_object(self._original_name)

    def _save_as(self):
        default = self.txt_name.text().strip()
        name, ok = QInputDialog.getText(self, "Save File Source Object", "Object name:", text=default)
        if not ok or not name.strip():
            return
        self._save_object(name.strip(), save_as=True)

    def _save_object(self, name: str, *, save_as: bool = False):
        if self._obj is None:
            QMessageBox.information(self, "File Required", "Choose a file source before saving.")
            return
        old_name = self._original_name
        self._obj.name = name
        self._obj.description = self.txt_description.text().strip()
        self._obj.tags = [tag.strip() for tag in self.txt_tags.text().split(",") if tag.strip()]
        self._obj.updated_at = datetime.now()
        query_object_store.save_object(self._obj)
        if old_name and old_name != name and not save_as:
            query_object_store.delete_object(old_name)
        self._original_name = name
        self.txt_name.setText(name)
        self._update_heading()
        self._update_save_state()
        self.saved.emit(name)
        QMessageBox.information(self, "Query Object Saved", f"Saved \"{name}\".")

    def _update_heading(self):
        name = self._original_name.strip() or "(new)"
        self.lbl_object_heading.setText(f"File Source Object: {name}")

    def _update_save_state(self):
        has_file = self._obj is not None
        has_existing = bool(self._original_name.strip())
        self.btn_change_file.setEnabled(has_file)
        self.btn_save.setVisible(has_existing)
        self.btn_save.setEnabled(has_file and has_existing)
        self.btn_save_as.setEnabled(has_file)