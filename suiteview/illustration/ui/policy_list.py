"""Illustration List side panel — one dockable window, two views.

A Policies | Saved Cases toggle in the panel's own header bar (where a title
would sit — the checked button IS the title) switches the body between:

- **Policies view** — the session's visited/added policies, one per row,
  labeled "REGION | CO | POLICY" with a trailing "| <form>" segment once the
  policy's data is loaded, plus the region/company/policy inputs + Add on
  top. Activating a row performs a fresh live DB2 load.
- **Saved Cases view** — ``SavedCasesView`` (``saved_cases_panel.py``): a
  search bar over a flat two-column case list (Saved date | Case Name).

The last active view sticks for the session (the stacked widget simply keeps
its index). The window header's single "List" button shows/hides the panel.
"""

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QAction
from PyQt6.QtWidgets import (
    QComboBox,
    QHBoxLayout,
    QLineEdit,
    QMenu,
    QPushButton,
    QStackedWidget,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from suiteview.core.db2_constants import REGIONS
from suiteview.polview.ui.tabs.policy_list_tab import PolicyListWindow

from .saved_cases_panel import SavedCasesView
from .styles import (
    GOLD_PRIMARY,
    GOLD_TEXT,
    HEADER_PANEL_BUTTON_STYLE,
    PURPLE_BG,
    PURPLE_DARK,
    PURPLE_LIGHT,
    PURPLE_PRIMARY,
    PURPLE_RICH,
    PURPLE_SUBTLE,
    WHITE,
)

# Policies | Saved Cases toggle in the PANEL's header bar — same visual
# language as the main window's header "List" button, compacted to fit the
# 36px panel header. The checked button names the active view (there is no
# separate title text).
_HEADER_TOGGLE_STYLE = HEADER_PANEL_BUTTON_STYLE + """
    QPushButton { padding: 0 8px; font-size: 10px; }
"""


class IllustrationPolicyListWindow(PolicyListWindow):
    """Merged List panel with Illustration purple/gold styling."""

    def __init__(self, parent_window=None):
        # Form number per policy (IllustrationPolicyData.form_number — base
        # coverage LH_COV_PHA.POL_FRM_NBR), shown as a trailing "| <form>"
        # label segment so the user can tell the policy type at a glance.
        # Backfilled when a policy loads; entries typed in before any load
        # simply omit the segment.
        self._policy_forms: dict[str, str] = {}
        super().__init__(parent_window)
        # 50% wider than the shared PolView base default (250) — the Saved
        # Cases list needs room for the Saved date + full case names. Height
        # is re-fitted to the parent on dock, so only width is set here.
        self.resize(375, self.height())
        self._bg_color = PURPLE_PRIMARY
        self._frame.setStyleSheet(f"""
            QFrame {{
                background: {PURPLE_PRIMARY};
                border: none;
                border-radius: 8px;
            }}
        """)

    def build_header(self):
        header = QWidget()
        header.setObjectName("policyListHeader")
        header.setFixedHeight(36)
        header.setStyleSheet(f"""
            QWidget#policyListHeader {{
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    stop:0 {PURPLE_LIGHT}, stop:0.5 {PURPLE_RICH}, stop:1 {PURPLE_DARK});
                border-top-left-radius: 8px;
                border-top-right-radius: 8px;
                border-bottom: 2px solid {GOLD_PRIMARY};
            }}
            QPushButton {{
                background: transparent;
                color: {GOLD_TEXT};
                border: 1px solid {GOLD_PRIMARY};
                border-radius: 3px;
                padding: 2px 8px;
                font-size: 10px;
                font-weight: bold;
                min-width: 20px;
            }}
            QPushButton:hover {{
                background-color: {GOLD_PRIMARY};
                color: {PURPLE_DARK};
            }}
        """)
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(8, 4, 8, 4)
        header_layout.setSpacing(4)

        # Policies | Saved Cases toggle lives IN the header where a title
        # would sit — the checked button IS the title.
        self.policies_view_btn = QPushButton("Policies")
        self.cases_view_btn = QPushButton("Saved Cases")
        for btn in (self.policies_view_btn, self.cases_view_btn):
            btn.setCheckable(True)
            btn.setStyleSheet(_HEADER_TOGGLE_STYLE)
            header_layout.addWidget(btn)
        self.policies_view_btn.setChecked(True)
        self.policies_view_btn.clicked.connect(
            lambda: self.show_view("policies"))
        self.cases_view_btn.clicked.connect(
            lambda: self.show_view("cases"))
        header_layout.addStretch()

        close_btn = QPushButton("✕")
        close_btn.setFixedSize(24, 20)
        close_btn.clicked.connect(self.on_closed)
        header_layout.addWidget(close_btn)

        return header

    def build_body(self):
        body = QWidget()
        body_layout = QVBoxLayout(body)
        body_layout.setContentsMargins(0, 0, 0, 0)
        body_layout.setSpacing(0)

        content = QWidget()
        content.setStyleSheet(f"background-color: {PURPLE_BG};")
        inner_layout = QVBoxLayout(content)
        inner_layout.setContentsMargins(8, 8, 8, 8)
        inner_layout.setSpacing(6)

        # ── page 0: Policies view (inputs + history list) ─────────────
        policies_page = QWidget()
        policies_layout = QVBoxLayout(policies_page)
        policies_layout.setContentsMargins(0, 0, 0, 0)
        policies_layout.setSpacing(6)

        form_widget = QWidget()
        form_widget.setStyleSheet(f"""
            QLabel {{
                font-size: 10px;
                color: {PURPLE_DARK};
                font-weight: bold;
                background: transparent;
            }}
            QLineEdit {{
                border: 1px solid {PURPLE_PRIMARY};
                border-radius: 3px;
                padding: 3px 5px;
                font-size: 10px;
                background-color: {WHITE};
            }}
            QComboBox {{
                border: 1px solid {PURPLE_PRIMARY};
                border-radius: 3px;
                padding: 3px 5px;
                font-size: 10px;
                background-color: {WHITE};
            }}
            QPushButton {{
                background-color: {PURPLE_PRIMARY};
                color: {GOLD_TEXT};
                border: 1px solid {GOLD_PRIMARY};
                border-radius: 3px;
                padding: 4px 12px;
                font-weight: bold;
                font-size: 10px;
            }}
            QPushButton:hover {{
                background-color: {PURPLE_RICH};
            }}
        """)
        form_layout = QVBoxLayout(form_widget)
        form_layout.setContentsMargins(0, 0, 0, 0)
        form_layout.setSpacing(4)

        input_row = QHBoxLayout()
        input_row.setSpacing(4)

        self.region_combo = QComboBox()
        self.region_combo.addItems(REGIONS)
        self.region_combo.setCurrentText("CKPR")
        self.region_combo.setFixedWidth(65)
        input_row.addWidget(self.region_combo)

        self.company_input = QLineEdit()
        self.company_input.setPlaceholderText("Co")
        self.company_input.setText("01")
        self.company_input.setFixedWidth(30)
        input_row.addWidget(self.company_input)

        self.policy_input = QLineEdit()
        self.policy_input.setPlaceholderText("Policy #")
        self.policy_input.returnPressed.connect(self._add_to_history)
        input_row.addWidget(self.policy_input)

        form_layout.addLayout(input_row)

        add_btn = QPushButton("Add")
        add_btn.clicked.connect(self._add_to_history)
        form_layout.addWidget(add_btn)

        policies_layout.addWidget(form_widget)

        # Policy list. Dense, spreadsheet-not-list: no header, tight rows.
        # (A QTreeWidget with flat top-level items — same widget family as
        # the Saved Cases view so both views read identically.)
        self.history_tree = QTreeWidget()
        self.history_tree.setHeaderHidden(True)
        self.history_tree.setRootIsDecorated(False)
        self.history_tree.setIndentation(0)
        self.history_tree.setUniformRowHeights(True)
        self.history_tree.setExpandsOnDoubleClick(False)
        self.history_tree.setStyleSheet(f"""
            QTreeWidget {{
                background-color: {WHITE};
                border: 1px solid {PURPLE_PRIMARY};
                border-radius: 3px;
                font-family: 'Segoe UI';
                font-size: 9pt;
            }}
            QTreeWidget::item {{
                padding: 0px 4px;
                margin: 0px;
                min-height: 18px;
                max-height: 18px;
            }}
            QTreeWidget::item:selected {{
                background-color: #FFE8A3;
                color: {PURPLE_DARK};
            }}
            QTreeWidget::item:hover {{
                background-color: {PURPLE_SUBTLE};
            }}
        """)
        self.history_tree.itemClicked.connect(self._on_tree_item_clicked)
        self.history_tree.itemDoubleClicked.connect(self._on_tree_item_double_clicked)
        self.history_tree.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.history_tree.customContextMenuRequested.connect(self._show_context_menu)
        policies_layout.addWidget(self.history_tree)

        self.clear_all_btn = QPushButton("Clear All")
        self.clear_all_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: transparent;
                color: {PURPLE_DARK};
                border: 1px solid {PURPLE_PRIMARY};
                border-radius: 3px;
                padding: 2px 8px;
                font-size: 9px;
                font-weight: bold;
                max-height: 18px;
            }}
            QPushButton:hover {{
                background-color: {PURPLE_PRIMARY};
                color: {GOLD_TEXT};
            }}
        """)
        self.clear_all_btn.clicked.connect(self._clear_all)
        policies_layout.addWidget(self.clear_all_btn)

        # ── page 1: Saved Cases view ──────────────────────────────────
        self.cases_view = SavedCasesView(host_panel=self)

        self._view_stack = QStackedWidget()
        self._view_stack.addWidget(policies_page)    # index 0
        self._view_stack.addWidget(self.cases_view)  # index 1
        inner_layout.addWidget(self._view_stack, 1)

        body_layout.addWidget(content)

        footer = QWidget()
        footer.setObjectName("policyListFooter")
        footer.setFixedHeight(22)
        footer.setStyleSheet(f"""
            QWidget#policyListFooter {{
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    stop:0 {PURPLE_LIGHT}, stop:0.5 {PURPLE_RICH}, stop:1 {PURPLE_DARK});
                border-top: 2px solid {GOLD_PRIMARY};
                border-bottom-left-radius: 8px;
                border-bottom-right-radius: 8px;
            }}
        """)
        body_layout.addWidget(footer)

        return body

    def on_closed(self):
        """Hide and update the parent's header toggle button state."""
        self.hide()
        pw = self._parent_window
        if pw is not None and hasattr(pw, "list_toggle_btn"):
            pw._list_panel_visible = False
            pw.list_toggle_btn.setChecked(False)

    # ── view switching ────────────────────────────────────────────────

    def show_view(self, name: str):
        """Front the "policies" or "cases" view; the choice sticks for the
        session (the stack keeps its index while the panel is hidden). The
        checked header button identifies the active view — no title text."""
        cases = name == "cases"
        self._view_stack.setCurrentIndex(1 if cases else 0)
        self.policies_view_btn.setChecked(not cases)
        self.cases_view_btn.setChecked(cases)

    def current_view(self) -> str:
        return "cases" if self._view_stack.currentIndex() == 1 else "policies"

    # ── saved-cases pass-through ──────────────────────────────────────

    def refresh_cases(self):
        self.cases_view.refresh_cases()

    # ── form-number label segment ─────────────────────────────────────

    def set_policy_form(self, policy: str, form_number: str):
        """Record a policy's form number and refresh its label segment in the
        Policies view. Called by the window once policy data loads —
        IllustrationPolicyData.form_number. (The Saved Cases view is a flat
        case list; its search reads forms from each case's snapshot instead.)
        """
        form = (form_number or "").strip()
        if not form:
            return
        key = (policy or "").strip().upper()
        if self._policy_forms.get(key) == form:
            return
        self._policy_forms[key] = form
        self._refresh_list()

    # ── list build ────────────────────────────────────────────────────

    def _refresh_list(self):
        self.history_tree.clear()
        for region, company, policy in self._policy_history:
            form = self._policy_forms.get(policy.strip().upper(), "")
            label = f"{region} | {company} | {policy}"
            if form:
                label += f" | {form}"
            item = QTreeWidgetItem([label])
            item.setData(0, Qt.ItemDataRole.UserRole, (region, company, policy))
            self.history_tree.addTopLevelItem(item)

    # ── activation ────────────────────────────────────────────────────

    def _activation_allowed(self) -> bool:
        parent_hidden = (
            self._parent_window is not None
            and not self._parent_window.isVisible()
        )
        return self.is_docked or parent_hidden

    def _on_tree_item_clicked(self, item: QTreeWidgetItem, column: int):
        data = item.data(0, Qt.ItemDataRole.UserRole)
        if data and self._activation_allowed():
            self._pending_click_data = data
            self._click_timer.start(220)

    def _on_tree_item_double_clicked(self, item: QTreeWidgetItem, column: int):
        self._click_timer.stop()
        self._pending_click_data = None
        data = item.data(0, Qt.ItemDataRole.UserRole)
        if data:
            region, company, policy = data
            self.policy_open_requested.emit(region, company, policy)

    def _emit_pending_policy_selection(self):
        data = self._pending_click_data
        self._pending_click_data = None
        if data and self._activation_allowed():
            region, company, policy = data
            self.policy_selected.emit(region, company, policy)

    # ── context menu / removal ────────────────────────────────────────

    def _show_context_menu(self, pos):
        item = self.history_tree.itemAt(pos)
        data = item.data(0, Qt.ItemDataRole.UserRole) if item else None
        if not data:
            return
        menu = QMenu(self)
        delete_action = QAction("Remove from list", self)
        delete_action.triggered.connect(lambda: self._delete_policy_item(item))
        menu.addAction(delete_action)
        menu.exec(self.history_tree.viewport().mapToGlobal(pos))

    def _delete_policy_item(self, item: QTreeWidgetItem):
        """Remove a policy from the history and evict its caches."""
        data = item.data(0, Qt.ItemDataRole.UserRole)
        if not data:
            return
        region, company, policy = data
        entry = (region, company, policy)
        if entry in self._policy_history:
            self._policy_history.remove(entry)
        self.policy_removed.emit(policy, region)
        self._refresh_list()

    def _clear_all(self):
        """Clear the session history and caches."""
        self._policy_history.clear()
        self.all_policies_removed.emit()
        self._refresh_list()
