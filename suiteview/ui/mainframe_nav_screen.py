"""
Mainframe Navigation Screen - File explorer interface for browsing mainframe datasets
"""

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QSplitter, QTextEdit, QLineEdit, QPushButton,
    QLabel, QMessageBox, QTreeWidget, QTreeWidgetItem, QTableWidget, QTableWidgetItem,
    QHeaderView, QDialog, QDialogButtonBox, QStyle
)
from PyQt6.QtCore import Qt, QThread, pyqtSignal
from PyQt6.QtGui import QFont, QIcon
from datetime import datetime
import logging

logger = logging.getLogger(__name__)


class FTPConnectionThread(QThread):
    """Background thread for FTP connection"""
    connection_success = pyqtSignal(object)  # Emits FTP manager object
    connection_failed = pyqtSignal(str)  # Emits error message
    
    def __init__(self, host, username, password, port, initial_path):
        super().__init__()
        self.host = host
        self.username = username
        self.password = password
        self.port = port
        self.initial_path = initial_path
    
    def run(self):
        """Run FTP connection in background"""
        try:
            from suiteview.core.ftp_manager import MainframeFTPManager
            
            ftp_manager = MainframeFTPManager(
                host=self.host,
                username=self.username,
                password=self.password,
                port=self.port,
                initial_path=self.initial_path
            )
            
            ftp_manager.connect()
            self.connection_success.emit(ftp_manager)
            
        except Exception as e:
            logger.error(f"FTP connection error: {str(e)}")
            self.connection_failed.emit(str(e))


class MainframeNavScreen(QWidget):
    """Mainframe navigation screen with file explorer layout"""
    
    def __init__(self, conn_manager):
        super().__init__()
        self.conn_manager = conn_manager
        self.current_connection_id = None
        self.ftp_manager = None
        self.current_dataset = ""
        self.current_member_content = ""
        self.connection_thread = None  # For background FTP connection
        
        # Connection settings
        self.connection_settings = {
            'host': 'PRODESA',
            'port': 21,
            'username': '',
            'password': '',
            'initial_path': ''
        }
        
        self.init_ui()
        self.load_default_settings()
        
    def init_ui(self):
        """Initialize the user interface"""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(5, 5, 5, 5)
        layout.setSpacing(2)
        
        # Top bar with connection button and dataset input
        top_bar = QHBoxLayout()
        top_bar.setSpacing(5)
        
        # Connection Details button
        self.connection_button = QPushButton("⚙️ Connection Details")
        self.connection_button.setFixedWidth(150)
        self.connection_button.clicked.connect(self.show_connection_dialog)
        self.connection_button.setStyleSheet("""
            QPushButton {
                background-color: #34495e;
                color: white;
                border: none;
                padding: 8px;
                font-weight: bold;
                border-radius: 4px;
            }
            QPushButton:hover {
                background-color: #2c3e50;
            }
        """)
        top_bar.addWidget(self.connection_button)
        
        # Dataset input
        dataset_label = QLabel("Dataset:")
        dataset_label.setStyleSheet("font-weight: bold;")
        top_bar.addWidget(dataset_label)
        
        self.dataset_edit = QLineEdit()
        self.dataset_edit.setPlaceholderText("e.g., d03.aa0139.CKAS.cirf.data")
        self.dataset_edit.returnPressed.connect(self.load_dataset)
        top_bar.addWidget(self.dataset_edit)
        
        # Load button
        self.load_button = QPushButton("Load Dataset")
        self.load_button.setFixedWidth(120)
        self.load_button.clicked.connect(self.load_dataset)
        self.load_button.setEnabled(False)
        self.load_button.setStyleSheet("""
            QPushButton {
                background-color: #3498db;
                color: white;
                border: none;
                padding: 8px;
                font-weight: bold;
                border-radius: 4px;
            }
            QPushButton:hover {
                background-color: #2980b9;
            }
            QPushButton:disabled {
                background-color: #bdc3c7;
            }
        """)
        top_bar.addWidget(self.load_button)
        
        layout.addLayout(top_bar)
        
        # Main splitter with 3 panels: Folder Tree | Folder Content | File View Window
        main_splitter = QSplitter(Qt.Orientation.Horizontal)
        
        # LEFT PANEL - Folder Tree
        tree_widget = QWidget()
        tree_layout = QVBoxLayout(tree_widget)
        tree_layout.setContentsMargins(0, 0, 0, 0)
        tree_layout.setSpacing(2)
        
        tree_header = QLabel("📁 Folder Tree")
        tree_header.setStyleSheet(
            "font-weight: bold; "
            "padding: 6px; "
            "background-color: #2c5f8d; "
            "color: white; "
            "border-radius: 3px;"
        )
        tree_layout.addWidget(tree_header)
        
        self.folder_tree = QTreeWidget()
        self.folder_tree.setHeaderHidden(True)  # Hide the "Path" header
        self.folder_tree.itemClicked.connect(self.on_tree_item_clicked)
        tree_layout.addWidget(self.folder_tree)
        
        main_splitter.addWidget(tree_widget)
        
        # MIDDLE PANEL - Folder Content
        content_widget = QWidget()
        content_layout = QVBoxLayout(content_widget)
        content_layout.setContentsMargins(0, 0, 0, 0)
        content_layout.setSpacing(2)
        
        content_header = QLabel("📄 Folder Content")
        content_header.setStyleSheet(
            "font-weight: bold; "
            "padding: 6px; "
            "background-color: #2c5f8d; "
            "color: white; "
            "border-radius: 3px;"
        )
        content_layout.addWidget(content_header)
        
        self.members_table = QTableWidget()
        self.members_table.setColumnCount(3)
        self.members_table.setHorizontalHeaderLabels(["Name", "Date Modified", "Type"])
        
        # Style like Windows File Explorer
        self.members_table.verticalHeader().setVisible(False)  # Hide row numbers
        self.members_table.setShowGrid(False)  # No grid lines
        self.members_table.setAlternatingRowColors(True)
        self.members_table.horizontalHeader().setDefaultAlignment(Qt.AlignmentFlag.AlignLeft)
        self.members_table.horizontalHeader().setStyleSheet("""
            QHeaderView::section {
                background-color: #f0f0f0;
                padding: 4px;
                border: none;
                border-bottom: 1px solid #d0d0d0;
                font-weight: normal;
                font-size: 11px;
            }
        """)
        
        self.members_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.members_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        self.members_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        self.members_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.members_table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        self.members_table.itemSelectionChanged.connect(self.on_member_selected)
        content_layout.addWidget(self.members_table)
        
        main_splitter.addWidget(content_widget)
        
        # RIGHT PANEL - File View Window
        right_widget = QWidget()
        right_layout = QVBoxLayout(right_widget)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.setSpacing(2)
        
        right_header = QLabel("👁️ File View Window")
        right_header.setStyleSheet(
            "font-weight: bold; "
            "padding: 6px; "
            "background-color: #2c5f8d; "
            "color: white; "
            "border-radius: 3px;"
        )
        right_layout.addWidget(right_header)
        
        self.file_preview = QTextEdit()
        self.file_preview.setReadOnly(True)
        self.file_preview.setFont(QFont("Courier New", 9))
        self.file_preview.setPlaceholderText("Select a member to view its contents (first 1000 rows)...")
        right_layout.addWidget(self.file_preview)
        
        # Buttons below preview
        button_layout = QHBoxLayout()
        button_layout.setSpacing(10)
        
        self.view_all_button = QPushButton("View All")
        self.view_all_button.setFixedWidth(100)
        self.view_all_button.clicked.connect(self.view_all_lines)
        self.view_all_button.setEnabled(False)
        button_layout.addWidget(self.view_all_button)
        
        button_layout.addStretch()
        
        self.export_button = QPushButton("Export")
        self.export_button.setFixedWidth(100)
        self.export_button.clicked.connect(self.export_member)
        self.export_button.setEnabled(False)
        button_layout.addWidget(self.export_button)
        
        right_layout.addLayout(button_layout)
        
        main_splitter.addWidget(right_widget)
        
        # Set splitter sizes (20% tree, 20% content, 60% preview)
        main_splitter.setSizes([250, 250, 700])
        
        layout.addWidget(main_splitter)
        
        # Status label at bottom
        self.status_label = QLabel("Click 'Connection Details' to configure connection")
        self.status_label.setStyleSheet("color: #7f8c8d; font-style: italic; padding: 2px; font-size: 11px;")
        self.status_label.setMaximumHeight(20)
        layout.addWidget(self.status_label)
    
    def show_connection_dialog(self):
        """Show dialog to edit connection settings"""
        dialog = QDialog(self)
        dialog.setWindowTitle("Mainframe FTP Connection Settings")
        dialog.setModal(True)
        dialog.resize(400, 250)
        
        layout = QVBoxLayout(dialog)
        
        # Connection form
        form_widget = QWidget()
        form_layout = QVBoxLayout(form_widget)
        
        # Host
        host_layout = QHBoxLayout()
        host_layout.addWidget(QLabel("Host:"))
        host_edit = QLineEdit(self.connection_settings['host'])
        host_layout.addWidget(host_edit)
        form_layout.addLayout(host_layout)
        
        # Port
        port_layout = QHBoxLayout()
        port_layout.addWidget(QLabel("Port:"))
        port_edit = QLineEdit(str(self.connection_settings['port']))
        port_layout.addWidget(port_edit)
        form_layout.addLayout(port_layout)
        
        # Username
        user_layout = QHBoxLayout()
        user_layout.addWidget(QLabel("Username:"))
        user_edit = QLineEdit(self.connection_settings['username'])
        user_layout.addWidget(user_edit)
        form_layout.addLayout(user_layout)
        
        # Password
        pass_layout = QHBoxLayout()
        pass_layout.addWidget(QLabel("Password:"))
        pass_edit = QLineEdit(self.connection_settings['password'])
        pass_edit.setEchoMode(QLineEdit.EchoMode.Password)
        pass_layout.addWidget(pass_edit)
        form_layout.addLayout(pass_layout)
        
        layout.addWidget(form_widget)
        
        # Buttons
        button_box = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        button_box.accepted.connect(dialog.accept)
        button_box.rejected.connect(dialog.reject)
        layout.addWidget(button_box)
        
        if dialog.exec() == QDialog.DialogCode.Accepted:
            # Save settings
            self.connection_settings['host'] = host_edit.text()
            self.connection_settings['port'] = int(port_edit.text())
            self.connection_settings['username'] = user_edit.text()
            self.connection_settings['password'] = pass_edit.text()
            
            # Save credentials to the first MAINFRAME_FTP connection
            self.save_credentials_to_connection(
                self.connection_settings['username'],
                self.connection_settings['password'],
                self.connection_settings['host'],
                self.connection_settings['port'],
                self.connection_settings['initial_path']
            )
            
            # Reconnect with new settings
            self.connect_to_mainframe()
    
    def save_credentials_to_connection(self, username, password, host, port, initial_path):
        """Save credentials to the first MAINFRAME_FTP connection in database"""
        try:
            # Get all connections using the correct method
            connections = self.conn_manager.repo.get_all_connections()
            ftp_connections = [c for c in connections if c.get('connection_type') == 'MAINFRAME_FTP']
            
            from suiteview.core.credential_manager import CredentialManager
            cred_manager = CredentialManager()
            
            # Encrypt credentials
            encrypted_username = cred_manager.encrypt(username)
            encrypted_password = cred_manager.encrypt(password)
            
            # Build connection string with FTP parameters
            conn_string = f"port={port};initial_path={initial_path}"
            
            if ftp_connections:
                # Update existing connection - use connection_id not 'id'
                conn_id = ftp_connections[0].get('connection_id')
                
                self.conn_manager.repo.update_connection(
                    conn_id,
                    server_name=host,
                    encrypted_username=encrypted_username,
                    encrypted_password=encrypted_password,
                    connection_string=conn_string
                )
                
                logger.info(f"Updated credentials for MAINFRAME_FTP connection (ID: {conn_id})")
                QMessageBox.information(
                    self,
                    "Credentials Saved",
                    "Your mainframe credentials have been saved successfully!"
                )
            else:
                # Create new connection if none exists
                self.conn_manager.repo.add_connection(
                    connection_name='Mainframe FTP',
                    connection_type='MAINFRAME_FTP',
                    server_name=host,
                    database_name='',
                    auth_type='password',
                    encrypted_username=encrypted_username,
                    encrypted_password=encrypted_password,
                    connection_string=conn_string
                )
                
                logger.info("Created new MAINFRAME_FTP connection with credentials")
                QMessageBox.information(
                    self,
                    "Credentials Saved",
                    "Your mainframe credentials have been saved successfully!"
                )
                
        except Exception as e:
            logger.error(f"Failed to save credentials: {str(e)}", exc_info=True)
            from PyQt6.QtWidgets import QMessageBox
            QMessageBox.warning(
                self, 
                "Save Error", 
                f"Failed to save credentials to database:\n{str(e)}"
            )
    
    def connect_to_mainframe(self):
        """Connect to mainframe FTP in background thread"""
        try:
            # Disable buttons during connection
            self.load_button.setEnabled(False)
            self.connection_button.setEnabled(False)
            
            self.status_label.setText("Connecting to mainframe...")
            self.status_label.setStyleSheet("color: #3498db; font-style: italic; padding: 2px; font-size: 11px;")
            
            # Start connection in background thread
            self.connection_thread = FTPConnectionThread(
                host=self.connection_settings['host'],
                username=self.connection_settings['username'],
                password=self.connection_settings['password'],
                port=self.connection_settings['port'],
                initial_path=self.connection_settings['initial_path']
            )
            
            # Connect signals
            self.connection_thread.connection_success.connect(self.on_connection_success)
            self.connection_thread.connection_failed.connect(self.on_connection_failed)
            
            # Start the thread
            self.connection_thread.start()
            
        except Exception as e:
            logger.error(f"Failed to start connection: {str(e)}")
            self.on_connection_failed(str(e))
    
    def on_connection_success(self, ftp_manager):
        """Handle successful FTP connection"""
        self.ftp_manager = ftp_manager
        self.status_label.setText("✓ Connected to mainframe")
        self.status_label.setStyleSheet("color: #27ae60; font-weight: bold; padding: 2px; font-size: 11px;")
        self.load_button.setEnabled(True)
        self.connection_button.setEnabled(True)
        logger.info("Successfully connected to mainframe")
    
    def on_connection_failed(self, error_message):
        """Handle failed FTP connection"""
        self.ftp_manager = None
        self.load_button.setEnabled(False)
        self.connection_button.setEnabled(True)
        
        # Check for common connection issues
        if "timed out" in error_message.lower() or "timeout" in error_message.lower():
            user_message = "Connection timed out. The mainframe server may be down or unreachable."
            self.status_label.setText("✗ Connection timeout - Mainframe may be down")
        elif "refused" in error_message.lower():
            user_message = "Connection refused. The mainframe FTP service may be down or blocked by firewall."
            self.status_label.setText("✗ Connection refused - FTP service may be down")
        elif "name or service not known" in error_message.lower() or "no such host" in error_message.lower():
            user_message = f"Cannot resolve host '{self.connection_settings['host']}'. Check the hostname."
            self.status_label.setText("✗ Host not found")
        elif "authentication" in error_message.lower() or "login" in error_message.lower():
            user_message = "Authentication failed. Check your username and password."
            self.status_label.setText("✗ Authentication failed")
        else:
            user_message = f"Connection failed: {error_message}"
            self.status_label.setText("✗ Connection failed")
        
        self.status_label.setStyleSheet("color: #e74c3c; font-weight: bold; padding: 2px; font-size: 11px;")
        
        QMessageBox.warning(
            self, 
            "Mainframe Connection Failed", 
            f"{user_message}\n\n"
            f"Host: {self.connection_settings['host']}\n"
            f"Port: {self.connection_settings['port']}\n\n"
            "Please check:\n"
            "• The mainframe is online and accessible\n"
            "• Your network connection is working\n"
            "• The FTP service is running\n"
            "• Your credentials are correct"
        )
        
        logger.error(f"Mainframe connection failed: {error_message}")
    
    def load_dataset(self):
        """Load dataset and populate tree structure"""
        if not self.ftp_manager:
            QMessageBox.warning(self, "Not Connected", "Please connect to mainframe first")
            return
        
        path = self.dataset_edit.text().strip()
        if not path:
            QMessageBox.warning(self, "No Dataset", "Please enter a dataset path")
            return
        
        try:
            self.status_label.setText("Loading dataset...")
            self.status_label.setStyleSheet("color: #3498db; font-style: italic; padding: 4px;")
            
            # Parse the dataset path
            parts = path.split('.')
            
            # Clear existing tree
            self.folder_tree.clear()
            self.members_table.setRowCount(0)
            self.file_preview.clear()
            
            # Build tree structure
            current_item = None
            full_path = ""
            
            # Get folder icon from system
            folder_icon = self.style().standardIcon(QStyle.StandardPixmap.SP_DirIcon)
            
            for i, part in enumerate(parts):
                if i == 0:
                    # Root level
                    current_item = QTreeWidgetItem(self.folder_tree, [part])
                    full_path = part
                else:
                    # Child level
                    full_path += f".{part}"
                    current_item = QTreeWidgetItem(current_item, [part])
                
                # Add folder icon
                current_item.setIcon(0, folder_icon)
                
                # Store the full path in the item
                current_item.setData(0, Qt.ItemDataRole.UserRole, full_path)
            
            # Expand all nodes
            self.folder_tree.expandAll()
            
            # Select the last item (the actual dataset)
            if current_item:
                self.folder_tree.setCurrentItem(current_item)
                self.current_dataset = full_path
                
                # Load members for this dataset
                self.load_members(full_path)
            
            self.status_label.setText(f"✓ Loaded dataset: {path}")
            self.status_label.setStyleSheet("color: #27ae60; font-weight: bold; padding: 4px;")
            
        except Exception as e:
            logger.error(f"Failed to load dataset: {str(e)}")
            self.status_label.setText(f"✗ Failed to load dataset")
            self.status_label.setStyleSheet("color: #e74c3c; font-weight: bold; padding: 4px;")
            QMessageBox.critical(self, "Load Error", f"Failed to load dataset:\n{str(e)}")
    
    def on_tree_item_clicked(self, item, column):
        """Handle tree item click"""
        dataset_path = item.data(0, Qt.ItemDataRole.UserRole)
        if dataset_path:
            self.current_dataset = dataset_path
            self.load_members(dataset_path)
    
    def load_members(self, dataset_path):
        """Load members/files for the selected dataset"""
        try:
            self.members_table.setRowCount(0)
            self.file_preview.clear()
            
            # Get icons
            folder_icon = self.style().standardIcon(QStyle.StandardPixmap.SP_DirIcon)
            file_icon = self.style().standardIcon(QStyle.StandardPixmap.SP_FileIcon)
            
            items_to_display = []
            
            # Check if this path could have child folders by looking at the full dataset path
            # For example, if full path is "d03.aa0139.CKAS.cirf.data" and current is "d03.aa0139.CKAS.cirf"
            # we should show "data" as a folder
            if self.dataset_edit.text().strip():
                full_dataset = self.dataset_edit.text().strip()
                current_parts = dataset_path.split('.')
                full_parts = full_dataset.split('.')
                
                # If current path is shorter than full path, show the next level as a folder
                if len(current_parts) < len(full_parts):
                    next_part = full_parts[len(current_parts)]
                    items_to_display.append({
                        'name': next_part,
                        'type': 'File folder',
                        'modified': '',
                        'is_folder': True
                    })
            
            # Always try to list members (files) in the dataset from FTP
            try:
                members = self.ftp_manager.list_datasets(dataset_path)
                
                if members:
                    for member in members:
                        items_to_display.append({
                            'name': member.get('name', ''),
                            'type': 'Member',
                            'modified': member.get('modified', ''),
                            'is_folder': False
                        })
            except Exception as e:
                logger.debug(f"No members found or error listing: {str(e)}")
            
            if not items_to_display:
                self.status_label.setText(f"No items found in {dataset_path}")
                return
            
            # Populate members table
            self.members_table.setRowCount(len(items_to_display))
            
            for row, item in enumerate(items_to_display):
                # Name with icon
                name_item = QTableWidgetItem(item['name'])
                if item['is_folder']:
                    name_item.setIcon(folder_icon)
                else:
                    name_item.setIcon(file_icon)
                self.members_table.setItem(row, 0, name_item)
                
                # Date
                date_item = QTableWidgetItem(item['modified'])
                self.members_table.setItem(row, 1, date_item)
                
                # Type
                type_item = QTableWidgetItem(item['type'])
                self.members_table.setItem(row, 2, type_item)
            
            folder_count = sum(1 for item in items_to_display if item['is_folder'])
            file_count = len(items_to_display) - folder_count
            self.status_label.setText(f"Found {folder_count} folder(s) and {file_count} member(s) in {dataset_path}")
            
        except Exception as e:
            logger.error(f"Failed to load members: {str(e)}")
            self.status_label.setText(f"✗ Failed to load members")
            QMessageBox.warning(self, "Load Error", f"Failed to load members:\n{str(e)}")
    
    def on_member_selected(self):
        """Handle member selection - show preview or navigate into folder"""
        selected_rows = self.members_table.selectedItems()
        if not selected_rows:
            return
        
        # Get the name and type from the selected row
        row = selected_rows[0].row()
        member_name = self.members_table.item(row, 0).text()
        member_type = self.members_table.item(row, 2).text()
        
        if not member_name:
            return
        
        logger.info(f"Member selected: {member_name} (Type: {member_type})")
        
        # If it's a folder, navigate into it
        if member_type == "File folder":
            new_path = f"{self.current_dataset}.{member_name}"
            self.current_dataset = new_path
            self.load_members(new_path)
            return
        
        # Check if FTP manager is connected
        if not self.ftp_manager:
            QMessageBox.warning(
                self,
                "Not Connected",
                "FTP connection lost. Please reconnect to mainframe."
            )
            return
        
        # If it's a file/member, show preview
        try:
            # Build full member path using PDS member syntax: DATASET(MEMBER)
            member_path = f"{self.current_dataset}({member_name})"
            
            logger.info(f"Loading member: {member_path}")
            self.status_label.setText(f"Loading {member_name}...")
            self.status_label.setStyleSheet("color: #3498db; font-style: italic; padding: 2px; font-size: 11px;")
            
            # Read first 1000 rows
            content, line_count = self.ftp_manager.read_dataset(member_path, max_lines=1000)
            
            logger.info(f"Loaded {line_count} lines from {member_name}")
            
            self.file_preview.setPlainText(content)
            self.current_member_content = member_path
            
            # Enable buttons
            self.view_all_button.setEnabled(True)
            self.export_button.setEnabled(True)
            
            self.status_label.setText(f"✓ Showing first 1000 rows of {member_name} (Total: {line_count} lines)")
            self.status_label.setStyleSheet("color: #27ae60; font-weight: bold; padding: 2px; font-size: 11px;")
            
        except Exception as e:
            logger.error(f"Failed to load member preview: {str(e)}", exc_info=True)
            self.status_label.setText(f"✗ Failed to load member: {str(e)}")
            self.status_label.setStyleSheet("color: #e74c3c; font-weight: bold; padding: 2px; font-size: 11px;")
            QMessageBox.critical(self, "Preview Error", f"Failed to load member:\n{str(e)}")
    
    def view_all_lines(self):
        """View all lines of the selected member"""
        if not self.current_member_content:
            return
        
        try:
            self.status_label.setText("Loading all lines...")
            
            content, line_count = self.ftp_manager.read_dataset(self.current_member_content, max_lines=None)
            
            self.file_preview.setPlainText(content)
            
            self.status_label.setText(f"✓ Showing all {line_count} lines")
            self.status_label.setStyleSheet("color: #27ae60; font-weight: bold; padding: 4px;")
            
        except Exception as e:
            logger.error(f"Failed to load all lines: {str(e)}")
            QMessageBox.critical(self, "Load Error", f"Failed to load all lines:\n{str(e)}")
    
    def export_member(self):
        """Export current member to file"""
        if not self.current_member_content:
            return
        
        try:
            from PyQt6.QtWidgets import QFileDialog
            
            # Get filename from user
            filename, _ = QFileDialog.getSaveFileName(
                self,
                "Export Member",
                f"{self.current_member_content.split('.')[-1]}.txt",
                "Text Files (*.txt);;All Files (*.*)"
            )
            
            if not filename:
                return
            
            self.status_label.setText("Exporting...")
            
            # Read all content
            content, _ = self.ftp_manager.read_dataset(self.current_member_content, max_lines=None)
            
            # Write to file
            with open(filename, 'w', encoding='utf-8') as f:
                f.write(content)
            
            self.status_label.setText(f"✓ Exported to {filename}")
            self.status_label.setStyleSheet("color: #27ae60; font-weight: bold; padding: 4px;")
            QMessageBox.information(self, "Export Complete", f"Member exported to:\n{filename}")
            
        except Exception as e:
            logger.error(f"Failed to export member: {str(e)}")
            QMessageBox.critical(self, "Export Error", f"Failed to export member:\n{str(e)}")
    
    def load_default_settings(self):
        """Load default settings from first MAINFRAME_FTP connection"""
        try:
            # Get all connections using the correct method
            connections = self.conn_manager.repo.get_all_connections()
            ftp_connections = [c for c in connections if c.get('connection_type') == 'MAINFRAME_FTP']
            
            if ftp_connections:
                # Use connection_id, not 'id'
                conn_id = ftp_connections[0].get('connection_id')
                connection = self.conn_manager.repo.get_connection(conn_id)
                
                if connection:
                    from suiteview.core.credential_manager import CredentialManager
                    cred_manager = CredentialManager()
                    
                    # Parse connection string for FTP details
                    conn_string = connection.get('connection_string', '')
                    ftp_params = {}
                    for param in conn_string.split(';'):
                        if '=' in param:
                            key, value = param.split('=', 1)
                            ftp_params[key] = value
                    
                    self.connection_settings['host'] = connection.get('server_name', 'PRODESA')
                    self.connection_settings['port'] = int(ftp_params.get('port', 21))
                    self.connection_settings['initial_path'] = ftp_params.get('initial_path', '')
                    
                    # Decrypt credentials
                    encrypted_username = connection.get('encrypted_username')
                    encrypted_password = connection.get('encrypted_password')
                    
                    if encrypted_username:
                        self.connection_settings['username'] = cred_manager.decrypt(encrypted_username)
                        logger.info(f"Loaded username: {self.connection_settings['username']}")
                    if encrypted_password:
                        self.connection_settings['password'] = cred_manager.decrypt(encrypted_password)
                        logger.info("Loaded encrypted password from database")
                    
                    # Auto-connect with loaded credentials
                    if self.connection_settings['username'] and self.connection_settings['password']:
                        logger.info("Loaded credentials from MAINFRAME_FTP connection, auto-connecting...")
                        # Small delay to let UI finish loading
                        from PyQt6.QtCore import QTimer
                        QTimer.singleShot(500, self.connect_to_mainframe)
                    else:
                        logger.warning("No credentials found in MAINFRAME_FTP connection")
            else:
                logger.warning("No MAINFRAME_FTP connections found in database")
                    
        except Exception as e:
            logger.error(f"Failed to load default settings: {str(e)}", exc_info=True)
    
    def set_connection(self, connection_id):
        """Load settings from a specific connection and connect"""
        try:
            connection = self.conn_manager.get_connection(connection_id)
            
            if not connection:
                logger.error(f"Connection {connection_id} not found")
                return
            
            from suiteview.core.credential_manager import CredentialManager
            cred_manager = CredentialManager()
            
            # Parse connection string for FTP details
            conn_string = connection.get('connection_string', '')
            ftp_params = {}
            for param in conn_string.split(';'):
                if '=' in param:
                    key, value = param.split('=', 1)
                    ftp_params[key] = value
            
            self.connection_settings['host'] = connection.get('server_name', 'PRODESA')
            self.connection_settings['port'] = int(ftp_params.get('port', 21))
            self.connection_settings['initial_path'] = ftp_params.get('initial_path', '')
            
            # Decrypt credentials
            encrypted_username = connection.get('encrypted_username')
            encrypted_password = connection.get('encrypted_password')
            
            if encrypted_username:
                self.connection_settings['username'] = cred_manager.decrypt(encrypted_username)
            if encrypted_password:
                self.connection_settings['password'] = cred_manager.decrypt(encrypted_password)
            
            # Auto-connect when clicking from connections screen
            self.current_connection_id = connection_id
            self.connect_to_mainframe()
                
        except Exception as e:
            logger.error(f"Failed to load connection: {str(e)}")
            QMessageBox.critical(self, "Connection Error", f"Failed to load connection:\n{str(e)}")
