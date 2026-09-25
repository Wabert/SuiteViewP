from PyQt6.QtCore import QPoint, QRect, QSize, Qt

from suiteview.ui.widgets.frame_geometry import (
    HORIZONTAL_RESIZE_EDGES,
    cursor_for_resize_edge,
    detect_snap_edge,
    resize_edge_at,
    resize_geometry_for_edge,
    snap_rect_for_edge,
)


def test_resize_edge_at_corners_edges_and_inside():
    rect = QRect(0, 0, 100, 80)
    assert resize_edge_at(QPoint(0, 0), rect, 6) == "top-left"
    assert resize_edge_at(QPoint(99, 0), rect, 6) == "top-right"
    assert resize_edge_at(QPoint(0, 79), rect, 6) == "bottom-left"
    assert resize_edge_at(QPoint(99, 79), rect, 6) == "bottom-right"
    assert resize_edge_at(QPoint(1, 40), rect, 6) == "left"
    assert resize_edge_at(QPoint(99, 40), rect, 6) == "right"
    assert resize_edge_at(QPoint(50, 1), rect, 6) == "top"
    assert resize_edge_at(QPoint(50, 79), rect, 6) == "bottom"
    assert resize_edge_at(QPoint(50, 40), rect, 6) is None


def test_resize_edge_at_can_limit_to_horizontal_edges():
    rect = QRect(0, 0, 100, 80)
    assert (
        resize_edge_at(
            QPoint(1, 1),
            rect,
            6,
            edges=HORIZONTAL_RESIZE_EDGES,
        )
        == "left"
    )
    assert resize_edge_at(QPoint(50, 1), rect, 6, edges=HORIZONTAL_RESIZE_EDGES) is None


def test_cursor_mapping_uses_one_canonical_table():
    assert cursor_for_resize_edge("left") == Qt.CursorShape.SizeHorCursor
    assert cursor_for_resize_edge("right") == Qt.CursorShape.SizeHorCursor
    assert cursor_for_resize_edge("top") == Qt.CursorShape.SizeVerCursor
    assert cursor_for_resize_edge("bottom") == Qt.CursorShape.SizeVerCursor
    assert cursor_for_resize_edge("top-left") == Qt.CursorShape.SizeFDiagCursor
    assert cursor_for_resize_edge("bottom-right") == Qt.CursorShape.SizeFDiagCursor
    assert cursor_for_resize_edge("top-right") == Qt.CursorShape.SizeBDiagCursor
    assert cursor_for_resize_edge("bottom-left") == Qt.CursorShape.SizeBDiagCursor
    assert cursor_for_resize_edge("tl") == Qt.CursorShape.SizeFDiagCursor
    assert cursor_for_resize_edge(None) is None


def test_resize_geometry_keeps_opposite_edge_and_minimum_size():
    start = QRect(100, 100, 300, 200)
    resized = resize_geometry_for_edge(
        start,
        QPoint(50, 25),
        "top-left",
        QSize(200, 120),
    )
    assert resized == QRect(150, 125, 250, 175)

    clamped = resize_geometry_for_edge(
        start,
        QPoint(250, 100),
        "left",
        QSize(200, 120),
    )
    assert clamped == start


def test_snap_edge_detection_and_target_rects():
    avail = QRect(10, 20, 1000, 700)
    assert detect_snap_edge(QPoint(15, 200), avail, 10) == "left"
    assert detect_snap_edge(QPoint(1005, 200), avail, 10) == "right"
    assert detect_snap_edge(QPoint(500, 200), avail, 10) is None
    assert snap_rect_for_edge("left", avail) == QRect(10, 20, 500, 700)
    assert snap_rect_for_edge("right", avail) == QRect(510, 20, 500, 700)
