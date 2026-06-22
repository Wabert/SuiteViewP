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
import pyodbc
from PyQt6.QtCore import Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QFont
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QTabWidget,
    QLabel, QComboBox, QPushButton, QCheckBox,
    QMessageBox, QDialog, QInputDialog,
    QSplitter, QFileDialog, QMenu, QToolButton,
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
from .tabs.custom_display_tab import CustomDisplayTab
from .tabs.results_tab import ResultsTab
from .tabs.sql_tab import SqlTab
from .tabs.plancode_tab import PlancodeTab
from .tabs.common_tables_tab import CommonTablesTab
from .tabs.build_sql_tab import BuildSqlTab
from .tabs.build_sql_results_tab import BuildSqlResultsTab
from .tabs.manual_sql_object_editor import ManualSqlObjectEditor
from .tabs.csv_excel_object_editor import CsvExcelObjectEditor
from .tabs.file_source_editor import FileSourceEditor
from .tabs._styles import style_combo as _style_combo
from suiteview.core.db2_connection import DB2Connection
from suiteview.core.db2_constants import DEFAULT_SCHEMA, REGION_SCHEMA_MAP
from .cyberlife_query import build_cyberlife_sql
from .dynamic_query import build_common_table_cte
from .sql_helpers import fmt_time
from .dynamic_group import DynamicQuery
from .field_picker_panel import FieldPickerPanel, _indexed_column_names
from .group_config import load_ui_settings, save_ui_settings
from .ui.bottom_bar import AuditBottomBar, FOOTER_BG
from .query_runner import (
    execute_odbc_query,
    run_button_context,
    run_query_async,
    format_query_error,
)
from suiteview.audit.dataforge.dataforge_group import DataForgeGroup
from .dialogs.tables_dialog import _clean_odbc_identifier
logger = logging.getLogger(__name__)
_FONT = QFont("Segoe UI", 9)
# Theme — default SuiteView blue header, gold border
_HEADER_COLORS = ("#1E5BA8", "#0D3A7A", "#082B5C")
_BORDER_COLOR = "#D4A017"
_BUILD_MODE_BUTTON_WIDTH = 132


class QueryObjectModeDialog(QDialog):
    """Dense chooser for the four Query Object creation modes."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.selected_mode = ""
        self.setWindowTitle("New Query Object")
        self.setModal(True)
        self.resize(640, 260)
        self._build_ui()

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(8, 8, 8, 8)
        root.setSpacing(8)
        self.setStyleSheet(
            "QDialog { background-color: #F0F0F0; }"
            "QLabel#title { color: #1E5BA8; font-size: 14pt; font-weight: bold; }"
            "QPushButton { text-align: left; background: white; border: 1px solid #A0C4E8;"
            " border-left: 5px solid #1E5BA8; padding: 8px 10px; color: #111; }"
            "QPushButton:hover { background: #E8F0FB; border-color: #1E5BA8; }"
        )

        title = QLabel("New Query Object")
        title.setObjectName("title")
        root.addWidget(title)

        modes = [
            (
                "cyberlife",
                "Cyberlife Object",
                "Policy extract builder with Cyberlife criteria and generated DB2 SQL",
            ),
            (
                "visual",
                "Visual Query Object",
                "Table-driven builder for sources, inputs, outputs, joins, and preview",
            ),
            (
                "manual_sql",
                "Manual SQL Object",
                "Paste or edit SQL, run it, capture output schema, then save object",
            ),
        ]
        for mode, heading, detail in modes:
            button = QPushButton(f"{heading}\n{detail}")
            button.setFont(QFont("Segoe UI", 9))
            button.setFixedHeight(46)
            button.clicked.connect(lambda checked=False, value=mode: self._choose(value))
            root.addWidget(button)

    def _choose(self, mode: str):
        self.selected_mode = mode
        self.accept()


class AuditWindow(FramelessWindowBase):
    """Top-level audit window, replicating VBA frmAudit layout."""
    query_object_saved = pyqtSignal(str)

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
        self._selected_build_mode = "cyberlife"
        self._cyberlife_saved_object_name = ""
        self._manual_sql_started = False
        # Object/build controls — placed in the window header bar
        # Gold trim style for all header buttons
        _GOLD = "#D4A017"
        _GOLD_BTN_BASE = (
            " color: {gold}; border: 1px solid {gold}; border-radius: 3px;"
            " padding: 2px 10px; font-size: 8pt;"
        ).format(gold=_GOLD)
        _HEADER_BTN_STYLE = (
            "QPushButton { background-color: rgba(255,255,255,0.10);"
            + _GOLD_BTN_BASE + " }"
            "QPushButton:hover { background-color: rgba(255,255,255,0.25); }"
        )
        self.btn_objects = QPushButton("Objects")
        self.btn_objects.setFont(QFont("Segoe UI", 8))
        self.btn_objects.setFixedHeight(24)
        self.btn_objects.setStyleSheet(_HEADER_BTN_STYLE)
        self.btn_objects.setToolTip("Open the unified Query Object browser")
        self.btn_objects.clicked.connect(self._open_query_object_viewer)
        self.lbl_build_mode = QLabel("Build Mode")
        self.lbl_build_mode.setFont(QFont("Segoe UI", 8, QFont.Weight.Bold))
        self.lbl_build_mode.setStyleSheet("color: #D4A017; padding: 0 4px;")
        self.btn_build_mode = QToolButton()
        self.btn_build_mode.setFont(QFont("Segoe UI", 8))
        self.btn_build_mode.setFixedSize(_BUILD_MODE_BUTTON_WIDTH, 24)
        self.btn_build_mode.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        self.btn_build_mode.setPopupMode(QToolButton.ToolButtonPopupMode.MenuButtonPopup)
        self.btn_build_mode.setToolTip("Choose the Query Object build mode")
        self.btn_build_mode.clicked.connect(self._on_build_mode_button_clicked)
        # Each mode carries its identity color (build_mode_styles) — the
        # same chip/color the browser shows on queries built by that mode.
        from suiteview.audit.build_mode_styles import build_mode_style, mode_icon
        mode_menu = QMenu(self.btn_build_mode)
        for mode, label in (
            ("cyberlife", "Cyberlife"),
            ("visual", "Visual Query"),
            ("manual_sql", "Manual SQL"),
        ):
            action = mode_menu.addAction(label)
            action.setIcon(mode_icon(build_mode_style(mode).color))
            action.triggered.connect(lambda checked=False, value=mode: self._on_build_mode_selected(value))
        self.btn_build_mode.setMenu(mode_menu)
        self._style_build_mode_button("cyberlife")
        # Cyberlife header button (view toggle)
        _CYB_HDR_BTN_STYLE = (
            "QPushButton { background-color: rgba(10,42,92,0.8);"
            + _GOLD_BTN_BASE + " }"
            "QPushButton:hover { background-color: rgba(30,91,168,0.8); }"
            "QPushButton:checked { background-color: #0A2A5C;"
            " border: 2px solid " + _GOLD + "; color: " + _GOLD + "; }"
        )
        self.btn_cyberlife = QPushButton("Cyberlife")
        self.btn_cyberlife.setFont(QFont("Segoe UI", 8))
        self.btn_cyberlife.setFixedHeight(24)
        self.btn_cyberlife.setCheckable(True)
        self.btn_cyberlife.setChecked(True)
        self.btn_cyberlife.setStyleSheet(_CYB_HDR_BTN_STYLE)
        self.btn_cyberlife.setToolTip("Switch to the Cyberlife audit view")
        self.btn_cyberlife.clicked.connect(self._on_cyberlife_header_clicked)
        self.btn_cyberlife.setVisible(False)
        _WB_BTN_STYLE = (
            "QPushButton { background-color: rgba(124,58,237,0.7);"
            + _GOLD_BTN_BASE + " }"
            "QPushButton:hover { background-color: rgba(139,92,246,0.8); }"
            "QPushButton:checked { background-color: #7C3AED;"
            " border: 2px solid " + _GOLD + "; color: " + _GOLD + "; }"
        )
        self.btn_workbench = QPushButton("Query Studio")
        self.btn_workbench.setFont(QFont("Segoe UI", 8))
        self.btn_workbench.setFixedHeight(24)
        self.btn_workbench.setCheckable(True)
        self.btn_workbench.setStyleSheet(_WB_BTN_STYLE)
        self.btn_workbench.setToolTip("Switch to the visual Query Object builder")
        self.btn_workbench.clicked.connect(self._toggle_saved_queries_shelf)
        self.btn_workbench.setVisible(False)
        _DF_BTN_STYLE = (
            "QPushButton { background-color: rgba(194,65,12,0.78);"
            + _GOLD_BTN_BASE + " }"
            "QPushButton:hover { background-color: rgba(234,88,12,0.86); }"
            "QPushButton:checked { background-color: #C2410C;"
            " border: 2px solid " + _GOLD + "; color: " + _GOLD + "; }"
        )
        self.btn_dataforge = QPushButton("DataForge")
        self.btn_dataforge.setFont(QFont("Segoe UI", 8))
        self.btn_dataforge.setFixedHeight(24)
        self.btn_dataforge.setCheckable(True)
        self.btn_dataforge.setStyleSheet(_DF_BTN_STYLE)
        self.btn_dataforge.setToolTip("Switch to the DataForge view")
        self.btn_dataforge.clicked.connect(self._toggle_dataforge_shelf)
        # Advanced executable-definition viewer button
        _QDEF_BTN_STYLE = (
            "QPushButton { background-color: rgba(124,58,237,0.4);"
            + _GOLD_BTN_BASE + " }"
            "QPushButton:hover { background-color: rgba(124,58,237,0.6); }"
        )
        self.btn_qdef = QPushButton("Advanced")
        self.btn_qdef.setFont(QFont("Segoe UI", 8))
        self.btn_qdef.setFixedHeight(24)
        self.btn_qdef.setStyleSheet(_QDEF_BTN_STYLE)
        self.btn_qdef.setToolTip("Open the technical QDefinition viewer")
        self.btn_qdef.clicked.connect(self._open_qdef_viewer)
        self.btn_qdef.setVisible(False)
        _SAVE_OBJECT_BTN_STYLE = (
            "QPushButton { background-color: #0A2A5C; color: #D4AF37;"
            " border: 2px solid #D4AF37; border-radius: 3px;"
            " padding: 1px 4px; font-size: 8pt; font-weight: bold; }"
            "QPushButton:hover { background-color: #123C69; color: #F4D03F; }"
            "QPushButton:disabled { background-color: #6B7A90; color: #E6D8A6;"
            " border-color: #C9B46B; }"
        )
        self.btn_save_cyberlife = QPushButton("Save")
        self.btn_save_cyberlife.setFont(QFont("Segoe UI", 8, QFont.Weight.Bold))
        self.btn_save_cyberlife.setFixedSize(60, 36)
        self.btn_save_cyberlife.setStyleSheet(_SAVE_OBJECT_BTN_STYLE)
        self.btn_save_cyberlife.setToolTip("Update the current Cyberlife Query Object")
        self.btn_save_cyberlife.clicked.connect(self._save_cyberlife_query_object_update)
        self.btn_save_cyberlife.setVisible(False)
        self.btn_save_object = QPushButton("Save As")
        self.btn_save_object.setFont(QFont("Segoe UI", 8, QFont.Weight.Bold))
        self.btn_save_object.setFixedSize(60, 36)
        self.btn_save_object.setStyleSheet(_SAVE_OBJECT_BTN_STYLE)
        self.btn_save_object.setToolTip(
            "Save the current Cyberlife builder output as a new Query Object")
        self.btn_save_object.clicked.connect(self._save_cyberlife_query_object_as)
        self.btn_new_cyberlife = QPushButton("New Query")
        self.btn_new_cyberlife.setFont(QFont("Segoe UI", 8, QFont.Weight.Bold))
        self.btn_new_cyberlife.setFixedSize(78, 36)
        self.btn_new_cyberlife.setStyleSheet(_SAVE_OBJECT_BTN_STYLE)
        self.btn_new_cyberlife.setToolTip("Start a new Cyberlife Query Object")
        self.btn_new_cyberlife.clicked.connect(self._new_cyberlife_query_object)
        # Insert into header bar layout before window control buttons
        # Group 1: object tools — then spacer — Build Mode selector
        from PyQt6.QtWidgets import QSpacerItem, QSizePolicy
        header_layout = self.header_bar.layout()
        insert_pos = header_layout.count() - 3  # before min/max/close
        header_layout.insertWidget(insert_pos, self.btn_objects)
        header_layout.insertItem(insert_pos + 1,
            QSpacerItem(20, 0, QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Minimum))
        header_layout.insertWidget(insert_pos + 2, self.lbl_build_mode)
        header_layout.insertWidget(insert_pos + 3, self.btn_build_mode)
        header_layout.insertWidget(insert_pos + 4, self.btn_dataforge)
        # Dynamic query storage
        self._dynamic_queries: dict[str, DynamicQuery] = {}
        # Track which unpinned query is currently active
        self._active_unpinned: str | None = None
        # Track last active query/forge mode for restoring on space switch
        self._last_query_mode: str | None = None
        self._last_forge_mode: str | None = None
        self._active_unpinned_forge: str | None = None
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
        # Custom Display tab
        self.custom_display_tab = CustomDisplayTab()
        self.tabs.addTab(self.custom_display_tab, "Custom Display")
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
        # Common Tables tab
        self.cyb_common_tables_tab = CommonTablesTab()
        self.tabs.addTab(self.cyb_common_tables_tab, "Common Tables")
        # SQL tab
        self.sql_tab = SqlTab()
        self.tabs.addTab(self.sql_tab, "SQL")
        # Build SQL tab (hidden until "Move to Build" is clicked)
        self.build_sql_tab = BuildSqlTab()
        self._build_sql_tab_index = -1
        # Build SQL Results tab (hidden until build query is run)
        self.build_sql_results_tab = BuildSqlResultsTab()
        self._build_sql_results_tab_index = -1
        # Manual SQL Object editor screen (hidden until New Object chooses it)
        self.manual_sql_object_tab = ManualSqlObjectEditor()
        self.csv_excel_object_tab = CsvExcelObjectEditor()
        self.file_source_tab = FileSourceEditor()
        # Right-click on tab bar → close transient SQL/object tabs
        self.tabs.tabBar().setContextMenuPolicy(
            Qt.ContextMenuPolicy.CustomContextMenu)
        self.tabs.tabBar().customContextMenuRequested.connect(
            self._on_tab_context_menu)
        _left_lay.addWidget(self.tabs, 1)  # stretch=1 so tabs fill
        # ── Cyberlife bottom bar ─────────────────────────────────────
        self.cyberlife_bottom_bar = AuditBottomBar(
            bg_color=FOOTER_BG, run_label="Run")
        # Convenience aliases for existing code
        self.btn_all = self.cyberlife_bottom_bar.btn_all
        self.txt_max_count = self.cyberlife_bottom_bar.txt_max_count
        self.lbl_result_count = self.cyberlife_bottom_bar.lbl_result_count
        self.lbl_query_time = self.cyberlife_bottom_bar.lbl_query_time
        self.lbl_print_time = self.cyberlife_bottom_bar.lbl_print_time
        self.lbl_total_time = self.cyberlife_bottom_bar.lbl_total_time
        self.btn_run = self.cyberlife_bottom_bar.btn_run
        self.chk_coverage_level = QCheckBox("Coverage Level")
        self.chk_coverage_level.setFont(QFont("Segoe UI", 8, QFont.Weight.Bold))
        self.chk_coverage_level.setToolTip(
            "Return one row per matching coverage and show coverage-level values")
        self.cyberlife_bottom_bar.action_layout.addWidget(self.chk_coverage_level)
        self.cyberlife_bottom_bar.center_action_layout.addWidget(self.btn_new_cyberlife)
        self.cyberlife_bottom_bar.center_action_layout.addWidget(self.btn_save_object)
        self.cyberlife_bottom_bar.center_action_layout.addWidget(self.btn_save_cyberlife)
        # Left side: Region/SysCode
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
        self._forge_blank.setStyleSheet("QWidget { background-color: #FFF3E8; }")
        self._forge_blank.setVisible(False)
        self._dynamic_query_container.addWidget(self._forge_blank)
        # ── Query blank placeholder (shown when Queries space has no active query) ──
        self._query_blank = QWidget()
        self._query_blank.setStyleSheet("QWidget { background-color: #EDE9FE; }")
        query_blank_layout = QVBoxLayout(self._query_blank)
        query_blank_layout.setContentsMargins(0, 0, 0, 0)
        query_blank_layout.setSpacing(0)
        query_blank_layout.addStretch()
        self._query_blank_footer = AuditBottomBar(
            bg_color=FOOTER_BG, run_label="Run")
        self._query_blank_footer.btn_all.setVisible(False)
        self._query_blank_footer.txt_max_count.setVisible(False)
        self._query_blank_footer.lbl_max_count.setVisible(False)
        self._btn_query_blank_new = QPushButton("New Query")
        self._btn_query_blank_new.setFont(QFont("Segoe UI", 8, QFont.Weight.Bold))
        self._btn_query_blank_new.setFixedSize(78, 36)
        self._btn_query_blank_new.setStyleSheet(_SAVE_OBJECT_BTN_STYLE)
        self._btn_query_blank_new.setToolTip("Start a new Visual Query Object")
        self._btn_query_blank_new.clicked.connect(self._start_visual_query_object)
        self._query_blank_footer.action_layout.addWidget(self._btn_query_blank_new)
        self._btn_query_blank_save_as = QPushButton("Save As")
        self._btn_query_blank_save_as.setFont(QFont("Segoe UI", 8, QFont.Weight.Bold))
        self._btn_query_blank_save_as.setFixedSize(60, 36)
        self._btn_query_blank_save_as.setStyleSheet(_SAVE_OBJECT_BTN_STYLE)
        self._btn_query_blank_save_as.setToolTip("Create and save a new Visual Query Object")
        self._btn_query_blank_save_as.clicked.connect(self._start_visual_query_object)
        self._query_blank_footer.action_layout.addWidget(self._btn_query_blank_save_as)
        self._query_blank_footer.btn_run.clicked.connect(self._start_visual_query_object)
        query_blank_layout.addWidget(self._query_blank_footer)
        self._query_blank.setVisible(False)
        self._dynamic_query_container.addWidget(self._query_blank)
        self.manual_sql_object_tab.setVisible(False)
        self._dynamic_query_container.addWidget(self.manual_sql_object_tab)
        self.csv_excel_object_tab.setVisible(False)
        self._dynamic_query_container.addWidget(self.csv_excel_object_tab)
        self.file_source_tab.setVisible(False)
        self._dynamic_query_container.addWidget(self.file_source_tab)
        # DataForge group storage
        self._dataforge_groups: dict[str, DataForgeGroup] = {}
        # ── Left picker panel (embedded) ───────────────────────────
        from suiteview.audit.dataforge.query_field_picker import QueryFieldPicker
        from PyQt6.QtWidgets import QStackedWidget
        self._field_picker = FieldPickerPanel()
        self._field_picker.field_requested.connect(self._on_picker_field_requested)
        self._field_picker.query_clicked.connect(self._on_picker_query_clicked)
        self._field_picker.new_query_requested.connect(self._start_visual_query_object)
        self._field_picker.pinned_tables_changed.connect(self._on_picker_pinned_tables_changed)
        self._field_picker.common_table_requested.connect(self._on_picker_common_table_requested)
        self._field_picker.common_table_remove_requested.connect(self._on_picker_common_table_remove_requested)
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
        self._forge_field_picker.source_refreshed.connect(
            self._on_forge_picker_source_refreshed)
        self._forge_field_picker.query_table_requested.connect(
            self._on_forge_picker_query_table_requested)
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
            "QSplitter::handle { background: #FED7AA; }"
            "QSplitter::handle:hover { background: #EA580C; }")
        self._content_splitter.addWidget(self._picker_container)
        self._content_splitter.addWidget(self._content_left)
        self._content_splitter.setStretchFactor(0, 0)
        self._content_splitter.setStretchFactor(1, 1)
        self._content_splitter.setSizes([0, 900])
        self._content_splitter.splitterMoved.connect(self._on_content_splitter_moved)
        root.addWidget(self._content_splitter, 1)
        self._mode_footer_host = QWidget()
        self._mode_footer_host.setVisible(False)
        self._mode_footer_layout = QVBoxLayout(self._mode_footer_host)
        self._mode_footer_layout.setContentsMargins(0, 0, 0, 0)
        self._mode_footer_layout.setSpacing(0)
        self._active_mode_footer = None
        root.addWidget(self._mode_footer_host)
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
        self.manual_sql_object_tab.set_connection_options(
            self._manual_sql_odbc_connections(),
            DB2Connection(self.cmb_region.currentText()).dsn,
        )
    def _connect_signals(self):
        self.btn_run.clicked.connect(self._run_audit)
        self.sql_tab.build_sql_requested.connect(self._build_cyberlife_sql_only)
        self.sql_tab.move_to_build.connect(self._on_move_to_build)
        self.build_sql_tab.run_sql_requested.connect(self._run_build_sql)
        self.manual_sql_object_tab.preview_requested.connect(self._run_manual_sql_preview)
        self.manual_sql_object_tab.save_requested.connect(self._save_manual_sql_object)
        self.csv_excel_object_tab.saved.connect(lambda _: self._open_query_object_viewer())
        self.file_source_tab.query_requested.connect(self._open_manual_sql_on_file_source)
        self.file_source_tab.visual_query_requested.connect(self._open_visual_query_on_file_source)
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
            is_manual_sql_object = (mode == "__manual_sql_object__")
            is_csv_excel_object = (mode == "__csv_excel_object__")
            self.tabs.setVisible(is_cyberlife)
            self.cyberlife_bottom_bar.setVisible(is_cyberlife)
            self._forge_blank.setVisible(is_forge_blank)
            self._query_blank.setVisible(is_query_blank)
            self.manual_sql_object_tab.setVisible(is_manual_sql_object)
            self.csv_excel_object_tab.setVisible(is_csv_excel_object)
            self.file_source_tab.setVisible(mode == "__file_source__")
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
        elif mode == "__manual_sql_object__":
            self._enter_manual_sql_object_mode()
        elif mode == "__csv_excel_object__":
            self._enter_csv_excel_object_mode()
        elif mode == "__file_source__":
            self._enter_file_source_mode()
        else:
            self._enter_cyberlife_mode()
    def _enter_cyberlife_mode(self):
        """Configure UI for Cyberlife mode."""
        self._hide_mode_footer()
        self._style_build_mode_button("cyberlife")
        self.btn_save_cyberlife.setVisible(bool(self._cyberlife_saved_object_name.strip()))
        self.btn_cyberlife.blockSignals(True)
        self.btn_cyberlife.setChecked(True)
        self.btn_cyberlife.blockSignals(False)
        self.btn_dataforge.blockSignals(True)
        self.btn_dataforge.setChecked(False)
        self.btn_dataforge.blockSignals(False)
        self.tabs.setStyleSheet(self._CYB_TAB_STYLE)
        self._save_picker_width()
        self._hide_picker_panel()
    def _enter_query_mode(self, mode: str, prev_had_picker: bool):
        """Configure UI for a dynamic query or the query-blank placeholder."""
        self._style_build_mode_button("visual")
        self.btn_cyberlife.blockSignals(True)
        self.btn_cyberlife.setChecked(False)
        self.btn_cyberlife.blockSignals(False)
        self.btn_dataforge.blockSignals(True)
        self.btn_dataforge.setChecked(False)
        self.btn_dataforge.blockSignals(False)
        self._save_picker_width()
        self._refresh_picker_query_list()
        self._content_splitter.setStyleSheet(
            "QSplitter::handle { background: #DDD6FE; }"
            "QSplitter::handle:hover { background: #7C3AED; }")
        if mode in self._dynamic_queries:
            dq = self._dynamic_queries[mode]
            self._set_mode_footer(dq.bottom_bar)
            if dq.dsn.startswith("file:"):
                self._bind_picker_to_file_source(dq)
            else:
                self._field_picker.set_connection_options(
                    self._manual_sql_odbc_connections(), dq.dsn)
                self._field_picker.set_group(
                    dq.dsn, dq.tables, dq.display_names,
                    preferred_table=self._preferred_query_table(dq),
                    pinned_tables=dq.pinned_tables)
                dq.set_source_dsn(self._field_picker.current_connection())
                self._push_common_tables_to_picker(dq)
            raw_name = mode.removeprefix("▸ ")
            self._field_picker.highlight_query(raw_name)
        else:
            self._set_mode_footer(self._query_blank_footer)
            self._field_picker.clear()
            self._field_picker.set_connection_options(
                self._manual_sql_odbc_connections(),
                DB2Connection(self.cmb_region.currentText()).dsn,
            )
        self._picker_stack.setCurrentWidget(self._field_picker)
        if not prev_had_picker:
            self._show_picker_panel()
    def _enter_forge_mode(self, mode: str, prev_had_picker: bool):
        """Configure UI for a DataForge or the forge-blank placeholder."""
        self._hide_mode_footer()
        self.btn_cyberlife.blockSignals(True)
        self.btn_cyberlife.setChecked(False)
        self.btn_cyberlife.blockSignals(False)
        self.btn_dataforge.blockSignals(True)
        self.btn_dataforge.setChecked(True)
        self.btn_dataforge.blockSignals(False)
        self._save_picker_width()
        self._refresh_picker_forge_list()
        fg = self._dataforge_groups.get(mode)
        if fg:
            self._set_forge_picker_sources(fg)
            raw_name = mode.removeprefix("⚙ ")
            self._forge_field_picker.highlight_forge(raw_name)
        self._content_splitter.setStyleSheet(
            "QSplitter::handle { background: #FED7AA; }"
            "QSplitter::handle:hover { background: #EA580C; }")
        self._picker_stack.setCurrentWidget(self._forge_field_picker)
        if not prev_had_picker:
            self._show_picker_panel()
    def _enter_manual_sql_object_mode(self):
        """Configure UI for the standalone Manual SQL Object editor."""
        self._hide_mode_footer()
        self._style_build_mode_button("manual_sql")
        self.btn_cyberlife.blockSignals(True)
        self.btn_cyberlife.setChecked(False)
        self.btn_cyberlife.blockSignals(False)
        self.btn_workbench.setChecked(False)
        self.btn_dataforge.setChecked(False)
        self._save_picker_width()
        self._hide_picker_panel()
        self._content_splitter.setStyleSheet(
            "QSplitter::handle { background: #AFC3DA; }"
            "QSplitter::handle:hover { background: #1E5BA8; }")

    def _enter_csv_excel_object_mode(self):
        """Configure UI for the File Source Object editor."""
        self._hide_mode_footer()
        self._style_build_mode_button("file")
        self.btn_cyberlife.blockSignals(True)
        self.btn_cyberlife.setChecked(False)
        self.btn_cyberlife.blockSignals(False)
        self.btn_workbench.setChecked(False)
        self.btn_dataforge.setChecked(False)
        self._save_picker_width()
        self._hide_picker_panel()
        self._content_splitter.setStyleSheet(
            "QSplitter::handle { background: #AFC3DA; }"
            "QSplitter::handle:hover { background: #1E5BA8; }")

    def _enter_file_source_mode(self):
        """Configure UI for the File Source editor (define a flat-file data source)."""
        self._hide_mode_footer()
        self._style_build_mode_button("file")
        self.btn_cyberlife.blockSignals(True)
        self.btn_cyberlife.setChecked(False)
        self.btn_cyberlife.blockSignals(False)
        self.btn_workbench.setChecked(False)
        self.btn_dataforge.setChecked(False)
        self._save_picker_width()
        self._hide_picker_panel()
        self._content_splitter.setStyleSheet(
            "QSplitter::handle { background: #AFC3DA; }"
            "QSplitter::handle:hover { background: #1E5BA8; }")

    def _save_picker_width(self):
        """Capture current picker width before switching modes."""
        if self._picker_container.isVisible():
            self._picker_width = self._content_splitter.sizes()[0]

    def _set_mode_footer(self, footer: QWidget):
        """Show a mode-specific footer across the full content width."""
        if self._active_mode_footer is not footer:
            if self._active_mode_footer is not None:
                self._active_mode_footer.setVisible(False)
            while self._mode_footer_layout.count():
                item = self._mode_footer_layout.takeAt(0)
                widget = item.widget()
                if widget is not None:
                    widget.setVisible(False)
            self._mode_footer_layout.addWidget(footer)
            self._active_mode_footer = footer
        footer.setVisible(True)
        self._mode_footer_host.setVisible(True)

    def _hide_mode_footer(self):
        """Hide the full-width mode footer host."""
        if self._active_mode_footer is not None:
            self._active_mode_footer.setVisible(False)
        self._mode_footer_host.setVisible(False)
    # ── Field Picker panel ───────────────────────────────────────────
    def _update_field_picker(self):
        """Populate the field picker from the active dynamic query."""
        group = self._dynamic_queries.get(self._current_mode)
        if group is not None:
            self._field_picker.set_connection_options(
                self._manual_sql_odbc_connections(), group.dsn)
            self._field_picker.set_group(
                group.dsn, group.tables, group.display_names,
                pinned_tables=group.pinned_tables)
            self._push_common_tables_to_picker(group)
        else:
            self._field_picker.clear()

    def _on_common_tables_changed(self, common_cols: dict):
        """A DynamicQuery's common tables changed — refresh field picker."""
        # Only update picker if the emitting group is the active one
        group = self._dynamic_queries.get(self._current_mode)
        if group is not None:
            self._field_picker.set_common_tables(common_cols)

    def _push_common_tables_to_picker(self, group):
        """Push a DynamicQuery's common table info to the field picker."""
        common_cols: dict[str, list[tuple[str, str]]] = {}
        for ct in group.common_tables_tab.get_selected_tables():
            cols = [(c["name"], c.get("type", "TEXT")) for c in ct.columns]
            common_cols[ct.name] = cols
        self._field_picker.set_common_tables(common_cols)
    def _on_picker_field_requested(self, table: str, column: str,
                                   type_name: str, display: str):
        """Double-click in field picker — delegate to the active dynamic query."""
        group = self._dynamic_queries.get(self._current_mode)
        if group is not None:
            group.set_source_dsn(self._field_picker.current_connection())
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
            self._field_picker.set_connection_options(
                self._manual_sql_odbc_connections(), group.dsn)
            self._field_picker.set_group(
                group.dsn, group.tables, group.display_names,
                preferred_table=self._preferred_query_table(group),
                pinned_tables=group.pinned_tables)
            self._field_picker.highlight_query(sq.name)
    def _on_picker_tables_changed(self, tables: list[str]):
        """Tables list was changed in the picker — sync back to the query."""
        group = self._dynamic_queries.get(self._current_mode)
        if group is not None:
            group.set_source_dsn(self._field_picker.current_connection())
            group.tables = list(tables)

    def _on_picker_pinned_tables_changed(self, tables: list[str]):
        """Pinned SQL Assist tables changed for the active Visual Query."""
        group = self._dynamic_queries.get(self._current_mode)
        if group is not None:
            group.set_pinned_tables(tables)

    def _on_picker_common_table_requested(self, table_name: str):
        """Add a Common Table selected from SQL Assist to the active Visual Query."""
        group = self._dynamic_queries.get(self._current_mode)
        if group is None:
            return
        group.add_common_table(table_name)
        self._push_common_tables_to_picker(group)
        self._field_picker._preferred_table = table_name
        self._field_picker._rebuild_table_list()

    def _on_picker_common_table_remove_requested(self, table_name: str):
        """Remove a Common Table selected from SQL Assist from the active Visual Query."""
        group = self._dynamic_queries.get(self._current_mode)
        if group is None:
            return
        group.remove_common_table(table_name)
        self._push_common_tables_to_picker(group)
    def _refresh_picker_query_list(self):
        """Refresh the query list in the field picker from saved queries."""
        from suiteview.audit import saved_query_store as sq_store
        queries = sq_store.list_queries()
        names = [sq.name for sq in queries]
        self._field_picker.set_queries(names)

    @staticmethod
    def _preferred_query_table(group) -> str:
        preferred_table = getattr(group, "preferred_picker_table", None)
        if callable(preferred_table):
            table = preferred_table()
            if table:
                return table
        for table in group.tables:
            if table:
                return table
        for tab in group._criteria_tabs:
            for row in tab.grid._rows:
                table = group._table_from_field_key(row.field_key)
                if table:
                    return table
        for item in group.select_tab.get_select_columns():
            table = group._table_from_field_key(item.get("field_key", ""))
            if table:
                return table
        return ""
    def _on_forge_picker_field_requested(self, query_name: str, col_name: str):
        """Double-click in forge field picker — delegate to active DataForge group."""
        group = self._dataforge_groups.get(self._current_mode)
        if group is not None:
            group.on_field_requested(query_name, col_name)

    def _on_forge_picker_query_table_requested(self, query_name: str):
        """Double-click in Forge Assist queries — add query to join canvas."""
        group = self._dataforge_groups.get(self._current_mode)
        if group is None:
            return
        if query_name not in group._sources:
            qd = group.add_source_copy(query_name)
            if qd is None:
                return
            query_name = qd.name
            self._set_forge_picker_sources(group)
        add_query_table = getattr(group.joins_tab, "add_query_table", None)
        if callable(add_query_table) and add_query_table(query_name):
            group.tab_widget.setCurrentWidget(group.joins_tab)
            group._schedule_save()

    def _on_picker_forge_clicked(self, forge_name: str):
        """User clicked a forge name in the picker's forge list."""
        from suiteview.audit.dataforge import dataforge_store as df_store
        forge = df_store.load_forge(forge_name)
        if forge is None:
            return
        self._on_load_dataforge(forge)
        display = f"⚙ {forge.name}"
        group = self._dataforge_groups.get(display)
        self._sync_forge_picker_to_group(group, forge.name)

    def _sync_forge_picker_to_group(self, group, forge_name: str = ""):
        """Show the active DataForge group's source queries in Forge Assist."""
        if group is None:
            return
        self._set_forge_picker_sources(group)
        self._forge_field_picker.highlight_forge(
            forge_name or group._saved_forge_name)

    def _set_forge_picker_sources(self, group):
        names = (group.picker_source_names()
                 if hasattr(group, "picker_source_names")
                 else list(group._sources.keys()))
        definitions = (group.picker_source_definitions()
                       if hasattr(group, "picker_source_definitions")
                       else group._sources)
        self._forge_field_picker.set_sources(
            names,
            forge_name=group._saved_forge_name,
            source_definitions=definitions,
        )

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
            group.sync_source_copies(source_names)
            self._set_forge_picker_sources(group)

    def _refresh_query_object_browser_if_open(self):
        try:
            from .query_object_viewer_window import QueryObjectViewerWindow
        except Exception:
            logger.exception("Failed to import Query Object browser for refresh")
            return
        viewer = getattr(QueryObjectViewerWindow, "_instance", None)
        if viewer is not None and viewer.isVisible():
            viewer.refresh()

    def _on_forge_picker_source_refreshed(self, old_name: str, qd):
        """A forge source query was edited/refreshed from Forge Assist."""
        group = self._dataforge_groups.get(self._current_mode)
        if group is None or qd is None:
            return
        old_key = old_name
        object_id = group._query_object_id_from_qdefinition(qd)
        if object_id:
            for key, source in group._sources.items():
                if group._query_object_id_from_qdefinition(source) == object_id:
                    old_key = key
                    break
        if old_key != qd.name:
            group._sources.pop(old_key, None)
            group._sources.pop(old_name, None)
            mapping = {old_key: qd.name}
            group._rename_join_sources(mapping)
            group._rename_filter_sources(mapping)
            group._rename_display_sources(mapping)
        group._sources[qd.name] = qd
        group._datasets.pop(old_key, None)
        group._datasets.pop(old_name, None)
        group._datasets.pop(qd.name, None)
        group.joins_tab.update_queries(
            list(group._sources.keys()),
            group._query_columns_map(),
            group._query_column_types_map(),
        )
        group._schedule_save()
        group._persist_source_roster_if_saved()
        self._set_forge_picker_sources(group)
        self._forge_field_picker.add_source(qd.name)
        self._refresh_query_object_browser_if_open()

    @staticmethod
    def _dataforge_source_copy_name(source_name: str, forge_name: str) -> str:
        """Return a stable Query Object copy name for a DataForge source."""
        label = forge_name.strip() or "DataForge"
        return f"{source_name} [{label}]"
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

    def _create_blank_visual_query(self):
        """Create an unsaved Visual Query builder without prompting."""
        base_name = "Visual Query"
        suffix = 1
        name = base_name
        while name in self._dynamic_queries:
            suffix += 1
            name = f"{base_name} {suffix}"

        try:
            dsn = DB2Connection(self.cmb_region.currentText()).dsn
        except Exception:
            dsn = self.cmb_region.currentText()

        self._create_dynamic_query(name, dsn, [], saved_query_name="")
        prev = self._active_unpinned
        self._active_unpinned = name
        self._switch_mode(name)
        if prev and prev != name:
            self._remove_query(prev)

    def _create_dynamic_query(self, name: str, dsn: str, tables: list[str],
                              display_names: dict[str, str] | None = None,
                              saved_query_name: str = ""):
        """Create a DynamicQuery widget and wire it into the UI."""
        group = DynamicQuery(name, dsn, tables, display_names, parent=self,
                             saved_query_name=saved_query_name)
        group.setVisible(False)
        self._dynamic_queries[name] = group
        self._dynamic_query_container.addWidget(group)
        group.query_saved.connect(self._on_dynamic_query_saved)
        group.query_deleted.connect(self._on_query_deleted_from_group)
        group.common_tables_changed.connect(self._on_common_tables_changed)
        group.new_query_requested.connect(self._start_visual_query_object)

    def _on_dynamic_query_saved(self, saved_query):
        self._refresh_picker_query_list()
        name = getattr(saved_query, "name", "")
        if name:
            self.query_object_saved.emit(name)

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
    # ── QDefinition Viewer ───────────────────────────────────────────
    def _open_qdef_viewer(self):
        """Open the QDefinition viewer window."""
        try:
            from .qdef_viewer_window import QDefViewerWindow
            QDefViewerWindow.show_instance(parent=None)
        except Exception as exc:
            logger.exception("Failed to open QDef viewer window")
            QMessageBox.warning(self, "QDef Error", str(exc))
    def _open_query_object_viewer(self):
        """Open the unified Query Object browser window."""
        try:
            from .query_object_viewer_window import QueryObjectViewerWindow
            QueryObjectViewerWindow.show_instance(parent=self)
        except Exception as exc:
            logger.exception("Failed to open Query Object browser")
            QMessageBox.warning(self, "Query Object Error", str(exc))

    def open_query_object_in_builder(self, object_name: str):
        """Open a QueryObject in the builder that owns its editable design."""
        from suiteview.audit import query_object_store, saved_query_store as sq_store
        from suiteview.audit.query_object import (
            OBJECT_KIND_ADHOC_SOURCE,
            OBJECT_KIND_CYBERLIFE,
            OBJECT_KIND_EXECUTABLE,
            OBJECT_KIND_MANUAL_SQL,
            OBJECT_KIND_VISUAL,
        )

        obj = query_object_store.load_object(object_name)
        if obj is None:
            QMessageBox.warning(
                self,
                "Query Object Missing",
                f"Could not find query object \"{object_name}\".",
            )
            return
        if (obj.config or {}).get("dataforge") and obj.kind == OBJECT_KIND_EXECUTABLE:
            if self._open_dataforge_source_design(obj):
                return
        if obj.kind == OBJECT_KIND_MANUAL_SQL:
            self.open_manual_sql_object(obj)
            return
        if obj.kind == OBJECT_KIND_ADHOC_SOURCE:
            self.open_csv_excel_object(obj)
            return
        if obj.kind == OBJECT_KIND_CYBERLIFE:
            self.open_cyberlife_query_object(obj)
            return
        if obj.kind == OBJECT_KIND_EXECUTABLE:
            self.open_manual_sql_object(obj)
            return
        if obj.kind != OBJECT_KIND_VISUAL:
            QMessageBox.information(
                self,
                "Builder Not Available",
                "Only Cyberlife, visual Query Studio, Manual SQL, File Source, and DataForge query objects can be reopened in a designer right now.",
            )
            return

        saved = sq_store.load_query(obj.name)
        if saved is None:
            saved = query_object_store.restore_saved_visual_design(obj)
        if saved is None:
            QMessageBox.warning(
                self,
                "Saved Design Missing",
                "This object does not have a matching saved visual design to reopen.",
            )
            return
        self.btn_workbench.setChecked(True)
        self._toggle_saved_queries_shelf(True)
        self._on_load_saved_query(saved)

    def _open_dataforge_source_design(self, obj) -> bool:
        """Open an upstream design only for DataForge copies without a native builder."""
        from suiteview.audit import query_object_store, saved_query_store as sq_store

        dataforge = (obj.config or {}).get("dataforge", {})
        candidates = [
            str(dataforge.get("source_name", "")).strip(),
            self._dataforge_copy_source_name(obj.name),
            str(obj.source_design or "").strip(),
        ]
        for candidate in candidates:
            if not candidate or candidate == obj.name:
                continue
            original = query_object_store.load_object(candidate)
            if original is not None:
                self.open_query_object_in_builder(original.name)
                return True
            saved = sq_store.load_query(candidate)
            if saved is not None:
                self.btn_workbench.setChecked(True)
                self._toggle_saved_queries_shelf(True)
                self._on_load_saved_query(saved)
                return True
        return False

    @staticmethod
    def _dataforge_copy_source_name(name: str) -> str:
        clean = str(name or "").strip()
        if not clean.endswith("]"):
            return ""
        source, sep, _suffix = clean.rpartition(" [")
        if not sep:
            return ""
        return source.strip()

    def open_dataforge_in_builder(self, forge_name: str):
        """Open a saved DataForge, or a new DataForge for unnamed source copies."""
        from suiteview.audit.dataforge import dataforge_store as df_store

        name = forge_name.strip()
        self.btn_dataforge.setChecked(True)
        if not name or name.lower() in {"(new)", "dataforge"}:
            forge = df_store.load_forge(name) if name else None
            if forge is None:
                self._create_blank_dataforge()
                self._refresh_picker_forge_list()
                return
        else:
            forge = df_store.load_forge(name)
        if forge is None:
            QMessageBox.warning(
                self,
                "DataForge Missing",
                f"Could not find DataForge \"{name}\".",
            )
            return
        self._on_load_dataforge(forge)
        self._refresh_picker_forge_list()
        self._sync_forge_picker_to_group(
            self._dataforge_groups.get(f"⚙ {forge.name}"), forge.name)

    def _show_new_object_menu(self):
        """Show the Query Object creation chooser."""
        dlg = QueryObjectModeDialog(self)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        chosen = dlg.selected_mode
        if chosen == "cyberlife":
            self._start_cyberlife_object()
        elif chosen == "visual":
            self._start_visual_query_object()
        elif chosen == "manual_sql":
            self._start_manual_sql_object()

    def _style_build_mode_button(self, mode: str):
        """Paint the selector in the active mode's identity color."""
        from suiteview.audit.build_mode_styles import build_mode_style, mode_icon

        style = build_mode_style(mode)
        self._selected_build_mode = mode
        self.btn_build_mode.setText(style.label)
        self.btn_build_mode.setIcon(mode_icon("#FFFFFF"))
        self.btn_build_mode.setFixedSize(_BUILD_MODE_BUTTON_WIDTH, 24)
        self.btn_build_mode.setStyleSheet(
            f"QToolButton {{ background-color: {style.color}; color: white;"
            " border: 1px solid rgba(255,255,255,0.45); border-radius: 3px;"
            " padding: 2px 8px; font-weight: bold; }"
            f"QToolButton:hover {{ background-color: {style.color};"
            " border: 1px solid white; }"
            "QToolButton::menu-button { border-left: 1px solid rgba(255,255,255,0.45); width: 22px; }"
            "QToolButton::menu-arrow { image: none; border-left: 4px solid transparent;"
            " border-right: 4px solid transparent; border-top: 5px solid white;"
            " width: 0px; height: 0px; margin-right: 6px; }")

    def _on_build_mode_button_clicked(self, checked: bool = False):
        """Activate the current build mode from the main split-button face."""
        self._on_build_mode_selected(self._selected_build_mode)

    def _on_build_mode_selected(self, mode: str):
        """Switch the primary Audit build surface from the header selector."""
        self._style_build_mode_button(mode)
        if mode == "cyberlife":
            self._switch_mode("cyberlife")
        elif mode == "visual":
            self._open_visual_query_builder()
        elif mode == "manual_sql":
            self._start_manual_sql_object(reset=False)

    def _open_visual_query_builder(self):
        """Open the tabbed Visual Query builder, creating one if needed."""
        self.btn_workbench.setChecked(True)
        if self._current_mode in self._dynamic_queries:
            self._toggle_saved_queries_shelf(True)
            return
        if self._last_query_mode and self._last_query_mode in self._dynamic_queries:
            self._switch_mode(self._last_query_mode)
            self._refresh_picker_query_list()
            return
        self._start_visual_query_object()

    def _open_dataforge_builder(self):
        """Open the DataForge builder, restoring an active forge when possible."""
        self.btn_dataforge.setChecked(True)
        self._toggle_dataforge_shelf(True)

    def _start_cyberlife_object(self):
        """Switch to Cyberlife; the header Save button publishes the object."""
        self._switch_mode("cyberlife")
        QMessageBox.information(
            self,
            "Cyberlife Object",
            "Build the Cyberlife criteria, then use Save Cyberlife Object.",
        )

    def _start_visual_query_object(self):
        """Start a blank unsaved Visual Query Object builder."""
        self.btn_workbench.setChecked(True)
        self._toggle_saved_queries_shelf(True)
        self._create_blank_visual_query()

    def _start_manual_sql_object(self, *, reset: bool = True):
        """Open the dedicated Manual SQL Object editor shell."""
        if reset or not self._manual_sql_started:
            self.manual_sql_object_tab.new_object()
            self._manual_sql_started = True
        self.manual_sql_object_tab.set_connection_options(
            self._manual_sql_odbc_connections(),
            DB2Connection(self.cmb_region.currentText()).dsn,
        )
        self._switch_mode("__manual_sql_object__")

    def _start_csv_excel_object(self, *, reset: bool = True):
        """Open the legacy single-file CSV/Excel object editor (for old adhoc objects)."""
        if reset:
            self.csv_excel_object_tab.new_object()
        self._switch_mode("__csv_excel_object__")

    def new_file_source(self):
        """Open the File Source editor on a blank new flat-file data source.

        Creating a File Source lives on the Object Browser's Data Sources tab
        (a source is a thing you connect to, not a query build mode) — this is
        the entry point that tab calls.
        """
        self.file_source_tab.new_object()
        self._switch_mode("__file_source__")

    def open_manual_sql_object(self, obj):
        """Open a saved Manual SQL QueryObject in its editor."""
        self._manual_sql_started = True
        self.manual_sql_object_tab.load_object(obj)
        self.manual_sql_object_tab.set_connection_options(
            self._manual_sql_odbc_connections(),
            obj.dsn or DB2Connection(self.cmb_region.currentText()).dsn,
        )
        self._switch_mode("__manual_sql_object__")

    def open_csv_excel_object(self, obj):
        """Open a saved (legacy) File Source QueryObject in its editor."""
        self.csv_excel_object_tab.load_object(obj)
        self._switch_mode("__csv_excel_object__")

    def open_file_source(self, fds):
        """Open a saved FileDataSource in the File Source editor."""
        self.file_source_tab.load_file_source(fds)
        self._switch_mode("__file_source__")

    def open_cyberlife_query_object(self, obj):
        """Open a saved Cyberlife QueryObject in the Cyberlife builder."""
        config = obj.config or {}
        criteria = config.get("criteria") or {}

        region = config.get("region") or ""
        if region:
            idx = self.cmb_region.findText(region)
            if idx >= 0:
                self.cmb_region.setCurrentIndex(idx)

        system_code = config.get("system_code") or ""
        idx_sys = self.cmb_system.findText(system_code)
        if idx_sys >= 0:
            self.cmb_system.setCurrentIndex(idx_sys)

        self.txt_max_count.setText(str(criteria.get("max_count", "25")))
        self.chk_coverage_level.setChecked(bool(criteria.get("coverage_level", False)))

        common_tables = criteria.get("common_tables")
        if common_tables:
            self.cyb_common_tables_tab.set_state(common_tables)

        tab_states = criteria.get("tabs") or {}
        for key, tab in self._cyberlife_criteria_tabs():
            tab.set_state(tab_states.get(key, {}))

        self._cyberlife_saved_object_name = obj.name
        self.btn_save_cyberlife.setVisible(True)
        self._switch_mode("cyberlife")

    def _import_file_query_object(self):
        """Import a file source directly into the Query Object catalog."""
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Import File Source Object",
            "",
            "Data Files (*.csv *.txt *.dat *.psv *.tsv *.xlsx *.xlsm *.xls);;Text Files (*.csv *.txt *.dat *.psv *.tsv);;Excel Files (*.xlsx *.xlsm *.xls);;All Files (*.*)",
        )
        if not path:
            return
        default_name = path.rsplit("/", 1)[-1].rsplit("\\", 1)[-1].rsplit(".", 1)[0]
        name, ok = QInputDialog.getText(
            self,
            "File Source Object Name",
            "Object name:",
            text=default_name,
        )
        if not ok or not name.strip():
            return
        try:
            from suiteview.audit.adhoc_source_intake import query_object_from_file
            from suiteview.audit import query_object_store

            obj = query_object_from_file(path, name=name.strip())
            query_object_store.save_object(obj)
        except Exception as exc:
            logger.exception("File QueryObject import failed: %s", path)
            QMessageBox.warning(
                self,
                "Import Failed",
                f"Could not import file source object:\n\n{exc}",
            )
            return
        QMessageBox.information(
            self,
            "Query Object Imported",
            f"Imported \"{obj.name}\" with {len(obj.fields)} fields.",
        )
        self._open_query_object_viewer()
    # ── Query building ───────────────────────────────────────────────
    def _build_sql(self) -> str:
        """Build the CyberLife audit SQL — delegates to cyberlife_query module."""
        region = self.cmb_region.currentText()
        schema = REGION_SCHEMA_MAP.get(region, DEFAULT_SCHEMA)
        sql = build_cyberlife_sql(
            schema=schema,
            sys_code=self.cmb_system.currentText().strip(),
            max_count_text=self.txt_max_count.text().strip(),
            coverage_level=self.chk_coverage_level.isChecked(),
            policy_tab=self.policy_tab,
            display_tab=self.display_tab,
            custom_display_tab=self.custom_display_tab,
            policy2_tab=self.policy2_tab,
            adv_tab=self.adv_tab,
            coverages_tab=self.coverages_tab,
            plancode_tab=self.plancode_tab,
            benefits_tab=self.benefits_tab,
            transaction_tab=self.transaction_tab,
        )

        # Prepend Common Table CTEs if any are selected
        common_tables = self.cyb_common_tables_tab.get_selected_tables()
        if common_tables:
            cte_prefix = build_common_table_cte(common_tables, dialect="DB2")
            # Cyberlife SQL starts with 'WITH COVERAGE1 AS ...'
            # Merge by replacing 'WITH' with the common tables CTE + comma
            if sql.strip().upper().startswith("WITH "):
                sql = cte_prefix + ",\n" + sql.strip()[4:]  # strip 'WITH'
            else:
                sql = cte_prefix + "\n" + sql

        return sql

    def _build_cyberlife_sql_only(self):
        """Build and show Cyberlife SQL without executing the query."""
        try:
            sql = self._build_sql()
        except Exception as exc:
            logger.exception("Failed to build audit SQL")
            QMessageBox.warning(self, "SQL Build Error", str(exc))
            return
        self.sql_tab.set_sql(sql)
        self.tabs.setCurrentWidget(self.sql_tab)
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
            ("custom_display", self.custom_display_tab),
            ("plancode", self.plancode_tab),
        ]
    def _cyberlife_query_object_state(self) -> dict:
        """Return the Cyberlife builder state stored in a QueryObject config."""
        return {
            "max_count": self.txt_max_count.text().strip(),
            "coverage_level": self.chk_coverage_level.isChecked(),
            "common_tables": self.cyb_common_tables_tab.get_state(),
            "tabs": {
                key: tab.get_state()
                for key, tab in self._cyberlife_criteria_tabs()
            },
        }

    def _new_cyberlife_query_object(self):
        """Start a new unsaved Cyberlife Query Object."""
        reply = QMessageBox.question(
            self,
            "Start New Query?",
            "This will clear the current Cyberlife query builder. Continue?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return
        self._cyberlife_saved_object_name = ""
        self.btn_save_cyberlife.setVisible(False)
        self._on_clear_cyberlife()
        self._switch_mode("cyberlife")

    def _save_cyberlife_query_object_update(self):
        """Update the current Cyberlife QueryObject, or Save As if none exists."""
        if not self._cyberlife_saved_object_name:
            self._save_cyberlife_query_object_as()
            return
        self._save_cyberlife_query_object(self._cyberlife_saved_object_name)

    def _save_cyberlife_query_object_as(self):
        """Save the current Cyberlife builder as a new QueryObject."""
        self._save_cyberlife_query_object("")

    def _save_cyberlife_query_object(self, object_name: str = ""):
        """Publish current Cyberlife builder SQL/state as one QueryObject."""
        if self._current_mode != "cyberlife":
            QMessageBox.information(
                self, "Save Object",
                "Switch to Cyberlife to save the Cyberlife builder as an object.")
            return
        try:
            sql = self._build_sql()
        except Exception as exc:
            logger.exception("Failed to build Cyberlife SQL for QueryObject")
            QMessageBox.warning(self, "SQL Build Error", str(exc))
            return
        self.sql_tab.set_sql(sql)

        name = object_name.strip()
        if not name:
            name, ok = QInputDialog.getText(
                self, "Save Query Object",
                "Object name:",
                text=self._cyberlife_saved_object_name or "Cyberlife Base Extract",
            )
            if not ok or not name.strip():
                return
            name = name.strip()

        region = self.cmb_region.currentText()
        system_code = self.cmb_system.currentText().strip()
        try:
            dsn = DB2Connection(region).dsn
        except Exception:
            dsn = region

        result_columns: list[str] = []
        column_types: dict[str, str] = {}
        ctx = getattr(self.results_tab, "_query_context", None)
        if ctx:
            result_columns = list(ctx.get("result_columns", []))
            column_types = dict(ctx.get("column_types", {}))
        elif getattr(self.results_tab, "_df", None) is not None:
            df = self.results_tab._df
            result_columns = list(df.columns)
            column_types = {col: str(df[col].dtype) for col in df.columns}

        from suiteview.audit.query_object import cyberlife_query_object
        from suiteview.audit import query_object_store

        existing = query_object_store.load_object(name)
        qo = cyberlife_query_object(
            name,
            sql=sql,
            dsn=dsn,
            region=region,
            system_code=system_code,
            criteria=self._cyberlife_query_object_state(),
            result_columns=result_columns,
            column_types=column_types,
        )
        if existing is not None:
            qo.id = existing.id
            qo.created_at = existing.created_at
            qo.description = existing.description
            qo.tags = list(existing.tags)
            existing_config = dict(existing.config or {})
            dataforge_config = existing_config.get("dataforge")
            if isinstance(dataforge_config, dict):
                dataforge_config = dict(dataforge_config)
                dataforge_config["query_object_id"] = qo.id
                qo.config["query_object_id"] = qo.id
                qo.config["dataforge"] = dataforge_config
        query_object_store.save_object(qo)
        self._cyberlife_saved_object_name = name
        self.btn_save_cyberlife.setVisible(True)
        self.query_object_saved.emit(name)
        QMessageBox.information(
            self, "Query Object Saved",
            f"Cyberlife query object \"{name}\" saved successfully.")
    def _on_clear_cyberlife(self):
        """Reset only Cyberlife tabs to defaults."""
        for _key, tab in self._cyberlife_criteria_tabs():
            tab.set_state({})
        self.txt_max_count.setText("25")
        self.chk_coverage_level.setChecked(False)
        self.results_tab.clear_results()
        self.sql_tab.clear_sql()
        self.build_sql_tab.clear_sql()
        self.build_sql_results_tab.clear_results()
        self.lbl_result_count.setText("Result count:")
        self.tabs.setCurrentWidget(self.policy_tab)
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
        db = DB2Connection(region)
        dsn = db.dsn

        def work():
            t0 = time.time()
            columns, rows = db.execute_query_with_headers_isolated(sql)
            t_query = time.time() - t0
            df = pd.DataFrame([list(r) for r in rows], columns=columns)
            return columns, df, t_query

        def on_success(payload):
            columns, df, t_query = payload
            t1 = time.time()
            self.results_tab.set_results(df)
            self.results_tab.set_query_context(
                sql=sql, dsn=dsn,
                source_design="Cyberlife",
                result_columns=columns,
            )
            t_print = time.time() - t1
            self.lbl_query_time.setText(f"Query time:  {fmt_time(t_query)}")
            self.lbl_print_time.setText(f"Print time:  {fmt_time(t_print)}")
            self.lbl_total_time.setText(f"Total time:  {fmt_time(t_query + t_print)}")
            self.lbl_result_count.setText(f"Result count:   {len(df)}")
            # Switch to Results tab
            self.tabs.setCurrentWidget(self.results_tab)

        def on_error(exc):
            logger.error("Audit query failed: %s", exc)
            QMessageBox.warning(self, "Query Error", format_query_error(exc))

        run_query_async(
            owner=self,
            work=work,
            on_success=on_success,
            on_error=on_error,
            btn=self.btn_run,
            restore_text="Run\nAudit",
            bar=self.cyberlife_bottom_bar,
        )

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
                    self._create_blank_dataforge()
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
    def _create_blank_dataforge(self):
        """Create an unsaved DataForge builder without prompting."""
        display = "⚙ (new)"
        for open_name, open_group in list(self._dataforge_groups.items()):
            if not getattr(open_group, "_saved_forge_name", ""):
                discard = getattr(open_group, "discard_temporary_source_copies", None)
                if callable(discard):
                    discard()
                self._remove_dataforge_group(open_name)
        group = self._create_dataforge_group(
            display, forge_name="", saved_forge_name="")
        self._active_unpinned_forge = display
        return group
    def _on_load_saved_query(self, sq):
        """Create a DynamicQuery from a saved query and switch to it."""
        config: dict = sq.config
        name = f"▸ {sq.name}"
        # If already loaded, switch first then clean up old
        if name in self._dynamic_queries:
            self._dynamic_queries[name].focus_initial_builder_state()
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
        group.query_saved.connect(self._on_dynamic_query_saved)
        group.query_deleted.connect(self._on_query_deleted_from_group)
        group.common_tables_changed.connect(self._on_common_tables_changed)
        group.new_query_requested.connect(self._start_visual_query_object)
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
        self.btn_dataforge.setChecked(True)
        self._create_blank_dataforge()
        self._refresh_picker_forge_list()
    def _on_load_dataforge(self, forge):
        """Open a DataForge designer from the shelf click."""
        display = f"⚙ {forge.name}"
        # If already loaded, switch to it
        if display in self._dataforge_groups:
            group = self._dataforge_groups.get(display)
            if group is not None:
                self._sync_loaded_dataforge_sources(group, forge)
            self._switch_mode(display)
            self._sync_forge_picker_to_group(
                group, forge.name)
            return
        group = self._create_dataforge_group(
            display, forge_name=forge.name, saved_forge_name=forge.name)
        # Restore sources
        self._sync_loaded_dataforge_sources(group, forge)
        # Restore config
        if forge.config:
            group.set_config(forge.config)
        self._sync_forge_picker_to_group(group, forge.name)

    def _sync_loaded_dataforge_sources(self, group, forge) -> None:
        """Merge persisted DataForge sources into an already-created builder."""
        for src in forge.sources:
            qd = self._qdefinition_from_dataforge_source(src, forge.name)
            if qd is not None and qd.name not in group._sources:
                group.add_source_query(qd)

    @staticmethod
    def _qdefinition_from_dataforge_source(src, forge_name: str):
        """Restore the QDefinition-shaped source used by a saved DataForge."""
        from suiteview.audit import (
            qdef_store,
            query_object_store,
            saved_query_store as sq_store,
        )
        from suiteview.audit.query_object import (
            QueryObject,
            qdefinition_from_query_object,
        )
        from suiteview.audit.qdefinition import QDefinition

        qd = None
        if getattr(src, "query_object_id", ""):
            obj = query_object_store.load_object_by_id(src.query_object_id)
            if obj is not None:
                qd = qdefinition_from_query_object(obj)
                qd.forge_name = forge_name
                return qd
        if src.definition:
            try:
                if "kind" in src.definition:
                    obj = QueryObject.from_dict(src.definition)
                    qd = qdefinition_from_query_object(obj)
                else:
                    qd = QDefinition.from_dict(src.definition)
                qd.forge_name = forge_name
                if getattr(src, "query_object_id", ""):
                    config = dict(getattr(qd, "query_object_config", {}) or {})
                    dataforge = config.get("dataforge", {}) if isinstance(config.get("dataforge", {}), dict) else {}
                    dataforge = dict(dataforge)
                    config["query_object_id"] = src.query_object_id
                    dataforge["query_object_id"] = src.query_object_id
                    config["dataforge"] = dataforge
                    qd.query_object_config = config
                return qd
            except Exception:
                logger.exception(
                    "Failed to restore DataForge source definition: %s",
                    src.query_name,
                )

        source_names = [
            name for name in (src.effective_alias(), src.query_name)
            if name
        ]
        for name in source_names:
            qd = qdef_store.load_qdef(name, forge_name=forge_name)
            if qd is None:
                qd = qdef_store.load_qdef(name)
            if qd is not None:
                return qd
        for name in source_names:
            obj = query_object_store.load_object(name)
            if obj is not None:
                qd = qdefinition_from_query_object(obj)
                qd.forge_name = forge_name
                return qd
        for name in source_names:
            qd = sq_store.load_query(name)
            if qd is not None:
                return qd
        return None
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
        group.source_records_changed.connect(self._refresh_query_object_browser_if_open)
        group.source_records_changed.connect(
            lambda g=group: self._sync_forge_picker_to_group(g, g._saved_forge_name)
            if self._dataforge_groups.get(self._current_mode) is g else None)
        group.forge_saved.connect(self._on_forge_saved_refresh)
        group.forge_deleted.connect(self._on_forge_deleted_from_group)
        group.new_forge_requested.connect(self._on_new_dataforge)
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
    def _on_forge_saved_refresh(self, forge=None):
        """A forge was saved — refresh the picker forge list."""
        if forge is not None:
            new_display = f"⚙ {forge.name}"
            sender = self.sender()
            old_display = next(
                (name for name, group in self._dataforge_groups.items()
                 if group is sender),
                None,
            )
            if old_display and old_display != new_display:
                self._dataforge_groups[new_display] = self._dataforge_groups.pop(old_display)
                if self._current_mode == old_display:
                    self._current_mode = new_display
                if self._last_forge_mode == old_display:
                    self._last_forge_mode = new_display
                if self._active_unpinned_forge == old_display:
                    self._active_unpinned_forge = None
            if self._current_mode == new_display:
                self._sync_forge_picker_to_group(sender, forge.name)
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
        db = DB2Connection(region)
        dsn = getattr(db, "dsn", region)

        def work():
            columns, rows = db.execute_query_with_headers_isolated(sql)
            return pd.DataFrame([list(r) for r in rows], columns=columns)

        def on_success(df):
            # Add results tab if not already present
            if self._build_sql_results_tab_index < 0:
                self._build_sql_results_tab_index = self.tabs.addTab(
                    self.build_sql_results_tab, "Build SQL Results")
            self.build_sql_results_tab.set_results(df, sql=sql, dsn=dsn)
            self.tabs.setCurrentWidget(self.build_sql_results_tab)

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

    def _run_manual_sql_preview(self, sql: str):
        """Execute Manual SQL Object preview and capture output schema."""
        dsn = self.manual_sql_object_tab.current_connection()
        if not dsn:
            QMessageBox.warning(self, "Connection Required", "Select a connection before previewing SQL.")
            return
        if dsn.startswith("file:"):
            self._run_manual_sql_preview_file(dsn, sql)
            return

        def work():
            t0 = time.time()
            columns, rows = execute_odbc_query(dsn, sql)
            t_query = time.time() - t0
            df = pd.DataFrame([list(r) for r in rows], columns=columns)
            return df, t_query

        def on_success(payload):
            df, t_query = payload
            t1 = time.time()
            self.manual_sql_object_tab.set_preview_results(df, dsn=dsn)
            t_print = time.time() - t1
            footer = self.manual_sql_object_tab.bottom_bar
            footer.lbl_query_time.setText(f"Query time: {fmt_time(t_query)}")
            footer.lbl_print_time.setText(f"Print time: {fmt_time(t_print)}")
            footer.lbl_total_time.setText(f"Total time: {fmt_time(t_query + t_print)}")

        def on_error(exc):
            logger.error("Manual SQL object preview failed: %s", exc)
            QMessageBox.warning(self, "Query Error", format_query_error(exc))

        run_query_async(
            owner=self,
            work=work,
            on_success=on_success,
            on_error=on_error,
            on_busy=self.manual_sql_object_tab.set_running,
        )

    def _run_manual_sql_preview_file(self, token: str, sql: str):
        """Run a Manual SQL preview against a File Source via DuckDB."""
        from suiteview.audit import file_query_runner

        fds = file_query_runner.resolve_file_source(token[len("file:"):])
        if fds is None:
            QMessageBox.warning(self, "File Source", "This file source could not be found.")
            return

        def work():
            t0 = time.time()
            result = file_query_runner.run_sql(fds, sql, limit=1000)
            return result.dataframe, time.time() - t0

        def on_success(payload):
            df, t_query = payload
            t1 = time.time()
            self.manual_sql_object_tab.set_preview_results(df, dsn=token)
            self.manual_sql_object_tab.lbl_status.setText(
                f"Captured {len(df.columns)} columns from “{fds.name}” (DuckDB)")
            t_print = time.time() - t1
            footer = self.manual_sql_object_tab.bottom_bar
            footer.lbl_query_time.setText(f"Query time: {fmt_time(t_query)}")
            footer.lbl_print_time.setText(f"Print time: {fmt_time(t_print)}")
            footer.lbl_total_time.setText(f"Total time: {fmt_time(t_query + t_print)}")

        def on_error(exc):
            logger.error("File source SQL preview failed: %s", exc)
            QMessageBox.warning(self, "Query Error", str(exc))

        run_query_async(
            owner=self,
            work=work,
            on_success=on_success,
            on_error=on_error,
            on_busy=self.manual_sql_object_tab.set_running,
        )

    def new_query_on_file_source(self, file_source_id: str, *, mode: str = "visual"):
        """Start a new query on a saved File Source — the Object Browser's
        Data Sources dashboard "New Query" action routes here."""
        if mode == "manual":
            self._open_manual_sql_on_file_source(file_source_id)
        else:
            self._open_visual_query_on_file_source(file_source_id)

    def _open_manual_sql_on_file_source(self, file_source_id: str):
        """Open the Manual SQL editor targeted at a saved File Source (DuckDB)."""
        from suiteview.audit import file_query_runner

        fds = file_query_runner.resolve_file_source(file_source_id)
        if fds is None:
            QMessageBox.warning(self, "File Source", "This file source could not be found.")
            return
        self._manual_sql_started = True
        self.manual_sql_object_tab.new_object()
        self.manual_sql_object_tab.set_file_source(fds)
        first = fds.table_names[0] if fds.table_names else ""
        if first:
            self.manual_sql_object_tab.set_sql(f'SELECT *\nFROM "{first}"')
        self._switch_mode("__manual_sql_object__")

    def _open_visual_query_on_file_source(self, file_source_id: str):
        """Open a Visual Query designer targeted at a saved File Source (DuckDB)."""
        from suiteview.audit import file_query_runner

        fds = file_query_runner.resolve_file_source(file_source_id)
        if fds is None:
            QMessageBox.warning(self, "File Source", "This file source could not be found.")
            return
        token = f"file:{fds.id}"
        base_name = f"{fds.name} (Visual)"
        name = base_name
        suffix = 1
        while name in self._dynamic_queries:
            suffix += 1
            name = f"{base_name} {suffix}"
        # tables=[] → the source table is inferred from the fields the user drags,
        # so a multi-file source with identical columns can't silently pick the
        # wrong one. The picker still lists every member (see _bind_picker...).
        self._create_dynamic_query(name, token, [], saved_query_name="")
        self.btn_workbench.setChecked(True)
        prev = self._active_unpinned
        self._active_unpinned = name
        self._switch_mode(name)
        if prev and prev != name:
            self._remove_query(prev)

    def _bind_picker_to_file_source(self, dq):
        """Fill the SQL Assist picker from a File Source's stored schema (no ODBC)."""
        from suiteview.audit import file_query_runner
        from suiteview.audit.file_source import datasource_label

        fds = file_query_runner.resolve_file_source(dq.dsn[len("file:"):])
        if fds is None:
            self._field_picker.clear()
            return
        label = f"{fds.name} [{datasource_label(fds)}]"
        table_fields = {
            member.resolved_table_name():
                [(col.name, col.data_type) for col in fds.columns]
            for member in fds.members
        }
        self._field_picker.load_local_source(label, dq.dsn, table_fields)

    def _load_manual_sql_assist_tables(self, dsn: str = ""):
        """Load tables for the selected ODBC connection."""
        dsn = dsn or self.manual_sql_object_tab.current_connection()
        if not dsn:
            self.manual_sql_object_tab.set_assist_error("Select an ODBC connection")
            return
        try:
            conn = pyodbc.connect(f"DSN={dsn}", autocommit=True, timeout=15)
            cursor = conn.cursor()
            tables = []
            for row in cursor.tables(tableType="TABLE"):
                name = _clean_odbc_identifier(getattr(row, "table_name", ""))
                row_schema = _clean_odbc_identifier(getattr(row, "table_schem", ""))
                if name:
                    tables.append(f"{row_schema}.{name}" if row_schema else name)
            cursor.close()
            conn.close()
            self.manual_sql_object_tab.set_assist_tables(
                sorted(set(tables), key=str.lower),
                region=dsn,
            )
        except (pyodbc.Error, Exception) as exc:
            logger.exception("Manual SQL assist table load failed")
            self.manual_sql_object_tab.set_assist_error(f"Table load failed: {exc}")
    def _load_manual_sql_assist_fields(self, dsn: str, table_name: str):
        """Load columns for the selected ODBC table."""
        dsn = dsn or self.manual_sql_object_tab.current_connection()
        if not dsn:
            self.manual_sql_object_tab.set_assist_error("Select an ODBC connection")
            return
        try:
            conn = pyodbc.connect(f"DSN={dsn}", autocommit=True, timeout=15)
            cursor = conn.cursor()
            parts = [_clean_odbc_identifier(part) for part in table_name.split(".", 1)]
            if len(parts) == 2:
                schema, table = parts
            else:
                schema = None
                table = parts[0]
            indexed_names = _indexed_column_names(cursor, table, schema)
            fields = []
            for row in cursor.columns(table=table, schema=schema):
                column_name = _clean_odbc_identifier(getattr(row, "column_name", ""))
                fields.append((
                    column_name,
                    _clean_odbc_identifier(getattr(row, "type_name", "")),
                    column_name.upper() in indexed_names,
                ))
            cursor.close()
            conn.close()
            self.manual_sql_object_tab.set_assist_fields(table_name, fields)
        except (pyodbc.Error, Exception) as exc:
            logger.exception("Manual SQL assist field load failed")
            self.manual_sql_object_tab.set_assist_error(f"Field load failed: {exc}")
    def _manual_sql_odbc_connections(self) -> list[tuple[str, str]]:
        """Return saved ODBC connections plus system/user DSNs."""
        saved: list[tuple[str, str]] = []
        seen: set[str] = set()
        try:
            from suiteview.data.repositories import get_connection_repository

            for connection in get_connection_repository().get_all_connections():
                connection_string = str(connection.get("connection_string") or "")
                if not connection_string.upper().startswith("DSN="):
                    continue
                dsn = connection_string.split("=", 1)[1].strip()
                dsn_key = dsn.lower()
                if not dsn or dsn_key in seen:
                    continue
                name = str(connection.get("connection_name") or dsn)
                saved.append((f"{name} ({dsn})", dsn))
                seen.add(dsn_key)
        except Exception:
            logger.exception("Failed to load saved ODBC connections")

        try:
            for dsn in sorted(pyodbc.dataSources().keys(), key=str.lower):
                dsn_key = dsn.lower()
                if dsn_key in seen:
                    continue
                saved.append((dsn, dsn))
                seen.add(dsn_key)
        except Exception:
            logger.exception("Failed to load system ODBC data sources")
        return saved
    def _save_manual_sql_object(self, payload: dict):
        """Persist the Manual SQL editor payload as a QueryObject."""
        from suiteview.audit.query_object import manual_sql_query_object
        from suiteview.audit import query_object_store

        old_name = payload.get("original_name", "")
        new_name = payload["name"]
        if new_name != old_name and query_object_store.object_exists(new_name):
            QMessageBox.warning(
                self,
                "Name Already Exists",
                f"A Query Object named \"{new_name}\" already exists.",
            )
            return
        obj = manual_sql_query_object(
            new_name,
            sql=payload["sql"],
            dsn=payload["dsn"],
            result_columns=payload["result_columns"],
            column_types=payload["column_types"],
        )
        obj.description = payload.get("description", "")
        obj.tags = payload.get("tags", [])
        obj.config = {"sql_assist": payload.get("sql_assist", {})}
        if str(payload.get("dsn", "")).startswith("file:"):
            # File-backed Manual SQL runs through DuckDB, not ODBC.
            obj.dialect = "DUCKDB"
            obj.config["file_source_id"] = payload["dsn"][len("file:"):]
        existing_fields = payload.get("existing_fields") or []
        if existing_fields:
            old_name = payload.get("original_name", "")
            for field in existing_fields:
                if field.source == old_name:
                    field.source = new_name
            obj.fields = existing_fields
        query_object_store.save_object(obj)
        if old_name and old_name != new_name:
            query_object_store.delete_object(old_name)
        self.manual_sql_object_tab.load_object(obj)
        QMessageBox.information(
            self,
            "Query Object Saved",
            f"Manual SQL query object \"{obj.name}\" saved successfully.",
        )
    # ── PolView integration ─────────────────────────────────────
    def _on_tab_context_menu(self, pos):
        """Show a context menu to close transient SQL/object tabs."""
        tab_index = self.tabs.tabBar().tabAt(pos)
        if tab_index < 0:
            return
        widget = self.tabs.widget(tab_index)
        if widget not in (
            self.build_sql_tab,
            self.build_sql_results_tab,
        ):
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
        if hasattr(pw, 'lookup_bar'):
            lb = pw.lookup_bar
            lb.region_input.setText(region)
            lb.company_input.setText(company_code)
            lb.policy_input.setText(policy_number)
            lb._on_get_policy()
        pw.show()
        pw.raise_()
        pw.activateWindow()
        # Keep policy list panel at same Z-level as PolView
        if hasattr(pw, 'policy_list_window') and pw.policy_list_window.isVisible():
            pw.policy_list_window.raise_()