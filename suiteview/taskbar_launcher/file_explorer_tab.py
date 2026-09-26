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
        self._collaborators = (self.navigation, self.quick_links)
        
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

    def __getattr__(self, name: str):
        for collaborator in self._collaborators:
            if any(name in cls.__dict__ for cls in type(collaborator).__mro__):
                return getattr(collaborator, name)
        raise AttributeError(f"{type(self).__name__!s} object has no attribute {name!r}")
    
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
