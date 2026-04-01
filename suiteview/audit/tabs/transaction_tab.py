"""
Transaction tab — faithful replica of VBA frmAudit Transaction tab.

Layout (two columns):
  LEFT:  Transaction Type and Subtype — read-only reference listbox (green border)
         + note label + checkboxes + Eff Month/Day ranges
  RIGHT: Transaction 1 input row:
         combo + Entry Date Range + Effective Date Range +
         Gross Amount Range + ORIGIN_OF_TRANS + Fund ID List
"""
from __future__ import annotations

from PyQt6.QtCore import Qt, QSize
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGroupBox,
    QLabel, QLineEdit, QCheckBox, QComboBox, QListWidget,
    QAbstractItemView, QStyledItemDelegate, QFrame,
)
from PyQt6.QtGui import QFont

from ..constants import TRANSACTION_TYPE_ITEMS
from ._styles import make_checkbox as _make_checkbox, style_combo as _style_combo

# ── Compact sizing helpers ──────────────────────────────────────────────
_FONT = QFont("Segoe UI", 9)
_FONT_BOLD = QFont("Segoe UI", 9, QFont.Weight.Bold)
_ROW_H = 16
_CTRL_H = 22
_V_SPACING = 2
_H_SPACING = 6
_RANGE_W = 70

_GRP_STYLE = (
    "QGroupBox { font-weight: bold; color: #1E5BA8; border: 1px solid #6A9BD1;"
    " border-radius: 3px; margin-top: 8px; padding-top: 10px; }"
    "QGroupBox::title { subcontrol-origin: margin; left: 8px; padding: 0 4px; }"
)

_GRP_STYLE_GREEN = (
    "QGroupBox { font-weight: bold; color: #2E7D32; border: 1px solid #4CAF50;"
    " border-radius: 3px; margin-top: 8px; padding-top: 10px; }"
    "QGroupBox::title { subcontrol-origin: margin; left: 8px; padding: 0 4px; }"
)


class _TightItemDelegate(QStyledItemDelegate):
    ROW_H = _ROW_H
    def sizeHint(self, option, index):
        sh = super().sizeHint(option, index)
        return QSize(sh.width(), self.ROW_H)


class TransactionTab(QWidget):
    """Transaction tab — transaction type reference + filter inputs."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._build_ui()

    def _build_ui(self):
        root = QHBoxLayout(self)
        root.setContentsMargins(6, 6, 6, 4)
        root.setSpacing(10)

        # ════════════════════════════════════════════════════════════
        # LEFT COLUMN — reference listbox + note + checkboxes + ranges
        # ════════════════════════════════════════════════════════════
        left = QVBoxLayout()
        left.setSpacing(4)

        # Transaction Type and Subtype — read-only reference list
        grp_ref = QGroupBox("Transaction Type and Subtype")
        grp_ref.setStyleSheet(_GRP_STYLE_GREEN)
        ref_lay = QVBoxLayout(grp_ref)
        ref_lay.setContentsMargins(6, 6, 6, 4)
        ref_lay.setSpacing(_V_SPACING)

        self.list_trans_ref = QListWidget()
        self.list_trans_ref.setFont(_FONT)
        self.list_trans_ref.setItemDelegate(_TightItemDelegate(self.list_trans_ref))
        self.list_trans_ref.setUniformItemSizes(True)
        self.list_trans_ref.setSelectionMode(
            QAbstractItemView.SelectionMode.NoSelection)
        self.list_trans_ref.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.list_trans_ref.setStyleSheet(
            "QListWidget { border: none; background-color: #F5F5F0; color: #555; }"
            "QListWidget::item { padding: 0px 2px; }"
        )
        self.list_trans_ref.addItems(TRANSACTION_TYPE_ITEMS)
        self.list_trans_ref.setMinimumWidth(320)
        ref_lay.addWidget(self.list_trans_ref)
        left.addWidget(grp_ref, 1)  # stretch so listbox fills

        # Note label
        note = QLabel(
            "Note: Query time on transactions will\n"
            "be much longer without a plancode")
        note.setFont(_FONT)
        note.setStyleSheet("color: #C00000;")
        left.addWidget(note)

        # Checkboxes
        self.chk_eff_day = _make_checkbox("Effective day = Issue day")
        self.chk_eff_month = _make_checkbox("Effective month = Issue month")
        left.addWidget(self.chk_eff_day)
        left.addWidget(self.chk_eff_month)

        root.addLayout(left)

        # ════════════════════════════════════════════════════════════
        # RIGHT COLUMN — Transaction 1 filter inputs (vertical)
        # ════════════════════════════════════════════════════════════
        right = QVBoxLayout()
        right.setSpacing(6)

        # Transaction Type and Subtype combo
        lbl_ts = QLabel("Transaction Type and Subtype")
        lbl_ts.setFont(_FONT_BOLD)
        right.addWidget(lbl_ts)

        row_trans = QHBoxLayout()
        row_trans.setSpacing(_H_SPACING)
        lbl_t1 = QLabel("Transaction 1:")
        lbl_t1.setFont(_FONT)
        self.cmb_transaction = QComboBox()
        self.cmb_transaction.setFont(_FONT)
        self.cmb_transaction.setFixedHeight(_CTRL_H)
        self.cmb_transaction.setMinimumWidth(280)
        self.cmb_transaction.addItem("")
        self.cmb_transaction.addItems(TRANSACTION_TYPE_ITEMS)
        _style_combo(self.cmb_transaction)
        row_trans.addWidget(lbl_t1)
        row_trans.addWidget(self.cmb_transaction)
        row_trans.addStretch()
        right.addLayout(row_trans)
        right.addSpacing(4)

        # Entry Date Range
        lbl_ed = QLabel("Entry Date Range")
        lbl_ed.setFont(_FONT_BOLD)
        right.addWidget(lbl_ed)
        row_entry = QHBoxLayout()
        row_entry.setSpacing(_H_SPACING)
        self.txt_entry_lo = QLineEdit()
        self.txt_entry_lo.setFont(_FONT)
        self.txt_entry_lo.setFixedSize(_RANGE_W, _CTRL_H)
        lbl_to1 = QLabel("to")
        lbl_to1.setFont(_FONT)
        self.txt_entry_hi = QLineEdit()
        self.txt_entry_hi.setFont(_FONT)
        self.txt_entry_hi.setFixedSize(_RANGE_W, _CTRL_H)
        row_entry.addWidget(self.txt_entry_lo)
        row_entry.addWidget(lbl_to1)
        row_entry.addWidget(self.txt_entry_hi)
        row_entry.addStretch()
        right.addLayout(row_entry)
        right.addSpacing(4)

        # Effective Date Range
        lbl_eff = QLabel("Effective Date Range")
        lbl_eff.setFont(_FONT_BOLD)
        right.addWidget(lbl_eff)
        row_eff = QHBoxLayout()
        row_eff.setSpacing(_H_SPACING)
        self.txt_eff_lo = QLineEdit()
        self.txt_eff_lo.setFont(_FONT)
        self.txt_eff_lo.setFixedSize(_RANGE_W, _CTRL_H)
        lbl_to2 = QLabel("to")
        lbl_to2.setFont(_FONT)
        self.txt_eff_hi = QLineEdit()
        self.txt_eff_hi.setFont(_FONT)
        self.txt_eff_hi.setFixedSize(_RANGE_W, _CTRL_H)
        row_eff.addWidget(self.txt_eff_lo)
        row_eff.addWidget(lbl_to2)
        row_eff.addWidget(self.txt_eff_hi)
        row_eff.addStretch()
        right.addLayout(row_eff)
        right.addSpacing(2)

        # Eff Month Range
        lbl_em = QLabel("Eff Month Range")
        lbl_em.setFont(_FONT_BOLD)
        right.addWidget(lbl_em)
        row_em = QHBoxLayout()
        row_em.setSpacing(_H_SPACING)
        self.txt_eff_month_lo = QLineEdit()
        self.txt_eff_month_lo.setFont(_FONT)
        self.txt_eff_month_lo.setFixedSize(_RANGE_W, _CTRL_H)
        lbl_to_em = QLabel("to")
        lbl_to_em.setFont(_FONT)
        self.txt_eff_month_hi = QLineEdit()
        self.txt_eff_month_hi.setFont(_FONT)
        self.txt_eff_month_hi.setFixedSize(_RANGE_W, _CTRL_H)
        row_em.addWidget(self.txt_eff_month_lo)
        row_em.addWidget(lbl_to_em)
        row_em.addWidget(self.txt_eff_month_hi)
        row_em.addStretch()
        right.addLayout(row_em)
        right.addSpacing(2)

        # Eff Day Range
        lbl_ed2 = QLabel("Eff Day Range")
        lbl_ed2.setFont(_FONT_BOLD)
        right.addWidget(lbl_ed2)
        row_ed2 = QHBoxLayout()
        row_ed2.setSpacing(_H_SPACING)
        self.txt_eff_day_lo = QLineEdit()
        self.txt_eff_day_lo.setFont(_FONT)
        self.txt_eff_day_lo.setFixedSize(_RANGE_W, _CTRL_H)
        lbl_to_ed2 = QLabel("to")
        lbl_to_ed2.setFont(_FONT)
        self.txt_eff_day_hi = QLineEdit()
        self.txt_eff_day_hi.setFont(_FONT)
        self.txt_eff_day_hi.setFixedSize(_RANGE_W, _CTRL_H)
        row_ed2.addWidget(self.txt_eff_day_lo)
        row_ed2.addWidget(lbl_to_ed2)
        row_ed2.addWidget(self.txt_eff_day_hi)
        row_ed2.addStretch()
        right.addLayout(row_ed2)
        right.addSpacing(4)

        # Gross Amount Range
        lbl_ga = QLabel("Gross Amount Range")
        lbl_ga.setFont(_FONT_BOLD)
        right.addWidget(lbl_ga)
        row_gross = QHBoxLayout()
        row_gross.setSpacing(_H_SPACING)
        self.txt_gross_lo = QLineEdit()
        self.txt_gross_lo.setFont(_FONT)
        self.txt_gross_lo.setFixedSize(_RANGE_W, _CTRL_H)
        lbl_to3 = QLabel("to")
        lbl_to3.setFont(_FONT)
        self.txt_gross_hi = QLineEdit()
        self.txt_gross_hi.setFont(_FONT)
        self.txt_gross_hi.setFixedSize(_RANGE_W, _CTRL_H)
        row_gross.addWidget(self.txt_gross_lo)
        row_gross.addWidget(lbl_to3)
        row_gross.addWidget(self.txt_gross_hi)
        row_gross.addStretch()
        right.addLayout(row_gross)
        right.addSpacing(4)

        # ORIGIN_OF_TRANS
        lbl_ot = QLabel("ORIGIN_OF_TRANS")
        lbl_ot.setFont(_FONT_BOLD)
        right.addWidget(lbl_ot)
        self.txt_origin = QLineEdit()
        self.txt_origin.setFont(_FONT)
        self.txt_origin.setFixedSize(_RANGE_W, _CTRL_H)
        right.addWidget(self.txt_origin)
        right.addSpacing(4)

        # Fund ID List
        lbl_fid = QLabel("Fund ID List")
        lbl_fid.setFont(_FONT_BOLD)
        right.addWidget(lbl_fid)
        self.txt_fund_id = QLineEdit()
        self.txt_fund_id.setFont(_FONT)
        self.txt_fund_id.setFixedSize(_RANGE_W, _CTRL_H)
        right.addWidget(self.txt_fund_id)

        right.addStretch()
        root.addLayout(right)
        root.addStretch()

    # ── Profile save/load ────────────────────────────────────────────
    def get_state(self) -> dict:
        from ..profile_manager import (
            get_lineedit_text as _t, get_checkbox_checked as _c,
            get_combo_text as _cmb,
        )
        return {
            "chk_eff_day": _c(self.chk_eff_day),
            "chk_eff_month": _c(self.chk_eff_month),
            "cmb_transaction": _cmb(self.cmb_transaction),
            "txt_entry_lo": _t(self.txt_entry_lo),
            "txt_entry_hi": _t(self.txt_entry_hi),
            "txt_eff_lo": _t(self.txt_eff_lo),
            "txt_eff_hi": _t(self.txt_eff_hi),
            "txt_eff_month_lo": _t(self.txt_eff_month_lo),
            "txt_eff_month_hi": _t(self.txt_eff_month_hi),
            "txt_eff_day_lo": _t(self.txt_eff_day_lo),
            "txt_eff_day_hi": _t(self.txt_eff_day_hi),
            "txt_gross_lo": _t(self.txt_gross_lo),
            "txt_gross_hi": _t(self.txt_gross_hi),
            "txt_origin": _t(self.txt_origin),
            "txt_fund_id": _t(self.txt_fund_id),
        }

    def set_state(self, state: dict):
        from ..profile_manager import (
            set_lineedit_text as _t, set_checkbox_checked as _c,
            set_combo_text as _cmb,
        )
        _c(self.chk_eff_day, state.get("chk_eff_day", False))
        _c(self.chk_eff_month, state.get("chk_eff_month", False))
        _cmb(self.cmb_transaction, state.get("cmb_transaction", ""))
        _t(self.txt_entry_lo, state.get("txt_entry_lo", ""))
        _t(self.txt_entry_hi, state.get("txt_entry_hi", ""))
        _t(self.txt_eff_lo, state.get("txt_eff_lo", ""))
        _t(self.txt_eff_hi, state.get("txt_eff_hi", ""))
        _t(self.txt_eff_month_lo, state.get("txt_eff_month_lo", ""))
        _t(self.txt_eff_month_hi, state.get("txt_eff_month_hi", ""))
        _t(self.txt_eff_day_lo, state.get("txt_eff_day_lo", ""))
        _t(self.txt_eff_day_hi, state.get("txt_eff_day_hi", ""))
        _t(self.txt_gross_lo, state.get("txt_gross_lo", ""))
        _t(self.txt_gross_hi, state.get("txt_gross_hi", ""))
        _t(self.txt_origin, state.get("txt_origin", ""))
        _t(self.txt_fund_id, state.get("txt_fund_id", ""))
