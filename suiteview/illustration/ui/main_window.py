"""Main window for the SuiteView Illustration app."""

import copy
import logging
from typing import Optional

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QCursor
from PyQt6.QtWidgets import (
    QApplication,
    QLabel,
    QMessageBox,
    QPushButton,
    QSizePolicy,
    QStackedWidget,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from suiteview.core.build_env import is_distribution_build
from suiteview.core.db2_connection import DB2Connection
from suiteview.core.odbc_utils import is_password_error
from suiteview.illustration.core.calc_engine import IllustrationEngine
from suiteview.illustration.core.illustration_policy_service import build_illustration_data
from suiteview.illustration.core.rate_loader import load_rates
from suiteview.illustration.core.rate_validation import missing_required_rate_warnings
from suiteview.illustration.core.scenario_builder import build_illustration_scenario
from suiteview.illustration.models.plancode_config import load_plancode
from suiteview.polview.models.policy_information import PolicyInformation
from suiteview.polview.ui.widgets import PolicyLookupBar
from suiteview.ui.widgets.frameless_window import FramelessWindowBase

from suiteview.illustration.models.case_store import CaseStoreError

from .case_controls import CasesController
from .inputs_tab import IllustrationInputsTab
from .policy_list import IllustrationPolicyListWindow
from .policy_tab import IllustrationPolicyTab
from .compare_tab import IllustrationCompareTab
from .report_tab import IllustrationReportTab
from .saved_cases_panel import format_saved_stamp
from .values_tab import IllustrationValuesTab
from .styles import (
    GOLD_TEXT,
    HEADER_PANEL_BUTTON_STYLE,
    ILLUSTRATION_BORDER_COLOR,
    ILLUSTRATION_HEADER_COLORS,
    ILLUSTRATION_SNAPSHOT_HEADER_COLORS,
    PURPLE_BG,
    STATUS_BAR_STYLE,
    TAB_WIDGET_STYLE,
    VALUE_BUTTON_STYLE,
)

logger = logging.getLogger(__name__)

WINDOW_TITLE = "SuiteView:  Illustration"


class IllustrationWindow(FramelessWindowBase):
    """PolView-style shell for Illustration."""

    def __init__(self, parent=None, initial_policy: str = "",
                 initial_region: str = "CKPR", initial_company: str = ""):
        self._db: Optional[DB2Connection] = None
        self._policy: Optional[PolicyInformation] = None
        self._current_policy = None
        self._current_region = None
        self._where_clause = None
        self._policy_info = {}
        self._policy_cache: dict = {}
        self._list_panel_visible = False
        self._last_scenario = None
        # Per-policy session state, keyed like _policy_cache by
        # (policy_number, region, company_code). Each entry keeps the policy's
        # live IllustrationInputsTab widget (the inputs ARE the widget state —
        # dynamic rows, grids, control toggles, solved amounts) plus snapshots
        # of the last computed values/report/status, so switching back to a
        # visited policy restores everything without re-entering or re-running.
        # Session-only: never persisted to disk.
        self._session_states: dict[tuple, dict] = {}
        self._current_key: tuple | None = None
        # Set while a saved case's FROZEN policy snapshot is loaded instead of
        # live DB2 data (activated from the Saved Cases panel).
        # Run Values then projects the snapshot — no DB2 round trip — and the
        # header/inputs wear a visible as-of indicator. Cleared by any fresh
        # policy load (Get button / policy node). Invariant: when set, its
        # .policy_snapshot is never None.
        self._snapshot_case = None

        # The List panel-toggle button lives IN the window header (title
        # bar) — built before super().__init__ so FramelessWindowBase can
        # place it via header_widgets, wired after (the panel itself is
        # built in build_content). The panel holds both the Policy List and
        # the Saved Cases views behind its own Policies | Saved Cases toggle.
        self.list_toggle_btn = QPushButton("List")
        self.list_toggle_btn.setCheckable(True)
        self.list_toggle_btn.setToolTip(
            "Toggle the List panel (Policies / Saved Cases)")
        self.list_toggle_btn.setStyleSheet(HEADER_PANEL_BUTTON_STYLE)

        super().__init__(
            title=WINDOW_TITLE,
            default_size=(1200, 825),
            min_size=(500, 420),
            parent=parent,
            header_colors=ILLUSTRATION_HEADER_COLORS,
            border_color=ILLUSTRATION_BORDER_COLOR,
            header_widgets=[self.list_toggle_btn],
        )
        self.list_toggle_btn.clicked.connect(self._toggle_list_panel)

        # Optionally pull in a policy on open (e.g. launched from the taskbar
        # policy bar or PolView's "Open in Illustrator" button).
        if initial_policy:
            self.load_policy(initial_policy, region=initial_region,
                             company_code=initial_company)

    def load_policy(self, policy_number: str, region: str = "CKPR",
                    company_code: str = ""):
        """Load *policy_number* through the exact path the Get button uses.

        Public entry point reused by the taskbar policy launcher and PolView's
        "Open in Illustrator" header button — it drives the shared
        PolicyLookupBar so the load path is identical to a user typing the
        policy and clicking Get.
        """
        policy_number = (policy_number or "").strip()
        if not policy_number:
            return
        self.lookup_bar.region_input.setText(region or "CKPR")
        self.lookup_bar.company_input.setText(company_code or "")
        self.lookup_bar.policy_input.setText(policy_number)
        self.lookup_bar._on_get_policy()

    def build_content(self) -> QWidget:
        body = QWidget()
        body.setStyleSheet(f"background-color: {PURPLE_BG};")
        main_layout = QVBoxLayout(body)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        self.lookup_bar = PolicyLookupBar()
        self.lookup_bar.setMinimumHeight(58)
        self.lookup_bar.policy_label.setMinimumHeight(42)
        self.lookup_bar.policy_label.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        self.lookup_bar.policy_requested.connect(self._on_get_policy)
        self.lookup_bar.company_chosen.connect(self._on_get_policy)

        self.run_values_btn = QPushButton("Run Values")
        self.run_values_btn.setStyleSheet(VALUE_BUTTON_STYLE)
        self.run_values_btn.setEnabled(False)
        self.run_values_btn.setFixedHeight(28)
        self.run_values_btn.clicked.connect(self._on_run_values)
        self.lookup_bar.layout().addSpacing(8)
        self.lookup_bar.layout().addWidget(self.run_values_btn)

        # Saved cases: persist named input scenarios (plus a frozen policy
        # snapshot) to disk (~/.suiteview/illustration_cases) and reload them
        # across sessions. Save lives here; browsing/loading/rename/delete
        # live in the Saved Cases panel (header toggle).
        self._cases_controller = CasesController(
            self, on_cases_changed=self._refresh_saved_cases)
        self.save_case_btn = QPushButton("Save")
        self.save_case_btn.setToolTip(
            "Save the current illustration inputs (and policy data) as a "
            "named case")
        self.save_case_btn.setStyleSheet(VALUE_BUTTON_STYLE)
        self.save_case_btn.setEnabled(False)
        self.save_case_btn.setFixedHeight(28)
        self.save_case_btn.clicked.connect(self._cases_controller.save_flow)
        self.lookup_bar.layout().addSpacing(6)
        self.lookup_bar.layout().addWidget(self.save_case_btn)
        main_layout.addWidget(self.lookup_bar)

        tabs_container = QWidget()
        tabs_container.setStyleSheet(f"background-color: {PURPLE_BG};")
        tabs_layout = QVBoxLayout(tabs_container)
        tabs_layout.setContentsMargins(10, 10, 10, 10)
        tabs_layout.setSpacing(10)

        self.tabs = QTabWidget()
        self.tabs.setStyleSheet(TAB_WIDGET_STYLE)
        self.policy_tab = IllustrationPolicyTab()
        # One IllustrationInputsTab per visited policy lives in this stack;
        # self.inputs_tab always points at the active one. Swapping the whole
        # widget preserves every input exactly across policy switches.
        self._inputs_stack = QStackedWidget()
        self.inputs_tab = IllustrationInputsTab()
        self._inputs_stack.addWidget(self.inputs_tab)
        self.values_tab = IllustrationValuesTab()
        self.report_tab = IllustrationReportTab()
        self.compare_tab = IllustrationCompareTab(window=self)
        self.tabs.addTab(self.policy_tab, "Policy")
        self.tabs.addTab(self._inputs_stack, "Illustration Inputs")
        self.tabs.addTab(self.values_tab, "Values")
        self.tabs.addTab(self.report_tab, "Report")
        self.tabs.addTab(self.compare_tab, "Compare")
        tabs_layout.addWidget(self.tabs)
        main_layout.addWidget(tabs_container, 1)

        bottom_bar = QWidget()
        bottom_bar.setStyleSheet(STATUS_BAR_STYLE)
        bottom_layout = QVBoxLayout(bottom_bar)
        bottom_layout.setContentsMargins(8, 2, 8, 2)
        self._status_label = QLabel("Ready - Enter a policy number to begin")
        self._status_label.setStyleSheet(f"background: transparent; color: {GOLD_TEXT}; font-size: 11px; font-weight: bold;")
        bottom_layout.addWidget(self._status_label)
        main_layout.addWidget(bottom_bar)

        self._create_policy_list_window()
        return body

    def _create_policy_list_window(self):
        self.policy_list_window = IllustrationPolicyListWindow(self)
        self.policy_list_window.policy_selected.connect(self._on_policy_selected_from_list)
        self.policy_list_window.policy_open_requested.connect(self._on_policy_selected_from_list)
        self.policy_list_window.policy_removed.connect(self._on_policy_removed_from_list)
        self.policy_list_window.all_policies_removed.connect(self._on_all_policies_removed)
        # Saved Cases view (second page of the panel's Policies | Saved Cases
        # toggle): activation, copy, rename, and delete all route back here.
        cases_view = self.policy_list_window.cases_view
        cases_view.case_selected.connect(self._on_case_selected_from_list)
        cases_view.case_delete_requested.connect(self._on_case_delete_requested)
        cases_view.cases_delete_requested.connect(self._on_cases_delete_requested)
        cases_view.case_rename_requested.connect(self._on_case_rename_requested)
        cases_view.case_copy_requested.connect(self._on_case_copy_requested)

    def _refresh_saved_cases(self):
        if hasattr(self, "policy_list_window"):
            self.policy_list_window.refresh_cases()

    def _toggle_list_panel(self):
        self._list_panel_visible = not self._list_panel_visible
        if self._list_panel_visible:
            self.policy_list_window.show_docked()
        else:
            self.policy_list_window.hide()
        self.list_toggle_btn.setChecked(self._list_panel_visible)

    def _on_policy_selected_from_list(self, region: str, company: str, policy: str):
        if not self.isVisible():
            self.show()
        self.lookup_bar.region_input.setText(region)
        self.lookup_bar.company_input.setText(company)
        self.lookup_bar.policy_input.setText(policy)
        self.lookup_bar._on_get_policy()

    def _add_policy_to_history(self, region: str, company: str, policy: str):
        self.policy_list_window.add_policy(region, company, policy)

    def _on_policy_removed_from_list(self, policy_number: str, region: str):
        keys_to_remove = [key for key in self._policy_cache if key[0] == policy_number and key[1] == region]
        for key in keys_to_remove:
            del self._policy_cache[key]
        session_keys = [key for key in self._session_states if key[0] == policy_number and key[1] == region]
        for key in session_keys:
            self._drop_session_state(key)

    def _on_all_policies_removed(self):
        self._policy_cache.clear()
        for key in list(self._session_states):
            self._drop_session_state(key)

    # ── Per-policy session state (inputs + computed values) ──────────

    def _drop_session_state(self, key: tuple):
        """Forget a policy's session inputs/values. The active inputs widget
        stays on screen until the next switch (then it is unregistered and
        cleaned up by _set_active_inputs_tab)."""
        entry = self._session_states.pop(key, None)
        if entry is None:
            return
        inputs_tab = entry["inputs"]
        if inputs_tab is not self.inputs_tab:
            self._inputs_stack.removeWidget(inputs_tab)
            inputs_tab.deleteLater()

    def _registered_inputs_tabs(self) -> set:
        return {entry["inputs"] for entry in self._session_states.values()}

    def _set_active_inputs_tab(self, inputs_tab):
        """Front the given inputs widget; delete the outgoing one if no
        session entry owns it (the startup placeholder or a removed policy)."""
        previous = self.inputs_tab
        if inputs_tab is previous:
            return
        if self._inputs_stack.indexOf(inputs_tab) == -1:
            self._inputs_stack.addWidget(inputs_tab)
        self.inputs_tab = inputs_tab
        self._inputs_stack.setCurrentWidget(inputs_tab)
        if previous is not None and previous not in self._registered_inputs_tabs():
            self._inputs_stack.removeWidget(previous)
            previous.deleteLater()

    def _snapshot_active_session(self):
        """Capture the displayed values/report/status for the current policy
        before switching away. The inputs need no capture — each policy owns
        its live inputs widget in the stack."""
        entry = self._session_states.get(self._current_key) if self._current_key else None
        if entry is None:
            return
        entry["values"] = self.values_tab.capture_session_state()
        entry["report"] = self.report_tab.current_report()
        entry["status"] = self._status_label.text()
        entry["scenario"] = self._last_scenario

    def _show_status(self, message: str):
        self._status_label.setText(message)

    def _apply_illustration_gate(self) -> bool:
        """DISTRIBUTION-ONLY: if the loaded policy's plancode is flagged
        ``CanIllustrate = False``, disable Run Values and post a persistent
        notice in the status bar. In dev (running from source) this is a no-op,
        so the flag never blocks anything while building/testing.

        Called at the end of every policy/saved-case load. Returns True when
        the policy is blocked (button left disabled). Must run AFTER the load
        path has otherwise enabled the button, so the block wins.
        """
        if not is_distribution_build():
            return False
        plancode = str(getattr(self._illustration_data, "plancode", "") or "").strip()
        if not plancode:
            return False
        try:
            config = load_plancode(plancode)
        except Exception:
            return False
        if config.can_illustrate:
            return False
        self.run_values_btn.setEnabled(False)
        self._show_status(
            f"This plancode ({plancode}) is not currently enabled for "
            f"illustration in this application.")
        return True

    def _on_get_policy(self, policy_number: str, region: str, company_code: str = ""):
        self.lookup_bar.hide_company_chooser()
        # A fresh policy load always returns to LIVE data — clear any saved-
        # case as-of state so the user can trust what the header shows.
        self._snapshot_case = None
        self._set_live_header_mode()
        self.policy_tab.set_snapshot_notice(None)
        self.policy_tab.set_snapshot_banner(None)
        # Preserve the displayed values/report/status for the policy being
        # switched away from — restored if the user comes back this session.
        self._snapshot_active_session()
        QApplication.setOverrideCursor(QCursor(Qt.CursorShape.WaitCursor))
        cache_key = (policy_number, region, company_code)

        try:
            if company_code and cache_key in self._policy_cache:
                cached = self._policy_cache[cache_key]
                self._policy = cached["policy"]
                self._policy_info = cached["policy_info"]
                self._where_clause = cached["where_clause"]
                self._current_policy = policy_number
                self._current_region = region
                self._load_policy_into_ui(region, cached=True)
                return

            self._show_status(f"Loading policy {policy_number} from {region}...")
            QApplication.processEvents()
            self._policy = PolicyInformation(policy_number, company_code=company_code or None, region=region)

            if self._policy.available_companies:
                self.lookup_bar.show_company_chooser(self._policy.available_companies, policy_number, region)
                self._show_status(f"Policy {policy_number} found in {len(self._policy.available_companies)} companies - select one above")
                return

            if not self._policy.exists:
                self._policy = PolicyInformation(policy_number, company_code=company_code or None, system_code="P", region=region)
                if self._policy.available_companies:
                    self.lookup_bar.show_company_chooser(self._policy.available_companies, policy_number, region)
                    self._show_status(f"Policy {policy_number} (Pending) found in {len(self._policy.available_companies)} companies - select one above")
                    return

            if not self._policy.exists:
                QMessageBox.warning(self, "Not Found", f"Policy {policy_number} not found in {region}")
                self._show_status("Policy not found")
                self.run_values_btn.setEnabled(False)
                self.save_case_btn.setEnabled(False)
                self.values_tab.clear_results("Load a policy, then click Run Values.")
                self.report_tab.clear("Load a policy, then click Run Values.")
                # The cleared display no longer belongs to the previous policy;
                # detach so a later snapshot cannot overwrite its saved session.
                self._current_key = None
                return

            company_code = self._policy.company_code
            system_code = self._policy.system_code
            policy_id = self._policy.policy_id
            self._where_clause = f"CK_SYS_CD = '{system_code}' AND TCH_POL_ID = '{policy_id}' AND CK_CMP_CD = '{company_code}'"
            self._policy_info = {
                "PolicyID": policy_id,
                "PolicyNumber": policy_number,
                "CompanyCode": company_code,
                "SystemCode": system_code,
                "Region": region,
            }
            self._policy_cache[(policy_number, region, company_code)] = {
                "policy": self._policy,
                "policy_info": dict(self._policy_info),
                "where_clause": self._where_clause,
            }
            self._current_policy = policy_number
            self._current_region = region
            self._add_policy_to_history(region, company_code, policy_number)
            self._load_policy_into_ui(region, cached=False)

        except Exception as exc:
            if is_password_error(str(exc)):
                self._show_status(f"{region} connection failed - update your ODBC password and retry")
            else:
                QMessageBox.critical(self, "Error", f"Failed to load policy: {exc}")
                self._show_status(f"Error: {exc}")
        finally:
            QApplication.restoreOverrideCursor()

    def _load_policy_into_ui(self, region: str, cached: bool = False):
        if not self._policy or not self._policy.exists:
            return
        company_code = self._policy_info.get("CompanyCode", self._policy.company_code)
        if not self._db or self._db.region != region:
            if self._db:
                self._db.close()
            self._db = DB2Connection(region)
            self._db.connect()
        self.lookup_bar.set_policy_display(
            company_code,
            self._policy_info.get("PolicyNumber", self._policy.policy_number),
            region,
            is_pending=self._policy.system_code == "P",
        )
        warnings, md_check = self._policy_load_checks(
            policy_number=self._policy_info.get("PolicyNumber", self._policy.policy_number),
            region=region,
            company_code=company_code,
        )
        self.policy_tab.load_data_from_policy(self._policy, self._policy_info, md_check=md_check)
        self.policy_tab.set_rate_warnings(warnings)
        # Backfill both List views' "| <form>" label segment now that the
        # policy's data (and its base-coverage form number) is loaded.
        form_number = getattr(self._illustration_data, "form_number", "") or ""
        if form_number:
            self.policy_list_window.set_policy_form(
                self._policy_info.get("PolicyNumber", self._policy.policy_number),
                form_number)

        key = (
            self._policy_info.get("PolicyNumber", self._policy.policy_number),
            region,
            company_code,
        )
        session = self._session_states.get(key)
        if session is None:
            # First visit this session: fresh inputs from the policy, empty values.
            inputs_tab = IllustrationInputsTab()
            self._session_states[key] = {
                "inputs": inputs_tab,
                "values": None,
                "report": None,
                "status": None,
                "scenario": None,
            }
            self._set_active_inputs_tab(inputs_tab)
            inputs_tab.load_data_from_policy(
                self._policy,
                has_shadow=bool(getattr(self._illustration_data, "has_shadow_account", False)),
                shadow_ceased=bool(getattr(self._illustration_data, "ccv_ceased", False)))
            self.values_tab.clear_results("Click Run Values to project the selected illustration duration.")
            self.report_tab.clear()
        else:
            # Revisit: the policy's own inputs widget comes back untouched and
            # the last computed values/report re-render from the snapshot —
            # no engine run.
            self._set_active_inputs_tab(session["inputs"])
            if not self.values_tab.restore_session_state(session.get("values")):
                self.values_tab.clear_results("Click Run Values to project the selected illustration duration.")
            report = session.get("report")
            if report is not None:
                self.report_tab.display_report(report)
            else:
                self.report_tab.clear()
            self._last_scenario = session.get("scenario")

        # Live data on screen — no as-of strip on this policy's inputs tab.
        self.inputs_tab.set_snapshot_notice(None)

        # A different policy invalidates any rendered comparison — clear it so
        # the old policy's results can never sit under the new pickers.
        if self._current_key != key:
            self.compare_tab.clear_results()
        self._current_key = key
        self.run_values_btn.setEnabled(True)
        self.save_case_btn.setEnabled(True)
        if session is not None and session.get("status"):
            self._show_status(session["status"])
        else:
            cache_note = " (cached)" if cached else ""
            self._show_status(f"Loaded policy {self._policy.policy_number} ({company_code}) - {self._policy.status_description}{cache_note}")

        # Distribution builds gate illustration by plancode (no-op in dev).
        self._apply_illustration_gate()

    # ── saved-case activation (Saved Cases panel) ─────────────────────

    def _on_case_selected_from_list(self, case_name: str):
        """Activate a saved case from the Saved Cases panel.

        v2 cases restore their FROZEN policy snapshot — no DB2 round trip.
        v1 cases (no snapshot) fall back to a fresh live load of the policy
        plus a visible note that the case predates snapshots.
        """
        if not self.isVisible():
            self.show()
        try:
            case = self._cases_controller.load_named_case(case_name)
        except CaseStoreError as exc:
            QMessageBox.warning(self, "Load Case", str(exc))
            self._show_status(f"Load Case failed: {exc}")
            return
        if case.policy_snapshot is None:
            self._load_v1_case_against_live(case)
        else:
            self._load_case_snapshot(case)

    def _load_case_snapshot(self, case):
        """Restore a case's frozen IllustrationPolicyData as the loaded policy."""
        snapshot = copy.deepcopy(case.policy_snapshot)
        stamp = format_saved_stamp(case.saved_at)
        self.lookup_bar.hide_company_chooser()
        self._snapshot_active_session()

        policy_number = case.policy_number
        region = case.region or snapshot.region or "CKPR"
        company_code = case.company_code or snapshot.company_code or ""
        key = (policy_number, region, company_code)

        self._snapshot_case = case
        self._policy = None            # no live PolicyInformation in this mode
        self._where_clause = None
        self._current_policy = policy_number
        self._current_region = region
        self._illustration_data = snapshot   # a re-save re-freezes this data
        self._policy_info = {
            "PolicyNumber": policy_number,
            "CompanyCode": company_code,
            "Region": region,
        }

        # Header: the user must never mistake the snapshot for live data.
        self._set_case_asof_header(case)
        # The Policy tab populates from the frozen snapshot (no live DB2), with
        # a red statement across the top so frozen data is never mistaken for
        # live. Fields the snapshot never captured stay blank.
        self.policy_tab.load_data_from_snapshot(snapshot)
        self.policy_tab.set_rate_warnings(None)
        self.policy_tab.set_snapshot_banner(
            f"Policy data was not retrieved live — effective as of {stamp}. "
            f"Get the policy to return to live data.")
        if hasattr(self, "policy_list_window"):
            self.policy_list_window.set_policy_form(
                policy_number, snapshot.form_number)

        session = self._session_states.get(key)
        if session is None:
            inputs_tab = IllustrationInputsTab()
            self._session_states[key] = {
                "inputs": inputs_tab,
                "values": None,
                "report": None,
                "status": None,
                "scenario": None,
            }
            self._set_active_inputs_tab(inputs_tab)
            inputs_tab.load_data_from_policy(
                snapshot,
                has_shadow=bool(snapshot.has_shadow_account),
                shadow_ceased=bool(snapshot.ccv_ceased))
        else:
            self._set_active_inputs_tab(session["inputs"])
        # A different policy invalidates any rendered comparison — clear it so
        # the old policy's results can never sit under the new pickers.
        if self._current_key != key:
            self.compare_tab.clear_results()
        self._current_key = key

        warnings = self.inputs_tab.apply_case_inputs(case.inputs)
        self.inputs_tab.set_snapshot_notice(
            f"Viewing saved case “{case.name}” — policy data frozen as of "
            f"{stamp}. Run Values projects the snapshot, not the live policy. "
            f"Get the policy to return to live data.")
        self.values_tab.clear_results(
            "Click Run Values to project the saved case snapshot.")
        self.report_tab.clear()
        self.tabs.setCurrentWidget(self._inputs_stack)
        self.run_values_btn.setEnabled(True)
        self.save_case_btn.setEnabled(True)
        if warnings:
            bullets = "\n".join(f"•  {w}" for w in warnings)
            QMessageBox.warning(
                self, "Load Case",
                f"Case '{case.name}' loaded, but some inputs did not apply:"
                f"\n\n{bullets}")
            self._show_status(
                f"Loaded case '{case.name}' (policy data as of {stamp}) with "
                f"{len(warnings)} warning(s) — review the inputs, then Run Values.")
        else:
            self._show_status(
                f"Loaded case '{case.name}' — policy data as of {stamp}. "
                f"Review the inputs, then Run Values.")

        # Saved-case loads run values too — gate them the same way (dist only).
        self._apply_illustration_gate()

    def _load_v1_case_against_live(self, case):
        """No snapshot in the file: load CURRENT policy data, apply the case
        inputs onto it, and say so visibly."""
        region = case.region or "CKPR"
        self._on_get_policy(case.policy_number, region, case.company_code)
        if (self._current_key is None
                or self._current_key[0] != case.policy_number):
            # The live load did not land (not found / company chooser /
            # connection failure) — its own message is already on screen.
            self._show_status(
                f"Case '{case.name}' not applied — policy "
                f"{case.policy_number} did not load.")
            return
        warnings = self._cases_controller.apply_case(case)
        note = (
            f"Case “{case.name}” was saved before policy snapshots existed — "
            f"its inputs were applied to CURRENT policy data loaded fresh "
            f"from {region}.")
        self.inputs_tab.set_snapshot_notice(note)
        if warnings:
            bullets = "\n".join(f"•  {w}" for w in warnings)
            QMessageBox.warning(
                self, "Load Case",
                f"Case '{case.name}' loaded, but some inputs did not apply:"
                f"\n\n{bullets}")
        self._show_status(
            f"Loaded case '{case.name}' against CURRENT policy data (case "
            f"predates snapshots) — review the inputs, then Run Values.")
        # Restore the gate notice (dist only) — the live load already disabled
        # the button, but the status above overwrote the block message.
        self._apply_illustration_gate()

    def _set_case_asof_header(self, case):
        """Snapshot mode wears its state in the TITLE BAR: the case name
        joins the window title and the header gradient lightens. The big
        policy header line stays plain (the amber as-of strip on the inputs
        tab carries the frozen-date detail)."""
        region = case.region or "CKPR"
        company = case.company_code or "—"
        self.lookup_bar.policy_label.setText(
            f"{region} - {company} - {case.policy_number}")
        self.set_title(f"{WINDOW_TITLE} — Case “{case.name}”")
        self.set_header_colors(ILLUSTRATION_SNAPSHOT_HEADER_COLORS)

    def _set_live_header_mode(self):
        """Back to live data: standard title and header gradient."""
        self.set_title(WINDOW_TITLE)
        self.set_header_colors(ILLUSTRATION_HEADER_COLORS)

    def _on_case_delete_requested(self, case_name: str):
        answer = QMessageBox.question(
            self, "Delete Case", f"Delete saved case '{case_name}'?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No)
        if answer != QMessageBox.StandardButton.Yes:
            return
        try:
            self._cases_controller.delete_named_case(case_name)
        except CaseStoreError as exc:
            QMessageBox.warning(self, "Delete Case", str(exc))
            return
        self._show_status(f"Deleted saved case '{case_name}'.")

    # Names beyond this count are summarized as "and N more" instead of
    # listed — keeps the confirm dialog readable for a large selection.
    _BATCH_DELETE_NAMES_SHOWN = 5

    def _on_cases_delete_requested(self, case_names: list):
        """Multi-select delete (Delete key or 'Delete N Cases…' context-menu
        action) — one confirmation for the whole batch, then one
        ``delete_named_case`` call per case through the existing controller
        (no new persistence path)."""
        if not case_names:
            return
        count = len(case_names)
        if count == 1:
            self._on_case_delete_requested(case_names[0])
            return
        if count <= self._BATCH_DELETE_NAMES_SHOWN:
            names_text = "\n".join(f"  • {name}" for name in case_names)
            prompt = f"Delete {count} saved cases?\n\n{names_text}"
        else:
            prompt = f"Delete {count} saved cases?"
        answer = QMessageBox.question(
            self, "Delete Cases", prompt,
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No)
        if answer != QMessageBox.StandardButton.Yes:
            return
        deleted, errors = [], []
        for name in case_names:
            try:
                self._cases_controller.delete_named_case(name)
                deleted.append(name)
            except CaseStoreError as exc:
                errors.append(f"{name}: {exc}")
        if errors:
            QMessageBox.warning(
                self, "Delete Cases",
                "Some cases could not be deleted:\n\n" + "\n".join(errors))
        if deleted:
            self._show_status(f"Deleted {len(deleted)} saved cases.")

    def _on_case_copy_requested(self, case_name: str):
        self._cases_controller.copy_flow(case_name)

    def _on_case_rename_requested(self, case_name: str):
        from .case_controls import _name_prompt

        new_name = _name_prompt(self, "Rename Case", case_name)
        if not new_name or new_name == case_name:
            return
        try:
            renamed = self._cases_controller.rename_named_case(
                case_name, new_name)
        except CaseStoreError as exc:
            QMessageBox.warning(self, "Rename Case", str(exc))
            return
        # If the renamed case is the one currently loaded, track the new
        # identity so the as-of header and a later Save (pre-filled with the
        # case name) follow the rename instead of resurrecting the old name.
        if (self._snapshot_case is not None
                and self._snapshot_case.name == case_name):
            self._snapshot_case = renamed
            self._set_case_asof_header(renamed)
        self._show_status(
            f"Renamed saved case '{case_name}' to '{renamed.name}'.")

    def _policy_load_checks(self, policy_number: str, region: str, company_code: str):
        warnings: list[str] = []
        self._illustration_data = None
        try:
            policy_data = build_illustration_data(policy_number, region=region, company_code=company_code)
            self._illustration_data = policy_data
            warnings.extend(self._definition_of_life_warnings(policy_data))
            config = load_plancode(policy_data.plancode)
            rates = load_rates(policy_data, config)
            warnings.extend(missing_required_rate_warnings(policy_data, rates))
        except Exception as exc:
            return [f"Unable to validate illustration rider/benefit rates: {exc}"], None

        md_check = None
        try:
            md_check = IllustrationEngine().project(policy_data, months=0, rates_override=rates)[0]
            warnings.extend(self._monthly_deduction_warnings(md_check))
        except Exception as exc:
            warnings.append(f"Unable to validate monthly deduction: {exc}")
        return warnings, md_check

    @staticmethod
    def _monthly_deduction_warnings(md_check) -> list[str]:
        cyberlife_md = float(getattr(md_check, "system_monthly_deduction", 0.0) or 0.0)
        calculated_md = float(getattr(md_check, "md_check_calculated_deduction", 0.0) or 0.0)
        variance = calculated_md - cyberlife_md
        if abs(variance) < 0.005:
            return []
        return [
            "Monthly deduction check mismatch: "
            f"CyberLife MD ${cyberlife_md:,.2f} vs Calculated MD ${calculated_md:,.2f} "
            f"(variance ${variance:,.2f})."
        ]

    @staticmethod
    def _definition_of_life_warnings(policy_data) -> list[str]:
        if getattr(policy_data, "has_defined_life_insurance", False):
            return []
        return [
            "Definition of Life Insurance is not defined for this policy. "
            "Check the issue date and issue state to confirm if this looks accurate."
        ]

    def _on_run_values(self):
        snapshot_case = self._snapshot_case
        if snapshot_case is not None:
            # Saved-case view: project the FROZEN snapshot — no DB2.
            policy_number = snapshot_case.policy_number
            region = snapshot_case.region or self._current_region or "CKPR"
            company_code = snapshot_case.company_code
        elif not self._policy or not self._policy.exists:
            QMessageBox.information(self, "Run Values", "Load a policy before running illustrated values.")
            return
        else:
            policy_number = self._policy_info.get("PolicyNumber", self._policy.policy_number)
            region = self._policy_info.get("Region", self._current_region or "CKPR")
            company_code = self._policy_info.get("CompanyCode", self._policy.company_code)

        QApplication.setOverrideCursor(QCursor(Qt.CursorShape.WaitCursor))
        self.run_values_btn.setEnabled(False)
        self._show_status(f"Running illustration values for {policy_number}...")
        QApplication.processEvents()

        try:
            if snapshot_case is not None:
                # Each run projects a fresh copy — the engine/scenario must
                # never mutate the case's stored snapshot.
                policy_data = copy.deepcopy(snapshot_case.policy_snapshot)
            else:
                policy_data = build_illustration_data(policy_number, region=region, company_code=company_code)
            scenario = build_illustration_scenario(
                policy_data,
                inforce_overrides=self.inputs_tab.export_inforce_overrides(),
                future_inputs=self.inputs_tab.export_input_set(),
            )
            projection_months = self.inputs_tab.projection_months(scenario.projectable_policy)
            duration_label = self.inputs_tab.projection_duration_label(scenario.projectable_policy)
            self._show_status(f"Running illustration values for {policy_number} {duration_label}...")
            QApplication.processEvents()

            self._last_scenario = scenario

            future_inputs = scenario.future_inputs
            run_options = self.inputs_tab.export_options()
            engine = IllustrationEngine()

            # "Lumpsum to Next Premium": solve FIRST so every later solve (e.g.
            # Prem to Maturity) sees the bridging lumpsum already funding the early
            # months. If the policy would lapse before its next modal premium,
            # solve a bridging lumpsum and layer it in as an unscheduled premium
            # on the forecast date.
            lumpsum_result = None
            if self.inputs_tab.lumpsum_to_next_enabled():
                from suiteview.illustration.core.solve_lumpsum_to_next_premium import (
                    solve_lumpsum_to_next_premium,
                )
                from suiteview.illustration.models.input_set import (
                    DatedTransaction, IllustrationInputSet, TransactionKind,
                )
                lumpsum_result = solve_lumpsum_to_next_premium(
                    scenario.projectable_policy,
                    base_future_inputs=future_inputs,
                    base_options=run_options,
                    engine=engine,
                )
                if lumpsum_result is not None and lumpsum_result.lumpsum > 0:
                    dated = list(future_inputs.dated_transactions)
                    dated.append(DatedTransaction(
                        kind=TransactionKind.PREMIUM,
                        effective_date=lumpsum_result.forecast_date,
                        amount=lumpsum_result.lumpsum,
                        subtype="lumpsum_to_next_premium"))
                    future_inputs = IllustrationInputSet(
                        scheduled_transactions=list(future_inputs.scheduled_transactions),
                        dated_transactions=dated,
                        policy_changes=list(future_inputs.policy_changes))
                    self.inputs_tab.set_lumpsum_amount(lumpsum_result.lumpsum)
                else:
                    # No bridge was needed — show 0 so the disabled field reads
                    # as "solved, nothing required" rather than blank.
                    self.inputs_tab.set_lumpsum_amount(0.0)

            # "Max Level" premium type: solve the largest level premium
            # the guideline acceptance chain never caps, on the real projection —
            # so a Face Amount or DB Option change's effect on the guideline
            # premiums (GLP/GSP recalc, AccumGLP stream) is reflected, including
            # the final GSP/AccumGLP at age 100 and any tighter mid-projection
            # point a guideline drop creates. The row's instant closed-form
            # estimate is replaced by the solved amount, and the premium is
            # layered in from its start year under the same guideline basis the
            # solver used (or the premium won't behave as solved).
            max_level = self.inputs_tab.max_level_request()
            if max_level is not None:
                from suiteview.illustration.core.solve_level_to_exception import (
                    level_to_exception_options,
                )
                from suiteview.illustration.core.solve_max_level_allowed import (
                    MaxLevelAllowedError, solve_max_level_allowed,
                )
                from suiteview.illustration.models.input_set import (
                    IllustrationInputSet, ScheduledTransaction, TransactionKind,
                )
                allow_exceptions = bool(run_options.allow_exception_prems)
                try:
                    mla = solve_max_level_allowed(
                        scenario.projectable_policy,
                        mode=max_level["mode"],
                        start_policy_year=max_level["start_year"],
                        base_future_inputs=future_inputs,
                        allow_exceptions=allow_exceptions,
                        base_options=run_options,
                        engine=engine)
                except MaxLevelAllowedError as exc:
                    QApplication.restoreOverrideCursor()
                    self.run_values_btn.setEnabled(True)
                    self.inputs_tab.set_max_level_amount(None)
                    QMessageBox.information(self, "Max Level", str(exc))
                    self._show_status(str(exc))
                    return
                sched = list(future_inputs.scheduled_transactions)
                sched.append(ScheduledTransaction(
                    kind=TransactionKind.PREMIUM,
                    policy_year=int(max_level["start_year"]),
                    amount=mla.premium, mode=mla.mode))
                # Premiums stop at age 100 — AccumGLP freezes there, so any
                # later payment would always be capped (mirrors the solver's
                # own schedule).
                policy_for_stop = scenario.projectable_policy
                if policy_for_stop.maturity_age > 100:
                    sched.append(ScheduledTransaction(
                        kind=TransactionKind.PREMIUM,
                        policy_year=100 - int(policy_for_stop.issue_age or 0) + 1,
                        amount=0.0, mode="A"))
                future_inputs = IllustrationInputSet(
                    scheduled_transactions=sched,
                    dated_transactions=list(future_inputs.dated_transactions),
                    policy_changes=list(future_inputs.policy_changes))
                run_options = level_to_exception_options(run_options, allow_exceptions)
                self.inputs_tab.set_max_level_amount(mla.premium)

            # "Prem to Maturity" premium type: solve the minimum level
            # premium that keeps the policy in force to maturity, honoring the
            # prior premium rows AND any lumpsum already merged into future_inputs
            # above, then layer it on top from its start year under the same
            # guideline + exception basis the solver used (or the premium won't
            # behave as solved). Other modes run as the user configured them.
            min_level = self.inputs_tab.min_level_request()
            if min_level is not None:
                from suiteview.illustration.core.solve_level_to_exception import (
                    LevelToExceptionError, level_to_exception_options,
                    solve_level_to_exception,
                )
                from suiteview.illustration.models.input_set import (
                    IllustrationInputSet, ScheduledTransaction, TransactionKind,
                )
                # On GPT policies Prem to Maturity ALWAYS allows GP exception
                # premiums — the solve rides the GLP exception period when the
                # guideline caps further funding, regardless of the Allow GP
                # Exception Premium checkbox (which still governs INPUT-premium
                # runs and Max Level). CVAT policies have no guideline cap or
                # exception machinery, so they solve (and display) with
                # exceptions off. The displayed run below inherits the same
                # basis via level_to_exception_options, or the solved premium
                # wouldn't behave as solved.
                allow_exceptions = not scenario.projectable_policy.is_cvat
                try:
                    lte = solve_level_to_exception(
                        scenario.projectable_policy,
                        mode=min_level["mode"],
                        start_policy_year=min_level["start_year"],
                        base_future_inputs=future_inputs,
                        allow_exceptions=allow_exceptions,
                        base_options=run_options)
                except LevelToExceptionError as exc:
                    QApplication.restoreOverrideCursor()
                    self.run_values_btn.setEnabled(True)
                    self.inputs_tab.set_min_level_amount(None)
                    QMessageBox.information(self, "Prem to Maturity", str(exc))
                    self._show_status(str(exc))
                    return
                sched = list(future_inputs.scheduled_transactions)
                sched.append(ScheduledTransaction(
                    kind=TransactionKind.PREMIUM,
                    policy_year=int(min_level["start_year"]),
                    amount=lte.premium, mode=lte.mode))
                future_inputs = IllustrationInputSet(
                    scheduled_transactions=sched,
                    dated_transactions=list(future_inputs.dated_transactions),
                    policy_changes=list(future_inputs.policy_changes))
                # CVAT solves with TAMRA conformance off (the CVAT TAMRA cap
                # rides on the unmodeled NPT premium) — the displayed run must
                # match the solve's basis.
                run_options = level_to_exception_options(
                    run_options, allow_exceptions,
                    conform_to_tamra=not scenario.projectable_policy.is_cvat)
                self.inputs_tab.set_min_level_amount(lte.premium)

            # "Prem to Shadow Maturity" premium type: solve the minimum level
            # premium that keeps the SHADOW account in force to maturity — the
            # shadow account governs lapse once past the safety-net period, so
            # the regular account value may run negative while the policy stays
            # in force. The shadow account blocks GP exception premiums, so the
            # solve (and its displayed run) uses exceptions off.
            shadow_level = self.inputs_tab.shadow_level_request()
            if shadow_level is not None:
                from suiteview.illustration.core.solve_level_to_exception import (
                    LevelToExceptionError, level_to_exception_options,
                    solve_level_to_exception,
                )
                from suiteview.illustration.models.input_set import (
                    IllustrationInputSet, ScheduledTransaction, TransactionKind,
                )
                shadow_policy = scenario.projectable_policy
                if not shadow_policy.has_shadow_account:
                    QApplication.restoreOverrideCursor()
                    self.run_values_btn.setEnabled(True)
                    self.inputs_tab.set_shadow_level_amount(None)
                    if getattr(shadow_policy, "ccv_ceased", False):
                        msg = ("Prem to Shadow Maturity cannot run: this policy's "
                               "shadow account benefit (type A) has ceased, so the "
                               "shadow account no longer governs lapse.")
                    else:
                        msg = ("Prem to Shadow Maturity cannot run: this policy has "
                               "no shadow account benefit (type A).")
                    QMessageBox.information(self, "Prem to Shadow Maturity", msg)
                    self._show_status(msg)
                    return
                allow_exceptions = False
                try:
                    slte = solve_level_to_exception(
                        shadow_policy,
                        mode=shadow_level["mode"],
                        start_policy_year=shadow_level["start_year"],
                        base_future_inputs=future_inputs,
                        allow_exceptions=allow_exceptions,
                        base_options=run_options)
                except LevelToExceptionError:
                    QApplication.restoreOverrideCursor()
                    self.run_values_btn.setEnabled(True)
                    self.inputs_tab.set_shadow_level_amount(None)
                    msg = ("No level premium keeps the shadow account in force "
                           "to maturity (the guideline premium cap limits what "
                           "can be paid in).")
                    QMessageBox.information(self, "Prem to Shadow Maturity", msg)
                    self._show_status(msg)
                    return
                sched = list(future_inputs.scheduled_transactions)
                sched.append(ScheduledTransaction(
                    kind=TransactionKind.PREMIUM,
                    policy_year=int(shadow_level["start_year"]),
                    amount=slte.premium, mode=slte.mode))
                future_inputs = IllustrationInputSet(
                    scheduled_transactions=sched,
                    dated_transactions=list(future_inputs.dated_transactions),
                    policy_changes=list(future_inputs.policy_changes))
                # Same basis note as Prem to Maturity: CVAT solves with TAMRA
                # conformance off, and the displayed run must match the solve.
                run_options = level_to_exception_options(
                    run_options, allow_exceptions,
                    conform_to_tamra=not shadow_policy.is_cvat)
                self.inputs_tab.set_shadow_level_amount(slte.premium)

            # "Solve" premium type: solve the minimum level premium that
            # carries the chosen value (Account / Surrender / Shadow Account
            # Value) to the target amount at the target age (beginning-of-year
            # age → the prior year's month-12 ending value). Solved under the
            # SAME run options as the displayed run, honoring the prior
            # premium rows / lumpsum / policy changes already merged into
            # future_inputs. An unreachable target reports instead of running.
            solve_req = self.inputs_tab.solve_request()
            if solve_req is not None:
                from suiteview.illustration.core.solve_premium_to_target import (
                    PremiumTargetError, TARGET_FIELDS, solve_premium_to_target,
                )
                from suiteview.illustration.models.input_set import (
                    IllustrationInputSet, ScheduledTransaction, TransactionKind,
                )

                def _solve_stop(message: str):
                    QApplication.restoreOverrideCursor()
                    self.run_values_btn.setEnabled(True)
                    self.inputs_tab.set_solve_amount(None)
                    QMessageBox.information(self, "Premium Solve", message)
                    self._show_status(message)

                if solve_req["amount"] is None or solve_req["at_age"] is None:
                    _solve_stop(
                        "Enter the Premium Solve criteria first — the target "
                        "Amount and the At Age (beginning-of-year age) in the "
                        "Solve group under the Premiums section.")
                    return
                try:
                    pts = solve_premium_to_target(
                        scenario.projectable_policy,
                        target=solve_req["target"],
                        amount=solve_req["amount"],
                        at_age=solve_req["at_age"],
                        mode=solve_req["mode"],
                        start_policy_year=solve_req["start_year"],
                        end_policy_year=solve_req["end_year"],
                        base_future_inputs=future_inputs,
                        base_options=run_options,
                        engine=engine)
                except PremiumTargetError as exc:
                    _solve_stop(str(exc))
                    return
                sched = list(future_inputs.scheduled_transactions)
                sched.append(ScheduledTransaction(
                    kind=TransactionKind.PREMIUM,
                    policy_year=int(solve_req["start_year"]),
                    amount=pts.premium, mode=pts.mode))
                if solve_req["end_year"] is not None:
                    sched.append(ScheduledTransaction(
                        kind=TransactionKind.PREMIUM,
                        policy_year=int(solve_req["end_year"]) + 1,
                        amount=0.0, mode="A"))
                future_inputs = IllustrationInputSet(
                    scheduled_transactions=sched,
                    dated_transactions=list(future_inputs.dated_transactions),
                    policy_changes=list(future_inputs.policy_changes))
                self.inputs_tab.set_solve_amount(pts.premium)
                target_label = TARGET_FIELDS[pts.target][1]
                self._show_status(
                    f"Premium Solve: {pts.premium:,.2f}/{pts.mode} reaches "
                    f"{target_label} {pts.achieved_value:,.2f} at age "
                    f"{pts.at_age}.")

            # "Pay-off" loan repayment rows: solve the level modal repayment
            # that zeroes the loan by the end of each row's window. Repayments
            # apply before new loans in the month order, so the balance is zero
            # just before any new loan that follows a window. Solved
            # chronologically — a later payoff window sees the earlier one's
            # repayments (and any loans borrowed between them) already layered
            # into the inputs.
            payoff_requests = self.inputs_tab.loan_payoff_requests()
            if payoff_requests:
                from suiteview.illustration.core.solve_loan_payoff import (
                    PAYOFF_SUBTYPE, LoanPayoffError, solve_loan_payoff,
                )
                from suiteview.illustration.models.input_set import (
                    DatedTransaction, IllustrationInputSet, TransactionKind,
                )
                solved_amounts = []
                try:
                    for request in payoff_requests:
                        payoff = solve_loan_payoff(
                            scenario.projectable_policy,
                            repayment_dates=request["dates"],
                            check_date=request["check_date"],
                            base_future_inputs=future_inputs,
                            base_options=run_options,
                            engine=engine)
                        solved_amounts.append(payoff.repayment)
                        if payoff.repayment > 0:
                            dated = list(future_inputs.dated_transactions)
                            dated.extend(DatedTransaction(
                                kind=TransactionKind.LOAN_REPAYMENT,
                                effective_date=when, amount=payoff.repayment,
                                subtype=PAYOFF_SUBTYPE)
                                for when in request["dates"])
                            future_inputs = IllustrationInputSet(
                                scheduled_transactions=list(future_inputs.scheduled_transactions),
                                dated_transactions=dated,
                                policy_changes=list(future_inputs.policy_changes))
                except LoanPayoffError as exc:
                    QApplication.restoreOverrideCursor()
                    self.run_values_btn.setEnabled(True)
                    self.inputs_tab.set_loan_payoff_amounts(
                        [None] * len(payoff_requests))
                    QMessageBox.information(self, "Loan Pay-off", str(exc))
                    self._show_status(str(exc))
                    return
                self.inputs_tab.set_loan_payoff_amounts(solved_amounts)

            results = engine.project(
                scenario.projectable_policy,
                months=projection_months,
                future_inputs=future_inputs,
                options=run_options,
                stop_on_lapse=self.inputs_tab.stop_on_lapse_enabled(),
            )

            # Guaranteed side (RERUN LockValues): re-project with guaranteed
            # COIs / interest using the current run's applied cash flows locked
            # in. Non-fatal, but never silent — a failure raises a warning
            # banner on the Values and Report tabs and is logged with its
            # traceback.
            guaranteed_results = None
            guaranteed_error = None
            try:
                from suiteview.illustration.core.guaranteed_projection import (
                    run_guaranteed_projection,
                )
                guaranteed_results = run_guaranteed_projection(
                    scenario.projectable_policy,
                    results,
                    base_options=run_options,
                    base_future_inputs=future_inputs,
                    engine=engine,
                )
            except Exception as exc:
                guaranteed_error = str(exc) or type(exc).__name__
                logger.error(
                    "Guaranteed projection failed for %s: %s",
                    policy_number, guaranteed_error, exc_info=True)

            self.values_tab.display_projection(
                scenario.projectable_policy,
                results,
                months=max(len(results) - 1, 0),
                injected_first_row_columns=self._first_row_injected_columns(scenario),
            )
            if guaranteed_results:
                self.values_tab.set_guaranteed_results(
                    scenario.projectable_policy, guaranteed_results)
            elif guaranteed_error:
                self.values_tab.set_guaranteed_failure(guaranteed_error)
            from datetime import date as _date

            from suiteview.illustration.core.report_builder import build_ul_report

            self.report_tab.display_report(build_ul_report(
                scenario.projectable_policy,
                results,
                options=run_options,
                future_inputs=future_inputs,
                run_date=_date.today(),
                guaranteed_results=guaranteed_results,
            ), guaranteed_error=guaranteed_error)
            self.tabs.setCurrentWidget(self.values_tab)
            status = (
                f"Values ready for {policy_number} - valuation snapshot plus "
                f"{max(len(results) - 1, 0)} projected months"
            )
            if snapshot_case is not None:
                status += (
                    f"  ·  Saved case '{snapshot_case.name}' — policy data "
                    f"as of {format_saved_stamp(snapshot_case.saved_at)}")
            if guaranteed_error:
                status += f"  ·  Guaranteed values unavailable: {guaranteed_error}"
            if lumpsum_result is not None and lumpsum_result.lumpsum > 0:
                from suiteview.polview.ui.formatting import format_amount, format_date
                reason = {"SV": "surrender-value", "AV": "account-value-less-loans",
                          "SNET": "safety-net"}.get(
                              lumpsum_result.binding_reason, lumpsum_result.binding_reason)
                status += (
                    f"  ·  Applied a {format_amount(lumpsum_result.lumpsum)} lumpsum on "
                    f"{format_date(lumpsum_result.forecast_date)} to carry the policy to its "
                    f"next premium on {format_date(lumpsum_result.next_premium_date)} "
                    f"(sized by the {reason} shortfall)."
                )
                if lumpsum_result.guideline_limited:
                    QMessageBox.warning(
                        self, "Lumpsum to Next Premium",
                        f"The 7702 guideline limited the bridging premium to "
                        f"{format_amount(lumpsum_result.applied)}, which cannot carry the "
                        f"policy to its next premium on "
                        f"{format_date(lumpsum_result.next_premium_date)} on premium alone.\n\n"
                        f"Enable Allow GP Exception Premium to bridge the remaining gap."
                    )
            self._show_status(status)
        except Exception as exc:
            QMessageBox.critical(self, "Run Values", f"Failed to run illustration values: {exc}")
            self._show_status(f"Run Values failed: {exc}")
        finally:
            self.run_values_btn.setEnabled(True)
            QApplication.restoreOverrideCursor()

    @staticmethod
    def _first_row_injected_columns(scenario) -> set[str]:
        columns: set[str] = set()
        overrides = getattr(scenario, "inforce_overrides", None)
        if not overrides or overrides.is_empty():
            return columns

        if overrides.account_value is not None:
            columns.add("Account Value")
        if overrides.face_amount is not None:
            columns.add("Face Amount")
        if overrides.regular_loan_principal is not None or overrides.regular_loan_accrued is not None:
            columns.add("RegLn Total")
            columns.add("Advance - Rg Ln Princ/Total")
            columns.add("Advance - Rg Ln Int Accrued")
            columns.add("Rg Ln Princ")
            columns.add("Rg Ln Int")
            columns.add("PolicyDebt")
        if overrides.preferred_loan_principal is not None or overrides.preferred_loan_accrued is not None:
            columns.add("PrefLn Total")
            columns.add("Advance - Pf Ln Princ/Total")
            columns.add("Advance - Pf Ln Int Accrued")
            columns.add("Pf Ln Princ")
            columns.add("Pf Ln Int")
            columns.add("PolicyDebt")
        if overrides.variable_loan_principal is not None or overrides.variable_loan_accrued is not None:
            columns.add("Varln Total")
            columns.add("Advance - Var Ln Princ/Total")
            columns.add("Advance - Var Ln Int Accrued")
            columns.add("Var Ln Princ")
            columns.add("Var Ln Int")
            columns.add("PolicyDebt")
        return columns

    def moveEvent(self, event):
        super().moveEvent(event)
        if hasattr(self, "policy_list_window"):
            self.policy_list_window.follow_parent()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if hasattr(self, "policy_list_window"):
            self.policy_list_window.follow_parent()

    def closeEvent(self, event):
        if hasattr(self, "policy_list_window") and self.policy_list_window.isVisible():
            self.policy_list_window.hide()
        if self._db:
            self._db.close()
            self._db = None
        event.accept()
