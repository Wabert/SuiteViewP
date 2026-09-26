"""FileExplorerTab composition for the taskbar and FileNav windows."""

import ctypes
import logging
import os
import subprocess
import sys
import time
import traceback
import webbrowser
from ctypes import wintypes
from datetime import datetime
from pathlib import Path

from PyQt6 import sip
from PyQt6.QtCore import QEvent, QPoint, QRect, QSize, Qt, QTimer, pyqtSignal
from PyQt6.QtGui import (
    QAction,
    QBrush,
    QColor,
    QCursor,
    QFont,
    QIcon,
    QLinearGradient,
    QMouseEvent,
    QPainter,
    QPen,
    QPixmap,
    QStandardItemModel,
)
from PyQt6.QtWidgets import (
    QAbstractButton,
    QApplication,
    QComboBox,
    QFrame,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMenu,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSizeGrip,
    QSizePolicy,
    QSplitter,
    QStyle,
    QSystemTrayIcon,
    QTabBar,
    QTabWidget,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from suiteview import __version__ as APP_VERSION
from suiteview.core.access_control import (
    AccessDeniedError,
    AccessUnavailableError,
    can_access_app,
    get_access,
    guard_app_access,
    requires_app_access,
)
from suiteview.core.profile_paths import profile_path, profile_root
from suiteview.file_nav.file_explorer_core import DropTreeView, FileExplorerCore, NoFocusDelegate
from suiteview.file_nav.sharepoint_client import is_sp_path
from suiteview.scratchpad.scratchpad_panel import ScratchPadPanel
from suiteview.taskbar_launcher import appbar
from suiteview.taskbar_launcher.albert_launcher import AlbertButton
from suiteview.taskbar_launcher.single_instance import activation_message
from suiteview.ui.dialogs.shortcuts_dialog import AddBookmarkDialog
from suiteview.ui.widgets.bookmark_data_manager import get_bookmark_manager
from suiteview.ui.widgets.bookmark_widgets import (
    BookmarkContainer,
    BookmarkContainerRegistry,
    CATEGORY_CONTEXT_MENU_STYLE,
    CategoryButton,
    CategoryPopup,
    StandaloneBookmarkButton,
    set_footer_status_callback,
)
from suiteview.ui.widgets.file_open_history import FileOpenHistoryPanel
from suiteview.ui.widgets.frame_geometry import (
    ALL_RESIZE_EDGES,
    cursor_for_resize_edge,
    resize_edge_at,
    resize_geometry_for_edge,
    update_cursor_for_resize_edge,
)
from suiteview.ui.widgets.frameless_window import FramelessWindowBase
from suiteview.ui.widgets.uppercase_input import force_uppercase
from suiteview.ui.widgets.window_state import NativeMinimizeMixin
from suiteview.administrator.launcher import AdministratorMenuAccess

logger = logging.getLogger(__name__)
from suiteview.taskbar_launcher.file_explorer_navigation import FileExplorerNavigationMixin
from suiteview.taskbar_launcher.file_explorer_quick_links import FileExplorerQuickLinksMixin

class FileExplorerTab(FileExplorerQuickLinksMixin, FileExplorerNavigationMixin, FileExplorerCore):
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
        
        # Display names for SharePoint virtual paths (sp://... -> folder name)
        self._sp_display_names = {}
        
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
