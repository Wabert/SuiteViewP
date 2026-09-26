"""Shared imports, constants, and helpers for QueryObject Viewer."""
from __future__ import annotations

import logging
import re

from PyQt6.QtCore import Qt
from PyQt6.QtGui import (
    QFont,
)

from suiteview.audit.build_mode_styles import (
    GROUP_STYLE,
)
from suiteview.audit.query_object import (
    OBJECT_KIND_ADHOC_SOURCE,
    OBJECT_KIND_CYBERLIFE,
    OBJECT_KIND_EXECUTABLE,
    OBJECT_KIND_MANUAL_SQL,
    OBJECT_KIND_VISUAL,
    QueryObject,
)
from suiteview.core.odbc_utils import (
    ACCESS,
    DB2,
    SQL_SERVER,
    UNKNOWN,
    detect_dialect,
)
from suiteview.ui.widgets.bookmark_widgets import (
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

# StyledInfoTableGroup's inner FixedHeaderTableWidget bakes PolView greens into
# its frame border, header sections and scrollbars (the BLUE_* style constants
# resolve to green). _DASHBOARD_GROUP_STYLE only re-skins the outer QGroupBox,
# so re-skin the inner table widgets to the Audit tool's Blue/Gold here.
_INFO_TABLE_BLUE_STYLE = (
    "QTableWidget { background-color: white; border: none;"
    " gridline-color: transparent; font-size: 11px;"
    " selection-background-color: #DCEAFB; selection-color: #0D3A7A; }"
    "QTableWidget::item { padding: 0px 4px; border: none; }"
    "QTableWidget::item:selected { background-color: #DCEAFB; color: #0D3A7A;"
    " border: none; }"
    "QHeaderView::section { background-color: #E8F0FB; color: #0D3A7A;"
    " padding: 2px 4px; border: none; border-right: 1px solid #E1E5EB;"
    " border-bottom: 1px solid #1E5BA8; font-size: 10px; font-weight: normal;"
    " height: 18px; }"
    "QHeaderView::section:last { border-right: none; }"
    "QScrollBar:vertical { background-color: #E8F0FB; width: 14px; margin: 0px;"
    " border: none; }"
    "QScrollBar::handle:vertical { background-color: #A8C6E8; min-height: 30px;"
    " margin: 2px; }"
    "QScrollBar::handle:vertical:hover { background-color: #2A6BC4; }"
    "QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0px; }"
    "QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical { background: none; }"
    "QScrollBar:horizontal { background-color: #E8F0FB; height: 14px; margin: 0px;"
    " border: none; }"
    "QScrollBar::handle:horizontal { background-color: #A8C6E8; min-width: 30px;"
    " margin: 2px; }"
    "QScrollBar::handle:horizontal:hover { background-color: #2A6BC4; }"
    "QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal { width: 0px; }"
    "QScrollBar::add-page:horizontal, QScrollBar::sub-page:horizontal { background: none; }"
)


def _reskin_info_table_blue(group) -> None:
    """Re-skin a StyledInfoTableGroup's inner table from PolView green to blue."""
    table = getattr(group, "table", None)
    if table is None:
        return
    outer = getattr(table, "_outer_frame", None)
    if outer is not None:
        outer.setStyleSheet(
            "QFrame#outerFrame { background-color: white;"
            " border: 1px solid #1E5BA8; border-radius: 4px; }"
        )
    data_table = getattr(table, "_data_table", None)
    if data_table is not None:
        data_table.setStyleSheet(_INFO_TABLE_BLUE_STYLE)

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


_HEALTH_PILL_COLORS = {
    "ok": ("#E6F4EA", "#1E7E34", "#A3D9B1"),
    "warn": ("#FFF4D6", "#9A7A00", "#E6D08A"),
    "bad": ("#FCE8E8", "#B71C1C", "#E6A6A6"),
    "neutral": ("#EEF2F7", "#475569", "#C9D5E3"),
}



__all__ = [name for name in globals() if not name.startswith('__')]
