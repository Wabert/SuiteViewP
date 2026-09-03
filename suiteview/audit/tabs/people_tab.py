"""People tab — person-level criteria for the Cyberlife query builder.

Filters the policies returned by the audit down to those whose
``VH_POL_HAS_LOC_CLT`` person rows match the entered name(s), and adds the
matched person's name columns to the results.

Lives on its own tab (rather than tucked into the bottom of Policy (2)) because
name lookup is how most users start a search, and it is where further
person-level criteria will be added.
"""
from __future__ import annotations

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGridLayout, QLabel, QLineEdit,
)
from PyQt6.QtGui import QFont

from ._styles import make_combo as _make_combo

# ── Compact sizing helpers (same as the other criteria tabs) ────────────
_FONT = QFont("Segoe UI", 9)
_CTRL_H = 22
_V_SPACING = 2
_H_SPACING = 4
_NAME_LABEL_W = 70

# Match-type options for the Person Info name filters.
NAME_MATCH_ITEMS = ["Exact match", "Contains", "Begins with", "Ends with"]


class PeopleTab(QWidget):
    """Person-level criteria (VH_POL_HAS_LOC_CLT)."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._build_ui()

    def _add_name_row(self, layout: QGridLayout, row: int, label_text: str):
        """Add a 'label | match-type combo | text' row and return (combo, line-edit)."""
        lbl = QLabel(label_text)
        lbl.setFont(_FONT)
        lbl.setFixedWidth(_NAME_LABEL_W)
        lbl.setFixedHeight(_CTRL_H)

        cmb = _make_combo(NAME_MATCH_ITEMS, width=100)

        txt = QLineEdit()
        txt.setFont(_FONT)
        txt.setFixedHeight(_CTRL_H)
        txt.setMinimumWidth(110)

        layout.addWidget(lbl, row, 0)
        layout.addWidget(cmb, row, 1)
        layout.addWidget(txt, row, 2)
        return cmb, txt

    def _build_ui(self):
        root = QHBoxLayout(self)
        root.setContentsMargins(4, 4, 4, 4)
        root.setSpacing(8)

        col1 = QVBoxLayout()
        col1.setSpacing(_V_SPACING)

        # ── Person Info (VH_POL_HAS_LOC_CLT) ───────────────────────
        lbl_person = QLabel("Person Info")
        lbl_person.setFont(QFont("Segoe UI", 9, QFont.Weight.Bold))
        col1.addWidget(lbl_person)

        person_grid = QGridLayout()
        person_grid.setSpacing(_V_SPACING)
        person_grid.setContentsMargins(0, 0, 0, 0)
        person_grid.setHorizontalSpacing(_H_SPACING)
        self.cmb_first_name_match, self.txt_first_name = self._add_name_row(
            person_grid, 0, "First Name")
        self.cmb_last_name_match, self.txt_last_name = self._add_name_row(
            person_grid, 1, "Last Name")
        person_grid.setColumnStretch(3, 1)
        col1.addLayout(person_grid)

        lbl_hint = QLabel(
            "Name matching ignores case and surrounding spaces.  Matching "
            "policies also return the person's name columns.")
        lbl_hint.setFont(QFont("Segoe UI", 8))
        lbl_hint.setStyleSheet("color: #555;")
        lbl_hint.setWordWrap(True)
        lbl_hint.setMaximumWidth(360)
        col1.addSpacing(4)
        col1.addWidget(lbl_hint)

        col1.addStretch()
        root.addLayout(col1)
        root.addStretch()

    # ── Profile save/load ────────────────────────────────────────────
    def get_state(self) -> dict:
        from ..profile_manager import (
            get_lineedit_text as _t, get_combo_text as _cb,
        )
        return {
            "cmb_first_name_match": _cb(self.cmb_first_name_match),
            "txt_first_name": _t(self.txt_first_name),
            "cmb_last_name_match": _cb(self.cmb_last_name_match),
            "txt_last_name": _t(self.txt_last_name),
        }

    def set_state(self, state: dict):
        from ..profile_manager import (
            set_lineedit_text as _t, set_combo_text as _cb,
        )
        _cb(self.cmb_first_name_match,
            state.get("cmb_first_name_match", NAME_MATCH_ITEMS[0]))
        _t(self.txt_first_name, state.get("txt_first_name", ""))
        _cb(self.cmb_last_name_match,
            state.get("cmb_last_name_match", NAME_MATCH_ITEMS[0]))
        _t(self.txt_last_name, state.get("txt_last_name", ""))
