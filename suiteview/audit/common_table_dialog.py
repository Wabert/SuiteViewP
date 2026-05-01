"""
Common Table Manager dialog — create, edit, and delete user-defined
lookup / translation tables.

Layout
------
┌─ Left ──────────────────┐  ┌─ Right ──────────────────────────────┐
│ [table list]            │  │  Name: [__________]                  │
│                         │  │  Description: [________________]     │
│ [New] [Duplicate] [Del] │  │                                      │
│                         │  │  ── Columns ──────────────────────── │
│                         │  │  [column grid: Name | Type]          │
│                         │  │  [+ Add Column] [- Remove Column]    │
│                         │  │                                      │
│                         │  │  ── Data ──────────────────────────  │
│                         │  │  [data grid]                         │
│                         │  │  [+ Add Row] [- Remove Row]          │
│                         │  │  [Paste from Clipboard]              │
│                         │  │                                      │
│                         │  │  [Save]                              │
└─────────────────────────┘  └─────────────────────────────────────┘
"""
from __future__ import annotations

import logging
import re
from datetime import datetime

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QFont
from PyQt6.QtWidgets import (
    QApplication,
    QDialog,
    QHBoxLayout,
    QHeaderView,
    QInputDialog,
    QLabel,
    QLineEdit,
    QListWidget,
    QMessageBox,
    QPushButton,
    QSplitter,
    QTableWidget,
    QTableWidgetItem,
    QComboBox,
    QVBoxLayout,
    QWidget,
)

from suiteview.audit.common_table import COLUMN_TYPES, CommonTable
from suiteview.audit import common_table_store
from suiteview.audit.common_table_defaults import seed_defaults

logger = logging.getLogger(__name__)

_FONT = QFont("Segoe UI", 9)
_FONT_BOLD = QFont("Segoe UI", 9, QFont.Weight.Bold)

_BTN_STYLE = (
    "QPushButton { background-color: #1E5BA8; color: white;"
    " border: 1px solid #14407A; border-radius: 3px;"
    " padding: 4px 12px; font-size: 9pt; }"
    "QPushButton:hover { background-color: #2A6BC4; }"
    "QPushButton:disabled { background-color: #A0A0A0; border: 1px solid #888; }"
)

_BTN_RED_STYLE = (
    "QPushButton { background-color: #C00000; color: white;"
    " border: 1px solid #900; border-radius: 3px;"
    " padding: 4px 12px; font-size: 9pt; }"
    "QPushButton:hover { background-color: #E00000; }"
    "QPushButton:disabled { background-color: #A0A0A0; border: 1px solid #888; }"
)

_BTN_GREEN_STYLE = (
    "QPushButton { background-color: #2E7D32; color: white;"
    " border: 1px solid #1B5E20; border-radius: 3px;"
    " padding: 4px 16px; font-size: 9pt; }"
    "QPushButton:hover { background-color: #388E3C; }"
    "QPushButton:disabled { background-color: #A0A0A0; border: 1px solid #888; }"
)

_LIST_STYLE = (
    "QListWidget { border: 1px solid #1E5BA8; background-color: white;"
    " font-size: 9pt; outline: none; }"
    "QListWidget::item:selected { background-color: #A0C4E8; color: black; }"
    "QListWidget::item:hover { background-color: #D6E8FA; }"
)

_TABLE_STYLE = (
    "QTableWidget { border: 1px solid #1E5BA8; background-color: white;"
    " gridline-color: #D0D8E0; font-size: 9pt; }"
    "QTableWidget::item:selected { background-color: #D6E8FA; color: black; }"
    "QHeaderView::section { background-color: #E8F0FB; color: #0A1E5E;"
    " font-size: 8pt; font-weight: bold; padding: 3px;"
    " border: none; border-bottom: 1px solid #1E5BA8;"
    " border-right: 1px solid #D0D8E0; }"
)

_INPUT_STYLE = (
    "QLineEdit { border: 1px solid #1E5BA8; padding: 2px 4px;"
    " font-size: 9pt; }"
)


class CommonTableDialog(QDialog):
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
        super().__init__(parent)
        self.setWindowTitle("Common Tables")
        self.setMinimumSize(900, 600)
        self.resize(1050, 650)
        self.setFont(_FONT)
        self.setStyleSheet("QWidget { background-color: #F0F0F0; }")

        self._current_name: str = ""  # name of table being edited
        self._dirty = False

        seed_defaults()  # create starter tables on first use
        self._build_ui()
        self._refresh_list()

    # ── UI construction ──────────────────────────────────────────

    def _build_ui(self):
        root = QHBoxLayout(self)
        root.setContentsMargins(8, 8, 8, 8)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        root.addWidget(splitter)

        # ── Left panel: table list ───────────────────────────────
        left = QWidget()
        left_lay = QVBoxLayout(left)
        left_lay.setContentsMargins(0, 0, 0, 0)
        left_lay.setSpacing(4)

        lbl = QLabel("Common Tables")
        lbl.setFont(_FONT_BOLD)
        left_lay.addWidget(lbl)

        self.lst_tables = QListWidget()
        self.lst_tables.setStyleSheet(_LIST_STYLE)
        self.lst_tables.currentTextChanged.connect(self._on_table_selected)
        left_lay.addWidget(self.lst_tables)

        btn_row = QHBoxLayout()
        btn_row.setSpacing(4)
        self.btn_new = QPushButton("New")
        self.btn_new.setStyleSheet(_BTN_STYLE)
        self.btn_new.clicked.connect(self._on_new)
        btn_row.addWidget(self.btn_new)

        self.btn_dup = QPushButton("Duplicate")
        self.btn_dup.setStyleSheet(_BTN_STYLE)
        self.btn_dup.clicked.connect(self._on_duplicate)
        btn_row.addWidget(self.btn_dup)

        self.btn_del = QPushButton("Delete")
        self.btn_del.setStyleSheet(_BTN_RED_STYLE)
        self.btn_del.clicked.connect(self._on_delete)
        btn_row.addWidget(self.btn_del)

        left_lay.addLayout(btn_row)
        splitter.addWidget(left)

        # ── Right panel: editor ──────────────────────────────────
        right = QWidget()
        right_lay = QVBoxLayout(right)
        right_lay.setContentsMargins(4, 0, 0, 0)
        right_lay.setSpacing(6)

        # Name + description
        name_row = QHBoxLayout()
        name_row.addWidget(QLabel("Name:"))
        self.txt_name = QLineEdit()
        self.txt_name.setStyleSheet(_INPUT_STYLE)
        self.txt_name.setMaximumWidth(300)
        name_row.addWidget(self.txt_name)
        name_row.addSpacing(12)
        name_row.addWidget(QLabel("Description:"))
        self.txt_desc = QLineEdit()
        self.txt_desc.setStyleSheet(_INPUT_STYLE)
        name_row.addWidget(self.txt_desc)
        right_lay.addLayout(name_row)

        # ── Columns section ──────────────────────────────────────
        col_header = QLabel("Columns")
        col_header.setFont(_FONT_BOLD)
        right_lay.addWidget(col_header)

        self.tbl_columns = QTableWidget(0, 2)
        self.tbl_columns.setHorizontalHeaderLabels(["Column Name", "Type"])
        self.tbl_columns.setStyleSheet(_TABLE_STYLE)
        self.tbl_columns.horizontalHeader().setStretchLastSection(True)
        self.tbl_columns.horizontalHeader().setSectionResizeMode(
            0, QHeaderView.ResizeMode.Stretch
        )
        self.tbl_columns.setMaximumHeight(150)
        self.tbl_columns.verticalHeader().setDefaultSectionSize(22)
        self.tbl_columns.verticalHeader().hide()
        right_lay.addWidget(self.tbl_columns)

        col_btn_row = QHBoxLayout()
        col_btn_row.setSpacing(4)
        btn_add_col = QPushButton("+ Add Column")
        btn_add_col.setStyleSheet(_BTN_STYLE)
        btn_add_col.clicked.connect(self._on_add_column)
        col_btn_row.addWidget(btn_add_col)
        btn_rem_col = QPushButton("- Remove Column")
        btn_rem_col.setStyleSheet(_BTN_STYLE)
        btn_rem_col.clicked.connect(self._on_remove_column)
        col_btn_row.addWidget(btn_rem_col)
        col_btn_row.addStretch()
        right_lay.addLayout(col_btn_row)

        # ── Data section ─────────────────────────────────────────
        data_header = QLabel("Data")
        data_header.setFont(_FONT_BOLD)
        right_lay.addWidget(data_header)

        self.tbl_data = QTableWidget(0, 0)
        self.tbl_data.setStyleSheet(_TABLE_STYLE)
        self.tbl_data.horizontalHeader().setStretchLastSection(True)
        self.tbl_data.verticalHeader().setDefaultSectionSize(22)
        right_lay.addWidget(self.tbl_data)

        data_btn_row = QHBoxLayout()
        data_btn_row.setSpacing(4)
        btn_add_row = QPushButton("+ Add Row")
        btn_add_row.setStyleSheet(_BTN_STYLE)
        btn_add_row.clicked.connect(self._on_add_row)
        data_btn_row.addWidget(btn_add_row)
        btn_rem_row = QPushButton("- Remove Row")
        btn_rem_row.setStyleSheet(_BTN_STYLE)
        btn_rem_row.clicked.connect(self._on_remove_row)
        data_btn_row.addWidget(btn_rem_row)

        btn_paste = QPushButton("Paste from\nClipboard")
        btn_paste.setStyleSheet(_BTN_STYLE)
        btn_paste.setFixedSize(120, 40)
        btn_paste.clicked.connect(self._on_paste)
        data_btn_row.addWidget(btn_paste)

        btn_clear_data = QPushButton("Clear Data")
        btn_clear_data.setStyleSheet(_BTN_RED_STYLE)
        btn_clear_data.clicked.connect(self._on_clear_data)
        data_btn_row.addWidget(btn_clear_data)

        data_btn_row.addStretch()
        right_lay.addLayout(data_btn_row)

        # ── Info + Save ──────────────────────────────────────────
        bottom_row = QHBoxLayout()
        self.lbl_info = QLabel("")
        self.lbl_info.setStyleSheet("color: #666; font-size: 8pt;")
        bottom_row.addWidget(self.lbl_info)
        bottom_row.addStretch()

        self.btn_save = QPushButton("Save")
        self.btn_save.setStyleSheet(_BTN_GREEN_STYLE)
        self.btn_save.setFixedSize(100, 32)
        self.btn_save.clicked.connect(self._on_save)
        bottom_row.addWidget(self.btn_save)
        right_lay.addLayout(bottom_row)

        splitter.addWidget(right)
        splitter.setSizes([220, 780])

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
        self.txt_desc.setText(ct.description)

        # Populate columns grid
        self.tbl_columns.setRowCount(len(ct.columns))
        for i, col in enumerate(ct.columns):
            self.tbl_columns.setItem(i, 0, QTableWidgetItem(col["name"]))
            combo = QComboBox()
            combo.addItems(COLUMN_TYPES)
            combo.setCurrentText(col.get("type", "TEXT"))
            self.tbl_columns.setCellWidget(i, 1, combo)

        # Update data grid headers
        self._sync_data_headers()

        # Populate data grid
        self.tbl_data.setRowCount(len(ct.rows))
        for r, row in enumerate(ct.rows):
            for c, val in enumerate(row):
                if c < self.tbl_data.columnCount():
                    self.tbl_data.setItem(r, c, QTableWidgetItem(str(val)))

        info_parts = [f"{ct.row_count} rows"]
        info_parts.append(f"Created: {ct.created_at:%Y-%m-%d %H:%M}")
        if ct.updated_at != ct.created_at:
            info_parts.append(f"Updated: {ct.updated_at:%Y-%m-%d %H:%M}")
        self.lbl_info.setText("  |  ".join(info_parts))

    def _sync_data_headers(self):
        """Update data grid column headers from the columns grid."""
        col_names = self._get_column_defs()
        self.tbl_data.setColumnCount(len(col_names))
        self.tbl_data.setHorizontalHeaderLabels(
            [c["name"] for c in col_names]
        )

    # ── Column actions ───────────────────────────────────────────

    def _on_add_column(self):
        row = self.tbl_columns.rowCount()
        self.tbl_columns.insertRow(row)
        self.tbl_columns.setItem(row, 0, QTableWidgetItem(f"col{row + 1}"))
        combo = QComboBox()
        combo.addItems(COLUMN_TYPES)
        self.tbl_columns.setCellWidget(row, 1, combo)
        self._sync_data_headers()
        self._dirty = True

    def _on_remove_column(self):
        row = self.tbl_columns.currentRow()
        if row < 0:
            return
        self.tbl_columns.removeRow(row)
        self._sync_data_headers()
        self._dirty = True

    # ── Row actions ──────────────────────────────────────────────

    def _on_add_row(self):
        row = self.tbl_data.rowCount()
        self.tbl_data.insertRow(row)
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

        # Auto-create columns if none defined yet
        if self.tbl_columns.rowCount() == 0:
            first = raw_rows[0]
            # Heuristic: if every cell in first row looks non-numeric,
            # treat it as a header row
            is_header = all(
                not cell.replace(".", "").replace("-", "").isdigit()
                for cell in first
                if cell
            )
            if is_header:
                for cell in first:
                    self._on_add_column()
                    row = self.tbl_columns.rowCount() - 1
                    # Clean the name: remove spaces, special chars
                    clean = re.sub(r'[^A-Za-z0-9_]', '_', cell)
                    self.tbl_columns.setItem(
                        row, 0, QTableWidgetItem(clean or f"col{row + 1}")
                    )
                raw_rows = raw_rows[1:]  # skip header row for data
                self._sync_data_headers()
            else:
                # Create generic columns
                num_cols = len(first)
                for i in range(num_cols):
                    self._on_add_column()
                self._sync_data_headers()

        # Ensure column count matches
        num_cols = self.tbl_data.columnCount()

        # Append data rows
        for cells in raw_rows:
            row = self.tbl_data.rowCount()
            self.tbl_data.insertRow(row)
            for c, val in enumerate(cells):
                if c < num_cols:
                    self.tbl_data.setItem(row, c, QTableWidgetItem(val))

        self._dirty = True

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
        self.tbl_columns.setRowCount(0)
        self.tbl_data.setRowCount(0)
        self.tbl_data.setColumnCount(0)
        self.lbl_info.clear()
        self._refresh_list()
        self.tables_changed.emit()

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
            description=self.txt_desc.text().strip(),
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
        """Read column definitions from the columns grid."""
        cols = []
        for i in range(self.tbl_columns.rowCount()):
            name_item = self.tbl_columns.item(i, 0)
            name = name_item.text().strip() if name_item else ""
            combo = self.tbl_columns.cellWidget(i, 1)
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
