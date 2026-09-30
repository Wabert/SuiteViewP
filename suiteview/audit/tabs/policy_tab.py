"""
Policy tab — compact CyberLife policy criteria.

Layout (from the screenshot):
  LEFT column:  Aligned Plancode/RGA, Company/Market, Form#/Branch, Policy number,
                then stacked range rows (Issue Age .. Billing Prem)
  CENTER-LEFT:  Status Code
  CENTER:       Product Line Code, Product Indicator, Suspense Code, Grace Indicator
  CENTER-RIGHT: State
  RIGHT:        Last Entry Code, Bill Mode, Billing Form
"""
from __future__ import annotations

from PyQt6.QtCore import Qt, QSize
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGridLayout,
    QLabel, QLineEdit, QComboBox, QCheckBox, QPushButton,
    QListWidget, QAbstractItemView, QFrame, QStyledItemDelegate,
)
from PyQt6.QtGui import QFont

from ..constants import (
    STATUS_CODE_ITEMS, PRODUCT_LINE_CODE_ITEMS, PRODUCT_INDICATOR_ITEMS,
    STATE_ITEMS, BILL_MODE_ITEMS, LAST_ENTRY_CODE_ITEMS,
    BILLING_FORM_ITEMS, GRACE_INDICATOR_ITEMS, SUSPENSE_CODE_ITEMS,
    COMPANY_ITEMS, MARKET_ORG_ITEMS, POLICYNUMBER_CRITERIA_ITEMS,
    POLICYNUMBER_CRITERIA_DEFAULT,
)
from ._styles import style_combo as _style_combo, make_checkbox as _make_checkbox
from suiteview.audit.criteria_specs import (
    POLICY_TAB_STATE_SPEC,
    apply_tab_state,
    tab_state,
)
from suiteview.ui.widgets.uppercase_input import force_uppercase

# ── Compact sizing helpers ──────────────────────────────────────────────
_FONT = QFont("Segoe UI", 9)
_ROW_H = 16          # pixel height per listbox row (matches PolView TightItemDelegate)
_CTRL_H = 22         # control height (line edits, combos, buttons)
_V_SPACING = 2       # vertical spacing between controls
_H_SPACING = 4       # horizontal spacing
_RANGE_W = 70        # width of range text inputs
_LABEL_W = 165       # width of range-row label buttons


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
    bg_color = "white" if enabled else "#F0F0F0"
    lb.setStyleSheet(
        f"QListWidget {{ border: 1px solid #1E5BA8; background-color: {bg_color}; }}"
        "QListWidget::item { padding: 0px 2px; border: none; }"
        "QListWidget::item:selected { background-color: #A0C4E8; color: black; border: none; }"
    )
    if multi:
        lb.setSelectionMode(QAbstractItemView.SelectionMode.MultiSelection)
    else:
        lb.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
    lb.addItems(items)
    lb.setFixedHeight(height_rows * _ROW_H + 4)
    lb.setEnabled(enabled)
    return lb


def _connect_checkbox_listbox(chk: QCheckBox, lb: QListWidget):
    """Wire checkbox to enable/disable listbox and clear selections on uncheck."""
    def _on_toggle(checked: bool):
        lb.setEnabled(checked)
        bg_color = "white" if checked else "#F0F0F0"
        lb.setStyleSheet(
            f"QListWidget {{ border: 1px solid #1E5BA8; background-color: {bg_color}; }}"
            "QListWidget::item { padding: 0px 2px; border: none; }"
            "QListWidget::item:selected { background-color: #A0C4E8; color: black; border: none; }"
        )
        if not checked:
            lb.clearSelection()
    chk.toggled.connect(_on_toggle)


def _add_range_row(layout: QGridLayout, row: int, label_text: str) -> tuple[QLineEdit, QLineEdit]:
    """Add a label | lo | 'to' | hi range row and return (lo, hi)."""
    lbl = QLabel(label_text)
    lbl.setFont(_FONT)
    lbl.setFixedWidth(_LABEL_W)
    lbl.setFixedHeight(_CTRL_H)

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

    layout.addWidget(lbl, row, 0)
    layout.addWidget(lo, row, 1)
    layout.addWidget(lbl_to, row, 2)
    layout.addWidget(hi, row, 3)
    return lo, hi


class PolicyTab(QWidget):
    """Policy criteria with compact, aligned identifier and range inputs."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._build_ui()

    @staticmethod
    def _vsep() -> QFrame:
        """Create a thin vertical separator line."""
        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.VLine)
        sep.setStyleSheet("color: #bbb;")
        sep.setFixedWidth(2)
        return sep

    @staticmethod
    def _hsep() -> QFrame:
        """Create a thin horizontal separator line."""
        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setStyleSheet("color: #bbb;")
        sep.setFixedHeight(2)
        return sep

    def _build_ui(self):
        root = QHBoxLayout(self)
        root.setContentsMargins(4, 4, 4, 4)
        root.setSpacing(8)

        # ────────────────────────────────────────────────────────────
        # COLUMN 1 — left controls + ranges
        # ────────────────────────────────────────────────────────────
        col1 = QVBoxLayout()
        col1.setSpacing(_V_SPACING)

        identifiers = QGridLayout()
        identifiers.setContentsMargins(0, 0, 0, 0)
        identifiers.setVerticalSpacing(_V_SPACING)
        identifiers.setHorizontalSpacing(_H_SPACING)
        identifiers.setColumnStretch(2, 1)
        for index, text in enumerate((
            "Plancode", "Company", "Market", "Form number like",
            "3 digit Branch #", "Policy number",
        )):
            label = QLabel(text)
            label.setFont(_FONT)
            label.setFixedHeight(_CTRL_H)
            identifiers.addWidget(label, index, 0)

        self.txt_plancode = QLineEdit()
        self.txt_plancode.setFont(_FONT)
        self.txt_plancode.setFixedSize(92, _CTRL_H)
        force_uppercase(self.txt_plancode)
        self.txt_plancode.setToolTip(
            "Matches the complete plancode. Blank applies no plancode filter. "
            "Combined with the Plans and Policies plancodes as OR."
        )
        self.chk_rga = _make_checkbox("RGA (52)")
        identifiers.addWidget(self.txt_plancode, 0, 1)
        identifiers.addWidget(self.chk_rga, 0, 2, Qt.AlignmentFlag.AlignLeft)

        self.cmb_company = QComboBox(); self.cmb_company.setFont(_FONT)
        self.cmb_company.addItems(COMPANY_ITEMS); self.cmb_company.setFixedHeight(_CTRL_H)
        self.cmb_company.setMinimumWidth(130); _style_combo(self.cmb_company)
        self.cmb_market = QComboBox(); self.cmb_market.setFont(_FONT)
        self.cmb_market.addItems(MARKET_ORG_ITEMS); self.cmb_market.setFixedHeight(_CTRL_H)
        self.cmb_market.setMinimumWidth(110); _style_combo(self.cmb_market)
        identifiers.addWidget(self.cmb_company, 1, 1, 1, 2)
        identifiers.addWidget(self.cmb_market, 2, 1, 1, 2)

        self.txt_form_number = QLineEdit(); self.txt_form_number.setFont(_FONT)
        self.txt_form_number.setFixedHeight(_CTRL_H)
        identifiers.addWidget(self.txt_form_number, 3, 1, 1, 2)

        self.txt_branch = QLineEdit(); self.txt_branch.setFont(_FONT)
        self.txt_branch.setFixedSize(50, _CTRL_H); self.txt_branch.setMaxLength(3)
        identifiers.addWidget(self.txt_branch, 4, 1, Qt.AlignmentFlag.AlignLeft)

        self.cmb_polnum_criteria = QComboBox(); self.cmb_polnum_criteria.setFont(_FONT)
        self.cmb_polnum_criteria.addItems(POLICYNUMBER_CRITERIA_ITEMS)
        self.cmb_polnum_criteria.setCurrentText(POLICYNUMBER_CRITERIA_DEFAULT)
        self.cmb_polnum_criteria.setFixedSize(92, _CTRL_H); _style_combo(self.cmb_polnum_criteria)
        self.txt_polnum_value = QLineEdit(); self.txt_polnum_value.setFont(_FONT)
        self.txt_polnum_value.setFixedHeight(_CTRL_H); self.txt_polnum_value.setMinimumWidth(90)
        force_uppercase(self.txt_polnum_value)
        identifiers.addWidget(self.cmb_polnum_criteria, 5, 1)
        identifiers.addWidget(self.txt_polnum_value, 5, 2)
        col1.addLayout(identifiers)

        col1.addSpacing(2); col1.addWidget(self._hsep()); col1.addSpacing(2)

        # Range fields
        grid = QGridLayout()
        grid.setSpacing(_V_SPACING)
        grid.setContentsMargins(0, 4, 0, 0)
        grid.setHorizontalSpacing(_H_SPACING)

        r = 0
        self.txt_issue_age_lo, self.txt_issue_age_hi = _add_range_row(grid, r, "Issue Age Range"); r += 1
        self.txt_current_age_lo, self.txt_current_age_hi = _add_range_row(grid, r, "Current Age Range"); r += 1
        self.txt_val_age_lo, self.txt_val_age_hi = _add_range_row(grid, r, "Val Attained Age Range"); r += 1
        self.txt_pol_year_lo, self.txt_pol_year_hi = _add_range_row(grid, r, "Current Policy Year"); r += 1
        self.txt_issue_month_lo, self.txt_issue_month_hi = _add_range_row(grid, r, "Issue Month Range"); r += 1
        self.txt_issue_day_lo, self.txt_issue_day_hi = _add_range_row(grid, r, "Issue Day Range"); r += 1
        col1.addLayout(grid)

        col1.addSpacing(2); col1.addWidget(self._hsep()); col1.addSpacing(2)

        # Date / amount range fields (second group)
        grid = QGridLayout()
        grid.setSpacing(_V_SPACING)
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setHorizontalSpacing(_H_SPACING)
        r = 0
        self.txt_issued_date_lo, self.txt_issued_date_hi = _add_range_row(grid, r, "Issued date Range"); r += 1
        self.txt_paid_to_lo, self.txt_paid_to_hi = _add_range_row(grid, r, "Paid To Date Range"); r += 1
        self.txt_gpe_date_lo, self.txt_gpe_date_hi = _add_range_row(grid, r, "GPE Date Range (51 or 66)"); r += 1
        self.txt_app_date_lo, self.txt_app_date_hi = _add_range_row(grid, r, "Application Date (01)"); r += 1
        self.txt_billing_prem_lo, self.txt_billing_prem_hi = _add_range_row(grid, r, "Billing Prem Amt (01)"); r += 1

        col1.addLayout(grid)

        col1.addSpacing(2); col1.addWidget(self._hsep()); col1.addSpacing(2)

        # Checkboxes below the ranges
        self.chk_is_mdo = _make_checkbox("Is MDO (59)")
        col1.addWidget(self.chk_is_mdo)
        self.chk_multiple_base_covs = _make_checkbox("Multiple Base Covs (02)")
        col1.addWidget(self.chk_multiple_base_covs)
        self.chk_in_conversion = _make_checkbox("In conversion period (Calc)")
        col1.addWidget(self.chk_in_conversion)
        col1.addStretch()

        # ────────────────────────────────────────────────────────────
        # COLUMN 2 — Status Code only
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
        self.list_status = _make_listbox(STATUS_CODE_ITEMS, height_rows=20, enabled=False)
        _connect_checkbox_listbox(self.chk_status_code, self.list_status)
        col2.addWidget(self.list_status)
        col2.addStretch()

        # ────────────────────────────────────────────────────────────
        # COLUMN 2b — Product Line Code, Product Indicator
        # ────────────────────────────────────────────────────────────
        col2b = QVBoxLayout()
        col2b.setSpacing(_V_SPACING)

        # Product Line Code — show all 8 items
        self.chk_product_line = _make_checkbox("Product Line Code (02) - All Covs")
        col2b.addWidget(self.chk_product_line)
        self.list_product_line = _make_listbox(PRODUCT_LINE_CODE_ITEMS, height_rows=9, enabled=False)
        self.list_product_line.setMinimumWidth(280)
        _connect_checkbox_listbox(self.chk_product_line, self.list_product_line)
        col2b.addWidget(self.list_product_line)

        # Product Indicator — show all 11 items
        self.chk_product_indicator = _make_checkbox("Product Indicator (02) - All covs")
        col2b.addWidget(self.chk_product_indicator)
        self.list_product_indicator = _make_listbox(PRODUCT_INDICATOR_ITEMS, height_rows=11, enabled=False)
        self.list_product_indicator.setMinimumWidth(280)
        _connect_checkbox_listbox(self.chk_product_indicator, self.list_product_indicator)
        col2b.addWidget(self.list_product_indicator)

        # Suspense Code
        col2b.addSpacing(4)
        self.chk_suspense = _make_checkbox("Suspense Code (01)")
        col2b.addWidget(self.chk_suspense)
        self.list_suspense = _make_listbox(SUSPENSE_CODE_ITEMS, height_rows=4, enabled=False)
        _connect_checkbox_listbox(self.chk_suspense, self.list_suspense)
        col2b.addWidget(self.list_suspense)

        # Grace Indicator
        col2b.addSpacing(4)
        self.chk_grace_indicator = _make_checkbox("Grace Indicator (51 or 66)")
        col2b.addWidget(self.chk_grace_indicator)
        self.list_grace_indicator = _make_listbox(GRACE_INDICATOR_ITEMS, height_rows=2, enabled=False)
        _connect_checkbox_listbox(self.chk_grace_indicator, self.list_grace_indicator)
        col2b.addWidget(self.list_grace_indicator)
        col2b.addStretch()

        # ────────────────────────────────────────────────────────────
        # COLUMN 3 — State
        # ────────────────────────────────────────────────────────────
        col3 = QVBoxLayout()
        col3.setSpacing(_V_SPACING)

        self.chk_state = _make_checkbox("State")
        col3.addWidget(self.chk_state)
        self.list_state = _make_listbox(STATE_ITEMS, height_rows=35, enabled=False)
        self.list_state.setFixedWidth(55)
        _connect_checkbox_listbox(self.chk_state, self.list_state)
        col3.addWidget(self.list_state)
        col3.addStretch()

        # ────────────────────────────────────────────────────────────
        # COLUMN 4 — Last Entry Code, Suspense Code
        # ────────────────────────────────────────────────────────────
        col4 = QVBoxLayout()
        col4.setSpacing(_V_SPACING)
        _COL4_W = 215  # fits the longest code description without a wide empty right edge

        self.chk_last_entry = _make_checkbox("Last Entry Code (01)")
        col4.addWidget(self.chk_last_entry)
        self.list_last_entry = _make_listbox(
            LAST_ENTRY_CODE_ITEMS, height_rows=len(LAST_ENTRY_CODE_ITEMS), enabled=False)
        self.list_last_entry.setFixedWidth(_COL4_W)
        _connect_checkbox_listbox(self.chk_last_entry, self.list_last_entry)
        col4.addWidget(self.list_last_entry)

        note = QLabel('A code of "P" could mean either a full\nsurrender (SF) or internal surrender (SI)')
        note.setFont(QFont("Segoe UI", 7))
        note.setStyleSheet("color: #666;")
        note.setWordWrap(True)
        note.setFixedWidth(_COL4_W)
        col4.addWidget(note)

        # Bill Mode with Billing Form stacked underneath
        col4.addSpacing(4)
        self.chk_bill_mode = _make_checkbox("Bill Mode (01)")
        col4.addWidget(self.chk_bill_mode)
        self.list_bill_mode = _make_listbox(
            BILL_MODE_ITEMS, height_rows=len(BILL_MODE_ITEMS), enabled=False)
        self.list_bill_mode.setFixedWidth(_COL4_W)
        _connect_checkbox_listbox(self.chk_bill_mode, self.list_bill_mode)
        col4.addWidget(self.list_bill_mode)

        col4.addSpacing(4)
        self.chk_billing_form = _make_checkbox("Billing Form (01)")
        col4.addWidget(self.chk_billing_form)
        self.list_billing_form = _make_listbox(
            BILLING_FORM_ITEMS, height_rows=len(BILLING_FORM_ITEMS), enabled=False)
        self.list_billing_form.setFixedWidth(_COL4_W)
        _connect_checkbox_listbox(self.chk_billing_form, self.list_billing_form)
        col4.addWidget(self.list_billing_form)
        col4.addStretch()

        # ── Assemble columns with separator lines ─────────────────
        root.addLayout(col1)
        root.addWidget(self._vsep())
        root.addLayout(col2)
        root.addWidget(self._vsep())
        root.addLayout(col2b)
        root.addWidget(self._vsep())
        root.addLayout(col3)
        root.addWidget(self._vsep())
        root.addLayout(col4)
        root.addStretch(1)

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

    # ── Profile save/load ────────────────────────────────────────────
    def get_state(self) -> dict:
        return tab_state(self, POLICY_TAB_STATE_SPEC)

    def set_state(self, state: dict):
        apply_tab_state(self, POLICY_TAB_STATE_SPEC, state)
        if "cmb_polnum_criteria" not in state:
            self.cmb_polnum_criteria.setCurrentText(POLICYNUMBER_CRITERIA_DEFAULT)
