"""
Add File Datasets dialog — pick File Source member tables for a Visual Query.

Lists every member file of every saved File Source (dataset + its source), so a
query can join file datasets with database tables. Tables already in the query
are left out; the currently selected File Source's members are pre-selected.
"""
from __future__ import annotations

import logging

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QAbstractItemView, QDialog, QHBoxLayout, QLabel, QLineEdit, QPushButton,
    QTreeWidget, QTreeWidgetItem, QVBoxLayout,
)

from suiteview.audit.dialogs.tables_dialog import _BTN_SMALL_STYLE, _BTN_STYLE, _TREE_STYLE
from suiteview.audit.query_sources import list_file_tables

logger = logging.getLogger(__name__)

_ROLE_TOKEN = Qt.ItemDataRole.UserRole


class AddFileTablesDialog(QDialog):
    """Multi-select File Source member tables; ``get_selected()`` → [(token, table)]."""

    def __init__(self, existing: set[str], preferred_token: str = "", parent=None):
        super().__init__(parent)
        self.setWindowTitle("Add File Datasets")
        self.setMinimumSize(460, 380)
        self._selected: list[tuple[str, str]] = []

        lay = QVBoxLayout(self)
        lay.setContentsMargins(8, 8, 8, 8)
        lay.setSpacing(6)

        self.txt_search = QLineEdit()
        self.txt_search.setPlaceholderText("Search datasets or File Sources...")
        self.txt_search.setClearButtonEnabled(True)
        self.txt_search.setFixedHeight(24)
        self.txt_search.textChanged.connect(self._filter)
        lay.addWidget(self.txt_search)

        self.tree = QTreeWidget()
        self.tree.setColumnCount(2)
        self.tree.setHeaderLabels(["Dataset (table)", "File Source"])
        self.tree.setRootIsDecorated(False)
        self.tree.setUniformRowHeights(True)
        self.tree.setStyleSheet(_TREE_STYLE)
        self.tree.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.tree.itemDoubleClicked.connect(lambda _item, _col: self._on_add())
        lay.addWidget(self.tree, 1)

        self.lbl_status = QLabel("")
        self.lbl_status.setStyleSheet("color: #64748B; font-size: 8pt;")
        lay.addWidget(self.lbl_status)

        buttons = QHBoxLayout()
        buttons.addStretch()
        self.btn_add = QPushButton("Add Selected")
        self.btn_add.setStyleSheet(_BTN_STYLE)
        self.btn_add.clicked.connect(self._on_add)
        buttons.addWidget(self.btn_add)
        btn_cancel = QPushButton("Cancel")
        btn_cancel.setStyleSheet(_BTN_SMALL_STYLE)
        btn_cancel.clicked.connect(self.reject)
        buttons.addWidget(btn_cancel)
        lay.addLayout(buttons)

        self._load(existing, preferred_token)

    def _load(self, existing: set[str], preferred_token: str):
        try:
            rows = list_file_tables()
        except Exception:
            logger.exception("Could not list File Sources for Add File Datasets")
            rows = []
        count = 0
        for label, token, table in sorted(rows, key=lambda r: (r[0].lower(), r[2].lower())):
            if table in existing:
                continue
            item = QTreeWidgetItem([table, label])
            item.setData(0, _ROLE_TOKEN, token)
            item.setToolTip(0, f"{table}\n{label}")
            self.tree.addTopLevelItem(item)
            if preferred_token and token == preferred_token:
                item.setSelected(True)
            count += 1
        self.tree.resizeColumnToContents(0)
        if count:
            self.lbl_status.setText(f"{count} datasets available — Ctrl/Shift-click to pick several")
        elif rows:
            self.lbl_status.setText("Every file dataset is already in this query.")
        else:
            self.lbl_status.setText("No File Sources yet — create one in Objects › File Sources.")
        self.btn_add.setEnabled(bool(count))

    def _filter(self, text: str):
        needle = text.strip().lower()
        for index in range(self.tree.topLevelItemCount()):
            item = self.tree.topLevelItem(index)
            hay = f"{item.text(0)} {item.text(1)}".lower()
            item.setHidden(bool(needle) and needle not in hay)

    def _on_add(self):
        self._selected = [
            (str(item.data(0, _ROLE_TOKEN)), item.text(0))
            for item in self.tree.selectedItems()
            if not item.isHidden()
        ]
        self.accept()

    def get_selected(self) -> list[tuple[str, str]]:
        return list(self._selected)
