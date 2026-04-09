
"""
SuiteView - Main Application Window
File Navigator with Multi-Tab support, system tray integration, and access to all SuiteView tools
"""

import os
import sys
import subprocess
import json
import time
from pathlib import Path
from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QTabWidget, 
                              QPushButton, QLabel, QFrame, QMenu, QLineEdit, QTreeView, QStyle, QTabBar, QToolButton,
                              QListWidget, QListWidgetItem, QSplitter, QAbstractItemView, QScrollArea,
                              QSystemTrayIcon, QApplication, QSizePolicy, QComboBox, QMessageBox)
from PyQt6.QtCore import Qt, pyqtSignal, QEvent, QSize, QPoint, QRect
from PyQt6.QtGui import QAction, QCursor, QMouseEvent, QIcon, QPainter, QColor, QPen, QPixmap, QFont, QBrush

# Import the base FileExplorerCore
from suiteview.file_nav.file_explorer_core import FileExplorerCore, DropTreeView

# Import unified bookmark widgets for sidebar categories
from suiteview.ui.widgets.bookmark_widgets import (
    CategoryButton, CategoryPopup, CategoryBookmarkButton, BookmarkContainer,
    CATEGORY_BUTTON_STYLE_SIDEBAR, CONTEXT_MENU_STYLE, CATEGORY_CONTEXT_MENU_STYLE,
    set_footer_status_callback
)

import logging
logger = logging.getLogger(__name__)

from suiteview.messaging.message_service import MessageService
from suiteview.messaging.inbox_widget import MessageInbox

# DEV_MODE is True when running from source, False when running as a PyInstaller exe.
# Experimental features (PolView, Audit, Task Tracker, etc.) are only shown in DEV_MODE.
DEV_MODE = not getattr(sys, 'frozen', False)


class NavigableTreeView(DropTreeView):
    """Custom QTreeView that emits signals for back/forward mouse buttons and supports file drops"""
    
    back_button_clicked = pyqtSignal()
    forward_button_clicked = pyqtSignal()
    
    def mousePressEvent(self, event: QMouseEvent):
        """Override to catch back/forward mouse buttons"""
        if event.button() == Qt.MouseButton.XButton1:
            self.back_button_clicked.emit()
            event.accept()
            return
        elif event.button() == Qt.MouseButton.XButton2:
            self.forward_button_clicked.emit()
            event.accept()
            return
        
        # Pass other events to parent
        super().mousePressEvent(event)
    
    def mouseDoubleClickEvent(self, event: QMouseEvent):
        """Override to handle double-clicks"""
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
        
        # Allow tab content to shrink so window can collapse to just header bar
        self.setMinimumSize(0, 0)
        
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
        quick_links_panel.setMinimumWidth(50)  # Allow narrow width
        quick_links_panel.setMinimumHeight(0)  # Allow panel to collapse vertically
        quick_links_panel.setStyleSheet("background-color: #CCE5F8;")
        panel_layout = QVBoxLayout(quick_links_panel)
        panel_layout.setContentsMargins(0, 0, 0, 0)
        panel_layout.setSpacing(0)
        
        # Header widget with title and + button
        header_widget = QWidget()
        header_widget.setStyleSheet("""
            QWidget {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    stop:0 #1E5BA8, stop:0.5 #0D3A7A, stop:1 #082B5C);
                border: none;
            }
        """)
        header_layout = QHBoxLayout(header_widget)
        header_layout.setContentsMargins(12, 6, 8, 6)
        header_layout.setSpacing(4)
        
        # Add "Bookmarks" header label (PolView style)
        header_label = QLabel("BOOKMARKS")
        header_label.setStyleSheet("""
            QLabel {
                background: transparent;
                font-weight: 700;
                font-size: 10pt;
                color: #D4A017;
                text-transform: uppercase;
                letter-spacing: 1px;
            }
        """)
        header_layout.addWidget(header_label)
        header_layout.addStretch()
        
        # Add context menu to header for creating new categories
        header_widget.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        header_widget.customContextMenuRequested.connect(self._show_quick_links_panel_context_menu)
        panel_layout.addWidget(header_widget)
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
        # Note: Do NOT connect navigate_to_path here — _on_bookmark_clicked already
        # handles files (open) vs folders (navigate) properly. Connecting navigate_to_path
        # would cause file clicks to also navigate the Details panel to the file's parent folder.  
        
        # Connect drop signals for cross-container moves (preserves existing move logic)
        # Note: file_dropped is handled internally by BookmarkContainer._handle_file_drop
        self.bookmark_container.bookmark_dropped.connect(self.on_bookmark_dropped_to_quick_links)
        self.bookmark_container.category_dropped.connect(self.on_category_dropped_to_quick_links)
        
        # Add the container to the panel layout
        panel_layout.addWidget(self.bookmark_container, 1)  # stretch factor 1 to fill space
        
        # Add footer to sidebar panel for consistency with other panels
        self.sidebar_footer = QLabel("")
        self.sidebar_footer.setStyleSheet("""
            QLabel {
                background-color: #E0E0E0;
                padding: 2px 8px;
                font-size: 9pt;
                color: #555555;
                border: none;
                border-top: 1px solid #A0B8D8;
            }
        """)
        self.sidebar_footer.setFixedHeight(20)
        panel_layout.addWidget(self.sidebar_footer)
        
        # Store reference to items_layout for backwards compatibility with drop handlers
        self.quick_links_items_layout = self.bookmark_container.items_layout
        self.quick_links_scroll_content = self.bookmark_container.items_container
        
        # Update footer count after populating (BookmarkContainer auto-refreshes in __init__)
        self._update_sidebar_footer()
        
        # Add to the RIGHT side of the splitter (after details view)
        self.main_splitter.addWidget(quick_links_panel)
        
        # Set stretch factors: tree stays fixed, details stretches, bookmarks stays fixed
        # Index 0 = tree panel, Index 1 = details panel, Index 2 = quick links panel
        self.main_splitter.setStretchFactor(0, 0)  # Tree panel doesn't stretch
        self.main_splitter.setStretchFactor(1, 1)  # Details panel stretches on window resize
        self.main_splitter.setStretchFactor(2, 0)  # Quick links stays fixed width
        
        # Store reference to the panel (keep old name for compatibility)
        self.tree_panel_2 = quick_links_panel
        self.quick_links_panel = quick_links_panel
        
        # Restore panel visibility and sizes from saved state
        self.dual_pane_active = self.panel_widths.get('quick_links_visible', False)
        quick_links_panel.setVisible(self.dual_pane_active)
        
        # Restore all panel sizes (3rd = bookmarks, 4th = notes added later)
        saved_left = self.panel_widths.get('left_panel', 300)
        saved_middle = self.panel_widths.get('middle_panel', 700)
        saved_right = self.panel_widths.get('right_panel', 200)
        
        if self.dual_pane_active:
            self.main_splitter.setSizes([saved_left, saved_middle, saved_right, 0])
        else:
            # Quick links hidden - give its space to middle panel
            self.main_splitter.setSizes([saved_left, saved_middle + saved_right, 0, 0])
        
        # Connect the bookmark bar's sidebar toggle button to toggle_dual_pane
        if hasattr(self, 'bookmark_bar') and hasattr(self.bookmark_bar, 'sidebar_toggle_btn'):
            self.bookmark_bar.sidebar_toggle_btn.clicked.connect(self.toggle_dual_pane)
            # Set initial checked state based on restored visibility
            self.bookmark_bar.sidebar_toggle_btn.setChecked(self.dual_pane_active)

        # ── ScratchPad panel (4th splitter widget, index 3) ────────────
        from suiteview.scratchpad.scratchpad_panel import ScratchPadPanel
        self.scratchpad_panel = ScratchPadPanel(parent=self)
        self.scratchpad_panel.setVisible(False)
        self.scratchpad_panel.fullscreen_toggled.connect(self._on_scratchpad_fullscreen)
        self.main_splitter.addWidget(self.scratchpad_panel)
        self.main_splitter.setStretchFactor(3, 0)  # ScratchPad panel stays fixed width
        self.scratchpad_panel_active = self.panel_widths.get('scratchpad_visible', False)
        if self.scratchpad_panel_active:
            self.scratchpad_panel.setVisible(True)
            # Restore widths including scratchpad panel
            saved_scratchpad = self.panel_widths.get('scratchpad_panel', 220)
            sizes = self.main_splitter.sizes()
            if len(sizes) >= 4:
                sizes[3] = saved_scratchpad
                sizes[1] = max(100, sizes[1] - saved_scratchpad)
                self.main_splitter.setSizes(sizes)
    
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
            self._update_sidebar_footer()
        else:
            logger.warning("BookmarkContainer not available, cannot refresh quick links")
    
    def _update_sidebar_footer(self):
        """Update the sidebar footer with bookmark and category counts"""
        if not hasattr(self, 'sidebar_footer'):
            return
        
        try:
            # Count bookmarks and categories from the data store
            bookmark_count = 0
            category_count = 0
            
            if hasattr(self, 'custom_quick_links'):
                # Count items (new format: categories have nested items)
                items = self.custom_quick_links.get('items', [])
                for item in items:
                    if item.get('type') == 'bookmark':
                        bookmark_count += 1
                    elif item.get('type') == 'category':
                        category_count += 1
                        # Count bookmarks inside this category
                        bookmark_count += len(item.get('items', []))
            
            self.sidebar_footer.setText(f"{bookmark_count} bookmarks, {category_count} categories")
        except Exception as e:
            logger.error(f"Error updating sidebar footer: {e}")
            self.sidebar_footer.setText("")
    
    def _on_bookmark_clicked(self, path):
        """Handle click on bookmark button in Quick Links"""
        # Handle URLs first
        if path.startswith('http://') or path.startswith('https://'):
            import webbrowser
            webbrowser.open(path)
            return
        
        path_obj = Path(path)
        if path_obj.is_dir():
            self.navigate_to_path(path)
        elif path_obj.is_file():
            # Single click on file opens it
            self.open_file(path)
        else:
            from PyQt6.QtWidgets import QMessageBox
            QMessageBox.warning(
                self, "Bookmark Invalid",
                f"The bookmark path no longer exists:\n\n{path}\n\n"
                "The folder or file may have been renamed, moved, or deleted."
            )
    
    def _on_bookmark_double_clicked(self, path):
        """Handle double-click on bookmark button in Quick Links"""
        # Handle URLs first
        if path.startswith('http://') or path.startswith('https://'):
            import webbrowser
            webbrowser.open(path)
            return
        
        path_obj = Path(path)
        if not path_obj.exists():
            from PyQt6.QtWidgets import QMessageBox
            QMessageBox.warning(
                self, "Bookmark Invalid",
                f"The bookmark path no longer exists:\n\n{path}\n\n"
                "The folder or file may have been renamed, moved, or deleted."
            )
            return
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
            
            if self._bookmark_manager.find_category_by_name(new_name):
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
            
            # Check if category already exists (use new format - search items)
            if self._bookmark_manager.find_category_by_name(name):
                QMessageBox.warning(self, "Duplicate", f"Category '{name}' already exists.")
                return
            
            # Use BookmarkContainer's add_category method (new format)
            self.bookmark_container.add_category(name)
            self._update_sidebar_footer()
            logger.info(f"Created new category '{name}' in Quick Links")
    
    def _add_bookmark_to_sidebar(self):
        """Launch the Add Bookmark dialog to add a bookmark to the sidebar"""
        from suiteview.ui.dialogs.shortcuts_dialog import AddBookmarkDialog
        
        # Get current folder to pre-fill the dialog
        current_folder = getattr(self, 'current_details_folder', None)
        if not current_folder:
            current_folder = getattr(self, 'current_directory', None)
        
        # Get categories from the sidebar bookmark container (new format - from items)
        categories = [item.get('name') for item in self.custom_quick_links.get('items', [])
                      if item.get('type') == 'category']
        
        dialog = AddBookmarkDialog(categories, self)
        
        # Pre-fill path if we have a current folder
        if current_folder:
            dialog.path_input.setText(str(current_folder))
            path_obj = Path(current_folder)
            dialog.name_input.setText(path_obj.name or str(path_obj))
        
        if dialog.exec() == dialog.DialogCode.Accepted:
            data = dialog.get_bookmark_data()
            name = data.get('name', '')
            path = data.get('path', '')
            category = data.get('category')
            
            if not path:
                return
            
            # Check if already exists
            items = self.custom_quick_links.get('items', [])
            for item in items:
                if item.get('type') == 'bookmark':
                    if item.get('path') == path:
                        from PyQt6.QtWidgets import QMessageBox
                        QMessageBox.information(self, "Already Added", f"'{name}' is already in Bookmarks.")
                        return
            
            # Add to items
            if 'items' not in self.custom_quick_links:
                self.custom_quick_links['items'] = []
            
            # Determine bookmark type
            bm_type = 'folder'
            if path.startswith('http://') or path.startswith('https://'):
                bm_type = 'url'
            elif Path(path).exists() and Path(path).is_file():
                bm_type = 'file'
            
            from suiteview.ui.widgets.bookmark_data_manager import get_bookmark_manager
            new_bookmark = get_bookmark_manager().create_bookmark(
                name or Path(path).name,
                path
            )
            self.custom_quick_links['items'].append(new_bookmark)
            
            self.save_quick_links()
            self.refresh_quick_links_list()
            logger.info(f"Added '{name}' to Quick Links sidebar")
    
    def _remove_bookmark_from_quick_links(self, path):
        """Remove a bookmark from Quick Links"""
        if self._bookmark_manager.remove_bookmark_by_path(1, path):
            self.save_quick_links()
            self.refresh_quick_links_list()
    
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
                
                # Remove from source category (new format - categories have nested items)
                self._bookmark_manager.remove_bookmark_from_category_by_name(source_category, path)
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
        
        # Find the target category in the new format (categories are items with nested items)
        target_category = self._bookmark_manager.find_category_by_name(category_name)
        if not target_category:
            logger.warning(f"Target category '{category_name}' not found")
            return
        
        # Check if already in target category
        for item in target_category.get('items', []):
            if item.get('path') == path:
                return  # Already exists
        
        # Add to target category
        new_bookmark = self._bookmark_manager.create_bookmark(
            bookmark.get('name', Path(path).name),
            path
        )
        target_category.setdefault('items', []).append(new_bookmark)
        
        # Remove from source
        removed_from_source = False
        
        # If from bookmark bar (top level), remove from bar items
        if source_category in ('__BAR__', '__CONTAINER__') and bookmark.get('source_location') == 'bar':
            if hasattr(self, 'bookmark_bar') and self.bookmark_bar:
                removed_from_source = self.bookmark_bar.remove_bookmark_by_path(path)
                if removed_from_source:
                    logger.info(f"Removed '{path}' from bookmark bar")
        
        # If from Quick Links sidebar (top level), remove from sidebar items
        if not removed_from_source and source_category in ('__QUICK_LINKS__', '__CONTAINER__'):
            items = self.custom_quick_links.get('items', [])
            for i, item in enumerate(items):
                if item.get('type') == 'bookmark' and item.get('path') == path:
                    items.pop(i)
                    logger.info(f"Removed '{path}' from Quick Links sidebar")
                    removed_from_source = True
                    break
        
        # If from another category, remove from source category
        if not removed_from_source and source_category and source_category not in ('__QUICK_LINKS__', '__CONTAINER__', '__BAR__', ''):
            if self._bookmark_manager.remove_bookmark_from_category_by_name(source_category, path):
                logger.info(f"Removed '{path}' from category '{source_category}'")
                removed_from_source = True
        
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
        from suiteview.ui.widgets.bookmark_data_manager import get_bookmark_manager
        manager = get_bookmark_manager()
        new_items = []
        for path in new_order:
            new_items.append(manager.create_bookmark(
                Path(path).name,
                path
            ))
        
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
                item_path = item.get('path')
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
                        item_path = item.get('path')
                        if item_path == path:
                            bar_items.pop(i)
                            self.bookmark_bar.save_bookmarks()
                            self.bookmark_bar.refresh_bookmarks()
                            logger.info(f"Removed '{path}' from bookmark bar")
                            removed_from_source = True
                            break
            
            # Try Quick Links categories (sidebar categories - new format)
            if not removed_from_source and is_from_sidebar_category:
                if self._bookmark_manager.remove_bookmark_from_category_by_name(source_category, path):
                    removed_from_source = True
                    logger.info(f"Removed from Quick Links category '{source_category}'")
            
            # If from bookmark bar category (new format)
            if not removed_from_source and is_from_bar_category and hasattr(self, 'bookmark_bar') and self.bookmark_bar:
                if self._bookmark_manager.remove_bookmark_from_category_by_name(source_category, path):
                    self.bookmark_bar.save_bookmarks()
                    self.bookmark_bar.refresh_bookmarks()
                    logger.info(f"Removed from bookmark bar category '{source_category}'")
                    removed_from_source = True
            
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
        
        # Check if category already exists in Quick Links (new format)
        if self._bookmark_manager.find_category_by_name(category_name):
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
        
        # Use BookmarkContainer's remove_category method (new format)
        self.bookmark_bar.remove_category(category_name)
    
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
            
            # Update the sidebar toggle button state in bookmark bar
            if hasattr(self, 'bookmark_bar') and hasattr(self.bookmark_bar, 'sidebar_toggle_btn'):
                self.bookmark_bar.sidebar_toggle_btn.setChecked(self.dual_pane_active)
            # Update the breadcrumb bar bookmarks toggle button
            if hasattr(self, 'bookmarks_toggle_btn'):
                self.bookmarks_toggle_btn.setChecked(self.dual_pane_active)
            
            # Refresh quick links when showing
            if self.dual_pane_active:
                self.refresh_quick_links()
            
            # Adjust splitter sizes when toggling
            # IMPORTANT: Preserve the left panel width
            current_sizes = self.main_splitter.sizes()
            left_width = current_sizes[0] if current_sizes else 300  # Keep current left width
            notes_width = current_sizes[3] if len(current_sizes) >= 4 else 0
            
            if self.dual_pane_active:
                # Use saved right panel width if available, otherwise calculate
                saved_right = self.panel_widths.get('right_panel', 0)
                if saved_right > 0:
                    right_width = saved_right
                    middle_width = self.main_splitter.width() - left_width - right_width - notes_width
                else:
                    total_available = self.main_splitter.width() - left_width - notes_width
                    right_width = max(200, int(total_available * 0.25))
                    middle_width = total_available - right_width
                self.main_splitter.setSizes([left_width, middle_width, right_width, notes_width])
            else:
                details_width = self.main_splitter.width() - left_width - notes_width
                self.main_splitter.setSizes([left_width, details_width, 0, notes_width])
            
            # Save visibility state
            self.panel_widths['quick_links_visible'] = self.dual_pane_active
            self.save_panel_widths()
        
        print(f"Dual pane {'enabled' if self.dual_pane_active else 'disabled'}")

    def toggle_scratchpad_panel(self):
        """Toggle the ScratchPad panel on/off"""
        if not hasattr(self, 'scratchpad_panel'):
            return

        self.scratchpad_panel_active = not self.scratchpad_panel_active
        self.scratchpad_panel.setVisible(self.scratchpad_panel_active)

        # Update toggle button checked state
        if hasattr(self, 'scratchpad_toggle_btn'):
            self.scratchpad_toggle_btn.setChecked(self.scratchpad_panel_active)

        # Adjust splitter sizes
        current_sizes = self.main_splitter.sizes()
        left_width = current_sizes[0] if current_sizes else 300
        right_width = current_sizes[2] if len(current_sizes) >= 3 else 0

        if self.scratchpad_panel_active:
            # Refresh scratchpad when showing
            self.scratchpad_panel.refresh()
            saved_scratchpad = self.panel_widths.get('scratchpad_panel', 220)
            middle_width = self.main_splitter.width() - left_width - right_width - saved_scratchpad
            self.main_splitter.setSizes([left_width, max(100, middle_width), right_width, saved_scratchpad])
        else:
            middle_width = self.main_splitter.width() - left_width - right_width
            self.main_splitter.setSizes([left_width, middle_width, right_width, 0])

        # Persist
        self.panel_widths['scratchpad_visible'] = self.scratchpad_panel_active
        self.save_panel_widths()
        print(f"ScratchPad panel {'shown' if self.scratchpad_panel_active else 'hidden'}")

    def _on_scratchpad_fullscreen(self, go_full: bool):
        """Expand the scratchpad panel to fill the entire splitter, or restore."""
        if not hasattr(self, 'main_splitter'):
            return

        if go_full:
            # Save current sizes so we can restore later
            self._pre_fs_sizes = self.main_splitter.sizes()
            total = self.main_splitter.width()
            self.main_splitter.setSizes([0, 0, 0, total])
        else:
            # Restore saved sizes
            if hasattr(self, '_pre_fs_sizes') and self._pre_fs_sizes:
                self.main_splitter.setSizes(self._pre_fs_sizes)
            else:
                # Fallback
                left = self.panel_widths.get('left_panel', 300)
                mid = self.panel_widths.get('middle_panel', 700)
                right = self.panel_widths.get('right_panel', 0)
                scratchpad = self.panel_widths.get('scratchpad_panel', 220)
                self.main_splitter.setSizes([left, mid, right, scratchpad])
    
    def _replace_views_with_navigable(self):
        """Replace parent's QTreeView instances with NavigableTreeView"""
        from suiteview.file_nav.file_explorer_core import NoFocusDelegate
        
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
                border: 2px solid #D4A017;
                border-radius: 4px;
            }
            QFrame#breadcrumbFrame:hover {
                border-color: #FFD700;
            }
        """)
        
        breadcrumb_layout = QHBoxLayout(self.breadcrumb_frame)
        breadcrumb_layout.setContentsMargins(4, 3, 4, 3)
        breadcrumb_layout.setSpacing(4)

        # Back button - go to last visited folder
        back_icon = self.style().standardIcon(QStyle.StandardPixmap.SP_ArrowBack)
        self.back_btn = self._create_nav_button(back_icon, "Go Back (Alt+Left)", self.navigate_back)
        breadcrumb_layout.addWidget(self.back_btn)
        
        # Up button - go up one level
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
        
        # Explorer button - folder icon only with blue background and gold trim
        self.explorer_btn = QPushButton()
        self.explorer_btn.setToolTip("Open in Windows Explorer")
        self.explorer_btn.setFixedSize(26, 26)
        folder_icon = self.style().standardIcon(QStyle.StandardPixmap.SP_DirIcon)
        self.explorer_btn.setIcon(folder_icon)
        self.explorer_btn.setIconSize(QSize(16, 16))
        self.explorer_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.explorer_btn.setStyleSheet("""
            QPushButton {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    stop:0 #3A6AB4, stop:1 #1A4A94);
                border: 2px solid #D4A017;
                border-radius: 4px;
            }
            QPushButton:hover {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    stop:0 #4A7DC4, stop:1 #2A5AA4);
                border-color: #FFD700;
            }
            QPushButton:pressed {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    stop:0 #1E5BA8, stop:1 #082B5C);
            }
        """)
        self.explorer_btn.clicked.connect(self.open_in_explorer)
        breadcrumb_layout.addWidget(self.explorer_btn)
        
        # Bookmarks sidebar toggle button - show/hide the Quick Links / Bookmarks panel
        self.bookmarks_toggle_btn = QPushButton()
        self.bookmarks_toggle_btn.setToolTip("Toggle Bookmarks Sidebar")
        self.bookmarks_toggle_btn.setFixedSize(26, 26)
        self.bookmarks_toggle_btn.setText("🔖")
        self.bookmarks_toggle_btn.setCheckable(True)
        self.bookmarks_toggle_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.bookmarks_toggle_btn.setStyleSheet("""
            QPushButton {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    stop:0 #3A6AB4, stop:1 #1A4A94);
                border: 2px solid #D4A017;
                border-radius: 4px;
                font-size: 12pt;
            }
            QPushButton:hover {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    stop:0 #4A7DC4, stop:1 #2A5AA4);
                border-color: #FFD700;
            }
            QPushButton:checked {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    stop:0 #1E5BA8, stop:1 #082B5C);
                border: 2px solid #FFD700;
            }
            QPushButton:pressed {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    stop:0 #1E5BA8, stop:1 #082B5C);
            }
        """)
        self.bookmarks_toggle_btn.clicked.connect(self.toggle_dual_pane)
        breadcrumb_layout.addWidget(self.bookmarks_toggle_btn)
        
        # Connect history button from Folders header
        if hasattr(self, 'folders_history_btn'):
            self.folders_history_btn.clicked.connect(self.toggle_history_panel)
        
        # Insert at position 2 (after toolbar and bookmark bar)
        # Order: toolbar(0), bookmark_bar(1), breadcrumb(2), splitter(3)
        main_layout.insertWidget(2, self.breadcrumb_frame)
        
        # Set initial state of bookmarks sidebar toggle button
        if hasattr(self, 'dual_pane_active'):
            self.bookmarks_toggle_btn.setChecked(self.dual_pane_active)
        
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
        
        # Also call parent method to apply red border to splitter
        super()._apply_depth_search_locked_style(locked)
        
        if locked:
            # Red background when depth search is locked
            self.breadcrumb_frame.setStyleSheet("""
                QFrame#breadcrumbFrame {
                    background-color: #FFCCCC;
                    border: 2px solid #DC2626;
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
            # Normal yellow background with gold border
            self.breadcrumb_frame.setStyleSheet("""
                QFrame#breadcrumbFrame {
                    background-color: #FFFDE7;
                    border: 2px solid #D4A017;
                    border-radius: 4px;
                }
                QFrame#breadcrumbFrame:hover {
                    border-color: #FFD700;
                }
            """)
            # Restore breadcrumb widget style
            if hasattr(self, 'breadcrumb_widget'):
                self.breadcrumb_widget.setStyleSheet("""
                    ClickableBreadcrumb {
                        background-color: #FFFDE7;
                        border: 2px solid #D4A017;
                        border-radius: 3px;
                        padding: 1px;
                    }
                    ClickableBreadcrumb:hover {
                        border-color: #FFD700;
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
            self.folders_history_btn.setChecked(False)
        else:
            self._update_history_panel()
            self.history_panel.show()
            self.folders_history_btn.setChecked(True)
    
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
        close_btn.clicked.connect(lambda: (self.history_panel.hide(), self.folders_history_btn.setChecked(False)))
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
                            self._safe_startfile(str(target_obj))
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
        
        is_dir = path_obj.is_dir()
        is_file = path_obj.is_file()
        
        if is_dir:
            print(f"Is directory, navigating to: {path_obj}")
            # Use navigate_to_path to track history
            self.navigate_to_path(path_obj, add_to_history=True)
        elif is_file or (not is_dir and not is_file):
            # Open file with default application
            # Note: we also try opening when both is_file and is_dir return False,
            # which happens with long paths (>260 chars) on Windows with LongPathsEnabled=0
            try:
                if os.name == 'nt':
                    self._safe_startfile(str(path_obj))
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


class SuiteViewTaskbar(QWidget):
    """
    SuiteView main application window and tool launcher.
    Features:
    - Multiple tabs for different folders
    - Breadcrumb navigation per tab
    - New tab, close tab, pin tab functionality
    - All FileExplorerCore features in each tab
    """
    
    def __init__(self):
        super().__init__()
        
        # Frameless window setup
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowMinMaxButtonsHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, False)
        
        # Set minimum size to allow collapsing to just header bar (38 + margins)
        # Min width: SuiteView label + screenshot btn + Tools + window buttons
        self.setMinimumSize(330, 40)
        
        # Enable mouse tracking for resize cursor updates
        self.setMouseTracking(True)
        
        # Drag tracking
        self._drag_pos = None
        self._is_maximized = False
        self._is_compact_mode = False  # Will be set True after init
        self._is_floating_mode = False  # Undocked floating mini-bar mode
        self._stored_geometry = None
        self._compact_bar_pos = None   # Last known compact bar position
        self._appbar_registered = False  # True when registered as Windows AppBar
        
        # Resize edge detection
        self._resize_margin = 6
        self._resizing = False
        self._resize_edge = None
        self._resize_start_pos = None
        self._start_geometry = None
        
        # Store references to opened app windows
        self.db_window = None
        self.mainframe_window = None
        self.email_attachments_window = None
        self.screenshot_window = None
        self.task_tracker_window = None
        self.polview_window = None
        self.audit_window = None
        self.ratemanager_window = None
        self.abrquote_window = None
        self.file_nav_window = None
        self.scratchpad_window = None

        # Create PolView eagerly so all tools share the same instance
        # (only if the polview package is available in this deployment)
        try:
            from suiteview.polview.ui.main_window import GetPolicyWindow
            self.polview_window = GetPolicyWindow()
            self._setup_child_window(self.polview_window, "PolView")
        except ImportError:
            logger.info("PolView package not available — skipping")
        except Exception as e:
            logger.error(f"Failed to pre-create PolView: {e}")

        # Messaging service
        self._msg_service = MessageService(self)
        self._msg_inbox = MessageInbox()
        self._unread_count = 0

        # Shared splitter sizes across all tabs - loaded from saved settings
        self._shared_splitter_sizes = None  # Will be set from first tab or saved
        self._syncing_splitter = False  # Prevent recursive updates
        
        self.init_ui()
        
        # Add resize grips to corners
        self._add_resize_grips()
        
        # Setup system tray
        self._setup_system_tray()

        # Connect messaging signals
        self._msg_service.new_messages.connect(self._on_new_messages)
        self._msg_inbox.message_dismissed.connect(self._on_message_dismissed)
        self._msg_inbox.open_file.connect(self._on_msg_open_file)
        self._msg_inbox.navigate_to.connect(self._on_msg_open_in_folder)

        # Create initial tab
        self.add_new_tab()
        
        # Start in compact mini-bar mode at bottom-right corner
        self._enter_compact_mode(initial=True)
    
    def _build_suiteview_icon(self, size=64):
        """Build the SuiteView icon - blue square with gold trim and golden S
        
        For Windows taskbar compatibility, this creates an icon with multiple sizes.
        """
        icon = QIcon()
        
        # Add multiple sizes for Windows taskbar compatibility
        # Windows uses different sizes: 16 (small), 32 (medium), 48, 64, 128, 256 (large)
        sizes = [16, 24, 32, 48, 64, 128, 256] if size >= 64 else [size]
        
        for sz in sizes:
            pixmap = self._create_icon_pixmap(sz)
            icon.addPixmap(pixmap)
        
        return icon
    
    def _create_icon_pixmap(self, size):
        """Create a single pixmap for the SuiteView icon at specified size"""
        pixmap = QPixmap(size, size)
        pixmap.fill(Qt.GlobalColor.transparent)
        
        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        
        margin = max(1, size // 32)
        rect_size = size - margin * 2
        
        # Draw blue background with gradient
        from PyQt6.QtGui import QLinearGradient
        gradient = QLinearGradient(0, 0, 0, size)
        gradient.setColorAt(0, QColor("#1E5BA8"))
        gradient.setColorAt(0.5, QColor("#0D3A7A"))
        gradient.setColorAt(1, QColor("#082B5C"))
        
        border_width = max(1, size // 20)
        painter.setBrush(QBrush(gradient))
        painter.setPen(QPen(QColor("#D4A017"), border_width))  # Gold border
        corner_radius = max(2, size // 8)
        painter.drawRoundedRect(margin, margin, rect_size, rect_size, corner_radius, corner_radius)
        
        # Draw golden "S" in the center
        painter.setPen(QColor("#D4A017"))
        font_size = max(8, int(size * 0.55))
        font = QFont("Georgia", font_size, QFont.Weight.Bold)
        font.setItalic(True)
        painter.setFont(font)
        painter.drawText(pixmap.rect(), Qt.AlignmentFlag.AlignCenter, "S")
        
        painter.end()
        return pixmap
    
    def _setup_system_tray(self):
        """Setup system tray icon and menu"""
        self.tray_icon = QSystemTrayIcon(self)
        self.tray_icon.setIcon(self._build_suiteview_icon(64))
        self.tray_icon.setToolTip("SuiteView - Click to show")
        
        # Create tray menu
        tray_menu = QMenu()
        tray_menu.setStyleSheet("""
            QMenu {
                background-color: #0D3A7A;
                border: 1px solid #D4A017;
                border-radius: 4px;
                padding: 4px;
            }
            QMenu::item {
                background-color: transparent;
                color: white;
                padding: 8px 20px;
                font-size: 11px;
            }
            QMenu::item:selected {
                background-color: #3A7DC8;
            }
            QMenu::separator {
                height: 1px;
                background: #D4A017;
                margin: 4px 8px;
            }
        """)
        
        # Store all actions as instance variables to prevent garbage collection
        self._show_action = QAction("Show SuiteView", self)
        self._show_action.triggered.connect(self._show_from_tray)
        tray_menu.addAction(self._show_action)
        
        tray_menu.addSeparator()
        
        self._mainframe_action = QAction("💻 Mainframe Navigator", self)
        self._mainframe_action.triggered.connect(self._open_mainframe)
        tray_menu.addAction(self._mainframe_action)
        
        if DEV_MODE:
            self._data_action = QAction("🗄️ Data Manager", self)
            self._data_action.triggered.connect(self._open_data_manager)
            tray_menu.addAction(self._data_action)
        
        self._screenshot_action = QAction("📸 View Screenshots", self)
        self._screenshot_action.triggered.connect(self._open_screenshot)
        tray_menu.addAction(self._screenshot_action)
        
        # PolView and ABR Quote are always available (including distribution builds)
        self._polview_action = QAction("📋 PolView", self)
        self._polview_action.triggered.connect(self._open_polview)
        tray_menu.addAction(self._polview_action)
        
        self._abrquote_action = QAction("💰 ABR Quote", self)
        self._abrquote_action.triggered.connect(self._open_abrquote)
        tray_menu.addAction(self._abrquote_action)
        
        if DEV_MODE:
            self._audit_action = QAction("🔍 Audit Tool", self)
            self._audit_action.triggered.connect(self._open_audit)
            tray_menu.addAction(self._audit_action)
        
        tray_menu.addSeparator()
        
        # Store as instance variable to prevent garbage collection
        self._quit_action = QAction("Quit SuiteView", self)
        self._quit_action.triggered.connect(self._quit_application)
        tray_menu.addAction(self._quit_action)
        
        # Store tray menu as instance variable too
        self._tray_menu = tray_menu
        self.tray_icon.setContextMenu(self._tray_menu)
        self.tray_icon.activated.connect(self._on_tray_activated)
        self.tray_icon.show()
        
        # Also set the window icon
        self.setWindowIcon(self._build_suiteview_icon(64))
    
    def _on_tray_activated(self, reason):
        """Handle tray icon clicks"""
        if reason == QSystemTrayIcon.ActivationReason.Trigger:
            self._show_from_tray()
    
    def _show_from_tray(self):
        """Show and activate the main window"""
        self.show()
        self.activateWindow()
        self.raise_()
        if self._is_maximized:
            self.showMaximized()

        # Re-register AppBar and re-hide taskbar icon if we're in compact mode
        if self._is_compact_mode:
            bar_h = self.height() or 42
            self._register_appbar(bar_h)
            # Re-apply WS_EX_TOOLWINDOW to hide taskbar icon
            try:
                import ctypes
                hwnd = int(self.winId())
                GWL_EXSTYLE = -20
                WS_EX_TOOLWINDOW = 0x00000080
                WS_EX_APPWINDOW  = 0x00040000
                user32 = ctypes.windll.user32
                ex_style = user32.GetWindowLongW(hwnd, GWL_EXSTYLE)
                ex_style = (ex_style | WS_EX_TOOLWINDOW) & ~WS_EX_APPWINDOW
                user32.SetWindowLongW(hwnd, GWL_EXSTYLE, ex_style)
            except Exception:
                pass
    
    def _hide_to_tray(self):
        """Hide to system tray"""
        # If docked, unregister AppBar so desktop reclaims the full work area
        if self._is_compact_mode:
            self._unregister_appbar()
        self.hide()
        self.tray_icon.showMessage(
            "SuiteView",
            "SuiteView is still running. Click the tray icon to restore.",
            QSystemTrayIcon.MessageIcon.Information,
            2000
        )
    
    def _quit_application(self):
        """Quit the entire application"""
        import logging
        logger = logging.getLogger(__name__)
        logger.info("Quit requested from system tray")
        
        try:
            # Stop messaging service
            if hasattr(self, '_msg_service'):
                self._msg_service.stop()

            # Unregister AppBar to restore desktop work area (compact mode)
            self._unregister_appbar()
            
            # Close all child windows
            for window in [self.db_window, self.mainframe_window, self.email_attachments_window, 
                           self.screenshot_window, self.polview_window, self.ratemanager_window,
                           self.file_nav_window]:
                if window:
                    try:
                        window.close()
                    except:
                        pass
            
            # Hide tray icon
            try:
                self.tray_icon.hide()
            except:
                pass
            
            # Close main window
            self.close()
            
            # Force quit the application
            QApplication.quit()
            
        except Exception as e:
            logger.error(f"Error during quit: {e}")
            # Force quit anyway
            QApplication.quit()

    # ── Messaging ────────────────────────────────────────────────

    def _on_new_messages(self, messages):
        """Handle newly arrived messages from the polling service."""
        self._unread_count += len(messages)
        self._update_msg_badge()
        self._msg_inbox.add_messages(messages)
        # System tray balloon
        if hasattr(self, 'tray_icon') and self.tray_icon.isVisible():
            sender = messages[0].sender_display or messages[0].sender
            if len(messages) == 1:
                body = f"📄 {Path(messages[0].path).name}"
            else:
                body = f"{len(messages)} new file links"
            self.tray_icon.showMessage(
                f"Message from {sender}", body,
                QSystemTrayIcon.MessageIcon.Information, 4000)

    def _on_message_dismissed(self, msg):
        """Acknowledge (delete) the message file and update badge."""
        self._msg_service.acknowledge(msg)
        self._unread_count = max(0, self._unread_count - 1)
        self._update_msg_badge()

    def _on_msg_open_file(self, file_path):
        """Open a file received via message."""
        try:
            p = Path(file_path)
            if p.exists():
                if os.name == 'nt':
                    os.startfile(str(p))
                else:
                    import subprocess
                    subprocess.run(['xdg-open', str(p)])
            else:
                QMessageBox.warning(self, "File Not Found",
                                    f"The file no longer exists:\n{file_path}")
        except Exception as e:
            logger.error(f"Failed to open message file: {e}")

    def _on_msg_open_in_folder(self, file_path):
        """Open the file's parent folder in File Nav in a new tab."""
        p = Path(file_path)
        folder = str(p.parent) if p.is_file() else str(p)
        # Ensure File Nav is open
        self._open_file_nav()
        if self.file_nav_window:
            self.file_nav_window.add_new_tab(path=folder)

    def _update_msg_badge(self):
        """Update the message badge button appearance based on unread count."""
        count = self._unread_count
        if count > 0:
            display = f"\u2709 {count}" if count <= 99 else "\u2709 99+"
            self.msg_badge_btn.setText(display)
            self.msg_badge_btn.setFixedSize(48, 28)
            self.msg_badge_btn.setStyleSheet("""
                QPushButton {
                    background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                        stop:0 #E03030, stop:1 #B01010);
                    border: 2px solid #FF2222;
                    border-radius: 4px;
                    color: white;
                    font-size: 10px;
                    font-weight: bold;
                }
                QPushButton:hover {
                    background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                        stop:0 #FF4040, stop:1 #D02020);
                    border-color: #FF5555;
                }
            """)
            self.msg_badge_btn.setToolTip(f"{count} unread message{'s' if count != 1 else ''}")
        else:
            self.msg_badge_btn.setText("\u2709")
            self.msg_badge_btn.setFixedSize(28, 28)
            self.msg_badge_btn.setStyleSheet("""
                QPushButton {
                    background: transparent;
                    border: 2px solid #555;
                    border-radius: 4px;
                    color: #888;
                    font-size: 14px;
                }
                QPushButton:hover {
                    background: rgba(255, 255, 255, 0.1);
                    border-color: #777;
                }
            """)
            self.msg_badge_btn.setToolTip("Messages")

    def _toggle_msg_inbox(self):
        """Show / hide the message inbox popup above the badge button."""
        if self._msg_inbox.isVisible():
            self._msg_inbox.hide()
            return
        # Popup auto-closes on outside click; if the badge button was that
        # click, the popup just closed and we should NOT reopen it.
        if self._msg_inbox.recently_closed:
            return
        # Ensure the widget knows its size before positioning
        self._msg_inbox.adjustSize()
        inbox_h = self._msg_inbox.sizeHint().height()
        inbox_w = self._msg_inbox.width()  # fixedWidth=340

        # Anchor: top-right of the badge button
        btn_top_right = self.msg_badge_btn.mapToGlobal(
            QPoint(self.msg_badge_btn.width(), 0))

        # Position the popup so its bottom edge is at the top of the button
        x = btn_top_right.x() - inbox_w
        y = btn_top_right.y() - inbox_h - 4

        # Clamp to screen bounds so nothing goes off-screen
        screen = self.msg_badge_btn.screen()
        if screen:
            avail = screen.availableGeometry()
            # If popup would go above the screen top, flip it below the button
            if y < avail.top():
                btn_bottom = self.msg_badge_btn.mapToGlobal(
                    QPoint(0, self.msg_badge_btn.height()))
                y = btn_bottom.y() + 4
            # Keep within horizontal bounds
            if x < avail.left():
                x = avail.left() + 4
            if x + inbox_w > avail.right():
                x = avail.right() - inbox_w - 4

        self._msg_inbox.move(x, y)
        self._msg_inbox.show()

    def _take_quick_screenshot(self):
        """Take a screenshot of the primary screen INCLUDING SuiteView windows"""
        try:
            from datetime import datetime
            import time
            
            # Small delay to ensure screen is fully rendered
            QApplication.processEvents()
            time.sleep(0.05)
            
            # Get screenshots folder
            screenshots_dir = Path.home() / '.suiteview' / 'screenshots'
            screenshots_dir.mkdir(parents=True, exist_ok=True)
            
            # Generate filename with timestamp
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            filename = f"screenshot_{timestamp}.png"
            filepath = screenshots_dir / filename
            
            # Take screenshot of primary screen (including SuiteView windows)
            screen = QApplication.primaryScreen()
            if screen:
                pixmap = screen.grabWindow(0)
                pixmap.save(str(filepath), 'PNG')
                
                # Notify Screenshot Manager if it's open
                if self.screenshot_window is not None and self.screenshot_window.isVisible():
                    try:
                        self.screenshot_window.add_screenshot_from_file(filepath)
                    except Exception as e:
                        logger.warning(f"Failed to notify Screenshot Manager: {e}")
                
                # Show notification
                self.tray_icon.showMessage(
                    "Screenshot Saved",
                    f"Saved to: {filename}",
                    QSystemTrayIcon.MessageIcon.Information,
                    2000
                )
                
        except Exception as e:
            logger.error(f"Failed to take screenshot: {e}")
            self.tray_icon.showMessage(
                "Screenshot Failed",
                str(e),
                QSystemTrayIcon.MessageIcon.Warning,
                2000
            )
    
    def _capture_active_window(self):
        """Capture full screen EXCLUDING SuiteView and Screenshot Manager windows"""
        try:
            import time
            
            # Track which windows we need to restore
            windows_to_restore = []
            
            # Hide SuiteView main window
            if self.isVisible():
                self.hide()
                windows_to_restore.append(self)
            
            # Hide Screenshot Manager if open
            if self.screenshot_window is not None and self.screenshot_window.isVisible():
                self.screenshot_window.hide()
                windows_to_restore.append(self.screenshot_window)
            
            # Process events and wait for windows to hide
            QApplication.processEvents()
            time.sleep(0.15)  # Brief delay for windows to hide
            
            # Now capture the screen
            self._do_capture_excluding_suiteview(windows_to_restore)
                
        except Exception as e:
            logger.error(f"Failed to capture screen: {e}")
            self.tray_icon.showMessage(
                "Capture Failed",
                str(e),
                QSystemTrayIcon.MessageIcon.Warning,
                2000
            )
    
    def _do_capture_excluding_suiteview(self, windows_to_restore):
        """Perform the actual capture after hiding SuiteView windows"""
        try:
            from datetime import datetime
            
            # Get screenshots folder
            screenshots_dir = Path.home() / '.suiteview' / 'screenshots'
            screenshots_dir.mkdir(parents=True, exist_ok=True)
            
            # Generate filename with timestamp
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            filename = f"screen_{timestamp}.png"
            filepath = screenshots_dir / filename
            
            # Take screenshot of primary screen
            screen = QApplication.primaryScreen()
            if screen:
                pixmap = screen.grabWindow(0)
                pixmap.save(str(filepath), 'PNG')
                
                # Show notification
                self.tray_icon.showMessage(
                    "Screen Captured",
                    f"Saved to: {filename}",
                    QSystemTrayIcon.MessageIcon.Information,
                    2000
                )
            
            # Restore all hidden windows
            for window in windows_to_restore:
                window.show()
                window.activateWindow()
                window.raise_()
            
            # Notify Screenshot Manager to reload if it was restored
            if self.screenshot_window is not None and self.screenshot_window in windows_to_restore:
                try:
                    self.screenshot_window._load_existing_screenshots()
                except Exception as e:
                    logger.warning(f"Failed to notify Screenshot Manager: {e}")
                    
        except Exception as e:
            logger.error(f"Failed to capture screen: {e}")
            # Still restore windows on error
            for window in windows_to_restore:
                window.show()
    
    def _open_data_manager(self):
        """Open the Data Manager window"""
        if self.db_window is None:
            try:
                from suiteview.database_manager.main_window import MainWindow
                from suiteview.utils.config import Config
                self.db_window = MainWindow(Config())
                self._setup_child_window(self.db_window, "Data Manager")
            except Exception as e:
                logger.error(f"Failed to open Data Manager: {e}")
                return
        self._bring_to_front(self.db_window)
    
    def _open_mainframe(self):
        """Open the Mainframe Navigator window"""
        if self.mainframe_window is None:
            try:
                from suiteview.mainframe_nav.mainframe_window import MainframeWindow
                self.mainframe_window = MainframeWindow()
                self._setup_child_window(self.mainframe_window, "Mainframe Navigator")
            except Exception as e:
                logger.error(f"Failed to open Mainframe Navigator: {e}")
                return
        self._bring_to_front(self.mainframe_window)
    
    def _open_screenshot(self):
        """Open the Screenshot Manager window"""
        if self.screenshot_window is None:
            try:
                from suiteview.screenshot_manager.screenshot_manager_window import ScreenShotManagerWindow
                self.screenshot_window = ScreenShotManagerWindow()
                self._setup_child_window(self.screenshot_window, "Screenshot Manager")
            except Exception as e:
                logger.error(f"Failed to open Screenshot Manager: {e}")
                return
        else:
            # Reload screenshots to show any new ones taken while window was hidden
            self.screenshot_window._load_existing_screenshots()
        self._bring_to_front(self.screenshot_window)
    
    def _open_email_attachments(self):
        """Open the Email Attachments window"""
        if self.email_attachments_window is None:
            try:
                from suiteview.ui.email_attachments_window import EmailAttachmentsWindow
                self.email_attachments_window = EmailAttachmentsWindow()
                self.email_attachments_window.setWindowIcon(self._build_suiteview_icon(32))
            except Exception as e:
                logger.error(f"Failed to open Email Attachments: {e}")
                return
        self._bring_to_front(self.email_attachments_window)
    
    def _open_task_tracker(self):
        """Open the Task Tracker window"""
        if self.task_tracker_window is None:
            try:
                from suiteview.tasktracker import TaskTrackerWindow
                self.task_tracker_window = TaskTrackerWindow()
                self._setup_child_window(self.task_tracker_window, "Task Tracker")
            except Exception as e:
                logger.error(f"Failed to open Task Tracker: {e}")
                return
        self._bring_to_front(self.task_tracker_window)

    def _open_polview(self):
        """Open the PolView - Policy Viewer window"""
        if self.polview_window is None:
            try:
                from suiteview.polview.ui.main_window import GetPolicyWindow
                self.polview_window = GetPolicyWindow()
                self._setup_child_window(self.polview_window, "PolView")
            except Exception as e:
                logger.error(f"Failed to open PolView: {e}")
                return
        self._bring_to_front(self.polview_window)

    def _get_polview_window(self):
        """Get the shared PolView window (used as provider callback for child tools).

        Creates the window lazily if requested before the taskbar opened it,
        but does NOT show it — the caller decides when to show.
        """
        if self.polview_window is None:
            try:
                from suiteview.polview.ui.main_window import GetPolicyWindow
                self.polview_window = GetPolicyWindow()
                self._setup_child_window(self.polview_window, "PolView")
            except ImportError:
                logger.info("PolView package not available")
            except Exception as e:
                logger.error(f"Failed to create PolView: {e}")
        return self.polview_window

    def _polview_btn_clicked(self):
        """Handle [P] button click — open with policy if input has text, else just open."""
        if (self._is_compact_mode
                and hasattr(self, 'compact_policy_input')
                and self.compact_policy_input.text().strip()):
            self._open_polview_with_policy()
        else:
            self._open_polview()

    def _open_polview_with_policy(self):
        """Open PolView and load the policy specified in the compact bar inputs."""
        policy = self.compact_policy_input.text().strip()
        if not policy:
            return

        region = self.compact_region_combo.currentText()

        # Ensure PolView window exists
        self._open_polview()

        # Populate PolView's lookup bar and trigger the lookup
        if self.polview_window and hasattr(self.polview_window, 'lookup_bar'):
            lb = self.polview_window.lookup_bar
            lb.region_input.setText(region)
            lb.company_input.setText("")   # Let it auto-detect
            lb.policy_input.setText(policy)
            lb._on_get_policy()

    def _open_audit(self):
        """Open the Audit Tool window"""
        if self.audit_window is None:
            try:
                from suiteview.audit import launch_audit
                self.audit_window = launch_audit()
                self._setup_child_window(self.audit_window, "Audit Tool")
            except Exception as e:
                import traceback
                logger.error(f"Failed to open Audit Tool: {e}\n{traceback.format_exc()}")
                QMessageBox.warning(self, "Audit Tool Error",
                                    f"Failed to open Audit Tool:\n\n{e}")
                return
        # Share PolView so policies opened from Audit use the same window
        if hasattr(self.audit_window, 'set_polview_provider'):
            self.audit_window.set_polview_provider(self._get_polview_window)
        self._bring_to_front(self.audit_window)

    def _open_abrquote(self):
        """Open the ABR Quote Tool window"""
        # Guard: if the stored window was destroyed (e.g. C++ object deleted),
        # reset so we recreate it cleanly.
        if self.abrquote_window is not None:
            try:
                # Accessing any Qt property on a deleted C++ object raises RuntimeError
                _ = self.abrquote_window.isVisible()
            except RuntimeError:
                self.abrquote_window = None

        if self.abrquote_window is None:
            try:
                from suiteview.abrquote import launch_abrquote
                self.abrquote_window = launch_abrquote()
                self._setup_child_window(self.abrquote_window, "ABR Quote")
            except Exception as e:
                import traceback
                tb = traceback.format_exc()
                logger.error(f"Failed to open ABR Quote: {e}\n{tb}")
                QMessageBox.critical(self, "ABR Quote Error",
                                     f"Failed to open ABR Quote:\n\n{e}\n\n{tb}")
                self.abrquote_window = None  # reset so retry works
                return
        self._bring_to_front(self.abrquote_window)


    def _open_rate_manager(self):
        """Open the Rate File Converter window"""
        if self.ratemanager_window is None:
            try:
                from suiteview.ratemanager.ratemanager_window import RateManagerWindow
                self.ratemanager_window = RateManagerWindow()
                self._setup_child_window(self.ratemanager_window, "Rate File Converter")
            except Exception as e:
                logger.error(f"Failed to open Rate File Converter: {e}")
                return
        self._bring_to_front(self.ratemanager_window)

    def _open_file_nav(self):
        """Open the File Navigator as a separate window."""
        # Guard: if the stored window was destroyed, reset it
        if self.file_nav_window is not None:
            try:
                _ = self.file_nav_window.isVisible()
            except RuntimeError:
                self.file_nav_window = None

        if self.file_nav_window is None:
            try:
                self.file_nav_window = FileNavWindow(parent_bar=self)
                self._setup_child_window(self.file_nav_window, "FileNav")
            except Exception as e:
                import traceback
                tb = traceback.format_exc()
                logger.error(f"Failed to open File Navigator: {e}\n{tb}")
                self.file_nav_window = None
                return
        self._bring_to_front(self.file_nav_window)

    def _open_app_data_location(self):
        """Navigate to the app data folder (~/.suiteview) in the details view"""
        app_data_dir = Path.home() / '.suiteview'
        # Create the directory if it doesn't exist
        app_data_dir.mkdir(parents=True, exist_ok=True)
        # Navigate to it in the current tab's details pane
        current_tab = self.get_current_tab()
        if current_tab and hasattr(current_tab, 'navigate_to_path'):
            current_tab.navigate_to_path(str(app_data_dir))

    def _toggle_scratchpad_window(self):
        """Toggle the ScratchPad window visibility."""
        # Guard: if the stored window was destroyed, reset it
        if self.scratchpad_window is not None:
            try:
                _ = self.scratchpad_window.isVisible()
            except RuntimeError:
                self.scratchpad_window = None

        if self.scratchpad_window is None:
            try:
                from suiteview.scratchpad.scratchpad_panel import ScratchPadWindow
                self.scratchpad_window = ScratchPadWindow.open(parent_bar=self)
                self._setup_child_window(self.scratchpad_window, "ScratchPad")
            except Exception as e:
                import traceback
                tb = traceback.format_exc()
                logger.error(f"Failed to open ScratchPad window: {e}\n{tb}")
                self.scratchpad_window = None
                return

                return

        if self.scratchpad_window.isVisible():
            self.scratchpad_window.hide()
        else:
            self._bring_to_front(self.scratchpad_window)

    def _toggle_file_open_history(self):
        """Toggle the File Open History popup panel."""
        if not hasattr(self, '_file_open_history_panel') or self._file_open_history_panel is None:
            from suiteview.ui.widgets.file_open_history import FileOpenHistoryPanel
            self._file_open_history_panel = FileOpenHistoryPanel(self)

        panel = self._file_open_history_panel
        if panel.isVisible():
            panel.hide()
        elif panel.was_recently_hidden():
            # Popup auto-closed because user clicked the H button — treat as "close" toggle
            pass
        else:
            panel.show_under(self.file_history_btn)

    
    def _bring_to_front(self, window):
        """Show a child window and reliably bring it to the foreground."""
        window.show()
        window.activateWindow()
        window.raise_()
        # On Windows, raise_() often fails due to focus-stealing prevention.
        # Use the Win32 API to force the window to the foreground.
        try:
            import ctypes
            hwnd = int(window.winId())
            ctypes.windll.user32.SetForegroundWindow(hwnd)
        except Exception:
            pass

    def _setup_child_window(self, window, title):
        """Setup a child window with hide-on-close behavior"""
        window.setWindowTitle(f"SuiteView - {title}")
        window.setWindowIcon(self._build_suiteview_icon(32))
        
        # Override close event to hide instead of closing
        def hide_on_close(event):
            event.ignore()
            window.hide()
        window.closeEvent = hide_on_close
    
    def _add_resize_grips(self):
        """Add resize grips to all edges and corners for easier resizing"""
        from PyQt6.QtWidgets import QSizeGrip
        
        # Bottom-right grip (visible, standard Qt grip)
        self.size_grip = QSizeGrip(self)
        self.size_grip.setStyleSheet("""
            QSizeGrip {
                background-color: transparent;
                width: 16px;
                height: 16px;
            }
        """)
        
        # Create edge resize widgets
        self._resize_widgets = []
        
        # Edge widget class for resize
        class ResizeEdge(QFrame):
            def __init__(self, parent, edge):
                super().__init__(parent)
                self.edge = edge
                self.parent_window = parent
                self.setMouseTracking(True)
                self.setCursor(self._get_cursor())
                self.setStyleSheet("background-color: transparent;")
                self._dragging = False
                self._start_pos = None
                self._start_geometry = None
                
            def _get_cursor(self):
                cursors = {
                    'left': Qt.CursorShape.SizeHorCursor,
                    'right': Qt.CursorShape.SizeHorCursor,
                    'top': Qt.CursorShape.SizeVerCursor,
                    'bottom': Qt.CursorShape.SizeVerCursor,
                    'top-left': Qt.CursorShape.SizeFDiagCursor,
                    'bottom-right': Qt.CursorShape.SizeFDiagCursor,
                    'top-right': Qt.CursorShape.SizeBDiagCursor,
                    'bottom-left': Qt.CursorShape.SizeBDiagCursor,
                }
                return cursors.get(self.edge, Qt.CursorShape.ArrowCursor)
                
            def mousePressEvent(self, event):
                if event.button() == Qt.MouseButton.LeftButton:
                    self._dragging = True
                    self._start_pos = event.globalPosition().toPoint()
                    self._start_geometry = self.parent_window.geometry()
                    event.accept()
                    
            def mouseMoveEvent(self, event):
                if self._dragging and self._start_geometry:
                    delta = event.globalPosition().toPoint() - self._start_pos
                    geo = self._start_geometry
                    new_x, new_y = geo.x(), geo.y()
                    new_w, new_h = geo.width(), geo.height()
                    min_w, min_h = 330, 46  # Allow shrinking to just header bar
                    
                    # Calculate fixed edges for proper clamping
                    right_edge = geo.x() + geo.width()
                    bottom_edge = geo.y() + geo.height()
                    
                    if 'left' in self.edge:
                        new_w = max(min_w, geo.width() - delta.x())
                        new_x = right_edge - new_w  # Keep right edge fixed
                    if 'right' in self.edge:
                        new_w = max(min_w, geo.width() + delta.x())
                    if 'top' in self.edge:
                        new_h = max(min_h, geo.height() - delta.y())
                        new_y = bottom_edge - new_h  # Keep bottom edge fixed
                    if 'bottom' in self.edge:
                        new_h = max(min_h, geo.height() + delta.y())
                    
                    self.parent_window.setGeometry(new_x, new_y, new_w, new_h)
                    event.accept()
                    
            def mouseReleaseEvent(self, event):
                self._dragging = False
                self._start_pos = None
                self._start_geometry = None
        
        # Create edge widgets
        margin = 6
        
        # Top edge
        self._edge_top = ResizeEdge(self, 'top')
        self._resize_widgets.append(('top', self._edge_top))
        
        # Bottom edge  
        self._edge_bottom = ResizeEdge(self, 'bottom')
        self._resize_widgets.append(('bottom', self._edge_bottom))
        
        # Left edge
        self._edge_left = ResizeEdge(self, 'left')
        self._resize_widgets.append(('left', self._edge_left))
        
        # Right edge
        self._edge_right = ResizeEdge(self, 'right')
        self._resize_widgets.append(('right', self._edge_right))
        
        # Corners
        self._edge_tl = ResizeEdge(self, 'top-left')
        self._resize_widgets.append(('top-left', self._edge_tl))
        
        self._edge_tr = ResizeEdge(self, 'top-right')
        self._resize_widgets.append(('top-right', self._edge_tr))
        
        self._edge_bl = ResizeEdge(self, 'bottom-left')
        self._resize_widgets.append(('bottom-left', self._edge_bl))
        
    def resizeEvent(self, event):
        """Position the resize widgets on resize and collapse/expand UI elements"""
        super().resizeEvent(event)
        margin = 6
        w, h = self.width(), self.height()
        
        # Collapse/expand UI elements based on window height
        # Header bar is ~38px, footer is ~24px, tab bar is ~30px
        if hasattr(self, 'footer_bar') and hasattr(self, 'tab_widget'):
            # Hide footer and tab content when window is very small (just header)
            if h < 70:
                self.footer_bar.hide()
                self.tab_widget.hide()
            elif h < 100:
                self.footer_bar.hide()
                self.tab_widget.show()
            else:
                self.footer_bar.show()
                self.tab_widget.show()
        
        if hasattr(self, 'size_grip'):
            self.size_grip.move(w - 16, h - 16)
            self.size_grip.raise_()
        
        if hasattr(self, '_resize_widgets'):
            for edge_name, widget in self._resize_widgets:
                if edge_name == 'top':
                    widget.setGeometry(margin, 0, w - 2*margin, margin)
                elif edge_name == 'bottom':
                    widget.setGeometry(margin, h - margin, w - 2*margin, margin)
                elif edge_name == 'left':
                    widget.setGeometry(0, margin, margin, h - 2*margin)
                elif edge_name == 'right':
                    widget.setGeometry(w - margin, margin, margin, h - 2*margin)
                elif edge_name == 'top-left':
                    widget.setGeometry(0, 0, margin, margin)
                elif edge_name == 'top-right':
                    widget.setGeometry(w - margin, 0, margin, margin)
                elif edge_name == 'bottom-left':
                    widget.setGeometry(0, h - margin, margin, margin)
                widget.raise_()
    
    def init_ui(self):
        """Initialize the UI"""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(2, 2, 2, 2)  # Small margin for resize handles
        layout.setSpacing(0)
        
        # ====== GLOBAL SCROLLBAR STYLING (light blue for contrast) ======
        self.setStyleSheet("""
            QScrollBar:vertical {
                background: #E8F0F8;
                width: 12px;
                margin: 0;
                border-radius: 6px;
            }
            QScrollBar::handle:vertical {
                background: #A8C8E8;
                min-height: 20px;
                border-radius: 5px;
                margin: 1px;
            }
            QScrollBar::handle:vertical:hover {
                background: #88B0D8;
            }
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
                height: 0;
                background: none;
            }
            QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {
                background: none;
            }
            QScrollBar:horizontal {
                background: #E8F0F8;
                height: 12px;
                margin: 0;
                border-radius: 6px;
            }
            QScrollBar::handle:horizontal {
                background: #A8C8E8;
                min-width: 20px;
                border-radius: 5px;
                margin: 1px;
            }
            QScrollBar::handle:horizontal:hover {
                background: #88B0D8;
            }
            QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {
                width: 0;
                background: none;
            }
            QScrollBar::add-page:horizontal, QScrollBar::sub-page:horizontal {
                background: none;
            }
        """)
        
        # ====== HEADER BAR (Custom Title Bar) ======
        self.header_bar = QFrame()
        self.header_bar.setFixedHeight(38)
        self.header_bar.setMouseTracking(True)
        self.header_bar.setStyleSheet("""
            QFrame {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    stop:0 #1E5BA8, stop:0.5 #0D3A7A, stop:1 #082B5C);
                border: none;
            }
        """)
        self.header_bar.setCursor(Qt.CursorShape.ArrowCursor)
        header_layout = QHBoxLayout(self.header_bar)
        header_layout.setContentsMargins(12, 4, 8, 4)
        header_layout.setSpacing(8)
        
        # App title (acts as drag handle) - larger and italic
        self.title_label = QLabel("SuiteView")
        self.title_label.setStyleSheet("""
            QLabel {
                color: #D4A017;
                font-size: 18px;
                font-weight: bold;
                font-style: italic;
                background: transparent;
                padding-right: 4px;
            }
        """)
        self.title_label.setCursor(Qt.CursorShape.PointingHandCursor)
        self.title_label.mouseDoubleClickEvent = lambda event: self._toggle_compact_mode()
        header_layout.addWidget(self.title_label)
        
        # ====== QUICK SCREENSHOT BUTTON (yellow dot) ======
        self.quick_screenshot_btn = QPushButton()
        self.quick_screenshot_btn.setFixedSize(28, 28)
        self.quick_screenshot_btn.setToolTip("Take Screenshot (saves to Screenshots folder)")
        self.quick_screenshot_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        # Create icon with yellow dot
        dot_pixmap = QPixmap(24, 24)
        dot_pixmap.fill(Qt.GlobalColor.transparent)
        dot_painter = QPainter(dot_pixmap)
        dot_painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        dot_painter.setBrush(QBrush(QColor("#FFD700")))  # Yellow/gold dot
        dot_painter.setPen(Qt.PenStyle.NoPen)
        dot_painter.drawEllipse(6, 6, 12, 12)  # Centered dot
        dot_painter.end()
        self.quick_screenshot_btn.setIcon(QIcon(dot_pixmap))
        self.quick_screenshot_btn.setStyleSheet("""
            QPushButton {
                background: transparent;
                border: 2px solid #D4A017;
                border-radius: 4px;
            }
            QPushButton:hover {
                background: rgba(212, 160, 23, 0.2);
                border-color: #FFD700;
            }
            QPushButton:pressed {
                background: rgba(212, 160, 23, 0.4);
            }
        """)
        self.quick_screenshot_btn.clicked.connect(self._take_quick_screenshot)
        header_layout.addWidget(self.quick_screenshot_btn)
        
        # ====== COMPACT MODE: Region combo + Policy input ======
        # Placed after screenshot button. Only visible when docked.
        self.compact_region_combo = QComboBox()
        self.compact_region_combo.addItems(["CKPR", "CKMO", "CKAS", "CKSR"])
        self.compact_region_combo.setFixedHeight(28)
        self.compact_region_combo.setToolTip("Region")
        self.compact_region_combo.setStyleSheet("""
            QComboBox {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    stop:0 #1E5BA8, stop:1 #0D3A7A);
                border: 2px solid #D4A017;
                border-radius: 4px;
                color: #FFD700;
                font-size: 13px;
                font-weight: bold;
                font-family: 'Segoe UI', sans-serif;
                padding: 0px 6px;
            }
            QComboBox:hover {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    stop:0 #2A6FBF, stop:1 #1E5BA8);
                border-color: #FFD700;
            }
            QComboBox::drop-down {
                border: none;
                width: 0px;
            }
            QComboBox::down-arrow {
                image: none;
                width: 0px;
                height: 0px;
                border: none;
            }
            QComboBox QAbstractItemView {
                background: #0D3A7A;
                color: #FFD700;
                selection-background-color: #3A7DC8;
                selection-color: white;
                font-size: 13px;
                font-weight: bold;
                border: 1px solid #D4A017;
                outline: none;
            }
        """)
        self.compact_region_combo.hide()
        header_layout.addWidget(self.compact_region_combo)

        self.compact_policy_input = QLineEdit()
        self.compact_policy_input.setPlaceholderText("Policy #")
        self.compact_policy_input.setFixedWidth(100)
        self.compact_policy_input.setFixedHeight(28)
        self.compact_policy_input.setStyleSheet("""
            QLineEdit {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    stop:0 #1E5BA8, stop:1 #0D3A7A);
                border: 2px solid #D4A017;
                border-radius: 4px;
                color: #FFD700;
                font-size: 13px;
                font-weight: bold;
                font-family: 'Segoe UI', sans-serif;
                padding: 0px 4px;
            }
            QLineEdit:focus {
                border-color: #FFD700;
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    stop:0 #2A6FBF, stop:1 #1E5BA8);
            }
            QLineEdit::placeholder {
                color: rgba(212, 160, 23, 0.5);
            }
        """)
        self.compact_policy_input.setToolTip("Policy Number")
        self.compact_policy_input.returnPressed.connect(self._open_polview_with_policy)
        self.compact_policy_input.hide()
        header_layout.addWidget(self.compact_policy_input)

        # ====== POLVIEW BUTTON (green "P" with gold trim) ======
        self.polview_btn = QPushButton("P")
        self.polview_btn.setFixedSize(28, 28)
        self.polview_btn.setToolTip("Open PolView - Policy Viewer")
        self.polview_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.polview_btn.setStyleSheet("""
            QPushButton {
                background: #2E7D32;
                border: 2px solid #D4A017;
                border-radius: 4px;
                color: #FFD700;
                font-size: 14px;
                font-weight: bold;
                font-family: 'Segoe UI', sans-serif;
            }
            QPushButton:hover {
                background: #388E3C;
                border-color: #FFD700;
            }
            QPushButton:pressed {
                background: #1B5E20;
            }
        """)
        self.polview_btn.clicked.connect(self._polview_btn_clicked)
        header_layout.addWidget(self.polview_btn)

        # ====== FILE NAV BUTTON (gold "F" with blue trim) ======
        self.filenav_btn = QPushButton("F")
        self.filenav_btn.setFixedSize(28, 28)
        self.filenav_btn.setToolTip("Open File Navigator")
        self.filenav_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.filenav_btn.setStyleSheet("""
            QPushButton {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    stop:0 #1E5BA8, stop:1 #0D3A7A);
                border: 2px solid #D4A017;
                border-radius: 4px;
                color: #D4A017;
                font-size: 14px;
                font-weight: bold;
                font-family: 'Segoe UI', sans-serif;
            }
            QPushButton:hover {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    stop:0 #2A6FBF, stop:1 #1E5BA8);
                border-color: #FFD700;
            }
            QPushButton:pressed {
                background: #082B5C;
                border-color: #FFD700;
            }
        """)
        self.filenav_btn.clicked.connect(self._open_file_nav)
        header_layout.addWidget(self.filenav_btn)

        # ====== ABR QUOTE BUTTON (crimson "A" with slate-blue trim) ======
        self.abrquote_btn = QPushButton("A")
        self.abrquote_btn.setFixedSize(28, 28)
        self.abrquote_btn.setToolTip("Open ABR Quote Tool")
        self.abrquote_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.abrquote_btn.setStyleSheet("""
            QPushButton {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    stop:0 #8B1A2A, stop:1 #5C0A14);
                border: 2px solid #4A6FA5;
                border-radius: 4px;
                color: #B8D0F0;
                font-size: 14px;
                font-weight: bold;
                font-family: 'Segoe UI', sans-serif;
            }
            QPushButton:hover {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    stop:0 #A52535, stop:1 #8B1A2A);
                border-color: #7AA0D5;
                color: #D8E8FF;
            }
            QPushButton:pressed {
                background: #5C0A14;
                border-color: #2E4F85;
            }
        """)
        self.abrquote_btn.clicked.connect(self._open_abrquote)
        header_layout.addWidget(self.abrquote_btn)
        
        # ====== AUDIT BUTTON ("Q" — silver & blue) - DEV ONLY ======
        if DEV_MODE:
            self.audit_btn = QPushButton("Q")
            self.audit_btn.setFixedSize(28, 28)
            self.audit_btn.setToolTip("Open Audit Tool")
            self.audit_btn.setCursor(Qt.CursorShape.PointingHandCursor)
            self.audit_btn.setStyleSheet("""
                QPushButton {
                    background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                        stop:0 #D0D0D0, stop:1 #A0A0A0);
                    border: 2px solid #1E5BA8;
                    border-radius: 4px;
                    color: #1E5BA8;
                    font-size: 14px;
                    font-weight: bold;
                    font-family: 'Segoe UI', sans-serif;
                }
                QPushButton:hover {
                    background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                        stop:0 #E0E0E0, stop:1 #B0B0B0);
                    border-color: #2A6FBF;
                }
                QPushButton:pressed {
                    background: #909090;
                }
            """)
            self.audit_btn.clicked.connect(self._open_audit)
            header_layout.addWidget(self.audit_btn)
        
        # ====== WINDOW CAPTURE BUTTON (blue dot) - HIDDEN FOR NOW ======
        # Functionality preserved in _capture_active_window() for future use
        # self.window_capture_btn = QPushButton()
        # self.window_capture_btn.setFixedSize(28, 28)
        # self.window_capture_btn.setToolTip("Capture Active Window (saves to Screenshots folder)")
        # self.window_capture_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        # # Create icon with blue dot
        # win_dot_pixmap = QPixmap(24, 24)
        # win_dot_pixmap.fill(Qt.GlobalColor.transparent)
        # win_dot_painter = QPainter(win_dot_pixmap)
        # win_dot_painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        # win_dot_painter.setBrush(QBrush(QColor("#4A90D9")))  # Blue dot
        # win_dot_painter.setPen(Qt.PenStyle.NoPen)
        # win_dot_painter.drawEllipse(6, 6, 12, 12)  # Centered dot
        # win_dot_painter.end()
        # self.window_capture_btn.setIcon(QIcon(win_dot_pixmap))
        # self.window_capture_btn.setStyleSheet("""
        #     QPushButton {
        #         background: transparent;
        #         border: 2px solid #4A90D9;
        #         border-radius: 4px;
        #     }
        #     QPushButton:hover {
        #         background: rgba(74, 144, 217, 0.2);
        #         border-color: #6AB0F9;
        #     }
        #     QPushButton:pressed {
        #         background: rgba(74, 144, 217, 0.4);
        #     }
        # """)
        # self.window_capture_btn.clicked.connect(self._capture_active_window)
        # header_layout.addWidget(self.window_capture_btn)
        # ====== SCRATCHPAD BUTTON (📝 parchment green) ======
        self.scratchpad_window_btn = QPushButton("📝")
        self.scratchpad_window_btn.setFixedSize(28, 28)
        self.scratchpad_window_btn.setToolTip("Open ScratchPad")
        self.scratchpad_window_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.scratchpad_window_btn.setStyleSheet("""
            QPushButton {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    stop:0 #2D6A3F, stop:1 #163820);
                border: 2px solid #C8A84B;
                border-radius: 4px;
                font-size: 13px;
            }
            QPushButton:hover {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    stop:0 #3D8A55, stop:1 #2D6A3F);
                border-color: #E0C070;
            }
            QPushButton:pressed {
                background: #163820;
                border-color: #C8A84B;
            }
        """)
        self.scratchpad_window_btn.clicked.connect(self._toggle_scratchpad_window)
        header_layout.addWidget(self.scratchpad_window_btn)

        # ====== FILE OPEN HISTORY BUTTON (teal "H" with gold trim) ======
        self.file_history_btn = QPushButton("H")
        self.file_history_btn.setFixedSize(28, 28)
        self.file_history_btn.setToolTip("File Open History")
        self.file_history_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.file_history_btn.setStyleSheet("""
            QPushButton {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    stop:0 #1A7A6A, stop:1 #0D4A3F);
                border: 2px solid #D4A017;
                border-radius: 4px;
                color: #FFD700;
                font-size: 14px;
                font-weight: bold;
                font-family: 'Segoe UI', sans-serif;
            }
            QPushButton:hover {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    stop:0 #20907E, stop:1 #1A7A6A);
                border-color: #FFD700;
            }
            QPushButton:pressed {
                background: #0D4A3F;
            }
        """)
        self.file_history_btn.clicked.connect(self._toggle_file_open_history)
        header_layout.addWidget(self.file_history_btn)

        # Tools dropdown menu button - gold text only
        self.tools_menu_btn = QPushButton("Tools")
        self.tools_menu_btn.setStyleSheet("""
            QPushButton {
                background: transparent;
                border: none;
                padding: 4px 12px;
                color: #D4A017;
                font-size: 12px;
                font-weight: 600;
            }
            QPushButton:hover {
                color: #FFD700;
            }
            QPushButton::menu-indicator {
                image: none;
            }
        """)
        
        # Create Tools menu
        self.tools_menu = QMenu(self)
        self.tools_menu.setStyleSheet("""
            QMenu {
                background-color: #1E5BA8;
                border: 1px solid #D4A017;
                border-radius: 4px;
                padding: 4px;
            }
            QMenu::item {
                background-color: transparent;
                color: white;
                padding: 6px 20px;
                font-size: 11px;
            }
            QMenu::item:selected {
                background-color: #3A7DC8;
            }
        """)
        # Apps submenu
        self.tools_menu.addAction("View Screenshots", self._open_screenshot)
        # PolView, ABR Quote, and Mainframe Nav are always available
        self.tools_menu.addAction("PolView", self._open_polview)
        self.tools_menu.addAction("ABR Quote", self._open_abrquote)
        self.tools_menu.addAction("Mainframe Navigator", self._open_mainframe)
        if DEV_MODE:
            self.tools_menu.addAction("Email Attachments", self._open_email_attachments)
            self.tools_menu.addAction("Task Tracker", self._open_task_tracker)
            self.tools_menu.addAction("Audit Tool", self._open_audit)
            self.tools_menu.addAction("Rate File Converter", self._open_rate_manager)
        self.tools_menu.addSeparator()
        self.tools_menu.addAction("📁 App Data Location", self._open_app_data_location)
        self.tools_menu_btn.setMenu(self.tools_menu)
        header_layout.addWidget(self.tools_menu_btn)

        # Spacer between tools and window controls — hidden in compact mode
        self.header_spacer = QWidget()
        self.header_spacer.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        self.header_spacer.setMinimumWidth(20)
        header_layout.addWidget(self.header_spacer)

        # ====== MESSAGE NOTIFICATION BADGE (right side of bar) ======
        self.msg_badge_btn = QPushButton("✉")
        self.msg_badge_btn.setFixedSize(28, 28)
        self.msg_badge_btn.setToolTip("Messages")
        self.msg_badge_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.msg_badge_btn.setStyleSheet("""
            QPushButton {
                background: transparent;
                border: 2px solid #555;
                border-radius: 4px;
                color: #888;
                font-size: 14px;
            }
            QPushButton:hover {
                background: rgba(255, 255, 255, 0.1);
                border-color: #777;
            }
        """)
        self.msg_badge_btn.clicked.connect(self._toggle_msg_inbox)
        header_layout.addWidget(self.msg_badge_btn)

        # ====== WINDOW CONTROL BUTTONS ======
        window_btn_style = """
            QPushButton {
                background: transparent;
                border: none;
                border-radius: 0px;
                padding: 0px;
                min-width: 40px;
                max-width: 40px;
                min-height: 28px;
                max-height: 28px;
                font-size: 14px;
                font-weight: bold;
            }
        """
        
        # Minimize button - gold text
        self.minimize_btn = QPushButton("–")
        self.minimize_btn.setStyleSheet(window_btn_style + """
            QPushButton {
                color: #D4A017;
            }
            QPushButton:hover {
                background-color: rgba(255, 255, 255, 0.15);
                color: #FFD700;
            }
        """)
        self.minimize_btn.setToolTip("Minimize")
        self.minimize_btn.clicked.connect(self.showMinimized)
        header_layout.addWidget(self.minimize_btn)
        
        # Maximize/Restore button - gold text
        self.maximize_btn = QPushButton("□")
        self.maximize_btn.setStyleSheet(window_btn_style + """
            QPushButton {
                color: #D4A017;
            }
            QPushButton:hover {
                background-color: rgba(255, 255, 255, 0.15);
                color: #FFD700;
            }
        """)
        self.maximize_btn.setToolTip("Maximize")
        self.maximize_btn.clicked.connect(self._toggle_maximize)
        header_layout.addWidget(self.maximize_btn)
        
        # Close button - gold text
        self.close_btn = QPushButton("✕")
        self.close_btn.setStyleSheet(window_btn_style + """
            QPushButton {
                color: #D4A017;
            }
            QPushButton:hover {
                background-color: #E81123;
                color: #FFD700;
            }
        """)
        self.close_btn.setToolTip("Close to tray")
        self.close_btn.clicked.connect(self._hide_to_tray)
        header_layout.addWidget(self.close_btn)
        
        layout.addWidget(self.header_bar)
        
        # ====== TAB WIDGET ======
        self.tab_widget = QTabWidget()
        self.tab_widget.setTabsClosable(True)
        self.tab_widget.setMovable(True)
        self.tab_widget.setDocumentMode(True)
        # Allow tab widget to shrink to 0 so window can collapse to just header bar
        self.tab_widget.setMinimumSize(0, 0)
        self.tab_widget.setStyleSheet("""
            QTabWidget::pane {
                border: none;
                background: #CCE5F8;
            }
            QTabBar {
                background: #CCE5F8;
            }
            QTabBar::tab {
                padding: 6px 14px;
                margin-right: 2px;
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    stop:0 #4A7DC4, stop:1 #2A5AA4);
                color: white;
                font-weight: 600;
                font-size: 11px;
                border: 1px solid #1A4A94;
                border-bottom: none;
                border-top-left-radius: 4px;
                border-top-right-radius: 4px;
            }
            QTabBar::tab:selected {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    stop:0 #5A9DE8, stop:1 #3A7DC8);
                border-bottom: 3px solid #D4A017;
                color: white;
            }
            QTabBar::tab:!selected {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    stop:0 #3A6AB4, stop:1 #1A4A94);
                color: #C8DCF8;
            }
            QTabBar::tab:hover {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    stop:0 #5A8DD4, stop:1 #3A6AB4);
            }
        """)
        self.tab_widget.tabBar().setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.tab_widget.tabBar().customContextMenuRequested.connect(self.show_tab_bar_context_menu)
        
        # Tab bar controls
        self.tab_widget.tabCloseRequested.connect(self.close_tab)
        
        layout.addWidget(self.tab_widget)
        
        # ====== FOOTER BAR (PolView style) ======
        self.footer_bar = QFrame()
        self.footer_bar.setMaximumHeight(24)
        self.footer_bar.setMinimumHeight(0)  # Allow footer to collapse
        self.footer_bar.setStyleSheet("""
            QFrame {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    stop:0 #1E5BA8, stop:0.5 #0D3A7A, stop:1 #082B5C);
                border: none;
                border-top: 1px solid #D4A017;
            }
        """)
        footer_layout = QHBoxLayout(self.footer_bar)
        footer_layout.setContentsMargins(12, 2, 12, 2)
        footer_layout.setSpacing(8)
        
        self.footer_status = QLabel("Ready")
        self.footer_status.setStyleSheet("""
            QLabel {
                color: #D4A017;
                font-size: 15px;
                background: transparent;
            }
        """)
        footer_layout.addWidget(self.footer_status)
        
        # Set up callback for bookmark hover to update footer status
        set_footer_status_callback(lambda path: self.footer_status.setText(path if path else "Ready"))
        
        footer_layout.addStretch()
        
        self.footer_size = QLabel("")
        self.footer_size.setStyleSheet("""
            QLabel {
                color: #888888;
                font-size: 10px;
                background: transparent;
            }
        """)
        footer_layout.addWidget(self.footer_size)
        
        layout.addWidget(self.footer_bar)
        
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

        # Share splitter sizes across all tabs
        self._connect_tab_splitter(explorer_tab)
        
        return explorer_tab
    
    def _connect_tab_splitter(self, tab):
        """Connect tab's splitter to shared size management"""
        if not hasattr(tab, 'main_splitter'):
            return
        
        # If we have shared sizes, apply them to this tab
        if self._shared_splitter_sizes:
            tab.main_splitter.setSizes(self._shared_splitter_sizes)
        else:
            # First tab - capture its sizes as the shared sizes
            self._shared_splitter_sizes = tab.main_splitter.sizes()
        
        # Connect splitter movement to sync across all tabs
        tab.main_splitter.splitterMoved.connect(
            lambda pos, idx: self._on_tab_splitter_moved(tab)
        )
    
    def _on_tab_splitter_moved(self, source_tab):
        """When any tab's splitter moves, sync to all other tabs"""
        if self._syncing_splitter:
            return
        
        self._syncing_splitter = True
        try:
            # Get the new sizes from the tab that was moved
            new_sizes = source_tab.main_splitter.sizes()
            self._shared_splitter_sizes = new_sizes
            
            # Apply to all other tabs
            for i in range(self.tab_widget.count()):
                tab = self.tab_widget.widget(i)
                if tab is not source_tab and hasattr(tab, 'main_splitter'):
                    tab.main_splitter.setSizes(new_sizes)
        finally:
            self._syncing_splitter = False
    
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
    
    def _header_add_bookmark(self):
        """Delegate Add Bookmark to current tab"""
        current_tab = self.get_current_tab()
        if current_tab and hasattr(current_tab, '_add_bookmark'):
            current_tab._add_bookmark()
    
    def _header_print_directory(self):
        """Delegate Print Directory to current tab"""
        current_tab = self.get_current_tab()
        if current_tab and hasattr(current_tab, 'print_directory_to_excel'):
            current_tab.print_directory_to_excel()
    
    def _header_batch_rename(self):
        """Delegate Batch Rename to current tab"""
        current_tab = self.get_current_tab()
        if current_tab and hasattr(current_tab, 'batch_rename_files'):
            current_tab.batch_rename_files()
    
    def _header_open_in_explorer(self):
        """Delegate Open in Explorer to current tab"""
        current_tab = self.get_current_tab()
        if current_tab and hasattr(current_tab, 'open_in_explorer'):
            current_tab.open_in_explorer()
    
    def update_footer_status(self, message):
        """Update the footer status text"""
        if hasattr(self, 'footer_status'):
            self.footer_status.setText(message)

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

    # ====== CUSTOM TITLE BAR METHODS ======
    
    def _toggle_maximize(self):
        """Toggle between maximized and normal window state"""
        if self._is_maximized:
            self.showNormal()
            self._is_maximized = False
            self.maximize_btn.setText("☐")
            self.maximize_btn.setToolTip("Maximize")
        else:
            self.showMaximized()
            self._is_maximized = True
            self.maximize_btn.setText("❐")
            self.maximize_btn.setToolTip("Restore")
    
    def _toggle_compact_mode(self):
        """Toggle between compact mode (mini bar) and normal mode.
        
        Called by double-clicking the SuiteView label.
        Three states:
        - Full window         → collapse to docked compact bar
        - Docked compact bar  → undock to floating mini-bar
        - Floating mini-bar   → re-dock to compact bar
        """
        if getattr(self, '_is_floating_mode', False):
            # Floating → re-dock to compact bar
            self._exit_floating_mode()
            self._enter_compact_mode(initial=False)
        elif self._is_compact_mode:
            # Docked compact → undock to floating mini-bar
            self._enter_floating_mode()
        else:
            # Full window → docked compact
            self._enter_compact_mode(initial=False)

    def _enter_floating_mode(self):
        """Undock the compact bar into a short, draggable floating bar.
        
        Shows only:  SuiteView [ P ] [ F ] [ A ] [ Q ] [✕]
        The bar becomes draggable and is not docked to the taskbar.
        """
        # First unregister appbar so the desktop work area is restored
        self._unregister_appbar()

        # Hide everything except the core tool buttons
        if hasattr(self, 'tab_widget'):
            self.tab_widget.hide()
        if hasattr(self, 'footer_bar'):
            self.footer_bar.hide()
        if hasattr(self, 'sidebar_container'):
            self.sidebar_container.hide()
        if hasattr(self, 'minimize_btn'):
            self.minimize_btn.hide()
        if hasattr(self, 'maximize_btn'):
            self.maximize_btn.hide()
        if hasattr(self, 'header_spacer'):
            self.header_spacer.hide()

        # Hide compact-mode policy lookup inputs (not needed in floating)
        if hasattr(self, 'compact_region_combo'):
            self.compact_region_combo.hide()
        if hasattr(self, 'compact_policy_input'):
            self.compact_policy_input.hide()

        # Hide the screenshot button, tools menu, scratchpad, audit icon (floating shows only P/F/A/Q)
        if hasattr(self, 'quick_screenshot_btn'):
            self.quick_screenshot_btn.hide()
        if hasattr(self, 'tools_menu_btn'):
            self.tools_menu_btn.hide()
        if hasattr(self, 'scratchpad_window_btn'):
            self.scratchpad_window_btn.hide()
        if hasattr(self, 'file_history_btn'):
            self.file_history_btn.hide()

        # Ensure the core buttons are visible: P, F, A, Q
        if hasattr(self, 'polview_btn'):
            self.polview_btn.show()
        if hasattr(self, 'filenav_btn'):
            self.filenav_btn.show()
        if hasattr(self, 'abrquote_btn'):
            self.abrquote_btn.show()
        if hasattr(self, 'audit_btn'):
            self.audit_btn.show()
        if hasattr(self, 'close_btn'):
            self.close_btn.show()

        # Set height to just the header
        bar_h = 42
        self.setMinimumSize(100, bar_h)
        self.setMaximumHeight(bar_h)

        # Calculate a short width: roughly 320px to hold the buttons
        bar_w = 320

        # Position: center of screen, near bottom (above taskbar)
        avail = QApplication.primaryScreen().availableGeometry()
        bar_x = avail.x() + (avail.width() - bar_w) // 2
        bar_y = avail.bottom() - bar_h - 10  # 10px above bottom

        # Keep stay-on-top but as a normal floating window
        was_visible = self.isVisible()
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint
                            | Qt.WindowType.WindowMinMaxButtonsHint
                            | Qt.WindowType.WindowStaysOnTopHint)
        self.setGeometry(bar_x, bar_y, bar_w, bar_h)
        if was_visible:
            self.show()

        # Restore taskbar icon so user can click on it
        try:
            import ctypes
            hwnd = int(self.winId())
            GWL_EXSTYLE = -20
            WS_EX_TOOLWINDOW = 0x00000080
            WS_EX_APPWINDOW  = 0x00040000
            user32 = ctypes.windll.user32
            ex_style = user32.GetWindowLongW(hwnd, GWL_EXSTYLE)
            ex_style = (ex_style | WS_EX_TOOLWINDOW) & ~WS_EX_APPWINDOW
            user32.SetWindowLongW(hwnd, GWL_EXSTYLE, ex_style)
            user32.ShowWindow(hwnd, 0)  # SW_HIDE
            user32.ShowWindow(hwnd, 5)  # SW_SHOW
        except Exception:
            pass

        self._is_compact_mode = False
        self._is_floating_mode = True

    def _exit_floating_mode(self):
        """Exit floating mini-bar mode (caller will re-dock or restore)."""
        self._is_floating_mode = False

        # Remove height cap
        self.setMaximumHeight(16777215)
        self.setMinimumSize(330, 40)

        # Restore all header widgets to their proper visibility
        # (the caller — _enter_compact_mode or _exit_compact_mode — will
        #  handle showing/hiding the right widgets for the target state)
        if hasattr(self, 'quick_screenshot_btn'):
            self.quick_screenshot_btn.show()
        if hasattr(self, 'tools_menu_btn'):
            self.tools_menu_btn.show()
        if hasattr(self, 'header_spacer'):
            self.header_spacer.show()
    
    def _enter_compact_mode(self, initial=False):
        """Collapse to the compact mini-bar docked above the taskbar.

        The bar spans the FULL screen width and sits immediately above the
        Windows taskbar.  SPI_SETWORKAREA then shrinks the desktop work area
        so its bottom edge aligns with the TOP of our bar — exactly like
        docking a new toolbar.  The bar is NOT draggable while docked.

        Args:
            initial: True when called at startup (no stored geometry yet).
        """
        # Store current full-window geometry so we can restore it later
        if not initial:
            self._stored_geometry = self.geometry()

        # --- Hide content widgets ---
        if hasattr(self, 'tab_widget'):
            self.tab_widget.hide()
        if hasattr(self, 'footer_bar'):
            self.footer_bar.hide()
        if hasattr(self, 'sidebar_container'):
            self.sidebar_container.hide()
        # Hide minimize and maximize — not needed in docked bar
        if hasattr(self, 'minimize_btn'):
            self.minimize_btn.hide()
        if hasattr(self, 'maximize_btn'):
            self.maximize_btn.hide()
        # Keep close_btn visible so user can quit to tray
        if hasattr(self, 'close_btn'):
            self.close_btn.show()
        # Keep the stretch spacer — pushes ✕ to the far right across the full width
        if hasattr(self, 'header_spacer'):
            self.header_spacer.show()
        # Show compact-mode policy lookup inputs
        if hasattr(self, 'compact_region_combo'):
            self.compact_region_combo.show()
        if hasattr(self, 'compact_policy_input'):
            self.compact_policy_input.show()

        # Shrink to just the header bar height
        bar_h = 42  # header height + 2 px border top/bottom
        self.setMinimumSize(100, bar_h)
        self.setMaximumHeight(bar_h)

        # availableGeometry() gives us the screen EXCLUDING the taskbar.
        # We sit immediately above the taskbar: x=0, y = avail.bottom() - bar_h
        # Width = full physical screen width so we span edge-to-edge.
        avail  = QApplication.primaryScreen().availableGeometry()
        full   = QApplication.primaryScreen().geometry()
        bar_w  = full.width()
        bar_x  = full.left()
        bar_y  = avail.bottom() - bar_h        # just above the taskbar

        # Apply always-on-top Qt flag — requires hide/show to take effect
        was_visible = self.isVisible()
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint
                            | Qt.WindowType.WindowMinMaxButtonsHint
                            | Qt.WindowType.WindowStaysOnTopHint)
        self.setGeometry(bar_x, bar_y, bar_w, bar_h)
        if was_visible:
            self.show()

        # Hide from taskbar using native Windows API (reliable, unlike Qt Tool flag)
        try:
            import ctypes
            hwnd = int(self.winId())
            GWL_EXSTYLE = -20
            WS_EX_TOOLWINDOW = 0x00000080
            WS_EX_APPWINDOW  = 0x00040000
            user32 = ctypes.windll.user32
            ex_style = user32.GetWindowLongW(hwnd, GWL_EXSTYLE)
            ex_style = (ex_style | WS_EX_TOOLWINDOW) & ~WS_EX_APPWINDOW
            user32.SetWindowLongW(hwnd, GWL_EXSTYLE, ex_style)
            # Force shell to notice the change
            user32.ShowWindow(hwnd, 0)  # SW_HIDE
            user32.ShowWindow(hwnd, 5)  # SW_SHOW
        except Exception:
            pass

        self._is_compact_mode = True

        # Register as a Windows AppBar so the shell reserves screen space.
        # This must happen AFTER the window is shown (so winId() is valid).
        self._register_appbar(bar_h)

    # ------------------------------------------------------------------
    #  Windows AppBar API – proper desktop space reservation
    # ------------------------------------------------------------------
    #  Instead of the fragile SPI_SETWORKAREA (which can be overridden by
    #  Explorer at any time), we register our window as an "AppBar" using
    #  SHAppBarMessage.  This is the same mechanism the Windows taskbar
    #  uses and is the officially supported way to dock a toolbar and
    #  have other windows respect the reserved space.
    #
    #  Flow:  ABM_NEW  →  ABM_QUERYPOS  →  ABM_SETPOS  →  SetWindowPos
    #  Tear-down:  ABM_REMOVE
    # ------------------------------------------------------------------

    def _register_appbar(self, bar_h: int):
        """Register this window as a Windows AppBar docked to the bottom edge.

        The shell will shrink the desktop work area by *bar_h* pixels at the
        bottom so maximised / snapped windows never overlap our bar.
        """
        try:
            import ctypes
            import ctypes.wintypes as wt

            # ---- struct definitions ------------------------------------
            class RECT(ctypes.Structure):
                _fields_ = [('left', wt.LONG), ('top', wt.LONG),
                             ('right', wt.LONG), ('bottom', wt.LONG)]

            class APPBARDATA(ctypes.Structure):
                _fields_ = [
                    ('cbSize',           wt.DWORD),
                    ('hWnd',             wt.HWND),
                    ('uCallbackMessage', wt.UINT),
                    ('uEdge',            wt.UINT),
                    ('rc',               RECT),
                    ('lParam',           ctypes.c_void_p),
                ]

            # ---- constants ---------------------------------------------
            ABM_NEW      = 0x00
            ABM_REMOVE   = 0x01
            ABM_QUERYPOS = 0x02
            ABM_SETPOS   = 0x03
            ABE_BOTTOM   = 3

            SWP_NOZORDER    = 0x0004
            SWP_NOACTIVATE  = 0x0010
            SWP_SHOWWINDOW  = 0x0040

            shell32 = ctypes.windll.shell32
            user32  = ctypes.windll.user32

            # Prototype so ctypes knows the return type
            shell32.SHAppBarMessage.restype  = wt.ULONG
            user32.RegisterWindowMessageW.restype = wt.UINT

            # ---- native window handle ----------------------------------
            hwnd = int(self.winId())

            # ---- monitor geometry (physical pixels) --------------------
            # We query the full monitor rect via the Win32 API so we are
            # always in physical-pixel space, matching APPBARDATA.rc.
            class MONITORINFO(ctypes.Structure):
                _fields_ = [('cbSize', wt.DWORD),
                             ('rcMonitor', RECT),
                             ('rcWork', RECT),
                             ('dwFlags', wt.DWORD)]

            MONITOR_DEFAULTTONEAREST = 2
            hMon = user32.MonitorFromWindow(hwnd, MONITOR_DEFAULTTONEAREST)
            mi = MONITORINFO()
            mi.cbSize = ctypes.sizeof(MONITORINFO)
            user32.GetMonitorInfoW(hMon, ctypes.byref(mi))

            mon_left   = mi.rcMonitor.left
            mon_top    = mi.rcMonitor.top
            mon_right  = mi.rcMonitor.right
            mon_bottom = mi.rcMonitor.bottom

            # Convert bar_h from Qt logical pixels → physical pixels
            dpr = QApplication.primaryScreen().devicePixelRatio()
            bar_h_phys = round(bar_h * dpr)

            # ---- build APPBARDATA --------------------------------------
            abd = APPBARDATA()
            abd.cbSize = ctypes.sizeof(APPBARDATA)
            abd.hWnd   = hwnd
            abd.uCallbackMessage = user32.RegisterWindowMessageW("SuiteView_AppBar")
            abd.uEdge  = ABE_BOTTOM
            abd.rc.left   = mon_left
            abd.rc.top    = mon_bottom - bar_h_phys
            abd.rc.right  = mon_right
            abd.rc.bottom = mon_bottom

            # 1) Register
            result = shell32.SHAppBarMessage(ABM_NEW, ctypes.byref(abd))
            if not result:
                import logging
                logging.getLogger(__name__).warning("SHAppBarMessage ABM_NEW failed")
                return

            # 2) Let the shell negotiate the rectangle
            shell32.SHAppBarMessage(ABM_QUERYPOS, ctypes.byref(abd))

            # After QUERYPOS the shell may have adjusted rc.top (e.g. if
            # another appbar is already on that edge).  Fix rc.bottom so
            # the height stays what we asked for.
            abd.rc.top = abd.rc.bottom - bar_h_phys

            # 3) Lock the rectangle
            shell32.SHAppBarMessage(ABM_SETPOS, ctypes.byref(abd))

            # 4) Move our window into the approved rectangle
            user32.SetWindowPos(
                hwnd, 0,
                abd.rc.left, abd.rc.top,
                abd.rc.right - abd.rc.left,
                abd.rc.bottom - abd.rc.top,
                SWP_NOZORDER | SWP_NOACTIVATE | SWP_SHOWWINDOW)

            # Remember that we registered so we can unregister later
            self._appbar_registered = True

            import logging
            logging.getLogger(__name__).info(
                f"AppBar registered: rect=({abd.rc.left},{abd.rc.top},"
                f"{abd.rc.right},{abd.rc.bottom})")

        except Exception as exc:
            import logging
            logging.getLogger(__name__).error(f"AppBar registration failed: {exc}")

    def _unregister_appbar(self):
        """Unregister the AppBar so the shell restores the full work area."""
        try:
            if not getattr(self, '_appbar_registered', False):
                return
            import ctypes
            import ctypes.wintypes as wt

            class RECT(ctypes.Structure):
                _fields_ = [('left', wt.LONG), ('top', wt.LONG),
                             ('right', wt.LONG), ('bottom', wt.LONG)]

            class APPBARDATA(ctypes.Structure):
                _fields_ = [
                    ('cbSize',           wt.DWORD),
                    ('hWnd',             wt.HWND),
                    ('uCallbackMessage', wt.UINT),
                    ('uEdge',            wt.UINT),
                    ('rc',               RECT),
                    ('lParam',           ctypes.c_void_p),
                ]

            ABM_REMOVE = 0x01

            abd = APPBARDATA()
            abd.cbSize = ctypes.sizeof(APPBARDATA)
            abd.hWnd   = int(self.winId())

            ctypes.windll.shell32.SHAppBarMessage(ABM_REMOVE, ctypes.byref(abd))
            self._appbar_registered = False

            import logging
            logging.getLogger(__name__).info("AppBar unregistered — work area restored")

        except Exception as exc:
            import logging
            logging.getLogger(__name__).error(f"AppBar unregister failed: {exc}")

    def _exit_compact_mode(self):
        """Expand from compact mini-bar back to the full window."""
        # Unregister the AppBar FIRST, before repositioning our window
        self._unregister_appbar()

        # Remember where the bar was so we can return to it later
        self._compact_bar_pos = self.geometry().topLeft()

        # Remove the height cap
        self.setMaximumHeight(16777215)  # Qt's QWIDGETSIZE_MAX
        self.setMinimumSize(330, 40)

        # Restore content widgets
        if hasattr(self, 'tab_widget'):
            self.tab_widget.show()
        if hasattr(self, 'footer_bar'):
            self.footer_bar.show()
        if hasattr(self, 'sidebar_container'):
            self.sidebar_container.show()
        if hasattr(self, 'minimize_btn'):
            self.minimize_btn.show()
        if hasattr(self, 'maximize_btn'):
            self.maximize_btn.show()
        if hasattr(self, 'close_btn'):
            self.close_btn.show()
        if hasattr(self, 'header_spacer'):
            self.header_spacer.show()
        # Hide compact-mode policy lookup inputs
        if hasattr(self, 'compact_region_combo'):
            self.compact_region_combo.hide()
        if hasattr(self, 'compact_policy_input'):
            self.compact_policy_input.hide()

        # Determine target geometry before touching flags
        if self._stored_geometry:
            target_geo = self._stored_geometry
        else:
            screen = QApplication.primaryScreen().availableGeometry()
            w, h = 1400, 800
            x = screen.x() + (screen.width() - w) // 2
            y = screen.y() + (screen.height() - h) // 2
            from PyQt6.QtCore import QRect
            target_geo = QRect(x, y, w, h)

        # Remove always-on-top flag — requires hide/show on Windows to take effect
        was_visible = self.isVisible()

        # Restore taskbar icon: remove WS_EX_TOOLWINDOW before changing Qt flags
        try:
            import ctypes
            hwnd = int(self.winId())
            GWL_EXSTYLE = -20
            WS_EX_TOOLWINDOW = 0x00000080
            WS_EX_APPWINDOW  = 0x00040000
            user32 = ctypes.windll.user32
            ex_style = user32.GetWindowLongW(hwnd, GWL_EXSTYLE)
            ex_style = (ex_style & ~WS_EX_TOOLWINDOW) | WS_EX_APPWINDOW
            user32.SetWindowLongW(hwnd, GWL_EXSTYLE, ex_style)
        except Exception:
            pass

        self.setWindowFlags(Qt.WindowType.FramelessWindowHint
                            | Qt.WindowType.WindowMinMaxButtonsHint)
        self.setGeometry(target_geo)
        if was_visible:
            self.show()
            self.activateWindow()
            self.raise_()

        self._is_compact_mode = False

    
    def _get_resize_edge(self, pos):
        """Determine which edge/corner is being hovered for resize"""
        margin = self._resize_margin
        rect = self.rect()
        
        left = pos.x() < margin
        right = pos.x() > rect.width() - margin
        top = pos.y() < margin
        bottom = pos.y() > rect.height() - margin
        
        if top and left:
            return 'top-left'
        elif top and right:
            return 'top-right'
        elif bottom and left:
            return 'bottom-left'
        elif bottom and right:
            return 'bottom-right'
        elif left:
            return 'left'
        elif right:
            return 'right'
        elif top:
            return 'top'
        elif bottom:
            return 'bottom'
        return None
    
    def _update_cursor_for_edge(self, edge):
        """Update cursor based on resize edge"""
        cursors = {
            'left': Qt.CursorShape.SizeHorCursor,
            'right': Qt.CursorShape.SizeHorCursor,
            'top': Qt.CursorShape.SizeVerCursor,
            'bottom': Qt.CursorShape.SizeVerCursor,
            'top-left': Qt.CursorShape.SizeFDiagCursor,
            'bottom-right': Qt.CursorShape.SizeFDiagCursor,
            'top-right': Qt.CursorShape.SizeBDiagCursor,
            'bottom-left': Qt.CursorShape.SizeBDiagCursor,
        }
        if edge in cursors:
            self.setCursor(cursors[edge])
        else:
            self.unsetCursor()
    
    def mousePressEvent(self, event):
        """Handle mouse press for dragging and resizing"""
        # Right-click anywhere on the bar → show bookmark bars popup
        if event.button() == Qt.MouseButton.RightButton:
            # Don't show popup if clicking on a button
            widget_at = self.childAt(event.pos())
            import PyQt6.QtWidgets as _qw
            if not isinstance(widget_at, (QPushButton, _qw.QComboBox, _qw.QLineEdit, _qw.QAbstractButton)):
                self._show_bookmark_bars_popup(event.globalPosition().toPoint())
                event.accept()
                return

        # Docked compact bar is not movable or resizable
        if self._is_compact_mode:
            super().mousePressEvent(event)
            return
        
        if event.button() == Qt.MouseButton.LeftButton:
            pos = event.pos()
            
            # Check if we're on a resize edge (not in floating mode)
            if not getattr(self, '_is_floating_mode', False):
                edge = self._get_resize_edge(pos)
                if edge and not self._is_maximized:
                    self._resizing = True
                    self._resize_edge = edge
                    self._resize_start_pos = event.globalPosition().toPoint()
                    self._start_geometry = self.geometry()
                    event.accept()
                    return
            
            # Check if we're in the header bar (for dragging)
            header_rect = self.header_bar.geometry()
            if header_rect.contains(pos):
                # Don't drag if clicking on buttons
                widget_at = self.childAt(pos)
                if isinstance(widget_at, QPushButton):
                    super().mousePressEvent(event)
                    return
                
                self._drag_pos = event.globalPosition().toPoint()
                event.accept()
                return
        
        super().mousePressEvent(event)

    def _show_bookmark_bars_popup(self, global_pos):
        """Show a floating popup with all bookmark bars as vertical panels."""
        # Close any existing popup before opening a new one.
        # (No timestamp guard — a right-click elsewhere on the bar should
        # close the old popup AND immediately reopen at the new position.)
        if hasattr(self, '_bookmark_popup') and self._bookmark_popup is not None:
            try:
                self._bookmark_popup.close()
            except RuntimeError:
                pass
            self._bookmark_popup = None

        popup = BookmarkBarsPopup(parent_bar=self)
        popup.bookmark_activated.connect(self._on_popup_bookmark_activated)
        self._bookmark_popup = popup

        # Size the popup first so we know its dimensions
        popup.adjustSize()
        popup_height = popup.sizeHint().height()
        popup_width  = popup.sizeHint().width()

        # Prefer to show above the click; if not enough room, show below
        bar_geo = self.geometry()
        y = bar_geo.top() - popup_height - 4
        if y < 0:
            y = bar_geo.bottom() + 4

        # Horizontally: centre the popup on the right-click X position,
        # clamped so it stays fully on screen.
        screen = QApplication.primaryScreen().availableGeometry()
        x = global_pos.x() - popup_width // 2
        x = max(screen.left(), min(x, screen.right() - popup_width))

        popup.move(x, y)
        popup.show()
        popup.raise_()
        popup.activateWindow()

    def _on_popup_bookmark_activated(self, path):
        """Handle a bookmark activation from the popup.

        Folder bookmarks open in the FileNav window so the SuiteView compact
        bar stays right where it is.
        Files are opened with the default application.
        URLs are opened in the browser.
        """
        # Close the popup first
        if hasattr(self, '_bookmark_popup') and self._bookmark_popup is not None:
            try:
                self._bookmark_popup.close()
            except RuntimeError:
                pass
            self._bookmark_popup = None

        import webbrowser
        from pathlib import Path as _Path

        if not path:
            return

        if path.startswith('http://') or path.startswith('https://'):
            webbrowser.open(path)
        elif _Path(path).is_dir():
            # Open the folder in the FileNav window — SuiteView bar stays put
            self._open_file_nav_at(path)
        else:
            try:
                os.startfile(path)
            except Exception as e:
                logger.error(f"Failed to open bookmark path: {e}")

    def _open_file_nav_at(self, path):
        """Open (or reuse) the FileNav window and navigate it to *path*."""
        # Guard against stale C++ wrapped object
        if self.file_nav_window is not None:
            try:
                _ = self.file_nav_window.isVisible()
            except RuntimeError:
                self.file_nav_window = None

        if self.file_nav_window is None:
            try:
                self.file_nav_window = FileNavWindow(parent_bar=self)
                self._setup_child_window(self.file_nav_window, "FileNav")
            except Exception as e:
                import traceback
                logger.error(f"Failed to open File Navigator: {e}\n{traceback.format_exc()}")
                return

        # Show / raise the window
        self._bring_to_front(self.file_nav_window)

        # Navigate the current (or a new) tab to the requested folder
        try:
            current_tab = self.file_nav_window.tab_widget.currentWidget()
            if current_tab and hasattr(current_tab, 'navigate_to_bookmark_folder'):
                current_tab.navigate_to_bookmark_folder(path)
            elif current_tab and hasattr(current_tab, 'navigate_to_path'):
                current_tab.navigate_to_path(path)
        except Exception as e:
            logger.error(f"FileNav navigation failed: {e}")
    
    def mouseMoveEvent(self, event):
        """Handle mouse move for dragging and resizing"""
        # Docked compact bar is not movable or resizable — just pass through
        if self._is_compact_mode:
            super().mouseMoveEvent(event)
            return
        
        pos = event.pos()
        
        # Update cursor when not pressing
        if not event.buttons():
            edge = self._get_resize_edge(pos)
            self._update_cursor_for_edge(edge)
            super().mouseMoveEvent(event)
            return
        
        if event.buttons() == Qt.MouseButton.LeftButton:
            # Handle resizing (takes priority - check first)
            if self._resizing and self._resize_edge and self._resize_start_pos is not None:
                delta = event.globalPosition().toPoint() - self._resize_start_pos
                geo = self._start_geometry
                
                new_x, new_y = geo.x(), geo.y()
                new_w, new_h = geo.width(), geo.height()
                min_w, min_h = 330, 46  # Allow shrinking to just header bar
                
                # For left/top edges, we need to keep the opposite edge fixed
                # Calculate the fixed edges
                right_edge = geo.x() + geo.width()
                bottom_edge = geo.y() + geo.height()
                
                if 'left' in self._resize_edge:
                    new_w = max(min_w, geo.width() - delta.x())
                    new_x = right_edge - new_w  # Keep right edge fixed
                if 'right' in self._resize_edge:
                    new_w = max(min_w, geo.width() + delta.x())
                if 'top' in self._resize_edge:
                    new_h = max(min_h, geo.height() - delta.y())
                    new_y = bottom_edge - new_h  # Keep bottom edge fixed
                if 'bottom' in self._resize_edge:
                    new_h = max(min_h, geo.height() + delta.y())
                
                self.setGeometry(new_x, new_y, new_w, new_h)
                event.accept()
                return
            
            # Handle dragging (only if not resizing)
            if self._drag_pos is not None and not self._resizing:
                # If maximized, restore and center on cursor
                if self._is_maximized:
                    self._is_maximized = False
                    self.showNormal()
                    self.maximize_btn.setText("☐")
                    # Reposition so cursor is centered on title bar
                    new_geo = self.geometry()
                    self._drag_pos = event.globalPosition().toPoint()
                    self.move(
                        self._drag_pos.x() - new_geo.width() // 2,
                        self._drag_pos.y() - 20
                    )
                else:
                    delta = event.globalPosition().toPoint() - self._drag_pos
                    self.move(self.pos() + delta)
                    self._drag_pos = event.globalPosition().toPoint()
                event.accept()
                return
        
        super().mouseMoveEvent(event)
    
    def mouseReleaseEvent(self, event):
        """Handle mouse release"""
        self._drag_pos = None
        self._resizing = False
        self._resize_edge = None
        self._resize_start_pos = None
        super().mouseReleaseEvent(event)
    
    def mouseDoubleClickEvent(self, event):
        """Handle double-click on title bar.
        
        - Double-click on the SuiteView label → toggle compact/full mode
          (handled by the label's own mouseDoubleClickEvent override)
        - Double-click elsewhere on header (not a button) → maximize/restore (full mode only)
        """
        if event.button() == Qt.MouseButton.LeftButton:
            header_rect = self.header_bar.geometry()
            if header_rect.contains(event.pos()):
                widget_at = self.childAt(event.pos())
                # Maximize/restore when double-clicking empty header space (full mode only)
                if not isinstance(widget_at, QPushButton) and not self._is_compact_mode:
                    self._toggle_maximize()
                    event.accept()
                    return
        super().mouseDoubleClickEvent(event)
    
    def paintEvent(self, event):
        """Paint a gold border around the frameless window.
        
        In compact mode the bottom border is the most visible element —
        draw it slightly thicker for emphasis.
        """
        super().paintEvent(event)
        from PyQt6.QtGui import QPainter, QColor, QPen
        painter = QPainter(self)
        r = self.rect().adjusted(1, 1, -1, -1)
        # Draw the full gold border (all four sides)
        painter.setPen(QPen(QColor("#D4A017"), 2))
        painter.drawRect(r)
        # Extra-thick bottom gold accent (signature mini-bar look)
        painter.setPen(QPen(QColor("#D4A017"), 3))
        painter.drawLine(r.bottomLeft(), r.bottomRight())
        painter.end()


# =============================================================================
# BookmarkBarsPopup — Right-click popup showing all bookmark bars vertically
# =============================================================================

class BookmarkBarsPopup(QWidget):
    """
    Frameless popup that appears when the user right-clicks the SuiteView bar.
    Displays one vertical BookmarkContainer panel per configured bookmark bar,
    side-by-side, so every bar and its categories/bookmarks are visible at once.
    Closes when the user clicks outside the popup or activates a bookmark.
    """
    # Emitted with the path when a bookmark is clicked
    bookmark_activated = pyqtSignal(str)

    def __init__(self, parent_bar=None):
        super().__init__(parent=None)  # Top-level so it floats above everything
        self._parent_bar = parent_bar
        self._containers = []  # Keep refs so they don't get GC'd

        # Use Tool | FramelessWindowHint | WindowStaysOnTopHint instead of
        # Qt.WindowType.Popup.  The Popup flag auto-closes but it also
        # re-delivers the dismissing click to whatever Qt widget is underneath,
        # which caused a CategoryButton on the SuiteView bar to open its
        # popup immediately after the bookmark popup closed.
        # Instead we use an application-level event filter (below) to close
        # the popup when the user clicks outside it.
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint |
            Qt.WindowType.Tool |
            Qt.WindowType.WindowStaysOnTopHint
        )

        self._build_ui()

        # Install an application-level event filter to detect outside clicks.
        # This is the same mechanism used by QMenu and QComboBox dropdowns
        # when NOT using the Popup window flag.
        QApplication.instance().installEventFilter(self)

    def _build_ui(self):
        """Build the popup UI: one panel per bar, populated with bookmark buttons.

        We intentionally do NOT create new BookmarkContainer instances here because
        doing so would:
        1. Overwrite the existing registry entries for each bar_id, breaking
           cross-bar drag-and-drop on the live containers.
        2. Mutate the stored orientation in the data manager for bar 0 (horizontal)
           since we want vertical orientation in the popup.

        Instead we read raw data from the BookmarkDataManager and build lightweight
        read-only panels using StandaloneBookmarkButton and CategoryButton directly.
        """
        from suiteview.ui.widgets.bookmark_data_manager import get_bookmark_manager
        from suiteview.ui.widgets.bookmark_widgets import (
            StandaloneBookmarkButton, CategoryButton
        )
        from PyQt6.QtWidgets import QScrollArea

        manager = get_bookmark_manager()
        bar_ids = manager.get_all_bar_ids()

        # ── Outer styling ────────────────────────────────────────────────────
        self.setStyleSheet("""
            BookmarkBarsPopup {
                background: #0D3A7A;
                border: 2px solid #D4A017;
                border-radius: 6px;
            }
        """)

        outer_layout = QVBoxLayout(self)
        outer_layout.setContentsMargins(6, 6, 6, 6)
        outer_layout.setSpacing(0)

        # ── Header ───────────────────────────────────────────────────────────
        header = QLabel("📌  Bookmarks")
        header.setStyleSheet("""
            QLabel {
                color: #D4A017;
                font-size: 11pt;
                font-weight: bold;
                font-family: 'Segoe UI', sans-serif;
                background: transparent;
                padding: 4px 8px 6px 8px;
                border-bottom: 1px solid #D4A017;
            }
        """)
        outer_layout.addWidget(header)

        # ── Panel row ────────────────────────────────────────────────────────
        panels_frame = QFrame()
        panels_frame.setStyleSheet("QFrame { background: transparent; border: none; }")
        panels_layout = QHBoxLayout(panels_frame)
        panels_layout.setContentsMargins(4, 6, 4, 4)
        panels_layout.setSpacing(10)

        PANEL_WIDTH = 220
        PANEL_MAX_HEIGHT = 460

        _panels_built = 0

        for bar_id in bar_ids:
            bar_data = manager.get_bar_data(bar_id)
            items = bar_data.get('items', [])

            # Skip bars with no items
            if not items:
                continue

            bar_name = bar_data.get('name', f"Bookmark Bar {bar_id + 1}")

            # ── Per-bar outer panel ──────────────────────────────────────────
            panel = QFrame()
            panel.setFixedWidth(PANEL_WIDTH)
            panel.setMaximumHeight(PANEL_MAX_HEIGHT)
            panel.setStyleSheet("""
                QFrame {
                    background: #9EC8EE;
                    border: 1px solid #5A9FD8;
                    border-radius: 5px;
                }
            """)
            panel_layout = QVBoxLayout(panel)
            panel_layout.setContentsMargins(0, 0, 0, 0)
            panel_layout.setSpacing(0)

            # Bar title
            title_lbl = QLabel(bar_name)
            title_lbl.setStyleSheet("""
                QLabel {
                    color: #FFD700;
                    font-size: 9pt;
                    font-weight: bold;
                    font-family: 'Segoe UI', sans-serif;
                    background: #0D3A7A;
                    padding: 4px 8px;
                    border-bottom: 1px solid #3A7DC8;
                    border-top-left-radius: 4px;
                    border-top-right-radius: 4px;
                    border-bottom-left-radius: 0px;
                    border-bottom-right-radius: 0px;
                }
            """)
            panel_layout.addWidget(title_lbl)

            # Scroll area for items
            scroll = QScrollArea()
            scroll.setWidgetResizable(True)
            scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
            scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
            scroll.setFrameShape(QFrame.Shape.NoFrame)
            scroll.setStyleSheet("""
                QScrollArea { background: transparent; border: none; }
                QScrollArea > QWidget > QWidget { background: transparent; }
                QScrollBar:vertical {
                    background: #0D3A7A;
                    width: 6px;
                    margin: 0;
                    border-radius: 3px;
                }
                QScrollBar::handle:vertical {
                    background: #D4A017;
                    border-radius: 3px;
                    min-height: 20px;
                }
                QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
            """)

            # Items container
            items_widget = QWidget()
            items_widget.setStyleSheet("background: transparent;")
            items_layout = QVBoxLayout(items_widget)
            items_layout.setContentsMargins(4, 4, 4, 4)
            items_layout.setSpacing(2)
            items_layout.setAlignment(Qt.AlignmentFlag.AlignTop)

            # ── Populate items ───────────────────────────────────────────────
            for idx, item_data in enumerate(items):
                item_type = item_data.get('type')

                if item_type == 'bookmark':
                    bm = {
                        'name': item_data.get('name', ''),
                        'path': item_data.get('path', ''),
                        'id': item_data.get('id'),
                    }
                    btn = StandaloneBookmarkButton(
                        bookmark_data=bm,
                        item_index=idx,
                        parent=items_widget,
                        container=None,
                        orientation='vertical'
                    )
                    btn.clicked_path.connect(self.bookmark_activated.emit)
                    # Also close the popup on ANY click (including URLs, which the
                    # button handles internally without emitting clicked_path).
                    btn.clicked.connect(self.close)
                    items_layout.addWidget(btn)

                elif item_type == 'category':
                    cat_items = []
                    subcats = []
                    for child in item_data.get('items', []):
                        if child.get('type') == 'bookmark':
                            cat_items.append({
                                'name': child.get('name', ''),
                                'path': child.get('path', ''),
                                'id': child.get('id'),
                            })
                        elif child.get('type') == 'category':
                            subcats.append(child.get('name', ''))

                    cat_btn = CategoryButton(
                        category_name=item_data.get('name', ''),
                        category_items=cat_items,
                        subcategories=subcats,
                        item_index=idx,
                        parent=items_widget,
                        data_manager=None,    # read-only popup — no editing
                        source_bar_id=bar_id,
                        orientation='vertical',
                        color=item_data.get('color'),
                        category_id=item_data.get('id'),
                    )
                    cat_btn.item_clicked.connect(self.bookmark_activated.emit)
                    items_layout.addWidget(cat_btn)

            items_layout.addStretch()
            scroll.setWidget(items_widget)
            panel_layout.addWidget(scroll)

            panels_layout.addWidget(panel)
            _panels_built += 1

        outer_layout.addWidget(panels_frame)

        # ── Fallback: no bookmarks ───────────────────────────────────────────
        if _panels_built == 0:
            placeholder = QLabel("No bookmarks yet.\nRight-click a folder in SuiteView\nto add bookmarks.")
            placeholder.setAlignment(Qt.AlignmentFlag.AlignCenter)
            placeholder.setStyleSheet("""
                QLabel {
                    color: #A0B8D8;
                    font-size: 10pt;
                    font-style: italic;
                    font-family: 'Segoe UI', sans-serif;
                    padding: 28px;
                }
            """)
            outer_layout.addWidget(placeholder)

        self.adjustSize()

    def eventFilter(self, obj, event):
        """Close the popup when the user clicks outside it and all its child popups."""
        if event.type() == QEvent.Type.MouseButtonPress:
            # Get global click position
            try:
                global_pos = event.globalPosition().toPoint()
            except AttributeError:
                global_pos = event.globalPos()

            # Click is inside our own window — keep open
            if self.geometry().contains(global_pos):
                return False

            # Click might be inside a CategoryPopup opened from one of our
            # CategoryButtons (those float as separate windows but have a parent
            # widget, so they appear in allWidgets(), not topLevelWidgets()).
            from suiteview.ui.widgets.bookmark_widgets import CategoryPopup
            for widget in QApplication.allWidgets():
                if isinstance(widget, CategoryPopup) and widget.isVisible():
                    if widget.geometry().contains(global_pos):
                        return False  # Click inside a child category popup — stay open

            # Genuinely outside — close
            QApplication.instance().removeEventFilter(self)
            self.close()
            if self._parent_bar is not None:
                try:
                    self._parent_bar._bookmark_popup = None
                except Exception:
                    pass

        return False  # Never consume the event

    def closeEvent(self, event):
        """Remove event filter on close."""
        try:
            QApplication.instance().removeEventFilter(self)
        except Exception:
            pass
        super().closeEvent(event)

    def changeEvent(self, event):
        """Close when the app loses OS-level activation (click on desktop / taskbar / other app)."""
        from PyQt6.QtCore import QEvent as _QEvent
        if event.type() == _QEvent.Type.ActivationChange and not self.isActiveWindow():
            # Don't close if a CategoryPopup just took activation — the user
            # may be clicking a bookmark inside one of our category panels.
            from suiteview.ui.widgets.bookmark_widgets import CategoryPopup
            active_win = QApplication.activeWindow()
            if not isinstance(active_win, CategoryPopup):
                import time as _time
                QApplication.instance().removeEventFilter(self)
                if self._parent_bar is not None:
                    try:
                        self._parent_bar._bookmark_popup = None
                    except Exception:
                        pass
                self.close()
        super().changeEvent(event)

    def paintEvent(self, event):
        """Draw blue/gold border around the popup."""
        super().paintEvent(event)
        from PyQt6.QtGui import QPainter, QColor, QPen
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        r = self.rect().adjusted(1, 1, -1, -1)
        painter.setPen(QPen(QColor("#D4A017"), 2))
        painter.setBrush(QColor("#0D3A7A"))
        painter.drawRoundedRect(r, 5, 5)
        painter.end()


# =============================================================================
# FileNavWindow — Standalone File Navigator window (Blue & Gold theme)
# =============================================================================

class FileNavWindow(QWidget):
    """Standalone File Navigator window with classic Blue & Gold theme.
    
    This window provides the full file explorer experience (multi-tab,
    breadcrumb navigation, bookmarks) in a separate window launched from
    the SuiteView compact bar's [F] button.
    
    Color theme: Blue & Gold — same as the SuiteView bar
      - Header gradient: #1E5BA8 → #082B5C  (blue)
      - Accent / border: #D4A017  (gold)
      - Text on headers: #D4A017  (gold on blue)
    """

    # --- Classic Blue & Gold palette (matches SuiteView bar) ---
    _BLUE_START  = "#1E5BA8"   # Blue gradient top
    _BLUE_MID    = "#0D3A7A"   # Blue gradient mid
    _BLUE_END    = "#082B5C"   # Blue gradient bottom
    _BLUE_LIGHT  = "#2A6FBF"   # Lighter blue accent / hover
    _GOLD_PRIMARY = "#D4A017"  # Primary gold (text, accents)
    _GOLD_BRIGHT  = "#FFD700"  # Bright gold (highlights, hover)
    _PANEL_BG     = "#CCE5F8"  # Light blue panel background

    def __init__(self, parent_bar=None):
        super().__init__()
        self._parent_bar = parent_bar  # Reference to SuiteView compact bar

        # Frameless window setup
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowMinMaxButtonsHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, False)
        self.setMinimumSize(600, 400)

        # Enable mouse tracking for resize
        self.setMouseTracking(True)

        # Drag tracking
        self._drag_pos = None
        self._is_maximized = False

        # Snap-to-edge state
        self._is_snapped = False
        self._normal_geometry = None
        self._snap_preview = None
        self._snap_edge_threshold = 10  # px from screen edge to trigger snap

        # Resize edge detection
        self._resize_margin = 6
        self._resizing = False
        self._resize_edge = None
        self._resize_start_pos = None
        self._start_geometry = None

        # Shared splitter sizes
        self._shared_splitter_sizes = None
        self._syncing_splitter = False

        self._init_ui()
        self._add_resize_grips()

        # Create initial tab
        self.add_new_tab()

        # Position at center of screen
        screen = QApplication.primaryScreen().availableGeometry()
        w, h = 1400, 800
        x = screen.x() + (screen.width() - w) // 2
        y = screen.y() + (screen.height() - h) // 2
        self.setGeometry(x, y, w, h)

    # ------------------------------------------------------------------
    #  UI Construction
    # ------------------------------------------------------------------
    def _init_ui(self):
        """Build the FileNav window UI with classic Blue & Gold theme."""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(2, 2, 2, 2)
        layout.setSpacing(0)

        # Global scrollbar styling — blue-tinted (matching SuiteView bar)
        self.setStyleSheet("""
            QScrollBar:vertical {
                background: #E0ECFF;
                width: 12px;
                margin: 0;
                border-radius: 6px;
            }
            QScrollBar::handle:vertical {
                background: #1E5BA8;
                min-height: 20px;
                border-radius: 5px;
                margin: 1px;
            }
            QScrollBar::handle:vertical:hover {
                background: #2A6FBF;
            }
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
                height: 0; background: none;
            }
            QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {
                background: none;
            }
            QScrollBar:horizontal {
                background: #E0ECFF;
                height: 12px;
                margin: 0;
                border-radius: 6px;
            }
            QScrollBar::handle:horizontal {
                background: #1E5BA8;
                min-width: 20px;
                border-radius: 5px;
                margin: 1px;
            }
            QScrollBar::handle:horizontal:hover {
                background: #2A6FBF;
            }
            QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {
                width: 0; background: none;
            }
            QScrollBar::add-page:horizontal, QScrollBar::sub-page:horizontal {
                background: none;
            }
        """)

        # ====== HEADER BAR (Blue gradient with gold accents — same as SuiteView) ======
        self.header_bar = QFrame()
        self.header_bar.setFixedHeight(38)
        self.header_bar.setMouseTracking(True)
        self.header_bar.setStyleSheet(f"""
            QFrame {{
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    stop:0 {self._BLUE_START}, stop:0.5 {self._BLUE_MID},
                    stop:1 {self._BLUE_END});
                border: none;
            }}
        """)
        self.header_bar.setCursor(Qt.CursorShape.ArrowCursor)
        header_layout = QHBoxLayout(self.header_bar)
        header_layout.setContentsMargins(12, 4, 8, 4)
        header_layout.setSpacing(8)

        # Title — "FileNav" in gold on blue
        self.title_label = QLabel("FileNav")
        self.title_label.setStyleSheet(f"""
            QLabel {{
                color: {self._GOLD_PRIMARY};
                font-size: 18px;
                font-weight: bold;
                font-style: italic;
                background: transparent;
                padding-right: 4px;
            }}
        """)
        header_layout.addWidget(self.title_label)

        # ====== TOOLS DROPDOWN MENU ======
        self.tools_menu_btn = QPushButton("Tools")
        self.tools_menu_btn.setStyleSheet(f"""
            QPushButton {{
                background: transparent;
                border: none;
                padding: 4px 12px;
                color: {self._GOLD_PRIMARY};
                font-size: 12px;
                font-weight: 600;
            }}
            QPushButton:hover {{
                color: {self._GOLD_BRIGHT};
            }}
            QPushButton::menu-indicator {{
                image: none;
            }}
        """)

        self.tools_menu = QMenu(self)
        self.tools_menu.setStyleSheet(f"""
            QMenu {{
                background-color: {self._BLUE_START};
                border: 1px solid {self._GOLD_PRIMARY};
                border-radius: 4px;
                padding: 4px;
            }}
            QMenu::item {{
                background-color: transparent;
                color: white;
                padding: 6px 20px;
                font-size: 11px;
            }}
            QMenu::item:selected {{
                background-color: #3A7DC8;
            }}
        """)
        self.tools_menu.addAction("Print Directory", self._tools_print_directory)
        self.tools_menu.addAction("Batch Rename", self._tools_batch_rename)
        self.tools_menu_btn.setMenu(self.tools_menu)
        header_layout.addWidget(self.tools_menu_btn)

        # Spacer pushes window controls to the right
        header_spacer = QWidget()
        header_spacer.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        header_spacer.setMinimumWidth(20)
        header_layout.addWidget(header_spacer)

        # ====== WINDOW CONTROL BUTTONS (gold text on blue) ======
        window_btn_style = """
            QPushButton {
                background: transparent;
                border: none;
                border-radius: 0px;
                padding: 0px;
                min-width: 40px;
                max-width: 40px;
                min-height: 28px;
                max-height: 28px;
                font-size: 14px;
                font-weight: bold;
            }
        """

        # Minimize
        self.minimize_btn = QPushButton("–")
        self.minimize_btn.setStyleSheet(window_btn_style + f"""
            QPushButton {{ color: {self._GOLD_PRIMARY}; }}
            QPushButton:hover {{
                background-color: rgba(255, 255, 255, 0.15);
                color: {self._GOLD_BRIGHT};
            }}
        """)
        self.minimize_btn.setToolTip("Minimize")
        self.minimize_btn.clicked.connect(self.showMinimized)
        header_layout.addWidget(self.minimize_btn)

        # Maximize / Restore
        self.maximize_btn = QPushButton("□")
        self.maximize_btn.setStyleSheet(window_btn_style + f"""
            QPushButton {{ color: {self._GOLD_PRIMARY}; }}
            QPushButton:hover {{
                background-color: rgba(255, 255, 255, 0.15);
                color: {self._GOLD_BRIGHT};
            }}
        """)
        self.maximize_btn.setToolTip("Maximize")
        self.maximize_btn.clicked.connect(self._toggle_maximize)
        header_layout.addWidget(self.maximize_btn)

        # Close
        self.close_btn = QPushButton("✕")
        self.close_btn.setStyleSheet(window_btn_style + f"""
            QPushButton {{ color: {self._GOLD_PRIMARY}; }}
            QPushButton:hover {{
                background-color: #E81123;
                color: {self._GOLD_BRIGHT};
            }}
        """)
        self.close_btn.setToolTip("Close")
        self.close_btn.clicked.connect(self.hide)
        header_layout.addWidget(self.close_btn)

        layout.addWidget(self.header_bar)

        # ====== TAB WIDGET (Blue & Gold themed tabs — same as SuiteView) ======
        self.tab_widget = QTabWidget()
        self.tab_widget.setTabsClosable(True)
        self.tab_widget.setMovable(True)
        self.tab_widget.setDocumentMode(True)
        self.tab_widget.setMinimumSize(0, 0)
        self.tab_widget.setStyleSheet(f"""
            QTabWidget::pane {{
                border: none;
                background: {self._PANEL_BG};
            }}
            QTabBar {{
                background: {self._PANEL_BG};
            }}
            QTabBar::tab {{
                padding: 6px 14px;
                margin-right: 2px;
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    stop:0 #4A7DC4, stop:1 #2A5AA4);
                color: white;
                font-weight: 600;
                font-size: 11px;
                border: 1px solid #1A4A94;
                border-bottom: none;
                border-top-left-radius: 4px;
                border-top-right-radius: 4px;
            }}
            QTabBar::tab:selected {{
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    stop:0 #5A9DE8, stop:1 #3A7DC8);
                border-bottom: 3px solid {self._GOLD_PRIMARY};
                color: white;
            }}
            QTabBar::tab:!selected {{
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    stop:0 #3A6AB4, stop:1 #1A4A94);
                color: #C8DCF8;
            }}
            QTabBar::tab:hover {{
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    stop:0 #5A8DD4, stop:1 #3A6AB4);
            }}
        """)
        self.tab_widget.tabBar().setContextMenuPolicy(
            Qt.ContextMenuPolicy.CustomContextMenu)
        self.tab_widget.tabBar().customContextMenuRequested.connect(
            self._show_tab_bar_context_menu)
        self.tab_widget.tabCloseRequested.connect(self.close_tab)
        self.tab_widget.currentChanged.connect(self._on_tab_switched)

        layout.addWidget(self.tab_widget)

        # ====== FOOTER BAR (Blue & Gold — same as SuiteView) ======
        self.footer_bar = QFrame()
        self.footer_bar.setMaximumHeight(24)
        self.footer_bar.setMinimumHeight(0)
        self.footer_bar.setStyleSheet(f"""
            QFrame {{
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    stop:0 {self._BLUE_START}, stop:0.5 {self._BLUE_MID},
                    stop:1 {self._BLUE_END});
                border: none;
                border-top: 1px solid {self._GOLD_PRIMARY};
            }}
        """)
        footer_layout = QHBoxLayout(self.footer_bar)
        footer_layout.setContentsMargins(12, 2, 12, 2)
        footer_layout.setSpacing(8)

        self.footer_status = QLabel("Ready")
        self.footer_status.setStyleSheet(f"""
            QLabel {{
                color: {self._GOLD_PRIMARY};
                font-size: 15px;
                background: transparent;
            }}
        """)
        footer_layout.addWidget(self.footer_status)

        # Register global footer callback so bookmark hover shows path in this footer
        set_footer_status_callback(
            lambda path: self.footer_status.setText(path if path else "Ready")
        )
        footer_layout.addStretch()

        self.footer_size = QLabel("")
        self.footer_size.setStyleSheet("""
            QLabel {
                color: #666666;
                font-size: 10px;
                background: transparent;
            }
        """)
        footer_layout.addWidget(self.footer_size)

        layout.addWidget(self.footer_bar)

    # ------------------------------------------------------------------
    #  Tab management
    # ------------------------------------------------------------------
    def add_new_tab(self, path=None, title=None):
        """Add a new file explorer tab."""
        tab = FileExplorerTab(initial_path=path)
        tab.path_changed.connect(
            lambda p, t=tab: self._update_tab_title(t, p))

        display_title = title or "OneDrive"
        index = self.tab_widget.addTab(tab, display_title)
        self.tab_widget.setCurrentIndex(index)
        self._style_close_button(index)
        self._connect_tab_splitter(tab)
        return tab

    def _connect_tab_splitter(self, tab):
        """Connect a tab's splitter to shared size management."""
        if hasattr(tab, 'main_splitter'):
            tab.main_splitter.splitterMoved.connect(
                lambda: self._on_tab_splitter_moved(tab))
            if self._shared_splitter_sizes:
                tab.main_splitter.setSizes(self._shared_splitter_sizes)

    def _on_tab_splitter_moved(self, source_tab):
        """Sync splitter sizes across all tabs."""
        if self._syncing_splitter:
            return
        self._syncing_splitter = True
        try:
            sizes = source_tab.main_splitter.sizes()
            self._shared_splitter_sizes = sizes
            for i in range(self.tab_widget.count()):
                other = self.tab_widget.widget(i)
                if other is not source_tab and hasattr(other, 'main_splitter'):
                    other.main_splitter.setSizes(sizes)
        finally:
            self._syncing_splitter = False

    def close_tab(self, index):
        """Close a tab (keep at least one)."""
        if self.tab_widget.count() > 1:
            widget = self.tab_widget.widget(index)

            # Disconnect signals to prevent crashes during cleanup
            if widget:
                try:
                    if hasattr(widget, 'depth_level_combo'):
                        widget.depth_level_combo.currentTextChanged.disconnect()
                    if hasattr(widget, 'path_changed'):
                        widget.path_changed.disconnect()
                    if hasattr(widget, 'details_search'):
                        widget.details_search.textChanged.disconnect()
                    if hasattr(widget, 'depth_search_enabled') and widget.depth_search_enabled:
                        widget.depth_search_enabled = False
                        widget.depth_search_locked = False
                        widget.depth_search_active_results = None
                    # Unregister BookmarkContainers from global registry
                    from suiteview.ui.widgets.bookmark_widgets import BookmarkContainerRegistry
                    if hasattr(widget, 'bookmark_bar'):
                        BookmarkContainerRegistry.unregister(
                            widget.bookmark_bar.bar_id, widget.bookmark_bar)
                    if hasattr(widget, 'bookmark_container'):
                        BookmarkContainerRegistry.unregister(
                            widget.bookmark_container.bar_id, widget.bookmark_container)
                except Exception as e:
                    logger.error(f"Error during FileNav tab cleanup: {e}")

            self.tab_widget.removeTab(index)
            if widget:
                widget.deleteLater()
        elif self.tab_widget.count() == 1:
            # Last tab: just reset it
            tab = self.tab_widget.widget(0)
            if hasattr(tab, 'go_to_onedrive_home'):
                tab.go_to_onedrive_home()
            self.tab_widget.setTabText(0, "OneDrive")

    def _update_tab_title(self, tab, path):
        """Update tab title when path changes."""
        idx = self.tab_widget.indexOf(tab)
        if idx >= 0:
            p = Path(path)
            name = p.name or str(p)
            self.tab_widget.setTabText(idx, name)
            self.tab_widget.setTabToolTip(idx, str(p))

    def _on_tab_switched(self, index):
        """Handle tab switch — wrapped in try/except for crash diagnostics."""
        try:
            widget = self.tab_widget.widget(index)
            if widget and hasattr(widget, 'current_details_folder'):
                folder = widget.current_details_folder
                if folder:
                    self.footer_status.setText(folder)
        except Exception as e:
            import traceback
            tb = traceback.format_exc()
            logger.error(f"FileNav tab switch error (tab {index}): {e}\n{tb}")
            # Also write to crash log for diagnostics
            try:
                crash_file = Path.home() / '.suiteview' / 'filenav_crash.log'
                crash_file.parent.mkdir(parents=True, exist_ok=True)
                from datetime import datetime
                with open(crash_file, 'a') as f:
                    f.write(f"\n{'='*60}\n")
                    f.write(f"FileNav tab switch crash at {datetime.now()}\n")
                    f.write(f"Tab index: {index}\n")
                    f.write(tb)
                    f.write(f"{'='*60}\n")
            except Exception:
                pass

    def get_current_tab(self):
        """Get currently active tab."""
        return self.tab_widget.currentWidget()

    # ------------------------------------------------------------------
    #  Tools menu actions
    # ------------------------------------------------------------------
    def _tools_print_directory(self):
        """Delegate Print Directory to current tab."""
        current_tab = self.get_current_tab()
        if current_tab and hasattr(current_tab, 'print_directory_to_excel'):
            current_tab.print_directory_to_excel()

    def _tools_batch_rename(self):
        """Delegate Batch Rename to current tab."""
        current_tab = self.get_current_tab()
        if current_tab and hasattr(current_tab, 'batch_rename_files'):
            current_tab.batch_rename_files()

    def _show_tab_bar_context_menu(self, pos):
        """Tab bar right-click menu."""
        tab_bar = self.tab_widget.tabBar()
        index = tab_bar.tabAt(pos)
        menu = QMenu(self)
        menu.setStyleSheet(f"""
            QMenu {{
                background-color: {self._BLUE_START};
                border: 1px solid {self._GOLD_PRIMARY};
                border-radius: 4px;
                padding: 4px;
            }}
            QMenu::item {{
                background-color: transparent;
                color: {self._GOLD_PRIMARY};
                padding: 6px 20px;
                font-size: 11px;
            }}
            QMenu::item:selected {{
                background-color: {self._GOLD_BRIGHT};
            }}
        """)
        if index >= 0:
            menu.addAction("Duplicate Tab",
                           lambda: self._duplicate_tab(index))
        menu.addAction("New Tab", self.add_new_tab)
        menu.exec(tab_bar.mapToGlobal(pos))

    def _duplicate_tab(self, index):
        """Duplicate the given tab."""
        source = self.tab_widget.widget(index)
        if source and hasattr(source, 'current_details_folder'):
            folder = source.current_details_folder
            title = self.tab_widget.tabText(index)
            self.add_new_tab(path=folder, title=title)

    def _style_close_button(self, index):
        """Replace the platform-drawn close button with a QToolButton showing a subtle gold ✕.

        Qt's built-in QTabBar close button is rendered by the platform style engine and
        ignores CSS color / icon overrides — so we swap it out entirely via setTabButton().

        Uses the same approach as SuiteViewTaskbar (QToolButton + tabCloseRequested)
        which is proven to work reliably across all tabs.
        """
        tab_bar = self.tab_widget.tabBar()

        close_btn = QToolButton(tab_bar)
        close_btn.setAutoRaise(True)
        close_btn.setText("✕")
        close_btn.setToolTip("Close Tab")
        close_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        close_btn.setStyleSheet(f"""
            QToolButton {{
                background: transparent;
                color: {self._GOLD_PRIMARY};
                border: none;
                font-size: 12px;
                font-weight: 700;
                padding: 0px;
                min-width: 14px;
            }}
            QToolButton:hover {{
                color: {self._GOLD_BRIGHT};
            }}
        """)
        close_btn.clicked.connect(lambda _: self._emit_close_for_button(close_btn))
        tab_bar.setTabButton(index, QTabBar.ButtonPosition.RightSide, close_btn)

    def _emit_close_for_button(self, button):
        """Map custom close button clicks to the correct tab index."""
        tab_bar = self.tab_widget.tabBar()
        for idx in range(tab_bar.count()):
            if tab_bar.tabButton(idx, QTabBar.ButtonPosition.RightSide) is button:
                self.tab_widget.tabCloseRequested.emit(idx)
                return

    # ------------------------------------------------------------------
    #  Window controls
    # ------------------------------------------------------------------
    def _toggle_maximize(self):
        """Toggle maximized / normal."""
        if self._is_maximized:
            self.showNormal()
            self.maximize_btn.setText("□")
            self._is_maximized = False
            self._is_snapped = False
            self._normal_geometry = None
        else:
            if not self._is_maximized and not self._is_snapped:
                self._normal_geometry = self.geometry()
            self.showMaximized()
            self.maximize_btn.setText("❐")
            self._is_maximized = True
            self._is_snapped = False

    # ------------------------------------------------------------------
    #  Resize grips
    # ------------------------------------------------------------------
    def _add_resize_grips(self):
        """Add resize grips to edges for frameless window resizing."""
        from PyQt6.QtWidgets import QSizeGrip
        self.size_grip = QSizeGrip(self)
        self.size_grip.setStyleSheet("QSizeGrip { background: transparent; }")

        self._resize_widgets = []
        edges = ['top', 'bottom', 'left', 'right',
                 'top-left', 'top-right', 'bottom-left']
        for edge in edges:
            widget = _ResizeEdge(self, edge)
            self._resize_widgets.append((edge, widget))

    def resizeEvent(self, event):
        """Reposition resize widgets and update size label."""
        super().resizeEvent(event)
        w, h = self.width(), self.height()
        margin = 6

        if hasattr(self, 'footer_bar') and hasattr(self, 'tab_widget'):
            if h < 70:
                self.footer_bar.hide()
                self.tab_widget.hide()
            elif h < 100:
                self.footer_bar.hide()
                self.tab_widget.show()
            else:
                self.footer_bar.show()
                self.tab_widget.show()

        if hasattr(self, 'size_grip'):
            self.size_grip.move(w - 16, h - 16)
            self.size_grip.raise_()

        if hasattr(self, '_resize_widgets'):
            for edge_name, widget in self._resize_widgets:
                if edge_name == 'top':
                    widget.setGeometry(margin, 0, w - 2*margin, margin)
                elif edge_name == 'bottom':
                    widget.setGeometry(margin, h - margin, w - 2*margin, margin)
                elif edge_name == 'left':
                    widget.setGeometry(0, margin, margin, h - 2*margin)
                elif edge_name == 'right':
                    widget.setGeometry(w - margin, margin, margin, h - 2*margin)
                elif edge_name == 'top-left':
                    widget.setGeometry(0, 0, margin, margin)
                elif edge_name == 'top-right':
                    widget.setGeometry(w - margin, 0, margin, margin)
                elif edge_name == 'bottom-left':
                    widget.setGeometry(0, h - margin, margin, margin)
                widget.raise_()

        # Update footer size label
        if hasattr(self, 'footer_size'):
            self.footer_size.setText(f"{w} × {h}")

    # ------------------------------------------------------------------
    #  Snap-to-edge helpers
    # ------------------------------------------------------------------
    def _detect_snap_edge(self, global_pos):
        """Return 'left' or 'right' if global_pos is near a screen edge."""
        screen = QApplication.screenAt(global_pos)
        if screen is None:
            return None
        avail = screen.availableGeometry()
        threshold = self._snap_edge_threshold
        if global_pos.x() <= avail.left() + threshold:
            return 'left'
        if global_pos.x() >= avail.right() - threshold:
            return 'right'
        return None

    def _show_snap_preview(self, edge, global_pos):
        """Show a translucent overlay on the target half of the screen."""
        from suiteview.ui.widgets.frameless_window import _SnapPreview
        screen = QApplication.screenAt(global_pos)
        if screen is None:
            return
        avail = screen.availableGeometry()
        if edge == 'left':
            target = QRect(avail.x(), avail.y(),
                           avail.width() // 2, avail.height())
        else:
            half_w = avail.width() // 2
            target = QRect(avail.x() + half_w, avail.y(),
                           avail.width() - half_w, avail.height())
        if self._snap_preview is None:
            self._snap_preview = _SnapPreview()
        self._snap_preview.setGeometry(target)
        self._snap_preview.show()

    def _hide_snap_preview(self):
        if self._snap_preview is not None:
            self._snap_preview.hide()
            self._snap_preview.deleteLater()
            self._snap_preview = None

    def _snap_to_edge(self, edge, global_pos):
        """Snap the window to the left or right half of the screen."""
        screen = QApplication.screenAt(global_pos)
        if screen is None:
            return
        avail = screen.availableGeometry()
        if not self._is_snapped and not self._is_maximized:
            self._normal_geometry = self.geometry()
        if edge == 'left':
            target = QRect(avail.x(), avail.y(),
                           avail.width() // 2, avail.height())
        else:
            half_w = avail.width() // 2
            target = QRect(avail.x() + half_w, avail.y(),
                           avail.width() - half_w, avail.height())
        self.setGeometry(target)
        self._is_snapped = True
        self._is_maximized = False
        self.maximize_btn.setText("□")

    # ------------------------------------------------------------------
    #  Mouse handling (drag & resize)
    # ------------------------------------------------------------------
    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            header_rect = self.header_bar.geometry()
            if header_rect.contains(event.pos()):
                widget_at = self.childAt(event.pos())
                if not isinstance(widget_at, QPushButton):
                    self._drag_pos = event.globalPosition().toPoint() - self.frameGeometry().topLeft()
                    event.accept()
                    return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self._drag_pos is not None and event.buttons() == Qt.MouseButton.LeftButton:
            global_pos = event.globalPosition().toPoint()

            # Un-snap on drag (restore previous window size)
            if self._is_snapped:
                self._is_snapped = False
                restore_geo = self._normal_geometry or QRect(0, 0, 1400, 800)
                self._normal_geometry = None
                cursor = global_pos
                new_w = restore_geo.width()
                self.resize(new_w, restore_geo.height())
                self.move(cursor.x() - new_w // 2, cursor.y() - 20)
                self._drag_pos = cursor - self.frameGeometry().topLeft()
            else:
                self.move(global_pos - self._drag_pos)

            # Show / hide snap preview while dragging
            snap_edge = self._detect_snap_edge(global_pos)
            if snap_edge:
                self._show_snap_preview(snap_edge, global_pos)
            else:
                self._hide_snap_preview()

            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if self._drag_pos is not None:
            global_pos = event.globalPosition().toPoint()
            snap_edge = self._detect_snap_edge(global_pos)
            if snap_edge and not self._is_maximized:
                self._snap_to_edge(snap_edge, global_pos)
            self._hide_snap_preview()
        self._drag_pos = None
        super().mouseReleaseEvent(event)

    def mouseDoubleClickEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            header_rect = self.header_bar.geometry()
            if header_rect.contains(event.pos()):
                widget_at = self.childAt(event.pos())
                if not isinstance(widget_at, QPushButton):
                    self._toggle_maximize()
                    event.accept()
                    return
        super().mouseDoubleClickEvent(event)

    # ------------------------------------------------------------------
    #  Paint — blue border with gold accent
    # ------------------------------------------------------------------
    def paintEvent(self, event):
        super().paintEvent(event)
        painter = QPainter(self)
        r = self.rect().adjusted(1, 1, -1, -1)
        painter.setPen(QPen(QColor(self._GOLD_PRIMARY), 2))
        painter.drawRect(r)
        painter.setPen(QPen(QColor(self._GOLD_PRIMARY), 3))
        painter.drawLine(r.bottomLeft(), r.bottomRight())
        painter.end()


class _ResizeEdge(QWidget):
    """Invisible edge widget for frameless window resizing."""

    def __init__(self, parent, edge):
        super().__init__(parent)
        self.edge = edge
        self.parent_window = parent
        self.setMouseTracking(True)
        self.setCursor(self._get_cursor())
        self.setStyleSheet("background-color: transparent;")
        self._dragging = False
        self._start_pos = None
        self._start_geometry = None

    def _get_cursor(self):
        curmap = {
            'top': Qt.CursorShape.SizeVerCursor,
            'bottom': Qt.CursorShape.SizeVerCursor,
            'left': Qt.CursorShape.SizeHorCursor,
            'right': Qt.CursorShape.SizeHorCursor,
            'top-left': Qt.CursorShape.SizeFDiagCursor,
            'bottom-right': Qt.CursorShape.SizeFDiagCursor,
            'top-right': Qt.CursorShape.SizeBDiagCursor,
            'bottom-left': Qt.CursorShape.SizeBDiagCursor,
        }
        return curmap.get(self.edge, Qt.CursorShape.ArrowCursor)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._dragging = True
            self._start_pos = event.globalPosition().toPoint()
            self._start_geometry = self.parent_window.geometry()

    def mouseMoveEvent(self, event):
        if not self._dragging:
            return
        gp = event.globalPosition().toPoint()
        dx = gp.x() - self._start_pos.x()
        dy = gp.y() - self._start_pos.y()
        g = self._start_geometry
        new_x, new_y = g.x(), g.y()
        new_w, new_h = g.width(), g.height()

        if 'left' in self.edge:
            new_x = g.x() + dx
            new_w = g.width() - dx
        if 'right' in self.edge:
            new_w = g.width() + dx
        if 'top' in self.edge:
            new_y = g.y() + dy
            new_h = g.height() - dy
        if 'bottom' in self.edge:
            new_h = g.height() + dy

        min_w = self.parent_window.minimumWidth()
        min_h = self.parent_window.minimumHeight()
        if new_w >= min_w and new_h >= min_h:
            self.parent_window.setGeometry(new_x, new_y, new_w, new_h)

    def mouseReleaseEvent(self, event):
        self._dragging = False
