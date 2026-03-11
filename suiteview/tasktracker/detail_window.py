"""
TaskTracker Detail Window — Companion panel that docks to the right
of the main Task Tracker list window.

Shows task details, description editing, assignee management,
email actions, and email trail with reply compose.

Inherits from DockableToolPanel for frameless docking behavior.
"""

import logging
from datetime import datetime
from typing import List, Optional

from PyQt6.QtCore import Qt, QTimer, pyqtSignal, QPoint, QRect, QSize
from PyQt6.QtGui import QFont, QColor, QCursor
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QLineEdit, QPlainTextEdit, QFrame, QScrollArea, QLayout,
    QSizePolicy, QMessageBox,
)

from suiteview.ui.widgets import DockableToolPanel
from suiteview.tasktracker.constants import (
    C, FONT_FAMILY, MONO_FAMILY,
    STATUS_OPEN, STATUS_CLOSED,
    DETAIL_DEFAULT_WIDTH, DETAIL_MIN_WIDTH, DETAIL_MAX_WIDTH,
)
from suiteview.tasktracker.models import Task, Email, Contact
from suiteview.tasktracker.storage import Storage
from suiteview.tasktracker.outlook_bridge import (
    ContactSearchWorker, SendTaskEmailWorker, SendReplyWorker,
)

logger = logging.getLogger(__name__)

_GAP = 0  # no gap between main window and detail window
_RESIZE_MARGIN = 6  # pixels on each edge that act as resize handle
_MIN_HEIGHT = 200


# ════════════════════════════════════════════════════════════════════
#  Flow layout helper (for assignee chips)
# ════════════════════════════════════════════════════════════════════

class _FlowLayout(QLayout):
    """Simple flow layout that wraps widgets horizontally."""

    def __init__(self, parent=None, h_spacing=6, v_spacing=6):
        super().__init__(parent)
        self._h_spacing = h_spacing
        self._v_spacing = v_spacing
        self._items = []

    def addItem(self, item):
        self._items.append(item)

    def count(self):
        return len(self._items)

    def itemAt(self, index):
        if 0 <= index < len(self._items):
            return self._items[index]
        return None

    def takeAt(self, index):
        if 0 <= index < len(self._items):
            return self._items.pop(index)
        return None

    def hasHeightForWidth(self):
        return True

    def heightForWidth(self, width):
        return self._do_layout(QRect(0, 0, width, 0), test_only=True)

    def setGeometry(self, rect):
        super().setGeometry(rect)
        self._do_layout(rect, test_only=False)

    def sizeHint(self):
        return self.minimumSize()

    def minimumSize(self):
        size = QSize()
        for item in self._items:
            size = size.expandedTo(item.minimumSize())
        m = self.contentsMargins()
        size += QSize(m.left() + m.right(), m.top() + m.bottom())
        return size

    def _do_layout(self, rect, test_only):
        m = self.contentsMargins()
        effective = rect.adjusted(m.left(), m.top(), -m.right(), -m.bottom())
        x = effective.x()
        y = effective.y()
        row_height = 0

        for item in self._items:
            space_x = self._h_spacing
            space_y = self._v_spacing
            next_x = x + item.sizeHint().width() + space_x
            if next_x - space_x > effective.right() and row_height > 0:
                x = effective.x()
                y = y + row_height + space_y
                next_x = x + item.sizeHint().width() + space_x
                row_height = 0
            if not test_only:
                item.setGeometry(QRect(QPoint(x, y), item.sizeHint()))
            x = next_x
            row_height = max(row_height, item.sizeHint().height())

        return y + row_height - rect.y() + m.bottom()


# ════════════════════════════════════════════════════════════════════
#  Section box helper
# ════════════════════════════════════════════════════════════════════

class _SectionBox(QFrame):
    """A labeled section card with beveled header strip.

    Each section gets a mini crimson-gradient header that echoes
    the panel header's 3-D look.  See DEV_GUIDE.md § Beveling.
    """

    def __init__(self, label: str, bg: str = C.WHITE, parent=None):
        super().__init__(parent)
        self.setStyleSheet(f"""
            _SectionBox {{
                background: {bg};
                border: 1px solid {C.GOLD};
                border-radius: 6px;
            }}
        """)
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # ── Beveled header strip ────────────────────────────────
        hdr_widget = QWidget()
        hdr_widget.setStyleSheet(f"""
            QWidget {{
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    stop:0 #B01030,   /* lighter crimson */
                    stop:1 #8B0A25);  /* deeper crimson  */
                border-top-left-radius: 5px;
                border-top-right-radius: 5px;
                border: none;
                border-bottom: 1px solid {C.GOLD};
            }}
        """)
        hdr_lay = QHBoxLayout(hdr_widget)
        hdr_lay.setContentsMargins(10, 5, 10, 5)

        lbl = QLabel(label)
        lbl.setStyleSheet(
            "font-size: 12px; font-weight: 700; color: #F5EAED;"
            " background: transparent; padding: 0; border: none;"
        )
        hdr_lay.addWidget(lbl)
        root.addWidget(hdr_widget)

        # ── Content area ────────────────────────────────────────
        self._inner = QVBoxLayout()
        self._inner.setContentsMargins(10, 8, 10, 10)
        self._inner.setSpacing(6)
        root.addLayout(self._inner)

    def content_layout(self) -> QVBoxLayout:
        return self._inner


# ════════════════════════════════════════════════════════════════════
#  Detail Window
# ════════════════════════════════════════════════════════════════════

class DetailWindow(DockableToolPanel):
    """Companion detail window that docks to the right of the main window.

    Inherits from DockableToolPanel for frameless docking, resize, and
    drag-to-undock / double-click-to-redock behavior.

    Signals
    -------
    task_updated(task_id)
        Emitted when the detail window modifies a task.
    task_deleted(task_id)
        Emitted when the detail window deletes a task.
    closed_by_user()
        Emitted when the user clicks the close button.
    """

    task_updated = pyqtSignal(str)
    task_deleted = pyqtSignal(str)
    closed_by_user = pyqtSignal()

    def __init__(self, storage: Storage, parent_window: QWidget, parent=None):
        self.storage = storage
        self._task: Optional[Task] = None

        # State
        self._detail_tab = "details"
        self._editing_description = False
        self._confirm_delete = False
        self._assign_search_text = ""
        self._show_assign_dropdown = False
        self._replying_to: Optional[int] = None
        self._reply_text = ""
        self._expanded_emails: dict = {}
        self._email_search = ""

        # Workers
        self._contact_worker: Optional[ContactSearchWorker] = None
        self._send_email_worker: Optional[SendTaskEmailWorker] = None
        self._send_reply_worker: Optional[SendReplyWorker] = None
        self._assign_debounce = QTimer()
        self._assign_debounce.setSingleShot(True)
        self._assign_debounce.setInterval(400)
        self._assign_debounce.timeout.connect(self._do_contact_search)

        # On first show, match parent width
        self._initial_width = None

        # Call base class __init__ -- this sets up window flags, docking,
        # resize/drag state, and calls build_header/build_body
        super().__init__(
            parent_window,
            default_width=480,
            min_width=DETAIL_MIN_WIDTH,
            min_height=_MIN_HEIGHT,
            border_color=C.GOLD,
            bg_color=C.BLUE_PALE,
            corner_radius=12.0,
            parent=parent,
        )

    # ════════════════════════════════════════════════════════════════
    #  PUBLIC API
    # ════════════════════════════════════════════════════════════════

    def show_task(self, task: Task):
        """Display a task and dock to the parent window."""
        self._task = task
        self._detail_tab = "details"
        self._editing_description = False
        self._confirm_delete = False
        self._assign_search_text = ""
        self._show_assign_dropdown = False
        self._replying_to = None
        self._reply_text = ""
        self._expanded_emails = {}
        self._email_search = ""
        # On first show, match parent width
        if self._initial_width is None:
            self._initial_width = self._parent_window.width()
            self.resize(self._initial_width, self.height())
        self._rebuild_content()
        # Use base class docking
        self.show_docked()

    def current_task_id(self) -> Optional[str]:
        return self._task.task_id if self._task else None

    # ════════════════════════════════════════════════════════════════
    #  DockableToolPanel overrides: build_header / build_body
    # ════════════════════════════════════════════════════════════════

    def build_header(self) -> QWidget:
        """Return the header widget for dragging/docking.

        Uses beveled gradient (lighter crimson top → darker bottom)
        to simulate overhead lighting, with a slate accent border
        for visual pop.  See DEV_GUIDE.md § Beveling / Embossing.
        """
        header = QWidget()
        header.setStyleSheet(f"""
            background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                stop:0 #DC143C,   /* bright crimson – light source */
                stop:1 #8B0A25);  /* deep crimson – shadow */
            border-top-left-radius: 12px;
            border-top-right-radius: 12px;
            border-bottom: 2px solid {C.GOLD}; /* slate accent */
        """)
        hdr_lay = QHBoxLayout(header)
        hdr_lay.setContentsMargins(12, 8, 8, 8)

        self._hdr_title = QLabel("Task Details")
        self._hdr_title.setStyleSheet(
            "color: #B0C0D0; font-size: 18px; font-weight: 700;"
            " background: transparent; border: none;"
        )
        self._hdr_task_id = QLabel("")
        self._hdr_task_id.setStyleSheet(
            f"font-family: {MONO_FAMILY}; font-size: 16px;"
            f" color: {C.GOLD}; font-weight: 700;"
            f" background: transparent; border: none;"
        )
        hdr_lay.addWidget(self._hdr_title)
        hdr_lay.addSpacing(10)
        hdr_lay.addWidget(self._hdr_task_id)
        hdr_lay.addStretch()

        _hdr_btn_style = """
            QPushButton {
                background: rgba(255,255,255,0.15); color: #B0C0D0;
                border: none; border-radius: 4px; font-size: 15px;
            }
            QPushButton:hover { background: rgba(255,255,255,0.3); }
        """

        close_btn = QPushButton("✕")
        close_btn.setFixedSize(28, 28)
        close_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        close_btn.setStyleSheet(_hdr_btn_style)
        close_btn.clicked.connect(self._on_close_clicked)
        hdr_lay.addWidget(close_btn)

        return header

    def build_body(self) -> QWidget:
        """Return the main body widget (status bar, tabs, scroll area)."""
        body_container = QWidget()
        body_container.setStyleSheet(f"background: {C.BLUE_PALE}; border: none;")
        body_lay = QVBoxLayout(body_container)
        body_lay.setContentsMargins(0, 0, 0, 0)
        body_lay.setSpacing(0)

        # ── Status / Created bar (subtle emboss) ────────────────────
        self._status_bar = QWidget()
        self._status_bar.setStyleSheet(f"""
            background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                stop:0 #FFFFFF, stop:1 #F0EAED);
            border-bottom: 1px solid {C.BORDER};
        """)
        sb_lay = QHBoxLayout(self._status_bar)
        sb_lay.setContentsMargins(12, 6, 12, 6)

        self._created_label = QLabel()
        self._created_label.setStyleSheet(
            f"font-size: 13px; color: {C.TEXT_MID};"
            f" background: transparent; border: none;"
        )
        sb_lay.addWidget(self._created_label)
        sb_lay.addStretch()

        status_lbl = QLabel("Status:")
        status_lbl.setStyleSheet(
            f"font-size: 13px; color: {C.TEXT}; font-weight: 600;"
            f" background: transparent; border: none;"
        )
        sb_lay.addWidget(status_lbl)
        sb_lay.addSpacing(6)

        self._status_btn = QPushButton("OPEN")
        self._status_btn.setFixedHeight(24)
        self._status_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._status_btn.clicked.connect(self._toggle_status)
        sb_lay.addWidget(self._status_btn)
        body_lay.addWidget(self._status_bar)

        # ── Email-sent banner (shown only when email has been sent) ─
        self._email_sent_banner = QLabel()
        self._email_sent_banner.setStyleSheet(
            f"font-size: 12px; font-weight: 600; color: {C.GREEN};"
            f" background: {C.GOLD_PALE}; border: none;"
            f" padding: 4px 12px;"
        )
        self._email_sent_banner.hide()
        body_lay.addWidget(self._email_sent_banner)

        # ── Tab bar (subtle emboss) ──────────────────────────────────
        self._tab_bar = QWidget()
        self._tab_bar.setStyleSheet(f"""
            background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                stop:0 #FAFAFA, stop:1 #F0EAED);
            border-bottom: 1px solid {C.BORDER};
        """)
        tb_lay = QHBoxLayout(self._tab_bar)
        tb_lay.setContentsMargins(0, 0, 0, 0)
        tb_lay.setSpacing(0)

        self._details_tab_btn = QPushButton("Details")
        self._emails_tab_btn = QPushButton("Email Trail (0)")
        for btn in (self._details_tab_btn, self._emails_tab_btn):
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.setStyleSheet(self._tab_style(False))
        self._details_tab_btn.clicked.connect(lambda: self._set_tab("details"))
        self._emails_tab_btn.clicked.connect(lambda: self._set_tab("emails"))
        tb_lay.addWidget(self._details_tab_btn)
        tb_lay.addWidget(self._emails_tab_btn)
        tb_lay.addStretch()
        body_lay.addWidget(self._tab_bar)

        # ── Scrollable body ─────────────────────────────────────────
        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(True)
        self._scroll.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )
        self._scroll.setStyleSheet(f"""
            QScrollArea {{
                border: none; background: {C.BLUE_PALE};
            }}
            QScrollBar:vertical {{
                background: {C.BLUE_PALE}; width: 8px;
            }}
            QScrollBar::handle:vertical {{
                background: rgba(139,10,37,0.3); border-radius: 4px;
            }}
            QScrollBar::add-line:vertical,
            QScrollBar::sub-line:vertical {{ height: 0px; }}
        """)

        self._body = QWidget()
        self._body.setStyleSheet(f"background: {C.BLUE_PALE}; border: none;")
        self._body_layout = QVBoxLayout(self._body)
        self._body_layout.setContentsMargins(12, 10, 12, 10)
        self._body_layout.setSpacing(10)
        self._body_layout.addStretch()

        self._scroll.setWidget(self._body)
        body_lay.addWidget(self._scroll, 1)

        return body_container

    def on_closed(self):
        """Emit closed_by_user signal when panel is closed."""
        self.closed_by_user.emit()

    # ════════════════════════════════════════════════════════════════
    #  REBUILD CONTENT
    # ════════════════════════════════════════════════════════════════

    def _rebuild_content(self):
        """Clear and repopulate the scrollable body from self._task."""
        if not self._task:
            return
        task = self._task

        # Header
        self._hdr_task_id.setText(task.task_id)
        self._created_label.setText(
            f"<b style='color:{C.TEXT}'>Created:</b> {task.created_date}"
        )

        # Status button
        is_open = task.status == STATUS_OPEN
        self._status_btn.setText("OPEN" if is_open else "CLOSED")
        bg = C.RED if is_open else C.BLUE
        self._status_btn.setStyleSheet(f"""
            QPushButton {{
                padding: 3px 14px; border-radius: 4px;
                font-size: 12px; font-weight: 700;
                border: none; background: {bg}; color: #fff;
            }}
            QPushButton:hover {{ opacity: 0.9; }}
        """)

        # Email-sent banner
        if task.email_sent:
            self._email_sent_banner.setText(
                f"\u2713 Email sent \u2014 tracking via [{task.task_id}]"
            )
            self._email_sent_banner.show()
        else:
            self._email_sent_banner.hide()

        # Tab labels
        n_emails = len(task.emails)
        self._emails_tab_btn.setText(f"Email Trail ({n_emails})")
        self._style_tabs()

        # Clear body
        while self._body_layout.count():
            item = self._body_layout.takeAt(0)
            w = item.widget()
            if w:
                w.deleteLater()

        if self._detail_tab == "details":
            self._build_details_tab()
        else:
            self._build_emails_tab()

        self._body_layout.addStretch()

    # ── Tab styling ─────────────────────────────────────────────────

    def _tab_style(self, active: bool) -> str:
        bg = C.GOLD_PALE if active else "transparent"
        border_b = f"3px solid {C.GOLD}" if active else "3px solid transparent"
        color = C.BLUE if active else C.TEXT_LIGHT
        return f"""
            QPushButton {{
                padding: 8px 18px; border: none; border-bottom: {border_b};
                background: {bg}; font-size: 14px; font-weight: 700;
                color: {color};
            }}
            QPushButton:hover {{ background: {C.GOLD_PALE}; }}
        """

    def _style_tabs(self):
        self._details_tab_btn.setStyleSheet(
            self._tab_style(self._detail_tab == "details")
        )
        self._emails_tab_btn.setStyleSheet(
            self._tab_style(self._detail_tab == "emails")
        )

    def _set_tab(self, tab: str):
        self._detail_tab = tab
        self._replying_to = None
        self._reply_text = ""
        self._rebuild_content()

    # ════════════════════════════════════════════════════════════════
    #  DETAILS TAB
    # ════════════════════════════════════════════════════════════════

    def _build_details_tab(self):
        task = self._task

        # ── Description section ─────────────────────────────────────
        desc_box = _SectionBox("Description")
        lay = desc_box.content_layout()

        if self._editing_description:
            self._desc_edit = QPlainTextEdit(task.title)
            self._desc_edit.setStyleSheet(f"""
                QPlainTextEdit {{
                    border: 1px solid {C.GOLD}; border-radius: 4px;
                    padding: 6px 8px; font-size: 14px;
                    font-family: {FONT_FAMILY}; background: {C.WHITE};
                    min-height: 60px;
                }}
            """)
            lay.addWidget(self._desc_edit)

            btn_row = QHBoxLayout()
            btn_row.setSpacing(6)
            save_btn = QPushButton("Save")
            save_btn.setCursor(Qt.CursorShape.PointingHandCursor)
            save_btn.setStyleSheet(f"""
                QPushButton {{
                    padding: 4px 12px; background: {C.BLUE}; color: #fff;
                    border: none; border-radius: 3px;
                    font-size: 12px; font-weight: 600;
                }}
                QPushButton:hover {{ background: {C.BLUE_LIGHT}; }}
            """)
            save_btn.clicked.connect(self._save_description)
            cancel_btn = QPushButton("Cancel")
            cancel_btn.setCursor(Qt.CursorShape.PointingHandCursor)
            cancel_btn.setStyleSheet(f"""
                QPushButton {{
                    padding: 4px 12px; background: {C.WHITE}; color: {C.TEXT_MID};
                    border: 1px solid {C.BORDER}; border-radius: 3px;
                    font-size: 12px; font-weight: 600;
                }}
            """)
            cancel_btn.clicked.connect(self._cancel_description_edit)
            btn_row.addWidget(save_btn)
            btn_row.addWidget(cancel_btn)
            btn_row.addStretch()
            lay.addLayout(btn_row)
        else:
            desc_lbl = QLabel(task.title)
            desc_lbl.setWordWrap(True)
            desc_lbl.setStyleSheet(
                f"font-size: 14px; line-height: 1.6; color: {C.TEXT_MID};"
                f" background: transparent; border: none; min-height: 30px;"
            )
            desc_lbl.setCursor(Qt.CursorShape.PointingHandCursor)
            desc_lbl.mousePressEvent = lambda e: self._start_description_edit()
            lay.addWidget(desc_lbl)

            hint = QLabel("Click to edit")
            hint.setStyleSheet(
                f"font-size: 11px; color: {C.TEXT_LIGHT};"
                f" font-style: italic; background: transparent; border: none;"
            )
            lay.addWidget(hint)

        self._body_layout.addWidget(desc_box)

        # ── Assigned To section ─────────────────────────────────────
        assign_box = _SectionBox("Assigned To")
        a_lay = assign_box.content_layout()

        if task.assignees:
            chip_container = QWidget()
            chip_container.setStyleSheet("background: transparent; border: none;")
            chip_flow = _FlowLayout(chip_container, h_spacing=6, v_spacing=6)
            for assignee in task.assignees:
                chip = self._make_assignee_chip(assignee)
                chip_flow.addWidget(chip)
            a_lay.addWidget(chip_container)

        placeholder = (
            "Add another person..."
            if task.assignees
            else "Type a name or email to assign..."
        )
        self._assign_input = QLineEdit()
        self._assign_input.setPlaceholderText(placeholder)
        self._assign_input.setText(self._assign_search_text)
        self._assign_input.setStyleSheet(f"""
            QLineEdit {{
                padding: 6px 10px; border: 1px solid {C.GOLD};
                border-radius: 4px; font-size: 13px;
                font-family: {FONT_FAMILY}; background: {C.GOLD_PALE};
            }}
        """)
        self._assign_input.textChanged.connect(self._on_assign_search_changed)
        self._assign_input.returnPressed.connect(self._on_assign_enter)
        a_lay.addWidget(self._assign_input)

        if self._show_assign_dropdown and self._assign_search_text.strip():
            self._build_assign_dropdown(a_lay)

        self._body_layout.addWidget(assign_box)

        # ── Send email button (below Assigned To, only if not yet sent) ─
        if task.assignees and not task.email_sent:
            if len(task.assignees) == 1:
                btn_text = (
                    f"\u2709 SEND TASK TO "
                    f"{task.assignees[0].name.split()[0].upper()}"
                )
            else:
                btn_text = f"\u2709 SEND TASK TO {len(task.assignees)} PEOPLE"
            send_btn = QPushButton(btn_text)
            send_btn.setCursor(Qt.CursorShape.PointingHandCursor)
            send_btn.setStyleSheet(f"""
                QPushButton {{
                    padding: 6px 16px; background: {C.GOLD};
                    color: #fff; border: none; border-radius: 4px;
                    font-size: 13px; font-weight: 700;
                }}
                QPushButton:hover {{ background: #8A9BAD; }}
            """)
            send_btn.clicked.connect(self._send_task_email)
            self._body_layout.addWidget(send_btn)

        # ── Delete task ─────────────────────────────────────────────
        delete_area = QWidget()
        delete_area.setStyleSheet(f"background: transparent; border: none;")
        d_lay = QHBoxLayout(delete_area)
        d_lay.setContentsMargins(0, 10, 0, 0)

        if not self._confirm_delete:
            del_btn = QPushButton("🗑 Delete Task")
            del_btn.setCursor(Qt.CursorShape.PointingHandCursor)
            del_btn.setStyleSheet(f"""
                QPushButton {{
                    padding: 5px 14px; background: {C.WHITE};
                    color: {C.RED}; border: 1px solid {C.RED};
                    border-radius: 4px; font-size: 12px; font-weight: 600;
                }}
                QPushButton:hover {{ background: {C.RED_CARD}; }}
            """)
            del_btn.clicked.connect(self._request_delete)
            d_lay.addWidget(del_btn)
        else:
            confirm_lbl = QLabel(f"Delete {task.task_id}?")
            confirm_lbl.setStyleSheet(
                f"font-size: 13px; color: {C.RED}; font-weight: 600;"
                f" background: transparent; border: none;"
            )
            d_lay.addWidget(confirm_lbl)
            d_lay.addSpacing(8)

            yes_btn = QPushButton("Yes")
            yes_btn.setCursor(Qt.CursorShape.PointingHandCursor)
            yes_btn.setStyleSheet(f"""
                QPushButton {{
                    padding: 4px 12px; background: {C.RED}; color: #fff;
                    border: none; border-radius: 4px;
                    font-size: 12px; font-weight: 700;
                }}
            """)
            yes_btn.clicked.connect(self._do_delete_task)
            d_lay.addWidget(yes_btn)

            no_btn = QPushButton("Cancel")
            no_btn.setCursor(Qt.CursorShape.PointingHandCursor)
            no_btn.setStyleSheet(f"""
                QPushButton {{
                    padding: 4px 12px; background: {C.WHITE};
                    color: {C.TEXT_MID}; border: 1px solid {C.BORDER};
                    border-radius: 4px; font-size: 12px; font-weight: 600;
                }}
            """)
            no_btn.clicked.connect(self._cancel_delete)
            d_lay.addWidget(no_btn)

        d_lay.addStretch()
        self._body_layout.addWidget(delete_area)

    # ════════════════════════════════════════════════════════════════
    #  EMAILS TAB
    # ════════════════════════════════════════════════════════════════

    def _build_emails_tab(self):
        task = self._task

        # Search bar
        search = QLineEdit()
        search.setPlaceholderText("Search emails...")
        search.setText(self._email_search)
        search.setStyleSheet(f"""
            QLineEdit {{
                padding: 5px 10px; border: 1px solid {C.BORDER};
                border-radius: 4px; font-size: 13px;
                font-family: {FONT_FAMILY}; background: {C.WHITE};
            }}
        """)
        search.textChanged.connect(self._on_email_search_changed)
        self._body_layout.addWidget(search)

        # Sort emails newest first
        sorted_emails = sorted(
            task.emails, key=lambda e: e.date_sort, reverse=True
        )

        # Filter by search
        if self._email_search.strip():
            s = self._email_search.strip().lower()
            sorted_emails = [
                e for e in sorted_emails
                if s in e.subject.lower()
                or s in e.body.lower()
                or s in e.from_addr.lower()
                or s in e.to_addr.lower()
            ]

        if not task.emails:
            empty = QFrame()
            empty.setStyleSheet(f"""
                QFrame {{
                    border: 1px dashed {C.BORDER}; border-radius: 4px;
                    background: transparent; padding: 20px;
                }}
            """)
            e_lay = QVBoxLayout(empty)
            e_lay.setAlignment(Qt.AlignmentFlag.AlignCenter)
            icon = QLabel("✉")
            icon.setStyleSheet(
                "font-size: 24px; opacity: 0.4;"
                " background: transparent; border: none;"
            )
            icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
            e_lay.addWidget(icon)
            title = QLabel("No emails yet")
            title.setStyleSheet(
                f"font-size: 14px; font-weight: 600; color: {C.TEXT_LIGHT};"
                f" background: transparent; border: none;"
            )
            title.setAlignment(Qt.AlignmentFlag.AlignCenter)
            e_lay.addWidget(title)
            sub = QLabel("Assign someone and send to start tracking")
            sub.setStyleSheet(
                f"font-size: 12px; color: {C.TEXT_LIGHT};"
                f" background: transparent; border: none;"
            )
            sub.setAlignment(Qt.AlignmentFlag.AlignCenter)
            e_lay.addWidget(sub)
            self._body_layout.addWidget(empty)

        elif not sorted_emails:
            no_match = QLabel("No emails match your search")
            no_match.setStyleSheet(
                f"font-size: 13px; color: {C.TEXT_LIGHT};"
                f" background: transparent; border: none; padding: 20px;"
            )
            no_match.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self._body_layout.addWidget(no_match)

        else:
            for idx, email in enumerate(sorted_emails):
                card = self._make_email_card(email, idx)
                self._body_layout.addWidget(card)

        # ── Reply compose area ──────────────────────────────────────
        if self._replying_to is not None and sorted_emails:
            all_sorted = sorted(
                task.emails, key=lambda e: e.date_sort, reverse=True
            )
            if self._replying_to < len(all_sorted):
                orig = all_sorted[self._replying_to]
                reply_to_name = (
                    orig.to_addr if orig.from_addr == "You" else orig.from_addr
                )

                sep = QFrame()
                sep.setFixedHeight(2)
                sep.setStyleSheet(f"background: {C.GOLD}; border: none;")
                self._body_layout.addWidget(sep)

                reply_hdr = QLabel(
                    f"Replying to: <span style='color:{C.BLUE}'>"
                    f"{reply_to_name}</span>"
                )
                reply_hdr.setStyleSheet(
                    f"font-size: 12px; color: {C.TEXT_MID}; font-weight: 600;"
                    f" background: transparent; border: none;"
                )
                self._body_layout.addWidget(reply_hdr)

                self._reply_edit = QPlainTextEdit()
                self._reply_edit.setPlaceholderText("Type your response...")
                self._reply_edit.setPlainText(self._reply_text)
                self._reply_edit.setStyleSheet(f"""
                    QPlainTextEdit {{
                        border: 1px solid {C.GOLD}; border-radius: 4px;
                        padding: 6px 8px; font-size: 13px;
                        font-family: {FONT_FAMILY}; min-height: 60px;
                        background: {C.WHITE};
                    }}
                """)
                self._reply_edit.textChanged.connect(
                    lambda: setattr(
                        self, '_reply_text',
                        self._reply_edit.toPlainText()
                    )
                )
                self._body_layout.addWidget(self._reply_edit)

                btn_row = QHBoxLayout()
                btn_row.setSpacing(6)
                send_btn = QPushButton("✉ Send Reply")
                send_btn.setCursor(Qt.CursorShape.PointingHandCursor)
                send_btn.setStyleSheet(f"""
                    QPushButton {{
                        padding: 5px 14px; background: {C.BLUE};
                        color: #fff; border: none; border-radius: 4px;
                        font-size: 12px; font-weight: 700;
                    }}
                    QPushButton:hover {{ background: {C.BLUE_LIGHT}; }}
                """)
                send_btn.clicked.connect(self._send_reply)
                cancel_btn = QPushButton("Cancel")
                cancel_btn.setCursor(Qt.CursorShape.PointingHandCursor)
                cancel_btn.setStyleSheet(f"""
                    QPushButton {{
                        padding: 5px 14px; background: {C.WHITE};
                        color: {C.TEXT_MID};
                        border: 1px solid {C.BORDER};
                        border-radius: 4px;
                        font-size: 12px; font-weight: 600;
                    }}
                """)
                cancel_btn.clicked.connect(self._cancel_reply)
                btn_row.addWidget(send_btn)
                btn_row.addWidget(cancel_btn)
                btn_row.addStretch()
                self._body_layout.addLayout(btn_row)

    # ════════════════════════════════════════════════════════════════
    #  WIDGET FACTORIES
    # ════════════════════════════════════════════════════════════════

    def _make_assignee_chip(self, contact: Contact) -> QFrame:
        """Build a rounded chip showing initials + name + remove button."""
        chip = QFrame()
        chip.setStyleSheet(f"""
            QFrame {{
                background: {C.BLUE_PALE};
                border: 1px solid {C.BORDER};
                border-radius: 12px;
            }}
        """)
        c_lay = QHBoxLayout(chip)
        c_lay.setContentsMargins(7, 2, 5, 2)
        c_lay.setSpacing(5)

        initials = "".join(
            p[0] for p in contact.name.split() if p
        )[:2].upper()
        init_lbl = QLabel(initials)
        init_lbl.setFixedSize(20, 20)
        init_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        init_lbl.setStyleSheet(f"""
            background: {C.WHITE}; border: 1px solid {C.BORDER};
            border-radius: 10px; font-size: 8px; font-weight: 700;
            color: {C.BLUE};
        """)
        c_lay.addWidget(init_lbl)

        name_lbl = QLabel(contact.name)
        name_lbl.setStyleSheet(
            f"font-size: 12px; font-weight: 600; color: {C.BLUE};"
            f" background: transparent; border: none;"
        )
        c_lay.addWidget(name_lbl)

        rm_btn = QPushButton("×")
        rm_btn.setFixedSize(16, 16)
        rm_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        rm_btn.setStyleSheet(f"""
            QPushButton {{
                background: none; border: none;
                color: {C.RED}; font-size: 13px;
                font-weight: 700; padding: 0;
            }}
        """)
        rm_btn.clicked.connect(
            lambda _, e=contact.email, n=contact.name: self._remove_assignee(e, n)
        )
        c_lay.addWidget(rm_btn)

        return chip

    def _make_email_card(self, email: Email, idx: int) -> QFrame:
        """Build a single email card for the Email Trail tab."""
        border_color = C.BLUE if email.type == "sent" else C.GOLD
        card = QFrame()
        card.setStyleSheet(f"""
            QFrame {{
                background: {C.WHITE};
                border: 1px solid {C.BORDER};
                border-left: 3px solid {border_color};
                border-radius: 4px;
            }}
        """)
        c_lay = QVBoxLayout(card)
        c_lay.setContentsMargins(8, 4, 8, 4)
        c_lay.setSpacing(2)

        # Top row: from -> to  |  date  Reply
        top = QHBoxLayout()
        top.setSpacing(6)

        from_lbl = QLabel(email.from_addr)
        from_color = C.BLUE if email.type == "sent" else C.GOLD
        from_lbl.setStyleSheet(
            f"font-size: 13px; font-weight: 700; color: {from_color};"
            f" background: transparent; border: none;"
        )
        top.addWidget(from_lbl)

        arrow = QLabel("→")
        arrow.setStyleSheet(
            f"color: {C.TEXT_LIGHT}; background: transparent; border: none;"
        )
        top.addWidget(arrow)

        to_lbl = QLabel(email.to_addr)
        to_lbl.setStyleSheet(
            f"font-size: 13px; color: {C.TEXT_LIGHT};"
            f" background: transparent; border: none;"
        )
        to_lbl.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred
        )
        top.addWidget(to_lbl, 1)

        if email.has_attachment:
            att = QLabel("📎")
            att.setStyleSheet("background: transparent; border: none;")
            att.setToolTip("Has attachment")
            top.addWidget(att)

        date_lbl = QLabel(email.date)
        date_lbl.setStyleSheet(
            f"font-size: 11px; color: {C.TEXT_LIGHT};"
            f" background: transparent; border: none;"
        )
        top.addWidget(date_lbl)

        reply_btn = QPushButton("Reply")
        reply_btn.setFixedHeight(20)
        reply_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        reply_btn.setStyleSheet(f"""
            QPushButton {{
                padding: 2px 8px; background: {C.BLUE}; color: #fff;
                border: none; border-radius: 3px;
                font-size: 10px; font-weight: 700;
            }}
            QPushButton:hover {{ background: {C.BLUE_LIGHT}; }}
        """)
        reply_btn.clicked.connect(lambda _, i=idx: self._start_reply(i))
        top.addWidget(reply_btn)

        c_lay.addLayout(top)

        # Body (click to expand / collapse)
        is_expanded = self._expanded_emails.get(idx, False)
        body_text = email.body if is_expanded else (
            email.body[:70] + "…" if len(email.body) > 70 else email.body
        )

        body_lbl = QLabel(body_text)
        body_lbl.setWordWrap(True)
        body_lbl.setStyleSheet(
            f"font-size: 13px; color: {C.TEXT_MID}; line-height: 1.5;"
            f" background: transparent; border: none;"
        )
        body_lbl.setCursor(Qt.CursorShape.PointingHandCursor)
        body_lbl.mousePressEvent = lambda e, i=idx: self._toggle_email_expand(i)
        c_lay.addWidget(body_lbl)

        return card

    def _build_assign_dropdown(self, parent_layout: QVBoxLayout):
        """Build the contact dropdown below the assign search input."""
        contacts = self.storage.get_contacts()
        q = self._assign_search_text.strip().lower()
        filtered = [
            c for c in contacts
            if q in c.name.lower() or q in c.email.lower()
        ]
        assigned_emails = {
            a.email for a in self._task.assignees if a.email
        }
        filtered = [c for c in filtered if c.email not in assigned_emails]

        dropdown = QFrame()
        dropdown.setStyleSheet(f"""
            QFrame {{
                background: {C.WHITE};
                border: 1px solid {C.BORDER};
                border-radius: 4px;
            }}
        """)
        dd_lay = QVBoxLayout(dropdown)
        dd_lay.setContentsMargins(0, 0, 0, 0)
        dd_lay.setSpacing(0)

        for c in filtered[:8]:
            row = QPushButton(f"{c.name}   ({c.email})")
            row.setCursor(Qt.CursorShape.PointingHandCursor)
            row.setStyleSheet(f"""
                QPushButton {{
                    text-align: left; padding: 7px 12px;
                    border: none; font-size: 13px;
                    border-bottom: 1px solid {C.BLUE_PALE};
                    background: {C.WHITE};
                }}
                QPushButton:hover {{ background: {C.GOLD_PALE}; }}
            """)
            row.clicked.connect(
                lambda _, contact=c: self._assign_contact(contact)
            )
            dd_lay.addWidget(row)

        if not filtered:
            freeform = QPushButton(
                f'+ Assign to "{self._assign_search_text.strip()}"'
            )
            freeform.setCursor(Qt.CursorShape.PointingHandCursor)
            freeform.setStyleSheet(f"""
                QPushButton {{
                    text-align: left; padding: 7px 12px;
                    border: none; font-size: 13px; color: {C.BLUE};
                    font-weight: 600; background: {C.WHITE};
                }}
                QPushButton:hover {{ background: {C.GOLD_PALE}; }}
            """)
            freeform.clicked.connect(self._assign_freeform)
            dd_lay.addWidget(freeform)
        else:
            freeform = QPushButton(
                f'+ Use "{self._assign_search_text.strip()}" as new contact'
            )
            freeform.setCursor(Qt.CursorShape.PointingHandCursor)
            freeform.setStyleSheet(f"""
                QPushButton {{
                    text-align: left; padding: 5px 12px;
                    border: none; font-size: 11px; color: {C.TEXT_LIGHT};
                    border-top: 1px solid {C.BORDER};
                    background: {C.WHITE};
                }}
                QPushButton:hover {{ background: {C.GOLD_PALE}; }}
            """)
            freeform.clicked.connect(self._assign_freeform)
            dd_lay.addWidget(freeform)

        parent_layout.addWidget(dropdown)

    # ════════════════════════════════════════════════════════════════
    #  ACTION HANDLERS
    # ════════════════════════════════════════════════════════════════

    def _on_close_clicked(self):
        self.hide()
        self.on_closed()  # calls our override which emits closed_by_user

    # ── Status toggle ───────────────────────────────────────────────

    def _toggle_status(self):
        if not self._task:
            return
        self._task.status = (
            STATUS_CLOSED if self._task.status == STATUS_OPEN else STATUS_OPEN
        )
        self.storage.update_task(self._task)
        self.task_updated.emit(self._task.task_id)
        self._rebuild_content()

    # ── Description ─────────────────────────────────────────────────

    def _start_description_edit(self):
        self._editing_description = True
        self._rebuild_content()

    def _save_description(self):
        new_text = self._desc_edit.toPlainText().strip()
        if new_text and self._task:
            self._task.title = new_text
            self.storage.update_task(self._task)
            self.task_updated.emit(self._task.task_id)
        self._editing_description = False
        self._rebuild_content()

    def _cancel_description_edit(self):
        self._editing_description = False
        self._rebuild_content()

    # ── Assignee management ─────────────────────────────────────────

    def _on_assign_search_changed(self, text: str):
        self._assign_search_text = text
        self._show_assign_dropdown = bool(text.strip())
        self._assign_debounce.start()
        self._rebuild_content()
        QTimer.singleShot(0, lambda: (
            self._assign_input.setFocus()
            if hasattr(self, '_assign_input') else None
        ))

    def _on_assign_enter(self):
        """Enter key in assign input — pick first match or freeform."""
        if not self._assign_search_text.strip():
            return
        contacts = self.storage.get_contacts()
        q = self._assign_search_text.strip().lower()
        filtered = [
            c for c in contacts
            if q in c.name.lower() or q in c.email.lower()
        ]
        assigned_emails = {
            a.email for a in self._task.assignees if a.email
        }
        filtered = [c for c in filtered if c.email not in assigned_emails]
        if filtered:
            self._assign_contact(filtered[0])
        else:
            self._assign_freeform()

    def _assign_contact(self, contact: Contact):
        if not self._task:
            return
        self.storage.add_assignee(self._task.task_id, contact)
        self._task = self.storage.get_task(self._task.task_id)
        self._assign_search_text = ""
        self._show_assign_dropdown = False
        self.task_updated.emit(self._task.task_id)
        self._rebuild_content()

    def _assign_freeform(self):
        if not self._task:
            return
        text = self._assign_search_text.strip()
        if not text:
            return
        if "@" in text:
            contact = Contact(name=text.split("@")[0], email=text)
        else:
            contact = Contact(name=text, email="")
        self.storage.add_assignee(self._task.task_id, contact)
        self.storage.add_contact(contact.name, contact.email)
        self._task = self.storage.get_task(self._task.task_id)
        self._assign_search_text = ""
        self._show_assign_dropdown = False
        self.task_updated.emit(self._task.task_id)
        self._rebuild_content()

    def _remove_assignee(self, email: str, name: str):
        if not self._task:
            return
        self.storage.remove_assignee(
            self._task.task_id, email=email, name=name
        )
        self._task = self.storage.get_task(self._task.task_id)
        self.task_updated.emit(self._task.task_id)
        self._rebuild_content()

    def _do_contact_search(self):
        """Fire background GAL search."""
        query = self._assign_search_text
        if len(query) < 3:
            return
        if self._contact_worker and self._contact_worker.isRunning():
            return
        self._contact_worker = ContactSearchWorker(query, parent=self)
        self._contact_worker.results_ready.connect(self._on_gal_results)
        self._contact_worker.start()

    def _on_gal_results(self, results: List[Contact]):
        for c in results:
            self.storage.add_contact(c.name, c.email)
        if self._show_assign_dropdown:
            self._rebuild_content()

    # ── Delete ──────────────────────────────────────────────────────

    def _request_delete(self):
        self._confirm_delete = True
        self._rebuild_content()

    def _cancel_delete(self):
        self._confirm_delete = False
        self._rebuild_content()

    def _do_delete_task(self):
        if not self._task:
            return
        task_id = self._task.task_id
        self.storage.delete_task(task_id)
        self._task = None
        self.hide()
        self.task_deleted.emit(task_id)

    # ── Email send ──────────────────────────────────────────────────

    def _send_task_email(self):
        if not self._task or not self._task.assignees:
            return
        body = self._task.title
        self._send_email_worker = SendTaskEmailWorker(
            self._task, body, parent=self
        )
        self._send_email_worker.finished.connect(self._on_send_email_done)
        self._send_email_worker.start()

    def _on_send_email_done(self):
        success = getattr(self._send_email_worker, 'success', False)
        if not self._task:
            return
        if success:
            now = datetime.now()
            date_str = now.strftime("%b %d, %I:%M %p").replace(" 0", " ")
            date_sort = (
                float(now.strftime("%Y%m%d"))
                + float(now.strftime("%H%M")) / 10000
            )
            for a in self._task.assignees:
                if a.email:
                    email = Email(
                        from_addr="You",
                        to_addr=a.email,
                        date=date_str,
                        date_sort=date_sort,
                        subject=f"[{self._task.task_id}] "
                                f"{self._task.title[:60]}",
                        body=self._task.title,
                        type="sent",
                        has_attachment=False,
                    )
                    self.storage.add_email(self._task.task_id, email)
            self._task = self.storage.get_task(self._task.task_id)
            self._task.email_sent = True
            self._task.last_activity = "Just now"
            self._task.last_activity_sort = 0
            self._task.last_activity_from = "You"
            self.storage.update_task(self._task)
            self.task_updated.emit(self._task.task_id)
            self._rebuild_content()
        else:
            QMessageBox.critical(
                self, "Send Failed",
                "Could not send email. Check that Outlook is running."
            )

    # ── Reply ───────────────────────────────────────────────────────

    def _on_email_search_changed(self, text: str):
        self._email_search = text
        self._rebuild_content()

    def _toggle_email_expand(self, idx: int):
        self._expanded_emails[idx] = not self._expanded_emails.get(idx, False)
        self._rebuild_content()

    def _start_reply(self, idx: int):
        self._replying_to = idx
        self._reply_text = ""
        self._rebuild_content()

    def _cancel_reply(self):
        self._replying_to = None
        self._reply_text = ""
        self._rebuild_content()

    def _send_reply(self):
        if not self._task or self._replying_to is None:
            return
        sorted_emails = sorted(
            self._task.emails, key=lambda e: e.date_sort, reverse=True
        )
        if self._replying_to >= len(sorted_emails):
            return
        orig = sorted_emails[self._replying_to]
        reply_body = self._reply_text.strip()
        if not reply_body:
            return
        self._pending_reply_body = reply_body
        self._pending_reply_orig = orig
        self._send_reply_worker = SendReplyWorker(
            self._task, reply_body, orig, parent=self
        )
        self._send_reply_worker.send_complete.connect(self._on_reply_done)
        self._send_reply_worker.start()

    def _on_reply_done(self, success: bool):
        if not self._task:
            return
        if success:
            now = datetime.now()
            date_str = now.strftime("%b %d, %I:%M %p").replace(" 0", " ")
            date_sort = (
                float(now.strftime("%Y%m%d"))
                + float(now.strftime("%H%M")) / 10000
            )
            orig = self._pending_reply_orig
            reply_to = (
                orig.from_addr if orig.type == "received" else orig.to_addr
            )
            reply_email = Email(
                from_addr="You",
                to_addr=reply_to,
                date=date_str,
                date_sort=date_sort,
                subject=f"Re: [{self._task.task_id}] "
                        f"{self._task.title[:60]}",
                body=self._pending_reply_body,
                type="sent",
            )
            self.storage.add_email(self._task.task_id, reply_email)
            self._task = self.storage.get_task(self._task.task_id)
            self._task.last_activity = "Just now"
            self._task.last_activity_sort = 0
            self._task.last_activity_from = "You"
            self.storage.update_task(self._task)
            self._replying_to = None
            self._reply_text = ""
            self.task_updated.emit(self._task.task_id)
            self._rebuild_content()
        else:
            QMessageBox.critical(
                self, "Reply Failed",
                "Could not send reply. Check that Outlook is running."
            )
