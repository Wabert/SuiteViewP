"""Quick-links, bookmarks, and scratchpad mixin for FileExplorerTab."""

import logging
import subprocess
import webbrowser
from pathlib import Path

from PyQt6.QtCore import Qt
from PyQt6.QtGui import (
    QAction,
    QStandardItemModel,
)
from PyQt6.QtWidgets import (
    QApplication,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QMenu,
    QMessageBox,
    QSplitter,
    QVBoxLayout,
    QWidget,
)

from suiteview.core.access_control import (
    can_access_app,
)
from suiteview.ui.access_control import requires_app_access
from suiteview.scratchpad.scratchpad_panel import ScratchPadPanel
from suiteview.ui.dialogs.shortcuts_dialog import AddBookmarkDialog
from suiteview.ui.widgets.bookmark_data_manager import get_bookmark_manager
from suiteview.ui.widgets.bookmark_widgets import (
    CATEGORY_CONTEXT_MENU_STYLE,
    BookmarkContainer,
)
from suiteview.taskbar_launcher.collaborators import FileExplorerController

logger = logging.getLogger(__name__)


class QuickLinksController(FileExplorerController):
    """Owns the bookmark/sidebar/scratchpad panels for a File Explorer tab."""

    def _setup_dual_pane(self):
        """Set up the Quick Links panel (on the right) - using unified BookmarkContainer"""
        
        # Find the main splitter that contains tree and details
        for child in self.tab.findChildren(QSplitter):
            if child.count() >= 2:
                self.main_splitter = child
                break
        
        if not hasattr(self, 'main_splitter'):
            logger.debug("Could not find main splitter")
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
        self.state.dual_pane_active = self.tab.panel_widths.get('quick_links_visible', False)
        quick_links_panel.setVisible(self.state.dual_pane_active)
        
        # Restore all panel sizes (3rd = bookmarks, 4th = notes added later)
        saved_left = self.tab.panel_widths.get('left_panel', 300)
        saved_middle = self.tab.panel_widths.get('middle_panel', 700)
        saved_right = self.tab.panel_widths.get('right_panel', 200)
        
        if self.state.dual_pane_active:
            self.main_splitter.setSizes([saved_left, saved_middle, saved_right, 0])
        else:
            # Quick links hidden - give its space to middle panel
            self.main_splitter.setSizes([saved_left, saved_middle + saved_right, 0, 0])
        
        # Connect the bookmark bar's sidebar toggle button to toggle_dual_pane
        if hasattr(self, 'bookmark_bar') and hasattr(self.tab.bookmark_bar, 'sidebar_toggle_btn'):
            self.tab.bookmark_bar.sidebar_toggle_btn.clicked.connect(self.toggle_dual_pane)
            # Set initial checked state based on restored visibility
            self.tab.bookmark_bar.sidebar_toggle_btn.setChecked(self.state.dual_pane_active)

        # ── ScratchPad panel (4th splitter widget, index 3) ────────────
        self.scratchpad_panel = None
        self.state.scratchpad_panel_active = (
            can_access_app("SCRATCHPAD") and self.tab.panel_widths.get('scratchpad_visible', False)
        )
        if self.state.scratchpad_panel_active:
            self._create_scratchpad_panel()
            self.scratchpad_panel.setVisible(True)
            # Restore widths including scratchpad panel
            saved_scratchpad = self.tab.panel_widths.get('scratchpad_panel', 220)
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
            self.tab.open_file(path)
        else:
            self.tab.navigate_to_path(path)
    
    def open_path_in_explorer(self, path):
        """Open a path in Windows Explorer"""
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
                items = self.tab.custom_quick_links.get('items', [])
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
            webbrowser.open(path)
            return
        
        path_obj = Path(path)
        if path_obj.is_dir():
            self.tab.navigate_to_path(path)
        elif path_obj.is_file():
            # Single click on file opens it
            self.tab.open_file(path)
        else:
            QMessageBox.warning(
                self, "Bookmark Invalid",
                f"The bookmark path no longer exists:\n\n{path}\n\n"
                "The folder or file may have been renamed, moved, or deleted."
            )
    
    def _on_bookmark_double_clicked(self, path):
        """Handle double-click on bookmark button in Quick Links"""
        # Handle URLs first
        if path.startswith('http://') or path.startswith('https://'):
            webbrowser.open(path)
            return
        
        path_obj = Path(path)
        if not path_obj.exists():
            QMessageBox.warning(
                self, "Bookmark Invalid",
                f"The bookmark path no longer exists:\n\n{path}\n\n"
                "The folder or file may have been renamed, moved, or deleted."
            )
            return
        if path_obj.is_file():
            self.tab.open_file(path)
        else:
            self.tab.navigate_to_path(path)
    
    def _show_bookmark_context_menu(self, position, bookmark_btn):
        """Show context menu for a bookmark button in Quick Links"""
        
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
            self.tab.navigate_to_path(parent_folder)
    
    def _show_category_context_menu(self, position, cat_widget):
        """Show context menu for a category in Quick Links"""
        
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
            
            if self.tab._bookmark_manager.find_category_by_name(new_name):
                QMessageBox.warning(self, "Duplicate", f"Category '{new_name}' already exists.")
            else:
                if self.tab.rename_category_in_quick_links(old_name, new_name):
                    self.tab.refresh_quick_links_list()
    
    def _remove_category_with_confirmation(self, category_name, category_items):
        """Remove a category from Quick Links with confirmation showing all items"""
        
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
            self.tab.remove_category_from_quick_links(category_name)
            self.tab.refresh_quick_links_list()
    
    def _show_quick_links_panel_context_menu(self, position):
        """Show context menu for Quick Links panel (empty area or header) - allows creating new categories"""
        
        menu = QMenu(self)
        
        # New Category action
        new_category_action = QAction("📁 New Category...", self)
        new_category_action.triggered.connect(self._create_new_category)
        menu.addAction(new_category_action)
        
        # Get the sender widget to map position correctly
        sender = self.tab.sender()
        if sender:
            menu.exec(sender.mapToGlobal(position))
        else:
            menu.exec(self.tab.mapToGlobal(position))
    
    def _create_new_category(self):
        """Create a new empty category in Quick Links"""
        
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
            if self.tab._bookmark_manager.find_category_by_name(name):
                QMessageBox.warning(self, "Duplicate", f"Category '{name}' already exists.")
                return
            
            # Use BookmarkContainer's add_category method (new format)
            self.bookmark_container.add_category(name)
            self._update_sidebar_footer()
            logger.info(f"Created new category '{name}' in Quick Links")
    
    def _add_bookmark_to_sidebar(self):
        """Launch the Add Bookmark dialog to add a bookmark to the sidebar"""
        
        # Get current folder to pre-fill the dialog
        current_folder = getattr(self, 'current_details_folder', None)
        if not current_folder:
            current_folder = getattr(self, 'current_directory', None)
        
        # Get categories from the sidebar bookmark container (new format - from items)
        categories = [item.get('name') for item in self.tab.custom_quick_links.get('items', [])
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
            items = self.tab.custom_quick_links.get('items', [])
            for item in items:
                if item.get('type') == 'bookmark':
                    if item.get('path') == path:
                        QMessageBox.information(self, "Already Added", f"'{name}' is already in Bookmarks.")
                        return
            
            # Add to items
            if 'items' not in self.tab.custom_quick_links:
                self.tab.custom_quick_links['items'] = []
            
            # Determine bookmark type
            bm_type = 'folder'
            if path.startswith('http://') or path.startswith('https://'):
                bm_type = 'url'
            elif Path(path).exists() and Path(path).is_file():
                bm_type = 'file'
            new_bookmark = get_bookmark_manager().create_bookmark(
                name or Path(path).name,
                path
            )
            self.tab.custom_quick_links['items'].append(new_bookmark)
            
            self.tab.save_quick_links()
            self.tab.refresh_quick_links_list()
            logger.info(f"Added '{name}' to Quick Links sidebar")
    
    def _remove_bookmark_from_quick_links(self, path):
        """Remove a bookmark from Quick Links"""
        if self.tab._bookmark_manager.remove_bookmark_by_path(1, path):
            self.tab.save_quick_links()
            self.tab.refresh_quick_links_list()
    
    def on_quick_link_item_dropped(self, item_data, drop_index):
        """Handle an item being dropped at a specific position in Quick Links"""
        items = self.tab.custom_quick_links.get('items', [])
        
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
                self.tab.save_quick_links()
                self.tab.refresh_quick_links_list()
        elif source == 'quick_links_category' and source_category:
            # Item from Quick Links category - move to main sidebar
            path = item_data.get('path', '')
            name = item_data.get('name', '')
            if path and not self.tab.is_path_in_quick_links(path):
                # Add to sidebar
                self.tab.add_to_quick_links(path, insert_at=drop_index)
                
                # Remove from source category (new format - categories have nested items)
                self.tab._bookmark_manager.remove_bookmark_from_category_by_name(source_category, path)
                self.tab.save_quick_links()
                self.tab.refresh_quick_links_list()
                logger.info(f"Moved '{name}' from category '{source_category}' to Quick Links sidebar")
        else:
            # New item from outside - will be handled by other drop handlers
            pass
    
    def _on_category_item_clicked(self, path):
        """Handle click on item inside a Quick Links category"""
        path_obj = Path(path)
        if path_obj.is_dir():
            self.tab.navigate_to_path(path)
    
    def _on_category_item_double_clicked(self, path):
        """Handle double-click on item inside a Quick Links category"""
        path_obj = Path(path)
        if path_obj.is_file():
            self.tab.open_file(path)
        else:
            self.tab.navigate_to_path(path)
    
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
        target_category = self.tab._bookmark_manager.find_category_by_name(category_name)
        if not target_category:
            logger.warning(f"Target category '{category_name}' not found")
            return
        
        # Check if already in target category
        for item in target_category.get('items', []):
            if item.get('path') == path:
                return  # Already exists
        
        # Add to target category
        new_bookmark = self.tab._bookmark_manager.create_bookmark(
            bookmark.get('name', Path(path).name),
            path
        )
        target_category.setdefault('items', []).append(new_bookmark)
        
        # Remove from source
        removed_from_source = False
        
        # If from bookmark bar (top level), remove from bar items
        if source_category in ('__BAR__', '__CONTAINER__') and bookmark.get('source_location') == 'bar':
            if hasattr(self, 'bookmark_bar') and self.tab.bookmark_bar:
                removed_from_source = self.tab.bookmark_bar.remove_bookmark_by_path(path)
                if removed_from_source:
                    logger.info(f"Removed '{path}' from bookmark bar")
        
        # If from Quick Links sidebar (top level), remove from sidebar items
        if not removed_from_source and source_category in ('__QUICK_LINKS__', '__CONTAINER__'):
            items = self.tab.custom_quick_links.get('items', [])
            for i, item in enumerate(items):
                if item.get('type') == 'bookmark' and item.get('path') == path:
                    items.pop(i)
                    logger.info(f"Removed '{path}' from Quick Links sidebar")
                    removed_from_source = True
                    break
        
        # If from another category, remove from source category
        if not removed_from_source and source_category and source_category not in ('__QUICK_LINKS__', '__CONTAINER__', '__BAR__', ''):
            if self.tab._bookmark_manager.remove_bookmark_from_category_by_name(source_category, path):
                logger.info(f"Removed '{path}' from category '{source_category}'")
                removed_from_source = True
        
        self.tab.save_quick_links()
        self.tab.refresh_quick_links_list()
        logger.info(f"Added '{path}' to category '{category_name}'")
    
    def _on_category_moved_out(self, category_name, category_data):
        """Handle category being dragged out of Quick Links"""
        # This is called when the category is being moved elsewhere
        # The actual removal happens when the drop is accepted
        pass
    
    def refresh_quick_links(self):
        """Refresh the Quick Links panel"""
        self.tab.refresh_quick_links_list()
    
    def on_quick_links_reordered(self, new_order):
        """Handle Quick Links reorder via drag-drop"""
        # Convert the new_order (list of paths) back to structured items
        manager = get_bookmark_manager()
        new_items = []
        for path in new_order:
            new_items.append(manager.create_bookmark(
                Path(path).name,
                path
            ))
        
        # Keep categories at the end (after the reordered bookmarks)
        for item in self.tab.custom_quick_links.get('items', []):
            if item.get('type') == 'category':
                new_items.append(item)
        
        self.tab.custom_quick_links['items'] = new_items
        self.tab.save_quick_links()
        self.tab.refresh_quick_links_list()
    
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
        for item in self.tab.custom_quick_links.get('items', []):
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
            if is_from_bar and not is_from_bar_category and hasattr(self, 'bookmark_bar') and self.tab.bookmark_bar:
                bar_items = self.tab.bookmark_bar.bookmarks_data.get('bar_items', [])
                for i, item in enumerate(bar_items):
                    if item.get('type') == 'bookmark':
                        item_path = item.get('path')
                        if item_path == path:
                            bar_items.pop(i)
                            self.tab.bookmark_bar.save_bookmarks()
                            self.tab.bookmark_bar.refresh_bookmarks()
                            logger.info(f"Removed '{path}' from bookmark bar")
                            removed_from_source = True
                            break
            
            # Try Quick Links categories (sidebar categories - new format)
            if not removed_from_source and is_from_sidebar_category:
                if self.tab._bookmark_manager.remove_bookmark_from_category_by_name(source_category, path):
                    removed_from_source = True
                    logger.info(f"Removed from Quick Links category '{source_category}'")
            
            # If from bookmark bar category (new format)
            if not removed_from_source and is_from_bar_category and hasattr(self, 'bookmark_bar') and self.tab.bookmark_bar:
                if self.tab._bookmark_manager.remove_bookmark_from_category_by_name(source_category, path):
                    self.tab.bookmark_bar.save_bookmarks()
                    self.tab.bookmark_bar.refresh_bookmarks()
                    logger.info(f"Removed from bookmark bar category '{source_category}'")
                    removed_from_source = True
            
            # NOW add to sidebar at specified position (after removing from source)
            self.tab.add_to_quick_links(path, insert_at=drop_index)
            logger.info(f"Added bookmark '{bookmark.get('name', path)}' to Quick Links sidebar at position {drop_index}")
            
            self.tab.save_quick_links()
            self.tab.refresh_quick_links_list()
        elif not self.tab.is_path_in_quick_links(path):
            # New item from outside Quick Links entirely
            self.tab.add_to_quick_links(path, insert_at=drop_index)
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
        
        if actual_path and not self.tab.is_path_in_quick_links(actual_path):
            self.tab.add_to_quick_links(actual_path, insert_at=drop_index)
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
        if self.tab._bookmark_manager.find_category_by_name(category_name):
            logger.warning(f"Category '{category_name}' already exists in Quick Links")
            return
        
        # Add category to Quick Links at the specified position
        self.tab.add_category_to_quick_links(category_name, category_items, insert_at=drop_index)
        
        # Transfer color if present
        if category_color:
            if 'category_colors' not in self.tab.custom_quick_links:
                self.tab.custom_quick_links['category_colors'] = {}
            self.tab.custom_quick_links['category_colors'][category_name] = category_color
            self.tab.save_quick_links()
        
        # If it came from bookmark bar, remove it from there (MOVE semantics)
        if source == 'bookmark_bar' and hasattr(self, 'bookmark_bar'):
            self._remove_category_from_bookmark_bar(category_name)
        
        self.tab.refresh_quick_links_list()
        logger.info(f"Moved category '{category_name}' to Quick Links at position {drop_index}")
    
    def _remove_category_from_bookmark_bar(self, category_name):
        """Remove a category from the bookmark bar (after moving to Quick Links)"""
        if not hasattr(self, 'bookmark_bar'):
            return
        
        # Use BookmarkContainer's remove_category method (new format)
        self.tab.bookmark_bar.remove_category(category_name)
    
    def on_quick_link_clicked(self, item):
        """Handle single click on quick link - navigate to folder or select file"""
        path_str = item.data(Qt.ItemDataRole.UserRole)
        if path_str:
            path = Path(path_str)
            if path.is_dir():
                self.tab.navigate_to_path(path_str)
    
    def on_quick_link_double_clicked(self, item):
        """Handle double click on quick link - open the item"""
        path_str = item.data(Qt.ItemDataRole.UserRole)
        if path_str:
            path = Path(path_str)
            if path.is_file():
                self.tab.open_file(path_str)
            else:
                self.tab.navigate_to_path(path_str)
    
    def toggle_dual_pane(self):
        """Toggle the Quick Links panel on/off"""
        self.state.dual_pane_active = not self.state.dual_pane_active
        
        if hasattr(self, 'tree_panel_2'):
            self.tree_panel_2.setVisible(self.state.dual_pane_active)
            
            # Update the sidebar toggle button state in bookmark bar
            if hasattr(self, 'bookmark_bar') and hasattr(self.tab.bookmark_bar, 'sidebar_toggle_btn'):
                self.tab.bookmark_bar.sidebar_toggle_btn.setChecked(self.state.dual_pane_active)
            # Update the breadcrumb bar bookmarks toggle button
            if hasattr(self, 'bookmarks_toggle_btn'):
                self.bookmarks_toggle_btn.setChecked(self.state.dual_pane_active)
            
            # Refresh quick links when showing
            if self.state.dual_pane_active:
                self.tab.refresh_quick_links()
            
            # Adjust splitter sizes when toggling
            # IMPORTANT: Preserve the left panel width
            current_sizes = self.main_splitter.sizes()
            left_width = current_sizes[0] if current_sizes else 300  # Keep current left width
            notes_width = current_sizes[3] if len(current_sizes) >= 4 else 0
            
            if self.state.dual_pane_active:
                # Use saved right panel width if available, otherwise calculate
                saved_right = self.tab.panel_widths.get('right_panel', 0)
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
            self.tab.panel_widths['quick_links_visible'] = self.state.dual_pane_active
            self.tab.save_panel_widths()
        
        logger.debug(f"Dual pane {'enabled' if self.state.dual_pane_active else 'disabled'}")

    def _create_scratchpad_panel(self):

        self.scratchpad_panel = ScratchPadPanel(parent=self.tab)
        self.scratchpad_panel.setVisible(False)
        self.scratchpad_panel.fullscreen_toggled.connect(self._on_scratchpad_fullscreen)
        self.main_splitter.addWidget(self.scratchpad_panel)
        self.main_splitter.setStretchFactor(3, 0)

    @requires_app_access("SCRATCHPAD")
    def toggle_scratchpad_panel(self):
        """Toggle the ScratchPad panel on/off"""
        if self.scratchpad_panel is None:
            self._create_scratchpad_panel()

        self.state.scratchpad_panel_active = not self.state.scratchpad_panel_active
        self.scratchpad_panel.setVisible(self.state.scratchpad_panel_active)

        # Update toggle button checked state
        if hasattr(self, 'scratchpad_toggle_btn'):
            self.scratchpad_toggle_btn.setChecked(self.state.scratchpad_panel_active)

        # Adjust splitter sizes
        current_sizes = self.main_splitter.sizes()
        left_width = current_sizes[0] if current_sizes else 300
        right_width = current_sizes[2] if len(current_sizes) >= 3 else 0

        if self.state.scratchpad_panel_active:
            # Refresh scratchpad when showing
            self.scratchpad_panel.refresh()
            saved_scratchpad = self.tab.panel_widths.get('scratchpad_panel', 220)
            middle_width = self.main_splitter.width() - left_width - right_width - saved_scratchpad
            self.main_splitter.setSizes([left_width, max(100, middle_width), right_width, saved_scratchpad])
        else:
            middle_width = self.main_splitter.width() - left_width - right_width
            self.main_splitter.setSizes([left_width, middle_width, right_width, 0])

        # Persist
        self.tab.panel_widths['scratchpad_visible'] = self.state.scratchpad_panel_active
        self.tab.save_panel_widths()
        logger.debug(f"ScratchPad panel {'shown' if self.state.scratchpad_panel_active else 'hidden'}")

    @requires_app_access("SCRATCHPAD")
    def _on_scratchpad_fullscreen(self, go_full: bool):
        """Expand the scratchpad panel to fill the entire splitter, or restore."""
        if not hasattr(self, 'main_splitter'):
            return

        if go_full:
            # Save current sizes so we can restore later
            self.state.pre_fs_sizes = self.main_splitter.sizes()
            total = self.main_splitter.width()
            self.main_splitter.setSizes([0, 0, 0, total])
        else:
            # Restore saved sizes
            if self.state.pre_fs_sizes:
                self.main_splitter.setSizes(self.state.pre_fs_sizes)
            else:
                # Fallback
                left = self.tab.panel_widths.get('left_panel', 300)
                mid = self.tab.panel_widths.get('middle_panel', 700)
                right = self.tab.panel_widths.get('right_panel', 0)
                scratchpad = self.tab.panel_widths.get('scratchpad_panel', 220)
                self.main_splitter.setSizes([left, mid, right, scratchpad])
