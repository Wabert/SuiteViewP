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

from PyQt6.QtCore import QSize, Qt, QTimer, pyqtSignal
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
    QComboBox,
    QFrame,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QGridLayout,
    QGroupBox,
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
from suiteview.audit.file_source import DATA_TYPES as _FILE_DATA_TYPES
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
from suiteview.polview.ui.widgets import StyledInfoTableGroup
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

# StyledInfoTableGroup ships PolView's identity (its BLUE_* constants resolve to
# green). The Audit tool is Blue/Gold, so re-skin the dashboard panels to match.
_DASHBOARD_GROUP_STYLE = (
    "QGroupBox { font-size: 11px; font-weight: bold; color: #0D3A7A;"
    " border: 2px solid #1E5BA8; border-radius: 8px; margin-top: 3px;"
    " background-color: white; }"
    "QGroupBox::title { subcontrol-origin: margin; subcontrol-position: top left;"
    " padding: 1px 10px; background-color: #1E5BA8; color: #D4A017;"
    " border-radius: 4px; left: 10px; }"
    "QGroupBox QLabel { font-size: 10px; color: #444; border: none;"
    " background: transparent; }"
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
_FILE_SOURCE_FILE_FILTER = (
    "Data Files (*.csv *.txt *.dat *.psv *.tsv *.xlsx *.xlsm *.xls);;"
    "Text Files (*.csv *.txt *.dat *.psv *.tsv);;"
    "Excel Files (*.xlsx *.xlsm *.xls);;All Files (*.*)"
)
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


class _TablePreviewDialog(QDialog):
    """Popup preview of a table's data with adjustable row count and search.

    The embedded :class:`FilterTableView` provides the search bar; the Rows
    input lets the user change how many rows to pull and reload in place.
    """

    reload_requested = pyqtSignal(int)  # requested row count

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Preview")
        self.setStyleSheet("QDialog { background: #F0F0F0; }")
        self.resize(760, 480)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(8, 8, 8, 8)
        lay.setSpacing(6)
        controls = QHBoxLayout()
        controls.setSpacing(6)
        controls.addWidget(QLabel("Rows"))
        self.edit_rows = QLineEdit("100")
        self.edit_rows.setFixedWidth(60)
        self.edit_rows.setStyleSheet(
            "QLineEdit { background: white; border: 1px solid #A0C4E8; padding: 2px 4px; }")
        self.edit_rows.returnPressed.connect(self._emit_reload)
        controls.addWidget(self.edit_rows)
        self.btn_reload = QPushButton("Reload")
        self.btn_reload.setFont(_FONT_BOLD)
        self.btn_reload.setFixedHeight(24)
        self.btn_reload.setStyleSheet(_BTN_STYLE)
        self.btn_reload.clicked.connect(self._emit_reload)
        controls.addWidget(self.btn_reload)
        controls.addStretch(1)
        lay.addLayout(controls)
        self.table = FilterTableView(self)
        pv = self.table.table_view
        pv.setShowGrid(False)
        pv.verticalHeader().setVisible(False)
        pv.verticalHeader().setDefaultSectionSize(16)
        lay.addWidget(self.table, 1)

    def rows_value(self) -> int:
        try:
            rows = int(self.edit_rows.text().strip() or "100")
        except ValueError:
            rows = 100
            self.edit_rows.setText("100")
        return max(1, rows)

    def _emit_reload(self) -> None:
        self.reload_requested.emit(self.rows_value())

    def set_dataframe(self, dataframe) -> None:
        self.table.set_dataframe(dataframe, limit_rows=False)

    def set_title(self, name: str) -> None:
        self.setWindowTitle(f"Preview: {name}")


class _SourceDashboard(QWidget):
    """Detail view AND editor for a Data Source — a source dashboard.

    A data source is a thing you *connect to* (a DSN, an Access file, a File
    Source), so this surfaces its identity, reachability (health), connection
    setup, the tables it exposes, their columns, and which Query Objects use it
    — never query-only tabs (outputs / joins / SQL).

    For **File Sources** this is also the single canonical screen used to add,
    edit, and view: the Setup name/description and the Columns (name + type) are
    editable in place, files can be dropped/added on the Tables tab, and a Save
    button persists the draft. ODBC / Access stay read-only here (they edit via a
    small registration dialog). The window owns all data extraction, the
    ``FileDataSource`` mutation, and persistence; this widget holds only the
    draft and emits intent (``save_requested`` / ``add_files_requested`` / …).
    """

    preview_requested = pyqtSignal(str, int)      # table name, row count
    remove_table_requested = pyqtSignal(str)      # table name
    open_table_folder_requested = pyqtSignal(str) # file path of that table
    save_requested = pyqtSignal()                 # persist the editable draft
    add_files_requested = pyqtSignal(list)        # member file paths to add
    pick_files_requested = pyqtSignal()           # open a file picker to add members
    bulk_columns_requested = pyqtSignal()         # open the multi-line column-spec box

    def __init__(self, parent=None):
        super().__init__(parent)
        self._editable = False     # File Source edit mode (vs read-only ODBC/Access)
        self._loading = False      # suppress dirty marking during programmatic fill
        self._dirty = False
        self._names_editable = True
        self.setStyleSheet("QWidget { background: #F0F0F0; }")
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(6)

        header = QFrame()
        header.setStyleSheet(
            "QFrame { background: #FAFBFD; border: 1px solid #C9D8EA; }"
            "QLabel { border: none; background: transparent; }")
        hlay = QHBoxLayout(header)
        hlay.setContentsMargins(8, 6, 8, 6)
        hlay.setSpacing(8)

        self.lbl_name = QLabel("")
        self.lbl_name.setFont(QFont("Segoe UI", 14, QFont.Weight.Bold))
        self.lbl_name.setStyleSheet("color: #1E5BA8; border: none; background: transparent;")
        hlay.addWidget(self.lbl_name)

        self.lbl_badge = QLabel("")
        self.lbl_badge.setFont(_FONT_SMALL)
        self.lbl_badge.setVisible(False)
        hlay.addWidget(self.lbl_badge)

        self.lbl_health = QLabel("")
        self.lbl_health.setFont(_FONT_SMALL)
        self.lbl_health.setVisible(False)
        hlay.addWidget(self.lbl_health)

        self.lbl_status = QLabel("")
        self.lbl_status.setFont(_FONT_SMALL)
        self.lbl_status.setStyleSheet("color: #6B7280; border: none; background: transparent;")
        hlay.addWidget(self.lbl_status)

        hlay.addStretch(1)

        self.btn_test = self._make_button("Test")
        self.btn_register = self._make_button("Register")
        self.btn_edit = self._make_button("Edit Setup")
        self.btn_edit_format = self._make_button("Edit Format")
        self.btn_edit_format.setToolTip(
            "Re-open the delimiter / fixed-width layout dialog and re-read the columns")
        self.btn_new_query = self._make_button("New Query")
        self.btn_open_folder = self._make_button("Open Folder")
        self.btn_save = self._make_button("Save")
        # Save is dirty-gated; mute it visibly when disabled (the custom stylesheet
        # otherwise suppresses Qt's default disabled greying).
        self.btn_save.setStyleSheet(
            _BTN_STYLE + "QPushButton:disabled { background-color: #A9BBD0;"
            " color: #E8EEF6; border-color: #93A7C0; }")
        self.btn_delete = self._make_button("Delete", danger=True)
        self.btn_save.clicked.connect(self.save_requested.emit)
        for btn in (self.btn_test, self.btn_register, self.btn_edit,
                    self.btn_edit_format, self.btn_new_query, self.btn_open_folder,
                    self.btn_save, self.btn_delete):
            hlay.addWidget(btn)
        root.addWidget(header)

        # ── Overview tab: Setup and Columns side by side ───────────────────
        # Each side is a stack: read-only StyledInfoTableGroup (ODBC/Access) OR
        # an editable widget (File Source). set_editable() picks the page.
        self.grp_setup = StyledInfoTableGroup("Setup", show_info=False)
        self.grp_columns = StyledInfoTableGroup("Columns", show_info=False, filterable=True)
        self.grp_usedby = StyledInfoTableGroup("Used by", show_info=False)
        for grp in (self.grp_setup, self.grp_columns, self.grp_usedby):
            grp.setStyleSheet(_DASHBOARD_GROUP_STYLE)

        self.setup_stack = QStackedWidget()
        self.setup_stack.addWidget(self.grp_setup)          # 0 read-only
        self.setup_stack.addWidget(self._build_setup_editor())  # 1 editable
        self.columns_stack = QStackedWidget()
        self.columns_stack.addWidget(self.grp_columns)      # 0 read-only
        self.columns_stack.addWidget(self._build_columns_editor())  # 1 editable

        overview = QSplitter(Qt.Orientation.Horizontal)
        overview.setChildrenCollapsible(False)
        overview.setHandleWidth(4)
        overview.addWidget(self.setup_stack)
        overview.addWidget(self.columns_stack)
        overview.setSizes([420, 420])

        self._panels = {
            "setup": self.grp_setup,
            "columns": self.grp_columns,
            "usedby": self.grp_usedby,
        }

        # ── Tables tab: table list (top) + a row-count preview (bottom) ──────
        self.tables_list = _FileDropTable(0, 3)
        self.tables_list.setHorizontalHeaderLabels(["Table", "Status", "File"])
        self.tables_list.verticalHeader().setVisible(False)
        self.tables_list.verticalHeader().setDefaultSectionSize(19)
        self.tables_list.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.tables_list.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.tables_list.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.tables_list.setFont(_FONT)
        self.tables_list.horizontalHeader().setStretchLastSection(True)
        self.tables_list.setStyleSheet(
            "QTableWidget { background: white; border: none; gridline-color: #EEF2F7; }"
            "QTableWidget::item { padding: 0px 4px; }"
            "QTableWidget::item:selected { background: #DCEAFB; color: #0D3A7A; }"
            "QHeaderView::section { background: #E8F0FB; font-weight: bold;"
            " font-size: 8pt; border: 1px solid #C0C0C0; padding: 1px 4px; }")
        self.tables_list.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.tables_list.customContextMenuRequested.connect(self._on_tables_context_menu)
        self.tables_list.itemDoubleClicked.connect(lambda *_: self._on_preview_clicked())
        self.tables_list.files_dropped.connect(self.add_files_requested.emit)

        tables_box = QGroupBox("Tables")
        tables_box.setStyleSheet(_DASHBOARD_GROUP_STYLE)
        tb_lay = QVBoxLayout(tables_box)
        tb_lay.setContentsMargins(6, 16, 6, 4)
        tb_lay.setSpacing(2)
        add_row = QHBoxLayout()
        self.btn_add_files = QPushButton("Add File(s)…")
        self.btn_add_files.setFont(_FONT_BOLD)
        self.btn_add_files.setFixedHeight(22)
        self.btn_add_files.setStyleSheet(_BTN_STYLE)
        self.btn_add_files.clicked.connect(self.pick_files_requested.emit)
        add_row.addWidget(self.btn_add_files)
        add_row.addStretch(1)
        self.btn_preview = QPushButton("Preview")
        self.btn_preview.setFont(_FONT_BOLD)
        self.btn_preview.setFixedHeight(22)
        self.btn_preview.setStyleSheet(_BTN_STYLE)
        self.btn_preview.clicked.connect(self._on_preview_clicked)
        add_row.addWidget(self.btn_preview)
        tb_lay.addLayout(add_row)
        tb_lay.addWidget(self.tables_list, 1)
        self.lbl_tables_footnote = QLabel(
            "Right-click a table to copy its path, open its folder, or remove it.")
        self.lbl_tables_footnote.setFont(_FONT_SMALL)
        self.lbl_tables_footnote.setStyleSheet(
            "color: #6B7280; font-style: italic; border: none; background: transparent;")
        tb_lay.addWidget(self.lbl_tables_footnote)

        used_by_page = QWidget()
        ub_lay = QVBoxLayout(used_by_page)
        ub_lay.setContentsMargins(2, 2, 2, 2)
        ub_lay.addWidget(self.grp_usedby)

        self.tabs = QTabWidget()
        self.tabs.setStyleSheet(
            "QTabWidget::pane { border: 1px solid #1E5BA8; background: #F0F0F0; }"
            "QTabBar::tab { background: #E8F0FB; color: #0D3A7A; border: 1px solid #A0C4E8;"
            " border-bottom: none; padding: 3px 12px; font-size: 8pt; }"
            "QTabBar::tab:selected { background: #F0F0F0; color: #1E5BA8; font-weight: bold; }")
        self.tabs.addTab(overview, "Overview")
        self.tabs.addTab(tables_box, "Tables")       # index 1 (toggled per source)
        self.tabs.addTab(used_by_page, "Used by")
        root.addWidget(self.tabs, 1)

        self._tables_rows: list[dict] = []
        self._tables_removable = False
        self._preview_dialog: "_TablePreviewDialog | None" = None
        self._preview_table_name = ""

    # ── Editable (File Source) widgets ──────────────────────────────────

    def _build_setup_editor(self) -> QWidget:
        """Editable Setup pane (File Source): Name + Description + read-only info."""
        box = QGroupBox("Setup")
        box.setStyleSheet(_DASHBOARD_GROUP_STYLE)
        lay = QVBoxLayout(box)
        lay.setContentsMargins(8, 16, 8, 8)
        lay.setSpacing(6)
        form = QFormLayout()
        form.setSpacing(4)
        edit_style = ("QLineEdit { background: white; border: 1px solid #A0C4E8;"
                      " padding: 3px 5px; }")
        self.edit_src_name = QLineEdit()
        self.edit_src_name.setStyleSheet(edit_style)
        self.edit_src_name.textEdited.connect(self._on_edit_changed)
        self.edit_src_desc = QLineEdit()
        self.edit_src_desc.setStyleSheet(edit_style)
        self.edit_src_desc.setPlaceholderText("Optional description")
        self.edit_src_desc.textEdited.connect(self._on_edit_changed)
        form.addRow("Name", self.edit_src_name)
        form.addRow("Description", self.edit_src_desc)
        lay.addLayout(form)
        self.lbl_setup_info = QLabel("")
        self.lbl_setup_info.setWordWrap(True)
        self.lbl_setup_info.setFont(_FONT_SMALL)
        self.lbl_setup_info.setStyleSheet(
            "color: #475569; border: none; background: transparent;")
        lay.addWidget(self.lbl_setup_info)
        lay.addStretch(1)
        return box

    def _build_columns_editor(self) -> QWidget:
        """Editable Columns pane (File Source): name cells + a Type combo per row."""
        box = QGroupBox("Columns")
        box.setStyleSheet(_DASHBOARD_GROUP_STYLE)
        lay = QVBoxLayout(box)
        lay.setContentsMargins(8, 16, 8, 8)
        lay.setSpacing(4)
        hint = QLabel("Edit a column name or pick its Type, then Save.")
        hint.setFont(_FONT_SMALL)
        hint.setStyleSheet(
            "color: #6B7280; font-style: italic; border: none; background: transparent;")
        hint_row = QHBoxLayout()
        hint_row.setContentsMargins(0, 0, 0, 0)
        hint_row.setSpacing(6)
        hint_row.addWidget(hint)
        hint_row.addStretch(1)
        self.btn_bulk_columns = QPushButton("Enter Columns…")
        self.btn_bulk_columns.setFont(_FONT_SMALL)
        self.btn_bulk_columns.setFixedHeight(20)
        self.btn_bulk_columns.setToolTip(
            "Type or paste all columns at once — one name per line, or "
            "name,start,width for a fixed-width layout")
        self.btn_bulk_columns.setStyleSheet(
            "QPushButton { background: #F8FAFC; border: 1px solid #8AAED8;"
            " border-radius: 3px; color: #0D3A7A; padding: 1px 8px; }"
            "QPushButton:hover { background: #E8F0FB; border-color: #1E5BA8; }")
        self.btn_bulk_columns.clicked.connect(self.bulk_columns_requested.emit)
        hint_row.addWidget(self.btn_bulk_columns)
        lay.addLayout(hint_row)
        self.tbl_columns_edit = QTableWidget(0, 2)
        self.tbl_columns_edit.setHorizontalHeaderLabels(["Column", "Type"])
        self.tbl_columns_edit.verticalHeader().setVisible(False)
        self.tbl_columns_edit.verticalHeader().setDefaultSectionSize(20)
        self.tbl_columns_edit.setSelectionMode(
            QAbstractItemView.SelectionMode.SingleSelection)
        self.tbl_columns_edit.setEditTriggers(
            QAbstractItemView.EditTrigger.DoubleClicked
            | QAbstractItemView.EditTrigger.EditKeyPressed
            | QAbstractItemView.EditTrigger.AnyKeyPressed)
        self.tbl_columns_edit.setFont(_FONT)
        self.tbl_columns_edit.setStyleSheet(
            "QTableWidget { background: white; border: none; gridline-color: #EEF2F7; }"
            "QTableWidget::item:selected { background: #DCEAFB; color: #0D3A7A; }"
            "QHeaderView::section { background: #E8F0FB; font-weight: bold;"
            " font-size: 8pt; border: 1px solid #C0C0C0; padding: 1px 4px; }")
        hdr = self.tbl_columns_edit.horizontalHeader()
        hdr.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        hdr.setSectionResizeMode(1, QHeaderView.ResizeMode.Fixed)
        self.tbl_columns_edit.setColumnWidth(1, 110)
        self.tbl_columns_edit.itemChanged.connect(self._on_edit_changed)
        lay.addWidget(self.tbl_columns_edit, 1)
        return box

    def set_editable(self, editable: bool) -> None:
        """Switch Setup/Columns between read-only (ODBC/Access) and editable."""
        self._editable = editable
        page = 1 if editable else 0
        self.setup_stack.setCurrentIndex(page)
        self.columns_stack.setCurrentIndex(page)
        self.tables_list.setAcceptDrops(editable)
        self.tables_list.viewport().setAcceptDrops(editable)
        self.tables_list.setDragDropMode(
            QAbstractItemView.DragDropMode.DropOnly if editable
            else QAbstractItemView.DragDropMode.NoDragDrop)
        self.btn_add_files.setVisible(editable)
        self.lbl_tables_footnote.setText(
            "Drag files here to add, or use Add File(s)…. Right-click a table to "
            "copy its path, open its folder, or remove it." if editable
            else "Right-click a table to copy its path, open its folder, or remove it.")

    def set_editable_setup(self, name: str, description: str, info: str) -> None:
        self._loading = True
        self.edit_src_name.setText(name or "")
        self.edit_src_desc.setText(description or "")
        self.lbl_setup_info.setText(info or "")
        self._loading = False

    def set_editable_columns(self, columns: list[tuple], *,
                             names_editable: bool = True) -> None:
        """Fill the editable columns table. ``columns`` = (name, data_type)."""
        self._loading = True
        self._names_editable = names_editable
        tbl = self.tbl_columns_edit
        tbl.setRowCount(0)
        tbl.setRowCount(len(columns))
        for row, (name, data_type) in enumerate(columns):
            item = QTableWidgetItem(str(name))
            if not names_editable:
                item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            tbl.setItem(row, 0, item)
            combo = QComboBox()
            combo.addItems(list(_FILE_DATA_TYPES))
            dt = (data_type or "TEXT").upper()
            if dt not in _FILE_DATA_TYPES:
                combo.addItem(dt)
            combo.setCurrentText(dt)
            combo.currentTextChanged.connect(self._on_edit_changed)
            tbl.setCellWidget(row, 1, combo)
        self._loading = False

    def editable_name(self) -> str:
        return self.edit_src_name.text().strip()

    def editable_description(self) -> str:
        return self.edit_src_desc.text().strip()

    def editable_columns(self) -> list[tuple]:
        """Read the draft columns back as (name, data_type) tuples."""
        out: list[tuple] = []
        tbl = self.tbl_columns_edit
        for row in range(tbl.rowCount()):
            item = tbl.item(row, 0)
            combo = tbl.cellWidget(row, 1)
            name = item.text().strip() if item else ""
            data_type = combo.currentText() if combo else "TEXT"
            out.append((name, data_type))
        return out

    @property
    def names_editable(self) -> bool:
        return self._names_editable

    def _on_edit_changed(self, *_args) -> None:
        if not self._loading:
            self.set_dirty(True)

    def set_dirty(self, dirty: bool) -> None:
        self._dirty = bool(dirty)
        if self._editable:
            self.btn_save.setEnabled(self._dirty)
            self.lbl_status.setText("Unsaved changes" if self._dirty else "")

    def is_dirty(self) -> bool:
        return self._editable and self._dirty

    @staticmethod
    def _make_button(text: str, *, danger: bool = False) -> QPushButton:
        btn = QPushButton(text)
        btn.setFont(_FONT_BOLD)
        btn.setFixedHeight(26)
        btn.setStyleSheet(_BTN_DANGER_STYLE if danger else _BTN_STYLE)
        return btn

    def set_title(self, text: str) -> None:
        self.lbl_name.setText(text or "")

    def set_badge(self, text: str, color: str) -> None:
        if not text:
            self.lbl_badge.setVisible(False)
            return
        self.lbl_badge.setText(text)
        self.lbl_badge.setStyleSheet(
            f"color: white; background: {color or '#475569'};"
            " border-radius: 8px; padding: 1px 9px;")
        self.lbl_badge.setVisible(True)

    def set_health(self, text: str, state: str | None) -> None:
        if not text or state is None:
            self.lbl_health.setVisible(False)
            return
        bg, fg, border = _HEALTH_PILL_COLORS.get(state, _HEALTH_PILL_COLORS["neutral"])
        self.lbl_health.setText(text)
        self.lbl_health.setStyleSheet(
            f"color: {fg}; background: {bg}; border: 1px solid {border};"
            " border-radius: 8px; padding: 1px 9px;")
        self.lbl_health.setVisible(True)

    def set_actions(self, *, test: bool, edit: bool, new_query: bool,
                    open_folder: bool, delete: bool, register: bool = False,
                    save: bool = False, edit_format: bool = False) -> None:
        self.btn_test.setVisible(test)
        self.btn_register.setVisible(register)
        self.btn_edit.setVisible(edit)
        self.btn_edit_format.setVisible(edit_format)
        self.btn_new_query.setVisible(new_query)
        self.btn_open_folder.setVisible(open_folder)
        self.btn_save.setVisible(save)
        self.btn_delete.setVisible(delete)

    def set_test_button(self, label: str, tooltip: str) -> None:
        """The top 'Test' action means different things per source type — name it."""
        self.btn_test.setText(label)
        self.btn_test.setToolTip(tooltip)

    def set_panel(self, key: str, columns: list[str], rows: list[list[object]],
                  visible: bool = True) -> None:
        grp = self._panels[key]
        if not visible:
            grp.setVisible(False)
            return
        grp.setVisible(True)
        grp.load_data(columns, [tuple(row) for row in rows])

    # ── Tables tab ────────────────────────────────────────────────────

    def set_tables(self, rows: list[tuple], *, removable: bool) -> None:
        """Fill the Tables list. ``rows`` = (table, status, path); ``removable``
        gates the right-click Remove (File Source members can be removed)."""
        self._tables_rows = [
            {"name": str(r[0]), "status": str(r[1]) if len(r) > 1 else "",
             "path": str(r[2]) if len(r) > 2 else ""}
            for r in rows
        ]
        self._tables_removable = removable
        self.tables_list.setRowCount(len(self._tables_rows))
        for row, info in enumerate(self._tables_rows):
            for col, value in enumerate((info["name"], info["status"], info["path"])):
                self.tables_list.setItem(row, col, QTableWidgetItem(value))
        self.tables_list.resizeColumnToContents(0)
        self.tables_list.resizeColumnToContents(1)
        if self._tables_rows:
            self.tables_list.selectRow(0)  # a default target for the Preview button
        self.clear_preview()

    def set_tables_tab_visible(self, visible: bool) -> None:
        self.tabs.setTabVisible(1, visible)
        if not visible and self.tabs.currentIndex() == 1:
            self.tabs.setCurrentIndex(0)

    def _ensure_preview_dialog(self) -> "_TablePreviewDialog":
        if self._preview_dialog is None:
            self._preview_dialog = _TablePreviewDialog(self)
            self._preview_dialog.reload_requested.connect(self._on_preview_reload)
        return self._preview_dialog

    def set_preview(self, dataframe) -> None:
        self._ensure_preview_dialog().set_dataframe(dataframe)

    def clear_preview(self) -> None:
        if self._preview_dialog is not None:
            import pandas as pd
            self._preview_dialog.set_dataframe(pd.DataFrame())

    def _selected_table(self) -> dict | None:
        rows = self.tables_list.selectionModel().selectedRows()
        if not rows:
            return None
        index = rows[0].row()
        return self._tables_rows[index] if 0 <= index < len(self._tables_rows) else None

    def _on_preview_clicked(self) -> None:
        info = self._selected_table()
        if info is None and self._tables_rows:
            self.tables_list.selectRow(0)
            info = self._selected_table()
        if info is None:
            return
        self._preview_table_name = info["name"]
        dlg = self._ensure_preview_dialog()
        dlg.set_title(info["name"])
        rows = dlg.rows_value()
        dlg.show()
        dlg.raise_()
        dlg.activateWindow()
        self.preview_requested.emit(info["name"], rows)

    def _on_preview_reload(self, rows: int) -> None:
        if self._preview_table_name:
            self.preview_requested.emit(self._preview_table_name, max(1, rows))

    def _on_tables_context_menu(self, pos) -> None:
        item = self.tables_list.itemAt(pos)
        if item is None:
            return
        info = self._tables_rows[item.row()] if item.row() < len(self._tables_rows) else None
        if info is None:
            return
        menu = QMenu(self.tables_list)
        copy_path = menu.addAction("Copy path")
        copy_path.setEnabled(bool(info["path"]))
        open_folder = menu.addAction("Open containing folder")
        open_folder.setEnabled(bool(info["path"]))
        remove = menu.addAction("Remove table from source")
        remove.setEnabled(self._tables_removable)
        chosen = menu.exec(self.tables_list.viewport().mapToGlobal(pos))
        if chosen == copy_path and info["path"]:
            QApplication.clipboard().setText(info["path"])
        elif chosen == open_folder and info["path"]:
            self.open_table_folder_requested.emit(info["path"])
        elif chosen == remove:
            self.remove_table_requested.emit(info["name"])

    def show_empty(self, message: str) -> None:
        self.set_editable(False)
        self.set_dirty(False)
        self.lbl_status.setText("")
        self.set_title(message)
        self.set_badge("", "")
        self.set_health("", None)
        self.set_actions(test=False, edit=False, new_query=False,
                         open_folder=False, delete=False, save=False)
        for key in self._panels:
            self.set_panel(key, [], [], visible=False)
        self.set_tables([], removable=False)
        self.set_tables_tab_visible(False)


class _RegisterOdbcDialog(QDialog):
    """Register (or edit) an ODBC DSN as a named, persisted data source.

    You pick from the installed Windows DSNs or type a name, give it a friendly
    label + notes, and can Test the connection before saving. Produces a
    ``RegisteredDataSource`` on ``result_source`` when accepted.
    """

    def __init__(self, parent=None, *, dsn: str = "", existing=None):
        super().__init__(parent)
        from suiteview.core.odbc_utils import list_installed_dsns

        self._existing = existing
        self.result_source = None
        self.setWindowTitle("Register ODBC Data Source")
        self.setMinimumWidth(440)
        self.setStyleSheet(
            "QDialog { background: #F0F0F0; }"
            "QLabel { color: #0D3A7A; }"
            "QLineEdit, QComboBox { background: white; border: 1px solid #A0C4E8;"
            " padding: 3px 4px; }")

        grid = QGridLayout(self)
        grid.setContentsMargins(12, 12, 12, 12)
        grid.setHorizontalSpacing(8)
        grid.setVerticalSpacing(8)

        grid.addWidget(QLabel("ODBC DSN"), 0, 0)
        self.cmb_dsn = QComboBox()
        self.cmb_dsn.setEditable(True)
        for name, driver in list_installed_dsns():
            self.cmb_dsn.addItem(name)
            self.cmb_dsn.setItemData(self.cmb_dsn.count() - 1, driver, Qt.ItemDataRole.ToolTipRole)
        self.cmb_dsn.setCurrentText(dsn or (existing.dsn if existing else ""))
        grid.addWidget(self.cmb_dsn, 0, 1, 1, 2)

        grid.addWidget(QLabel("Name"), 1, 0)
        self.edit_name = QLineEdit(existing.name if existing else (dsn or ""))
        grid.addWidget(self.edit_name, 1, 1, 1, 2)

        grid.addWidget(QLabel("Notes"), 2, 0)
        self.edit_notes = QLineEdit(existing.notes if existing else "")
        grid.addWidget(self.edit_notes, 2, 1, 1, 2)

        self.lbl_test = QLabel("")
        self.lbl_test.setFont(_FONT_SMALL)
        grid.addWidget(self.lbl_test, 3, 1, 1, 2)

        btn_test = QPushButton("Test Connection")
        btn_test.setStyleSheet(_BTN_STYLE)
        btn_test.clicked.connect(self._on_test)
        grid.addWidget(btn_test, 4, 0)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel)
        buttons.button(QDialogButtonBox.StandardButton.Save).setText(
            "Save" if existing is None else "Update")
        buttons.accepted.connect(self._on_accept)
        buttons.rejected.connect(self.reject)
        grid.addWidget(buttons, 4, 1, 1, 2)

    def _current_dsn(self) -> str:
        return self.cmb_dsn.currentText().strip()

    def _on_test(self) -> None:
        from suiteview.core.odbc_utils import probe_dsn_connection

        dsn = self._current_dsn()
        if not dsn:
            self.lbl_test.setText("Enter a DSN first.")
            self.lbl_test.setStyleSheet("color: #9A7A00;")
            return
        ok, message = probe_dsn_connection(dsn)
        self.lbl_test.setText("✓ Connected" if ok else f"✗ {message[:90]}")
        self.lbl_test.setStyleSheet("color: #1E7E34;" if ok else "color: #B71C1C;")

    def _on_accept(self) -> None:
        from suiteview.audit.data_source import KIND_ODBC, RegisteredDataSource
        from suiteview.core.odbc_utils import detect_dialect

        dsn = self._current_dsn()
        if not dsn:
            QMessageBox.warning(self, "DSN Required", "Pick or type an ODBC DSN.")
            return
        name = self.edit_name.text().strip() or dsn
        notes = self.edit_notes.text().strip()
        if self._existing is not None:
            ds = self._existing
            ds.name, ds.dsn, ds.notes = name, dsn, notes
            ds.dialect = detect_dialect(dsn)
            ds.updated_at = datetime.now()
        else:
            ds = RegisteredDataSource(
                name=name, kind=KIND_ODBC, dsn=dsn,
                dialect=detect_dialect(dsn), notes=notes)
        self.result_source = ds
        self.accept()


class _RegisterAccessDialog(QDialog):
    """Register (or edit) an MS Access file as a named, persisted data source.

    Access connects DSN-less (driver + file path), so you pick a ``.accdb`` /
    ``.mdb`` file, name it, and can Test the connection. Produces a
    ``RegisteredDataSource`` (kind=access) on ``result_source`` when accepted.
    """

    def __init__(self, parent=None, *, path: str = "", existing=None):
        super().__init__(parent)
        self._existing = existing
        self.result_source = None
        self.setWindowTitle("Register MS Access Data Source")
        self.setMinimumWidth(500)
        self.setStyleSheet(
            "QDialog { background: #F0F0F0; }"
            "QLabel { color: #0D3A7A; }"
            "QLineEdit { background: white; border: 1px solid #A0C4E8; padding: 3px 4px; }")

        grid = QGridLayout(self)
        grid.setContentsMargins(12, 12, 12, 12)
        grid.setHorizontalSpacing(8)
        grid.setVerticalSpacing(8)

        grid.addWidget(QLabel("Access file"), 0, 0)
        self.edit_path = QLineEdit(path or (existing.path if existing else ""))
        grid.addWidget(self.edit_path, 0, 1)
        btn_browse = QPushButton("Browse…")
        btn_browse.setStyleSheet(_BTN_STYLE)
        btn_browse.clicked.connect(self._on_browse)
        grid.addWidget(btn_browse, 0, 2)

        grid.addWidget(QLabel("Name"), 1, 0)
        default_name = existing.name if existing else (Path(path).stem if path else "")
        self.edit_name = QLineEdit(default_name)
        grid.addWidget(self.edit_name, 1, 1, 1, 2)

        grid.addWidget(QLabel("Notes"), 2, 0)
        self.edit_notes = QLineEdit(existing.notes if existing else "")
        grid.addWidget(self.edit_notes, 2, 1, 1, 2)

        self.lbl_test = QLabel("")
        self.lbl_test.setFont(_FONT_SMALL)
        grid.addWidget(self.lbl_test, 3, 1, 1, 2)

        btn_test = QPushButton("Test Connection")
        btn_test.setStyleSheet(_BTN_STYLE)
        btn_test.clicked.connect(self._on_test)
        grid.addWidget(btn_test, 4, 0)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel)
        buttons.button(QDialogButtonBox.StandardButton.Save).setText(
            "Save" if existing is None else "Update")
        buttons.accepted.connect(self._on_accept)
        buttons.rejected.connect(self.reject)
        grid.addWidget(buttons, 4, 1, 1, 2)

    def _on_browse(self) -> None:
        start = self.edit_path.text().strip() or str(Path.home())
        file_path, _ = QFileDialog.getOpenFileName(
            self, "Select MS Access database", start,
            "Access Databases (*.accdb *.mdb);;All Files (*.*)")
        if file_path:
            self.edit_path.setText(file_path)
            if not self.edit_name.text().strip():
                self.edit_name.setText(Path(file_path).stem)

    def _on_test(self) -> None:
        from suiteview.core.odbc_utils import probe_access_connection

        ok, message = probe_access_connection(self.edit_path.text().strip())
        self.lbl_test.setText("✓ Connected" if ok else f"✗ {message[:90]}")
        self.lbl_test.setStyleSheet("color: #1E7E34;" if ok else "color: #B71C1C;")

    def _on_accept(self) -> None:
        from suiteview.audit.data_source import KIND_ACCESS, RegisteredDataSource
        from suiteview.core.odbc_utils import ACCESS

        path = self.edit_path.text().strip()
        if not path:
            QMessageBox.warning(self, "File Required", "Pick an MS Access file.")
            return
        name = self.edit_name.text().strip() or Path(path).stem
        notes = self.edit_notes.text().strip()
        if self._existing is not None:
            ds = self._existing
            ds.name, ds.path, ds.notes, ds.dialect = name, path, notes, ACCESS
            ds.updated_at = datetime.now()
        else:
            ds = RegisteredDataSource(
                name=name, kind=KIND_ACCESS, path=path, dialect=ACCESS, notes=notes)
        self.result_source = ds
        self.accept()


class QueryObjectViewerWindow(FramelessWindowBase):
    """Non-blocking QueryObject browser and inspector."""

    _instance = None

    def __init__(self, parent=None):
        self._current: QueryObject | None = None
        self._current_forge_name = ""
        self._current_source_path = ""
        self._current_source_kind = ""
        self._current_source_payload: dict = {}
        self._current_file_source = None
        self._current_data_source = None
        self._loading_detail = False
        self._loading_tree = False
        self._loading_source_tree = False
        self._restoring_left_width = False
        self._left_panel_width = self._load_left_panel_width()
        self._audit_parent = parent
        self._dataforge_builder_windows: list[QDialog] = []
        self._audit_builder_windows: list[QWidget] = []
        self._file_nav_window = None
        self._file_source_is_new = False  # editing an unsaved (new) File Source
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
        self.left_tabs.addTab(self._tables_left_host, "Common Tables")
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

        # A Data Source gets its own dashboard page — never the query detail tabs.
        self._source_dashboard = _SourceDashboard()
        self._browser_canvas_stack.addWidget(self._source_dashboard)
        self._source_dashboard.btn_test.clicked.connect(self._on_source_test)
        self._source_dashboard.btn_register.clicked.connect(self._on_source_register)
        self._source_dashboard.btn_edit.clicked.connect(self._on_source_edit_setup)
        self._source_dashboard.btn_edit_format.clicked.connect(self._on_edit_file_source_format)
        self._source_dashboard.btn_open_folder.clicked.connect(self._on_open_source_folder)
        self._source_dashboard.btn_delete.clicked.connect(self._on_source_delete)
        new_query_menu = QMenu(self._source_dashboard.btn_new_query)
        new_query_menu.addAction("Visual Query").triggered.connect(
            lambda: self._on_source_new_query("visual"))
        new_query_menu.addAction("Manual SQL").triggered.connect(
            lambda: self._on_source_new_query("manual"))
        self._source_dashboard.btn_new_query.setMenu(new_query_menu)
        self._source_dashboard.preview_requested.connect(self._on_dashboard_preview)
        self._source_dashboard.remove_table_requested.connect(self._on_dashboard_remove_table)
        self._source_dashboard.open_table_folder_requested.connect(self._open_path_folder)
        self._source_dashboard.save_requested.connect(self._on_source_save)
        self._source_dashboard.add_files_requested.connect(self._on_add_files_to_source)
        self._source_dashboard.pick_files_requested.connect(self._on_pick_files_for_source)
        self._source_dashboard.bulk_columns_requested.connect(self._on_bulk_edit_columns)

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
        if label == "Common Tables":
            self._ensure_tables_embedded()
            self._browser_canvas_stack.setCurrentWidget(self._tables_canvas_host)
            self._update_common_tables_canvas_title()
            return
        if label == "Registry":
            self._ensure_registry_embedded()
            self._browser_canvas_stack.setCurrentWidget(self._registry_canvas_host)
            self._update_registry_canvas_title()
            return
        if label == "Data Sources":
            self._refresh_source_tree()
            self._route_source_selection(self.source_tree.currentItem())
            self._update_data_sources_canvas_title()
        else:
            self._browser_canvas_stack.setCurrentWidget(self._detail_canvas)
            self._update_queried_canvas_title()

    def _ensure_tables_embedded(self) -> None:
        if self._embedded_common_tables is not None:
            return
        try:
            from suiteview.audit.common_table_dialog import CommonTableDialog
            self._embedded_common_tables = CommonTableDialog(parent=self, embedded=True)
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
        self._select_left_tab("Common Tables")

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

        # Defining a source is a data-source action, not a query build mode — so
        # the entry point lives here. A typed chooser: File Source + ODBC DSN
        # today; MS Access joins it next.
        self.btn_add_source = QPushButton("+ Add Data Source  ▾")
        self.btn_add_source.setFont(_FONT_BOLD)
        self.btn_add_source.setFixedHeight(24)
        self.btn_add_source.setStyleSheet(_BTN_STYLE)
        self.btn_add_source.setToolTip("Register a new data source to query against")
        add_menu = QMenu(self.btn_add_source)
        add_menu.addAction("File Source…").triggered.connect(self._on_add_file_source)
        add_menu.addAction("ODBC DSN…").triggered.connect(self._on_add_odbc_source)
        add_menu.addAction("MS Access…").triggered.connect(self._on_add_access_source)
        self.btn_add_source.setMenu(add_menu)
        panel_lay.addWidget(self.btn_add_source)

        self.source_tree = QTreeWidget()
        self.source_tree.setHeaderHidden(True)
        self.source_tree.setDragEnabled(False)
        self.source_tree.setAcceptDrops(False)
        self.source_tree.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.source_tree.setRootIsDecorated(True)
        self.source_tree.setIndentation(12)
        self.source_tree.setUniformRowHeights(False)
        self.source_tree.setItemDelegate(_CompactSourceDelegate(self.source_tree))
        self.source_tree.setFont(_FONT)
        self.source_tree.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.source_tree.setStyleSheet(
            "QTreeWidget { border: 1px solid #C9D8EA; border-radius: 3px;"
            " background: white; outline: 0; }"
            "QTreeWidget::item { padding: 0px 4px; border: none; }"
            "QTreeWidget::item:hover { background: #F2F7FD; }"
            "QTreeWidget::item:selected { background: #DCEAFB; color: #0D3A7A; }"
        )
        self.source_tree.itemClicked.connect(self._on_source_tree_clicked)
        self.source_tree.currentItemChanged.connect(self._on_source_tree_selection)
        self.source_tree.itemDoubleClicked.connect(self._on_source_tree_double_clicked)
        self.source_tree.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.source_tree.customContextMenuRequested.connect(
            self._on_source_tree_context_menu)
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
                "registered_odbc": ("data_source_id",),
                "access_source": ("data_source_id",),
                "file_source": ("key",),
                "file_data_source": ("key",),
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
            item.setForeground(0, QColor("#000000"))
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
            root.setForeground(0, QColor("#000000"))
            root.setBackground(0, QBrush(QColor("#E8F0FB")))
            payload = {"type": "source_group", "group": group_key}
            root.setData(0, Qt.ItemDataRole.UserRole, payload)
            self.source_tree.addTopLevelItem(root)
            _track(root, payload)
            src_color = {"odbc": "#1E5BA8", "access": "#8B5E00",
                         "file_sources": "#4D7C0F"}.get(group_key, "#8B6914")
            src_type = {"odbc": "odbc_source", "access": "access_source",
                        "file_sources": "file_data_source"}.get(group_key, "file_source")
            for source, children in visible_sources:
                label = source.get("label", "")
                node_type = source.get("node_type") or src_type
                registered = bool(source.get("registered"))
                source_item = QTreeWidgetItem([label])
                source_item.setFont(0, _FONT_BOLD)
                source_item.setForeground(0, QColor("#000000"))
                tooltip = source.get("path") or source.get("dsn") or label
                if group_key == "file_sources":
                    tooltip = "Double-click to edit this File Source"
                elif registered:
                    tooltip = f"Registered ODBC source — DSN {source.get('dsn', '')}"
                source_item.setToolTip(0, tooltip)
                source_payload = {
                    "type": node_type,
                    "group": group_key,
                    "key": source.get("key", ""),
                    "dsn": source.get("dsn", ""),
                    "path": source.get("path", ""),
                    "label": label,
                    "registered": registered,
                    "source_type": source.get("source_type", ""),
                    "metadata": source.get("metadata", {}),
                    "file_source_id": source.get("file_source_id", ""),
                    "data_source_id": source.get("data_source_id", ""),
                    "object_ids": [obj.id for obj in source.get("objects", [])],
                }
                source_item.setData(0, Qt.ItemDataRole.UserRole, source_payload)
                root.addChild(source_item)
                _track(source_item, source_payload)
                if group_key == "file_sources":
                    for table_name, member_path in source.get("members", []):
                        member_item = QTreeWidgetItem([_filename_from_path(member_path)])
                        member_item.setFont(0, _FONT)
                        member_item.setForeground(0, QColor("#000000"))
                        member_item.setData(0, Qt.ItemDataRole.UserRole,
                                            {"type": "file_member", "label": table_name,
                                             "path": member_path})
                        source_item.addChild(member_item)
                source_item.setExpanded(search_active or group_key == "file_sources")
            root.setExpanded(True)

        _add_group("odbc", "ODBC", sorted(index["odbc"].values(), key=lambda item: item["label"].lower()))
        _add_group("access", "MS Access", sorted(index["access"].values(), key=lambda item: item["label"].lower()))
        _add_group("file_sources", "File Sources", sorted(index["file_sources"].values(), key=lambda item: item["label"].lower()))

        if selected_item is not None:
            self.source_tree.setCurrentItem(selected_item)
        self._loading_source_tree = False

    def _build_data_source_index(self, objects: list[QueryObject]) -> dict[str, dict[str, dict]]:
        from suiteview.audit import data_source_store, file_source_store
        from suiteview.audit.data_source import (
            KIND_ACCESS, KIND_ODBC, datasource_kind_label)
        from suiteview.audit.file_source import datasource_label

        index: dict[str, dict[str, dict]] = {
            "odbc": {}, "access": {}, "files": {}, "file_sources": {}}

        # Registered ODBC / Access sources are pinned — they show whether or not
        # a query targets them yet (the whole point of "Add Data Source").
        for ds in data_source_store.list_data_sources():
            if ds.kind == KIND_ODBC and ds.dsn.strip():
                index["odbc"][ds.dsn.strip().lower()] = {
                    "group": "odbc",
                    "key": ds.dsn.strip().lower(),
                    "label": f"{ds.name}  [{datasource_kind_label(ds)}]",
                    "dsn": ds.dsn.strip(),
                    "node_type": "registered_odbc",
                    "registered": True,
                    "data_source_id": ds.id,
                    "objects": [],
                }
            elif ds.kind == KIND_ACCESS and ds.path.strip():
                index["access"][ds.id] = {
                    "group": "access",
                    "key": ds.id,
                    "label": f"{ds.name}  [{datasource_kind_label(ds)}]",
                    "path": ds.path,
                    "node_type": "access_source",
                    "registered": True,
                    "data_source_id": ds.id,
                    "objects": [],
                }

        # Saved File Sources are their own store entity (peer of a DSN) — show
        # them whether or not a query targets them yet.
        for fds in file_source_store.list_file_sources():
            index["file_sources"][fds.id] = {
                "group": "file_sources",
                "key": fds.id,
                "label": f"{fds.name}  [{datasource_label(fds)}]",
                "file_source_id": fds.id,
                "members": [(m.resolved_table_name(), m.path) for m in fds.members],
                "objects": [],
            }

        for obj in objects:
            fs_id = self._file_source_id_for_object(obj)
            if fs_id and fs_id in index["file_sources"]:
                # A query that targets a File Source belongs under it, not ODBC.
                entry = index["file_sources"][fs_id]
                if all(existing.id != obj.id for existing in entry["objects"]):
                    entry["objects"].append(obj)
                continue
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
    def _file_source_id_for_object(obj: QueryObject) -> str:
        """The FileDataSource id a query targets (``file:<id>`` dsn or config)."""
        dsn = (obj.dsn or "").strip()
        if dsn.startswith("file:"):
            return dsn[len("file:"):]
        return str((obj.config or {}).get("file_source_id", "")).strip()

    @staticmethod
    def _odbc_dsns_for_object(obj: QueryObject) -> list[str]:
        if obj.kind == OBJECT_KIND_ADHOC_SOURCE:
            return []
        if (obj.dsn or "").strip().startswith("file:"):
            return []  # file-backed query — listed under File Sources, not ODBC
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
        self._offer_to_save_file_source_edits()
        self._route_source_selection(current)

    def _offer_to_save_file_source_edits(self) -> None:
        """If a File Source has unsaved edits, offer to Save before navigating away.

        Light guard — it never blocks navigation, it just asks whether to persist
        the draft first (Save) or drop it (Discard)."""
        dash = self._source_dashboard
        if self._current_source_kind != "file_data_source" or not dash.is_dirty():
            return
        if self._current_file_source is None or not self._current_file_source.members:
            return
        reply = QMessageBox.question(
            self, "Unsaved File Source",
            f'"{dash.editable_name() or "This File Source"}" has unsaved changes. '
            "Save them before leaving?",
            QMessageBox.StandardButton.Save | QMessageBox.StandardButton.Discard,
            QMessageBox.StandardButton.Save)
        if reply == QMessageBox.StandardButton.Save:
            self._on_source_save()
        dash.set_dirty(False)

    def _route_source_selection(self, current) -> None:
        """Show a source node in the dashboard, a query node in the detail canvas."""
        payload = _payload(current)
        payload_type = payload.get("type")
        if payload_type in {"query", "source_query"}:
            obj = query_object_store.load_object_by_id(payload.get("id", ""))
            if obj is not None:
                self._browser_canvas_stack.setCurrentWidget(self._detail_canvas)
                self._show_detail(obj)
                return
        if payload_type in {"odbc_source", "registered_odbc", "access_source",
                            "file_data_source", "file_source"}:
            self._browser_canvas_stack.setCurrentWidget(self._source_dashboard)
            if payload_type == "registered_odbc":
                self._show_registered_odbc_detail(payload)
            elif payload_type == "access_source":
                self._show_access_source_detail(payload)
            elif payload_type == "odbc_source":
                self._show_odbc_source_detail(payload)
            elif payload_type == "file_data_source":
                self._show_file_data_source_detail(payload)
            else:
                self._show_file_source_detail(payload)
            return
        if payload_type == "file_member" and current is not None and current.parent() is not None:
            self._route_source_selection(current.parent())
            return
        # A group node or empty selection: nothing to inspect.
        self._browser_canvas_stack.setCurrentWidget(self._source_dashboard)
        self._reset_current_source()
        self._source_dashboard.show_empty("Select a data source")
        self._update_data_sources_canvas_title()

    def _reset_current_source(self) -> None:
        self._current_source_kind = ""
        self._current_source_payload = {}
        self._current_file_source = None
        self._current_data_source = None
        self._current_source_path = ""

    def _on_source_tree_double_clicked(self, item: QTreeWidgetItem, column: int) -> None:
        payload = _payload(item)
        if payload.get("type") == "file_data_source":
            # The dashboard already IS the editor — single-click selects + shows it.
            self._route_source_selection(item)
            return
        if payload.get("type") not in {"query", "source_query"}:
            return
        obj = query_object_store.load_object_by_id(payload.get("id", ""))
        if obj is None:
            return
        self._show_detail(obj)
        if self._current is not None and self._can_open_in_builder(self._current):
            self._on_open_builder()

    def _on_source_tree_context_menu(self, pos) -> None:
        """Right-click a File Source node to delete it."""
        item = self.source_tree.itemAt(pos)
        if item is None:
            return
        payload = _payload(item)
        if payload.get("type") != "file_data_source":
            return
        menu = QMenu(self.source_tree)
        delete_action = menu.addAction("Delete File Source")
        chosen = menu.exec(self.source_tree.viewport().mapToGlobal(pos))
        if chosen is delete_action:
            self._delete_file_source_by_payload(payload)

    def _delete_file_source_by_payload(self, payload: dict) -> None:
        """Confirm and delete a File Source identified by a tree payload."""
        from suiteview.audit import file_source_store

        fs_id = str(payload.get("file_source_id") or payload.get("key", "")).strip()
        fds = file_source_store.load_file_source_by_id(fs_id)
        if fds is None:
            return
        objects = self._objects_from_payload(payload)
        extra = (f"\n\n{len(objects)} query object(s) target it and will stop "
                 "resolving.") if objects else ""
        reply = QMessageBox.question(
            self,
            "Delete File Source",
            f'Delete File Source "{fds.name}"?{extra}\n\n'
            "This removes the source definition, not the underlying files.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return
        file_source_store.delete_file_source_by_id(fds.id)
        self.refresh()
        self._reset_current_source()
        self._source_dashboard.show_empty("Select a data source")

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
        query_object_store.rename_object(obj, new_name.strip())
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

        from suiteview.audit import qdef_store, saved_query_store
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
        # Move a visual Source's name-keyed design too (no-op if none).
        saved_query_store.rename_query(old_name, new_name)

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

        qdef_store.delete_qdef_files(qdef_name, forge_name=forge_name)

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

    def _show_odbc_source_detail(self, payload: dict, *, probe: bool = False) -> None:
        """A DSN discovered from queries (not registered). Read-only + Register."""
        dsn = str(payload.get("dsn", "")).strip()
        objects = self._objects_from_payload(payload)
        self._current = None
        self._current_forge_name = ""
        self._current_source_kind = "odbc_source"
        self._current_source_payload = payload
        self._current_file_source = None
        self._current_data_source = None
        self._current_source_path = ""

        dialect = detect_dialect(dsn) if dsn else UNKNOWN
        dash = self._source_dashboard
        dash.set_editable(False)
        dash.set_title(dsn or "ODBC")
        dash.set_badge(dialect if dialect != UNKNOWN else "ODBC", "#1E5BA8")
        dash.set_health(*self._odbc_health(dsn, probe))
        # Discovered DSN: read-only, but offer to Register it (pin + name it).
        dash.set_actions(test=True, register=True, edit=False, new_query=False,
                         open_folder=False, delete=False)
        dash.set_test_button("Test", "Test the ODBC DSN connection")
        dash.set_panel("setup", ["Property", "Value"], self._odbc_detail_rows(dsn))
        dash.set_panel("columns", [], [], visible=False)
        dash.set_tables([], removable=False)
        dash.set_tables_tab_visible(False)
        dash.set_panel("usedby", ["Query Object", "Kind", "Source", "Fields"],
                       self._source_query_rows(objects))
        self._set_canvas_title(f"Data Sources: {dsn}" if dsn else "Data Sources")

    def _show_registered_odbc_detail(self, payload: dict, *, probe: bool = False) -> None:
        from suiteview.audit import data_source_store

        ds = data_source_store.load_data_source_by_id(str(payload.get("data_source_id", "")))
        self._current = None
        self._current_forge_name = ""
        self._current_source_kind = "registered_odbc"
        self._current_source_payload = payload
        self._current_file_source = None
        self._current_data_source = ds
        self._current_source_path = ""
        if ds is None:
            self._reset_current_source()
            self._source_dashboard.show_empty("This data source could not be found.")
            return

        objects = self._objects_from_payload(payload)
        dash = self._source_dashboard
        dash.set_editable(False)
        dash.set_title(ds.name)
        dash.set_badge(ds.dialect or "ODBC", "#1E5BA8")
        dash.set_health(*self._odbc_health(ds.dsn, probe))
        dash.set_actions(test=True, register=False, edit=True, new_query=False,
                         open_folder=False, delete=True)
        dash.set_test_button("Test", "Test the ODBC DSN connection")
        setup = [
            ["Name", ds.name],
            ["DSN", ds.dsn],
            ["Dialect", ds.dialect or "—"],
            ["Notes", ds.notes or "—"],
            ["Registered", ds.created_at.strftime("%Y-%m-%d %H:%M")],
        ]
        # Append the live DSN details, but not the keys we already show above.
        shown = {"dsn", "dialect"}
        setup.extend(row for row in self._odbc_detail_rows(ds.dsn)
                     if str(row[0]).strip().lower() not in shown)
        dash.set_panel("setup", ["Property", "Value"], setup)
        dash.set_panel("columns", [], [], visible=False)
        dash.set_tables([], removable=False)
        dash.set_tables_tab_visible(False)
        dash.set_panel("usedby", ["Query Object", "Kind", "Source", "Fields"],
                       self._source_query_rows(objects))
        self._set_canvas_title(f"Data Sources: {ds.name}")

    def _odbc_health(self, dsn: str, probe: bool) -> tuple[str, str]:
        """Health pill for an ODBC DSN. ``probe`` does a live connection test
        (Test button); otherwise just report whether the DSN is configured."""
        if not dsn:
            return "No DSN", "warn"
        if probe:
            from suiteview.core.odbc_utils import probe_dsn_connection
            ok, message = probe_dsn_connection(dsn)
            return ("Connected", "ok") if ok else (f"Unreachable — {message[:60]}", "bad")
        details = self._safe_dsn_details(dsn)
        if "__error__" in details or "Error" in details:
            return "DSN not found on this machine", "bad"
        return "Configured", "neutral"

    def _show_access_source_detail(self, payload: dict, *, probe: bool = False) -> None:
        from suiteview.audit import data_source_store
        from suiteview.core.odbc_utils import access_driver, list_access_tables

        ds = data_source_store.load_data_source_by_id(str(payload.get("data_source_id", "")))
        self._current = None
        self._current_forge_name = ""
        self._current_source_kind = "access_source"
        self._current_source_payload = payload
        self._current_file_source = None
        self._current_data_source = ds
        if ds is None:
            self._reset_current_source()
            self._source_dashboard.show_empty("This data source could not be found.")
            return

        self._current_source_path = ds.path
        objects = self._objects_from_payload(payload)
        dash = self._source_dashboard
        dash.set_editable(False)
        dash.set_title(ds.name)
        dash.set_badge("MS Access", "#8B5E00")
        dash.set_health(*self._access_health(ds.path, probe))
        dash.set_actions(test=True, register=False, edit=True, new_query=False,
                         open_folder=bool(ds.path), delete=True)
        dash.set_test_button("Test", "Open the Access file to test the connection")
        setup = [
            ["Name", ds.name],
            ["File", ds.path],
            ["Folder", str(Path(ds.path).parent) if ds.path else ""],
            ["Driver", access_driver() or "Access ODBC driver not installed"],
            ["Notes", ds.notes or "—"],
            ["Registered", ds.created_at.strftime("%Y-%m-%d %H:%M")],
        ]
        dash.set_panel("setup", ["Property", "Value"], setup)
        tables = list_access_tables(ds.path)
        # Each Access table lives in the one .accdb file, so they share its path.
        dash.set_tables([(name, "", ds.path) for name in tables], removable=False)
        dash.set_tables_tab_visible(bool(tables))
        dash.set_panel("columns", [], [], visible=False)
        dash.set_panel("usedby", ["Query Object", "Kind", "Source", "Fields"],
                       self._source_query_rows(objects))
        self._set_canvas_title(f"Data Sources: {ds.name}")

    @staticmethod
    def _access_health(path: str, probe: bool) -> tuple[str, str]:
        import os

        if not path:
            return "No file", "warn"
        if not os.path.exists(path):
            return "File not found", "bad"
        if probe:
            from suiteview.core.odbc_utils import probe_access_connection
            ok, message = probe_access_connection(path)
            return ("Connected", "ok") if ok else (f"Unreachable — {message[:60]}", "bad")
        return "File OK", "ok"

    def _show_file_data_source_detail(self, payload: dict) -> None:
        """Render a saved File Source in the editable dashboard (view = edit)."""
        from suiteview.audit import file_source_store

        fs_id = str(payload.get("file_source_id") or payload.get("key", "")).strip()
        fds = file_source_store.load_file_source_by_id(fs_id)
        self._current = None
        self._current_forge_name = ""
        self._current_source_kind = "file_data_source"
        self._current_source_payload = payload
        self._current_file_source = fds
        self._file_source_is_new = False
        if fds is None:
            self._reset_current_source()
            self._source_dashboard.show_empty("This File Source could not be found.")
            return
        self._render_file_source(fds, payload, new=False)

    def _render_file_source(self, fds, payload: dict, *, new: bool) -> None:
        """Fill the editable dashboard for a File Source (``fds=None`` = brand new).

        Drives the single canonical screen: Setup name/description + Columns
        (name/type) editable, member files on the Tables tab, Save in the header.
        ``new`` sources hide query/delete/refresh until first saved.
        """
        from suiteview.audit.file_source import SOURCE_TYPE_EXCEL, datasource_label

        dash = self._source_dashboard
        dash.set_editable(True)
        objects = self._objects_from_payload(payload) if payload else []

        if fds is None:
            self._current_source_path = ""
            dash.set_title("New File Source")
            dash.set_badge("", "")
            dash.set_health("Add a file to set the format", "warn")
            dash.set_actions(test=False, edit=False, new_query=False,
                             open_folder=False, delete=False, save=True)
            dash.set_editable_setup(
                "", "",
                "Add a file (drag it onto the Tables tab, or Add File(s)…) to set "
                "the format and columns. Later files must match.")
            dash.set_editable_columns([])
            dash.set_tables([], removable=False)
            dash.set_tables_tab_visible(True)
            dash.set_panel("usedby", ["Query Object", "Kind", "Fields"], [])
            dash.set_dirty(False)
            dash.btn_save.setEnabled(False)
            dash.tabs.setCurrentIndex(1)  # land on the Tables tab to add a file
            self._set_canvas_title("Data Sources: New File Source")
            return

        self._current_source_path = fds.members[0].path if fds.members else ""
        dash.set_title("New File Source" if new else fds.name)
        dash.set_badge(datasource_label(fds), "#B58900")
        missing = [m for m in fds.members if not Path(m.path).exists()]
        if not fds.members:
            dash.set_health("No files", "warn")
        elif missing:
            dash.set_health(f"{len(missing)} of {len(fds.members)} files missing", "bad")
        else:
            dash.set_health(f"{len(fds.members)} files OK", "ok")
        if new:
            dash.set_actions(test=False, edit=False, new_query=False,
                             open_folder=False, delete=False, save=True,
                             edit_format=True)
        else:
            dash.set_actions(test=False, edit=False, new_query=False,
                             open_folder=False, delete=False, save=True,
                             edit_format=True)
        dash.set_test_button("Refresh", "Re-check that the member files still exist")
        dash.set_editable_setup(
            fds.name, fds.description, self._file_source_info_text(fds))
        dash.set_editable_columns(
            [(c.name, c.data_type) for c in fds.columns],
            names_editable=fds.source_type != SOURCE_TYPE_EXCEL)
        dash.set_tables([
            (m.resolved_table_name(),
             "OK" if Path(m.path).exists() else "missing", m.path)
            for m in fds.members
        ], removable=True)
        dash.set_tables_tab_visible(True)
        dash.set_panel("usedby", ["Query Object", "Kind", "Fields"], [
            [obj.name, _kind_label(obj.kind), len(obj.fields)] for obj in objects
        ])
        dash.set_dirty(bool(new))
        self._set_canvas_title(
            "Data Sources: New File Source" if new else f"Data Sources: {fds.name}")

    def _refresh_file_source_tables(self, fds) -> None:
        """Update only the Tables list + info line (preserves in-progress edits)."""
        dash = self._source_dashboard
        dash.set_tables([
            (m.resolved_table_name(),
             "OK" if Path(m.path).exists() else "missing", m.path)
            for m in fds.members
        ], removable=True)
        dash.set_tables_tab_visible(True)
        dash.lbl_setup_info.setText(self._file_source_info_text(fds))
        missing = [m for m in fds.members if not Path(m.path).exists()]
        if missing:
            dash.set_health(f"{len(missing)} of {len(fds.members)} files missing", "bad")
        elif fds.members:
            dash.set_health(f"{len(fds.members)} files OK", "ok")
        else:
            dash.set_health("No files", "warn")

    def _file_source_info_text(self, fds) -> str:
        from suiteview.audit.file_source import datasource_label

        return "\n".join([
            f"Type: {datasource_label(fds)}",
            f"Format: {self._file_source_format_summary(fds)}",
            f"Member files: {len(fds.members)}    Columns: {len(fds.columns)}",
            f"Updated: {fds.updated_at.strftime('%Y-%m-%d %H:%M')}",
        ])

    @staticmethod
    def _file_source_format_summary(fds) -> str:
        from suiteview.audit.file_source import (
            SOURCE_TYPE_CSV, SOURCE_TYPE_EXCEL, SOURCE_TYPE_FIXED_WIDTH)

        st = fds.source_type
        ps = fds.parse_spec or {}
        if st == SOURCE_TYPE_CSV:
            delim = ps.get("delimiter", ",")
            delim_disp = "\\t (tab)" if delim == "\t" else f"'{delim}'"
            header = "header row" if ps.get("has_header", True) else "no header"
            skip = ps.get("skip_rows", 0)
            extra = f", skip {skip}" if skip else ""
            return f"Delimited — delimiter {delim_disp}, {header}{extra}"
        if st == SOURCE_TYPE_FIXED_WIDTH:
            return f"Fixed width — {len(ps.get('columns', []))} columns"
        if st == SOURCE_TYPE_EXCEL:
            return f"Excel — sheet {ps.get('sheet_name', 0)}"
        return st

    def _show_file_source_detail(self, payload: dict) -> None:
        path = str(payload.get("path", "")).strip()
        label = str(payload.get("label", "")).strip() or _filename_from_path(path)
        source_type = str(payload.get("source_type", "")).strip()
        objects = self._objects_from_payload(payload)
        self._current = None
        self._current_forge_name = ""
        self._current_source_kind = "file_source"
        self._current_source_payload = payload
        self._current_file_source = None
        self._current_source_path = path

        dash = self._source_dashboard
        dash.set_editable(False)
        dash.set_title(label)
        dash.set_badge(_file_source_type_label(source_type, payload.get("metadata", {})), "#8B6914")
        if path and Path(path).exists():
            dash.set_health("File OK", "ok")
        elif path:
            dash.set_health("File missing", "bad")
        else:
            dash.set_health("Path not saved", "warn")
        dash.set_actions(test=True, edit=False, new_query=False,
                         open_folder=bool(path), delete=False)
        dash.set_test_button("Refresh", "Re-check that the file still exists")
        dash.set_panel("setup", ["Property", "Value"],
                       self._file_detail_rows(payload, objects))
        dash.set_panel("columns", [], [], visible=False)
        dash.set_tables([], removable=False)
        dash.set_tables_tab_visible(False)
        dash.set_panel("usedby", ["Query Object", "Kind", "Source", "Fields"],
                       self._source_query_rows(objects))
        self._set_canvas_title(f"Data Sources: {label}" if label else "Data Sources")

    @staticmethod
    def _safe_dsn_details(dsn: str) -> dict:
        if not dsn:
            return {"__error__": "no dsn"}
        try:
            details = dict(get_dsn_details(dsn) or {})
        except Exception as exc:
            return {"__error__": str(exc)}
        return details or {"__error__": "not found"}

    # ── Data Source dashboard actions ─────────────────────────────────

    def _on_source_test(self) -> None:
        """Re-evaluate the selected source's health (re-render its detail).

        ODBC sources do a *live* connection probe here (``probe=True``)."""
        payload = self._current_source_payload
        kind = self._current_source_kind
        if kind == "file_data_source":
            self._show_file_data_source_detail(payload)
        elif kind == "file_source":
            self._show_file_source_detail(payload)
        elif kind == "registered_odbc":
            self._show_registered_odbc_detail(payload, probe=True)
        elif kind == "access_source":
            self._show_access_source_detail(payload, probe=True)
        elif kind == "odbc_source":
            self._show_odbc_source_detail(payload, probe=True)

    def _on_source_register(self) -> None:
        """Promote a discovered DSN to a registered (named, pinned) source."""
        if self._current_source_kind != "odbc_source":
            return
        self._register_odbc_dsn(dsn=str(self._current_source_payload.get("dsn", "")))

    # ── Tables tab: preview / remove / per-file open-folder ────────────

    def _on_dashboard_preview(self, table_name: str, rows: int) -> None:
        """Preview N rows of the selected member table (File Sources only)."""
        if self._current_source_kind != "file_data_source" or self._current_file_source is None:
            return
        member = self._current_file_source.find_member_by_table(table_name)
        if member is None:
            return
        from suiteview.audit import file_query_runner
        try:
            result = file_query_runner.run_sql(
                self._current_file_source, f'SELECT * FROM "{table_name}"',
                limit=rows, table_names=[table_name])
            self._source_dashboard.set_preview(result.dataframe)
        except Exception as exc:
            logger.warning("File Source preview failed for %s: %s", table_name, exc)
            self._source_dashboard.clear_preview()

    def _on_dashboard_remove_table(self, table_name: str) -> None:
        """Remove a member file (table) from a File Source."""
        if self._current_source_kind != "file_data_source" or self._current_file_source is None:
            return
        from suiteview.audit import file_source_store

        fds = self._current_file_source
        member = fds.find_member_by_table(table_name)
        if member is None:
            return
        # A *saved* source must keep at least one file — delete the source instead.
        # A *new* (unsaved) source may drop its last file, reverting to empty.
        if not self._file_source_is_new and len(fds.members) <= 1:
            QMessageBox.information(
                self, "Cannot Remove",
                "A File Source needs at least one file. Delete the whole source instead.")
            return
        reply = QMessageBox.question(
            self,
            "Remove Table",
            f"Remove table \"{table_name}\" ({Path(member.path).name}) from this "
            "File Source?\n\nThis removes the file from the source definition, "
            "not from disk.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return
        fds.members = [m for m in fds.members if m is not member]
        if self._file_source_is_new:
            # Stay in the in-memory draft; never touch the store until Save.
            if not fds.members:
                self._current_file_source = None
                self._render_file_source(None, self._current_source_payload, new=True)
            else:
                self._refresh_file_source_tables(fds)
                self._source_dashboard.set_dirty(True)
            return
        fds.updated_at = datetime.now()
        file_source_store.save_file_source(fds)
        self.refresh()
        self._select_file_source(fds.id)

    # ── File Source editing (the canonical add/edit/view screen) ───────

    def _on_source_save(self) -> None:
        """Persist the editable File Source draft shown in the dashboard."""
        if self._current_source_kind != "file_data_source":
            return
        fds = self._current_file_source
        dash = self._source_dashboard
        if fds is None or not fds.members:
            QMessageBox.information(self, "Add a File First",
                                   "Add at least one file before saving.")
            return
        name = dash.editable_name()
        if not name:
            QMessageBox.information(self, "Name Required",
                                   "Give the File Source a name before saving.")
            return
        from suiteview.audit import file_source_store
        from suiteview.audit.file_source import SOURCE_TYPE_EXCEL
        from suiteview.audit.file_source_intake import apply_column_names

        draft_cols = dash.editable_columns()
        if len(draft_cols) == len(fds.columns):
            names = [c[0].strip() for c in draft_cols]
            if fds.source_type != SOURCE_TYPE_EXCEL and dash.names_editable:
                if any(not n for n in names):
                    QMessageBox.warning(self, "Invalid Column Names",
                                       "Column names cannot be blank.")
                    return
                if len({n.lower() for n in names}) != len(names):
                    QMessageBox.warning(self, "Invalid Column Names",
                                       "Column names must be unique.")
                    return
                try:
                    apply_column_names(fds, names)
                except ValueError as exc:
                    QMessageBox.warning(self, "Invalid Column Names", str(exc))
                    return
            for col, (_, data_type) in zip(fds.columns, draft_cols):
                col.data_type = data_type
        fds.name = name
        fds.description = dash.editable_description()
        fds.updated_at = datetime.now()
        file_source_store.save_file_source(fds)
        self._file_source_is_new = False
        dash.set_dirty(False)
        self.refresh()
        self._select_file_source(fds.id)

    def _on_edit_file_source_format(self) -> None:
        """Re-open the format/layout dialog and re-read the columns.

        Fixes a mis-detected text file (wrong delimiter, or it's really
        fixed-width) and lets fixed-width column definitions be changed after the
        fact. The schema is re-inferred from the first member; the change is
        staged (Save persists it)."""
        if self._current_source_kind != "file_data_source" or self._current_file_source is None:
            return
        fds = self._current_file_source
        if not fds.members:
            QMessageBox.information(self, "Add a File First",
                                   "Add a file before editing its format.")
            return
        from suiteview.audit.file_source_format_dialogs import (
            DialogCancelled, prompt_format_spec_for_source)
        from suiteview.audit.file_source_intake import (
            infer_file_source_from_file, validate_member_file)

        try:
            new_spec = prompt_format_spec_for_source(self, fds)
        except DialogCancelled:
            return
        first = fds.members[0].path
        try:
            fresh = infer_file_source_from_file(first, name=fds.name, format_spec=new_spec)
        except Exception as exc:  # noqa: BLE001 — surface any read error
            QMessageBox.warning(self, "Could Not Apply Format", f"{exc}")
            return
        # Adopt the new format + columns; keep identity, name, description, members.
        fds.source_type = fresh.source_type
        fds.parse_spec = fresh.parse_spec
        fds.columns = fresh.columns
        # Warn if any existing member no longer matches the new format.
        mismatched = []
        for member in fds.members:
            try:
                if validate_member_file(fds, member.path):
                    mismatched.append(Path(member.path).name)
            except Exception:  # noqa: BLE001 — unreadable under the new format
                mismatched.append(Path(member.path).name)
        self._render_file_source(
            fds, self._current_source_payload, new=self._file_source_is_new)
        self._source_dashboard.set_dirty(True)
        self._source_dashboard.tabs.setCurrentIndex(0)  # show the re-read columns
        if mismatched:
            QMessageBox.warning(
                self, "Format Changed",
                "These files no longer match the new format and may fail to "
                "query:\n• " + "\n• ".join(mismatched))

    def _on_bulk_edit_columns(self) -> None:
        """Multi-line column entry: a list of names, or name,start,width rows.

        A names list renames the draft columns in place (Save persists). A
        name,start,width block redefines a fixed-width layout — the format is
        re-applied and the columns re-read, mirroring Edit Format."""
        if (self._current_source_kind != "file_data_source"
                or self._current_file_source is None):
            return
        from suiteview.audit.file_source import SOURCE_TYPE_EXCEL
        from suiteview.audit.file_source_intake import parse_column_spec_text

        fds = self._current_file_source
        if fds.source_type == SOURCE_TYPE_EXCEL:
            QMessageBox.information(
                self, "Excel Columns",
                "Excel columns follow the sheet's header row and can't be "
                "entered here.")
            return
        if not fds.members:
            QMessageBox.information(self, "Add a File First",
                                   "Add a file before entering its columns.")
            return

        prefill = self._column_spec_prefill(fds)
        message = (
            "Enter one column name per line, or name,start,width for a "
            "fixed-width layout.\n\nNames:\n  Policy\n  Company\n\n"
            "Fixed width (name,start,width):\n  Policy,1,10\n  Company,11,2")
        text, ok = QInputDialog.getMultiLineText(
            self, "Enter Columns", message, prefill)
        if not ok:
            return
        try:
            mode, parsed = parse_column_spec_text(text)
        except ValueError as exc:
            QMessageBox.warning(self, "Invalid Columns", str(exc))
            return
        if mode == "fixed_width":
            self._apply_fixed_width_columns(fds, parsed)
        else:
            self._apply_bulk_column_names(fds, parsed)

    @staticmethod
    def _column_spec_prefill(fds) -> str:
        """Current columns as editable text for the multi-line box."""
        from suiteview.audit.file_source import SOURCE_TYPE_FIXED_WIDTH
        if fds.source_type == SOURCE_TYPE_FIXED_WIDTH:
            specs = fds.parse_spec.get("columns", [])
            if specs:
                return "\n".join(
                    f"{s.get('name', '')},{s.get('start', '')},{s.get('width', '')}"
                    for s in specs)
        return "\n".join(c.name for c in fds.columns)

    def _apply_bulk_column_names(self, fds, names: list) -> None:
        """Fill the editable columns table from a pasted name list.

        Count must match the current columns; types are preserved and nothing
        persists until Save."""
        dash = self._source_dashboard
        if not dash.names_editable:
            QMessageBox.information(
                self, "Names Fixed",
                "This source's column names follow its file header and can't be "
                "renamed here.")
            return
        draft = dash.editable_columns()
        if len(names) != len(draft):
            QMessageBox.warning(
                self, "Column Count Mismatch",
                f"The source has {len(draft)} columns but you entered "
                f"{len(names)} names.\n\nEnter exactly {len(draft)} names, or use "
                "name,start,width on every line to redefine a fixed-width layout.")
            return
        dash.set_editable_columns(
            [(name, data_type) for name, (_, data_type) in zip(names, draft)],
            names_editable=True)
        dash.set_dirty(True)
        dash.tabs.setCurrentIndex(0)

    def _apply_fixed_width_columns(self, fds, columns: list) -> None:
        """Re-apply a fixed-width layout from pasted name,start,width rows.

        Reuses the format re-inference path so columns are re-read from the first
        member; the change is staged (Save persists)."""
        from suiteview.audit.adhoc_source_intake import fixed_width_spec
        from suiteview.audit.file_source_intake import (
            infer_file_source_from_file, validate_member_file)

        skip_rows = int(fds.parse_spec.get("skip_rows", 0) or 0)
        spec = fixed_width_spec(columns, skip_rows=skip_rows)
        first = fds.members[0].path
        try:
            fresh = infer_file_source_from_file(first, name=fds.name, format_spec=spec)
        except Exception as exc:  # noqa: BLE001 — surface any read error
            QMessageBox.warning(self, "Could Not Apply Columns", f"{exc}")
            return
        fds.source_type = fresh.source_type
        fds.parse_spec = fresh.parse_spec
        fds.columns = fresh.columns
        mismatched = []
        for member in fds.members:
            try:
                if validate_member_file(fds, member.path):
                    mismatched.append(Path(member.path).name)
            except Exception:  # noqa: BLE001 — unreadable under the new format
                mismatched.append(Path(member.path).name)
        self._render_file_source(
            fds, self._current_source_payload, new=self._file_source_is_new)
        self._source_dashboard.set_dirty(True)
        self._source_dashboard.tabs.setCurrentIndex(0)
        if mismatched:
            QMessageBox.warning(
                self, "Columns Changed",
                "These files no longer match the new layout and may fail to "
                "query:\n• " + "\n• ".join(mismatched))

    def _on_pick_files_for_source(self) -> None:
        """Add File(s)… button — pick member files for the current File Source."""
        if self._current_source_kind != "file_data_source":
            return
        paths, _ = QFileDialog.getOpenFileNames(
            self, "Add File(s) to Source", "", _FILE_SOURCE_FILE_FILTER)
        if paths:
            self._on_add_files_to_source(paths)

    def _on_add_files_to_source(self, paths: list) -> None:
        """Add member files (button or drag-drop). The first file of a new source
        establishes its format; later files are validated against it. Nothing is
        persisted until Save."""
        if self._current_source_kind != "file_data_source":
            return
        from suiteview.audit.file_source_intake import (
            FileValidationError, add_member_file)
        from suiteview.audit.file_source_format_dialogs import (
            DialogCancelled, establish_source_from_first_file)

        fds = self._current_file_source
        established_new = False
        errors: list[str] = []
        added = 0
        for path in paths:
            if fds is None:
                try:
                    fds = establish_source_from_first_file(
                        self, path, self._source_dashboard.editable_name())
                except DialogCancelled:
                    break
                if fds is None:
                    continue  # unreadable file; a warning was already shown
                self._current_file_source = fds
                established_new = True
                added += 1
            else:
                try:
                    add_member_file(fds, path)
                    added += 1
                except FileValidationError as exc:
                    errors.append(f"• {Path(path).name}: {exc}")
        if fds is None:
            return
        if established_new:
            self._render_file_source(
                fds, self._current_source_payload, new=self._file_source_is_new)
            # First file just set the format + columns — show them on Overview.
            self._source_dashboard.tabs.setCurrentIndex(0)
        else:
            self._refresh_file_source_tables(fds)
        if added:
            self._source_dashboard.set_dirty(True)
        if errors:
            QMessageBox.warning(self, "Some files were not added", "\n\n".join(errors))

    def _select_file_source(self, file_source_id: str) -> None:
        """Select the tree node for a File Source so its dashboard re-renders."""
        if not file_source_id or not hasattr(self, "source_tree"):
            return

        def _find(item: QTreeWidgetItem):
            if _payload(item).get("file_source_id") == file_source_id:
                return item
            for index in range(item.childCount()):
                found = _find(item.child(index))
                if found is not None:
                    return found
            return None

        for i in range(self.source_tree.topLevelItemCount()):
            node = _find(self.source_tree.topLevelItem(i))
            if node is not None:
                self.source_tree.setCurrentItem(node)
                return

    def _open_path_folder(self, path: str) -> None:
        """Open the folder containing a specific file (resolves multi-folder sources)."""
        folder = str(Path(path).parent) if path else ""
        if not folder:
            return
        if self._open_folder_in_suiteview_file_nav(folder):
            return
        try:
            import os
            os.startfile(folder)
        except Exception as exc:
            QMessageBox.warning(self, "Open Folder Failed", str(exc))

    def _on_add_odbc_source(self) -> None:
        """Add Data Source → ODBC DSN: register a new ODBC source."""
        self._register_odbc_dsn()

    def _on_add_access_source(self) -> None:
        """Add Data Source → MS Access: register a new Access file source."""
        self._register_access_file()

    def _register_odbc_dsn(self, *, dsn: str = "", existing=None) -> None:
        from suiteview.audit import data_source_store

        dialog = _RegisterOdbcDialog(self, dsn=dsn, existing=existing)
        if dialog.exec() != QDialog.DialogCode.Accepted or dialog.result_source is None:
            return
        data_source_store.save_data_source(dialog.result_source)
        self.refresh()
        self._select_registered_source(dialog.result_source.id)

    def _register_access_file(self, *, path: str = "", existing=None) -> None:
        from suiteview.audit import data_source_store

        dialog = _RegisterAccessDialog(self, path=path, existing=existing)
        if dialog.exec() != QDialog.DialogCode.Accepted or dialog.result_source is None:
            return
        data_source_store.save_data_source(dialog.result_source)
        self.refresh()
        self._select_registered_source(dialog.result_source.id)

    def _select_registered_source(self, data_source_id: str) -> None:
        """After save, select the source's tree node so its dashboard shows."""
        if not hasattr(self, "source_tree"):
            return

        def _find(item: QTreeWidgetItem):
            if _payload(item).get("data_source_id") == data_source_id:
                return item
            for index in range(item.childCount()):
                found = _find(item.child(index))
                if found is not None:
                    return found
            return None

        for i in range(self.source_tree.topLevelItemCount()):
            node = _find(self.source_tree.topLevelItem(i))
            if node is not None:
                self.source_tree.setCurrentItem(node)
                return

    def _on_source_edit_setup(self) -> None:
        # File Sources are edited in place on the dashboard (no "Edit Setup"
        # button is shown for them). ODBC / Access edit via their dialog.
        if self._current_source_kind == "registered_odbc" and self._current_data_source is not None:
            self._register_odbc_dsn(existing=self._current_data_source)
        elif self._current_source_kind == "access_source" and self._current_data_source is not None:
            self._register_access_file(existing=self._current_data_source)

    def _on_source_new_query(self, mode: str) -> None:
        if self._current_source_kind != "file_data_source" or self._current_file_source is None:
            return
        parent = self._audit_window_for_builder()
        opener = getattr(parent, "new_query_on_file_source", None)
        if opener is None:
            QMessageBox.information(
                self, "Builder Unavailable",
                "Could not open a query on this File Source.")
            return
        opener(self._current_file_source.id, mode=mode)

    def _on_source_delete(self) -> None:
        if (self._current_source_kind in {"registered_odbc", "access_source"}
                and self._current_data_source is not None):
            self._delete_registered_source()
            return
        if self._current_source_kind != "file_data_source" or self._current_file_source is None:
            return
        from suiteview.audit import file_source_store

        fds = self._current_file_source
        objects = self._objects_from_payload(self._current_source_payload)
        extra = (f"\n\n{len(objects)} query object(s) target it and will stop "
                 "resolving.") if objects else ""
        reply = QMessageBox.question(
            self,
            "Delete File Source",
            f"Delete File Source \"{fds.name}\"?{extra}\n\n"
            "This removes the source definition, not the underlying files.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return
        file_source_store.delete_file_source_by_id(fds.id)
        self.refresh()
        self._reset_current_source()
        self._source_dashboard.show_empty("Select a data source")

    def _delete_registered_source(self) -> None:
        from suiteview.audit import data_source_store
        from suiteview.audit.data_source import KIND_ACCESS

        ds = self._current_data_source
        if ds.kind == KIND_ACCESS:
            target, underlying = ds.path, "Access file"
        else:
            target, underlying = f"DSN {ds.dsn}", "Windows DSN"
        reply = QMessageBox.question(
            self,
            "Unregister Data Source",
            f"Unregister data source \"{ds.name}\" ({target})?\n\n"
            f"This removes the registration only — the {underlying} and any "
            "queries that use it are untouched.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return
        data_source_store.delete_data_source_by_id(ds.id)
        self.refresh()
        self._reset_current_source()
        self._source_dashboard.show_empty("Select a data source")

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

        self._current.description = self.edit_description.text().strip()
        self._current.tags = [tag.strip() for tag in self.edit_tags.text().split(",") if tag.strip()]
        self._current.source_design = self.edit_origin.text().strip()
        self._current.sql = self.txt_sql.toPlainText().strip()
        self._current.fields = updated_fields
        self._current.updated_at = datetime.now()

        if new_name != old_name:
            # Rename across every store so it sticks (the SavedQuery design and
            # any old-name QDefinition would otherwise resurrect the old name).
            query_object_store.rename_object(self._current, new_name)
        else:
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

    def _on_add_file_source(self):
        """Add a File Source — open the editable dashboard in 'new' mode.

        Same screen used to view/edit; the first file added sets the format."""
        self._offer_to_save_file_source_edits()
        # Clear the tree selection first: that routes the canvas to "empty" via
        # the selection handler, so set our new-source state *after* it.
        self.source_tree.setCurrentItem(None)
        self._current = None
        self._current_forge_name = ""
        self._current_source_kind = "file_data_source"
        self._current_source_payload = {}
        self._current_file_source = None
        self._current_data_source = None
        self._current_source_path = ""
        self._file_source_is_new = True
        self._browser_canvas_stack.setCurrentWidget(self._source_dashboard)
        self._render_file_source(None, {}, new=True)

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