"""
Attachment Drop Zone Widget - Drag-and-drop file attachment area for Task Tracker

Supports:
  - Drag files from OS file explorer
  - Toggle between Copy (saves a local copy) and Link (stores path reference only)
  - Display list of attached files with remove buttons
"""

import os
import logging
from typing import List

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QDragEnterEvent, QDropEvent
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QListWidget,
    QListWidgetItem, QPushButton, QAbstractItemView,
)

logger = logging.getLogger(__name__)


class AttachmentDropZone(QWidget):
    """Widget that accepts file drops and tracks attached files."""

    attachment_added = pyqtSignal(str)      # emits file path
    attachment_removed = pyqtSignal(int)    # emits index

    def __init__(self, parent=None):
        super().__init__(parent)
        self._is_copy_mode = False  # Default: Link mode
        self._init_ui()
        self.setAcceptDrops(True)

    # ── UI setup ────────────────────────────────────────────────────

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)

        # Header row: label + toggle button
        header = QHBoxLayout()
        header.setContentsMargins(0, 0, 0, 0)
        lbl = QLabel("📎 Attachments")
        lbl.setStyleSheet("font-weight: bold; font-size: 12px; color: #333;")
        header.addWidget(lbl)
        header.addStretch()

        self.toggle_btn = QPushButton("🔗 Link")
        self.toggle_btn.setToolTip(
            "Link mode: stores a reference to the original file.\n"
            "Click to switch to Copy mode."
        )
        self.toggle_btn.setFixedWidth(90)
        self.toggle_btn.setStyleSheet("""
            QPushButton {
                background: #E8F0FF;
                border: 1px solid #1E3A8A;
                border-radius: 3px;
                padding: 3px 8px;
                font-size: 11px;
            }
            QPushButton:hover { background: #D0E0FF; }
        """)
        self.toggle_btn.clicked.connect(self._toggle_mode)
        header.addWidget(self.toggle_btn)

        layout.addLayout(header)

        # List of attached files
        self.file_list = QListWidget()
        self.file_list.setMinimumHeight(60)
        self.file_list.setMaximumHeight(120)
        self.file_list.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.file_list.setStyleSheet("""
            QListWidget {
                background: #FAFAFA;
                border: 2px dashed #B0B0B0;
                border-radius: 4px;
                font-size: 11px;
            }
            QListWidget::item { padding: 3px 6px; }
            QListWidget::item:selected { background: #D0E0FF; }
        """)
        layout.addWidget(self.file_list)

        # Drop hint (shown when list is empty)
        self.hint_label = QLabel("  Drag files here to attach")
        self.hint_label.setStyleSheet("color: #999; font-size: 11px; font-style: italic;")
        self.hint_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.hint_label)

        # Remove button
        btn_row = QHBoxLayout()
        btn_row.addStretch()
        self.remove_btn = QPushButton("✕ Remove Selected")
        self.remove_btn.setFixedWidth(130)
        self.remove_btn.setStyleSheet("""
            QPushButton {
                background: transparent;
                border: 1px solid #DC3545;
                color: #DC3545;
                border-radius: 3px;
                padding: 2px 8px;
                font-size: 11px;
            }
            QPushButton:hover { background: #FFF0F0; }
        """)
        self.remove_btn.clicked.connect(self._remove_selected)
        btn_row.addWidget(self.remove_btn)
        layout.addLayout(btn_row)

        self._update_hint_visibility()

    # ── Public API ──────────────────────────────────────────────────

    @property
    def is_copy_mode(self) -> bool:
        return self._is_copy_mode

    def add_file(self, file_path: str):
        """Add a file to the attachment list."""
        file_path = file_path.strip()
        if not file_path:
            return
        name = os.path.basename(file_path)
        icon = "📄" if self._is_copy_mode else "🔗"
        item = QListWidgetItem(f"{icon}  {name}")
        item.setData(Qt.ItemDataRole.UserRole, file_path)
        item.setData(Qt.ItemDataRole.UserRole + 1, self._is_copy_mode)
        self.file_list.addItem(item)
        self._update_hint_visibility()
        self.attachment_added.emit(file_path)
        logger.info(f"Attached {'(copy)' if self._is_copy_mode else '(link)'}: {file_path}")

    def remove_file(self, index: int):
        """Remove attachment at index."""
        if 0 <= index < self.file_list.count():
            self.file_list.takeItem(index)
            self._update_hint_visibility()
            self.attachment_removed.emit(index)

    def get_attachments(self) -> List[dict]:
        """Return list of {'file_path': str, 'file_name': str, 'is_copy': bool}."""
        result = []
        for i in range(self.file_list.count()):
            item = self.file_list.item(i)
            result.append({
                'file_path': item.data(Qt.ItemDataRole.UserRole),
                'file_name': os.path.basename(item.data(Qt.ItemDataRole.UserRole)),
                'is_copy': item.data(Qt.ItemDataRole.UserRole + 1),
            })
        return result

    def clear(self):
        """Remove all attachments."""
        self.file_list.clear()
        self._update_hint_visibility()

    # ── Drag-and-drop ───────────────────────────────────────────────

    def dragEnterEvent(self, event: QDragEnterEvent):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
            self.file_list.setStyleSheet(self.file_list.styleSheet().replace(
                "border: 2px dashed #B0B0B0", "border: 2px solid #1E3A8A"
            ))
        else:
            event.ignore()

    def dragLeaveEvent(self, event):
        self.file_list.setStyleSheet(self.file_list.styleSheet().replace(
            "border: 2px solid #1E3A8A", "border: 2px dashed #B0B0B0"
        ))

    def dropEvent(self, event: QDropEvent):
        self.file_list.setStyleSheet(self.file_list.styleSheet().replace(
            "border: 2px solid #1E3A8A", "border: 2px dashed #B0B0B0"
        ))
        if event.mimeData().hasUrls():
            for url in event.mimeData().urls():
                path = url.toLocalFile()
                if path:
                    self.add_file(path)
            event.acceptProposedAction()

    # ── Internal ────────────────────────────────────────────────────

    def _toggle_mode(self):
        self._is_copy_mode = not self._is_copy_mode
        if self._is_copy_mode:
            self.toggle_btn.setText("📁 Copy")
            self.toggle_btn.setToolTip(
                "Copy mode: saves a copy of the file locally.\n"
                "Click to switch to Link mode."
            )
        else:
            self.toggle_btn.setText("🔗 Link")
            self.toggle_btn.setToolTip(
                "Link mode: stores a reference to the original file.\n"
                "Click to switch to Copy mode."
            )

    def _remove_selected(self):
        row = self.file_list.currentRow()
        if row >= 0:
            self.remove_file(row)

    def _update_hint_visibility(self):
        has_items = self.file_list.count() > 0
        self.hint_label.setVisible(not has_items)
        self.remove_btn.setVisible(has_items)
