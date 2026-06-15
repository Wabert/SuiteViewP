"""
QueryObject Viewer Window — unified browser for saved query objects.

Shows visual query designs, QDefinitions, Cyberlife-produced objects, manual SQL,
and ad hoc sources from the QueryObject store in one place.
"""
from __future__ import annotations

import json
import logging
import re
from datetime import datetime
from pathlib import Path

import pandas as pd

from PyQt6.QtCore import QSize, Qt, QTimer
from PyQt6.QtGui import (
    QBrush,
    QColor,
    QFont,
    QLinearGradient,
    QPainter,
    QPen,
)
from PyQt6.QtWidgets import (
    QAbstractItemView,
    QFrame,
    QDialog,
    QFileDialog,
    QGridLayout,
    QHeaderView,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QMenu,
    QApplication,
    QSizePolicy,
    QSplitter,
    QStackedWidget,
    QStyle,
    QStyledItemDelegate,
    QTableWidget,
    QTableWidgetItem,
    QTabWidget,
    QTextEdit,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from suiteview.audit.adhoc_source_intake import (
    promote_adhoc_source,
    query_adhoc_object,
    query_object_from_file,
)
from suiteview.audit.query_object import (
    OBJECT_KIND_ADHOC_SOURCE,
    OBJECT_KIND_CYBERLIFE,
    OBJECT_KIND_EXECUTABLE,
    OBJECT_KIND_MANUAL_SQL,
    OBJECT_KIND_VISUAL,
    QueryObject,
    object_from_qdefinition,
    qdefinition_from_query_object,
)
from suiteview.audit.qdefinition import QDefinition
from suiteview.audit.query_runner import execute_odbc_query
from suiteview.audit import query_object_store
from suiteview.audit.build_mode_styles import (
    FORGE_STYLE, GROUP_STYLE, mode_style,
)
from suiteview.audit.query_organizer import (
    COMMONS_GROUP_ID,
    COMMONS_GROUP_NAME,
    get_query_organizer,
)
from suiteview.audit.group_config import load_ui_settings, save_ui_settings
from suiteview.core.odbc_utils import (
    ACCESS,
    DB2,
    SQL_SERVER,
    UNKNOWN,
    detect_dialect,
    get_dsn_details,
)
from suiteview.ui.widgets.filter_table_view import FilterTableView
from suiteview.ui.widgets.frameless_window import FramelessWindowBase
from suiteview.ui.widgets.bookmark_widgets import (
    ColorPickerPopup,
    darken_color,
    lighten_color,
)

logger = logging.getLogger(__name__)

_FONT = QFont("Segoe UI", 9)
_FONT_BOLD = QFont("Segoe UI", 9, QFont.Weight.Bold)
_FONT_MONO = QFont("Consolas", 9)
_FONT_SMALL = QFont("Segoe UI", 8)

_HEADER_COLORS = ("#1E5BA8", "#0D3A7A", "#082B5C")
_BORDER_COLOR = "#D4A017"

_BTN_STYLE = (
    "QPushButton { background-color: #1E5BA8; color: white;"
    " border: 1px solid #14407A; border-radius: 3px;"
    " padding: 3px 10px; font-size: 8pt; }"
    "QPushButton:hover { background-color: #2A6BC4; }"
)

_BTN_DANGER_STYLE = (
    "QPushButton { background-color: #C00000; color: white;"
    " border: 1px solid #900; border-radius: 3px;"
    " padding: 3px 10px; font-size: 8pt; }"
    "QPushButton:hover { background-color: #E00000; }"
)

# ── Tree item payloads (UserRole) ───────────────────────────────────────
# {"type": "query", "id": <object id>, "name": <object name>[, "forge": name]}
# {"type": "group", "group_id": <organizer group id>, "name": <group name>}
# {"type": "forge", "name": <forge name>}

_LEFT_PANEL_DEFAULT_WIDTH = 280
_LEFT_PANEL_MIN_WIDTH = 220
_LEFT_PANEL_MAX_WIDTH = 720
_RIGHT_PANEL_MIN_WIDTH = 220
_FILE_SOURCE_TYPES = {"csv", "excel", "fixed_width"}
_SENSITIVE_ODBC_KEYS = {
    "password",
    "pwd",
    "pass",
    "uid",
    "user",
    "username",
    "userid",
    "user id",
}

_QUERY_BADGES = {
    OBJECT_KIND_VISUAL: "VIS",
    OBJECT_KIND_MANUAL_SQL: "SQL",
    OBJECT_KIND_CYBERLIFE: "CL",
    OBJECT_KIND_ADHOC_SOURCE: "FILE",
    OBJECT_KIND_EXECUTABLE: "RUN",
}

_THEME_PILL_COLORS = {
    "theme:blue_gold": ("#1E5BA8", "#082B5C", "#D4A017", "#D4A017"),
    "theme:gold_blue": ("#D4A017", "#8B6914", "#0D3A7A", "#0D3A7A"),
    "theme:navy_silver": ("#0A1E3E", "#050F1F", "#C0C0C0", "#C0C0C0"),
    "theme:teal_coral": ("#008080", "#004040", "#FF7F50", "#FF7F50"),
    "theme:purple_gold": ("#6B2D8E", "#3D1A52", "#FFD700", "#FFD700"),
    "theme:forest_cream": ("#228B22", "#145214", "#FFFDD0", "#FFFDD0"),
    "theme:crimson_slate": ("#DC143C", "#8B0A25", "#708090", "#B0C0D0"),
    "theme:ocean_sunset": ("#006994", "#003D56", "#FF6B35", "#FF6B35"),
    "theme:silver_blue": ("#C0C0C0", "#808080", "#1E5BA8", "#1E5BA8"),
    "theme:mint_chocolate": ("#98FB98", "#3CB371", "#8B4513", "#5D2E0C"),
    "theme:sunset_purple": ("#FF7F50", "#FF6347", "#6B2D8E", "#6B2D8E"),
    "theme:steel_orange": ("#708090", "#4A5568", "#FF8C00", "#FF8C00"),
}


def _payload(item) -> dict:
    if item is None:
        return {}
    data = item.data(0, Qt.ItemDataRole.UserRole)
    return data if isinstance(data, dict) else {}


def _filename_from_path(path_or_name: str) -> str:
    clean = str(path_or_name or "").strip()
    if not clean:
        return "(unknown file)"
    return clean.rsplit("/", 1)[-1].rsplit("\\", 1)[-1] or clean


def _file_source_key(path: str, source_name: str) -> str:
    clean_path = str(path or "").strip()
    if clean_path:
        return f"path:{clean_path.lower()}"
    return f"name:{str(source_name or '').strip().lower()}"


def _pill_colors_for_group(color: str) -> tuple[str, str, str, str]:
    if color in _THEME_PILL_COLORS:
        return _THEME_PILL_COLORS[color]
    if not color or not str(color).startswith("#"):
        color = GROUP_STYLE.tint
    return (
        lighten_color(color, 0.42),
        color,
        darken_color(color, 0.58),
        "#202124",
    )


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
        badge_rect = rect.adjusted(16, 4, 0, -4)
        badge_rect.setWidth(34 if len(badge) <= 3 else 42)
        painter.setPen(QPen(QColor(badge_color), 1))
        painter.setBrush(QColor(badge_fill))
        painter.drawRoundedRect(badge_rect, 4, 4)
        painter.setPen(QColor(badge_text_color))
        badge_font = QFont(_FONT_SMALL)
        badge_font.setBold(True)
        painter.setFont(badge_font)
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


def _kind_label(kind: str) -> str:
    labels = {
        "visual_query": "Visual Queries",
        "executable_query": "Executable Queries",
        "cyberlife_query": "Cyberlife Objects",
        "manual_sql": "Manual SQL Objects",
        "adhoc_source": "File Sources",
    }
    return labels.get(kind, kind.replace("_", " ").title())


def _object_group_label(obj: QueryObject) -> str:
    """Kind-based group label — no longer used by the browser tree (user
    Query Groups replaced it, design §8) but still consumed by the DataForge
    query picker until the field-picker consolidation pass (#5)."""
    if obj.kind == OBJECT_KIND_ADHOC_SOURCE:
        return "File Sources"
    return _kind_label(obj.kind)


def _object_group_order(label: str) -> tuple[int, str]:
    """Sort order for the kind-based groups (picker-only; see above)."""
    order = {
        "Cyberlife Objects": 10,
        "File Sources": 20,
        "Manual SQL Objects": 30,
        "Visual Queries": 40,
        "Executable Queries": 50,
    }
    return order.get(label, 90), label.lower()


def _dataforge_info(obj: QueryObject) -> tuple[str, str] | None:
    dataforge = (obj.config or {}).get("dataforge", {})
    forge_name = str(dataforge.get("forge_name", "")).strip()
    source_name = str(dataforge.get("source_name", "")).strip()
    if forge_name:
        return forge_name, source_name or obj.name

    match = re.match(r"^(?P<source>.+) \[(?P<forge>[^\]]+)\]$", obj.name)
    if match:
        return match.group("forge"), match.group("source")

    return None


def _dataforge_display_name(forge_name: str) -> str:
    name = forge_name.strip()
    return "(new)" if name.lower() == "dataforge" else name or "(new)"


def _file_source_type_label(source_type: str, metadata: dict | None = None) -> str:
    metadata = metadata or {}
    path = str(metadata.get("path", "")).strip()
    if path:
        filename = path.rsplit("/", 1)[-1].rsplit("\\", 1)[-1]
        if "." in filename:
            suffix = filename.rsplit(".", 1)[-1].strip().lower()
            if suffix:
                return f".{suffix}"
    source_type = source_type.strip().lower()
    fallback = {
        "csv": ".csv",
        "excel": "Excel",
        "fixed_width": "Fixed Width",
    }
    return fallback.get(source_type, "Flat File")


def _display_dsn_for_object(obj: QueryObject) -> str:
    if obj.kind == OBJECT_KIND_ADHOC_SOURCE:
        source = obj.sources[0] if obj.sources else None
        return _file_source_type_label(
            source.source_type if source is not None else obj.source_design,
            source.metadata if source is not None else (obj.config or {}).get("source_metadata", {}),
        )
    return obj.dsn.strip()


def _display_dsn_for_definition(definition: dict) -> str:
    kind = str(definition.get("kind", "")).strip()
    query_object_kind = str(definition.get("query_object_kind", "")).strip()
    source_design = str(definition.get("source_design", "")).strip().lower()
    metadata = (
        definition.get("query_object_source_metadata")
        or definition.get("source_metadata")
        or (definition.get("config", {}) or {}).get("source_metadata")
        or {}
    )
    if kind == OBJECT_KIND_ADHOC_SOURCE or query_object_kind == OBJECT_KIND_ADHOC_SOURCE:
        return _file_source_type_label(source_design, metadata)
    if source_design in {"csv", "excel", "fixed_width"} and metadata:
        return _file_source_type_label(source_design, metadata)
    return str(definition.get("dsn", "")).strip()


def _preview_dialect_for_object(obj: QueryObject) -> str:
    detected = detect_dialect(obj.dsn.strip()) if obj.dsn.strip() else UNKNOWN
    if detected != UNKNOWN:
        return detected
    return obj.dialect.strip().upper() or UNKNOWN


def _limited_preview_sql(sql: str, limit: int, dialect: str) -> str:
    sql = sql.strip().rstrip(";")
    if limit <= 0:
        return sql
    if dialect == DB2:
        if re.search(r"\bFETCH\s+FIRST\s+\d+\s+ROWS\s+ONLY\b", sql, re.IGNORECASE):
            return sql
        trailing_clause = re.search(r"\s+(WITH\s+UR(?:\s+OPTIMIZE\s+FOR\s+\d+\s+ROWS)?|OPTIMIZE\s+FOR\s+\d+\s+ROWS)\s*$", sql, re.IGNORECASE)
        if trailing_clause:
            return f"{sql[:trailing_clause.start()]} FETCH FIRST {limit} ROWS ONLY{sql[trailing_clause.start():]}"
        return f"{sql} FETCH FIRST {limit} ROWS ONLY"
    if dialect in {SQL_SERVER, ACCESS, UNKNOWN}:
        return f"SELECT TOP {limit} * FROM (\n{sql}\n) AS QOBJ_PREVIEW"
    return f"SELECT TOP {limit} * FROM (\n{sql}\n) AS QOBJ_PREVIEW"


class QueryObjectViewerWindow(FramelessWindowBase):
    """Non-blocking QueryObject browser and inspector."""

    _instance = None

    def __init__(self, parent=None):
        self._current: QueryObject | None = None
        self._current_forge_name = ""
        self._current_source_path = ""
        self._loading_detail = False
        self._loading_tree = False
        self._loading_source_tree = False
        self._restoring_left_width = False
        self._left_panel_width = self._load_left_panel_width()
        self._audit_parent = parent
        self._dataforge_builder_windows: list[QDialog] = []
        self._audit_builder_windows: list[QWidget] = []
        self._file_nav_window = None
        self._embedded_common_tables = None
        self._embedded_registry = None
        super().__init__(
            title="Object Browser",
            default_size=(1120, 620),
            min_size=(760, 420),
            parent=None,
            header_colors=_HEADER_COLORS,
            border_color=_BORDER_COLOR,
        )

    @classmethod
    def show_instance(cls, parent=None):
        if cls._instance is None or not cls._instance.isVisible():
            cls._instance = cls(parent)
            cls._instance.show()
        else:
            if parent is not None:
                cls._instance._audit_parent = parent
            cls._instance.refresh()
            cls._instance.raise_()
            cls._instance.activateWindow()
        return cls._instance

    def build_content(self) -> QWidget:
        body = QWidget()
        body.setStyleSheet("QWidget { background-color: #F0F0F0; }")
        root = QVBoxLayout(body)
        root.setContentsMargins(4, 2, 4, 4)
        root.setSpacing(4)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        self._browser_splitter = splitter
        splitter.setChildrenCollapsible(False)
        splitter.setHandleWidth(4)
        splitter.splitterMoved.connect(self._on_browser_splitter_moved)

        left = QWidget()
        left.setMinimumWidth(_LEFT_PANEL_MIN_WIDTH)
        left.setMaximumWidth(_LEFT_PANEL_MAX_WIDTH)
        left.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        left_lay = QVBoxLayout(left)
        left_lay.setContentsMargins(0, 0, 0, 0)
        left_lay.setSpacing(0)

        self.left_tabs = QTabWidget()
        self.left_tabs.setFont(_FONT_SMALL)
        self.left_tabs.setStyleSheet(
            "QTabWidget::pane { border: 1px solid #1E5BA8; background: white; }"
            "QTabBar::tab { background: #E8F0FB; color: #0D3A7A;"
            " border: 1px solid #A0C4E8; border-bottom: none;"
            " padding: 3px 5px; font-size: 8pt; }"
            "QTabBar::tab:selected { background: white; color: #1E5BA8; font-weight: bold; }"
        )

        queried_panel = QWidget()
        queried_lay = QVBoxLayout(queried_panel)
        queried_lay.setContentsMargins(3, 3, 3, 3)
        queried_lay.setSpacing(4)

        lbl_left = QLabel("Queries")
        lbl_left.setFont(_FONT_BOLD)
        lbl_left.setStyleSheet("color: #1E5BA8;")
        queried_lay.addWidget(lbl_left)

        search_row = QWidget()
        search_lay = QHBoxLayout(search_row)
        search_lay.setContentsMargins(0, 0, 0, 0)
        search_lay.setSpacing(4)

        self.edit_search = self._make_search_edit("Search query objects...")
        self.edit_search.textChanged.connect(lambda _text: self.refresh())
        search_lay.addWidget(self.edit_search, 1)
        queried_lay.addWidget(search_row)

        self.tree = _OrganizerTree(self)
        self.tree.setHeaderHidden(True)
        self.tree.setMinimumWidth(210)
        self.tree.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.tree.setRootIsDecorated(False)
        self.tree.setIndentation(14)
        self.tree.setUniformRowHeights(False)
        self.tree.setItemDelegate(_OrganizerPillDelegate(self.tree))
        self.tree.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.tree.setFont(_FONT)
        self.tree.setStyleSheet(
            "QTreeWidget { border: 1px solid #1E5BA8; background: white; }"
            "QTreeWidget::item { padding: 0px; border: none; background: transparent; }"
            "QTreeWidget::item:selected { background: transparent; color: black; }"
        )
        self.tree.itemClicked.connect(self._on_tree_clicked)
        self.tree.currentItemChanged.connect(self._on_tree_selection)
        self.tree.itemDoubleClicked.connect(self._on_tree_double_clicked)
        self.tree.itemExpanded.connect(lambda item: self._on_tree_expansion_changed(item, True))
        self.tree.itemCollapsed.connect(lambda item: self._on_tree_expansion_changed(item, False))
        self.tree.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.tree.customContextMenuRequested.connect(self._show_tree_context_menu)
        queried_lay.addWidget(self.tree, 1)

        self.left_tabs.addTab(queried_panel, "Queries")
        self.left_tabs.addTab(self._build_data_source_panel(), "Data Sources")
        self._tables_left_host = self._make_embedded_host()
        self._registry_left_host = self._make_embedded_host()
        self.left_tabs.addTab(self._tables_left_host, "Tables")
        self.left_tabs.addTab(self._registry_left_host, "Registry")
        self.left_tabs.currentChanged.connect(self._on_left_tab_changed)
        left_lay.addWidget(self.left_tabs, 1)

        splitter.addWidget(left)

        right = QWidget()
        right.setMinimumWidth(_RIGHT_PANEL_MIN_WIDTH)
        right.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Expanding)
        right_lay = QVBoxLayout(right)
        right_lay.setContentsMargins(0, 0, 0, 0)
        right_lay.setSpacing(4)

        info = QWidget()
        info_lay = QHBoxLayout(info)
        info_lay.setContentsMargins(0, 0, 0, 0)
        info_lay.setSpacing(10)

        self.lbl_name = QLabel("Select a QueryObject")
        self.lbl_name.setFont(QFont("Segoe UI", 14, QFont.Weight.Bold))
        self.lbl_name.setStyleSheet("color: #1E5BA8;")
        self.lbl_name.setFixedWidth(430)
        self.lbl_name.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        info_lay.addWidget(self.lbl_name)

        self.lbl_kind = QLabel("")
        self.lbl_kind.setFont(_FONT)
        self.lbl_kind.setStyleSheet("color: #666;")
        self.lbl_kind.setVisible(False)
        info_lay.addWidget(self.lbl_kind)

        self.lbl_status = QLabel("")
        self.lbl_status.setFont(_FONT)
        self.lbl_status.setStyleSheet("color: #666;")
        self.lbl_status.setVisible(False)
        info_lay.addWidget(self.lbl_status)
        info_lay.addStretch()

        self.btn_open_builder = QPushButton("Open in Builder")
        self.btn_open_builder.setFont(_FONT_BOLD)
        self.btn_open_builder.setFixedSize(116, 26)
        self.btn_open_builder.setStyleSheet(_BTN_STYLE)
        self.btn_open_builder.setToolTip("Open this object in its designer when available")
        self.btn_open_builder.clicked.connect(self._on_open_builder)
        info_lay.addWidget(self.btn_open_builder)

        self.btn_preview_file = QPushButton("Preview File")
        self.btn_preview_file.setFont(_FONT_BOLD)
        self.btn_preview_file.setText("Preview Data")
        self.btn_preview_file.setFixedSize(98, 26)
        self.btn_preview_file.setStyleSheet(_BTN_STYLE)
        self.btn_preview_file.clicked.connect(self._on_preview_file)
        info_lay.addWidget(self.btn_preview_file)

        self.btn_open_source_folder = QPushButton("Open Folder")
        self.btn_open_source_folder.setFont(_FONT_BOLD)
        self.btn_open_source_folder.setFixedSize(98, 26)
        self.btn_open_source_folder.setStyleSheet(_BTN_STYLE)
        self.btn_open_source_folder.setToolTip("Open this source file's folder in File Nav")
        self.btn_open_source_folder.clicked.connect(self._on_open_source_folder)
        self.btn_open_source_folder.setVisible(False)
        info_lay.addWidget(self.btn_open_source_folder)

        self.btn_promote = QPushButton("Register Source")
        self.btn_promote.setFont(_FONT_BOLD)
        self.btn_promote.setFixedSize(112, 26)
        self.btn_promote.setStyleSheet(_BTN_STYLE)
        self.btn_promote.setToolTip("Mark a file source object as a registered, reusable source")
        self.btn_promote.clicked.connect(self._on_promote)
        self._promote_slot = QWidget()
        self._promote_slot.setFixedSize(112, 26)
        promote_lay = QHBoxLayout(self._promote_slot)
        promote_lay.setContentsMargins(0, 0, 0, 0)
        promote_lay.setSpacing(0)
        promote_lay.addWidget(self.btn_promote)
        info_lay.addWidget(self._promote_slot)

        self.btn_delete = QPushButton("Delete")
        self.btn_delete.setFont(_FONT_BOLD)
        self.btn_delete.setFixedSize(80, 26)
        self.btn_delete.setStyleSheet(_BTN_DANGER_STYLE)
        self.btn_delete.clicked.connect(self._on_delete)
        info_lay.addWidget(self.btn_delete)

        right_lay.addWidget(info)

        editor = QWidget()
        editor.setStyleSheet(
            "QWidget { background: #FAFBFD; border: 1px solid #C9D8EA; }"
            "QLabel { border: none; background: transparent; color: #444; }"
            "QLineEdit { background: white; border: 1px solid #A0C4E8; padding: 2px 4px; }"
        )
        editor_lay = QGridLayout(editor)
        editor_lay.setContentsMargins(6, 5, 6, 5)
        editor_lay.setHorizontalSpacing(6)
        editor_lay.setVerticalSpacing(4)

        self.edit_name = self._make_line_edit(0)
        self.edit_origin = self._make_line_edit(0)
        self.edit_origin.setToolTip("Builder/source that created this object, such as Query Studio, Cyberlife, Manual SQL, or csv")
        self.edit_tags = self._make_line_edit(0)
        self.edit_tags.setToolTip("Optional comma-separated labels for grouping and finding objects later")
        self.edit_description = self._make_line_edit(0)

        self._add_editor_field(editor_lay, 0, 0, "Object", self.edit_name)
        self._add_editor_field(editor_lay, 0, 2, "Builder", self.edit_origin)
        self._add_editor_field(editor_lay, 1, 0, "Description", self.edit_description)
        self._add_editor_field(editor_lay, 1, 2, "Tags", self.edit_tags)

        self.btn_save = QPushButton("Save")
        self.btn_save.setFont(_FONT_BOLD)
        self.btn_save.setFixedSize(72, 24)
        self.btn_save.setStyleSheet(_BTN_STYLE)
        self.btn_save.clicked.connect(self._on_save_changes)
        editor_lay.addWidget(self.btn_save, 0, 4, 2, 1, Qt.AlignmentFlag.AlignTop)
        editor_lay.setColumnStretch(1, 3)
        editor_lay.setColumnStretch(3, 2)
        editor_lay.setRowStretch(0, 0)
        editor_lay.setRowStretch(1, 0)
        editor_lay.setRowStretch(2, 1)

        self.tabs = QTabWidget()
        self.tabs.setFont(_FONT)
        self.tabs.setStyleSheet(
            "QTabWidget::pane { border: 2px solid #1E5BA8; background: white; }"
            "QTabBar::tab { padding: 4px 14px; font-size: 9pt;"
            " border: 1px solid #A0C4E8; border-bottom: none; margin-right: 1px; }"
            "QTabBar::tab:selected { background: white; color: #1E5BA8;"
            " font-weight: bold; }"
            "QTabBar::tab:!selected { background: #E8F0FB; color: #444; }"
        )

        self.tabs.addTab(editor, "Object")

        self.tbl_sources = self._make_table(["Name", "Type", "DSN", "Status"])
        self.tabs.addTab(self.tbl_sources, "Sources")

        self.tbl_outputs = self._make_table(["Field", "Type", "Display Name", "Source"])
        self.tabs.addTab(self.tbl_outputs, "Outputs")

        self.tbl_inputs = self._make_table(["Field", "Type", "Display Name", "Source"])
        self.tabs.addTab(self.tbl_inputs, "Inputs")

        self.tbl_joins = self._make_table(["Field", "Type", "Display Name", "Source"])
        self.tabs.addTab(self.tbl_joins, "Joins")

        self.tbl_fields = self._make_table(["Field", "Type", "Role", "Display Name", "Source"])
        self.tbl_fields.setEditTriggers(
            QAbstractItemView.EditTrigger.DoubleClicked
            | QAbstractItemView.EditTrigger.EditKeyPressed
            | QAbstractItemView.EditTrigger.SelectedClicked
        )
        self.tabs.addTab(self.tbl_fields, "All Fields")

        self.txt_sql = QTextEdit()
        self.txt_sql.setFont(_FONT_MONO)
        self.txt_sql.setReadOnly(False)
        self.txt_sql.setStyleSheet("QTextEdit { background: white; border: none; }")
        self.tabs.addTab(self.txt_sql, "SQL")

        self.txt_config = QTextEdit()
        self.txt_config.setFont(_FONT_MONO)
        self.txt_config.setReadOnly(True)
        self.txt_config.setStyleSheet("QTextEdit { background: white; border: none; }")
        self.tabs.addTab(self.txt_config, "Config")

        right_lay.addWidget(self.tabs, 1)

        self._detail_canvas = right
        self._browser_canvas_stack = QStackedWidget()
        self._browser_canvas_stack.addWidget(right)
        self._tables_canvas_host = self._make_embedded_host()
        self._registry_canvas_host = self._make_embedded_host()
        self._browser_canvas_stack.addWidget(self._tables_canvas_host)
        self._browser_canvas_stack.addWidget(self._registry_canvas_host)

        canvas_shell = QWidget()
        canvas_shell.setMinimumWidth(_RIGHT_PANEL_MIN_WIDTH)
        canvas_shell.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Expanding)
        canvas_lay = QVBoxLayout(canvas_shell)
        canvas_lay.setContentsMargins(0, 0, 0, 0)
        canvas_lay.setSpacing(4)

        self.lbl_canvas_title = QLabel("Object Browser")
        self.lbl_canvas_title.setFont(QFont("Segoe UI", 10, QFont.Weight.Bold))
        self.lbl_canvas_title.setMinimumHeight(28)
        self.lbl_canvas_title.setStyleSheet(
            "QLabel { background: #2A6BC4; color: white;"
            " border: 1px solid #14407A; padding: 4px 8px; }"
        )
        self.lbl_canvas_title.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        canvas_lay.addWidget(self.lbl_canvas_title)
        canvas_lay.addWidget(self._browser_canvas_stack, 1)

        splitter.addWidget(canvas_shell)
        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)
        splitter.setSizes([
            self._left_panel_width,
            max(_RIGHT_PANEL_MIN_WIDTH, 1120 - self._left_panel_width),
        ])

        root.addWidget(splitter, 1)

        self.refresh()
        QTimer.singleShot(0, self._apply_left_panel_width)
        return body

    @staticmethod
    def _make_line_edit(width: int) -> QLineEdit:
        edit = QLineEdit()
        edit.setFont(_FONT)
        edit.setFixedHeight(24)
        if width:
            edit.setFixedWidth(width)
        edit.setStyleSheet(
            "QLineEdit { background: white; border: 1px solid #A0C4E8;"
            " padding: 2px 4px; }"
        )
        return edit

    @staticmethod
    def _make_search_edit(placeholder: str) -> QLineEdit:
        edit = QLineEdit()
        edit.setFont(_FONT)
        edit.setFixedHeight(24)
        edit.setPlaceholderText(placeholder)
        edit.setClearButtonEnabled(True)
        edit.setStyleSheet(
            "QLineEdit { background: white; border: 1px solid #1E5BA8;"
            " border-radius: 3px; padding: 2px 6px; }"
        )
        return edit

    @staticmethod
    def _install_nav_search(panel: QWidget, search_edit: QLineEdit) -> None:
        layout = panel.layout()
        if layout is None:
            return
        layout.insertWidget(min(1, layout.count()), search_edit)

    def _set_canvas_title(self, title: str) -> None:
        if hasattr(self, "lbl_canvas_title"):
            self.lbl_canvas_title.setText(title or "Object Browser")

    def _make_embedded_host(self) -> QWidget:
        host = QWidget()
        lay = QVBoxLayout(host)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)
        return host

    @staticmethod
    def _replace_host_content(host: QWidget, child: QWidget) -> None:
        layout = host.layout()
        if layout is None:
            layout = QVBoxLayout(host)
            layout.setContentsMargins(0, 0, 0, 0)
            layout.setSpacing(0)
        while layout.count():
            item = layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.setParent(None)
        child.setParent(host)
        child.setVisible(True)
        layout.addWidget(child, 1)

    def _on_left_tab_changed(self, index: int) -> None:
        label = self.left_tabs.tabText(index)
        if label == "Tables":
            self._ensure_tables_embedded()
            self._browser_canvas_stack.setCurrentWidget(self._tables_canvas_host)
            self._update_common_tables_canvas_title()
            return
        if label == "Registry":
            self._ensure_registry_embedded()
            self._browser_canvas_stack.setCurrentWidget(self._registry_canvas_host)
            self._update_registry_canvas_title()
            return
        self._browser_canvas_stack.setCurrentWidget(self._detail_canvas)
        if label == "Data Sources":
            self._refresh_source_tree()
            self._update_data_sources_canvas_title()
        else:
            self._update_queried_canvas_title()

    def _ensure_tables_embedded(self) -> None:
        if self._embedded_common_tables is not None:
            return
        try:
            from suiteview.audit.common_table_dialog import CommonTableDialog
            self._embedded_common_tables = CommonTableDialog(parent=self)
            self._replace_host_content(
                self._tables_left_host, self._embedded_common_tables._nav_panel)
            self._replace_host_content(
                self._tables_canvas_host, self._embedded_common_tables._canvas_panel)
            self.edit_table_search = self._make_search_edit("Search common tables...")
            self.edit_table_search.textChanged.connect(self._filter_common_table_list)
            self._install_nav_search(
                self._embedded_common_tables._nav_panel, self.edit_table_search)
            self._embedded_common_tables.lst_tables.currentTextChanged.connect(
                lambda _name: self._update_common_tables_canvas_title())
            self._filter_common_table_list(self.edit_table_search.text())
        except Exception as exc:
            logger.exception("Failed to embed Common Tables in Object Browser")
            QMessageBox.warning(self, "Common Tables Error", str(exc))

    def _ensure_registry_embedded(self) -> None:
        if self._embedded_registry is not None:
            return
        try:
            from suiteview.audit.unique_value_registry_window import UniqueValueRegistryWindow
            self._embedded_registry = UniqueValueRegistryWindow(parent=self)
            self._replace_host_content(
                self._registry_left_host, self._embedded_registry._nav_panel)
            self._replace_host_content(
                self._registry_canvas_host, self._embedded_registry._canvas_panel)
            self.edit_registry_search = self._make_search_edit("Search registry fields...")
            self.edit_registry_search.textChanged.connect(self._filter_registry_tree)
            self._install_nav_search(
                self._embedded_registry._nav_panel, self.edit_registry_search)
            self._embedded_registry.tree.currentItemChanged.connect(
                lambda current, _previous: self._update_registry_canvas_title(current))
            self._filter_registry_tree(self.edit_registry_search.text())
        except Exception as exc:
            logger.exception("Failed to embed Registry in Object Browser")
            QMessageBox.warning(self, "Registry Error", str(exc))

    def _select_left_tab(self, label: str) -> None:
        for index in range(self.left_tabs.count()):
            if self.left_tabs.tabText(index) == label:
                self.left_tabs.setCurrentIndex(index)
                return

    def _open_common_tables(self):
        self._select_left_tab("Tables")

    def _open_registry(self):
        self._select_left_tab("Registry")

    def _update_queried_canvas_title(self) -> None:
        self._set_canvas_title(self._query_canvas_title())

    def _update_data_sources_canvas_title(self) -> None:
        self._set_canvas_title(self._data_source_canvas_title())

    def _update_common_tables_canvas_title(self) -> None:
        table_name = ""
        if self._embedded_common_tables is not None:
            current = self._embedded_common_tables.lst_tables.currentItem()
            table_name = current.text() if current is not None else ""
        self._set_canvas_title(f"Common Tables: {table_name}" if table_name else "Common Tables")

    def _update_registry_canvas_title(self, item: QTreeWidgetItem | None = None) -> None:
        if self._embedded_registry is None:
            self._set_canvas_title("Registry")
            return
        current = item or self._embedded_registry.tree.currentItem()
        if current is None:
            self._set_canvas_title("Registry")
            return
        parent = current.parent()
        grandparent = parent.parent() if parent is not None else None
        if grandparent is not None:
            self._set_canvas_title(f"Registry: {parent.text(0)}.{current.text(0)}")
        else:
            self._set_canvas_title(f"Registry: {current.text(0)}")

    def _query_canvas_title(self) -> str:
        payload = _payload(self.tree.currentItem()) if hasattr(self, "tree") else {}
        payload_type = payload.get("type")
        if payload_type == "query":
            obj = query_object_store.load_object_by_id(payload.get("id", ""))
            if obj is not None:
                return f"{_kind_label(obj.kind)}: {obj.name}"
            name = str(payload.get("name", "")).strip()
            return f"Queries: {name}" if name else "Queries"
        if payload_type == "group":
            name = str(payload.get("name", "")).strip()
            return f"Query Groups: {name}" if name else "Query Groups"
        if payload_type == "forge":
            name = str(payload.get("name", "")).strip()
            display_name = _dataforge_display_name(name) if name else ""
            return f"DataForge: {display_name}" if display_name else "DataForge"
        return "Queries"

    def _data_source_canvas_title(self) -> str:
        payload = _payload(self.source_tree.currentItem()) if hasattr(self, "source_tree") else {}
        payload_type = payload.get("type")
        if payload_type in {"query", "source_query"}:
            obj = query_object_store.load_object_by_id(payload.get("id", ""))
            name = obj.name if obj is not None else str(payload.get("name", "")).strip()
            return f"Data Sources: {name}" if name else "Data Sources"
        if payload_type == "odbc_source":
            dsn = str(payload.get("dsn", "")).strip()
            return f"Data Sources: {dsn}" if dsn else "Data Sources"
        if payload_type == "file_source":
            label = str(payload.get("label", "")).strip()
            return f"Data Sources: {label}" if label else "Data Sources"
        if payload_type == "source_group":
            group = str(payload.get("group", "")).strip().title()
            return f"Data Sources: {group}" if group else "Data Sources"
        return "Data Sources"

    def _filter_common_table_list(self, search_text: str) -> None:
        if self._embedded_common_tables is None:
            return
        table_list = self._embedded_common_tables.lst_tables
        for row in range(table_list.count()):
            item = table_list.item(row)
            item.setHidden(not self._text_matches_search(search_text, [item.text()]))
        self._update_common_tables_canvas_title()

    def _filter_registry_tree(self, search_text: str) -> None:
        if self._embedded_registry is None:
            return
        tree = self._embedded_registry.tree
        search_active = bool(search_text.strip())

        def _matches(item: QTreeWidgetItem) -> bool:
            return self._text_matches_search(
                search_text, [item.text(column) for column in range(tree.columnCount())])

        def _filter_item(item: QTreeWidgetItem, ancestor_matches: bool = False) -> bool:
            own_matches = _matches(item)
            descendant_matches = False
            for child_index in range(item.childCount()):
                child = item.child(child_index)
                descendant_matches = _filter_item(child, ancestor_matches or own_matches) or descendant_matches
            visible = not search_active or ancestor_matches or own_matches or descendant_matches
            item.setHidden(not visible)
            if search_active and visible and item.childCount():
                item.setExpanded(True)
            return visible

        root = tree.invisibleRootItem()
        for index in range(root.childCount()):
            _filter_item(root.child(index))
        self._update_registry_canvas_title()

    def _build_data_source_panel(self) -> QWidget:
        panel = QWidget()
        panel.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        panel_lay = QVBoxLayout(panel)
        panel_lay.setContentsMargins(3, 3, 3, 3)
        panel_lay.setSpacing(4)

        lbl = QLabel("Data Sources")
        lbl.setFont(_FONT_BOLD)
        lbl.setStyleSheet("color: #1E5BA8;")
        panel_lay.addWidget(lbl)

        self.edit_source_search = self._make_search_edit("Search data sources...")
        self.edit_source_search.textChanged.connect(lambda _text: self._refresh_source_tree())
        panel_lay.addWidget(self.edit_source_search)

        self.source_tree = QTreeWidget()
        self.source_tree.setHeaderHidden(True)
        self.source_tree.setDragEnabled(False)
        self.source_tree.setAcceptDrops(False)
        self.source_tree.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.source_tree.setRootIsDecorated(True)
        self.source_tree.setIndentation(14)
        self.source_tree.setUniformRowHeights(False)
        self.source_tree.setItemDelegate(_OrganizerPillDelegate(self.source_tree))
        self.source_tree.setFont(_FONT)
        self.source_tree.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.source_tree.setStyleSheet(
            "QTreeWidget { border: 1px solid #1E5BA8; background: white; }"
            "QTreeWidget::item { padding: 2px 3px; min-height: 19px; }"
            "QTreeWidget::item:selected { background: #D7E6F8; color: #0D3A7A; }"
        )
        self.source_tree.itemClicked.connect(self._on_source_tree_clicked)
        self.source_tree.currentItemChanged.connect(self._on_source_tree_selection)
        self.source_tree.itemDoubleClicked.connect(self._on_source_tree_double_clicked)
        panel_lay.addWidget(self.source_tree, 1)
        return panel

    @staticmethod
    def _add_editor_field(layout: QGridLayout, row: int, col: int, label: str, widget: QLineEdit):
        lbl = QLabel(label)
        lbl.setFont(_FONT_SMALL)
        layout.addWidget(lbl, row, col)
        layout.addWidget(widget, row, col + 1)

    @staticmethod
    def _make_table(headers: list[str]) -> QTableWidget:
        table = QTableWidget()
        table.setColumnCount(len(headers))
        table.setHorizontalHeaderLabels(headers)
        table.horizontalHeader().setStretchLastSection(True)
        table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        table.verticalHeader().setVisible(False)
        table.verticalHeader().setDefaultSectionSize(18)
        table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        table.setFont(_FONT)
        table.setStyleSheet(
            "QTableWidget { border: none; background: white; gridline-color: #E0E0E0; }"
            "QHeaderView::section { background: #E8F0FB; font-weight: bold;"
            " font-size: 8pt; border: 1px solid #C0C0C0; padding: 1px 4px; }"
        )
        return table

    @staticmethod
    def _set_table_headers(table: QTableWidget, headers: list[str]) -> None:
        table.clear()
        table.setColumnCount(len(headers))
        table.setHorizontalHeaderLabels(headers)
        table.setRowCount(0)

    @staticmethod
    def _set_table_rows(table: QTableWidget, rows: list[list[object]]) -> None:
        table.setRowCount(len(rows))
        for row_index, values in enumerate(rows):
            for col_index, value in enumerate(values):
                table.setItem(row_index, col_index, QTableWidgetItem(str(value)))
        table.resizeColumnsToContents()

    def _configure_object_tables(self) -> None:
        self._set_tab_labels([
            "Object", "Sources", "Outputs", "Inputs",
            "Joins", "All Fields", "SQL", "Config",
        ])
        self._set_table_headers(self.tbl_sources, ["Name", "Type", "DSN", "Status"])
        self._set_table_headers(self.tbl_outputs, ["Field", "Type", "Display Name", "Source"])
        self._set_table_headers(self.tbl_inputs, ["Field", "Type", "Display Name", "Source"])
        self._set_table_headers(self.tbl_joins, ["Field", "Type", "Display Name", "Source"])
        self._set_table_headers(self.tbl_fields, ["Field", "Type", "Role", "Display Name", "Source"])

    def _configure_forge_tables(self) -> None:
        self._set_tab_labels([
            "Forge", "Sources", "Outputs", "Filters",
            "Joins", "All Fields", "SQL", "Config",
        ])
        self._set_table_headers(self.tbl_sources, ["Source", "Query Copy", "Kind", "DSN", "Columns", "Snapshot", "Rows"])
        self._set_table_headers(self.tbl_outputs, ["Field", "Display Name", "Source", "Type"])
        self._set_table_headers(self.tbl_inputs, ["Filter Tab", "Field", "Mode", "Value"])
        self._set_table_headers(self.tbl_joins, ["Left Source", "Left Field(s)", "Right Source", "Right Field(s)", "Type"])
        self._set_table_headers(self.tbl_fields, ["Field", "Type", "Role", "Source"])

    def _configure_data_source_tables(self) -> None:
        self._set_tab_labels([
            "Source", "Setup", "Query Objects", "Source Uses",
            "Joins", "Fields", "SQL", "Config",
        ])
        self._set_table_headers(self.tbl_sources, ["Property", "Value"])
        self._set_table_headers(self.tbl_outputs, ["Query Object", "Kind", "Builder", "Fields"])
        self._set_table_headers(self.tbl_inputs, ["Query Object", "Source/Table", "Type", "Status"])
        self._set_table_headers(self.tbl_joins, ["", ""])
        self._set_table_headers(self.tbl_fields, ["Query Object", "Field", "Role", "Type", "Source"])

    def _set_tab_labels(self, labels: list[str]) -> None:
        if not hasattr(self, "tabs"):
            return
        for index, label in enumerate(labels):
            if index >= self.tabs.count():
                break
            self.tabs.setTabText(index, label)

    def refresh(self):
        """Rebuild the tree from the organizer: groups, forges, loose queries.

        Weight tells structure (query < Group < Forge), color tells origin
        (build-mode chips/tints; DataForge orange) — design §8.
        """
        current_payload = _payload(self.tree.currentItem())
        search_text = self.edit_search.text() if hasattr(self, "edit_search") else ""
        search_active = bool(search_text.strip())
        self._loading_tree = True
        self.tree.clear()
        self.tree.setDragEnabled(not search_active)
        self.tree.setAcceptDrops(not search_active)
        self.tree.setDropIndicatorShown(not search_active)
        self._ensure_dataforge_query_objects()
        objects = query_object_store.list_objects()
        by_id = {o.id: o for o in objects}

        # Forge-owned Source copies render under their forge node.
        forge_children: dict[str, list[QueryObject]] = {}
        for obj in objects:
            info = _dataforge_info(obj)
            if info is not None:
                forge_children.setdefault(info[0], []).append(obj)

        from suiteview.audit.dataforge import dataforge_store
        forge_names = [f.name for f in dataforge_store.list_forges()]
        organizer = get_query_organizer()
        if organizer.reconcile(objects, forge_names):
            organizer.save()

        fallback_item = None
        selected_item = None

        def _track(item: QTreeWidgetItem, payload: dict):
            nonlocal fallback_item, selected_item
            if fallback_item is None and payload.get("type") == "query":
                fallback_item = item
            if current_payload and payload.get("type") == current_payload.get("type"):
                keys = {"query": ("id",), "group": ("group_id",),
                        "forge": ("name",)}.get(payload.get("type"), ())
                if keys and all(payload.get(k) == current_payload.get(k)
                                for k in keys):
                    selected_item = item

        def _add_query_item(parent, obj: QueryObject, forge_name: str = ""):
            style = mode_style(obj.kind)
            dsn = _display_dsn_for_object(obj) or "?"
            item = QTreeWidgetItem([f"{obj.name}  [{dsn}]"])
            item.setFont(0, _FONT)
            item.setForeground(0, QColor(style.color))
            item.setBackground(0, QBrush(QColor(style.tint)))
            item.setToolTip(0, f"{style.label} — {dsn}")
            payload = {
                "type": "query",
                "id": obj.id,
                "name": obj.name,
                "badge": _QUERY_BADGES.get(obj.kind, "Q"),
                "badge_color": style.color,
                "badge_fill": style.color,
                "badge_text_color": "#FFFFFF",
            }
            if forge_name:
                payload["forge"] = forge_name
            item.setData(0, Qt.ItemDataRole.UserRole, payload)
            if parent is None:
                self.tree.addTopLevelItem(item)
            else:
                parent.addChild(item)
            _track(item, payload)
            return item

        def _add_forge_item(forge_name: str):
            children = sorted(forge_children.get(forge_name, []),
                              key=lambda o: o.name.lower())
            forge_matches = self._text_matches_search(
                search_text, ["DataForge", _dataforge_display_name(forge_name), forge_name])
            if search_text:
                children = [obj for obj in children
                            if self._object_matches_search(obj, search_text)]
            if search_text and not forge_matches and not children:
                return
            item = QTreeWidgetItem([f"⚙ {_dataforge_display_name(forge_name)} ({len(children)})"])
            item.setFont(0, QFont("Segoe UI", 10, QFont.Weight.Bold))
            item.setForeground(0, QColor(FORGE_STYLE.color))
            item.setBackground(0, QBrush(QColor(FORGE_STYLE.tint)))
            item.setSizeHint(0, QSize(0, 30))
            payload = {"type": "forge", "name": forge_name}
            item.setData(0, Qt.ItemDataRole.UserRole, payload)
            self.tree.addTopLevelItem(item)
            for obj in children:
                _add_query_item(item, obj, forge_name=forge_name)
            item.setExpanded(self._expanded_for_item(payload, search_active))
            _track(item, payload)

        def _add_group_item(group: dict):
            children = []
            group_matches = self._text_matches_search(search_text, [group["name"]])
            for child in group.get("items", []):
                obj = by_id.get(child.get("query_id"))
                if obj is not None and (not search_text
                                        or self._object_matches_search(obj, search_text)):
                    children.append(obj)
            if search_text and not group_matches and not children:
                return
            prefix = "" if group.get("id") == COMMONS_GROUP_ID else "▣ "
            item = QTreeWidgetItem([f"{prefix}{group['name']} ({len(children)})"])
            item.setFont(0, QFont("Segoe UI", 9, QFont.Weight.Bold))
            item.setForeground(0, QColor(GROUP_STYLE.color))
            item.setBackground(0, QBrush(QColor(GROUP_STYLE.tint)))
            item.setSizeHint(0, QSize(0, 30))
            payload = {"type": "group", "group_id": group["id"],
                       "name": group["name"],
                       "color": group.get("color"),
                       "expanded": group.get("expanded", True)}
            item.setData(0, Qt.ItemDataRole.UserRole, payload)
            self.tree.addTopLevelItem(item)
            for obj in children:
                _add_query_item(item, obj)
            item.setExpanded(self._expanded_for_item(payload, search_active))
            _track(item, payload)

        for entry in organizer.items:
            kind = entry.get("type")
            if kind == "query":
                obj = by_id.get(entry.get("query_id"))
                if obj is not None and self._object_matches_search(obj, search_text):
                    _add_query_item(None, obj)
            elif kind == "group":
                _add_group_item(entry)
            elif kind == "forge":
                _add_forge_item(entry.get("name", ""))

        item_to_select = selected_item or fallback_item
        if item_to_select is not None:
            self.tree.setCurrentItem(item_to_select)
        else:
            self._clear_detail()
        self._loading_tree = False
        if hasattr(self, "source_tree"):
            self._refresh_source_tree(objects)

    def _refresh_source_tree(self, objects: list[QueryObject] | None = None) -> None:
        if not hasattr(self, "source_tree"):
            return
        current_payload = _payload(self.source_tree.currentItem())
        search_text = self.edit_source_search.text() if hasattr(self, "edit_source_search") else ""
        search_active = bool(search_text.strip())
        self._loading_source_tree = True
        self.source_tree.clear()
        objects = objects if objects is not None else query_object_store.list_objects()
        index = self._build_data_source_index(objects)

        selected_item = None

        def _track(item: QTreeWidgetItem, payload: dict) -> None:
            nonlocal selected_item
            if not current_payload or payload.get("type") != current_payload.get("type"):
                return
            keys = {
                "odbc_source": ("dsn",),
                "file_source": ("key",),
                "query": ("id", "source_key"),
                "source_query": ("id", "source_key"),
                "source_group": ("group",),
            }.get(payload.get("type"), ())
            if keys and all(payload.get(key) == current_payload.get(key) for key in keys):
                selected_item = item

        def _add_query_leaf(parent: QTreeWidgetItem, obj: QueryObject, source_key: str) -> None:
            style = mode_style(obj.kind)
            dsn = _display_dsn_for_object(obj) or obj.source_design or "?"
            item = QTreeWidgetItem([f"{obj.name}  [{dsn}]"])
            item.setFont(0, _FONT)
            item.setForeground(0, QColor(style.color))
            item.setBackground(0, QBrush(QColor(style.tint)))
            item.setToolTip(0, f"{style.label} - {dsn}")
            payload = {
                "type": "query",
                "id": obj.id,
                "name": obj.name,
                "source_key": source_key,
                "source_tree": True,
                "badge": _QUERY_BADGES.get(obj.kind, "Q"),
                "badge_color": style.color,
                "badge_fill": style.color,
                "badge_text_color": "#FFFFFF",
            }
            item.setData(0, Qt.ItemDataRole.UserRole, payload)
            parent.addChild(item)
            _track(item, payload)

        def _filtered_source_objects(source: dict) -> list[QueryObject]:
            source_values = [
                source.get("label", ""), source.get("path", ""),
                source.get("source_type", ""), source.get("group", ""),
            ]
            source_matches = self._text_matches_search(search_text, source_values)
            if source_matches:
                return list(source.get("objects", []))
            return [
                obj for obj in source.get("objects", [])
                if self._object_matches_search(obj, search_text)
            ]

        def _add_group(group_key: str, title: str, sources: list[dict]) -> None:
            visible_sources: list[tuple[dict, list[QueryObject]]] = []
            for source in sources:
                children = _filtered_source_objects(source)
                source_matches = self._text_matches_search(search_text, [
                    source.get("label", ""), source.get("path", ""),
                    source.get("source_type", ""), title,
                ])
                if not search_active or source_matches or children:
                    visible_sources.append((source, children))
            if search_active and not visible_sources:
                return
            root = QTreeWidgetItem([f"{title} ({len(visible_sources)})"])
            root.setFont(0, QFont("Segoe UI", 9, QFont.Weight.Bold))
            root.setForeground(0, QColor("#0D3A7A"))
            root.setBackground(0, QBrush(QColor("#E8F0FB")))
            payload = {"type": "source_group", "group": group_key}
            root.setData(0, Qt.ItemDataRole.UserRole, payload)
            self.source_tree.addTopLevelItem(root)
            _track(root, payload)
            for source, children in visible_sources:
                label = source.get("label", "")
                source_item = QTreeWidgetItem([label])
                source_item.setFont(0, _FONT_BOLD)
                source_item.setForeground(0, QColor("#1E5BA8" if group_key == "odbc" else "#8B6914"))
                tooltip = source.get("path") or source.get("dsn") or label
                source_item.setToolTip(0, tooltip)
                source_payload = {
                    "type": "odbc_source" if group_key == "odbc" else "file_source",
                    "group": group_key,
                    "key": source.get("key", ""),
                    "dsn": source.get("dsn", ""),
                    "path": source.get("path", ""),
                    "label": label,
                    "source_type": source.get("source_type", ""),
                    "metadata": source.get("metadata", {}),
                    "object_ids": [obj.id for obj in source.get("objects", [])],
                }
                source_item.setData(0, Qt.ItemDataRole.UserRole, source_payload)
                root.addChild(source_item)
                _track(source_item, source_payload)
                for obj in children:
                    _add_query_leaf(source_item, obj, source.get("key", ""))
                source_item.setExpanded(search_active)
            root.setExpanded(True)

        _add_group("odbc", "ODBC", sorted(index["odbc"].values(), key=lambda item: item["label"].lower()))
        _add_group("files", "Files", sorted(index["files"].values(), key=lambda item: (item["label"].lower(), item.get("path", "").lower())))

        if selected_item is not None:
            self.source_tree.setCurrentItem(selected_item)
        self._loading_source_tree = False

    def _build_data_source_index(self, objects: list[QueryObject]) -> dict[str, dict[str, dict]]:
        index: dict[str, dict[str, dict]] = {"odbc": {}, "files": {}}

        for obj in objects:
            for dsn in self._odbc_dsns_for_object(obj):
                entry = index["odbc"].setdefault(dsn.lower(), {
                    "group": "odbc",
                    "key": dsn.lower(),
                    "label": dsn,
                    "dsn": dsn,
                    "objects": [],
                })
                if all(existing.id != obj.id for existing in entry["objects"]):
                    entry["objects"].append(obj)

            for file_entry in self._file_sources_for_object(obj):
                key = file_entry["key"]
                entry = index["files"].setdefault(key, {
                    "group": "files",
                    "key": key,
                    "label": file_entry["label"],
                    "path": file_entry["path"],
                    "source_type": file_entry["source_type"],
                    "metadata": file_entry["metadata"],
                    "objects": [],
                })
                if all(existing.id != obj.id for existing in entry["objects"]):
                    entry["objects"].append(obj)

        for group in index.values():
            for entry in group.values():
                entry["objects"].sort(key=lambda item: item.name.lower())
        return index

    @staticmethod
    def _odbc_dsns_for_object(obj: QueryObject) -> list[str]:
        if obj.kind == OBJECT_KIND_ADHOC_SOURCE:
            return []
        dsns: set[str] = set()
        if obj.dsn.strip():
            dsns.add(obj.dsn.strip())
        for source in obj.sources:
            if source.dsn.strip():
                dsns.add(source.dsn.strip())
        return sorted(dsns, key=str.lower)

    @staticmethod
    def _file_sources_for_object(obj: QueryObject) -> list[dict]:
        entries: list[dict] = []
        for source in obj.sources:
            metadata = dict(source.metadata or {})
            path = str(metadata.get("path", "")).strip()
            source_type = (source.source_type or obj.source_design or "").strip().lower()
            if obj.kind != OBJECT_KIND_ADHOC_SOURCE and not path and source_type not in _FILE_SOURCE_TYPES:
                continue
            label = _filename_from_path(path or source.name or obj.name)
            entries.append({
                "key": _file_source_key(path, source.name or obj.name),
                "label": label,
                "path": path,
                "source_type": source_type or source.source_type or obj.source_design,
                "metadata": metadata,
                "source_name": source.name,
                "status": source.status,
            })
        if not entries and obj.kind == OBJECT_KIND_ADHOC_SOURCE:
            metadata = dict((obj.config or {}).get("source_metadata", {}) or {})
            path = str(metadata.get("path", "")).strip()
            entries.append({
                "key": _file_source_key(path, obj.name),
                "label": _filename_from_path(path or obj.name),
                "path": path,
                "source_type": obj.source_design,
                "metadata": metadata,
                "source_name": obj.name,
                "status": obj.metadata_status,
            })
        return entries

    def _on_source_tree_clicked(self, item: QTreeWidgetItem, column: int) -> None:
        payload = _payload(item)
        if payload.get("type") == "source_group":
            item.setExpanded(not item.isExpanded())

    def _on_source_tree_selection(self, current, previous) -> None:
        if self._loading_source_tree:
            return
        payload = _payload(current)
        payload_type = payload.get("type")
        if payload_type in {"query", "source_query"}:
            obj = query_object_store.load_object_by_id(payload.get("id", ""))
            if obj is not None:
                self._show_detail(obj)
            return
        if payload_type == "odbc_source":
            self._show_odbc_source_detail(payload)
            return
        if payload_type == "file_source":
            self._show_file_source_detail(payload)
            return
        self._update_data_sources_canvas_title()

    def _on_source_tree_double_clicked(self, item: QTreeWidgetItem, column: int) -> None:
        payload = _payload(item)
        if payload.get("type") not in {"query", "source_query"}:
            return
        obj = query_object_store.load_object_by_id(payload.get("id", ""))
        if obj is None:
            return
        self._show_detail(obj)
        if self._current is not None and self._can_open_in_builder(self._current):
            self._on_open_builder()

    def _expanded_for_item(self, payload: dict, search_active: bool) -> bool:
        if search_active:
            return True
        if payload.get("type") == "group":
            return bool(payload.get("expanded", True))
        if payload.get("type") == "forge":
            organizer = get_query_organizer()
            ref = organizer.forge_ref(payload.get("name", ""))
            return bool((ref or {}).get("expanded", True))
        return False

    def _set_all_containers_expanded(self, expanded: bool) -> None:
        organizer = get_query_organizer()
        for entry in organizer.items:
            if entry.get("type") == "group":
                organizer.set_group_expanded(entry.get("id"), expanded)
            elif entry.get("type") == "forge":
                organizer.set_forge_expanded(entry.get("name", ""), expanded)
        organizer.save()
        self.refresh()

    def _on_tree_expansion_changed(self, item: QTreeWidgetItem, expanded: bool) -> None:
        if self._loading_tree:
            return
        payload = _payload(item)
        organizer = get_query_organizer()
        changed = False
        if payload.get("type") == "group":
            changed = organizer.set_group_expanded(payload.get("group_id"), expanded)
        elif payload.get("type") == "forge":
            changed = organizer.set_forge_expanded(payload.get("name", ""), expanded)
        if changed:
            organizer.save()

    def _on_tree_clicked(self, item: QTreeWidgetItem, column: int) -> None:
        payload = _payload(item)
        if payload.get("type") in {"group", "forge"}:
            item.setExpanded(not item.isExpanded())

    @staticmethod
    def _load_left_panel_width() -> int:
        ui = load_ui_settings()
        width = ui.get("query_object_browser_left_width", _LEFT_PANEL_DEFAULT_WIDTH)
        if not isinstance(width, (int, float)):
            return _LEFT_PANEL_DEFAULT_WIDTH
        return max(_LEFT_PANEL_MIN_WIDTH, min(int(width), _LEFT_PANEL_MAX_WIDTH))

    def _save_left_panel_width(self) -> None:
        ui = load_ui_settings()
        ui["query_object_browser_left_width"] = self._left_panel_width
        save_ui_settings(ui)

    def _on_browser_splitter_moved(self, pos: int, index: int) -> None:
        if self._restoring_left_width:
            return
        handle = self._browser_splitter.handle(index)
        user_drag = bool(QApplication.mouseButtons() & Qt.MouseButton.LeftButton)
        if handle is None or not handle.underMouse() or not user_drag:
            QTimer.singleShot(0, self._apply_left_panel_width)
            return
        sizes = self._browser_splitter.sizes()
        if not sizes:
            return
        width = max(_LEFT_PANEL_MIN_WIDTH, min(int(sizes[0]), _LEFT_PANEL_MAX_WIDTH))
        self._left_panel_width = width
        self._save_left_panel_width()

    def _apply_left_panel_width(self) -> None:
        splitter = getattr(self, "_browser_splitter", None)
        if splitter is None:
            return
        sizes = splitter.sizes()
        total = sum(sizes) if sizes else 1120
        width = max(_LEFT_PANEL_MIN_WIDTH, min(self._left_panel_width, _LEFT_PANEL_MAX_WIDTH))
        self._restoring_left_width = True
        try:
            splitter.setSizes([width, max(_RIGHT_PANEL_MIN_WIDTH, total - width)])
        finally:
            self._restoring_left_width = False

    def _restore_left_panel_width(self) -> None:
        try:
            self._apply_left_panel_width()
        finally:
            self._restoring_left_width = False

    @staticmethod
    def _text_matches_search(search_text: str, values: list[object]) -> bool:
        terms = [term for term in search_text.lower().split() if term]
        if not terms:
            return True
        haystack = " ".join(str(value or "") for value in values).lower()
        return all(term in haystack for term in terms)

    @staticmethod
    def _object_matches_search(obj: QueryObject, search_text: str) -> bool:
        return QueryObjectViewerWindow._text_matches_search(search_text, [
            obj.name,
            _display_dsn_for_object(obj),
            _kind_label(obj.kind),
            obj.source_design,
            obj.description,
            " ".join(obj.tags),
        ])

    def _ensure_dataforge_query_objects(self) -> None:
        """Publish missing browser QueryObjects from saved DataForge definitions."""
        from suiteview.audit.dataforge import dataforge_store

        for forge in dataforge_store.list_forges():
            for source in forge.sources:
                definition = source.definition or {}
                copy_name = str(definition.get("name", "")).strip() or source.query_name
                if not copy_name:
                    continue
                source_label = self._definition_source_label(definition, source.query_name)
                existing = query_object_store.load_object(copy_name)
                if existing is not None and _dataforge_info(existing) is not None:
                    continue
                try:
                    if "kind" in definition:
                        obj = QueryObject.from_dict(definition)
                    else:
                        qd = QDefinition.from_dict(definition)
                        qd.forge_name = forge.name
                        obj = object_from_qdefinition(qd)
                except Exception:
                    logger.exception("Failed to repair DataForge QueryObject: %s", copy_name)
                    continue
                obj.name = copy_name
                obj.config = dict(obj.config or {})
                obj.config["dataforge"] = {
                    "forge_name": forge.name,
                    "source_name": source_label,
                }
                obj.source_design = obj.source_design or source_label
                query_object_store.save_object(obj)

    def select_object(self, name: str):
        """Refresh and select a Query Object by name if it exists."""
        self.refresh()

        def _select_under(item: QTreeWidgetItem) -> bool:
            payload = _payload(item)
            if payload.get("type") == "query" and payload.get("name") == name:
                self.tree.setCurrentItem(item)
                return True
            for index in range(item.childCount()):
                if _select_under(item.child(index)):
                    return True
            return False

        for i in range(self.tree.topLevelItemCount()):
            if _select_under(self.tree.topLevelItem(i)):
                return

    def _select_object(self, name: str):
        self.select_object(name)

    def _on_tree_selection(self, current, previous):
        self._update_group_action_buttons()
        saved_width = self._left_panel_width
        self._restoring_left_width = True
        payload = _payload(current)
        try:
            if payload.get("type") == "forge":
                self._clear_detail()
                return
            if payload.get("type") == "query":
                obj = query_object_store.load_object_by_id(payload.get("id", ""))
                if obj is not None:
                    self._show_detail(obj)
                    return
            self._clear_detail()
        finally:
            self._left_panel_width = saved_width
            QTimer.singleShot(0, self._restore_left_panel_width)

    def _selected_group_payload(self) -> dict:
        payload = _payload(self.tree.currentItem())
        return payload if payload.get("type") == "group" else {}

    def _selected_group_is_editable(self) -> bool:
        payload = self._selected_group_payload()
        return bool(payload and payload.get("group_id") != COMMONS_GROUP_ID)

    def _update_group_action_buttons(self) -> None:
        return

    def _on_rename_selected_group(self) -> None:
        payload = self._selected_group_payload()
        if not payload or payload.get("group_id") == COMMONS_GROUP_ID:
            return
        self._rename_group(payload)

    def _on_color_selected_group(self) -> None:
        payload = self._selected_group_payload()
        if not payload or payload.get("group_id") == COMMONS_GROUP_ID:
            return
        self._choose_group_color(payload)

    def _on_delete_selected_group(self) -> None:
        payload = self._selected_group_payload()
        if not payload or payload.get("group_id") == COMMONS_GROUP_ID:
            return
        self._delete_group_and_queries(payload)

    def _on_tree_double_clicked(self, item, column):
        payload = _payload(item)
        if payload.get("type") == "forge":
            self._open_dataforge_builder(payload.get("name", ""))
            return
        if payload.get("type") == "query":
            obj = query_object_store.load_object_by_id(payload.get("id", ""))
            if obj is not None and self._can_open_in_builder(obj):
                self._open_query_object_builder(obj.name)
            return
        if self._current is not None and self._can_open_in_builder(self._current):
            self._on_open_builder()

    def _show_tree_context_menu(self, pos):
        item = self.tree.itemAt(pos)
        payload = _payload(item)
        global_pos = self.tree.viewport().mapToGlobal(pos)

        # Background: organizer-level actions.
        if item is None or not payload:
            menu = QMenu(self)
            new_query, new_forge = self._add_creation_actions(menu)
            menu.addSeparator()
            new_group = menu.addAction("New Query Group...")
            chosen = menu.exec(global_pos)
            if self._handle_creation_action(chosen, new_query, new_forge):
                return
            if chosen == new_group:
                self._on_new_group()
            return

        self.tree.setCurrentItem(item)

        if payload["type"] == "group":
            self._group_context_menu(payload, global_pos)
        elif payload["type"] == "forge":
            self._forge_context_menu(payload, global_pos)
        elif payload.get("forge"):
            self._forge_query_context_menu(payload, global_pos)
        else:
            self._query_context_menu(payload, global_pos)

    def _group_context_menu(self, payload: dict, global_pos):
        group_id = payload["group_id"]
        menu = QMenu(self)
        is_commons = group_id == COMMONS_GROUP_ID
        rename = menu.addAction("Rename Group...")
        rename.setEnabled(not is_commons)
        color = menu.addAction("Group Color...")
        color.setEnabled(not is_commons)
        clone = menu.addAction("Clone Group (with queries)")
        clone.setEnabled(not is_commons)
        menu.addSeparator()
        new_query, new_forge = self._add_creation_actions(menu)
        new_group = menu.addAction("New Query Group...")
        menu.addSeparator()
        delete = menu.addAction("Delete Group and Queries")
        delete.setEnabled(not is_commons)

        chosen = menu.exec(global_pos)
        organizer = get_query_organizer()
        if chosen == rename:
            self._rename_group(payload)
        elif chosen == color:
            self._choose_group_color(payload)
        elif chosen == clone:
            organizer.clone_group(group_id)
            organizer.save()
            self.refresh()
        elif self._handle_creation_action(chosen, new_query, new_forge):
            return
        elif chosen == new_group:
            self._on_new_group()
        elif chosen == delete:
            self._delete_group_and_queries(payload)

    def _rename_group(self, payload: dict) -> None:
        group_id = payload.get("group_id")
        if group_id == COMMONS_GROUP_ID:
            return
        new_name, ok = QInputDialog.getText(
            self, "Rename Group", "Group name:", text=payload.get("name", ""))
        if ok and new_name.strip():
            organizer = get_query_organizer()
            organizer.rename_group(group_id, new_name)
            organizer.save()
            self.refresh()

    def _choose_group_color(self, payload: dict) -> None:
        group_id = payload.get("group_id")
        if group_id == COMMONS_GROUP_ID:
            return
        picker = ColorPickerPopup(self, payload.get("color"))
        picker.color_selected.connect(lambda color: self._set_group_color(group_id, color))
        picker.move(self.mapToGlobal(self.rect().center()))
        picker.show()

    def _set_group_color(self, group_id: int, color: str) -> None:
        organizer = get_query_organizer()
        if organizer.set_group_color(group_id, color):
            organizer.save()
            self.refresh()

    def _delete_group_and_queries(self, payload: dict) -> None:
        group_id = payload.get("group_id")
        if group_id == COMMONS_GROUP_ID:
            return
        organizer = get_query_organizer()
        group = organizer.find_group(group_id)
        if group is None:
            return
        query_ids = [child.get("query_id") for child in group.get("items", [])
                     if child.get("type") == "query" and child.get("query_id")]
        reply = QMessageBox.question(
            self,
            "Delete Query Group",
            f"Delete group \"{group.get('name', payload.get('name', ''))}\"?\n\n"
            f"All {len(query_ids)} query object(s) inside this group will be deleted. "
            "This cannot be undone.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return
        for query_id in query_ids:
            query_object_store.delete_object_by_id(query_id)
        organizer.delete_group(group_id, keep_queries=False)
        organizer.save()
        self.refresh()
        self._clear_detail()

    def _forge_context_menu(self, payload: dict, global_pos):
        forge_name = payload["name"]
        menu = QMenu(self)
        open_forge = menu.addAction("Open DataForge in Builder")
        clone = menu.addAction("Clone DataForge (with Sources + Snapshots)")
        menu.addSeparator()
        delete_forge = menu.addAction("Delete DataForge")
        menu.addSeparator()
        new_query, new_forge = self._add_creation_actions(menu)

        chosen = menu.exec(global_pos)
        if chosen == open_forge:
            self._open_dataforge_builder(forge_name)
        elif chosen == clone:
            organizer = get_query_organizer()
            clone_name = organizer.clone_forge(forge_name)
            organizer.save()
            self._notify_forge_list_changed()
            self.refresh()
            if clone_name:
                QMessageBox.information(
                    self, "DataForge Cloned",
                    f"Created \"{clone_name}\" — Sources and Snapshots "
                    f"included, ready to run.")
        elif chosen == delete_forge:
            self._delete_dataforge(forge_name)
        elif self._handle_creation_action(chosen, new_query, new_forge):
            return

    def _query_context_menu(self, payload: dict, global_pos):
        obj = query_object_store.load_object_by_id(payload["id"])
        if obj is None:
            return
        organizer = get_query_organizer()

        menu = QMenu(self)
        rename = menu.addAction("Rename")
        copy_here = menu.addAction("Copy")
        delete = menu.addAction("Delete")
        menu.addSeparator()
        new_query, new_forge = self._add_creation_actions(menu)

        chosen = menu.exec(global_pos)
        if self._handle_creation_action(chosen, new_query, new_forge):
            return
        if chosen is None:
            return
        if chosen == rename:
            self._rename_query_object(obj)
        elif chosen == copy_here:
            organizer.copy_query(obj.id, organizer.query_location(obj.id))
            organizer.save()
            self.refresh()
        elif chosen == delete:
            self._delete_query_object(obj)

    def _rename_query_object(self, obj: QueryObject) -> None:
        new_name, ok = QInputDialog.getText(
            self, "Rename Query Object", "Object name:", text=obj.name)
        if not ok or not new_name.strip() or new_name.strip() == obj.name:
            return
        if obj.kind == OBJECT_KIND_VISUAL and query_object_store.object_exists(new_name.strip()):
            QMessageBox.warning(
                self,
                "Name Already Exists",
                f"A visual Query Object named \"{new_name.strip()}\" already exists.",
            )
            return
        obj.name = new_name.strip()
        obj.updated_at = datetime.now()
        query_object_store.save_object(obj)
        self.refresh()

    def _delete_query_object(self, obj: QueryObject) -> None:
        reply = QMessageBox.question(
            self,
            "Delete Query Object",
            f"Delete query object \"{obj.name}\"?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return
        query_object_store.delete_object_by_id(obj.id)
        organizer = get_query_organizer()
        organizer.remove_query(obj.id)
        organizer.save()
        self.refresh()
        if self._current is not None and self._current.id == obj.id:
            self._clear_detail()

    def _forge_query_context_menu(self, payload: dict, global_pos):
        """Context menu for a Source copy inside a DataForge node."""
        forge_name = payload["forge"]
        obj = query_object_store.load_object_by_id(payload["id"])
        if obj is None:
            return
        menu = QMenu(self)
        rename = menu.addAction("Rename Source...")
        open_forge = menu.addAction("Open DataForge in Builder")
        menu.addSeparator()
        copy_out = menu.addAction("Copy out to Browser")
        move_out = menu.addAction("Move out to Browser")
        menu.addSeparator()
        remove = menu.addAction("Remove from DataForge")
        menu.addSeparator()
        new_query, new_forge = self._add_creation_actions(menu)

        chosen = menu.exec(global_pos)
        organizer = get_query_organizer()
        if self._handle_creation_action(chosen, new_query, new_forge):
            return
        if chosen == rename:
            self._rename_forge_query_object(forge_name, obj)
        elif chosen == open_forge:
            self._open_dataforge_builder(forge_name)
        elif chosen in (copy_out, move_out):
            out = organizer.extract_query_from_forge(
                forge_name, obj.name, remove_source=(chosen == move_out))
            if out is None:
                QMessageBox.warning(
                    self, "Extract Failed",
                    f"Could not find Source \"{obj.name}\" in "
                    f"\"{forge_name}\".")
                return
            if chosen == move_out:
                self._delete_forge_source_records(forge_name, obj)
            organizer.save()
            self.refresh()
        elif chosen == remove:
            reply = QMessageBox.question(
                self, "Remove from DataForge",
                f"Remove Source \"{obj.name}\" from \"{forge_name}\"?\n\n"
                "Its Snapshot and Forge-local copy are deleted.",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No)
            if reply == QMessageBox.StandardButton.Yes:
                self._remove_source_from_forge(forge_name, obj)
                self.refresh()

    def _rename_forge_query_object(self, forge_name: str, obj: QueryObject) -> None:
        new_name, ok = QInputDialog.getText(
            self, "Rename DataForge Source", "Source name:", text=obj.name)
        new_name = new_name.strip()
        if not ok or not new_name or new_name == obj.name:
            return
        try:
            self._rename_forge_source_records(forge_name, obj, new_name)
        except ValueError as exc:
            QMessageBox.warning(self, "Rename Source Failed", str(exc))
            return
        self._notify_forge_list_changed()
        self.refresh()

    @staticmethod
    def _rename_forge_source_records(
            forge_name: str, obj: QueryObject, new_name: str) -> QueryObject:
        """Rename a Forge-local Source copy across the persisted stores."""
        new_name = new_name.strip()
        old_name = obj.name
        if not new_name:
            raise ValueError("Source name cannot be blank.")
        if new_name == old_name:
            return obj

        from suiteview.audit import qdef_store
        from suiteview.audit.dataforge import dataforge_store

        forge = dataforge_store.load_forge(forge_name)
        if forge is None:
            raise ValueError(f"DataForge \"{forge_name}\" was not found.")

        source = None
        for candidate in forge.sources:
            definition = candidate.definition or {}
            if (candidate.query_name == old_name
                    or candidate.effective_alias() == old_name
                    or definition.get("id") == obj.id):
                source = candidate
                break
        if source is None:
            raise ValueError(
                f"Source \"{old_name}\" was not found in \"{forge_name}\".")

        old_alias = source.effective_alias()
        new_alias = new_name if not source.alias or source.alias == old_name else source.alias
        for candidate in forge.sources:
            if candidate is source:
                continue
            if candidate.query_name == new_name or candidate.effective_alias() == new_alias:
                raise ValueError(
                    f"A Source named \"{new_name}\" already exists in \"{forge_name}\".")

        obj.name = new_name
        obj.updated_at = datetime.now()
        obj.config = dict(obj.config or {})
        dataforge_config = obj.config.get("dataforge", {})
        if not isinstance(dataforge_config, dict):
            dataforge_config = {}
        dataforge_config["forge_name"] = forge_name
        dataforge_config.setdefault("source_name", old_name)
        obj.config["dataforge"] = dataforge_config
        query_object_store.save_object(obj)

        QueryObjectViewerWindow._delete_forge_qdef_file_only(forge_name, old_name)
        qd = qdefinition_from_query_object(obj)
        qd.forge_name = forge_name
        qdef_store.save_qdef(qd)

        source.query_name = new_name
        if source.alias == old_name:
            source.alias = new_name
        source.definition = obj.to_dict()

        mapping = {old_name: new_name}
        if old_alias != new_alias:
            mapping[old_alias] = new_alias
            QueryObjectViewerWindow._rename_forge_source_snapshot(
                forge_name, old_alias, new_alias)
        forge.config = QueryObjectViewerWindow._rename_forge_config_sources(
            dict(forge.config or {}), mapping)
        dataforge_store.save_forge(forge)
        return obj

    @staticmethod
    def _delete_forge_qdef_file_only(forge_name: str, qdef_name: str) -> None:
        from suiteview.audit import qdef_store

        safe = qdef_store._safe_filename(qdef_name)
        directory = qdef_store._forge_dir(forge_name)
        for suffix in (".json", ".parquet"):
            path = directory / f"{safe}{suffix}"
            if path.exists():
                path.unlink()

    @staticmethod
    def _rename_forge_source_snapshot(forge_name: str, old_alias: str, new_alias: str) -> None:
        from suiteview.audit.dataforge import dataforge_store

        old_path = dataforge_store.source_snapshot_path(forge_name, old_alias)
        if not old_path.exists():
            return
        new_path = dataforge_store.source_snapshot_path(forge_name, new_alias)
        new_path.parent.mkdir(parents=True, exist_ok=True)
        if new_path.exists():
            raise ValueError(
                f"A Snapshot already exists for Source \"{new_alias}\".")
        old_path.replace(new_path)

    @staticmethod
    def _rename_forge_config_sources(value, mapping: dict[str, str]):
        if isinstance(value, dict):
            return {
                QueryObjectViewerWindow._rename_forge_config_sources(k, mapping):
                QueryObjectViewerWindow._rename_forge_config_sources(v, mapping)
                for k, v in value.items()
            }
        if isinstance(value, list):
            return [QueryObjectViewerWindow._rename_forge_config_sources(v, mapping)
                    for v in value]
        if isinstance(value, str):
            return QueryObjectViewerWindow._replace_forge_source_name(value, mapping)
        return value

    @staticmethod
    def _replace_forge_source_name(value: str, mapping: dict[str, str]) -> str:
        for old_name, new_name in sorted(mapping.items(), key=lambda pair: len(pair[0]), reverse=True):
            if value == old_name:
                return new_name
            if value.startswith(f"{old_name}."):
                return f"{new_name}{value[len(old_name):]}"
        return value

    # ── Organizer actions ─────────────────────────────────────────────

    def _container_targets(self, organizer) -> list[tuple[str, dict]]:
        """(label, target) pairs for the Move to / Copy to submenus."""
        from suiteview.audit.dataforge import dataforge_store

        targets: list[tuple[str, dict]] = [("Top level", {"root": True})]
        for entry in organizer.items:
            if entry.get("type") == "group":
                targets.append((f"Group: {entry['name']}",
                                {"group_id": entry["id"]}))
        for forge in dataforge_store.list_forges():
            targets.append((f"⚙ Forge: {forge.name}", {"forge": forge.name}))
        return targets

    def _send_query_to(self, obj: QueryObject, target: dict, *, move: bool):
        organizer = get_query_organizer()
        if target.get("forge"):
            ok = organizer.send_query_to_forge(obj.id, target["forge"],
                                               move=move)
            if not ok:
                QMessageBox.warning(self, "Add to DataForge Failed",
                                    f"Could not add \"{obj.name}\" to "
                                    f"\"{target['forge']}\".")
                return
            self._notify_forge_list_changed()
        elif move:
            organizer.move_query(obj.id, target.get("group_id"))
        else:
            organizer.copy_query(obj.id, target.get("group_id"))
        organizer.save()
        self.refresh()

    def _add_creation_actions(self, menu: QMenu):
        new_query = menu.addAction("New Query")
        new_forge = menu.addAction("New Forge")
        return new_query, new_forge

    def _handle_creation_action(self, chosen, new_query, new_forge) -> bool:
        if chosen == new_query:
            self._on_new_query()
            return True
        if chosen == new_forge:
            self._on_new_forge()
            return True
        return False

    def _on_new_query(self):
        parent = self._audit_window_for_builder()
        opener = getattr(parent, "_show_new_object_menu", None)
        if opener is None:
            QMessageBox.information(
                self,
                "Builder Unavailable",
                "Could not open the Query builder chooser.",
            )
            return
        opener()

    def _on_new_forge(self):
        self._open_dataforge_builder("")

    def _on_new_group(self):
        name, ok = QInputDialog.getText(self, "New Query Group", "Group name:")
        if not ok or not name.strip():
            return
        organizer = get_query_organizer()
        organizer.create_group(name)
        organizer.save()
        self.refresh()

    def _notify_forge_list_changed(self):
        parent = self._audit_parent or self.parent() or self._find_audit_window()
        refresher = getattr(parent, "_refresh_picker_forge_list", None)
        if callable(refresher):
            refresher()

    def _remove_source_from_forge(self, forge_name: str, obj: QueryObject):
        """Delete one Source (and its Snapshot + Forge-local copy records)."""
        from suiteview.audit.dataforge import dataforge_store

        forge = dataforge_store.load_forge(forge_name)
        if forge is not None:
            source = forge.source_by_alias(obj.name)
            if source is not None:
                forge.sources.remove(source)
                dataforge_store.save_forge(forge)
            dataforge_store.delete_source_snapshot(forge_name, obj.name)
        self._delete_forge_source_records(forge_name, obj)

    @staticmethod
    def _delete_forge_source_records(forge_name: str, obj: QueryObject):
        from suiteview.audit import qdef_store

        try:
            qdef_store.delete_qdef(obj.name, forge_name=forge_name)
        except Exception:
            logger.exception("Failed to delete DataForge QDefinition: %s",
                             obj.name)
        query_object_store.delete_object_by_id(obj.id)

    # ── Drag & drop (from _OrganizerTree) ─────────────────────────────

    def _handle_tree_drop(self, dragged, target, indicator):
        """Apply a tree drag-drop to the organizer, then rebuild."""
        src = _payload(dragged)
        dst = _payload(target)
        if not src or dragged is target:
            return
        on_item = indicator == QAbstractItemView.DropIndicatorPosition.OnItem
        organizer = get_query_organizer()

        if src["type"] == "query" and not src.get("forge"):
            obj = query_object_store.load_object_by_id(src["id"])
            if obj is None:
                return
            if on_item and dst.get("type") == "forge":
                self._drop_query_on_forge(obj, dst["name"])
            elif on_item and dst.get("type") == "group":
                organizer.move_query(obj.id, dst["group_id"])
                organizer.set_group_expanded(dst["group_id"], True)
            elif on_item and dst.get("type") == "query" and dst.get("forge"):
                self._drop_query_on_forge(obj, dst["forge"])
            else:
                group_id, index = self._drop_position(target, indicator)
                organizer.move_query(obj.id, group_id, index)
                if group_id is not None:
                    organizer.set_group_expanded(group_id, True)
            organizer.save()
            self.refresh()
            return

        if src["type"] == "query" and src.get("forge"):
            # Dragging a Source out of a Forge: ask copy vs move.
            obj = query_object_store.load_object_by_id(src["id"])
            if obj is None:
                return
            box = QMessageBox(self)
            box.setWindowTitle("Out of DataForge")
            box.setText(f"Take \"{obj.name}\" out of \"{src['forge']}\"?")
            copy_btn = box.addButton("Copy out", QMessageBox.ButtonRole.AcceptRole)
            move_btn = box.addButton("Move out", QMessageBox.ButtonRole.DestructiveRole)
            box.addButton(QMessageBox.StandardButton.Cancel)
            box.exec()
            if box.clickedButton() not in (copy_btn, move_btn):
                return
            group_id = dst.get("group_id") if dst.get("type") == "group" else None
            out = organizer.extract_query_from_forge(
                src["forge"], obj.name, group_id,
                remove_source=(box.clickedButton() is move_btn))
            if out is not None and box.clickedButton() is move_btn:
                self._delete_forge_source_records(src["forge"], obj)
            if out is not None and group_id is not None:
                organizer.set_group_expanded(group_id, True)
            organizer.save()
            self.refresh()
            return

        if src["type"] in ("group", "forge"):
            # Root-level reordering only.
            entry = (organizer.find_group(src.get("group_id"))
                     if src["type"] == "group"
                     else organizer.forge_ref(src.get("name", "")))
            if entry is None:
                return
            _, index = self._drop_position(target, indicator, root_only=True)
            if src["type"] == "group":
                organizer.set_group_expanded(src.get("group_id"), False)
            else:
                organizer.set_forge_expanded(src.get("name", ""), False)
            organizer.move_root_item(entry, index)
            organizer.save()
            self.refresh()

    def _drop_query_on_forge(self, obj: QueryObject, forge_name: str):
        """A query dropped onto a Forge: ask whether to move or copy it in."""
        box = QMessageBox(self)
        box.setWindowTitle("Add to DataForge")
        box.setText(
            f"Add \"{obj.name}\" to DataForge \"{forge_name}\"?\n\n"
            "It becomes a Forge-local Source copy (Refresh it there to pull "
            "data). Move also removes the standalone query.")
        copy_btn = box.addButton("Copy in", QMessageBox.ButtonRole.AcceptRole)
        move_btn = box.addButton("Move in", QMessageBox.ButtonRole.DestructiveRole)
        box.addButton(QMessageBox.StandardButton.Cancel)
        box.exec()
        if box.clickedButton() not in (copy_btn, move_btn):
            return
        organizer = get_query_organizer()
        organizer.send_query_to_forge(obj.id, forge_name,
                                      move=box.clickedButton() is move_btn)
        organizer.set_forge_expanded(forge_name, True)
        self._notify_forge_list_changed()

    def _drop_position(self, target, indicator,
                       root_only: bool = False) -> tuple[int | None, int | None]:
        """Resolve a drop to (group_id or None=root, index or None=append)."""
        below = indicator == QAbstractItemView.DropIndicatorPosition.BelowItem
        if target is None:
            return None, None
        parent = target.parent()
        if parent is None:
            index = self.tree.indexOfTopLevelItem(target) + (1 if below else 0)
            dst = _payload(target)
            if (not root_only and indicator
                    == QAbstractItemView.DropIndicatorPosition.OnItem
                    and dst.get("type") == "group"):
                return dst["group_id"], None
            return None, index
        if root_only:
            return None, None
        parent_payload = _payload(parent)
        if parent_payload.get("type") == "group":
            index = parent.indexOfChild(target) + (1 if below else 0)
            return parent_payload["group_id"], index
        return None, None

    def _clear_detail(self):
        self._current = None
        self._current_forge_name = ""
        self._current_source_path = ""
        self._set_editor_read_only(False)
        self._configure_object_tables()
        self.lbl_name.setText("Select a QueryObject")
        self.lbl_kind.setText("")
        self.lbl_status.setText("")
        self.edit_name.clear()
        self.edit_origin.clear()
        self.edit_tags.clear()
        self.edit_description.clear()
        self.tbl_sources.setRowCount(0)
        self.tbl_outputs.setRowCount(0)
        self.tbl_inputs.setRowCount(0)
        self.tbl_joins.setRowCount(0)
        self.tbl_fields.setRowCount(0)
        self.txt_sql.clear()
        self.txt_config.clear()
        self.btn_open_builder.setEnabled(False)
        self.btn_preview_file.setEnabled(False)
        self.btn_open_source_folder.setEnabled(False)
        self.btn_open_source_folder.setVisible(False)
        self.btn_promote.setEnabled(False)
        self.btn_promote.setVisible(False)
        self.btn_delete.setEnabled(False)
        self.btn_save.setEnabled(False)
        if hasattr(self, "left_tabs"):
            if self.left_tabs.tabText(self.left_tabs.currentIndex()) == "Data Sources":
                self._update_data_sources_canvas_title()
            else:
                self._update_queried_canvas_title()

    def _show_detail(self, obj: QueryObject):
        self._loading_detail = True
        self._current = obj
        self._current_forge_name = ""
        self._current_source_path = ""
        self._set_editor_read_only(False)
        self._configure_object_tables()
        if hasattr(self, "left_tabs") and self.left_tabs.tabText(self.left_tabs.currentIndex()) == "Data Sources":
            self._set_canvas_title(f"Data Sources: {obj.name}")
        else:
            self._set_canvas_title(f"{_kind_label(obj.kind)}: {obj.name}")
        self.lbl_name.setText(obj.name)
        self.lbl_kind.setText(_kind_label(obj.kind))
        self.lbl_status.setText(f"Status: {obj.metadata_status}    DSN: {_display_dsn_for_object(obj) or '-'}")
        self.btn_delete.setEnabled(True)
        self.btn_save.setEnabled(True)
        self.btn_open_builder.setEnabled(self._can_open_in_builder(obj))
        self.btn_preview_file.setEnabled(self._can_preview_object(obj))
        self.btn_open_source_folder.setEnabled(False)
        self.btn_open_source_folder.setVisible(False)
        self.btn_promote.setEnabled(obj.kind == OBJECT_KIND_ADHOC_SOURCE)
        self.btn_promote.setVisible(obj.kind == OBJECT_KIND_ADHOC_SOURCE)
        self.edit_name.setText(obj.name)
        self.edit_origin.setText("File Source" if obj.kind == OBJECT_KIND_ADHOC_SOURCE else obj.source_design or obj.kind)
        self.edit_tags.setText(", ".join(obj.tags))
        self.edit_description.setText(obj.description)

        self.tbl_sources.setRowCount(len(obj.sources))
        for row, source in enumerate(obj.sources):
            dsn = _file_source_type_label(source.source_type, source.metadata) if obj.kind == OBJECT_KIND_ADHOC_SOURCE else source.dsn
            values = [source.name, source.source_type, dsn, source.status]
            for col, value in enumerate(values):
                self.tbl_sources.setItem(row, col, QTableWidgetItem(str(value)))
        self.tbl_sources.resizeColumnsToContents()
        self.tbl_sources.setColumnWidth(0, max(self.tbl_sources.columnWidth(0), 240))
        self.tbl_sources.setColumnWidth(1, max(self.tbl_sources.columnWidth(1), 80))

        self._populate_role_table(self.tbl_outputs, obj, {"output"})
        self._populate_role_table(self.tbl_inputs, obj, {"input"})
        self._populate_role_table(self.tbl_joins, obj, {"join_key"})

        self.tbl_fields.setRowCount(len(obj.fields))
        for row, field in enumerate(obj.fields):
            values = [field.name, field.data_type, field.role, field.display_name, field.source]
            for col, value in enumerate(values):
                item = QTableWidgetItem(str(value))
                if col == 0:
                    item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
                self.tbl_fields.setItem(row, col, item)
        self.tbl_fields.resizeColumnsToContents()
        self.tbl_fields.setColumnWidth(0, max(self.tbl_fields.columnWidth(0), 180))
        self.tbl_fields.setColumnWidth(1, max(self.tbl_fields.columnWidth(1), 110))

        self.txt_sql.setPlainText(obj.sql or "")
        self.txt_config.setPlainText(json.dumps({
            "config": obj.config,
            "manual_layers": obj.manual_layers,
            "source_design": obj.source_design,
            "created_at": obj.created_at.isoformat(),
            "updated_at": obj.updated_at.isoformat(),
        }, indent=2))
        self._loading_detail = False

    def _show_forge_detail(self, forge_name: str):
        from suiteview.audit.dataforge import dataforge_store

        self._loading_detail = True
        self._current = None
        self._current_forge_name = forge_name
        self._current_source_path = ""
        self._set_editor_read_only(False)
        self._configure_forge_tables()

        forge = dataforge_store.load_forge(forge_name)
        forge_objects = self._query_objects_for_forge(forge_name)
        display_name = _dataforge_display_name(forge_name)

        self._set_canvas_title(f"DataForge: {display_name}")
        self.lbl_name.setText(f"Forge: {display_name}")
        self.lbl_kind.setText("DataForge")
        saved_text = "Saved" if forge is not None else "Query copies only"
        source_count = len(forge.sources) if forge is not None else len(forge_objects)
        self.lbl_status.setText(f"Status: {saved_text}    Sources: {source_count}")
        self.btn_delete.setEnabled(True)
        self.btn_save.setEnabled(False)
        self.btn_open_builder.setEnabled(forge is not None)
        self.btn_preview_file.setEnabled(False)
        self.btn_open_source_folder.setEnabled(False)
        self.btn_open_source_folder.setVisible(False)
        self.btn_promote.setEnabled(False)
        self.btn_promote.setVisible(False)
        self.edit_name.setText(display_name)
        self.edit_origin.setText("DataForge")
        self.edit_tags.clear()
        self.edit_description.setText(
            "Saved DataForge definition and its forge-local query copies." if forge is not None
            else "Forge-local query copies without a saved DataForge definition.")

        source_rows = self._forge_source_rows(forge, forge_objects)
        self._set_table_rows(self.tbl_sources, source_rows)
        self.tbl_sources.setColumnWidth(0, max(self.tbl_sources.columnWidth(0), 180))
        self.tbl_sources.setColumnWidth(1, max(self.tbl_sources.columnWidth(1), 220))

        output_rows, all_field_rows = self._forge_field_rows(forge, forge_objects)
        self._set_table_rows(self.tbl_outputs, output_rows)
        self._set_table_rows(self.tbl_fields, all_field_rows)
        self._set_table_rows(self.tbl_inputs, self._forge_filter_rows(forge))
        self._set_table_rows(self.tbl_joins, self._forge_join_rows(forge))
        self.txt_sql.setPlainText(self._forge_sql_text(forge, forge_objects))
        self.txt_config.setPlainText(json.dumps(
            forge.to_dict() if forge is not None else {
                "name": forge_name,
                "query_objects": [obj.to_dict() for obj in forge_objects],
            },
            indent=2,
        ))
        self._loading_detail = False

    def _show_odbc_source_detail(self, payload: dict) -> None:
        dsn = str(payload.get("dsn", "")).strip()
        objects = self._objects_from_payload(payload)
        self._loading_detail = True
        self._current = None
        self._current_forge_name = ""
        self._current_source_path = ""
        self._set_editor_read_only(True)
        self._configure_data_source_tables()

        self._set_canvas_title(f"Data Sources: {dsn}" if dsn else "Data Sources")
        self.lbl_name.setText(f"ODBC: {dsn}")
        self.lbl_kind.setText("Data Source")
        self.lbl_status.setText(f"Query Objects: {len(objects)}")
        self.btn_delete.setEnabled(False)
        self.btn_save.setEnabled(False)
        self.btn_open_builder.setEnabled(False)
        self.btn_preview_file.setEnabled(False)
        self.btn_open_source_folder.setEnabled(False)
        self.btn_open_source_folder.setVisible(False)
        self.btn_promote.setEnabled(False)
        self.btn_promote.setVisible(False)
        self.edit_name.setText(dsn)
        self.edit_origin.setText("ODBC")
        self.edit_tags.clear()
        self.edit_description.setText("Windows ODBC setup information for this DSN.")

        self._set_table_rows(self.tbl_sources, self._odbc_detail_rows(dsn))
        self._set_table_rows(self.tbl_outputs, self._source_query_rows(objects))
        self._set_table_rows(self.tbl_inputs, self._odbc_source_use_rows(dsn, objects))
        self.tbl_joins.setRowCount(0)
        self._set_table_rows(self.tbl_fields, self._source_field_rows(objects))
        self.txt_sql.setPlainText(self._source_sql_text(objects))
        self.txt_config.setPlainText(json.dumps({
            "type": "odbc",
            "dsn": dsn,
            "query_objects": [obj.id for obj in objects],
        }, indent=2))
        self._loading_detail = False

    def _show_file_source_detail(self, payload: dict) -> None:
        path = str(payload.get("path", "")).strip()
        label = str(payload.get("label", "")).strip() or _filename_from_path(path)
        source_type = str(payload.get("source_type", "")).strip()
        objects = self._objects_from_payload(payload)
        self._loading_detail = True
        self._current = None
        self._current_forge_name = ""
        self._current_source_path = path
        self._set_editor_read_only(True)
        self._configure_data_source_tables()

        self._set_canvas_title(f"Data Sources: {label}" if label else "Data Sources")
        self.lbl_name.setText(f"File: {label}")
        self.lbl_kind.setText("Data Source")
        self.lbl_status.setText(f"Query Objects: {len(objects)}")
        self.btn_delete.setEnabled(False)
        self.btn_save.setEnabled(False)
        self.btn_open_builder.setEnabled(False)
        self.btn_preview_file.setEnabled(False)
        self.btn_open_source_folder.setEnabled(bool(path))
        self.btn_open_source_folder.setVisible(True)
        self.btn_promote.setEnabled(False)
        self.btn_promote.setVisible(False)
        self.edit_name.setText(label)
        self.edit_origin.setText(_file_source_type_label(source_type, payload.get("metadata", {})))
        self.edit_tags.clear()
        self.edit_description.setText(path or "File path was not saved for this source.")

        self._set_table_rows(self.tbl_sources, self._file_detail_rows(payload, objects))
        self._set_table_rows(self.tbl_outputs, self._source_query_rows(objects))
        self._set_table_rows(self.tbl_inputs, self._file_source_use_rows(payload, objects))
        self.tbl_joins.setRowCount(0)
        self._set_table_rows(self.tbl_fields, self._source_field_rows(objects))
        self.txt_sql.setPlainText(self._source_sql_text(objects))
        self.txt_config.setPlainText(json.dumps({
            "type": "file",
            "path": path,
            "source_type": source_type,
            "metadata": payload.get("metadata", {}),
            "query_objects": [obj.id for obj in objects],
        }, indent=2))
        self._loading_detail = False

    def _set_editor_read_only(self, read_only: bool) -> None:
        for edit in (self.edit_name, self.edit_origin, self.edit_tags, self.edit_description):
            edit.setReadOnly(read_only)

    @staticmethod
    def _objects_from_payload(payload: dict) -> list[QueryObject]:
        objects: list[QueryObject] = []
        for object_id in payload.get("object_ids", []) or []:
            obj = query_object_store.load_object_by_id(object_id)
            if obj is not None:
                objects.append(obj)
        return sorted(objects, key=lambda item: item.name.lower())

    @staticmethod
    def _source_query_rows(objects: list[QueryObject]) -> list[list[object]]:
        return [[obj.name, _kind_label(obj.kind), obj.source_design or obj.kind, len(obj.fields)]
                for obj in objects]

    @staticmethod
    def _source_field_rows(objects: list[QueryObject]) -> list[list[object]]:
        rows: list[list[object]] = []
        for obj in objects:
            for field in obj.fields:
                rows.append([obj.name, field.name, field.role, field.data_type, field.source])
        return rows

    @staticmethod
    def _source_sql_text(objects: list[QueryObject]) -> str:
        chunks: list[str] = []
        for obj in objects:
            sql = obj.sql.strip()
            if sql:
                chunks.append(f"-- Query Object: {obj.name}\n{sql}")
        return "\n\n".join(chunks)

    @staticmethod
    def _odbc_detail_rows(dsn: str) -> list[list[object]]:
        try:
            details = get_dsn_details(dsn)
        except Exception as exc:
            details = {"DSN": dsn, "Error": str(exc)}
        details = dict(details or {})
        details.setdefault("DSN", dsn)
        details["Dialect"] = detect_dialect(dsn) if dsn else UNKNOWN

        priority = [
            "DSN", "Scope", "Driver", "Description", "Server", "Database",
            "Host", "Port", "Port Number", "Subsystem", "Dialect", "Error",
        ]
        keys: list[str] = []
        for key in priority:
            if key in details and key not in keys:
                keys.append(key)
        keys.extend(sorted(key for key in details if key not in keys))

        rows: list[list[object]] = []
        for key in keys:
            value = details.get(key, "")
            if value in (None, ""):
                continue
            display_value = "(hidden)" if key.strip().lower() in _SENSITIVE_ODBC_KEYS else value
            rows.append([key, display_value])
        return rows

    @staticmethod
    def _odbc_source_use_rows(dsn: str, objects: list[QueryObject]) -> list[list[object]]:
        rows: list[list[object]] = []
        dsn_key = dsn.lower()
        for obj in objects:
            matched = False
            for source in obj.sources:
                if source.dsn.strip().lower() == dsn_key:
                    rows.append([obj.name, source.name, source.source_type, source.status])
                    matched = True
            if not matched and obj.dsn.strip().lower() == dsn_key:
                rows.append([obj.name, obj.source_design or obj.kind, "object", obj.metadata_status])
        return rows

    @staticmethod
    def _file_detail_rows(payload: dict, objects: list[QueryObject]) -> list[list[object]]:
        path = str(payload.get("path", "")).strip()
        metadata = dict(payload.get("metadata", {}) or {})
        source_type = str(payload.get("source_type", "")).strip()
        rows: list[list[object]] = [
            ["File Name", payload.get("label", "")],
            ["Full Path", path or "(not saved)"],
            ["Folder", str(Path(path).parent) if path else ""],
            ["Source Type", source_type or "File"],
            ["Query Objects", len(objects)],
        ]
        for key in sorted(metadata):
            if key == "path":
                continue
            rows.append([key, metadata[key]])
        return rows

    @staticmethod
    def _file_source_use_rows(payload: dict, objects: list[QueryObject]) -> list[list[object]]:
        target_key = str(payload.get("key", ""))
        rows: list[list[object]] = []
        for obj in objects:
            for source in obj.sources:
                metadata = dict(source.metadata or {})
                path = str(metadata.get("path", "")).strip()
                if _file_source_key(path, source.name or obj.name) == target_key:
                    rows.append([obj.name, source.name, source.source_type, source.status])
        return rows

    @staticmethod
    def _definition_source_label(definition: dict, fallback: str) -> str:
        config = definition.get("config", {}) if isinstance(definition, dict) else {}
        dataforge = config.get("dataforge", {}) if isinstance(config, dict) else {}
        return str(dataforge.get("source_name", "")).strip() or fallback

    def _query_objects_for_forge(self, forge_name: str) -> list[QueryObject]:
        objects = []
        for obj in query_object_store.list_objects():
            info = _dataforge_info(obj)
            if info is not None and info[0] == forge_name:
                objects.append(obj)
        return sorted(objects, key=lambda item: item.name.lower())

    def _forge_source_rows(self, forge, forge_objects: list[QueryObject]) -> list[list[object]]:
        rows: list[list[object]] = []
        seen = set()
        objects_by_name = {obj.name: obj for obj in forge_objects}
        if forge is not None:
            for source in forge.sources:
                definition = source.definition or {}
                copy_name = str(definition.get("name", "")).strip() or source.query_name
                source_label = self._definition_source_label(definition, source.query_name)
                fields = definition.get("fields") or []
                result_columns = definition.get("result_columns") or []
                column_count = len(fields) or len(result_columns)
                snapshot = "Stale" if source.snapshot.stale else source.snapshot.created_at or "Not refreshed"
                dsn_label = _display_dsn_for_definition(definition)
                source_object = objects_by_name.get(copy_name) or objects_by_name.get(source.query_name)
                if source_object is not None and not dsn_label:
                    dsn_label = _display_dsn_for_object(source_object)
                rows.append([
                    source_label,
                    copy_name,
                    _kind_label(str(definition.get("kind", "executable_query"))),
                    dsn_label,
                    column_count,
                    snapshot,
                    source.snapshot.row_count or "",
                ])
                seen.add(copy_name)
        for obj in forge_objects:
            if obj.name in seen:
                continue
            info = _dataforge_info(obj)
            rows.append([
                info[1] if info else obj.name,
                obj.name,
                _kind_label(obj.kind),
                _display_dsn_for_object(obj),
                len(obj.fields),
                "",
                "",
            ])
        return rows

    def _forge_field_rows(self, forge, forge_objects: list[QueryObject]) -> tuple[list[list[object]], list[list[object]]]:
        display_state = (forge.config or {}).get("display_tab", {}) if forge is not None else {}
        selected = set(display_state.get("selected", []))
        display_all = display_state.get("display_all", True)
        output_rows: list[list[object]] = []
        all_rows: list[list[object]] = []

        def add_field(field_name: str, data_type: str, role: str, source: str, display_name: str = ""):
            all_rows.append([field_name, data_type, role, source])
            if display_all or not selected or field_name in selected or f"{source}.{field_name}" in selected:
                if role in {"", "output"}:
                    output_rows.append([field_name, display_name or field_name, source, data_type])

        for obj in forge_objects:
            info = _dataforge_info(obj)
            source_label = info[1] if info else obj.name
            for field in obj.fields:
                add_field(field.name, field.data_type, field.role, source_label, field.display_name)

        if forge is not None and not all_rows:
            for source in forge.sources:
                definition = source.definition or {}
                source_label = self._definition_source_label(definition, source.query_name)
                column_types = definition.get("column_types", {}) or {}
                for field_name in definition.get("result_columns", []) or []:
                    add_field(field_name, column_types.get(field_name, ""), "output", source_label)
        return output_rows, all_rows

    @staticmethod
    def _forge_filter_rows(forge) -> list[list[object]]:
        if forge is None:
            return []
        rows: list[list[object]] = []
        modes = ["contains", "regex", "combo", "list", "range"]
        for tab in (forge.config or {}).get("filter_tabs", []) or []:
            tab_name = tab.get("tab_name", "Filter")
            fields = (tab.get("grid", {}) or {}).get("fields", {}) or {}
            for field_key, state in fields.items():
                mode_idx = int(state.get("mode", 0) or 0)
                mode = modes[mode_idx] if 0 <= mode_idx < len(modes) else str(mode_idx)
                if mode == "range":
                    value = f"{state.get('val', '')} to {state.get('hi', '')}".strip()
                elif mode == "list":
                    value = ", ".join(str(v) for v in state.get("list_selected", []))
                else:
                    value = state.get("val", "")
                rows.append([tab_name, field_key, mode, value])
        return rows

    @staticmethod
    def _forge_join_rows(forge) -> list[list[object]]:
        if forge is None:
            return []
        joins_state = (forge.config or {}).get("joins_tab", {}) or {}
        joins = joins_state.get("joins", []) or []
        rows: list[list[object]] = []
        for join in joins:
            keys = join.get("keys", []) or []
            left_fields = [key.get("left_field", "") for key in keys]
            right_fields = [key.get("right_field", "") for key in keys]
            rows.append([
                join.get("left_source", ""),
                ", ".join(left_fields),
                join.get("right_source", ""),
                ", ".join(right_fields),
                join.get("how", "inner"),
            ])
        for join in (forge.config or {}).get("joins", []) or []:
            rows.append([
                join.get("left_source", ""),
                ", ".join(join.get("left_keys", [])),
                join.get("right_source", ""),
                ", ".join(join.get("right_keys", [])),
                join.get("how", "inner"),
            ])
        return rows

    @staticmethod
    def _forge_sql_text(forge, forge_objects: list[QueryObject]) -> str:
        chunks: list[str] = []
        if forge is not None:
            for source in forge.sources:
                definition = source.definition or {}
                sql = str(definition.get("sql", "")).strip()
                if sql:
                    label = definition.get("name", source.query_name)
                    chunks.append(f"-- Source: {label}\n{sql}")
        for obj in forge_objects:
            if obj.sql.strip() and all(f"-- Source: {obj.name}\n" not in chunk for chunk in chunks):
                chunks.append(f"-- Source: {obj.name}\n{obj.sql.strip()}")
        return "\n\n".join(chunks)

    def _populate_role_table(self, table: QTableWidget, obj: QueryObject, roles: set[str]):
        fields = [field for field in obj.fields if field.role in roles]
        table.setRowCount(len(fields))
        for row, field in enumerate(fields):
            values = [field.name, field.data_type, field.display_name, field.source]
            for col, value in enumerate(values):
                table.setItem(row, col, QTableWidgetItem(str(value)))
        table.resizeColumnsToContents()
        table.setColumnWidth(0, max(table.columnWidth(0), 180))
        table.setColumnWidth(1, max(table.columnWidth(1), 110))

    def _on_open_source_folder(self) -> None:
        path_text = self._current_source_path.strip()
        if not path_text:
            return
        path = Path(path_text)
        folder = path.parent if path.suffix else path
        folder_text = str(folder)
        if self._open_folder_in_suiteview_file_nav(folder_text):
            return
        try:
            import os
            os.startfile(folder_text)
        except Exception as exc:
            QMessageBox.warning(self, "Open Folder Failed", str(exc))

    def _open_folder_in_suiteview_file_nav(self, folder: str) -> bool:
        launcher = self._find_file_nav_launcher()
        if launcher is not None:
            if hasattr(launcher, "_open_file_nav_at"):
                launcher._open_file_nav_at(folder)
                return True
            if hasattr(launcher, "_open_file_nav"):
                launcher._open_file_nav()
                file_nav = getattr(launcher, "file_nav_window", None)
                if file_nav is not None and hasattr(file_nav, "add_new_tab"):
                    file_nav.add_new_tab(path=folder)
                    return True
        existing = self._find_existing_file_nav_window()
        if existing is not None:
            existing.show()
            existing.raise_()
            existing.activateWindow()
            existing.add_new_tab(path=folder)
            return True
        if self._file_nav_window is not None:
            try:
                _ = self._file_nav_window.isVisible()
            except RuntimeError:
                self._file_nav_window = None
        if self._file_nav_window is None:
            try:
                from suiteview.taskbar_launcher.suiteview_taskbar import FileNavWindow
                self._file_nav_window = FileNavWindow(parent_bar=None)
            except Exception:
                logger.exception("Failed to open standalone File Nav")
                return False
        self._file_nav_window.show()
        self._file_nav_window.raise_()
        self._file_nav_window.activateWindow()
        if hasattr(self._file_nav_window, "add_new_tab"):
            self._file_nav_window.add_new_tab(path=folder)
            return True
        return False

    def _find_file_nav_launcher(self):
        current = self._audit_parent
        seen: set[int] = set()
        while current is not None and id(current) not in seen:
            seen.add(id(current))
            if hasattr(current, "_open_file_nav_at") or hasattr(current, "_open_file_nav"):
                return current
            parent_bar = getattr(current, "_parent_bar", None) or getattr(current, "parent_bar", None)
            if parent_bar is not None and id(parent_bar) not in seen:
                current = parent_bar
                continue
            current = current.parent() if hasattr(current, "parent") else None
        for window in QApplication.topLevelWidgets():
            try:
                _ = window.isVisible()
            except RuntimeError:
                continue
            if hasattr(window, "_open_file_nav_at") or hasattr(window, "_open_file_nav"):
                return window
        return None

    def _find_existing_file_nav_window(self):
        for window in QApplication.topLevelWidgets():
            try:
                _ = window.isVisible()
            except RuntimeError:
                continue
            if window is self:
                continue
            if window.__class__.__name__ == "FileNavWindow" and hasattr(window, "add_new_tab"):
                return window
            file_nav = getattr(window, "file_nav_window", None)
            if file_nav is not None and hasattr(file_nav, "add_new_tab"):
                return file_nav
        return None

    def _on_save_changes(self):
        if self._current is None or self._loading_detail:
            return
        old_name = self._current.name
        new_name = self.edit_name.text().strip()
        if not new_name:
            QMessageBox.warning(self, "Name Required", "Object name cannot be blank.")
            return
        # Duplicate names are legal now (ids disambiguate) — except visual
        # queries, whose designer snapshots are still name-keyed.
        if (new_name != old_name
                and self._current.kind == OBJECT_KIND_VISUAL
                and query_object_store.object_exists(new_name)):
            QMessageBox.warning(
                self,
                "Name Already Exists",
                f"A visual Query Object named \"{new_name}\" already exists.",
            )
            return

        updated_fields = []
        for row, field in enumerate(self._current.fields):
            role = self._normalize_role(self._table_text(self.tbl_fields, row, 2))
            if not role:
                QMessageBox.warning(
                    self,
                    "Invalid Field Role",
                    f"Role for \"{field.name}\" must be output, input, or join key.",
                )
                return
            field.data_type = self._table_text(self.tbl_fields, row, 1)
            field.role = role
            field.display_name = self._table_text(self.tbl_fields, row, 3) or field.name
            field.source = self._table_text(self.tbl_fields, row, 4)
            updated_fields.append(field)

        self._current.name = new_name
        self._current.description = self.edit_description.text().strip()
        self._current.tags = [tag.strip() for tag in self.edit_tags.text().split(",") if tag.strip()]
        self._current.source_design = self.edit_origin.text().strip()
        self._current.sql = self.txt_sql.toPlainText().strip()
        self._current.fields = updated_fields
        self._current.updated_at = datetime.now()

        # The id-keyed store moves the file itself on rename; no old-name
        # cleanup is needed (and with duplicate names it would be wrong).
        query_object_store.save_object(self._current)
        self.refresh()
        QMessageBox.information(self, "Query Object Saved", f"Saved \"{new_name}\".")

    def _on_open_builder(self):
        if self._current_forge_name:
            self._open_dataforge_builder(self._current_forge_name)
            return
        if self._current is None:
            return
        self._open_query_object_builder(self._current.name)

    def _open_query_object_builder(self, object_name: str):
        parent = self._audit_window_for_builder()
        opener = getattr(parent, "open_query_object_in_builder", None)
        if opener is None:
            QMessageBox.information(
                self,
                "Builder Unavailable",
                "Could not open the Audit builder for this Query Object.",
            )
            return
        opener(object_name)

    def _open_dataforge_builder(self, forge_name: str):
        parent = self._audit_window_for_builder()
        opener = getattr(parent, "open_dataforge_in_builder", None)
        if opener is None:
            QMessageBox.information(
                self,
                "Builder Unavailable",
                "Could not open the Audit DataForge builder.",
            )
            return
        opener(forge_name)

    def _audit_window_for_builder(self):
        for candidate in (self._audit_parent, self.parent(), self._find_audit_window()):
            if not self._is_audit_window(candidate):
                continue
            if self._show_audit_window(candidate):
                return candidate
        try:
            from suiteview.audit.main import create_audit_window
            window = create_audit_window()
        except Exception:
            logger.exception("Failed to create AuditWindow for QueryObject builder")
            return None
        self._audit_parent = window
        self._audit_builder_windows.append(window)
        window.destroyed.connect(lambda _=None, win=window: self._forget_audit_window(win))
        return window

    @staticmethod
    def _is_audit_window(candidate) -> bool:
        if candidate is None:
            return False
        try:
            return (
                hasattr(candidate, "open_query_object_in_builder")
                or hasattr(candidate, "open_dataforge_in_builder")
            )
        except RuntimeError:
            return False

    def _show_audit_window(self, window) -> bool:
        try:
            if not window.isVisible():
                window.show()
            if window.isMinimized():
                window.showNormal()
            window.raise_()
            window.activateWindow()
            return True
        except RuntimeError:
            if self._audit_parent is window:
                self._audit_parent = None
            return False

    def _forget_audit_window(self, window):
        if window in self._audit_builder_windows:
            self._audit_builder_windows.remove(window)
        if self._audit_parent is window:
            self._audit_parent = None

    @staticmethod
    def _find_audit_window():
        app = QApplication.instance()
        if app is None:
            return None
        for widget in app.topLevelWidgets():
            if hasattr(widget, "open_query_object_in_builder"):
                return widget
        return None

    @staticmethod
    def _table_text(table: QTableWidget, row: int, col: int) -> str:
        item = table.item(row, col)
        return item.text().strip() if item is not None else ""

    @staticmethod
    def _normalize_role(value: str) -> str:
        normalized = value.strip().lower().replace(" ", "_").replace("-", "_")
        aliases = {
            "": "output",
            "output": "output",
            "select": "output",
            "input": "input",
            "where": "input",
            "filter": "input",
            "join": "join_key",
            "join_key": "join_key",
            "joinkey": "join_key",
            "key": "join_key",
        }
        return aliases.get(normalized, "")

    def _on_delete(self):
        if self._current_forge_name:
            self._delete_dataforge(self._current_forge_name)
            return
        if self._current is None:
            return
        name = self._current.name
        reply = QMessageBox.question(
            self,
            "Delete Query Object",
            f"Delete query object \"{name}\"?\n\nThis does not delete the original SavedQuery or QDefinition.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return
        query_object_store.delete_object_by_id(self._current.id)
        organizer = get_query_organizer()
        organizer.remove_query(self._current.id)
        organizer.save()
        self.refresh()
        self._clear_detail()

    def _delete_dataforge(self, forge_name: str):
        from suiteview.audit import qdef_store
        from suiteview.audit.dataforge import dataforge_store

        display_name = _dataforge_display_name(forge_name)
        forge_objects = self._query_objects_for_forge(forge_name)
        reply = QMessageBox.question(
            self,
            "Delete DataForge",
            f"Delete DataForge \"{display_name}\"?\n\n"
            "This deletes the saved forge, snapshots, and its DataForge query copies. "
            "Original query objects remain.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return
        self._delete_dataforge_records(forge_name, forge_objects)
        parent = self._audit_parent or self.parent() or self._find_audit_window()
        handler = getattr(parent, "_on_forge_deleted_from_group", None)
        if callable(handler):
            handler(forge_name)
        refresher = getattr(parent, "_refresh_picker_forge_list", None)
        if callable(refresher):
            refresher()
        self.refresh()
        self._clear_detail()

    @staticmethod
    def _delete_dataforge_records(forge_name: str, forge_objects: list[QueryObject]) -> None:
        from suiteview.audit import qdef_store
        from suiteview.audit.dataforge import dataforge_store

        dataforge_store.delete_forge(forge_name)
        for obj in forge_objects:
            try:
                qdef_store.delete_qdef(obj.name, forge_name=forge_name)
            except Exception:
                logger.exception("Failed to delete DataForge QDefinition: %s", obj.name)
            query_object_store.delete_object_by_id(obj.id)

    def _on_promote(self):
        if self._current is None:
            return
        name = self._current.name
        try:
            promote_adhoc_source(self._current)
            query_object_store.save_object(self._current)
        except Exception as exc:
            logger.exception("Ad hoc source promotion failed: %s", name)
            QMessageBox.warning(
                self,
                "Promotion Failed",
                f"Could not promote this object:\n\n{exc}",
            )
            return
        self.refresh()
        QMessageBox.information(
            self,
            "Object Promoted",
            f"Promoted \"{name}\" to registered metadata.",
        )

    def _on_preview_file(self):
        if self._current is None:
            return
        dlg = FileObjectPreviewDialog(self._current, self)
        dlg.exec()

    @staticmethod
    def _can_open_in_builder(obj: QueryObject) -> bool:
        if (obj.config or {}).get("dataforge") and obj.kind == OBJECT_KIND_EXECUTABLE:
            return True
        return obj.kind in {
            OBJECT_KIND_VISUAL,
            OBJECT_KIND_CYBERLIFE,
            OBJECT_KIND_MANUAL_SQL,
            OBJECT_KIND_ADHOC_SOURCE,
        }

    @staticmethod
    def _can_preview_object(obj: QueryObject) -> bool:
        if obj.kind == OBJECT_KIND_ADHOC_SOURCE:
            return True
        return bool(obj.sql.strip() and obj.dsn.strip())

    def _on_import_file(self):
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Import Ad Hoc Source",
            "",
            "Data Files (*.csv *.xlsx *.xlsm *.xls);;CSV Files (*.csv);;Excel Files (*.xlsx *.xlsm *.xls)",
        )
        if not path:
            return
        default_name = path.rsplit("/", 1)[-1].rsplit("\\", 1)[-1].rsplit(".", 1)[0]
        name, ok = QInputDialog.getText(
            self,
            "Ad Hoc Source Name",
            "Name:",
            text=default_name,
        )
        if not ok or not name.strip():
            return
        try:
            obj = query_object_from_file(path, name=name.strip())
            query_object_store.save_object(obj)
        except Exception as exc:
            logger.exception("Ad hoc source import failed: %s", path)
            QMessageBox.warning(
                self,
                "Import Failed",
                f"Could not import ad hoc source:\n\n{exc}",
            )
            return
        self.refresh()
        QMessageBox.information(
            self,
            "Source Imported",
            f"Imported \"{obj.name}\" with {len(obj.fields)} fields.",
        )


class FileObjectPreviewDialog(QDialog):
    """Small query surface for QueryObjects."""

    def __init__(self, query_object: QueryObject, parent=None):
        super().__init__(parent)
        self._query_object = query_object
        self.setWindowTitle(f"Preview Data - {query_object.name}")
        self.resize(880, 520)
        self._build_ui()
        self._run_preview()

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(6, 6, 6, 6)
        root.setSpacing(6)

        top = QHBoxLayout()
        top.setContentsMargins(0, 0, 0, 0)
        top.setSpacing(6)

        self.edit_columns = QLineEdit(
            ", ".join(field.name for field in self._query_object.fields)
        )
        self.edit_columns.setFont(_FONT)
        self.edit_columns.setPlaceholderText("Columns")
        top.addWidget(QLabel("Columns"))
        top.addWidget(self.edit_columns, 2)

        self.edit_filter = QLineEdit()
        self.edit_filter.setFont(_FONT)
        self.edit_filter.setPlaceholderText("Filter")
        top.addWidget(QLabel("Filter"))
        top.addWidget(self.edit_filter, 2)

        self.edit_limit = QLineEdit("500")
        self.edit_limit.setFont(_FONT)
        self.edit_limit.setFixedWidth(60)
        top.addWidget(QLabel("Rows"))
        top.addWidget(self.edit_limit)

        self.btn_run = QPushButton("Run")
        self.btn_run.setFont(_FONT_BOLD)
        self.btn_run.setFixedSize(70, 26)
        self.btn_run.setStyleSheet(_BTN_STYLE)
        self.btn_run.clicked.connect(self._run_preview)
        top.addWidget(self.btn_run)
        root.addLayout(top)

        self.table = FilterTableView(self)
        root.addWidget(self.table, 1)

        self.lbl_status = QLabel("")
        self.lbl_status.setFont(_FONT_SMALL)
        self.lbl_status.setStyleSheet("color: #555;")
        root.addWidget(self.lbl_status)

    def _run_preview(self):
        columns = [
            column.strip()
            for column in self.edit_columns.text().split(",")
            if column.strip()
        ]
        try:
            limit = int(self.edit_limit.text().strip() or "500")
        except ValueError:
            QMessageBox.warning(self, "Invalid Rows", "Rows must be a number.")
            return
        try:
            if self._query_object.kind == OBJECT_KIND_ADHOC_SOURCE:
                df = query_adhoc_object(
                    self._query_object,
                    columns=columns,
                    filter_expr=self.edit_filter.text(),
                    limit=limit,
                )
            else:
                df = self._query_sql_object(columns=columns, filter_expr=self.edit_filter.text(), limit=limit)
        except Exception as exc:
            QMessageBox.warning(self, "Preview Failed", str(exc))
            return
        self.table.set_dataframe(df, limit_rows=False)
        self.lbl_status.setText(f"{len(df)} rows x {len(df.columns)} columns")

    def _query_sql_object(self, *, columns: list[str], filter_expr: str, limit: int) -> pd.DataFrame:
        sql = self._query_object.sql.strip().rstrip(";")
        dsn = self._query_object.dsn.strip()
        if not sql or not dsn:
            raise ValueError("This object does not have saved SQL and DSN information to preview.")
        preview_sql = _limited_preview_sql(sql, limit, _preview_dialect_for_object(self._query_object))
        result_columns, rows = execute_odbc_query(dsn, preview_sql)
        df = pd.DataFrame([list(row) for row in rows], columns=result_columns)
        if columns:
            available = [column for column in columns if column in df.columns]
            if available:
                df = df[available]
        if filter_expr.strip():
            df = df.query(filter_expr.strip(), engine="python")
        return df