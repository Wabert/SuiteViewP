"""Main window for the SuiteView Illustration app."""

from typing import Optional

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QCursor
from PyQt6.QtWidgets import QApplication, QLabel, QMessageBox, QPushButton, QSizePolicy, QTabWidget, QVBoxLayout, QWidget

from suiteview.core.db2_connection import DB2Connection
from suiteview.core.odbc_utils import is_password_error
from suiteview.illustration.core.calc_engine import IllustrationEngine
from suiteview.illustration.core.illustration_policy_service import build_illustration_data
from suiteview.illustration.core.scenario_builder import build_illustration_scenario
from suiteview.polview.models.policy_information import PolicyInformation
from suiteview.polview.ui.widgets import PolicyLookupBar
from suiteview.ui.widgets.frameless_window import FramelessWindowBase

from .inputs_tab import IllustrationInputsTab
from .policy_list import IllustrationPolicyListWindow
from .policy_tab import IllustrationPolicyTab
from .report_tab import IllustrationReportTab
from .values_tab import IllustrationValuesTab
from .styles import (
    GOLD_TEXT,
    ILLUSTRATION_BORDER_COLOR,
    ILLUSTRATION_HEADER_COLORS,
    LIST_BUTTON_STYLE,
    PURPLE_BG,
    STATUS_BAR_STYLE,
    TAB_WIDGET_STYLE,
    VALUE_BUTTON_STYLE,
)


class IllustrationWindow(FramelessWindowBase):
    """PolView-style shell for Illustration."""

    def __init__(self, parent=None):
        self._db: Optional[DB2Connection] = None
        self._policy: Optional[PolicyInformation] = None
        self._current_policy = None
        self._current_region = None
        self._where_clause = None
        self._policy_info = {}
        self._policy_cache: dict = {}
        self._history_panel_visible = False
        self._last_scenario = None

        super().__init__(
            title="SuiteView:  Illustration",
            default_size=(1200, 825),
            min_size=(500, 420),
            parent=parent,
            header_colors=ILLUSTRATION_HEADER_COLORS,
            border_color=ILLUSTRATION_BORDER_COLOR,
        )

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

        self.list_toggle_btn = QPushButton("List")
        self.list_toggle_btn.setCheckable(True)
        self.list_toggle_btn.setToolTip("Toggle Policy List panel")
        self.list_toggle_btn.setStyleSheet(LIST_BUTTON_STYLE)
        self.list_toggle_btn.clicked.connect(self._toggle_policy_list)
        self.lookup_bar.layout().addSpacing(6)
        self.lookup_bar.layout().addWidget(self.list_toggle_btn)
        main_layout.addWidget(self.lookup_bar)

        tabs_container = QWidget()
        tabs_container.setStyleSheet(f"background-color: {PURPLE_BG};")
        tabs_layout = QVBoxLayout(tabs_container)
        tabs_layout.setContentsMargins(10, 10, 10, 10)
        tabs_layout.setSpacing(10)

        self.tabs = QTabWidget()
        self.tabs.setStyleSheet(TAB_WIDGET_STYLE)
        self.policy_tab = IllustrationPolicyTab()
        self.inputs_tab = IllustrationInputsTab()
        self.values_tab = IllustrationValuesTab()
        self.report_tab = IllustrationReportTab()
        self.tabs.addTab(self.policy_tab, "Policy")
        self.tabs.addTab(self.inputs_tab, "Illustration Inputs")
        self.tabs.addTab(self.values_tab, "Values")
        self.tabs.addTab(self.report_tab, "Report")
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

    def _toggle_policy_list(self):
        self._history_panel_visible = not self._history_panel_visible
        if self._history_panel_visible:
            self.policy_list_window.show_docked()
        else:
            self.policy_list_window.hide()
        self.list_toggle_btn.setChecked(self._history_panel_visible)

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

    def _on_all_policies_removed(self):
        self._policy_cache.clear()

    def _show_status(self, message: str):
        self._status_label.setText(message)

    def _on_get_policy(self, policy_number: str, region: str, company_code: str = ""):
        self.lookup_bar.hide_company_chooser()
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
                self.values_tab.clear_results("Load a policy, then click Run Values.")
                self.report_tab.clear("Load a policy, then click Run Values.")
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
        self.policy_tab.load_data_from_policy(self._policy, self._policy_info)
        self.inputs_tab.load_data_from_policy(self._policy)
        self.values_tab.clear_results("Click Run Values to project the selected illustration duration.")
        self.report_tab.clear()
        self.run_values_btn.setEnabled(True)
        cache_note = " (cached)" if cached else ""
        self._show_status(f"Loaded policy {self._policy.policy_number} ({company_code}) - {self._policy.status_description}{cache_note}")

    def _on_run_values(self):
        if not self._policy or not self._policy.exists:
            QMessageBox.information(self, "Run Values", "Load a policy before running illustrated values.")
            return

        policy_number = self._policy_info.get("PolicyNumber", self._policy.policy_number)
        region = self._policy_info.get("Region", self._current_region or "CKPR")
        company_code = self._policy_info.get("CompanyCode", self._policy.company_code)

        QApplication.setOverrideCursor(QCursor(Qt.CursorShape.WaitCursor))
        self.run_values_btn.setEnabled(False)
        self._show_status(f"Running illustration values for {policy_number}...")
        QApplication.processEvents()

        try:
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
            engine = IllustrationEngine()
            results = engine.project(
                scenario.projectable_policy,
                months=projection_months,
                future_inputs=scenario.future_inputs,
                options=self.inputs_tab.export_options(),
                stop_on_lapse=self.inputs_tab.stop_on_lapse_enabled(),
            )
            self.values_tab.display_projection(
                scenario.projectable_policy,
                results,
                months=max(len(results) - 1, 0),
                injected_first_row_columns=self._first_row_injected_columns(scenario),
            )
            from datetime import date as _date

            from suiteview.illustration.core.report_builder import build_ul_report

            self.report_tab.display_report(build_ul_report(
                scenario.projectable_policy,
                results,
                options=self.inputs_tab.export_options(),
                future_inputs=scenario.future_inputs,
                run_date=_date.today(),
            ))
            self.tabs.setCurrentWidget(self.values_tab)
            self._show_status(
                f"Values ready for {policy_number} - valuation snapshot plus {max(len(results) - 1, 0)} projected months"
            )
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
            columns.add("PolicyDebt")
        if overrides.preferred_loan_principal is not None or overrides.preferred_loan_accrued is not None:
            columns.add("PrefLn Total")
            columns.add("PolicyDebt")
        if overrides.variable_loan_principal is not None or overrides.variable_loan_accrued is not None:
            columns.add("Varln Total")
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
