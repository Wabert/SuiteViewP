"""
QueryFieldPicker — sidebar for DataForge:
  Forge Assist header | Query Objects multi-select dropdown | Queries + Fields

Forge heat-themed to match the DataForge identity.
"""
from __future__ import annotations

import logging

from PyQt6.QtCore import Qt, QMimeData, pyqtSignal
from PyQt6.QtGui import QColor, QFont, QDrag
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
    QListWidget, QListWidgetItem, QAbstractItemView, QSplitter, QPushButton,
    QDialog, QMenu, QTreeWidget, QTreeWidgetItem, QApplication, QMessageBox,
)

from suiteview.audit.qdefinition import QDefinition
from suiteview.audit import qdef_store
from suiteview.audit.query_object import (
    OBJECT_KIND_ADHOC_SOURCE,
    QueryObject,
    manual_sql_query_object,
    object_from_qdefinition,
    qdefinition_from_query_object,
)
from suiteview.audit import query_object_store
from suiteview.audit.adhoc_source_intake import dataframe_from_adhoc_metadata
from suiteview.audit.query_runner import execute_odbc_query
from suiteview.audit.tabs._styles import TightItemDelegate
from suiteview.audit.query_object_viewer_window import (
    _dataforge_display_name,
    _dataforge_info,
    _display_dsn_for_object,
    _file_source_type_label,
    _object_group_label,
    _object_group_order,
)

logger = logging.getLogger(__name__)

_FILE_SOURCE_DESIGNS = {"csv", "excel", "fixed_width"}


def _forge_copy_source_name(name: str, forge_name: str = "") -> str:
    """Return the original source name for a DataForge-local copy name."""
    clean = name.strip()
    forge = forge_name.strip()
    if forge and clean.endswith(f" [{forge}]"):
        return clean[:-(len(forge) + 3)].strip()
    if clean.endswith("]"):
        source, sep, _suffix = clean.rpartition(" [")
        if sep and source.strip():
            return source.strip()
    return ""


def _is_file_source_qdefinition(source: QDefinition) -> bool:
    if getattr(source, "query_object_kind", "") == OBJECT_KIND_ADHOC_SOURCE:
        return True
    source_design = str(getattr(source, "source_design", "")).strip().lower()
    metadata = getattr(source, "query_object_source_metadata", {}) or {}
    return source_design in _FILE_SOURCE_DESIGNS and bool(metadata)


def _repair_flat_file_qdefinition(
    source: QDefinition,
    requested_name: str,
    forge_name: str = "",
) -> QDefinition:
    """Patch stale forge-local QDefinitions with metadata from the file source object."""
    if _is_file_source_qdefinition(source):
        return source

    candidates: list[str] = []
    config = getattr(source, "query_object_config", {}) or {}
    dataforge = config.get("dataforge", {}) if isinstance(config, dict) else {}
    source_name = str(dataforge.get("source_name", "")).strip()
    for candidate in (
        requested_name,
        getattr(source, "name", ""),
        source_name,
        _forge_copy_source_name(requested_name, forge_name),
        _forge_copy_source_name(getattr(source, "name", ""), forge_name),
    ):
        candidate = str(candidate).strip()
        if candidate and candidate not in candidates:
            candidates.append(candidate)

    for candidate in candidates:
        obj = query_object_store.load_object(candidate)
        if obj is None or obj.kind != OBJECT_KIND_ADHOC_SOURCE:
            continue
        repaired = qdefinition_from_query_object(obj)
        repaired.name = getattr(source, "name", "") or requested_name
        repaired.forge_name = getattr(source, "forge_name", "") or forge_name
        repaired.query_object_config = dict(repaired.query_object_config or {})
        if repaired.forge_name:
            repaired.query_object_config.setdefault("dataforge", {
                "forge_name": repaired.forge_name,
                "source_name": obj.name,
            })
        return repaired
    return source


def _load_query_source(name: str, forge_name: str = "") -> QDefinition | None:
    """Load a DataForge source by name from QDefs first, then QueryObjects."""
    sq = qdef_store.load_qdef(name, forge_name=forge_name)
    if not sq:
        sq = qdef_store.load_qdef(name)
    if sq:
        return _repair_flat_file_qdefinition(sq, name, forge_name=forge_name)
    obj = query_object_store.load_object(name)
    if obj:
        return qdefinition_from_query_object(obj)
    return None


def _list_query_sources() -> list[QDefinition]:
    """Return QDefinition-shaped sources from QDefs plus object-only QueryObjects."""
    sources: dict[str, QDefinition] = {qd.name: qd for qd in qdef_store.list_qdefs()}
    for obj in query_object_store.list_objects():
        if obj.name not in sources:
            sources[obj.name] = qdefinition_from_query_object(obj)
    return sorted(sources.values(), key=lambda qd: qd.name.lower())


def _source_kind_label(source: QDefinition) -> str:
    kind = getattr(source, "query_object_kind", "")
    labels = {
        "visual_query": "Visual",
        "executable_query": "Executable",
        "cyberlife_query": "Cyberlife",
        "manual_sql": "Manual SQL",
        "adhoc_source": "Ad Hoc",
    }
    if kind in labels:
        return labels[kind]
    if source.source_design:
        return "Executable"
    return "Query"


def _source_dsn_label(source: QDefinition | QueryObject) -> str:
    kind = getattr(source, "query_object_kind", getattr(source, "kind", ""))
    if kind == OBJECT_KIND_ADHOC_SOURCE:
        if isinstance(source, QueryObject):
            return _display_dsn_for_object(source)
        return _file_source_type_label(
            str(getattr(source, "source_design", "")),
            getattr(source, "query_object_source_metadata", {}) or {},
        )
    return str(getattr(source, "dsn", "")).strip()


def _source_group_label(source: QDefinition) -> str:
    kind = getattr(source, "query_object_kind", "")
    labels = {
        "visual_query": "Visual Queries",
        "executable_query": "Executable Queries",
        "cyberlife_query": "Cyberlife Objects",
        "manual_sql": "Manual SQL Objects",
        "adhoc_source": "File Sources",
    }
    if kind in labels:
        return labels[kind]
    if source.source_design:
        return "Executable Queries"
    return "Queries"


def _copy_source_name(query_object_name: str, forge_name: str) -> str:
    label = forge_name.strip() or "DataForge"
    return f"{query_object_name} [{label}]"


def _group_query_objects_for_selector(query_objects: list[QueryObject]) -> tuple[
        dict[str, list[QueryObject]], dict[str, list[QueryObject]]]:
    groups: dict[str, list[QueryObject]] = {}
    dataforge_groups: dict[str, list[QueryObject]] = {}
    for obj in query_objects:
        dataforge_info = _dataforge_info(obj)
        if dataforge_info is not None:
            forge_name, _ = dataforge_info
            dataforge_groups.setdefault(forge_name, []).append(obj)
            continue
        groups.setdefault(_object_group_label(obj), []).append(obj)
    return groups, dataforge_groups


_FONT = QFont("Segoe UI", 9)
_FONT_BOLD = QFont("Segoe UI", 9, QFont.Weight.Bold)
_FONT_SMALL = QFont("Segoe UI", 8)

FORGE_FIELD_DRAG_MIME = "application/x-dataforge-field-drag"

_FORGE = "#EA580C"
_FORGE_DARK = "#C2410C"
_FORGE_LIGHT = "#FED7AA"
_FORGE_BG = "#FFF3E8"
_FORGE_DEEP = "#7C2D12"


def _make_list_style(border: str, sel_bg: str, sel_fg: str) -> str:
    return (
        f"QListWidget {{ border: 1px solid {border}; background-color: white;"
        " font-size: 9pt; outline: none; }"
        "QListWidget::item { padding: 0px 2px; border: none; }"
        f"QListWidget::item:selected {{ background-color: {sel_bg}; color: {sel_fg}; border: none; }}"
        "QListWidget::item:focus { outline: none; border: none; }"
    )


_FIELD_LIST_STYLE = _make_list_style(_FORGE_DARK, _FORGE_LIGHT, _FORGE_DEEP)
_QUERY_LIST_STYLE = _make_list_style(_FORGE_DARK, _FORGE_LIGHT, _FORGE_DEEP)
_QUERY_TREE_STYLE = (
    f"QTreeWidget {{ border: 1px solid {_FORGE_DARK}; background: white;"
    " font-size: 9pt; outline: none; }"
    "QTreeWidget::item { padding: 1px 4px; border: none; }"
    f"QTreeWidget::item:selected {{ background-color: {_FORGE_LIGHT}; color: {_FORGE_DEEP}; border: none; }}"
    "QTreeWidget::item:focus { outline: none; border: none; }"
)

_HEADER_STYLE = (
    f"QLabel, QPushButton {{ color: white; font-size: 8pt; font-weight: bold;"
    f" padding: 2px 4px; background-color: {_FORGE_DARK};"
    f" border: 1px solid {_FORGE_DEEP}; border-radius: 2px; }}"
    f"QPushButton:hover {{ background-color: {_FORGE}; }}"
)

_SEARCH_STYLE = (
    f"QLineEdit {{ border: 1px solid {_FORGE_DARK}; border-radius: 2px;"
    " padding: 1px 4px; font-size: 8pt; }"
    f"QLineEdit:focus {{ border: 1px solid {_FORGE_DEEP}; }}"
)

_BTN_STYLE = (
    f"QPushButton {{ background-color: {_FORGE_BG}; color: {_FORGE_DARK};"
    f" border: 1px solid {_FORGE_DARK}; border-radius: 2px;"
    " padding: 1px 6px; font-size: 8pt; }"
    f"QPushButton:hover {{ background-color: {_FORGE_LIGHT}; }}"
)

_NEW_BTN_STYLE = (
    f"QPushButton {{ background-color: {_FORGE_DARK}; color: white;"
    f" border: 1px solid {_FORGE_DEEP}; border-radius: 2px;"
    " padding: 1px 6px; font-size: 8pt; font-weight: bold; }"
    f"QPushButton:hover {{ background-color: {_FORGE}; }}"
)

class DraggableQueryFieldList(QListWidget):
    """QListWidget that supports dragging query field items out."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setDragEnabled(True)
        self.setDragDropMode(QAbstractItemView.DragDropMode.DragOnly)
        self.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self._field_data: dict[str, tuple[str, str]] = {}

    def set_field_data(self, data: dict[str, tuple[str, str]]):
        self._field_data = data

    def startDrag(self, supportedActions):
        lines = []
        for item in self.selectedItems():
            info = self._field_data.get(item.text())
            if info:
                query_name, col_name = info
                lines.append(f"{query_name}|{col_name}")
        if not lines:
            return
        drag = QDrag(self)
        mime = QMimeData()
        mime.setData(FORGE_FIELD_DRAG_MIME, "\n".join(lines).encode("utf-8"))
        drag.setMimeData(mime)
        drag.exec(Qt.DropAction.CopyAction)


class QueryFieldPicker(QWidget):
    """Side panel: Forge Assist query source picker and field list."""
    field_requested = pyqtSignal(str, str)
    sources_changed = pyqtSignal(list)
    source_refreshed = pyqtSignal(str, object)
    query_table_requested = pyqtSignal(str)
    forge_clicked = pyqtSignal(str)
    new_forge_requested = pyqtSignal()
    splitter_changed = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumWidth(300)
        self.setMaximumWidth(600)
        self._sources: dict[str, QDefinition] = {}
        self._current_query = ""
        self._current_forge_name = ""
        self._fields_sort_ascending = True
        self._pending_sizes: list[int] | None = None
        self._last_good_sizes: list[int] | None = None
        self._available_query_sources: list[QDefinition] = []
        self._forge_names: list[str] = []
        self._builder_windows: list[QDialog] = []
        self._build_ui()

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(4, 4, 4, 4)
        root.setSpacing(4)
        self.setStyleSheet(f"QWidget {{ background-color: {_FORGE_BG}; }}")

        lbl_header = QLabel("Forge Assist")
        lbl_header.setFixedHeight(22)
        lbl_header.setStyleSheet(_HEADER_STYLE)
        root.addWidget(lbl_header, 0)

        object_row = QHBoxLayout()
        object_row.setContentsMargins(0, 0, 0, 0)
        object_row.setSpacing(4)
        lbl_query_objects = QLabel("Query Objects")
        lbl_query_objects.setFont(_FONT_BOLD)
        lbl_query_objects.setStyleSheet(f"color: {_FORGE_DARK};")
        self.btn_query_objects = QPushButton("Select queries...")
        self.btn_query_objects.setFont(_FONT_SMALL)
        self.btn_query_objects.setFixedHeight(24)
        self.btn_query_objects.setStyleSheet(_BTN_STYLE)
        self.btn_query_objects.clicked.connect(self._show_query_object_dropdown)
        object_row.addWidget(lbl_query_objects)
        object_row.addWidget(self.btn_query_objects, 1)
        root.addLayout(object_row, 0)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.setHandleWidth(4)
        splitter.setStyleSheet(
            f"QSplitter::handle {{ background: {_FORGE_LIGHT}; }}"
            f"QSplitter::handle:hover {{ background: {_FORGE}; }}")

        queries_frame = QWidget()
        queries_frame.setStyleSheet(f"QWidget {{ background-color: {_FORGE_BG}; }}")
        ql = QVBoxLayout(queries_frame)
        ql.setContentsMargins(2, 4, 2, 4)
        ql.setSpacing(3)

        lbl_queries = QLabel("Queries")
        lbl_queries.setFixedHeight(22)
        lbl_queries.setStyleSheet(_HEADER_STYLE)
        ql.addWidget(lbl_queries)

        self.list_queries = QListWidget()
        self.list_queries.setFont(_FONT)
        self.list_queries.setStyleSheet(_QUERY_LIST_STYLE)
        self.list_queries.setItemDelegate(TightItemDelegate(self.list_queries))
        self.list_queries.setUniformItemSizes(True)
        self.list_queries.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.list_queries.currentItemChanged.connect(self._on_query_selected)
        self.list_queries.itemDoubleClicked.connect(self._on_query_double_clicked)
        self.list_queries.itemSelectionChanged.connect(self._on_query_list_selection_changed)
        self.list_queries.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.list_queries.customContextMenuRequested.connect(self._on_query_context_menu)
        ql.addWidget(self.list_queries, 1)

        splitter.addWidget(queries_frame)

        fields_frame = QWidget()
        fields_frame.setStyleSheet(f"QWidget {{ background-color: {_FORGE_BG}; }}")
        fl = QVBoxLayout(fields_frame)
        fl.setContentsMargins(2, 4, 4, 4)
        fl.setSpacing(3)

        self.btn_fields_header = QPushButton("Fields ↑")
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

        self.list_fields = DraggableQueryFieldList()
        self.list_fields.setFont(_FONT)
        self.list_fields.setStyleSheet(_FIELD_LIST_STYLE)
        self.list_fields.setItemDelegate(TightItemDelegate(self.list_fields))
        self.list_fields.setUniformItemSizes(True)
        self.list_fields.itemDoubleClicked.connect(self._on_field_double_clicked)
        fl.addWidget(self.list_fields, 1)

        self.lbl_status = QLabel("")
        self.lbl_status.setFont(_FONT_SMALL)
        self.lbl_status.setStyleSheet(f"color: {_FORGE_DARK};")
        fl.addWidget(self.lbl_status)
        splitter.addWidget(fields_frame)

        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 1)
        self._splitter = splitter
        splitter.splitterMoved.connect(self._on_splitter_moved)
        root.addWidget(splitter, 1)

    def set_sources(
        self,
        source_query_names: list[str],
        forge_name: str = "",
        source_definitions: dict[str, QDefinition] | None = None,
    ):
        self._sources.clear()
        self._current_query = ""
        self._current_forge_name = forge_name
        self.list_queries.clear()
        self.list_fields.clear()
        self.lbl_status.setText("")
        source_definitions = source_definitions or {}
        for name in source_query_names:
            sq = source_definitions.get(name)
            if sq is not None:
                sq = _repair_flat_file_qdefinition(sq, name, forge_name=forge_name)
            if sq is None:
                sq = _load_query_source(name, forge_name=forge_name)
            if sq:
                self._sources[name] = sq
        self._rebuild_query_list()
        self._update_query_object_button()
        first = self._first_query_item()
        if first:
            self.list_queries.setCurrentItem(first)

    def add_source(self, query_name: str):
        if query_name in self._sources:
            return
        sq = _load_query_source(query_name, forge_name=self._current_forge_name)
        if sq:
            self._sources[query_name] = sq
            self._rebuild_query_list(select_name=query_name)
            self._update_query_object_button()

    def remove_source(self, query_name: str):
        self._sources.pop(query_name, None)
        self._rebuild_query_list()
        self._update_query_object_button()
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
        self._update_query_object_button()

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

    def set_forges(self, names: list[str]):
        self._forge_names = sorted(names, key=str.lower)

    def highlight_forge(self, name: str):
        return

    def _filter_forges(self, text: str):
        return

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
        query_name = current.data(Qt.ItemDataRole.UserRole) or current.text()
        if not query_name or query_name == self._current_query:
            return
        self._current_query = query_name
        self._populate_fields(query_name)

    def _on_query_double_clicked(self, item):
        query_name = item.data(Qt.ItemDataRole.UserRole) or item.text()
        if query_name:
            self.query_table_requested.emit(query_name)

    def _on_query_list_selection_changed(self):
        selected_names = [
            item.data(Qt.ItemDataRole.UserRole) or item.text()
            for item in self.list_queries.selectedItems()
            if item.data(Qt.ItemDataRole.UserRole) or item.text()
        ]
        if len(selected_names) > 1:
            self.lbl_status.setText(f"{len(selected_names)} queries selected")

    def _rebuild_query_list(self, select_name: str = ""):
        current_name = select_name or self._current_query
        self.list_queries.blockSignals(True)
        self.list_queries.clear()
        selected_item = None
        for source in sorted(self._sources.values(), key=lambda qd: self._source_display_name(qd).lower()):
            item = QListWidgetItem(self._source_display_name(source))
            item.setData(Qt.ItemDataRole.UserRole, source.name)
            tooltip = _source_kind_label(source)
            if item.text() != source.name:
                tooltip = f"{tooltip} - stored as {source.name}"
            item.setToolTip(tooltip)
            self.list_queries.addItem(item)
            if source.name == current_name:
                selected_item = item
        self.list_queries.blockSignals(False)
        if selected_item:
            self.list_queries.setCurrentItem(selected_item)

    @staticmethod
    def _source_display_name(source: QDefinition) -> str:
        config = getattr(source, "query_object_config", {}) or {}
        dataforge = config.get("dataforge", {}) if isinstance(config, dict) else {}
        source_name = str(dataforge.get("source_name", "")).strip()
        return source_name or source.name

    def _first_query_item(self):
        return self.list_queries.item(0) if self.list_queries.count() else None

    def _update_query_object_button(self):
        count = len(self._sources)
        self.btn_query_objects.setText(
            "Select queries..." if count == 0 else f"{count} selected")

    def _show_query_object_dropdown(self):
        dlg = QDialog(self)
        dlg.setWindowTitle("Select Query Objects")
        dlg.setMinimumSize(420, 360)
        dlg.resize(560, 520)
        dlg.setStyleSheet(f"QDialog {{ background-color: {_FORGE_BG}; }}")

        lay = QVBoxLayout(dlg)
        lay.setContentsMargins(6, 6, 6, 6)
        lay.setSpacing(4)

        txt_search = QLineEdit()
        txt_search.setFont(_FONT_SMALL)
        txt_search.setPlaceholderText("Search query objects...")
        txt_search.setClearButtonEnabled(True)
        txt_search.setFixedHeight(24)
        txt_search.setStyleSheet(_SEARCH_STYLE)
        lay.addWidget(txt_search)

        tree = QTreeWidget()
        tree.setHeaderHidden(True)
        tree.setFont(_FONT)
        tree.setStyleSheet(_QUERY_TREE_STYLE)
        tree.setItemDelegate(TightItemDelegate(tree))
        tree.setSelectionMode(QAbstractItemView.SelectionMode.MultiSelection)

        query_objects = query_object_store.list_objects()
        groups, dataforge_groups = _group_query_objects_for_selector(query_objects)

        def _add_object_child(parent: QTreeWidgetItem, obj: QueryObject,
                              label: str | None = None):
            dsn = _source_dsn_label(obj)
            suffix = f"  ({dsn})" if dsn else ""
            child = QTreeWidgetItem([f"{label or obj.name}{suffix}"])
            child.setFont(0, _FONT)
            child.setData(0, Qt.ItemDataRole.UserRole, obj.name)
            child.setToolTip(0, _source_kind_label(qdefinition_from_query_object(obj)))
            parent.addChild(child)

        for group_label in sorted(groups, key=_object_group_order):
            parent = QTreeWidgetItem([group_label])
            parent.setFont(0, _FONT_BOLD)
            parent.setForeground(0, QColor(_FORGE_DARK))
            parent.setData(0, Qt.ItemDataRole.UserRole, None)
            parent.setFlags(parent.flags() & ~Qt.ItemFlag.ItemIsSelectable)
            tree.addTopLevelItem(parent)
            for obj in sorted(groups[group_label], key=lambda item: item.name.lower()):
                _add_object_child(parent, obj)
            parent.setExpanded(True)

        if dataforge_groups:
            dataforge_parent = QTreeWidgetItem(["DataForge"])
            dataforge_parent.setFont(0, _FONT_BOLD)
            dataforge_parent.setForeground(0, QColor(_FORGE_DARK))
            dataforge_parent.setData(0, Qt.ItemDataRole.UserRole, None)
            dataforge_parent.setFlags(dataforge_parent.flags() & ~Qt.ItemFlag.ItemIsSelectable)
            tree.addTopLevelItem(dataforge_parent)
            for forge_name in sorted(dataforge_groups, key=str.lower):
                forge_node = QTreeWidgetItem([_dataforge_display_name(forge_name)])
                forge_node.setFont(0, _FONT_BOLD)
                forge_node.setForeground(0, QColor(_FORGE_DARK))
                forge_node.setData(0, Qt.ItemDataRole.UserRole, None)
                forge_node.setFlags(forge_node.flags() & ~Qt.ItemFlag.ItemIsSelectable)
                dataforge_parent.addChild(forge_node)
                for obj in sorted(dataforge_groups[forge_name], key=lambda item: item.name.lower()):
                    _, source_label = _dataforge_info(obj) or (forge_name, obj.name)
                    _add_object_child(forge_node, obj, source_label)
                forge_node.setExpanded(True)
            dataforge_parent.setExpanded(True)
        lay.addWidget(tree, 1)

        lbl_status = QLabel(f"{len(query_objects)} query objects")
        lbl_status.setFont(_FONT_SMALL)
        lbl_status.setStyleSheet(f"color: {_FORGE_DARK};")
        lay.addWidget(lbl_status)

        def _filter(text: str):
            filt = text.strip().lower()
            visible = 0

            def _filter_item(item: QTreeWidgetItem) -> int:
                if item.childCount() == 0:
                    hidden = filt not in item.text(0).lower() if filt else False
                    item.setHidden(hidden)
                    return 0 if hidden else 1
                visible_children = 0
                for idx in range(item.childCount()):
                    visible_children += _filter_item(item.child(idx))
                item.setHidden(visible_children == 0 and bool(filt))
                return visible_children

            for i in range(tree.topLevelItemCount()):
                visible += _filter_item(tree.topLevelItem(i))
            lbl_status.setText(f"{visible} query objects")
        txt_search.textChanged.connect(_filter)

        btn_row = QHBoxLayout()
        btn_row.setContentsMargins(0, 0, 0, 0)
        btn_row.addStretch()
        btn_add = QPushButton("Add Selected")
        btn_add.setFont(_FONT_SMALL)
        btn_add.setStyleSheet(_NEW_BTN_STYLE)
        btn_row.addWidget(btn_add)
        btn_cancel = QPushButton("Cancel")
        btn_cancel.setFont(_FONT_SMALL)
        btn_cancel.setStyleSheet(_BTN_STYLE)
        btn_cancel.clicked.connect(dlg.reject)
        btn_row.addWidget(btn_cancel)
        lay.addLayout(btn_row)

        def _add_selected():
            added = []
            for item in tree.selectedItems():
                name = item.data(0, Qt.ItemDataRole.UserRole)
                if name and name not in self._sources:
                    self.add_source(name)
                    added.append(name)
            if added:
                self.sources_changed.emit(list(self._sources.keys()))
            dlg.accept()
        btn_add.clicked.connect(_add_selected)

        dlg.exec()

    def _populate_fields(self, query_name: str):
        self.list_fields.clear()
        sq = self._sources.get(query_name)
        if not sq:
            self.lbl_status.setText("Query not found")
            return
        columns = sq.result_columns
        if not columns:
            self.lbl_status.setText("No columns (run query first)")
            return

        field_data: dict[str, tuple[str, str]] = {}
        sorted_columns = sorted(
            columns,
            key=lambda column: str(column).lower(),
            reverse=not self._fields_sort_ascending,
        )
        for col_name in sorted_columns:
            self.list_fields.addItem(col_name)
            field_data[col_name] = (query_name, col_name)
        self.list_fields.set_field_data(field_data)
        self.lbl_status.setText(f"{len(columns)} fields")

    def _toggle_fields_sort(self):
        self._fields_sort_ascending = not self._fields_sort_ascending
        self.btn_fields_header.setText("Fields ↑" if self._fields_sort_ascending else "Fields ↓")
        if self._current_query:
            self._populate_fields(self._current_query)

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

    def _on_add_query(self):
        self._show_query_object_dropdown()

    def _on_query_context_menu(self, pos):
        item = self.list_queries.itemAt(pos)
        if item is None:
            return
        query_name = item.data(Qt.ItemDataRole.UserRole) or item.text()
        if not query_name:
            return

        menu = QMenu(self)
        act_preview = menu.addAction("Preview Data")
        act_open_builder = menu.addAction("Open in Builder")
        act_refresh = menu.addAction("Refresh / Requery")
        menu.addSeparator()
        act_modify = menu.addAction("Modify in Browser")
        act_rename = menu.addAction("Rename")
        chosen = menu.exec(self.list_queries.viewport().mapToGlobal(pos))
        if chosen == act_preview:
            self._preview_query_data(query_name)
        elif chosen == act_open_builder:
            self._open_query_builder(query_name)
        elif chosen == act_refresh:
            self._refresh_query_source(query_name)
        elif chosen == act_modify:
            self._modify_query_object(query_name)
        elif chosen == act_rename:
            self._rename_qdef(query_name)

    def _open_query_builder(self, query_name: str):
        audit_window = self._new_audit_window_for_builder(query_name)
        if audit_window is not None:
            audit_window.open_query_object_in_builder(query_name)
            audit_window.raise_()
            audit_window.activateWindow()
            return
        QMessageBox.information(
            self,
            "Builder Unavailable",
            "This query type needs the full Audit builder, but a builder window could not be opened.",
        )

    def _new_audit_window_for_builder(self, query_name: str):
        source = self._sources.get(query_name)
        existing = query_object_store.load_object(query_name)
        if source is not None and (existing is None or self._should_republish_builder_source(query_name, source, existing)):
            try:
                query_object_store.save_object(object_from_qdefinition(source))
            except Exception:
                logger.exception("Failed to publish source for Audit builder: %s", query_name)
        try:
            from suiteview.audit.main import create_audit_window
            window = create_audit_window()
        except Exception:
            logger.exception("Failed to create AuditWindow for source builder: %s", query_name)
            return None
        self._builder_windows.append(window)
        window.destroyed.connect(lambda _=None, win=window: self._forget_builder_window(win))
        return window

    @staticmethod
    def _should_republish_builder_source(query_name: str, source: QDefinition, existing: QueryObject) -> bool:
        if (existing.config or {}).get("dataforge"):
            return False
        if getattr(source, "forge_name", ""):
            return True
        return bool(_forge_copy_source_name(query_name))

    def _forget_builder_window(self, window):
        if window in self._builder_windows:
            self._builder_windows.remove(window)

    def _open_file_source_builder(self, query_name: str, obj: QueryObject):
        from suiteview.audit.tabs.csv_excel_object_editor import CsvExcelObjectEditor

        dlg = QDialog(self)
        dlg.setWindowTitle(f"File Source Builder - {query_name}")
        dlg.resize(1120, 680)
        layout = QVBoxLayout(dlg)
        layout.setContentsMargins(4, 4, 4, 4)
        editor = CsvExcelObjectEditor(dlg)
        editor.load_object(obj)
        editor.saved.connect(lambda saved_name, old=query_name: self._refresh_query_source(old, saved_name))
        layout.addWidget(editor)
        self._show_builder_dialog(dlg)

    def _open_manual_sql_builder(self, query_name: str, obj: QueryObject):
        from suiteview.audit.tabs.manual_sql_object_editor import ManualSqlObjectEditor

        dlg = QDialog(self)
        dlg.setWindowTitle(f"Query Builder - {query_name}")
        dlg.resize(1180, 720)
        layout = QVBoxLayout(dlg)
        layout.setContentsMargins(4, 4, 4, 4)
        editor = ManualSqlObjectEditor(dlg)
        editor.load_object(obj)
        connections = self._manual_sql_connections()
        editor.set_connection_options(connections, obj.dsn)
        editor.preview_requested.connect(lambda sql, ed=editor: self._preview_manual_sql_builder(ed, sql))
        editor.save_requested.connect(lambda payload, ed=editor, old=query_name: self._save_manual_sql_builder(ed, payload, old))
        layout.addWidget(editor)
        self._show_builder_dialog(dlg)

    def _show_builder_dialog(self, dlg: QDialog):
        dlg.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        dlg.finished.connect(lambda _=0, d=dlg: self._builder_windows.remove(d) if d in self._builder_windows else None)
        self._builder_windows.append(dlg)
        dlg.show()

    def _manual_sql_connections(self) -> list[tuple[str, str]]:
        parent = self.window()
        provider = getattr(parent, "_manual_sql_odbc_connections", None)
        if callable(provider):
            return provider()
        source_dsns = sorted({source.dsn for source in self._sources.values() if source.dsn}, key=str.lower)
        return [(dsn, dsn) for dsn in source_dsns]

    def _preview_manual_sql_builder(self, editor, sql: str):
        dsn = editor.current_connection()
        if not dsn:
            QMessageBox.information(editor, "Connection Required", "Select an ODBC connection before running SQL.")
            return
        editor.set_running(True)
        try:
            columns, rows = execute_odbc_query(dsn, sql)
            import pandas as pd
            editor.set_preview_results(pd.DataFrame([list(row) for row in rows], columns=columns), dsn=dsn)
        except Exception as exc:
            logger.exception("Manual SQL builder preview failed")
            QMessageBox.warning(editor, "Query Error", str(exc))
        finally:
            editor.set_running(False)

    def _save_manual_sql_builder(self, editor, payload: dict, old_query_name: str):
        old_obj = query_object_store.load_object(payload.get("original_name", "") or old_query_name)
        old_name = payload.get("original_name", "")
        new_name = payload["name"]
        if new_name != old_name and query_object_store.object_exists(new_name):
            QMessageBox.warning(editor, "Name Already Exists", f"A Query Object named \"{new_name}\" already exists.")
            return
        obj = manual_sql_query_object(
            new_name,
            sql=payload["sql"],
            dsn=payload["dsn"],
            result_columns=payload["result_columns"],
            column_types=payload["column_types"],
        )
        obj.description = payload.get("description", "")
        obj.tags = payload.get("tags", [])
        obj.config = dict(getattr(old_obj, "config", {}) or {})
        obj.config["sql_assist"] = payload.get("sql_assist", {})
        obj.source_design = getattr(old_obj, "source_design", "") or obj.source_design
        existing_fields = payload.get("existing_fields") or []
        if existing_fields:
            for field in existing_fields:
                if field.source == old_name:
                    field.source = new_name
            obj.fields = existing_fields
        query_object_store.save_object(obj)
        if old_name and old_name != new_name:
            query_object_store.delete_object(old_name)
        editor.load_object(obj)
        self._refresh_query_source(old_query_name, obj.name)
        QMessageBox.information(editor, "Query Object Saved", f"Saved \"{obj.name}\".")

    def _refresh_query_source(self, query_name: str, saved_name: str = ""):
        source_name = saved_name or query_name
        obj = query_object_store.load_object(source_name)
        if obj is None:
            qd = qdef_store.load_qdef(source_name, forge_name=self._current_forge_name) or qdef_store.load_qdef(source_name)
        else:
            qd = qdefinition_from_query_object(obj)
        if qd is None:
            QMessageBox.warning(self, "Refresh Failed", f"Could not find query object \"{source_name}\".")
            return
        qd.forge_name = self._current_forge_name
        if query_name != qd.name:
            self._sources.pop(query_name, None)
        self._sources[qd.name] = qd
        qdef_store.save_qdef(qd)
        if obj is not None:
            query_object_store.save_object(obj)
        self._rebuild_query_list(select_name=qd.name)
        self._update_query_object_button()
        if self._current_query == query_name or self._current_query == qd.name:
            self._current_query = qd.name
            self._populate_fields(qd.name)
        self.source_refreshed.emit(query_name, qd)

    def _modify_query_object(self, query_name: str):
        from suiteview.audit.query_object_viewer_window import QueryObjectViewerWindow
        win = QueryObjectViewerWindow.show_instance(parent=self.window())
        selector = getattr(win, "select_object", None)
        if selector is not None:
            selector(query_name)

    def _rename_qdef(self, old_name: str):
        from PyQt6.QtWidgets import QInputDialog, QMessageBox
        new_name, ok = QInputDialog.getText(
            self, "Rename QDefinition", "New name:", text=old_name)
        if not ok or not new_name.strip() or new_name.strip() == old_name:
            return
        new_name = new_name.strip()

        forge = self._current_forge_name
        if qdef_store.qdef_exists(new_name, forge_name=forge):
            QMessageBox.warning(
                self, "Name Exists",
                f"A query object named '{new_name}' already exists.")
            return

        qd = qdef_store.load_qdef(old_name, forge_name=forge)
        if not qd:
            return

        qd.name = new_name
        qdef_store.save_qdef(qd)
        old_snap = qdef_store.snapshot_path(old_name, forge_name=forge)
        if old_snap.exists():
            old_snap.rename(qdef_store.snapshot_path(new_name, forge_name=forge))
        qdef_store.delete_qdef(old_name, forge_name=forge)

        if old_name in self._sources:
            self._sources[new_name] = self._sources.pop(old_name)
            self._sources[new_name].name = new_name

        self._rebuild_query_list(select_name=new_name)
        self._update_query_object_button()
        self.sources_changed.emit(list(self._sources.keys()))

    def _preview_query_data(self, query_name: str):
        sq = self._sources.get(query_name)
        if not sq:
            return
        QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
        try:
            df = self._load_preview_dataframe(sq)
        except Exception as exc:
            QApplication.restoreOverrideCursor()
            logger.exception("Forge Assist preview failed: %s", query_name)
            QMessageBox.warning(
                self,
                "Preview Failed",
                f"Could not preview \"{query_name}\":\n\n{exc}",
            )
            return
        QApplication.restoreOverrideCursor()
        from suiteview.audit.dataforge._query_preview_window import QueryPreviewWindow
        win = QueryPreviewWindow(query_name, df, parent=None)
        win.show()
        if not hasattr(self, "_preview_windows"):
            self._preview_windows = []
        self._preview_windows.append(win)

    @staticmethod
    def _is_adhoc_source(source: QDefinition) -> bool:
        return _is_file_source_qdefinition(source)

    def _load_preview_dataframe(self, source: QDefinition):
        if self._is_adhoc_source(source):
            metadata = getattr(source, "query_object_source_metadata", {}) or {}
            return dataframe_from_adhoc_metadata(
                source.source_design,
                metadata,
                columns=source.result_columns,
            )
        if not source.sql or not source.dsn:
            raise ValueError("This query does not have saved SQL and DSN information to preview.")
        columns, rows = execute_odbc_query(source.dsn, source.sql)
        import pandas as pd
        return pd.DataFrame([list(row) for row in rows], columns=columns)