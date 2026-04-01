"""
Plancode tab — lets users build a list of plancodes to filter the audit query.

Layout:
  LEFT column:   Plancode label + input + "Add -->" button
                 "Remove Selected" button
                 "Remove All" button
                 "Paste from Clipboard" button
  RIGHT column:  QListWidget showing added plancodes
"""
from __future__ import annotations

from PyQt6.QtCore import Qt, QSize
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QLineEdit, QPushButton,
    QListWidget, QAbstractItemView, QStyledItemDelegate,
    QApplication,
)
from PyQt6.QtGui import QFont

_FONT = QFont("Segoe UI", 9)
_ROW_H = 16
_CTRL_H = 22
_V_SPACING = 2
_H_SPACING = 4


class _TightItemDelegate(QStyledItemDelegate):
    ROW_H = _ROW_H

    def sizeHint(self, option, index):
        sh = super().sizeHint(option, index)
        return QSize(sh.width(), self.ROW_H)


class PlancodeTab(QWidget):
    """Plancode multi-select tab — add plancodes individually or paste from clipboard."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._build_ui()

    def _build_ui(self):
        root = QHBoxLayout(self)
        root.setContentsMargins(8, 8, 8, 8)
        root.setSpacing(12)

        # ── LEFT: input + buttons ────────────────────────────────────
        left = QVBoxLayout()
        left.setSpacing(_V_SPACING)

        # Plancode input row
        row = QHBoxLayout()
        row.setSpacing(_H_SPACING)
        lbl = QLabel("Plancode")
        lbl.setFont(_FONT)
        self.txt_plancode = QLineEdit()
        self.txt_plancode.setFont(_FONT)
        self.txt_plancode.setFixedSize(80, _CTRL_H)
        row.addWidget(lbl)
        row.addWidget(self.txt_plancode)
        row.addStretch()
        left.addLayout(row)

        left.addSpacing(8)

        # Add button
        self.btn_add = QPushButton("Add -->")
        self.btn_add.setFont(_FONT)
        self.btn_add.setFixedSize(120, 26)
        left.addWidget(self.btn_add)

        left.addSpacing(4)

        # Remove Selected button
        self.btn_remove_selected = QPushButton("Remove Selected")
        self.btn_remove_selected.setFont(_FONT)
        self.btn_remove_selected.setFixedSize(120, 26)
        left.addWidget(self.btn_remove_selected)

        # Remove All button
        self.btn_remove_all = QPushButton("Remove All")
        self.btn_remove_all.setFont(_FONT)
        self.btn_remove_all.setFixedSize(120, 26)
        left.addWidget(self.btn_remove_all)

        left.addSpacing(24)

        # Paste from Clipboard button
        self.btn_paste = QPushButton("Paste from\nClipboard")
        self.btn_paste.setFont(_FONT)
        self.btn_paste.setFixedSize(120, 40)
        left.addWidget(self.btn_paste)

        left.addStretch()
        root.addLayout(left)

        # ── RIGHT: plancode list ─────────────────────────────────────
        self.list_plancodes = QListWidget()
        self.list_plancodes.setFont(_FONT)
        self.list_plancodes.setItemDelegate(_TightItemDelegate(self.list_plancodes))
        self.list_plancodes.setUniformItemSizes(True)
        self.list_plancodes.setSelectionMode(
            QAbstractItemView.SelectionMode.ExtendedSelection
        )
        self.list_plancodes.setStyleSheet(
            "QListWidget { border: 1px solid #1E5BA8; background-color: white; }"
            "QListWidget::item { padding: 0px 2px; border: none; }"
            "QListWidget::item:selected { background-color: #A0C4E8; color: black; border: none; }"
        )
        self.list_plancodes.setMinimumWidth(120)
        root.addWidget(self.list_plancodes, 1)  # stretch=1

        # ── Connect signals ──────────────────────────────────────────
        self.btn_add.clicked.connect(self._add_plancode)
        self.txt_plancode.returnPressed.connect(self._add_plancode)
        self.btn_remove_selected.clicked.connect(self._remove_selected)
        self.btn_remove_all.clicked.connect(self._remove_all)
        self.btn_paste.clicked.connect(self._paste_from_clipboard)

    # ── Actions ──────────────────────────────────────────────────────

    def _add_plancode(self):
        """Add the typed plancode to the list (if non-empty and not duplicate)."""
        code = self.txt_plancode.text().strip().upper()
        if not code:
            return
        # Avoid duplicates
        existing = self.get_plancodes()
        if code not in existing:
            self.list_plancodes.addItem(code)
        self.txt_plancode.clear()
        self.txt_plancode.setFocus()

    def _remove_selected(self):
        """Remove all selected items from the list."""
        for item in reversed(self.list_plancodes.selectedItems()):
            self.list_plancodes.takeItem(self.list_plancodes.row(item))

    def _remove_all(self):
        """Clear the entire plancode list."""
        self.list_plancodes.clear()

    def _paste_from_clipboard(self):
        """Parse clipboard text and add each plancode found.

        Handles newline-separated, comma-separated, tab-separated,
        or space-separated values (e.g. pasted from Excel column).
        """
        clipboard = QApplication.clipboard()
        if clipboard is None:
            return
        text = clipboard.text()
        if not text:
            return

        existing = set(self.get_plancodes())
        # Split on common delimiters: newline, comma, tab, semicolon
        import re
        tokens = re.split(r'[\n\r,;\t]+', text)
        for token in tokens:
            code = token.strip().upper()
            if code and code not in existing:
                self.list_plancodes.addItem(code)
                existing.add(code)

    # ── Public API ───────────────────────────────────────────────────

    def get_plancodes(self) -> list[str]:
        """Return the list of plancodes currently in the list widget."""
        return [
            self.list_plancodes.item(i).text()
            for i in range(self.list_plancodes.count())
        ]

    # ── Profile save/load ────────────────────────────────────────────
    def get_state(self) -> dict:
        return {"plancodes": self.get_plancodes()}

    def set_state(self, state: dict):
        self.list_plancodes.clear()
        for code in state.get("plancodes", []):
            self.list_plancodes.addItem(code)
