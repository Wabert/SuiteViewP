"""
DynamicQuery — a full mode (tab set + footer) for user-created audit groups.

Each DynamicQuery manages:
  - A QTabWidget with an initial "All" tab + Results + SQL tabs
  - A bottom bar with Tables, Clear All, timing, max count, Run Audit
  - Dynamic field placement on tabs via drag-drop from Tables dialog
  - SQL building from placed FieldRow widgets
"""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass

import pandas as pd
from PyQt6.QtCore import Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QFont
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QTabWidget, QLabel, QPushButton, QMessageBox,
    QInputDialog, QScrollArea, QDialog,
)

from .tabs.field_row import FieldRow, FieldGrid
from .tabs.results_tab import ResultsTab
from .tabs.sql_tab import SqlTab
from .tabs.select_tab import SelectTab
from .tabs.visual_joins_tab import VisualJoinsTab as JoinsTab
from .tabs.common_tables_tab import CommonTablesTab
from .tabs.build_sql_tab import BuildSqlTab
from .tabs.build_sql_results_tab import BuildSqlResultsTab
from .tabs._styles import _FONT
from .query_builder_menu import query_builder_menu
from .sql_helpers import fmt_time
from .dynamic_query import (
    DB2,
    DUCKDB,
    build_common_table_cte,
    build_dynamic_sql,
    build_join_sql,
    choose_primary_table,
    find_outer_join_ambiguity,
    order_join_infos,
    outer_join_ambiguity,
    split_field_key,
)
from .query_sources import (
    file_source_label,
    is_file_token,
    is_list_token,
    is_local_token,
    list_token,
    resolve_file_token,
)
from .federated_query import FederatedPlan, execute_federated_plan, plan_federated_query
from .policy_list import COMPANY_COLUMN, POLICY_COLUMN, SYSTEM_COLUMN, PolicyList
from .dialogs.tables_dialog import TablesDialog, FIELD_DRAG_MIME
from .ui.bottom_bar import AuditBottomBar, FOOTER_BG
from .query_runner import (
    run_button_context,
    execute_odbc_query,
    execute_odbc_query_with_types,
    run_query_async,
    format_query_error,
)
from suiteview.core.odbc_utils import detect_dialect

logger = logging.getLogger(__name__)

BAS_POL_TABLE = "DB2TAB.LH_BAS_POL"

_FONT_LABEL = QFont("Segoe UI", 9)
_FONT_BOLD = QFont("Segoe UI", 9, QFont.Weight.Bold)

_RUN_BTN_STYLE = (
    "QPushButton { background-color: #C00000; color: white; border: 1px solid #900;"
    " border-radius: 3px; }"
    "QPushButton:hover { background-color: #E00000; }"
)

_CLEAR_BTN_STYLE = (
    "QPushButton { background-color: #1E5BA8; color: white;"
    " border: 1px solid #14407A; border-radius: 2px;"
    " padding: 1px 8px; font-size: 9pt; }"
    "QPushButton:hover { background-color: #2A6BC4; }"
)

_SAVE_QUERY_BTN_STYLE = (
    "QPushButton { background-color: #0A2A5C; color: #D4AF37;"
    " border: 2px solid #D4AF37; border-radius: 3px;"
    " padding: 1px 4px; font-size: 8pt; font-weight: bold; }"
    "QPushButton:hover { background-color: #123C69; color: #F4D03F; }"
)

_TABLES_BTN_STYLE = (
    "QPushButton { background-color: #E8F0FB; color: #1E5BA8;"
    " border: 1px solid #1E5BA8; border-radius: 3px;"
    " padding: 2px 10px; font-size: 9pt; font-weight: bold; }"
    "QPushButton:hover { background-color: #C5D8F5; }"
)


@dataclass
class _PreparedQuery:
    """SQL text for the SQL tab / save, plus the federated plan when files join in."""

    sql: str
    plan: FederatedPlan | None


def _detect_widget_mode(type_name: str) -> str:
    """Auto-detect FieldRow mode based on SQL type name."""
    t = type_name.upper()
    if any(kw in t for kw in ("INT", "SMALLINT", "BIGINT", "DECIMAL",
                               "NUMERIC", "FLOAT", "DOUBLE", "REAL")):
        return "range"
    if any(kw in t for kw in ("DATE", "TIME", "TIMESTAMP")):
        return "range"
    return "contains"


class DynamicTab(QScrollArea):
    """A single criteria tab for a dynamic query — wraps a FieldGrid."""

    def __init__(self, tab_name: str = "All", dsn: str = "", parent=None):
        super().__init__(parent)
        self.tab_name = tab_name
        self.dsn = dsn
        # Owner hooks: the source (DSN or file:<id>) of a table, and a callback
        # when a field from a table is placed on this tab.
        self.source_for = None
        self.on_field_placed = None
        self.setWidgetResizable(True)

        self.grid = FieldGrid(columns=2)
        self.setWidget(self.grid)

        # Accept drops from the Tables dialog
        self.setAcceptDrops(True)
        self.grid._canvas.setAcceptDrops(True)
        # Override canvas drop events to handle external field drops
        self._orig_canvas_dragEnter = self.grid._canvas.dragEnterEvent
        self._orig_canvas_dragMove = self.grid._canvas.dragMoveEvent
        self._orig_canvas_drop = self.grid._canvas.dropEvent
        self.grid._canvas.dragEnterEvent = self._canvas_dragEnterEvent
        self.grid._canvas.dragMoveEvent = self._canvas_dragMoveEvent
        self.grid._canvas.dropEvent = self._canvas_dropEvent

    def _canvas_dragEnterEvent(self, event):
        if event.mimeData().hasFormat(FIELD_DRAG_MIME):
            event.acceptProposedAction()
        else:
            self._orig_canvas_dragEnter(event)

    def _canvas_dragMoveEvent(self, event):
        if event.mimeData().hasFormat(FIELD_DRAG_MIME):
            event.acceptProposedAction()
        else:
            self._orig_canvas_dragMove(event)

    def _canvas_dropEvent(self, event):
        if event.mimeData().hasFormat(FIELD_DRAG_MIME):
            data = bytes(event.mimeData().data(FIELD_DRAG_MIME)).decode("utf-8")
            pos = event.position().toPoint()
            y_offset = 0
            # Support multi-field drops (newline-separated)
            for line in data.split("\n"):
                line = line.strip()
                if not line:
                    continue
                parts = line.split("|", 3)
                if len(parts) == 4:
                    table, column, type_name, display = parts
                    self._add_field_at(table, column, type_name, display,
                                       pos.x(), pos.y() + y_offset)
                    y_offset += 36  # stack multiple fields vertically
            event.acceptProposedAction()
        else:
            self._orig_canvas_drop(event)

    def _row_source(self, table: str) -> str:
        return self.source_for(table) if self.source_for is not None else self.dsn

    def _placed(self, table: str):
        if self.on_field_placed is not None:
            self.on_field_placed(table)

    def _add_field_at(self, table: str, column: str, type_name: str,
                      display: str, x: int, y: int):
        """Add a FieldRow at a specific position."""
        key = f"{table}.{column}"
        if self.grid.field(key) is not None:
            return  # already placed

        row = FieldRow(
            field_key=key,
            label_text=display or column,
            placeholder=column,
            registry_info=(table, column, display or column, self._row_source(table)),
        )
        mode = _detect_widget_mode(type_name)
        self.grid.add_field(row)
        row.set_mode_idx(["contains", "regex", "combo", "list", "range"].index(mode))
        self.grid.move_field(key, x, y)
        self._placed(table)

    def add_field_auto(self, table: str, column: str, type_name: str,
                       display: str):
        """Auto-place a field below the last placed field."""
        key = f"{table}.{column}"
        if self.grid.field(key) is not None:
            return  # already placed

        row = FieldRow(
            field_key=key,
            label_text=display or column,
            placeholder=column,
            registry_info=(table, column, display or column, self._row_source(table)),
        )
        mode = _detect_widget_mode(type_name)
        # Compute position below the last field
        if self.grid._rows:
            last = self.grid._rows[-1]
            last_pos = self.grid._positions.get(last.field_key, (4, 0))
            last_h = self.grid._sizes.get(last.field_key, (0, 0))[1] or last.sizeHint().height()
            next_y = self.grid._snap(last_pos[1] + last_h + 4)
            self.grid._positions[key] = (last_pos[0], next_y)
        self.grid.add_field(row)
        row.set_mode_idx(["contains", "regex", "combo", "list", "range"].index(mode))
        self._placed(table)

    def remove_field(self, key: str):
        """Remove a FieldRow by key."""
        row = self.grid.field(key)
        if row is None:
            return
        self.grid._rows.remove(row)
        del self.grid._field_map[key]
        self.grid._positions.pop(key, None)
        self.grid._sizes.pop(key, None)
        if row in self.grid._selection:
            self.grid._selection.remove(row)
        row.setParent(None)
        row.deleteLater()
        self.grid._update_canvas_bounds()

    def get_state(self) -> dict:
        return {
            "tab_name": self.tab_name,
            "grid": self.grid.get_state(),
        }

    def set_state(self, state: dict):
        self.tab_name = state.get("tab_name", self.tab_name)
        grid_state = state.get("grid", {})
        if grid_state:
            self.grid.set_state(grid_state)


class DynamicQuery(QWidget):
    """Complete mode widget for a user-created dynamic query.

    Contains tab widget + bottom bar. Meant to be shown/hidden by AuditWindow
    like cyberlife/tai modes.
    """
    config_changed = pyqtSignal()
    common_tables_changed = pyqtSignal(dict)  # {name: [(col, type), ...]}
    query_saved = pyqtSignal(object)     # SavedQuery
    query_deleted = pyqtSignal(str)      # query name deleted
    new_query_requested = pyqtSignal()
    add_tables_requested = pyqtSignal(str)  # "odbc" / "files" from the Joins canvas
    sources_changed = pyqtSignal()          # a table was added here (e.g. pasted list)

    def __init__(self, name: str, dsn: str, tables: list[str],
                 display_names: dict[str, str] | None = None,
                 parent=None, saved_query_name: str = ""):
        super().__init__(parent)
        self.query_name = name
        self.dsn = dsn
        self.dialect = detect_dialect(dsn)
        self.tables = list(tables)  # mutable — tables can be added/removed
        self.display_names: dict[str, str] = display_names or {}
        self.pinned_tables: list[str] = []
        # File Source datasets (file:<id>) and pasted lists (list:<table>) in
        # this query: table → token. Every other table belongs to self.dsn.
        self.table_sources: dict[str, str] = {}
        # Pasted lists' data: table → {"columns": [...], "rows": [[...], ...]}.
        self.inline_tables: dict[str, dict] = {}

        # Temp group tracking: non-empty means this is a loaded saved query
        self._saved_query_name = saved_query_name
        self._is_temp = bool(saved_query_name)

        self._tabs_dialog: TablesDialog | None = None
        self._loading = False  # suppress auto-save during set_config

        # ── Auto-save debounce timer (must exist before _build_ui) ───
        self._save_timer = QTimer(self)
        self._save_timer.setSingleShot(True)
        self._save_timer.setInterval(800)
        self._save_timer.timeout.connect(self.config_changed)
        # Design-time "how will each table be fetched" badges on the canvas.
        self._plan_timer = QTimer(self)
        self._plan_timer.setSingleShot(True)
        self._plan_timer.setInterval(250)
        self._plan_timer.timeout.connect(self.refresh_plan_badges)

        self._build_ui()

        # Wire child signals for auto-save
        self.joins_tab.state_changed.connect(self._schedule_save)
        self.joins_tab.state_changed.connect(self._schedule_plan_refresh)
        self.joins_tab.add_tables_requested.connect(self.add_tables_requested)
        self.joins_tab.paste_policy_list_requested.connect(self.paste_policy_list)
        self.common_tables_tab.state_changed.connect(self._schedule_save)
        self.common_tables_tab.state_changed.connect(self._sync_common_tables_to_joins)
        self.select_tab.state_changed.connect(self._schedule_save)
        self.select_tab.state_changed.connect(self._schedule_plan_refresh)
        self.txt_max_count.textChanged.connect(self._schedule_save)
        # Wire existing criteria tabs
        for tab in self._criteria_tabs:
            tab.grid.state_changed.connect(self._schedule_save)

    def _schedule_plan_refresh(self, *_args):
        self._plan_timer.start()

    def set_source_dsn(self, dsn: str):
        """Update this visual query to use the selected SQL Assist DSN.

        File datasets keep their own ``file:<id>`` source; only tables that
        belonged to the previous connection move to the new one.
        """
        dsn = (dsn or "").strip()
        if not dsn or dsn == self.dsn:
            return
        previous_dsn = self.dsn
        if is_file_token(previous_dsn) and not is_file_token(dsn):
            # A file-only query gaining a database: its tables stay file tables.
            for table in self._known_tables():
                if table not in self._common_table_names():
                    self.table_sources.setdefault(table, previous_dsn)
            self._push_local_tables()
        self.dsn = dsn
        self.dialect = detect_dialect(dsn)
        self.joins_tab.set_dsn(dsn)
        for tab in self._criteria_tabs:
            tab.dsn = dsn
            for row in tab.grid._rows:
                if not row._registry_info or len(row._registry_info) < 3:
                    continue
                current_dsn = row._registry_info[3] if len(row._registry_info) > 3 else ""
                if current_dsn and current_dsn != previous_dsn:
                    continue
                table, column, display = row._registry_info[:3]
                if table in self.table_sources:
                    continue
                row._registry_info = (table, column, display, dsn)
        self._schedule_save()

    # ── Table sources (database tables + file datasets + pasted lists) ──

    def source_for(self, table: str) -> str:
        """The source of ``table``: its ``file:``/``list:`` token, else the query DSN."""
        return self.table_sources.get(table, self.dsn)

    def _push_local_tables(self):
        self.joins_tab.set_local_tables(self.table_sources, self.inline_tables)

    def set_table_sources(self, table_sources: dict[str, str]):
        """File datasets / pasted lists in this query (table → token) from SQL Assist."""
        self.table_sources = {
            table: token for table, token in (table_sources or {}).items()
            if table and is_local_token(token)
        }
        # A pasted list removed from SQL Assist takes its data with it.
        self.inline_tables = {
            table: data for table, data in self.inline_tables.items()
            if is_list_token(self.table_sources.get(table, ""))
        }
        self._push_local_tables()
        self._sync_tables_to_joins()
        self._schedule_plan_refresh()
        self._schedule_save()

    # ── Pasted policy lists ──────────────────────────────────────────

    def paste_policy_list(self, text: str | None = None) -> str:
        """Paste a policy list from the clipboard (or ``text``); returns its table name."""
        from .dialogs.policy_list_dialog import PolicyListDialog

        dialog = PolicyListDialog(
            taken_names=set(self._known_tables()) | self._common_table_names(),
            can_join_bas_pol=self._can_join_bas_pol(),
            text=text,
            parent=self,
        )
        if dialog.exec() != QDialog.DialogCode.Accepted or dialog.result_list() is None:
            return ""
        return self.add_policy_list(dialog.table_name(), dialog.result_list(),
                                    join_to_bas_pol=dialog.join_to_bas_pol())

    def _can_join_bas_pol(self) -> bool:
        # UNKNOWN: the DSN isn't registered on this machine; a wrong guess fails
        # loudly at run time, never silently.
        return (bool(self.dsn) and not is_local_token(self.dsn)
                and self.dialect in (DB2, "UNKNOWN"))

    def add_policy_list(self, name: str, policy_list: PolicyList, *,
                        join_to_bas_pol: bool) -> str:
        """Add a normalized policy list as a table, optionally joined to LH_BAS_POL."""
        self.inline_tables[name] = {
            "columns": list(policy_list.columns),
            "rows": [list(row) for row in policy_list.rows],
        }
        self.table_sources[name] = list_token(name)
        for table in ([name, BAS_POL_TABLE] if join_to_bas_pol else [name]):
            if table not in self.tables:
                self.tables.append(table)
            if table not in self.pinned_tables:
                self.pinned_tables.append(table)
        self._push_local_tables()
        self._sync_tables_to_joins()
        self.joins_tab.ensure_on_canvas(name)
        if join_to_bas_pol:
            self.joins_tab.ensure_on_canvas(BAS_POL_TABLE)
            self._place_right_of(BAS_POL_TABLE, name)
            keys = [(POLICY_COLUMN, "CK_POLICY_NBR")]
            if COMPANY_COLUMN in policy_list.columns:
                keys.append((COMPANY_COLUMN, "CK_CMP_CD"))
            if SYSTEM_COLUMN in policy_list.columns:
                keys.append((SYSTEM_COLUMN, "CK_SYS_CD"))
            for list_col, pol_col in keys:
                self.joins_tab.scene.add_link(name, list_col, BAS_POL_TABLE, pol_col)
            # Every pasted policy stays in the result, found or not.
            self.joins_tab.model.set_how(name, BAS_POL_TABLE, "left")
            self.joins_tab.scene.rebuild()
            self.joins_tab._update_suggestions()
        self.sources_changed.emit()
        self.tab_widget.setCurrentWidget(self.joins_tab)
        self._schedule_plan_refresh()
        self._schedule_save()
        return name

    def _place_right_of(self, table: str, anchor: str):
        src, ref = self.joins_tab.model.get_source(table), self.joins_tab.model.get_source(anchor)
        box = self.joins_tab.scene.box_items.get(anchor)
        if src is None or ref is None or box is None:
            return
        src.x = ref.x + box.boundingRect().width() + 90
        src.y = ref.y
        self.joins_tab.scene.rebuild()

    def set_tables(self, tables: list[str]):
        """The SQL Assist table list for this query."""
        self.tables = list(tables)
        self._sync_tables_to_joins()

    def _common_table_names(self) -> set[str]:
        return {ct.name for ct in self.common_tables_tab.get_selected_tables()}

    def _known_tables(self) -> list[str]:
        """Every table this query knows about (list, pins, files, fields, canvas)."""
        names: list[str] = []
        for table in [*self.tables, *self.pinned_tables, *self.table_sources,
                      *self.joins_tab.canvas_tables()]:
            if table and table not in names:
                names.append(table)
        for table in self._field_tables(names):
            if table not in names:
                names.append(table)
        return names

    def _field_tables(self, known: list[str]) -> list[str]:
        """Tables of the fields placed on Filter tabs and Display, in order."""
        keys = [row.field_key for tab in self._criteria_tabs for row in tab.grid._rows]
        keys.extend(sc.get("field_key", "") for sc in self.select_tab.get_select_columns())
        tables: list[str] = []
        for key in keys:
            table = split_field_key(key, known)[0]
            if table and table not in tables:
                tables.append(table)
        return tables

    def _sync_tables_to_joins(self):
        names: list[str] = []
        for table in [*self.tables, *self.pinned_tables, *self.table_sources]:
            if table and table not in names:
                names.append(table)
        self.joins_tab.update_tables(names)

    def _ensure_used_tables_on_canvas(self):
        for table in self._field_tables(self._known_tables()):
            if table not in self._common_table_names():
                self.joins_tab.ensure_on_canvas(table)

    def show_table_on_canvas(self, table: str):
        """Place ``table`` on the Joins canvas and show the Joins tab."""
        if not table:
            return
        self.joins_tab.ensure_on_canvas(table)
        self.tab_widget.setCurrentWidget(self.joins_tab)

    def _on_tab_changed(self, _index: int):
        if self.tab_widget.currentWidget() is self.joins_tab:
            self._ensure_used_tables_on_canvas()
            self.refresh_plan_badges()

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(2)

        self._lbl_query_name = QLabel()
        self._lbl_query_name.setFont(QFont("Segoe UI", 12, QFont.Weight.Bold))
        self._lbl_query_name.setStyleSheet("QLabel { color: #0A2A5C; padding: 2px 6px; }")
        root.addWidget(self._lbl_query_name)

        # ── Tab widget ───────────────────────────────────────────────
        self.tab_widget = QTabWidget()
        self.tab_widget.setFont(_FONT)
        self.tab_widget.setStyleSheet(
            "QTabWidget::pane { border-top: 3px solid #1E5BA8;"
            " border-bottom: 3px solid #1E5BA8;"
            " border-left: 1px solid #999; border-right: 1px solid #999;"
            " background-color: #F6F8FB; }"
            "QTabBar { background-color: #F6F8FB; }"
            "QTabBar::tab { padding: 2px 8px; min-height: 20px; font-size: 9pt;"
            " background-color: #E8F0FB; border: 1px solid #1E5BA8;"
            " border-bottom: none; border-top-left-radius: 3px;"
            " border-top-right-radius: 3px; margin-right: 1px; }"
            "QTabBar::tab:selected { font-weight: bold;"
            " background-color: #F6F8FB; color: #0A2A5C; }"
            "QTabBar::tab:!selected { background-color: #E8F0FB; color: #444; }"
            "QTabBar::tab:hover:!selected { background-color: #D9E8F7; }"
        )

        # Right-click tab bar for add/rename/remove
        self.tab_widget.tabBar().setContextMenuPolicy(
            Qt.ContextMenuPolicy.CustomContextMenu)
        self.tab_widget.tabBar().customContextMenuRequested.connect(
            self._on_tab_context_menu)

        # Default tabs
        self._criteria_tabs: list[DynamicTab] = []
        self._add_criteria_tab("Filter")

        # Joins tab — for building table joins
        self.joins_tab = JoinsTab(tables=self.tables, dsn=self.dsn)
        self.tab_widget.addTab(self.joins_tab, "Joins")

        # Common Tables state — driven from SQL Assist instead of a visible tab
        self.common_tables_tab = CommonTablesTab()
        self.common_tables_tab.setVisible(False)

        # Select tab — for managing SELECT columns
        self.select_tab = SelectTab()
        self.tab_widget.addTab(self.select_tab, "Display")

        self.results_tab = ResultsTab()
        self.tab_widget.addTab(self.results_tab, "Results")

        self.sql_tab = SqlTab()
        self.tab_widget.addTab(self.sql_tab, "SQL")

        # Build SQL tabs (hidden until "Move to Build" is clicked)
        self.build_sql_tab = BuildSqlTab()
        self.build_sql_results_tab = BuildSqlResultsTab()
        self._build_sql_tab_index = -1
        self._build_sql_results_tab_index = -1

        # Wire Move to Build signal
        self.sql_tab.build_sql_requested.connect(self._build_sql_only)
        self.sql_tab.move_to_build.connect(self._on_move_to_build)
        self.build_sql_tab.run_sql_requested.connect(self._run_build_sql)

        root.addWidget(self.tab_widget, 1)
        self.tab_widget.currentChanged.connect(self._on_tab_changed)

        # ── Bottom bar ───────────────────────────────────────────────
        self.bottom_bar = AuditBottomBar(
            bg_color=FOOTER_BG, run_label="Run",
            run_style=_RUN_BTN_STYLE)

        # Convenience aliases
        self.btn_all = self.bottom_bar.btn_all
        self.txt_max_count = self.bottom_bar.txt_max_count
        self.lbl_result_count = self.bottom_bar.lbl_result_count
        self.lbl_query_time = self.bottom_bar.lbl_query_time
        self.lbl_print_time = self.bottom_bar.lbl_print_time
        self.lbl_total_time = self.bottom_bar.lbl_total_time
        self.btn_run = self.bottom_bar.btn_run

        self.btn_new_query = QPushButton("New Query")
        self.btn_new_query.setFont(_FONT_BOLD)
        self.btn_new_query.setFixedSize(78, 36)
        self.btn_new_query.setStyleSheet(_SAVE_QUERY_BTN_STYLE)
        self.btn_new_query.setToolTip("Start a new Visual Query Object")
        self.btn_new_query.clicked.connect(self._confirm_new_query)
        self.bottom_bar.action_layout.addWidget(self.btn_new_query)

        # Action buttons: Save / Save As Query Object
        self.btn_save_query = QPushButton("Save")
        self.btn_save_query.setFont(_FONT_BOLD)
        self.btn_save_query.setFixedSize(60, 36)
        self.btn_save_query.setStyleSheet(_SAVE_QUERY_BTN_STYLE)
        self.btn_save_query.setToolTip("Update this visual Query Object")
        self.btn_save_query.clicked.connect(self._save_or_update_query)

        self.btn_save_as = QPushButton("Save As")
        self.btn_save_as.setFont(_FONT_BOLD)
        self.btn_save_as.setFixedSize(60, 36)
        self.btn_save_as.setStyleSheet(_SAVE_QUERY_BTN_STYLE)
        self.btn_save_as.setToolTip("Save a copy as a new query object")
        self.btn_save_as.clicked.connect(self._save_query)
        self.bottom_bar.action_layout.addWidget(self.btn_save_as)
        self.bottom_bar.action_layout.addWidget(self.btn_save_query)

        self._update_builder_heading()

        self.btn_run.clicked.connect(self._run_audit)

        root.addWidget(self.bottom_bar)

    def _confirm_new_query(self):
        reply = QMessageBox.question(
            self,
            "Start New Query?",
            "This will clear the current Visual Query builder. Continue?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if reply == QMessageBox.StandardButton.Yes:
            self.results_tab.clear_results()
            self.sql_tab.clear_sql()
            self.build_sql_tab.clear_sql()
            self.build_sql_results_tab.clear_results()
            self.lbl_result_count.setText("Result count:")
            self.new_query_requested.emit()

    # ── Tab management ───────────────────────────────────────────────

    def _add_criteria_tab(self, name: str) -> DynamicTab:
        tab = DynamicTab(tab_name=name, dsn=self.dsn)
        tab.source_for = self.source_for
        tab.on_field_placed = self._add_source_table
        self._criteria_tabs.append(tab)
        # Insert before Select/Results/SQL (3 fixed tabs at the end)
        idx = max(self.tab_widget.count() - 4, 0)
        self.tab_widget.insertTab(idx, tab, name)
        # Wire grid state changes for auto-save
        tab.grid.state_changed.connect(self._schedule_save)
        tab.grid.state_changed.connect(self._schedule_plan_refresh)
        self._schedule_save()
        return tab

    def _on_tab_context_menu(self, pos):
        tab_bar = self.tab_widget.tabBar()
        tab_index = tab_bar.tabAt(pos)

        menu = query_builder_menu(self)

        act_add = menu.addAction("Add Tab")

        act_rename = None
        act_remove = None
        act_close_build = None
        if tab_index >= 0:
            widget = self.tab_widget.widget(tab_index)
            # Only allow rename/remove for criteria tabs (not Results/SQL)
            if isinstance(widget, DynamicTab):
                act_rename = menu.addAction("Rename Tab")
                if len(self._criteria_tabs) > 1:
                    act_remove = menu.addAction("Remove Tab")
            elif isinstance(widget, (BuildSqlTab, BuildSqlResultsTab)):
                act_close_build = menu.addAction("Close")

        chosen = menu.exec(tab_bar.mapToGlobal(pos))
        if chosen is None:
            return

        if chosen is act_add:
            name, ok = QInputDialog.getText(self, "Add Tab", "Tab name:")
            if ok and name.strip():
                self._add_criteria_tab(name.strip())

        elif chosen is act_rename:
            widget = self.tab_widget.widget(tab_index)
            old_name = self.tab_widget.tabText(tab_index)
            name, ok = QInputDialog.getText(
                self, "Rename Tab", "New name:", text=old_name)
            if ok and name.strip():
                self.tab_widget.setTabText(tab_index, name.strip())
                if isinstance(widget, DynamicTab):
                    widget.tab_name = name.strip()
                self._schedule_save()

        elif chosen is act_remove:
            widget = self.tab_widget.widget(tab_index)
            if isinstance(widget, DynamicTab):
                reply = QMessageBox.question(
                    self, "Remove Tab?",
                    f"Remove tab '{self.tab_widget.tabText(tab_index)}'?",
                    QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
                if reply == QMessageBox.StandardButton.Yes:
                    self._criteria_tabs.remove(widget)
                    self.tab_widget.removeTab(tab_index)
                    widget.deleteLater()
                    self._schedule_save()

        elif chosen is act_close_build:
            widget = self.tab_widget.widget(tab_index)
            self.tab_widget.removeTab(tab_index)
            if isinstance(widget, BuildSqlTab):
                self._build_sql_tab_index = -1
            elif isinstance(widget, BuildSqlResultsTab):
                self._build_sql_results_tab_index = -1

    # ── Tables dialog ────────────────────────────────────────────────

    def _open_tables_dialog(self):
        if self._tabs_dialog is not None and self._tabs_dialog.isVisible():
            self._tabs_dialog.raise_()
            self._tabs_dialog.activateWindow()
            return
        dlg = TablesDialog(self.dsn, self.tables, self.display_names, self)
        dlg.setWindowModality(Qt.WindowModality.NonModal)
        dlg.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose, False)
        dlg.field_requested.connect(self._on_field_requested)
        dlg.finished.connect(lambda: self._on_tables_dialog_closed(dlg))
        self._tabs_dialog = dlg
        dlg.show()

    def _on_tables_dialog_closed(self, dlg: TablesDialog):
        # Update tables/display_names from dialog
        self.tables = dlg.get_tables()
        self.display_names = dlg.get_display_names()
        # Propagate table list to joins tab
        self._sync_tables_to_joins()
        # Re-sync common tables so they stay in the joins table list
        self._sync_common_tables_to_joins()
        self._tabs_dialog = None
        self._schedule_save()

    def _sync_common_tables_to_joins(self):
        """Push common table names + column info to the Joins tab and picker."""
        common_cols: dict[str, list[tuple[str, str]]] = {}
        for ct in self.common_tables_tab.get_selected_tables():
            cols = [(c["name"], c.get("type", "TEXT")) for c in ct.columns]
            common_cols[ct.name] = cols
        self.joins_tab.update_common_tables(common_cols)
        self.common_tables_changed.emit(common_cols)

    def add_common_table(self, name: str):
        """Include a Common Table in this query."""
        if not name:
            return
        state = self.common_tables_tab.get_state()
        selected = list(state.get("selected_tables", []))
        if name not in selected:
            selected.append(name)
        self.common_tables_tab.set_state({"selected_tables": selected})
        self._sync_common_tables_to_joins()
        self._schedule_save()

    def set_pinned_tables(self, tables: list[str]):
        """Persist the SQL Assist pinned table list for this query."""
        seen: set[str] = set()
        self.pinned_tables = []
        for table in tables:
            if table and table not in seen:
                self.pinned_tables.append(table)
                seen.add(table)
        self._sync_tables_to_joins()
        self._schedule_save()

    def remove_common_table(self, name: str):
        """Remove a Common Table from this query."""
        if not name:
            return
        state = self.common_tables_tab.get_state()
        selected = [t for t in state.get("selected_tables", []) if t != name]
        self.common_tables_tab.set_state({"selected_tables": selected})
        self._sync_common_tables_to_joins()
        self._schedule_save()

    def _on_field_requested(self, table: str, column: str,
                            type_name: str, display: str):
        """Handle field placement request (double-click or drag) from Tables dialog."""
        self._add_source_table(table)
        current = self.tab_widget.currentWidget()
        # If the Select tab is active, add to Select tab
        if isinstance(current, SelectTab):
            key = f"{table}.{column}"
            current.add_field(key, display or column)
            return
        # Otherwise place on the current criteria tab
        if not isinstance(current, DynamicTab):
            # Default to first criteria tab
            if self._criteria_tabs:
                current = self._criteria_tabs[0]
                self.tab_widget.setCurrentWidget(current)
            else:
                return
        current.add_field_auto(table, column, type_name, display or column)
        self._schedule_save()

    def _add_source_table(self, table: str):
        """Track a table introduced by a placed SQL Assist field."""
        if not table:
            return
        if table not in self.tables:
            self.tables.append(table)
            self._sync_tables_to_joins()
        if table not in self._common_table_names():
            self.joins_tab.ensure_on_canvas(table)

    # ── Field display name context menu ──────────────────────────────

    def update_display_name(self, key: str, new_name: str):
        """Update display name for a field (single source of truth)."""
        self.display_names[key] = new_name
        # Update any FieldRow widgets that use this key
        for tab in self._criteria_tabs:
            row = tab.grid.field(key)
            if row is not None:
                row._lbl.setText(new_name)
        self._schedule_save()

    # ── Clear all ────────────────────────────────────────────────────

    def _clear_all(self):
        for tab in self._criteria_tabs:
            for row in list(tab.grid._rows):
                row.set_state({})
        self.select_tab.clear()
        self.txt_max_count.setText("25")
        self.lbl_result_count.setText("Result count:")
        self.lbl_query_time.setText("Query time:")
        self.lbl_print_time.setText("Print time:")
        self.lbl_total_time.setText("Total time:")
        self._schedule_save()

    # ── Auto-save ────────────────────────────────────────────────────

    def _schedule_save(self):
        """Restart the debounce timer — config_changed emits after 800ms idle."""
        if self._loading:
            return
        self._save_timer.start()

    # ── Run audit ────────────────────────────────────────────────────

    def _base_known_tables(self) -> list[str]:
        names: list[str] = []
        for table in [*self.tables, *self.pinned_tables, *self.table_sources,
                      *self.joins_tab.canvas_tables(), *self._common_table_names()]:
            if table and table not in names:
                names.append(table)
        return names

    def _table_from_field_key(self, field_key: str) -> str:
        return split_field_key(field_key, self._base_known_tables())[0]

    def _infer_tables_from_fields(
        self,
        field_filters: list[dict],
        select_columns: list[dict],
    ) -> list[str]:
        tables: list[str] = []
        for item in [*field_filters, *select_columns]:
            table = self._table_from_field_key(item.get("field_key", ""))
            if table and table not in tables:
                tables.append(table)
        return tables

    def _initial_focus_target(self) -> tuple[QWidget | None, str]:
        """Return the first populated builder tab and its primary table."""
        for tab in self._criteria_tabs:
            if tab.grid._rows:
                table = self._table_from_field_key(tab.grid._rows[0].field_key)
                return tab, table

        join_infos = self.joins_tab.get_join_infos()
        if join_infos:
            table = (join_infos[0].get("left_table") or join_infos[0].get("right_table") or "").strip()
            return self.joins_tab, table

        select_columns = self.select_tab.get_select_columns()
        if select_columns:
            table = self._table_from_field_key(select_columns[0].get("field_key", ""))
            return self.select_tab, table

        fallback = next((table for table in self.tables if table), "")
        if self._criteria_tabs:
            return self._criteria_tabs[0], fallback
        return None, fallback

    def preferred_picker_table(self) -> str:
        """Return the table that best matches the first visible builder surface."""
        _, table = self._initial_focus_target()
        return table

    def focus_initial_builder_state(self):
        """Select the first populated tab when reopening a saved visual query."""
        widget, _ = self._initial_focus_target()
        if widget is not None:
            self.tab_widget.setCurrentWidget(widget)

    def _design_inputs(self) -> dict:
        """Everything the builders need from Filter / Joins / Display."""
        from .dynamic_query import collect_field_filters

        all_filters = []
        for tab in self._criteria_tabs:
            all_filters.extend(collect_field_filters(tab.grid))
        select_cols = self.select_tab.get_select_columns()
        join_infos = self.joins_tab.get_join_infos()

        # Field keys are "table.column"; file columns may contain dots, so the
        # known table name (not the last dot) decides where the column starts.
        known = self._base_known_tables()
        for spec in select_cols:
            table, column = split_field_key(spec.get("field_key", ""), known)
            if table:
                spec["column"] = column

        join_tables: list[str] = []
        for ji in join_infos:
            for table in (ji["left_table"], ji["right_table"]):
                if table not in join_tables:
                    join_tables.append(table)
        return {
            "filters": all_filters,
            "select": select_cols,
            "joins": join_infos,
            "max_count": self.txt_max_count.text().strip(),
            "display_all": self.select_tab.display_all,
            "distinct": self.select_tab.show_distinct,
            "field_tables": self._infer_tables_from_fields(all_filters, select_cols),
            "join_tables": join_tables,
            "fallback": next(
                (t for t in [*self.joins_tab.canvas_tables(), *self.tables] if t), ""),
        }

    def _plan(self, design: dict, primary: str, sources: dict[str, str]) -> FederatedPlan:
        """Federated plan for a design whose tables include files / pasted lists."""
        labels = {}
        for token in {s for s in sources.values() if is_file_token(s)}:
            fds = resolve_file_token(token)
            if fds is None:
                missing = [t for t, s in sources.items() if s == token]
                raise ValueError(
                    "The File Source for " + ", ".join(missing)
                    + " could not be found. It may have been deleted; "
                    "remove the table from SQL Assist or restore the File Source.")
            labels[token] = file_source_label(fds)
        return plan_federated_query(
            table_sources=sources,
            used_tables=list(sources),
            primary_table=primary,
            field_filters=design["filters"],
            select_columns=design["select"],
            join_infos=design["joins"],
            max_count=design["max_count"],
            display_all=design["display_all"],
            distinct=design["distinct"],
            cte_prefix=build_common_table_cte(
                self.common_tables_tab.get_selected_tables(), DUCKDB),
            source_labels=labels,
            inline_tables=self.inline_tables,
        )

    def _design_sources(self, primary: str, design: dict) -> dict[str, str]:
        used: list[str] = []
        for table in [primary, *design["field_tables"], *design["join_tables"]]:
            if table and table not in used:
                used.append(table)
        common_names = self._common_table_names()
        return {t: self.source_for(t) for t in used if t not in common_names}

    def _prepare_query(self) -> "_PreparedQuery | None":
        """Validate the design and compile it — natively, or federated for files."""
        design = self._design_inputs()
        all_filters = design["filters"]
        max_count = design["max_count"]
        select_cols = design["select"]
        display_all = design["display_all"]
        show_distinct = design["distinct"]
        join_infos = design["joins"]
        field_tables = design["field_tables"]
        join_tables = design["join_tables"]
        fallback = design["fallback"]
        if not field_tables and not join_tables and not fallback:
            QMessageBox.warning(
                self,
                "No Tables",
                "This query has no source table. Add fields from SQL Assist "
                "to Filter or Display first.",
            )
            return None
        if field_tables and not self.tables:
            self.tables = list(field_tables)
            self._sync_tables_to_joins()

        if not join_infos and len(field_tables) > 1:
            QMessageBox.warning(
                self,
                "Joins Required",
                "This query uses fields from more than one table:\n\n"
                + "\n".join(field_tables)
                + "\n\nOn the Joins tab, drag a field from one table onto the "
                "matching field of another to join them.",
            )
            self._ensure_used_tables_on_canvas()
            self.tab_widget.setCurrentWidget(self.joins_tab)
            return None

        primary = choose_primary_table(field_tables, join_infos, fallback)
        if join_infos:
            ambiguity = outer_join_ambiguity(join_infos)
            if ambiguity:
                QMessageBox.warning(self, "Ambiguous Outer Join", ambiguity)
                self.tab_widget.setCurrentWidget(self.joins_tab)
                return None
            try:
                order_join_infos(primary, join_infos)
            except ValueError as exc:
                QMessageBox.warning(self, "Joins Incomplete", str(exc))
                self.tab_widget.setCurrentWidget(self.joins_tab)
                return None
            joined = {primary, *join_tables}
            unjoined = [t for t in field_tables if t not in joined]
            if unjoined:
                QMessageBox.warning(
                    self,
                    "Table Not Joined",
                    "These tables have fields on Filter/Display but are not "
                    "joined to the other tables:\n\n" + "\n".join(unjoined)
                    + "\n\nOn the Joins tab, drag one of their fields onto the "
                    "matching field of a joined table.",
                )
                self._ensure_used_tables_on_canvas()
                self.tab_widget.setCurrentWidget(self.joins_tab)
                return None

        common_tables = self.common_tables_tab.get_selected_tables()
        sources = self._design_sources(primary, design)
        federated = any(is_local_token(source) for source in sources.values())

        try:
            if federated:
                plan = self._plan(design, primary, sources)
                return _PreparedQuery(plan.describe(), plan)

            if join_infos:
                sql = build_join_sql(
                    primary, max_count, all_filters,
                    join_infos=join_infos,
                    select_columns=select_cols,
                    display_all=display_all,
                    distinct=show_distinct,
                    dialect=self.dialect)
            else:
                sql = build_dynamic_sql(
                    primary, max_count, all_filters,
                    select_columns=select_cols,
                    display_all=display_all,
                    distinct=show_distinct,
                    dialect=self.dialect)

            # Prepend Common Table CTEs
            cte_prefix = build_common_table_cte(common_tables, self.dialect)
            if cte_prefix:
                sql = cte_prefix + "\n" + sql
        except Exception as exc:
            logger.exception("Failed to build dynamic SQL")
            QMessageBox.warning(self, "SQL Build Error", str(exc))
            return None

        return _PreparedQuery(sql, None)

    def _build_sql(self) -> str | None:
        prepared = self._prepare_query()
        return prepared.sql if prepared is not None else None

    def is_mixed_source(self) -> bool:
        """True when a file dataset / pasted list joins tables of this query's database."""
        return bool(self.table_sources) and not is_file_token(self.dsn)

    def refresh_plan_badges(self):
        """Show on the canvas how each table will be fetched when the query runs.

        Database tables staged for a file/list join say whether they're narrowed
        (by key values or filters) or downloaded whole; tables on the canvas that
        the query doesn't use say so; pasted lists show their row count.
        """
        canvas = self.joins_tab.canvas_tables()
        design = self._design_inputs()
        used = set(design["field_tables"]) | set(design["join_tables"])
        status: dict[str, tuple[str, str]] = {}
        for table in canvas:
            if table in self.inline_tables:
                count = len(self.inline_tables[table].get("rows", []))
                status[table] = ("info", f"{count} pasted {'row' if count == 1 else 'rows'}")
            elif len(canvas) > 1 and table not in used:
                status[table] = ("muted", "Not used — no fields or joins",
                                 "Place one of its fields on Filter/Display or join it, "
                                 "or right-click › Delete Table.")
        try:
            ambiguity = find_outer_join_ambiguity(design["joins"])
            if ambiguity:
                status[ambiguity[0]] = ("warn", "\u26A0 Ambiguous outer join",
                                        outer_join_ambiguity(design["joins"]))
                self.joins_tab.set_box_status(status)
                return
            primary = choose_primary_table(
                design["field_tables"], design["joins"], design["fallback"])
            sources = self._design_sources(primary, design)
            if primary and any(is_local_token(s) for s in sources.values()):
                if design["joins"]:
                    order_join_infos(primary, design["joins"])
                for step in self._plan(design, primary, sources).steps:
                    if step.pushdowns:
                        p = step.pushdowns[0]
                        short = p.from_table.rsplit(".", 1)[-1]
                        status[step.table] = (
                            "ok", f"\u2713 Only rows matching {short}",
                            f"Fetches only the {p.column} values found in "
                            f"{p.from_table}.{p.from_column}, then joins.")
                    elif step.filters:
                        status[step.table] = (
                            "ok", "\u2713 Narrowed by its filters",
                            "Its Filter criteria run on the database before joining.")
                    else:
                        status[step.table] = (
                            "warn", "\u26A0 Downloads the whole table",
                            "Nothing narrows this table: add a filter on it, or join it "
                            "with an Inner join to a pasted list or file dataset.")
        except Exception:
            logger.debug("Plan badges unavailable for the current design", exc_info=True)
        self.joins_tab.set_box_status(status)

    def _build_sql_only(self):
        sql = self._build_sql()
        if not sql:
            return
        self.sql_tab.set_sql(sql)
        self.tab_widget.setCurrentWidget(self.sql_tab)
        logger.info("Generated SQL:\n%s", sql)

    def _confirm_full_downloads(self, plan: FederatedPlan) -> bool:
        tables = plan.unrestricted_tables()
        if not tables:
            return True
        reply = QMessageBox.question(
            self,
            "Download Whole Table?",
            "These database tables have no filter and no join to a file dataset "
            "that could narrow them, so every row is downloaded before joining:\n\n"
            + "\n".join(tables)
            + "\n\nAdd a filter, or join them to a file dataset with an Inner "
            "join, to limit the download. Run anyway?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        return reply == QMessageBox.StandardButton.Yes

    def _run_audit(self):
        prepared = self._prepare_query()
        if prepared is None:
            return
        sql = prepared.sql
        plan = prepared.plan

        self.sql_tab.set_sql(sql)
        logger.info("Generated SQL:\n%s", sql)
        if plan is not None and not self._confirm_full_downloads(plan):
            return

        dsn = self.dsn

        def work():
            t0 = time.time()
            if plan is not None:
                from suiteview.audit.file_query_runner import dtype_label

                df = execute_federated_plan(plan)
                columns = [str(c) for c in df.columns]
                col_types = {str(c): dtype_label(df[c]) for c in df.columns}
            else:
                columns, rows, col_types = execute_odbc_query_with_types(dsn, sql)
                df = pd.DataFrame([list(r) for r in rows], columns=columns)
            t_query = time.time() - t0
            return columns, col_types, df, t_query

        def on_success(payload):
            columns, col_types, df, t_query = payload
            t1 = time.time()
            self.results_tab.set_results(df)
            self.results_tab.set_query_context(
                sql=sql, dsn=dsn,
                source_design=self.query_name,
                result_columns=columns,
                column_types=col_types,
                tables=self.tables,
                display_names=self.display_names,
            )
            t_print = time.time() - t1
            self.lbl_query_time.setText(f"Query time:  {fmt_time(t_query)}")
            self.lbl_print_time.setText(f"Print time:  {fmt_time(t_print)}")
            self.lbl_total_time.setText(f"Total time:  {fmt_time(t_query + t_print)}")
            self.lbl_result_count.setText(f"Result count:   {len(df)}")
            self.tab_widget.setCurrentWidget(self.results_tab)

        def on_error(exc):
            logger.error("Dynamic audit query failed: %s\nSQL:\n%s", exc, sql)
            QMessageBox.warning(self, "Query Error", format_query_error(exc))

        run_query_async(
            owner=self,
            work=work,
            on_success=on_success,
            on_error=on_error,
            btn=self.btn_run,
            bar=self.bottom_bar,
        )


    # ── Save Query Object ────────────────────────────────────────────

    def _last_result_schema(self) -> tuple[list[str], dict[str, str]]:
        ctx = getattr(self.results_tab, "_query_context", None)
        if ctx:
            return (
                list(ctx.get("result_columns", [])),
                dict(ctx.get("column_types", {})),
            )
        df = getattr(self.results_tab, "_df", None)
        if df is not None:
            return list(df.columns), {col: str(df[col].dtype) for col in df.columns}
        return [], {}

    def _save_query_update(self):
        """Overwrite the linked saved query with the current config."""
        from suiteview.audit.saved_query import SavedQuery
        from suiteview.audit import saved_query_store as sq_store

        name = self._saved_query_name
        if not name:
            return

        sql = self._build_sql()
        if not sql:
            return
        self.sql_tab.set_sql(sql)
        config = self.get_config()
        result_columns, column_types = self._last_result_schema()

        sq = SavedQuery(
            name=name,
            source_group=self.query_name,
            dsn=self.dsn,
            tables=list(self.tables),
            display_names=dict(self.display_names),
            config=config,
            sql=sql,
            result_columns=result_columns,
            column_types=column_types,
        )
        sq_store.save_query(sq)
        self.query_saved.emit(sq)
        self._update_builder_heading()

        QMessageBox.information(
            self, "Query Object Saved",
            f"Query object \"{name}\" updated successfully.")

    def _save_or_update_query(self):
        """Save the current visual query, updating when it has a saved name."""
        if self._saved_query_name:
            self._save_query_update()
            return
        self._save_query()

    def _save_query(self):
        """Snapshot the current designer config as a saved query."""
        from suiteview.audit.saved_query import SavedQuery
        from suiteview.audit import saved_query_store as sq_store

        name, ok = QInputDialog.getText(
            self, "Save Query Object",
            "Object name:",
            text="",
        )
        if not ok or not name.strip():
            return
        name = name.strip()

        if sq_store.query_exists(name):
            reply = QMessageBox.question(
                self, "Overwrite?",
                f"A query named \"{name}\" already exists.\nOverwrite it?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if reply != QMessageBox.StandardButton.Yes:
                return

        sql = self._build_sql()
        if not sql:
            return
        self.sql_tab.set_sql(sql)
        config = self.get_config()
        result_columns, column_types = self._last_result_schema()

        sq = SavedQuery(
            name=name,
            source_group=self.query_name,
            dsn=self.dsn,
            tables=list(self.tables),
            display_names=dict(self.display_names),
            config=config,
            sql=sql,
            result_columns=result_columns,
            column_types=column_types,
        )
        sq_store.save_query(sq)
        self._saved_query_name = name
        self._update_builder_heading()
        self.query_saved.emit(sq)

        QMessageBox.information(
            self, "Query Object Saved",
            f"Query object \"{name}\" saved successfully.")

    def _update_builder_heading(self):
        name = self._saved_query_name.strip() or "(new)"
        self._lbl_query_name.setText(f"Visual Query Object: {name}")
        self.btn_save_query.setVisible(bool(self._saved_query_name.strip()))
        self.btn_save_as.setVisible(True)
        self.btn_new_query.setVisible(True)

    # ── Build SQL feature ────────────────────────────────────────────

    def _on_move_to_build(self, sql: str):
        """Copy SQL to the Build SQL tab and switch to it."""
        if self._build_sql_tab_index < 0:
            self._build_sql_tab_index = self.tab_widget.addTab(
                self.build_sql_tab, "Build SQL")
        self.build_sql_tab.set_sql(sql)
        self.tab_widget.setCurrentWidget(self.build_sql_tab)

    def _run_build_sql(self, sql: str):
        """Execute user-edited SQL and show results in Build SQL Results."""
        if self.is_mixed_source():
            QMessageBox.information(
                self,
                "Mixed-Source Query",
                "Edited SQL runs on a single connection, but this query joins "
                "database tables with file datasets. Change the design on the "
                "Filter / Joins / Display tabs and press Run instead.",
            )
            return
        dsn = self.dsn

        def work():
            if dsn.startswith("file:"):
                from suiteview.audit import file_query_runner
                fds = file_query_runner.resolve_file_source(dsn[len("file:"):])
                if fds is None:
                    raise RuntimeError("This file source could not be found.")
                return file_query_runner.run_sql(fds, sql, limit=None).dataframe
            columns, rows = execute_odbc_query(dsn, sql)
            return pd.DataFrame([list(r) for r in rows], columns=columns)

        def on_success(df):
            if self._build_sql_results_tab_index < 0:
                self._build_sql_results_tab_index = self.tab_widget.addTab(
                    self.build_sql_results_tab, "Build SQL Results")
            self.build_sql_results_tab.set_results(df)
            self.tab_widget.setCurrentWidget(self.build_sql_results_tab)

        def on_error(exc):
            logger.error("Build SQL query failed: %s", exc)
            QMessageBox.warning(self, "Query Error", format_query_error(exc))

        run_query_async(
            owner=self,
            work=work,
            on_success=on_success,
            on_error=on_error,
            btn=self.build_sql_tab.btn_run_sql,
            restore_text="Run this SQL",
        )


    # ── State persistence ────────────────────────────────────────────

    def get_config(self) -> dict:
        """Return the full query config for save."""
        return {
            "name": self.query_name,
            "dsn": self.dsn,
            "tables": self.tables,
            "pinned_tables": self.pinned_tables,
            "table_sources": dict(self.table_sources),
            "inline_tables": {t: dict(d) for t, d in self.inline_tables.items()},
            "display_names": self.display_names,
            "max_count": self.txt_max_count.text(),
            "tabs": [tab.get_state() for tab in self._criteria_tabs],
            "joins_tab": self.joins_tab.get_state(),
            "common_tables_tab": self.common_tables_tab.get_state(),
            "select_tab": self.select_tab.get_state(),
        }

    def set_config(self, config: dict):
        """Restore from a saved config."""
        self._loading = True
        try:
            self.display_names = config.get("display_names", {})
            self.tables = config.get("tables", self.tables)
            self.pinned_tables = list(config.get("pinned_tables", []))
            self.table_sources = {
                table: token
                for table, token in dict(config.get("table_sources", {})).items()
                if table and is_local_token(token)
            }
            self.inline_tables = {
                table: {"columns": list(data.get("columns", [])),
                        "rows": [list(row) for row in data.get("rows", [])]}
                for table, data in dict(config.get("inline_tables", {})).items()
                if is_list_token(self.table_sources.get(table, ""))
            }
            self.txt_max_count.setText(config.get("max_count", "25"))
            tab_states = config.get("tabs", [])
            # Rebuild criteria tabs from saved state
            if tab_states:
                # Remove existing criteria tabs (except the default one)
                while len(self._criteria_tabs) > 1:
                    tab = self._criteria_tabs.pop()
                    idx = self.tab_widget.indexOf(tab)
                    if idx >= 0:
                        self.tab_widget.removeTab(idx)
                    tab.deleteLater()

                # Restore first tab
                if self._criteria_tabs:
                    first_state = tab_states[0]
                    self._criteria_tabs[0].set_state(first_state)
                    name = first_state.get("tab_name", "Filter")
                    if name == "Where":
                        name = "Filter"
                    idx = self.tab_widget.indexOf(self._criteria_tabs[0])
                    if idx >= 0:
                        self.tab_widget.setTabText(idx, name)

                # Create additional tabs
                for ts in tab_states[1:]:
                    tab_name = ts.get("tab_name", "Tab")
                    if tab_name == "Where":
                        tab_name = "Filter"
                    tab = self._add_criteria_tab(tab_name)
                    tab.set_state(ts)

            # Restore Common Tables tab state (before Joins so names are available)
            ct_state = config.get("common_tables_tab")
            if ct_state:
                self.common_tables_tab.set_state(ct_state)
            # Push common table column info to Joins tab
            self._sync_common_tables_to_joins()
            self.joins_tab.set_dsn(self.dsn)
            self._push_local_tables()
            self._sync_tables_to_joins()

            # Restore Joins tab state (after common tables are in the combo)
            joins_state = config.get("joins_tab")
            if joins_state:
                self.joins_tab.set_state(joins_state)

            # Restore Select tab state
            select_state = config.get("select_tab")
            if select_state:
                self.select_tab.set_state(select_state)

            self.focus_initial_builder_state()
        finally:
            self._loading = False
        self._schedule_plan_refresh()
