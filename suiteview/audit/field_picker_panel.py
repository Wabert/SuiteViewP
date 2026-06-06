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
    QListWidget, QAbstractItemView, QSplitter, QPushButton, QMenu,
    QComboBox,
    QListWidgetItem,
    QDialog,
)

from .dialogs.tables_dialog import _clean_odbc_identifier
from .tabs._styles import TightItemDelegate

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)

_FONT = QFont("Segoe UI", 9)
_FONT_BOLD = QFont("Segoe UI", 9, QFont.Weight.Bold)
_FONT_SMALL = QFont("Segoe UI", 8)

FIELD_DRAG_MIME = "application/x-audit-field-drag"


def _indexed_column_names(cursor, table: str, schema: str | None) -> set[str]:
    names: set[str] = set()
    for loader in (cursor.primaryKeys, cursor.statistics):
        try:
            for row in loader(table=table, schema=schema):
                name = _clean_odbc_identifier(getattr(row, "column_name", ""))
                if name:
                    names.add(name.upper())
        except Exception:
            logger.debug("Could not load key/index metadata for %s.%s", schema, table, exc_info=True)
    if schema and not names:
        schema_lit = schema.replace("'", "''").upper()
        table_lit = table.replace("'", "''").upper()
        try:
            cursor.execute(
                "SELECT DISTINCT K.COLNAME "
                "FROM SYSIBM.SYSINDEXES I "
                "JOIN SYSIBM.SYSKEYS K "
                "ON K.IXCREATOR = I.CREATOR AND K.IXNAME = I.NAME "
                f"WHERE I.TBCREATOR = '{schema_lit}' AND I.TBNAME = '{table_lit}'"
            )
            for row in cursor.fetchall():
                name = _clean_odbc_identifier(getattr(row, "COLNAME", "") or row[0])
                if name:
                    names.add(name.upper())
        except Exception:
            logger.debug("Could not load DB2 index catalog metadata for %s.%s", schema, table, exc_info=True)
    return names

# ── Blue/gold builder styles ─────────────────────────────────────
_BLUE = "#1E5BA8"
_BLUE_DARK = "#0A2A5C"
_BLUE_LIGHT = "#D9E8F7"
_BLUE_BG = "#EDF3FA"
_BLUE_HOVER = "#2A6BC4"
_GOLD = "#D4AF37"

def _make_list_style(border: str, sel_bg: str, sel_fg: str) -> str:
    return (
        f"QListWidget {{ border: 1px solid {border}; background-color: white;"
        f" font-size: 9pt; outline: none; }}"
        f"QListWidget::item {{ padding: 0px 2px; border: none; }}"
        f"QListWidget::item:selected {{ background-color: {sel_bg}; color: {sel_fg}; border: none; }}"
        f"QListWidget::item:focus {{ outline: none; border: none; }}"
    )

_TABLE_LIST_STYLE = _make_list_style(_BLUE, _BLUE_LIGHT, _BLUE_DARK)
_FIELD_LIST_STYLE = _make_list_style(_BLUE, _BLUE_LIGHT, _BLUE_DARK)

_HEADER_STYLE = (
    f"QLabel, QPushButton {{ color: white; font-size: 8pt; font-weight: bold;"
    f" padding: 2px 4px; background-color: {_BLUE};"
    f" border: 1px solid {_GOLD}; border-radius: 2px; }}"
    f"QPushButton:hover {{ background-color: {_BLUE_HOVER}; }}"
)

_SEARCH_STYLE = (
    f"QLineEdit {{ border: 1px solid {_BLUE}; border-radius: 2px;"
    f" padding: 1px 4px; font-size: 8pt; }}"
    f"QLineEdit:focus {{ border: 1px solid {_GOLD}; }}"
)

_BTN_STYLE = (
    f"QPushButton {{ background-color: {_BLUE_BG}; color: {_BLUE_DARK};"
    f" border: 1px solid {_BLUE}; border-radius: 2px;"
    f" padding: 1px 6px; font-size: 8pt; }}"
    f"QPushButton:hover {{ background-color: {_BLUE_LIGHT}; }}"
)

_NEW_BTN_STYLE = (
    f"QPushButton {{ background-color: {_BLUE_DARK}; color: {_GOLD};"
    f" border: 1px solid {_GOLD}; border-radius: 2px;"
    f" padding: 1px 6px; font-size: 8pt; font-weight: bold; }}"
    f"QPushButton:hover {{ background-color: {_BLUE}; }}"
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
            parts = [_clean_odbc_identifier(part) for part in self.table_name.split(".", 1)]
            if len(parts) == 2:
                schema, table = parts
            else:
                schema, table = None, parts[0]
            indexed_names = _indexed_column_names(cursor, table, schema)
            columns = []
            for row in cursor.columns(table=table, schema=schema):
                column_name = _clean_odbc_identifier(row.column_name)
                columns.append((
                    column_name,
                    _clean_odbc_identifier(row.type_name),
                    row.column_size,
                    "Yes" if row.nullable else "No",
                    str(column_name).upper() in indexed_names,
                ))
            conn.close()
            self.columns_loaded.emit(self.table_name, columns)
        except Exception as exc:
            self.error_occurred.emit(str(exc))


class _TableLoaderThread(QThread):
    """Background thread to fetch table metadata from ODBC."""
    tables_loaded = pyqtSignal(list)
    error_occurred = pyqtSignal(str)

    def __init__(self, dsn: str, parent=None):
        super().__init__(parent)
        self.dsn = dsn

    def run(self):
        try:
            conn = pyodbc.connect(f"DSN={self.dsn}", autocommit=True, timeout=15)
            cursor = conn.cursor()
            tables = []
            for table_type in ("TABLE", "VIEW"):
                try:
                    rows = cursor.tables(tableType=table_type)
                    for row in rows:
                        schema = _clean_odbc_identifier(getattr(row, "table_schem", ""))
                        name = _clean_odbc_identifier(getattr(row, "table_name", ""))
                        if name:
                            tables.append(f"{schema}.{name}" if schema else name)
                except Exception:
                    logger.debug(
                        "Visual Query SQL Assist skipped %s metadata for %s",
                        table_type,
                        self.dsn,
                        exc_info=True,
                    )
            conn.close()
            self.tables_loaded.emit(sorted(set(tables), key=str.lower))
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
        mime.setText(", ".join(line.split("|", 3)[1] for line in lines))
        drag.setMimeData(mime)
        drag.exec(Qt.DropAction.CopyAction)


class FieldPickerPanel(QWidget):
    """Side panel: Query list | Tables list | Fields list with teal theme."""
    field_requested = pyqtSignal(str, str, str, str)  # table, column, type, display
    table_requested = pyqtSignal(str)  # table double-clicked for SQL insertion
    tables_changed = pyqtSignal(list)  # emitted when tables added via + Table
    pinned_tables_changed = pyqtSignal(list)  # per-query pinned table list changed
    common_table_requested = pyqtSignal(str)  # common table name selected from picker
    common_table_remove_requested = pyqtSignal(str)  # common table name removed from picker
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
        self._table_loader: _TableLoaderThread | None = None
        self._field_cache: dict[str, list[tuple]] = {}
        self._common_table_cols: dict[str, list[tuple]] = {}
        self._connections: list[tuple[str, str]] = []
        self._fields_sort_mode = "native"
        self._preferred_table: str = ""
        self._pinned_tables: set[str] = set()
        self._pending_sizes: list[int] | None = None
        self._last_good_sizes: list[int] | None = None

        self._build_ui()

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(4, 4, 4, 4)
        root.setSpacing(4)

        self.setStyleSheet(f"QWidget {{ background-color: {_BLUE_BG}; }}")

        lbl_header = QLabel("SQL Assist")
        lbl_header.setStyleSheet(_HEADER_STYLE)
        root.addWidget(lbl_header)

        connection_row = QHBoxLayout()
        connection_row.setContentsMargins(0, 0, 0, 0)
        connection_row.setSpacing(4)
        lbl_connection = QLabel("ODBC")
        lbl_connection.setFont(_FONT_BOLD)
        lbl_connection.setStyleSheet(f"color: {_BLUE_DARK};")
        self.cmb_connection = QComboBox()
        self.cmb_connection.setFont(_FONT_SMALL)
        self.cmb_connection.setFixedHeight(24)
        self.cmb_connection.currentTextChanged.connect(self._on_connection_changed)
        connection_row.addWidget(lbl_connection)
        connection_row.addWidget(self.cmb_connection, 1)
        root.addLayout(connection_row)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.setHandleWidth(4)
        splitter.setStyleSheet(
            f"QSplitter::handle {{ background: {_BLUE_LIGHT}; }}"
            f"QSplitter::handle:hover {{ background: {_BLUE}; }}")

        # ── Middle: Tables ───────────────────────────────────────
        tables_frame = QWidget()
        tables_frame.setStyleSheet(f"QWidget {{ background-color: {_BLUE_BG}; }}")
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
        self.list_tables.itemDoubleClicked.connect(self._on_table_double_clicked)
        tl.addWidget(self.list_tables)

        self.btn_common_table = QPushButton("Common Table")
        self.btn_common_table.setFont(_FONT_BOLD)
        self.btn_common_table.setFixedHeight(24)
        self.btn_common_table.setStyleSheet(_NEW_BTN_STYLE)
        self.btn_common_table.clicked.connect(self._show_common_table_dialog)
        tl.addWidget(self.btn_common_table)

        splitter.addWidget(tables_frame)

        # ── Right: Fields ────────────────────────────────────────
        fields_frame = QWidget()
        fields_frame.setStyleSheet(f"QWidget {{ background-color: {_BLUE_BG}; }}")
        fl = QVBoxLayout(fields_frame)
        fl.setContentsMargins(2, 4, 4, 4)
        fl.setSpacing(3)

        self.btn_fields_header = QPushButton("Fields")
        self.btn_fields_header.setFont(_FONT_BOLD)
        self.btn_fields_header.setStyleSheet(_HEADER_STYLE)
        self.btn_fields_header.setFixedHeight(22)
        self.btn_fields_header.clicked.connect(self._toggle_fields_sort)
        fl.addWidget(self.btn_fields_header)

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
        self.lbl_status.setVisible(False)

        splitter.addWidget(fields_frame)

        splitter.setStretchFactor(0, 1)  # tables
        splitter.setStretchFactor(1, 1)  # fields

        self._splitter = splitter
        splitter.splitterMoved.connect(self._on_splitter_moved)
        root.addWidget(splitter, 1)

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
        if sizes and len(sizes) in (2, 3) and any(s > 0 for s in sizes):
            sizes = list(sizes[-2:])
            self._pending_sizes = sizes
            self._last_good_sizes = sizes
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
        """Compatibility hook; saved queries are opened from the Object Browser."""
        return

    def highlight_query(self, name: str):
        """Compatibility hook; the picker no longer shows a saved-query list."""
        return

    def _filter_queries(self, text: str):
        return

    def _on_query_clicked(self, item):
        self.query_clicked.emit(item.text())

    def _filter_tables(self, text: str):
        filt = text.strip().lower()
        for i in range(self.list_tables.count()):
            item = self.list_tables.item(i)
            if item.data(Qt.ItemDataRole.UserRole) == "__separator__":
                item.setHidden(False)
                continue
            table = item.data(Qt.ItemDataRole.UserRole) or item.text()
            if str(table) in self._pinned_tables or str(table) in self._common_table_cols:
                item.setHidden(False)
                continue
            item.setHidden(filt not in str(table).lower() if filt else False)

    # ── Public API ────────────────────────────────────────────────

    def set_connection_options(self, connections: list, current: str = ""):
        """Set the ODBC connections available to the Visual Query SQL Assist picker."""
        selected = current or self.current_connection()
        previous_dsn = self._dsn
        self.cmb_connection.blockSignals(True)
        self.cmb_connection.clear()
        self._connections = []
        for connection in connections:
            if isinstance(connection, tuple):
                label, dsn = connection
            else:
                label = str(connection)
                dsn = str(connection)
            self._connections.append((str(label), str(dsn)))
            self.cmb_connection.addItem(str(label), str(dsn))
        selected_index = -1
        if selected:
            for row in range(self.cmb_connection.count()):
                if self.cmb_connection.itemData(row) == selected or self.cmb_connection.itemText(row) == selected:
                    selected_index = row
                    break
        if selected_index < 0 and self.cmb_connection.count() > 0:
            selected_index = 0
        if selected_index >= 0:
            self.cmb_connection.setCurrentIndex(selected_index)
        self.cmb_connection.blockSignals(False)
        dsn = self.current_connection()
        if dsn and dsn != previous_dsn:
            self._dsn = dsn
            self._display_names = {}
            self._field_cache.clear()
            self._common_table_cols.clear()
            self._current_table = ""
            self._load_tables(dsn)

    def current_connection(self) -> str:
        data = self.cmb_connection.currentData()
        return str(data or self.cmb_connection.currentText()).strip()

    def current_connection_label(self) -> str:
        return self.cmb_connection.currentText().strip()

    def _on_connection_changed(self, connection: str):
        dsn = self.current_connection()
        if not dsn or dsn == self._dsn:
            return
        self._dsn = dsn
        self._display_names = {}
        self._field_cache.clear()
        self._common_table_cols.clear()
        self._current_table = ""
        self._load_tables(dsn)

    def _load_tables(self, dsn: str):
        self.list_tables.clear()
        self.list_fields.clear()
        self.lbl_status.setText(f"Loading tables for {dsn}...")
        self._table_loader = _TableLoaderThread(dsn, self)
        self._table_loader.tables_loaded.connect(self._on_tables_loaded)
        self._table_loader.error_occurred.connect(self._on_tables_error)
        self._table_loader.start()

    def _on_tables_loaded(self, tables: list[str]):
        self._tables = list(tables)
        self._rebuild_table_list()
        self.lbl_status.setText("")
        self._table_loader = None

    def _on_tables_error(self, message: str):
        self.list_tables.clear()
        self.list_fields.clear()
        self.lbl_status.setText("Error loading tables")
        logger.warning("Visual Query SQL Assist table load failed: %s", message)
        self._table_loader = None

    def set_group(self, dsn: str, tables: list[str],
                  display_names: dict[str, str],
                  preferred_table: str = "",
                  pinned_tables: list[str] | None = None):
        """Load tables and fields from a dynamic group."""
        previous_dsn = self._dsn
        self._dsn = dsn
        self._display_names = display_names
        self._preferred_table = preferred_table or (tables[0] if tables else "")
        self._pinned_tables = set(pinned_tables or [])
        self.set_connection_options(self._connections, dsn)

        if dsn and dsn != previous_dsn:
            self._field_cache.clear()
            self._current_table = ""
            self._load_tables(dsn)
        elif not self._tables:
            self._tables = list(tables)
            self._rebuild_table_list()
        else:
            self._select_table(self._preferred_table)

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
        preferred = self._preferred_table or self._current_table
        self.list_tables.clear()
        self.list_fields.clear()
        self.lbl_status.setText("")

        ct_names = sorted(self._common_table_cols.keys(), key=str.lower)
        pinned_names = sorted(
            (set(self._pinned_tables) | set(ct_names)) & (set(self._tables) | set(ct_names)),
            key=str.lower,
        )
        regular_names = [t for t in self._tables if t not in pinned_names]

        for name in pinned_names:
            self._add_table_item(name, pinned=True, common=name in self._common_table_cols)

        if pinned_names and regular_names:
            sep = QListWidgetItem("────────────────────")
            sep.setFlags(Qt.ItemFlag.NoItemFlags)
            sep.setForeground(QBrush(QColor("#7A8CA5")))
            sep.setData(Qt.ItemDataRole.UserRole, "__separator__")
            self.list_tables.addItem(sep)

        for t in regular_names:
            self._add_table_item(t, pinned=False, common=False)

        # Common tables already pinned above. Keep this for common tables that
        # are not in the ODBC table list.
        for name in ct_names:
            if name not in pinned_names:
                self._add_table_item(name, pinned=True, common=True)

        # Restore selection, prefer a used query table, or default to first
        if self._select_table(preferred):
            return
        if self.list_tables.count() > 0:
            self.list_tables.setCurrentRow(0)

    def _add_table_item(self, table: str, *, pinned: bool, common: bool):
        label = table
        if common:
            label = f"○ {table}"
        item = QListWidgetItem(label)
        item.setData(Qt.ItemDataRole.UserRole, table)
        if common:
            item.setForeground(QBrush(QColor("#4F5F73")))
            item.setBackground(QBrush(QColor("#F0F4FA")))
            item.setToolTip(f"Pinned Common Table: {table}")
        self.list_tables.addItem(item)

    def _select_table(self, table_name: str) -> bool:
        if not table_name:
            return False
        for i in range(self.list_tables.count()):
            item = self.list_tables.item(i)
            real = item.data(Qt.ItemDataRole.UserRole) or item.text()
            if real == "__separator__":
                continue
            if real == table_name:
                self.list_tables.setCurrentRow(i)
                self._preferred_table = ""
                return True
        return False

    def clear(self):
        """Clear the panel."""
        self._dsn = ""
        self._tables = []
        self._display_names = {}
        self._field_cache.clear()
        self._common_table_cols.clear()
        self._pinned_tables.clear()
        self._current_table = ""
        self.list_tables.clear()
        self.list_fields.clear()
        self.lbl_status.setText("")
        self.txt_table_search.clear()
        self.txt_search.clear()

    # ── Table selection ──────────────────────────────────────────

    def _on_table_selected(self, current, previous):
        if current is None:
            return
        # Use UserRole data for common tables (stores the real name)
        table = current.data(Qt.ItemDataRole.UserRole) or current.text()
        if table == "__separator__":
            return
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
        ordered_columns = self._ordered_fields(columns)
        for column in ordered_columns:
            col_name = column[0]
            type_name = column[1] if len(column) > 1 else ""
            is_key = bool(column[4]) if len(column) > 4 else False
            key = f"{table}.{col_name}"
            display = self._display_names.get(key, col_name)
            # Show display name with column in parens
            if display != col_name:
                label = f"{display}  ({col_name})"
            else:
                label = col_name
            item = QListWidgetItem(label)
            if is_key:
                font = item.font()
                font.setWeight(QFont.Weight.Bold)
                item.setFont(font)
                item.setToolTip("Key/index field")
            self.list_fields.addItem(item)
            field_data[label] = (table, col_name, type_name, display)
        self.list_fields.set_field_data(field_data)
        self.lbl_status.setText("")

    def _ordered_fields(self, columns: list[tuple]) -> list[tuple]:
        if self._fields_sort_mode == "native":
            return list(columns)
        return sorted(
            columns,
            key=lambda column: str(column[0]).lower(),
            reverse=self._fields_sort_mode == "desc",
        )

    def _toggle_fields_sort(self):
        next_mode = {"native": "asc", "asc": "desc", "desc": "native"}
        self._fields_sort_mode = next_mode[self._fields_sort_mode]
        labels = {"native": "Fields", "asc": "Fields ↑", "desc": "Fields ↓"}
        self.btn_fields_header.setText(labels[self._fields_sort_mode])
        if self._current_table:
            self._load_fields(self._current_table)

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

    def _on_table_double_clicked(self, item):
        table = item.data(Qt.ItemDataRole.UserRole) or item.text()
        if table and table != "__separator__":
            self.table_requested.emit(str(table))

    # ── Table context menu / buttons ─────────────────────────────

    def _show_table_context_menu(self, pos):
        """Right-click a table → pin/unpin or show field details."""
        item = self.list_tables.itemAt(pos)
        if item is None:
            return
        table = item.data(Qt.ItemDataRole.UserRole) or item.text()
        if table == "__separator__":
            return

        menu = QMenu(self)
        is_common = table in self._common_table_cols
        if not is_common:
            act_pin = menu.addAction("Unpin Table" if table in self._pinned_tables else "Pin Table")
            act_remove_common = None
            act_preview = menu.addAction("View Top 1000 Rows")
        else:
            act_pin = None
            act_remove_common = menu.addAction("Remove Common Table")
            act_preview = None

        chosen = menu.exec(self.list_tables.mapToGlobal(pos))
        if chosen is None:
            return
        if act_pin is not None and chosen is act_pin:
            if table in self._pinned_tables:
                self._pinned_tables.remove(table)
            else:
                self._pinned_tables.add(table)
            self._preferred_table = table
            self._rebuild_table_list()
            self.pinned_tables_changed.emit(sorted(self._pinned_tables, key=str.lower))
            return
        if act_remove_common is not None and chosen is act_remove_common:
            self.common_table_remove_requested.emit(table)
            return
        if act_preview is not None and chosen is act_preview:
            self._preview_table(table)

    def _preview_table(self, table: str):
        if not self._dsn:
            return
        from suiteview.audit.dialogs.tables_dialog import _TablePreviewDialog
        dlg = _TablePreviewDialog(self._dsn, table, self)
        dlg.show()

    def _show_common_table_dialog(self):
        from suiteview.audit import common_table_store

        dialog = QDialog(self)
        dialog.setWindowTitle("Add Common Table")
        layout = QVBoxLayout(dialog)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(6)

        lst = QListWidget(dialog)
        lst.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        lst.setStyleSheet(_TABLE_LIST_STYLE)
        for ct in common_table_store.list_tables():
            item = QListWidgetItem(ct.name)
            item.setToolTip(
                f"{ct.description}\nColumns: {', '.join(ct.column_names)}\nRows: {ct.row_count}"
            )
            lst.addItem(item)
        layout.addWidget(lst, 1)

        buttons = QHBoxLayout()
        btn_manage = QPushButton("Manage")
        btn_manage.setStyleSheet(_BTN_STYLE)
        btn_add = QPushButton("Add")
        btn_add.setStyleSheet(_NEW_BTN_STYLE)
        btn_close = QPushButton("Close")
        btn_close.setStyleSheet(_BTN_STYLE)
        buttons.addWidget(btn_manage)
        buttons.addStretch()
        buttons.addWidget(btn_add)
        buttons.addWidget(btn_close)
        layout.addLayout(buttons)

        def refresh():
            lst.clear()
            for ct in common_table_store.list_tables():
                item = QListWidgetItem(ct.name)
                item.setToolTip(
                    f"{ct.description}\nColumns: {', '.join(ct.column_names)}\nRows: {ct.row_count}"
                )
                lst.addItem(item)

        def add_selected():
            for selected in lst.selectedItems():
                self.common_table_requested.emit(selected.text())
            dialog.accept()

        def manage():
            from suiteview.audit.common_table_dialog import CommonTableDialog
            manager = CommonTableDialog.show_instance(dialog)
            manager.tables_changed.connect(refresh)

        btn_add.clicked.connect(add_selected)
        btn_close.clicked.connect(dialog.reject)
        btn_manage.clicked.connect(manage)
        lst.itemDoubleClicked.connect(lambda _item: add_selected())
        dialog.resize(320, 420)
        dialog.exec()

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
        table = current.data(Qt.ItemDataRole.UserRole) or current.text()
        from .dialogs.tables_dialog import _TablePreviewDialog
        dlg = _TablePreviewDialog(self._dsn, table, self)
        dlg.show()
