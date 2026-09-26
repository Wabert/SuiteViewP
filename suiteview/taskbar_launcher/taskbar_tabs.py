"""SuiteViewTaskbar tab and header file-action helpers."""

import logging
from pathlib import Path

from PyQt6.QtCore import Qt
from PyQt6.QtGui import (
    QAction,
)
from PyQt6.QtWidgets import (
    QMenu,
    QTabBar,
    QToolButton,
)

from suiteview.core.access_control import (
    requires_app_access,
)
from suiteview.ui.widgets.bookmark_widgets import (
    BookmarkContainerRegistry,
)

logger = logging.getLogger(__name__)
from suiteview.taskbar_launcher.file_explorer_tab import FileExplorerTab


class TaskbarTabsMixin:
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

    @requires_app_access("FILENAV")
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
                
                # Unregister BookmarkContainers from the global registry so no
                # deleted widget is left behind (prevents crashes when a later
                # bookmark hover/drag/refresh broadcasts across all containers).
                if hasattr(widget, 'bookmark_bar'):
                    BookmarkContainerRegistry.unregister(
                        widget.bookmark_bar.bar_id, widget.bookmark_bar)
                if hasattr(widget, 'bookmark_container'):
                    BookmarkContainerRegistry.unregister(
                        widget.bookmark_container.bar_id, widget.bookmark_container)
                
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
