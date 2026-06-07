"""
QueryObject Viewer Window — unified browser for saved query objects.

Shows visual query designs, QDefinitions, Cyberlife-produced objects, manual SQL,
and ad hoc sources from the QueryObject store in one place.
"""
from __future__ import annotations

import json
import logging
import re
from datetime import datetime

import pandas as pd

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor, QFont
from PyQt6.QtWidgets import (
    QAbstractItemView,
    QDialog,
    QFileDialog,
    QGridLayout,
    QHeaderView,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QMenu,
    QApplication,
    QSizePolicy,
    QSplitter,
    QTableWidget,
    QTableWidgetItem,
    QTabWidget,
    QTextEdit,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from suiteview.audit.adhoc_source_intake import (
    promote_adhoc_source,
    query_adhoc_object,
    query_object_from_file,
)
from suiteview.audit.query_object import (
    OBJECT_KIND_ADHOC_SOURCE,
    OBJECT_KIND_CYBERLIFE,
    OBJECT_KIND_EXECUTABLE,
    OBJECT_KIND_MANUAL_SQL,
    OBJECT_KIND_VISUAL,
    QueryObject,
    object_from_qdefinition,
)
from suiteview.audit.qdefinition import QDefinition
from suiteview.audit.query_runner import execute_odbc_query
from suiteview.audit import query_object_store
from suiteview.core.odbc_utils import ACCESS, DB2, SQL_SERVER, UNKNOWN, detect_dialect
from suiteview.ui.widgets.filter_table_view import FilterTableView
from suiteview.ui.widgets.frameless_window import FramelessWindowBase

logger = logging.getLogger(__name__)

_FONT = QFont("Segoe UI", 9)
_FONT_BOLD = QFont("Segoe UI", 9, QFont.Weight.Bold)
_FONT_MONO = QFont("Consolas", 9)
_FONT_SMALL = QFont("Segoe UI", 8)

_HEADER_COLORS = ("#1E5BA8", "#0D3A7A", "#082B5C")
_BORDER_COLOR = "#D4A017"

_BTN_STYLE = (
    "QPushButton { background-color: #1E5BA8; color: white;"
    " border: 1px solid #14407A; border-radius: 3px;"
    " padding: 3px 10px; font-size: 8pt; }"
    "QPushButton:hover { background-color: #2A6BC4; }"
)

_BTN_DANGER_STYLE = (
    "QPushButton { background-color: #C00000; color: white;"
    " border: 1px solid #900; border-radius: 3px;"
    " padding: 3px 10px; font-size: 8pt; }"
    "QPushButton:hover { background-color: #E00000; }"
)

_DATAFORGE_NODE_PREFIX = "__dataforge_forge__:"


def _dataforge_node_value(forge_name: str) -> str:
    return f"{_DATAFORGE_NODE_PREFIX}{forge_name}"


def _dataforge_node_name(value) -> str:
    if isinstance(value, str) and value.startswith(_DATAFORGE_NODE_PREFIX):
        return value[len(_DATAFORGE_NODE_PREFIX):]
    return ""


def _kind_label(kind: str) -> str:
    labels = {
        "visual_query": "Visual Queries",
        "executable_query": "Executable Queries",
        "cyberlife_query": "Cyberlife Objects",
        "manual_sql": "Manual SQL Objects",
        "adhoc_source": "File Sources",
    }
    return labels.get(kind, kind.replace("_", " ").title())


def _object_group_label(obj: QueryObject) -> str:
    if obj.kind == OBJECT_KIND_ADHOC_SOURCE:
        return "File Sources"
    return _kind_label(obj.kind)


def _dataforge_info(obj: QueryObject) -> tuple[str, str] | None:
    dataforge = (obj.config or {}).get("dataforge", {})
    forge_name = str(dataforge.get("forge_name", "")).strip()
    source_name = str(dataforge.get("source_name", "")).strip()
    if forge_name:
        return forge_name, source_name or obj.name

    match = re.match(r"^(?P<source>.+) \[(?P<forge>[^\]]+)\]$", obj.name)
    if match:
        return match.group("forge"), match.group("source")

    return None


def _dataforge_display_name(forge_name: str) -> str:
    name = forge_name.strip()
    return "(new)" if name.lower() == "dataforge" else name or "(new)"


def _file_source_type_label(source_type: str, metadata: dict | None = None) -> str:
    metadata = metadata or {}
    path = str(metadata.get("path", "")).strip()
    if path:
        filename = path.rsplit("/", 1)[-1].rsplit("\\", 1)[-1]
        if "." in filename:
            suffix = filename.rsplit(".", 1)[-1].strip().lower()
            if suffix:
                return f".{suffix}"
    source_type = source_type.strip().lower()
    fallback = {
        "csv": ".csv",
        "excel": "Excel",
        "fixed_width": "Fixed Width",
    }
    return fallback.get(source_type, "Flat File")


def _display_dsn_for_object(obj: QueryObject) -> str:
    if obj.kind == OBJECT_KIND_ADHOC_SOURCE:
        source = obj.sources[0] if obj.sources else None
        return _file_source_type_label(
            source.source_type if source is not None else obj.source_design,
            source.metadata if source is not None else (obj.config or {}).get("source_metadata", {}),
        )
    return obj.dsn.strip()


def _display_dsn_for_definition(definition: dict) -> str:
    kind = str(definition.get("kind", "")).strip()
    query_object_kind = str(definition.get("query_object_kind", "")).strip()
    source_design = str(definition.get("source_design", "")).strip().lower()
    metadata = (
        definition.get("query_object_source_metadata")
        or definition.get("source_metadata")
        or (definition.get("config", {}) or {}).get("source_metadata")
        or {}
    )
    if kind == OBJECT_KIND_ADHOC_SOURCE or query_object_kind == OBJECT_KIND_ADHOC_SOURCE:
        return _file_source_type_label(source_design, metadata)
    if source_design in {"csv", "excel", "fixed_width"} and metadata:
        return _file_source_type_label(source_design, metadata)
    return str(definition.get("dsn", "")).strip()


def _object_group_order(label: str) -> tuple[int, str]:
    order = {
        "Cyberlife Objects": 10,
        "File Sources": 20,
        "Manual SQL Objects": 30,
        "Visual Queries": 40,
        "Executable Queries": 50,
    }
    return order.get(label, 90), label.lower()


def _preview_dialect_for_object(obj: QueryObject) -> str:
    detected = detect_dialect(obj.dsn.strip()) if obj.dsn.strip() else UNKNOWN
    if detected != UNKNOWN:
        return detected
    return obj.dialect.strip().upper() or UNKNOWN


def _limited_preview_sql(sql: str, limit: int, dialect: str) -> str:
    sql = sql.strip().rstrip(";")
    if limit <= 0:
        return sql
    if dialect == DB2:
        if re.search(r"\bFETCH\s+FIRST\s+\d+\s+ROWS\s+ONLY\b", sql, re.IGNORECASE):
            return sql
        trailing_clause = re.search(r"\s+(WITH\s+UR(?:\s+OPTIMIZE\s+FOR\s+\d+\s+ROWS)?|OPTIMIZE\s+FOR\s+\d+\s+ROWS)\s*$", sql, re.IGNORECASE)
        if trailing_clause:
            return f"{sql[:trailing_clause.start()]} FETCH FIRST {limit} ROWS ONLY{sql[trailing_clause.start():]}"
        return f"{sql} FETCH FIRST {limit} ROWS ONLY"
    if dialect in {SQL_SERVER, ACCESS, UNKNOWN}:
        return f"SELECT TOP {limit} * FROM (\n{sql}\n) AS QOBJ_PREVIEW"
    return f"SELECT TOP {limit} * FROM (\n{sql}\n) AS QOBJ_PREVIEW"


class QueryObjectViewerWindow(FramelessWindowBase):
    """Non-blocking QueryObject browser and inspector."""

    _instance = None

    def __init__(self, parent=None):
        self._current: QueryObject | None = None
        self._current_forge_name = ""
        self._loading_detail = False
        self._audit_parent = parent
        self._dataforge_builder_windows: list[QDialog] = []
        self._audit_builder_windows: list[QWidget] = []
        super().__init__(
            title="Query Object Browser",
            default_size=(1120, 620),
            min_size=(760, 420),
            parent=None,
            header_colors=_HEADER_COLORS,
            border_color=_BORDER_COLOR,
        )

    @classmethod
    def show_instance(cls, parent=None):
        if cls._instance is None or not cls._instance.isVisible():
            cls._instance = cls(parent)
            cls._instance.show()
        else:
            if parent is not None:
                cls._instance._audit_parent = parent
            cls._instance.refresh()
            cls._instance.raise_()
            cls._instance.activateWindow()
        return cls._instance

    def build_content(self) -> QWidget:
        body = QWidget()
        body.setStyleSheet("QWidget { background-color: #F0F0F0; }")
        root = QVBoxLayout(body)
        root.setContentsMargins(4, 2, 4, 4)
        root.setSpacing(4)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.setChildrenCollapsible(False)
        splitter.setHandleWidth(4)

        left = QWidget()
        left.setMinimumWidth(220)
        left.setMaximumWidth(520)
        left.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Expanding)
        left_lay = QVBoxLayout(left)
        left_lay.setContentsMargins(0, 0, 0, 0)
        left_lay.setSpacing(4)

        lbl_left = QLabel("Query Objects")
        lbl_left.setFont(_FONT_BOLD)
        lbl_left.setStyleSheet("color: #1E5BA8;")
        left_lay.addWidget(lbl_left)

        self.tree = QTreeWidget()
        self.tree.setHeaderHidden(True)
        self.tree.setMinimumWidth(210)
        self.tree.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.tree.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.tree.setFont(_FONT)
        self.tree.setStyleSheet(
            "QTreeWidget { border: 1px solid #1E5BA8; background: white; }"
            "QTreeWidget::item { padding: 1px 4px; }"
            "QTreeWidget::item:selected { background-color: #A0C4E8; color: black; }"
        )
        self.tree.currentItemChanged.connect(self._on_tree_selection)
        self.tree.itemDoubleClicked.connect(self._on_tree_double_clicked)
        self.tree.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.tree.customContextMenuRequested.connect(self._show_tree_context_menu)
        left_lay.addWidget(self.tree, 1)

        splitter.addWidget(left)

        right = QWidget()
        right_lay = QVBoxLayout(right)
        right_lay.setContentsMargins(0, 0, 0, 0)
        right_lay.setSpacing(4)

        info = QWidget()
        info_lay = QHBoxLayout(info)
        info_lay.setContentsMargins(0, 0, 0, 0)
        info_lay.setSpacing(10)

        self.lbl_name = QLabel("Select a QueryObject")
        self.lbl_name.setFont(QFont("Segoe UI", 14, QFont.Weight.Bold))
        self.lbl_name.setStyleSheet("color: #1E5BA8;")
        self.lbl_name.setFixedWidth(430)
        self.lbl_name.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        info_lay.addWidget(self.lbl_name)

        self.lbl_kind = QLabel("")
        self.lbl_kind.setFont(_FONT)
        self.lbl_kind.setStyleSheet("color: #666;")
        self.lbl_kind.setVisible(False)
        info_lay.addWidget(self.lbl_kind)

        self.lbl_status = QLabel("")
        self.lbl_status.setFont(_FONT)
        self.lbl_status.setStyleSheet("color: #666;")
        self.lbl_status.setVisible(False)
        info_lay.addWidget(self.lbl_status)
        info_lay.addStretch()

        self.btn_open_builder = QPushButton("Open in Builder")
        self.btn_open_builder.setFont(_FONT_BOLD)
        self.btn_open_builder.setFixedSize(116, 26)
        self.btn_open_builder.setStyleSheet(_BTN_STYLE)
        self.btn_open_builder.setToolTip("Open this object in its designer when available")
        self.btn_open_builder.clicked.connect(self._on_open_builder)
        info_lay.addWidget(self.btn_open_builder)

        self.btn_preview_file = QPushButton("Preview File")
        self.btn_preview_file.setFont(_FONT_BOLD)
        self.btn_preview_file.setText("Preview Data")
        self.btn_preview_file.setFixedSize(98, 26)
        self.btn_preview_file.setStyleSheet(_BTN_STYLE)
        self.btn_preview_file.clicked.connect(self._on_preview_file)
        info_lay.addWidget(self.btn_preview_file)

        self.btn_promote = QPushButton("Register Source")
        self.btn_promote.setFont(_FONT_BOLD)
        self.btn_promote.setFixedSize(112, 26)
        self.btn_promote.setStyleSheet(_BTN_STYLE)
        self.btn_promote.setToolTip("Mark a file source object as a registered, reusable source")
        self.btn_promote.clicked.connect(self._on_promote)
        info_lay.addWidget(self.btn_promote)

        self.btn_delete = QPushButton("Delete")
        self.btn_delete.setFont(_FONT_BOLD)
        self.btn_delete.setFixedSize(80, 26)
        self.btn_delete.setStyleSheet(_BTN_DANGER_STYLE)
        self.btn_delete.clicked.connect(self._on_delete)
        info_lay.addWidget(self.btn_delete)

        right_lay.addWidget(info)

        editor = QWidget()
        editor.setStyleSheet(
            "QWidget { background: #FAFBFD; border: 1px solid #C9D8EA; }"
            "QLabel { border: none; background: transparent; color: #444; }"
            "QLineEdit { background: white; border: 1px solid #A0C4E8; padding: 2px 4px; }"
        )
        editor_lay = QGridLayout(editor)
        editor_lay.setContentsMargins(6, 5, 6, 5)
        editor_lay.setHorizontalSpacing(6)
        editor_lay.setVerticalSpacing(4)

        self.edit_name = self._make_line_edit(0)
        self.edit_origin = self._make_line_edit(0)
        self.edit_origin.setToolTip("Builder/source that created this object, such as Query Studio, Cyberlife, Manual SQL, or csv")
        self.edit_tags = self._make_line_edit(0)
        self.edit_tags.setToolTip("Optional comma-separated labels for grouping and finding objects later")
        self.edit_description = self._make_line_edit(0)

        self._add_editor_field(editor_lay, 0, 0, "Object", self.edit_name)
        self._add_editor_field(editor_lay, 0, 2, "Builder", self.edit_origin)
        self._add_editor_field(editor_lay, 1, 0, "Description", self.edit_description)
        self._add_editor_field(editor_lay, 1, 2, "Tags", self.edit_tags)

        self.btn_save = QPushButton("Save")
        self.btn_save.setFont(_FONT_BOLD)
        self.btn_save.setFixedSize(72, 24)
        self.btn_save.setStyleSheet(_BTN_STYLE)
        self.btn_save.clicked.connect(self._on_save_changes)
        editor_lay.addWidget(self.btn_save, 0, 4, 2, 1, Qt.AlignmentFlag.AlignTop)
        editor_lay.setColumnStretch(1, 3)
        editor_lay.setColumnStretch(3, 2)
        editor_lay.setRowStretch(0, 0)
        editor_lay.setRowStretch(1, 0)
        editor_lay.setRowStretch(2, 1)

        self.tabs = QTabWidget()
        self.tabs.setFont(_FONT)
        self.tabs.setStyleSheet(
            "QTabWidget::pane { border: 2px solid #1E5BA8; background: white; }"
            "QTabBar::tab { padding: 4px 14px; font-size: 9pt;"
            " border: 1px solid #A0C4E8; border-bottom: none; margin-right: 1px; }"
            "QTabBar::tab:selected { background: white; color: #1E5BA8;"
            " font-weight: bold; }"
            "QTabBar::tab:!selected { background: #E8F0FB; color: #444; }"
        )

        self.tabs.addTab(editor, "Object")

        self.tbl_sources = self._make_table(["Name", "Type", "DSN", "Status"])
        self.tabs.addTab(self.tbl_sources, "Sources")

        self.tbl_outputs = self._make_table(["Field", "Type", "Display Name", "Source"])
        self.tabs.addTab(self.tbl_outputs, "Outputs")

        self.tbl_inputs = self._make_table(["Field", "Type", "Display Name", "Source"])
        self.tabs.addTab(self.tbl_inputs, "Inputs")

        self.tbl_joins = self._make_table(["Field", "Type", "Display Name", "Source"])
        self.tabs.addTab(self.tbl_joins, "Joins")

        self.tbl_fields = self._make_table(["Field", "Type", "Role", "Display Name", "Source"])
        self.tbl_fields.setEditTriggers(
            QAbstractItemView.EditTrigger.DoubleClicked
            | QAbstractItemView.EditTrigger.EditKeyPressed
            | QAbstractItemView.EditTrigger.SelectedClicked
        )
        self.tabs.addTab(self.tbl_fields, "All Fields")

        self.txt_sql = QTextEdit()
        self.txt_sql.setFont(_FONT_MONO)
        self.txt_sql.setReadOnly(False)
        self.txt_sql.setStyleSheet("QTextEdit { background: white; border: none; }")
        self.tabs.addTab(self.txt_sql, "SQL")

        self.txt_config = QTextEdit()
        self.txt_config.setFont(_FONT_MONO)
        self.txt_config.setReadOnly(True)
        self.txt_config.setStyleSheet("QTextEdit { background: white; border: none; }")
        self.tabs.addTab(self.txt_config, "Config")

        right_lay.addWidget(self.tabs, 1)
        splitter.addWidget(right)
        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)
        splitter.setSizes([280, 840])

        root.addWidget(splitter, 1)

        self.refresh()
        return body

    @staticmethod
    def _make_line_edit(width: int) -> QLineEdit:
        edit = QLineEdit()
        edit.setFont(_FONT)
        edit.setFixedHeight(24)
        if width:
            edit.setFixedWidth(width)
        edit.setStyleSheet(
            "QLineEdit { background: white; border: 1px solid #A0C4E8;"
            " padding: 2px 4px; }"
        )
        return edit

    @staticmethod
    def _add_editor_field(layout: QGridLayout, row: int, col: int, label: str, widget: QLineEdit):
        lbl = QLabel(label)
        lbl.setFont(_FONT_SMALL)
        layout.addWidget(lbl, row, col)
        layout.addWidget(widget, row, col + 1)

    @staticmethod
    def _make_table(headers: list[str]) -> QTableWidget:
        table = QTableWidget()
        table.setColumnCount(len(headers))
        table.setHorizontalHeaderLabels(headers)
        table.horizontalHeader().setStretchLastSection(True)
        table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        table.verticalHeader().setVisible(False)
        table.verticalHeader().setDefaultSectionSize(18)
        table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        table.setFont(_FONT)
        table.setStyleSheet(
            "QTableWidget { border: none; background: white; gridline-color: #E0E0E0; }"
            "QHeaderView::section { background: #E8F0FB; font-weight: bold;"
            " font-size: 8pt; border: 1px solid #C0C0C0; padding: 1px 4px; }"
        )
        return table

    @staticmethod
    def _set_table_headers(table: QTableWidget, headers: list[str]) -> None:
        table.clear()
        table.setColumnCount(len(headers))
        table.setHorizontalHeaderLabels(headers)
        table.setRowCount(0)

    @staticmethod
    def _set_table_rows(table: QTableWidget, rows: list[list[object]]) -> None:
        table.setRowCount(len(rows))
        for row_index, values in enumerate(rows):
            for col_index, value in enumerate(values):
                table.setItem(row_index, col_index, QTableWidgetItem(str(value)))
        table.resizeColumnsToContents()

    def _configure_object_tables(self) -> None:
        self._set_table_headers(self.tbl_sources, ["Name", "Type", "DSN", "Status"])
        self._set_table_headers(self.tbl_outputs, ["Field", "Type", "Display Name", "Source"])
        self._set_table_headers(self.tbl_inputs, ["Field", "Type", "Display Name", "Source"])
        self._set_table_headers(self.tbl_joins, ["Field", "Type", "Display Name", "Source"])
        self._set_table_headers(self.tbl_fields, ["Field", "Type", "Role", "Display Name", "Source"])

    def _configure_forge_tables(self) -> None:
        self._set_table_headers(self.tbl_sources, ["Source", "Query Copy", "Kind", "DSN", "Columns", "Snapshot", "Rows"])
        self._set_table_headers(self.tbl_outputs, ["Field", "Display Name", "Source", "Type"])
        self._set_table_headers(self.tbl_inputs, ["Filter Tab", "Field", "Mode", "Value"])
        self._set_table_headers(self.tbl_joins, ["Left Source", "Left Field(s)", "Right Source", "Right Field(s)", "Type"])
        self._set_table_headers(self.tbl_fields, ["Field", "Type", "Role", "Source"])

    def refresh(self):
        """Reload the object tree from disk."""
        current_name = None
        current = self.tree.currentItem()
        if current is not None:
            current_name = current.data(0, Qt.ItemDataRole.UserRole)
        self.tree.clear()
        self._ensure_dataforge_query_objects()
        objects = query_object_store.list_objects()
        groups: dict[str, list[QueryObject]] = {}
        dataforge_groups: dict[str, list[QueryObject]] = {}
        for obj in objects:
            dataforge_info = _dataforge_info(obj)
            if dataforge_info is not None:
                forge_name, _ = dataforge_info
                dataforge_groups.setdefault(forge_name, []).append(obj)
                continue
            groups.setdefault(_object_group_label(obj), []).append(obj)

        fallback_item = None
        selected_item = None

        def _add_object_child(parent_item: QTreeWidgetItem, obj: QueryObject,
                              label: str | None = None):
            nonlocal fallback_item, selected_item
            child = QTreeWidgetItem([label or obj.name])
            child.setFont(0, _FONT)
            child.setData(0, Qt.ItemDataRole.UserRole, obj.name)
            parent_item.addChild(child)
            if fallback_item is None:
                fallback_item = child
            if current_name == obj.name:
                selected_item = child

        for group_label in sorted(groups, key=_object_group_order):
            parent = QTreeWidgetItem([group_label])
            parent.setFont(0, _FONT_BOLD)
            parent.setForeground(0, QColor("#1E5BA8"))
            parent.setData(0, Qt.ItemDataRole.UserRole, None)
            self.tree.addTopLevelItem(parent)
            for obj in groups[group_label]:
                _add_object_child(parent, obj)
            parent.setExpanded(True)

        if dataforge_groups:
            dataforge_parent = QTreeWidgetItem(["DataForge"])
            dataforge_parent.setFont(0, _FONT_BOLD)
            dataforge_parent.setForeground(0, QColor("#C2410C"))
            dataforge_parent.setData(0, Qt.ItemDataRole.UserRole, None)
            self.tree.addTopLevelItem(dataforge_parent)
            for forge_name in sorted(dataforge_groups, key=str.lower):
                forge_node = QTreeWidgetItem([_dataforge_display_name(forge_name)])
                forge_node.setFont(0, _FONT_BOLD)
                forge_node.setForeground(0, QColor("#C2410C"))
                forge_node.setData(0, Qt.ItemDataRole.UserRole, _dataforge_node_value(forge_name))
                dataforge_parent.addChild(forge_node)
                for obj in sorted(dataforge_groups[forge_name], key=lambda item: item.name.lower()):
                    _, source_label = _dataforge_info(obj) or (forge_name, obj.name)
                    _add_object_child(forge_node, obj, source_label)
                forge_node.setExpanded(True)
            dataforge_parent.setExpanded(True)

        item_to_select = selected_item or fallback_item
        if item_to_select is not None:
            self.tree.setCurrentItem(item_to_select)
        else:
            self._clear_detail()

    def _ensure_dataforge_query_objects(self) -> None:
        """Publish missing browser QueryObjects from saved DataForge definitions."""
        from suiteview.audit.dataforge import dataforge_store

        for forge in dataforge_store.list_forges():
            for source in forge.sources:
                definition = source.definition or {}
                copy_name = str(definition.get("name", "")).strip() or source.query_name
                if not copy_name:
                    continue
                source_label = self._definition_source_label(definition, source.query_name)
                existing = query_object_store.load_object(copy_name)
                if existing is not None and _dataforge_info(existing) is not None:
                    continue
                try:
                    if "kind" in definition:
                        obj = QueryObject.from_dict(definition)
                    else:
                        qd = QDefinition.from_dict(definition)
                        qd.forge_name = forge.name
                        obj = object_from_qdefinition(qd)
                except Exception:
                    logger.exception("Failed to repair DataForge QueryObject: %s", copy_name)
                    continue
                obj.name = copy_name
                obj.config = dict(obj.config or {})
                obj.config["dataforge"] = {
                    "forge_name": forge.name,
                    "source_name": source_label,
                }
                obj.source_design = obj.source_design or source_label
                query_object_store.save_object(obj)

    def select_object(self, name: str):
        """Refresh and select a Query Object by name if it exists."""
        self.refresh()
        def _select_under(item: QTreeWidgetItem) -> bool:
            if item.data(0, Qt.ItemDataRole.UserRole) == name:
                self.tree.setCurrentItem(item)
                return True
            for index in range(item.childCount()):
                if _select_under(item.child(index)):
                    return True
            return False

        for i in range(self.tree.topLevelItemCount()):
            if _select_under(self.tree.topLevelItem(i)):
                return

    def _select_object(self, name: str):
        self.select_object(name)

    def _on_tree_selection(self, current, previous):
        if current is None:
            self._clear_detail()
            return
        name = current.data(0, Qt.ItemDataRole.UserRole)
        forge_name = _dataforge_node_name(name)
        if forge_name:
            self._show_forge_detail(forge_name)
            return
        if not name:
            self._clear_detail()
            return
        obj = query_object_store.load_object(name)
        if obj is None:
            self._clear_detail()
            return
        self._show_detail(obj)

    def _on_tree_double_clicked(self, item, column):
        name = item.data(0, Qt.ItemDataRole.UserRole)
        forge_name = _dataforge_node_name(name)
        if forge_name:
            self._open_dataforge_builder(forge_name)
            return
        if self._current is not None and self._can_open_in_builder(self._current):
            self._on_open_builder()

    def _show_tree_context_menu(self, pos):
        item = self.tree.itemAt(pos)
        if item is None:
            return
        name = item.data(0, Qt.ItemDataRole.UserRole)
        forge_name = _dataforge_node_name(name)
        if forge_name:
            self.tree.setCurrentItem(item)
            menu = QMenu(self)
            open_forge = menu.addAction("Open DataForge in Builder")
            delete_forge = menu.addAction("Delete DataForge")
            chosen = menu.exec(self.tree.viewport().mapToGlobal(pos))
            if chosen == open_forge:
                self._open_dataforge_builder(forge_name)
            elif chosen == delete_forge:
                self._delete_dataforge(forge_name)
            return
        if not name:
            return
        obj = query_object_store.load_object(name)
        if obj is None:
            return
        self.tree.setCurrentItem(item)

        menu = QMenu(self)
        open_builder = menu.addAction("Open in Builder")
        open_builder.setEnabled(self._can_open_in_builder(obj))
        preview = menu.addAction("Preview Data")
        preview.setEnabled(self._can_preview_object(obj))
        copy_object = menu.addAction("Make Copy...")
        register_source = None
        if obj.kind == OBJECT_KIND_ADHOC_SOURCE:
            register_source = menu.addAction("Register Source")
        menu.addSeparator()
        delete = menu.addAction("Delete")

        chosen = menu.exec(self.tree.viewport().mapToGlobal(pos))
        if chosen is None:
            return
        if chosen == open_builder:
            self._on_open_builder()
        elif chosen == preview:
            self._on_preview_file()
        elif chosen == copy_object:
            self._on_make_copy(obj.name)
        elif register_source is not None and chosen == register_source:
            self._on_promote()
        elif chosen == delete:
            self._on_delete()

    def _clear_detail(self):
        self._current = None
        self._current_forge_name = ""
        self._configure_object_tables()
        self.lbl_name.setText("Select a QueryObject")
        self.lbl_kind.setText("")
        self.lbl_status.setText("")
        self.edit_name.clear()
        self.edit_origin.clear()
        self.edit_tags.clear()
        self.edit_description.clear()
        self.tbl_sources.setRowCount(0)
        self.tbl_outputs.setRowCount(0)
        self.tbl_inputs.setRowCount(0)
        self.tbl_joins.setRowCount(0)
        self.tbl_fields.setRowCount(0)
        self.txt_sql.clear()
        self.txt_config.clear()
        self.btn_open_builder.setEnabled(False)
        self.btn_preview_file.setEnabled(False)
        self.btn_promote.setEnabled(False)
        self.btn_promote.setVisible(False)
        self.btn_delete.setEnabled(False)
        self.btn_save.setEnabled(False)

    def _show_detail(self, obj: QueryObject):
        self._loading_detail = True
        self._current = obj
        self._current_forge_name = ""
        self._configure_object_tables()
        self.lbl_name.setText(obj.name)
        self.lbl_kind.setText(_kind_label(obj.kind))
        self.lbl_status.setText(f"Status: {obj.metadata_status}    DSN: {_display_dsn_for_object(obj) or '-'}")
        self.btn_delete.setEnabled(True)
        self.btn_save.setEnabled(True)
        self.btn_open_builder.setEnabled(self._can_open_in_builder(obj))
        self.btn_preview_file.setEnabled(self._can_preview_object(obj))
        self.btn_promote.setEnabled(obj.kind == OBJECT_KIND_ADHOC_SOURCE)
        self.btn_promote.setVisible(obj.kind == OBJECT_KIND_ADHOC_SOURCE)
        self.edit_name.setText(obj.name)
        self.edit_origin.setText("File Source" if obj.kind == OBJECT_KIND_ADHOC_SOURCE else obj.source_design or obj.kind)
        self.edit_tags.setText(", ".join(obj.tags))
        self.edit_description.setText(obj.description)

        self.tbl_sources.setRowCount(len(obj.sources))
        for row, source in enumerate(obj.sources):
            dsn = _file_source_type_label(source.source_type, source.metadata) if obj.kind == OBJECT_KIND_ADHOC_SOURCE else source.dsn
            values = [source.name, source.source_type, dsn, source.status]
            for col, value in enumerate(values):
                self.tbl_sources.setItem(row, col, QTableWidgetItem(str(value)))
        self.tbl_sources.resizeColumnsToContents()
        self.tbl_sources.setColumnWidth(0, max(self.tbl_sources.columnWidth(0), 240))
        self.tbl_sources.setColumnWidth(1, max(self.tbl_sources.columnWidth(1), 80))

        self._populate_role_table(self.tbl_outputs, obj, {"output"})
        self._populate_role_table(self.tbl_inputs, obj, {"input"})
        self._populate_role_table(self.tbl_joins, obj, {"join_key"})

        self.tbl_fields.setRowCount(len(obj.fields))
        for row, field in enumerate(obj.fields):
            values = [field.name, field.data_type, field.role, field.display_name, field.source]
            for col, value in enumerate(values):
                item = QTableWidgetItem(str(value))
                if col == 0:
                    item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
                self.tbl_fields.setItem(row, col, item)
        self.tbl_fields.resizeColumnsToContents()
        self.tbl_fields.setColumnWidth(0, max(self.tbl_fields.columnWidth(0), 180))
        self.tbl_fields.setColumnWidth(1, max(self.tbl_fields.columnWidth(1), 110))

        self.txt_sql.setPlainText(obj.sql or "")
        self.txt_config.setPlainText(json.dumps({
            "config": obj.config,
            "manual_layers": obj.manual_layers,
            "source_design": obj.source_design,
            "created_at": obj.created_at.isoformat(),
            "updated_at": obj.updated_at.isoformat(),
        }, indent=2))
        self._loading_detail = False

    def _show_forge_detail(self, forge_name: str):
        from suiteview.audit.dataforge import dataforge_store

        self._loading_detail = True
        self._current = None
        self._current_forge_name = forge_name
        self._configure_forge_tables()

        forge = dataforge_store.load_forge(forge_name)
        forge_objects = self._query_objects_for_forge(forge_name)
        display_name = _dataforge_display_name(forge_name)

        self.lbl_name.setText(f"Forge: {display_name}")
        self.lbl_kind.setText("DataForge")
        saved_text = "Saved" if forge is not None else "Query copies only"
        source_count = len(forge.sources) if forge is not None else len(forge_objects)
        self.lbl_status.setText(f"Status: {saved_text}    Sources: {source_count}")
        self.btn_delete.setEnabled(True)
        self.btn_save.setEnabled(False)
        self.btn_open_builder.setEnabled(forge is not None)
        self.btn_preview_file.setEnabled(False)
        self.btn_promote.setEnabled(False)
        self.btn_promote.setVisible(False)
        self.edit_name.setText(display_name)
        self.edit_origin.setText("DataForge")
        self.edit_tags.clear()
        self.edit_description.setText(
            "Saved DataForge definition and its forge-local query copies." if forge is not None
            else "Forge-local query copies without a saved DataForge definition.")

        source_rows = self._forge_source_rows(forge, forge_objects)
        self._set_table_rows(self.tbl_sources, source_rows)
        self.tbl_sources.setColumnWidth(0, max(self.tbl_sources.columnWidth(0), 180))
        self.tbl_sources.setColumnWidth(1, max(self.tbl_sources.columnWidth(1), 220))

        output_rows, all_field_rows = self._forge_field_rows(forge, forge_objects)
        self._set_table_rows(self.tbl_outputs, output_rows)
        self._set_table_rows(self.tbl_fields, all_field_rows)
        self._set_table_rows(self.tbl_inputs, self._forge_filter_rows(forge))
        self._set_table_rows(self.tbl_joins, self._forge_join_rows(forge))
        self.txt_sql.setPlainText(self._forge_sql_text(forge, forge_objects))
        self.txt_config.setPlainText(json.dumps(
            forge.to_dict() if forge is not None else {
                "name": forge_name,
                "query_objects": [obj.to_dict() for obj in forge_objects],
            },
            indent=2,
        ))
        self._loading_detail = False

    @staticmethod
    def _definition_source_label(definition: dict, fallback: str) -> str:
        config = definition.get("config", {}) if isinstance(definition, dict) else {}
        dataforge = config.get("dataforge", {}) if isinstance(config, dict) else {}
        return str(dataforge.get("source_name", "")).strip() or fallback

    def _query_objects_for_forge(self, forge_name: str) -> list[QueryObject]:
        objects = []
        for obj in query_object_store.list_objects():
            info = _dataforge_info(obj)
            if info is not None and info[0] == forge_name:
                objects.append(obj)
        return sorted(objects, key=lambda item: item.name.lower())

    def _forge_source_rows(self, forge, forge_objects: list[QueryObject]) -> list[list[object]]:
        rows: list[list[object]] = []
        seen = set()
        objects_by_name = {obj.name: obj for obj in forge_objects}
        if forge is not None:
            for source in forge.sources:
                definition = source.definition or {}
                copy_name = str(definition.get("name", "")).strip() or source.query_name
                source_label = self._definition_source_label(definition, source.query_name)
                fields = definition.get("fields") or []
                result_columns = definition.get("result_columns") or []
                column_count = len(fields) or len(result_columns)
                snapshot = "Stale" if source.snapshot.stale else source.snapshot.created_at or "Not refreshed"
                dsn_label = _display_dsn_for_definition(definition)
                source_object = objects_by_name.get(copy_name) or objects_by_name.get(source.query_name)
                if source_object is not None and not dsn_label:
                    dsn_label = _display_dsn_for_object(source_object)
                rows.append([
                    source_label,
                    copy_name,
                    _kind_label(str(definition.get("kind", "executable_query"))),
                    dsn_label,
                    column_count,
                    snapshot,
                    source.snapshot.row_count or "",
                ])
                seen.add(copy_name)
        for obj in forge_objects:
            if obj.name in seen:
                continue
            info = _dataforge_info(obj)
            rows.append([
                info[1] if info else obj.name,
                obj.name,
                _kind_label(obj.kind),
                _display_dsn_for_object(obj),
                len(obj.fields),
                "",
                "",
            ])
        return rows

    def _forge_field_rows(self, forge, forge_objects: list[QueryObject]) -> tuple[list[list[object]], list[list[object]]]:
        display_state = (forge.config or {}).get("display_tab", {}) if forge is not None else {}
        selected = set(display_state.get("selected", []))
        display_all = display_state.get("display_all", True)
        output_rows: list[list[object]] = []
        all_rows: list[list[object]] = []

        def add_field(field_name: str, data_type: str, role: str, source: str, display_name: str = ""):
            all_rows.append([field_name, data_type, role, source])
            if display_all or not selected or field_name in selected or f"{source}.{field_name}" in selected:
                if role in {"", "output"}:
                    output_rows.append([field_name, display_name or field_name, source, data_type])

        for obj in forge_objects:
            info = _dataforge_info(obj)
            source_label = info[1] if info else obj.name
            for field in obj.fields:
                add_field(field.name, field.data_type, field.role, source_label, field.display_name)

        if forge is not None and not all_rows:
            for source in forge.sources:
                definition = source.definition or {}
                source_label = self._definition_source_label(definition, source.query_name)
                column_types = definition.get("column_types", {}) or {}
                for field_name in definition.get("result_columns", []) or []:
                    add_field(field_name, column_types.get(field_name, ""), "output", source_label)
        return output_rows, all_rows

    @staticmethod
    def _forge_filter_rows(forge) -> list[list[object]]:
        if forge is None:
            return []
        rows: list[list[object]] = []
        modes = ["contains", "regex", "combo", "list", "range"]
        for tab in (forge.config or {}).get("filter_tabs", []) or []:
            tab_name = tab.get("tab_name", "Filter")
            fields = (tab.get("grid", {}) or {}).get("fields", {}) or {}
            for field_key, state in fields.items():
                mode_idx = int(state.get("mode", 0) or 0)
                mode = modes[mode_idx] if 0 <= mode_idx < len(modes) else str(mode_idx)
                if mode == "range":
                    value = f"{state.get('val', '')} to {state.get('hi', '')}".strip()
                elif mode == "list":
                    value = ", ".join(str(v) for v in state.get("list_selected", []))
                else:
                    value = state.get("val", "")
                rows.append([tab_name, field_key, mode, value])
        return rows

    @staticmethod
    def _forge_join_rows(forge) -> list[list[object]]:
        if forge is None:
            return []
        joins_state = (forge.config or {}).get("joins_tab", {}) or {}
        joins = joins_state.get("joins", []) or []
        rows: list[list[object]] = []
        for join in joins:
            keys = join.get("keys", []) or []
            left_fields = [key.get("left_field", "") for key in keys]
            right_fields = [key.get("right_field", "") for key in keys]
            rows.append([
                join.get("left_source", ""),
                ", ".join(left_fields),
                join.get("right_source", ""),
                ", ".join(right_fields),
                join.get("how", "inner"),
            ])
        for join in (forge.config or {}).get("joins", []) or []:
            rows.append([
                join.get("left_source", ""),
                ", ".join(join.get("left_keys", [])),
                join.get("right_source", ""),
                ", ".join(join.get("right_keys", [])),
                join.get("how", "inner"),
            ])
        return rows

    @staticmethod
    def _forge_sql_text(forge, forge_objects: list[QueryObject]) -> str:
        chunks: list[str] = []
        if forge is not None:
            for source in forge.sources:
                definition = source.definition or {}
                sql = str(definition.get("sql", "")).strip()
                if sql:
                    label = definition.get("name", source.query_name)
                    chunks.append(f"-- Source: {label}\n{sql}")
        for obj in forge_objects:
            if obj.sql.strip() and all(f"-- Source: {obj.name}\n" not in chunk for chunk in chunks):
                chunks.append(f"-- Source: {obj.name}\n{obj.sql.strip()}")
        return "\n\n".join(chunks)

    def _populate_role_table(self, table: QTableWidget, obj: QueryObject, roles: set[str]):
        fields = [field for field in obj.fields if field.role in roles]
        table.setRowCount(len(fields))
        for row, field in enumerate(fields):
            values = [field.name, field.data_type, field.display_name, field.source]
            for col, value in enumerate(values):
                table.setItem(row, col, QTableWidgetItem(str(value)))
        table.resizeColumnsToContents()
        table.setColumnWidth(0, max(table.columnWidth(0), 180))
        table.setColumnWidth(1, max(table.columnWidth(1), 110))

    def _on_save_changes(self):
        if self._current is None or self._loading_detail:
            return
        old_name = self._current.name
        new_name = self.edit_name.text().strip()
        if not new_name:
            QMessageBox.warning(self, "Name Required", "Object name cannot be blank.")
            return
        if new_name != old_name and query_object_store.object_exists(new_name):
            QMessageBox.warning(
                self,
                "Name Already Exists",
                f"A Query Object named \"{new_name}\" already exists.",
            )
            return

        updated_fields = []
        for row, field in enumerate(self._current.fields):
            role = self._normalize_role(self._table_text(self.tbl_fields, row, 2))
            if not role:
                QMessageBox.warning(
                    self,
                    "Invalid Field Role",
                    f"Role for \"{field.name}\" must be output, input, or join key.",
                )
                return
            field.data_type = self._table_text(self.tbl_fields, row, 1)
            field.role = role
            field.display_name = self._table_text(self.tbl_fields, row, 3) or field.name
            field.source = self._table_text(self.tbl_fields, row, 4)
            updated_fields.append(field)

        self._current.name = new_name
        self._current.description = self.edit_description.text().strip()
        self._current.tags = [tag.strip() for tag in self.edit_tags.text().split(",") if tag.strip()]
        self._current.source_design = self.edit_origin.text().strip()
        self._current.sql = self.txt_sql.toPlainText().strip()
        self._current.fields = updated_fields
        self._current.updated_at = datetime.now()

        query_object_store.save_object(self._current)
        if new_name != old_name:
            query_object_store.delete_object(old_name)
        self.refresh()
        QMessageBox.information(self, "Query Object Saved", f"Saved \"{new_name}\".")

    def _on_open_builder(self):
        if self._current_forge_name:
            self._open_dataforge_builder(self._current_forge_name)
            return
        if self._current is None:
            return
        parent = self._audit_window_for_builder()
        opener = getattr(parent, "open_query_object_in_builder", None)
        if opener is None:
            QMessageBox.information(
                self,
                "Builder Unavailable",
                "Could not open the Audit builder for this Query Object.",
            )
            return
        opener(self._current.name)

    def _open_dataforge_builder(self, forge_name: str):
        parent = self._audit_window_for_builder()
        opener = getattr(parent, "open_dataforge_in_builder", None)
        if opener is None:
            QMessageBox.information(
                self,
                "Builder Unavailable",
                "Could not open the Audit DataForge builder.",
            )
            return
        opener(forge_name)

    def _audit_window_for_builder(self):
        for candidate in (self._audit_parent, self.parent(), self._find_audit_window()):
            if not self._is_audit_window(candidate):
                continue
            if self._show_audit_window(candidate):
                return candidate
        try:
            from suiteview.audit.main import create_audit_window
            window = create_audit_window()
        except Exception:
            logger.exception("Failed to create AuditWindow for QueryObject builder")
            return None
        self._audit_parent = window
        self._audit_builder_windows.append(window)
        window.destroyed.connect(lambda _=None, win=window: self._forget_audit_window(win))
        return window

    @staticmethod
    def _is_audit_window(candidate) -> bool:
        if candidate is None:
            return False
        try:
            return (
                hasattr(candidate, "open_query_object_in_builder")
                or hasattr(candidate, "open_dataforge_in_builder")
            )
        except RuntimeError:
            return False

    def _show_audit_window(self, window) -> bool:
        try:
            if not window.isVisible():
                window.show()
            if window.isMinimized():
                window.showNormal()
            window.raise_()
            window.activateWindow()
            return True
        except RuntimeError:
            if self._audit_parent is window:
                self._audit_parent = None
            return False

    def _forget_audit_window(self, window):
        if window in self._audit_builder_windows:
            self._audit_builder_windows.remove(window)
        if self._audit_parent is window:
            self._audit_parent = None

    @staticmethod
    def _find_audit_window():
        app = QApplication.instance()
        if app is None:
            return None
        for widget in app.topLevelWidgets():
            if hasattr(widget, "open_query_object_in_builder"):
                return widget
        return None

    @staticmethod
    def _table_text(table: QTableWidget, row: int, col: int) -> str:
        item = table.item(row, col)
        return item.text().strip() if item is not None else ""

    @staticmethod
    def _normalize_role(value: str) -> str:
        normalized = value.strip().lower().replace(" ", "_").replace("-", "_")
        aliases = {
            "": "output",
            "output": "output",
            "select": "output",
            "input": "input",
            "where": "input",
            "filter": "input",
            "join": "join_key",
            "join_key": "join_key",
            "joinkey": "join_key",
            "key": "join_key",
        }
        return aliases.get(normalized, "")

    def _on_make_copy(self, source_name: str | None = None):
        if source_name is None:
            if self._current is None:
                return
            source_name = self._current.name
        default_name = self._default_copy_name(source_name)
        new_name, ok = QInputDialog.getText(
            self,
            "Copy Query Object",
            "New object name:",
            text=default_name,
        )
        if not ok or not new_name.strip():
            return
        try:
            copied = query_object_store.copy_object(source_name, new_name.strip())
        except Exception as exc:
            QMessageBox.warning(self, "Copy Failed", str(exc))
            return
        self.refresh()
        self._select_object(copied.name)
        QMessageBox.information(
            self,
            "Query Object Copied",
            f"Created \"{copied.name}\" from \"{source_name}\".",
        )

    @staticmethod
    def _default_copy_name(source_name: str) -> str:
        base = f"{source_name} Copy"
        if not query_object_store.object_exists(base):
            return base
        suffix = 2
        while query_object_store.object_exists(f"{base} {suffix}"):
            suffix += 1
        return f"{base} {suffix}"

    def _on_delete(self):
        if self._current_forge_name:
            self._delete_dataforge(self._current_forge_name)
            return
        if self._current is None:
            return
        name = self._current.name
        reply = QMessageBox.question(
            self,
            "Delete Query Object",
            f"Delete query object \"{name}\"?\n\nThis does not delete the original SavedQuery or QDefinition.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return
        query_object_store.delete_object(name)
        self.refresh()
        self._clear_detail()

    def _delete_dataforge(self, forge_name: str):
        from suiteview.audit import qdef_store
        from suiteview.audit.dataforge import dataforge_store

        display_name = _dataforge_display_name(forge_name)
        forge_objects = self._query_objects_for_forge(forge_name)
        reply = QMessageBox.question(
            self,
            "Delete DataForge",
            f"Delete DataForge \"{display_name}\"?\n\n"
            "This deletes the saved forge, snapshots, and its DataForge query copies. "
            "Original query objects remain.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return
        self._delete_dataforge_records(forge_name, forge_objects)
        parent = self._audit_parent or self.parent() or self._find_audit_window()
        handler = getattr(parent, "_on_forge_deleted_from_group", None)
        if callable(handler):
            handler(forge_name)
        refresher = getattr(parent, "_refresh_picker_forge_list", None)
        if callable(refresher):
            refresher()
        self.refresh()
        self._clear_detail()

    @staticmethod
    def _delete_dataforge_records(forge_name: str, forge_objects: list[QueryObject]) -> None:
        from suiteview.audit import qdef_store
        from suiteview.audit.dataforge import dataforge_store

        dataforge_store.delete_forge(forge_name)
        for obj in forge_objects:
            try:
                qdef_store.delete_qdef(obj.name, forge_name=forge_name)
            except Exception:
                logger.exception("Failed to delete DataForge QDefinition: %s", obj.name)
            query_object_store.delete_object(obj.name)

    def _on_promote(self):
        if self._current is None:
            return
        name = self._current.name
        try:
            promote_adhoc_source(self._current)
            query_object_store.save_object(self._current)
        except Exception as exc:
            logger.exception("Ad hoc source promotion failed: %s", name)
            QMessageBox.warning(
                self,
                "Promotion Failed",
                f"Could not promote this object:\n\n{exc}",
            )
            return
        self.refresh()
        QMessageBox.information(
            self,
            "Object Promoted",
            f"Promoted \"{name}\" to registered metadata.",
        )

    def _on_preview_file(self):
        if self._current is None:
            return
        dlg = FileObjectPreviewDialog(self._current, self)
        dlg.exec()

    @staticmethod
    def _can_open_in_builder(obj: QueryObject) -> bool:
        if (obj.config or {}).get("dataforge") and obj.kind == OBJECT_KIND_EXECUTABLE:
            return True
        return obj.kind in {
            OBJECT_KIND_VISUAL,
            OBJECT_KIND_CYBERLIFE,
            OBJECT_KIND_MANUAL_SQL,
            OBJECT_KIND_ADHOC_SOURCE,
        }

    @staticmethod
    def _can_preview_object(obj: QueryObject) -> bool:
        if obj.kind == OBJECT_KIND_ADHOC_SOURCE:
            return True
        return bool(obj.sql.strip() and obj.dsn.strip())

    def _on_import_file(self):
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Import Ad Hoc Source",
            "",
            "Data Files (*.csv *.xlsx *.xlsm *.xls);;CSV Files (*.csv);;Excel Files (*.xlsx *.xlsm *.xls)",
        )
        if not path:
            return
        default_name = path.rsplit("/", 1)[-1].rsplit("\\", 1)[-1].rsplit(".", 1)[0]
        name, ok = QInputDialog.getText(
            self,
            "Ad Hoc Source Name",
            "Name:",
            text=default_name,
        )
        if not ok or not name.strip():
            return
        try:
            obj = query_object_from_file(path, name=name.strip())
            query_object_store.save_object(obj)
        except Exception as exc:
            logger.exception("Ad hoc source import failed: %s", path)
            QMessageBox.warning(
                self,
                "Import Failed",
                f"Could not import ad hoc source:\n\n{exc}",
            )
            return
        self.refresh()
        QMessageBox.information(
            self,
            "Source Imported",
            f"Imported \"{obj.name}\" with {len(obj.fields)} fields.",
        )


class FileObjectPreviewDialog(QDialog):
    """Small query surface for QueryObjects."""

    def __init__(self, query_object: QueryObject, parent=None):
        super().__init__(parent)
        self._query_object = query_object
        self.setWindowTitle(f"Preview Data - {query_object.name}")
        self.resize(880, 520)
        self._build_ui()
        self._run_preview()

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(6, 6, 6, 6)
        root.setSpacing(6)

        top = QHBoxLayout()
        top.setContentsMargins(0, 0, 0, 0)
        top.setSpacing(6)

        self.edit_columns = QLineEdit(
            ", ".join(field.name for field in self._query_object.fields)
        )
        self.edit_columns.setFont(_FONT)
        self.edit_columns.setPlaceholderText("Columns")
        top.addWidget(QLabel("Columns"))
        top.addWidget(self.edit_columns, 2)

        self.edit_filter = QLineEdit()
        self.edit_filter.setFont(_FONT)
        self.edit_filter.setPlaceholderText("Filter")
        top.addWidget(QLabel("Filter"))
        top.addWidget(self.edit_filter, 2)

        self.edit_limit = QLineEdit("500")
        self.edit_limit.setFont(_FONT)
        self.edit_limit.setFixedWidth(60)
        top.addWidget(QLabel("Rows"))
        top.addWidget(self.edit_limit)

        self.btn_run = QPushButton("Run")
        self.btn_run.setFont(_FONT_BOLD)
        self.btn_run.setFixedSize(70, 26)
        self.btn_run.setStyleSheet(_BTN_STYLE)
        self.btn_run.clicked.connect(self._run_preview)
        top.addWidget(self.btn_run)
        root.addLayout(top)

        self.table = FilterTableView(self)
        root.addWidget(self.table, 1)

        self.lbl_status = QLabel("")
        self.lbl_status.setFont(_FONT_SMALL)
        self.lbl_status.setStyleSheet("color: #555;")
        root.addWidget(self.lbl_status)

    def _run_preview(self):
        columns = [
            column.strip()
            for column in self.edit_columns.text().split(",")
            if column.strip()
        ]
        try:
            limit = int(self.edit_limit.text().strip() or "500")
        except ValueError:
            QMessageBox.warning(self, "Invalid Rows", "Rows must be a number.")
            return
        try:
            if self._query_object.kind == OBJECT_KIND_ADHOC_SOURCE:
                df = query_adhoc_object(
                    self._query_object,
                    columns=columns,
                    filter_expr=self.edit_filter.text(),
                    limit=limit,
                )
            else:
                df = self._query_sql_object(columns=columns, filter_expr=self.edit_filter.text(), limit=limit)
        except Exception as exc:
            QMessageBox.warning(self, "Preview Failed", str(exc))
            return
        self.table.set_dataframe(df, limit_rows=False)
        self.lbl_status.setText(f"{len(df)} rows x {len(df.columns)} columns")

    def _query_sql_object(self, *, columns: list[str], filter_expr: str, limit: int) -> pd.DataFrame:
        sql = self._query_object.sql.strip().rstrip(";")
        dsn = self._query_object.dsn.strip()
        if not sql or not dsn:
            raise ValueError("This object does not have saved SQL and DSN information to preview.")
        preview_sql = _limited_preview_sql(sql, limit, _preview_dialect_for_object(self._query_object))
        result_columns, rows = execute_odbc_query(dsn, preview_sql)
        df = pd.DataFrame([list(row) for row in rows], columns=result_columns)
        if columns:
            available = [column for column in columns if column in df.columns]
            if available:
                df = df[available]
        if filter_expr.strip():
            df = df.query(filter_expr.strip(), engine="python")
        return df