"""
Manual SQL Object editor.

Dedicated Query Object creation shell for user-authored SQL. AuditWindow owns
database execution; this widget owns the object metadata, SQL text, preview
schema display, and save request.
"""
from __future__ import annotations

from dataclasses import replace

import pandas as pd
import time
from PyQt6.QtCore import QMimeData, Qt, pyqtSignal
from PyQt6.QtGui import QDrag, QFont
from PyQt6.QtWidgets import (
    QAbstractItemView,
    QGridLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMenu,
    QMessageBox,
    QPushButton,
    QInputDialog,
    QSplitter,
    QTabWidget,
    QTableWidget,
    QTableWidgetItem,
    QTextEdit,
    QVBoxLayout,
    QWidget,
    QWidgetAction,
)

from .build_sql_tab import _SqlHighlighter
from suiteview.audit.query_object import QueryObject
from suiteview.audit.ui.bottom_bar import AuditBottomBar, FOOTER_BG
from suiteview.ui.widgets.filter_table_view import FilterTableView
from suiteview.audit.field_picker_panel import FieldPickerPanel


_FONT = QFont("Segoe UI", 9)
_FONT_BOLD = QFont("Segoe UI", 9, QFont.Weight.Bold)
_FONT_MONO = QFont("Consolas", 10)
SQL_ASSIST_MIME = "application/x-manual-sql-assist"
SQL_KEYWORDS = [
    "SELECT", "FROM", "WHERE", "AND",
    "OR", "JOIN", "LEFT JOIN", "INNER JOIN",
    "ON", "GROUP BY", "ORDER BY", "HAVING",
    "AS", "IN", "FETCH FIRST", "WITH",
]

_SAVE_OBJECT_BTN_STYLE = (
    "QPushButton { background-color: #0A2A5C; color: #D4AF37;"
    " border: 2px solid #D4AF37; border-radius: 3px;"
    " padding: 1px 4px; font-size: 8pt; font-weight: bold; }"
    "QPushButton:hover { background-color: #123C69; color: #F4D03F; }"
    "QPushButton:disabled { background-color: #6B7A90; color: #E6D8A6;"
    " border-color: #C9B46B; }"
)

_ASSIST_BLUE = "#1E5BA8"
_ASSIST_BLUE_DARK = "#0A2A5C"
_ASSIST_BLUE_BG = "#EDF3FA"
_ASSIST_BLUE_LIGHT = "#D9E8F7"
_ASSIST_GOLD = "#D4AF37"

_ASSIST_HEADER_STYLE = (
    f"QLabel, QPushButton {{ color: white; font-size: 8pt; font-weight: bold;"
    f" padding: 2px 4px; background-color: {_ASSIST_BLUE};"
    f" border: 1px solid {_ASSIST_GOLD}; border-radius: 2px; text-align: left; }}"
    f"QPushButton:hover {{ background-color: #2A6BC4; }}"
)

_ASSIST_SEARCH_STYLE = (
    f"QLineEdit {{ border: 1px solid {_ASSIST_BLUE}; border-radius: 2px;"
    f" padding: 1px 4px; font-size: 8pt; }}"
    f"QLineEdit:focus {{ border: 1px solid {_ASSIST_GOLD}; }}"
)

_ASSIST_LIST_STYLE = (
    f"QListWidget {{ border: 1px solid {_ASSIST_BLUE}; background-color: white;"
    f" font-size: 9pt; outline: none; }}"
    f"QListWidget::item {{ padding: 0px 2px; border: none; }}"
    f"QListWidget::item:selected {{ background-color: {_ASSIST_BLUE_LIGHT}; color: {_ASSIST_BLUE_DARK}; border: none; }}"
    f"QListWidget::item:focus {{ outline: none; border: none; }}"
)


class SqlAssistList(QListWidget):
    """List that can drag SQL identifier text into the editor."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setDragEnabled(True)
        self.setDragDropMode(QAbstractItemView.DragDropMode.DragOnly)
        self.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)

    def startDrag(self, supportedActions):
        items = self.selectedItems()
        if not items:
            return
        values = [item.data(Qt.ItemDataRole.UserRole) or item.text() for item in items]
        drag = QDrag(self)
        mime = QMimeData()
        text = ", ".join(str(value) for value in values)
        mime.setText(text)
        mime.setData(SQL_ASSIST_MIME, text.encode("utf-8"))
        drag.setMimeData(mime)
        drag.exec(Qt.DropAction.CopyAction)


class SqlDropTextEdit(QTextEdit):
    """SQL editor that accepts table/field drops from the assist picker."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAcceptDrops(True)

    def dragEnterEvent(self, event):  # noqa: N802
        if event.mimeData().hasFormat(SQL_ASSIST_MIME) or event.mimeData().hasText():
            event.acceptProposedAction()
            return
        super().dragEnterEvent(event)

    def dragMoveEvent(self, event):  # noqa: N802
        if event.mimeData().hasFormat(SQL_ASSIST_MIME) or event.mimeData().hasText():
            event.acceptProposedAction()
            return
        super().dragMoveEvent(event)

    def dropEvent(self, event):  # noqa: N802
        if event.mimeData().hasFormat(SQL_ASSIST_MIME):
            text = bytes(event.mimeData().data(SQL_ASSIST_MIME)).decode("utf-8")
            self.textCursor().insertText(text)
            event.acceptProposedAction()
            return
        if event.mimeData().hasText():
            self.textCursor().insertText(event.mimeData().text())
            event.acceptProposedAction()
            return
        super().dropEvent(event)

    def contextMenuEvent(self, event):  # noqa: N802
        menu = QMenu(self)
        palette = QWidget(menu)
        grid = QGridLayout(palette)
        grid.setContentsMargins(6, 6, 6, 6)
        grid.setSpacing(4)
        for index, keyword in enumerate(SQL_KEYWORDS):
            button = QPushButton(keyword)
            button.setFont(_FONT)
            button.setFixedSize(92, 26)
            button.setStyleSheet(
                "QPushButton { background-color: #EDF3FA; color: #123C69;"
                " border: 1px solid #9FB4CC; border-radius: 2px; }"
                "QPushButton:hover { background-color: #D9E8F7; }"
            )
            button.clicked.connect(
                lambda checked=False, value=keyword: self._insert_keyword(menu, value)
            )
            grid.addWidget(button, index // 4, index % 4)
        action = QWidgetAction(menu)
        action.setDefaultWidget(palette)
        menu.addAction(action)
        menu.exec(event.globalPos())

    def _insert_keyword(self, menu: QMenu, keyword: str):
        cursor = self.textCursor()
        cursor.insertText(keyword)
        self.setTextCursor(cursor)
        menu.close()


class ManualSqlObjectEditor(QWidget):
    """Create a Manual SQL QueryObject from pasted SQL and preview schema."""

    preview_requested = pyqtSignal(str)
    save_requested = pyqtSignal(dict)
    load_assist_requested = pyqtSignal(str)
    load_fields_requested = pyqtSignal(str, str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._df: pd.DataFrame | None = None
        self._dsn = ""
        self._file_source_token = ""  # "file:<id>" when targeting a File Source
        self._original_name = ""
        self._result_columns: list[str] = []
        self._column_types: dict[str, str] = {}
        self._existing_fields = []
        self._assist_tables: list[str] = []
        self._assist_fields: dict[str, list[tuple[str, str]]] = {}
        self._current_assist_table = ""
        self._fields_sort_mode = "native"
        self._pinned_tables: list[str] = []
        self._common_table_names: list[str] = []
        self._build_ui()

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(4, 4, 4, 4)
        root.setSpacing(6)

        self.setStyleSheet(
            "QWidget { background-color: #F6F8FB; color: #111; }"
            "QGroupBox { border: 1px solid #AFC3DA; margin-top: 8px;"
            " padding: 8px 6px 6px 6px; font-weight: bold; }"
            "QGroupBox::title { subcontrol-origin: margin; left: 8px; padding: 0 4px; }"
            "QLineEdit, QTextEdit { background: white; border: 1px solid #9FB4CC;"
            " padding: 4px; }"
            "QTableWidget { background: white; border: 1px solid #9FB4CC; gridline-color: #E4E9F0; }"
            "QHeaderView::section { background: #E8EEF6; border: 1px solid #C6D4E4;"
            " padding: 3px 5px; font-weight: normal; }"
            "QTabWidget::pane { border: 1px solid #AFC3DA; background: white; }"
            "QTabBar::tab { padding: 4px 14px; min-height: 22px; }"
            "QTabBar::tab:selected { background: white; font-weight: bold; }"
        )

        header = QHBoxLayout()
        self.lbl_object_heading = QLabel("Manual SQL Object: (new)")
        self.lbl_object_heading.setFont(QFont("Segoe UI", 12, QFont.Weight.Bold))
        self.lbl_object_heading.setStyleSheet("color: #1E5BA8;")
        header.addWidget(self.lbl_object_heading)
        header.addStretch()
        self.lbl_status = QLabel("Preview SQL to capture output schema")
        self.lbl_status.setFont(_FONT)
        self.lbl_status.setStyleSheet("color: #4B5563;")
        header.addWidget(self.lbl_status)
        root.addLayout(header)

        # SQL Assist on the left, the SQL/Results/Schema canvas on the right —
        # mirrors the Visual Query builder so the two feel like one tool.
        self._main_splitter = QSplitter(Qt.Orientation.Horizontal)
        self._main_splitter.setHandleWidth(4)
        self.sql_assist = FieldPickerPanel()
        self.sql_assist.setMinimumWidth(240)
        self.sql_assist.setMaximumWidth(460)
        self._main_splitter.addWidget(self.sql_assist)

        self.editor_tabs = QTabWidget()
        self.editor_tabs.setFont(_FONT)
        self._main_splitter.addWidget(self.editor_tabs)
        self._main_splitter.setStretchFactor(0, 0)
        self._main_splitter.setStretchFactor(1, 1)
        self._main_splitter.setSizes([300, 820])
        root.addWidget(self._main_splitter, 1)

        self.bottom_bar = AuditBottomBar(bg_color=FOOTER_BG, run_label="Run")
        self.bottom_bar.btn_all.setVisible(False)
        self.bottom_bar.txt_max_count.setVisible(False)
        self.bottom_bar.lbl_max_count.setVisible(False)
        self.btn_new_query = QPushButton("New Query")
        self.btn_new_query.setFont(_FONT_BOLD)
        self.btn_new_query.setFixedSize(78, 36)
        self.btn_new_query.setStyleSheet(_SAVE_OBJECT_BTN_STYLE)
        self.btn_new_query.setToolTip("Start a new Manual SQL Query Object")
        self.btn_save = QPushButton("Save")
        self.btn_save.setFont(_FONT_BOLD)
        self.btn_save.setFixedSize(60, 36)
        self.btn_save.setEnabled(False)
        self.btn_save.setStyleSheet(_SAVE_OBJECT_BTN_STYLE)
        self.btn_save_as = QPushButton("Save As")
        self.btn_save_as.setFont(_FONT_BOLD)
        self.btn_save_as.setFixedSize(60, 36)
        self.btn_save_as.setEnabled(False)
        self.btn_save_as.setStyleSheet(_SAVE_OBJECT_BTN_STYLE)
        self.bottom_bar.action_layout.addWidget(self.btn_new_query)
        self.bottom_bar.action_layout.addWidget(self.btn_save_as)
        self.bottom_bar.action_layout.addWidget(self.btn_save)
        root.addWidget(self.bottom_bar)

        # Name/Description/Tags are no longer a tab — match the Visual Query,
        # which only asks for a name on Save As. Kept as hidden value-holders so
        # editing a saved object still round-trips its description and tags.
        self.txt_name = QLineEdit()
        self.txt_description = QLineEdit()
        self.txt_tags = QLineEdit()

        sql_page = QWidget()
        sql_layout = QVBoxLayout(sql_page)
        sql_layout.setContentsMargins(6, 6, 6, 6)
        sql_layout.setSpacing(6)
        self.txt_sql = SqlDropTextEdit()
        self.txt_sql.setFont(_FONT_MONO)
        self.txt_sql.setLineWrapMode(QTextEdit.LineWrapMode.NoWrap)
        self.txt_sql.setPlaceholderText("Paste DB2 SQL here")
        self._highlighter = _SqlHighlighter(self.txt_sql.document())
        sql_layout.addWidget(self.txt_sql, 1)
        self.editor_tabs.addTab(sql_page, "SQL")

        results_page = QWidget()
        results_layout = QVBoxLayout(results_page)
        results_layout.setContentsMargins(4, 4, 4, 4)
        self.results_table = FilterTableView(self)
        tv = self.results_table.table_view
        tv.verticalHeader().setVisible(False)
        tv.verticalHeader().setDefaultSectionSize(16)
        tv.verticalHeader().setMinimumSectionSize(14)
        tv.setShowGrid(False)
        tv.setAlternatingRowColors(False)
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
            QTableView#filterTableView::item:selected {
                background-color: #e0e8f0;
                color: black;
            }
            QTableView#filterTableView::item:hover {
                background-color: transparent;
            }
            QHeaderView::section {
                background-color: #e8e8e8;
                color: #000000;
                font-weight: normal;
                font-size: 8pt;
                padding: 1px 16px 1px 4px;
                border: 1px solid #c0c0c0;
            }
            QHeaderView::section:hover {
                background-color: #d8d8d8;
            }
        """)
        results_layout.addWidget(self.results_table, 1)
        self.editor_tabs.addTab(results_page, "Results")

        schema_page = QWidget()
        schema_layout = QVBoxLayout(schema_page)
        schema_layout.setContentsMargins(4, 4, 4, 4)
        self.schema_table = QTableWidget(0, 3)
        self.schema_table.setHorizontalHeaderLabels(["Column", "Type", "Role"])
        self.schema_table.verticalHeader().setVisible(False)
        self.schema_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.schema_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.schema_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.schema_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        self.schema_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        schema_layout.addWidget(self.schema_table)
        self.editor_tabs.addTab(schema_page, "Schema")

        self.bottom_bar.btn_run.clicked.connect(self._on_preview)
        self.btn_save.clicked.connect(self._on_save)
        self.btn_save_as.clicked.connect(self._on_save_as)
        self.btn_new_query.clicked.connect(self._confirm_new_object)
        self.sql_assist.table_requested.connect(self._insert_sql_text)
        self.sql_assist.field_requested.connect(self._on_assist_field_requested)
        self.sql_assist.tables_changed.connect(self._on_assist_tables_changed)
        self.sql_assist.pinned_tables_changed.connect(self._on_assist_pins_changed)
        self.sql_assist.common_table_requested.connect(self._on_common_table_requested)
        self.sql_assist.common_table_remove_requested.connect(self._on_common_table_remove_requested)
        self.txt_sql.textChanged.connect(self._on_sql_changed)

    def _confirm_new_object(self):
        reply = QMessageBox.question(
            self,
            "Start New Query?",
            "This will clear the current Manual SQL query. Continue?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if reply == QMessageBox.StandardButton.Yes:
            self.new_object()

    def set_file_source(self, fds):
        """Target a File Source: the SQL Assist lists its member tables + schema
        (no ODBC), and Run executes through DuckDB (the AuditWindow routes it)."""
        from suiteview.audit.file_source import datasource_label

        self._file_source_token = f"file:{fds.id}"
        label = f"{fds.name} [{datasource_label(fds)}]"
        table_fields = {
            member.resolved_table_name():
                [(col.name, col.data_type) for col in fds.columns]
            for member in fds.members
        }
        self.sql_assist.load_local_source(label, self._file_source_token, table_fields)
        self.lbl_status.setText(
            f"Querying file source “{fds.name}” via DuckDB — "
            "write SQL over its tables")

    def new_object(self):
        """Reset the editor for a new Manual SQL object."""
        self._file_source_token = ""
        self._original_name = ""
        self._pinned_tables = []
        self._common_table_names = []
        self.sql_assist.set_group(self.current_connection(), [], {})
        self.sql_assist.set_common_tables({})
        self._update_object_heading()
        self.txt_name.clear()
        self.txt_description.clear()
        self.txt_tags.clear()
        self._existing_fields = []
        self.set_sql("")
        self.bottom_bar.reset_timing()
        self.editor_tabs.setCurrentIndex(0)

    def load_object(self, obj: QueryObject):
        """Load an existing Manual SQL QueryObject for editing."""
        self._original_name = obj.name
        self._update_object_heading()
        self.txt_name.setText(obj.name)
        self.txt_description.setText(obj.description)
        self.txt_tags.setText(", ".join(obj.tags))
        self.txt_sql.blockSignals(True)
        self.txt_sql.setPlainText(obj.sql or "")
        self.txt_sql.blockSignals(False)
        self._df = None
        self._dsn = obj.dsn
        config = obj.config or {}
        assist_config = config.get("sql_assist", {})
        self._pinned_tables = list(
            assist_config.get("tables", assist_config.get("pinned_tables", []))
        )
        self._common_table_names = list(assist_config.get("common_tables", []))
        self._refresh_common_tables()
        self._existing_fields = [replace(field) for field in obj.fields]
        self._result_columns = [field.name for field in obj.fields]
        self._column_types = {field.name: field.data_type for field in obj.fields}
        self._populate_schema(self._result_columns, self._column_types)
        self.results_table.set_dataframe(pd.DataFrame(columns=self._result_columns), limit_rows=False)
        self._set_save_enabled(bool(self.current_sql()) and bool(self._result_columns))
        self.lbl_status.setText(f"Loaded {len(self._result_columns)} saved columns from {obj.dsn or '-'}")
        self.editor_tabs.setCurrentIndex(0)  # SQL

    def set_connection_options(self, connections: list, current: str = ""):
        """Set the ODBC connections available to the SQL Assist picker."""
        selected = current or self.current_connection()
        self.sql_assist.set_connection_options(connections, selected)
        self.sql_assist.set_group(
            self.sql_assist.current_connection(), list(self._pinned_tables), {},
            pinned_tables=self._pinned_tables,
        )
        self._refresh_common_tables()

    def current_connection(self) -> str:
        return self.sql_assist.current_connection()

    def current_connection_label(self) -> str:
        return self.sql_assist.current_connection_label()

    def _on_assist_field_requested(self, table: str, column: str,
                                   type_name: str, display: str):
        self._insert_sql_text(column)

    def _on_assist_pins_changed(self, tables: list[str]):
        self._pinned_tables = list(tables)

    def _on_assist_tables_changed(self, tables: list[str]):
        self._pinned_tables = list(tables)

    def _on_common_table_requested(self, table_name: str):
        if table_name not in self._common_table_names:
            self._common_table_names.append(table_name)
        self._refresh_common_tables()

    def _on_common_table_remove_requested(self, table_name: str):
        self._common_table_names = [t for t in self._common_table_names if t != table_name]
        self._refresh_common_tables()

    def _refresh_common_tables(self):
        from suiteview.audit import common_table_store

        common_cols: dict[str, list[tuple[str, str]]] = {}
        for name in self._common_table_names:
            ct = common_table_store.load_table(name)
            if ct:
                common_cols[ct.name] = [
                    (c["name"], c.get("type", "TEXT")) for c in ct.columns
                ]
        self.sql_assist.set_common_tables(common_cols)

    def set_assist_tables(self, tables: list[str], *, region: str = ""):
        """Populate the SQL Assist table list."""
        self._assist_tables = list(tables)
        self._assist_fields.clear()
        self._current_assist_table = ""
        self.list_tables.clear()
        self.list_fields.clear()
        for table in self._assist_tables:
            item = QListWidgetItem(table)
            item.setData(Qt.ItemDataRole.UserRole, table)
            self.list_tables.addItem(item)
        self.lbl_assist_status.setText(
            f"{len(tables)} tables" + (f" in {region}" if region else "")
        )
        if self.list_tables.count() > 0:
            self.list_tables.setCurrentRow(0)

    def set_assist_fields(self, table: str, fields: list[tuple]):
        """Populate the SQL Assist field list for a selected table."""
        self._assist_fields[table] = list(fields)
        if table == self._current_assist_table:
            self._populate_assist_fields(table)

    def set_assist_error(self, message: str):
        self.lbl_assist_status.setText(message)

    def _on_load_assist(self):
        self.lbl_assist_status.setText("Loading tables...")
        self.load_assist_requested.emit(self.current_connection())

    def _on_connection_changed(self, connection: str):
        self._assist_tables = []
        self._assist_fields.clear()
        self._current_assist_table = ""
        self.list_tables.clear()
        self.list_fields.clear()
        if connection:
            self.lbl_assist_status.setText(f"Loading tables for {self.current_connection_label()}...")
            self.load_assist_requested.emit(self.current_connection())
        else:
            self.lbl_assist_status.setText("Select an ODBC connection")

    def _on_assist_table_selected(self, current, previous):
        if current is None:
            return
        table = current.data(Qt.ItemDataRole.UserRole) or current.text()
        if table == self._current_assist_table:
            return
        self._current_assist_table = table
        if table in self._assist_fields:
            self._populate_assist_fields(table)
        else:
            self.list_fields.clear()
            self.lbl_assist_status.setText(f"Loading fields for {table}...")
            self.load_fields_requested.emit(self.current_connection(), table)

    def _show_table_context_menu(self, pos):
        item = self.list_tables.itemAt(pos)
        if item is None:
            return
        table = str(item.data(Qt.ItemDataRole.UserRole) or item.text())
        menu = QMenu(self)
        act_preview = menu.addAction("View Top 1000 Rows")
        chosen = menu.exec(self.list_tables.mapToGlobal(pos))
        if chosen is act_preview:
            self._preview_assist_table(table)

    def _preview_assist_table(self, table: str):
        dsn = self.current_connection()
        if not dsn:
            QMessageBox.information(self, "ODBC Required", "Select an ODBC connection first.")
            return
        from suiteview.audit.dialogs.tables_dialog import _TablePreviewDialog
        dlg = _TablePreviewDialog(dsn, table, self)
        dlg.show()

    def _populate_assist_fields(self, table: str):
        fields = self._assist_fields.get(table, [])
        self.list_fields.clear()
        ordered_fields = self._ordered_assist_fields(fields)
        for field in ordered_fields:
            name = field[0]
            type_name = field[1] if len(field) > 1 else ""
            is_key = bool(field[2]) if len(field) > 2 else False
            label = f"{name}  ({type_name})" if type_name else name
            item = QListWidgetItem(label)
            item.setData(Qt.ItemDataRole.UserRole, name)
            if is_key:
                font = item.font()
                font.setWeight(QFont.Weight.Bold)
                item.setFont(font)
                item.setToolTip("Key/index field")
            self.list_fields.addItem(item)
        self.lbl_assist_status.setText(f"{table}: {len(fields)} fields")
        self._filter_assist_fields(self.txt_field_search.text())

    def _ordered_assist_fields(self, fields: list[tuple]) -> list[tuple]:
        if self._fields_sort_mode == "native":
            return list(fields)
        return sorted(
            fields,
            key=lambda field: str(field[0]).lower(),
            reverse=self._fields_sort_mode == "desc",
        )

    def _toggle_fields_sort(self):
        next_mode = {"native": "asc", "asc": "desc", "desc": "native"}
        self._fields_sort_mode = next_mode[self._fields_sort_mode]
        labels = {"native": "Fields", "asc": "Fields ↑", "desc": "Fields ↓"}
        self.btn_fields_header.setText(labels[self._fields_sort_mode])
        if self._current_assist_table:
            self._populate_assist_fields(self._current_assist_table)

    def _filter_assist_tables(self, text: str):
        filt = text.strip().lower()
        for row in range(self.list_tables.count()):
            item = self.list_tables.item(row)
            item.setHidden(filt not in item.text().lower() if filt else False)

    def _filter_assist_fields(self, text: str):
        filt = text.strip().lower()
        for row in range(self.list_fields.count()):
            item = self.list_fields.item(row)
            item.setHidden(filt not in item.text().lower() if filt else False)

    def _insert_sql_text(self, text: str):
        cursor = self.txt_sql.textCursor()
        cursor.insertText(text)
        self.txt_sql.setTextCursor(cursor)
        self.txt_sql.setFocus()

    def _current_table_name(self) -> str:
        item = self.list_tables.currentItem()
        if item is None:
            return ""
        return str(item.data(Qt.ItemDataRole.UserRole) or item.text())

    def _selected_field_names(self) -> list[str]:
        names = []
        for item in self.list_fields.selectedItems():
            names.append(str(item.data(Qt.ItemDataRole.UserRole) or item.text()))
        return names

    def _insert_current_table(self):
        table = self._current_table_name()
        if table:
            self._insert_sql_text(table)

    def _insert_select_template(self):
        table = self._current_table_name()
        if table:
            self._insert_sql_text(f"SELECT *\nFROM {table}\nFETCH FIRST 25 ROWS ONLY")

    def _insert_selected_fields(self):
        fields = self._selected_field_names()
        if fields:
            self._insert_sql_text(", ".join(fields))

    def _insert_selected_fields_csv(self):
        fields = self._selected_field_names()
        table = self._current_table_name()
        if table and fields:
            fields = [f"{table}.{field}" for field in fields]
        if fields:
            self._insert_sql_text(", ".join(fields))

    def set_sql(self, sql: str):
        """Load SQL text and clear stale preview schema."""
        self.txt_sql.setPlainText(sql)
        self.clear_preview()

    def set_running(self, running: bool):
        """Reflect preview execution state."""
        self.bottom_bar.btn_run.setEnabled(not running)
        self.bottom_bar.btn_run.setText("Run..." if running else "Run")

    def set_preview_results(self, df: pd.DataFrame, *, dsn: str):
        """Display captured result schema after a successful preview."""
        self._df = df
        self._dsn = dsn
        self._result_columns = list(df.columns)
        self._column_types = {column: str(df[column].dtype) for column in df.columns}
        self._existing_fields = []
        self._populate_schema(self._result_columns, self._column_types)
        self.results_table.set_dataframe(df, limit_rows=False)
        self._set_save_enabled(bool(self.current_sql()) and df is not None)
        self.bottom_bar.lbl_result_count.setText(f"Result count: {len(df)}")
        self.lbl_status.setText(f"Captured {len(df.columns)} columns from {dsn}")
        self.editor_tabs.setCurrentIndex(1)  # Results

    def clear_preview(self):
        """Clear preview schema when SQL changes or a new object starts."""
        self._df = None
        self._dsn = ""
        self._result_columns = []
        self._column_types = {}
        self._existing_fields = []
        self.schema_table.setRowCount(0)
        self.results_table.set_dataframe(pd.DataFrame(), limit_rows=False)
        self._set_save_enabled(False)
        self.bottom_bar.reset_timing()
        self.lbl_status.setText("Preview SQL to capture output schema")

    def _populate_schema(self, columns: list[str], column_types: dict[str, str]):
        self.schema_table.setRowCount(0)
        for row, column in enumerate(columns):
            self.schema_table.insertRow(row)
            self.schema_table.setItem(row, 0, QTableWidgetItem(str(column)))
            self.schema_table.setItem(row, 1, QTableWidgetItem(str(column_types.get(column, ""))))
            self.schema_table.setItem(row, 2, QTableWidgetItem("output"))

    def current_sql(self) -> str:
        return self.txt_sql.toPlainText().strip()

    def _on_sql_changed(self):
        if self._df is not None:
            self.clear_preview()

    def _on_preview(self):
        sql = self.current_sql()
        if not sql:
            QMessageBox.information(self, "SQL Required", "Enter SQL before previewing.")
            return
        self._preview_started_at = time.time()
        self.preview_requested.emit(sql)

    def _set_save_enabled(self, enabled: bool):
        has_existing_object = bool(self._original_name.strip())
        self.btn_save.setVisible(has_existing_object)
        self.btn_save.setEnabled(enabled and has_existing_object)
        self.btn_save_as.setEnabled(enabled)

    def _update_object_heading(self):
        name = self._original_name.strip() or "(new)"
        self.lbl_object_heading.setText(f"Manual SQL Object: {name}")
        if hasattr(self, "btn_save"):
            self.btn_save.setVisible(bool(self._original_name.strip()))

    def _on_save(self):
        self._emit_save_request(save_as=False)

    def _on_save_as(self):
        self._emit_save_request(save_as=True)

    def _emit_save_request(self, *, save_as: bool):
        if not self._result_columns:
            QMessageBox.information(self, "Preview Required", "Preview SQL before saving an object.")
            return
        name = self.txt_name.text().strip()
        original_name = self._original_name
        if save_as:
            name, ok = QInputDialog.getText(
                self,
                "Save Manual SQL Object As",
                "Object name:",
                text=name,
            )
            if not ok or not name.strip():
                return
            name = name.strip()
            self.txt_name.setText(name)
            original_name = ""
        if not name:
            QMessageBox.information(self, "Object Name Required", "Enter an object name before saving.")
            return
        tags = [tag.strip() for tag in self.txt_tags.text().split(",") if tag.strip()]
        self.save_requested.emit({
            "name": name,
            "original_name": original_name,
            "description": self.txt_description.text().strip(),
            "tags": tags,
            "sql": self.current_sql(),
            "dsn": self.current_connection() or self._dsn,
            "result_columns": list(self._result_columns),
            "column_types": dict(self._column_types),
            "existing_fields": [replace(field) for field in self._existing_fields],
            "sql_assist": {
                "tables": list(self._pinned_tables),
                "pinned_tables": list(self._pinned_tables),
                "common_tables": list(self._common_table_names),
            },
        })