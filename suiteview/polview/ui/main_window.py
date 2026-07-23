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

import subprocess

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout,
    QTabWidget, QPushButton, QLabel, QMessageBox, QApplication,
)
from PyQt6.QtGui import QCursor
from PyQt6.QtCore import Qt

from suiteview.ui.widgets.frameless_window import FramelessWindowBase
from suiteview.core.db2_connection import DB2Connection
from suiteview.core.db2_constants import REGION_DSN_MAP
from suiteview.core.odbc_utils import is_password_error
from ..models.policy_information import PolicyInformation

from .styles import (
    TAB_WIDGET_STYLE,
    GREEN_BG, GOLD_TEXT, GOLD_PRIMARY,
    POLVIEW_HEADER_COLORS, POLVIEW_DUPLICATE_HEADER_COLORS, POLVIEW_BORDER_COLOR,
)
from .widgets import PolicyLookupBar
from .tree_panel import PolicyRecordTreePanel
from .tabs import (
    CoveragesTab, PolicyTab, TargetsAccumulatorsTab, PersonsTab,
    AdvProdValuesTab, ActivityTab, DividendsTab, LoansTab, RawTableTab,
    PolicyListWindow, PolicySupportTab, PolicyLibraryTab, ReinsuranceTab,
    SapTab, ClaimsTab, TaiFdTab, OrionPcrTab, CyberlifePdfTab,
)


# Header-bar button style (PolView green/gold), matching the other compact
# header controls — used for the "Open in Illustrator" button.
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
    msg.setWindowTitle("ODBC Connection Failed")
    msg.setText(
        f"Connection to {dsn} failed.\n\n"
        "This likely means you need to update your ODBC password.\n\n"
        "1.  Click \"Open Manager\" below\n"
        f"2.  Double-click on {dsn} to open it\n"
        "3.  Update your password, then click Test to verify it works\n"
        "4.  Close the ODBC Manager and retry your policy lookup"
    )

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

    def __init__(self, parent=None, *, enable_policy_list: bool = True,
                 initial_policy: str = "", initial_region: str = "CKPR",
                 initial_company: str = ""):
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
        self._history_panel_visible = False
        # Cache: (policy_number, region) -> (PolicyInformation, policy_info_dict, where_clause)
        self._policy_cache: dict = {}
        # Per-policy snapshots of the optional SAP / CLAIMSFILE tabs so switching
        # between already-viewed policies restores what was there, while a brand
        # new policy starts with a clean slate.
        self._aux_tab_state: dict = {}

        # Header-bar "Open in Illustrator" button (built before super().__init__
        # so FramelessWindowBase can place it via header_widgets; wired after).
        self.open_illustrator_btn = QPushButton("📈 Illustrator")
        self.open_illustrator_btn.setToolTip("Open this policy in the Illustrator")
        self.open_illustrator_btn.setEnabled(False)
        self.open_illustrator_btn.setStyleSheet(HEADER_ILLUSTRATOR_BUTTON_STYLE)

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
            header_widgets=[self.open_illustrator_btn],
        )
        self.open_illustrator_btn.clicked.connect(self._open_in_illustrator)

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
        self.sap_tab = SapTab(self.tabs)
        self.claims_tab = ClaimsTab(self.tabs)
        self.tai_fd_tab = TaiFdTab(self.tabs)
        self.orion_pcr_tab = OrionPcrTab(self.tabs)
        self.cyberlife_pdf_tab = CyberlifePdfTab(self.tabs)

        # Optional database-backed tabs that get a clean slate on a new policy
        # but are restored when switching back to an already-viewed policy.
        # (tab widget, tab title)
        self._aux_tabs = [
            (self.sap_tab, "SAP"),
            (self.claims_tab, "CLAIMSFILE"),
            (self.tai_fd_tab, "TAICyberTAIFd"),
            (self.orion_pcr_tab, "orion_pcr3_r"),
            (self.cyberlife_pdf_tab, "CYBERLIFE_PDF"),
        ]

        self.tabs.addTab(self.coverages_tab, "Coverages")
        self.tabs.addTab(self.policy_tab, "Policy")
        self.tabs.addTab(self.targets_tab, "Targets && Accumulators")
        self.tabs.addTab(self.persons_tab, "Persons")
        # AdvProdValues tab added dynamically in _load_all_tabs() for advanced products only
        self.tabs.addTab(self.activity_tab, "Activity")
        self.tabs.addTab(self.policy_support_tab, "Policy Support")
        self.tabs.addTab(self.raw_table_tab, "Raw Table")

        for optional_tab in (
            self.dividends_tab,
            self.advprod_tab,
            self.loans_tab,
            self.reinsurance_tab,
            self.policy_library_tab,
            self.sap_tab,
            self.claims_tab,
            self.tai_fd_tab,
            self.orion_pcr_tab,
            self.cyberlife_pdf_tab,
        ):
            optional_tab.hide()

        self.policy_support_tab.policy_library_requested.connect(self._show_policy_library_tab)
        self.policy_support_tab.sap_requested.connect(self._show_sap_tab)
        self.policy_support_tab.claims_requested.connect(self._show_claims_tab)
        self.policy_support_tab.tai_fd_requested.connect(self._show_tai_fd_tab)
        self.policy_support_tab.orion_pcr_requested.connect(self._show_orion_pcr_tab)
        self.policy_support_tab.cyberlife_pdf_requested.connect(self._show_cyberlife_pdf_tab)
        self.coverages_tab.annuity_rider_requested.connect(self._show_annuity_rider_tab)

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
            self.policy_list_window.show_docked()
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
                    self.policy_list_window.show_docked()
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
                self.policy_list_window.show_docked()
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
            del self._policy_cache[k]

    def _on_all_policies_removed(self):
        """Evict all policies from the cache."""
        self._policy_cache.clear()

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
        if self._policy and self._policy.exists:
            self.policy_support_tab.load_data_from_policy(self._policy)

        self.tabs.setCurrentWidget(self.policy_support_tab)
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

    def _insert_aux_tab(self, tab: QWidget, title: str):
        """Insert an optional database-backed tab just before Raw Table."""
        if self.tabs.indexOf(tab) >= 0:
            return
        raw_idx = self.tabs.indexOf(self.raw_table_tab)
        if raw_idx >= 0:
            self.tabs.insertTab(raw_idx, tab, title)
        else:
            self.tabs.addTab(tab, title)

    def _show_aux_tab(self, tab: QWidget, title: str):
        """Open (or focus) an optional database-backed tab for the loaded policy."""
        first_open = self.tabs.indexOf(tab) < 0
        self._insert_aux_tab(tab, title)
        if first_open:
            tab.load_policy(self._policy)
        self.tabs.setCurrentWidget(tab)
        self._show_status(f"{title} tab opened")

    def _show_sap_tab(self):
        """Show the SAP.LDTI_TX7 ledger tab for the loaded policy."""
        self._show_aux_tab(self.sap_tab, "SAP")

    def _show_claims_tab(self):
        """Show the CLAIMSFILE claim-file tab for the loaded policy."""
        self._show_aux_tab(self.claims_tab, "CLAIMSFILE")

    def _show_tai_fd_tab(self):
        """Show the dbo.TAICyberTAIFd tab for the loaded policy."""
        self._show_aux_tab(self.tai_fd_tab, "TAICyberTAIFd")

    def _show_orion_pcr_tab(self):
        """Show the dbo.orion_pcr3_r tab for the loaded policy."""
        self._show_aux_tab(self.orion_pcr_tab, "orion_pcr3_r")

    def _show_cyberlife_pdf_tab(self):
        """Show the dbo.CYBERLIFE_PDF (pivoted) tab for the loaded policy."""
        self._show_aux_tab(self.cyberlife_pdf_tab, "CYBERLIFE_PDF")

    # -- Optional-tab state (SAP / CLAIMSFILE) ----------------------------

    def _current_aux_key(self):
        """Cache key for the currently loaded policy, or None if none loaded."""
        if not self._current_policy:
            return None
        company = (self._policy_info or {}).get("CompanyCode", "")
        return (self._current_policy, self._current_region, company)

    def _save_current_aux_state(self):
        """Snapshot the optional database-backed tabs for the outgoing policy."""
        key = self._current_aux_key()
        if key is None:
            return
        snapshot = {}
        for tab, title in self._aux_tabs:
            snapshot[title] = {
                "open": self.tabs.indexOf(tab) >= 0,
                "state": tab.export_state(),
            }
        self._aux_tab_state[key] = snapshot

    def _remove_aux_tabs(self):
        """Detach all optional database-backed tabs from the tab bar."""
        for tab, _title in self._aux_tabs:
            idx = self.tabs.indexOf(tab)
            if idx >= 0:
                self.tabs.removeTab(idx)
            tab.hide()

    def _reset_aux_tabs(self, key=None):
        """Clean slate for a brand new policy: close and clear all aux tabs."""
        self._remove_aux_tabs()
        for tab, _title in self._aux_tabs:
            tab.reset()
        if key is not None:
            self._aux_tab_state.pop(key, None)

    def _restore_aux_tabs(self, key):
        """Restore the optional tabs for a previously-viewed policy."""
        self._remove_aux_tabs()
        snapshot = self._aux_tab_state.get(key) or {}
        for tab, title in self._aux_tabs:
            entry = snapshot.get(title)
            if entry and entry.get("open"):
                self._insert_aux_tab(tab, title)
                tab.restore_state(self._policy, entry.get("state", {}))
            else:
                tab.reset()

    def _show_annuity_rider_tab(self, coverage=None):
        """Focus the embedded Annuity Rider section for eligible rider coverage."""
        if not self._policy or not self._policy.exists:
            return

        if coverage is not None:
            plancode = str(getattr(coverage, "plancode", "")).strip().upper()
            if plancode != "0699830R":
                return

        self.policy_support_tab.load_data_from_policy(self._policy)
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
        header "Open in Illustrator" button. The taskbar sets this so the shared
        Illustration window is reused; when unset the button opens a standalone
        Illustration window."""
        self._illustration_launcher = launcher

    def _open_in_illustrator(self):
        """Open the currently-loaded policy in the Illustration app."""
        if not self._current_policy:
            return
        region = self._current_region or "CKPR"
        company = str((self._policy_info or {}).get("CompanyCode", "") or "")
        if self._illustration_launcher is not None:
            self._illustration_launcher(self._current_policy, region, company)
            return
        # Standalone fallback: open our own Illustration window.
        from suiteview.illustration.ui.main_window import IllustrationWindow
        self._illustrator_window = IllustrationWindow(
            initial_policy=self._current_policy,
            initial_region=region,
            initial_company=company,
        )
        self._illustrator_window.show()

    def _on_get_policy(self, policy_number: str, region: str, company_code: str = ""):
        """Handle policy lookup request using PolicyInformation.

        Results are cached so re-selecting a policy from the list is instant.
        When company_code is empty and multiple companies are found,
        shows a company chooser instead of loading.
        """
        # Hide any previous company chooser
        self.lookup_bar.hide_company_chooser()

        # Snapshot the optional SAP / CLAIMSFILE tabs for the outgoing policy
        # before we switch, so returning to it restores what was there.
        self._save_current_aux_state()

        # Show loading indicator immediately
        QApplication.setOverrideCursor(QCursor(Qt.CursorShape.WaitCursor))

        cache_key = (policy_number, region, company_code)

        # Check cache first
        if company_code and cache_key in self._policy_cache:
            self._show_status(f"Loading policy {policy_number} from cache...")
            QApplication.processEvents()
            cached = self._policy_cache[cache_key]
            self._policy = cached["policy"]
            self._policy_info = cached["policy_info"]
            self._where_clause = cached["where_clause"]
            self._current_policy = policy_number
            self._current_region = region

            company_code = self._policy_info["CompanyCode"]
            is_pending = self._policy_info.get("SystemCode") == "P"

            # Reconnect DB if region changed
            if not self._db or self._db.region != region:
                if self._db:
                    self._db.close()
                self._db = DB2Connection(region)
                self._db.connect()

            self.lookup_bar.set_policy_display(
                company_code, policy_number, region, is_pending=is_pending
            )

            # Deferred tree loading for cached policies too
            self.records_tree.reset_for_new_policy()
            self.records_tree.store_connection_info(
                self._db, self._where_clause,
                policy_id=self._policy_info["PolicyID"],
                company_code=company_code,
            )
            self.records_tree.enable_rates_tab(self._policy)
            self.records_tree.show_rates_tab()

            self._load_all_tabs()
            # Switching back to a previously-viewed policy: restore its
            # SAP / CLAIMSFILE tabs exactly as they were left.
            self._restore_aux_tabs(self._current_aux_key())
            self._show_status(
                f"Loaded policy {policy_number} ({company_code}) "
                f"- {self._policy.status_description} (cached)"
            )
            QApplication.restoreOverrideCursor()
            return

        self._show_status(f"Loading policy {policy_number} from {region}...")
        QApplication.processEvents()

        try:
            import time as _time

            t0 = _time.perf_counter()
            self._policy = PolicyInformation(
                policy_number,
                company_code=company_code or None,
                region=region,
            )
            t_policy = _time.perf_counter() - t0

            # Check if multiple companies were found (no extra DB query needed)
            if self._policy.available_companies:
                self.lookup_bar.show_company_chooser(
                    self._policy.available_companies, policy_number, region
                )
                self._show_status(
                    f"Policy {policy_number} found in "
                    f"{len(self._policy.available_companies)} companies: "
                    f"{', '.join(self._policy.available_companies)} — select one above"
                )
                return

            # Fallback: if inforce (I) not found, try pending (P)
            if not self._policy.exists:
                self._policy = PolicyInformation(
                    policy_number,
                    company_code=company_code or None,
                    system_code="P",
                    region=region,
                )
                # Pending may also have multiple companies
                if self._policy.available_companies:
                    self.lookup_bar.show_company_chooser(
                        self._policy.available_companies, policy_number, region
                    )
                    self._show_status(
                        f"Policy {policy_number} (Pending) found in "
                        f"{len(self._policy.available_companies)} companies: "
                        f"{', '.join(self._policy.available_companies)} — select one above"
                    )
                    return

            if not self._policy.exists:
                error_text = self._policy.last_error or ""
                # Detect connection / auth errors and offer ODBC Manager
                if error_text and is_password_error(error_text):
                    dsn = REGION_DSN_MAP.get(region, "NEON_DSN")
                    QApplication.restoreOverrideCursor()
                    _show_odbc_warning(self, dsn, error_detail=error_text)
                    self._show_status(
                        f"{dsn} connection failed — update your ODBC password and retry"
                    )
                    return

                QMessageBox.warning(
                    self, "Not Found",
                    f"Policy {policy_number} not found in {region}\n{error_text}",
                )
                self._show_status("Policy not found")
                return

            company_code = self._policy.company_code
            system_code = self._policy.system_code
            tch_pol_id = self._policy.policy_id

            self._where_clause = (
                f"CK_SYS_CD = \'{system_code}\' "
                f"AND TCH_POL_ID = \'{tch_pol_id}\' "
                f"AND CK_CMP_CD = \'{company_code}\'"
            )

            self._policy_info = {
                "PolicyID": tch_pol_id,
                "PolicyNumber": policy_number,
                "CompanyCode": company_code,
                "SystemCode": system_code,
                "Region": region,
            }

            # Store in cache (keyed by policy+region+company)
            store_key = (policy_number, region, company_code)
            self._policy_cache[store_key] = {
                "policy": self._policy,
                "policy_info": dict(self._policy_info),
                "where_clause": self._where_clause,
            }

            self._current_policy = policy_number
            self._current_region = region

            if not self._db or self._db.region != region:
                if self._db:
                    self._db.close()
                self._db = DB2Connection(region)
                self._db.connect()

            is_pending = self._policy.system_code == "P"
            self._add_policy_to_history(region, company_code, policy_number)
            self.lookup_bar.set_policy_display(
                company_code, policy_number, region, is_pending=is_pending
            )

            # Reset tree and store connection info for lazy loading
            self.records_tree.reset_for_new_policy()
            self.records_tree.store_connection_info(
                self._db, self._where_clause,
                policy_id=tch_pol_id, company_code=company_code,
            )
            self.records_tree.enable_rates_tab(self._policy)
            # Start on Rates tab (fast) — Tables will load on-demand
            self.records_tree.show_rates_tab()

            t2 = _time.perf_counter()
            self._load_all_tabs()
            # Brand new policy: start with a clean slate — close the optional
            # SAP / CLAIMSFILE tabs and clear any prior policy's data.
            self._reset_aux_tabs(store_key)
            t_tabs = _time.perf_counter() - t2

            t_total = _time.perf_counter() - t0
            self._show_status(
                f"Loaded {policy_number} ({company_code}) "
                f"- {self._policy.status_description}  |  "
                f"Policy: {t_policy:.1f}s  Tabs: {t_tabs:.1f}s  "
                f"Total: {t_total:.1f}s"
            )

        except Exception as e:
            error_text = str(e)
            if is_password_error(error_text):
                dsn = REGION_DSN_MAP.get(region, "NEON_DSN")
                QApplication.restoreOverrideCursor()
                _show_odbc_warning(self, dsn, error_detail=error_text)
                self._show_status(
                    f"{dsn} connection failed — update your ODBC password and retry"
                )
                return
            QMessageBox.critical(self, "Error", f"Failed to load policy: {e}")
            self._show_status(f"Error: {e}")
        finally:
            QApplication.restoreOverrideCursor()

    def _load_all_tabs(self):
        """Load data into all tabs using PolicyInformation."""
        if not self._policy or not self._policy.exists:
            return

        # A policy is loaded — enable the "Open in Illustrator" header button.
        self.open_illustrator_btn.setEnabled(True)

        # Clear the Raw Table tab so stale data doesn't persist across policies
        self.raw_table_tab.clear()

        self.coverages_tab.load_data_from_policy(self._policy)
        self.policy_tab.load_data_from_policy(self._policy, self._policy_info)
        self.targets_tab.load_data_from_policy(self._policy)
        self.persons_tab.load_data_from_policy(self._policy)
        self.activity_tab.load_data_from_policy(self._policy)

        # AdvProdValues tab -- add/remove dynamically based on product type
        advprod_index = self.tabs.indexOf(self.advprod_tab)
        if self._policy.is_advanced_product:
            if advprod_index < 0:
                # Insert after Persons (index 4) or after Dividends if present
                insert_pos = self.tabs.indexOf(self.dividends_tab)
                if insert_pos >= 0:
                    insert_pos += 1
                else:
                    insert_pos = 4
                self.tabs.insertTab(insert_pos, self.advprod_tab, "AdvProdValues")
            self.advprod_tab.load_data_from_policy(self._policy)
        else:
            if advprod_index >= 0:
                self.tabs.removeTab(advprod_index)
            self.advprod_tab.hide()

        # Dividends tab -- add/remove dynamically
        dividends_index = self.tabs.indexOf(self.dividends_tab)
        if dividends_index >= 0:
            self.tabs.removeTab(dividends_index)
        self.dividends_tab.hide()

        if self.dividends_tab.has_dividend_data(self._policy):
            self.tabs.insertTab(4, self.dividends_tab, "Dividends")
            self.dividends_tab.load_data_from_policy(self._policy)

        # Loans tab -- add/remove dynamically based on loan data
        loans_idx = self.tabs.indexOf(self.loans_tab)
        if loans_idx >= 0:
            self.tabs.removeTab(loans_idx)
        self.loans_tab.hide()

        if self.loans_tab.has_loan_data(self._policy):
            # Insert before Activity tab
            activity_idx = self.tabs.indexOf(self.activity_tab)
            if activity_idx >= 0:
                self.tabs.insertTab(activity_idx, self.loans_tab, "Loans")
            else:
                self.tabs.addTab(self.loans_tab, "Loans")
            self.loans_tab.load_data_from_policy(self._policy)

        # Reinsurance tab -- add/remove dynamically based on TAICession data
        reins_idx = self.tabs.indexOf(self.reinsurance_tab)
        if reins_idx >= 0:
            self.tabs.removeTab(reins_idx)
        self.reinsurance_tab.hide()

        # Always show the tab — it will display either data or "not found" message
        activity_idx = self.tabs.indexOf(self.activity_tab)
        if activity_idx >= 0:
            self.tabs.insertTab(activity_idx, self.reinsurance_tab, "Reinsurance")
        else:
            self.tabs.addTab(self.reinsurance_tab, "Reinsurance")
        self.reinsurance_tab.load_data_from_policy(self._policy)

        self.policy_support_tab.load_data_from_policy(self._policy)

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

        try:
            matrix = None
            display_title = ""

            if category == "Coverages":
                matrix = self._policy.build_coverage_rate_matrix(index)
                display_title = f"Rates for Coverage {index}"
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
                self._show_status(f"No rate data available for {label}{diag}")

        except Exception as e:
            self._show_status(f"Error loading rates: {e}")
