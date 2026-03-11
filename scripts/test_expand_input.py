"""Minimal test: a single expanding input box in a window."""
import sys
sys.path.insert(0, r'c:\Users\ab7y02\SuiteViewP')

from PyQt6.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QPlainTextEdit, QSizePolicy,
)
from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QFontMetrics


class ExpandBox(QPlainTextEdit):
    _MAX_H = 200

    def __init__(self):
        super().__init__()
        self.setPlaceholderText("Type here — box grows as you type...")
        self.setLineWrapMode(QPlainTextEdit.LineWrapMode.WidgetWidth)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

        # Calculate single-line height from font metrics + frame
        fm = QFontMetrics(self.font())
        self._line_h = fm.height()
        # frame margins: top/bottom of the QPlainTextEdit frame
        frame_w = self.frameWidth() * 2
        doc_margin = int(self.document().documentMargin()) * 2
        self._base_pad = frame_w + doc_margin
        self._min_h = self._line_h + self._base_pad

        self.setFixedHeight(self._min_h)
        self.textChanged.connect(self._schedule_grow)

    def _schedule_grow(self):
        # Defer so the layout has updated viewport width
        QTimer.singleShot(0, self._grow)

    def _grow(self):
        # Ask the document how tall it really is given current viewport width
        doc = self.document().clone()
        doc.setTextWidth(self.viewport().width())
        content_h = int(doc.size().height()) + self._base_pad
        h = max(self._min_h, min(self._MAX_H, content_h))
        if h != self.height():
            self.setFixedHeight(h)
        # scrollbar only when maxed out
        if h >= self._MAX_H:
            self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        else:
            self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

    def resizeEvent(self, e):
        super().resizeEvent(e)
        self._grow()


app = QApplication(sys.argv)

win = QWidget()
win.setWindowTitle("Test Expanding Input")
win.resize(400, 200)

lay = QVBoxLayout(win)
lay.setContentsMargins(10, 10, 10, 10)

box = ExpandBox()
lay.addWidget(box)
lay.addStretch()

win.show()
sys.exit(app.exec())
