"""
Transactions Criteria Panel
==============================
Filter by transaction type, dates, amounts, 68-segment change codes.
"""

from __future__ import annotations

from PyQt6.QtWidgets import QCheckBox, QHBoxLayout, QLabel

from .panel_widgets import (
    CriteriaPanel, CollapsibleSection, CheckableListBox,
    DateRangeRow, NumericRangeRow, SingleValueRow, make_combo,
)
from ...models.audit_constants import TRANSACTION_CODES, CHANGE_CODES_68


class TransactionsPanel(CriteriaPanel):
    """Transaction filters: type, dates, amounts, 68-segment change codes."""

    def _build_ui(self):
        # ── Enable toggle ───────────────────────────────────────────────
        self.enabled_cb = QCheckBox("Enable Transaction Criteria")
        self.enabled_cb.setStyleSheet("font-weight: bold;")
        self.main_layout.addWidget(self.enabled_cb)

        # ── Transaction Type ────────────────────────────────────────────
        sec_type = CollapsibleSection("Transaction Type")
        self.txn_type_combo = make_combo(TRANSACTION_CODES, include_blank=True)
        sec_type.add_widget(self.txn_type_combo)

        type_lbl = QLabel("— or multi-select —")
        type_lbl.setStyleSheet("font-size: 8pt; color: #666;")
        sec_type.add_widget(type_lbl)

        self.txn_types_list = CheckableListBox(TRANSACTION_CODES, max_height=200)
        sec_type.add_widget(self.txn_types_list)
        self.main_layout.addWidget(sec_type)

        # ── Dates ───────────────────────────────────────────────────────
        sec_dates = CollapsibleSection("Transaction Dates")
        self.entry_date_range = DateRangeRow("Entry Date")
        sec_dates.add_widget(self.entry_date_range)
        self.effective_date_range = DateRangeRow("Effective Date")
        sec_dates.add_widget(self.effective_date_range)

        # Effective-month / day sub-row
        month_row = QHBoxLayout()
        month_row.setSpacing(4)
        month_row.addWidget(QLabel("Eff Month:"))
        self.eff_month_low = SingleValueRow("From", "", 50)
        month_row.addWidget(self.eff_month_low)
        self.eff_month_high = SingleValueRow("To", "", 50)
        month_row.addWidget(self.eff_month_high)
        month_row.addStretch()
        sec_dates.add_layout(month_row)

        day_row = QHBoxLayout()
        day_row.setSpacing(4)
        day_row.addWidget(QLabel("Eff Day:"))
        self.eff_day_low = SingleValueRow("From", "", 50)
        day_row.addWidget(self.eff_day_low)
        self.eff_day_high = SingleValueRow("To", "", 50)
        day_row.addWidget(self.eff_day_high)
        day_row.addStretch()
        sec_dates.add_layout(day_row)

        self.on_issue_day_cb = QCheckBox("On Issue Day")
        sec_dates.add_widget(self.on_issue_day_cb)
        self.on_issue_month_cb = QCheckBox("On Issue Month")
        sec_dates.add_widget(self.on_issue_month_cb)
        self.main_layout.addWidget(sec_dates)

        # ── Amounts ─────────────────────────────────────────────────────
        sec_amt = CollapsibleSection("Transaction Amounts")
        self.gross_amount_range = NumericRangeRow("Gross Amount")
        sec_amt.add_widget(self.gross_amount_range)
        self.origin_combo = make_combo(
            {"": "", "A": "Auto", "M": "Manual"}, include_blank=True
        )
        from .panel_widgets import make_form_row
        sec_amt.add_layout(make_form_row("Origin of Txn", self.origin_combo))
        self.main_layout.addWidget(sec_amt)

        # ── 68-Segment Change Codes ─────────────────────────────────────
        sec_68 = CollapsibleSection("68-Segment Change Codes")
        self.has_change_cb = QCheckBox("Has Change Segment")
        sec_68.add_widget(self.has_change_cb)
        self.change_codes_list = CheckableListBox(CHANGE_CODES_68, max_height=250)
        sec_68.add_widget(self.change_codes_list)
        self.main_layout.addWidget(sec_68)

    # ── CriteriaPanel interface ─────────────────────────────────────────
    def write_to_criteria(self, criteria):
        tc = criteria.transaction
        tc.enabled = self.enabled_cb.isChecked()

        # Type
        tc.transaction_type = self.txn_type_combo.currentData() or ""
        tc.transaction_types = self.txn_types_list.get_checked_codes()

        # Dates
        tc.low_entry_date, tc.high_entry_date = self.entry_date_range.get_range()
        tc.low_effective_date, tc.high_effective_date = self.effective_date_range.get_range()
        tc.low_effective_month = self.eff_month_low.get_value()
        tc.high_effective_month = self.eff_month_high.get_value()
        tc.low_effective_day = self.eff_day_low.get_value()
        tc.high_effective_day = self.eff_day_high.get_value()
        tc.on_issue_day = self.on_issue_day_cb.isChecked()
        tc.on_issue_month = self.on_issue_month_cb.isChecked()

        # Amounts
        tc.low_gross_amount, tc.high_gross_amount = self.gross_amount_range.get_range()
        tc.origin_of_transaction = self.origin_combo.currentData() or ""

        # 68 codes
        tc.has_change_segment = self.has_change_cb.isChecked()
        tc.change_codes_68 = self.change_codes_list.get_checked_codes()

    def reset(self):
        self.enabled_cb.setChecked(False)
        self.txn_type_combo.setCurrentIndex(0)
        self.txn_types_list.clear_all()
        self.entry_date_range.clear()
        self.effective_date_range.clear()
        self.eff_month_low.clear()
        self.eff_month_high.clear()
        self.eff_day_low.clear()
        self.eff_day_high.clear()
        self.on_issue_day_cb.setChecked(False)
        self.on_issue_month_cb.setChecked(False)
        self.gross_amount_range.clear()
        self.origin_combo.setCurrentIndex(0)
        self.has_change_cb.setChecked(False)
        self.change_codes_list.clear_all()
