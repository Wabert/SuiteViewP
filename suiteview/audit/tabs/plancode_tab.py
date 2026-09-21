"""Side-by-side plancode and policy-number lists for the audit query."""
from __future__ import annotations

import re

from PyQt6.QtCore import QSize
from PyQt6.QtGui import QFont
from PyQt6.QtWidgets import (
    QApplication, QAbstractItemView, QHBoxLayout, QLabel,
    QLineEdit, QListWidget, QPushButton, QStyledItemDelegate, QVBoxLayout,
    QWidget,
)

from suiteview.ui.widgets.uppercase_input import force_uppercase
from ._styles import make_checkbox

_FONT = QFont("Segoe UI", 9)
_ROW_H = 16
_CTRL_H = 22


class _TightItemDelegate(QStyledItemDelegate):
    def sizeHint(self, option, index):
        sh = super().sizeHint(option, index)
        return QSize(sh.width(), _ROW_H)


class _IdentifierListPanel(QWidget):
    """Shared add/remove/clipboard controls for exact identifier lists."""

    def __init__(self, title: str, input_label: str, extra_control=None, parent=None):
        super().__init__(parent)
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(4)
        heading = QLabel(title)
        heading.setFont(_FONT)
        heading.setStyleSheet("color: #1E5BA8; font-weight: bold;")
        root.addWidget(heading)
        body = QHBoxLayout()
        body.setSpacing(8)
        root.addLayout(body, 1)
        controls = QVBoxLayout()
        controls.setSpacing(2)
        row = QHBoxLayout()
        row.setSpacing(4)
        label = QLabel(input_label)
        label.setFont(_FONT)
        self.input = QLineEdit()
        self.input.setFont(_FONT)
        self.input.setFixedSize(100, _CTRL_H)
        force_uppercase(self.input)
        row.addWidget(label)
        row.addWidget(self.input)
        row.addStretch()
        controls.addLayout(row)
        controls.addSpacing(8)

        self.btn_add = QPushButton("Add -->")
        self.btn_remove_selected = QPushButton("Remove Selected")
        self.btn_remove_all = QPushButton("Remove All")
        self.btn_paste = QPushButton("Paste from\nClipboard")
        for button in (
            self.btn_add, self.btn_remove_selected, self.btn_remove_all, self.btn_paste,
        ):
            button.setFont(_FONT)
            button.setFixedSize(120, 40 if button is self.btn_paste else 26)
        controls.addWidget(self.btn_add)
        if extra_control is not None:
            extra_control.setFixedHeight(_CTRL_H)
            controls.addWidget(extra_control)
        else:
            placeholder = QWidget()
            placeholder.setFixedHeight(_CTRL_H)
            controls.addWidget(placeholder)
        controls.addSpacing(4)
        controls.addWidget(self.btn_remove_selected)
        controls.addWidget(self.btn_remove_all)
        controls.addSpacing(24)
        controls.addWidget(self.btn_paste)
        controls.addStretch()
        body.addLayout(controls)

        self.list_values = QListWidget()
        self.list_values.setFont(_FONT)
        self.list_values.setItemDelegate(_TightItemDelegate(self.list_values))
        self.list_values.setUniformItemSizes(True)
        self.list_values.setSelectionMode(
            QAbstractItemView.SelectionMode.ExtendedSelection
        )
        self.list_values.setStyleSheet(
            "QListWidget { border: 1px solid #1E5BA8; background-color: white; }"
            "QListWidget::item { padding: 0px 2px; border: none; }"
            "QListWidget::item:selected { background-color: #A0C4E8; color: black; border: none; }"
        )
        self.list_values.setMinimumWidth(120)
        body.addWidget(self.list_values, 1)

        self.btn_add.clicked.connect(self._add_input)
        self.input.returnPressed.connect(self._add_input)
        self.btn_remove_selected.clicked.connect(self._remove_selected)
        self.btn_remove_all.clicked.connect(self.list_values.clear)
        self.btn_paste.clicked.connect(self._paste_from_clipboard)
        self.btn_paste.setToolTip(
            "Paste identifiers separated by lines, tabs, commas, semicolons or spaces. "
            "Duplicates are ignored; leading zeros are kept."
        )

    def _append_values(self, values: list[str]):
        existing = set(self.values())
        for value in values:
            code = value.strip().upper()
            if code and code not in existing:
                self.list_values.addItem(code)
                existing.add(code)

    def _add_input(self):
        self._append_values([self.input.text()])
        self.input.clear()
        self.input.setFocus()

    def _remove_selected(self):
        for item in self.list_values.selectedItems():
            self.list_values.takeItem(self.list_values.row(item))

    def _paste_from_clipboard(self):
        clipboard = QApplication.clipboard()
        if clipboard is not None:
            self._append_values(re.split(r"[\s,;]+", clipboard.text()))

    def values(self) -> list[str]:
        return [
            self.list_values.item(i).text().strip().upper()
            for i in range(self.list_values.count())
        ]

    def set_values(self, values: list[str]):
        self.input.clear()
        self.list_values.clear()
        self._append_values(values)


class PlancodeTab(QWidget):
    """Plans and Policies criteria, combined with each other and other tabs."""

    def __init__(self, parent=None):
        super().__init__(parent)
        root = QHBoxLayout(self)
        root.setContentsMargins(8, 8, 8, 8)
        root.setSpacing(12)
        self.chk_cov1_plancode_match_only = make_checkbox("Cov1 plancode match only")
        self.plancodes = _IdentifierListPanel(
            "Plancode", "Plancode", self.chk_cov1_plancode_match_only,
        )
        self.policies = _IdentifierListPanel("Policies", "Policy number")
        root.addWidget(self.plancodes, 1)
        root.addWidget(self.policies, 1)
        self.policies.setToolTip(
            "Match any policy number in this list exactly, together with all other "
            "active query criteria. An empty list adds no restriction."
        )

    def get_plancodes(self) -> list[str]:
        return self.plancodes.values()

    def get_policies(self) -> list[str]:
        return self.policies.values()

    def cov1_plancode_match_only(self) -> bool:
        return self.chk_cov1_plancode_match_only.isChecked()

    def get_state(self) -> dict:
        return {
            "plancodes": self.get_plancodes(),
            "policies": self.get_policies(),
            "cov1_plancode_match_only": self.cov1_plancode_match_only(),
        }

    def set_state(self, state: dict):
        self.plancodes.set_values(state.get("plancodes", []))
        self.policies.set_values(state.get("policies", []))
        self.chk_cov1_plancode_match_only.setChecked(
            bool(state.get("cov1_plancode_match_only", False))
        )
