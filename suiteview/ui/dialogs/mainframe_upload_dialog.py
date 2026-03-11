"""
Mainframe Upload Dialog - Select connection and dataset for upload
"""

from pathlib import Path
from PyQt6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QLabel, 
                              QComboBox, QLineEdit, QPushButton, QRadioButton,
                              QButtonGroup, QDialogButtonBox, QMessageBox,
                              QProgressDialog, QFrame, QTextEdit)
from PyQt6.QtCore import Qt, QThread, pyqtSignal
from PyQt6.QtGui import QFont

import logging
logger = logging.getLogger(__name__)


class MainframeUploadThread(QThread):
    """Background thread for uploading files to mainframe"""
    progress = pyqtSignal(str)
    finished = pyqtSignal(bool, str)
    
    def __init__(self, file_path, connection_details, dataset_name, upload_mode):
        super().__init__()
        self.file_path = file_path
        self.connection_details = connection_details
        self.dataset_name = dataset_name
        self.upload_mode = upload_mode  # 'binary' or 'text'
        
    def run(self):
        """Perform the upload"""
        try:
            from suiteview.core.ftp_manager import MainframeFTPManager
            
            self.progress.emit("Connecting to mainframe...")
            
            # Create FTP manager
            ftp_mgr = MainframeFTPManager(
                host=self.connection_details['host'],
                username=self.connection_details['username'],
                password=self.connection_details['password'],
                port=self.connection_details.get('port', 21)
            )
            
            # Connect
            ftp_mgr.connect()
            
            self.progress.emit(f"Uploading {Path(self.file_path).name}...")
            
            # Upload based on mode
            if self.upload_mode == 'text':
                success, message = ftp_mgr.upload_file_as_text(self.file_path, self.dataset_name)
            else:
                success, message = ftp_mgr.upload_file(self.file_path, self.dataset_name)
            
            # Disconnect
            ftp_mgr.disconnect()
            
            if success:
                self.finished.emit(True, message)
            else:
                self.finished.emit(False, f"Upload failed: {message}")
                
        except Exception as e:
            logger.error(f"Upload failed: {e}")
            self.finished.emit(False, f"Upload error: {str(e)}")


class MainframeUploadDialog(QDialog):
    """Dialog for uploading files to mainframe"""
    
    def __init__(self, file_path, parent=None):
        super().__init__(parent)
        self.file_path = Path(file_path)
        self.connections = []
        self.selected_connection = None
        
        self.setWindowTitle("Upload to Mainframe")
        self.setModal(True)
        self.resize(600, 450)
        
        self.init_ui()
        self.load_connections()
    
    def init_ui(self):
        """Initialize UI"""
        layout = QVBoxLayout(self)
        layout.setSpacing(15)
        
        # File info
        file_frame = QFrame()
        file_frame.setFrameShape(QFrame.Shape.StyledPanel)
        file_frame.setStyleSheet("background-color: #f8f9fa; border-radius: 5px;")
        file_layout = QVBoxLayout(file_frame)
        
        file_label = QLabel(f"<b>File to Upload:</b>")
        file_layout.addWidget(file_label)
        
        filename_label = QLabel(f"📄 {self.file_path.name}")
        filename_label.setStyleSheet("font-size: 11pt; padding: 5px;")
        file_layout.addWidget(filename_label)
        
        size_label = QLabel(f"Size: {self.format_size(self.file_path.stat().st_size)}")
        size_label.setStyleSheet("color: #666; padding-left: 5px;")
        file_layout.addWidget(size_label)
        
        layout.addWidget(file_frame)
        
        # Connection selection
        conn_label = QLabel("<b>Select Mainframe Connection:</b>")
        layout.addWidget(conn_label)
        
        self.connection_combo = QComboBox()
        self.connection_combo.setMinimumHeight(30)
        layout.addWidget(self.connection_combo)
        
        # Dataset name
        dataset_label = QLabel("<b>Target Dataset Name:</b>")
        layout.addWidget(dataset_label)
        
        self.dataset_input = QLineEdit()
        self.dataset_input.setPlaceholderText("e.g., D03.AA0139.TEST.DATA or USER.TEST.FILE")
        self.dataset_input.setMinimumHeight(30)
        layout.addWidget(self.dataset_input)
        
        help_label = QLabel("💡 Tip: Enter the fully qualified dataset name without quotes")
        help_label.setStyleSheet("color: #666; font-size: 9pt; padding-left: 5px;")
        layout.addWidget(help_label)
        
        # Upload mode
        mode_label = QLabel("<b>Upload Mode:</b>")
        layout.addWidget(mode_label)
        
        self.mode_group = QButtonGroup(self)
        
        self.text_mode_radio = QRadioButton("Text Mode (ASCII) - For text files, CSV, etc.")
        self.binary_mode_radio = QRadioButton("Binary Mode - For all other files")
        
        self.mode_group.addButton(self.text_mode_radio, 0)
        self.mode_group.addButton(self.binary_mode_radio, 1)
        
        # Auto-select based on file type
        if self.file_path.suffix.lower() in ['.txt', '.csv', '.log', '.dat', '.sql', '.py', '.js', '.html']:
            self.text_mode_radio.setChecked(True)
        else:
            self.binary_mode_radio.setChecked(True)
        
        layout.addWidget(self.text_mode_radio)
        layout.addWidget(self.binary_mode_radio)
        
        layout.addStretch()
        
        # Buttons
        button_box = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        button_box.accepted.connect(self.accept)
        button_box.rejected.connect(self.reject)
        layout.addWidget(button_box)
    
    def load_connections(self):
        """Load mainframe connections from database"""
        try:
            from suiteview.data.database import Database
            from suiteview.data.repositories import ConnectionRepository
            
            db = Database()
            db.connect()
            
            conn_repo = ConnectionRepository(db.connection)
            all_connections = conn_repo.get_all()
            
            # Filter for FTP connections (mainframe)
            self.connections = [
                conn for conn in all_connections 
                if conn.connection_type and 'FTP' in conn.connection_type.upper()
            ]
            
            # Populate combo box
            for conn in self.connections:
                self.connection_combo.addItem(
                    f"🖥️ {conn.name} ({conn.host})",
                    conn
                )
            
            if not self.connections:
                QMessageBox.warning(
                    self,
                    "No Connections",
                    "No mainframe FTP connections found.\n\n"
                    "Please create a mainframe connection first in the Connections screen."
                )
                
        except Exception as e:
            logger.error(f"Failed to load connections: {e}")
            QMessageBox.critical(
                self,
                "Error",
                f"Failed to load mainframe connections:\n{str(e)}"
            )
    
    def format_size(self, size_bytes):
        """Format file size"""
        if size_bytes < 1024:
            return f"{size_bytes} B"
        elif size_bytes < 1024 * 1024:
            return f"{size_bytes / 1024:.1f} KB"
        elif size_bytes < 1024 * 1024 * 1024:
            return f"{size_bytes / (1024 * 1024):.1f} MB"
        else:
            return f"{size_bytes / (1024 * 1024 * 1024):.2f} GB"
    
    def get_upload_details(self):
        """Get upload configuration"""
        if self.connection_combo.currentIndex() < 0:
            return None
        
        connection = self.connection_combo.currentData()
        dataset_name = self.dataset_input.text().strip()
        
        if not dataset_name:
            QMessageBox.warning(self, "Missing Information", "Please enter a dataset name")
            return None
        
        upload_mode = 'text' if self.text_mode_radio.isChecked() else 'binary'
        
        return {
            'connection': connection,
            'dataset_name': dataset_name,
            'upload_mode': upload_mode
        }
    
    def perform_upload(self):
        """Perform the mainframe upload"""
        details = self.get_upload_details()
        if not details:
            return False
        
        connection = details['connection']
        
        # Create progress dialog
        progress = QProgressDialog("Uploading to mainframe...", "Cancel", 0, 0, self)
        progress.setWindowTitle("Upload Progress")
        progress.setWindowModality(Qt.WindowModality.WindowModal)
        progress.setMinimumDuration(0)
        progress.setCancelButton(None)  # Can't cancel upload mid-stream
        
        # Create upload thread
        upload_thread = MainframeUploadThread(
            str(self.file_path),
            {
                'host': connection.host,
                'username': connection.username,
                'password': connection.password,
                'port': connection.port or 21
            },
            details['dataset_name'],
            details['upload_mode']
        )
        
        # Connect signals
        upload_thread.progress.connect(lambda msg: progress.setLabelText(msg))
        
        def on_finished(success, message):
            progress.close()
            if success:
                QMessageBox.information(
                    self,
                    "Upload Complete",
                    f"✅ {message}\n\nFile: {self.file_path.name}\nDataset: {details['dataset_name']}"
                )
                return True
            else:
                QMessageBox.critical(
                    self,
                    "Upload Failed",
                    f"❌ {message}"
                )
                return False
        
        upload_thread.finished.connect(on_finished)
        
        # Start upload
        upload_thread.start()
        progress.exec()
        
        # Wait for thread to finish
        upload_thread.wait()
        
        return True
