"""
Policy List window -- dockable/undockable side panel with policy history.

Inherits from DockableToolPanel for drag-to-undock / double-click-to-redock
behaviour shared with the TaskTracker detail panel.
"""

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QPushButton, QLineEdit, QComboBox,
    QListWidget, QListWidgetItem, QAbstractItemView,
    QMenu,
)
from PyQt6.QtCore import QSize
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QAction

from suiteview.core.db2_constants import REGIONS
from suiteview.ui.widgets.dockable_tool_panel import DockableToolPanel
from ..styles import (
    BLUE_RICH, BLUE_GRADIENT_TOP, BLUE_GRADIENT_BOT,
    BLUE_PRIMARY, BLUE_DARK, BLUE_SUBTLE, BLUE_BG,
    GOLD_PRIMARY, GOLD_LIGHT, GOLD_TEXT,
)


class PolicyListWindow(DockableToolPanel):
    """
    Policy List tool window that docks to the right of the main PolView window.

    Drag the header to undock; double-click the header to re-dock.
    """

    policy_selected = pyqtSignal(str, str, str)  # region, company, policy
    policy_removed = pyqtSignal(str, str)          # policy_number, region  (for cache eviction)
    all_policies_removed = pyqtSignal()            # clear entire cache

    def __init__(self, parent_window=None):
        self._policy_history = []
        self._resize_edge_handle = None
        self._resize_start_x = 0
        self._resize_start_width = 0
        self._resize_start_parent_width = 0

        super().__init__(
            parent_window,
            default_width=250,
            min_width=100,
            min_height=300,
            border_color=GOLD_PRIMARY,
            bg_color=BLUE_PRIMARY,
            corner_radius=8.0,
        )

    # -- DockableToolPanel overrides ----------------------------------------

    def build_header(self):
        """Green/gold gradient header bar with close button only."""
        header = QWidget()
        header.setObjectName("policyListHeader")
        header.setFixedHeight(36)
        header.setStyleSheet(f"""
            QWidget#policyListHeader {{
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    stop:0 {BLUE_GRADIENT_TOP}, stop:0.5 {BLUE_RICH}, stop:1 {BLUE_GRADIENT_BOT});
                border-top-left-radius: 8px;
                border-top-right-radius: 8px;
                border-bottom: 2px solid {GOLD_PRIMARY};
            }}
            QLabel {{
                color: {GOLD_TEXT};
                font-size: 12px;
                font-weight: bold;
                background: transparent;
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
                color: {BLUE_DARK};
            }}
        """)
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(8, 4, 8, 4)
        header_layout.setSpacing(8)

        title_label = QLabel("Policy List")
        header_layout.addWidget(title_label)
        header_layout.addStretch()

        # Close button (no dock/undock button -- drag header to undock,
        # double-click header to re-dock)
        close_btn = QPushButton("\u2715")
        close_btn.setFixedSize(24, 20)
        close_btn.clicked.connect(self.on_closed)
        header_layout.addWidget(close_btn)

        return header

    def build_body(self):
        """Form + history list body."""
        body = QWidget()
        body_layout = QVBoxLayout(body)
        body_layout.setContentsMargins(0, 0, 0, 0)
        body_layout.setSpacing(0)

        # Content area with light background
        content = QWidget()
        content.setStyleSheet(f"background-color: {BLUE_BG};")
        inner_layout = QVBoxLayout(content)
        inner_layout.setContentsMargins(8, 8, 8, 8)
        inner_layout.setSpacing(6)

        # Form for adding policies
        form_widget = QWidget()
        form_widget.setStyleSheet(f"""
            QLabel {{
                font-size: 10px;
                color: {BLUE_DARK};
                font-weight: bold;
                background: transparent;
            }}
            QLineEdit {{
                border: 1px solid {BLUE_PRIMARY};
                border-radius: 3px;
                padding: 3px 5px;
                font-size: 10px;
                background-color: white;
            }}
            QComboBox {{
                border: 1px solid {BLUE_PRIMARY};
                border-radius: 3px;
                padding: 3px 5px;
                font-size: 10px;
                background-color: white;
            }}
            QPushButton {{
                background-color: {BLUE_PRIMARY};
                color: white;
                border: none;
                border-radius: 3px;
                padding: 4px 12px;
                font-weight: bold;
                font-size: 10px;
            }}
            QPushButton:hover {{
                background-color: {BLUE_RICH};
            }}
        """)
        form_layout = QVBoxLayout(form_widget)
        form_layout.setContentsMargins(0, 0, 0, 0)
        form_layout.setSpacing(4)

        # Row 1: Region, Company, Policy # — inline, no labels
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

        # Row 2: Add button full width
        add_btn = QPushButton("Add")
        add_btn.clicked.connect(self._add_to_history)
        form_layout.addWidget(add_btn)

        inner_layout.addWidget(form_widget)

        # History list
        self.history_list = QListWidget()
        self.history_list.setStyleSheet(f"""
            QListWidget {{
                background-color: white;
                border: 1px solid {BLUE_PRIMARY};
                border-radius: 3px;
                font-family: 'Segoe UI';
                font-size: 9pt;
            }}
            QListWidget::item {{
                padding: 0px 4px;
                margin: 0px;
                border-bottom: none;
                min-height: 18px;
                max-height: 18px;
            }}
            QListWidget::item:selected {{
                background-color: {GOLD_LIGHT};
                color: {BLUE_DARK};
            }}
            QListWidget::item:hover {{
                background-color: {BLUE_SUBTLE};
            }}
        """)
        self.history_list.setSpacing(0)
        self.history_list.setUniformItemSizes(True)
        self.history_list.setIconSize(QSize(0, 0))
        self.history_list.itemClicked.connect(self._on_item_clicked)
        self.history_list.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.history_list.customContextMenuRequested.connect(self._show_context_menu)
        inner_layout.addWidget(self.history_list)

        # Clear All button
        self.clear_all_btn = QPushButton("Clear All")
        self.clear_all_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: transparent;
                color: {BLUE_DARK};
                border: 1px solid {BLUE_PRIMARY};
                border-radius: 3px;
                padding: 2px 8px;
                font-size: 9px;
                font-weight: bold;
                max-height: 18px;
            }}
            QPushButton:hover {{
                background-color: {BLUE_PRIMARY};
                color: white;
            }}
        """)
        self.clear_all_btn.clicked.connect(self._clear_all)
        inner_layout.addWidget(self.clear_all_btn)

        body_layout.addWidget(content)

        # Footer bar
        footer = QWidget()
        footer.setObjectName("policyListFooter")
        footer.setFixedHeight(22)
        footer.setStyleSheet(f"""
            QWidget#policyListFooter {{
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    stop:0 {BLUE_GRADIENT_TOP}, stop:0.5 {BLUE_RICH}, stop:1 {BLUE_GRADIENT_BOT});
                border-top: 2px solid {GOLD_PRIMARY};
                border-bottom-left-radius: 8px;
                border-bottom-right-radius: 8px;
            }}
        """)
        body_layout.addWidget(footer)

        return body

    def on_closed(self):
        """Hide and update parent toggle button state."""
        self.hide()
        pw = self._parent_window
        if pw and hasattr(pw, "list_toggle_btn"):
            pw._history_panel_visible = False
            pw.list_toggle_btn.setChecked(False)

    # -- Policy history ----------------------------------------------------

    def _add_to_history(self):
        region = self.region_combo.currentText()
        company = self.company_input.text().strip() or "01"
        policy = self.policy_input.text().strip()

        if policy:
            entry = (region, company, policy)
            if entry not in self._policy_history:
                self._policy_history.insert(0, entry)
                self._refresh_list()
            self.policy_input.clear()
            # Also trigger policy retrieval in the main window
            self.policy_selected.emit(region, company, policy)

    def add_policy(self, region: str, company: str, policy: str):
        """Add a policy to history (called externally)."""
        entry = (region, company, policy)
        if entry not in self._policy_history:
            self._policy_history.insert(0, entry)
            self._refresh_list()

    def _refresh_list(self):
        self.history_list.clear()
        for region, company, policy in self._policy_history:
            item = QListWidgetItem(f"{region} | {company} | {policy}")
            item.setData(Qt.ItemDataRole.UserRole, (region, company, policy))
            self.history_list.addItem(item)

    def _on_item_clicked(self, item: QListWidgetItem):
        data = item.data(Qt.ItemDataRole.UserRole)
        if data:
            region, company, policy = data
            self.policy_selected.emit(region, company, policy)

    def _show_context_menu(self, pos):
        """Show right-click context menu on a policy entry."""
        item = self.history_list.itemAt(pos)
        if not item:
            return

        menu = QMenu(self)
        delete_action = QAction("Delete", self)
        delete_action.triggered.connect(lambda: self._delete_item(item))
        menu.addAction(delete_action)
        menu.exec(self.history_list.viewport().mapToGlobal(pos))

    def _delete_item(self, item: QListWidgetItem):
        """Remove a single policy entry and evict its cache."""
        data = item.data(Qt.ItemDataRole.UserRole)
        if data:
            region, company, policy = data
            entry = (region, company, policy)
            if entry in self._policy_history:
                self._policy_history.remove(entry)
            self.policy_removed.emit(policy, region)
        row = self.history_list.row(item)
        self.history_list.takeItem(row)

    def _clear_all(self):
        """Remove all policy entries and clear all caches."""
        self._policy_history.clear()
        self.history_list.clear()
        self.all_policies_removed.emit()
