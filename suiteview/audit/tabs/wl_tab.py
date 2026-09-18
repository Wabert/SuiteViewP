"""Compact Whole Life dividend, nonforfeiture and base participation criteria."""
from __future__ import annotations

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QFont
from PyQt6.QtWidgets import (
    QCheckBox, QHBoxLayout, QListWidget, QPushButton, QSizePolicy, QVBoxLayout, QWidget,
)

from ..constants import (
    DIVIDEND_OPTION_ITEMS, NFO_CODE_ITEMS, PARTICIPATION_CODES,
    PARTICIPATION_TYPE_DESCRIPTIONS,
)
from ._styles import make_checkbox, make_listbox, connect_checkbox_listbox

_FONT = QFont("Segoe UI", 9)


def _selector(title: str, items: list[str], button: QPushButton | None = None
              ) -> tuple[QWidget, QCheckBox, QListWidget]:
    panel = QWidget()
    panel.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
    layout = QVBoxLayout(panel)
    layout.setContentsMargins(0, 0, 0, 0)
    layout.setSpacing(2)
    checkbox = make_checkbox(title)
    checkbox.setFixedHeight(20)
    header = QHBoxLayout()
    header.setSpacing(4)
    header.addWidget(checkbox)
    if button is not None:
        header.addWidget(button)
    header.addStretch()
    layout.addLayout(header)
    listbox = make_listbox(items, height_rows=len(items), enabled=False)
    connect_checkbox_listbox(checkbox, listbox)
    layout.addWidget(listbox)
    content_width = max(listbox.fontMetrics().horizontalAdvance(text) for text in items) + 16
    panel.setFixedWidth(max(content_width, header.sizeHint().width()))
    return panel, checkbox, listbox


class WlTab(QWidget):
    """WL criteria use base coverage participation, never the rider code mapping."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._build_ui()

    def _build_ui(self):
        root = QHBoxLayout(self)
        root.setContentsMargins(6, 6, 6, 4)
        root.setSpacing(12)
        left = QVBoxLayout()
        left.setSpacing(8)
        primary, self.chk_pri_div, self.list_pri_div = _selector(
            "Primary Dividend Option (01)", DIVIDEND_OPTION_ITEMS)
        left.addWidget(primary)
        nfo, self.chk_nfo, self.list_nfo = _selector("NFO code (01)", NFO_CODE_ITEMS)
        left.addWidget(nfo)
        left.addStretch()
        root.addLayout(left)

        middle = QVBoxLayout()
        middle.setSpacing(8)
        secondary, self.chk_sec_div, self.list_sec_div = _selector(
            "Secondary Dividend Option (01)", DIVIDEND_OPTION_ITEMS)
        dividend_width = max(primary.width(), secondary.width())
        for panel in (primary, secondary, nfo):
            panel.setFixedWidth(dividend_width)
        middle.addWidget(secondary)
        self.chk_cv_rate = make_checkbox("Current CV rate > 0 on base cov (02)")
        middle.addWidget(self.chk_cv_rate)
        middle.addStretch()
        root.addLayout(middle)

        self.btn_par = QPushButton("Par")
        self.btn_par.setFont(_FONT)
        self.btn_par.setFixedSize(36, 20)
        self.btn_par.setStyleSheet("padding:0 2px;")
        self.btn_par.setToolTip("Select A-H only; excludes code 9 (dividends paid up).")
        self.btn_par.clicked.connect(self._select_par)
        participation, self.chk_participation_type, self.list_participation_type = _selector(
            "Participation Type (02)",
            [f"{code or 'Blank'} - {description}"
             for code, description in PARTICIPATION_TYPE_DESCRIPTIONS.items()],
            self.btn_par,
        )
        for row, code in enumerate(PARTICIPATION_TYPE_DESCRIPTIONS):
            self.list_participation_type.item(row).setData(Qt.ItemDataRole.UserRole, code)
        tip = (
            "Base coverage (phase 1) DIV_PTP_TYP_CD. Select individual codes, "
            "or Par for A-H. Blank is a stored blank, not SQL NULL. "
            "Rider participation uses different codes. Combines with Policy (2) "
            "participation criteria using AND. Check without selecting to display only."
        )
        self.chk_participation_type.setToolTip(tip)
        self.list_participation_type.setToolTip(tip)
        root.addWidget(participation, alignment=Qt.AlignmentFlag.AlignTop)
        root.addStretch()

    def selected_participation_codes(self) -> list[str]:
        return [
            item.data(Qt.ItemDataRole.UserRole)
            for item in self.list_participation_type.selectedItems()
        ]

    def _select_par(self):
        self.chk_participation_type.setChecked(True)
        for row in range(self.list_participation_type.count()):
            item = self.list_participation_type.item(row)
            item.setSelected(item.data(Qt.ItemDataRole.UserRole) in PARTICIPATION_CODES["Participating"])

    def get_state(self) -> dict:
        from ..profile_manager import get_checkbox_checked as _c, get_listbox_selected as _sel
        return {
            "grp_pri_checked": _c(self.chk_pri_div),
            "list_pri_div": _sel(self.list_pri_div),
            "grp_sec_checked": _c(self.chk_sec_div),
            "list_sec_div": _sel(self.list_sec_div),
            "grp_nfo_checked": _c(self.chk_nfo),
            "list_nfo": _sel(self.list_nfo),
            "chk_cv_rate": _c(self.chk_cv_rate),
            "chk_participation_type": _c(self.chk_participation_type),
            "list_participation_type": _sel(self.list_participation_type),
        }

    def set_state(self, state: dict):
        from ..profile_manager import set_checkbox_checked as _c, set_listbox_selected as _sel
        _c(self.chk_pri_div, state.get("grp_pri_checked", False))
        _sel(self.list_pri_div, state.get("list_pri_div", []))
        _c(self.chk_sec_div, state.get("grp_sec_checked", False))
        _sel(self.list_sec_div, state.get("list_sec_div", []))
        _c(self.chk_nfo, state.get("grp_nfo_checked", False))
        _sel(self.list_nfo, state.get("list_nfo", []))
        _c(self.chk_cv_rate, state.get("chk_cv_rate", False))
        _c(self.chk_participation_type, state.get("chk_participation_type", False))
        _sel(self.list_participation_type, state.get("list_participation_type", []))
