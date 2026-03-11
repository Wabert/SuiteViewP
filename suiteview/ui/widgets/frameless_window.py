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

from PyQt6.QtCore import Qt, QPoint
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

        layout = QHBoxLayout(bar)
        layout.setContentsMargins(12, 4, 8, 4)
        layout.setSpacing(8)

        # Title
        title_label = QLabel(title)
        title_label.setStyleSheet(f"""
            QLabel {{
                color: {self._border_color};
                font-size: 18px;
                font-weight: bold;
                font-style: italic;
                background: transparent;
            }}
        """)
        layout.addWidget(title_label)
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
            self.max_btn.setText("\u25A1")
            self.max_btn.setToolTip("Maximize")
        else:
            self.showMaximized()
            self._is_maximized = True
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
                if self._is_maximized:
                    self._is_maximized = False
                    self.showNormal()
                    self.max_btn.setText("\u25A1")
                    new_geo = self.geometry()
                    self._drag_pos = event.globalPosition().toPoint()
                    self.move(
                        self._drag_pos.x() - new_geo.width() // 2,
                        self._drag_pos.y() - 20,
                    )
                else:
                    delta = event.globalPosition().toPoint() - self._drag_pos
                    self.move(self.pos() + delta)
                    self._drag_pos = event.globalPosition().toPoint()
                event.accept()
                return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
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
