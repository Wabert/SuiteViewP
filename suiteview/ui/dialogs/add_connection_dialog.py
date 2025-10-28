"""Add Connection Dialog"""

import logging
from PyQt6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QFormLayout,
                              QLabel, QLineEdit, QComboBox, QPushButton,
                              QGroupBox, QMessageBox, QRadioButton, QButtonGroup)
from PyQt6.QtCore import Qt, pyqtSignal

from suiteview.core.connection_manager import get_connection_manager

logger = logging.getLogger(__name__)


class AddConnectionDialog(QDialog):
    """Dialog for adding a new database connection"""

    # Signal emitted when connection is successfully added
    connection_added = pyqtSignal(int)  # Emits connection_id

    def __init__(self, parent=None):
        super().__init__(parent)
        self.conn_manager = get_connection_manager()
        self.init_ui()

    def init_ui(self):
        """Initialize the UI"""
        self.setWindowTitle("Add New Connection")
        self.setModal(True)
        self.setMinimumWidth(500)

        # Main layout
        layout = QVBoxLayout(self)
        layout.setSpacing(15)

        # Header
        header = QLabel("Add New Database Connection")
        header.setStyleSheet("""
            font-size: 18px;
            font-weight: 800;
            color: #FFD700;
            padding: 10px;
        """)
        header.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(header)

        # Connection details group
        details_group = QGroupBox("Connection Details")
        details_layout = QFormLayout()
        details_layout.setSpacing(12)

        # Connection name
        self.name_input = QLineEdit()
        self.name_input.setPlaceholderText("e.g., Production Database")
        details_layout.addRow("Connection Name:", self.name_input)

        # Connection type
        self.type_combo = QComboBox()
        self.type_combo.addItems([
            "SQL_SERVER",
            "SQLITE",
            "POSTGRESQL",
            "MYSQL",
            "ORACLE",
            "DB2"
        ])
        self.type_combo.currentTextChanged.connect(self.on_type_changed)
        details_layout.addRow("Database Type:", self.type_combo)

        # Server name
        self.server_input = QLineEdit()
        self.server_input.setPlaceholderText("e.g., localhost or server.company.com")
        details_layout.addRow("Server/Host:", self.server_input)

        # Database name
        self.database_input = QLineEdit()
        self.database_input.setPlaceholderText("e.g., MyDatabase")
        details_layout.addRow("Database Name:", self.database_input)

        details_group.setLayout(details_layout)
        layout.addWidget(details_group)

        # Authentication group
        auth_group = QGroupBox("Authentication")
        auth_layout = QVBoxLayout()
        auth_layout.setSpacing(10)

        # Auth type radio buttons
        self.auth_button_group = QButtonGroup(self)

        self.windows_auth_radio = QRadioButton("Windows Authentication (Trusted)")
        self.sql_auth_radio = QRadioButton("SQL Server Authentication")
        self.sql_auth_radio.setChecked(True)

        self.auth_button_group.addButton(self.windows_auth_radio)
        self.auth_button_group.addButton(self.sql_auth_radio)

        self.windows_auth_radio.toggled.connect(self.on_auth_type_changed)

        auth_layout.addWidget(self.windows_auth_radio)
        auth_layout.addWidget(self.sql_auth_radio)

        # Credentials form
        self.cred_form = QFormLayout()
        self.cred_form.setSpacing(12)

        self.username_input = QLineEdit()
        self.username_input.setPlaceholderText("Username")
        self.cred_form.addRow("Username:", self.username_input)

        self.password_input = QLineEdit()
        self.password_input.setPlaceholderText("Password")
        self.password_input.setEchoMode(QLineEdit.EchoMode.Password)
        self.cred_form.addRow("Password:", self.password_input)

        auth_layout.addLayout(self.cred_form)
        auth_group.setLayout(auth_layout)
        layout.addWidget(auth_group)

        # Buttons
        button_layout = QHBoxLayout()
        button_layout.addStretch()

        self.test_button = QPushButton("Test Connection")
        self.test_button.setObjectName("secondary_button")
        self.test_button.clicked.connect(self.test_connection)
        button_layout.addWidget(self.test_button)

        self.save_button = QPushButton("Save Connection")
        self.save_button.setObjectName("gold_button")
        self.save_button.clicked.connect(self.save_connection)
        button_layout.addWidget(self.save_button)

        self.cancel_button = QPushButton("Cancel")
        self.cancel_button.setObjectName("secondary_button")
        self.cancel_button.clicked.connect(self.reject)
        button_layout.addWidget(self.cancel_button)

        layout.addLayout(button_layout)

        # Initial state
        self.on_type_changed(self.type_combo.currentText())
        self.on_auth_type_changed()

    def on_type_changed(self, conn_type: str):
        """Handle connection type change"""
        # SQLite doesn't need server or auth
        is_sqlite = conn_type == "SQLITE"

        self.server_input.setEnabled(not is_sqlite)
        if is_sqlite:
            self.server_input.clear()
            self.server_input.setPlaceholderText("(Not needed for SQLite)")
            self.database_input.setPlaceholderText("Path to .db file")
            self.windows_auth_radio.setEnabled(False)
            self.sql_auth_radio.setEnabled(False)
            self.username_input.setEnabled(False)
            self.password_input.setEnabled(False)
        else:
            self.server_input.setPlaceholderText("e.g., localhost or server.company.com")
            self.database_input.setPlaceholderText("e.g., MyDatabase")
            self.windows_auth_radio.setEnabled(conn_type == "SQL_SERVER")
            self.sql_auth_radio.setEnabled(True)
            self.on_auth_type_changed()

    def on_auth_type_changed(self):
        """Handle authentication type change"""
        is_windows_auth = self.windows_auth_radio.isChecked()
        conn_type = self.type_combo.currentText()

        # Windows auth only available for SQL Server
        if conn_type != "SQL_SERVER":
            is_windows_auth = False

        self.username_input.setEnabled(not is_windows_auth)
        self.password_input.setEnabled(not is_windows_auth)

    def validate_inputs(self) -> tuple[bool, str]:
        """Validate form inputs"""
        if not self.name_input.text().strip():
            return False, "Please enter a connection name"

        if not self.database_input.text().strip():
            return False, "Please enter a database name"

        conn_type = self.type_combo.currentText()

        if conn_type != "SQLITE" and not self.server_input.text().strip():
            return False, "Please enter a server/host name"

        # Check credentials if not Windows auth
        if not self.windows_auth_radio.isChecked():
            if conn_type != "SQLITE":
                if not self.username_input.text().strip():
                    return False, "Please enter a username"
                if not self.password_input.text().strip():
                    return False, "Please enter a password"

        return True, ""

    def test_connection(self):
        """Test the connection"""
        # Validate inputs first
        is_valid, error_msg = self.validate_inputs()
        if not is_valid:
            QMessageBox.warning(self, "Validation Error", error_msg)
            return

        # Create temporary connection to test
        try:
            conn_id = self._create_connection()

            # Test it
            success, message = self.conn_manager.test_connection(conn_id)

            # Delete the temporary connection
            self.conn_manager.delete_connection(conn_id)

            if success:
                QMessageBox.information(self, "Connection Test", message)
            else:
                QMessageBox.warning(self, "Connection Test Failed", message)

        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to test connection:\n{str(e)}")

    def save_connection(self):
        """Save the connection"""
        # Validate inputs
        is_valid, error_msg = self.validate_inputs()
        if not is_valid:
            QMessageBox.warning(self, "Validation Error", error_msg)
            return

        try:
            # Create connection
            conn_id = self._create_connection()

            # Emit signal
            self.connection_added.emit(conn_id)

            # Show success message
            QMessageBox.information(self, "Success",
                                  f"Connection '{self.name_input.text()}' added successfully!")

            # Close dialog
            self.accept()

        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to save connection:\n{str(e)}")

    def _create_connection(self) -> int:
        """Create the connection and return its ID"""
        name = self.name_input.text().strip()
        conn_type = self.type_combo.currentText()
        server = self.server_input.text().strip()
        database = self.database_input.text().strip()

        auth_type = "WINDOWS" if self.windows_auth_radio.isChecked() else "SQL_AUTH"
        username = self.username_input.text().strip() if not self.windows_auth_radio.isChecked() else None
        password = self.password_input.text().strip() if not self.windows_auth_radio.isChecked() else None

        # For SQLite, use empty server
        if conn_type == "SQLITE":
            server = ""
            auth_type = "NONE"

        return self.conn_manager.add_connection(
            name=name,
            conn_type=conn_type,
            server=server,
            database=database,
            auth_type=auth_type,
            username=username,
            password=password
        )
