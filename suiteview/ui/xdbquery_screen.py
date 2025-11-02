"""XDB Query Screen - Cross-database query builder"""

import logging
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QSplitter,
    QTreeWidget, QTreeWidgetItem, QPushButton, QFrame, QMenu,
    QScrollArea, QComboBox, QMessageBox, QFileDialog, QTabWidget,
    QLineEdit, QCheckBox, QDateEdit, QToolButton, QSizePolicy
)
from PyQt6.QtCore import Qt, QDate, pyqtSignal
from PyQt6.QtGui import QAction, QDrag
from typing import Optional

from suiteview.data.repositories import (ConnectionRepository, get_query_repository, 
                                         get_saved_table_repository, SavedTableRepository)
from suiteview.core.schema_discovery import SchemaDiscovery
from suiteview.core.query_executor_xdb import XDBQueryExecutor
from suiteview.ui.dialogs.query_results_dialog import QueryResultsDialog

logger = logging.getLogger(__name__)


class CascadingMenuWidget(QWidget):
    """Simple widget with vertically stacked buttons that show cascading menus on click"""

    def __init__(self, parent=None):
        super().__init__(parent)

        # Create vertical layout
        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(0, 0, 0, 0)
        self.layout.setSpacing(0)
        self.layout.setAlignment(Qt.AlignmentFlag.AlignTop)

        # Track currently open menu
        self.current_button = None
        self.current_menu = None

        # Style for the container
        self.setStyleSheet(
            """
            QWidget { background: white; }
            """
        )

    def add_menu_item(self, text, menu, enabled=True):
        """Add a button with a cascading menu"""
        btn = QPushButton(text, self)
        btn.setEnabled(enabled)

        # Style the button to look like tree items - tight and compact
        btn.setStyleSheet(
            """
            QPushButton {
                background: white;
                border: none;
                border-bottom: 1px solid #ddd;
                padding: 2px 8px;
                text-align: left;
                font-size: 11px;
                color: #333;
                min-height: 18px;
                max-height: 18px;
            }
            QPushButton:hover { background: #e3f2fd; }
            QPushButton:pressed { background: #bbdefb; }
            """
        )

        # Connect click to show menu to the right
        btn.clicked.connect(lambda: self._show_menu_to_right(btn, menu))

        self.layout.addWidget(btn)

    def _show_menu_to_right(self, button, menu):
        """Show the menu to the right of the button, or close if already open"""
        # If this button's menu is already open, close it
        if self.current_button == button and self.current_menu and self.current_menu.isVisible():
            self.current_menu.close()
            self.current_button = None
            self.current_menu = None
            return

        # Close any previously open menu
        if self.current_menu and self.current_menu.isVisible():
            self.current_menu.close()

        # Get the button's geometry
        button_rect = button.rect()
        # Calculate position to the right of the button
        global_pos = button.mapToGlobal(button_rect.topRight())

        # Show the menu (non-blocking)
        menu.popup(global_pos)

        # Track this as the current menu
        self.current_button = button
        self.current_menu = menu

        # Connect to aboutToHide to clear tracking when menu closes
        menu.aboutToHide.connect(lambda: self._on_menu_closed())

    def _on_menu_closed(self):
        """Clear tracking when menu closes"""
        self.current_button = None
        self.current_menu = None

    def add_separator(self):
        """Add a visual separator"""
        separator = QFrame(self)
        separator.setFrameShape(QFrame.Shape.HLine)
        separator.setFrameShadow(QFrame.Shadow.Sunken)
        separator.setMaximumHeight(1)
        separator.setStyleSheet("background: #ddd;")
        self.layout.addWidget(separator)

    def clear(self):
        """Remove all items"""
        while self.layout.count():
            item = self.layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()


class XDBQueryScreen(QWidget):
    """XDB Query screen with four-panel layout (mirrors DB Query look-and-feel)"""

    def __init__(self):
        super().__init__()
        self.conn_repo = ConnectionRepository()
        self.query_repo = get_query_repository()
        self.saved_table_repo = get_saved_table_repository()
        self.schema_discovery = SchemaDiscovery()
        self.xdb_executor = XDBQueryExecutor(use_duckdb=True)
        # Track selection
        self.current_connection_id = None
        self.current_schema_name = None
        # Track XDB sources
        self.source_a = {}
        self.source_b = {}
        # Track datasources (connection + table pairs)
        self.datasources = []  # List of {connection, table_name, schema_name, alias}
        # Track display fields and criteria filters
        self.display_fields = []  # List of field_data dicts
        self.criteria_widgets = []  # List of CriteriaFilterWidget instances
        # Track selected tables for XDB query building
        self.selected_tables = {}  # Dict: {connection_id: [table_names]}
        self.init_ui()
        self.load_data_sources()

    def init_ui(self):
        """Initialize the UI"""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        # Create horizontal splitter for four panels
        splitter = QSplitter(Qt.Orientation.Horizontal)

        # Left Panel 1 - Data Sources (Databases + XDB Queries)
        panel1 = self._create_data_sources_panel()
        panel1.setMinimumWidth(20)
        splitter.addWidget(panel1)

        # Left Panel 2 - Tables
        panel2 = self._create_tables_panel()
        panel2.setMinimumWidth(20)
        splitter.addWidget(panel2)

        # Left Panel 3 - Fields
        panel3 = self._create_fields_panel()
        panel3.setMinimumWidth(20)
        splitter.addWidget(panel3)

        # Right Panel - XDB Query Builder
        right_panel = self._create_builder_panel()
        right_panel.setMinimumWidth(200)
        splitter.addWidget(right_panel)

        # Set initial sizes (200px, 200px, 200px, remaining)
        splitter.setSizes([200, 200, 200, 600])

        layout.addWidget(splitter)

    def _create_tables_panel(self) -> QWidget:
        """Create middle panel with tables list (hierarchical: Database → Tables)"""
        panel = QWidget()
        panel_layout = QVBoxLayout(panel)
        panel_layout.setContentsMargins(5, 5, 5, 5)

        self.tables_header = QLabel("TABLES (Select from databases)")
        self.tables_header.setObjectName("panel_header")
        panel_layout.addWidget(self.tables_header)

        # Search box
        # Keeping structure similar to DB Query; hook up later if needed
        # Using a simple placeholder to keep compact look
        self.tables_search = QLabel("")
        self.tables_search.setVisible(False)
        panel_layout.addWidget(self.tables_search)

        self.tables_tree = QTreeWidget()
        self.tables_tree.setHeaderHidden(True)
        self.tables_tree.setStyleSheet(
            """
            QTreeWidget { background: white; border: 1px solid #ddd; border-radius: 4px; }
            QTreeWidget::item { height: 18px; padding: 0px 2px; }
            QTreeWidget::item:hover { background-color: #b3d9ff; }
            QTreeWidget::item:selected { background-color: #b3d9ff; }
            """
        )
        self.tables_tree.itemClicked.connect(self._on_table_clicked)
        self.tables_tree.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.tables_tree.customContextMenuRequested.connect(self._show_table_context_menu)
        panel_layout.addWidget(self.tables_tree)

        return panel
        self.tables_tree.itemClicked.connect(self._on_table_clicked)
        panel_layout.addWidget(self.tables_tree)

        return panel

    def _create_fields_panel(self) -> QWidget:
        """Create left third panel with fields list"""
        panel = QWidget()
        panel_layout = QVBoxLayout(panel)
        panel_layout.setContentsMargins(5, 5, 5, 5)

        header = QLabel("FIELDS")
        header.setObjectName("panel_header")
        panel_layout.addWidget(header)

        self.fields_tree = QTreeWidget()
        self.fields_tree.setHeaderHidden(True)
        self.fields_tree.setStyleSheet(
            """
            QTreeWidget { background: white; border: 1px solid #ddd; border-radius: 4px; }
            QTreeWidget::item { height: 18px; padding: 0px 2px; }
            QTreeWidget::item:hover { background-color: #b3d9ff; }
            QTreeWidget::item:selected { background-color: #b3d9ff; }
            """
        )
        self.fields_tree.itemDoubleClicked.connect(self._on_field_double_clicked)
        panel_layout.addWidget(self.fields_tree)

        return panel

    def _create_builder_panel(self) -> QWidget:
        """Create the XDB query builder panel with 3 tabs: Display, Criteria, Datasources"""
        panel = QWidget()
        panel_layout = QVBoxLayout(panel)
        panel_layout.setContentsMargins(5, 5, 5, 5)
        panel_layout.setSpacing(5)

        # Toolbar with Run Query, Save Query, and New Query buttons
        toolbar_layout = QHBoxLayout()
        toolbar_layout.setContentsMargins(10, 5, 10, 5)
        toolbar_layout.setSpacing(10)

        # Left side: Run and Save buttons
        self.run_query_btn = QPushButton("▶ Run Query")
        self.run_query_btn.setObjectName("gold_button")
        self.run_query_btn.setMinimumWidth(120)
        self.run_query_btn.clicked.connect(self._run_query)
        toolbar_layout.addWidget(self.run_query_btn)

        self.save_query_btn = QPushButton("💾 Save Query")
        self.save_query_btn.setObjectName("gold_button")
        self.save_query_btn.setMinimumWidth(120)
        self.save_query_btn.clicked.connect(self._save_query)
        toolbar_layout.addWidget(self.save_query_btn)

        # Center: Query name label
        self.query_name_label = QLabel("unnamed")
        self.query_name_label.setStyleSheet("""
            QLabel {
                color: #95a5a6;
                font-size: 16px;
                font-style: italic;
                padding: 5px 20px;
            }
        """)
        toolbar_layout.addWidget(self.query_name_label)
        
        # Add stretch to push New Query button to the right
        toolbar_layout.addStretch()

        # Right side: New Query button
        self.new_query_btn = QPushButton("📄 New Query")
        self.new_query_btn.setObjectName("gold_button")
        self.new_query_btn.setMinimumWidth(120)
        self.new_query_btn.clicked.connect(self._new_query)
        toolbar_layout.addWidget(self.new_query_btn)

        # Add toolbar layout to panel
        toolbar_container = QWidget()
        toolbar_container.setLayout(toolbar_layout)
        toolbar_container.setStyleSheet("""
            QWidget {
                background: #f8f9fa;
                border-bottom: 1px solid #ddd;
            }
        """)
        panel_layout.addWidget(toolbar_container)

        # Tab widget for Display, Criteria, Datasources
        self.xdb_tabs = QTabWidget()
        self.xdb_tabs.setStyleSheet("""
            QTabWidget::pane {
                border: 1px solid #ddd;
                background: white;
            }
            QTabBar::tab {
                padding: 10px 20px;
                margin-right: 2px;
                background: #e8e8e8;
                color: #2c3e50;
                font-weight: 600;
            }
            QTabBar::tab:selected {
                background: white;
                border-bottom: 3px solid #667eea;
                color: #2c3e50;
            }
            QTabBar::tab:!selected {
                background: #e8e8e8;
                color: #5a6c7d;
            }
            QTabBar::tab:hover {
                background: #d4d4d4;
            }
        """)

        # Display tab (FIRST)
        self.display_tab = self._create_display_tab()
        self.xdb_tabs.addTab(self.display_tab, "Display")

        # Criteria tab (SECOND)
        self.criteria_tab = self._create_criteria_tab()
        self.xdb_tabs.addTab(self.criteria_tab, "Criteria")

        # Datasources tab (THIRD - replaces Tables)
        self.datasources_tab = self._create_datasources_tab()
        self.xdb_tabs.addTab(self.datasources_tab, "Datasources")

        panel_layout.addWidget(self.xdb_tabs)

        return panel
    
    def _create_display_tab(self) -> QWidget:
        """Create Display tab for field selection"""
        tab = QWidget()
        tab.setAcceptDrops(True)
        
        layout = QVBoxLayout(tab)
        layout.setContentsMargins(10, 10, 10, 10)

        # Instructions
        instructions = QLabel("Drag fields here to add to SELECT list")
        instructions.setStyleSheet("color: #7f8c8d; font-style: italic; padding: 10px;")
        layout.addWidget(instructions)

        # Scroll area for display fields
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet("QScrollArea { border: none; background: transparent; }")

        self.display_container = QWidget()
        self.display_layout = QVBoxLayout(self.display_container)
        self.display_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        self.display_layout.setSpacing(10)

        scroll.setWidget(self.display_container)
        layout.addWidget(scroll)

        return tab
    
    def _create_criteria_tab(self) -> QWidget:
        """Create Criteria tab for filters"""
        tab = QWidget()
        tab.setAcceptDrops(True)
        
        layout = QVBoxLayout(tab)
        layout.setContentsMargins(10, 10, 10, 10)

        # Instructions
        instructions = QLabel("Drag fields here to add filter criteria")
        instructions.setStyleSheet("color: #7f8c8d; font-style: italic; padding: 10px;")
        layout.addWidget(instructions)

        # Scroll area for criteria widgets
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet("QScrollArea { border: none; background: transparent; }")

        self.criteria_container = QWidget()
        self.criteria_layout = QVBoxLayout(self.criteria_container)
        self.criteria_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        self.criteria_layout.setSpacing(10)

        scroll.setWidget(self.criteria_container)
        layout.addWidget(scroll)

        return tab
    
    def _create_datasources_tab(self) -> QWidget:
        """Create Datasources tab with connection+table selection and join configuration"""
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setContentsMargins(10, 10, 10, 10)

        # Tables involved section (showing Datasource.TableName format)
        tables_label = QLabel("Tables Involved:")
        tables_label.setStyleSheet("font-weight: bold; padding: 5px;")
        layout.addWidget(tables_label)

        self.datasources_involved_label = QLabel("(None)")
        self.datasources_involved_label.setStyleSheet("color: #7f8c8d; padding: 5px 5px 15px 20px;")
        layout.addWidget(self.datasources_involved_label)

        # Add Datasource button (to add datasources to the query)
        add_ds_layout = QHBoxLayout()
        self.add_datasource_btn = QPushButton("+ Add Datasource")
        self.add_datasource_btn.setObjectName("gold_button")
        self.add_datasource_btn.clicked.connect(self._add_datasource)
        add_ds_layout.addWidget(self.add_datasource_btn)
        add_ds_layout.addStretch()
        layout.addLayout(add_ds_layout)
        
        layout.addSpacing(10)

        # FROM clause section
        from_layout = QHBoxLayout()
        from_label = QLabel("FROM:")
        from_label.setStyleSheet("font-weight: bold;")
        from_layout.addWidget(from_label)

        self.from_datasource_combo = QComboBox()
        self.from_datasource_combo.setMinimumWidth(200)
        from_layout.addWidget(self.from_datasource_combo)
        from_layout.addStretch()

        layout.addLayout(from_layout)

        # JOIN section
        layout.addSpacing(20)
        join_header_layout = QHBoxLayout()
        join_label = QLabel("JOINS:")
        join_label.setStyleSheet("font-weight: bold;")
        join_header_layout.addWidget(join_label)
        join_header_layout.addStretch()

        self.add_join_btn = QPushButton("+ Add Join")
        self.add_join_btn.setObjectName("gold_button")
        self.add_join_btn.clicked.connect(self._add_join)
        join_header_layout.addWidget(self.add_join_btn)

        layout.addLayout(join_header_layout)

        # Scroll area for joins
        join_scroll = QScrollArea()
        join_scroll.setWidgetResizable(True)
        join_scroll.setStyleSheet("QScrollArea { border: none; background: transparent; }")

        self.joins_container = QWidget()
        self.joins_layout = QVBoxLayout(self.joins_container)
        self.joins_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        self.joins_layout.setSpacing(10)

        join_scroll.setWidget(self.joins_container)
        layout.addWidget(join_scroll)

        layout.addStretch()

        return tab

    def _create_data_sources_panel(self) -> QWidget:
        """Create left panel with two sections: Databases and XDB Queries"""
        panel = QWidget()
        panel_layout = QVBoxLayout(panel)
        panel_layout.setContentsMargins(5, 5, 5, 5)
        panel_layout.setSpacing(10)

        # Databases section
        databases_header = QLabel("DATABASES")
        databases_header.setObjectName("panel_header")
        panel_layout.addWidget(databases_header)

        # Cascading list of database types with menus
        self.data_sources_list = CascadingMenuWidget(self)
        panel_layout.addWidget(self.data_sources_list, stretch=1)

        # XDB Queries section
        queries_header = QLabel("XDB QUERIES")
        queries_header.setObjectName("panel_header")
        panel_layout.addWidget(queries_header)

        self.xdb_queries_tree = QTreeWidget()
        self.xdb_queries_tree.setHeaderHidden(True)
        self.xdb_queries_tree.setStyleSheet(
            """
            QTreeWidget { background: white; border: 1px solid #ddd; border-radius: 4px; }
            QTreeWidget::item { height: 18px; padding: 0px 2px; }
            QTreeWidget::item:hover { background-color: #b3d9ff; }
            QTreeWidget::item:selected { background-color: #b3d9ff; }
            """
        )
        self.xdb_queries_tree.itemClicked.connect(self._on_xdb_query_clicked)
        self.xdb_queries_tree.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.xdb_queries_tree.customContextMenuRequested.connect(self._show_xdb_query_context_menu)
        panel_layout.addWidget(self.xdb_queries_tree, stretch=1)

        return panel

    # --------------------- Data loading ---------------------
    def load_data_sources(self):
        """Load databases and XDB queries into the left panel"""
        try:
            self.data_sources_list.clear()
            self.xdb_queries_tree.clear()

            self._load_my_connections()
            self._load_xdb_queries_tree()
            logger.info("XDB data sources loaded")
        except Exception as e:
            logger.error(f"Error loading XDB data sources: {e}")

    def _load_my_connections(self):
        """Create cascading menu items for each connection type with tables as sub-menus"""
        all_connections = self.conn_repo.get_all_connections()

        # Group by type (already standardized in DB): SQL_SERVER, DB2, ACCESS, EXCEL, CSV, FIXED_WIDTH
        types_dict = {}
        for conn in all_connections:
            conn_type = conn.get('connection_type', 'Unknown')
            types_dict.setdefault(conn_type, []).append(conn)

        type_order = ['DB2', 'SQL_SERVER', 'ACCESS', 'EXCEL', 'CSV', 'FIXED_WIDTH']

        for t in type_order:
            if t not in types_dict:
                continue

            type_menu = QMenu(self)
            for conn in sorted(types_dict[t], key=lambda c: c['connection_name']):
                # Create submenu for this connection showing its My Data tables
                conn_menu = QMenu(conn['connection_name'], self)
                
                # Load My Data tables for this connection
                try:
                    saved_tables = self.saved_table_repo.get_saved_tables(conn['connection_id'])
                    
                    if saved_tables:
                        for table in saved_tables:
                            # Build display name
                            if table['schema_name']:
                                display_name = f"{table['schema_name']}.{table['table_name']}"
                            else:
                                display_name = table['table_name']
                            
                            # Create action for this table
                            table_action = QAction(display_name, self)
                            table_action.triggered.connect(
                                lambda checked, c=conn, t=table: self._add_table_to_list(c, t)
                            )
                            conn_menu.addAction(table_action)
                    else:
                        # No tables in My Data for this connection
                        no_tables_action = QAction("(No tables in My Data)", self)
                        no_tables_action.setEnabled(False)
                        conn_menu.addAction(no_tables_action)
                        
                except Exception as e:
                    logger.error(f"Failed to load tables for connection {conn['connection_id']}: {e}")
                    error_action = QAction("(Error loading tables)", self)
                    error_action.setEnabled(False)
                    conn_menu.addAction(error_action)
                
                type_menu.addMenu(conn_menu)

            self.data_sources_list.add_menu_item(t, type_menu)

    def _load_xdb_queries_tree(self):
        """Populate the XDB Queries tree widget"""
        queries = self.query_repo.get_all_queries(query_type='XDB')
        for q in queries:
            item = QTreeWidgetItem([q['query_name']])
            item.setData(0, Qt.ItemDataRole.UserRole, q['query_id'])
            item.setData(0, Qt.ItemDataRole.UserRole + 1, q.get('query_definition', ''))
            self.xdb_queries_tree.addTopLevelItem(item)
        logger.info(f"Loaded {len(queries)} XDB queries into tree")

    # --------------------- Event handlers ---------------------
    def _on_xdb_query_clicked(self, item: QTreeWidgetItem, column: int):
        """Load selected XDB query (placeholder hook)"""
        qid = item.data(0, Qt.ItemDataRole.UserRole)
        _qdef = item.data(0, Qt.ItemDataRole.UserRole + 1)
        logger.info(f"XDB query selected: {qid}")
        # A full load into the builder will be implemented in the next phase.

    def _show_xdb_query_context_menu(self, position):
        item = self.xdb_queries_tree.itemAt(position)
        if not item:
            return
        query_id = item.data(0, Qt.ItemDataRole.UserRole)
        query_name = item.text(0)

        menu = QMenu(self)
        rename_action = menu.addAction("✏️ Rename")
        copy_action = menu.addAction("📋 Copy")
        delete_action = menu.addAction("🗑️ Delete")
        action = menu.exec(self.xdb_queries_tree.mapToGlobal(position))

        # Forward to DB query handlers once shared helpers exist; placeholders for now
        if action == rename_action:
            logger.info(f"Rename XDB query requested: {query_id} {query_name}")
        elif action == copy_action:
            logger.info(f"Copy XDB query requested: {query_id} {query_name}")
        elif action == delete_action:
            logger.info(f"Delete XDB query requested: {query_id} {query_name}")

    def _on_connection_selected(self, connection_id: int):
        """Legacy method - no longer used with new cascading table selection"""
        # This method is deprecated - tables are now added via _add_table_to_list
        pass

    def _add_table_to_list(self, connection: dict, table: dict):
        """Add a table to the Tables list with Database as parent node"""
        try:
            connection_id = connection['connection_id']
            connection_name = connection['connection_name']
            table_name = table['table_name']
            schema_name = table.get('schema_name')
            
            # Build display name for table
            if schema_name:
                table_display = f"{schema_name}.{table_name}"
            else:
                table_display = table_name
            
            # Check if table already added
            root = self.tables_tree.invisibleRootItem()
            for i in range(root.childCount()):
                db_node = root.child(i)
                db_conn_id = db_node.data(0, Qt.ItemDataRole.UserRole)
                if db_conn_id == connection_id:
                    # Database node exists, check if table already added
                    for j in range(db_node.childCount()):
                        table_node = db_node.child(j)
                        existing_table = table_node.data(0, Qt.ItemDataRole.UserRole)
                        if existing_table == table_name:
                            logger.info(f"Table {table_display} already added to list")
                            return
                    
                    # Add table to existing database node
                    table_item = QTreeWidgetItem([table_display])
                    table_item.setData(0, Qt.ItemDataRole.UserRole, table_name)
                    table_item.setData(0, Qt.ItemDataRole.UserRole + 1, schema_name)
                    table_item.setData(0, Qt.ItemDataRole.UserRole + 2, connection_id)
                    table_item.setData(0, Qt.ItemDataRole.UserRole + 3, "table")  # Mark as table node
                    db_node.addChild(table_item)
                    db_node.setExpanded(True)
                    
                    logger.info(f"Added table {table_display} to existing database {connection_name}")
                    self._update_tables_count()
                    return
            
            # Database node doesn't exist, create it
            db_item = QTreeWidgetItem([connection_name])
            db_item.setData(0, Qt.ItemDataRole.UserRole, connection_id)
            db_item.setData(0, Qt.ItemDataRole.UserRole + 1, "database")  # Mark as database node
            db_item.setData(0, Qt.ItemDataRole.UserRole + 2, connection)  # Store full connection dict
            self.tables_tree.addTopLevelItem(db_item)
            
            # Add table as child
            table_item = QTreeWidgetItem([table_display])
            table_item.setData(0, Qt.ItemDataRole.UserRole, table_name)
            table_item.setData(0, Qt.ItemDataRole.UserRole + 1, schema_name)
            table_item.setData(0, Qt.ItemDataRole.UserRole + 2, connection_id)
            table_item.setData(0, Qt.ItemDataRole.UserRole + 3, "table")  # Mark as table node
            db_item.addChild(table_item)
            db_item.setExpanded(True)
            
            logger.info(f"Added table {table_display} under new database {connection_name}")
            self._update_tables_count()
            
        except Exception as e:
            logger.error(f"Failed to add table to list: {e}")

    def _update_tables_count(self):
        """Update the tables header with count"""
        total_tables = 0
        root = self.tables_tree.invisibleRootItem()
        for i in range(root.childCount()):
            db_node = root.child(i)
            total_tables += db_node.childCount()
        
        self.tables_header.setText(f"TABLES ({total_tables} selected)")

    def _show_table_context_menu(self, position):
        """Show context menu for tables with Remove option"""
        item = self.tables_tree.itemAt(position)
        if not item:
            return
        
        # Check if it's a table or database node
        # For database nodes: UserRole+1 = "database"
        # For table nodes: UserRole+3 = "table"
        db_type = item.data(0, Qt.ItemDataRole.UserRole + 1)
        table_type = item.data(0, Qt.ItemDataRole.UserRole + 3)
        
        # Only show context menu for database nodes (to remove all) or table nodes
        menu = QMenu(self)
        
        if table_type == "table":
            # Table node - offer to remove this table
            remove_action = menu.addAction("🗑️ Remove Table")
            action = menu.exec(self.tables_tree.mapToGlobal(position))
            
            if action == remove_action:
                self._remove_table_from_list(item)
        
        elif db_type == "database":
            # Database node - offer to remove all tables from this database
            remove_all_action = menu.addAction("🗑️ Remove All Tables from this Database")
            action = menu.exec(self.tables_tree.mapToGlobal(position))
            
            if action == remove_all_action:
                self._remove_database_from_list(item)

    def _remove_table_from_list(self, table_item: QTreeWidgetItem):
        """Remove a single table from the list"""
        parent = table_item.parent()
        if parent:
            parent.removeChild(table_item)
            
            # If database node has no more children, remove it too
            if parent.childCount() == 0:
                root = self.tables_tree.invisibleRootItem()
                root.removeChild(parent)
            
            self._update_tables_count()
            logger.info(f"Removed table {table_item.text(0)} from list")

    def _remove_database_from_list(self, db_item: QTreeWidgetItem):
        """Remove all tables from a database (remove the entire database node)"""
        root = self.tables_tree.invisibleRootItem()
        root.removeChild(db_item)
        self._update_tables_count()
        logger.info(f"Removed database {db_item.text(0)} and all its tables from list")


    def _on_table_clicked(self, item: QTreeWidgetItem, column: int):
        """Load fields for the selected table into the FIELDS panel"""
        # Get item type - it's stored differently for database vs table nodes
        # For table nodes: UserRole = table_name, UserRole+1 = schema_name, UserRole+2 = connection_id, UserRole+3 = "table"
        item_type = item.data(0, Qt.ItemDataRole.UserRole + 3)
        
        # Only process table nodes, not database nodes
        if item_type != "table":
            return
        
        table_name = item.data(0, Qt.ItemDataRole.UserRole)
        schema_name = item.data(0, Qt.ItemDataRole.UserRole + 1)
        connection_id = item.data(0, Qt.ItemDataRole.UserRole + 2)
        
        try:
            self.fields_tree.clear()
            cols = self.schema_discovery.get_columns(connection_id, table_name, schema_name)
            for c in cols:
                label = f"{c['column_name']} ({c.get('data_type','')})"
                field_item = QTreeWidgetItem([label])
                # Store field metadata
                field_item.setData(0, Qt.ItemDataRole.UserRole, "field")
                field_item.setData(0, Qt.ItemDataRole.UserRole + 1, c['column_name'])
                field_item.setData(0, Qt.ItemDataRole.UserRole + 2, c.get('data_type', 'VARCHAR'))
                field_item.setData(0, Qt.ItemDataRole.UserRole + 3, table_name)
                field_item.setData(0, Qt.ItemDataRole.UserRole + 4, schema_name)
                self.fields_tree.addTopLevelItem(field_item)
            
            logger.info(f"Loaded {len(cols)} fields for table {table_name}")
        except Exception as e:
            logger.error(f"Failed to load columns for {table_name}: {e}")

    def _on_field_double_clicked(self, item: QTreeWidgetItem, column: int):
        """Handle double-click on field to add to active tab"""
        item_type = item.data(0, Qt.ItemDataRole.UserRole)

        if item_type != "field":
            return

        # Get field data
        col_name = item.data(0, Qt.ItemDataRole.UserRole + 1)
        col_type = item.data(0, Qt.ItemDataRole.UserRole + 2)
        table_name = item.data(0, Qt.ItemDataRole.UserRole + 3)
        schema_name = item.data(0, Qt.ItemDataRole.UserRole + 4)
        
        # We also need connection info - get from the currently selected table in tables_tree
        current_table_item = self.tables_tree.currentItem()
        if not current_table_item:
            logger.warning("No table selected in tables tree")
            return
        
        # Get connection info from table item
        connection_id = current_table_item.data(0, Qt.ItemDataRole.UserRole + 2)
        
        # Look up connection from repository
        connection = self.conn_repo.get_connection(connection_id)
        if not connection:
            logger.error(f"Could not find connection for id {connection_id}")
            return
        
        # Auto-create or find datasource for this connection+table combination
        datasource_alias = self._ensure_datasource_exists(connection, table_name, schema_name)
        
        field_data = {
            'field_name': col_name,
            'data_type': col_type,
            'table_name': table_name,
            'schema_name': schema_name,
            'datasource_alias': datasource_alias,
            'connection': connection
        }
        
        # Get the active tab (0=Display, 1=Criteria, 2=Datasources)
        active_tab_index = self.xdb_tabs.currentIndex()
        
        if active_tab_index == 0:  # Display tab
            self.add_display_field(field_data)
        elif active_tab_index == 1:  # Criteria tab
            self.add_criteria_filter(field_data)
        # Datasources tab doesn't support adding fields this way

    def add_display_field(self, field_data: dict):
        """Add a field to display tab"""
        # Create display field widget
        display_widget = XDBDisplayFieldWidget(field_data, self)
        display_widget.remove_requested.connect(lambda: self.remove_display_field(display_widget))

        # Add to the end (bottom) of the layout
        self.display_layout.addWidget(display_widget)
        self.display_fields.append(field_data)
        
        # Update datasources tab (automatically adds datasource if needed)
        self._update_datasources_from_fields()

        logger.info(f"Added display field: {field_data['field_name']}")

    def remove_display_field(self, widget):
        """Remove a field from display tab"""
        # Find and remove from tracking
        for field_data in self.display_fields:
            if (field_data['field_name'] == widget.field_data['field_name'] and
                field_data['table_name'] == widget.field_data['table_name']):
                self.display_fields.remove(field_data)
                break

        # Remove widget
        self.display_layout.removeWidget(widget)
        widget.deleteLater()
        
        # Update datasources tab (removes datasources no longer in use)
        self._update_datasources_from_fields()

    def add_criteria_filter(self, field_data: dict):
        """Add a filter widget to criteria tab"""
        # Create filter widget
        filter_widget = XDBCriteriaFilterWidget(field_data, self)
        filter_widget.remove_requested.connect(lambda: self.remove_criteria_filter(filter_widget))

        # Add to the end (bottom) of the layout
        self.criteria_layout.addWidget(filter_widget)
        self.criteria_widgets.append(filter_widget)
        
        # Update datasources tab (automatically adds datasource if needed)
        self._update_datasources_from_fields()

        logger.info(f"Added criteria filter for {field_data['field_name']}")

    def remove_criteria_filter(self, widget):
        """Remove a filter widget from criteria tab"""
        self.criteria_widgets.remove(widget)
        self.criteria_layout.removeWidget(widget)
        widget.deleteLater()
        
        # Update datasources tab (removes datasources no longer in use)
        self._update_datasources_from_fields()
    
    def _update_datasources_from_fields(self):
        """
        Update datasources list based on fields currently in Display and Criteria tabs.
        This mimics the behavior of DB Query's update_tables_involved method.
        """
        # Collect all unique datasources from display fields and criteria widgets
        datasources_in_use = {}
        
        # From display fields
        for field_data in self.display_fields:
            if 'datasource_alias' in field_data:
                alias = field_data['datasource_alias']
                if alias not in datasources_in_use:
                    datasources_in_use[alias] = {
                        'alias': alias,
                        'connection': field_data['connection'],
                        'table_name': field_data['table_name'],
                        'schema_name': field_data.get('schema_name')
                    }
        
        # From criteria widgets
        for widget in self.criteria_widgets:
            field_data = widget.field_data
            if 'datasource_alias' in field_data:
                alias = field_data['datasource_alias']
                if alias not in datasources_in_use:
                    datasources_in_use[alias] = {
                        'alias': alias,
                        'connection': field_data['connection'],
                        'table_name': field_data['table_name'],
                        'schema_name': field_data.get('schema_name')
                    }
        
        # Update self.datasources to match what's in use
        self.datasources = list(datasources_in_use.values())
        
        # Update UI
        self._update_datasources_label()

    def _ensure_datasource_exists(self, connection: dict, table_name: str, schema_name: str) -> str:
        """
        Ensure a datasource exists for the given connection+table combination.
        Returns the datasource alias (creates a new one if needed).
        """
        # Check if datasource already exists for this connection+table
        for ds in self.datasources:
            if (ds['connection']['connection_id'] == connection['connection_id'] and
                ds['table_name'] == table_name and
                ds.get('schema_name') == schema_name):
                return ds['alias']
        
        # Datasource doesn't exist - create a new one with auto-generated alias
        # Use connection name as base for alias (e.g., "DeArb_Data", "TALCESS_Test")
        base_alias = connection['connection_name'].replace(' ', '_').replace('-', '_')
        
        # If alias already exists, append a number
        alias = base_alias
        counter = 1
        while any(ds['alias'] == alias for ds in self.datasources):
            alias = f"{base_alias}_{counter}"
            counter += 1
        
        # Create new datasource
        ds = {
            'alias': alias,
            'connection': connection,
            'table_name': table_name,
            'schema_name': schema_name
        }
        self.datasources.append(ds)
        
        # Update label and FROM combo
        self._update_datasources_label()
        
        logger.info(f"Auto-created datasource: {alias} -> {connection['connection_name']}.{table_name}")
        return alias


    def _add_datasource(self):
        """Add a new datasource (connection + table) to the query"""
        from PyQt6.QtWidgets import QDialog, QVBoxLayout, QFormLayout, QDialogButtonBox
        
        dialog = QDialog(self)
        dialog.setWindowTitle("Add Datasource")
        dialog.setModal(True)
        dialog.setMinimumWidth(400)
        
        layout = QVBoxLayout(dialog)
        form = QFormLayout()
        
        # Alias input
        alias_input = QLineEdit()
        alias_input.setPlaceholderText("e.g., DS1, DS2, etc.")
        form.addRow("Alias:", alias_input)
        
        # Connection dropdown
        conn_combo = QComboBox()
        all_conns = self.conn_repo.get_all_connections()
        conn_combo.addItem("-- Select Connection --", None)
        for conn in all_conns:
            display = f"{conn['connection_name']} ({conn['connection_type']})"
            conn_combo.addItem(display, conn)
        form.addRow("Connection:", conn_combo)
        
        # Table dropdown (populated when connection changes)
        table_combo = QComboBox()
        table_combo.addItem("-- Select Table --", None)
        
        def on_conn_changed():
            table_combo.clear()
            conn = conn_combo.currentData()
            if conn:
                try:
                    saved_tables = self.saved_table_repo.get_saved_tables(conn['connection_id'])
                    table_combo.addItem("-- Select Table --", None)
                    for t in saved_tables:
                        display = f"{t['schema_name']}.{t['table_name']}" if t['schema_name'] else t['table_name']
                        table_combo.addItem(display, t)
                except Exception as e:
                    logger.error(f"Failed to load tables: {e}")
        
        conn_combo.currentIndexChanged.connect(on_conn_changed)
        form.addRow("Table:", table_combo)
        
        layout.addLayout(form)
        
        # Buttons
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        layout.addWidget(buttons)
        
        if dialog.exec() == QDialog.DialogCode.Accepted:
            alias = alias_input.text().strip()
            conn = conn_combo.currentData()
            table = table_combo.currentData()
            
            if not alias:
                QMessageBox.warning(self, "Missing Alias", "Please enter an alias for this datasource.")
                return
            
            if not conn or not table:
                QMessageBox.warning(self, "Incomplete Selection", "Please select both connection and table.")
                return
            
            # Add to datasources list
            ds = {
                'alias': alias,
                'connection': conn,
                'table_name': table['table_name'],
                'schema_name': table.get('schema_name')
            }
            self.datasources.append(ds)
            
            # Update label and FROM combo
            self._update_datasources_label()
            
            logger.info(f"Added datasource: {alias} -> {conn['connection_name']}.{table['table_name']}")
    
    def _add_join(self):
        """Add a join configuration between two datasources"""
        if len(self.datasources) < 2:
            QMessageBox.warning(self, "Not Enough Datasources", "You need at least 2 datasources to create a join.")
            return
        
        from PyQt6.QtWidgets import QDialog, QFormLayout, QDialogButtonBox
        
        dialog = QDialog(self)
        dialog.setWindowTitle("Add Join")
        dialog.setModal(True)
        dialog.setMinimumWidth(450)
        
        layout = QVBoxLayout(dialog)
        form = QFormLayout()
        
        # Join type
        join_type_combo = QComboBox()
        join_type_combo.addItems(["INNER", "LEFT", "RIGHT", "FULL"])
        form.addRow("Join Type:", join_type_combo)
        
        # Left datasource
        left_ds_combo = QComboBox()
        for ds in self.datasources:
            left_ds_combo.addItem(ds['alias'], ds)
        form.addRow("Left Datasource:", left_ds_combo)
        
        # Left column
        left_col_combo = QComboBox()
        
        # Right datasource
        right_ds_combo = QComboBox()
        for ds in self.datasources:
            right_ds_combo.addItem(ds['alias'], ds)
        form.addRow("Right Datasource:", right_ds_combo)
        
        # Right column
        right_col_combo = QComboBox()
        
        form.addRow("Left Column:", left_col_combo)
        form.addRow("Right Column:", right_col_combo)
        
        def update_left_columns():
            left_col_combo.clear()
            ds = left_ds_combo.currentData()
            if ds:
                try:
                    cols = self.schema_discovery.get_columns(
                        ds['connection']['connection_id'],
                        ds['table_name'],
                        ds.get('schema_name')
                    )
                    for c in cols:
                        left_col_combo.addItem(c['column_name'], c['column_name'])
                except Exception as e:
                    logger.error(f"Failed to load columns: {e}")
        
        def update_right_columns():
            right_col_combo.clear()
            ds = right_ds_combo.currentData()
            if ds:
                try:
                    cols = self.schema_discovery.get_columns(
                        ds['connection']['connection_id'],
                        ds['table_name'],
                        ds.get('schema_name')
                    )
                    for c in cols:
                        right_col_combo.addItem(c['column_name'], c['column_name'])
                except Exception as e:
                    logger.error(f"Failed to load columns: {e}")
        
        left_ds_combo.currentIndexChanged.connect(update_left_columns)
        right_ds_combo.currentIndexChanged.connect(update_right_columns)
        
        # Initial population
        if len(self.datasources) > 0:
            update_left_columns()
        if len(self.datasources) > 1:
            right_ds_combo.setCurrentIndex(1)
            update_right_columns()
        
        layout.addLayout(form)
        
        # Buttons
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        layout.addWidget(buttons)
        
        if dialog.exec() == QDialog.DialogCode.Accepted:
            join_type = join_type_combo.currentText()
            left_ds = left_ds_combo.currentData()
            right_ds = right_ds_combo.currentData()
            left_col = left_col_combo.currentData()
            right_col = right_col_combo.currentData()
            
            if not all([left_ds, right_ds, left_col, right_col]):
                QMessageBox.warning(self, "Incomplete Join", "Please fill all join fields.")
                return
            
            # Create join widget
            self._create_join_widget(join_type, left_ds['alias'], left_col, right_ds['alias'], right_col)
    
    def _create_join_widget(self, join_type: str, left_alias: str, left_col: str, right_alias: str, right_col: str):
        """Create a visual widget for a join"""
        join_frame = QFrame()
        join_frame.setFrameShape(QFrame.Shape.Box)
        join_frame.setStyleSheet("QFrame { background: white; border: 1px solid #ddd; border-radius: 4px; padding: 10px; }")
        
        join_layout = QVBoxLayout(join_frame)
        
        # Join description
        join_text = QLabel(f"<b>{join_type} JOIN</b>: {left_alias}.{left_col} = {right_alias}.{right_col}")
        join_layout.addWidget(join_text)
        
        # Remove button
        remove_btn = QPushButton("✕ Remove")
        remove_btn.setMaximumWidth(80)
        remove_btn.clicked.connect(lambda: self._remove_join_widget(join_frame))
        join_layout.addWidget(remove_btn)
        
        self.joins_layout.addWidget(join_frame)
        logger.info(f"Added join: {join_type} {left_alias}.{left_col} = {right_alias}.{right_col}")
    
    def _remove_join_widget(self, widget: QWidget):
        """Remove a join widget"""
        self.joins_layout.removeWidget(widget)
        widget.deleteLater()
    
    def _update_datasources_label(self):
        """Update the datasources involved label with Datasource.TableName format"""
        if not self.datasources:
            self.datasources_involved_label.setText("(None)")
            self.from_datasource_combo.clear()
        else:
            # Build list in "Datasource.TableName" format
            table_names = []
            for ds in self.datasources:
                alias = ds['alias']
                table = ds['table_name']
                table_names.append(f"{alias}.{table}")
            
            table_list = ", ".join(table_names)
            self.datasources_involved_label.setText(table_list)
            
            # Update FROM combo with same format
            self.from_datasource_combo.clear()
            for ds in self.datasources:
                display_name = f"{ds['alias']}.{ds['table_name']}"
                self.from_datasource_combo.addItem(display_name)
    
    def _preview_query(self):
        """Execute cross-query with LIMIT 1000 for preview"""
        self._execute_xdb_query(limit=1000)
    
    def _run_query(self):
        """Execute full cross-query"""
        self._execute_xdb_query(limit=None)
    
    def _execute_xdb_query(self, limit: Optional[int]):
        """Build and execute the XDB query"""
        try:
            # Validate we have at least 2 datasources
            if len(self.datasources) < 2:
                QMessageBox.warning(self, "Not Enough Datasources", "Please add at least 2 datasources in the Datasources tab.")
                return
            
            # For now, use first two datasources (will enhance for N-way joins later)
            source_a_ds = self.datasources[0]
            source_b_ds = self.datasources[1]
            
            # Build source configs
            source_a = {
                'connection': source_a_ds['connection'],
                'table_name': source_a_ds['table_name'],
                'schema_name': source_a_ds.get('schema_name'),
                'columns': ['*'],  # TODO: Get from Display tab
                'filters': []  # TODO: Get from Criteria tab
            }
            
            source_b = {
                'connection': source_b_ds['connection'],
                'table_name': source_b_ds['table_name'],
                'schema_name': source_b_ds.get('schema_name'),
                'columns': ['*'],  # TODO: Get from Display tab
                'filters': []  # TODO: Get from Criteria tab
            }
            
            # Build join config - extract from first join widget
            # TODO: Parse join widgets properly
            join_config = {
                'type': 'INNER',  # Default for now
                'keys_a': ['PolicyNumber'],  # TODO: Extract from joins
                'keys_b': ['PolicyNumber']  # TODO: Extract from joins
            }
            
            # Execute
            logger.info(f"Executing XDB query with limit={limit}")
            result_df = self.xdb_executor.execute_cross_query(source_a, source_b, join_config, limit)
            
            # Show results
            self._show_results(result_df, limit)
            
        except Exception as e:
            logger.error(f"XDB query failed: {e}", exc_info=True)
            QMessageBox.critical(self, "Query Error", f"Failed to execute cross-database query:\n\n{str(e)}")
    
    def _show_results(self, df, limit: Optional[int]):
        """Display query results in a dialog"""
        # Convert DataFrame to dict format expected by QueryResultsDialog
        result = {
            'columns': df.columns.tolist(),
            'rows': df.values.tolist(),
            'row_count': len(df)
        }
        
        title = f"XDB Query Results ({len(df)} rows)"
        if limit:
            title += f" - Preview Limited to {limit}"
        
        dialog = QueryResultsDialog(result, query_text="Cross-Database Query", parent=self)
        dialog.setWindowTitle(title)
        dialog.exec()
    
    def _export_results(self):
        """Export last query results to file"""
        QMessageBox.information(self, "Export", "Export feature: Execute a query first, then use this to save results to Parquet/CSV.")
    
    def _save_query(self):
        """Save current XDB query configuration"""
        QMessageBox.information(
            self, 
            "Save Query", 
            "Save XDB query functionality coming soon.\n\nThis will save your table selections, field configurations, joins, and filters."
        )
    
    def _new_query(self):
        """Clear the query builder and start a new query"""
        # Clear display fields
        for widget in self.display_fields[:]:
            widget.deleteLater()
        self.display_fields.clear()
        
        # Clear criteria widgets
        for widget in self.criteria_widgets[:]:
            widget.deleteLater()
        self.criteria_widgets.clear()
        
        # Clear selected tables
        self.tables_tree.clear()
        self.selected_tables.clear()
        self._update_tables_header()
        
        # Reset query name
        self.query_name_label.setText("unnamed")
        
        logger.info("Query builder cleared - ready for new query")


# ====================== Widget Classes ======================

class XDBDisplayFieldWidget(QFrame):
    """Widget for a single display field in XDB queries"""

    remove_requested = pyqtSignal()

    def __init__(self, field_data: dict, parent=None):
        super().__init__(parent)
        self.field_data = field_data
        self.init_ui()

    def init_ui(self):
        """Initialize UI"""
        self.setFrameStyle(QFrame.Shape.Box)
        self.setStyleSheet("""
            XDBDisplayFieldWidget {
                border: 1px solid #ddd;
                border-radius: 4px;
                background: white;
                padding: 5px;
            }
        """)
        
        # Prevent widget from expanding
        self.setSizePolicy(QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Fixed)
        self.setMaximumHeight(40)

        layout = QHBoxLayout(self)
        layout.setSpacing(5)
        layout.setContentsMargins(5, 5, 5, 5)

        # Field name label container (two lines: field name on top, table name below)
        label_container = QWidget()
        label_layout = QVBoxLayout(label_container)
        label_layout.setSpacing(0)
        label_layout.setContentsMargins(0, 0, 0, 0)
        
        # Field name (bold, on top)
        field_label = QLabel(self.field_data['field_name'])
        field_label.setStyleSheet("font-weight: bold; font-size: 11px;")
        label_layout.addWidget(field_label)
        
        # Table name in "Datasource.TableName" format (smaller, gray, below)
        datasource_alias = self.field_data.get('datasource_alias', '')
        table_name = self.field_data['table_name']
        if datasource_alias:
            display_table = f"{datasource_alias}.{table_name}"
        else:
            display_table = table_name
        
        table_label = QLabel(display_table)
        table_label.setStyleSheet("color: #7f8c8d; font-size: 9px;")
        label_layout.addWidget(table_label)
        
        label_container.setMinimumWidth(150)
        label_container.setMaximumWidth(250)
        layout.addWidget(label_container)

        # Type label (compact)
        type_label = QLabel(f"({self.field_data['data_type']})")
        type_label.setStyleSheet("color: #7f8c8d; font-size: 9px;")
        type_label.setMaximumWidth(80)
        layout.addWidget(type_label)

        # Add stretch to push remove button to the right
        layout.addStretch()

        # Remove button with white X, right-justified
        remove_btn = QPushButton("X")
        remove_btn.setFixedSize(25, 25)
        remove_btn.setStyleSheet("""
            QPushButton {
                background: #e74c3c;
                color: white;
                border: none;
                border-radius: 3px;
                font-size: 12px;
                font-weight: bold;
            }
            QPushButton:hover {
                background: #c0392b;
            }
        """)
        remove_btn.clicked.connect(self.remove_requested.emit)
        layout.addWidget(remove_btn, alignment=Qt.AlignmentFlag.AlignVCenter)


class XDBCriteriaFilterWidget(QFrame):
    """Widget for a single filter criterion in XDB queries"""

    remove_requested = pyqtSignal()

    def __init__(self, field_data: dict, parent=None):
        super().__init__(parent)
        self.field_data = field_data
        self.parent_screen = parent
        self.init_ui()

    def init_ui(self):
        """Initialize UI"""
        self.setFrameStyle(QFrame.Shape.Box)
        self.setStyleSheet("""
            XDBCriteriaFilterWidget {
                border: 1px solid #ddd;
                border-radius: 4px;
                background: white;
                padding: 5px;
            }
        """)
        
        # Prevent widget from expanding horizontally
        self.setSizePolicy(QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Fixed)
        self.setMaximumHeight(95)

        main_layout = QHBoxLayout(self)
        main_layout.setSpacing(5)
        main_layout.setContentsMargins(5, 5, 5, 5)

        # Field name label container (two lines: field name on top, table name below)
        label_container = QWidget()
        label_layout = QVBoxLayout(label_container)
        label_layout.setSpacing(0)
        label_layout.setContentsMargins(0, 0, 0, 0)
        
        # Field name (bold, on top)
        self.field_label = QLabel(self.field_data['field_name'])
        self.field_label.setStyleSheet("font-weight: bold; font-size: 11px;")
        label_layout.addWidget(self.field_label)
        
        # Table name in "Datasource.TableName" format (smaller, gray, below)
        datasource_alias = self.field_data.get('datasource_alias', '')
        table_name = self.field_data['table_name']
        if datasource_alias:
            display_table = f"{datasource_alias}.{table_name}"
        else:
            display_table = table_name
        
        table_label = QLabel(display_table)
        table_label.setStyleSheet("color: #7f8c8d; font-size: 9px;")
        label_layout.addWidget(table_label)
        
        label_container.setMinimumWidth(150)
        label_container.setMaximumWidth(200)
        main_layout.addWidget(label_container)

        # Type label (smaller)
        type_label = QLabel(f"({self.field_data['data_type']})")
        type_label.setStyleSheet("color: #7f8c8d; font-size: 9px;")
        type_label.setMaximumWidth(80)
        main_layout.addWidget(type_label)

        # Filter controls container
        self.controls_container = QWidget()
        self.controls_layout = QHBoxLayout(self.controls_container)
        self.controls_layout.setContentsMargins(0, 0, 0, 0)
        self.controls_layout.setSpacing(5)
        main_layout.addWidget(self.controls_container)

        # Add basic filter controls (operator and value)
        self.operator_combo = QComboBox()
        self.operator_combo.addItems(["=", "!=", ">", "<", ">=", "<=", "LIKE", "IN"])
        self.operator_combo.setMaximumWidth(80)
        self.controls_layout.addWidget(self.operator_combo)

        self.value_input = QLineEdit()
        self.value_input.setPlaceholderText("Value...")
        self.value_input.setMaximumWidth(150)
        self.controls_layout.addWidget(self.value_input)

        # Add stretch to push remove button to the right
        main_layout.addStretch()

        # Remove button with white X, right-justified
        remove_btn = QPushButton("X")
        remove_btn.setFixedSize(25, 25)
        remove_btn.setStyleSheet("""
            QPushButton {
                background: #e74c3c;
                color: white;
                border: none;
                border-radius: 3px;
                font-size: 12px;
                font-weight: bold;
                padding: 0px;
            }
            QPushButton:hover {
                background: #c0392b;
            }
        """)
        remove_btn.clicked.connect(self.remove_requested.emit)
        main_layout.addWidget(remove_btn, alignment=Qt.AlignmentFlag.AlignVCenter)

    def get_filter_condition(self) -> dict:
        """Get the filter condition as a dict"""
        return {
            'field_name': self.field_data['field_name'],
            'table_name': self.field_data['table_name'],
            'operator': self.operator_combo.currentText(),
            'value': self.value_input.text()
        }
