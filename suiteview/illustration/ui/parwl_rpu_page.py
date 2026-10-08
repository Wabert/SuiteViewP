"""Par WL Values page: the reduced paid-up (RPU) cash value worked from the mortality table.

Pick an RPU monthliversary and the page lists each step from the RPU basis
(NSP_RPU_TBL_CD / NSP_ITS_RT) to the month's base cash value: attained age, the
NSP sums at ages x and x + 1, the monthly interpolation, the per-unit value and
units. Each step is checked against the Cash Value page and CyberLife's stored NSPs.
A second grid lists every mortality term of the selected NSP sum so it can be
reproduced in Excel.
"""
from __future__ import annotations

from typing import List, Optional, Sequence

import pandas as pd
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor
from PyQt6.QtWidgets import QComboBox, QHBoxLayout, QLabel, QSplitter, QVBoxLayout, QWidget

from suiteview.illustration.core.parwl.nsp import NSPError, NSPWorkup
from suiteview.illustration.core.parwl.rpu_workup import RPUWorkup, rpu_cash_value_workup
from suiteview.illustration.models.parwl import ParWLMonth, ParWLPolicy
from suiteview.ui import tokens
from suiteview.ui.widgets.filter_table_view import FilterTableView

from .styles import INPUT_COMBO_STYLE, PURPLE_DARK

PAGE_TITLE = "RPU NSP Workup"
STEP_COLUMNS = ["Step", "Item", "Formula / Source", "Value", "Check"]
LEFT_ALIGNED_STEP_COLUMNS = ("Item", "Formula / Source", "Check")
TERM_COLUMNS = ["Age", "t", "q(x+t)", "tpx", "v^(t+1)", "tpx * q * v^(t+1)", "Cumulative Sum"]
TERM_DECIMALS = {"Age": 0, "t": 0, "q(x+t)": 8, "tpx": 10, "v^(t+1)": 10,
                 "tpx * q * v^(t+1)": 10, "Cumulative Sum": 10}
MATCH_BG = "#DFF3E4"
DIFFER_BG = "#F9D6D5"
NOT_RPU_NOTE = ("Not on reduced paid-up in this run: the base cash value comes from the tabular cash "
                "values (Cash Value page). Set Reduced paid-up on Inputs to see the NSP workup.")


def steps_frame(workup: RPUWorkup) -> pd.DataFrame:
    rows = [[n, s.item, s.formula, s.value, s.check] for n, s in enumerate(workup.steps, start=1)]
    return pd.DataFrame(rows, columns=STEP_COLUMNS)


def terms_frame(work: NSPWorkup) -> pd.DataFrame:
    rows = [[t.age, t.t, t.q, t.survival, t.discount, t.term, t.cumulative] for t in work.terms]
    return pd.DataFrame(rows, columns=TERM_COLUMNS)


def month_label(month: ParWLMonth) -> str:
    return (f"{month.when:%m/%d/%Y}   Year {month.policy_year}  Month {month.month_of_year}"
            f"  Age {month.attained_age}")


class ParWLRPUWorkupPage(QWidget):
    """Workup of one RPU month's base cash value, with the NSP mortality terms."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._policy: Optional[ParWLPolicy] = None
        self._months: List[ParWLMonth] = []
        self.workup: Optional[RPUWorkup] = None
        self._build()

    def _build(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)
        top = QHBoxLayout()
        top.setSpacing(6)
        caption_style = f"color: {PURPLE_DARK}; background: transparent; font-size: 11px; font-weight: bold;"
        month_caption = QLabel("RPU month:")
        month_caption.setStyleSheet(caption_style)
        top.addWidget(month_caption)
        self.month_combo = QComboBox()
        self.month_combo.setStyleSheet(INPUT_COMBO_STYLE)
        self.month_combo.setMinimumWidth(260)
        self.month_combo.currentIndexChanged.connect(self._show_month)
        top.addWidget(self.month_combo)
        terms_caption = QLabel("Mortality terms for:")
        terms_caption.setStyleSheet(caption_style)
        top.addSpacing(12)
        top.addWidget(terms_caption)
        self.terms_combo = QComboBox()
        self.terms_combo.setStyleSheet(INPUT_COMBO_STYLE)
        self.terms_combo.setMinimumWidth(150)
        self.terms_combo.currentIndexChanged.connect(self._show_terms)
        top.addWidget(self.terms_combo)
        top.addStretch(1)
        layout.addLayout(top)
        self.note = QLabel(NOT_RPU_NOTE)
        self.note.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.note.setWordWrap(True)
        self.note.setStyleSheet(
            f"color: {tokens.TEXT_MUTED}; font-style: italic; background: transparent; font-size: 11px;")
        layout.addWidget(self.note)
        split = QSplitter(Qt.Orientation.Vertical, self)
        self.steps_grid = self._grid(split)
        self.steps_grid.show_cell_highlights()
        self.terms_grid = self._grid(split)
        split.addWidget(self.steps_grid)
        split.addWidget(self.terms_grid)
        split.setSizes([420, 300])
        layout.addWidget(split, 1)
        self._set_active(False)

    @staticmethod
    def _grid(parent) -> FilterTableView:
        grid = FilterTableView(parent)
        grid.set_search_visible(False)
        grid.apply_ledger_style()
        grid.set_sort_enabled(False)
        grid.set_full_row_selection(True)
        return grid

    def _set_active(self, active: bool, note: str = NOT_RPU_NOTE, error: bool = False) -> None:
        for widget in (self.month_combo, self.terms_combo, self.steps_grid, self.terms_grid):
            widget.setEnabled(active)
        color = tokens.STATUS_ERROR if error else tokens.TEXT_MUTED
        self.note.setStyleSheet(
            f"color: {color}; font-style: italic; background: transparent; font-size: 11px;")
        self.note.setText(note)
        self.note.setVisible(not active or error)

    def clear(self, message: str = "") -> None:
        self._policy, self._months, self.workup = None, [], None
        self.month_combo.blockSignals(True)
        self.month_combo.clear()
        self.month_combo.blockSignals(False)
        self.terms_combo.clear()
        self.steps_grid.set_dataframe(pd.DataFrame())
        self.terms_grid.set_dataframe(pd.DataFrame())
        self._set_active(False, message or NOT_RPU_NOTE)

    def set_months(self, policy: ParWLPolicy, months: Sequence[ParWLMonth]) -> None:
        """Offer the run's RPU months, keeping the selected date when the run switches."""
        current = self.month_combo.currentIndex()
        previous = self._months[current].when if 0 <= current < len(self._months) else None
        self._policy = policy
        self._months = [m for m in months if m.rpu]
        self.month_combo.blockSignals(True)
        self.month_combo.clear()
        self.month_combo.addItems([month_label(m) for m in self._months])
        index = next((i for i, m in enumerate(self._months) if m.when == previous), 0)
        self.month_combo.setCurrentIndex(index if self._months else -1)
        self.month_combo.blockSignals(False)
        if not self._months:
            self.workup = None
            self.terms_combo.clear()
            self.steps_grid.set_dataframe(pd.DataFrame())
            self.terms_grid.set_dataframe(pd.DataFrame())
            self._set_active(False)
            return
        self._show_month(index)

    def _show_month(self, index: int) -> None:
        if self._policy is None or not 0 <= index < len(self._months):
            return
        try:
            workup = rpu_cash_value_workup(self._policy, self._months[index])
        except (NSPError, ValueError) as exc:
            self.workup = None
            self.steps_grid.set_dataframe(pd.DataFrame())
            self.terms_grid.set_dataframe(pd.DataFrame())
            self._set_active(False, f"The RPU workup could not be calculated: {exc}", error=True)
            self.month_combo.setEnabled(True)
            return
        self.workup = workup
        if workup.matches:
            self._set_active(True)
        else:
            self._set_active(True, f"The recalculated base cash value {workup.base_cv:,.2f} differs from the "
                                   f"projection's {workup.engine_base_cv:,.2f}.", error=True)
        frame = steps_frame(workup)
        self.steps_grid.set_dataframe(frame, limit_rows=False)
        self.steps_grid.model._left_align_columns = {STEP_COLUMNS.index(c) for c in LEFT_ALIGNED_STEP_COLUMNS}
        self.steps_grid.set_numeric_formatting(default_decimals=0)
        self.steps_grid.set_highlighted_cells({
            (row, "Check"): QColor(MATCH_BG if text.startswith("Matches") else DIFFER_BG)
            for row, text in enumerate(frame["Check"]) if text})
        self.steps_grid.autofit_columns_to_data(max_width=520)
        self.terms_combo.blockSignals(True)
        current = max(0, self.terms_combo.currentIndex())
        self.terms_combo.clear()
        self.terms_combo.addItems([f"Age {workup.at_age.attained_age} (x)",
                                   f"Age {workup.at_next_age.attained_age} (x + 1)"])
        self.terms_combo.setCurrentIndex(current)
        self.terms_combo.blockSignals(False)
        self._show_terms(current)

    def _show_terms(self, index: int) -> None:
        if self.workup is None or index < 0:
            return
        work = self.workup.at_age if index == 0 else self.workup.at_next_age
        self.terms_grid.set_dataframe(terms_frame(work), limit_rows=False)
        self.terms_grid.set_numeric_formatting(default_decimals=10, column_decimals=TERM_DECIMALS)
        self.terms_grid.autofit_columns_to_data()

    def current_frame(self) -> pd.DataFrame:
        return steps_frame(self.workup) if self.workup is not None else pd.DataFrame(columns=STEP_COLUMNS)
