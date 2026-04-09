"""
File Open History Panel — reads Windows Recent Items to show files and folders opened
across ALL applications (Office, Notepad++, VS Code, etc.) over the last 30 days.

Displays 3 columns filled top-to-bottom, oldest at top-left, newest at bottom-right.
"""

import os
import sys
import logging
from pathlib import Path
from datetime import datetime, timedelta
from collections import defaultdict

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QScrollArea,
    QFrame, QToolButton, QPushButton, QSizePolicy, QToolTip, QMenu,
    QLineEdit, QFileIconProvider, QApplication,
)
from PyQt6.QtCore import Qt, pyqtSignal, QSize, QEvent, QTimer, QPoint, QFileInfo
from PyQt6.QtGui import QFont, QColor, QCursor, QPalette, QFontMetrics, QAction, QIcon, QPixmap

logger = logging.getLogger(__name__)

# Extensions we care about (common work files)
TRACKED_EXTENSIONS = {
    # Microsoft Office
    '.xlsx', '.xls', '.xlsm', '.xlsb', '.xltx', '.xltm',
    '.docx', '.doc', '.docm', '.dotx',
    '.pptx', '.ppt', '.pptm',
    '.accdb', '.mdb',
    '.vsdx', '.vsd',
    '.msg', '.eml',
    # Text / Code
    '.txt', '.csv', '.tsv', '.log', '.md', '.json', '.xml', '.yaml', '.yml',
    '.py', '.js', '.ts', '.html', '.css', '.sql', '.bat', '.ps1', '.sh',
    '.ini', '.cfg', '.conf', '.toml',
    # PDF / Images
    '.pdf',
    '.png', '.jpg', '.jpeg', '.gif', '.bmp', '.tiff', '.svg',
    # Archives
    '.zip', '.7z', '.rar',
}

DAY_NAMES = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun']


def _get_recent_files(days=7):
    """
    Scan Windows Recent Items folder and return a dict:
        { date_str: [ (filename, full_target_path, timestamp), ... ] }
    grouped by calendar day for the last `days` days.
    """
    recent_dir = Path(os.environ.get('APPDATA', '')) / 'Microsoft' / 'Windows' / 'Recent'
    if not recent_dir.is_dir():
        return {}

    cutoff = datetime.now() - timedelta(days=days)
    by_day = defaultdict(list)

    # Try using win32com for fast shortcut resolution
    shell = None
    try:
        import win32com.client
        shell = win32com.client.Dispatch("WScript.Shell")
    except Exception:
        pass

    for lnk in recent_dir.iterdir():
        if lnk.suffix.lower() != '.lnk':
            continue
        try:
            mtime = datetime.fromtimestamp(lnk.stat().st_mtime)
        except OSError:
            continue
        if mtime < cutoff:
            continue

        # Resolve the shortcut target
        target = None
        if shell:
            try:
                sc = shell.CreateShortCut(str(lnk))
                target = sc.Targetpath
            except Exception:
                pass

        if not target:
            # Derive from .lnk filename as a fallback (strip trailing .lnk)
            target = lnk.stem  # e.g. "report.xlsx"

        target_path = Path(target) if target else None

        # Determine if it looks like a folder
        is_folder = bool(target_path and target_path.is_dir())

        # Filter by extension (folders pass through without extension check)
        if not is_folder:
            ext = target_path.suffix.lower() if target_path else ''
            if ext not in TRACKED_EXTENSIONS:
                continue

        day_key = mtime.strftime('%Y-%m-%d')
        display_name = target_path.name if target_path else lnk.stem
        # Keep the full path even if the file isn't locally cached
        # (OneDrive on-demand files aren't on disk but os.startfile handles them)
        full_path = str(target_path) if target_path and len(target_path.parts) > 1 else ''
        by_day[day_key].append((display_name, full_path, mtime, is_folder))

    # Sort each day's entries by time ascending (oldest first at top, newest at bottom)
    for day in by_day:
        by_day[day].sort(key=lambda x: x[2], reverse=False)

    return dict(by_day)


# ── Cache for previous days (they never change) ──
_day_cache = {}       # { 'YYYY-MM-DD': [ (name, path, datetime), ... ] }
_cache_date = None    # date when cache was last built


def get_recent_files_cached(days=7):
    """Return recent files with caching for past days.
    
    Only today's column is rescanned each time. Previous days are
    served from an in-memory cache that persists for the session.
    """
    global _day_cache, _cache_date

    today = datetime.now().date()
    today_key = today.strftime('%Y-%m-%d')

    # If the calendar day rolled over, invalidate the whole cache
    if _cache_date != today:
        _day_cache.clear()
        _cache_date = today

    # Figure out which days we still need to scan
    needed_days = set()
    for offset in range(days):
        day = today - timedelta(days=offset)
        day_key = day.strftime('%Y-%m-%d')
        if day_key == today_key or day_key not in _day_cache:
            needed_days.add(day_key)

    if needed_days:
        # Only scan .lnk files whose mtime falls in a needed day
        fresh = _scan_recent_for_days(needed_days, days)
        _day_cache.update(fresh)
        # Ensure days with no files still get cached (so we don't rescan)
        for dk in needed_days:
            if dk not in _day_cache:
                _day_cache[dk] = []

    # Return only the last `days` worth
    result = {}
    for offset in range(days):
        day = today - timedelta(days=offset)
        day_key = day.strftime('%Y-%m-%d')
        if day_key in _day_cache:
            result[day_key] = _day_cache[day_key]
    return result


def _scan_recent_for_days(needed_day_keys, max_days=7):
    """Scan Windows Recent Items but only process .lnk files whose date is in needed_day_keys."""
    recent_dir = Path(os.environ.get('APPDATA', '')) / 'Microsoft' / 'Windows' / 'Recent'
    if not recent_dir.is_dir():
        return {}

    cutoff = datetime.now() - timedelta(days=max_days)
    by_day = defaultdict(list)

    shell = None
    try:
        import win32com.client
        shell = win32com.client.Dispatch("WScript.Shell")
    except Exception:
        pass

    for lnk in recent_dir.iterdir():
        if lnk.suffix.lower() != '.lnk':
            continue
        try:
            mtime = datetime.fromtimestamp(lnk.stat().st_mtime)
        except OSError:
            continue
        if mtime < cutoff:
            continue

        day_key = mtime.strftime('%Y-%m-%d')
        if day_key not in needed_day_keys:
            continue

        target = None
        if shell:
            try:
                sc = shell.CreateShortCut(str(lnk))
                target = sc.Targetpath
            except Exception:
                pass

        if not target:
            target = lnk.stem

        target_path = Path(target) if target else None

        # Determine if it looks like a folder
        is_folder = bool(target_path and target_path.is_dir())

        # Filter by extension (folders pass through without extension check)
        if not is_folder:
            ext = target_path.suffix.lower() if target_path else ''
            if ext not in TRACKED_EXTENSIONS:
                continue

        display_name = target_path.name if target_path else lnk.stem
        # Keep the full path even if the file isn't locally cached
        # (OneDrive on-demand files aren't on disk but os.startfile handles them)
        full_path = str(target_path) if target_path and len(target_path.parts) > 1 else ''
        by_day[day_key].append((display_name, full_path, mtime, is_folder))

    for day in by_day:
        by_day[day].sort(key=lambda x: x[2], reverse=False)

    return dict(by_day)


class FileOpenHistoryPanel(QWidget):
    """
    A panel that shows 3 columns of recently opened files (last 7 days),
    filled top-to-bottom with oldest at top-left and newest at bottom-right.
    """

    file_requested = pyqtSignal(str)  # emitted with full path when user clicks a file
    _session_width = None  # persists across show/hide within the same process

    _RESIZE_MARGIN = 10  # pixels from left/right edge that trigger resize cursor
    _icon_provider = None  # shared QFileIconProvider instance

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowFlags(
            Qt.WindowType.Tool
            | Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
        )
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setMouseTracking(True)
        self._last_hide_ms = 0  # track when popup was last hidden for toggle logic
        self._resizing = False
        self._resize_edge = None  # 'left' or 'right'
        self._resize_start_x = 0
        self._resize_start_w = 0
        self._resize_start_left = 0
        self._file_buttons = []  # list of (QPushButton, display_name) for search highlighting
        self._build_ui()
        self._build_custom_tooltip()

    def hideEvent(self, event):
        """Track hide time so toggle can distinguish user-click from auto-close."""
        import time
        self._last_hide_ms = int(time.time() * 1000)
        self._tip.hide()
        self._tip_timer.stop()
        super().hideEvent(event)

    def changeEvent(self, event):
        """Auto-hide when the panel loses focus (mimics Popup close-on-outside-click)."""
        if event.type() == QEvent.Type.WindowDeactivate and not self._resizing:
            self.hide()
        super().changeEvent(event)

    def was_recently_hidden(self, threshold_ms=300):
        """Return True if the panel was hidden within the last threshold_ms."""
        import time
        now_ms = int(time.time() * 1000)
        return (now_ms - self._last_hide_ms) < threshold_ms

    def _build_ui(self):
        self.setStyleSheet("""
            FileOpenHistoryPanel {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    stop:0 #1A4A8A, stop:1 #0D3060);
                border: 2px solid #D4A017;
                border-radius: 6px;
            }
        """)

        root = QVBoxLayout(self)
        root.setContentsMargins(10, 8, 10, 10)
        root.setSpacing(6)

        # ── Header row ──
        hdr = QHBoxLayout()
        hdr.setContentsMargins(0, 0, 0, 0)
        self._title_label = QLabel("File Open History")
        self._title_label.setStyleSheet(
            "color: #FFD700; font-size: 14px; font-weight: bold; "
            "background: transparent; border: none;"
        )
        hdr.addWidget(self._title_label)
        hdr.addStretch()

        close_btn = QToolButton()
        close_btn.setText("✕")
        close_btn.setFixedSize(22, 22)
        close_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        close_btn.setStyleSheet("""
            QToolButton {
                background: transparent; border: none;
                color: #D4A017; font-size: 14px; font-weight: bold;
            }
            QToolButton:hover { color: #FF4444; }
        """)
        close_btn.clicked.connect(self.hide)
        hdr.addWidget(close_btn)
        root.addLayout(hdr)

        # ── Separator ──
        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setStyleSheet("background: #D4A017; max-height: 1px; border: none;")
        root.addWidget(sep)

        # ── Columns area (scroll horizontally if needed) ──
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setStyleSheet("""
            QScrollArea { background: transparent; border: none; }
            QWidget#columnsContainer { background: transparent; }
        """)

        self.columns_container = QWidget()
        self.columns_container.setObjectName("columnsContainer")
        self.columns_layout = QHBoxLayout(self.columns_container)
        self.columns_layout.setContentsMargins(0, 0, 0, 0)
        self.columns_layout.setSpacing(6)

        scroll.setWidget(self.columns_container)
        root.addWidget(scroll)

        # ── Search bar at bottom ──
        search_row = QHBoxLayout()
        search_row.setContentsMargins(0, 2, 0, 0)
        search_row.setSpacing(6)
        search_icon = QLabel("\U0001F50D")
        search_icon.setStyleSheet("background: transparent; border: none; font-size: 14px;")
        search_row.addWidget(search_icon)
        self._search_box = QLineEdit()
        self._search_box.setPlaceholderText("Search files and folders...")
        self._search_box.setClearButtonEnabled(True)
        self._search_box.setStyleSheet("""
            QLineEdit {
                background: #D6E8F8;
                color: #1A2A40;
                border: 1px solid #A0C0E0;
                border-radius: 4px;
                padding: 3px 8px;
                font-size: 12px;
                font-family: 'Segoe UI', sans-serif;
            }
            QLineEdit:focus {
                border: 1px solid #FFD700;
            }
        """)
        self._search_box.setFixedHeight(26)
        self._search_box.textChanged.connect(self._on_search_changed)
        search_row.addWidget(self._search_box)

        # Folder button to open the Windows Recent Items folder
        open_recent_btn = QToolButton()
        open_recent_btn.setText("\U0001F4C2")
        open_recent_btn.setFixedSize(26, 26)
        open_recent_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        open_recent_btn.setToolTip("Open Recent Items folder")
        open_recent_btn.setStyleSheet("""
            QToolButton {
                background: transparent; border: none;
                font-size: 16px;
            }
            QToolButton:hover { background: rgba(255, 255, 255, 0.15); border-radius: 4px; }
        """)
        open_recent_btn.clicked.connect(self._open_recent_folder)
        search_row.addWidget(open_recent_btn)

        root.addLayout(search_row)

    def _build_custom_tooltip(self):
        """Create a custom tooltip label that we position manually on hover."""
        self._tip = QLabel(self)
        self._tip.setStyleSheet("""
            QLabel {
                background-color: #FFFFF0;
                color: #1A2A40;
                border: 1px solid #A0A060;
                border-radius: 3px;
                padding: 4px 8px;
                font-size: 11px;
                font-family: 'Segoe UI', sans-serif;
            }
        """)
        self._tip.hide()
        self._tip_timer = QTimer(self)
        self._tip_timer.setSingleShot(True)
        self._tip_timer.setInterval(400)
        self._tip_timer.timeout.connect(self._show_tip)
        self._tip_path = ""
        self._tip_widget = None

    # ── Public API ──

    def refresh(self):
        """Reload data from Windows Recent Items and rebuild 3 columns."""
        import math

        # Clear old columns
        self._file_buttons.clear()
        while self.columns_layout.count():
            item = self.columns_layout.takeAt(0)
            w = item.widget()
            if w:
                w.deleteLater()

        data = get_recent_files_cached(days=30)

        # Flatten all entries into one list, deduplicate by filename
        all_entries = []
        seen = set()
        for day_key, entries in data.items():
            for display_name, full_path, timestamp, is_folder in entries:
                if display_name not in seen:
                    seen.add(display_name)
                    all_entries.append((display_name, full_path, timestamp, is_folder))

        # Sort oldest-first so oldest lands at top-left, newest at bottom-right
        all_entries.sort(key=lambda x: x[2])

        # Update title with count
        folder_count = sum(1 for e in all_entries if e[3])
        file_count = len(all_entries) - folder_count
        parts = []
        if file_count:
            parts.append(f"{file_count} file{'s' if file_count != 1 else ''}")
        if folder_count:
            parts.append(f"{folder_count} folder{'s' if folder_count != 1 else ''}")
        self._title_label.setText(f"File Open History \u2014 {', '.join(parts) or '0 items'}")

        # Distribute into 4 columns, filling top-to-bottom then left-to-right
        num_cols = 4
        total = len(all_entries)
        per_col = math.ceil(total / num_cols) if total else 0

        for c in range(num_cols):
            start = c * per_col
            end = min(start + per_col, total) if per_col else 0
            col_entries = all_entries[start:end]
            col = self._make_column(col_entries)
            self.columns_layout.addWidget(col, 1)  # equal stretch factor

    def show_under(self, button: QWidget):
        """Position with bottom edge aligned to top of the button, stretching up to top of screen."""
        self._search_box.clear()
        self.refresh()

        screen = button.screen().availableGeometry() if button.screen() else None
        if FileOpenHistoryPanel._session_width is not None:
            w = FileOpenHistoryPanel._session_width
        elif screen:
            w = min(int(screen.width() * 0.95), 1800)
        else:
            w = 1400

        # Bottom of panel aligns with top of button
        btn_top_global = button.mapToGlobal(button.rect().topRight())
        bottom_y = btn_top_global.y()  # bottom edge of panel = top of button
        x = btn_top_global.x() - w

        if screen:
            if x < screen.x():
                x = screen.x()
            top_y = screen.y() + 8  # 8px margin from top of screen
            h = bottom_y - top_y
            h = max(h, 300)
        else:
            top_y = 8
            h = bottom_y - top_y

        self.setFixedHeight(h)
        self.setMinimumWidth(400)
        self.setMaximumWidth(16777215)
        self.resize(w, h)
        self.move(x, top_y)
        self.show()
        self.activateWindow()
        self.raise_()

    # ── Edge resize handling (left and right) ──

    def _edge_at(self, pos):
        """Return 'left', 'right', or None depending on proximity to edges."""
        if pos.x() <= self._RESIZE_MARGIN:
            return 'left'
        if pos.x() >= self.width() - self._RESIZE_MARGIN:
            return 'right'
        return None

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            edge = self._edge_at(event.position().toPoint())
            if edge:
                self._resizing = True
                self._resize_edge = edge
                self._resize_start_x = event.globalPosition().toPoint().x()
                self._resize_start_w = self.width()
                self._resize_start_left = self.x()
                event.accept()
                return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        pos = event.position().toPoint()
        if self._resizing:
            dx = event.globalPosition().toPoint().x() - self._resize_start_x
            if self._resize_edge == 'left':
                new_w = self._resize_start_w - dx
                new_w = max(new_w, 400)
                actual_dx = self._resize_start_w - new_w
                new_x = self._resize_start_left + actual_dx
                self.setGeometry(new_x, self.y(), new_w, self.height())
            else:  # right
                new_w = self._resize_start_w + dx
                new_w = max(new_w, 400)
                self.resize(new_w, self.height())
            event.accept()
            return
        # Show resize cursor when hovering near edges
        if self._edge_at(pos):
            self.setCursor(Qt.CursorShape.SizeHorCursor)
        else:
            self.unsetCursor()
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if self._resizing:
            self._resizing = False
            self._resize_edge = None
            FileOpenHistoryPanel._session_width = self.width()
            self.unsetCursor()
            event.accept()
            return
        super().mouseReleaseEvent(event)

    # ── Internals ──

    def _make_column(self, entries):
        """Build a single column widget with file entries showing icon, date/time, name."""
        col = QFrame()
        col.setStyleSheet("""
            QFrame {
                background: #D6E8F8;
                border: 1px solid #A0C0E0;
                border-radius: 4px;
            }
        """)
        col.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

        layout = QVBoxLayout(col)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(2)

        # File list (no scroll — panel stretches to full height)
        list_widget = QWidget()
        list_widget.setStyleSheet("background: transparent;")
        list_layout = QVBoxLayout(list_widget)
        list_layout.setContentsMargins(2, 2, 2, 2)
        list_layout.setSpacing(1)

        # Stretch at top pushes entries to the bottom
        list_layout.addStretch()

        if not entries:
            empty = QLabel("—")
            empty.setAlignment(Qt.AlignmentFlag.AlignLeft)
            empty.setStyleSheet(
                "color: #8A9AB0; font-size: 12px; "
                "background: transparent; border: none; padding-left: 4px;"
            )
            list_layout.addWidget(empty)
        else:
            row_style = """
                background: transparent;
            """
            row_hover_ss = """
                QPushButton {
                    background: transparent;
                    border: none;
                    color: #1A2A40;
                    font-size: 12px;
                    font-family: 'Segoe UI', sans-serif;
                    text-align: left;
                    padding: 2px 0px;
                }
                QPushButton:hover {
                    color: #0D3A7A;
                }
            """
            for display_name, full_path, timestamp, is_folder in entries:
                # Row widget: [date_label] [icon_label] [name_button]
                row = QPushButton()
                row.setCursor(Qt.CursorShape.PointingHandCursor)
                row.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
                row.setStyleSheet("""
                    QPushButton {
                        background: transparent;
                        border: none;
                        color: #1A2A40;
                        font-size: 12px;
                        font-family: 'Segoe UI', sans-serif;
                        text-align: left;
                        padding: 2px 4px;
                    }
                    QPushButton:hover {
                        background: rgba(30, 91, 168, 0.15);
                        color: #0D3A7A;
                        border-radius: 2px;
                    }
                """)
                # Date + time first, then icon placeholder, then name
                date_str = timestamp.strftime('%m/%d %I:%M %p').lstrip('0')
                # Build text with spacing for the icon (icon inserted via setIcon trick below)
                row.setText(f"{date_str}  {display_name}")
                # We need the icon BETWEEN date and name. QPushButton can't do that,
                # so we use a QWidget with a layout instead.
                row.deleteLater()  # discard the button, use a composite widget

                row_widget = QWidget()
                row_widget.setStyleSheet(row_style)
                row_widget.setCursor(Qt.CursorShape.PointingHandCursor)
                row_layout = QHBoxLayout(row_widget)
                row_layout.setContentsMargins(4, 1, 4, 1)
                row_layout.setSpacing(4)

                # Date label
                date_label = QLabel(date_str)
                date_label.setStyleSheet(
                    "color: #1A2A40; font-size: 12px; font-family: 'Segoe UI', sans-serif; "
                    "background: transparent; border: none;"
                )
                date_label.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
                row_layout.addWidget(date_label)

                # Icon label
                icon = self._get_file_icon(full_path or display_name)
                icon_label = QLabel()
                icon_label.setFixedSize(18, 18)
                icon_label.setStyleSheet("background: transparent; border: none;")
                if icon and not icon.isNull():
                    icon_label.setPixmap(icon.pixmap(QSize(16, 16)))
                row_layout.addWidget(icon_label)

                # Name button (clickable part)
                name_btn = QPushButton(display_name)
                name_btn.setCursor(Qt.CursorShape.PointingHandCursor)
                name_btn.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
                name_btn.setStyleSheet(row_hover_ss)
                row_layout.addWidget(name_btn)

                # Custom tooltip on hover via event filter
                name_btn.setProperty('_tip_text', full_path or display_name)
                name_btn.installEventFilter(self)
                row_widget.setProperty('_tip_text', full_path or display_name)
                row_widget.installEventFilter(self)
                if full_path:
                    if is_folder:
                        name_btn.clicked.connect(lambda checked=False, p=full_path: self._open_folder_directly(p))
                    else:
                        name_btn.clicked.connect(lambda checked=False, p=full_path: self._open_file(p))
                    # Right-click context menu on the whole row
                    name_btn.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
                    name_btn.customContextMenuRequested.connect(
                        lambda pos, b=name_btn, p=full_path, f=is_folder: self._show_context_menu(b, pos, p, f)
                    )
                self._file_buttons.append((name_btn, display_name))
                list_layout.addWidget(row_widget)

        # Wrap in scroll area so individual columns can scroll if needed
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setStyleSheet("QScrollArea { background: transparent; border: none; }")
        scroll.setWidget(list_widget)
        layout.addWidget(scroll)

        return col

    # --- Custom tooltip logic ------------------------------------------------
    def eventFilter(self, obj, event):
        """Show/hide custom tooltip on button hover."""
        if event.type() == QEvent.Type.Enter:
            tip_text = obj.property('_tip_text')
            if tip_text:
                self._tip_path = tip_text
                self._tip_widget = obj
                self._tip_timer.start()
            return False
        if event.type() == QEvent.Type.Leave:
            self._tip_timer.stop()
            self._tip.hide()
            return False
        return super().eventFilter(obj, event)

    def _show_tip(self):
        """Position and show the custom tooltip near the hovered button."""
        if not self._tip_widget or not self._tip_path:
            return
        self._tip.setText(self._tip_path)
        self._tip.adjustSize()
        # Position just below the hovered button, within this popup
        btn_rect = self._tip_widget.geometry()
        parent_of_btn = self._tip_widget.parentWidget()
        # Map position to self (the popup)
        pos = parent_of_btn.mapTo(self, btn_rect.bottomLeft())
        # Ensure it doesn't overflow the right edge
        tip_w = self._tip.width()
        panel_w = self.width()
        x = max(4, min(pos.x(), panel_w - tip_w - 4))
        self._tip.move(x, pos.y() + 2)
        self._tip.raise_()
        self._tip.show()

    # ── Search highlighting ──────────────────────────────────────────
    _BTN_STYLE_NORMAL = """
        QPushButton {
            background: transparent;
            border: none;
            color: #1A2A40;
            font-size: 12px;
            font-family: 'Segoe UI', sans-serif;
            text-align: left;
            padding: 2px 0px;
        }
        QPushButton:hover {
            color: #0D3A7A;
        }
    """
    _BTN_STYLE_HIGHLIGHT = """
        QPushButton {
            background: rgba(220, 80, 80, 0.25);
            border: none;
            color: #1A2A40;
            font-size: 12px;
            font-family: 'Segoe UI', sans-serif;
            text-align: left;
            padding: 2px 0px;
            border-radius: 2px;
        }
        QPushButton:hover {
            background: rgba(220, 80, 80, 0.40);
            color: #0D3A7A;
        }
    """

    def _on_search_changed(self, text: str):
        """Highlight file buttons whose name contains the search string."""
        needle = text.strip().lower()
        for btn, display_name in self._file_buttons:
            if needle and needle in display_name.lower():
                btn.setStyleSheet(self._BTN_STYLE_HIGHLIGHT)
            else:
                btn.setStyleSheet(self._BTN_STYLE_NORMAL)

    # ── File icon helper ─────────────────────────────────────────────
    @classmethod
    def _get_file_icon(cls, file_path: str) -> QIcon:
        """Return the Windows shell icon for a file path or filename."""
        if cls._icon_provider is None:
            cls._icon_provider = QFileIconProvider()
        return cls._icon_provider.icon(QFileInfo(file_path))

    # -------------------------------------------------------------------------

    def _show_context_menu(self, button, pos, file_path, is_folder=False):
        """Show right-click context menu with Open Folder option."""
        menu = QMenu(self)
        menu.setMinimumWidth(220)
        menu.setStyleSheet("""
            QMenu {
                background-color: #F0F4F8;
                color: #1A2A40;
                border: 1px solid #A0C0E0;
                padding: 4px;
                font-family: 'Segoe UI';
                font-size: 12px;
            }
            QMenu::item {
                padding: 4px 16px;
            }
            QMenu::item:selected {
                background-color: #1E5BA8;
                color: white;
            }
        """)
        if is_folder:
            open_action = menu.addAction("Open Folder")
            open_parent_action = menu.addAction("Open Parent Folder")
            menu.addSeparator()
            copy_path_action = menu.addAction("Copy Folder Path")
            action = menu.exec(button.mapToGlobal(pos))
            if action == open_action:
                self._open_folder_directly(file_path)
            elif action == open_parent_action:
                self._open_folder(file_path)
            elif action == copy_path_action:
                QApplication.clipboard().setText(file_path)
        else:
            open_file_action = menu.addAction("Open File")
            open_folder_action = menu.addAction("Open Containing Folder")
            menu.addSeparator()
            copy_file_path_action = menu.addAction("Copy File Path")
            copy_folder_path_action = menu.addAction("Copy Folder Path")
            action = menu.exec(button.mapToGlobal(pos))
            if action == open_file_action:
                self._open_file(file_path)
            elif action == open_folder_action:
                self._open_folder(file_path)
            elif action == copy_file_path_action:
                QApplication.clipboard().setText(file_path)
            elif action == copy_folder_path_action:
                QApplication.clipboard().setText(str(Path(file_path).parent))

    def _open_folder(self, file_path):
        """Open the containing folder in the system file explorer, selecting the file."""
        self.hide()
        try:
            if os.name == 'nt':
                import subprocess
                subprocess.Popen(['explorer', '/select,', os.path.normpath(file_path)])
            elif sys.platform == 'darwin':
                import subprocess
                subprocess.run(['open', '-R', file_path])
            else:
                import subprocess
                folder = os.path.dirname(file_path)
                subprocess.run(['xdg-open', folder])
        except Exception as e:
            logger.error(f"Failed to open folder for: {e}")

    def _open_folder_directly(self, folder_path):
        """Open a folder directly in the system file explorer."""
        self.hide()
        try:
            if os.name == 'nt':
                os.startfile(folder_path)
            elif sys.platform == 'darwin':
                import subprocess
                subprocess.run(['open', folder_path])
            else:
                import subprocess
                subprocess.run(['xdg-open', folder_path])
        except Exception as e:
            logger.error(f"Failed to open folder from history: {e}")
        self.file_requested.emit(folder_path)

    def _open_file(self, path):
        """Open a file with the system default application."""
        self.hide()
        try:
            if os.name == 'nt':
                os.startfile(path)
            elif sys.platform == 'darwin':
                import subprocess
                subprocess.run(['open', path])
            else:
                import subprocess
                subprocess.run(['xdg-open', path])
        except Exception as e:
            logger.error(f"Failed to open file from history: {e}")
        self.file_requested.emit(path)

    def _open_recent_folder(self):
        """Open the Windows Recent Items folder in Explorer."""
        recent_dir = Path(os.environ.get('APPDATA', '')) / 'Microsoft' / 'Windows' / 'Recent'
        if recent_dir.is_dir():
            self.hide()
            try:
                os.startfile(str(recent_dir))
            except Exception as e:
                logger.error(f"Failed to open Recent Items folder: {e}")
