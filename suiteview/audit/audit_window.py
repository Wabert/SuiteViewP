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
from .tabs.tai_cession_tab import TaiCessionTab
from .tabs.tai_transactions_tab import TaiTransactionsTab
from .tabs.tai_reserve_tab import TaiReserveTab
from .tabs._styles import style_combo as _style_combo
from suiteview.core.db2_connection import DB2Connection
from suiteview.core.db2_constants import DEFAULT_SCHEMA, REGION_SCHEMA_MAP
from .tabs.compare_results_tab import CompareResultsTab
from .cyberlife_query import build_cyberlife_sql
from .tai_query import (build_tai_sql, run_tai_query, run_tai_compare,
                        TAI_DEFAULT_COLUMNS,
                        build_taicybertaifd_sql, run_taicybertaifd_query)
from .sql_helpers import fmt_time

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

        # ── Mode toolbar (Cyberlife / TAI) ──────────────────────────
        self._current_mode = "cyberlife"
        mode_bar = QWidget()
        mode_bar.setFixedHeight(32)
        mode_bar.setStyleSheet("QWidget { background-color: #E0E0E0; }")
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

        self.btn_cyberlife = QPushButton("Cyberlife")
        self.btn_cyberlife.setFont(QFont("Segoe UI", 9, QFont.Weight.Bold))
        self.btn_cyberlife.setFixedHeight(26)
        self.btn_cyberlife.setStyleSheet(_ACTIVE_STYLE)
        mode_layout.addWidget(self.btn_cyberlife)

        self.btn_tai = QPushButton("TAI")
        self.btn_tai.setFont(QFont("Segoe UI", 9, QFont.Weight.Bold))
        self.btn_tai.setFixedHeight(26)
        self.btn_tai.setStyleSheet(_INACTIVE_STYLE)
        mode_layout.addWidget(self.btn_tai)

        mode_layout.addStretch()
        self._active_mode_style = _ACTIVE_STYLE
        self._inactive_mode_style = _INACTIVE_STYLE

        root.addWidget(mode_bar)

        # ── Tab widget ──────────────────────────────────────────────
        self.tabs = QTabWidget()
        self.tabs.setFont(_FONT)
        self.tabs.setStyleSheet(
            "QTabWidget::pane { border: 1px solid #999; }"
            "QTabBar::tab { padding: 2px 8px; min-height: 20px; font-size: 9pt; }"
            "QTabBar::tab:selected { font-weight: bold; }"
        )

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

        root.addWidget(self.tabs, 1)  # stretch=1 so tabs fill

        # ── TAI Tab widget (hidden by default) ─────────────────────
        self.tai_tabs = QTabWidget()
        self.tai_tabs.setFont(_FONT)
        self.tai_tabs.setStyleSheet(
            "QTabWidget::pane { border: 1px solid #999; }"
            "QTabBar::tab { padding: 2px 8px; min-height: 20px; font-size: 9pt; }"
            "QTabBar::tab:selected { font-weight: bold; }"
        )

        self.tai_cession_tab = TaiCessionTab()
        self.tai_tabs.addTab(self.tai_cession_tab, "TAI_Cession")

        self.tai_transactions_tab = TaiTransactionsTab()
        self.tai_tabs.addTab(self.tai_transactions_tab, "TAICyberTAIFd")

        self.tai_reserve_tab = TaiReserveTab()
        self.tai_tabs.addTab(self.tai_reserve_tab, "TAI_Reserve")

        # TAI reuses Display, Results, SQL classes (separate instances)
        self.tai_display_tab = QWidget()  # placeholder — TAI-specific display options TBD
        self.tai_tabs.addTab(self.tai_display_tab, "Display")

        self.tai_results_tab = ResultsTab()
        self.tai_tabs.addTab(self.tai_results_tab, "Results")
        self.tai_results_tab.policy_double_clicked.connect(
            self._open_polview_tai)

        self.tai_sql_tab = SqlTab()
        self.tai_tabs.addTab(self.tai_sql_tab, "SQL")

        # Compare Results tab (hidden until a compare is run)
        self.tai_compare_tab = CompareResultsTab()
        self.tai_compare_tab.policy_double_clicked.connect(
            self._open_polview_tai)
        self._tai_compare_tab_idx = -1  # will be set when first shown

        self.tai_tabs.setVisible(False)
        root.addWidget(self.tai_tabs, 1)

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

        self.btn_profile_clear = QPushButton("Clear All")
        self.btn_profile_clear.setFont(_FONT)
        self.btn_profile_clear.setFixedHeight(22)
        self.btn_profile_clear.setStyleSheet(_BTN_STYLE)
        pb_layout.addWidget(self.btn_profile_clear)

        pb_layout.addStretch()

        # ── Cyberlife bottom bar ─────────────────────────────────────
        self.cyberlife_bottom_bar = QWidget()
        cyb_layout = QHBoxLayout(self.cyberlife_bottom_bar)
        cyb_layout.setSpacing(6)
        cyb_layout.setContentsMargins(4, 3, 4, 3)

        # Region
        self.lbl_region = QLabel("Region:")
        self.lbl_region.setFont(_FONT)
        self.cmb_region = QComboBox()
        self.cmb_region.setFont(_FONT)
        self.cmb_region.addItems(REGION_ITEMS)
        self.cmb_region.setFixedHeight(20)
        self.cmb_region.setFixedWidth(70)
        _style_combo(self.cmb_region)
        cyb_layout.addWidget(self.lbl_region)
        cyb_layout.addWidget(self.cmb_region)

        cyb_layout.addSpacing(6)

        # System Code
        self.lbl_sys = QLabel("System Code:")
        self.lbl_sys.setFont(_FONT)
        self.cmb_system = QComboBox()
        self.cmb_system.setFont(_FONT)
        self.cmb_system.addItems(SYSTEM_CODE_ITEMS)
        self.cmb_system.setFixedHeight(20)
        self.cmb_system.setFixedWidth(45)
        _style_combo(self.cmb_system)
        cyb_layout.addWidget(self.lbl_sys)
        cyb_layout.addWidget(self.cmb_system)

        cyb_layout.addSpacing(10)

        # All button + Max Count
        self.btn_all = QPushButton("All")
        self.btn_all.setFont(_FONT)
        self.btn_all.setFixedSize(36, 22)
        cyb_layout.addWidget(self.btn_all)

        self.txt_max_count = QLineEdit("25")
        self.txt_max_count.setFont(_FONT)
        self.txt_max_count.setFixedSize(40, 20)
        self.txt_max_count.setAlignment(Qt.AlignmentFlag.AlignCenter)
        cyb_layout.addWidget(self.txt_max_count)

        lbl_mc = QLabel("Max Count")
        lbl_mc.setFont(_FONT)
        cyb_layout.addWidget(lbl_mc)

        cyb_layout.addStretch()

        # Timing labels
        time_grid = QVBoxLayout()
        time_grid.setSpacing(0)
        self.lbl_query_time = QLabel("Query time:")
        self.lbl_print_time = QLabel("Print time:")
        self.lbl_total_time = QLabel("Total time:")
        for lbl in (self.lbl_query_time, self.lbl_print_time, self.lbl_total_time):
            lbl.setFont(_FONT)
            time_grid.addWidget(lbl)
        cyb_layout.addLayout(time_grid)

        cyb_layout.addStretch()

        # Result count
        self.lbl_result_count = QLabel("Result count:")
        self.lbl_result_count.setFont(_FONT)
        cyb_layout.addWidget(self.lbl_result_count)

        cyb_layout.addSpacing(12)

        # Run Audit button
        self.btn_run = QPushButton("Run\nAudit")
        self.btn_run.setFont(QFont("Segoe UI", 9, QFont.Weight.Bold))
        self.btn_run.setFixedSize(60, 36)
        self.btn_run.setStyleSheet(
            "QPushButton { background-color: #C00000; color: white; border: 1px solid #900; "
            "border-radius: 3px; }"
            "QPushButton:hover { background-color: #E00000; }"
        )
        cyb_layout.addWidget(self.btn_run)

        root.addWidget(self.cyberlife_bottom_bar)

        # ── TAI bottom bar ───────────────────────────────────────────
        self.tai_bottom_bar = QWidget()
        tai_btm_layout = QHBoxLayout(self.tai_bottom_bar)
        tai_btm_layout.setSpacing(6)
        tai_btm_layout.setContentsMargins(4, 3, 4, 3)

        # All button + Max Count (TAI)
        self.btn_all_tai = QPushButton("All")
        self.btn_all_tai.setFont(_FONT)
        self.btn_all_tai.setFixedSize(36, 22)
        tai_btm_layout.addWidget(self.btn_all_tai)

        self.txt_max_count_tai = QLineEdit("25")
        self.txt_max_count_tai.setFont(_FONT)
        self.txt_max_count_tai.setFixedSize(40, 20)
        self.txt_max_count_tai.setAlignment(Qt.AlignmentFlag.AlignCenter)
        tai_btm_layout.addWidget(self.txt_max_count_tai)

        lbl_mc_tai = QLabel("Max Count")
        lbl_mc_tai.setFont(_FONT)
        tai_btm_layout.addWidget(lbl_mc_tai)

        tai_btm_layout.addStretch()

        # Timing labels (TAI)
        time_grid_tai = QVBoxLayout()
        time_grid_tai.setSpacing(0)
        self.lbl_query_time_tai = QLabel("Query time:")
        self.lbl_print_time_tai = QLabel("Print time:")
        self.lbl_total_time_tai = QLabel("Total time:")
        for lbl in (self.lbl_query_time_tai, self.lbl_print_time_tai,
                    self.lbl_total_time_tai):
            lbl.setFont(_FONT)
            time_grid_tai.addWidget(lbl)
        tai_btm_layout.addLayout(time_grid_tai)

        tai_btm_layout.addStretch()

        # Result count (TAI)
        self.lbl_result_count_tai = QLabel("Result count:")
        self.lbl_result_count_tai.setFont(_FONT)
        tai_btm_layout.addWidget(self.lbl_result_count_tai)

        tai_btm_layout.addSpacing(12)

        # Run TAI Audit button
        self.btn_run_tai = QPushButton("Run\nAudit")
        self.btn_run_tai.setFont(QFont("Segoe UI", 9, QFont.Weight.Bold))
        self.btn_run_tai.setFixedSize(60, 36)
        self.btn_run_tai.setStyleSheet(
            "QPushButton { background-color: #C00000; color: white; border: 1px solid #900; "
            "border-radius: 3px; }"
            "QPushButton:hover { background-color: #E00000; }"
        )
        tai_btm_layout.addWidget(self.btn_run_tai)

        self.tai_bottom_bar.setVisible(False)
        root.addWidget(self.tai_bottom_bar)

        # ── Separator + Profile bar (shared) ─────────────────────────
        sep_line = QFrame()
        sep_line.setFrameShape(QFrame.Shape.HLine)
        sep_line.setStyleSheet("color: #999;")
        sep_line.setFixedHeight(1)
        root.addWidget(sep_line)

        root.addWidget(profile_bar)

        self._apply_initial_state()
        self._connect_signals()
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
        self.btn_run_tai.clicked.connect(self._run_tai_audit)
        self.btn_all_tai.clicked.connect(self._set_all_rows_tai)
        self.tai_cession_tab.compare_ready_changed.connect(self._on_compare_ready)
        self.sql_tab.move_to_build.connect(self._on_move_to_build)
        self.build_sql_tab.run_sql_requested.connect(self._run_build_sql)
        # Mode switching
        self.btn_cyberlife.clicked.connect(lambda: self._switch_mode("cyberlife"))
        self.btn_tai.clicked.connect(lambda: self._switch_mode("tai"))
        # Profile signals
        self.cmb_profile.currentIndexChanged.connect(self._on_profile_selected)
        self.btn_profile_save.clicked.connect(self._on_profile_save)
        self.btn_profile_save_as.clicked.connect(self._on_profile_save_as)
        self.btn_profile_delete.clicked.connect(self._on_profile_delete)
        self.btn_profile_clear.clicked.connect(self._on_profile_clear)
        self._update_profile_buttons()

    # ── Mode switching (Cyberlife / TAI) ─────────────────────────────

    def _switch_mode(self, mode: str):
        """Toggle between Cyberlife and TAI tab sets."""
        if mode == self._current_mode:
            return
        self._current_mode = mode

        is_tai = (mode == "tai")
        self.tabs.setVisible(not is_tai)
        self.tai_tabs.setVisible(is_tai)

        # Style the active/inactive buttons
        self.btn_cyberlife.setStyleSheet(
            self._inactive_mode_style if is_tai else self._active_mode_style)
        self.btn_tai.setStyleSheet(
            self._active_mode_style if is_tai else self._inactive_mode_style)

        # Toggle mode-specific bottom bars
        self.cyberlife_bottom_bar.setVisible(not is_tai)
        self.tai_bottom_bar.setVisible(is_tai)

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

    def _all_criteria_tabs(self):
        """Return (key, tab) pairs for all tabs that support get_state/set_state."""
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

    def _on_profile_clear(self):
        """Reset all tabs to defaults."""
        self._clear_full_state()
        self.cmb_profile.blockSignals(True)
        self.cmb_profile.setCurrentIndex(0)
        self.cmb_profile.blockSignals(False)
        self._update_profile_buttons()

    # ── Run audit ────────────────────────────────────────────────────

    def _set_all_rows(self):
        """Clear max count (fetch all rows)."""
        self.txt_max_count.setText("")

    def _set_all_rows_tai(self):
        """Clear TAI max count (fetch all rows)."""
        self.txt_max_count_tai.setText("")

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

    # ── TAI audit ────────────────────────────────────────────────────

    def _build_tai_sql(self) -> str:
        """Build TAI SQL — delegates to tai_query.build_tai_sql."""
        return build_tai_sql(
            self.tai_cession_tab,
            self.txt_max_count_tai.text().strip(),
        )

    # ── Compare button state ─────────────────────────────────────────

    _RUN_AUDIT_STYLE = (
        "QPushButton { background-color: #C00000; color: white; border: 1px solid #900; "
        "border-radius: 3px; }"
        "QPushButton:hover { background-color: #E00000; }"
    )
    _RUN_COMPARE_STYLE = (
        "QPushButton { background-color: #1565C0; color: white; border: 1px solid #0D47A1; "
        "border-radius: 3px; }"
        "QPushButton:hover { background-color: #1976D2; }"
    )

    def _on_compare_ready(self, ready: bool):
        """Switch the Run button between audit and compare modes."""
        if ready:
            self.btn_run_tai.setText("Run\nCompare")
            self.btn_run_tai.setStyleSheet(self._RUN_COMPARE_STYLE)
        else:
            self.btn_run_tai.setText("Run\nAudit")
            self.btn_run_tai.setStyleSheet(self._RUN_AUDIT_STYLE)

    def _run_tai_audit(self):
        """Execute TAI audit — routes to cession or TAICyberTAIFd based on active tab."""
        current_tab = self.tai_tabs.currentWidget()

        # TAICyberTAIFd tab
        if current_tab is self.tai_transactions_tab:
            self._run_taicybertaifd_audit()
            return

        # TAI Cession tab (or any other tab) — existing behaviour
        ct = self.tai_cession_tab
        if ct.is_compare_ready():
            self._run_tai_compare()
            return

        try:
            sql = self._build_tai_sql()
        except Exception as exc:
            logger.exception("Failed to build TAI SQL")
            QMessageBox.warning(self, "SQL Build Error", str(exc))
            return

        # Show SQL in TAI SQL tab
        self.tai_sql_tab.set_sql(sql)

        self.btn_run_tai.setEnabled(False)
        self.btn_run_tai.setText("Running...")
        self.lbl_query_time_tai.setText("Query time:")
        self.lbl_print_time_tai.setText("Print time:")
        self.lbl_total_time_tai.setText("Total time:")
        self.lbl_result_count_tai.setText("Result count:")

        from PyQt6.QtWidgets import QApplication
        QApplication.processEvents()

        try:
            df, t_query = run_tai_query(sql)

            t1 = time.time()
            self.tai_results_tab.set_results(df)
            t_print = time.time() - t1
            t_total = t_query + t_print

            self.lbl_query_time_tai.setText(f"Query time:  {fmt_time(t_query)}")
            self.lbl_print_time_tai.setText(f"Print time:  {fmt_time(t_print)}")
            self.lbl_total_time_tai.setText(f"Total time:  {fmt_time(t_total)}")
            self.lbl_result_count_tai.setText(f"Result count:   {len(df)}")

            # Switch to Results tab in TAI tab widget
            self.tai_tabs.setCurrentWidget(self.tai_results_tab)

        except Exception as exc:
            logger.exception("TAI audit query failed")
            msg = str(exc)
            if hasattr(exc, 'args') and len(exc.args) >= 2:
                msg = f"{exc.args[0]}\n\n{exc.args[1]}"
            QMessageBox.warning(self, "Query Error", msg)
        finally:
            self.btn_run_tai.setEnabled(True)
            self._on_compare_ready(self.tai_cession_tab.is_compare_ready())

    def _run_taicybertaifd_audit(self):
        """Execute a TAICyberTAIFd query and display results."""
        ct = self.tai_transactions_tab
        try:
            sql = build_taicybertaifd_sql(ct, self.txt_max_count_tai.text().strip())
        except Exception as exc:
            logger.exception("Failed to build TAICyberTAIFd SQL")
            QMessageBox.warning(self, "SQL Build Error", str(exc))
            return

        self.tai_sql_tab.set_sql(sql)

        self.btn_run_tai.setEnabled(False)
        self.btn_run_tai.setText("Running...")
        self.lbl_query_time_tai.setText("Query time:")
        self.lbl_print_time_tai.setText("Print time:")
        self.lbl_total_time_tai.setText("Total time:")
        self.lbl_result_count_tai.setText("Result count:")

        from PyQt6.QtWidgets import QApplication
        QApplication.processEvents()

        try:
            all_cols = ct.chk_all_columns.isChecked()
            df, t_query = run_taicybertaifd_query(sql, all_columns=all_cols)

            t1 = time.time()
            self.tai_results_tab.set_results(df)
            t_print = time.time() - t1
            t_total = t_query + t_print

            self.lbl_query_time_tai.setText(f"Query time:  {fmt_time(t_query)}")
            self.lbl_print_time_tai.setText(f"Print time:  {fmt_time(t_print)}")
            self.lbl_total_time_tai.setText(f"Total time:  {fmt_time(t_total)}")
            self.lbl_result_count_tai.setText(f"Result count:   {len(df)}")

            self.tai_tabs.setCurrentWidget(self.tai_results_tab)

        except Exception as exc:
            logger.exception("TAICyberTAIFd query failed")
            msg = str(exc)
            if hasattr(exc, 'args') and len(exc.args) >= 2:
                msg = f"{exc.args[0]}\n\n{exc.args[1]}"
            QMessageBox.warning(self, "Query Error", msg)
        finally:
            self.btn_run_tai.setEnabled(True)
            self.btn_run_tai.setText("Run\nAudit")

    def _run_tai_compare(self):
        """Run the month-end compare and show results in Compare Results tab."""
        ct = self.tai_cession_tab
        eom1 = ct.txt_eom1.text().strip()
        eom2 = ct.txt_eom2.text().strip()

        self.btn_run_tai.setEnabled(False)
        self.btn_run_tai.setText("Running...")
        self.lbl_query_time_tai.setText("Query time:")
        self.lbl_print_time_tai.setText("Print time:")
        self.lbl_total_time_tai.setText("Total time:")
        self.lbl_result_count_tai.setText("Result count:")

        from PyQt6.QtWidgets import QApplication
        QApplication.processEvents()

        try:
            df1_only, df2_only, t_query = run_tai_compare(ct, eom1, eom2)

            t1 = time.time()
            # Ensure Compare Results tab is visible
            if self._tai_compare_tab_idx < 0:
                self._tai_compare_tab_idx = self.tai_tabs.addTab(
                    self.tai_compare_tab, "Compare Results")
            self.tai_compare_tab.set_results(df1_only, df2_only, eom1, eom2)
            t_print = time.time() - t1
            t_total = t_query + t_print

            total_rows = len(df1_only) + len(df2_only)
            self.lbl_query_time_tai.setText(f"Query time:  {fmt_time(t_query)}")
            self.lbl_print_time_tai.setText(f"Print time:  {fmt_time(t_print)}")
            self.lbl_total_time_tai.setText(f"Total time:  {fmt_time(t_total)}")
            self.lbl_result_count_tai.setText(
                f"Result count:   {len(df1_only)} / {len(df2_only)}")

            # Show the SQL used (both queries)
            from .tai_query import build_tai_compare_sql
            sql_text = (f"-- {eom1}\n"
                        f"{build_tai_compare_sql(ct, eom1)}\n\n"
                        f"-- {eom2}\n"
                        f"{build_tai_compare_sql(ct, eom2)}")
            self.tai_sql_tab.set_sql(sql_text)

            self.tai_tabs.setCurrentWidget(self.tai_compare_tab)

        except Exception as exc:
            logger.exception("TAI compare query failed")
            msg = str(exc)
            if hasattr(exc, 'args') and len(exc.args) >= 2:
                msg = f"{exc.args[0]}\n\n{exc.args[1]}"
            QMessageBox.warning(self, "Query Error", msg)
        finally:
            self.btn_run_tai.setEnabled(True)
            self._on_compare_ready(self.tai_cession_tab.is_compare_ready())

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

    # TAI company code → CyberLife company code
    _TAI_TO_CL_COMPANY = {
        "101": "01", "104": "04", "106": "06",
        "108": "08", "130": "26", "FFL": "26",
    }

    def _open_polview_tai(self, policy_number: str, company_code: str):
        """Convert TAI company code to CyberLife and open PolView."""
        cl_code = self._TAI_TO_CL_COMPANY.get(company_code, company_code)
        self._open_polview_with_policy(policy_number, cl_code)

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
