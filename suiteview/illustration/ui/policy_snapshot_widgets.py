"""Policy-page building blocks shared by the fixed-premium RERUN workspaces.

The par whole life and indeterminate premium term Policy pages show the in-force
snapshot the same way as RERUN's UL Policy tab: purple ``GROUP_STYLE`` panels, a
coverages table in PolView's columns sized to its rows, and the supplemental benefits
as form-number buttons that open the shared Benefit Detail card.
"""
from __future__ import annotations

from typing import List, Optional, Sequence, Tuple

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QGroupBox, QHBoxLayout, QLabel, QPushButton, QVBoxLayout

from suiteview.polview.ui.widgets import StyledInfoTableGroup

from .policy_tab import show_detail_dialog
from .styles import FUND_TABLE_STYLE, GROUP_STYLE, PURPLE_DARK, VALUE_BUTTON_STYLE

# (button label, tooltip, detail card rows)
BenefitButton = Tuple[str, str, List[tuple]]


def money(value: Optional[float]) -> str:
    return "" if value is None else f"{value:,.2f}"


def short_date(value) -> str:
    return f"{value:%m/%d/%Y}" if value else ""


class CoverageTableGroup(StyledInfoTableGroup):
    """The purple Coverages panel: a PolView-column table as tall as its rows."""

    def __init__(self, columns: Sequence[str], title: str = "Coverages", parent=None):
        super().__init__(title, show_info=False, parent=parent)
        self.setStyleSheet(GROUP_STYLE)
        self.setup_table(list(columns))
        self.table.set_empty_message("No coverages on this policy.")
        self.table._outer_frame.setStyleSheet(FUND_TABLE_STYLE)
        self.table._data_table.setStyleSheet(FUND_TABLE_STYLE)

    def load_rows(self, rows: List[list]) -> None:
        self.load_table_data(rows)
        self.table.setFixedHeight(self.table.fitted_height(min_rows=1, max_rows=10))


class BenefitButtonsGroup(QGroupBox):
    """The purple Benefits panel: one button per benefit (its form number) opening its detail card."""

    def __init__(self, title: str = "Benefits", parent=None):
        super().__init__(title, parent)
        self.setStyleSheet(GROUP_STYLE)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 18, 8, 8)
        self.buttons = QHBoxLayout()
        self.buttons.setSpacing(6)
        layout.addLayout(self.buttons)

    def load(self, items: Sequence[BenefitButton]) -> None:
        while self.buttons.count():
            widget = self.buttons.takeAt(0).widget()
            if widget is not None:
                widget.hide()
                widget.deleteLater()
        if not items:
            note = QLabel("No supplemental benefits on this policy.")
            note.setStyleSheet(f"color: {PURPLE_DARK}; background: transparent; font-size: 11px; font-style: italic;")
            self.buttons.addWidget(note)
        for label, tooltip, rows in items:
            button = QPushButton(label)
            button.setStyleSheet(VALUE_BUTTON_STYLE)
            button.setCursor(Qt.CursorShape.PointingHandCursor)
            button.setToolTip(f"{tooltip} - click for details")
            button.clicked.connect(lambda _checked=False, r=rows: show_detail_dialog(self, "Benefit Detail", r))
            self.buttons.addWidget(button)
        self.buttons.addStretch(1)
