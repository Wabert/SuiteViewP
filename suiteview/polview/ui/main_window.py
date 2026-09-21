"""
Policy Viewer UI -- Main application window (GetPolicyWindow).

All widget, tab, tree-panel, and styling classes have been extracted to:
    ui/styles.py        -- colour constants & stylesheet strings
    ui/widgets.py       -- reusable widget building-blocks
    ui/tree_panel.py    -- left-panel policy-record / rates tree
    ui/tabs/            -- one module per tab (coverages, policy, ...)

This file now contains only the top-level window orchestrator,
inheriting from FramelessWindowBase for SuiteView-consistent chrome.
"""

from typing import Optional

import logging
import subprocess
from time import perf_counter

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout,
    QTabWidget, QPushButton, QLabel, QMessageBox, QApplication,
)
from PyQt6.QtGui import QCursor
from PyQt6.QtCore import Qt, QSignalBlocker, pyqtSignal, pyqtSlot

from suiteview.ui.widgets.frameless_window import FramelessWindowBase
from suiteview.core.access_control import requires_app_access
from suiteview.core.db2_connection import DB2Connection
from suiteview.core.db2_constants import REGION_DSN_MAP
from suiteview.core.odbc_utils import is_password_error
from suiteview.core.policy_service import cache_policy_info, remove_from_cache
from ..models.policy_information import PolicyInformation

from .styles import (
    TAB_WIDGET_STYLE,
    GREEN_BG, GOLD_TEXT, GOLD_PRIMARY,
    POLVIEW_HEADER_COLORS, POLVIEW_DUPLICATE_HEADER_COLORS, POLVIEW_BORDER_COLOR,
)
from .widgets import PolicyLookupBar
from .tree_panel import PolicyRecordTreePanel
from .loading_overlay import TabLoadingOverlay
from .policy_load_controller import PolicyLoadController
from .tabs.reinstatement_tab import ReinstatementTab
from .tabs.other_data_tab import OtherDataTab
from ..services.reinstatement import is_ul_policy
from .tabs import (
    CoveragesTab, PolicyTab, TargetsAccumulatorsTab, PersonsTab,
    AdvProdValuesTab, ActivityTab, DividendsTab, LoansTab, RawTableTab,
    PolicyListWindow, PolicySupportTab, PolicyLibraryTab, ReinsuranceTab,
)

logger = logging.getLogger(__name__)

# Header-bar button style (PolView green/gold), matching the other compact
# header controls — used for the "Open in RERUN" button.
HEADER_ILLUSTRATOR_BUTTON_STYLE = """
    QPushButton {
        background: rgba(0, 0, 0, 60);
        border: 1px solid #D4A017;
        border-radius: 4px;
        min-height: 24px; max-height: 24px;
        font-size: 11px; font-weight: bold;
        color: #D4A017;
        padding: 0 12px;
    }
    QPushButton:hover {
        background-color: rgba(255, 255, 255, 0.15);
        color: #FFD700;
    }
    QPushButton:disabled {
        color: rgba(212, 160, 23, 0.4);
        border-color: rgba(212, 160, 23, 0.4);
    }
"""


def _open_odbc_manager():
    """Launch the Windows ODBC Data Source Administrator."""
    try:
        subprocess.Popen(["odbcad32.exe"])
    except OSError:
        try:
            subprocess.Popen([r"C:\Windows\System32\odbcad32.exe"])
        except OSError:
            pass


def _show_odbc_warning(parent, dsn: str, error_detail: str = ""):
    """Show a warning about ODBC connection failure with an Open ODBC Manager button."""
    msg = QMessageBox(parent)
    msg.setIcon(QMessageBox.Icon.Warning)
    msg.setWindowTitle("ODBC Authentication Failed")
    msg.setText(
        f"Authentication to {dsn} failed.\n\n"
        "Check the saved credentials for this DSN.\n\n"
        "1.  Click \"Open Manager\" below\n"
        f"2.  Double-click on {dsn} to open it\n"
        "3.  Update your password, then click Test to verify it works\n"
        "4.  Close the ODBC Manager and retry your policy lookup"
    )
    if error_detail:
        msg.setDetailedText(error_detail)

    odbc_btn = msg.addButton("Open Manager", QMessageBox.ButtonRole.ActionRole)
    msg.addButton(QMessageBox.StandardButton.Close)
    msg.exec()

    if msg.clickedButton() == odbc_btn:
        _open_odbc_manager()
        # Clear cached connections so next lookup picks up new creds
        DB2Connection.close_all()


class GetPolicyWindow(FramelessWindowBase):
    """
    Main PolView window with SuiteView frameless chrome.
    Features a professional green and gold color scheme.
    Uses PolicyInformation for centralized data access.
    """

    policy_ready = pyqtSignal()
    background_ready = pyqtSignal()

    def __init__(self, parent=None, *, enable_policy_list: bool = True,
                 initial_policy: str = "", initial_region: str = "CKPR",
                 initial_company: str = ""):
        from suiteview.core.access_control import guard_app_access
        guard_app_access("POLVIEW")
        self._enable_policy_list = enable_policy_list
        self._window_bg = GREEN_BG if enable_policy_list else "#E8F5E9"
        # Callback (policy_number, region, company_code) that opens the
        # Illustration app with the given policy. Set by the taskbar launcher;
        # when unset the header button lazily opens a standalone window.
        self._illustration_launcher = None
        self._db: Optional[DB2Connection] = None
        self._policy: Optional[PolicyInformation] = None
        self._current_policy = None
        self._current_region = None
        self._where_clause = None
        self._policy_info = {}
        self._policy_history = []
        self._child_polview_windows = []
        self._record_windows = []
        self._history_panel_visible = False
        # Cache: (policy_number, region, company) -> loaded policy context.
        self._policy_cache: dict = {}
        # Per-policy snapshots of Other Data so switching
        # between already-viewed policies restores what was there, while a brand
        # new policy starts with a clean slate.
        self._aux_tab_state: dict = {}
        self._pending_policy_tabs: set[QWidget] = set()
        self._tab_states: dict[str, str] = {}
        self._tab_payloads: dict[str, object] = {}
        self._load_token = 0
        self._requested_policy = ("", "CKPR", "")
        self._load_started = 0.0
        self._pending_annuity = False
        self.reinstatement_tab: ReinstatementTab | None = None

        # Header-bar "Open in RERUN" button (built before super().__init__
        # so FramelessWindowBase can place it via header_widgets; wired after).
        self.open_illustrator_btn = QPushButton("📈 RERUN")
        self.open_illustrator_btn.setToolTip("Open this policy in RERUN")
        self.open_illustrator_btn.setEnabled(False)
        self.open_illustrator_btn.setStyleSheet(HEADER_ILLUSTRATOR_BUTTON_STYLE)

        # Header-bar "Policy Record" button -- opens the CyberLife green-screen
        # segment viewer.  Always enabled (currently sample data).
        self.open_record_btn = QPushButton("📟 Record")
        self.open_record_btn.setToolTip(
            "View the CyberLife policy record segments (mainframe-style)"
        )
        self.open_record_btn.setStyleSheet(HEADER_ILLUSTRATOR_BUTTON_STYLE)

        super().__init__(
            title="SuiteView:  PolView",
            default_size=(1200, 780),
            min_size=(400, 400),
            parent=parent,
            header_colors=(
                POLVIEW_HEADER_COLORS
                if self._enable_policy_list
                else POLVIEW_DUPLICATE_HEADER_COLORS
            ),
            border_color=POLVIEW_BORDER_COLOR,
            header_widgets=[self.open_record_btn, self.open_illustrator_btn],
        )
        self.open_illustrator_btn.clicked.connect(self._open_in_illustrator)
        self.open_record_btn.clicked.connect(self._open_policy_record)
        self._loader = PolicyLoadController()
        self._loader.ready.connect(self._on_prepared_policy)
        self._loader.failed.connect(self._on_load_failed)
        self._loader.state_changed.connect(self._on_load_state_changed)
        self._loader.settled.connect(self._on_background_settled)
        self.destroyed.connect(self._loader.dispose)

        # Optionally pull in a policy on open (e.g. launched from the taskbar).
        if initial_policy:
            self.load_policy(initial_policy, region=initial_region,
                             company_code=initial_company)

    # == FramelessWindowBase override =====================================

    # Width of the tree panel when extended
    TREE_PANEL_WIDTH = 200

    def build_content(self) -> QWidget:
        """Build the main body widget (everything below the title bar)."""
        self._tree_visible = False

        body = QWidget()
        body.setStyleSheet(f"background-color: {self._window_bg};")
        main_layout = QVBoxLayout(body)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # Policy lookup bar
        self.lookup_bar = PolicyLookupBar()
        self.lookup_bar.policy_requested.connect(self._on_get_policy)  # (policy, region, company)
        self.lookup_bar.company_chosen.connect(self._on_get_policy)    # (policy, region, company)
        if self._enable_policy_list:
            # Add "☰ List" toggle button to the lookup bar, right after Get button
            self.list_toggle_btn = QPushButton("☰ List")
            self.list_toggle_btn.setCheckable(True)
            self.list_toggle_btn.setToolTip("Toggle Policy List panel")
            self.list_toggle_btn.setStyleSheet("""
                QPushButton {
                    background: transparent;
                    border: 1px solid #D4A017;
                    border-radius: 3px;
                    min-width: 56px; max-width: 56px;
                    min-height: 24px; max-height: 24px;
                    font-size: 11px; font-weight: bold;
                    color: #D4A017;
                    padding: 0 6px;
                }
                QPushButton:hover {
                    background-color: rgba(255, 255, 255, 0.15);
                    color: #FFD700;
                }
                QPushButton:checked {
                    background-color: rgba(212, 160, 23, 0.3);
                    color: #FFD700;
                }
            """)
            self.list_toggle_btn.clicked.connect(self._toggle_policy_list)
            self.lookup_bar.layout().addWidget(self.list_toggle_btn)
        main_layout.addWidget(self.lookup_bar)

        # Main content area
        content_widget = QWidget()
        content_widget.setStyleSheet(f"background-color: {self._window_bg};")
        content_layout = QHBoxLayout(content_widget)
        content_layout.setContentsMargins(0, 0, 0, 0)
        content_layout.setSpacing(0)

        # Tree panel (hidden initially, shown when toggled)
        self.records_tree = PolicyRecordTreePanel()
        self.records_tree.table_selected.connect(self._on_table_selected)
        self.records_tree.rate_selected.connect(self._on_rate_selected)
        self.records_tree.setFixedWidth(self.TREE_PANEL_WIDTH)
        self.records_tree.setVisible(False)
        content_layout.addWidget(self.records_tree)

        # Tabs (main content, always visible)
        tabs_container = QWidget()
        tabs_container.setStyleSheet(f"background-color: {self._window_bg};")
        tabs_layout = QVBoxLayout(tabs_container)
        tabs_layout.setContentsMargins(10, 10, 10, 10)
        tabs_layout.setSpacing(10)

        self.tabs = QTabWidget()
        self.tabs.setStyleSheet(TAB_WIDGET_STYLE)

        self.coverages_tab = CoveragesTab(self.tabs)
        self.policy_tab = PolicyTab(self.tabs)
        self.targets_tab = TargetsAccumulatorsTab(self.tabs)
        self.persons_tab = PersonsTab(self.tabs)
        self.dividends_tab = DividendsTab(self.tabs)
        self.advprod_tab = AdvProdValuesTab(self.tabs)
        self.activity_tab = ActivityTab(self.tabs)
        self.loans_tab = LoansTab(self.tabs)
        self.reinsurance_tab = ReinsuranceTab(self.tabs)
        self.raw_table_tab = RawTableTab(self.tabs)

        self.policy_support_tab = PolicySupportTab(self.tabs)
        self.policy_library_tab = PolicyLibraryTab(self.tabs)
        self.other_data_tab = OtherDataTab(self.tabs)

        self.tabs.addTab(self.coverages_tab, "Coverages")
        self.tabs.addTab(self.policy_tab, "Policy")
        self.tabs.addTab(self.targets_tab, "Targets && Accumulators")
        self.tabs.addTab(self.persons_tab, "Persons")
        # AdvProdValues is added for advanced products when a policy is loaded.
        self.tabs.addTab(self.activity_tab, "Activity")
        self.tabs.addTab(self.policy_support_tab, "Policy Support")
        self.tabs.addTab(self.other_data_tab, "Other Data")
        self.tabs.addTab(self.raw_table_tab, "Raw Table")

        for optional_tab in (
            self.dividends_tab,
            self.advprod_tab,
            self.loans_tab,
            self.reinsurance_tab,
            self.policy_library_tab,
        ):
            optional_tab.hide()

        self.policy_support_tab.policy_library_requested.connect(self._show_policy_library_tab)
        self.policy_support_tab.reinstatement_requested.connect(self._show_reinstatement_tab)
        self.coverages_tab.annuity_rider_requested.connect(self._show_annuity_rider_tab)
        self._stage_tabs = {
            "coverages": (self.coverages_tab, "Coverages"),
            "policy": (self.policy_tab, "Policy"),
            "targets": (self.targets_tab, "Targets && Accumulators"),
            "persons": (self.persons_tab, "Persons"),
            "dividends": (self.dividends_tab, "Dividends"),
            "loans": (self.loans_tab, "Loans"),
            "advprod": (self.advprod_tab, "AdvProdValues"),
            "reinsurance": (self.reinsurance_tab, "Reinsurance"),
            "activity": (self.activity_tab, "Activity"),
            "support": (self.policy_support_tab, "Policy Support"),
            "other": (self.other_data_tab, "Other Data"),
            "raw": (self.raw_table_tab, "Raw Table"),
        }
        self._load_overlays = {}
        for stage, (tab, _title) in self._stage_tabs.items():
            overlay = TabLoadingOverlay(tab, stage)
            overlay.retry_requested.connect(self._retry_policy_tab)
            self._load_overlays[stage] = overlay
        self.tabs.currentChanged.connect(self._on_policy_tab_changed)

        tabs_layout.addWidget(self.tabs)

        # Tree toggle button — properly laid out at bottom-left of tabs area
        tree_btn_row = QHBoxLayout()
        tree_btn_row.setContentsMargins(0, 0, 0, 0)
        self._tree_toggle_btn = QPushButton("+")
        self._tree_toggle_btn.setToolTip("Show/hide Tables & Rates panel")
        self._tree_toggle_btn.setCheckable(True)
        self._tree_toggle_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._tree_toggle_btn.setStyleSheet("""
            QPushButton {
                background: transparent;
                border: 1px solid #D4A017;
                border-radius: 3px;
                min-width: 28px; max-width: 28px;
                min-height: 24px; max-height: 24px;
                font-size: 15px; font-weight: bold;
                color: #D4A017;
                padding: 0px;
            }
            QPushButton:hover {
                background-color: rgba(255, 255, 255, 0.15);
                color: #FFD700;
            }
            QPushButton:checked {
                background-color: rgba(212, 160, 23, 0.3);
                color: #FFD700;
            }
        """)
        self._tree_toggle_btn.clicked.connect(self._toggle_tree_panel)
        tree_btn_row.addWidget(self._tree_toggle_btn)
        tree_btn_row.addStretch(1)
        tabs_layout.addLayout(tree_btn_row)

        content_layout.addWidget(tabs_container, 1)

        main_layout.addWidget(content_widget, 1)

        # Bottom bar: status label + dimension label
        bottom_bar = QWidget()
        bottom_top = "#0A3D0A" if self._enable_policy_list else "#2E7D32"
        bottom_bot = "#2E7D32" if self._enable_policy_list else "#66BB6A"
        bottom_bar.setStyleSheet(f"""
            background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                stop:0 {bottom_top}, stop:1 {bottom_bot});
            border-top: 2px solid #D4A017;
        """)
        bottom_layout = QHBoxLayout(bottom_bar)
        bottom_layout.setContentsMargins(8, 2, 8, 2)
        bottom_layout.setSpacing(6)

        # Status label
        self._status_label = QLabel("Ready - Enter a policy number to begin")
        self._status_label.setStyleSheet(f"""
            background: transparent;
            color: {GOLD_TEXT};
            font-size: 11px;
            font-weight: bold;
            padding: 2px 4px;
        """)
        bottom_layout.addWidget(self._status_label, 1)

        # Window dimension label (bottom-right)
        self._dim_label = QLabel("")
        self._dim_label.setStyleSheet(f"""
            background: transparent;
            color: {GOLD_PRIMARY};
            font-size: 10px;
            padding: 2px 4px;
        """)
        self._dim_label.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        bottom_layout.addWidget(self._dim_label)

        main_layout.addWidget(bottom_bar)

        if self._enable_policy_list:
            self._create_policy_list_window()

        return body

    def _toggle_tree_panel(self):
        """Toggle the tree panel — extends/shrinks window to the left.

        The tabs container (and the + button inside it) stay at the
        same screen position because the window's left edge moves by
        exactly the tree panel width.
        """
        geo = self.geometry()
        tree_w = self.TREE_PANEL_WIDTH

        if self._tree_visible:
            # Hide tree — shrink window from the left
            self.records_tree.setVisible(False)
            self._tree_visible = False
            self._tree_toggle_btn.setText("+")
            self._tree_toggle_btn.setChecked(False)
            self._tree_toggle_btn.setToolTip("Show Tables & Rates panel")
            self.setGeometry(geo.x() + tree_w, geo.y(),
                             geo.width() - tree_w, geo.height())
        else:
            # Show tree — extend window to the left
            self.records_tree.setVisible(True)
            self._tree_visible = True
            self._tree_toggle_btn.setText("−")
            self._tree_toggle_btn.setChecked(True)
            self._tree_toggle_btn.setToolTip("Hide Tables & Rates panel")
            self.setGeometry(geo.x() - tree_w, geo.y(),
                             geo.width() + tree_w, geo.height())

    def _create_policy_list_window(self):
        self.policy_list_window = PolicyListWindow(self)
        self.policy_list_window.policy_selected.connect(
            self._on_policy_selected_from_list
        )
        self.policy_list_window.policy_open_requested.connect(
            self._open_policy_in_new_window
        )
        self.policy_list_window.policy_removed.connect(
            self._on_policy_removed_from_list
        )
        self.policy_list_window.all_policies_removed.connect(
            self._on_all_policies_removed
        )

    # == Status helpers (replaces QStatusBar .showMessage) =================

    def _show_status(self, msg: str):
        self._status_label.setText(msg)

    # == Policy List helpers ===============================================

    def _toggle_policy_list(self):
        if not self._enable_policy_list:
            return
        self._history_panel_visible = not self._history_panel_visible
        if self._history_panel_visible:
            self.policy_list_window.show_panel()
        else:
            self.policy_list_window.hide()
        if hasattr(self, 'list_toggle_btn'):
            self.list_toggle_btn.setChecked(self._history_panel_visible)

    def _on_policy_selected_from_list(self, region: str, company: str, policy: str):
        was_hidden = not self.isVisible()

        if self._is_current_policy(region, company, policy):
            self._show_status(f"Policy {policy} ({company}) is already loaded")
            if was_hidden:
                self.show()
                self._history_panel_visible = True
                if hasattr(self, "policy_list_window"):
                    self.policy_list_window.show_panel()
                if hasattr(self, "list_toggle_btn"):
                    self.list_toggle_btn.setChecked(True)
            return

        self.lookup_bar.region_input.setText(region)
        self.lookup_bar.company_input.setText(company)
        self.lookup_bar.policy_input.setText(policy)
        self.lookup_bar._on_get_policy()
        if was_hidden:
            self.show()
            self._history_panel_visible = True
            if hasattr(self, "policy_list_window"):
                self.policy_list_window.show_panel()
            if hasattr(self, "list_toggle_btn"):
                self.list_toggle_btn.setChecked(True)

    def _is_current_policy(self, region: str, company: str, policy: str) -> bool:
        if not self._policy or not self._policy.exists:
            return False
        current_company = str(self._policy_info.get("CompanyCode", "")).strip()
        return (
            str(self._current_region or "").strip().upper() == str(region or "").strip().upper()
            and str(self._current_policy or "").strip().upper() == str(policy or "").strip().upper()
            and current_company.upper() == str(company or "").strip().upper()
        )

    @requires_app_access("POLVIEW")
    def _open_policy_in_new_window(self, region: str, company: str, policy: str):
        window = GetPolicyWindow(enable_policy_list=False)
        self._child_polview_windows.append(window)
        window.destroyed.connect(
            lambda _=None, w=window: self._forget_child_polview_window(w)
        )
        window.lookup_bar.region_input.setText(region)
        window.lookup_bar.company_input.setText(company)
        window.lookup_bar.policy_input.setText(policy)
        window.lookup_bar._on_get_policy()
        window.show()
        window.raise_()
        window.activateWindow()

    def _forget_child_polview_window(self, window):
        if window in self._child_polview_windows:
            self._child_polview_windows.remove(window)

    def _add_policy_to_history(self, region: str, company: str, policy: str):
        if self._enable_policy_list and hasattr(self, "policy_list_window"):
            self.policy_list_window.add_policy(region, company, policy)

    def has_policy_loaded(self, policy_number: str) -> bool:
        """Return True if *policy_number* is already in the policy list history.

        Used by the taskbar so pressing the [P] button only re-loads a typed
        policy when it's new; otherwise PolView stays on whatever policy was
        last shown.
        """
        pn = (policy_number or "").strip()
        if not pn:
            return False
        if self._enable_policy_list and hasattr(self, "policy_list_window"):
            return self.policy_list_window.has_policy(pn)
        return (self._current_policy or "").strip().upper() == pn.upper()

    def _on_policy_removed_from_list(self, policy_number: str, region: str):
        """Evict all cache entries for this policy+region (any company)."""
        keys_to_remove = [
            k for k in self._policy_cache
            if k[0] == policy_number and k[1] == region
        ]
        for k in keys_to_remove:
            remove_from_cache(
                k[0], region=k[1], company_code=k[2],
                system_code=self._policy_cache[k]["policy"].system_code,
            )
            del self._policy_cache[k]

    def _on_all_policies_removed(self):
        """Evict all policies from the cache."""
        for policy_number, region, _company in list(self._policy_cache):
            self._on_policy_removed_from_list(policy_number, region)

    # == Window events =====================================================

    def moveEvent(self, event):
        super().moveEvent(event)
        if hasattr(self, "policy_list_window"):
            self.policy_list_window.follow_parent()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if hasattr(self, "policy_list_window"):
            self.policy_list_window.follow_parent()
        # Update dimension label
        if hasattr(self, "_dim_label"):
            s = self.size()
            self._dim_label.setText(f"{s.width()} × {s.height()}")

    def changeEvent(self, event):
        super().changeEvent(event)
        if not hasattr(self, "policy_list_window"):
            return
        if event.type() == event.Type.WindowStateChange:
            if self.policy_list_window.is_docked:
                if self.isMinimized():
                    self.policy_list_window.hide()
                elif self._history_panel_visible:
                    self.policy_list_window.show_docked()
        elif event.type() == event.Type.ActivationChange and self.isActiveWindow():
            if self.policy_list_window.isVisible() and self.policy_list_window.is_docked:
                self.policy_list_window.raise_()

    def closeEvent(self, event):
        if (
            self._enable_policy_list
            and hasattr(self, "policy_list_window")
            and self.policy_list_window.isVisible()
        ):
            if self.policy_list_window.is_docked:
                self.policy_list_window.detach()
            self._history_panel_visible = True
            if hasattr(self, "list_toggle_btn"):
                self.list_toggle_btn.setChecked(True)
            self.policy_list_window.show()
            self.policy_list_window.raise_()
        if self._db:
            self._db.close()
            self._db = None
        event.accept()

    # == Policy Support tab =================================================

    def _show_policy_support_tab(self):
        """Show the always-visible Policy Support tab."""
        self.tabs.setCurrentWidget(self.policy_support_tab)
        self._load_policy_tab(self.policy_support_tab)
        self._show_status("Policy Support tab opened")

    def _show_policy_library_tab(self):
        """Show the searchable Policy Library tab."""
        library_idx = self.tabs.indexOf(self.policy_library_tab)
        if library_idx < 0:
            raw_idx = self.tabs.indexOf(self.raw_table_tab)
            if raw_idx >= 0:
                self.tabs.insertTab(raw_idx, self.policy_library_tab, "Policy Library")
            else:
                self.tabs.addTab(self.policy_library_tab, "Policy Library")

        self.policy_library_tab.refresh()
        self.tabs.setCurrentWidget(self.policy_library_tab)
        self._show_status("Policy Library tab opened")

    def _show_reinstatement_tab(self):
        if self._policy is None or not self._policy.exists:
            QMessageBox.information(self, "UL Reinstatement", "Please load a policy first.")
            return
        if not is_ul_policy(self._policy):
            QMessageBox.information(
                self, "UL Reinstatement",
                "Currently reinstatement quotes are only available for ULs",
            )
            return
        if self.reinstatement_tab is None:
            self.reinstatement_tab = ReinstatementTab(self.tabs)
        self._insert_aux_tab(self.reinstatement_tab, "Reinstatement")
        self.tabs.setCurrentWidget(self.reinstatement_tab)
        self.reinstatement_tab.load_policy(self._policy)
        self._show_status("Reinstatement tab opened")

    def _clear_reinstatement_tab(self):
        if self.reinstatement_tab is not None:
            index = self.tabs.indexOf(self.reinstatement_tab)
            if index >= 0:
                self.tabs.removeTab(index)
            self.reinstatement_tab.hide()
            self.reinstatement_tab.clear()

    def _insert_aux_tab(self, tab: QWidget, title: str):
        """Insert an optional database-backed tab just before Raw Table."""
        if self.tabs.indexOf(tab) >= 0:
            return
        raw_idx = self.tabs.indexOf(self.raw_table_tab)
        if raw_idx >= 0:
            self.tabs.insertTab(raw_idx, tab, title)
        else:
            self.tabs.addTab(tab, title)

    # -- Per-policy Other Data state ------------------------------------

    def _current_aux_key(self):
        """Cache key for the currently loaded policy, or None if none loaded."""
        if not self._current_policy:
            return None
        company = (self._policy_info or {}).get("CompanyCode", "")
        return (self._current_policy, self._current_region, company)

    def _save_current_aux_state(self):
        """Snapshot Other Data for the outgoing policy."""
        key = self._current_aux_key()
        if key is None:
            return
        self._aux_tab_state[key] = self.other_data_tab.export_state()

    def _reset_aux_tabs(self, key=None):
        """Clear Other Data and bind the newly loaded policy without querying."""
        self.other_data_tab.reset(self._policy)
        if key is not None:
            self._aux_tab_state.pop(key, None)

    def _restore_aux_tabs(self, key):
        """Restore Other Data for a previously viewed policy without querying."""
        snapshot = self._aux_tab_state.get(key) or {}
        self.other_data_tab.restore_state(self._policy, snapshot)

    def _show_annuity_rider_tab(self, coverage=None):
        """Focus the embedded Annuity Rider section for eligible rider coverage."""
        if not self._policy or not self._policy.exists:
            return

        if coverage is not None:
            plancode = str(getattr(coverage, "plancode", "")).strip().upper()
            if plancode != "0699830R":
                return

        self.tabs.setCurrentWidget(self.policy_support_tab)
        if not self._load_policy_tab(self.policy_support_tab):
            self._pending_annuity = True
            return
        self.policy_support_tab.show_annuity_rider()
        self.tabs.setCurrentWidget(self.policy_support_tab)
        self._show_status("Annuity Rider opened")

    # == Policy loading ====================================================

    def load_policy(self, policy_number: str, region: str = "CKPR",
                    company_code: str = ""):
        """Load *policy_number* through the same path the Get button uses.

        Public entry point reused by the taskbar policy launcher — drives the
        shared PolicyLookupBar so the load is identical to a user typing the
        policy and clicking Get.
        """
        policy_number = (policy_number or "").strip()
        if not policy_number:
            return
        self.lookup_bar.region_input.setText(region or "CKPR")
        self.lookup_bar.company_input.setText(company_code or "")
        self.lookup_bar.policy_input.setText(policy_number)
        self.lookup_bar._on_get_policy()

    def set_illustration_launcher(self, launcher):
        """Register a callback ``launcher(policy, region, company)`` used by the
        header "Open in RERUN" button. The taskbar sets this so the shared RERUN
        window is reused; when unset the button opens a standalone RERUN window."""
        self._illustration_launcher = launcher

    @requires_app_access("RERUN")
    def _open_in_illustrator(self, checked=False):
        """Open the currently-loaded policy in RERUN."""
        if not self._current_policy:
            return
        region = self._current_region or "CKPR"
        company = str((self._policy_info or {}).get("CompanyCode", "") or "")
        if self._illustration_launcher is not None:
            self._illustration_launcher(self._current_policy, region, company)
            return
        # Standalone fallback: open our own RERUN window.
        from suiteview.illustration.ui.main_window import IllustrationWindow
        self._illustrator_window = IllustrationWindow(
            initial_policy=self._current_policy,
            initial_region=region,
            initial_company=company,
        )
        self._illustrator_window.show()

    def _open_policy_record(self):
        """Open the CyberLife policy-record segment viewer (green-screen)."""
        from .policy_record_viewer import PolicyRecordViewerWindow
        company = str((self._policy_info or {}).get("CompanyCode", "") or "")
        window = PolicyRecordViewerWindow(
            policy_number=self._current_policy or "",
            region=self._current_region or "CKPR",
            company_code=company,
        )
        window.destroyed.connect(
            lambda *_: self._record_windows.remove(window)
            if window in self._record_windows else None
        )
        self._record_windows.append(window)
        window.show()

    def _on_get_policy(self, policy_number: str, region: str, company_code: str = ""):
        """Queue lookup and Coverages; return to the event loop without DB work."""
        policy_number = policy_number.strip().upper()
        region = region.strip().upper()
        company_code = company_code.strip().upper()
        self.lookup_bar.hide_company_chooser()
        self._save_current_aux_state()
        self._requested_policy = (policy_number, region, company_code)
        cached = self._policy_cache.get(self._requested_policy) if company_code else None
        seed = cached["policy"].detached_copy() if cached else None
        self._policy = None
        self._current_policy = None
        self._current_region = None
        self._policy_info = {}
        self._where_clause = None
        self._tab_payloads.clear()
        self._pending_annuity = False
        self.open_illustrator_btn.setEnabled(False)
        self.open_record_btn.setEnabled(False)
        self._tree_toggle_btn.setEnabled(False)
        self.records_tree.setEnabled(False)
        self._clear_reinstatement_tab()
        self._pending_policy_tabs = {tab for tab, _ in self._stage_tabs.values()}
        for stage in self._stage_tabs:
            self._set_tab_state(stage, "queued")
        self._load_started = perf_counter()
        self._show_status(f"Loading policy {policy_number} from {region}...")
        self._load_token = self._loader.start(
            policy_number, region, company_code, seed=seed,
        )

    @pyqtSlot(int, str, object)
    def _on_prepared_policy(self, token: int, stage: str, prepared):
        if token != self._load_token:
            return
        try:
            self._apply_prepared_policy(token, stage, prepared)
        except Exception as exc:
            logger.exception("Could not apply PolView %s result", stage)
            self._on_load_failed(token, stage, str(exc))

    def _apply_prepared_policy(self, token: int, stage: str, prepared):
        policy = prepared.policy
        if stage == "coverages":
            number, region, _company = self._requested_policy
            if policy.available_companies:
                self.lookup_bar.show_company_chooser(
                    policy.available_companies, number, region,
                )
                self._show_initial_notice("Select a company above to finish loading this policy.")
                return
            if not policy.exists:
                self._on_load_failed(token, stage, policy.last_error or "Policy not found.")
                return
            self._policy = policy
            self._current_policy = policy.policy_number
            self._current_region = policy.region
            self._policy_info = {
                "PolicyID": policy.policy_id, "PolicyNumber": policy.policy_number,
                "CompanyCode": policy.company_code, "SystemCode": policy.system_code,
                "Region": policy.region,
            }
            self._where_clause = (
                f"CK_SYS_CD = '{policy.system_code}' "
                f"AND TCH_POL_ID = '{policy.policy_id}' "
                f"AND CK_CMP_CD = '{policy.company_code}'"
            )
            store_key = self._current_aux_key()
            was_viewed = store_key in self._policy_cache
            self._policy_cache[store_key] = {
                "policy": policy,
                "policy_info": dict(self._policy_info),
                "where_clause": self._where_clause,
            }
            cache_policy_info(policy)
            self._db = DB2Connection(policy.region)
            self._add_policy_to_history(policy.region, policy.company_code, policy.policy_number)
            self.lookup_bar.set_policy_display(
                policy.company_code, policy.policy_number, policy.region,
                is_pending=policy.system_code == "P",
            )
            self.records_tree.reset_for_new_policy()
            self.records_tree.store_connection_info(
                self._db, self._where_clause,
                policy_id=policy.policy_id, company_code=policy.company_code,
            )
            self.records_tree.enable_rates_tab(policy)
            with policy.cached_reads_only():
                self.records_tree.show_rates_tab()
            self._prepare_policy_tabs()
            if was_viewed:
                self._restore_aux_tabs(store_key)
            else:
                self._reset_aux_tabs(store_key)
            self.raw_table_tab.clear()
            for key in ("other", "raw"):
                self._set_tab_state(key, "ready")
                self._pending_policy_tabs.discard(self._stage_tabs[key][0])
                self._load_overlays[key].hide()
            self.open_illustrator_btn.setEnabled(True)
            self.open_record_btn.setEnabled(True)
            self._tree_toggle_btn.setEnabled(True)
            self.records_tree.setEnabled(True)
            self._set_tab_state("coverages", "ready")
            coverages_ok = self._load_policy_tab(self.coverages_tab)
            self._on_policy_tab_changed(self.tabs.currentIndex())
            if not coverages_ok:
                return
            elapsed = perf_counter() - self._load_started
            logger.info("PolView Coverages ready in %.3fs; details loading asynchronously", elapsed)
            self._show_status(
                f"{policy.policy_number} ({policy.company_code}) ready in {elapsed:.1f}s"
                " - loading details in background"
            )
            self.policy_ready.emit()
            return
        if self._policy is None:
            return
        self._policy.merge_prefetched(policy)
        self._tab_payloads[stage] = prepared.payload
        tab, _title = self._stage_tabs[stage]
        if not prepared.available:
            with QSignalBlocker(self.tabs):
                if self.tabs.currentWidget() is tab:
                    self.tabs.setCurrentWidget(self.coverages_tab)
                index = self.tabs.indexOf(tab)
                if index >= 0:
                    self.tabs.removeTab(index)
                tab.hide()
            self._pending_policy_tabs.discard(tab)
        self._set_tab_state(stage, "ready")
        if prepared.available and self.tabs.currentWidget() is tab:
            self._load_policy_tab(tab)

    def _prepare_policy_tabs(self) -> bool:
        """No data queries: optional tabs remain pending until their worker result."""
        with QSignalBlocker(self.tabs):
            self._clear_reinstatement_tab()
        if not self._policy or not self._policy.exists:
            return False
        selected = self.tabs.currentWidget()
        with QSignalBlocker(self.tabs):
            for tab in (self.dividends_tab, self.advprod_tab,
                        self.loans_tab, self.reinsurance_tab):
                index = self.tabs.indexOf(tab)
                if index >= 0:
                    self.tabs.removeTab(index)
                tab.hide()
            self.tabs.insertTab(4, self.dividends_tab, "Dividends")
            if self._policy.is_advanced_product:
                self.tabs.insertTab(5, self.advprod_tab, "AdvProdValues")
            self.tabs.insertTab(
                self.tabs.indexOf(self.activity_tab), self.loans_tab, "Loans",
            )
            self.tabs.insertTab(
                self.tabs.indexOf(self.activity_tab), self.reinsurance_tab, "Reinsurance",
            )
            self.tabs.setCurrentWidget(
                selected if self.tabs.indexOf(selected) >= 0 else self.coverages_tab,
            )
        for stage in self._stage_tabs:
            self._set_tab_state(stage, self._tab_states.get(stage, "queued"))
        return True

    @pyqtSlot(int)
    def _on_policy_tab_changed(self, _index: int):
        self._load_policy_tab(self.tabs.currentWidget())

    def _load_policy_tab(self, tab: QWidget) -> bool:
        stage = next((key for key, (page, _) in self._stage_tabs.items() if page is tab), None)
        if stage is None:
            return True
        if tab not in self._pending_policy_tabs:
            return True
        if self._tab_states.get(stage) != "ready" or self._policy is None:
            if hasattr(self, "_loader"):
                self._loader.prioritize(stage)
            return False
        title = self.tabs.tabText(self.tabs.indexOf(tab)).replace("&&", "&")
        started = perf_counter()
        try:
            self._load_overlays[stage].release_controls()
            if stage == "support":
                # File browsing/GLP tools are explicit actions, never auto-prefetched.
                tab.load_data_from_policy(self._policy)
                if self._pending_annuity:
                    self._pending_annuity = False
                    tab.show_annuity_rider()
            else:
                with self._policy.cached_reads_only():
                    if stage == "policy":
                        tab.load_data_from_policy(self._policy, self._policy_info)
                    elif stage in ("advprod", "reinsurance"):
                        tab.load_data_from_policy(self._policy, self._tab_payloads[stage])
                    else:
                        tab.load_data_from_policy(self._policy)
            self._pending_policy_tabs.discard(tab)
            self._load_overlays[stage].hide()
            elapsed = perf_counter() - started
            logger.info("PolView tab %s rendered in %.3fs", title, elapsed)
            return True
        except Exception as exc:
            logger.exception("Failed to render PolView tab %s", title)
            self._on_load_failed(self._load_token, stage, str(exc))
            return False

    def _set_tab_state(self, stage: str, state: str, error: str = ""):
        self._tab_states[stage] = state
        tab, title = self._stage_tabs[stage]
        index = self.tabs.indexOf(tab)
        if index >= 0:
            suffix = "..." if state in ("queued", "loading") else " !" if state == "failed" else ""
            self.tabs.setTabText(index, title + suffix)
            self.tabs.setTabToolTip(index, error or {
                "queued": "Waiting to load. Select to prioritize.",
                "loading": "Loading in background", "ready": "Ready",
                "failed": "Failed - open the tab to retry",
            }[state])
        if state in ("queued", "loading"):
            self._load_overlays[stage].display(
                f"Loading {title.replace('&&', '&')} for {self._requested_policy[0]}...\n"
                "You can use other ready tabs while this loads."
            )
        elif state == "failed":
            self._load_overlays[stage].display(error, failed=True)

    @pyqtSlot(str, str)
    def _on_load_state_changed(self, stage: str, state: str):
        self._set_tab_state(stage, state)

    def _show_initial_notice(self, message: str, *, failed: bool = False):
        self._show_status(message)
        for stage, overlay in self._load_overlays.items():
            self._set_tab_state(stage, "failed" if failed else "queued", message)
            overlay.display(message, failed=failed)

    @pyqtSlot(int, str, str)
    def _on_load_failed(self, token: int, stage: str, error: str):
        if token != self._load_token:
            return
        logger.error("PolView %s unavailable: %s", stage, error)
        if stage == "coverages" and self._policy is None:
            self._show_initial_notice(error, failed=True)
            if is_password_error(error):
                dsn = REGION_DSN_MAP.get(self._requested_policy[1], "NEON_DSN")
                _show_odbc_warning(self, dsn, error_detail=error)
        else:
            self._set_tab_state(stage, "failed", error)
            self._show_status(f"{self._stage_tabs[stage][1]} unavailable: {error}")

    @pyqtSlot(str)
    def _retry_policy_tab(self, stage: str):
        if self._policy is None or stage == "coverages":
            self._on_get_policy(*self._requested_policy)
        else:
            self._pending_policy_tabs.add(self._stage_tabs[stage][0])
            self._loader.retry(stage)

    @pyqtSlot(int)
    def _on_background_settled(self, token: int):
        if token != self._load_token or self._policy is None:
            return
        failures = [key for key, state in self._tab_states.items() if state == "failed"]
        self._show_status(
            f"{self._policy.policy_number} - "
            + (f"{len(failures)} tab(s) unavailable; open a marked tab to retry"
               if failures else "Background data ready")
        )
        self.background_ready.emit()

    # == Tree selection handlers ===========================================

    def _on_table_selected(self, policy_record: str, table_name: str):
        if not self._db or not self._where_clause:
            QMessageBox.information(self, "Info", "Please load a policy first")
            return

        self.tabs.setCurrentWidget(self.raw_table_tab)

        policy_id = self._policy_info.get("PolicyID") if self._policy_info else None
        company_code = self._policy_info.get("CompanyCode") if self._policy_info else None

        self.raw_table_tab.load_table(
            self._db, table_name, self._where_clause,
            policy_id=policy_id, company_code=company_code,
        )

    def _on_rate_selected(self, category: str, label: str, index: int):
        """Handle rate node selection from the rates tree."""
        if not self._policy:
            return

        self._show_status(f"Loading rates for {label}...")
        self.tabs.setCurrentWidget(self.raw_table_tab)
        self.raw_table_tab.show_message(f"Loading rates for {label}...", table_name=label)

        try:
            matrix = None
            display_title = ""

            if category == "Coverages":
                if (not self._policy.is_advanced_product
                        and self._policy.product_type == "WL"
                        and self._policy.premium_pay_status_code.strip() in ("44", "45")):
                    message = "Cash value file is not available for policies on ETI or RPU."
                    self.raw_table_tab.show_message(
                        message, table_name=f"Whole Life Cash Value Rates - Coverage {index}"
                    )
                    self._show_status(message)
                    return
                matrix = self._policy.build_coverage_rate_matrix(index)
                display_title = f"Rates for Coverage {index}"
                if matrix and "CV" in matrix[0]:
                    display_title = f"Whole Life Cash Value Rates - Coverage {index}"
            elif category == "Benefits":
                matrix = self._policy.build_benefit_rate_matrix(index)
                display_title = f"Rates for Benefit {index}"
            elif category == "Policy":
                matrix = self._policy.build_policy_rate_matrix()
                display_title = "Policy Level Rates"

            if matrix is not None and len(matrix) > 1:
                self.tabs.setCurrentWidget(self.raw_table_tab)

                headers = matrix[0]
                data_rows = [tuple(row) for row in matrix[1:]]

                self.raw_table_tab.set_data(
                    headers, data_rows, table_name=display_title, transposed=False
                )

                rate_col_start = next(
                    (i for i, h in enumerate(headers) if h in ("COI", "TPP")), -1
                )
                if rate_col_start >= 0:
                    all_na = all(
                        str(row[c]) == "NA"
                        for row in data_rows[:5]
                        for c in range(rate_col_start, len(headers))
                        if c < len(row)
                    )
                    if all_na:
                        diag_msg = (
                            f"{display_title} - {len(data_rows)} rows "
                            "(Rate values show NA -- check UL_Rates ODBC connection)"
                        )
                    else:
                        diag_msg = f"{display_title} - {len(data_rows)} rows"
                else:
                    diag_msg = f"{display_title} - {len(data_rows)} rows"

                self._show_status(diag_msg)
            else:
                diag = ""
                if matrix is None:
                    ok = 'OK'
                    miss = 'MISSING'
                    if category == "Coverages":
                        if not self._policy.is_advanced_product and self._policy.product_type == "WL":
                            diag = (
                                f" (WL_RATE_CV: company={self._policy.company_code}, "
                                f"key={self._policy.cov_cash_value_key(index)!r}, "
                                f"issue_age={self._policy.cov_issue_age(index)}, user_defined=blank)"
                            )
                        else:
                            iss_dt = self._policy.cov_issue_date(index)
                            iss_age = self._policy.cov_issue_age(index)
                            band = self._policy.cov_band(index)
                            miss_rates = 'MISSING -- check UL_Rates connection'
                            diag = (
                                f" (issue_date={ok if iss_dt else miss}"
                                f", issue_age={ok if iss_age is not None else miss}"
                                f", band={ok if band is not None else miss_rates})"
                            )
                    elif category == "Benefits":
                        iss_dt = self._policy.cov_issue_date(1)
                        benefits = self._policy.get_benefits()
                        ben_age = benefits[index - 1].issue_age if index <= len(benefits) else None
                        diag = (
                            f" (cov1_date={ok if iss_dt else miss}"
                            f", ben_age={ok if ben_age is not None else miss})"
                        )
                message = f"No rate data available for {label}{diag}"
                self.raw_table_tab.show_message(message, table_name=display_title or label)
                self._show_status(message)

        except Exception as e:
            logger.exception("Rate display failed for %s", label)
            self.raw_table_tab.show_message(f"Error loading rates: {e}", table_name=label)
            self._show_status(f"Error loading rates: {e}")
