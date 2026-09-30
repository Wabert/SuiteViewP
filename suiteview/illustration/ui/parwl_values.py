"""Par WL Values tab: monthly debug pages of a par whole life projection.

The illustration ledger is annual, but every page here is monthly - one row per
monthliversary, anniversary rows marked - so each step of the engine (premiums,
dividends and their application, paid-up additions and their NSP, cash values,
loans, deposits and OYT, death benefit) can be traced. A Current / Guaranteed toggle
switches between the dividend run and the no-dividend (guaranteed) run.
"""
from __future__ import annotations

from dataclasses import asdict
from typing import Dict, List, Optional, Sequence, Tuple

import pandas as pd
from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QButtonGroup,
    QCheckBox,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QPushButton,
    QSplitter,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from suiteview.illustration.models.parwl import ParWLMonth, ParWLResult
from suiteview.ui.widgets.filter_table_view import FilterTableView

from .styles import PURPLE_BG, PURPLE_DARK, PURPLE_PRIMARY, WHITE

LEAD_COLUMNS: Tuple[Tuple[str, str], ...] = (
    ("when", "Date"), ("policy_year", "Year"), ("month_of_year", "Month"), ("attained_age", "Age"),
)

# Page title -> (attribute, header) columns after the lead columns.
PAGES: Dict[str, Tuple[Tuple[str, str], ...]] = {
    "Summary": (
        ("status", "Status"), ("premium_paid", "Premium Paid"), ("dividend_total", "Dividend"),
        ("face", "Face"), ("additions", "Paid-Up Additions"), ("oyt_face", "OYT"),
        ("base_cv", "Base CV"), ("additions_cv", "Additions CV"), ("deposits", "Deposits"),
        ("cash_value", "Cash Value"), ("loan_payoff", "Loan Payoff"), ("surrender_value", "Surrender Value"),
        ("death_benefit", "Death Benefit"), ("notes", "Notes"),
    ),
    "Premiums": (
        ("base_premium", "Base Premium"), ("rider_premium", "Rider Premium"),
        ("benefit_premium", "Benefit & Extra Premium"), ("policy_fee", "Policy Fee"),
        ("premium_billed", "Premium Billed"), ("premium_by_dividend", "Paid by Dividend"),
        ("premium_paid", "Premium Paid"), ("premium_credit", "Premium Credit Left"),
        ("rider_payment", "PUA Rider Payment"),
    ),
    "Dividends": (
        ("dividend_year", "Div Year"), ("dividend_record", "Record"), ("dividend_option", "Option"),
        ("dividend_rate", "Cash Rate / Unit"), ("dividend_base", "On Coverage"),
        ("dividend_on_additions", "On Additions"), ("dividend_rider", "On PUA Rider"),
        ("dividend_total", "Total Dividend"), ("dividend_cash", "To Cash"),
        ("dividend_to_premium", "To Premium"), ("dividend_to_deposit", "To Deposit"),
        ("dividend_to_additions", "To Additions"), ("dividend_to_oyt", "To OYT"),
        ("dividend_to_loan", "To Loan"),
    ),
    "Paid-Up Additions": (
        ("additions_bought", "Bought by Dividend"), ("additions_bought_by_rider", "Bought by Rider Payment"),
        ("additions_dividend", "Base Additions"), ("additions_rider", "Rider Additions"),
        ("additions", "Total Additions"), ("nsp_start", "NSP Year Start"), ("nsp_end", "NSP Year End"),
        ("additions_cv", "Additions CV"),
    ),
    "Cash Value": (
        ("units", "Units"), ("rpu", "RPU"), ("cv_per_unit_start", "CV/Unit Year Start"),
        ("cv_per_unit_end", "CV/Unit Year End"), ("cv_per_unit", "CV/Unit"), ("base_cv", "Base CV"),
        ("additions_cv", "Additions CV"), ("deposits", "Deposits"), ("cash_value", "Cash Value"),
        ("loan_payoff", "Loan Payoff"), ("surrender_value", "Surrender Value"),
    ),
    "Loans": (
        ("new_loan", "New Loan"), ("loan_repayment", "Repayment"), ("loan_interest", "Interest Charged"),
        ("loan_interest_paid", "Interest Paid"), ("loan_principal", "Principal"), ("loan_accrued", "Accrued"),
        ("loan_unearned", "Unearned (Advance)"), ("loan_payoff", "Payoff"),
    ),
    "Deposits & OYT": (
        ("deposit_interest", "Deposit Interest"), ("dividend_to_deposit", "Dividend Deposited"),
        ("deposits", "Deposits"), ("dividend_to_oyt", "Dividend to OYT"), ("oyt_face", "OYT Face"),
    ),
    "Death Benefit": (
        ("face", "Face"), ("additions", "Paid-Up Additions"), ("oyt_face", "OYT"),
        ("term_rider_face", "Term Riders"), ("deposits", "Deposits"), ("loan_payoff", "Loan Payoff"),
        ("death_benefit", "Death Benefit"),
    ),
}
TEXT_COLUMNS = frozenset({"when", "status", "notes", "dividend_record", "dividend_option", "rpu"})
# Anniversary-only facts left blank on the other months so the dividend rows stand out.
BLANK_WHEN_ZERO = frozenset({"dividend_year", "dividend_rate"})
RATE_COLUMNS = {"dividend_rate": 4, "nsp_start": 3, "nsp_end": 3, "units": 3, "cv_per_unit_start": 2,
                "cv_per_unit_end": 2, "cv_per_unit": 2, "policy_year": 0, "month_of_year": 0,
                "attained_age": 0, "dividend_year": 0}


def month_frame(months: Sequence[ParWLMonth], page: str, anniversaries_only: bool = False) -> pd.DataFrame:
    """One page of monthly rows as a DataFrame with display headers."""
    columns = LEAD_COLUMNS + PAGES[page]
    rows = []
    for month in months:
        if anniversaries_only and month.month_of_year != 0 and month.index != 0:
            continue
        data = asdict(month)
        record = {}
        for attr, header in columns:
            value = data[attr]
            if attr == "when":
                value = value.strftime("%m/%d/%Y")
            elif attr == "rpu":
                value = "RPU" if value else ""
            elif attr in BLANK_WHEN_ZERO and not value:
                value = None
            record[header] = value
        rows.append(record)
    return pd.DataFrame(rows, columns=[header for _attr, header in columns])


class ParWLValuesTab(QWidget):
    """Navigator of monthly value pages with a Current / Guaranteed switch."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._result: Optional[ParWLResult] = None
        self._grids: Dict[str, FilterTableView] = {}
        self._build()

    def _build(self) -> None:
        self.setStyleSheet(f"background-color: {PURPLE_BG};")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(6, 6, 6, 6)
        layout.setSpacing(6)
        top = QHBoxLayout()
        self.caption = QLabel("Run Values to see the monthly par whole life values.")
        self.caption.setStyleSheet(f"color: {PURPLE_DARK}; font-weight: bold; background: transparent;")
        top.addWidget(self.caption, 1)
        self.anniversaries_only = QCheckBox("Anniversaries only")
        self.anniversaries_only.setStyleSheet(f"color: {PURPLE_DARK}; background: transparent;")
        self.anniversaries_only.toggled.connect(self._refresh)
        top.addWidget(self.anniversaries_only)
        self.toggle_group = QButtonGroup(self)
        self.toggle_group.setExclusive(True)
        segment = (
            f"QPushButton {{ background: {WHITE}; color: {PURPLE_DARK}; border: 1px solid {PURPLE_PRIMARY};"
            " padding: 2px 10px; font-size: 11px; }"
            f" QPushButton:checked {{ background: {PURPLE_PRIMARY}; color: white; font-weight: bold; }}")
        self.current_btn = QPushButton("Current Dividends")
        self.guaranteed_btn = QPushButton("Guaranteed (No Dividends)")
        for button in (self.current_btn, self.guaranteed_btn):
            button.setCheckable(True)
            button.setStyleSheet(segment)
            self.toggle_group.addButton(button)
            top.addWidget(button)
        self.current_btn.setChecked(True)
        self.guaranteed_btn.toggled.connect(self._refresh)
        layout.addLayout(top)
        self.notes_label = QLabel("")
        self.notes_label.setWordWrap(True)
        self.notes_label.setStyleSheet(
            "background: #FFF6D6; color: #3A2A00; border: 1px solid #D9B44A; border-radius: 4px;"
            " padding: 3px 6px; font-size: 11px;")
        self.notes_label.setVisible(False)
        layout.addWidget(self.notes_label)
        body = QSplitter(Qt.Orientation.Horizontal, self)
        self.navigator = QListWidget(body)
        self.navigator.setStyleSheet(
            "QListWidget { background: white; border: 1px solid #B79CDE; font-size: 11px; }"
            "QListWidget::item { height: 18px; }"
            "QListWidget::item:selected { background: #E8DDF8; color: #2A1458; }")
        self.navigator.addItems(list(PAGES))
        self.navigator.currentRowChanged.connect(self._show_page)
        self.stack = QStackedWidget(body)
        for title in PAGES:
            grid = FilterTableView(self.stack)
            grid.set_search_visible(False)
            grid.apply_ledger_style()
            grid.set_sort_enabled(False)
            grid.set_full_row_selection(True)
            grid.set_frozen_column_count(len(LEAD_COLUMNS))
            self._grids[title] = grid
            self.stack.addWidget(grid)
        body.addWidget(self.navigator)
        body.addWidget(self.stack)
        body.setStretchFactor(0, 0)
        body.setStretchFactor(1, 1)
        body.setSizes([150, 900])
        layout.addWidget(body, 1)
        self.navigator.setCurrentRow(0)

    def clear(self, message: str = "Run Values to see the monthly par whole life values.") -> None:
        self._result = None
        self.caption.setText(message)
        self.notes_label.setVisible(False)
        for grid in self._grids.values():
            grid.set_dataframe(pd.DataFrame())

    def set_result(self, result: ParWLResult) -> None:
        self._result = result
        policy = result.policy
        self.caption.setText(
            f"{policy.policy_number} {policy.base.plancode} - monthly values from "
            f"{policy.valuation_date:%m/%d/%Y} ({len(result.months)} months)")
        notes: List[str] = list(result.notes)
        self.notes_label.setText("\n".join(notes))
        self.notes_label.setVisible(bool(notes))
        self._refresh()

    def _months(self) -> List[ParWLMonth]:
        if self._result is None:
            return []
        return self._result.guaranteed_months if self.guaranteed_btn.isChecked() else self._result.months

    def _refresh(self, *_args) -> None:
        months = self._months()
        for title, grid in self._grids.items():
            frame = month_frame(months, title, self.anniversaries_only.isChecked())
            grid.set_dataframe(frame, limit_rows=False)
            decimals = {header: RATE_COLUMNS.get(attr, 2) for attr, header in LEAD_COLUMNS + PAGES[title]
                        if attr not in TEXT_COLUMNS}
            grid.set_numeric_formatting(default_decimals=2, column_decimals=decimals)
            grid.autofit_columns_to_data()

    def _show_page(self, row: int) -> None:
        if row >= 0:
            self.stack.setCurrentIndex(row)

    def current_frame(self) -> pd.DataFrame:
        title = self.navigator.currentItem().text() if self.navigator.currentItem() else "Summary"
        return month_frame(self._months(), title, self.anniversaries_only.isChecked())
