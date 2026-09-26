"""File Explorer helper widgets."""
from __future__ import annotations

import logging
import os
from datetime import datetime
from pathlib import Path

from PyQt6.QtCore import (
    QMimeData,
    QObject,
    QSortFilterProxyModel,
    Qt,
    QUrl,
    pyqtSignal,
)
from PyQt6.QtGui import (
    QDrag,
    QDragEnterEvent,
    QDragMoveEvent,
    QDropEvent,
)
from PyQt6.QtWidgets import (
    QCheckBox,
    QDialog,
    QDialogButtonBox,
    QLabel,
    QStyle,
    QStyledItemDelegate,
    QTreeView,
    QVBoxLayout,
)

from suiteview.file_nav.sharepoint_client import (
    is_sp_path,
)
from suiteview.ui.workers import WorkerSignals

logger = logging.getLogger(__name__)


class FileSortProxyModel(QSortFilterProxyModel):
    """Custom sort proxy that uses UserRole+1 data for proper sorting
    
    Also supports length-based filtering with formulas:
    - =(len=9)     : Names exactly 9 characters
    - =(len>10)    : Names longer than 10 characters  
    - =(len<5)     : Names shorter than 5 characters
    - =(len>=8)    : Names 8 or more characters
    - =(len<=12)   : Names 12 or fewer characters
    - =(len!=7)    : Names not 7 characters
    """
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self._length_filter = None  # Tuple of (operator, value) or None
    
    def setLengthFilter(self, operator: str, value: int):
        """Set a length-based filter. operator is one of: =, >, <, >=, <=, !="""
        self._length_filter = (operator, value)
        self.invalidateFilter()
    
    def clearLengthFilter(self):
        """Clear the length filter"""
        self._length_filter = None
        self.invalidateFilter()
    
    def filterAcceptsRow(self, source_row: int, source_parent) -> bool:
        """Override to apply length filter in addition to regex filter"""
        # First check length filter if active
        if self._length_filter:
            operator, target_len = self._length_filter
            # Get the name from column 0
            index = self.sourceModel().index(source_row, 0, source_parent)
            name = self.sourceModel().data(index, Qt.ItemDataRole.DisplayRole)
            if name:
                name_len = len(str(name))
                # Apply operator comparison
                if operator == '=':
                    if name_len != target_len:
                        return False
                elif operator == '>':
                    if name_len <= target_len:
                        return False
                elif operator == '<':
                    if name_len >= target_len:
                        return False
                elif operator == '>=':
                    if name_len < target_len:
                        return False
                elif operator == '<=':
                    if name_len > target_len:
                        return False
                elif operator == '!=':
                    if name_len == target_len:
                        return False
            else:
                return False  # No name, filter out
        
        # Then apply the standard regex filter
        return super().filterAcceptsRow(source_row, source_parent)
    
    def lessThan(self, left, right):
        """Compare items using custom sort data"""
        # Get the sort data (UserRole + 1) from both items
        left_data = self.sourceModel().data(left, Qt.ItemDataRole.UserRole + 1)
        right_data = self.sourceModel().data(right, Qt.ItemDataRole.UserRole + 1)
        
        # If both have sort data, use it
        if left_data is not None and right_data is not None:
            # Handle numeric comparison
            if isinstance(left_data, (int, float)) and isinstance(right_data, (int, float)):
                return left_data < right_data
            # Handle string comparison (includes folder/file prefix)
            return str(left_data) < str(right_data)
        
        # Fallback to display text
        left_text = self.sourceModel().data(left, Qt.ItemDataRole.DisplayRole)
        right_text = self.sourceModel().data(right, Qt.ItemDataRole.DisplayRole)
        
        if left_text is None:
            left_text = ""
        if right_text is None:
            right_text = ""
            
        return str(left_text).lower() < str(right_text).lower()

class NoFocusDelegate(QStyledItemDelegate):
    """Custom delegate that removes the focus rectangle from items"""
    
    def paint(self, painter, option, index):
        # Remove focus indicator - this removes the dotted focus rectangle
        option.state = option.state & ~QStyle.StateFlag.State_HasFocus
        super().paint(painter, option, index)

class DropTreeView(QTreeView):
    """Custom QTreeView that accepts file drops and supports dragging files out"""
    
    # Signal emitted when files are dropped (list of paths, destination folder)
    files_dropped = pyqtSignal(list, str)
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAcceptDrops(True)
        self.setDragEnabled(True)
        self.setDragDropMode(QTreeView.DragDropMode.DragDrop)
        self.setDropIndicatorShown(True)
        self.setDefaultDropAction(Qt.DropAction.CopyAction)
        self._file_explorer = None  # Reference to FileExplorerCore for getting folder paths
        self._current_folder = None  # Current folder being displayed
    
    def set_file_explorer(self, explorer):
        """Set reference to the file explorer for accessing current folder"""
        self._file_explorer = explorer
    
    def set_current_folder(self, folder_path):
        """Set the current folder path"""
        self._current_folder = folder_path
    
    def mouseDoubleClickEvent(self, event):
        """Override to prevent edit mode on double-click, but allow signal emission"""
        # Get the index at the click position
        index = self.indexAt(event.pos())
        if index.isValid():
            # Emit the doubleClicked signal manually
            self.doubleClicked.emit(index)
            # Accept the event to prevent further processing
            event.accept()
            return
        # If no valid index, call parent handler
        super().mouseDoubleClickEvent(event)
    
    def startDrag(self, supportedActions):
        """Start drag operation with selected files"""
        indexes = self.selectedIndexes()
        if not indexes:
            return
        
        # Get unique file paths from selected rows. SharePoint rows carry an
        # sp:// virtual path — drag those as their real SharePoint web URL so
        # drop targets (e.g. the bookmarks bar) can store a working link.
        urls = []
        seen_rows = set()
        for index in indexes:
            row = index.row()
            if row not in seen_rows:
                seen_rows.add(row)
                # Get path from column 0
                col0_index = index.sibling(row, 0)
                path = self.model().data(col0_index, Qt.ItemDataRole.UserRole)
                if not path:
                    continue
                if is_sp_path(path):
                    web_url = self.model().data(col0_index, Qt.ItemDataRole.UserRole + 4)
                    if web_url:
                        urls.append(QUrl(web_url))
                elif os.path.exists(path):
                    urls.append(QUrl.fromLocalFile(path))
        
        if not urls:
            return
        
        # Create mime data with file URLs
        mime_data = QMimeData()
        mime_data.setUrls(urls)
        
        # Create and execute drag
        drag = QDrag(self)
        drag.setMimeData(mime_data)
        drag.exec(Qt.DropAction.CopyAction)
    
    def dragEnterEvent(self, event: QDragEnterEvent):
        """Handle drag enter - accept if it contains file URLs"""
        if event.mimeData().hasUrls():
            # Check if any URLs are local files
            for url in event.mimeData().urls():
                if url.isLocalFile():
                    event.acceptProposedAction()
                    return
        event.ignore()
    
    def dragMoveEvent(self, event: QDragMoveEvent):
        """Handle drag move - highlight target folder if hovering over one"""
        if event.mimeData().hasUrls():
            # Check if hovering over a folder item
            index = self.indexAt(event.position().toPoint())
            if index.isValid():
                # Get the path from the model
                path = self.model().data(index, Qt.ItemDataRole.UserRole)
                if not path:
                    # Try column 0
                    col0_index = index.sibling(index.row(), 0)
                    path = self.model().data(col0_index, Qt.ItemDataRole.UserRole)
                
                if path and os.path.isdir(path):
                    # Hovering over a folder - will drop into it
                    event.acceptProposedAction()
                    return
            
            # Not over a folder item - will drop into current folder
            if self._current_folder and os.path.isdir(self._current_folder):
                event.acceptProposedAction()
                return
        
        event.ignore()
    
    def dropEvent(self, event: QDropEvent):
        """Handle drop - copy FILES ONLY to target folder (folders are blocked to prevent accidents)"""
        if not event.mimeData().hasUrls():
            event.ignore()
            return
        
        # Get dropped file paths
        dropped_files = []
        for url in event.mimeData().urls():
            if url.isLocalFile():
                file_path = url.toLocalFile()
                if os.path.exists(file_path):
                    dropped_files.append(file_path)
        
        if not dropped_files:
            event.ignore()
            return
        
        # SAFETY: Reject any folders being dropped - only files allowed
        # This prevents accidental folder moves/copies
        for dropped_path in dropped_files:
            if os.path.isdir(dropped_path):
                event.ignore()
                return
        
        # SAFETY: If dropping within the same current folder view, ignore completely
        # This prevents accidental copies/moves when dragging and dropping in details view
        if self._current_folder:
            current_folder_resolved = str(Path(self._current_folder).resolve()).lower()
            
            for dropped_path in dropped_files:
                dropped_parent = str(Path(dropped_path).resolve().parent).lower()
                
                # If the dropped item came from the current folder, ignore the drop entirely
                if dropped_parent == current_folder_resolved:
                    event.ignore()
                    return
        
        # Determine destination folder
        dest_folder = None
        index = self.indexAt(event.position().toPoint())
        
        if index.isValid():
            # Get the path from the model
            path = self.model().data(index, Qt.ItemDataRole.UserRole)
            if not path:
                # Try column 0
                col0_index = index.sibling(index.row(), 0)
                path = self.model().data(col0_index, Qt.ItemDataRole.UserRole)
            
            if path:
                if os.path.isdir(path):
                    dest_folder = path
                else:
                    # Dropped on a file - use its parent folder
                    dest_folder = str(Path(path).parent)
        
        # If no folder from drop target, use current folder
        if not dest_folder:
            dest_folder = self._current_folder
        
        if dest_folder and os.path.isdir(dest_folder):
            # Additional safety checks
            dest_folder_resolved = str(Path(dest_folder).resolve()).lower()
            
            for dropped_path in dropped_files:
                dropped_resolved = str(Path(dropped_path).resolve()).lower()
                dropped_parent = str(Path(dropped_path).resolve().parent).lower()
                
                # Case 1: Dropping item onto itself
                if dropped_resolved == dest_folder_resolved:
                    event.ignore()
                    return
                
                # Case 2: Item is already in the destination folder
                if dropped_parent == dest_folder_resolved:
                    event.ignore()
                    return
            
            # Safe to proceed - emit signal with dropped files and destination
            self.files_dropped.emit(dropped_files, dest_folder)
            event.acceptProposedAction()
        else:
            event.ignore()

class DropFolderTreeView(QTreeView):
    """Custom QTreeView for folder navigation that accepts file drops and folder pins"""
    
    # Signal emitted when files are dropped (list of paths, destination folder)
    files_dropped = pyqtSignal(list, str)
    # Signal emitted when a folder is dropped to be pinned
    folder_pinned = pyqtSignal(str)
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAcceptDrops(True)
        self.setDragDropMode(QTreeView.DragDropMode.DropOnly)
        self.setDropIndicatorShown(True)
        self._file_explorer = None
    
    def set_file_explorer(self, explorer):
        """Set reference to the file explorer for handling drops"""
        self._file_explorer = explorer
    
    def dragEnterEvent(self, event: QDragEnterEvent):
        """Handle drag enter - accept if it contains file URLs"""
        if event.mimeData().hasUrls():
            for url in event.mimeData().urls():
                if url.isLocalFile():
                    event.acceptProposedAction()
                    return
        event.ignore()
    
    def dragMoveEvent(self, event: QDragMoveEvent):
        """Handle drag move - accept folders for pinning OR files for dropping into folders"""
        if event.mimeData().hasUrls():
            # Check what's being dragged
            dragging_folders_only = True
            dragging_files = False
            for url in event.mimeData().urls():
                if url.isLocalFile():
                    path = url.toLocalFile()
                    if os.path.isdir(path):
                        pass  # It's a folder
                    else:
                        dragging_folders_only = False
                        dragging_files = True
            
            # If dragging only folders, accept anywhere (for pinning)
            if dragging_folders_only:
                event.acceptProposedAction()
                return
            
            # If dragging files, only accept over a folder target
            if dragging_files:
                index = self.indexAt(event.position().toPoint())
                if index.isValid():
                    path = self.model().data(index, Qt.ItemDataRole.UserRole)
                    if path and os.path.isdir(path):
                        event.acceptProposedAction()
                        return
        event.ignore()
    
    def dropEvent(self, event: QDropEvent):
        """Handle drop - pin folders OR copy files to target folder"""
        if not event.mimeData().hasUrls():
            event.ignore()
            return
        
        # Separate folders and files
        dropped_folders = []
        dropped_files = []
        for url in event.mimeData().urls():
            if url.isLocalFile():
                file_path = url.toLocalFile()
                if os.path.exists(file_path):
                    if os.path.isdir(file_path):
                        dropped_folders.append(file_path)
                    else:
                        dropped_files.append(file_path)
        
        # If only folders were dropped, pin them
        if dropped_folders and not dropped_files:
            for folder_path in dropped_folders:
                self.folder_pinned.emit(folder_path)
            event.acceptProposedAction()
            return
        
        # If files were dropped, handle as before (copy to target folder)
        if dropped_files:
            # Get destination folder from drop target
            index = self.indexAt(event.position().toPoint())
            if not index.isValid():
                event.ignore()
                return
            
            path = self.model().data(index, Qt.ItemDataRole.UserRole)
            if not path or not os.path.isdir(path):
                event.ignore()
                return
            
            dest_folder = path
            
            # SAFETY CHECK: Prevent same-folder drops
            dest_folder_resolved = str(Path(dest_folder).resolve()).lower()
            
            for dropped_path in dropped_files:
                dropped_resolved = str(Path(dropped_path).resolve()).lower()
                dropped_parent = str(Path(dropped_path).resolve().parent).lower()
                
                # Case 1: Dropping item onto itself
                if dropped_resolved == dest_folder_resolved:
                    event.ignore()
                    return
                
                # Case 2: Item is already in the destination folder
                if dropped_parent == dest_folder_resolved:
                    event.ignore()
                    return
            
            # Safe to proceed - emit signal with dropped files and destination
            self.files_dropped.emit(dropped_files, dest_folder)
            event.acceptProposedAction()
        else:
            event.ignore()

class DepthScanWorker(QObject):
    """Background thread for scanning folders at specified depth"""

    def __init__(self, root_path, depth_level):
        super().__init__()
        self.signals = WorkerSignals(self)
        self.root_path = root_path
        self.depth_level = depth_level
        self._cancelled = False
        
    def cancel(self):
        """Request cancellation of the scan"""
        self._cancelled = True
        
    def run(self):
        """Scan folders up to specified depth and return results"""
        results = []
        
        try:
            root = Path(self.root_path)
            
            # Scan folders recursively up to depth_level
            self._scan_folder(root, "", 0, results)
            
        except Exception as e:
            logger.error(f"Error during depth scan: {e}")
        
        if self._cancelled:
            self.signals.cancelled.emit()
        self.signals.result.emit(results)
        self.signals.finished.emit()
    
    def _scan_folder(self, folder_path: Path, relative_path: str, current_depth: int, results: list):
        """Recursively scan folder up to specified depth"""
        # Check if cancelled
        if self._cancelled:
            return
        
        # If depth_level is -1 (Max), scan everything; otherwise check depth limit
        if self.depth_level != -1 and current_depth >= self.depth_level:
            return
        
        try:
            # Get all items in this folder
            with os.scandir(str(folder_path)) as entries:
                folders = []
                files = []
                
                for entry in entries:
                    try:
                        is_dir = entry.is_dir()
                        item_path = Path(entry.path)
                        
                        # Build display name with pipe delimiters
                        if relative_path:
                            display_name = f"{relative_path} | {entry.name}"
                        else:
                            display_name = entry.name
                        
                        # Get file stats (if not network drive)
                        size = 0
                        modified = ""
                        accessed = ""
                        
                        try:
                            stat_info = entry.stat()
                            size = stat_info.st_size if not is_dir else 0
                            modified = datetime.fromtimestamp(stat_info.st_mtime).strftime("%Y-%m-%d %H:%M")
                            accessed = datetime.fromtimestamp(stat_info.st_atime).strftime("%Y-%m-%d %H:%M")
                        except Exception:
                            logger.debug("Suppressed File Explorer exception", exc_info=True)
                        
                        # Add to results
                        item_data = {
                            'path': str(item_path),
                            'display_name': display_name,
                            'is_dir': is_dir,
                            'depth': current_depth + 1,
                            'size': size,
                            'modified': modified,
                            'accessed': accessed
                        }
                        
                        if is_dir:
                            folders.append((item_path, display_name))
                        
                        results.append(item_data)
                        
                        # Emit progress every 50 items
                        if len(results) % 50 == 0:
                            self.signals.progress.emit((len(results), f"Scanning depth {current_depth + 1}..."))
                        
                    except (PermissionError, OSError):
                        continue
                
                # Recursively scan subfolders if we haven't reached max depth (or if Max mode)
                if self.depth_level == -1 or current_depth + 1 < self.depth_level:
                    for subfolder_path, subfolder_display in folders:
                        self._scan_folder(subfolder_path, subfolder_display, current_depth + 1, results)
                        
        except (PermissionError, OSError):
            logger.debug("Suppressed File Explorer exception", exc_info=True)

class PrintDirectoryDialog(QDialog):
    """Dialog for Print Directory options"""
    
    def __init__(self, current_path, parent=None):
        super().__init__(parent)
        self.current_path = current_path
        self.setWindowTitle("Print Directory to Excel")
        self.setModal(True)
        self.resize(550, 220)
        
        layout = QVBoxLayout(self)
        
        # Current path
        path_label = QLabel(f"<b>Directory:</b> {current_path}")
        path_label.setWordWrap(True)
        path_label.setStyleSheet("padding: 10px; background-color: #f0f0f0; border-radius: 5px;")
        layout.addWidget(path_label)
        
        layout.addSpacing(15)
        
        # Options
        options_label = QLabel("<b>Export Options:</b>")
        layout.addWidget(options_label)
        
        # Include subdirectories checkbox
        self.include_subdirs_cb = QCheckBox("Include all subdirectories and files (recursive)")
        # Default OFF: recursive exports can be extremely large/slow on network paths
        self.include_subdirs_cb.setChecked(False)
        layout.addWidget(self.include_subdirs_cb)
        
        info_label = QLabel("📝 The directory listing will open directly in Excel as an unsaved workbook.")
        info_label.setStyleSheet("color: #666; font-size: 9pt; padding-left: 20px;")
        layout.addWidget(info_label)
        
        layout.addSpacing(10)
        
        note_label = QLabel("💡 Use 'Save As' in Excel if you want to keep the file.")
        note_label.setStyleSheet("color: #0066cc; font-size: 9pt; padding-left: 20px;")
        layout.addWidget(note_label)
        
        layout.addStretch()
        
        # Buttons
        button_box = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        button_box.accepted.connect(self.accept)
        button_box.rejected.connect(self.reject)
        layout.addWidget(button_box)
    
    def get_options(self):
        """Return selected options"""
        return {
            'include_subdirs': self.include_subdirs_cb.isChecked()
        }
