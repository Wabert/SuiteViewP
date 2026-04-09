"""
TAI Reserve tab — placeholder for future TAI reserve criteria.
"""
from __future__ import annotations

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QWidget, QVBoxLayout, QLabel
from PyQt6.QtGui import QFont

_FONT = QFont("Segoe UI", 10)


class TaiReserveTab(QWidget):
    """Placeholder tab for TAI Reserve criteria."""

    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        lbl = QLabel("TAI Reserve — coming soon")
        lbl.setFont(_FONT)
        lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(lbl)
        layout.addStretch()

    def get_state(self) -> dict:
        return {}

    def set_state(self, state: dict):
        pass
