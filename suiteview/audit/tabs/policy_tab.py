"""
Policy tab — faithful replica of VBA frmAudit Policy (tab 1).

Layout (from the screenshot):
  LEFT column:  Plancode/RGA, Company/Market, Form#/Branch, PolicyNum criteria,
                then stacked range rows (Issue Age .. Billing Prem)
  CENTER-LEFT:  Status Code, Product Line Code, Product Indicator, Grace Indicator
  CENTER-RIGHT: State, Bill Mode, Billing Form
  RIGHT:        Last Entry Code, checkboxes, Suspense Code
"""
from __future__ import annotations

from PyQt6.QtCore import Qt, QSize
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGridLayout,
    QLabel, QLineEdit, QComboBox, QCheckBox, QPushButton,
    QListWidget, QAbstractItemView, QFrame, QSizePolicy,
    QStyledItemDelegate,
)
from PyQt6.QtGui import QFont

from ..constants import (
    STATUS_CODE_ITEMS, PRODUCT_LINE_CODE_ITEMS, PRODUCT_INDICATOR_ITEMS,
    STATE_ITEMS, BILL_MODE_ITEMS, LAST_ENTRY_CODE_ITEMS,
    BILLING_FORM_ITEMS, GRACE_INDICATOR_ITEMS, SUSPENSE_CODE_ITEMS,
    COMPANY_ITEMS, MARKET_ORG_ITEMS, POLICYNUMBER_CRITERIA_ITEMS,
)

# ── Compact sizing helpers ──────────────────────────────────────────────
_FONT = QFont("Segoe UI", 9)
_ROW_H = 16          # pixel height per listbox row (matches PolView TightItemDelegate)
_CTRL_H = 22         # control height (line edits, combos, buttons)
_V_SPACING = 2       # vertical spacing between controls
_H_SPACING = 4       # horizontal spacing
_RANGE_W = 70        # width of range text inputs
_LABEL_W = 130       # width of range-row label buttons


class _TightItemDelegate(QStyledItemDelegate):
    """Forces a fixed compact row height on QListWidget items."""
    ROW_H = _ROW_H

    def sizeHint(self, option, index):
        sh = super().sizeHint(option, index)
        return QSize(sh.width(), self.ROW_H)


def _make_listbox(items: list[str], *, height_rows: int = 10,
                  multi: bool = True, enabled: bool = True) -> QListWidget:
    """Create a compact multi-select listbox with TightItemDelegate for VBA-level density."""
    lb = QListWidget()
    lb.setFont(_FONT)
    lb.setItemDelegate(_TightItemDelegate(lb))
    lb.setUniformItemSizes(True)
    lb.setStyleSheet(
        "QListWidget { border: 1px solid #999; }"
        "QListWidget::item { padding: 0px 2px; }"
    )
    if multi:
        lb.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
    else:
        lb.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
    lb.addItems(items)
    lb.setFixedHeight(height_rows * _ROW_H + 4)
    lb.setEnabled(enabled)
    return lb


def _make_checkbox(text: str, *, checked: bool = False) -> QCheckBox:
    cb = QCheckBox(text)
    cb.setFont(_FONT)
    cb.setChecked(checked)
    return cb


def _add_range_row(layout: QGridLayout, row: int, label_text: str) -> tuple[QLineEdit, QLineEdit]:
    """Add a label-button | lo | 'to' | hi range row and return (lo, hi)."""
    btn = QPushButton(label_text)
    btn.setFont(_FONT)
    btn.setFixedWidth(_LABEL_W)
    btn.setFixedHeight(_CTRL_H)
    btn.setStyleSheet("QPushButton { text-align: left; padding: 1px 4px; }")

    lo = QLineEdit()
    lo.setFont(_FONT)
    lo.setFixedWidth(_RANGE_W)
    lo.setFixedHeight(_CTRL_H)

    lbl_to = QLabel("to")
    lbl_to.setFont(_FONT)
    lbl_to.setFixedWidth(16)
    lbl_to.setAlignment(Qt.AlignmentFlag.AlignCenter)

    hi = QLineEdit()
    hi.setFont(_FONT)
    hi.setFixedWidth(_RANGE_W)
    hi.setFixedHeight(_CTRL_H)

    layout.addWidget(btn, row, 0)
    layout.addWidget(lo, row, 1)
    layout.addWidget(lbl_to, row, 2)
    layout.addWidget(hi, row, 3)
    return lo, hi


class PolicyTab(QWidget):
    """Policy criteria tab — mirrors VBA frmAudit Page1 exactly."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._build_ui()

    def _build_ui(self):
        root = QHBoxLayout(self)
        root.setContentsMargins(4, 4, 4, 4)
        root.setSpacing(8)

        # ────────────────────────────────────────────────────────────
        # COLUMN 1 — left controls + ranges
        # ────────────────────────────────────────────────────────────
        col1 = QVBoxLayout()
        col1.setSpacing(_V_SPACING)

        # Plancode + RGA
        row = QHBoxLayout(); row.setSpacing(_H_SPACING)
        btn_pc = QPushButton("Plancode")
        btn_pc.setFont(_FONT); btn_pc.setFixedSize(72, _CTRL_H)
        btn_pc.setStyleSheet("text-align:left; padding:1px 4px;")
        self.txt_plancode = QLineEdit()
        self.txt_plancode.setFont(_FONT); self.txt_plancode.setFixedSize(80, _CTRL_H)
        self.chk_rga = QCheckBox("RGA (52)")
        self.chk_rga.setFont(_FONT)
        row.addWidget(btn_pc); row.addWidget(self.txt_plancode)
        row.addSpacing(8); row.addWidget(self.chk_rga); row.addStretch()
        col1.addLayout(row)

        # Company / Market labels
        row = QHBoxLayout(); row.setSpacing(_H_SPACING)
        btn_co = QPushButton("Company"); btn_co.setFont(_FONT)
        btn_co.setFixedSize(66, _CTRL_H); btn_co.setStyleSheet("text-align:left; padding:1px 4px;")
        btn_mk = QPushButton("Market"); btn_mk.setFont(_FONT)
        btn_mk.setFixedSize(54, _CTRL_H); btn_mk.setStyleSheet("text-align:left; padding:1px 4px;")
        row.addWidget(btn_co); row.addWidget(btn_mk); row.addStretch()
        col1.addLayout(row)

        # Company / Market combos
        row = QHBoxLayout(); row.setSpacing(_H_SPACING)
        self.cmb_company = QComboBox(); self.cmb_company.setFont(_FONT)
        self.cmb_company.addItems(COMPANY_ITEMS); self.cmb_company.setFixedHeight(_CTRL_H)
        self.cmb_company.setMinimumWidth(100)
        self.cmb_market = QComboBox(); self.cmb_market.setFont(_FONT)
        self.cmb_market.addItems(MARKET_ORG_ITEMS); self.cmb_market.setFixedHeight(_CTRL_H)
        self.cmb_market.setMinimumWidth(90)
        row.addWidget(self.cmb_company); row.addWidget(self.cmb_market); row.addStretch()
        col1.addLayout(row)

        # Form number like
        row = QHBoxLayout(); row.setSpacing(_H_SPACING)
        lbl = QLabel("Form number like:"); lbl.setFont(_FONT)
        self.txt_form_number = QLineEdit(); self.txt_form_number.setFont(_FONT)
        self.txt_form_number.setFixedSize(90, _CTRL_H)
        row.addWidget(lbl); row.addWidget(self.txt_form_number); row.addStretch()
        col1.addLayout(row)

        # 3 digit Branch #
        row = QHBoxLayout(); row.setSpacing(_H_SPACING)
        lbl = QLabel("3 digit Branch #:"); lbl.setFont(_FONT)
        self.txt_branch = QLineEdit(); self.txt_branch.setFont(_FONT)
        self.txt_branch.setFixedSize(50, _CTRL_H); self.txt_branch.setMaxLength(3)
        row.addWidget(lbl); row.addWidget(self.txt_branch); row.addStretch()
        col1.addLayout(row)

        # Policynumber criteria
        row = QHBoxLayout(); row.setSpacing(_H_SPACING)
        lbl_pc = QPushButton("Policynumber criteria"); lbl_pc.setFont(_FONT)
        lbl_pc.setFixedHeight(_CTRL_H); lbl_pc.setStyleSheet("text-align:left; padding:1px 4px;")
        row.addWidget(lbl_pc); row.addStretch()
        col1.addLayout(row)

        row = QHBoxLayout(); row.setSpacing(_H_SPACING)
        self.cmb_polnum_criteria = QComboBox(); self.cmb_polnum_criteria.setFont(_FONT)
        self.cmb_polnum_criteria.addItems(POLICYNUMBER_CRITERIA_ITEMS)
        self.cmb_polnum_criteria.setFixedHeight(_CTRL_H)
        self.txt_polnum_value = QLineEdit(); self.txt_polnum_value.setFont(_FONT)
        self.txt_polnum_value.setFixedHeight(_CTRL_H); self.txt_polnum_value.setMinimumWidth(90)
        row.addWidget(self.cmb_polnum_criteria); row.addWidget(self.txt_polnum_value); row.addStretch()
        col1.addLayout(row)

        # Range fields
        grid = QGridLayout()
        grid.setSpacing(_V_SPACING)
        grid.setContentsMargins(0, 4, 0, 0)
        grid.setHorizontalSpacing(_H_SPACING)

        r = 0
        self.txt_issue_age_lo, self.txt_issue_age_hi = _add_range_row(grid, r, "Issue Age Range"); r += 1
        self.txt_current_age_lo, self.txt_current_age_hi = _add_range_row(grid, r, "Current Age Range"); r += 1
        self.txt_pol_year_lo, self.txt_pol_year_hi = _add_range_row(grid, r, "Current Policy Year"); r += 1
        self.txt_issue_month_lo, self.txt_issue_month_hi = _add_range_row(grid, r, "Issue Month Range"); r += 1
        self.txt_issue_day_lo, self.txt_issue_day_hi = _add_range_row(grid, r, "Issue Day Range"); r += 1
        grid.setRowMinimumHeight(r, 6); r += 1  # visual spacer
        self.txt_issued_date_lo, self.txt_issued_date_hi = _add_range_row(grid, r, "Issued date Range"); r += 1
        self.txt_paid_to_lo, self.txt_paid_to_hi = _add_range_row(grid, r, "Paid To Date Range"); r += 1
        self.txt_gpe_date_lo, self.txt_gpe_date_hi = _add_range_row(grid, r, "GPE Date Range (51 o.."); r += 1
        self.txt_app_date_lo, self.txt_app_date_hi = _add_range_row(grid, r, "Application Date (01)"); r += 1
        self.txt_billing_prem_lo, self.txt_billing_prem_hi = _add_range_row(grid, r, "Billing Prem Amt (01)"); r += 1

        col1.addLayout(grid)
        col1.addStretch()

        # ────────────────────────────────────────────────────────────
        # COLUMN 2 — Status Code, Prod Line, Prod Indicator, Grace
        # ────────────────────────────────────────────────────────────
        col2 = QVBoxLayout()
        col2.setSpacing(_V_SPACING)

        # Status Code header
        hdr = QHBoxLayout(); hdr.setSpacing(_H_SPACING)
        self.chk_status_code = _make_checkbox("Status Code (01)")
        btn_inforce = QPushButton("Inforce"); btn_inforce.setFont(_FONT)
        btn_inforce.setFixedSize(50, 20); btn_inforce.setStyleSheet("padding:0 2px;")
        btn_inforce.clicked.connect(self._select_inforce)
        hdr.addWidget(self.chk_status_code); hdr.addWidget(btn_inforce); hdr.addStretch()
        col2.addLayout(hdr)
        self.list_status = _make_listbox(STATUS_CODE_ITEMS, height_rows=14, enabled=False)
        self.chk_status_code.toggled.connect(self.list_status.setEnabled)
        col2.addWidget(self.list_status)

        # Product Line Code
        self.chk_product_line = _make_checkbox("Product Line Code (02)")
        col2.addWidget(self.chk_product_line)
        self.list_product_line = _make_listbox(PRODUCT_LINE_CODE_ITEMS, height_rows=8, enabled=False)
        self.chk_product_line.toggled.connect(self.list_product_line.setEnabled)
        col2.addWidget(self.list_product_line)

        # Product Indicator — All covs
        self.chk_product_indicator = _make_checkbox("Product Indicator (02) - All covs")
        col2.addWidget(self.chk_product_indicator)
        self.list_product_indicator = _make_listbox(PRODUCT_INDICATOR_ITEMS, height_rows=8, enabled=False)
        self.chk_product_indicator.toggled.connect(self.list_product_indicator.setEnabled)
        col2.addWidget(self.list_product_indicator)

        # Grace Indicator
        self.chk_grace_indicator = _make_checkbox("Grace Indicator (51 or 66)")
        col2.addWidget(self.chk_grace_indicator)
        self.list_grace_indicator = _make_listbox(GRACE_INDICATOR_ITEMS, height_rows=2, enabled=False)
        self.chk_grace_indicator.toggled.connect(self.list_grace_indicator.setEnabled)
        col2.addWidget(self.list_grace_indicator)
        col2.addStretch()

        # ────────────────────────────────────────────────────────────
        # COLUMN 3 — State, Bill Mode, Billing Form, checkboxes
        # ────────────────────────────────────────────────────────────
        col3 = QVBoxLayout()
        col3.setSpacing(_V_SPACING)

        self.chk_state = _make_checkbox("State")
        col3.addWidget(self.chk_state)
        self.list_state = _make_listbox(STATE_ITEMS, height_rows=20, enabled=False)
        self.list_state.setFixedWidth(55)
        self.chk_state.toggled.connect(self.list_state.setEnabled)
        col3.addWidget(self.list_state)

        self.chk_bill_mode = _make_checkbox("Bill Mode (01)")
        col3.addWidget(self.chk_bill_mode)
        self.list_bill_mode = _make_listbox(BILL_MODE_ITEMS, height_rows=8, enabled=False)
        self.list_bill_mode.setFixedWidth(110)
        self.chk_bill_mode.toggled.connect(self.list_bill_mode.setEnabled)
        col3.addWidget(self.list_bill_mode)

        self.chk_billing_form = _make_checkbox("Billing Form (01)")
        col3.addWidget(self.chk_billing_form)
        self.list_billing_form = _make_listbox(BILLING_FORM_ITEMS, height_rows=5, enabled=False)
        self.chk_billing_form.toggled.connect(self.list_billing_form.setEnabled)
        col3.addWidget(self.list_billing_form)

        self.chk_is_mdo = QCheckBox("Is MDO (59)"); self.chk_is_mdo.setFont(_FONT)
        col3.addWidget(self.chk_is_mdo)
        self.chk_multiple_base_covs = QCheckBox("Multiple Base Covs (02)"); self.chk_multiple_base_covs.setFont(_FONT)
        col3.addWidget(self.chk_multiple_base_covs)
        col3.addSpacing(4)
        self.chk_in_conversion = QCheckBox("In conversion period (Calc)"); self.chk_in_conversion.setFont(_FONT)
        col3.addWidget(self.chk_in_conversion)
        col3.addStretch()

        # ────────────────────────────────────────────────────────────
        # COLUMN 4 — Last Entry Code, Suspense Code
        # ────────────────────────────────────────────────────────────
        col4 = QVBoxLayout()
        col4.setSpacing(_V_SPACING)

        self.chk_last_entry = _make_checkbox("Last Entry Code (01)")
        col4.addWidget(self.chk_last_entry)
        self.list_last_entry = _make_listbox(LAST_ENTRY_CODE_ITEMS, height_rows=13, enabled=False)
        self.chk_last_entry.toggled.connect(self.list_last_entry.setEnabled)
        col4.addWidget(self.list_last_entry)

        note = QLabel('A code of "P" could mean either a full\nsurrender (SF) or internal surrender (SI)')
        note.setFont(QFont("Segoe UI", 7))
        note.setStyleSheet("color: #666;")
        note.setWordWrap(True)
        col4.addWidget(note)

        col4.addSpacing(8)
        self.chk_suspense = _make_checkbox("Suspense Code (01)")
        col4.addWidget(self.chk_suspense)
        self.list_suspense = _make_listbox(SUSPENSE_CODE_ITEMS, height_rows=4, enabled=False)
        self.chk_suspense.toggled.connect(self.list_suspense.setEnabled)
        col4.addWidget(self.list_suspense)
        col4.addStretch()

        # ── Assemble ────────────────────────────────────────────────
        root.addLayout(col1)
        root.addLayout(col2)
        root.addLayout(col3)
        root.addLayout(col4)

    # ── helpers ──────────────────────────────────────────────────────
    def _select_inforce(self):
        """Select all status codes < 97 (inforce) — mirrors VBA Inforce button."""
        self.chk_status_code.setChecked(True)
        for i in range(self.list_status.count()):
            text = self.list_status.item(i).text()
            try:
                code = int(text.split("-")[0].strip())
                self.list_status.item(i).setSelected(code < 97)
            except ValueError:
                self.list_status.item(i).setSelected(False)
