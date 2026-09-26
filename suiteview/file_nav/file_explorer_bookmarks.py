"""File Explorer Bookmarks."""
from __future__ import annotations

import json
import logging
import webbrowser
from pathlib import Path

from PyQt6.QtWidgets import (
    QDialog,
    QMessageBox,
)

from suiteview.core.json_store import write_json
from suiteview.ui.dialogs.shortcuts_dialog import (
    AddBookmarkDialog,
    show_compact_confirm,
)
from suiteview.ui.widgets.bookmark_data_manager import get_bookmark_manager
from suiteview.ui.widgets.bookmark_widgets import BookmarkContainerRegistry

logger = logging.getLogger(__name__)


class FileExplorerBookmarksMixin:
    """Requires: BookmarkDataManager, bookmark containers, and current folder state.
    Provides: quick-link CRUD, bookmark drops, and cross-container refresh.
    """

    def load_quick_links(self):
        """Load sidebar quick links from unified bookmarks.json file
        
        Reads from bars.sidebar in the unified format:
        {
            'bars': {
                'sidebar': {
                    'categories': {'Category Name': [{'name': '...', 'path': '...', 'type': 'file|folder'}, ...]},
                    'items': [...],
                    'category_colors': {...}
                }
            },
            'version': 2
        }
        """
        try:
            bookmarks_file = getattr(self, "bookmarks_file", None)
            if bookmarks_file and bookmarks_file.exists():
                with open(bookmarks_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    
                    # Read from unified format: bars.sidebar
                    if 'bars' in data and 'sidebar' in data['bars']:
                        sidebar_data = data['bars']['sidebar']
                        # Ensure structure has required keys
                        if 'categories' not in sidebar_data:
                            sidebar_data['categories'] = {}
                        if 'items' not in sidebar_data:
                            sidebar_data['items'] = []
                        if 'category_colors' not in sidebar_data:
                            sidebar_data['category_colors'] = {}
                        return sidebar_data
                    
        except (OSError, json.JSONDecodeError) as e:
            logger.error(f"Failed to load quick links: {e}")
        
        # Default structure
        return {
            'categories': {},
            'items': [],
            'category_colors': {}
        }

    def save_quick_links(self):
        """Save sidebar quick links via centralized bookmark manager"""
        try:
            self._bookmark_manager.save()
        except (OSError, json.JSONDecodeError) as e:
            logger.error(f"Failed to save quick links: {e}")

    def get_quick_links_paths(self):
        """Get flat list of paths from quick links for compatibility"""
        paths = []
        for item in self.custom_quick_links.get('items', []):
            if item.get('type') == 'bookmark':
                path = item.get('path')
                if path:
                    paths.append(path)
        return paths

    def is_path_in_quick_links(self, path):
        """Check if a path is already in quick links (at top level or in any category)"""
        return self._bookmark_manager.is_path_in_bar(1, path)

    def add_bookmark_to_quick_links(self, path, insert_at=None):
        """Add a bookmark path to Quick Links items"""
        path_str = str(Path(path).resolve())
        
        # Check if already exists
        if self.is_path_in_quick_links(path_str):
            return False
        
        path_obj = Path(path_str)
        new_item = self._bookmark_manager.create_bookmark(path_obj.name, path_str)
        
        items = self.custom_quick_links.get('items', [])
        if insert_at is not None and 0 <= insert_at <= len(items):
            items.insert(insert_at, new_item)
        else:
            items.append(new_item)
        
        self.save_quick_links()
        return True

    def remove_bookmark_from_quick_links(self, path):
        """Remove a bookmark from Quick Links by path"""
        if self._bookmark_manager.remove_bookmark_by_path(1, path):
            self.save_quick_links()
            return True
        return False

    def add_category_to_quick_links(self, category_name, category_items=None, insert_at=None):
        """Add a category to Quick Links"""
        # Check if category already exists
        if self._bookmark_manager.find_category_by_name(category_name):
            return False
        
        # Create category item in new format (nested items, not separate dict)
        new_category = self._bookmark_manager.create_category(category_name, category_items or [])
        
        items = self.custom_quick_links.get('items', [])
        if insert_at is not None and 0 <= insert_at <= len(items):
            items.insert(insert_at, new_category)
        else:
            items.append(new_category)
        
        self.save_quick_links()
        return True

    def remove_category_from_quick_links(self, category_name):
        """Remove a category from Quick Links"""
        category = self._bookmark_manager.find_category_by_name(category_name)
        if category:
            self._bookmark_manager.remove_item(category.get('id'))
            self.save_quick_links()
            return True
        return False

    def rename_category_in_quick_links(self, old_name, new_name):
        """Rename a category in Quick Links"""
        if old_name == new_name:
            return False
        
        # Check if new name already exists
        if self._bookmark_manager.find_category_by_name(new_name):
            return False
        
        category = self._bookmark_manager.find_category_by_name(old_name)
        if category:
            category['name'] = new_name
            self.save_quick_links()
            return True
        return False

    def load_hidden_onedrive(self):
        """Load hidden OneDrive paths from JSON file"""
        try:
            if self.hidden_onedrive_file.exists():
                with open(self.hidden_onedrive_file, 'r') as f:
                    paths = json.load(f)
                    # Normalize paths to lowercase for comparison
                    return set(p.lower() for p in paths)
        except OSError as e:
            logger.error(f"Failed to load hidden OneDrive paths: {e}")
        return set()

    def save_hidden_onedrive(self):
        """Save hidden OneDrive paths to JSON file"""
        try:
            # Ensure directory exists
            self.hidden_onedrive_file.parent.mkdir(parents=True, exist_ok=True)
            write_json(self.hidden_onedrive_file, list(self.hidden_onedrive_paths), ensure_ascii=True)
        except (OSError, json.JSONDecodeError) as e:
            logger.error(f"Failed to save hidden OneDrive paths: {e}")

    def hide_onedrive_path(self, path):
        """Hide a OneDrive path from Quick Links"""
        path_str = str(path).lower()
        if path_str not in self.hidden_onedrive_paths:
            self.hidden_onedrive_paths.add(path_str)
            self.save_hidden_onedrive()
            # Refresh tree to remove it
            self.load_tree()
            QMessageBox.information(self, "OneDrive Hidden", f"Hidden from Quick Links:\n{Path(path).name}\n\nTo unhide, delete:\n{self.hidden_onedrive_file}")

    def load_pinned_folders(self):
        """Load pinned folders from JSON file"""
        try:
            if self.pinned_folders_file.exists():
                with open(self.pinned_folders_file, 'r') as f:
                    return json.load(f)
        except OSError as e:
            logger.error(f"Failed to load pinned folders: {e}")
        return []

    def save_pinned_folders(self):
        """Save pinned folders to JSON file"""
        try:
            # Ensure directory exists
            self.pinned_folders_file.parent.mkdir(parents=True, exist_ok=True)
            write_json(self.pinned_folders_file, self.pinned_folders, ensure_ascii=True)
        except Exception as e:
            logger.error(f"Failed to save pinned folders: {e}")

    def pin_folder_to_tree(self, folder_path):
        """Pin a folder to the Folders panel"""
        folder_path = str(Path(folder_path).resolve())
        
        # Check if already pinned (case-insensitive)
        for pinned in self.pinned_folders:
            if pinned.lower() == folder_path.lower():
                return  # Already pinned
        
        self.pinned_folders.append(folder_path)
        self.save_pinned_folders()
        self.populate_tree_model()
        logger.info(f"Pinned folder to Folders panel: {folder_path}")

    def unpin_folder_from_tree(self, folder_path):
        """Unpin a folder from the Folders panel"""
        folder_path_lower = str(Path(folder_path).resolve()).lower()
        
        # Find and remove (case-insensitive)
        for i, pinned in enumerate(self.pinned_folders):
            if pinned.lower() == folder_path_lower:
                self.pinned_folders.pop(i)
                self.save_pinned_folders()
                self.populate_tree_model()
                logger.info(f"Unpinned folder from Folders panel: {folder_path}")
                return

    def add_to_quick_access(self):
        """Add selected item to Quick Access"""
        path = self.get_selected_path()
        if not path:
            return
        
        # Use the new helper method
        if self.add_bookmark_to_quick_links(path):
            # Refresh Quick Links panel if it exists
            if hasattr(self, 'refresh_quick_links'):
                self.refresh_quick_links()

    def remove_from_quick_access(self):
        """Remove selected item from Quick Access"""
        path = self.get_selected_path()
        if not path:
            return
        
        if self.is_path_in_quick_links(path):
            if self.remove_bookmark_from_quick_links(path):
                # Refresh Quick Links panel if it exists
                if hasattr(self, 'refresh_quick_links'):
                    self.refresh_quick_links()
                QMessageBox.information(self, "Bookmarks", f"Removed from Bookmarks:\n{Path(path).name}")
        else:
            QMessageBox.warning(self, "Bookmarks", "This item is not in Bookmarks")

    def remove_quick_link_by_path(self, path):
        """Remove a specific path from Quick Links (used by context menu)"""
        
        if self.is_path_in_quick_links(path):
            # Show confirmation dialog
            if show_compact_confirm(self, "Remove Bookmark", f"Remove '{Path(path).name}'?"):
                self.remove_bookmark_from_quick_links(path)
                
                # Refresh Quick Links panel if it exists
                if hasattr(self, 'refresh_quick_links'):
                    self.refresh_quick_links()

    def add_to_quick_links(self, path, insert_at=None):
        """Add a path to Quick Links"""
        # Use the new helper method
        if self.add_bookmark_to_quick_links(path, insert_at=insert_at):
            # Refresh Quick Links panel if it exists
            if hasattr(self, 'refresh_quick_links'):
                self.refresh_quick_links()

    def navigate_to_bookmark_folder(self, folder_path):
        """Navigate to a folder from bookmark click or open URL in browser"""
        logger.debug(f"[DEBUG] navigate_to_bookmark_folder called with: {folder_path}")
        try:
            # Check if it's a URL
            if folder_path and (folder_path.lower().startswith('http://') or folder_path.lower().startswith('https://')):
                # Open URL in default browser
                logger.debug(f"[DEBUG] Opening URL in browser: {folder_path}")
                webbrowser.open(folder_path)
                return
            
            # Handle as file/folder path
            path = Path(folder_path)
            if path.exists():
                if path.is_dir():
                    # Load folder in details view
                    self.load_folder_contents_in_details(path)
                elif path.is_file():
                    # Open file with default application (don't navigate folder)
                    self.open_file(str(path))
            else:
                QMessageBox.warning(
                    self, "Bookmark Invalid",
                    f"The bookmark path no longer exists:\n\n{folder_path}\n\n"
                    "The folder or file may have been renamed, moved, or deleted."
                )
        except Exception as e:
            logger.error(f"Failed to navigate to bookmark: {e}")

    def add_to_bookmarks(self, path, name=None):
        """Add a path to Bookmarks via the bookmark bar"""
        # Use the bookmark bar's add functionality
        if hasattr(self, 'bookmark_bar'):
            # Pre-populate the dialog if it's a specific path
            
            categories = list(self.bookmark_bar.bookmarks_data['categories'].keys())
            
            dialog = AddBookmarkDialog(categories, self)
            
            # Pre-fill with the path
            if name:
                dialog.name_input.setText(name)
            else:
                dialog.name_input.setText(Path(path).name)
            dialog.path_input.setText(str(path))
            
            if dialog.exec() == QDialog.DialogCode.Accepted:
                bookmark = dialog.get_bookmark_data()
                if bookmark['name'] and bookmark['path']:
                    category = bookmark['category']
                    target_bar_id = bookmark.get('target_bar_id')
                    
                    # Remove the category and target_bar_id from bookmark data for storage
                    del bookmark['category']
                    if 'target_bar_id' in bookmark:
                        del bookmark['target_bar_id']
                    
                    if category == "__BAR__" and target_bar_id is not None:
                        # Add directly to a specific bookmark bar
                        
                        manager = get_bookmark_manager()
                        bar_data = manager.get_bar_data(target_bar_id)
                        
                        # Add to the bar's items
                        if 'items' not in bar_data:
                            bar_data['items'] = []
                        bar_data['items'].append(manager.create_bookmark(
                            bookmark.get('name', ''),
                            bookmark.get('path', '')
                        ))
                        
                        # Save and refresh ALL containers for the target bar
                        manager.save()
                        for container in BookmarkContainerRegistry.get_all_for_bar(target_bar_id):
                            try:
                                container.refresh()
                            except RuntimeError:
                                logger.debug("Suppressed File Explorer exception", exc_info=True)
                    else:
                        # Add to category (in the current bar, bar 0)
                        if category not in self.bookmark_bar.bookmarks_data['categories']:
                            self.bookmark_bar.bookmarks_data['categories'][category] = []
                            # Add category to bar_items if it's new
                            self.bookmark_bar.bookmarks_data['bar_items'].append({
                                'type': 'category',
                                'name': category
                            })
                        self.bookmark_bar.bookmarks_data['categories'][category].append(bookmark)
                        
                        self.bookmark_bar.save_bookmarks()
                        self.bookmark_bar.refresh_bookmarks()
