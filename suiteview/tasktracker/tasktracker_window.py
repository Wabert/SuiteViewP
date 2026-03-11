"""
TaskTracker Window — Clean list-view UI for task tracking.

Rebuilt from scratch for a precise, aligned card layout.
Inherits frameless-window chrome from FramelessWindowBase.
"""

import logging
from datetime import datetime
from typing import List, Optional, Dict

from PyQt6.QtCore import Qt, QTimer, pyqtSignal, QPoint, QRectF
from PyQt6.QtGui import (
    QFont, QColor, QCursor, QPainter, QPen, QBrush, QPainterPath,
    QFontMetrics, QTextOption, QKeyEvent,
)
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QLineEdit, QPlainTextEdit, QFrame, QScrollArea, QSizePolicy,
    QMessageBox, QApplication, QGraphicsDropShadowEffect,
)

from suiteview.ui.widgets.frameless_window import FramelessWindowBase
from suiteview.tasktracker.constants import (
    C, FONT_FAMILY, MONO_FAMILY,
    STATUS_OPEN, STATUS_CLOSED,
    EMAIL_SCAN_INTERVAL_MS, VERSION,
)
from suiteview.tasktracker.models import Task, Email, Contact
from suiteview.tasktracker.storage import Storage
from suiteview.tasktracker import outlook_bridge
from suiteview.tasktracker.outlook_bridge import (
    OutlookScanWorker, ContactSearchWorker,
)
from suiteview.tasktracker.detail_window import DetailWindow

logger = logging.getLogger(__name__)


# ════════════════════════════════════════════════════════════════════
#  Layout constants — column widths for perfect alignment
# ════════════════════════════════════════════════════════════════════

# Margins inside each card
CARD_H_PAD = 12          # left/right padding inside cards
CARD_V_PAD = 2           # top/bottom padding inside cards

# Fixed column widths (pixels) — used by BOTH header row and card row 1
COL_ID_W       = 62      # "TSK-007"
COL_DATE_W     = 76      # "2026-02-08"
COL_ACTIVITY_W = 78      # dot + "Just now"
COL_SPACING    = 6       # gap between columns


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
#  Card colour logic
# ════════════════════════════════════════════════════════════════════

def _needs_attention(task: Task) -> bool:
    return bool(task.last_activity_from and task.last_activity_from != "You")


def _card_bg(task: Task) -> str:
    if _needs_attention(task):
        return "#FDE8EC"  # Pale crimson highlight for attention
    if task.status == STATUS_CLOSED:
        return "#f0f0f0"
    return "#F5EAED"  # Pale rose default


def _card_border(task: Task, selected: bool) -> str:
    if selected:
        return C.GOLD
    if _needs_attention(task):
        return "#DC143C"  # Crimson border for attention
    return "#B8C4CE"  # Cool grey default border


# ════════════════════════════════════════════════════════════════════
#  Expanding Text Input — Enter = newline, grows vertically
# ════════════════════════════════════════════════════════════════════

class ExpandingTextEdit(QPlainTextEdit):
    """A QPlainTextEdit that auto-expands vertically as content grows.

    Starts at single-line height.  Grows taller as text wraps or
    newlines are added, up to ``_MAX_H``.  Uses a deferred resize
    via QTimer.singleShot(0) so the measurement happens after Qt
    has finished its layout pass.
    """

    _MAX_H = 200

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setPlaceholderText("New task — type and press [+] to add")
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setLineWrapMode(QPlainTextEdit.LineWrapMode.WidgetWidth)
        self.setTabChangesFocus(True)

        # Calculate single-line height from font metrics + frame
        fm = QFontMetrics(self.font())
        self._line_h = fm.height()
        frame_w = self.frameWidth() * 2
        doc_margin = int(self.document().documentMargin()) * 2
        self._base_pad = frame_w + doc_margin
        self._min_h = self._line_h + self._base_pad

        self.setFixedHeight(self._min_h)
        self.textChanged.connect(self._schedule_grow)

    def _schedule_grow(self):
        """Defer resize so Qt has finished its layout pass."""
        QTimer.singleShot(0, self._grow)

    def _grow(self):
        """Measure document height with a clone and resize."""
        doc = self.document().clone()
        doc.setTextWidth(self.viewport().width())
        content_h = int(doc.size().height()) + self._base_pad
        h = max(self._min_h, min(self._MAX_H, content_h))
        if h != self.height():
            self.setFixedHeight(h)
        # Scrollbar only when maxed out
        if h >= self._MAX_H:
            self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        else:
            self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._grow()

    def reset(self):
        """Clear text and shrink back to minimum height."""
        self.clear()
        self.setFixedHeight(self._min_h)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)


# ════════════════════════════════════════════════════════════════════
#  Task Card — Two-row rounded card
# ════════════════════════════════════════════════════════════════════

class TaskCard(QFrame):
    """A compact, two-line card for the task list.

    Row 1: ID | Created | Activity | Assignee   (fixed-width columns)
    Row 2: First line of the title text (elided)

    Rounded corners, full-width, hover highlight.
    """

    clicked = pyqtSignal(str)  # task_id

    def __init__(self, task: Task, is_selected: bool = False, parent=None):
        super().__init__(parent)
        self.task = task
        self._is_selected = is_selected
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self._build()

    def _build(self):
        task = self.task
        selected = self._is_selected
        bg = _card_bg(task)
        border = _card_border(task, selected)
        border_w = 2 if selected else 1

        self.setStyleSheet(f"""
            TaskCard {{
                background: {bg};
                border: {border_w}px solid {border};
                border-radius: 8px;
            }}
            TaskCard:hover {{
                background: {'#E8D0D5' if not selected else bg};
            }}
        """)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(CARD_H_PAD, CARD_V_PAD, CARD_H_PAD, CARD_V_PAD)
        layout.setSpacing(2)

        # ── Row 1: fixed-width data columns ────────────────────────
        row1 = QHBoxLayout()
        row1.setSpacing(0)  # we manage spacing via fixed-width columns

        # Task ID — bold, mono, blue
        tid_lbl = QLabel(task.task_id)
        tid_lbl.setFixedWidth(COL_ID_W)
        tid_lbl.setStyleSheet(
            f"font-family: {MONO_FAMILY}; font-size: 13px; font-weight: bold;"
            f" color: {C.BLUE}; background: transparent; padding: 0;"
        )
        row1.addWidget(tid_lbl)

        # Spacer
        row1.addSpacing(COL_SPACING)

        # Created date
        date_lbl = QLabel(task.created_date)
        date_lbl.setFixedWidth(COL_DATE_W)
        date_lbl.setStyleSheet(
            f"font-size: 13px; color: {C.TEXT}; font-weight: 600;"
            f" background: transparent; padding: 0;"
        )
        row1.addWidget(date_lbl)

        # Spacer
        row1.addSpacing(COL_SPACING)

        # Activity column — dot + text
        act_container = QWidget()
        act_container.setFixedWidth(COL_ACTIVITY_W)
        act_container.setStyleSheet("background: transparent;")
        act_lay = QHBoxLayout(act_container)
        act_lay.setContentsMargins(0, 0, 0, 0)
        act_lay.setSpacing(4)

        if task.email_sent:
            dot_color = C.GREEN_DOT if _needs_attention(task) else C.YELLOW_DOT
            dot = QLabel()
            dot.setFixedSize(8, 8)
            dot.setStyleSheet(
                f"background: {dot_color}; border-radius: 4px;"
                f" min-width:8px; max-width:8px; min-height:8px; max-height:8px;"
            )
            act_lay.addWidget(dot, 0, Qt.AlignmentFlag.AlignVCenter)

        act_text = QLabel(task.last_activity or "—")
        act_text.setStyleSheet(
            f"font-size: 12px; color: {C.TEXT_MID}; background: transparent; padding: 0;"
        )
        act_lay.addWidget(act_text)
        act_lay.addStretch()
        row1.addWidget(act_container)

        # Spacer
        row1.addSpacing(COL_SPACING)

        # Assignee (takes remaining space)
        if not task.assignees:
            dash = QLabel("—")
            dash.setStyleSheet(
                f"font-size: 12px; color: {C.TEXT_LIGHT}; font-style: italic;"
                f" background: transparent; padding: 0;"
            )
            row1.addWidget(dash, 1)
        else:
            assignee_w = QWidget()
            assignee_w.setStyleSheet("background: transparent;")
            a_lay = QHBoxLayout(assignee_w)
            a_lay.setContentsMargins(0, 0, 0, 0)
            a_lay.setSpacing(4)
            for a in task.assignees:
                chip = QLabel(a.name)
                chip.setStyleSheet(
                    f"font-size: 11px; color: {C.BLUE};"
                    f" background: rgba(245,234,237,0.95);"
                    f" padding: 1px 6px; border-radius: 6px;"
                    f" border: 1px solid #C0808A; font-weight: 600;"
                )
                a_lay.addWidget(chip)
            a_lay.addStretch()
            row1.addWidget(assignee_w, 1)

        layout.addLayout(row1)

        # ── Row 2: title (first line only, elided to 60 chars) ─────
        first_line = task.title.split('\n')[0] if task.title else ""
        if len(first_line) > 60:
            first_line = first_line[:60] + "…"
        title_lbl = QLabel(first_line)
        title_lbl.setStyleSheet(
            f"font-size: 13px; color: {C.TEXT_MID}; background: transparent;"
            f" padding: 0 0 0 0;"
        )
        title_lbl.setWordWrap(False)
        title_lbl.setTextFormat(Qt.TextFormat.PlainText)
        layout.addWidget(title_lbl)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit(self.task.task_id)
        super().mousePressEvent(event)


# ════════════════════════════════════════════════════════════════════
#  Main window
# ════════════════════════════════════════════════════════════════════

class TaskTrackerWindow(FramelessWindowBase):
    """Task Tracker — clean list view with aligned columns."""

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

        # Background workers
        self._scan_worker: Optional[OutlookScanWorker] = None
        self._contact_worker: Optional[ContactSearchWorker] = None

        super().__init__(
            title="SuiteView:  Task Tracker",
            default_size=(480, 520),
            min_size=(200, 150),
            parent=parent,
            header_colors=("#DC143C", "#8B0A25", "#5A0A1E"),
            border_color="#708090",
        )

        # Detail window (separate companion window)
        self._detail_window = DetailWindow(
            storage=self.storage, parent_window=self
        )
        self._detail_window.task_updated.connect(self._on_detail_task_updated)
        self._detail_window.task_deleted.connect(self._on_detail_task_deleted)
        self._detail_window.closed_by_user.connect(self._on_detail_closed)

        # Periodic email scan timer
        self._scan_timer = QTimer(self)
        self._scan_timer.timeout.connect(self._start_background_scan)
        self._scan_timer.start(EMAIL_SCAN_INTERVAL_MS)

        # Initial scan after short delay
        QTimer.singleShot(3000, self._start_background_scan)

    # ════════════════════════════════════════════════════════════════
    #  BUILD CONTENT — called by FramelessWindowBase
    # ════════════════════════════════════════════════════════════════

    def build_content(self) -> QWidget:
        """Construct the entire content area below the title bar."""
        root = QWidget()
        root_lay = QVBoxLayout(root)
        root_lay.setContentsMargins(0, 0, 0, 0)
        root_lay.setSpacing(0)

        # ── 1) Quick-add input bar ──────────────────────────────────
        add_bar = QWidget()
        add_bar.setObjectName("addBar")
        add_bar.setSizePolicy(QSizePolicy.Policy.Expanding,
                              QSizePolicy.Policy.Preferred)
        add_bar.setStyleSheet(f"""
            #addBar {{
                background: {C.GOLD_PALE};
                border-bottom: 1px solid {C.GOLD_BORDER};
            }}
        """)
        add_lay = QHBoxLayout(add_bar)
        add_lay.setContentsMargins(8, 6, 8, 6)
        add_lay.setSpacing(6)

        add_btn = QPushButton("+")
        add_btn.setFixedSize(30, 30)
        add_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        add_btn.setStyleSheet(f"""
            QPushButton {{
                background: {C.GOLD}; color: #fff;
                border: none; border-radius: 8px;
                font-size: 20px; font-weight: 800;
            }}
            QPushButton:hover {{ background: #8A9BAD; }}
        """)
        add_btn.clicked.connect(self._on_quick_add)
        add_lay.addWidget(add_btn, 0, Qt.AlignmentFlag.AlignTop)

        self._quick_input = ExpandingTextEdit()
        self._quick_input.setStyleSheet(f"""
            QPlainTextEdit {{
                border: 1px solid {C.GOLD_BORDER};
                border-radius: 8px;
                padding: 4px 8px;
                font-size: 13px;
                font-family: {FONT_FAMILY};
                background: {C.WHITE};
            }}
            QPlainTextEdit:focus {{
                border-color: {C.GOLD};
            }}
        """)
        add_lay.addWidget(self._quick_input, 1)

        root_lay.addWidget(add_bar)

        # ── 2) Filter bar (Open / Closed + Search) ─────────────────
        filter_bar = QWidget()
        filter_bar.setObjectName("filterBar")
        filter_bar.setStyleSheet(f"""
            #filterBar {{
                background: {C.BLUE_PALE};
                border-bottom: 1px solid {C.BORDER};
            }}
        """)
        filt_lay = QHBoxLayout(filter_bar)
        filt_lay.setContentsMargins(8, 4, 8, 4)
        filt_lay.setSpacing(6)

        self._open_btn = QPushButton("Open")
        self._closed_btn = QPushButton("Closed")
        for btn, key in [(self._open_btn, STATUS_OPEN), (self._closed_btn, STATUS_CLOSED)]:
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.clicked.connect(lambda checked, k=key: self._set_status_filter(k))
        self._style_filter_buttons()

        filt_lay.addWidget(self._open_btn)
        filt_lay.addWidget(self._closed_btn)

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
        root_lay.addWidget(filter_bar)

        # ── 3) Column headers ──────────────────────────────────────
        hdr_bar = QWidget()
        hdr_bar.setObjectName("hdrBar")
        hdr_bar.setStyleSheet(f"""
            #hdrBar {{
                background: {C.BLUE_PALE};
                border-bottom: 1px solid {C.BORDER};
            }}
        """)
        hdr_lay = QHBoxLayout(hdr_bar)
        # Match card internal padding:  card_container margins (8) + card margins (CARD_H_PAD)
        hdr_lay.setContentsMargins(8 + CARD_H_PAD, 3, 8 + CARD_H_PAD, 3)
        hdr_lay.setSpacing(0)

        col_style = (
            f"font-size: 11px; font-weight: bold; color: {C.BLUE};"
            f" background: transparent; padding: 0;"
        )

        self._sort_labels: Dict[str, QLabel] = {}
        for col_key, col_text, col_w in [
            ("id",       "ID",       COL_ID_W),
            ("date",     "CREATED",  COL_DATE_W),
            ("activity", "ACTIVITY", COL_ACTIVITY_W),
            ("assignee", "ASSIGNEE", 0),          # 0 = stretch
        ]:
            lbl = QLabel(col_text + " ⇅")
            lbl.setStyleSheet(col_style)
            lbl.setCursor(Qt.CursorShape.PointingHandCursor)
            lbl.mousePressEvent = lambda e, k=col_key: self._handle_sort(k)
            self._sort_labels[col_key] = lbl

            if col_w > 0:
                lbl.setFixedWidth(col_w)
                hdr_lay.addWidget(lbl)
                hdr_lay.addSpacing(COL_SPACING)
            else:
                hdr_lay.addWidget(lbl, 1)

        root_lay.addWidget(hdr_bar)

        # ── 4) Scrollable card list ────────────────────────────────
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
            QScrollBar::add-line:vertical,
            QScrollBar::sub-line:vertical {{
                height: 0px;
            }}
        """)

        self._card_container = QWidget()
        self._card_container.setStyleSheet(f"background: {C.HEADER_FLAT};")
        self._card_layout = QVBoxLayout(self._card_container)
        self._card_layout.setContentsMargins(8, 6, 8, 6)
        self._card_layout.setSpacing(4)
        self._card_layout.addStretch()

        self._scroll.setWidget(self._card_container)
        root_lay.addWidget(self._scroll, 1)

        # ── 5) Footer — crimson gradient, slate text ──────────────
        footer = QWidget()
        footer.setObjectName("ttFooter")
        footer.setStyleSheet(f"""
            #ttFooter {{
                background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
                    stop:0 #DC143C, stop:0.5 #8B0A25, stop:1 #5A0A1E);
                border-top: 2px solid #708090;
            }}
        """)
        foot_lay = QHBoxLayout(footer)
        foot_lay.setContentsMargins(12, 5, 12, 5)

        self._count_label = QLabel("0 tasks")
        self._count_label.setStyleSheet(
            "font-size: 12px; color: #B0C0D0; background: transparent;"
        )
        foot_lay.addWidget(self._count_label)
        foot_lay.addStretch()

        date_lbl = QLabel(datetime.now().strftime("%A, %Y-%m-%d"))
        date_lbl.setStyleSheet(
            "font-size: 11px; color: rgba(176,192,208,0.6); background: transparent;"
        )
        foot_lay.addWidget(date_lbl)

        foot_lay.addSpacing(16)

        ver_lbl = QLabel(f"TaskTracker {VERSION}")
        ver_lbl.setStyleSheet(
            "font-size: 12px; color: #B0C0D0; background: transparent;"
        )
        foot_lay.addWidget(ver_lbl)
        root_lay.addWidget(footer)

        # ── Initial data load ──────────────────────────────────────
        self._refresh_task_list()
        return root

    # ════════════════════════════════════════════════════════════════
    #  TASK LIST — filter, sort, rebuild cards
    # ════════════════════════════════════════════════════════════════

    def _refresh_task_list(self):
        """Reload tasks from storage, apply filters/sort, rebuild cards."""
        all_tasks = self.storage.get_all_tasks()

        # Filter by status
        tasks = [t for t in all_tasks if t.status == self._status_filter]

        # Filter by search text
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

        # Clear existing cards
        while self._card_layout.count():
            item = self._card_layout.takeAt(0)
            w = item.widget()
            if w:
                w.deleteLater()

        # Build new cards
        if not tasks:
            empty = QLabel("No tasks found")
            empty.setStyleSheet(
                "color: rgba(255,255,255,0.5); font-size: 15px;"
                " padding: 30px; background: transparent;"
            )
            empty.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self._card_layout.addWidget(empty)
        else:
            for task in tasks:
                card = TaskCard(task, is_selected=(task.task_id == self._selected_task_id))
                card.clicked.connect(self._on_card_clicked)
                self._card_layout.addWidget(card)

        self._card_layout.addStretch()

        # Update footer count
        self._count_label.setText(f"{len(tasks)} task{'s' if len(tasks) != 1 else ''}")

    # ════════════════════════════════════════════════════════════════
    #  EVENT HANDLERS
    # ════════════════════════════════════════════════════════════════

    # ── Quick-add ───────────────────────────────────────────────────

    def _on_quick_add(self):
        """Create a new task from the quick-add input."""
        title = self._quick_input.toPlainText().strip()
        if not title:
            return
        task = self.storage.create_task(title)
        self._quick_input.reset()
        self._selected_task_id = task.task_id
        self._refresh_task_list()
        self.task_created.emit(task.task_id)

    # ── Card click ──────────────────────────────────────────────────

    def _on_card_clicked(self, task_id: str):
        """Select / deselect a task card; toggle detail window."""
        if self._selected_task_id == task_id:
            # Deselect — hide detail window
            self._selected_task_id = None
            self._detail_window.hide()
        else:
            # Select — show detail window for this task
            self._selected_task_id = task_id
            task = self.storage.get_task(task_id)
            if task:
                self._detail_window.show_task(task)
        self._refresh_task_list()

    # ── Detail window callbacks ─────────────────────────────────────

    def _on_detail_task_updated(self, task_id: str):
        """Detail window changed a task — refresh the list."""
        self.task_updated.emit(task_id)
        self._refresh_task_list()

    def _on_detail_task_deleted(self, task_id: str):
        """Detail window deleted a task — deselect and refresh."""
        self._selected_task_id = None
        self.task_deleted.emit(task_id)
        self._refresh_task_list()

    def _on_detail_closed(self):
        """User closed detail window via its X button."""
        self._selected_task_id = None
        self._refresh_task_list()

    # ── Keep detail window docked on move/resize ───────────────────

    def moveEvent(self, event):
        super().moveEvent(event)
        self._detail_window.reposition()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._detail_window.reposition()

    def changeEvent(self, event):
        super().changeEvent(event)
        if event.type() == event.Type.ActivationChange and self.isActiveWindow():
            if self._detail_window.isVisible():
                self._detail_window.raise_()

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
            base_text = {
                "id": "ID", "date": "CREATED",
                "activity": "ACTIVITY", "assignee": "ASSIGNEE",
            }[key]
            if self._sort_col == key:
                arrow = " ▲" if self._sort_dir == "asc" else " ▼"
            else:
                arrow = " ⇅"
            lbl.setText(base_text + arrow)

    # ════════════════════════════════════════════════════════════════
    #  BACKGROUND EMAIL SCANNING
    # ════════════════════════════════════════════════════════════════

    def _start_background_scan(self):
        """Kick off a background Outlook scan for new replies."""
        if self._scan_worker and self._scan_worker.isRunning():
            return
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
            self.storage.add_email(task_id, email)
            display, sort_h = _relative_time(
                datetime.now().strftime("%Y-%m-%dT%H:%M:%S")
            )
            task = self.storage.get_task(task_id)
            task.last_activity = display
            task.last_activity_sort = sort_h
            task.last_activity_from = email.from_addr
            self.storage.update_task(task)
        self._refresh_task_list()

    # ════════════════════════════════════════════════════════════════
    #  CLEANUP
    # ════════════════════════════════════════════════════════════════

    def closeEvent(self, event):
        """Stop timers, close detail window, wait for workers."""
        self._scan_timer.stop()
        self._detail_window.hide()
        self._detail_window.deleteLater()
        if self._scan_worker and self._scan_worker.isRunning():
            self._scan_worker.wait(2000)
        if self._contact_worker and self._contact_worker.isRunning():
            self._contact_worker.wait(1000)
        super().closeEvent(event)
