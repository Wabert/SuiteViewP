"""
DI tab — faithful replica of VBA frmAudit DI tab.

Layout:
  Benefit Period Code (02) group box:
    Accident checkbox + listbox   |   Sickness checkbox + listbox
  Elimination Period Code (02) group box:
    Accident checkbox + listbox   |   Sickness checkbox + listbox
"""
from __future__ import annotations

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGroupBox,
    QCheckBox, QListWidget,
)
from PyQt6.QtGui import QFont

from ..constants import (
    BENEFIT_PERIOD_ACCIDENT_ITEMS, BENEFIT_PERIOD_SICKNESS_ITEMS,
    ELIM_PERIOD_ACCIDENT_ITEMS, ELIM_PERIOD_SICKNESS_ITEMS,
)
from ._styles import make_checkbox as _make_checkbox, make_listbox as _make_listbox, connect_checkbox_listbox as _connect_checkbox_listbox

# ── Compact sizing helpers ──────────────────────────────────────────────
_FONT = QFont("Segoe UI", 9)
_ROW_H = 16
_V_SPACING = 2

_GRP_STYLE = (
    "QGroupBox { font-weight: bold; color: #1E5BA8; border: 1px solid #6A9BD1;"
    " border-radius: 3px; margin-top: 8px; padding-top: 10px; }"
    "QGroupBox::title { subcontrol-origin: margin; left: 8px; padding: 0 4px; }"
)


class DiTab(QWidget):
    """DI (Disability Income) tab — benefit/elimination period criteria."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._build_ui()

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(6, 6, 6, 4)
        root.setSpacing(6)

        # ────────────────────────────────────────────────────────────
        # Benefit Period Code (02)
        # ────────────────────────────────────────────────────────────
        grp_bp = QGroupBox("Benefit Period Code (02)")
        grp_bp.setStyleSheet(_GRP_STYLE)
        bp_lay = QHBoxLayout(grp_bp)
        bp_lay.setContentsMargins(6, 6, 6, 4)
        bp_lay.setSpacing(12)

        # Accident column
        bp_acc_col = QVBoxLayout()
        bp_acc_col.setSpacing(_V_SPACING)
        self.chk_bp_accident = _make_checkbox("Accident")
        bp_acc_col.addWidget(self.chk_bp_accident)
        self.list_bp_accident = _make_listbox(
            BENEFIT_PERIOD_ACCIDENT_ITEMS, height_rows=10, enabled=False)
        self.list_bp_accident.setFixedWidth(120)
        bp_acc_col.addWidget(self.list_bp_accident)
        _connect_checkbox_listbox(self.chk_bp_accident, self.list_bp_accident)
        bp_lay.addLayout(bp_acc_col)

        # Sickness column
        bp_sck_col = QVBoxLayout()
        bp_sck_col.setSpacing(_V_SPACING)
        self.chk_bp_sickness = _make_checkbox("Sickness")
        bp_sck_col.addWidget(self.chk_bp_sickness)
        self.list_bp_sickness = _make_listbox(
            BENEFIT_PERIOD_SICKNESS_ITEMS, height_rows=10, enabled=False)
        self.list_bp_sickness.setFixedWidth(120)
        bp_sck_col.addWidget(self.list_bp_sickness)
        _connect_checkbox_listbox(self.chk_bp_sickness, self.list_bp_sickness)
        bp_lay.addLayout(bp_sck_col)

        bp_lay.addStretch()
        root.addWidget(grp_bp)

        # ────────────────────────────────────────────────────────────
        # Elimination Period Code (02)
        # ────────────────────────────────────────────────────────────
        grp_ep = QGroupBox("Elimination Period Code (02)")
        grp_ep.setStyleSheet(_GRP_STYLE)
        ep_lay = QHBoxLayout(grp_ep)
        ep_lay.setContentsMargins(6, 6, 6, 4)
        ep_lay.setSpacing(12)

        # Accident column
        ep_acc_col = QVBoxLayout()
        ep_acc_col.setSpacing(_V_SPACING)
        self.chk_ep_accident = _make_checkbox("Accident")
        ep_acc_col.addWidget(self.chk_ep_accident)
        self.list_ep_accident = _make_listbox(
            ELIM_PERIOD_ACCIDENT_ITEMS, height_rows=10, enabled=False)
        self.list_ep_accident.setFixedWidth(120)
        ep_acc_col.addWidget(self.list_ep_accident)
        _connect_checkbox_listbox(self.chk_ep_accident, self.list_ep_accident)
        ep_lay.addLayout(ep_acc_col)

        # Sickness column
        ep_sck_col = QVBoxLayout()
        ep_sck_col.setSpacing(_V_SPACING)
        self.chk_ep_sickness = _make_checkbox("Sickness")
        ep_sck_col.addWidget(self.chk_ep_sickness)
        self.list_ep_sickness = _make_listbox(
            ELIM_PERIOD_SICKNESS_ITEMS, height_rows=11, enabled=False)
        self.list_ep_sickness.setFixedWidth(120)
        ep_sck_col.addWidget(self.list_ep_sickness)
        _connect_checkbox_listbox(self.chk_ep_sickness, self.list_ep_sickness)
        ep_lay.addLayout(ep_sck_col)

        ep_lay.addStretch()
        root.addWidget(grp_ep)

        root.addStretch()

    # ── Profile save/load ────────────────────────────────────────────
    def get_state(self) -> dict:
        from ..profile_manager import (
            get_checkbox_checked as _c, get_listbox_selected as _sel,
        )
        return {
            "chk_bp_accident": _c(self.chk_bp_accident),
            "list_bp_accident": _sel(self.list_bp_accident),
            "chk_bp_sickness": _c(self.chk_bp_sickness),
            "list_bp_sickness": _sel(self.list_bp_sickness),
            "chk_ep_accident": _c(self.chk_ep_accident),
            "list_ep_accident": _sel(self.list_ep_accident),
            "chk_ep_sickness": _c(self.chk_ep_sickness),
            "list_ep_sickness": _sel(self.list_ep_sickness),
        }

    def set_state(self, state: dict):
        from ..profile_manager import (
            set_checkbox_checked as _c, set_listbox_selected as _sel,
        )
        _c(self.chk_bp_accident, state.get("chk_bp_accident", False))
        _sel(self.list_bp_accident, state.get("list_bp_accident", []))
        _c(self.chk_bp_sickness, state.get("chk_bp_sickness", False))
        _sel(self.list_bp_sickness, state.get("list_bp_sickness", []))
        _c(self.chk_ep_accident, state.get("chk_ep_accident", False))
        _sel(self.list_ep_accident, state.get("list_ep_accident", []))
        _c(self.chk_ep_sickness, state.get("chk_ep_sickness", False))
        _sel(self.list_ep_sickness, state.get("list_ep_sickness", []))
