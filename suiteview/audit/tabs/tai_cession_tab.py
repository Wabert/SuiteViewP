"""
TAI Cession tab — filter criteria for TAICession table queries.

Layout mirrors the VBA-style filter form with:
  Date Range, Status Code, ReinsCo, RepCo, ReinsType, Mode,
  ProdCD, Company, Policynumber criteria, Plancode criteria, RGA checkbox.
"""
from __future__ import annotations

import logging
import pyodbc

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGridLayout,
    QLabel, QLineEdit, QComboBox, QCheckBox, QPushButton,
    QListWidget, QAbstractItemView, QFrame, QGroupBox,
    QMessageBox,
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

# ── Hard-coded filter values (matching VBA form) ─────────────────────

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

REINSCO_ITEMS = [
    "RGAO", "GB", "AC", "AL", "AN", "AU", "CG", "CL", "CN", "ER",
    "FF", "GC", "GG", "GL", "GN", "HA", "IN", "LN", "LR", "MG",
    "MU", "NA", "OP", "RG", "SW",
]

REPCO_ITEMS = [
    "RGAO", "GB", "RG", "AC", "AN", "AU", "SW", "CL", "MU", "ER",
    "FF", "GC", "GG", "GL", "GN", "HA", "IN", "LN", "OP", "TR",
    "TT", "WI",
]

REINS_TYPE_ITEMS = ["Y", "C"]
MODE_ITEMS = ["AN", "MN", "MF"]
PRODCD_ITEMS = ["T", "U", "V", "W"]
COMPANY_ITEMS = ["101", "104", "106", "108", "130", "FFL"]

POLICYNUMBER_CRITERIA = ["0 - Match", "1 - Starts with", "2 - Contains"]
PLANCODE_CRITERIA = ["0 - Match", "1 - Starts with", "2 - Contains"]

_DSN = "UL_Rates"

TABLE_ITEMS = ["(none)", "TAICession", "orion_pcr3_r", "orion_pcr3_r_old"]


class TaiCessionTab(QWidget):
    """TAI Cession tab — filter criteria for TAICession queries."""

    # Emitted when compare mode or field population changes.
    # True = compare ON and both fields populated; False otherwise.
    compare_ready_changed = pyqtSignal(bool)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._build_ui()

    # ── UI construction ──────────────────────────────────────────────

    def _build_ui(self):
        root = QHBoxLayout(self)
        root.setContentsMargins(6, 6, 6, 4)
        root.setSpacing(8)

        # ── LEFT column: Date Range + Get Dates button only ──────
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

        self.btn_month_end = QPushButton("Month End")
        self.btn_month_end.setFont(_FONT)
        self.btn_month_end.setFixedHeight(_CTRL_H)
        self.btn_month_end.clicked.connect(self._month_end_clicked)
        date_lay.addWidget(self.btn_month_end)

        self.list_dates = QListWidget()
        self.list_dates.setFont(_FONT)
        self.list_dates.setFixedWidth(80)
        self.list_dates.setItemDelegate(TightItemDelegate(self.list_dates))
        self.list_dates.setUniformItemSizes(True)
        self.list_dates.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.list_dates.setStyleSheet(
            "QListWidget { border: 1px solid #1E5BA8; background-color: white; }"
            "QListWidget::item { padding: 0px 2px; border: none; }"
            "QListWidget::item:selected { background-color: #A0C4E8; color: black; border: none; }"
        )
        self.list_dates.itemDoubleClicked.connect(self._on_date_double_clicked)
        date_lay.addWidget(self.list_dates, 1)  # stretch=1 fills remaining space

        left_col.addWidget(date_grp, 1)  # date group expands

        # ── Compare section ──────────────────────────────────────
        self.btn_compare = QPushButton("Compare – off")
        self.btn_compare.setFont(_FONT_BOLD)
        self.btn_compare.setFixedHeight(24)
        self._set_compare_style(False)
        self.btn_compare.clicked.connect(self._toggle_compare)
        left_col.addWidget(self.btn_compare)

        cmp_grid = QGridLayout()
        cmp_grid.setContentsMargins(0, 2, 0, 2)
        cmp_grid.setSpacing(3)

        lbl_eom1 = QLabel("MonthEnd1:")
        lbl_eom1.setFont(_FONT)
        cmp_grid.addWidget(lbl_eom1, 0, 0)
        self.txt_eom1 = QLineEdit()
        self.txt_eom1.setFont(_FONT)
        self.txt_eom1.setFixedHeight(_CTRL_H)
        self.txt_eom1.setPlaceholderText("YYYYMM")
        self.txt_eom1.setEnabled(False)
        self.txt_eom1.textChanged.connect(self._on_compare_fields_changed)
        cmp_grid.addWidget(self.txt_eom1, 0, 1)

        lbl_eom2 = QLabel("MonthEnd2:")
        lbl_eom2.setFont(_FONT)
        cmp_grid.addWidget(lbl_eom2, 1, 0)
        self.txt_eom2 = QLineEdit()
        self.txt_eom2.setFont(_FONT)
        self.txt_eom2.setFixedHeight(_CTRL_H)
        self.txt_eom2.setPlaceholderText("YYYYMM")
        self.txt_eom2.setEnabled(False)
        self.txt_eom2.textChanged.connect(self._on_compare_fields_changed)
        cmp_grid.addWidget(self.txt_eom2, 1, 1)

        left_col.addLayout(cmp_grid)

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

        # ── Status Code column ───────────────────────────────────
        status_col = QVBoxLayout()
        status_col.setSpacing(2)

        status_header = QHBoxLayout()
        self.chk_status_code = make_checkbox("Status Code")
        status_header.addWidget(self.chk_status_code)
        status_header.addSpacing(8)
        self.chk_inforce = make_checkbox("Inforce")
        status_header.addWidget(self.chk_inforce)
        status_header.addStretch()
        status_col.addLayout(status_header)

        self.list_status_code = make_listbox(STATUS_CODE_ITEMS, height_rows=13, enabled=False)
        self.list_status_code.setFixedWidth(170)
        connect_checkbox_listbox(self.chk_status_code, self.list_status_code)
        status_col.addWidget(self.list_status_code)

        # Policynumber criteria
        status_col.addSpacing(6)
        btn_pn = QPushButton("Policynumber criteria")
        btn_pn.setFont(_FONT_BOLD)
        btn_pn.setFlat(True)
        btn_pn.setEnabled(False)
        btn_pn.setStyleSheet("QPushButton { color: black; text-align: center; border: none; }")
        status_col.addWidget(btn_pn)

        self.cmb_polnum_criteria = QComboBox()
        self.cmb_polnum_criteria.setFont(_FONT)
        self.cmb_polnum_criteria.addItems(POLICYNUMBER_CRITERIA)
        self.cmb_polnum_criteria.setFixedHeight(_CTRL_H)
        style_combo(self.cmb_polnum_criteria)
        status_col.addWidget(self.cmb_polnum_criteria)

        self.txt_polnum = QLineEdit()
        self.txt_polnum.setFont(_FONT)
        self.txt_polnum.setFixedHeight(_CTRL_H)
        self.txt_polnum.setPlaceholderText("Policy number")
        status_col.addWidget(self.txt_polnum)

        # Plancode criteria
        status_col.addSpacing(4)
        btn_pc = QPushButton("Plancode criteria")
        btn_pc.setFont(_FONT_BOLD)
        btn_pc.setFlat(True)
        btn_pc.setEnabled(False)
        btn_pc.setStyleSheet("QPushButton { color: black; text-align: center; border: none; }")
        status_col.addWidget(btn_pc)

        self.cmb_plancode_criteria = QComboBox()
        self.cmb_plancode_criteria.setFont(_FONT)
        self.cmb_plancode_criteria.addItems(PLANCODE_CRITERIA)
        self.cmb_plancode_criteria.setFixedHeight(_CTRL_H)
        style_combo(self.cmb_plancode_criteria)
        status_col.addWidget(self.cmb_plancode_criteria)

        self.txt_plancode = QLineEdit()
        self.txt_plancode.setFont(_FONT)
        self.txt_plancode.setFixedHeight(_CTRL_H)
        self.txt_plancode.setPlaceholderText("Plan code")
        status_col.addWidget(self.txt_plancode)

        # RGA checkbox
        status_col.addSpacing(4)
        self.chk_rga = make_checkbox("RGA")
        status_col.addWidget(self.chk_rga)

        status_col.addStretch()
        root.addLayout(status_col)

        # ── ReinsCo column ───────────────────────────────────────
        reinsco_col = QVBoxLayout()
        reinsco_col.setSpacing(2)
        self.chk_reinsco = make_checkbox("ReinsCo")
        reinsco_col.addWidget(self.chk_reinsco)
        self.list_reinsco = make_listbox(REINSCO_ITEMS, height_rows=25, enabled=False)
        self.list_reinsco.setFixedWidth(65)
        connect_checkbox_listbox(self.chk_reinsco, self.list_reinsco)
        reinsco_col.addWidget(self.list_reinsco)
        reinsco_col.addStretch()
        root.addLayout(reinsco_col)

        # ── RepCo column ─────────────────────────────────────────
        repco_col = QVBoxLayout()
        repco_col.setSpacing(2)
        self.chk_repco = make_checkbox("RepCo")
        repco_col.addWidget(self.chk_repco)
        self.list_repco = make_listbox(REPCO_ITEMS, height_rows=25, enabled=False)
        self.list_repco.setFixedWidth(65)
        connect_checkbox_listbox(self.chk_repco, self.list_repco)
        repco_col.addWidget(self.list_repco)
        repco_col.addStretch()
        root.addLayout(repco_col)

        # ── Right side: ReinsType, Mode, ProdCD, Company ────────
        right_col = QVBoxLayout()
        right_col.setSpacing(8)

        # ReinsType
        rt_col = QVBoxLayout()
        rt_col.setSpacing(2)
        self.chk_reinstype = make_checkbox("ReinsType")
        rt_col.addWidget(self.chk_reinstype)
        self.list_reinstype = make_listbox(REINS_TYPE_ITEMS, height_rows=2, enabled=False)
        self.list_reinstype.setFixedWidth(55)
        connect_checkbox_listbox(self.chk_reinstype, self.list_reinstype)
        rt_col.addWidget(self.list_reinstype)
        right_col.addLayout(rt_col)

        # ProdCD
        pd_col = QVBoxLayout()
        pd_col.setSpacing(2)
        self.chk_prodcd = make_checkbox("ProdCD")
        pd_col.addWidget(self.chk_prodcd)
        self.list_prodcd = make_listbox(PRODCD_ITEMS, height_rows=4, enabled=False)
        self.list_prodcd.setFixedWidth(55)
        connect_checkbox_listbox(self.chk_prodcd, self.list_prodcd)
        pd_col.addWidget(self.list_prodcd)
        right_col.addLayout(pd_col)

        right_col.addStretch()
        root.addLayout(right_col)

        # ── Far right: Mode, Company ─────────────────────────────
        far_right = QVBoxLayout()
        far_right.setSpacing(8)

        # Mode
        mode_col = QVBoxLayout()
        mode_col.setSpacing(2)
        self.chk_mode = make_checkbox("Mode")
        mode_col.addWidget(self.chk_mode)
        self.list_mode = make_listbox(MODE_ITEMS, height_rows=3, enabled=False)
        self.list_mode.setFixedWidth(55)
        connect_checkbox_listbox(self.chk_mode, self.list_mode)
        mode_col.addWidget(self.list_mode)
        far_right.addLayout(mode_col)

        # Company
        co_col = QVBoxLayout()
        co_col.setSpacing(2)
        self.chk_company = make_checkbox("Company")
        co_col.addWidget(self.chk_company)
        self.list_company = make_listbox(COMPANY_ITEMS, height_rows=6, enabled=False)
        self.list_company.setFixedWidth(55)
        connect_checkbox_listbox(self.chk_company, self.list_company)
        co_col.addWidget(self.list_company)
        far_right.addLayout(co_col)

        far_right.addStretch()
        root.addLayout(far_right)

        root.addStretch()

    # ── Compare helpers ──────────────────────────────────────────────

    def _set_compare_style(self, on: bool):
        """Apply visual style to the Compare button."""
        if on:
            self.btn_compare.setStyleSheet(
                "QPushButton { background-color: #1565C0; color: white;"
                " border: 2px solid #0D47A1; border-radius: 3px; }"
                "QPushButton:hover { background-color: #1976D2; }"
            )
        else:
            self.btn_compare.setStyleSheet(
                "QPushButton { background-color: #E0E0E0; color: #555;"
                " border: 1px solid #BDBDBD; border-radius: 3px; }"
                "QPushButton:hover { background-color: #D0D0D0; }"
            )

    def _toggle_compare(self):
        """Toggle compare mode on/off."""
        on = not self.is_compare_on()
        self.btn_compare.setText("Compare \u2013 on" if on else "Compare \u2013 off")
        self._set_compare_style(on)
        self.txt_eom1.setEnabled(on)
        self.txt_eom2.setEnabled(on)
        # Disable / re-enable the date range fields
        self.txt_date_from.setEnabled(not on)
        self.txt_date_to.setEnabled(not on)
        self._on_compare_fields_changed()

    def is_compare_on(self) -> bool:
        """Return True when compare mode is active."""
        return "on" in self.btn_compare.text()

    def is_compare_ready(self) -> bool:
        """True when compare is on AND both month-end fields are populated."""
        return (self.is_compare_on()
                and bool(self.txt_eom1.text().strip())
                and bool(self.txt_eom2.text().strip()))

    def _on_compare_fields_changed(self, _text=None):
        """Re-emit the compare_ready_changed signal."""
        self.compare_ready_changed.emit(self.is_compare_ready())

    # ── Get Dates — query distinct monthEnd values ───────────────────

    def _on_get_dates(self):
        """Query distinct monthEnd values from the selected table and populate the dates listbox."""
        table = self.cmb_table.currentText()
        if table == "(none)":
            QMessageBox.information(self, "Get Dates", "Please select a table first.")
            return
        try:
            conn = pyodbc.connect(f"DSN={_DSN}")
            cursor = conn.cursor()
            cursor.execute(f"SELECT DISTINCT monthEnd FROM {table} ORDER BY monthEnd DESC")
            dates = [str(row[0]).strip() for row in cursor.fetchall() if row[0]]
            conn.close()

            if not dates:
                QMessageBox.information(self, "Get Dates", f"No dates found in {table}.")
                return

            self.list_dates.clear()
            for d in dates:
                self.list_dates.addItem(d)

        except Exception as exc:
            logger.exception("Failed to query dates")
            QMessageBox.warning(self, "Error", f"Failed to get dates:\n{exc}")

    # ── Date listbox double-click — set from/to to selected date ────────

    def _on_date_double_clicked(self, item):
        """Double-clicking a date sets both from and to fields to that date."""
        d = item.text().strip()
        self.txt_date_from.setText(d)
        self.txt_date_to.setText(d)

    # ── Month End — set both date fields to same value ───────────────

    def _month_end_clicked(self):
        """Set to/from to the same value (latest month end)."""
        val = self.txt_date_from.text().strip()
        if val:
            self.txt_date_to.setText(val)

    # ── State management (for profiles) ──────────────────────────────

    def get_state(self) -> dict:
        """Return the current filter state as a serialisable dict."""
        state = {
            "date_from": self.txt_date_from.text(),
            "date_to": self.txt_date_to.text(),
            "polnum_criteria": self.cmb_polnum_criteria.currentIndex(),
            "polnum": self.txt_polnum.text(),
            "plancode_criteria": self.cmb_plancode_criteria.currentIndex(),
            "plancode": self.txt_plancode.text(),
            "rga": self.chk_rga.isChecked(),
            "inforce": self.chk_inforce.isChecked(),
            "compare_on": self.is_compare_on(),
            "eom1": self.txt_eom1.text(),
            "eom2": self.txt_eom2.text(),
        }
        # Checkbox + listbox pairs
        for name in ("status_code", "reinsco", "repco", "reinstype",
                      "mode", "prodcd", "company"):
            chk = getattr(self, f"chk_{name}")
            lb = getattr(self, f"list_{name}")
            state[f"{name}_checked"] = chk.isChecked()
            state[f"{name}_selected"] = [
                lb.item(i).text() for i in range(lb.count())
                if lb.item(i).isSelected()
            ]
        return state

    def set_state(self, state: dict):
        """Restore filter state from a dict."""
        self.txt_date_from.setText(state.get("date_from", ""))
        self.txt_date_to.setText(state.get("date_to", ""))
        self.cmb_polnum_criteria.setCurrentIndex(state.get("polnum_criteria", 0))
        self.txt_polnum.setText(state.get("polnum", ""))
        self.cmb_plancode_criteria.setCurrentIndex(state.get("plancode_criteria", 0))
        self.txt_plancode.setText(state.get("plancode", ""))
        self.chk_rga.setChecked(state.get("rga", False))
        self.chk_inforce.setChecked(state.get("inforce", False))
        # Restore compare state
        self.txt_eom1.setText(state.get("eom1", ""))
        self.txt_eom2.setText(state.get("eom2", ""))
        if state.get("compare_on", False) != self.is_compare_on():
            self._toggle_compare()

        for name in ("status_code", "reinsco", "repco", "reinstype",
                      "mode", "prodcd", "company"):
            chk = getattr(self, f"chk_{name}")
            lb = getattr(self, f"list_{name}")
            chk.setChecked(state.get(f"{name}_checked", False))
            selected = set(state.get(f"{name}_selected", []))
            for i in range(lb.count()):
                lb.item(i).setSelected(lb.item(i).text() in selected)
