"""My Data Screen"""

import logging
from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QSplitter,
                              QTreeWidget, QTreeWidgetItem, QTableWidget, QTableWidgetItem,
                              QLabel, QPushButton, QGroupBox, QFormLayout, QMessageBox,
                              QHeaderView, QMenu, QCheckBox, QLineEdit, QComboBox)
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QAction

from suiteview.data.repositories import (SavedTableRepository, ConnectionRepository, 
                                         get_metadata_cache_repository, get_query_repository)
from suiteview.core.schema_discovery import SchemaDiscovery

logger = logging.getLogger(__name__)


class MyDataScreen(QWidget):
    """My Data screen - shows user's curated tables and saved queries"""

    # Signal to request tab switch for editing queries
    edit_query_requested = pyqtSignal(str, int)  # query_type, query_id

    def __init__(self, parent=None):
        super().__init__(parent)
        self.saved_table_repo = SavedTableRepository()
        self.conn_repo = ConnectionRepository()
        self.schema_discovery = SchemaDiscovery()
        self.metadata_cache_repo = get_metadata_cache_repository()
        self.query_repo = get_query_repository()

        # Track current selection
        self.current_connection_id = None
        self.current_table_name = None
        self.current_schema_name = None

        self.init_ui()
        self.load_my_data()

    def init_ui(self):
        """Initialize the UI"""
        # Main layout
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        # Create horizontal splitter for three-panel layout
        splitter = QSplitter(Qt.Orientation.Horizontal)
        
        # Allow panels to be resized down to very small widths
        splitter.setChildrenCollapsible(False)  # Prevent complete collapse

        # Left Panel - My Data Sources (200px default)
        left_panel = self._create_left_panel()
        left_panel.setMinimumWidth(20)  # Allow resizing down to 20px
        splitter.addWidget(left_panel)

        # Middle Panel - Tables List (300px default)
        middle_panel = self._create_middle_panel()
        middle_panel.setMinimumWidth(20)  # Allow resizing down to 20px
        splitter.addWidget(middle_panel)

        # Right Panel - Schema Details (flex)
        right_panel = self._create_right_panel()
        right_panel.setMinimumWidth(100)  # Keep minimum width for readability
        splitter.addWidget(right_panel)

        # Set initial sizes (200px, 300px, rest)
        splitter.setSizes([200, 300, 700])

        layout.addWidget(splitter)

    def _create_left_panel(self) -> QWidget:
        """Create left panel with My Data sources tree"""
        panel = QWidget()
        panel_layout = QVBoxLayout(panel)
        panel_layout.setContentsMargins(5, 5, 5, 5)

        # Panel header
        header = QLabel("Tables")
        header.setObjectName("panel_header")
        panel_layout.addWidget(header)

        # My Data tree
        self.my_data_tree = QTreeWidget()
        self.my_data_tree.setHeaderLabel("My Data")
        self.my_data_tree.setHeaderHidden(True)
        self.my_data_tree.setStyleSheet("""
            QTreeWidget {
                background: white;
                border: 1px solid #ddd;
                border-radius: 4px;
            }
            QTreeWidget::item:hover {
                background-color: #b3d9ff;
            }
            QTreeWidget::item:selected {
                background-color: #b3d9ff;
            }
        """)

        # Don't create section items here - they will be created in load_my_data()
        # in the correct order after connection types

        # Connect signals
        self.my_data_tree.itemClicked.connect(self.on_data_source_clicked)

        panel_layout.addWidget(self.my_data_tree)
        return panel

    def _create_middle_panel(self) -> QWidget:
        """Create middle panel with tables list"""
        panel = QWidget()
        panel_layout = QVBoxLayout(panel)
        panel_layout.setContentsMargins(5, 5, 5, 5)
        panel_layout.setSpacing(5)

        # Panel header
        header = QLabel("Fields")
        header.setObjectName("panel_header")
        panel_layout.addWidget(header)
        
        # Search box for filtering tables
        self.tables_search_box = QLineEdit()
        self.tables_search_box.setPlaceholderText("Search tables...")
        self.tables_search_box.textChanged.connect(self._filter_tables)
        panel_layout.addWidget(self.tables_search_box)

        # Tables tree
        self.tables_tree = QTreeWidget()
        self.tables_tree.setHeaderLabel("Table Name")
        self.tables_tree.setHeaderHidden(True)
        self.tables_tree.setStyleSheet("""
            QTreeWidget {
                background: white;
                border: 1px solid #ddd;
                border-radius: 4px;
            }
            QTreeWidget::item:hover {
                background-color: #b3d9ff;
            }
            QTreeWidget::item:selected {
                background-color: #b3d9ff;
            }
        """)
        # Make header stretch to fill width and remove spacing
        self.tables_tree.setIndentation(20)

        # Connect signals
        self.tables_tree.itemClicked.connect(self.on_table_clicked)
        self.tables_tree.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.tables_tree.customContextMenuRequested.connect(self.show_context_menu)

        panel_layout.addWidget(self.tables_tree)

        # Info label
        self.table_info_label = QLabel("Select a connection to view tables")
        self.table_info_label.setStyleSheet("color: #7f8c8d; font-size: 10px; padding: 5px;")
        panel_layout.addWidget(self.table_info_label)

        return panel

    def _create_right_panel(self) -> QWidget:
        """Create right panel for schema details"""
        panel = QWidget()
        self.right_panel_layout = QVBoxLayout(panel)
        self.right_panel_layout.setContentsMargins(5, 5, 5, 5)

        # Default content
        self.default_label = QLabel("Select a table to view schema details")
        self.default_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.default_label.setStyleSheet("color: #7f8c8d; font-size: 12px;")
        self.right_panel_layout.addWidget(self.default_label)

        return panel

    def load_my_data(self):
        """Load all user's saved data into the tree"""
        # Clear the entire tree
        self.my_data_tree.clear()

        # Clear tables list
        self.tables_tree.clear()
        self.table_info_label.setText("Select a connection to view tables")

        # Load connections directly at root level (they will be added first)
        self._load_my_connections()

        # Create and add DB Queries section AFTER connection types
        self.db_queries_item = QTreeWidgetItem(self.my_data_tree)
        self.db_queries_item.setText(0, "DB Queries")
        self.db_queries_item.setData(0, Qt.ItemDataRole.UserRole, "section")
        self.db_queries_item.setExpanded(True)
        self.db_queries_item.setFlags(Qt.ItemFlag.ItemIsEnabled)
        self._load_db_queries()

        # Create and add XDB Queries section AFTER DB Queries
        self.xdb_queries_item = QTreeWidgetItem(self.my_data_tree)
        self.xdb_queries_item.setText(0, "XDB Queries")
        self.xdb_queries_item.setData(0, Qt.ItemDataRole.UserRole, "section")
        self.xdb_queries_item.setExpanded(True)
        self.xdb_queries_item.setFlags(Qt.ItemFlag.ItemIsEnabled)

        # TODO: Load XDB Queries (Phase 5)

    def _load_db_queries(self):
        """Load saved DB queries"""
        try:
            queries = self.query_repo.get_all_queries(query_type='DB')
            
            for query in queries:
                query_item = QTreeWidgetItem()
                query_item.setText(0, query['query_name'])
                query_item.setData(0, Qt.ItemDataRole.UserRole, "db_query")
                query_item.setData(0, Qt.ItemDataRole.UserRole + 1, query['query_id'])
                query_item.setData(0, Qt.ItemDataRole.UserRole + 2, query['query_definition'])
                
                self.db_queries_item.addChild(query_item)
            
            logger.info(f"Loaded {len(queries)} DB queries")
            
        except Exception as e:
            logger.error(f"Error loading DB queries: {e}")
            QMessageBox.critical(self, "Error", f"Failed to load DB queries:\n{str(e)}")

    def _load_my_connections(self):
        """Load saved connections directly at root level (no parent)"""
        try:
            # Get all saved tables
            saved_tables = self.saved_table_repo.get_all_saved_tables()

            # Group by connection
            connections_dict = {}
            for table in saved_tables:
                conn_id = table['connection_id']
                if conn_id not in connections_dict:
                    # Get connection details
                    conn = self.conn_repo.get_connection(conn_id)
                    if conn:
                        connections_dict[conn_id] = {
                            'connection': conn,
                            'tables': []
                        }

                if conn_id in connections_dict:
                    connections_dict[conn_id]['tables'].append(table)

            # Group connections by their actual type (don't merge types)
            type_groups = {}
            for conn_id, data in connections_dict.items():
                conn = data['connection']
                conn_type = conn['connection_type']
                
                # DEBUG: Log connection type
                logger.info(f"DEBUG: Connection '{conn['connection_name']}' has type '{conn_type}'")
                
                # Use the actual connection type as-is
                if conn_type not in type_groups:
                    type_groups[conn_type] = []
                
                type_groups[conn_type].append((conn_id, conn))

            # DEBUG: Log all type groups
            logger.info(f"DEBUG: Type groups found: {list(type_groups.keys())}")

            # Define the display order (before DB Queries and XDB Queries)
            type_order = ['DB2', 'SQL_SERVER', 'ACCESS', 'EXCEL', 'CSV', 'FIXED_WIDTH']
            
            # Add type nodes in the specified order
            insert_position = 0  # Track actual position in tree
            for type_name in type_order:
                if type_name not in type_groups:
                    continue
                    
                # Create type node at the correct position
                type_item = QTreeWidgetItem()
                type_item.setText(0, type_name)
                type_item.setData(0, Qt.ItemDataRole.UserRole, "connection_type")
                type_item.setExpanded(True)  # Expand type nodes by default
                
                # Insert at the actual position (not the type_order index)
                self.my_data_tree.insertTopLevelItem(insert_position, type_item)
                logger.info(f"DEBUG: Inserted '{type_name}' at position {insert_position}")
                insert_position += 1  # Increment for next type
                
                # Add connections under this type
                for conn_id, conn in sorted(type_groups[type_name], key=lambda x: x[1]['connection_name']):
                    conn_item = QTreeWidgetItem(type_item)
                    conn_item.setText(0, conn['connection_name'])
                    conn_item.setData(0, Qt.ItemDataRole.UserRole, "connection")
                    conn_item.setData(0, Qt.ItemDataRole.UserRole + 1, conn_id)
                    conn_item.setExpanded(False)  # Start collapsed

            logger.info(f"Loaded {len(connections_dict)} connections in {len(type_groups)} type groups")

        except Exception as e:
            logger.error(f"Error loading My Connections: {e}")
            QMessageBox.critical(self, "Error", f"Failed to load My Connections:\n{str(e)}")

    def on_data_source_clicked(self, item: QTreeWidgetItem, column: int):
        """Handle click on data source tree (left panel)"""
        item_type = item.data(0, Qt.ItemDataRole.UserRole)

        logger.info(f"Data source clicked: type={item_type}, text={item.text(0)}")

        if item_type == "connection":
            # Load tables for this connection in middle panel
            conn_id = item.data(0, Qt.ItemDataRole.UserRole + 1)
            self.load_tables_for_connection(conn_id)

        elif item_type == "db_query":
            # TODO: Show query details (Phase 4)
            pass

        elif item_type == "xdb_query":
            # TODO: Show query details (Phase 5)
            pass

    def load_tables_for_connection(self, connection_id: int):
        """Load saved tables for a connection into middle panel"""
        self.current_connection_id = connection_id
        self.tables_tree.clear()

        try:
            # Get saved tables for this connection
            saved_tables = self.saved_table_repo.get_saved_tables(connection_id)

            if not saved_tables:
                self.table_info_label.setText("No saved tables for this connection")
                return

            # Add tables to middle panel
            for table in saved_tables:
                table_item = QTreeWidgetItem()
                table_name = table['table_name']
                schema_name = table.get('schema_name', '')

                # Display name (show schema if present)
                display_name = f"{schema_name}.{table_name}" if schema_name else table_name
                table_item.setText(0, display_name)
                table_item.setData(0, Qt.ItemDataRole.UserRole, "table")
                table_item.setData(0, Qt.ItemDataRole.UserRole + 1, connection_id)
                table_item.setData(0, Qt.ItemDataRole.UserRole + 2, table_name)
                table_item.setData(0, Qt.ItemDataRole.UserRole + 3, schema_name)

                self.tables_tree.addTopLevelItem(table_item)

            self.table_info_label.setText(f"{len(saved_tables)} table(s)")
            logger.info(f"Loaded {len(saved_tables)} tables for connection {connection_id}")

        except Exception as e:
            logger.error(f"Error loading tables: {e}")
            self.table_info_label.setText(f"Error: {str(e)}")
            QMessageBox.warning(self, "Error", f"Failed to load tables:\n{str(e)}")

    def _filter_tables(self, search_text: str):
        """Filter tables based on search text"""
        search_text = search_text.lower()
        
        for i in range(self.tables_tree.topLevelItemCount()):
            item = self.tables_tree.topLevelItem(i)
            table_name = item.text(0).lower()
            
            # Show/hide based on search text
            if search_text in table_name:
                item.setHidden(False)
            else:
                item.setHidden(True)

    def on_table_clicked(self, item: QTreeWidgetItem, column: int):
        """Handle click on table in middle panel"""
        item_type = item.data(0, Qt.ItemDataRole.UserRole)

        if item_type == "table":
            conn_id = item.data(0, Qt.ItemDataRole.UserRole + 1)
            table_name = item.data(0, Qt.ItemDataRole.UserRole + 2)
            schema_name = item.data(0, Qt.ItemDataRole.UserRole + 3)

            logger.info(f"Table clicked: conn_id={conn_id}, table={table_name}, schema={schema_name}")
            self.show_table_schema(conn_id, table_name, schema_name)

    def show_table_schema(self, connection_id: int, table_name: str, schema_name: str):
        """Display table schema in right panel"""
        self.current_connection_id = connection_id
        self.current_table_name = table_name
        self.current_schema_name = schema_name

        # Clear right panel
        self._clear_right_panel()

        # Create schema view widget
        schema_widget = QWidget()
        schema_layout = QVBoxLayout(schema_widget)
        schema_layout.setContentsMargins(0, 0, 0, 0)

        # Header with table name
        display_name = f"{schema_name}.{table_name}" if schema_name else table_name
        header = QLabel(f"Table: {display_name}")
        header.setStyleSheet("""
            font-size: 14px;
            font-weight: 800;
            color: #2c3e50;
            padding: 10px 0;
        """)
        schema_layout.addWidget(header)

        # Buttons above the table
        button_layout = QHBoxLayout()
        button_layout.addStretch()

        self.find_unique_btn = QPushButton("Find Unique")
        self.find_unique_btn.setObjectName("gold_button")
        self.find_unique_btn.setMinimumWidth(120)
        self.find_unique_btn.clicked.connect(self.find_unique_values)
        button_layout.addWidget(self.find_unique_btn)

        self.preview_btn = QPushButton("Preview")
        self.preview_btn.setObjectName("gold_button")
        self.preview_btn.setMinimumWidth(120)
        self.preview_btn.clicked.connect(self.preview_table)
        button_layout.addWidget(self.preview_btn)

        schema_layout.addLayout(button_layout)

        # Schema table with proper columns
        self.schema_table = QTableWidget()
        self.schema_table.setColumnCount(8)
        self.schema_table.setHorizontalHeaderLabels([
            "Field", "Type", "Key", "Nullable", "Common", "Find Unique", "Last Updated", "Unique Values"
        ])
        self.schema_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.schema_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.schema_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)

        # Set specific column widths
        self.schema_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)  # Field
        self.schema_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)  # Type
        self.schema_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Fixed)  # Key
        self.schema_table.setColumnWidth(2, 50)
        self.schema_table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.Fixed)  # Nullable
        self.schema_table.setColumnWidth(3, 70)
        self.schema_table.horizontalHeader().setSectionResizeMode(4, QHeaderView.ResizeMode.Fixed)  # Common checkbox
        self.schema_table.setColumnWidth(4, 80)
        self.schema_table.horizontalHeader().setSectionResizeMode(5, QHeaderView.ResizeMode.Fixed)  # Find Unique checkbox
        self.schema_table.setColumnWidth(5, 100)
        self.schema_table.horizontalHeader().setSectionResizeMode(6, QHeaderView.ResizeMode.ResizeToContents)  # Last Updated
        self.schema_table.horizontalHeader().setSectionResizeMode(7, QHeaderView.ResizeMode.Stretch)  # Unique Values

        # Connect double-click event to show unique values dialog
        self.schema_table.cellDoubleClicked.connect(self.on_schema_cell_double_clicked)

        # Get or create metadata entry
        metadata_id = self.metadata_cache_repo.get_or_create_metadata(
            connection_id, table_name, schema_name
        )

        # Get connection type to determine if we should allow type editing
        connection = self.conn_repo.get_connection(connection_id)
        connection_type = connection.get('connection_type') if connection else None
        is_csv = (connection_type == 'CSV')

        # Try to load cached columns first
        cached_columns = self.metadata_cache_repo.get_cached_columns(metadata_id)
        cached_at = None

        if cached_columns:
            logger.info(f"Using cached columns for {display_name}")
            columns = cached_columns
            cached_at = self.metadata_cache_repo.get_metadata_cached_at(metadata_id)
        else:
            # Load column data from database
            logger.info(f"Fetching fresh column data for {display_name}")
            columns = self.schema_discovery.get_columns(connection_id, table_name, schema_name)
            
            # Cache the column metadata
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
            cached_at = self.metadata_cache_repo.get_metadata_cached_at(metadata_id)

        # Load column data
        try:
            self.schema_table.setRowCount(len(columns))

            # Store checkboxes for later access
            self.common_checkboxes = []
            self.find_unique_checkboxes = []
            self.type_comboboxes = []  # Store type dropdowns for CSV files

            for row, col_data in enumerate(columns):
                # Handle both cache format and direct query format
                col_name = col_data.get('name') or col_data.get('column_name')
                col_type = col_data.get('type') or col_data.get('data_type')
                is_pk = col_data.get('primary_key') or col_data.get('is_primary_key', False)
                is_nullable = col_data.get('nullable', True)
                if 'is_nullable' in col_data:
                    is_nullable = col_data['is_nullable']
                is_common = col_data.get('is_common', False)

                # Field (Column Name)
                self.schema_table.setItem(row, 0, QTableWidgetItem(col_name))

                # Type (Data Type) - For CSV files, use QComboBox to allow changing type
                if is_csv:
                    type_combo = QComboBox()
                    type_combo.addItems([
                        "TEXT",
                        "INTEGER", 
                        "FLOAT",
                        "DECIMAL",
                        "DATE",
                        "DATETIME",
                        "BOOLEAN"
                    ])
                    
                    # Apply compact styling to the combobox - fill the entire cell
                    type_combo.setStyleSheet("""
                        QComboBox {
                            border: 1px solid #ccc;
                            border-radius: 2px;
                            padding: 1px 3px 1px 5px;
                            background: white;
                            font-size: 11px;
                        }
                        QComboBox:hover {
                            border: 1px solid #0078d4;
                        }
                        QComboBox::drop-down {
                            border: none;
                            width: 18px;
                        }
                        QComboBox::down-arrow {
                            image: url(none);
                            border-left: 3px solid transparent;
                            border-right: 3px solid transparent;
                            border-top: 4px solid #555;
                            width: 0;
                            height: 0;
                            margin-right: 3px;
                        }
                    """)
                    
                    # Set current type
                    current_type = col_type.upper()
                    if current_type in ["TEXT", "INTEGER", "FLOAT", "DECIMAL", "DATE", "DATETIME", "BOOLEAN"]:
                        type_combo.setCurrentText(current_type)
                    else:
                        type_combo.setCurrentText("TEXT")
                    
                    # Connect change handler
                    type_combo.currentTextChanged.connect(
                        lambda new_type, r=row, c=col_name: self.on_type_changed(r, c, new_type)
                    )
                    
                    # Add directly to cell without wrapper widget
                    self.schema_table.setCellWidget(row, 1, type_combo)
                    self.type_comboboxes.append(type_combo)
                else:
                    # Regular database - just display type as text
                    self.schema_table.setItem(row, 1, QTableWidgetItem(col_type))
                    self.type_comboboxes.append(None)

                # Key (PK, FK, etc.)
                key_value = ""
                if is_pk:
                    key_value = "PK"
                # TODO: Add FK detection when available
                self.schema_table.setItem(row, 2, QTableWidgetItem(key_value))

                # Nullable
                nullable = "Yes" if is_nullable else "No"
                self.schema_table.setItem(row, 3, QTableWidgetItem(nullable))

                # Common (QCheckBox widget) - Column 4
                common_checkbox_widget = QWidget()
                common_checkbox_layout = QHBoxLayout(common_checkbox_widget)
                common_checkbox_layout.setContentsMargins(0, 0, 0, 0)
                common_checkbox_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

                common_checkbox = QCheckBox()
                common_checkbox.setChecked(is_common)
                common_checkbox.stateChanged.connect(
                    lambda state, r=row, c=col_name: self.on_common_checkbox_changed(r, c, state)
                )
                common_checkbox_layout.addWidget(common_checkbox)

                self.schema_table.setCellWidget(row, 4, common_checkbox_widget)
                self.common_checkboxes.append(common_checkbox)

                # Find Unique (QCheckBox widget) - Column 5 (shifted from 4)
                find_unique_checkbox_widget = QWidget()
                find_unique_checkbox_layout = QHBoxLayout(find_unique_checkbox_widget)
                find_unique_checkbox_layout.setContentsMargins(0, 0, 0, 0)
                find_unique_checkbox_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

                find_unique_checkbox = QCheckBox()
                find_unique_checkbox_layout.addWidget(find_unique_checkbox)

                self.schema_table.setCellWidget(row, 5, find_unique_checkbox_widget)
                self.find_unique_checkboxes.append(find_unique_checkbox)

                # Check for cached unique values
                cached_unique = self.metadata_cache_repo.get_cached_unique_values(metadata_id, col_name)
                
                if cached_unique:
                    # Last Updated (timestamp from cache) - Column 6 (shifted from 5)
                    timestamp = cached_unique['cached_at']
                    if timestamp:
                        # Format timestamp nicely
                        from datetime import datetime
                        dt_obj = datetime.fromisoformat(timestamp.replace('Z', '+00:00'))
                        timestamp = dt_obj.strftime("%m/%d/%Y %H:%M")
                    self.schema_table.setItem(row, 6, QTableWidgetItem(timestamp or ""))

                    # Unique Values (display cached unique values) - Column 7 (shifted from 6)
                    unique_values = cached_unique['unique_values']
                    value_count = cached_unique['value_count']
                    
                    if value_count == 0:
                        display_text = "(no values)"
                    elif value_count <= 10:
                        display_text = ", ".join(str(v) for v in unique_values)
                    else:
                        first_ten = ", ".join(str(v) for v in unique_values[:10])
                        display_text = f"{first_ten}... ({value_count} total)"
                    
                    unique_values_item = QTableWidgetItem(display_text)
                    unique_values_item.setData(Qt.ItemDataRole.UserRole, unique_values)
                    self.schema_table.setItem(row, 7, unique_values_item)
                else:
                    # No cached data
                    self.schema_table.setItem(row, 6, QTableWidgetItem(""))
                    self.schema_table.setItem(row, 7, QTableWidgetItem(""))

            schema_layout.addWidget(self.schema_table)

            # Add to right panel
            self.right_panel_layout.addWidget(schema_widget)

            logger.info(f"Displayed schema for {display_name} with {len(columns)} columns")

        except Exception as e:
            logger.error(f"Error loading schema: {e}")
            error_label = QLabel(f"Error loading schema: {str(e)}")
            error_label.setStyleSheet("color: #e74c3c; padding: 20px;")
            self.right_panel_layout.addWidget(error_label)

    def find_unique_values(self):
        """Find unique values for checked columns"""
        if not hasattr(self, 'schema_table') or not hasattr(self, 'find_unique_checkboxes'):
            return

        # Get checked columns using stored checkboxes
        checked_columns = []
        for row, checkbox in enumerate(self.find_unique_checkboxes):
            if checkbox.isChecked():
                col_name_item = self.schema_table.item(row, 0)  # Field name is in column 0
                if col_name_item:
                    checked_columns.append(col_name_item.text())

        if not checked_columns:
            QMessageBox.information(self, "No Columns Selected",
                                   "Please check at least one column to find unique values.")
            return

        # Get or create metadata entry
        metadata_id = self.metadata_cache_repo.get_or_create_metadata(
            self.current_connection_id,
            self.current_table_name,
            self.current_schema_name
        )

        # Execute queries to find unique values
        try:
            import datetime
            from datetime import datetime as dt

            for col_name in checked_columns:
                # Find the row for this column
                row_index = None
                for row in range(self.schema_table.rowCount()):
                    if self.schema_table.item(row, 0).text() == col_name:
                        row_index = row
                        break

                if row_index is None:
                    continue

                # Query unique values for this column
                logger.info(f"Finding unique values for {col_name}")
                unique_values = self.schema_discovery.get_unique_values(
                    self.current_connection_id,
                    self.current_table_name,
                    col_name,
                    self.current_schema_name
                )

                # Cache the unique values
                self.metadata_cache_repo.cache_unique_values(metadata_id, col_name, unique_values)
                
                # Get the cached timestamp
                cached_unique = self.metadata_cache_repo.get_cached_unique_values(metadata_id, col_name)
                timestamp = cached_unique['cached_at'] if cached_unique else dt.now().isoformat()
                
                # Format timestamp nicely
                dt_obj = dt.fromisoformat(timestamp.replace('Z', '+00:00'))
                formatted_timestamp = dt_obj.strftime("%m/%d/%Y %H:%M")

                # Update the table with results (Column 6 is Last Updated)
                last_updated_item = self.schema_table.item(row_index, 6)
                if last_updated_item:
                    last_updated_item.setText(formatted_timestamp)
                else:
                    self.schema_table.setItem(row_index, 6, QTableWidgetItem(formatted_timestamp))

                # Format unique values for display
                value_count = len(unique_values)
                if value_count == 0:
                    display_text = "(no values)"
                elif value_count <= 10:
                    # Show all values if 10 or fewer
                    display_text = ", ".join(str(v) for v in unique_values)
                else:
                    # Show first 10 + count if more than 10
                    first_ten = ", ".join(str(v) for v in unique_values[:10])
                    display_text = f"{first_ten}... ({value_count} total)"

                # Update Column 7 (Unique Values)
                unique_values_item = self.schema_table.item(row_index, 7)
                if unique_values_item:
                    unique_values_item.setText(display_text)
                else:
                    unique_values_item = QTableWidgetItem(display_text)
                    self.schema_table.setItem(row_index, 7, unique_values_item)
                
                # Store the full unique values list for later access (for double-click dialog)
                unique_values_item = self.schema_table.item(row_index, 7)
                unique_values_item.setData(Qt.ItemDataRole.UserRole, unique_values)

                # Uncheck the "Find Unique" checkbox for this column
                self.find_unique_checkboxes[row_index].setChecked(False)

                logger.info(f"Found and cached {value_count} unique values for {col_name}")

            QMessageBox.information(self, "Find Unique Values",
                                   f"Successfully found unique values for {len(checked_columns)} column(s)")

        except Exception as e:
            logger.error(f"Error finding unique values: {e}")
            QMessageBox.critical(self, "Error", f"Failed to find unique values:\n{str(e)}")

    def on_schema_cell_double_clicked(self, row: int, column: int):
        """Handle double-click on schema table cells"""
        # Only handle double-clicks on the "Unique Values" column (column 7)
        if column != 7:
            return
        
        # Get the unique values stored in the cell
        unique_values_item = self.schema_table.item(row, 7)
        if not unique_values_item:
            return
        
        # Get the full list of unique values from UserRole data
        unique_values = unique_values_item.data(Qt.ItemDataRole.UserRole)
        if not unique_values:
            QMessageBox.information(self, "No Data", 
                                   "No unique values have been found for this column yet.\n"
                                   "Check the 'Find Unique' box and click 'Find Unique Values' to populate.")
            return
        
        # Get the column name
        col_name = self.schema_table.item(row, 0).text()
        
        # Show dialog with all unique values
        self.show_unique_values_dialog(col_name, unique_values)

    def show_unique_values_dialog(self, column_name: str, unique_values: list):
        """Show a dialog displaying all unique values in a grid"""
        from PyQt6.QtWidgets import QDialog, QVBoxLayout, QLabel, QTableWidget, QTableWidgetItem
        
        dialog = QDialog(self)
        dialog.setWindowTitle(f"Unique Values - {column_name}")
        dialog.setMinimumWidth(400)
        dialog.setMinimumHeight(500)
        
        layout = QVBoxLayout(dialog)
        
        # Header label
        header = QLabel(f"Column: {column_name}")
        header.setStyleSheet("font-weight: bold; font-size: 14px; padding: 10px;")
        layout.addWidget(header)
        
        # Count label
        count_label = QLabel(f"Total unique values: {len(unique_values)}")
        count_label.setStyleSheet("padding: 0 10px 10px 10px;")
        layout.addWidget(count_label)
        
        # Table with unique values
        table = QTableWidget()
        table.setColumnCount(2)
        table.setHorizontalHeaderLabels(["#", "Value"])
        table.setRowCount(len(unique_values))
        
        # Populate table
        for i, value in enumerate(unique_values):
            # Row number
            table.setItem(i, 0, QTableWidgetItem(str(i + 1)))
            
            # Value (convert to string, handle None)
            display_value = str(value) if value is not None else "(NULL)"
            table.setItem(i, 1, QTableWidgetItem(display_value))
        
        # Set column widths
        table.setColumnWidth(0, 60)
        table.horizontalHeader().setStretchLastSection(True)
        
        # Make read-only
        table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        
        layout.addWidget(table)
        
        # Add close button
        from PyQt6.QtWidgets import QPushButton, QHBoxLayout
        button_layout = QHBoxLayout()
        button_layout.addStretch()
        
        close_btn = QPushButton("Close")
        close_btn.clicked.connect(dialog.accept)
        button_layout.addWidget(close_btn)
        
        layout.addLayout(button_layout)
        
        dialog.exec()

    def preview_table(self):
        """Preview table data (first 100 rows)"""
        if not self.current_connection_id or not self.current_table_name:
            return

        try:
            from suiteview.ui.dialogs.preview_dialog import PreviewDialog

            # Get preview data
            display_name = f"{self.current_schema_name}.{self.current_table_name}" if self.current_schema_name else self.current_table_name
            logger.info(f"Fetching preview data for {display_name}")

            columns, data = self.schema_discovery.get_preview_data(
                self.current_connection_id,
                self.current_table_name,
                self.current_schema_name,
                limit=100
            )

            # Show preview dialog
            dialog = PreviewDialog(display_name, data, columns, self)
            dialog.exec()

        except Exception as e:
            logger.error(f"Error previewing table: {e}")
            QMessageBox.critical(self, "Error", f"Failed to preview table:\n{str(e)}")

    def on_common_checkbox_changed(self, row: int, column_name: str, state: int):
        """Handle common checkbox state change"""
        is_common = (state == Qt.CheckState.Checked.value)
        
        # Get metadata_id for the current table
        metadata_id = self.metadata_cache_repo.get_or_create_metadata(
            self.current_connection_id,
            self.current_table_name,
            self.current_schema_name
        )
        
        # Update the database
        self.metadata_cache_repo.update_column_common_flag(metadata_id, column_name, is_common)
        
        logger.info(f"Set common flag for {column_name} to {is_common}")

    def on_type_changed(self, row: int, column_name: str, new_type: str):
        """Handle data type change for CSV columns"""
        # Get metadata_id for the current table
        metadata_id = self.metadata_cache_repo.get_or_create_metadata(
            self.current_connection_id,
            self.current_table_name,
            self.current_schema_name
        )
        
        # Update the column type in the cache
        self.metadata_cache_repo.update_column_type(metadata_id, column_name, new_type)
        
        logger.info(f"Changed type for {column_name} to {new_type}")

    def show_context_menu(self, position):
        """Show context menu for tree items"""
        item = self.tables_tree.itemAt(position)
        if not item:
            return

        item_type = item.data(0, Qt.ItemDataRole.UserRole)

        menu = QMenu()

        if item_type == "table":
            # Context menu for saved tables
            remove_action = QAction("Remove from My Data", self)
            remove_action.triggered.connect(lambda: self.remove_saved_table(item))
            menu.addAction(remove_action)

        elif item_type == "db_query" or item_type == "xdb_query":
            # Context menu for saved queries (Phase 4/5)
            edit_action = QAction("Edit Query", self)
            menu.addAction(edit_action)

            delete_action = QAction("Delete Query", self)
            menu.addAction(delete_action)

        if not menu.isEmpty():
            menu.exec(self.tables_tree.viewport().mapToGlobal(position))

    def remove_saved_table(self, item: QTreeWidgetItem):
        """Remove a table from My Data"""
        conn_id = item.data(0, Qt.ItemDataRole.UserRole + 1)
        table_name = item.data(0, Qt.ItemDataRole.UserRole + 2)
        schema_name = item.data(0, Qt.ItemDataRole.UserRole + 3)

        # Confirm deletion
        display_name = f"{schema_name}.{table_name}" if schema_name else table_name
        reply = QMessageBox.question(
            self,
            "Remove Table",
            f"Remove '{display_name}' from My Data?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )

        if reply == QMessageBox.StandardButton.Yes:
            try:
                self.saved_table_repo.delete_saved_table(conn_id, table_name, schema_name)
                logger.info(f"Removed saved table: {display_name}")

                # Reload tables for current connection
                if self.current_connection_id == conn_id:
                    self.load_tables_for_connection(conn_id)

                # Reload My Data tree
                self.load_my_data()

                # Clear right panel if this was the selected table
                if self.current_table_name == table_name:
                    self._clear_right_panel()
                    self.right_panel_layout.addWidget(self.default_label)

            except Exception as e:
                logger.error(f"Error removing saved table: {e}")
                QMessageBox.critical(self, "Error", f"Failed to remove table:\n{str(e)}")

    def _clear_right_panel(self):
        """Clear all widgets from right panel"""
        while self.right_panel_layout.count():
            child = self.right_panel_layout.takeAt(0)
            if child.widget():
                child.widget().deleteLater()

    def refresh(self):
        """Refresh My Data (called when tables are saved/removed)"""
        self.load_my_data()
