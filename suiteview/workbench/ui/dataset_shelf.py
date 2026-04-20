"""
DatasetShelf — collapsible sidebar listing all pinned datasets as cards.

Provides search, memory usage footer, and preview/refresh/delete actions.
Cards are draggable onto the Workbench canvas.
"""
from __future__ import annotations

import logging

import pandas as pd
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QFont
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
    QPushButton, QScrollArea, QFrame, QMessageBox,
)

from suiteview.workbench.models import PinnedDataset
from suiteview.workbench import dataset_store as store
from suiteview.workbench.ui.dataset_card import DatasetCard

logger = logging.getLogger(__name__)

_FONT = QFont("Segoe UI", 9)


class DatasetShelf(QWidget):
    """Scrollable panel showing all pinned datasets as cards."""

    # Emitted when user clicks Preview on a card
    preview_requested = pyqtSignal(object)  # PinnedDataset (with df loaded)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._cards: dict[str, DatasetCard] = {}   # id → card
        self._datasets: dict[str, PinnedDataset] = {}  # id → model
        self._build_ui()
        self.reload()

    def _build_ui(self):
        self.setMinimumWidth(220)
        self.setMaximumWidth(280)

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # ── Header ───────────────────────────────────────────────────
        header = QLabel("  📦  PINNED DATASETS")
        header.setFixedHeight(28)
        header.setFont(QFont("Segoe UI", 10, QFont.Weight.Bold))
        header.setAlignment(Qt.AlignmentFlag.AlignVCenter)
        header.setStyleSheet(
            "QLabel { background: qlineargradient(x1:0,y1:0,x2:1,y2:0,"
            " stop:0 #0D9488, stop:1 #14B8A6);"
            " color: white; padding-left: 4px; letter-spacing: 1px; }")
        root.addWidget(header)

        # ── Search ───────────────────────────────────────────────────
        self.search = QLineEdit()
        self.search.setPlaceholderText("🔍 Search datasets…")
        self.search.setFont(QFont("Segoe UI", 9))
        self.search.setFixedHeight(24)
        self.search.setStyleSheet(
            "QLineEdit { padding: 3px 6px; margin: 4px 4px 2px 4px;"
            " font-size: 11px; border: 1px solid #B0C8E8;"
            " border-radius: 3px; background: white; }")
        self.search.textChanged.connect(self._apply_filter)
        root.addWidget(self.search)

        # ── Separator ────────────────────────────────────────────────
        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setFixedHeight(1)
        sep.setStyleSheet("background-color: #B0C8E8;")
        root.addWidget(sep)

        # ── Scrollable card list ─────────────────────────────────────
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setStyleSheet(
            "QScrollArea { border: none; background: #F0F6FF; }")

        self._card_container = QWidget()
        self._card_container.setStyleSheet("background: #F0F6FF;")
        self._card_layout = QVBoxLayout(self._card_container)
        self._card_layout.setContentsMargins(4, 4, 4, 4)
        self._card_layout.setSpacing(4)
        self._card_layout.addStretch()

        scroll.setWidget(self._card_container)
        root.addWidget(scroll, 1)

        # ── Memory footer ────────────────────────────────────────────
        self.lbl_memory = QLabel()
        self.lbl_memory.setFixedHeight(22)
        self.lbl_memory.setFont(QFont("Segoe UI", 8, QFont.Weight.Bold))
        self.lbl_memory.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_memory.setStyleSheet(
            "QLabel { background-color: #E0F2F1; color: #0D9488;"
            " padding: 2px 6px; border-top: 1px solid #B0C8E8; }")
        root.addWidget(self.lbl_memory)

        self._update_memory_label()

    # ── Public API ───────────────────────────────────────────────────

    def reload(self):
        """Reload all datasets from disk and rebuild cards."""
        # Clear existing cards
        for card in self._cards.values():
            card.setParent(None)
            card.deleteLater()
        self._cards.clear()
        self._datasets.clear()

        datasets = store.list_datasets()
        # Sort newest first
        datasets.sort(key=lambda d: d.created_at, reverse=True)

        for ds in datasets:
            self._add_card(ds)

        self._update_memory_label()

    def add_dataset(self, ds: PinnedDataset):
        """Add a newly pinned dataset to the shelf (without full reload)."""
        self._add_card(ds, at_top=True)
        self._update_memory_label()

    # ── Internal ─────────────────────────────────────────────────────

    def _add_card(self, ds: PinnedDataset, at_top: bool = False):
        card = DatasetCard(ds)
        card.preview_requested.connect(self._on_preview)
        card.refresh_requested.connect(self._on_refresh)
        card.delete_requested.connect(self._on_delete)

        self._cards[ds.id] = card
        self._datasets[ds.id] = ds

        if at_top:
            self._card_layout.insertWidget(0, card)
        else:
            # Insert before the trailing stretch
            idx = max(0, self._card_layout.count() - 1)
            self._card_layout.insertWidget(idx, card)

    def _apply_filter(self, text: str):
        text = text.lower().strip()
        for ds_id, card in self._cards.items():
            ds = self._datasets[ds_id]
            visible = (not text
                       or text in ds.name.lower()
                       or text in ds.source_label.lower()
                       or text in ds.source_type.lower())
            card.setVisible(visible)

    def _update_memory_label(self):
        mb = store.get_total_memory_mb()
        count = len(self._cards)
        self.lbl_memory.setText(
            f"{count} dataset{'s' if count != 1 else ''} · {mb:.1f} MB on disk")

    # ── Card actions ─────────────────────────────────────────────────

    def _on_preview(self, dataset_id: str):
        ds = self._datasets.get(dataset_id)
        if ds is None:
            return
        try:
            if not ds.is_loaded():
                store.load_dataframe(ds)
            self.preview_requested.emit(ds)
        except Exception as exc:
            logger.exception("Failed to load dataset for preview")
            QMessageBox.warning(
                self, "Load Error",
                f"Could not load dataset:\n{exc}")

    def _on_refresh(self, dataset_id: str):
        """Placeholder — re-executes source SQL in the future."""
        QMessageBox.information(
            self, "Refresh",
            "Re-query from source is not yet implemented.\n"
            "Pin the results again from the Audit tool to update.")

    def _on_delete(self, dataset_id: str):
        ds = self._datasets.get(dataset_id)
        if ds is None:
            return
        reply = QMessageBox.question(
            self, "Delete Dataset",
            f"Delete \"{ds.name}\"?\n\nThis cannot be undone.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return

        store.delete_dataset(dataset_id)
        card = self._cards.pop(dataset_id, None)
        if card:
            card.setParent(None)
            card.deleteLater()
        self._datasets.pop(dataset_id, None)
        self._update_memory_label()
