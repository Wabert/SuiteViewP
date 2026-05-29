"""
Annuity Rider tab - backcasts rider values from a current cash value.
"""

from __future__ import annotations

import calendar
import math
from collections import defaultdict
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from typing import TYPE_CHECKING, Iterable

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QPushButton,
    QTableWidgetItem,
)

from ..formatting import format_date
from ..styles import WHITE, BLUE_DARK
from ..widgets import StyledInfoTableGroup

if TYPE_CHECKING:
    from ...models.policy_information import PolicyInformation


RIDER_PLANCODE = "0699830R"
ANNUITY_FUND_ID = "A1"
NEW_MONEY_RATE = Decimal("0.06")
PORTFOLIO_RATE = Decimal("0.04")


@dataclass
class RiderTransaction:
    effective_date: date
    sequence: int
    code: str
    amount: Decimal


@dataclass
class NewMoneyBucket:
    amount: Decimal
    roll_date: date


@dataclass
class RiderHistoryRow:
    effective_date: date
    transaction_type: str
    transaction_amount: Decimal
    cash_value: Decimal
    portfolio_value: Decimal
    new_money_value: Decimal
    new_money_buckets: list[Decimal]


class AnnuityRiderTab(QWidget):
    """Tool tab for the annuity rider value backcast."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._policy: PolicyInformation | None = None
        self._input_date = date.today()
        self._transactions: list[RiderTransaction] = []
        self._cyberlife_start_date: date | None = None
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 8, 12, 8)
        layout.setSpacing(8)
        self.setStyleSheet(f"background-color: {WHITE};")

        input_row = QHBoxLayout()
        input_row.setSpacing(8)

        label_style = f"font-size: 11px; font-weight: bold; color: {BLUE_DARK}; background: transparent;"
        self.input_date_label = QLabel("Input Date")
        self.input_date_label.setStyleSheet(label_style)
        self.input_date_value = QLabel(format_date(self._input_date))
        self.input_date_value.setMinimumWidth(90)
        self.input_date_value.setStyleSheet("font-size: 11px; background: transparent;")

        self.cash_value_label = QLabel("Annuity Cash Value")
        self.cash_value_label.setStyleSheet(label_style)
        self.cash_value_input = QLineEdit()
        self.cash_value_input.setMaximumWidth(130)
        self.cash_value_input.setAlignment(Qt.AlignmentFlag.AlignRight)
        self.cash_value_input.setPlaceholderText("0.00")
        self.cash_value_input.editingFinished.connect(self._recalculate)

        self.calculate_btn = QPushButton("Calculate")
        self.calculate_btn.setMaximumWidth(90)
        self.calculate_btn.clicked.connect(self._recalculate)

        self.status_label = QLabel("")
        self.status_label.setStyleSheet("font-size: 11px; background: transparent;")

        input_row.addWidget(self.input_date_label)
        input_row.addWidget(self.input_date_value)
        input_row.addSpacing(16)
        input_row.addWidget(self.cash_value_label)
        input_row.addWidget(self.cash_value_input)
        input_row.addWidget(self.calculate_btn)
        input_row.addWidget(self.status_label, 1)
        layout.addLayout(input_row)

        self.history_group = StyledInfoTableGroup(
            "Annuity Rider Values", show_info=False, show_table=True, filterable=True
        )
        self.history_table = self.history_group.table
        self.history_table.setColumnCount(7)
        self.history_table.setHorizontalHeaderLabels([
            "Effective Date", "Transaction type", "Transaction Amount", "Cash Value",
            "Portfolio Value", "Total New Money Value", "Calced New Money Buckets",
        ])
        layout.addWidget(self.history_group, 1)

    def load_data_from_policy(self, policy: 'PolicyInformation'):
        """Load eligible annuity rider transactions for the current policy."""
        self._policy = policy
        self._input_date = date.today()
        self.input_date_value.setText(format_date(self._input_date))
        self._cyberlife_start_date = self._get_cyberlife_transaction_start(policy)
        self._transactions = self._get_rider_transactions(policy)
        self.history_table.setRowCount(0)

        if not self._transactions:
            self._set_message_row("No A1 annuity rider transactions found")
            return

        if self.cash_value_input.text().strip():
            self._recalculate()
        else:
            start_date = self._display_start_date(self._input_date)
            self.status_label.setText(
                f"{len(self._transactions)} A1 transactions loaded; history starts {format_date(start_date)}"
            )
            self._set_message_row("Enter Annuity Cash Value and click Calculate")

    def _recalculate(self):
        if not self._policy:
            return
        if not self._transactions:
            self._set_message_row("No A1 annuity rider transactions found")
            return

        cash_value = self._parse_amount(self.cash_value_input.text())
        if cash_value is None:
            self._set_message_row("Enter a valid Annuity Cash Value")
            return

        try:
            rows = self._build_history(self._transactions, self._input_date, cash_value)
        except Exception as exc:
            self._set_message_row(f"Error: {exc}")
            return

        self._populate_history(rows)
        self.status_label.setText(f"{len(rows)} rows calculated")

    def _populate_history(self, rows: list[RiderHistoryRow]):
        self.history_table.setRowCount(len(rows))
        for row_idx, row in enumerate(reversed(rows)):
            self.history_table.setItem(row_idx, 0, QTableWidgetItem(format_date(row.effective_date)))
            self.history_table.setItem(row_idx, 1, QTableWidgetItem(row.transaction_type))
            self.history_table.setItem(row_idx, 2, QTableWidgetItem(self._format_money(row.transaction_amount)))
            self.history_table.setItem(row_idx, 3, QTableWidgetItem(self._format_money(row.cash_value)))
            self.history_table.setItem(row_idx, 4, QTableWidgetItem(self._format_money(row.portfolio_value)))
            self.history_table.setItem(row_idx, 5, QTableWidgetItem(self._format_money(row.new_money_value)))
            self.history_table.setItem(row_idx, 6, QTableWidgetItem(self._format_bucket_values(row.new_money_buckets, row.new_money_value)))
        self.history_table.autoFitAllColumns()

    def _set_message_row(self, message: str):
        self.history_table.setRowCount(1)
        self.history_table.setItem(
            0, 0, QTableWidgetItem(message),
            alignment=Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
        )
        for col in range(1, self.history_table.columnCount()):
            self.history_table.setItem(0, col, QTableWidgetItem(""))
        self.history_table.autoFitAllColumns()

    def _get_rider_transactions(self, policy: 'PolicyInformation') -> list[RiderTransaction]:
        transactions = []
        for row in policy.fetch_table("FH_FIXED"):
            fund_id = str(row.get("FUND_ID") or row.get("FND_ID_CD") or "").strip()
            if fund_id.upper() != ANNUITY_FUND_ID:
                continue
            if self._is_reversal_or_reversed(row):
                continue
            effective_date = self._parse_date(row.get("ASOF_DT"))
            if not effective_date or effective_date > self._input_date:
                continue
            net_amount = self._parse_amount(row.get("NET_AMT") or row.get("ACC_VAL_GRS_AMT"))
            if net_amount is None or net_amount == 0:
                continue
            code = self._transaction_code(row)
            amount = self._signed_amount(code, net_amount)
            sequence = self._parse_int(row.get("SEQ_NO"))
            transactions.append(RiderTransaction(effective_date, sequence, code, amount))

        return sorted(transactions, key=lambda trans: (trans.effective_date, trans.sequence))

    def _get_cyberlife_transaction_start(self, policy: 'PolicyInformation') -> date | None:
        dates = []
        for row in policy.fetch_table("FH_FIXED"):
            effective_date = self._parse_date(row.get("ASOF_DT"))
            if effective_date and effective_date <= self._input_date:
                dates.append(effective_date)
        return min(dates) if dates else None

    @staticmethod
    def _is_reversal_or_reversed(row: dict) -> bool:
        rev_ind = str(row.get("FCB0_REV_IND", "") or "").strip()
        rev_appl = str(row.get("FCB2_REV_APPL_IND", "") or "").strip()
        return rev_ind == "1" or rev_appl == "1"

    @staticmethod
    def _transaction_code(row: dict) -> str:
        code = str(row.get("TRANS", "") or "").strip()
        if code:
            return code
        return f"{str(row.get('TRN_TYP_CD', '') or '').strip()}{str(row.get('TRN_SBY_CD', '') or '').strip()}"

    @staticmethod
    def _signed_amount(code: str, amount: Decimal) -> Decimal:
        code = (code or "").strip().upper()
        if code.startswith("S") and amount > 0:
            return -amount
        return amount

    def _build_history(
        self,
        transactions: list[RiderTransaction],
        input_date: date,
        target_value: Decimal,
    ) -> list[RiderHistoryRow]:
        first_date = transactions[0].effective_date
        display_start = self._display_start_date(input_date)
        initial_portfolio = self._solve_initial_portfolio(transactions, first_date, input_date, target_value)

        tx_by_date: dict[date, list[RiderTransaction]] = defaultdict(list)
        for trans in transactions:
            tx_by_date[trans.effective_date].append(trans)

        event_dates = set(tx_by_date.keys())
        event_dates.update(self._month_ends(display_start, input_date))
        event_dates.add(input_date)
        event_dates = {event_date for event_date in event_dates if first_date <= event_date <= input_date}

        portfolio = initial_portfolio
        buckets: list[NewMoneyBucket] = []
        previous_date = first_date
        rows: list[RiderHistoryRow] = []

        for event_date in sorted(event_dates):
            portfolio, buckets = self._accrue_state(portfolio, buckets, previous_date, event_date)
            codes = []
            transaction_amount = Decimal("0")
            for trans in tx_by_date.get(event_date, []):
                portfolio, buckets = self._apply_transaction(portfolio, buckets, trans)
                codes.append(trans.code)
                transaction_amount += trans.amount

            if event_date >= display_start:
                transaction_type = ", ".join(codes) if codes else "Month End"
                if event_date == input_date and not codes and event_date.day != self._last_day_of_month(event_date):
                    transaction_type = "Input Date"
                new_money_value = sum((bucket.amount for bucket in buckets), Decimal("0"))
                rows.append(RiderHistoryRow(
                    event_date,
                    transaction_type,
                    transaction_amount,
                    portfolio + new_money_value,
                    portfolio,
                    new_money_value,
                    [bucket.amount for bucket in buckets],
                ))
            previous_date = event_date

        return rows

    @staticmethod
    def _format_money(value: Decimal) -> str:
        cents = value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        return f"{cents:,.2f}"

    def _format_bucket_values(self, bucket_values: list[Decimal], total_value: Decimal) -> str:
        if not bucket_values:
            return ""
        bucket_cents = [value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP) for value in bucket_values]
        total_cents = total_value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        bucket_cents[-1] += total_cents - sum(bucket_cents, Decimal("0.00"))
        return ", ".join(f"{value:,.2f}" for value in bucket_cents if value != 0)

    def _display_start_date(self, input_date: date) -> date:
        start_source = self._cyberlife_start_date or input_date
        return min(self._add_years(start_source, 2), input_date)

    def _solve_initial_portfolio(
        self,
        transactions: list[RiderTransaction],
        first_date: date,
        input_date: date,
        target_value: Decimal,
    ) -> Decimal:
        def final_value(initial_value: Decimal) -> Decimal:
            portfolio = initial_value
            buckets: list[NewMoneyBucket] = []
            previous_date = first_date
            for trans in transactions:
                portfolio, buckets = self._accrue_state(portfolio, buckets, previous_date, trans.effective_date)
                portfolio, buckets = self._apply_transaction(portfolio, buckets, trans)
                previous_date = trans.effective_date
            portfolio, buckets = self._accrue_state(portfolio, buckets, previous_date, input_date)
            return portfolio + sum((bucket.amount for bucket in buckets), Decimal("0"))

        spread = max(abs(target_value), Decimal("1000"))
        low = -spread
        high = spread
        while final_value(low) > target_value:
            low *= 2
        while final_value(high) < target_value:
            high *= 2

        for _ in range(80):
            mid = (low + high) / 2
            if final_value(mid) < target_value:
                low = mid
            else:
                high = mid
        return (low + high) / 2

    def _apply_transaction(
        self,
        portfolio: Decimal,
        buckets: list[NewMoneyBucket],
        trans: RiderTransaction,
    ) -> tuple[Decimal, list[NewMoneyBucket]]:
        if trans.amount >= 0:
            buckets.append(NewMoneyBucket(trans.amount, self._new_money_roll_date(trans.effective_date)))
            return portfolio, buckets

        portfolio += trans.amount
        return portfolio, buckets

    def _accrue_state(
        self,
        portfolio: Decimal,
        buckets: list[NewMoneyBucket],
        start_date: date,
        end_date: date,
    ) -> tuple[Decimal, list[NewMoneyBucket]]:
        current = start_date
        active_buckets = list(buckets)
        while current < end_date:
            next_roll = min(
                (bucket.roll_date for bucket in active_buckets if current < bucket.roll_date <= end_date),
                default=end_date,
            )
            portfolio = self._compound(portfolio, PORTFOLIO_RATE, current, next_roll)
            for bucket in active_buckets:
                bucket.amount = self._compound(bucket.amount, NEW_MONEY_RATE, current, next_roll)
            rolling = [bucket for bucket in active_buckets if bucket.roll_date == next_roll]
            if rolling:
                portfolio += sum((bucket.amount for bucket in rolling), Decimal("0"))
                active_buckets = [bucket for bucket in active_buckets if bucket.roll_date != next_roll]
            current = next_roll
        return portfolio, active_buckets

    @staticmethod
    def _compound(amount: Decimal, annual_rate: Decimal, start_date: date, end_date: date) -> Decimal:
        days = AnnuityRiderTab._cyberlife_interest_days(start_date, end_date)
        if days <= 0 or amount == 0:
            return amount
        factor = math.pow(float(Decimal("1") + annual_rate), days / 365.0)
        return amount * Decimal(str(factor))

    @staticmethod
    def _cyberlife_interest_days(start_date: date, end_date: date) -> int:
        days = (end_date - start_date).days
        leap_days = 0
        for year in range(start_date.year, end_date.year + 1):
            if calendar.isleap(year):
                leap_day = date(year, 2, 29)
                if start_date <= leap_day < end_date:
                    leap_days += 1
        return days - leap_days

    @staticmethod
    def _new_money_roll_date(effective_date: date) -> date:
        roll_year = effective_date.year + 1
        roll_month = effective_date.month
        return date(roll_year, roll_month, calendar.monthrange(roll_year, roll_month)[1])

    @staticmethod
    def _month_ends(start_date: date, end_date: date) -> Iterable[date]:
        year = start_date.year
        month = start_date.month
        while True:
            month_end = date(year, month, calendar.monthrange(year, month)[1])
            if month_end > end_date:
                break
            if month_end >= start_date:
                yield month_end
            month += 1
            if month == 13:
                month = 1
                year += 1

    @staticmethod
    def _add_years(value: date, years: int) -> date:
        try:
            return value.replace(year=value.year + years)
        except ValueError:
            return value.replace(year=value.year + years, day=28)

    @staticmethod
    def _last_day_of_month(value: date) -> int:
        return calendar.monthrange(value.year, value.month)[1]

    @staticmethod
    def _parse_date(value) -> date | None:
        if isinstance(value, datetime):
            return value.date()
        if isinstance(value, date):
            return value
        text = str(value or "").strip()
        if not text or text.lower() in {"none", "null"}:
            return None
        for fmt in ("%Y-%m-%d", "%m/%d/%Y", "%Y%m%d"):
            try:
                return datetime.strptime(text[:10] if fmt == "%Y-%m-%d" else text, fmt).date()
            except ValueError:
                continue
        return None

    @staticmethod
    def _parse_amount(value) -> Decimal | None:
        if value is None:
            return None
        text = str(value).strip().replace("$", "").replace(",", "")
        if not text or text.lower() in {"none", "null"}:
            return None
        try:
            return Decimal(text)
        except (InvalidOperation, ValueError):
            return None

    @staticmethod
    def _parse_int(value) -> int:
        try:
            return int(value or 0)
        except (TypeError, ValueError):
            return 0