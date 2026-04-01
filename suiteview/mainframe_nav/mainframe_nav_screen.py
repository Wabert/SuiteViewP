"""
Mainframe Navigation Screen - File explorer interface for browsing mainframe datasets
"""

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QSplitter, QTextEdit, QLineEdit, QPushButton,
    QLabel, QMessageBox, QTreeWidget, QTreeWidgetItem, QTableWidget, QTableWidgetItem,
    QHeaderView, QDialog, QDialogButtonBox, QStyle, QComboBox, QFileDialog, QInputDialog,
    QListWidget, QListWidgetItem, QToolButton, QApplication, QCheckBox
)
from PyQt6.QtCore import Qt, QThread, pyqtSignal, QSize
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


class ContentSearchThread(QThread):
    """Background thread for searching dataset content"""
    progress_update = pyqtSignal(str, int, int)  # message, current, total
    search_complete = pyqtSignal(object)  # Search results dict with results, errors, skipped
    
    def __init__(self, ftp_manager, datasets, search_strings, case_sensitive, whole_word, current_dataset):
        super().__init__()
        self.ftp_manager = ftp_manager
        self.datasets = datasets
        self.search_strings = search_strings
        self.case_sensitive = case_sensitive
        self.whole_word = whole_word
        self.current_dataset = current_dataset
        self._is_cancelled = False
    
    def cancel(self):
        """Cancel the search"""
        self._is_cancelled = True
    
    def run(self):
        """Search through datasets"""
        import re
        results = []
        errors = []
        skipped = []
        total = len(self.datasets)
        
        for idx, dataset_info in enumerate(self.datasets):
            if self._is_cancelled:
                break
            
            member_name = dataset_info['name']
            full_path = dataset_info['full_path']
            dsorg = dataset_info.get('dsorg', '')
            
            self.progress_update.emit(f"Searching {member_name}...", idx + 1, total)
            
            # Skip PO datasets - they can't be read directly, only their members
            if dsorg == 'PO':
                skipped.append(f"{member_name} (PO dataset - cannot read directly)")
                continue
            
            try:
                # Read dataset content
                content, total_lines = self.ftp_manager.read_dataset(full_path, max_lines=None)
                
                if not content:
                    skipped.append(f"{member_name} (empty or no content)")
                    continue
                
                # Search for each string
                dataset_matches = []
                for search_str in self.search_strings:
                    # Convert wildcard pattern to regex
                    pattern = re.escape(search_str)
                    pattern = pattern.replace(r'\*', '.*').replace(r'\?', '.')
                    
                    # Add word boundaries if whole word search
                    if self.whole_word:
                        pattern = r'\b' + pattern + r'\b'
                    
                    # Compile regex
                    flags = 0 if self.case_sensitive else re.IGNORECASE
                    regex = re.compile(pattern, flags)
                    
                    # Search each line
                    matches = []
                    for line_num, line in enumerate(content.split('\n'), 1):
                        if regex.search(line):
                            matches.append({
                                'line_number': line_num,
                                'line_content': line.strip()
                            })
                    
                    if matches:
                        dataset_matches.append({
                            'search_string': search_str,
                            'matches': matches[:10]  # Limit to first 10 matches per string
                        })
                
                if dataset_matches:
                    results.append({
                        'dataset': member_name,
                        'full_path': full_path,
                        'matches': dataset_matches
                    })
                    
            except Exception as e:
                error_msg = str(e)
                logger.error(f"Error searching {member_name}: {error_msg}")
                errors.append(f"{member_name}: {error_msg}")
                continue
        
        # Include error/skip info in results
        self.search_complete.emit({
            'results': results,
            'errors': errors,
            'skipped': skipped
        })


class MainframeNavScreen(QWidget):
    """Mainframe navigation screen with file explorer layout"""
    
    def __init__(self, conn_manager):
        super().__init__()
        self.conn_manager = conn_manager
        self.current_connection_id = None
        self.ftp_manager = None
        self.current_dataset = ""
        self.connection_thread = None  # For background FTP connection
        
        # Cache for folder contents - cleared when app closes
        self.folder_cache = {}  # {dataset_path: members_list}
        
        # Navigation history for back/forward buttons
        self.navigation_history = []  # List of dataset paths
        self.current_history_index = -1  # Current position in history
        
        # Connection settings
        self.connection_settings = {
            'host': 'PRODESA',
            'port': 21,
            'username': '',
            'password': '',
            'initial_path': ''
        }
        
        # Search content window reference
        self.search_content_window = None
        
        self.init_ui()
        self.load_connections()  # Load all mainframe connections into dropdown
        self.load_default_settings()  # Load saved credentials from database
        
    def init_ui(self):
        """Initialize the user interface"""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(5, 5, 5, 5)
        layout.setSpacing(2)
        
        # Top bar with connection management buttons
        top_bar = QHBoxLayout()
        top_bar.setSpacing(5)
        
        # Connection selector label
        conn_label = QLabel("Connections:")
        conn_label.setStyleSheet(
            "font-weight: bold; "
            "color: #1A3A6E; "
            "font-size: 11pt; "
            "padding: 4px;"
        )
        top_bar.addWidget(conn_label)
        
        # Add Connection button
        self.add_conn_button = QPushButton("➕ New")
        self.add_conn_button.setFixedWidth(80)
        self.add_conn_button.clicked.connect(self.add_connection)
        self.add_conn_button.setStyleSheet("""
            QPushButton {
                background-color: #4A6FA5;
                color: white;
                border: 1px solid #3A5A8A;
                padding: 6px;
                font-weight: bold;
                border-radius: 4px;
            }
            QPushButton:hover {
                background-color: #5A7FB5;
            }
        """)
        top_bar.addWidget(self.add_conn_button)
        
        # Edit Connection button
        self.edit_conn_button = QPushButton("✏️ Edit")
        self.edit_conn_button.setFixedWidth(80)
        self.edit_conn_button.clicked.connect(self.edit_connection)
        self.edit_conn_button.setEnabled(False)
        self.edit_conn_button.setStyleSheet("""
            QPushButton {
                background-color: #4A6FA5;
                color: white;
                border: 1px solid #3A5A8A;
                padding: 6px;
                font-weight: bold;
                border-radius: 4px;
            }
            QPushButton:hover {
                background-color: #5A7FB5;
            }
            QPushButton:disabled {
                background-color: #B0C0D8;
                color: #7A8A9E;
                border: 1px solid #95A5B8;
            }
        """)
        top_bar.addWidget(self.edit_conn_button)
        
        # Delete Connection button
        self.delete_conn_button = QPushButton("🗑️ Delete")
        self.delete_conn_button.setFixedWidth(90)
        self.delete_conn_button.clicked.connect(self.delete_connection)
        self.delete_conn_button.setEnabled(False)
        self.delete_conn_button.setStyleSheet("""
            QPushButton {
                background-color: #4A6FA5;
                color: white;
                border: 1px solid #3A5A8A;
                padding: 6px;
                font-weight: bold;
                border-radius: 4px;
            }
            QPushButton:hover {
                background-color: #5A7FB5;
            }
            QPushButton:disabled {
                background-color: #B0C0D8;
                color: #7A8A9E;
                border: 1px solid #95A5B8;
            }
        """)
        top_bar.addWidget(self.delete_conn_button)
        
        # Settings button for global credentials
        self.settings_button = QPushButton("⚙️ Settings")
        self.settings_button.setFixedWidth(100)
        self.settings_button.clicked.connect(self.show_credentials_dialog)
        self.settings_button.setStyleSheet("""
            QPushButton {
                background-color: #4A6FA5;
                color: white;
                border: 1px solid #3A5A8A;
                padding: 6px;
                font-weight: bold;
                border-radius: 4px;
            }
            QPushButton:hover {
                background-color: #5A7FB5;
            }
        """)
        top_bar.addWidget(self.settings_button)
        
        top_bar.addStretch()
        
        # Search Content button (right side)
        self.search_content_button = QPushButton("🔍 Search Content")
        self.search_content_button.setFixedWidth(130)
        self.search_content_button.setStyleSheet("""
            QPushButton {
                background-color: #3498db;
                color: white;
                border: 1px solid #2980b9;
                padding: 6px;
                font-weight: bold;
                border-radius: 4px;
            }
            QPushButton:hover {
                background-color: #5dade2;
            }
            QPushButton:disabled {
                background-color: #B0C0D8;
                color: #7A8A9E;
                border: 1px solid #95A5B8;
            }
        """)
        self.search_content_button.clicked.connect(self.open_search_content_window)
        self.search_content_button.setEnabled(False)
        top_bar.addWidget(self.search_content_button)
        
        layout.addLayout(top_bar)
        
        # Main splitter with 2 panels: Connections List | Detail View
        main_splitter = QSplitter(Qt.Orientation.Horizontal)
        
        # LEFT PANEL - Connections List (File Nav style)
        connections_widget = QWidget()
        connections_widget.setStyleSheet("background-color: #FFF9E6;")  # Light yellow like File Nav
        connections_layout = QVBoxLayout(connections_widget)
        connections_layout.setContentsMargins(0, 0, 0, 0)
        connections_layout.setSpacing(0)
        
        connections_header = QLabel("🔗 Connections")
        connections_header.setStyleSheet(
            "font-weight: 600; "
            "font-size: 10pt; "
            "padding: 4px 8px; "
            "background-color: #C0D4F0; "
            "color: #1A3A6E; "
            "border: none; "
            "border-bottom: 1px solid #A0B8D8;"
        )
        connections_layout.addWidget(connections_header)
        
        self.connections_list = QListWidget()
        self.connections_list.itemClicked.connect(self.on_connection_list_item_clicked)
        self.connections_list.setStyleSheet("""
            QListWidget {
                border: none;
                background-color: transparent;
                outline: none;
            }
            QListWidget::item {
                padding: 8px;
                border: none;
                background-color: transparent;
                color: #1A3A6E;
            }
            QListWidget::item:selected {
                background-color: #B0C8E8;
                color: #0A1E5E;
                font-weight: bold;
            }
            QListWidget::item:hover {
                background-color: #C8DCF0;
                color: #0A1E5E;
                font-weight: bold;
            }
        """)
        connections_layout.addWidget(self.connections_list)
        
        main_splitter.addWidget(connections_widget)
        
        # RIGHT PANEL - Detail View with Dataset Attributes
        content_widget = QWidget()
        content_layout = QVBoxLayout(content_widget)
        content_layout.setContentsMargins(0, 0, 0, 0)
        content_layout.setSpacing(2)
        
        # Detail View header with navigation and breadcrumb (File Nav style)
        content_header_widget = QWidget()
        content_header_widget.setStyleSheet(
            "background-color: #FFF9E6; "
            "border: none;"
        )
        content_header_layout = QHBoxLayout(content_header_widget)
        content_header_layout.setContentsMargins(8, 4, 8, 4)
        content_header_layout.setSpacing(6)
        
        # Navigation buttons (Back, Forward, Up) - File Nav style
        self.back_button = QToolButton()
        self.back_button.setText("←")
        self.back_button.setToolTip("Back")
        self.back_button.setEnabled(False)
        self.back_button.setAutoRaise(True)
        self.back_button.clicked.connect(self.navigate_back)
        self.back_button.setStyleSheet("""
            QToolButton {
                border: 1px solid #4A6FA5;
                border-bottom: 2px solid #3A5A8A;
                border-radius: 4px;
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                                            stop:0 #FFFFFF,
                                            stop:0.45 #F0F5FF,
                                            stop:1 #D0E3FF);
                color: #0A1E5E;
                font-weight: 600;
                font-size: 12px;
                padding: 2px 8px;
            }
            QToolButton:hover:enabled {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                                            stop:0 #FFFFFF,
                                            stop:0.35 #E3EDFF,
                                            stop:1 #B8D0F0);
                border-color: #2563EB;
            }
            QToolButton:pressed {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                                            stop:0 #B8D0F0,
                                            stop:1 #E3EDFF);
                border: 1px solid #3A5A8A;
                border-top: 2px solid #3A5A8A;
            }
            QToolButton:disabled {
                color: #95A5C0;
                background: #E8EEF7;
                border: 1px solid #B0C0D8;
            }
        """)
        content_header_layout.addWidget(self.back_button)
        
        self.forward_button = QToolButton()
        self.forward_button.setText("→")
        self.forward_button.setToolTip("Forward")
        self.forward_button.setEnabled(False)
        self.forward_button.setAutoRaise(True)
        self.forward_button.clicked.connect(self.navigate_forward)
        self.forward_button.setStyleSheet("""
            QToolButton {
                border: 1px solid #4A6FA5;
                border-bottom: 2px solid #3A5A8A;
                border-radius: 4px;
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                                            stop:0 #FFFFFF,
                                            stop:0.45 #F0F5FF,
                                            stop:1 #D0E3FF);
                color: #0A1E5E;
                font-weight: 600;
                font-size: 12px;
                padding: 2px 8px;
            }
            QToolButton:hover:enabled {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                                            stop:0 #FFFFFF,
                                            stop:0.35 #E3EDFF,
                                            stop:1 #B8D0F0);
                border-color: #2563EB;
            }
            QToolButton:pressed {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                                            stop:0 #B8D0F0,
                                            stop:1 #E3EDFF);
                border: 1px solid #3A5A8A;
                border-top: 2px solid #3A5A8A;
            }
            QToolButton:disabled {
                color: #95A5C0;
                background: #E8EEF7;
                border: 1px solid #B0C0D8;
            }
        """)
        content_header_layout.addWidget(self.forward_button)
        
        self.up_button = QToolButton()
        self.up_button.setText("↑")
        self.up_button.setToolTip("Up One Level")
        self.up_button.setEnabled(False)
        self.up_button.setAutoRaise(True)
        self.up_button.clicked.connect(self.navigate_up)
        self.up_button.setStyleSheet("""
            QToolButton {
                border: 1px solid #4A6FA5;
                border-bottom: 2px solid #3A5A8A;
                border-radius: 4px;
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                                            stop:0 #FFFFFF,
                                            stop:0.45 #F0F5FF,
                                            stop:1 #D0E3FF);
                color: #0A1E5E;
                font-weight: 600;
                font-size: 12px;
                padding: 2px 8px;
            }
            QToolButton:hover:enabled {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                                            stop:0 #FFFFFF,
                                            stop:0.35 #E3EDFF,
                                            stop:1 #B8D0F0);
                border-color: #2563EB;
            }
            QToolButton:pressed {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                                            stop:0 #B8D0F0,
                                            stop:1 #E3EDFF);
                border: 1px solid #3A5A8A;
                border-top: 2px solid #3A5A8A;
            }
            QToolButton:disabled {
                color: #95A5C0;
                background: #E8EEF7;
                border: 1px solid #B0C0D8;
            }
        """)
        content_header_layout.addWidget(self.up_button)
        
        # Breadcrumb navigation with clickable path input
        self.breadcrumb_container = QWidget()
        self.breadcrumb_container.setStyleSheet("""
            QWidget {
                background-color: #FFF9E6;
                border: 2px solid #6B8DC9;
                border-radius: 3px;
                padding: 1px;
            }
            QWidget:hover {
                border-color: #2563EB;
            }
        """)
        breadcrumb_container_layout = QHBoxLayout(self.breadcrumb_container)
        breadcrumb_container_layout.setContentsMargins(0, 0, 0, 0)
        breadcrumb_container_layout.setSpacing(0)
        
        # Breadcrumb display (shows clickable segments)
        self.breadcrumb_widget = QWidget()
        self.breadcrumb_widget.setStyleSheet("background-color: #FFF9E6;")
        self.breadcrumb_layout = QHBoxLayout(self.breadcrumb_widget)
        self.breadcrumb_layout.setContentsMargins(2, 0, 2, 0)
        self.breadcrumb_layout.setSpacing(0)
        
        # Text input for showing full path (hidden by default)
        self.path_input = QLineEdit()
        self.path_input.setStyleSheet("""
            QLineEdit {
                background-color: #FFF9E6;
                border: none;
                padding: 2px 6px;
                font-size: 11pt;
                color: #2563EB;
            }
            QLineEdit:focus {
                border: 1px solid #2563EB;
            }
        """)
        self.path_input.hide()
        self.path_input.setReadOnly(True)  # Read-only so user can only copy
        self.path_input.installEventFilter(self)
        
        breadcrumb_container_layout.addWidget(self.breadcrumb_widget, 1)
        breadcrumb_container_layout.addWidget(self.path_input, 1)
        
        # Install event filter on breadcrumb widgets to detect clicks
        self.breadcrumb_widget.installEventFilter(self)
        self.breadcrumb_container.installEventFilter(self)
        
        content_header_layout.addWidget(self.breadcrumb_container, 1)
        
        content_header_layout.addStretch()
        
        # Export button
        self.export_button = QPushButton("📤 Export")
        self.export_button.setFixedWidth(85)
        self.export_button.setStyleSheet("""
            QPushButton {
                background-color: #27ae60;
                color: white;
                border: 2px solid #229954;
                border-radius: 4px;
                padding: 3px 6px;
                font-weight: bold;
                font-size: 10px;
            }
            QPushButton:hover {
                background-color: #2ecc71;
                border-color: #27ae60;
            }
            QPushButton:pressed {
                background-color: #229954;
            }
            QPushButton:disabled {
                background-color: #5d6d7e;
                border-color: #4a5a6a;
                color: #95a5a6;
            }
        """)
        self.export_button.clicked.connect(self.export_selected_datasets)
        self.export_button.setEnabled(False)
        content_header_layout.addWidget(self.export_button)
        
        # Delete Member button
        self.delete_member_button = QPushButton("🗑️ Delete")
        self.delete_member_button.setFixedWidth(80)
        self.delete_member_button.setStyleSheet("""
            QPushButton {
                background-color: #e74c3c;
                color: white;
                border: 2px solid #c0392b;
                border-radius: 4px;
                padding: 3px 6px;
                font-weight: bold;
                font-size: 10px;
            }
            QPushButton:hover {
                background-color: #ec7063;
                border-color: #e74c3c;
            }
            QPushButton:pressed {
                background-color: #c0392b;
            }
            QPushButton:disabled {
                background-color: #5d6d7e;
                border-color: #4a5a6a;
                color: #95a5a6;
            }
        """)
        self.delete_member_button.clicked.connect(self.delete_member)
        self.delete_member_button.setEnabled(False)
        content_header_layout.addWidget(self.delete_member_button)
        
        content_layout.addWidget(content_header_widget)
        
        # Search bar below breadcrumb navigation
        search_widget = QWidget()
        search_widget.setStyleSheet("background-color: #FFF9E6; border: none;")
        search_layout = QHBoxLayout(search_widget)
        search_layout.setContentsMargins(8, 4, 8, 4)
        search_layout.setSpacing(8)
        
        search_label = QLabel("🔍 Search:")
        search_label.setStyleSheet("""
            QLabel {
                color: #1A3A6E;
                font-size: 10pt;
                font-weight: 600;
            }
        """)
        search_layout.addWidget(search_label)
        
        self.dataset_search = QLineEdit()
        self.dataset_search.setPlaceholderText("Search datasets (use * as wildcard, e.g., S*.Error)...")
        self.dataset_search.setClearButtonEnabled(True)
        self.dataset_search.setStyleSheet("""
            QLineEdit {
                padding: 3px 8px;
                border: 1px solid #A0B8D8;
                border-radius: 3px;
                background: white;
                color: #1A3A6E;
                font-size: 10pt;
            }
            QLineEdit:focus {
                border: 1px solid #2563EB;
            }
        """)
        self.dataset_search.textChanged.connect(self.on_dataset_search_changed)
        search_layout.addWidget(self.dataset_search)
        
        # Case-sensitive toggle checkbox
        self.case_sensitive_checkbox = QCheckBox("Case Sensitive")
        self.case_sensitive_checkbox.setChecked(False)  # Default to case-insensitive
        self.case_sensitive_checkbox.setStyleSheet("""
            QCheckBox {
                color: #1A3A6E;
                font-size: 9pt;
                padding: 2px 4px;
            }
            QCheckBox::indicator {
                width: 16px;
                height: 16px;
            }
        """)
        self.case_sensitive_checkbox.stateChanged.connect(lambda: self.on_dataset_search_changed(self.dataset_search.text()))
        search_layout.addWidget(self.case_sensitive_checkbox)
        
        content_layout.addWidget(search_widget)
        
        # Detail table with all mainframe dataset attributes
        self.members_table = QTableWidget()
        self.members_table.setColumnCount(10)
        self.members_table.setHorizontalHeaderLabels([
            "Name", "Volume", "Unit", "Referred", "Ext", "Used", "Recfm", "Lrecl", "BlkSz", "Dsorg"
        ])
        
        # Style like Windows File Explorer
        self.members_table.verticalHeader().setVisible(False)  # Hide row numbers
        self.members_table.setShowGrid(False)  # No grid lines
        self.members_table.setAlternatingRowColors(True)
        self.members_table.horizontalHeader().setDefaultAlignment(Qt.AlignmentFlag.AlignLeft)
        
        # Apply comprehensive table styling
        self.members_table.setStyleSheet("""
            QTableWidget {
                border: none;
                background-color: white;
                outline: none;
            }
            QTableWidget::item {
                padding: 0px;
                margin: 0px;
                border: none;
                outline: none;
            }
            QTableWidget::item:selected {
                background-color: #0078d4;
                color: white;
                border: none;
                outline: none;
            }
            QTableWidget::item:focus {
                border: none;
                outline: none;
                background-color: #0078d4;
                color: white;
            }
            QHeaderView::section {
                background-color: #f0f0f0;
                padding: 4px;
                border: none;
                border-bottom: 1px solid #d0d0d0;
                font-weight: normal;
                font-size: 11px;
            }
        """)
        
        # Set column resize modes - all columns are user-adjustable
        self.members_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        # Set default widths
        self.members_table.setColumnWidth(0, 150)  # Name
        self.members_table.setColumnWidth(1, 70)   # Volume
        self.members_table.setColumnWidth(2, 60)   # Unit
        self.members_table.setColumnWidth(3, 100)  # Referred
        self.members_table.setColumnWidth(4, 50)   # Ext
        self.members_table.setColumnWidth(5, 60)   # Used
        self.members_table.setColumnWidth(6, 70)   # Recfm
        self.members_table.setColumnWidth(7, 60)   # Lrecl
        self.members_table.setColumnWidth(8, 70)   # BlkSz
        self.members_table.setColumnWidth(9, 60)   # Dsorg
        
        # Load saved column widths
        self.load_column_widths()
        
        # Save column widths when changed
        self.members_table.horizontalHeader().sectionResized.connect(self.save_column_widths)
        
        self.members_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.members_table.setSelectionMode(QTableWidget.SelectionMode.ExtendedSelection)
        # Disable editing - table is read-only
        self.members_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        # Enable sorting by clicking column headers
        self.members_table.setSortingEnabled(True)
        self.members_table.itemSelectionChanged.connect(self.on_member_selected)
        # Double-click to navigate or view
        self.members_table.itemDoubleClicked.connect(self.on_item_double_clicked)
        # Enable right-click context menu
        self.members_table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.members_table.customContextMenuRequested.connect(self.show_context_menu)
        content_layout.addWidget(self.members_table)
        
        main_splitter.addWidget(content_widget)
        
        # Store splitter reference for saving/loading sizes
        self.main_splitter = main_splitter
        
        # Set default splitter sizes (30% tree, 70% detail view)
        main_splitter.setSizes([300, 700])
        
        # Load saved splitter sizes
        self.load_splitter_sizes()
        
        # Save splitter sizes when moved
        main_splitter.splitterMoved.connect(self.save_splitter_sizes)
        
        layout.addWidget(main_splitter)
        
        # Bottom status bar with action status on left and item count on right
        bottom_bar = QWidget()
        bottom_bar.setMaximumHeight(20)
        bottom_layout = QHBoxLayout(bottom_bar)
        bottom_layout.setContentsMargins(2, 0, 2, 0)
        bottom_layout.setSpacing(0)
        
        # Action status label (left side)
        self.status_label = QLabel("Select a connection to browse mainframe datasets")
        self.status_label.setStyleSheet("color: #7f8c8d; font-style: italic; padding: 2px; font-size: 11px;")
        bottom_layout.addWidget(self.status_label)
        
        # Spacer to push item count to the right
        bottom_layout.addStretch()
        
        # Item count label (right side, below details panel)
        self.item_count_label = QLabel("")
        self.item_count_label.setStyleSheet("color: #2c3e50; font-weight: normal; padding: 2px; font-size: 11px;")
        bottom_layout.addWidget(self.item_count_label)
        
        layout.addWidget(bottom_bar)
    
    def show_credentials_dialog(self):
        """Show dialog to configure global FTP credentials"""
        dialog = QDialog(self)
        dialog.setWindowTitle("Mainframe FTP Credentials")
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
        
        layout.addWidget(form_widget)
        
        # Note about credentials
        cred_note = QLabel("💡 Use the 'User' button at the bottom of the window to set your credentials.")
        cred_note.setStyleSheet("""
            QLabel {
                color: #666;
                font-style: italic;
                padding: 10px;
                background-color: #f0f8ff;
                border-radius: 4px;
                border: 1px solid #cce5ff;
            }
        """)
        cred_note.setWordWrap(True)
        layout.addWidget(cred_note)
        
        # Buttons with royal blue theme
        button_box = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        button_box.button(QDialogButtonBox.StandardButton.Ok).setStyleSheet("""
            QPushButton {
                background-color: #2c5f8d;
                color: white;
                padding: 6px 20px;
                border-radius: 4px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #1e4a6b;
            }
        """)
        button_box.accepted.connect(dialog.accept)
        button_box.rejected.connect(dialog.reject)
        layout.addWidget(button_box)
        
        if dialog.exec() == QDialog.DialogCode.Accepted:
            # Save settings
            self.connection_settings['host'] = host_edit.text()
            self.connection_settings['port'] = int(port_edit.text())
            
            # Get credentials from MAINFRAME_USER connection
            user_conn = self.conn_manager.get_connection("MAINFRAME_USER")
            if user_conn:
                self.connection_settings['username'] = user_conn.get('username', '')
                self.connection_settings['password'] = self.cred_manager.decrypt_password(user_conn.get('password', ''))
            
            # Save global credentials to all MAINFRAME_FTP connections
            self.save_global_credentials(
                self.connection_settings['username'],
                self.connection_settings['password'],
                self.connection_settings['host'],
                self.connection_settings['port']
            )
            
            # Reconnect with new settings
            self.connect_to_mainframe()
    
    def save_global_credentials(self, username, password, host, port):
        """Save global credentials to MAINFRAME_USER connection (shared with Terminal)"""
        try:
            from suiteview.core.credential_manager import CredentialManager
            cred_manager = CredentialManager()
            
            # Encrypt credentials
            encrypted_username = cred_manager.encrypt(username)
            encrypted_password = cred_manager.encrypt(password)
            
            # Get all connections using the correct method
            connections = self.conn_manager.repo.get_all_connections()
            
            # Find or create MAINFRAME_USER connection
            user_conn = None
            conn_id = None
            for conn in connections:
                if conn.get('connection_name') == 'MAINFRAME_USER':
                    user_conn = conn
                    conn_id = conn.get('connection_id')
                    break
            
            if user_conn:
                # Update existing MAINFRAME_USER connection
                self.conn_manager.repo.update_connection(
                    conn_id,
                    encrypted_username=encrypted_username,
                    encrypted_password=encrypted_password
                )
                logger.info("Updated MAINFRAME_USER credentials")
            else:
                # Create new MAINFRAME_USER connection
                self.conn_manager.repo.create_connection(
                    connection_name='MAINFRAME_USER',
                    connection_type='Generic',
                    server_name='',
                    database_name='',
                    auth_type='SQL_AUTH',
                    encrypted_username=encrypted_username,
                    encrypted_password=encrypted_password
                )
                logger.info("Created MAINFRAME_USER credentials")
            
            # Also update host/port in first MAINFRAME_FTP connection if it exists
            ftp_connections = [c for c in connections if c.get('connection_type') == 'MAINFRAME_FTP']
            if ftp_connections:
                conn_id = ftp_connections[0].get('connection_id')
                conn = ftp_connections[0]
                
                # Parse existing connection string to preserve initial_path
                conn_string = conn.get('connection_string', '')
                ftp_params = {}
                for param in conn_string.split(';'):
                    if '=' in param:
                        key, value = param.split('=', 1)
                        ftp_params[key] = value
                
                # Build connection string preserving the initial_path
                initial_path = ftp_params.get('initial_path', '')
                new_conn_string = f"port={port};initial_path={initial_path}"
                
                self.conn_manager.repo.update_connection(
                    conn_id,
                    server_name=host,
                    connection_string=new_conn_string
                )
            
            # Immediately reload settings
            self.load_default_settings()
            
            logger.info("Updated global mainframe credentials")
            QMessageBox.information(
                self,
                "Credentials Saved",
                "Global mainframe credentials have been saved!\n\nThey will be used by both Mainframe Nav and Terminal."
            )
                
        except Exception as e:
            logger.error(f"Failed to save credentials: {str(e)}", exc_info=True)
            QMessageBox.warning(
                self, 
                "Save Error", 
                f"Failed to save credentials to database:\n{str(e)}"
            )
    
    def _reload_credentials_from_db(self):
        """Reload credentials from MAINFRAME_USER connection in database"""
        try:
            from suiteview.core.credential_manager import CredentialManager
            cred_manager = CredentialManager()
            
            # Get all connections
            connections = self.conn_manager.repo.get_all_connections()
            
            # Find MAINFRAME_USER connection
            user_conn = None
            for conn in connections:
                if conn.get('connection_name') == 'MAINFRAME_USER':
                    user_conn = conn
                    break
            
            if user_conn:
                # Decrypt username
                encrypted_username = user_conn.get('encrypted_username')
                if encrypted_username:
                    try:
                        self.connection_settings['username'] = cred_manager.decrypt(encrypted_username)
                        logger.info(f"Reloaded username from database: {self.connection_settings['username']}")
                    except Exception as e:
                        logger.error(f"Failed to decrypt username: {e}")
                
                # Decrypt password
                encrypted_password = user_conn.get('encrypted_password')
                if encrypted_password:
                    try:
                        self.connection_settings['password'] = cred_manager.decrypt(encrypted_password)
                        logger.info("Reloaded password from database")
                    except Exception as e:
                        logger.error(f"Failed to decrypt password: {e}")
            else:
                logger.warning("No MAINFRAME_USER connection found in database")
        except Exception as e:
            logger.error(f"Failed to reload credentials from database: {e}")
    
    def connect_to_mainframe(self):
        """Connect to mainframe FTP in background thread"""
        try:
            # Reload credentials from database in case User button updated them
            self._reload_credentials_from_db()
            
            # Disable buttons during connection (load_button removed in UI refactor)
            
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
        # Clear cache on new connection
        self.folder_cache.clear()
        self.status_label.setText("✓ Connected to mainframe")
        self.status_label.setStyleSheet("color: #27ae60; font-weight: bold; padding: 2px; font-size: 11px;")
        logger.info("Successfully connected to mainframe")
        
        # Enable Search Content button
        self.search_content_button.setEnabled(True)
        
        # Auto-load dataset after successful connection
        from PyQt6.QtCore import QTimer
        QTimer.singleShot(200, self.load_dataset)
    
    def on_connection_failed(self, error_message):
        """Handle failed FTP connection"""
        self.ftp_manager = None
        
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
    
    def eventFilter(self, obj, event):
        """Handle events for breadcrumb and path input"""
        from PyQt6.QtCore import QEvent
        
        # Handle click on breadcrumb to show path input
        if obj in (self.breadcrumb_widget, self.breadcrumb_container) and event.type() == QEvent.Type.MouseButtonPress:
            self.show_path_edit()
            return True
        
        # Handle focus loss on path input
        if obj == self.path_input and event.type() == QEvent.Type.FocusOut:
            self.hide_path_edit()
            return True
        
        return super().eventFilter(obj, event)
    
    def show_path_edit(self):
        """Show the path input for copying"""
        if self.current_dataset:
            self.breadcrumb_widget.hide()
            self.path_input.setText(self.current_dataset)
            self.path_input.show()
            self.path_input.setFocus()
            self.path_input.selectAll()
    
    def hide_path_edit(self):
        """Hide the path input and show breadcrumb"""
        self.path_input.hide()
        self.breadcrumb_widget.show()
    
    def on_dataset_search_changed(self, search_text: str):
        """Filter datasets table based on search text with wildcard support"""
        search_text = search_text.strip()
        
        # Convert wildcard pattern (* to .*, ? to .) for regex
        if search_text:
            import re
            # Escape special regex characters except * and ?
            pattern = re.escape(search_text)
            # Replace escaped wildcards with regex equivalents
            pattern = pattern.replace(r'\*', '.*').replace(r'\?', '.')
            # Check case sensitivity setting
            flags = 0 if self.case_sensitive_checkbox.isChecked() else re.IGNORECASE
            regex = re.compile(pattern, flags)
        
        # Show/hide rows based on search
        for row in range(self.members_table.rowCount()):
            name_item = self.members_table.item(row, 0)
            if name_item:
                name = name_item.text()
                if search_text:
                    # Show row if it matches the pattern anywhere in the name
                    self.members_table.setRowHidden(row, not bool(regex.search(name)))
                else:
                    # Show all rows if search is empty
                    self.members_table.setRowHidden(row, False)
    
    def export_selected_datasets(self):
        """Export selected datasets/members to a folder"""
        if not self.ftp_manager:
            QMessageBox.warning(self, "Not Connected", "Please connect to a mainframe first.")
            return
        
        # Get selected rows (unique row numbers)
        selected_rows = set()
        for item in self.members_table.selectedItems():
            selected_rows.add(item.row())
        
        if not selected_rows:
            return
        
        # Ask user to select export folder
        folder_path = QFileDialog.getExistingDirectory(
            self,
            "Select Export Folder",
            "",
            QFileDialog.Option.ShowDirsOnly
        )
        
        if not folder_path:
            return
        
        # Export each selected dataset
        success_count = 0
        failed_items = []
        
        self.status_label.setText("Exporting datasets...")
        QApplication.processEvents()
        
        for row in sorted(selected_rows):
            try:
                name_item = self.members_table.item(row, 0)
                if not name_item:
                    continue
                
                member_name = name_item.text()
                dsorg_item = self.members_table.item(row, 9)
                dsorg = dsorg_item.text() if dsorg_item else ''
                
                # Get dataset data
                item_data = name_item.data(Qt.ItemDataRole.UserRole)
                
                # Build full path based on dataset type
                if item_data and item_data.get('full_path'):
                    # Sequential dataset with full path stored
                    full_path = item_data.get('full_path')
                elif item_data and item_data.get('is_dataset'):
                    # Dataset listed with attributes
                    if dsorg == 'PS':
                        # Sequential dataset - use dotted notation
                        if self.current_dataset:
                            full_path = f"{self.current_dataset}.{member_name}"
                        else:
                            full_path = member_name
                    else:
                        # PO dataset - use parentheses notation
                        if self.current_dataset:
                            full_path = f"{self.current_dataset}({member_name})"
                        else:
                            full_path = member_name
                else:
                    # Regular PDS member
                    if '(' not in self.current_dataset:
                        full_path = f"{self.current_dataset}({member_name})"
                    else:
                        full_path = f"{self.current_dataset}.{member_name}"
                
                logger.info(f"Exporting {full_path}...")
                self.status_label.setText(f"Exporting {member_name}...")
                QApplication.processEvents()
                
                # Read dataset content
                content, total_lines = self.ftp_manager.read_dataset(full_path, max_lines=None)
                
                if content or total_lines > 0:
                    # Save to file
                    import os
                    safe_filename = member_name.replace('/', '_').replace('\\', '_')
                    file_path = os.path.join(folder_path, f"{safe_filename}.txt")
                    
                    with open(file_path, 'w', encoding='utf-8') as f:
                        f.write(content)
                    
                    success_count += 1
                    logger.info(f"Exported {member_name} to {file_path}")
                else:
                    failed_items.append(f"{member_name} (no content)")
                    logger.warning(f"No content found for {member_name}")
                    
            except Exception as e:
                failed_items.append(f"{member_name} ({str(e)})")
                logger.error(f"Failed to export {member_name}: {str(e)}")
        
        # Show summary
        if success_count > 0:
            message = f"Successfully exported {success_count} dataset(s) to:\n{folder_path}"
            if failed_items:
                message += f"\n\nFailed to export {len(failed_items)} item(s):\n" + "\n".join(failed_items[:5])
                if len(failed_items) > 5:
                    message += f"\n...and {len(failed_items) - 5} more"
            
            QMessageBox.information(self, "Export Complete", message)
            self.status_label.setText(f"✓ Exported {success_count} dataset(s)")
            self.status_label.setStyleSheet("color: #27ae60; font-weight: bold; padding: 2px; font-size: 11px;")
        else:
            QMessageBox.warning(self, "Export Failed", 
                f"Failed to export datasets:\n" + "\n".join(failed_items[:10]))
            self.status_label.setText("Export failed")
            self.status_label.setStyleSheet("color: #e74c3c; font-weight: bold; padding: 2px; font-size: 11px;")
    
    def copy_search_results_to_clipboard(self, text: str):
        """Copy search results to clipboard"""
        from PyQt6.QtGui import QGuiApplication
        clipboard = QGuiApplication.clipboard()
        clipboard.setText(text)
        
        self.status_label.setText("✓ Search results copied to clipboard")
        self.status_label.setStyleSheet("color: #27ae60; font-weight: bold; padding: 2px; font-size: 11px;")
        logger.info("Search results copied to clipboard")
    
    def load_dataset(self):
        """Load dataset - now just populates connections list"""
        # Populate connections list
        self.populate_connections_list()
    
    def populate_connections_list(self):
        """Populate the connections list with mainframe connections"""
        self.connections_list.clear()
        
        try:
            # Get all connections
            connections = self.conn_manager.repo.get_all_connections()
            mainframe_connections = [c for c in connections if c.get('connection_type') == 'MAINFRAME_FTP']
            
            # Add each connection to the list
            for conn in mainframe_connections:
                conn_name = conn.get('connection_name', 'Unknown')
                conn_id = conn.get('connection_id')
                
                item = QListWidgetItem(f"🖥️ {conn_name}")
                item.setData(Qt.ItemDataRole.UserRole, conn_id)
                self.connections_list.addItem(item)
            
            logger.info(f"Populated {len(mainframe_connections)} connections in list")
            
        except Exception as e:
            logger.error(f"Failed to populate connections list: {str(e)}")
    
    def load_connection_dataset(self, connection_id):
        """Load dataset for a specific connection"""
        try:
            # Set current connection
            self.current_connection_id = connection_id
            
            # Get connection details
            connection = self.conn_manager.repo.get_connection(connection_id)
            if not connection:
                return
            
            # Parse connection string for dataset path
            conn_string = connection.get('connection_string', '')
            ftp_params = {}
            for param in conn_string.split(';'):
                if '=' in param:
                    key, value = param.split('=', 1)
                    ftp_params[key] = value
            
            initial_path = ftp_params.get('initial_path', '').strip()
            if not initial_path:
                QMessageBox.warning(self, "No Dataset Path", 
                    "This connection does not have a dataset path configured.\n"
                    "Please edit the connection to add one.")
                return
            
            # Connect to mainframe if not already connected or different connection
            if not self.ftp_manager or self.current_connection_id != connection_id:
                # Trigger connection
                self.connect_to_mainframe()
                return
            
            # Clear navigation history when loading new connection
            self.navigation_history = []
            self.current_history_index = -1
            
            # Navigate to initial path
            self.navigate_to_dataset(initial_path)
            
        except Exception as e:
            logger.error(f"Failed to load connection dataset: {str(e)}")
            QMessageBox.critical(self, "Load Error", f"Failed to load dataset:\n{str(e)}")
    
    def on_tree_item_clicked(self, item, column):
        """DEPRECATED - kept for compatibility but no longer used"""
        pass
    
    def load_members(self, dataset_path):
        """Load members/files for the selected dataset"""
        try:
            # Check if FTP connection is still alive
            if not self.ftp_manager or not self.ftp_manager.is_alive():
                QApplication.restoreOverrideCursor()
                self.status_label.setText("✗ Mainframe connection lost")
                self.status_label.setStyleSheet("color: #e74c3c; font-weight: bold; padding: 2px; font-size: 11px;")
                QMessageBox.warning(
                    self,
                    "Connection Lost",
                    "The mainframe connection has been lost.\n\n"
                    "The mainframe region may be down or the connection timed out.\n\n"
                    "Please reconnect to the mainframe by selecting a connection from the list."
                )
                self.ftp_manager = None
                return
            
            # Set wait cursor and show loading status immediately
            QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
            self.status_label.setText(f"Loading {dataset_path}...")
            QApplication.processEvents()
            
            self.members_table.setRowCount(0)
            
            # Update breadcrumb navigation
            self.update_breadcrumb(dataset_path)
            self.update_navigation_buttons()
            
            # Get icons
            folder_icon = self.style().standardIcon(QStyle.StandardPixmap.SP_DirIcon)
            file_icon = self.style().standardIcon(QStyle.StandardPixmap.SP_FileIcon)
            
            items_to_display = []
            
            # Always try to list members (files) in the dataset from FTP
            try:
                # Check cache first
                if dataset_path in self.folder_cache:
                    logger.info(f"Using cached data for {dataset_path}")
                    members = self.folder_cache[dataset_path]
                else:
                    logger.info(f"Fetching data from FTP for {dataset_path}")
                    members = self.ftp_manager.list_datasets(dataset_path)
                    # Store in cache
                    if members:
                        self.folder_cache[dataset_path] = members
                        logger.info(f"Cached {len(members)} items for {dataset_path}")
                
                if members:
                    for member in members:
                        member_type = member.get('type', 'member')
                        is_dataset = member.get('is_dataset', False)
                        
                        # Check if this is a dataset with attributes (from _parse_dataset_attributes)
                        if is_dataset:
                            items_to_display.append({
                                'name': member.get('name', ''),
                                'volume': member.get('volume', ''),
                                'unit': member.get('unit', ''),
                                'referred': member.get('referred', ''),
                                'ext': member.get('ext', ''),
                                'used': member.get('used', ''),
                                'recfm': member.get('recfm', ''),
                                'lrecl': member.get('lrecl', ''),
                                'blksz': member.get('blksz', ''),
                                'dsorg': member.get('dsorg', ''),
                                'is_folder': False,
                                'is_dataset': True,
                                'full_path': member.get('full_path', '')
                            })
                        # Check if this is a sequential dataset (PS)
                        elif member_type == 'sequential_dataset':
                            items_to_display.append({
                                'name': member.get('name', ''),
                                'volume': '',
                                'unit': '',
                                'referred': member.get('modified', ''),
                                'ext': '',
                                'used': '',
                                'recfm': '',
                                'lrecl': '',
                                'blksz': '',
                                'dsorg': 'PS',
                                'is_folder': False,
                                'is_sequential': True,
                                'full_path': member.get('full_path', '')
                            })
                        else:
                            # Regular PDS member
                            items_to_display.append({
                                'name': member.get('name', ''),
                                'volume': '',
                                'unit': '',
                                'referred': member.get('modified', ''),
                                'ext': '',
                                'used': '',
                                'recfm': '',
                                'lrecl': '',
                                'blksz': '',
                                'dsorg': 'PO',
                                'is_folder': False,
                                'is_member': True
                            })
            except Exception as e:
                logger.debug(f"No members found or error listing: {str(e)}")
            
            if not items_to_display:
                self.status_label.setText(f"No items found in {dataset_path}")
                # Restore cursor before returning
                QApplication.restoreOverrideCursor()
                return
            
            # Populate members table with all dataset attributes
            self.members_table.setRowCount(len(items_to_display))
            
            # Show loading message for large datasets
            if len(items_to_display) > 1000:
                self.status_label.setText(f"Loading {len(items_to_display)} items...")
                QApplication.processEvents()  # Update UI
            
            # Disable sorting during bulk insert for performance
            self.members_table.setSortingEnabled(False)
            
            for row, item in enumerate(items_to_display):
                # Update progress every 5000 items
                if len(items_to_display) > 5000 and row % 5000 == 0 and row > 0:
                    self.status_label.setText(f"Loading {row}/{len(items_to_display)} items...")
                    QApplication.processEvents()  # Keep UI responsive
                # Column 0: Name with icon
                name_item = QTableWidgetItem(item['name'])
                if item['is_folder']:
                    name_item.setIcon(folder_icon)
                else:
                    name_item.setIcon(file_icon)
                
                # Store dataset info and full path
                if item.get('is_dataset') or item.get('is_sequential'):
                    item_data = {
                        'full_path': item.get('full_path', ''),
                        'is_dataset': item.get('is_dataset', False),
                        'is_sequential': item.get('is_sequential', False),
                        'dsorg': item.get('dsorg', '')
                    }
                    name_item.setData(Qt.ItemDataRole.UserRole, item_data)
                
                self.members_table.setItem(row, 0, name_item)
                
                # Column 1: Volume
                self.members_table.setItem(row, 1, QTableWidgetItem(item.get('volume', '')))
                
                # Column 2: Unit
                self.members_table.setItem(row, 2, QTableWidgetItem(item.get('unit', '')))
                
                # Column 3: Referred (date)
                self.members_table.setItem(row, 3, QTableWidgetItem(item.get('referred', '')))
                
                # Column 4: Ext
                self.members_table.setItem(row, 4, QTableWidgetItem(item.get('ext', '')))
                
                # Column 5: Used
                self.members_table.setItem(row, 5, QTableWidgetItem(item.get('used', '')))
                
                # Column 6: Recfm
                self.members_table.setItem(row, 6, QTableWidgetItem(item.get('recfm', '')))
                
                # Column 7: Lrecl
                self.members_table.setItem(row, 7, QTableWidgetItem(item.get('lrecl', '')))
                
                # Column 8: BlkSz
                self.members_table.setItem(row, 8, QTableWidgetItem(item.get('blksz', '')))
                
                # Column 9: Dsorg
                self.members_table.setItem(row, 9, QTableWidgetItem(item.get('dsorg', '')))
            
            # Re-enable sorting after bulk insert
            self.members_table.setSortingEnabled(True)
            
            folder_count = sum(1 for item in items_to_display if item['is_folder'])
            dataset_count = sum(1 for item in items_to_display if item.get('is_dataset', False))
            member_count = len(items_to_display) - folder_count - dataset_count
            total_count = len(items_to_display)
            
            # Show item count in the right side label
            if dataset_count > 0:
                self.item_count_label.setText(f"{total_count} items ({dataset_count} dataset(s))")
            elif member_count > 0:
                self.item_count_label.setText(f"{total_count} items ({member_count} member(s))")
            elif folder_count > 0:
                self.item_count_label.setText(f"{total_count} items ({folder_count} folder(s))")
            else:
                self.item_count_label.setText(f"{total_count} items")
            
            # Update status to show completion
            self.status_label.setText(f"Loaded {dataset_path}")
            
            # Restore cursor
            QApplication.restoreOverrideCursor()
            
            # Disable delete until a member is selected
            self.delete_member_button.setEnabled(False)
            
        except Exception as e:
            logger.error(f"Failed to load members: {str(e)}")
            # Restore cursor on error too
            QApplication.restoreOverrideCursor()
            self.status_label.setText(f"✗ Failed to load members")
            QMessageBox.warning(self, "Load Error", f"Failed to load members:\n{str(e)}")
    
    def show_context_menu(self, position):
        """Show context menu for right-click on table items"""
        from PyQt6.QtWidgets import QMenu
        from PyQt6.QtGui import QGuiApplication
        
        # Get the item at the clicked position
        item = self.members_table.itemAt(position)
        if not item:
            return
        
        row = item.row()
        name_item = self.members_table.item(row, 0)
        if not name_item:
            return
        
        member_name = name_item.text()
        if not member_name:
            return
        
        # Get dataset data to determine the full path
        item_data = name_item.data(Qt.ItemDataRole.UserRole)
        
        # Build full path for the clicked item
        if item_data and item_data.get('full_path'):
            # Sequential dataset with full path stored
            full_path = item_data.get('full_path')
        elif item_data and item_data.get('is_dataset'):
            # Dataset - just the dataset name itself
            full_path = f"{self.current_dataset}.{member_name}"
        else:
            # PDS member - use (MEMBER) syntax
            full_path = f"{self.current_dataset}({member_name})"
        
        # Create context menu
        menu = QMenu(self)
        
        # Add to Search option - handle multiple selections
        selected_rows = set(item.row() for item in self.members_table.selectedItems())
        if len(selected_rows) > 1:
            add_to_search_action = menu.addAction(f"🔍 Add {len(selected_rows)} Datasets to Search")
        else:
            add_to_search_action = menu.addAction("🔍 Add to Search")
        add_to_search_action.triggered.connect(self.add_selected_to_search_content)
        
        menu.addSeparator()
        
        # Add Copy Full Path action
        copy_action = menu.addAction("📋 Copy Full Path")
        copy_action.triggered.connect(lambda: self.copy_full_path(full_path))
        
        # Show menu at cursor position
        menu.exec(self.members_table.viewport().mapToGlobal(position))
    
    def copy_full_path(self, full_path):
        """Copy the full path to clipboard"""
        from PyQt6.QtGui import QGuiApplication
        
        clipboard = QGuiApplication.clipboard()
        clipboard.setText(full_path)
        
        self.status_label.setText(f"✓ Copied to clipboard: {full_path}")
        self.status_label.setStyleSheet("color: #27ae60; font-weight: bold; padding: 2px; font-size: 11px;")
        logger.info(f"Copied full path to clipboard: {full_path}")
    
    def open_search_content_window(self):
        """Open or show the search content window"""
        if not self.ftp_manager:
            QMessageBox.warning(self, "Not Connected", "Please connect to a mainframe first.")
            return
        
        if self.search_content_window is None or not self.search_content_window.isVisible():
            from suiteview.ui.search_content_window import SearchContentWindow
            self.search_content_window = SearchContentWindow(self.ftp_manager, self)
            self.search_content_window.show()
        else:
            # Bring window to front
            self.search_content_window.raise_()
            self.search_content_window.activateWindow()
    
    def add_to_search_content(self, member_name, full_path, item_data):
        """Add selected dataset to search content window"""
        if not self.ftp_manager:
            QMessageBox.warning(self, "Not Connected", "Please connect to a mainframe first.")
            return
        
        # Get dsorg
        dsorg = ''
        if item_data:
            dsorg = item_data.get('dsorg', '')
        
        # Open search window if not open
        if self.search_content_window is None or not self.search_content_window.isVisible():
            from suiteview.ui.search_content_window import SearchContentWindow
            self.search_content_window = SearchContentWindow(self.ftp_manager, self)
            self.search_content_window.show()
        
        # Add dataset to search
        self.search_content_window.add_dataset(member_name, full_path, dsorg)
        
        # Bring window to front
        self.search_content_window.raise_()
        self.search_content_window.activateWindow()
        
        self.status_label.setText(f"✓ Added {member_name} to Search Content")
        self.status_label.setStyleSheet("color: #27ae60; font-weight: bold; padding: 2px; font-size: 11px;")
    
    def add_selected_to_search_content(self):
        """Add all selected datasets to search content window"""
        if not self.ftp_manager:
            QMessageBox.warning(self, "Not Connected", "Please connect to a mainframe first.")
            return
        
        # Get all selected rows (unique)
        selected_rows = set(item.row() for item in self.members_table.selectedItems())
        
        if not selected_rows:
            return
        
        # Open search window if not open
        if self.search_content_window is None or not self.search_content_window.isVisible():
            from suiteview.ui.search_content_window import SearchContentWindow
            self.search_content_window = SearchContentWindow(self.ftp_manager, self)
            self.search_content_window.show()
        
        # Add each selected dataset
        added_count = 0
        for row in sorted(selected_rows):
            name_item = self.members_table.item(row, 0)
            if not name_item:
                continue
            
            member_name = name_item.text()
            item_data = name_item.data(Qt.ItemDataRole.UserRole)
            
            # Build full path
            if item_data and item_data.get('full_path'):
                full_path = item_data.get('full_path')
            elif item_data and item_data.get('is_dataset'):
                full_path = f"{self.current_dataset}.{member_name}"
            else:
                full_path = f"{self.current_dataset}({member_name})"
            
            # Get dsorg
            dsorg = item_data.get('dsorg', '') if item_data else ''
            
            # Add to search window (silently skips duplicates)
            self.search_content_window.add_dataset(member_name, full_path, dsorg)
            added_count += 1
        
        # Bring window to front
        self.search_content_window.raise_()
        self.search_content_window.activateWindow()
        
        self.status_label.setText(f"✓ Added {added_count} dataset(s) to Search Content")
        self.status_label.setStyleSheet("color: #27ae60; font-weight: bold; padding: 2px; font-size: 11px;")
    
    def on_member_selected(self):
        """Handle member selection - enable/disable buttons"""
        selected_rows = self.members_table.selectedItems()
        if not selected_rows:
            self.delete_member_button.setEnabled(False)
            self.export_button.setEnabled(False)
            return
        
        # Enable export for any selection
        self.export_button.setEnabled(True)
        
        # Get the name and dataset info from the selected row
        row = selected_rows[0].row()
        name_item = self.members_table.item(row, 0)
        if not name_item:
            self.delete_member_button.setEnabled(False)
            return
            
        member_name = name_item.text()
        
        # Safely get Dsorg column
        dsorg_item = self.members_table.item(row, 9)
        dsorg = dsorg_item.text() if dsorg_item else ''
        
        if not member_name:
            self.delete_member_button.setEnabled(False)
            return
        
        logger.info(f"Member selected: {member_name} (Dsorg: {dsorg})")
        
        # Get dataset data
        item_data = name_item.data(Qt.ItemDataRole.UserRole)
        
        # Enable delete button for PDS members only (not datasets themselves)
        if dsorg == 'PO' and not (item_data and item_data.get('is_dataset')):
            self.delete_member_button.setEnabled(True)
        else:
            self.delete_member_button.setEnabled(False)
    
    def on_item_double_clicked(self, item):
        """Handle double-click on table item - navigate into PO/GDG datasets or view PS/members"""
        if not item:
            return
        
        row = item.row()
        name_item = self.members_table.item(row, 0)
        if not name_item:
            return
            
        member_name = name_item.text()
        
        # Safely get Dsorg column
        dsorg_item = self.members_table.item(row, 9)
        dsorg = dsorg_item.text() if dsorg_item else ''
        
        if not member_name:
            return
        
        logger.info(f"Double-clicked: {member_name} (Dsorg: {dsorg})")
        
        # Get dataset data
        item_data = name_item.data(Qt.ItemDataRole.UserRole)
        
        # If it's a PO (Partitioned) or GDG (Generation Data Group), navigate into it to show contents
        if item_data and item_data.get('is_dataset'):
            if dsorg in ('PO', 'GDG'):
                # Navigate into the dataset to show members/generations
                new_path = f"{self.current_dataset}.{member_name}"
                self.navigate_to_dataset(new_path)
                return
            elif dsorg == 'PS':
                # PS (Physical Sequential) is a file - view it
                self.view_selected_item()
                return
        
        # Otherwise, view the content (PDS member or other file)
        self.view_selected_item()
    
    def update_breadcrumb(self, dataset_path):
        """Update breadcrumb navigation with clickable path segments (File Nav style)"""
        # Clear existing breadcrumb
        while self.breadcrumb_layout.count():
            child = self.breadcrumb_layout.takeAt(0)
            if child.widget():
                child.widget().deleteLater()
        
        if not dataset_path:
            # Show placeholder when no path
            label = QLabel("Select a connection")
            label.setStyleSheet(
                "color: #4A6FA5; "
                "font-style: italic; "
                "font-size: 10pt;"
            )
            self.breadcrumb_layout.addWidget(label)
            return
        
        # Split path into segments
        segments = dataset_path.split('.')
        
        # Create clickable button for each segment (like File Nav)
        for i, segment in enumerate(segments):
            # Add separator before each segment except the first
            if i > 0:
                sep = QLabel(" > ")
                sep.setStyleSheet(
                    "color: #2563EB; "
                    "font-weight: normal; "
                    "font-size: 11pt; "
                    "background: transparent; "
                    "border: none; "
                    "padding: 0px; "
                    "margin: 0px;"
                )
                self.breadcrumb_layout.addWidget(sep)
            
            # Create clickable button styled as text (like File Nav)
            btn = QPushButton(segment)
            btn.setFlat(True)  # Remove button appearance
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            
            # Build the partial path for this segment
            partial_path = '.'.join(segments[:i+1])
            
            # Style as hyperlink - blue, bold, underline on hover
            btn.setStyleSheet("""
                QPushButton {
                    color: #2563EB;
                    font-weight: 600;
                    font-size: 11pt;
                    border: none;
                    background: transparent;
                    text-align: left;
                    padding: 2px 4px;
                    margin: 0px;
                }
                QPushButton:hover {
                    text-decoration: underline;
                }
                QPushButton:focus {
                    outline: none;
                    border: none;
                }
            """)
            
            # Connect click to navigate to this segment
            btn.clicked.connect(lambda checked, path=partial_path: self.navigate_to_dataset(path))
            
            self.breadcrumb_layout.addWidget(btn)
        
        # Add stretch at the end to keep segments left-aligned
        self.breadcrumb_layout.addStretch()
    
    def navigate_to_dataset(self, dataset_path, add_to_history=True):
        """Navigate to a specific dataset path"""
        if not self.ftp_manager:
            return
        
        # Show immediate feedback
        self.status_label.setText(f"Loading {dataset_path}...")
        QApplication.processEvents()  # Update UI immediately
        
        # Save where we're coming from for potential history management
        old_dataset = self.current_dataset
        
        # Navigate to new path FIRST
        self.current_dataset = dataset_path
        self.load_members(dataset_path)
        self.update_breadcrumb(dataset_path)
        
        # THEN manage history if this is a new navigation (not from back/forward buttons)
        if add_to_history:
            # If we're not at the end of history, truncate forward history
            if self.current_history_index < len(self.navigation_history) - 1:
                self.navigation_history = self.navigation_history[:self.current_history_index + 1]
            
            # Add the NEW location to history
            if not self.navigation_history or self.navigation_history[-1] != dataset_path:
                self.navigation_history.append(dataset_path)
                self.current_history_index = len(self.navigation_history) - 1
        
        # Update button states
        self.update_navigation_buttons()
    
    def navigate_back(self):
        """Navigate to previous location in history"""
        if self.current_history_index > 0:
            self.current_history_index -= 1
            dataset_path = self.navigation_history[self.current_history_index]
            self.navigate_to_dataset(dataset_path, add_to_history=False)
    
    def navigate_forward(self):
        """Navigate to next location in history"""
        if self.current_history_index < len(self.navigation_history) - 1:
            self.current_history_index += 1
            dataset_path = self.navigation_history[self.current_history_index]
            self.navigate_to_dataset(dataset_path, add_to_history=False)
    
    def navigate_up(self):
        """Navigate to parent dataset (one level up)"""
        if not self.current_dataset:
            return
        
        # Split current path and remove last segment
        segments = self.current_dataset.split('.')
        if len(segments) > 1:
            parent_path = '.'.join(segments[:-1])
            # Navigate up - this DOES add to history so Back works correctly
            self.navigate_to_dataset(parent_path)
        # If already at root (only one segment), do nothing
    
    def update_navigation_buttons(self):
        """Update enabled state of navigation buttons"""
        # Back button enabled if there's history to go back to
        self.back_button.setEnabled(self.current_history_index > 0)
        
        # Forward button enabled if there's history to go forward to
        self.forward_button.setEnabled(
            self.current_history_index < len(self.navigation_history) - 1
        )
        
        # Up button enabled if not at root level (more than one segment)
        has_parent = self.current_dataset and len(self.current_dataset.split('.')) > 1
        self.up_button.setEnabled(has_parent)
    
    def on_connection_list_item_clicked(self, item):
        """Handle click on connection in list - load its dataset"""
        if not item:
            return
        
        # Get connection ID from item data
        connection_id = item.data(Qt.ItemDataRole.UserRole)
        if not connection_id:
            return
        
        # Load connection's dataset
        self.load_connection_dataset(connection_id)
    
    def save_splitter_sizes(self):
        """Save splitter sizes to file for persistence"""
        try:
            import json
            from pathlib import Path
            
            # Save to app config directory
            config_dir = Path.home() / '.suiteview'
            config_dir.mkdir(exist_ok=True)
            config_file = config_dir / 'mainframe_nav_splitter.json'
            
            # Get splitter sizes
            sizes = self.main_splitter.sizes()
            
            with open(config_file, 'w') as f:
                json.dump({'sizes': sizes}, f, indent=2)
            
            logger.debug(f"Saved splitter sizes: {sizes}")
        except Exception as e:
            logger.error(f"Failed to save splitter sizes: {e}")
    
    def load_splitter_sizes(self):
        """Load saved splitter sizes from file"""
        try:
            import json
            from pathlib import Path
            
            config_file = Path.home() / '.suiteview' / 'mainframe_nav_splitter.json'
            
            if not config_file.exists():
                return
            
            with open(config_file, 'r') as f:
                data = json.load(f)
            
            sizes = data.get('sizes', [])
            if sizes and len(sizes) == 2:
                self.main_splitter.setSizes(sizes)
                logger.debug(f"Loaded splitter sizes: {sizes}")
        except Exception as e:
            logger.error(f"Failed to load splitter sizes: {e}")
    
    def save_column_widths(self):
        """Save column widths to file for persistence"""
        try:
            import json
            from pathlib import Path
            
            # Save to app config directory
            config_dir = Path.home() / '.suiteview'
            config_dir.mkdir(exist_ok=True)
            config_file = config_dir / 'mainframe_nav_columns.json'
            
            # Get all column widths
            widths = {}
            for i in range(self.members_table.columnCount()):
                header = self.members_table.horizontalHeaderItem(i)
                if header:
                    widths[header.text()] = self.members_table.columnWidth(i)
            
            with open(config_file, 'w') as f:
                json.dump(widths, f, indent=2)
            
            logger.debug(f"Saved column widths: {widths}")
        except Exception as e:
            logger.error(f"Failed to save column widths: {e}")
    
    def load_column_widths(self):
        """Load saved column widths from file"""
        try:
            import json
            from pathlib import Path
            
            config_file = Path.home() / '.suiteview' / 'mainframe_nav_columns.json'
            
            if not config_file.exists():
                return
            
            with open(config_file, 'r') as f:
                widths = json.load(f)
            
            # Apply saved widths
            for i in range(self.members_table.columnCount()):
                header = self.members_table.horizontalHeaderItem(i)
                if header and header.text() in widths:
                    self.members_table.setColumnWidth(i, widths[header.text()])
            
            logger.debug(f"Loaded column widths: {widths}")
        except Exception as e:
            logger.error(f"Failed to load column widths: {e}")
    
    def view_selected_item(self):
        """View the selected dataset or member content in a dialog"""
        selected_rows = self.members_table.selectedItems()
        if not selected_rows:
            return
        
        # Get the name and dataset info from the selected row
        row = selected_rows[0].row()
        name_item = self.members_table.item(row, 0)
        if not name_item:
            return
            
        member_name = name_item.text()
        
        # Safely get Dsorg column
        dsorg_item = self.members_table.item(row, 9)
        dsorg = dsorg_item.text() if dsorg_item else ''
        
        if not member_name:
            return
        
        # Check if FTP manager is connected and alive
        if not self.ftp_manager:
            QMessageBox.warning(
                self,
                "Not Connected",
                "FTP connection lost. Please reconnect to mainframe."
            )
            return
        
        if not self.ftp_manager.is_alive():
            self.status_label.setText("✗ Mainframe connection lost")
            self.status_label.setStyleSheet("color: #e74c3c; font-weight: bold; padding: 2px; font-size: 11px;")
            QMessageBox.warning(
                self,
                "Connection Lost",
                "The mainframe connection has been lost.\n\n"
                "The mainframe region may be down or the connection timed out.\n\n"
                "Please reconnect to the mainframe by selecting a connection from the list."
            )
            self.ftp_manager = None
            return
        
        # Get dataset data
        item_data = name_item.data(Qt.ItemDataRole.UserRole)
        
        try:
            # Build full member path
            if item_data and item_data.get('full_path'):
                # Use explicit full path if provided
                member_path = item_data.get('full_path')
                logger.info(f"Loading dataset with full path: {member_path}")
            elif item_data and item_data.get('is_dataset'):
                # This is a dataset listed with attributes
                # For PS datasets, use dotted notation (not parentheses)
                # For PO datasets being viewed as members, use parentheses
                if dsorg == 'PS':
                    # Sequential dataset - use full dotted path
                    member_path = f"{self.current_dataset}.{member_name}"
                    logger.info(f"Loading PS dataset: {member_path}")
                else:
                    # PO or other - treat as member with parentheses
                    member_path = f"{self.current_dataset}({member_name})"
                    logger.info(f"Loading dataset member: {member_path}")
            elif dsorg == 'PS':
                # Sequential dataset - could be member or standalone
                # If we're inside a PDS, treat as member
                if '(' not in self.current_dataset:
                    member_path = f"{self.current_dataset}({member_name})"
                else:
                    member_path = f"{self.current_dataset}.{member_name}"
                logger.info(f"Loading PS dataset: {member_path}")
            else:
                # PDS member syntax: DATASET(MEMBER)
                member_path = f"{self.current_dataset}({member_name})"
                logger.info(f"Loading PDS member: {member_path}")
            
            self.status_label.setText(f"Loading {member_name}...")
            self.status_label.setStyleSheet("color: #3498db; font-style: italic; padding: 2px; font-size: 11px;")
            
            # Read first 1000 rows
            content, line_count = self.ftp_manager.read_dataset(member_path, max_lines=1000)
            
            # Check if connection is still alive after read attempt
            if line_count == 0 and len(content) == 0:
                if not self.ftp_manager.is_alive():
                    self.status_label.setText("✗ Connection lost while reading dataset")
                    self.status_label.setStyleSheet("color: #e74c3c; font-weight: bold; padding: 2px; font-size: 11px;")
                    QMessageBox.warning(
                        self,
                        "Connection Lost",
                        f"Failed to read {member_name}.\n\n"
                        "The FTP connection was lost during the read operation.\n\n"
                        "Please reconnect by selecting a connection from the list."
                    )
                    self.ftp_manager = None
                    return
                else:
                    # Dataset might be empty, binary, or have other issues
                    logger.warning(f"Dataset {member_path} returned 0 lines but connection is still alive")
                    
                    # Get dataset info for better error message
                    item_data = name_item.data(Qt.ItemDataRole.UserRole)
                    recfm = item_data.get('recfm', 'Unknown') if item_data else 'Unknown'
                    used = item_data.get('used', '0') if item_data else '0'
                    
                    error_msg = f"Dataset {member_name} returned no readable content.\n\nPath: {member_path}\n"
                    
                    if int(used) > 0:
                        error_msg += f"\nThis dataset shows {used} tracks used but returned 0 lines.\n"
                        error_msg += "\nPossible reasons:\n"
                        error_msg += "• Dataset contains binary data (not text)\n"
                        error_msg += "• Dataset contains only control characters\n"
                        if recfm == 'VB':
                            error_msg += "• VB (Variable Block) format may have compatibility issues\n"
                        error_msg += "• Dataset may be migrated/archived\n"
                        error_msg += "\nTry viewing this dataset on the mainframe directly (TSO/ISPF)\nto verify its contents."
                    else:
                        error_msg += "\nThis dataset appears to be empty (0 tracks used)."
                    
                    QMessageBox.warning(
                        self,
                        "No Content",
                        error_msg
                    )
                    self.status_label.setText(f"✗ Could not read {member_name}")
                    self.status_label.setStyleSheet("color: #e74c3c; font-weight: bold; padding: 2px; font-size: 11px;")
                    return
            
            logger.info(f"Loaded {line_count} lines from {member_name}")
            
            # Show content in a dialog
            from PyQt6.QtWidgets import QDialog, QVBoxLayout, QHBoxLayout, QTextEdit, QDialogButtonBox, QLabel, QPushButton, QFileDialog
            from PyQt6.QtGui import QGuiApplication
            
            dialog = QDialog(self)
            dialog.setWindowTitle(f"View: {member_name}")
            dialog.resize(900, 700)
            
            layout = QVBoxLayout(dialog)
            
            # Info label
            info_label = QLabel(f"Showing first 1000 lines of {member_name} (Total: {line_count} lines)")
            info_label.setStyleSheet("font-weight: bold; padding: 4px; background-color: #e8f4f8;")
            layout.addWidget(info_label)
            
            # Text viewer
            text_edit = QTextEdit()
            text_edit.setReadOnly(True)
            text_edit.setFont(QFont("Courier New", 9))
            text_edit.setPlainText(content)
            layout.addWidget(text_edit)
            
            # Track edit mode
            is_edit_mode = [False]  # Use list to allow modification in nested functions
            
            # Action buttons row
            action_layout = QHBoxLayout()
            
            # Edit/Cancel button
            edit_btn = QPushButton("✏️ Edit")
            edit_btn.setStyleSheet("""
                QPushButton {
                    background-color: #4A6FA5;
                    color: white;
                    border: none;
                    padding: 6px 12px;
                    font-size: 10pt;
                }
                QPushButton:hover {
                    background-color: #3D5A7F;
                }
            """)
            
            # Save button (initially hidden)
            save_btn = QPushButton("💾 Save Changes")
            save_btn.setStyleSheet("""
                QPushButton {
                    background-color: #4A6FA5;
                    color: white;
                    border: none;
                    padding: 6px 12px;
                    font-size: 10pt;
                }
                QPushButton:hover {
                    background-color: #3D5A7F;
                }
            """)
            save_btn.setVisible(False)
            
            def toggle_edit():
                if is_edit_mode[0]:
                    # Cancel edit - restore original content
                    reply = QMessageBox.question(
                        dialog,
                        "Cancel Edit",
                        "Discard changes?",
                        QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                        QMessageBox.StandardButton.No
                    )
                    if reply == QMessageBox.StandardButton.Yes:
                        text_edit.setReadOnly(True)
                        text_edit.setPlainText(content)
                        is_edit_mode[0] = False
                        edit_btn.setText("✏️ Edit")
                        save_btn.setVisible(False)
                        load_all_btn.setEnabled(True)
                        info_label.setText(f"Showing first 1000 lines of {member_name} (Total: {line_count} lines)")
                else:
                    # Enter edit mode
                    text_edit.setReadOnly(False)
                    is_edit_mode[0] = True
                    edit_btn.setText("❌ Cancel")
                    save_btn.setVisible(True)
                    load_all_btn.setEnabled(False)
                    info_label.setText(f"✏️ Edit mode - Make changes and click Save")
                    info_label.setStyleSheet("font-weight: bold; padding: 4px; background-color: #fff3cd;")
            
            def save_changes():
                reply = QMessageBox.question(
                    dialog,
                    "Save Changes",
                    f"Save changes to {member_name}?",
                    QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                    QMessageBox.StandardButton.Yes
                )
                
                if reply == QMessageBox.StandardButton.Yes:
                    try:
                        info_label.setText(f"Saving changes to {member_name}...")
                        dialog.setCursor(Qt.CursorShape.WaitCursor)
                        
                        modified_content = text_edit.toPlainText()
                        success, message = self.ftp_manager.write_content(member_path, modified_content)
                        
                        dialog.setCursor(Qt.CursorShape.ArrowCursor)
                        
                        if success:
                            text_edit.setReadOnly(True)
                            is_edit_mode[0] = False
                            edit_btn.setText("✏️ Edit")
                            save_btn.setVisible(False)
                            load_all_btn.setEnabled(True)
                            info_label.setText(f"✓ {message}")
                            info_label.setStyleSheet("font-weight: bold; padding: 4px; background-color: #d4edda;")
                            QMessageBox.information(dialog, "Save Complete", message)
                            # Clear cache so we reload fresh data
                            if self.current_dataset in self.folder_cache:
                                del self.folder_cache[self.current_dataset]
                        else:
                            info_label.setText(f"✗ {message}")
                            info_label.setStyleSheet("font-weight: bold; padding: 4px; background-color: #f8d7da;")
                            QMessageBox.critical(dialog, "Save Error", message)
                    except Exception as e:
                        dialog.setCursor(Qt.CursorShape.ArrowCursor)
                        QMessageBox.critical(dialog, "Save Error", f"Failed to save:\n{str(e)}")
            
            edit_btn.clicked.connect(toggle_edit)
            save_btn.clicked.connect(save_changes)
            action_layout.addWidget(edit_btn)
            action_layout.addWidget(save_btn)
            
            # Load All button
            load_all_btn = QPushButton("Load All Lines")
            load_all_btn.setStyleSheet("""
                QPushButton {
                    background-color: #4A6FA5;
                    color: white;
                    border: none;
                    padding: 6px 12px;
                    font-size: 10pt;
                }
                QPushButton:hover {
                    background-color: #3D5A7F;
                }
            """)
            def load_all():
                try:
                    info_label.setText(f"Loading all lines from {member_name}...")
                    dialog.setCursor(Qt.CursorShape.WaitCursor)
                    full_content, total_lines = self.ftp_manager.read_dataset(member_path, max_lines=None)
                    text_edit.setPlainText(full_content)
                    info_label.setText(f"Showing all {total_lines} lines of {member_name}")
                    load_all_btn.setEnabled(False)
                    dialog.setCursor(Qt.CursorShape.ArrowCursor)
                except Exception as e:
                    dialog.setCursor(Qt.CursorShape.ArrowCursor)
                    QMessageBox.critical(dialog, "Load Error", f"Failed to load all lines:\n{str(e)}")
            
            load_all_btn.clicked.connect(load_all)
            action_layout.addWidget(load_all_btn)
            
            # Copy to Clipboard button
            copy_btn = QPushButton("Copy to Clipboard")
            copy_btn.setStyleSheet("""
                QPushButton {
                    background-color: #4A6FA5;
                    color: white;
                    border: none;
                    padding: 6px 12px;
                    font-size: 10pt;
                }
                QPushButton:hover {
                    background-color: #3D5A7F;
                }
            """)
            def copy_to_clipboard():
                clipboard = QGuiApplication.clipboard()
                clipboard.setText(text_edit.toPlainText())
                info_label.setText(f"✓ Copied {len(text_edit.toPlainText().splitlines())} lines to clipboard")
            
            copy_btn.clicked.connect(copy_to_clipboard)
            action_layout.addWidget(copy_btn)
            
            # Export to File button
            export_btn = QPushButton("Export to File")
            export_btn.setStyleSheet("""
                QPushButton {
                    background-color: #4A6FA5;
                    color: white;
                    border: none;
                    padding: 6px 12px;
                    font-size: 10pt;
                }
                QPushButton:hover {
                    background-color: #3D5A7F;
                }
            """)
            def export_to_file():
                filename, _ = QFileDialog.getSaveFileName(
                    dialog,
                    "Export to File",
                    f"{member_name}.txt",
                    "Text Files (*.txt);;All Files (*.*)"
                )
                if filename:
                    try:
                        with open(filename, 'w', encoding='utf-8') as f:
                            f.write(text_edit.toPlainText())
                        info_label.setText(f"✓ Exported to {filename}")
                        QMessageBox.information(dialog, "Export Complete", f"File saved to:\n{filename}")
                    except Exception as e:
                        QMessageBox.critical(dialog, "Export Error", f"Failed to export:\n{str(e)}")
            
            export_btn.clicked.connect(export_to_file)
            action_layout.addWidget(export_btn)
            
            action_layout.addStretch()
            layout.addLayout(action_layout)
            
            # Close button
            close_btn = QPushButton("Close")
            close_btn.setStyleSheet("""
                QPushButton {
                    background-color: #4A6FA5;
                    color: white;
                    border: none;
                    padding: 6px 12px;
                    font-size: 10pt;
                }
                QPushButton:hover {
                    background-color: #3D5A7F;
                }
            """)
            close_btn.clicked.connect(dialog.reject)
            action_layout.addWidget(close_btn)
            action_layout.addStretch()
            layout.addLayout(action_layout)
            
            dialog.exec()
            
            self.status_label.setText(f"✓ Viewed {member_name}")
            self.status_label.setStyleSheet("color: #27ae60; font-weight: bold; padding: 2px; font-size: 11px;")
            
        except Exception as e:
            logger.error(f"Failed to load member: {str(e)}", exc_info=True)
            self.status_label.setText(f"✗ Failed to load member: {str(e)}")
            self.status_label.setStyleSheet("color: #e74c3c; font-weight: bold; padding: 2px; font-size: 11px;")
            QMessageBox.critical(self, "View Error", f"Failed to load member:\n{str(e)}")
    
    
    def add_member(self):
        """Add a new member from a local text file"""
        if not self.current_dataset or not self.ftp_manager:
            QMessageBox.warning(self, "Not Ready", "Please select a PDS first.")
            return
        
        # Ask for member name
        member_name, ok = QInputDialog.getText(
            self,
            "Add Member",
            "Enter member name (max 8 characters):",
            QLineEdit.EchoMode.Normal
        )
        
        if not ok or not member_name:
            return
        
        # Validate member name (must be 1-8 chars, alphanumeric + national chars)
        member_name = member_name.strip().upper()
        if len(member_name) > 8:
            QMessageBox.warning(self, "Invalid Name", "Member name must be 8 characters or less.")
            return
        
        if not member_name.replace('@', '').replace('#', '').replace('$', '').isalnum():
            QMessageBox.warning(self, "Invalid Name", "Member name can only contain letters, numbers, @, #, $")
            return
        
        # Open file dialog to select source file
        filename, _ = QFileDialog.getOpenFileName(
            self,
            "Select Text File to Upload",
            "",
            "Text Files (*.txt *.jcl *.cob *.cbl *.asm *.pli *.rexx *.clist);;All Files (*.*)"
        )
        
        if not filename:
            return
        
        try:
            self.status_label.setText(f"Uploading {member_name}...")
            
            # Build the member path
            member_path = f"{self.current_dataset}({member_name})"
            
            # Upload using text mode
            success, message = self.ftp_manager.upload_file_as_text(filename, member_path)
            
            if success:
                self.status_label.setText(f"✓ Added {member_name}")
                self.status_label.setStyleSheet("color: #27ae60; font-weight: bold; padding: 2px; font-size: 11px;")
                QMessageBox.information(self, "Upload Complete", f"Member {member_name} added successfully.")
                # Reload the member list to get actual dates from mainframe
                self.load_members(self.current_dataset)
            else:
                self.status_label.setText(f"✗ {message}")
                self.status_label.setStyleSheet("color: #e74c3c; font-weight: bold; padding: 2px; font-size: 11px;")
                QMessageBox.critical(self, "Upload Error", message)
                
        except Exception as e:
            logger.error(f"Failed to add member: {str(e)}")
            QMessageBox.critical(self, "Upload Error", f"Failed to add member:\n{str(e)}")
    
    def delete_member(self):
        """Delete the selected member"""
        selected_rows = self.members_table.selectedItems()
        if not selected_rows:
            QMessageBox.warning(self, "No Selection", "Please select a member to delete.")
            return
        
        row = selected_rows[0].row()
        name_item = self.members_table.item(row, 0)
        if not name_item:
            return
            
        member_name = name_item.text()
        
        # Get Dsorg to check if it's a dataset or member
        dsorg_item = self.members_table.item(row, 9)
        dsorg = dsorg_item.text() if dsorg_item else ''
        
        # Get dataset data
        item_data = name_item.data(Qt.ItemDataRole.UserRole)
        
        # Don't allow deleting datasets, only members
        if item_data and item_data.get('is_dataset'):
            QMessageBox.warning(self, "Cannot Delete", "Cannot delete datasets, only PDS members.")
            return
        
        if not member_name:
            return
        
        # Confirm deletion with strong warning
        reply = QMessageBox.warning(
            self,
            "⚠️ Confirm Delete",
            f"Are you sure you want to delete member '{member_name}'?\n\n"
            f"Dataset: {self.current_dataset}\n\n"
            f"⚠️ This action cannot be undone!",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No
        )
        
        if reply != QMessageBox.StandardButton.Yes:
            return
        
        try:
            self.status_label.setText(f"Deleting {member_name}...")
            
            # Build the member path
            member_path = f"{self.current_dataset}({member_name})"
            
            success, message = self.ftp_manager.delete_member(member_path)
            
            if success:
                self.status_label.setText(f"✓ Deleted {member_name}")
                self.status_label.setStyleSheet("color: #27ae60; font-weight: bold; padding: 2px; font-size: 11px;")
                QMessageBox.information(self, "Delete Complete", f"Member {member_name} deleted successfully.")
                # Clear cache and reload the member list
                if self.current_dataset in self.folder_cache:
                    del self.folder_cache[self.current_dataset]
                self.load_members(self.current_dataset)
            else:
                self.status_label.setText(f"✗ {message}")
                self.status_label.setStyleSheet("color: #e74c3c; font-weight: bold; padding: 2px; font-size: 11px;")
                QMessageBox.critical(self, "Delete Error", message)
                
        except Exception as e:
            logger.error(f"Failed to delete member: {str(e)}")
            QMessageBox.critical(self, "Delete Error", f"Failed to delete member:\n{str(e)}")
    
    def load_connections(self):
        """Load all MAINFRAME_FTP connections into connections list"""
        try:
            # Get all connections
            connections = self.conn_manager.repo.get_all_connections()
            ftp_connections = [c for c in connections if c.get('connection_type') == 'MAINFRAME_FTP']
            
            if not ftp_connections:
                self.edit_conn_button.setEnabled(False)
                self.delete_conn_button.setEnabled(False)
                self.status_label.setText("No mainframe connections found. Click 'New' to create one.")
            else:
                self.edit_conn_button.setEnabled(True)
                self.delete_conn_button.setEnabled(True)
            
            # Populate the connections list
            self.populate_connections_list()
            
            logger.info(f"Loaded {len(ftp_connections)} mainframe connections")
            
        except Exception as e:
            logger.error(f"Failed to load connections: {str(e)}")
            QMessageBox.critical(self, "Error", f"Failed to load connections:\n{str(e)}")
    
    def on_connection_list_item_clicked(self, item):
        """Handle click on connection in list - load its dataset"""
        if not item:
            return
        
        # Get connection ID from item data
        connection_id = item.data(Qt.ItemDataRole.UserRole)
        if not connection_id:
            return
        
        # Enable edit/delete buttons
        self.edit_conn_button.setEnabled(True)
        self.delete_conn_button.setEnabled(True)
        
        # Load connection's dataset
        self.load_connection_dataset(connection_id)
    
    def add_connection(self):
        """Add a new mainframe connection"""
        dialog = QDialog(self)
        dialog.setWindowTitle("New Mainframe Connection")
        dialog.setModal(True)
        dialog.resize(450, 200)
        
        layout = QVBoxLayout(dialog)
        
        # Connection form
        form_widget = QWidget()
        form_layout = QVBoxLayout(form_widget)
        
        # Connection Name
        name_layout = QHBoxLayout()
        name_layout.addWidget(QLabel("Connection Name:"))
        name_edit = QLineEdit()
        name_edit.setPlaceholderText("e.g., CKAS CIRF Data")
        name_layout.addWidget(name_edit)
        form_layout.addLayout(name_layout)
        
        # Dataset Path (initial_path)
        path_layout = QHBoxLayout()
        path_layout.addWidget(QLabel("Dataset Path:"))
        path_edit = QLineEdit()
        path_edit.setPlaceholderText("e.g., d03.aa0139.CKAS.cirf.data")
        path_layout.addWidget(path_edit)
        form_layout.addLayout(path_layout)
        
        layout.addWidget(form_widget)
        
        # Buttons with royal blue theme
        button_box = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        button_box.button(QDialogButtonBox.StandardButton.Ok).setStyleSheet("""
            QPushButton {
                background-color: #2c5f8d;
                color: white;
                padding: 6px 20px;
                border-radius: 4px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #1e4a6b;
            }
        """)
        button_box.accepted.connect(dialog.accept)
        button_box.rejected.connect(dialog.reject)
        layout.addWidget(button_box)
        
        if dialog.exec() == QDialog.DialogCode.Accepted:
            try:
                from suiteview.core.credential_manager import CredentialManager
                cred_manager = CredentialManager()
                
                # Use global credentials from connection_settings
                encrypted_username = cred_manager.encrypt(self.connection_settings['username'])
                encrypted_password = cred_manager.encrypt(self.connection_settings['password'])
                
                # Build connection string with dataset path
                conn_string = f"port={self.connection_settings['port']};initial_path={path_edit.text()}"
                
                # Add connection using repository's create_connection method
                self.conn_manager.repo.create_connection(
                    connection_name=name_edit.text() or "Mainframe Dataset",
                    connection_type='MAINFRAME_FTP',
                    server_name=self.connection_settings['host'],
                    database_name='',
                    auth_type='password',
                    encrypted_username=encrypted_username,
                    encrypted_password=encrypted_password,
                    connection_string=conn_string
                )
                
                logger.info(f"Created new mainframe connection: {name_edit.text()}")
                QMessageBox.information(self, "Success", "Mainframe connection created successfully!")
                
                # Reload connections
                self.load_connections()
                
            except Exception as e:
                logger.error(f"Failed to create connection: {str(e)}")
                QMessageBox.critical(self, "Error", f"Failed to create connection:\n{str(e)}")
    
    def edit_connection(self):
        """Edit the selected mainframe connection"""
        # Get selected connection from list
        selected_items = self.connections_list.selectedItems()
        if not selected_items:
            QMessageBox.warning(self, "No Selection", "Please select a connection to edit.")
            return
        
        conn_id = selected_items[0].data(Qt.ItemDataRole.UserRole)
        if not conn_id:
            return
        
        try:
            connection = self.conn_manager.repo.get_connection(conn_id)
            if not connection:
                return
            
            # Parse existing connection string for dataset path
            conn_string = connection.get('connection_string', '')
            ftp_params = {}
            for param in conn_string.split(';'):
                if '=' in param:
                    key, value = param.split('=', 1)
                    ftp_params[key] = value
            
            # Show edit dialog
            dialog = QDialog(self)
            dialog.setWindowTitle("Edit Mainframe Connection")
            dialog.setModal(True)
            dialog.resize(450, 200)
            
            layout = QVBoxLayout(dialog)
            
            # Connection form
            form_widget = QWidget()
            form_layout = QVBoxLayout(form_widget)
            
            # Connection Name
            name_layout = QHBoxLayout()
            name_layout.addWidget(QLabel("Connection Name:"))
            name_edit = QLineEdit(connection.get('connection_name', ''))
            name_layout.addWidget(name_edit)
            form_layout.addLayout(name_layout)
            
            # Dataset Path
            path_layout = QHBoxLayout()
            path_layout.addWidget(QLabel("Dataset Path:"))
            path_edit = QLineEdit(ftp_params.get('initial_path', ''))
            path_layout.addWidget(path_edit)
            form_layout.addLayout(path_layout)
            
            layout.addWidget(form_widget)
            
            # Buttons with royal blue theme
            button_box = QDialogButtonBox(
                QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
            )
            button_box.button(QDialogButtonBox.StandardButton.Ok).setStyleSheet("""
                QPushButton {
                    background-color: #2c5f8d;
                    color: white;
                    padding: 6px 20px;
                    border-radius: 4px;
                    font-weight: bold;
                }
                QPushButton:hover {
                    background-color: #1e4a6b;
                }
            """)
            button_box.accepted.connect(dialog.accept)
            button_box.rejected.connect(dialog.reject)
            layout.addWidget(button_box)
            
            if dialog.exec() == QDialog.DialogCode.Accepted:
                from suiteview.core.credential_manager import CredentialManager
                cred_manager = CredentialManager()
                
                # Use global credentials from connection_settings
                encrypted_username = cred_manager.encrypt(self.connection_settings['username'])
                encrypted_password = cred_manager.encrypt(self.connection_settings['password'])
                
                # Build connection string with new dataset path
                conn_string = f"port={self.connection_settings['port']};initial_path={path_edit.text()}"
                
                # Update connection
                self.conn_manager.repo.update_connection(
                    conn_id,
                    connection_name=name_edit.text(),
                    server_name=self.connection_settings['host'],
                    encrypted_username=encrypted_username,
                    encrypted_password=encrypted_password,
                    connection_string=conn_string
                )
                
                logger.info(f"Updated mainframe connection: {name_edit.text()}")
                QMessageBox.information(self, "Success", "Connection updated successfully!")
                
                # Reload connections
                self.load_connections()
                
        except Exception as e:
            logger.error(f"Failed to edit connection: {str(e)}")
            QMessageBox.critical(self, "Error", f"Failed to edit connection:\n{str(e)}")
    
    def delete_connection(self):
        """Delete the selected mainframe connection"""
        # Get selected connection from list
        selected_items = self.connections_list.selectedItems()
        if not selected_items:
            QMessageBox.warning(self, "No Selection", "Please select a connection to delete.")
            return
        
        conn_id = selected_items[0].data(Qt.ItemDataRole.UserRole)
        conn_name = selected_items[0].text().replace("🖥️ ", "")  # Remove icon
        
        if not conn_id:
            return
        
        reply = QMessageBox.question(
            self,
            "Confirm Delete",
            f"Are you sure you want to delete the connection '{conn_name}'?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        
        if reply == QMessageBox.StandardButton.Yes:
            try:
                self.conn_manager.repo.delete_connection(conn_id)
                logger.info(f"Deleted mainframe connection: {conn_name}")
                QMessageBox.information(self, "Success", "Connection deleted successfully!")
                
                # Disconnect if this was the active connection
                if self.current_connection_id == conn_id:
                    self.ftp_manager = None
                    self.current_connection_id = None
                    # Clear navigation
                    self.navigation_history = []
                    self.current_history_index = -1
                    self.update_breadcrumb("")
                    self.update_navigation_buttons()
                
                # Reload connections
                self.load_connections()
                
            except Exception as e:
                logger.error(f"Failed to delete connection: {str(e)}")
                QMessageBox.critical(self, "Error", f"Failed to delete connection:\n{str(e)}")
    
    def load_default_settings(self):
        """Load default settings - credentials from MAINFRAME_USER, paths from MAINFRAME_FTP"""
        try:
            from suiteview.core.credential_manager import CredentialManager
            cred_manager = CredentialManager()
            
            # First, try to load credentials from MAINFRAME_USER connection (shared with Terminal)
            connections = self.conn_manager.repo.get_all_connections()
            user_conn = None
            for conn in connections:
                if conn.get('connection_name') == 'MAINFRAME_USER':
                    user_conn = conn
                    break
            
            if user_conn:
                # Decrypt username
                encrypted_username = user_conn.get('encrypted_username')
                if encrypted_username:
                    try:
                        self.connection_settings['username'] = cred_manager.decrypt(encrypted_username)
                        logger.info(f"Loaded username from MAINFRAME_USER: {self.connection_settings['username']}")
                    except Exception as e:
                        logger.error(f"Failed to decrypt username: {e}")
                
                # Decrypt password
                encrypted_password = user_conn.get('encrypted_password')
                if encrypted_password:
                    try:
                        self.connection_settings['password'] = cred_manager.decrypt(encrypted_password)
                        logger.info("Loaded password from MAINFRAME_USER")
                    except Exception as e:
                        logger.error(f"Failed to decrypt password: {e}")
            else:
                logger.warning("No MAINFRAME_USER connection found - credentials may not be set")
            
            # Then load host/port/path from first MAINFRAME_FTP connection
            ftp_connections = [c for c in connections if c.get('connection_type') == 'MAINFRAME_FTP']
            
            if ftp_connections:
                # Use connection_id, not 'id'
                conn_id = ftp_connections[0].get('connection_id')
                connection = self.conn_manager.repo.get_connection(conn_id)
                
                if connection:
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
                    logger.info(f"Loaded FTP settings from MAINFRAME_FTP connection")
            else:
                logger.warning("No MAINFRAME_FTP connections found - using defaults")
                    
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
