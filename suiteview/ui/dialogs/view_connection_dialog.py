"""View/Edit Connection Dialog - Display and edit connection details"""

import logging
from PyQt6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
                              QPushButton, QWidget, QComboBox, QCheckBox, QSpinBox,
                              QMessageBox, QFileDialog)
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QFont

logger = logging.getLogger(__name__)


class ViewConnectionDialog(QDialog):
    """Dialog to view and edit connection details"""
    
    def __init__(self, parent=None, connection_data: dict = None):
        super().__init__(parent)
        self.connection_data = connection_data or {}
        self.connection_type = self.connection_data.get('connection_type', '')
        self.edit_mode = False
        
        self.setWindowTitle(f"Connection Details - {self.connection_data.get('connection_name', 'Unknown')}")
        self.setMinimumWidth(600)
        self.setMinimumHeight(400)
        
        self.init_ui()
        self.populate_fields()
        self.set_fields_readonly(True)
    
    def init_ui(self):
        """Initialize the UI based on connection type"""
        layout = QVBoxLayout(self)
        
        # Title
        title = QLabel(f"{self.connection_type} Connection")
        title.setFont(QFont("Segoe UI", 14, QFont.Weight.Bold))
        title.setStyleSheet("color: #D4AF37; padding: 10px;")
        layout.addWidget(title)
        
        # Form container
        form_container = QWidget()
        self.form_layout = QVBoxLayout(form_container)
        self.form_layout.setSpacing(10)
        
        # Create fields based on connection type
        if self.connection_type in ['CSV', 'CSV File']:
            self.create_csv_fields()
        elif self.connection_type in ['EXCEL', 'Excel File']:
            self.create_excel_fields()
        elif self.connection_type in ['ACCESS', 'MS Access']:
            self.create_access_fields()
        elif self.connection_type in ['FIXED_WIDTH', 'Fixed Width File']:
            self.create_fixed_width_fields()
        elif self.connection_type in ['DB2']:
            self.create_db2_fields()
        elif self.connection_type in ['SQL_SERVER', 'Local ODBC']:
            self.create_sql_server_fields()
        elif self.connection_type in ['MAINFRAME_FTP', 'Mainframe FTP']:
            self.create_ftp_fields()
        else:
            self.create_generic_fields()
        
        layout.addWidget(form_container)
        layout.addStretch()
        
        # Button bar
        button_layout = QHBoxLayout()
        
        self.edit_btn = QPushButton("✏️ Edit")
        self.edit_btn.setObjectName("gold_button")
        self.edit_btn.clicked.connect(self.toggle_edit_mode)
        button_layout.addWidget(self.edit_btn)
        
        button_layout.addStretch()
        
        self.save_btn = QPushButton("💾 Save")
        self.save_btn.setObjectName("gold_button")
        self.save_btn.clicked.connect(self.save_changes)
        self.save_btn.setVisible(False)
        button_layout.addWidget(self.save_btn)
        
        self.cancel_btn = QPushButton("Cancel")
        self.cancel_btn.clicked.connect(self.cancel_edit)
        self.cancel_btn.setVisible(False)
        button_layout.addWidget(self.cancel_btn)
        
        self.close_btn = QPushButton("Close")
        self.close_btn.clicked.connect(self.close)
        button_layout.addWidget(self.close_btn)
        
        layout.addLayout(button_layout)
    
    def add_field(self, label_text: str, widget: QWidget, field_name: str):
        """Add a field to the form"""
        row = QHBoxLayout()
        
        label = QLabel(label_text)
        label.setMinimumWidth(150)
        label.setStyleSheet("font-weight: bold;")
        row.addWidget(label)
        
        row.addWidget(widget)
        
        self.form_layout.addLayout(row)
        
        # Store widget reference
        if not hasattr(self, 'field_widgets'):
            self.field_widgets = {}
        self.field_widgets[field_name] = widget
    
    def create_csv_fields(self):
        """Create fields for CSV connection"""
        self.file_edit = QLineEdit()
        self.add_field("File:", self.file_edit, 'file')
        
        self.folder_edit = QLineEdit()
        self.add_field("File Location (Folder):", self.folder_edit, 'folder')
        
        self.delimiter_edit = QLineEdit()
        self.add_field("Delimiter:", self.delimiter_edit, 'delimiter')
        
        self.encoding_combo = QComboBox()
        self.encoding_combo.addItems(['UTF-8', 'UTF-16', 'ASCII', 'ISO-8859-1', 'Windows-1252'])
        self.add_field("Encoding:", self.encoding_combo, 'encoding')
        
        self.header_check = QCheckBox("First row contains column headers")
        self.form_layout.addWidget(self.header_check)
        self.field_widgets['has_header'] = self.header_check
        
        self.name_edit = QLineEdit()
        self.add_field("Connection Name:", self.name_edit, 'connection_name')
    
    def create_excel_fields(self):
        """Create fields for Excel connection"""
        self.file_edit = QLineEdit()
        self.add_field("File:", self.file_edit, 'file')
        
        self.folder_edit = QLineEdit()
        self.add_field("File Location (Folder):", self.folder_edit, 'folder')
        
        self.name_edit = QLineEdit()
        self.add_field("Connection Name:", self.name_edit, 'connection_name')
    
    def create_access_fields(self):
        """Create fields for MS Access connection"""
        self.file_edit = QLineEdit()
        self.add_field("File:", self.file_edit, 'file')
        
        self.folder_edit = QLineEdit()
        self.add_field("File Location (Folder):", self.folder_edit, 'folder')
        
        self.name_edit = QLineEdit()
        self.add_field("Connection Name:", self.name_edit, 'connection_name')
    
    def create_fixed_width_fields(self):
        """Create fields for Fixed Width connection"""
        self.file_edit = QLineEdit()
        self.add_field("File:", self.file_edit, 'file')
        
        self.folder_edit = QLineEdit()
        self.add_field("File Location (Folder):", self.folder_edit, 'folder')
        
        self.encoding_combo = QComboBox()
        self.encoding_combo.addItems(['UTF-8', 'UTF-16', 'ASCII', 'ISO-8859-1', 'Windows-1252'])
        self.add_field("Encoding:", self.encoding_combo, 'encoding')
        
        self.name_edit = QLineEdit()
        self.add_field("Connection Name:", self.name_edit, 'connection_name')
    
    def create_db2_fields(self):
        """Create fields for DB2 connection (ODBC DSN-based)"""
        self.dsn_edit = QLineEdit()
        self.add_field("ODBC Data Source Name:", self.dsn_edit, 'dsn')
        
        self.driver_edit = QLineEdit()
        self.add_field("Driver Name:", self.driver_edit, 'driver')
        
        self.db_type_edit = QLineEdit()
        self.add_field("Database Type:", self.db_type_edit, 'db_type')
        
        self.name_edit = QLineEdit()
        self.add_field("Connection Name:", self.name_edit, 'connection_name')
    
    def create_sql_server_fields(self):
        """Create fields for SQL Server connection (ODBC DSN-based)"""
        self.dsn_edit = QLineEdit()
        self.add_field("ODBC Data Source Name:", self.dsn_edit, 'dsn')
        
        self.driver_edit = QLineEdit()
        self.add_field("Driver Name:", self.driver_edit, 'driver')
        
        self.db_type_edit = QLineEdit()
        self.add_field("Database Type:", self.db_type_edit, 'db_type')
        
        self.name_edit = QLineEdit()
        self.add_field("Connection Name:", self.name_edit, 'connection_name')
    
    def create_ftp_fields(self):
        """Create fields for Mainframe FTP connection"""
        self.host_edit = QLineEdit()
        self.add_field("Host:", self.host_edit, 'ftp_host')
        
        self.port_spin = QSpinBox()
        self.port_spin.setRange(1, 65535)
        self.port_spin.setValue(21)
        self.add_field("Port:", self.port_spin, 'ftp_port')
        
        self.username_edit = QLineEdit()
        self.add_field("Username:", self.username_edit, 'ftp_username')
        
        self.password_edit = QLineEdit()
        self.password_edit.setEchoMode(QLineEdit.EchoMode.Password)
        self.add_field("Password:", self.password_edit, 'ftp_password')
        
        self.initial_path_edit = QLineEdit()
        self.add_field("Initial Path:", self.initial_path_edit, 'ftp_initial_path')
        
        self.name_edit = QLineEdit()
        self.add_field("Connection Name:", self.name_edit, 'connection_name')
    
    def create_generic_fields(self):
        """Create generic fields for unknown connection type"""
        self.name_edit = QLineEdit()
        self.add_field("Connection Name:", self.name_edit, 'connection_name')
        
        info_label = QLabel(f"Connection type: {self.connection_type}\n\nNo specific fields available for this connection type.")
        info_label.setStyleSheet("color: #999; padding: 20px;")
        self.form_layout.addWidget(info_label)
    
    def populate_fields(self):
        """Populate fields with connection data"""
        from suiteview.core.credential_manager import CredentialManager
        
        cred_mgr = CredentialManager()
        
        # Connection name (common to all)
        if hasattr(self, 'name_edit'):
            self.name_edit.setText(self.connection_data.get('connection_name', ''))
        
        # Type-specific fields
        if self.connection_type in ['CSV', 'CSV File']:
            # Get file path from connection_string (stored directly as the path)
            file_path = self.connection_data.get('connection_string', '')
            
            # Parse additional CSV parameters if they exist (semicolon-separated)
            if ';' in file_path:
                # New format: file=/path;delimiter=,;encoding=UTF-8;has_header=true
                params = dict(param.split('=', 1) for param in file_path.split(';') if '=' in param)
                file_path = params.get('file', '')
                delimiter = params.get('delimiter', ',')
                encoding = params.get('encoding', 'UTF-8')
                has_header = params.get('has_header', 'true').lower() == 'true'
            else:
                # Old format: just the file path
                delimiter = ','
                encoding = 'UTF-8'
                has_header = True
            
            if file_path:
                import os
                self.file_edit.setText(os.path.basename(file_path))
                self.folder_edit.setText(os.path.dirname(file_path))
            
            self.delimiter_edit.setText(delimiter)
            self.encoding_combo.setCurrentText(encoding)
            self.header_check.setChecked(has_header)
        
        elif self.connection_type in ['EXCEL', 'Excel File']:
            # Get file path from connection_string (stored directly as the path)
            file_path = self.connection_data.get('connection_string', '')
            
            if file_path:
                import os
                self.file_edit.setText(os.path.basename(file_path))
                self.folder_edit.setText(os.path.dirname(file_path))
        
        elif self.connection_type in ['ACCESS', 'MS Access']:
            # Get file path from connection_string (stored directly as the path)
            file_path = self.connection_data.get('connection_string', '')
            
            if file_path:
                import os
                self.file_edit.setText(os.path.basename(file_path))
                self.folder_edit.setText(os.path.dirname(file_path))
        
        elif self.connection_type in ['FIXED_WIDTH', 'Fixed Width File']:
            # Get file path from connection_string
            file_path = self.connection_data.get('connection_string', '')
            
            # Parse additional parameters if they exist
            if ';' in file_path:
                params = dict(param.split('=', 1) for param in file_path.split(';') if '=' in param)
                file_path = params.get('file', '')
                encoding = params.get('encoding', 'UTF-8')
            else:
                encoding = 'UTF-8'
            
            if file_path:
                import os
                self.file_edit.setText(os.path.basename(file_path))
                self.folder_edit.setText(os.path.dirname(file_path))
            
            self.encoding_combo.setCurrentText(encoding)
        
        elif self.connection_type == 'DB2':
            # For DB2, show ODBC DSN information
            conn_string = self.connection_data.get('connection_string', '')
            
            # Extract DSN from connection string (format: "DSN=NEON_DSN")
            dsn = conn_string.replace('DSN=', '').strip()
            self.dsn_edit.setText(dsn)
            
            # Get driver and database type from server_name and database_name if stored there
            # (These were captured during connection creation)
            driver = self.connection_data.get('driver_name', 'N/A')
            db_type = self.connection_data.get('database_type', 'DB2')
            
            self.driver_edit.setText(driver)
            self.db_type_edit.setText(db_type)
        
        elif self.connection_type in ['SQL_SERVER', 'Local ODBC']:
            # For SQL Server/ODBC, show ODBC DSN information
            conn_string = self.connection_data.get('connection_string', '')
            
            # Extract DSN from connection string
            dsn = conn_string.replace('DSN=', '').strip()
            self.dsn_edit.setText(dsn)
            
            # Get driver and database type
            driver = self.connection_data.get('driver_name', 'N/A')
            db_type = self.connection_data.get('database_type', 'SQL_SERVER')
            
            self.driver_edit.setText(driver)
            self.db_type_edit.setText(db_type)
        
        elif self.connection_type in ['MAINFRAME_FTP', 'Mainframe FTP']:
            self.host_edit.setText(self.connection_data.get('server_name', ''))
            
            conn_string = self.connection_data.get('connection_string', '')
            params = dict(param.split('=', 1) for param in conn_string.split(';') if '=' in param)
            self.port_spin.setValue(int(params.get('port', 21)))
            self.initial_path_edit.setText(params.get('initial_path', ''))
            
            # Decrypt credentials
            encrypted_username = self.connection_data.get('encrypted_username')
            encrypted_password = self.connection_data.get('encrypted_password')
            if encrypted_username:
                self.username_edit.setText(cred_mgr.decrypt(encrypted_username))
            if encrypted_password:
                self.password_edit.setText(cred_mgr.decrypt(encrypted_password))
    
    def set_fields_readonly(self, readonly: bool):
        """Set all fields to readonly or editable"""
        if not hasattr(self, 'field_widgets'):
            return
        
        for widget in self.field_widgets.values():
            if isinstance(widget, QLineEdit):
                widget.setReadOnly(readonly)
            elif isinstance(widget, (QComboBox, QSpinBox, QCheckBox)):
                widget.setEnabled(not readonly)
    
    def toggle_edit_mode(self):
        """Toggle between view and edit mode"""
        self.edit_mode = True
        self.set_fields_readonly(False)
        
        # Show/hide buttons
        self.edit_btn.setVisible(False)
        self.save_btn.setVisible(True)
        self.cancel_btn.setVisible(True)
        self.close_btn.setVisible(False)
    
    def cancel_edit(self):
        """Cancel editing and restore original values"""
        self.edit_mode = False
        self.populate_fields()
        self.set_fields_readonly(True)
        
        # Show/hide buttons
        self.edit_btn.setVisible(True)
        self.save_btn.setVisible(False)
        self.cancel_btn.setVisible(False)
        self.close_btn.setVisible(True)
    
    def save_changes(self):
        """Save the changes"""
        try:
            from suiteview.core.connection_manager import get_connection_manager
            from suiteview.core.credential_manager import CredentialManager
            
            conn_mgr = get_connection_manager()
            cred_mgr = CredentialManager()
            
            connection_id = self.connection_data.get('connection_id')
            if not connection_id:
                raise ValueError("Connection ID not found")
            
            # Build updated connection data based on type
            updated_data = {
                'connection_name': self.name_edit.text()
            }
            
            # Type-specific updates
            if self.connection_type in ['CSV', 'CSV File']:
                import os
                file_path = os.path.join(self.folder_edit.text(), self.file_edit.text())
                updated_data['file_path'] = file_path
                updated_data['connection_string'] = (
                    f"file={file_path};"
                    f"delimiter={self.delimiter_edit.text()};"
                    f"encoding={self.encoding_combo.currentText()};"
                    f"has_header={'true' if self.header_check.isChecked() else 'false'}"
                )
            
            elif self.connection_type in ['EXCEL', 'Excel File', 'ACCESS', 'MS Access']:
                import os
                file_path = os.path.join(self.folder_edit.text(), self.file_edit.text())
                updated_data['file_path'] = file_path
                updated_data['connection_string'] = f"file={file_path}"
            
            elif self.connection_type in ['FIXED_WIDTH', 'Fixed Width File']:
                import os
                file_path = os.path.join(self.folder_edit.text(), self.file_edit.text())
                updated_data['file_path'] = file_path
                updated_data['connection_string'] = (
                    f"file={file_path};"
                    f"encoding={self.encoding_combo.currentText()}"
                )
            
            elif self.connection_type == 'DB2':
                # For DB2 ODBC, only save DSN
                dsn = self.dsn_edit.text()
                updated_data['connection_string'] = f"DSN={dsn}"
                # Also update these if you want to keep them for reference
                updated_data['driver_name'] = self.driver_edit.text()
                updated_data['database_type'] = self.db_type_edit.text()
            
            elif self.connection_type in ['SQL_SERVER', 'Local ODBC']:
                # For SQL Server ODBC, only save DSN
                dsn = self.dsn_edit.text()
                updated_data['connection_string'] = f"DSN={dsn}"
                # Also update these if you want to keep them for reference
                updated_data['driver_name'] = self.driver_edit.text()
                updated_data['database_type'] = self.db_type_edit.text()
            
            elif self.connection_type in ['MAINFRAME_FTP', 'Mainframe FTP']:
                updated_data['server_name'] = self.host_edit.text()
                updated_data['database_name'] = self.initial_path_edit.text()  # Store initial_path in database_name
                updated_data['connection_string'] = (
                    f"host={self.host_edit.text()};"
                    f"port={self.port_spin.value()};"
                    f"initial_path={self.initial_path_edit.text()}"
                )
                updated_data['encrypted_username'] = cred_mgr.encrypt(self.username_edit.text())
                updated_data['encrypted_password'] = cred_mgr.encrypt(self.password_edit.text())
            
            # Update the connection using **kwargs
            conn_mgr.update_connection(connection_id, **updated_data)
            
            QMessageBox.information(self, "Success", "Connection updated successfully!")
            logger.info(f"Updated connection: {self.name_edit.text()}")
            
            # Exit edit mode
            self.edit_mode = False
            self.set_fields_readonly(True)
            self.edit_btn.setVisible(True)
            self.save_btn.setVisible(False)
            self.cancel_btn.setVisible(False)
            self.close_btn.setVisible(True)
            
            # Signal parent to refresh
            self.accept()
            
        except Exception as e:
            logger.error(f"Failed to update connection: {e}")
            QMessageBox.critical(self, "Error", f"Failed to update connection:\n{str(e)}")
