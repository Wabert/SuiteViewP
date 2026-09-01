"""Landing screen that asks which product line's rates to manage.

UL and Term rates live in different tables, are built from different source
files, and follow different rules — so Rate Manager asks once, up front,
rather than mixing the two behind one set of controls.
"""

from __future__ import annotations

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QFrame, QHBoxLayout, QLabel, QVBoxLayout, QWidget,
)

from suiteview.ratemanager.rm_styles import (
    BG_INPUT, BG_MID, BORDER, GOLD, GOLD_TEXT, TEXT, TEXT_MID,
    body_stylesheet,
)

UL_LINE = "UL"
TERM_LINE = "Term"


class _ProductCard(QFrame):
    """One large, clickable product-line card."""

    clicked = pyqtSignal(str)

    def __init__(self, line: str, title: str, blurb: str, detail: str,
                 parent=None):
        super().__init__(parent)
        self._line = line
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setMinimumSize(300, 200)
        self.setMaximumHeight(250)
        self.setStyleSheet(f"""
            QFrame {{
                background: {BG_INPUT};
                border: 2px solid {BORDER};
                border-radius: 8px;
            }}
            QFrame:hover {{
                background: {BG_MID};
                border-color: {GOLD};
            }}
        """)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(22, 20, 22, 20)
        layout.setSpacing(10)

        heading = QLabel(title)
        heading.setStyleSheet(
            f"color: {GOLD_TEXT}; font-size: 20px; font-weight: bold; "
            f"background: transparent; border: none;")
        layout.addWidget(heading)

        summary = QLabel(blurb)
        summary.setWordWrap(True)
        summary.setStyleSheet(
            f"color: {TEXT}; font-size: 13px; background: transparent; "
            f"border: none;")
        layout.addWidget(summary)

        layout.addStretch()

        tables = QLabel(detail)
        tables.setWordWrap(True)
        tables.setStyleSheet(
            f"color: {TEXT_MID}; font-size: 11px; font-family: 'Cascadia Code',"
            f" 'Consolas', monospace; background: transparent; border: none;")
        layout.addWidget(tables)

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton and self.rect().contains(
                event.position().toPoint()):
            self.clicked.emit(self._line)
        super().mouseReleaseEvent(event)


class ProductLineChooser(QWidget):
    """Two cards: UL rates or Term rates."""

    line_chosen = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("RateManagerBody")
        self.setStyleSheet(body_stylesheet())

        root = QVBoxLayout(self)
        root.setContentsMargins(40, 30, 40, 40)
        root.setSpacing(14)

        heading = QLabel("Which rates are you working with?")
        heading.setStyleSheet(
            f"color: {GOLD_TEXT}; font-size: 22px; font-weight: bold;")
        heading.setAlignment(Qt.AlignmentFlag.AlignCenter)
        root.addWidget(heading)

        subtitle = QLabel(
            "The two product lines load from different source files into "
            "different tables. Pick one to continue — you can switch at any "
            "time from the header.")
        subtitle.setObjectName("Subtitle")
        subtitle.setWordWrap(True)
        subtitle.setAlignment(Qt.AlignmentFlag.AlignCenter)
        root.addWidget(subtitle)

        root.addSpacing(10)

        cards = QHBoxLayout()
        cards.setSpacing(24)
        cards.addStretch()
        for line, title, blurb, detail in (
            (UL_LINE, "UL Rates",
             "Universal and indexed life. Builds from an IAF plus the "
             "optional MPF, CKULTB04 and CKULTB01 reports, and includes the "
             "per-file converters.",
             "POINT_PVSRB · RATE_COI · RATE_TRGPREM\n"
             "RATE_SCR · RATE_EPU\n"
             "POINT_BENEFIT · RATE_BENCOI · RATE_BENTRG"),
            (TERM_LINE, "Term Rates",
             "Term life. Builds from a single IAF into pre-compiled premium "
             "and benefit rates, using the modal factors, band structure and "
             "level periods you supply.",
             "TERM_POINT_PV · TERM_POINT_PVSRB\n"
             "TERM_POINT_BENEFIT · TERM_RATE_PREM · TERM_RATE_BEN\n"
             "TERM_RATE_MODEFACT · TERM_RATE_BANDSPECS"),
        ):
            card = _ProductCard(line, title, blurb, detail)
            card.clicked.connect(self.line_chosen.emit)
            cards.addWidget(card, stretch=1)
        cards.addStretch()
        root.addLayout(cards)
        root.addStretch()

        hint = QLabel(
            "Both lines write to the same UL_Rates database, but never to "
            "each other's tables.")
        hint.setObjectName("Subtitle")
        hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
        root.addWidget(hint)
