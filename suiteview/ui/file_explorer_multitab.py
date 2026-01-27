
"""
File Explorer - Multi-Tab Edition
Wraps FileExplorerCore with tab support, breadcrumbs, and enhanced features
"""

import os
import sys
import subprocess
import json
import time
from pathlib import Path
from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QTabWidget, 
                              QPushButton, QLabel, QFrame, QMenu, QLineEdit, QTreeView, QStyle, QTabBar, QToolButton,
                              QListWidget, QListWidgetItem, QSplitter, QAbstractItemView, QScrollArea)
from PyQt6.QtCore import Qt, pyqtSignal, QEvent, QSize
from PyQt6.QtGui import QAction, QCursor, QMouseEvent

# Import the base FileExplorerCore
from suiteview.ui.file_explorer_core import FileExplorerCore, DropTreeView

# Import unified bookmark widgets for sidebar categories
from suiteview.ui.widgets.bookmark_widgets import (
    CategoryButton, CategoryPopup, CategoryBookmarkButton, BookmarkContainer,
    CATEGORY_BUTTON_STYLE_SIDEBAR, CONTEXT_MENU_STYLE, CATEGORY_CONTEXT_MENU_STYLE
)

import logging
logger = logging.getLogger(__name__)


class NavigableTreeView(DropTreeView):
    """Custom QTreeView that emits signals for back/forward mouse buttons and supports file drops"""
    
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
        self.breadcrumb_display.setStyleSheet("background-color: #FFFDE7;")
        self.breadcrumb_layout = QHBoxLayout(self.breadcrumb_display)
        self.breadcrumb_layout.setContentsMargins(2, 0, 2, 0)
        self.breadcrumb_layout.setSpacing(0)
        self.breadcrumb_layout.addStretch()
        
        # Text input for editing (hidden by default)
        self.path_input = QLineEdit()
        self.path_input.setStyleSheet("""
            QLineEdit {
                background-color: #FFFDE7;
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
                background-color: #FFFDE7;
                border: 2px solid #6B8DC9;
                border-radius: 3px;
                padding: 1px;
            }
            ClickableBreadcrumb:hover {
                border-color: #2563EB;
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
                        background-color: #FFFDE7;
                        border: none;
                        padding: 2px 6px;
                        text-align: left;
                        font-family: Segoe UI;
                        font-size: 9pt;
                        font-weight: bold;
                        color: #0066cc;
                    }
                    QPushButton:hover {
                        background-color: #FFFDE7;
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
        
        # Two separate history tracking systems:
        # 1. Current Path - browser-style with back/forward, truncates on branch
        self.current_path_history = []  # List of visited paths (truncates on branch)
        self.current_path_index = -1  # Current position in current path
        
        # 2. Full History - complete log of everywhere visited (never truncates)
        self.full_history = []  # List of all visited paths
        
        # Which history view is active in the panel
        self.history_view_mode = "current_path"  # "current_path" or "full_history"
        
        # Replace the parent's tree views with our custom NavigableTreeView
        # to catch mouse button events
        self._replace_views_with_navigable()
        
        # Set up dual pane feature
        self._setup_dual_pane()
        
        # Add breadcrumb bar at the top
        self.insert_breadcrumb_bar()
        
        # Only navigate if initial path is explicitly provided
        # Otherwise, navigate to OneDrive by default
        if initial_path:
            self.navigate_to_path(initial_path)
        else:
            # Navigate to OneDrive as the default starting location
            onedrive_paths = self.get_onedrive_paths()
            if onedrive_paths:
                self.navigate_to_path(str(onedrive_paths[0]))
            else:
                # Fallback to home directory if OneDrive not available
                self.navigate_to_path(str(Path.home()))
        
        # Set up keyboard shortcuts
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
    
    def keyPressEvent(self, event):
        """Handle keyboard shortcuts for navigation"""
        modifiers = event.modifiers()
        key = event.key()
        
        # Alt+Left = Back
        if key == Qt.Key.Key_Left and (modifiers & Qt.KeyboardModifier.AltModifier):
            self.navigate_back()
            event.accept()
            return
        
        # Alt+Right = Forward
        if key == Qt.Key.Key_Right and (modifiers & Qt.KeyboardModifier.AltModifier):
            self.navigate_forward()
            event.accept()
            return
        
        # Backspace = Go up one level (like Windows Explorer)
        if key == Qt.Key.Key_Backspace and not modifiers:
            self.go_up_one_level()
            event.accept()
            return
        
        # F5 = Refresh current folder
        if key == Qt.Key.Key_F5 and not modifiers:
            self.refresh_current_folder()
            event.accept()
            return
        
        super().keyPressEvent(event)
    
    def _setup_dual_pane(self):
        """Set up the Quick Links panel (on the right) - using unified BookmarkContainer"""
        from PyQt6.QtWidgets import QSplitter, QHeaderView, QVBoxLayout, QWidget, QLabel, QScrollArea
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
        
        # Create a panel for Quick Links
        quick_links_panel = QWidget()
        quick_links_panel.setVisible(False)  # Hidden by default
        quick_links_panel.setMinimumWidth(180)  # Ensure minimum width for readability
        panel_layout = QVBoxLayout(quick_links_panel)
        panel_layout.setContentsMargins(0, 0, 0, 0)
        panel_layout.setSpacing(0)
        
        # Add "Bookmarks" header - matching other panel headers with 3D effect
        header_label = QLabel("Bookmarks")
        header_label.setStyleSheet("""
            QLabel {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    stop:0 #C8DCF8, stop:0.5 #A8C8F0, stop:1 #90B8E8);
                padding: 5px 12px;
                font-weight: 700;
                font-size: 11px;
                color: #0A1E5E;
                border: none;
                border-top: 1px solid #D8E8FF;
                border-bottom: 1px solid #6090C0;
                text-transform: uppercase;
                letter-spacing: 1px;
            }
        """)
        # Add context menu to header for creating new categories
        header_label.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        header_label.customContextMenuRequested.connect(self._show_quick_links_panel_context_menu)
        panel_layout.addWidget(header_label)
        self.quick_links_header = header_label
        
        # Create a separate model for Quick Links (kept for compatibility)
        self.quick_links_model = QStandardItemModel()
        self.quick_links_model.setHorizontalHeaderLabels(['Name'])
        
        # Create unified BookmarkContainer for the sidebar
        # Bar ID 1 = vertical sidebar (by convention)
        self.bookmark_container = BookmarkContainer(
            bar_id=1,
            orientation='vertical',
            parent=quick_links_panel
        )
        
        # Connect signals from BookmarkContainer
        self.bookmark_container.item_clicked.connect(self._on_bookmark_clicked)
        self.bookmark_container.item_double_clicked.connect(self._on_bookmark_double_clicked)
        
        # Connect drop signals for cross-container moves (preserves existing move logic)
        self.bookmark_container.bookmark_dropped.connect(self.on_bookmark_dropped_to_quick_links)
        self.bookmark_container.file_dropped.connect(self.on_file_dropped_to_quick_links)
        self.bookmark_container.category_dropped.connect(self.on_category_dropped_to_quick_links)
        
        # Add the container to the panel layout
        panel_layout.addWidget(self.bookmark_container, 1)  # stretch factor 1 to fill space
        
        # Store reference to items_layout for backwards compatibility with drop handlers
        self.quick_links_items_layout = self.bookmark_container.items_layout
        self.quick_links_scroll_content = self.bookmark_container.items_container
        
        # Populate with quick links (items and categories)
        self.bookmark_container.refresh()
        
        # Add footer to Quick Links panel
        footer = QLabel("")
        footer.setStyleSheet("""
            QLabel {
                background-color: #E8D8F0;
                padding: 2px 8px;
                font-size: 9pt;
                color: #555555;
                border: none;
                border-top: 1px solid #B098D0;
            }
        """)
        footer.setFixedHeight(20)
        panel_layout.addWidget(footer)
        self.quick_links_footer = footer
        
        # Add to the RIGHT side of the splitter (after details view)
        self.main_splitter.addWidget(quick_links_panel)
        
        # Set stretch factors: tree and details stay fixed size,
        # Quick Links panel stretches when window is resized
        # Index 0 = tree panel, Index 1 = details panel, Index 2 = quick links panel
        self.main_splitter.setStretchFactor(0, 0)  # Tree panel doesn't stretch
        self.main_splitter.setStretchFactor(1, 0)  # Details panel doesn't stretch
        self.main_splitter.setStretchFactor(2, 1)  # Quick links stretches on window resize
        
        # Store reference to the panel (keep old name for compatibility)
        self.tree_panel_2 = quick_links_panel
        self.quick_links_panel = quick_links_panel
        
        # Restore panel visibility and sizes from saved state
        self.dual_pane_active = self.panel_widths.get('quick_links_visible', False)
        quick_links_panel.setVisible(self.dual_pane_active)
        
        # Restore all 3 panel sizes (now that 3rd panel is added)
        saved_left = self.panel_widths.get('left_panel', 300)
        saved_middle = self.panel_widths.get('middle_panel', 700)
        saved_right = self.panel_widths.get('right_panel', 200)
        
        if self.dual_pane_active:
            self.main_splitter.setSizes([saved_left, saved_middle, saved_right])
        else:
            # Quick links hidden - give its space to middle panel
            self.main_splitter.setSizes([saved_left, saved_middle + saved_right, 0])
    
    def show_quick_links_context_menu(self, position):
        """Show context menu for Quick Links panel items - DEPRECATED, using per-item menus now"""
        # This method is deprecated - context menus are now handled by individual item buttons
        pass
    
    def open_quick_link_path(self, path):
        """Open a quick link path - navigate for folders, open for files"""
        path_obj = Path(path)
        if path_obj.is_file():
            self.open_file(path)
        else:
            self.navigate_to_path(path)
    
    def open_path_in_explorer(self, path):
        """Open a path in Windows Explorer"""
        import subprocess
        from pathlib import Path
        path = Path(path)
        if path.exists():
            if path.is_file():
                subprocess.run(['explorer', '/select,', str(path)])
            else:
                subprocess.run(['explorer', str(path)])
    
    def refresh_quick_links_list(self):
        """Refresh the Quick Links list - delegates to BookmarkContainer"""
        if hasattr(self, 'bookmark_container'):
            self.bookmark_container.refresh()
            self._update_quick_links_footer()
        else:
            logger.warning("BookmarkContainer not available, cannot refresh quick links")
    
    def _update_quick_links_footer(self):
        """Update the footer with item/category counts"""
        if not hasattr(self, 'quick_links_footer'):
            return
            
        items = self.custom_quick_links.get('items', [])
        categories = self.custom_quick_links.get('categories', {})
        
        bookmark_count = 0
        category_count = 0
        
        for item_data in items:
            if item_data.get('type') == 'bookmark':
                bookmark_count += 1
            elif item_data.get('type') == 'category':
                category_name = item_data.get('name', '')
                if category_name in categories:
                    category_count += 1
                    bookmark_count += len(categories[category_name])
        
        if category_count > 0:
            self.quick_links_footer.setText(f"{bookmark_count} item(s), {category_count} categories")
        else:
            self.quick_links_footer.setText(f"{bookmark_count} quick link(s)")
    
    def _on_bookmark_clicked(self, path):
        """Handle click on bookmark button in Quick Links"""
        path_obj = Path(path)
        if path_obj.is_dir():
            self.navigate_to_path(path)
        elif path_obj.is_file():
            # Single click on file opens it
            self.open_file(path)
    
    def _on_bookmark_double_clicked(self, path):
        """Handle double-click on bookmark button in Quick Links"""
        path_obj = Path(path)
        if path_obj.is_file():
            self.open_file(path)
        else:
            self.navigate_to_path(path)
    
    def _show_bookmark_context_menu(self, position, bookmark_btn):
        """Show context menu for a bookmark button in Quick Links"""
        from PyQt6.QtWidgets import QMenu, QApplication
        from PyQt6.QtGui import QAction
        
        path = bookmark_btn.bookmark_path
        
        menu = QMenu(self)
        
        # Open folder location - navigate to parent folder
        open_folder_action = QAction("📂 Open folder location", self)
        open_folder_action.triggered.connect(lambda: self._open_folder_location(path))
        menu.addAction(open_folder_action)
        
        # Copy full link to clipboard
        copy_link_action = QAction("📋 Copy full link to clipboard", self)
        copy_link_action.triggered.connect(lambda: QApplication.clipboard().setText(path))
        menu.addAction(copy_link_action)
        
        menu.addSeparator()
        
        # Remove action
        remove_action = QAction("🗑️ Remove from Quick Links", self)
        remove_action.triggered.connect(lambda: self._remove_bookmark_from_quick_links(path))
        menu.addAction(remove_action)
        
        menu.exec(bookmark_btn.mapToGlobal(position))
    
    def _open_folder_location(self, path):
        """Open the folder containing the given path in File Navigator"""
        path_obj = Path(path)
        if path_obj.is_file():
            # Navigate to parent folder
            parent_folder = str(path_obj.parent)
        else:
            # It's already a folder, navigate to its parent
            parent_folder = str(path_obj.parent)
        
        if Path(parent_folder).exists():
            self.navigate_to_path(parent_folder)
    
    def _show_category_context_menu(self, position, cat_widget):
        """Show context menu for a category in Quick Links"""
        from PyQt6.QtWidgets import QMenu, QMessageBox, QInputDialog
        from PyQt6.QtGui import QAction
        
        category_name = cat_widget.category_name
        category_items = cat_widget.category_items
        
        menu = QMenu(self)
        menu.setStyleSheet(CATEGORY_CONTEXT_MENU_STYLE)
        
        # Rename action
        rename_action = QAction("✏️ Rename", self)
        rename_action.triggered.connect(lambda: self._rename_category_in_quick_links(category_name))
        menu.addAction(rename_action)
        
        # Remove action with confirmation
        remove_action = QAction("🗑️ Remove", self)
        remove_action.triggered.connect(lambda: self._remove_category_with_confirmation(category_name, category_items))
        menu.addAction(remove_action)
        
        menu.exec(cat_widget.mapToGlobal(position))
    
    def _rename_category_in_quick_links(self, old_name):
        """Rename a category in Quick Links"""
        from PyQt6.QtWidgets import QInputDialog, QMessageBox, QLineEdit
        
        new_name, ok = QInputDialog.getText(
            self,
            "Rename Category",
            f"Enter new name for '{old_name}':",
            QLineEdit.EchoMode.Normal,
            old_name
        )
        
        if ok and new_name:
            new_name = new_name.strip()
            if new_name == old_name:
                return
            
            if new_name in self.custom_quick_links.get('categories', {}):
                QMessageBox.warning(self, "Duplicate", f"Category '{new_name}' already exists.")
            else:
                if self.rename_category_in_quick_links(old_name, new_name):
                    self.refresh_quick_links_list()
    
    def _remove_category_with_confirmation(self, category_name, category_items):
        """Remove a category from Quick Links with confirmation showing all items"""
        from PyQt6.QtWidgets import QMessageBox
        
        # Build message with list of items
        if category_items:
            items_list = "\n".join([f"  • {item.get('name', item.get('path', 'Unknown'))}" for item in category_items])
            message = f"Are you sure you want to remove the category '{category_name}'?\n\nThe following {len(category_items)} bookmark(s) will be deleted:\n{items_list}"
        else:
            message = f"Are you sure you want to remove the empty category '{category_name}'?"
        
        reply = QMessageBox.question(
            self,
            "Remove Category",
            message,
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No
        )
        
        if reply == QMessageBox.StandardButton.Yes:
            self.remove_category_from_quick_links(category_name)
            self.refresh_quick_links_list()
    
    def _show_quick_links_panel_context_menu(self, position):
        """Show context menu for Quick Links panel (empty area or header) - allows creating new categories"""
        from PyQt6.QtWidgets import QMenu
        from PyQt6.QtGui import QAction
        
        menu = QMenu(self)
        
        # New Category action
        new_category_action = QAction("📁 New Category...", self)
        new_category_action.triggered.connect(self._create_new_category)
        menu.addAction(new_category_action)
        
        # Get the sender widget to map position correctly
        sender = self.sender()
        if sender:
            menu.exec(sender.mapToGlobal(position))
        else:
            menu.exec(self.mapToGlobal(position))
    
    def _create_new_category(self):
        """Create a new empty category in Quick Links"""
        from PyQt6.QtWidgets import QInputDialog, QMessageBox, QLineEdit
        
        name, ok = QInputDialog.getText(
            self,
            "New Category",
            "Enter name for the new category:",
            QLineEdit.EchoMode.Normal,
            ""
        )
        
        if ok and name:
            name = name.strip()
            if not name:
                QMessageBox.warning(self, "Invalid Name", "Category name cannot be empty.")
                return
            
            # Check if category already exists
            if name in self.custom_quick_links.get('categories', {}):
                QMessageBox.warning(self, "Duplicate", f"Category '{name}' already exists.")
                return
            
            # Create the category
            if 'categories' not in self.custom_quick_links:
                self.custom_quick_links['categories'] = {}
            self.custom_quick_links['categories'][name] = []
            
            # Add to items list (categories appear at the end by default)
            if 'items' not in self.custom_quick_links:
                self.custom_quick_links['items'] = []
            self.custom_quick_links['items'].append({
                'type': 'category',
                'name': name
            })
            
            self.save_quick_links()
            self.refresh_quick_links_list()
            logger.info(f"Created new category '{name}' in Quick Links")
    
    def _remove_bookmark_from_quick_links(self, path):
        """Remove a bookmark from Quick Links"""
        items = self.custom_quick_links.get('items', [])
        # Find and remove the bookmark
        for i, item_data in enumerate(items):
            if item_data.get('type') == 'bookmark':
                if item_data.get('data', {}).get('path') == path:
                    items.pop(i)
                    self.save_quick_links()
                    self.refresh_quick_links_list()
                    return
    
    def on_quick_link_item_dropped(self, item_data, drop_index):
        """Handle an item being dropped at a specific position in Quick Links"""
        items = self.custom_quick_links.get('items', [])
        
        item_type = item_data.get('type', '')
        source = item_data.get('source', '')
        old_index = item_data.get('index', -1)
        source_category = item_data.get('source_category', '')
        
        if source == 'quick_links' and old_index >= 0:
            # Internal reorder - remove from old position first
            if old_index < len(items):
                moved_item = items.pop(old_index)
                # Adjust drop_index if we removed from before it
                if old_index < drop_index:
                    drop_index -= 1
                # Insert at new position
                items.insert(drop_index, moved_item)
                self.save_quick_links()
                self.refresh_quick_links_list()
        elif source == 'quick_links_category' and source_category:
            # Item from Quick Links category - move to main sidebar
            path = item_data.get('path', '')
            name = item_data.get('name', '')
            if path and not self.is_path_in_quick_links(path):
                # Add to sidebar
                self.add_to_quick_links(path, insert_at=drop_index)
                
                # Remove from source category
                categories = self.custom_quick_links.get('categories', {})
                if source_category in categories:
                    category_items = categories[source_category]
                    for i, item in enumerate(category_items):
                        if item.get('path') == path:
                            category_items.pop(i)
                            break
                self.save_quick_links()
                self.refresh_quick_links_list()
                logger.info(f"Moved '{name}' from category '{source_category}' to Quick Links sidebar")
        else:
            # New item from outside - will be handled by other drop handlers
            pass
    
    def _on_category_item_clicked(self, path):
        """Handle click on item inside a Quick Links category"""
        path_obj = Path(path)
        if path_obj.is_dir():
            self.navigate_to_path(path)
    
    def _on_category_item_double_clicked(self, path):
        """Handle double-click on item inside a Quick Links category"""
        path_obj = Path(path)
        if path_obj.is_file():
            self.open_file(path)
        else:
            self.navigate_to_path(path)
    
    def _on_bookmark_dropped_to_category(self, category_name, bookmark):
        """Handle bookmark dropped onto a Quick Links category"""
        path = bookmark.get('path', '')
        source_category = bookmark.get('_source_category', bookmark.get('source_category', ''))
        if not path:
            return
        
        # Don't move to the same category
        if source_category == category_name:
            return
        
        # Add to the category
        if category_name in self.custom_quick_links.get('categories', {}):
            # Check if already in category
            for item in self.custom_quick_links['categories'][category_name]:
                if item.get('path') == path:
                    return  # Already exists
            
            self.custom_quick_links['categories'][category_name].append({
                'name': bookmark.get('name', Path(path).name),
                'path': path,
                'type': bookmark.get('type', 'folder' if Path(path).is_dir() else 'file')
            })
            
            # Remove from source
            removed_from_source = False
            
            # If from bookmark bar (top level), remove from items list
            if source_category in ('__BAR__', '__CONTAINER__') and bookmark.get('source_location') == 'bar':
                if hasattr(self, 'bookmark_bar') and self.bookmark_bar:
                    bar_items = self.bookmark_bar.bookmarks_data.get('items', [])
                    for i, item in enumerate(bar_items):
                        if item.get('type') == 'bookmark':
                            item_path = item.get('path') or item.get('data', {}).get('path')
                            if item_path == path:
                                bar_items.pop(i)
                                self.bookmark_bar.save_bookmarks()
                                self.bookmark_bar.refresh_bookmarks()
                                logger.info(f"Removed '{path}' from bookmark bar")
                                removed_from_source = True
                                break
            
            # If from Quick Links sidebar (top level), remove from items list
            if not removed_from_source and source_category in ('__QUICK_LINKS__', '__CONTAINER__'):
                items = self.custom_quick_links.get('items', [])
                for i, item in enumerate(items):
                    if item.get('type') == 'bookmark':
                        item_path = item.get('path') or item.get('data', {}).get('path')
                        if item_path == path:
                            items.pop(i)
                            logger.info(f"Removed '{path}' from Quick Links sidebar")
                            removed_from_source = True
                            break
            
            # Check Quick Links categories
            if not removed_from_source and source_category and source_category not in ('__QUICK_LINKS__', '__CONTAINER__', '__BAR__', ''):
                categories = self.custom_quick_links.get('categories', {})
                if source_category in categories:
                    category_items = categories[source_category]
                    for i, item in enumerate(category_items):
                        if item.get('path') == path:
                            category_items.pop(i)
                            logger.info(f"Removed '{path}' from Quick Links category '{source_category}'")
                            removed_from_source = True
                            break
                
                # If not found in Quick Links categories, check bookmark bar categories
                if not removed_from_source and hasattr(self, 'bookmark_bar') and self.bookmark_bar:
                    bar_categories = self.bookmark_bar.bookmarks_data.get('categories', {})
                    if source_category in bar_categories:
                        bar_category_items = bar_categories[source_category]
                        for i, item in enumerate(bar_category_items):
                            if item.get('path') == path:
                                bar_category_items.pop(i)
                                self.bookmark_bar.save_bookmarks()
                                self.bookmark_bar.refresh_bookmarks()
                                logger.info(f"Removed '{path}' from bookmark bar category '{source_category}'")
                                removed_from_source = True
                                break
            
            self.save_quick_links()
            self.refresh_quick_links_list()
            logger.info(f"Added '{path}' to category '{category_name}'")
    
    def _on_category_moved_out(self, category_name, category_data):
        """Handle category being dragged out of Quick Links"""
        # This is called when the category is being moved elsewhere
        # The actual removal happens when the drop is accepted
        pass
    
    def refresh_quick_links(self):
        """Refresh the Quick Links panel"""
        self.refresh_quick_links_list()
    
    def on_quick_links_reordered(self, new_order):
        """Handle Quick Links reorder via drag-drop"""
        # Convert the new_order (list of paths) back to structured items
        new_items = []
        for path in new_order:
            new_items.append({
                'type': 'bookmark',
                'data': {
                    'name': Path(path).name,
                    'path': path,
                    'type': 'folder' if Path(path).is_dir() else 'file'
                }
            })
        
        # Keep categories at the end (after the reordered bookmarks)
        for item in self.custom_quick_links.get('items', []):
            if item.get('type') == 'category':
                new_items.append(item)
        
        self.custom_quick_links['items'] = new_items
        self.save_quick_links()
        self.refresh_quick_links_list()
    
    def on_bookmark_dropped_to_quick_links(self, bookmark):
        """Handle bookmark dropped into Quick Links panel"""
        path = bookmark.get('path', '')
        drop_index = bookmark.get('_drop_index', -1)  # Position to insert at
        # Check both _source_category (set by drop handler) and source_category (fallback)
        source_category = bookmark.get('_source_category', bookmark.get('source_category', ''))
        source_location = bookmark.get('source_location', '')
        source = bookmark.get('source', '')  # e.g., 'quick_links_category', 'bar_category'
        
        logger.debug(f"on_bookmark_dropped_to_quick_links: path={path}, source_category={source_category}, source_location={source_location}, source={source}, drop_index={drop_index}")
        
        if not path:
            return
        
        # Check if already exists at top level (not in a category)
        already_at_top_level = False
        for item in self.custom_quick_links.get('items', []):
            if item.get('type') == 'bookmark':
                item_path = item.get('path') or item.get('data', {}).get('path')
                if item_path == path:
                    already_at_top_level = True
                    break
        
        # Determine the source type
        is_from_bar = source_location == 'bar' or source == 'bar_category' or (source_category in ('__BAR__', '__CONTAINER__') and source_location != 'sidebar')
        is_from_sidebar_category = source == 'quick_links_category' or (source_category and source_category not in ('__QUICK_LINKS__', '__CONTAINER__', '__BAR__', '') and source != 'bar_category')
        is_from_bar_category = source == 'bar_category'
        
        # If coming from somewhere else and not already at top level, move it
        if (is_from_bar or is_from_sidebar_category or is_from_bar_category) and not already_at_top_level:
            # IMPORTANT: Remove from source FIRST (before add check)
            # This is because is_path_in_quick_links checks categories too
            removed_from_source = False
            
            # Check if from bookmark bar directly (top level, not a category)
            if is_from_bar and not is_from_bar_category and hasattr(self, 'bookmark_bar') and self.bookmark_bar:
                bar_items = self.bookmark_bar.bookmarks_data.get('bar_items', [])
                for i, item in enumerate(bar_items):
                    if item.get('type') == 'bookmark':
                        item_path = item.get('path') or item.get('data', {}).get('path')
                        if item_path == path:
                            bar_items.pop(i)
                            self.bookmark_bar.save_bookmarks()
                            self.bookmark_bar.refresh_bookmarks()
                            logger.info(f"Removed '{path}' from bookmark bar")
                            removed_from_source = True
                            break
            
            # Try Quick Links categories (sidebar categories)
            if not removed_from_source and is_from_sidebar_category:
                categories = self.custom_quick_links.get('categories', {})
                if source_category in categories:
                    category_items = categories[source_category]
                    for i, item in enumerate(category_items):
                        if item.get('path') == path:
                            category_items.pop(i)
                            removed_from_source = True
                            logger.info(f"Removed from Quick Links category '{source_category}'")
                            break
            
            # If from bookmark bar category
            if not removed_from_source and is_from_bar_category and hasattr(self, 'bookmark_bar') and self.bookmark_bar:
                bar_categories = self.bookmark_bar.bookmarks_data.get('categories', {})
                if source_category in bar_categories:
                    bar_category_items = bar_categories[source_category]
                    for i, item in enumerate(bar_category_items):
                        if item.get('path') == path:
                            bar_category_items.pop(i)
                            self.bookmark_bar.save_bookmarks()
                            self.bookmark_bar.refresh_bookmarks()
                            logger.info(f"Removed from bookmark bar category '{source_category}'")
                            removed_from_source = True
                            break
            
            # NOW add to sidebar at specified position (after removing from source)
            self.add_to_quick_links(path, insert_at=drop_index)
            logger.info(f"Added bookmark '{bookmark.get('name', path)}' to Quick Links sidebar at position {drop_index}")
            
            self.save_quick_links()
            self.refresh_quick_links_list()
        elif not self.is_path_in_quick_links(path):
            # New item from outside Quick Links entirely
            self.add_to_quick_links(path, insert_at=drop_index)
            logger.info(f"Added bookmark '{bookmark.get('name', path)}' to Quick Links at position {drop_index}")
    
    def on_file_dropped_to_quick_links(self, path):
        """Handle file/folder dropped into Quick Links panel from details view"""
        # Check if path is a dict with _drop_index
        if isinstance(path, dict):
            drop_index = path.get('_drop_index', -1)
            actual_path = path.get('path', '')
        else:
            drop_index = -1
            actual_path = path
        
        if actual_path and not self.is_path_in_quick_links(actual_path):
            self.add_to_quick_links(actual_path, insert_at=drop_index)
            logger.info(f"Added file '{actual_path}' to Quick Links at position {drop_index}")
    
    def on_category_dropped_to_quick_links(self, category_data):
        """Handle category dropped into Quick Links panel (MOVE from bookmark bar)"""
        category_name = category_data.get('name', '')
        category_items = category_data.get('items', [])
        source = category_data.get('source', '')
        drop_index = category_data.get('_drop_index', -1)  # Position to insert at
        category_color = category_data.get('color', None)  # Get color from drag data
        
        if not category_name:
            return
        
        # Check if category already exists in Quick Links
        if category_name in self.custom_quick_links.get('categories', {}):
            logger.warning(f"Category '{category_name}' already exists in Quick Links")
            return
        
        # Add category to Quick Links at the specified position
        self.add_category_to_quick_links(category_name, category_items, insert_at=drop_index)
        
        # Transfer color if present
        if category_color:
            if 'category_colors' not in self.custom_quick_links:
                self.custom_quick_links['category_colors'] = {}
            self.custom_quick_links['category_colors'][category_name] = category_color
            self.save_quick_links()
        
        # If it came from bookmark bar, remove it from there (MOVE semantics)
        if source == 'bookmark_bar' and hasattr(self, 'bookmark_bar'):
            self._remove_category_from_bookmark_bar(category_name)
        
        self.refresh_quick_links_list()
        logger.info(f"Moved category '{category_name}' to Quick Links at position {drop_index}")
    
    def _remove_category_from_bookmark_bar(self, category_name):
        """Remove a category from the bookmark bar (after moving to Quick Links)"""
        if not hasattr(self, 'bookmark_bar'):
            return
        
        bookmarks_data = self.bookmark_bar.bookmarks_data
        
        # Remove from categories dict
        if category_name in bookmarks_data.get('categories', {}):
            del bookmarks_data['categories'][category_name]
        
        # Remove color (it's been transferred to Quick Links)
        category_colors = bookmarks_data.get('category_colors', {})
        if category_name in category_colors:
            del category_colors[category_name]
        
        # Remove from bar_items
        bar_items = bookmarks_data.get('bar_items', [])
        for i, item in enumerate(bar_items):
            if item.get('type') == 'category' and item.get('name') == category_name:
                bar_items.pop(i)
                break
        
        self.bookmark_bar.save_bookmarks()
        self.bookmark_bar.refresh_bookmarks()
    
    def on_quick_link_clicked(self, item):
        """Handle single click on quick link - navigate to folder or select file"""
        path_str = item.data(Qt.ItemDataRole.UserRole)
        if path_str:
            path = Path(path_str)
            if path.is_dir():
                self.navigate_to_path(path_str)
    
    def on_quick_link_double_clicked(self, item):
        """Handle double click on quick link - open the item"""
        path_str = item.data(Qt.ItemDataRole.UserRole)
        if path_str:
            path = Path(path_str)
            if path.is_file():
                self.open_file(path_str)
            else:
                self.navigate_to_path(path_str)
    
    def toggle_dual_pane(self):
        """Toggle the Quick Links panel on/off"""
        self.dual_pane_active = not self.dual_pane_active
        
        if hasattr(self, 'tree_panel_2'):
            self.tree_panel_2.setVisible(self.dual_pane_active)
            
            # Refresh quick links when showing
            if self.dual_pane_active:
                self.refresh_quick_links()
            
            # Adjust splitter sizes when toggling
            # IMPORTANT: Preserve the left panel width
            current_sizes = self.main_splitter.sizes()
            left_width = current_sizes[0] if current_sizes else 300  # Keep current left width
            
            if self.dual_pane_active:
                # Three panes: left tree (keep size), details (middle), right quick links
                # Use saved right panel width if available, otherwise calculate
                saved_right = self.panel_widths.get('right_panel', 0)
                if saved_right > 0:
                    right_width = saved_right
                    middle_width = self.main_splitter.width() - left_width - right_width
                else:
                    total_available = self.main_splitter.width() - left_width
                    right_width = max(200, int(total_available * 0.25))  # At least 200px or 25% for Quick Links
                    middle_width = total_available - right_width  # Rest goes to details
                self.main_splitter.setSizes([left_width, middle_width, right_width])
            else:
                # Two panes: left tree (keep size), details (take rest)
                details_width = self.main_splitter.width() - left_width
                self.main_splitter.setSizes([left_width, details_width, 0])
            
            # Save visibility state
            self.panel_widths['quick_links_visible'] = self.dual_pane_active
            self.save_panel_widths()
        
        print(f"Dual pane {'enabled' if self.dual_pane_active else 'disabled'}")
    
    def _replace_views_with_navigable(self):
        """Replace parent's QTreeView instances with NavigableTreeView"""
        from suiteview.ui.file_explorer_core import NoFocusDelegate
        
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
        
        # Copy stylesheet from old tree view
        new_tree.setStyleSheet(old_tree.styleSheet())
        
        # Apply NoFocusDelegate to remove focus rectangle
        new_tree.setItemDelegate(NoFocusDelegate(new_tree))
        
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

        # Preserve styling and remove the focus rectangle on selected items.
        # (Without this, Windows styles can draw a visible focus "halo" around the text.)
        new_details.setStyleSheet(old_details.styleSheet())
        new_details.setItemDelegate(NoFocusDelegate(new_details))
        
        # Copy sort column and order from old view (default to Name ascending)
        old_header = old_details.header()
        sort_column = old_header.sortIndicatorSection()
        sort_order = old_header.sortIndicatorOrder()
        new_details.sortByColumn(sort_column, sort_order)
        
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
        
        # Connect drag/drop signals for tree view (left panel)
        self.tree_view.set_file_explorer(self)
        self.tree_view.files_dropped.connect(self.handle_dropped_files)
        
        # Connect drag/drop signals for details view (middle panel)
        self.details_view.set_file_explorer(self)
        self.details_view.files_dropped.connect(self.handle_dropped_files)
        
        # Reinstall event filter for keyboard shortcuts (F2, Delete, Ctrl+C/V/X)
        self.details_view.installEventFilter(self)
    
    def insert_breadcrumb_bar(self):
        """Insert breadcrumb navigation bar above the tree"""
        # Get the main layout
        main_layout = self.layout()
        
        # Create breadcrumb widget with fixed height
        self.breadcrumb_frame = QFrame()
        self.breadcrumb_frame.setObjectName("breadcrumbFrame")
        self.breadcrumb_frame.setFrameShape(QFrame.Shape.StyledPanel)
        self.breadcrumb_frame.setFixedHeight(32)  # Fixed height for breadcrumb bar
        self.breadcrumb_frame.setStyleSheet("""
            QFrame#breadcrumbFrame {
                background-color: #FFFDE7;
                border: 2px solid #6B8DC9;
                border-radius: 4px;
            }
            QFrame#breadcrumbFrame:hover {
                border-color: #2563EB;
            }
        """)
        
        breadcrumb_layout = QHBoxLayout(self.breadcrumb_frame)
        breadcrumb_layout.setContentsMargins(4, 3, 4, 3)
        breadcrumb_layout.setSpacing(4)

        # History panel toggle button (left of navigation buttons)
        history_icon = self.style().standardIcon(QStyle.StandardPixmap.SP_FileDialogContentsView)
        self.history_btn = QPushButton()
        self.history_btn.setIcon(history_icon)
        self.history_btn.setToolTip("Toggle History Panel")
        self.history_btn.setFixedSize(24, 24)
        self.history_btn.setCheckable(True)
        self.history_btn.setStyleSheet("""
            QPushButton {
                background-color: #E0ECFF;
                border: 1px solid #2563EB;
                border-radius: 4px;
            }
            QPushButton:hover {
                background-color: #C9DAFF;
            }
            QPushButton:checked {
                background-color: #1E3A8A;
                border: 1px solid #FFD700;
            }
        """)
        self.history_btn.clicked.connect(self.toggle_history_panel)
        breadcrumb_layout.addWidget(self.history_btn)
        
        # Back button
        back_icon = self.style().standardIcon(QStyle.StandardPixmap.SP_ArrowBack)
        self.back_btn = self._create_nav_button(back_icon, "Go Back (Alt+Left)", self.navigate_back)
        breadcrumb_layout.addWidget(self.back_btn)
        
        # Forward button
        forward_icon = self.style().standardIcon(QStyle.StandardPixmap.SP_ArrowForward)
        self.forward_btn = self._create_nav_button(forward_icon, "Go Forward (Alt+Right)", self.navigate_forward)
        breadcrumb_layout.addWidget(self.forward_btn)
        
        # Up/Back button
        up_icon = self.style().standardIcon(QStyle.StandardPixmap.SP_ArrowUp)
        self.up_btn = self._create_nav_button(up_icon, "Go Up One Level", self.go_up_one_level)
        breadcrumb_layout.addWidget(self.up_btn)
        
        # Refresh button
        refresh_icon = self.style().standardIcon(QStyle.StandardPixmap.SP_BrowserReload)
        self.refresh_btn = self._create_nav_button(refresh_icon, "Refresh Folder (F5)", self.refresh_current_folder)
        breadcrumb_layout.addWidget(self.refresh_btn)
        
        # Clickable breadcrumb widget
        self.breadcrumb_widget = ClickableBreadcrumb()
        self.breadcrumb_widget.path_clicked.connect(self.navigate_to_path)
        breadcrumb_layout.addWidget(self.breadcrumb_widget, 1)
        
        # Dual pane toggle button
        self.dual_pane_btn = QPushButton()
        self.dual_pane_btn.setToolTip("Toggle Dual Pane View")
        self.dual_pane_btn.setFixedSize(24, 24)
        self.dual_pane_btn.setCheckable(True)
        list_icon = self.style().standardIcon(QStyle.StandardPixmap.SP_FileDialogListView)
        self.dual_pane_btn.setIcon(list_icon)
        self.dual_pane_btn.setIconSize(QSize(14, 14))
        self.dual_pane_btn.setStyleSheet("""
            QPushButton {
                background-color: #E0ECFF;
                border: 1px solid #2563EB;
                border-radius: 4px;
                color: #0A1E5E;
            }
            QPushButton:hover {
                background-color: #C9DAFF;
            }
            QPushButton:checked {
                background-color: #1E3A8A;
                border: 1px solid #FFD700;
            }
        """)
        self.dual_pane_btn.clicked.connect(self.toggle_dual_pane)
        # Set initial checked state based on restored visibility
        self.dual_pane_btn.setChecked(self.dual_pane_active)
        breadcrumb_layout.addWidget(self.dual_pane_btn)
        
        # Insert at position 2 (after toolbar and bookmark bar)
        # Order: toolbar(0), bookmark_bar(1), breadcrumb(2), splitter(3)
        main_layout.insertWidget(2, self.breadcrumb_frame)
        
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
    
    def _apply_depth_search_locked_style(self, locked: bool = False) -> None:
        """Override to change breadcrumb bar color when depth search is locked."""
        if not hasattr(self, 'breadcrumb_frame'):
            return
        
        if locked:
            # Red background when depth search is locked
            self.breadcrumb_frame.setStyleSheet("""
                QFrame#breadcrumbFrame {
                    background-color: #FFCCCC;
                    border: 2px solid #CC4444;
                    border-radius: 4px;
                }
            """)
            # Also update the breadcrumb widget inside
            if hasattr(self, 'breadcrumb_widget'):
                self.breadcrumb_widget.setStyleSheet("""
                    ClickableBreadcrumb {
                        background-color: #FFCCCC;
                        border: none;
                        padding: 1px;
                    }
                """)
                self.breadcrumb_widget.breadcrumb_display.setStyleSheet("background-color: #FFCCCC;")
        else:
            # Normal yellow background
            self.breadcrumb_frame.setStyleSheet("""
                QFrame#breadcrumbFrame {
                    background-color: #FFFDE7;
                    border: 2px solid #6B8DC9;
                    border-radius: 4px;
                }
                QFrame#breadcrumbFrame:hover {
                    border-color: #2563EB;
                }
            """)
            # Restore breadcrumb widget style
            if hasattr(self, 'breadcrumb_widget'):
                self.breadcrumb_widget.setStyleSheet("""
                    ClickableBreadcrumb {
                        background-color: #FFFDE7;
                        border: 2px solid #6B8DC9;
                        border-radius: 3px;
                        padding: 1px;
                    }
                    ClickableBreadcrumb:hover {
                        border-color: #2563EB;
                    }
                """)
                self.breadcrumb_widget.breadcrumb_display.setStyleSheet("background-color: #FFFDE7;")
    
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
                # Current Path History - browser-style with truncation
                # If we're not at the end, truncate everything after current position
                if self.current_path_index < len(self.current_path_history) - 1:
                    self.current_path_history = self.current_path_history[:self.current_path_index + 1]
                
                # Add new path if different from current
                if not self.current_path_history or self.current_path_history[-1] != path_str:
                    self.current_path_history.append(path_str)
                    self.current_path_index = len(self.current_path_history) - 1
                
                # Full History - always append, never truncate
                if not self.full_history or self.full_history[-1] != path_str:
                    self.full_history.append(path_str)
                
                print(f"Added to history: {path_str}")
                print(f"Current Path: {self.current_path_history}, index={self.current_path_index}")
                print(f"Full History: {self.full_history}")
            
            # Update breadcrumb
            self.update_breadcrumb(path_str)
            
            # Update navigation button states
            self._update_nav_button_states()
            
            # Load in the details pane (right side) instead of tree
            self.load_folder_contents_in_details(path_obj)
            
        except Exception as e:
            logger.error(f"Failed to navigate to {path}: {e}")
    
    def _update_nav_button_states(self):
        """Update enabled/disabled state of back/forward buttons based on current path history"""
        if hasattr(self, 'back_btn'):
            self.back_btn.setEnabled(self.current_path_index > 0)
        if hasattr(self, 'forward_btn'):
            self.forward_btn.setEnabled(self.current_path_index < len(self.current_path_history) - 1)
        # Update history panel if visible
        if hasattr(self, 'history_panel') and self.history_panel.isVisible():
            self._update_history_panel()
    
    def toggle_history_panel(self):
        """Toggle the history panel on/off"""
        if not hasattr(self, 'history_panel'):
            self._create_history_panel()
        
        if self.history_panel.isVisible():
            self.history_panel.hide()
            self.history_btn.setChecked(False)
        else:
            self._update_history_panel()
            self.history_panel.show()
            self.history_btn.setChecked(True)
    
    def _create_history_panel(self):
        """Create the history panel widget"""
        from PyQt6.QtWidgets import QListWidget, QListWidgetItem, QButtonGroup, QToolButton
        
        # Create panel frame
        self.history_panel = QFrame(self)
        self.history_panel.setFrameShape(QFrame.Shape.StyledPanel)
        self.history_panel.setStyleSheet("""
            QFrame {
                background-color: #FFFDE7;
                border: 1px solid #94BBD9;
                border-radius: 4px;
            }
        """)
        
        panel_layout = QVBoxLayout(self.history_panel)
        panel_layout.setContentsMargins(6, 4, 6, 6)
        panel_layout.setSpacing(4)
        
        # Header with close button
        header_layout = QHBoxLayout()
        header_layout.setContentsMargins(0, 0, 0, 0)
        header_label = QLabel("History")
        header_label.setStyleSheet(
            "font-weight: bold; font-size: 11px; color: #1A3A6E; background: transparent; border: none; padding: 0px; margin: 0px;"
        )
        header_layout.addWidget(header_label)
        header_layout.addStretch()
        
        # Close button
        close_btn = QToolButton()
        close_btn.setText("x")
        close_btn.setFixedSize(18, 18)
        close_btn.setToolTip("Close")
        close_btn.setStyleSheet("""
            QToolButton {
                background-color: transparent;
                border: none;
                font-size: 12px;
                font-weight: bold;
                color: #B00020;
                padding: 0px;
                margin: 0px;
            }
            QToolButton:hover {
                background-color: rgba(176, 0, 32, 0.12);
                border-radius: 3px;
            }
        """)
        close_btn.clicked.connect(lambda: (self.history_panel.hide(), self.history_btn.setChecked(False)))
        header_layout.addWidget(close_btn)
        panel_layout.addLayout(header_layout)
        
        # Toggle buttons for Current Path vs Full History
        toggle_layout = QHBoxLayout()
        toggle_layout.setSpacing(2)
        
        toggle_btn_style = """
            QPushButton {
                background-color: transparent;
                border: 1px solid #94BBD9;
                border-radius: 3px;
                padding: 3px 6px;
                font-size: 9px;
                color: #1A3A6E;
            }
            QPushButton:hover {
                background-color: #C0DAF0;
            }
            QPushButton:checked {
                background-color: #1A3A6E;
                color: white;
                border: 1px solid #1A3A6E;
            }
        """
        
        self.current_path_btn = QPushButton("Current Path")
        self.current_path_btn.setCheckable(True)
        self.current_path_btn.setChecked(True)
        self.current_path_btn.setStyleSheet(toggle_btn_style)
        self.current_path_btn.clicked.connect(lambda: self._set_history_view("current_path"))
        toggle_layout.addWidget(self.current_path_btn)
        
        self.full_history_btn = QPushButton("Full History")
        self.full_history_btn.setCheckable(True)
        self.full_history_btn.setStyleSheet(toggle_btn_style)
        self.full_history_btn.clicked.connect(lambda: self._set_history_view("full_history"))
        toggle_layout.addWidget(self.full_history_btn)
        
        panel_layout.addLayout(toggle_layout)
        
        # History list
        self.history_list = QListWidget()
        self.history_list.setStyleSheet("""
            QListWidget {
                background-color: transparent;
                border: none;
                font-size: 10px;
            }
            QListWidget::item {
                padding: 4px 8px;
                border-bottom: 1px solid #A8C8E8;
                background: transparent;
            }
            QListWidget::item:selected {
                background-color: #A0C4E8;
                color: #1A3A6E;
            }
            QListWidget::item:hover {
                background-color: #C0DAF0;
            }
        """)
        self.history_list.itemClicked.connect(self._on_history_item_clicked)
        panel_layout.addWidget(self.history_list)
        
        # Clear button
        clear_btn = QPushButton("Clear")
        clear_btn.setStyleSheet("""
            QPushButton {
                background-color: transparent;
                border: 1px solid #94BBD9;
                border-radius: 3px;
                padding: 4px 8px;
                font-size: 10px;
                color: #0066cc;
                font-weight: 500;
            }
            QPushButton:hover {
                background-color: #B8D4EC;
            }
        """)
        clear_btn.clicked.connect(self._clear_history)
        panel_layout.addWidget(clear_btn)
        
        # Position panel on the left side
        self.history_panel.setFixedWidth(200)
        self.history_panel.hide()
        
        # Insert into main layout at the left
        main_layout = self.layout()
        # Find the splitter and insert panel before it
        for i in range(main_layout.count()):
            widget = main_layout.itemAt(i).widget()
            if isinstance(widget, QSplitter):
                # Create a horizontal layout to hold history panel and splitter
                container = QWidget()
                container_layout = QHBoxLayout(container)
                container_layout.setContentsMargins(0, 0, 0, 0)
                container_layout.setSpacing(4)
                
                # Add history panel
                container_layout.addWidget(self.history_panel)
                
                # Move splitter to container
                main_layout.removeWidget(widget)
                container_layout.addWidget(widget)
                
                # Add container back to main layout
                main_layout.insertWidget(i, container)
                break
    
    def _set_history_view(self, mode):
        """Switch between current path and full history views"""
        self.history_view_mode = mode
        
        # Update button states
        self.current_path_btn.setChecked(mode == "current_path")
        self.full_history_btn.setChecked(mode == "full_history")
        
        # Refresh the list
        self._update_history_panel()
    
    def _update_history_panel(self):
        """Update the history list widget with current history"""
        if not hasattr(self, 'history_list'):
            return
        
        self.history_list.clear()
        
        # Choose which history to display
        if self.history_view_mode == "current_path":
            history = self.current_path_history
            current_index = self.current_path_index
        else:
            history = self.full_history
            current_index = len(self.full_history) - 1 if self.full_history else -1
        
        if not history:
            item = QListWidgetItem("No history yet")
            item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEnabled)
            self.history_list.addItem(item)
            return
        
        # Show history with most recent at top
        for i, path in enumerate(reversed(history)):
            actual_index = len(history) - 1 - i
            path_obj = Path(path)
            
            # Create display name (folder name or drive letter)
            if path_obj.name:
                display_name = path_obj.name
            else:
                display_name = str(path_obj)
            
            # Mark current position (only for current path view)
            if self.history_view_mode == "current_path" and actual_index == current_index:
                display_name = f"● {display_name}"
            
            item = QListWidgetItem(display_name)
            item.setToolTip(path)
            item.setData(Qt.ItemDataRole.UserRole, actual_index)
            self.history_list.addItem(item)
    
    def _on_history_item_clicked(self, item):
        """Handle click on history list item"""
        index = item.data(Qt.ItemDataRole.UserRole)
        if index is None:
            return
        
        if self.history_view_mode == "current_path":
            # Current Path view: jump to that position (like back/forward)
            if 0 <= index < len(self.current_path_history):
                self.current_path_index = index
                path = self.current_path_history[index]
                # Also add to full history
                if not self.full_history or self.full_history[-1] != path:
                    self.full_history.append(path)
                self.navigate_to_path(path, add_to_history=False)
        else:
            # Full History view: navigate there as a new entry
            if 0 <= index < len(self.full_history):
                path = self.full_history[index]
                self.navigate_to_path(path, add_to_history=True)
                
    def _jump_to_history_index(self, index):
        """Jump to a specific index in the current path history"""
        if 0 <= index < len(self.current_path_history):
            self.current_path_index = index
            path = self.current_path_history[index]
            self.navigate_to_path(path, add_to_history=False)
    
    def _clear_history(self):
        """Clear navigation history based on current view mode"""
        if self.history_view_mode == "current_path":
            # Clear current path, keep only current location
            if self.current_path_history and 0 <= self.current_path_index < len(self.current_path_history):
                current = self.current_path_history[self.current_path_index]
                self.current_path_history = [current]
                self.current_path_index = 0
            else:
                self.current_path_history = []
                self.current_path_index = -1
        else:
            # Clear full history, keep only current location
            if self.current_path_history and 0 <= self.current_path_index < len(self.current_path_history):
                current = self.current_path_history[self.current_path_index]
                self.full_history = [current]
            else:
                self.full_history = []
        self._update_nav_button_states()
    
    def navigate_back(self):
        """Navigate to previous folder in current path history"""
        print(f"navigate_back called: index={self.current_path_index}, history={self.current_path_history}")
        if self.current_path_index > 0:
            self.current_path_index -= 1
            path = self.current_path_history[self.current_path_index]
            print(f"Going back to: {path}")
            # Also add to full history
            if not self.full_history or self.full_history[-1] != path:
                self.full_history.append(path)
            self.navigate_to_path(path, add_to_history=False)
        else:
            print("Already at beginning of history")
    
    def navigate_forward(self):
        """Navigate to next folder in current path history"""
        print(f"navigate_forward called: index={self.current_path_index}, history={self.current_path_history}")
        if self.current_path_index < len(self.current_path_history) - 1:
            self.current_path_index += 1
            path = self.current_path_history[self.current_path_index]
            print(f"Going forward to: {path}")
            # Also add to full history
            if not self.full_history or self.full_history[-1] != path:
                self.full_history.append(path)
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
        
        # Handle .lnk shortcut files - resolve target and navigate if it's a folder
        if path_obj.suffix.lower() == '.lnk' and path_obj.is_file():
            target_path = self._resolve_shortcut(str(path_obj))
            if target_path:
                target_obj = Path(target_path)
                if target_obj.exists() and target_obj.is_dir():
                    # Navigate to the folder target within File Nav (with history tracking)
                    print(f"Shortcut resolves to folder: {target_obj}")
                    self.navigate_to_path(target_obj, add_to_history=True)
                    return
                elif target_obj.exists() and target_obj.is_file():
                    # Shortcut points to a file, open it
                    print(f"Shortcut resolves to file: {target_obj}")
                    try:
                        if os.name == 'nt':
                            os.startfile(str(target_obj))
                        elif sys.platform == 'darwin':
                            subprocess.run(['open', str(target_obj)])
                        else:
                            subprocess.run(['xdg-open', str(target_obj)])
                    except Exception as e:
                        logger.error(f"Failed to open file: {e}")
                        from PyQt6.QtWidgets import QMessageBox
                        QMessageBox.warning(self, "Cannot Open File", f"Failed to open {target_obj.name}\n\nError: {str(e)}")
                    return
            # If we can't resolve, fall through to open the .lnk file itself
        
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
            # Use navigate_to_path which handles history
            self.navigate_to_path(parent_path)
    
    def refresh_current_folder(self):
        """Refresh the current folder contents"""
        if hasattr(self, 'current_details_folder') and self.current_details_folder:
            # Refresh without adding to history
            self.load_folder_contents_in_details(Path(self.current_details_folder))
    
    def on_tree_item_clicked(self, index):
        """Override parent method to use navigate_to_path for history tracking"""
        # Get the path from the clicked item
        item = self.model.itemFromIndex(index)
        if not item:
            return
        
        path = item.data(Qt.ItemDataRole.UserRole)
        if path:
            # Use navigate_to_path which handles history
            self.navigate_to_path(path)
    
    def navigate_to_bookmark_folder(self, folder_path):
        """Override parent method to use navigate_to_path for history tracking"""
        # Use navigate_to_path which handles history
        self.navigate_to_path(folder_path)
    
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
        
        # Create header bar (app-level header above tabs)
        header_widget = QWidget()
        header_widget.setFixedHeight(8)
        header_widget.setStyleSheet("""
            QWidget {
                background-color: #1E5BA8;
            }
        """)
        layout.addWidget(header_widget)
        
        # Create tab widget
        self.tab_widget = QTabWidget()
        self.tab_widget.setTabsClosable(True)
        self.tab_widget.setMovable(True)
        self.tab_widget.setDocumentMode(True)
        self.tab_widget.setStyleSheet("""
            QTabWidget::pane {
                border: 1px solid #B0C8E8;
                background-color: #E8F0FF;
            }
            QTabBar {
                background-color: #F5F8FC;
            }
            QTabBar::tab {
                padding: 8px 16px;
                margin-right: 2px;
                background-color: #D8E8FF;
                color: #0A1E5E;
                font-weight: 600;
                font-size: 11px;
                border: 1px solid #B0C8E8;
                border-bottom: none;
            }
            QTabBar::tab:selected {
                background-color: #6BA3E8;
                border-bottom: 3px solid #FFD700;
                color: #0A1E5E;
            }
            QTabBar::tab:!selected {
                background-color: #D8E8FF;
                color: #5a6c7d;
            }
            QTabBar::tab:hover {
                background-color: #C8DFFF;
            }
        """)
        self.tab_widget.tabBar().setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.tab_widget.tabBar().customContextMenuRequested.connect(self.show_tab_bar_context_menu)
        
        # Tab bar controls
        self.tab_widget.tabCloseRequested.connect(self.close_tab)
        
        layout.addWidget(self.tab_widget)
        
        # Keyboard shortcuts (TODO: implement)
        # Ctrl+T: New tab
        # Ctrl+W: Close tab
        # Ctrl+Tab: Next tab
        # Ctrl+Shift+Tab: Previous tab
    
    def show_tab_bar_context_menu(self, pos):
        """Show context menu for the tab bar.

        - Right-click a tab: offer Duplicate (open new tab at same folder)
        - Right-click empty space: offer New Tab
        """
        tab_bar = self.tab_widget.tabBar()
        tab_index = tab_bar.tabAt(pos)

        menu = QMenu(self)
        if tab_index >= 0:
            duplicate_action = QAction("Duplicate", self)
            duplicate_action.triggered.connect(lambda _: self.duplicate_tab(tab_index))
            menu.addAction(duplicate_action)
        else:
            new_tab_action = QAction("New Tab", self)
            new_tab_action.triggered.connect(lambda _: self.add_new_tab())
            menu.addAction(new_tab_action)

        menu.exec(tab_bar.mapToGlobal(pos))

    def duplicate_tab(self, index: int) -> None:
        """Duplicate the given tab into a new tab at the same folder."""
        try:
            widget = self.tab_widget.widget(index)
            if widget is None:
                return

            # Prefer the tab's current directory (kept in sync with breadcrumb)
            path = getattr(widget, 'current_directory', None)
            if not path:
                path = getattr(widget, 'current_details_folder', None)

            title = self.tab_widget.tabText(index)
            self.add_new_tab(path=path, title=title)
        except Exception as e:
            logger.error(f"Failed to duplicate tab: {e}")

    def add_new_tab(self, path=None, title=None):
        """Add a new tab"""
        # Create new tab - if no path specified, navigate to OneDrive
        explorer_tab = FileExplorerTab(initial_path=path)
        
        # Determine tab title
        if title is None:
            if path:
                path_obj = Path(path)
                title = path_obj.name if path_obj.name else str(path)
            else:
                title = "OneDrive"
        
        # Add tab
        index = self.tab_widget.addTab(explorer_tab, title)
        self.tab_widget.setCurrentIndex(index)
        self._style_close_button(index)
        
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
        
        # Get the widget before removing it
        widget = self.tab_widget.widget(index)
        
        # Disconnect signals to prevent crashes during cleanup
        if widget:
            try:
                # Disconnect depth level combo signal to prevent it firing during deletion
                if hasattr(widget, 'depth_level_combo'):
                    widget.depth_level_combo.currentTextChanged.disconnect()
                
                # Disconnect path changed signal
                if hasattr(widget, 'path_changed'):
                    widget.path_changed.disconnect()
                
                # Disconnect other signals that might reference the widget
                if hasattr(widget, 'details_search'):
                    widget.details_search.textChanged.disconnect()
                
                # If depth search is enabled, turn it off before closing
                if hasattr(widget, 'depth_search_enabled') and widget.depth_search_enabled:
                    widget.depth_search_enabled = False
                    widget.depth_search_locked = False
                    widget.depth_search_active_results = None
                
            except Exception as e:
                logger.error(f"Error disconnecting signals during tab close: {e}")
        
        # Now remove the tab
        self.tab_widget.removeTab(index)
        
        # Delete the widget to free resources
        if widget:
            widget.deleteLater()
    
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

    def _style_close_button(self, index):
        """Make the tab close button a subtle gold X instead of the default red icon."""
        tab_bar = self.tab_widget.tabBar()
        close_btn = QToolButton(tab_bar)
        close_btn.setAutoRaise(True)
        close_btn.setText("X")
        close_btn.setToolTip("Close Tab")
        close_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        close_btn.setStyleSheet(
            """
            QToolButton {
                background: transparent;
                color: #FFD700;
                border: none;
                font-size: 12px;
                font-weight: 700;
                padding: 0px;
                min-width: 14px;
            }
            QToolButton:hover {
                color: #FFE066;
            }
            """
        )
        close_btn.clicked.connect(lambda _: self._emit_close_for_button(close_btn))
        tab_bar.setTabButton(index, QTabBar.ButtonPosition.RightSide, close_btn)

    def _emit_close_for_button(self, button):
        """Map custom close button clicks to the correct tab index."""
        tab_bar = self.tab_widget.tabBar()
        for idx in range(tab_bar.count()):
            if tab_bar.tabButton(idx, QTabBar.ButtonPosition.RightSide) is button:
                self.tab_widget.tabCloseRequested.emit(idx)
                return
