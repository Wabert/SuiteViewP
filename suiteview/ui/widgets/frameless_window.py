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
from typing import Optional

from PyQt6.QtCore import Qt, QPoint, QRect
from PyQt6.QtGui import QColor, QPainter, QPen
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QFrame, QSizeGrip, QApplication,
)

logger = logging.getLogger(__name__)


class FramelessWindowBase(QWidget):
    """Base class for frameless windows with a custom blue/gold title bar.

    Subclasses must override ``build_content()`` to return the main body widget.
    Optionally pass *title* and *default_size* to the constructor.
    """

    # â”€â”€ Construction â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

    def __init__(self, title: str = "SuiteView", default_size=(1000, 700),
                 min_size=(500, 450), parent=None,
                 header_colors=None, border_color="#D4A017",
                 header_widgets=None):
        super().__init__(parent)

        # Theme colours -- header gradient stops & border
        self._header_colors = header_colors or (
            "#1E5BA8", "#0D3A7A", "#082B5C"  # default SuiteView blue
        )
        self._border_color = border_color
        self._header_widgets = header_widgets or []

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

    def _build_header_bar(self, title: str) -> QFrame:
        bar = QFrame()
        bar.setFixedHeight(38)
        bar.setMouseTracking(True)
        c1, c2, c3 = self._header_colors
        bar.setStyleSheet(f"""
            QFrame {{
                background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
                    stop:0 {c1}, stop:0.5 {c2}, stop:1 {c3});
                border: none;
            }}
        """)
        bar.setCursor(Qt.CursorShape.ArrowCursor)
        bar.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        bar.customContextMenuRequested.connect(self._header_context_menu)

        layout = QHBoxLayout(bar)
        layout.setContentsMargins(12, 4, 8, 4)
        layout.setSpacing(8)

        # Title
        self._title_label = QLabel(title)
        self._title_label.setStyleSheet("""
            QLabel {
                color: #FFFFFF;
                font-size: 18px;
                font-weight: bold;
                font-style: italic;
                background: transparent;
            }
        """)
        layout.addWidget(self._title_label)
        layout.addStretch()

        # Custom header widgets (injected)
        for widget in self._header_widgets:
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

        self.max_btn = QPushButton("\u25A1")
        self.max_btn.setStyleSheet(btn_style)
        self.max_btn.setToolTip("Maximize")
        self.max_btn.clicked.connect(self._toggle_maximize)
        layout.addWidget(self.max_btn)

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

        return bar

    # â”€â”€ Maximize toggle â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

    def _toggle_maximize(self):
        if self._is_maximized:
            self.showNormal()
            self._is_maximized = False
            self._is_snapped = False
            self._normal_geometry = None
            self.max_btn.setText("\u25A1")
            self.max_btn.setToolTip("Maximize")
        else:
            if not self._is_maximized and not self._is_snapped:
                self._normal_geometry = self.geometry()
            self.showMaximized()
            self._is_maximized = True
            self._is_snapped = False
            self.max_btn.setText("\u274F")
            self.max_btn.setToolTip("Restore")

    # â”€â”€ Resize grips â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

    def _add_resize_grips(self):
        """Add resize grips to all edges and corners."""
        self.size_grip = QSizeGrip(self)
        self.size_grip.setStyleSheet("QSizeGrip { background-color: transparent; width: 16px; height: 16px; }")

        self._resize_widgets = []

        for edge in ('top', 'bottom', 'left', 'right',
                     'top-left', 'top-right', 'bottom-left'):
            w = _ResizeEdge(self, edge)
            self._resize_widgets.append((edge, w))

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
        margin = self._resize_margin
        rect = self.rect()
        left = pos.x() < margin
        right = pos.x() > rect.width() - margin
        top = pos.y() < margin
        bottom = pos.y() > rect.height() - margin

        if top and left:     return 'top-left'
        if top and right:    return 'top-right'
        if bottom and left:  return 'bottom-left'
        if bottom and right: return 'bottom-right'
        if left:   return 'left'
        if right:  return 'right'
        if top:    return 'top'
        if bottom: return 'bottom'
        return None

    @staticmethod
    def _cursor_for_edge(edge):
        cursors = {
            'left':         Qt.CursorShape.SizeHorCursor,
            'right':        Qt.CursorShape.SizeHorCursor,
            'top':          Qt.CursorShape.SizeVerCursor,
            'bottom':       Qt.CursorShape.SizeVerCursor,
            'top-left':     Qt.CursorShape.SizeFDiagCursor,
            'bottom-right': Qt.CursorShape.SizeFDiagCursor,
            'top-right':    Qt.CursorShape.SizeBDiagCursor,
            'bottom-left':  Qt.CursorShape.SizeBDiagCursor,
        }
        return cursors.get(edge)

    def _update_cursor_for_edge(self, edge):
        cursor = self._cursor_for_edge(edge)
        if cursor:
            self.setCursor(cursor)
        else:
            self.unsetCursor()

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
            self.size_grip.raise_()

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
                widget.raise_()

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            pos = event.pos()
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
        avail = screen.availableGeometry()
        threshold = self._snap_edge_threshold
        if global_pos.x() <= avail.left() + threshold:
            return 'left'
        if global_pos.x() >= avail.right() - threshold:
            return 'right'
        return None

    def _show_snap_preview(self, edge: str, global_pos: QPoint):
        """Show a translucent overlay on the target half of the screen."""
        screen = QApplication.screenAt(global_pos)
        if screen is None:
            return
        avail = screen.availableGeometry()
        if edge == 'left':
            target = QRect(avail.x(), avail.y(),
                           avail.width() // 2, avail.height())
        else:
            half_w = avail.width() // 2
            target = QRect(avail.x() + half_w, avail.y(),
                           avail.width() - half_w, avail.height())

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
        avail = screen.availableGeometry()

        if not self._is_snapped and not self._is_maximized:
            self._normal_geometry = self.geometry()

        if edge == 'left':
            target = QRect(avail.x(), avail.y(),
                           avail.width() // 2, avail.height())
        else:
            half_w = avail.width() // 2
            target = QRect(avail.x() + half_w, avail.y(),
                           avail.width() - half_w, avail.height())

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
            edge = self._get_resize_edge(pos)
            self._update_cursor_for_edge(edge)
            super().mouseMoveEvent(event)
            return

        if event.buttons() == Qt.MouseButton.LeftButton:
            # Resize
            if self._resizing and self._resize_edge and self._resize_start_pos is not None:
                delta = event.globalPosition().toPoint() - self._resize_start_pos
                geo = self._start_geometry
                new_x, new_y = geo.x(), geo.y()
                new_w, new_h = geo.width(), geo.height()
                min_w = self.minimumWidth()
                min_h = self.minimumHeight()
                right_edge = geo.x() + geo.width()
                bottom_edge = geo.y() + geo.height()

                if 'left' in self._resize_edge:
                    new_w = max(min_w, geo.width() - delta.x())
                    new_x = right_edge - new_w
                if 'right' in self._resize_edge:
                    new_w = max(min_w, geo.width() + delta.x())
                if 'top' in self._resize_edge:
                    new_h = max(min_h, geo.height() - delta.y())
                    new_y = bottom_edge - new_h
                if 'bottom' in self._resize_edge:
                    new_h = max(min_h, geo.height() + delta.y())

                self.setGeometry(new_x, new_y, new_w, new_h)
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
        cursor = FramelessWindowBase._cursor_for_edge(edge)
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
            geo = self._start_geometry
            new_x, new_y = geo.x(), geo.y()
            new_w, new_h = geo.width(), geo.height()
            min_w = self.parent_window.minimumWidth()
            min_h = self.parent_window.minimumHeight()
            right_edge = geo.x() + geo.width()
            bottom_edge = geo.y() + geo.height()

            if 'left' in self.edge:
                new_w = max(min_w, geo.width() - delta.x())
                new_x = right_edge - new_w
            if 'right' in self.edge:
                new_w = max(min_w, geo.width() + delta.x())
            if 'top' in self.edge:
                new_h = max(min_h, geo.height() - delta.y())
                new_y = bottom_edge - new_h
            if 'bottom' in self.edge:
                new_h = max(min_h, geo.height() + delta.y())

            self.parent_window.setGeometry(new_x, new_y, new_w, new_h)
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

