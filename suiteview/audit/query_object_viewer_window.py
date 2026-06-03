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
    OBJECT_KIND_MANUAL_SQL,
    OBJECT_KIND_VISUAL,
    QueryObject,
)
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
        self._loading_detail = False
        self._audit_parent = parent
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

    def refresh(self):
        """Reload the object tree from disk."""
        current_name = None
        current = self.tree.currentItem()
        if current is not None:
            current_name = current.data(0, Qt.ItemDataRole.UserRole)
        self.tree.clear()
        objects = query_object_store.list_objects()
        groups: dict[str, list[QueryObject]] = {}
        for obj in objects:
            groups.setdefault(_object_group_label(obj), []).append(obj)

        fallback_item = None
        selected_item = None

        for group_label in sorted(groups):
            parent = QTreeWidgetItem([group_label])
            parent.setFont(0, _FONT_BOLD)
            parent.setForeground(0, QColor("#1E5BA8"))
            parent.setData(0, Qt.ItemDataRole.UserRole, None)
            self.tree.addTopLevelItem(parent)
            for obj in groups[group_label]:
                child = QTreeWidgetItem([obj.name])
                child.setFont(0, _FONT)
                child.setData(0, Qt.ItemDataRole.UserRole, obj.name)
                parent.addChild(child)
                if fallback_item is None:
                    fallback_item = child
                if current_name == obj.name:
                    selected_item = child
            parent.setExpanded(True)

        item_to_select = selected_item or fallback_item
        if item_to_select is not None:
            self.tree.setCurrentItem(item_to_select)
        else:
            self._clear_detail()

    def _on_tree_selection(self, current, previous):
        if current is None:
            self._clear_detail()
            return
        name = current.data(0, Qt.ItemDataRole.UserRole)
        if not name:
            self._clear_detail()
            return
        obj = query_object_store.load_object(name)
        if obj is None:
            self._clear_detail()
            return
        self._show_detail(obj)

    def _show_tree_context_menu(self, pos):
        item = self.tree.itemAt(pos)
        if item is None:
            return
        name = item.data(0, Qt.ItemDataRole.UserRole)
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
        self.lbl_name.setText(obj.name)
        self.lbl_kind.setText(_kind_label(obj.kind))
        self.lbl_status.setText(f"Status: {obj.metadata_status}    DSN: {obj.dsn or '-'}")
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
            values = [source.name, source.source_type, source.dsn, source.status]
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
        if self._current is None:
            return
        parent = self._audit_parent or self.parent() or self._find_audit_window()
        opener = getattr(parent, "open_query_object_in_builder", None)
        if opener is None:
            QMessageBox.information(
                self,
                "Builder Unavailable",
                "Open the Query Object Browser from the Audit window to edit Query Objects.",
            )
            return
        opener(self._current.name)

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