"""
Tables Dialog — browse tables and fields in a dynamic group.

Left panel: list of tables (add/remove).
Right panel: field list for selected table with display name editing.
Supports drag-out of fields onto tab forms, and double-click to auto-place.
"""
from __future__ import annotations

import logging
from typing import TYPE_CHECKING

import time

import pandas as pd
from PyQt6.QtCore import QObject, Qt, QMimeData, pyqtSignal
from PyQt6.QtGui import QFont, QDrag
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
    QListWidget, QAbstractItemView, QPushButton, QMessageBox,
    QTreeWidget, QTreeWidgetItem, QHeaderView, QSplitter,
    QGroupBox, QInputDialog, QSpinBox,
    QStyledItemDelegate, QWidget,
)

from suiteview.audit.query_builder_menu import query_builder_menu
from suiteview.core.odbc_utils import connect_dsn
from suiteview.ui.workers import WorkerController, WorkerSignals

from ..tabs._styles import TightItemDelegate

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)


def _clean_odbc_identifier(value: object) -> str:
    return str(value or "").replace("\x00", "").strip()


def _quote_qualified_table_name(table_name: str, dialect: str) -> str:
    """Quote each part of a schema-qualified table name for preview SQL."""
    parts = [_clean_odbc_identifier(part) for part in table_name.split(".", 1)]
    parts = [part for part in parts if part]
    if not parts:
        return _clean_odbc_identifier(table_name)
    if dialect == "DB2":
        return ".".join(f'"{part.replace(chr(34), chr(34) + chr(34))}"' for part in parts)
    return ".".join(f"[{part.replace(']', ']]')}]" for part in parts)

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
    " font-size: 9pt; outline: none; }"
    "QListWidget::item { padding: 2px 4px; }"
    "QListWidget::item:selected { background-color: #A0C4E8; color: black; }"
    "QListWidget::item:focus { outline: none; border: none; }"
)

# MIME type for dragging fields from this dialog
FIELD_DRAG_MIME = "application/x-audit-field-drag"


class _DisplayNameOnlyDelegate(QStyledItemDelegate):
    """Only allows editing on column 3 (Display Name); all others are read-only."""

    def createEditor(self, parent, option, index):
        if index.column() != 3:
            return None  # reject editing on non-display-name columns
        return super().createEditor(parent, option, index)


class _FieldLoaderWorker(QObject):
    """Fetch column metadata from ODBC inside a WorkerController thread."""

    def __init__(self, dsn: str, table_name: str, parent=None):
        super().__init__(parent)
        self.signals = WorkerSignals(self)
        self.dsn = dsn
        self.table_name = table_name

    def run(self):
        try:
            conn = connect_dsn(
                self.dsn, autocommit=True, timeout=15, readonly=False,
            )
            cursor = conn.cursor()

            # Parse schema.table
            parts = [_clean_odbc_identifier(part) for part in self.table_name.split(".", 1)]
            if len(parts) == 2:
                schema, table = parts
            else:
                schema, table = None, parts[0]

            columns = []
            rows = cursor.columns(table=table, schema=schema)
            while True:
                try:
                    row = next(rows)
                except StopIteration:
                    break
                except Exception:
                    continue
                col_name = _clean_odbc_identifier(row.column_name)
                type_name = _clean_odbc_identifier(row.type_name)
                col_size = row.column_size
                nullable = "Yes" if row.nullable else "No"
                columns.append((col_name, type_name, col_size, nullable))
            conn.close()
            self.signals.result.emit(columns)
        except Exception as exc:
            self.signals.error.emit(str(exc))
        finally:
            self.signals.finished.emit()


class DraggableFieldTree(QTreeWidget):
    """QTreeWidget that supports dragging field items out (multi-select)."""

    field_double_clicked = pyqtSignal(str, str, str)  # table, column, display_name

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setDragEnabled(True)
        self.setDragDropMode(QAbstractItemView.DragDropMode.DragOnly)
        self.setSelectionMode(
            QAbstractItemView.SelectionMode.ExtendedSelection)

    def startDrag(self, supportedActions):
        items = self.selectedItems()
        if not items:
            return

        # Build multi-field payload: one entry per line
        lines = []
        for item in items:
            col_name = item.text(0)
            type_name = item.text(1)
            display = item.text(3)
            table = item.data(0, Qt.ItemDataRole.UserRole)
            if not table:
                continue
            lines.append(f"{table}|{col_name}|{type_name}|{display}")

        if not lines:
            return

        drag = QDrag(self)
        mime = QMimeData()
        payload = "\n".join(lines)
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
        self.setWindowFlags(
            Qt.WindowType.Window | Qt.WindowType.FramelessWindowHint)
        self.setMinimumSize(900, 750)
        self.resize(900, 750)
        self.setFont(_FONT)

        # Drag state for custom title bar
        self._drag_pos = None

        self._dsn = dsn
        self._tables = list(tables)
        self._display_names = display_names  # key: "table.column" → display_name
        self._current_table: str = ""
        self._loader: WorkerController | None = None
        self._field_cache: dict[str, list[tuple]] = {}  # table → [(name,type,size,null)]

        self._build_ui()
        self._refresh_table_list()

    def paintEvent(self, event):
        """Draw gold border around the dialog (matching FramelessWindowBase)."""
        super().paintEvent(event)
        from PyQt6.QtGui import QPainter, QPen, QColor
        p = QPainter(self)
        pen = QPen(QColor("#D4A017"))
        pen.setWidth(2)
        p.setPen(pen)
        p.drawRect(self.rect().adjusted(1, 1, -1, -1))
        p.end()

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(2, 2, 2, 2)
        root.setSpacing(0)

        # ── Custom title bar (matches FramelessWindowBase theme) ─────
        header = QWidget()
        header.setFixedHeight(32)
        header.setStyleSheet(
            "QWidget { background: qlineargradient(x1:0, y1:0, x2:1, y2:1,"
            " stop:0 #1E5BA8, stop:0.5 #0D3A7A, stop:1 #082B5C); }")
        header.setCursor(Qt.CursorShape.ArrowCursor)
        hlay = QHBoxLayout(header)
        hlay.setContentsMargins(10, 2, 6, 2)
        hlay.setSpacing(6)

        title_lbl = QLabel("Tables && Fields")
        title_lbl.setStyleSheet(
            "QLabel { color: white; font-size: 14px; font-weight: bold;"
            " font-style: italic; background: transparent; }")
        hlay.addWidget(title_lbl)
        hlay.addStretch()

        btn_close = QPushButton("✕")
        btn_close.setFixedSize(28, 22)
        btn_close.setStyleSheet(
            "QPushButton { background: transparent; border: none;"
            " color: #D4A017; font-size: 14px; font-weight: bold; }"
            "QPushButton:hover { background-color: #E81123; }")
        btn_close.clicked.connect(self.accept)
        hlay.addWidget(btn_close)

        # Enable drag-to-move on the header
        header.mousePressEvent = self._header_mouse_press
        header.mouseMoveEvent = self._header_mouse_move
        header.mouseReleaseEvent = self._header_mouse_release

        root.addWidget(header)

        # ── Body ─────────────────────────────────────────────────────
        body = QWidget()
        body.setStyleSheet("QWidget { background-color: white; }")
        body_lay = QVBoxLayout(body)
        body_lay.setSpacing(6)
        body_lay.setContentsMargins(6, 6, 6, 6)

        splitter = QSplitter(Qt.Orientation.Horizontal)

        # ── Left: Table list ─────────────────────────────────────────
        left = QGroupBox("Tables")
        left_lay = QVBoxLayout(left)
        left_lay.setSpacing(4)

        self.list_tables = QListWidget()
        self.list_tables.setStyleSheet(_LIST_STYLE)
        self.list_tables.setItemDelegate(TightItemDelegate(self.list_tables))
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

        self.btn_view_table = QPushButton("View")
        self.btn_view_table.setStyleSheet(
            "QPushButton { background-color: #2E7D32; color: white;"
            " border: 1px solid #1B5E20; border-radius: 2px;"
            " padding: 2px 8px; font-size: 8pt; }"
            "QPushButton:hover { background-color: #388E3C; }")
        self.btn_view_table.setFixedHeight(22)
        self.btn_view_table.setToolTip("Preview first 1000 rows of the selected table")
        self.btn_view_table.clicked.connect(self._on_view_table)
        tbl_btns.addWidget(self.btn_view_table)

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
        self.tree_fields.setItemDelegate(_DisplayNameOnlyDelegate(self.tree_fields))
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

        body_lay.addWidget(splitter, 1)

        # Hint label at bottom
        hint2 = QLabel("Multi-select fields with Ctrl+Click, then drag onto a tab.")
        hint2.setFont(QFont("Segoe UI", 7))
        hint2.setStyleSheet("color: #888;")
        body_lay.addWidget(hint2)

        root.addWidget(body, 1)

    # ── Title bar drag-to-move ───────────────────────────────────────

    def _header_mouse_press(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_pos = event.globalPosition().toPoint() - self.pos()

    def _header_mouse_move(self, event):
        if self._drag_pos is not None:
            self.move(event.globalPosition().toPoint() - self._drag_pos)

    def _header_mouse_release(self, event):
        self._drag_pos = None

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

        worker = _FieldLoaderWorker(self._dsn, table)
        self._loader = WorkerController(self, worker)
        self._loader.result.connect(lambda cols: self._on_fields_loaded(table, cols))
        self._loader.error.connect(self._on_fields_error)
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
            # Allow editing — delegate restricts to Display Name column only
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsEditable)
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
        menu = query_builder_menu(self)
        act_rename = menu.addAction("Edit Display Name")
        act_place = menu.addAction("Place on Tab")
        chosen = menu.exec(self.tree_fields.viewport().mapToGlobal(pos))
        if chosen is act_rename:
            self.tree_fields.editItem(item, 3)
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
            # Double-clicking the display name column edits it inline
            self.tree_fields.editItem(item, 3)
            return
        table = item.data(0, Qt.ItemDataRole.UserRole)
        col_name = item.text(0)
        type_name = item.text(1)
        display = item.text(3)
        self.field_requested.emit(table, col_name, type_name, display)

    def _on_add_table(self):
        """Add a new table from the same DSN."""

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

    def _on_view_table(self):
        """Open a preview window showing the first 1000 rows."""
        current = self.list_tables.currentItem()
        if current is None:
            QMessageBox.information(self, "No Table", "Select a table first.")
            return
        table = current.text()
        dlg = _TablePreviewDialog(self._dsn, table, self)
        dlg.show()

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
        self.list_tables.setItemDelegate(TightItemDelegate(self.list_tables))
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
        self._loader = None
        # Use inline loading (simpler for a secondary dialog)
        try:
            conn = connect_dsn(dsn, autocommit=True, timeout=15, readonly=False)
            cursor = conn.cursor()
            tables = []
            rows = cursor.tables()
            while True:
                try:
                    row = next(rows)
                except StopIteration:
                    break
                except Exception:
                    continue
                if row.table_type in ("TABLE", "VIEW"):
                    schema = _clean_odbc_identifier(row.table_schem)
                    name = _clean_odbc_identifier(row.table_name)
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


DEFAULT_TABLE_VIEW_ROWS = 1000


def _table_view_sql(table_name: str, dialect: str, row_limit: int) -> str:
    table = _quote_qualified_table_name(table_name, dialect)
    limit = max(1, int(row_limit))
    if dialect == "DB2":
        return f"SELECT * FROM {table} FETCH FIRST {limit} ROWS ONLY"
    return f"SELECT TOP {limit} * FROM {table}"


class _PreviewLoaderWorker(QObject):
    """Fetch up to ``row_limit`` rows of one table on a worker thread.

    Reads a database table through ``dsn``, or a File Source member when
    ``source_token`` is a ``file:`` token.
    """

    def __init__(self, dsn: str, table_name: str, dialect: str, parent=None, *,
                 row_limit: int = DEFAULT_TABLE_VIEW_ROWS, source_token: str = ""):
        super().__init__(parent)
        self.signals = WorkerSignals(self)
        self.dsn = dsn
        self.table_name = table_name
        self.dialect = dialect
        self.row_limit = max(1, int(row_limit))
        self.source_token = source_token

    def run(self):
        try:
            if self.source_token:
                from suiteview.audit.federated_query import load_file_table
                df = load_file_table(self.source_token, self.table_name)
                self.signals.result.emit(df.head(self.row_limit).reset_index(drop=True))
                return
            conn = connect_dsn(
                self.dsn, autocommit=True, timeout=30, readonly=False,
            )
            try:
                cursor = conn.cursor()
                cursor.execute(_table_view_sql(self.table_name, self.dialect, self.row_limit))
                columns = [desc[0] for desc in cursor.description]
                rows = cursor.fetchall()
            finally:
                conn.close()
            df = pd.DataFrame([list(r) for r in rows], columns=columns)
            self.signals.result.emit(df)
        except Exception as exc:
            self.signals.error.emit(str(exc))
        finally:
            self.signals.finished.emit()


# Open table views; top-level windows need a reference to stay alive.
_OPEN_TABLE_VIEWS: set = set()


def open_table_view(dsn: str, table_name: str, *, source_token: str = "",
                    inline_data: dict | None = None) -> "_TablePreviewDialog":
    """Show ``table_name`` in its own window (first 1000 rows; adjustable)."""
    dlg = _TablePreviewDialog(dsn, table_name, None,
                              source_token=source_token, inline_data=inline_data)
    _OPEN_TABLE_VIEWS.add(dlg)
    dlg.destroyed.connect(lambda *_a, d=dlg: _OPEN_TABLE_VIEWS.discard(d))
    dlg.show()
    dlg.raise_()
    dlg.activateWindow()
    return dlg


class _TablePreviewDialog(QDialog):
    """Non-modal table view: the first N rows (default 1000) of a table.

    Shows a database table (via ``dsn``), a File Source member
    (``source_token``) or a pasted list (``inline_data``).
    """

    def __init__(self, dsn: str, table_name: str, parent=None, *,
                 source_token: str = "", inline_data: dict | None = None,
                 row_limit: int = DEFAULT_TABLE_VIEW_ROWS):
        super().__init__(parent)
        self.setWindowTitle(f"Table View \u2014 {table_name}")
        self.setWindowFlags(
            Qt.WindowType.Window | Qt.WindowType.WindowMinimizeButtonHint
            | Qt.WindowType.WindowMaximizeButtonHint | Qt.WindowType.WindowCloseButtonHint)
        self.resize(1000, 600)
        self.setFont(_FONT)
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)

        self._dsn = dsn
        self._table_name = table_name
        self._source_token = source_token
        self._inline_data = inline_data
        self._loader: WorkerController | None = None

        lay = QVBoxLayout(self)
        lay.setContentsMargins(4, 4, 4, 4)
        lay.setSpacing(4)

        bar = QHBoxLayout()
        bar.addWidget(QLabel("Rows:"))
        self.spn_rows = QSpinBox()
        self.spn_rows.setRange(1, 10_000_000)
        self.spn_rows.setSingleStep(1000)
        self.spn_rows.setGroupSeparatorShown(True)
        self.spn_rows.setValue(max(1, int(row_limit)))
        self.spn_rows.setFixedWidth(110)
        self.spn_rows.setToolTip("How many rows to show. Press Enter or Reload to apply.")
        self.spn_rows.editingFinished.connect(self._reload_if_changed)
        bar.addWidget(self.spn_rows)
        self.btn_reload = QPushButton("Reload")
        self.btn_reload.setStyleSheet(_BTN_SMALL_STYLE)
        self.btn_reload.clicked.connect(self._load_data)
        bar.addWidget(self.btn_reload)
        bar.addStretch(1)
        lay.addLayout(bar)

        from suiteview.ui.widgets.filter_table_view import FilterTableView
        self.table = FilterTableView(self)
        tv = self.table.table_view
        tv.verticalHeader().setVisible(False)
        tv.verticalHeader().setDefaultSectionSize(16)
        tv.verticalHeader().setMinimumSectionSize(14)
        tv.setSelectionBehavior(tv.SelectionBehavior.SelectRows)
        tv.setEditTriggers(tv.EditTrigger.NoEditTriggers)
        tv.setStyleSheet("""
            QTableView#filterTableView {
                gridline-color: transparent;
                background-color: white;
                alternate-background-color: white;
                selection-background-color: #e0e8f0;
                selection-color: black;
                font-size: 9pt;
                border: none;
            }
            QTableView#filterTableView::item {
                padding: 0px 2px;
                border: none;
            }
            QHeaderView::section {
                background-color: #e8e8e8;
                color: #000000;
                font-weight: normal;
                font-size: 8pt;
                padding: 1px 16px 1px 4px;
                border: 1px solid #c0c0c0;
            }
        """)
        lay.addWidget(self.table, 1)

        self.lbl_status = QLabel("Loading...")
        self.lbl_status.setFont(QFont("Segoe UI", 8))
        self.lbl_status.setStyleSheet("color: #666;")
        lay.addWidget(self.lbl_status)

        self._loaded_limit = 0
        self._load_data()

    def row_limit(self) -> int:
        return self.spn_rows.value()

    def _reload_if_changed(self):
        if self.spn_rows.value() != self._loaded_limit:
            self._load_data()

    def _load_data(self):
        if self._loader is not None and self._loader.is_running():
            return
        limit = self.spn_rows.value()
        self._loaded_limit = limit
        self._t0 = time.time()
        self.lbl_status.setText("Loading...")
        if self._inline_data is not None:
            from suiteview.audit.federated_query import inline_dataframe
            self._on_data_loaded(inline_dataframe(self._inline_data).head(limit))
            return
        from suiteview.core.odbc_utils import detect_dialect
        dialect = "" if self._source_token else detect_dialect(self._dsn)
        self.btn_reload.setEnabled(False)
        worker = _PreviewLoaderWorker(
            self._dsn, self._table_name, dialect,
            row_limit=limit, source_token=self._source_token)
        self._loader = WorkerController(self, worker)
        self._loader.result.connect(self._on_data_loaded)
        self._loader.error.connect(self._on_error)
        self._loader.start()

    def _on_data_loaded(self, df):
        self.btn_reload.setEnabled(True)
        self.table.set_dataframe(df, limit_rows=False)
        elapsed = time.time() - self._t0
        self.lbl_status.setText(
            f"{len(df):,} rows  |  {len(df.columns)} columns  |  "
            f"loaded in {elapsed:.1f}s")
        self._loader = None

    def _on_error(self, msg: str):
        self.btn_reload.setEnabled(True)
        self.lbl_status.setText("Error loading data")
        QMessageBox.warning(self, "Table View Error",
                            f"Failed to load data:\n\n{msg}")
        self._loader = None

    def closeEvent(self, event):
        if self._loader is not None and self._loader.is_running():
            # Let the query finish off-window rather than destroying a running thread.
            loader = self._loader
            loader.setParent(None)
            _OPEN_TABLE_VIEWS.add(loader)
            loader.finished.connect(lambda *_a, l=loader: _OPEN_TABLE_VIEWS.discard(l))
            for signal in (loader.result, loader.error):
                try:
                    signal.disconnect()
                except TypeError:
                    pass
            self._loader = None
        super().closeEvent(event)
