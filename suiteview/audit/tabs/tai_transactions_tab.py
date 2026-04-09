"""
TAICyberTAIFd tab — filter criteria for the TAICyberTAIFd table.

Layout similar to TAI_Cession but without Compare, ReinsCo, RepCo,
ReinsType, Mode, RGA, or Inforce controls.
"""
from __future__ import annotations

import logging
import pyodbc

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGridLayout,
    QLabel, QLineEdit, QComboBox, QCheckBox, QPushButton,
    QListWidget, QAbstractItemView, QGroupBox, QMessageBox,
)
from PyQt6.QtGui import QFont

from ._styles import (
    make_checkbox, make_listbox, make_combo, style_combo,
    connect_checkbox_listbox, TightItemDelegate,
)

logger = logging.getLogger(__name__)

_FONT = QFont("Segoe UI", 9)
_FONT_BOLD = QFont("Segoe UI", 9, QFont.Weight.Bold)
_CTRL_H = 22

_DSN = "UL_Rates"

STATUS_CODE_ITEMS = [
    "CNT - Converted",
    "DTH - Death",
    "ETI - Extended Term",
    "EXP - Expired",
    "LAP - Lapsed",
    "NTO - Not Taken Out",
    "PDT - Pending Death",
    "PDU - Paid Up",
    "PMP - Prem Paying",
    "RPU - Reduced Paid Up",
    "SUR - Surrendered",
    "TRM",
    "WOP - Waiver of Prem",
]

PRODCD_ITEMS = ["T", "U", "V", "W"]
COMPANY_ITEMS = ["101", "104", "106", "108", "130", "FFL"]

POLICYNUMBER_CRITERIA = ["0 - Match", "1 - Starts with", "2 - Contains"]
PLANCODE_CRITERIA = ["0 - Match", "1 - Starts with", "2 - Contains"]

TABLE_ITEMS = ["(none)", "TAICyberTAIFd"]


class TaiTransactionsTab(QWidget):
    """TAICyberTAIFd tab — filter criteria for TAICyberTAIFd queries."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._build_ui()

    # ── UI construction ──────────────────────────────────────────────

_RANGE_W = 80        # width of date range text inputs
_RANGE_LABEL_W = 130 # width of range-row labels


def _add_date_range_row(layout: QGridLayout, row: int,
                        label_text: str) -> tuple[QLineEdit, QLineEdit]:
    """Add a label | lo | 'to' | hi date range row and return (lo, hi)."""
    lbl = QLabel(label_text)
    lbl.setFont(_FONT)
    lbl.setFixedWidth(_RANGE_LABEL_W)
    lbl.setFixedHeight(_CTRL_H)

    lo = QLineEdit()
    lo.setFont(_FONT)
    lo.setFixedWidth(_RANGE_W)
    lo.setFixedHeight(_CTRL_H)
    lo.setPlaceholderText("m/d/yyyy")

    lbl_to = QLabel("to")
    lbl_to.setFont(_FONT)
    lbl_to.setFixedWidth(16)
    lbl_to.setAlignment(Qt.AlignmentFlag.AlignCenter)

    hi = QLineEdit()
    hi.setFont(_FONT)
    hi.setFixedWidth(_RANGE_W)
    hi.setFixedHeight(_CTRL_H)
    hi.setPlaceholderText("m/d/yyyy")

    layout.addWidget(lbl, row, 0)
    layout.addWidget(lo, row, 1)
    layout.addWidget(lbl_to, row, 2)
    layout.addWidget(hi, row, 3)
    return lo, hi


class TaiTransactionsTab(QWidget):
    """TAICyberTAIFd tab — filter criteria for TAICyberTAIFd queries."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._build_ui()

    # ── UI construction ──────────────────────────────────────────────

    def _build_ui(self):
        root = QHBoxLayout(self)
        root.setContentsMargins(6, 6, 6, 4)
        root.setSpacing(8)

        # ── LEFT column: Table selector + Date Range + Get Dates ─────
        left_widget = QWidget()
        left_widget.setMaximumWidth(200)
        left_col = QVBoxLayout(left_widget)
        left_col.setSpacing(4)
        left_col.setContentsMargins(0, 0, 0, 0)

        # Table selector
        tbl_row = QHBoxLayout()
        tbl_row.setSpacing(4)
        lbl_tbl = QLabel("Select table:")
        lbl_tbl.setFont(_FONT)
        tbl_row.addWidget(lbl_tbl)
        self.cmb_table = QComboBox()
        self.cmb_table.setFont(_FONT)
        self.cmb_table.addItems(TABLE_ITEMS)
        self.cmb_table.setCurrentIndex(1)  # default to TAICyberTAIFd
        self.cmb_table.setFixedHeight(_CTRL_H)
        style_combo(self.cmb_table)
        tbl_row.addWidget(self.cmb_table)
        tbl_row.addStretch()
        left_col.addLayout(tbl_row)
        left_col.addSpacing(4)

        # Date Range group
        date_grp = QGroupBox("Date Range")
        date_grp.setFont(_FONT_BOLD)
        date_lay = QVBoxLayout(date_grp)
        date_lay.setContentsMargins(6, 14, 6, 6)
        date_lay.setSpacing(4)

        self.txt_date_from = QLineEdit()
        self.txt_date_from.setFont(_FONT)
        self.txt_date_from.setFixedHeight(_CTRL_H)
        self.txt_date_from.setFixedWidth(80)
        self.txt_date_from.setPlaceholderText("YYYYMM")
        date_lay.addWidget(self.txt_date_from)

        lbl_to = QLabel("to")
        lbl_to.setFont(_FONT)
        date_lay.addWidget(lbl_to)

        self.txt_date_to = QLineEdit()
        self.txt_date_to.setFont(_FONT)
        self.txt_date_to.setFixedHeight(_CTRL_H)
        self.txt_date_to.setFixedWidth(80)
        self.txt_date_to.setPlaceholderText("YYYYMM")
        date_lay.addWidget(self.txt_date_to)

        self.btn_last_update = QPushButton("Last Update")
        self.btn_last_update.setFont(_FONT)
        self.btn_last_update.setFixedHeight(_CTRL_H)
        self.btn_last_update.clicked.connect(self._last_update_clicked)
        date_lay.addWidget(self.btn_last_update)

        self.list_dates = QListWidget()
        self.list_dates.setFont(_FONT)
        self.list_dates.setFixedWidth(80)
        self.list_dates.setItemDelegate(TightItemDelegate(self.list_dates))
        self.list_dates.setUniformItemSizes(True)
        self.list_dates.setSelectionMode(
            QAbstractItemView.SelectionMode.SingleSelection)
        self.list_dates.setStyleSheet(
            "QListWidget { border: 1px solid #1E5BA8; background-color: white; }"
            "QListWidget::item { padding: 0px 2px; border: none; }"
            "QListWidget::item:selected { background-color: #A0C4E8;"
            " color: black; border: none; }"
        )
        self.list_dates.itemDoubleClicked.connect(
            self._on_date_double_clicked)
        date_lay.addWidget(self.list_dates, 1)

        left_col.addWidget(date_grp, 1)

        # Get Dates button
        self.btn_get_dates = QPushButton("Get Dates")
        self.btn_get_dates.setFont(_FONT_BOLD)
        self.btn_get_dates.setFixedHeight(28)
        self.btn_get_dates.setFixedWidth(100)
        self.btn_get_dates.setStyleSheet(
            "QPushButton { border: 2px solid #1E5BA8; border-radius: 3px;"
            "  background-color: #E8F0FB; color: #1E5BA8; padding: 2px 6px; }"
            "QPushButton:hover { background-color: #C5D8F5; }"
            "QPushButton:pressed { background-color: #A0C4E8; }"
        )
        self.btn_get_dates.clicked.connect(self._on_get_dates)
        left_col.addWidget(self.btn_get_dates)

        root.addWidget(left_widget)

        # ── CENTER column: Status Code (top), ProdCD + Company (bottom) ──
        center_col = QVBoxLayout()
        center_col.setSpacing(2)

        self.chk_status_code = make_checkbox("Status Code")
        center_col.addWidget(self.chk_status_code)

        self.list_status_code = make_listbox(
            STATUS_CODE_ITEMS, height_rows=13, enabled=False)
        self.list_status_code.setFixedWidth(170)
        connect_checkbox_listbox(self.chk_status_code, self.list_status_code)
        center_col.addWidget(self.list_status_code)

        # ProdCD + Company side by side below Status Code
        center_col.addSpacing(4)
        prodco_row = QHBoxLayout()
        prodco_row.setSpacing(8)

        # ProdCD
        pd_col = QVBoxLayout()
        pd_col.setSpacing(2)
        self.chk_prodcd = make_checkbox("ProdCD")
        pd_col.addWidget(self.chk_prodcd)
        self.list_prodcd = make_listbox(
            PRODCD_ITEMS, height_rows=4, enabled=False)
        self.list_prodcd.setFixedWidth(55)
        connect_checkbox_listbox(self.chk_prodcd, self.list_prodcd)
        pd_col.addWidget(self.list_prodcd)
        prodco_row.addLayout(pd_col)

        # Company
        co_col = QVBoxLayout()
        co_col.setSpacing(2)
        self.chk_company = make_checkbox("Company")
        co_col.addWidget(self.chk_company)
        self.list_company = make_listbox(
            COMPANY_ITEMS, height_rows=6, enabled=False)
        self.list_company.setFixedWidth(55)
        connect_checkbox_listbox(self.chk_company, self.list_company)
        co_col.addWidget(self.list_company)
        prodco_row.addLayout(co_col)

        prodco_row.addStretch()
        center_col.addLayout(prodco_row)

        center_col.addStretch()
        root.addLayout(center_col)

        # ── RIGHT column: Policy/Plancode criteria (top), date ranges (bottom) ──
        right_col = QVBoxLayout()
        right_col.setSpacing(2)

        # Policynumber criteria
        btn_pn = QPushButton("Policynumber criteria")
        btn_pn.setFont(_FONT_BOLD)
        btn_pn.setFlat(True)
        btn_pn.setEnabled(False)
        btn_pn.setStyleSheet(
            "QPushButton { color: black; text-align: center; border: none; }")
        right_col.addWidget(btn_pn)

        self.cmb_polnum_criteria = QComboBox()
        self.cmb_polnum_criteria.setFont(_FONT)
        self.cmb_polnum_criteria.addItems(POLICYNUMBER_CRITERIA)
        self.cmb_polnum_criteria.setFixedHeight(_CTRL_H)
        self.cmb_polnum_criteria.setFixedWidth(250)
        style_combo(self.cmb_polnum_criteria)
        right_col.addWidget(self.cmb_polnum_criteria)

        self.txt_polnum = QLineEdit()
        self.txt_polnum.setFont(_FONT)
        self.txt_polnum.setFixedHeight(_CTRL_H)
        self.txt_polnum.setFixedWidth(250)
        self.txt_polnum.setPlaceholderText("Policy number")
        right_col.addWidget(self.txt_polnum)

        # Plancode criteria
        right_col.addSpacing(4)
        btn_pc = QPushButton("Plancode criteria")
        btn_pc.setFont(_FONT_BOLD)
        btn_pc.setFlat(True)
        btn_pc.setEnabled(False)
        btn_pc.setStyleSheet(
            "QPushButton { color: black; text-align: center; border: none; }")
        right_col.addWidget(btn_pc)

        self.cmb_plancode_criteria = QComboBox()
        self.cmb_plancode_criteria.setFont(_FONT)
        self.cmb_plancode_criteria.addItems(PLANCODE_CRITERIA)
        self.cmb_plancode_criteria.setFixedHeight(_CTRL_H)
        self.cmb_plancode_criteria.setFixedWidth(250)
        style_combo(self.cmb_plancode_criteria)
        right_col.addWidget(self.cmb_plancode_criteria)

        self.txt_plancode = QLineEdit()
        self.txt_plancode.setFont(_FONT)
        self.txt_plancode.setFixedHeight(_CTRL_H)
        self.txt_plancode.setFixedWidth(250)
        self.txt_plancode.setPlaceholderText("Plan code")
        right_col.addWidget(self.txt_plancode)

        # ── Date range filters ───────────────────────────────────
        right_col.addSpacing(8)
        range_grid = QGridLayout()
        range_grid.setContentsMargins(0, 0, 0, 0)
        range_grid.setHorizontalSpacing(4)
        range_grid.setVerticalSpacing(4)

        r = 0
        self.txt_issue_date_lo, self.txt_issue_date_hi = \
            _add_date_range_row(range_grid, r, "Issue Date Range"); r += 1
        self.txt_paid_to_date_lo, self.txt_paid_to_date_hi = \
            _add_date_range_row(range_grid, r, "Paid To Date Range"); r += 1
        self.txt_last_trans_date_lo, self.txt_last_trans_date_hi = \
            _add_date_range_row(range_grid, r, "Last Trans Date Range"); r += 1
        self.txt_values_date_lo, self.txt_values_date_hi = \
            _add_date_range_row(range_grid, r, "Values Date Range"); r += 1

        right_col.addLayout(range_grid)

        # All columns checkbox at bottom-right
        right_col.addStretch()
        self.chk_all_columns = make_checkbox("All columns")
        right_col.addWidget(self.chk_all_columns,
                            alignment=Qt.AlignmentFlag.AlignRight)
        root.addLayout(right_col)

        root.addStretch()

    # ── Get Dates ────────────────────────────────────────────────────

    def _on_get_dates(self):
        table = self.cmb_table.currentText()
        if table == "(none)":
            QMessageBox.information(
                self, "Get Dates", "Please select a table first.")
            return
        try:
            conn = pyodbc.connect(f"DSN={_DSN}")
            cursor = conn.cursor()
            cursor.execute(
                f"SELECT DISTINCT CAST(LastUpdate AS DATE) AS dt"
                f" FROM {table} ORDER BY dt DESC")
            dates = []
            for row in cursor.fetchall():
                if row[0] is None:
                    continue
                val = row[0]
                if hasattr(val, 'strftime'):
                    dates.append(val.strftime('%Y-%m-%d'))
                else:
                    dates.append(str(val).strip()[:10])
            conn.close()

            if not dates:
                QMessageBox.information(
                    self, "Get Dates", f"No dates found in {table}.")
                return

            self.list_dates.clear()
            for d in dates:
                self.list_dates.addItem(d)

        except Exception as exc:
            logger.exception("Failed to query dates")
            QMessageBox.warning(
                self, "Error", f"Failed to get dates:\n{exc}")

    def _on_date_double_clicked(self, item):
        d = item.text().strip()
        self.txt_date_from.setText(d)
        self.txt_date_to.setText(d)

    def _last_update_clicked(self):
        val = self.txt_date_from.text().strip()
        if val:
            self.txt_date_to.setText(val)

    # ── State management (for profiles) ──────────────────────────────

    def get_state(self) -> dict:
        state = {
            "table": self.cmb_table.currentText(),
            "date_from": self.txt_date_from.text(),
            "date_to": self.txt_date_to.text(),
            "polnum_criteria": self.cmb_polnum_criteria.currentIndex(),
            "polnum": self.txt_polnum.text(),
            "plancode_criteria": self.cmb_plancode_criteria.currentIndex(),
            "plancode": self.txt_plancode.text(),
        }
        for name in ("status_code", "prodcd", "company"):
            chk = getattr(self, f"chk_{name}")
            lb = getattr(self, f"list_{name}")
            state[f"{name}_checked"] = chk.isChecked()
            state[f"{name}_selected"] = [
                lb.item(i).text() for i in range(lb.count())
                if lb.item(i).isSelected()
            ]
        state["all_columns"] = self.chk_all_columns.isChecked()
        # Date range fields
        for rng in ("issue_date", "paid_to_date", "last_trans_date", "values_date"):
            state[f"{rng}_lo"] = getattr(self, f"txt_{rng}_lo").text()
            state[f"{rng}_hi"] = getattr(self, f"txt_{rng}_hi").text()
        return state

    def set_state(self, state: dict):
        if not state:
            return
        # Table
        idx = self.cmb_table.findText(state.get("table", ""))
        if idx >= 0:
            self.cmb_table.setCurrentIndex(idx)
        self.txt_date_from.setText(state.get("date_from", ""))
        self.txt_date_to.setText(state.get("date_to", ""))
        self.cmb_polnum_criteria.setCurrentIndex(
            state.get("polnum_criteria", 0))
        self.txt_polnum.setText(state.get("polnum", ""))
        self.cmb_plancode_criteria.setCurrentIndex(
            state.get("plancode_criteria", 0))
        self.txt_plancode.setText(state.get("plancode", ""))
        # Date range fields
        for rng in ("issue_date", "paid_to_date", "last_trans_date", "values_date"):
            getattr(self, f"txt_{rng}_lo").setText(state.get(f"{rng}_lo", ""))
            getattr(self, f"txt_{rng}_hi").setText(state.get(f"{rng}_hi", ""))

        for name in ("status_code", "prodcd", "company"):
            chk = getattr(self, f"chk_{name}")
            lb = getattr(self, f"list_{name}")
            chk.setChecked(state.get(f"{name}_checked", False))
            selected = state.get(f"{name}_selected", [])
            for i in range(lb.count()):
                lb.item(i).setSelected(lb.item(i).text() in selected)
        self.chk_all_columns.setChecked(state.get("all_columns", False))
