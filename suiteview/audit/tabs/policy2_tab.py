"""
Policy (2) tab — faithful replica of VBA frmAudit Policy (2) (tab 2).

Layout — left column groups (ordered top to bottom):
  GROUP 1: TAMRA range fields
  GROUP 2: Termination Entry Date, BIL_COMMENCE_DT, Billing suspended, Last Financial Date
  GROUP 3: Converted/replacement/GIO/COLA/Rein checkboxes
  GROUP 4: 1035 Amt, MEC, Failed Guideline or TAMRA checkboxes
"""
from __future__ import annotations

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGridLayout, QGroupBox,
    QLabel, QLineEdit, QCheckBox, QFrame, QListWidget, QSizePolicy,
)
from PyQt6.QtGui import QFont

from ..constants import (
    LOAN_TYPE_ITEMS, TRAD_OVERLOAN_IND_ITEMS, NON_TRAD_INDICATOR_ITEMS,
    DEFINITION_OF_LIFE_ITEMS, REINSURANCE_CODE_ITEMS,
    STANDARD_LOAN_PAYMENT_ITEMS,
    CHANGE_SEQ_68_ITEMS,
)
from ._styles import make_checkbox as _make_checkbox, make_listbox as _make_listbox, connect_checkbox_listbox as _connect_checkbox_listbox

# ── Compact sizing helpers (same as policy_tab) ────────────────────────
_FONT = QFont("Segoe UI", 9)
_ROW_H = 16
_CTRL_H = 22
_V_SPACING = 2
_H_SPACING = 4
_RANGE_W = 70
_LABEL_W = 195       # slightly wider for longer labels on this tab


def _connect_checkbox_widgets(chk: QCheckBox, widgets: list[QWidget]):
    """Enable/disable a list of widgets based on checkbox state."""
    def _on_toggle(checked: bool):
        for w in widgets:
            w.setEnabled(checked)
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


class Policy2Tab(QWidget):
    """Policy (2) criteria tab — mirrors VBA frmAudit Page2."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._build_ui()

    @staticmethod
    def _hsep() -> QFrame:
        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setStyleSheet("color: #bbb;")
        sep.setFixedHeight(2)
        return sep

    @staticmethod
    def _vsep() -> QFrame:
        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.VLine)
        sep.setStyleSheet("color: #bbb;")
        sep.setFixedWidth(2)
        return sep

    def _build_ui(self):
        root = QHBoxLayout(self)
        root.setContentsMargins(4, 4, 4, 4)
        root.setSpacing(8)

        # ────────────────────────────────────────────────────────────
        # LEFT COLUMN
        # ────────────────────────────────────────────────────────────
        col1 = QVBoxLayout()
        col1.setSpacing(_V_SPACING)

        # ── GROUP 1: TAMRA range fields ────────────────────────────
        grid1 = QGridLayout()
        grid1.setSpacing(_V_SPACING)
        grid1.setContentsMargins(0, 0, 0, 0)
        grid1.setHorizontalSpacing(_H_SPACING)

        r = 0
        self.txt_tamra_7pay_prem_lo, self.txt_tamra_7pay_prem_hi = _add_range_row(
            grid1, r, "TAMRA 7-Pay Premium (59)"); r += 1
        self.txt_tamra_7pay_av_lo, self.txt_tamra_7pay_av_hi = _add_range_row(
            grid1, r, "TAMRA 7-Pay Starting AV (59)"); r += 1
        self.txt_total_addl_prem_lo, self.txt_total_addl_prem_hi = _add_range_row(
            grid1, r, "Total Additional Prem (60)"); r += 1
        self.txt_total_prem_addl_reg_lo, self.txt_total_prem_addl_reg_hi = _add_range_row(
            grid1, r, "Total Prem (Additional + Reg)"); r += 1
        self.txt_accum_wd_lo, self.txt_accum_wd_hi = _add_range_row(
            grid1, r, "Accum WD (60)"); r += 1
        self.txt_prem_ytd_lo, self.txt_prem_ytd_hi = _add_range_row(
            grid1, r, "Premium Year To Date (63)"); r += 1

        col1.addLayout(grid1)

        col1.addSpacing(2); col1.addWidget(self._hsep()); col1.addSpacing(2)

        # ── GROUP 2: Termination / Billing dates ───────────────────
        grid2 = QGridLayout()
        grid2.setSpacing(_V_SPACING)
        grid2.setContentsMargins(0, 0, 0, 0)
        grid2.setHorizontalSpacing(_H_SPACING)

        r = 0
        self.txt_term_entry_date_lo, self.txt_term_entry_date_hi = _add_range_row(
            grid2, r, "Termination Entry Date (69)"); r += 1
        self.txt_bil_commence_dt_lo, self.txt_bil_commence_dt_hi = _add_range_row(
            grid2, r, "BIL_COMMENCE_DT (66)"); r += 1

        col1.addLayout(grid2)

        # Billing suspended checkbox (standalone, between the ranges)
        self.chk_billing_suspended = _make_checkbox("Billing suspended (66)")
        col1.addWidget(self.chk_billing_suspended)

        grid2b = QGridLayout()
        grid2b.setSpacing(_V_SPACING)
        grid2b.setContentsMargins(0, 0, 0, 0)
        grid2b.setHorizontalSpacing(_H_SPACING)
        self.txt_last_fin_date_lo, self.txt_last_fin_date_hi = _add_range_row(
            grid2b, 0, "Last Financial Date (01)")
        col1.addLayout(grid2b)

        col1.addSpacing(2); col1.addWidget(self._hsep()); col1.addSpacing(2)

        # ── GROUP 3: Converted / replacement / GIO / COLA / Rein ───
        self.chk_has_converted = _make_checkbox("Has converted policy (52)")
        col1.addWidget(self.chk_has_converted)
        self.chk_is_replacement = _make_checkbox("Is a replacement (52-R)")
        col1.addWidget(self.chk_is_replacement)
        self.chk_has_replacement_pol = _make_checkbox("Has a replacement pol (52-R)")
        col1.addWidget(self.chk_has_replacement_pol)
        self.chk_cov_gio = _make_checkbox("Cov has GIO ind (02)")
        col1.addWidget(self.chk_cov_gio)
        self.chk_cov_cola = _make_checkbox("Cov has COLA ind (02)")
        col1.addWidget(self.chk_cov_cola)
        self.chk_skipped_cov_rein = _make_checkbox("Skipped Cov Rein (09)")
        col1.addWidget(self.chk_skipped_cov_rein)

        col1.addSpacing(2); col1.addWidget(self._hsep()); col1.addSpacing(2)

        # ── GROUP 4: 1035 / MEC / Failed Guideline checkboxes ─────
        self.chk_1035_amt = _make_checkbox("1035 Amt (59)")
        col1.addWidget(self.chk_1035_amt)
        self.chk_mec = _make_checkbox("MEC (59)")
        col1.addWidget(self.chk_mec)
        self.chk_failed_guideline = _make_checkbox("Failed Guideline or TAMRA (66)")
        col1.addWidget(self.chk_failed_guideline)

        col1.addStretch()

        # ────────────────────────────────────────────────────────────
        # COLUMN 2 — Loan Type, Loan Rate, 77-segment, Overloan/NonTrad
        # ────────────────────────────────────────────────────────────
        col2_widget = QWidget()
        col2_widget.setMaximumWidth(420)
        col2_widget.setSizePolicy(QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Preferred)
        col2 = QVBoxLayout(col2_widget)
        col2.setContentsMargins(0, 0, 0, 0)
        col2.setSpacing(_V_SPACING)

        # ── Loan Type (01) — checkbox + listbox ────────────────────
        self.chk_loan_type = _make_checkbox("Loan Type (01)")
        col2.addWidget(self.chk_loan_type)
        self.list_loan_type = _make_listbox(LOAN_TYPE_ITEMS, height_rows=5, enabled=False)
        _connect_checkbox_listbox(self.chk_loan_type, self.list_loan_type)
        col2.addWidget(self.list_loan_type)

        col2.addSpacing(4)

        # ── Loan charge Rate (01) — text input ─────────────────────
        row_rate = QHBoxLayout(); row_rate.setSpacing(_H_SPACING)
        lbl_rate = QLabel("Loan charge Rate (01):")
        lbl_rate.setFont(_FONT)
        self.txt_loan_charge_rate = QLineEdit()
        self.txt_loan_charge_rate.setFont(_FONT)
        self.txt_loan_charge_rate.setFixedSize(_RANGE_W, _CTRL_H)
        lbl_example = QLabel("(Example: 6)")
        lbl_example.setFont(QFont("Segoe UI", 8))
        lbl_example.setStyleSheet("color: #666;")
        row_rate.addWidget(lbl_rate)
        row_rate.addWidget(self.txt_loan_charge_rate)
        row_rate.addWidget(lbl_example)
        row_rate.addStretch()
        col2.addLayout(row_rate)

        col2.addSpacing(2); col2.addWidget(self._hsep()); col2.addSpacing(2)

        # ── Policies with a 77 segment ─────────────────────────────
        lbl_77 = QLabel("Policies with a 77 segment")
        lbl_77.setFont(QFont("Segoe UI", 8))
        lbl_77.setStyleSheet("color: #444; font-style: italic;")
        col2.addWidget(lbl_77)

        # Has Loan checkbox + Preferred Loan on left, ranges on right
        loan_row = QHBoxLayout()
        loan_row.setSpacing(8)

        loan_left = QVBoxLayout()
        loan_left.setSpacing(_V_SPACING)
        self.chk_has_loan = _make_checkbox("Has Loan (77)")
        loan_left.addWidget(self.chk_has_loan)
        self.chk_has_preferred_loan = _make_checkbox("Has Preferred Loan")
        self.chk_has_preferred_loan.setEnabled(False)
        loan_left.addWidget(self.chk_has_preferred_loan)
        loan_left.addStretch()
        loan_row.addLayout(loan_left)

        grid_loan = QGridLayout()
        grid_loan.setSpacing(_V_SPACING)
        grid_loan.setContentsMargins(0, 0, 0, 0)
        grid_loan.setHorizontalSpacing(_H_SPACING)
        self.txt_total_loan_prin_lo, self.txt_total_loan_prin_hi = _add_range_row(
            grid_loan, 0, "Total Loan Principle (77)")
        self.txt_total_accured_lint_lo, self.txt_total_accured_lint_hi = _add_range_row(
            grid_loan, 1, "Total Accured Loan Int")
        for w in (self.txt_total_loan_prin_lo, self.txt_total_loan_prin_hi,
                  self.txt_total_accured_lint_lo, self.txt_total_accured_lint_hi):
            w.setEnabled(False)
        loan_row.addLayout(grid_loan)

        col2.addLayout(loan_row)

        # Wire Has Loan checkbox to enable/disable sub-fields
        _connect_checkbox_widgets(self.chk_has_loan, [
            self.chk_has_preferred_loan,
            self.txt_total_loan_prin_lo, self.txt_total_loan_prin_hi,
            self.txt_total_accured_lint_lo, self.txt_total_accured_lint_hi,
        ])

        col2.addSpacing(2); col2.addWidget(self._hsep()); col2.addSpacing(2)

        # ── Trad Overloan Ind (01) — checkbox + listbox ────────────
        self.chk_trad_overloan = _make_checkbox("Trad Overloan Ind (01)")
        col2.addWidget(self.chk_trad_overloan)
        self.list_trad_overloan = _make_listbox(TRAD_OVERLOAN_IND_ITEMS, height_rows=2, enabled=False)
        _connect_checkbox_listbox(self.chk_trad_overloan, self.list_trad_overloan)
        col2.addWidget(self.list_trad_overloan)

        col2.addSpacing(4)

        # ── Non Trad Indicator (02) — checkbox + listbox ───────────
        self.chk_non_trad = _make_checkbox("Non Trad Indicator (02)")
        col2.addWidget(self.chk_non_trad)
        self.list_non_trad = _make_listbox(NON_TRAD_INDICATOR_ITEMS, height_rows=2, enabled=False)
        _connect_checkbox_listbox(self.chk_non_trad, self.list_non_trad)
        col2.addWidget(self.list_non_trad)

        col2.addSpacing(2); col2.addWidget(self._hsep()); col2.addSpacing(2)

        # ── Scheduled Loan Payment (20) — checkbox + listbox ────────
        self.chk_std_loan_payment = _make_checkbox("Scheduled Loan Payment (20)")
        col2.addWidget(self.chk_std_loan_payment)
        self.list_std_loan_payment = _make_listbox(
            STANDARD_LOAN_PAYMENT_ITEMS, height_rows=5, enabled=False)
        _connect_checkbox_listbox(self.chk_std_loan_payment, self.list_std_loan_payment)
        col2.addWidget(self.list_std_loan_payment)

        col2.addSpacing(2); col2.addWidget(self._hsep()); col2.addSpacing(2)

        # ── Definition of Life Insurance (66) + Reinsurance Code ───
        # Side by side, matching VBA layout
        deflife_rein = QHBoxLayout()
        deflife_rein.setSpacing(8)

        dl_col = QVBoxLayout(); dl_col.setSpacing(_V_SPACING)
        self.chk_def_life = _make_checkbox("Definition of Life Insurance (66)")
        dl_col.addWidget(self.chk_def_life)
        self.list_def_life = _make_listbox(
            DEFINITION_OF_LIFE_ITEMS, height_rows=5, enabled=False)
        _connect_checkbox_listbox(self.chk_def_life, self.list_def_life)
        dl_col.addWidget(self.list_def_life)
        deflife_rein.addLayout(dl_col)

        rc_col = QVBoxLayout(); rc_col.setSpacing(_V_SPACING)
        self.chk_reinsurance = _make_checkbox("Reinsurance Code")
        rc_col.addWidget(self.chk_reinsurance)
        self.list_reinsurance = _make_listbox(
            REINSURANCE_CODE_ITEMS, height_rows=5, enabled=False)
        _connect_checkbox_listbox(self.chk_reinsurance, self.list_reinsurance)
        rc_col.addWidget(self.list_reinsurance)
        deflife_rein.addLayout(rc_col)

        col2.addLayout(deflife_rein)

        col2.addStretch()

        # ────────────────────────────────────────────────────────────
        # COLUMN 3 — Has Change Seq (68)
        # ────────────────────────────────────────────────────────────
        col3 = QVBoxLayout()
        col3.setSpacing(_V_SPACING)

        # Has Change Seq (68)
        self.chk_change_seq = _make_checkbox("Has Change Seq (68)")
        col3.addWidget(self.chk_change_seq)
        self.list_change_seq = _make_listbox(
            CHANGE_SEQ_68_ITEMS, height_rows=28, enabled=False)
        _connect_checkbox_listbox(self.chk_change_seq, self.list_change_seq)
        col3.addWidget(self.list_change_seq)
        col3.addStretch()

        # ── Assemble columns ─────────────────────────────────────────
        root.addLayout(col1)
        root.addWidget(self._vsep())
        root.addWidget(col2_widget)
        root.addWidget(self._vsep())
        root.addLayout(col3)
        root.addStretch()

    # ── Profile save/load ────────────────────────────────────────────
    def get_state(self) -> dict:
        from ..profile_manager import (
            get_lineedit_text as _t, get_checkbox_checked as _c,
            get_listbox_selected as _sel,
        )
        return {
            "txt_tamra_7pay_prem_lo": _t(self.txt_tamra_7pay_prem_lo),
            "txt_tamra_7pay_prem_hi": _t(self.txt_tamra_7pay_prem_hi),
            "txt_tamra_7pay_av_lo": _t(self.txt_tamra_7pay_av_lo),
            "txt_tamra_7pay_av_hi": _t(self.txt_tamra_7pay_av_hi),
            "txt_total_addl_prem_lo": _t(self.txt_total_addl_prem_lo),
            "txt_total_addl_prem_hi": _t(self.txt_total_addl_prem_hi),
            "txt_total_prem_addl_reg_lo": _t(self.txt_total_prem_addl_reg_lo),
            "txt_total_prem_addl_reg_hi": _t(self.txt_total_prem_addl_reg_hi),
            "txt_accum_wd_lo": _t(self.txt_accum_wd_lo),
            "txt_accum_wd_hi": _t(self.txt_accum_wd_hi),
            "txt_prem_ytd_lo": _t(self.txt_prem_ytd_lo),
            "txt_prem_ytd_hi": _t(self.txt_prem_ytd_hi),
            "txt_term_entry_date_lo": _t(self.txt_term_entry_date_lo),
            "txt_term_entry_date_hi": _t(self.txt_term_entry_date_hi),
            "txt_bil_commence_dt_lo": _t(self.txt_bil_commence_dt_lo),
            "txt_bil_commence_dt_hi": _t(self.txt_bil_commence_dt_hi),
            "chk_billing_suspended": _c(self.chk_billing_suspended),
            "txt_last_fin_date_lo": _t(self.txt_last_fin_date_lo),
            "txt_last_fin_date_hi": _t(self.txt_last_fin_date_hi),
            "chk_has_converted": _c(self.chk_has_converted),
            "chk_is_replacement": _c(self.chk_is_replacement),
            "chk_has_replacement_pol": _c(self.chk_has_replacement_pol),
            "chk_cov_gio": _c(self.chk_cov_gio),
            "chk_cov_cola": _c(self.chk_cov_cola),
            "chk_skipped_cov_rein": _c(self.chk_skipped_cov_rein),
            "chk_1035_amt": _c(self.chk_1035_amt),
            "chk_mec": _c(self.chk_mec),
            "chk_failed_guideline": _c(self.chk_failed_guideline),
            "chk_loan_type": _c(self.chk_loan_type),
            "list_loan_type": _sel(self.list_loan_type),
            "txt_loan_charge_rate": _t(self.txt_loan_charge_rate),
            "chk_has_loan": _c(self.chk_has_loan),
            "chk_has_preferred_loan": _c(self.chk_has_preferred_loan),
            "txt_total_loan_prin_lo": _t(self.txt_total_loan_prin_lo),
            "txt_total_loan_prin_hi": _t(self.txt_total_loan_prin_hi),
            "txt_total_accured_lint_lo": _t(self.txt_total_accured_lint_lo),
            "txt_total_accured_lint_hi": _t(self.txt_total_accured_lint_hi),
            "chk_trad_overloan": _c(self.chk_trad_overloan),
            "list_trad_overloan": _sel(self.list_trad_overloan),
            "chk_non_trad": _c(self.chk_non_trad),
            "list_non_trad": _sel(self.list_non_trad),
            "chk_std_loan_payment": _c(self.chk_std_loan_payment),
            "list_std_loan_payment": _sel(self.list_std_loan_payment),
            "chk_def_life": _c(self.chk_def_life),
            "list_def_life": _sel(self.list_def_life),
            "chk_reinsurance": _c(self.chk_reinsurance),
            "list_reinsurance": _sel(self.list_reinsurance),
            "chk_change_seq": _c(self.chk_change_seq),
            "list_change_seq": _sel(self.list_change_seq),
        }

    def set_state(self, state: dict):
        from ..profile_manager import (
            set_lineedit_text as _t, set_checkbox_checked as _c,
            set_listbox_selected as _sel,
        )
        _t(self.txt_tamra_7pay_prem_lo, state.get("txt_tamra_7pay_prem_lo", ""))
        _t(self.txt_tamra_7pay_prem_hi, state.get("txt_tamra_7pay_prem_hi", ""))
        _t(self.txt_tamra_7pay_av_lo, state.get("txt_tamra_7pay_av_lo", ""))
        _t(self.txt_tamra_7pay_av_hi, state.get("txt_tamra_7pay_av_hi", ""))
        _t(self.txt_total_addl_prem_lo, state.get("txt_total_addl_prem_lo", ""))
        _t(self.txt_total_addl_prem_hi, state.get("txt_total_addl_prem_hi", ""))
        _t(self.txt_total_prem_addl_reg_lo, state.get("txt_total_prem_addl_reg_lo", ""))
        _t(self.txt_total_prem_addl_reg_hi, state.get("txt_total_prem_addl_reg_hi", ""))
        _t(self.txt_accum_wd_lo, state.get("txt_accum_wd_lo", ""))
        _t(self.txt_accum_wd_hi, state.get("txt_accum_wd_hi", ""))
        _t(self.txt_prem_ytd_lo, state.get("txt_prem_ytd_lo", ""))
        _t(self.txt_prem_ytd_hi, state.get("txt_prem_ytd_hi", ""))
        _t(self.txt_term_entry_date_lo, state.get("txt_term_entry_date_lo", ""))
        _t(self.txt_term_entry_date_hi, state.get("txt_term_entry_date_hi", ""))
        _t(self.txt_bil_commence_dt_lo, state.get("txt_bil_commence_dt_lo", ""))
        _t(self.txt_bil_commence_dt_hi, state.get("txt_bil_commence_dt_hi", ""))
        _c(self.chk_billing_suspended, state.get("chk_billing_suspended", False))
        _t(self.txt_last_fin_date_lo, state.get("txt_last_fin_date_lo", ""))
        _t(self.txt_last_fin_date_hi, state.get("txt_last_fin_date_hi", ""))
        _c(self.chk_has_converted, state.get("chk_has_converted", False))
        _c(self.chk_is_replacement, state.get("chk_is_replacement", False))
        _c(self.chk_has_replacement_pol, state.get("chk_has_replacement_pol", False))
        _c(self.chk_cov_gio, state.get("chk_cov_gio", False))
        _c(self.chk_cov_cola, state.get("chk_cov_cola", False))
        _c(self.chk_skipped_cov_rein, state.get("chk_skipped_cov_rein", False))
        _c(self.chk_1035_amt, state.get("chk_1035_amt", False))
        _c(self.chk_mec, state.get("chk_mec", False))
        _c(self.chk_failed_guideline, state.get("chk_failed_guideline", False))
        _c(self.chk_loan_type, state.get("chk_loan_type", False))
        _sel(self.list_loan_type, state.get("list_loan_type", []))
        _t(self.txt_loan_charge_rate, state.get("txt_loan_charge_rate", ""))
        _c(self.chk_has_loan, state.get("chk_has_loan", False))
        _c(self.chk_has_preferred_loan, state.get("chk_has_preferred_loan", False))
        _t(self.txt_total_loan_prin_lo, state.get("txt_total_loan_prin_lo", ""))
        _t(self.txt_total_loan_prin_hi, state.get("txt_total_loan_prin_hi", ""))
        _t(self.txt_total_accured_lint_lo, state.get("txt_total_accured_lint_lo", ""))
        _t(self.txt_total_accured_lint_hi, state.get("txt_total_accured_lint_hi", ""))
        _c(self.chk_trad_overloan, state.get("chk_trad_overloan", False))
        _sel(self.list_trad_overloan, state.get("list_trad_overloan", []))
        _c(self.chk_non_trad, state.get("chk_non_trad", False))
        _sel(self.list_non_trad, state.get("list_non_trad", []))
        _c(self.chk_std_loan_payment, state.get("chk_std_loan_payment", False))
        _sel(self.list_std_loan_payment, state.get("list_std_loan_payment", []))
        _c(self.chk_def_life, state.get("chk_def_life", False))
        _sel(self.list_def_life, state.get("list_def_life", []))
        _c(self.chk_reinsurance, state.get("chk_reinsurance", False))
        _sel(self.list_reinsurance, state.get("list_reinsurance", []))
        _c(self.chk_change_seq, state.get("chk_change_seq", False))
        _sel(self.list_change_seq, state.get("list_change_seq", []))
