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
        self._table_data_cache = {}  # table_name -> has_data
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
    
    def rebuild_tree_with_data(self, db, where_clause: str, policy_id: str = None, company_code: str = None):
        """Rebuild tree showing only records/tables that have data.
        
        Args:
            db: Database connection
            where_clause: Standard WHERE clause with CK_SYS_CD, TCH_POL_ID, CK_CMP_CD
            policy_id: Policy ID for FH_ tables (which don't use CK_SYS_CD)
            company_code: Company code for FH_ tables
        """
        self.clear()
        self._table_data_cache.clear()
        
        # Build alternate WHERE clause for FH_ tables (no CK_SYS_CD)
        fh_where_clause = None
        if policy_id and company_code:
            fh_where_clause = f"TCH_POL_ID = '{policy_id}' AND CK_CMP_CD = '{company_code}'"
        
        for policy_record in get_sorted_policy_records():
            tables = POLICY_RECORD_TABLES.get(policy_record, [])
            tables_with_data = []
            
            # Check each table for data
            for table in tables:
                try:
                    # FH_ tables don't have CK_SYS_CD column - use alternate WHERE clause
                    if table.startswith("FH_") and fh_where_clause:
                        sql = f"SELECT 1 FROM DB2TAB.{table} WHERE {fh_where_clause} FETCH FIRST 1 ROWS ONLY"
                    else:
                        sql = f"SELECT 1 FROM DB2TAB.{table} WHERE {where_clause} FETCH FIRST 1 ROWS ONLY"
                    rows = db.execute_query(sql)
                    has_data = len(rows) > 0
                    self._table_data_cache[table] = has_data
                    if has_data:
                        tables_with_data.append(table)
                except Exception:
                    self._table_data_cache[table] = False
            
            # Only add policy record if it has tables with data
            if tables_with_data:
                # Add arrow indicator at start of text
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
        
        # Cache the freshly-built tables tree
        self._tables_snapshot = self._save_tree_snapshot()
    
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
          Policy
        """
        self.clear()
        self._mode = self.MODE_RATES
        self.setHeaderLabel("Rates")
        
        # Coverages branch (top-level)
        cov_node = QTreeWidgetItem([f"▶  Coverages"])
        cov_node.setData(0, Qt.ItemDataRole.UserRole, {"type": "record", "name": "Coverages"})
        self.addTopLevelItem(cov_node)
        
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
                top.addChild(child)
            if top_data["expanded"]:
                self.expandItem(top)

    def switch_to_tables_mode(self, db=None, where_clause=None, policy_id=None, company_code=None):
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
        elif db and where_clause:
            self.rebuild_tree_with_data(db, where_clause, policy_id, company_code)
    
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
        self._db = None
        self._where_clause = None
        self._policy_id = None
        self._company_code = None
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
            from PyQt6.QtWidgets import QApplication
            from PyQt6.QtGui import QCursor
            QApplication.setOverrideCursor(QCursor(Qt.CursorShape.WaitCursor))
            try:
                self._tree.switch_to_tables_mode(
                    self._db, self._where_clause, self._policy_id, self._company_code
                )
                self._update_tab_styles("tables")
                self.mode_changed.emit("tables")
            finally:
                QApplication.restoreOverrideCursor()
        elif tab == "rates" and self._tree.mode != PolicyRecordTreeWidget.MODE_RATES:
            if self._policy:
                self._tree.switch_to_rates_mode(self._policy)
                self._update_tab_styles("rates")
                self.mode_changed.emit("rates")
    
    # =========================================================================
    # Public API - forward to tree widget
    # =========================================================================
    
    @property
    def mode(self) -> str:
        return self._tree.mode
    
    def store_connection_info(self, db, where_clause: str, policy_id: str = None, company_code: str = None):
        """Store DB connection info for deferred/lazy table loading.
        
        Tables will be scanned only when the user clicks the Tables tab.
        """
        self._db = db
        self._where_clause = where_clause
        self._policy_id = policy_id
        self._company_code = company_code
    
    def show_rates_tab(self):
        """Switch to the Rates tab and build the rates tree if a policy is loaded."""
        if self._policy:
            self._tree.build_rates_tree(self._policy)
            self._update_tab_styles("rates")
    
    def rebuild_tree_with_data(self, db, where_clause: str, policy_id: str = None, company_code: str = None):
        """Rebuild tree showing only records/tables that have data."""
        # Cache connection info for tab switching
        self._db = db
        self._where_clause = where_clause
        self._policy_id = policy_id
        self._company_code = company_code
        self._tree.rebuild_tree_with_data(db, where_clause, policy_id, company_code)
    
    def build_rates_tree(self, policy: 'PolicyInformation'):
        """Build the rates tree from PolicyInformation."""
        self._policy = policy
        self._tree.build_rates_tree(policy)
    
    def switch_to_tables_mode(self, db=None, where_clause=None, policy_id=None, company_code=None):
        """Switch to Tables mode."""
        if db:
            self._db = db
        if where_clause:
            self._where_clause = where_clause
        if policy_id:
            self._policy_id = policy_id
        if company_code:
            self._company_code = company_code
        self._tree.switch_to_tables_mode(self._db, self._where_clause, self._policy_id, self._company_code)
        self._update_tab_styles("tables")
    
    def switch_to_rates_mode(self, policy: 'PolicyInformation'):
        """Switch to Rates mode."""
        self._policy = policy
        self._tree.switch_to_rates_mode(policy)
        self._update_tab_styles("rates")
    
    def reset_for_new_policy(self):
        """Reset state when a new policy is loaded."""
        self._tree.reset_for_new_policy()
        self._update_tab_styles("tables")
    
    def enable_rates_tab(self, policy: 'PolicyInformation'):
        """Enable the rates tab after policy is loaded."""
        self._policy = policy
        self._rates_btn.setEnabled(True)
        self._update_tab_styles(self._tree.mode)
    
    def disable_rates_tab(self):
        """Disable the rates tab."""
        self._rates_btn.setEnabled(False)
        self._update_tab_styles("tables")

    def get_tree_snapshot(self):
        """Return a serialisable snapshot of the current tables tree."""
        return self._tree._save_tree_snapshot()

    def restore_from_snapshot(self, snapshot, db=None, where_clause=None, policy_id=None, company_code=None):
        """Restore the tables tree from a cached snapshot (no DB queries)."""
        self._tree.reset_for_new_policy()
        if db:
            self._db = db
        if where_clause:
            self._where_clause = where_clause
        if policy_id:
            self._policy_id = policy_id
        if company_code:
            self._company_code = company_code
        self._tree._mode = self._tree.MODE_TABLES
        self._tree._restore_tree_snapshot(snapshot)
        self._tree._tables_snapshot = snapshot
        self._update_tab_styles("tables")

