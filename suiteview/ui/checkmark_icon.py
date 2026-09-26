"""Shared checkbox checkmark asset for SuiteView styles."""

from __future__ import annotations

from pathlib import Path

from suiteview.core.profile_paths import profile_path


def checkmark_path() -> Path:
    return profile_path("checkmark.png")


class _DynamicPathString(str):
    def __new__(cls, profile_name: str):
        value = str(profile_path(profile_name))
        obj = str.__new__(cls, value)
        obj._profile_name = profile_name
        return obj

    def _value(self) -> str:
        return str(profile_path(self._profile_name))

    def __str__(self) -> str:
        return self._value()

    def __repr__(self) -> str:
        return repr(self._value())

    def __format__(self, format_spec: str) -> str:
        return format(self._value(), format_spec)

    def replace(self, old: str, new: str, count: int = -1) -> str:
        return self._value().replace(old, new, count)


class _DynamicProfilePath:
    def __init__(self, profile_name: str):
        self._profile_name = profile_name

    def _path(self) -> Path:
        return profile_path(self._profile_name)

    def __fspath__(self) -> str:
        return str(self._path())

    def __str__(self) -> str:
        return _DynamicPathString(self._profile_name)

    def __getattr__(self, name: str):
        return getattr(self._path(), name)


CHECKMARK_PATH = _DynamicProfilePath("checkmark.png")


def ensure_checkmark() -> None:
    """Create the white tick PNG used by QSS checkbox indicators."""

    path = checkmark_path()
    if path.exists():
        return
    path.parent.mkdir(parents=True, exist_ok=True)
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
    pixmap.save(str(path))
