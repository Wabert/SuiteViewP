"""
Queries && Fields Dialog — browse saved queries and their fields
for a DataForge group.

Left panel:  list of source queries (add/remove from available saved queries).
Right panel:  field list for selected query with Column, Type, Size, Display Name, Nullable.
Supports drag-out of fields onto DataForge filter tabs, and double-click to auto-place.

Mirrors the look of TablesDialog but with purple DataForge theming.
"""
from __future__ import annotations

import logging
from typing import TYPE_CHECKING

import pyodbc
from PyQt6.QtCore import Qt, QMimeData, QThread, pyqtSignal
from PyQt6.QtGui import QFont, QDrag
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
    QListWidget, QListWidgetItem, QAbstractItemView, QPushButton, QMessageBox,
    QTreeWidget, QTreeWidgetItem, QHeaderView, QSplitter,
    QGroupBox, QMenu, QWidget, QCheckBox, QStackedWidget,
    QTextEdit, QApplication,
)

from suiteview.audit.qdefinition import QDefinition
from suiteview.audit import qdef_store
from suiteview.audit.tabs._styles import TightItemDelegate

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)

_FONT = QFont("Segoe UI", 9)

# Purple theme
_BTN_STYLE = (
    "QPushButton { background-color: #7C3AED; color: white;"
    " border: 1px solid #6D28D9; border-radius: 3px;"
    " padding: 3px 10px; font-size: 8pt; }"
    "QPushButton:hover { background-color: #8B5CF6; }"
    "QPushButton:disabled { background-color: #A0A0A0;"
    " border: 1px solid #888; }"
)

_BTN_SMALL_STYLE = (
    "QPushButton { background-color: #F5F3FF; color: #7C3AED;"
    " border: 1px solid #7C3AED; border-radius: 2px;"
    " padding: 2px 8px; font-size: 8pt; }"
    "QPushButton:hover { background-color: #EDE9FE; }"
)

_TREE_STYLE = (
    "QTreeWidget { border: 1px solid #7C3AED; background-color: white;"
    " font-size: 9pt; }"
    "QTreeWidget::item { padding: 1px 4px; }"
    "QTreeWidget::item:selected { background-color: #DDD6FE; color: black; }"
    "QHeaderView::section { background-color: #F5F3FF; color: #7C3AED;"
    " font-weight: bold; font-size: 8pt; border: 1px solid #C0C0C0;"
    " padding: 2px 6px; }"
)

_LIST_STYLE = (
    "QListWidget { border: 1px solid #7C3AED; background-color: white;"
    " font-size: 9pt; outline: none; }"
    "QListWidget::item { padding: 2px 4px; }"
    "QListWidget::item:selected { background-color: #DDD6FE; color: black; }"
    "QListWidget::item:focus { outline: none; border: none; }"
)

# MIME type for dragging fields from this dialog
FORGE_FIELD_DRAG_MIME = "application/x-dataforge-field-drag"


# ── Background field loader ─────────────────────────────────────────

class _QueryFieldLoaderThread(QThread):
    """Background thread to fetch column metadata from a saved query's DSN."""
    columns_loaded = pyqtSignal(list)  # list of (name, type_name, size, nullable)
    error_occurred = pyqtSignal(str)

    def __init__(self, dsn: str, tables: list[str], parent=None):
        super().__init__(parent)
        self.dsn = dsn
        self.tables = tables

    def run(self):
        try:
            conn = pyodbc.connect(f"DSN={self.dsn}", autocommit=True, timeout=15)
            cursor = conn.cursor()

            columns = []
            for table_name in self.tables:
                parts = table_name.split(".", 1)
                if len(parts) == 2:
                    schema, table = parts
                else:
                    schema, table = None, parts[0]

                rows = cursor.columns(table=table, schema=schema)
                while True:
                    try:
                        row = next(rows)
                    except StopIteration:
                        break
                    except Exception:
                        continue
                    col_name = row.column_name
                    type_name = row.type_name
                    col_size = row.column_size
                    nullable = "Yes" if row.nullable else "No"
                    columns.append((col_name, type_name, col_size, nullable))

            conn.close()
            self.columns_loaded.emit(columns)
        except Exception as exc:
            self.error_occurred.emit(str(exc))


# ── Draggable field tree ─────────────────────────────────────────────

class _DraggableForgeFieldTree(QTreeWidget):
    """QTreeWidget that supports dragging field items out (multi-select)."""

    field_double_clicked = pyqtSignal(str, str, str)  # query_name, column, display_name

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

        lines = []
        for item in items:
            col_name = item.text(0)
            query_name = item.data(0, Qt.ItemDataRole.UserRole)
            if not query_name:
                continue
            lines.append(f"{query_name}|{col_name}")

        if not lines:
            return

        drag = QDrag(self)
        mime = QMimeData()
        payload = "\n".join(lines)
        mime.setData(FORGE_FIELD_DRAG_MIME, payload.encode("utf-8"))
        drag.setMimeData(mime)
        drag.exec(Qt.DropAction.CopyAction)


# ═════════════════════════════════════════════════════════════════════
# QueriesFieldsDialog
# ═════════════════════════════════════════════════════════════════════

class QueriesFieldsDialog(QDialog):
    """Dialog showing saved queries and their fields for a DataForge group.

    Mirrors the layout of TablesDialog but with purple theming.
    Left:  list of source saved queries (add/remove).
    Right: field details (Column, Type, Size, Display Name, Nullable).
    """

    # Emitted when a field is double-clicked to auto-place
    field_requested = pyqtSignal(str, str)  # query_name, column_name

    # Emitted when the set of source queries changes
    sources_changed = pyqtSignal(list)  # list of query names

    # Emitted when user requests to run a single query
    run_query_requested = pyqtSignal(str)  # query_name

    # Emitted when user clicks View to preview query results
    view_query_requested = pyqtSignal(str)  # query_name

    # Emitted when user clicks View to preview query results
    view_query_requested = pyqtSignal(str)  # query_name

    def __init__(self, source_queries: dict[str, QDefinition], parent=None,
                 forge_name: str = ""):
        super().__init__(parent)
        self.setWindowFlags(
            Qt.WindowType.Window | Qt.WindowType.FramelessWindowHint)
        self.setMinimumSize(900, 750)
        self.resize(900, 750)
        self.setFont(_FONT)

        self._drag_pos = None
        self._sources: dict[str, QDefinition] = dict(source_queries)
        self._forge_name = forge_name
        self._current_query: str = ""
        self._loader: _QueryFieldLoaderThread | None = None
        self._field_cache: dict[str, list[tuple]] = {}  # query_name → [(col, type, size, null)]
        self._loaded_queries: set[str] = set()  # queries with data in memory

        self._build_ui()
        self._refresh_query_list()

    def paintEvent(self, event):
        """Draw purple border around the dialog."""
        super().paintEvent(event)
        from PyQt6.QtGui import QPainter, QPen, QColor
        p = QPainter(self)
        pen = QPen(QColor("#7C3AED"))
        pen.setWidth(2)
        p.setPen(pen)
        p.drawRect(self.rect().adjusted(1, 1, -1, -1))
        p.end()

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(2, 2, 2, 2)
        root.setSpacing(0)

        # ── Custom title bar (purple gradient) ───────────────────────
        header = QWidget()
        header.setFixedHeight(32)
        header.setStyleSheet(
            "QWidget { background: qlineargradient(x1:0, y1:0, x2:1, y2:1,"
            " stop:0 #7C3AED, stop:0.5 #6D28D9, stop:1 #5B21B6); }")
        header.setCursor(Qt.CursorShape.ArrowCursor)
        hlay = QHBoxLayout(header)
        hlay.setContentsMargins(10, 2, 6, 2)
        hlay.setSpacing(6)

        title_lbl = QLabel("Query Definitions && Fields")
        title_lbl.setStyleSheet(
            "QLabel { color: white; font-size: 14px; font-weight: bold;"
            " font-style: italic; background: transparent; }")
        hlay.addWidget(title_lbl)
        hlay.addStretch()

        btn_close = QPushButton("✕")
        btn_close.setFixedSize(28, 22)
        btn_close.setStyleSheet(
            "QPushButton { background: transparent; border: none;"
            " color: #DDD6FE; font-size: 14px; font-weight: bold; }"
            "QPushButton:hover { background-color: #E81123; color: white; }")
        btn_close.clicked.connect(self.accept)
        hlay.addWidget(btn_close)

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

        # ── Left: Query list ─────────────────────────────────────────
        left = QGroupBox("Query Definitions")
        left_lay = QVBoxLayout(left)
        left_lay.setSpacing(4)

        self.list_queries = QListWidget()
        self.list_queries.setStyleSheet(_LIST_STYLE)
        self.list_queries.setItemDelegate(TightItemDelegate(self.list_queries))
        self.list_queries.setSelectionMode(
            QAbstractItemView.SelectionMode.SingleSelection)
        self.list_queries.currentItemChanged.connect(self._on_query_selected)
        self.list_queries.setContextMenuPolicy(
            Qt.ContextMenuPolicy.CustomContextMenu)
        self.list_queries.customContextMenuRequested.connect(
            self._on_query_context_menu)
        left_lay.addWidget(self.list_queries)

        q_btns = QHBoxLayout()
        self.btn_add_query = QPushButton("+ QDef")
        self.btn_add_query.setStyleSheet(_BTN_SMALL_STYLE)
        self.btn_add_query.setFixedHeight(22)
        self.btn_add_query.clicked.connect(self._on_add_query)
        q_btns.addWidget(self.btn_add_query)

        self.btn_remove_query = QPushButton("- Remove")
        self.btn_remove_query.setStyleSheet(_BTN_SMALL_STYLE)
        self.btn_remove_query.setFixedHeight(22)
        self.btn_view_query = QPushButton("View")
        self.btn_view_query.setStyleSheet(
            "QPushButton { background-color: #059669; color: white;"
            " border: 1px solid #047857; border-radius: 2px;"
            " padding: 3px 10px; font-size: 8pt; }"
            "QPushButton:hover { background-color: #10B981; }")
        self.btn_view_query.setFixedHeight(22)
        self.btn_view_query.setToolTip("Preview the first 1000 rows of this query")
        self.btn_view_query.clicked.connect(self._on_view_query)
        q_btns.addWidget(self.btn_view_query)

        self.btn_remove_query.clicked.connect(self._on_remove_query)
        q_btns.addWidget(self.btn_remove_query)

        self.btn_view_query = QPushButton("View")
        self.btn_view_query.setStyleSheet(
            "QPushButton { background-color: #059669; color: white;"
            " border: 1px solid #047857; border-radius: 2px;"
            " padding: 3px 10px; font-size: 8pt; }"
            "QPushButton:hover { background-color: #10B981; }")
        self.btn_view_query.setFixedHeight(22)
        self.btn_view_query.setToolTip("Preview the first 1000 rows of this query")
        self.btn_view_query.clicked.connect(self._on_view_query)
        q_btns.addWidget(self.btn_view_query)

        q_btns.addStretch()
        left_lay.addLayout(q_btns)

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

        # Stacked widget: page 0 = fields, page 1 = SQL view
        self._right_stack = QStackedWidget()

        # Page 0: Field tree
        fields_page = QWidget()
        fp_lay = QVBoxLayout(fields_page)
        fp_lay.setContentsMargins(0, 0, 0, 0)
        fp_lay.setSpacing(4)

        self.tree_fields = _DraggableForgeFieldTree()
        self.tree_fields.setStyleSheet(_TREE_STYLE)
        self.tree_fields.setHeaderLabels(
            ["Column", "Type", "Size", "Display Name", "Nullable"])
        self.tree_fields.setColumnCount(5)
        self.tree_fields.setRootIsDecorated(False)
        self.tree_fields.setAlternatingRowColors(True)
        hdr = self.tree_fields.header()
        hdr.setDefaultSectionSize(120)
        hdr.setSectionResizeMode(0, QHeaderView.ResizeMode.Interactive)
        hdr.setSectionResizeMode(1, QHeaderView.ResizeMode.Interactive)
        hdr.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        hdr.setSectionResizeMode(3, QHeaderView.ResizeMode.Stretch)
        hdr.setSectionResizeMode(4, QHeaderView.ResizeMode.ResizeToContents)

        self.tree_fields.setContextMenuPolicy(
            Qt.ContextMenuPolicy.CustomContextMenu)
        self.tree_fields.customContextMenuRequested.connect(
            self._on_field_context_menu)
        self.tree_fields.itemDoubleClicked.connect(self._on_field_double_clicked)
        fp_lay.addWidget(self.tree_fields)

        self.lbl_field_status = QLabel("")
        self.lbl_field_status.setFont(QFont("Segoe UI", 8))
        self.lbl_field_status.setStyleSheet("color: #666;")
        fp_lay.addWidget(self.lbl_field_status)

        hint = QLabel("Drag a field onto a tab, or double-click to auto-place.")
        hint.setFont(QFont("Segoe UI", 7))
        hint.setStyleSheet("color: #888;")
        fp_lay.addWidget(hint)

        self._right_stack.addWidget(fields_page)  # index 0

        # Page 1: Inspect view
        inspect_page = QWidget()
        ip_lay = QVBoxLayout(inspect_page)
        ip_lay.setContentsMargins(0, 0, 0, 0)
        ip_lay.setSpacing(4)

        inspect_header = QHBoxLayout()
        self._lbl_inspect_title = QLabel("Inspect")
        self._lbl_inspect_title.setFont(QFont("Segoe UI", 9, QFont.Weight.Bold))
        self._lbl_inspect_title.setStyleSheet("color: #7C3AED;")
        inspect_header.addWidget(self._lbl_inspect_title)
        inspect_header.addStretch()
        btn_back = QPushButton("← Fields")
        btn_back.setStyleSheet(_BTN_SMALL_STYLE)
        btn_back.setFixedHeight(22)
        btn_back.clicked.connect(lambda: self._right_stack.setCurrentIndex(0))
        inspect_header.addWidget(btn_back)
        ip_lay.addLayout(inspect_header)

        self._txt_inspect = QTextEdit()
        self._txt_inspect.setReadOnly(True)
        self._txt_inspect.setFont(QFont("Consolas", 9))
        self._txt_inspect.setStyleSheet(
            "QTextEdit { border: 1px solid #7C3AED; background-color: #FAFAFA; }")
        ip_lay.addWidget(self._txt_inspect)

        self._right_stack.addWidget(inspect_page)  # index 1

        right_lay.addWidget(self._right_stack)

        splitter.addWidget(right)
        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 3)

        body_lay.addWidget(splitter, 1)

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

    # ── Query list management ────────────────────────────────────────

    def _refresh_query_list(self):
        self.list_queries.clear()
        for name in self._sources:
            item = QListWidgetItem(name)
            if name in self._loaded_queries:
                item.setIcon(self._green_dot_icon())
                item.setToolTip("Data loaded in memory")
            self.list_queries.addItem(item)

    @staticmethod
    def _green_dot_icon():
        """Return a small green circle icon indicating data is loaded."""
        from PyQt6.QtGui import QPixmap, QPainter, QColor
        px = QPixmap(12, 12)
        px.fill(QColor(0, 0, 0, 0))
        p = QPainter(px)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setBrush(QColor("#22C55E"))
        p.setPen(QColor("#16A34A"))
        p.drawEllipse(1, 1, 10, 10)
        p.end()
        from PyQt6.QtGui import QIcon
        return QIcon(px)

    def update_data_status(self, loaded: set[str]):
        """Update which queries have data in memory and refresh indicators."""
        self._loaded_queries = set(loaded)
        self._refresh_query_list()

    def _on_query_selected(self, current, previous):
        if current is None:
            return
        query_name = current.text()
        if query_name == self._current_query:
            return
        self._current_query = query_name
        self._load_fields(query_name)
        # Switch right panel back to fields view when selecting a query
        self._right_stack.setCurrentIndex(0)

    def _on_query_context_menu(self, pos):
        """Right-click context menu on a query in the list."""
        item = self.list_queries.itemAt(pos)
        if item is None:
            return
        query_name = item.text()
        menu = QMenu(self)
        act_inspect = menu.addAction("Inspect")

        # Run Query — load data into memory
        is_loaded = query_name in self._loaded_queries
        if is_loaded:
            act_run = menu.addAction("Reload Data Into Memory")
        else:
            act_run = menu.addAction("Run Query  (load data)")

        menu.addSeparator()
        act_remove = menu.addAction("Remove")
        chosen = menu.exec(self.list_queries.viewport().mapToGlobal(pos))
        if chosen is act_inspect:
            self._show_inspect(query_name)
        elif chosen is act_run:
            self.run_query_requested.emit(query_name)
        elif chosen is act_remove:
            self._remove_query_by_name(query_name)

    def _show_inspect(self, query_name: str):
        """Display full query details in the right panel."""
        sq = self._sources.get(query_name)
        if not sq:
            return

        lines = []
        lines.append(f"Query: {sq.name}")
        lines.append(f"Source Group: {sq.source_group or '(none)'}")
        lines.append("")

        # Database / connection info
        lines.append("=" * 50)
        lines.append("DATABASE")
        lines.append("=" * 50)
        lines.append(f"DSN: {sq.dsn or '(none)'}")
        lines.append(f"Tables: {', '.join(sq.tables) if sq.tables else '(none)'}")
        lines.append("")

        # Fields
        lines.append("=" * 50)
        lines.append(f"FIELDS  ({len(sq.result_columns)})")
        lines.append("=" * 50)
        if sq.result_columns:
            type_map = sq.column_types or {}
            for col in sq.result_columns:
                display = col
                for key, dname in sq.display_names.items():
                    if key.endswith(f".{col}"):
                        display = dname
                        break
                col_type = type_map.get(col, "")
                parts = [f"  {col}"]
                if col_type:
                    parts.append(f"[{col_type}]")
                if display != col:
                    parts.append(f"->  {display}")
                lines.append("  ".join(parts))
        else:
            lines.append("  (no columns — run the query first to capture them)")
        lines.append("")

        # SQL
        lines.append("=" * 50)
        lines.append("SQL")
        lines.append("=" * 50)
        lines.append(sq.sql if sq.sql else "(no SQL stored)")
        lines.append("")

        # Saved date
        lines.append("=" * 50)
        lines.append(f"Saved: {sq.created_at.strftime('%Y-%m-%d %H:%M')}")

        self._lbl_inspect_title.setText(f"Inspect — {query_name}")
        self._txt_inspect.setPlainText("\n".join(lines))
        self._right_stack.setCurrentIndex(1)

    def _remove_query_by_name(self, name: str):
        """Remove a query source by name (shared by context menu and button)."""
        reply = QMessageBox.question(
            self, "Remove Query",
            f"Remove query '{name}' from this DataForge?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        if reply == QMessageBox.StandardButton.Yes:
            self._sources.pop(name, None)
            self._field_cache.pop(name, None)
            self._refresh_query_list()
            self.sources_changed.emit(list(self._sources.keys()))

    def _load_fields(self, query_name: str):
        """Load field metadata for a saved query.

        Prefers result_columns (the SELECT columns) so only fields
        actually in the query are shown.  Falls back to ODBC table
        metadata when result_columns is empty.
        """
        if query_name in self._field_cache:
            self._populate_fields(query_name, self._field_cache[query_name])
            return

        sq = self._sources.get(query_name)
        if not sq:
            return

        # Prefer result_columns — these are the columns from the SELECT
        if sq.result_columns and sq.column_types:
            # We have both column names and saved type metadata — use directly
            type_map = sq.column_types
            cols = [(c, type_map.get(c, ""), "", "") for c in sq.result_columns]
            self._field_cache[query_name] = cols
            self._populate_fields(query_name, cols)
        elif sq.dsn and sq.tables:
            # Fetch live ODBC metadata (will be filtered to result_columns if available)
            self.tree_fields.clear()
            self.lbl_field_status.setText("Loading fields...")

            self._loader = _QueryFieldLoaderThread(sq.dsn, sq.tables, self)
            self._loader.columns_loaded.connect(
                lambda cols: self._on_fields_loaded(query_name, cols))
            self._loader.error_occurred.connect(
                lambda msg: self._on_fields_error(query_name, msg))
            self._loader.start()
        else:
            cols = []
            self._field_cache[query_name] = cols
            self._populate_fields(query_name, cols)

    def _on_fields_loaded(self, query_name: str, columns: list[tuple]):
        # If we have result_columns, filter ODBC metadata to only those columns
        # (preserving the SELECT order) so we show query fields, not all table fields
        sq = self._sources.get(query_name)
        if sq and sq.result_columns:
            col_lookup = {name: (name, tname, sz, null)
                          for name, tname, sz, null in columns}
            columns = [col_lookup.get(c, (c, "", "", ""))
                       for c in sq.result_columns]
        self._field_cache[query_name] = columns
        if self._current_query == query_name:
            self._populate_fields(query_name, columns)
        self._loader = None

    def _on_fields_error(self, query_name: str, msg: str):
        """ODBC failed — fall back to result_columns."""
        logger.warning("ODBC field load failed for %s: %s", query_name, msg)
        sq = self._sources.get(query_name)
        if sq and sq.result_columns:
            type_map = sq.column_types or {}
            cols = [(c, type_map.get(c, ""), "", "") for c in sq.result_columns]
            self._field_cache[query_name] = cols
            self._populate_fields(query_name, cols)
            self.lbl_field_status.setText(
                f"{len(cols)} fields (from result columns)")
        else:
            self.lbl_field_status.setText("No field information available")
        self._loader = None

    def _populate_fields(self, query_name: str, columns: list[tuple]):
        self.tree_fields.clear()
        sq = self._sources.get(query_name)
        display_names = sq.display_names if sq else {}

        for col_name, type_name, size, nullable in columns:
            # Try to find a display name from the saved query
            display = col_name
            for key, dname in display_names.items():
                if key.endswith(f".{col_name}"):
                    display = dname
                    break

            item = QTreeWidgetItem([
                col_name,
                type_name,
                str(size) if size else "",
                display,
                nullable,
            ])
            item.setData(0, Qt.ItemDataRole.UserRole, query_name)
            self.tree_fields.addTopLevelItem(item)

        self.lbl_field_status.setText(f"{len(columns)} fields")

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
        act_place = menu.addAction("Place on Filter")
        chosen = menu.exec(self.tree_fields.viewport().mapToGlobal(pos))
        if chosen is act_place:
            self._on_field_double_clicked(item, 0)

    def _on_field_double_clicked(self, item: QTreeWidgetItem, column: int):
        """Double-click → request auto-placement on current filter tab."""
        query_name = item.data(0, Qt.ItemDataRole.UserRole)
        col_name = item.text(0)
        self.field_requested.emit(query_name, col_name)

    # ── Add / Remove queries ─────────────────────────────────────────

    def _on_add_query(self):
        """Show a picker to add saved queries as sources (mirrors _AddTableDialog)."""
        all_queries = qdef_store.list_qdefs(forge_name=self._forge_name)
        if not all_queries:
            QMessageBox.information(
                self, "No QDefinitions",
                "No QDefinitions found. Create and save a QDefinition first.")
            return

        current_names = set(self._sources.keys())
        available = [sq for sq in all_queries if sq.name not in current_names]
        if not available:
            QMessageBox.information(
                self, "All Added",
                "All saved queries are already added as sources.")
            return

        dlg = QDialog(self)
        dlg.setWindowTitle("Add Query Definitions")
        dlg.setMinimumSize(400, 400)
        lay = QVBoxLayout(dlg)

        txt_search = QLineEdit()
        txt_search.setPlaceholderText("Search QDefinitions...")
        txt_search.setClearButtonEnabled(True)
        txt_search.setFixedHeight(24)
        lay.addWidget(txt_search)

        lst = QListWidget()
        lst.setStyleSheet(_LIST_STYLE)
        lst.setItemDelegate(TightItemDelegate(lst))
        lst.setSelectionMode(
            QAbstractItemView.SelectionMode.MultiSelection)
        for sq in available:
            lst.addItem(sq.name)
        lay.addWidget(lst, 1)

        lbl_status = QLabel(f"{len(available)} available")
        lbl_status.setFont(QFont("Segoe UI", 8))
        lbl_status.setStyleSheet("color: #666;")
        lay.addWidget(lbl_status)

        def _filter(text):
            filt = text.strip().lower()
            for i in range(lst.count()):
                item = lst.item(i)
                item.setHidden(filt not in item.text().lower() if filt else False)

        txt_search.textChanged.connect(_filter)

        btn_row = QHBoxLayout()
        btn_row.addStretch()
        btn_add = QPushButton("Add Selected")
        btn_add.setStyleSheet(_BTN_STYLE)
        btn_add.clicked.connect(dlg.accept)
        btn_row.addWidget(btn_add)
        btn_cancel = QPushButton("Cancel")
        btn_cancel.clicked.connect(dlg.reject)
        btn_row.addWidget(btn_cancel)
        lay.addLayout(btn_row)

        if dlg.exec() != QDialog.DialogCode.Accepted:
            return

        added = []
        for i in range(lst.count()):
            item = lst.item(i)
            if item.isSelected():
                name = item.text()
                sq = next((q for q in all_queries if q.name == name), None)
                if sq:
                    self._sources[name] = sq
                    added.append(name)

        if added:
            self._refresh_query_list()
            self.sources_changed.emit(list(self._sources.keys()))

    def _on_remove_query(self):
        current = self.list_queries.currentItem()
        if current is None:
            return
        self._remove_query_by_name(current.text())

    def _on_view_query(self):
        """Emit view request for the selected query."""
        current = self.list_queries.currentItem()
        if current is None:
            QMessageBox.information(self, "No Selection", "Select a query first.")
            return
        self.view_query_requested.emit(current.text())

    # ── Public accessors ─────────────────────────────────────────────

    def get_sources(self) -> dict[str, QDefinition]:
        return dict(self._sources)

    def get_source_names(self) -> list[str]:
        return list(self._sources.keys())
