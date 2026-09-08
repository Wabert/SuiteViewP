"""Landing screen that asks which product line's rates to manage.

UL, Term and Whole Life rates live in different tables and use different source
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
WL_LINE = "Whole Life"


class _ProductCard(QFrame):
    """One large, clickable product-line card."""

    clicked = pyqtSignal(str)

    def __init__(self, line: str, title: str, blurb: str, detail: str,
                 parent=None):
        super().__init__(parent)
        self._line = line
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setMinimumSize(220, 230)
        self.setMaximumHeight(290)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setAccessibleName(title)
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
        layout.setContentsMargins(14, 16, 14, 16)
        layout.setSpacing(8)

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
        tables.setMinimumWidth(0)
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

    def keyPressEvent(self, event):
        if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter, Qt.Key.Key_Space):
            self.clicked.emit(self._line)
            event.accept()
            return
        super().keyPressEvent(event)


class ProductLineChooser(QWidget):
    """Three independent rate lines, sized to fit the minimum window width."""

    line_chosen = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("RateManagerBody")
        self.setStyleSheet(body_stylesheet())

        root = QVBoxLayout(self)
        root.setContentsMargins(18, 24, 18, 24)
        root.setSpacing(14)

        heading = QLabel("Which rates are you working with?")
        heading.setStyleSheet(
            f"color: {GOLD_TEXT}; font-size: 22px; font-weight: bold;")
        heading.setAlignment(Qt.AlignmentFlag.AlignCenter)
        root.addWidget(heading)

        subtitle = QLabel(
            "The product lines load from different source files into "
            "different tables. Pick one to continue — you can switch at any "
            "time from the header.")
        subtitle.setObjectName("Subtitle")
        subtitle.setWordWrap(True)
        subtitle.setAlignment(Qt.AlignmentFlag.AlignCenter)
        root.addWidget(subtitle)

        root.addSpacing(10)

        cards = QHBoxLayout()
        cards.setSpacing(12)
        for line, title, blurb, detail in (
            (UL_LINE, "UL Rates",
             "Universal and indexed life. Builds from an IAF plus the "
             "optional MPF, CKULTB04 and CKULTB01 reports, and includes the "
             "per-file converters.",
             "POINT_PVSRB · RATE_COI\n"
             "RATE_TRGPREM · RATE_SCR · RATE_EPU\n"
             "POINT_BENEFIT · RATE_BENCOI\nRATE_BENTRG"),
            (TERM_LINE, "Term Rates",
             "Term life. Builds from a single IAF into pre-compiled premium "
             "and benefit rates, using the modal factors, band structure and "
             "level periods you supply.",
             "TERM_POINT_PV · TERM_POINT_PVSRB\nTERM_POINT_BENEFIT\n"
             "TERM_RATE_PREM · TERM_RATE_BEN\n"
             "TERM_RATE_MODEFACT · TERM_RATE_BANDSPECS"),
            (WL_LINE, "Whole Life",
             "Load cash values, net single premiums, paid-up insurance, "
             "IAF premiums and dividends. Preview source rows, compare "
             "against the database, then approve changes.",
             "WL rates · Dividend tables\n"
             "Dividend plan-key map\n"
             "CYBERLIFE_PDF metadata (read-only)"),
        ):
            card = _ProductCard(line, title, blurb, detail)
            card.clicked.connect(self.line_chosen.emit)
            cards.addWidget(card, stretch=1)
        root.addLayout(cards)
        root.addStretch()

        hint = QLabel(
            "All three lines use the UL_Rates database, but never write to "
            "each other's tables.")
        hint.setObjectName("Subtitle")
        hint.setWordWrap(True)
        hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
        root.addWidget(hint)
