"""
WL tab — faithful replica of VBA frmAudit WL tab.

Layout:
  TOP ROW:
    Primary Dividend Option (01) — checkable group box + listbox
    Secondary Dividend Option (01) — checkable group box + listbox
  BOTTOM ROW:
    NFO code (01) — checkable group box + listbox
    Current CV rate > 0 on base cov (02) — standalone checkbox
"""
from __future__ import annotations

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGroupBox,
    QLabel, QCheckBox, QListWidget,
)
from PyQt6.QtGui import QFont

from ..constants import DIVIDEND_OPTION_ITEMS, NFO_CODE_ITEMS
from ._styles import make_checkbox as _make_checkbox, make_listbox as _make_listbox

# ── Compact sizing helpers ──────────────────────────────────────────────
_FONT = QFont("Segoe UI", 9)
_ROW_H = 16
_V_SPACING = 2

_GRP_STYLE = (
    "QGroupBox { font-weight: bold; color: #1E5BA8; border: 1px solid #6A9BD1;"
    " border-radius: 3px; margin-top: 8px; padding-top: 10px; }"
    "QGroupBox::title { subcontrol-origin: margin; left: 8px; padding: 0 4px; }"
)


class WlTab(QWidget):
    """WL (Whole Life) tab — dividend and NFO criteria."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._build_ui()

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(6, 6, 6, 4)
        root.setSpacing(6)

        # ────────────────────────────────────────────────────────────
        # TOP ROW — Primary + Secondary Dividend Option
        # ────────────────────────────────────────────────────────────
        top_row = QHBoxLayout()
        top_row.setSpacing(12)

        # Primary Dividend Option (01)
        grp_pri = QGroupBox("Primary Dividend Option (01)")
        grp_pri.setStyleSheet(_GRP_STYLE)
        grp_pri.setCheckable(True)
        grp_pri.setChecked(False)
        pri_lay = QVBoxLayout(grp_pri)
        pri_lay.setContentsMargins(6, 6, 6, 4)
        pri_lay.setSpacing(_V_SPACING)
        self.list_pri_div = _make_listbox(
            DIVIDEND_OPTION_ITEMS, height_rows=12, enabled=False)
        pri_lay.addWidget(self.list_pri_div)
        grp_pri.toggled.connect(
            lambda on: self.list_pri_div.setEnabled(on) or
            (not on and self.list_pri_div.clearSelection()))
        top_row.addWidget(grp_pri)

        # Secondary Dividend Option (01)
        grp_sec = QGroupBox("Secondary Dividend Option (01)")
        grp_sec.setStyleSheet(_GRP_STYLE)
        grp_sec.setCheckable(True)
        grp_sec.setChecked(False)
        sec_lay = QVBoxLayout(grp_sec)
        sec_lay.setContentsMargins(6, 6, 6, 4)
        sec_lay.setSpacing(_V_SPACING)
        self.list_sec_div = _make_listbox(
            DIVIDEND_OPTION_ITEMS, height_rows=12, enabled=False)
        sec_lay.addWidget(self.list_sec_div)
        grp_sec.toggled.connect(
            lambda on: self.list_sec_div.setEnabled(on) or
            (not on and self.list_sec_div.clearSelection()))
        top_row.addWidget(grp_sec)

        top_row.addStretch()
        root.addLayout(top_row)

        # ────────────────────────────────────────────────────────────
        # BOTTOM ROW — NFO code + CV rate checkbox
        # ────────────────────────────────────────────────────────────
        bot_row = QHBoxLayout()
        bot_row.setSpacing(12)

        # NFO code (01)
        grp_nfo = QGroupBox("NFO code (01)")
        grp_nfo.setStyleSheet(_GRP_STYLE)
        grp_nfo.setCheckable(True)
        grp_nfo.setChecked(False)
        nfo_lay = QVBoxLayout(grp_nfo)
        nfo_lay.setContentsMargins(6, 6, 6, 4)
        nfo_lay.setSpacing(_V_SPACING)
        self.list_nfo = _make_listbox(
            NFO_CODE_ITEMS, height_rows=8, enabled=False)
        nfo_lay.addWidget(self.list_nfo)
        grp_nfo.toggled.connect(
            lambda on: self.list_nfo.setEnabled(on) or
            (not on and self.list_nfo.clearSelection()))
        bot_row.addWidget(grp_nfo)

        # Standalone checkbox
        self.chk_cv_rate = _make_checkbox(
            "Current CV rate > 0 on base cov (02)")
        bot_row.addWidget(self.chk_cv_rate, alignment=Qt.AlignmentFlag.AlignTop)

        bot_row.addStretch()
        root.addLayout(bot_row)

        root.addStretch()

    # ── Profile save/load ────────────────────────────────────────────
    def get_state(self) -> dict:
        from ..profile_manager import (
            get_checkbox_checked as _c, get_listbox_selected as _sel,
            get_groupbox_checked as _gc,
        )
        # Find the parent QGroupBox widgets for primary/secondary/nfo
        grp_pri = self.list_pri_div.parent()
        grp_sec = self.list_sec_div.parent()
        grp_nfo = self.list_nfo.parent()
        return {
            "grp_pri_checked": _gc(grp_pri),
            "list_pri_div": _sel(self.list_pri_div),
            "grp_sec_checked": _gc(grp_sec),
            "list_sec_div": _sel(self.list_sec_div),
            "grp_nfo_checked": _gc(grp_nfo),
            "list_nfo": _sel(self.list_nfo),
            "chk_cv_rate": _c(self.chk_cv_rate),
        }

    def set_state(self, state: dict):
        from ..profile_manager import (
            set_checkbox_checked as _c, set_listbox_selected as _sel,
            set_groupbox_checked as _gc,
        )
        grp_pri = self.list_pri_div.parent()
        grp_sec = self.list_sec_div.parent()
        grp_nfo = self.list_nfo.parent()
        _gc(grp_pri, state.get("grp_pri_checked", False))
        _sel(self.list_pri_div, state.get("list_pri_div", []))
        _gc(grp_sec, state.get("grp_sec_checked", False))
        _sel(self.list_sec_div, state.get("list_sec_div", []))
        _gc(grp_nfo, state.get("grp_nfo_checked", False))
        _sel(self.list_nfo, state.get("list_nfo", []))
        _c(self.chk_cv_rate, state.get("chk_cv_rate", False))
