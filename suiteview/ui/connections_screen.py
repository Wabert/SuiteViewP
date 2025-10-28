"""Connections Screen - Manage database connections"""

import logging
from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel, QSplitter,
                              QTreeWidget, QTreeWidgetItem, QLineEdit, QToolBar,
                              QPushButton, QTableWidget, QTableWidgetItem, QMessageBox,
                              QHeaderView, QCheckBox, QMenu, QDialog)
from PyQt6.QtCore import Qt, pyqtSignal, QThread, QPoint
from PyQt6.QtGui import QIcon, QAction, QCursor

from suiteview.core.connection_manager import get_connection_manager
from suiteview.core.schema_discovery import get_schema_discovery
from suiteview.data.repositories import get_saved_table_repository
from suiteview.ui.dialogs.add_connection_dialog_v2 import AddConnectionDialog

logger = logging.getLogger(__name__)


class ConnectionsScreen(QWidget):
    """Connections screen with three-panel layout"""

    # Signal emitted when saved tables change (so My Data can refresh)
    saved_tables_changed = pyqtSignal()

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

        header_label = QLabel("CONNECTIONS")
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

            # Group connections by type
            type_groups = {
                'ODBC': [],
                'SQL_SERVER': [],
                'DB2': [],
                'EXCEL': [],
                'ACCESS': [],
                'CSV': [],
                'FIXED_WIDTH': []
            }

            # Map connection types to display names
            type_display_names = {
                'ODBC': 'ODBC',
                'SQL_SERVER': 'ODBC',  # SQL Server typically accessed via ODBC
                'DB2': 'ODBC',  # DB2 typically accessed via ODBC
                'EXCEL': 'Excel',
                'ACCESS': 'MS Access',
                'CSV': 'CSV',
                'FIXED_WIDTH': 'Fixed Width File'
            }

            # Group connections
            for conn in connections:
                conn_type = conn['connection_type']
                if conn_type in type_groups:
                    type_groups[conn_type].append(conn)

            # Create tree structure with groups
            for group_type, group_conns in type_groups.items():
                if not group_conns:
                    continue  # Skip empty groups

                # Create group header
                display_name = type_display_names.get(group_type, group_type)

                # For ODBC group, combine SQL_SERVER and DB2
                if group_type == 'ODBC':
                    combined_conns = (type_groups.get('ODBC', []) +
                                    type_groups.get('SQL_SERVER', []) +
                                    type_groups.get('DB2', []))
                    if not combined_conns:
                        continue
                    group_conns = combined_conns
                elif group_type in ['SQL_SERVER', 'DB2']:
                    continue  # Already handled in ODBC group

                group_item = QTreeWidgetItem(self.conn_tree)
                group_item.setText(0, display_name)
                group_item.setData(0, Qt.ItemDataRole.UserRole + 1, "group")
                group_item.setExpanded(True)

                # Add connections to group
                for conn in group_conns:
                    conn_item = QTreeWidgetItem(group_item)
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

    def load_tables(self, connection_id: int):
        """Load tables for a connection"""
        self.tables_tree.clear()
        self.table_info_label.setText("Loading tables...")

        try:
            # Block signals while loading to prevent premature itemChanged events
            self.tables_tree.blockSignals(True)

            # Get tables from schema discovery
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

            # Re-enable signals after all items are loaded
            self.tables_tree.blockSignals(False)

            self.table_info_label.setText(f"Found {len(tables)} tables")
            logger.info(f"Loaded {len(tables)} tables for connection {connection_id}")

        except Exception as e:
            logger.error(f"Failed to load tables: {e}")
            self.table_info_label.setText(f"Error loading tables: {str(e)}")
            QMessageBox.warning(self, "Error", f"Failed to load tables:\n{str(e)}")

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
            # Get columns
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

    def add_connection(self):
        """Show add connection dialog"""
        dialog = AddConnectionDialog(self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            conn_data = dialog.get_connection_data()
            if conn_data:
                try:
                    conn_type = conn_data['connection_type']
                    conn_name = conn_data['connection_name']

                    # Handle file-based connections (Excel, CSV, Access, Fixed Width)
                    if conn_type in ["Excel File", "MS Access", "CSV File", "Fixed Width File"]:
                        # For file-based connections, store file path in connection_string
                        file_path = conn_data.get('file_path', '')

                        # Map dialog connection types to database connection types
                        type_mapping = {
                            "Excel File": "EXCEL",
                            "MS Access": "ACCESS",
                            "CSV File": "CSV",
                            "Fixed Width File": "FIXED_WIDTH"
                        }
                        db_conn_type = type_mapping.get(conn_type, conn_type)

                        # Save to database via repository
                        connection_id = self.conn_manager.repo.create_connection(
                            connection_name=conn_name,
                            connection_type=db_conn_type,
                            server_name='',
                            database_name=conn_data.get('filename', ''),
                            auth_type='NONE',
                            encrypted_username=None,
                            encrypted_password=None,
                            connection_string=file_path
                        )

                        logger.info(f"Added file-based connection: {conn_name} (ID: {connection_id})")

                    elif conn_type == "Local ODBC":
                        # Handle ODBC connections
                        dsn = conn_data.get('dsn', '')
                        db_type = conn_data.get('database_type', 'SQL')

                        # Map database type to connection type
                        type_mapping = {
                            'SQL': 'SQL_SERVER',
                            'DB2': 'DB2'
                        }
                        db_conn_type = type_mapping.get(db_type, 'ODBC')

                        # Save ODBC connection
                        connection_id = self.conn_manager.repo.create_connection(
                            connection_name=conn_name,
                            connection_type=db_conn_type,
                            server_name=dsn,
                            database_name=dsn,
                            auth_type='WINDOWS',  # ODBC typically uses Windows auth
                            encrypted_username=None,
                            encrypted_password=None,
                            connection_string=f"DSN={dsn}"
                        )

                        logger.info(f"Added ODBC connection: {conn_name} (ID: {connection_id})")

                    # Reload connections tree
                    self.load_connections()

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

        # Create context menu
        menu = QMenu(self)
        edit_action = menu.addAction("Edit")
        delete_action = menu.addAction("Delete")

        # Show menu and get selected action
        action = menu.exec(self.conn_tree.mapToGlobal(position))

        if action == edit_action:
            self.edit_connection()
        elif action == delete_action:
            self.delete_connection()

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

            # For now, show connection details and allow renaming
            from PyQt6.QtWidgets import QInputDialog

            new_name, ok = QInputDialog.getText(
                self,
                "Edit Connection",
                f"Edit connection name:\n(Type: {connection['connection_type']})",
                QLineEdit.EchoMode.Normal,
                connection['connection_name']
            )

            if ok and new_name and new_name != connection['connection_name']:
                # Update connection name
                self.conn_manager.update_connection(
                    self.current_connection_id,
                    connection_name=new_name
                )
                self.load_connections()
                QMessageBox.information(
                    self,
                    "Success",
                    f"Connection renamed to '{new_name}'"
                )
                logger.info(f"Renamed connection {self.current_connection_id} to '{new_name}'")

        except Exception as e:
            logger.error(f"Failed to edit connection: {e}", exc_info=True)
            QMessageBox.critical(self, "Error", f"Failed to edit connection:\n{str(e)}")
