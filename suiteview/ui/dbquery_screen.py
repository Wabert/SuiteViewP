"""DB Query Screen - Single-database query builder"""

import logging
from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel, QSplitter,
                              QTreeWidget, QTreeWidgetItem, QTabWidget, QPushButton,
                              QScrollArea, QFrame, QLineEdit, QComboBox, QCheckBox,
                              QMessageBox, QInputDialog, QToolBar, QDateEdit, QSizePolicy,
                              QMenu)
from PyQt6.QtCore import Qt, pyqtSignal, QMimeData, QDate
from PyQt6.QtGui import QDrag, QAction

from suiteview.data.repositories import (SavedTableRepository, ConnectionRepository,
                                         get_metadata_cache_repository, get_query_repository)
from suiteview.core.schema_discovery import SchemaDiscovery
from suiteview.core.query_builder import QueryBuilder, Query
from suiteview.core.query_executor import QueryExecutor
from suiteview.ui.dialogs.query_results_dialog import QueryResultsDialog

logger = logging.getLogger(__name__)


class DBQueryScreen(QWidget):
    """DB Query screen with visual query builder"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.saved_table_repo = SavedTableRepository()
        self.conn_repo = ConnectionRepository()
        self.schema_discovery = SchemaDiscovery()
        self.metadata_cache_repo = get_metadata_cache_repository()
        self.query_repo = get_query_repository()
        self.query_builder = QueryBuilder()
        self.query_executor = QueryExecutor()

        # Track current query state
        self.current_connection_id = None
        self.current_database_name = None
        self.current_table_name = None
        self.current_schema_name = None
        self.current_query_name = None  # Track the query name

        # Track query components
        self.criteria_widgets = []  # List of filter widgets in Criteria tab
        self.display_fields = []    # List of fields in Display tab
        self.tables_involved = set()  # Set of table names involved in query
        self.joins = []  # List of join configurations
        
        # Track unsaved query states (query_id -> query_state_dict)
        self.unsaved_query_states = {}
        self.current_query_id = None  # Track which query is currently loaded

        self.init_ui()
        self.load_data_sources()

    def init_ui(self):
        """Initialize the UI"""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        # Create horizontal splitter for four panels
        splitter = QSplitter(Qt.Orientation.Horizontal)

        # Left Panel 1 - Data Sources
        panel1 = self._create_data_sources_panel()
        splitter.addWidget(panel1)

        # Left Panel 2 - Tables
        panel2 = self._create_tables_panel()
        splitter.addWidget(panel2)

        # Left Panel 3 - Fields
        panel3 = self._create_fields_panel()
        splitter.addWidget(panel3)

        # Right Panel - Query Builder
        right_panel = self._create_query_builder_panel()
        splitter.addWidget(right_panel)

        # Set initial sizes (200px, 200px, 200px, remaining)
        splitter.setSizes([200, 200, 200, 600])

        layout.addWidget(splitter)

    def _create_data_sources_panel(self) -> QWidget:
        """Create left panel with data sources tree"""
        panel = QWidget()
        panel_layout = QVBoxLayout(panel)
        panel_layout.setContentsMargins(5, 5, 5, 5)

        # Panel header
        header = QLabel("DATA SOURCES")
        header.setStyleSheet("""
            background: #34495e;
            color: white;
            padding: 8px;
            font-size: 10px;
            font-weight: 800;
            letter-spacing: 1px;
        """)
        panel_layout.addWidget(header)

        # Data sources tree (shows My Data connections)
        self.data_sources_tree = QTreeWidget()
        self.data_sources_tree.setHeaderLabel("Data Sources")
        self.data_sources_tree.setHeaderHidden(True)
        self.data_sources_tree.setStyleSheet("""
            QTreeWidget {
                background: white;
                border: 1px solid #ddd;
                border-radius: 4px;
            }
        """)
        
        # Connect signals
        self.data_sources_tree.itemClicked.connect(self.on_data_source_clicked)
        self.data_sources_tree.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.data_sources_tree.customContextMenuRequested.connect(self.show_data_source_context_menu)

        panel_layout.addWidget(self.data_sources_tree)

        return panel

    def _create_tables_panel(self) -> QWidget:
        """Create middle panel with tables list"""
        panel = QWidget()
        panel_layout = QVBoxLayout(panel)
        panel_layout.setContentsMargins(5, 5, 5, 5)

        # Panel header (will be updated dynamically)
        self.tables_header = QLabel("TABLES")
        self.tables_header.setStyleSheet("""
            background: #34495e;
            color: white;
            padding: 8px;
            font-size: 10px;
            font-weight: 800;
            letter-spacing: 1px;
        """)
        panel_layout.addWidget(self.tables_header)

        # Tables tree
        self.tables_tree = QTreeWidget()
        self.tables_tree.setHeaderLabel("Tables")
        self.tables_tree.setHeaderHidden(True)
        self.tables_tree.setStyleSheet("""
            QTreeWidget {
                background: white;
                border: 1px solid #ddd;
                border-radius: 4px;
            }
        """)
        
        # Connect signals
        self.tables_tree.itemClicked.connect(self.on_table_clicked)

        panel_layout.addWidget(self.tables_tree)

        # Info label
        self.table_info_label = QLabel("Select a database to view tables")
        self.table_info_label.setStyleSheet("color: #7f8c8d; font-size: 10px; padding: 5px;")
        panel_layout.addWidget(self.table_info_label)

        return panel

    def _create_fields_panel(self) -> QWidget:
        """Create fields panel with column list"""
        panel = QWidget()
        panel_layout = QVBoxLayout(panel)
        panel_layout.setContentsMargins(5, 5, 5, 5)

        # Panel header (will be updated dynamically)
        self.fields_header = QLabel("FIELDS")
        self.fields_header.setStyleSheet("""
            background: #34495e;
            color: white;
            padding: 8px;
            font-size: 10px;
            font-weight: 800;
            letter-spacing: 1px;
        """)
        panel_layout.addWidget(self.fields_header)

        # Fields tree (with drag support) - use custom subclass
        self.fields_tree = DraggableFieldsTree()
        self.fields_tree.setHeaderLabel("Fields")
        self.fields_tree.setHeaderHidden(True)
        self.fields_tree.setStyleSheet("""
            QTreeWidget {
                background: white;
                border: 1px solid #ddd;
                border-radius: 4px;
            }
        """)
        
        # Connect double-click to show unique values inline
        self.fields_tree.itemDoubleClicked.connect(self.on_field_double_clicked)

        panel_layout.addWidget(self.fields_tree)

        # Info label
        self.field_info_label = QLabel("Select a table to view fields")
        self.field_info_label.setStyleSheet("color: #7f8c8d; font-size: 10px; padding: 5px;")
        panel_layout.addWidget(self.field_info_label)

        return panel

    def _create_query_builder_panel(self) -> QWidget:
        """Create right panel with query builder tabs"""
        panel = QWidget()
        panel_layout = QVBoxLayout(panel)
        panel_layout.setContentsMargins(5, 5, 5, 5)

        # Toolbar with action buttons
        toolbar_layout = QHBoxLayout()
        toolbar_layout.setContentsMargins(10, 5, 10, 5)
        toolbar_layout.setSpacing(10)

        # Left side: Run and Save buttons
        self.run_query_btn = QPushButton("▶ Run Query")
        self.run_query_btn.setObjectName("gold_button")
        self.run_query_btn.setMinimumWidth(120)
        self.run_query_btn.clicked.connect(self.run_query)
        self.run_query_btn.setEnabled(False)
        toolbar_layout.addWidget(self.run_query_btn)

        self.save_query_btn = QPushButton("💾 Save Query")
        self.save_query_btn.setObjectName("gold_button")
        self.save_query_btn.setMinimumWidth(120)
        self.save_query_btn.clicked.connect(self.save_query)
        self.save_query_btn.setEnabled(False)
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
        self.new_query_btn = QPushButton("� New Query")
        self.new_query_btn.setObjectName("gold_button")
        self.new_query_btn.setMinimumWidth(120)
        self.new_query_btn.clicked.connect(self.new_query)
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

        # Tab widget for Criteria, Display, Tables
        self.query_tabs = QTabWidget()
        self.query_tabs.setStyleSheet("""
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

        # Criteria tab
        self.criteria_tab = self._create_criteria_tab()
        self.query_tabs.addTab(self.criteria_tab, "Criteria")

        # Display tab
        self.display_tab = self._create_display_tab()
        self.query_tabs.addTab(self.display_tab, "Display")

        # Tables tab
        self.tables_tab = self._create_tables_tab()
        self.query_tabs.addTab(self.tables_tab, "Tables")

        panel_layout.addWidget(self.query_tabs)

        return panel

    def _create_criteria_tab(self) -> QWidget:
        """Create Criteria tab with drop zone for filters"""
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setContentsMargins(10, 10, 10, 10)

        # Instructions
        instructions = QLabel("Drag fields here to add filter criteria")
        instructions.setStyleSheet("color: #7f8c8d; font-style: italic; padding: 10px;")
        layout.addWidget(instructions)

        # Scroll area for criteria widgets
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet("""
            QScrollArea {
                border: none;
                background: transparent;
            }
        """)

        # Container for criteria widgets
        self.criteria_container = QWidget()
        self.criteria_layout = QVBoxLayout(self.criteria_container)
        self.criteria_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        self.criteria_layout.setSpacing(10)

        # Drop zone widget
        self.criteria_drop_zone = DropZoneWidget("Drag fields here to add filters")
        self.criteria_drop_zone.field_dropped.connect(self.add_criteria_filter)
        self.criteria_layout.addWidget(self.criteria_drop_zone)

        scroll.setWidget(self.criteria_container)
        layout.addWidget(scroll)

        return tab

    def _create_display_tab(self) -> QWidget:
        """Create Display tab with drop zone for fields"""
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setContentsMargins(10, 10, 10, 10)

        # Instructions
        instructions = QLabel("Drag fields here to add to SELECT list")
        instructions.setStyleSheet("color: #7f8c8d; font-style: italic; padding: 10px;")
        layout.addWidget(instructions)

        # Scroll area for display fields
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet("""
            QScrollArea {
                border: none;
                background: transparent;
            }
        """)

        # Container for display fields
        self.display_container = QWidget()
        self.display_layout = QVBoxLayout(self.display_container)
        self.display_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        self.display_layout.setSpacing(10)

        # Drop zone widget
        self.display_drop_zone = DropZoneWidget("Drag fields here to add to display")
        self.display_drop_zone.field_dropped.connect(self.add_display_field)
        self.display_layout.addWidget(self.display_drop_zone)

        scroll.setWidget(self.display_container)
        layout.addWidget(scroll)

        return tab

    def _create_tables_tab(self) -> QWidget:
        """Create Tables tab with FROM and JOIN configuration"""
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setContentsMargins(10, 10, 10, 10)

        # Tables involved section
        tables_label = QLabel("Tables Involved:")
        tables_label.setStyleSheet("font-weight: bold; padding: 5px;")
        layout.addWidget(tables_label)

        self.tables_involved_label = QLabel("(None)")
        self.tables_involved_label.setStyleSheet("color: #7f8c8d; padding: 5px 5px 15px 20px;")
        layout.addWidget(self.tables_involved_label)

        # FROM clause section
        from_layout = QHBoxLayout()
        from_label = QLabel("FROM:")
        from_label.setStyleSheet("font-weight: bold;")
        from_layout.addWidget(from_label)

        self.from_table_combo = QComboBox()
        self.from_table_combo.setMinimumWidth(200)
        from_layout.addWidget(self.from_table_combo)
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
        self.add_join_btn.clicked.connect(self.add_join)
        join_header_layout.addWidget(self.add_join_btn)

        layout.addLayout(join_header_layout)

        # Scroll area for joins
        join_scroll = QScrollArea()
        join_scroll.setWidgetResizable(True)
        join_scroll.setStyleSheet("""
            QScrollArea {
                border: none;
                background: transparent;
            }
        """)

        self.joins_container = QWidget()
        self.joins_layout = QVBoxLayout(self.joins_container)
        self.joins_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        self.joins_layout.setSpacing(10)

        join_scroll.setWidget(self.joins_container)
        layout.addWidget(join_scroll)

        layout.addStretch()

        return tab

    def load_data_sources(self):
        """Load data sources from My Data - structured like My Data screen"""
        self.data_sources_tree.clear()

        try:
            # Create three top-level sections
            my_connections_item = QTreeWidgetItem()
            my_connections_item.setText(0, "My Connections")
            my_connections_item.setData(0, Qt.ItemDataRole.UserRole, "section")
            self.data_sources_tree.addTopLevelItem(my_connections_item)

            db_queries_item = QTreeWidgetItem()
            db_queries_item.setText(0, "DB Queries")
            db_queries_item.setData(0, Qt.ItemDataRole.UserRole, "section")
            self.data_sources_tree.addTopLevelItem(db_queries_item)

            xdb_queries_item = QTreeWidgetItem()
            xdb_queries_item.setText(0, "XDB Queries")
            xdb_queries_item.setData(0, Qt.ItemDataRole.UserRole, "section")
            self.data_sources_tree.addTopLevelItem(xdb_queries_item)

            # Load My Connections
            self._load_my_connections(my_connections_item)
            
            # Load DB Queries
            self._load_db_queries(db_queries_item)
            
            # Expand all items in the tree
            self.data_sources_tree.expandAll()

            logger.info(f"Loaded data sources tree")

        except Exception as e:
            logger.error(f"Error loading data sources: {e}")

    def _load_my_connections(self, parent_item: QTreeWidgetItem):
        """Load My Connections section"""
        try:
            # Get all saved tables grouped by connection
            saved_tables = self.saved_table_repo.get_all_saved_tables()

            # Group by connection and type
            connections_dict = {}
            for table in saved_tables:
                conn_id = table['connection_id']
                if conn_id not in connections_dict:
                    conn = self.conn_repo.get_connection(conn_id)
                    if conn:
                        connections_dict[conn_id] = {
                            'connection': conn,
                            'type': conn.get('connection_type', 'Unknown')
                        }

            # Group connections by type
            types_dict = {}
            for conn_id, data in connections_dict.items():
                conn_type = data['type']
                if conn_type not in types_dict:
                    types_dict[conn_type] = []
                types_dict[conn_type].append((conn_id, data['connection']))

            # Add type groups to tree
            for conn_type in sorted(types_dict.keys()):
                # Create type group item
                type_item = QTreeWidgetItem()
                type_item.setText(0, conn_type)
                type_item.setData(0, Qt.ItemDataRole.UserRole, "connection_type")
                type_item.setExpanded(False)
                parent_item.addChild(type_item)

                # Add connections under type
                for conn_id, conn in types_dict[conn_type]:
                    conn_item = QTreeWidgetItem()
                    conn_item.setText(0, conn['connection_name'])
                    conn_item.setData(0, Qt.ItemDataRole.UserRole, "connection")
                    conn_item.setData(0, Qt.ItemDataRole.UserRole + 1, conn_id)
                    conn_item.setData(0, Qt.ItemDataRole.UserRole + 2, conn['database_name'])
                    conn_item.setExpanded(False)
                    type_item.addChild(conn_item)

            logger.info(f"Loaded {len(connections_dict)} connections in {len(types_dict)} type groups")

        except Exception as e:
            logger.error(f"Error loading connections: {e}")

    def _load_db_queries(self, parent_item: QTreeWidgetItem):
        """Load saved DB queries"""
        try:
            queries = self.query_repo.get_all_queries(query_type='DB')
            
            for query in queries:
                query_item = QTreeWidgetItem()
                query_item.setText(0, query['query_name'])
                query_item.setData(0, Qt.ItemDataRole.UserRole, "db_query")
                query_item.setData(0, Qt.ItemDataRole.UserRole + 1, query['query_id'])
                query_item.setData(0, Qt.ItemDataRole.UserRole + 2, query['query_definition'])
                parent_item.addChild(query_item)
            
            logger.info(f"Loaded {len(queries)} DB queries")
            
        except Exception as e:
            logger.error(f"Error loading DB queries: {e}")

    def on_data_source_clicked(self, item: QTreeWidgetItem, column: int):
        """Handle click on data source item"""
        item_type = item.data(0, Qt.ItemDataRole.UserRole)

        if item_type == "connection":
            # Connection clicked - load tables
            conn_id = item.data(0, Qt.ItemDataRole.UserRole + 1)
            db_name = item.data(0, Qt.ItemDataRole.UserRole + 2)
            self.load_tables_for_connection(conn_id, db_name)
            
        elif item_type == "db_query":
            # Saved query clicked - save current state first, then load
            if self.current_query_id:
                self._save_current_query_state()
            
            query_id = item.data(0, Qt.ItemDataRole.UserRole + 1)
            query_definition = item.data(0, Qt.ItemDataRole.UserRole + 2)
            self.load_saved_query(query_id, query_definition)

    def _save_current_query_state(self):
        """Save the current query state to memory (not to database)"""
        if self.current_query_id is None:
            return  # Don't save state for unsaved queries
        
        # Capture current UI state
        state = {
            'connection_id': self.current_connection_id,
            'database_name': self.current_database_name,
            'schema_name': self.current_schema_name,
            'from_table': self.from_table_combo.currentText() if self.from_table_combo.currentText() else None,
            'display_fields': self.display_fields.copy(),
            'criteria': [],
            'joins': []
        }
        
        # Capture criteria widget states
        for i in range(self.criteria_layout.count()):
            widget = self.criteria_layout.itemAt(i).widget()
            if widget and hasattr(widget, 'get_filter_value') and hasattr(widget, 'field_data'):
                filter_value = widget.get_filter_value()
                if filter_value:  # Only save if there's a value
                    state['criteria'].append({
                        'field_data': widget.field_data,
                        'filter_config': filter_value
                    })
        
        # Capture join widget states
        for i in range(self.joins_layout.count()):
            widget = self.joins_layout.itemAt(i).widget()
            if widget and hasattr(widget, 'get_join_config'):
                join_config = widget.get_join_config()
                if join_config:  # Only save if configured
                    state['joins'].append(join_config)
        
        # Store in memory
        self.unsaved_query_states[self.current_query_id] = state
        logger.debug(f"Saved state for query {self.current_query_id}: {state}")

    def show_data_source_context_menu(self, position):
        """Show context menu for data source items"""
        item = self.data_sources_tree.itemAt(position)
        if not item:
            return
        
        item_type = item.data(0, Qt.ItemDataRole.UserRole)
        
        if item_type == "db_query":
            query_id = item.data(0, Qt.ItemDataRole.UserRole + 1)
            query_name = item.text(0)
            
            menu = QMenu(self)
            
            # Copy Query action
            copy_action = QAction("📋 Copy Query", self)
            copy_action.triggered.connect(lambda: self._copy_query(query_id, query_name))
            menu.addAction(copy_action)
            
            # Delete Query action
            delete_action = QAction("🗑️ Delete Query", self)
            delete_action.triggered.connect(lambda: self._delete_query(query_id, query_name))
            menu.addAction(delete_action)
            
            menu.exec(self.data_sources_tree.mapToGlobal(position))

    def _copy_query(self, query_id: int, query_name: str):
        """Copy a saved query"""
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
            existing_queries = self.query_repo.get_all_queries(query_type='DB')
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
                    logger.info(f"Deleted existing query '{new_name}' to overwrite")
            
            # Get the original query
            query_record = self.query_repo.get_query(query_id)
            if not query_record:
                raise Exception("Query not found")
            
            # Save as new query with new name
            new_query_id = self.query_repo.save_query(
                query_name=new_name,
                query_type='DB',
                query_definition=query_record['query_definition'],
                category=query_record.get('category', 'User Queries')
            )
            
            QMessageBox.information(
                self,
                "Query Copied",
                f"Query copied successfully as '{new_name}'!"
            )
            
            # Refresh data sources
            self.load_data_sources()
            
        except Exception as e:
            logger.error(f"Error copying query: {e}")
            QMessageBox.critical(
                self,
                "Copy Failed",
                f"Failed to copy query:\n{str(e)}"
            )

    def _delete_query(self, query_id: int, query_name: str):
        """Delete a saved query"""
        try:
            # Confirm deletion
            reply = QMessageBox.question(
                self,
                "Delete Query",
                f"Are you sure you want to delete the query '{query_name}'?\n\n"
                f"This action cannot be undone.",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No
            )
            
            if reply == QMessageBox.StandardButton.No:
                return
            
            # Delete from database
            self.query_repo.delete_query(query_id)
            
            # If this was the currently loaded query, clear it
            if self.current_query_id == query_id:
                self.new_query()
            
            # Remove from unsaved states if present
            if query_id in self.unsaved_query_states:
                del self.unsaved_query_states[query_id]
            
            QMessageBox.information(
                self,
                "Query Deleted",
                f"Query '{query_name}' has been deleted."
            )
            
            # Refresh data sources
            self.load_data_sources()
            
        except Exception as e:
            logger.error(f"Error deleting query: {e}")
            QMessageBox.critical(
                self,
                "Delete Failed",
                f"Failed to delete query:\n{str(e)}"
            )

    def load_tables_for_connection(self, connection_id: int, database_name: str):
        """Load tables for selected connection"""
        self.current_connection_id = connection_id
        self.current_database_name = database_name
        self.tables_tree.clear()
        self.fields_tree.clear()

        # Update tables header with database name
        self.tables_header.setText(f"{database_name.upper()}: TABLES")

        # Reset fields header
        self.fields_header.setText("FIELDS")

        try:
            # Get saved tables for this connection
            saved_tables = self.saved_table_repo.get_saved_tables(connection_id)

            if not saved_tables:
                self.table_info_label.setText("No saved tables for this connection")
                return

            # Add tables to tree
            for table in saved_tables:
                table_item = QTreeWidgetItem()
                table_name = table['table_name']
                schema_name = table.get('schema_name', '')

                # Display name
                display_name = f"{schema_name}.{table_name}" if schema_name else table_name
                table_item.setText(0, display_name)
                table_item.setData(0, Qt.ItemDataRole.UserRole, "table")
                table_item.setData(0, Qt.ItemDataRole.UserRole + 1, table_name)
                table_item.setData(0, Qt.ItemDataRole.UserRole + 2, schema_name)

                self.tables_tree.addTopLevelItem(table_item)

            self.table_info_label.setText(f"{len(saved_tables)} table(s)")
            logger.info(f"Loaded {len(saved_tables)} tables for connection {connection_id}")

        except Exception as e:
            logger.error(f"Error loading tables: {e}")
            self.table_info_label.setText(f"Error: {str(e)}")

    def on_table_clicked(self, item: QTreeWidgetItem, column: int):
        """Handle click on table"""
        item_type = item.data(0, Qt.ItemDataRole.UserRole)

        if item_type == "table":
            table_name = item.data(0, Qt.ItemDataRole.UserRole + 1)
            schema_name = item.data(0, Qt.ItemDataRole.UserRole + 2)
            self.load_fields_for_table(table_name, schema_name)

    def load_fields_for_table(self, table_name: str, schema_name: str):
        """Load fields for selected table"""
        self.current_table_name = table_name
        self.current_schema_name = schema_name
        self.fields_tree.clear()

        # Update fields header with table name
        display_name = f"{schema_name}.{table_name}" if schema_name else table_name
        self.fields_header.setText(f"{display_name.upper()}: FIELDS")

        try:
            # Get or create metadata
            metadata_id = self.metadata_cache_repo.get_or_create_metadata(
                self.current_connection_id, table_name, schema_name
            )

            # Try cached columns first
            cached_columns = self.metadata_cache_repo.get_cached_columns(metadata_id)

            if cached_columns:
                columns = cached_columns
            else:
                # Load from database
                columns = self.schema_discovery.get_columns(
                    self.current_connection_id, table_name, schema_name
                )

                # Cache them
                self.metadata_cache_repo.cache_column_metadata(metadata_id, [
                    {
                        'name': col['column_name'],
                        'type': col['data_type'],
                        'nullable': col.get('is_nullable', True),
                        'primary_key': col.get('is_primary_key', False),
                        'max_length': col.get('max_length')
                    }
                    for col in columns
                ])

            # Add fields to tree
            for col_data in columns:
                col_name = col_data.get('name') or col_data.get('column_name')
                col_type = col_data.get('type') or col_data.get('data_type')

                field_item = QTreeWidgetItem()
                field_item.setText(0, f"{col_name} ({col_type})")
                field_item.setData(0, Qt.ItemDataRole.UserRole, "field")
                field_item.setData(0, Qt.ItemDataRole.UserRole + 1, col_name)
                field_item.setData(0, Qt.ItemDataRole.UserRole + 2, col_type)
                field_item.setData(0, Qt.ItemDataRole.UserRole + 3, table_name)
                field_item.setData(0, Qt.ItemDataRole.UserRole + 4, schema_name)

                self.fields_tree.addTopLevelItem(field_item)

            self.field_info_label.setText(f"{len(columns)} field(s)")
            logger.info(f"Loaded {len(columns)} fields for table {table_name}")

        except Exception as e:
            logger.error(f"Error loading fields: {e}")
            self.field_info_label.setText(f"Error: {str(e)}")

    def on_field_double_clicked(self, item: QTreeWidgetItem, column: int):
        """Handle double-click on field to show unique values inline"""
        item_type = item.data(0, Qt.ItemDataRole.UserRole)

        if item_type != "field":
            return

        # Check if already expanded with unique values
        if item.childCount() > 0:
            # Collapse
            item.takeChildren()
            return

        # Expand with unique values
        col_name = item.data(0, Qt.ItemDataRole.UserRole + 1)
        table_name = item.data(0, Qt.ItemDataRole.UserRole + 3)
        schema_name = item.data(0, Qt.ItemDataRole.UserRole + 4)

        try:
            # Get cached unique values
            metadata_id = self.metadata_cache_repo.get_or_create_metadata(
                self.current_connection_id, table_name, schema_name
            )
            cached_unique = self.metadata_cache_repo.get_cached_unique_values(
                metadata_id, col_name
            )

            if cached_unique and cached_unique['unique_values']:
                unique_values = cached_unique['unique_values']
            else:
                # Query unique values
                unique_values = self.schema_discovery.get_unique_values(
                    self.current_connection_id, table_name, col_name, schema_name
                )
                # Cache them
                self.metadata_cache_repo.cache_unique_values(
                    metadata_id, col_name, unique_values
                )

            # Add as child items (limit to 50 for display)
            display_count = min(50, len(unique_values))
            for i in range(display_count):
                value = unique_values[i]
                value_item = QTreeWidgetItem()
                value_item.setText(0, str(value) if value is not None else "(NULL)")
                value_item.setData(0, Qt.ItemDataRole.UserRole, "unique_value")
                item.addChild(value_item)

            if len(unique_values) > 50:
                more_item = QTreeWidgetItem()
                more_item.setText(0, f"... and {len(unique_values) - 50} more")
                item.addChild(more_item)

            item.setExpanded(True)

        except Exception as e:
            logger.error(f"Error loading unique values: {e}")
            error_item = QTreeWidgetItem()
            error_item.setText(0, f"Error: {str(e)}")
            item.addChild(error_item)

    def add_criteria_filter(self, field_data: dict):
        """Add a filter widget to criteria tab"""
        # Create filter widget based on data type
        filter_widget = CriteriaFilterWidget(field_data, self)
        filter_widget.remove_requested.connect(lambda: self.remove_criteria_filter(filter_widget))

        # Insert before the drop zone (drop zone is always last)
        insert_position = self.criteria_layout.count() - 1
        self.criteria_layout.insertWidget(insert_position, filter_widget)
        self.criteria_widgets.append(filter_widget)

        # Update tables involved
        self.update_tables_involved()

        # Enable query buttons
        self.update_query_buttons()

        logger.info(f"Added criteria filter for {field_data['field_name']}")

    def remove_criteria_filter(self, widget):
        """Remove a filter widget from criteria tab"""
        self.criteria_widgets.remove(widget)
        self.criteria_layout.removeWidget(widget)
        widget.deleteLater()

        # Update tables involved
        self.update_tables_involved()

        # Update query buttons
        self.update_query_buttons()

    def add_display_field(self, field_data: dict):
        """Add a field to display tab"""
        # Create display field widget
        display_widget = DisplayFieldWidget(field_data, self)
        display_widget.remove_requested.connect(lambda: self.remove_display_field(display_widget))

        # Insert before the drop zone (drop zone is always last)
        insert_position = self.display_layout.count() - 1
        self.display_layout.insertWidget(insert_position, display_widget)
        self.display_fields.append(field_data)

        # Update tables involved
        self.update_tables_involved()

        # Enable query buttons
        self.update_query_buttons()

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

        # Update tables involved
        self.update_tables_involved()

        # Update query buttons
        self.update_query_buttons()

    def update_tables_involved(self):
        """Update the list of tables involved in the query"""
        tables = set()

        # From criteria filters
        for widget in self.criteria_widgets:
            tables.add(widget.field_data['table_name'])

        # From display fields
        for field_data in self.display_fields:
            tables.add(field_data['table_name'])

        self.tables_involved = tables

        # Update Tables tab
        if tables:
            table_list = ", ".join(sorted(tables))
            self.tables_involved_label.setText(table_list)

            # Update FROM combo
            self.from_table_combo.clear()
            for table in sorted(tables):
                self.from_table_combo.addItem(table)
        else:
            self.tables_involved_label.setText("(None)")
            self.from_table_combo.clear()

    def update_query_buttons(self):
        """Enable/disable query buttons based on query state"""
        has_display_fields = len(self.display_fields) > 0
        self.run_query_btn.setEnabled(has_display_fields)
        self.save_query_btn.setEnabled(has_display_fields)

    def add_join(self):
        """Add a new JOIN configuration widget"""
        if len(self.tables_involved) < 2:
            QMessageBox.warning(
                self, "Need Multiple Tables",
                "You need at least 2 tables in your query to add a JOIN.\n\n"
                "Add fields from multiple tables to the Criteria or Display tabs first."
            )
            return

        join_widget = JoinWidget(list(self.tables_involved), self)
        join_widget.remove_requested.connect(lambda: self.remove_join(join_widget))

        self.joins_layout.addWidget(join_widget)
        self.joins.append(join_widget)

        logger.info("Added JOIN widget")

    def remove_join(self, widget):
        """Remove a JOIN widget"""
        self.joins.remove(widget)
        self.joins_layout.removeWidget(widget)
        widget.deleteLater()

    def run_query(self):
        """Execute the query"""
        try:
            # Build query object
            query = self._build_query_object()
            
            # Validate query
            validation_errors = self._validate_query(query)
            if validation_errors:
                QMessageBox.warning(
                    self,
                    "Query Validation Failed",
                    "Please fix the following issues:\n\n" + "\n".join(validation_errors)
                )
                return
            
            # Show progress cursor
            self.setCursor(Qt.CursorShape.WaitCursor)
            
            try:
                # Execute query
                logger.info("Executing query...")
                df = self.query_executor.execute_db_query(query)
                logger.info(f"Query executed successfully, returned {len(df)} rows")
                
                # Get execution metadata
                metadata = self.query_executor.get_execution_metadata()
                logger.info(f"Retrieved metadata: {metadata}")
                
                # Restore cursor
                self.unsetCursor()
                
                # Show results dialog
                logger.info("Creating results dialog...")
                results_dialog = QueryResultsDialog(
                    df,
                    metadata['sql'],
                    metadata['execution_time_ms'],
                    self
                )
                logger.info("Showing results dialog...")
                results_dialog.exec()
                logger.info("Results dialog closed")
                
            except Exception as e:
                self.unsetCursor()
                logger.error(f"Error during query execution or display: {e}", exc_info=True)
                raise
            
        except Exception as e:
            self.unsetCursor()
            logger.error(f"Query execution failed: {e}", exc_info=True)
            QMessageBox.critical(
                self,
                "Query Execution Failed",
                f"Failed to execute query:\n\n{str(e)}"
            )

    def _build_query_object(self) -> Query:
        """Build Query object from current UI state"""
        query = Query()
        
        # Connection info
        query.connection_id = self.current_connection_id
        
        # Display fields
        query.display_fields = self.display_fields.copy()
        
        # FROM clause
        query.from_table = self.from_table_combo.currentText()
        query.from_schema = self.current_schema_name
        
        # Criteria
        query.criteria = []
        for widget in self.criteria_widgets:
            filter_value = widget.get_filter_value()
            if filter_value:
                criterion = {
                    'table_name': widget.field_data['table_name'],
                    'field_name': widget.field_data['field_name'],
                    'data_type': widget.field_data['data_type'],
                    'schema_name': widget.field_data.get('schema_name', ''),
                }
                
                # Add filter-specific fields based on type
                filter_type = filter_value.get('type')
                
                if filter_type == 'string':
                    criterion['match_type'] = filter_value.get('match_type', 'contains')
                    criterion['value'] = filter_value.get('value', '')
                    
                elif filter_type == 'checkbox_list':
                    # Handle checkbox list - convert to IN clause
                    selected = filter_value.get('selected_values', [])
                    if selected:
                        criterion['operator'] = 'IN'
                        criterion['value'] = selected
                        
                elif filter_type == 'numeric_exact':
                    criterion['operator'] = '='
                    criterion['value'] = filter_value.get('value', '')
                    
                elif filter_type == 'numeric_range':
                    low = filter_value.get('low', '')
                    high = filter_value.get('high', '')
                    if low and high:
                        criterion['operator'] = 'BETWEEN'
                        criterion['value'] = (low, high)
                    elif low:
                        criterion['operator'] = '>='
                        criterion['value'] = low
                    elif high:
                        criterion['operator'] = '<='
                        criterion['value'] = high
                        
                elif filter_type == 'date_exact':
                    criterion['operator'] = '='
                    criterion['value'] = filter_value.get('value', '')
                    
                elif filter_type == 'date_range':
                    start = filter_value.get('start', '')
                    end = filter_value.get('end', '')
                    if start and end:
                        criterion['operator'] = 'BETWEEN'
                        criterion['value'] = (start, end)
                    elif start:
                        criterion['operator'] = '>='
                        criterion['value'] = start
                    elif end:
                        criterion['operator'] = '<='
                        criterion['value'] = end
                
                # Only add if we have a value
                if 'value' in criterion and criterion['value']:
                    query.criteria.append(criterion)
        
        # JOINs
        query.joins = []
        for join_widget in self.joins:
            join_config = join_widget.get_join_config()
            if join_config['on_conditions']:
                query.joins.append({
                    'join_type': join_config['join_type'],
                    'table_name': join_config['join_table'],
                    'schema_name': self.current_schema_name,
                    'on_conditions': join_config['on_conditions']
                })
        
        return query

    def _validate_query(self, query: Query) -> list:
        """Validate query and return list of error messages"""
        errors = []
        
        if not query.connection_id:
            errors.append("No database connection selected")
        
        if not query.display_fields:
            errors.append("No display fields selected (add fields to Display tab)")
        
        if not query.from_table:
            errors.append("No FROM table selected (select FROM table in Tables tab)")
        
        return errors

    def save_query(self):
        """Save the query definition"""
        try:
            # Build query object first
            query = self._build_query_object()
            
            # Validate query
            validation_errors = self._validate_query(query)
            if validation_errors:
                QMessageBox.warning(
                    self,
                    "Query Validation Failed",
                    "Please fix the following issues before saving:\n\n" + "\n".join(validation_errors)
                )
                return
            
            # Prompt for query name if not already named
            if not self.current_query_name:
                query_name, ok = QInputDialog.getText(
                    self, "Save Query", "Enter a name for this query:"
                )
                
                if not ok or not query_name.strip():
                    return
                
                query_name = query_name.strip()
            else:
                query_name = self.current_query_name
            
            # Convert Query object to dictionary for storage
            query_dict = {
                'connection_id': query.connection_id,
                'from_table': query.from_table,
                'from_schema': query.from_schema,
                'display_fields': query.display_fields,
                'criteria': query.criteria,
                'joins': query.joins
            }
            
            # Save to database
            query_id = self.query_repo.save_query(
                query_name=query_name,
                query_type='DB',
                query_definition=query_dict,
                category='User Queries'
            )
            
            # Set current query ID and name
            self.current_query_id = query_id
            self.current_query_name = query_name
            
            # Clear unsaved state since we just saved
            if query_id in self.unsaved_query_states:
                del self.unsaved_query_states[query_id]
            
            # Update display
            self._update_query_name_display()
            
            QMessageBox.information(
                self,
                "Query Saved",
                f"Query '{query_name}' has been saved successfully!"
            )
            
            # Refresh data sources to show new query
            self.load_data_sources()
            
        except Exception as e:
            logger.error(f"Error saving query: {e}")
            QMessageBox.critical(
                self,
                "Save Failed",
                f"Failed to save query:\n{str(e)}"
            )

    def load_saved_query(self, query_id: int, query_definition_json: str):
        """Load a saved query into the query builder"""
        try:
            import json
            
            # Check if there's an unsaved state for this query
            if query_id in self.unsaved_query_states:
                logger.info(f"Loading unsaved state for query {query_id}")
                self._restore_query_state(query_id, self.unsaved_query_states[query_id])
                return
            
            # Get the full query record to get the name
            query_record = self.query_repo.get_query(query_id)
            if not query_record:
                raise Exception("Query not found")
            
            # Parse the query definition (handle both string and dict)
            if isinstance(query_definition_json, str):
                query_dict = json.loads(query_definition_json)
            elif isinstance(query_definition_json, dict):
                query_dict = query_definition_json
            else:
                raise Exception(f"Invalid query_definition type: {type(query_definition_json)}")
            
            # Clear current query (without confirmation for saved queries)
            self._clear_query_ui()
            
            # Set the current query ID and name
            self.current_query_id = query_id
            self.current_query_name = query_record['query_name']
            self._update_query_name_display()
            
            # Load connection and tables
            connection_id = query_dict.get('connection_id')
            if connection_id:
                # Get connection info
                conn = self.conn_repo.get_connection(connection_id)
                if conn:
                    self.current_connection_id = connection_id
                    self.current_database_name = conn['database_name']
                    self.current_schema_name = query_dict.get('from_schema', '')
                    
                    # Load tables for this connection
                    self.load_tables_for_connection(connection_id, conn['database_name'])
            
            # Set FROM table
            from_table = query_dict.get('from_table')
            if from_table:
                index = self.from_table_combo.findText(from_table)
                if index >= 0:
                    self.from_table_combo.setCurrentIndex(index)
            
            # Load display fields
            display_fields = query_dict.get('display_fields', [])
            for field in display_fields:
                self.display_fields.append(field)
                # Create the display widget
                display_widget = DisplayFieldWidget(field, self)
                display_widget.remove_requested.connect(lambda w=display_widget: self.remove_display_field(w))
                insert_position = self.display_layout.count() - 1
                self.display_layout.insertWidget(insert_position, display_widget)
            
            # Load criteria filters
            criteria = query_dict.get('criteria', [])
            for criterion in criteria:
                # Convert saved criterion format back to field_data and filter_config
                field_data = {
                    'table_name': criterion.get('table_name', ''),
                    'field_name': criterion.get('field_name', ''),
                    'data_type': criterion.get('data_type', ''),
                    'schema_name': criterion.get('schema_name', '')
                }
                
                # Convert criterion to filter_config format
                filter_config = self._criterion_to_filter_config(criterion)
                
                if filter_config:
                    # Recreate the filter widget
                    filter_widget = CriteriaFilterWidget(field_data, self)
                    filter_widget.remove_requested.connect(lambda w=filter_widget: self.remove_criteria_filter(w))
                    insert_position = self.criteria_layout.count() - 1
                    self.criteria_layout.insertWidget(insert_position, filter_widget)
                    self.criteria_widgets.append(filter_widget)
                    
                    # Restore the filter configuration
                    self._restore_filter_config(filter_widget, filter_config)
            
            # Load JOINs
            joins = query_dict.get('joins', [])
            for join_config in joins:
                # Update tables_involved first (needed by JoinWidget)
                self.update_tables_involved()
                
                # Create the JOIN widget
                join_widget = JoinWidget(list(self.tables_involved), self)
                join_widget.remove_requested.connect(lambda w=join_widget: self.remove_join(w))
                self.joins_layout.addWidget(join_widget)
                self.joins.append(join_widget)
                
                # Restore the JOIN configuration
                self._restore_join_config(join_widget, join_config)
            
            # Update tables involved and buttons
            self.update_tables_involved()
            self.update_query_buttons()
            
            logger.info(f"Loaded query {query_id}: {query_record['query_name']}")
            
        except Exception as e:
            logger.error(f"Error loading saved query: {e}")
            QMessageBox.critical(
                self,
                "Load Failed",
                f"Failed to load query:\n{str(e)}"
            )
    
    def _restore_query_state(self, query_id: int, state: dict):
        """Restore query UI from saved state"""
        try:
            # Get the query name from database
            query_record = self.query_repo.get_query(query_id)
            if not query_record:
                raise Exception("Query not found")
            
            # Clear current query UI
            self._clear_query_ui()
            
            # Set query ID and name
            self.current_query_id = query_id
            self.current_query_name = query_record['query_name']
            self._update_query_name_display()
            
            # Restore connection info
            self.current_connection_id = state.get('connection_id')
            self.current_database_name = state.get('database_name')
            self.current_schema_name = state.get('schema_name')
            
            # Load tables if we have connection info
            if self.current_connection_id and self.current_database_name:
                self.load_tables_for_connection(self.current_connection_id, self.current_database_name)
            
            # Restore FROM table
            from_table = state.get('from_table')
            if from_table:
                index = self.from_table_combo.findText(from_table)
                if index >= 0:
                    self.from_table_combo.setCurrentIndex(index)
            
            # Restore display fields
            for field in state.get('display_fields', []):
                self.display_fields.append(field)
                # Create the display widget
                display_widget = DisplayFieldWidget(field, self)
                display_widget.remove_requested.connect(lambda w=display_widget: self.remove_display_field(w))
                insert_position = self.display_layout.count() - 1
                self.display_layout.insertWidget(insert_position, display_widget)
            
            # Restore criteria filters
            for criterion in state.get('criteria', []):
                # Recreate the filter widget
                filter_widget = CriteriaFilterWidget(criterion['field_data'], self)
                filter_widget.remove_requested.connect(lambda w=filter_widget: self.remove_criteria_filter(w))
                insert_position = self.criteria_layout.count() - 1
                self.criteria_layout.insertWidget(insert_position, filter_widget)
                self.criteria_widgets.append(filter_widget)
                
                # Restore the filter configuration
                self._restore_filter_config(filter_widget, criterion['filter_config'])
            
            # Restore JOINs
            for join_config in state.get('joins', []):
                # Update tables_involved first (needed by JoinWidget)
                self.update_tables_involved()
                
                # Create the JOIN widget
                join_widget = JoinWidget(list(self.tables_involved), self)
                join_widget.remove_requested.connect(lambda w=join_widget: self.remove_join(w))
                self.joins_layout.addWidget(join_widget)
                self.joins.append(join_widget)
                
                # Restore the JOIN configuration
                self._restore_join_config(join_widget, join_config)
            
            # Update tables involved and buttons
            self.update_tables_involved()
            self.update_query_buttons()
            
            logger.info(f"Restored unsaved state for query {query_id}")
            
        except Exception as e:
            logger.error(f"Error restoring query state: {e}")
            QMessageBox.critical(
                self,
                "Restore Failed",
                f"Failed to restore query state:\n{str(e)}"
            )
    
    def _clear_query_ui(self):
        """Clear the query builder UI without confirmation"""
        # Clear all criteria widgets
        for widget in self.criteria_widgets.copy():
            self.remove_criteria_filter(widget)
        
        # Clear all display fields
        for field_data in self.display_fields.copy():
            # Find the widget
            for i in range(self.display_layout.count()):
                widget = self.display_layout.itemAt(i).widget()
                if isinstance(widget, DisplayFieldWidget) and widget.field_data == field_data:
                    self.remove_display_field(widget)
                    break
        
        # Clear all joins
        for widget in self.joins.copy():
            self.remove_join(widget)
        
        # Reset FROM table
        self.from_table_combo.clear()
    
    def _criterion_to_filter_config(self, criterion: dict) -> dict:
        """Convert saved criterion format to filter_config format"""
        operator = criterion.get('operator', '')
        value = criterion.get('value')
        match_type = criterion.get('match_type', '')
        
        # String filters (have match_type)
        if match_type:
            return {
                'type': 'string',
                'match_type': match_type,
                'value': value or ''
            }
        
        # IN operator means checkbox list
        elif operator == 'IN':
            return {
                'type': 'checkbox_list',
                'selected_values': value if isinstance(value, list) else []
            }
        
        # BETWEEN operator
        elif operator == 'BETWEEN':
            if isinstance(value, (tuple, list)) and len(value) == 2:
                # Check if it's a date or numeric based on data_type
                data_type = criterion.get('data_type', '').upper()
                if any(t in data_type for t in ['DATE', 'TIME', 'TIMESTAMP']):
                    return {
                        'type': 'date_range',
                        'start': value[0],
                        'end': value[1]
                    }
                else:
                    return {
                        'type': 'numeric_range',
                        'low': str(value[0]),
                        'high': str(value[1])
                    }
        
        # Comparison operators for numeric/date
        elif operator in ('=', '>=', '<=', '>', '<'):
            data_type = criterion.get('data_type', '').upper()
            
            # Date types
            if any(t in data_type for t in ['DATE', 'TIME', 'TIMESTAMP']):
                if operator == '=':
                    return {
                        'type': 'date_exact',
                        'value': value or ''
                    }
                elif operator == '>=':
                    return {
                        'type': 'date_range',
                        'start': value or '',
                        'end': ''
                    }
                elif operator == '<=':
                    return {
                        'type': 'date_range',
                        'start': '',
                        'end': value or ''
                    }
            
            # Numeric types
            else:
                if operator == '=':
                    return {
                        'type': 'numeric_exact',
                        'value': str(value) if value else ''
                    }
                elif operator == '>=':
                    return {
                        'type': 'numeric_range',
                        'low': str(value) if value else '',
                        'high': ''
                    }
                elif operator == '<=':
                    return {
                        'type': 'numeric_range',
                        'low': '',
                        'high': str(value) if value else ''
                    }
        
        # Default fallback
        return {
            'type': 'text',
            'value': str(value) if value else ''
        }
    
    def _restore_filter_config(self, filter_widget: 'CriteriaFilterWidget', filter_config: dict):
        """Restore filter widget configuration from saved state"""
        if not filter_config:
            return
        
        filter_type = filter_config.get('type')
        
        try:
            if filter_type == 'string':
                if hasattr(filter_widget, 'match_type_combo') and hasattr(filter_widget, 'filter_input'):
                    # Map match_type back to display text
                    match_type_map = {
                        'exact': 'Exact',
                        'starts_with': 'Starts',
                        'ends_with': 'Ends',
                        'contains': 'Contains'
                    }
                    display_text = match_type_map.get(filter_config.get('match_type', 'exact'), 'Exact')
                    filter_widget.match_type_combo.setCurrentText(display_text)
                    filter_widget.filter_input.setText(filter_config.get('value', ''))
            
            elif filter_type == 'numeric_exact':
                if hasattr(filter_widget, 'exact_input'):
                    filter_widget.exact_input.setText(str(filter_config.get('value', '')))
            
            elif filter_type == 'numeric_range':
                if hasattr(filter_widget, 'range_low_input') and hasattr(filter_widget, 'range_high_input'):
                    filter_widget.range_low_input.setText(str(filter_config.get('low', '')))
                    filter_widget.range_high_input.setText(str(filter_config.get('high', '')))
            
            elif filter_type == 'date_exact':
                if hasattr(filter_widget, 'exact_date_input'):
                    from PyQt6.QtCore import QDate
                    date_str = filter_config.get('value', '')
                    if date_str:
                        date = QDate.fromString(date_str, 'yyyy-MM-dd')
                        filter_widget.exact_date_input.setDate(date)
            
            elif filter_type == 'date_range':
                if hasattr(filter_widget, 'date_range_start') and hasattr(filter_widget, 'date_range_end'):
                    from PyQt6.QtCore import QDate
                    start_str = filter_config.get('start', '')
                    end_str = filter_config.get('end', '')
                    if start_str:
                        start_date = QDate.fromString(start_str, 'yyyy-MM-dd')
                        filter_widget.date_range_start.setDate(start_date)
                    if end_str:
                        end_date = QDate.fromString(end_str, 'yyyy-MM-dd')
                        filter_widget.date_range_end.setDate(end_date)
            
            elif filter_type == 'checkbox_list':
                selected_values = filter_config.get('selected_values', [])
                # Check the appropriate checkboxes
                for cb in filter_widget.value_checkboxes:
                    if cb.value in selected_values:
                        cb.setChecked(True)
                    else:
                        cb.setChecked(False)
                
                # Also restore text filter if present
                if 'text_value' in filter_config and hasattr(filter_widget, 'filter_input'):
                    filter_widget.filter_input.setText(filter_config.get('text_value', ''))
                if 'text_match' in filter_config and hasattr(filter_widget, 'match_type_combo'):
                    filter_widget.match_type_combo.setCurrentText(filter_config.get('text_match', 'Exact'))
            
            elif filter_type == 'text':
                if hasattr(filter_widget, 'filter_input'):
                    filter_widget.filter_input.setText(filter_config.get('value', ''))
        
        except Exception as e:
            logger.warning(f"Could not fully restore filter config: {e}")
    
    def _restore_join_config(self, join_widget: 'JoinWidget', join_config: dict):
        """Restore JOIN widget configuration from saved state"""
        if not join_config:
            return
        
        try:
            # Set join type
            if hasattr(join_widget, 'join_type_combo'):
                join_widget.join_type_combo.setCurrentText(join_config.get('join_type', 'INNER JOIN'))
            
            # Set join table
            if hasattr(join_widget, 'join_table_combo'):
                join_widget.join_table_combo.setCurrentText(join_config.get('join_table', ''))
            
            # Restore ON conditions
            on_conditions = join_config.get('on_conditions', [])
            
            # The first condition row already exists, populate it
            if on_conditions and hasattr(join_widget, 'on_condition_rows') and join_widget.on_condition_rows:
                first_row = join_widget.on_condition_rows[0]
                first_condition = on_conditions[0]
                
                if 'left_field_combo' in first_row:
                    first_row['left_field_combo'].setCurrentText(first_condition.get('left_field', ''))
                if 'operator_combo' in first_row:
                    first_row['operator_combo'].setCurrentText(first_condition.get('operator', '='))
                if 'right_field_combo' in first_row:
                    first_row['right_field_combo'].setCurrentText(first_condition.get('right_field', ''))
            
            # Add and populate additional condition rows
            for i in range(1, len(on_conditions)):
                # Add new row
                if hasattr(join_widget, '_add_on_condition_row'):
                    join_widget._add_on_condition_row()
                    
                    # Populate the new row
                    if i < len(join_widget.on_condition_rows):
                        row = join_widget.on_condition_rows[i]
                        condition = on_conditions[i]
                        
                        if 'left_field_combo' in row:
                            row['left_field_combo'].setCurrentText(condition.get('left_field', ''))
                        if 'operator_combo' in row:
                            row['operator_combo'].setCurrentText(condition.get('operator', '='))
                        if 'right_field_combo' in row:
                            row['right_field_combo'].setCurrentText(condition.get('right_field', ''))
        
        except Exception as e:
            logger.warning(f"Could not fully restore JOIN config: {e}")

    def new_query(self):
        """Clear current query and start fresh"""
        # Save current query state if it's a saved query with changes
        if self.current_query_id is not None:
            self._save_current_query_state()
        
        # Confirm if there are unsaved changes
        if self.display_fields or self.criteria_widgets or self.joins:
            reply = QMessageBox.question(
                self,
                "New Query",
                "Are you sure you want to start a new query?\n\n"
                "All unsaved changes will be lost.",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No
            )
            
            if reply == QMessageBox.StandardButton.No:
                return
        
        # Clear the UI
        self._clear_query_ui()
        
        # Reset tables involved
        self.tables_involved = set()
        self.tables_involved_label.setText("(None)")
        
        # Clear fields panel
        self.fields_tree.clear()
        self.field_info_label.setText("Select a table to view fields")
        
        # Reset current state
        self.current_table_name = None
        self.current_schema_name = None
        self.current_query_name = None
        self.current_query_id = None
        
        # Update query name display
        self._update_query_name_display()
        
        logger.info("Started new query - cleared all previous state")

    def _update_query_name_display(self):
        """Update the query name label"""
        if self.current_query_name:
            self.query_name_label.setText(self.current_query_name)
            self.query_name_label.setStyleSheet("""
                QLabel {
                    color: #2c3e50;
                    font-size: 18px;
                    font-weight: bold;
                    padding: 5px 20px;
                }
            """)
        else:
            self.query_name_label.setText("unnamed")
            self.query_name_label.setStyleSheet("""
                QLabel {
                    color: #95a5a6;
                    font-size: 16px;
                    font-style: italic;
                    padding: 5px 20px;
                }
            """)



class DropZoneWidget(QWidget):
    """Drop zone widget for drag-and-drop fields"""

    field_dropped = pyqtSignal(dict)  # Emits field data when dropped

    def __init__(self, message: str, parent=None):
        super().__init__(parent)
        self.message = message
        self.init_ui()

    def init_ui(self):
        """Initialize UI"""
        self.setAcceptDrops(True)
        self.setMinimumHeight(100)
        self.setStyleSheet("""
            DropZoneWidget {
                border: 2px dashed #ccc;
                border-radius: 4px;
                background: #f8f9fa;
            }
        """)

        layout = QVBoxLayout(self)
        label = QLabel(self.message)
        label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        label.setStyleSheet("color: #7f8c8d; font-style: italic;")
        layout.addWidget(label)

    def dragEnterEvent(self, event):
        """Handle drag enter"""
        if event.mimeData().hasText():
            event.acceptProposedAction()
            self.setStyleSheet("""
                DropZoneWidget {
                    border: 2px dashed #667eea;
                    border-radius: 4px;
                    background: #e8eaf6;
                }
            """)

    def dragLeaveEvent(self, event):
        """Handle drag leave"""
        self.setStyleSheet("""
            DropZoneWidget {
                border: 2px dashed #ccc;
                border-radius: 4px;
                background: #f8f9fa;
            }
        """)

    def dropEvent(self, event):
        """Handle drop"""
        try:
            # Parse field data from mime data
            import json
            field_data = json.loads(event.mimeData().text())
            self.field_dropped.emit(field_data)

            # Reset styling
            self.setStyleSheet("""
                DropZoneWidget {
                    border: 2px dashed #ccc;
                    border-radius: 4px;
                    background: #f8f9fa;
                }
            """)

        except Exception as e:
            logger.error(f"Error handling drop: {e}")


class CriteriaFilterWidget(QFrame):
    """Widget for a single filter criterion"""

    remove_requested = pyqtSignal()

    def __init__(self, field_data: dict, parent=None):
        super().__init__(parent)
        self.field_data = field_data
        self.parent_screen = parent
        self.unique_values = None
        self.value_checkboxes = []
        self.init_ui()

    def init_ui(self):
        """Initialize UI"""
        self.setFrameStyle(QFrame.Shape.Box)
        self.setStyleSheet("""
            CriteriaFilterWidget {
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

        # Field name label (compact)
        field_label = QLabel(f"{self.field_data['table_name']}.{self.field_data['field_name']}")
        field_label.setStyleSheet("font-weight: bold; font-size: 11px;")
        field_label.setMinimumWidth(150)
        field_label.setMaximumWidth(200)
        main_layout.addWidget(field_label)

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

        # Add filter controls
        self._add_filter_controls()

        # Remove button (square)
        remove_btn = QPushButton("×")
        remove_btn.setFixedSize(30, 30)  # Square button
        remove_btn.setStyleSheet("""
            QPushButton {
                background: #e74c3c;
                color: white;
                border: none;
                border-radius: 3px;
                font-size: 14px;
                font-weight: bold;
                padding: 0px;
            }
            QPushButton:hover {
                background: #c0392b;
            }
        """)
        remove_btn.clicked.connect(self.remove_requested.emit)
        main_layout.addWidget(remove_btn)
        
        # Add stretch to prevent expansion
        main_layout.addStretch()

    def _add_filter_controls(self):
        """Add type-specific filter controls"""
        data_type = self.field_data['data_type'].upper()

        # Check if we have cached unique values
        self._load_unique_values()

        # Determine if string type
        is_string = any(t in data_type for t in ['CHAR', 'VARCHAR', 'TEXT', 'STRING'])
        is_numeric = any(t in data_type for t in ['INT', 'DECIMAL', 'NUMERIC', 'FLOAT', 'DOUBLE', 'REAL', 'NUMBER'])
        is_date = any(t in data_type for t in ['DATE', 'TIME', 'TIMESTAMP'])

        # If we have unique values and they're limited (< 50), show checkbox list PLUS controls
        if self.unique_values and len(self.unique_values) < 50:
            # Add the type-specific control first (left side)
            if is_string:
                self._add_string_filter_compact()
            elif is_numeric:
                self._add_numeric_filter_compact()
            elif is_date:
                self._add_date_filter_compact()
            else:
                self._add_default_filter_compact()
            
            # Then add checkbox list (right side)
            self._add_checkbox_list_compact()
        # String types
        elif is_string:
            self._add_string_filter_compact()
        # Numeric types
        elif is_numeric:
            self._add_numeric_filter_compact()
        # Date/Time types
        elif is_date:
            self._add_date_filter_compact()
        # Default: simple text input
        else:
            self._add_default_filter_compact()

    def _load_unique_values(self):
        """Try to load cached unique values for this field"""
        try:
            metadata_id = self.parent_screen.metadata_cache_repo.get_or_create_metadata(
                self.parent_screen.current_connection_id,
                self.field_data['table_name'],
                self.field_data.get('schema_name', '')
            )
            
            cached_unique = self.parent_screen.metadata_cache_repo.get_cached_unique_values(
                metadata_id,
                self.field_data['field_name']
            )
            
            if cached_unique:
                self.unique_values = cached_unique['unique_values']
        except Exception as e:
            logger.warning(f"Could not load unique values: {e}")
            self.unique_values = None

    def _add_checkbox_list_compact(self):
        """Add compact checkbox list for limited unique values - tight spacing like VBA tool"""
        # Compact scrollable checkbox area
        scroll = QScrollArea()
        scroll.setFixedHeight(80)
        scroll.setMinimumWidth(200)
        scroll.setMaximumWidth(280)
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setStyleSheet("""
            QScrollArea {
                border: 1px solid #ccc;
                border-radius: 3px;
                background: #fafafa;
            }
        """)

        checkbox_widget = QWidget()
        checkbox_layout = QVBoxLayout(checkbox_widget)
        checkbox_layout.setSpacing(0)  # No spacing between items like VBA tool
        checkbox_layout.setContentsMargins(2, 2, 2, 2)

        self.value_checkboxes = []
        
        # Add [Select All] checkbox - compact like VBA, no checkbox indicator
        select_all_cb = QCheckBox("[Select All]")
        select_all_cb.setStyleSheet("""
            QCheckBox {
                font-weight: bold; 
                color: #3498db;
                font-size: 10px;
                padding: 0px;
                spacing: 2px;
            }
            QCheckBox::indicator {
                width: 0px;
                height: 0px;
            }
        """)
        select_all_cb.setMaximumHeight(14)
        select_all_cb.setChecked(True)
        select_all_cb.stateChanged.connect(self._on_select_all_changed)
        checkbox_layout.addWidget(select_all_cb)
        self.select_all_checkbox = select_all_cb
        
        # Add [Select None] - compact like VBA, no checkbox indicator
        select_none_cb = QCheckBox("[Select None]")
        select_none_cb.setStyleSheet("""
            QCheckBox {
                font-weight: bold; 
                color: #e74c3c;
                font-size: 10px;
                padding: 0px;
                spacing: 2px;
            }
            QCheckBox::indicator {
                width: 0px;
                height: 0px;
            }
        """)
        select_none_cb.setMaximumHeight(14)
        select_none_cb.setChecked(False)
        select_none_cb.stateChanged.connect(self._on_select_none_changed)
        checkbox_layout.addWidget(select_none_cb)
        self.select_none_checkbox = select_none_cb
        
        # Add separator line
        separator = QFrame()
        separator.setFrameShape(QFrame.Shape.HLine)
        separator.setStyleSheet("background: #ddd; max-height: 1px;")
        separator.setMaximumHeight(1)
        checkbox_layout.addWidget(separator)
        
        # Add value checkboxes - compact like VBA tool
        for value in self.unique_values:
            cb = QCheckBox(str(value) if value is not None else "(NULL)")
            cb.setChecked(True)  # Default: all selected
            cb.value = value  # Store value as attribute
            cb.stateChanged.connect(self._on_value_checkbox_changed)
            # Make compact like VBA tool
            cb.setStyleSheet("""
                QCheckBox {
                    font-size: 10px;
                    padding: 0px;
                    spacing: 2px;
                }
                QCheckBox::indicator {
                    width: 12px;
                    height: 12px;
                }
            """)
            cb.setMaximumHeight(14)
            checkbox_layout.addWidget(cb)
            self.value_checkboxes.append(cb)

        checkbox_layout.addStretch()
        scroll.setWidget(checkbox_widget)
        self.controls_layout.addWidget(scroll)

    def _on_select_all_changed(self, state):
        """Handle Select All checkbox"""
        if state == Qt.CheckState.Checked.value:
            self.select_none_checkbox.blockSignals(True)
            self.select_none_checkbox.setChecked(False)
            self.select_none_checkbox.blockSignals(False)
            for cb in self.value_checkboxes:
                cb.setChecked(True)
    
    def _on_select_none_changed(self, state):
        """Handle Select None checkbox"""
        if state == Qt.CheckState.Checked.value:
            self.select_all_checkbox.blockSignals(True)
            self.select_all_checkbox.setChecked(False)
            self.select_all_checkbox.blockSignals(False)
            for cb in self.value_checkboxes:
                cb.setChecked(False)
            # Uncheck self after action
            self.select_none_checkbox.blockSignals(True)
            self.select_none_checkbox.setChecked(False)
            self.select_none_checkbox.blockSignals(False)
    
    def _on_value_checkbox_changed(self):
        """Handle individual value checkbox changes"""
        # Update Select All/None state based on selections
        all_checked = all(cb.isChecked() for cb in self.value_checkboxes)
        none_checked = not any(cb.isChecked() for cb in self.value_checkboxes)
        
        self.select_all_checkbox.blockSignals(True)
        self.select_all_checkbox.setChecked(all_checked)
        self.select_all_checkbox.blockSignals(False)
        
        self.select_none_checkbox.blockSignals(True)
        self.select_none_checkbox.setChecked(False)  # Always unchecked unless clicked
        self.select_none_checkbox.blockSignals(False)

    def _add_string_filter_compact(self):
        """Add compact string filter controls"""
        # Match type dropdown (compact with reduced height)
        self.match_type_combo = QComboBox()
        self.match_type_combo.addItems(["Exact", "Starts", "Ends", "Contains"])
        self.match_type_combo.setMinimumWidth(80)
        self.match_type_combo.setMaximumWidth(90)
        self.match_type_combo.setMaximumHeight(22)
        self.match_type_combo.setStyleSheet("""
            QComboBox {
                font-size: 10px;
                padding: 2px 4px;
            }
        """)
        self.controls_layout.addWidget(self.match_type_combo)

        # Text input (compact with reduced height)
        self.filter_input = QLineEdit()
        self.filter_input.setPlaceholderText("Enter text...")
        self.filter_input.setMinimumWidth(120)
        self.filter_input.setMaximumWidth(200)
        self.filter_input.setMaximumHeight(22)
        self.filter_input.setStyleSheet("""
            QLineEdit {
                font-size: 10px;
                padding: 2px 4px;
            }
        """)
        self.controls_layout.addWidget(self.filter_input)

    def _add_numeric_filter_compact(self):
        """Add compact numeric filter controls"""
        # Exact value (reduced height)
        self.exact_input = QLineEdit()
        self.exact_input.setPlaceholderText("Exact value")
        self.exact_input.setMinimumWidth(80)
        self.exact_input.setMaximumWidth(100)
        self.exact_input.setMaximumHeight(22)
        self.exact_input.setStyleSheet("""
            QLineEdit {
                font-size: 10px;
                padding: 2px 4px;
            }
        """)
        self.controls_layout.addWidget(self.exact_input)

        # Or label
        or_label = QLabel("or")
        or_label.setStyleSheet("font-size: 10px; color: #7f8c8d;")
        self.controls_layout.addWidget(or_label)

        # Range low (reduced height)
        self.range_low_input = QLineEdit()
        self.range_low_input.setPlaceholderText("Min")
        self.range_low_input.setMinimumWidth(60)
        self.range_low_input.setMaximumWidth(80)
        self.range_low_input.setMaximumHeight(22)
        self.range_low_input.setStyleSheet("""
            QLineEdit {
                font-size: 10px;
                padding: 2px 4px;
            }
        """)
        self.controls_layout.addWidget(self.range_low_input)

        # To label
        to_label = QLabel("to")
        to_label.setStyleSheet("font-size: 10px; color: #7f8c8d;")
        self.controls_layout.addWidget(to_label)

        # Range high (reduced height)
        self.range_high_input = QLineEdit()
        self.range_high_input.setPlaceholderText("Max")
        self.range_high_input.setMinimumWidth(60)
        self.range_high_input.setMaximumWidth(80)
        self.range_high_input.setMaximumHeight(22)
        self.range_high_input.setStyleSheet("""
            QLineEdit {
                font-size: 10px;
                padding: 2px 4px;
            }
        """)
        self.controls_layout.addWidget(self.range_high_input)

    def _add_date_filter_compact(self):
        """Add compact date filter controls"""
        # Exact date (reduced height)
        self.exact_date_input = QDateEdit()
        self.exact_date_input.setCalendarPopup(True)
        self.exact_date_input.setDate(QDate.currentDate())
        self.exact_date_input.setMinimumWidth(100)
        self.exact_date_input.setMaximumWidth(120)
        self.exact_date_input.setMaximumHeight(22)
        self.exact_date_input.setDisplayFormat("MM/dd/yyyy")
        self.exact_date_input.setStyleSheet("""
            QDateEdit {
                font-size: 10px;
                padding: 2px 4px;
            }
        """)
        self.controls_layout.addWidget(self.exact_date_input)

        # Or label
        or_label = QLabel("or")
        or_label.setStyleSheet("font-size: 10px; color: #7f8c8d;")
        self.controls_layout.addWidget(or_label)

        # Date range start (reduced height)
        self.date_range_start = QDateEdit()
        self.date_range_start.setCalendarPopup(True)
        self.date_range_start.setDate(QDate.currentDate())
        self.date_range_start.setMinimumWidth(100)
        self.date_range_start.setMaximumWidth(120)
        self.date_range_start.setMaximumHeight(22)
        self.date_range_start.setDisplayFormat("MM/dd/yyyy")
        self.date_range_start.setStyleSheet("""
            QDateEdit {
                font-size: 10px;
                padding: 2px 4px;
            }
        """)
        self.controls_layout.addWidget(self.date_range_start)

        # To label
        to_label = QLabel("to")
        to_label.setStyleSheet("font-size: 10px; color: #7f8c8d;")
        self.controls_layout.addWidget(to_label)

        # Date range end (reduced height)
        self.date_range_end = QDateEdit()
        self.date_range_end.setCalendarPopup(True)
        self.date_range_end.setDate(QDate.currentDate())
        self.date_range_end.setMinimumWidth(100)
        self.date_range_end.setMaximumWidth(120)
        self.date_range_end.setMaximumHeight(22)
        self.date_range_end.setDisplayFormat("MM/dd/yyyy")
        self.date_range_end.setStyleSheet("""
            QDateEdit {
                font-size: 10px;
                padding: 2px 4px;
            }
        """)
        self.controls_layout.addWidget(self.date_range_end)

    def _add_default_filter_compact(self):
        """Add simple text input for unknown types"""
        self.filter_input = QLineEdit()
        self.filter_input.setPlaceholderText("Enter value...")
        self.filter_input.setMinimumWidth(150)
        self.filter_input.setMaximumWidth(200)
        self.filter_input.setMaximumHeight(22)
        self.filter_input.setStyleSheet("""
            QLineEdit {
                font-size: 10px;
                padding: 2px 4px;
            }
        """)
        self.controls_layout.addWidget(self.filter_input)
        self.date_range_start.setMinimumWidth(100)
        self.date_range_start.setMaximumWidth(120)
        self.date_range_start.setStyleSheet("font-size: 10px;")
        self.date_range_start.setDisplayFormat("MM/dd/yyyy")
        self.controls_layout.addWidget(self.date_range_start)

        # To label
        to_label = QLabel("to")
        to_label.setStyleSheet("font-size: 10px; color: #7f8c8d;")
        self.controls_layout.addWidget(to_label)

        # Date range end
        self.date_range_end = QDateEdit()
        self.date_range_end.setCalendarPopup(True)
        self.date_range_end.setDate(QDate.currentDate())
        self.date_range_end.setMinimumWidth(100)
        self.date_range_end.setMaximumWidth(120)
        self.date_range_end.setStyleSheet("font-size: 10px;")
        self.date_range_end.setDisplayFormat("MM/dd/yyyy")
        self.controls_layout.addWidget(self.date_range_end)

    def _add_default_filter_compact(self):
        """Add compact default text input filter"""
        self.filter_input = QLineEdit()
        self.filter_input.setPlaceholderText("Enter value...")
        self.filter_input.setMinimumWidth(150)
        self.filter_input.setMaximumWidth(250)
        self.filter_input.setStyleSheet("font-size: 10px;")
        self.controls_layout.addWidget(self.filter_input)

    def get_filter_value(self):
        """Get the current filter configuration"""
        data_type = self.field_data['data_type'].upper()

        # Checkbox list mode (get selected values)
        if self.value_checkboxes:
            selected_values = [cb.value for cb in self.value_checkboxes if cb.isChecked()]
            result = {
                'type': 'checkbox_list',
                'selected_values': selected_values  # Changed from 'values' to 'selected_values'
            }
            # Also check if there's a text/range input with value
            if hasattr(self, 'filter_input') and self.filter_input.text():
                result['text_value'] = self.filter_input.text()
                if hasattr(self, 'match_type_combo'):
                    result['text_match'] = self.match_type_combo.currentText()
            return result

        # String mode
        if hasattr(self, 'match_type_combo'):
            match_types = {
                'Exact': 'exact',
                'Starts': 'starts_with',
                'Ends': 'ends_with',
                'Contains': 'contains'
            }
            return {
                'type': 'string',
                'match_type': match_types.get(self.match_type_combo.currentText(), 'exact'),
                'value': self.filter_input.text() if hasattr(self, 'filter_input') else ''
            }

        # Numeric mode (check which input has value)
        if hasattr(self, 'exact_input'):
            exact_val = self.exact_input.text().strip()
            low_val = self.range_low_input.text().strip() if hasattr(self, 'range_low_input') else ''
            high_val = self.range_high_input.text().strip() if hasattr(self, 'range_high_input') else ''
            
            if exact_val:
                return {
                    'type': 'numeric_exact',
                    'value': exact_val
                }
            elif low_val or high_val:
                return {
                    'type': 'numeric_range',
                    'low': low_val,
                    'high': high_val
                }

        # Date mode (check which input to use)
        if hasattr(self, 'exact_date_input'):
            # Check if range inputs have been modified from default
            if hasattr(self, 'date_range_start') and hasattr(self, 'date_range_end'):
                start_date = self.date_range_start.date().toString('yyyy-MM-dd')
                end_date = self.date_range_end.date().toString('yyyy-MM-dd')
                exact_date = self.exact_date_input.date().toString('yyyy-MM-dd')
                
                # If range dates differ from current date, use range
                if start_date != exact_date or end_date != exact_date:
                    return {
                        'type': 'date_range',
                        'start': start_date,
                        'end': end_date
                    }
            
            # Otherwise use exact date
            return {
                'type': 'date_exact',
                'value': self.exact_date_input.date().toString('yyyy-MM-dd')
            }

        # Default mode
        if hasattr(self, 'filter_input'):
            return {
                'type': 'text',
                'value': self.filter_input.text()
            }

        return None


class DisplayFieldWidget(QFrame):
    """Widget for a single display field"""

    remove_requested = pyqtSignal()

    def __init__(self, field_data: dict, parent=None):
        super().__init__(parent)
        self.field_data = field_data
        self.init_ui()

    def init_ui(self):
        """Initialize UI"""
        self.setFrameStyle(QFrame.Shape.Box)
        self.setStyleSheet("""
            DisplayFieldWidget {
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

        # Field name label (fully qualified, compact)
        field_label = QLabel(f"{self.field_data['table_name']}.{self.field_data['field_name']}")
        field_label.setStyleSheet("font-family: 'Consolas', monospace; font-size: 11px; font-weight: bold;")
        field_label.setMinimumWidth(150)
        field_label.setMaximumWidth(250)
        layout.addWidget(field_label)

        # Type label (compact)
        type_label = QLabel(f"({self.field_data['data_type']})")
        type_label.setStyleSheet("color: #7f8c8d; font-size: 9px;")
        type_label.setMaximumWidth(80)
        layout.addWidget(type_label)

        # Remove button (square)
        remove_btn = QPushButton("×")
        remove_btn.setFixedSize(30, 30)
        remove_btn.setStyleSheet("""
            QPushButton {
                background: #e74c3c;
                color: white;
                border: none;
                border-radius: 3px;
                font-size: 14px;
                font-weight: bold;
            }
            QPushButton:hover {
                background: #c0392b;
            }
        """)
        remove_btn.clicked.connect(self.remove_requested.emit)
        layout.addWidget(remove_btn)
        
        # Add stretch to prevent expansion
        layout.addStretch()


class JoinWidget(QFrame):
    """Widget for configuring a single JOIN"""

    remove_requested = pyqtSignal()

    def __init__(self, tables: list, parent=None):
        super().__init__(parent)
        self.tables = tables
        self.parent_screen = parent
        self.from_table = None
        self.join_table = None
        self.init_ui()

    def init_ui(self):
        """Initialize UI"""
        self.setFrameStyle(QFrame.Shape.Box)
        self.setStyleSheet("""
            JoinWidget {
                border: 1px solid #ddd;
                border-radius: 4px;
                background: white;
                padding: 10px;
            }
        """)

        layout = QVBoxLayout(self)

        # First row: JOIN type and table
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

        # Table selection
        self.join_table_combo = QComboBox()
        self.join_table_combo.addItems(self.tables)
        self.join_table_combo.setMinimumWidth(150)
        self.join_table_combo.setMaximumHeight(22)
        self.join_table_combo.setStyleSheet("""
            QComboBox {
                font-size: 10px;
                padding: 2px 4px;
            }
        """)
        self.join_table_combo.currentTextChanged.connect(self._on_join_table_changed)
        top_layout.addWidget(self.join_table_combo)

        top_layout.addStretch()

        # Remove button
        remove_btn = QPushButton("×")
        remove_btn.setFixedSize(30, 30)
        remove_btn.setStyleSheet("""
            QPushButton {
                background: #e74c3c;
                color: white;
                border: none;
                border-radius: 3px;
                font-size: 14px;
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
        
        # Left table name label
        left_table_label = QLabel("")
        left_table_label.setStyleSheet("color: #7f8c8d; font-size: 9px; font-style: italic;")
        left_table_label.setMinimumWidth(80)
        row_layout.addWidget(left_table_label)
        
        # Left field dropdown (FROM table fields)
        left_field_combo = QComboBox()
        left_field_combo.setMinimumWidth(180)
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
        
        # Right table name label
        right_table_label = QLabel("")
        right_table_label.setStyleSheet("color: #7f8c8d; font-size: 9px; font-style: italic;")
        right_table_label.setMinimumWidth(80)
        row_layout.addWidget(right_table_label)

        # Right field dropdown (JOIN table fields)
        right_field_combo = QComboBox()
        right_field_combo.setMinimumWidth(180)
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
        
        # Store references
        row_data = {
            'widget': row_widget,
            'left_table_label': left_table_label,
            'left_field_combo': left_field_combo,
            'right_table_label': right_table_label,
            'right_field_combo': right_field_combo
        }
        self.on_condition_rows.append(row_data)
        
        # Add to layout
        self.on_conditions_layout.addWidget(row_widget)
        
        # Update labels and populate fields for the new row
        self._update_on_condition_labels()
        
        # Populate the field combos for the new row
        if self.from_table and self.join_table:
            # Populate left field combo (FROM table)
            fields = self._get_table_fields(self.from_table)
            left_field_combo.addItems(fields)
            
            # Populate right field combo (JOIN table)
            fields = self._get_table_fields(self.join_table)
            right_field_combo.addItems(fields)

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

    def _update_on_condition_labels(self):
        """Update table name labels for all ON condition rows"""
        from_table = self.from_table or ""
        join_table = self.join_table or ""
        
        for row_data in self.on_condition_rows:
            if from_table:
                row_data['left_table_label'].setText(f"({from_table})")
            if join_table:
                row_data['right_table_label'].setText(f"({join_table})")

    def _on_join_table_changed(self, table_name):
        """Handle join table selection change"""
        self.join_table = table_name
        self._load_field_lists()

    def _load_field_lists(self):
        """Load fields for FROM and JOIN tables"""
        if not self.parent_screen:
            return
        
        # Get FROM table from parent
        from_table = self.parent_screen.from_table_combo.currentText()
        join_table = self.join_table_combo.currentText()
        
        self.from_table = from_table
        self.join_table = join_table
        
        # Update table labels
        self._update_on_condition_labels()
        
        # Load fields for all ON condition rows
        for row_data in self.on_condition_rows:
            # Load FROM table fields (left side)
            row_data['left_field_combo'].clear()
            if from_table:
                fields = self._get_table_fields(from_table)
                row_data['left_field_combo'].addItems(fields)
            
            # Load JOIN table fields (right side)
            row_data['right_field_combo'].clear()
            if join_table:
                fields = self._get_table_fields(join_table)
                row_data['right_field_combo'].addItems(fields)

    def _get_table_fields(self, table_name):
        """Get list of fields for a table"""
        if not self.parent_screen or not hasattr(self.parent_screen, 'schema_discovery'):
            return []
        
        try:
            connection_id = self.parent_screen.current_connection_id
            schema_name = self.parent_screen.current_schema_name or ''
            
            columns = self.parent_screen.schema_discovery.get_columns(
                connection_id, table_name, schema_name
            )
            return [col['column_name'] for col in columns]
        except Exception as e:
            logger.error(f"Error loading fields for {table_name}: {e}")
            return []

    def get_join_config(self):
        """Get JOIN configuration as dict"""
        on_conditions = []
        for row_data in self.on_condition_rows:
            left_field = row_data['left_field_combo'].currentText()
            right_field = row_data['right_field_combo'].currentText()
            if left_field and right_field:
                on_conditions.append({
                    'left_field': left_field,
                    'right_field': right_field
                })
        
        return {
            'join_type': self.join_type_combo.currentText(),
            'join_table': self.join_table_combo.currentText(),
            'on_conditions': on_conditions
        }


class DraggableFieldsTree(QTreeWidget):
    """Tree widget with custom drag behavior for fields"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setDragEnabled(True)
        self.setDragDropMode(QTreeWidget.DragDropMode.DragOnly)

    def startDrag(self, supportedActions):
        """Start drag operation with field data"""
        item = self.currentItem()
        if not item:
            logger.warning("No item selected for drag")
            return

        item_type = item.data(0, Qt.ItemDataRole.UserRole)
        
        # If trying to drag a unique value child, get the parent field instead
        if item_type == "unique_value" or item_type is None:
            parent = item.parent()
            if parent and parent.data(0, Qt.ItemDataRole.UserRole) == "field":
                item = parent
                item_type = "field"
            else:
                logger.warning(f"Cannot drag item of type: {item_type}")
                return
        
        if item_type != "field":
            logger.warning(f"Skipping drag for item type: {item_type}")
            return

        # Get field data
        field_name = item.data(0, Qt.ItemDataRole.UserRole + 1)
        data_type = item.data(0, Qt.ItemDataRole.UserRole + 2)
        table_name = item.data(0, Qt.ItemDataRole.UserRole + 3)
        schema_name = item.data(0, Qt.ItemDataRole.UserRole + 4)
        
        # Validate we have the required data
        if not field_name or not table_name:
            logger.error(f"Invalid field data: field_name={field_name}, table_name={table_name}")
            return

        # Create field data dict
        import json
        field_data = {
            'field_name': field_name,
            'data_type': data_type,
            'table_name': table_name,
            'schema_name': schema_name
        }
        
        logger.info(f"Starting drag for field: {table_name}.{field_name}")

        # Create drag
        drag = QDrag(self)
        mime_data = QMimeData()
        mime_data.setText(json.dumps(field_data))
        drag.setMimeData(mime_data)

        # Execute drag
        drag.exec(Qt.DropAction.CopyAction)
