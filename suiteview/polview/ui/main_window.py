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
from html import escape
from time import perf_counter

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout,
    QTabWidget, QPushButton, QLabel, QMessageBox, QApplication,
)
from PyQt6.QtGui import QKeySequence, QShortcut
from PyQt6.QtCore import QEvent, QTimer, Qt, QSignalBlocker, pyqtSignal, pyqtSlot

from suiteview.ui.widgets.frameless_window import FramelessWindowBase
from suiteview.ui.access_control import requires_app_access
from suiteview.core.db2_connection import DB2Connection
from suiteview.core.db2_constants import REGION_DSN_MAP
from suiteview.core.odbc_utils import is_password_error
from suiteview.polview.services.policy_service import cache_policy_info, remove_from_cache
from ..models.policy_information import PolicyInformation

from .styles import (
    TAB_WIDGET_STYLE,
    GREEN_BG, GOLD_TEXT, GOLD_PRIMARY,
    POLVIEW_HEADER_COLORS, POLVIEW_DUPLICATE_HEADER_COLORS, POLVIEW_BORDER_COLOR,
)
from .widgets import PolicyLookupBar, StyledInfoTableGroup
from .tree_panel import PolicyRecordTreePanel
from .loading_overlay import TabLoadingOverlay
from .policy_load_controller import PolicyLoadController
from .policy_summary_strip import PolicySummaryStrip
from .tooltip_style import use_readable_tooltips
from .tabs.reinstatement_tab import ReinstatementTab
from .tabs.other_data_tab import OtherDataTab
from ..services.reinstatement import is_ul_policy
from ..services.policy_insights import (
    build_policy_summary, suggested_actions, summary_html, summary_text,
    support_tool_availability,
)
from ..services.policy_notes import PolicyNotesStore, RecentPoliciesStore
from ..services.rate_selection import build_rate_selection, missing_rate_diagnostic
from ..services.table_search import search_policy_tables
from .tabs import (
    CoveragesTab, PolicyTab, TargetsAccumulatorsTab, PersonsTab,
    AdvProdValuesTab, ActivityTab, DividendsTab, LoansTab, RawTableTab,
    PolicyListWindow, PolicySupportTab, PolicyLibraryTab, ReinsuranceTab,
)
from suiteview.polview.models.policy_sections.lookup import policy_attr

logger = logging.getLogger(__name__)

# Optional pages stay in a fixed position; when they do not apply they are
# greyed with the reason in their tooltip rather than removed.
UNAVAILABLE_TAB_REASONS = {
    "dividends": "No dividend records on this policy "
                 "(LH_UNAPPLIED_PTP, LH_ONE_YR_TRM_ADD, LH_PTP_ON_DEP, LH_PAID_UP_ADD).",
    "loans": "No loan records on this policy (LH_CSH_VAL_LOAN, LH_FND_VAL_LOAN).",
    "advprod": "Account values apply to advanced products (UL/IUL/VUL/ISWL); "
               "this is a traditional policy.",
}

_KONAMI = (
    Qt.Key.Key_Up, Qt.Key.Key_Up, Qt.Key.Key_Down, Qt.Key.Key_Down,
    Qt.Key.Key_Left, Qt.Key.Key_Right, Qt.Key.Key_Left, Qt.Key.Key_Right,
    Qt.Key.Key_B, Qt.Key.Key_A,
)
_LOADING_QUIPS = (
    "Consulting the mortality tables…",
    "Asking CyberLife nicely…",
    "Rounding to the nearest cent…",
    "Counting monthliversaries…",
    "Checking the 7-pay test twice…",
    "Warming up the green screen…",
    "Reconciling accumulators…",
)

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


# Joint survivor columns: (joint COI, CyberLife stored rate, check) in the schema
# grid ("C JointCOI", "CyberLife RNL_RT", ...) and the legacy grid.
_JOINT_COLUMNS = (("C JointCOI", "CyberLife RNL_RT", "CyberLife Check"),
                  ("JointCOI", "CyberLife", "Check"))


def joint_survivor_columns(headers):
    """The joint survivor (COI, stored rate, check) column names in a rate grid, else None."""
    return next((names for names in _JOINT_COLUMNS if all(n in headers for n in names)), None)


def _alive(obj) -> bool:
    from PyQt6 import sip
    try:
        return obj is not None and not sip.isdeleted(obj)
    except TypeError:
        return False


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
        self._unavailable_tabs: dict[str, str] = {}
        self._notes_store = PolicyNotesStore()
        self._recent_store = RecentPoliciesStore()
        self._recent_recorded: tuple = ()
        self._key_trail: list = []
        self._dialogs: list = []

        # Header-bar "Open in RERUN" button (built before super().__init__
        # so FramelessWindowBase can place it via header_widgets; wired after).
        self.open_illustrator_btn = QPushButton("📈 RERUN")
        self.open_illustrator_btn.setToolTip("Open this policy in RERUN")
        self.open_illustrator_btn.setEnabled(False)
        self.open_illustrator_btn.setStyleSheet(HEADER_ILLUSTRATOR_BUTTON_STYLE)

        # Header-bar "Policy Record" button -- opens the CyberLife green-screen
        # segment viewer for the loaded policy.
        self.open_record_btn = QPushButton("📟 Record")
        self.open_record_btn.setToolTip(
            "View the CyberLife policy record segments (mainframe-style)"
        )
        self.open_record_btn.setEnabled(False)
        self.open_record_btn.setStyleSheet(HEADER_ILLUSTRATOR_BUTTON_STYLE)

        self.shortcuts_btn = QPushButton("⌨ Shortcuts")
        self.shortcuts_btn.setToolTip("Keyboard shortcuts and tips (F1)")
        self.shortcuts_btn.setStyleSheet(HEADER_ILLUSTRATOR_BUTTON_STYLE)

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
            header_widgets=[self.shortcuts_btn, self.open_record_btn, self.open_illustrator_btn],
        )
        self.shortcuts_btn.clicked.connect(self._show_help)
        self.open_illustrator_btn.clicked.connect(self._open_in_illustrator)
        self.open_record_btn.clicked.connect(self._open_policy_record)
        self._loader = PolicyLoadController()
        self._loader.ready.connect(self._on_prepared_policy)
        self._loader.failed.connect(self._on_load_failed)
        self._loader.state_changed.connect(self._on_load_state_changed)
        self._loader.settled.connect(self._on_background_settled)
        self.destroyed.connect(self._loader.dispose)
        self._install_shortcuts()
        self._refresh_recent_completer()
        use_readable_tooltips(self)
        # Easter-egg listener: only the policy box, never an app-wide filter.
        self.lookup_bar.policy_input.installEventFilter(self)

        # Optionally pull in a policy on open (e.g. launched from the taskbar).
        if initial_policy:
            self.load_policy(initial_policy, region=initial_region,
                             company_code=initial_company)

    # == FramelessWindowBase override =====================================

    # Width of the tree panel when extended
    TREE_PANEL_WIDTH = 200

    def build_content(self) -> QWidget:
        """Build the main body widget (everything below the title bar).

        The Tables & Rates panel is a full-height column left of everything
        else, so opening it (which grows the window leftwards) leaves the
        lookup bar, badges, tabs and footer where they were on screen.
        """
        self._tree_visible = False

        body = QWidget()
        body.setStyleSheet(f"background-color: {self._window_bg};")
        body_layout = QHBoxLayout(body)
        body_layout.setContentsMargins(0, 0, 0, 0)
        body_layout.setSpacing(0)

        # Tree panel (hidden initially, shown when toggled)
        self.records_tree = PolicyRecordTreePanel()
        self.records_tree.table_selected.connect(self._on_table_selected)
        self.records_tree.rate_selected.connect(self._on_rate_selected)
        self.records_tree.search_requested.connect(self._on_tables_search)
        self.records_tree.setFixedWidth(self.TREE_PANEL_WIDTH)
        self.records_tree.setVisible(False)
        body_layout.addWidget(self.records_tree)

        main_column = QWidget()
        main_layout = QVBoxLayout(main_column)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)
        body_layout.addWidget(main_column, 1)

        # Policy lookup bar
        self.lookup_bar = PolicyLookupBar()
        self.lookup_bar.policy_requested.connect(self._on_get_policy)  # (policy, region, company)
        self.lookup_bar.company_chosen.connect(self._on_get_policy)    # (policy, region, company)
        # Checked = solid green with gold text so the label stays readable.
        toggle_style = """
            QPushButton {
                background: #FFFFFF;
                border: 1px solid #D4A017;
                border-radius: 3px;
                min-height: 24px; max-height: 24px;
                font-size: 11px; font-weight: bold;
                color: #0A3D0A;
                padding: 0 8px;
            }
            QPushButton:hover {
                background-color: #FFF3D0;
                color: #0A3D0A;
            }
            QPushButton:checked {
                background-color: #1B5E20;
                border-color: #0A3D0A;
                color: #FFD54F;
            }
            QPushButton:checked:hover {
                background-color: #2E7D32;
                color: #FFFFFF;
            }
            QPushButton:disabled {
                background: transparent;
                color: rgba(10, 61, 10, 0.35);
                border-color: rgba(212, 160, 23, 0.4);
            }
        """
        # Tables & Rates panel toggle sits at the left, next to where the panel opens.
        self._tree_toggle_btn = QPushButton("⊞ Tables")
        self._tree_toggle_btn.setToolTip("Show the Tables & Rates panel")
        self._tree_toggle_btn.setCheckable(True)
        self._tree_toggle_btn.setEnabled(False)
        self._tree_toggle_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._tree_toggle_btn.setStyleSheet(toggle_style)
        self._tree_toggle_btn.clicked.connect(self._toggle_tree_panel)
        if self._enable_policy_list:
            # Add "☰ List" toggle button to the lookup bar, right after Get button
            self.list_toggle_btn = QPushButton("☰ List")
            self.list_toggle_btn.setCheckable(True)
            self.list_toggle_btn.setToolTip("Toggle Policy List panel")
            self.list_toggle_btn.setStyleSheet(toggle_style)
            self.list_toggle_btn.clicked.connect(self._toggle_policy_list)
            self.lookup_bar.layout().addWidget(self.list_toggle_btn)
        main_layout.addWidget(self.lookup_bar)

        # Status badges and quick actions
        strip_host = QWidget()
        strip_host.setStyleSheet(f"background-color: {self._window_bg};")
        strip_layout = QHBoxLayout(strip_host)
        strip_layout.setContentsMargins(10, 0, 10, 0)
        strip_layout.setSpacing(6)
        strip_layout.addWidget(self._tree_toggle_btn)
        self.summary_strip = PolicySummaryStrip()
        self.summary_strip.suggestion_clicked.connect(self._on_suggestion_clicked)
        self.summary_strip.copy_requested.connect(self._copy_policy_summary)
        self.summary_strip.notes_requested.connect(self._open_policy_notes)
        self.summary_strip.timeline_requested.connect(self._open_timeline)
        strip_layout.addWidget(self.summary_strip, 1)
        main_layout.addWidget(strip_host)

        # Main content area
        content_widget = QWidget()
        content_widget.setStyleSheet(f"background-color: {self._window_bg};")
        content_layout = QHBoxLayout(content_widget)
        content_layout.setContentsMargins(0, 0, 0, 0)
        content_layout.setSpacing(0)

        # Tabs (main content, always visible)
        tabs_container = QWidget()
        tabs_container.setStyleSheet(f"background-color: {self._window_bg};")
        tabs_layout = QVBoxLayout(tabs_container)
        tabs_layout.setContentsMargins(10, 6, 10, 8)
        tabs_layout.setSpacing(6)

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
        self.raw_table_tab.search_hit_activated.connect(self._on_search_hit_activated)

        self.policy_support_tab = PolicySupportTab(self.tabs)
        self.policy_library_tab = PolicyLibraryTab(self.tabs)
        self.other_data_tab = OtherDataTab(self.tabs)

        self.tabs.addTab(self.coverages_tab, "Coverages")
        self.tabs.addTab(self.policy_tab, "Policy")
        self.tabs.addTab(self.targets_tab, "Targets && Accumulators")
        self.tabs.addTab(self.persons_tab, "Persons")
        self.tabs.addTab(self.advprod_tab, "Account Values")
        self.tabs.addTab(self.dividends_tab, "Dividends")
        self.tabs.addTab(self.loans_tab, "Loans")
        self.tabs.addTab(self.reinsurance_tab, "Reinsurance")
        self.tabs.addTab(self.activity_tab, "Activity")
        self.tabs.addTab(self.policy_support_tab, "Policy Support")
        self.tabs.addTab(self.other_data_tab, "Other Data")
        self.tabs.addTab(self.raw_table_tab, "Raw Table")
        self.policy_library_tab.hide()

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
            "advprod": (self.advprod_tab, "Account Values"),
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

        The window's left edge moves by exactly the tree panel width and the
        panel fills that new strip, so the rest of the body stays at the same
        screen position. The title bar spans the whole window, so its
        contents are indented by the same width to stay put too.
        """
        geo = self.geometry()
        tree_w = self.TREE_PANEL_WIDTH
        header_layout = self.header_bar.layout()
        margins = header_layout.contentsMargins()

        if self._tree_visible:
            # Hide tree — shrink window from the left
            self.records_tree.setVisible(False)
            self._tree_visible = False
            self._tree_toggle_btn.setChecked(False)
            self._tree_toggle_btn.setToolTip("Show the Tables & Rates panel")
            header_layout.setContentsMargins(
                margins.left() - tree_w, margins.top(), margins.right(), margins.bottom())
            self.setGeometry(geo.x() + tree_w, geo.y(),
                             geo.width() - tree_w, geo.height())
        else:
            # Show tree — extend window to the left
            self.records_tree.setVisible(True)
            self._tree_visible = True
            self._tree_toggle_btn.setChecked(True)
            self._tree_toggle_btn.setToolTip("Hide the Tables & Rates panel")
            header_layout.setContentsMargins(
                margins.left() + tree_w, margins.top(), margins.right(), margins.bottom())
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

    # == Summary strip, notes & recents ====================================

    def _loading_quip(self) -> str:
        return _LOADING_QUIPS[self._load_token % len(_LOADING_QUIPS)]

    def _refresh_summary(self):
        """Rebuild the at-a-glance strip from whatever data has arrived."""
        policy = self._policy
        if policy is None or not policy.exists:
            return
        summary = build_policy_summary(policy)
        tools = support_tool_availability(policy)
        self.summary_strip.set_summary(summary, suggested_actions(policy, summary, tools))
        self.summary_strip.set_notes_count(
            self._notes_store.count(policy.company_code, policy.policy_number))
        self.policy_support_tab.apply_tool_availability(tools)
        region = policy.region or ""
        base_title = "SuiteView:  PolView"
        self.set_title(base_title if region in ("", "CKPR") else f"{base_title}   ·   {region} (non-production)")
        marker = (policy.policy_number, policy.company_code, policy.region, summary.insured_name)
        if marker != self._recent_recorded:
            self._recent_recorded = marker
            try:
                self._recent_store.record(
                    policy=policy.policy_number, company=policy.company_code,
                    region=policy.region, insured=summary.insured_name or "",
                    plancode=summary.plancode or "",
                )
                self._refresh_recent_completer()
            except OSError:
                logger.warning("Could not save recent PolView policies", exc_info=True)

    def _refresh_recent_completer(self):
        try:
            self.lookup_bar.set_recent_entries(self._recent_store.entries())
        except OSError:
            logger.warning("Could not read recent PolView policies", exc_info=True)

    @pyqtSlot()
    def _copy_policy_summary(self):
        summary = self.summary_strip.summary
        if summary is None:
            self._show_status("Load a policy to copy its summary")
            return
        from PyQt6.QtCore import QMimeData

        mime = QMimeData()
        mime.setText(summary_text(summary))
        mime.setHtml(summary_html(summary))
        QApplication.clipboard().setMimeData(mime)
        self._show_status(f"Copied {summary.policy_number} summary to the clipboard 📋")

    @pyqtSlot()
    def _open_policy_notes(self):
        if self._policy is None or not self._policy.exists:
            self._show_status("Load a policy to see its notes")
            return
        from .polview_dialogs import PolicyNotesDialog

        dialog = PolicyNotesDialog(self._policy.company_code, self._policy.policy_number,
                                   self, store=self._notes_store)
        dialog.notes_changed.connect(self.summary_strip.set_notes_count)
        self._keep_dialog(dialog)
        dialog.show()
        dialog.editor.setFocus()

    def _keep_dialog(self, dialog):
        self._dialogs = [d for d in self._dialogs if _alive(d)]
        self._dialogs.append(dialog)

    @pyqtSlot()
    def _open_timeline(self):
        if self._policy is None or not self._policy.exists:
            self._show_status("Load a policy to see its timeline")
            return
        from datetime import date as _date
        from ..services.policy_timeline import build_policy_timeline
        from .polview_dialogs import TimelineDialog

        policy = self._policy
        dialog = TimelineDialog(
            f"Timeline · {policy.company_code} - {policy.policy_number}",
            build_policy_timeline(policy), _date.today(), self,
        )
        self._keep_dialog(dialog)
        dialog.show()

    @pyqtSlot(str)
    def _on_suggestion_clicked(self, key: str):
        if key == "reinstatement":
            self._show_reinstatement_tab()
        elif key == "annuity_rider":
            self._show_annuity_rider_tab()
        elif key in ("glp_exception", "forecast", "abr", "policy_support"):
            self.tabs.setCurrentWidget(self.policy_support_tab)
            if self._load_policy_tab(self.policy_support_tab):
                self.policy_support_tab.open_section(key)

    # == Shortcuts ==========================================================

    def _install_shortcuts(self):
        def bind(sequence, handler):
            shortcut = QShortcut(QKeySequence(sequence), self)
            shortcut.setContext(Qt.ShortcutContext.WindowShortcut)
            shortcut.activated.connect(handler)
            return shortcut

        self._shortcuts = [
            bind("Ctrl+F", self._open_field_finder),
            bind("F1", self._show_help),
        ]

    @pyqtSlot()
    def _show_help(self):
        from .polview_dialogs import shortcut_help_html, show_message_dialog

        self._keep_dialog(show_message_dialog(
            self, "PolView shortcuts & tricks", shortcut_help_html(), width=520))

    # == Field finder ========================================================

    def field_index(self) -> list:
        """Every info field and table column across the tabs, for Ctrl+F."""
        entries = []
        for index in range(self.tabs.count()):
            page = self.tabs.widget(index)
            if not self.tabs.isTabEnabled(index):
                continue
            tab_title = self.tabs.tabText(index).replace("&&", "&").rstrip(". !")
            for group in page.findChildren(StyledInfoTableGroup):
                if not group.isVisibleTo(page):
                    continue
                group_title = group.title()
                if group._show_info:
                    for attr, label, value in group.field_entries():
                        if not value.isVisibleTo(page) and not group._labels[attr].isVisibleTo(page):
                            continue
                        entries.append((index, tab_title, group_title, label, value.text(),
                                        group._labels[attr]))
                if group.table is not None:
                    for header in group.table._original_headers:
                        entries.append((index, tab_title, group_title, f"{header} (column)", "",
                                        group))
        return entries

    @pyqtSlot()
    def _open_field_finder(self):
        from .polview_dialogs import FieldFinderDialog

        dialog = FieldFinderDialog(self.field_index, self._jump_to_field, self)
        self._keep_dialog(dialog)
        dialog.show()

    def _jump_to_field(self, entry):
        from .polview_dialogs import flash_widget

        index, _tab, _group, label, _value, widget = entry
        self.tabs.setCurrentIndex(index)
        flash_widget(widget)
        self._show_status(f"Found “{label}”")

    # == Easter egg ========================================================

    def eventFilter(self, obj, event):
        if obj is self.lookup_bar.policy_input and event.type() == QEvent.Type.KeyPress:
            self._key_trail = (self._key_trail + [event.key()])[-len(_KONAMI):]
            if tuple(self._key_trail) == _KONAMI:
                self._key_trail = []
                QTimer.singleShot(0, self._activate_actuary_mode)
        return super().eventFilter(obj, event)

    def _activate_actuary_mode(self):
        """↑↑↓↓←→←→BA: ten seconds of celebratory chrome."""
        if getattr(self, "_actuary_mode", False):
            return
        self._actuary_mode = True
        original = self._header_colors
        self.set_header_colors(("#6A1B9A", "#D4A017", "#1B5E20"))
        self._show_status("🎲 Actuary Mode unlocked — q(x) = 0 for the next ten seconds. Nobody tell reinsurance.")

        def restore():
            if _alive(self):
                self.set_header_colors(original)
                self._actuary_mode = False
                self._show_status("Actuary Mode ended. Mortality has resumed. 😇")

        QTimer.singleShot(10000, restore)

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
                system_code=self._policy_cache[k]['policy'].system_code,
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
        self._set_requested_policy_display("Loading...")
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
        self._unavailable_tabs.clear()
        for index in range(self.tabs.count()):
            self.tabs.setTabEnabled(index, True)
        self.summary_strip.clear(f"Loading {policy_number}…  {self._loading_quip()}")
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
            self.records_tree.enable_rates_tab(policy)
            with policy.cached_reads_only():
                self.records_tree.show_rates_tab()
            self._prepare_policy_tabs()
            if was_viewed:
                self._restore_aux_tabs(store_key)
            else:
                self._reset_aux_tabs(store_key)
                with QSignalBlocker(self.tabs):
                    self.tabs.setCurrentWidget(self.coverages_tab)
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
            flash = " ⚡" if elapsed < 1.0 else ""
            self._show_status(
                f"{policy.policy_number} ({policy.company_code}) ready in {elapsed:.1f}s{flash}"
                " - loading details in background"
            )
            self._refresh_summary()
            self.policy_ready.emit()
            return
        if self._policy is None:
            return
        self._policy.merge_prefetched(policy)
        if stage == "tables":
            self.records_tree.set_table_presence(prepared.payload)
            return
        self._tab_payloads[stage] = prepared.payload
        tab, _title = self._stage_tabs[stage]
        if not prepared.available:
            self._mark_tab_unavailable(stage)
            self._pending_policy_tabs.discard(tab)
        self._set_tab_state(stage, "ready")
        if prepared.available and self.tabs.currentWidget() is tab:
            self._load_policy_tab(tab)
        self._refresh_summary()

    def _prepare_policy_tabs(self) -> bool:
        """No data queries: optional tabs remain pending until their worker result."""
        with QSignalBlocker(self.tabs):
            self._clear_reinstatement_tab()
        if not self._policy or not self._policy.exists:
            return False
        selected = self.tabs.currentWidget()
        with QSignalBlocker(self.tabs):
            for index in range(self.tabs.count()):
                self.tabs.setTabEnabled(index, True)
            rules = policy_attr(self._policy, "product_rules", None)
            advanced = rules.is_advanced if rules is not None else self._policy.product.is_advanced_product
            if not advanced:
                self._mark_tab_unavailable("advprod")
            if not self.tabs.isTabEnabled(self.tabs.indexOf(selected)):
                self.tabs.setCurrentWidget(self.coverages_tab)
        for stage in self._stage_tabs:
            self._set_tab_state(stage, self._tab_states.get(stage, "queued"))
        return True

    def _mark_tab_unavailable(self, stage: str):
        """Grey a not-applicable page in place, with the reason as its tooltip."""
        tab, _title = self._stage_tabs[stage]
        self._unavailable_tabs[stage] = UNAVAILABLE_TAB_REASONS.get(
            stage, "Not applicable for this policy.")
        index = self.tabs.indexOf(tab)
        with QSignalBlocker(self.tabs):
            if self.tabs.currentWidget() is tab:
                self.tabs.setCurrentWidget(self.coverages_tab)
            if index >= 0:
                self.tabs.setTabEnabled(index, False)
        self._load_overlays[stage].hide()

    def is_tab_available(self, tab: QWidget) -> bool:
        index = self.tabs.indexOf(tab)
        return index >= 0 and self.tabs.isTabEnabled(index)

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
        if stage not in self._stage_tabs:
            if stage == "tables" and state == "failed":
                self.records_tree.set_table_presence_error(error)
            return
        self._tab_states[stage] = state
        tab, title = self._stage_tabs[stage]
        index = self.tabs.indexOf(tab)
        unavailable = self._unavailable_tabs.get(stage)
        if index >= 0:
            suffix = "" if unavailable else (
                "..." if state in ("queued", "loading") else " !" if state == "failed" else "")
            self.tabs.setTabText(index, title + suffix)
            self.tabs.setTabToolTip(index, unavailable or error or {
                "queued": "Waiting to load. Select to prioritize.",
                "loading": "Loading in background", "ready": "Ready",
                "failed": "Failed - open the tab to retry",
            }[state])
        if unavailable:
            self._load_overlays[stage].hide()
        elif state in ("queued", "loading"):
            self._load_overlays[stage].display(
                f"Loading {title.replace('&&', '&')} for {self._requested_policy[0]}...\n"
                f"{self._loading_quip()}  You can use other ready tabs while this loads."
            )
        elif state == "failed":
            self._load_overlays[stage].display(error, failed=True)

    @pyqtSlot(str, str)
    def _on_load_state_changed(self, stage: str, state: str):
        self._set_tab_state(stage, state)

    def _set_requested_policy_display(self, status: str):
        number, region, company = self._requested_policy
        requested_label = " - ".join(part for part in (region, company, number) if part)
        self.lookup_bar.policy_label.setText(f"{escape(requested_label)} ({status})")

    def _show_initial_notice(self, message: str, *, failed: bool = False):
        self._set_requested_policy_display("Load failed" if failed else "Select company")
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
            title = self._stage_tabs[stage][1] if stage in self._stage_tabs else "Tables panel"
            self._show_status(f"{title} unavailable: {error}")

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

    def open_source_table(self, table_name: str):
        """Jump from a field's documented source to its rows in Raw Table."""
        from ..config.policy_records import POLICY_RECORD_TABLES

        record = next((name for name, tables in POLICY_RECORD_TABLES.items()
                       if table_name in tables), "")
        self._show_status(f"Opening {table_name} rows…")
        self._on_table_selected(record, table_name)

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

    @pyqtSlot(str)
    def _on_tables_search(self, text: str):
        """Tables-panel search: list matching tables/fields/values in Raw Table."""
        if not text:
            if self.raw_table_tab.showing_search_results:
                self.raw_table_tab.clear()
            return
        if self._policy is None:
            return
        result = search_policy_tables(self._policy, self.records_tree.tables_with_data(), text)
        self.tabs.setCurrentWidget(self.raw_table_tab)
        self.raw_table_tab.show_search_results(result)

    @pyqtSlot(str, str, str, int)
    def _on_search_hit_activated(self, record: str, table_name: str, field: str, row: int):
        self._on_table_selected(record, table_name)
        self.raw_table_tab.focus_field(field, row)
        where = f".{field}" if field else ""
        self._show_status(f"Opened {table_name}{where} from search "
                          f"“{self.records_tree.search_text()}”")

    def _on_rate_selected(self, category: str, label: str, index: int):
        """Handle rate node selection from the rates tree."""
        if not self._policy:
            return

        self._show_status(f"Loading rates for {label}...")
        self.tabs.setCurrentWidget(self.raw_table_tab)
        self.raw_table_tab.show_message(f"Loading rates for {label}...", table_name=label)

        try:
            selection = build_rate_selection(self._policy, category, index)
            if selection.message:
                self.raw_table_tab.show_message(selection.message, table_name=selection.display_title)
                self._show_status(selection.message)
                return
            matrix = selection.matrix
            display_title = selection.display_title

            if matrix is not None and len(matrix) > 1:
                self.tabs.setCurrentWidget(self.raw_table_tab)

                headers = matrix[0]
                data_rows = [tuple(row) for row in matrix[1:]]

                self.raw_table_tab.set_data(
                    headers, data_rows, table_name=display_title, transposed=False,
                    header_labels=selection.header_labels, column_groups=selection.column_groups,
                )

                if joint_survivor_columns(headers) is not None:
                    self._show_joint_survivor_status(display_title, headers, data_rows)
                    return

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
                diag = missing_rate_diagnostic(self._policy, category, index) if matrix is None else ""
                message = f"No rate data available for {label}{diag}"
                self.raw_table_tab.show_message(message, table_name=display_title or label)
                self._show_status(message)

        except Exception as e:
            logger.exception("Rate display failed for %s", label)
            self.raw_table_tab.show_message(f"Error loading rates: {e}", table_name=label)
            self._show_status(f"Error loading rates: {e}")

    def _show_joint_survivor_status(self, title: str, headers, rows):
        """Highlight the current policy year and report the CyberLife comparison."""
        coi_name, stored_name, check_name = joint_survivor_columns(headers)
        stored_col, check_col = headers.index(stored_name), headers.index(check_name)
        year_col, coi_col = headers.index("Year"), headers.index(coi_name)
        current = next((i for i, row in enumerate(rows) if row[check_col] != ""), None)
        if current is None:
            self._show_status(f"{title} - current policy year is outside the calculated horizon")
            return
        row = rows[current]
        check = row[check_col]
        color = ("#D4EDDA" if check == "Match"
                 else "#FFE8A1" if check.startswith("Matches year") else "#F8D7DA")
        self.raw_table_tab.highlight_row(current, color)
        stored = row[stored_col]
        stored_text = f"{stored:.5f}" if isinstance(stored, float) else str(stored)
        self._show_status(
            f"{title} - year {row[year_col]}: calculated {row[coi_col]:.5f}, "
            f"CyberLife {stored_text} - {check}"
        )
