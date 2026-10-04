"""Account Values: the Short Pay / Dial-To button and its popup.

The six short-pay and death-benefit dial-to rows sit behind one compact button in
the Policy Info panel instead of taking six panel rows. The button looks active
(PolView green) when any of the values is present and greyed when none is, but it
stays clickable either way: the popup then lists the rows blank with an italic
"none" note, so the user can confirm the policy has no short-pay data rather than
wonder whether the button is broken (inactive stays visible).
"""

from __future__ import annotations

from PyQt6.QtCore import QPoint, Qt
from PyQt6.QtWidgets import QFrame, QLabel, QPushButton, QVBoxLayout

from ..styles import GOLD_PRIMARY, GREEN_DARK, GREEN_PRIMARY, WHITE
from ..widgets import StyledInfoTableGroup

BUTTON_TEXT = "Short Pay / Dial-To \u25b8"
EMPTY_NOTE = "No short-pay or dial-to-age values on this policy."
# (label, attr) in display order; attrs also key the AdvProdValues field tooltips.
FIELDS = (
    ("Short Pay Prem", "short_pay_prem"),
    ("Short Pay Mode", "short_pay_mode"),
    ("Short Pay Dur", "short_pay_dur"),
    ("SP Billing Cease", "sp_billing_cease_date"),
    ("SP Prem Cease Age", "sp_prem_cease_age"),
    ("DB Dial-To Age", "db_dial_to_age"),
)
_INACTIVE_BG = "#E1E5EB"
_INACTIVE_TEXT = "#8A96A3"
_INACTIVE_BORDER = "#CBD5E0"
_NOTE_TEXT = "#6B7785"

_ACTIVE_STYLE = f"""
    QPushButton {{
        background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 {GREEN_PRIMARY}, stop:1 {GREEN_DARK});
        color: #FFFFFF; border: 1px solid {GREEN_DARK}; border-radius: 3px;
        font-size: 10px; font-weight: bold; padding: 0px 8px;
    }}
    QPushButton:hover {{ color: #FFD54F; }}
"""
_INACTIVE_STYLE = f"""
    QPushButton {{
        background: {_INACTIVE_BG}; color: {_INACTIVE_TEXT}; border: 1px solid {_INACTIVE_BORDER};
        border-radius: 3px; font-size: 10px; font-weight: bold; font-style: italic; padding: 0px 8px;
    }}
    QPushButton:hover {{ border-color: {GREEN_PRIMARY}; }}
"""


class ShortPayDialToButton(QPushButton):
    """Compact button: green when the policy has short-pay/dial-to data, grey otherwise."""

    def __init__(self, parent=None):
        super().__init__(BUTTON_TEXT, parent)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFixedHeight(17)
        self.set_active(False, ())

    @property
    def active(self) -> bool:
        return self._active

    def set_active(self, active: bool, present_labels) -> None:
        self._active = bool(active)
        self.setStyleSheet(_ACTIVE_STYLE if self._active else _INACTIVE_STYLE)
        self.setToolTip(
            "Short pay / dial-to values present: " + ", ".join(present_labels)
            if self._active else EMPTY_NOTE + " Click to confirm.")


class ShortPayDialToPopup(QFrame):
    """Small click-away popup holding the short-pay and dial-to-age rows."""

    def __init__(self, parent=None):
        super().__init__(parent, Qt.WindowType.Popup)
        self.setObjectName("ShortPayDialToPopup")
        self.setStyleSheet(
            f"QFrame#ShortPayDialToPopup {{ background: {WHITE}; border: 2px solid {GOLD_PRIMARY}; }}")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(2)
        self.info = StyledInfoTableGroup("Short Pay / Dial-To", columns=1, show_table=False)
        for label, attr in FIELDS:
            self.info.add_field(label, attr, 115, 80, "AdvProdValues", attr)
        self.info.setFixedSize(236, 136)
        layout.addWidget(self.info)
        self.empty_note = QLabel(EMPTY_NOTE)
        self.empty_note.setWordWrap(True)
        self.empty_note.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.empty_note.setStyleSheet(f"color: {_NOTE_TEXT}; font-style: italic; font-size: 10px;")
        self.empty_note.setFixedWidth(236)
        layout.addWidget(self.empty_note)

    def clear(self) -> None:
        self.info.clear_info()
        for field in self.info._fields.values():
            field.setToolTip("")
        self.empty_note.show()

    def set_value(self, attr: str, text: str, tip: str = "") -> None:
        self.info.set_value(attr, text)
        if tip:
            self.info._fields[attr].setToolTip(tip)

    def present_labels(self) -> tuple[str, ...]:
        return tuple(label for label, attr in FIELDS if self.info._fields[attr].text().strip())

    def refresh_note(self) -> None:
        self.empty_note.setVisible(not self.present_labels())

    def show_below(self, anchor) -> None:
        self.adjustSize()
        self.move(anchor.mapToGlobal(QPoint(0, anchor.height() + 2)))
        self.show()
