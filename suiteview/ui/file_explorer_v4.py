"""
File Explorer V4 - Multi-Tab Edition
Wraps FileExplorerV3 with tab support, breadcrumbs, and enhanced features
"""

import os
import sys
from pathlib import Path
from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QTabWidget, 
                              QPushButton, QLabel, QFrame, QToolButton, QMenu, QLineEdit)
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QAction

# Import the base FileExplorerV3
from suiteview.ui.file_explorer_v3 import FileExplorerV3

import logging
logger = logging.getLogger(__name__)


class FileExplorerTab(FileExplorerV3):
    """
    Extended FileExplorer with breadcrumb navigation and current path tracking
    """
    
    path_changed = pyqtSignal(str)  # Signal when path changes
    
    def __init__(self, initial_path=None):
        super().__init__()
        
        # Store the starting path (OneDrive if available)
        if initial_path:
            self.starting_path = initial_path
        else:
            onedrive_paths = self.get_onedrive_paths()
            self.starting_path = str(onedrive_paths[0]) if onedrive_paths else str(Path.home())
        
        self.current_directory = self.starting_path
        
        # Add breadcrumb bar at the top
        self.insert_breadcrumb_bar()
        
        # Only navigate if initial path is explicitly provided
        # Otherwise, stay at root level with Quick Links
        if initial_path:
            self.navigate_to_path(initial_path)
        else:
            # Stay at root level - don't navigate anywhere
            self.update_breadcrumb("Quick Links")
    
    def insert_breadcrumb_bar(self):
        """Insert breadcrumb navigation bar above the tree"""
        # Get the main layout
        main_layout = self.layout()
        
        # Create breadcrumb widget with fixed height
        breadcrumb_frame = QFrame()
        breadcrumb_frame.setFrameShape(QFrame.Shape.StyledPanel)
        breadcrumb_frame.setFixedHeight(32)  # Fixed height for breadcrumb bar
        breadcrumb_frame.setStyleSheet("""
            QFrame {
                background-color: #f8f9fa;
                border: 1px solid #dee2e6;
                border-radius: 3px;
            }
        """)
        
        breadcrumb_layout = QHBoxLayout(breadcrumb_frame)
        breadcrumb_layout.setContentsMargins(4, 3, 4, 3)
        breadcrumb_layout.setSpacing(4)
        
        # Home button - go to OneDrive instead of user folder
        self.home_btn = QPushButton("🏠")
        self.home_btn.setToolTip("Go to OneDrive")
        self.home_btn.setFixedSize(24, 24)
        self.home_btn.setStyleSheet("""
            QPushButton {
                background-color: #ffffff;
                border: 1px solid #ced4da;
                border-radius: 2px;
                font-size: 11px;
            }
            QPushButton:hover {
                background-color: #e9ecef;
            }
        """)
        self.home_btn.clicked.connect(self.go_to_onedrive_home)
        breadcrumb_layout.addWidget(self.home_btn)
        
        # Up/Back button
        self.up_btn = QPushButton("⬆️")
        self.up_btn.setToolTip("Go Up One Level")
        self.up_btn.setFixedSize(24, 24)
        self.up_btn.setStyleSheet(self.home_btn.styleSheet())
        self.up_btn.clicked.connect(self.go_up_one_level)
        breadcrumb_layout.addWidget(self.up_btn)
        
        # Path input field (editable - can paste paths)
        self.breadcrumb_input = QLineEdit()
        self.breadcrumb_input.setPlaceholderText("Enter or paste a path...")
        self.breadcrumb_input.setStyleSheet("""
            QLineEdit {
                background-color: #ffffff;
                border: 1px solid #ced4da;
                border-radius: 2px;
                padding: 2px 6px;
                font-family: Segoe UI;
                font-size: 9pt;
            }
            QLineEdit:focus {
                border-color: #0078d4;
            }
        """)
        self.breadcrumb_input.returnPressed.connect(self.navigate_from_breadcrumb_input)
        breadcrumb_layout.addWidget(self.breadcrumb_input, 1)
        
        # Insert at position 1 (after toolbar)
        main_layout.insertWidget(1, breadcrumb_frame)
        
        # Update initial breadcrumb
        self.update_breadcrumb(self.current_directory)
    
    def update_breadcrumb(self, path):
        """Update breadcrumb display"""
        try:
            path_obj = Path(path)
            if path_obj.exists() and path_obj.is_file():
                path_obj = path_obj.parent
            
            # Update the input field with the full path
            self.breadcrumb_input.setText(str(path_obj))
            self.breadcrumb_input.setToolTip(str(path_obj))
            
            self.current_directory = str(path_obj)
            self.path_changed.emit(str(path_obj))
            
        except Exception as e:
            logger.error(f"Failed to update breadcrumb: {e}")
            self.breadcrumb_input.setText(str(path))
    
    def navigate_from_breadcrumb_input(self):
        """Navigate to the path entered in the breadcrumb input field"""
        path_text = self.breadcrumb_input.text().strip()
        if path_text:
            path_obj = Path(path_text)
            if path_obj.exists():
                self.navigate_to_path(str(path_obj))
            else:
                from PyQt6.QtWidgets import QMessageBox
                QMessageBox.warning(self, "Invalid Path", f"Path does not exist:\n{path_text}")
                # Restore the previous path
                self.breadcrumb_input.setText(self.current_directory)
    
    def go_to_onedrive_home(self):
        """Navigate to the starting path (OneDrive folder where app opened)"""
        if hasattr(self, 'starting_path'):
            self.navigate_to_path(self.starting_path)
        else:
            # Fallback: try to find OneDrive
            onedrive_paths = self.get_onedrive_paths()
            if onedrive_paths:
                self.navigate_to_path(str(onedrive_paths[0]))
            else:
                self.navigate_to_path(str(Path.home()))
    
    def navigate_to_path(self, path):
        """Navigate to a specific directory path - loads in details pane (right side)"""
        try:
            path_obj = Path(path)
            if not path_obj.exists():
                return
            
            if path_obj.is_file():
                path_obj = path_obj.parent
            
            # Update breadcrumb
            self.update_breadcrumb(str(path_obj))
            
            # Load in the details pane (right side) instead of tree
            self.load_folder_contents_in_details(path_obj)
            
        except Exception as e:
            logger.error(f"Failed to navigate to {path}: {e}")
    
    def load_directory_contents_at_root(self, dir_path):
        """Load a specific directory at the root of the tree"""
        self.model.clear()
        self.model.setHorizontalHeaderLabels(['Name', 'Size', 'Type', 'Date Modified'])
        
        try:
            dir_path = Path(dir_path)
            items = sorted(dir_path.iterdir(), key=lambda x: (not x.is_dir(), x.name.lower()))
            
            for item in items:
                try:
                    if item.is_dir():
                        row_items = self.create_folder_item(item)
                    else:
                        row_items = self.create_file_item(item)
                    
                    self.model.appendRow(row_items)
                except (PermissionError, OSError):
                    continue
                    
        except (PermissionError, OSError) as e:
            logger.error(f"Cannot access {dir_path}: {e}")
    
    def go_up_one_level(self):
        """Go up one directory level - operates on details view"""
        # Use the current details folder, not the tree selection
        if hasattr(self, 'current_details_folder') and self.current_details_folder:
            current = Path(self.current_details_folder)
        else:
            current = Path(self.current_directory)
        
        if current.parent != current:  # Not at root
            parent_path = str(current.parent)
            # Load parent folder in details view
            self.load_folder_contents_in_details(Path(parent_path))
            # Update breadcrumb
            self.update_breadcrumb(parent_path)
            self.current_directory = parent_path
    
    def on_tree_item_clicked(self, index):
        """Override parent method to update breadcrumb when tree item is clicked"""
        # Call parent implementation to load folder contents
        super().on_tree_item_clicked(index)
        
        # Update breadcrumb if we have current_details_folder set
        if hasattr(self, 'current_details_folder') and self.current_details_folder:
            self.update_breadcrumb(self.current_details_folder)
            self.current_directory = self.current_details_folder
    
    def on_details_item_double_clicked(self, index):
        """Override to update breadcrumb when double-clicking folders in details view"""
        # Call parent implementation
        super().on_details_item_double_clicked(index)
        
        # Update breadcrumb if we navigated to a new folder
        if hasattr(self, 'current_details_folder') and self.current_details_folder:
            self.update_breadcrumb(self.current_details_folder)
            self.current_directory = self.current_details_folder
    
    def on_item_double_clicked(self, index):
        """Override to update breadcrumb when navigating into folders"""
        item = self.model.itemFromIndex(self.model.index(index.row(), 0, index.parent()))
        if not item:
            return
        
        path = item.data(Qt.ItemDataRole.UserRole)
        if not path:
            return
        
        path_obj = Path(path)
        
        if path_obj.is_dir():
            # Navigate into this directory
            self.navigate_to_path(str(path_obj))
        elif path_obj.is_file():
            # Open file with default app
            try:
                if os.name == 'nt':
                    os.startfile(str(path_obj))
                elif sys.platform == 'darwin':
                    import subprocess
                    subprocess.run(['open', str(path_obj)])
                else:
                    import subprocess
                    subprocess.run(['xdg-open', str(path_obj)])
            except Exception as e:
                logger.error(f"Failed to open file: {e}")


class FileExplorerV4(QWidget):
    """
    Multi-tab File Explorer with breadcrumb navigation
    Features:
    - Multiple tabs for different folders
    - Breadcrumb navigation per tab
    - New tab, close tab, pin tab functionality
    - All FileExplorerV3 features in each tab
    """
    
    def __init__(self):
        super().__init__()
        self.init_ui()
        
        # Create initial tab
        self.add_new_tab()
    
    def init_ui(self):
        """Initialize the UI"""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        
        # Create tab widget
        self.tab_widget = QTabWidget()
        self.tab_widget.setTabsClosable(True)
        self.tab_widget.setMovable(True)
        self.tab_widget.setDocumentMode(True)
        
        # Tab bar controls
        self.tab_widget.tabCloseRequested.connect(self.close_tab)
        
        # Add "+" button for new tab
        self.new_tab_btn = QToolButton()
        self.new_tab_btn.setText("➕")
        self.new_tab_btn.setToolTip("New Tab (Ctrl+T)")
        self.new_tab_btn.clicked.connect(self.add_new_tab)
        self.tab_widget.setCornerWidget(self.new_tab_btn, Qt.Corner.TopRightCorner)
        
        layout.addWidget(self.tab_widget)
        
        # Keyboard shortcuts (TODO: implement)
        # Ctrl+T: New tab
        # Ctrl+W: Close tab
        # Ctrl+Tab: Next tab
        # Ctrl+Shift+Tab: Previous tab
    
    def add_new_tab(self, path=None, title=None):
        """Add a new tab"""
        # Create new tab - if no path specified, stay at root Quick Links level
        explorer_tab = FileExplorerTab(initial_path=path)
        
        # Determine tab title
        if title is None:
            if path:
                path_obj = Path(path)
                title = path_obj.name if path_obj.name else str(path)
            else:
                title = "Quick Links"
        
        # Add tab
        index = self.tab_widget.addTab(explorer_tab, title)
        self.tab_widget.setCurrentIndex(index)
        
        # Connect path changes to update tab title
        explorer_tab.path_changed.connect(
            lambda p: self.update_tab_title(explorer_tab, p)
        )
        
        return explorer_tab
    
    def close_tab(self, index):
        """Close a tab"""
        # Don't close if it's the last tab
        if self.tab_widget.count() <= 1:
            return
        
        self.tab_widget.removeTab(index)
    
    def update_tab_title(self, tab_widget, path):
        """Update tab title when path changes"""
        index = self.tab_widget.indexOf(tab_widget)
        if index >= 0:
            path_obj = Path(path)
            title = path_obj.name if path_obj.name else str(path)
            self.tab_widget.setTabText(index, title)
            self.tab_widget.setTabToolTip(index, str(path))
    
    def get_current_tab(self):
        """Get currently active tab"""
        return self.tab_widget.currentWidget()
