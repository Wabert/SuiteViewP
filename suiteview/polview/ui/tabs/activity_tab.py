"""
Activity tab – transaction types on this policy and the Policy Transactions table.

The left panel lists the transaction codes that actually occur on the policy
(with counts); clicking one filters the transactions to that code. Reversal
indicators are spelled out and reversed/reversing entries are dimmed so the
net activity stands out. A footer totals the rows currently shown.
"""

from PyQt6.QtWidgets import QCheckBox, QHBoxLayout, QLabel, QTableWidgetItem, QWidget
from PyQt6.QtCore import Qt, pyqtSlot
from PyQt6.QtGui import QColor, QFont

from ...models.cl_polrec.policy_translations import TRANSACTION_CODES
from ..formatting import format_currency, format_date, format_rate
from ..styles import GRAY_TEXT, GREEN_DARK
from ..widgets import StyledInfoTableGroup, parse_number

from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from ...models.policy_information import PolicyInformation

LEFT_ALIGN = Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter
TRANSACTION_COLUMNS = [
    "Eff Date", "SeqNo", "Code", "Description", "Gross Amt", "Net Amt",
    "Fund", "Phs", "Int Rate", "Reversal", "Entry Date", "Origin",
]
CODE_COLUMN = TRANSACTION_COLUMNS.index("Code")
GROSS_COLUMN = TRANSACTION_COLUMNS.index("Gross Amt")
NET_COLUMN = TRANSACTION_COLUMNS.index("Net Amt")
_DIMMED = QColor("#9AA5B1")


def reversal_text(rev_ind: str, rev_applied: str) -> str:
    """Spell out FCB0_REV_IND (is a reversal) and FCB2_REV_APPL_IND (was reversed)."""
    is_reversal = str(rev_ind or "").strip() == "1"
    was_reversed = str(rev_applied or "").strip() == "1"
    if is_reversal and was_reversed:
        return "Reversal (reversed)"
    if is_reversal:
        return "Reversal"
    if was_reversed:
        return "Reversed"
    return ""


def transaction_description(code: str) -> str:
    return TRANSACTION_CODES.get(str(code or "").strip(), "")


class ActivityTab(QWidget):
    """Tab for Activity/Financial History."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._counts: dict[str, int] = {}
        self._setup_ui()

    def _setup_ui(self):
        main_layout = QHBoxLayout(self)
        main_layout.setSpacing(10)
        self._create_transaction_index(main_layout)
        self._create_transaction_table(main_layout)

    def _create_transaction_index(self, parent_layout):
        self.index_group = StyledInfoTableGroup("Transaction Types", show_info=False, show_table=True)
        self.index_group.table.setColumnCount(3)
        self.index_group.table.setHorizontalHeaderLabels(["Code", "Description", "Count"])
        self.index_group.table.align_headers_left({"Code", "Description"})
        self.index_group.table.set_empty_message("No transactions")
        index_view = self.index_group.table._data_table
        index_view.setSelectionBehavior(index_view.SelectionBehavior.SelectRows)
        index_view.setSelectionMode(index_view.SelectionMode.SingleSelection)
        index_view.itemClicked.connect(self._on_index_clicked)
        index_view.setCursor(Qt.CursorShape.PointingHandCursor)
        self.index_group.table.setToolTip("Click a transaction type to show only those transactions")
        self.show_all_codes = QCheckBox("Show every CyberLife code")
        self.show_all_codes.setStyleSheet(f"font-size: 10px; color: {GRAY_TEXT};")
        self.show_all_codes.toggled.connect(self._rebuild_index)
        self.index_group.layout().addWidget(self.show_all_codes)
        self.index_group.setFixedWidth(330)
        parent_layout.addWidget(self.index_group)

    def _create_transaction_table(self, parent_layout):
        self.transactions_group = StyledInfoTableGroup(
            "Policy Transactions", show_info=False, show_table=True, filterable=True)
        table = self.transactions_group.table
        table.setColumnCount(len(TRANSACTION_COLUMNS))
        table.setHorizontalHeaderLabels(TRANSACTION_COLUMNS)
        table.align_headers_left({"Description"})
        table.set_empty_message("No transactions found for this policy.")
        table.set_column_settings_key("polview.activity")
        table.filters_changed.connect(self._update_footer)
        self.footer_label = QLabel("")
        self.footer_label.setStyleSheet(
            f"font-size: 10px; color: {GREEN_DARK}; background: transparent; padding: 1px 4px;"
        )
        self.footer_label.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        self.transactions_group.layout().addWidget(self.footer_label)
        parent_layout.addWidget(self.transactions_group, 1)

    # ── helpers ──────────────────────────────────────────────────────────

    def _populate_row(self, table, row_idx, data):
        code = str(data.get("TRANS", "")).strip()
        fund_id = data.get("FUND_ID")
        reversal = reversal_text(data.get("FCB0_REV_IND", ""), data.get("FCB2_REV_APPL_IND", ""))
        values = [
            format_date(data.get("ASOF_DT")),
            str(data.get("SEQ_NO", "")),
            code,
            transaction_description(code),
            format_currency(data.get("GROSS_AMT")),
            format_currency(data.get("NET_AMT")),
            "" if fund_id is None or str(fund_id).strip().lower() == "null" else str(fund_id).strip(),
            str(data.get("FNDVAL_PH", "")).strip(),
            format_rate(data.get("INT_RT")),
            reversal,
            format_date(data.get("ENTRY_DT")),
            str(data.get("ORIGIN_OF_TRANS", "")).strip(),
        ]
        for col, value in enumerate(values):
            item = QTableWidgetItem(value)
            if reversal:
                item.setForeground(_DIMMED)
                font = QFont(item.font())
                font.setItalic(True)
                item.setFont(font)
                item.setToolTip("Reversed or reversing entry (FCB0_REV_IND / FCB2_REV_APPL_IND)")
            table.setItem(row_idx, col, item,
                          alignment=LEFT_ALIGN if col == TRANSACTION_COLUMNS.index("Description") else None)

    @pyqtSlot()
    def _rebuild_index(self, *_args):
        table = self.index_group.table
        codes = dict(self._counts)
        if self.show_all_codes.isChecked():
            for code in TRANSACTION_CODES:
                codes.setdefault(code, 0)
        rows = sorted(codes.items())
        total = sum(self._counts.values())
        table.setRowCount(len(rows) + (1 if total else 0))
        offset = 0
        if total:
            for col, value in enumerate(("All", "All transactions", str(total))):
                item = QTableWidgetItem(value)
                font = QFont(item.font())
                font.setBold(True)
                item.setFont(font)
                table.setItem(0, col, item, alignment=LEFT_ALIGN if col < 2 else None)
            offset = 1
        for row, (code, count) in enumerate(rows, start=offset):
            for col, value in enumerate((code, TRANSACTION_CODES.get(code, ""), str(count) if count else "")):
                item = QTableWidgetItem(value)
                if not count:
                    item.setForeground(_DIMMED)
                table.setItem(row, col, item, alignment=LEFT_ALIGN if col < 2 else None)
        table.autoFitAllColumns()

    @pyqtSlot(QTableWidgetItem)
    def _on_index_clicked(self, item):
        code_item = self.index_group.table.item(item.row(), 0)
        if code_item is None:
            return
        self.filter_code(None if code_item.text() == "All" else code_item.text())

    def filter_code(self, code):
        """Show only *code* transactions (``None`` shows all)."""
        table = self.transactions_group.table
        if code is None:
            table.filter_column(CODE_COLUMN, set())
        else:
            table.filter_column(CODE_COLUMN, {code})

    @pyqtSlot()
    def _update_footer(self):
        table = self.transactions_group.table
        rows = table.visible_row_indexes()
        total = table.rowCount()
        if not total or (total == 1 and not table.item(0, CODE_COLUMN)):
            self.footer_label.setText("")
            return

        def column_sum(col):
            values = [parse_number(table.item(r, col).text()) for r in rows if table.item(r, col)]
            return sum(v for v in values if v is not None)

        shown = f"Showing {len(rows):,} of {total:,}" if len(rows) != total else f"{total:,} transactions"
        self.footer_label.setText(
            f"{shown}   ·   Gross Σ {column_sum(GROSS_COLUMN):,.2f}   ·   Net Σ {column_sum(NET_COLUMN):,.2f}"
            "   (reversed entries included)"
        )

    # ── data loading ─────────────────────────────────────────────────────

    def load_data_from_policy(self, policy: 'PolicyInformation'):
        table = self.transactions_group.table
        try:
            rows = policy.fetch_table("FH_FIXED")
            table.clear_filters()
            table.setRowCount(0)  # clear all old data first
            self._counts = {}
            if not rows:
                self._rebuild_index()
                self._update_footer()
                return

            rows = sorted(rows, key=lambda x: (str(x.get("ASOF_DT", "")), int(x.get("SEQ_NO", 0) or 0)), reverse=True)
            table.setRowCount(len(rows))
            for row_idx, data in enumerate(rows):
                self._populate_row(table, row_idx, data)
                code = str(data.get("TRANS", "")).strip()
                self._counts[code] = self._counts.get(code, 0) + 1
            table.autoFitAllColumns()
            self._rebuild_index()
            self._update_footer()

        except Exception as e:
            table.setRowCount(0)  # clear all old data first
            table.setRowCount(1)
            table.setItem(0, 0, QTableWidgetItem(f"Error: {e}"))
            raise
