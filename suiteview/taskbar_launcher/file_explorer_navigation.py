"""Navigation, breadcrumb, and history mixin for FileExplorerTab."""

import logging
import os
import subprocess
import sys
from pathlib import Path

from PyQt6.QtCore import QSize, Qt
from PyQt6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QSplitter,
    QStyle,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from suiteview.file_nav.file_explorer_widgets import NoFocusDelegate
from suiteview.file_nav.sharepoint_client import is_sp_path

logger = logging.getLogger(__name__)
from suiteview.taskbar_launcher.file_explorer_widgets import (
    ClickableBreadcrumb,
    NavigableTreeView,
)


class FileExplorerNavigationMixin:
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
        # SharePoint virtual folders show their display name as a single segment
        if is_sp_path(path):
            name = self._sp_display_names.get(path, "SharePoint")
            self.breadcrumb_widget.set_path(f"🌐 {name}")
            self.current_directory = path
            self.path_changed.emit(name)  # Tab title shows the folder name
            return
        
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
            # SharePoint virtual folders bypass all filesystem checks
            if is_sp_path(path):
                if add_to_history:
                    self._record_navigation(path)
                self.update_breadcrumb(path)
                self._update_nav_button_states()
                display_name = self._sp_display_names.get(path, "SharePoint")
                # Call the parent implementation directly (our override funnels here)
                super().load_sharepoint_contents_in_details(path, display_name)
                return
            
            path_obj = Path(path)
            if not path_obj.exists():
                return
            
            if path_obj.is_file():
                path_obj = path_obj.parent
            
            path_str = str(path_obj)
            
            # Add to navigation history if requested (not when using back/forward)
            if add_to_history:
                self._record_navigation(path_str)
            
            # Update breadcrumb
            self.update_breadcrumb(path_str)
            
            # Update navigation button states
            self._update_nav_button_states()
            
            # Load in the details pane (right side) instead of tree
            self.load_folder_contents_in_details(path_obj)
            
        except Exception as e:
            logger.error(f"Failed to navigate to {path}: {e}")
    
    def _record_navigation(self, path_str):
        """Append a path to both navigation histories (browser-style truncation)"""
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
        logger.debug(f"navigate_back called: index={self.current_path_index}, history={self.current_path_history}")
        if self.current_path_index > 0:
            self.current_path_index -= 1
            path = self.current_path_history[self.current_path_index]
            logger.debug(f"Going back to: {path}")
            # Also add to full history
            if not self.full_history or self.full_history[-1] != path:
                self.full_history.append(path)
            self.navigate_to_path(path, add_to_history=False)
        else:
            logger.debug("Already at beginning of history")
    
    def navigate_forward(self):
        """Navigate to next folder in current path history"""
        logger.debug(f"navigate_forward called: index={self.current_path_index}, history={self.current_path_history}")
        if self.current_path_index < len(self.current_path_history) - 1:
            self.current_path_index += 1
            path = self.current_path_history[self.current_path_index]
            logger.debug(f"Going forward to: {path}")
            # Also add to full history
            if not self.full_history or self.full_history[-1] != path:
                self.full_history.append(path)
            self.navigate_to_path(path, add_to_history=False)
        else:
            logger.debug("Already at end of history")
    
    def on_details_item_double_clicked(self, index):
        """Override to use navigate_to_path for history tracking"""
        logger.debug(f"\n=== DOUBLE CLICK DEBUG ===")
        logger.debug(f"Proxy Index: row={index.row()}, col={index.column()}")
        
        # Get the data directly from the proxy model (which handles sorting)
        path = self.details_sort_proxy.data(index, Qt.ItemDataRole.UserRole)
        
        # If this column doesn't have the path data, get it from column 0 of the same row
        if not path:
            col0_index = index.sibling(index.row(), 0)
            col0_text = self.details_sort_proxy.data(col0_index, Qt.ItemDataRole.DisplayRole)
            logger.debug(f"Column 0 text for this row: {col0_text}")
            path = self.details_sort_proxy.data(col0_index, Qt.ItemDataRole.UserRole)
        
        if not path:
            logger.debug("No path data found")
            return
        
        logger.debug(f"Path retrieved: {path}")
        logger.debug(f"=========================\n")
        
        # SharePoint virtual items: navigate folders, download-and-open files
        if is_sp_path(path):
            col0_index = index.sibling(index.row(), 0)
            kind = self.details_sort_proxy.data(col0_index, Qt.ItemDataRole.UserRole + 3)
            name = (self.details_sort_proxy.data(col0_index, Qt.ItemDataRole.UserRole + 5)
                    or self.details_sort_proxy.data(col0_index, Qt.ItemDataRole.DisplayRole))
            if kind == "folder":
                self.load_sharepoint_contents_in_details(path, name)
            else:
                self.open_sharepoint_file(path, name)
            return
        
        path_obj = Path(path)
        
        # Handle .lnk shortcut files - resolve target and navigate if it's a folder
        if path_obj.suffix.lower() == '.lnk' and path_obj.is_file():
            target_path = self._resolve_shortcut(str(path_obj))
            if target_path:
                target_obj = Path(target_path)
                if target_obj.exists() and target_obj.is_dir():
                    # Navigate to the folder target within File Nav (with history tracking)
                    logger.debug(f"Shortcut resolves to folder: {target_obj}")
                    self.navigate_to_path(target_obj, add_to_history=True)
                    return
                elif target_obj.exists() and target_obj.is_file():
                    # Shortcut points to a file, open it
                    logger.debug(f"Shortcut resolves to file: {target_obj}")
                    try:
                        if os.name == 'nt':
                            self._safe_startfile(str(target_obj))
                        elif sys.platform == 'darwin':
                            subprocess.run(['open', str(target_obj)])
                        else:
                            subprocess.run(['xdg-open', str(target_obj)])
                    except Exception as e:
                        logger.error(f"Failed to open file: {e}")
                        QMessageBox.warning(self, "Cannot Open File", f"Failed to open {target_obj.name}\n\nError: {str(e)}")
                    return
            # If we can't resolve, fall through to open the .lnk file itself
        
        is_dir = path_obj.is_dir()
        is_file = path_obj.is_file()
        
        if is_dir:
            logger.debug(f"Is directory, navigating to: {path_obj}")
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
    
    def load_sharepoint_contents_in_details(self, sp_path, display_name=None):
        """Override: route SharePoint loads through navigate_to_path so
        breadcrumb, tab title, and back/forward history stay in sync."""
        if display_name:
            self._sp_display_names[sp_path] = display_name
        self.navigate_to_path(sp_path)
    
    def on_tree_item_clicked(self, index):
        """Override parent method to use navigate_to_path for history tracking"""
        # Get the path from the clicked item
        item = self.model.itemFromIndex(index)
        if not item:
            return
        
        path = item.data(Qt.ItemDataRole.UserRole)
        if is_sp_path(path):
            # Remember the display name for the breadcrumb/tab title
            self._sp_display_names[path] = (item.data(Qt.ItemDataRole.UserRole + 5)
                                            or item.text())
            self.navigate_to_path(path)
            return
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
        
        if is_sp_path(path):
            self._sp_display_names[path] = (item.data(Qt.ItemDataRole.UserRole + 5)
                                            or item.text())
            self.navigate_to_path(path)
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
                    subprocess.run(['open', str(path_obj)])
                else:
                    subprocess.run(['xdg-open', str(path_obj)])
            except Exception as e:
                logger.error(f"Failed to open file: {e}")
