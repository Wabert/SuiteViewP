"""
Frameless Window Base â€” Reusable frameless window with custom title bar.

Provides:
  - Custom title bar with gradient, title text, min/max/close buttons
  - Mouse drag-to-move with de-maximize-on-drag
  - 8-edge resize grips via ResizeEdge inner class + QSizeGrip
  - Gold border paint
  - Double-click title bar to maximize/restore

Subclasses override `build_content() -> QWidget` to provide their content.
"""

import logging
import sys
from typing import Optional

from PyQt6.QtCore import Qt, QPoint, QRect, QEvent, QSize
from PyQt6.QtGui import QColor, QPainter, QPen
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QFrame, QSizeGrip, QApplication, QDialog,
)

from suiteview.ui.widgets.window_state import NativeMinimizeMixin
from suiteview.ui.widgets.frame_geometry import (
    ALL_RESIZE_EDGES,
    cursor_for_resize_edge,
    detect_snap_edge,
    resize_edge_at,
    resize_geometry_for_edge,
    snap_rect_for_edge,
    update_cursor_for_resize_edge,
)

logger = logging.getLogger(__name__)

# ── Native Windows resize support ────────────────────────────────────────────
# Frameless windows resized purely in Python (per-mouse-move setGeometry) look
# glitchy on Windows because they bypass DWM's GPU-composited resize.  Handing
# resizing to the OS via WM_NCHITTEST + a native sizing frame (WS_THICKFRAME)
# gives smooth, artifact-free resizing while we keep our own title bar, drag,
# maximize/snap logic and painted border.
_IS_WINDOWS = sys.platform == "win32"

if _IS_WINDOWS:
    import ctypes
    from ctypes import wintypes

    _WM_NCCALCSIZE = 0x0083
    _WM_NCHITTEST = 0x0084
    _WM_GETMINMAXINFO = 0x0024

    _GWL_STYLE = -16
    _WS_THICKFRAME = 0x00040000
    _WS_CAPTION = 0x00C00000
    _WS_MAXIMIZEBOX = 0x00010000
    _WS_MINIMIZEBOX = 0x00020000
    _WS_SYSMENU = 0x00080000

    _SWP_NOMOVE = 0x0002
    _SWP_NOSIZE = 0x0001
    _SWP_NOZORDER = 0x0004
    _SWP_NOOWNERZORDER = 0x0200
    _SWP_FRAMECHANGED = 0x0020

    _MONITOR_DEFAULTTONEAREST = 2

    # Hit-test result codes returned to Windows so it performs a native resize.
    _HTCLIENT = 1
    _HTLEFT = 10
    _HTRIGHT = 11
    _HTTOP = 12
    _HTTOPLEFT = 13
    _HTTOPRIGHT = 14
    _HTBOTTOM = 15
    _HTBOTTOMLEFT = 16
    _HTBOTTOMRIGHT = 17

    class _MONITORINFO(ctypes.Structure):
        _fields_ = [
            ("cbSize", wintypes.DWORD),
            ("rcMonitor", wintypes.RECT),
            ("rcWork", wintypes.RECT),
            ("dwFlags", wintypes.DWORD),
        ]

    class _MINMAXINFO(ctypes.Structure):
        _fields_ = [
            ("ptReserved", wintypes.POINT),
            ("ptMaxSize", wintypes.POINT),
            ("ptMaxPosition", wintypes.POINT),
            ("ptMinTrackSize", wintypes.POINT),
            ("ptMaxTrackSize", wintypes.POINT),
        ]

    class _NCCALCSIZE_PARAMS(ctypes.Structure):
        _fields_ = [
            ("rgrc", wintypes.RECT * 3),
            ("lppos", ctypes.c_void_p),
        ]

    def _get_window_long(hwnd):
        user32 = ctypes.windll.user32
        if hasattr(user32, "GetWindowLongPtrW"):
            return user32.GetWindowLongPtrW(hwnd, _GWL_STYLE)
        return user32.GetWindowLongW(hwnd, _GWL_STYLE)

    def _set_window_long(hwnd, value):
        user32 = ctypes.windll.user32
        if hasattr(user32, "SetWindowLongPtrW"):
            return user32.SetWindowLongPtrW(hwnd, _GWL_STYLE, value)
        return user32.SetWindowLongW(hwnd, _GWL_STYLE, value)

    def _configure_win32_signatures():
        """Declare argtypes/restype for the Win32 calls we use.

        Without this, ctypes assumes 32-bit ints for every argument and return
        value, which truncates 64-bit window handles and pointers and corrupts
        the stack (hard crash / STATUS_STACK_BUFFER_OVERRUN)."""
        user32 = ctypes.windll.user32
        LONG_PTR = ctypes.c_longlong if ctypes.sizeof(ctypes.c_void_p) == 8 \
            else ctypes.c_long

        for name in ("GetWindowLongPtrW", "GetWindowLongW"):
            fn = getattr(user32, name, None)
            if fn is not None:
                fn.restype = LONG_PTR
                fn.argtypes = [wintypes.HWND, ctypes.c_int]
        for name in ("SetWindowLongPtrW", "SetWindowLongW"):
            fn = getattr(user32, name, None)
            if fn is not None:
                fn.restype = LONG_PTR
                fn.argtypes = [wintypes.HWND, ctypes.c_int, LONG_PTR]

        user32.SetWindowPos.restype = wintypes.BOOL
        user32.SetWindowPos.argtypes = [
            wintypes.HWND, wintypes.HWND, ctypes.c_int, ctypes.c_int,
            ctypes.c_int, ctypes.c_int, wintypes.UINT,
        ]
        user32.GetWindowRect.restype = wintypes.BOOL
        user32.GetWindowRect.argtypes = [
            wintypes.HWND, ctypes.POINTER(wintypes.RECT),
        ]
        user32.MonitorFromWindow.restype = ctypes.c_void_p
        user32.MonitorFromWindow.argtypes = [wintypes.HWND, wintypes.DWORD]
        user32.GetMonitorInfoW.restype = wintypes.BOOL
        user32.GetMonitorInfoW.argtypes = [
            ctypes.c_void_p, ctypes.POINTER(_MONITORINFO),
        ]

    try:
        _configure_win32_signatures()
    except Exception:  # pragma: no cover - defensive
        logger.exception("Failed to configure Win32 signatures; "
                         "native frameless resize disabled")
        _IS_WINDOWS = False


class FramelessWindowBase(NativeMinimizeMixin, QWidget):
    """Base class for frameless windows with a custom blue/gold title bar.

    Subclasses must override ``build_content()`` to return the main body widget.
    Optionally pass *title* and *default_size* to the constructor.
    """

    # â”€â”€ Construction â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

    def __init__(self, title: str = "SuiteView", default_size=(1000, 700),
                 min_size=(500, 450), parent=None,
                 header_colors=None, border_color="#D4A017",
                 header_widgets=None, header_prefix_widgets=None,
                 header_title_stretch=0):
        super().__init__(parent)

        # Theme colours -- header gradient stops & border
        self._header_colors = header_colors or (
            "#1E5BA8", "#0D3A7A", "#082B5C"  # default SuiteView blue
        )
        self._border_color = border_color
        self._header_widgets = header_widgets or []
        self._header_prefix_widgets = header_prefix_widgets or []
        self._header_title_stretch = header_title_stretch

        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowMinMaxButtonsHint
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, False)
        self.setMouseTracking(True)

        self.resize(*default_size)
        self.setMinimumSize(*min_size)

        # Drag / resize state
        self._drag_pos: Optional[QPoint] = None
        self._is_maximized = False
        self._resize_margin = 6
        self._resizing = False
        self._resize_edge = None
        self._resize_start_pos = None
        self._start_geometry = None

        # Native (DWM) resize — smooth, artifact-free.  When active, the OS
        # handles edge/corner resizing via WM_NCHITTEST and the manual Python
        # resize path (edge widgets + mouse handlers) is disabled.
        self._native_resize = _IS_WINDOWS
        self._native_installed = False

        # Snap-to-edge state
        self._is_snapped = False
        self._normal_geometry: Optional[QRect] = None
        self._snap_preview: Optional["_SnapPreview"] = None
        self._snap_edge_threshold = 10  # px from screen edge to trigger snap

        self._window_title_text = title

        self._build_root(title)
        self._add_resize_grips()

    # â”€â”€ Root layout â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

    def _build_root(self, title: str):
        root = QVBoxLayout(self)
        root.setContentsMargins(2, 2, 2, 2)
        root.setSpacing(0)

        # Custom title bar
        self.header_bar = self._build_header_bar(title)
        root.addWidget(self.header_bar)

        # Subclass-provided content
        content = self.build_content()
        if content is not None:
            root.addWidget(content, 1)

        # Size display label (bottom-right, positioned absolutely)
        self._size_label = QLabel(self)
        self._size_label.setStyleSheet(
            "color: rgba(0,0,0,0.45); font-size: 9px; background: transparent;"
        )
        self._size_label.setAlignment(
            Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
        )
        self._size_label.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self._update_size_label()

    # â”€â”€ Override point â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

    def build_content(self) -> QWidget:
        """Return the main body widget for the window.

        Subclasses **must** override this.  The returned widget is added
        with stretch factor 1 below the title bar.
        """
        return QWidget()

    # â”€â”€ Header bar (custom title bar) â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

    def _apply_header_gradient(self):
        """(Re)paint the header bar with the current 3-stop gradient."""
        c1, c2, c3 = self._header_colors
        self.header_bar.setStyleSheet(f"""
            QFrame {{
                background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
                    stop:0 {c1}, stop:0.5 {c2}, stop:1 {c3});
                border: none;
            }}
        """)

    def header_prefix_widgets(self):
        """Return widgets placed before the title in the header bar."""
        return list(self._header_prefix_widgets)

    def header_widgets(self):
        """Return widgets placed between the title and window controls."""
        return list(self._header_widgets)

    def header_title_style(self):
        """Return the stylesheet for the header title label."""
        return """
            QLabel {
                color: #FFFFFF;
                font-size: 18px;
                font-weight: bold;
                font-style: italic;
                background: transparent;
            }
        """

    def set_header_colors(self, colors):
        """Swap the header gradient at runtime (e.g. a mode indicator)."""
        self._header_colors = tuple(colors)
        self._apply_header_gradient()

    def set_title(self, title: str):
        """Update the header title text at runtime."""
        self._window_title_text = title
        self._title_label.setText(title)

    def _build_header_bar(self, title: str) -> QFrame:
        bar = QFrame()
        bar.setFixedHeight(38)
        bar.setMouseTracking(True)
        self.header_bar = bar
        self._apply_header_gradient()
        bar.setCursor(Qt.CursorShape.ArrowCursor)
        bar.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        bar.customContextMenuRequested.connect(self._header_context_menu)

        layout = QHBoxLayout(bar)
        layout.setContentsMargins(12, 4, 8, 4)
        layout.setSpacing(8)

        for widget in self.header_prefix_widgets():
            layout.addWidget(widget)

        # Title (always plain text — a runtime set_title may carry
        # user-entered strings, e.g. a saved-case name)
        self._title_label = QLabel(title)
        self._title_label.setTextFormat(Qt.TextFormat.PlainText)
        self._title_label.setStyleSheet(self.header_title_style())
        self.title_label = self._title_label
        layout.addWidget(self._title_label, self._header_title_stretch)
        layout.addStretch()

        # Custom header widgets (injected)
        for widget in self.header_widgets():
            layout.addWidget(widget)

        # Window control buttons
        btn_style = f"""
            QPushButton {{
                background: transparent;
                border: none;
                min-width: 40px; max-width: 40px;
                min-height: 28px; max-height: 28px;
                font-size: 14px; font-weight: bold;
                color: {self._border_color};
            }}
            QPushButton:hover {{
                background-color: rgba(255, 255, 255, 0.15);
                color: {self._border_color};
            }}
        """

        min_btn = QPushButton("\u2013")
        min_btn.setStyleSheet(btn_style)
        min_btn.setToolTip("Minimize")
        min_btn.clicked.connect(self.showMinimized)
        layout.addWidget(min_btn)
        self.min_btn = min_btn
        self.minimize_btn = min_btn

        self.max_btn = QPushButton("\u25A1")
        self.max_btn.setStyleSheet(btn_style)
        self.max_btn.setToolTip("Maximize")
        self.max_btn.clicked.connect(self._toggle_maximize)
        layout.addWidget(self.max_btn)
        self.maximize_btn = self.max_btn

        close_btn = QPushButton("\u2715")
        close_btn.setStyleSheet(btn_style + f"""
            QPushButton:hover {{
                background-color: #E81123;
                color: {self._border_color};
            }}
        """)
        close_btn.setToolTip("Close")
        close_btn.clicked.connect(self.close)
        layout.addWidget(close_btn)
        self.close_btn = close_btn

        return bar

    # â”€â”€ Maximize toggle â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

    def _toggle_maximize(self):
        # Trust the real window state, not just our cached flag — the OS (or a
        # restore driven from outside Qt) can maximize/restore the window
        # without going through this method.
        if self.isMaximized() or self._is_maximized:
            self.showNormal()
            self._is_maximized = False
            self._is_snapped = False
            self._normal_geometry = None
            self.max_btn.setText("\u25A1")
            self.max_btn.setToolTip("Maximize")
        else:
            if not self._is_snapped:
                self._normal_geometry = self.geometry()
            self.showMaximized()
            self._is_maximized = True
            self._is_snapped = False
            self.max_btn.setText("\u274F")
            self.max_btn.setToolTip("Restore")

    # ── Minimize / restore ──────────────────────────────────────────────────
    # (showMinimized / restore_window come from NativeMinimizeMixin)

    def changeEvent(self, event):
        super().changeEvent(event)
        if event.type() == QEvent.Type.WindowStateChange:
            self._sync_window_state()

    def _sync_window_state(self):
        """Keep the cached maximize flags and button glyph in step with the
        real window state, which the OS can change behind our back (Win+Up,
        Aero snap, a native restore, the taskbar)."""
        if not hasattr(self, "max_btn"):
            return  # still constructing
        if self.isMinimized():
            # Flags describe the pre-minimize layout; leave them alone.
            return
        maximized = self.isMaximized()
        if maximized != self._is_maximized:
            self._is_maximized = maximized
            if maximized:
                self._is_snapped = False
        self.max_btn.setText("\u274F" if maximized else "\u25A1")
        self.max_btn.setToolTip("Restore" if maximized else "Maximize")

    # â”€â”€ Resize grips â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

    def _add_resize_grips(self):
        """Add resize grips to all edges and corners.

        When native (DWM) resizing is active we skip the manual overlay widgets
        entirely — Windows handles resizing via WM_NCHITTEST, so the Python
        grips would be redundant (and would fight the OS at the corners).
        """
        self.size_grip = QSizeGrip(self)
        self.size_grip.setStyleSheet("QSizeGrip { background-color: transparent; width: 16px; height: 16px; }")

        self._resize_widgets = []

        if self._native_resize:
            # Native resize handles all edges/corners; keep the grip object for
            # API/menu compatibility but hidden so it doesn't double-resize.
            self.size_grip.hide()
            return

        for edge in ALL_RESIZE_EDGES:
            w = _ResizeEdge(self, edge)
            self._resize_widgets.append((edge, w))
            w.raise_()
        self.size_grip.raise_()

    def set_size_grip_visible(self, visible: bool):
        """Show or hide the bottom-right corner resize grip."""
        if hasattr(self, 'size_grip'):
            self.size_grip.setVisible(visible)

    def _header_context_menu(self, pos):
        """Right-click menu on the header bar."""
        from PyQt6.QtWidgets import QMenu
        menu = QMenu(self)
        grip_visible = hasattr(self, 'size_grip') and self.size_grip.isVisible()
        act_grip = menu.addAction(
            "Hide resize grip" if grip_visible else "Show resize grip")
        chosen = menu.exec(self.header_bar.mapToGlobal(pos))
        if chosen is act_grip:
            self.set_size_grip_visible(not grip_visible)

    # â”€â”€ Edge detection helpers â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

    def _get_resize_edge(self, pos):
        return resize_edge_at(pos, self.rect(), self._resize_margin)

    @staticmethod
    def _cursor_for_edge(edge):
        return cursor_for_resize_edge(edge)

    def _update_cursor_for_edge(self, edge):
        update_cursor_for_resize_edge(self, edge)

    # â”€â”€ Event overrides â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

    def _update_size_label(self):
        """Update the W × H size label text and position."""
        w, h = self.width(), self.height()
        self._size_label.setText(f"{w} × {h}")
        lbl_w, lbl_h = 80, 14
        # Position to the left of the size grip, near bottom-right
        self._size_label.setGeometry(w - lbl_w - 20, h - lbl_h - 2, lbl_w, lbl_h)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        margin = 6
        w, h = self.width(), self.height()

        if hasattr(self, '_size_label'):
            self._update_size_label()

        if hasattr(self, 'size_grip'):
            self.size_grip.move(w - 16, h - 16)

        if hasattr(self, '_resize_widgets'):
            for edge_name, widget in self._resize_widgets:
                if edge_name == 'top':
                    widget.setGeometry(margin, 0, w - 2 * margin, margin)
                elif edge_name == 'bottom':
                    widget.setGeometry(margin, h - margin, w - 2 * margin, margin)
                elif edge_name == 'left':
                    widget.setGeometry(0, margin, margin, h - 2 * margin)
                elif edge_name == 'right':
                    widget.setGeometry(w - margin, margin, margin, h - 2 * margin)
                elif edge_name == 'top-left':
                    widget.setGeometry(0, 0, margin, margin)
                elif edge_name == 'top-right':
                    widget.setGeometry(w - margin, 0, margin, margin)
                elif edge_name == 'bottom-left':
                    widget.setGeometry(0, h - margin, margin, margin)
                elif edge_name == 'bottom-right':
                    widget.setGeometry(w - margin, h - margin, margin, margin)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            pos = event.pos()
            if not self._native_resize:
                edge = self._get_resize_edge(pos)
                if edge and not self._is_maximized:
                    self._resizing = True
                    self._resize_edge = edge
                    self._resize_start_pos = event.globalPosition().toPoint()
                    self._start_geometry = self.geometry()
                    event.accept()
                    return
            # Drag if click is in header bar
            if hasattr(self, 'header_bar') and self.header_bar.geometry().contains(pos):
                widget_at = self.childAt(pos)
                if not isinstance(widget_at, QPushButton):
                    self._drag_pos = event.globalPosition().toPoint()
                    event.accept()
                    return
        super().mousePressEvent(event)

    # ── Snap-to-edge helpers ──────────────────────────────────────────────

    def _detect_snap_edge(self, global_pos: QPoint) -> Optional[str]:
        """Return 'left' or 'right' if global_pos is near a screen edge."""
        screen = QApplication.screenAt(global_pos)
        if screen is None:
            return None
        return detect_snap_edge(
            global_pos, screen.availableGeometry(), self._snap_edge_threshold)

    def _show_snap_preview(self, edge: str, global_pos: QPoint):
        """Show a translucent overlay on the target half of the screen."""
        screen = QApplication.screenAt(global_pos)
        if screen is None:
            return
        target = snap_rect_for_edge(edge, screen.availableGeometry())

        if self._snap_preview is None:
            self._snap_preview = _SnapPreview()
        self._snap_preview.setGeometry(target)
        self._snap_preview.show()

    def _hide_snap_preview(self):
        if self._snap_preview is not None:
            self._snap_preview.hide()
            self._snap_preview.deleteLater()
            self._snap_preview = None

    def _snap_to_edge(self, edge: str, global_pos: QPoint):
        """Snap the window to the left or right half of the screen."""
        screen = QApplication.screenAt(global_pos)
        if screen is None:
            return
        if not self._is_snapped and not self._is_maximized:
            self._normal_geometry = self.geometry()

        target = snap_rect_for_edge(edge, screen.availableGeometry())

        self.setGeometry(target)
        self._is_snapped = True
        self._is_maximized = False
        self.max_btn.setText("\u25A1")
        self.max_btn.setToolTip("Maximize")

    def _unsnap_on_drag(self, event):
        """Restore window size when dragging away from a snapped state."""
        self._is_snapped = False
        restore_geo = self._normal_geometry or QRect(0, 0, 1000, 700)
        self._normal_geometry = None

        # Position so cursor stays proportionally placed in the title bar
        cursor = event.globalPosition().toPoint()
        new_w = restore_geo.width()
        self.resize(new_w, restore_geo.height())
        self.move(cursor.x() - new_w // 2, cursor.y() - 20)
        self._drag_pos = cursor

    # ── Event overrides (mouse) ─────────────────────────────────────────

    def mouseMoveEvent(self, event):
        pos = event.pos()
        if not event.buttons():
            if not self._native_resize:
                edge = self._get_resize_edge(pos)
                self._update_cursor_for_edge(edge)
            super().mouseMoveEvent(event)
            return

        if event.buttons() == Qt.MouseButton.LeftButton:
            # Resize
            if self._resizing and self._resize_edge and self._resize_start_pos is not None:
                delta = event.globalPosition().toPoint() - self._resize_start_pos
                geo = self._start_geometry
                self.setGeometry(resize_geometry_for_edge(
                    geo,
                    delta,
                    self._resize_edge,
                    QSize(self.minimumWidth(), self.minimumHeight()),
                ))
                event.accept()
                return

            # Drag
            if self._drag_pos is not None and not self._resizing:
                global_pos = event.globalPosition().toPoint()

                # Un-maximize on drag
                if self._is_maximized:
                    self._is_maximized = False
                    self.showNormal()
                    self.max_btn.setText("\u25A1")
                    new_geo = self.geometry()
                    self._drag_pos = global_pos
                    self.move(
                        self._drag_pos.x() - new_geo.width() // 2,
                        self._drag_pos.y() - 20,
                    )
                # Un-snap on drag
                elif self._is_snapped:
                    self._unsnap_on_drag(event)
                else:
                    delta = global_pos - self._drag_pos
                    self.move(self.pos() + delta)
                    self._drag_pos = global_pos

                # Show / hide snap preview while dragging
                snap_edge = self._detect_snap_edge(global_pos)
                if snap_edge:
                    self._show_snap_preview(snap_edge, global_pos)
                else:
                    self._hide_snap_preview()

                event.accept()
                return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if self._drag_pos is not None:
            global_pos = event.globalPosition().toPoint()
            snap_edge = self._detect_snap_edge(global_pos)
            if snap_edge and not self._is_maximized:
                self._snap_to_edge(snap_edge, global_pos)
            self._hide_snap_preview()

        self._drag_pos = None
        self._resizing = False
        self._resize_edge = None
        self._resize_start_pos = None
        super().mouseReleaseEvent(event)

    def mouseDoubleClickEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            if event.pos().y() <= 40:
                widget_at = self.childAt(event.pos())
                if not isinstance(widget_at, QPushButton):
                    self._toggle_maximize()
                    event.accept()
                    return
        super().mouseDoubleClickEvent(event)

    def paintEvent(self, event):
        super().paintEvent(event)
        painter = QPainter(self)
        painter.setPen(QPen(QColor(self._border_color), 2))
        painter.drawRect(self.rect().adjusted(0, 0, -1, -1))
        painter.end()

    # -- Native (DWM) resize -------------------------------------------------

    def showEvent(self, event):
        super().showEvent(event)
        if self._native_resize and not self._native_installed:
            self._install_native_frame()

    def _install_native_frame(self):
        """Give the frameless window a native sizing frame so Windows/DWM
        performs smooth, composited resizing.  The visible native title bar and
        borders are removed via WM_NCCALCSIZE, leaving our custom chrome."""
        try:
            hwnd = int(self.winId())
            style = _get_window_long(hwnd)
            style |= (_WS_THICKFRAME | _WS_CAPTION | _WS_MAXIMIZEBOX
                      | _WS_MINIMIZEBOX | _WS_SYSMENU)
            _set_window_long(hwnd, style)
            ctypes.windll.user32.SetWindowPos(
                hwnd, 0, 0, 0, 0, 0,
                _SWP_NOMOVE | _SWP_NOSIZE | _SWP_NOZORDER
                | _SWP_NOOWNERZORDER | _SWP_FRAMECHANGED,
            )
            self._native_installed = True
        except Exception:  # pragma: no cover - defensive; fall back to manual
            logger.exception("Failed to install native window frame; "
                             "falling back to manual resize")
            self._native_resize = False

    def nativeEvent(self, eventType, message):
        if self._native_resize and eventType in (b"windows_generic_MSG",
                                                  b"windows_dispatcher_MSG"):
            try:
                msg = wintypes.MSG.from_address(int(message))
            except Exception:
                return False, 0

            if msg.message == _WM_NCCALCSIZE:
                # Not shrinking the proposed rectangle makes the client area
                # fill the whole window (no native title bar / borders).  When
                # maximized, clamp to the monitor work area so the window
                # doesn't cover the taskbar — but never while the window is
                # iconic, or we'd pin a full-screen client rect onto a window
                # that is supposed to be minimized.
                if msg.wParam and self.isMaximized() and not self.is_iconic():
                    self._clamp_maximized_client(msg.lParam)
                return True, 0

            if msg.message == _WM_GETMINMAXINFO:
                # Constrain the maximized size to the monitor work area, then
                # let Qt/DefWindowProc apply it (return "not handled").
                self._apply_maxinfo(msg.hWnd, msg.lParam)
                return False, 0

            if msg.message == _WM_NCHITTEST:
                hit = self._native_hit_test(msg.hWnd, msg.lParam)
                if hit is not None:
                    return True, hit

        return False, 0

    def _native_hit_test(self, hwnd, lparam):
        """Return an HT* resize code when the cursor is over a window border,
        otherwise None (let Qt handle drag / clicks as HTCLIENT)."""
        if self.isMaximized() or self._is_maximized:
            return None

        x = ctypes.c_short(lparam & 0xFFFF).value
        y = ctypes.c_short((lparam >> 16) & 0xFFFF).value

        rect = wintypes.RECT()
        ctypes.windll.user32.GetWindowRect(hwnd, ctypes.byref(rect))

        border = max(1, round(self._resize_margin * self.devicePixelRatioF()))
        left = x < rect.left + border
        right = x >= rect.right - border
        top = y < rect.top + border
        bottom = y >= rect.bottom - border

        if top and left:
            return _HTTOPLEFT
        if top and right:
            return _HTTOPRIGHT
        if bottom and left:
            return _HTBOTTOMLEFT
        if bottom and right:
            return _HTBOTTOMRIGHT
        if left:
            return _HTLEFT
        if right:
            return _HTRIGHT
        if top:
            return _HTTOP
        if bottom:
            return _HTBOTTOM
        return None

    def _monitor_work_rect(self, hwnd):
        monitor = ctypes.windll.user32.MonitorFromWindow(
            hwnd, _MONITOR_DEFAULTTONEAREST)
        if not monitor:
            return None
        info = _MONITORINFO()
        info.cbSize = ctypes.sizeof(_MONITORINFO)
        if not ctypes.windll.user32.GetMonitorInfoW(
                monitor, ctypes.byref(info)):
            return None
        return info.rcWork

    def _clamp_maximized_client(self, lparam):
        try:
            params = _NCCALCSIZE_PARAMS.from_address(lparam)
            work = self._monitor_work_rect(int(self.winId()))
            if work is not None:
                params.rgrc[0] = work
        except Exception:
            logger.debug("clamp maximized client failed", exc_info=True)

    def _apply_maxinfo(self, hwnd, lparam):
        try:
            work = self._monitor_work_rect(hwnd)
            if work is None:
                return
            info = _MINMAXINFO.from_address(lparam)
            info.ptMaxPosition.x = 0
            info.ptMaxPosition.y = 0
            info.ptMaxSize.x = work.right - work.left
            info.ptMaxSize.y = work.bottom - work.top
            info.ptMaxTrackSize.x = work.right - work.left
            info.ptMaxTrackSize.y = work.bottom - work.top
        except Exception:
            logger.debug("apply maxinfo failed", exc_info=True)


# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•
#  Resize-edge helper widget (private)
# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•

class _ResizeEdge(QFrame):
    """Invisible frame placed on a window edge to handle drag-resize."""

    def __init__(self, parent_window: FramelessWindowBase, edge: str):
        super().__init__(parent_window)
        self.edge = edge
        self.parent_window = parent_window
        self.setMouseTracking(True)
        cursor = cursor_for_resize_edge(edge)
        if cursor:
            self.setCursor(cursor)
        self.setStyleSheet("background-color: transparent;")
        self._dragging = False
        self._start_pos = None
        self._start_geometry = None

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._dragging = True
            self._start_pos = event.globalPosition().toPoint()
            self._start_geometry = self.parent_window.geometry()
            event.accept()

    def mouseMoveEvent(self, event):
        if self._dragging and self._start_geometry:
            delta = event.globalPosition().toPoint() - self._start_pos
            self.parent_window.setGeometry(resize_geometry_for_edge(
                self._start_geometry,
                delta,
                self.edge,
                QSize(
                    self.parent_window.minimumWidth(),
                    self.parent_window.minimumHeight(),
                ),
            ))
            event.accept()

    def mouseReleaseEvent(self, event):
        self._dragging = False
        self._start_pos = None
        self._start_geometry = None


# ═══════════════════════════════════════════════════════════════════════════
#  Snap-preview overlay (private)
# ═══════════════════════════════════════════════════════════════════════════

class _SnapPreview(QWidget):
    """Translucent overlay that previews the snap target area."""

    def __init__(self):
        super().__init__(None, Qt.WindowType.FramelessWindowHint
                         | Qt.WindowType.WindowStaysOnTopHint
                         | Qt.WindowType.Tool)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)

    def paintEvent(self, event):
        painter = QPainter(self)
        # Translucent blue fill
        painter.fillRect(self.rect(), QColor(30, 91, 168, 60))
        # Subtle border
        painter.setPen(QPen(QColor(212, 160, 23, 140), 2))
        painter.drawRect(self.rect().adjusted(1, 1, -2, -2))
        painter.end()


# ═══════════════════════════════════════════════════════════════════════════
#  Frameless dialog — themed modal popup
# ═══════════════════════════════════════════════════════════════════════════

class FramelessDialog(QDialog):
    """Modal dialog wearing the SuiteView custom frame: gradient header with
    title and close button, painted border, drag-to-move on the header.

    A lightweight sibling of :class:`FramelessWindowBase` for popups — no
    resize grips, snap, or min/max. Callers add content to ``body_layout``
    (a QVBoxLayout inside the bordered frame) and theme via the same
    *header_colors* / *border_color* pair their main window uses.
    """

    def __init__(self, title: str, parent=None,
                 header_colors=None, border_color: str = "#D4A017",
                 body_color: str = "#FFFFFF"):
        super().__init__(parent, Qt.WindowType.Dialog
                         | Qt.WindowType.FramelessWindowHint)
        self._header_colors = header_colors or (
            "#1E5BA8", "#0D3A7A", "#082B5C"  # default SuiteView blue
        )
        self._border_color = border_color
        self._drag_pos: Optional[QPoint] = None

        root = QVBoxLayout(self)
        root.setContentsMargins(2, 2, 2, 2)
        root.setSpacing(0)
        root.addWidget(self._build_header_bar(title))

        body = QWidget()
        body.setObjectName("framelessDialogBody")
        body.setStyleSheet(
            f"#framelessDialogBody {{ background-color: {body_color}; }}")
        self.body_layout = QVBoxLayout(body)
        self.body_layout.setContentsMargins(12, 12, 12, 12)
        self.body_layout.setSpacing(8)
        root.addWidget(body, 1)

    def _build_header_bar(self, title: str) -> QFrame:
        bar = QFrame()
        bar.setFixedHeight(30)
        c1, c2, c3 = self._header_colors
        bar.setStyleSheet(f"""
            QFrame {{
                background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
                    stop:0 {c1}, stop:0.5 {c2}, stop:1 {c3});
                border: none;
            }}
        """)
        layout = QHBoxLayout(bar)
        layout.setContentsMargins(12, 2, 4, 2)
        layout.setSpacing(8)

        title_label = QLabel(title)
        title_label.setStyleSheet(
            "QLabel { color: #FFFFFF; font-size: 13px; font-weight: bold;"
            " font-style: italic; background: transparent; }")
        layout.addWidget(title_label)
        layout.addStretch()

        close_btn = QPushButton("✕")
        close_btn.setStyleSheet(f"""
            QPushButton {{
                background: transparent; border: none;
                min-width: 32px; max-width: 32px;
                min-height: 24px; max-height: 24px;
                font-size: 13px; font-weight: bold;
                color: {self._border_color};
            }}
            QPushButton:hover {{
                background-color: #E81123;
                color: {self._border_color};
            }}
        """)
        close_btn.setToolTip("Close")
        close_btn.clicked.connect(self.reject)
        layout.addWidget(close_btn)

        self._header_bar = bar
        return bar

    # Drag-to-move on the header bar
    def mousePressEvent(self, event):
        if (event.button() == Qt.MouseButton.LeftButton
                and self._header_bar.geometry().contains(event.position().toPoint())):
            self._drag_pos = (event.globalPosition().toPoint()
                              - self.frameGeometry().topLeft())
            event.accept()
        else:
            super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self._drag_pos is not None and event.buttons() & Qt.MouseButton.LeftButton:
            self.move(event.globalPosition().toPoint() - self._drag_pos)
            event.accept()
        else:
            super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        self._drag_pos = None
        super().mouseReleaseEvent(event)

    def paintEvent(self, event):
        super().paintEvent(event)
        painter = QPainter(self)
        painter.setPen(QPen(QColor(self._border_color), 2))
        painter.drawRect(self.rect().adjusted(0, 0, -1, -1))
        painter.end()
