"""Connections Screen - Manage database connections"""

import logging
from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel, QSplitter,
                              QTreeWidget, QTreeWidgetItem, QLineEdit, QToolBar,
                              QPushButton, QTableWidget, QTableWidgetItem, QMessageBox,
                              QHeaderView, QCheckBox, QMenu, QDialog, QTextEdit, QFileDialog)
from PyQt6.QtCore import Qt, pyqtSignal, QThread, QPoint
from PyQt6.QtGui import QIcon, QAction, QCursor, QFont

from suiteview.core.connection_manager import get_connection_manager
from suiteview.core.schema_discovery import get_schema_discovery
from suiteview.data.repositories import get_saved_table_repository
from suiteview.ui.dialogs.add_connection_dialog_v2 import AddConnectionDialog

logger = logging.getLogger(__name__)


class ConnectionsScreen(QWidget):
    """Connections screen with three-panel layout"""

    # Signal emitted when saved tables change (so My Data can refresh)
    saved_tables_changed = pyqtSignal()
    
    # Signal emitted when connections are added/edited/deleted (so other screens can refresh)
    connections_changed = pyqtSignal()
    
    # Signal emitted when a mainframe FTP connection is selected (connection_id)
    mainframe_connection_selected = pyqtSignal(int)

    def __init__(self):
        super().__init__()
        self.conn_manager = get_connection_manager()
        self.schema_discovery = get_schema_discovery()
        self.saved_table_repo = get_saved_table_repository()

        self.current_connection_id = None
        self.current_table = None
        self.current_schema = None
        self._updating_checkboxes = False  # Flag to prevent reload loops

        self.init_ui()
        self.load_connections()

    def init_ui(self):
        """Initialize the UI"""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # Create horizontal splitter for three panels
        splitter = QSplitter(Qt.Orientation.Horizontal)

        # Left Panel - Connection Tree
        left_panel = self.create_connections_panel()
        splitter.addWidget(left_panel)

        # Middle Panel - Tables List
        middle_panel = self.create_tables_panel()
        splitter.addWidget(middle_panel)

        # Right Panel - Schema Details
        right_panel = self.create_schema_panel()
        splitter.addWidget(right_panel)

        # Set initial sizes (200px, 300px, remaining)
        splitter.setSizes([200, 300, 700])

        layout.addWidget(splitter)


    def create_connections_panel(self) -> QWidget:
        """Create connections tree panel"""
        panel = QWidget()
        panel.setObjectName("panel")

        layout = QVBoxLayout(panel)
        layout.setSpacing(8)

        # Header with embedded + New button
        header_container = QWidget()
        header_container.setObjectName("panel_header")
        header_layout = QHBoxLayout(header_container)
        header_layout.setContentsMargins(10, 5, 10, 5)
        header_layout.setSpacing(10)

        header_label = QLabel("DATABASES")
        header_label.setStyleSheet("background: transparent; border: none;")
        header_layout.addWidget(header_label)

        header_layout.addStretch()

        # Add button inside header
        add_btn = QPushButton("+ New")
        add_btn.setFixedHeight(25)
        add_btn.setObjectName("header_button")
        add_btn.clicked.connect(self.add_connection)
        add_btn.setToolTip("Add New Connection")
        header_layout.addWidget(add_btn)

        layout.addWidget(header_container)

        # Connection tree
        self.conn_tree = QTreeWidget()
        self.conn_tree.setHeaderHidden(True)
        self.conn_tree.setStyleSheet("""
            QTreeWidget {
                background: white;
                border: 1px solid #ddd;
                border-radius: 4px;
            }
            QTreeWidget::item {
                height: 18px;
                padding: 0px 2px;
            }
            QTreeWidget::item:hover {
                background-color: #b3d9ff;
            }
            QTreeWidget::item:selected {
                background-color: #b3d9ff;
            }
        """)
        self.conn_tree.setIndentation(15)
        self.conn_tree.itemClicked.connect(self.on_connection_selected)
        self.conn_tree.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.conn_tree.customContextMenuRequested.connect(self.show_connection_context_menu)
        layout.addWidget(self.conn_tree)

        return panel

    def create_tables_panel(self) -> QWidget:
        """Create tables list panel"""
        panel = QWidget()
        panel.setObjectName("panel")

        layout = QVBoxLayout(panel)
        layout.setSpacing(8)

        # Header
        header = QLabel("TABLES")
        header.setObjectName("panel_header")
        layout.addWidget(header)

        # Search box
        self.table_search = QLineEdit()
        self.table_search.setPlaceholderText("Search tables...")
        self.table_search.textChanged.connect(self.filter_tables)
        layout.addWidget(self.table_search)

        # Tables tree with checkboxes
        self.tables_tree = QTreeWidget()
        self.tables_tree.setHeaderLabels(["Table Name"])
        self.tables_tree.setHeaderHidden(True)
        self.tables_tree.setStyleSheet("""
            QTreeWidget {
                background: white;
                border: 1px solid #ddd;
                border-radius: 4px;
            }
            QTreeWidget::item {
                height: 18px;
                padding: 0px 2px;
            }
            QTreeWidget::item:hover {
                background-color: #b3d9ff;
            }
            QTreeWidget::item:selected {
                background-color: #b3d9ff;
            }
        """)
        self.tables_tree.setIndentation(15)
        self.tables_tree.itemChanged.connect(self.on_table_checked)
        self.tables_tree.itemClicked.connect(self.on_table_selected)
        layout.addWidget(self.tables_tree)

        return panel

    def create_schema_panel(self) -> QWidget:
        """Create schema details panel"""
        panel = QWidget()
        panel.setObjectName("panel")

        layout = QVBoxLayout(panel)
        layout.setSpacing(8)

        # Header
        header = QLabel("SCHEMA DETAILS")
        header.setObjectName("panel_header")
        layout.addWidget(header)

        # Table info label
        self.table_info_label = QLabel("Select a table to view schema details")
        self.table_info_label.setStyleSheet("color: #D4AF37; padding: 10px;")
        layout.addWidget(self.table_info_label)

        # Schema table
        self.schema_table = QTableWidget()
        self.schema_table.setColumnCount(5)
        self.schema_table.setHorizontalHeaderLabels([
            "Column Name", "Data Type", "Nullable", "Primary Key", "Default"
        ])
        self.schema_table.horizontalHeader().setStretchLastSection(True)
        self.schema_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.schema_table.setAlternatingRowColors(True)
        layout.addWidget(self.schema_table)

        return panel

    def load_connections(self):
        """Load all connections into the tree, grouped by type"""
        self.conn_tree.clear()

        try:
            connections = self.conn_manager.get_connections()

            # Map connection types to display categories
            type_mapping = {
                'Local ODBC': 'SQL_SERVER',
                'DB2': 'DB2',
                'MS Access': 'ACCESS',
                'ACCESS': 'ACCESS',
                'Excel File': 'EXCEL',
                'EXCEL': 'EXCEL',
                'CSV File': 'CSV',
                'CSV': 'CSV',
                'Fixed Width File': 'FIXED_WIDTH',
                'FIXED_WIDTH': 'FIXED_WIDTH',
                'Mainframe FTP': 'MAINFRAME_FTP',
                'MAINFRAME_FTP': 'MAINFRAME_FTP'
            }

            # Group connections by normalized type (don't merge types)
            connections_by_type = {}
            for conn in connections:
                conn_type = conn['connection_type']
                
                # Normalize the connection type
                normalized_type = type_mapping.get(conn_type, conn_type)
                
                if normalized_type not in connections_by_type:
                    connections_by_type[normalized_type] = []
                connections_by_type[normalized_type].append(conn)

            # Define the display order
            type_order = ['DB2', 'SQL_SERVER', 'ACCESS', 'EXCEL', 'CSV', 'FIXED_WIDTH', 'MAINFRAME_FTP']
            
            # Add connection groups in the specified order
            for group_type in type_order:
                if group_type not in connections_by_type:
                    continue
                    
                group_conns = connections_by_type[group_type]
                
                # Create type group item at root level
                type_item = QTreeWidgetItem(self.conn_tree)
                type_item.setText(0, group_type)
                type_item.setData(0, Qt.ItemDataRole.UserRole + 1, "group")
                type_item.setExpanded(True)

                # Add connections under type
                for conn in sorted(group_conns, key=lambda x: x['connection_name']):
                    conn_item = QTreeWidgetItem(type_item)
                    conn_item.setText(0, conn['connection_name'])
                    conn_item.setData(0, Qt.ItemDataRole.UserRole, conn['connection_id'])
                    conn_item.setData(0, Qt.ItemDataRole.UserRole + 1, "connection")

            logger.info(f"Loaded {len(connections)} connections")

        except Exception as e:
            logger.error(f"Failed to load connections: {e}")
            QMessageBox.critical(self, "Error", f"Failed to load connections:\n{str(e)}")

    def on_connection_selected(self, item: QTreeWidgetItem, column: int):
        """Handle connection selection"""
        item_type = item.data(0, Qt.ItemDataRole.UserRole + 1)

        if item_type == "connection":
            connection_id = item.data(0, Qt.ItemDataRole.UserRole)
            self.current_connection_id = connection_id
            self.load_tables(connection_id)
            
            # Don't emit mainframe_connection_selected signal - we'll show datasets here
            # connection = self.conn_manager.repo.get_connection(connection_id)
            # if connection and connection.get('connection_type') == 'MAINFRAME_FTP':
            #     self.mainframe_connection_selected.emit(connection_id)

    def load_tables(self, connection_id: int):
        """Load tables for a connection"""
        self.tables_tree.clear()
        self.table_info_label.setText("Loading tables...")

        try:
            # Get connection info to check type
            connection = self.conn_manager.repo.get_connection(connection_id)
            if not connection:
                raise ValueError("Connection not found")
            
            conn_type = connection.get('connection_type', '')
            
            # Block signals while loading to prevent premature itemChanged events
            self.tables_tree.blockSignals(True)

            # Handle Mainframe FTP connections differently
            if conn_type == 'MAINFRAME_FTP':
                self.load_ftp_datasets(connection_id, connection)
            else:
                # Get tables from schema discovery for database connections
                tables = self.schema_discovery.get_tables(connection_id)

                # Get saved tables to show checkmarks
                saved_tables = self.saved_table_repo.get_saved_tables(connection_id)
                saved_table_names = {(st['schema_name'], st['table_name']) for st in saved_tables}

                # Add tables to tree
                for table in tables:
                    # Create item WITHOUT adding to tree yet
                    table_item = QTreeWidgetItem()

                    # Set text and data
                    table_item.setText(0, table['full_name'])
                    table_item.setData(0, Qt.ItemDataRole.UserRole, table['table_name'])
                    table_item.setData(0, Qt.ItemDataRole.UserRole + 1, table['schema_name'])

                    # Enable checkbox
                    table_item.setFlags(table_item.flags() | Qt.ItemFlag.ItemIsUserCheckable)

                    # Set initial check state
                    is_saved = (table['schema_name'], table['table_name']) in saved_table_names
                    table_item.setCheckState(0, Qt.CheckState.Checked if is_saved else Qt.CheckState.Unchecked)

                    # NOW add to tree (with all properties set)
                    self.tables_tree.addTopLevelItem(table_item)

                self.table_info_label.setText(f"Found {len(tables)} tables")
                logger.info(f"Loaded {len(tables)} tables for connection {connection_id}")

            # Re-enable signals after all items are loaded
            self.tables_tree.blockSignals(False)

        except Exception as e:
            logger.error(f"Failed to load tables: {e}")
            self.table_info_label.setText(f"Error loading tables: {str(e)}")
            
            # Re-enable signals even on error
            self.tables_tree.blockSignals(False)
            
            # Show a less intrusive error message for connection issues
            error_msg = str(e)
            if "ODBC Driver" in error_msg or "Data source name" in error_msg:
                self.table_info_label.setText(f"Connection error: ODBC driver or DSN not configured. Right-click to view/edit connection.")
                # Don't show popup for ODBC configuration issues - just show in label
                logger.warning(f"DB2/ODBC configuration issue for connection {connection_id}: {e}")
            else:
                # For other errors, show the popup
                QMessageBox.warning(self, "Error", f"Failed to load tables:\n{str(e)}")
    
    def load_ftp_datasets(self, connection_id: int, connection: dict):
        """Load datasets/members for FTP connection"""
        from suiteview.core.ftp_manager import MainframeFTPManager
        from suiteview.core.credential_manager import CredentialManager
        
        try:
            # Get FTP connection details
            cred_mgr = CredentialManager()
            
            # Parse connection string for details
            conn_string = connection.get('connection_string', '')
            ftp_params = {}
            for param in conn_string.split(';'):
                if '=' in param:
                    key, value = param.split('=', 1)
                    ftp_params[key] = value
            
            host = connection.get('server_name', '')
            port = int(ftp_params.get('port', 21))
            initial_path = ftp_params.get('initial_path', '')
            
            # Decrypt credentials
            encrypted_username = connection.get('encrypted_username')
            encrypted_password = connection.get('encrypted_password')
            username = cred_mgr.decrypt(encrypted_username) if encrypted_username else ''
            password = cred_mgr.decrypt(encrypted_password) if encrypted_password else ''
            
            # Connect to FTP
            self.table_info_label.setText("Connecting to mainframe...")
            ftp_mgr = MainframeFTPManager(host, username, password, port, initial_path)
            
            if not ftp_mgr.connect():
                raise ValueError("Failed to connect to FTP server")
            
            self.table_info_label.setText("Loading datasets...")
            
            # List all datasets in the initial path
            datasets = ftp_mgr.list_datasets(initial_path)
            ftp_mgr.disconnect()
            
            # Add datasets to tree
            for dataset_info in sorted(datasets, key=lambda x: x.get('name', '')):
                dataset_name = dataset_info.get('name', '')
                dataset_type = dataset_info.get('type', 'dataset')
                
                dataset_item = QTreeWidgetItem()
                dataset_item.setText(0, dataset_name)
                
                # Store full dataset path for loading later
                # For PDS members, use parentheses: D03.AA0139.CKAS(MEMBER)
                # For subdatasets, use dots: D03.AA0139.CKAS
                if initial_path:
                    full_path = f"{initial_path}({dataset_name})"
                else:
                    full_path = dataset_name
                    
                dataset_item.setData(0, Qt.ItemDataRole.UserRole, full_path)
                dataset_item.setData(0, Qt.ItemDataRole.UserRole + 1, "ftp_dataset")
                
                self.tables_tree.addTopLevelItem(dataset_item)
            
            self.table_info_label.setText(f"Found {len(datasets)} datasets")
            logger.info(f"Loaded {len(datasets)} FTP datasets from {initial_path}")
            
        except Exception as e:
            logger.error(f"Error loading FTP datasets: {str(e)}")
            self.table_info_label.setText(f"Error: {str(e)}")
            
            # Show friendly error in table
            error_item = QTreeWidgetItem()
            error_item.setText(0, f"❌ Error: {str(e)}")
            error_item.setForeground(0, self.palette().color(self.palette().ColorRole.PlaceholderText))
            self.tables_tree.addTopLevelItem(error_item)
        finally:
            self.tables_tree.blockSignals(False)

    def filter_tables(self, search_text: str):
        """Filter tables based on search text"""
        search_text = search_text.lower()

        for i in range(self.tables_tree.topLevelItemCount()):
            item = self.tables_tree.topLevelItem(i)
            table_name = item.text(0).lower()
            item.setHidden(search_text not in table_name)

    def on_table_checked(self, item: QTreeWidgetItem, column: int):
        """Handle table checkbox change"""
        if self.current_connection_id is None:
            return

        table_name = item.data(0, Qt.ItemDataRole.UserRole)
        schema_name = item.data(0, Qt.ItemDataRole.UserRole + 1)

        # Skip if table_name is None (happens during initialization)
        if table_name is None:
            logger.debug("Skipping checkbox event - table_name is None")
            return

        is_checked = item.checkState(0) == Qt.CheckState.Checked

        try:
            if is_checked:
                # Save table to My Data
                self.saved_table_repo.save_table(
                    self.current_connection_id,
                    table_name,
                    schema_name
                )
                logger.info(f"Saved table {table_name} to My Data")
            else:
                # Remove table from My Data
                self.saved_table_repo.remove_table(
                    self.current_connection_id,
                    table_name,
                    schema_name
                )
                logger.info(f"Removed table {table_name} from My Data")

            # Emit signal to refresh My Data screen
            self.saved_tables_changed.emit()

        except Exception as e:
            logger.error(f"Failed to update saved table: {e}")
            QMessageBox.warning(self, "Error", f"Failed to update saved table:\n{str(e)}")

    def on_table_selected(self, item: QTreeWidgetItem, column: int):
        """Handle table selection to show schema"""
        if self.current_connection_id is None:
            return

        table_name = item.data(0, Qt.ItemDataRole.UserRole)
        schema_name = item.data(0, Qt.ItemDataRole.UserRole + 1)

        # Skip if we're already showing this table (prevents unnecessary reloads)
        if self.current_table == table_name and self.current_schema == schema_name:
            return

        self.current_table = table_name
        self.current_schema = schema_name

        self.load_schema(self.current_connection_id, table_name, schema_name)

    def load_schema(self, connection_id: int, table_name: str, schema_name: str = None):
        """Load schema details for a table"""
        self.schema_table.setRowCount(0)

        try:
            # Get connection info to check type
            connection = self.conn_manager.repo.get_connection(connection_id)
            if not connection:
                raise ValueError("Connection not found")
            
            conn_type = connection.get('connection_type', '')
            
            # Handle FTP datasets differently
            if conn_type == 'MAINFRAME_FTP':
                self.load_ftp_dataset_preview(connection, table_name)
            else:
                # Show schema table and hide FTP text viewer for database tables
                self.schema_table.setVisible(True)
                if hasattr(self, 'ftp_text_viewer'):
                    self.ftp_text_viewer.setVisible(False)
                if hasattr(self, 'ftp_button_bar'):
                    self.ftp_button_bar.setVisible(False)
                
                # Reset to 5 columns for database tables
                self.schema_table.setColumnCount(5)
                self.schema_table.setHorizontalHeaderLabels(["Column Name", "Data Type", "Nullable", "Primary Key", "Default"])
                
                # Get columns from schema discovery for database connections
                columns = self.schema_discovery.get_columns(connection_id, table_name, schema_name)

                # Display in table
                self.schema_table.setRowCount(len(columns))

                for row, col_info in enumerate(columns):
                    # Column name
                    self.schema_table.setItem(row, 0, QTableWidgetItem(col_info['column_name']))

                    # Data type
                    self.schema_table.setItem(row, 1, QTableWidgetItem(col_info['data_type']))

                    # Nullable
                    nullable_text = "Yes" if col_info['is_nullable'] else "No"
                    nullable_item = QTableWidgetItem(nullable_text)
                    if not col_info['is_nullable']:
                        nullable_item.setForeground(Qt.GlobalColor.yellow)
                    self.schema_table.setItem(row, 2, nullable_item)

                    # Primary key
                    pk_text = "Yes" if col_info['is_primary_key'] else "No"
                    pk_item = QTableWidgetItem(pk_text)
                    if col_info['is_primary_key']:
                        pk_item.setForeground(Qt.GlobalColor.yellow)
                    self.schema_table.setItem(row, 3, pk_item)

                    # Default
                    default_val = col_info.get('default', '')
                    self.schema_table.setItem(row, 4, QTableWidgetItem(str(default_val) if default_val else ""))

                full_name = f"{schema_name}.{table_name}" if schema_name else table_name
                self.table_info_label.setText(f"Table: {full_name} ({len(columns)} columns)")

                logger.info(f"Loaded schema for {full_name}")

        except Exception as e:
            logger.error(f"Failed to load schema: {e}")
            self.table_info_label.setText(f"Error loading schema: {str(e)}")
            QMessageBox.warning(self, "Error", f"Failed to load schema:\n{str(e)}")
    
    def load_ftp_dataset_preview(self, connection: dict, dataset_name: str):
        """Load preview of FTP dataset - show first 2000 lines in text viewer"""
        from suiteview.core.ftp_manager import MainframeFTPManager
        from suiteview.core.credential_manager import CredentialManager
        
        try:
            # Store connection info for View All button
            self.current_ftp_connection = connection
            self.current_ftp_dataset = dataset_name
            
            # Get FTP connection details
            cred_mgr = CredentialManager()
            
            # Parse connection string for details
            conn_string = connection.get('connection_string', '')
            ftp_params = {}
            for param in conn_string.split(';'):
                if '=' in param:
                    key, value = param.split('=', 1)
                    ftp_params[key] = value
            
            host = connection.get('server_name', '')
            port = int(ftp_params.get('port', 21))
            initial_path = ftp_params.get('initial_path', '')
            
            # Decrypt credentials
            encrypted_username = connection.get('encrypted_username')
            encrypted_password = connection.get('encrypted_password')
            username = cred_mgr.decrypt(encrypted_username) if encrypted_username else ''
            password = cred_mgr.decrypt(encrypted_password) if encrypted_password else ''
            
            # Connect and read dataset preview
            ftp_mgr = MainframeFTPManager(host, username, password, port, initial_path)
            if not ftp_mgr.connect():
                raise ValueError("Failed to connect to FTP server")
            
            # Read all lines
            content, total_lines = ftp_mgr.read_dataset(dataset_name, max_lines=1000)
            ftp_mgr.disconnect()
            
            # Store content for export button
            self.current_ftp_content = content
            
            # Hide the schema table and show text viewer instead
            self.schema_table.setVisible(False)
            
            # Create or update text viewer for FTP datasets
            if not hasattr(self, 'ftp_text_viewer'):
                self.ftp_text_viewer = QTextEdit()
                self.ftp_text_viewer.setReadOnly(True)
                self.ftp_text_viewer.setFont(QFont("Courier New", 10))
                self.ftp_text_viewer.setLineWrapMode(QTextEdit.LineWrapMode.NoWrap)
                
                # Add to the same layout as schema_table
                schema_panel = self.schema_table.parent()
                if schema_panel and hasattr(schema_panel, 'layout'):
                    layout = schema_panel.layout()
                    if layout:
                        # Add text viewer to layout
                        layout.addWidget(self.ftp_text_viewer)
            
            # Show text viewer and populate with content
            self.ftp_text_viewer.setVisible(True)
            self.ftp_text_viewer.setPlainText(content)
            
            # Update info label
            self.table_info_label.setText(
                f"Dataset: {dataset_name} - Showing {min(1000, total_lines)} of {total_lines} lines (80-byte card format)"
            )
            
            # Create button bar if it doesn't exist
            if not hasattr(self, 'ftp_button_bar'):
                self.ftp_button_bar = QWidget()
                button_layout = QHBoxLayout(self.ftp_button_bar)
                button_layout.setContentsMargins(0, 0, 0, 0)
                
                # View All button (left, smaller)
                self.view_all_btn = QPushButton("📄 View All")
                self.view_all_btn.setObjectName("gold_button")
                self.view_all_btn.setMaximumWidth(100)
                self.view_all_btn.clicked.connect(self._view_all_ftp_dataset)
                button_layout.addWidget(self.view_all_btn)
                
                # Spacer
                button_layout.addStretch()
                
                # Export button (right)
                self.export_btn = QPushButton("💾 Export")
                self.export_btn.setObjectName("gold_button")
                self.export_btn.setMaximumWidth(120)
                self.export_btn.clicked.connect(self._export_current_ftp_dataset)
                button_layout.addWidget(self.export_btn)
                
                # Add button bar to layout (after info label)
                schema_panel = self.schema_table.parent()
                if schema_panel and hasattr(schema_panel, 'layout'):
                    layout = schema_panel.layout()
                    if layout:
                        layout.insertWidget(2, self.ftp_button_bar)
            
            # Show button bar
            self.ftp_button_bar.setVisible(True)
            
            logger.info(f"Loaded preview for FTP dataset {dataset_name} ({total_lines} lines)")
            
        except Exception as e:
            logger.error(f"Failed to load FTP dataset preview: {e}")
            # Show schema table again on error
            self.schema_table.setVisible(True)
            if hasattr(self, 'ftp_text_viewer'):
                self.ftp_text_viewer.setVisible(False)
            if hasattr(self, 'ftp_button_bar'):
                self.ftp_button_bar.setVisible(False)
            raise
    
    def _view_all_ftp_dataset(self):
        """Open dialog to view complete FTP dataset"""
        if not hasattr(self, 'current_ftp_dataset'):
            return
        
        from PyQt6.QtWidgets import QDialog, QVBoxLayout, QTextEdit, QHBoxLayout, QPushButton, QFileDialog
        from suiteview.core.ftp_manager import MainframeFTPManager
        from suiteview.core.credential_manager import CredentialManager
        
        try:
            # Create dialog
            dialog = QDialog(self)
            dialog.setWindowTitle(f"View Dataset: {self.current_ftp_dataset}")
            dialog.setMinimumSize(1000, 600)
            
            layout = QVBoxLayout(dialog)
            
            # Text display
            text_edit = QTextEdit()
            text_edit.setReadOnly(True)
            text_edit.setFont(QFont("Courier New", 10))
            text_edit.setLineWrapMode(QTextEdit.LineWrapMode.NoWrap)
            layout.addWidget(text_edit)
            
            # Get FTP connection details
            cred_mgr = CredentialManager()
            connection = self.current_ftp_connection
            
            conn_string = connection.get('connection_string', '')
            ftp_params = {}
            for param in conn_string.split(';'):
                if '=' in param:
                    key, value = param.split('=', 1)
                    ftp_params[key] = value
            
            host = connection.get('server_name', '')
            port = int(ftp_params.get('port', 21))
            initial_path = ftp_params.get('initial_path', '')
            
            encrypted_username = connection.get('encrypted_username')
            encrypted_password = connection.get('encrypted_password')
            username = cred_mgr.decrypt(encrypted_username) if encrypted_username else ''
            password = cred_mgr.decrypt(encrypted_password) if encrypted_password else ''
            
            # Connect and read full dataset
            ftp_mgr = MainframeFTPManager(host, username, password, port, initial_path)
            if not ftp_mgr.connect():
                raise ValueError("Failed to connect to FTP server")
            
            # Read all lines (no limit)
            content, total_lines = ftp_mgr.read_dataset(self.current_ftp_dataset, max_lines=None)
            ftp_mgr.disconnect()
            
            # Display content
            text_edit.setPlainText(content)
            
            # Button bar
            button_layout = QHBoxLayout()
            
            # Export button
            export_btn = QPushButton("💾 Export to Text File")
            export_btn.setObjectName("gold_button")
            export_btn.clicked.connect(lambda: self._export_ftp_dataset(content))
            button_layout.addWidget(export_btn)
            
            button_layout.addStretch()
            
            # Close button
            close_btn = QPushButton("Close")
            close_btn.clicked.connect(dialog.close)
            button_layout.addWidget(close_btn)
            
            layout.addLayout(button_layout)
            
            # Show info
            text_edit.append(f"\n\n--- {total_lines} lines total ---")
            
            dialog.exec()
            
        except Exception as e:
            logger.error(f"Failed to view complete dataset: {e}")
            QMessageBox.critical(self, "Error", f"Failed to load complete dataset:\n{str(e)}")
    
    def _export_ftp_dataset(self, content: str):
        """Export FTP dataset content to text file"""
        try:
            # Ask user where to save
            file_path, _ = QFileDialog.getSaveFileName(
                self,
                "Export Dataset",
                f"{self.current_ftp_dataset}.txt",
                "Text Files (*.txt);;All Files (*.*)"
            )
            
            if file_path:
                with open(file_path, 'w', encoding='utf-8') as f:
                    f.write(content)
                
                QMessageBox.information(
                    self,
                    "Export Success",
                    f"Dataset exported successfully to:\n{file_path}"
                )
                logger.info(f"Exported FTP dataset to {file_path}")
        
        except Exception as e:
            logger.error(f"Failed to export dataset: {e}")
            QMessageBox.critical(self, "Export Failed", f"Failed to export dataset:\n{str(e)}")
    
    def _export_current_ftp_dataset(self):
        """Export currently displayed FTP dataset preview to text file"""
        if not hasattr(self, 'current_ftp_content') or not hasattr(self, 'current_ftp_dataset'):
            return
        
        try:
            # Ask user where to save
            file_path, _ = QFileDialog.getSaveFileName(
                self,
                "Export Dataset Preview",
                f"{self.current_ftp_dataset}.txt",
                "Text Files (*.txt);;All Files (*.*)"
            )
            
            if file_path:
                with open(file_path, 'w', encoding='utf-8') as f:
                    f.write(self.current_ftp_content)
                
                QMessageBox.information(
                    self,
                    "Export Success",
                    f"Dataset preview exported successfully to:\n{file_path}"
                )
                logger.info(f"Exported FTP dataset preview to {file_path}")
        
        except Exception as e:
            logger.error(f"Failed to export dataset preview: {e}")
            QMessageBox.critical(self, "Export Failed", f"Failed to export dataset:\n{str(e)}")

    def add_connection(self):
        """Show add connection dialog"""
        dialog = AddConnectionDialog(self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            conn_data = dialog.get_connection_data()
            if conn_data:
                try:
                    conn_type = conn_data['connection_type']
                    conn_name = conn_data['connection_name']

                    # Map dialog types to storage types
                    type_storage_map = {
                        "Excel File": "EXCEL",
                        "MS Access": "ACCESS",
                        "CSV File": "CSV",
                        "Fixed Width File": "FIXED_WIDTH",
                        "Mainframe FTP": "MAINFRAME_FTP",
                        "SQL Server": "SQL_SERVER",
                        "Local ODBC": None  # Will determine based on database_type
                    }

                    # Handle file-based connections (Excel, CSV, Access, Fixed Width)
                    if conn_type in ["Excel File", "MS Access", "CSV File", "Fixed Width File"]:
                        # For file-based connections, store file path in connection_string
                        file_path = conn_data.get('file_path', '')
                        
                        # Convert to standardized storage type
                        storage_type = type_storage_map[conn_type]

                        connection_id = self.conn_manager.repo.create_connection(
                            connection_name=conn_name,
                            connection_type=storage_type,  # Store standardized type: EXCEL, ACCESS, CSV, FIXED_WIDTH
                            server_name='',
                            database_name=conn_data.get('filename', ''),
                            auth_type='NONE',
                            encrypted_username=None,
                            encrypted_password=None,
                            connection_string=file_path
                        )

                        logger.info(f"Added file-based connection: {conn_name} (ID: {connection_id})")

                    elif conn_type == "Local ODBC":
                        # Handle ODBC connections - determine if SQL_SERVER or DB2
                        dsn = conn_data.get('dsn', '')
                        db_type = conn_data.get('database_type', 'SQL')

                        # Map database_type to storage type
                        storage_type = 'DB2' if db_type == 'DB2' else 'SQL_SERVER'

                        connection_id = self.conn_manager.repo.create_connection(
                            connection_name=conn_name,
                            connection_type=storage_type,  # Store as SQL_SERVER or DB2
                            server_name=dsn,
                            database_name=dsn,
                            auth_type='WINDOWS',  # ODBC typically uses Windows auth
                            encrypted_username=None,
                            encrypted_password=None,
                            connection_string=f"DSN={dsn}"
                        )

                        logger.info(f"Added ODBC connection: {conn_name} (ID: {connection_id})")

                    elif conn_type == "SQL Server":
                        # Handle direct SQL Server connections
                        from suiteview.core.credential_manager import CredentialManager
                        
                        server = conn_data.get('server', '')
                        database = conn_data.get('database', 'master')
                        auth_type = conn_data.get('auth_type', 'Windows')
                        
                        # Build connection string based on authentication type
                        if auth_type == 'Windows':
                            conn_string = f"DRIVER={{ODBC Driver 17 for SQL Server}};SERVER={server};DATABASE={database};Trusted_Connection=yes"
                            encrypted_username = None
                            encrypted_password = None
                        else:  # SQL Server Authentication
                            username = conn_data.get('username', '')
                            password = conn_data.get('password', '')
                            
                            # Encrypt credentials
                            cred_mgr = CredentialManager()
                            encrypted_username = cred_mgr.encrypt(username)
                            encrypted_password = cred_mgr.encrypt(password)
                            
                            conn_string = f"DRIVER={{ODBC Driver 17 for SQL Server}};SERVER={server};DATABASE={database};UID={username};PWD={password}"
                        
                        connection_id = self.conn_manager.repo.create_connection(
                            connection_name=conn_name,
                            connection_type="SQL_SERVER",
                            server_name=server,
                            database_name=database,
                            auth_type=auth_type.upper(),
                            encrypted_username=encrypted_username,
                            encrypted_password=encrypted_password,
                            connection_string=conn_string
                        )
                        
                        logger.info(f"Added SQL Server connection: {conn_name} (ID: {connection_id})")

                    elif conn_type == "Mainframe FTP":
                        # Handle Mainframe FTP connections
                        from suiteview.core.credential_manager import CredentialManager
                        
                        ftp_host = conn_data.get('ftp_host', '')
                        ftp_port = conn_data.get('ftp_port', 21)
                        ftp_username = conn_data.get('ftp_username', '')
                        ftp_password = conn_data.get('ftp_password', '')
                        ftp_initial_path = conn_data.get('ftp_initial_path', '')
                        
                        # Encrypt credentials
                        cred_mgr = CredentialManager()
                        encrypted_username = cred_mgr.encrypt(ftp_username)
                        encrypted_password = cred_mgr.encrypt(ftp_password)
                        
                        # Build connection string with FTP details
                        conn_string = f"host={ftp_host};port={ftp_port};initial_path={ftp_initial_path}"
                        
                        connection_id = self.conn_manager.repo.create_connection(
                            connection_name=conn_name,
                            connection_type="MAINFRAME_FTP",
                            server_name=ftp_host,
                            database_name=ftp_initial_path,
                            auth_type='PASSWORD',
                            encrypted_username=encrypted_username,
                            encrypted_password=encrypted_password,
                            connection_string=conn_string
                        )
                        
                        logger.info(f"Added Mainframe FTP connection: {conn_name} (ID: {connection_id})")

                    # Reload connections tree
                    self.load_connections()
                    
                    # Emit signal so other screens can refresh
                    self.connections_changed.emit()

                    QMessageBox.information(
                        self,
                        "Connection Saved",
                        f"Connection '{conn_name}' saved successfully!"
                    )

                except Exception as e:
                    logger.error(f"Failed to save connection: {e}", exc_info=True)
                    QMessageBox.critical(self, "Error", f"Failed to save connection:\n{str(e)}")

    def test_connection(self):
        """Test the selected connection"""
        if self.current_connection_id is None:
            QMessageBox.information(self, "No Connection", "Please select a connection to test")
            return

        try:
            success, message = self.conn_manager.test_connection(self.current_connection_id)

            if success:
                QMessageBox.information(self, "Connection Test", message)
            else:
                QMessageBox.warning(self, "Connection Test Failed", message)

        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to test connection:\n{str(e)}")

    def refresh_metadata(self):
        """Refresh metadata for selected connection"""
        if self.current_connection_id is None:
            QMessageBox.information(self, "No Connection", "Please select a connection to refresh")
            return

        try:
            self.schema_discovery.refresh_metadata(self.current_connection_id)
            self.load_tables(self.current_connection_id)
            QMessageBox.information(self, "Success", "Metadata refreshed successfully!")

        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to refresh metadata:\n{str(e)}")

    def delete_connection(self):
        """Delete the selected connection"""
        if self.current_connection_id is None:
            QMessageBox.information(self, "No Connection", "Please select a connection to delete")
            return

        # Confirm deletion
        connection = self.conn_manager.get_connection(self.current_connection_id)
        if not connection:
            return

        reply = QMessageBox.question(
            self,
            "Confirm Deletion",
            f"Are you sure you want to delete connection '{connection['connection_name']}'?\n\n"
            "This will also remove all saved tables and queries associated with this connection.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No
        )

        if reply == QMessageBox.StandardButton.Yes:
            try:
                self.conn_manager.delete_connection(self.current_connection_id)
                self.current_connection_id = None
                self.load_connections()
                self.tables_tree.clear()
                self.schema_table.setRowCount(0)
                self.table_info_label.setText("Connection deleted")
                
                # Emit signal so other screens can refresh
                self.connections_changed.emit()
                
                QMessageBox.information(self, "Success", "Connection deleted successfully!")

            except Exception as e:
                QMessageBox.critical(self, "Error", f"Failed to delete connection:\n{str(e)}")

    def show_connection_context_menu(self, position: QPoint):
        """Show context menu for connection item"""
        item = self.conn_tree.itemAt(position)
        if not item:
            return

        item_type = item.data(0, Qt.ItemDataRole.UserRole + 1)
        if item_type != "connection":
            return

        # Get the connection_id from the clicked item (stored in UserRole, not UserRole+2)
        connection_id = item.data(0, Qt.ItemDataRole.UserRole)
        
        if connection_id is None:
            logger.warning("Right-clicked connection has no connection_id")
            return
        
        # Create context menu
        menu = QMenu(self)
        view_action = menu.addAction("View")
        delete_action = menu.addAction("Delete")

        # Show menu and get selected action
        action = menu.exec(self.conn_tree.mapToGlobal(position))

        if action == view_action:
            # View connection without changing current selection
            self.view_connection(connection_id)
        elif action == delete_action:
            # For delete, we need to set it as current and call delete
            temp_current = self.current_connection_id  # Save current selection
            self.current_connection_id = connection_id
            self.delete_connection()
            self.current_connection_id = temp_current  # Restore selection
    
    def view_connection(self, connection_id: int = None):
        """View/Edit the selected connection"""
        # Use provided connection_id or fall back to current
        conn_id = connection_id if connection_id is not None else self.current_connection_id
        
        if conn_id is None:
            QMessageBox.information(self, "No Connection", "Please select a connection to view")
            return

        try:
            # Get existing connection data
            connection = self.conn_manager.repo.get_connection(conn_id)
            if not connection:
                QMessageBox.warning(self, "Error", "Connection not found")
                return

            # Open the view connection dialog
            from suiteview.ui.dialogs.view_connection_dialog import ViewConnectionDialog
            dialog = ViewConnectionDialog(self, connection_data=connection)
            
            if dialog.exec() == QDialog.DialogCode.Accepted:
                # Refresh the connections list if changes were saved
                self.load_connections()
                # Emit signal to notify other screens
                self.connections_changed.emit()
                logger.info("Connection updated, refreshing display")
            
        except Exception as e:
            logger.error(f"Failed to open view connection dialog: {e}")
            QMessageBox.critical(self, "Error", f"Failed to view connection:\n{str(e)}")

    def edit_connection(self):
        """Edit the selected connection"""
        if self.current_connection_id is None:
            QMessageBox.information(self, "No Connection", "Please select a connection to edit")
            return

        try:
            # Get existing connection data
            connection = self.conn_manager.get_connection(self.current_connection_id)
            if not connection:
                QMessageBox.warning(self, "Error", "Connection not found")
                return

            # Open the connection dialog with existing data pre-populated
            dialog = AddConnectionDialog(self, connection_data=connection)
            
            if dialog.exec() == QDialog.DialogCode.Accepted:
                # Get the updated connection data from the dialog
                updated_data = dialog.get_connection_data()
                
                # Map dialog types to storage types
                type_storage_map = {
                    "Excel File": "EXCEL",
                    "MS Access": "ACCESS",
                    "CSV File": "CSV",
                    "Fixed Width File": "FIXED_WIDTH",
                    "Local ODBC": None  # Will determine based on database_type
                }
                
                conn_type = updated_data['connection_type']
                
                # Convert dialog type to storage type
                if conn_type in type_storage_map and type_storage_map[conn_type]:
                    storage_type = type_storage_map[conn_type]
                elif conn_type == "Local ODBC":
                    # Determine SQL_SERVER vs DB2 based on database_type
                    db_type = updated_data.get('database_type', 'SQL')
                    storage_type = 'DB2' if db_type == 'DB2' else 'SQL_SERVER'
                else:
                    # Already a storage type (editing existing)
                    storage_type = conn_type
                
                # For file-based connections, store file_path in connection_string
                conn_string = updated_data.get('connection_string', '')
                if 'file_path' in updated_data and updated_data['file_path']:
                    conn_string = updated_data['file_path']
                
                # For ODBC connections, build connection string from DSN
                if 'dsn' in updated_data and updated_data['dsn']:
                    conn_string = f"DSN={updated_data['dsn']}"
                
                # Update the connection in the database
                self.conn_manager.update_connection(
                    self.current_connection_id,
                    connection_name=updated_data['connection_name'],
                    connection_type=storage_type,  # Use standardized storage type
                    connection_string=conn_string,
                    server_name=updated_data.get('server', ''),
                    database_name=updated_data.get('database_name', ''),
                    username=updated_data.get('username', ''),
                    password=updated_data.get('password', '')
                )
                
                # Reload connections
                self.load_connections()
                
                # Emit signal so other screens can refresh
                self.connections_changed.emit()
                
                QMessageBox.information(
                    self,
                    "Success",
                    f"Connection '{updated_data['connection_name']}' updated successfully"
                )
                logger.info(f"Updated connection {self.current_connection_id}")

        except Exception as e:
            logger.error(f"Failed to edit connection: {e}", exc_info=True)
            QMessageBox.critical(self, "Error", f"Failed to edit connection:\n{str(e)}")
