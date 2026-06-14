"""
Common Table Manager dialog — create, edit, and delete user-defined
lookup / translation tables.

Layout
------
┌─ Left ──────────────────┐  ┌─ Right ──────────────────────────────┐
│ [table list]            │  │  Name: [__________]                  │
│                         │  │  Description:                       │
│ [New] [More]            │  │  [______________________________]    │
│                         │  │  ── Data ──────────────────────────  │
│                         │  │  [frozen type + field header]        │
│                         │  │  [scrollable data grid]              │
│                         │  │  [Add Field] [Add Row] [Paste] [Export] │
│                         │  │                                      │
│                         │  │  [Save]                              │
└─────────────────────────┘  └─────────────────────────────────────┘
"""
from __future__ import annotations

import logging
import re
from datetime import datetime

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QAction, QColor, QFont
from PyQt6.QtWidgets import (
    QApplication,
    QHBoxLayout,
    QHeaderView,
    QInputDialog,
    QLabel,
    QLineEdit,
    QListWidget,
    QMenu,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QSplitter,
    QTableWidget,
    QTableWidgetItem,
    QComboBox,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from suiteview.audit.common_table import COLUMN_TYPES, CommonTable
from suiteview.audit import common_table_store
from suiteview.audit.common_table_defaults import seed_defaults
from suiteview.audit.tabs._styles import TightItemDelegate
from suiteview.ui.widgets.frameless_window import FramelessWindowBase

logger = logging.getLogger(__name__)

_FONT = QFont("Segoe UI", 9)
_FONT_SMALL = QFont("Segoe UI", 8)
_FONT_BOLD = QFont("Segoe UI", 9, QFont.Weight.Bold)
_HEADER_COLORS = ("#1E5BA8", "#0D3A7A", "#082B5C")
_BORDER_COLOR = "#D4A017"
_PANEL_BG = "#F2F5F8"
_TYPE_ROW = 0
_NAME_ROW = 1
_TYPE_ROW_H = 22
_NAME_ROW_H = 20
_ROW_H = 16
_BTN_H = 22

_BTN_STYLE = (
    "QPushButton { background-color: #1E5BA8; color: white;"
    " border: 1px solid #14407A; border-radius: 3px;"
    " padding: 2px 9px; font-size: 8pt; }"
    "QPushButton:hover { background-color: #2A6BC4; }"
    "QPushButton:disabled { background-color: #A0A0A0; border: 1px solid #888; }"
)

_TOOL_BTN_STYLE = (
    "QToolButton { background-color: #F8FBFF; color: #0A1E5E;"
    " border: 1px solid #1E5BA8; border-radius: 3px;"
    " padding: 2px 8px; font-size: 8pt; }"
    "QToolButton:hover { background-color: #E8F0FB; }"
    "QToolButton::menu-indicator { image: none; width: 0px; }"
)

_BTN_GREEN_STYLE = (
    "QPushButton { background-color: #2E7D32; color: white;"
    " border: 1px solid #1B5E20; border-radius: 3px;"
    " padding: 2px 12px; font-size: 8pt; font-weight: bold; }"
    "QPushButton:hover { background-color: #388E3C; }"
    "QPushButton:disabled { background-color: #A0A0A0; border: 1px solid #888; }"
)

_LIST_STYLE = (
    "QListWidget { border: 1px solid #1E5BA8; background-color: white;"
    " font-size: 8pt; outline: none; }"
    "QListWidget::item { padding: 0px 5px; }"
    "QListWidget::item:selected { background-color: #A0C4E8; color: black; }"
    "QListWidget::item:hover { background-color: #D6E8FA; }"
)

_TABLE_STYLE = (
    "QTableWidget { border: 1px solid #1E5BA8; background-color: white;"
    " font-size: 8pt; selection-background-color: #D6E8FA;"
    " selection-color: #0A1E5E; }"
    "QTableWidget::item { padding: 0px 3px; border: none; }"
    "QTableWidget::item:selected { background-color: #D6E8FA; color: black; }"
    "QHeaderView { background-color: #E8F0FB; border: none; }"
    "QHeaderView::section { background-color: #E8F0FB; color: #0A1E5E;"
    " font-size: 8pt; font-weight: bold; padding: 1px 6px;"
    " border: none; border-bottom: 1px solid #1E5BA8; }"
)

_INPUT_STYLE = (
    "QLineEdit { border: 1px solid #1E5BA8; padding: 2px 4px;"
    " font-size: 9pt; }"
)

_DESC_STYLE = (
    "QPlainTextEdit { border: 1px solid #1E5BA8; padding: 2px 4px;"
    " font-size: 9pt; background-color: white; }"
)

_TYPE_COMBO_STYLE = (
    "QComboBox { background-color: #E8F0FB; color: #0A1E5E;"
    " border: none; padding: 0px 4px; font-size: 8pt; }"
    "QComboBox::drop-down { border: none; width: 14px; }"
)


class CommonTableDialog(FramelessWindowBase):
    """Manager dialog for Common Tables."""

    tables_changed = pyqtSignal()  # emitted when tables are saved/deleted

    _instance = None

    @classmethod
    def show_instance(cls, parent=None):
        """Show or raise the singleton dialog."""
        if cls._instance is None or not cls._instance.isVisible():
            cls._instance = cls(parent)
            cls._instance.show()
        else:
            cls._instance.raise_()
            cls._instance.activateWindow()
        return cls._instance

    def __init__(self, parent=None):
        self._current_name: str = ""  # name of table being edited
        self._dirty = False

        seed_defaults()  # create starter tables on first use

        super().__init__(
            title="Common Tables",
            default_size=(1050, 650),
            min_size=(900, 600),
            parent=None,
            header_colors=_HEADER_COLORS,
            border_color=_BORDER_COLOR,
        )
        self.setWindowTitle("Common Tables")
        self.setFont(_FONT)
        self._refresh_list()

    # ── UI construction ──────────────────────────────────────────

    def build_content(self) -> QWidget:
        body = QWidget()
        body.setStyleSheet(f"QWidget {{ background-color: {_PANEL_BG}; }}")
        root = QHBoxLayout(body)
        root.setContentsMargins(6, 5, 6, 7)
        root.setSpacing(6)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.setChildrenCollapsible(False)
        splitter.setHandleWidth(4)
        self._splitter = splitter
        root.addWidget(splitter)

        # ── Left panel: table list ───────────────────────────────
        left = QWidget()
        left_lay = QVBoxLayout(left)
        left_lay.setContentsMargins(0, 0, 0, 0)
        left_lay.setSpacing(4)

        lbl = QLabel("Common Tables")
        lbl.setFont(_FONT_BOLD)
        lbl.setStyleSheet("color: #0A1E5E;")
        left_lay.addWidget(lbl)

        self.lst_tables = QListWidget()
        self.lst_tables.setFont(_FONT_SMALL)
        self.lst_tables.setItemDelegate(TightItemDelegate(self.lst_tables))
        self.lst_tables.setUniformItemSizes(True)
        self.lst_tables.setSpacing(0)
        self.lst_tables.setStyleSheet(_LIST_STYLE)
        self.lst_tables.currentTextChanged.connect(self._on_table_selected)
        left_lay.addWidget(self.lst_tables)

        btn_row = QHBoxLayout()
        btn_row.setSpacing(5)
        self.btn_new = QPushButton("New")
        self.btn_new.setFont(_FONT_SMALL)
        self.btn_new.setFixedHeight(_BTN_H)
        self.btn_new.setStyleSheet(_BTN_STYLE)
        self.btn_new.clicked.connect(self._on_new)
        btn_row.addWidget(self.btn_new)

        self.btn_table_actions = self._make_menu_button(
            "More",
            [
                ("Duplicate selected table", self._on_duplicate),
                ("Delete selected table", self._on_delete),
            ],
        )
        btn_row.addWidget(self.btn_table_actions)
        left_lay.addLayout(btn_row)
        self._nav_panel = left
        splitter.addWidget(left)

        # ── Right panel: editor ──────────────────────────────────
        right = QWidget()
        right_lay = QVBoxLayout(right)
        right_lay.setContentsMargins(4, 0, 0, 0)
        right_lay.setSpacing(5)

        # Name
        name_row = QHBoxLayout()
        name_row.setSpacing(6)
        name_row.addWidget(QLabel("Name:"))
        self.txt_name = QLineEdit()
        self.txt_name.setStyleSheet(_INPUT_STYLE)
        self.txt_name.setMaximumWidth(300)
        self.txt_name.setFixedHeight(22)
        self.txt_name.textEdited.connect(self._mark_dirty)
        name_row.addWidget(self.txt_name)
        name_row.addStretch()
        right_lay.addLayout(name_row)

        desc_label = QLabel("Description:")
        desc_label.setFont(_FONT_SMALL)
        desc_label.setStyleSheet("color: #0A1E5E;")
        right_lay.addWidget(desc_label)

        self.txt_desc = QPlainTextEdit()
        self.txt_desc.setStyleSheet(_DESC_STYLE)
        self.txt_desc.setFixedHeight(48)
        self.txt_desc.textChanged.connect(self._mark_dirty)
        right_lay.addWidget(self.txt_desc)

        # ── Data section ─────────────────────────────────────────
        data_header = QLabel("Data")
        data_header.setFont(_FONT_BOLD)
        data_header.setStyleSheet("color: #0A1E5E;")
        right_lay.addWidget(data_header)

        self.tbl_header = QTableWidget(2, 0)
        self._configure_header_grid(self.tbl_header)
        self.tbl_header.itemChanged.connect(self._mark_dirty)
        right_lay.addWidget(self.tbl_header)

        self.tbl_data = QTableWidget(0, 0)
        self._configure_grid(self.tbl_data)
        data_header_view = self.tbl_data.horizontalHeader()
        data_header_view.setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        data_header_view.setStretchLastSection(False)
        data_header_view.hide()
        self.tbl_data.itemChanged.connect(self._mark_dirty)
        right_lay.addWidget(self.tbl_data)
        self._sync_horizontal_scrollbars()

        data_btn_row = QHBoxLayout()
        data_btn_row.setSpacing(5)
        btn_add_field = QPushButton("Add Field")
        btn_add_field.setFont(_FONT_SMALL)
        btn_add_field.setFixedHeight(_BTN_H)
        btn_add_field.setStyleSheet(_BTN_STYLE)
        btn_add_field.clicked.connect(self._on_add_column)
        data_btn_row.addWidget(btn_add_field)

        btn_add_row = QPushButton("Add Row")
        btn_add_row.setFont(_FONT_SMALL)
        btn_add_row.setFixedHeight(_BTN_H)
        btn_add_row.setStyleSheet(_BTN_STYLE)
        btn_add_row.clicked.connect(self._on_add_row)
        data_btn_row.addWidget(btn_add_row)

        btn_paste = QPushButton("Paste")
        btn_paste.setFont(_FONT_SMALL)
        btn_paste.setFixedHeight(_BTN_H)
        btn_paste.setStyleSheet(_BTN_STYLE)
        btn_paste.setToolTip("Paste rows from the clipboard")
        btn_paste.clicked.connect(self._on_paste)
        data_btn_row.addWidget(btn_paste)

        btn_export = QPushButton("Export")
        btn_export.setFont(_FONT_SMALL)
        btn_export.setFixedHeight(_BTN_H)
        btn_export.setStyleSheet(_BTN_STYLE)
        btn_export.setToolTip("Open this table in a new Excel workbook")
        btn_export.clicked.connect(self._on_export_excel)
        data_btn_row.addWidget(btn_export)

        data_btn_row.addWidget(self._make_menu_button(
            "More",
            [
                ("Remove selected field", self._on_remove_column),
                ("Remove selected row", self._on_remove_row),
                ("Clear all data rows", self._on_clear_data),
            ],
        ))

        data_btn_row.addStretch()
        right_lay.addLayout(data_btn_row)

        # ── Info + Save ──────────────────────────────────────────
        bottom_row = QHBoxLayout()
        self.lbl_info = QLabel("")
        self.lbl_info.setStyleSheet("color: #666; font-size: 8pt;")
        bottom_row.addWidget(self.lbl_info)
        bottom_row.addStretch()

        self.btn_save = QPushButton("Save")
        self.btn_save.setFont(_FONT_SMALL)
        self.btn_save.setStyleSheet(_BTN_GREEN_STYLE)
        self.btn_save.setFixedSize(78, 24)
        self.btn_save.clicked.connect(self._on_save)
        bottom_row.addWidget(self.btn_save)
        right_lay.addLayout(bottom_row)

        self._canvas_panel = right
        splitter.addWidget(right)
        splitter.setSizes([220, 780])
        return body

    def _make_menu_button(self, text: str, actions: list[tuple[str, object]]) -> QToolButton:
        button = QToolButton()
        button.setText(text)
        button.setFont(_FONT_SMALL)
        button.setFixedHeight(_BTN_H)
        button.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        button.setStyleSheet(_TOOL_BTN_STYLE)

        menu = QMenu(button)
        for label, slot in actions:
            action = QAction(label, button)
            action.triggered.connect(slot)
            menu.addAction(action)
        button.setMenu(menu)
        return button

    def _configure_grid(self, table: QTableWidget):
        table.setStyleSheet(_TABLE_STYLE)
        table.setShowGrid(False)
        table.setAlternatingRowColors(False)
        table.setWordWrap(False)
        table.setCornerButtonEnabled(False)
        table.verticalHeader().hide()
        table.verticalHeader().setDefaultSectionSize(_ROW_H)
        table.verticalHeader().setMinimumSectionSize(16)
        table.horizontalHeader().setDefaultSectionSize(110)
        table.horizontalHeader().setMinimumSectionSize(36)
        table.horizontalHeader().setStretchLastSection(False)

    def _configure_header_grid(self, table: QTableWidget):
        self._configure_grid(table)
        table.setFixedHeight(_TYPE_ROW_H + _NAME_ROW_H + 3)
        table.setRowCount(2)
        table.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        table.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        table.horizontalHeader().hide()
        table.verticalHeader().hide()
        table.setRowHeight(_TYPE_ROW, _TYPE_ROW_H)
        table.setRowHeight(_NAME_ROW, _NAME_ROW_H)

    def _sync_horizontal_scrollbars(self):
        header_bar = self.tbl_header.horizontalScrollBar()
        data_bar = self.tbl_data.horizontalScrollBar()
        data_bar.valueChanged.connect(header_bar.setValue)
        header_bar.valueChanged.connect(data_bar.setValue)

    def _current_column(self) -> int:
        column = self.tbl_header.currentColumn()
        if column >= 0:
            return column
        return self.tbl_data.currentColumn()

    def _fit_grid_columns(self, table: QTableWidget | None = None, *, min_width: int = 72, max_width: int = 260):
        if self.tbl_data.columnCount() == 0:
            return
        self.tbl_header.resizeColumnsToContents()
        self.tbl_data.resizeColumnsToContents()
        for column in range(self.tbl_data.columnCount()):
            width = max(
                self.tbl_header.columnWidth(column),
                self.tbl_data.columnWidth(column),
            ) + 10
            width = max(min_width, min(width, max_width))
            self.tbl_header.setColumnWidth(column, width)
            self.tbl_data.setColumnWidth(column, width)

    def _apply_data_row_heights(self):
        self.tbl_header.setRowHeight(_TYPE_ROW, _TYPE_ROW_H)
        self.tbl_header.setRowHeight(_NAME_ROW, _NAME_ROW_H)
        for row in range(self.tbl_data.rowCount()):
            self.tbl_data.setRowHeight(row, _ROW_H)

    def _mark_dirty(self, *args):
        self._dirty = True

    def _make_type_combo(self, current_type: str = "TEXT") -> QComboBox:
        combo = QComboBox()
        combo.addItems(COLUMN_TYPES)
        combo.setCurrentText(current_type if current_type in COLUMN_TYPES else "TEXT")
        combo.setStyleSheet(_TYPE_COMBO_STYLE)
        combo.currentTextChanged.connect(self._mark_dirty)
        return combo

    def _set_field_metadata(self, column: int, name: str, field_type: str = "TEXT"):
        combo = self._make_type_combo(field_type)
        self.tbl_header.setCellWidget(_TYPE_ROW, column, combo)
        item = QTableWidgetItem(name)
        item.setFont(_FONT_BOLD)
        item.setBackground(QColor("#F8FBFF"))
        item.setForeground(QColor("#0A1E5E"))
        self.tbl_header.setItem(_NAME_ROW, column, item)

    def _set_data_column_count(self, count: int):
        self.tbl_header.setColumnCount(count)
        self.tbl_data.setColumnCount(count)
        for column in range(count):
            if self.tbl_header.cellWidget(_TYPE_ROW, column) is None:
                self._set_field_metadata(column, f"col{column + 1}", "TEXT")
        self._fit_grid_columns(self.tbl_data)

    def _clear_data_grid(self):
        header_was_blocked = self.tbl_header.signalsBlocked()
        was_blocked = self.tbl_data.signalsBlocked()
        self.tbl_header.blockSignals(True)
        self.tbl_data.blockSignals(True)
        self.tbl_header.setColumnCount(0)
        self.tbl_data.setRowCount(0)
        self.tbl_data.setColumnCount(0)
        self.tbl_header.blockSignals(header_was_blocked)
        self.tbl_data.blockSignals(was_blocked)

    # ── List management ──────────────────────────────────────────

    def _refresh_list(self):
        self.lst_tables.blockSignals(True)
        self.lst_tables.clear()
        for ct in common_table_store.list_tables():
            self.lst_tables.addItem(ct.name)
        self.lst_tables.blockSignals(False)

    def _on_table_selected(self, name: str):
        if not name:
            return
        if self._dirty:
            reply = QMessageBox.question(
                self, "Unsaved Changes",
                f"Save changes to '{self._current_name}' before switching?",
                QMessageBox.StandardButton.Yes
                | QMessageBox.StandardButton.No
                | QMessageBox.StandardButton.Cancel,
            )
            if reply == QMessageBox.StandardButton.Cancel:
                # Re-select old item
                items = self.lst_tables.findItems(
                    self._current_name, Qt.MatchFlag.MatchExactly
                )
                if items:
                    self.lst_tables.blockSignals(True)
                    self.lst_tables.setCurrentItem(items[0])
                    self.lst_tables.blockSignals(False)
                return
            if reply == QMessageBox.StandardButton.Yes:
                self._on_save()

        ct = common_table_store.load_table(name)
        if ct:
            self._load_table(ct)

    def _load_table(self, ct: CommonTable):
        self._current_name = ct.name
        self._dirty = False
        self.txt_name.setText(ct.name)
        self.txt_desc.setPlainText(ct.description)

        self.tbl_header.blockSignals(True)
        self.tbl_data.blockSignals(True)
        self._clear_data_grid()
        self._set_data_column_count(len(ct.columns))
        for column, col in enumerate(ct.columns):
            self._set_field_metadata(column, col["name"], col.get("type", "TEXT"))

        self.tbl_data.setRowCount(len(ct.rows))
        self._apply_data_row_heights()
        for r, row in enumerate(ct.rows):
            for c, val in enumerate(row):
                if c < self.tbl_data.columnCount():
                    self.tbl_data.setItem(r, c, QTableWidgetItem(str(val)))
        self.tbl_header.blockSignals(False)
        self.tbl_data.blockSignals(False)
        self._fit_grid_columns(self.tbl_data)

        info_parts = [f"{ct.row_count} rows"]
        info_parts.append(f"Created: {ct.created_at:%Y-%m-%d %H:%M}")
        if ct.updated_at != ct.created_at:
            info_parts.append(f"Updated: {ct.updated_at:%Y-%m-%d %H:%M}")
        self.lbl_info.setText("  |  ".join(info_parts))
        self._dirty = False

    # ── Column actions ───────────────────────────────────────────

    def _on_add_column(self):
        column = self._current_column()
        if column < 0:
            column = self.tbl_data.columnCount() - 1
        insert_at = column + 1
        self.tbl_header.insertColumn(insert_at)
        self.tbl_data.insertColumn(insert_at)
        self._set_field_metadata(insert_at, f"col{insert_at + 1}", "TEXT")
        self._fit_grid_columns(self.tbl_data)
        self._dirty = True

    def _on_remove_column(self):
        column = self._current_column()
        if column < 0:
            return
        self.tbl_header.removeColumn(column)
        self.tbl_data.removeColumn(column)
        self._fit_grid_columns(self.tbl_data)
        self._dirty = True

    # ── Row actions ──────────────────────────────────────────────

    def _on_add_row(self):
        if self.tbl_data.columnCount() == 0:
            self._on_add_column()
        row = self.tbl_data.rowCount()
        self.tbl_data.insertRow(row)
        self.tbl_data.setRowHeight(row, _ROW_H)
        self._dirty = True

    def _on_remove_row(self):
        row = self.tbl_data.currentRow()
        if row < 0:
            return
        self.tbl_data.removeRow(row)
        self._dirty = True

    def _on_clear_data(self):
        if self.tbl_data.rowCount() == 0:
            return
        reply = QMessageBox.question(
            self, "Clear Data",
            "Remove all data rows?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply == QMessageBox.StandardButton.Yes:
            self.tbl_data.setRowCount(0)
            self._dirty = True

    # ── Clipboard paste ──────────────────────────────────────────

    def _on_paste(self):
        """Parse clipboard text (tab/comma/newline delimited) into the
        data grid. Handles pasting from Excel, CSV, or plain text.

        If columns are not yet defined, auto-creates them from the first
        row (treating it as a header when it looks like one).
        """
        clipboard = QApplication.clipboard()
        if clipboard is None:
            return
        text = clipboard.text()
        if not text:
            return

        # Parse rows: split on newlines, then columns on tab or comma
        raw_rows: list[list[str]] = []
        for line in text.splitlines():
            line = line.strip()
            if not line:
                continue
            # Prefer tab delimiter; fall back to comma
            if "\t" in line:
                cells = [c.strip() for c in line.split("\t")]
            else:
                cells = [c.strip() for c in line.split(",")]
            raw_rows.append(cells)

        if not raw_rows:
            return

        if self._paste_exported_table(raw_rows):
            return

        # Auto-create fields if none defined yet
        if self.tbl_data.columnCount() == 0:
            first = raw_rows[0]
            # Heuristic: if every cell in first row looks non-numeric,
            # treat it as a header row
            is_header = all(
                not cell.replace(".", "").replace("-", "").isdigit()
                for cell in first
                if cell
            )
            if is_header:
                self._set_data_column_count(len(first))
                for column, cell in enumerate(first):
                    clean = re.sub(r'[^A-Za-z0-9_]', '_', cell)
                    self._set_field_metadata(column, clean or f"col{column + 1}", "TEXT")
                raw_rows = raw_rows[1:]  # skip header row for data
            else:
                self._set_data_column_count(len(first))

        # Ensure column count matches
        num_cols = self.tbl_data.columnCount()

        # Append data rows
        for cells in raw_rows:
            row = self.tbl_data.rowCount()
            self.tbl_data.insertRow(row)
            self.tbl_data.setRowHeight(row, _ROW_H)
            for c, val in enumerate(cells):
                if c < num_cols:
                    self.tbl_data.setItem(row, c, QTableWidgetItem(val))
        self._fit_grid_columns(self.tbl_data)

        self._dirty = True

    def _paste_exported_table(self, raw_rows: list[list[str]]) -> bool:
        if len(raw_rows) < 2:
            return False
        width = len(raw_rows[1])
        if width == 0:
            return False
        type_row = [cell.strip().upper() for cell in raw_rows[0][:width]]
        if len(type_row) != width or any(cell not in COLUMN_TYPES for cell in type_row):
            return False

        headers = []
        for index, cell in enumerate(raw_rows[1][:width]):
            clean = re.sub(r'[^A-Za-z0-9_]', '_', cell.strip())
            headers.append(clean or f"col{index + 1}")

        data_rows = [(row + [""] * width)[:width] for row in raw_rows[2:]]

        self.tbl_header.blockSignals(True)
        self.tbl_data.blockSignals(True)
        self._clear_data_grid()
        self._set_data_column_count(width)
        for column, (header, field_type) in enumerate(zip(headers, type_row)):
            self._set_field_metadata(column, header, field_type)
        self.tbl_data.setRowCount(len(data_rows))
        self._apply_data_row_heights()
        for row_index, row in enumerate(data_rows):
            for column, value in enumerate(row):
                self.tbl_data.setItem(row_index, column, QTableWidgetItem(value))
        self.tbl_header.blockSignals(False)
        self.tbl_data.blockSignals(False)
        self._fit_grid_columns(self.tbl_data)
        self._dirty = True
        return True

    def _on_export_excel(self):
        col_defs = self._get_column_defs()
        if not col_defs:
            QMessageBox.warning(self, "No Columns", "Please define at least one field before exporting.")
            return

        rows = self._get_data_rows()
        type_row = [col["type"] for col in col_defs]
        header_row = [col["name"] for col in col_defs]
        text_col_indexes = [
            index + 1
            for index, col in enumerate(col_defs)
            if col["type"].upper() == "TEXT"
        ]
        data_rows = [
            [self._coerce_excel_value(row[index] if index < len(row) else "", col["type"])
             for index, col in enumerate(col_defs)]
            for row in rows
        ]

        try:
            from suiteview.core.excel_export import ExcelExportError, open_excel

            excel = open_excel(visible=True)
            try:
                excel.ScreenUpdating = False
                workbook = excel.Workbooks.Add()
                worksheet = workbook.ActiveSheet
                worksheet.Name = self._excel_sheet_name()

                for column_index in text_col_indexes:
                    worksheet.Columns(column_index).NumberFormat = "@"

                export_rows = [type_row, header_row] + data_rows
                row_count = len(export_rows)
                column_count = len(header_row)
                rng = worksheet.Range(worksheet.Cells(1, 1), worksheet.Cells(row_count, column_count))
                rng.Value = tuple(tuple(row) for row in export_rows)

                worksheet.Range(worksheet.Cells(1, 1), worksheet.Cells(1, column_count)).Font.Bold = True
                worksheet.Range(worksheet.Cells(2, 1), worksheet.Cells(2, column_count)).Font.Bold = True
                if row_count > 2:
                    worksheet.Range(worksheet.Cells(2, 1), worksheet.Cells(row_count, column_count)).AutoFilter()
                worksheet.Range("A3").Select()
                excel.ActiveWindow.FreezePanes = True
                worksheet.Columns.AutoFit()
                worksheet.Range("A1").Select()
            finally:
                try:
                    excel.ScreenUpdating = True
                except Exception:
                    pass
        except ExcelExportError as exc:
            QMessageBox.warning(self, "Excel Error", str(exc))
        except Exception as exc:
            logger.exception("Common table Excel export failed")
            QMessageBox.warning(self, "Excel Error", f"Could not export table:\n{exc}")

    def _coerce_excel_value(self, value: str, field_type: str):
        if value is None:
            return ""
        text = str(value)
        if text == "":
            return ""
        field_type = field_type.upper()
        if field_type == "TEXT":
            return text
        clean = text.replace(",", "").replace("$", "").strip()
        try:
            if field_type == "INTEGER":
                return int(float(clean))
            if field_type == "DECIMAL":
                return float(clean)
        except (TypeError, ValueError):
            return text
        return text

    def _excel_sheet_name(self) -> str:
        name = self.txt_name.text().strip() or self._current_name or "Common Table"
        name = re.sub(r'[\\/*?:\[\]]', "_", name).strip()
        return (name or "Common Table")[:31]

    # ── CRUD ─────────────────────────────────────────────────────

    def _on_new(self):
        name, ok = QInputDialog.getText(
            self, "New Common Table", "Table name:"
        )
        if not ok or not name.strip():
            return
        name = name.strip()

        if common_table_store.table_exists(name):
            QMessageBox.warning(
                self, "Exists",
                f"A table named '{name}' already exists."
            )
            return

        ct = CommonTable(name=name)
        common_table_store.save_table(ct)
        self._refresh_list()
        # Select the new table
        items = self.lst_tables.findItems(name, Qt.MatchFlag.MatchExactly)
        if items:
            self.lst_tables.setCurrentItem(items[0])
        self.tables_changed.emit()

    def _on_duplicate(self):
        if not self._current_name:
            return
        ct = common_table_store.load_table(self._current_name)
        if not ct:
            return
        name, ok = QInputDialog.getText(
            self, "Duplicate Table",
            "New table name:",
            text=f"{ct.name}_copy",
        )
        if not ok or not name.strip():
            return
        name = name.strip()
        if common_table_store.table_exists(name):
            QMessageBox.warning(
                self, "Exists",
                f"A table named '{name}' already exists."
            )
            return
        ct.name = name
        ct.created_at = datetime.now()
        ct.updated_at = datetime.now()
        common_table_store.save_table(ct)
        self._refresh_list()
        items = self.lst_tables.findItems(name, Qt.MatchFlag.MatchExactly)
        if items:
            self.lst_tables.setCurrentItem(items[0])
        self.tables_changed.emit()

    def _on_delete(self):
        if not self._current_name:
            return
        reply = QMessageBox.question(
            self, "Delete Table",
            f"Delete common table '{self._current_name}'?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return
        common_table_store.delete_table(self._current_name)
        self._current_name = ""
        self._dirty = False
        self.txt_name.clear()
        self.txt_desc.clear()
        self._clear_data_grid()
        self.lbl_info.clear()
        self._refresh_list()
        self.tables_changed.emit()
        self._dirty = False

    def _on_save(self):
        name = self.txt_name.text().strip()
        if not name:
            QMessageBox.warning(self, "No Name", "Please enter a table name.")
            return

        # Validate: need at least one column
        col_defs = self._get_column_defs()
        if not col_defs:
            QMessageBox.warning(
                self, "No Columns",
                "Please define at least one column."
            )
            return

        # Validate column names are unique
        col_names = [c["name"] for c in col_defs]
        if len(col_names) != len(set(col_names)):
            QMessageBox.warning(
                self, "Duplicate Columns",
                "Column names must be unique."
            )
            return

        # Validate column names are valid identifiers
        for cn in col_names:
            if not re.match(r'^[A-Za-z_][A-Za-z0-9_]*$', cn):
                QMessageBox.warning(
                    self, "Invalid Column Name",
                    f"'{cn}' is not a valid column name.\n"
                    "Use letters, digits, and underscores only "
                    "(must start with a letter or underscore)."
                )
                return

        # Validate table name is a valid identifier
        if not re.match(r'^[A-Za-z_][A-Za-z0-9_]*$', name):
            QMessageBox.warning(
                self, "Invalid Table Name",
                f"'{name}' is not a valid table name.\n"
                "Use letters, digits, and underscores only "
                "(must start with a letter or underscore)."
            )
            return

        # Collect data rows
        rows = self._get_data_rows()

        # If renaming (name changed), delete old file
        if self._current_name and self._current_name != name:
            if common_table_store.table_exists(name):
                reply = QMessageBox.question(
                    self, "Overwrite",
                    f"A table named '{name}' already exists. Overwrite?",
                    QMessageBox.StandardButton.Yes
                    | QMessageBox.StandardButton.No,
                )
                if reply != QMessageBox.StandardButton.Yes:
                    return
            common_table_store.delete_table(self._current_name)

        # Preserve original creation date if editing
        existing = common_table_store.load_table(name)
        created = existing.created_at if existing else datetime.now()

        ct = CommonTable(
            name=name,
            description=self.txt_desc.toPlainText().strip(),
            columns=col_defs,
            rows=rows,
            created_at=created,
            updated_at=datetime.now(),
        )
        common_table_store.save_table(ct)
        self._current_name = name
        self._dirty = False
        self._refresh_list()
        # Re-select
        items = self.lst_tables.findItems(name, Qt.MatchFlag.MatchExactly)
        if items:
            self.lst_tables.blockSignals(True)
            self.lst_tables.setCurrentItem(items[0])
            self.lst_tables.blockSignals(False)
        self._load_table(ct)
        self.tables_changed.emit()

    # ── Helpers ──────────────────────────────────────────────────

    def _get_column_defs(self) -> list[dict]:
        """Read column definitions from the frozen header grid."""
        cols = []
        for column in range(self.tbl_header.columnCount()):
            name_item = self.tbl_header.item(_NAME_ROW, column)
            name = name_item.text().strip() if name_item else ""
            combo = self.tbl_header.cellWidget(_TYPE_ROW, column)
            ctype = combo.currentText() if combo else "TEXT"
            if name:
                cols.append({"name": name, "type": ctype})
        return cols

    def _get_data_rows(self) -> list[list]:
        """Read data rows from the data grid."""
        rows = []
        for r in range(self.tbl_data.rowCount()):
            row = []
            for c in range(self.tbl_data.columnCount()):
                item = self.tbl_data.item(r, c)
                row.append(item.text() if item else "")
            rows.append(row)
        return rows
