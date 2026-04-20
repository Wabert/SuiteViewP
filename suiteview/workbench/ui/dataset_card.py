"""
DatasetCard — a compact card widget displaying a PinnedDataset's signature.

Shows: source badge, name, row×col shape, timestamp, preview/refresh buttons.
Supports drag for future Workbench canvas drop.
"""
from __future__ import annotations

from datetime import datetime

from PyQt6.QtCore import Qt, QMimeData, pyqtSignal, QPoint
from PyQt6.QtGui import QDrag, QFont, QColor, QPainter
from PyQt6.QtWidgets import (
    QFrame, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QToolTip,
)

from suiteview.workbench.models import PinnedDataset

# Source-type → (badge text, badge colour)
_SOURCE_BADGES: dict[str, tuple[str, str]] = {
    "cyberlife":      ("CYB", "#E97320"),
    "tai":            ("TAI", "#2563EB"),
    "dynamic_group":  ("GRP", "#10B981"),
    "db_query":       ("DBQ", "#8B5CF6"),
    "xdb_query":      ("XDB", "#EC4899"),
    "workbench":      ("WRK", "#0D9488"),
}

DATASET_DRAG_MIME = "application/x-suiteview-pinned-dataset"


class DatasetCard(QFrame):
    """Compact card for one pinned dataset."""

    preview_requested = pyqtSignal(str)   # dataset id
    refresh_requested = pyqtSignal(str)   # dataset id
    delete_requested = pyqtSignal(str)    # dataset id

    def __init__(self, dataset: PinnedDataset, parent=None):
        super().__init__(parent)
        self.dataset = dataset
        self._drag_start: QPoint | None = None
        self._build_ui()

    def _build_ui(self):
        self.setFrameShape(QFrame.Shape.Box)
        self.setObjectName("datasetCard")
        self._apply_style(selected=False)
        self.setFixedHeight(82)
        self.setCursor(Qt.CursorShape.OpenHandCursor)

        root = QVBoxLayout(self)
        root.setContentsMargins(8, 6, 8, 6)
        root.setSpacing(2)

        # ── Row 1: badge + name ──────────────────────────────────────
        row1 = QHBoxLayout()
        row1.setSpacing(6)

        badge_text, badge_colour = _SOURCE_BADGES.get(
            self.dataset.source_type, ("???", "#6B7280"))
        self.badge = QLabel(badge_text)
        self.badge.setFixedSize(32, 16)
        self.badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.badge.setFont(QFont("Segoe UI", 7, QFont.Weight.Bold))
        self.badge.setStyleSheet(
            f"QLabel {{ background-color: {badge_colour}; color: white;"
            f" border-radius: 3px; padding: 0px; }}")
        row1.addWidget(self.badge)

        self.lbl_name = QLabel(self.dataset.name)
        self.lbl_name.setFont(QFont("Segoe UI", 9, QFont.Weight.Bold))
        self.lbl_name.setStyleSheet("color: #0A1E5E; background: transparent;")
        self.lbl_name.setWordWrap(False)
        row1.addWidget(self.lbl_name, 1)

        btn_del = QPushButton("×")
        btn_del.setFixedSize(16, 16)
        btn_del.setFont(QFont("Segoe UI", 10, QFont.Weight.Bold))
        btn_del.setStyleSheet(
            "QPushButton { color: #999; background: transparent; border: none; }"
            "QPushButton:hover { color: #DC2626; }")
        btn_del.setToolTip("Delete dataset")
        btn_del.clicked.connect(lambda: self.delete_requested.emit(self.dataset.id))
        row1.addWidget(btn_del)

        root.addLayout(row1)

        # ── Row 2: source label + shape ──────────────────────────────
        row2 = QHBoxLayout()
        row2.setSpacing(4)

        self.lbl_source = QLabel(self.dataset.source_label)
        self.lbl_source.setFont(QFont("Segoe UI", 8))
        self.lbl_source.setStyleSheet("color: #6B7280; background: transparent;")
        row2.addWidget(self.lbl_source)
        row2.addStretch()

        self.lbl_shape = QLabel(self.dataset.shape_label)
        self.lbl_shape.setFont(QFont("Segoe UI", 8, QFont.Weight.Bold))
        self.lbl_shape.setStyleSheet("color: #0D9488; background: transparent;")
        row2.addWidget(self.lbl_shape)

        root.addLayout(row2)

        # ── Row 3: timestamp + buttons ───────────────────────────────
        row3 = QHBoxLayout()
        row3.setSpacing(4)

        ts = self.dataset.created_at.strftime("%b %d %I:%M%p").lower()
        self.lbl_time = QLabel(ts)
        self.lbl_time.setFont(QFont("Segoe UI", 7))
        self.lbl_time.setStyleSheet("color: #9CA3AF; background: transparent;")
        row3.addWidget(self.lbl_time)
        row3.addStretch()

        btn_preview = QPushButton("Preview")
        btn_preview.setFixedHeight(18)
        btn_preview.setFont(QFont("Segoe UI", 7))
        btn_preview.setStyleSheet(
            "QPushButton { background: #E8F0FF; color: #2563EB;"
            " border: 1px solid #B0C8E8; border-radius: 2px; padding: 0 6px; }"
            "QPushButton:hover { background: #D0E0F5; }")
        btn_preview.clicked.connect(
            lambda: self.preview_requested.emit(self.dataset.id))
        row3.addWidget(btn_preview)

        btn_refresh = QPushButton("Refresh")
        btn_refresh.setFixedHeight(18)
        btn_refresh.setFont(QFont("Segoe UI", 7))
        btn_refresh.setStyleSheet(
            "QPushButton { background: #E8F0FF; color: #10B981;"
            " border: 1px solid #B0C8E8; border-radius: 2px; padding: 0 6px; }"
            "QPushButton:hover { background: #D0E0F5; }")
        btn_refresh.clicked.connect(
            lambda: self.refresh_requested.emit(self.dataset.id))
        row3.addWidget(btn_refresh)

        root.addLayout(row3)

    # ── Visual state ─────────────────────────────────────────────────

    def _apply_style(self, selected: bool = False):
        if selected:
            self.setStyleSheet(
                "QFrame#datasetCard { background: #D0E0F5; border: 2px solid #2563EB;"
                " border-radius: 6px; }")
        else:
            self.setStyleSheet(
                "QFrame#datasetCard { background: white; border: 1px solid #B0C8E8;"
                " border-radius: 6px; }"
                "QFrame#datasetCard:hover { border: 1px solid #6BA3E8;"
                " background: #F0F6FF; }")

    def set_selected(self, selected: bool):
        self._apply_style(selected)

    def update_from_dataset(self, ds: PinnedDataset):
        """Refresh display after re-pin or rename."""
        self.dataset = ds
        self.lbl_name.setText(ds.name)
        self.lbl_source.setText(ds.source_label)
        self.lbl_shape.setText(ds.shape_label)
        ts = ds.created_at.strftime("%b %d %I:%M%p").lower()
        self.lbl_time.setText(ts)
        badge_text, badge_colour = _SOURCE_BADGES.get(
            ds.source_type, ("???", "#6B7280"))
        self.badge.setText(badge_text)
        self.badge.setStyleSheet(
            f"QLabel {{ background-color: {badge_colour}; color: white;"
            f" border-radius: 3px; padding: 0px; }}")

    # ── Drag support ─────────────────────────────────────────────────

    def mousePressEvent(self, ev):
        if ev.button() == Qt.MouseButton.LeftButton:
            self._drag_start = ev.pos()
        super().mousePressEvent(ev)

    def mouseMoveEvent(self, ev):
        if (self._drag_start is not None
                and (ev.pos() - self._drag_start).manhattanLength() > 10):
            drag = QDrag(self)
            mime = QMimeData()
            mime.setData(DATASET_DRAG_MIME,
                         self.dataset.id.encode("utf-8"))
            drag.setMimeData(mime)
            self.setCursor(Qt.CursorShape.ClosedHandCursor)
            drag.exec(Qt.DropAction.CopyAction)
            self.setCursor(Qt.CursorShape.OpenHandCursor)
            self._drag_start = None
        super().mouseMoveEvent(ev)

    def mouseReleaseEvent(self, ev):
        self._drag_start = None
        super().mouseReleaseEvent(ev)
