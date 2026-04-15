"""
DynamicGroup — a full mode (tab set + footer) for user-created audit groups.

Each DynamicGroup manages:
  - A QTabWidget with an initial "All" tab + Results + SQL tabs
  - A bottom bar with Tables, Clear All, timing, max count, Run Audit
  - Dynamic field placement on tabs via drag-drop from Tables dialog
  - SQL building from placed FieldRow widgets
"""
from __future__ import annotations

import logging
import time

import pandas as pd
import pyodbc
from PyQt6.QtCore import Qt, QMimeData, pyqtSignal
from PyQt6.QtGui import QFont, QDrag
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QTabWidget, QTabBar,
    QLabel, QLineEdit, QPushButton, QMessageBox, QMenu,
    QApplication, QInputDialog, QComboBox, QScrollArea,
)

from .tabs.field_row import FieldRow, FieldGrid
from .tabs.results_tab import ResultsTab
from .tabs.sql_tab import SqlTab
from .tabs._styles import _FONT, style_combo as _style_combo
from .sql_helpers import fmt_time
from .dynamic_query import build_dynamic_sql, collect_field_filters
from .dialogs.tables_dialog import TablesDialog, FIELD_DRAG_MIME

logger = logging.getLogger(__name__)

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

_TABLES_BTN_STYLE = (
    "QPushButton { background-color: #E8F0FB; color: #1E5BA8;"
    " border: 1px solid #1E5BA8; border-radius: 3px;"
    " padding: 2px 10px; font-size: 9pt; font-weight: bold; }"
    "QPushButton:hover { background-color: #C5D8F5; }"
)


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
    """A single criteria tab for a dynamic group — wraps a FieldGrid."""

    def __init__(self, tab_name: str = "All", parent=None):
        super().__init__(parent)
        self.tab_name = tab_name
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
            parts = data.split("|", 3)
            if len(parts) == 4:
                table, column, type_name, display = parts
                pos = event.position().toPoint()
                self._add_field_at(table, column, type_name, display, pos.x(), pos.y())
            event.acceptProposedAction()
        else:
            self._orig_canvas_drop(event)

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
        )
        mode = _detect_widget_mode(type_name)
        self.grid.add_field(row)
        row.set_mode_idx(["contains", "regex", "combo", "list", "range"].index(mode))
        self.grid.move_field(key, x, y)

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


class DynamicGroup(QWidget):
    """Complete mode widget for a user-created dynamic group.

    Contains tab widget + bottom bar. Meant to be shown/hidden by AuditWindow
    like cyberlife/tai modes.
    """

    def __init__(self, name: str, dsn: str, tables: list[str],
                 display_names: dict[str, str] | None = None,
                 parent=None):
        super().__init__(parent)
        self.group_name = name
        self.dsn = dsn
        self.tables = list(tables)  # mutable — tables can be added/removed
        self.display_names: dict[str, str] = display_names or {}

        self._tabs_dialog: TablesDialog | None = None

        self._build_ui()

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(2)

        # ── Tab widget ───────────────────────────────────────────────
        self.tab_widget = QTabWidget()
        self.tab_widget.setFont(_FONT)
        self.tab_widget.setStyleSheet(
            "QTabWidget::pane { border: 1px solid #999; }"
            "QTabBar::tab { padding: 2px 8px; min-height: 20px; font-size: 9pt; }"
            "QTabBar::tab:selected { font-weight: bold; }"
        )

        # Right-click tab bar for add/rename/remove
        self.tab_widget.tabBar().setContextMenuPolicy(
            Qt.ContextMenuPolicy.CustomContextMenu)
        self.tab_widget.tabBar().customContextMenuRequested.connect(
            self._on_tab_context_menu)

        # Default tabs
        self._criteria_tabs: list[DynamicTab] = []
        self._add_criteria_tab("All")

        self.results_tab = ResultsTab()
        self.tab_widget.addTab(self.results_tab, "Results")

        self.sql_tab = SqlTab()
        self.tab_widget.addTab(self.sql_tab, "SQL")

        root.addWidget(self.tab_widget, 1)

        # ── Bottom bar ───────────────────────────────────────────────
        self.bottom_bar = QWidget()
        self.bottom_bar.setFixedHeight(50)
        self.bottom_bar.setStyleSheet(
            "QWidget { background-color: #D6E4F0; }")
        btm = QHBoxLayout(self.bottom_bar)
        btm.setSpacing(8)
        btm.setContentsMargins(4, 2, 4, 2)

        # 0) Group name label (far left)
        self._lbl_group_name = QLabel(self.group_name)
        self._lbl_group_name.setFont(QFont("Segoe UI", 9, QFont.Weight.Bold))
        self._lbl_group_name.setStyleSheet("QLabel { color: #1E5BA8; }")
        btm.addWidget(self._lbl_group_name)
        btm.addSpacing(4)

        # 1) Tables button
        self.btn_tables = QPushButton("Tables")
        self.btn_tables.setFont(_FONT_BOLD)
        self.btn_tables.setFixedSize(60, 36)
        self.btn_tables.setStyleSheet(_TABLES_BTN_STYLE)
        self.btn_tables.setToolTip("Browse tables and fields in this group")
        self.btn_tables.clicked.connect(self._open_tables_dialog)
        btm.addWidget(self.btn_tables)

        # 2) Clear All button
        self.btn_clear = QPushButton("Clear All")
        self.btn_clear.setFont(_FONT)
        self.btn_clear.setFixedSize(60, 36)
        self.btn_clear.setStyleSheet(_CLEAR_BTN_STYLE)
        self.btn_clear.clicked.connect(self._clear_all)
        btm.addWidget(self.btn_clear)

        btm.addStretch()

        # Active table indicator (between left and right clusters)
        self.lbl_active_table = QLabel("")
        self.lbl_active_table.setFont(QFont("Segoe UI", 8))
        self.lbl_active_table.setStyleSheet("color: #666;")
        if self.tables:
            self.lbl_active_table.setText(f"Table: {self.tables[0]}")
        btm.addWidget(self.lbl_active_table)

        btm.addStretch()

        # 4) All + Max Count + Result Count
        count_stack = QVBoxLayout()
        count_stack.setSpacing(2)
        count_stack.setContentsMargins(0, 0, 0, 0)

        mc_row = QHBoxLayout()
        mc_row.setSpacing(3)
        mc_row.setContentsMargins(0, 0, 0, 0)
        self.btn_all = QPushButton("All")
        self.btn_all.setFont(QFont("Segoe UI", 8))
        self.btn_all.setFixedSize(28, 18)
        self.btn_all.clicked.connect(self._set_all_rows)
        mc_row.addWidget(self.btn_all)
        self.txt_max_count = QLineEdit("25")
        self.txt_max_count.setFont(QFont("Segoe UI", 8))
        self.txt_max_count.setFixedSize(36, 18)
        self.txt_max_count.setAlignment(Qt.AlignmentFlag.AlignCenter)
        mc_row.addWidget(self.txt_max_count)
        lbl_mc = QLabel("Max Count")
        lbl_mc.setFont(QFont("Segoe UI", 8))
        mc_row.addWidget(lbl_mc)
        count_stack.addLayout(mc_row)

        self.lbl_result_count = QLabel("Result count:")
        self.lbl_result_count.setFont(QFont("Segoe UI", 8))
        count_stack.addWidget(self.lbl_result_count)

        btm.addLayout(count_stack)
        btm.addSpacing(12)

        # 5) Timing labels
        time_stack = QVBoxLayout()
        time_stack.setSpacing(0)
        time_stack.setContentsMargins(0, 0, 0, 0)
        self.lbl_query_time = QLabel("Query time:")
        self.lbl_print_time = QLabel("Print time:")
        self.lbl_total_time = QLabel("Total time:")
        for lbl in (self.lbl_query_time, self.lbl_print_time, self.lbl_total_time):
            lbl.setFont(QFont("Segoe UI", 8))
            time_stack.addWidget(lbl)
        btm.addLayout(time_stack)

        btm.addSpacing(12)

        # 6) Run Audit (far right)
        self.btn_run = QPushButton("Run\nAudit")
        self.btn_run.setFont(QFont("Segoe UI", 9, QFont.Weight.Bold))
        self.btn_run.setFixedSize(60, 36)
        self.btn_run.setStyleSheet(_RUN_BTN_STYLE)
        self.btn_run.clicked.connect(self._run_audit)
        btm.addWidget(self.btn_run)

        root.addWidget(self.bottom_bar)

    # ── Tab management ───────────────────────────────────────────────

    def _add_criteria_tab(self, name: str) -> DynamicTab:
        tab = DynamicTab(tab_name=name)
        self._criteria_tabs.append(tab)
        # Insert before Results/SQL
        idx = max(self.tab_widget.count() - 2, 0)  # before Results, SQL
        self.tab_widget.insertTab(idx, tab, name)
        return tab

    def _on_tab_context_menu(self, pos):
        tab_bar = self.tab_widget.tabBar()
        tab_index = tab_bar.tabAt(pos)

        menu = QMenu(self)
        menu.setStyleSheet(
            "QMenu { background-color: white; border: 1px solid #1E5BA8;"
            " font-size: 9pt; }"
            "QMenu::item { padding: 3px 16px; }"
            "QMenu::item:selected { background-color: #A0C4E8; color: black; }"
        )

        act_add = menu.addAction("Add Tab")

        act_rename = None
        act_remove = None
        if tab_index >= 0:
            widget = self.tab_widget.widget(tab_index)
            # Only allow rename/remove for criteria tabs (not Results/SQL)
            if isinstance(widget, DynamicTab):
                act_rename = menu.addAction("Rename Tab")
                if len(self._criteria_tabs) > 1:
                    act_remove = menu.addAction("Remove Tab")

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
        if self.tables:
            self.lbl_active_table.setText(f"Table: {self.tables[0]}")
        self._tabs_dialog = None

    def _on_field_requested(self, table: str, column: str,
                            type_name: str, display: str):
        """Handle field placement request (double-click or drag) from Tables dialog."""
        # Place on the current criteria tab
        current = self.tab_widget.currentWidget()
        if not isinstance(current, DynamicTab):
            # Default to first criteria tab
            if self._criteria_tabs:
                current = self._criteria_tabs[0]
                self.tab_widget.setCurrentWidget(current)
            else:
                return
        current.add_field_auto(table, column, type_name, display or column)

    # ── Field display name context menu ──────────────────────────────

    def update_display_name(self, key: str, new_name: str):
        """Update display name for a field (single source of truth)."""
        self.display_names[key] = new_name
        # Update any FieldRow widgets that use this key
        for tab in self._criteria_tabs:
            row = tab.grid.field(key)
            if row is not None:
                row._lbl.setText(new_name)

    # ── Clear all ────────────────────────────────────────────────────

    def _clear_all(self):
        for tab in self._criteria_tabs:
            for row in list(tab.grid._rows):
                row.set_state({})
        self.txt_max_count.setText("25")
        self.lbl_result_count.setText("Result count:")
        self.lbl_query_time.setText("Query time:")
        self.lbl_print_time.setText("Print time:")
        self.lbl_total_time.setText("Total time:")

    def _set_all_rows(self):
        self.txt_max_count.setText("")

    # ── Run audit ────────────────────────────────────────────────────

    def _run_audit(self):
        if not self.tables:
            QMessageBox.warning(self, "No Tables",
                                "This group has no tables. Use the Tables "
                                "button to add tables.")
            return

        table_name = self.tables[0]  # query first table

        # Collect filters from ALL criteria tabs
        all_filters = []
        for tab in self._criteria_tabs:
            from .dynamic_query import collect_field_filters
            all_filters.extend(collect_field_filters(tab.grid))

        max_count = self.txt_max_count.text().strip()

        try:
            sql = build_dynamic_sql(table_name, max_count, all_filters)
        except Exception as exc:
            logger.exception("Failed to build dynamic SQL")
            QMessageBox.warning(self, "SQL Build Error", str(exc))
            return

        self.sql_tab.set_sql(sql)

        self.btn_run.setEnabled(False)
        self.btn_run.setText("Running...")
        self.lbl_query_time.setText("Query time:")
        self.lbl_print_time.setText("Print time:")
        self.lbl_total_time.setText("Total time:")
        self.lbl_result_count.setText("Result count:")
        QApplication.processEvents()

        t0 = time.time()
        try:
            conn = pyodbc.connect(f"DSN={self.dsn}", autocommit=True)
            cursor = conn.cursor()
            cursor.execute(sql)
            columns = [desc[0] for desc in cursor.description]
            rows = cursor.fetchall()
            conn.close()
            t_query = time.time() - t0

            t1 = time.time()
            df = pd.DataFrame([list(r) for r in rows], columns=columns)
            self.results_tab.set_results(df)
            t_print = time.time() - t1
            t_total = time.time() - t0

            self.lbl_query_time.setText(f"Query time:  {fmt_time(t_query)}")
            self.lbl_print_time.setText(f"Print time:  {fmt_time(t_print)}")
            self.lbl_total_time.setText(f"Total time:  {fmt_time(t_total)}")
            self.lbl_result_count.setText(f"Result count:   {len(df)}")

            self.tab_widget.setCurrentWidget(self.results_tab)

        except Exception as exc:
            logger.exception("Dynamic audit query failed")
            msg = str(exc)
            if hasattr(exc, 'args') and len(exc.args) >= 2:
                msg = f"{exc.args[0]}\n\n{exc.args[1]}"
            QMessageBox.warning(self, "Query Error", msg)
        finally:
            self.btn_run.setEnabled(True)
            self.btn_run.setText("Run\nAudit")

    # ── State persistence ────────────────────────────────────────────

    def get_config(self) -> dict:
        """Return the full group config for save."""
        return {
            "name": self.group_name,
            "dsn": self.dsn,
            "tables": self.tables,
            "display_names": self.display_names,
            "max_count": self.txt_max_count.text(),
            "tabs": [tab.get_state() for tab in self._criteria_tabs],
        }

    def set_config(self, config: dict):
        """Restore from a saved config."""
        self.display_names = config.get("display_names", {})
        self.tables = config.get("tables", self.tables)
        self.txt_max_count.setText(config.get("max_count", "25"))
        if self.tables:
            self.lbl_active_table.setText(f"Table: {self.tables[0]}")

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
                name = first_state.get("tab_name", "All")
                idx = self.tab_widget.indexOf(self._criteria_tabs[0])
                if idx >= 0:
                    self.tab_widget.setTabText(idx, name)

            # Create additional tabs
            for ts in tab_states[1:]:
                tab = self._add_criteria_tab(ts.get("tab_name", "Tab"))
                tab.set_state(ts)
