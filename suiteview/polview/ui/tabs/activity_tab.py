"""
Activity tab – Transaction Type Index and Policy Transactions table.
"""

from PyQt6.QtWidgets import QWidget, QHBoxLayout, QTableWidgetItem
from PyQt6.QtCore import Qt

from ...models.cl_polrec.policy_translations import TRANSACTION_CODES
from ..formatting import format_currency, format_date, format_rate
from ..widgets import StyledInfoTableGroup

from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from ...models.policy_information import PolicyInformation


class ActivityTab(QWidget):
    """Tab for Activity/Financial History - matches VBA SuiteView layout."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._setup_ui()

    def _setup_ui(self):
        main_layout = QHBoxLayout(self)
        main_layout.setSpacing(10)

        self._create_transaction_index(main_layout)
        self._create_transaction_table(main_layout)

    def _create_transaction_index(self, parent_layout):
        self.index_group = StyledInfoTableGroup("Transaction Type Index", show_info=False, show_table=True)
        self.index_group.table.setColumnCount(1)
        self.index_group.table.setHorizontalHeaderLabels(["Transaction Type"])
        # Left-align the header for this table
        h = self.index_group.table._data_table.horizontalHeaderItem(0)
        if h:
            h.setTextAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)

        LEFT_ALIGN = Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter
        sorted_codes = sorted(TRANSACTION_CODES.items())
        self.index_group.table.setRowCount(len(sorted_codes))
        for row_idx, (code, description) in enumerate(sorted_codes):
            self.index_group.table.setItem(row_idx, 0, QTableWidgetItem(f"{code} - {description}"), alignment=LEFT_ALIGN)
        self.index_group.table.autoFitAllColumns()
        self.index_group.setFixedWidth(295)
        parent_layout.addWidget(self.index_group)

    def _create_transaction_table(self, parent_layout):
        self.transactions_group = StyledInfoTableGroup("Policy Transactions", show_info=False, show_table=True, filterable=True)
        self.transactions_group.table.setColumnCount(11)
        self.transactions_group.table.setHorizontalHeaderLabels([
            "Eff Date", "SeqNo", "Code", "Gross Amt", "Net Amt",
            "Fund", "Phs", "Int Rate", "Reversal", "Entry Date", "Origin",
        ])
        parent_layout.addWidget(self.transactions_group, 1)

    # ── helpers ──────────────────────────────────────────────────────────

    def _populate_row(self, table, row_idx, data):
        table.setItem(row_idx, 0, QTableWidgetItem(format_date(data.get("ASOF_DT"))))
        table.setItem(row_idx, 1, QTableWidgetItem(str(data.get("SEQ_NO", ""))))
        table.setItem(row_idx, 2, QTableWidgetItem(str(data.get("TRANS", "")).strip()))
        table.setItem(row_idx, 3, QTableWidgetItem(format_currency(data.get("GROSS_AMT"))))
        table.setItem(row_idx, 4, QTableWidgetItem(format_currency(data.get("NET_AMT"))))

        fund_id = data.get("FUND_ID")
        table.setItem(row_idx, 5, QTableWidgetItem(
            "" if fund_id is None or str(fund_id).strip().lower() == "null" else str(fund_id).strip()
        ))
        table.setItem(row_idx, 6, QTableWidgetItem(str(data.get("FNDVAL_PH", "")).strip()))
        table.setItem(row_idx, 7, QTableWidgetItem(format_rate(data.get("INT_RT"))))

        rev_ind = str(data.get("FCB0_REV_IND", "")).strip()
        rev_appl = str(data.get("FCB2_REV_APPL_IND", "")).strip()
        if rev_ind == "1" and rev_appl == "1":
            reversal = "RR"
        elif rev_ind == "1":
            reversal = "Rev"
        elif rev_appl == "1":
            reversal = "RV"
        else:
            reversal = ""
        table.setItem(row_idx, 8, QTableWidgetItem(reversal))
        table.setItem(row_idx, 9, QTableWidgetItem(format_date(data.get("ENTRY_DT"))))
        table.setItem(row_idx, 10, QTableWidgetItem(str(data.get("ORIGIN_OF_TRANS", "")).strip()))

    # ── data loading ─────────────────────────────────────────────────────

    def load_data_from_policy(self, policy: 'PolicyInformation'):
        try:
            rows = policy.fetch_table("FH_FIXED")
            table = self.transactions_group.table
            table.setRowCount(0)  # clear all old data first

            if not rows:
                table.setRowCount(1)
                table.setItem(0, 0, QTableWidgetItem("No transactions found"))
                return

            rows = sorted(rows, key=lambda x: (str(x.get("ASOF_DT", "")), int(x.get("SEQ_NO", 0) or 0)), reverse=True)
            table.setRowCount(len(rows))
            for row_idx, data in enumerate(rows):
                self._populate_row(table, row_idx, data)
            table.autoFitAllColumns()

        except Exception as e:
            table = self.transactions_group.table
            table.setRowCount(0)  # clear all old data first
            table.setRowCount(1)
            table.setItem(0, 0, QTableWidgetItem(f"Error: {e}"))
