"""
Left-panel tree widgets for navigating Policy Record tables and Rates.

Contains:
- PolicyRecordTreeWidget – tree listing DB2 tables with data
- PolicyRecordTreePanel  – wrapper with Tables/Rates tab header
"""

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout,
    QTreeWidget, QTreeWidgetItem, QPushButton,
)
from PyQt6.QtCore import Qt, pyqtSignal

from ..config.policy_records import POLICY_RECORD_TABLES, get_sorted_policy_records
from .styles import (
    BLUE_RICH, BLUE_GRADIENT_TOP, BLUE_PRIMARY, BLUE_DARK,
    GOLD_PRIMARY, GOLD_LIGHT, GOLD_TEXT,
    WHITE, GRAY_MID,
    TREE_WIDGET_STYLE,
)

from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from ..models.policy_information import PolicyInformation


class PolicyRecordTreeWidget(QTreeWidget):
    """Left panel tree showing Policy Records/Rates and their tables."""
    
    table_selected = pyqtSignal(str, str)  # policy_record, table_name
    rate_selected = pyqtSignal(str, str, int)  # category (Coverages/Benefits/Policy), label, index
    
    MODE_TABLES = "tables"
    MODE_RATES = "rates"
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setHeaderHidden(True)  # Hide native header - panel provides custom header
        self.setMinimumWidth(180)
        self._apply_compact_style()
        self.itemClicked.connect(self._on_item_clicked)
        self.itemExpanded.connect(self._on_item_expanded)
        self.itemCollapsed.connect(self._on_item_collapsed)
        self._table_data_cache = {}  # table_name -> True, False, or None on error
        self._mode = self.MODE_TABLES
        self._tables_snapshot = None  # saved tree state for tables mode
        self._rates_snapshot = None   # saved tree state for rates mode
        self._rates_loaded = False
    
    @property
    def mode(self) -> str:
        return self._mode
    
    def _apply_compact_style(self):
        """Apply compact styling with blue/gold theme."""
        self.setStyleSheet(TREE_WIDGET_STYLE)
        self.setIndentation(12)
        self.setRootIsDecorated(False)  # We'll add our own indicators
    
    def build_tables_tree(self, presence: dict):
        """Show only records/tables that have data, from a worker-computed map.

        *presence* maps table -> True (has rows), False (empty) or an error
        string (could not be read, shown explicitly rather than as empty).
        """
        self.clear()
        self._table_data_cache = {
            table: (value if isinstance(value, bool) else None)
            for table, value in presence.items()
        }
        for policy_record in get_sorted_policy_records():
            tables = POLICY_RECORD_TABLES.get(policy_record, [])
            tables_with_data = [t for t in tables if presence.get(t) is True]
            table_errors = [(t, presence[t]) for t in tables if isinstance(presence.get(t), str)]
            # Keep access failures visible instead of silently presenting them
            # as empty tables.
            if tables_with_data or table_errors:
                record_item = QTreeWidgetItem([f"▶  {policy_record}"])
                record_item.setData(0, Qt.ItemDataRole.UserRole, {"type": "record", "name": policy_record})
                self.addTopLevelItem(record_item)

                for table in tables_with_data:
                    table_item = QTreeWidgetItem([f"      {table}"])
                    table_item.setData(0, Qt.ItemDataRole.UserRole, {
                        "type": "table",
                        "name": table,
                        "record": policy_record
                    })
                    record_item.addChild(table_item)

                for table, error in table_errors:
                    error_item = QTreeWidgetItem([
                        f"      ⚠ {table} (unavailable)"
                    ])
                    error_item.setData(0, Qt.ItemDataRole.UserRole, {
                        "type": "table_error",
                        "name": table,
                        "record": policy_record,
                        "error": error,
                    })
                    error_item.setToolTip(
                        0,
                        "PolView could not check this DB2 table.\n\n"
                        f"{error}",
                    )
                    record_item.addChild(error_item)

        # Cache the freshly-built tables tree
        self._tables_snapshot = self._save_tree_snapshot()

    def show_placeholder(self, text: str, tooltip: str = ""):
        self.clear()
        item = QTreeWidgetItem([f"  {text}"])
        item.setData(0, Qt.ItemDataRole.UserRole, {"type": "placeholder"})
        item.setToolTip(0, tooltip)
        self.addTopLevelItem(item)
    
    def _on_item_expanded(self, item: QTreeWidgetItem):
        """Update arrow when expanded."""
        data = item.data(0, Qt.ItemDataRole.UserRole)
        if data and data.get("type") == "record":
            item.setText(0, f"▼  {data['name']}")
    
    def _on_item_collapsed(self, item: QTreeWidgetItem):
        """Update arrow when collapsed."""
        data = item.data(0, Qt.ItemDataRole.UserRole)
        if data and data.get("type") == "record":
            item.setText(0, f"▶  {data['name']}")
    
    def _on_item_clicked(self, item: QTreeWidgetItem, column: int):
        data = item.data(0, Qt.ItemDataRole.UserRole)
        if data:
            if data.get("type") == "record":
                # Toggle expand/collapse on single click for record items
                if item.isExpanded():
                    self.collapseItem(item)
                else:
                    self.expandItem(item)
            elif data.get("type") == "table":
                self.table_selected.emit(data["record"], data["name"])
            elif data.get("type") == "rate_leaf":
                # Rates tree leaf node clicked
                category = data.get("category", "")
                label = data.get("label", "")
                index = data.get("index", 0)
                self.rate_selected.emit(category, label, index)
    
    def build_rates_tree(self, policy: 'PolicyInformation'):
        """Build the rates tree from PolicyInformation coverage/benefit data.
        
        Tree structure (top-level nodes, no wrapper):
          ▶ Coverages
          │   ├── Cov 01 (plancode)
          │   ├── Cov 02 (plancode)
          │   └── ...
          ▶ Benefits
          │   ├── Ben 01 (typecode)
          │   └── ...
          ▶ Fixed Premium        (ISWL / traditional WL only)
          │   ├── Cash Values Cov 01   (ISWL; WL shows CVs on Coverages)
          │   ├── Premium Rates Cov 01
          │   └── Modal Premium
          Policy
        """
        self.clear()
        self._mode = self.MODE_RATES
        self.setHeaderLabel("Rates")
        
        # Coverages branch (top-level)
        cov_node = QTreeWidgetItem([f"▶  Coverages"])
        cov_node.setData(0, Qt.ItemDataRole.UserRole, {"type": "record", "name": "Coverages"})
        self.addTopLevelItem(cov_node)
        whole_life = not policy.is_advanced_product and policy.product_type == "WL"
        for i in range(1, policy.coverage_count + 1):
            plancode = policy.cov_plancode(i)
            label = f"Cov {i:02d} ({plancode})"
            cov_item = QTreeWidgetItem([f"      {label}"])
            cov_item.setData(0, Qt.ItemDataRole.UserRole, {
                "type": "rate_leaf",
                "category": "Coverages",
                "label": label,
                "index": i
            })
            if whole_life:
                cov_item.setToolTip(
                    0, "Cash values from WL_RATE_CV by CyberLife user, class/base/sub and issue age.\n"
                    "NSP, PUI and dividend rate lookups are not yet available."
                )
            elif policy.product_type == "ISWL":
                cov_item.setToolTip(
                    0, "UL-style rates (current-scale COI), GINT, CVR, premium rate, loans and cease ages.\n"
                    "Cash values, premium rates and modal factors are under Fixed Premium."
                )
            cov_node.addChild(cov_item)
        
        # Benefits branch (top-level)
        ben_node = QTreeWidgetItem([f"▶  Benefits"])
        ben_node.setData(0, Qt.ItemDataRole.UserRole, {"type": "record", "name": "Benefits"})
        self.addTopLevelItem(ben_node)
        
        benefits = policy.get_benefits()
        for i in range(1, policy.benefit_count + 1):
            type_code = benefits[i - 1].benefit_type_cd if i <= len(benefits) else ""
            label = f"Ben {i:02d} ({type_code})"
            ben_item = QTreeWidgetItem([f"      {label}"])
            ben_item.setData(0, Qt.ItemDataRole.UserRole, {
                "type": "rate_leaf",
                "category": "Benefits",
                "label": label,
                "index": i
            })
            ben_node.addChild(ben_item)

        if policy.has_fixed_premium_rates:
            self._add_fixed_premium_branch(policy, whole_life)
        
        # Policy node (top-level leaf)
        policy_node = QTreeWidgetItem(["  Policy"])
        policy_node.setData(0, Qt.ItemDataRole.UserRole, {
            "type": "rate_leaf",
            "category": "Policy",
            "label": "Policy",
            "index": 1
        })
        self.addTopLevelItem(policy_node)
        
        self._rates_loaded = True

    def _add_fixed_premium_branch(self, policy: 'PolicyInformation', whole_life: bool):
        """ISWL/WL fixed-premium sources. WL cash values stay on the Coverages leaves."""
        node = QTreeWidgetItem(["▶  Fixed Premium"])
        node.setData(0, Qt.ItemDataRole.UserRole, {"type": "record", "name": "Fixed Premium"})
        self.addTopLevelItem(node)
        leaves = []
        for i in range(1, policy.coverage_count + 1):
            if not whole_life:
                leaves.append(("Cash Values", f"Cash Values Cov {i:02d}", i,
                               "Guaranteed cash values from WL_RATE_CV (CVF) by duration."))
            leaves.append(("Premium Rates", f"Premium Rates Cov {i:02d}", i,
                           "IAF premiums from WL_RATE_PREM for the base plan and its benefits."))
        leaves.append(("Modal Premium", "Modal Premium", 1,
                       "Annual premium x RATE_MODEFACT mode factor plus policy fee,\n"
                       "compared with LH_BAS_POL.POL_PRM_AMT."))
        for category, label, index, tooltip in leaves:
            item = QTreeWidgetItem([f"      {label}"])
            item.setData(0, Qt.ItemDataRole.UserRole, {
                "type": "rate_leaf", "category": category, "label": label, "index": index,
            })
            item.setToolTip(0, tooltip)
            node.addChild(item)
    
    def _save_tree_snapshot(self):
        """Save the current tree items as a serializable snapshot."""
        snapshot = []
        for i in range(self.topLevelItemCount()):
            top = self.topLevelItem(i)
            top_data = {
                "text": top.text(0),
                "user_data": top.data(0, Qt.ItemDataRole.UserRole),
                "expanded": top.isExpanded(),
                "children": []
            }
            for j in range(top.childCount()):
                child = top.child(j)
                top_data["children"].append({
                    "text": child.text(0),
                    "user_data": child.data(0, Qt.ItemDataRole.UserRole),
                    "tooltip": child.toolTip(0),
                })
            snapshot.append(top_data)
        return snapshot

    def _restore_tree_snapshot(self, snapshot):
        """Restore tree items from a saved snapshot."""
        self.clear()
        for top_data in snapshot:
            top = QTreeWidgetItem([top_data["text"]])
            top.setData(0, Qt.ItemDataRole.UserRole, top_data["user_data"])
            self.addTopLevelItem(top)
            for child_data in top_data["children"]:
                child = QTreeWidgetItem([child_data["text"]])
                child.setData(0, Qt.ItemDataRole.UserRole, child_data["user_data"])
                child.setToolTip(0, child_data.get("tooltip", ""))
                top.addChild(child)
            if top_data["expanded"]:
                self.expandItem(top)

    def switch_to_tables_mode(self, presence=None, pending_message: str = "Checking which tables have data…"):
        """Switch back to Tables mode, restoring from cache if available."""
        if self._mode == self.MODE_TABLES:
            return
        # Save current rates tree before switching
        self._rates_snapshot = self._save_tree_snapshot()
        self._mode = self.MODE_TABLES
        self.setHeaderLabel("Tables")
        if self._tables_snapshot:
            # Restore cached tables tree — no DB re-query needed
            self._restore_tree_snapshot(self._tables_snapshot)
        elif presence is not None:
            self.build_tables_tree(presence)
        else:
            self.show_placeholder(pending_message,
                                  "Tables are checked in the background after the policy tabs load.")
    
    def switch_to_rates_mode(self, policy: 'PolicyInformation'):
        """Switch to Rates mode, restoring from cache if available."""
        if self._mode == self.MODE_RATES:
            return
        # Save current tables tree before switching
        self._tables_snapshot = self._save_tree_snapshot()
        if self._rates_loaded and self._rates_snapshot:
            # Restore cached rates tree — no rebuild needed
            self._mode = self.MODE_RATES
            self.setHeaderLabel("Rates")
            self._restore_tree_snapshot(self._rates_snapshot)
        else:
            self.build_rates_tree(policy)
    
    def reset_for_new_policy(self):
        """Reset state when a new policy is loaded."""
        self._rates_loaded = False
        self._mode = self.MODE_TABLES
        self._tables_snapshot = None
        self._rates_snapshot = None


class PolicyRecordTreePanel(QWidget):
    """Panel containing a tab-style header (Tables/Rates) and the tree widget.
    
    This solves the scrollbar overlap issue by separating the header from
    the scrollable tree content.
    """
    
    # Forward signals from the tree
    table_selected = pyqtSignal(str, str)
    rate_selected = pyqtSignal(str, str, int)
    mode_changed = pyqtSignal(str)  # "tables" or "rates"
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self._policy = None
        self._presence = None
        self._presence_error = ""
        self._setup_ui()
    
    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        
        # Header bar with tab-style buttons
        header = QWidget()
        header.setFixedHeight(28)
        header.setStyleSheet(f"""
            QWidget {{
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    stop:0 {BLUE_GRADIENT_TOP}, stop:1 {BLUE_RICH});
                border: 2px solid {BLUE_PRIMARY};
                border-bottom: none;
                border-top-left-radius: 4px;
                border-top-right-radius: 4px;
            }}
        """)
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(4, 2, 4, 2)
        header_layout.setSpacing(4)
        
        # Tab-style buttons
        self._tables_btn = QPushButton("Tables")
        self._rates_btn = QPushButton("Rates")
        
        for btn in (self._tables_btn, self._rates_btn):
            btn.setFixedHeight(22)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
        
        self._update_tab_styles("tables")  # Tables selected by default
        
        self._tables_btn.clicked.connect(lambda: self._on_tab_clicked("tables"))
        self._rates_btn.clicked.connect(lambda: self._on_tab_clicked("rates"))
        
        header_layout.addWidget(self._tables_btn)
        header_layout.addWidget(self._rates_btn)
        header_layout.addStretch()
        
        layout.addWidget(header)
        
        # Tree widget (no header, scrollbar won't overlap)
        self._tree = PolicyRecordTreeWidget()
        self._tree.setStyleSheet(TREE_WIDGET_STYLE + f"""
            QTreeWidget {{
                border-top: none;
                border-top-left-radius: 0px;
                border-top-right-radius: 0px;
            }}
        """)
        self._tree.table_selected.connect(self.table_selected.emit)
        self._tree.rate_selected.connect(self.rate_selected.emit)
        layout.addWidget(self._tree)
        
        # Rates button disabled until policy loaded
        self._rates_btn.setEnabled(False)
    
    def _update_tab_styles(self, active_tab: str):
        """Update button styles based on which tab is active."""
        active_style = f"""
            QPushButton {{
                background-color: {WHITE};
                color: {BLUE_DARK};
                border: 1px solid {GOLD_PRIMARY};
                border-radius: 3px;
                font-size: 11px;
                font-weight: bold;
                padding: 2px 12px;
            }}
        """
        inactive_style = f"""
            QPushButton {{
                background: transparent;
                color: {GOLD_TEXT};
                border: 1px solid transparent;
                border-radius: 3px;
                font-size: 11px;
                font-weight: normal;
                padding: 2px 12px;
            }}
            QPushButton:hover {{
                background-color: rgba(255, 255, 255, 0.1);
                border: 1px solid {GOLD_LIGHT};
            }}
        """
        disabled_style = f"""
            QPushButton {{
                background: transparent;
                color: {GRAY_MID};
                border: 1px solid transparent;
                border-radius: 3px;
                font-size: 11px;
                font-weight: normal;
                padding: 2px 12px;
            }}
        """
        
        if active_tab == "tables":
            self._tables_btn.setStyleSheet(active_style)
            if self._rates_btn.isEnabled():
                self._rates_btn.setStyleSheet(inactive_style)
            else:
                self._rates_btn.setStyleSheet(disabled_style)
        else:
            self._rates_btn.setStyleSheet(active_style)
            self._tables_btn.setStyleSheet(inactive_style)
    
    def _on_tab_clicked(self, tab: str):
        """Handle tab button click."""
        if tab == "tables" and self._tree.mode != PolicyRecordTreeWidget.MODE_TABLES:
            self._tree.switch_to_tables_mode(self._presence, self._pending_text())
            self._update_tab_styles("tables")
            self.mode_changed.emit("tables")
        elif tab == "rates" and self._tree.mode != PolicyRecordTreeWidget.MODE_RATES:
            if self._policy:
                self._tree.switch_to_rates_mode(self._policy)
                self._update_tab_styles("rates")
                self.mode_changed.emit("rates")

    def _pending_text(self) -> str:
        if self._presence_error:
            return "⚠ Could not check tables"
        return "Checking which tables have data…"
    
    # =========================================================================
    # Public API - forward to tree widget
    # =========================================================================
    
    @property
    def mode(self) -> str:
        return self._tree.mode

    def set_table_presence(self, presence: dict):
        """Receive the background table check; refresh the tree if it is waiting."""
        self._presence = dict(presence or {})
        self._presence_error = ""
        if self._tree.mode == PolicyRecordTreeWidget.MODE_TABLES:
            self._tree.build_tables_tree(self._presence)

    def set_table_presence_error(self, error: str):
        self._presence_error = error or "Unknown error"
        if self._tree.mode == PolicyRecordTreeWidget.MODE_TABLES and self._presence is None:
            self._tree.show_placeholder("⚠ Could not check tables", self._presence_error)
    
    def show_rates_tab(self):
        """Switch to the Rates tab and build the rates tree if a policy is loaded."""
        if self._policy:
            self._tree.build_rates_tree(self._policy)
            self._update_tab_styles("rates")
    
    def build_rates_tree(self, policy: 'PolicyInformation'):
        """Build the rates tree from PolicyInformation."""
        self._policy = policy
        self._tree.build_rates_tree(policy)
    
    def switch_to_tables_mode(self):
        """Switch to Tables mode."""
        self._tree.switch_to_tables_mode(self._presence, self._pending_text())
        self._update_tab_styles("tables")
    
    def switch_to_rates_mode(self, policy: 'PolicyInformation'):
        """Switch to Rates mode."""
        self._policy = policy
        self._tree.switch_to_rates_mode(policy)
        self._update_tab_styles("rates")
    
    def reset_for_new_policy(self):
        """Reset state when a new policy is loaded."""
        self._presence = None
        self._presence_error = ""
        self._tree.reset_for_new_policy()
        self._update_tab_styles("tables")
    
    def enable_rates_tab(self, policy: 'PolicyInformation'):
        """Enable the rates tab after policy is loaded."""
        self._policy = policy
        self._rates_btn.setEnabled(True)
        self._update_tab_styles(self._tree.mode)
