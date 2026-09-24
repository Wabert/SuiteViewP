"""
ADV tab — Advanced product (UL, IUL, ISWL) criteria.

Layout (three top-aligned columns, each fitted to its content):
  LEFT:   ADV comparison checkboxes, then the value/target ranges
  MIDDLE: code lists — Grace Period Rule (66), Death Benefit Option (66),
          Decrease Charge Rule (66), Orig Entry Code (01)
  RIGHT:  IUL/fund criteria — CIRF Key (55), Premium Allocation funds (57),
          Allocation Sequence Count (57), Current Fund Value (65)
"""
from __future__ import annotations

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGridLayout, QGroupBox,
    QLabel, QLineEdit, QCheckBox, QListWidget, QSizePolicy,
)
from PyQt6.QtGui import QFont, QFontMetrics

from ..constants import (
    GRACE_PERIOD_RULE_CODE_ITEMS,
    DEATH_BENEFIT_OPTION_ITEMS,
    DECREASE_CHARGE_RULE_ITEMS,
    ORIG_ENTRY_CODE_ITEMS,
    PREMIUM_ALLOCATION_FUND_ITEMS,
)
from ._styles import (
    make_checkbox as _make_checkbox, make_listbox as _make_listbox,
    make_combo as _make_combo, connect_checkbox_listbox as _connect_checkbox_listbox,
)

# ── Compact sizing helpers ──────────────────────────────────────────────
_FONT = QFont("Segoe UI", 9)
_CHK_H = 20
_CTRL_H = 22
_V_SPACING = 2
_H_SPACING = 4
_SECTION_GAP = 8
_RANGE_W = 70

_GRP_STYLE = (
    "QGroupBox { font-weight: bold; color: #1E5BA8; border: 1px solid #6A9BD1;"
    " border-radius: 3px; margin-top: 8px; padding-top: 10px; }"
    "QGroupBox::title { subcontrol-origin: margin; left: 8px; padding: 0 4px; }"
)


def _label_width(texts: list[str]) -> int:
    metrics = QFontMetrics(_FONT)
    return max(metrics.horizontalAdvance(text) for text in texts) + 8


def _add_range_row(layout: QGridLayout, row: int, label_text: str,
                   label_width: int) -> tuple[QLineEdit, QLineEdit]:
    lbl = QLabel(label_text)
    lbl.setFont(_FONT)
    lbl.setFixedWidth(label_width)

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


def _group(title: str) -> tuple[QGroupBox, QGridLayout]:
    grp = QGroupBox(title)
    grp.setStyleSheet(_GRP_STYLE)
    grid = QGridLayout(grp)
    grid.setContentsMargins(6, 6, 6, 4)
    grid.setHorizontalSpacing(_H_SPACING)
    grid.setVerticalSpacing(_V_SPACING)
    return grp, grid


def _code_list(title: str, items: list[str]) -> tuple[QWidget, QCheckBox, QListWidget]:
    """Gating checkbox above a listbox sized to show every item without scrolling."""
    panel = QWidget()
    panel.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)
    layout = QVBoxLayout(panel)
    layout.setContentsMargins(0, 0, 0, 0)
    layout.setSpacing(_V_SPACING)
    checkbox = _make_checkbox(title)
    checkbox.setFixedHeight(_CHK_H)
    layout.addWidget(checkbox)
    listbox = _make_listbox(items, height_rows=len(items), enabled=False)
    listbox.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
    listbox.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
    listbox.setMinimumWidth(
        max(listbox.fontMetrics().horizontalAdvance(text) for text in items) + 16)
    _connect_checkbox_listbox(checkbox, listbox)
    layout.addWidget(listbox)
    return panel, checkbox, listbox


def _column() -> QVBoxLayout:
    col = QVBoxLayout()
    col.setSpacing(_SECTION_GAP)
    col.setAlignment(Qt.AlignmentFlag.AlignTop)
    return col


class AdvTab(QWidget):
    """ADV Products tab — UL, IUL, ISWL criteria."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._build_ui()

    # ================================================================
    def _build_ui(self):
        root = QHBoxLayout(self)
        root.setContentsMargins(6, 6, 6, 4)
        root.setSpacing(16)

        left = self._build_left_column()
        middle = self._build_code_column()
        right = self._build_fund_column()
        for col in (left, middle, right):
            root.addLayout(col)
        root.addStretch()

    # ── Left: comparisons + value ranges ──────────────────────────
    def _build_left_column(self) -> QVBoxLayout:
        col = _column()

        checks = QVBoxLayout()
        checks.setSpacing(_V_SPACING)
        hdr = QLabel("ADV Products = UL, IUL, ISWL")
        hdr.setFont(QFont("Segoe UI", 9, QFont.Weight.Bold))
        checks.addWidget(hdr)

        self.chk_cv_corr = _make_checkbox("CV * CORR% > Specified Amount + OPTDB")
        self.chk_accum_gt_prem = _make_checkbox("Accumulation Value > Premiums Paid")
        self.chk_prem_wd_gt_face = _make_checkbox("Prem - WD > Face")
        self.chk_glp_neg = _make_checkbox("GLP is negative")
        self.chk_sa_lt_orig = _make_checkbox("Current SA < Original SA")
        self.chk_sa_gt_orig = _make_checkbox("Current SA > Original SA")
        self.chk_apb_rider = _make_checkbox("Include APB Rider as Base Coverage")
        self.chk_gcv_gt_cv = _make_checkbox("GCV > Current CV (02 and 75) (ISWL)")
        self.chk_gcv_lt_cv = _make_checkbox("GCV < Current CV (02 and 75) (ISWL)")
        for cb in (self.chk_cv_corr, self.chk_accum_gt_prem, self.chk_prem_wd_gt_face,
                   self.chk_glp_neg, self.chk_sa_lt_orig, self.chk_sa_gt_orig,
                   self.chk_apb_rider, self.chk_gcv_gt_cv, self.chk_gcv_lt_cv):
            cb.setFixedHeight(_CHK_H)
            checks.addWidget(cb)
        col.addLayout(checks)

        range_labels = [
            "Accumulation Value (75)", "Shadow Account Value (58)",
            "Current Specified Amount (02)", "Accum MTP (58)", "Accum GLP (58)",
            "GLP (58)", "GSP (58)",
        ]
        width = _label_width(range_labels)
        grp, grid = _group("Value Ranges")
        (self.rng_accum_val, self.rng_shadow_acct, self.rng_curr_spec_amt,
         self.rng_accum_mtp, self.rng_accum_glp, self.rng_glp, self.rng_gsp) = [
            _add_range_row(grid, row, text, width)
            for row, text in enumerate(range_labels)
        ]
        col.addWidget(grp)
        return col

    # ── Middle: code lists ────────────────────────────────────────
    def _build_code_column(self) -> QVBoxLayout:
        col = _column()
        panel, self.chk_grace_rule, self.list_grace_rule = _code_list(
            "Grace Period Rule Code (66)", GRACE_PERIOD_RULE_CODE_ITEMS)
        col.addWidget(panel)
        panel, self.chk_db_option, self.list_db_option = _code_list(
            "Death Benefit Option (66)", DEATH_BENEFIT_OPTION_ITEMS)
        col.addWidget(panel)
        panel, self.chk_decr_chrg_rule, self.list_decr_chrg_rule = _code_list(
            "Decrease Charge Rule (66)", DECREASE_CHARGE_RULE_ITEMS)
        col.addWidget(panel)
        panel, self.chk_orig_entry, self.list_orig_entry = _code_list(
            "Orig Entry Code (01)", ORIG_ENTRY_CODE_ITEMS)
        col.addWidget(panel)
        return col

    # ── Right: IUL / fund criteria ────────────────────────────────
    def _build_fund_column(self) -> QVBoxLayout:
        col = _column()

        grp_cirf = QGroupBox("CIRF Key (55)")
        grp_cirf.setStyleSheet(_GRP_STYLE)
        cirf_row = QHBoxLayout(grp_cirf)
        cirf_row.setContentsMargins(6, 6, 6, 4)
        cirf_row.setSpacing(_H_SPACING)
        self.cbo_cirf_match = _make_combo(["Contains", "Exact"], width=80)
        self.txt_cirf = QLineEdit()
        self.txt_cirf.setFont(_FONT)
        self.txt_cirf.setFixedHeight(_CTRL_H)
        cirf_row.addWidget(self.cbo_cirf_match)
        cirf_row.addWidget(self.txt_cirf)
        col.addWidget(grp_cirf)

        panel, self.chk_prem_alloc, self.list_prem_alloc = _code_list(
            "IUL Only - Premium Allocation funds (57)", PREMIUM_ALLOCATION_FUND_ITEMS)
        col.addWidget(panel)

        seq_labels = ["Type P Sequence (57)", "Type V Sequence (57)"]
        width = _label_width(seq_labels)
        grp_alloc, alloc_grid = _group("IUL Only - Allocation Sequence Count (57)")
        self.rng_type_p = _add_range_row(alloc_grid, 0, seq_labels[0], width)
        self.rng_type_v = _add_range_row(alloc_grid, 1, seq_labels[1], width)
        col.addWidget(grp_alloc)

        grp_fund, fund_grid = _group("Current Fund Value (65)")
        lbl_fid = QLabel("Fund ID")
        lbl_fid.setFont(_FONT)
        self.txt_fund_id = QLineEdit()
        self.txt_fund_id.setFont(_FONT)
        self.txt_fund_id.setFixedSize(_RANGE_W, _CTRL_H)
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
        fund_grid.setColumnStretch(4, 1)
        col.addWidget(grp_fund)
        return col

    # ── Profile save/load ────────────────────────────────────────────
    def get_state(self) -> dict:
        from ..profile_manager import (
            get_lineedit_text as _t, get_checkbox_checked as _c,
            get_listbox_selected as _sel, get_combo_text as _cbo,
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
            "chk_prem_wd_gt_face": _c(self.chk_prem_wd_gt_face),
            "chk_grace_rule": _c(self.chk_grace_rule),
            "list_grace_rule": _sel(self.list_grace_rule),
            "chk_db_option": _c(self.chk_db_option),
            "list_db_option": _sel(self.list_db_option),
            "chk_decr_chrg_rule": _c(self.chk_decr_chrg_rule),
            "list_decr_chrg_rule": _sel(self.list_decr_chrg_rule),
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
            "rng_glp_lo": _t(self.rng_glp[0]),
            "rng_glp_hi": _t(self.rng_glp[1]),
            "rng_gsp_lo": _t(self.rng_gsp[0]),
            "rng_gsp_hi": _t(self.rng_gsp[1]),
            "chk_prem_alloc": _c(self.chk_prem_alloc),
            "list_prem_alloc": _sel(self.list_prem_alloc),
            "rng_type_p_lo": _t(self.rng_type_p[0]),
            "rng_type_p_hi": _t(self.rng_type_p[1]),
            "rng_type_v_lo": _t(self.rng_type_v[0]),
            "rng_type_v_hi": _t(self.rng_type_v[1]),
            "cbo_cirf_match": _cbo(self.cbo_cirf_match),
            "txt_cirf": _t(self.txt_cirf),
        }

    def set_state(self, state: dict):
        from ..profile_manager import (
            set_lineedit_text as _t, set_checkbox_checked as _c,
            set_listbox_selected as _sel, set_combo_text as _cbo,
        )
        _c(self.chk_cv_corr, state.get("chk_cv_corr", False))
        _c(self.chk_accum_gt_prem, state.get("chk_accum_gt_prem", False))
        _c(self.chk_glp_neg, state.get("chk_glp_neg", False))
        _c(self.chk_sa_lt_orig, state.get("chk_sa_lt_orig", False))
        _c(self.chk_sa_gt_orig, state.get("chk_sa_gt_orig", False))
        _c(self.chk_apb_rider, state.get("chk_apb_rider", False))
        _c(self.chk_gcv_gt_cv, state.get("chk_gcv_gt_cv", False))
        _c(self.chk_gcv_lt_cv, state.get("chk_gcv_lt_cv", False))
        _c(self.chk_prem_wd_gt_face, state.get("chk_prem_wd_gt_face", False))
        _c(self.chk_grace_rule, state.get("chk_grace_rule", False))
        _sel(self.list_grace_rule, state.get("list_grace_rule", []))
        _c(self.chk_db_option, state.get("chk_db_option", False))
        _sel(self.list_db_option, state.get("list_db_option", []))
        _c(self.chk_decr_chrg_rule, state.get("chk_decr_chrg_rule", False))
        _sel(self.list_decr_chrg_rule, state.get("list_decr_chrg_rule", []))
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
        _t(self.rng_glp[0], state.get("rng_glp_lo", ""))
        _t(self.rng_glp[1], state.get("rng_glp_hi", ""))
        _t(self.rng_gsp[0], state.get("rng_gsp_lo", ""))
        _t(self.rng_gsp[1], state.get("rng_gsp_hi", ""))
        _c(self.chk_prem_alloc, state.get("chk_prem_alloc", False))
        _sel(self.list_prem_alloc, state.get("list_prem_alloc", []))
        _t(self.rng_type_p[0], state.get("rng_type_p_lo", ""))
        _t(self.rng_type_p[1], state.get("rng_type_p_hi", ""))
        _t(self.rng_type_v[0], state.get("rng_type_v_lo", ""))
        _t(self.rng_type_v[1], state.get("rng_type_v_hi", ""))
        _cbo(self.cbo_cirf_match, state.get("cbo_cirf_match", "Contains"))
        _t(self.txt_cirf, state.get("txt_cirf", ""))
