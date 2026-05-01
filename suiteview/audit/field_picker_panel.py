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
from PyQt6.QtGui import QFont, QDrag, QColor, QBrush
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
    QListWidget, QAbstractItemView, QSplitter, QFrame, QPushButton, QMenu,
    QListWidgetItem,
)

from .tabs._styles import TightItemDelegate

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)

_FONT = QFont("Segoe UI", 9)
_FONT_BOLD = QFont("Segoe UI", 9, QFont.Weight.Bold)
_FONT_SMALL = QFont("Segoe UI", 8)

FIELD_DRAG_MIME = "application/x-audit-field-drag"

# ── Purple-themed styles ──────────────────────────────────────────
_PURPLE = "#7C3AED"
_PURPLE_DARK = "#6D28D9"
_PURPLE_LIGHT = "#DDD6FE"
_PURPLE_BG = "#EDE9FE"
_PURPLE_HOVER = "#8B5CF6"
_PURPLE_DEEP = "#4C1D95"

def _make_list_style(border: str, sel_bg: str, sel_fg: str) -> str:
    return (
        f"QListWidget {{ border: 1px solid {border}; background-color: white;"
        f" font-size: 9pt; outline: none; }}"
        f"QListWidget::item {{ padding: 0px 2px; border: none; }}"
        f"QListWidget::item:selected {{ background-color: {sel_bg}; color: {sel_fg}; border: none; }}"
        f"QListWidget::item:focus {{ outline: none; border: none; }}"
    )

_QUERY_LIST_STYLE = _make_list_style(_PURPLE, _PURPLE_LIGHT, _PURPLE_DEEP)
_TABLE_LIST_STYLE = _make_list_style(_PURPLE, _PURPLE_LIGHT, _PURPLE_DEEP)
_FIELD_LIST_STYLE = _make_list_style(_PURPLE, _PURPLE_LIGHT, _PURPLE_DEEP)

_HEADER_STYLE = (
    f"QLabel {{ color: white; font-size: 8pt; font-weight: bold;"
    f" padding: 2px 4px; background-color: {_PURPLE};"
    f" border: 1px solid {_PURPLE_DARK}; border-radius: 2px; }}"
)

_SEARCH_STYLE = (
    f"QLineEdit {{ border: 1px solid {_PURPLE}; border-radius: 2px;"
    f" padding: 1px 4px; font-size: 8pt; }}"
    f"QLineEdit:focus {{ border: 1px solid {_PURPLE_DARK}; }}"
)

_BTN_STYLE = (
    f"QPushButton {{ background-color: {_PURPLE_BG}; color: {_PURPLE_DARK};"
    f" border: 1px solid {_PURPLE}; border-radius: 2px;"
    f" padding: 1px 6px; font-size: 8pt; }}"
    f"QPushButton:hover {{ background-color: {_PURPLE_LIGHT}; }}"
)

_NEW_BTN_STYLE = (
    f"QPushButton {{ background-color: {_PURPLE}; color: white;"
    f" border: 1px solid {_PURPLE_DARK}; border-radius: 2px;"
    f" padding: 1px 6px; font-size: 8pt; font-weight: bold; }}"
    f"QPushButton:hover {{ background-color: {_PURPLE_HOVER}; }}"
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
    """Side panel: Query list | Tables list | Fields list with teal theme."""
    field_requested = pyqtSignal(str, str, str, str)  # table, column, type, display
    tables_changed = pyqtSignal(list)  # emitted when tables added via + Table
    query_clicked = pyqtSignal(str)    # query name clicked → load it
    new_query_requested = pyqtSignal()  # user clicked "+ New"
    splitter_changed = pyqtSignal()     # internal column widths changed

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumWidth(300)
        self.setMaximumWidth(600)

        self._dsn: str = ""
        self._tables: list[str] = []
        self._display_names: dict[str, str] = {}
        self._current_table: str = ""
        self._loader: _FieldLoaderThread | None = None
        self._field_cache: dict[str, list[tuple]] = {}
        self._common_table_cols: dict[str, list[tuple]] = {}
        self._pending_sizes: list[int] | None = None
        self._last_good_sizes: list[int] | None = None

        self._build_ui()

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.setHandleWidth(4)
        splitter.setStyleSheet(
            f"QSplitter::handle {{ background: {_PURPLE_LIGHT}; }}"
            f"QSplitter::handle:hover {{ background: {_PURPLE}; }}")

        # ── Left: Queries ────────────────────────────────────────
        queries_frame = QWidget()
        queries_frame.setStyleSheet(f"QWidget {{ background-color: {_PURPLE_BG}; }}")
        ql = QVBoxLayout(queries_frame)
        ql.setContentsMargins(4, 4, 2, 4)
        ql.setSpacing(3)

        lbl_queries = QLabel("QDesign")
        lbl_queries.setStyleSheet(_HEADER_STYLE)
        ql.addWidget(lbl_queries)

        self.txt_query_search = QLineEdit()
        self.txt_query_search.setFont(_FONT_SMALL)
        self.txt_query_search.setPlaceholderText("Search queries...")
        self.txt_query_search.setClearButtonEnabled(True)
        self.txt_query_search.setFixedHeight(22)
        self.txt_query_search.setStyleSheet(_SEARCH_STYLE)
        self.txt_query_search.textChanged.connect(self._filter_queries)
        ql.addWidget(self.txt_query_search)

        self.list_queries = QListWidget()
        self.list_queries.setFont(_FONT)
        self.list_queries.setStyleSheet(_QUERY_LIST_STYLE)
        self.list_queries.setItemDelegate(TightItemDelegate(self.list_queries))
        self.list_queries.setUniformItemSizes(True)
        self.list_queries.setSelectionMode(
            QAbstractItemView.SelectionMode.SingleSelection)
        self.list_queries.itemClicked.connect(self._on_query_clicked)
        ql.addWidget(self.list_queries)

        btn_new = QPushButton("+ New")
        btn_new.setFont(_FONT_SMALL)
        btn_new.setFixedHeight(20)
        btn_new.setStyleSheet(_NEW_BTN_STYLE)
        btn_new.clicked.connect(self.new_query_requested)
        ql.addWidget(btn_new)

        splitter.addWidget(queries_frame)

        # ── Middle: Tables ───────────────────────────────────────
        tables_frame = QWidget()
        tables_frame.setStyleSheet(f"QWidget {{ background-color: {_PURPLE_BG}; }}")
        tl = QVBoxLayout(tables_frame)
        tl.setContentsMargins(2, 4, 2, 4)
        tl.setSpacing(3)

        lbl_tables = QLabel("Tables")
        lbl_tables.setStyleSheet(_HEADER_STYLE)
        tl.addWidget(lbl_tables)

        self.txt_table_search = QLineEdit()
        self.txt_table_search.setFont(_FONT_SMALL)
        self.txt_table_search.setPlaceholderText("Search tables...")
        self.txt_table_search.setClearButtonEnabled(True)
        self.txt_table_search.setFixedHeight(22)
        self.txt_table_search.setStyleSheet(_SEARCH_STYLE)
        self.txt_table_search.textChanged.connect(self._filter_tables)
        tl.addWidget(self.txt_table_search)

        self.list_tables = QListWidget()
        self.list_tables.setFont(_FONT)
        self.list_tables.setStyleSheet(_TABLE_LIST_STYLE)
        self.list_tables.setItemDelegate(TightItemDelegate(self.list_tables))
        self.list_tables.setUniformItemSizes(True)
        self.list_tables.setSelectionMode(
            QAbstractItemView.SelectionMode.SingleSelection)
        self.list_tables.currentItemChanged.connect(self._on_table_selected)
        self.list_tables.setContextMenuPolicy(
            Qt.ContextMenuPolicy.CustomContextMenu)
        self.list_tables.customContextMenuRequested.connect(
            self._show_table_context_menu)
        tl.addWidget(self.list_tables)

        # ── + Table / View buttons ─────────────────────────────────
        tbl_btns = QHBoxLayout()
        tbl_btns.setContentsMargins(0, 0, 0, 0)
        tbl_btns.setSpacing(3)

        self.btn_add_table = QPushButton("+ Table")
        self.btn_add_table.setFont(_FONT_SMALL)
        self.btn_add_table.setFixedHeight(20)
        self.btn_add_table.setStyleSheet(_BTN_STYLE)
        self.btn_add_table.clicked.connect(self._on_add_table)
        tbl_btns.addWidget(self.btn_add_table)

        self.btn_view_table = QPushButton("View")
        self.btn_view_table.setFont(_FONT_SMALL)
        self.btn_view_table.setFixedHeight(20)
        self.btn_view_table.setStyleSheet(
            f"QPushButton {{ background-color: {_PURPLE_DARK}; color: white;"
            f" border: 1px solid {_PURPLE_DEEP}; border-radius: 2px;"
            f" padding: 1px 6px; font-size: 8pt; }}"
            f"QPushButton:hover {{ background-color: {_PURPLE}; }}")
        self.btn_view_table.setToolTip("Preview first 1000 rows")
        self.btn_view_table.clicked.connect(self._on_view_table)
        tbl_btns.addWidget(self.btn_view_table)

        tbl_btns.addStretch()
        tl.addLayout(tbl_btns)

        splitter.addWidget(tables_frame)

        # ── Right: Fields ────────────────────────────────────────
        fields_frame = QWidget()
        fields_frame.setStyleSheet(f"QWidget {{ background-color: {_PURPLE_BG}; }}")
        fl = QVBoxLayout(fields_frame)
        fl.setContentsMargins(2, 4, 4, 4)
        fl.setSpacing(3)

        lbl_fields = QLabel("Fields")
        lbl_fields.setStyleSheet(_HEADER_STYLE)
        fl.addWidget(lbl_fields)

        self.txt_search = QLineEdit()
        self.txt_search.setFont(_FONT_SMALL)
        self.txt_search.setPlaceholderText("Search fields...")
        self.txt_search.setClearButtonEnabled(True)
        self.txt_search.setFixedHeight(22)
        self.txt_search.setStyleSheet(_SEARCH_STYLE)
        self.txt_search.textChanged.connect(self._filter_fields)
        fl.addWidget(self.txt_search)

        self.list_fields = DraggableFieldList()
        self.list_fields.setFont(_FONT)
        self.list_fields.setStyleSheet(_FIELD_LIST_STYLE)
        self.list_fields.setItemDelegate(TightItemDelegate(self.list_fields))
        self.list_fields.setUniformItemSizes(True)
        self.list_fields.itemDoubleClicked.connect(self._on_field_double_clicked)
        fl.addWidget(self.list_fields)

        self.lbl_status = QLabel("")
        self.lbl_status.setFont(_FONT_SMALL)
        self.lbl_status.setStyleSheet(f"color: {_PURPLE_DARK};")
        fl.addWidget(self.lbl_status)

        splitter.addWidget(fields_frame)

        splitter.setStretchFactor(0, 1)  # queries
        splitter.setStretchFactor(1, 1)  # tables
        splitter.setStretchFactor(2, 3)  # fields

        self._splitter = splitter
        splitter.splitterMoved.connect(self._on_splitter_moved)
        root.addWidget(splitter)

    # ── State persistence ─────────────────────────────────────────

    def _on_splitter_moved(self, pos, index):
        self._last_good_sizes = self._splitter.sizes()
        self.splitter_changed.emit()

    def get_state(self) -> dict:
        sizes = self._splitter.sizes()
        if all(s == 0 for s in sizes) and self._last_good_sizes:
            sizes = self._last_good_sizes
        return {"splitter_sizes": sizes}

    def set_state(self, state: dict):
        sizes = state.get("splitter_sizes")
        if sizes and len(sizes) == 3 and any(s > 0 for s in sizes):
            self._pending_sizes = list(sizes)
            self._last_good_sizes = list(sizes)
            self._splitter.setSizes(sizes)

    def showEvent(self, event):
        super().showEvent(event)
        if self._pending_sizes:
            from PyQt6.QtCore import QTimer
            sizes = self._pending_sizes
            self._pending_sizes = None
            QTimer.singleShot(0, lambda: self._splitter.setSizes(sizes))

    # ── Query list API ────────────────────────────────────────────

    def set_queries(self, names: list[str]):
        """Populate the query list with saved query names."""
        self.list_queries.blockSignals(True)
        self.list_queries.clear()
        for name in sorted(names, key=str.lower):
            self.list_queries.addItem(name)
        self.list_queries.blockSignals(False)

    def highlight_query(self, name: str):
        """Select the given query name in the list (no signal)."""
        self.list_queries.blockSignals(True)
        for i in range(self.list_queries.count()):
            item = self.list_queries.item(i)
            item.setSelected(item.text() == name)
        self.list_queries.blockSignals(False)

    def _filter_queries(self, text: str):
        filt = text.strip().lower()
        for i in range(self.list_queries.count()):
            item = self.list_queries.item(i)
            item.setHidden(filt not in item.text().lower() if filt else False)

    def _on_query_clicked(self, item):
        self.query_clicked.emit(item.text())

    def _filter_tables(self, text: str):
        filt = text.strip().lower()
        for i in range(self.list_tables.count()):
            item = self.list_tables.item(i)
            item.setHidden(filt not in item.text().lower() if filt else False)

    # ── Public API ────────────────────────────────────────────────

    def set_group(self, dsn: str, tables: list[str],
                  display_names: dict[str, str]):
        """Load tables and fields from a dynamic group."""
        self._dsn = dsn
        self._tables = list(tables)
        self._display_names = display_names
        self._field_cache.clear()
        self._current_table = ""

        self._rebuild_table_list()

    def set_common_tables(
        self, common_cols: dict[str, list[tuple[str, str]]]
    ):
        """Update common table entries in the table list.

        Args:
            common_cols: {table_name: [(col_name, type_name), ...]}
        """
        # Remove old common table names from regular tables list
        old_names = set(self._common_table_cols.keys())
        self._tables = [t for t in self._tables if t not in old_names]
        self._common_table_cols = dict(common_cols)

        # Pre-populate field cache for common tables
        for name, cols in common_cols.items():
            # Convert (col_name, type_name) to the standard 4-tuple format
            self._field_cache[name] = [
                (col_name, type_name, "", "") for col_name, type_name in cols
            ]

        self._rebuild_table_list()

    def _rebuild_table_list(self):
        """Rebuild the table list widget with DB tables + common tables."""
        prev = self._current_table
        self.list_tables.clear()
        self.list_fields.clear()
        self.lbl_status.setText("")

        # Add regular DB tables
        for t in self._tables:
            self.list_tables.addItem(t)

        # Add common tables with grey styling
        ct_names = sorted(self._common_table_cols.keys())
        for name in ct_names:
            item = QListWidgetItem(f"\u25cb {name}")  # small circle prefix
            item.setForeground(QBrush(QColor("#666666")))
            item.setBackground(QBrush(QColor("#F0F0F0")))
            item.setToolTip(f"Common Table: {name}")
            item.setData(Qt.ItemDataRole.UserRole, name)  # store real name
            self.list_tables.addItem(item)

        # Restore selection or default to first
        if prev:
            for i in range(self.list_tables.count()):
                itm = self.list_tables.item(i)
                real = itm.data(Qt.ItemDataRole.UserRole) or itm.text()
                if real == prev:
                    self.list_tables.setCurrentRow(i)
                    return
        if self.list_tables.count() > 0:
            self.list_tables.setCurrentRow(0)

    def clear(self):
        """Clear the panel."""
        self._dsn = ""
        self._tables = []
        self._display_names = {}
        self._field_cache.clear()
        self._common_table_cols.clear()
        self._current_table = ""
        self.list_tables.clear()
        self.list_fields.clear()
        self.lbl_status.setText("")

    # ── Table selection ──────────────────────────────────────────

    def _on_table_selected(self, current, previous):
        if current is None:
            return
        # Use UserRole data for common tables (stores the real name)
        table = current.data(Qt.ItemDataRole.UserRole) or current.text()
        if table == self._current_table:
            return
        self._current_table = table
        self._load_fields(table)

    def _load_fields(self, table: str):
        # Common tables and cached tables can be served immediately
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

    # ── Table context menu / buttons ─────────────────────────────

    def _show_table_context_menu(self, pos):
        """Right-click a table → show field details in a popup."""
        item = self.list_tables.itemAt(pos)
        if item is None:
            return
        table = item.text()
        # Load fields first (if not cached)
        if table not in self._field_cache:
            self._load_fields(table)
            return  # will populate once loaded asynchronously

        columns = self._field_cache[table]
        menu = QMenu(self)

        # Build a mini summary of fields
        act_view = menu.addAction(f"View  ({len(columns)} fields)")
        menu.addSeparator()
        for col_name, type_name, size, nullable in columns[:20]:
            menu.addAction(f"  {col_name}  ({type_name})")
        if len(columns) > 20:
            menu.addAction(f"  ... {len(columns) - 20} more")

        chosen = menu.exec(self.list_tables.mapToGlobal(pos))
        if chosen is act_view:
            self._on_view_table()

    def _on_add_table(self):
        """Open the Add Table dialog to add more tables from the DSN."""
        if not self._dsn:
            return
        from .dialogs.tables_dialog import _AddTableDialog
        dlg = _AddTableDialog(self._dsn, self._tables, self)
        from PyQt6.QtWidgets import QDialog
        if dlg.exec() == QDialog.DialogCode.Accepted:
            new_tables = dlg.get_selected()
            for t in new_tables:
                if t not in self._tables:
                    self._tables.append(t)
            self.list_tables.clear()
            self.list_tables.addItems(self._tables)
            self.tables_changed.emit(self._tables)

    def _on_view_table(self):
        """Preview first 1000 rows of the selected table."""
        current = self.list_tables.currentItem()
        if current is None:
            return
        if not self._dsn:
            return
        table = current.text()
        from .dialogs.tables_dialog import _TablePreviewDialog
        dlg = _TablePreviewDialog(self._dsn, table, self)
        dlg.show()
