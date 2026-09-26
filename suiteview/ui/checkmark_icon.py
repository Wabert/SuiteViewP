"""Shared checkbox checkmark asset for SuiteView styles."""

from __future__ import annotations

from suiteview.core.profile_paths import profile_path

CHECKMARK_PATH = profile_path("checkmark.png")


def ensure_checkmark() -> None:
    """Create the white tick PNG used by QSS checkbox indicators."""

    if CHECKMARK_PATH.exists():
        return
    CHECKMARK_PATH.parent.mkdir(parents=True, exist_ok=True)
    from PyQt6.QtCore import QPoint
    from PyQt6.QtGui import QColor, QPainter, QPen, QPixmap

    pixmap = QPixmap(12, 12)
    pixmap.fill(QColor(0, 0, 0, 0))
    painter = QPainter(pixmap)
    pen = QPen(QColor("white"))
    pen.setWidth(2)
    painter.setPen(pen)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.drawLine(QPoint(2, 6), QPoint(5, 9))
    painter.drawLine(QPoint(5, 9), QPoint(10, 3))
    painter.end()
    pixmap.save(str(CHECKMARK_PATH))
