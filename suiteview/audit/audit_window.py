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
from PyQt6.QtCore import Qt, QThread, pyqtSignal
from PyQt6.QtGui import QFont
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QTabWidget,
    QLabel, QLineEdit, QComboBox, QPushButton,
    QSizePolicy, QFrame, QMessageBox, QMenu, QInputDialog,
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
from .dynamic_group import DynamicGroup
from .field_picker_window import FieldPickerWindow
from .group_config import (list_groups, load_group, save_group,
                           delete_group, group_exists,
                           load_ui_settings, save_ui_settings)

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

        # ── Mode toolbar ─────────────────────────────────────────
        self._current_mode = "cyberlife"
        mode_bar = QWidget()
        self._mode_bar = mode_bar
        mode_bar.setFixedHeight(32)
        mode_bar.setStyleSheet(self._MODE_BAR_CYB_STYLE)
        mode_layout = QHBoxLayout(mode_bar)
        mode_layout.setContentsMargins(8, 2, 8, 2)
        mode_layout.setSpacing(6)

        _MODE_BTN = (
            "QPushButton {{ background-color: {bg}; color: {fg};"
            " border: 1px solid {border}; border-radius: 3px;"
            " padding: 2px 16px; font-size: 9pt; font-weight: bold; }}"
            "QPushButton:hover {{ background-color: {hover}; }}"
        )
        _ACTIVE_STYLE = _MODE_BTN.format(
            bg="#1E5BA8", fg="white", border="#14407A", hover="#2A6BC4")
        _INACTIVE_STYLE = _MODE_BTN.format(
            bg="#C0C0C0", fg="#333", border="#999", hover="#D0D0D0")

        # Cyberlife uses darker navy to distinguish from custom groups
        _CYBERLIFE_ACTIVE_STYLE = _MODE_BTN.format(
            bg="#0A2A5C", fg="white", border="#061D40", hover="#14407A")

        self.btn_cyberlife = QPushButton("Cyberlife")
        self.btn_cyberlife.setFont(QFont("Segoe UI", 9, QFont.Weight.Bold))
        self.btn_cyberlife.setFixedHeight(26)
        self.btn_cyberlife.setStyleSheet(_CYBERLIFE_ACTIVE_STYLE)
        mode_layout.addWidget(self.btn_cyberlife)

        # Spacer for dynamic group buttons
        self._dynamic_group_btn_layout = QHBoxLayout()
        self._dynamic_group_btn_layout.setSpacing(6)
        mode_layout.addSpacing(8)
        mode_layout.addLayout(self._dynamic_group_btn_layout)

        mode_layout.addStretch()

        # Field Picker toggle styles (used by dynamic group footer buttons)
        self._picker_btn_on_style = (
            "QPushButton { background-color: #1E5BA8; color: white;"
            " border: 1px solid #14407A; border-radius: 3px;"
            " padding: 2px 10px; font-size: 8pt; }"
            "QPushButton:hover { background-color: #2A6BC4; }"
        )
        self._picker_btn_off_style = (
            "QPushButton { background-color: #E8F0FB; color: #1E5BA8;"
            " border: 1px solid #1E5BA8; border-radius: 3px;"
            " padding: 2px 10px; font-size: 9pt; font-weight: bold; }"
            "QPushButton:hover { background-color: #C5D8F5; }"
        )

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

        self.btn_add_group = QPushButton("+ Group")
        self.btn_add_group.setFont(QFont("Segoe UI", 8))
        self.btn_add_group.setFixedHeight(24)
        self.btn_add_group.setStyleSheet(_HEADER_BTN_STYLE)
        self.btn_add_group.setToolTip("Create a new dynamic audit group")
        self.btn_add_group.clicked.connect(self._on_add_group)

        # Insert into header bar layout before window control buttons
        header_layout = self.header_bar.layout()
        insert_pos = header_layout.count() - 3  # before min/max/close
        header_layout.insertWidget(insert_pos, self.btn_registry)
        header_layout.insertWidget(insert_pos + 1, self.btn_add_group)

        # Dynamic group storage
        self._dynamic_groups: dict[str, DynamicGroup] = {}
        self._dynamic_buttons: dict[str, QPushButton] = {}
        self._active_mode_style = _ACTIVE_STYLE
        self._inactive_mode_style = _INACTIVE_STYLE
        self._cyberlife_active_style = _CYBERLIFE_ACTIVE_STYLE

        root.addWidget(mode_bar)

        # ── Main content area (tabs + bottom bars + dynamic groups) ──
        self._content_left = QWidget()
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

        # ── Profile bar ────────────────────────────────────────────
        profile_bar = QWidget()
        profile_bar.setFixedHeight(28)
        profile_bar.setStyleSheet(
            "QWidget { background-color: #E8E8E8; }"
        )
        pb_layout = QHBoxLayout(profile_bar)
        pb_layout.setContentsMargins(6, 2, 6, 2)
        pb_layout.setSpacing(6)

        lbl_profile = QLabel("Profile:")
        lbl_profile.setFont(QFont("Segoe UI", 9, QFont.Weight.Bold))
        pb_layout.addWidget(lbl_profile)

        self.cmb_profile = QComboBox()
        self.cmb_profile.setFont(_FONT)
        self.cmb_profile.setFixedHeight(22)
        self.cmb_profile.setMinimumWidth(200)
        self.cmb_profile.setMaximumWidth(300)
        _style_combo(self.cmb_profile)
        pb_layout.addWidget(self.cmb_profile)

        _BTN_STYLE = (
            "QPushButton { background-color: #1E5BA8; color: white;"
            " border: 1px solid #14407A; border-radius: 2px;"
            " padding: 1px 8px; font-size: 9pt; }"
            "QPushButton:hover { background-color: #2A6BC4; }"
            "QPushButton:disabled { background-color: #A0A0A0;"
            " border: 1px solid #888; }"
        )
        self.btn_profile_save = QPushButton("Save")
        self.btn_profile_save.setFont(_FONT)
        self.btn_profile_save.setFixedHeight(22)
        self.btn_profile_save.setStyleSheet(_BTN_STYLE)
        pb_layout.addWidget(self.btn_profile_save)

        self.btn_profile_save_as = QPushButton("Save As")
        self.btn_profile_save_as.setFont(_FONT)
        self.btn_profile_save_as.setFixedHeight(22)
        self.btn_profile_save_as.setStyleSheet(_BTN_STYLE)
        pb_layout.addWidget(self.btn_profile_save_as)

        self.btn_profile_delete = QPushButton("Delete")
        self.btn_profile_delete.setFont(_FONT)
        self.btn_profile_delete.setFixedHeight(22)
        self.btn_profile_delete.setStyleSheet(_BTN_STYLE)
        pb_layout.addWidget(self.btn_profile_delete)

        pb_layout.addStretch()

        # ── Cyberlife bottom bar ─────────────────────────────────────
        self.cyberlife_bottom_bar = QWidget()
        self.cyberlife_bottom_bar.setFixedHeight(50)
        self.cyberlife_bottom_bar.setStyleSheet(
            "QWidget { background-color: #C8D4E4; }")
        cyb_layout = QHBoxLayout(self.cyberlife_bottom_bar)
        cyb_layout.setSpacing(8)
        cyb_layout.setContentsMargins(4, 2, 4, 2)

        # 1) Tables button (far left) — darker navy for Cyberlife
        _TABLES_BTN_STYLE = (
            "QPushButton { background-color: #D6E4F4; color: #0A2A5C;"
            " border: 1px solid #14407A; border-radius: 3px;"
            " padding: 2px 10px; font-size: 9pt; font-weight: bold; }"
            "QPushButton:hover { background-color: #B8CCE4; }"
        )
        self.btn_tables_cyberlife = QPushButton("Tables")
        self.btn_tables_cyberlife.setFont(QFont("Segoe UI", 9, QFont.Weight.Bold))
        self.btn_tables_cyberlife.setFixedSize(60, 36)
        self.btn_tables_cyberlife.setStyleSheet(_TABLES_BTN_STYLE)
        self.btn_tables_cyberlife.setToolTip("View Cyberlife table information")
        cyb_layout.addWidget(self.btn_tables_cyberlife)

        # 2) Clear All button — darker navy for Cyberlife
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
        cyb_layout.addWidget(self.btn_clear_cyberlife)

        cyb_layout.addSpacing(4)

        # 3) Region + System Code stacked (brown position)
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

        cyb_layout.addLayout(region_sys_stack)

        # ── Spacer ───────────────────────────────────────────────────
        cyb_layout.addStretch()

        # 4) All + Max Count + Result Count (red position)
        cyb_count_stack = QVBoxLayout()
        cyb_count_stack.setSpacing(2)
        cyb_count_stack.setContentsMargins(0, 0, 0, 0)

        # Top row: [All] [25] Max Count
        cyb_mc_row = QHBoxLayout()
        cyb_mc_row.setSpacing(3)
        cyb_mc_row.setContentsMargins(0, 0, 0, 0)
        self.btn_all = QPushButton("All")
        self.btn_all.setFont(QFont("Segoe UI", 8))
        self.btn_all.setFixedSize(28, 18)
        cyb_mc_row.addWidget(self.btn_all)
        self.txt_max_count = QLineEdit("25")
        self.txt_max_count.setFont(QFont("Segoe UI", 8))
        self.txt_max_count.setFixedSize(36, 18)
        self.txt_max_count.setAlignment(Qt.AlignmentFlag.AlignCenter)
        cyb_mc_row.addWidget(self.txt_max_count)
        lbl_mc = QLabel("Max Count")
        lbl_mc.setFont(QFont("Segoe UI", 8))
        cyb_mc_row.addWidget(lbl_mc)
        cyb_count_stack.addLayout(cyb_mc_row)

        # Bottom row: Result count
        self.lbl_result_count = QLabel("Result count:")
        self.lbl_result_count.setFont(QFont("Segoe UI", 8))
        cyb_count_stack.addWidget(self.lbl_result_count)

        cyb_layout.addLayout(cyb_count_stack)
        cyb_layout.addSpacing(12)

        # 5) Timing labels (green position)
        time_grid = QVBoxLayout()
        time_grid.setSpacing(0)
        time_grid.setContentsMargins(0, 0, 0, 0)
        self.lbl_query_time = QLabel("Query time:")
        self.lbl_print_time = QLabel("Print time:")
        self.lbl_total_time = QLabel("Total time:")
        for lbl in (self.lbl_query_time, self.lbl_print_time, self.lbl_total_time):
            lbl.setFont(QFont("Segoe UI", 8))
            time_grid.addWidget(lbl)
        cyb_layout.addLayout(time_grid)

        cyb_layout.addSpacing(12)

        # 6) Run Audit button (orange position — far right)
        self.btn_run = QPushButton("Run\nAudit")
        self.btn_run.setFont(QFont("Segoe UI", 9, QFont.Weight.Bold))
        self.btn_run.setFixedSize(60, 36)
        self.btn_run.setStyleSheet(
            "QPushButton { background-color: #C00000; color: white; border: 1px solid #900; "
            "border-radius: 3px; }"
            "QPushButton:hover { background-color: #E00000; }"
        )
        cyb_layout.addWidget(self.btn_run)

        _left_lay.addWidget(self.cyberlife_bottom_bar)

        # ── Dynamic group container (placeholder — groups added dynamically) ──
        self._dynamic_group_container = QVBoxLayout()
        self._dynamic_group_container.setSpacing(0)
        self._dynamic_group_container.setContentsMargins(0, 0, 0, 0)
        _left_lay.addLayout(self._dynamic_group_container)

        root.addWidget(self._content_left, 1)

        # ── Field Picker dockable window (created after layout) ────
        self._field_picker = FieldPickerWindow(self)
        self._field_picker.field_requested.connect(self._on_picker_field_requested)
        self._field_picker.closed.connect(self._on_field_picker_closed)
        self._field_picker_visible = False

        # ── Separator + Profile bar (shared) ─────────────────────────
        sep_line = QFrame()
        sep_line.setFrameShape(QFrame.Shape.HLine)
        sep_line.setStyleSheet("color: #999;")
        sep_line.setFixedHeight(1)
        root.addWidget(sep_line)

        root.addWidget(profile_bar)

        self._apply_initial_state()
        self._connect_signals()
        self._load_saved_groups()
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
        # Populate profile dropdown
        self._refresh_profile_list()

    def _connect_signals(self):
        self.btn_run.clicked.connect(self._run_audit)
        self.btn_all.clicked.connect(self._set_all_rows)
        self.sql_tab.move_to_build.connect(self._on_move_to_build)
        self.build_sql_tab.run_sql_requested.connect(self._run_build_sql)
        # Mode switching
        self.btn_cyberlife.clicked.connect(lambda: self._switch_mode("cyberlife"))
        # Profile signals
        self.cmb_profile.currentIndexChanged.connect(self._on_profile_selected)
        self.btn_profile_save.clicked.connect(self._on_profile_save)
        self.btn_profile_save_as.clicked.connect(self._on_profile_save_as)
        self.btn_profile_delete.clicked.connect(self._on_profile_delete)
        self.btn_clear_cyberlife.clicked.connect(self._on_clear_cyberlife)
        self._update_profile_buttons()

    # ── Mode switching (Cyberlife / dynamic) ─────────────────────────

    # Cyberlife tab pane — darker blue top/bottom border
    _CYB_TAB_STYLE = (
        "QTabWidget::pane { border-top: 3px solid #14407A;"
        " border-bottom: 3px solid #14407A;"
        " border-left: 1px solid #999; border-right: 1px solid #999; }"
        "QTabBar::tab { padding: 2px 8px; min-height: 20px; font-size: 9pt; }"
        "QTabBar::tab:selected { font-weight: bold; }"
    )
    # Custom group tab pane — lighter blue top/bottom border
    _DYN_TAB_STYLE = (
        "QTabWidget::pane { border-top: 3px solid #1E5BA8;"
        " border-bottom: 3px solid #1E5BA8;"
        " border-left: 1px solid #999; border-right: 1px solid #999; }"
        "QTabBar::tab { padding: 2px 8px; min-height: 20px; font-size: 9pt; }"
        "QTabBar::tab:selected { font-weight: bold; }"
    )
    # Mode bar backgrounds
    _MODE_BAR_CYB_STYLE = "QWidget { background-color: #C8D4E4; }"
    _MODE_BAR_DYN_STYLE = "QWidget { background-color: #D6E4F0; }"
    _MODE_BAR_DEFAULT_STYLE = "QWidget { background-color: #E0E0E0; }"

    def _switch_mode(self, mode: str):
        """Toggle between Cyberlife and dynamic group tab sets."""
        if mode == self._current_mode:
            return
        self._current_mode = mode

        is_cyberlife = (mode == "cyberlife")
        is_dynamic = not is_cyberlife

        self.tabs.setVisible(is_cyberlife)

        # Style the active/inactive buttons
        self.btn_cyberlife.setStyleSheet(
            self._cyberlife_active_style if is_cyberlife
            else self._inactive_mode_style)

        # Toggle mode-specific bottom bars
        self.cyberlife_bottom_bar.setVisible(is_cyberlife)

        # Toggle dynamic group widgets
        for name, group in self._dynamic_groups.items():
            group.setVisible(name == mode)
        for name, btn in self._dynamic_buttons.items():
            btn.setStyleSheet(
                self._active_mode_style if name == mode
                else self._inactive_mode_style)

        # Tab pane border theming
        if is_cyberlife:
            self.tabs.setStyleSheet(self._CYB_TAB_STYLE)
        # Dynamic groups handle their own tab styling internally

        # Mode bar background
        if is_cyberlife:
            self._mode_bar.setStyleSheet(self._MODE_BAR_CYB_STYLE)
        elif is_dynamic:
            self._mode_bar.setStyleSheet(self._MODE_BAR_DYN_STYLE)
        else:
            self._mode_bar.setStyleSheet(self._MODE_BAR_DEFAULT_STYLE)

        # Hide/show field picker controls based on mode
        if is_cyberlife and self._field_picker_visible:
            self._field_picker.hide()
            self._field_picker_visible = False
            self._set_all_picker_buttons(False)
        elif is_dynamic:
            # Sync picker button states: uncheck all, check active if picker open
            for gname, g in self._dynamic_groups.items():
                if gname == mode:
                    g.btn_field_picker.blockSignals(True)
                    g.btn_field_picker.setChecked(self._field_picker_visible)
                    g.btn_field_picker.setStyleSheet(
                        self._picker_btn_on_style if self._field_picker_visible
                        else self._picker_btn_off_style)
                    g.btn_field_picker.blockSignals(False)
                else:
                    g.btn_field_picker.blockSignals(True)
                    g.btn_field_picker.setChecked(False)
                    g.btn_field_picker.setStyleSheet(self._picker_btn_off_style)
                    g.btn_field_picker.blockSignals(False)

        # Update field picker for the active dynamic group
        self._update_field_picker()

    # ── Field Picker panel ───────────────────────────────────────────

    def _active_picker_btn(self):
        """Return the field picker button for the currently active dynamic group."""
        group = self._dynamic_groups.get(self._current_mode)
        return group.btn_field_picker if group is not None else None

    def _set_all_picker_buttons(self, checked: bool):
        """Uncheck all group picker buttons and reset style."""
        for g in self._dynamic_groups.values():
            g.btn_field_picker.setChecked(checked)
            g.btn_field_picker.setStyleSheet(
                self._picker_btn_on_style if checked else self._picker_btn_off_style)

    def _toggle_field_picker(self, checked: bool):
        """Show or hide the dockable field picker window."""
        self._field_picker_visible = checked
        btn = self._active_picker_btn()
        if checked:
            if btn:
                btn.setStyleSheet(self._picker_btn_on_style)
            self._update_field_picker()
            self._field_picker.show_docked()
        else:
            if btn:
                btn.setStyleSheet(self._picker_btn_off_style)
            self._field_picker.hide()

    def _on_field_picker_closed(self):
        """Called when the user closes the field picker via its X button."""
        self._field_picker_visible = False
        self._set_all_picker_buttons(False)

    def _update_field_picker(self):
        """Populate the field picker from the active dynamic group."""
        if not self._field_picker_visible:
            return
        group = self._dynamic_groups.get(self._current_mode)
        if group is not None:
            self._field_picker.set_group(
                group.dsn, group.tables, group.display_names)
        else:
            self._field_picker.clear()

    def _on_picker_field_requested(self, table: str, column: str,
                                   type_name: str, display: str):
        """Double-click in field picker — delegate to the active dynamic group."""
        group = self._dynamic_groups.get(self._current_mode)
        if group is not None:
            group._on_field_requested(table, column, type_name, display)

    # ── Dynamic group management ─────────────────────────────────────

    def _on_add_group(self):
        """Open the Create Group dialog and add a new dynamic group."""
        from .dialogs.create_group_dialog import CreateGroupDialog
        dlg = CreateGroupDialog(self)
        if dlg.exec() != dlg.DialogCode.Accepted:
            return
        name, dsn, tables = dlg.get_result()
        if group_exists(name):
            QMessageBox.warning(self, "Group Exists",
                                f"A group named '{name}' already exists.")
            return
        self._create_dynamic_group(name, dsn, tables)
        # Save immediately
        group = self._dynamic_groups[name]
        save_group(name, group.get_config())
        # Switch to the new group
        self._switch_mode(name)

    def _create_dynamic_group(self, name: str, dsn: str, tables: list[str],
                              display_names: dict[str, str] | None = None):
        """Create a DynamicGroup widget and wire it into the UI."""
        group = DynamicGroup(name, dsn, tables, display_names, parent=self)
        group.setVisible(False)
        self._dynamic_groups[name] = group
        self._dynamic_group_container.addWidget(group)

        # Wire field picker button in the group's footer
        group.btn_field_picker.toggled.connect(self._toggle_field_picker)

        # Auto-save when group config changes
        group.config_changed.connect(
            lambda n=name: self._auto_save_group(n))

        # Create mode button
        btn = QPushButton(name)
        btn.setFont(QFont("Segoe UI", 9, QFont.Weight.Bold))
        btn.setFixedHeight(26)
        btn.setStyleSheet(self._inactive_mode_style)
        btn.clicked.connect(lambda checked, n=name: self._switch_mode(n))
        btn.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        btn.customContextMenuRequested.connect(
            lambda pos, n=name: self._on_group_btn_context_menu(n, pos))
        self._dynamic_buttons[name] = btn
        self._dynamic_group_btn_layout.addWidget(btn)

    def _on_group_btn_context_menu(self, group_name: str, pos):
        """Right-click on a dynamic group button — delete option."""
        btn = self._dynamic_buttons.get(group_name)
        if btn is None:
            return
        menu = QMenu(self)
        act_rename = menu.addAction("Rename group")
        act_delete = menu.addAction(f"Delete group '{group_name}'")
        act_save = menu.addAction("Save group")
        chosen = menu.exec(btn.mapToGlobal(pos))
        if chosen is act_rename:
            self._rename_dynamic_group(group_name)
        elif chosen is act_delete:
            reply = QMessageBox.question(
                self, "Delete Group?",
                f"Delete group '{group_name}'? This cannot be undone.",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
            if reply == QMessageBox.StandardButton.Yes:
                self._delete_dynamic_group(group_name)
        elif chosen is act_save:
            group = self._dynamic_groups.get(group_name)
            if group:
                save_group(group_name, group.get_config())

    def _delete_dynamic_group(self, name: str):
        """Remove a dynamic group from UI and disk."""
        if self._current_mode == name:
            self._switch_mode("cyberlife")

        group = self._dynamic_groups.pop(name, None)
        if group:
            self._dynamic_group_container.removeWidget(group)
            group.deleteLater()

        btn = self._dynamic_buttons.pop(name, None)
        if btn:
            self._dynamic_group_btn_layout.removeWidget(btn)
            btn.deleteLater()

        delete_group(name)

    def _rename_dynamic_group(self, old_name: str):
        """Rename a dynamic group — updates button, group, and disk file."""
        new_name, ok = QInputDialog.getText(
            self, "Rename Group", "New group name:", text=old_name)
        if not ok or not new_name.strip():
            return
        new_name = new_name.strip()
        if new_name == old_name:
            return
        if group_exists(new_name):
            QMessageBox.warning(self, "Name Taken",
                                f"A group named '{new_name}' already exists.")
            return

        group = self._dynamic_groups.pop(old_name)
        group.group_name = new_name
        group._lbl_group_name.setText(new_name)
        self._dynamic_groups[new_name] = group

        # Update button
        btn = self._dynamic_buttons.pop(old_name)
        btn.setText(new_name)
        btn.clicked.disconnect()
        btn.clicked.connect(lambda checked, n=new_name: self._switch_mode(n))
        btn.customContextMenuRequested.disconnect()
        btn.customContextMenuRequested.connect(
            lambda pos, n=new_name: self._on_group_btn_context_menu(n, pos))
        self._dynamic_buttons[new_name] = btn

        # Update auto-save connection
        group.config_changed.disconnect()
        group.config_changed.connect(
            lambda n=new_name: self._auto_save_group(n))

        # Update disk: delete old, save new
        delete_group(old_name)
        save_group(new_name, group.get_config())

        # Switch mode if currently active
        if self._current_mode == old_name:
            self._current_mode = new_name

    def _load_saved_groups(self):
        """Load all saved dynamic groups from disk on startup."""
        for name in list_groups():
            config = load_group(name)
            if config is None:
                continue
            dsn = config.get("dsn", "")
            tables = config.get("tables", [])
            display_names = config.get("display_names", {})
            self._create_dynamic_group(name, dsn, tables, display_names)
            group = self._dynamic_groups[name]
            group.set_config(config)

    def _save_all_dynamic_groups(self):
        """Save all dynamic groups to disk."""
        for name, group in self._dynamic_groups.items():
            save_group(name, group.get_config())

    def _restore_ui_settings(self):
        """Restore window-level UI settings (field picker sizes, etc.)."""
        ui = load_ui_settings()
        picker_state = ui.get("field_picker")
        if picker_state:
            self._field_picker.set_state(picker_state)

    def _auto_save_group(self, name: str):
        """Auto-save a single dynamic group to disk (called by debounce timer)."""
        group = self._dynamic_groups.get(name)
        if group:
            save_group(name, group.get_config())

    def closeEvent(self, event):
        """Save all dynamic groups on window close."""
        # Stop any pending debounce timers and flush immediately
        for group in self._dynamic_groups.values():
            group._save_timer.stop()
        self._save_all_dynamic_groups()
        # Save UI settings (field picker sizes, etc.)
        ui = load_ui_settings()
        ui["field_picker"] = self._field_picker.get_state()
        ui["field_picker_visible"] = self._field_picker_visible
        save_ui_settings(ui)
        # Hide the dockable field picker
        self._field_picker.hide()
        super().closeEvent(event)

    def moveEvent(self, event):
        super().moveEvent(event)
        if hasattr(self, "_field_picker"):
            self._field_picker.follow_parent()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if hasattr(self, "_field_picker"):
            self._field_picker.follow_parent()

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

    def _all_criteria_tabs(self):
        """Return (key, tab) pairs for all tabs that support get_state/set_state."""
        return self._cyberlife_criteria_tabs()

    def _get_full_state(self) -> dict:
        """Collect the complete form state from all tabs + bottom bar."""
        state = {
            "region": self.cmb_region.currentText(),
            "system_code": self.cmb_system.currentText(),
            "max_count": self.txt_max_count.text(),
        }
        for key, tab in self._all_criteria_tabs():
            state[key] = tab.get_state()
        return state

    def _set_full_state(self, state: dict):
        """Restore the complete form state from a saved profile."""
        # Bottom bar
        from .profile_manager import set_combo_text
        set_combo_text(self.cmb_region, state.get("region", ""))
        set_combo_text(self.cmb_system, state.get("system_code", ""))
        self.txt_max_count.setText(state.get("max_count", "25"))
        # All tabs
        for key, tab in self._all_criteria_tabs():
            tab_state = state.get(key, {})
            if tab_state:
                tab.set_state(tab_state)

    def _clear_full_state(self):
        """Reset all tabs to their default (empty) state."""
        for _key, tab in self._all_criteria_tabs():
            tab.set_state({})
        self.txt_max_count.setText("25")

    def _refresh_profile_list(self):
        """Reload the profile dropdown from disk."""
        from .profile_manager import list_profiles
        self.cmb_profile.blockSignals(True)
        current = self.cmb_profile.currentText()
        self.cmb_profile.clear()
        self.cmb_profile.addItem("(none)")
        for name in list_profiles():
            self.cmb_profile.addItem(name)
        # Restore previous selection if still present
        idx = self.cmb_profile.findText(current)
        self.cmb_profile.setCurrentIndex(max(idx, 0))
        self.cmb_profile.blockSignals(False)
        self._update_profile_buttons()

    def _update_profile_buttons(self):
        """Enable/disable Save and Delete based on current selection."""
        is_none = self.cmb_profile.currentIndex() == 0
        self.btn_profile_save.setEnabled(not is_none)
        self.btn_profile_delete.setEnabled(not is_none)

    def _on_profile_selected(self, index: int):
        """Load a profile when selected from dropdown."""
        self._update_profile_buttons()
        if index <= 0:
            return  # (none) selected
        name = self.cmb_profile.currentText()
        from .profile_manager import load_profile
        state = load_profile(name)
        if state is None:
            QMessageBox.warning(self, "Profile Error",
                                f"Could not load profile '{name}'.")
            return
        self._set_full_state(state)

    def _on_profile_save(self):
        """Overwrite the currently selected profile."""
        name = self.cmb_profile.currentText()
        if not name or name == "(none)":
            return
        from .profile_manager import save_profile
        state = self._get_full_state()
        save_profile(name, state)

    def _on_profile_save_as(self):
        """Prompt for a name and save current state as a new profile."""
        from .profile_manager import save_profile, profile_exists
        name, ok = QInputDialog.getText(
            self, "Save Profile As", "Profile name:",
            text=self.cmb_profile.currentText()
            if self.cmb_profile.currentIndex() > 0 else "")
        if not ok or not name.strip():
            return
        name = name.strip()
        if profile_exists(name):
            reply = QMessageBox.question(
                self, "Overwrite?",
                f"Profile '{name}' already exists. Overwrite?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
            if reply != QMessageBox.StandardButton.Yes:
                return
        state = self._get_full_state()
        save_profile(name, state)
        self._refresh_profile_list()
        idx = self.cmb_profile.findText(name)
        if idx >= 0:
            self.cmb_profile.blockSignals(True)
            self.cmb_profile.setCurrentIndex(idx)
            self.cmb_profile.blockSignals(False)
            self._update_profile_buttons()

    def _on_profile_delete(self):
        """Delete the currently selected profile."""
        name = self.cmb_profile.currentText()
        if not name or name == "(none)":
            return
        reply = QMessageBox.question(
            self, "Delete Profile?",
            f"Delete profile '{name}'?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        if reply != QMessageBox.StandardButton.Yes:
            return
        from .profile_manager import delete_profile
        delete_profile(name)
        self._refresh_profile_list()

    def _on_clear_cyberlife(self):
        """Reset only Cyberlife tabs to defaults."""
        for _key, tab in self._cyberlife_criteria_tabs():
            tab.set_state({})
        self.txt_max_count.setText("25")
        self.cmb_profile.blockSignals(True)
        self.cmb_profile.setCurrentIndex(0)
        self.cmb_profile.blockSignals(False)
        self._update_profile_buttons()

    # ── Run audit ────────────────────────────────────────────────────

    def _set_all_rows(self):
        """Clear max count (fetch all rows)."""
        self.txt_max_count.setText("")

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
        self.btn_run.setEnabled(False)
        self.btn_run.setText("Running...")
        self.lbl_query_time.setText("Query time:")
        self.lbl_print_time.setText("Print time:")
        self.lbl_total_time.setText("Total time:")
        self.lbl_result_count.setText("Result count:")

        from PyQt6.QtWidgets import QApplication
        QApplication.processEvents()

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
            # Surface the actual DB2 error details
            msg = str(exc)
            if hasattr(exc, 'args') and len(exc.args) >= 2:
                msg = f"{exc.args[0]}\n\n{exc.args[1]}"
            QMessageBox.warning(self, "Query Error", msg)
        finally:
            self.btn_run.setEnabled(True)
            self.btn_run.setText("Run\nAudit")

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
        self.build_sql_tab.btn_run_sql.setEnabled(False)
        self.build_sql_tab.btn_run_sql.setText("Running...")

        from PyQt6.QtWidgets import QApplication
        QApplication.processEvents()

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
        finally:
            self.build_sql_tab.btn_run_sql.setEnabled(True)
            self.build_sql_tab.btn_run_sql.setText("Run this SQL")

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
