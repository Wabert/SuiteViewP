"""
QueryObject Viewer Window — unified browser for saved query objects.

Shows visual query designs, QDefinitions, Cyberlife-produced objects, manual SQL,
and ad hoc sources from the QueryObject store in one place.
"""
from __future__ import annotations

import json
import logging
from datetime import datetime

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor, QFont
from PyQt6.QtWidgets import (
    QAbstractItemView,
    QDialog,
    QFileDialog,
    QHeaderView,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
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
from suiteview.audit.query_object import OBJECT_KIND_ADHOC_SOURCE, QueryObject
from suiteview.audit import query_object_store
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
        "adhoc_source": "Ad Hoc Sources",
    }
    return labels.get(kind, kind.replace("_", " ").title())


class QueryObjectViewerWindow(FramelessWindowBase):
    """Non-blocking QueryObject browser and inspector."""

    _instance = None

    def __init__(self, parent=None):
        self._current: QueryObject | None = None
        self._loading_detail = False
        super().__init__(
            title="Query Object Browser",
            default_size=(1120, 620),
            min_size=(760, 420),
            parent=parent,
            header_colors=_HEADER_COLORS,
            border_color=_BORDER_COLOR,
        )

    @classmethod
    def show_instance(cls, parent=None):
        if cls._instance is None or not cls._instance.isVisible():
            cls._instance = cls(parent)
            cls._instance.show()
        else:
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

        left = QWidget()
        left_lay = QVBoxLayout(left)
        left_lay.setContentsMargins(0, 0, 0, 0)
        left_lay.setSpacing(4)

        lbl_left = QLabel("Query Objects")
        lbl_left.setFont(_FONT_BOLD)
        lbl_left.setStyleSheet("color: #1E5BA8;")
        left_lay.addWidget(lbl_left)

        self.tree = QTreeWidget()
        self.tree.setHeaderHidden(True)
        self.tree.setFont(_FONT)
        self.tree.setStyleSheet(
            "QTreeWidget { border: 1px solid #1E5BA8; background: white; }"
            "QTreeWidget::item { padding: 1px 4px; }"
            "QTreeWidget::item:selected { background-color: #A0C4E8; color: black; }"
        )
        self.tree.currentItemChanged.connect(self._on_tree_selection)
        left_lay.addWidget(self.tree, 1)

        btn_row = QHBoxLayout()
        btn_row.setContentsMargins(0, 0, 0, 0)
        btn_row.setSpacing(4)

        btn_import = QPushButton("Import File")
        btn_import.setFont(_FONT_SMALL)
        btn_import.setFixedHeight(24)
        btn_import.setStyleSheet(_BTN_STYLE)
        btn_import.clicked.connect(self._on_import_file)
        btn_row.addWidget(btn_import)

        btn_refresh = QPushButton("Refresh")
        btn_refresh.setFont(_FONT_SMALL)
        btn_refresh.setFixedHeight(24)
        btn_refresh.setStyleSheet(_BTN_STYLE)
        btn_refresh.clicked.connect(self.refresh)
        btn_row.addWidget(btn_refresh)
        left_lay.addLayout(btn_row)

        splitter.addWidget(left)

        right = QWidget()
        right_lay = QVBoxLayout(right)
        right_lay.setContentsMargins(0, 0, 0, 0)
        right_lay.setSpacing(4)

        info = QWidget()
        info_lay = QHBoxLayout(info)
        info_lay.setContentsMargins(0, 0, 0, 0)
        info_lay.setSpacing(16)

        self.lbl_name = QLabel("Select a QueryObject")
        self.lbl_name.setFont(QFont("Segoe UI", 14, QFont.Weight.Bold))
        self.lbl_name.setStyleSheet("color: #1E5BA8;")
        info_lay.addWidget(self.lbl_name)

        self.lbl_kind = QLabel("")
        self.lbl_kind.setFont(_FONT)
        self.lbl_kind.setStyleSheet("color: #666;")
        info_lay.addWidget(self.lbl_kind)

        self.lbl_status = QLabel("")
        self.lbl_status.setFont(_FONT)
        self.lbl_status.setStyleSheet("color: #666;")
        info_lay.addWidget(self.lbl_status)
        info_lay.addStretch()

        self.btn_preview_file = QPushButton("Preview File")
        self.btn_preview_file.setFont(_FONT_BOLD)
        self.btn_preview_file.setFixedSize(92, 26)
        self.btn_preview_file.setStyleSheet(_BTN_STYLE)
        self.btn_preview_file.clicked.connect(self._on_preview_file)
        info_lay.addWidget(self.btn_preview_file)

        self.btn_promote = QPushButton("Promote")
        self.btn_promote.setFont(_FONT_BOLD)
        self.btn_promote.setFixedSize(82, 26)
        self.btn_promote.setStyleSheet(_BTN_STYLE)
        self.btn_promote.setToolTip("Mark a CSV/Excel ad hoc object as registered")
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
        editor_lay = QHBoxLayout(editor)
        editor_lay.setContentsMargins(0, 0, 0, 0)
        editor_lay.setSpacing(6)

        self.edit_name = self._make_line_edit(180)
        self.edit_design = self._make_line_edit(130)
        self.edit_dsn = self._make_line_edit(120)
        self.edit_status = self._make_line_edit(110)
        self.edit_tags = self._make_line_edit(180)

        for label, widget in (
            ("Name", self.edit_name),
            ("Design", self.edit_design),
            ("DSN", self.edit_dsn),
            ("Status", self.edit_status),
            ("Tags", self.edit_tags),
        ):
            lbl = QLabel(label)
            lbl.setFont(_FONT_SMALL)
            lbl.setStyleSheet("color: #444;")
            editor_lay.addWidget(lbl)
            editor_lay.addWidget(widget)

        self.btn_save = QPushButton("Save Changes")
        self.btn_save.setFont(_FONT_BOLD)
        self.btn_save.setFixedSize(110, 26)
        self.btn_save.setStyleSheet(_BTN_STYLE)
        self.btn_save.clicked.connect(self._on_save_changes)
        editor_lay.addWidget(self.btn_save)
        right_lay.addWidget(editor)

        self.edit_description = self._make_line_edit(0)
        self.edit_description.setPlaceholderText("Description")
        right_lay.addWidget(self.edit_description)

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
        splitter.setSizes([280, 840])

        root.addWidget(splitter, 1)

        self.refresh()
        self._clear_detail()
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
            groups.setdefault(obj.kind, []).append(obj)

        fallback_item = None
        selected_item = None

        for kind in sorted(groups, key=_kind_label):
            parent = QTreeWidgetItem([_kind_label(kind)])
            parent.setFont(0, _FONT_BOLD)
            parent.setForeground(0, QColor("#1E5BA8"))
            parent.setData(0, Qt.ItemDataRole.UserRole, None)
            self.tree.addTopLevelItem(parent)
            for obj in groups[kind]:
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

    def _clear_detail(self):
        self._current = None
        self.lbl_name.setText("Select a QueryObject")
        self.lbl_kind.setText("")
        self.lbl_status.setText("")
        self.edit_name.clear()
        self.edit_design.clear()
        self.edit_dsn.clear()
        self.edit_status.clear()
        self.edit_tags.clear()
        self.edit_description.clear()
        self.tbl_sources.setRowCount(0)
        self.tbl_outputs.setRowCount(0)
        self.tbl_inputs.setRowCount(0)
        self.tbl_joins.setRowCount(0)
        self.tbl_fields.setRowCount(0)
        self.txt_sql.clear()
        self.txt_config.clear()
        self.btn_preview_file.setEnabled(False)
        self.btn_promote.setEnabled(False)
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
        self.btn_preview_file.setEnabled(obj.kind == OBJECT_KIND_ADHOC_SOURCE)
        self.btn_promote.setEnabled(obj.kind == OBJECT_KIND_ADHOC_SOURCE)
        self.edit_name.setText(obj.name)
        self.edit_design.setText(obj.source_design)
        self.edit_dsn.setText(obj.dsn)
        self.edit_status.setText(obj.metadata_status)
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
        self._current.source_design = self.edit_design.text().strip()
        self._current.dsn = self.edit_dsn.text().strip()
        self._current.metadata_status = self.edit_status.text().strip() or self._current.metadata_status
        self._current.sql = self.txt_sql.toPlainText().strip()
        self._current.fields = updated_fields
        self._current.updated_at = datetime.now()

        query_object_store.save_object(self._current)
        if new_name != old_name:
            query_object_store.delete_object(old_name)
        self.refresh()
        QMessageBox.information(self, "Query Object Saved", f"Saved \"{new_name}\".")

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
    """Small query surface for CSV/Excel QueryObjects."""

    def __init__(self, query_object: QueryObject, parent=None):
        super().__init__(parent)
        self._query_object = query_object
        self.setWindowTitle(f"Preview File - {query_object.name}")
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
            df = query_adhoc_object(
                self._query_object,
                columns=columns,
                filter_expr=self.edit_filter.text(),
                limit=limit,
            )
        except Exception as exc:
            QMessageBox.warning(self, "File Query Failed", str(exc))
            return
        self.table.set_dataframe(df, limit_rows=False)
        self.lbl_status.setText(f"{len(df)} rows x {len(df.columns)} columns")