"""
Dividends tab – Unapplied, PUA, OYT, and On Deposit dividend sections.
"""

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QScrollArea, QFrame, QTableWidgetItem,
)

from ..formatting import format_date, US_DATE_FMT
from ..widgets import StyledTableGroup


class DividendsTab(QWidget):
    """
    Tab for displaying dividend information for participating policies.
    Based on VBA frmPolicyMasterTV Dividends tab.

    Sections:
    - Unapplied (18/19 Seg) - from LH_UNAPPLIED_PTP
    - Paid Up Additions (14 Seg) - from LH_PAID_UP_ADD
    - One Year Term (15 Seg) - from LH_ONE_YR_TRM_ADD
    - On Deposit (13 Seg) - from LH_PTP_ON_DEP
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self._setup_ui()

    def _setup_ui(self):
        """Setup the dividends tab layout."""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(6)

        # Create scroll area for the content
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)

        content = QWidget()
        content_layout = QVBoxLayout(content)
        content_layout.setContentsMargins(0, 0, 0, 0)
        content_layout.setSpacing(8)

        # Unapplied Dividends section (18/19 Seg)
        self.unapplied_group = StyledTableGroup("Unapplied (18/19 Seg)")
        self.unapplied_group.table.setColumnCount(15)
        self.unapplied_group.table.setHorizontalHeaderLabels([
            "Type", "Date", "Cov", "FromPUA", "Cash Rt", "Cash Proj", "Cash Int",
            "PUA Rt", "PUA Units", "PUA Mort", "PUA Int", "PUA Mat Dur",
            "OYT Rt", "OYT Mort", "OYT Int",
        ])
        content_layout.addWidget(self.unapplied_group)

        # Bottom row with three sections side by side
        bottom_row = QHBoxLayout()
        bottom_row.setSpacing(8)

        # Paid Up Additions section (14 Seg)
        self.pua_group = StyledTableGroup("Paid Up Additions (14 Seg)")
        self.pua_group.table.setColumnCount(7)
        self.pua_group.table.setHorizontalHeaderLabels([
            "Eff Date", "Phs", "FromPrem", "Mat Date", "Amount", "Mort Tbl", "Int Rate",
        ])
        bottom_row.addWidget(self.pua_group, 1)

        # One Year Term section (15 Seg)
        self.oyt_group = StyledTableGroup("One Year Term (15 Seg)")
        self.oyt_group.table.setColumnCount(5)
        self.oyt_group.table.setHorizontalHeaderLabels([
            "Eff Date", "Mat Date", "Amount", "Mort Tbl", "Int Rate",
        ])
        bottom_row.addWidget(self.oyt_group, 1)

        content_layout.addLayout(bottom_row)

        # On Deposit section (13 Seg)
        self.deposit_group = StyledTableGroup("On Deposit (13 Seg)")
        self.deposit_group.table.setColumnCount(6)
        self.deposit_group.table.setHorizontalHeaderLabels([
            "Last Ann", "Interest Date", "Amount", "Int Rate", "Int Withheld", "Interest On WD",
        ])
        content_layout.addWidget(self.deposit_group)

        content_layout.addStretch()

        scroll.setWidget(content)
        layout.addWidget(scroll)

    # ── public helpers ───────────────────────────────────────────────────

    def has_dividend_data(self, policy) -> bool:
        """Check if policy has any dividend data to display."""
        if not policy:
            return False
        try:
            unapplied_count = policy.data_item_count("LH_UNAPPLIED_PTP")
            oyt_count = policy.data_item_count("LH_ONE_YR_TRM_ADD")
            deposit_count = policy.data_item_count("LH_PTP_ON_DEP")
            pua_count = policy.data_item_count("LH_PAID_UP_ADD")
            has_data = (unapplied_count > 0 or oyt_count > 0
                        or deposit_count > 0 or pua_count > 0)
            return has_data
        except Exception as e:
            pass
            return False

    # ── data loading ─────────────────────────────────────────────────────

    def load_data_from_policy(self, policy):
        """Load dividend data from PolicyInformation object."""
        if not policy:
            return

        try:
            # Get coverage issue date for date calculations
            cov_issue_date = policy.cov_issue_date(1) if policy.coverage_count > 0 else None
            issue_day = cov_issue_date.day if cov_issue_date else 1

            # Load each section
            self._load_unapplied(policy, issue_day)
            self._load_pua(policy, issue_day)
            self._load_oyt(policy, issue_day)
            self._load_deposit(policy, issue_day)

        except Exception as e:
            import traceback, sys
            print(f"[DividendsTab] Error loading data: {e}", file=sys.stderr)
            traceback.print_exc(file=sys.stderr)

    # ── private helpers ──────────────────────────────────────────────────

    def _months_to_date(self, months_from_1900: int, day: int = 1) -> str:
        """Convert months from 1/1/1900 to a date string m/yyyy format."""
        if not months_from_1900:
            return ""
        try:
            year = 1900 + (months_from_1900 - 1) // 12
            month = ((months_from_1900 - 1) % 12) + 1
            return f"{month}/{year}"
        except Exception:
            return str(months_from_1900)

    def _load_unapplied(self, policy, issue_day: int):
        """Load Unapplied Dividends table."""
        table = self.unapplied_group.table
        table.setRowCount(0)

        try:
            rows = policy.fetch_table("LH_UNAPPLIED_PTP")
            if not rows:
                return

            table.setRowCount(len(rows))
            for row_idx, row in enumerate(rows):
                div_type = str(row.get("CK_PTP_TYP_CD", "") or "")
                table.setItem(row_idx, 0, QTableWidgetItem(div_type))

                date_months = row.get("ERN_DT_MO_YR_NBR")
                date_str = self._months_to_date(int(date_months) if date_months else 0, issue_day)
                table.setItem(row_idx, 1, QTableWidgetItem(date_str))

                table.setItem(row_idx, 2, QTableWidgetItem(str(row.get("COV_PHA_NBR", "") or "")))
                table.setItem(row_idx, 3, QTableWidgetItem(str(row.get("PTP_SRC_IND", "") or "")))

                cash_rt = row.get("CSH_AMT")
                table.setItem(row_idx, 4, QTableWidgetItem(f"{float(cash_rt):.2f}" if cash_rt else ""))

                cash_proj = row.get("PRJ_CSH_AMT")
                table.setItem(row_idx, 5, QTableWidgetItem(f"{float(cash_proj):.2f}" if cash_proj else ""))

                cash_int = row.get("DEP_ITS_RT")
                if cash_int:
                    table.setItem(row_idx, 6, QTableWidgetItem(f"{float(cash_int)/100:.2%}"))
                else:
                    table.setItem(row_idx, 6, QTableWidgetItem(""))

                pua_rt = row.get("PUA_AMT")
                table.setItem(row_idx, 7, QTableWidgetItem(f"{float(pua_rt):.2f}" if pua_rt else ""))

                pua_units = row.get("PUA_UNT_QTY")
                table.setItem(row_idx, 8, QTableWidgetItem(f"{float(pua_units):.3f}" if pua_units else ""))

                table.setItem(row_idx, 9, QTableWidgetItem(str(row.get("PUA_MTL_TBL_CD", "") or "")))

                pua_int = row.get("PUA_ITS_RT")
                if pua_int:
                    table.setItem(row_idx, 10, QTableWidgetItem(f"{float(pua_int)/100:.2%}"))
                else:
                    table.setItem(row_idx, 10, QTableWidgetItem(""))

                table.setItem(row_idx, 11, QTableWidgetItem(str(row.get("PUA_MT_DUR", "") or "")))

                oyt_rt = row.get("OYT_AMT")
                table.setItem(row_idx, 12, QTableWidgetItem(f"{float(oyt_rt):.2f}" if oyt_rt else ""))

                table.setItem(row_idx, 13, QTableWidgetItem(str(row.get("OYT_MTL_TBL_CD", "") or "")))

                oyt_int = row.get("OYT_ITS_RT")
                if oyt_int:
                    table.setItem(row_idx, 14, QTableWidgetItem(f"{float(oyt_int)/100:.2%}"))
                else:
                    table.setItem(row_idx, 14, QTableWidgetItem(""))

            table.autoFitAllColumns()
        except Exception as e:
            pass

    def _load_pua(self, policy, issue_day: int):
        """Load Paid Up Additions table."""
        table = self.pua_group.table
        table.setRowCount(0)

        try:
            rows = policy.fetch_table("LH_PAID_UP_ADD")
            if not rows:
                return

            table.setRowCount(len(rows))
            for row_idx, row in enumerate(rows):
                eff_date = row.get("MVRY_DT")
                table.setItem(row_idx, 0, QTableWidgetItem(format_date(eff_date, US_DATE_FMT)))

                table.setItem(row_idx, 1, QTableWidgetItem(str(row.get("COV_PHA_NBR", "") or "")))
                table.setItem(row_idx, 2, QTableWidgetItem(str(row.get("PUA_PUR_SRC_CD", "") or "")))

                mat_date_months = row.get("PUA_MT_MO_YR_NBR")
                mat_date_str = self._months_to_date(int(mat_date_months) if mat_date_months else 0, issue_day)
                table.setItem(row_idx, 3, QTableWidgetItem(mat_date_str))

                amount = row.get("PUA_AMT")
                table.setItem(row_idx, 4, QTableWidgetItem(f"{float(amount):,.2f}" if amount else ""))

                table.setItem(row_idx, 5, QTableWidgetItem(str(row.get("PUA_MTL_TBL_CD", "") or "")))

                int_rate = row.get("PUA_ITS_RT")
                if int_rate:
                    table.setItem(row_idx, 6, QTableWidgetItem(f"{float(int_rate)/100:.2%}"))
                else:
                    table.setItem(row_idx, 6, QTableWidgetItem(""))

            table.autoFitAllColumns()
        except Exception as e:
            pass

    def _load_oyt(self, policy, issue_day: int):
        """Load One Year Term table."""
        table = self.oyt_group.table
        table.setRowCount(0)

        try:
            rows = policy.fetch_table("LH_ONE_YR_TRM_ADD")
            if not rows:
                return

            table.setRowCount(len(rows))
            for row_idx, row in enumerate(rows):
                eff_date = row.get("MVRY_DT")
                table.setItem(row_idx, 0, QTableWidgetItem(format_date(eff_date, US_DATE_FMT)))

                mat_date_months = row.get("OYT_EXP_MO_YR_NBR")
                mat_date_str = self._months_to_date(int(mat_date_months) if mat_date_months else 0, issue_day)
                table.setItem(row_idx, 1, QTableWidgetItem(mat_date_str))

                amount = row.get("OYT_ADD_AMT")
                table.setItem(row_idx, 2, QTableWidgetItem(f"{float(amount):,.2f}" if amount else ""))

                table.setItem(row_idx, 3, QTableWidgetItem(str(row.get("OYT_MTL_TBL_CD", "") or "")))

                int_rate = row.get("OYT_ITS_RT")
                table.setItem(row_idx, 4, QTableWidgetItem(f"{float(int_rate):.2f}" if int_rate else ""))

            table.autoFitAllColumns()
        except Exception as e:
            pass

    def _load_deposit(self, policy, issue_day: int):
        """Load On Deposit table."""
        table = self.deposit_group.table
        table.setRowCount(0)

        try:
            rows = policy.fetch_table("LH_PTP_ON_DEP")
            if not rows:
                return

            table.setRowCount(len(rows))
            for row_idx, row in enumerate(rows):
                last_ann = row.get("MVRY_DT")
                table.setItem(row_idx, 0, QTableWidgetItem(format_date(last_ann, US_DATE_FMT)))

                int_date_months = row.get("ITS_APP_MO_YR_NBR")
                int_date_str = self._months_to_date(int(int_date_months) if int_date_months else 0, issue_day)
                table.setItem(row_idx, 1, QTableWidgetItem(int_date_str))

                amount = row.get("PTP_DEP_AMT")
                table.setItem(row_idx, 2, QTableWidgetItem(f"{float(amount):,.2f}" if amount else ""))

                int_rate = row.get("DEP_ITS_RT")
                if int_rate:
                    table.setItem(row_idx, 3, QTableWidgetItem(f"{float(int_rate)/100:.2%}"))
                else:
                    table.setItem(row_idx, 3, QTableWidgetItem(""))

                int_withheld = row.get("ACU_ITS_WHD_AMT")
                table.setItem(row_idx, 4, QTableWidgetItem(
                    f"{float(int_withheld):,.2f}" if int_withheld else ""))

                int_on_wd = row.get("PRE_WTD_ITS_AMT")
                table.setItem(row_idx, 5, QTableWidgetItem(
                    f"{float(int_on_wd):,.2f}" if int_on_wd else ""))

            table.autoFitAllColumns()
        except Exception as e:
            pass
