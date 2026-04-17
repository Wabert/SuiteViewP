"""
Create Group Dialog — ODBC DSN picker + table selector + group naming.

Flow:
  1. User selects an ODBC DSN from a searchable list
  2. Tables from that DSN are loaded and shown in a searchable, multi-select list
  3. User names the group
  4. Returns (group_name, dsn, [table_names])
"""
from __future__ import annotations

import logging

import pyodbc
from PyQt6.QtCore import Qt, QThread, pyqtSignal
from PyQt6.QtGui import QFont
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
    QListWidget, QAbstractItemView, QPushButton, QMessageBox,
    QApplication, QSplitter, QGroupBox, QWidget,
)

from ..tabs._styles import TightItemDelegate

logger = logging.getLogger(__name__)

_FONT = QFont("Segoe UI", 9)

_BTN_STYLE = (
    "QPushButton { background-color: #1E5BA8; color: white;"
    " border: 1px solid #14407A; border-radius: 3px;"
    " padding: 4px 16px; font-size: 9pt; }"
    "QPushButton:hover { background-color: #2A6BC4; }"
    "QPushButton:disabled { background-color: #A0A0A0;"
    " border: 1px solid #888; }"
)

_LIST_STYLE = (
    "QListWidget { border: 1px solid #1E5BA8; background-color: white;"
    " font-size: 8pt; outline: none; }"
    "QListWidget::item { padding: 0px 4px; }"
    "QListWidget::item:selected { background-color: #A0C4E8; color: black; }"
    "QListWidget::item:focus { outline: none; border: none; }"
)


class _TableLoaderThread(QThread):
    """Background thread to fetch table names from an ODBC DSN."""
    tables_loaded = pyqtSignal(list)
    error_occurred = pyqtSignal(str)

    def __init__(self, dsn: str, parent=None):
        super().__init__(parent)
        self.dsn = dsn

    def run(self):
        try:
            conn = pyodbc.connect(f"DSN={self.dsn}", autocommit=True, timeout=15)
            cursor = conn.cursor()
            tables = []
            try:
                rows = cursor.tables()
                while True:
                    try:
                        row = next(rows)
                    except StopIteration:
                        break
                    except Exception:
                        continue  # skip rows that cause conversion errors
                    if row.table_type in ("TABLE", "VIEW"):
                        schema = row.table_schem or ""
                        name = row.table_name
                        full = f"{schema}.{name}" if schema else name
                        tables.append(full)
            except Exception as exc:
                logger.warning("Error iterating tables for %s: %s",
                               self.dsn, exc)
            conn.close()
            self.tables_loaded.emit(sorted(tables))
        except Exception as exc:
            self.error_occurred.emit(str(exc))


class CreateGroupDialog(QDialog):
    """Dialog to create a new dynamic audit group."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Create New Group")
        self.setMinimumSize(700, 500)
        self.setFont(_FONT)

        self._selected_dsn: str = ""
        self._tables: list[str] = []
        self._loader: _TableLoaderThread | None = None

        self._result_name: str = ""
        self._result_dsn: str = ""
        self._result_tables: list[str] = []

        self._build_ui()

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setSpacing(8)

        # ── Group name ───────────────────────────────────────────────
        name_row = QHBoxLayout()
        name_row.addWidget(QLabel("Group Name:"))
        self.txt_name = QLineEdit()
        self.txt_name.setPlaceholderText("Enter a name for this group...")
        self.txt_name.setFixedHeight(24)
        name_row.addWidget(self.txt_name)
        root.addLayout(name_row)

        # ── Splitter: DSN list | Table list ──────────────────────────
        splitter = QSplitter(Qt.Orientation.Horizontal)

        # Left: DSN selection
        dsn_box = QGroupBox("ODBC Data Sources")
        dsn_lay = QVBoxLayout(dsn_box)
        dsn_lay.setSpacing(4)

        self.txt_dsn_search = QLineEdit()
        self.txt_dsn_search.setPlaceholderText("Search DSNs...")
        self.txt_dsn_search.setClearButtonEnabled(True)
        self.txt_dsn_search.setFixedHeight(24)
        self.txt_dsn_search.textChanged.connect(self._filter_dsns)
        dsn_lay.addWidget(self.txt_dsn_search)

        self.list_dsn = QListWidget()
        self.list_dsn.setStyleSheet(_LIST_STYLE)
        self.list_dsn.setFont(QFont("Segoe UI", 8))
        self.list_dsn.setItemDelegate(TightItemDelegate(self.list_dsn))
        self.list_dsn.setUniformItemSizes(True)
        self.list_dsn.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.list_dsn.currentItemChanged.connect(self._on_dsn_selected)
        dsn_lay.addWidget(self.list_dsn)

        splitter.addWidget(dsn_box)

        # Right: Table selection
        table_box = QGroupBox("Tables")
        table_lay = QVBoxLayout(table_box)
        table_lay.setSpacing(4)

        self.txt_table_search = QLineEdit()
        self.txt_table_search.setPlaceholderText("Search tables...")
        self.txt_table_search.setClearButtonEnabled(True)
        self.txt_table_search.setFixedHeight(24)
        self.txt_table_search.textChanged.connect(self._filter_tables)
        table_lay.addWidget(self.txt_table_search)

        self.list_tables = QListWidget()
        self.list_tables.setStyleSheet(_LIST_STYLE)
        self.list_tables.setFont(QFont("Segoe UI", 8))
        self.list_tables.setItemDelegate(TightItemDelegate(self.list_tables))
        self.list_tables.setUniformItemSizes(True)
        self.list_tables.setSelectionMode(
            QAbstractItemView.SelectionMode.MultiSelection)
        table_lay.addWidget(self.list_tables)

        self.lbl_table_status = QLabel("")
        self.lbl_table_status.setFont(QFont("Segoe UI", 8))
        self.lbl_table_status.setStyleSheet("color: #666;")
        table_lay.addWidget(self.lbl_table_status)

        splitter.addWidget(table_box)
        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 2)

        root.addWidget(splitter, 1)

        # ── Buttons ──────────────────────────────────────────────────
        btn_row = QHBoxLayout()
        btn_row.addStretch()

        self.btn_create = QPushButton("Create Group")
        self.btn_create.setStyleSheet(_BTN_STYLE)
        self.btn_create.setFixedHeight(30)
        self.btn_create.clicked.connect(self._on_create)
        btn_row.addWidget(self.btn_create)

        self.btn_cancel = QPushButton("Cancel")
        self.btn_cancel.setFixedHeight(30)
        self.btn_cancel.clicked.connect(self.reject)
        btn_row.addWidget(self.btn_cancel)

        root.addLayout(btn_row)

        # ── Populate DSNs ────────────────────────────────────────────
        self._populate_dsns()

    def _populate_dsns(self):
        """List all system and user ODBC DSNs."""
        self._all_dsns: list[str] = []
        try:
            for dsn_info in pyodbc.dataSources().items():
                self._all_dsns.append(dsn_info[0])
        except Exception:
            logger.exception("Failed to list ODBC data sources")
        self._all_dsns.sort(key=str.lower)
        self.list_dsn.clear()
        self.list_dsn.addItems(self._all_dsns)

    def _filter_dsns(self, text: str):
        filt = text.strip().lower()
        for i in range(self.list_dsn.count()):
            item = self.list_dsn.item(i)
            item.setHidden(filt not in item.text().lower() if filt else False)

    def _filter_tables(self, text: str):
        filt = text.strip().lower()
        for i in range(self.list_tables.count()):
            item = self.list_tables.item(i)
            item.setHidden(filt not in item.text().lower() if filt else False)

    def _on_dsn_selected(self, current, previous):
        if current is None:
            return
        dsn = current.text()
        if dsn == self._selected_dsn:
            return
        self._selected_dsn = dsn
        self._load_tables(dsn)

    def _load_tables(self, dsn: str):
        self.list_tables.clear()
        self.lbl_table_status.setText("Loading tables...")
        self.list_tables.setEnabled(False)

        self._loader = _TableLoaderThread(dsn, self)
        self._loader.tables_loaded.connect(self._on_tables_loaded)
        self._loader.error_occurred.connect(self._on_tables_error)
        self._loader.start()

    def _on_tables_loaded(self, tables: list[str]):
        self._tables = tables
        self.list_tables.clear()
        self.list_tables.addItems(tables)
        self.list_tables.setEnabled(True)
        self.lbl_table_status.setText(f"{len(tables)} tables found")
        self._loader = None

    def _on_tables_error(self, msg: str):
        self.list_tables.setEnabled(True)
        self.lbl_table_status.setText("Error loading tables")
        QMessageBox.warning(self, "Connection Error",
                            f"Failed to connect to {self._selected_dsn}:\n\n{msg}")
        self._loader = None

    def _on_create(self):
        name = self.txt_name.text().strip()
        if not name:
            QMessageBox.warning(self, "Missing Name",
                                "Please enter a group name.")
            return
        if not self._selected_dsn:
            QMessageBox.warning(self, "No DSN Selected",
                                "Please select an ODBC data source.")
            return
        selected = [self.list_tables.item(i).text()
                    for i in range(self.list_tables.count())
                    if self.list_tables.item(i).isSelected()]
        if not selected:
            QMessageBox.warning(self, "No Tables Selected",
                                "Please select at least one table.")
            return

        self._result_name = name
        self._result_dsn = self._selected_dsn
        self._result_tables = selected
        self.accept()

    def get_result(self) -> tuple[str, str, list[str]]:
        """Return (group_name, dsn, [table_names]) after accept."""
        return self._result_name, self._result_dsn, self._result_tables
