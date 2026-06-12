"""
DataForgeGroup — designer widget for cross-query DataForges.

Each DataForgeGroup manages:
  - Source saved queries (instead of direct tables)
  - A QTabWidget with Filter, Joins, Display, Results, SQL, Code tabs
  - A bottom bar with Queries, Field Picker, Save, Run buttons
  - Execution via pandas merge/filter operations
"""
from __future__ import annotations

import logging
import time
from copy import deepcopy

import pandas as pd
from PyQt6.QtCore import QMimeData, QPoint, Qt, pyqtSignal
from PyQt6.QtGui import QDrag, QFont
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QTabWidget,
    QLabel, QPushButton, QMessageBox, QApplication, QInputDialog, QTextEdit, QScrollArea,
    QFrame, QMenu, QCheckBox,
)

from suiteview.audit.qdefinition import QDefinition
from suiteview.audit import qdef_store
from suiteview.audit.query_object import (
    object_from_qdefinition,
    object_from_saved_query,
    qdefinition_from_query_object,
)
from suiteview.audit import query_object_store
from suiteview.audit.adhoc_source_intake import dataframe_from_adhoc_metadata
from suiteview.audit.dataforge.dataforge_model import DataForge, DataForgeSource
from suiteview.audit.dataforge import dataforge_store as df_store
from suiteview.audit.tabs.field_row import FieldRow, FieldGrid
from suiteview.audit.tabs.results_tab import ResultsTab
from suiteview.audit.tabs._styles import _FONT
from suiteview.audit.sql_helpers import fmt_time
from suiteview.audit.ui.bottom_bar import AuditBottomBar
from suiteview.audit.query_runner import (
    run_button_context,
    execute_odbc_query,
    run_query_async,
    format_query_error,
)
from suiteview.audit.dataforge.query_field_picker import FORGE_FIELD_DRAG_MIME
# Phase 2 join UI: the MS-Access-style canvas (field-linked Source boxes with
# drawn join lines) replaces the old card-based ForgeJoinsTab. ForgeJoinCanvas
# is API-compatible (update_queries / get_merge_ops / get_state / set_state /
# state_changed) and its set_state migrates the old {"cards": [...]} format, so
# previously-saved Forges still load. forge_joins_tab.py is kept for rollback.
from suiteview.audit.dataforge.forge_canvas_view import (
    ForgeJoinCanvas as ForgeJoinsTab,
)
# Phase 3 Manual mode: the visual design compiles to one DuckDB statement
# (shown on the SQL tab); Manual mode lets the user edit and run that SQL
# directly against the Source tables. See DATAFORGE_DESIGN.md §5.
from suiteview.audit.dataforge.forge_engine import (
    FilterSpec, ForgeEngineError, JoinSpec, OutputColumn,
    compile_forge_sql, run_manual_sql,
)

logger = logging.getLogger(__name__)

_FONT_LABEL = QFont("Segoe UI", 9)
_FONT_BOLD = QFont("Segoe UI", 9, QFont.Weight.Bold)
_FONT_MONO = QFont("Consolas", 10)

_FORGE = "#EA580C"
_FORGE_DARK = "#C2410C"
_FORGE_DEEP = "#7C2D12"
_FORGE_LIGHT = "#FED7AA"
_FORGE_BG = "#FFF3E8"
_FORGE_HOVER = "#FB923C"

_RUN_BTN_STYLE = (
    f"QPushButton {{ background-color: {_FORGE_DARK}; color: white; border: 1px solid {_FORGE_DEEP};"
    " border-radius: 3px; }"
    f"QPushButton:hover {{ background-color: {_FORGE}; }}"
)

_CLEAR_BTN_STYLE = (
    f"QPushButton {{ background-color: {_FORGE_DARK}; color: white;"
    f" border: 1px solid {_FORGE_DEEP}; border-radius: 2px;"
    " padding: 1px 8px; font-size: 9pt; }"
    f"QPushButton:hover {{ background-color: {_FORGE}; }}"
)

_SAVE_BTN_STYLE = (
    "QPushButton { background-color: #0A2A5C; color: #D4AF37;"
    " border: 2px solid #D4AF37; border-radius: 3px;"
    " padding: 1px 4px; font-size: 8pt; font-weight: bold; }"
    "QPushButton:hover { background-color: #123C69; color: #F4D03F; }"
)

_QUERIES_BTN_STYLE = (
    f"QPushButton {{ background-color: {_FORGE_BG}; color: {_FORGE_DARK};"
    f" border: 1px solid {_FORGE_DARK}; border-radius: 3px;"
    " padding: 2px 10px; font-size: 9pt; font-weight: bold; }"
    f"QPushButton:hover {{ background-color: {_FORGE_LIGHT}; }}"
)

_DATASET_BTN_STYLE = (
    f"QPushButton {{ background-color: {_FORGE_BG}; color: {_FORGE_DARK};"
    f" border: 1px solid {_FORGE_LIGHT}; border-radius: 3px;"
    " padding: 4px 12px; font-size: 9pt; }"
    f"QPushButton:hover {{ background-color: {_FORGE_LIGHT}; }}"
)

_DATASET_BTN_ACTIVE_STYLE = (
    f"QPushButton {{ background-color: {_FORGE_DARK}; color: white;"
    f" border: 1px solid {_FORGE_DEEP}; border-radius: 3px;"
    " padding: 4px 12px; font-size: 9pt; font-weight: bold; }"
    f"QPushButton:hover {{ background-color: {_FORGE}; }}"
)

_DISPLAY_REORDER_MIME = "application/x-dataforge-display-row-reorder"
_DISPLAY_AGGREGATES = ["display", "COUNT", "SUM", "MIN", "MAX"]

_DISPLAY_TOGGLE_STYLE = (
    f"QPushButton {{ font-size: 7pt; padding: 0px 4px;"
    f" border: 1px solid {_FORGE_DARK}; border-radius: 2px;"
    f" background-color: {_FORGE_LIGHT}; color: {_FORGE_DEEP};"
    " min-width: 48px; max-width: 60px; }}"
    f"QPushButton:hover {{ background-color: {_FORGE_HOVER}; }}"
)


# ── Helper: detect mode for DataForge fields ────────────────────────

def _detect_field_mode(col_name: str) -> str:
    """Guess the best FieldRow mode for a column name."""
    lower = col_name.lower()
    if any(kw in lower for kw in ("date", "time", "age", "count",
                                   "amount", "prem", "face", "nar",
                                   "ceded", "retn")):
        return "range"
    return "contains"


def _str_literal(value) -> str:
    return repr(str(value))


def _resolve_filter_column(df: pd.DataFrame, field_key: str, column: str) -> str:
    """Resolve a filter field to the concrete result DataFrame column."""
    candidates = [column, field_key]
    if "." in field_key:
        source_name, bare_column = field_key.rsplit(".", 1)
        candidates.extend([
            bare_column,
            f"{bare_column}_{source_name}",
            f"{bare_column}__{source_name}",
        ])
    for candidate in candidates:
        if candidate and candidate in df.columns:
            return candidate
    return ""


def _series_matches_range(series: pd.Series, lo: str, hi: str, column: str = "") -> pd.Series:
    """Build a boolean mask for numeric, datetime, or string range values."""
    mask = pd.Series(True, index=series.index)
    non_null = series.dropna()

    if non_null.empty:
        return mask

    lo_text = str(lo).strip()
    hi_text = str(hi).strip()

    sample_values = [str(value) for value in non_null.head(10)]
    temporal_markers = ("date", "time", "dt")
    looks_temporal = (
        pd.api.types.is_datetime64_any_dtype(series)
        or any(marker in column.lower() for marker in temporal_markers)
        or any(any(sep in value for sep in ("/", "-", ":")) for value in [lo_text, hi_text, *sample_values])
    )
    if looks_temporal:
        date_values = pd.to_datetime(series, errors="coerce")
        parsed_bounds = {
            "lo": pd.to_datetime(lo_text, errors="coerce") if lo_text else pd.NaT,
            "hi": pd.to_datetime(hi_text, errors="coerce") if hi_text else pd.NaT,
        }
        if date_values.notna().any() and (
            (lo_text and not pd.isna(parsed_bounds["lo"]))
            or (hi_text and not pd.isna(parsed_bounds["hi"]))
        ):
            if lo_text:
                mask &= date_values >= parsed_bounds["lo"]
            if hi_text:
                mask &= date_values <= parsed_bounds["hi"]
            return mask & date_values.notna()

    numeric_values = pd.to_numeric(series, errors="coerce")
    if numeric_values.notna().any():
        if lo_text:
            try:
                mask &= numeric_values >= float(lo_text.replace(",", ""))
            except ValueError:
                pass
        if hi_text:
            try:
                mask &= numeric_values <= float(hi_text.replace(",", ""))
            except ValueError:
                pass
        return mask & numeric_values.notna()

    text_values = series.astype(str)
    if lo_text:
        mask &= text_values >= lo_text
    if hi_text:
        mask &= text_values <= hi_text
    return mask


# ── Filter Tab for DataForge ─────────────────────────────────────────

class ForgeFilterTab(QScrollArea):
    """A filter criteria tab for a DataForge — wraps a FieldGrid."""

    def __init__(self, tab_name: str = "Filter", parent=None,
                 unique_provider: callable | None = None):
        super().__init__(parent)
        self.tab_name = tab_name
        self._unique_provider = unique_provider  # (query, col) → [str]
        self.setWidgetResizable(True)
        self.grid = FieldGrid(columns=2)
        self.setWidget(self.grid)

    def add_field_auto(self, query_name: str, col_name: str):
        """Auto-place a field from a query."""
        key = f"{query_name}.{col_name}"
        if self.grid.field(key) is not None:
            return  # already placed

        row = FieldRow(
            field_key=key,
            label_text=col_name,
            placeholder=f"{query_name}.{col_name}",
        )
        row._forge_unique_provider = self._unique_provider
        mode = _detect_field_mode(col_name)
        # Compute position below the last field
        if self.grid._rows:
            last = self.grid._rows[-1]
            last_pos = self.grid._positions.get(last.field_key, (4, 0))
            last_h = self.grid._sizes.get(last.field_key, (0, 0))[1] or last.sizeHint().height()
            next_y = self.grid._snap(last_pos[1] + last_h + 4)
            self.grid._positions[key] = (last_pos[0], next_y)
        self.grid.add_field(row)
        row.set_mode_idx(["contains", "regex", "combo", "list", "range"].index(mode))

    def get_state(self) -> dict:
        return {"tab_name": self.tab_name, "grid": self.grid.get_state()}

    def set_state(self, state: dict):
        self.tab_name = state.get("tab_name", self.tab_name)
        grid_state = state.get("grid", {})
        if grid_state:
            self.grid.set_state(grid_state)
        # Apply forge unique provider to all restored fields
        if self._unique_provider:
            for row in self.grid._rows:
                row._forge_unique_provider = self._unique_provider


# ── SQL Tab for DataForge (per-dataset buttons) ─────────────────────

# Sentinel for the Forge (DuckDB) view on the SQL tab — distinct from any
# real dataset name (those are query names).
_FORGE_VIEW = "⚒ Forge"

_FORGE_SQL_BTN_STYLE = (
    f"QPushButton {{ background-color: {_FORGE_BG}; color: {_FORGE_DEEP};"
    f" border: 1px solid {_FORGE_DARK}; border-radius: 3px;"
    " padding: 4px 12px; font-size: 9pt; font-weight: bold; }"
    f"QPushButton:hover {{ background-color: {_FORGE_LIGHT}; }}"
)

_FORGE_SQL_BTN_ACTIVE_STYLE = (
    f"QPushButton {{ background-color: {_FORGE_DEEP}; color: white;"
    f" border: 1px solid {_FORGE_DEEP}; border-radius: 3px;"
    " padding: 4px 12px; font-size: 9pt; font-weight: bold; }"
    f"QPushButton:hover {{ background-color: {_FORGE_DARK}; }}"
)


class ForgeSqlTab(QWidget):
    """SQL tab: the compiled Forge (DuckDB) SQL plus per-Source SQL views.

    The **Forge (DuckDB)** view shows the single DuckDB statement compiled
    from the visual design. Ticking **Manual mode** makes that SQL editable
    and the Forge runs it instead of the visual design — the Visual→Manual
    flip from DATAFORGE_DESIGN.md §5. The per-dataset buttons show the SQL
    each Source pulls (read-only), as before.
    """

    forge_sql_requested = pyqtSignal()   # ask the designer to (re)compile
    manual_state_changed = pyqtSignal()  # Manual toggled or manual SQL edited

    def __init__(self, parent=None):
        super().__init__(parent)
        self._sqls: dict[str, str] = {}  # query_name → SQL
        self._active: str = _FORGE_VIEW
        self._forge_sql: str = ""        # compiled from the visual design
        self._manual_sql: str = ""       # the user's hand-written SQL
        self._updating = False           # guards programmatic editor updates
        self._build_ui()

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(4, 4, 4, 4)
        root.setSpacing(4)

        # ── Button row: [Forge (DuckDB)] [datasets…] [Manual mode] ──
        top_row = QHBoxLayout()
        top_row.setSpacing(4)
        top_row.setContentsMargins(0, 0, 0, 0)

        self.btn_forge = QPushButton("Forge (DuckDB)")
        self.btn_forge.setFont(QFont("Segoe UI", 9))
        self.btn_forge.setStyleSheet(_FORGE_SQL_BTN_ACTIVE_STYLE)
        self.btn_forge.clicked.connect(self._select_forge_view)
        top_row.addWidget(self.btn_forge)

        self._btn_row = QHBoxLayout()
        self._btn_row.setSpacing(4)
        self._btn_row.setContentsMargins(0, 0, 0, 0)
        self._btn_row.addStretch()
        top_row.addLayout(self._btn_row, 1)

        self.chk_manual = QCheckBox("Manual mode")
        self.chk_manual.setFont(QFont("Segoe UI", 9))
        self.chk_manual.setStyleSheet(f"QCheckBox {{ color: {_FORGE_DEEP}; }}")
        self.chk_manual.setToolTip(
            "Edit the Forge SQL and run it instead of the visual design.")
        self.chk_manual.toggled.connect(self._on_manual_toggled)
        top_row.addWidget(self.chk_manual)
        root.addLayout(top_row)

        # ── Hint line (the tab teaches what it shows) ─────────────
        self.lbl_hint = QLabel()
        self.lbl_hint.setFont(QFont("Segoe UI", 8))
        self.lbl_hint.setStyleSheet("QLabel { color: #666; font-style: italic; }")
        self.lbl_hint.setWordWrap(True)
        root.addWidget(self.lbl_hint)

        # ── SQL display / editor ──────────────────────────────────
        self.txt_sql = QTextEdit()
        self.txt_sql.setFont(_FONT_MONO)
        self.txt_sql.setReadOnly(True)
        self.txt_sql.textChanged.connect(self._on_text_changed)

        # Syntax highlighting
        from suiteview.audit.tabs.sql_tab import _SqlHighlighter
        self._highlighter = _SqlHighlighter(self.txt_sql.document())

        root.addWidget(self.txt_sql, 1)

        self._buttons: dict[str, QPushButton] = {}
        self._refresh_view()

    # ── Public state ──────────────────────────────────────────────

    @property
    def manual_mode(self) -> bool:
        return self.chk_manual.isChecked()

    @property
    def manual_sql(self) -> str:
        return self._manual_sql

    def set_manual_state(self, manual: bool, sql: str):
        """Restore the saved Manual state (used by set_config)."""
        self._manual_sql = sql or ""
        self.chk_manual.setChecked(manual)
        self._refresh_view()

    def set_forge_sql(self, sql: str):
        """Update the compiled-from-visual-design DuckDB SQL."""
        self._forge_sql = sql or ""
        if self._active == _FORGE_VIEW and not self.manual_mode:
            self._refresh_view()

    def set_datasets(self, sqls: dict[str, str]):
        """Set the SQL for each dataset. Creates/updates buttons."""
        self._sqls = dict(sqls)

        # Clear old dataset buttons + stretch (the Forge button and the
        # Manual checkbox live outside this layout and are kept).
        self._buttons.clear()
        while self._btn_row.count():
            item = self._btn_row.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        for name in sqls:
            btn = QPushButton(name)
            btn.setFont(QFont("Segoe UI", 9))
            btn.setStyleSheet(_DATASET_BTN_STYLE)
            btn.clicked.connect(lambda checked, n=name: self._select_dataset(n))
            self._btn_row.addWidget(btn)
            self._buttons[name] = btn
        self._btn_row.addStretch()

        # Keep the current selection when it still exists; default to the
        # Forge view (the headline — the SQL the whole Forge runs).
        if self._active in self._sqls:
            self._select_dataset(self._active)
        else:
            self._select_forge_view()

    # ── View switching ────────────────────────────────────────────

    def _select_forge_view(self):
        self._active = _FORGE_VIEW
        self._refresh_view()

    def _select_dataset(self, name: str):
        self._active = name
        self._refresh_view()

    def _refresh_view(self):
        """Re-render buttons, hint, and editor for the active view/state."""
        manual = self.manual_mode
        forge_active = self._active == _FORGE_VIEW

        self.btn_forge.setStyleSheet(
            _FORGE_SQL_BTN_ACTIVE_STYLE if forge_active else _FORGE_SQL_BTN_STYLE)
        for n, btn in self._buttons.items():
            btn.setStyleSheet(
                _DATASET_BTN_ACTIVE_STYLE if (not forge_active and n == self._active)
                else _DATASET_BTN_STYLE)

        editable = forge_active and manual
        self._updating = True
        try:
            self.txt_sql.setReadOnly(not editable)
            if editable:
                # Orange border = custom criteria (app-wide visual cue).
                self.txt_sql.setStyleSheet(
                    "QTextEdit { background-color: white;"
                    f" border: 2px solid {_FORGE_DARK}; border-radius: 3px; }}")
                self.txt_sql.setPlainText(self._manual_sql)
                self.lbl_hint.setText(
                    "Manual mode — this SQL runs instead of the visual design "
                    "(Filter / Joins / Display tabs are ignored). Reference "
                    "Sources by their quoted table names, e.g. "
                    "SELECT * FROM \"My Query\".")
            else:
                self.txt_sql.setStyleSheet(
                    "QTextEdit { background-color: #FAFAFA; border: 1px solid #DDD;"
                    " border-radius: 3px; }")
                if forge_active:
                    self.txt_sql.setPlainText(self._forge_sql)
                    self.lbl_hint.setText(
                        "DuckDB SQL compiled from the visual design. Tick "
                        "Manual mode to edit it and run your own SQL instead.")
                else:
                    from suiteview.audit.tabs.sql_tab import _format_sql
                    sql = self._sqls.get(self._active, "")
                    self.txt_sql.setPlainText(_format_sql(sql) if sql else "")
                    self.lbl_hint.setText(
                        f"SQL that pulls Source “{self._active}” (read-only).")
        finally:
            self._updating = False

    # ── Manual mode ───────────────────────────────────────────────

    def _on_manual_toggled(self, checked: bool):
        if checked:
            # Visual→Manual flip: prefill from the freshly-compiled design.
            self.forge_sql_requested.emit()
            if not self._manual_sql.strip():
                self._manual_sql = self._forge_sql
        self._select_forge_view()
        self.manual_state_changed.emit()

    def _on_text_changed(self):
        if self._updating or not (self.manual_mode and self._active == _FORGE_VIEW):
            return
        self._manual_sql = self.txt_sql.toPlainText()
        self.manual_state_changed.emit()


# ── Code Tab (Python/Pandas) ────────────────────────────────────────

class ForgeCodeTab(QWidget):
    """Displays the generated Python/pandas code that merges datasets."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._build_ui()

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(4, 4, 4, 4)
        root.setSpacing(4)

        lbl = QLabel("Python Code — Dataset Merge & Filter")
        lbl.setFont(QFont("Segoe UI", 9, QFont.Weight.Bold))
        lbl.setStyleSheet(f"color: {_FORGE_DARK};")
        root.addWidget(lbl)

        self.txt_code = QTextEdit()
        self.txt_code.setFont(_FONT_MONO)
        self.txt_code.setReadOnly(True)
        self.txt_code.setStyleSheet(
            "QTextEdit { background-color: #1E1E2E; color: #CDD6F4;"
            " border: 1px solid #45475A; border-radius: 3px; }")
        root.addWidget(self.txt_code, 1)

        # Copy button
        btn_copy = QPushButton("Copy to Clipboard")
        btn_copy.setFont(QFont("Segoe UI", 9))
        btn_copy.setFixedHeight(28)
        btn_copy.setStyleSheet(
            f"QPushButton {{ background-color: {_FORGE_DARK}; color: white;"
            f" border: 1px solid {_FORGE_DEEP}; border-radius: 3px;"
            " padding: 2px 12px; }"
            f"QPushButton:hover {{ background-color: {_FORGE}; }}")
        btn_copy.clicked.connect(self._copy_code)
        root.addWidget(btn_copy)

    def set_code(self, code: str):
        self.txt_code.setPlainText(code)

    def _copy_code(self):
        QApplication.clipboard().setText(self.txt_code.toPlainText())


# ── Display Tab for DataForge ────────────────────────────────────────

class ForgeDisplayFieldRow(QFrame):
    """One DataForge display field row with aggregate toggle + reorder drag."""
    state_changed = pyqtSignal()

    def __init__(self, field_key: str, display_name: str,
                 parent: QWidget | None = None):
        super().__init__(parent)
        self.field_key = field_key
        self._display_name = display_name
        self._agg_idx = 0
        self._drag_start_pos: QPoint | None = None

        self.setFrameShape(QFrame.Shape.StyledPanel)
        self.setFixedHeight(26)
        self.setCursor(Qt.CursorShape.OpenHandCursor)
        self.setStyleSheet(
            "ForgeDisplayFieldRow { border: 1px solid #FDBA74;"
            " border-radius: 2px; background-color: #FFF7ED; }"
            "ForgeDisplayFieldRow:hover { background-color: #FED7AA; }"
        )

        lay = QHBoxLayout(self)
        lay.setContentsMargins(4, 2, 4, 2)
        lay.setSpacing(6)

        self.btn_agg = QPushButton("display")
        self.btn_agg.setFont(QFont("Segoe UI", 7))
        self.btn_agg.setFixedSize(52, 18)
        self.btn_agg.setStyleSheet(_DISPLAY_TOGGLE_STYLE)
        self.btn_agg.setToolTip("Click to cycle: display -> COUNT -> SUM -> MIN -> MAX")
        self.btn_agg.clicked.connect(self._cycle_agg)
        self.btn_agg.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.btn_agg.customContextMenuRequested.connect(self._show_agg_menu)
        lay.addWidget(self.btn_agg)

        self.lbl_name = QLabel(display_name)
        self.lbl_name.setFont(_FONT_BOLD)
        self.lbl_name.setStyleSheet("color: #0F172A; background: transparent;")
        lay.addWidget(self.lbl_name)

        self.lbl_key = QLabel(f"({field_key})")
        self.lbl_key.setFont(QFont("Segoe UI", 7))
        self.lbl_key.setStyleSheet("color: #7C2D12; background: transparent;")
        lay.addWidget(self.lbl_key)
        lay.addStretch()

        self.btn_remove = QPushButton("x")
        self.btn_remove.setFont(QFont("Segoe UI", 7))
        self.btn_remove.setFixedSize(16, 16)
        self.btn_remove.setStyleSheet(
            "QPushButton { border: none; color: #9A3412; background: transparent; }"
            "QPushButton:hover { color: #C00000; }")
        self.btn_remove.setToolTip("Remove from Display")
        lay.addWidget(self.btn_remove)

    @property
    def aggregate(self) -> str:
        return _DISPLAY_AGGREGATES[self._agg_idx]

    @property
    def display_name(self) -> str:
        return self._display_name

    def _cycle_agg(self):
        self._agg_idx = (self._agg_idx + 1) % len(_DISPLAY_AGGREGATES)
        self.btn_agg.setText(_DISPLAY_AGGREGATES[self._agg_idx])
        self.state_changed.emit()

    def _show_agg_menu(self, pos):
        menu = QMenu(self)
        actions = []
        for idx, name in enumerate(_DISPLAY_AGGREGATES):
            act = menu.addAction(name)
            act.setCheckable(True)
            act.setChecked(idx == self._agg_idx)
            actions.append((act, idx))
        chosen = menu.exec(self.btn_agg.mapToGlobal(pos))
        if chosen is None:
            return
        for act, idx in actions:
            if chosen is act:
                self._agg_idx = idx
                self.btn_agg.setText(_DISPLAY_AGGREGATES[idx])
                self.state_changed.emit()
                return

    def get_state(self) -> dict:
        return {
            "field_key": self.field_key,
            "display_name": self._display_name,
            "aggregate": self._agg_idx,
        }

    def set_state(self, state: dict):
        self._agg_idx = max(0, min(len(_DISPLAY_AGGREGATES) - 1,
                                  int(state.get("aggregate", 0))))
        self.btn_agg.setText(_DISPLAY_AGGREGATES[self._agg_idx])
        display_name = state.get("display_name", self._display_name)
        if display_name:
            self._display_name = display_name
            self.lbl_name.setText(display_name)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_start_pos = event.pos()
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if (self._drag_start_pos is not None
                and event.buttons() & Qt.MouseButton.LeftButton):
            dist = (event.pos() - self._drag_start_pos).manhattanLength()
            if dist >= QApplication.startDragDistance():
                self._start_drag()
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        self._drag_start_pos = None
        super().mouseReleaseEvent(event)

    def _start_drag(self):
        self._drag_start_pos = None
        drag = QDrag(self)
        mime = QMimeData()
        mime.setData(_DISPLAY_REORDER_MIME, self.field_key.encode("utf-8"))
        drag.setMimeData(mime)
        self.setCursor(Qt.CursorShape.ClosedHandCursor)
        drag.exec(Qt.DropAction.MoveAction)
        self.setCursor(Qt.CursorShape.OpenHandCursor)


class ForgeDisplayTab(QScrollArea):
    """Select and order final DataForge output fields."""
    state_changed = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWidgetResizable(True)
        self.setAcceptDrops(True)
        self._all_columns: list[str] = []

        self._container = QWidget()
        self.setWidget(self._container)
        self._layout = QVBoxLayout(self._container)
        self._layout.setContentsMargins(6, 6, 6, 6)
        self._layout.setSpacing(4)
        self._layout.setAlignment(Qt.AlignmentFlag.AlignTop)

        from PyQt6.QtWidgets import QCheckBox
        self.chk_all = QCheckBox("Display all columns")
        self.chk_all.setFont(_FONT_BOLD)
        self.chk_all.setChecked(True)
        self.chk_all.toggled.connect(self.state_changed.emit)
        self._layout.addWidget(self.chk_all)

        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setStyleSheet("color: #FDBA74;")
        self._layout.addWidget(sep)

        self._hint = QLabel("Drag fields here from Forge Assist, or double-click to add.")
        self._hint.setFont(QFont("Segoe UI", 8))
        self._hint.setStyleSheet("color: #9A3412;")
        self._hint.setWordWrap(True)
        self._layout.addWidget(self._hint)

        self.lbl_count = QLabel("")
        self.lbl_count.setFont(QFont("Segoe UI", 8))
        self.lbl_count.setStyleSheet("color: #9A3412;")
        self._layout.addWidget(self.lbl_count)

        self._layout.addStretch()
        self._rows: list[ForgeDisplayFieldRow] = []
        self._field_set: set[str] = set()

        self._drop_indicator = QFrame(self._container)
        self._drop_indicator.setFixedHeight(3)
        self._drop_indicator.setStyleSheet(
            f"background-color: {_FORGE_DARK}; border-radius: 1px;")
        self._drop_indicator.hide()

    @property
    def display_all(self) -> bool:
        return self.chk_all.isChecked()

    def set_columns(self, columns: list[str]):
        """Set available columns from merged datasets."""
        self._all_columns = list(columns)
        self.lbl_count.setText(f"{len(columns)} columns available")

    def add_field(self, field_key: str, display_name: str = ""):
        """Add a display field row, preserving order and avoiding duplicates."""
        field_key = field_key.strip()
        if not field_key or field_key in self._field_set:
            return
        display_name = display_name or field_key.split(".")[-1]
        row = ForgeDisplayFieldRow(field_key, display_name, self._container)
        row.btn_remove.clicked.connect(lambda: self._remove_row(row))
        row.state_changed.connect(self.state_changed)
        self._rows.append(row)
        self._field_set.add(field_key)
        self._layout.insertWidget(self._layout.count() - 1, row)
        self._update_hint_visibility()
        self.state_changed.emit()

    def add_query_field(self, query_name: str, col_name: str):
        self.chk_all.setChecked(False)
        self.add_field(f"{query_name}.{col_name}", col_name)

    def _remove_row(self, row: ForgeDisplayFieldRow):
        if row not in self._rows:
            return
        self._rows.remove(row)
        self._field_set.discard(row.field_key)
        self._layout.removeWidget(row)
        row.setParent(None)
        row.deleteLater()
        self._update_hint_visibility()
        self.state_changed.emit()

    def _update_hint_visibility(self):
        self._hint.setVisible(len(self._rows) == 0)

    def get_selected_columns(self) -> list[str]:
        if self.display_all:
            return list(self._all_columns)
        return [item["column"] for item in self.get_display_columns()]

    def get_display_columns(self) -> list[dict]:
        result = []
        for row in self._rows:
            parts = row.field_key.split(".")
            result.append({
                "column": parts[-1] if parts else row.field_key,
                "field_key": row.field_key,
                "display_name": row.display_name,
                "aggregate": row.aggregate,
            })
        return result

    def dragEnterEvent(self, event):
        md = event.mimeData()
        if md.hasFormat(FORGE_FIELD_DRAG_MIME) or md.hasFormat(_DISPLAY_REORDER_MIME):
            event.acceptProposedAction()
        else:
            super().dragEnterEvent(event)

    def dragMoveEvent(self, event):
        md = event.mimeData()
        if md.hasFormat(FORGE_FIELD_DRAG_MIME) or md.hasFormat(_DISPLAY_REORDER_MIME):
            event.acceptProposedAction()
            self._show_drop_indicator(event.position().toPoint())
        else:
            super().dragMoveEvent(event)

    def dragLeaveEvent(self, event):
        self._drop_indicator.hide()
        super().dragLeaveEvent(event)

    def dropEvent(self, event):
        self._drop_indicator.hide()
        md = event.mimeData()
        if md.hasFormat(_DISPLAY_REORDER_MIME):
            key = bytes(md.data(_DISPLAY_REORDER_MIME)).decode("utf-8")
            self._reorder_row(key, self._drop_index(event.position().toPoint()))
            event.acceptProposedAction()
            return
        if md.hasFormat(FORGE_FIELD_DRAG_MIME):
            data = bytes(md.data(FORGE_FIELD_DRAG_MIME)).decode("utf-8")
            self.chk_all.setChecked(False)
            insert_idx = self._drop_index(event.position().toPoint())
            added = []
            for line in data.split("\n"):
                parts = line.strip().split("|")
                if len(parts) >= 2:
                    query_name, col_name = parts[0], parts[1]
                    key = f"{query_name}.{col_name}"
                    if key not in self._field_set:
                        self.add_field(key, col_name)
                        added.append(key)
            for offset, key in enumerate(added):
                self._reorder_row(key, insert_idx + offset)
            event.acceptProposedAction()
            return
        super().dropEvent(event)

    def _drop_index(self, pos: QPoint) -> int:
        container_pos = self._container.mapFrom(self, pos)
        for idx, row in enumerate(self._rows):
            if container_pos.y() < row.y() + row.height() // 2:
                return idx
        return len(self._rows)

    def _show_drop_indicator(self, pos: QPoint):
        idx = self._drop_index(pos)
        if not self._rows:
            self._drop_indicator.hide()
            return
        if idx < len(self._rows):
            y = self._rows[idx].y() - 2
        else:
            last = self._rows[-1]
            y = last.y() + last.height() + 1
        self._drop_indicator.setGeometry(self._rows[0].x(), y,
                                         self._rows[0].width(), 3)
        self._drop_indicator.raise_()
        self._drop_indicator.show()

    def _reorder_row(self, field_key: str, new_idx: int):
        row = None
        old_idx = -1
        for idx, candidate in enumerate(self._rows):
            if candidate.field_key == field_key:
                row = candidate
                old_idx = idx
                break
        if row is None:
            return
        if new_idx > old_idx:
            new_idx -= 1
        new_idx = max(0, min(new_idx, len(self._rows) - 1))
        if new_idx == old_idx:
            return
        self._layout.removeWidget(row)
        self._rows.pop(old_idx)
        self._rows.insert(new_idx, row)
        row_start = self._layout.count() - 1 - len(self._rows)
        self._layout.insertWidget(row_start + new_idx, row)
        self.state_changed.emit()

    def get_state(self) -> dict:
        return {
            "display_all": self.display_all,
            "fields": [row.get_state() for row in self._rows],
        }

    def set_state(self, state: dict):
        self.chk_all.setChecked(state.get("display_all", True))
        for row in list(self._rows):
            self._remove_row(row)
        fields = state.get("fields", [])
        if not fields and state.get("selected"):
            fields = [
                {"field_key": col, "display_name": col, "aggregate": 0}
                for col in state.get("selected", [])
            ]
        for field_state in fields:
            key = field_state.get("field_key", "")
            self.add_field(key, field_state.get("display_name", key))
            if self._rows:
                self._rows[-1].set_state(field_state)
        self._update_hint_visibility()


# ═════════════════════════════════════════════════════════════════════
# DataForgeGroup — main designer widget
# ═════════════════════════════════════════════════════════════════════

class DataForgeGroup(QWidget):
    """Complete designer widget for a DataForge.

    Contains tab widget + bottom bar. Similar structure to DynamicQuery
    but operates on saved queries instead of direct tables.
    """
    config_changed = pyqtSignal()
    source_records_changed = pyqtSignal()
    forge_saved = pyqtSignal(object)      # DataForge
    forge_deleted = pyqtSignal(str)       # forge name
    new_forge_requested = pyqtSignal()

    def __init__(self, name: str, parent=None, saved_forge_name: str = ""):
        super().__init__(parent)
        self.forge_name = name
        self._saved_forge_name = saved_forge_name

        # Source queries: name → QDefinition
        self._sources: dict[str, QDefinition] = {}
        self._datasets: dict[str, pd.DataFrame] = {}  # in-memory query results
        self._queries_dialog = None
        self._loading = False
        self._dirty = False

        self._build_ui()

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(2)

        header = QWidget()
        header.setStyleSheet(f"QWidget {{ background-color: {_FORGE_BG}; }}")
        header_lay = QHBoxLayout(header)
        header_lay.setContentsMargins(6, 4, 6, 2)
        header_lay.setSpacing(6)
        self._lbl_name = QLabel()
        self._lbl_name.setFont(QFont("Segoe UI", 14, QFont.Weight.Bold))
        self._lbl_name.setStyleSheet(f"QLabel {{ color: {_FORGE_DEEP}; }}")
        header_lay.addWidget(self._lbl_name)
        header_lay.addStretch()

        self.btn_new_forge = QPushButton("New Forge")
        self.btn_new_forge.setFont(_FONT_BOLD)
        self.btn_new_forge.setFixedSize(82, 36)
        self.btn_new_forge.setStyleSheet(_SAVE_BTN_STYLE)
        self.btn_new_forge.clicked.connect(self.new_forge_requested)

        self.btn_save_as = QPushButton("Save As")
        self.btn_save_as.setFont(_FONT_BOLD)
        self.btn_save_as.setFixedSize(60, 36)
        self.btn_save_as.setStyleSheet(_SAVE_BTN_STYLE)
        self.btn_save_as.clicked.connect(self._save_forge)

        self.btn_save = QPushButton("Save")
        self.btn_save.setFont(_FONT_BOLD)
        self.btn_save.setFixedSize(60, 36)
        self.btn_save.setStyleSheet(_SAVE_BTN_STYLE)
        self.btn_save.clicked.connect(self._save_or_update)
        root.addWidget(header)

        # ── Tab widget ───────────────────────────────────────────────
        self.tab_widget = QTabWidget()
        self.tab_widget.setFont(_FONT)
        self.tab_widget.setStyleSheet(
            f"QTabWidget::pane {{ border-top: 3px solid {_FORGE_DARK};"
            f" border-bottom: 3px solid {_FORGE_DARK};"
            " border-left: 1px solid #999; border-right: 1px solid #999;"
            f" background-color: {_FORGE_BG}; }}"
            f"QTabBar {{ background-color: {_FORGE_BG}; }}"
            "QTabBar::tab { padding: 2px 8px; min-height: 20px; font-size: 9pt;"
            f" background-color: {_FORGE_LIGHT}; border: 1px solid {_FORGE_DARK};"
            " border-bottom: none; border-top-left-radius: 3px;"
            " border-top-right-radius: 3px; margin-right: 1px; }"
            "QTabBar::tab:selected { font-weight: bold;"
            f" background-color: {_FORGE_BG}; color: {_FORGE_DEEP}; }}"
            f"QTabBar::tab:!selected {{ background-color: {_FORGE_LIGHT}; color: #444; }}"
            f"QTabBar::tab:hover:!selected {{ background-color: {_FORGE_HOVER}; }}"
        )

        # Filter tab
        self._filter_tabs: list[ForgeFilterTab] = []
        self._add_filter_tab("Filter")

        # Joins tab
        self.joins_tab = ForgeJoinsTab()
        self.joins_tab.state_changed.connect(self._schedule_save)
        self.tab_widget.addTab(self.joins_tab, "Joins")

        # Display tab
        self.display_tab = ForgeDisplayTab()
        self.display_tab.state_changed.connect(self._schedule_save)
        self.tab_widget.addTab(self.display_tab, "Display")

        # Results tab
        self.results_tab = ResultsTab()
        self.tab_widget.addTab(self.results_tab, "Results")

        # SQL tab — compiled Forge (DuckDB) SQL + Manual mode + per-dataset SQL
        self.sql_tab = ForgeSqlTab()
        self.sql_tab.forge_sql_requested.connect(self._refresh_forge_sql)
        self.sql_tab.manual_state_changed.connect(self._schedule_save)
        self.tab_widget.addTab(self.sql_tab, "SQL")
        self.tab_widget.currentChanged.connect(self._on_tab_changed)

        # Code tab (Python/pandas)
        self.code_tab = ForgeCodeTab()
        self.tab_widget.addTab(self.code_tab, "Code")

        root.addWidget(self.tab_widget, 1)

        # ── Bottom bar ───────────────────────────────────────────────
        self.bottom_bar = AuditBottomBar(
            bg_color=_FORGE_BG, run_label="Run\nForge",
            run_style=_RUN_BTN_STYLE)

        # Convenience aliases
        self.btn_all = self.bottom_bar.btn_all
        self.txt_max_count = self.bottom_bar.txt_max_count
        self.lbl_result_count = self.bottom_bar.lbl_result_count
        self.lbl_query_time = self.bottom_bar.lbl_query_time
        self.lbl_print_time = self.bottom_bar.lbl_print_time
        self.lbl_total_time = self.bottom_bar.lbl_total_time
        self.btn_run = self.bottom_bar.btn_run

        self.bottom_bar.center_action_layout.addWidget(self.btn_new_forge)
        self.bottom_bar.center_action_layout.addWidget(self.btn_save_as)
        self.bottom_bar.center_action_layout.addWidget(self.btn_save)

        _DELETE_BTN_STYLE = (
            "QPushButton { background-color: #C00000; color: white;"
            " border: 1px solid #900; border-radius: 3px;"
            " padding: 2px 10px; font-size: 9pt; font-weight: bold; }"
            "QPushButton:hover { background-color: #E00000; }"
        )
        self.btn_delete = QPushButton("Delete")
        self.btn_delete.setFont(_FONT_BOLD)
        self.btn_delete.setFixedSize(65, 36)
        self.btn_delete.setStyleSheet(_DELETE_BTN_STYLE)
        self.btn_delete.clicked.connect(self._delete_forge)
        self.bottom_bar.action_layout.addWidget(self.btn_delete)

        self.btn_run.clicked.connect(self._run_forge)

        root.addWidget(self.bottom_bar)
        self._update_forge_heading()

    # ── Tab management ───────────────────────────────────────────────

    def _add_filter_tab(self, name: str) -> ForgeFilterTab:
        tab = ForgeFilterTab(
            tab_name=name, unique_provider=self.get_unique_values)
        self._filter_tabs.append(tab)
        idx = max(self.tab_widget.count() - 5, 0)  # before Joins/Display/Results/SQL/Code
        self.tab_widget.insertTab(idx, tab, name)
        tab.grid.state_changed.connect(self._schedule_save)
        return tab

    def _on_tab_changed(self, idx: int):
        # Compile the visual design whenever the SQL tab comes into view so
        # the Forge (DuckDB) statement always reflects the current design.
        if self.tab_widget.widget(idx) is self.sql_tab:
            self._refresh_forge_sql()

    # ── Source management ────────────────────────────────────────────

    def _open_queries_dialog(self):
        """Open the Queries && Fields dialog (mirrors Tables dialog)."""
        if self._queries_dialog is not None and self._queries_dialog.isVisible():
            self._queries_dialog.raise_()
            return

        from suiteview.audit.dataforge.queries_dialog import QueriesFieldsDialog
        dlg = QueriesFieldsDialog(self._sources, self,
                                   forge_name=self._saved_forge_name)
        dlg.setWindowModality(Qt.WindowModality.NonModal)
        dlg.field_requested.connect(self.on_field_requested)
        dlg.sources_changed.connect(self._on_sources_changed)
        dlg.finished.connect(lambda: self._on_queries_dialog_closed(dlg))
        dlg.run_query_requested.connect(self._run_single_query)
        dlg.view_query_requested.connect(self._view_query_results)
        dlg.update_data_status(set(self._datasets.keys()))
        self._queries_dialog = dlg
        dlg.show()

    def _on_queries_dialog_closed(self, dlg):
        """Sync sources when the dialog is closed."""
        self.sync_source_copies(list(dlg.get_sources().keys()))
        self._queries_dialog = None

    def _on_sources_changed(self, names: list[str]):
        """Handle live source changes from the dialog."""
        # Reload sources from the dialog
        if self._queries_dialog:
            self.sync_source_copies(list(self._queries_dialog.get_sources().keys()))

    def _query_columns_map(self) -> dict[str, list[str]]:
        """Build {query_name: [col, ...]} from current sources."""
        return {name: sq.result_columns
                for name, sq in self._sources.items()}

    def _dataforge_source_copy_name(self, source_name: str) -> str:
        """Return the private Query Object name used inside this DataForge."""
        label = self._saved_forge_name.strip() or "DataForge"
        return f"{source_name} [{label}]"

    @staticmethod
    def _source_original_name(qd: QDefinition, fallback: str) -> str:
        config = getattr(qd, "query_object_config", {}) or {}
        dataforge = config.get("dataforge", {}) if isinstance(config, dict) else {}
        source_name = str(dataforge.get("source_name", "")).strip()
        if source_name:
            return source_name
        if fallback.endswith("]"):
            source, sep, _suffix = fallback.rpartition(" [")
            if sep and source.strip():
                return source.strip()
        return fallback

    @staticmethod
    def _delete_query_copy_records(name: str, forge_name: str = "") -> None:
        """Delete a DataForge-local query copy and its visual design, if present."""
        if not name:
            return
        try:
            from suiteview.audit import saved_query_store
            if saved_query_store.query_exists(name):
                saved_query_store.delete_query(name)
            else:
                query_object_store.delete_object(name)
        except Exception:
            logger.exception("Failed to delete DataForge query object copy: %s", name)
        for scope in {forge_name, "DataForge", qdef_store.COMMONS_NAME}:
            if not scope:
                continue
            try:
                qdef_store.delete_qdef(name, forge_name=scope)
            except Exception:
                logger.exception("Failed to delete DataForge QDefinition copy: %s", name)

    @staticmethod
    def _copy_query_object_overwrite(source_name: str, new_name: str):
        try:
            from suiteview.audit import saved_query_store
            if saved_query_store.query_exists(new_name):
                saved_query_store.delete_query(new_name)
            else:
                query_object_store.delete_object(new_name)
            return query_object_store.copy_object(source_name, new_name)
        except Exception:
            logger.exception(
                "Failed to copy DataForge QueryObject %s to %s",
                source_name,
                new_name,
            )
            return None

    @staticmethod
    def _replace_source_prefix(value: str, mapping: dict[str, str]) -> str:
        for old, new in mapping.items():
            if value == old:
                return new
            prefix = f"{old}."
            if value.startswith(prefix):
                return f"{new}.{value[len(prefix):]}"
        return value

    def add_source_copy(self, source_name: str, *, refresh: bool = True) -> QDefinition | None:
        """Add a query as an independent DataForge source copy."""
        if source_name in self._sources:
            return self._sources[source_name]

        forge_name = self._saved_forge_name.strip() or "DataForge"
        obj = query_object_store.load_object(source_name)
        if obj is None:
            try:
                from suiteview.audit import saved_query_store
                saved_query = saved_query_store.load_query(source_name)
                if saved_query is not None:
                    obj = object_from_saved_query(saved_query)
                    query_object_store.save_object(obj)
            except Exception:
                logger.exception(
                    "Failed to publish visual query before DataForge copy: %s",
                    source_name,
                )
        original_name = source_name
        if obj is not None:
            dataforge = (obj.config or {}).get("dataforge", {})
            original_name = str(dataforge.get("source_name", "")).strip() or source_name
        copy_name = self._dataforge_source_copy_name(original_name)

        if copy_name in self._sources:
            return self._sources[copy_name]

        if obj is not None:
            if query_object_store.object_exists(copy_name):
                copied = query_object_store.load_object(copy_name)
            else:
                copied = query_object_store.copy_object(source_name, copy_name)
            if copied is None:
                return None
            copied.config = dict(copied.config or {})
            copied.config["dataforge"] = {
                "forge_name": forge_name,
                "source_name": original_name,
            }
            copied.source_design = copied.source_design or original_name
            query_object_store.save_object(copied)
            qd = qdefinition_from_query_object(copied)
        else:
            qd = qdef_store.load_qdef(source_name, forge_name=self._saved_forge_name)
            if qd is None:
                qd = qdef_store.load_qdef(source_name)
            if qd is None:
                return None
            original_name = self._source_original_name(qd, source_name)
            copy_name = self._dataforge_source_copy_name(original_name)
            if copy_name in self._sources:
                return self._sources[copy_name]
            qd = QDefinition.from_dict(deepcopy(qd.to_dict()))
            qd.name = copy_name

        qd.forge_name = self._saved_forge_name
        self._sources[qd.name] = qd
        if refresh:
            self.joins_tab.update_queries(list(self._sources.keys()),
                                         self._query_columns_map())
            self._schedule_save()
            self._persist_source_roster_if_saved()
            self.source_records_changed.emit()
        return qd

    def sync_source_copies(self, source_names: list[str]) -> None:
        """Sync selected source names, converting each to a private copy."""
        desired: set[str] = set()
        for name in source_names:
            if name in self._sources:
                desired.add(name)
                continue
            qd = self.add_source_copy(name, refresh=False)
            if qd is not None:
                desired.add(qd.name)

        removed: list[tuple[str, str]] = []
        for name in list(self._sources.keys()):
            if name not in desired:
                qd = self._sources.pop(name, None)
                self._datasets.pop(name, None)
                removed.append((name, getattr(qd, "forge_name", "") if qd else ""))

        for name, forge_name in removed:
            self._delete_query_copy_records(name, forge_name or self._saved_forge_name)

        self.joins_tab.update_queries(list(self._sources.keys()),
                                     self._query_columns_map())
        self._schedule_save()
        self._persist_source_roster_if_saved()
        self.source_records_changed.emit()

    def _persist_source_roster_if_saved(self) -> None:
        """Keep saved DataForge source records aligned with live add/remove."""
        name = self._saved_forge_name.strip()
        if not name or not df_store.forge_exists(name):
            return
        existing = df_store.load_forge(name)
        kwargs = {}
        if existing is not None:
            kwargs["created_at"] = existing.created_at
        forge = DataForge(
            name=name,
            sources=self._dataforge_sources_for_save(name),
            config=self.get_config(),
            **kwargs,
        )
        df_store.save_forge(forge)

    def _promote_unsaved_source_names(self, forge_name: str) -> None:
        """Rename temporary [DataForge] copies to this forge's real name."""
        mapping: dict[str, str] = {}
        promoted: dict[str, QDefinition] = {}
        temporary_records: list[tuple[str, str]] = []
        for old_name, qd in list(self._sources.items()):
            source_label = self._source_label_for_browser(qd, old_name)
            new_name = f"{source_label} [{forge_name}]"
            dataforge = (getattr(qd, "query_object_config", {}) or {}).get("dataforge", {})
            is_temporary = old_name.endswith(" [DataForge]") or dataforge.get("forge_name") == "DataForge"
            if not is_temporary or old_name == new_name:
                promoted[old_name] = qd
                continue

            obj = query_object_store.load_object(old_name)
            if obj is not None:
                copied = self._copy_query_object_overwrite(old_name, new_name)
                if copied is None:
                    promoted[old_name] = qd
                    continue
                copied.config = dict(copied.config or {})
                copied.config["dataforge"] = {
                    "forge_name": forge_name,
                    "source_name": source_label,
                }
                copied.source_design = copied.source_design or source_label
                query_object_store.save_object(copied)
                new_qd = qdefinition_from_query_object(copied)
            else:
                new_qd = QDefinition.from_dict(deepcopy(qd.to_dict()))
                new_qd.name = new_name
            new_qd.forge_name = forge_name
            promoted[new_name] = new_qd
            mapping[old_name] = new_name
            temporary_records.append((old_name, getattr(qd, "forge_name", "")))

        if not mapping:
            return
        self._sources = promoted
        for old, new in mapping.items():
            if old in self._datasets:
                self._datasets[new] = self._datasets.pop(old)
        self._rename_join_sources(mapping)
        self._rename_filter_sources(mapping)
        self._rename_display_sources(mapping)
        self.joins_tab.update_queries(list(self._sources.keys()),
                                     self._query_columns_map())
        for old_name, old_forge in temporary_records:
            self._delete_query_copy_records(old_name, old_forge)

    def discard_temporary_source_copies(self) -> None:
        """Remove unsaved DataForge-local source copies for a discarded `(new)` forge."""
        for name, qd in list(self._sources.items()):
            dataforge = (getattr(qd, "query_object_config", {}) or {}).get("dataforge", {})
            if name.endswith(" [DataForge]") or dataforge.get("forge_name") == "DataForge":
                self._delete_query_copy_records(name, getattr(qd, "forge_name", ""))

    def _rename_join_sources(self, mapping: dict[str, str]) -> None:
        state = self.joins_tab.get_state()
        for source in state.get("sources", []):
            source["alias"] = mapping.get(source.get("alias", ""), source.get("alias", ""))
        for join in state.get("joins", []):
            join["left_source"] = mapping.get(join.get("left_source", ""), join.get("left_source", ""))
            join["right_source"] = mapping.get(join.get("right_source", ""), join.get("right_source", ""))
        if state.get("removed"):
            state["removed"] = [mapping.get(a, a) for a in state["removed"]]
        self.joins_tab.set_state(state)

    def _rename_filter_sources(self, mapping: dict[str, str]) -> None:
        for tab in self._filter_tabs:
            grid = tab.grid
            for row in list(grid._rows):
                old_key = row.field_key
                new_key = self._replace_source_prefix(old_key, mapping)
                if new_key == old_key:
                    continue
                grid._field_map.pop(old_key, None)
                row.field_key = new_key
                row._placeholder = self._replace_source_prefix(getattr(row, "_placeholder", ""), mapping)
                grid._field_map[new_key] = row
                if old_key in grid._positions:
                    grid._positions[new_key] = grid._positions.pop(old_key)
                if old_key in grid._sizes:
                    grid._sizes[new_key] = grid._sizes.pop(old_key)
            grid._apply_positions()

    def _rename_display_sources(self, mapping: dict[str, str]) -> None:
        self.display_tab._field_set.clear()
        for row in self.display_tab._rows:
            new_key = self._replace_source_prefix(row.field_key, mapping)
            row.field_key = new_key
            row.lbl_key.setText(f"({new_key})")
            self.display_tab._field_set.add(new_key)

    def add_source_query(self, sq: QDefinition):
        """Programmatically add a source query."""
        self._sources[sq.name] = sq
        self.joins_tab.update_queries(list(self._sources.keys()),
                                     self._query_columns_map())

    def add_source_object(self, query_object):
        """Programmatically add a QueryObject source via QDefinition adapter."""
        self.add_source_query(qdefinition_from_query_object(query_object))

    # ── Field placement (from picker) ────────────────────────────────

    def on_field_requested(self, query_name: str, col_name: str):
        """Handle field placement from QueryFieldPicker."""
        current = self.tab_widget.currentWidget()
        if isinstance(current, ForgeDisplayTab):
            current.add_query_field(query_name, col_name)
            self._schedule_save()
            return
        if not isinstance(current, ForgeFilterTab):
            if self._filter_tabs:
                current = self._filter_tabs[0]
                self.tab_widget.setCurrentWidget(current)
            else:
                return
        current.add_field_auto(query_name, col_name)
        self._schedule_save()

    # ── Single-query execution (from Queries dialog) ─────────────────

    def _run_single_query(self, query_name: str):
        """Execute a single source query and cache its DataFrame."""
        sq = self._sources.get(query_name)
        if not sq:
            return
        if not sq.sql and not self._is_adhoc_source(sq):
            QMessageBox.warning(
                self, "Missing SQL",
                f"Query \"{query_name}\" has no SQL. Run and re-save it first.")
            return
        QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
        try:
            df = self._load_source_dataframe(sq)
            self._datasets[query_name] = df
            QApplication.restoreOverrideCursor()
            if self._queries_dialog and self._queries_dialog.isVisible():
                self._queries_dialog.update_data_status(
                    set(self._datasets.keys()))
            QMessageBox.information(
                self, "Query Loaded",
                f"\"{query_name}\" — {len(df)} rows loaded into memory.")
        except Exception as exc:
            QApplication.restoreOverrideCursor()
            logger.exception("Single query execution failed: %s", query_name)
            QMessageBox.warning(
                self, "Query Error",
                f"Failed to execute \"{query_name}\":\n\n{exc}")

    def get_unique_values(self, query_name: str, col_name: str) -> list[str]:
        """Return sorted unique values for a column from the cached dataset."""
        df = self._datasets.get(query_name)
        if df is None or col_name not in df.columns:
            return []
        vals = df[col_name].dropna().astype(str).unique().tolist()
        vals.sort()
        return vals

    def _view_query_results(self, query_name: str):
        """Show query results in a preview window. Load if not cached."""
        sq = self._sources.get(query_name)
        if not sq:
            return
        if not sq.sql and not self._is_adhoc_source(sq):
            QMessageBox.warning(
                self, "Missing SQL",
                f"Query \"{query_name}\" has no SQL. Run and re-save it first.")
            return

        # If data not loaded, execute with a progress dialog
        if query_name not in self._datasets:
            from PyQt6.QtWidgets import QProgressDialog
            progress = QProgressDialog(
                f"Running \"{query_name}\"...", "Cancel", 0, 0, self)
            progress.setWindowTitle("Loading Query")
            progress.setWindowModality(Qt.WindowModality.WindowModal)
            progress.setMinimumDuration(0)
            progress.setValue(0)
            QApplication.processEvents()

            try:
                df = self._load_source_dataframe(sq)
                self._datasets[query_name] = df
                if self._queries_dialog and self._queries_dialog.isVisible():
                    self._queries_dialog.update_data_status(
                        set(self._datasets.keys()))
            except Exception as exc:
                progress.close()
                logger.exception("View query failed: %s", query_name)
                QMessageBox.warning(
                    self, "Query Error",
                    f"Failed to execute \"{query_name}\":\n\n{exc}")
                return
            finally:
                progress.close()

        df = self._datasets[query_name]
        self._show_preview_window(query_name, df)

    def _show_preview_window(self, query_name: str, df: pd.DataFrame):
        """Open a preview window showing the first 1000 rows."""
        from suiteview.audit.dataforge._query_preview_window import (
            QueryPreviewWindow)
        win = QueryPreviewWindow(query_name, df, parent=None)
        win.show()
        # Keep reference to prevent GC
        if not hasattr(self, '_preview_windows'):
            self._preview_windows = []
        self._preview_windows.append(win)

    @staticmethod
    def _is_adhoc_source(sq: QDefinition) -> bool:
        return getattr(sq, "query_object_kind", "") == "adhoc_source"

    def _load_source_dataframe(self, sq: QDefinition) -> pd.DataFrame:
        if self._is_adhoc_source(sq):
            metadata = getattr(sq, "query_object_source_metadata", {}) or {}
            return dataframe_from_adhoc_metadata(
                sq.source_design,
                metadata,
                columns=sq.result_columns,
            )
        columns, rows = execute_odbc_query(sq.dsn, sq.sql)
        return pd.DataFrame([list(r) for r in rows], columns=columns)

    def _resolve_display_column(self, result: pd.DataFrame, spec: dict) -> str:
        column = spec.get("column", "")
        if column in result.columns:
            return column
        field_key = spec.get("field_key", "")
        if field_key in result.columns:
            return field_key
        source_name = field_key.rsplit(".", 1)[0] if "." in field_key else ""
        suffixed = f"{column}_{source_name}" if source_name else ""
        if suffixed in result.columns:
            return suffixed
        return ""

    def _unique_output_name(self, base: str, used: set[str]) -> str:
        name = base
        idx = 2
        while name in used:
            name = f"{base}_{idx}"
            idx += 1
        used.add(name)
        return name

    def _apply_display_columns(self, result: pd.DataFrame) -> pd.DataFrame:
        specs = self.display_tab.get_display_columns()
        if not specs:
            return result

        resolved = []
        for spec in specs:
            column = self._resolve_display_column(result, spec)
            if column:
                resolved.append((spec, column))
        if not resolved:
            return result

        display_cols = [
            column for spec, column in resolved
            if spec.get("aggregate", "display") == "display"
        ]
        aggregate_specs = [
            (spec, column) for spec, column in resolved
            if spec.get("aggregate", "display") != "display"
        ]
        if not aggregate_specs:
            return result[[c for c in display_cols if c in result.columns]]

        used_names = set(display_cols)
        named_aggs = {}
        for spec, column in aggregate_specs:
            aggregate = spec.get("aggregate", "display")
            output_name = self._unique_output_name(
                f"{aggregate}_{spec.get('column', column)}", used_names)
            named_aggs[output_name] = (column, aggregate.lower())

        if display_cols:
            grouped = result.groupby(display_cols, dropna=False).agg(**named_aggs).reset_index()
            return grouped[[*display_cols, *named_aggs.keys()]]

        values = {}
        for output_name, (column, aggregate) in named_aggs.items():
            values[output_name] = [getattr(result[column], aggregate)()]
        return pd.DataFrame(values)

    # ── Dirty tracking ────────────────────────────────────────────────

    @property
    def dirty(self) -> bool:
        return self._dirty

    def mark_clean(self):
        self._dirty = False

    def _schedule_save(self):
        if self._loading:
            return
        self._dirty = True
        self.config_changed.emit()

    # ── Run DataForge ────────────────────────────────────────────────

    def _run_forge(self):
        """Execute all source queries, then combine: Manual-mode DuckDB SQL
        when enabled, otherwise pandas merge + filters (the visual design)."""
        if not self._sources:
            QMessageBox.warning(self, "No Sources",
                                "Add at least one query object via the Objects button.")
            return

        manual_sql = self.sql_tab.manual_sql if self.sql_tab.manual_mode else ""
        if self.sql_tab.manual_mode and not manual_sql.strip():
            QMessageBox.warning(
                self, "Manual SQL Empty",
                "Manual mode is on but the SQL editor is empty.\n"
                "Type SQL in the SQL tab, or untick Manual mode.")
            return

        # Validate + snapshot sources on the GUI thread before going async.
        sources: list = []
        sqls: dict[str, str] = {}
        for name, sq in self._sources.items():
            if not sq.sql and not self._is_adhoc_source(sq):
                QMessageBox.warning(
                    self, "Missing SQL",
                    f"Query \"{name}\" has no SQL. Run and re-save it first.")
                return
            sqls[name] = sq.sql or f"Ad hoc source: {sq.source_design}"
            sources.append((name, sq))

        def work():
            # Slow part: run each source query off the GUI thread.
            t0 = time.time()
            datasets: dict[str, pd.DataFrame] = {}
            for name, sq in sources:
                datasets[name] = self._load_source_dataframe(sq)
            return datasets, time.time() - t0

        def on_success(payload):
            datasets, t_query = payload

            # Cache datasets so field picker can see them
            self._datasets.update(datasets)
            # Notify open dialog about data availability
            if self._queries_dialog and self._queries_dialog.isVisible():
                self._queries_dialog.update_data_status(set(self._datasets.keys()))

            # Manual mode: the hand-written DuckDB SQL replaces the visual
            # design (joins/filters/display) entirely.
            if manual_sql.strip():
                self._show_manual_results(datasets, sqls, manual_sql, t_query)
                return

            # Step 2: Apply pandas merge operations
            t1 = time.time()
            merge_ops = self.joins_tab.get_merge_ops()

            if merge_ops:
                # Execute merges in order
                result = None
                for op in merge_ops:
                    left_name = op["left"]
                    right_name = op["right"]
                    left_on = op["left_on"]
                    right_on = op["right_on"]
                    how = op["how"]

                    if not left_on or not right_on:
                        continue

                    left_df = result if result is not None else datasets.get(left_name)
                    right_df = datasets.get(right_name)

                    if left_df is None or right_df is None:
                        continue

                    result = pd.merge(
                        left_df, right_df,
                        left_on=left_on, right_on=right_on,
                        how=how, suffixes=(f"_{left_name}", f"_{right_name}"))

                if result is None:
                    # No valid merges — use first dataset
                    result = next(iter(datasets.values()))
            else:
                # No merges — use first dataset
                result = next(iter(datasets.values()))

            # Step 3: Apply pandas filters from filter tabs
            for tab in self._filter_tabs:
                result = self._apply_pandas_filters(result, tab)

            # Step 4: Apply display column selection
            if not self.display_tab.display_all:
                result = self._apply_display_columns(result)

            # Step 5: Apply max count
            max_count = self.txt_max_count.text().strip()
            if max_count.isdigit():
                result = result.head(int(max_count))

            t_print = time.time() - t1
            t_total = t_query + t_print

            # Update Display tab with available columns
            self.display_tab.set_columns(list(result.columns))

            # Show results
            self.results_tab.set_results(result)
            self.lbl_query_time.setText(f"Query time:  {fmt_time(t_query)}")
            self.lbl_print_time.setText(f"Merge time:  {fmt_time(t_print)}")
            self.lbl_total_time.setText(f"Total time:  {fmt_time(t_total)}")
            self.lbl_result_count.setText(f"Result count:   {len(result)}")

            # Update SQL tab: per-dataset SQL + the compiled Forge SQL
            self.sql_tab.set_datasets(sqls)
            self._refresh_forge_sql()

            # Generate Python code
            code = self._generate_python_code(sqls, merge_ops, max_count)
            self.code_tab.set_code(code)

            self.tab_widget.setCurrentWidget(self.results_tab)

        def on_error(exc):
            logger.error("DataForge execution failed: %s", exc)
            QMessageBox.warning(self, "DataForge Error", format_query_error(exc))

        run_query_async(
            owner=self,
            work=work,
            on_success=on_success,
            on_error=on_error,
            btn=self.btn_run,
            restore_text="Run\nForge",
            bar=self.bottom_bar,
        )

    def _show_manual_results(self, datasets: dict[str, pd.DataFrame],
                             sqls: dict[str, str], manual_sql: str,
                             t_query: float):
        """Run Manual-mode DuckDB SQL over the loaded Source tables and show it."""
        t1 = time.time()
        max_count = self.txt_max_count.text().strip()
        limit = int(max_count) if max_count.isdigit() else None
        try:
            res = run_manual_sql(datasets, manual_sql, limit=limit)
        except ForgeEngineError as exc:
            QMessageBox.warning(self, "Manual SQL Error", str(exc))
            return
        result = res.dataframe

        t_sql = time.time() - t1
        self.results_tab.set_results(result)
        self.lbl_query_time.setText(f"Query time:  {fmt_time(t_query)}")
        self.lbl_print_time.setText(f"SQL time:  {fmt_time(t_sql)}")
        self.lbl_total_time.setText(f"Total time:  {fmt_time(t_query + t_sql)}")
        self.lbl_result_count.setText(f"Result count:   {len(result)}")

        self.sql_tab.set_datasets(sqls)
        self._refresh_forge_sql()
        self.code_tab.set_code(
            self._generate_manual_python_code(sqls, manual_sql, limit))
        self.tab_widget.setCurrentWidget(self.results_tab)

    def _apply_pandas_filters(self, df: pd.DataFrame,
                              tab: ForgeFilterTab) -> pd.DataFrame:
        """Apply filter criteria from a ForgeFilterTab to a DataFrame."""
        from suiteview.audit.dynamic_query import collect_field_filters

        filters = collect_field_filters(tab.grid)
        for filt in filters:
            field_key = filt.get("field_key") or filt.get("key", "")
            col_name = _resolve_filter_column(
                df,
                field_key,
                filt.get("column") or field_key.rsplit(".", 1)[-1],
            )
            if not col_name:
                continue

            mode = filt.get("mode", "contains")
            value = filt.get("value", "")

            if mode == "contains" and value:
                df = df[df[col_name].astype(str).str.contains(
                    value, case=False, na=False)]
            elif mode == "regex" and value:
                df = df[df[col_name].astype(str).str.contains(
                    value, case=False, na=False, regex=True)]
            elif mode == "range":
                lo = filt.get("range_lo", filt.get("lo", ""))
                hi = filt.get("range_hi", filt.get("hi", ""))
                if lo or hi:
                    df = df[_series_matches_range(df[col_name], lo, hi, col_name)]
            elif mode == "list":
                items = filt.get("list_values", filt.get("items", []))
                if items:
                    df = df[df[col_name].astype(str).isin(items)]

        return df

    # ── Visual design → DuckDB SQL (Phase 3) ─────────────────────────

    def _source_for_field_key(self, field_key: str) -> tuple[str, str]:
        """Split a 'source.column' field key into (source, column).

        Source names may themselves contain dots, so match known Source
        names by prefix first; fall back to splitting on the last dot.
        Returns ("", field_key) when no source can be identified.
        """
        for name in self._sources:
            if field_key.startswith(name + "."):
                return name, field_key[len(name) + 1:]
        if "." in field_key:
            source, column = field_key.rsplit(".", 1)
            return source, column
        return "", field_key

    def _engine_schemas(self) -> dict[str, list[str]]:
        """Best-known columns per Source: loaded data first, else definition."""
        schemas: dict[str, list[str]] = {}
        for name, sq in self._sources.items():
            if name in self._datasets:
                schemas[name] = list(self._datasets[name].columns)
            else:
                schemas[name] = list(sq.result_columns or [])
        return schemas

    def _outputs_config(self) -> list[dict]:
        """Display-tab rows as engine-shaped output dicts (for the config)."""
        if self.display_tab.display_all:
            return []
        outputs: list[dict] = []
        for spec in self.display_tab.get_display_columns():
            source, column = self._source_for_field_key(spec.get("field_key", ""))
            if source not in self._sources or not column:
                continue
            outputs.append({"source": source, "column": column,
                            "agg": spec.get("aggregate", "display")})
        return outputs

    def _engine_outputs(self) -> list[OutputColumn] | None:
        """OutputColumns for compilation, or None for select-everything."""
        outputs = [OutputColumn(source=o["source"], column=o["column"],
                                agg=o["agg"])
                   for o in self._outputs_config()]
        return outputs or None

    def _engine_filter_specs(self) -> list[FilterSpec]:
        """Filter-tab criteria as Source-scope engine FilterSpecs.

        Note the scope difference from the pandas run path: the engine
        applies these inside each Source's CTE (before the join), which is
        the design-correct semantics (DATAFORGE_DESIGN.md §3); the pandas
        path filters the merged result. A combo pick compiles to equals.
        """
        from suiteview.audit.dynamic_query import collect_field_filters
        specs: list[FilterSpec] = []
        for tab in self._filter_tabs:
            for filt in collect_field_filters(tab.grid):
                field_key = filt.get("field_key") or filt.get("key", "")
                source, column = self._source_for_field_key(field_key)
                if source not in self._sources or not column:
                    continue
                mode = filt.get("mode", "contains")
                specs.append(FilterSpec(
                    source=source,
                    column=column,
                    mode="equals" if mode == "combo" else mode,
                    value=filt.get("value", ""),
                    lo=str(filt.get("range_lo", filt.get("lo", ""))),
                    hi=str(filt.get("range_hi", filt.get("hi", ""))),
                    items=tuple(filt.get("list_values", filt.get("items", []))),
                ))
        return specs

    def _engine_joins(self) -> list[JoinSpec]:
        """Canvas relationships as engine JoinSpecs."""
        return [
            JoinSpec(
                left_source=j["left_source"],
                right_source=j["right_source"],
                left_keys=tuple(j["left_keys"]),
                right_keys=tuple(j["right_keys"]),
                how=j.get("how", "inner"),
            )
            for j in self.joins_tab.to_config_joins()
        ]

    def _compile_visual_sql(self) -> str:
        """Compile the current visual design into one DuckDB statement.

        Physical table names default to the Source names, so the returned
        SQL is exactly what Manual mode runs (the Visual→Manual flip).
        Raises ForgeEngineError when the design doesn't compile.
        """
        schemas = self._engine_schemas()
        outputs = self._engine_outputs()
        # A Source whose columns aren't known yet (never run, no saved
        # columns) would reject its outputs — trust the display rows.
        unknown = {s for s, cols in schemas.items() if not cols}
        for oc in outputs or []:
            if oc.source in unknown and oc.column not in schemas[oc.source]:
                schemas[oc.source].append(oc.column)

        max_count = self.txt_max_count.text().strip()
        sql, _ = compile_forge_sql(
            schemas,
            self._engine_joins(),
            filters=self._engine_filter_specs(),
            outputs=outputs,
            limit=int(max_count) if max_count.isdigit() else None,
        )
        return sql

    def _refresh_forge_sql(self):
        """Recompile the visual design and update the SQL tab's Forge view."""
        if not self._sources:
            self.sql_tab.set_forge_sql(
                "-- Add Sources via the Queries button, then the compiled\n"
                "-- DuckDB SQL for the whole Forge appears here.")
            return
        try:
            self.sql_tab.set_forge_sql(self._compile_visual_sql())
        except Exception as exc:
            self.sql_tab.set_forge_sql(
                "-- The visual design doesn't compile yet:\n-- "
                + str(exc).replace("\n", "\n-- ")
                + "\n-- Fix the design, or write your own SQL in Manual mode.")

    # ── Python code generation ───────────────────────────────────────

    def _generate_load_code(self, sqls: dict[str, str],
                            extra_imports: tuple[str, ...] = ()) -> list[str]:
        """Imports + per-Source dataset-load lines shared by both generators."""
        lines = [
            "import pandas as pd",
        ]
        lines.extend(extra_imports)
        if any(not self._is_adhoc_source(sq) for sq in self._sources.values()):
            lines.append("import pyodbc")
        lines.extend([
            "",
            "# ── Load datasets ──────────────────────────────────────────",
        ])

        for name, sq in self._sources.items():
            safe = name.replace('"', '\\"')
            lines.extend(["", f'# Dataset: {safe}'])
            if self._is_adhoc_source(sq):
                lines.extend(self._generate_adhoc_load_code(name, sq))
            else:
                dsn = sq.dsn.replace('"', '\\"')
                sql = sqls.get(name, sq.sql).replace('"""', '\\"""')
                lines.extend([
                    f'conn_{_var(name)} = pyodbc.connect("DSN={dsn}", autocommit=True)',
                    f'df_{_var(name)} = pd.read_sql("""',
                    f'{sql}',
                    f'""", conn_{_var(name)})',
                    f'conn_{_var(name)}.close()',
                ])
        return lines

    def _generate_manual_python_code(self, sqls: dict[str, str],
                                     manual_sql: str,
                                     limit: int | None) -> str:
        """Generate runnable Python that reproduces a Manual-mode run."""
        lines = self._generate_load_code(sqls, extra_imports=("import duckdb",))
        lines.extend([
            "",
            "# ── Run Manual SQL with DuckDB ─────────────────────────────",
            "con = duckdb.connect()",
        ])
        for name in self._sources:
            safe = name.replace('"', '\\"')
            lines.append(f'con.register("{safe}", df_{_var(name)})')
        lines.extend([
            'result = con.execute("""',
            manual_sql.replace('"""', '\\"""'),
            '""").df()',
            "con.close()",
        ])
        if limit:
            lines.append(f"result = result.head({limit})")
        lines.extend(["", "print(result)"])
        return "\n".join(lines)

    def _generate_python_code(self, sqls: dict[str, str],
                              merge_ops: list[dict],
                              max_count: str) -> str:
        """Generate real, runnable Python code that reproduces the DataForge."""
        lines = self._generate_load_code(sqls)

        if merge_ops:
            lines.extend([
                "",
                "# ── Merge datasets ─────────────────────────────────────────",
            ])
            for i, op in enumerate(merge_ops):
                left = op["left"]
                right = op["right"]
                left_on = op["left_on"]
                right_on = op["right_on"]
                how = op["how"]
                if i == 0:
                    lines.append(
                        f'result = pd.merge(df_{_var(left)}, df_{_var(right)}, '
                        f'left_on="{left_on}", right_on="{right_on}", '
                        f'how="{how}")')
                else:
                    lines.append(
                        f'result = pd.merge(result, df_{_var(right)}, '
                        f'left_on="{left_on}", right_on="{right_on}", '
                        f'how="{how}")')
        else:
            first_name = next(iter(self._sources)) if self._sources else "data"
            lines.extend([
                "",
                f"result = df_{_var(first_name)}",
            ])

        # Filters
        filter_code = self._generate_filter_code()
        if filter_code:
            lines.extend([
                "",
                "# ── Apply filters ──────────────────────────────────────────",
            ])
            lines.extend(filter_code)

        # Max count
        if max_count.isdigit():
            lines.extend([
                "",
                f"result = result.head({max_count})",
            ])

        lines.extend([
            "",
            "print(f'Result: {result.shape[0]} rows x {result.shape[1]} columns')",
            "print(result.head(20))",
        ])

        return "\n".join(lines)

    def _generate_adhoc_load_code(self, name: str, sq: QDefinition) -> list[str]:
        """Generate pandas load code for a DataForge ad hoc file source."""
        metadata = getattr(sq, "query_object_source_metadata", {}) or {}
        path = metadata.get("path", "")
        var_name = f"df_{_var(name)}"
        source_type = sq.source_design or "csv"
        path_arg = _str_literal(path)

        if source_type == "excel":
            sheet_name = metadata.get("sheet_name", 0)
            lines = [f"{var_name} = pd.read_excel({path_arg}, sheet_name={sheet_name!r})"]
        elif source_type == "fixed_width":
            columns = metadata.get("columns", [])
            names = [str(column.get("name", "")) for column in columns]
            colspecs = [
                (int(column.get("start", 0) or 0) - 1,
                 int(column.get("start", 0) or 0) - 1 + int(column.get("width", 0) or 0))
                for column in columns
            ]
            lines = [
                f"{var_name} = pd.read_fwf(",
                f"    {path_arg},",
                f"    colspecs={colspecs!r},",
                f"    names={names!r},",
                "    header=None,",
                f"    encoding={metadata.get('encoding', 'utf-8-sig')!r},",
                f"    skiprows={int(metadata.get('skip_rows', 0) or 0)!r},",
                ")",
            ]
        else:
            has_header = bool(metadata.get("has_header", True))
            column_names = [str(name).strip() for name in metadata.get("column_names", []) if str(name).strip()]
            lines = [
                f"{var_name} = pd.read_csv(",
                f"    {path_arg},",
                f"    sep={metadata.get('delimiter', ',')!r},",
                f"    header={0 if has_header else None!r},",
                f"    encoding={metadata.get('encoding', 'utf-8-sig')!r},",
                f"    skiprows={int(metadata.get('skip_rows', 0) or 0)!r},",
                ")",
            ]
            if column_names:
                lines.append(f"{var_name}.columns = {column_names!r}")

        selected_columns = [column for column in sq.result_columns if column]
        if selected_columns:
            lines.append(f"{var_name} = {var_name}[[c for c in {selected_columns!r} if c in {var_name}.columns]]")
        return lines

    def _generate_filter_code(self) -> list[str]:
        """Generate pandas filter code from filter tabs."""
        from suiteview.audit.dynamic_query import collect_field_filters
        lines = []
        filter_lines = []
        needs_range_helper = False
        for tab in self._filter_tabs:
            filters = collect_field_filters(tab.grid)
            for filt in filters:
                field_key = filt.get("field_key") or filt.get("key", "")
                col = filt.get("column") or field_key.rsplit(".", 1)[-1]
                if not col:
                    continue
                mode = filt.get("mode", "contains")
                value = filt.get("value", "")

                if mode == "contains" and value:
                    filter_lines.append(
                        f'result = result[result["{col}"].astype(str)'
                        f'.str.contains("{value}", case=False, na=False)]')
                elif mode == "regex" and value:
                    filter_lines.append(
                        f'result = result[result["{col}"].astype(str)'
                        f'.str.contains(r"{value}", case=False, na=False)]')
                elif mode == "range":
                    lo = filt.get("range_lo", filt.get("lo", ""))
                    hi = filt.get("range_hi", filt.get("hi", ""))
                    if lo or hi:
                        needs_range_helper = True
                        filter_lines.append(
                            f'result = result[_series_matches_range(result["{col}"], "{lo}", "{hi}", "{col}")]')
                elif mode == "list":
                    items = filt.get("list_values", filt.get("items", []))
                    if items:
                        filter_lines.append(
                            f'result = result[result["{col}"].astype(str)'
                            f'.isin({items!r})]')
        if needs_range_helper:
            lines.extend([
                "def _series_matches_range(series, lo='', hi='', column=''):",
                "    mask = pd.Series(True, index=series.index)",
                "    non_null = series.dropna()",
                "    if non_null.empty:",
                "        return mask",
                "    lo_text = str(lo).strip()",
                "    hi_text = str(hi).strip()",
                "    sample_values = [str(value) for value in non_null.head(10)]",
                "    looks_temporal = (",
                "        pd.api.types.is_datetime64_any_dtype(series)",
                "        or any(marker in column.lower() for marker in ('date', 'time', 'dt'))",
                "        or any(any(sep in value for sep in ('/', '-', ':')) for value in [lo_text, hi_text, *sample_values])",
                "    )",
                "    if looks_temporal:",
                "        date_values = pd.to_datetime(series, errors='coerce')",
                "        lo_dt = pd.to_datetime(lo_text, errors='coerce') if lo_text else pd.NaT",
                "        hi_dt = pd.to_datetime(hi_text, errors='coerce') if hi_text else pd.NaT",
                "        if date_values.notna().any() and ((lo_text and not pd.isna(lo_dt)) or (hi_text and not pd.isna(hi_dt))):",
                "            if lo_text:",
                "                mask &= date_values >= lo_dt",
                "            if hi_text:",
                "                mask &= date_values <= hi_dt",
                "            return mask & date_values.notna()",
                "    numeric_values = pd.to_numeric(series, errors='coerce')",
                "    if numeric_values.notna().any():",
                "        if lo_text:",
                "            try:",
                "                mask &= numeric_values >= float(lo_text.replace(',', ''))",
                "            except ValueError:",
                "                pass",
                "        if hi_text:",
                "            try:",
                "                mask &= numeric_values <= float(hi_text.replace(',', ''))",
                "            except ValueError:",
                "                pass",
                "        return mask & numeric_values.notna()",
                "    text_values = series.astype(str)",
                "    if lo_text:",
                "        mask &= text_values >= lo_text",
                "    if hi_text:",
                "        mask &= text_values <= hi_text",
                "    return mask",
                "",
            ])
        lines.extend(filter_lines)
        return lines

    # ── Save/Delete DataForge ────────────────────────────────────────

    def _save_or_update(self):
        if self._saved_forge_name:
            self._save_update()
        else:
            self._save_forge()

    def _save_update(self):
        name = self._saved_forge_name
        if not name:
            return
        forge = DataForge(
            name=name,
            sources=self._dataforge_sources_for_save(name),
            config=self.get_config(),
        )
        df_store.save_forge(forge)
        self._dirty = False
        self.forge_saved.emit(forge)
        self._update_forge_heading()
        QMessageBox.information(self, "DataForge Saved",
                                f"DataForge \"{name}\" updated.")

    def _save_forge(self):
        name, ok = QInputDialog.getText(
            self, "Save DataForge", "DataForge name:",
            text=self._saved_forge_name or "")
        if not ok or not name.strip():
            return
        name = name.strip()
        previous_saved_name = self._saved_forge_name

        if df_store.forge_exists(name):
            reply = QMessageBox.question(
                self, "Overwrite?",
                f"A DataForge named \"{name}\" already exists.\nOverwrite?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No)
            if reply != QMessageBox.StandardButton.Yes:
                return
            if name != previous_saved_name:
                self._delete_existing_forge_records(name)

        self._promote_unsaved_source_names(name)
        self._saved_forge_name = name
        self.forge_name = f"⚙ {name}"
        forge = DataForge(
            name=name,
            sources=self._dataforge_sources_for_save(name),
            config=self.get_config(),
        )
        df_store.save_forge(forge)
        self._dirty = False
        self._update_forge_heading()
        self.forge_saved.emit(forge)
        QMessageBox.information(self, "DataForge Saved",
                                f"DataForge \"{name}\" saved.")

    def _delete_existing_forge_records(self, forge_name: str) -> None:
        df_store.delete_forge(forge_name)
        for qd in qdef_store.list_qdefs(forge_name=forge_name):
            self._delete_query_copy_records(qd.name, forge_name)
        for obj in query_object_store.list_objects():
            dataforge = (obj.config or {}).get("dataforge", {})
            if dataforge.get("forge_name") == forge_name:
                self._delete_query_copy_records(obj.name, forge_name)

    def _dataforge_sources_for_save(self, forge_name: str) -> list[DataForgeSource]:
        """Persist source definitions and return DataForge source records."""
        sources: list[DataForgeSource] = []
        for source_name, qd in list(self._sources.items()):
            obj = query_object_store.load_object(qd.name)
            if obj is not None:
                qd = qdefinition_from_query_object(obj)
                self._sources[source_name] = qd
            qd.forge_name = forge_name
            source_label = self._source_label_for_browser(qd, source_name)
            qd_config = dict(getattr(qd, "query_object_config", {}) or {})
            qd_config["dataforge"] = {
                "forge_name": forge_name,
                "source_name": source_label,
            }
            qd.query_object_config = qd_config
            qdef_store.save_qdef(qd)
            if obj is None:
                obj = object_from_qdefinition(qd)
            obj.config = dict(qd_config)
            obj.source_design = obj.source_design or source_label
            query_object_store.save_object(obj)
            definition = obj.to_dict()
            sources.append(DataForgeSource(
                query_name=qd.name or source_name,
                alias="",
                definition=definition,
            ))
        return sources

    @staticmethod
    def _source_label_for_browser(qd: QDefinition, fallback: str) -> str:
        config = getattr(qd, "query_object_config", {}) or {}
        dataforge = config.get("dataforge", {}) if isinstance(config, dict) else {}
        source_name = str(dataforge.get("source_name", "")).strip()
        if source_name:
            return source_name
        return DataForgeGroup._source_original_name(qd, fallback)

    def _delete_forge(self):
        name = self._saved_forge_name
        if not name:
            QMessageBox.information(self, "Not Saved",
                                    "This DataForge has not been saved yet.")
            return
        reply = QMessageBox.question(
            self, "Delete DataForge",
            f"Delete DataForge \"{name}\"?\nThis cannot be undone.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No)
        if reply != QMessageBox.StandardButton.Yes:
            return
        df_store.delete_forge(name)
        self._saved_forge_name = ""
        self._dirty = False
        self._update_forge_heading()
        self.forge_deleted.emit(name)

    def _update_forge_heading(self):
        name = self._saved_forge_name.strip() or "(new)"
        self._lbl_name.setText(f"Forge: {name}")
        self.btn_save.setVisible(bool(self._saved_forge_name.strip()))
        self.btn_save_as.setVisible(True)
        self.btn_new_forge.setVisible(True)

    # ── State persistence ────────────────────────────────────────────

    def get_config(self) -> dict:
        max_count = self.txt_max_count.text().strip()
        return {
            "name": self.forge_name,
            "sources": list(self._sources.keys()),
            "max_count": self.txt_max_count.text(),
            "filter_tabs": [t.get_state() for t in self._filter_tabs],
            "joins_tab": self.joins_tab.get_state(),
            "display_tab": self.display_tab.get_state(),
            # Engine-shaped views of the design, so forge_runtime can run a
            # saved Forge headless over Snapshots (run_saved_forge reads
            # joins/outputs/limit — see WORK_LAPTOP_SPEC §1.5/§3b).
            "joins": self.joins_tab.to_config_joins(),
            "outputs": self._outputs_config(),
            "limit": int(max_count) if max_count.isdigit() else None,
            # Manual mode (Phase 3): hand-written DuckDB SQL, when enabled.
            "sql_mode": "manual" if self.sql_tab.manual_mode else "visual",
            "manual_sql": self.sql_tab.manual_sql,
        }

    def set_config(self, config: dict):
        self._loading = True
        try:
            self.txt_max_count.setText(config.get("max_count", "25"))

            # Restore sources
            for name in config.get("sources", []):
                sq = qdef_store.load_qdef(name, forge_name=self._saved_forge_name)
                if not sq:
                    sq = qdef_store.load_qdef(name)  # fallback: search all
                if not sq:
                    obj = query_object_store.load_object(name)
                    if obj:
                        sq = qdefinition_from_query_object(obj)
                if sq:
                    self._sources[name] = sq
            self.joins_tab.update_queries(list(self._sources.keys()),
                                         self._query_columns_map())

            # Restore filter tabs
            tab_states = config.get("filter_tabs", [])
            if tab_states:
                while len(self._filter_tabs) > 1:
                    tab = self._filter_tabs.pop()
                    idx = self.tab_widget.indexOf(tab)
                    if idx >= 0:
                        self.tab_widget.removeTab(idx)
                    tab.deleteLater()
                if self._filter_tabs:
                    self._filter_tabs[0].set_state(tab_states[0])
                    name = tab_states[0].get("tab_name", "Filter")
                    idx = self.tab_widget.indexOf(self._filter_tabs[0])
                    if idx >= 0:
                        self.tab_widget.setTabText(idx, name)
                for ts in tab_states[1:]:
                    tab = self._add_filter_tab(ts.get("tab_name", "Filter"))
                    tab.set_state(ts)

            # Restore joins
            joins_state = config.get("joins_tab", {})
            if joins_state:
                self.joins_tab.set_state(joins_state)

            # Restore display
            display_state = config.get("display_tab", {})
            if display_state:
                self.display_tab.set_state(display_state)

            # Restore Manual mode (after sources/joins so a compile works)
            self.sql_tab.set_manual_state(
                config.get("sql_mode") == "manual",
                config.get("manual_sql", ""))

        finally:
            self._loading = False
            self._dirty = False


def _var(name: str) -> str:
    """Convert a query name to a valid Python variable suffix."""
    import re
    return re.sub(r'[^a-zA-Z0-9_]', '_', name).strip('_').lower() or "data"
