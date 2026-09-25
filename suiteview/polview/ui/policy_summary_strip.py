"""PolicySummaryStrip -- the badge band under the PolView lookup bar.

One compact row: status badges on the left (they appear as their data
arrives from the background loader), then context-aware suggested next steps
and the Timeline / Notes / Copy buttons on the right.

The strip is fed a ``PolicySummary`` from ``services.policy_insights`` after
every background stage.
"""

from __future__ import annotations

from typing import Iterable, Optional

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import QHBoxLayout, QLabel, QPushButton, QWidget

from ..services.policy_insights import (
    DANGER, FUN, INFO, NEUTRAL, OK, TEST, WARN, Chip, PolicySummary, Suggestion,
)
from .styles import GOLD_PRIMARY, GRAY_TEXT, GREEN_DARK, GREEN_PRIMARY
from .widgets import CopyableLabel

CHIP_COLORS = {
    DANGER: ("#FDECEA", "#B71C1C", "#E57373"),
    WARN: ("#FFF4E0", "#8A5300", "#F0B429"),
    INFO: ("#E3F2FD", "#0D47A1", "#90CAF9"),
    OK: ("#E8F5E9", "#1B5E20", "#81C784"),
    NEUTRAL: ("#F1F3F5", "#2D3748", "#CBD5E0"),
    TEST: ("#6A1B9A", "#FFFFFF", "#4A148C"),
    FUN: ("#FFF8E1", "#6D4C41", "#FFD54F"),
}


def chip_style(tone: str) -> str:
    bg, fg, border = CHIP_COLORS.get(tone, CHIP_COLORS[NEUTRAL])
    return (
        f"QLabel {{ background: {bg}; color: {fg}; border: 1px solid {border};"
        " border-radius: 8px; padding: 0px 7px; font-size: 10px; font-weight: bold; }"
    )


_STRIP_STYLE = f"""
    QWidget#policySummaryStrip {{
        background: #FFFFFF;
        border: 1px solid {GREEN_PRIMARY};
        border-radius: 6px;
    }}
"""

_TOOL_BUTTON_STYLE = f"""
    QPushButton {{
        background: transparent; border: 1px solid #CBD5E0; border-radius: 8px;
        color: {GREEN_DARK}; font-size: 10px; font-weight: bold;
        padding: 0px 7px; min-height: 16px; max-height: 16px;
    }}
    QPushButton:hover {{ background: #E8F5E9; border-color: {GREEN_PRIMARY}; }}
    QPushButton:disabled {{ color: #A0AEC0; border-color: #E2E8F0; }}
"""

_NOTES_WITH_COUNT_STYLE = _TOOL_BUTTON_STYLE + (
    f"QPushButton {{ background: #FFF3D0; border-color: {GOLD_PRIMARY}; }}"
)

_SUGGESTION_STYLE = f"""
    QPushButton {{
        background: #FFF3D0; border: 1px solid {GOLD_PRIMARY}; border-radius: 8px;
        color: {GREEN_DARK}; font-size: 10px; font-weight: bold;
        padding: 0px 8px; min-height: 16px; max-height: 16px;
    }}
    QPushButton:hover {{ background: {GOLD_PRIMARY}; color: #FFFFFF; }}
"""


class PolicySummaryStrip(QWidget):
    """Status badges and quick actions for the loaded policy."""

    suggestion_clicked = pyqtSignal(str)
    copy_requested = pyqtSignal()
    notes_requested = pyqtSignal()
    timeline_requested = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("policySummaryStrip")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setStyleSheet(_STRIP_STYLE)
        self._summary: Optional[PolicySummary] = None
        self._chip_labels: dict[str, QLabel] = {}
        self._notes_count = 0

        row = QHBoxLayout(self)
        row.setContentsMargins(6, 3, 6, 3)
        row.setSpacing(4)

        self.message_label = QLabel("")
        self.message_label.setStyleSheet(
            f"font-size: 11px; color: {GRAY_TEXT}; font-style: italic; background: transparent;"
        )
        row.addWidget(self.message_label)

        self._chips_host = QWidget()
        self._chips_host.setStyleSheet("background: transparent;")
        self._chips_layout = QHBoxLayout(self._chips_host)
        self._chips_layout.setContentsMargins(0, 0, 0, 0)
        self._chips_layout.setSpacing(4)
        row.addWidget(self._chips_host)
        row.addStretch(1)

        self._suggest_caption = QLabel("Suggested:")
        self._suggest_caption.setStyleSheet(
            f"font-size: 10px; color: {GRAY_TEXT}; font-style: italic; background: transparent;"
        )
        row.addWidget(self._suggest_caption)
        self._suggest_host = QWidget()
        self._suggest_host.setStyleSheet("background: transparent;")
        self._suggest_layout = QHBoxLayout(self._suggest_host)
        self._suggest_layout.setContentsMargins(0, 0, 8, 0)
        self._suggest_layout.setSpacing(4)
        row.addWidget(self._suggest_host)

        self.timeline_button = self._tool_button(
            "🗓 Timeline", "Every key policy date in order, with today marked (Ctrl+D)",
            self.timeline_requested)
        self.notes_button = self._tool_button(
            "📝 Notes", "Your private notes for this policy (Ctrl+N)", self.notes_requested)
        self.copy_button = self._tool_button(
            "⧉ Copy",
            "Copy a policy summary for email, tickets or test evidence (Ctrl+Shift+C).\n"
            "Pastes as a neat table in Outlook/Word/Excel and as aligned text elsewhere.",
            self.copy_requested)
        for button in (self.timeline_button, self.notes_button, self.copy_button):
            row.addWidget(button)

        self.clear("Enter a policy number to begin")

    def _tool_button(self, text: str, tooltip: str, signal) -> QPushButton:
        button = QPushButton(text)
        button.setToolTip(tooltip)
        button.setStyleSheet(_TOOL_BUTTON_STYLE)
        button.setCursor(Qt.CursorShape.PointingHandCursor)
        button.clicked.connect(signal.emit)
        return button

    # -- public API -------------------------------------------------------

    @property
    def summary(self) -> Optional[PolicySummary]:
        return self._summary

    def chip_texts(self) -> list[str]:
        return [label.text() for label in self._chip_labels.values()]

    def clear(self, message: str = ""):
        self._summary = None
        self.message_label.setText(message)
        self.message_label.setVisible(bool(message))
        self._set_chips(())
        self._set_suggestions(())
        for button in (self.copy_button, self.notes_button, self.timeline_button):
            button.setEnabled(False)

    def set_summary(self, summary: PolicySummary, suggestions: Iterable[Suggestion] = ()):
        self._summary = summary
        self.message_label.setVisible(False)
        self._set_chips(summary.chips)
        self._set_suggestions(tuple(suggestions))
        for button in (self.copy_button, self.notes_button, self.timeline_button):
            button.setEnabled(True)

    def set_notes_count(self, count: int):
        self._notes_count = count
        self.notes_button.setText(f"📝 Notes ({count})" if count else "📝 Notes")
        self.notes_button.setStyleSheet(_NOTES_WITH_COUNT_STYLE if count else _TOOL_BUTTON_STYLE)

    def suggestion_keys(self) -> list[str]:
        keys = []
        for index in range(self._suggest_layout.count()):
            widget = self._suggest_layout.itemAt(index).widget()
            if widget is not None:
                keys.append(widget.objectName().removeprefix("suggest_"))
        return keys

    # -- helpers ----------------------------------------------------------

    def _set_chips(self, chips: Iterable[Chip]):
        while self._chips_layout.count():
            item = self._chips_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        self._chip_labels = {}
        for chip in chips:
            label = CopyableLabel(chip.text)
            label.setObjectName(f"chip_{chip.key}")
            label.setStyleSheet(chip_style(chip.tone))
            label.setToolTip(chip.tooltip)
            label.setFixedHeight(18)
            label.setMinimumWidth(label.sizeHint().width())
            self._chips_layout.addWidget(label)
            self._chip_labels[chip.key] = label

    def _set_suggestions(self, suggestions):
        while self._suggest_layout.count():
            item = self._suggest_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        for suggestion in suggestions:
            button = QPushButton(f"{suggestion.text} ▸")
            button.setObjectName(f"suggest_{suggestion.key}")
            button.setToolTip(suggestion.tooltip)
            button.setStyleSheet(_SUGGESTION_STYLE)
            button.setCursor(Qt.CursorShape.PointingHandCursor)
            button.clicked.connect(
                lambda _checked=False, key=suggestion.key: self.suggestion_clicked.emit(key)
            )
            self._suggest_layout.addWidget(button)
        self._suggest_caption.setVisible(bool(suggestions))
        self._suggest_host.setVisible(bool(suggestions))
