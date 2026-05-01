"""
Common Tables tab — lets users select which Common Tables to include
in the current query as CTEs.

Appears as a tab in the QDesigner tab widget. Selected tables become
available as joinable/queryable tables in the SQL output.
"""
from __future__ import annotations

import logging

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QFont
from PyQt6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from suiteview.audit import common_table_store
from suiteview.audit.common_table import CommonTable

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

_LIST_STYLE = (
    "QListWidget { border: 1px solid #1E5BA8; background-color: white;"
    " font-size: 9pt; outline: none; }"
    "QListWidget::item:selected { background-color: #A0C4E8; color: black; }"
    "QListWidget::item:hover { background-color: #D6E8FA; }"
)


class CommonTablesTab(QWidget):
    """Tab for selecting Common Tables to include in a query."""

    state_changed = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFont(_FONT)
        self._build_ui()

    def _build_ui(self):
        root = QHBoxLayout(self)
        root.setContentsMargins(8, 8, 8, 8)
        root.setSpacing(12)

        # ── Left: available tables ───────────────────────────────
        left = QVBoxLayout()
        left.setSpacing(4)
        lbl_avail = QLabel("Available Common Tables")
        lbl_avail.setFont(_FONT_BOLD)
        left.addWidget(lbl_avail)

        self.lst_available = QListWidget()
        self.lst_available.setStyleSheet(_LIST_STYLE)
        self.lst_available.setSelectionMode(
            QListWidget.SelectionMode.ExtendedSelection
        )
        left.addWidget(self.lst_available)
        root.addLayout(left, 1)

        # ── Center: add/remove buttons ───────────────────────────
        center = QVBoxLayout()
        center.setSpacing(6)
        center.addStretch()

        btn_add = QPushButton("Add ▶")
        btn_add.setStyleSheet(_BTN_STYLE)
        btn_add.setFixedWidth(80)
        btn_add.clicked.connect(self._on_add)
        center.addWidget(btn_add)

        btn_remove = QPushButton("◀ Remove")
        btn_remove.setStyleSheet(_BTN_STYLE)
        btn_remove.setFixedWidth(80)
        btn_remove.clicked.connect(self._on_remove)
        center.addWidget(btn_remove)

        center.addSpacing(20)

        btn_refresh = QPushButton("Refresh")
        btn_refresh.setStyleSheet(_BTN_STYLE)
        btn_refresh.setFixedWidth(80)
        btn_refresh.clicked.connect(self.refresh_available)
        center.addWidget(btn_refresh)

        btn_manage = QPushButton("Manage…")
        btn_manage.setStyleSheet(_BTN_STYLE)
        btn_manage.setFixedWidth(80)
        btn_manage.clicked.connect(self._on_manage)
        center.addWidget(btn_manage)

        center.addStretch()
        root.addLayout(center)

        # ── Right: selected (included) tables ────────────────────
        right = QVBoxLayout()
        right.setSpacing(4)
        lbl_sel = QLabel("Included in Query")
        lbl_sel.setFont(_FONT_BOLD)
        right.addWidget(lbl_sel)

        self.lst_selected = QListWidget()
        self.lst_selected.setStyleSheet(_LIST_STYLE)
        self.lst_selected.setSelectionMode(
            QListWidget.SelectionMode.ExtendedSelection
        )
        right.addWidget(self.lst_selected)

        # Info label showing columns of selected table
        self.lbl_columns = QLabel("")
        self.lbl_columns.setStyleSheet("color: #666; font-size: 8pt;")
        self.lbl_columns.setWordWrap(True)
        right.addWidget(self.lbl_columns)
        self.lst_selected.currentTextChanged.connect(self._on_selected_changed)

        root.addLayout(right, 1)

        # Initial load
        self.refresh_available()

    # ── Public API ───────────────────────────────────────────────

    def refresh_available(self):
        """Reload the available tables list from disk."""
        selected_names = self._get_selected_names()
        self.lst_available.clear()
        for ct in common_table_store.list_tables():
            if ct.name not in selected_names:
                item = QListWidgetItem(ct.name)
                item.setToolTip(
                    f"{ct.description}\n"
                    f"Columns: {', '.join(ct.column_names)}\n"
                    f"Rows: {ct.row_count}"
                )
                self.lst_available.addItem(item)

    def get_selected_tables(self) -> list[CommonTable]:
        """Return the CommonTable objects for all selected (included) tables."""
        tables: list[CommonTable] = []
        for i in range(self.lst_selected.count()):
            name = self.lst_selected.item(i).text()
            ct = common_table_store.load_table(name)
            if ct:
                tables.append(ct)
        return tables

    def get_state(self) -> dict:
        """Serialize selected table names for config save."""
        return {
            "selected_tables": self._get_selected_names(),
        }

    def set_state(self, state: dict):
        """Restore from saved config."""
        names = state.get("selected_tables", [])
        self.lst_selected.clear()
        for name in names:
            if common_table_store.table_exists(name):
                self.lst_selected.addItem(name)
        self.refresh_available()
        self.state_changed.emit()

    # ── Actions ──────────────────────────────────────────────────

    def _on_add(self):
        for item in self.lst_available.selectedItems():
            name = item.text()
            # Move to selected list
            self.lst_selected.addItem(name)
        self.refresh_available()
        self.state_changed.emit()

    def _on_remove(self):
        for item in self.lst_selected.selectedItems():
            row = self.lst_selected.row(item)
            self.lst_selected.takeItem(row)
        self.refresh_available()
        self.state_changed.emit()

    def _on_manage(self):
        """Open the Common Table Manager dialog."""
        from suiteview.audit.common_table_dialog import CommonTableDialog
        dlg = CommonTableDialog.show_instance(self)
        dlg.tables_changed.connect(self.refresh_available)

    def _on_selected_changed(self, name: str):
        """Show column info when a selected table is clicked."""
        if not name:
            self.lbl_columns.clear()
            return
        ct = common_table_store.load_table(name)
        if ct:
            cols = ", ".join(
                f"{c['name']} ({c['type']})" for c in ct.columns
            )
            self.lbl_columns.setText(
                f"Columns: {cols}  |  {ct.row_count} rows"
            )
        else:
            self.lbl_columns.setText("(table not found)")

    # ── Helpers ──────────────────────────────────────────────────

    def _get_selected_names(self) -> list[str]:
        return [
            self.lst_selected.item(i).text()
            for i in range(self.lst_selected.count())
        ]
