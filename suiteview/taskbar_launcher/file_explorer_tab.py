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
from suiteview.taskbar_launcher.collaborators import FileExplorerTabState


class FileExplorerTab(FileExplorerCore):
    """
    Extended FileExplorer with breadcrumb navigation and current path tracking
    """
    
    path_changed = pyqtSignal(str)  # Signal when path changes
    
    def __init__(self, initial_path=None):
        super().__init__()
        self.tab_state = FileExplorerTabState()
        self.navigation = NavigationController(self, self.tab_state)
        self.quick_links = QuickLinksController(self, self.tab_state)
        
        # Allow tab content to shrink so window can collapse to just header bar
        self.setMinimumSize(0, 0)
        
        # Store the starting path (OneDrive if available)
        if initial_path:
            self.tab_state.starting_path = initial_path
        else:
            onedrive_paths = self.get_onedrive_paths()
            self.tab_state.starting_path = str(onedrive_paths[0]) if onedrive_paths else str(Path.home())
        
        self.tab_state.current_directory = self.tab_state.starting_path
        
        # Replace the parent's tree views with our custom NavigableTreeView
        # to catch mouse button events
        self.navigation._replace_views_with_navigable()
        
        # Set up dual pane feature
        self.quick_links._setup_dual_pane()
        self._sync_quick_links_widgets()
        
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

    @property
    def current_directory(self):
        return self.tab_state.current_directory

    @current_directory.setter
    def current_directory(self, value):
        self.tab_state.current_directory = value

    def replace_navigation_views(self, tree_view, details_view):
        self.tree_view = tree_view
        self.details_view = details_view

    def _sync_quick_links_widgets(self):
        self.main_splitter = self.quick_links.main_splitter
        self.bookmark_container = self.quick_links.bookmark_container
        self.quick_links_panel = self.quick_links.quick_links_panel
        self.tree_panel_2 = self.quick_links.tree_panel_2
        self.quick_links_header = self.quick_links.quick_links_header
        self.quick_links_model = self.quick_links.quick_links_model
        self.sidebar_footer = self.quick_links.sidebar_footer
        self.quick_links_items_layout = self.quick_links.quick_links_items_layout
        self.quick_links_scroll_content = self.quick_links.quick_links_scroll_content

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

    def _replace_views_with_navigable(self, *args, **kwargs):
        return self.navigation._replace_views_with_navigable(*args, **kwargs)

    def insert_breadcrumb_bar(self, *args, **kwargs):
        return self.navigation.insert_breadcrumb_bar(*args, **kwargs)

    def update_breadcrumb(self, *args, **kwargs):
        return self.navigation.update_breadcrumb(*args, **kwargs)

    def _apply_depth_search_locked_style(self, *args, **kwargs):
        return self.navigation._apply_depth_search_locked_style(*args, **kwargs)

    def go_to_onedrive_home(self, *args, **kwargs):
        return self.navigation.go_to_onedrive_home(*args, **kwargs)

    def navigate_to_path(self, *args, **kwargs):
        return self.navigation.navigate_to_path(*args, **kwargs)

    def _record_navigation(self, *args, **kwargs):
        return self.navigation._record_navigation(*args, **kwargs)

    def _update_nav_button_states(self, *args, **kwargs):
        return self.navigation._update_nav_button_states(*args, **kwargs)

    def toggle_history_panel(self, *args, **kwargs):
        return self.navigation.toggle_history_panel(*args, **kwargs)

    def _create_history_panel(self, *args, **kwargs):
        return self.navigation._create_history_panel(*args, **kwargs)

    def _set_history_view(self, *args, **kwargs):
        return self.navigation._set_history_view(*args, **kwargs)

    def _update_history_panel(self, *args, **kwargs):
        return self.navigation._update_history_panel(*args, **kwargs)

    def _on_history_item_clicked(self, *args, **kwargs):
        return self.navigation._on_history_item_clicked(*args, **kwargs)

    def _jump_to_history_index(self, *args, **kwargs):
        return self.navigation._jump_to_history_index(*args, **kwargs)

    def _clear_history(self, *args, **kwargs):
        return self.navigation._clear_history(*args, **kwargs)

    def navigate_back(self, *args, **kwargs):
        return self.navigation.navigate_back(*args, **kwargs)

    def navigate_forward(self, *args, **kwargs):
        return self.navigation.navigate_forward(*args, **kwargs)

    def on_details_item_double_clicked(self, *args, **kwargs):
        return self.navigation.on_details_item_double_clicked(*args, **kwargs)

    def load_directory_contents_at_root(self, *args, **kwargs):
        return self.navigation.load_directory_contents_at_root(*args, **kwargs)

    def go_up_one_level(self, *args, **kwargs):
        return self.navigation.go_up_one_level(*args, **kwargs)

    def refresh_current_folder(self, *args, **kwargs):
        return self.navigation.refresh_current_folder(*args, **kwargs)

    def load_sharepoint_contents_in_details(self, *args, **kwargs):
        return self.navigation.load_sharepoint_contents_in_details(*args, **kwargs)

    def on_tree_item_clicked(self, *args, **kwargs):
        return self.navigation.on_tree_item_clicked(*args, **kwargs)

    def navigate_to_bookmark_folder(self, *args, **kwargs):
        return self.navigation.navigate_to_bookmark_folder(*args, **kwargs)

    def on_item_double_clicked(self, *args, **kwargs):
        return self.navigation.on_item_double_clicked(*args, **kwargs)

    def _setup_dual_pane(self, *args, **kwargs):
        return self.quick_links._setup_dual_pane(*args, **kwargs)

    def show_quick_links_context_menu(self, *args, **kwargs):
        return self.quick_links.show_quick_links_context_menu(*args, **kwargs)

    def open_quick_link_path(self, *args, **kwargs):
        return self.quick_links.open_quick_link_path(*args, **kwargs)

    def open_path_in_explorer(self, *args, **kwargs):
        return self.quick_links.open_path_in_explorer(*args, **kwargs)

    def refresh_quick_links_list(self, *args, **kwargs):
        return self.quick_links.refresh_quick_links_list(*args, **kwargs)

    def _update_sidebar_footer(self, *args, **kwargs):
        return self.quick_links._update_sidebar_footer(*args, **kwargs)

    def _on_bookmark_clicked(self, *args, **kwargs):
        return self.quick_links._on_bookmark_clicked(*args, **kwargs)

    def _on_bookmark_double_clicked(self, *args, **kwargs):
        return self.quick_links._on_bookmark_double_clicked(*args, **kwargs)

    def _show_bookmark_context_menu(self, *args, **kwargs):
        return self.quick_links._show_bookmark_context_menu(*args, **kwargs)

    def _open_folder_location(self, *args, **kwargs):
        return self.quick_links._open_folder_location(*args, **kwargs)

    def _show_category_context_menu(self, *args, **kwargs):
        return self.quick_links._show_category_context_menu(*args, **kwargs)

    def _rename_category_in_quick_links(self, *args, **kwargs):
        return self.quick_links._rename_category_in_quick_links(*args, **kwargs)

    def _remove_category_with_confirmation(self, *args, **kwargs):
        return self.quick_links._remove_category_with_confirmation(*args, **kwargs)

    def _show_quick_links_panel_context_menu(self, *args, **kwargs):
        return self.quick_links._show_quick_links_panel_context_menu(*args, **kwargs)

    def _create_new_category(self, *args, **kwargs):
        return self.quick_links._create_new_category(*args, **kwargs)

    def _add_bookmark_to_sidebar(self, *args, **kwargs):
        return self.quick_links._add_bookmark_to_sidebar(*args, **kwargs)

    def _remove_bookmark_from_quick_links(self, *args, **kwargs):
        return self.quick_links._remove_bookmark_from_quick_links(*args, **kwargs)

    def on_quick_link_item_dropped(self, *args, **kwargs):
        return self.quick_links.on_quick_link_item_dropped(*args, **kwargs)

    def _on_category_item_clicked(self, *args, **kwargs):
        return self.quick_links._on_category_item_clicked(*args, **kwargs)

    def _on_category_item_double_clicked(self, *args, **kwargs):
        return self.quick_links._on_category_item_double_clicked(*args, **kwargs)

    def _on_bookmark_dropped_to_category(self, *args, **kwargs):
        return self.quick_links._on_bookmark_dropped_to_category(*args, **kwargs)

    def _on_category_moved_out(self, *args, **kwargs):
        return self.quick_links._on_category_moved_out(*args, **kwargs)

    def refresh_quick_links(self, *args, **kwargs):
        return self.quick_links.refresh_quick_links(*args, **kwargs)

    def on_quick_links_reordered(self, *args, **kwargs):
        return self.quick_links.on_quick_links_reordered(*args, **kwargs)

    def on_bookmark_dropped_to_quick_links(self, *args, **kwargs):
        return self.quick_links.on_bookmark_dropped_to_quick_links(*args, **kwargs)

    def on_file_dropped_to_quick_links(self, *args, **kwargs):
        return self.quick_links.on_file_dropped_to_quick_links(*args, **kwargs)

    def on_category_dropped_to_quick_links(self, *args, **kwargs):
        return self.quick_links.on_category_dropped_to_quick_links(*args, **kwargs)

    def _remove_category_from_bookmark_bar(self, *args, **kwargs):
        return self.quick_links._remove_category_from_bookmark_bar(*args, **kwargs)

    def on_quick_link_clicked(self, *args, **kwargs):
        return self.quick_links.on_quick_link_clicked(*args, **kwargs)

    def on_quick_link_double_clicked(self, *args, **kwargs):
        return self.quick_links.on_quick_link_double_clicked(*args, **kwargs)

    def toggle_dual_pane(self, *args, **kwargs):
        return self.quick_links.toggle_dual_pane(*args, **kwargs)

    def _create_scratchpad_panel(self, *args, **kwargs):
        return self.quick_links._create_scratchpad_panel(*args, **kwargs)

    def toggle_scratchpad_panel(self, *args, **kwargs):
        return self.quick_links.toggle_scratchpad_panel(*args, **kwargs)

    def _on_scratchpad_fullscreen(self, *args, **kwargs):
        return self.quick_links._on_scratchpad_fullscreen(*args, **kwargs)
