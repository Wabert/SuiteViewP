"""File Explorer File Ops."""
from __future__ import annotations

import logging
import os
import shutil
import subprocess
from pathlib import Path
from urllib.parse import quote

try:
    import winreg
except ImportError:  # pragma: no cover - non-Windows development host
    winreg = None





from PyQt6.QtCore import (
    QMimeData,
    Qt,
    QTimer,
    QUrl,
)
from PyQt6.QtWidgets import (
    QApplication,
    QInputDialog,
    QLineEdit,
    QMessageBox,
)

from suiteview.core.support_files import guard_support_file_paths
from suiteview.file_nav.sharepoint_client import (
    is_sp_path,
)

logger = logging.getLogger(__name__)


class FileExplorerFileOpsMixin:
    """Requires: details selection, clipboard state, and support-file guards.
    Provides: copy, cut, paste, rename, delete, mkdir, drops, and refresh hooks.
    """

    def get_selected_path(self):
        """Get currently selected file/folder path from details view (single selection)"""
        indexes = self.details_view.selectedIndexes()
        if not indexes:
            return None
        
        # Get the data directly from the proxy model
        path = self.details_sort_proxy.data(indexes[0], Qt.ItemDataRole.UserRole)
        
        # If this column doesn't have the path data, get it from column 0 of the same row
        if not path:
            col0_index = indexes[0].sibling(indexes[0].row(), 0)
            path = self.details_sort_proxy.data(col0_index, Qt.ItemDataRole.UserRole)
        
        return path

    def get_selected_paths(self):
        """Get all selected file/folder paths from details view (multi-selection)"""
        selected_rows = {}
        paths = []
        
        # Get unique rows (since selecting a row selects all columns)
        for index in self.details_view.selectedIndexes():
            row = index.row()
            
            if row not in selected_rows:
                selected_rows[row] = True
                # Get column 0 index for this row and query the proxy model
                col0_index = index.sibling(row, 0)
                path = self.details_sort_proxy.data(col0_index, Qt.ItemDataRole.UserRole)
                if path:
                    paths.append(path)
        
        return paths

    def cut_file(self):
        """Cut selected file(s)/folder(s)"""
        paths = self.get_selected_paths()
        if paths:
            self.clipboard = {"paths": paths, "operation": "cut"}
            # Also set system clipboard so files can be pasted in Windows Explorer
            self._set_system_clipboard(paths)
            logger.info(f"Cut: {len(paths)} item(s)")

    def copy_file(self):
        """Copy selected file(s)/folder(s)"""
        paths = self.get_selected_paths()
        if paths:
            self.clipboard = {"paths": paths, "operation": "copy"}
            # Also set system clipboard so files can be pasted in Windows Explorer
            self._set_system_clipboard(paths)
            logger.info(f"Copy: {len(paths)} item(s)")

    def copy_full_path_to_clipboard(self, path):
        """Copy the full path of a file or folder to clipboard as text"""
        clipboard = QApplication.clipboard()
        clipboard.setText(str(path))
        logger.info(f"Copied path to clipboard: {path}")

    def get_onedrive_url(self, local_path):
        """Get the OneDrive/SharePoint URL for a local OneDrive-synced file.
        
        Reads mount-point → URL mappings from the Windows registry
        (HKCU\\Software\\SyncEngines\\Providers\\OneDrive).
        Returns the URL string, or None if the file is not under a known mount.
        """
        try:

            local_path = str(Path(local_path).resolve())
            best_mount = None
            best_url = None

            key_path = r"Software\SyncEngines\Providers\OneDrive"
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, key_path) as providers:
                i = 0
                while True:
                    try:
                        subkey_name = winreg.EnumKey(providers, i)
                        i += 1
                    except OSError:
                        break
                    try:
                        with winreg.OpenKey(providers, subkey_name) as sub:
                            mount_point, _ = winreg.QueryValueEx(sub, "MountPoint")
                            url_namespace, _ = winreg.QueryValueEx(sub, "UrlNamespace")
                    except OSError:
                        continue

                    mount_point = str(Path(mount_point).resolve())
                    # Pick the longest matching mount point
                    if local_path.lower().startswith(mount_point.lower()):
                        if best_mount is None or len(mount_point) > len(best_mount):
                            best_mount = mount_point
                            best_url = url_namespace

            if best_mount and best_url:
                relative = local_path[len(best_mount):].replace("\\", "/")
                # URL-encode path segments but keep slashes
                parts = relative.split("/")
                encoded = "/".join(quote(p) for p in parts)
                url = best_url.rstrip("/") + encoded
                return url
        except (AttributeError, OSError, TypeError, ValueError):
            logger.debug("Failed to resolve OneDrive URL", exc_info=True)
        return None

    def copy_sharepoint_link(self, path):
        """Copy the SharePoint/OneDrive URL for a file to the clipboard."""
        url = self.get_onedrive_url(path)
        if url:
            clipboard = QApplication.clipboard()
            clipboard.setText(url)
            logger.info(f"Copied SharePoint link: {url}")
        else:
            QMessageBox.information(
                self, "SharePoint Link",
                "Could not determine the SharePoint URL for this file.\n"
                "It may not be in a synced OneDrive folder."
            )

    def open_folder_location_in_file_nav(self, path):
        """Navigate to the parent folder of the given path in File Nav"""
        path_obj = Path(path)
        parent_folder = path_obj.parent if path_obj.is_file() else path_obj
        
        # Check if this is a FileExplorerTab (has navigate_to_path for breadcrumb/history)
        # or just the base FileExplorerCore
        if hasattr(self, 'navigate_to_path'):
            # Use navigate_to_path to update breadcrumb and history
            self.navigate_to_path(str(parent_folder), add_to_history=True)
        else:
            # Fall back to direct loading (base FileExplorerCore)
            self.load_folder_contents_in_details(parent_folder)
        
        # If this is a file, select it in the details view after loading
        if path_obj.is_file():
            # Small delay to ensure the model is populated
            # QTimer already imported at module level
            QTimer.singleShot(100, lambda: self.select_file_in_details(path))
        
        logger.info(f"Navigated to folder location: {parent_folder}")

    def _set_system_clipboard(self, paths):
        """Set file paths to the system clipboard for use with Windows Explorer"""
        clipboard = QApplication.clipboard()
        mime_data = QMimeData()
        
        # Convert paths to QUrl list
        urls = [QUrl.fromLocalFile(path) for path in paths]
        mime_data.setUrls(urls)
        
        clipboard.setMimeData(mime_data)

    def get_clipboard_files(self):
        """Get list of file paths from Windows clipboard"""
        clipboard = QApplication.clipboard()
        mime_data = clipboard.mimeData()
        
        files = []
        if mime_data.hasUrls():
            for url in mime_data.urls():
                if url.isLocalFile():
                    file_path = url.toLocalFile()
                    if os.path.exists(file_path):
                        files.append(file_path)
        
        return files

    def has_clipboard_content(self):
        """Check if there's pasteable content in clipboard (internal or Windows)"""
        # Check internal clipboard
        if self.clipboard.get("paths"):
            return True
        # Check Windows clipboard for files
        return len(self.get_clipboard_files()) > 0

    def _paste_destination_path(self) -> str | None:
        dest_path = self.get_selected_path()
        if dest_path and os.path.isfile(dest_path):
            dest_path = str(Path(dest_path).parent)
        if dest_path and os.path.isdir(dest_path):
            return dest_path
        if hasattr(self, 'current_details_folder') and self.current_details_folder:
            return self.current_details_folder
        QMessageBox.warning(self, "Paste", "No destination folder available")
        return None

    def _paste_one_source(self, source: Path, dest_path: str, operation: str | None) -> None:
        dest = Path(dest_path) / source.name
        if dest.exists():
            dest = self._get_unique_dest_path(dest)
        if operation == "cut":
            guard_support_file_paths(source, dest, action="move policy support files or folders")
            shutil.move(str(source), str(dest))
            return
        guard_support_file_paths(dest, action="copy policy support files or folders")
        if source.is_dir():
            shutil.copytree(str(source), str(dest))
        else:
            shutil.copy2(str(source), str(dest))

    def _paste_sources(self, sources: list[str], dest_path: str, operation: str | None) -> tuple[int, list[str]]:
        success_count = 0
        errors = []
        for source_path in sources:
            source = Path(source_path)
            try:
                FileExplorerFileOpsMixin._paste_one_source(self, source, dest_path, operation)
                success_count += 1
                logger.info(f"Pasted {source.name} to {dest_path}")
            except Exception as e:
                errors.append(f"{source.name}: {e}")
                logger.error(f"Failed to paste {source.name}: {e}")
        return success_count, errors

    def _refresh_current_details_folder(self) -> None:
        if hasattr(self, 'current_details_folder') and self.current_details_folder:
            self.load_folder_contents_in_details(Path(self.current_details_folder))

    def _warn_transfer_errors(self, title: str, verb: str, success_count: int, errors: list[str]) -> None:
        if errors:
            QMessageBox.warning(
                self, title,
                f"{verb} {success_count} item(s).\n{len(errors)} item(s) failed.\n"
                + "\n".join(errors[:5])
            )

    def paste_file(self):
        """Paste cut/copied file/folder from internal clipboard or Windows clipboard"""
        if is_sp_path(self.current_details_folder):
            QMessageBox.information(self, "Read-Only",
                "SharePoint libraries are read-only in FileNav.\n"
                "Use 'Open in Browser' to make changes in SharePoint.")
            return

        dest_path = FileExplorerFileOpsMixin._paste_destination_path(self)
        if not dest_path:
            return

        if self.clipboard.get("paths"):
            operation = self.clipboard["operation"]
            success_count, errors = FileExplorerFileOpsMixin._paste_sources(
                self, self.clipboard["paths"], dest_path, operation)
            if operation == "cut":
                self.clipboard = {"paths": [], "operation": None}
            FileExplorerFileOpsMixin._refresh_current_details_folder(self)
            FileExplorerFileOpsMixin._warn_transfer_errors(
                self, "Paste Results", "Pasted", success_count, errors)
            return

        clipboard_files = self.get_clipboard_files()
        if clipboard_files:
            success_count, errors = FileExplorerFileOpsMixin._paste_sources(
                self, clipboard_files, dest_path, "copy")
            FileExplorerFileOpsMixin._refresh_current_details_folder(self)
            FileExplorerFileOpsMixin._warn_transfer_errors(
                self, "Paste Results", "Pasted", success_count, errors)
            return

        QMessageBox.information(self, "Paste", "No files in clipboard to paste")

    def _get_unique_dest_path(self, dest: Path) -> Path:
        """Get a unique destination path by adding (1), (2), etc. if file exists"""
        if not dest.exists():
            return dest
        
        base = dest.stem
        ext = dest.suffix
        parent = dest.parent
        counter = 1
        
        while True:
            new_name = f"{base} ({counter}){ext}"
            new_dest = parent / new_name
            if not new_dest.exists():
                return new_dest
            counter += 1

    @staticmethod
    def _all_sources_from_destination(file_paths: list, dest_folder: str) -> bool:
        return all(str(Path(file_path).parent) == dest_folder for file_path in file_paths)

    @staticmethod
    def _split_drop_sources(file_paths: list) -> tuple[list[Path], list[Path]]:
        folders_to_move = []
        files_to_copy = []
        for file_path in file_paths:
            source = Path(file_path)
            if source.is_dir():
                folders_to_move.append(source)
            else:
                files_to_copy.append(source)
        return folders_to_move, files_to_copy

    def _confirm_folder_drop(self, folders_to_move: list[Path], dest_folder: str) -> bool:
        if not folders_to_move:
            return True
        dest_name = Path(dest_folder).name
        if len(folders_to_move) == 1:
            folder_name = folders_to_move[0].name
            confirm_msg = f"Move folder '{folder_name}' into '{dest_name}'?"
        else:
            folder_names = ", ".join([f.name for f in folders_to_move[:3]])
            if len(folders_to_move) > 3:
                folder_names += f", ... ({len(folders_to_move)} folders total)"
            confirm_msg = f"Move folders {folder_names} into '{dest_name}'?"

        reply = QMessageBox.question(
            self, "Confirm Folder Move",
            confirm_msg,
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        if reply != QMessageBox.StandardButton.Yes:
            logger.info("User cancelled folder move operation")
            return False
        return True

    def _copy_drop_sources(self, file_paths: list, dest_folder: str) -> tuple[int, list[str]]:
        success_count = 0
        errors = []
        for file_path in file_paths:
            source = Path(file_path)
            if str(source.parent) == dest_folder:
                logger.info(f"Skipping {source.name} - already in destination folder")
                continue
            dest = Path(dest_folder) / source.name
            try:
                if dest.exists():
                    dest = self._get_unique_dest_path(dest)
                guard_support_file_paths(dest, action="copy policy support files or folders")
                if source.is_dir():
                    shutil.copytree(str(source), str(dest))
                else:
                    shutil.copy2(str(source), str(dest))
                success_count += 1
                logger.info(f"Copied {source.name} to {dest_folder}")
            except Exception as e:
                errors.append(f"{source.name}: {e}")
                logger.error(f"Failed to copy {source.name}: {e}")
        return success_count, errors

    def handle_dropped_files(self, file_paths: list, dest_folder: str):
        """Handle files dropped from external sources (Windows Explorer, desktop, etc.)"""
        if not file_paths or not dest_folder:
            return

        if FileExplorerFileOpsMixin._all_sources_from_destination(file_paths, dest_folder):
            logger.info(f"Ignored drop operation - files dropped in same folder")
            return

        folders_to_move, _files_to_copy = FileExplorerFileOpsMixin._split_drop_sources(file_paths)
        if not FileExplorerFileOpsMixin._confirm_folder_drop(self, folders_to_move, dest_folder):
            return

        success_count, errors = FileExplorerFileOpsMixin._copy_drop_sources(self, file_paths, dest_folder)
        FileExplorerFileOpsMixin._refresh_current_details_folder(self)
        if errors:
            QMessageBox.warning(
                self, "Copy Results", 
                f"Copied {success_count} file(s).\n{len(errors)} file(s) failed.\n"
                + "\n".join(errors[:5])
            )
        elif success_count > 1:
            logger.info(f"Successfully copied {success_count} files to {dest_folder}")

    def rename_file(self):
        """Rename selected file/folder"""
        path = self.get_selected_path()
        if not path:
            return
        
        old_path = Path(path)
        new_name, ok = QInputDialog.getText(
            self, "Rename", f"Rename '{old_path.name}' to:",
            text=old_path.name
        )
        
        if ok and new_name:
            try:
                new_path = old_path.parent / new_name
                guard_support_file_paths(
                    old_path, new_path, action="rename policy support files or folders"
                )
                old_path.rename(new_path)
                self.refresh_tree()
                QMessageBox.information(self, "Success", f"Renamed to {new_name}")
            except Exception as e:
                QMessageBox.critical(self, "Error", f"Rename failed: {e}")

    def delete_file(self):
        """Delete selected file(s)/folder(s)"""
        paths = self.get_selected_paths()
        if not paths:
            return
        
        # Build confirmation message
        if len(paths) == 1:
            message = f"Delete '{Path(paths[0]).name}'?"
        else:
            message = f"Delete {len(paths)} selected items?"
        
        reply = QMessageBox.question(
            self, "Confirm Delete",
            message,
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        
        if reply == QMessageBox.StandardButton.Yes:
            deleted_count = 0
            error_count = 0
            errors = []
            
            for path in paths:
                try:
                    path_obj = Path(path)
                    guard_support_file_paths(path_obj, action="delete policy support files or folders")
                    if path_obj.is_dir():
                        shutil.rmtree(path)
                    else:
                        path_obj.unlink()
                    deleted_count += 1
                    logger.info(f"Deleted: {path}")
                except Exception as e:
                    error_count += 1
                    errors.append(f"{Path(path).name}: {e}")
                    logger.error(f"Failed to delete {path}: {e}")
            
            # Refresh the details view to show files are gone
            if hasattr(self, 'current_details_folder') and self.current_details_folder:
                self.load_folder_contents_in_details(Path(self.current_details_folder))
            
            if error_count > 0:
                QMessageBox.warning(
                    self, "Delete Results",
                    f"Deleted {deleted_count} item(s).\n{error_count} item(s) failed.\n"
                    + "\n".join(errors[:5])
                )

    def refresh_details_view(self):
        """Refresh the current folder contents in the details view"""
        if self.current_details_folder:
            if is_sp_path(self.current_details_folder):
                self.load_sharepoint_contents_in_details(
                    self.current_details_folder, self._sp_current_name)
            else:
                self.load_folder_contents_in_details(Path(self.current_details_folder))
        else:
            logger.warning("No current folder to refresh")

    def create_new_folder(self):
        """Create a new folder in the current directory"""
        if not self.current_details_folder:
            QMessageBox.warning(self, "Error", "No folder selected")
            return
        
        if is_sp_path(self.current_details_folder):
            QMessageBox.information(self, "Read-Only",
                "SharePoint libraries are read-only in FileNav.\n"
                "Use 'Open in Browser' to make changes in SharePoint.")
            return
        
        # Prompt for folder name
        folder_name, ok = QInputDialog.getText(
            self, "New Folder", 
            "Enter folder name:",
            QLineEdit.EchoMode.Normal,
            "New Folder"
        )
        
        if ok and folder_name:
            try:
                new_folder_path = Path(self.current_details_folder) / folder_name
                guard_support_file_paths(new_folder_path, action="create policy support folders")
                new_folder_path.mkdir(parents=False, exist_ok=False)
                logger.info(f"Created folder: {new_folder_path}")
                
                # Refresh the details view to show the new folder
                self.load_folder_contents_in_details(Path(self.current_details_folder))
                
                QMessageBox.information(self, "Success", f"Folder '{folder_name}' created successfully")
            except FileExistsError:
                QMessageBox.warning(self, "Error", f"Folder '{folder_name}' already exists")
            except Exception as e:
                logger.error(f"Failed to create folder: {e}")
                QMessageBox.warning(self, "Error", f"Failed to create folder:\n{str(e)}")

    def open_in_explorer(self):
        """Open current folder or selected path in Windows Explorer"""
        path = self.get_selected_path()
        
        # If no selection, use current details folder
        if not path and hasattr(self, 'current_details_folder') and self.current_details_folder:
            path = self.current_details_folder
        
        if not path:
            return
        
        try:
            path_obj = Path(path)
            # Use parent for files. If is_file() fails (long path / cloud-only OneDrive),
            # check if it has a file extension as a heuristic
            if path_obj.is_file() or (path_obj.suffix and not path_obj.is_dir()):
                folder_path = str(path_obj.parent)
            else:
                folder_path = str(path_obj)
            
            if os.name == 'nt':
                subprocess.run(['explorer', folder_path])
            else:
                subprocess.run(['xdg-open', folder_path])
        except Exception as e:
            logger.error(f"Failed to open explorer: {e}")
            # Fallback: try opening the current details folder
            if hasattr(self, 'current_details_folder') and self.current_details_folder:
                try:
                    subprocess.run(['explorer', self.current_details_folder])
                except Exception:
                    logger.debug("Suppressed File Explorer exception", exc_info=True)
