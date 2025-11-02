"""
Add Connection Dialog - Multi-type connection configuration
Professional data tool paradigm - maximum information density
"""

import os
from typing import Optional, Dict, Any

try:
    import pyodbc
    PYODBC_AVAILABLE = True
except ImportError:
    PYODBC_AVAILABLE = False
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QGridLayout, QLabel, QLineEdit,
    QComboBox, QPushButton, QFileDialog, QCheckBox, QMessageBox,
    QListWidget, QGroupBox, QTableWidget, QTableWidgetItem, QHeaderView,
    QWidget
)
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QFont


class AddConnectionDialog(QDialog):
    """
    Unified connection dialog for all connection types.
    Follows data tool paradigm - professional, efficient, no wasted space.
    """

    CONNECTION_TYPES = [
        "Local ODBC",
        "SQL Server",
        "Excel File",
        "MS Access",
        "CSV File",
        "Fixed Width File",
        "Mainframe FTP"
    ]

    def __init__(self, parent=None, connection_data=None):
        super().__init__(parent)
        self.connection_data = None
        self.edit_mode = connection_data is not None
        self.existing_connection = connection_data

        # Set window flags to make it a proper dialog
        from PyQt6.QtCore import Qt
        self.setWindowFlags(Qt.WindowType.Dialog | Qt.WindowType.WindowCloseButtonHint)
        self.setModal(True)  # Make it modal so it blocks parent

        self.init_ui()
        self.setMinimumWidth(700)
        self.setMinimumHeight(500)
        
        # If editing, populate the form with existing data
        if self.edit_mode:
            self.populate_form_with_existing_data()

    def init_ui(self):
        """Initialize the UI - stable layout, no expanding/collapsing"""
        window_title = "Edit Connection" if self.edit_mode else "Add New Connection"
        self.setWindowTitle(window_title)

        layout = QVBoxLayout(self)
        layout.setSpacing(0)
        layout.setContentsMargins(0, 0, 0, 0)

        # Title bar with blue gradient
        title_bar = QWidget()
        title_bar.setObjectName("dialog_title_bar")
        title_bar.setMaximumHeight(50)  # Limit title bar height
        title_bar_layout = QHBoxLayout(title_bar)
        title_bar_layout.setContentsMargins(15, 10, 15, 10)

        title_text = "Edit Connection" if self.edit_mode else "Add New Connection"
        title_label = QLabel(title_text)
        title_label.setObjectName("dialog_title")
        title_label.setStyleSheet("""
            QLabel#dialog_title {
                color: #FFD700;
                font-size: 14px;
                font-weight: 800;
                background: transparent;
                border: none;
            }
        """)
        title_bar_layout.addWidget(title_label)
        title_bar_layout.addStretch()

        layout.addWidget(title_bar)

        # Content area
        content_widget = QWidget()
        content_layout = QVBoxLayout(content_widget)
        content_layout.setSpacing(8)
        content_layout.setContentsMargins(12, 8, 12, 12)

        # Connection Type ribbon at top
        type_ribbon = QWidget()
        type_ribbon.setObjectName("type_ribbon")
        type_ribbon_layout = QHBoxLayout(type_ribbon)
        type_ribbon_layout.setSpacing(0)
        type_ribbon_layout.setContentsMargins(0, 0, 0, 0)

        # Create button group for connection types
        self.type_buttons = []
        for i, conn_type in enumerate(self.CONNECTION_TYPES):
            btn = QPushButton(conn_type)
            btn.setCheckable(True)
            btn.setObjectName("type_ribbon_button")
            btn.clicked.connect(lambda checked, idx=i: self.on_type_button_clicked(idx))
            btn.setMinimumHeight(40)
            type_ribbon_layout.addWidget(btn)
            self.type_buttons.append(btn)

        # Select first button by default
        self.type_buttons[0].setChecked(True)
        self.current_type_index = 0

        content_layout.addWidget(type_ribbon)

        # Main form area - grid layout for maximum density
        self.form_grid = QGridLayout()
        self.form_grid.setSpacing(8)
        self.form_grid.setColumnStretch(1, 1)  # Value column stretches
        content_layout.addLayout(self.form_grid)

        # Create all form fields (show/hide based on connection type)
        self.create_form_fields()

        # Results area - for test connection results
        self.results_group = QGroupBox("Test Results")
        self.results_group.setVisible(False)
        results_layout = QVBoxLayout(self.results_group)
        results_layout.setContentsMargins(8, 12, 8, 8)
        results_layout.setSpacing(8)

        # Two list widgets side by side for Excel
        results_lists_layout = QHBoxLayout()

        sheets_layout = QVBoxLayout()
        sheets_layout.addWidget(QLabel("Sheets:"))
        self.sheets_list = QListWidget()
        self.sheets_list.setMaximumHeight(150)
        sheets_layout.addWidget(self.sheets_list)
        results_lists_layout.addLayout(sheets_layout)

        tables_layout = QVBoxLayout()
        tables_layout.addWidget(QLabel("Tables:"))
        self.tables_list = QListWidget()
        self.tables_list.setMaximumHeight(150)
        tables_layout.addWidget(self.tables_list)
        results_lists_layout.addLayout(tables_layout)

        results_layout.addLayout(results_lists_layout)
        content_layout.addWidget(self.results_group)

        # Bottom buttons
        button_layout = QHBoxLayout()
        button_layout.addStretch()

        self.test_btn = QPushButton("Test Connection")
        self.test_btn.setObjectName("gold_button")
        self.test_btn.clicked.connect(self.test_connection)
        button_layout.addWidget(self.test_btn)

        self.save_btn = QPushButton("Save")
        self.save_btn.setObjectName("gold_button")
        self.save_btn.clicked.connect(self.save_connection)
        button_layout.addWidget(self.save_btn)

        cancel_btn = QPushButton("Cancel")
        cancel_btn.setObjectName("secondary_button")
        cancel_btn.clicked.connect(self.reject)
        button_layout.addWidget(cancel_btn)

        content_layout.addLayout(button_layout)

        # Add stretch at bottom to push everything to the top
        content_layout.addStretch()

        layout.addWidget(content_widget)

        # Initialize first connection type
        self.on_type_changed(0)

    def create_form_fields(self):
        """Create all form fields - will show/hide based on connection type"""
        row = 0

        # ODBC fields
        self.odbc_dsn_label = QLabel("ODBC Data Source Name:")
        self.odbc_dsn_label.setMinimumWidth(160)
        self.odbc_dsn_combo = QComboBox()
        self.odbc_dsn_combo.setEditable(True)
        self.odbc_dsn_combo.currentTextChanged.connect(self.on_odbc_dsn_changed)
        self.populate_odbc_dsn_list()
        self.form_grid.addWidget(self.odbc_dsn_label, row, 0)
        self.form_grid.addWidget(self.odbc_dsn_combo, row, 1)
        row += 1

        self.driver_name_label = QLabel("Driver Name:")
        self.driver_name_value = QLineEdit()
        self.driver_name_value.setReadOnly(True)
        self.form_grid.addWidget(self.driver_name_label, row, 0)
        self.form_grid.addWidget(self.driver_name_value, row, 1)
        row += 1

        self.db_type_label = QLabel("Database Type:")
        self.db_type_value = QLineEdit()
        self.db_type_value.setReadOnly(True)
        self.form_grid.addWidget(self.db_type_label, row, 0)
        self.form_grid.addWidget(self.db_type_value, row, 1)
        row += 1

        # SQL Server direct connection fields
        self.sql_server_label = QLabel("Server Name:")
        self.sql_server_edit = QLineEdit()
        self.sql_server_edit.setPlaceholderText("e.g., dsul_ratesdev or SERVER\\INSTANCE")
        self.form_grid.addWidget(self.sql_server_label, row, 0)
        self.form_grid.addWidget(self.sql_server_edit, row, 1)
        row += 1

        self.sql_database_label = QLabel("Database (Optional):")
        self.sql_database_edit = QLineEdit()
        self.sql_database_edit.setPlaceholderText("Leave empty to see all databases")
        self.form_grid.addWidget(self.sql_database_label, row, 0)
        self.form_grid.addWidget(self.sql_database_edit, row, 1)
        row += 1

        self.sql_auth_label = QLabel("Authentication:")
        self.sql_auth_combo = QComboBox()
        self.sql_auth_combo.addItems(["Windows Authentication", "SQL Server Authentication"])
        self.sql_auth_combo.currentIndexChanged.connect(self.on_sql_auth_changed)
        self.form_grid.addWidget(self.sql_auth_label, row, 0)
        self.form_grid.addWidget(self.sql_auth_combo, row, 1)
        row += 1

        self.sql_username_label = QLabel("Username:")
        self.sql_username_edit = QLineEdit()
        self.sql_username_edit.setPlaceholderText("SQL Server login")
        self.form_grid.addWidget(self.sql_username_label, row, 0)
        self.form_grid.addWidget(self.sql_username_edit, row, 1)
        row += 1

        self.sql_password_label = QLabel("Password:")
        self.sql_password_edit = QLineEdit()
        self.sql_password_edit.setEchoMode(QLineEdit.EchoMode.Password)
        self.form_grid.addWidget(self.sql_password_label, row, 0)
        self.form_grid.addWidget(self.sql_password_edit, row, 1)
        row += 1

        # File picker fields (shared)
        self.file_label = QLabel("File:")
        self.file_layout = QHBoxLayout()
        self.file_layout.setSpacing(8)
        self.file_path_edit = QLineEdit()
        self.file_path_edit.setReadOnly(True)
        self.file_path_edit.textChanged.connect(self.on_file_path_changed)
        self.file_layout.addWidget(self.file_path_edit)
        self.pick_file_btn = QPushButton("Browse...")
        self.pick_file_btn.clicked.connect(self.pick_file)
        self.file_layout.addWidget(self.pick_file_btn)
        self.form_grid.addWidget(self.file_label, row, 0)
        self.form_grid.addLayout(self.file_layout, row, 1)
        row += 1

        self.folder_label = QLabel("File Location (Folder):")
        self.folder_value = QLineEdit()
        self.folder_value.setReadOnly(True)
        self.form_grid.addWidget(self.folder_label, row, 0)
        self.form_grid.addWidget(self.folder_value, row, 1)
        row += 1

        self.filename_label = QLabel("File Name:")
        self.filename_value = QLineEdit()
        self.filename_value.setReadOnly(True)
        self.form_grid.addWidget(self.filename_label, row, 0)
        self.form_grid.addWidget(self.filename_value, row, 1)
        row += 1

        # CSV-specific fields
        self.csv_header_check = QCheckBox("First row contains column headers")
        self.csv_header_check.setChecked(True)
        self.form_grid.addWidget(QLabel(""), row, 0)
        self.form_grid.addWidget(self.csv_header_check, row, 1)
        row += 1

        self.delimiter_label = QLabel("Delimiter:")
        self.delimiter_combo = QComboBox()
        self.delimiter_combo.addItems([",", ";", "|", "Tab", "Space"])
        self.form_grid.addWidget(self.delimiter_label, row, 0)
        self.form_grid.addWidget(self.delimiter_combo, row, 1)
        row += 1

        self.encoding_label = QLabel("Encoding:")
        self.encoding_combo = QComboBox()
        self.encoding_combo.addItems(["UTF-8", "Windows-1252", "ISO-8859-1", "ASCII"])
        self.form_grid.addWidget(self.encoding_label, row, 0)
        self.form_grid.addWidget(self.encoding_combo, row, 1)
        row += 1

        # Fixed width field definition grid
        self.fixed_width_label = QLabel("Field Definitions:")
        self.fixed_width_grid = QTableWidget()
        self.fixed_width_grid.setColumnCount(4)
        self.fixed_width_grid.setHorizontalHeaderLabels(["Field Name", "Start", "Length", "Data Type"])
        self.fixed_width_grid.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.fixed_width_grid.setMaximumHeight(200)

        # Add row button for fixed width
        self.fw_button_layout = QHBoxLayout()
        self.add_field_btn = QPushButton("+ Add Field")
        self.add_field_btn.clicked.connect(self.add_fixed_width_field)
        self.fw_button_layout.addWidget(self.add_field_btn)
        self.import_fields_btn = QPushButton("Import from Clipboard")
        self.import_fields_btn.clicked.connect(self.import_fixed_width_fields)
        self.fw_button_layout.addWidget(self.import_fields_btn)
        self.fw_button_layout.addStretch()

        self.form_grid.addWidget(self.fixed_width_label, row, 0, Qt.AlignmentFlag.AlignTop)
        fw_container = QVBoxLayout()
        fw_container.addWidget(self.fixed_width_grid)
        fw_container.addLayout(self.fw_button_layout)
        self.form_grid.addLayout(fw_container, row, 1)
        row += 1

        # Mainframe FTP fields
        self.ftp_host_label = QLabel("FTP Host:")
        self.ftp_host_edit = QLineEdit()
        self.ftp_host_edit.setPlaceholderText("e.g., PRODESA")
        self.form_grid.addWidget(self.ftp_host_label, row, 0)
        self.form_grid.addWidget(self.ftp_host_edit, row, 1)
        row += 1

        self.ftp_port_label = QLabel("FTP Port:")
        self.ftp_port_edit = QLineEdit()
        self.ftp_port_edit.setText("21")
        self.ftp_port_edit.setPlaceholderText("21")
        self.form_grid.addWidget(self.ftp_port_label, row, 0)
        self.form_grid.addWidget(self.ftp_port_edit, row, 1)
        row += 1

        self.ftp_username_label = QLabel("Username:")
        self.ftp_username_edit = QLineEdit()
        self.ftp_username_edit.setPlaceholderText("e.g., AC1Z42")
        self.form_grid.addWidget(self.ftp_username_label, row, 0)
        self.form_grid.addWidget(self.ftp_username_edit, row, 1)
        row += 1

        self.ftp_password_label = QLabel("Password:")
        self.ftp_password_edit = QLineEdit()
        self.ftp_password_edit.setEchoMode(QLineEdit.EchoMode.Password)
        self.form_grid.addWidget(self.ftp_password_label, row, 0)
        self.form_grid.addWidget(self.ftp_password_edit, row, 1)
        row += 1

        self.ftp_initial_path_label = QLabel("Initial Path (Optional):")
        self.ftp_initial_path_edit = QLineEdit()
        self.ftp_initial_path_edit.setPlaceholderText("e.g., d03.aa0139.CKAS.cdf.data")
        self.form_grid.addWidget(self.ftp_initial_path_label, row, 0)
        self.form_grid.addWidget(self.ftp_initial_path_edit, row, 1)
        row += 1

        # Connection name (common to all)
        self.conn_name_label = QLabel("Connection Name:")
        self.conn_name_edit = QLineEdit()
        self.form_grid.addWidget(self.conn_name_label, row, 0)
        self.form_grid.addWidget(self.conn_name_edit, row, 1)
        row += 1

    def on_type_button_clicked(self, index: int):
        """Handle connection type button click"""
        # Uncheck all other buttons
        for i, btn in enumerate(self.type_buttons):
            btn.setChecked(i == index)

        self.current_type_index = index
        self.on_type_changed(index)

    def on_type_changed(self, index: int):
        """Show/hide fields based on connection type"""
        conn_type = self.CONNECTION_TYPES[index]

        # Hide all first
        self.hide_all_fields()

        # Show common field (with safety checks)
        if hasattr(self, 'conn_name_label'):
            self.conn_name_label.setVisible(True)
        if hasattr(self, 'conn_name_edit'):
            self.conn_name_edit.setVisible(True)

        if conn_type == "Local ODBC":
            if hasattr(self, 'odbc_dsn_label'):
                self.odbc_dsn_label.setVisible(True)
            if hasattr(self, 'odbc_dsn_combo'):
                self.odbc_dsn_combo.setVisible(True)
            if hasattr(self, 'driver_name_label'):
                self.driver_name_label.setVisible(True)
            if hasattr(self, 'driver_name_value'):
                self.driver_name_value.setVisible(True)
            if hasattr(self, 'db_type_label'):
                self.db_type_label.setVisible(True)
            if hasattr(self, 'db_type_value'):
                self.db_type_value.setVisible(True)

        elif conn_type in ["Excel File", "MS Access"]:
            for attr in ['file_label', 'file_path_edit', 'pick_file_btn',
                        'folder_label', 'folder_value', 'filename_label', 'filename_value']:
                if hasattr(self, attr):
                    getattr(self, attr).setVisible(True)

        elif conn_type == "CSV File":
            for attr in ['file_label', 'file_path_edit', 'pick_file_btn',
                        'folder_label', 'folder_value', 'filename_label', 'filename_value',
                        'csv_header_check', 'delimiter_label', 'delimiter_combo',
                        'encoding_label', 'encoding_combo']:
                if hasattr(self, attr):
                    getattr(self, attr).setVisible(True)

        elif conn_type == "Fixed Width File":
            for attr in ['file_label', 'file_path_edit', 'pick_file_btn',
                        'folder_label', 'folder_value', 'filename_label', 'filename_value',
                        'csv_header_check', 'fixed_width_label', 'fixed_width_grid',
                        'add_field_btn', 'import_fields_btn']:
                if hasattr(self, attr):
                    getattr(self, attr).setVisible(True)

        elif conn_type == "SQL Server":
            for attr in ['sql_server_label', 'sql_server_edit', 'sql_database_label', 'sql_database_edit',
                        'sql_auth_label', 'sql_auth_combo', 'sql_username_label', 'sql_username_edit',
                        'sql_password_label', 'sql_password_edit']:
                if hasattr(self, attr):
                    getattr(self, attr).setVisible(True)
            # Trigger auth change to show/hide credentials
            if hasattr(self, 'sql_auth_combo'):
                self.on_sql_auth_changed(self.sql_auth_combo.currentIndex())

        elif conn_type == "Mainframe FTP":
            for attr in ['ftp_host_label', 'ftp_host_edit', 'ftp_port_label', 'ftp_port_edit',
                        'ftp_username_label', 'ftp_username_edit', 'ftp_password_label', 'ftp_password_edit',
                        'ftp_initial_path_label', 'ftp_initial_path_edit']:
                if hasattr(self, attr):
                    getattr(self, attr).setVisible(True)

    def hide_all_fields(self):
        """Hide all form fields"""
        # Safely hide fields that might not be initialized yet
        for attr in ['odbc_dsn_label', 'odbc_dsn_combo', 'driver_name_label',
                     'driver_name_value', 'db_type_label', 'db_type_value',
                     'sql_server_label', 'sql_server_edit', 'sql_database_label', 'sql_database_edit',
                     'sql_auth_label', 'sql_auth_combo', 'sql_username_label', 'sql_username_edit',
                     'sql_password_label', 'sql_password_edit',
                     'file_label', 'file_path_edit', 'pick_file_btn',
                     'folder_label', 'folder_value', 'filename_label', 'filename_value',
                     'csv_header_check', 'delimiter_label', 'delimiter_combo',
                     'encoding_label', 'encoding_combo', 'fixed_width_label',
                     'fixed_width_grid', 'add_field_btn', 'import_fields_btn',
                     'ftp_host_label', 'ftp_host_edit', 'ftp_port_label', 'ftp_port_edit',
                     'ftp_username_label', 'ftp_username_edit', 'ftp_password_label', 'ftp_password_edit',
                     'ftp_initial_path_label', 'ftp_initial_path_edit']:
            if hasattr(self, attr):
                getattr(self, attr).setVisible(False)

    def populate_odbc_dsn_list(self):
        """Populate ODBC DSN combo with available User DSNs"""
        if not PYODBC_AVAILABLE:
            return

        try:
            datasources = pyodbc.dataSources()
            dsn_list = sorted(datasources.keys())
            self.odbc_dsn_combo.addItems(dsn_list)
        except Exception as e:
            print(f"Error loading ODBC DSNs: {e}")

    def on_odbc_dsn_changed(self, dsn_name: str):
        """When DSN is selected, lookup driver and determine database type"""
        if not dsn_name or not PYODBC_AVAILABLE:
            return

        # Check if widgets are initialized
        if not hasattr(self, 'driver_name_value') or not hasattr(self, 'db_type_value'):
            return

        try:
            datasources = pyodbc.dataSources()
            if dsn_name in datasources:
                driver = datasources[dsn_name]
                self.driver_name_value.setText(driver)

                # Determine database type from driver name
                driver_lower = driver.lower()
                if 'sql server' in driver_lower or 'mssql' in driver_lower:
                    db_type = 'SQL'
                elif 'db2' in driver_lower or 'datadirect' in driver_lower or 'shadow' in driver_lower:
                    # DB2 or DataDirect Shadow Client (used for DB2)
                    db_type = 'DB2'
                else:
                    db_type = 'Unknown'

                self.db_type_value.setText(db_type)
                
                # Only set connection name if it's empty (for new connections)
                if not self.conn_name_edit.text().strip():
                    self.conn_name_edit.setText(dsn_name)
        except Exception as e:
            QMessageBox.warning(self, "Error", f"Failed to get driver info: {str(e)}")
    
    def on_sql_auth_changed(self, index: int):
        """Show/hide SQL Server username/password based on authentication type"""
        # 0 = Windows Authentication, 1 = SQL Server Authentication
        is_sql_auth = (index == 1)
        
        if hasattr(self, 'sql_username_label'):
            self.sql_username_label.setVisible(is_sql_auth)
        if hasattr(self, 'sql_username_edit'):
            self.sql_username_edit.setVisible(is_sql_auth)
        if hasattr(self, 'sql_password_label'):
            self.sql_password_label.setVisible(is_sql_auth)
        if hasattr(self, 'sql_password_edit'):
            self.sql_password_edit.setVisible(is_sql_auth)

    def pick_file(self):
        """Open file picker dialog (or folder for CSV)"""
        conn_type = self.CONNECTION_TYPES[self.current_type_index]

        # For CSV, select folder instead of file
        if conn_type == "CSV File":
            folder_path = QFileDialog.getExistingDirectory(
                self,
                "Select Folder Containing CSV Files",
                "",
                QFileDialog.Option.ShowDirsOnly
            )
            if folder_path:
                # Normalize to Windows backslashes
                folder_path = os.path.normpath(folder_path)
                self.file_path_edit.setText(folder_path)
            return

        # For other file types, select individual files
        if conn_type == "Excel File":
            file_filter = "Excel Files (*.xlsx *.xls)"
        elif conn_type == "MS Access":
            file_filter = "Access Files (*.accdb *.mdb)"
        elif conn_type == "Fixed Width File":
            file_filter = "Text Files (*.txt *.dat);;All Files (*.*)"
        else:
            file_filter = "All Files (*.*)"

        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "Select File",
            "",
            file_filter
        )

        if file_path:
            # Normalize to Windows backslashes
            file_path = os.path.normpath(file_path)
            self.file_path_edit.setText(file_path)

    def on_file_path_changed(self, file_path: str):
        """Update folder and filename when file path changes"""
        if file_path:
            # Normalize path to use Windows backslashes
            file_path = os.path.normpath(file_path)

            conn_type = self.CONNECTION_TYPES[self.current_type_index]
            
            # For CSV, the path IS the folder (no filename)
            if conn_type == "CSV File":
                if os.path.isdir(file_path):
                    self.folder_value.setText(file_path)
                    self.filename_value.setText("(All CSV files in folder)")
                    # Set connection name to folder name
                    folder_name = os.path.basename(file_path)
                    self.conn_name_edit.setText(folder_name)
                return

            # For other file types, split into folder and filename
            folder = os.path.dirname(file_path)
            filename = os.path.basename(file_path)

            self.folder_value.setText(folder)
            self.filename_value.setText(filename)

            # Set connection name to filename without extension
            name_without_ext = os.path.splitext(filename)[0]
            self.conn_name_edit.setText(name_without_ext)

    def add_fixed_width_field(self):
        """Add a new row to fixed width field grid"""
        row = self.fixed_width_grid.rowCount()
        self.fixed_width_grid.insertRow(row)

        # Add default data type combo
        type_combo = QComboBox()
        type_combo.addItems(["String", "Integer", "Decimal", "Date"])
        self.fixed_width_grid.setCellWidget(row, 3, type_combo)

    def import_fixed_width_fields(self):
        """Import fixed width field definitions from clipboard"""
        # TODO: Implement clipboard import
        QMessageBox.information(
            self,
            "Import Fields",
            "Paste field definitions from spreadsheet (Name, Start, Length, Type)"
        )

    def test_connection(self):
        """Test the connection and show results"""
        conn_type = self.CONNECTION_TYPES[self.current_type_index]

        try:
            if conn_type == "Local ODBC":
                self.test_odbc_connection()
            elif conn_type == "SQL Server":
                self.test_sql_server_connection()
            elif conn_type == "Excel File":
                self.test_excel_connection()
            elif conn_type == "MS Access":
                self.test_access_connection()
            elif conn_type == "CSV File":
                self.test_csv_connection()
            elif conn_type == "Fixed Width File":
                self.test_fixed_width_connection()
            elif conn_type == "Mainframe FTP":
                self.test_ftp_connection()

        except Exception as e:
            QMessageBox.critical(self, "Connection Failed", str(e))
            self.results_group.setVisible(False)

    def test_odbc_connection(self):
        """Test ODBC connection"""
        if not PYODBC_AVAILABLE:
            raise ValueError("ODBC support not available. Please install ODBC drivers.")

        dsn = self.odbc_dsn_combo.currentText()
        if not dsn:
            raise ValueError("Please select a Data Source Name")

        try:
            conn_str = f"DSN={dsn}"
            
            # Show connection attempt
            QMessageBox.information(self, "Debug", f"Attempting to connect with:\n{conn_str}")
            
            conn = pyodbc.connect(conn_str)

            # Detect database type from driver name and stored value
            db_type = None
            driver_name = ""
            
            if hasattr(self, 'db_type_value'):
                db_type = self.db_type_value.text()
            
            if hasattr(self, 'driver_name_value'):
                driver_name = self.driver_name_value.text()
            
            # Enhanced DB2 detection - check driver name for DataDirect, Shadow, or DB2
            driver_lower = driver_name.lower()
            if db_type != 'DB2' and ('datadirect' in driver_lower or 'shadow' in driver_lower or 'db2' in driver_lower):
                db_type = 'DB2'
                QMessageBox.information(self, "Debug", f"DB2 detected from driver name: {driver_name}")

            QMessageBox.information(self, "Debug", f"Connected!\nDriver: {driver_name}\nDetected database type: {db_type}")

            # Get table list - DB2 requires special handling
            cursor = conn.cursor()
            tables = []
            
            try:
                if db_type == 'DB2':
                    # DB2 with DataDirect Shadow Client requires WITH clause and LIMIT
                    query = """
                        WITH DUMMY AS (SELECT 1 FROM SYSIBM.SYSDUMMY1)
                        SELECT NAME, CREATOR
                        FROM SYSIBM.SYSTABLES
                        WHERE TYPE = 'T'
                            AND CREATOR NOT LIKE 'SYS%'
                            AND NAME NOT LIKE 'SYS%'
                        ORDER BY CREATOR, NAME
                        LIMIT 10000
                    """
                    
                    # Show the SQL query before executing
                    QMessageBox.information(self, "Debug - SQL Query", f"About to execute DB2 query:\n\n{query}")
                    
                    cursor.execute(query)
                    
                    QMessageBox.information(self, "Debug", "Query executed successfully! Fetching results...")
                    
                    for row in cursor.fetchall():
                        table_name = row[0].strip() if row[0] else row[0]
                        schema_name = row[1].strip() if row[1] else row[1]
                        tables.append(f"{schema_name}.{table_name}" if schema_name else table_name)
                else:
                    # Standard ODBC table discovery
                    QMessageBox.information(self, "Debug", "Using standard ODBC cursor.tables() method")
                    
                    for table_info in cursor.tables(tableType='TABLE'):
                        tables.append(table_info.table_name)
            except Exception as table_err:
                conn.close()
                raise ValueError(f"Failed to get table list: {str(table_err)}\n\nFor DB2 connections, ensure the database type is correctly detected.")

            conn.close()

            # Show results
            self.sheets_list.clear()
            self.tables_list.clear()
            self.tables_list.addItems(tables[:50])  # Limit to first 50
            self.results_group.setVisible(True)

            QMessageBox.information(self, "Success", f"Connected successfully! Found {len(tables)} tables.")
            
        except pyodbc.Error as e:
            raise ValueError(f"ODBC Error: {str(e)}\n\nThis may be a driver-specific issue. For DB2 with DataDirect driver, special handling is required.")

    def test_sql_server_connection(self):
        """Test SQL Server direct connection"""
        if not PYODBC_AVAILABLE:
            raise ValueError("ODBC support not available. Please install ODBC drivers.")

        server = self.sql_server_edit.text()
        if not server:
            raise ValueError("Please enter a server name")

        database = self.sql_database_edit.text() or "master"
        auth_type = self.sql_auth_combo.currentIndex()  # 0 = Windows, 1 = SQL Server
        
        # Build connection string based on authentication type
        if auth_type == 0:  # Windows Authentication
            conn_str = f"DRIVER={{ODBC Driver 17 for SQL Server}};SERVER={server};DATABASE={database};Trusted_Connection=yes"
        else:  # SQL Server Authentication
            username = self.sql_username_edit.text()
            password = self.sql_password_edit.text()
            if not username:
                raise ValueError("Please enter a username for SQL Server Authentication")
            conn_str = f"DRIVER={{ODBC Driver 17 for SQL Server}};SERVER={server};DATABASE={database};UID={username};PWD={password}"

        try:
            # Test connection
            conn = pyodbc.connect(conn_str, timeout=5)
            
            # Get table list
            cursor = conn.cursor()
            tables = []
            
            # Get tables from all schemas
            for table_info in cursor.tables(tableType='TABLE'):
                schema_name = table_info.table_schem
                table_name = table_info.table_name
                if schema_name:
                    tables.append(f"{schema_name}.{table_name}")
                else:
                    tables.append(table_name)

            conn.close()

            # Show results
            self.sheets_list.clear()
            self.tables_list.clear()
            self.tables_list.addItems(tables[:50])  # Limit to first 50
            self.results_group.setVisible(True)

            QMessageBox.information(self, "Success", f"Connected successfully to {server}! Found {len(tables)} tables.")
            
        except pyodbc.Error as e:
            raise ValueError(f"SQL Server Connection Error: {str(e)}")

    def test_excel_connection(self):
        """Test Excel file connection"""
        file_path = self.file_path_edit.text()
        if not file_path or not os.path.exists(file_path):
            raise ValueError("Please select a valid Excel file")

        import openpyxl
        wb = openpyxl.load_workbook(file_path, read_only=True)

        # Get sheets
        sheets = wb.sheetnames

        # Get named tables/ranges
        table_names = []
        try:
            # wb.defined_names returns a DefinedNameDict, iterate over it directly
            for name, defn in wb.defined_names.items():
                if defn.name:
                    table_names.append(defn.name)
        except Exception:
            # If there's any issue reading defined names, just skip them
            pass

        wb.close()

        # Show results
        self.sheets_list.clear()
        self.tables_list.clear()
        self.sheets_list.addItems(sheets)
        if table_names:
            self.tables_list.addItems(table_names)
        self.results_group.setVisible(True)

        QMessageBox.information(
            self,
            "Success",
            f"Excel file loaded!\nSheets: {len(sheets)}\nTables: {len(table_names)}"
        )

    def test_access_connection(self):
        """Test MS Access connection"""
        if not PYODBC_AVAILABLE:
            raise ValueError("ODBC support not available. Please install ODBC drivers.")

        file_path = self.file_path_edit.text()
        if not file_path or not os.path.exists(file_path):
            raise ValueError("Please select a valid Access database file")

        conn_str = (
            r'DRIVER={Microsoft Access Driver (*.mdb, *.accdb)};'
            f'DBQ={file_path};'
        )
        conn = pyodbc.connect(conn_str)

        # Get table list
        cursor = conn.cursor()
        tables = []
        for table_info in cursor.tables(tableType='TABLE'):
            tables.append(table_info.table_name)

        conn.close()

        # Show results
        self.sheets_list.clear()
        self.tables_list.clear()
        self.tables_list.addItems(tables)
        self.results_group.setVisible(True)

        QMessageBox.information(self, "Success", f"Connected successfully! Found {len(tables)} tables.")

    def test_csv_connection(self):
        """Test CSV folder connection"""
        folder_path = self.file_path_edit.text()
        if not folder_path or not os.path.exists(folder_path):
            raise ValueError("Please select a valid folder")

        if not os.path.isdir(folder_path):
            raise ValueError("Please select a folder, not a file")

        # Find all CSV files in the folder
        csv_files = [f for f in os.listdir(folder_path) 
                     if f.lower().endswith('.csv')]

        if not csv_files:
            raise ValueError("No CSV files found in the selected folder")

        self.results_group.setVisible(False)
        QMessageBox.information(
            self,
            "Success",
            f"Found {len(csv_files)} CSV file(s) in folder:\n\n" + 
            "\n".join(csv_files[:10]) + 
            (f"\n... and {len(csv_files) - 10} more" if len(csv_files) > 10 else "")
        )

    def test_fixed_width_connection(self):
        """Test fixed width file connection"""
        file_path = self.file_path_edit.text()
        if not file_path or not os.path.exists(file_path):
            raise ValueError("Please select a valid text file")

        if self.fixed_width_grid.rowCount() == 0:
            raise ValueError("Please define at least one field")

        # Verify file can be opened
        with open(file_path, 'r') as f:
            first_line = f.readline()

        self.results_group.setVisible(False)
        QMessageBox.information(
            self,
            "Success",
            f"File is accessible!\nFields defined: {self.fixed_width_grid.rowCount()}"
        )

    def test_ftp_connection(self):
        """Test mainframe FTP connection"""
        from suiteview.core.ftp_manager import MainframeFTPManager
        
        host = self.ftp_host_edit.text().strip()
        port = int(self.ftp_port_edit.text().strip() or "21")
        username = self.ftp_username_edit.text().strip()
        password = self.ftp_password_edit.text().strip()
        initial_path = self.ftp_initial_path_edit.text().strip()
        
        if not all([host, username, password]):
            raise ValueError("Please enter Host, Username, and Password")
        
        # Test connection
        ftp_mgr = MainframeFTPManager(host, username, password, port, initial_path)
        success, message = ftp_mgr.test_connection()
        
        if not success:
            raise ValueError(message)
        
        # Try to list datasets at initial path or root
        datasets = ftp_mgr.list_datasets()
        ftp_mgr.disconnect()
        
        # Show results
        self.sheets_list.clear()
        self.tables_list.clear()
        self.tables_list.addItems([ds['name'] for ds in datasets[:50]])  # Limit to first 50
        self.results_group.setVisible(True)
        
        QMessageBox.information(
            self,
            "Success",
            f"{message}\n\nFound {len(datasets)} dataset(s)/member(s)"
        )

    def save_connection(self):
        """Save connection and close dialog"""
        conn_name = self.conn_name_edit.text().strip()
        if not conn_name:
            QMessageBox.warning(self, "Validation", "Please enter a connection name")
            return

        conn_type = self.CONNECTION_TYPES[self.current_type_index]

        # Build connection data based on type
        # If editing existing connection, start with existing data to preserve all fields
        if self.existing_connection:
            self.connection_data = self.existing_connection.copy()
            # Update with new values
            self.connection_data["connection_name"] = conn_name
            self.connection_data["connection_type"] = conn_type
        else:
            self.connection_data = {
                "connection_name": conn_name,
                "connection_type": conn_type
            }

        if conn_type == "Local ODBC":
            self.connection_data.update({
                "dsn": self.odbc_dsn_combo.currentText(),
                "driver": self.driver_name_value.text(),
                "database_type": self.db_type_value.text()
            })
        elif conn_type == "SQL Server":
            auth_type = self.sql_auth_combo.currentIndex()  # 0 = Windows, 1 = SQL Server
            self.connection_data.update({
                "server": self.sql_server_edit.text().strip(),
                "database": self.sql_database_edit.text().strip() or "master",
                "auth_type": "Windows" if auth_type == 0 else "SQL Server"
            })
            # Only store username/password for SQL Server Authentication
            if auth_type == 1:
                self.connection_data.update({
                    "username": self.sql_username_edit.text().strip(),
                    "password": self.sql_password_edit.text().strip()
                })
        elif conn_type == "Mainframe FTP":
            self.connection_data.update({
                "ftp_host": self.ftp_host_edit.text().strip(),
                "ftp_port": int(self.ftp_port_edit.text().strip() or "21"),
                "ftp_username": self.ftp_username_edit.text().strip(),
                "ftp_password": self.ftp_password_edit.text().strip(),
                "ftp_initial_path": self.ftp_initial_path_edit.text().strip()
            })
        elif conn_type in ["Excel File", "MS Access", "CSV File", "Fixed Width File"]:
            self.connection_data.update({
                "file_path": self.file_path_edit.text(),
                "folder": self.folder_value.text(),
                "filename": self.filename_value.text()
            })

            if conn_type == "CSV File":
                delimiter = self.delimiter_combo.currentText()
                if delimiter == "Tab":
                    delimiter = "\t"
                elif delimiter == "Space":
                    delimiter = " "

                self.connection_data.update({
                    "has_header": self.csv_header_check.isChecked(),
                    "delimiter": delimiter,
                    "encoding": self.encoding_combo.currentText()
                })
            elif conn_type == "Fixed Width File":
                # Get field definitions
                fields = []
                for row in range(self.fixed_width_grid.rowCount()):
                    name_item = self.fixed_width_grid.item(row, 0)
                    start_item = self.fixed_width_grid.item(row, 1)
                    length_item = self.fixed_width_grid.item(row, 2)
                    type_widget = self.fixed_width_grid.cellWidget(row, 3)

                    if name_item and start_item and length_item:
                        fields.append({
                            "name": name_item.text(),
                            "start": int(start_item.text()),
                            "length": int(length_item.text()),
                            "type": type_widget.currentText() if type_widget else "String"
                        })

                self.connection_data.update({
                    "has_header": self.csv_header_check.isChecked(),
                    "fields": fields
                })

        self.accept()

    def populate_form_with_existing_data(self):
        """Populate form fields with existing connection data"""
        if not self.existing_connection:
            return
        
        conn = self.existing_connection
        conn_type = conn.get('connection_type', '')
        
        # Map stored connection types to button indices
        # Stored types: SQL_SERVER, DB2, ACCESS, EXCEL, CSV, FIXED_WIDTH
        # Dialog buttons: "Local ODBC" (0), "Excel File" (1), "MS Access" (2), "CSV File" (3), "Fixed Width File" (4)
        type_map = {
            'SQL_SERVER': 0,  # Maps to "Local ODBC" button
            'DB2': 0,         # Maps to "Local ODBC" button
            'EXCEL': 1,       # Maps to "Excel File" button
            'ACCESS': 2,      # Maps to "MS Access" button
            'CSV': 3,         # Maps to "CSV File" button
            'FIXED_WIDTH': 4  # Maps to "Fixed Width File" button
        }
        
        # Set the connection type button
        type_index = type_map.get(conn_type, 0)
        if type_index < len(self.type_buttons):
            self.type_buttons[type_index].setChecked(True)
            self.on_type_button_clicked(type_index)
        
        # Populate connection name
        self.conn_name_edit.setText(conn.get('connection_name', ''))
        
        # Populate type-specific fields
        if conn_type in ['SQL_SERVER', 'DB2']:
            # ODBC connection
            dsn = conn.get('dsn', '') or conn.get('server_name', '') or conn.get('connection_string', '').replace('DSN=', '')
            if dsn and self.odbc_dsn_combo.findText(dsn) >= 0:
                self.odbc_dsn_combo.setCurrentText(dsn)
            elif dsn:
                # If DSN not in combo, add it and select it
                self.odbc_dsn_combo.addItem(dsn)
                self.odbc_dsn_combo.setCurrentText(dsn)
            
            # Trigger the DSN selection to populate driver and database type
            if dsn:
                self.on_odbc_dsn_changed(dsn)
                
        elif conn_type in ['EXCEL', 'ACCESS', 'CSV', 'FIXED_WIDTH']:
            # File-based connections
            # File path is stored in connection_string for file-based connections
            file_path = conn.get('file_path', '') or conn.get('connection_string', '')
            if file_path:
                self.file_path_edit.setText(file_path)
                # Manually update folder and filename (without changing conn name)
                folder = os.path.dirname(file_path)
                filename = os.path.basename(file_path)
                self.folder_value.setText(folder)
                self.filename_value.setText(filename)
                
            if conn_type == 'CSV':
                # CSV-specific fields
                if hasattr(self, 'csv_header_check'):
                    self.csv_header_check.setChecked(conn.get('has_header', True))
                if hasattr(self, 'delimiter_combo'):
                    delimiter = conn.get('delimiter', ',')
                    if delimiter == '\t':
                        self.delimiter_combo.setCurrentText('Tab')
                    elif delimiter == ' ':
                        self.delimiter_combo.setCurrentText('Space')
                    else:
                        self.delimiter_combo.setCurrentText(delimiter)
                if hasattr(self, 'encoding_combo'):
                    encoding = conn.get('encoding', 'utf-8')
                    if self.encoding_combo.findText(encoding) >= 0:
                        self.encoding_combo.setCurrentText(encoding)
                        
            elif conn_type == 'FIXED_WIDTH':
                # Fixed width specific fields
                if hasattr(self, 'csv_header_check'):
                    self.csv_header_check.setChecked(conn.get('has_header', False))
                # TODO: Populate field definitions if stored

    def get_connection_data(self) -> Optional[Dict[str, Any]]:
        """Return the connection data after dialog closes"""
        return self.connection_data
