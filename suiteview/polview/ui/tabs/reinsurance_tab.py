"""
Reinsurance tab – Displays TAI Cession records for the current policy.

Queries the TAICession table in the UL_Rates database via the shared
suiteview.core.reinsurance module.  Shows all cession records for the
latest month-end date, or a "not found" message when no records exist.

Also checks whether the policy number exists under multiple Cyberlife
companies and displays a prominent notice if so (since TAICession is
queried by policy number only, to capture intercompany cessions).
"""

import calendar
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QScrollArea, QFrame, QLabel, QTableWidgetItem,
)
from PyQt6.QtCore import Qt

from suiteview.core.reinsurance import (
    fetch_tai_cession, TAICessionResult, TAI_CESSION_HEADERS,
)
from ..widgets import StyledTableGroup


def _format_month_end(yyyymm: str) -> str:
    """Convert '202602' to 'end of Feb 2026'."""
    yyyymm = str(yyyymm).strip()
    if len(yyyymm) < 6:
        return yyyymm
    try:
        year = int(yyyymm[:4])
        month = int(yyyymm[4:6])
        month_abbr = calendar.month_abbr[month]
        return f"end of {month_abbr} {year}"
    except (ValueError, IndexError):
        return yyyymm


class ReinsuranceTab(QWidget):
    """
    Tab for displaying TAI Cession (reinsurance) records for a policy.
    Always shown in main_window — displays either data or a "not found" msg.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self._last_result: TAICessionResult | None = None
        self._setup_ui()

    def _setup_ui(self):
        """Setup the reinsurance tab layout."""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(6)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)

        content = QWidget()
        content_layout = QVBoxLayout(content)
        content_layout.setContentsMargins(0, 0, 0, 0)
        content_layout.setSpacing(8)

        # ── Search summary label (always visible) ───────────────────────
        self._summary_label = QLabel("")
        self._summary_label.setStyleSheet(
            "font-size: 13px; font-weight: bold; color: #1B5E20; "
            "padding: 6px 8px; background: transparent;"
        )
        self._summary_label.setWordWrap(True)
        content_layout.addWidget(self._summary_label)

        # ── Multi-company warning (hidden by default) ───────────────────
        self._multi_co_label = QLabel("")
        self._multi_co_label.setStyleSheet(
            "font-size: 12px; font-weight: bold; color: #FFFFFF; "
            "background-color: #C62828; padding: 8px 12px; "
            "border-radius: 4px;"
        )
        self._multi_co_label.setWordWrap(True)
        self._multi_co_label.setVisible(False)
        content_layout.addWidget(self._multi_co_label)

        # ── Cession table ───────────────────────────────────────────────
        self.cession_group = StyledTableGroup("TAI Cession Records")
        self.cession_group.table.setColumnCount(len(TAI_CESSION_HEADERS))
        self.cession_group.table.setHorizontalHeaderLabels(TAI_CESSION_HEADERS)
        content_layout.addWidget(self.cession_group)

        # ── "No records" message label (hidden by default) ──────────────
        self._no_data_label = QLabel("")
        self._no_data_label.setStyleSheet(
            "font-size: 12px; font-weight: bold; color: #8B0000; "
            "padding: 12px; background: transparent;"
        )
        self._no_data_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._no_data_label.setVisible(False)
        content_layout.addWidget(self._no_data_label)

        content_layout.addStretch()

        scroll.setWidget(content)
        layout.addWidget(scroll)

    # ── public helpers ───────────────────────────────────────────────────

    def has_reinsurance_data(self, policy) -> bool:
        """Query TAICession and return True if records exist for this policy."""
        if not policy:
            return False
        try:
            result = fetch_tai_cession(policy.policy_number)
            self._last_result = result
            return result.found
        except Exception:
            self._last_result = None
            return False

    # ── data loading ─────────────────────────────────────────────────────

    def load_data_from_policy(self, policy):
        """Load reinsurance data from the cached TAICession result."""
        if not policy:
            return

        # Use cached result from has_reinsurance_data() if available,
        # otherwise query fresh
        result = self._last_result
        if result is None:
            try:
                result = fetch_tai_cession(policy.policy_number)
            except Exception as e:
                import traceback, sys
                print(f"[ReinsuranceTab] Error: {e}", file=sys.stderr)
                traceback.print_exc(file=sys.stderr)
                return

        # ── Build search summary text ───────────────────────────────────
        co_code = getattr(policy, "company_code", "") or ""
        pol_num = getattr(policy, "policy_number", "") or ""
        policy_display = f"{co_code}-{pol_num}" if co_code else pol_num
        month_end_display = _format_month_end(result.month_end)

        self._summary_label.setText(
            f"Reinsurance table results for {month_end_display} "
            f"for {policy_display}"
        )

        # ── Multi-company check ─────────────────────────────────────────
        self._multi_co_label.setVisible(False)
        try:
            from ...models.policy_information import PolicyInformation
            region = getattr(policy, "region", "CKPR") or "CKPR"
            companies = PolicyInformation.find_companies(pol_num, region)
            if len(companies) > 1:
                co_list = ", ".join(companies)
                self._multi_co_label.setText(
                    f"⚠  This policy number exists in {len(companies)} "
                    f"Cyberlife companies: {co_list}.  "
                    f"TAICession records below are for ALL companies "
                    f"(matched on policy number only)."
                )
                self._multi_co_label.setVisible(True)
        except Exception:
            pass  # If company check fails, just skip it

        # ── Populate table or show "not found" ──────────────────────────
        table = self.cession_group.table

        if result.found and result.rows:
            self._no_data_label.setVisible(False)
            self.cession_group.setVisible(True)

            table.setRowCount(len(result.rows))
            for row_idx, row_data in enumerate(result.rows):
                for col_idx, col_name in enumerate(TAI_CESSION_HEADERS):
                    value = row_data.get(col_name, "")
                    text = str(value).strip() if value is not None else ""
                    item = QTableWidgetItem(text)
                    item.setTextAlignment(
                        Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
                    )
                    table.setItem(row_idx, col_idx, item)

            table.autoFitAllColumns()
        else:
            table.setRowCount(0)
            self.cession_group.setVisible(False)
            self._no_data_label.setText(
                f"No reinsurance records found in the TAI Cession file "
                f"as of month end date = {result.month_end}"
            )
            self._no_data_label.setVisible(True)

        # Clear cached result
        self._last_result = None
