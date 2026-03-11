"""
DockableToolPanel -- Abstract base for frameless tool windows that dock
to the right edge of a parent window.

Behaviour
---------
- Docked by default: positioned flush-right of the parent, matching its height.
- Drag header to undock: auto-detaches when the user drags the header bar.
- Double-click header to re-dock: snaps back to the docked position.
- 8-edge resize: corners + edges, respecting minimum dimensions.
- Rounded-rect border painting.
- follow_parent() / show_docked() API for parent integration.

Subclasses override build_header() and build_body() to supply
their own content.  The base class composes them into the window layout
and handles all chrome behavior.
"""

from typing import Optional

from PyQt6.QtCore import Qt, QPoint, QRect
from PyQt6.QtGui import (
    QColor, QPainter, QPen, QBrush, QPainterPath, QMouseEvent,
)
from PyQt6.QtWidgets import QWidget, QVBoxLayout, QFrame

_RESIZE_MARGIN = 6
_MIN_HEIGHT_DEFAULT = 200


class DockableToolPanel(QWidget):
    """Abstract dockable tool-window base.

    Parameters
    ----------
    parent_window : QWidget
        The window this panel docks to (positioned at its right edge).
    default_width : int
        Initial width of the panel.
    min_width : int
        Minimum width when resizing.
    min_height : int
        Minimum height when resizing.
    border_color : str
        Hex color for the rounded-rect border (default gold #D4A017).
    bg_color : str
        Hex color for the background fill (default #E8EAF0).
    corner_radius : float
        Radius for the rounded corners (default 12.0).
    """

    def __init__(
        self,
        parent_window: QWidget,
        *,
        default_width: int = 250,
        min_width: int = 100,
        min_height: int = _MIN_HEIGHT_DEFAULT,
        border_color: str = "#D4A017",
        bg_color: str = "#E8EAF0",
        corner_radius: float = 12.0,
        parent: Optional[QWidget] = None,
    ):
        super().__init__(parent)
        self._parent_window = parent_window
        self._border_color = border_color
        self._bg_color = bg_color
        self._corner_radius = corner_radius

        # Dock state
        self._docked = True

        # Resize state (8-edge)
        self._resizing = False
        self._resize_edge: Optional[str] = None
        self._resize_start_pos: Optional[QPoint] = None
        self._resize_start_geo: Optional[QRect] = None

        # Header drag state
        self._dragging = False
        self._drag_offset = QPoint()

        # Window flags -- frameless tool window, no taskbar entry
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint | Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose, False)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setMouseTracking(True)
        self.setMinimumWidth(min_width)
        self.setMinimumHeight(min_height)
        self.resize(default_width, 520)

        self._compose_layout()
        self.hide()

    # -- Layout composition ------------------------------------------------

    def _compose_layout(self):
        """Build outer layout from subclass-provided header + body."""
        outer = QVBoxLayout(self)
        m = _RESIZE_MARGIN
        outer.setContentsMargins(m, m, m, m)
        outer.setSpacing(0)

        self._frame = QFrame()
        self._frame.setStyleSheet(f"""
            QFrame {{
                background: {self._bg_color};
                border: none;
                border-radius: {self._corner_radius}px;
            }}
        """)
        frame_lay = QVBoxLayout(self._frame)
        frame_lay.setContentsMargins(0, 0, 0, 0)
        frame_lay.setSpacing(0)

        # Subclass-provided header
        self._header_widget = self.build_header()
        if self._header_widget is not None:
            frame_lay.addWidget(self._header_widget)

        # Subclass-provided body
        body = self.build_body()
        if body is not None:
            frame_lay.addWidget(body, 1)

        outer.addWidget(self._frame)

    # -- Abstract override points ------------------------------------------

    def build_header(self) -> Optional[QWidget]:
        """Return the header widget for the tool panel.

        Subclasses **must** override this.  The header is used for
        drag-to-undock and double-click-to-redock hit-testing.
        """
        return None

    def build_body(self) -> Optional[QWidget]:
        """Return the main body widget for the tool panel.

        Subclasses **must** override this.
        """
        return None

    # -- Dock / undock API -------------------------------------------------

    @property
    def is_docked(self) -> bool:
        return self._docked

    def detach(self):
        """Switch to free-floating mode."""
        if self._docked:
            self._docked = False
            self.on_dock_state_changed(False)

    def dock(self):
        """Re-dock to the parent window."""
        if not self._docked:
            self._docked = True
            self._dock_to_parent()
            self.on_dock_state_changed(True)

    def on_dock_state_changed(self, docked: bool):
        """Hook for subclasses to react to dock state changes."""
        pass

    def _dock_to_parent(self):
        """Position flush to the right edge of the parent window."""
        pw = self._parent_window
        geo = pw.geometry()
        x = geo.x() + geo.width()
        y = geo.y()
        h = geo.height()
        self.move(x, y)
        self.resize(self.width(), h)

    def follow_parent(self):
        """Called by parent on move/resize -- only follows if docked + visible."""
        if self._docked and self.isVisible():
            self._dock_to_parent()

    # Backward-compatible alias used by TaskTracker
    def reposition(self):
        """Alias for follow_parent()."""
        self.follow_parent()

    def show_docked(self):
        """Show the panel in docked position."""
        self._docked = True
        self._dock_to_parent()
        self.show()
        self.raise_()

    # -- Close hook --------------------------------------------------------

    def on_closed(self):
        """Called when the user closes the panel.

        Default: just hides.  Subclasses can override to signal the
        parent or update toggle-button state.
        """
        self.hide()

    # -- 8-edge resize + header drag ---------------------------------------

    _EDGE_CURSORS = {
        "left":   Qt.CursorShape.SizeHorCursor,
        "right":  Qt.CursorShape.SizeHorCursor,
        "top":    Qt.CursorShape.SizeVerCursor,
        "bottom": Qt.CursorShape.SizeVerCursor,
        "tl":     Qt.CursorShape.SizeFDiagCursor,
        "br":     Qt.CursorShape.SizeFDiagCursor,
        "tr":     Qt.CursorShape.SizeBDiagCursor,
        "bl":     Qt.CursorShape.SizeBDiagCursor,
    }

    def _edge_at(self, pos) -> Optional[str]:
        """Return the resize edge/corner name at pos, or None."""
        em = _RESIZE_MARGIN
        x, y, w, h = pos.x(), pos.y(), self.width(), self.height()
        on_left   = x <= em
        on_right  = x >= w - em
        on_top    = y <= em
        on_bottom = y >= h - em
        if on_top and on_left:     return "tl"
        if on_top and on_right:    return "tr"
        if on_bottom and on_left:  return "bl"
        if on_bottom and on_right: return "br"
        if on_left:   return "left"
        if on_right:  return "right"
        if on_top:    return "top"
        if on_bottom: return "bottom"
        return None

    def _in_header(self, pos) -> bool:
        """Return True if pos is inside the header widget."""
        if self._header_widget is None:
            return False
        return self._header_widget.geometry().contains(pos)

    def mousePressEvent(self, event: QMouseEvent):
        if event.button() != Qt.MouseButton.LeftButton:
            super().mousePressEvent(event)
            return
        edge = self._edge_at(event.pos())
        if edge:
            self._resizing = True
            self._resize_edge = edge
            self._resize_start_pos = event.globalPosition().toPoint()
            self._resize_start_geo = self.geometry()
        elif self._in_header(event.pos()):
            self._dragging = True
            self._drag_offset = event.globalPosition().toPoint() - self.pos()
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event: QMouseEvent):
        if self._resizing and self._resize_start_pos:
            gpos = event.globalPosition().toPoint()
            delta = gpos - self._resize_start_pos
            geo = QRect(self._resize_start_geo)
            edge = self._resize_edge
            mw = self.minimumWidth()
            mh = self.minimumHeight()

            if "left" in edge:
                new_left = geo.left() + delta.x()
                new_w = geo.right() - new_left + 1
                if new_w >= mw:
                    geo.setLeft(new_left)
            if "right" in edge:
                new_w = geo.width() + delta.x()
                geo.setWidth(max(mw, new_w))
            if "top" in edge:
                new_top = geo.top() + delta.y()
                new_h = geo.bottom() - new_top + 1
                if new_h >= mh:
                    geo.setTop(new_top)
            if "bottom" in edge:
                new_h = geo.height() + delta.y()
                geo.setHeight(max(mh, new_h))

            self.setGeometry(geo)
        elif self._dragging:
            new_pos = event.globalPosition().toPoint() - self._drag_offset
            self.move(new_pos)
            # Auto-detach when dragged
            if self._docked:
                self.detach()
        else:
            edge = self._edge_at(event.pos())
            if edge:
                self.setCursor(self._EDGE_CURSORS[edge])
            else:
                self.setCursor(Qt.CursorShape.ArrowCursor)
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event: QMouseEvent):
        if event.button() == Qt.MouseButton.LeftButton:
            self._resizing = False
            self._resize_edge = None
            self._dragging = False
        super().mouseReleaseEvent(event)

    def mouseDoubleClickEvent(self, event: QMouseEvent):
        """Double-click header to re-dock."""
        if (
            event.button() == Qt.MouseButton.LeftButton
            and self._in_header(event.pos())
        ):
            self.dock()
        else:
            super().mouseDoubleClickEvent(event)

    # -- Painting -- rounded-rect border -----------------------------------

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        rect = self.rect().adjusted(1, 1, -1, -1)
        path = QPainterPath()
        r = self._corner_radius
        path.addRoundedRect(
            float(rect.x()), float(rect.y()),
            float(rect.width()), float(rect.height()), r, r
        )
        painter.fillPath(path, QBrush(QColor(self._bg_color)))
        painter.setPen(QPen(QColor(self._border_color), 2))
        painter.drawPath(path)
        painter.end()
