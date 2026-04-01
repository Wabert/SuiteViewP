"""
Message Inbox Widget — compact one-line-per-message popup.

Each row:  date/time  From  filename(clickable)  [✕ remove]

Unread items have a bright blue background + bold text.
Read items have a muted background + normal text.
Opening a file auto-marks the message as read.
"""
from __future__ import annotations

import json
import logging
import time
from datetime import datetime
from pathlib import Path

from PyQt6.QtCore import Qt, pyqtSignal, QPoint
from PyQt6.QtGui import QFont
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QScrollArea, QFrame, QSizePolicy, QMenu,
)

from .message_service import Message

logger = logging.getLogger(__name__)

_WIDTH_FILE = Path.home() / ".suiteview" / "inbox_width.json"

_FONT = QFont("Segoe UI", 9)
_FONT_BOLD = QFont("Segoe UI", 9, QFont.Weight.Bold)
_FONT_SM = QFont("Segoe UI", 8)

# ── Compact button style ────────────────────────────────────────────
_BTN_STYLE = """
    QPushButton {
        background: #2A6FBF; color: white;
        border: 1px solid #4A90D9; border-radius: 2px;
        padding: 0 6px; font-size: 8pt;
    }
    QPushButton:hover { background: #3A8FDF; }
"""
_REMOVE_STYLE = """
    QPushButton {
        background: transparent; color: #FF6666;
        border: none; font-weight: bold; font-size: 11px;
    }
    QPushButton:hover { color: #FF2222; background: rgba(255,50,50,0.15); border-radius: 2px; }
"""
_FILE_LINK_STYLE = """
    QPushButton {
        background: transparent; color: white;
        border: none; text-align: left; padding: 0;
        font-size: 9pt;
    }
    QPushButton:hover { color: #5AAFFF; text-decoration: underline; }
"""
_FILE_LINK_READ_STYLE = """
    QPushButton {
        background: transparent; color: #8899AA;
        border: none; text-align: left; padding: 0;
        font-size: 9pt;
    }
    QPushButton:hover { color: #5AAFFF; text-decoration: underline; }
"""

# ── Card background styles ──────────────────────────────────────────
_UNREAD_STYLE = """
    MessageCard {
        background: #1A4A7A;
        border: 1px solid #3A8FDF;
        border-left: 3px solid #5AAFFF;
        border-radius: 3px;
        margin: 1px 0;
    }
"""
_READ_STYLE = """
    MessageCard {
        background: #0F2E52;
        border: 1px solid #1A3A5A;
        border-left: 3px solid #1A3A5A;
        border-radius: 3px;
        margin: 1px 0;
    }
"""


class MessageCard(QFrame):
    """Single message row — compact one-liner layout."""

    open_requested = pyqtSignal(str)        # file path
    folder_requested = pyqtSignal(str)      # file path (navigate in FileNav)
    dismiss_requested = pyqtSignal(object)  # Message object

    def __init__(self, msg: Message, is_read: bool = False, parent=None):
        super().__init__(parent)
        self.msg = msg
        self._is_read = is_read
        self.setFrameShape(QFrame.Shape.NoFrame)
        self.setFixedHeight(28)

        row = QHBoxLayout(self)
        row.setContentsMargins(4, 2, 4, 2)
        row.setSpacing(4)

        # Date/time
        ts_text = ""
        if msg.timestamp:
            try:
                dt = datetime.fromisoformat(msg.timestamp)
                ts_text = dt.strftime("%m/%d %I:%M%p").replace("AM", "am").replace("PM", "pm")
            except Exception:
                ts_text = msg.timestamp[:10]
        ts_lbl = QLabel(ts_text)
        ts_lbl.setFont(_FONT_SM)
        ts_lbl.setStyleSheet("color: #AABBCC; background: transparent;")
        ts_lbl.setFixedWidth(72)
        ts_lbl.setToolTip(msg.timestamp)
        row.addWidget(ts_lbl)

        # Sender
        sender = msg.sender_display or msg.sender
        sender_lbl = QLabel(sender)
        sender_lbl.setStyleSheet("color: #FFD700; background: transparent;")
        sender_lbl.setFixedWidth(60)
        sender_lbl.setToolTip(f"From: {sender}")
        row.addWidget(sender_lbl)
        self._sender_lbl = sender_lbl

        # Filename — clickable link that opens the file
        fname = Path(msg.path).name if msg.path else "(no file)"
        self._file_btn = QPushButton(fname)
        self._file_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._file_btn.setToolTip(msg.path)
        self._file_btn.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        self._file_btn.clicked.connect(self._on_open)
        self._file_btn.setContextMenuPolicy(
            Qt.ContextMenuPolicy.CustomContextMenu)
        self._file_btn.customContextMenuRequested.connect(
            self._show_file_context_menu)
        row.addWidget(self._file_btn)

        # Remove ✕ button
        remove_btn = QPushButton("✕")
        remove_btn.setFixedSize(20, 20)
        remove_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        remove_btn.setStyleSheet(_REMOVE_STYLE)
        remove_btn.setToolTip("Remove")
        remove_btn.clicked.connect(lambda: self.dismiss_requested.emit(msg))
        row.addWidget(remove_btn)

        # Apply initial visual state
        self._apply_style()

    @property
    def is_read(self) -> bool:
        return self._is_read

    def _on_open(self):
        """Open file and auto-mark as read."""
        if not self._is_read:
            self._is_read = True
            self._apply_style()
        self.open_requested.emit(self.msg.path)

    def _show_file_context_menu(self, pos):
        """Right-click menu on the file link."""
        menu = QMenu(self)
        menu.setStyleSheet(
            "QMenu { background: #1A3A6E; color: white; border: 1px solid #3A8FDF; }"
            "QMenu::item:selected { background: #2A6FBF; }")
        action = menu.addAction("Open in Folder")
        chosen = menu.exec(self._file_btn.mapToGlobal(pos))
        if chosen == action:
            self.folder_requested.emit(self.msg.path)

    def _apply_style(self):
        if self._is_read:
            self.setStyleSheet(_READ_STYLE)
            self._sender_lbl.setFont(_FONT)
            self._file_btn.setFont(_FONT)
            self._file_btn.setStyleSheet(_FILE_LINK_READ_STYLE)
        else:
            self.setStyleSheet(_UNREAD_STYLE)
            self._sender_lbl.setFont(_FONT_BOLD)
            self._file_btn.setFont(_FONT_BOLD)
            self._file_btn.setStyleSheet(_FILE_LINK_STYLE)


class MessageInbox(QFrame):
    """Dropdown popup showing all messages as compact one-liners."""

    open_file = pyqtSignal(str)             # request to open a file path
    navigate_to = pyqtSignal(str)           # request to navigate File Nav
    message_dismissed = pyqtSignal(object)  # Message acknowledged

    _DRAG_MARGIN = 6  # pixels from left/right edge to trigger resize

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowFlags(
            Qt.WindowType.Popup | Qt.WindowType.FramelessWindowHint)
        self._saved_width = self._load_width()
        self.setFixedWidth(self._saved_width)
        self.setMaximumHeight(360)
        self.setStyleSheet("""
            MessageInbox {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    stop:0 #0D3A7A, stop:1 #082B5C);
                border: 2px solid #D4A017;
                border-radius: 6px;
            }
        """)
        self.setMouseTracking(True)
        self._resizing = False
        self._resize_edge = None  # 'left' or 'right'
        self._resize_start_x = 0
        self._resize_start_w = 0
        self._resize_start_pos = QPoint()

        outer = QVBoxLayout(self)
        outer.setContentsMargins(6, 6, 6, 6)
        outer.setSpacing(3)

        # Title
        title = QLabel("📨  Messages")
        title.setFont(QFont("Segoe UI", 10, QFont.Weight.Bold))
        title.setStyleSheet("color: #FFD700; background: transparent;")
        outer.addWidget(title)

        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setStyleSheet("color: #D4A017; background: transparent;")
        sep.setFixedHeight(1)
        outer.addWidget(sep)

        # Scrollable message area
        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(True)
        self._scroll.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._scroll.setStyleSheet("""
            QScrollArea { border: none; background: transparent; }
            QScrollBar:vertical {
                width: 6px; background: transparent;
            }
            QScrollBar::handle:vertical {
                background: #D4A017; border-radius: 3px; min-height: 20px;
            }
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
                height: 0px;
            }
        """)

        self._container = QWidget()
        self._container.setStyleSheet("background: transparent;")
        self._card_layout = QVBoxLayout(self._container)
        self._card_layout.setContentsMargins(0, 0, 0, 0)
        self._card_layout.setSpacing(2)
        self._card_layout.addStretch()

        self._scroll.setWidget(self._container)
        outer.addWidget(self._scroll, 1)

        # Empty-state label
        self._empty_label = QLabel("No messages")
        self._empty_label.setFont(_FONT)
        self._empty_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._empty_label.setStyleSheet(
            "color: #888; background: transparent; padding: 20px;")
        self._card_layout.insertWidget(0, self._empty_label)

        self._cards: list[MessageCard] = []
        self._last_hide_time: float = 0.0

    def add_messages(self, messages: list[Message], is_read: bool = False):
        """Add one or more new messages to the inbox."""
        self._empty_label.hide()
        for msg in messages:
            card = MessageCard(msg, is_read=is_read)
            card.open_requested.connect(self.open_file.emit)
            card.folder_requested.connect(self.navigate_to.emit)
            card.dismiss_requested.connect(self._dismiss_card)
            self._cards.append(card)
            # Insert above the stretch
            self._card_layout.insertWidget(
                self._card_layout.count() - 1, card)
        self.adjustSize()

    @property
    def count(self) -> int:
        return len(self._cards)

    @property
    def unread_count(self) -> int:
        return sum(1 for c in self._cards if not c.is_read)

    def _dismiss_card(self, msg: Message):
        """Remove a card and emit the dismiss signal."""
        for card in self._cards:
            if card.msg is msg:
                self._cards.remove(card)
                card.setParent(None)
                card.deleteLater()
                break
        self.message_dismissed.emit(msg)
        if not self._cards:
            self._empty_label.show()
        self.adjustSize()

    def clear(self):
        for card in self._cards:
            card.setParent(None)
            card.deleteLater()
        self._cards.clear()
        self._empty_label.show()

    # ── Resizable width via edge drag ────────────────────────────

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            edge = self._hit_edge(event.position().toPoint())
            if edge:
                self._resizing = True
                self._resize_edge = edge
                self._resize_start_x = event.globalPosition().toPoint().x()
                self._resize_start_w = self.width()
                self._resize_start_pos = self.pos()
                event.accept()
                return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self._resizing:
            dx = event.globalPosition().toPoint().x() - self._resize_start_x
            if self._resize_edge == 'right':
                new_w = max(300, self._resize_start_w + dx)
            else:  # left
                new_w = max(300, self._resize_start_w - dx)
            self.setFixedWidth(new_w)
            if self._resize_edge == 'left':
                self.move(self._resize_start_pos.x() + (self._resize_start_w - new_w),
                          self.pos().y())
            event.accept()
            return
        # Change cursor near edges
        edge = self._hit_edge(event.position().toPoint())
        if edge:
            self.setCursor(Qt.CursorShape.SizeHorCursor)
        else:
            self.unsetCursor()
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if self._resizing:
            self._resizing = False
            self._resize_edge = None
            self._save_width(self.width())
            event.accept()
            return
        super().mouseReleaseEvent(event)

    def _hit_edge(self, pos: QPoint) -> str | None:
        m = self._DRAG_MARGIN
        if pos.x() <= m:
            return 'left'
        if pos.x() >= self.width() - m:
            return 'right'
        return None

    @staticmethod
    def _load_width() -> int:
        try:
            data = json.loads(_WIDTH_FILE.read_text(encoding='utf-8'))
            w = int(data.get('width', 480))
            return max(300, min(w, 1200))
        except Exception:
            return 480

    @staticmethod
    def _save_width(w: int):
        try:
            _WIDTH_FILE.parent.mkdir(parents=True, exist_ok=True)
            _WIDTH_FILE.write_text(
                json.dumps({'width': w}), encoding='utf-8')
        except Exception:
            pass

    @property
    def recently_closed(self) -> bool:
        """True if the popup was hidden less than 300ms ago."""
        return (time.monotonic() - self._last_hide_time) < 0.3

    def hideEvent(self, event):
        self._last_hide_time = time.monotonic()
        super().hideEvent(event)
