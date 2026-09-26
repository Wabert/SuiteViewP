"""File Explorer Sharepoint."""
from __future__ import annotations

import json
import logging
import re
import stat as stat_module
import tempfile
import time
from datetime import datetime
from pathlib import Path

from PyQt6.QtCore import (
    QPersistentModelIndex,
    QRegularExpression,
    Qt,
    QUrl,
)
from PyQt6.QtGui import (
    QDesktopServices,
    QStandardItem,
)
from PyQt6.QtWidgets import (
    QApplication,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QInputDialog,
    QLabel,
    QLineEdit,
    QMenu,
    QMessageBox,
    QProgressDialog,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
)

from suiteview.core.json_store import write_json
from suiteview.file_nav.sharepoint_client import (
    SharePointDiscoverWorker,
    SharePointDownloadWorker,
    SharePointListWorker,
    SharePointResolveWorker,
    make_sp_path,
    parse_sp_path,
)
from suiteview.ui import muted_signals
from suiteview.ui.workers import WorkerController

logger = logging.getLogger(__name__)


class FileExplorerSharePointMixin:
    """Requires: SharePoint library state, details/tree models, and worker tracking.
    Provides: library discovery, Graph listings, downloads, and virtual-path rows.
    """

    def load_sharepoint_libraries(self):
        """Load saved SharePoint libraries from JSON file"""
        try:
            if self.sharepoint_libraries_file.exists():
                with open(self.sharepoint_libraries_file, 'r') as f:
                    return json.load(f)
        except (OSError, json.JSONDecodeError) as e:
            logger.error(f"Failed to load SharePoint libraries: {e}")
        return []

    def save_sharepoint_libraries(self):
        """Save SharePoint libraries to JSON file"""
        try:
            self.sharepoint_libraries_file.parent.mkdir(parents=True, exist_ok=True)
            write_json(self.sharepoint_libraries_file, self.sharepoint_libraries, ensure_ascii=True)
        except OSError as e:
            logger.error(f"Failed to save SharePoint libraries: {e}")

    def create_sp_tree_item(self, name, sp_path, web_url="", is_root=False, has_children=True):
        """Create a tree item for a SharePoint library or folder"""
        icon = "🌐" if is_root else "📁"
        item = QStandardItem(f"{icon} {name}")
        item.setData(sp_path, Qt.ItemDataRole.UserRole)
        item.setData("folder", Qt.ItemDataRole.UserRole + 3)
        item.setData(web_url, Qt.ItemDataRole.UserRole + 4)
        item.setData(name, Qt.ItemDataRole.UserRole + 5)
        item.setEditable(False)
        item.setToolTip(web_url or name)
        if is_root:
            item.setData("__SHAREPOINT__", Qt.ItemDataRole.UserRole + 2)
        if has_children:
            placeholder = QStandardItem("Loading...")
            placeholder.setEnabled(False)
            item.appendRow(placeholder)
        return item

    def _track_sp_worker(self, controller):
        """Keep a reference to a worker controller and clean up when it finishes."""
        self._sp_workers.append(controller)
        controller.finished.connect(lambda: self._sp_workers.remove(controller)
                                    if controller in self._sp_workers else None)

    def add_sharepoint_library_dialog(self):
        """Prompt for a SharePoint library URL and add it to the tree"""
        url, ok = QInputDialog.getText(
            self, "Add SharePoint Library",
            "Paste the SharePoint document library URL\n"
            "(e.g. https://yourcompany.sharepoint.com/sites/SiteName/LibraryName):",
            QLineEdit.EchoMode.Normal, "https://")
        if not ok or not url or url.strip() in ("", "https://"):
            return
        
        # Already added?
        for lib in self.sharepoint_libraries:
            if lib.get('url', '').rstrip('/').lower() == url.strip().rstrip('/').lower():
                QMessageBox.information(self, "Already Added",
                                        "That library is already in the Folders panel.")
                return
        
        progress = QProgressDialog(
            "Connecting to SharePoint…\n\n"
            "If a browser window opens, complete the sign-in with your work account.",
            "Cancel", 0, 0, self)
        progress.setWindowTitle("Add SharePoint Library")
        progress.setWindowModality(Qt.WindowModality.WindowModal)
        progress.setMinimumDuration(0)
        
        worker = SharePointResolveWorker(url.strip())
        
        def on_resolved(lib):
            progress.close()
            self.sharepoint_libraries.append(lib)
            self.save_sharepoint_libraries()
            self.populate_tree_model()
            logger.info(f"Added SharePoint library: {lib['name']}")
        
        def on_failed(msg):
            progress.close()
            QMessageBox.warning(self, "Add SharePoint Library", msg)
        
        def on_cancelled():
            # Don't kill the thread mid-request - just ignore its result
            try:
                controller.result.disconnect(on_resolved)
                controller.error.disconnect(on_failed)
            except TypeError:
                logger.debug("Suppressed File Explorer exception", exc_info=True)
        
        controller = WorkerController(self, worker)
        controller.result.connect(on_resolved)
        controller.error.connect(on_failed)
        progress.canceled.connect(on_cancelled)
        self._track_sp_worker(controller)
        controller.start()
        progress.show()

    def discover_sharepoint_libraries_dialog(self):
        """Find all document libraries on sites the user syncs with OneDrive,
        and let them pick which ones to add to the Folders panel."""
        progress = QProgressDialog(
            "Discovering your SharePoint libraries…\n\n"
            "If a browser window opens, complete the sign-in with your work account.",
            "Cancel", 0, 0, self)
        progress.setWindowTitle("Discover My Libraries")
        progress.setWindowModality(Qt.WindowModality.WindowModal)
        progress.setMinimumDuration(0)
        
        worker = SharePointDiscoverWorker()
        
        def on_progress(msg):
            progress.setLabelText(f"Discovering your SharePoint libraries…\n\n{msg}")
        
        def on_discovered(libraries):
            progress.close()
            self._show_sp_library_picker(libraries)
        
        def on_failed(msg):
            progress.close()
            QMessageBox.warning(self, "Discover My Libraries", msg)
        
        def on_cancelled():
            try:
                controller.result.disconnect(on_discovered)
                controller.error.disconnect(on_failed)
            except TypeError:
                logger.debug("Suppressed File Explorer exception", exc_info=True)
        
        controller = WorkerController(self, worker)
        controller.progress.connect(on_progress)
        controller.result.connect(on_discovered)
        controller.error.connect(on_failed)
        progress.canceled.connect(on_cancelled)
        self._track_sp_worker(controller)
        controller.start()
        progress.show()

    def _show_sp_library_picker(self, libraries):
        """Checkbox picker for discovered libraries, grouped by site"""
        
        existing = {lib.get('drive_id') for lib in self.sharepoint_libraries}
        
        dialog = QDialog(self)
        dialog.setWindowTitle("Discover My Libraries")
        dialog.resize(560, 480)
        layout = QVBoxLayout(dialog)
        
        info = QLabel(f"Found {len(libraries)} document libraries on your synced sites.\n"
                      "Check the ones to add to the Folders panel:")
        layout.addWidget(info)
        
        tree = QTreeWidget()
        tree.setHeaderLabels(["Library"])
        tree.setRootIsDecorated(True)
        
        # Group by site
        sites = {}
        for lib in libraries:
            sites.setdefault(lib.get('site_name', 'SharePoint'), []).append(lib)
        
        for site_name, libs in sites.items():
            site_item = QTreeWidgetItem(tree, [f"🏢 {site_name}"])
            site_item.setFlags(site_item.flags() & ~Qt.ItemFlag.ItemIsUserCheckable)
            for lib in libs:
                child = QTreeWidgetItem(site_item, [f"🌐 {lib.get('library_name', lib['name'])}"])
                child.setToolTip(0, lib.get('url', ''))
                child.setData(0, Qt.ItemDataRole.UserRole, lib)
                if lib['drive_id'] in existing:
                    child.setText(0, child.text(0) + "   (already added)")
                    child.setFlags(Qt.ItemFlag.ItemIsEnabled)  # visible but not checkable
                else:
                    child.setFlags(child.flags() | Qt.ItemFlag.ItemIsUserCheckable)
                    child.setCheckState(0, Qt.CheckState.Unchecked)
            site_item.setExpanded(True)
        
        layout.addWidget(tree)
        
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok
                                   | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        layout.addWidget(buttons)
        
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        
        added = 0
        for i in range(tree.topLevelItemCount()):
            site_item = tree.topLevelItem(i)
            for j in range(site_item.childCount()):
                child = site_item.child(j)
                if child.checkState(0) == Qt.CheckState.Checked:
                    lib = child.data(0, Qt.ItemDataRole.UserRole)
                    self.sharepoint_libraries.append({
                        'name': lib['name'], 'url': lib['url'],
                        'drive_id': lib['drive_id'], 'item_id': lib.get('item_id', 'root'),
                    })
                    added += 1
        
        if added:
            self.save_sharepoint_libraries()
            self.populate_tree_model()
            logger.info(f"Added {added} SharePoint libraries via discovery")

    def remove_sharepoint_library(self, sp_path):
        """Remove a SharePoint library from the tree (by its sp:// root path)"""
        drive_id, item_id = parse_sp_path(sp_path)
        for i, lib in enumerate(self.sharepoint_libraries):
            if lib.get('drive_id') == drive_id and lib.get('item_id', 'root') == item_id:
                removed = self.sharepoint_libraries.pop(i)
                self.save_sharepoint_libraries()
                self.populate_tree_model()
                logger.info(f"Removed SharePoint library: {removed.get('name')}")
                return

    def load_sharepoint_tree_children(self, item, sp_path):
        """Async-load subfolders of a SharePoint folder into the tree"""
        if sp_path in self._sp_pending_tree:
            return  # Listing already in flight
        self._sp_pending_tree.add(sp_path)
        
        context = {"pidx": QPersistentModelIndex(self.model.indexFromItem(item)),
                   "sp_path": sp_path}
        worker = SharePointListWorker(sp_path, context)
        controller = WorkerController(self, worker)
        controller.result.connect(lambda payload: self._on_sp_tree_children(payload[0], payload[1]))
        controller.error.connect(lambda payload: self._on_sp_tree_failed(payload[0], payload[1]))
        self._track_sp_worker(controller)
        controller.start()

    def _sp_tree_item_from_context(self, context):
        self._sp_pending_tree.discard(context["sp_path"])
        pidx = context["pidx"]
        if not pidx.isValid():
            return None
        return self.model.itemFromIndex(self.model.index(pidx.row(), pidx.column(),
                                                          pidx.parent()))

    def _on_sp_tree_children(self, context, entries):
        """Populate a tree node with SharePoint subfolders (folders only)"""
        item = self._sp_tree_item_from_context(context)
        if item is None:
            return
        item.removeRows(0, item.rowCount())
        drive_id, _ = parse_sp_path(context["sp_path"])
        for entry in entries:
            if not entry["is_folder"]:
                continue
            child = self.create_sp_tree_item(
                entry["name"], make_sp_path(drive_id, entry["id"]),
                web_url=entry["web_url"],
                has_children=entry["child_count"] > 0)
            item.appendRow(child)

    def _on_sp_tree_failed(self, context, message):
        item = self._sp_tree_item_from_context(context)
        if item is None:
            return
        item.removeRows(0, item.rowCount())
        error_item = QStandardItem(f"❌ {message}")
        error_item.setEnabled(False)
        item.appendRow(error_item)

    def _refresh_sp_tree_item(self, item):
        """Re-fetch a SharePoint tree node's children"""
        sp_path = item.data(Qt.ItemDataRole.UserRole)
        item.removeRows(0, item.rowCount())
        placeholder = QStandardItem("Loading...")
        placeholder.setEnabled(False)
        item.appendRow(placeholder)
        self.load_sharepoint_tree_children(item, sp_path)

    def load_sharepoint_contents_in_details(self, sp_path, display_name=None):
        """Async-load a SharePoint folder's contents into the details view"""
        self._sp_details_generation += 1
        generation = self._sp_details_generation
        start_time = time.perf_counter()
        
        # Returning to the depth search folder while locked — restore the
        # depth results instead of re-listing the folder (mirrors the local
        # branch at the top of load_folder_contents_in_details)
        if (self.depth_search_locked and 
            self.depth_search_folder and 
            sp_path == self.depth_search_folder and
            self.depth_search_active_results):
            self.current_details_folder = sp_path
            self._sp_current_name = (display_name or self.depth_search_folder_name
                                     or "SharePoint")
            self.details_view.set_current_folder(sp_path)
            self.details_header.setText(f"\U0001F310 {self._sp_current_name}")
            
            # Restore folder-specific search term for the depth search folder
            if hasattr(self, 'details_search') and hasattr(self, 'folder_search_terms'):
                saved_search = self.folder_search_terms.get(sp_path, "")
                with muted_signals(self.details_search):
                    self.details_search.setText(saved_search)
                if saved_search:
                    escaped = QRegularExpression.escape(saved_search)
                    regex = QRegularExpression(escaped, QRegularExpression.PatternOption.CaseInsensitiveOption)
                    self.details_sort_proxy.setFilterRegularExpression(regex)
                else:
                    self.details_sort_proxy.setFilterRegularExpression(QRegularExpression())
            
            self._populate_depth_results(self.depth_search_active_results)
            return
        
        self.current_details_folder = sp_path
        self._sp_current_name = display_name or "SharePoint"
        self.details_view.set_current_folder(sp_path)
        self.details_header.setText(f"🌐 {self._sp_current_name}")
        
        # Restore folder-specific search term (same behavior as local folders)
        if hasattr(self, 'details_search') and hasattr(self, 'folder_search_terms'):
            saved_search = self.folder_search_terms.get(sp_path, "")
            with muted_signals(self.details_search):
                self.details_search.setText(saved_search)
            if saved_search:
                escaped = QRegularExpression.escape(saved_search)
                regex = QRegularExpression(escaped, QRegularExpression.PatternOption.CaseInsensitiveOption)
                self.details_sort_proxy.setFilterRegularExpression(regex)
            else:
                self.details_sort_proxy.setFilterRegularExpression(QRegularExpression())
        
        # Reset model with loading indicator, preserving column widths
        self._reset_details_model_for_sp()
        loading_item = QStandardItem("⏳ Loading from SharePoint…")
        loading_item.setEnabled(False)
        self.details_model.appendRow([loading_item, QStandardItem(""), QStandardItem(""),
                                      QStandardItem(""), QStandardItem("")])
        
        context = {"gen": generation, "sp_path": sp_path, "start": start_time}
        worker = SharePointListWorker(sp_path, context)
        controller = WorkerController(self, worker)
        controller.result.connect(lambda payload: self._on_sp_details_ready(payload[0], payload[1]))
        controller.error.connect(lambda payload: self._on_sp_details_failed(payload[0], payload[1]))
        self._track_sp_worker(controller)
        controller.start()

    def _reset_details_model_for_sp(self):
        """Clear the details model while preserving column widths (SP loads)"""
        self.details_model.clear()
        self.details_model.setHorizontalHeaderLabels(
            ['Name', 'Size', 'Type', 'Date Modified', 'Date Accessed'])
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

    def _on_sp_details_ready(self, context, entries):
        """Populate the details view with SharePoint folder contents"""
        if (context["gen"] != self._sp_details_generation
                or self.current_details_folder != context["sp_path"]):
            return  # Stale result - user navigated elsewhere
        
        drive_id, _ = parse_sp_path(context["sp_path"])
        
        self._reset_details_model_for_sp()
        entries.sort(key=lambda e: (not e["is_folder"], e["name"].lower()))
        
        self.details_view.setUpdatesEnabled(False)
        try:
            for entry in entries:
                self.details_model.appendRow(
                    self._create_sp_details_row(entry, make_sp_path(drive_id, entry["id"])))
        finally:
            self.details_view.setUpdatesEnabled(True)
        
        # Re-apply current sort order
        header = self.details_view.header()
        self.details_sort_proxy.sort(header.sortIndicatorSection(), header.sortIndicatorOrder())
        
        elapsed_ms = int((time.perf_counter() - context["start"]) * 1000)
        self.update_details_footer(timing_ms=elapsed_ms)

    def _on_sp_details_failed(self, context, message):
        if (context["gen"] != self._sp_details_generation
                or self.current_details_folder != context["sp_path"]):
            return
        self._reset_details_model_for_sp()
        error_item = QStandardItem(f"❌ {message}")
        error_item.setEnabled(False)
        self.details_model.appendRow([error_item, QStandardItem(""), QStandardItem(""),
                                      QStandardItem(""), QStandardItem("")])

    def _create_sp_details_row(self, entry, sp_path):
        """Build a 5-column details row from a SharePoint item dict"""
        name = entry["name"]
        is_folder = entry["is_folder"]
        
        icon = self._get_cached_icon(Path(name), is_directory=is_folder)
        name_item = QStandardItem(icon, name)
        name_item.setData(sp_path, Qt.ItemDataRole.UserRole)
        name_item.setData(f"{'0' if is_folder else '1'}_{name.lower()}", Qt.ItemDataRole.UserRole + 1)
        name_item.setData("folder" if is_folder else "file", Qt.ItemDataRole.UserRole + 3)
        name_item.setData(entry["web_url"], Qt.ItemDataRole.UserRole + 4)
        name_item.setData(name, Qt.ItemDataRole.UserRole + 5)
        name_item.setEditable(False)
        
        # Size (blank for folders, like local view)
        if is_folder:
            size_str, size_val = "", 0
        else:
            size_val = entry["size"]
            if size_val < 1024:
                size_str = f"{size_val} B"
            elif size_val < 1024 * 1024:
                size_str = f"{size_val / 1024:.1f} KB"
            elif size_val < 1024 * 1024 * 1024:
                size_str = f"{size_val / (1024 * 1024):.1f} MB"
            else:
                size_str = f"{size_val / (1024 * 1024 * 1024):.2f} GB"
        size_item = QStandardItem(size_str)
        size_item.setEditable(False)
        size_item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        size_item.setData(size_val, Qt.ItemDataRole.UserRole + 1)
        
        # Type
        suffix = Path(name).suffix.lower()
        type_item = QStandardItem("Folder" if is_folder
                                  else (suffix.upper()[1:] if suffix else "File"))
        type_item.setEditable(False)
        
        # Date modified (Graph returns ISO 8601 UTC)
        date_str, mtime = "", 0
        if entry["modified"]:
            try:
                dt = datetime.fromisoformat(entry["modified"].replace("Z", "+00:00")).astimezone()
                date_str = dt.strftime("%Y-%m-%d %H:%M")
                mtime = dt.timestamp()
            except ValueError:
                logger.debug("Suppressed File Explorer exception", exc_info=True)
        date_item = QStandardItem(date_str)
        date_item.setEditable(False)
        date_item.setData(mtime, Qt.ItemDataRole.UserRole + 1)
        
        # Date accessed (not available from SharePoint)
        adate_item = QStandardItem("")
        adate_item.setEditable(False)
        adate_item.setData(0, Qt.ItemDataRole.UserRole + 1)
        
        return [name_item, size_item, type_item, date_item, adate_item]

    def open_sharepoint_file(self, sp_path, name, dest_path=None):
        """Download a SharePoint file (to temp cache by default) and open it.
        
        The cached copy is marked read-only so edits aren't mistaken for
        changes that would sync back to SharePoint.
        """
        
        open_after = dest_path is None
        if dest_path is None:
            _, item_id = parse_sp_path(sp_path)
            safe_id = re.sub(r'[^A-Za-z0-9_-]', '_', item_id)[:40]
            dest_path = Path(tempfile.gettempdir()) / "SuiteView_SharePoint" / safe_id / name
        
        progress = QProgressDialog(f"Downloading {name}…", "Cancel", 0, 100, self)
        progress.setWindowTitle("SharePoint")
        progress.setWindowModality(Qt.WindowModality.WindowModal)
        progress.setMinimumDuration(400)
        
        worker = SharePointDownloadWorker(sp_path, dest_path)
        
        def on_progress(done, total):
            if total > 0:
                progress.setMaximum(100)
                progress.setValue(min(99, int(done * 100 / total)))
            else:
                progress.setMaximum(0)  # Indeterminate
        
        def on_finished(local_path):
            progress.close()
            if open_after:
                try:
                    # Read-only: this is a downloaded copy, not a synced file
                    Path(local_path).chmod(stat_module.S_IREAD)
                except OSError:
                    logger.debug("Suppressed File Explorer exception", exc_info=True)
                try:
                    self._safe_startfile(local_path)
                except Exception as e:
                    logger.error(f"Failed to open downloaded file: {e}")
                    QMessageBox.warning(self, "Cannot Open File",
                                        f"Downloaded but failed to open {name}\n\nError: {e}")
        
        def on_failed(msg):
            progress.close()
            if msg != "Download cancelled":
                QMessageBox.warning(self, "SharePoint Download", msg)
        
        controller = WorkerController(self, worker, cancel=worker.cancel)
        controller.progress.connect(lambda payload: on_progress(payload[0], payload[1]))
        controller.result.connect(on_finished)
        controller.error.connect(on_failed)
        progress.canceled.connect(controller.cancel)
        self._track_sp_worker(controller)
        controller.start()

    def show_sp_details_context_menu(self, position, index):
        """Context menu for the details view when browsing SharePoint (read-only)"""
        menu = QMenu()
        
        if index.isValid():
            col0_index = index.sibling(index.row(), 0)
            sp_path = self.details_sort_proxy.data(col0_index, Qt.ItemDataRole.UserRole)
            kind = self.details_sort_proxy.data(col0_index, Qt.ItemDataRole.UserRole + 3)
            name = self.details_sort_proxy.data(col0_index, Qt.ItemDataRole.UserRole + 5)
            web_url = self.details_sort_proxy.data(col0_index, Qt.ItemDataRole.UserRole + 4)
            
            if sp_path:
                if kind == "folder":
                    open_action = menu.addAction("📂 Open")
                    open_action.triggered.connect(
                        lambda: self.load_sharepoint_contents_in_details(sp_path, name))
                else:
                    open_action = menu.addAction("📄 Open (download copy)")
                    open_action.triggered.connect(
                        lambda: self.open_sharepoint_file(sp_path, name))
                    save_action = menu.addAction("💾 Save a Copy As…")
                    save_action.triggered.connect(
                        lambda: self._save_sp_file_as(sp_path, name))
                
                if web_url:
                    browser_action = menu.addAction("🌐 Open in Browser")
                    browser_action.triggered.connect(
                        lambda: QDesktopServices.openUrl(QUrl(web_url)))
                    copy_link_action = menu.addAction("🔗 Copy SharePoint Link")
                    copy_link_action.triggered.connect(
                        lambda: QApplication.clipboard().setText(web_url))
                
                menu.addSeparator()
        
        refresh_action = menu.addAction("🔄 Refresh")
        refresh_action.triggered.connect(self.refresh_details_view)
        
        menu.exec(self.details_view.viewport().mapToGlobal(position))

    def _save_sp_file_as(self, sp_path, name):
        """Download a SharePoint file to a user-chosen location"""
        dest, _ = QFileDialog.getSaveFileName(self, "Save a Copy As",
                                              str(Path.home() / "Downloads" / name))
        if dest:
            self.open_sharepoint_file(sp_path, name, dest_path=dest)
