"""
MS-Access-style join canvas (Phase 2) — the visual layer over
:class:`JoinCanvasModel`.

Each Source is a movable box listing its fields; drag a field from one box onto
a field in another to draw a **join line**; click a line to set its
inner/left/right/outer type or delete it; multiple lines between two boxes form
a multi-key relationship. This replaces the card metaphor in
``forge_joins_tab.py`` while keeping the same public API
(``update_queries`` / ``get_merge_ops`` / ``get_state`` / ``set_state`` /
``state_changed``) so the designer swap is a one-line import change. It also
adds :meth:`ForgeJoinCanvas.to_join_specs` for the DuckDB engine.

Built so the join logic lives in the (Qt-free) model; this file only renders and
edits it, which keeps the heavy logic unit-testable without a display.
"""
from __future__ import annotations

import logging

from PyQt6.QtCore import QPointF, QRectF, Qt, pyqtSignal
from PyQt6.QtGui import (
    QBrush, QColor, QFont, QPainter, QPainterPath, QPainterPathStroker, QPen,
)
from PyQt6.QtWidgets import (
    QGraphicsObject, QGraphicsPathItem, QGraphicsScene, QGraphicsView,
    QGraphicsItem, QLabel, QMenu, QVBoxLayout, QWidget,
)

from .forge_canvas_model import JOIN_TYPES, JoinCanvasModel, JoinKey

logger = logging.getLogger(__name__)

# Geometry
_HEADER_H = 22
_ROW_H = 18
_BOX_W = 184
_MIN_BOX_W = 140
_MAX_BOX_W = 520
_PAD = 8
_RESIZE_HANDLE = 12
_MIN_VISIBLE_ROWS = 3
_DEFAULT_VISIBLE_ROWS = 12

# Theme (forge heat, matching the rest of DataForge)
_FORGE = QColor("#C2410C")
_FORGE_BG = QColor("#FFF7ED")
_HEADER_BG = QColor("#C2410C")
_HEADER_FG = QColor("#FFFFFF")
_ROW_FG = QColor("#0F172A")
_ROW_HOVER = QColor("#FED7AA")
_LINE_COLOR = QColor("#EA580C")
_LINE_SEL = QColor("#F59E0B")

_FONT = QFont("Segoe UI", 8)
_FONT_BOLD = QFont("Segoe UI", 8, QFont.Weight.Bold)

_HOW_LABEL = {"inner": "=", "left": "⊐=", "right": "=⊏", "outer": "⊐⊏"}


# ── Source box ───────────────────────────────────────────────────────────

class SourceBoxItem(QGraphicsObject):
    """A movable box for one Source, listing its fields."""

    moved = pyqtSignal()

    def __init__(self, alias: str, fields: list[str], collapsed: bool = False,
                 width: float = _BOX_W,
                 visible_rows: int = _DEFAULT_VISIBLE_ROWS,
                 scroll_offset: int = 0):
        super().__init__()
        self.alias = alias
        self.fields = list(fields)
        self.width = max(_MIN_BOX_W, min(_MAX_BOX_W, float(width or _BOX_W)))
        self.collapsed = collapsed
        self.visible_rows = max(_MIN_VISIBLE_ROWS, int(visible_rows))
        self.scroll_offset = max(0, int(scroll_offset))
        self._hover_field: str | None = None
        self._resizing = False
        self._resize_start_pos = QPointF()
        self._resize_start_width = self.width
        self._resize_start_rows = self.visible_rows
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsMovable, True)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemSendsGeometryChanges,
                     True)
        self.setAcceptHoverEvents(True)
        self.setZValue(1)

    # -- geometry --
    def _body_rows(self) -> int:
        if self.collapsed:
            return 0
        return min(len(self.fields), self.visible_rows)

    def _max_scroll_offset(self) -> int:
        return max(0, len(self.fields) - self.visible_rows)

    def _clamp_scroll(self):
        self.scroll_offset = max(0, min(self.scroll_offset, self._max_scroll_offset()))

    def boundingRect(self) -> QRectF:
        h = _HEADER_H + self._body_rows() * _ROW_H
        return QRectF(0, 0, self.width, max(h, _HEADER_H))

    def resize_handle_rect(self) -> QRectF:
        rect = self.boundingRect()
        return QRectF(rect.right() - _RESIZE_HANDLE, rect.bottom() - _RESIZE_HANDLE,
                      _RESIZE_HANDLE, _RESIZE_HANDLE)

    def is_resize_handle(self, pos: QPointF) -> bool:
        return self.resize_handle_rect().contains(pos)

    def field_index_at(self, local_y: float) -> int | None:
        if self.collapsed or local_y < _HEADER_H:
            return None
        idx = int((local_y - _HEADER_H) // _ROW_H)
        if 0 <= idx < self._body_rows():
            field_index = self.scroll_offset + idx
            if 0 <= field_index < len(self.fields):
                return field_index
        return None

    def field_at(self, local_y: float) -> str | None:
        idx = self.field_index_at(local_y)
        return self.fields[idx] if idx is not None else None

    def is_header(self, local_y: float) -> bool:
        return local_y < _HEADER_H

    def _row_mid_y(self, field: str) -> float:
        if self.collapsed or field not in self.fields:
            return _HEADER_H / 2
        idx = self.fields.index(field)
        visible_idx = idx - self.scroll_offset
        if visible_idx < 0:
            visible_idx = 0
        elif visible_idx >= self._body_rows():
            visible_idx = max(0, self._body_rows() - 1)
        return _HEADER_H + visible_idx * _ROW_H + _ROW_H / 2

    def anchor_scene_pos(self, field: str, right_side: bool) -> QPointF:
        x = self.width if right_side else 0.0
        return self.mapToScene(QPointF(x, self._row_mid_y(field)))

    def center_x_scene(self) -> float:
        return self.mapToScene(QPointF(self.width / 2, 0)).x()

    # -- paint --
    def paint(self, painter, option, widget=None):
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        rect = self.boundingRect()
        # Body
        painter.setBrush(QBrush(_FORGE_BG))
        painter.setPen(QPen(_FORGE, 1))
        painter.drawRoundedRect(rect.adjusted(0.5, 0.5, -0.5, -0.5), 4, 4)
        # Header
        header = QRectF(0, 0, self.width, _HEADER_H)
        painter.setBrush(QBrush(_HEADER_BG))
        painter.setPen(Qt.PenStyle.NoPen)
        path = QPainterPath()
        path.addRoundedRect(header, 4, 4)
        painter.drawPath(path)
        painter.fillRect(QRectF(0, _HEADER_H - 6, self.width, 6), _HEADER_BG)
        painter.setPen(QPen(_HEADER_FG))
        painter.setFont(_FONT_BOLD)
        painter.drawText(header.adjusted(_PAD, 0, -_PAD, 0),
                         Qt.AlignmentFlag.AlignVCenter
                         | Qt.AlignmentFlag.AlignLeft, self.alias)
        # Fields
        if not self.collapsed:
            painter.setFont(_FONT)
            self._clamp_scroll()
            visible_fields = self.fields[self.scroll_offset:self.scroll_offset + self._body_rows()]
            for i, name in enumerate(visible_fields):
                row = QRectF(1, _HEADER_H + i * _ROW_H, self.width - 2, _ROW_H)
                if name == self._hover_field:
                    painter.fillRect(row, _ROW_HOVER)
                painter.setPen(QPen(_ROW_FG))
                painter.drawText(row.adjusted(_PAD, 0, -_PAD, 0),
                                 Qt.AlignmentFlag.AlignVCenter
                                 | Qt.AlignmentFlag.AlignLeft, name)
            if len(self.fields) > self.visible_rows:
                track = QRectF(self.width - 8, _HEADER_H + 2, 4,
                               self._body_rows() * _ROW_H - 4)
                painter.setPen(Qt.PenStyle.NoPen)
                painter.setBrush(QBrush(QColor("#FDBA74")))
                painter.drawRoundedRect(track, 2, 2)
                ratio = self.visible_rows / max(1, len(self.fields))
                handle_h = max(18, track.height() * ratio)
                travel = max(1, track.height() - handle_h)
                handle_y = track.y() + travel * (self.scroll_offset / max(1, self._max_scroll_offset()))
                painter.setBrush(QBrush(_FORGE))
                painter.drawRoundedRect(QRectF(track.x(), handle_y, track.width(), handle_h), 2, 2)
            handle = self.resize_handle_rect()
            painter.setPen(QPen(_FORGE, 1))
            painter.drawLine(handle.bottomLeft() + QPointF(3, -2),
                     handle.topRight() + QPointF(-2, 3))
            painter.drawLine(handle.bottomLeft() + QPointF(7, -2),
                     handle.topRight() + QPointF(-2, 7))

    # -- events --
    def itemChange(self, change, value):
        if change == QGraphicsItem.GraphicsItemChange.ItemPositionHasChanged:
            self.moved.emit()
        return super().itemChange(change, value)

    def hoverMoveEvent(self, event):
        if self.is_resize_handle(event.pos()):
            self.setCursor(Qt.CursorShape.SizeFDiagCursor)
        else:
            self.unsetCursor()
        self._hover_field = self.field_at(event.pos().y())
        self.update()
        super().hoverMoveEvent(event)

    def hoverLeaveEvent(self, event):
        self._hover_field = None
        self.unsetCursor()
        self.update()
        super().hoverLeaveEvent(event)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton and self.is_resize_handle(event.pos()):
            self._resizing = True
            self._resize_start_pos = event.pos()
            self._resize_start_width = self.width
            self._resize_start_rows = self.visible_rows
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self._resizing:
            delta = event.pos() - self._resize_start_pos
            new_width = max(_MIN_BOX_W, min(_MAX_BOX_W, self._resize_start_width + delta.x()))
            max_rows = max(_MIN_VISIBLE_ROWS, len(self.fields) or _MIN_VISIBLE_ROWS)
            row_delta = int(round(delta.y() / _ROW_H))
            new_rows = max(_MIN_VISIBLE_ROWS, min(max_rows, self._resize_start_rows + row_delta))
            if new_width != self.width or new_rows != self.visible_rows:
                self.prepareGeometryChange()
                self.width = new_width
                self.visible_rows = new_rows
                self._clamp_scroll()
                self.update()
                self.moved.emit()
            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if self._resizing:
            self._resizing = False
            self.moved.emit()
            event.accept()
            return
        super().mouseReleaseEvent(event)

    def toggle_collapsed(self):
        self.prepareGeometryChange()
        self.collapsed = not self.collapsed
        self.update()
        self.moved.emit()

    def resize_rows(self, delta: int):
        self.prepareGeometryChange()
        self.visible_rows = max(_MIN_VISIBLE_ROWS, min(len(self.fields) or _MIN_VISIBLE_ROWS,
                                                       self.visible_rows + delta))
        self._clamp_scroll()
        self.update()
        self.moved.emit()

    def wheelEvent(self, event):
        if self.collapsed or len(self.fields) <= self.visible_rows:
            super().wheelEvent(event)
            return
        delta = -1 if event.delta() > 0 else 1
        old_offset = self.scroll_offset
        self.scroll_offset = max(0, min(self.scroll_offset + delta, self._max_scroll_offset()))
        if self.scroll_offset != old_offset:
            self._hover_field = None
            self.update()
            self.moved.emit()
            event.accept()
            return
        super().wheelEvent(event)


# ── Join line ─────────────────────────────────────────────────────────────

class JoinLineItem(QGraphicsPathItem):
    """One field-to-field join line (one key) between two Source boxes."""

    def __init__(self, left_box: SourceBoxItem, left_field: str,
                 right_box: SourceBoxItem, right_field: str, how: str):
        super().__init__()
        self.left_box = left_box
        self.left_field = left_field
        self.right_box = right_box
        self.right_field = right_field
        self.how = how
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, True)
        self.setZValue(0)
        self.setPen(QPen(_LINE_COLOR, 2))
        self.update_path()

    def update_path(self):
        # Anchor on the sides facing each other.
        left_right = self.left_box.center_x_scene() <= \
            self.right_box.center_x_scene()
        p1 = self.left_box.anchor_scene_pos(self.left_field, right_side=left_right)
        p2 = self.right_box.anchor_scene_pos(self.right_field,
                                             right_side=not left_right)
        path = QPainterPath(p1)
        dx = abs(p2.x() - p1.x()) * 0.5
        c1 = QPointF(p1.x() + (dx if left_right else -dx), p1.y())
        c2 = QPointF(p2.x() + (-dx if left_right else dx), p2.y())
        path.cubicTo(c1, c2, p2)
        self.setPath(path)

    def paint(self, painter, option, widget=None):
        sel = self.isSelected()
        pen = QPen(_LINE_SEL if sel else _LINE_COLOR, 3 if sel else 2)
        self.setPen(pen)
        super().paint(painter, option, widget)
        # Join-type glyph at the midpoint.
        mid = self.path().pointAtPercent(0.5)
        painter.setFont(_FONT_BOLD)
        painter.setPen(QPen(_LINE_SEL if sel else _LINE_COLOR))
        painter.drawText(QPointF(mid.x() - 6, mid.y() - 4),
                         _HOW_LABEL.get(self.how, "="))

    def shape(self):
        # Fatten the clickable area around the thin curve.
        stroker_path = QPainterPath(self.path())
        pen = QPen(Qt.PenStyle.SolidLine)
        pen.setWidth(10)
        return QPainterPathStroker(pen).createStroke(stroker_path)


# ── Scene ───────────────────────────────────────────────────────────────

class JoinCanvasScene(QGraphicsScene):
    """Holds the box/line items and keeps them in sync with the model."""

    changed_model = pyqtSignal()

    def __init__(self, model: JoinCanvasModel, parent=None):
        super().__init__(parent)
        self.model = model
        self.box_items: dict[str, SourceBoxItem] = {}
        self.line_items: list[JoinLineItem] = []
        self._link_from: tuple[SourceBoxItem, str] | None = None
        self._temp_line: QGraphicsPathItem | None = None

    # -- (re)build from model --
    def rebuild(self):
        self.clear()
        self.box_items.clear()
        self.line_items.clear()
        for src in self.model.sources:
            self._add_box_item(src.alias, src.field_names(), src.collapsed,
                               src.x, src.y, src.width, src.visible_rows,
                               src.scroll_offset)
        for join in self.model.joins:
            lbox = self.box_items.get(join.left_source)
            rbox = self.box_items.get(join.right_source)
            if not lbox or not rbox:
                continue
            for key in join.keys:
                self._add_line_item(lbox, key.left_field,
                                    rbox, key.right_field, join.how)

    def _add_box_item(self, alias, fields, collapsed, x, y, width=_BOX_W,
                      visible_rows=_DEFAULT_VISIBLE_ROWS,
                      scroll_offset=0) -> SourceBoxItem:
        box = SourceBoxItem(alias, fields, collapsed, width, visible_rows, scroll_offset)
        box.setPos(x, y)
        box.moved.connect(self._on_box_moved)
        self.addItem(box)
        self.box_items[alias] = box
        return box

    def _add_line_item(self, lbox, lfield, rbox, rfield, how) -> JoinLineItem:
        line = JoinLineItem(lbox, lfield, rbox, rfield, how)
        self.addItem(line)
        self.line_items.append(line)
        return line

    def _on_box_moved(self):
        # Persist positions back to the model and reroute lines.
        for alias, box in self.box_items.items():
            src = self.model.get_source(alias)
            if src is not None:
                src.x = box.pos().x()
                src.y = box.pos().y()
                src.width = box.width
                src.collapsed = box.collapsed
                src.visible_rows = box.visible_rows
                src.scroll_offset = box.scroll_offset
        for line in self.line_items:
            line.update_path()
        self.changed_model.emit()

    def remove_source(self, alias: str):
        self.model.remove_source(alias)
        self.rebuild()
        self.changed_model.emit()

    # -- programmatic linking (used by the drag gesture and by tests) --
    def add_link(self, src_a: str, field_a: str,
                 src_b: str, field_b: str) -> bool:
        """Create a key between two Sources in both model and scene."""
        try:
            join = self.model.add_link(src_a, field_a, src_b, field_b)
        except ValueError as exc:
            logger.debug("add_link rejected: %s", exc)
            return False
        lbox = self.box_items[join.left_source]
        rbox = self.box_items[join.right_source]
        # Orient the new key the same way the model stored it.
        if join.left_source == src_a:
            lf, rf = field_a, field_b
        else:
            lf, rf = field_b, field_a
        # Avoid a duplicate line if the key already had one.
        for ln in self.line_items:
            if (ln.left_box is lbox and ln.left_field == lf
                    and ln.right_box is rbox and ln.right_field == rf):
                return False
        self._add_line_item(lbox, lf, rbox, rf, join.how)
        self.changed_model.emit()
        return True

    def remove_line(self, line: JoinLineItem):
        self.model.remove_key(
            line.left_box.alias, line.right_box.alias,
            JoinKey(line.left_field, line.right_field))
        if line in self.line_items:
            self.line_items.remove(line)
        self.removeItem(line)
        self.changed_model.emit()

    def set_line_how(self, line: JoinLineItem, how: str):
        self.model.set_how(line.left_box.alias, line.right_box.alias, how)
        # Join type is per relationship → update every line of that pair.
        for ln in self.line_items:
            if {ln.left_box.alias, ln.right_box.alias} == \
                    {line.left_box.alias, line.right_box.alias}:
                ln.how = how
                ln.update()
        self.changed_model.emit()

    # -- mouse: header moves a box; a field starts a link --
    def mousePressEvent(self, event):
        item = self.itemAt(event.scenePos(), self.views()[0].transform()
                           if self.views() else None)  # type: ignore[arg-type]
        if isinstance(item, SourceBoxItem):
            local = item.mapFromScene(event.scenePos())
            if item.is_resize_handle(local):
                super().mousePressEvent(event)
                return
            if not item.is_header(local.y()):
                field = item.field_at(local.y())
                if field is not None and event.button() == \
                        Qt.MouseButton.LeftButton:
                    self._begin_link(item, field, event.scenePos())
                    return  # don't start moving the box
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self._link_from is not None and self._temp_line is not None:
            box, field = self._link_from
            start = box.anchor_scene_pos(field, right_side=True)
            path = QPainterPath(start)
            path.lineTo(event.scenePos())
            self._temp_line.setPath(path)
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if self._link_from is not None:
            self._finish_link(event.scenePos())
            return
        super().mouseReleaseEvent(event)

    def _begin_link(self, box: SourceBoxItem, field: str, scene_pos):
        self._link_from = (box, field)
        self._temp_line = QGraphicsPathItem()
        self._temp_line.setPen(QPen(_LINE_SEL, 2, Qt.PenStyle.DashLine))
        self._temp_line.setZValue(2)
        self.addItem(self._temp_line)

    def _finish_link(self, scene_pos):
        if self._temp_line is not None:
            self.removeItem(self._temp_line)
            self._temp_line = None
        src = self._link_from
        self._link_from = None
        if src is None:
            return
        target = self.itemAt(scene_pos, self.views()[0].transform()
                             if self.views() else None)  # type: ignore[arg-type]
        if not isinstance(target, SourceBoxItem) or target is src[0]:
            return
        tfield = target.field_at(target.mapFromScene(scene_pos).y())
        if tfield is None:
            return
        self.add_link(src[0].alias, src[1], target.alias, tfield)


# ── Public widget ──────────────────────────────────────────────────────────

class ForgeJoinCanvas(QWidget):
    """Drop-in replacement for ForgeJoinsTab using an MS-Access-style canvas."""

    state_changed = pyqtSignal()

    def __init__(self, parent=None, *, source_label: str = "Source",
                 add_menu_label: str = "Add Query Table"):
        super().__init__(parent)
        self._source_label = source_label
        self._add_menu_label = add_menu_label
        self.model = JoinCanvasModel()
        self._available_query_names: list[str] = []
        self._available_query_columns: dict[str, list[str]] = {}
        # Sources the user explicitly removed from the canvas ("Delete Table").
        # Available queries are not shown until the user adds them from the join
        # canvas menu or by double-clicking the query list.
        self._removed_aliases: set[str] = set()
        self.scene = JoinCanvasScene(self.model, self)
        self.scene.changed_model.connect(self.state_changed.emit)

        self.view = QGraphicsView(self.scene)
        self.view.setRenderHint(QPainter.RenderHint.Antialiasing)
        self.view.setDragMode(QGraphicsView.DragMode.RubberBandDrag)

        hint = QLabel(
            f"Drag a field from one {self._source_label} onto a field in another to join. "
            "Click a line to set its type or delete it.")
        hint.setFont(QFont("Segoe UI", 8))
        hint.setStyleSheet("color: #64748B; padding: 2px;")
        hint.setWordWrap(True)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)
        lay.addWidget(hint)
        lay.addWidget(self.view, 1)

        self.view.setContextMenuPolicy(
            Qt.ContextMenuPolicy.DefaultContextMenu)
        self.view.contextMenuEvent = self._view_context_menu  # type: ignore
        self.view.keyPressEvent = self._view_key_press  # type: ignore

    # ── Public API (compatible with ForgeJoinsTab) ──────────────────────

    def update_queries(self, query_names: list[str],
                       query_columns: dict[str, list[str]] | None = None):
        """Refresh the set of available Source queries.

        Adding a query to the Forge only makes it available to the join canvas;
        it should not create a Source box until the user explicitly adds one.
        Sources no longer available are dropped, and their stale removal flag is
        forgotten.
        """
        self._available_query_names = list(query_names)
        self._available_query_columns = query_columns or {}
        # Forget removals for Sources that no longer exist.
        self._removed_aliases &= set(self._available_query_names)
        visible = [src.alias for src in self.model.sources
               if src.alias in self._available_query_names
               and src.alias not in self._removed_aliases]
        self.model.set_sources(visible, self._available_query_columns,
                       add_missing=False)
        self.scene.rebuild()
        self.state_changed.emit()

    def get_merge_ops(self) -> list[dict]:
        return self.model.get_merge_ops()

    def to_join_specs(self):
        return self.model.to_join_specs()

    def to_config_joins(self) -> list[dict]:
        return self.model.to_config_joins()

    def card_count(self) -> int:
        return len(self.model.joins)

    def get_state(self) -> dict:
        self._sync_positions()
        state = self.model.to_state()
        if self._removed_aliases:
            state["removed"] = sorted(self._removed_aliases)
        return state

    def set_state(self, state: dict):
        self._removed_aliases = set(state.get("removed", []))
        if "sources" in state or "joins" in state:
            self.model.from_state(state)
        elif "cards" in state:
            self.model = JoinCanvasModel.from_legacy_cards(state["cards"])
            self.scene.model = self.model
        elif "merges" in state:
            self.model = JoinCanvasModel.from_legacy_merges(state["merges"])
            self.scene.model = self.model
        self.scene.rebuild()
        self.state_changed.emit()

    # ── Internals ────────────────────────────────────────────────────────

    def _sync_positions(self):
        for alias, box in self.scene.box_items.items():
            src = self.model.get_source(alias)
            if src is not None:
                src.x = box.pos().x()
                src.y = box.pos().y()
                src.width = box.width
                src.collapsed = box.collapsed
                src.visible_rows = box.visible_rows
                src.scroll_offset = box.scroll_offset

    def _available_to_add(self) -> list[str]:
        visible = {src.alias for src in self.model.sources}
        return [name for name in self._available_query_names if name not in visible]

    def _add_query_table(self, name: str):
        if name not in self._available_query_names:
            return False
        self._removed_aliases.discard(name)
        visible = [src.alias for src in self.model.sources]
        if name in visible:
            return False
        self.model.set_sources(visible + [name], self._available_query_columns,
                               add_missing=True)
        self.scene.rebuild()
        self.state_changed.emit()
        return True

    def _remove_query_table(self, alias: str):
        """Remove a Source box from the canvas and remember the removal."""
        self._removed_aliases.add(alias)
        self.scene.remove_source(alias)

    def add_query_table(self, name: str) -> bool:
        """Add an available query Source box to the join canvas."""
        return self._add_query_table(name)

    def _selected_line(self) -> JoinLineItem | None:
        for item in self.scene.selectedItems():
            if isinstance(item, JoinLineItem):
                return item
        return None

    def _view_context_menu(self, event):
        scene_pos = self.view.mapToScene(event.pos())
        item = self.scene.itemAt(scene_pos, self.view.transform())
        if isinstance(item, JoinLineItem):
            menu = QMenu(self.view)
            for how in JOIN_TYPES:
                act = menu.addAction(f"{how.title()} join"
                                     + ("  ✓" if item.how == how else ""))
                act.triggered.connect(
                    lambda _=False, h=how, ln=item: self.scene.set_line_how(ln, h))
            menu.addSeparator()
            act_del = menu.addAction("Delete this key")
            act_del.triggered.connect(lambda: self.scene.remove_line(item))
            menu.exec(event.globalPos())
        elif isinstance(item, SourceBoxItem):
            menu = QMenu(self.view)
            act = menu.addAction("Expand" if item.collapsed else "Collapse")
            act.triggered.connect(item.toggle_collapsed)
            if not item.collapsed and item.fields:
                act_more = menu.addAction("Show More Rows")
                act_more.setEnabled(item.visible_rows < len(item.fields))
                act_more.triggered.connect(lambda: item.resize_rows(5))
                act_fewer = menu.addAction("Show Fewer Rows")
                act_fewer.setEnabled(item.visible_rows > _MIN_VISIBLE_ROWS)
                act_fewer.triggered.connect(lambda: item.resize_rows(-5))
            menu.addSeparator()
            act_delete = menu.addAction("Delete Table")
            act_delete.triggered.connect(
                lambda _=False, a=item.alias: self._remove_query_table(a))
            menu.exec(event.globalPos())
        else:
            menu = QMenu(self.view)
            add_menu = menu.addMenu(self._add_menu_label)
            names = self._available_to_add()
            if names:
                for name in names:
                    act = add_menu.addAction(name)
                    act.triggered.connect(lambda _=False, n=name: self._add_query_table(n))
            else:
                act = add_menu.addAction("No available queries")
                act.setEnabled(False)
            menu.exec(event.globalPos())

    def _view_key_press(self, event):
        if event.key() in (Qt.Key.Key_Delete, Qt.Key.Key_Backspace):
            line = self._selected_line()
            if line is not None:
                self.scene.remove_line(line)
                return
        QGraphicsView.keyPressEvent(self.view, event)
