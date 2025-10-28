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
        "Excel File",
        "MS Access",
        "CSV File",
        "Fixed Width File"
    ]

    def __init__(self, parent=None):
        super().__init__(parent)
        self.connection_data = None

        # Set window flags to make it a proper dialog
        from PyQt6.QtCore import Qt
        self.setWindowFlags(Qt.WindowType.Dialog | Qt.WindowType.WindowCloseButtonHint)
        self.setModal(True)  # Make it modal so it blocks parent

        self.init_ui()
        self.setMinimumWidth(700)
        self.setMinimumHeight(500)

    def init_ui(self):
        """Initialize the UI - stable layout, no expanding/collapsing"""
        self.setWindowTitle("Add New Connection")

        layout = QVBoxLayout(self)
        layout.setSpacing(0)
        layout.setContentsMargins(0, 0, 0, 0)

        # Title bar with blue gradient
        title_bar = QWidget()
        title_bar.setObjectName("dialog_title_bar")
        title_bar.setMaximumHeight(50)  # Limit title bar height
        title_bar_layout = QHBoxLayout(title_bar)
        title_bar_layout.setContentsMargins(15, 10, 15, 10)

        title_label = QLabel("Add New Connection")
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

    def hide_all_fields(self):
        """Hide all form fields"""
        # Safely hide fields that might not be initialized yet
        for attr in ['odbc_dsn_label', 'odbc_dsn_combo', 'driver_name_label',
                     'driver_name_value', 'db_type_label', 'db_type_value',
                     'file_label', 'file_path_edit', 'pick_file_btn',
                     'folder_label', 'folder_value', 'filename_label', 'filename_value',
                     'csv_header_check', 'delimiter_label', 'delimiter_combo',
                     'encoding_label', 'encoding_combo', 'fixed_width_label',
                     'fixed_width_grid', 'add_field_btn', 'import_fields_btn']:
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

        try:
            datasources = pyodbc.dataSources()
            if dsn_name in datasources:
                driver = datasources[dsn_name]
                self.driver_name_value.setText(driver)

                # Determine database type from driver name
                driver_lower = driver.lower()
                if 'sql server' in driver_lower or 'mssql' in driver_lower:
                    db_type = 'SQL'
                    suffix = ' (SQL)'
                elif 'db2' in driver_lower:
                    db_type = 'DB2'
                    suffix = ' (DB2)'
                else:
                    db_type = 'Unknown'
                    suffix = ''

                self.db_type_value.setText(db_type)
                self.conn_name_edit.setText(dsn_name + suffix)
        except Exception as e:
            QMessageBox.warning(self, "Error", f"Failed to get driver info: {str(e)}")

    def pick_file(self):
        """Open file picker dialog"""
        conn_type = self.CONNECTION_TYPES[self.current_type_index]

        if conn_type == "Excel File":
            file_filter = "Excel Files (*.xlsx *.xls)"
        elif conn_type == "MS Access":
            file_filter = "Access Files (*.accdb *.mdb)"
        elif conn_type == "CSV File":
            file_filter = "CSV Files (*.csv *.txt)"
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
            elif conn_type == "Excel File":
                self.test_excel_connection()
            elif conn_type == "MS Access":
                self.test_access_connection()
            elif conn_type == "CSV File":
                self.test_csv_connection()
            elif conn_type == "Fixed Width File":
                self.test_fixed_width_connection()

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

        conn_str = f"DSN={dsn}"
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
        self.tables_list.addItems(tables[:50])  # Limit to first 50
        self.results_group.setVisible(True)

        QMessageBox.information(self, "Success", f"Connected successfully! Found {len(tables)} tables.")

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
        """Test CSV file connection"""
        file_path = self.file_path_edit.text()
        if not file_path or not os.path.exists(file_path):
            raise ValueError("Please select a valid CSV file")

        # Just verify file can be opened
        with open(file_path, 'r', encoding=self.encoding_combo.currentText().lower().replace('-', '')) as f:
            first_line = f.readline()

        self.results_group.setVisible(False)
        QMessageBox.information(
            self,
            "Success",
            f"CSV file is accessible!\nFirst line preview:\n{first_line[:100]}"
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

    def save_connection(self):
        """Save connection and close dialog"""
        conn_name = self.conn_name_edit.text().strip()
        if not conn_name:
            QMessageBox.warning(self, "Validation", "Please enter a connection name")
            return

        conn_type = self.CONNECTION_TYPES[self.current_type_index]

        # Build connection data based on type
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

    def get_connection_data(self) -> Optional[Dict[str, Any]]:
        """Return the connection data after dialog closes"""
        return self.connection_data
