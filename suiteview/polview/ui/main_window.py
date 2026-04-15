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

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout,
    QTabWidget, QPushButton, QLabel, QMessageBox, QApplication,
)
from PyQt6.QtGui import QCursor
from PyQt6.QtCore import Qt

from suiteview.ui.widgets.frameless_window import FramelessWindowBase
from suiteview.core.db2_connection import DB2Connection
from ..models.policy_information import PolicyInformation

from .styles import (
    TAB_WIDGET_STYLE,
    GREEN_BG, GOLD_TEXT, GOLD_PRIMARY,
    POLVIEW_HEADER_COLORS, POLVIEW_BORDER_COLOR,
)
from .widgets import PolicyLookupBar
from .tree_panel import PolicyRecordTreePanel
from .tabs import (
    CoveragesTab, PolicyTab, TargetsAccumulatorsTab, PersonsTab,
    AdvProdValuesTab, ActivityTab, DividendsTab, LoansTab, RawTableTab,
    PolicyListWindow, PolicySupportTab, ReinsuranceTab,
)


class GetPolicyWindow(FramelessWindowBase):
    """
    Main PolView window with SuiteView frameless chrome.
    Features a professional green and gold color scheme.
    Uses PolicyInformation for centralized data access.
    """

    def __init__(self, parent=None):
        self._db: Optional[DB2Connection] = None
        self._policy: Optional[PolicyInformation] = None
        self._current_policy = None
        self._current_region = None
        self._where_clause = None
        self._policy_info = {}
        self._policy_history = []
        self._history_panel_visible = False
        # Cache: (policy_number, region) -> (PolicyInformation, policy_info_dict, where_clause)
        self._policy_cache: dict = {}

        super().__init__(
            title="SuiteView:  PolView",
            default_size=(1000, 780),
            min_size=(400, 400),
            parent=parent,
            header_colors=POLVIEW_HEADER_COLORS,
            border_color=POLVIEW_BORDER_COLOR,
        )

    # == FramelessWindowBase override =====================================

    # Width of the tree panel when extended
    TREE_PANEL_WIDTH = 200

    def build_content(self) -> QWidget:
        """Build the main body widget (everything below the title bar)."""
        self._tree_visible = False

        body = QWidget()
        body.setStyleSheet(f"background-color: {GREEN_BG};")
        main_layout = QVBoxLayout(body)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # Policy lookup bar
        self.lookup_bar = PolicyLookupBar()
        self.lookup_bar.policy_requested.connect(self._on_get_policy)  # (policy, region, company)
        self.lookup_bar.company_chosen.connect(self._on_get_policy)    # (policy, region, company)
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
        content_widget.setStyleSheet(f"background-color: {GREEN_BG};")
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
        tabs_container.setStyleSheet(f"background-color: {GREEN_BG};")
        tabs_layout = QVBoxLayout(tabs_container)
        tabs_layout.setContentsMargins(10, 10, 10, 10)
        tabs_layout.setSpacing(10)

        self.tabs = QTabWidget()
        self.tabs.setStyleSheet(TAB_WIDGET_STYLE)

        self.coverages_tab = CoveragesTab()
        self.policy_tab = PolicyTab()
        self.targets_tab = TargetsAccumulatorsTab()
        self.persons_tab = PersonsTab()
        self.dividends_tab = DividendsTab()
        self.advprod_tab = AdvProdValuesTab()
        self.activity_tab = ActivityTab()
        self.loans_tab = LoansTab()
        self.reinsurance_tab = ReinsuranceTab()
        self.raw_table_tab = RawTableTab()

        self.policy_support_tab = PolicySupportTab()
        self._policies_with_support_tab: set = set()  # track which policies have PS tab open

        self.tabs.addTab(self.coverages_tab, "Coverages")
        self.tabs.addTab(self.policy_tab, "Policy")
        self.tabs.addTab(self.targets_tab, "Targets && Accumulators")
        self.tabs.addTab(self.persons_tab, "Persons")
        # AdvProdValues tab added dynamically in _load_all_tabs() for advanced products only
        self.tabs.addTab(self.activity_tab, "Activity")
        self.tabs.addTab(self.raw_table_tab, "Raw Table")
        # PolicySupport tab added dynamically via double-click on Policy Info header

        # Connect CoveragesTab signal to show Policy Support tab
        self.coverages_tab.policy_support_requested.connect(self._show_policy_support_tab)

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
        bottom_bar.setStyleSheet(f"""
            background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                stop:0 #0A3D0A, stop:1 #2E7D32);
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

        # Policy List side-window
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
        self._history_panel_visible = not self._history_panel_visible
        if self._history_panel_visible:
            self.policy_list_window.show_docked()
        else:
            self.policy_list_window.hide()
        if hasattr(self, 'list_toggle_btn'):
            self.list_toggle_btn.setChecked(self._history_panel_visible)

    def _on_policy_selected_from_list(self, region: str, company: str, policy: str):
        self.lookup_bar.region_input.setText(region)
        self.lookup_bar.company_input.setText(company)
        self.lookup_bar.policy_input.setText(policy)
        self.lookup_bar._on_get_policy()

    def _add_policy_to_history(self, region: str, company: str, policy: str):
        if hasattr(self, "policy_list_window"):
            self.policy_list_window.add_policy(region, company, policy)

    def _on_policy_removed_from_list(self, policy_number: str, region: str):
        """Evict a single policy from the cache."""
        cache_key = (policy_number, region)
        self._policy_cache.pop(cache_key, None)

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

    def closeEvent(self, event):
        if self._db:
            self._db.close()
        event.accept()

    # == Policy Support tab =================================================

    def _show_policy_support_tab(self):
        """Show the Policy Support tab (triggered by double-click on Policy Info).

        Dynamically adds the tab if not already present, loads the
        current policy's data, and switches focus to it.
        Records the policy so the tab reappears when switching back.
        """
        # Record this policy as having the PS tab
        if self._policy and self._policy.exists:
            key = f"{self._policy.company_code}_{self._policy.policy_number}"
            self._policies_with_support_tab.add(key)

        ps_idx = self.tabs.indexOf(self.policy_support_tab)
        if ps_idx < 0:
            # Insert before Raw Table (at the end of content tabs)
            raw_idx = self.tabs.indexOf(self.raw_table_tab)
            if raw_idx >= 0:
                self.tabs.insertTab(raw_idx, self.policy_support_tab, "Policy Support")
            else:
                self.tabs.addTab(self.policy_support_tab, "Policy Support")

        # Load data if we have a policy
        if self._policy and self._policy.exists:
            self.policy_support_tab.load_data_from_policy(self._policy)

        # Switch to the tab
        self.tabs.setCurrentWidget(self.policy_support_tab)
        self._show_status("Policy Support tab opened")

    # == Policy loading ====================================================

    def _on_get_policy(self, policy_number: str, region: str, company_code: str = ""):
        """Handle policy lookup request using PolicyInformation.

        Results are cached so re-selecting a policy from the list is instant.
        When company_code is empty and multiple companies are found,
        shows a company chooser instead of loading.
        """
        # Hide any previous company chooser
        self.lookup_bar.hide_company_chooser()

        # Show loading indicator immediately
        QApplication.setOverrideCursor(QCursor(Qt.CursorShape.WaitCursor))

        cache_key = (policy_number, region)

        # Check cache first
        if cache_key in self._policy_cache:
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
                QMessageBox.warning(
                    self, "Not Found",
                    f"Policy {policy_number} not found in {region}\n{self._policy.last_error}",
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

            # Store in cache
            self._policy_cache[cache_key] = {
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
            t_tabs = _time.perf_counter() - t2

            t_total = _time.perf_counter() - t0
            self._show_status(
                f"Loaded {policy_number} ({company_code}) "
                f"- {self._policy.status_description}  |  "
                f"Policy: {t_policy:.1f}s  Tabs: {t_tabs:.1f}s  "
                f"Total: {t_total:.1f}s"
            )

        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to load policy: {e}")
            self._show_status(f"Error: {e}")
        finally:
            QApplication.restoreOverrideCursor()

    def _load_all_tabs(self):
        """Load data into all tabs using PolicyInformation."""
        if not self._policy or not self._policy.exists:
            return

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

        # Dividends tab -- add/remove dynamically
        dividends_index = self.tabs.indexOf(self.dividends_tab)
        if dividends_index >= 0:
            self.tabs.removeTab(dividends_index)

        if self.dividends_tab.has_dividend_data(self._policy):
            self.tabs.insertTab(4, self.dividends_tab, "Dividends")
            self.dividends_tab.load_data_from_policy(self._policy)

        # Loans tab -- add/remove dynamically based on loan data
        loans_idx = self.tabs.indexOf(self.loans_tab)
        if loans_idx >= 0:
            self.tabs.removeTab(loans_idx)

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

        # Always show the tab — it will display either data or "not found" message
        activity_idx = self.tabs.indexOf(self.activity_tab)
        if activity_idx >= 0:
            self.tabs.insertTab(activity_idx, self.reinsurance_tab, "Reinsurance")
        else:
            self.tabs.addTab(self.reinsurance_tab, "Reinsurance")
        self.reinsurance_tab.load_data_from_policy(self._policy)

        # Policy Support tab -- show/hide based on per-policy tracking.
        ps_idx = self.tabs.indexOf(self.policy_support_tab)
        pol_key = f"{self._policy.company_code}_{self._policy.policy_number}"
        if pol_key in self._policies_with_support_tab:
            # This policy should have the tab — add if missing, refresh data
            if ps_idx < 0:
                raw_idx = self.tabs.indexOf(self.raw_table_tab)
                if raw_idx >= 0:
                    self.tabs.insertTab(raw_idx, self.policy_support_tab, "Policy Support")
                else:
                    self.tabs.addTab(self.policy_support_tab, "Policy Support")
            self.policy_support_tab.load_data_from_policy(self._policy)
        else:
            # This policy doesn't have the tab — remove if present
            if ps_idx >= 0:
                self.tabs.removeTab(ps_idx)

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

                self.raw_table_tab.table_label.setText(display_title)
                self.raw_table_tab._current_table_name = display_title
                self.raw_table_tab._current_cols = headers
                self.raw_table_tab._current_rows = data_rows
                self.raw_table_tab._is_transposed = False
                self.raw_table_tab._display_data()

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
                    if category == "Coverages":
                        iss_dt = self._policy.cov_issue_date(index)
                        iss_age = self._policy.cov_issue_age(index)
                        band = self._policy.cov_band(index)
                        ok = 'OK'
                        miss = 'MISSING'
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
