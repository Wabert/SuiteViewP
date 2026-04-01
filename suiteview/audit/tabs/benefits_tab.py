"""
Benefits tab — faithful replica of VBA frmAudit Benefits tab.

Layout:
  3 rows (row 1 plain, rows 2-3 prefixed "and"):
    Benefit combo | Sub Type text | Post Issue checkbox |
    Cease Dt Range (lo/to) | Cease Date Status combo
"""
from __future__ import annotations

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGridLayout, QGroupBox,
    QLabel, QLineEdit, QCheckBox, QComboBox,
)
from PyQt6.QtGui import QFont

from ..constants import BENEFIT_TYPE_ITEMS, BENEFIT_CEASE_STATUS_ITEMS
from ._styles import make_combo as _make_combo, make_checkbox as _make_checkbox

# ── Compact sizing helpers ──────────────────────────────────────────────
_FONT = QFont("Segoe UI", 9)
_CTRL_H = 22
_V_SPACING = 2
_H_SPACING = 6
_RANGE_W = 70

_GRP_STYLE = (
    "QGroupBox { font-weight: bold; color: #1E5BA8; border: 1px solid #6A9BD1;"
    " border-radius: 3px; margin-top: 8px; padding-top: 10px; }"
    "QGroupBox::title { subcontrol-origin: margin; left: 8px; padding: 0 4px; }"
)


class BenefitsTab(QWidget):
    """Benefits tab — benefit type / cease date criteria (3 rows)."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._build_ui()

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(6, 6, 6, 4)
        root.setSpacing(6)

        grid = QGridLayout()
        grid.setHorizontalSpacing(_H_SPACING)
        grid.setVerticalSpacing(_V_SPACING)
        grid.setSizeConstraint(QGridLayout.SizeConstraint.SetFixedSize)

        # ── Column headers ──────────────────────────────────────────
        headers = [
            (0, ""),           # "and" prefix column
            (1, "Benefit"),
            (2, "Sub Type"),
            (3, "Post\nIssue"),
            (4, "Cease Dt Range"),
            (5, ""),           # "to" label
            (6, ""),           # hi field
            (7, "Cease  Date Status"),
        ]
        for col, text in headers:
            lbl = QLabel(text)
            lbl.setFont(QFont("Segoe UI", 9, QFont.Weight.Bold))
            if col == 3:
                lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            grid.addWidget(lbl, 0, col)

        # ── Build 3 data rows ──────────────────────────────────────
        self.benefit_combos: list[QComboBox] = []
        self.subtype_edits: list[QLineEdit] = []
        self.post_issue_chks: list[QCheckBox] = []
        self.cease_lo_edits: list[QLineEdit] = []
        self.cease_hi_edits: list[QLineEdit] = []
        self.cease_status_combos: list[QComboBox] = []

        for i in range(3):
            row = i + 1  # grid row (0 is headers)

            # "and" prefix for rows 2-3
            if i > 0:
                lbl_and = QLabel("and")
                lbl_and.setFont(_FONT)
                grid.addWidget(lbl_and, row, 0, Qt.AlignmentFlag.AlignRight)

            # Benefit combo
            cmb_ben = _make_combo(BENEFIT_TYPE_ITEMS, width=120)
            grid.addWidget(cmb_ben, row, 1)
            self.benefit_combos.append(cmb_ben)

            # Sub Type text
            txt_sub = QLineEdit()
            txt_sub.setFont(_FONT)
            txt_sub.setFixedSize(60, _CTRL_H)
            grid.addWidget(txt_sub, row, 2)
            self.subtype_edits.append(txt_sub)

            # Post Issue checkbox
            chk_pi = _make_checkbox("")
            grid.addWidget(chk_pi, row, 3, Qt.AlignmentFlag.AlignCenter)
            self.post_issue_chks.append(chk_pi)

            # Cease Dt Range — lo
            txt_lo = QLineEdit()
            txt_lo.setFont(_FONT)
            txt_lo.setFixedSize(_RANGE_W, _CTRL_H)
            grid.addWidget(txt_lo, row, 4)
            self.cease_lo_edits.append(txt_lo)

            # "to"
            if i == 0:
                lbl_to = QLabel("to")
                lbl_to.setFont(_FONT)
                grid.addWidget(lbl_to, row, 5, Qt.AlignmentFlag.AlignCenter)

            # Cease Dt Range — hi
            txt_hi = QLineEdit()
            txt_hi.setFont(_FONT)
            txt_hi.setFixedSize(_RANGE_W, _CTRL_H)
            grid.addWidget(txt_hi, row, 6)
            self.cease_hi_edits.append(txt_hi)

            # Cease Date Status combo
            cmb_status = _make_combo(BENEFIT_CEASE_STATUS_ITEMS, width=220)
            grid.addWidget(cmb_status, row, 7)
            self.cease_status_combos.append(cmb_status)

        grid_row = QHBoxLayout()
        grid_row.addLayout(grid)
        grid_row.addStretch()
        root.addLayout(grid_row)
        root.addStretch()

    # ── Profile save/load ────────────────────────────────────────────
    def get_state(self) -> dict:
        from ..profile_manager import (
            get_lineedit_text as _t, get_checkbox_checked as _c,
            get_combo_text as _cmb,
        )
        rows = []
        for i in range(3):
            rows.append({
                "benefit": _cmb(self.benefit_combos[i]),
                "subtype": _t(self.subtype_edits[i]),
                "post_issue": _c(self.post_issue_chks[i]),
                "cease_lo": _t(self.cease_lo_edits[i]),
                "cease_hi": _t(self.cease_hi_edits[i]),
                "cease_status": _cmb(self.cease_status_combos[i]),
            })
        return {"rows": rows}

    def set_state(self, state: dict):
        from ..profile_manager import (
            set_lineedit_text as _t, set_checkbox_checked as _c,
            set_combo_text as _cmb,
        )
        rows = state.get("rows", [])
        for i in range(3):
            row = rows[i] if i < len(rows) else {}
            _cmb(self.benefit_combos[i], row.get("benefit", ""))
            _t(self.subtype_edits[i], row.get("subtype", ""))
            _c(self.post_issue_chks[i], row.get("post_issue", False))
            _t(self.cease_lo_edits[i], row.get("cease_lo", ""))
            _t(self.cease_hi_edits[i], row.get("cease_hi", ""))
            _cmb(self.cease_status_combos[i], row.get("cease_status", ""))
