"""
Audit Window — main container with VBA-faithful tab strip and bottom bar.
Tabs: Policy | Policy (2) | Coverages | ADV | WL | DI | Benefits |
      Transaction | Results | Display | SQL
Bottom bar: Region combo, System Code combo, query/print/total time,
            All button, Max Count field, Result count label, Run Audit button.
"""
from __future__ import annotations
import logging
import time
import pandas as pd
from PyQt6.QtCore import Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QFont
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QTabWidget,
    QLabel, QComboBox, QPushButton,
    QMessageBox, QMenu, QInputDialog,
    QSplitter,
)
from suiteview.core.db2_constants import DEFAULT_REGION
from suiteview.ui.widgets.frameless_window import FramelessWindowBase
from .constants import REGION_ITEMS, SYSTEM_CODE_ITEMS
from .tabs.policy_tab import PolicyTab
from .tabs.policy2_tab import Policy2Tab
from .tabs.coverages_tab import CoveragesTab
from .tabs.adv_tab import AdvTab
from .tabs.wl_tab import WlTab
from .tabs.di_tab import DiTab
from .tabs.benefits_tab import BenefitsTab
from .tabs.transaction_tab import TransactionTab
from .tabs.display_tab import DisplayTab
from .tabs.results_tab import ResultsTab
from .tabs.sql_tab import SqlTab
from .tabs.plancode_tab import PlancodeTab
from .tabs.build_sql_tab import BuildSqlTab
from .tabs.build_sql_results_tab import BuildSqlResultsTab
from .tabs._styles import style_combo as _style_combo
from suiteview.core.db2_connection import DB2Connection
from suiteview.core.db2_constants import DEFAULT_SCHEMA, REGION_SCHEMA_MAP
from .cyberlife_query import build_cyberlife_sql
from .sql_helpers import fmt_time
from .dynamic_group import DynamicQuery
from .field_picker_panel import FieldPickerPanel
from .group_config import load_ui_settings, save_ui_settings
from .ui.bottom_bar import AuditBottomBar
from .query_runner import run_button_context
from suiteview.audit.dataforge.dataforge_group import DataForgeGroup
logger = logging.getLogger(__name__)
_FONT = QFont("Segoe UI", 9)
# Theme — default SuiteView blue header, gold border
_HEADER_COLORS = ("#1E5BA8", "#0D3A7A", "#082B5C")
_BORDER_COLOR = "#D4A017"
class AuditWindow(FramelessWindowBase):
    """Top-level audit window, replicating VBA frmAudit layout."""
    def __init__(self, region: str = DEFAULT_REGION, parent=None):
        self._region = region
        super().__init__(
            title="SuiteView - Audit Tool",
            default_size=(1215, 720),
            min_size=(1100, 680),
            parent=parent,
            header_colors=_HEADER_COLORS,
            border_color=_BORDER_COLOR,
        )
    # ── UI construction ──────────────────────────────────────────────
    def build_content(self) -> QWidget:
        body = QWidget()
        body.setStyleSheet(
            "QWidget { background-color: #F0F0F0; }"
            "QLineEdit { background-color: white; border: 1px solid #888;"
            "  border-top: 2px solid #666; border-left: 2px solid #666;"
            "  padding: 1px 3px; }"
            "QComboBox { background-color: white; border: 1px solid #888;"
            "  border-top: 2px solid #666; border-left: 2px solid #666;"
            "  padding: 1px 3px; }"
            "QComboBox::drop-down { border-left: 1px solid #888;"
            "  width: 16px; subcontrol-position: right center; }"
            "QComboBox::down-arrow { image: none; border-left: 4px solid transparent;"
            "  border-right: 4px solid transparent; border-top: 5px solid #444;"
            "  width: 0px; height: 0px; margin-right: 3px; }"
            "QComboBox QAbstractItemView { border: 1px solid #888;"
            "  background-color: white; selection-background-color: #A0C4E8;"
            "  selection-color: black; outline: none; }"
            "QComboBox QAbstractItemView::item { padding: 0px 3px;"
            "  min-height: 16px; max-height: 16px; }"
        )
        root = QVBoxLayout(body)
        root.setContentsMargins(2, 0, 2, 2)
        root.setSpacing(2)
        # ── Mode tracking ─────────────────────────────────────────
        self._current_mode = "cyberlife"
        # Registry and +Group buttons — placed in the window header bar
        _HEADER_BTN_STYLE = (
            "QPushButton { background-color: rgba(255,255,255,0.15); color: white;"
            " border: 1px solid rgba(255,255,255,0.3); border-radius: 3px;"
            " padding: 2px 10px; font-size: 8pt; }"
            "QPushButton:hover { background-color: rgba(255,255,255,0.25); }"
        )
        self.btn_registry = QPushButton("Registry")
        self.btn_registry.setFont(QFont("Segoe UI", 8))
        self.btn_registry.setFixedHeight(24)
        self.btn_registry.setStyleSheet(_HEADER_BTN_STYLE)
        self.btn_registry.setToolTip("Open the Unique Value Registry viewer")
        self.btn_registry.clicked.connect(self._open_registry)
        # Cyberlife header button (view toggle)
        _CYB_HDR_BTN_STYLE = (
            "QPushButton { background-color: rgba(10,42,92,0.8); color: white;"
            " border: 1px solid rgba(10,42,92,0.9); border-radius: 3px;"
            " padding: 2px 10px; font-size: 8pt; }"
            "QPushButton:hover { background-color: rgba(30,91,168,0.8); }"
            "QPushButton:checked { background-color: #0A2A5C;"
            " border: 1px solid #061D40; }"
        )
        self.btn_cyberlife = QPushButton("Cyberlife")
        self.btn_cyberlife.setFont(QFont("Segoe UI", 8))
        self.btn_cyberlife.setFixedHeight(24)
        self.btn_cyberlife.setCheckable(True)
        self.btn_cyberlife.setChecked(True)
        self.btn_cyberlife.setStyleSheet(_CYB_HDR_BTN_STYLE)
        self.btn_cyberlife.setToolTip("Switch to the Cyberlife audit view")
        self.btn_cyberlife.clicked.connect(self._on_cyberlife_header_clicked)
        _WB_BTN_STYLE = (
            "QPushButton { background-color: rgba(124,58,237,0.7); color: white;"
            " border: 1px solid rgba(124,58,237,0.9); border-radius: 3px;"
            " padding: 2px 10px; font-size: 8pt; }"
            "QPushButton:hover { background-color: rgba(139,92,246,0.8); }"
            "QPushButton:checked { background-color: #7C3AED;"
            " border: 1px solid #6D28D9; }"
        )
        self.btn_workbench = QPushButton("Queries")
        self.btn_workbench.setFont(QFont("Segoe UI", 8))
        self.btn_workbench.setFixedHeight(24)
        self.btn_workbench.setCheckable(True)
        self.btn_workbench.setStyleSheet(_WB_BTN_STYLE)
        self.btn_workbench.setToolTip("Switch to the Queries view")
        self.btn_workbench.clicked.connect(self._toggle_saved_queries_shelf)
        _DF_BTN_STYLE = (
            "QPushButton { background-color: rgba(13,148,136,0.7); color: white;"
            " border: 1px solid rgba(13,148,136,0.9); border-radius: 3px;"
            " padding: 2px 10px; font-size: 8pt; }"
            "QPushButton:hover { background-color: rgba(20,184,166,0.8); }"
            "QPushButton:checked { background-color: #0D9488;"
            " border: 1px solid #0F766E; }"
        )
        self.btn_dataforge = QPushButton("DataForge")
        self.btn_dataforge.setFont(QFont("Segoe UI", 8))
        self.btn_dataforge.setFixedHeight(24)
        self.btn_dataforge.setCheckable(True)
        self.btn_dataforge.setStyleSheet(_DF_BTN_STYLE)
        self.btn_dataforge.setToolTip("Switch to the DataForge view")
        self.btn_dataforge.clicked.connect(self._toggle_dataforge_shelf)
        # Insert into header bar layout before window control buttons
        header_layout = self.header_bar.layout()
        insert_pos = header_layout.count() - 3  # before min/max/close
        header_layout.insertWidget(insert_pos, self.btn_registry)
        header_layout.insertWidget(insert_pos + 1, self.btn_cyberlife)
        header_layout.insertWidget(insert_pos + 2, self.btn_workbench)
        header_layout.insertWidget(insert_pos + 3, self.btn_dataforge)
        # Dynamic query storage
        self._dynamic_queries: dict[str, DynamicQuery] = {}
        # Track which unpinned query is currently active
        self._active_unpinned: str | None = None
        # Track last active query/forge mode for restoring on space switch
        self._last_query_mode: str | None = None
        self._last_forge_mode: str | None = None
        # ── Main content area (tabs + bottom bars + dynamic queries) ──
        self._content_left = QWidget()
        self._content_left.setMinimumWidth(400)
        _left_lay = QVBoxLayout(self._content_left)
        _left_lay.setContentsMargins(0, 0, 0, 0)
        _left_lay.setSpacing(2)
        # ── Tab widget ──────────────────────────────────────────────
        self.tabs = QTabWidget()
        self.tabs.setFont(_FONT)
        self.tabs.setStyleSheet(self._CYB_TAB_STYLE)
        # Policy tab (fully built)
        self.policy_tab = PolicyTab()
        self.tabs.addTab(self.policy_tab, "Policy")
        # Policy (2) tab
        self.policy2_tab = Policy2Tab()
        self.tabs.addTab(self.policy2_tab, "Policy (2)")
        # Coverages tab
        self.coverages_tab = CoveragesTab()
        self.tabs.addTab(self.coverages_tab, "Coverages")
        # ADV tab
        self.adv_tab = AdvTab()
        self.tabs.addTab(self.adv_tab, "ADV")
        # WL tab
        self.wl_tab = WlTab()
        self.tabs.addTab(self.wl_tab, "WL")
        # DI tab
        self.di_tab = DiTab()
        self.tabs.addTab(self.di_tab, "DI")
        # Benefits tab
        self.benefits_tab = BenefitsTab()
        self.tabs.addTab(self.benefits_tab, "Benefits")
        # Transaction tab
        self.transaction_tab = TransactionTab()
        self.tabs.addTab(self.transaction_tab, "Transaction")
        # Display tab
        self.display_tab = DisplayTab()
        self.tabs.addTab(self.display_tab, "Display")
        # Results tab
        self.results_tab = ResultsTab()
        self.tabs.addTab(self.results_tab, "Results")
        self.results_tab.policy_double_clicked.connect(
            self._open_polview_with_policy)
        self._polview_window = None
        self._polview_owner = False  # True if we created the window ourselves
        self._polview_provider = None  # callback → shared PolView window
        # Plancode tab
        self.plancode_tab = PlancodeTab()
        self.tabs.addTab(self.plancode_tab, "Plancode")
        # SQL tab
        self.sql_tab = SqlTab()
        self.tabs.addTab(self.sql_tab, "SQL")
        # Build SQL tab (hidden until "Move to Build" is clicked)
        self.build_sql_tab = BuildSqlTab()
        self._build_sql_tab_index = -1
        # Build SQL Results tab (hidden until build query is run)
        self.build_sql_results_tab = BuildSqlResultsTab()
        self._build_sql_results_tab_index = -1
        # Right-click on tab bar → close Build SQL / Build SQL Results
        self.tabs.tabBar().setContextMenuPolicy(
            Qt.ContextMenuPolicy.CustomContextMenu)
        self.tabs.tabBar().customContextMenuRequested.connect(
            self._on_tab_context_menu)
        _left_lay.addWidget(self.tabs, 1)  # stretch=1 so tabs fill
        # ── Cyberlife bottom bar ─────────────────────────────────────
        self.cyberlife_bottom_bar = AuditBottomBar(
            bg_color="#C8D4E4", run_label="Run\nAudit")
        # Convenience aliases for existing code
        self.btn_all = self.cyberlife_bottom_bar.btn_all
        self.txt_max_count = self.cyberlife_bottom_bar.txt_max_count
        self.lbl_result_count = self.cyberlife_bottom_bar.lbl_result_count
        self.lbl_query_time = self.cyberlife_bottom_bar.lbl_query_time
        self.lbl_print_time = self.cyberlife_bottom_bar.lbl_print_time
        self.lbl_total_time = self.cyberlife_bottom_bar.lbl_total_time
        self.btn_run = self.cyberlife_bottom_bar.btn_run
        # Left side: Clear All + Region/SysCode
        _CLEAR_BTN_STYLE = (
            "QPushButton { background-color: #14407A; color: white;"
            " border: 1px solid #0A2A5C; border-radius: 2px;"
            " padding: 1px 8px; font-size: 9pt; }"
            "QPushButton:hover { background-color: #1E5BA8; }"
        )
        self.btn_clear_cyberlife = QPushButton("Clear All")
        self.btn_clear_cyberlife.setFont(_FONT)
        self.btn_clear_cyberlife.setFixedSize(60, 36)
        self.btn_clear_cyberlife.setStyleSheet(_CLEAR_BTN_STYLE)
        self.cyberlife_bottom_bar.left_layout.addWidget(self.btn_clear_cyberlife)
        self.cyberlife_bottom_bar.left_layout.addSpacing(4)
        # Region + System Code stacked
        region_sys_stack = QVBoxLayout()
        region_sys_stack.setSpacing(2)
        region_sys_stack.setContentsMargins(0, 0, 0, 0)
        region_row = QHBoxLayout()
        region_row.setSpacing(3)
        region_row.setContentsMargins(0, 0, 0, 0)
        self.lbl_region = QLabel("Region:")
        self.lbl_region.setFont(QFont("Segoe UI", 8))
        self.cmb_region = QComboBox()
        self.cmb_region.setFont(_FONT)
        self.cmb_region.addItems(REGION_ITEMS)
        self.cmb_region.setFixedHeight(18)
        self.cmb_region.setFixedWidth(70)
        _style_combo(self.cmb_region)
        region_row.addWidget(self.lbl_region)
        region_row.addWidget(self.cmb_region)
        region_row.addStretch()
        region_sys_stack.addLayout(region_row)
        sys_row = QHBoxLayout()
        sys_row.setSpacing(3)
        sys_row.setContentsMargins(0, 0, 0, 0)
        self.lbl_sys = QLabel("Sys Code:")
        self.lbl_sys.setFont(QFont("Segoe UI", 8))
        self.cmb_system = QComboBox()
        self.cmb_system.setFont(_FONT)
        self.cmb_system.addItems(SYSTEM_CODE_ITEMS)
        self.cmb_system.setFixedHeight(18)
        self.cmb_system.setFixedWidth(45)
        _style_combo(self.cmb_system)
        sys_row.addWidget(self.lbl_sys)
        sys_row.addWidget(self.cmb_system)
        sys_row.addStretch()
        region_sys_stack.addLayout(sys_row)
        self.cyberlife_bottom_bar.left_layout.addLayout(region_sys_stack)
        _left_lay.addWidget(self.cyberlife_bottom_bar)
        # ── Dynamic query container (placeholder — queries added dynamically) ──
        self._dynamic_query_container = QVBoxLayout()
        self._dynamic_query_container.setSpacing(0)
        self._dynamic_query_container.setContentsMargins(0, 0, 0, 0)
        _left_lay.addLayout(self._dynamic_query_container)
        # ── Forge blank placeholder (shown when DataForge space has no active forge) ──
        self._forge_blank = QWidget()
        self._forge_blank.setStyleSheet("QWidget { background-color: #E6F5F3; }")
        self._forge_blank.setVisible(False)
        self._dynamic_query_container.addWidget(self._forge_blank)
        # ── Query blank placeholder (shown when Queries space has no active query) ──
        self._query_blank = QWidget()
        self._query_blank.setStyleSheet("QWidget { background-color: #EDE9FE; }")
        self._query_blank.setVisible(False)
        self._dynamic_query_container.addWidget(self._query_blank)
        # DataForge group storage
        self._dataforge_groups: dict[str, DataForgeGroup] = {}
        # ── Left picker panel (embedded) ───────────────────────────
        from suiteview.audit.dataforge.query_field_picker import QueryFieldPicker
        from PyQt6.QtWidgets import QStackedWidget
        self._field_picker = FieldPickerPanel()
        self._field_picker.field_requested.connect(self._on_picker_field_requested)
        self._field_picker.query_clicked.connect(self._on_picker_query_clicked)
        self._field_picker.new_query_requested.connect(self._on_add_group)
        self._field_picker.tables_changed.connect(self._on_picker_tables_changed)
        self._field_picker.splitter_changed.connect(self._schedule_save_ui)
        self._forge_field_picker = QueryFieldPicker()
        self._forge_field_picker.field_requested.connect(
            self._on_forge_picker_field_requested)
        self._forge_field_picker.forge_clicked.connect(
            self._on_picker_forge_clicked)
        self._forge_field_picker.new_forge_requested.connect(
            self._on_new_dataforge)
        self._forge_field_picker.sources_changed.connect(
            self._on_forge_picker_sources_changed)
        self._forge_field_picker.splitter_changed.connect(self._schedule_save_ui)
        self._picker_stack = QStackedWidget()
        self._picker_stack.addWidget(self._field_picker)
        self._picker_stack.addWidget(self._forge_field_picker)
        # Picker container — always visible in query/forge modes
        self._picker_container = QWidget()
        _pc_lay = QVBoxLayout(self._picker_container)
        _pc_lay.setContentsMargins(0, 0, 0, 0)
        _pc_lay.setSpacing(0)
        _pc_lay.addWidget(self._picker_stack, 1)
        self._picker_container.setVisible(False)
        self._picker_width = 380
        self._content_splitter = QSplitter(Qt.Orientation.Horizontal)
        self._content_splitter.setChildrenCollapsible(False)
        self._content_splitter.setHandleWidth(6)
        self._content_splitter.setStyleSheet(
            "QSplitter::handle { background: #B2DFDB; }"
            "QSplitter::handle:hover { background: #0D9488; }")
        self._content_splitter.addWidget(self._picker_container)
        self._content_splitter.addWidget(self._content_left)
        self._content_splitter.setStretchFactor(0, 0)
        self._content_splitter.setStretchFactor(1, 1)
        self._content_splitter.setSizes([0, 900])
        self._content_splitter.splitterMoved.connect(self._on_content_splitter_moved)
        root.addWidget(self._content_splitter, 1)
        self._apply_initial_state()
        self._connect_signals()
        self._restore_ui_settings()
        return body
    # ── Initial state ────────────────────────────────────────────────
    def _apply_initial_state(self):
        idx = self.cmb_region.findText(self._region)
        if idx >= 0:
            self.cmb_region.setCurrentIndex(idx)
        # Default system code = "I"  (inforce)
        idx_sys = self.cmb_system.findText("I")
        if idx_sys >= 0:
            self.cmb_system.setCurrentIndex(idx_sys)
    def _connect_signals(self):
        self.btn_run.clicked.connect(self._run_audit)
        self.sql_tab.move_to_build.connect(self._on_move_to_build)
        self.build_sql_tab.run_sql_requested.connect(self._run_build_sql)
        self.btn_clear_cyberlife.clicked.connect(self._on_clear_cyberlife)
    # ── Mode switching (Cyberlife / dynamic) ─────────────────────────
    # Cyberlife tab pane — darker blue top/bottom border
    _CYB_TAB_STYLE = (
        "QTabWidget::pane { border-top: 3px solid #14407A;"
        " border-bottom: 3px solid #14407A;"
        " border-left: 1px solid #999; border-right: 1px solid #999; }"
        "QTabBar::tab { padding: 2px 8px; min-height: 20px; font-size: 9pt; }"
        "QTabBar::tab:selected { font-weight: bold; }"
    )
    def _switch_mode(self, mode: str):
        """Switch between Cyberlife, dynamic query, and DataForge views."""
        if mode == self._current_mode:
            return
        prev = self._current_mode
        self._current_mode = mode
        # Track last active query/forge for restoring on space switch
        if mode in self._dynamic_queries:
            self._last_query_mode = mode
        elif mode in self._dataforge_groups:
            self._last_forge_mode = mode
        prev_had_picker = (prev in self._dynamic_queries
                           or prev in self._dataforge_groups
                           or prev == "__forge_blank__"
                           or prev == "__query_blank__")
        # Batch all visibility/style changes to avoid intermediate repaints
        self.setUpdatesEnabled(False)
        try:
            is_cyberlife = (mode == "cyberlife")
            is_forge_blank = (mode == "__forge_blank__")
            is_query_blank = (mode == "__query_blank__")
            self.tabs.setVisible(is_cyberlife)
            self.cyberlife_bottom_bar.setVisible(is_cyberlife)
            self._forge_blank.setVisible(is_forge_blank)
            self._query_blank.setVisible(is_query_blank)
            # Only toggle the two affected widgets (prev + new)
            for name, q in self._dynamic_queries.items():
                if name == mode:
                    q.setVisible(True)
                elif name == prev:
                    q.setVisible(False)
            for name, fg in self._dataforge_groups.items():
                if name == mode:
                    fg.setVisible(True)
                elif name == prev:
                    fg.setVisible(False)
        finally:
            self.setUpdatesEnabled(True)
        # Dispatch to per-mode-type setup
        if mode in self._dataforge_groups or mode == "__forge_blank__":
            self._enter_forge_mode(mode, prev_had_picker)
        elif mode in self._dynamic_queries or mode == "__query_blank__":
            self._enter_query_mode(mode, prev_had_picker)
        else:
            self._enter_cyberlife_mode()
    def _enter_cyberlife_mode(self):
        """Configure UI for Cyberlife mode."""
        self.btn_cyberlife.blockSignals(True)
        self.btn_cyberlife.setChecked(True)
        self.btn_cyberlife.blockSignals(False)
        self.tabs.setStyleSheet(self._CYB_TAB_STYLE)
        self._save_picker_width()
        self._hide_picker_panel()
    def _enter_query_mode(self, mode: str, prev_had_picker: bool):
        """Configure UI for a dynamic query or the query-blank placeholder."""
        self.btn_cyberlife.blockSignals(True)
        self.btn_cyberlife.setChecked(False)
        self.btn_cyberlife.blockSignals(False)
        self._save_picker_width()
        self._refresh_picker_query_list()
        self._content_splitter.setStyleSheet(
            "QSplitter::handle { background: #DDD6FE; }"
            "QSplitter::handle:hover { background: #7C3AED; }")
        if mode in self._dynamic_queries:
            dq = self._dynamic_queries[mode]
            self._field_picker.set_group(
                dq.dsn, dq.tables, dq.display_names)
            raw_name = mode.removeprefix("▸ ")
            self._field_picker.highlight_query(raw_name)
        else:
            self._field_picker.clear()
        self._picker_stack.setCurrentWidget(self._field_picker)
        if not prev_had_picker:
            self._show_picker_panel()
    def _enter_forge_mode(self, mode: str, prev_had_picker: bool):
        """Configure UI for a DataForge or the forge-blank placeholder."""
        self.btn_cyberlife.blockSignals(True)
        self.btn_cyberlife.setChecked(False)
        self.btn_cyberlife.blockSignals(False)
        self._save_picker_width()
        self._refresh_picker_forge_list()
        fg = self._dataforge_groups.get(mode)
        if fg:
            self._forge_field_picker.set_sources(
                list(fg._sources.keys()))
            raw_name = mode.removeprefix("⚙ ")
            self._forge_field_picker.highlight_forge(raw_name)
        self._content_splitter.setStyleSheet(
            "QSplitter::handle { background: #B2DFDB; }"
            "QSplitter::handle:hover { background: #0D9488; }")
        self._picker_stack.setCurrentWidget(self._forge_field_picker)
        if not prev_had_picker:
            self._show_picker_panel()
    def _save_picker_width(self):
        """Capture current picker width before switching modes."""
        if self._picker_container.isVisible():
            self._picker_width = self._content_splitter.sizes()[0]
    # ── Field Picker panel ───────────────────────────────────────────
    def _update_field_picker(self):
        """Populate the field picker from the active dynamic query."""
        group = self._dynamic_queries.get(self._current_mode)
        if group is not None:
            self._field_picker.set_group(
                group.dsn, group.tables, group.display_names)
        else:
            self._field_picker.clear()
    def _on_picker_field_requested(self, table: str, column: str,
                                   type_name: str, display: str):
        """Double-click in field picker — delegate to the active dynamic query."""
        group = self._dynamic_queries.get(self._current_mode)
        if group is not None:
            group._on_field_requested(table, column, type_name, display)
    def _on_picker_query_clicked(self, query_name: str):
        """User clicked a query name in the picker's query list."""
        from suiteview.audit import saved_query_store as sq_store
        sq = sq_store.load_query(query_name)
        if sq is None:
            return
        self._on_load_saved_query(sq)
        # Always update picker tables/fields for the active query
        name = f"\u25b8 {sq.name}"
        group = self._dynamic_queries.get(name)
        if group is not None:
            self._field_picker.set_group(
                group.dsn, group.tables, group.display_names)
            self._field_picker.highlight_query(sq.name)
    def _on_picker_tables_changed(self, tables: list[str]):
        """Tables list was changed in the picker — sync back to the query."""
        group = self._dynamic_queries.get(self._current_mode)
        if group is not None:
            group.tables = list(tables)
    def _refresh_picker_query_list(self):
        """Refresh the query list in the field picker from saved queries."""
        from suiteview.audit import saved_query_store as sq_store
        queries = sq_store.list_queries()
        names = [sq.name for sq in queries]
        self._field_picker.set_queries(names)
    def _on_forge_picker_field_requested(self, query_name: str, col_name: str):
        """Double-click in forge field picker — delegate to active DataForge group."""
        group = self._dataforge_groups.get(self._current_mode)
        if group is not None:
            group.on_field_requested(query_name, col_name)
    def _on_picker_forge_clicked(self, forge_name: str):
        """User clicked a forge name in the picker's forge list."""
        from suiteview.audit.dataforge import dataforge_store as df_store
        forge = df_store.load_forge(forge_name)
        if forge is None:
            return
        self._on_load_dataforge(forge)
        # Always update picker queries/fields for the active forge
        display = f"⚙ {forge.name}"
        group = self._dataforge_groups.get(display)
        if group is not None:
            self._forge_field_picker.set_sources(
                list(group._sources.keys()))
            self._forge_field_picker.highlight_forge(forge.name)
    def _refresh_picker_forge_list(self):
        """Refresh the forge list in the forge field picker from saved forges."""
        from suiteview.audit.dataforge import dataforge_store as df_store
        forges = df_store.list_forges()
        names = [f.name for f in forges]
        self._forge_field_picker.set_forges(names)
    def _on_forge_picker_sources_changed(self, source_names: list[str]):
        """Queries list was changed in the forge picker — sync back to the group."""
        group = self._dataforge_groups.get(self._current_mode)
        if group is not None:
            from suiteview.audit import saved_query_store as sq_store
            for name in source_names:
                if name not in group._sources:
                    sq = sq_store.load_query(name)
                    if sq:
                        group.add_source_query(sq)
    # ── Dynamic query management ─────────────────────────────────────
    def _on_add_group(self):
        """Open the Create Query dialog and add a new dynamic query."""
        from .dialogs.create_group_dialog import CreateQueryDialog
        dlg = CreateQueryDialog(self)
        if dlg.exec() != dlg.DialogCode.Accepted:
            return
        name, dsn, tables = dlg.get_result()
        # Auto-save the new query so it appears in the Queries shelf
        from suiteview.audit.saved_query import SavedQuery
        from suiteview.audit import saved_query_store as sq_store
        sq = SavedQuery(
            name=name,
            source_group=name,
            dsn=dsn,
            tables=list(tables),
            display_names={},
            config={},
            sql="",
        )
        sq_store.save_query(sq)
        # Create the group as a "temp" (loaded saved query) so it gets Save + Save As
        self._create_dynamic_query(
            name, dsn, tables, saved_query_name=name)
        # Refresh query lists and switch
        self._refresh_picker_query_list()
        self._switch_mode(name)
    def _create_dynamic_query(self, name: str, dsn: str, tables: list[str],
                              display_names: dict[str, str] | None = None,
                              saved_query_name: str = ""):
        """Create a DynamicQuery widget and wire it into the UI."""
        group = DynamicQuery(name, dsn, tables, display_names, parent=self,
                             saved_query_name=saved_query_name)
        group.setVisible(False)
        self._dynamic_queries[name] = group
        self._dynamic_query_container.addWidget(group)
        group.query_saved.connect(lambda _: self._refresh_picker_query_list())
        group.query_deleted.connect(self._on_query_deleted_from_group)
    def _close_group(self, name: str):
        """Close a query group — removes from UI."""
        self._remove_query(name)
    def _on_query_deleted_from_group(self, query_name: str):
        """A query was deleted from disk — close the group."""
        name_to_close = None
        for name, group in self._dynamic_queries.items():
            if group._saved_query_name == query_name:
                name_to_close = name
                break
        if name_to_close:
            self._remove_query(name_to_close)
    def _restore_ui_settings(self):
        """Restore window-level UI settings (field picker sizes, etc.)."""
        ui = load_ui_settings()
        picker_state = ui.get("field_picker")
        if picker_state:
            self._field_picker.set_state(picker_state)
        forge_picker_state = ui.get("forge_field_picker")
        if forge_picker_state and hasattr(self._forge_field_picker, 'set_state'):
            self._forge_field_picker.set_state(forge_picker_state)
        pw = ui.get("picker_width")
        if pw and isinstance(pw, (int, float)) and pw > 0:
            self._picker_width = int(pw)
    def closeEvent(self, event):
        """Save UI settings on window close."""
        ui = load_ui_settings()
        ui["field_picker"] = self._field_picker.get_state()
        if hasattr(self._forge_field_picker, 'get_state'):
            ui["forge_field_picker"] = self._forge_field_picker.get_state()
        ui["field_picker_visible"] = self._picker_container.isVisible()
        # Save the current picker width (from splitter or last-known)
        if self._picker_container.isVisible():
            ui["picker_width"] = self._content_splitter.sizes()[0]
        else:
            ui["picker_width"] = self._picker_width
        save_ui_settings(ui)
        super().closeEvent(event)
    # ── Picker slide-out helpers ─────────────────────────────────────
    def _show_picker_panel(self):
        """Show the picker panel inward, taking space from the content area."""
        if self._picker_container.isVisible():
            return
        pw = self._picker_width
        self.setUpdatesEnabled(False)
        try:
            self._picker_container.setVisible(True)
            sizes = self._content_splitter.sizes()
            # Give picker pw pixels, shrink content by that amount
            sizes[0] = pw
            sizes[1] = max(400, sizes[1] - pw)
            self._content_splitter.setSizes(sizes)
        finally:
            self.setUpdatesEnabled(True)
            self.repaint()
        self._schedule_save_ui()
    def _hide_picker_panel(self):
        """Collapse the picker panel, returning space to the content area."""
        if not self._picker_container.isVisible():
            return
        self.setUpdatesEnabled(False)
        try:
            # Remember the current picker width for next show
            self._picker_width = self._content_splitter.sizes()[0]
            pw = self._picker_width
            self._picker_container.setVisible(False)
            sizes = self._content_splitter.sizes()
            sizes[1] = sizes[1] + pw
            sizes[0] = 0
            self._content_splitter.setSizes(sizes)
        finally:
            self.setUpdatesEnabled(True)
            self.repaint()
        self._schedule_save_ui()
    def _on_content_splitter_moved(self, pos, index):
        """Track picker panel width when user drags the splitter handle."""
        if self._picker_container.isVisible():
            w = self._content_splitter.sizes()[0]
            if w > 0:
                self._picker_width = w
        self._schedule_save_ui()
    def _schedule_save_ui(self):
        """Debounced save of UI settings — writes to disk after 500ms idle."""
        if not hasattr(self, '_save_ui_timer'):
            self._save_ui_timer = QTimer(self)
            self._save_ui_timer.setSingleShot(True)
            self._save_ui_timer.setInterval(500)
            self._save_ui_timer.timeout.connect(self._do_save_ui_settings)
        self._save_ui_timer.start()
    def _do_save_ui_settings(self):
        """Actually write UI settings to disk."""
        ui = load_ui_settings()
        ui["field_picker"] = self._field_picker.get_state()
        if hasattr(self._forge_field_picker, 'get_state'):
            ui["forge_field_picker"] = self._forge_field_picker.get_state()
        ui["field_picker_visible"] = self._picker_container.isVisible()
        if self._picker_container.isVisible():
            ui["picker_width"] = self._content_splitter.sizes()[0]
        else:
            ui["picker_width"] = self._picker_width
        save_ui_settings(ui)
    # ── Unique Value Registry ────────────────────────────────────────
    def _open_registry(self):
        """Open the Unique Value Registry viewer window."""
        try:
            from .unique_value_registry_window import UniqueValueRegistryWindow
            UniqueValueRegistryWindow.show_instance(parent=None)
        except Exception as exc:
            logger.exception("Failed to open registry window")
            QMessageBox.warning(self, "Registry Error", str(exc))
    # ── Query building ───────────────────────────────────────────────
    def _build_sql(self) -> str:
        """Build the CyberLife audit SQL — delegates to cyberlife_query module."""
        region = self.cmb_region.currentText()
        schema = REGION_SCHEMA_MAP.get(region, DEFAULT_SCHEMA)
        return build_cyberlife_sql(
            schema=schema,
            sys_code=self.cmb_system.currentText().strip(),
            max_count_text=self.txt_max_count.text().strip(),
            policy_tab=self.policy_tab,
            display_tab=self.display_tab,
            policy2_tab=self.policy2_tab,
            adv_tab=self.adv_tab,
            coverages_tab=self.coverages_tab,
            plancode_tab=self.plancode_tab,
            benefits_tab=self.benefits_tab,
            transaction_tab=self.transaction_tab,
        )
    # ── Profile management ───────────────────────────────────────────
    def _cyberlife_criteria_tabs(self):
        """Return (key, tab) pairs for Cyberlife tabs that support get_state/set_state."""
        return [
            ("policy", self.policy_tab),
            ("policy2", self.policy2_tab),
            ("coverages", self.coverages_tab),
            ("adv", self.adv_tab),
            ("wl", self.wl_tab),
            ("di", self.di_tab),
            ("benefits", self.benefits_tab),
            ("transaction", self.transaction_tab),
            ("display", self.display_tab),
            ("plancode", self.plancode_tab),
        ]
    def _on_clear_cyberlife(self):
        """Reset only Cyberlife tabs to defaults."""
        for _key, tab in self._cyberlife_criteria_tabs():
            tab.set_state({})
        self.txt_max_count.setText("25")
    # ── Run audit ────────────────────────────────────────────────────
    def _run_audit(self):
        """Execute the audit query and display results."""
        try:
            sql = self._build_sql()
        except Exception as exc:
            logger.exception("Failed to build audit SQL")
            QMessageBox.warning(self, "SQL Build Error", str(exc))
            return
        # Show SQL immediately
        self.sql_tab.set_sql(sql)
        region = self.cmb_region.currentText()
        with run_button_context(self.btn_run, bar=self.cyberlife_bottom_bar):
            t0 = time.time()
            try:
                db = DB2Connection(region)
                columns, rows = db.execute_query_with_headers(sql)
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
                # Switch to Results tab
                self.tabs.setCurrentWidget(self.results_tab)
            except Exception as exc:
                logger.exception("Audit query failed")
                msg = str(exc)
                if hasattr(exc, 'args') and len(exc.args) >= 2:
                    msg = f"{exc.args[0]}\n\n{exc.args[1]}"
                QMessageBox.warning(self, "Query Error", msg)
    # ── Header view buttons ──────────────────────────────────────────
    def _on_cyberlife_header_clicked(self, checked: bool):
        """Switch to Cyberlife view from header button."""
        if checked:
            self.btn_workbench.setChecked(False)
            self.btn_dataforge.setChecked(False)
            self._switch_mode("cyberlife")
        else:
            # Don't allow unchecking when already in cyberlife
            self.btn_cyberlife.blockSignals(True)
            self.btn_cyberlife.setChecked(True)
            self.btn_cyberlife.blockSignals(False)
    # ── Query/DataForge space switching ────────────────────────────
    def _toggle_saved_queries_shelf(self, checked: bool):
        """Switch to/from Queries mode."""
        if checked:
            self.btn_dataforge.setChecked(False)
            self.btn_cyberlife.blockSignals(True)
            self.btn_cyberlife.setChecked(False)
            self.btn_cyberlife.blockSignals(False)
            # Restore last active query, or show blank
            if self._current_mode not in self._dynamic_queries:
                restore = self._last_query_mode
                if restore and restore in self._dynamic_queries:
                    self._switch_mode(restore)
                else:
                    self._switch_mode("__query_blank__")
            self._refresh_picker_query_list()
        else:
            pass  # Clicking again does nothing — use Cyberlife to leave
    def _toggle_dataforge_shelf(self, checked: bool):
        """Switch to/from DataForge mode."""
        if checked:
            self.btn_workbench.setChecked(False)
            self.btn_cyberlife.blockSignals(True)
            self.btn_cyberlife.setChecked(False)
            self.btn_cyberlife.blockSignals(False)
            # Restore last active forge, or show blank
            if self._current_mode not in self._dataforge_groups:
                restore = self._last_forge_mode
                if restore and restore in self._dataforge_groups:
                    self._switch_mode(restore)
                else:
                    self._switch_mode("__forge_blank__")
            self._refresh_picker_forge_list()
        else:
            pass  # Clicking again does nothing — use Cyberlife to leave
    # ── Query removal ────────────────────────────────────────────
    def _remove_query(self, name: str):
        """Remove a DynamicQuery widget and clean up tracking."""
        if self._current_mode == name:
            self._switch_mode("cyberlife")
        group = self._dynamic_queries.pop(name, None)
        if group:
            self._dynamic_query_container.removeWidget(group)
            group.deleteLater()
        if self._active_unpinned == name:
            self._active_unpinned = None
        if self._last_query_mode == name:
            self._last_query_mode = None
        if self._last_forge_mode == name:
            self._last_forge_mode = None
    def _on_load_saved_query(self, sq):
        """Create a DynamicQuery from a saved query and switch to it."""
        from suiteview.audit.saved_query import SavedQuery
        config: dict = sq.config
        name = f"▸ {sq.name}"
        # If already loaded, switch first then clean up old
        if name in self._dynamic_queries:
            self._switch_mode(name)
            # Now safely remove previous unpinned (no flash — we already switched)
            prev = self._active_unpinned
            if prev and prev != name:
                self._remove_query(prev)
            self._active_unpinned = name
            return
        tables = config.get("tables", sq.tables)
        dsn = config.get("dsn", sq.dsn)
        display_names = config.get("display_names", sq.display_names)
        # Create the group widget
        group = DynamicQuery(
            name, dsn, tables, display_names,
            parent=self, saved_query_name=sq.name)
        group.setVisible(False)
        self._dynamic_queries[name] = group
        self._dynamic_query_container.addWidget(group)
        group.query_saved.connect(lambda _: self._refresh_picker_query_list())
        group.query_deleted.connect(self._on_query_deleted_from_group)
        # Restore saved config into the group (marks clean after load)
        group.set_config(config)
        # Switch to new query first, then remove old (avoids flash to Cyberlife)
        prev = self._active_unpinned
        self._active_unpinned = name
        self._switch_mode(name)
        # Now safely remove previous unpinned (current_mode != prev, no flash)
        if prev:
            self._remove_query(prev)
    # ── DataForge ─────────────────────────────────────────────────
    def _on_new_dataforge(self):
        """Create a brand-new empty DataForge designer."""
        from suiteview.audit.dataforge.dataforge_model import DataForge
        from suiteview.audit.dataforge import dataforge_store as df_store
        name, ok = QInputDialog.getText(
            self, "New DataForge", "DataForge name:")
        if not ok or not name.strip():
            return
        name = name.strip()
        # Block duplicate names
        if df_store.forge_exists(name):
            QMessageBox.warning(
                self, "Name Taken",
                f"A DataForge named \"{name}\" already exists.\n"
                "Please choose a different name.")
            return
        display = f"⚙ {name}"
        # Save an empty forge to disk immediately so it appears in the shelf
        forge = DataForge(name=name, sources=[], config={})
        df_store.save_forge(forge)
        self._create_dataforge_group(
            display, forge_name=name, saved_forge_name=name)
        # Refresh the forge list in the picker
        self._refresh_picker_forge_list()
    def _on_load_dataforge(self, forge):
        """Open a DataForge designer from the shelf click."""
        from suiteview.audit.dataforge.dataforge_model import DataForge
        from suiteview.audit import saved_query_store as sq_store
        display = f"⚙ {forge.name}"
        # If already loaded, switch to it
        if display in self._dataforge_groups:
            self._switch_mode(display)
            return
        group = self._create_dataforge_group(
            display, forge_name=forge.name, saved_forge_name=forge.name)
        # Restore sources
        for src in forge.sources:
            sq = sq_store.load_query(src.query_name)
            if sq:
                group.add_source_query(sq)
        # Restore config
        if forge.config:
            group.set_config(forge.config)
    def _on_close_dataforge_from_shelf(self, forge_name: str):
        """Close an open DataForge designer."""
        display = f"⚙ {forge_name}"
        self._remove_dataforge_group(display)
    def _create_dataforge_group(self, display: str, forge_name: str = "",
                                saved_forge_name: str = "") -> DataForgeGroup:
        """Create a DataForgeGroup widget and switch to it."""
        group = DataForgeGroup(
            name=display, parent=self,
            saved_forge_name=saved_forge_name)
        group.setVisible(False)
        self._dataforge_groups[display] = group
        self._dynamic_query_container.addWidget(group)
        group.forge_saved.connect(self._on_forge_saved_refresh)
        group.forge_deleted.connect(self._on_forge_deleted_from_group)
        self._switch_mode(display)
        return group
    def _remove_dataforge_group(self, name: str):
        """Remove a DataForge widget and clean up."""
        if self._current_mode == name:
            self._switch_mode("cyberlife")
        group = self._dataforge_groups.pop(name, None)
        if group:
            self._dynamic_query_container.removeWidget(group)
            group.deleteLater()
    def _on_forge_saved_refresh(self):
        """A forge was saved — refresh the picker forge list."""
        self._refresh_picker_forge_list()
    def _on_forge_deleted_from_group(self, forge_name: str):
        """Handle a DataForge being deleted from within its group."""
        display = f"⚙ {forge_name}"
        self._remove_dataforge_group(display)
        self._refresh_picker_forge_list()
    # ── Build SQL feature ───────────────────────────────────────
    def _on_move_to_build(self, sql: str):
        """Copy SQL to the Build SQL tab and switch to it."""
        # Add tab if not already present
        if self._build_sql_tab_index < 0:
            self._build_sql_tab_index = self.tabs.addTab(
                self.build_sql_tab, "Build SQL")
        self.build_sql_tab.set_sql(sql)
        self.tabs.setCurrentWidget(self.build_sql_tab)
    def _run_build_sql(self, sql: str):
        """Execute user-edited SQL and show results in Build SQL Results."""
        region = self.cmb_region.currentText()
        with run_button_context(
            self.build_sql_tab.btn_run_sql,
            restore_text="Run this SQL",
        ):
            try:
                db = DB2Connection(region)
                columns, rows = db.execute_query_with_headers(sql)
                df = pd.DataFrame([list(r) for r in rows], columns=columns)
                # Add results tab if not already present
                if self._build_sql_results_tab_index < 0:
                    self._build_sql_results_tab_index = self.tabs.addTab(
                        self.build_sql_results_tab, "Build SQL Results")
                self.build_sql_results_tab.set_results(df)
                self.tabs.setCurrentWidget(self.build_sql_results_tab)
            except Exception as exc:
                logger.exception("Build SQL query failed")
                msg = str(exc)
                if hasattr(exc, 'args') and len(exc.args) >= 2:
                    msg = f"{exc.args[0]}\n\n{exc.args[1]}"
                QMessageBox.warning(self, "Query Error", msg)
    # ── PolView integration ─────────────────────────────────────
    def _on_tab_context_menu(self, pos):
        """Show a context menu to close Build SQL / Build SQL Results tabs."""
        tab_index = self.tabs.tabBar().tabAt(pos)
        if tab_index < 0:
            return
        widget = self.tabs.widget(tab_index)
        # Only allow closing Build SQL tabs
        if widget not in (self.build_sql_tab, self.build_sql_results_tab):
            return
        menu = QMenu(self)
        action = menu.addAction("Close tab")
        chosen = menu.exec(self.tabs.tabBar().mapToGlobal(pos))
        if chosen == action:
            self.tabs.removeTab(tab_index)
            if widget is self.build_sql_tab:
                self._build_sql_tab_index = -1
            elif widget is self.build_sql_results_tab:
                self._build_sql_results_tab_index = -1
    def set_polview_window(self, polview_window):
        """Set a shared PolView window (from the parent app)."""
        self._polview_window = polview_window
        self._polview_owner = False
    def set_polview_provider(self, provider):
        """Set a callback that returns the shared PolView window."""
        self._polview_provider = provider
    def _open_polview_with_policy(self, policy_number: str,
                                  company_code: str):
        """Open PolView and load the given policy."""
        region = self.cmb_region.currentText()
        # Ask the provider for the canonical PolView instance
        if self._polview_provider is not None:
            pw = self._polview_provider()
            if pw is not None:
                self._polview_window = pw
                self._polview_owner = False
        # Fallback: create our own if no shared instance available
        if self._polview_window is None:
            from suiteview.polview.ui.main_window import GetPolicyWindow
            self._polview_window = GetPolicyWindow()
            self._polview_owner = True
        pw = self._polview_window
        pw.show()
        pw.raise_()
        pw.activateWindow()
        # Keep policy list panel at same Z-level as PolView
        if hasattr(pw, 'policy_list_window') and pw.policy_list_window.isVisible():
            pw.policy_list_window.raise_()
        if hasattr(pw, 'lookup_bar'):
            lb = pw.lookup_bar
            lb.region_input.setText(region)
            lb.company_input.setText(company_code)
            lb.policy_input.setText(policy_number)
            lb._on_get_policy()