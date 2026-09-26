"""File Explorer Details Io."""
from __future__ import annotations

import logging
import os
import re
import subprocess
import sys
import time
from pathlib import Path

try:
    import openpyxl
    from openpyxl.styles import Font, PatternFill
except ImportError:  # pragma: no cover - optional Excel export dependency
    openpyxl = None
    Font = None
    PatternFill = None

try:
    import pandas as pd
except ImportError:  # pragma: no cover - optional preview dependency
    pd = None

try:
    from PIL import Image
except ImportError:  # pragma: no cover - optional image preview dependency
    Image = None

try:
    import win32com.client
    from win32com.client import dynamic as win32com_dynamic
except ImportError:  # pragma: no cover - optional Windows COM automation
    win32com = None
    win32com_dynamic = None

from PyQt6.QtCore import (
    QRegularExpression,
    Qt,
)
from PyQt6.QtGui import (
    QStandardItem,
)
from PyQt6.QtWidgets import (
    QMessageBox,
)

from suiteview.core.support_files import guard_support_file_paths
from suiteview.file_nav.sharepoint_client import (
    is_sp_path,
)

logger = logging.getLogger(__name__)


class FileExplorerDetailsIOMixin:
    def on_item_renamed(self, item):
        """Handle item rename after F2 edit"""
        # Disconnect temporarily to avoid recursive calls
        self.details_model.itemChanged.disconnect(self.on_item_renamed)
        
        try:
            # Get the old path from UserRole
            old_path = item.data(Qt.ItemDataRole.UserRole)
            if not old_path:
                return
            
            old_path_obj = Path(old_path)
            
            # Extract new name from the item text (remove icon emoji)
            new_text = item.text()
            # Remove emoji icons (they're at the start)
            new_name = re.sub(r'^[\U0001F300-\U0001F9FF]\s*', '', new_text).strip()
            
            # Validate new name
            if not new_name or new_name == old_path_obj.name:
                # No change or empty name, revert
                icon = item.text().split()[0] if ' ' in item.text() else ""
                item.setText(f"{icon} {old_path_obj.name}" if icon else old_path_obj.name)
                return
            
            # Check for invalid characters
            invalid_chars = r'<>:"/\|?*'
            if any(c in new_name for c in invalid_chars):
                QMessageBox.warning(
                    self, 
                    "Invalid Name", 
                    f"The name cannot contain any of the following characters:\n{invalid_chars}"
                )
                # Revert name
                icon = item.text().split()[0] if ' ' in item.text() else ""
                item.setText(f"{icon} {old_path_obj.name}" if icon else old_path_obj.name)
                return
            
            # Build new path
            new_path_obj = old_path_obj.parent / new_name
            
            # Check if target already exists
            if new_path_obj.exists():
                QMessageBox.warning(
                    self,
                    "Name Conflict",
                    f"A file or folder with the name '{new_name}' already exists."
                )
                # Revert name
                icon = item.text().split()[0] if ' ' in item.text() else ""
                item.setText(f"{icon} {old_path_obj.name}" if icon else old_path_obj.name)
                return
            
            # Perform the rename
            try:
                guard_support_file_paths(
                    old_path_obj, new_path_obj, action="rename policy support files or folders"
                )
                old_path_obj.rename(new_path_obj)
                
                # Update the item's UserRole data with new path
                item.setData(str(new_path_obj), Qt.ItemDataRole.UserRole)
                
                # Update sort data
                is_folder = new_path_obj.is_dir()
                prefix = "0_" if is_folder else "1_"
                item.setData(f"{prefix}{new_name.lower()}", Qt.ItemDataRole.UserRole + 1)
                
                logger.info(f"Renamed: {old_path_obj} -> {new_path_obj}")
                
            except Exception as e:
                logger.error(f"Failed to rename: {e}")
                QMessageBox.critical(
                    self,
                    "Rename Failed",
                    f"Failed to rename '{old_path_obj.name}':\n{str(e)}"
                )
                # Revert name
                icon = item.text().split()[0] if ' ' in item.text() else ""
                item.setText(f"{icon} {old_path_obj.name}" if icon else old_path_obj.name)
                
        finally:
            # Reconnect signal
            self.details_model.itemChanged.connect(self.on_item_renamed)

    def load_folder_contents_in_details(self, dir_path):
        """Load folder contents into the details view - optimized for network drives"""
        # Check if we're returning to the depth search folder while locked
        if (self.depth_search_locked and 
            self.depth_search_folder and 
            str(dir_path) == self.depth_search_folder and
            self.depth_search_active_results):
            # Restore depth search results instead of loading normal contents
            self.current_details_folder = str(dir_path)
            self.details_view.set_current_folder(str(dir_path))
            self.details_header.setText(f"📂 {dir_path.name or str(dir_path)}")
            
            self._restore_details_search_term(dir_path)
            
            self._populate_depth_results(self.depth_search_active_results)
            return
        
        # Start timing and show loading indicator
        start_time = time.perf_counter()
        
        # Note: Removed QApplication.processEvents() here - it causes event loop recursion
        # and is a common source of UI stuttering. The loading indicator can be shown
        # via other means if needed.
        
        try:
            dir_path = Path(dir_path)
            
            # Store current folder for breadcrumb and other operations
            self.current_details_folder = str(dir_path)
            
            # Update the details view's current folder for drag/drop
            self.details_view.set_current_folder(str(dir_path))
            
            # Update header
            self.details_header.setText(f"📂 {dir_path.name or str(dir_path)}")
            
            self._restore_details_search_term(dir_path)
            self._reset_details_model_preserving_widths()
            
            # Check if it's a network path
            is_network = str(dir_path).startswith('\\\\')
            
            self._populate_details_items(self._scan_details_directory(dir_path))
            
            # Re-apply current sort order (default: Name ascending)
            header = self.details_view.header()
            sort_column = header.sortIndicatorSection()
            sort_order = header.sortIndicatorOrder()
            self.details_sort_proxy.sort(sort_column, sort_order)
            
            # Calculate elapsed time and update footer with timing
            elapsed_ms = int((time.perf_counter() - start_time) * 1000)
            self.update_details_footer(timing_ms=elapsed_ms)
                    
        except (PermissionError, OSError) as e:
            self._reset_details_model_preserving_widths()
            
            error_item = QStandardItem(f"❌ Access denied: {str(e)}")
            error_item.setEnabled(False)
            self.details_model.appendRow([error_item, QStandardItem(""), QStandardItem(""), QStandardItem(""), QStandardItem("")])
            
            # Update footer even on error
            elapsed_ms = int((time.perf_counter() - start_time) * 1000)
            self.update_details_footer(timing_ms=elapsed_ms)

    def _restore_details_search_term(self, dir_path):
        """Restore the folder-specific details search text and filter."""
        if not hasattr(self, 'details_search') or not hasattr(self, 'folder_search_terms'):
            return
        saved_search = self.folder_search_terms.get(str(dir_path), "")
        self.details_search.blockSignals(True)
        self.details_search.setText(saved_search)
        self.details_search.blockSignals(False)
        if saved_search:
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
            escaped = QRegularExpression.escape(saved_search)
            regex = QRegularExpression(escaped, QRegularExpression.PatternOption.CaseInsensitiveOption)
            self.details_sort_proxy.setFilterRegularExpression(regex)
            return
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
        self.details_sort_proxy.setFilterRegularExpression(QRegularExpression())

    def _reset_details_model_preserving_widths(self):
        self.details_model.clear()
        self.details_model.setHorizontalHeaderLabels(['Name', 'Size', 'Type', 'Date Modified', 'Date Accessed'])
        header_view = self.details_view.header()
        try:
            header_view.sectionResized.disconnect(self.on_column_resized)
        except (RuntimeError, TypeError):
            logger.debug("Details column resize signal was not connected", exc_info=True)
        default_widths = [350, 100, 120, 150, 150]
        for col, default_width in enumerate(default_widths):
            width = self.column_widths.get(f'col_{col}', default_width)
            self.details_view.setColumnWidth(col, width)
        header_view.sectionResized.connect(self.on_column_resized)

    def _scan_details_directory(self, dir_path):
        items_with_type = []
        try:
            with os.scandir(str(dir_path)) as entries:
                for entry in entries:
                    try:
                        is_directory = entry.is_dir()
                        items_with_type.append((Path(entry.path), is_directory, entry))
                    except (PermissionError, OSError):
                        continue
            items_with_type.sort(key=lambda x: (not x[1], x[0].name.lower()))
        except OSError:
            logger.debug("Could not scan details directory", exc_info=True)
        return items_with_type

    def _populate_details_items(self, items_with_type):
        self.details_view.setUpdatesEnabled(False)
        try:
            for item_path, is_directory, dir_entry in items_with_type:
                try:
                    row_items = (
                        self.create_folder_item(item_path, dir_entry=dir_entry)
                        if is_directory
                        else self.create_file_item(item_path, dir_entry=dir_entry)
                    )
                    self.details_model.appendRow(row_items)
                except (PermissionError, OSError):
                    continue
        finally:
            self.details_view.setUpdatesEnabled(True)

    def on_details_item_double_clicked(self, index):
        """Handle double click in details view"""
        # DEBUG: Log what we're clicking
        logger.debug(f"\n=== DOUBLE CLICK DEBUG ===")
        logger.debug(f"Proxy Index: row={index.row()}, col={index.column()}")
        logger.debug(f"Display text at clicked index: {self.details_sort_proxy.data(index, Qt.ItemDataRole.DisplayRole)}")
        
        # Get the data directly from the proxy model at the clicked index
        # The proxy model handles all the sorting/filtering, so we should query it directly
        path = self.details_sort_proxy.data(index, Qt.ItemDataRole.UserRole)
        
        # If this column doesn't have the path data, get it from column 0 of the same row
        if not path:
            col0_index = index.sibling(index.row(), 0)
            col0_text = self.details_sort_proxy.data(col0_index, Qt.ItemDataRole.DisplayRole)
            logger.debug(f"Column 0 text for this row: {col0_text}")
            path = self.details_sort_proxy.data(col0_index, Qt.ItemDataRole.UserRole)
        
        logger.debug(f"Path retrieved: {path}")
        logger.debug(f"=========================\n")
        
        if not path:
            return
        
        # SharePoint virtual items: navigate folders, download-and-open files
        if is_sp_path(path):
            col0_index = index.sibling(index.row(), 0)
            kind = self.details_sort_proxy.data(col0_index, Qt.ItemDataRole.UserRole + 3)
            name = (self.details_sort_proxy.data(col0_index, Qt.ItemDataRole.UserRole + 5)
                    or self.details_sort_proxy.data(col0_index, Qt.ItemDataRole.DisplayRole))
            if kind == "folder":
                self.load_sharepoint_contents_in_details(path, name)
            else:
                self.open_sharepoint_file(path, name)
            return
        
        path_obj = Path(path)
        
        # Handle .lnk shortcut files - resolve target and navigate if it's a folder
        if path_obj.suffix.lower() == '.lnk' and path_obj.is_file():
            target_path = self._resolve_shortcut(str(path_obj))
            if target_path:
                target_obj = Path(target_path)
                if target_obj.exists() and target_obj.is_dir():
                    # Navigate to the folder target within File Nav
                    # If depth search is active, turn it off first
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
                        # Re-enable tree panel
                        if hasattr(self, 'tree_view'):
                            self.tree_view.setEnabled(True)
                        # Restore normal toolbar color
                        self._apply_compact_toolbar_style(self.toolbar, locked=False)
                    
                    self.load_folder_contents_in_details(target_obj)
                    return
                elif target_obj.exists() and target_obj.is_file():
                    # Shortcut points to a file, open it
                    try:
                        if os.name == 'nt':
                            self._safe_startfile(str(target_obj))
                        elif sys.platform == 'darwin':
                            subprocess.run(['open', str(target_obj)])
                        else:
                            subprocess.run(['xdg-open', str(target_obj)])
                    except Exception as e:
                        logger.error(f"Failed to open file: {e}")
                        QMessageBox.warning(self, "Cannot Open File", f"Failed to open {target_obj.name}\n\nError: {str(e)}")
                    return
                # Target doesn't exist — show message in the details panel
                self.details_model.clear()
                self.details_model.setHorizontalHeaderLabels(
                    ['Name', 'Size', 'Type', 'Date Modified', 'Date Accessed'])
                msg_item = QStandardItem(f"File location not found: {target_path}")
                msg_item.setForeground(Qt.GlobalColor.red)
                msg_item.setEditable(False)
                self.details_model.appendRow([msg_item])
                return
            else:
                # Could not resolve shortcut target at all
                self.details_model.clear()
                self.details_model.setHorizontalHeaderLabels(
                    ['Name', 'Size', 'Type', 'Date Modified', 'Date Accessed'])
                msg_item = QStandardItem(f"File location not found: {path_obj}")
                msg_item.setForeground(Qt.GlobalColor.red)
                msg_item.setEditable(False)
                self.details_model.appendRow([msg_item])
                return
        
        is_dir = path_obj.is_dir()
        is_file = path_obj.is_file()
        
        if is_dir:
            # Navigate into folder - update tree selection and load in details
            self.load_folder_contents_in_details(path_obj)
            # TODO: Could also expand/select this folder in the tree view
        elif is_file or (not is_dir and not is_file):
            # Open file with default application
            # Note: we also try opening when both is_file and is_dir return False,
            # which happens with long paths (>260 chars) or cloud-only OneDrive files.
            # Windows os.startfile() handles these cases fine even when Python can't stat them.
            try:
                if os.name == 'nt':
                    self._safe_startfile(str(path_obj))
                elif sys.platform == 'darwin':
                    subprocess.run(['open', str(path_obj)])
                else:
                    subprocess.run(['xdg-open', str(path_obj)])
            except Exception as e:
                logger.error(f"Failed to open file: {e}")
                QMessageBox.warning(self, "Cannot Open File", f"Failed to open {path_obj.name}\n\nError: {str(e)}")

    def _resolve_shortcut(self, lnk_path):
        """Resolve a Windows .lnk shortcut file to get its target path"""
        try:
            shell = win32com.client.Dispatch("WScript.Shell")
            shortcut = shell.CreateShortCut(lnk_path)
            return shortcut.Targetpath
        except ImportError:
            # win32com not available, try alternative method
            try:
                # Use PowerShell as fallback
                result = subprocess.run(
                    ['powershell', '-Command', 
                     f"(New-Object -ComObject WScript.Shell).CreateShortcut('{lnk_path}').TargetPath"],
                    capture_output=True, text=True, timeout=5
                )
                if result.returncode == 0 and result.stdout.strip():
                    return result.stdout.strip()
            except Exception as e:
                logger.error(f"Failed to resolve shortcut via PowerShell: {e}")
        except Exception as e:
            logger.error(f"Failed to resolve shortcut: {e}")
        return None

    def open_file(self, path):
        """Open file with default application"""
        try:
            path_obj = Path(path)
            if os.name == 'nt':
                self._safe_startfile(str(path_obj))
            elif sys.platform == 'darwin':
                subprocess.run(['open', str(path_obj)])
            else:
                subprocess.run(['xdg-open', str(path_obj)])
        except OSError as e:
            logger.error(f"Failed to open file: {e}")
            # WinError 1223 typically means a .lnk shortcut target no longer exists
            if getattr(e, 'winerror', None) == 1223 or str(path_obj).lower().endswith('.lnk'):
                QMessageBox.warning(
                    self, "Shortcut Target Not Found",
                    f"The shortcut's target no longer exists:\n\n{path_obj.name}\n\n"
                    "The destination may have been renamed, moved, or deleted."
                )
            else:
                QMessageBox.warning(self, "Error", f"Failed to open file:\n{str(e)}")
        except Exception as e:
            logger.error(f"Failed to open file: {e}")
            QMessageBox.warning(self, "Error", f"Failed to open file:\n{str(e)}")

    def open_path_in_explorer(self, path):
        """Open path in system file explorer"""
        try:
            path_obj = Path(path)
            if os.name == 'nt':
                subprocess.run(['explorer', '/select,', str(path_obj)])
            elif sys.platform == 'darwin':
                subprocess.run(['open', '-R', str(path_obj)])
            else:
                subprocess.run(['xdg-open', str(path_obj.parent)])
        except Exception as e:
            logger.error(f"Failed to open in explorer: {e}")

    def get_current_details_folder(self):
        """Get the current folder being displayed in details view"""
        # This would need to track the current folder - for now return empty
        # You could store this as self.current_details_folder when loading
        return ""

    def show_file_preview(self, file_path):
        """Show enhanced file preview with support for Excel, CSV, images, etc."""
        self.current_file_path = file_path
        path = Path(file_path)
        suffix = path.suffix.lower()
        
        # Clear preview
        self.preview_text.clear()
        self.upload_button.setEnabled(True)
        
        try:
            # Check file size first
            file_size = path.stat().st_size
            if file_size > 10 * 1024 * 1024:  # 10 MB
                self.preview_text.setText(
                    f"📄 {path.name}\n"
                    f"Size: {file_size / (1024 * 1024):.2f} MB\n\n"
                    f"⚠️ File too large for preview\n"
                    f"Double-click to open in default application"
                )
                return
            
            # Excel files (.xlsx, .xls, .xlsm)
            if suffix in ['.xlsx', '.xls', '.xlsm']:
                self.preview_excel_file(path)
            
            # CSV files
            elif suffix == '.csv':
                self.preview_csv_file(path)
            
            # Text files
            elif suffix in ['.txt', '.log', '.md', '.py', '.js', '.html', '.css', '.json', '.xml', '.sql']:
                self.preview_text_file(path)
            
            # Image files
            elif suffix in ['.jpg', '.jpeg', '.png', '.gif', '.bmp']:
                self.preview_image_file(path)
            
            # PDF files
            elif suffix == '.pdf':
                self.preview_text.setText(
                    f"📕 PDF Document: {path.name}\n"
                    f"Size: {file_size / 1024:.1f} KB\n\n"
                    f"📌 Double-click to open in PDF viewer"
                )
            
            # Word documents
            elif suffix in ['.docx', '.doc']:
                self.preview_text.setText(
                    f"📝 Word Document: {path.name}\n"
                    f"Size: {file_size / 1024:.1f} KB\n\n"
                    f"📌 Double-click to open in Microsoft Word"
                )
            
            # PowerPoint
            elif suffix in ['.pptx', '.ppt']:
                self.preview_text.setText(
                    f"📽️ PowerPoint: {path.name}\n"
                    f"Size: {file_size / 1024:.1f} KB\n\n"
                    f"📌 Double-click to open in PowerPoint"
                )
            
            # Access databases
            elif suffix in ['.accdb', '.mdb']:
                self.preview_text.setText(
                    f"🗃️ Access Database: {path.name}\n"
                    f"Size: {file_size / 1024:.1f} KB\n\n"
                    f"📌 Double-click to open in Microsoft Access"
                )
            
            # Unknown/Binary
            else:
                self.preview_text.setText(
                    f"📃 {path.name}\n"
                    f"Type: {suffix.upper()[1:] if suffix else 'Unknown'}\n"
                    f"Size: {file_size / 1024:.1f} KB\n\n"
                    f"Preview not available for this file type\n"
                    f"Double-click to open"
                )
                
        except Exception as e:
            logger.error(f"Preview error: {e}")
            self.preview_text.setText(
                f"❌ Error previewing file:\n{str(e)}\n\n"
                f"File: {path.name}"
            )

    def preview_excel_file(self, path):
        """Preview Excel file showing first few rows"""
        try:
            
            # Read first sheet using openpyxl engine
            df = pd.read_excel(path, engine='openpyxl', nrows=100)
            
            # Build preview text
            preview = f"📊 Excel File: {path.name}\n"
            preview += f"Rows: {len(df)}, Columns: {len(df.columns)}\n"
            preview += "=" * 60 + "\n\n"
            
            # Column names
            preview += "Columns:\n"
            for i, col in enumerate(df.columns, 1):
                preview += f"  {i}. {col}\n"
            
            preview += "\n" + "=" * 60 + "\n"
            preview += "First 10 Rows:\n"
            preview += "=" * 60 + "\n\n"
            
            # Show first 10 rows with formatting
            preview += df.head(10).to_string(index=True, max_colwidth=40)
            
            if len(df) > 10:
                preview += f"\n\n... and {len(df) - 10} more rows"
            
            preview += "\n\n📌 Double-click to open in Excel"
            
            self.preview_text.setText(preview)
            self.current_file_content = preview
            
        except ImportError:
            self.preview_text.setText(
                f"📊 Excel File: {path.name}\n\n"
                f"⚠️ Could not preview Excel file:\n"
                f"Missing optional dependency 'xlrd'. Install xlrd >= 2.0.1 for xls Excel support\n"
                f"or use openpyxl for xlsx files.\n\n"
                f"Run: pip install openpyxl\n\n"
                f"Double-click to open in Microsoft Excel"
            )
        except Exception as e:
            self.preview_text.setText(
                f"📊 Excel File: {path.name}\n\n"
                f"⚠️ Could not preview Excel file:\n{str(e)}\n\n"
                f"Double-click to open in Microsoft Excel"
            )

    def preview_csv_file(self, path):
        """Preview CSV file"""
        try:
            
            # Try to read CSV
            df = pd.read_csv(path, nrows=100)
            
            preview = f"📑 CSV File: {path.name}\n"
            preview += f"Rows: {len(df)}, Columns: {len(df.columns)}\n"
            preview += "=" * 60 + "\n\n"
            
            # Column names
            preview += "Columns:\n"
            for i, col in enumerate(df.columns, 1):
                preview += f"  {i}. {col}\n"
            
            preview += "\n" + "=" * 60 + "\n"
            preview += "First 10 Rows:\n"
            preview += "=" * 60 + "\n\n"
            
            preview += df.head(10).to_string(index=False, max_colwidth=40)
            
            if len(df) > 10:
                preview += f"\n\n... and {len(df) - 10} more rows"
            
            self.preview_text.setText(preview)
            self.current_file_content = preview
            
        except Exception:
            # Fallback to text preview
            self.preview_text_file(path)

    def preview_text_file(self, path):
        """Preview text files"""
        try:
            with open(path, 'r', encoding='utf-8', errors='ignore') as f:
                content = f.read(50000)  # Read first 50KB
                
            preview = f"📄 Text File: {path.name}\n"
            preview += f"Size: {path.stat().st_size / 1024:.1f} KB\n"
            preview += "=" * 60 + "\n\n"
            preview += content
            
            if path.stat().st_size > 50000:
                preview += "\n\n... (file truncated for preview)"
            
            self.preview_text.setText(preview)
            self.current_file_content = content
            
        except Exception as e:
            self.preview_text.setText(
                f"Cannot read file:\n{str(e)}\n\n"
                f"File: {path.name}"
            )

    def preview_image_file(self, path):
        """Preview image file info"""
        try:
            
            img = Image.open(path)
            
            preview = f"🖼️ Image: {path.name}\n"
            preview += f"Size: {path.stat().st_size / 1024:.1f} KB\n"
            preview += f"Dimensions: {img.width} × {img.height} pixels\n"
            preview += f"Format: {img.format}\n"
            preview += f"Mode: {img.mode}\n\n"
            preview += "📌 Double-click to view image"
            
            self.preview_text.setText(preview)
            
        except Exception:
            # If PIL not available, show basic info
            self.preview_text.setText(
                f"🖼️ Image: {path.name}\n"
                f"Size: {path.stat().st_size / 1024:.1f} KB\n\n"
                f"📌 Double-click to view image"
            )

    def show_upload_menu(self):
        """Show mainframe upload menu"""
        if not self.current_file_path:
            return
        
        QMessageBox.information(
            self,
            "Upload to Mainframe",
            f"Upload functionality will be integrated here.\n\n"
            f"File: {Path(self.current_file_path).name}"
        )

    def select_file_in_details(self, file_path):
        """Select a specific file in the details view"""
        try:
            file_name = Path(file_path).name
            # Search through the model to find and select the file
            for row in range(self.details_model.rowCount()):
                item = self.details_model.item(row, 0)
                if item and item.text() == file_name:
                    # Get the index in the proxy model
                    source_index = self.details_model.indexFromItem(item)
                    proxy_index = self.details_sort_proxy.mapFromSource(source_index)
                    
                    # Select and scroll to the item
                    self.details_view.setCurrentIndex(proxy_index)
                    self.details_view.scrollTo(proxy_index)
                    break
        except Exception as e:
            logger.error(f"Failed to select file in details: {e}")
