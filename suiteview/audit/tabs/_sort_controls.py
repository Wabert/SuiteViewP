"""Reusable ASC/DESC + sort-order controls for Display-tab field rows.

Each display field row (Visual Query ``SelectFieldRow`` and DataForge
``ForgeDisplayFieldRow``) embeds a :class:`SortControl`: a direction toggle
button that cycles None -> ASC -> DESC and an integer spinbox that holds the
sort priority (1 = sorted first).

The module-level helpers manage priority numbers *across* a tab's rows so the
integers always stay contiguous (1..k) and editing one number cleanly inserts
the row at that position, cascading the others — mirroring how a user expects
"set this column to 2" to bump the current 2,3,4 to 3,4,5.

Any object passed to the helpers must expose a ``sort_ctrl`` attribute holding
a :class:`SortControl`.
"""
from __future__ import annotations

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QFont, QIntValidator
from PyQt6.QtWidgets import QWidget, QHBoxLayout, QPushButton, QLineEdit

# Direction cycle order for the toggle button.
_DIRECTIONS = ["", "ASC", "DESC"]
_DIR_LABELS = {"": "Sort", "ASC": "ASC \u25B2", "DESC": "DESC \u25BC"}

_BTN_STYLE = (
    "QPushButton { font-size: 7pt; padding: 0px 2px;"
    " border: 1px solid #1E5BA8; border-radius: 2px;"
    " background-color: #F0F0F0; color: #888;"
    " min-width: 46px; max-width: 52px; }"
    "QPushButton:hover { background-color: #E0E8F4; }"
)
_BTN_STYLE_ACTIVE = (
    "QPushButton { font-size: 7pt; padding: 0px 2px; font-weight: bold;"
    " border: 1px solid #1E5BA8; border-radius: 2px;"
    " background-color: #1E5BA8; color: white;"
    " min-width: 46px; max-width: 52px; }"
    "QPushButton:hover { background-color: #17457F; }"
)
_ORDER_STYLE = (
    "QLineEdit { font-size: 7pt; border: 1px solid #1E5BA8;"
    " border-radius: 2px; background-color: white; padding: 0px 2px; }"
    "QLineEdit:disabled { background-color: #ECECEC; color: #BBB;"
    " border-color: #C0C0C0; }"
)


class SortControl(QWidget):
    """Direction toggle (None/ASC/DESC) + sort-order integer input.

    Signals:
        dir_changed():       user cycled the direction button.
        order_edited(int):   user changed the order spinbox value.
    """
    dir_changed = pyqtSignal()
    order_edited = pyqtSignal(int)

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self._dir_idx = 0
        self._suppress = False

        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(3)

        self.btn_dir = QPushButton(_DIR_LABELS[""])
        self.btn_dir.setFont(QFont("Segoe UI", 7))
        self.btn_dir.setFixedHeight(18)
        self.btn_dir.setToolTip(
            "Sort direction \u2014 click to cycle None \u2192 ASC \u2192 DESC")
        self.btn_dir.setStyleSheet(_BTN_STYLE)
        self.btn_dir.clicked.connect(self._cycle)
        lay.addWidget(self.btn_dir)

        self.order_edit = QLineEdit()
        self.order_edit.setValidator(QIntValidator(0, 99, self))
        self.order_edit.setFixedSize(30, 18)
        self.order_edit.setFont(QFont("Segoe UI", 7))
        self.order_edit.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.order_edit.setStyleSheet(_ORDER_STYLE)
        self.order_edit.setToolTip("Sort priority (1 = sorted first)")
        self.order_edit.setEnabled(False)
        self.order_edit.editingFinished.connect(self._on_order_changed)
        lay.addWidget(self.order_edit)

    # ── State accessors ──────────────────────────────────────────────
    @property
    def direction(self) -> str:
        """Current sort direction: "", "ASC" or "DESC"."""
        return _DIRECTIONS[self._dir_idx]

    @property
    def order(self) -> int:
        """Current sort priority (0 when unsorted)."""
        text = self.order_edit.text().strip()
        return int(text) if text.isdigit() else 0

    def set_order(self, value: int):
        """Set the priority field without emitting ``order_edited``."""
        self._suppress = True
        value = max(0, int(value or 0))
        self.order_edit.setText(str(value) if value else "")
        self._suppress = False

    def set_direction(self, direction: str):
        """Set direction without emitting ``dir_changed``."""
        try:
            self._dir_idx = _DIRECTIONS.index((direction or "").upper())
        except ValueError:
            self._dir_idx = 0
        self._refresh()

    # ── Internal ─────────────────────────────────────────────────────
    def _cycle(self):
        self._dir_idx = (self._dir_idx + 1) % len(_DIRECTIONS)
        self._refresh()
        self.dir_changed.emit()

    def _refresh(self):
        active = self._dir_idx != 0
        self.btn_dir.setText(_DIR_LABELS[self.direction])
        self.btn_dir.setStyleSheet(_BTN_STYLE_ACTIVE if active else _BTN_STYLE)
        self.order_edit.setEnabled(active)
        if not active:
            self.set_order(0)

    def _on_order_changed(self):
        if self._suppress:
            return
        self.order_edited.emit(self.order)


# ── Cross-row priority management ────────────────────────────────────

def _active(rows) -> list:
    """Rows whose sort direction is set."""
    return [r for r in rows if r.sort_ctrl.direction]


def _active_in_order(rows) -> list:
    """Active rows ordered by their current priority (stable for ties)."""
    active = _active(rows)
    return sorted(active, key=lambda r: r.sort_ctrl.order or 10_000)


def _assign_contiguous(ordered_rows) -> None:
    """Number the given already-ordered rows 1..k."""
    for i, r in enumerate(ordered_rows, start=1):
        r.sort_ctrl.set_order(i)


def renumber(rows) -> None:
    """Re-number active rows 1..k by current priority; zero the rest."""
    _assign_contiguous(_active_in_order(rows))
    for r in rows:
        if not r.sort_ctrl.direction:
            r.sort_ctrl.set_order(0)


def handle_direction_changed(rows, row) -> None:
    """Update priorities after a row's direction toggle changed.

    Newly-activated rows are appended at the end of the sort order; a row
    switched back to None drops out and the rest re-number contiguously.
    """
    if row.sort_ctrl.direction:
        if row.sort_ctrl.order == 0:
            others = [r for r in _active(rows) if r is not row]
            row.sort_ctrl.set_order(len(others) + 1)
    else:
        row.sort_ctrl.set_order(0)
    renumber(rows)


def handle_order_edited(rows, row, new_val: int) -> None:
    """Re-position *row* to priority *new_val*, cascading the others.

    Example: rows at 1,2,3,4 and the user sets one to 2 -> that row lands at
    2 and the previous 2,3,4 shift to 3,4,5.
    """
    active = _active(rows)
    if row not in active:
        # Editing order on an unsorted row is a no-op (spinbox is disabled).
        row.sort_ctrl.set_order(0)
        return
    k = len(active)
    target = max(1, min(int(new_val or 1), k))
    others = [r for r in _active_in_order(rows) if r is not row]
    others.insert(target - 1, row)
    _assign_contiguous(others)
    for r in rows:
        if not r.sort_ctrl.direction:
            r.sort_ctrl.set_order(0)


def order_by_specs(specs: list[dict]) -> list[dict]:
    """Filter+sort a list of column spec dicts by their sort metadata.

    Each spec may carry ``sort`` ("ASC"/"DESC"/"") and ``sort_order`` (int).
    Returns only the sorted specs, ordered by ``sort_order``.
    """
    sortable = [s for s in specs
                if (s.get("sort") or "").upper() in ("ASC", "DESC")]
    return sorted(sortable, key=lambda s: s.get("sort_order", 0) or 0)
