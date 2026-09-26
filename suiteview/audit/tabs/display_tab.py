"""Display tab generated from declarative criteria specs."""
from __future__ import annotations

from PyQt6.QtGui import QFont
from PyQt6.QtWidgets import (
    QCheckBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QVBoxLayout,
    QWidget,
)

from suiteview.audit.criteria_specs import DISPLAY_TAB_SPEC, apply_tab_state, tab_state

from ._styles import make_checkbox

_V_SPACING = 2

_TOOLTIPS = {
    "chk_post_conversion": (
        "For last entry code O, find destination policies whose conversion "
        "record names this policy and source company, within the same system. "
        "Shows destination policy number and company; unmatched policies stay "
        "in the results with blanks. Multiple destinations appear on separate rows."
    ),
    "chk_conversion_dates": (
        "Entry and effective dates from the latest non-reversed SC transaction "
        "for policies whose last entry code is O (Termination - Conversion). "
        "Latest is by entry date, time, then sequence; both reversal flags must "
        "be 0. Other policies remain in the results with blank dates."
    ),
}


def _spacer() -> QWidget:
    widget = QWidget()
    widget.setFixedHeight(8)
    return widget


def _vsep() -> QFrame:
    frame = QFrame()
    frame.setFrameShape(QFrame.Shape.VLine)
    frame.setFrameShadow(QFrame.Shadow.Sunken)
    return frame


class DisplayTab(QWidget):
    """Display tab — checkboxes for additional result columns."""

    spec = DISPLAY_TAB_SPEC

    def __init__(self, parent=None):
        super().__init__(parent)
        self._build_ui()

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(6, 6, 6, 4)
        root.setSpacing(4)

        hdr = QLabel("Select additional data items to display in the results")
        hdr.setFont(QFont("Segoe UI", 10, QFont.Weight.Bold))
        hdr.setStyleSheet("color: #333;")
        root.addWidget(hdr)

        columns = QHBoxLayout()
        columns.setSpacing(8)
        by_column = self._fields_by_column()
        for column in range(1, 6):
            columns.addLayout(self._build_column(by_column[column]))
            if column != 5:
                columns.addWidget(_vsep())
        root.addLayout(columns, 1)

    def _fields_by_column(self) -> dict[int, list]:
        grouped = {column: [] for column in range(1, 6)}
        for field in self.spec.fields:
            grouped[int(field.layout_hints["column"])].append(field)
        return grouped

    def _build_column(self, fields: list) -> QVBoxLayout:
        layout = QVBoxLayout()
        layout.setSpacing(_V_SPACING)
        last_group = None
        for field in fields:
            group = field.layout_hints.get("group")
            if last_group is not None and group != last_group:
                layout.addWidget(_spacer())
            checkbox = make_checkbox(field.label)
            if field.key in _TOOLTIPS:
                checkbox.setToolTip(_TOOLTIPS[field.key])
            setattr(self, field.key, checkbox)
            layout.addWidget(checkbox)
            last_group = group
        layout.addStretch()
        return layout

    def _all_checkboxes(self) -> list[tuple[str, QCheckBox]]:
        return [
            (field.key, getattr(self, field.key))
            for field in self.spec.fields
        ]

    def get_state(self) -> dict:
        return tab_state(self, self.spec)

    def set_state(self, state: dict) -> None:
        apply_tab_state(self, self.spec, state)
