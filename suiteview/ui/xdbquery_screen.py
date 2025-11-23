"""XDB Query Screen - Cross-database query builder"""

import logging
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QSplitter,
    QTreeWidget, QTreeWidgetItem, QPushButton, QFrame, QMenu,
    QScrollArea, QComboBox, QMessageBox, QFileDialog, QTabWidget,
    QLineEdit, QCheckBox, QDateEdit, QToolButton, QSizePolicy, QInputDialog
)
from PyQt6.QtCore import Qt, QDate, pyqtSignal
from PyQt6.QtGui import QAction, QDrag
from typing import Optional

from suiteview.data.repositories import (ConnectionRepository, get_query_repository, 
                                         get_saved_table_repository, SavedTableRepository)
from suiteview.core.schema_discovery import SchemaDiscovery
from suiteview.core.query_executor_xdb import XDBQueryExecutor
from suiteview.ui.dialogs.query_results_dialog import QueryResultsDialog
from suiteview.ui.widgets import CascadingMenuWidget
from suiteview.ui import theme

logger = logging.getLogger(__name__)


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
        theme.apply_panel_header(self.tables_header)
        panel_layout.addWidget(self.tables_header)

        # Search box
        # Keeping structure similar to DB Query; hook up later if needed
        # Using a simple placeholder to keep compact look
        self.tables_search = QLabel("")
        self.tables_search.setVisible(False)
        panel_layout.addWidget(self.tables_search)

        self.tables_tree = QTreeWidget()
        self.tables_tree.setHeaderHidden(True)
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
        theme.apply_panel_header(header)
        panel_layout.addWidget(header)

        self.fields_tree = QTreeWidget()
        self.fields_tree.setHeaderHidden(True)
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
        self.new_query_btn = QPushButton("New Query")
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
                border: 1px solid #B0C8E8;
                background-color: #E8F0FF;
            }
            QTabBar {
                background-color: #E8F0FF;
            }
            QTabBar::tab {
                padding: 10px 20px;
                margin-right: 2px;
                margin-left: 0px;
                background-color: #D8E8FF;
                color: #0A1E5E;
                font-weight: 600;
            }
            QTabBar::tab:selected {
                background-color: #6BA3E8;
                border-bottom: 3px solid #FFD700;
                color: #0A1E5E;
            }
            QTabBar::tab:!selected {
                background-color: #D8E8FF;
                color: #5a6c7d;
            }
            QTabBar::tab:hover {
                background-color: #C8DFFF;
            }
            QTabBar::tab:last {
                margin-left: 0px;
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
        theme.apply_panel_header(databases_header)
        panel_layout.addWidget(databases_header)

        # Cascading list of database types with menus
        self.data_sources_list = CascadingMenuWidget(self)
        panel_layout.addWidget(self.data_sources_list, stretch=1)

        # XDB Queries section
        queries_header = QLabel("XDB QUERIES")
        theme.apply_panel_header(queries_header)
        panel_layout.addWidget(queries_header)

        self.xdb_queries_tree = QTreeWidget()
        self.xdb_queries_tree.setHeaderHidden(True)
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
        self.xdb_queries_tree.clear()  # Clear existing items first
        queries = self.query_repo.get_all_queries(query_type='XDB')
        for q in queries:
            item = QTreeWidgetItem([q['query_name']])
            item.setData(0, Qt.ItemDataRole.UserRole, q['query_id'])
            item.setData(0, Qt.ItemDataRole.UserRole + 1, q.get('query_definition', ''))
            self.xdb_queries_tree.addTopLevelItem(item)
        logger.info(f"Loaded {len(queries)} XDB queries into tree")

    # --------------------- Event handlers ---------------------
    def _on_xdb_query_clicked(self, item: QTreeWidgetItem, column: int):
        """Load selected XDB query"""
        query_id = item.data(0, Qt.ItemDataRole.UserRole)
        query_definition = item.data(0, Qt.ItemDataRole.UserRole + 1)
        
        if query_id and query_definition:
            self._load_saved_query(query_id, query_definition)
    
    def _load_saved_query(self, query_id: int, query_definition: str):
        """Load a saved XDB query into the query builder"""
        try:
            import json
            
            # Get the full query record to get the name
            query_record = self.query_repo.get_query(query_id)
            if not query_record:
                raise Exception("Query not found")
            
            # Parse the query definition (handle both string and dict)
            if isinstance(query_definition, str):
                query_dict = json.loads(query_definition)
            elif isinstance(query_definition, dict):
                query_dict = query_definition
            else:
                raise Exception(f"Invalid query_definition type: {type(query_definition)}")
            
            # Clear current query
            self._clear_query()
            
            # Set query name
            self.query_name_label.setText(query_record['query_name'])
            self.query_name_label.setStyleSheet("""
                QLabel {
                    color: #2c3e50;
                    font-size: 16px;
                    font-weight: bold;
                    padding: 5px 20px;
                }
            """)
            
            # Load datasources
            for ds_data in query_dict.get('datasources', []):
                # Get the connection from repository
                connection = self.conn_repo.get_connection(ds_data['connection_id'])
                if connection:
                    ds = {
                        'alias': ds_data['alias'],
                        'connection': connection,
                        'table_name': ds_data['table_name'],
                        'schema_name': ds_data.get('schema_name')
                    }
                    self.datasources.append(ds)
            
            # Update datasources label and FROM combo
            self._update_datasources_label()
            
            # Set FROM datasource
            from_datasource = query_dict.get('from_datasource')
            if from_datasource:
                index = self.from_datasource_combo.findText(from_datasource)
                if index >= 0:
                    self.from_datasource_combo.setCurrentIndex(index)
            
            # Load display fields
            for field_data in query_dict.get('display_fields', []):
                # Add to tracking
                self.display_fields.append(field_data)
                
                # Create widget
                display_widget = XDBDisplayFieldWidget(field_data, self)
                display_widget.remove_requested.connect(lambda w=display_widget: self.remove_display_field(w))
                self.display_layout.addWidget(display_widget)
            
            # Load criteria filters
            for criterion in query_dict.get('criteria', []):
                # Reconstruct field_data
                field_data = {
                    'field_name': criterion.get('field_name'),
                    'data_type': criterion.get('data_type'),
                    'table_name': criterion.get('table_name'),
                    'schema_name': criterion.get('schema_name'),
                    'datasource_alias': criterion.get('datasource_alias')
                }
                
                # Create filter widget
                filter_widget = XDBCriteriaFilterWidget(field_data, self)
                filter_widget.remove_requested.connect(lambda w=filter_widget: self.remove_criteria_filter(w))
                self.criteria_layout.addWidget(filter_widget)
                self.criteria_widgets.append(filter_widget)
                
                # Restore filter values
                if 'operator' in criterion:
                    operator_index = filter_widget.operator_combo.findText(criterion['operator'])
                    if operator_index >= 0:
                        filter_widget.operator_combo.setCurrentIndex(operator_index)
                
                if 'value' in criterion:
                    filter_widget.value_input.setText(str(criterion['value']))
            
            # Load joins
            for join_config in query_dict.get('joins', []):
                # Create join widget
                join_widget = XDBJoinWidget(self.datasources, self)
                join_widget.remove_requested.connect(lambda w=join_widget: self._remove_join_widget(w))
                self.joins_layout.addWidget(join_widget)
                
                # Restore join configuration
                self._restore_join_config(join_widget, join_config)
            
            logger.info(f"Loaded XDB query: {query_record['query_name']}")
            
        except Exception as e:
            logger.error(f"Error loading XDB query: {e}", exc_info=True)
            QMessageBox.critical(
                self,
                "Load Failed",
                f"Failed to load XDB query:\n{str(e)}"
            )
    
    def _restore_join_config(self, join_widget: 'XDBJoinWidget', join_config: dict):
        """Restore join widget configuration from saved state"""
        try:
            # Set join type
            join_type = join_config.get('join_type', 'INNER JOIN')
            index = join_widget.join_type_combo.findText(join_type)
            if index >= 0:
                join_widget.join_type_combo.setCurrentIndex(index)
            
            # Set right datasource
            right_ds = join_config.get('right_datasource')
            if right_ds:
                for i in range(join_widget.right_datasource_combo.count()):
                    ds = join_widget.right_datasource_combo.itemData(i)
                    if ds and ds['alias'] == right_ds['alias']:
                        join_widget.right_datasource_combo.setCurrentIndex(i)
                        break
            
            # Restore ON conditions
            on_conditions = join_config.get('on_conditions', [])
            
            # First condition already exists, restore it
            if len(on_conditions) > 0 and len(join_widget.on_condition_rows) > 0:
                self._restore_on_condition(join_widget.on_condition_rows[0], on_conditions[0])
            
            # Add additional conditions
            for i in range(1, len(on_conditions)):
                join_widget._add_on_condition_row()
                if i < len(join_widget.on_condition_rows):
                    self._restore_on_condition(join_widget.on_condition_rows[i], on_conditions[i])
            
        except Exception as e:
            logger.error(f"Error restoring join config: {e}", exc_info=True)
    
    def _restore_on_condition(self, row_data: dict, condition: dict):
        """Restore a single ON condition row"""
        try:
            # Set left datasource
            left_ds_alias = condition.get('left_datasource')
            if left_ds_alias:
                for i in range(row_data['left_datasource_combo'].count()):
                    ds = row_data['left_datasource_combo'].itemData(i)
                    if ds and ds['alias'] == left_ds_alias:
                        row_data['left_datasource_combo'].setCurrentIndex(i)
                        break
            
            # Set left field
            left_field = condition.get('left_field')
            if left_field:
                index = row_data['left_field_combo'].findText(left_field)
                if index >= 0:
                    row_data['left_field_combo'].setCurrentIndex(index)
            
            # Set right datasource
            right_ds_alias = condition.get('right_datasource')
            if right_ds_alias:
                for i in range(row_data['right_datasource_combo'].count()):
                    ds = row_data['right_datasource_combo'].itemData(i)
                    if ds and ds['alias'] == right_ds_alias:
                        row_data['right_datasource_combo'].setCurrentIndex(i)
                        break
            
            # Set right field
            right_field = condition.get('right_field')
            if right_field:
                index = row_data['right_field_combo'].findText(right_field)
                if index >= 0:
                    row_data['right_field_combo'].setCurrentIndex(index)
            
        except Exception as e:
            logger.error(f"Error restoring ON condition: {e}", exc_info=True)
    
    def _clear_query(self):
        """Clear the query builder"""
        # Clear display fields
        while self.display_layout.count() > 0:
            item = self.display_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        self.display_fields.clear()
        
        # Clear criteria widgets
        while self.criteria_layout.count() > 0:
            item = self.criteria_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        self.criteria_widgets.clear()
        
        # Clear joins
        while self.joins_layout.count() > 0:
            item = self.joins_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        
        # Clear datasources
        self.datasources.clear()
        self._update_datasources_label()
        
        # Reset query name
        self.query_name_label.setText("unnamed")
        self.query_name_label.setStyleSheet("""
            QLabel {
                color: #95a5a6;
                font-size: 16px;
                font-style: italic;
                padding: 5px 20px;
            }
        """)

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

        if action == rename_action:
            self._rename_query(query_id, query_name)
        elif action == copy_action:
            self._copy_query(query_id, query_name)
        elif action == delete_action:
            self._delete_query(query_id, query_name)
    
    def _rename_query(self, query_id: int, query_name: str):
        """Rename a saved XDB query"""
        try:
            # Prompt for new name
            new_name, ok = QInputDialog.getText(
                self, "Rename Query", 
                f"Enter a new name for '{query_name}':",
                text=query_name
            )
            
            if not ok or not new_name.strip():
                return
            
            new_name = new_name.strip()
            
            # Don't update if name hasn't changed
            if new_name == query_name:
                return
            
            # Update the query name
            self.query_repo.update_query_name(query_id, new_name)
            
            # If this is the currently loaded query, update the label
            if self.query_name_label.text() == query_name:
                self.query_name_label.setText(new_name)
            
            QMessageBox.information(
                self,
                "Query Renamed",
                f"Query renamed successfully to '{new_name}'!"
            )
            
            # Refresh XDB queries list
            self._load_xdb_queries_tree()
            
            logger.info(f"Renamed XDB query {query_id} from '{query_name}' to '{new_name}'")
            
        except Exception as e:
            logger.error(f"Error renaming XDB query: {e}", exc_info=True)
            QMessageBox.critical(
                self,
                "Rename Failed",
                f"Failed to rename query:\n{str(e)}"
            )
    
    def _copy_query(self, query_id: int, query_name: str):
        """Copy a saved XDB query"""
        try:
            # Prompt for new name
            new_name, ok = QInputDialog.getText(
                self, "Copy Query", 
                f"Enter a name for the copy of '{query_name}':",
                text=f"{query_name} (Copy)"
            )
            
            if not ok or not new_name.strip():
                return
            
            new_name = new_name.strip()
            
            # Check if a query with this name already exists
            existing_queries = self.query_repo.get_all_queries(query_type='XDB')
            existing_names = [q['query_name'] for q in existing_queries]
            
            if new_name in existing_names:
                reply = QMessageBox.question(
                    self,
                    "Query Name Exists",
                    f"A query named '{new_name}' already exists.\n\n"
                    f"Do you want to overwrite it?",
                    QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                    QMessageBox.StandardButton.No
                )
                
                if reply == QMessageBox.StandardButton.No:
                    return
                
                # Find and delete the existing query
                existing_query = next((q for q in existing_queries if q['query_name'] == new_name), None)
                if existing_query:
                    self.query_repo.delete_query(existing_query['query_id'])
                    logger.info(f"Deleted existing XDB query '{new_name}' to overwrite")
            
            # Get the original query
            query_record = self.query_repo.get_query(query_id)
            if not query_record:
                raise Exception("Query not found")
            
            # Save as new query with new name
            new_query_id = self.query_repo.save_query(
                query_name=new_name,
                query_type='XDB',
                query_definition=query_record['query_definition'],
                category=query_record.get('category', 'User Queries')
            )
            
            QMessageBox.information(
                self,
                "Query Copied",
                f"Query copied successfully as '{new_name}'!"
            )
            
            # Refresh XDB queries list
            self._load_xdb_queries_tree()
            
            logger.info(f"Copied XDB query '{query_name}' to '{new_name}' (ID: {new_query_id})")
            
        except Exception as e:
            logger.error(f"Error copying XDB query: {e}", exc_info=True)
            QMessageBox.critical(
                self,
                "Copy Failed",
                f"Failed to copy query:\n{str(e)}"
            )
    
    def _delete_query(self, query_id: int, query_name: str):
        """Delete a saved XDB query"""
        try:
            # Confirm deletion
            reply = QMessageBox.question(
                self,
                "Delete Query",
                f"Are you sure you want to delete the XDB query '{query_name}'?\n\n"
                f"This action cannot be undone.",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No
            )
            
            if reply == QMessageBox.StandardButton.No:
                return
            
            # Delete from database
            self.query_repo.delete_query(query_id)
            
            # If this was the currently loaded query, clear it
            if self.query_name_label.text() == query_name:
                self._clear_query()
            
            QMessageBox.information(
                self,
                "Query Deleted",
                f"XDB Query '{query_name}' has been deleted."
            )
            
            # Refresh XDB queries list
            self._load_xdb_queries_tree()
            
            logger.info(f"Deleted XDB query '{query_name}' (ID: {query_id})")
            
        except Exception as e:
            logger.error(f"Error deleting XDB query: {e}", exc_info=True)
            QMessageBox.critical(
                self,
                "Delete Failed",
                f"Failed to delete query:\n{str(e)}"
            )

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
        display_widget.remove_requested.connect(lambda w=display_widget: self.remove_display_field(w))

        # Add to the end (bottom) of the layout
        self.display_layout.addWidget(display_widget)
        self.display_fields.append(field_data)
        
        # Update datasources tab (automatically adds datasource if needed)
        self._update_datasources_from_fields()

        logger.info(f"Added display field: {field_data['field_name']}")

    def remove_display_field(self, widget):
        """Remove a field from display tab"""
        try:
            # Find and remove from tracking by matching the widget's field_data
            field_to_remove = None
            for field_data in self.display_fields:
                # Match on key identifying fields
                if (field_data.get('field_name') == widget.field_data.get('field_name') and
                    field_data.get('table_name') == widget.field_data.get('table_name') and
                    field_data.get('datasource_alias') == widget.field_data.get('datasource_alias')):
                    field_to_remove = field_data
                    break
            
            if field_to_remove:
                self.display_fields.remove(field_to_remove)
                logger.info(f"Removed display field: {field_to_remove.get('field_name')}")

            # Remove widget
            self.display_layout.removeWidget(widget)
            widget.deleteLater()
            
            # Update datasources tab (removes datasources no longer in use)
            self._update_datasources_from_fields()
            
        except Exception as e:
            logger.error(f"Error removing display field: {e}", exc_info=True)

    def add_criteria_filter(self, field_data: dict):
        """Add a filter widget to criteria tab"""
        # Create filter widget
        filter_widget = XDBCriteriaFilterWidget(field_data, self)
        filter_widget.remove_requested.connect(lambda w=filter_widget: self.remove_criteria_filter(w))

        # Add to the end (bottom) of the layout
        self.criteria_layout.addWidget(filter_widget)
        self.criteria_widgets.append(filter_widget)
        
        # Update datasources tab (automatically adds datasource if needed)
        self._update_datasources_from_fields()

        logger.info(f"Added criteria filter for {field_data['field_name']}")

    def remove_criteria_filter(self, widget):
        """Remove a filter widget from criteria tab"""
        try:
            if widget in self.criteria_widgets:
                self.criteria_widgets.remove(widget)
            
            self.criteria_layout.removeWidget(widget)
            widget.deleteLater()
            
            # Update datasources tab (removes datasources no longer in use)
            self._update_datasources_from_fields()
            
            logger.info("Removed criteria filter")
            
        except Exception as e:
            logger.error(f"Error removing criteria filter: {e}", exc_info=True)
    
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
        """Add an inline join configuration widget between datasources"""
        if len(self.datasources) < 2:
            QMessageBox.warning(self, "Not Enough Datasources", "You need at least 2 datasources to create a join.")
            return
        
        # Create inline join widget
        join_widget = XDBJoinWidget(self.datasources, self)
        join_widget.remove_requested.connect(lambda: self._remove_join_widget(join_widget))
        
        # Add to joins layout
        self.joins_layout.addWidget(join_widget)
        
        logger.info("Added inline JOIN widget")
    
    def _remove_join_widget(self, widget: QWidget):
        """Remove a join widget"""
        self.joins_layout.removeWidget(widget)
        widget.deleteLater()
        logger.info("Removed JOIN widget")
    
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
            # Validate we have at least 1 datasource
            if len(self.datasources) < 1:
                QMessageBox.warning(self, "No Datasources", "Please add at least 1 datasource in the Datasources tab.")
                return
            
            # Extract display columns from Display tab
            display_columns = []
            datasource_columns = {}  # Track which columns belong to which datasource
            
            for field_data in self.display_fields:
                datasource_alias = field_data.get('datasource_alias', '')
                field_name = field_data.get('field_name', '')
                
                if datasource_alias and field_name:
                    if datasource_alias not in datasource_columns:
                        datasource_columns[datasource_alias] = []
                    datasource_columns[datasource_alias].append(field_name)
            
            # Extract criteria filters from Criteria tab
            datasource_filters = {}  # Track which filters belong to which datasource
            
            for widget in self.criteria_widgets:
                filter_condition = widget.get_filter_condition()
                if filter_condition:
                    datasource_alias = widget.field_data.get('datasource_alias', '')
                    
                    if datasource_alias:
                        if datasource_alias not in datasource_filters:
                            datasource_filters[datasource_alias] = []
                        
                        # Create filter dict for query executor
                        filter_dict = {
                            'column': filter_condition['field_name'],
                            'operator': filter_condition['operator'],
                            'value': filter_condition['value']
                        }
                        datasource_filters[datasource_alias].append(filter_dict)
            
            logger.info(f"Display columns by datasource: {datasource_columns}")
            logger.info(f"Filters by datasource: {datasource_filters}")
            
            # Handle any number of datasources (1 or more)
            # Build list of all source configs
            source_configs = []
            for ds in self.datasources:
                # Use explicit columns for this datasource if provided; otherwise, pass empty list
                ds_alias = ds['alias']
                ds_columns = datasource_columns.get(ds_alias, [])
                source_config = {
                    'connection': ds['connection'],
                    'table_name': ds['table_name'],
                    'schema_name': ds.get('schema_name'),
                    'alias': ds_alias,
                    'columns': ds_columns,
                    'filters': datasource_filters.get(ds_alias, [])
                }
                source_configs.append(source_config)
            
            # Extract join configs from Joins tab (empty list if no joins)
            join_configs = []
            for i in range(self.joins_layout.count()):
                join_widget = self.joins_layout.itemAt(i).widget()
                if join_widget and hasattr(join_widget, 'get_join_config'):
                    join_config = join_widget.get_join_config()
                    if join_config:
                        join_configs.append(join_config)
            
            logger.info(f"Executing XDB query with {len(source_configs)} datasource(s)")
            logger.info(f"Join configs: {join_configs}")
            
            # Execute using XDB executor (handles N datasources flexibly)
            result_df = self.xdb_executor.execute_query(source_configs, join_configs, limit)
            
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
        try:
            # Validate we have necessary components
            validation_errors = []
            
            if not self.datasources:
                validation_errors.append("No datasources added (add datasources in Datasources tab)")
            
            if not self.display_fields:
                validation_errors.append("No display fields selected (add fields to Display tab)")
            
            if validation_errors:
                QMessageBox.warning(
                    self,
                    "Query Validation Failed",
                    "Please fix the following issues before saving:\n\n" + "\n".join(validation_errors)
                )
                return
            
            # Prompt for query name if not already named
            current_name = self.query_name_label.text()
            if not current_name or current_name == "unnamed":
                query_name, ok = QInputDialog.getText(
                    self, "Save Query", "Enter a name for this XDB query:"
                )
                
                if not ok or not query_name.strip():
                    return
                
                query_name = query_name.strip()
            else:
                query_name = current_name
            
            # Build query definition dictionary
            query_dict = self._build_query_definition()
            
            # Save to database
            query_id = self.query_repo.save_query(
                query_name=query_name,
                query_type='XDB',
                query_definition=query_dict,
                category='User Queries'
            )
            
            # Update display
            self.query_name_label.setText(query_name)
            self.query_name_label.setStyleSheet("""
                QLabel {
                    color: #2c3e50;
                    font-size: 16px;
                    font-weight: bold;
                    padding: 5px 20px;
                }
            """)
            
            QMessageBox.information(
                self,
                "Query Saved",
                f"XDB Query '{query_name}' has been saved successfully!"
            )
            
            # Refresh XDB queries list
            self._load_xdb_queries_tree()
            
            logger.info(f"Saved XDB query: {query_name} (ID: {query_id})")
            
        except Exception as e:
            logger.error(f"Error saving XDB query: {e}", exc_info=True)
            QMessageBox.critical(
                self,
                "Save Failed",
                f"Failed to save XDB query:\n{str(e)}"
            )
    
    def _build_query_definition(self) -> dict:
        """Build query definition dictionary from current UI state"""
        query_dict = {
            'datasources': [],
            'display_fields': [],
            'criteria': [],
            'joins': [],
            'from_datasource': self.from_datasource_combo.currentText()
        }
        
        # Save datasources
        for ds in self.datasources:
            query_dict['datasources'].append({
                'alias': ds['alias'],
                'connection_id': ds['connection']['connection_id'],
                'connection_name': ds['connection']['connection_name'],
                'table_name': ds['table_name'],
                'schema_name': ds.get('schema_name')
            })
        
        # Save display fields
        for field_data in self.display_fields:
            query_dict['display_fields'].append({
                'field_name': field_data['field_name'],
                'data_type': field_data['data_type'],
                'table_name': field_data['table_name'],
                'schema_name': field_data.get('schema_name'),
                'datasource_alias': field_data.get('datasource_alias')
            })
        
        # Save criteria filters
        for widget in self.criteria_widgets:
            filter_condition = widget.get_filter_condition()
            if filter_condition:
                # Include datasource alias
                filter_condition['datasource_alias'] = widget.field_data.get('datasource_alias')
                filter_condition['schema_name'] = widget.field_data.get('schema_name')
                filter_condition['data_type'] = widget.field_data.get('data_type')
                query_dict['criteria'].append(filter_condition)
        
        # Save joins
        for i in range(self.joins_layout.count()):
            widget = self.joins_layout.itemAt(i).widget()
            if widget and hasattr(widget, 'get_join_config'):
                join_config = widget.get_join_config()
                if join_config and join_config.get('on_conditions'):
                    query_dict['joins'].append(join_config)
        
        return query_dict
    
    def _new_query(self):
        """Clear the query builder and start a new query"""
        self._clear_query()
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
        
        # Store default background for toggling
        self.default_bg = "white"
        self.aggregated_bg = "#FFE5CC"  # Light orange
        
        self.setStyleSheet(f"""
            XDBDisplayFieldWidget {{
                border: 1px solid #ddd;
                border-radius: 4px;
                background: {self.default_bg};
                padding: 0px;
            }}
        """)
        
        # Fixed size for tile layout
        self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        self.setFixedWidth(200)
        self.setFixedHeight(95)

        layout = QVBoxLayout(self)
        layout.setSpacing(1)
        layout.setContentsMargins(4, 2, 4, 2)

        # Header row: Field name, data type, and remove button
        header_layout = QHBoxLayout()
        header_layout.setSpacing(3)
        
        # Field name (bold)
        field_label = QLabel(self.field_data['field_name'])
        field_label.setStyleSheet("font-weight: bold; font-size: 11px; background: transparent;")
        field_label.setWordWrap(True)
        header_layout.addWidget(field_label)
        
        # Data type (subtle, in header)
        type_label = QLabel(f"({self.field_data['data_type']})")
        type_label.setStyleSheet("color: #999; font-size: 8px; background: transparent;")
        header_layout.addWidget(type_label)
        
        header_layout.addStretch()
        
        # Subtle remove button with X
        remove_btn = QPushButton("×")
        remove_btn.setFixedSize(14, 14)
        remove_btn.setStyleSheet("""
            QPushButton {
                background: transparent;
                color: #999;
                border: none;
                font-size: 16px;
                font-weight: normal;
                padding: 0px;
            }
            QPushButton:hover {
                color: #e74c3c;
            }
        """)
        remove_btn.clicked.connect(self.remove_requested.emit)
        header_layout.addWidget(remove_btn, alignment=Qt.AlignmentFlag.AlignTop)
        
        layout.addLayout(header_layout)
        
        # Alias input field (editable)
        alias_layout = QHBoxLayout()
        alias_layout.setSpacing(2)
        alias_label = QLabel("Alias:")
        alias_label.setStyleSheet("font-size: 9px; color: #7f8c8d; background: transparent;")
        alias_layout.addWidget(alias_label)
        
        self.alias_input = QLineEdit()
        self.alias_input.setText(self.field_data['field_name'])  # Default to field name
        self.alias_input.setStyleSheet("""
            QLineEdit {
                font-size: 9px;
                padding: 1px 2px;
                background: white;
                border: 1px solid #ddd;
                border-radius: 2px;
            }
        """)
        self.alias_input.setMaximumHeight(16)
        alias_layout.addWidget(self.alias_input)
        
        layout.addLayout(alias_layout)
        
        # Table name in "Datasource.TableName" format
        datasource_alias = self.field_data.get('datasource_alias', '')
        table_name = self.field_data['table_name']
        if datasource_alias:
            display_table = f"📋 {datasource_alias}.{table_name}"
        else:
            display_table = f"📋 {table_name}"
        
        table_label = QLabel(display_table)
        table_label.setStyleSheet("color: #7f8c8d; font-size: 9px; background: transparent;")
        layout.addWidget(table_label)

        # Bottom row: Agg and Order on same line
        controls_layout = QHBoxLayout()
        controls_layout.setSpacing(4)
        
        # Aggregation combobox
        agg_label = QLabel("Agg:")
        agg_label.setStyleSheet("font-size: 9px; color: #7f8c8d; background: transparent;")
        controls_layout.addWidget(agg_label)
        
        self.agg_combo = QComboBox()
        # Populate based on data type
        data_type_lower = self.field_data['data_type'].lower()
        if any(t in data_type_lower for t in ['char', 'varchar', 'text', 'string', 'clob']):
            # String types
            self.agg_combo.addItems(["None", "First", "Last", "Count"])
        else:
            # Numeric types (int, decimal, float, double, etc.)
            self.agg_combo.addItems(["None", "Sum", "Max", "Min", "Avg", "First", "Last", "Count"])
        
        self.agg_combo.setStyleSheet("""
            QComboBox {
                font-size: 9px;
                padding: 1px;
                background: white;
                border: 1px solid #ddd;
                border-radius: 2px;
            }
        """)
        self.agg_combo.setMaximumHeight(16)
        self.agg_combo.setMaximumWidth(60)
        self.agg_combo.currentTextChanged.connect(self.on_agg_changed)
        controls_layout.addWidget(self.agg_combo)
        
        # Order combobox
        order_label = QLabel("Order:")
        order_label.setStyleSheet("font-size: 9px; color: #7f8c8d; background: transparent;")
        controls_layout.addWidget(order_label)
        
        self.order_combo = QComboBox()
        self.order_combo.addItems(["None", "Ascend", "Descend"])
        self.order_combo.setStyleSheet("""
            QComboBox {
                font-size: 9px;
                padding: 1px;
                background: white;
                border: 1px solid #ddd;
                border-radius: 2px;
            }
        """)
        self.order_combo.setMaximumHeight(16)
        self.order_combo.setMaximumWidth(60)
        controls_layout.addWidget(self.order_combo)
        
        layout.addLayout(controls_layout)
    
    def on_agg_changed(self, text):
        """Handle aggregation selection change"""
        if text != "None":
            # Apply light orange background when aggregated
            self.setStyleSheet(f"""
                XDBDisplayFieldWidget {{
                    border: 1px solid #ddd;
                    border-radius: 4px;
                    background: {self.aggregated_bg};
                    padding: 0px;
                }}
            """)
        else:
            # Restore white background
            self.setStyleSheet(f"""
                XDBDisplayFieldWidget {{
                    border: 1px solid #ddd;
                    border-radius: 4px;
                    background: {self.default_bg};
                    padding: 0px;
                }}
            """)


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
        label_container.setStyleSheet("background: transparent;")
        label_layout = QVBoxLayout(label_container)
        label_layout.setSpacing(0)
        label_layout.setContentsMargins(0, 0, 0, 0)
        
        # Field name (bold, on top)
        self.field_label = QLabel(self.field_data['field_name'])
        self.field_label.setStyleSheet("font-weight: bold; font-size: 11px; background: transparent;")
        label_layout.addWidget(self.field_label)
        
        # Table name in "Datasource.TableName" format (smaller, gray, below)
        datasource_alias = self.field_data.get('datasource_alias', '')
        table_name = self.field_data['table_name']
        if datasource_alias:
            display_table = f"{datasource_alias}.{table_name}"
        else:
            display_table = table_name
        
        table_label = QLabel(display_table)
        table_label.setStyleSheet("color: #7f8c8d; font-size: 9px; background: transparent;")
        label_layout.addWidget(table_label)
        
        label_container.setMinimumWidth(150)
        label_container.setMaximumWidth(200)
        main_layout.addWidget(label_container)

        # Type label (smaller)
        type_label = QLabel(f"({self.field_data['data_type']})")
        type_label.setStyleSheet("color: #7f8c8d; font-size: 9px; background: transparent;")
        type_label.setMaximumWidth(80)
        main_layout.addWidget(type_label)

        # Filter controls container
        self.controls_container = QWidget()
        self.controls_container.setStyleSheet("background: transparent;")
        self.controls_layout = QHBoxLayout(self.controls_container)
        self.controls_layout.setContentsMargins(0, 0, 0, 0)
        self.controls_layout.setSpacing(5)
        main_layout.addWidget(self.controls_container)

        # Add basic filter controls (operator and value)
        self.operator_combo = QComboBox()
        self.operator_combo.addItems(["=", "!=", ">", "<", ">=", "<=", "LIKE", "IN"])
        self.operator_combo.setMaximumWidth(80)
        self.operator_combo.setStyleSheet("background: white;")
        self.controls_layout.addWidget(self.operator_combo)

        self.value_input = QLineEdit()
        self.value_input.setPlaceholderText("Value...")
        self.value_input.setMaximumWidth(150)
        self.value_input.setStyleSheet("background: white;")
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


class XDBJoinWidget(QFrame):
    """Widget for configuring a single JOIN between datasources in XDB queries"""

    remove_requested = pyqtSignal()

    def __init__(self, datasources: list, parent=None):
        super().__init__(parent)
        self.datasources = datasources
        self.parent_screen = parent
        self.left_datasource = None
        self.right_datasource = None
        self.init_ui()

    def init_ui(self):
        """Initialize UI"""
        self.setFrameStyle(QFrame.Shape.Box)
        self.setStyleSheet("""
            XDBJoinWidget {
                border: 1px solid #ddd;
                border-radius: 4px;
                background: white;
                padding: 10px;
            }
        """)

        layout = QVBoxLayout(self)

        # First row: JOIN type and right datasource
        top_layout = QHBoxLayout()

        # JOIN type
        self.join_type_combo = QComboBox()
        self.join_type_combo.addItems(["INNER JOIN", "LEFT OUTER JOIN", "RIGHT OUTER JOIN", "FULL OUTER JOIN"])
        self.join_type_combo.setMinimumWidth(150)
        self.join_type_combo.setMaximumHeight(22)
        self.join_type_combo.setStyleSheet("""
            QComboBox {
                font-size: 10px;
                padding: 2px 4px;
            }
        """)
        top_layout.addWidget(self.join_type_combo)

        # Right datasource selection (the table being joined)
        self.right_datasource_combo = QComboBox()
        for ds in self.datasources:
            display_name = f"{ds['alias']}.{ds['table_name']}"
            self.right_datasource_combo.addItem(display_name, ds)
        self.right_datasource_combo.setMinimumWidth(200)
        self.right_datasource_combo.setMaximumHeight(22)
        self.right_datasource_combo.setStyleSheet("""
            QComboBox {
                font-size: 10px;
                padding: 2px 4px;
            }
        """)
        self.right_datasource_combo.currentIndexChanged.connect(self._on_right_datasource_changed)
        top_layout.addWidget(self.right_datasource_combo)

        top_layout.addStretch()

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
        top_layout.addWidget(remove_btn)

        layout.addLayout(top_layout)

        # Container for ON conditions (can have multiple)
        self.on_conditions_container = QWidget()
        self.on_conditions_layout = QVBoxLayout(self.on_conditions_container)
        self.on_conditions_layout.setContentsMargins(0, 0, 0, 0)
        self.on_conditions_layout.setSpacing(5)
        
        # Store ON condition rows
        self.on_condition_rows = []
        
        # Add first ON condition row
        self._add_on_condition_row()
        
        layout.addWidget(self.on_conditions_container)
        
        # Add button for additional ON conditions
        add_on_btn = QPushButton("+ Add ON Condition")
        add_on_btn.setObjectName("gold_button")
        add_on_btn.setMaximumWidth(150)
        add_on_btn.clicked.connect(self._add_on_condition_row)
        layout.addWidget(add_on_btn)
        
        # Load initial field lists
        self._load_field_lists()

    def _add_on_condition_row(self):
        """Add a new ON condition row"""
        row_widget = QWidget()
        row_layout = QHBoxLayout(row_widget)
        row_layout.setContentsMargins(0, 0, 0, 0)
        row_layout.setSpacing(5)
        
        # ON label (only on first row)
        if len(self.on_condition_rows) == 0:
            on_label = QLabel("ON:")
            on_label.setStyleSheet("font-weight: bold; font-size: 10px;")
            on_label.setMinimumWidth(30)
            row_layout.addWidget(on_label)
        else:
            # AND label for additional conditions
            and_label = QLabel("AND:")
            and_label.setStyleSheet("font-weight: bold; font-size: 10px; color: #7f8c8d;")
            and_label.setMinimumWidth(30)
            row_layout.addWidget(and_label)
        
        # Left datasource dropdown
        left_datasource_combo = QComboBox()
        for ds in self.datasources:
            display_name = f"{ds['alias']}.{ds['table_name']}"
            left_datasource_combo.addItem(display_name, ds)
        left_datasource_combo.setMinimumWidth(150)
        left_datasource_combo.setMaximumHeight(22)
        left_datasource_combo.setStyleSheet("""
            QComboBox {
                font-size: 10px;
                padding: 2px 4px;
            }
        """)
        row_layout.addWidget(left_datasource_combo)
        
        # Left field dropdown
        left_field_combo = QComboBox()
        left_field_combo.setMinimumWidth(150)
        left_field_combo.setMaximumHeight(22)
        left_field_combo.setStyleSheet("""
            QComboBox {
                font-size: 10px;
                padding: 2px 4px;
            }
        """)
        row_layout.addWidget(left_field_combo)

        # Equals label
        equals_label = QLabel("=")
        equals_label.setStyleSheet("font-weight: bold;")
        row_layout.addWidget(equals_label)
        
        # Right datasource dropdown (for the right side of the join condition)
        right_datasource_combo = QComboBox()
        for ds in self.datasources:
            display_name = f"{ds['alias']}.{ds['table_name']}"
            right_datasource_combo.addItem(display_name, ds)
        right_datasource_combo.setMinimumWidth(150)
        right_datasource_combo.setMaximumHeight(22)
        right_datasource_combo.setStyleSheet("""
            QComboBox {
                font-size: 10px;
                padding: 2px 4px;
            }
        """)
        row_layout.addWidget(right_datasource_combo)

        # Right field dropdown
        right_field_combo = QComboBox()
        right_field_combo.setMinimumWidth(150)
        right_field_combo.setMaximumHeight(22)
        right_field_combo.setStyleSheet("""
            QComboBox {
                font-size: 10px;
                padding: 2px 4px;
            }
        """)
        row_layout.addWidget(right_field_combo)
        
        # Remove button (only for additional rows)
        if len(self.on_condition_rows) > 0:
            remove_on_btn = QPushButton("×")
            remove_on_btn.setFixedSize(22, 22)
            remove_on_btn.setStyleSheet("""
                QPushButton {
                    background: #95a5a6;
                    color: white;
                    border: none;
                    border-radius: 3px;
                    font-size: 12px;
                    font-weight: bold;
                }
                QPushButton:hover {
                    background: #7f8c8d;
                }
            """)
            remove_on_btn.clicked.connect(lambda: self._remove_on_condition_row(row_widget))
            row_layout.addWidget(remove_on_btn)
        
        row_layout.addStretch()
        
        # Connect datasource changes to update field lists
        left_datasource_combo.currentIndexChanged.connect(
            lambda: self._update_left_fields(left_datasource_combo, left_field_combo)
        )
        right_datasource_combo.currentIndexChanged.connect(
            lambda: self._update_right_fields(right_datasource_combo, right_field_combo)
        )
        
        # Store references
        row_data = {
            'widget': row_widget,
            'left_datasource_combo': left_datasource_combo,
            'left_field_combo': left_field_combo,
            'right_datasource_combo': right_datasource_combo,
            'right_field_combo': right_field_combo
        }
        self.on_condition_rows.append(row_data)
        
        # Add to layout
        self.on_conditions_layout.addWidget(row_widget)
        
        # Populate the field combos for the new row
        if len(self.datasources) > 0:
            self._update_left_fields(left_datasource_combo, left_field_combo)
            if len(self.datasources) > 1:
                right_datasource_combo.setCurrentIndex(1)
            self._update_right_fields(right_datasource_combo, right_field_combo)

    def _remove_on_condition_row(self, row_widget):
        """Remove an ON condition row"""
        # Find and remove from list
        for i, row_data in enumerate(self.on_condition_rows):
            if row_data['widget'] == row_widget:
                self.on_condition_rows.pop(i)
                break
        
        # Remove widget
        self.on_conditions_layout.removeWidget(row_widget)
        row_widget.deleteLater()

    def _on_right_datasource_changed(self):
        """Handle right datasource selection change"""
        self.right_datasource = self.right_datasource_combo.currentData()
        self._load_field_lists()

    def _load_field_lists(self):
        """Load fields for all datasources in ON conditions"""
        for row_data in self.on_condition_rows:
            self._update_left_fields(
                row_data['left_datasource_combo'],
                row_data['left_field_combo']
            )
            self._update_right_fields(
                row_data['right_datasource_combo'],
                row_data['right_field_combo']
            )

    def _update_left_fields(self, datasource_combo: QComboBox, field_combo: QComboBox):
        """Update left field combo based on selected datasource"""
        field_combo.clear()
        ds = datasource_combo.currentData()
        if ds:
            fields = self._get_datasource_fields(ds)
            field_combo.addItems(fields)

    def _update_right_fields(self, datasource_combo: QComboBox, field_combo: QComboBox):
        """Update right field combo based on selected datasource"""
        field_combo.clear()
        ds = datasource_combo.currentData()
        if ds:
            fields = self._get_datasource_fields(ds)
            field_combo.addItems(fields)

    def _get_datasource_fields(self, datasource: dict) -> list:
        """Get list of fields for a datasource"""
        if not self.parent_screen or not hasattr(self.parent_screen, 'schema_discovery'):
            return []
        
        try:
            connection = datasource['connection']
            connection_id = connection['connection_id']
            table_name = datasource['table_name']
            schema_name = datasource.get('schema_name', '')
            
            columns = self.parent_screen.schema_discovery.get_columns(
                connection_id, table_name, schema_name
            )
            return [col['column_name'] for col in columns]
        except Exception as e:
            logger.error(f"Error loading fields for datasource {datasource.get('alias', 'unknown')}: {e}")
            return []

    def get_join_config(self):
        """Get JOIN configuration as dict"""
        on_conditions = []
        for row_data in self.on_condition_rows:
            left_ds = row_data['left_datasource_combo'].currentData()
            left_field = row_data['left_field_combo'].currentText()
            right_ds = row_data['right_datasource_combo'].currentData()
            right_field = row_data['right_field_combo'].currentText()
            
            if left_ds and left_field and right_ds and right_field:
                on_conditions.append({
                    'left_datasource': left_ds['alias'],
                    'left_field': left_field,
                    'right_datasource': right_ds['alias'],
                    'right_field': right_field
                })
        
        return {
            'join_type': self.join_type_combo.currentText(),
            'right_datasource': self.right_datasource_combo.currentData(),
            'on_conditions': on_conditions
        }
