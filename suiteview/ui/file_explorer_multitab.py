
"""
File Explorer - Multi-Tab Edition
Wraps FileExplorerCore with tab support, breadcrumbs, and enhanced features
"""

import os
import sys
import subprocess
from pathlib import Path
from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QTabWidget, 
                              QPushButton, QLabel, QFrame, QToolButton, QMenu, QLineEdit, QTreeView)
from PyQt6.QtCore import Qt, pyqtSignal, QEvent
from PyQt6.QtGui import QAction, QCursor, QMouseEvent

# Import the base FileExplorerCore
from suiteview.ui.file_explorer_core import FileExplorerCore

import logging
logger = logging.getLogger(__name__)


class NavigableTreeView(QTreeView):
    """Custom QTreeView that emits signals for back/forward mouse buttons"""
    
    back_button_clicked = pyqtSignal()
    forward_button_clicked = pyqtSignal()
    
    def mousePressEvent(self, event: QMouseEvent):
        """Override to catch back/forward mouse buttons"""
        button = event.button()
        
        # Get the item being clicked
        index = self.indexAt(event.pos())
        if index.isValid():
            # Get the name from the model (column 0 is the Name column)
            item_name = self.model().data(index.sibling(index.row(), 0), Qt.ItemDataRole.DisplayRole)
            print(f"NavigableTreeView.mousePressEvent: {button} - Clicked: {item_name}")
        else:
            print(f"NavigableTreeView.mousePressEvent: {button}")
        
        if event.button() == Qt.MouseButton.XButton1:
            print("XButton1 detected")
            self.back_button_clicked.emit()
            event.accept()
            return
        elif event.button() == Qt.MouseButton.XButton2:
            print("XButton2 detected")
            self.forward_button_clicked.emit()
            event.accept()
            return
        
        # Pass other events to parent
        super().mousePressEvent(event)
    
    def mouseDoubleClickEvent(self, event: QMouseEvent):
        """Override to see double-clicks"""
        print(f"NavigableTreeView.mouseDoubleClickEvent: {event.button()}")
        super().mouseDoubleClickEvent(event)


class ClickableBreadcrumb(QWidget):
    """Breadcrumb widget with clickable path segments"""
    
    path_clicked = pyqtSignal(str)  # Emits path when segment is clicked
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.current_path = ""
        self.is_edit_mode = False
        
        # Main layout
        self.layout = QHBoxLayout(self)
        self.layout.setContentsMargins(0, 0, 0, 0)
        self.layout.setSpacing(0)
        
        # Breadcrumb display widget (shows clickable segments)
        self.breadcrumb_display = QWidget()
        self.breadcrumb_layout = QHBoxLayout(self.breadcrumb_display)
        self.breadcrumb_layout.setContentsMargins(2, 0, 2, 0)
        self.breadcrumb_layout.setSpacing(0)
        self.breadcrumb_layout.addStretch()
        
        # Text input for editing (hidden by default)
        self.path_input = QLineEdit()
        self.path_input.setStyleSheet("""
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
        self.path_input.hide()
        self.path_input.returnPressed.connect(self.finish_editing)
        self.path_input.installEventFilter(self)
        
        self.layout.addWidget(self.breadcrumb_display)
        self.layout.addWidget(self.path_input)
        
        self.setStyleSheet("""
            ClickableBreadcrumb {
                background-color: #ffffff;
                border: 1px solid #ced4da;
                border-radius: 2px;
            }
        """)
    
    def eventFilter(self, obj, event):
        """Handle events for path input"""
        if obj == self.path_input and event.type() == QEvent.Type.FocusOut:
            self.finish_editing()
        return super().eventFilter(obj, event)
    
    def mousePressEvent(self, event):
        """Switch to edit mode when clicking on breadcrumb"""
        if not self.is_edit_mode and event.button() == Qt.MouseButton.LeftButton:
            self.enter_edit_mode()
    
    def enter_edit_mode(self):
        """Switch to editable text input"""
        self.is_edit_mode = True
        self.breadcrumb_display.hide()
        self.path_input.setText(self.current_path)
        self.path_input.show()
        self.path_input.setFocus()
        self.path_input.selectAll()
    
    def finish_editing(self):
        """Finish editing and emit signal if path changed"""
        if self.is_edit_mode:
            new_path = self.path_input.text().strip()
            if new_path and new_path != self.current_path:
                if Path(new_path).exists():
                    self.path_clicked.emit(new_path)
            
            self.is_edit_mode = False
            self.path_input.hide()
            self.breadcrumb_display.show()
    
    def set_path(self, path):
        """Update the breadcrumb with a new path"""
        self.current_path = str(path)
        self.update_display()
    
    def update_display(self):
        """Update the breadcrumb display with clickable segments"""
        # Clear existing widgets
        while self.breadcrumb_layout.count() > 1:  # Keep the stretch
            item = self.breadcrumb_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        
        if not self.current_path:
            return
        
        try:
            path_obj = Path(self.current_path)
            
            # Build path segments
            parts = path_obj.parts
            
            for i, part in enumerate(parts):
                # Create button for this segment
                btn = QPushButton(part)
                btn.setFlat(True)
                btn.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
                btn.setStyleSheet("""
                    QPushButton {
                        background-color: transparent;
                        border: none;
                        padding: 2px 6px;
                        text-align: left;
                        font-family: Segoe UI;
                        font-size: 9pt;
                        color: #0066cc;
                    }
                    QPushButton:hover {
                        background-color: #e5f1fb;
                        text-decoration: underline;
                    }
                """)
                
                # Build the full path up to this segment
                segment_path = Path(*parts[:i+1])
                btn.clicked.connect(lambda checked, p=str(segment_path): self.path_clicked.emit(p))
                
                self.breadcrumb_layout.insertWidget(self.breadcrumb_layout.count() - 1, btn)
                
                # Add separator (except after last item)
                if i < len(parts) - 1:
                    separator = QLabel(" > ")
                    separator.setStyleSheet("color: #6c757d; font-size: 9pt;")
                    self.breadcrumb_layout.insertWidget(self.breadcrumb_layout.count() - 1, separator)
        
        except Exception as e:
            logger.error(f"Failed to update breadcrumb display: {e}")


class FileExplorerTab(FileExplorerCore):
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
        
        # Navigation history for back/forward buttons
        self.nav_history = []  # List of visited paths
        self.nav_history_index = -1  # Current position in history
        
        # Replace the parent's tree views with our custom NavigableTreeView
        # to catch mouse button events
        self._replace_views_with_navigable()
        
        # Set up dual pane feature
        self._setup_dual_pane()
        
        # Add breadcrumb bar at the top
        self.insert_breadcrumb_bar()
        
        # Only navigate if initial path is explicitly provided
        # Otherwise, stay at root level with Quick Links
        if initial_path:
            self.navigate_to_path(initial_path)
        else:
            # Stay at root level - don't navigate anywhere
            self.update_breadcrumb("Quick Links")
    
    def _setup_dual_pane(self):
        """Set up a second folder tree view for dual-pane mode (on the right)"""
        from PyQt6.QtWidgets import QSplitter, QHeaderView, QVBoxLayout, QWidget, QLabel
        from PyQt6.QtGui import QStandardItemModel, QStandardItem
        from PyQt6.QtCore import Qt
        
        # Find the main splitter that contains tree and details
        for child in self.findChildren(QSplitter):
            if child.count() >= 2:
                self.main_splitter = child
                break
        
        if not hasattr(self, 'main_splitter'):
            print("Could not find main splitter")
            return
        
        # Create a panel for the second tree (like the left tree panel)
        tree_panel_2 = QWidget()
        tree_panel_2.setVisible(False)  # Hidden by default
        panel_layout = QVBoxLayout(tree_panel_2)
        panel_layout.setContentsMargins(0, 0, 0, 0)
        panel_layout.setSpacing(0)
        
        # Add "Folders" header
        folders_label = QLabel("Folders")
        folders_label.setStyleSheet("""
            QLabel {
                background-color: #f8f9fa;
                padding: 8px;
                font-weight: bold;
                border-bottom: 1px solid #dee2e6;
            }
        """)
        panel_layout.addWidget(folders_label)
        
        # Create the second tree view
        self.tree_view_2 = NavigableTreeView()
        
        # Use the SAME model as the first tree (so they show the same Quick Links)
        self.tree_view_2.setModel(self.model)
        
        # Copy all properties from first tree view
        self.tree_view_2.setAnimated(self.tree_view.isAnimated())
        self.tree_view_2.setIndentation(self.tree_view.indentation())
        self.tree_view_2.setHeaderHidden(True)  # Hide header like left tree
        self.tree_view_2.setSelectionMode(self.tree_view.selectionMode())
        self.tree_view_2.setContextMenuPolicy(self.tree_view.contextMenuPolicy())
        
        # Hide all columns except the first (Name) - same as left tree
        for col in range(1, 4):
            self.tree_view_2.setColumnHidden(col, True)
        
        # Set column resize mode
        self.tree_view_2.header().setStretchLastSection(False)
        self.tree_view_2.header().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        
        # Connect signals for second tree - same as first tree
        self.tree_view_2.expanded.connect(self.on_item_expanded)
        self.tree_view_2.clicked.connect(self.on_tree_item_clicked)
        self.tree_view_2.customContextMenuRequested.connect(self.show_tree_context_menu)
        self.tree_view_2.back_button_clicked.connect(self.navigate_back)
        self.tree_view_2.forward_button_clicked.connect(self.navigate_forward)
        
        panel_layout.addWidget(self.tree_view_2)
        
        # Add to the RIGHT side of the splitter (after details view)
        self.main_splitter.addWidget(tree_panel_2)
        
        # Store reference to the panel
        self.tree_panel_2 = tree_panel_2
        
        # Store dual pane state
        self.dual_pane_active = False
    
    def toggle_dual_pane(self):
        """Toggle the second tree view on/off"""
        self.dual_pane_active = not self.dual_pane_active
        
        if hasattr(self, 'tree_panel_2'):
            self.tree_panel_2.setVisible(self.dual_pane_active)
            
            # Adjust splitter sizes when toggling
            if self.dual_pane_active:
                # Three panes: left tree, details (middle), right tree
                total = self.main_splitter.width()
                self.main_splitter.setSizes([total // 4, total // 2, total // 4])
            else:
                # Two panes: left tree, details
                total = self.main_splitter.width()
                self.main_splitter.setSizes([total // 3, total * 2 // 3, 0])
        
        print(f"Dual pane {'enabled' if self.dual_pane_active else 'disabled'}")
    
    def _replace_views_with_navigable(self):
        """Replace parent's QTreeView instances with NavigableTreeView"""
        # Get the parent's splitter that contains the views
        splitter = self.findChild(QWidget.__class__, "")  # Find splitter
        
        # Store old views' properties
        old_tree = self.tree_view
        old_details = self.details_view
        
        # Get the parent widgets (they're in a splitter)
        tree_parent = old_tree.parent()
        details_parent = old_details.parent()
        
        # Get layouts
        tree_layout = tree_parent.layout() if hasattr(tree_parent, 'layout') and tree_parent.layout() else None
        details_layout = details_parent.layout() if hasattr(details_parent, 'layout') and details_parent.layout() else None
        
        # Create new navigable views
        new_tree = NavigableTreeView()
        new_details = NavigableTreeView()
        
        # Copy properties from old tree view to new one
        new_tree.setModel(old_tree.model())
        new_tree.setAnimated(old_tree.isAnimated())
        new_tree.setIndentation(old_tree.indentation())
        new_tree.setHeaderHidden(old_tree.isHeaderHidden())
        new_tree.setSelectionMode(old_tree.selectionMode())
        new_tree.setContextMenuPolicy(old_tree.contextMenuPolicy())
        
        # Copy properties from old details view to new one  
        new_details.setModel(old_details.model())
        new_details.setAnimated(old_details.isAnimated())
        new_details.setRootIsDecorated(old_details.rootIsDecorated())
        new_details.setIndentation(old_details.indentation())
        new_details.setHeaderHidden(old_details.isHeaderHidden())
        new_details.setSelectionMode(old_details.selectionMode())
        new_details.setSortingEnabled(old_details.isSortingEnabled())
        new_details.setAlternatingRowColors(old_details.alternatingRowColors())
        new_details.setContextMenuPolicy(old_details.contextMenuPolicy())
        
        # Replace in layouts
        if tree_layout:
            tree_layout.replaceWidget(old_tree, new_tree)
        if details_layout:
            details_layout.replaceWidget(old_details, new_details)
        
        # Delete old views
        old_tree.deleteLater()
        old_details.deleteLater()
        
        # Update references
        self.tree_view = new_tree
        self.details_view = new_details
        
        # Reconnect signals that were on the old views
        # Note: We don't need to disconnect old signals because old_tree and old_details are being deleted
        self.tree_view.expanded.connect(self.on_item_expanded)
        self.tree_view.clicked.connect(self.on_tree_item_clicked)
        self.tree_view.customContextMenuRequested.connect(self.show_tree_context_menu)
        
        # IMPORTANT: Connect to our overridden method for history tracking
        self.details_view.doubleClicked.connect(self.on_details_item_double_clicked)
        self.details_view.customContextMenuRequested.connect(self.show_details_context_menu)
        
        print(f"Connected details_view.doubleClicked to {self.on_details_item_double_clicked}")
        print(f"details_view type: {type(self.details_view)}")
        print(f"Method owner: {self.on_details_item_double_clicked.__self__.__class__.__name__}")
        
        # Connect navigation signals
        self.tree_view.back_button_clicked.connect(self.navigate_back)
        self.tree_view.forward_button_clicked.connect(self.navigate_forward)
        self.details_view.back_button_clicked.connect(self.navigate_back)
        self.details_view.forward_button_clicked.connect(self.navigate_forward)
    
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
        
        # Clickable breadcrumb widget
        self.breadcrumb_widget = ClickableBreadcrumb()
        self.breadcrumb_widget.path_clicked.connect(self.navigate_to_path)
        breadcrumb_layout.addWidget(self.breadcrumb_widget, 1)
        
        # Dual pane toggle button
        self.dual_pane_btn = QPushButton("⇄")
        self.dual_pane_btn.setToolTip("Toggle Dual Pane View")
        self.dual_pane_btn.setFixedSize(24, 24)
        self.dual_pane_btn.setCheckable(True)
        self.dual_pane_btn.setStyleSheet("""
            QPushButton {
                background-color: #ffffff;
                border: 1px solid #ced4da;
                border-radius: 2px;
                font-size: 13px;
            }
            QPushButton:hover {
                background-color: #e9ecef;
            }
            QPushButton:checked {
                background-color: #0d6efd;
                color: white;
            }
        """)
        self.dual_pane_btn.clicked.connect(self.toggle_dual_pane)
        breadcrumb_layout.addWidget(self.dual_pane_btn)
        
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
            
            # Update the clickable breadcrumb widget
            self.breadcrumb_widget.set_path(str(path_obj))
            
            self.current_directory = str(path_obj)
            self.path_changed.emit(str(path_obj))
            
        except Exception as e:
            logger.error(f"Failed to update breadcrumb: {e}")
            self.breadcrumb_widget.set_path(str(path))
    
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
    
    def navigate_to_path(self, path, add_to_history=True):
        """Navigate to a specific directory path - loads in details pane (right side)"""
        try:
            path_obj = Path(path)
            if not path_obj.exists():
                return
            
            if path_obj.is_file():
                path_obj = path_obj.parent
            
            path_str = str(path_obj)
            
            # Add to navigation history if requested (not when using back/forward)
            if add_to_history:
                # If we're not at the end of history, remove everything after current position
                if self.nav_history_index < len(self.nav_history) - 1:
                    self.nav_history = self.nav_history[:self.nav_history_index + 1]
                
                # Add new path if it's different from current
                if not self.nav_history or self.nav_history[-1] != path_str:
                    self.nav_history.append(path_str)
                    self.nav_history_index = len(self.nav_history) - 1
                    print(f"Added to history: {path_str}")
                    print(f"History: {self.nav_history}")
                    print(f"Index: {self.nav_history_index}")
            
            # Update breadcrumb
            self.update_breadcrumb(path_str)
            
            # Load in the details pane (right side) instead of tree
            self.load_folder_contents_in_details(path_obj)
            
        except Exception as e:
            logger.error(f"Failed to navigate to {path}: {e}")
    
    def navigate_back(self):
        """Navigate to previous folder in history"""
        print(f"navigate_back called: index={self.nav_history_index}, history={self.nav_history}")
        if self.nav_history_index > 0:
            self.nav_history_index -= 1
            path = self.nav_history[self.nav_history_index]
            print(f"Going back to: {path}")
            self.navigate_to_path(path, add_to_history=False)
        else:
            print("Already at beginning of history")
    
    def navigate_forward(self):
        """Navigate to next folder in history"""
        print(f"navigate_forward called: index={self.nav_history_index}, history={self.nav_history}")
        if self.nav_history_index < len(self.nav_history) - 1:
            self.nav_history_index += 1
            path = self.nav_history[self.nav_history_index]
            print(f"Going forward to: {path}")
            self.navigate_to_path(path, add_to_history=False)
        else:
            print("Already at end of history")
    
    def on_details_item_double_clicked(self, index):
        """Override to use navigate_to_path for history tracking"""
        print(f"\n=== DOUBLE CLICK DEBUG ===")
        print(f"Proxy Index: row={index.row()}, col={index.column()}")
        
        # Get the data directly from the proxy model (which handles sorting)
        path = self.details_sort_proxy.data(index, Qt.ItemDataRole.UserRole)
        
        # If this column doesn't have the path data, get it from column 0 of the same row
        if not path:
            col0_index = index.sibling(index.row(), 0)
            col0_text = self.details_sort_proxy.data(col0_index, Qt.ItemDataRole.DisplayRole)
            print(f"Column 0 text for this row: {col0_text}")
            path = self.details_sort_proxy.data(col0_index, Qt.ItemDataRole.UserRole)
        
        if not path:
            print("No path data found")
            return
        
        print(f"Path retrieved: {path}")
        print(f"=========================\n")
        
        path_obj = Path(path)
        
        if path_obj.is_dir():
            print(f"Is directory, navigating to: {path_obj}")
            # Use navigate_to_path to track history
            self.navigate_to_path(path_obj, add_to_history=True)
        elif path_obj.is_file():
            # Open file with default application
            try:
                if os.name == 'nt':
                    os.startfile(str(path_obj))
                elif sys.platform == 'darwin':
                    subprocess.run(['open', str(path_obj)])
                else:
                    subprocess.run(['xdg-open', str(path_obj)])
            except Exception as e:
                logger.error(f"Failed to open file: {e}")
                from PyQt6.QtWidgets import QMessageBox
                QMessageBox.warning(self, "Cannot Open File", f"Failed to open {path_obj.name}\n\nError: {str(e)}")
    
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
    
    def navigate_to_bookmark_folder(self, folder_path):
        """Override parent method to update breadcrumb when navigating from bookmark"""
        # Call parent implementation to load folder contents
        super().navigate_to_bookmark_folder(folder_path)
        
        # Update breadcrumb if navigation was successful
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


class FileExplorerMultiTab(QWidget):
    """
    Multi-tab File Explorer with breadcrumb navigation
    Features:
    - Multiple tabs for different folders
    - Breadcrumb navigation per tab
    - New tab, close tab, pin tab functionality
    - All FileExplorerCore features in each tab
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
    
    def navigate_to_bookmark_folder(self, folder_path):
        """Navigate the current tab to a bookmark folder"""
        current_tab = self.get_current_tab()
        if current_tab and hasattr(current_tab, 'navigate_to_bookmark_folder'):
            current_tab.navigate_to_bookmark_folder(folder_path)
