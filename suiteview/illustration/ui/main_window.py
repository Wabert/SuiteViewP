"""Main window for the SuiteView Illustration app."""

import copy
import logging
from typing import Optional

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QAction, QCursor
from PyQt6.QtWidgets import (
    QApplication,
    QHBoxLayout,
    QLabel,
    QMenu,
    QMessageBox,
    QPushButton,
    QSizePolicy,
    QStackedWidget,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from suiteview.core.build_env import is_distribution_build
from suiteview.ui.access_control import requires_app_access
from suiteview.ui.signals import muted_signals
from suiteview.core.db2_connection import DB2Connection
from suiteview.core.odbc_utils import is_password_error
from suiteview.illustration.api import load_policy_data, project_policy
from suiteview.illustration.core.illustration_policy_service import (
    coverage_segment_data_warnings,
)
from suiteview.illustration.core.rate_loader import RateLookupError, load_rates
from suiteview.illustration.core.rate_validation import missing_required_rate_warnings
from suiteview.illustration.core.run_service import (
    PolicyBasis,
    RunControls,
    RunFlowError,
    RunRequest,
    RunResult,
    SolveRequestSet,
    SolvedInputs,
    execute_run,
)
from suiteview.illustration.core.run_input_compiler import (
    clear_rollback_draft,
    compile_input_set,
    compile_options,
)
from suiteview.illustration.core.scenario_builder import build_illustration_scenario
from suiteview.illustration.models.plancode_config import load_plancode
from suiteview.illustration.models.input_set import RollbackOverrideSet
from suiteview.illustration.core.value_rollback import available_rollback_dates
from suiteview.polview.models.policy_information import PolicyInformation
from suiteview.polview.ui.formatting import format_amount, format_date
from suiteview.polview.ui.widgets import PolicyLookupBar
from suiteview.ui.widgets.frameless_window import FramelessWindowBase

from suiteview.illustration.models.case_store import CaseStoreError
from suiteview.illustration.models.calc_state import MonthlyState
from suiteview.illustration.models.app_settings import get_illustration_settings

from .case_controls import CasesController
from .imported_case_controls import ImportedCasesController
from .inputs_tab import IllustrationInputsTab
from .policy_list import IllustrationPolicyListWindow
from .presenter import IllustrationPresenter, IllustrationSessionState
from .policy_tab import IllustrationPolicyTab
from .compare_tab import IllustrationCompareTab
from .report_tab import IllustrationReportTab
from .saved_cases_panel import format_saved_stamp
from .tips import RerunTipsDialog
from .values_tab import IllustrationValuesTab
from .value_rollback import (
    ROLLBACK_COLORS, ROLLBACK_NOTICE_STYLE, ValueRollbackControls,
)
from .styles import (
    GOLD_TEXT,
    HEADER_MENU_BUTTON_STYLE,
    HEADER_MENU_STYLE,
    HEADER_PANEL_BUTTON_STYLE,
    ILLUSTRATION_BORDER_COLOR,
    ILLUSTRATION_HEADER_COLORS,
    ILLUSTRATION_ISSUE_HEADER_COLORS,
    ILLUSTRATION_SNAPSHOT_HEADER_COLORS,
    ISSUE_BLUE_BG,
    ISSUE_TAB_WIDGET_STYLE,
    PURPLE_BG,
    STATUS_BAR_STYLE,
    TAB_WIDGET_STYLE,
    VALUE_BUTTON_STYLE,
)

logger = logging.getLogger(__name__)

WINDOW_TITLE = "SuiteView:  RERUN"


class IllustrationWindow(FramelessWindowBase):
    """PolView-style shell for Illustration."""

    def __init__(self, parent=None, initial_policy: str = "",
                 initial_region: str = "CKPR", initial_company: str = ""):
        from suiteview.core.access_control import guard_app_access
        guard_app_access("RERUN")
        self._db: Optional[DB2Connection] = None
        self._policy: Optional[PolicyInformation] = None
        self._current_policy = None
        self._current_region = None
        self._where_clause = None
        self._policy_info = {}
        self._polview_launcher = None
        self._policy_cache: dict = {}
        self._list_panel_visible = False
        self._last_scenario = None
        self._illustration_data = None
        self._live_policy_checks: tuple[
            PolicyInformation, list[str], MonthlyState | None
        ] | None = None
        self._rollback_projection_blocked = False
        self._record_drafts_pending = False
        # Per-policy session state, keyed like _policy_cache by
        # (policy_number, region, company_code). Each entry stores plain input
        # drafts plus values/report/status snapshots, so policy-list switching
        # restores everything without retaining live widgets or re-running.
        # Clicking Get deliberately replaces that state with fresh policy
        # defaults. Session-only: never persisted to disk.
        self._session_states: dict[tuple, IllustrationSessionState] = {}
        self._presenter = IllustrationPresenter()
        self._current_key: tuple | None = None
        self._default_inputs_on_next_get = False
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

        self.open_polview_btn = QPushButton("PolView")
        self.open_polview_btn.setToolTip("Open this policy in PolView")
        self.open_polview_btn.setEnabled(False)
        self.open_polview_btn.setStyleSheet(HEADER_PANEL_BUTTON_STYLE)

        # "Options" header menu (toolbar-style drop-down). Holds app-wide
        # toggles that apply across the whole Illustration app — not per
        # policy/case. Built before super().__init__ so FramelessWindowBase can
        # place it in the title bar via header_widgets.
        self._build_options_menu()

        self.tips_btn = QPushButton("Tips")
        self.tips_btn.setStyleSheet(HEADER_MENU_BUTTON_STYLE)
        self.tips_btn.setToolTip(
            "Hidden-ish features: right-click menus, hidden tabs, drag & drop")
        self._tips_dialog: Optional[RerunTipsDialog] = None

        super().__init__(
            title=WINDOW_TITLE,
            default_size=(1200, 825),
            min_size=(500, 420),
            parent=parent,
            header_colors=ILLUSTRATION_HEADER_COLORS,
            border_color=ILLUSTRATION_BORDER_COLOR,
            header_widgets=[
                self.open_polview_btn,
                self.options_btn,
                self.tips_btn,
                self.list_toggle_btn,
            ],
        )
        self.open_polview_btn.clicked.connect(self._open_in_polview)
        self.tips_btn.clicked.connect(self.show_tips)
        self.list_toggle_btn.clicked.connect(self._toggle_list_panel)
        get_illustration_settings().abr_quote_mode_changed.connect(
            self._refresh_rollback_controls)
        get_illustration_settings().rollback_enabled_changed.connect(
            self._on_rollback_option_changed)
        self._normal_header_button_styles = [
            (button, button.styleSheet())
            for button in self.header_bar.findChildren(QPushButton)
            if button in (self.options_btn, self.tips_btn)
            or button.toolTip() in {"Minimize", "Maximize", "Close"}
        ]
        self._refresh_rollback_controls()

        # Optionally pull in a policy on open (e.g. launched from the taskbar
        # policy bar or PolView's "Open in Illustrator" button).
        if initial_policy:
            self.load_policy(initial_policy, region=initial_region,
                             company_code=initial_company)

    def _build_options_menu(self):
        """Build the "Options" header drop-down and its app-wide toggles.
        Styled like the SuiteView taskbar's "Tools" menu — plain gold text you
        click, with a purple-themed drop-down."""
        self.options_btn = QPushButton("Options")
        self.options_btn.setStyleSheet(HEADER_MENU_BUTTON_STYLE)
        self.options_btn.setToolTip("Application options")

        menu = QMenu(self.options_btn)
        menu.setStyleSheet(HEADER_MENU_STYLE)

        settings = get_illustration_settings()
        self._additional_premium_types_action = QAction(
            "Additional Premium Types", menu, checkable=True)
        self._additional_premium_types_action.setChecked(
            settings.additional_premium_types)
        self._additional_premium_types_action.setToolTip(
            "Offer the advanced premium types (Billable to MD, Max Level, "
            "Monthly Deduction) in the Premium Type dropdown")
        self._additional_premium_types_action.toggled.connect(
            self._on_additional_premium_types_toggled)
        menu.addAction(self._additional_premium_types_action)

        self._testing_mode_action = QAction(
            "Testing Mode", menu, checkable=True)
        self._testing_mode_action.setChecked(settings.testing_mode)
        self._testing_mode_action.setToolTip(
            "Reveal testing-only controls — the Values Overview's Export "
            "Summary button and its folder picker")
        self._testing_mode_action.toggled.connect(
            self._on_testing_mode_toggled)
        menu.addAction(self._testing_mode_action)

        self._abr_quote_action = QAction(
            "ABR Quote", menu, checkable=True)
        self._abr_quote_action.setChecked(settings.abr_quote_mode)
        self._abr_quote_action.setToolTip(
            "Solve the theoretical annual level premium that carries the policy "
            "to maturity with a $1,000 surrender value at the entered Illustrated "
            "Rate. Locks every Input-tab control except the Illustrated Rate; the "
            "Report tab explains the solve instead of showing an illustration.")
        self._abr_quote_action.toggled.connect(self._on_abr_quote_mode_toggled)
        menu.addAction(self._abr_quote_action)

        self._rollback_action = QAction("Edit Record", menu, checkable=True)
        self._rollback_action.setChecked(settings.rollback_enabled)
        self._rollback_action.setToolTip(
            "Enable valuation-date selection and editable policy-record assumptions. "
            "Turning this off restores loaded values and removes valuation edits.")
        self._rollback_action.toggled.connect(settings.set_rollback_enabled)
        menu.addAction(self._rollback_action)

        self.options_btn.setMenu(menu)

    def show_tips(self):
        """Open (or raise) the non-modal RERUN Tips cheat-sheet."""
        if self._tips_dialog is None:
            self._tips_dialog = RerunTipsDialog(self)
        self._tips_dialog.show()
        self._tips_dialog.raise_()
        self._tips_dialog.activateWindow()

    def _on_rollback_option_changed(self, enabled: bool):
        with muted_signals(self._rollback_action):
            self._rollback_action.setChecked(enabled)
        if not enabled:
            if self.inputs_tab.export_rollback_overrides() is not None:
                self.inputs_tab.set_value_rollback(None)
            self._clear_rollback_session_states()
        self._refresh_policy_basis()
        self._on_run_from_issue_changed(self.inputs_tab.run_from_issue_enabled())
        self._refresh_rollback_controls()

    def _clear_rollback_session_states(self) -> None:
        """Remove inactive Edit Record drafts and invalidate their outputs."""

        for session in self._session_states.values():
            if session.input_draft is not None:
                session.input_draft = clear_rollback_draft(session.input_draft)
            session.values = None
            session.report = None
            session.status = None
            session.scenario = None

    def _on_additional_premium_types_toggled(self, checked: bool):
        """Flip the app-wide Additional Premium Types option. Every open
        policy/case's Premium Type dropdown re-syncs via the settings signal."""
        get_illustration_settings().set_additional_premium_types(checked)

    def _on_testing_mode_toggled(self, checked: bool):
        """Flip the app-wide Testing Mode option. The Values Overview's Export
        Summary controls show/hide via the settings signal."""
        get_illustration_settings().set_testing_mode(checked)

    def _on_abr_quote_mode_toggled(self, checked: bool):
        """Flip the app-wide ABR Quote option. Every open policy's Inputs tab
        locks/unlocks its controls via the settings signal."""
        get_illustration_settings().set_abr_quote_mode(checked)

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

    def set_polview_launcher(self, launcher):
        """Register the shared PolView policy launcher supplied by the taskbar."""
        self._polview_launcher = launcher

    @requires_app_access("POLVIEW")
    def _open_in_polview(self, checked=False):
        """Open the currently loaded policy in PolView."""
        if not self._current_policy:
            return
        region = self._current_region or "CKPR"
        company = str((self._policy_info or {}).get("CompanyCode", "") or "")
        if self._polview_launcher is not None:
            self._polview_launcher(self._current_policy, region, company)
            return

        from suiteview.polview.ui.main_window import GetPolicyWindow

        self._polview_window = GetPolicyWindow(
            initial_policy=self._current_policy,
            initial_region=region,
            initial_company=company,
        )
        self._polview_window.show()

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
        self.lookup_bar.get_button.pressed.connect(
            self._mark_next_get_for_default_inputs)

        self.run_values_btn = QPushButton("Run Values")
        self.run_values_btn.setStyleSheet(
            VALUE_BUTTON_STYLE
            + "QPushButton:disabled { background: #DDD6D0; color: #777; border-color: #AAA; }")
        self.run_values_btn.setEnabled(False)
        self.run_values_btn.setFixedHeight(28)
        self.run_values_btn.clicked.connect(self._on_run_values)
        self.lookup_bar.layout().addSpacing(8)
        self.lookup_bar.layout().addWidget(self.run_values_btn)

        # Saved cases: persist named input scenarios (plus a frozen policy
        # snapshot) to disk (~/.suiteview/data/illustration/cases) and reload them
        # across sessions. Save lives here; browsing/loading/rename/delete
        # live in the Saved Cases panel (header toggle).
        self._cases_controller = CasesController(
            self, on_cases_changed=self._refresh_saved_cases)
        # Imported cases: a separate on-disk collection loaded/dropped from
        # files, browsed in the List panel's Imported Cases view.
        self._imported_controller = ImportedCasesController(
            self, on_changed=self._refresh_imported_cases)
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

        self.projection_mode_notice = QLabel(
            "INFORCE | Projection starts after the loaded valuation date.")
        self.projection_mode_notice.setWordWrap(True)
        self.projection_mode_notice.setStyleSheet(
            "color: #2A1458; background: #EDE7F6; padding: 5px 12px; font-weight: bold;")
        basis_row = QHBoxLayout()
        basis_row.setContentsMargins(0, 0, 0, 0)
        basis_row.addWidget(self.projection_mode_notice, 1)
        self.rollback_controls = ValueRollbackControls()
        self.rollback_controls.update_requested.connect(self._on_rollback_update)
        basis_row.addWidget(self.rollback_controls)
        main_layout.addLayout(basis_row)

        self.tabs_container = QWidget()
        self.tabs_container.setStyleSheet(f"background-color: {PURPLE_BG};")
        tabs_layout = QVBoxLayout(self.tabs_container)
        tabs_layout.setContentsMargins(10, 10, 10, 10)
        tabs_layout.setSpacing(10)

        self.tabs = QTabWidget()
        self.tabs.setStyleSheet(TAB_WIDGET_STYLE)
        self.policy_tab = IllustrationPolicyTab()
        self.policy_tab.rollback_amount_requested.connect(self._on_rollback_amount)
        self.policy_tab.rollback_dbo_requested.connect(self._on_rollback_dbo)
        self.policy_tab.rollback_shadow_requested.connect(self._on_rollback_shadow)
        self.policy_tab.rollback_account_requested.connect(self._on_rollback_account)
        self.policy_tab.record_value_requested.connect(self._on_record_value)
        self.policy_tab.record_funds_requested.connect(self._on_record_funds)
        self.policy_tab.record_drafts_changed.connect(self._on_record_drafts_changed)
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
        main_layout.addWidget(self.tabs_container, 1)

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
        cases_view.cases_export_requested.connect(
            self._cases_controller.export_flow)

        # Imported Cases view (third page of the panel's toggle): import,
        # activation, remove, and export route to the imported controller.
        imported_view = self.policy_list_window.imported_view
        imported_view.import_requested.connect(
            self._imported_controller.pick_and_import)
        imported_view.case_activated.connect(
            self._imported_controller.activate_case)
        imported_view.cases_remove_requested.connect(
            self._imported_controller.remove_cases)
        imported_view.bundles_remove_requested.connect(
            self._imported_controller.remove_bundles)
        imported_view.cases_export_requested.connect(
            self._imported_controller.export_cases)
        # A file dropped anywhere on the List panel imports it.
        self.policy_list_window.case_files_dropped.connect(
            self._imported_controller.import_files)

    def _refresh_saved_cases(self):
        if hasattr(self, "policy_list_window"):
            self.policy_list_window.refresh_cases()

    def _refresh_imported_cases(self):
        if hasattr(self, "policy_list_window"):
            self.policy_list_window.refresh_imported()

    def _toggle_list_panel(self):
        self._list_panel_visible = not self._list_panel_visible
        if self._list_panel_visible:
            self.policy_list_window.show_panel()
        else:
            self.policy_list_window.hide()
        self.list_toggle_btn.setChecked(self._list_panel_visible)

    def _on_policy_selected_from_list(self, region: str, company: str, policy: str):
        if not self.isVisible():
            self.show()
        self._default_inputs_on_next_get = False
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
        """Forget a policy's session inputs/values."""
        self._session_states.pop(key, None)

    def _registered_inputs_tabs(self) -> set:
        return {self.inputs_tab}

    def _set_active_inputs_tab(self, inputs_tab):
        """Front the given inputs widget; delete the outgoing one if no
        session entry owns it (the startup placeholder or a removed policy)."""
        previous = self.inputs_tab
        if not inputs_tab.property("issueModeSignalConnected"):
            inputs_tab.run_from_issue_changed.connect(
                lambda enabled, tab=inputs_tab: self._on_run_from_issue_changed(
                    enabled, tab, invalidate=True))
            inputs_tab.issue_conditions_changed.connect(
                lambda tab=inputs_tab: self._invalidate_issue_results(tab))
            inputs_tab.rollback_changed.connect(
                lambda tab=inputs_tab: self._on_rollback_changed(tab))
            inputs_tab.setProperty("issueModeSignalConnected", True)
        if inputs_tab is previous:
            self._on_run_from_issue_changed(inputs_tab.run_from_issue_enabled(), inputs_tab)
            self._refresh_rollback_controls()
            return
        if self._inputs_stack.indexOf(inputs_tab) == -1:
            self._inputs_stack.addWidget(inputs_tab)
        self.inputs_tab = inputs_tab
        self._inputs_stack.setCurrentWidget(inputs_tab)
        if previous is not None and previous not in self._registered_inputs_tabs():
            self._inputs_stack.removeWidget(previous)
            previous.deleteLater()
        self._on_run_from_issue_changed(inputs_tab.run_from_issue_enabled(), inputs_tab)

    def _on_run_from_issue_changed(self, enabled: bool, source_tab=None, *, invalidate: bool = False):
        if not self._presenter.is_active_inputs_event(self.inputs_tab, source_tab):
            return
        self.tabs_container.setStyleSheet(
            f"background-color: {ISSUE_BLUE_BG if enabled else PURPLE_BG};")
        self.tabs.setStyleSheet(
            ISSUE_TAB_WIDGET_STYLE if enabled else TAB_WIDGET_STYLE)
        self.projection_mode_notice.setText(
            "NEW BUSINESS - FROM ISSUE | Hypothetical issue conditions; current side uses scale 1. "
            "Zero opening balances. Policy tab remains the loaded inforce snapshot."
            if enabled else
            "INFORCE | Projection starts after the loaded valuation date. "
            "At-issue edits do not apply.")
        self.projection_mode_notice.setStyleSheet(
            ("color: white; background: #205B78;" if enabled else
             "color: #2A1458; background: #EDE7F6;")
            + " padding: 5px 12px; font-weight: bold;")
        if invalidate:
            self._invalidate_issue_results()
        self._refresh_rollback_controls()
        self._refresh_rollback_notice()

    def _refresh_projection_header(self, enabled):
        title = WINDOW_TITLE
        if self._snapshot_case is not None:
            title += f" — Case “{self._snapshot_case.name}”"
        if enabled:
            title += " - NEW BUSINESS FROM ISSUE"
        rollback = self.inputs_tab.export_rollback_overrides()
        historical = self._is_historical_selection(rollback)
        if historical:
            title += f" - ROLLBACK {rollback.valuation_date:%m/%d/%Y}"
        elif rollback is not None:
            title += " - EDITED VALUES"
        self.set_title(title)
        self.set_header_colors(
            ROLLBACK_COLORS if historical else
            ILLUSTRATION_ISSUE_HEADER_COLORS if enabled else
            ILLUSTRATION_SNAPSHOT_HEADER_COLORS if self._snapshot_case is not None else
            ILLUSTRATION_HEADER_COLORS)
        for button, style in getattr(self, "_normal_header_button_styles", []):
            button.setStyleSheet(style + (
                "\nQPushButton { color: #4B2274; } QPushButton:hover { color: #351554; }"
                if historical else ""))

    def _refresh_rollback_controls(self, abr_mode=None):
        policy = self._illustration_data
        feature_enabled = get_illustration_settings().rollback_enabled
        rollback = self.inputs_tab.export_rollback_overrides()
        dates = available_rollback_dates(policy) if policy is not None else []
        incompatible = (
            self.inputs_tab.run_from_issue_enabled()
            or (self.inputs_tab.abr_quote_enabled() if abr_mode is None else abr_mode))
        reason = (
            "Inforce mode only" if incompatible else
            "Load a complete policy" if policy is None else "")
        self.rollback_controls.set_basis(
            dates, rollback.valuation_date if rollback else None,
            current_date=policy.valuation_date if policy is not None else None,
            enabled=feature_enabled and not incompatible and policy is not None, reason=reason)
        self.rollback_controls.setVisible(feature_enabled)
        self.policy_tab.set_value_editors_enabled(
            feature_enabled and not incompatible and policy is not None)

    def _is_historical_selection(self, overrides):
        return (
            overrides is not None and self._illustration_data is not None
            and overrides.valuation_date != self._illustration_data.valuation_date)

    def _refresh_rollback_notice(self):
        rollback = self.inputs_tab.export_rollback_overrides()
        if self._is_historical_selection(rollback):
            self.projection_mode_notice.setText(
                f"ROLLBACK | Values as of {rollback.valuation_date:%m/%d/%Y}. "
                + ("Historical shadow required before projection. "
                   if self._rollback_projection_blocked else "")
                + "Review Account/Shadow values, DB Option and coverage Amounts.")
            self.projection_mode_notice.setStyleSheet(ROLLBACK_NOTICE_STYLE)
        elif rollback is not None:
            self.projection_mode_notice.setText(
                "INFORCE | Edited illustration values at the loaded valuation date. "
                "The loaded policy record is unchanged.")
        self._refresh_projection_header(self.inputs_tab.run_from_issue_enabled())

    def _on_rollback_update(self, when):
        if when is None:
            QMessageBox.information(self, "Value Rollback", "Select a recorded monthliversary date.")
            return
        if self._illustration_data is not None and when == self._illustration_data.valuation_date:
            self.policy_tab.reset_fund_edits()
            self._apply_rollback_selection(None)
            return
        prior = self.inputs_tab.export_rollback_overrides()
        overrides = (
            copy.deepcopy(prior) if prior and prior.valuation_date == when
            else RollbackOverrideSet(valuation_date=when))
        self._apply_rollback_selection(overrides)

    def _apply_rollback_selection(self, overrides):
        try:
            self.inputs_tab.set_value_rollback(overrides)
        except ValueError as exc:
            logger.warning("Record edit not applied: %s", exc)
            self._refresh_rollback_controls()
            self._show_status(f"Record edit not applied: {exc}")
            QMessageBox.warning(self, "Record Edit Not Applied", str(exc))
            self._refresh_policy_basis()
            return False
        return True

    def _editable_value_overrides(self):
        if not get_illustration_settings().rollback_enabled:
            QMessageBox.warning(self, "Illustration Values", "Enable Options > Edit Record before editing values.")
            return None
        overrides = self.inputs_tab.export_rollback_overrides()
        if overrides is None:
            if self._illustration_data is None:
                QMessageBox.warning(self, "Illustration Values", "Load a complete policy before editing values.")
                return None
            overrides = RollbackOverrideSet(valuation_date=self._illustration_data.valuation_date)
        return overrides

    def _on_rollback_amount(self, kind, key, amount):
        overrides = self._editable_value_overrides()
        if overrides is None:
            return
        if kind == "coverage":
            overrides.coverage_amounts[key] = amount
        else:
            overrides.benefit_amounts[key] = amount
        self._apply_rollback_selection(overrides)

    def _on_rollback_dbo(self, db_option):
        overrides = self._editable_value_overrides()
        if overrides is None:
            return
        overrides.db_option = db_option
        self._apply_rollback_selection(overrides)

    def _on_rollback_shadow(self, amount):
        overrides = self._editable_value_overrides()
        if overrides is None:
            return
        overrides.shadow_account_value = amount
        self._apply_rollback_selection(overrides)

    def _on_rollback_account(self, amount):
        overrides = self._editable_value_overrides()
        if overrides is None:
            return
        overrides.account_value = amount
        self._apply_rollback_selection(overrides)

    def _on_record_value(self, name, value):
        overrides = self._editable_value_overrides()
        if overrides is None:
            return
        if name.startswith("tamra_7year_contributions."):
            values = list(self.policy_tab._record_snapshot.tamra_7year_contributions)
            values[int(name.rsplit(".", 1)[1])] = value
            overrides.tamra_7year_contributions = values
        else:
            overrides.record_values[name] = value
        self._apply_rollback_selection(overrides)

    def _on_record_funds(self, values):
        overrides = self._editable_value_overrides()
        if overrides is None:
            return
        if "fund_values" in values:
            overrides.fund_values = values["fund_values"]
        if "impaired_fund_values" in values:
            overrides.impaired_fund_values = values["impaired_fund_values"]
        if "premium_allocations" in values:
            overrides.premium_allocations = values["premium_allocations"]
        if self._apply_rollback_selection(overrides):
            self.policy_tab.reset_fund_edits()

    def _on_record_drafts_changed(self, pending):
        cleared = self._record_drafts_pending and not pending
        self._record_drafts_pending = pending
        loaded = self._illustration_data is not None
        self.run_values_btn.setEnabled(loaded and not pending and not self._rollback_projection_blocked)
        self.save_case_btn.setEnabled(loaded and not pending)
        self.compare_tab.setEnabled(not pending)
        if cleared:
            self._show_status("Record values ready - review inputs, then Run Values.")
        self._apply_illustration_gate()

    def _on_rollback_changed(self, source_tab=None):
        if not self._presenter.is_active_inputs_event(self.inputs_tab, source_tab):
            return
        self._refresh_policy_basis()
        self._on_run_from_issue_changed(self.inputs_tab.run_from_issue_enabled(), self.inputs_tab)
        self._apply_illustration_gate()

    def _refresh_policy_basis(self):
        rollback = self.inputs_tab.export_rollback_overrides()
        self._rollback_projection_blocked = False
        if rollback is not None and self._illustration_data is not None:
            policy = build_illustration_scenario(
                self._illustration_data, rollback_overrides=rollback,
                allow_missing_shadow=True).projectable_policy
            self._rollback_projection_blocked = policy.rollback_requires_shadow_value
            self.policy_tab.load_data_from_snapshot(policy)
            self.policy_tab.set_rollback_editing(
                True, policy.db_option,
                account_value=policy.account_value,
                historical=self._is_historical_selection(rollback),
                shadow_value=None if policy.rollback_requires_shadow_value else policy.shadow_account_value)
            if policy.rollback_requires_shadow_value:
                self.policy_tab.fund_values.set_value(
                    "shadow_account_value", "Unavailable - enter historical value")
            self.policy_tab.set_snapshot_banner(
                (f"VALUE ROLLBACK - {policy.valuation_date:%m/%d/%Y}. "
                "Historical values; not the current inforce record.\n"
                "Targets assume unchanged rates/coverage; amount/DB edits do not reconstruct tax limits. "
                "Hover for source details."
                + ("\nEnter the Shadow Account Value below before projecting."
                   if policy.rollback_requires_shadow_value else ""))
                if self._is_historical_selection(rollback) else
                "EDITED ILLUSTRATION VALUES - current valuation date. "
                "The loaded policy record is unchanged. Coverage/DB edits do not reconstruct tax limits.")
            self.policy_tab.snapshot_banner.setToolTip("\n\n".join(
                [*policy.rollback_limitations, *policy.starting_basis_assumptions]))
        elif self._snapshot_case is not None:
            self.policy_tab.load_data_from_snapshot(self._illustration_data)
            self.policy_tab.set_snapshot_banner(
                "Policy data was not retrieved live - effective as of "
                f"{format_saved_stamp(self._snapshot_case.saved_at)}. "
                "Get the policy to return to live data.")
        elif self._policy is not None and self._policy.exists:
            checks = self._live_policy_checks
            warnings, md_check = (
                checks[1:] if checks is not None and checks[0] is self._policy
                else ([], None)
            )
            self.policy_tab.load_data_from_policy(
                self._policy, self._policy_info, md_check=md_check)
            self.policy_tab.set_rate_warnings(warnings)
        elif self._illustration_data is not None:
            self.policy_tab.load_data_from_snapshot(self._illustration_data)
            self.policy_tab.set_snapshot_banner(None)
        if rollback is None and self._illustration_data is not None:
            policy = self._illustration_data
            self.policy_tab.set_rollback_editing(
                not self.inputs_tab.run_from_issue_enabled() and not self.inputs_tab.abr_quote_enabled(),
                policy.db_option, account_value=policy.account_value,
                shadow_value=policy.shadow_account_value)
        if self._illustration_data is not None:
            self.policy_tab.set_record_values(
                policy if rollback is not None else self._illustration_data)
        self.run_values_btn.setEnabled(
            self._illustration_data is not None and not self._rollback_projection_blocked)
        self._on_record_drafts_changed(self.policy_tab.has_pending_record_changes())

    def _invalidate_issue_results(self, source_tab=None):
        if not self._presenter.is_active_inputs_event(self.inputs_tab, source_tab):
            return
        self.values_tab.clear_results(
            "Illustration basis changed. Click Run Values to calculate this scenario.")
        self.report_tab.clear()
        self.compare_tab.clear_results()
        self._last_scenario = None
        self._show_status("Illustration basis changed - review inputs, then Run Values.")

    def _snapshot_active_session(self):
        """Capture the displayed values/report/status for the current policy
        before switching away."""
        entry = self._session_states.get(self._current_key) if self._current_key else None
        if entry is None:
            return
        entry.input_draft = self.inputs_tab.read_draft()
        entry.values = self.values_tab.capture_session_state()
        entry.report = self.report_tab.capture_session_state()
        entry.status = self._status_label.text()
        entry.scenario = self._last_scenario

    def _show_status(self, message: str):
        self._status_label.setText(message)

    def _mark_next_get_for_default_inputs(self):
        self._default_inputs_on_next_get = True

    def _apply_illustration_gate(self) -> bool:
        """DISTRIBUTION-ONLY: if the loaded policy's plancode is flagged
        ``CanIllustrate = False``, disable Run Values and post a persistent
        notice in the status bar. In dev (running from source) this is a no-op,
        so the flag never blocks anything while building/testing.

        Called at the end of every policy/saved-case load. Returns True when
        the policy is blocked (button left disabled). Must run AFTER the load
        path has otherwise enabled the button, so the block wins.
        """
        self.run_values_btn.setText(
            "Shadow Required" if self._rollback_projection_blocked else "Run Values")
        self.run_values_btn.setToolTip(
            "Enter a verified historical Shadow Account Value before projecting."
            if self._rollback_projection_blocked else "Project the selected illustration basis.")
        if self.policy_tab.has_pending_record_changes():
            self.run_values_btn.setEnabled(False)
            self._show_status("Apply or Reset the pending fund/allocation values before Run/Save.")
            return True
        if self._rollback_projection_blocked:
            self.run_values_btn.setEnabled(False)
            self._show_status("Rollback values loaded. Enter a historical shadow amount before Run Values.")
            return True
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
        self.policy_tab.reset_fund_edits()
        default_inputs = self._default_inputs_on_next_get
        self.lookup_bar.hide_company_chooser()
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
                self._load_policy_into_ui(
                    region, cached=True, default_inputs=default_inputs)
                self._default_inputs_on_next_get = False
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
                self._default_inputs_on_next_get = False
                self.run_values_btn.setEnabled(False)
                self.save_case_btn.setEnabled(False)
                self.values_tab.clear_results("Load a policy, then click Run Values.")
                self.report_tab.clear("Load a policy, then click Run Values.")
                # The cleared display no longer belongs to the previous policy;
                # detach so a later snapshot cannot overwrite its saved session.
                self._current_key = None
                self.rollback_controls.set_basis(
                    [], None, enabled=False, reason="Policy not found - reload")
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
            self._load_policy_into_ui(
                region, cached=False, default_inputs=default_inputs)
            self._default_inputs_on_next_get = False

        except Exception as exc:
            self._default_inputs_on_next_get = False
            self.rollback_controls.set_basis(
                [], None, enabled=False, reason="Policy load failed - reload")
            if is_password_error(str(exc)):
                self._show_status(f"{region} connection failed - update your ODBC password and retry")
            else:
                QMessageBox.critical(self, "Error", f"Failed to load policy: {exc}")
                self._show_status(f"Error: {exc}")
        finally:
            QApplication.restoreOverrideCursor()

    def _load_policy_into_ui(
            self, region: str, cached: bool = False,
            default_inputs: bool = False):
        if not self._policy or not self._policy.exists:
            return
        self._snapshot_case = None
        self._rollback_projection_blocked = False
        self._set_live_header_mode()
        self.policy_tab.set_snapshot_notice(None)
        self.policy_tab.set_snapshot_banner(None)
        self.open_polview_btn.setEnabled(True)
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
        self._live_policy_checks = None
        warnings, md_check = self._policy_load_checks(
            policy_number=self._policy_info.get("PolicyNumber", self._policy.policy_number),
            region=region,
            company_code=company_code,
        )
        self._live_policy_checks = (self._policy, warnings, md_check)
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
        if default_inputs and session is not None:
            # Explicit Get is the user's reset-to-live-defaults action. Results
            # must be discarded with the inputs because they describe the old
            # input state.
            self._drop_session_state(key)
            session = None
        inputs_tab = IllustrationInputsTab()
        self._set_active_inputs_tab(inputs_tab)
        inputs_policy = self._illustration_data or self._policy
        inputs_tab.load_data_from_policy(
            inputs_policy,
            has_shadow=bool(getattr(self._illustration_data, "has_shadow_account", False)),
            shadow_ceased=bool(getattr(self._illustration_data, "ccv_ceased", False)))
        if session is None:
            # First visit this session: fresh inputs from the policy, empty values.
            self._session_states[key] = IllustrationSessionState(
                input_draft=inputs_tab.read_draft(),
                policy_data=self._illustration_data,
            )
            self.values_tab.clear_results("Click Run Values to project the selected illustration duration.")
            self.report_tab.clear()
        else:
            # Revisit: render the plain input draft into a fresh widget and
            # re-render values/report from snapshots — no engine run.
            if session.input_draft is not None:
                with muted_signals(inputs_tab):
                    inputs_tab.render_draft(session.input_draft)
                self._on_run_from_issue_changed(
                    inputs_tab.run_from_issue_enabled(), inputs_tab)
            if self.inputs_tab.export_rollback_overrides() is not None:
                self._illustration_data = session.policy_data
            if not self.values_tab.restore_session_state(session.values):
                self.values_tab.clear_results("Click Run Values to project the selected illustration duration.")
            if not self.report_tab.restore_session_state(session.report):
                self.report_tab.clear()
            self._last_scenario = session.scenario

        # Live data on screen — no as-of strip on this policy's inputs tab.
        self.inputs_tab.set_snapshot_notice(None)

        # A different policy invalidates any rendered comparison — clear it so
        # the old policy's results can never sit under the new pickers.
        if self._current_key != key:
            self.compare_tab.clear_results()
        self._current_key = key
        self._refresh_rollback_controls()
        self._refresh_rollback_notice()
        if self.inputs_tab.export_rollback_overrides() is not None:
            self._refresh_policy_basis()
        elif self._illustration_data is not None:
            self._refresh_policy_basis()
        self.run_values_btn.setEnabled(True)
        self.save_case_btn.setEnabled(True)
        load_error = getattr(self, "_illustration_load_error", "")
        if load_error:
            QMessageBox.warning(self, "Illustration Data", load_error)
            self._show_status(load_error)
        elif session is not None and session.status:
            self._show_status(session.status)
        else:
            cache_note = " (cached)" if cached else ""
            self._show_status(f"Loaded policy {self._policy.policy_number} ({company_code}) - {self._policy.status.status_description}{cache_note}")

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
        self._activate_case(case)

    def _activate_case(self, case):
        """Load a SavedCase (from the saved OR imported store) into the tab.

        v2 cases restore their frozen snapshot; v1 cases fall back to a live
        load. Shared by the Saved Cases and Imported Cases panels."""
        if not self.isVisible():
            self.show()
        try:
            if case.policy_snapshot is None:
                self._load_v1_case_against_live(case)
            else:
                self._load_case_snapshot(case)
        except ValueError as exc:
            logger.warning("Invalid illustration case %s: %s", case.name, exc)
            self._invalidate_issue_results()
            self.run_values_btn.setEnabled(False)
            self.save_case_btn.setEnabled(False)
            self._show_status(f"Case could not be applied: {exc}. Reload the policy to continue.")
            QMessageBox.warning(self, "Load Case", str(exc))

    def _load_case_snapshot(self, case):
        """Restore a case's frozen IllustrationPolicyData as the loaded policy."""
        if case.inputs.get("value_rollback") is not None and not get_illustration_settings().rollback_enabled:
            QMessageBox.warning(
                self, "Edit Record Option Required",
                "Enable Options > Edit Record to open this case's valuation assumptions.")
            return
        snapshot = copy.deepcopy(case.policy_snapshot)
        stamp = format_saved_stamp(case.saved_at)
        self.lookup_bar.hide_company_chooser()
        self._snapshot_active_session()

        policy_number = case.policy_number
        region = case.region or snapshot.region or "CKPR"
        company_code = case.company_code or snapshot.company_code or ""
        key = (policy_number, region, company_code)

        # Populate the lookup bar inputs so the loaded case's company/policy are
        # visible (and ready for a live Get) — the snapshot path never fired the
        # Get flow that normally fills these.
        self.lookup_bar.region_input.setText(region)
        self.lookup_bar.company_input.setText(company_code)
        self.lookup_bar.policy_input.setText(policy_number)
        self.lookup_bar.set_policy_display(company_code, policy_number, region)

        self._snapshot_case = case
        self._policy = None            # no live PolicyInformation in this mode
        self._live_policy_checks = None
        self._where_clause = None
        self._current_policy = policy_number
        self._current_region = region
        self._illustration_data = snapshot   # a re-save re-freezes this data
        self._policy_info = {
            "PolicyNumber": policy_number,
            "CompanyCode": company_code,
            "Region": region,
        }
        self.open_polview_btn.setEnabled(True)

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
        inputs_tab = IllustrationInputsTab()
        self._set_active_inputs_tab(inputs_tab)
        self.inputs_tab.load_data_from_policy(
            snapshot,
            has_shadow=bool(snapshot.has_shadow_account),
            shadow_ceased=bool(snapshot.ccv_ceased))
        if session is None:
            session = IllustrationSessionState()
            self._session_states[key] = session
        session.policy_data = snapshot
        # A different policy invalidates any rendered comparison — clear it so
        # the old policy's results can never sit under the new pickers.
        if self._current_key != key:
            self.compare_tab.clear_results()
        self._current_key = key

        warnings = self.inputs_tab.apply_case_inputs(case.inputs)
        session.input_draft = self.inputs_tab.read_draft()
        self._refresh_rollback_controls()
        self._refresh_policy_basis()
        self._refresh_rollback_notice()
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
        self._refresh_projection_header(self.inputs_tab.run_from_issue_enabled())

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
        self._illustration_load_error = ""
        try:
            warnings.extend(coverage_segment_data_warnings(self._policy))
            policy_data = load_policy_data(
                policy_number, region=region, company_code=company_code)
            self._illustration_data = policy_data
            warnings.extend(self._definition_of_life_warnings(policy_data))
            config = load_plancode(policy_data.plancode)
            rates = load_rates(policy_data, config)
            warnings.extend(missing_required_rate_warnings(policy_data, rates))
        except Exception as exc:
            self._illustration_load_error = (
                f"Unable to load illustration data/rates: {exc}")
            warnings.append(self._illustration_load_error)
            return warnings, None

        md_check = None
        try:
            md_check = project_policy(
                policy_data, months=0, rates=rates, config=config).states[0]
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
        if self.policy_tab.has_pending_record_changes():
            QMessageBox.warning(
                self, "Unapplied Record Values",
                "Apply or Reset the pending fund/allocation values before running the illustration.")
            return
        try:
            request = self._read_run_request()
        except RunFlowError as exc:
            QMessageBox.information(self, exc.title, exc.message)
            self._show_status(exc.message)
            return

        QApplication.setOverrideCursor(QCursor(Qt.CursorShape.WaitCursor))
        self.run_values_btn.setEnabled(False)
        self._show_status(f"Running illustration values for {request.basis.policy_number}...")
        QApplication.processEvents()

        try:
            result = execute_run(request)
            if result.duration_label:
                self._show_status(
                    f"Running illustration values for {request.basis.policy_number} "
                    f"{result.duration_label}...")
                QApplication.processEvents()
            for message in result.messages[:-1]:
                self._show_status(message)
                QApplication.processEvents()
            self._last_scenario = result.scenario
            self._apply_solved_inputs(result.solved_inputs)
            self._render_run_result(result)
        except RunFlowError as exc:
            self._clear_solved_field(exc.clear_field)
            QMessageBox.information(self, exc.title, exc.message)
            self._show_status(exc.message)
        except RateLookupError as exc:
            logger.error("Run Values rate lookup failed: %s", exc, exc_info=True)
            QMessageBox.warning(self, "Missing Illustration Rate", str(exc))
            self._show_status(f"Run Values failed: {exc}")
        except Exception as exc:
            logger.exception("Run Values failed: %s", exc)
            QMessageBox.critical(self, "Run Values", f"Failed to run illustration values: {exc}")
            self._show_status(f"Run Values failed: {exc}")
        finally:
            self.run_values_btn.setEnabled(True)
            QApplication.restoreOverrideCursor()

    def _read_run_request(self) -> RunRequest:
        draft = self.inputs_tab.read_draft()
        snapshot_case = self._snapshot_case
        rollback = draft.rollback_overrides
        snapshot_status = ""
        policy_data = None
        if snapshot_case is not None:
            policy_number = snapshot_case.policy_number
            region = snapshot_case.region or self._current_region or "CKPR"
            company_code = snapshot_case.company_code
            policy_data = snapshot_case.policy_snapshot
            snapshot_status = (
                f"Saved case '{snapshot_case.name}' — policy data as of "
                f"{format_saved_stamp(snapshot_case.saved_at)}")
        elif not self._policy or not self._policy.exists:
            raise RunFlowError(
                "Run Values", "Load a policy before running illustrated values.")
        else:
            policy_number = self._policy_info.get("PolicyNumber", self._policy.policy_number)
            region = self._policy_info.get("Region", self._current_region or "CKPR")
            company_code = self._policy_info.get("CompanyCode", self._policy.company_code)
            if rollback is not None:
                policy_data = self._illustration_data

        rollback_status = ""
        if self._is_historical_selection(rollback):
            rollback_status = f"ROLLBACK as of {rollback.valuation_date:%m/%d/%Y}"
        elif rollback is not None:
            rollback_status = "Edited current-valuation assumptions"

        return RunRequest(
            basis=PolicyBasis(
                policy_number=policy_number,
                region=region,
                company_code=company_code,
                policy_data=policy_data,
                snapshot_status=snapshot_status,
            ),
            inputs=compile_input_set(draft),
            controls=RunControls(
                options=compile_options(draft),
                projection_months=None,
                duration_label=None,
                projection_months_for_policy=self.inputs_tab.projection_months,
                duration_label_for_policy=self.inputs_tab.projection_duration_label,
                stop_on_lapse=draft.controls.stop_on_lapse,
                run_from_issue=draft.controls.run_from_issue,
                abr_quote=draft.controls.abr_quote,
                abr_minimum_face_amount=draft.controls.abr_minimum_face_amount,
                rollback_status=rollback_status,
            ),
            solves=SolveRequestSet(
                lumpsum_to_next=draft.lumpsum_to_next,
                max_level=draft.max_level,
                min_level=draft.min_level,
                shadow_level=draft.shadow_level,
                target_premium=draft.target_premium,
                duration=draft.duration,
                loan_payoffs=draft.loan_payoffs,
            ),
            inforce_overrides=draft.inforce_overrides,
            issue_overrides=draft.issue_overrides,
            rollback_overrides=rollback,
        )

    def _apply_solved_inputs(self, solved: SolvedInputs):
        if solved.lumpsum_amount is not None:
            self.inputs_tab.set_lumpsum_amount(solved.lumpsum_amount)
        if solved.max_level_amount is not None:
            self.inputs_tab.set_max_level_amount(solved.max_level_amount)
        if solved.min_level_amount is not None:
            self.inputs_tab.set_min_level_amount(solved.min_level_amount)
        if solved.shadow_level_amount is not None:
            self.inputs_tab.set_shadow_level_amount(solved.shadow_level_amount)
        if solved.target_amount is not None:
            self.inputs_tab.set_solve_amount(solved.target_amount)
        if solved.duration_years is not None:
            self.inputs_tab.set_solve_duration(solved.duration_years)
        if solved.loan_payoff_amounts is not None:
            self.inputs_tab.set_loan_payoff_amounts(solved.loan_payoff_amounts)

    def _clear_solved_field(self, field_name: str | None):
        if field_name == "max_level":
            self.inputs_tab.set_max_level_amount(None)
        elif field_name == "min_level":
            self.inputs_tab.set_min_level_amount(None)
        elif field_name == "shadow_level":
            self.inputs_tab.set_shadow_level_amount(None)
        elif field_name == "target":
            self.inputs_tab.set_solve_amount(None)
        elif field_name == "loan_payoff":
            self.inputs_tab.set_loan_payoff_amounts(
                [None] * len(self.inputs_tab.loan_payoff_requests()))

    def _render_run_result(self, result: RunResult):
        if result.abr_quote is not None:
            from .report_tab import format_abr_quote_pages
            self.values_tab.display_projection(
                result.policy,
                result.current,
                months=max(len(result.current) - 1, 0),
                injected_first_row_columns=self._first_row_injected_columns(result.scenario),
            )
            self.report_tab.display_abr_quote(
                format_abr_quote_pages(result.abr_quote, result.policy))
            self.tabs.setCurrentWidget(self.report_tab)
            self._show_status(result.status)
            return

        scenario = result.scenario
        self.values_tab.display_projection(
            result.policy,
            result.current,
            months=max(len(result.current) - 1, 0),
            injected_first_row_columns=self._first_row_injected_columns(scenario),
        )
        if result.guaranteed:
            self.values_tab.set_guaranteed_results(result.policy, result.guaranteed)
        elif result.report.guaranteed_error:
            self.values_tab.set_guaranteed_failure(result.report.guaranteed_error)
        self.report_tab.display_report(
            result.report.report,
            guaranteed_error=result.report.guaranteed_error,
        )
        self.tabs.setCurrentWidget(self.values_tab)
        self._show_lumpsum_guideline_warning(result.lumpsum_result)
        self._show_status(result.status)

    def _show_lumpsum_guideline_warning(self, lumpsum_result):
        if (
            lumpsum_result is None
            or not getattr(lumpsum_result, "guideline_limited", False)
        ):
            return
        QMessageBox.warning(
            self,
            "Lumpsum to Next Premium",
            "The 7702 guideline limited the bridging premium to "
            f"{format_amount(lumpsum_result.applied)}, which cannot carry the "
            "policy to its next premium on "
            f"{format_date(lumpsum_result.next_premium_date)} on premium alone.\n\n"
            "Enable Allow GP Exception Premium to bridge the remaining gap.",
        )

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
