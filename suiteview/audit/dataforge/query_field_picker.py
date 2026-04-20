"""
QueryFieldPicker — sidebar for DataForge with 3 columns:
  DataForge list | Queries (sources) | Fields (columns)

Purple-themed to match the DataForge identity.
"""
from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from PyQt6.QtCore import Qt, QMimeData, pyqtSignal
from PyQt6.QtGui import QFont, QDrag
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
    QListWidget, QAbstractItemView, QSplitter, QPushButton,
    QMenu,
)

from suiteview.audit.saved_query import SavedQuery
from suiteview.audit import saved_query_store as sq_store
from suiteview.audit.tabs._styles import TightItemDelegate

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)

_FONT = QFont("Segoe UI", 9)
_FONT_BOLD = QFont("Segoe UI", 9, QFont.Weight.Bold)
_FONT_SMALL = QFont("Segoe UI", 8)

FORGE_FIELD_DRAG_MIME = "application/x-dataforge-field-drag"

# ── Teal-themed styles ────────────────────────────────────────────
_TEAL = "#0D9488"
_TEAL_DARK = "#0F766E"
_TEAL_LIGHT = "#B2DFDB"
_TEAL_BG = "#E6F5F3"
_TEAL_HOVER = "#14B8A6"
_TEAL_DEEP = "#004D40"


def _make_list_style(border: str, sel_bg: str, sel_fg: str) -> str:
    return (
        f"QListWidget {{ border: 1px solid {border}; background-color: white;"
        f" font-size: 9pt; outline: none; }}"
        f"QListWidget::item {{ padding: 0px 2px; border: none; }}"
        f"QListWidget::item:selected {{ background-color: {sel_bg}; color: {sel_fg}; border: none; }}"
        f"QListWidget::item:focus {{ outline: none; border: none; }}"
    )


_FORGE_LIST_STYLE = _make_list_style(_TEAL, _TEAL_LIGHT, _TEAL_DEEP)
_QUERY_LIST_STYLE = _make_list_style(_TEAL, _TEAL_LIGHT, _TEAL_DEEP)
_FIELD_LIST_STYLE = _make_list_style(_TEAL, _TEAL_LIGHT, _TEAL_DEEP)

_HEADER_STYLE = (
    f"QLabel {{ color: white; font-size: 8pt; font-weight: bold;"
    f" padding: 2px 4px; background-color: {_TEAL};"
    f" border: 1px solid {_TEAL_DARK}; border-radius: 2px; }}"
)

_SEARCH_STYLE = (
    f"QLineEdit {{ border: 1px solid {_TEAL}; border-radius: 2px;"
    f" padding: 1px 4px; font-size: 8pt; }}"
    f"QLineEdit:focus {{ border: 1px solid {_TEAL_DARK}; }}"
)

_BTN_STYLE = (
    f"QPushButton {{ background-color: {_TEAL_BG}; color: {_TEAL_DARK};"
    f" border: 1px solid {_TEAL}; border-radius: 2px;"
    f" padding: 1px 6px; font-size: 8pt; }}"
    f"QPushButton:hover {{ background-color: {_TEAL_LIGHT}; }}"
)

_NEW_BTN_STYLE = (
    f"QPushButton {{ background-color: {_TEAL}; color: white;"
    f" border: 1px solid {_TEAL_DARK}; border-radius: 2px;"
    f" padding: 1px 6px; font-size: 8pt; font-weight: bold; }}"
    f"QPushButton:hover {{ background-color: {_TEAL_HOVER}; }}"
)

_VIEW_BTN_STYLE = (
    f"QPushButton {{ background-color: {_TEAL_DARK}; color: white;"
    f" border: 1px solid {_TEAL_DEEP}; border-radius: 2px;"
    f" padding: 1px 6px; font-size: 8pt; }}"
    f"QPushButton:hover {{ background-color: {_TEAL}; }}"
)


class DraggableQueryFieldList(QListWidget):
    """QListWidget that supports dragging query field items out."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setDragEnabled(True)
        self.setDragDropMode(QAbstractItemView.DragDropMode.DragOnly)
        self.setSelectionMode(
            QAbstractItemView.SelectionMode.ExtendedSelection)
        self._field_data: dict[str, tuple] = {}  # display_text → (query_name, col_name)

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
                query_name, col_name = info
                lines.append(f"{query_name}|{col_name}")
        if not lines:
            return
        drag = QDrag(self)
        mime = QMimeData()
        payload = "\n".join(lines)
        mime.setData(FORGE_FIELD_DRAG_MIME, payload.encode("utf-8"))
        drag.setMimeData(mime)
        drag.exec(Qt.DropAction.CopyAction)


class QueryFieldPicker(QWidget):
    """Side panel: DataForge list | Queries list | Fields list with purple theme."""
    field_requested = pyqtSignal(str, str)       # query_name, column_name
    sources_changed = pyqtSignal(list)           # emitted when queries added via + Query
    forge_clicked = pyqtSignal(str)              # forge name clicked → load it
    new_forge_requested = pyqtSignal()           # user clicked "+ New"
    splitter_changed = pyqtSignal()              # internal column widths changed

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumWidth(300)
        self.setMaximumWidth(600)

        self._sources: dict[str, SavedQuery] = {}  # query_name → SavedQuery
        self._current_query: str = ""
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
            f"QSplitter::handle {{ background: {_TEAL_LIGHT}; }}"
            f"QSplitter::handle:hover {{ background: {_TEAL}; }}")

        # ── Left: DataForge list ─────────────────────────────────
        forge_frame = QWidget()
        forge_frame.setStyleSheet(f"QWidget {{ background-color: {_TEAL_BG}; }}")
        fl_lay = QVBoxLayout(forge_frame)
        fl_lay.setContentsMargins(4, 4, 2, 4)
        fl_lay.setSpacing(3)

        lbl_forge = QLabel("DataForge")
        lbl_forge.setStyleSheet(_HEADER_STYLE)
        fl_lay.addWidget(lbl_forge)

        self.txt_forge_search = QLineEdit()
        self.txt_forge_search.setFont(_FONT_SMALL)
        self.txt_forge_search.setPlaceholderText("Search forges...")
        self.txt_forge_search.setClearButtonEnabled(True)
        self.txt_forge_search.setFixedHeight(22)
        self.txt_forge_search.setStyleSheet(_SEARCH_STYLE)
        self.txt_forge_search.textChanged.connect(self._filter_forges)
        fl_lay.addWidget(self.txt_forge_search)

        self.list_forges = QListWidget()
        self.list_forges.setFont(_FONT)
        self.list_forges.setStyleSheet(_FORGE_LIST_STYLE)
        self.list_forges.setItemDelegate(TightItemDelegate(self.list_forges))
        self.list_forges.setUniformItemSizes(True)
        self.list_forges.setSelectionMode(
            QAbstractItemView.SelectionMode.SingleSelection)
        self.list_forges.itemClicked.connect(self._on_forge_clicked)
        fl_lay.addWidget(self.list_forges)

        btn_new = QPushButton("+ New")
        btn_new.setFont(_FONT_SMALL)
        btn_new.setFixedHeight(20)
        btn_new.setStyleSheet(_NEW_BTN_STYLE)
        btn_new.clicked.connect(self.new_forge_requested)
        fl_lay.addWidget(btn_new)

        splitter.addWidget(forge_frame)

        # ── Middle: Queries (sources) ────────────────────────────
        queries_frame = QWidget()
        queries_frame.setStyleSheet(f"QWidget {{ background-color: {_TEAL_BG}; }}")
        ql = QVBoxLayout(queries_frame)
        ql.setContentsMargins(2, 4, 2, 4)
        ql.setSpacing(3)

        lbl_queries = QLabel("Queries")
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
        self.list_queries.currentItemChanged.connect(self._on_query_selected)
        ql.addWidget(self.list_queries)

        # ── + Query / View buttons ─────────────────────────────
        q_btns = QHBoxLayout()
        q_btns.setContentsMargins(0, 0, 0, 0)
        q_btns.setSpacing(3)

        self.btn_add_query = QPushButton("+ Query")
        self.btn_add_query.setFont(_FONT_SMALL)
        self.btn_add_query.setFixedHeight(20)
        self.btn_add_query.setStyleSheet(_BTN_STYLE)
        self.btn_add_query.clicked.connect(self._on_add_query)
        q_btns.addWidget(self.btn_add_query)

        self.btn_view_query = QPushButton("View")
        self.btn_view_query.setFont(_FONT_SMALL)
        self.btn_view_query.setFixedHeight(20)
        self.btn_view_query.setStyleSheet(_VIEW_BTN_STYLE)
        self.btn_view_query.setToolTip("Preview query results")
        self.btn_view_query.clicked.connect(self._on_view_query)
        q_btns.addWidget(self.btn_view_query)

        q_btns.addStretch()
        ql.addLayout(q_btns)

        splitter.addWidget(queries_frame)

        # ── Right: Fields ────────────────────────────────────────
        fields_frame = QWidget()
        fields_frame.setStyleSheet(f"QWidget {{ background-color: {_TEAL_BG}; }}")
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

        self.list_fields = DraggableQueryFieldList()
        self.list_fields.setFont(_FONT)
        self.list_fields.setStyleSheet(_FIELD_LIST_STYLE)
        self.list_fields.setItemDelegate(TightItemDelegate(self.list_fields))
        self.list_fields.setUniformItemSizes(True)
        self.list_fields.itemDoubleClicked.connect(self._on_field_double_clicked)
        fl.addWidget(self.list_fields)

        self.lbl_status = QLabel("")
        self.lbl_status.setFont(_FONT_SMALL)
        self.lbl_status.setStyleSheet(f"color: {_TEAL_DARK};")
        fl.addWidget(self.lbl_status)

        splitter.addWidget(fields_frame)

        splitter.setStretchFactor(0, 1)  # forges
        splitter.setStretchFactor(1, 1)  # queries
        splitter.setStretchFactor(2, 3)  # fields

        self._splitter = splitter
        splitter.splitterMoved.connect(self._on_splitter_moved)
        root.addWidget(splitter)

    # ── Public API ────────────────────────────────────────────────

    def set_sources(self, source_query_names: list[str]):
        """Load query names and their field metadata."""
        self._sources.clear()
        self._current_query = ""
        self.list_queries.clear()
        self.list_fields.clear()
        self.lbl_status.setText("")

        for name in source_query_names:
            sq = sq_store.load_query(name)
            if sq:
                self._sources[name] = sq
                self.list_queries.addItem(name)

        if source_query_names:
            self.list_queries.setCurrentRow(0)

    def add_source(self, query_name: str):
        """Add a single query source."""
        if query_name in self._sources:
            return
        sq = sq_store.load_query(query_name)
        if sq:
            self._sources[query_name] = sq
            self.list_queries.addItem(query_name)

    def remove_source(self, query_name: str):
        """Remove a query source."""
        self._sources.pop(query_name, None)
        for i in range(self.list_queries.count()):
            if self.list_queries.item(i).text() == query_name:
                self.list_queries.takeItem(i)
                break
        if self._current_query == query_name:
            self._current_query = ""
            self.list_fields.clear()
            self.lbl_status.setText("")

    def clear(self):
        self._sources.clear()
        self._current_query = ""
        self.list_queries.clear()
        self.list_fields.clear()
        self.lbl_status.setText("")

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

    # ── Forge list API ────────────────────────────────────────────

    def set_forges(self, names: list[str]):
        """Populate the forge list with saved forge names."""
        self.list_forges.clear()
        for name in sorted(names, key=str.lower):
            self.list_forges.addItem(name)

    def highlight_forge(self, name: str):
        """Select the given forge name in the list (no signal)."""
        self.list_forges.blockSignals(True)
        for i in range(self.list_forges.count()):
            item = self.list_forges.item(i)
            item.setSelected(item.text() == name)
        self.list_forges.blockSignals(False)

    def _filter_forges(self, text: str):
        filt = text.strip().lower()
        for i in range(self.list_forges.count()):
            item = self.list_forges.item(i)
            item.setHidden(filt not in item.text().lower() if filt else False)

    def _on_forge_clicked(self, item):
        self.forge_clicked.emit(item.text())

    def _filter_queries(self, text: str):
        filt = text.strip().lower()
        for i in range(self.list_queries.count()):
            item = self.list_queries.item(i)
            item.setHidden(filt not in item.text().lower() if filt else False)

    def _on_query_selected(self, current, previous):
        if current is None:
            return
        query_name = current.text()
        if query_name == self._current_query:
            return
        self._current_query = query_name
        self._populate_fields(query_name)

    def _populate_fields(self, query_name: str):
        """Populate the fields list from a saved query's result_columns."""
        self.list_fields.clear()
        sq = self._sources.get(query_name)
        if not sq:
            self.lbl_status.setText("Query not found")
            return

        columns = sq.result_columns
        if not columns:
            self.lbl_status.setText("No columns (run query first)")
            return

        field_data: dict[str, tuple] = {}
        for col_name in columns:
            self.list_fields.addItem(col_name)
            field_data[col_name] = (query_name, col_name)
        self.list_fields.set_field_data(field_data)
        self.lbl_status.setText(f"{len(columns)} fields")

    def _filter_fields(self, text: str):
        filt = text.strip().lower()
        for i in range(self.list_fields.count()):
            item = self.list_fields.item(i)
            item.setHidden(filt not in item.text().lower() if filt else False)

    def _on_field_double_clicked(self, item):
        info = self.list_fields._field_data.get(item.text())
        if info:
            query_name, col_name = info
            self.field_requested.emit(query_name, col_name)

    # ── Query buttons ─────────────────────────────────────────

    def _on_add_query(self):
        """Pick a saved query to add as a DataForge source."""
        all_queries = sq_store.list_queries()
        existing = set(self._sources.keys())
        available = [sq for sq in all_queries if sq.name not in existing]
        if not available:
            return

        menu = QMenu(self)
        for sq in available:
            menu.addAction(f"{sq.name}  ({sq.dsn})")

        chosen = menu.exec(self.btn_add_query.mapToGlobal(
            self.btn_add_query.rect().topRight()))
        if chosen:
            # Extract name from "name  (dsn)" label
            name = chosen.text().split("  (")[0]
            self.add_source(name)
            self.sources_changed.emit(list(self._sources.keys()))

    def _on_view_query(self):
        """Preview the selected query's results."""
        current = self.list_queries.currentItem()
        if current is None:
            return
        query_name = current.text()
        sq = self._sources.get(query_name)
        if not sq or not sq.dsn:
            return
        from suiteview.audit.dialogs.tables_dialog import _TablePreviewDialog
        # Build a simple SQL from the saved query to preview
        # Use the query's built SQL if available, otherwise show table preview
        if hasattr(sq, 'sql') and sq.sql:
            dlg = _TablePreviewDialog(sq.dsn, sq.sql, self)
        else:
            # Fallback: show first source table
            tables = sq.tables if hasattr(sq, 'tables') and sq.tables else []
            if tables:
                dlg = _TablePreviewDialog(sq.dsn, tables[0], self)
            else:
                return
        dlg.show()
