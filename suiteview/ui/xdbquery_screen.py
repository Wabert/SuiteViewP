"""XDB Query Screen - Cross-database query builder"""

import logging
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QSplitter,
    QTreeWidget, QTreeWidgetItem, QPushButton, QFrame, QMenu,
    QScrollArea, QComboBox, QMessageBox, QFileDialog, QTabWidget,
    QLineEdit, QCheckBox, QDateEdit, QToolButton, QSizePolicy, QInputDialog,
    QTextEdit, QLayout, QWidgetItem
)
from PyQt6.QtCore import Qt, QDate, pyqtSignal, QMimeData, QRect, QPoint, QSize
from PyQt6.QtGui import QAction, QDrag


class FlowLayout(QLayout):
    """Custom flow layout that arranges widgets in rows with wrapping (grid-like)"""
    
    def __init__(self, parent=None, margin=0, spacing=-1):
        super().__init__(parent)
        
        if parent is not None:
            self.setContentsMargins(margin, margin, margin, margin)
        
        self.setSpacing(spacing)
        self._item_list = []
        
    def __del__(self):
        item = self.takeAt(0)
        while item:
            item = self.takeAt(0)
    
    def addItem(self, item):
        self._item_list.append(item)
    
    def count(self):
        return len(self._item_list)
    
    def itemAt(self, index):
        if 0 <= index < len(self._item_list):
            return self._item_list[index]
        return None
    
    def takeAt(self, index):
        if 0 <= index < len(self._item_list):
            return self._item_list.pop(index)
        return None
    
    def insertWidget(self, index, widget):
        """Insert widget at specific index"""
        item = QWidgetItem(widget)
        if 0 <= index <= len(self._item_list):
            self._item_list.insert(index, item)
        else:
            self._item_list.append(item)
        self.invalidate()
    
    def expandingDirections(self):
        return Qt.Orientation(0)
    
    def hasHeightForWidth(self):
        return True
    
    def heightForWidth(self, width):
        height = self._do_layout(QRect(0, 0, width, 0), True)
        return height
    
    def setGeometry(self, rect):
        super().setGeometry(rect)
        self._do_layout(rect, False)
    
    def sizeHint(self):
        return self.minimumSize()
    
    def minimumSize(self):
        size = QSize()
        
        for item in self._item_list:
            size = size.expandedTo(item.minimumSize())
        
        margins = self.contentsMargins()
        size += QSize(margins.left() + margins.right(), margins.top() + margins.bottom())
        return size
    
    def _do_layout(self, rect, test_only):
        x = rect.x()
        y = rect.y()
        line_height = 0
        spacing = self.spacing()
        
        for item in self._item_list:
            widget = item.widget()
            space_x = spacing
            space_y = spacing
            
            next_x = x + item.sizeHint().width() + space_x
            if next_x - space_x > rect.right() and line_height > 0:
                x = rect.x()
                y = y + line_height + space_y
                next_x = x + item.sizeHint().width() + space_x
                line_height = 0
            
            if not test_only:
                item.setGeometry(QRect(QPoint(x, y), item.sizeHint()))
            
            x = next_x
            line_height = max(line_height, item.sizeHint().height())
        
        return y + line_height - rect.y()
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
        self.display_widgets = []  # List of XDBDisplayFieldWidget instances for drag-drop
        self.criteria_widgets = []  # List of CriteriaFilterWidget instances
        # Track selected tables for XDB query building
        self.selected_tables = {}  # Dict: {connection_id: [table_names]}
        # Track current table for field highlighting
        self.current_table_name = None
        self.current_schema_name = None
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

        # Query Statement tab (FOURTH - shows executed SQL)
        self.query_statement_tab = self._create_query_statement_tab()
        self.xdb_tabs.addTab(self.query_statement_tab, "Query Statement")

        # Connect tab change to update field indicators
        self.xdb_tabs.currentChanged.connect(self._on_tab_changed)

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
        self.display_layout = FlowLayout(self.display_container, margin=10, spacing=10)

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
        self.criteria_layout = FlowLayout(self.criteria_container, margin=5, spacing=5)

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

        # Scroll area for joins - make it expand to fill available space
        join_scroll = QScrollArea()
        join_scroll.setWidgetResizable(True)
        join_scroll.setMinimumHeight(200)  # Minimum height so joins aren't cut off
        join_scroll.setStyleSheet("QScrollArea { border: 1px solid #ddd; background: #f9f9f9; border-radius: 4px; }")

        self.joins_container = QWidget()
        self.joins_layout = QVBoxLayout(self.joins_container)
        self.joins_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        self.joins_layout.setSpacing(10)
        self.joins_layout.setContentsMargins(5, 5, 5, 5)

        join_scroll.setWidget(self.joins_container)
        # Use stretch factor of 1 to let scroll area expand
        layout.addWidget(join_scroll, 1)

        return tab

    def _create_query_statement_tab(self) -> QWidget:
        """Create Query Statement tab to show executed SQL statements"""
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setContentsMargins(10, 10, 10, 10)

        # Header
        header = QLabel("SQL Statements Executed")
        header.setStyleSheet("font-weight: bold; font-size: 12px; padding: 5px;")
        layout.addWidget(header)

        # Text area to show the SQL
        self.query_statement_text = QTextEdit()
        self.query_statement_text.setReadOnly(True)
        self.query_statement_text.setStyleSheet("""
            QTextEdit {
                font-family: 'Consolas', 'Courier New', monospace;
                font-size: 11px;
                background: #f8f9fa;
                border: 1px solid #ddd;
                border-radius: 4px;
                padding: 10px;
            }
        """)
        self.query_statement_text.setPlaceholderText("SQL statements will appear here after running a query...")
        layout.addWidget(self.query_statement_text)

        # Copy button
        copy_layout = QHBoxLayout()
        copy_layout.addStretch()
        copy_btn = QPushButton("📋 Copy to Clipboard")
        copy_btn.clicked.connect(self._copy_query_statement)
        copy_layout.addWidget(copy_btn)
        layout.addLayout(copy_layout)

        return tab

    def _copy_query_statement(self):
        """Copy query statement to clipboard"""
        from PyQt6.QtWidgets import QApplication
        clipboard = QApplication.clipboard()
        clipboard.setText(self.query_statement_text.toPlainText())
        
        # Show brief feedback
        QMessageBox.information(self, "Copied", "Query statement copied to clipboard!")

    def _update_query_statement(self, statements: str):
        """Update the Query Statement tab with executed SQL"""
        self.query_statement_text.setPlainText(statements)

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
                    
                    # Also add to the tables tree panel
                    table_dict = {'table_name': ds_data['table_name'], 'schema_name': ds_data.get('schema_name')}
                    self._add_table_to_list(connection, table_dict)
            
            # Update datasources label and FROM combo
            self._update_datasources_label()
            
            # Set FROM datasource
            from_datasource = query_dict.get('from_datasource')
            if from_datasource:
                index = self.from_datasource_combo.findText(from_datasource)
                if index >= 0:
                    self.from_datasource_combo.setCurrentIndex(index)
            
            # Helper to find connection for a datasource alias
            def get_connection_for_alias(alias):
                for ds in self.datasources:
                    if ds['alias'] == alias:
                        return ds.get('connection')
                return None
            
            # Load display fields
            for field_data in query_dict.get('display_fields', []):
                # Add connection from matching datasource
                ds_alias = field_data.get('datasource_alias')
                if ds_alias and 'connection' not in field_data:
                    conn = get_connection_for_alias(ds_alias)
                    if conn:
                        field_data['connection'] = conn
                
                # Add to tracking
                self.display_fields.append(field_data)
                
                # Create widget
                display_widget = XDBDisplayFieldWidget(field_data, self)
                display_widget.remove_requested.connect(lambda w=display_widget: self.remove_display_field(w))
                self.display_layout.addWidget(display_widget)
                self.display_widgets.append(display_widget)  # Track widget for drag-drop
            
            # Load criteria filters
            for criterion in query_dict.get('criteria', []):
                # Reconstruct field_data with connection
                ds_alias = criterion.get('datasource_alias')
                conn = get_connection_for_alias(ds_alias) if ds_alias else None
                
                field_data = {
                    'field_name': criterion.get('field_name'),
                    'data_type': criterion.get('data_type'),
                    'table_name': criterion.get('table_name'),
                    'schema_name': criterion.get('schema_name'),
                    'datasource_alias': ds_alias,
                    'connection': conn
                }
                
                # Create filter widget
                filter_widget = XDBCriteriaFilterWidget(field_data, self)
                filter_widget.remove_requested.connect(lambda w=filter_widget: self.remove_criteria_filter(w))
                self.criteria_layout.addWidget(filter_widget)
                self.criteria_widgets.append(filter_widget)
                
                # Restore filter values using dedicated restore method
                match_type = criterion.get('match_type', '')
                operator = criterion.get('operator', '=')
                value = criterion.get('value', '')
                
                # Use the restore_filter_state method which handles List mode properly
                filter_widget.restore_filter_state(match_type, value, operator)
            
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
            
            # Set right datasource - match by connection_id + table_name for robustness
            right_ds = join_config.get('right_datasource')
            if right_ds:
                # Try matching by connection_id + table_name first (more reliable)
                right_conn_id = right_ds.get('connection_id') or (right_ds.get('connection', {}).get('connection_id'))
                right_table = right_ds.get('table_name')
                
                matched = False
                for i in range(join_widget.right_datasource_combo.count()):
                    ds = join_widget.right_datasource_combo.itemData(i)
                    if ds:
                        ds_conn_id = ds['connection']['connection_id']
                        ds_table = ds['table_name']
                        if right_conn_id and right_table and ds_conn_id == right_conn_id and ds_table == right_table:
                            join_widget.right_datasource_combo.setCurrentIndex(i)
                            matched = True
                            break
                
                # Fallback to alias matching
                if not matched and right_ds.get('alias'):
                    for i in range(join_widget.right_datasource_combo.count()):
                        ds = join_widget.right_datasource_combo.itemData(i)
                        if ds and ds['alias'] == right_ds['alias']:
                            join_widget.right_datasource_combo.setCurrentIndex(i)
                            break
            
            # Restore ON conditions
            on_conditions = join_config.get('on_conditions', [])
            
            # First condition already exists, restore it
            if len(on_conditions) > 0 and len(join_widget.on_condition_rows) > 0:
                self._restore_on_condition(join_widget.on_condition_rows[0], on_conditions[0], join_widget)
            
            # Add additional conditions
            for i in range(1, len(on_conditions)):
                join_widget._add_on_condition_row()
                if i < len(join_widget.on_condition_rows):
                    self._restore_on_condition(join_widget.on_condition_rows[i], on_conditions[i], join_widget)
            
        except Exception as e:
            logger.error(f"Error restoring join config: {e}", exc_info=True)
    
    def _restore_on_condition(self, row_data: dict, condition: dict, join_widget: 'XDBJoinWidget'):
        """Restore a single ON condition row"""
        try:
            # Helper to find datasource by connection_id + table_name or alias
            def find_datasource_index(combo, conn_id, table_name, alias):
                # First try connection_id + table_name (more reliable)
                if conn_id and table_name:
                    for i in range(combo.count()):
                        ds = combo.itemData(i)
                        if ds:
                            ds_conn_id = ds['connection']['connection_id']
                            ds_table = ds['table_name']
                            if ds_conn_id == conn_id and ds_table == table_name:
                                return i
                
                # Fallback to alias matching
                if alias:
                    for i in range(combo.count()):
                        ds = combo.itemData(i)
                        if ds and ds['alias'] == alias:
                            return i
                
                return -1
            
            # Set left datasource and trigger field loading
            left_conn_id = condition.get('left_connection_id')
            left_table = condition.get('left_table_name')
            left_alias = condition.get('left_datasource')
            
            left_idx = find_datasource_index(
                row_data['left_datasource_combo'],
                left_conn_id, left_table, left_alias
            )
            if left_idx >= 0:
                row_data['left_datasource_combo'].setCurrentIndex(left_idx)
                # Manually trigger field loading
                join_widget._update_left_fields(
                    row_data['left_datasource_combo'],
                    row_data['left_field_combo']
                )
            
            # Set left field (after fields are loaded)
            left_field = condition.get('left_field')
            if left_field:
                index = row_data['left_field_combo'].findText(left_field)
                if index >= 0:
                    row_data['left_field_combo'].setCurrentIndex(index)
            
            # Set right datasource and trigger field loading
            right_conn_id = condition.get('right_connection_id')
            right_table = condition.get('right_table_name')
            right_alias = condition.get('right_datasource')
            
            right_idx = find_datasource_index(
                row_data['right_datasource_combo'],
                right_conn_id, right_table, right_alias
            )
            if right_idx >= 0:
                row_data['right_datasource_combo'].setCurrentIndex(right_idx)
                # Manually trigger field loading
                join_widget._update_right_fields(
                    row_data['right_datasource_combo'],
                    row_data['right_field_combo']
                )
            
            # Set right field (after fields are loaded)
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
        self.display_widgets.clear()  # Clear widget tracking
        
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
        
        # Clear tables tree
        self.tables_tree.clear()
        self._update_tables_count()
        
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
        
        # Track current table for field highlighting
        self.current_table_name = table_name
        self.current_schema_name = schema_name
        
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
            
            # Update field indicators based on current tab
            self._update_field_indicators()
            
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

    def _on_tab_changed(self, index: int):
        """Handle tab change to update field indicators"""
        self._update_field_indicators()

    def _update_field_indicators(self):
        """Update green dot indicators next to fields based on current tab"""
        # Get current tab index (0=Display, 1=Criteria, 2=Datasources)
        current_tab = self.xdb_tabs.currentIndex()
        
        # Determine which fields to highlight based on current table
        if current_tab == 0:  # Display tab
            fields_in_use = {
                (f['field_name'], f['table_name']) 
                for f in self.display_fields
                if f.get('table_name') == self.current_table_name
            }
        elif current_tab == 1:  # Criteria tab
            fields_in_use = {
                (w.field_data['field_name'], w.field_data['table_name']) 
                for w in self.criteria_widgets
                if w.field_data.get('table_name') == self.current_table_name
            }
        else:  # Datasources tab or other
            fields_in_use = set()
        
        # Update indicators for all fields in the fields tree
        for i in range(self.fields_tree.topLevelItemCount()):
            item = self.fields_tree.topLevelItem(i)
            field_name = item.data(0, Qt.ItemDataRole.UserRole + 1)
            field_type = item.data(0, Qt.ItemDataRole.UserRole + 2)
            table_name = item.data(0, Qt.ItemDataRole.UserRole + 3)
            
            # Base display name (without indicator)
            base_name = f"{field_name} ({field_type})"
            
            # Check if this field is in use for the current tab
            if (field_name, table_name) in fields_in_use:
                # Add green dot indicator
                item.setText(0, f"🟢 {base_name}")
                # Make it bold
                font = item.font(0)
                font.setBold(True)
                item.setFont(0, font)
            else:
                # No indicator
                item.setText(0, base_name)
                # Regular font
                font = item.font(0)
                font.setBold(False)
                item.setFont(0, font)

    def add_display_field(self, field_data: dict):
        """Add a field to display tab"""
        # Create display field widget
        display_widget = XDBDisplayFieldWidget(field_data, self)
        display_widget.remove_requested.connect(lambda w=display_widget: self.remove_display_field(w))

        # Add to the end (bottom) of the layout
        self.display_layout.addWidget(display_widget)
        self.display_fields.append(field_data)
        self.display_widgets.append(display_widget)  # Track widget for drag-drop
        
        # Update datasources tab (automatically adds datasource if needed)
        self._update_datasources_from_fields()
        
        # Update field indicators
        self._update_field_indicators()

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

            # Remove from widget tracking
            if widget in self.display_widgets:
                self.display_widgets.remove(widget)

            # Remove widget
            self.display_layout.removeWidget(widget)
            widget.deleteLater()
            
            # Update datasources tab (removes datasources no longer in use)
            self._update_datasources_from_fields()
            
            # Update field indicators
            self._update_field_indicators()
            
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
        
        # Update field indicators
        self._update_field_indicators()

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
            
            # Update field indicators
            self._update_field_indicators()
            
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
            if 'datasource_alias' in field_data and 'connection' in field_data:
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
            if 'datasource_alias' in field_data and 'connection' in field_data:
                alias = field_data['datasource_alias']
                if alias not in datasources_in_use:
                    datasources_in_use[alias] = {
                        'alias': alias,
                        'connection': field_data['connection'],
                        'table_name': field_data['table_name'],
                        'schema_name': field_data.get('schema_name')
                    }
        
        # Only update if we have valid datasources with connections
        # (Don't clobber existing datasources if fields lack connection info)
        if datasources_in_use:
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
        # Use combination of connection name + table name for clarity in cross-DB queries
        import re
        
        # Sanitize connection name
        conn_part = connection['connection_name']
        conn_part = re.sub(r'[^a-zA-Z0-9]', '_', conn_part)
        conn_part = re.sub(r'_+', '_', conn_part).strip('_')
        
        # Sanitize table name
        table_part = table_name
        table_part = re.sub(r'[^a-zA-Z0-9]', '_', table_part)
        table_part = re.sub(r'_+', '_', table_part).strip('_')
        
        # Combine: ConnectionName__TableName (double underscore separator)
        # e.g., VRD_Prod_SQL__CENSUS_ADV, UL_Rates__TAICession
        base_alias = f"{conn_part}__{table_part}" if conn_part and table_part else (conn_part or table_part or 'datasource')
        
        # Ensure it doesn't start with a number
        if base_alias and base_alias[0].isdigit():
            base_alias = 'ds_' + base_alias
        
        # If alias already exists (unlikely but possible), append number
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
        
        # Update all existing join widgets with new datasource list
        self._update_join_widgets_datasources()
    
    def _update_join_widgets_datasources(self):
        """Update all join widgets when datasources change"""
        for i in range(self.joins_layout.count()):
            item = self.joins_layout.itemAt(i)
            if item and item.widget():
                join_widget = item.widget()
                if hasattr(join_widget, 'update_datasources'):
                    join_widget.update_datasources(self.datasources)
    
    def _preview_query(self):
        """Execute cross-query with LIMIT 1000 for preview"""
        self._execute_xdb_query(limit=1000)
    
    def _run_query(self):
        """Execute full cross-query"""
        self._execute_xdb_query(limit=None)
    
    def _execute_xdb_query(self, limit: Optional[int]):
        """Build and execute the XDB query using the hybrid engine"""
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
                # Only include filters with values AND valid operators (not None)
                if (filter_condition and 
                    filter_condition.get('value') and 
                    filter_condition.get('operator') is not None):
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
            
            # Build list of all source configs
            source_configs = []
            for ds in self.datasources:
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
            
            # Extract join configs from Joins tab
            join_configs = []
            for i in range(self.joins_layout.count()):
                join_widget = self.joins_layout.itemAt(i).widget()
                if join_widget and hasattr(join_widget, 'get_join_config'):
                    join_config = join_widget.get_join_config()
                    if join_config and join_config.get('on_conditions'):
                        join_configs.append(join_config)
            
            # Validate joins if multiple datasources
            if len(source_configs) > 1 and not join_configs:
                QMessageBox.warning(
                    self, 
                    "Missing Joins", 
                    "You have multiple datasources but no joins defined.\n\n"
                    "Please add at least one join in the Datasources tab to connect your tables."
                )
                return
            
            logger.info(f"Executing XDB query with {len(source_configs)} datasource(s)")
            logger.info(f"Join configs: {join_configs}")
            
            # Show progress
            from PyQt6.QtWidgets import QApplication
            QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
            
            try:
                # Execute using XDB executor
                result_df = self.xdb_executor.execute_query(source_configs, join_configs, limit)
                
                # Get execution plan summary if available
                plan_summary = ""
                if hasattr(self.xdb_executor, 'get_execution_plan_summary'):
                    plan_summary = self.xdb_executor.get_execution_plan_summary()
                
                # Update Query Statement tab with formatted SQL
                if hasattr(self.xdb_executor, 'get_formatted_sql'):
                    formatted_sql = self.xdb_executor.get_formatted_sql()
                    self.query_statement_text.setPlainText(formatted_sql)
                    # Switch to Query Statement tab to show the SQL
                    for i in range(self.xdb_tabs.count()):
                        if self.xdb_tabs.tabText(i) == "Query Statement":
                            self.xdb_tabs.setCurrentIndex(i)
                            break
                
                # Show results with plan info
                self._show_results(result_df, limit, plan_summary)
                
            finally:
                QApplication.restoreOverrideCursor()
            
        except Exception as e:
            logger.error(f"XDB query failed: {e}", exc_info=True)
            
            # Still try to show any SQL that was captured before the error
            if hasattr(self, 'xdb_executor') and hasattr(self.xdb_executor, 'get_formatted_sql'):
                try:
                    formatted_sql = self.xdb_executor.get_formatted_sql()
                    error_msg = f"ERROR: {str(e)}\n\n{'='*70}\n\n{formatted_sql}"
                    self.query_statement_text.setPlainText(error_msg)
                    # Switch to Query Statement tab to show the SQL with error
                    for i in range(self.xdb_tabs.count()):
                        if self.xdb_tabs.tabText(i) == "Query Statement":
                            self.xdb_tabs.setCurrentIndex(i)
                            break
                except Exception:
                    pass
            
            QMessageBox.critical(self, "Query Error", f"Failed to execute cross-database query:\n\n{str(e)}")
    
    def _show_results(self, df, limit: Optional[int], plan_summary: str = ""):
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
        
        # Build query text with execution plan
        query_text = "Cross-Database Query"
        if plan_summary:
            query_text = plan_summary
        
        # QueryResultsDialog expects (df, sql, execution_time_ms)
        # For XDB queries, we pass the plan summary as the SQL text
        execution_time_ms = 0  # Could extract from plan if available
        dialog = QueryResultsDialog(df, query_text, execution_time_ms, parent=self)
        dialog.setWindowTitle(title)
        dialog.show()  # Modeless - allows interaction with main app
    
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
        self.setAcceptDrops(True)  # Enable drop
        self.init_ui()

    def init_ui(self):
        """Initialize UI"""
        self.setFrameStyle(QFrame.Shape.Box)
        
        # Store default background for toggling
        self.default_bg = "white"
        self.aggregated_bg = "#FFE5CC"  # Light orange
        
        self.setStyleSheet(f"""
            XDBDisplayFieldWidget {{
                border: 2px solid #27ae60;
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
                    border: 2px solid #27ae60;
                    border-radius: 4px;
                    background: {self.aggregated_bg};
                    padding: 0px;
                }}
            """)
        else:
            # Restore white background
            self.setStyleSheet(f"""
                XDBDisplayFieldWidget {{
                    border: 2px solid #27ae60;
                    border-radius: 4px;
                    background: {self.default_bg};
                    padding: 0px;
                }}
            """)
    
    def mousePressEvent(self, event):
        """Handle mouse press for drag start"""
        if event.button() == Qt.MouseButton.LeftButton:
            self.drag_start_position = event.pos()
        super().mousePressEvent(event)
    
    def mouseMoveEvent(self, event):
        """Handle mouse move to initiate drag"""
        if not (event.buttons() & Qt.MouseButton.LeftButton):
            return
        if not hasattr(self, 'drag_start_position'):
            return
        if (event.pos() - self.drag_start_position).manhattanLength() < 10:
            return
        
        # Find the XDBQueryScreen parent
        parent = self.parent()
        while parent and not hasattr(parent, 'display_widgets'):
            parent = parent.parent()
        
        if not parent:
            return
        
        # Create drag object
        drag = QDrag(self)
        mime_data = QMimeData()
        
        # Store the index of this widget
        try:
            index = parent.display_widgets.index(self)
            mime_data.setText(f"display_widget:{index}")
            drag.setMimeData(mime_data)
            drag.exec(Qt.DropAction.MoveAction)
        except ValueError:
            pass
    
    def dragEnterEvent(self, event):
        """Handle drag enter"""
        if event.mimeData().hasText():
            text = event.mimeData().text()
            if text.startswith("display_widget:"):
                event.acceptProposedAction()
                self.setStyleSheet(f"""
                    XDBDisplayFieldWidget {{
                        border: 2px solid #3498db;
                        border-radius: 4px;
                        background: #e8f4fc;
                        padding: 0px;
                    }}
                """)
    
    def dragLeaveEvent(self, event):
        """Handle drag leave"""
        # Restore normal styling
        agg = self.agg_combo.currentText() if hasattr(self, 'agg_combo') else "None"
        bg = self.aggregated_bg if agg != "None" else self.default_bg
        self.setStyleSheet(f"""
            XDBDisplayFieldWidget {{
                border: 2px solid #27ae60;
                border-radius: 4px;
                background: {bg};
                padding: 0px;
            }}
        """)
    
    def dropEvent(self, event):
        """Handle drop to reorder widgets"""
        text = event.mimeData().text()
        if not text.startswith("display_widget:"):
            return
        
        source_index = int(text.split(":")[1])
        
        # Find parent with display_widgets
        parent = self.parent()
        while parent and not hasattr(parent, 'display_widgets'):
            parent = parent.parent()
        
        if not parent:
            return
        
        try:
            target_index = parent.display_widgets.index(self)
        except ValueError:
            return
        
        if source_index == target_index:
            # Restore styling
            self.dragLeaveEvent(event)
            return
        
        # Reorder in the list
        widget = parent.display_widgets.pop(source_index)
        parent.display_widgets.insert(target_index, widget)
        
        # Reorder in the layout
        layout = parent.display_layout
        layout.takeAt(source_index)
        layout.insertWidget(target_index, widget)
        
        # Restore styling
        self.dragLeaveEvent(event)
        event.acceptProposedAction()


class XDBCriteriaFilterWidget(QFrame):
    """Widget for a single filter criterion in XDB queries - matches DB Query style"""

    remove_requested = pyqtSignal()

    def __init__(self, field_data: dict, parent=None):
        super().__init__(parent)
        self.field_data = field_data
        self.parent_screen = parent
        self.unique_values = None
        self.selected_values = []
        self.setAcceptDrops(True)  # Enable drop
        # Enable right-click context menu on the whole widget
        self.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.customContextMenuRequested.connect(self._show_field_context_menu)
        self.init_ui()
        # Try to load cached unique values after UI is built
        self._load_cached_unique_values()

    def _load_cached_unique_values(self):
        """Try to load cached unique values for this field from My Data"""
        try:
            # Find the parent screen to get connection info
            parent = self.parent_screen
            if not parent:
                parent = self.parent()
                while parent and not hasattr(parent, 'datasources'):
                    parent = parent.parent()
            
            if not parent:
                return
            
            # Find the datasource for this field
            datasource_alias = self.field_data.get('datasource_alias', '')
            table_name = self.field_data['table_name']
            field_name = self.field_data['field_name']
            
            # Find matching datasource
            datasource = None
            for ds in parent.datasources:
                if ds.get('alias') == datasource_alias or ds.get('table_name') == table_name:
                    datasource = ds
                    break
            
            if not datasource:
                return
            
            connection = datasource.get('connection')
            if not connection:
                return
            
            connection_id = connection.get('connection_id')
            schema_name = datasource.get('schema_name', '')
            
            # Try to load from metadata cache
            from suiteview.data.repositories import MetadataCacheRepository
            metadata_repo = MetadataCacheRepository()
            
            metadata_id = metadata_repo.get_or_create_metadata(
                connection_id,
                table_name,
                schema_name or ''
            )
            
            cached_unique = metadata_repo.get_cached_unique_values(
                metadata_id,
                field_name
            )
            
            if cached_unique and cached_unique.get('unique_values'):
                self.unique_values = cached_unique['unique_values']
                self.selected_values = self.unique_values[:]  # Select all by default
                
                # Show and update the list button
                if hasattr(self, 'list_button') and self.list_button:
                    self.list_button.setVisible(True)
                    self._update_list_button_style()
                    logger.info(f"Loaded {len(self.unique_values)} cached unique values for {field_name}")
                    
        except Exception as e:
            logger.debug(f"Could not load cached unique values: {e}")

    def init_ui(self):
        """Initialize UI - compact card style matching DB Query"""
        self.setFrameStyle(QFrame.Shape.Box)
        self.setStyleSheet("""
            XDBCriteriaFilterWidget {
                border: 2px solid #e67e22;
                border-radius: 6px;
                background: white;
            }
        """)
        
        # Fixed width for tile layout - match DisplayFieldWidget width
        self.setFixedWidth(200)
        self.setMinimumHeight(100)
        self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)

        main_layout = QVBoxLayout(self)
        main_layout.setSpacing(2)
        main_layout.setContentsMargins(4, 4, 4, 4)

        # Header row: Field name and remove button
        header_layout = QHBoxLayout()
        header_layout.setSpacing(4)
        header_layout.setContentsMargins(0, 0, 0, 0)
        
        # Field name (bold, prominent) with right-click support
        self.field_label = QLabel(self.field_data['field_name'])
        self.field_label.setStyleSheet("font-weight: bold; font-size: 11px; color: #2c3e50; background: transparent;")
        self.field_label.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.field_label.customContextMenuRequested.connect(self._show_field_context_menu)
        header_layout.addWidget(self.field_label)
        
        header_layout.addStretch()

        # Remove button with X (subtle)
        remove_btn = QPushButton("×")
        remove_btn.setFixedSize(14, 14)
        remove_btn.setToolTip("Remove this filter")
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
        header_layout.addWidget(remove_btn)
        
        main_layout.addLayout(header_layout)
        
        # Table name and type row (compact info)
        info_layout = QHBoxLayout()
        info_layout.setSpacing(6)
        info_layout.setContentsMargins(0, 0, 0, 0)
        
        # Table name in "Datasource.TableName" format
        datasource_alias = self.field_data.get('datasource_alias', '')
        table_name = self.field_data['table_name']
        if datasource_alias:
            display_table = f"📋 {datasource_alias}.{table_name}"
        else:
            display_table = f"📋 {table_name}"
        
        table_label = QLabel(display_table)
        table_label.setStyleSheet("color: #7f8c8d; font-size: 9px; background: transparent;")
        info_layout.addWidget(table_label)
        
        type_label = QLabel(f"({self.field_data['data_type']})")
        type_label.setStyleSheet("color: #95a5a6; font-size: 9px; background: transparent;")
        info_layout.addWidget(type_label)
        
        info_layout.addStretch()
        main_layout.addLayout(info_layout)
        
        # Separator line
        separator = QFrame()
        separator.setFrameShape(QFrame.Shape.HLine)
        separator.setStyleSheet("background-color: #ecf0f1; max-height: 1px;")
        main_layout.addWidget(separator)

        # Filter controls container
        self.controls_container = QWidget()
        self.controls_container.setStyleSheet("background: transparent;")
        self.controls_layout = QVBoxLayout(self.controls_container)
        self.controls_layout.setContentsMargins(0, 2, 0, 0)
        self.controls_layout.setSpacing(3)
        main_layout.addWidget(self.controls_container)

        # Add filter controls
        self._add_filter_controls()

    def _add_filter_controls(self):
        """Add type-specific filter controls"""
        data_type = self.field_data['data_type'].upper()

        # Determine field type
        is_string = any(t in data_type for t in ['CHAR', 'VARCHAR', 'TEXT', 'STRING'])
        is_numeric = any(t in data_type for t in ['INT', 'DECIMAL', 'NUMERIC', 'FLOAT', 'DOUBLE', 'REAL', 'NUMBER'])
        is_date = any(t in data_type for t in ['DATE', 'TIME', 'TIMESTAMP'])

        if is_string:
            self._add_string_filter()
        elif is_numeric:
            self._add_numeric_filter()
        elif is_date:
            self._add_date_filter()
        else:
            self._add_string_filter()  # Default to string-like filter

    def _add_string_filter(self):
        """Add string filter controls"""
        # First row: Match type dropdown with list button
        combo_row = QHBoxLayout()
        combo_row.setSpacing(4)
        combo_row.setContentsMargins(0, 0, 0, 0)
        
        # Match type dropdown
        self.match_type_combo = QComboBox()
        self.match_type_combo.addItems(["None", "Exact", "Starts", "Ends", "Contains", "Expression"])
        self.match_type_combo.setCurrentText("Exact")
        self.match_type_combo.setMinimumWidth(80)
        self.match_type_combo.setMaximumWidth(90)
        self.match_type_combo.setMaximumHeight(22)
        self.match_type_combo.setStyleSheet("""
            QComboBox {
                font-size: 10px;
                padding: 2px 4px;
                background: white;
            }
        """)
        combo_row.addWidget(self.match_type_combo)
        
        # List button (hidden until unique values are loaded)
        self.list_button = QPushButton("☰")
        self.list_button.setFixedSize(20, 20)
        self.list_button.setToolTip("Select Values (right-click field name to fetch)")
        self.list_button.setVisible(False)  # Hidden until values are loaded
        self.list_button.setStyleSheet("""
            QPushButton {
                background: white;
                color: #e67e22;
                border: 2px solid #e67e22;
                border-radius: 3px;
                font-size: 11px;
                font-weight: bold;
            }
            QPushButton:hover {
                background: #fef5e7;
            }
        """)
        self.list_button.clicked.connect(self._open_value_selection_popup)
        combo_row.addWidget(self.list_button)
        
        combo_row.addStretch()
        
        combo_widget = QWidget()
        combo_widget.setStyleSheet("background: transparent;")
        combo_widget.setLayout(combo_row)
        self.controls_layout.addWidget(combo_widget)

        # Second row: Text input with custom criteria button
        input_row = QHBoxLayout()
        input_row.setSpacing(4)
        input_row.setContentsMargins(0, 0, 0, 0)
        
        self.filter_input = QLineEdit()
        self.filter_input.setPlaceholderText("Enter text...")
        self.filter_input.setMinimumWidth(120)
        self.filter_input.setMaximumWidth(160)
        self.filter_input.setMaximumHeight(22)
        self.filter_input.setStyleSheet("""
            QLineEdit {
                font-size: 10px;
                padding: 2px 4px;
                background: white;
            }
        """)
        input_row.addWidget(self.filter_input)
        
        # Custom criteria button (pen icon)
        self.custom_criteria_button = QPushButton("✏")
        self.custom_criteria_button.setFixedSize(20, 20)
        self.custom_criteria_button.setToolTip("Open larger editor")
        self.custom_criteria_button.setStyleSheet("""
            QPushButton {
                background: white;
                color: #e67e22;
                border: 2px solid #e67e22;
                border-radius: 3px;
                font-size: 12px;
            }
            QPushButton:hover {
                background: #fef5e7;
            }
        """)
        self.custom_criteria_button.clicked.connect(self._open_custom_criteria_dialog)
        input_row.addWidget(self.custom_criteria_button)
        
        input_widget = QWidget()
        input_widget.setStyleSheet("background: transparent;")
        input_widget.setLayout(input_row)
        self.controls_layout.addWidget(input_widget)

    def _add_numeric_filter(self):
        """Add numeric filter controls"""
        # First row: Operator dropdown
        combo_row = QHBoxLayout()
        combo_row.setSpacing(4)
        combo_row.setContentsMargins(0, 0, 0, 0)
        
        self.match_type_combo = QComboBox()
        self.match_type_combo.addItems(["None", "=", "!=", ">", "<", ">=", "<=", "Between"])
        self.match_type_combo.setCurrentText("=")
        self.match_type_combo.setMinimumWidth(80)
        self.match_type_combo.setMaximumWidth(90)
        self.match_type_combo.setMaximumHeight(22)
        self.match_type_combo.setStyleSheet("""
            QComboBox {
                font-size: 10px;
                padding: 2px 4px;
                background: white;
            }
        """)
        combo_row.addWidget(self.match_type_combo)
        
        # List button (hidden until unique values are loaded)
        self.list_button = QPushButton("☰")
        self.list_button.setFixedSize(20, 20)
        self.list_button.setToolTip("Select Values (right-click field name to fetch)")
        self.list_button.setVisible(False)  # Hidden until values are loaded
        self.list_button.setStyleSheet("""
            QPushButton {
                background: white;
                color: #e67e22;
                border: 2px solid #e67e22;
                border-radius: 3px;
                font-size: 11px;
                font-weight: bold;
            }
            QPushButton:hover {
                background: #fef5e7;
            }
        """)
        self.list_button.clicked.connect(self._open_value_selection_popup)
        combo_row.addWidget(self.list_button)
        
        combo_row.addStretch()
        
        combo_widget = QWidget()
        combo_widget.setStyleSheet("background: transparent;")
        combo_widget.setLayout(combo_row)
        self.controls_layout.addWidget(combo_widget)

        # Second row: Value input
        input_row = QHBoxLayout()
        input_row.setSpacing(4)
        input_row.setContentsMargins(0, 0, 0, 0)
        
        self.filter_input = QLineEdit()
        self.filter_input.setPlaceholderText("Enter value...")
        self.filter_input.setMinimumWidth(120)
        self.filter_input.setMaximumWidth(160)
        self.filter_input.setMaximumHeight(22)
        self.filter_input.setStyleSheet("""
            QLineEdit {
                font-size: 10px;
                padding: 2px 4px;
                background: white;
            }
        """)
        input_row.addWidget(self.filter_input)
        
        self.custom_criteria_button = QPushButton("✏")
        self.custom_criteria_button.setFixedSize(20, 20)
        self.custom_criteria_button.setToolTip("Open larger editor")
        self.custom_criteria_button.setStyleSheet("""
            QPushButton {
                background: white;
                color: #e67e22;
                border: 2px solid #e67e22;
                border-radius: 3px;
                font-size: 12px;
            }
            QPushButton:hover {
                background: #fef5e7;
            }
        """)
        self.custom_criteria_button.clicked.connect(self._open_custom_criteria_dialog)
        input_row.addWidget(self.custom_criteria_button)
        
        input_widget = QWidget()
        input_widget.setStyleSheet("background: transparent;")
        input_widget.setLayout(input_row)
        self.controls_layout.addWidget(input_widget)

    def _add_date_filter(self):
        """Add date filter controls"""
        # First row: Operator dropdown
        combo_row = QHBoxLayout()
        combo_row.setSpacing(4)
        combo_row.setContentsMargins(0, 0, 0, 0)
        
        self.match_type_combo = QComboBox()
        self.match_type_combo.addItems(["None", "=", "!=", ">", "<", ">=", "<=", "Between"])
        self.match_type_combo.setCurrentText("=")
        self.match_type_combo.setMinimumWidth(80)
        self.match_type_combo.setMaximumWidth(90)
        self.match_type_combo.setMaximumHeight(22)
        self.match_type_combo.setStyleSheet("""
            QComboBox {
                font-size: 10px;
                padding: 2px 4px;
                background: white;
            }
        """)
        combo_row.addWidget(self.match_type_combo)
        
        combo_row.addStretch()
        
        combo_widget = QWidget()
        combo_widget.setStyleSheet("background: transparent;")
        combo_widget.setLayout(combo_row)
        self.controls_layout.addWidget(combo_widget)

        # Second row: Date input
        input_row = QHBoxLayout()
        input_row.setSpacing(4)
        input_row.setContentsMargins(0, 0, 0, 0)
        
        self.filter_input = QLineEdit()
        self.filter_input.setPlaceholderText("YYYY-MM-DD...")
        self.filter_input.setMinimumWidth(120)
        self.filter_input.setMaximumWidth(160)
        self.filter_input.setMaximumHeight(22)
        self.filter_input.setStyleSheet("""
            QLineEdit {
                font-size: 10px;
                padding: 2px 4px;
                background: white;
            }
        """)
        input_row.addWidget(self.filter_input)
        
        self.custom_criteria_button = QPushButton("✏")
        self.custom_criteria_button.setFixedSize(20, 20)
        self.custom_criteria_button.setToolTip("Open larger editor")
        self.custom_criteria_button.setStyleSheet("""
            QPushButton {
                background: white;
                color: #e67e22;
                border: 2px solid #e67e22;
                border-radius: 3px;
                font-size: 12px;
            }
            QPushButton:hover {
                background: #fef5e7;
            }
        """)
        self.custom_criteria_button.clicked.connect(self._open_custom_criteria_dialog)
        input_row.addWidget(self.custom_criteria_button)
        
        input_widget = QWidget()
        input_widget.setStyleSheet("background: transparent;")
        input_widget.setLayout(input_row)
        self.controls_layout.addWidget(input_widget)

    def _show_field_context_menu(self, pos):
        """Show right-click context menu for fetching unique values"""
        menu = QMenu(self)
        
        fetch_unique_action = QAction("Fetch Unique Values", self)
        fetch_unique_action.triggered.connect(self._fetch_unique_values)
        menu.addAction(fetch_unique_action)
        
        # Map position to global - works whether called from field_label or widget itself
        menu.exec(self.mapToGlobal(pos))

    def _fetch_unique_values(self):
        """Fetch unique values for this field from the database"""
        try:
            # Find the parent screen to get connection info
            parent = self.parent_screen
            if not parent:
                parent = self.parent()
                while parent and not hasattr(parent, 'datasources'):
                    parent = parent.parent()
            
            if not parent:
                QMessageBox.warning(self, "Error", "Could not find parent screen")
                return
            
            # Find the datasource for this field
            datasource_alias = self.field_data.get('datasource_alias', '')
            table_name = self.field_data['table_name']
            field_name = self.field_data['field_name']
            schema_name = self.field_data.get('schema_name', '')
            
            # Find matching datasource
            datasource = None
            for ds in parent.datasources:
                if ds.get('alias') == datasource_alias or ds.get('table_name') == table_name:
                    datasource = ds
                    break
            
            if not datasource:
                QMessageBox.warning(self, "Error", f"Could not find datasource for {table_name}")
                return
            
            connection = datasource.get('connection')
            if not connection:
                QMessageBox.warning(self, "Error", "No connection found for this datasource")
                return
            
            connection_id = connection.get('connection_id')
            schema_name = datasource.get('schema_name', schema_name)
            
            # Fetch unique values using SchemaDiscovery instance
            schema_discovery = SchemaDiscovery()
            unique_values = schema_discovery.get_unique_values(
                connection_id,
                table_name,
                field_name,
                schema_name=schema_name,
                limit=1000
            )
            
            if unique_values:
                self.unique_values = unique_values
                self.selected_values = unique_values[:]  # Select all by default
                
                # Show and update the list button
                self.list_button.setVisible(True)
                self._update_list_button_style()
                
                # Cache to My Data (metadata cache) so it shows up when clicking on table
                try:
                    from suiteview.data.repositories import MetadataCacheRepository
                    metadata_repo = MetadataCacheRepository()
                    
                    # Get or create metadata entry for this table
                    metadata_id = metadata_repo.get_or_create_metadata(
                        connection_id,
                        table_name,
                        schema_name or ''
                    )
                    
                    # Cache the unique values
                    metadata_repo.cache_unique_values(
                        metadata_id,
                        field_name,
                        unique_values
                    )
                    logger.info(f"Cached {len(unique_values)} unique values for {field_name} to My Data")
                except Exception as cache_err:
                    logger.warning(f"Could not cache unique values: {cache_err}")
                
                QMessageBox.information(
                    self, "Success", 
                    f"Loaded {len(unique_values)} unique values for {field_name}"
                )
            else:
                QMessageBox.information(self, "No Values", f"No unique values found for {field_name}")
                
        except Exception as e:
            logger.error(f"Error fetching unique values: {e}")
            QMessageBox.warning(self, "Error", f"Failed to fetch unique values:\n{str(e)}")

    def _update_list_button_style(self):
        """Update list button style based on selection state"""
        if not self.list_button or not self.unique_values:
            return
        
        all_selected = len(self.selected_values) == len(self.unique_values)
        
        if all_selected:
            # Outline style - no filtering active
            self.list_button.setStyleSheet("""
                QPushButton {
                    background: white;
                    color: #e67e22;
                    border: 2px solid #e67e22;
                    border-radius: 3px;
                    font-size: 11px;
                    font-weight: bold;
                }
                QPushButton:hover {
                    background: #fef5e7;
                }
            """)
        else:
            # Solid style - filtering active
            self.list_button.setStyleSheet("""
                QPushButton {
                    background: #e67e22;
                    color: white;
                    border: 2px solid #e67e22;
                    border-radius: 3px;
                    font-size: 11px;
                    font-weight: bold;
                }
                QPushButton:hover {
                    background: #d35400;
                }
            """)
        
        self.list_button.setToolTip(f"Select Values ({len(self.selected_values)}/{len(self.unique_values)} selected)")

    def _open_value_selection_popup(self):
        """Open the value selection dialog"""
        if not self.unique_values:
            QMessageBox.information(self, "No Values", "No unique values available. Right-click the field name to fetch.")
            return
        
        # Import the dialog from dbquery_screen
        from suiteview.ui.dbquery_screen import ValueSelectionDialog
        
        dialog = ValueSelectionDialog(
            self.field_data['field_name'],
            self.unique_values,
            self.selected_values,
            self
        )
        
        dialog.values_selected.connect(self._update_selected_values)
        dialog.show()

    def _update_selected_values(self, selected_values):
        """Update stored selected values from popup"""
        self.selected_values = selected_values
        self._update_list_button_style()
        
        # Update combo and input based on selection
        all_selected = len(selected_values) == len(self.unique_values)
        
        if hasattr(self, 'match_type_combo'):
            self.match_type_combo.setEnabled(all_selected)
            if not all_selected:
                if self.match_type_combo.findText("List") == -1:
                    self.match_type_combo.addItem("List")
                self.match_type_combo.setCurrentText("List")
                self.match_type_combo.setStyleSheet("""
                    QComboBox {
                        background-color: #E0E0E0;
                        color: #808080;
                        font-size: 10px;
                        padding: 2px 4px;
                    }
                """)
            else:
                list_index = self.match_type_combo.findText("List")
                if list_index != -1:
                    self.match_type_combo.removeItem(list_index)
                self.match_type_combo.setStyleSheet("""
                    QComboBox {
                        font-size: 10px;
                        padding: 2px 4px;
                        background: white;
                    }
                """)
        
        if hasattr(self, 'filter_input'):
            self.filter_input.setEnabled(all_selected)
            if not all_selected:
                self.filter_input.setStyleSheet("""
                    QLineEdit {
                        background-color: #E0E0E0;
                        color: #808080;
                        font-size: 10px;
                        padding: 2px 4px;
                    }
                """)
            else:
                self.filter_input.setStyleSheet("""
                    QLineEdit {
                        font-size: 10px;
                        padding: 2px 4px;
                        background: white;
                    }
                """)

    def _open_custom_criteria_dialog(self):
        """Open dialog to enter custom criteria"""
        from PyQt6.QtWidgets import QDialog, QTextEdit
        
        dialog = QDialog(self)
        dialog.setWindowTitle(f"Edit - {self.field_data['field_name']}")
        dialog.setMinimumWidth(400)
        dialog.setMinimumHeight(200)
        
        layout = QVBoxLayout(dialog)
        
        instructions = QLabel("Enter your criteria below. This gives you more space to type.")
        instructions.setStyleSheet("font-size: 10px; color: #666; background: transparent;")
        instructions.setWordWrap(True)
        layout.addWidget(instructions)
        
        text_edit = QTextEdit()
        text_edit.setPlaceholderText("Type your filter criteria here...")
        
        if hasattr(self, 'filter_input') and self.filter_input.text():
            text_edit.setPlainText(self.filter_input.text())
        
        text_edit.setStyleSheet("""
            QTextEdit {
                font-size: 11px;
                font-family: 'Courier New', monospace;
                background: white;
            }
        """)
        layout.addWidget(text_edit)
        
        button_layout = QHBoxLayout()
        button_layout.addStretch()
        
        clear_btn = QPushButton("Clear")
        clear_btn.clicked.connect(lambda: text_edit.clear())
        button_layout.addWidget(clear_btn)
        
        cancel_btn = QPushButton("Cancel")
        cancel_btn.clicked.connect(dialog.reject)
        button_layout.addWidget(cancel_btn)
        
        ok_btn = QPushButton("OK")
        ok_btn.clicked.connect(dialog.accept)
        ok_btn.setDefault(True)
        button_layout.addWidget(ok_btn)
        
        layout.addLayout(button_layout)
        
        if dialog.exec() == QDialog.DialogCode.Accepted:
            new_text = text_edit.toPlainText().strip()
            if hasattr(self, 'filter_input'):
                self.filter_input.setText(new_text)

    def _reset_filter_values(self):
        """Reset filter values"""
        if hasattr(self, 'filter_input'):
            self.filter_input.clear()
        if hasattr(self, 'match_type_combo'):
            # Reset to first non-None option
            self.match_type_combo.setCurrentIndex(1 if self.match_type_combo.count() > 1 else 0)
        if self.unique_values:
            self.selected_values = self.unique_values[:]
            self._update_list_button_style()
            self._update_selected_values(self.selected_values)

    def get_filter_condition(self) -> dict:
        """Get the filter condition as a dict"""
        match_type = self.match_type_combo.currentText() if hasattr(self, 'match_type_combo') else "Exact"
        value = self.filter_input.text() if hasattr(self, 'filter_input') else ""
        
        # Handle List mode (selected values from popup)
        # Save as List if:
        # 1. Match type is List AND we have selected_values AND
        # 2. Either unique_values is not loaded OR selected_values is a subset of unique_values
        if match_type == "List" and self.selected_values:
            # Check if it's a meaningful filter (not all values selected)
            should_save_as_list = True
            if self.unique_values:
                # If unique_values loaded and ALL are selected, don't save as filter
                if set(self.selected_values) == set(self.unique_values):
                    should_save_as_list = False
            
            if should_save_as_list:
                return {
                    'field_name': self.field_data['field_name'],
                    'table_name': self.field_data['table_name'],
                    'datasource_alias': self.field_data.get('datasource_alias', ''),
                    'operator': 'IN',
                    'value': self.selected_values,
                    'match_type': 'List'
                }
        
        # Map match type to operator
        operator_map = {
            'None': None,
            'Exact': '=',
            '=': '=',
            '!=': '!=',
            '>': '>',
            '<': '<',
            '>=': '>=',
            '<=': '<=',
            'Starts': 'LIKE',
            'Ends': 'LIKE',
            'Contains': 'LIKE',
            'Expression': 'EXPR',
            'Between': 'BETWEEN',
            'List': 'IN'
        }
        
        operator = operator_map.get(match_type, '=')
        
        # Modify value for LIKE patterns
        if match_type == 'Starts':
            value = f"{value}%"
        elif match_type == 'Ends':
            value = f"%{value}"
        elif match_type == 'Contains':
            value = f"%{value}%"
        
        return {
            'field_name': self.field_data['field_name'],
            'table_name': self.field_data['table_name'],
            'datasource_alias': self.field_data.get('datasource_alias', ''),
            'operator': operator,
            'value': value,
            'match_type': match_type
        }
    
    def restore_filter_state(self, match_type: str, value, operator: str = None):
        """Restore saved filter state including List mode selections"""
        # Handle value restoration FIRST (before match_type, so List mode works)
        if value:
            if isinstance(value, list):
                # List mode - restore selected values
                self.selected_values = list(value)
                
                # Update unique_values if not already loaded, so condition check works
                if not self.unique_values:
                    # Use selected_values as minimum set (actual unique values may be larger)
                    # Add placeholder so selected_values < unique_values check works
                    self.unique_values = list(value) + ['__placeholder__']
                
                # Update the filter_input display
                if hasattr(self, 'filter_input'):
                    self.filter_input.setText(', '.join(str(v) for v in value))
                
                # Call _update_selected_values to properly set List mode UI state
                # (greyed out combo/input, solid list button, etc.)
                self._update_selected_values(self.selected_values)
                return  # Done - _update_selected_values handles everything for List mode
            else:
                # Regular value - strip LIKE wildcards for display
                if hasattr(self, 'filter_input'):
                    display_value = str(value)
                    if display_value.startswith('%') and display_value.endswith('%'):
                        display_value = display_value[1:-1]
                    elif display_value.startswith('%'):
                        display_value = display_value[1:]
                    elif display_value.endswith('%'):
                        display_value = display_value[:-1]
                    self.filter_input.setText(display_value)
        
        # Set match type (only for non-List modes, List is handled above)
        if hasattr(self, 'match_type_combo') and match_type and match_type != 'List':
            idx = self.match_type_combo.findText(match_type)
            if idx >= 0:
                self.match_type_combo.setCurrentIndex(idx)
            elif operator:
                # Fallback to operator mapping
                match_type_map = {
                    '=': 'Exact',
                    '!=': '!=',
                    '>': '>',
                    '<': '<',
                    '>=': '>=',
                    '<=': '<=',
                    'LIKE': 'Contains',
                    'IN': 'List'
                }
                if operator in match_type_map:
                    idx = self.match_type_combo.findText(match_type_map[operator])
                    if idx >= 0:
                        self.match_type_combo.setCurrentIndex(idx)
    
    def mousePressEvent(self, event):
        """Handle mouse press for drag start"""
        if event.button() == Qt.MouseButton.LeftButton:
            self.drag_start_position = event.pos()
        super().mousePressEvent(event)
    
    def mouseMoveEvent(self, event):
        """Handle mouse move to initiate drag"""
        if not (event.buttons() & Qt.MouseButton.LeftButton):
            return
        if not hasattr(self, 'drag_start_position'):
            return
        if (event.pos() - self.drag_start_position).manhattanLength() < 10:
            return
        
        # Find the XDBQueryScreen parent
        parent = self.parent()
        while parent and not hasattr(parent, 'criteria_widgets'):
            parent = parent.parent()
        
        if not parent:
            return
        
        # Create drag object
        drag = QDrag(self)
        mime_data = QMimeData()
        
        # Store the index of this widget
        try:
            index = parent.criteria_widgets.index(self)
            mime_data.setText(f"criteria_widget:{index}")
            drag.setMimeData(mime_data)
            drag.exec(Qt.DropAction.MoveAction)
        except ValueError:
            pass
    
    def dragEnterEvent(self, event):
        """Handle drag enter"""
        if event.mimeData().hasText():
            text = event.mimeData().text()
            if text.startswith("criteria_widget:"):
                event.acceptProposedAction()
                self.setStyleSheet("""
                    XDBCriteriaFilterWidget {
                        border: 2px solid #3498db;
                        border-radius: 6px;
                        background: #e8f4fc;
                    }
                """)
    
    def dragLeaveEvent(self, event):
        """Handle drag leave"""
        # Restore normal styling
        self.setStyleSheet("""
            XDBCriteriaFilterWidget {
                border: 2px solid #e67e22;
                border-radius: 6px;
                background: white;
            }
        """)
    
    def dropEvent(self, event):
        """Handle drop to reorder widgets"""
        text = event.mimeData().text()
        if not text.startswith("criteria_widget:"):
            return
        
        source_index = int(text.split(":")[1])
        
        # Find parent with criteria_widgets
        parent = self.parent()
        while parent and not hasattr(parent, 'criteria_widgets'):
            parent = parent.parent()
        
        if not parent:
            return
        
        try:
            target_index = parent.criteria_widgets.index(self)
        except ValueError:
            return
        
        if source_index == target_index:
            # Restore styling
            self.dragLeaveEvent(event)
            return
        
        # Reorder in the list
        widget = parent.criteria_widgets.pop(source_index)
        parent.criteria_widgets.insert(target_index, widget)
        
        # Reorder in the layout
        layout = parent.criteria_layout
        layout.takeAt(source_index)
        layout.insertWidget(target_index, widget)
        
        # Restore styling
        self.dragLeaveEvent(event)
        event.acceptProposedAction()


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
                    'left_connection_id': left_ds['connection']['connection_id'],
                    'left_table_name': left_ds['table_name'],
                    'left_field': left_field,
                    'right_datasource': right_ds['alias'],
                    'right_connection_id': right_ds['connection']['connection_id'],
                    'right_table_name': right_ds['table_name'],
                    'right_field': right_field
                })
        
        # Get right datasource info for the join row header
        right_ds_data = self.right_datasource_combo.currentData()
        right_ds_info = None
        if right_ds_data:
            right_ds_info = {
                'alias': right_ds_data['alias'],
                'connection_id': right_ds_data['connection']['connection_id'],
                'table_name': right_ds_data['table_name']
            }
        
        return {
            'join_type': self.join_type_combo.currentText(),
            'right_datasource': right_ds_info,
            'on_conditions': on_conditions
        }
    
    def update_datasources(self, datasources: list):
        """Update datasource list in all combo boxes when datasources change"""
        self.datasources = datasources
        
        # Helper to update a combo while preserving selection
        def update_combo(combo: QComboBox):
            current_data = combo.currentData()
            current_alias = current_data['alias'] if current_data else None
            
            combo.blockSignals(True)
            combo.clear()
            
            selected_index = 0
            for i, ds in enumerate(datasources):
                display_name = f"{ds['alias']}.{ds['table_name']}"
                combo.addItem(display_name, ds)
                # Try to restore previous selection
                if current_alias and ds['alias'] == current_alias:
                    selected_index = i
            
            combo.setCurrentIndex(selected_index)
            combo.blockSignals(False)
        
        # Update main right datasource combo
        update_combo(self.right_datasource_combo)
        
        # Update all ON condition row combos
        for row_data in self.on_condition_rows:
            update_combo(row_data['left_datasource_combo'])
            update_combo(row_data['right_datasource_combo'])
            # Refresh field lists after updating datasource combos
            self._update_left_fields(
                row_data['left_datasource_combo'],
                row_data['left_field_combo']
            )
            self._update_right_fields(
                row_data['right_datasource_combo'],
                row_data['right_field_combo']
            )
