"""File Explorer Context Menus."""
from __future__ import annotations

import logging
from pathlib import Path

from PyQt6.QtCore import (
    Qt,
    QUrl,
)
from PyQt6.QtGui import (
    QDesktopServices,
)
from PyQt6.QtWidgets import (
    QDialog,
    QMenu,
    QMessageBox,
)

from suiteview.file_nav.sharepoint_client import (
    is_sp_path,
)
from suiteview.ui.dialogs.batch_rename_dialog import BatchRenameDialog
from suiteview.ui.dialogs.mainframe_upload_dialog import MainframeUploadDialog

logger = logging.getLogger(__name__)


class FileExplorerContextMenuMixin:
    def show_tree_context_menu(self, position):
        """Show context menu for tree view"""
        index = self.tree_view.indexAt(position)
        if not index.isValid():
            # Blank area - offer to add a SharePoint library
            menu = QMenu()
            add_sp_action = menu.addAction("🌐 Add SharePoint Library…")
            add_sp_action.triggered.connect(self.add_sharepoint_library_dialog)
            discover_action = menu.addAction("🔍 Discover My Libraries…")
            discover_action.triggered.connect(self.discover_sharepoint_libraries_dialog)
            menu.exec(self.tree_view.viewport().mapToGlobal(position))
            return
        
        item = self.model.itemFromIndex(index)
        if not item:
            return
        
        path = item.data(Qt.ItemDataRole.UserRole)
        if not path:
            return
        
        # Also verify it's a top-level item (no parent except model root)
        is_top_level = item.parent() is None
        
        # SharePoint items get their own menu (no filesystem operations)
        if is_sp_path(path):
            menu = QMenu()
            web_url = item.data(Qt.ItemDataRole.UserRole + 4)
            if web_url:
                browser_action = menu.addAction("🌐 Open in Browser")
                browser_action.triggered.connect(lambda: QDesktopServices.openUrl(QUrl(web_url)))
            refresh_action = menu.addAction("🔄 Refresh")
            refresh_action.triggered.connect(lambda: self._refresh_sp_tree_item(item))
            if item.data(Qt.ItemDataRole.UserRole + 2) == "__SHAREPOINT__" and is_top_level:
                menu.addSeparator()
                remove_action = menu.addAction("🗑️ Remove SharePoint Library")
                remove_action.triggered.connect(lambda: self.remove_sharepoint_library(path))
            menu.addSeparator()
            add_sp_action = menu.addAction("🌐 Add SharePoint Library…")
            add_sp_action.triggered.connect(self.add_sharepoint_library_dialog)
            discover_action = menu.addAction("🔍 Discover My Libraries…")
            discover_action.triggered.connect(self.discover_sharepoint_libraries_dialog)
            menu.exec(self.tree_view.viewport().mapToGlobal(position))
            return
        
        # Check if this is a custom quick link (only top-level items in Quick Links)
        is_custom_link = item.data(Qt.ItemDataRole.UserRole + 1) == "__CUSTOM_LINK__"
        
        # Check if this is a pinned folder
        is_pinned = item.data(Qt.ItemDataRole.UserRole + 2) == "__PINNED__"
        
        menu = QMenu()
        
        # Open in Explorer
        open_explorer_action = menu.addAction("📂 Open in File Explorer")
        open_explorer_action.triggered.connect(lambda: self.open_path_in_explorer(path))
        
        # Remove from Sidebar Bookmarks (only for top-level custom links)
        if is_custom_link and is_top_level:
            menu.addSeparator()
            remove_action = menu.addAction("📌 Remove from Sidebar Bookmarks")
            remove_action.triggered.connect(lambda: self.remove_quick_link_by_path(path))
        
        # Unpin option for pinned folders
        if is_pinned and is_top_level:
            menu.addSeparator()
            unpin_action = menu.addAction("📌 Unpin from Folders")
            unpin_action.triggered.connect(lambda: self.unpin_folder_from_tree(path))
        
        # Add SharePoint library (always available)
        menu.addSeparator()
        add_sp_action = menu.addAction("🌐 Add SharePoint Library…")
        add_sp_action.triggered.connect(self.add_sharepoint_library_dialog)
        discover_action = menu.addAction("🔍 Discover My Libraries…")
        discover_action.triggered.connect(self.discover_sharepoint_libraries_dialog)
        
        # Show menu
        menu.exec(self.tree_view.viewport().mapToGlobal(position))

    def show_details_context_menu(self, position):
        """Show context menu for details view"""
        index = self.details_view.indexAt(position)
        
        # SharePoint items get a dedicated read-only menu
        if is_sp_path(self.current_details_folder):
            self.show_sp_details_context_menu(position, index)
            return
        
        menu = QMenu()
        
        # Add "New Folder" option at the top (always available when in a folder)
        if self.current_details_folder:
            new_folder_action = menu.addAction("📁 New Folder")
            new_folder_action.triggered.connect(self.create_new_folder)
            menu.addSeparator()
        
        if index.isValid():
            # Get the data directly from the proxy model at the clicked index
            path = self.details_sort_proxy.data(index, Qt.ItemDataRole.UserRole)
            
            # If this column doesn't have the path data, get it from column 0 of the same row
            if not path:
                col0_index = index.sibling(index.row(), 0)
                path = self.details_sort_proxy.data(col0_index, Qt.ItemDataRole.UserRole)
            
            if path:
                    path_obj = Path(path)
                    
                    # Copy Full Path
                    copy_path_action = menu.addAction("📄 Copy Full Path")
                    copy_path_action.triggered.connect(lambda: self.copy_full_path_to_clipboard(path))
                    
                    # Copy SharePoint Link (only if file is under a OneDrive mount)
                    onedrive_url = self.get_onedrive_url(path)
                    if onedrive_url:
                        copy_link_action = menu.addAction("🔗 Copy SharePoint Link")
                        copy_link_action.triggered.connect(lambda: self.copy_sharepoint_link(path))
                    
                    # Open folder location (navigate to parent folder in File Nav)
                    open_folder_action = menu.addAction("📂 Open Folder Location")
                    open_folder_action.triggered.connect(lambda: self.open_folder_location_in_file_nav(path))
                    
                    menu.addSeparator()
                    
                    # Cut, Copy operations
                    cut_action = menu.addAction("✂️ Cut")
                    cut_action.triggered.connect(self.cut_file)
                    
                    copy_action = menu.addAction("📋 Copy")
                    copy_action.triggered.connect(self.copy_file)
                    
                    # Rename, Delete
                    rename_action = menu.addAction("✏️ Rename")
                    rename_action.triggered.connect(self.rename_file)
                    
                    delete_action = menu.addAction("🗑️ Delete")
                    delete_action.triggered.connect(self.delete_file)
        
        # Paste (always available if clipboard has content - internal or Windows)
        if self.has_clipboard_content():
            if index.isValid():
                menu.addSeparator()
            paste_action = menu.addAction("📌 Paste")
            paste_action.triggered.connect(self.paste_file)
        elif self.current_details_folder:
            # Show disabled paste option when in a folder but no clipboard content
            if index.isValid():
                menu.addSeparator()
            paste_action = menu.addAction("📌 Paste")
            paste_action.setEnabled(False)
        
        # Show menu
        menu.exec(self.details_view.viewport().mapToGlobal(position))

    def show_context_menu(self, position):
        """Show context menu with quick link options"""
        menu = QMenu()
        
        # Check if item is a custom quick link
        indexes = self.tree_view.selectedIndexes()
        is_custom_link = False
        selected_path = None
        
        if indexes:
            item = self.model.itemFromIndex(self.model.index(indexes[0].row(), 0, indexes[0].parent()))
            if item:
                if item.data(Qt.ItemDataRole.UserRole + 1) == "__CUSTOM_LINK__":
                    is_custom_link = True
                selected_path = item.data(Qt.ItemDataRole.UserRole)
        
        # Remove from Sidebar Bookmarks (only for custom links)
        if is_custom_link:
            remove_from_quick = menu.addAction("❌ Remove from Sidebar Bookmarks")
        else:
            remove_from_quick = None
        
        explorer_action = menu.addAction("📂 Open in Explorer")
        
        menu.addSeparator()
        
        # File operations at the bottom
        cut_action = menu.addAction("✂️ Cut")
        copy_action = menu.addAction("📋 Copy")
        rename_action = menu.addAction("✏️ Rename")
        delete_action = menu.addAction("🗑️ Delete")
        
        menu.addSeparator()
        paste_action = menu.addAction("📌 Paste")
        
        action = menu.exec(self.tree_view.viewport().mapToGlobal(position))
        
        if action == cut_action:
            self.cut_file()
        elif action == copy_action:
            self.copy_file()
        elif action == paste_action:
            self.paste_file()
        elif action == rename_action:
            self.rename_file()
        elif action == delete_action:
            self.delete_file()
        elif action == remove_from_quick:
            self.remove_from_quick_access()
        elif action == explorer_action:
            self.open_in_explorer()

    def upload_to_mainframe(self):
        """Upload selected file to mainframe"""
        path = self.get_selected_path()
        if not path:
            return
        
        path_obj = Path(path)
        if not path_obj.is_file():
            QMessageBox.warning(self, "Invalid Selection", "Please select a file to upload")
            return
        
        try:
            
            dialog = MainframeUploadDialog(str(path_obj), self)
            if dialog.exec() == QDialog.DialogCode.Accepted:
                dialog.perform_upload()
                
        except Exception as e:
            logger.error(f"Failed to show upload dialog: {e}")
            QMessageBox.critical(
                self,
                "Error",
                f"Failed to open upload dialog:\n{str(e)}"
            )

    def batch_rename_files(self):
        """Batch rename multiple selected files"""
        paths = self.get_selected_paths()
        
        if not paths:
            QMessageBox.information(
                self,
                "No Selection",
                "Please select one or more files to rename.\n\n"
                "💡 Tip: Hold Ctrl and click to select multiple files"
            )
            return
        
        # Filter out folders (only rename files in batch)
        file_paths = [p for p in paths if Path(p).is_file()]
        
        if not file_paths:
            QMessageBox.warning(
                self,
                "No Files Selected",
                "Please select files (not folders) to batch rename."
            )
            return
        
        try:
            
            dialog = BatchRenameDialog(file_paths, self)
            if dialog.exec():
                if dialog.perform_rename():
                    self.refresh_tree()
                    self.refresh_details_view()
                    
        except Exception as e:
            logger.error(f"Failed to show batch rename dialog: {e}")
            QMessageBox.critical(
                self,
                "Error",
                f"Failed to open batch rename dialog:\n{str(e)}"
            )

