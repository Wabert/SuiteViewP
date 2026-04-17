"""
FieldPickerPanel — sidebar with Tables list and Fields list for quick
field drag-drop onto dynamic group tabs.

Left panel: field names for the selected table (draggable).
Right panel: table names from the active group's DSN.
"""
from __future__ import annotations

import logging
from typing import TYPE_CHECKING

import pyodbc
from PyQt6.QtCore import Qt, QMimeData, QThread, pyqtSignal
from PyQt6.QtGui import QFont, QDrag
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
    QListWidget, QAbstractItemView, QSplitter, QFrame,
)

from .tabs._styles import TightItemDelegate

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)

_FONT = QFont("Segoe UI", 9)
_FONT_BOLD = QFont("Segoe UI", 9, QFont.Weight.Bold)
_FONT_SMALL = QFont("Segoe UI", 8)

FIELD_DRAG_MIME = "application/x-audit-field-drag"

_LIST_STYLE = (
    "QListWidget { border: 1px solid #1E5BA8; background-color: white;"
    " font-size: 9pt; outline: none; }"
    "QListWidget::item { padding: 0px 2px; border: none; }"
    "QListWidget::item:selected { background-color: #A0C4E8; color: black; border: none; }"
    "QListWidget::item:focus { outline: none; border: none; }"
)

_HEADER_STYLE = (
    "QLabel { color: #1E5BA8; font-size: 8pt; font-weight: bold;"
    " padding: 2px 4px; background-color: #E8F0FB;"
    " border: 1px solid #C0D0E0; border-radius: 2px; }"
)


class _FieldLoaderThread(QThread):
    """Background thread to fetch column metadata from ODBC."""
    columns_loaded = pyqtSignal(str, list)  # table_name, [(col_name, type_name, size, nullable)]
    error_occurred = pyqtSignal(str)

    def __init__(self, dsn: str, table_name: str, parent=None):
        super().__init__(parent)
        self.dsn = dsn
        self.table_name = table_name

    def run(self):
        try:
            conn = pyodbc.connect(f"DSN={self.dsn}", autocommit=True, timeout=15)
            cursor = conn.cursor()
            parts = self.table_name.split(".", 1)
            if len(parts) == 2:
                schema, table = parts
            else:
                schema, table = None, parts[0]
            columns = []
            for row in cursor.columns(table=table, schema=schema):
                columns.append((
                    row.column_name,
                    row.type_name,
                    row.column_size,
                    "Yes" if row.nullable else "No",
                ))
            conn.close()
            self.columns_loaded.emit(self.table_name, columns)
        except Exception as exc:
            self.error_occurred.emit(str(exc))


class DraggableFieldList(QListWidget):
    """QListWidget that supports dragging field items out (multi-select)."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setDragEnabled(True)
        self.setDragDropMode(QAbstractItemView.DragDropMode.DragOnly)
        self.setSelectionMode(
            QAbstractItemView.SelectionMode.ExtendedSelection)
        self._field_data: dict[str, tuple] = {}  # display_text → (table, col, type, display)

    def set_field_data(self, data: dict[str, tuple]):
        self._field_data = data

    def startDrag(self, supportedActions):
        items = self.selectedItems()
        if not items:
            return
        lines = []
        for item in items:
            text = item.text()
            info = self._field_data.get(text)
            if info:
                table, col, type_name, display = info
                lines.append(f"{table}|{col}|{type_name}|{display}")
        if not lines:
            return
        drag = QDrag(self)
        mime = QMimeData()
        payload = "\n".join(lines)
        mime.setData(FIELD_DRAG_MIME, payload.encode("utf-8"))
        drag.setMimeData(mime)
        drag.exec(Qt.DropAction.CopyAction)


class FieldPickerPanel(QWidget):
    """Side panel showing Fields (left) and Tables (right) for easy drag-drop."""
    field_requested = pyqtSignal(str, str, str, str)  # table, column, type, display

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumWidth(200)
        self.setMaximumWidth(400)

        self._dsn: str = ""
        self._tables: list[str] = []
        self._display_names: dict[str, str] = {}
        self._current_table: str = ""
        self._loader: _FieldLoaderThread | None = None
        self._field_cache: dict[str, list[tuple]] = {}

        self._build_ui()

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.setHandleWidth(4)

        # ── Left: Fields ─────────────────────────────────────────
        fields_frame = QWidget()
        fl = QVBoxLayout(fields_frame)
        fl.setContentsMargins(4, 4, 2, 4)
        fl.setSpacing(3)

        lbl_fields = QLabel("Fields")
        lbl_fields.setStyleSheet(_HEADER_STYLE)
        fl.addWidget(lbl_fields)

        self.txt_search = QLineEdit()
        self.txt_search.setFont(_FONT_SMALL)
        self.txt_search.setPlaceholderText("Search fields...")
        self.txt_search.setClearButtonEnabled(True)
        self.txt_search.setFixedHeight(22)
        self.txt_search.textChanged.connect(self._filter_fields)
        fl.addWidget(self.txt_search)

        self.list_fields = DraggableFieldList()
        self.list_fields.setFont(_FONT)
        self.list_fields.setStyleSheet(_LIST_STYLE)
        self.list_fields.setItemDelegate(TightItemDelegate(self.list_fields))
        self.list_fields.setUniformItemSizes(True)
        self.list_fields.itemDoubleClicked.connect(self._on_field_double_clicked)
        fl.addWidget(self.list_fields)

        self.lbl_status = QLabel("")
        self.lbl_status.setFont(_FONT_SMALL)
        self.lbl_status.setStyleSheet("color: #666;")
        fl.addWidget(self.lbl_status)

        splitter.addWidget(fields_frame)

        # ── Right: Tables ────────────────────────────────────────
        tables_frame = QWidget()
        tl = QVBoxLayout(tables_frame)
        tl.setContentsMargins(2, 4, 4, 4)
        tl.setSpacing(3)

        lbl_tables = QLabel("Tables")
        lbl_tables.setStyleSheet(_HEADER_STYLE)
        tl.addWidget(lbl_tables)

        self.list_tables = QListWidget()
        self.list_tables.setFont(_FONT)
        self.list_tables.setStyleSheet(_LIST_STYLE)
        self.list_tables.setItemDelegate(TightItemDelegate(self.list_tables))
        self.list_tables.setUniformItemSizes(True)
        self.list_tables.setSelectionMode(
            QAbstractItemView.SelectionMode.SingleSelection)
        self.list_tables.currentItemChanged.connect(self._on_table_selected)
        tl.addWidget(self.list_tables)

        splitter.addWidget(tables_frame)

        splitter.setStretchFactor(0, 3)
        splitter.setStretchFactor(1, 1)

        self._splitter = splitter
        root.addWidget(splitter)

    # ── State persistence ─────────────────────────────────────────

    def get_state(self) -> dict:
        return {"splitter_sizes": self._splitter.sizes()}

    def set_state(self, state: dict):
        sizes = state.get("splitter_sizes")
        if sizes and len(sizes) == 2:
            self._splitter.setSizes(sizes)

    # ── Public API ────────────────────────────────────────────────

    def set_group(self, dsn: str, tables: list[str],
                  display_names: dict[str, str]):
        """Load tables and fields from a dynamic group."""
        self._dsn = dsn
        self._tables = list(tables)
        self._display_names = display_names
        self._field_cache.clear()
        self._current_table = ""

        self.list_tables.clear()
        self.list_fields.clear()
        self.lbl_status.setText("")

        self.list_tables.addItems(self._tables)
        if self._tables:
            self.list_tables.setCurrentRow(0)

    def clear(self):
        """Clear the panel."""
        self._dsn = ""
        self._tables = []
        self._display_names = {}
        self._field_cache.clear()
        self._current_table = ""
        self.list_tables.clear()
        self.list_fields.clear()
        self.lbl_status.setText("")

    # ── Table selection ──────────────────────────────────────────

    def _on_table_selected(self, current, previous):
        if current is None:
            return
        table = current.text()
        if table == self._current_table:
            return
        self._current_table = table
        self._load_fields(table)

    def _load_fields(self, table: str):
        if table in self._field_cache:
            self._populate_fields(table, self._field_cache[table])
            return
        self.list_fields.clear()
        self.lbl_status.setText("Loading...")
        self._loader = _FieldLoaderThread(self._dsn, table, self)
        self._loader.columns_loaded.connect(self._on_fields_loaded)
        self._loader.error_occurred.connect(self._on_fields_error)
        self._loader.start()

    def _on_fields_loaded(self, table: str, columns: list[tuple]):
        self._field_cache[table] = columns
        if self._current_table == table:
            self._populate_fields(table, columns)
        self._loader = None

    def _on_fields_error(self, msg: str):
        self.lbl_status.setText("Error")
        self._loader = None

    def _populate_fields(self, table: str, columns: list[tuple]):
        self.list_fields.clear()
        field_data: dict[str, tuple] = {}
        for col_name, type_name, size, nullable in columns:
            key = f"{table}.{col_name}"
            display = self._display_names.get(key, col_name)
            # Show display name with column in parens
            if display != col_name:
                label = f"{display}  ({col_name})"
            else:
                label = col_name
            self.list_fields.addItem(label)
            field_data[label] = (table, col_name, type_name, display)
        self.list_fields.set_field_data(field_data)
        self.lbl_status.setText(f"{len(columns)} fields")

    def _filter_fields(self, text: str):
        filt = text.strip().lower()
        for i in range(self.list_fields.count()):
            item = self.list_fields.item(i)
            item.setHidden(filt not in item.text().lower() if filt else False)

    def _on_field_double_clicked(self, item):
        """Emit field_requested when a field is double-clicked."""
        info = self.list_fields._field_data.get(item.text())
        if info:
            table, col, type_name, display = info
            self.field_requested.emit(table, col, type_name, display)
