"""FileExplorerTab composition for the taskbar and FileNav windows."""

import logging
from pathlib import Path

from PyQt6.QtCore import Qt, pyqtSignal

from suiteview.file_nav.file_explorer_core import FileExplorerCore

logger = logging.getLogger(__name__)
from suiteview.taskbar_launcher.file_explorer_navigation import (
    NavigationController,
)
from suiteview.taskbar_launcher.file_explorer_quick_links import (
    QuickLinksController,
)


class FileExplorerTab(FileExplorerCore):
    """
    Extended FileExplorer with breadcrumb navigation and current path tracking
    """
    
    path_changed = pyqtSignal(str)  # Signal when path changes
    
    def __init__(self, initial_path=None):
        super().__init__()
        self.navigation = NavigationController(self)
        self.quick_links = QuickLinksController(self)
        
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
        
        # Display names for SharePoint virtual paths (sp://... -> folder name)
        self._sp_display_names = {}
        
        # Which history view is active in the panel
        self.history_view_mode = "current_path"  # "current_path" or "full_history"
        
        # Replace the parent's tree views with our custom NavigableTreeView
        # to catch mouse button events
        self.navigation._replace_views_with_navigable()
        
        # Set up dual pane feature
        self.quick_links._setup_dual_pane()
        
        # Add breadcrumb bar at the top
        self.navigation.insert_breadcrumb_bar()
        
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


def _delegate(collaborator_name: str, method_name: str):
    def wrapper(self, *args, **kwargs):
        collaborator = getattr(self, collaborator_name)
        return getattr(collaborator, method_name)(*args, **kwargs)

    wrapper.__name__ = method_name
    return wrapper


for _name in {
    "_replace_views_with_navigable",
    "insert_breadcrumb_bar",
    "update_breadcrumb",
    "_apply_depth_search_locked_style",
    "go_to_onedrive_home",
    "navigate_to_path",
    "_record_navigation",
    "_update_nav_button_states",
    "toggle_history_panel",
    "_create_history_panel",
    "_set_history_view",
    "_update_history_panel",
    "_on_history_item_clicked",
    "_jump_to_history_index",
    "_clear_history",
    "navigate_back",
    "navigate_forward",
    "on_details_item_double_clicked",
    "load_directory_contents_at_root",
    "go_up_one_level",
    "refresh_current_folder",
    "load_sharepoint_contents_in_details",
    "on_tree_item_clicked",
    "navigate_to_bookmark_folder",
    "on_item_double_clicked",
}:
    setattr(FileExplorerTab, _name, _delegate("navigation", _name))

for _name in {
    "_setup_dual_pane",
    "show_quick_links_context_menu",
    "open_quick_link_path",
    "open_path_in_explorer",
    "refresh_quick_links_list",
    "_update_sidebar_footer",
    "_on_bookmark_clicked",
    "_on_bookmark_double_clicked",
    "_show_bookmark_context_menu",
    "_open_folder_location",
    "_show_category_context_menu",
    "_rename_category_in_quick_links",
    "_remove_category_with_confirmation",
    "_show_quick_links_panel_context_menu",
    "_create_new_category",
    "_add_bookmark_to_sidebar",
    "_remove_bookmark_from_quick_links",
    "on_quick_link_item_dropped",
    "_on_category_item_clicked",
    "_on_category_item_double_clicked",
    "_on_bookmark_dropped_to_category",
    "_on_category_moved_out",
    "refresh_quick_links",
    "on_quick_links_reordered",
    "on_bookmark_dropped_to_quick_links",
    "on_file_dropped_to_quick_links",
    "on_category_dropped_to_quick_links",
    "_remove_category_from_bookmark_bar",
    "on_quick_link_clicked",
    "on_quick_link_double_clicked",
    "toggle_dual_pane",
    "_create_scratchpad_panel",
    "toggle_scratchpad_panel",
    "_on_scratchpad_fullscreen",
}:
    setattr(FileExplorerTab, _name, _delegate("quick_links", _name))
