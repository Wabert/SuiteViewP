"""
ADV tab — faithful replica of VBA frmAudit ADV tab.

Layout:
  TOP ROW (3 columns):
    COL 1: "ADV Products = UL, IUL, ISWL" header + checkboxes
    COL 2: Grace Period Rule Code (66) + Death Benefit Option (66)
    COL 3: Orig Entry Code (01)
  BOTTOM ROW (3 zones):
    LEFT:   Current Fund Value (65) group + range fields below
    CENTER: IUL Only – Premium Allocation funds (57)
    RIGHT:  IUL Only – Allocation Sequence Count (57 segment)
"""
from __future__ import annotations

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGridLayout, QGroupBox,
    QLabel, QLineEdit, QCheckBox, QFrame, QListWidget, QSizePolicy,
)
from PyQt6.QtGui import QFont

from ..constants import (
    GRACE_PERIOD_RULE_CODE_ITEMS,
    DEATH_BENEFIT_OPTION_ITEMS,
    ORIG_ENTRY_CODE_ITEMS,
    PREMIUM_ALLOCATION_FUND_ITEMS,
)
from ._styles import make_checkbox as _make_checkbox, make_listbox as _make_listbox, connect_checkbox_listbox as _connect_checkbox_listbox

# ── Compact sizing helpers ──────────────────────────────────────────────
_FONT = QFont("Segoe UI", 9)
_ROW_H = 16
_CTRL_H = 22
_V_SPACING = 2
_H_SPACING = 4
_RANGE_W = 70
_LABEL_W = 210

_GRP_STYLE = (
    "QGroupBox { font-weight: bold; color: #1E5BA8; border: 1px solid #6A9BD1;"
    " border-radius: 3px; margin-top: 8px; padding-top: 10px; }"
    "QGroupBox::title { subcontrol-origin: margin; left: 8px; padding: 0 4px; }"
)


def _connect_checkbox_widgets(chk: QCheckBox, widgets: list[QWidget]):
    def _on_toggle(checked: bool):
        for w in widgets:
            w.setEnabled(checked)
            if not checked and isinstance(w, QLineEdit):
                w.clear()
    chk.toggled.connect(_on_toggle)


def _add_range_row(layout: QGridLayout, row: int, label_text: str,
                   *, label_color: str | None = None) -> tuple[QLineEdit, QLineEdit]:
    lbl = QLabel(label_text)
    lbl.setFont(_FONT)
    lbl.setFixedWidth(_LABEL_W)
    if label_color:
        lbl.setStyleSheet(f"color: {label_color};")

    lo = QLineEdit()
    lo.setFont(_FONT)
    lo.setFixedSize(_RANGE_W, _CTRL_H)

    lbl_to = QLabel("to")
    lbl_to.setFont(_FONT)

    hi = QLineEdit()
    hi.setFont(_FONT)
    hi.setFixedSize(_RANGE_W, _CTRL_H)

    layout.addWidget(lbl, row, 0)
    layout.addWidget(lo, row, 1)
    layout.addWidget(lbl_to, row, 2, Qt.AlignmentFlag.AlignCenter)
    layout.addWidget(hi, row, 3)
    return lo, hi


class AdvTab(QWidget):
    """ADV Products tab — UL, IUL, ISWL criteria."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._build_ui()

    # ================================================================
    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(6, 6, 6, 4)
        root.setSpacing(6)

        # ────────────────────────────────────────────────────────────
        # TOP SECTION
        # ────────────────────────────────────────────────────────────
        top_row = QHBoxLayout()
        top_row.setSpacing(12)

        # ── Column 1: header label + checkboxes ────────────────────
        col1 = QVBoxLayout()
        col1.setSpacing(_V_SPACING)

        hdr = QLabel("ADV Products = UL, IUL, ISWL")
        hdr.setFont(QFont("Segoe UI", 9, QFont.Weight.Bold))
        col1.addWidget(hdr)
        col1.addSpacing(4)

        self.chk_cv_corr = _make_checkbox(
            "CV * CORR% > Specified Amount + OPTDB")
        self.chk_accum_gt_prem = _make_checkbox(
            "Accumulation Value > Premiums Paid")
        col1.addWidget(self.chk_cv_corr)
        col1.addWidget(self.chk_accum_gt_prem)
        col1.addSpacing(8)

        self.chk_glp_neg = _make_checkbox("GLP is negative")
        self.chk_sa_lt_orig = _make_checkbox("Current SA < Original SA")
        self.chk_sa_gt_orig = _make_checkbox("Current SA > Original SA")
        self.chk_apb_rider = _make_checkbox(
            "Include APB Rider as Base Coverage")
        self.chk_gcv_gt_cv = _make_checkbox(
            "GCV > Current CV (02 and 75) (ISWL)")
        self.chk_gcv_lt_cv = _make_checkbox(
            "GCV < Current CV (02 and 75) (ISWL)")
        for cb in (self.chk_glp_neg, self.chk_sa_lt_orig,
                   self.chk_sa_gt_orig, self.chk_apb_rider,
                   self.chk_gcv_gt_cv, self.chk_gcv_lt_cv):
            col1.addWidget(cb)

        col1.addStretch()
        top_row.addLayout(col1)

        # ── Column 2: Grace Period Rule Code + Death Benefit Opt ───
        col2 = QVBoxLayout()
        col2.setSpacing(_V_SPACING)

        # Grace Period Rule Code (66)
        self.chk_grace_rule = _make_checkbox("Grace Period Rule Code (66)")
        col2.addWidget(self.chk_grace_rule)
        self.list_grace_rule = _make_listbox(
            GRACE_PERIOD_RULE_CODE_ITEMS, height_rows=6, enabled=False)
        _connect_checkbox_listbox(self.chk_grace_rule, self.list_grace_rule)
        col2.addWidget(self.list_grace_rule)
        col2.addSpacing(8)

        # Death Benefit Option (66)
        self.chk_db_option = _make_checkbox("Death Benefit Option (66)")
        col2.addWidget(self.chk_db_option)
        self.list_db_option = _make_listbox(
            DEATH_BENEFIT_OPTION_ITEMS, height_rows=4, enabled=False)
        _connect_checkbox_listbox(self.chk_db_option, self.list_db_option)
        col2.addWidget(self.list_db_option)

        col2.addStretch()
        top_row.addLayout(col2)

        # ── Column 3: Orig Entry Code (01) ────────────────────────
        col3 = QVBoxLayout()
        col3.setSpacing(_V_SPACING)

        self.chk_orig_entry = _make_checkbox("Orig Entry Code (01)")
        col3.addWidget(self.chk_orig_entry)
        self.list_orig_entry = _make_listbox(
            ORIG_ENTRY_CODE_ITEMS, height_rows=10, enabled=False)
        _connect_checkbox_listbox(self.chk_orig_entry, self.list_orig_entry)
        col3.addWidget(self.list_orig_entry)

        col3.addStretch()
        top_row.addLayout(col3)

        top_row.addStretch()
        root.addLayout(top_row)

        # ────────────────────────────────────────────────────────────
        # BOTTOM SECTION
        # ────────────────────────────────────────────────────────────
        bot_row = QHBoxLayout()
        bot_row.setSpacing(12)

        # ── Bottom-left: Current Fund Value (65) + range fields ────
        bot_left = QVBoxLayout()
        bot_left.setSpacing(_V_SPACING)

        grp_fund = QGroupBox("Current Fund Value (65)")
        grp_fund.setStyleSheet(_GRP_STYLE)
        fund_grid = QGridLayout(grp_fund)
        fund_grid.setContentsMargins(6, 6, 6, 4)
        fund_grid.setHorizontalSpacing(_H_SPACING)
        fund_grid.setVerticalSpacing(_V_SPACING)

        lbl_fid = QLabel("Fund ID")
        lbl_fid.setFont(_FONT)
        self.txt_fund_id = QLineEdit()
        self.txt_fund_id.setFont(_FONT)
        self.txt_fund_id.setFixedSize(80, _CTRL_H)

        lbl_fvr = QLabel("Fund Value Range")
        lbl_fvr.setFont(_FONT)
        self.txt_fund_lo = QLineEdit()
        self.txt_fund_lo.setFont(_FONT)
        self.txt_fund_lo.setFixedSize(_RANGE_W, _CTRL_H)
        lbl_to_f = QLabel("to")
        lbl_to_f.setFont(_FONT)
        self.txt_fund_hi = QLineEdit()
        self.txt_fund_hi.setFont(_FONT)
        self.txt_fund_hi.setFixedSize(_RANGE_W, _CTRL_H)

        fund_grid.addWidget(lbl_fid, 0, 0)
        fund_grid.addWidget(lbl_fvr, 0, 1, 1, 3)
        fund_grid.addWidget(self.txt_fund_id, 1, 0)
        fund_grid.addWidget(self.txt_fund_lo, 1, 1)
        fund_grid.addWidget(lbl_to_f, 1, 2, Qt.AlignmentFlag.AlignCenter)
        fund_grid.addWidget(self.txt_fund_hi, 1, 3)

        bot_left.addWidget(grp_fund)
        bot_left.addSpacing(4)

        # Range fields below the group
        range_grid = QGridLayout()
        range_grid.setHorizontalSpacing(_H_SPACING)
        range_grid.setVerticalSpacing(_V_SPACING)

        self.rng_accum_val = _add_range_row(
            range_grid, 0, "Accumulation Value range (75)")
        self.rng_shadow_acct = _add_range_row(
            range_grid, 1, "Shadow Account Value (58)")
        self.rng_curr_spec_amt = _add_range_row(
            range_grid, 2, "Current Specified Amount (02)")
        self.rng_accum_mtp = _add_range_row(
            range_grid, 3, "Accum MTP (58)")
        self.rng_accum_glp = _add_range_row(
            range_grid, 4, "Accum GLP (58)")

        bot_left.addLayout(range_grid)
        bot_left.addStretch()

        bot_row.addLayout(bot_left)

        # ── Bottom-center: IUL Only – Premium Allocation Funds ────
        bot_center = QVBoxLayout()
        bot_center.setSpacing(_V_SPACING)

        self.chk_prem_alloc = _make_checkbox("IUL Only - Premium Allocation funds (57)")
        bot_center.addWidget(self.chk_prem_alloc)
        self.list_prem_alloc = _make_listbox(
            PREMIUM_ALLOCATION_FUND_ITEMS, height_rows=10, enabled=False)
        _connect_checkbox_listbox(self.chk_prem_alloc, self.list_prem_alloc)
        bot_center.addWidget(self.list_prem_alloc)

        bot_center.addStretch()
        bot_row.addLayout(bot_center)

        # ── Bottom-right: IUL Only – Allocation Sequence Count ────
        bot_right = QVBoxLayout()
        bot_right.setSpacing(_V_SPACING)

        grp_alloc = QGroupBox(
            "IUL Only - Allocation Sequence Count (57 segment)")
        grp_alloc.setStyleSheet(_GRP_STYLE)
        alloc_grid = QGridLayout(grp_alloc)
        alloc_grid.setContentsMargins(6, 6, 6, 4)
        alloc_grid.setHorizontalSpacing(_H_SPACING)
        alloc_grid.setVerticalSpacing(_V_SPACING)

        self.rng_type_p = _add_range_row(
            alloc_grid, 0, "Type P Sequence (57)")
        self.rng_type_v = _add_range_row(
            alloc_grid, 1, "Type V Sequence (57)")

        bot_right.addWidget(grp_alloc)
        bot_right.addStretch()

        bot_row.addLayout(bot_right)
        bot_row.addStretch()

        root.addLayout(bot_row)

    # ── Vertical separator helper ──────────────────────────────────
    @staticmethod
    def _vsep() -> QFrame:
        f = QFrame()
        f.setFrameShape(QFrame.Shape.VLine)
        f.setFrameShadow(QFrame.Shadow.Sunken)
        return f

    # ── Profile save/load ────────────────────────────────────────────
    def get_state(self) -> dict:
        from ..profile_manager import (
            get_lineedit_text as _t, get_checkbox_checked as _c,
            get_listbox_selected as _sel,
        )
        return {
            "chk_cv_corr": _c(self.chk_cv_corr),
            "chk_accum_gt_prem": _c(self.chk_accum_gt_prem),
            "chk_glp_neg": _c(self.chk_glp_neg),
            "chk_sa_lt_orig": _c(self.chk_sa_lt_orig),
            "chk_sa_gt_orig": _c(self.chk_sa_gt_orig),
            "chk_apb_rider": _c(self.chk_apb_rider),
            "chk_gcv_gt_cv": _c(self.chk_gcv_gt_cv),
            "chk_gcv_lt_cv": _c(self.chk_gcv_lt_cv),
            "chk_grace_rule": _c(self.chk_grace_rule),
            "list_grace_rule": _sel(self.list_grace_rule),
            "chk_db_option": _c(self.chk_db_option),
            "list_db_option": _sel(self.list_db_option),
            "chk_orig_entry": _c(self.chk_orig_entry),
            "list_orig_entry": _sel(self.list_orig_entry),
            "txt_fund_id": _t(self.txt_fund_id),
            "txt_fund_lo": _t(self.txt_fund_lo),
            "txt_fund_hi": _t(self.txt_fund_hi),
            "rng_accum_val_lo": _t(self.rng_accum_val[0]),
            "rng_accum_val_hi": _t(self.rng_accum_val[1]),
            "rng_shadow_acct_lo": _t(self.rng_shadow_acct[0]),
            "rng_shadow_acct_hi": _t(self.rng_shadow_acct[1]),
            "rng_curr_spec_amt_lo": _t(self.rng_curr_spec_amt[0]),
            "rng_curr_spec_amt_hi": _t(self.rng_curr_spec_amt[1]),
            "rng_accum_mtp_lo": _t(self.rng_accum_mtp[0]),
            "rng_accum_mtp_hi": _t(self.rng_accum_mtp[1]),
            "rng_accum_glp_lo": _t(self.rng_accum_glp[0]),
            "rng_accum_glp_hi": _t(self.rng_accum_glp[1]),
            "chk_prem_alloc": _c(self.chk_prem_alloc),
            "list_prem_alloc": _sel(self.list_prem_alloc),
            "rng_type_p_lo": _t(self.rng_type_p[0]),
            "rng_type_p_hi": _t(self.rng_type_p[1]),
            "rng_type_v_lo": _t(self.rng_type_v[0]),
            "rng_type_v_hi": _t(self.rng_type_v[1]),
        }

    def set_state(self, state: dict):
        from ..profile_manager import (
            set_lineedit_text as _t, set_checkbox_checked as _c,
            set_listbox_selected as _sel,
        )
        _c(self.chk_cv_corr, state.get("chk_cv_corr", False))
        _c(self.chk_accum_gt_prem, state.get("chk_accum_gt_prem", False))
        _c(self.chk_glp_neg, state.get("chk_glp_neg", False))
        _c(self.chk_sa_lt_orig, state.get("chk_sa_lt_orig", False))
        _c(self.chk_sa_gt_orig, state.get("chk_sa_gt_orig", False))
        _c(self.chk_apb_rider, state.get("chk_apb_rider", False))
        _c(self.chk_gcv_gt_cv, state.get("chk_gcv_gt_cv", False))
        _c(self.chk_gcv_lt_cv, state.get("chk_gcv_lt_cv", False))
        _c(self.chk_grace_rule, state.get("chk_grace_rule", False))
        _sel(self.list_grace_rule, state.get("list_grace_rule", []))
        _c(self.chk_db_option, state.get("chk_db_option", False))
        _sel(self.list_db_option, state.get("list_db_option", []))
        _c(self.chk_orig_entry, state.get("chk_orig_entry", False))
        _sel(self.list_orig_entry, state.get("list_orig_entry", []))
        _t(self.txt_fund_id, state.get("txt_fund_id", ""))
        _t(self.txt_fund_lo, state.get("txt_fund_lo", ""))
        _t(self.txt_fund_hi, state.get("txt_fund_hi", ""))
        _t(self.rng_accum_val[0], state.get("rng_accum_val_lo", ""))
        _t(self.rng_accum_val[1], state.get("rng_accum_val_hi", ""))
        _t(self.rng_shadow_acct[0], state.get("rng_shadow_acct_lo", ""))
        _t(self.rng_shadow_acct[1], state.get("rng_shadow_acct_hi", ""))
        _t(self.rng_curr_spec_amt[0], state.get("rng_curr_spec_amt_lo", ""))
        _t(self.rng_curr_spec_amt[1], state.get("rng_curr_spec_amt_hi", ""))
        _t(self.rng_accum_mtp[0], state.get("rng_accum_mtp_lo", ""))
        _t(self.rng_accum_mtp[1], state.get("rng_accum_mtp_hi", ""))
        _t(self.rng_accum_glp[0], state.get("rng_accum_glp_lo", ""))
        _t(self.rng_accum_glp[1], state.get("rng_accum_glp_hi", ""))
        _c(self.chk_prem_alloc, state.get("chk_prem_alloc", False))
        _sel(self.list_prem_alloc, state.get("list_prem_alloc", []))
        _t(self.rng_type_p[0], state.get("rng_type_p_lo", ""))
        _t(self.rng_type_p[1], state.get("rng_type_p_hi", ""))
        _t(self.rng_type_v[0], state.get("rng_type_v_lo", ""))
        _t(self.rng_type_v[1], state.get("rng_type_v_hi", ""))
