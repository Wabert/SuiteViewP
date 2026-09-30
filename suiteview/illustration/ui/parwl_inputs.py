"""RERUN input screen for participating whole life (par WL) illustrations.

Different from the UL/ISWL inputs: a par WL illustration is driven by the dividend
option (and its changes), reduced paid-up conversion, policy loans and repayments,
paid-up additions rider payments and the illustration's end age. Transactions are
entered by policy year (the anniversary starting that year) or by monthliversary
date; ``read_inputs`` validates every row loudly.
"""
from __future__ import annotations

import calendar
from datetime import date, datetime
from typing import List, Optional

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QComboBox,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QScrollArea,
    QSpinBox,
    QTableWidget,
    QVBoxLayout,
    QWidget,
)

from suiteview.illustration.models.parwl import (
    DIVIDEND_OPTION_LABELS,
    SECONDARY_OPTION_LABELS,
    DatedAmount,
    OptionChange,
    ParWLInputs,
    ParWLPolicy,
)

from .inputs_tab import ExcelTableWidget, NavigationDelegate
from .styles import (
    GROUP_STYLE,
    INPUT_CAPTION_STYLE,
    INPUT_CHECKBOX_STYLE,
    INPUT_COMBO_STYLE,
    INPUT_EDIT_STYLE,
    INPUT_TABLE_STYLE,
    PURPLE_BG,
    PURPLE_DARK,
)

NOT_APPLICABLE_STYLE = f"color: {PURPLE_DARK}; font-style: italic; font-size: 11px; background: transparent;"


class ParWLInputError(ValueError):
    """An input row cannot be read (names the table and row)."""


def _add_months(start: date, months: int, day: int) -> date:
    year = start.year + (start.month - 1 + months) // 12
    month = (start.month - 1 + months) % 12 + 1
    return date(year, month, min(day, calendar.monthrange(year, month)[1]))


class ParWLInputsTab(QWidget):
    """Par WL illustration inputs: dividends, reduced paid-up, loans, PUA rider payments."""

    inputs_changed = pyqtSignal()

    TABLE_ROWS = 8

    def __init__(self, parent=None):
        super().__init__(parent)
        self._policy: Optional[ParWLPolicy] = None
        self._build()

    # -- construction ---------------------------------------------------------------

    def _build(self) -> None:
        self.setStyleSheet(f"background-color: {PURPLE_BG};")
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        scroll = QScrollArea(self)
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        body = QWidget()
        body.setStyleSheet(f"background-color: {PURPLE_BG};")
        columns = QHBoxLayout(body)
        columns.setContentsMargins(8, 8, 8, 8)
        columns.setSpacing(10)
        left = QVBoxLayout()
        left.setSpacing(10)
        left.addWidget(self._build_dividend_group())
        left.addWidget(self._build_rpu_group())
        left.addWidget(self._build_duration_group())
        left.addStretch(1)
        right = QVBoxLayout()
        right.setSpacing(10)
        right.addWidget(self._build_loan_group())
        right.addWidget(self._build_rider_group())
        right.addStretch(1)
        columns.addLayout(left, 1)
        columns.addLayout(right, 1)
        scroll.setWidget(body)
        outer.addWidget(scroll)

    def _group(self, title: str) -> QGroupBox:
        group = QGroupBox(title, self)
        group.setStyleSheet(GROUP_STYLE)
        return group

    def _caption(self, text: str) -> QLabel:
        label = QLabel(text)
        label.setStyleSheet(INPUT_CAPTION_STYLE)
        return label

    def _table(self, headers: List[str], rows: Optional[int] = None) -> ExcelTableWidget:
        rows = rows or self.TABLE_ROWS
        table = ExcelTableWidget(rows, len(headers), self)
        table.setHorizontalHeaderLabels(headers)
        table.setStyleSheet(INPUT_TABLE_STYLE)
        table.verticalHeader().setVisible(False)
        table.setFixedHeight(20 * rows + 28)
        table.setEditTriggers(QTableWidget.EditTrigger.AllEditTriggers)
        table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        table.setTabKeyNavigation(False)
        table.setHorizontalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)
        table.setItemDelegate(NavigationDelegate(table))
        table.init_rows(0, rows)
        table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        table.itemChanged.connect(lambda *_: self.inputs_changed.emit())
        return table

    def _build_dividend_group(self) -> QGroupBox:
        group = self._group("Dividends")
        layout = QGridLayout(group)
        layout.setContentsMargins(10, 18, 10, 10)
        self.dividends_on = QCheckBox("Illustrate the current dividend scale")
        self.dividends_on.setStyleSheet(INPUT_CHECKBOX_STYLE)
        self.dividends_on.setChecked(True)
        self.dividends_on.setToolTip(
            "Off: no dividends are paid (guaranteed basis). The guaranteed columns are always\n"
            "calculated without dividends; this switches the illustrated (non-guaranteed) side.")
        self.dividends_on.toggled.connect(lambda *_: self.inputs_changed.emit())
        layout.addWidget(self.dividends_on, 0, 0, 1, 2)
        layout.addWidget(self._caption("Dividend option"), 1, 0)
        self.option_combo = QComboBox()
        self.option_combo.setStyleSheet(INPUT_COMBO_STYLE)
        for code, label in DIVIDEND_OPTION_LABELS.items():
            self.option_combo.addItem(f"{code} - {label}", code)
        self.option_combo.currentIndexChanged.connect(lambda *_: self.inputs_changed.emit())
        layout.addWidget(self.option_combo, 1, 1)
        layout.addWidget(self._caption("Secondary option"), 2, 0)
        self.secondary_combo = QComboBox()
        self.secondary_combo.setStyleSheet(INPUT_COMBO_STYLE)
        self.secondary_combo.addItem("(none)", "")
        for code, label in SECONDARY_OPTION_LABELS.items():
            self.secondary_combo.addItem(f"{code} - {label}", code)
        self.secondary_combo.setToolTip(
            "Takes the dividend left over when OYT is limited, premium reduction exceeds the\n"
            "premiums due, or loan reduction pays the loan off.")
        layout.addWidget(self.secondary_combo, 2, 1)
        layout.addWidget(self._caption("Deposit interest %"), 3, 0)
        self.deposit_rate = QLineEdit()
        self.deposit_rate.setStyleSheet(INPUT_EDIT_STYLE)
        self.deposit_rate.setToolTip(
            "Interest credited to dividends on deposit at each anniversary. Blank uses the rate on the record.")
        layout.addWidget(self.deposit_rate, 3, 1)
        self.record_option_label = QLabel("")
        self.record_option_label.setStyleSheet(NOT_APPLICABLE_STYLE)
        layout.addWidget(self.record_option_label, 4, 0, 1, 2)
        layout.addWidget(self._caption("Option changes (policy year or date, option code)"), 5, 0, 1, 2)
        self.option_table = self._table(["Year / Date", "Option", "Secondary"], rows=5)
        layout.addWidget(self.option_table, 6, 0, 1, 2)
        return group

    def _build_rpu_group(self) -> QGroupBox:
        group = self._group("Reduced Paid-Up")
        layout = QGridLayout(group)
        layout.setContentsMargins(10, 18, 10, 10)
        self.rpu_check = QCheckBox("Convert to reduced paid-up at")
        self.rpu_check.setStyleSheet(INPUT_CHECKBOX_STYLE)
        self.rpu_check.setToolTip(
            "Premiums stop and the net cash value (base, additions and deposits less the loan)\n"
            "buys paid-up insurance at the coverage's RPU net single premium.")
        self.rpu_when = QLineEdit()
        self.rpu_when.setStyleSheet(INPUT_EDIT_STYLE)
        self.rpu_when.setPlaceholderText("policy year or mm/dd/yyyy")
        self.rpu_when.setEnabled(False)
        self.rpu_check.toggled.connect(self.rpu_when.setEnabled)
        self.rpu_check.toggled.connect(lambda *_: self.inputs_changed.emit())
        layout.addWidget(self.rpu_check, 0, 0)
        layout.addWidget(self.rpu_when, 0, 1)
        self.rpu_note = QLabel("")
        self.rpu_note.setStyleSheet(NOT_APPLICABLE_STYLE)
        self.rpu_note.setWordWrap(True)
        layout.addWidget(self.rpu_note, 1, 0, 1, 2)
        return group

    def _build_duration_group(self) -> QGroupBox:
        group = self._group("Illustration")
        layout = QHBoxLayout(group)
        layout.setContentsMargins(10, 18, 10, 10)
        layout.addWidget(self._caption("Illustrate to attained age"))
        self.end_age = QSpinBox()
        self.end_age.setRange(0, 121)
        self.end_age.setStyleSheet(INPUT_EDIT_STYLE)
        self.end_age.setToolTip("0 = to maturity")
        self.end_age.setSpecialValueText("maturity")
        layout.addWidget(self.end_age)
        layout.addStretch(1)
        return group

    def _build_loan_group(self) -> QGroupBox:
        group = self._group("Policy Loans")
        layout = QVBoxLayout(group)
        layout.setContentsMargins(10, 18, 10, 10)
        self.loan_note = QLabel("")
        self.loan_note.setStyleSheet(NOT_APPLICABLE_STYLE)
        self.loan_note.setWordWrap(True)
        layout.addWidget(self.loan_note)
        self.pay_interest = QCheckBox("Pay loan interest in cash (otherwise it is added to the loan)")
        self.pay_interest.setStyleSheet(INPUT_CHECKBOX_STYLE)
        self.pay_interest.toggled.connect(lambda *_: self.inputs_changed.emit())
        layout.addWidget(self.pay_interest)
        row = QHBoxLayout()
        left = QVBoxLayout()
        left.addWidget(self._caption("New loans"))
        self.loan_table = self._table(["Year / Date", "Amount"])
        left.addWidget(self.loan_table)
        right = QVBoxLayout()
        right.addWidget(self._caption("Loan repayments"))
        self.repay_table = self._table(["Year / Date", "Amount"])
        right.addWidget(self.repay_table)
        row.addLayout(left)
        row.addLayout(right)
        layout.addLayout(row)
        return group

    def _build_rider_group(self) -> QGroupBox:
        self.rider_group = self._group("Paid-Up Additions Rider Payments")
        layout = QVBoxLayout(self.rider_group)
        layout.setContentsMargins(10, 18, 10, 10)
        self.rider_note = QLabel("")
        self.rider_note.setStyleSheet(NOT_APPLICABLE_STYLE)
        self.rider_note.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.rider_note.setWordWrap(True)
        layout.addWidget(self.rider_note)
        self.rider_table = self._table(["Year / Date", "Amount"], rows=5)
        layout.addWidget(self.rider_table)
        return self.rider_group

    # -- policy -----------------------------------------------------------------------

    def load_policy(self, policy: ParWLPolicy) -> None:
        """Reset every input to the record's defaults."""
        self._policy = policy
        self.dividends_on.setChecked(True)
        option = policy.dividend_option if policy.dividend_option in DIVIDEND_OPTION_LABELS else "4"
        self.option_combo.setCurrentIndex(max(0, self.option_combo.findData(option)))
        secondary = policy.secondary_dividend_option
        self.secondary_combo.setCurrentIndex(max(0, self.secondary_combo.findData(secondary)))
        label = DIVIDEND_OPTION_LABELS.get(policy.dividend_option, "no further dividends")
        self.record_option_label.setText(
            f"Record: option {policy.dividend_option or '(blank)'} - {label}; secondary "
            f"{policy.secondary_dividend_option or '(none)'}")
        self.deposit_rate.clear()
        self.deposit_rate.setPlaceholderText(
            f"{policy.deposit_rate * 100:.3f} (record)" if policy.deposit_rate is not None else "not on record")
        for table in (self.option_table, self.loan_table, self.repay_table, self.rider_table):
            table.blockSignals(True)
            table.clearContents()
            table.init_rows(0, table.rowCount())
            table.blockSignals(False)
        self.rpu_check.setChecked(False)
        self.rpu_when.clear()
        rpu_possible = not policy.is_rpu
        self.rpu_check.setEnabled(rpu_possible)
        self.rpu_note.setText("" if rpu_possible else "The policy is already reduced paid-up.")
        self.pay_interest.setChecked(False)
        rate = f"{policy.loan_rate:.3%}" if policy.loan_rate is not None else "not on record"
        kind = {"0": "fixed, in advance", "1": "fixed, in arrears", "6": "variable, in advance",
                "7": "variable, in arrears", "9": "loans not allowed"}.get(policy.loan_type_code, "type unknown")
        balance = f"; current loan {policy.loan_principal:,.2f}" if policy.loans else ""
        self.loan_note.setText(f"Loan interest {rate} ({kind}){balance}.")
        rider = policy.pua_rider
        payable = rider is not None and not policy.is_rpu and not rider.payments_ceased
        self.rider_table.setEnabled(payable)
        if rider is None:
            self.rider_note.setText("Not applicable - the policy has no paid-up additions rider.")
        elif not payable:
            self.rider_note.setText(
                f"Not applicable - {rider.plancode} no longer accepts payments; its additions stay in force.")
        else:
            self.rider_note.setText(f"Payments buy paid-up additions on {rider.plancode} at its PUI rates.")
        self.end_age.setValue(0)

    # -- reading ----------------------------------------------------------------------

    def _when(self, text: str, what: str) -> date:
        policy = self._policy
        text = text.strip()
        if text.isdigit():
            year = int(text)
            if year < 1:
                raise ParWLInputError(f"{what}: policy year {year} is not valid.")
            return _add_months(policy.issue_date, (year - 1) * 12, policy.issue_date.day)
        for fmt in ("%m/%d/%Y", "%Y-%m-%d", "%m/%d/%y"):
            try:
                return datetime.strptime(text, fmt).date()
            except ValueError:
                continue
        raise ParWLInputError(f"{what}: '{text}' is not a policy year or a date.")

    @staticmethod
    def _amount(text: str, what: str) -> float:
        try:
            return float(text.replace(",", "").replace("$", "").strip())
        except ValueError:
            raise ParWLInputError(f"{what}: '{text}' is not an amount.") from None

    def _dated_amounts(self, table: QTableWidget, name: str) -> List[DatedAmount]:
        items = []
        for row in range(table.rowCount()):
            when_item, amount_item = table.item(row, 0), table.item(row, 1)
            when_text = when_item.text().strip() if when_item else ""
            amount_text = amount_item.text().strip() if amount_item else ""
            if not when_text and not amount_text:
                continue
            what = f"{name} row {row + 1}"
            if not when_text or not amount_text:
                raise ParWLInputError(f"{what}: enter both the year/date and the amount.")
            amount = self._amount(amount_text, what)
            if amount <= 0:
                raise ParWLInputError(f"{what}: the amount must be positive.")
            items.append(DatedAmount(self._when(when_text, what), amount))
        return items

    def _option_changes(self) -> List[OptionChange]:
        changes = []
        for row in range(self.option_table.rowCount()):
            cells = [self.option_table.item(row, c) for c in range(3)]
            texts = [c.text().strip() if c else "" for c in cells]
            if not any(texts):
                continue
            what = f"Option changes row {row + 1}"
            if not texts[0] or not texts[1]:
                raise ParWLInputError(f"{what}: enter the year/date and the option code.")
            option = texts[1][:1]
            if option not in DIVIDEND_OPTION_LABELS:
                raise ParWLInputError(f"{what}: option '{texts[1]}' is not one of {', '.join(DIVIDEND_OPTION_LABELS)}.")
            secondary = texts[2][:1] if texts[2] else ""
            if secondary and secondary not in SECONDARY_OPTION_LABELS:
                raise ParWLInputError(f"{what}: secondary option '{texts[2]}' is not valid.")
            changes.append(OptionChange(self._when(texts[0], what), option, secondary))
        return changes

    def read_inputs(self) -> ParWLInputs:
        """The screen as ``ParWLInputs``; raises ``ParWLInputError`` naming a bad row."""
        if self._policy is None:
            raise ParWLInputError("Load a par whole life policy first.")
        option = self.option_combo.currentData()
        rpu_at = None
        if self.rpu_check.isChecked():
            if not self.rpu_when.text().strip():
                raise ParWLInputError("Reduced paid-up: enter the policy year or date.")
            rpu_at = self._when(self.rpu_when.text(), "Reduced paid-up")
        deposit_rate = None
        if self.deposit_rate.text().strip():
            deposit_rate = self._amount(self.deposit_rate.text(), "Deposit interest %") / 100.0
            if not 0 <= deposit_rate < 0.25:
                raise ParWLInputError("Deposit interest %: enter a percentage such as 3.5.")
        return ParWLInputs(
            dividends=self.dividends_on.isChecked(),
            dividend_option=option if option != self._policy.dividend_option else None,
            secondary_option=self.secondary_combo.currentData() or None,
            option_changes=self._option_changes(),
            rpu_at=rpu_at,
            loans=self._dated_amounts(self.loan_table, "New loans"),
            loan_repayments=self._dated_amounts(self.repay_table, "Loan repayments"),
            rider_payments=self._dated_amounts(self.rider_table, "PUA rider payments"),
            pay_loan_interest=self.pay_interest.isChecked(),
            deposit_rate=deposit_rate,
            end_age=self.end_age.value() or None,
        )
