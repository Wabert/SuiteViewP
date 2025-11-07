"""
Enhanced File Explorer using QFileSystemModel
Based on PyQt-File-Explorer by proaddy (MIT License)
Adapted for SuiteView with PyQt6
"""

import os
import shutil
import subprocess
from pathlib import Path
from PyQt6.QtWidgets import (QMainWindow, QTreeView, QVBoxLayout, 
                              QHBoxLayout, QWidget, QHeaderView, QToolBar, QMessageBox, 
                              QInputDialog, QTextEdit, QPushButton, QSplitter, QLabel, QMenu)
from PyQt6.QtGui import QIcon, QAction, QFileSystemModel, QStandardItemModel, QStandardItem
from PyQt6.QtCore import Qt, QDir, QModelIndex

import logging

logger = logging.getLogger(__name__)


class FileExplorerV2(QWidget):
    """
    Enhanced File Explorer using QFileSystemModel
    Features:
    - Tree view of file system
    - Cut, Copy, Paste operations
    - Rename files/folders
    - Open in Windows Explorer
    - File preview pane
    """
    
    def __init__(self):
        super().__init__()
        self.current_file_path = None
        self.current_file_content = None
        
        # Clipboard for cut/copy operations
        self.clipboard = {"path": None, "operation": None}
        
        self.init_ui()
        
    def init_ui(self):
        """Initialize the UI"""
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)
        
        # Create toolbar with operations
        toolbar = self.create_toolbar()
        main_layout.addWidget(toolbar)
        
        # Main splitter: Tree View | File Preview
        splitter = QSplitter(Qt.Orientation.Horizontal)
        
        # LEFT PANEL - File Tree View
        left_widget = self.create_tree_panel()
        splitter.addWidget(left_widget)
        
        # RIGHT PANEL - File Preview
        right_widget = self.create_preview_panel()
        splitter.addWidget(right_widget)
        
        # Set initial sizes
        splitter.setSizes([600, 400])
        
        main_layout.addWidget(splitter)
        
    def create_toolbar(self) -> QToolBar:
        """Create toolbar with file operations"""
        toolbar = QToolBar("File Operations")
        toolbar.setMovable(False)
        
        # Cut action
        cut_action = QAction("✂️ Cut", self)
        cut_action.setShortcut("Ctrl+X")
        cut_action.triggered.connect(self.cut_file)
        toolbar.addAction(cut_action)
        
        # Copy action
        copy_action = QAction("📋 Copy", self)
        copy_action.setShortcut("Ctrl+C")
        copy_action.triggered.connect(self.copy_file)
        toolbar.addAction(copy_action)
        
        # Paste action
        paste_action = QAction("📌 Paste", self)
        paste_action.setShortcut("Ctrl+V")
        paste_action.triggered.connect(self.paste_file)
        toolbar.addAction(paste_action)
        
        toolbar.addSeparator()
        
        # Rename action
        rename_action = QAction("✏️ Rename", self)
        rename_action.setShortcut("F2")
        rename_action.triggered.connect(self.rename_file_or_folder)
        toolbar.addAction(rename_action)
        
        # Open in Explorer action
        open_explorer_action = QAction("📂 Open in Explorer", self)
        open_explorer_action.triggered.connect(self.open_in_explorer)
        toolbar.addAction(open_explorer_action)
        
        toolbar.addSeparator()
        
        # Refresh action
        refresh_action = QAction("🔄 Refresh", self)
        refresh_action.setShortcut("F5")
        refresh_action.triggered.connect(self.refresh_view)
        toolbar.addAction(refresh_action)
        
        return toolbar
        
    def create_tree_panel(self) -> QWidget:
        """Create the file tree view panel"""
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(0, 0, 0, 0)
        
        # Header - normal size, no color
        header = QLabel("File System")
        header.setStyleSheet("padding: 8px; font-weight: normal;")
        layout.addWidget(header)
        
        # Tree View and File System Model
        self.tree_view = QTreeView()
        self.model = QFileSystemModel()
        
        # Show hidden files and folders
        self.model.setFilter(QDir.Filter.AllEntries | QDir.Filter.NoDotAndDotDot | QDir.Filter.Hidden)
        
        # Set root to show all drives (empty string = root on Windows)
        self.model.setRootPath("")
        
        self.tree_view.setModel(self.model)
        # Set root index to show drives AND user folders at top level
        # On Windows, show root to include C:\, D:\, etc.
        root_path = ""
        if os.name == 'nt':
            # Show "My Computer" root which includes all drives
            root_path = ""
        self.tree_view.setRootIndex(self.model.index(root_path))
        self.tree_view.setIndentation(20)
        self.tree_view.setAnimated(True)
        
        # Customize header - make columns resizable
        header_view = self.tree_view.header()
        # Make all columns interactive (user can resize)
        header_view.setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        header_view.setStretchLastSection(False)  # Don't auto-stretch last column
        header_view.setVisible(True)
        
        # Set initial column widths (user can adjust)
        self.tree_view.setColumnWidth(0, 300)  # Name
        self.tree_view.setColumnWidth(1, 100)  # Size
        self.tree_view.setColumnWidth(2, 150)  # Type
        self.tree_view.setColumnWidth(3, 150)  # Date Modified
        
        # Connect selection signal
        self.tree_view.clicked.connect(self.on_item_selected)
        
        # Enable context menu
        self.tree_view.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.tree_view.customContextMenuRequested.connect(self.show_context_menu)
        
        # Add OneDrive shortcuts at top level
        self.add_onedrive_shortcuts()
        
        layout.addWidget(self.tree_view)
        
        return widget
        
    def add_onedrive_shortcuts(self):
        """Expand tree to show OneDrive prominently at top level"""
        import os
        from pathlib import Path
        
        if os.name != 'nt':
            return  # Only for Windows
        
        # Get OneDrive paths
        onedrive_paths = []
        
        # Check environment variables
        for env_var in ['OneDrive', 'OneDriveCommercial', 'OneDriveConsumer']:
            path = os.environ.get(env_var)
            if path and os.path.exists(path):
                onedrive_paths.append(Path(path))
        
        # Also check common locations
        home = Path.home()
        possible_onedrive = [
            home / "OneDrive",
            home / "OneDrive - American National Insurance Company",
        ]
        
        for od_path in possible_onedrive:
            if od_path.exists() and od_path not in onedrive_paths:
                onedrive_paths.append(od_path)
        
        if not onedrive_paths:
            return
        
        # Strategy: Expand C:\ drive and user profile to show OneDrive
        # This makes OneDrive visible without scrolling
        
        # 1. Expand C:\ drive
        c_drive = "C:\\"
        c_index = self.model.index(c_drive)
        if c_index.isValid():
            self.tree_view.expand(c_index)
            
            # 2. Expand C:\Users
            users_folder = "C:\\Users"
            users_index = self.model.index(users_folder)
            if users_index.isValid():
                self.tree_view.expand(users_index)
                
                # 3. Expand the current user's folder
                user_folder = str(Path.home())
                user_index = self.model.index(user_folder)
                if user_index.isValid():
                    self.tree_view.expand(user_index)
                    
                    # 4. Make first OneDrive folder visible
                    onedrive_index = self.model.index(str(onedrive_paths[0]))
                    if onedrive_index.isValid():
                        self.tree_view.scrollTo(onedrive_index)
                        # Optionally select it to highlight
                        # self.tree_view.setCurrentIndex(onedrive_index)
        
    def create_preview_panel(self) -> QWidget:
        """Create the file preview panel"""
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(0, 0, 0, 0)
        
        # Header - normal size, no color
        header = QLabel("File Preview")
        header.setStyleSheet("padding: 8px; font-weight: normal;")
        layout.addWidget(header)
        
        # Preview text area
        self.file_preview = QTextEdit()
        self.file_preview.setReadOnly(True)
        self.file_preview.setPlaceholderText("Select a text file to preview...")
        layout.addWidget(self.file_preview)
        
        # Action buttons
        button_layout = QHBoxLayout()
        
        self.upload_button = QPushButton("📤 Upload to Mainframe")
        self.upload_button.setObjectName("gold_button")
        self.upload_button.setEnabled(False)
        self.upload_button.clicked.connect(self.show_upload_menu)
        button_layout.addWidget(self.upload_button)
        
        button_layout.addStretch()
        
        layout.addLayout(button_layout)
        
        return widget
        
    def on_item_selected(self, index):
        """Handle item selection in tree view"""
        path = self.model.filePath(index)
        
        # If it's a file, try to preview it
        if os.path.isfile(path):
            self.preview_file(path)
        else:
            self.file_preview.clear()
            self.file_preview.setPlaceholderText(f"Folder: {path}")
            self.upload_button.setEnabled(False)
            
    def preview_file(self, file_path: str):
        """Preview text file contents"""
        self.current_file_path = file_path
        
        try:
            # Only preview text files
            if file_path.lower().endswith(('.txt', '.log', '.csv', '.json', '.xml', '.py', '.sql')):
                with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                    content = f.read(10000)  # First 10K chars
                    self.current_file_content = content
                    self.file_preview.setPlainText(content)
                    self.upload_button.setEnabled(True)
            else:
                self.file_preview.setPlainText(f"File type not supported for preview:\n{os.path.basename(file_path)}")
                self.upload_button.setEnabled(False)
                
        except Exception as e:
            logger.error(f"Error previewing file: {e}")
            self.file_preview.setPlainText(f"Cannot preview file:\n{str(e)}")
            self.upload_button.setEnabled(False)
            
    def show_context_menu(self, position):
        """Show context menu for file operations"""
        index = self.tree_view.indexAt(position)
        if not index.isValid():
            return
            
        menu = QMenu()
        
        path = self.model.filePath(index)
        is_dir = os.path.isdir(path)
        
        # Cut
        cut_action = menu.addAction("✂️ Cut")
        cut_action.triggered.connect(self.cut_file)
        
        # Copy
        copy_action = menu.addAction("📋 Copy")
        copy_action.triggered.connect(self.copy_file)
        
        # Paste (only in directories)
        if is_dir:
            paste_action = menu.addAction("📌 Paste")
            paste_action.triggered.connect(self.paste_file)
            paste_action.setEnabled(self.clipboard["path"] is not None)
        
        menu.addSeparator()
        
        # Rename
        rename_action = menu.addAction("✏️ Rename")
        rename_action.triggered.connect(self.rename_file_or_folder)
        
        # Delete
        delete_action = menu.addAction("🗑️ Delete")
        delete_action.triggered.connect(self.delete_item)
        
        menu.addSeparator()
        
        # Open in Explorer
        explorer_action = menu.addAction("📂 Open in Explorer")
        explorer_action.triggered.connect(self.open_in_explorer)
        
        # Properties
        props_action = menu.addAction("ℹ️ Properties")
        props_action.triggered.connect(self.show_properties)
        
        menu.exec(self.tree_view.viewport().mapToGlobal(position))
        
    def get_selected_path(self) -> str:
        """Get path of currently selected item"""
        index = self.tree_view.currentIndex()
        if index.isValid():
            return self.model.filePath(index)
        return None
        
    def cut_file(self):
        """Mark file/folder for cutting"""
        path = self.get_selected_path()
        if path:
            self.clipboard = {"path": path, "operation": "cut"}
            QMessageBox.information(self, "Cut", f"Cut: {os.path.basename(path)}")
            
    def copy_file(self):
        """Mark file/folder for copying"""
        path = self.get_selected_path()
        if path:
            self.clipboard = {"path": path, "operation": "copy"}
            QMessageBox.information(self, "Copy", f"Copied: {os.path.basename(path)}")
            
    def paste_file(self):
        """Paste cut/copied file to selected directory"""
        target_path = self.get_selected_path()
        
        if not target_path or not os.path.isdir(target_path):
            QMessageBox.warning(self, "Paste", "Please select a folder to paste into.")
            return
            
        src_path = self.clipboard.get("path")
        operation = self.clipboard.get("operation")
        
        if not src_path or not operation:
            QMessageBox.warning(self, "Paste", "Nothing to paste.")
            return
            
        dest_path = os.path.join(target_path, os.path.basename(src_path))
        
        try:
            if operation == "copy":
                if os.path.isdir(src_path):
                    shutil.copytree(src_path, dest_path)
                else:
                    shutil.copy2(src_path, dest_path)
                QMessageBox.information(self, "Paste", f"Copied to: {dest_path}")
            elif operation == "cut":
                shutil.move(src_path, dest_path)
                QMessageBox.information(self, "Paste", f"Moved to: {dest_path}")
                
            # Clear clipboard
            self.clipboard = {"path": None, "operation": None}
            
            # Refresh view
            self.refresh_view()
            
        except Exception as e:
            QMessageBox.critical(self, "Paste Error", str(e))
            
    def rename_file_or_folder(self):
        """Rename selected file or folder"""
        path = self.get_selected_path()
        if not path:
            return
            
        base_dir = os.path.dirname(path)
        current_name = os.path.basename(path)
        
        # Prompt for new name
        new_name, ok = QInputDialog.getText(
            self, 
            "Rename", 
            "Enter new name:", 
            text=current_name
        )
        
        if ok and new_name.strip():
            new_path = os.path.join(base_dir, new_name.strip())
            try:
                os.rename(path, new_path)
                logger.info(f"Renamed to: {new_path}")
                self.refresh_view()
            except Exception as e:
                QMessageBox.critical(self, "Rename Error", str(e))
                
    def delete_item(self):
        """Delete selected file or folder"""
        path = self.get_selected_path()
        if not path:
            return
            
        # Confirm deletion
        msg = f"Are you sure you want to delete:\n{path}"
        reply = QMessageBox.question(
            self,
            "Confirm Delete",
            msg,
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        
        if reply == QMessageBox.StandardButton.Yes:
            try:
                if os.path.isdir(path):
                    shutil.rmtree(path)
                else:
                    os.remove(path)
                logger.info(f"Deleted: {path}")
                self.refresh_view()
            except Exception as e:
                QMessageBox.critical(self, "Delete Error", str(e))
                
    def open_in_explorer(self):
        """Open selected path in Windows Explorer"""
        path = self.get_selected_path()
        if not path:
            return
            
        if os.path.exists(path):
            if os.name == 'nt':  # Windows
                # Use /select to highlight the file/folder
                subprocess.run(['explorer', '/select,', path])
            else:  # Unix/Linux/Mac
                # Open parent directory
                parent = os.path.dirname(path)
                subprocess.run(['xdg-open', parent])
        else:
            QMessageBox.warning(self, "Error", "Path does not exist")
            
    def show_properties(self):
        """Show properties of selected item"""
        path = self.get_selected_path()
        if not path:
            return
            
        try:
            stat_info = os.stat(path)
            size = stat_info.st_size
            
            # Format size
            for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
                if size < 1024.0:
                    size_str = f"{size:.1f} {unit}"
                    break
                size /= 1024.0
            else:
                size_str = f"{size:.1f} PB"
                
            import datetime
            mtime = datetime.datetime.fromtimestamp(stat_info.st_mtime)
            
            info = f"""Path: {path}
Type: {'Directory' if os.path.isdir(path) else 'File'}
Size: {size_str}
Modified: {mtime.strftime('%Y-%m-%d %H:%M:%S')}
"""
            QMessageBox.information(self, "Properties", info)
            
        except Exception as e:
            QMessageBox.warning(self, "Properties", f"Error: {e}")
            
    def refresh_view(self):
        """Refresh the file system view"""
        # Get current path
        index = self.tree_view.currentIndex()
        if index.isValid():
            path = self.model.filePath(index)
            # Re-set the root to force refresh
            self.model.setRootPath("")
            # Navigate back
            new_index = self.model.index(path)
            self.tree_view.setCurrentIndex(new_index)
            
    def show_upload_menu(self):
        """Show upload menu - placeholder for mainframe integration"""
        if not self.current_file_path:
            return
            
        QMessageBox.information(
            self,
            "Upload",
            f"Upload functionality will upload:\n{self.current_file_path}\n\n(Implementation in progress)"
        )
