"""
Tables Dialog — browse tables and fields in a dynamic group.

Left panel: list of tables (add/remove).
Right panel: field list for selected table with display name editing.
Supports drag-out of fields onto tab forms, and double-click to auto-place.
"""
from __future__ import annotations

import logging
from typing import TYPE_CHECKING

import pyodbc
from PyQt6.QtCore import Qt, QMimeData, QPoint, QThread, pyqtSignal
from PyQt6.QtGui import QFont, QDrag, QCursor
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
    QListWidget, QAbstractItemView, QPushButton, QMessageBox,
    QTreeWidget, QTreeWidgetItem, QHeaderView, QSplitter,
    QGroupBox, QApplication, QMenu, QInputDialog,
)

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)

_FONT = QFont("Segoe UI", 9)

_BTN_STYLE = (
    "QPushButton { background-color: #1E5BA8; color: white;"
    " border: 1px solid #14407A; border-radius: 3px;"
    " padding: 3px 10px; font-size: 8pt; }"
    "QPushButton:hover { background-color: #2A6BC4; }"
    "QPushButton:disabled { background-color: #A0A0A0;"
    " border: 1px solid #888; }"
)

_BTN_SMALL_STYLE = (
    "QPushButton { background-color: #E8F0FB; color: #1E5BA8;"
    " border: 1px solid #1E5BA8; border-radius: 2px;"
    " padding: 2px 8px; font-size: 8pt; }"
    "QPushButton:hover { background-color: #C5D8F5; }"
)

_TREE_STYLE = (
    "QTreeWidget { border: 1px solid #1E5BA8; background-color: white;"
    " font-size: 9pt; }"
    "QTreeWidget::item { padding: 1px 4px; }"
    "QTreeWidget::item:selected { background-color: #A0C4E8; color: black; }"
    "QHeaderView::section { background-color: #E8F0FB; color: #1E5BA8;"
    " font-weight: bold; font-size: 8pt; border: 1px solid #C0C0C0;"
    " padding: 2px 6px; }"
)

_LIST_STYLE = (
    "QListWidget { border: 1px solid #1E5BA8; background-color: white;"
    " font-size: 9pt; }"
    "QListWidget::item { padding: 2px 4px; }"
    "QListWidget::item:selected { background-color: #A0C4E8; color: black; }"
)

# MIME type for dragging fields from this dialog
FIELD_DRAG_MIME = "application/x-audit-field-drag"


class _FieldLoaderThread(QThread):
    """Background thread to fetch column metadata from ODBC."""
    columns_loaded = pyqtSignal(list)  # list of (name, type_name, size, nullable)
    error_occurred = pyqtSignal(str)

    def __init__(self, dsn: str, table_name: str, parent=None):
        super().__init__(parent)
        self.dsn = dsn
        self.table_name = table_name

    def run(self):
        try:
            conn = pyodbc.connect(f"DSN={self.dsn}", autocommit=True, timeout=15)
            cursor = conn.cursor()

            # Parse schema.table
            parts = self.table_name.split(".", 1)
            if len(parts) == 2:
                schema, table = parts
            else:
                schema, table = None, parts[0]

            columns = []
            for row in cursor.columns(table=table, schema=schema):
                col_name = row.column_name
                type_name = row.type_name
                col_size = row.column_size
                nullable = "Yes" if row.nullable else "No"
                columns.append((col_name, type_name, col_size, nullable))
            conn.close()
            self.columns_loaded.emit(columns)
        except Exception as exc:
            self.error_occurred.emit(str(exc))


class DraggableFieldTree(QTreeWidget):
    """QTreeWidget that supports dragging field items out."""

    field_double_clicked = pyqtSignal(str, str, str)  # table, column, display_name

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setDragEnabled(True)
        self.setDragDropMode(QAbstractItemView.DragDropMode.DragOnly)

    def startDrag(self, supportedActions):
        item = self.currentItem()
        if item is None:
            return
        col_name = item.text(0)
        type_name = item.text(1)
        display = item.text(3)
        table = item.data(0, Qt.ItemDataRole.UserRole)
        if not table:
            return

        drag = QDrag(self)
        mime = QMimeData()
        # Encode: table|column|type|display_name
        payload = f"{table}|{col_name}|{type_name}|{display}"
        mime.setData(FIELD_DRAG_MIME, payload.encode("utf-8"))
        drag.setMimeData(mime)
        drag.exec(Qt.DropAction.CopyAction)


class TablesDialog(QDialog):
    """Dialog showing tables and fields for a dynamic group."""

    # Signal emitted when user double-clicks a field to auto-place it
    field_requested = pyqtSignal(str, str, str, str)  # table, column, type, display

    def __init__(self, dsn: str, tables: list[str],
                 display_names: dict[str, str],
                 parent=None):
        super().__init__(parent)
        self.setWindowTitle("Tables & Fields")
        self.setMinimumSize(750, 500)
        self.setFont(_FONT)

        self._dsn = dsn
        self._tables = list(tables)
        self._display_names = display_names  # key: "table.column" → display_name
        self._current_table: str = ""
        self._loader: _FieldLoaderThread | None = None
        self._field_cache: dict[str, list[tuple]] = {}  # table → [(name,type,size,null)]

        self._build_ui()
        self._refresh_table_list()

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setSpacing(6)

        splitter = QSplitter(Qt.Orientation.Horizontal)

        # ── Left: Table list ─────────────────────────────────────────
        left = QGroupBox("Tables")
        left_lay = QVBoxLayout(left)
        left_lay.setSpacing(4)

        self.list_tables = QListWidget()
        self.list_tables.setStyleSheet(_LIST_STYLE)
        self.list_tables.setSelectionMode(
            QAbstractItemView.SelectionMode.SingleSelection)
        self.list_tables.currentItemChanged.connect(self._on_table_selected)
        left_lay.addWidget(self.list_tables)

        tbl_btns = QHBoxLayout()
        self.btn_add_table = QPushButton("+ Add")
        self.btn_add_table.setStyleSheet(_BTN_SMALL_STYLE)
        self.btn_add_table.setFixedHeight(22)
        self.btn_add_table.clicked.connect(self._on_add_table)
        tbl_btns.addWidget(self.btn_add_table)

        self.btn_remove_table = QPushButton("- Remove")
        self.btn_remove_table.setStyleSheet(_BTN_SMALL_STYLE)
        self.btn_remove_table.setFixedHeight(22)
        self.btn_remove_table.clicked.connect(self._on_remove_table)
        tbl_btns.addWidget(self.btn_remove_table)

        tbl_btns.addStretch()
        left_lay.addLayout(tbl_btns)

        splitter.addWidget(left)

        # ── Right: Field list ────────────────────────────────────────
        right = QGroupBox("Fields")
        right_lay = QVBoxLayout(right)
        right_lay.setSpacing(4)

        self.txt_field_search = QLineEdit()
        self.txt_field_search.setPlaceholderText("Search fields...")
        self.txt_field_search.setClearButtonEnabled(True)
        self.txt_field_search.setFixedHeight(24)
        self.txt_field_search.textChanged.connect(self._filter_fields)
        right_lay.addWidget(self.txt_field_search)

        self.tree_fields = DraggableFieldTree()
        self.tree_fields.setStyleSheet(_TREE_STYLE)
        self.tree_fields.setHeaderLabels(
            ["Column", "Type", "Size", "Display Name", "Nullable"])
        self.tree_fields.setColumnCount(5)
        self.tree_fields.setRootIsDecorated(False)
        self.tree_fields.setAlternatingRowColors(True)
        header = self.tree_fields.header()
        header.setDefaultSectionSize(120)
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Interactive)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Interactive)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(3, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(4, QHeaderView.ResizeMode.ResizeToContents)

        self.tree_fields.setContextMenuPolicy(
            Qt.ContextMenuPolicy.CustomContextMenu)
        self.tree_fields.customContextMenuRequested.connect(
            self._on_field_context_menu)
        self.tree_fields.itemDoubleClicked.connect(self._on_field_double_clicked)
        self.tree_fields.field_double_clicked.connect(
            lambda t, c, d: self.field_requested.emit(t, c, "", d))
        right_lay.addWidget(self.tree_fields)

        self.lbl_field_status = QLabel("")
        self.lbl_field_status.setFont(QFont("Segoe UI", 8))
        self.lbl_field_status.setStyleSheet("color: #666;")
        right_lay.addWidget(self.lbl_field_status)

        # Hint label
        hint = QLabel("Drag a field onto a tab, or double-click to auto-place.")
        hint.setFont(QFont("Segoe UI", 7, QFont.Weight.Normal))
        hint.setStyleSheet("color: #888;")
        right_lay.addWidget(hint)

        splitter.addWidget(right)
        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 3)

        root.addWidget(splitter, 1)

        # ── Close button ─────────────────────────────────────────────
        btn_row = QHBoxLayout()
        btn_row.addStretch()
        btn_close = QPushButton("Close")
        btn_close.setFixedHeight(26)
        btn_close.clicked.connect(self.accept)
        btn_row.addWidget(btn_close)
        root.addLayout(btn_row)

    def _refresh_table_list(self):
        self.list_tables.clear()
        self.list_tables.addItems(self._tables)

    def _on_table_selected(self, current, previous):
        if current is None:
            return
        table = current.text()
        if table == self._current_table:
            return
        self._current_table = table
        self._load_fields(table)

    def _load_fields(self, table: str):
        # Check cache first
        if table in self._field_cache:
            self._populate_fields(table, self._field_cache[table])
            return

        self.tree_fields.clear()
        self.lbl_field_status.setText("Loading fields...")

        self._loader = _FieldLoaderThread(self._dsn, table, self)
        self._loader.columns_loaded.connect(
            lambda cols: self._on_fields_loaded(table, cols))
        self._loader.error_occurred.connect(self._on_fields_error)
        self._loader.start()

    def _on_fields_loaded(self, table: str, columns: list[tuple]):
        self._field_cache[table] = columns
        if self._current_table == table:
            self._populate_fields(table, columns)
        self._loader = None

    def _on_fields_error(self, msg: str):
        self.lbl_field_status.setText("Error loading fields")
        QMessageBox.warning(self, "Error",
                            f"Failed to load fields:\n\n{msg}")
        self._loader = None

    def _populate_fields(self, table: str, columns: list[tuple]):
        self.tree_fields.clear()
        for col_name, type_name, size, nullable in columns:
            key = f"{table}.{col_name}"
            display = self._display_names.get(key, col_name)

            item = QTreeWidgetItem([
                col_name,
                type_name,
                str(size) if size else "",
                display,
                nullable,
            ])
            item.setData(0, Qt.ItemDataRole.UserRole, table)
            # Only Display Name column (3) is editable — handled via delegate/double-click
            item.setFlags(
                (item.flags() | Qt.ItemFlag.ItemIsEditable)
                & ~Qt.ItemFlag.ItemIsEditable
            )
            self.tree_fields.addTopLevelItem(item)

        self.lbl_field_status.setText(f"{len(columns)} fields")

        # Connect edit signal to track display name changes
        try:
            self.tree_fields.itemChanged.disconnect(self._on_item_changed)
        except TypeError:
            pass
        self.tree_fields.itemChanged.connect(self._on_item_changed)

    def _on_item_changed(self, item: QTreeWidgetItem, column: int):
        """Track display name edits (column 3)."""
        if column != 3:
            return
        table = item.data(0, Qt.ItemDataRole.UserRole)
        col_name = item.text(0)
        new_display = item.text(3).strip()
        if not new_display:
            new_display = col_name
            item.setText(3, col_name)
        key = f"{table}.{col_name}"
        self._display_names[key] = new_display

    def _filter_fields(self, text: str):
        filt = text.strip().lower()
        for i in range(self.tree_fields.topLevelItemCount()):
            item = self.tree_fields.topLevelItem(i)
            visible = True
            if filt:
                visible = (filt in item.text(0).lower()
                           or filt in item.text(1).lower()
                           or filt in item.text(3).lower())
            item.setHidden(not visible)

    def _on_field_context_menu(self, pos):
        item = self.tree_fields.itemAt(pos)
        if item is None:
            return
        menu = QMenu(self)
        act_rename = menu.addAction("Edit Display Name")
        act_place = menu.addAction("Place on Tab")
        chosen = menu.exec(self.tree_fields.viewport().mapToGlobal(pos))
        if chosen is act_rename:
            self._edit_display_name_inline(item)
        elif chosen is act_place:
            self._on_field_double_clicked(item, 0)

    def _edit_display_name_inline(self, item: QTreeWidgetItem):
        """Allow editing only the Display Name column via QInputDialog."""
        table = item.data(0, Qt.ItemDataRole.UserRole)
        col_name = item.text(0)
        current = item.text(3)
        new_name, ok = QInputDialog.getText(
            self, "Edit Display Name",
            f"Display name for {col_name}:", text=current)
        if ok and new_name.strip():
            new_name = new_name.strip()
            item.setText(3, new_name)
            key = f"{table}.{col_name}"
            self._display_names[key] = new_name

    def _on_field_double_clicked(self, item: QTreeWidgetItem, column: int):
        """Double-click → request auto-placement on current tab."""
        if column == 3:
            # Double-clicking the display name column should edit it
            self._edit_display_name_inline(item)
            return
        table = item.data(0, Qt.ItemDataRole.UserRole)
        col_name = item.text(0)
        type_name = item.text(1)
        display = item.text(3)
        self.field_requested.emit(table, col_name, type_name, display)

    def _on_add_table(self):
        """Add a new table from the same DSN."""
        from .create_group_dialog import _TableLoaderThread

        # We'll show a quick picker dialog
        dlg = _AddTableDialog(self._dsn, self._tables, self)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            new_tables = dlg.get_selected()
            for t in new_tables:
                if t not in self._tables:
                    self._tables.append(t)
            self._refresh_table_list()

    def _on_remove_table(self):
        current = self.list_tables.currentItem()
        if current is None:
            return
        table = current.text()
        reply = QMessageBox.question(
            self, "Remove Table",
            f"Remove table '{table}' from this group?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        if reply == QMessageBox.StandardButton.Yes:
            self._tables.remove(table)
            self._field_cache.pop(table, None)
            self._refresh_table_list()

    # ── Public accessors ─────────────────────────────────────────────

    def get_tables(self) -> list[str]:
        return list(self._tables)

    def get_display_names(self) -> dict[str, str]:
        return dict(self._display_names)


class _AddTableDialog(QDialog):
    """Quick dialog to add tables from the same DSN."""

    def __init__(self, dsn: str, existing: list[str], parent=None):
        super().__init__(parent)
        self.setWindowTitle("Add Tables")
        self.setMinimumSize(400, 400)
        self._selected: list[str] = []

        lay = QVBoxLayout(self)

        self.txt_search = QLineEdit()
        self.txt_search.setPlaceholderText("Search tables...")
        self.txt_search.setClearButtonEnabled(True)
        self.txt_search.setFixedHeight(24)
        self.txt_search.textChanged.connect(self._filter)
        lay.addWidget(self.txt_search)

        self.list_tables = QListWidget()
        self.list_tables.setStyleSheet(_LIST_STYLE)
        self.list_tables.setSelectionMode(
            QAbstractItemView.SelectionMode.MultiSelection)
        lay.addWidget(self.list_tables)

        self.lbl_status = QLabel("Loading...")
        lay.addWidget(self.lbl_status)

        btn_row = QHBoxLayout()
        btn_row.addStretch()
        btn_add = QPushButton("Add Selected")
        btn_add.setStyleSheet(_BTN_STYLE)
        btn_add.clicked.connect(self._on_add)
        btn_row.addWidget(btn_add)
        btn_cancel = QPushButton("Cancel")
        btn_cancel.clicked.connect(self.reject)
        btn_row.addWidget(btn_cancel)
        lay.addLayout(btn_row)

        self._existing = set(existing)
        self._load(dsn)

    def _load(self, dsn: str):
        self._loader = _FieldLoaderThread.__class__.__mro__  # just need the thread
        # Use inline loading (simpler for a secondary dialog)
        try:
            conn = pyodbc.connect(f"DSN={dsn}", autocommit=True, timeout=15)
            cursor = conn.cursor()
            tables = []
            for row in cursor.tables():
                if row.table_type in ("TABLE", "VIEW"):
                    schema = row.table_schem or ""
                    name = row.table_name
                    full = f"{schema}.{name}" if schema else name
                    if full not in self._existing:
                        tables.append(full)
            conn.close()
            self.list_tables.addItems(sorted(tables))
            self.lbl_status.setText(f"{len(tables)} available tables")
        except Exception as exc:
            self.lbl_status.setText("Error loading tables")
            QMessageBox.warning(self, "Error", str(exc))

    def _filter(self, text: str):
        filt = text.strip().lower()
        for i in range(self.list_tables.count()):
            item = self.list_tables.item(i)
            item.setHidden(filt not in item.text().lower() if filt else False)

    def _on_add(self):
        self._selected = [
            self.list_tables.item(i).text()
            for i in range(self.list_tables.count())
            if self.list_tables.item(i).isSelected()]
        self.accept()

    def get_selected(self) -> list[str]:
        return self._selected
