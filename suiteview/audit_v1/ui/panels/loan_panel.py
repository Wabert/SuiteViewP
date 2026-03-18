"""
Loan Criteria Panel
====================
Loan-specific filters — absolute coordinate placement.
Row 0: Loan Type | Trad Overloan Ind | Standard Loan Payment
Row 1: boolean checkboxes + range fields
"""

from __future__ import annotations

from typing import Dict, List, Tuple

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QFontMetrics
from PyQt6.QtWidgets import (
    QGroupBox, QListWidget, QListWidgetItem,
    QAbstractItemView, QVBoxLayout, QHBoxLayout,
    QCheckBox, QWidget, QLabel, QLineEdit,
)

from .panel_widgets import CriteriaPanel
from ..styles import BLUE_PRIMARY, BLUE_DARK, SILVER_MID
from ...models.audit_constants import (
    OVERLOAN_INDICATOR_CODES, STANDARD_LOAN_PAYMENT_CODES,
)
from suiteview.polview.models.cl_polrec.policy_translations import LOAN_TYPE_CODES

# ── Shared styling (same as policy_panel) ───────────────────────────────
_ROW_H = 19
_FONT_PX = 13
_MAX_VISIBLE = 22
_GAP_X = 8
_GAP_Y = 8
_CB_H = 20
_GRP_PAD = 10

_LIST_ENABLED_SS = f"""
    QListWidget {{
        font-size: {_FONT_PX}px;
        border: none; padding: 0px; outline: none;
        background: transparent; color: #1A1A1A;
    }}
    QListWidget::item {{
        padding: 0px 3px; margin: 0px;
        min-height: {_ROW_H}px; max-height: {_ROW_H}px;
    }}
    QListWidget::item:selected {{
        background-color: {BLUE_PRIMARY}; color: white;
    }}
    QListWidget::item:hover:!selected {{
        background-color: #D6E4F0;
    }}
"""
_LIST_DISABLED_SS = f"""
    QListWidget {{
        font-size: {_FONT_PX}px;
        border: none; padding: 0px; outline: none;
        background: transparent; color: {SILVER_MID};
    }}
    QListWidget::item {{
        padding: 0px 3px; margin: 0px;
        min-height: {_ROW_H}px; max-height: {_ROW_H}px;
    }}
"""

_CHECKBOX_SS = f"""
    QCheckBox {{
        spacing: 4px; font-size: 11px;
        color: {BLUE_DARK}; font-weight: bold;
    }}
    QCheckBox::indicator {{ width: 13px; height: 13px; }}
"""

_BOX_SS = f"""
    QGroupBox {{
        border: 2px solid {BLUE_PRIMARY};
        border-radius: 6px; margin: 0px; padding: 4px;
        background-color: #ffffff;
    }}
"""

_LABEL_SS = f"QLabel {{ font-size: 11px; font-weight: bold; color: {BLUE_DARK}; }}"
_INPUT_SS = f"QLineEdit {{ font-size: 12px; padding: 2px 4px; border: 1px solid {BLUE_PRIMARY}; border-radius: 3px; }}"


class LoanPanel(CriteriaPanel):
    """Loan-related criteria — coordinate-placed controls."""

    @staticmethod
    def _measure_width(items: Dict[str, str], fmt: str, extra: int = 28) -> int:
        tmp = QListWidget()
        tmp.setStyleSheet(f"font-size: {_FONT_PX}px;")
        fm = QFontMetrics(tmp.font())
        max_w = 0
        for code, label in items.items():
            text = f"{code}-{label}" if (fmt == "dash" and label) else code
            max_w = max(max_w, fm.horizontalAdvance(text))
        return max_w + extra

    def _make_control(
        self, parent, title, items, x, y, width=None, fmt="dash",
    ) -> Tuple[int, int, QCheckBox, QListWidget]:
        if width is None:
            width = self._measure_width(items, fmt)

        n_items = len(items)
        visible = min(n_items, _MAX_VISIBLE)
        list_h = visible * _ROW_H + 2

        cb = QCheckBox(title, parent)
        cb.setChecked(False)
        cb.setStyleSheet(_CHECKBOX_SS)
        cb.move(x, y)
        cb.adjustSize()

        grp = QGroupBox(parent)
        grp.setStyleSheet(_BOX_SS)
        grp_lay = QVBoxLayout(grp)
        grp_lay.setContentsMargins(3, 3, 3, 3)
        grp_lay.setSpacing(0)

        lw = QListWidget()
        lw.setSelectionMode(QAbstractItemView.SelectionMode.MultiSelection)
        lw.setSpacing(0)
        lw.setUniformItemSizes(True)
        lw.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        lw.setVerticalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAsNeeded
            if n_items > _MAX_VISIBLE
            else Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )
        lw.setStyleSheet(_LIST_DISABLED_SS)

        for code, label in items.items():
            text = f"{code}-{label}" if (fmt == "dash" and label) else code
            it = QListWidgetItem(text)
            it.setData(Qt.ItemDataRole.UserRole, code)
            lw.addItem(it)

        lw.setFixedHeight(list_h)
        lw.setFixedWidth(width)
        lw.setEnabled(False)
        grp_lay.addWidget(lw)

        grp_w = width + _GRP_PAD
        grp_h = list_h + _GRP_PAD
        grp.setFixedSize(grp_w, grp_h)
        grp.move(x, y + _CB_H + 2)

        cb.toggled.connect(lambda checked, w=lw: self._toggle_list(w, checked))

        total_w = max(cb.width(), grp_w)
        total_h = _CB_H + 2 + grp_h
        return total_w, total_h, cb, lw

    @staticmethod
    def _toggle_list(lw, checked):
        lw.setEnabled(checked)
        lw.setStyleSheet(_LIST_ENABLED_SS if checked else _LIST_DISABLED_SS)
        if not checked:
            lw.clearSelection()

    @staticmethod
    def _selected(lw) -> List[str]:
        return [it.data(Qt.ItemDataRole.UserRole) for it in lw.selectedItems()]

    # ── build UI ────────────────────────────────────────────────────────
    def _build_ui(self):
        self.canvas = QWidget()
        self.main_layout.addWidget(self.canvas)

        max_x = max_y = 0
        cx, cy = 0, 0
        row_h = 0

        # Row 0: list controls
        w, h, self.loantype_cb, self.loantype_list = self._make_control(
            self.canvas, "Loan Type (01)", LOAN_TYPE_CODES, cx, cy,
        )
        row_h = max(row_h, h); cx += w + _GAP_X

        w, h, self.overloan_cb, self.overloan_list = self._make_control(
            self.canvas, "Trad Overloan Ind (01)", OVERLOAN_INDICATOR_CODES, cx, cy,
        )
        row_h = max(row_h, h); cx += w + _GAP_X

        w, h, self.stdloan_cb, self.stdloan_list = self._make_control(
            self.canvas, "Standard Loan Payment (20)",
            STANDARD_LOAN_PAYMENT_CODES, cx, cy,
        )
        row_h = max(row_h, h); cx += w
        max_x = max(max_x, cx)
        max_y = max(max_y, cy + row_h)

        # Row 1: booleans + range fields
        cx = 0
        cy = max_y + _GAP_Y
        row_start_y = cy

        # Booleans
        self.has_loan_cb = QCheckBox("Has Loan (77)", self.canvas)
        self.has_loan_cb.setStyleSheet(_CHECKBOX_SS)
        self.has_loan_cb.move(cx, cy)
        self.has_loan_cb.adjustSize()
        cy += _CB_H + 4

        self.has_preferred_cb = QCheckBox("Has Preferred Loan", self.canvas)
        self.has_preferred_cb.setStyleSheet(_CHECKBOX_SS)
        self.has_preferred_cb.move(cx, cy)
        self.has_preferred_cb.adjustSize()

        # Range fields to the right of booleans
        range_x = 180
        range_y = row_start_y

        def _add_range(label_text, ry):
            lbl = QLabel(label_text, self.canvas)
            lbl.setStyleSheet(_LABEL_SS)
            lbl.move(range_x, ry)
            lbl.adjustSize()

            lo = QLineEdit(self.canvas)
            lo.setFixedWidth(90)
            lo.setStyleSheet(_INPUT_SS)
            lo.move(range_x + lbl.width() + 6, ry - 2)
            lo.setFixedHeight(22)

            to_lbl = QLabel("to", self.canvas)
            to_lbl.setStyleSheet("font-size: 11px;")
            to_lbl.move(range_x + lbl.width() + 100, ry)
            to_lbl.adjustSize()

            hi = QLineEdit(self.canvas)
            hi.setFixedWidth(90)
            hi.setStyleSheet(_INPUT_SS)
            hi.move(range_x + lbl.width() + 120, ry - 2)
            hi.setFixedHeight(22)

            return lo, hi

        self.loan_princ_lo, self.loan_princ_hi = _add_range(
            "Total Loan Principle (77)", range_y,
        )
        range_y += 28
        self.loan_int_lo, self.loan_int_hi = _add_range(
            "Total Accrued Loan Int (77)", range_y,
        )
        range_y += 28

        # Loan charge rate — single input
        rate_lbl = QLabel("Loan Charge Rate (01):", self.canvas)
        rate_lbl.setStyleSheet(_LABEL_SS)
        rate_lbl.move(range_x, range_y)
        rate_lbl.adjustSize()
        self.loan_charge_rate = QLineEdit(self.canvas)
        self.loan_charge_rate.setFixedWidth(90)
        self.loan_charge_rate.setFixedHeight(22)
        self.loan_charge_rate.setStyleSheet(_INPUT_SS)
        self.loan_charge_rate.move(range_x + rate_lbl.width() + 6, range_y - 2)

        max_y = max(max_y, range_y + 26)
        max_x = max(max_x, range_x + rate_lbl.width() + 100)

        self.canvas.setMinimumSize(max_x, max_y)

    # ── write / reset ───────────────────────────────────────────────────
    def write_to_criteria(self, criteria):
        criteria.loan_types = (
            self._selected(self.loantype_list) if self.loantype_cb.isChecked() else []
        )
        criteria.overloan_indicators = (
            self._selected(self.overloan_list) if self.overloan_cb.isChecked() else []
        )
        criteria.slr_billing_forms = (
            self._selected(self.stdloan_list) if self.stdloan_cb.isChecked() else []
        )
        criteria.has_loan = self.has_loan_cb.isChecked()
        criteria.has_preferred_loan = self.has_preferred_cb.isChecked()
        criteria.loan_principal_greater_than = self.loan_princ_lo.text().strip()
        criteria.loan_principal_less_than = self.loan_princ_hi.text().strip()
        criteria.loan_accrued_int_greater_than = self.loan_int_lo.text().strip()
        criteria.loan_accrued_int_less_than = self.loan_int_hi.text().strip()
        criteria.loan_charge_rate = self.loan_charge_rate.text().strip()

    def reset(self, criteria):
        super().reset(criteria)
        for cb in [self.loantype_cb, self.overloan_cb, self.stdloan_cb,
                    self.has_loan_cb, self.has_preferred_cb]:
            cb.setChecked(False)
        for lw in [self.loantype_list, self.overloan_list, self.stdloan_list]:
            lw.clearSelection()
        for le in [self.loan_princ_lo, self.loan_princ_hi,
                    self.loan_int_lo, self.loan_int_hi,
                    self.loan_charge_rate]:
            le.clear()
