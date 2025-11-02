"""File Explorer Screen - Browse and upload local files to mainframe datasets"""

import logging
import os
from pathlib import Path
from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel, QSplitter,
                              QTreeWidget, QTreeWidgetItem, QTableWidget, QTableWidgetItem,
                              QTextEdit, QPushButton, QLineEdit, QHeaderView, QMenu,
                              QMessageBox, QFileDialog)
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QFont, QAction

from suiteview.core.connection_manager import get_connection_manager
from suiteview.core.credential_manager import CredentialManager
from suiteview.core.ftp_manager import MainframeFTPManager

logger = logging.getLogger(__name__)


class FileExplorerScreen(QWidget):
    """File Explorer screen for browsing local files and uploading to mainframe"""

    def __init__(self):
        super().__init__()
        self.conn_manager = get_connection_manager()
        self.cred_manager = CredentialManager()
        self.current_path = str(Path.home())  # Start at user's home directory
        self.current_file_path = None
        self.current_file_content = None

        self.init_ui()
        self.load_folder_tree()

    def init_ui(self):
        """Initialize the UI with three-panel layout"""
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # Top bar with navigation
        nav_bar = self.create_navigation_bar()
        main_layout.addWidget(nav_bar)

        # Three-panel horizontal splitter
        main_splitter = QSplitter(Qt.Orientation.Horizontal)

        # LEFT PANEL - Folder Tree
        left_widget = QWidget()
        left_layout = QVBoxLayout(left_widget)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.setSpacing(0)

        # Header
        folder_header = QLabel("Folder Tree")
        folder_header.setObjectName("panel_header")
        folder_header.setStyleSheet("background-color: #2c5f8d; color: white; padding: 8px; font-weight: bold;")
        left_layout.addWidget(folder_header)

        # Folder tree widget
        self.folder_tree = QTreeWidget()
        self.folder_tree.setHeaderHidden(True)
        self.folder_tree.itemClicked.connect(self.on_folder_selected)
        self.folder_tree.itemExpanded.connect(self.on_tree_item_expanded)
        left_layout.addWidget(self.folder_tree)

        main_splitter.addWidget(left_widget)

        # MIDDLE PANEL - File List
        middle_widget = QWidget()
        middle_layout = QVBoxLayout(middle_widget)
        middle_layout.setContentsMargins(0, 0, 0, 0)
        middle_layout.setSpacing(0)

        # Header
        content_header = QLabel("File List")
        content_header.setObjectName("panel_header")
        content_header.setStyleSheet("background-color: #2c5f8d; color: white; padding: 8px; font-weight: bold;")
        middle_layout.addWidget(content_header)

        # File table
        self.files_table = QTableWidget()
        self.files_table.setColumnCount(3)
        self.files_table.setHorizontalHeaderLabels(["Name", "Size", "Modified"])
        self.files_table.verticalHeader().setVisible(False)
        self.files_table.setShowGrid(False)
        self.files_table.setAlternatingRowColors(True)
        self.files_table.horizontalHeader().setDefaultAlignment(Qt.AlignmentFlag.AlignLeft)
        self.files_table.horizontalHeader().setStyleSheet("""
            QHeaderView::section {
                background-color: #f0f0f0;
                padding: 4px;
                border: none;
                border-bottom: 1px solid #d0d0d0;
                font-weight: normal;
                font-size: 11px;
            }
        """)
        self.files_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.files_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        self.files_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        self.files_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.files_table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        # Use itemClicked for left-click navigation
        self.files_table.itemClicked.connect(self.on_file_clicked)
        # Install event filter to capture mouse events
        self.files_table.viewport().installEventFilter(self)
        middle_layout.addWidget(self.files_table)

        main_splitter.addWidget(middle_widget)

        # RIGHT PANEL - File Preview
        right_widget = QWidget()
        right_layout = QVBoxLayout(right_widget)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.setSpacing(0)

        # Header
        preview_header = QLabel("File Preview")
        preview_header.setObjectName("panel_header")
        preview_header.setStyleSheet("background-color: #2c5f8d; color: white; padding: 8px; font-weight: bold;")
        right_layout.addWidget(preview_header)

        # File preview text area
        self.file_preview = QTextEdit()
        self.file_preview.setReadOnly(True)
        self.file_preview.setFont(QFont("Courier New", 10))
        self.file_preview.setLineWrapMode(QTextEdit.LineWrapMode.NoWrap)
        self.file_preview.setPlaceholderText("Select a file to preview its contents...")
        right_layout.addWidget(self.file_preview)

        # Button bar
        button_bar = QWidget()
        button_layout = QHBoxLayout(button_bar)
        button_layout.setContentsMargins(8, 4, 8, 4)

        self.upload_button = QPushButton("📤 Upload to Mainframe")
        self.upload_button.setObjectName("gold_button")
        self.upload_button.setEnabled(False)
        self.upload_button.clicked.connect(self.show_upload_menu)
        button_layout.addWidget(self.upload_button)

        button_layout.addStretch()

        right_layout.addWidget(button_bar)

        main_splitter.addWidget(right_widget)

        # Set initial splitter sizes
        main_splitter.setSizes([250, 400, 550])

        main_layout.addWidget(main_splitter, 1)  # stretch=1 to fill remaining space

    def create_navigation_bar(self) -> QWidget:
        """Create navigation bar with current path display"""
        nav_bar = QWidget()
        nav_bar.setStyleSheet("background-color: #f8f8f8; border-bottom: 1px solid #d0d0d0;")
        nav_bar.setFixedHeight(50)
        nav_layout = QHBoxLayout(nav_bar)
        nav_layout.setContentsMargins(10, 8, 10, 8)
        nav_layout.setSpacing(8)

        # Path label
        path_label = QLabel("Current Path:")
        path_label.setStyleSheet("font-weight: bold; font-size: 11px;")
        nav_layout.addWidget(path_label)

        # Path display (read-only)
        self.path_display = QLineEdit()
        self.path_display.setFixedHeight(32)
        self.path_display.setText(self.current_path)
        self.path_display.setReadOnly(True)
        self.path_display.setStyleSheet("background-color: #ffffff; border: 1px solid #d0d0d0;")
        nav_layout.addWidget(self.path_display)

        return nav_bar

    def load_folder_tree(self):
        """Load folder tree starting from user's home directory"""
        self.folder_tree.clear()

        # Add drives (Windows) or root (Unix)
        if os.name == 'nt':  # Windows
            # Add common locations first
            # This PC
            this_pc = QTreeWidgetItem()
            this_pc.setText(0, "💻 This PC")
            this_pc.setData(0, Qt.ItemDataRole.UserRole, "")
            self.folder_tree.addTopLevelItem(this_pc)
            
            # Add drives under This PC
            for drive in 'CDEFGHIJKLMNOPQRSTUVWXYZ':
                drive_path = f"{drive}:\\"
                if os.path.exists(drive_path):
                    drive_item = QTreeWidgetItem()
                    drive_item.setText(0, f"💾 {drive}:\\")
                    drive_item.setData(0, Qt.ItemDataRole.UserRole, drive_path)
                    this_pc.addChild(drive_item)
                    # Add dummy child to make it expandable
                    dummy = QTreeWidgetItem()
                    drive_item.addChild(dummy)
            
            # Expand This PC by default
            this_pc.setExpanded(True)
            
            # Add Quick Access section with common folders
            quick_access = QTreeWidgetItem()
            quick_access.setText(0, "⭐ Quick Access")
            quick_access.setData(0, Qt.ItemDataRole.UserRole, "")
            self.folder_tree.addTopLevelItem(quick_access)
            
            # Add common user folders
            home = Path.home()
            
            # Try to find OneDrive folders
            onedrive_paths = []
            # Common OneDrive locations
            possible_onedrive = [
                home / "OneDrive",
                home / "OneDrive - American National Insurance Company",
            ]
            # Also check for OneDrive in environment variables
            onedrive_env = os.environ.get('OneDrive')
            if onedrive_env:
                possible_onedrive.insert(0, Path(onedrive_env))
            
            for od_path in possible_onedrive:
                if od_path.exists() and od_path not in onedrive_paths:
                    onedrive_paths.append(od_path)
            
            common_folders = [
                ("🏠 Home", str(home)),
            ]
            
            # Add OneDrive folders
            for od_path in onedrive_paths:
                common_folders.append(("☁️ OneDrive", str(od_path)))
            
            # Add other common folders
            common_folders.extend([
                ("📄 Documents", str(home / "Documents")),
                ("⬇️ Downloads", str(home / "Downloads")),
                ("🖼️ Pictures", str(home / "Pictures")),
                ("🎵 Music", str(home / "Music")),
                ("🎬 Videos", str(home / "Videos")),
                ("🖥️ Desktop", str(home / "Desktop")),
            ])
            
            for name, path in common_folders:
                if os.path.exists(path):
                    folder_item = QTreeWidgetItem()
                    folder_item.setText(0, name)
                    folder_item.setData(0, Qt.ItemDataRole.UserRole, path)
                    quick_access.addChild(folder_item)
                    # Add dummy child to make it expandable
                    dummy = QTreeWidgetItem()
                    folder_item.addChild(dummy)
            
            # Expand Quick Access by default
            quick_access.setExpanded(True)
            
        else:  # Unix/Linux/Mac
            root_item = QTreeWidgetItem()
            root_item.setText(0, "📁 /")
            root_item.setData(0, Qt.ItemDataRole.UserRole, "/")
            self.folder_tree.addTopLevelItem(root_item)
            dummy = QTreeWidgetItem()
            root_item.addChild(dummy)

    def on_tree_item_expanded(self, item: QTreeWidgetItem):
        """Load subfolders when tree item is expanded"""
        # Skip if this is a category item (no path)
        folder_path = item.data(0, Qt.ItemDataRole.UserRole)
        if not folder_path:
            return
            
        # Remove dummy child if it exists
        if item.childCount() == 1 and not item.child(0).text(0):
            item.takeChild(0)
            
            # Load subfolders
            try:
                for entry in os.scandir(folder_path):
                    if entry.is_dir():
                        try:
                            # Skip hidden and system folders
                            if entry.name.startswith('.') or entry.name.startswith('$'):
                                continue
                                
                            child_item = QTreeWidgetItem()
                            child_item.setText(0, f"📁 {entry.name}")
                            child_item.setData(0, Qt.ItemDataRole.UserRole, entry.path)
                            item.addChild(child_item)
                            
                            # Add dummy child to make it expandable
                            dummy = QTreeWidgetItem()
                            child_item.addChild(dummy)
                        except (PermissionError, OSError):
                            # Skip folders we can't access
                            continue
            except PermissionError:
                logger.warning(f"Permission denied: {folder_path}")
                # Show permission error in tree
                error_item = QTreeWidgetItem()
                error_item.setText(0, "⚠️ Permission denied")
                error_item.setForeground(0, self.palette().color(self.palette().ColorRole.PlaceholderText))
                item.addChild(error_item)
            except Exception as e:
                logger.error(f"Error loading folder tree: {e}")

    def on_folder_selected(self, item: QTreeWidgetItem, column: int):
        """Handle folder selection in tree"""
        folder_path = item.data(0, Qt.ItemDataRole.UserRole)
        # Skip if this is a category item (no path) or path is empty
        if folder_path:
            self.navigate_to_folder(folder_path)

    def navigate_to_folder(self, folder_path: str):
        """Navigate to a specific folder"""
        if not folder_path:
            return
            
        if not os.path.exists(folder_path):
            QMessageBox.warning(self, "Invalid Path", f"Folder not found: {folder_path}")
            return
            
        if not os.path.isdir(folder_path):
            return

        self.current_path = folder_path
        self.path_display.setText(folder_path)
        self.load_files()

    def load_files(self):
        """Load files in current folder - only show .txt files and folders"""
        self.files_table.setRowCount(0)

        try:
            entries = list(os.scandir(self.current_path))
            # Filter: only folders and .txt files
            filtered_entries = []
            for entry in entries:
                if entry.is_dir():
                    filtered_entries.append(entry)
                elif entry.is_file() and entry.name.lower().endswith('.txt'):
                    filtered_entries.append(entry)
            
            # Sort: folders first, then files
            filtered_entries.sort(key=lambda e: (not e.is_dir(), e.name.lower()))

            for entry in filtered_entries:
                row = self.files_table.rowCount()
                self.files_table.insertRow(row)

                # Name
                name_item = QTableWidgetItem(entry.name)
                if entry.is_dir():
                    name_item.setText(f"📁 {entry.name}")
                else:
                    name_item.setText(f"📄 {entry.name}")
                name_item.setData(Qt.ItemDataRole.UserRole, entry.path)
                name_item.setData(Qt.ItemDataRole.UserRole + 1, "folder" if entry.is_dir() else "file")
                self.files_table.setItem(row, 0, name_item)

                # Size
                if entry.is_file():
                    size = entry.stat().st_size
                    size_str = self.format_size(size)
                    size_item = QTableWidgetItem(size_str)
                    self.files_table.setItem(row, 1, size_item)

                # Modified
                try:
                    import datetime
                    mtime = datetime.datetime.fromtimestamp(entry.stat().st_mtime)
                    date_item = QTableWidgetItem(mtime.strftime("%Y-%m-%d %H:%M"))
                    self.files_table.setItem(row, 2, date_item)
                except:
                    pass

            # self.status_label.setText(f"Found {len(filtered_entries)} items in {self.current_path}")

        except PermissionError:
            QMessageBox.warning(self, "Permission Denied", f"Cannot access folder: {self.current_path}")
            # self.status_label.setText("Permission denied")
        except Exception as e:
            logger.error(f"Error loading files: {e}")
            QMessageBox.critical(self, "Error", f"Failed to load files:\n{str(e)}")
            # self.status_label.setText(f"Error: {str(e)}")

    def format_size(self, size: int) -> str:
        """Format file size in human-readable format"""
        for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
            if size < 1024.0:
                return f"{size:.1f} {unit}"
            size /= 1024.0
        return f"{size:.1f} PB"

    def eventFilter(self, obj, event):
        """Event filter to capture right-clicks on file list"""
        from PyQt6.QtCore import QEvent
        from PyQt6.QtGui import QMouseEvent
        
        if obj == self.files_table.viewport():
            if event.type() == QEvent.Type.MouseButtonPress:
                mouse_event = event
                if mouse_event.button() == Qt.MouseButton.RightButton:
                    # Right-click: go up one folder
                    self.go_up_one_folder()
                    return True  # Event handled
        
        return super().eventFilter(obj, event)

    def on_file_clicked(self, item):
        """Handle file left-click"""
        row = item.row()
        file_path = self.files_table.item(row, 0).data(Qt.ItemDataRole.UserRole)
        file_type = self.files_table.item(row, 0).data(Qt.ItemDataRole.UserRole + 1)

        if file_type == "folder":
            # Navigate into folder
            self.navigate_to_folder(file_path)
        else:
            # Show file preview
            self.preview_file(file_path)

    def preview_file(self, file_path: str):
        """Preview text file contents - reads entire file"""
        self.current_file_path = file_path
        
        try:
            # Read entire file as text
            with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                content = f.read()  # Read entire file
                self.current_file_content = content
                self.file_preview.setPlainText(content)
                self.upload_button.setEnabled(True)
                
                # file_size = os.path.getsize(file_path)
                # self.status_label.setText(f"Previewing: {os.path.basename(file_path)} ({self.format_size(file_size)})")
                
        except Exception as e:
            logger.error(f"Error previewing file: {e}")
            self.file_preview.setPlainText(f"Cannot preview file:\n{str(e)}")
            self.upload_button.setEnabled(False)

    def go_up_one_folder(self):
        """Navigate up one folder level"""
        parent = str(Path(self.current_path).parent)
        if parent != self.current_path:
            self.navigate_to_folder(parent)

    def show_upload_menu(self):
        """Show upload menu from button"""
        if not self.current_file_path:
            return

        menu = QMenu(self)
        
        # Get mainframe connections
        connections = self.conn_manager.repo.get_all_connections()
        mainframe_connections = [c for c in connections if c.get('connection_type') == 'MAINFRAME_FTP']
        
        if not mainframe_connections:
            no_conn_action = menu.addAction("No mainframe connections")
            no_conn_action.setEnabled(False)
        else:
            for conn in mainframe_connections:
                conn_name = conn.get('name', 'Unknown')
                conn_action = menu.addAction(f"📁 {conn_name}")
                conn_action.triggered.connect(lambda checked, c=conn: self.upload_to_mainframe(c, self.current_file_path))
        
        menu.exec(self.upload_button.mapToGlobal(self.upload_button.rect().bottomLeft()))

    def upload_to_mainframe(self, connection: dict, file_path: str):
        """Upload file to mainframe dataset"""
        # TODO: Show dialog to select specific dataset/member name
        QMessageBox.information(
            self,
            "Upload",
            f"Upload functionality will upload:\n{file_path}\n\nTo connection: {connection.get('name')}\n\n(Implementation in progress)"
        )

