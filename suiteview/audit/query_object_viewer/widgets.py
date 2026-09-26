"""Tree and table widgets/delegates for QueryObject Viewer."""
from __future__ import annotations

from .common import *  # noqa: F401,F403 - private split module shares viewer globals.

class _OrganizerTree(QTreeWidget):
    """The browser tree with bookmark-style drag-drop (design §8).

    The widget only works out WHAT was dragged WHERE and hands that to the
    window; the actual reorganization happens in QueryOrganizer and the tree
    is rebuilt from it — the organizer stays the single source of truth.
    """

    def __init__(self, window):
        super().__init__()
        self._window = window
        self.setDragEnabled(True)
        self.setAcceptDrops(True)
        self.setDropIndicatorShown(True)
        self.setDragDropMode(QAbstractItemView.DragDropMode.InternalMove)
        self.setDefaultDropAction(Qt.DropAction.MoveAction)

    def dropEvent(self, event):
        dragged = self.currentItem()
        target = self.itemAt(event.position().toPoint())
        indicator = self.dropIndicatorPosition()
        # Never let Qt restructure the tree itself; the organizer decides
        # and the tree is rebuilt from it.
        event.setDropAction(Qt.DropAction.IgnoreAction)
        event.accept()
        self._window._handle_tree_drop(dragged, target, indicator)


class _OrganizerPillDelegate(QStyledItemDelegate):
    """Paint Query Object organizer rows as bookmark-style pills."""

    def paint(self, painter: QPainter, option, index) -> None:
        payload = index.data(Qt.ItemDataRole.UserRole) or {}
        if not isinstance(payload, dict):
            super().paint(painter, option, index)
            return

        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        rect = option.rect.adjusted(3, 2, -3, -2)
        selected = bool(option.state & QStyle.StateFlag.State_Selected)

        if payload.get("type") == "query":
            self._paint_query(painter, rect, index.data(Qt.ItemDataRole.DisplayRole) or "", payload, selected)
        elif payload.get("type") == "forge":
            self._paint_container(
                painter,
                rect,
                index.data(Qt.ItemDataRole.DisplayRole) or "",
                "#B91C1C",
                "#F97316",
                "#7F1D1D",
                selected,
                radius=0,
                text_color="#FFF7ED",
            )
        elif payload.get("type") == "group":
            if payload.get("group_id") == COMMONS_GROUP_ID:
                top_color, bottom_color, border_color, text_color = (
                    "#9CA3AF", "#4B5563", "#374151", "#F8FAFC")
            else:
                top_color, bottom_color, border_color, text_color = _pill_colors_for_group(
                    payload.get("color") or GROUP_STYLE.tint)
            radius = 0 if payload.get("group_id") == COMMONS_GROUP_ID else 10
            self._paint_container(
                painter,
                rect,
                index.data(Qt.ItemDataRole.DisplayRole) or "",
                top_color,
                bottom_color,
                border_color,
                selected,
                radius=radius,
                text_color=text_color,
            )
        else:
            super().paint(painter, option, index)
        painter.restore()

    def sizeHint(self, option, index) -> QSize:
        payload = index.data(Qt.ItemDataRole.UserRole) or {}
        if isinstance(payload, dict) and payload.get("type") in {"group", "forge"}:
            return QSize(option.rect.width(), 30)
        if isinstance(payload, dict) and payload.get("type") == "query":
            return QSize(option.rect.width(), 25)
        return super().sizeHint(option, index)

    @staticmethod
    def _paint_container(
        painter: QPainter,
        rect,
        text: str,
        top_color: str,
        bottom_color: str,
        border_color: str,
        selected: bool,
        *,
        radius: int,
        text_color: str,
    ) -> None:
        gradient = QLinearGradient(
            float(rect.left()),
            float(rect.top()),
            float(rect.left()),
            float(rect.bottom()),
        )
        gradient.setColorAt(0, QColor(top_color))
        gradient.setColorAt(1, QColor(bottom_color))
        border = QColor("#1E5BA8" if selected else border_color)
        painter.setPen(QPen(border, 2))
        painter.setBrush(QBrush(gradient))
        painter.drawRoundedRect(rect, radius, radius)
        painter.setPen(QColor(text_color))
        font = QFont(_FONT_BOLD)
        painter.setFont(font)
        painter.drawText(rect.adjusted(10, 0, -8, 0), Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft, text)

    @staticmethod
    def _paint_query(painter: QPainter, rect, text: str, payload: dict, selected: bool) -> None:
        border = QColor("#1E5BA8" if selected else "#8AAED8")
        painter.setPen(QPen(border, 1.4))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawRoundedRect(rect.adjusted(10, 1, -2, -1), 7, 7)

        badge = payload.get("badge", "Q")
        badge_color = payload.get("badge_color") or "#64748B"
        badge_fill = payload.get("badge_fill") or badge_color
        badge_text_color = payload.get("badge_text_color") or "#FFFFFF"
        badge_font = QFont(_FONT_SMALL)
        badge_font.setBold(True)
        painter.setFont(badge_font)
        metrics = painter.fontMetrics()
        max_badge_width = 140
        badge_width = max(34, min(max_badge_width, metrics.horizontalAdvance(badge) + 14))
        if metrics.horizontalAdvance(badge) + 14 > max_badge_width:
            badge = metrics.elidedText(badge, Qt.TextElideMode.ElideRight, badge_width - 12)
        badge_rect = rect.adjusted(16, 4, 0, -4)
        badge_rect.setWidth(badge_width)
        painter.setPen(QPen(QColor(badge_color), 1))
        painter.setBrush(QColor(badge_fill))
        painter.drawRoundedRect(badge_rect, 4, 4)
        painter.setPen(QColor(badge_text_color))
        painter.drawText(badge_rect, Qt.AlignmentFlag.AlignCenter, badge)

        painter.setPen(QColor("#202124"))
        text_rect = rect.adjusted(16 + badge_rect.width() + 8, 0, -8, 0)
        _OrganizerPillDelegate._draw_bracketed_text(painter, text_rect, text)

    @staticmethod
    def _draw_bracketed_text(painter: QPainter, rect, text: str) -> None:
        painter.save()
        painter.setClipRect(rect)
        x = rect.left()
        parts = re.split(r"(\[[^\]]+\])", text)
        normal_font = QFont(_FONT)
        bold_font = QFont(_FONT)
        bold_font.setBold(True)
        painter.setFont(normal_font)
        metrics = painter.fontMetrics()
        baseline = int(rect.top() + (rect.height() + metrics.ascent() - metrics.descent()) / 2)
        for part in parts:
            if not part:
                continue
            painter.setFont(bold_font if part.startswith("[") and part.endswith("]") else normal_font)
            metrics = painter.fontMetrics()
            painter.drawText(x, baseline, part)
            x += metrics.horizontalAdvance(part)
            if x > rect.right():
                break
        painter.restore()



class _CompactSourceDelegate(QStyledItemDelegate):
    """Tight, uniform rows for the Data Sources tree.

    The Queries tree uses pill rows; the Data Sources tree is a plain compact
    catalog (groups → sources → tables/queries), so it reads better as a dense
    list — group headers a touch taller, everything else snug.
    """

    def sizeHint(self, option, index) -> QSize:
        size = super().sizeHint(option, index)
        payload = index.data(Qt.ItemDataRole.UserRole) or {}
        is_group = isinstance(payload, dict) and payload.get("type") == "source_group"
        size.setHeight(22 if is_group else 19)
        return size


_HEALTH_PILL_COLORS = {
    "ok": ("#E6F4EA", "#1E7E34", "#A3D9B1"),
    "warn": ("#FFF4D6", "#9A7A00", "#E6D08A"),
    "bad": ("#FCE8E8", "#B71C1C", "#E6A6A6"),
    "neutral": ("#EEF2F7", "#475569", "#C9D5E3"),
}


class _FileDropTable(QTableWidget):
    """The Tables list, made an OS-file drop target for editable File Sources.

    Dropped local file paths are emitted via ``files_dropped`` (the window
    validates + adds them). Drops are only accepted while ``setAcceptDrops(True)``
    is set, which the dashboard toggles per source kind.
    """

    files_dropped = pyqtSignal(list)

    def dragEnterEvent(self, event):  # noqa: N802 (Qt signature)
        if self.acceptDrops() and event.mimeData().hasUrls():
            event.acceptProposedAction()
        else:
            super().dragEnterEvent(event)

    def dragMoveEvent(self, event):  # noqa: N802
        if self.acceptDrops() and event.mimeData().hasUrls():
            event.acceptProposedAction()
        else:
            super().dragMoveEvent(event)

    def dropEvent(self, event):  # noqa: N802
        if self.acceptDrops() and event.mimeData().hasUrls():
            paths = [u.toLocalFile() for u in event.mimeData().urls() if u.isLocalFile()]
            if paths:
                event.acceptProposedAction()
                self.files_dropped.emit(paths)
                return
        super().dropEvent(event)


