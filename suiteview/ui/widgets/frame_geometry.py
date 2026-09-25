"""Shared frameless-window edge, cursor and snap geometry helpers."""

from __future__ import annotations

from typing import Iterable, Optional

from PyQt6.QtCore import QPoint, QRect, QSize, Qt
from PyQt6.QtWidgets import QWidget


ResizeEdgeName = str

EDGE_LEFT = "left"
EDGE_RIGHT = "right"
EDGE_TOP = "top"
EDGE_BOTTOM = "bottom"
EDGE_TOP_LEFT = "top-left"
EDGE_TOP_RIGHT = "top-right"
EDGE_BOTTOM_LEFT = "bottom-left"
EDGE_BOTTOM_RIGHT = "bottom-right"

ALL_RESIZE_EDGES = (
    EDGE_TOP,
    EDGE_BOTTOM,
    EDGE_LEFT,
    EDGE_RIGHT,
    EDGE_TOP_LEFT,
    EDGE_TOP_RIGHT,
    EDGE_BOTTOM_LEFT,
    EDGE_BOTTOM_RIGHT,
)

HORIZONTAL_RESIZE_EDGES = (EDGE_LEFT, EDGE_RIGHT)

_EDGE_ALIASES = {
    "tl": EDGE_TOP_LEFT,
    "tr": EDGE_TOP_RIGHT,
    "bl": EDGE_BOTTOM_LEFT,
    "br": EDGE_BOTTOM_RIGHT,
}


def normalize_resize_edge(edge: Optional[str]) -> Optional[ResizeEdgeName]:
    """Return SuiteView's canonical resize edge name."""
    if edge is None:
        return None
    return _EDGE_ALIASES.get(edge, edge)


def resize_edge_at(
    pos: QPoint,
    rect_or_size: QRect | QSize,
    margin: int,
    *,
    edges: Iterable[str] = ALL_RESIZE_EDGES,
) -> Optional[ResizeEdgeName]:
    """Return the resize edge/corner under ``pos`` within ``margin`` pixels."""
    if isinstance(rect_or_size, QRect):
        width = rect_or_size.width()
        height = rect_or_size.height()
    else:
        width = rect_or_size.width()
        height = rect_or_size.height()

    allowed = {normalize_resize_edge(edge) for edge in edges}
    left = pos.x() <= margin
    right = pos.x() >= width - margin
    top = pos.y() <= margin
    bottom = pos.y() >= height - margin

    candidates = (
        (top and left, EDGE_TOP_LEFT),
        (top and right, EDGE_TOP_RIGHT),
        (bottom and left, EDGE_BOTTOM_LEFT),
        (bottom and right, EDGE_BOTTOM_RIGHT),
        (left, EDGE_LEFT),
        (right, EDGE_RIGHT),
        (top, EDGE_TOP),
        (bottom, EDGE_BOTTOM),
    )
    for active, edge in candidates:
        if active and edge in allowed:
            return edge
    return None


def cursor_for_resize_edge(edge: Optional[str]) -> Optional[Qt.CursorShape]:
    """Return the cursor shape for a resize edge, or None for no edge."""
    edge = normalize_resize_edge(edge)
    cursors = {
        EDGE_LEFT: Qt.CursorShape.SizeHorCursor,
        EDGE_RIGHT: Qt.CursorShape.SizeHorCursor,
        EDGE_TOP: Qt.CursorShape.SizeVerCursor,
        EDGE_BOTTOM: Qt.CursorShape.SizeVerCursor,
        EDGE_TOP_LEFT: Qt.CursorShape.SizeFDiagCursor,
        EDGE_BOTTOM_RIGHT: Qt.CursorShape.SizeFDiagCursor,
        EDGE_TOP_RIGHT: Qt.CursorShape.SizeBDiagCursor,
        EDGE_BOTTOM_LEFT: Qt.CursorShape.SizeBDiagCursor,
    }
    return cursors.get(edge)


def update_cursor_for_resize_edge(
    widget: QWidget,
    edge: Optional[str],
    *,
    unset_when_none: bool = True,
) -> None:
    """Apply the resize cursor for ``edge`` to ``widget``."""
    cursor = cursor_for_resize_edge(edge)
    if cursor is not None:
        widget.setCursor(cursor)
    elif unset_when_none:
        widget.unsetCursor()
    else:
        widget.setCursor(Qt.CursorShape.ArrowCursor)


def resize_geometry_for_edge(
    start_geometry: QRect,
    delta: QPoint,
    edge: str,
    minimum_size: QSize,
) -> QRect:
    """Return geometry resized from ``start_geometry`` by dragging ``edge``."""
    edge = normalize_resize_edge(edge)
    geo = QRect(start_geometry)
    min_w = minimum_size.width()
    min_h = minimum_size.height()

    if EDGE_LEFT in edge:
        new_left = geo.left() + delta.x()
        if geo.right() - new_left + 1 >= min_w:
            geo.setLeft(new_left)
    if EDGE_RIGHT in edge:
        geo.setWidth(max(min_w, geo.width() + delta.x()))
    if EDGE_TOP in edge:
        new_top = geo.top() + delta.y()
        if geo.bottom() - new_top + 1 >= min_h:
            geo.setTop(new_top)
    if EDGE_BOTTOM in edge:
        geo.setHeight(max(min_h, geo.height() + delta.y()))

    return geo


def detect_snap_edge(
    global_pos: QPoint,
    available_geometry: QRect,
    threshold: int,
) -> Optional[str]:
    """Return ``left`` or ``right`` when ``global_pos`` is near that edge."""
    if global_pos.x() <= available_geometry.left() + threshold:
        return EDGE_LEFT
    if global_pos.x() >= available_geometry.right() - threshold:
        return EDGE_RIGHT
    return None


def snap_rect_for_edge(edge: str, available_geometry: QRect) -> QRect:
    """Return the half-screen target rectangle for a left/right snap edge."""
    edge = normalize_resize_edge(edge)
    half_w = available_geometry.width() // 2
    if edge == EDGE_LEFT:
        return QRect(
            available_geometry.x(),
            available_geometry.y(),
            half_w,
            available_geometry.height(),
        )
    if edge == EDGE_RIGHT:
        return QRect(
            available_geometry.x() + half_w,
            available_geometry.y(),
            available_geometry.width() - half_w,
            available_geometry.height(),
        )
    raise ValueError(f"Unsupported snap edge: {edge!r}")
