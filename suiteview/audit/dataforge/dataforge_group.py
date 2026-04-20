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
import textwrap
import time

import pandas as pd
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QFont
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QTabWidget,
    QLabel, QLineEdit, QPushButton, QMessageBox, QMenu,
    QApplication, QInputDialog, QTextEdit, QScrollArea,
)

from suiteview.audit.saved_query import SavedQuery
from suiteview.audit import saved_query_store as sq_store
from suiteview.audit.dataforge.dataforge_model import DataForge, DataForgeSource
from suiteview.audit.dataforge import dataforge_store as df_store
from suiteview.audit.tabs.field_row import FieldRow, FieldGrid
from suiteview.audit.tabs.results_tab import ResultsTab
from suiteview.audit.tabs.select_tab import SelectTab
from suiteview.audit.tabs.joins_tab import JoinsTab
from suiteview.audit.tabs._styles import _FONT
from suiteview.audit.sql_helpers import fmt_time
from suiteview.audit.ui.bottom_bar import AuditBottomBar
from suiteview.audit.query_runner import run_button_context, execute_odbc_query

logger = logging.getLogger(__name__)

_FONT_LABEL = QFont("Segoe UI", 9)
_FONT_BOLD = QFont("Segoe UI", 9, QFont.Weight.Bold)
_FONT_MONO = QFont("Consolas", 10)

_RUN_BTN_STYLE = (
    "QPushButton { background-color: #0D9488; color: white; border: 1px solid #0F766E;"
    " border-radius: 3px; }"
    "QPushButton:hover { background-color: #14B8A6; }"
)

_CLEAR_BTN_STYLE = (
    "QPushButton { background-color: #0D9488; color: white;"
    " border: 1px solid #0F766E; border-radius: 2px;"
    " padding: 1px 8px; font-size: 9pt; }"
    "QPushButton:hover { background-color: #14B8A6; }"
)

_SAVE_BTN_STYLE = (
    "QPushButton { background-color: #D4AF37; color: #0A1E5E;"
    " border: 1px solid #B8960F; border-radius: 3px;"
    " padding: 2px 10px; font-size: 9pt; font-weight: bold; }"
    "QPushButton:hover { background-color: #F4D03F; }"
)

_QUERIES_BTN_STYLE = (
    "QPushButton { background-color: #E6F5F3; color: #0D9488;"
    " border: 1px solid #0D9488; border-radius: 3px;"
    " padding: 2px 10px; font-size: 9pt; font-weight: bold; }"
    "QPushButton:hover { background-color: #B2DFDB; }"
)

_DATASET_BTN_STYLE = (
    "QPushButton { background-color: #E6F5F3; color: #0D9488;"
    " border: 1px solid #B2DFDB; border-radius: 3px;"
    " padding: 4px 12px; font-size: 9pt; }"
    "QPushButton:hover { background-color: #B2DFDB; }"
)

_DATASET_BTN_ACTIVE_STYLE = (
    "QPushButton { background-color: #0D9488; color: white;"
    " border: 1px solid #0F766E; border-radius: 3px;"
    " padding: 4px 12px; font-size: 9pt; font-weight: bold; }"
    "QPushButton:hover { background-color: #14B8A6; }"
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

class ForgeSqlTab(QWidget):
    """SQL tab showing a button per dataset and the SQL for the selected one."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._sqls: dict[str, str] = {}  # query_name → SQL
        self._active: str = ""
        self._build_ui()

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(4, 4, 4, 4)
        root.setSpacing(4)

        # ── Dataset buttons row ──────────────────────────────────
        self._btn_row = QHBoxLayout()
        self._btn_row.setSpacing(4)
        self._btn_row.setContentsMargins(0, 0, 0, 0)
        self._btn_row.addStretch()
        root.addLayout(self._btn_row)

        # ── SQL display ──────────────────────────────────────────
        self.txt_sql = QTextEdit()
        self.txt_sql.setFont(_FONT_MONO)
        self.txt_sql.setReadOnly(True)
        self.txt_sql.setStyleSheet(
            "QTextEdit { background-color: #FAFAFA; border: 1px solid #DDD;"
            " border-radius: 3px; }")

        # Syntax highlighting
        from suiteview.audit.tabs.sql_tab import _SqlHighlighter
        self._highlighter = _SqlHighlighter(self.txt_sql.document())

        root.addWidget(self.txt_sql, 1)

        self._buttons: dict[str, QPushButton] = {}

    def set_datasets(self, sqls: dict[str, str]):
        """Set the SQL for each dataset. Creates/updates buttons."""
        self._sqls = dict(sqls)

        # Clear old buttons
        for btn in self._buttons.values():
            self._btn_row.removeWidget(btn)
            btn.deleteLater()
        self._buttons.clear()

        # Remove stretch
        while self._btn_row.count():
            item = self._btn_row.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        # Create buttons
        for name in sqls:
            btn = QPushButton(name)
            btn.setFont(QFont("Segoe UI", 9))
            btn.setStyleSheet(_DATASET_BTN_STYLE)
            btn.clicked.connect(lambda checked, n=name: self._select_dataset(n))
            self._btn_row.addWidget(btn)
            self._buttons[name] = btn
        self._btn_row.addStretch()

        # Auto-select first
        if sqls:
            first = next(iter(sqls))
            self._select_dataset(first)
        else:
            self.txt_sql.clear()
            self._active = ""

    def _select_dataset(self, name: str):
        self._active = name
        # Update button styles
        for n, btn in self._buttons.items():
            if n == name:
                btn.setStyleSheet(_DATASET_BTN_ACTIVE_STYLE)
            else:
                btn.setStyleSheet(_DATASET_BTN_STYLE)
        # Show SQL
        from suiteview.audit.tabs.sql_tab import _format_sql
        sql = self._sqls.get(name, "")
        self.txt_sql.setPlainText(_format_sql(sql) if sql else "")


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
        lbl.setStyleSheet("color: #0D9488;")
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
            "QPushButton { background-color: #0D9488; color: white;"
            " border: 1px solid #0F766E; border-radius: 3px;"
            " padding: 2px 12px; }"
            "QPushButton:hover { background-color: #14B8A6; }")
        btn_copy.clicked.connect(self._copy_code)
        root.addWidget(btn_copy)

    def set_code(self, code: str):
        self.txt_code.setPlainText(code)

    def _copy_code(self):
        QApplication.clipboard().setText(self.txt_code.toPlainText())


# ── Joins Tab for DataForge ──────────────────────────────────────────

class ForgeJoinsTab(QWidget):
    """Configure pandas merge operations between query datasets."""
    state_changed = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._joins: list[dict] = []  # [{left, right, left_on, right_on, how}]
        self._query_names: list[str] = []
        self._build_ui()

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(4, 4, 4, 4)
        root.setSpacing(4)

        lbl = QLabel("Merge Operations — link query datasets together")
        lbl.setFont(QFont("Segoe UI", 9, QFont.Weight.Bold))
        lbl.setStyleSheet("color: #0D9488;")
        root.addWidget(lbl)

        self._joins_container = QVBoxLayout()
        self._joins_container.setSpacing(4)
        root.addLayout(self._joins_container)

        root.addStretch()

        btn_add = QPushButton("+ Add Merge")
        btn_add.setFont(QFont("Segoe UI", 9))
        btn_add.setFixedHeight(28)
        btn_add.setStyleSheet(
            "QPushButton { background: #0D9488; color: white; border: none;"
            " border-radius: 3px; padding: 2px 12px; }"
            "QPushButton:hover { background: #0F766E; }")
        btn_add.clicked.connect(self._add_join_card)
        root.addWidget(btn_add)

    def update_queries(self, query_names: list[str]):
        self._query_names = list(query_names)
        # Update combos in existing cards
        for i in range(self._joins_container.count()):
            item = self._joins_container.itemAt(i)
            if item and item.widget():
                card = item.widget()
                for combo in card.findChildren(QPushButton):
                    pass  # cards will be rebuilt

    def _add_join_card(self):
        """Add a merge configuration card."""
        from PyQt6.QtWidgets import QComboBox, QFrame
        card = QFrame()
        card.setFrameShape(QFrame.Shape.StyledPanel)
        card.setStyleSheet(
            "QFrame { background: #E6F5F3; border: 1px solid #B2DFDB;"
            " border-radius: 4px; padding: 4px; }")
        lay = QHBoxLayout(card)
        lay.setContentsMargins(8, 4, 8, 4)
        lay.setSpacing(6)

        cmb_left = QComboBox()
        cmb_left.setFont(_FONT)
        cmb_left.addItems(self._query_names)
        cmb_left.setMinimumWidth(100)
        lay.addWidget(QLabel("Left:"))
        lay.addWidget(cmb_left)

        txt_left_on = QLineEdit()
        txt_left_on.setFont(_FONT)
        txt_left_on.setPlaceholderText("left key column")
        txt_left_on.setMinimumWidth(100)
        lay.addWidget(QLabel("on"))
        lay.addWidget(txt_left_on)

        from PyQt6.QtWidgets import QComboBox as _CB
        cmb_how = QComboBox()
        cmb_how.setFont(_FONT)
        cmb_how.addItems(["inner", "left", "right", "outer"])
        cmb_how.setFixedWidth(70)
        lay.addWidget(cmb_how)

        cmb_right = QComboBox()
        cmb_right.setFont(_FONT)
        cmb_right.addItems(self._query_names)
        cmb_right.setMinimumWidth(100)
        lay.addWidget(QLabel("Right:"))
        lay.addWidget(cmb_right)

        txt_right_on = QLineEdit()
        txt_right_on.setFont(_FONT)
        txt_right_on.setPlaceholderText("right key column")
        txt_right_on.setMinimumWidth(100)
        lay.addWidget(QLabel("on"))
        lay.addWidget(txt_right_on)

        btn_remove = QPushButton("X")
        btn_remove.setFont(QFont("Segoe UI", 8, QFont.Weight.Bold))
        btn_remove.setFixedSize(20, 20)
        btn_remove.setStyleSheet(
            "QPushButton { background: #EF4444; color: white; border: none;"
            " border-radius: 2px; }"
            "QPushButton:hover { background: #DC2626; }")
        btn_remove.clicked.connect(lambda: self._remove_join_card(card))
        lay.addWidget(btn_remove)

        # Store references on card
        card._cmb_left = cmb_left
        card._cmb_right = cmb_right
        card._txt_left_on = txt_left_on
        card._txt_right_on = txt_right_on
        card._cmb_how = cmb_how

        # Signal changes
        for w in (cmb_left, cmb_right, cmb_how):
            w.currentIndexChanged.connect(lambda: self.state_changed.emit())
        for w in (txt_left_on, txt_right_on):
            w.textChanged.connect(lambda: self.state_changed.emit())

        self._joins_container.addWidget(card)
        self.state_changed.emit()

    def _remove_join_card(self, card):
        self._joins_container.removeWidget(card)
        card.deleteLater()
        self.state_changed.emit()

    def get_merge_ops(self) -> list[dict]:
        """Return list of merge operation dicts."""
        ops = []
        for i in range(self._joins_container.count()):
            item = self._joins_container.itemAt(i)
            if not item or not item.widget():
                continue
            card = item.widget()
            if not hasattr(card, '_cmb_left'):
                continue
            ops.append({
                "left": card._cmb_left.currentText(),
                "right": card._cmb_right.currentText(),
                "left_on": card._txt_left_on.text().strip(),
                "right_on": card._txt_right_on.text().strip(),
                "how": card._cmb_how.currentText(),
            })
        return ops

    def get_state(self) -> dict:
        return {"merges": self.get_merge_ops()}

    def set_state(self, state: dict):
        # Clear existing
        while self._joins_container.count():
            item = self._joins_container.takeAt(0)
            if item and item.widget():
                item.widget().deleteLater()
        # Rebuild
        for m in state.get("merges", []):
            self._add_join_card()
            card = self._joins_container.itemAt(
                self._joins_container.count() - 1).widget()
            idx = card._cmb_left.findText(m.get("left", ""))
            if idx >= 0:
                card._cmb_left.setCurrentIndex(idx)
            idx = card._cmb_right.findText(m.get("right", ""))
            if idx >= 0:
                card._cmb_right.setCurrentIndex(idx)
            card._txt_left_on.setText(m.get("left_on", ""))
            card._txt_right_on.setText(m.get("right_on", ""))
            idx = card._cmb_how.findText(m.get("how", "inner"))
            if idx >= 0:
                card._cmb_how.setCurrentIndex(idx)


# ── Display Tab for DataForge ────────────────────────────────────────

class ForgeDisplayTab(QWidget):
    """Select which columns to include in final DataForge output."""
    state_changed = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._all_columns: list[str] = []
        self._selected: set[str] = set()
        self.display_all = True
        self._build_ui()

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(4, 4, 4, 4)
        root.setSpacing(4)

        top_row = QHBoxLayout()
        from PyQt6.QtWidgets import QCheckBox
        self.chk_all = QCheckBox("Display All Columns")
        self.chk_all.setFont(_FONT_BOLD)
        self.chk_all.setChecked(True)
        self.chk_all.toggled.connect(self._on_toggle_all)
        top_row.addWidget(self.chk_all)
        top_row.addStretch()
        root.addLayout(top_row)

        from PyQt6.QtWidgets import QListWidget, QAbstractItemView
        self.list_cols = QListWidget()
        self.list_cols.setFont(_FONT)
        self.list_cols.setSelectionMode(
            QAbstractItemView.SelectionMode.MultiSelection)
        self.list_cols.setEnabled(False)
        self.list_cols.itemSelectionChanged.connect(self._on_selection_changed)
        root.addWidget(self.list_cols, 1)

        self.lbl_count = QLabel("")
        self.lbl_count.setFont(QFont("Segoe UI", 8))
        self.lbl_count.setStyleSheet("color: #666;")
        root.addWidget(self.lbl_count)

    def set_columns(self, columns: list[str]):
        """Set available columns from merged datasets."""
        self._all_columns = list(columns)
        self.list_cols.clear()
        for col in columns:
            self.list_cols.addItem(col)
        self.lbl_count.setText(f"{len(columns)} columns available")

    def _on_toggle_all(self, checked: bool):
        self.display_all = checked
        self.list_cols.setEnabled(not checked)
        self.state_changed.emit()

    def _on_selection_changed(self):
        self._selected = {
            self.list_cols.item(i).text()
            for i in range(self.list_cols.count())
            if self.list_cols.item(i).isSelected()
        }
        self.state_changed.emit()

    def get_selected_columns(self) -> list[str]:
        if self.display_all:
            return list(self._all_columns)
        return [c for c in self._all_columns if c in self._selected]

    def get_state(self) -> dict:
        return {
            "display_all": self.display_all,
            "selected": list(self._selected),
        }

    def set_state(self, state: dict):
        self.display_all = state.get("display_all", True)
        self.chk_all.setChecked(self.display_all)
        selected = set(state.get("selected", []))
        for i in range(self.list_cols.count()):
            item = self.list_cols.item(i)
            item.setSelected(item.text() in selected)


# ═════════════════════════════════════════════════════════════════════
# DataForgeGroup — main designer widget
# ═════════════════════════════════════════════════════════════════════

class DataForgeGroup(QWidget):
    """Complete designer widget for a DataForge.

    Contains tab widget + bottom bar. Similar structure to DynamicQuery
    but operates on saved queries instead of direct tables.
    """
    config_changed = pyqtSignal()
    forge_saved = pyqtSignal(object)      # DataForge
    forge_deleted = pyqtSignal(str)       # forge name

    def __init__(self, name: str, parent=None, saved_forge_name: str = ""):
        super().__init__(parent)
        self.forge_name = name
        self._saved_forge_name = saved_forge_name

        # Source queries: name → SavedQuery
        self._sources: dict[str, SavedQuery] = {}
        self._datasets: dict[str, pd.DataFrame] = {}  # in-memory query results
        self._queries_dialog = None
        self._loading = False
        self._dirty = False

        self._build_ui()

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(2)

        # ── Tab widget ───────────────────────────────────────────────
        self.tab_widget = QTabWidget()
        self.tab_widget.setFont(_FONT)
        self.tab_widget.setStyleSheet(
            "QTabWidget::pane { border-top: 3px solid #0D9488;"
            " border-bottom: 3px solid #0D9488;"
            " border-left: 1px solid #999; border-right: 1px solid #999;"
            " background-color: #E6F5F3; }"
            "QTabBar { background-color: #E6F5F3; }"
            "QTabBar::tab { padding: 2px 8px; min-height: 20px; font-size: 9pt;"
            " background-color: #B2DFDB; border: 1px solid #0D9488;"
            " border-bottom: none; border-top-left-radius: 3px;"
            " border-top-right-radius: 3px; margin-right: 1px; }"
            "QTabBar::tab:selected { font-weight: bold;"
            " background-color: #E6F5F3; color: #004D40; }"
            "QTabBar::tab:!selected { background-color: #B2DFDB; color: #444; }"
            "QTabBar::tab:hover:!selected { background-color: #80CBC4; }"
        )

        # Filter tab
        self._filter_tabs: list[ForgeFilterTab] = []
        self._add_filter_tab("Filter")

        # Joins tab
        self.joins_tab = ForgeJoinsTab()
        self.tab_widget.addTab(self.joins_tab, "Joins")

        # Display tab
        self.display_tab = ForgeDisplayTab()
        self.tab_widget.addTab(self.display_tab, "Display")

        # Results tab
        self.results_tab = ResultsTab()
        self.tab_widget.addTab(self.results_tab, "Results")

        # SQL tab (per-dataset)
        self.sql_tab = ForgeSqlTab()
        self.tab_widget.addTab(self.sql_tab, "SQL")

        # Code tab (Python/pandas)
        self.code_tab = ForgeCodeTab()
        self.tab_widget.addTab(self.code_tab, "Code")

        root.addWidget(self.tab_widget, 1)

        # ── Bottom bar ───────────────────────────────────────────────
        self.bottom_bar = AuditBottomBar(
            bg_color="#E6F5F3", run_label="Run\nForge",
            run_style=_RUN_BTN_STYLE)

        # Convenience aliases
        self.btn_all = self.bottom_bar.btn_all
        self.txt_max_count = self.bottom_bar.txt_max_count
        self.lbl_result_count = self.bottom_bar.lbl_result_count
        self.lbl_query_time = self.bottom_bar.lbl_query_time
        self.lbl_print_time = self.bottom_bar.lbl_print_time
        self.lbl_total_time = self.bottom_bar.lbl_total_time
        self.btn_run = self.bottom_bar.btn_run

        # Left side: forge name label
        self._lbl_name = QLabel(self.forge_name)
        self._lbl_name.setFont(QFont("Segoe UI", 14, QFont.Weight.Bold))
        self._lbl_name.setStyleSheet("QLabel { color: #0D9488; }")
        self.bottom_bar.left_layout.addWidget(self._lbl_name)

        # Action buttons: Save / Save As / Delete
        self.btn_save = QPushButton("Save")
        self.btn_save.setFont(_FONT_BOLD)
        self.btn_save.setFixedSize(55, 36)
        self.btn_save.setStyleSheet(_SAVE_BTN_STYLE)
        self.btn_save.clicked.connect(self._save_or_update)
        self.bottom_bar.action_layout.addWidget(self.btn_save)

        self.btn_save_as = QPushButton("Save As")
        self.btn_save_as.setFont(_FONT_BOLD)
        self.btn_save_as.setFixedSize(65, 36)
        self.btn_save_as.setStyleSheet(_SAVE_BTN_STYLE)
        self.btn_save_as.clicked.connect(self._save_forge)
        self.bottom_bar.action_layout.addWidget(self.btn_save_as)

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

    # ── Tab management ───────────────────────────────────────────────

    def _add_filter_tab(self, name: str) -> ForgeFilterTab:
        tab = ForgeFilterTab(
            tab_name=name, unique_provider=self.get_unique_values)
        self._filter_tabs.append(tab)
        idx = max(self.tab_widget.count() - 5, 0)  # before Joins/Display/Results/SQL/Code
        self.tab_widget.insertTab(idx, tab, name)
        tab.grid.state_changed.connect(self._schedule_save)
        return tab

    # ── Source management ────────────────────────────────────────────

    def _open_queries_dialog(self):
        """Open the Queries && Fields dialog (mirrors Tables dialog)."""
        if self._queries_dialog is not None and self._queries_dialog.isVisible():
            self._queries_dialog.raise_()
            return

        from suiteview.audit.dataforge.queries_dialog import QueriesFieldsDialog
        dlg = QueriesFieldsDialog(self._sources, self)
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
        new_sources = dlg.get_sources()
        self._sources = new_sources
        self.joins_tab.update_queries(list(self._sources.keys()))
        self._schedule_save()
        self._queries_dialog = None

    def _on_sources_changed(self, names: list[str]):
        """Handle live source changes from the dialog."""
        # Reload sources from the dialog
        if self._queries_dialog:
            self._sources = self._queries_dialog.get_sources()
            self.joins_tab.update_queries(list(self._sources.keys()))
            self._schedule_save()

    def add_source_query(self, sq: SavedQuery):
        """Programmatically add a source query."""
        self._sources[sq.name] = sq
        self.joins_tab.update_queries(list(self._sources.keys()))

    # ── Field placement (from picker) ────────────────────────────────

    def on_field_requested(self, query_name: str, col_name: str):
        """Handle field placement from QueryFieldPicker."""
        current = self.tab_widget.currentWidget()
        if isinstance(current, ForgeDisplayTab):
            # If Display tab is active, the field is already in the list
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
        if not sq or not sq.sql:
            QMessageBox.warning(
                self, "Missing SQL",
                f"Query \"{query_name}\" has no SQL. Run and re-save it first.")
            return
        QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
        try:
            columns, rows = execute_odbc_query(sq.dsn, sq.sql)
            df = pd.DataFrame([list(r) for r in rows], columns=columns)
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
        if not sq or not sq.sql:
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
                columns, rows = execute_odbc_query(sq.dsn, sq.sql)
                df = pd.DataFrame([list(r) for r in rows], columns=columns)
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
        """Execute all source queries, merge with pandas, apply filters."""
        if not self._sources:
            QMessageBox.warning(self, "No Sources",
                                "Add at least one saved query via the Queries button.")
            return

        with run_button_context(
            self.btn_run, bar=self.bottom_bar,
            restore_text="Run\nForge",
        ):
            t0 = time.time()
            datasets: dict[str, pd.DataFrame] = {}
            sqls: dict[str, str] = {}

            try:
                # Step 1: Execute each source query's SQL
                for name, sq in self._sources.items():
                    if not sq.sql:
                        QMessageBox.warning(
                            self, "Missing SQL",
                            f"Query \"{name}\" has no SQL. Run and re-save it first.")
                        return
                    sqls[name] = sq.sql
                    columns, rows = execute_odbc_query(sq.dsn, sq.sql)
                    datasets[name] = pd.DataFrame(
                        [list(r) for r in rows], columns=columns)

                # Cache datasets so field picker can see them
                self._datasets.update(datasets)
                # Notify open dialog about data availability
                if self._queries_dialog and self._queries_dialog.isVisible():
                    self._queries_dialog.update_data_status(set(self._datasets.keys()))

                t_query = time.time() - t0

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
                selected_cols = self.display_tab.get_selected_columns()
                if selected_cols and not self.display_tab.display_all:
                    available = [c for c in selected_cols if c in result.columns]
                    if available:
                        result = result[available]

                # Step 5: Apply max count
                max_count = self.txt_max_count.text().strip()
                if max_count.isdigit():
                    result = result.head(int(max_count))

                t_print = time.time() - t1
                t_total = time.time() - t0

                # Update Display tab with available columns
                self.display_tab.set_columns(list(result.columns))

                # Show results
                self.results_tab.set_results(result)
                self.lbl_query_time.setText(f"Query time:  {fmt_time(t_query)}")
                self.lbl_print_time.setText(f"Merge time:  {fmt_time(t_print)}")
                self.lbl_total_time.setText(f"Total time:  {fmt_time(t_total)}")
                self.lbl_result_count.setText(f"Result count:   {len(result)}")

                # Update SQL tab with per-dataset SQL
                self.sql_tab.set_datasets(sqls)

                # Generate Python code
                code = self._generate_python_code(sqls, merge_ops, max_count)
                self.code_tab.set_code(code)

                self.tab_widget.setCurrentWidget(self.results_tab)

            except Exception as exc:
                logger.exception("DataForge execution failed")
                msg = str(exc)
                if hasattr(exc, 'args') and len(exc.args) >= 2:
                    msg = f"{exc.args[0]}\n\n{exc.args[1]}"
                QMessageBox.warning(self, "DataForge Error", msg)

    def _apply_pandas_filters(self, df: pd.DataFrame,
                              tab: ForgeFilterTab) -> pd.DataFrame:
        """Apply filter criteria from a ForgeFilterTab to a DataFrame."""
        from suiteview.audit.dynamic_query import collect_field_filters

        filters = collect_field_filters(tab.grid)
        for filt in filters:
            key = filt.get("key", "")
            # key format: "query_name.column_name"
            parts = key.split(".", 1)
            if len(parts) != 2:
                continue
            col_name = parts[1]
            if col_name not in df.columns:
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
                lo = filt.get("lo", "")
                hi = filt.get("hi", "")
                if lo:
                    try:
                        df = df[df[col_name] >= type(df[col_name].iloc[0])(lo)]
                    except (ValueError, IndexError, TypeError):
                        pass
                if hi:
                    try:
                        df = df[df[col_name] <= type(df[col_name].iloc[0])(hi)]
                    except (ValueError, IndexError, TypeError):
                        pass
            elif mode == "list":
                items = filt.get("items", [])
                if items:
                    df = df[df[col_name].astype(str).isin(items)]

        return df

    # ── Python code generation ───────────────────────────────────────

    def _generate_python_code(self, sqls: dict[str, str],
                              merge_ops: list[dict],
                              max_count: str) -> str:
        """Generate real, runnable Python code that reproduces the DataForge."""
        lines = [
            "import pandas as pd",
            "import pyodbc",
            "",
            "# ── Load datasets ──────────────────────────────────────────",
        ]

        for name, sq in self._sources.items():
            safe = name.replace('"', '\\"')
            dsn = sq.dsn.replace('"', '\\"')
            sql = sqls.get(name, sq.sql).replace('"""', '\\"""')
            lines.extend([
                f"",
                f'# Dataset: {safe}',
                f'conn_{_var(name)} = pyodbc.connect("DSN={dsn}", autocommit=True)',
                f'df_{_var(name)} = pd.read_sql("""',
                f'{sql}',
                f'""", conn_{_var(name)})',
                f'conn_{_var(name)}.close()',
            ])

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

    def _generate_filter_code(self) -> list[str]:
        """Generate pandas filter code from filter tabs."""
        from suiteview.audit.dynamic_query import collect_field_filters
        lines = []
        for tab in self._filter_tabs:
            filters = collect_field_filters(tab.grid)
            for filt in filters:
                key = filt.get("key", "")
                parts = key.split(".", 1)
                if len(parts) != 2:
                    continue
                col = parts[1]
                mode = filt.get("mode", "contains")
                value = filt.get("value", "")

                if mode == "contains" and value:
                    lines.append(
                        f'result = result[result["{col}"].astype(str)'
                        f'.str.contains("{value}", case=False, na=False)]')
                elif mode == "regex" and value:
                    lines.append(
                        f'result = result[result["{col}"].astype(str)'
                        f'.str.contains(r"{value}", case=False, na=False)]')
                elif mode == "range":
                    lo = filt.get("lo", "")
                    hi = filt.get("hi", "")
                    if lo:
                        lines.append(f'result = result[result["{col}"] >= "{lo}"]')
                    if hi:
                        lines.append(f'result = result[result["{col}"] <= "{hi}"]')
                elif mode == "list":
                    items = filt.get("items", [])
                    if items:
                        lines.append(
                            f'result = result[result["{col}"].astype(str)'
                            f'.isin({items!r})]')
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
            sources=[DataForgeSource(query_name=n) for n in self._sources],
            config=self.get_config(),
        )
        df_store.save_forge(forge)
        self._dirty = False
        self.forge_saved.emit(forge)
        QMessageBox.information(self, "DataForge Saved",
                                f"DataForge \"{name}\" updated.")

    def _save_forge(self):
        name, ok = QInputDialog.getText(
            self, "Save DataForge", "DataForge name:",
            text=self._saved_forge_name or "")
        if not ok or not name.strip():
            return
        name = name.strip()

        if df_store.forge_exists(name):
            reply = QMessageBox.question(
                self, "Overwrite?",
                f"A DataForge named \"{name}\" already exists.\nOverwrite?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No)
            if reply != QMessageBox.StandardButton.Yes:
                return

        forge = DataForge(
            name=name,
            sources=[DataForgeSource(query_name=n) for n in self._sources],
            config=self.get_config(),
        )
        df_store.save_forge(forge)
        self._dirty = False
        self._saved_forge_name = name
        self.forge_saved.emit(forge)
        QMessageBox.information(self, "DataForge Saved",
                                f"DataForge \"{name}\" saved.")

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
        self.forge_deleted.emit(name)

    # ── State persistence ────────────────────────────────────────────

    def get_config(self) -> dict:
        return {
            "name": self.forge_name,
            "sources": list(self._sources.keys()),
            "max_count": self.txt_max_count.text(),
            "filter_tabs": [t.get_state() for t in self._filter_tabs],
            "joins_tab": self.joins_tab.get_state(),
            "display_tab": self.display_tab.get_state(),
        }

    def set_config(self, config: dict):
        self._loading = True
        try:
            self.txt_max_count.setText(config.get("max_count", "25"))

            # Restore sources
            for name in config.get("sources", []):
                sq = sq_store.load_query(name)
                if sq:
                    self._sources[name] = sq
            self.joins_tab.update_queries(list(self._sources.keys()))

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

        finally:
            self._loading = False
            self._dirty = False


def _var(name: str) -> str:
    """Convert a query name to a valid Python variable suffix."""
    import re
    return re.sub(r'[^a-zA-Z0-9_]', '_', name).strip('_').lower() or "data"
