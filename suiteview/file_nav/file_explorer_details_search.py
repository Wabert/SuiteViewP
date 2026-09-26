"""File Explorer Details Search."""
from __future__ import annotations

import logging
import math
import re
from pathlib import Path

from PyQt6.QtCore import (
    QRegularExpression,
    Qt,
    QTimer,
)
from PyQt6.QtGui import (
    QStandardItem,
)
from PyQt6.QtWidgets import (
    QMessageBox,
    QProgressDialog,
)

from suiteview.file_nav.file_explorer_widgets import (
    DepthScanWorker,
)
from suiteview.file_nav.sharepoint_client import (
    SharePointDepthScanWorker,
    is_sp_path,
)
from suiteview.ui.workers import WorkerController

logger = logging.getLogger(__name__)


class FileExplorerDetailsSearchMixin:
    """Requires: details search widgets, depth scan state, and details loaders.
    Provides: debounced filtering, depth search, cancellation, and result locking.
    """

    def on_details_search_changed(self, text: str) -> None:
        """Filter the details view contents with debouncing for performance.
        
        Visual feedback (border color) updates immediately for responsiveness,
        but actual filtering is debounced to avoid lag during fast typing.
        
        Supports length formulas:
        - =(len=9)     : Names exactly 9 characters
        - =(len>10)    : Names longer than 10 characters  
        - =(len<5)     : Names shorter than 5 characters
        - =(len>=8)    : Names 8 or more characters
        - =(len<=12)   : Names 12 or fewer characters
        - =(len!=7)    : Names not 7 characters
        """
        if not hasattr(self, 'details_sort_proxy'):
            return

        query = (text or "").strip()
        
        # Update search box border IMMEDIATELY for visual feedback (no debounce)
        if query:
            # Red border when filter is active
            self.details_search.setStyleSheet(
                """
                QLineEdit {
                    padding: 3px 8px;
                    border: 3px solid #DC143C;
                    border-radius: 3px;
                    background: white;
                    color: #1A3A6E;
                }
                """
            )
        else:
            # Normal border when no filter
            self.details_search.setStyleSheet(
                """
                QLineEdit {
                    padding: 3px 8px;
                    border: 1px solid #A0B8D8;
                    border-radius: 3px;
                    background: white;
                    color: #1A3A6E;
                }
                """
            )
        
        # Save the search term for the current folder (immediate, no debounce needed)
        if hasattr(self, 'current_details_folder') and self.current_details_folder:
            if query:
                self.folder_search_terms[self.current_details_folder] = query
            elif self.current_details_folder in self.folder_search_terms:
                # Remove empty search terms to keep dict clean
                del self.folder_search_terms[self.current_details_folder]
        
        # Debounce the actual filter application for performance
        # This prevents lag when typing quickly
        if self._search_debounce_timer is not None:
            self._search_debounce_timer.stop()
        
        self._search_debounce_timer = QTimer()
        self._search_debounce_timer.setSingleShot(True)
        self._search_debounce_timer.timeout.connect(lambda: self._apply_search_filter(query))
        self._search_debounce_timer.start(150)  # Apply filter after 150ms of no typing

    def _apply_search_filter(self, query: str) -> None:
        """Actually apply the search filter (called after debounce delay)"""
        if not hasattr(self, 'details_sort_proxy'):
            return
        
        # Check for length formula: =(len=9), =(len>10), etc.
        length_pattern = r'^=\s*\(\s*len\s*(=|>|<|>=|<=|!=)\s*(\d+)\s*\)$'
        length_match = re.match(length_pattern, query, re.IGNORECASE)
        
        if length_match:
            # Parse length formula
            operator = length_match.group(1)
            value = int(length_match.group(2))
            
            # Apply length filter (clear regex filter)
            self.details_sort_proxy.setFilterRegularExpression(QRegularExpression())
            self.details_sort_proxy.setLengthFilter(operator, value)
            return
        
        # Clear length filter for normal searches
        self.details_sort_proxy.clearLengthFilter()
        
        # Standard search using proxy filter (works for both normal and depth results)
        if not query:
            self.details_sort_proxy.setFilterRegularExpression(QRegularExpression())
            return

        # Treat user input as a literal substring match (case-insensitive)
        escaped = QRegularExpression.escape(query)
        regex = QRegularExpression(escaped, QRegularExpression.PatternOption.CaseInsensitiveOption)
        self.details_sort_proxy.setFilterRegularExpression(regex)

    def toggle_depth_search(self):
        """Toggle depth search on/off based on button state"""
        # Guard against callback during widget deletion
        try:
            if not self.isVisible() or not hasattr(self, 'depth_search_enabled'):
                return
        except RuntimeError:
            # Widget is being deleted
            return
        
        if self.depth_search_enabled:
            # Currently ON, turn it OFF
            self.depth_search_enabled = False
            self.depth_search_locked = False
            self.depth_search_active_results = None
            self.depth_toggle_btn.setText("Off")
            self.depth_toggle_btn.setToolTip("Depth search is off")
            self.depth_toggle_btn.setStyleSheet("""
                QPushButton {
                    background-color: #E0ECFF;
                    border: 1px solid #2563EB;
                    border-radius: 3px;
                    padding: 2px 6px;
                    font-size: 9pt;
                    color: #1A3A6E;
                    font-weight: bold;
                }
                QPushButton:hover {
                    background-color: #C9DAFF;
                }
            """)
            
            # Hide home button
            if hasattr(self, 'depth_home_btn'):
                self.depth_home_btn.hide()
            
            # Re-enable tree panel
            if hasattr(self, 'tree_view'):
                self.tree_view.setEnabled(True)
            
            # Restore normal breadcrumb bar style
            self._apply_depth_search_locked_style(locked=False)
            
            # Clear cache and search folder
            self.depth_search_cache.clear()
            self.depth_search_folder = None
            self.depth_search_folder_name = None
            
            # Reset combo to 1
            self.depth_level_combo.setCurrentText("1")
            
            # Clear search and restore normal view
            self.details_search.clear()
            self._reload_current_details_folder()
        else:
            # Currently OFF, turn it ON
            depth_level = self.depth_level_combo.currentText()
            
            if depth_level == "1":
                # Depth 1 doesn't need async scan, just notify user
                QMessageBox.information(self, "Depth Search", 
                    "Depth level 1 shows only current folder items.\n\n"
                    "Set depth to 2 or higher for subfolder search.")
                return
            
            # Start depth scan
            if not self.current_details_folder:
                return
            
            self.depth_search_enabled = True
            
            # Show home button
            if hasattr(self, 'depth_home_btn'):
                self.depth_home_btn.show()
            
            self.perform_depth_scan_and_populate(depth_level)

    def on_depth_level_changed(self, level_text):
        """Handle depth level change - clear cache"""
        # Guard against callback during widget deletion
        try:
            if not self.isVisible() or not hasattr(self, 'depth_search_cache'):
                return
        except RuntimeError:
            # Widget is being deleted
            return
        
        self.depth_search_cache.clear()
        
        # If depth search is active and user changes level, turn it off
        if self.depth_search_enabled:
            self.depth_search_enabled = False
            self.depth_search_locked = False
            self.depth_search_active_results = None
            self.depth_toggle_btn.setText("Off")
            self.depth_toggle_btn.setToolTip("Depth search is off")
            self.depth_toggle_btn.setStyleSheet("""
                QPushButton {
                    background-color: #E0ECFF;
                    border: 1px solid #2563EB;
                    border-radius: 3px;
                    padding: 2px 6px;
                    font-size: 9pt;
                    color: #1A3A6E;
                    font-weight: bold;
                }
                QPushButton:hover {
                    background-color: #C9DAFF;
                }
            """)
            self.depth_search_folder = None
            
            # Hide home button
            if hasattr(self, 'depth_home_btn'):
                self.depth_home_btn.hide()
            
            # Re-enable tree panel
            if hasattr(self, 'tree_view'):
                self.tree_view.setEnabled(True)
            
            # Restore normal toolbar color
            self._apply_compact_toolbar_style(self.toolbar, locked=False)
            
            # Restore normal view
            self._reload_current_details_folder()

    def _reload_current_details_folder(self):
        """Reload the current details folder (local path or SharePoint)."""
        if not self.current_details_folder:
            return
        if is_sp_path(self.current_details_folder):
            self.load_sharepoint_contents_in_details(
                self.current_details_folder, getattr(self, '_sp_current_name', None))
        else:
            self.load_folder_contents_in_details(Path(self.current_details_folder))

    def go_to_depth_search_home(self):
        """Navigate to the root folder of the current depth search (keeps depth search active)"""
        if hasattr(self, 'depth_search_folder') and self.depth_search_folder:
            # Navigate to the depth search root folder WITHOUT turning off depth search
            # Update breadcrumb to show the root folder
            if hasattr(self, 'update_breadcrumb'):
                self.update_breadcrumb(self.depth_search_folder)
            
            # Clear any search filter to show all depth search results
            if hasattr(self, 'details_search'):
                self.details_search.clear()
            
            # Reload the folder contents in the details panel
            if is_sp_path(self.depth_search_folder):
                # Locked restore in load_sharepoint_contents_in_details shows
                # the depth results instead of re-listing the folder
                self.load_sharepoint_contents_in_details(
                    self.depth_search_folder, self.depth_search_folder_name)
            else:
                self.load_folder_contents_in_details(Path(self.depth_search_folder))

    def perform_depth_scan_and_populate(self, depth_level):
        """Perform depth scan and populate all results (no search filter)"""
        if not self.current_details_folder:
            return
        
        # Convert "Max" to -1 for unlimited depth
        if depth_level == "Max":
            depth_level_int = -1
        else:
            depth_level_int = int(depth_level)
        
        search_folder = self.current_details_folder
        
        # Check if we have cached results for this folder and depth
        cache_key = search_folder
        if (cache_key in self.depth_search_cache and 
            depth_level_int in self.depth_search_cache[cache_key]):
            # Use cached results
            self._populate_depth_results(self.depth_search_cache[cache_key][depth_level_int])
            self.depth_toggle_btn.setText("On")
            self.depth_toggle_btn.setToolTip("Depth search is on")
            self.depth_toggle_btn.setStyleSheet("""
                QPushButton {
                    background-color: #FFB366;
                    border: 1px solid #FF8C00;
                    border-radius: 3px;
                    padding: 2px 6px;
                    font-size: 9pt;
                    color: #1A3A6E;
                    font-weight: bold;
                }
                QPushButton:hover {
                    background-color: #FFC080;
                }
            """)
            return
        
        # Start async scan
        self.depth_search_folder = search_folder
        self.depth_search_folder_name = (
            getattr(self, '_sp_current_name', None) if is_sp_path(search_folder)
            else None)
        
        # Create and start worker thread (SharePoint folders scan via Graph API)
        if is_sp_path(search_folder):
            self.depth_scan_worker = SharePointDepthScanWorker(search_folder, depth_level_int)
        else:
            self.depth_scan_worker = DepthScanWorker(search_folder, depth_level_int)
        self.depth_scan_controller = WorkerController(
            self,
            self.depth_scan_worker,
            cancel=self.depth_scan_worker.cancel,
        )
        self.depth_scan_controller.result.connect(self._on_depth_scan_complete)
        self.depth_scan_controller.progress.connect(
            lambda payload: self._on_depth_scan_progress(payload[0], payload[1])
        )
        
        # Create progress dialog with 3 second delay and actual progress bar
        self.depth_progress_dialog = QProgressDialog("Scanning subfolders...", "Stop", 0, 100, self)
        self.depth_progress_dialog.setWindowTitle("Loading Depth Search")
        self.depth_progress_dialog.setWindowModality(Qt.WindowModality.WindowModal)
        self.depth_progress_dialog.setMinimumDuration(3000)  # Show after 3 seconds
        self.depth_progress_dialog.setAutoClose(False)
        self.depth_progress_dialog.setAutoReset(False)
        self.depth_progress_dialog.setValue(0)  # Start at 0
        self.depth_progress_dialog.canceled.connect(self._on_depth_scan_cancelled)
        
        # Store start time for progress calculation
        self.depth_scan_start_count = 0
        
        # Start worker
        self.depth_scan_controller.start()

    def _on_depth_scan_progress(self, count: int, message: str):
        """Update progress dialog during depth scan"""
        if hasattr(self, 'depth_progress_dialog') and self.depth_progress_dialog:
            # Calculate a rough progress percentage (we don't know total, so use logarithmic scale)
            # This gives a sense of progress even without knowing the total
            if count > 0:
                # Use logarithmic scale for smoother progress: log(count+1) / log(10000+1) * 100
                # Caps at ~100% around 10000 items
                progress = min(99, int((math.log(count + 1) / math.log(10000 + 1)) * 100))
                self.depth_progress_dialog.setValue(progress)
            
            self.depth_progress_dialog.setLabelText(f"{message}\n{count} items found")

    def _on_depth_scan_cancelled(self):
        """Handle cancellation of depth scan"""
        if hasattr(self, 'depth_scan_worker') and self.depth_scan_worker:
            # Request worker to stop. The controller owns the thread and will
            # finish asynchronously without blocking the UI thread.
            if hasattr(self, 'depth_scan_controller') and self.depth_scan_controller:
                self.depth_scan_controller.cancel()
            else:
                self.depth_scan_worker.cancel()
            
            # The worker will emit finished signal with partial results
            # Just close the progress dialog
            if hasattr(self, 'depth_progress_dialog') and self.depth_progress_dialog:
                self.depth_progress_dialog.close()

    def _on_depth_scan_complete(self, results: list):
        """Handle completion of depth scan"""
        if not hasattr(self, 'depth_progress_dialog'):
            return
        
        # Check if scan was cancelled (partial results)
        was_cancelled = hasattr(self, 'depth_scan_worker') and self.depth_scan_worker._cancelled
        
        # Cache the results (even if partial from cancellation)
        search_folder = self.depth_search_folder
        depth_level_text = self.depth_level_combo.currentText()
        
        depth_level_key = self._depth_level_cache_key(depth_level_text)
        
        # Only cache if not cancelled (partial results shouldn't be cached)
        if not was_cancelled:
            if search_folder not in self.depth_search_cache:
                self.depth_search_cache[search_folder] = {}
            self.depth_search_cache[search_folder][depth_level_key] = results
        
        # Close progress dialog
        if self.depth_progress_dialog:
            self.depth_progress_dialog.close()
        
        # If no results, don't proceed
        if not results:
            self.depth_search_enabled = False
            self._set_depth_toggle_off()
            return
        
        # Check if we're still in the search folder
        currently_in_search_folder = (self.current_details_folder == search_folder)
        
        if currently_in_search_folder:
            # Populate all results (partial or complete)
            self._populate_depth_results(results)
            
            self._lock_depth_search_results(results)
        else:
            # Show dialog with "Go to search folder" button
            msg_box = QMessageBox(self)
            msg_box.setWindowTitle("Depth Search Complete")
            msg_box.setText(f"Found {len(results)} items at depth {depth_level_text}")
            msg_box.setInformativeText(f"Search folder: {search_folder}")
            
            # Add "Go to search folder" button
            go_button = msg_box.addButton("Go to search folder", QMessageBox.ButtonRole.AcceptRole)
            close_button = msg_box.addButton("Close", QMessageBox.ButtonRole.RejectRole)
            
            msg_box.exec()
            
            # Check which button was clicked
            if msg_box.clickedButton() == go_button:
                # Enable lock mode BEFORE navigating so the folder loaders
                # restore the depth results (SharePoint loads are async and
                # would otherwise overwrite them when the listing returns)
                self.depth_search_locked = True
                self.depth_search_active_results = results
                
                # Navigate to search folder — the locked-restore branch in the
                # loader populates the depth results
                if is_sp_path(search_folder):
                    self.load_sharepoint_contents_in_details(
                        search_folder, self.depth_search_folder_name)
                else:
                    self.load_folder_contents_in_details(Path(search_folder))
                
                self._lock_depth_search_results(results)
            else:
                # User closed dialog, turn off depth search
                self.depth_search_enabled = False
                self._set_depth_toggle_off()

    def _depth_level_cache_key(self, depth_level_text: str) -> int:
        return -1 if depth_level_text == "Max" else int(depth_level_text)

    def _lock_depth_search_results(self, results: list):
        self.depth_search_locked = True
        self.depth_search_active_results = results
        if hasattr(self, 'tree_view'):
            self.tree_view.setEnabled(False)
        self._apply_depth_search_locked_style(locked=True)
        self._set_depth_toggle_on()

    def _set_depth_toggle_on(self):
        self.depth_toggle_btn.setText("On")
        self.depth_toggle_btn.setToolTip("Depth search is on (click to turn off)")
        self.depth_toggle_btn.setStyleSheet("""
            QPushButton {
                background-color: #FF6B6B;
                border: 1px solid #CC4444;
                border-radius: 3px;
                padding: 2px 6px;
                font-size: 9pt;
                color: #FFFFFF;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #FF8888;
            }
        """)

    def _set_depth_toggle_off(self):
        self.depth_toggle_btn.setText("Off")
        self.depth_toggle_btn.setToolTip("Depth search is off")
        self.depth_toggle_btn.setStyleSheet("""
            QPushButton {
                background-color: #E0ECFF;
                border: 1px solid #2563EB;
                border-radius: 3px;
                padding: 2px 6px;
                font-size: 9pt;
                color: #1A3A6E;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #C9DAFF;
            }
        """)

    def _populate_depth_results(self, depth_items: list):
        """Populate view with all depth search results (no filtering)"""
        if not depth_items:
            return
        
        # Clear the model
        self.details_model.clear()
        self.details_model.setHorizontalHeaderLabels(['Name', 'Size', 'Type', 'Date Modified', 'Date Accessed'])
        
        # Restore column widths
        header_view = self.details_view.header()
        try:
            header_view.sectionResized.disconnect(self.on_column_resized)
        except Exception:
            logger.debug("Suppressed File Explorer exception", exc_info=True)
        
        default_widths = [350, 100, 120, 150, 150]
        for col in range(5):
            width = self.column_widths.get(f'col_{col}', default_widths[col])
            self.details_view.setColumnWidth(col, width)
        
        header_view.sectionResized.connect(self.on_column_resized)
        
        # Sort by depth level then alphabetically
        sorted_items = sorted(depth_items, key=lambda x: (x['depth'], x['display_name'].lower()))
        
        # PERFORMANCE: Disable view updates during bulk insertion
        self.details_view.setUpdatesEnabled(False)
        try:
            # Add all items to view
            for item in sorted_items:
                row_items = self._create_depth_search_item(item)
                self.details_model.appendRow(row_items)
        finally:
            # Re-enable updates and trigger single repaint
            self.details_view.setUpdatesEnabled(True)
        
        # Update footer
        self.update_details_footer()

    def _create_depth_search_item(self, item_data: dict):
        """Create a row item for depth search results"""
        display_name = item_data['display_name']
        full_path = item_data['path']
        is_dir = item_data['is_dir']
        depth = item_data['depth']
        size = item_data.get('size', 0)
        modified = item_data.get('modified', '')
        accessed = item_data.get('accessed', '')
        
        # SharePoint results carry sp:// virtual paths — derive icon/type from
        # the item's leaf name (the sp path is an opaque drive/item id pair)
        is_sp = is_sp_path(full_path)
        if is_sp:
            leaf_name = item_data.get('name') or display_name.split(' | ')[-1]
            path_obj = Path(leaf_name)
        else:
            path_obj = Path(full_path)
        
        # Create name item with icon
        name_item = QStandardItem(display_name)
        icon = self._get_cached_icon(path_obj, is_dir)
        name_item.setIcon(icon)
        name_item.setData(full_path, Qt.ItemDataRole.UserRole)
        if is_sp:
            # Same roles as _create_sp_details_row so double-click nav/open works
            name_item.setData("folder" if is_dir else "file", Qt.ItemDataRole.UserRole + 3)
            name_item.setData(item_data.get('web_url', ''), Qt.ItemDataRole.UserRole + 4)
            name_item.setData(path_obj.name, Qt.ItemDataRole.UserRole + 5)
            name_item.setEditable(False)
        
        # Set sort data (depth prefix for proper sorting)
        sort_prefix = f"{depth}_{'0' if is_dir else '1'}_"
        name_item.setData(sort_prefix + display_name.lower(), Qt.ItemDataRole.UserRole + 1)
        
        # Size item
        size_item = QStandardItem()
        if not is_dir and size > 0:
            if size < 1024:
                size_str = f"{size} B"
            elif size < 1024 * 1024:
                size_str = f"{size / 1024:.1f} KB"
            elif size < 1024 * 1024 * 1024:
                size_str = f"{size / (1024 * 1024):.1f} MB"
            else:
                size_str = f"{size / (1024 * 1024 * 1024):.2f} GB"
            size_item.setText(size_str)
            size_item.setData(size, Qt.ItemDataRole.UserRole + 1)
        else:
            size_item.setData(0, Qt.ItemDataRole.UserRole + 1)
        
        # Type item
        type_item = QStandardItem("Folder" if is_dir else path_obj.suffix.upper().lstrip('.'))
        type_item.setData(full_path, Qt.ItemDataRole.UserRole)
        
        # Modified item
        modified_item = QStandardItem(modified)
        modified_item.setData(full_path, Qt.ItemDataRole.UserRole)
        
        # Accessed item
        accessed_item = QStandardItem(accessed)
        accessed_item.setData(full_path, Qt.ItemDataRole.UserRole)
        
        return [name_item, size_item, type_item, modified_item, accessed_item]

    def eventFilter(self, obj, event):
        """Handle keyboard shortcuts in details view (F2 for rename, Ctrl+V for paste, Delete)"""
        if obj == self.details_view and event.type() == event.Type.KeyPress:
            modifiers = event.modifiers()
            key = event.key()
            
            if key == Qt.Key.Key_F2:
                # Get selected item
                indexes = self.details_view.selectedIndexes()
                if indexes:
                    # Get the name column (column 0) of the first selected row
                    name_index = self.details_view.model().index(indexes[0].row(), 0)
                    self.details_view.edit(name_index)
                    return True
            elif key == Qt.Key.Key_Delete:
                # Delete key - delete selected file(s)
                self.delete_file()
                return True
            elif key == Qt.Key.Key_V and (modifiers & Qt.KeyboardModifier.ControlModifier):
                # Ctrl+V - Paste
                self.paste_file()
                return True
            elif key == Qt.Key.Key_C and (modifiers & Qt.KeyboardModifier.ControlModifier):
                # Ctrl+C - Copy
                self.copy_file()
                return True
            elif key == Qt.Key.Key_X and (modifiers & Qt.KeyboardModifier.ControlModifier):
                # Ctrl+X - Cut
                self.cut_file()
                return True
        
        return super().eventFilter(obj, event)
