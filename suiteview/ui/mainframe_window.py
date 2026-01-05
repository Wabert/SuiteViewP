"""
Mainframe Window - Dedicated window for Mainframe Navigation and Terminal
"""

import logging
from PyQt6.QtWidgets import (QMainWindow, QTabWidget, QWidget, QVBoxLayout, QHBoxLayout, QStatusBar, QLabel, QPushButton, QDialog, QFormLayout, QLineEdit, QDialogButtonBox, QMessageBox)
from PyQt6.QtGui import QIcon
from PyQt6.QtCore import QSize, Qt

from suiteview.ui.mainframe_nav_screen import MainframeNavScreen
from suiteview.ui.mainframe_terminal_screen import DualTerminalScreen
from suiteview.core.connection_manager import ConnectionManager
from suiteview.core.credential_manager import CredentialManager

logger = logging.getLogger(__name__)

class MainframeWindow(QMainWindow):
    """Dedicated window for Mainframe tools"""

    def __init__(self):
        super().__init__()
        self.conn_manager = ConnectionManager()
        self.cred_manager = CredentialManager()
        self.init_ui()
        logger.info("Mainframe window initialized")

    def init_ui(self):
        """Initialize the UI"""
        self.setWindowTitle("SuiteView - Mainframe Tools")
        self.resize(1400, 800)
        # Allow window to be resized quite small
        self.setMinimumSize(600, 400)

        # Create central widget
        central_widget = QWidget()
        self.setCentralWidget(central_widget)

        # Create main layout
        layout = QVBoxLayout(central_widget)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # Create tab widget
        self.tab_widget = QTabWidget()
        self.tab_widget.setTabPosition(QTabWidget.TabPosition.North)
        self.tab_widget.setDocumentMode(True)

        # Create screens
        self.mainframe_nav_screen = MainframeNavScreen(self.conn_manager)
        self.mainframe_terminal_screen = DualTerminalScreen()

        # Add tabs - Terminal first
        self.tab_widget.addTab(self.mainframe_terminal_screen, "Mainframe Terminal")
        self.tab_widget.addTab(self.mainframe_nav_screen, "Mainframe Nav")

        # Add tab widget to layout
        layout.addWidget(self.tab_widget)
        
        # Add status bar with User button on left and size display on right
        self.statusBar = QStatusBar()
        self.setStatusBar(self.statusBar)
        
        # User button on the left
        self.user_button = QPushButton("👤 User")
        self.user_button.setStyleSheet("""
            QPushButton {
                background-color: transparent;
                color: #666;
                padding: 2px 8px;
                border: 1px solid #ccc;
                border-radius: 3px;
                font-size: 9pt;
            }
            QPushButton:hover {
                background-color: #f0f0f0;
                color: #333;
                border: 1px solid #999;
            }
        """)
        self.user_button.clicked.connect(self.show_user_credentials_dialog)
        self.user_button.setFixedHeight(20)
        self.statusBar.addWidget(self.user_button)
        
        # Size label on the right
        self.size_label = QLabel()
        self.size_label.setStyleSheet("color: #888; font-size: 11px; padding: 2px 5px;")
        self.statusBar.addPermanentWidget(self.size_label)
        self._update_size_label()
    
    def resizeEvent(self, event):
        """Handle window resize to update size display"""
        super().resizeEvent(event)
        self._update_size_label()
    
    def _update_size_label(self):
        """Update the size label with current window dimensions"""
        size = self.size()
        self.size_label.setText(f"{size.width()} x {size.height()}")
    
    def show_user_credentials_dialog(self):
        """Show dialog to set user credentials"""
        dialog = QDialog(self)
        dialog.setWindowTitle("User Credentials")
        dialog.setModal(True)
        dialog.resize(400, 200)
        
        layout = QFormLayout(dialog)
        
        # Info label
        info_label = QLabel("Enter your mainframe credentials.\nThese will be used for both Terminal and Navigation.")
        info_label.setStyleSheet("color: #555; font-style: italic; margin-bottom: 10px;")
        layout.addRow(info_label)
        
        # Load existing credentials if any
        all_connections = self.conn_manager.get_connections()
        existing_conn = None
        
        for conn in all_connections:
            if conn.get('connection_name') == "MAINFRAME_USER":
                existing_conn = conn
                break
        
        # Username field
        username_input = QLineEdit()
        username_input.setPlaceholderText("Enter username (e.g., ab7y02)")
        if existing_conn:
            # Decrypt username
            encrypted_user = existing_conn.get('encrypted_username')
            if encrypted_user:
                try:
                    decrypted_user = self.cred_manager.decrypt(encrypted_user)
                    username_input.setText(decrypted_user)
                except:
                    pass
        layout.addRow("Username:", username_input)
        
        # Password field
        password_input = QLineEdit()
        password_input.setEchoMode(QLineEdit.EchoMode.Password)
        password_input.setPlaceholderText("Enter password")
        if existing_conn:
            # Decrypt password
            encrypted_pw = existing_conn.get('encrypted_password')
            if encrypted_pw:
                try:
                    decrypted_pw = self.cred_manager.decrypt(encrypted_pw)
                    password_input.setText(decrypted_pw)
                except:
                    pass
        layout.addRow("Password:", password_input)
        
        # Buttons
        button_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel)
        button_box.accepted.connect(lambda: self.save_user_credentials(dialog, username_input.text(), password_input.text()))
        button_box.rejected.connect(dialog.reject)
        layout.addRow(button_box)
        
        dialog.exec()
    
    def save_user_credentials(self, dialog, username, password):
        """Save user credentials"""
        if not username or not password:
            QMessageBox.warning(dialog, "Missing Information", "Please enter both username and password.")
            return
        
        try:
            # Check if connection exists
            all_connections = self.conn_manager.get_connections()
            existing_conn = None
            conn_id = None
            
            for conn in all_connections:
                if conn.get('connection_name') == "MAINFRAME_USER":
                    existing_conn = conn
                    conn_id = conn.get('id')
                    break
            
            # Encrypt password
            encrypted_password = self.cred_manager.encrypt(password)
            
            if existing_conn:
                # Update existing connection
                self.conn_manager.update_connection(
                    conn_id,
                    connection_name="MAINFRAME_USER",
                    encrypted_username=self.cred_manager.encrypt(username),
                    encrypted_password=encrypted_password
                )
            else:
                # Create new connection
                self.conn_manager.add_connection(
                    name="MAINFRAME_USER",
                    conn_type="Generic",
                    server="",
                    database="",
                    auth_type="SQL_AUTH",
                    username=username,
                    password=password
                )
            
            QMessageBox.information(dialog, "Credentials Saved", 
                                  "Your credentials have been saved successfully.\n\n"
                                  "They will be used for mainframe connections in both Terminal and Navigation.")
            dialog.accept()
            
            logger.info(f"User credentials saved for: {username}")
            
        except Exception as e:
            logger.error(f"Failed to save credentials: {e}")
            QMessageBox.critical(dialog, "Save Error", f"Failed to save credentials:\n{str(e)}")
        
    def closeEvent(self, event):
        """Handle window close"""
        # Disconnect terminals if connected
        if hasattr(self.mainframe_terminal_screen, 'disconnect_all'):
            self.mainframe_terminal_screen.disconnect_all()
        elif hasattr(self.mainframe_terminal_screen, 'disconnect_from_mainframe'):
            self.mainframe_terminal_screen.disconnect_from_mainframe()
            
        super().closeEvent(event)
