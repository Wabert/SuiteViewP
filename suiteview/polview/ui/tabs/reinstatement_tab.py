"""Read-only UL reinstatement quotes using the shared projection service."""
from __future__ import annotations

import logging
from datetime import date
from typing import TYPE_CHECKING

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QApplication, QHBoxLayout, QLabel, QPushButton, QSizePolicy, QVBoxLayout, QWidget,
)

from ...services.reinstatement import (
    ReinstatementError,
    calculate_home_office_reinstatement,
    reinstatement_summary,
)
from ..formatting import format_currency, format_date
from ..styles import GRAY_LIGHT, GRAY_MID, GRAY_TEXT, GREEN_DARK, WHITE
from ..widgets import StyledInfoTableGroup

if TYPE_CHECKING:
    from ...models.policy_information import PolicyInformation

logger = logging.getLogger(__name__)


class ReinstatementTab(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._policy: PolicyInformation | None = None
        self._result = None
        self.setStyleSheet(f"background-color: {WHITE};")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(6, 4, 6, 4)
        layout.setSpacing(6)

        self.summary_group = StyledInfoTableGroup(
            "Termination", columns=4, show_table=False,
        )
        for label, key, label_width, value_width in (
            ("Last entry", "entry", 60, 145),
            ("Termination effective", "termination", 120, 80),
            ("Current date", "today", 75, 80),
            ("Terminated", "elapsed", 65, 105),
        ):
            self.summary_group.add_field(label, key, label_width, value_width)
        self.summary_group.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)
        layout.addWidget(self.summary_group)

        toolbar = QHBoxLayout()
        self.status_label = QLabel()
        self.status_label.setWordWrap(True)
        self.status_label.setTextFormat(Qt.TextFormat.PlainText)
        self.status_label.setStyleSheet(
            f"font-size: 11px; color: {GREEN_DARK}; background: transparent;"
        )
        toolbar.addWidget(self.status_label, 1)
        self.calculate_button = QPushButton("Recalculate")
        self.calculate_button.clicked.connect(self._calculate)
        toolbar.addWidget(self.calculate_button)
        layout.addLayout(toolbar)

        sections = QHBoxLayout()
        sections.setSpacing(6)
        self.home_group = StyledInfoTableGroup("Home Office Reinstatement")
        for label, key in (
            ("Quote pay-to date", "pay_to"),
            ("Funded through deduction", "next_date"),
            ("Reinstatement premium", "premium"),
            ("Calculation basis", "basis"),
        ):
            self.home_group.add_field(label, key, 155, 100)
        self.home_group.setup_table(["Calculation breakdown", "Amount / detail"])
        self.home_group.table._data_table.setSortingEnabled(False)
        self.home_group.table._data_table.horizontalHeaderItem(0).setTextAlignment(
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter
        )
        self.explanation_label = QLabel()
        self.explanation_label.setWordWrap(True)
        self.explanation_label.setTextFormat(Qt.TextFormat.PlainText)
        self.explanation_label.setStyleSheet(
            f"color: {GRAY_TEXT}; font-size: 11px; background: transparent; border: none;"
        )
        self.home_group.layout().addWidget(self.explanation_label)
        sections.addWidget(self.home_group, 1)

        self.skipped_group = StyledInfoTableGroup(
            "Skipped Coverage Reinstatement", show_info=False, show_table=False,
        )
        self.skipped_group.setStyleSheet(
            self.skipped_group.styleSheet()
            + f"\nQGroupBox {{ background-color: {GRAY_LIGHT}; border-color: {GRAY_MID}; }}"
        )
        self.skipped_note = QLabel(
            "Calculation not yet available.\n"
            "Skipped Coverage reinstatement rules have not been specified."
        )
        self.skipped_note.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.skipped_note.setWordWrap(True)
        self.skipped_note.setStyleSheet(
            f"color: {GRAY_TEXT}; font-size: 11px; font-style: italic;"
            "background: transparent; border: none;"
        )
        self.skipped_group.layout().insertWidget(0, self.skipped_note, 1)
        self.skipped_group.layout().setStretch(1, 0)
        sections.addWidget(self.skipped_group, 1)
        layout.addLayout(sections, 1)
        self.clear()

    def clear(self):
        self._policy = None
        self._result = None
        self.summary_group.clear_info()
        self.home_group.clear_info()
        self.home_group.table.setRowCount(0)
        self.explanation_label.clear()
        self.status_label.setText("Load a UL policy to quote reinstatement.")
        self.calculate_button.setEnabled(False)

    def load_policy(self, policy: PolicyInformation):
        self.clear()
        self._policy = policy
        self._calculate()

    def _calculate(self):
        self._result = None
        self.home_group.clear_info()
        self.home_group.table.setRowCount(0)
        self.summary_group.clear_info()
        self.explanation_label.clear()
        self.calculate_button.setEnabled(False)
        if self._policy is None:
            self.status_label.setText("Load a UL policy to quote reinstatement.")
            return
        today = date.today()
        QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
        try:
            summary = reinstatement_summary(self._policy, today=today)
            self.summary_group.set_value(
                "entry", f"{summary.last_entry_code} - {summary.last_entry_description}",
            )
            self.summary_group.set_value(
                "termination", format_date(summary.termination_date) or "Not available",
            )
            self.summary_group.set_value("today", format_date(summary.current_date))
            elapsed = (
                f"{summary.terminated_years} year{'s' if summary.terminated_years != 1 else ''}, "
                f"{summary.terminated_months} month{'s' if summary.terminated_months != 1 else ''}"
                if summary.terminated_years is not None else "Not available"
            )
            self.summary_group.set_value("elapsed", elapsed)
            self.home_group.set_value("pay_to", format_date(summary.quote_pay_to_date))
            self.home_group.set_value("next_date", format_date(summary.next_monthliversary))
            if not summary.eligible:
                self.status_label.setText(summary.message)
                self.home_group.set_value("premium", "Not eligible")
                return
            self.calculate_button.setEnabled(True)
            self.status_label.setText("Calculating Home Office reinstatement...")
            result = calculate_home_office_reinstatement(self._policy, today=today)
            self.home_group.set_value("premium", format_currency(result.premium, prefix="$"))
            self.home_group.set_value("basis", result.basis)
            self.home_group.load_table_data(result.breakdown)
            for row in range(self.home_group.table.rowCount()):
                self.home_group.table.item(row, 0).setTextAlignment(
                    Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter
                )
            self.home_group.table.autoFitAllColumns()
            self.explanation_label.setText(result.explanation)
            self.status_label.setText(
                "Home Office quote calculated. Skipped Coverage is not yet available."
            )
            self._result = result
        except ReinstatementError as exc:
            logger.warning("Reinstatement quote unavailable: %s", exc, exc_info=True)
            self.home_group.set_value("premium", "Unavailable")
            self.status_label.setText(f"Unable to quote reinstatement: {exc}")
            self.calculate_button.setEnabled(True)
        finally:
            QApplication.restoreOverrideCursor()
