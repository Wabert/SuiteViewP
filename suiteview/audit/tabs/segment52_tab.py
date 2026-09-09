"""52-G application/conversion criteria and optional result columns."""
from __future__ import annotations

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QFont
from PyQt6.QtWidgets import (
    QCheckBox, QComboBox, QGridLayout, QLabel, QLineEdit, QPushButton,
    QVBoxLayout, QWidget,
)

from suiteview.ui.widgets.uppercase_input import force_uppercase
from ..segment52_fields import SEGMENT52_FIELDS
from ._styles import make_checkbox, make_combo
from .people_tab import NAME_MATCH_ITEMS


class Segment52Tab(QWidget):
    """Inclusive ranges and text matching on TH_USER_GENERIC."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.display_fields: dict[str, QCheckBox] = {}
        self.ranges: dict[str, tuple[QLineEdit, QLineEdit]] = {}
        self.text_inputs: dict[str, QLineEdit] = {}
        self.match_types: dict[str, QComboBox] = {}
        root = QVBoxLayout(self)
        root.setContentsMargins(6, 6, 6, 4)
        root.setSpacing(4)
        title = QLabel("52-G: Application / Conversion (TH_USER_GENERIC)")
        title.setFont(QFont("Segoe UI", 10, QFont.Weight.Bold))
        root.addWidget(title)
        note = QLabel(
            "Ranges include both endpoints; either endpoint may be left blank. "
            "Criteria also display that field. Display alone keeps policies without "
            "52-G data (blank values)."
        )
        note.setWordWrap(True)
        note.setMaximumWidth(850)
        root.addWidget(note)

        grid = QGridLayout()
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setHorizontalSpacing(6)
        grid.setVerticalSpacing(2)
        for col, text in enumerate(("Display", "Field", "From / Match", "To / Value")):
            label = QLabel(text)
            label.setFont(QFont("Segoe UI", 9, QFont.Weight.Bold))
            grid.addWidget(label, 0, col)

        def entry(placeholder: str) -> QLineEdit:
            widget = QLineEdit()
            widget.setFont(QFont("Segoe UI", 9))
            widget.setFixedSize(140, 22)
            widget.setPlaceholderText(placeholder)
            return widget

        for row, field in enumerate(SEGMENT52_FIELDS, 1):
            show = make_checkbox("")
            show.setToolTip(f"Display {field.name} without filtering policies")
            self.display_fields[field.name] = show
            label = QLabel(field.name)
            label.setFont(QFont("Segoe UI", 9))
            label.setToolTip(f"{field.label}\nTH_USER_GENERIC.{field.name}")
            grid.addWidget(show, row, 0, alignment=Qt.AlignmentFlag.AlignCenter)
            grid.addWidget(label, row, 1)
            if field.kind == "text":
                match = make_combo(NAME_MATCH_ITEMS, width=140)
                value = entry("Any")
                force_uppercase(value)
                self.match_types[field.name] = match
                self.text_inputs[field.name] = value
                grid.addWidget(match, row, 2)
                grid.addWidget(value, row, 3)
            else:
                placeholder = "MM/DD/YYYY" if field.kind == "date" else "Any"
                lo, hi = entry(placeholder), entry(placeholder)
                hint = ("MM/DD/YYYY or YYYY-MM-DD" if field.kind == "date" else
                        "Whole number" if field.kind == "integer" else
                        "Number without commas (e.g. 100000.00)")
                for widget in (lo, hi):
                    widget.setToolTip(f"{field.label}: {hint}")
                self.ranges[field.name] = (lo, hi)
                grid.addWidget(lo, row, 2)
                grid.addWidget(hi, row, 3)
        grid.setColumnStretch(4, 1)
        root.addLayout(grid)
        select_all = QPushButton("Display all 52-G fields")
        select_all.setFixedHeight(22)
        select_all.clicked.connect(self._display_all)
        root.addWidget(select_all, alignment=Qt.AlignmentFlag.AlignLeft)
        root.addStretch()

    def _display_all(self):
        for checkbox in self.display_fields.values():
            checkbox.setChecked(True)

    def get_state(self) -> dict:
        fields = {}
        for field in SEGMENT52_FIELDS:
            values = {"display": self.display_fields[field.name].isChecked()}
            if field.kind == "text":
                values["match"] = self.match_types[field.name].currentText()
                values["value"] = self.text_inputs[field.name].text().strip().upper()
            else:
                lo, hi = self.ranges[field.name]
                values.update(lo=lo.text().strip(), hi=hi.text().strip())
            fields[field.name] = values
        return {"fields": fields}

    def set_state(self, state: dict):
        fields = state.get("fields", {})
        for field in SEGMENT52_FIELDS:
            values = fields.get(field.name, {})
            self.display_fields[field.name].setChecked(values.get("display", False))
            if field.kind == "text":
                self.match_types[field.name].setCurrentText(values.get("match", NAME_MATCH_ITEMS[0]))
                self.text_inputs[field.name].setText(values.get("value", ""))
            else:
                lo, hi = self.ranges[field.name]
                lo.setText(values.get("lo", ""))
                hi.setText(values.get("hi", ""))
