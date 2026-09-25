"""PolicySummaryStrip -- the at-a-glance band under the PolView lookup bar.

Row 1: insured name, plan, face and key dates on the left; status chips,
notes and copy buttons on the right.  Row 2 (only when there is something to
say): notices and context-aware suggested next steps.

The strip is fed a ``PolicySummary`` from ``services.policy_insights`` after
every background stage, so chips appear as their data arrives.
"""

from __future__ import annotations

from html import escape
from typing import Iterable, Optional

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget

from ..services.policy_insights import (
    DANGER, FUN, INFO, NEUTRAL, OK, TEST, WARN, Chip, PolicySummary, Suggestion,
)
from .styles import GOLD_DARK, GOLD_PRIMARY, GRAY_DARK, GRAY_TEXT, GREEN_DARK, GREEN_PRIMARY
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
    QPushButton:checked {{ background: #FFF3D0; border-color: {GOLD_PRIMARY}; }}
"""

_SUGGESTION_STYLE = f"""
    QPushButton {{
        background: #FFF3D0; border: 1px solid {GOLD_PRIMARY}; border-radius: 8px;
        color: {GREEN_DARK}; font-size: 10px; font-weight: bold;
        padding: 0px 8px; min-height: 16px; max-height: 16px;
    }}
    QPushButton:hover {{ background: {GOLD_PRIMARY}; color: #FFFFFF; }}
"""


class PolicySummaryStrip(QWidget):
    """Dense at-a-glance summary of the loaded policy."""

    suggestion_clicked = pyqtSignal(str)
    copy_requested = pyqtSignal()
    notes_requested = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("policySummaryStrip")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setStyleSheet(_STRIP_STYLE)
        self._summary: Optional[PolicySummary] = None
        self._chip_labels: dict[str, QLabel] = {}

        outer = QVBoxLayout(self)
        outer.setContentsMargins(8, 3, 6, 3)
        outer.setSpacing(2)

        row = QHBoxLayout()
        row.setSpacing(6)
        self.name_label = CopyableLabel("")
        self.name_label.setStyleSheet(
            f"font-size: 13px; font-weight: bold; color: {GREEN_DARK}; background: transparent;"
        )
        row.addWidget(self.name_label)
        self.facts_label = CopyableLabel("")
        self.facts_label.setTextFormat(Qt.TextFormat.RichText)
        self.facts_label.setStyleSheet(
            f"font-size: 11px; color: {GRAY_DARK}; background: transparent;"
        )
        row.addWidget(self.facts_label, 1)

        self._chips_host = QWidget()
        self._chips_host.setStyleSheet("background: transparent;")
        self._chips_layout = QHBoxLayout(self._chips_host)
        self._chips_layout.setContentsMargins(0, 0, 0, 0)
        self._chips_layout.setSpacing(4)
        row.addWidget(self._chips_host)

        self.notes_button = QPushButton("📝 Notes")
        self.notes_button.setToolTip("Your private notes for this policy (Ctrl+N)")
        self.notes_button.setStyleSheet(_TOOL_BUTTON_STYLE)
        self.notes_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.notes_button.clicked.connect(self.notes_requested.emit)
        row.addWidget(self.notes_button)

        self.copy_button = QPushButton("⧉ Copy")
        self.copy_button.setToolTip(
            "Copy a plain-text policy summary for email, tickets or test evidence (Ctrl+Shift+C)"
        )
        self.copy_button.setStyleSheet(_TOOL_BUTTON_STYLE)
        self.copy_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.copy_button.clicked.connect(self.copy_requested.emit)
        row.addWidget(self.copy_button)
        outer.addLayout(row)

        self._detail_row = QWidget()
        self._detail_row.setStyleSheet("background: transparent;")
        detail = QHBoxLayout(self._detail_row)
        detail.setContentsMargins(0, 0, 0, 0)
        detail.setSpacing(6)
        self.notice_label = QLabel("")
        self.notice_label.setWordWrap(False)
        self.notice_label.setStyleSheet(
            f"font-size: 10px; color: #8A5300; background: transparent;"
        )
        detail.addWidget(self.notice_label, 1)
        self._suggest_caption = QLabel("Suggested:")
        self._suggest_caption.setStyleSheet(
            f"font-size: 10px; color: {GRAY_TEXT}; font-style: italic; background: transparent;"
        )
        detail.addWidget(self._suggest_caption)
        self._suggest_host = QWidget()
        self._suggest_host.setStyleSheet("background: transparent;")
        self._suggest_layout = QHBoxLayout(self._suggest_host)
        self._suggest_layout.setContentsMargins(0, 0, 0, 0)
        self._suggest_layout.setSpacing(4)
        detail.addWidget(self._suggest_host)
        outer.addWidget(self._detail_row)
        self._detail_row.setVisible(False)

        self.set_notes_count(0)
        self.clear("Enter a policy number to begin  ·  press F1 for shortcuts")

    # -- public API -------------------------------------------------------

    @property
    def summary(self) -> Optional[PolicySummary]:
        return self._summary

    def chip_texts(self) -> list[str]:
        return [label.text() for label in self._chip_labels.values()]

    def clear(self, message: str = ""):
        self._summary = None
        self.name_label.setText("")
        self.facts_label.setText(
            f'<span style="color:{GRAY_TEXT}; font-style:italic;">{escape(message)}</span>'
        )
        self._set_chips(())
        self._set_detail((), ())
        self.copy_button.setEnabled(False)
        self.notes_button.setEnabled(False)

    def set_summary(self, summary: PolicySummary, suggestions: Iterable[Suggestion] = ()):
        self._summary = summary
        self.name_label.setText(summary.insured_name or "")
        self.name_label.setVisible(bool(summary.insured_name))
        self.facts_label.setText(self._facts_html(summary))
        self._set_chips(summary.chips)
        self._set_detail(summary.notices, tuple(suggestions))
        self.copy_button.setEnabled(True)
        self.notes_button.setEnabled(True)

    def set_notes_count(self, count: int):
        self.notes_button.setText(f"📝 Notes ({count})" if count else "📝 Notes")
        self.notes_button.setStyleSheet(
            _TOOL_BUTTON_STYLE + (
                f"QPushButton {{ background: #FFF3D0; border-color: {GOLD_PRIMARY}; }}"
                if count else ""
            )
        )

    # -- helpers ----------------------------------------------------------

    @staticmethod
    def _facts_html(summary: PolicySummary) -> str:
        sep = f' <span style="color:{GOLD_DARK};">·</span> '
        parts = []
        plan = summary.plancode or ""
        if summary.form_number:
            plan = f"{plan} ({summary.form_number})" if plan else summary.form_number
        if plan:
            parts.append(f"<b>{escape(plan)}</b>")
        if summary.face_amount is not None:
            parts.append(f"Face <b>${float(summary.face_amount):,.0f}</b>")
        if summary.issue_date:
            d = summary.issue_date
            age = f" (age {summary.issue_age})" if summary.issue_age is not None else ""
            parts.append(f"Issued {d.month}/{d.day:02d}/{d.year}{age}")
        if summary.policy_year:
            parts.append(f"Yr {summary.policy_year}")
        if summary.attained_age is not None:
            parts.append(f"Att age {summary.attained_age}")
        if summary.paid_to_date:
            d = summary.paid_to_date
            parts.append(f"Paid to {d.month}/{d.day:02d}/{d.year}")
        if not parts:
            return (f'<span style="color:{GRAY_TEXT}; font-style:italic;">'
                    "Loading policy summary…</span>")
        return sep.join(parts)

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
            self._chips_layout.addWidget(label)
            self._chip_labels[chip.key] = label

    def _set_detail(self, notices, suggestions):
        while self._suggest_layout.count():
            item = self._suggest_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        self.notice_label.setText("   ".join(f"⚠ {n}" for n in notices))
        self.notice_label.setToolTip("\n".join(notices))
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
        self._detail_row.setVisible(bool(notices or suggestions))

    def suggestion_keys(self) -> list[str]:
        keys = []
        for index in range(self._suggest_layout.count()):
            widget = self._suggest_layout.itemAt(index).widget()
            if widget is not None:
                keys.append(widget.objectName().removeprefix("suggest_"))
        return keys
