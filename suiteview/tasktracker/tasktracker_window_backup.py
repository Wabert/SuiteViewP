"""
TaskTracker Window — Main two-panel UI for task tracking.

Faithfully implements the design from tasktracker-mockup-reference.jsx and
TaskTracker-Developer-Spec.md using PyQt6.

Inherits frameless-window chrome from FramelessWindowBase.
"""

import logging
import re
from datetime import datetime
from typing import List, Optional, Dict

from PyQt6.QtCore import Qt, QTimer, pyqtSignal, QPoint
from PyQt6.QtGui import QFont, QColor, QCursor, QPainter, QPen, QMouseEvent
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QLineEdit, QPlainTextEdit, QFrame, QScrollArea, QSizePolicy,
    QMessageBox, QApplication, QGraphicsDropShadowEffect,
)

from suiteview.ui.widgets.frameless_window import FramelessWindowBase
from suiteview.tasktracker.constants import (
    C, FONT_FAMILY, MONO_FAMILY,
    COL_ID_WIDTH, COL_DATE_WIDTH, COL_ACTIVITY_WIDTH,
    LIST_WIDTH, DETAIL_DEFAULT_WIDTH, STATUS_OPEN, STATUS_CLOSED,
    EMAIL_SCAN_INTERVAL_MS, VERSION,
)
from suiteview.tasktracker.models import Task, Email, Contact
from suiteview.tasktracker.storage import Storage
from suiteview.tasktracker import outlook_bridge
from suiteview.tasktracker.outlook_bridge import (
    OutlookScanWorker, ContactSearchWorker,
)

logger = logging.getLogger(__name__)


# ════════════════════════════════════════════════════════════════════
#  Helper: human-readable relative time
# ════════════════════════════════════════════════════════════════════

def _relative_time(iso_date: str) -> tuple:
    """Return (display_str, sort_hours) for an ISO datetime string."""
    try:
        dt = datetime.fromisoformat(iso_date)
        delta = datetime.now() - dt
        hours = delta.total_seconds() / 3600
        if hours < 0.05:
            return ("Just now", 0)
        if hours < 1:
            return (f"{int(hours * 60)}m ago", hours)
        if hours < 24:
            return (f"{int(hours)}h ago", hours)
        days = int(hours / 24)
        return (f"{days}d ago", hours)
    except Exception:
        return ("—", 999)


# ════════════════════════════════════════════════════════════════════
#  Card colour logic  (matches JSX cardBg / cardBorder / cardBorderLeft)
# ════════════════════════════════════════════════════════════════════

def _needs_attention(task: Task) -> bool:
    return bool(task.last_activity_from and task.last_activity_from != "You")


def _card_bg(task: Task) -> str:
    if _needs_attention(task):
        return C.RED_CARD
    if task.status == STATUS_CLOSED:
        return C.CLOSED_BG
    return C.WHITE


def _card_border(task: Task, selected: bool) -> str:
    if selected:
        return C.GOLD
    if _needs_attention(task):
        return C.RED_BORDER
    return C.WHITE_TRANSLUCENT


def _card_border_left(task: Task, selected: bool) -> str:
    if selected:
        return C.GOLD
    if _needs_attention(task):
        return C.RED_DARK
    if task.status == STATUS_CLOSED:
        return C.GREEN_CLOSED_BORDER
    return C.GOLD_TRANSLUCENT


# ════════════════════════════════════════════════════════════════════
#  Task Card widget
# ════════════════════════════════════════════════════════════════════

class TaskCard(QFrame):
    """Compact 2-line card displayed in the task list."""

    clicked = pyqtSignal(str)  # task_id

    def __init__(self, task: Task, is_selected: bool = False, parent=None):
        super().__init__(parent)
        self.task = task
        self._is_selected = is_selected
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self._build()

    def _build(self):
        task = self.task
        selected = self._is_selected
        bg = _card_bg(task)
        border_col = _card_border(task, selected)
        border_left = _card_border_left(task, selected)

        sel_border = f"border: 2px solid {C.GOLD};" if selected else f"border: 1px solid {border_col};"
        self.setStyleSheet(f"""
            TaskCard {{
                background: {bg};
                {sel_border}
                border-left: 4px solid {border_left};
                border-radius: 10px;
                margin-bottom: 2px;
            }}
            TaskCard:hover {{
                background: {'#f5f0d0' if not selected else bg};
            }}
        """)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 4, 8, 4)
        layout.setSpacing(1)

        # ── Line 1: ID | Created | Activity | Assignees ────────────
        line1 = QHBoxLayout()
        line1.setSpacing(6)

        # Task ID
        tid = QLabel(task.task_id)
        tid.setStyleSheet(f"font-family: {MONO_FAMILY}; font-size: 13px; font-weight: bold; color: {C.BLUE}; background: transparent;")
        line1.addWidget(tid)

        # Created date
        date_lbl = QLabel(task.created_date)
        date_lbl.setStyleSheet(f"font-size: 13px; color: {C.TEXT}; font-weight: 600; background: transparent;")
        line1.addWidget(date_lbl)

        # Activity dot + text
        if task.email_sent:
            dot_color = C.GREEN_DOT if _needs_attention(task) else C.YELLOW_DOT
            dot = QLabel()
            dot.setFixedSize(8, 8)
            dot.setStyleSheet(f"""
                background: {dot_color};
                border-radius: 4px;
                min-width: 8px; max-width: 8px;
                min-height: 8px; max-height: 8px;
            """)
            line1.addWidget(dot)

        act_text = QLabel(task.last_activity or "—")
        act_text.setStyleSheet(f"font-size: 12px; color: {C.TEXT_MID}; background: transparent;")
        line1.addWidget(act_text)

        # Assignee chips (packed left, next to activity)
        if not task.assignees:
            dash = QLabel("—")
            dash.setStyleSheet(f"font-size: 12px; color: {C.TEXT_LIGHT}; font-style: italic; background: transparent;")
            line1.addWidget(dash)
        else:
            for a in task.assignees:
                chip = QLabel(a.name)
                chip.setStyleSheet(f"""
                    font-size: 11px; color: {C.BLUE};
                    background: rgba(232,237,246,0.95);
                    padding: 1px 6px; border-radius: 6px;
                    border: 1px solid #a0b4d4; font-weight: 600;
                """)
                line1.addWidget(chip)

        line1.addStretch()
        layout.addLayout(line1)

        # ── Line 2: Title (single line, elided) ────────────────────
        title_lbl = QLabel(task.title.replace('\n', ' '))
        title_lbl.setStyleSheet(f"font-size: 13px; color: {C.TEXT_MID}; background: transparent;")
        title_lbl.setWordWrap(False)
        title_lbl.setTextFormat(Qt.TextFormat.PlainText)
        layout.addWidget(title_lbl)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit(self.task.task_id)
        super().mousePressEvent(event)

    def enterEvent(self, event):
        pass  # hover handled by stylesheet

    def leaveEvent(self, event):
        pass  # hover handled by stylesheet


# ════════════════════════════════════════════════════════════════════
#  Section box (reusable detail panel card)
# ════════════════════════════════════════════════════════════════════

class SectionBox(QFrame):
    """A bordered card with an optional uppercase header label."""

    def __init__(self, label: str = "", bg: str = C.WHITE, parent=None):
        super().__init__(parent)
        self._bg = bg
        self._label = label
        self._border_color = C.SECTION_BORDER
        self._header_bg = C.BLUE_PALE
        self._header_color = C.BLUE
        self._radius = 10
        self._border_w = 2
        self._header_h = 34 if label else 0

        self._outer = QVBoxLayout(self)
        self._outer.setContentsMargins(
            self._border_w, self._border_w + self._header_h,
            self._border_w, self._border_w,
        )
        self._outer.setSpacing(0)
        self.setStyleSheet("background: transparent;")

        self.content = QWidget()
        self.content.setStyleSheet("background: transparent;")
        self.content_layout = QVBoxLayout(self.content)
        self.content_layout.setContentsMargins(8, 6, 8, 8)
        self.content_layout.setSpacing(4)
        self._outer.addWidget(self.content)

    def paintEvent(self, event):
        from PyQt6.QtGui import QPainter, QPen, QColor, QBrush, QFont, QPainterPath
        from PyQt6.QtCore import QRectF
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        bw = self._border_w
        r = self._radius
        outer = QRectF(bw / 2, bw / 2, self.width() - bw, self.height() - bw)

        # Clip to rounded rect so nothing leaks outside
        clip_path = QPainterPath()
        clip_path.addRoundedRect(outer, r, r)
        painter.setClipPath(clip_path)

        # Fill entire card background
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QBrush(QColor(self._bg)))
        painter.drawRoundedRect(outer, r, r)

        # Draw header band if we have a label
        if self._label:
            header_rect = QRectF(bw / 2, bw / 2, self.width() - bw, self._header_h)
            painter.setBrush(QBrush(QColor(self._header_bg)))
            painter.drawRect(header_rect)

            # Header bottom separator
            painter.setPen(QPen(QColor(self._border_color), bw))
            y_sep = bw / 2 + self._header_h
            painter.drawLine(int(bw), int(y_sep), int(self.width() - bw), int(y_sep))

            # Header text
            painter.setPen(QColor(self._header_color))
            font = QFont()
            font.setPixelSize(13)
            font.setBold(True)
            painter.setFont(font)
            text_rect = QRectF(16, bw / 2, self.width() - 32, self._header_h)
            painter.drawText(text_rect, Qt.AlignmentFlag.AlignVCenter, self._label.upper())

        # Remove clip for border so it draws cleanly
        painter.setClipping(False)

        # Draw border
        pen = QPen(QColor(self._border_color))
        pen.setWidthF(bw)
        painter.setPen(pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawRoundedRect(outer, r, r)
        painter.end()


# ════════════════════════════════════════════════════════════════════
#  Main window
# ════════════════════════════════════════════════════════════════════

class TaskTrackerWindow(FramelessWindowBase):
    """Two-panel Task Tracker — inherits frameless chrome from base class."""

    task_created = pyqtSignal(str)
    task_updated = pyqtSignal(str)
    task_deleted = pyqtSignal(str)

    def __init__(self, parent=None):
        # Storage must exist before build_content is called
        self.storage = Storage()
        self._selected_task_id: Optional[str] = None
        self._status_filter = STATUS_OPEN
        self._search_text = ""
        self._sort_col: Optional[str] = None
        self._sort_dir = "asc"
        self._detail_width = DETAIL_DEFAULT_WIDTH
        self._detail_tab = "details"
        self._editing_description = False
        self._confirm_delete = False
        self._show_assign_dropdown = False
        self._assign_search_text = ""
        self._expanded_emails: Dict[int, bool] = {}
        self._replying_to: Optional[int] = None
        self._reply_text = ""
        self._email_search_text = ""

        # Background workers
        self._scan_worker: Optional[OutlookScanWorker] = None
        self._contact_worker: Optional[ContactSearchWorker] = None

        self._list_width = LIST_WIDTH

        super().__init__(
            title="SuiteView:  Task Tracker",
            default_size=(420, 500),
            min_size=(220, 250),
            parent=parent,
        )

        # Periodic email scan timer
        self._scan_timer = QTimer(self)
        self._scan_timer.timeout.connect(self._start_background_scan)
        self._scan_timer.start(EMAIL_SCAN_INTERVAL_MS)

        # Assignee search debounce
        self._assign_debounce = QTimer(self)
        self._assign_debounce.setSingleShot(True)
        self._assign_debounce.setInterval(300)
        self._assign_debounce.timeout.connect(self._do_contact_search)

        # Initial scan after short delay
        QTimer.singleShot(3000, self._start_background_scan)

    # ── Build content (called by FramelessWindowBase) ───────────────

    def build_content(self) -> QWidget:
        container = QWidget()
        outer_layout = QVBoxLayout(container)
        outer_layout.setContentsMargins(0, 0, 0, 0)
        outer_layout.setSpacing(0)

        # Panels area: left (task list) + right (detail)
        panels_widget = QWidget()
        self._root_layout = QHBoxLayout(panels_widget)
        self._root_layout.setContentsMargins(0, 0, 0, 0)
        self._root_layout.setSpacing(0)

        # Left panel – flexible, fills available width
        self._left_panel = self._build_left_panel()
        self._left_panel.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self._root_layout.addWidget(self._left_panel, 1)

        # Vertical divider between left and right panels
        self._panel_divider = QFrame()
        self._panel_divider.setFrameShape(QFrame.Shape.VLine)
        self._panel_divider.setFixedWidth(3)
        self._panel_divider.setStyleSheet(f"background: {C.BLUE}; border: none;")
        self._panel_divider.setVisible(False)
        self._root_layout.addWidget(self._panel_divider)

        # Right panel – fixed width, hidden until a task is selected
        self._right_panel = self._build_right_panel()
        self._right_panel.setVisible(False)
        self._right_panel.setFixedWidth(self._detail_width)
        self._root_layout.addWidget(self._right_panel)

        outer_layout.addWidget(panels_widget, 1)

        # ── Footer (full width) ─────────────────────────────────────
        footer = QWidget()
        footer.setStyleSheet(f"""
            background: rgba(0,0,0,0.15);
            border-top: 1px solid {C.BORDER_ON_DARK};
        """)
        foot_lay = QHBoxLayout(footer)
        foot_lay.setContentsMargins(12, 5, 12, 5)

        self._count_label = QLabel("0 tasks")
        self._count_label.setStyleSheet("font-size: 12px; color: rgba(255,255,255,0.6); background: transparent;")
        foot_lay.addWidget(self._count_label)

        foot_lay.addStretch()

        ver_lbl = QLabel(f"TaskTracker {VERSION}")
        ver_lbl.setStyleSheet("font-size: 12px; color: rgba(255,255,255,0.6); background: transparent;")
        foot_lay.addWidget(ver_lbl)

        outer_layout.addWidget(footer)

        # Load data
        self._refresh_task_list()

        return container

    # ════════════════════════════════════════════════════════════════
    #  LEFT PANEL
    # ════════════════════════════════════════════════════════════════

    def _build_left_panel(self) -> QWidget:
        panel = QWidget()
        panel.setStyleSheet(f"background: {C.HEADER_FLAT};")
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # ── Control section (white bg) ──────────────────────────
        control = QWidget()
        control.setStyleSheet(f"background: {C.WHITE};")
        ctrl_lay = QVBoxLayout(control)
        ctrl_lay.setContentsMargins(0, 0, 0, 0)
        ctrl_lay.setSpacing(0)

        # (header removed — title bar handled by FramelessWindowBase)

        # ── Quick-add bar ───────────────────────────────────────────
        add_bar = QWidget()
        add_bar.setStyleSheet(f"background: {C.GOLD_PALE};")
        add_lay = QHBoxLayout(add_bar)
        add_lay.setContentsMargins(6, 4, 6, 4)
        add_lay.setSpacing(4)
        add_lay.setAlignment(Qt.AlignmentFlag.AlignTop)

        add_btn = QPushButton("+")
        add_btn.setFixedSize(28, 28)
        add_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        add_btn.setStyleSheet(f"""
            QPushButton {{
                background: {C.GOLD}; color: {C.BLUE};
                border: none; border-radius: 8px;
                font-size: 18px; font-weight: 800;
            }}
            QPushButton:hover {{ background: #d4b820; }}
        """)
        add_btn.clicked.connect(self._on_quick_add)
        add_lay.addWidget(add_btn, 0, Qt.AlignmentFlag.AlignTop)

        self._quick_add_input = QPlainTextEdit()
        self._quick_add_input.setPlaceholderText("New task — type and click [+] to add")
        self._quick_add_input.setStyleSheet(f"""
            QPlainTextEdit {{
                border: 1px solid {C.GOLD}; border-radius: 8px;
                padding: 3px 8px; font-size: 13px;
                font-family: {FONT_FAMILY};
                background: {C.WHITE};
            }}
            QPlainTextEdit:focus {{ border-color: {C.GOLD}; }}
        """)
        self._quick_add_input.setFixedHeight(30)
        self._quick_add_input.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._quick_add_input.setLineWrapMode(QPlainTextEdit.LineWrapMode.WidgetWidth)
        self._quick_add_input.textChanged.connect(self._on_quick_add_text_changed)
        add_lay.addWidget(self._quick_add_input, 1)
        ctrl_lay.addWidget(add_bar)

        # ── Filter bar ──────────────────────────────────────────────
        filter_bar = QWidget()
        filter_bar.setStyleSheet(f"background: {C.BLUE_PALE};")
        filt_lay = QHBoxLayout(filter_bar)
        filt_lay.setContentsMargins(6, 4, 6, 4)
        filt_lay.setSpacing(6)

        # Status toggle buttons
        self._open_btn = QPushButton("Open")
        self._closed_btn = QPushButton("Closed")
        for btn, key in [(self._open_btn, STATUS_OPEN), (self._closed_btn, STATUS_CLOSED)]:
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.clicked.connect(lambda checked, k=key: self._set_status_filter(k))
        self._style_filter_buttons()

        btn_group = QWidget()
        bg_lay = QHBoxLayout(btn_group)
        bg_lay.setContentsMargins(0, 0, 0, 0)
        bg_lay.setSpacing(6)
        bg_lay.addWidget(self._open_btn)
        bg_lay.addWidget(self._closed_btn)
        filt_lay.addWidget(btn_group)

        # Search input
        self._search_input = QLineEdit()
        self._search_input.setPlaceholderText("Search tasks...")
        self._search_input.setStyleSheet(f"""
            QLineEdit {{
                border: 1px solid {C.BORDER}; border-radius: 8px;
                padding: 4px 8px; font-size: 13px;
                font-family: {FONT_FAMILY};
                background: {C.WHITE};
            }}
        """)
        self._search_input.textChanged.connect(self._on_search_changed)
        filt_lay.addWidget(self._search_input, 1)
        ctrl_lay.addWidget(filter_bar)

        # ── Sort bar (compact, no fixed-width columns) ──────────────
        col_bar = QWidget()
        col_bar.setStyleSheet(f"background: {C.BLUE_PALE};")
        col_lay = QHBoxLayout(col_bar)
        col_lay.setContentsMargins(12, 4, 10, 4)
        col_lay.setSpacing(8)

        col_style = f"""
            QLabel {{
                font-size: 11px; font-weight: bold; color: {C.BLUE};
                text-transform: uppercase; letter-spacing: 0.5px;
                background: transparent;
            }}
        """

        self._sort_labels: Dict[str, QLabel] = {}
        for col_key, col_text in [
            ("id", "ID"),
            ("date", "Created"),
            ("activity", "Activity"),
            ("assignee", "Assignee"),
        ]:
            lbl = QLabel(col_text + " ⇅")
            lbl.setStyleSheet(col_style)
            lbl.setCursor(Qt.CursorShape.PointingHandCursor)
            lbl.mousePressEvent = lambda e, k=col_key: self._handle_sort(k)
            self._sort_labels[col_key] = lbl
            col_lay.addWidget(lbl)

        col_lay.addStretch()
        ctrl_lay.addWidget(col_bar)
        layout.addWidget(control)

        # ── Scrollable task list ────────────────────────────────────
        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(True)
        self._scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._scroll.setStyleSheet(f"""
            QScrollArea {{
                border: none;
                background: {C.HEADER_FLAT};
            }}
            QScrollBar:vertical {{
                background: {C.HEADER_FLAT};
                width: 8px;
            }}
            QScrollBar::handle:vertical {{
                background: rgba(255,255,255,0.3);
                border-radius: 4px;
            }}
        """)

        self._card_container = QWidget()
        self._card_container.setStyleSheet(f"background: {C.HEADER_FLAT};")
        self._card_layout = QVBoxLayout(self._card_container)
        self._card_layout.setContentsMargins(10, 6, 10, 6)
        self._card_layout.setSpacing(2)
        self._card_layout.addStretch()

        self._scroll.setWidget(self._card_container)
        layout.addWidget(self._scroll, 1)

        return panel

    # ════════════════════════════════════════════════════════════════
    #  RIGHT PANEL (detail)
    # ════════════════════════════════════════════════════════════════

    def _build_right_panel(self) -> QWidget:
        panel = QWidget()
        panel.setObjectName("rightPanel")
        panel.setStyleSheet(f"#rightPanel {{ background: {C.BLUE_PALE}; }}")

        self._right_layout = QVBoxLayout(panel)
        self._right_layout.setContentsMargins(0, 0, 0, 0)
        self._right_layout.setSpacing(0)

        # These get rebuilt on task selection
        return panel

    def _populate_right_panel(self, task: Task):
        """Tear down and rebuild the right panel content for *task*."""
        # Clear existing content
        while self._right_layout.count():
            item = self._right_layout.takeAt(0)
            w = item.widget()
            if w:
                w.deleteLater()

        # Reset transient state
        self._editing_description = False
        self._confirm_delete = False
        self._show_assign_dropdown = False
        self._assign_search_text = ""
        self._expanded_emails = {}
        self._replying_to = None
        self._reply_text = ""
        self._email_search_text = ""

        # ── Status row (with task ID, created date, close btn) ────
        status_row = QWidget()
        status_row.setStyleSheet(f"background: {C.WHITE}; border-bottom: 1px solid {C.BORDER};")
        sr_lay = QHBoxLayout(status_row)
        sr_lay.setContentsMargins(16, 8, 16, 8)

        d_id = QLabel(task.task_id)
        d_id.setStyleSheet(f"font-family: {MONO_FAMILY}; font-size: 15px; color: {C.BLUE}; font-weight: 700; background: transparent;")
        sr_lay.addWidget(d_id)

        created_lbl = QLabel(f"<b>Created:</b> {task.created_date}")
        created_lbl.setStyleSheet(f"font-size: 13px; color: {C.TEXT_MID}; background: transparent; margin-left: 12px;")
        sr_lay.addWidget(created_lbl)
        sr_lay.addStretch()

        status_lbl = QLabel("Status:")
        status_lbl.setStyleSheet(f"font-size: 13px; color: {C.TEXT}; font-weight: 600; background: transparent;")
        sr_lay.addWidget(status_lbl)

        is_open = task.status == STATUS_OPEN
        self._status_btn = QPushButton("OPEN" if is_open else "CLOSED")
        self._status_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_bg = C.RED if is_open else C.BLUE
        self._status_btn.setStyleSheet(f"""
            QPushButton {{
                padding: 3px 14px; border-radius: 8px;
                font-size: 12px; font-weight: 700;
                border: none; background: {btn_bg}; color: #fff;
            }}
            QPushButton:hover {{ opacity: 0.9; }}
        """)
        self._status_btn.clicked.connect(self._toggle_status)
        sr_lay.addWidget(self._status_btn)

        close_btn = QPushButton("✕")
        close_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        close_btn.setStyleSheet(f"""
            QPushButton {{ padding: 3px 8px; background: transparent; color: {C.TEXT_LIGHT}; border: none; border-radius: 8px; font-size: 15px; }}
            QPushButton:hover {{ background: {C.BLUE_PALE}; color: {C.RED}; }}
        """)
        close_btn.clicked.connect(self._close_detail)
        sr_lay.addWidget(close_btn)
        self._right_layout.addWidget(status_row)

        # ── Tab bar ─────────────────────────────────────────────────
        tab_bar = QWidget()
        tab_bar.setStyleSheet(f"background: {C.WHITE};")
        tb_lay = QHBoxLayout(tab_bar)
        tb_lay.setContentsMargins(0, 0, 0, 0)
        tb_lay.setSpacing(0)

        self._tab_details_btn = QPushButton("Details")
        self._tab_emails_btn = QPushButton("Email Trail")

        for btn, key in [(self._tab_details_btn, "details"), (self._tab_emails_btn, "emails")]:
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.clicked.connect(lambda checked, k=key: self._set_detail_tab(k))
        self._style_tab_buttons()
        tb_lay.addWidget(self._tab_details_btn)
        tb_lay.addWidget(self._tab_emails_btn)
        tb_lay.addStretch()
        self._right_layout.addWidget(tab_bar)

        # ── Tab content area (scrollable) ───────────────────────────
        self._tab_scroll = QScrollArea()
        self._tab_scroll.setWidgetResizable(True)
        self._tab_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._tab_scroll.setStyleSheet(f"""
            QScrollArea {{ border: none; background: {C.BLUE_PALE}; }}
            QScrollBar:vertical {{ background: {C.BLUE_PALE}; width: 8px; }}
            QScrollBar::handle:vertical {{ background: rgba(0,0,0,0.15); border-radius: 4px; }}
        """)

        self._tab_content = QWidget()
        self._tab_content.setObjectName("tabContentArea")
        self._tab_content.setStyleSheet(f"#tabContentArea {{ background: {C.BLUE_PALE}; }}")
        self._tab_content_layout = QVBoxLayout(self._tab_content)
        self._tab_content_layout.setContentsMargins(14, 12, 14, 12)
        self._tab_content_layout.setSpacing(12)
        self._tab_scroll.setWidget(self._tab_content)
        self._right_layout.addWidget(self._tab_scroll, 1)

        # Populate the active tab
        self._render_tab_content(task)

    # ── Tab content rendering ───────────────────────────────────────

    def _render_tab_content(self, task: Task):
        """Render the active tab (details or emails) for *task*."""
        # Clear
        while self._tab_content_layout.count():
            item = self._tab_content_layout.takeAt(0)
            w = item.widget()
            if w:
                w.deleteLater()

        if self._detail_tab == "details":
            self._render_details_tab(task)
        else:
            self._render_emails_tab(task)

    def _render_details_tab(self, task: Task):
        lay = self._tab_content_layout

        # ── Description section ─────────────────────────────────────
        desc_box = SectionBox("Description")
        if self._editing_description:
            self._desc_edit = QPlainTextEdit(task.title)
            self._desc_edit.setStyleSheet(f"""
                QPlainTextEdit {{
                    border: 1px solid {C.GOLD}; border-radius: 8px;
                    padding: 8px 10px; font-size: 14px;
                    font-family: {FONT_FAMILY}; line-height: 1.5;
                    background: {C.WHITE};
                }}
            """)
            self._desc_edit.setMinimumHeight(60)
            desc_box.content_layout.addWidget(self._desc_edit)

            btn_row = QHBoxLayout()
            save_btn = QPushButton("Save")
            save_btn.setCursor(Qt.CursorShape.PointingHandCursor)
            save_btn.setStyleSheet(f"""
                QPushButton {{ padding: 4px 12px; background: {C.BLUE}; color: #fff; border: none; border-radius: 8px; font-size: 12px; font-weight: 600; }}
                QPushButton:hover {{ background: {C.BLUE_LIGHT}; }}
            """)
            save_btn.clicked.connect(self._save_description)
            btn_row.addWidget(save_btn)

            cancel_btn = QPushButton("Cancel")
            cancel_btn.setCursor(Qt.CursorShape.PointingHandCursor)
            cancel_btn.setStyleSheet(f"""
                QPushButton {{ padding: 4px 12px; background: {C.WHITE}; color: {C.TEXT_MID}; border: 1px solid {C.BORDER}; border-radius: 8px; font-size: 12px; font-weight: 600; }}
                QPushButton:hover {{ background: {C.BLUE_PALE}; }}
            """)
            cancel_btn.clicked.connect(self._cancel_edit_description)
            btn_row.addWidget(cancel_btn)
            btn_row.addStretch()
            desc_box.content_layout.addLayout(btn_row)
        else:
            desc_text = QLabel(task.title)
            desc_text.setWordWrap(True)
            desc_text.setStyleSheet(f"font-size: 14px; line-height: 1.4; color: {C.TEXT_MID}; cursor: pointer; background: transparent;")
            desc_text.setCursor(Qt.CursorShape.PointingHandCursor)
            desc_text.mousePressEvent = lambda e: self._start_edit_description()
            desc_box.content_layout.addWidget(desc_text)

            hint = QLabel("Click to edit")
            hint.setStyleSheet(f"font-size: 11px; color: {C.TEXT_LIGHT}; font-style: italic; background: transparent;")
            desc_box.content_layout.addWidget(hint)

        lay.addWidget(desc_box)

        # ── Assigned To section ─────────────────────────────────────
        assign_box = SectionBox("Assigned To")

        # Existing assignee chips
        if task.assignees:
            chips_w = QWidget()
            chips_w.setStyleSheet("background: transparent;")
            chips_lay = QHBoxLayout(chips_w)
            chips_lay.setContentsMargins(0, 0, 0, 0)
            chips_lay.setSpacing(6)

            for a in task.assignees:
                chip = self._make_assignee_chip(a, task.task_id)
                chips_lay.addWidget(chip)
            chips_lay.addStretch()
            assign_box.content_layout.addWidget(chips_w)

        # Search input
        placeholder = "Add another person..." if task.assignees else "Type a name or email to assign..."
        self._assign_input = QLineEdit()
        self._assign_input.setPlaceholderText(placeholder)
        self._assign_input.setStyleSheet(f"""
            QLineEdit {{
                border: 1px solid {C.GOLD}; border-radius: 8px;
                padding: 4px 8px; font-size: 14px;
                font-family: {FONT_FAMILY};
                background: {C.GOLD_PALE};
            }}
        """)
        self._assign_input.textChanged.connect(self._on_assign_search_changed)
        self._assign_input.returnPressed.connect(self._on_assign_enter)
        assign_box.content_layout.addWidget(self._assign_input)

        # Dropdown (populated dynamically)
        self._assign_dropdown = QWidget()
        self._assign_dropdown.setStyleSheet(f"""
            background: {C.WHITE};
            border: 1px solid {C.BORDER};
            border-radius: 8px;
        """)
        self._assign_dropdown.setVisible(False)
        self._assign_dropdown_layout = QVBoxLayout(self._assign_dropdown)
        self._assign_dropdown_layout.setContentsMargins(0, 0, 0, 0)
        self._assign_dropdown_layout.setSpacing(0)
        assign_box.content_layout.addWidget(self._assign_dropdown)

        lay.addWidget(assign_box)

        # ── Action row: email status on left, delete on right ───
        action_w = QWidget()
        action_w.setStyleSheet("background: transparent;")
        action_lay = QHBoxLayout(action_w)
        action_lay.setContentsMargins(0, 4, 0, 0)
        action_lay.setSpacing(8)

        # Email status / send button (left side)
        if task.assignees:
            if not task.email_sent:
                count = len(task.assignees)
                if count == 1:
                    btn_text = f"✉ Send to {task.assignees[0].name.split()[0]}"
                else:
                    btn_text = f"✉ Send to {count} people"
                send_btn = QPushButton(btn_text)
                send_btn.setCursor(Qt.CursorShape.PointingHandCursor)
                send_btn.setStyleSheet(f"""
                    QPushButton {{
                        padding: 5px 12px; background: {C.GOLD}; color: {C.BLUE};
                        border: none; border-radius: 8px;
                        font-size: 12px; font-weight: 700;
                    }}
                    QPushButton:hover {{ background: #d4b820; }}
                """)
                send_btn.clicked.connect(self._send_task_email)
                action_lay.addWidget(send_btn)
            else:
                sent_lbl = QLabel(f"✓ Email sent — tracking via [{task.task_id}]")
                sent_lbl.setStyleSheet(f"font-size: 12px; font-weight: 600; color: {C.GREEN}; background: transparent;")
                action_lay.addWidget(sent_lbl)

        action_lay.addStretch()

        # Delete button (right side)
        if not self._confirm_delete:
            del_btn = QPushButton("🗑 Delete")
            del_btn.setCursor(Qt.CursorShape.PointingHandCursor)
            del_btn.setStyleSheet(f"""
                QPushButton {{
                    padding: 5px 12px; background: {C.WHITE}; color: {C.RED};
                    border: 1px solid {C.RED}; border-radius: 8px;
                    font-size: 12px; font-weight: 600;
                }}
                QPushButton:hover {{ background: #fff0f0; }}
            """)
            del_btn.clicked.connect(self._show_delete_confirm)
            action_lay.addWidget(del_btn)
        else:
            confirm_lbl = QLabel(f"Delete {task.task_id}?")
            confirm_lbl.setStyleSheet(f"font-size: 13px; color: {C.RED}; font-weight: 600; background: transparent;")
            action_lay.addWidget(confirm_lbl)

            yes_btn = QPushButton("Yes")
            yes_btn.setCursor(Qt.CursorShape.PointingHandCursor)
            yes_btn.setStyleSheet(f"""
                QPushButton {{ padding: 4px 12px; background: {C.RED}; color: #fff; border: none; border-radius: 8px; font-size: 12px; font-weight: 700; }}
            """)
            yes_btn.clicked.connect(self._delete_task)
            action_lay.addWidget(yes_btn)

            no_btn = QPushButton("Cancel")
            no_btn.setCursor(Qt.CursorShape.PointingHandCursor)
            no_btn.setStyleSheet(f"""
                QPushButton {{ padding: 4px 12px; background: {C.WHITE}; color: {C.TEXT_MID}; border: 1px solid {C.BORDER}; border-radius: 8px; font-size: 12px; font-weight: 600; }}
            """)
            no_btn.clicked.connect(self._cancel_delete)
            action_lay.addWidget(no_btn)

        lay.addWidget(action_w)
        lay.addStretch()

    def _render_emails_tab(self, task: Task):
        lay = self._tab_content_layout

        # ── Email search ────────────────────────────────────────────
        self._email_search_input = QLineEdit()
        self._email_search_input.setPlaceholderText("Search emails...")
        self._email_search_input.setStyleSheet(f"""
            QLineEdit {{
                border: 1px solid {C.BORDER}; border-radius: 8px;
                padding: 5px 10px; font-size: 13px;
                font-family: {FONT_FAMILY}; background: {C.WHITE};
            }}
        """)
        self._email_search_input.textChanged.connect(self._on_email_search_changed)
        lay.addWidget(self._email_search_input)

        # ── Email list ──────────────────────────────────────────────
        if not task.emails:
            empty = QFrame()
            empty.setStyleSheet(f"border: 1px dashed {C.BORDER}; border-radius: 10px; background: transparent;")
            e_lay = QVBoxLayout(empty)
            e_lay.setContentsMargins(14, 30, 14, 30)
            e_lay.setAlignment(Qt.AlignmentFlag.AlignCenter)

            icon = QLabel("✉")
            icon.setStyleSheet("font-size: 24px; opacity: 0.4; background: transparent;")
            icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
            e_lay.addWidget(icon)

            no_lbl = QLabel("No emails yet")
            no_lbl.setStyleSheet(f"font-size: 14px; font-weight: 600; color: {C.TEXT_LIGHT}; background: transparent;")
            no_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            e_lay.addWidget(no_lbl)

            hint = QLabel("Assign someone and send to start tracking")
            hint.setStyleSheet(f"font-size: 12px; color: {C.TEXT_LIGHT}; background: transparent;")
            hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
            e_lay.addWidget(hint)

            lay.addWidget(empty)
        else:
            # Sort by date descending
            emails = sorted(task.emails, key=lambda e: e.date_sort, reverse=True)

            # Apply search filter
            if self._email_search_text:
                s = self._email_search_text.lower()
                emails = [e for e in emails if
                          s in e.body.lower() or s in e.subject.lower() or
                          s in e.from_addr.lower() or s in e.to_addr.lower()]

            if not emails:
                no_match = QLabel("No emails match your search")
                no_match.setStyleSheet(f"font-size: 13px; color: {C.TEXT_LIGHT}; padding: 20px; background: transparent;")
                no_match.setAlignment(Qt.AlignmentFlag.AlignCenter)
                lay.addWidget(no_match)
            else:
                self._email_cards_list = emails
                for i, email in enumerate(emails):
                    card = self._build_email_card(email, i, task)
                    lay.addWidget(card)

        # ── Reply compose area ──────────────────────────────────────
        if self._replying_to is not None and task.emails:
            emails_sorted = sorted(task.emails, key=lambda e: e.date_sort, reverse=True)
            if self._replying_to < len(emails_sorted):
                orig = emails_sorted[self._replying_to]
                reply_to_name = orig.from_addr if orig.type == "received" else orig.to_addr

                reply_w = QWidget()
                reply_w.setStyleSheet(f"border-top: 2px solid {C.GOLD}; margin-top: 8px; background: transparent;")
                r_lay = QVBoxLayout(reply_w)
                r_lay.setContentsMargins(0, 10, 0, 0)

                r_hdr = QLabel(f'Replying to: <span style="color: {C.BLUE};">{reply_to_name}</span>')
                r_hdr.setStyleSheet(f"font-size: 12px; color: {C.TEXT_MID}; font-weight: 600; background: transparent;")
                r_lay.addWidget(r_hdr)

                self._reply_edit = QPlainTextEdit()
                self._reply_edit.setPlaceholderText("Type your response...")
                self._reply_edit.setStyleSheet(f"""
                    QPlainTextEdit {{
                        border: 1px solid {C.GOLD}; border-radius: 8px;
                        padding: 8px 10px; font-size: 13px;
                        font-family: {FONT_FAMILY}; line-height: 1.5;
                        min-height: 80px;
                    }}
                """)
                r_lay.addWidget(self._reply_edit)

                rbtn_row = QHBoxLayout()
                send_reply_btn = QPushButton("✉ Send Reply")
                send_reply_btn.setCursor(Qt.CursorShape.PointingHandCursor)
                send_reply_btn.setStyleSheet(f"""
                    QPushButton {{ padding: 5px 14px; background: {C.BLUE}; color: #fff; border: none; border-radius: 8px; font-size: 12px; font-weight: 700; }}
                    QPushButton:hover {{ background: {C.BLUE_LIGHT}; }}
                """)
                send_reply_btn.clicked.connect(self._send_reply)
                rbtn_row.addWidget(send_reply_btn)

                cancel_reply_btn = QPushButton("Cancel")
                cancel_reply_btn.setCursor(Qt.CursorShape.PointingHandCursor)
                cancel_reply_btn.setStyleSheet(f"""
                    QPushButton {{ padding: 5px 14px; background: {C.WHITE}; color: {C.TEXT_MID}; border: 1px solid {C.BORDER}; border-radius: 8px; font-size: 12px; font-weight: 600; }}
                """)
                cancel_reply_btn.clicked.connect(self._cancel_reply)
                rbtn_row.addWidget(cancel_reply_btn)
                rbtn_row.addStretch()
                r_lay.addLayout(rbtn_row)

                lay.addWidget(reply_w)

        lay.addStretch()

    # ── Email card widget ───────────────────────────────────────────

    def _build_email_card(self, email: Email, idx: int, task: Task) -> QFrame:
        card = QFrame()
        left_border_color = C.BLUE if email.type == "sent" else C.GOLD
        card.setStyleSheet(f"""
            QFrame {{
                border: 1px solid {C.BORDER};
                border-left: 3px solid {left_border_color};
                border-radius: 8px;
                margin-bottom: 6px;
                background: {C.WHITE};
            }}
        """)
        card_lay = QVBoxLayout(card)
        card_lay.setContentsMargins(10, 5, 10, 5)
        card_lay.setSpacing(2)

        # Line 1: from → to, 📎, date, Reply button
        line1 = QHBoxLayout()
        line1.setSpacing(6)

        from_color = C.BLUE if email.type == "sent" else C.GOLD
        from_lbl = QLabel(email.from_addr)
        from_lbl.setStyleSheet(f"font-weight: 700; color: {from_color}; font-size: 13px; background: transparent;")
        line1.addWidget(from_lbl)

        arrow = QLabel("→")
        arrow.setStyleSheet(f"color: {C.TEXT_LIGHT}; font-size: 13px; background: transparent;")
        line1.addWidget(arrow)

        to_lbl = QLabel(email.to_addr)
        to_lbl.setStyleSheet(f"color: {C.TEXT_LIGHT}; font-size: 13px; background: transparent;")
        line1.addWidget(to_lbl)

        if email.has_attachment:
            attach_icon = QLabel("📎")
            attach_icon.setToolTip("Has attachment")
            attach_icon.setStyleSheet("font-size: 14px; background: transparent;")
            line1.addWidget(attach_icon)

        line1.addStretch()

        date_lbl = QLabel(email.date)
        date_lbl.setStyleSheet(f"font-size: 11px; color: {C.TEXT_LIGHT}; background: transparent;")
        line1.addWidget(date_lbl)

        reply_btn = QPushButton("Reply")
        reply_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        reply_btn.setStyleSheet(f"""
            QPushButton {{
                padding: 2px 8px; background: {C.BLUE}; color: #fff;
                border: none; border-radius: 6px;
                font-size: 10px; font-weight: 700;
            }}
            QPushButton:hover {{ background: {C.BLUE_LIGHT}; }}
        """)
        reply_btn.clicked.connect(lambda: self._start_reply(idx))
        line1.addWidget(reply_btn)

        card_lay.addLayout(line1)

        # Line 2: body preview (click to expand)
        is_expanded = self._expanded_emails.get(idx, False)
        if is_expanded:
            body_lbl = QLabel(email.body)
            body_lbl.setWordWrap(True)
        else:
            preview = email.body[:70] + "…" if len(email.body) > 70 else email.body
            body_lbl = QLabel(preview)

        body_lbl.setStyleSheet(f"font-size: 13px; color: {C.TEXT_MID}; line-height: 1.5; background: transparent;")
        body_lbl.setCursor(Qt.CursorShape.PointingHandCursor)
        body_lbl.mousePressEvent = lambda e, i=idx: self._toggle_email_expand(i)
        card_lay.addWidget(body_lbl)

        # Double-click top row → open in Outlook
        def on_double_click(e, eid=email.outlook_entry_id):
            if eid:
                outlook_bridge.open_email_in_outlook(eid)
            else:
                QMessageBox.information(self, "Not Available",
                                        "This email doesn't have an Outlook reference. "
                                        "Emails from background scans will be openable.")

        # Attach double-click to the from_lbl as a proxy for line 1
        from_lbl.mouseDoubleClickEvent = on_double_click

        return card

    # ── Assignee chip ───────────────────────────────────────────────

    def _make_assignee_chip(self, contact: Contact, task_id: str) -> QFrame:
        chip = QFrame()
        chip.setStyleSheet(f"""
            QFrame {{
                background: {C.BLUE_PALE}; border: 1px solid {C.BORDER};
                border-radius: 12px; padding: 3px 7px;
            }}
        """)
        lay = QHBoxLayout(chip)
        lay.setContentsMargins(4, 2, 4, 2)
        lay.setSpacing(5)

        # Initials avatar
        initials = "".join(p[0] for p in contact.name.split() if p)[:2].upper()
        avatar = QLabel(initials)
        avatar.setFixedSize(24, 24)
        avatar.setAlignment(Qt.AlignmentFlag.AlignCenter)
        avatar.setStyleSheet(f"""
            background: {C.WHITE}; border: 1px solid {C.BORDER};
            border-radius: 12px; font-size: 9px; font-weight: 700;
            color: {C.BLUE};
        """)
        lay.addWidget(avatar)

        name_lbl = QLabel(contact.name)
        name_lbl.setStyleSheet(f"font-size: 14px; font-weight: 600; color: {C.BLUE}; background: transparent; border: none;")
        lay.addWidget(name_lbl)

        remove_btn = QPushButton("×")
        remove_btn.setFixedSize(16, 16)
        remove_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        remove_btn.setStyleSheet(f"""
            QPushButton {{
                background: none; border: none; color: {C.RED};
                font-size: 13px; font-weight: 700; padding: 0;
            }}
            QPushButton:hover {{ color: #ff0000; }}
        """)
        remove_btn.clicked.connect(lambda: self._remove_assignee(task_id, contact))
        lay.addWidget(remove_btn)

        return chip

    # ════════════════════════════════════════════════════════════════
    #  DATA / EVENT HANDLERS
    # ════════════════════════════════════════════════════════════════

    def _get_selected_task(self) -> Optional[Task]:
        if self._selected_task_id:
            return self.storage.get_task(self._selected_task_id)
        return None

    # ── Task list refresh ───────────────────────────────────────────

    def _refresh_task_list(self):
        """Reload tasks from storage, apply filters/sort, rebuild cards."""
        all_tasks = self.storage.get_all_tasks()

        # Filter by status
        tasks = [t for t in all_tasks if t.status == self._status_filter]

        # Filter by search
        if self._search_text:
            s = self._search_text.lower()
            tasks = [t for t in tasks if
                     s in t.task_id.lower() or
                     s in t.title.lower() or
                     any(s in a.name.lower() for a in t.assignees)]

        # Sort
        if self._sort_col:
            reverse = self._sort_dir == "desc"
            if self._sort_col == "id":
                tasks.sort(key=lambda t: t.task_id, reverse=reverse)
            elif self._sort_col == "date":
                tasks.sort(key=lambda t: t.created_date, reverse=reverse)
            elif self._sort_col == "activity":
                tasks.sort(key=lambda t: t.last_activity_sort, reverse=reverse)
            elif self._sort_col == "assignee":
                tasks.sort(
                    key=lambda t: (t.assignees[0].name if t.assignees else "zzz").lower(),
                    reverse=reverse,
                )

        # Rebuild card widgets
        # Remove existing cards
        while self._card_layout.count():
            item = self._card_layout.takeAt(0)
            w = item.widget()
            if w:
                w.deleteLater()

        if not tasks:
            empty = QLabel("No tasks found")
            empty.setStyleSheet("color: rgba(255,255,255,0.5); font-size: 15px; padding: 30px; background: transparent;")
            empty.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self._card_layout.addWidget(empty)
        else:
            for task in tasks:
                card = TaskCard(task, is_selected=(task.task_id == self._selected_task_id))
                card.clicked.connect(self._on_card_clicked)
                self._card_layout.addWidget(card)

        self._card_layout.addStretch()

        # Update count
        self._count_label.setText(f"{len(tasks)} task{'s' if len(tasks) != 1 else ''}")

    # ── Quick-add ───────────────────────────────────────────────────

    def eventFilter(self, obj, event):
        """Default event filter — no Enter interception on quick-add."""
        return super().eventFilter(obj, event)

    def _on_quick_add_text_changed(self):
        """Auto-grow the quick-add input as the user types multiple lines."""
        doc = self._quick_add_input.document()
        doc.setTextWidth(self._quick_add_input.viewport().width())
        content_h = int(doc.size().height()) + 10
        new_h = min(120, max(30, content_h))
        self._quick_add_input.setFixedHeight(new_h)
        # Show scrollbar only when at max height
        policy = Qt.ScrollBarPolicy.ScrollBarAsNeeded if new_h >= 120 else Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        self._quick_add_input.setVerticalScrollBarPolicy(policy)

    def _on_quick_add(self):
        title = self._quick_add_input.toPlainText().strip()
        if not title:
            return
        task = self.storage.create_task(title)
        self._quick_add_input.clear()
        self._quick_add_input.setFixedHeight(30)
        self._quick_add_input.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._selected_task_id = task.task_id
        self._refresh_task_list()
        self._show_detail(task)
        self.task_created.emit(task.task_id)

    # ── Card click ──────────────────────────────────────────────────

    def _on_card_clicked(self, task_id: str):
        if self._selected_task_id == task_id:
            # Clicking same card closes detail
            self._close_detail()
            return
        self._selected_task_id = task_id
        task = self.storage.get_task(task_id)
        if task:
            self._detail_tab = "details"
            self._show_detail(task)
            self._refresh_task_list()

    def _show_detail(self, task: Task):
        was_hidden = not self._right_panel.isVisible()
        self._populate_right_panel(task)
        if was_hidden:
            self._panel_divider.setVisible(True)
            self._right_panel.setVisible(True)
            # Expand window to fit detail panel
            geo = self.geometry()
            new_width = geo.width() + 3 + self._detail_width
            screen = self.screen().availableGeometry() if self.screen() else None
            if screen:
                max_right = screen.x() + screen.width()
                if geo.x() + new_width > max_right:
                    new_x = max(screen.x(), max_right - new_width)
                    self.setGeometry(new_x, geo.y(), new_width, geo.height())
                    return
            self.setGeometry(geo.x(), geo.y(), new_width, geo.height())

    def _close_detail(self):
        self._selected_task_id = None
        if self._right_panel.isVisible():
            self._panel_divider.setVisible(False)
            self._right_panel.setVisible(False)
            # Shrink window by detail panel width
            geo = self.geometry()
            new_width = max(self.minimumWidth(), geo.width() - 3 - self._detail_width)
            self.setGeometry(geo.x(), geo.y(), new_width, geo.height())
        self._refresh_task_list()

    # ── Status filter ───────────────────────────────────────────────

    def _set_status_filter(self, status: str):
        self._status_filter = status
        self._style_filter_buttons()
        self._refresh_task_list()

    def _style_filter_buttons(self):
        for btn, key in [(self._open_btn, STATUS_OPEN), (self._closed_btn, STATUS_CLOSED)]:
            active = self._status_filter == key
            bg = C.BLUE if active else C.WHITE
            fg = "#fff" if active else C.TEXT_MID
            border = C.BLUE if active else C.BORDER
            btn.setStyleSheet(f"""
                QPushButton {{
                    padding: 4px 14px;
                    border: 1px solid {border};
                    background: {bg}; color: {fg};
                    font-size: 13px; font-weight: 600;
                    border-radius: 12px;
                }}
                QPushButton:hover {{ opacity: 0.9; }}
            """)

    # ── Search ──────────────────────────────────────────────────────

    def _on_search_changed(self, text: str):
        self._search_text = text.strip()
        self._refresh_task_list()

    # ── Sort ────────────────────────────────────────────────────────

    def _handle_sort(self, col: str):
        if self._sort_col == col:
            self._sort_dir = "desc" if self._sort_dir == "asc" else "asc"
        else:
            self._sort_col = col
            self._sort_dir = "asc"
        self._update_sort_labels()
        self._refresh_task_list()

    def _update_sort_labels(self):
        for key, lbl in self._sort_labels.items():
            base_text = {"id": "ID", "date": "Created", "activity": "Activity", "assignee": "Assignee"}[key]
            if self._sort_col == key:
                arrow = " ▲" if self._sort_dir == "asc" else " ▼"
            else:
                arrow = " ⇅"
            lbl.setText(base_text + arrow)

    # ── Tab switching ───────────────────────────────────────────────

    def _set_detail_tab(self, tab: str):
        self._detail_tab = tab
        self._replying_to = None
        self._reply_text = ""
        self._style_tab_buttons()
        task = self._get_selected_task()
        if task:
            self._render_tab_content(task)

    def _style_tab_buttons(self):
        for btn, key in [(self._tab_details_btn, "details"), (self._tab_emails_btn, "emails")]:
            active = self._detail_tab == key
            if active:
                btn.setStyleSheet(f"""
                    QPushButton {{
                        padding: 6px 18px; margin: 4px 2px;
                        background: {C.GOLD_PALE};
                        border: 1px solid {C.GOLD_BORDER};
                        border-radius: 14px;
                        font-size: 14px; font-weight: 700; color: {C.BLUE};
                    }}
                    QPushButton:hover {{ background: {C.GOLD_PALE}; }}
                """)
            else:
                btn.setStyleSheet(f"""
                    QPushButton {{
                        padding: 6px 18px; margin: 4px 2px;
                        background: transparent;
                        border: 1px solid {C.BORDER};
                        border-radius: 14px;
                        font-size: 14px; font-weight: 700; color: {C.TEXT_LIGHT};
                    }}
                    QPushButton:hover {{ background: {C.BLUE_PALE}; }}
                """)

    # ── Status toggle ───────────────────────────────────────────────

    def _toggle_status(self):
        task = self._get_selected_task()
        if not task:
            return
        task.status = STATUS_CLOSED if task.status == STATUS_OPEN else STATUS_OPEN
        self.storage.update_task(task)
        self.task_updated.emit(task.task_id)
        # Re-render
        self._show_detail(self.storage.get_task(task.task_id))
        self._refresh_task_list()

    # ── Description editing ─────────────────────────────────────────

    def _start_edit_description(self):
        self._editing_description = True
        task = self._get_selected_task()
        if task:
            self._render_tab_content(task)

    def _save_description(self):
        task = self._get_selected_task()
        if task and hasattr(self, '_desc_edit'):
            task.title = self._desc_edit.toPlainText().strip()
            self.storage.update_task(task)
            self.task_updated.emit(task.task_id)
        self._editing_description = False
        task = self._get_selected_task()
        if task:
            self._render_tab_content(task)
            self._refresh_task_list()

    def _cancel_edit_description(self):
        self._editing_description = False
        task = self._get_selected_task()
        if task:
            self._render_tab_content(task)

    # ── Assignee management ─────────────────────────────────────────

    def _on_assign_search_changed(self, text: str):
        self._assign_search_text = text.strip()
        if len(self._assign_search_text) >= 2:
            self._assign_debounce.start()
            self._update_assign_dropdown()
        else:
            self._assign_dropdown.setVisible(False)

    def _do_contact_search(self):
        """Fire background search against Outlook contacts/GAL."""
        query = self._assign_search_text
        if len(query) < 3:
            return
        if self._contact_worker and self._contact_worker.isRunning():
            return
        self._contact_worker = ContactSearchWorker(query, parent=self)
        self._contact_worker.results_ready.connect(self._on_gal_results)
        self._contact_worker.start()

    def _on_gal_results(self, results: List[Contact]):
        """Merge GAL results into local contact list and refresh dropdown."""
        for c in results:
            self.storage.add_contact(c.name, c.email)
        self._update_assign_dropdown()

    def _update_assign_dropdown(self):
        """Rebuild the assignee dropdown based on current search text."""
        task = self._get_selected_task()
        if not task:
            return

        # Clear existing items
        while self._assign_dropdown_layout.count():
            item = self._assign_dropdown_layout.takeAt(0)
            w = item.widget()
            if w:
                w.deleteLater()

        search = self._assign_search_text.lower()
        all_contacts = self.storage.get_contacts()
        assigned_emails = {a.email for a in task.assignees if a.email}

        # Filter contacts
        filtered = [c for c in all_contacts
                    if (search in c.name.lower() or search in c.email.lower())
                    and c.email not in assigned_emails]

        if filtered:
            for c in filtered[:10]:  # limit dropdown items
                item_btn = QPushButton()
                item_btn.setText(f"  {c.name}  —  {c.email}")
                item_btn.setStyleSheet(f"""
                    QPushButton {{
                        text-align: left; padding: 7px 12px;
                        border: none; border-bottom: 1px solid {C.BLUE_PALE};
                        font-size: 13px; background: {C.WHITE};
                    }}
                    QPushButton:hover {{ background: {C.GOLD_PALE}; }}
                """)
                item_btn.setCursor(Qt.CursorShape.PointingHandCursor)
                item_btn.clicked.connect(lambda checked, contact=c: self._assign_contact(contact))
                self._assign_dropdown_layout.addWidget(item_btn)

        # Freeform entry option
        if self._assign_search_text:
            freeform_text = f'+ Assign to "{self._assign_search_text}"' if not filtered else f'+ Use "{self._assign_search_text}" as new contact'
            freeform_btn = QPushButton(freeform_text)
            freeform_btn.setStyleSheet(f"""
                QPushButton {{
                    text-align: left; padding: 5px 12px;
                    border: none; border-top: 1px solid {C.BORDER};
                    font-size: 11px; color: {C.TEXT_LIGHT if filtered else C.BLUE};
                    font-weight: {'normal' if filtered else '600'};
                    background: {C.WHITE};
                }}
                QPushButton:hover {{ background: {C.GOLD_PALE}; }}
            """)
            freeform_btn.setCursor(Qt.CursorShape.PointingHandCursor)
            freeform_btn.clicked.connect(self._assign_freeform)
            self._assign_dropdown_layout.addWidget(freeform_btn)

        self._assign_dropdown.setVisible(bool(self._assign_search_text))

    def _on_assign_enter(self):
        """Enter key in assign input: assign top match or freeform."""
        task = self._get_selected_task()
        if not task:
            return

        search = self._assign_search_text.lower()
        all_contacts = self.storage.get_contacts()
        assigned_emails = {a.email for a in task.assignees if a.email}
        filtered = [c for c in all_contacts
                    if (search in c.name.lower() or search in c.email.lower())
                    and c.email not in assigned_emails]

        if filtered:
            self._assign_contact(filtered[0])
        elif self._assign_search_text:
            self._assign_freeform()

    def _assign_contact(self, contact: Contact):
        task = self._get_selected_task()
        if not task:
            return
        self.storage.add_assignee(task.task_id, contact)
        self._assign_search_text = ""
        self._assign_dropdown.setVisible(False)
        self.task_updated.emit(task.task_id)
        # Refresh
        task = self.storage.get_task(task.task_id)
        self._render_tab_content(task)
        self._refresh_task_list()

    def _assign_freeform(self):
        text = self._assign_search_text.strip()
        if not text:
            return
        is_email = "@" in text
        name = text.split("@")[0] if is_email else text
        email = text if is_email else ""
        contact = Contact(name=name, email=email)
        if email:
            self.storage.add_contact(name, email)
        self._assign_contact(contact)

    def _remove_assignee(self, task_id: str, contact: Contact):
        self.storage.remove_assignee(task_id, email=contact.email, name=contact.name)
        self.task_updated.emit(task_id)
        task = self.storage.get_task(task_id)
        if task:
            self._render_tab_content(task)
            self._refresh_task_list()

    # ── Email actions ───────────────────────────────────────────────

    def _send_task_email(self):
        task = self._get_selected_task()
        if not task or not task.assignees:
            return

        body = task.title
        self._send_email_worker = outlook_bridge.SendTaskEmailWorker(task, body, parent=self)
        self._send_email_worker.finished.connect(self._on_send_task_email_done)
        self._send_email_worker.start()

    def _on_send_task_email_done(self):
        success = getattr(self._send_email_worker, 'success', False)
        task = self._get_selected_task()
        if not task:
            return

        if success:
            now = datetime.now()
            date_str = now.strftime("%b %d, %I:%M %p").replace(" 0", " ")
            date_sort = float(now.strftime("%Y%m%d")) + float(now.strftime("%H%M")) / 10000

            for a in task.assignees:
                if a.email:
                    email = Email(
                        from_addr="You",
                        to_addr=a.email,
                        date=date_str,
                        date_sort=date_sort,
                        subject=f"[{task.task_id}] {task.title[:60]}",
                        body=task.title,
                        type="sent",
                        has_attachment=False,
                    )
                    self.storage.add_email(task.task_id, email)

            task = self.storage.get_task(task.task_id)
            task.email_sent = True
            task.last_activity = "Just now"
            task.last_activity_sort = 0
            task.last_activity_from = "You"
            self.storage.update_task(task)

            self.task_updated.emit(task.task_id)
            task = self.storage.get_task(task.task_id)
            self._show_detail(task)
            self._refresh_task_list()
        else:
            QMessageBox.critical(self, "Send Failed",
                                 "Could not send email. Check that Outlook is running.")

    def _send_reply(self):
        task = self._get_selected_task()
        if not task or self._replying_to is None:
            return

        emails_sorted = sorted(task.emails, key=lambda e: e.date_sort, reverse=True)
        if self._replying_to >= len(emails_sorted):
            return

        orig = emails_sorted[self._replying_to]
        reply_body = self._reply_edit.toPlainText().strip()
        if not reply_body:
            return

        # Store context for callback
        self._pending_reply_body = reply_body
        self._pending_reply_orig = orig

        self._send_reply_worker = outlook_bridge.SendReplyWorker(task, reply_body, orig, parent=self)
        self._send_reply_worker.finished.connect(self._on_send_reply_done)
        self._send_reply_worker.start()

    def _on_send_reply_done(self):
        success = getattr(self._send_reply_worker, 'success', False)
        task = self._get_selected_task()
        if not task:
            return

        if success:
            now = datetime.now()
            date_str = now.strftime("%b %d, %I:%M %p").replace(" 0", " ")
            date_sort = float(now.strftime("%Y%m%d")) + float(now.strftime("%H%M")) / 10000

            orig = self._pending_reply_orig
            reply_to = orig.from_addr if orig.type == "received" else orig.to_addr
            reply_email = Email(
                from_addr="You",
                to_addr=reply_to,
                date=date_str,
                date_sort=date_sort,
                subject=f"Re: [{task.task_id}] {task.title[:60]}",
                body=self._pending_reply_body,
                type="sent",
            )
            self.storage.add_email(task.task_id, reply_email)

            task = self.storage.get_task(task.task_id)
            task.last_activity = "Just now"
            task.last_activity_sort = 0
            task.last_activity_from = "You"
            self.storage.update_task(task)

            self._replying_to = None
            self._reply_text = ""
            self.task_updated.emit(task.task_id)
            task = self.storage.get_task(task.task_id)
            self._show_detail(task)
            self._refresh_task_list()
        else:
            QMessageBox.critical(self, "Reply Failed",
                                 "Could not send reply. Check that Outlook is running.")

    def _start_reply(self, idx: int):
        self._replying_to = idx
        task = self._get_selected_task()
        if task:
            self._render_tab_content(task)

    def _cancel_reply(self):
        self._replying_to = None
        task = self._get_selected_task()
        if task:
            self._render_tab_content(task)

    # ── Email expand/collapse ───────────────────────────────────────

    def _toggle_email_expand(self, idx: int):
        self._expanded_emails[idx] = not self._expanded_emails.get(idx, False)
        task = self._get_selected_task()
        if task:
            self._render_tab_content(task)

    def _on_email_search_changed(self, text: str):
        self._email_search_text = text.strip()
        task = self._get_selected_task()
        if task:
            self._render_tab_content(task)

    # ── Delete ──────────────────────────────────────────────────────

    def _show_delete_confirm(self):
        self._confirm_delete = True
        task = self._get_selected_task()
        if task:
            self._render_tab_content(task)

    def _cancel_delete(self):
        self._confirm_delete = False
        task = self._get_selected_task()
        if task:
            self._render_tab_content(task)

    def _delete_task(self):
        task = self._get_selected_task()
        if not task:
            return
        task_id = task.task_id
        self.storage.delete_task(task_id)
        self.task_deleted.emit(task_id)
        self._close_detail()

    # ════════════════════════════════════════════════════════════════
    #  BACKGROUND EMAIL SCANNING
    # ════════════════════════════════════════════════════════════════

    def _start_background_scan(self):
        """Kick off a background Outlook scan for new replies."""
        if self._scan_worker and self._scan_worker.isRunning():
            return  # Previous scan still running

        task_ids = self.storage.get_task_ids_with_email()
        if not task_ids:
            return

        known_ids = self.storage.get_all_entry_ids()
        self._scan_worker = OutlookScanWorker(task_ids, known_ids, parent=self)
        self._scan_worker.results_ready.connect(self._on_scan_results)
        self._scan_worker.start()

    def _on_scan_results(self, results: list):
        """Handle new emails discovered by background scan."""
        if not results:
            return

        for task_id, email in results:
            task = self.storage.get_task(task_id)
            if task is None:
                continue

            # Store the email
            self.storage.add_email(task_id, email)

            # Update activity
            display, sort_h = _relative_time(
                datetime.now().strftime("%Y-%m-%dT%H:%M:%S")
            )
            task = self.storage.get_task(task_id)
            task.last_activity = display
            task.last_activity_sort = sort_h
            task.last_activity_from = email.from_addr
            self.storage.update_task(task)

        # Refresh UI
        self._refresh_task_list()
        if self._selected_task_id:
            task = self.storage.get_task(self._selected_task_id)
            if task:
                self._populate_right_panel(task)

    # ════════════════════════════════════════════════════════════════
    #  CLEANUP
    # ════════════════════════════════════════════════════════════════

    def closeEvent(self, event):
        """Stop timers and wait for background workers."""
        self._scan_timer.stop()
        if self._scan_worker and self._scan_worker.isRunning():
            self._scan_worker.wait(2000)
        if self._contact_worker and self._contact_worker.isRunning():
            self._contact_worker.wait(1000)
        super().closeEvent(event)
