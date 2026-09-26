"""File Explorer Tree."""
from __future__ import annotations

import logging

from suiteview.file_nav.file_explorer_imports import *
from suiteview.file_nav.file_explorer_widgets import (
    DepthScanWorker,
    DropFolderTreeView,
    DropTreeView,
    FileSortProxyModel,
    NoFocusDelegate,
    PrintDirectoryDialog,
)

logger = logging.getLogger(__name__)


class FileExplorerTreeMixin:
    def create_tree_panel(self):
        """Create the tree view with custom model (folders only, name column only)."""
        widget = QWidget()
        widget.setStyleSheet("background-color: #CCE5F8;")
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(self._create_tree_header())
        self._create_folder_tree_view()
        layout.addWidget(self.tree_view)
        self._create_tree_footer(layout)
        return widget

    def _create_tree_header(self):
        header_widget = QWidget()
        header_widget.setStyleSheet(
            """
            QWidget {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    stop:0 #1E5BA8, stop:0.5 #0D3A7A, stop:1 #082B5C);
                border: none;
            }
            """
        )
        header_layout = QHBoxLayout(header_widget)
        header_layout.setContentsMargins(10, 6, 8, 6)
        header_layout.setSpacing(4)
        header_layout.addWidget(self._create_tree_header_label())
        header_layout.addStretch()
        header_layout.addWidget(self._create_folders_history_button())
        return header_widget

    def _create_tree_header_label(self):
        header_label = QLabel("FOLDERS")
        header_label.setStyleSheet(
            """
            QLabel {
                font-weight: 700;
                font-size: 10pt;
                background: transparent;
                color: #D4A017;
                text-transform: uppercase;
                letter-spacing: 1px;
            }
            """
        )
        return header_label

    def _create_folders_history_button(self):
        self.folders_history_btn = QPushButton()
        self.folders_history_btn.setToolTip("Toggle History Panel")
        self.folders_history_btn.setFixedSize(22, 22)
        self.folders_history_btn.setCheckable(True)
        self.folders_history_btn.setText("📜")
        self.folders_history_btn.setStyleSheet("""
            QPushButton {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    stop:0 #4A7DC4, stop:1 #2A5AA4);
                border: 1px solid #1A4A94;
                border-radius: 3px;
                font-size: 10pt;
            }
            QPushButton:hover {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    stop:0 #5A8DD4, stop:1 #3A6AB4);
                border: 1px solid #D4A017;
            }
            QPushButton:checked {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    stop:0 #1E5BA8, stop:1 #082B5C);
                border: 2px solid #D4A017;
            }
        """)
        return self.folders_history_btn

    def _create_folder_tree_view(self):
        self.tree_view = DropFolderTreeView()
        self.tree_view.set_file_explorer(self)
        self.tree_view.files_dropped.connect(self.handle_dropped_files)
        self.tree_view.folder_pinned.connect(self.pin_folder_to_tree)
        self.tree_view.setAnimated(True)
        self.tree_view.setIndentation(20)
        self.tree_view.setHeaderHidden(True)
        self.tree_view.setSelectionMode(QTreeView.SelectionMode.SingleSelection)
        self.tree_view.setStyleSheet(self._tree_view_style())
        self.tree_view.setItemDelegate(NoFocusDelegate(self.tree_view))
        self._create_tree_model()
        self._configure_tree_view()
        self._connect_tree_view_signals()

    def _tree_view_style(self):
        return """
            QTreeView {
                outline: none;
                border: none;
                background-color: #CCE5F8;
            }
            QTreeView::item {
                padding: 2px 6px;
                margin: 0px;
                border: none;
                border-radius: 0px;
                background-color: transparent;
                min-height: 20px;
            }
            QTreeView::item:hover { background-color: #C8DCF0; border: none; }
            QTreeView::item:selected { background-color: #B0C8E8; color: #0A1E5E; border: none; }
            QTreeView::item:selected:!active { background-color: #B0C8E8; color: #0A1E5E; border: none; }
            QTreeView::item:focus { border: none; outline: none; }
            QTreeView::branch { background-color: transparent; border-image: none; image: none; }
            QTreeView::branch:selected { background-color: #B0C8E8; }
            QTreeView::branch:has-children:!has-siblings:closed,
            QTreeView::branch:closed:has-children:has-siblings {
                border-image: none;
                image: none;
                background: qradialgradient(cx:0.5, cy:0.5, radius:0.3, fx:0.5, fy:0.5, stop:0 #0078d4, stop:0.7 #0078d4, stop:0.71 transparent);
            }
            QTreeView::branch:has-children:!has-siblings:open,
            QTreeView::branch:open:has-children:has-siblings {
                border-image: none;
                image: none;
                background: qradialgradient(cx:0.5, cy:0.5, radius:0.3, fx:0.5, fy:0.5, stop:0 #0078d4, stop:0.7 #0078d4, stop:0.71 transparent);
            }
        """

    def _create_tree_model(self):
        self.model = QStandardItemModel()
        self.model.setHorizontalHeaderLabels(['Name'])
        self.model.setColumnCount(1)
        self.populate_tree_model()
        self.tree_view.setModel(self.model)

    def _configure_tree_view(self):
        for col in range(1, 10):
            self.tree_view.setColumnHidden(col, True)
        self.tree_view.header().setStretchLastSection(False)
        self.tree_view.header().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)

    def _connect_tree_view_signals(self):
        self.tree_view.expanded.connect(self.on_item_expanded)
        self.tree_view.clicked.connect(self.on_tree_item_clicked)
        self.tree_view.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.tree_view.customContextMenuRequested.connect(self.show_tree_context_menu)

    def _create_tree_footer(self, layout):
        footer = QLabel("")
        footer.setStyleSheet("""
            QLabel {
                background-color: #E0E0E0;
                padding: 2px 8px;
                font-size: 9pt;
                color: #555555;
                border: none;
                border-top: 1px solid #A0B8D8;
            }
        """)
        footer.setFixedHeight(20)
        layout.addWidget(footer)
        self.tree_footer = footer

    def populate_tree_model(self):
        """Populate tree with OneDrive, pinned folders, and system drives"""
        self.model.clear()
        self.model.setHorizontalHeaderLabels(['Name'])
        self.model.setColumnCount(1)  # Explicitly set to 1 column only
        
        # Track the first OneDrive item for auto-expansion
        self._first_onedrive_item = None
        
        # Add OneDrive folders (excluding hidden ones)
        onedrive_paths = self.get_onedrive_paths()
        for od_path in onedrive_paths:
            if od_path.exists() and str(od_path).lower() not in self.hidden_onedrive_paths:
                item = self.create_tree_folder_item(od_path, icon="⭐")
                self.model.appendRow(item)
                # Store reference to first OneDrive item for auto-expansion
                if self._first_onedrive_item is None:
                    self._first_onedrive_item = item
        
        # Add separator after OneDrive if we have any
        if onedrive_paths:
            separator = QStandardItem("─" * 30)
            separator.setEnabled(False)
            self.model.appendRow(separator)
        
        # Add pinned folders (📌 icon)
        if self.pinned_folders:
            for folder_path in self.pinned_folders:
                path_obj = Path(folder_path)
                if path_obj.exists():
                    item = self.create_tree_folder_item(path_obj, icon="📌")
                    # Mark as pinned so we can offer unpin in context menu
                    item.setData("__PINNED__", Qt.ItemDataRole.UserRole + 2)
                    self.model.appendRow(item)
            
            # Add separator after pinned folders
            separator = QStandardItem("─" * 30)
            separator.setEnabled(False)
            self.model.appendRow(separator)
        
        # Add SharePoint document libraries (🌐 icon, browsed via Graph API)
        if self.sharepoint_libraries:
            for lib in self.sharepoint_libraries:
                item = self.create_sp_tree_item(
                    lib.get('name', 'SharePoint Library'),
                    make_sp_path(lib['drive_id'], lib.get('item_id', 'root')),
                    web_url=lib.get('url', ''),
                    is_root=True)
                self.model.appendRow(item)
            
            # Add separator after SharePoint libraries
            separator = QStandardItem("─" * 30)
            separator.setEnabled(False)
            self.model.appendRow(separator)
        
        # Add system drives
        drives = self.get_system_drives()
        for drive in drives:
            item = self.create_tree_folder_item(Path(drive), icon="💾")
            self.model.appendRow(item)
        
        # Re-hide any extra columns and ensure proper column sizing
        for col in range(1, 10):
            self.tree_view.setColumnHidden(col, True)
        self.tree_view.header().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)

    def expand_first_onedrive(self):
        """Expand the first OneDrive folder in the tree view"""
        if hasattr(self, '_first_onedrive_item') and self._first_onedrive_item is not None:
            try:
                index = self.model.indexFromItem(self._first_onedrive_item)
                if index.isValid():
                    self.tree_view.expand(index)
                    logger.info("Auto-expanded OneDrive folder in tree view")
            except Exception as e:
                logger.error(f"Failed to expand OneDrive folder: {e}")

    def populate_quick_links_model(self, model):
        """Populate a model with quick links only (for the right panel)"""
        model.clear()
        model.setHorizontalHeaderLabels(['Name'])
        model.setColumnCount(1)
        
        # Add custom quick links with system icons (same as details panel)
        for link_path in self.custom_quick_links:
            path = Path(link_path)
            if path.exists():
                item = self.create_quick_link_item(path)
                # Mark as custom link
                item.setData("__QUICK_LINK__", Qt.ItemDataRole.UserRole + 1)
                model.appendRow(item)

    def create_quick_link_item(self, path):
        """Create a tree item for a quick link (file or folder) with system icon"""
        path = Path(path)
        
        item = QStandardItem(path.name)
        item.setData(str(path), Qt.ItemDataRole.UserRole)  # Store path
        item.setEditable(False)
        item.setToolTip(str(path))  # Show full path on hover
        
        # Use system icon (same as details panel)
        is_dir = path.is_dir()
        icon = self._get_cached_icon(path, is_dir)
        item.setIcon(icon)
        
        # If it's a directory, add a placeholder for expansion
        if is_dir:
            placeholder = QStandardItem("Loading...")
            placeholder.setEnabled(False)
            item.appendRow(placeholder)
        
        return item

    def get_onedrive_paths(self):
        """Get all OneDrive paths (deduplicated, prefer business OneDrive)"""
        onedrive_paths = []
        seen_paths = set()
        has_business_onedrive = False
        
        # Check environment variables - prioritize business OneDrive
        for env_var in ['OneDriveCommercial', 'OneDrive', 'OneDriveConsumer']:
            path = os.environ.get(env_var)
            if path and os.path.exists(path):
                path_obj = Path(path).resolve()  # Resolve to absolute path
                path_str = str(path_obj).lower()  # Normalize for comparison
                if path_str not in seen_paths:
                    seen_paths.add(path_str)
                    onedrive_paths.append(path_obj)
                    # Check if this is a business OneDrive (contains company name)
                    if ' - ' in path_obj.name:
                        has_business_onedrive = True
        
        # Check common locations - only if not already found via environment variables
        home = Path.home()
        
        # First check for business OneDrive with company name pattern
        business_onedrive_found = False
        for item in home.iterdir():
            if item.is_dir() and item.name.startswith("OneDrive - "):
                path_resolved = item.resolve()
                path_str = str(path_resolved).lower()
                if path_str not in seen_paths:
                    seen_paths.add(path_str)
                    onedrive_paths.append(path_resolved)
                    business_onedrive_found = True
                    has_business_onedrive = True
        
        # Only add generic "OneDrive" if no business OneDrive was found
        if not has_business_onedrive:
            generic_onedrive = home / "OneDrive"
            if generic_onedrive.exists():
                path_resolved = generic_onedrive.resolve()
                path_str = str(path_resolved).lower()
                if path_str not in seen_paths:
                    seen_paths.add(path_str)
                    onedrive_paths.append(path_resolved)
        
        return onedrive_paths

    def get_system_drives(self):
        """Get all system drives.

        IMPORTANT: this runs on the UI thread during startup, so it must never
        block.  A disconnected mapped network drive (DRIVE_REMOTE) still has its
        bit set in GetLogicalDrives(), but calling os.path.exists() on it can
        stall for many seconds while Windows tries to reconnect — which freezes
        the whole app before the event loop starts.  We therefore trust the
        drive-type for network drives and only do a (fast) existence check on
        local drive types.
        """
        drives = []

        if os.name == 'nt':  # Windows

            DRIVE_REMOVABLE = 2
            DRIVE_FIXED = 3
            DRIVE_REMOTE = 4
            DRIVE_CDROM = 5
            DRIVE_RAMDISK = 6

            bitmask = windll.kernel32.GetLogicalDrives()
            for letter in string.ascii_uppercase:
                if bitmask & 1:
                    drive_path = f"{letter}:\\"
                    drive_type = windll.kernel32.GetDriveTypeW(drive_path)
                    if drive_type == DRIVE_REMOTE:
                        # Mapped network drive — assigned, but may be offline.
                        # Add it without the blocking reachability check; the
                        # tree expands lazily when the user actually clicks it.
                        drives.append(drive_path)
                    elif drive_type in (DRIVE_FIXED, DRIVE_RAMDISK,
                                        DRIVE_REMOVABLE, DRIVE_CDROM):
                        # Local/removable media — existence check is fast.
                        if os.path.exists(drive_path):
                            drives.append(drive_path)
                bitmask >>= 1
        else:  # Unix-like
            drives.append("/")

        return drives

    def create_tree_folder_item(self, path, icon="📁"):
        """Create a single-column folder item for the tree view"""
        path = Path(path)
        
        # Use more descriptive icons for special folders
        folder_name = path.name.lower() if path.name else ""
        
        # Special folder icons
        if not icon or icon == "📁":  # Only override if default folder icon
            if "desktop" in folder_name:
                icon = "🖥️"
            elif "documents" in folder_name:
                icon = "📄"
            elif "downloads" in folder_name:
                icon = "⬇️"
            elif "pictures" in folder_name or "photos" in folder_name:
                icon = "🖼️"
            elif "music" in folder_name:
                icon = "🎵"
            elif "videos" in folder_name:
                icon = "🎬"
            elif "onedrive" in folder_name:
                icon = "☁️"
            elif folder_name in ["program files", "program files (x86)"]:
                icon = "⚙️"
            elif folder_name == "windows":
                icon = "🪟"
            elif folder_name == "users":
                icon = "👥"
            elif ".git" in folder_name:
                icon = "🔀"
            elif "project" in folder_name or "code" in folder_name:
                icon = "💻"
            else:
                icon = "📁"  # Default folder
        
        # Name column with icon
        name_item = QStandardItem(f"{icon} {path.name if path.name else str(path)}")
        name_item.setData(str(path), Qt.ItemDataRole.UserRole)
        name_item.setEditable(False)
        
        # Add placeholder child to make it expandable
        name_item.appendRow(QStandardItem("Loading..."))
        
        return name_item

    def create_folder_item(self, path, icon=None, dir_entry=None):
        """Create a row of items for a folder
        
        Args:
            path: Path to the folder
            icon: Optional custom icon
            dir_entry: Optional os.DirEntry with cached stat data (for network performance)
        """
        path = Path(path)
        
        # Get cached folder icon (fast - no network round-trips)
        system_icon = self._get_cached_icon(path, is_directory=True)
        
        # Name column with system icon
        name_item = QStandardItem(system_icon, path.name if path.name else str(path))
        name_item.setData(str(path), Qt.ItemDataRole.UserRole)
        name_item.setEditable(True)  # Allow editing for F2 rename
        # Store sort data: 0 = folder (sorts first), name in lowercase for case-insensitive sort
        name_item.setData(f"0_{(path.name if path.name else str(path)).lower()}", Qt.ItemDataRole.UserRole + 1)
        
        # Size column (empty for folders)
        size_item = QStandardItem("")
        size_item.setEditable(False)
        size_item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)  # Right-align
        size_item.setData(0, Qt.ItemDataRole.UserRole + 1)  # Sort value for empty size
        
        # Type column
        type_item = QStandardItem("Folder")
        type_item.setEditable(False)
        
        # Date modified - use cached stat from dir_entry when available
        stat_result = self._stat_path(path, dir_entry)
        try:
            if stat_result:
                mtime = stat_result.st_mtime
                date_str = datetime.fromtimestamp(mtime).strftime("%Y-%m-%d %H:%M")
            else:
                date_str = ""
                mtime = 0
        except Exception:
            date_str = ""
            mtime = 0
        date_item = QStandardItem(date_str)
        date_item.setEditable(False)
        # Store timestamp for proper sorting
        date_item.setData(mtime, Qt.ItemDataRole.UserRole + 1)
        
        # Date accessed
        try:
            if stat_result:
                atime = stat_result.st_atime
                adate_str = datetime.fromtimestamp(atime).strftime("%Y-%m-%d %H:%M")
            else:
                adate_str = ""
                atime = 0
        except Exception:
            adate_str = ""
            atime = 0
        adate_item = QStandardItem(adate_str)
        adate_item.setEditable(False)
        adate_item.setData(atime, Qt.ItemDataRole.UserRole + 1)
        
        # Add placeholder child to make it expandable
        name_item.appendRow([
            QStandardItem("Loading..."),
            QStandardItem(""),
            QStandardItem(""),
            QStandardItem(""),
            QStandardItem("")
        ])
        
        return [name_item, size_item, type_item, date_item, adate_item]

    def _safe_startfile(path_str):
        """Open a file with os.startfile, with fallback for long paths (>260 chars).
        
        On Windows with LongPathsEnabled=0, os.startfile() fails for paths
        exceeding MAX_PATH (260 chars). ShellExecuteW (used by os.startfile)
        does NOT support the extended-length path prefix, so we use
        GetShortPathNameW to convert to 8.3 short names that fit within MAX_PATH.
        """
        try:
            os.startfile(path_str)
        except OSError:
            # os.startfile uses ShellExecuteW which doesn't support extended-length
            # path prefix. Use GetShortPathNameW to get the 8.3 short path instead.
            kernel32 = ctypes.windll.kernel32
            buf = ctypes.create_unicode_buffer(512)
            # Build the extended-length path prefix (backslash backslash ? backslash)
            ext_prefix = os.sep + os.sep + '?' + os.sep
            long_prefixed = ext_prefix + os.path.abspath(path_str)
            result = kernel32.GetShortPathNameW(long_prefixed, buf, 512)
            if result:
                short_path = buf.value
                # Strip the 4-char prefix if present in the short path
                if short_path.startswith(ext_prefix):
                    short_path = short_path[4:]
                os.startfile(short_path)
            else:
                raise  # Re-raise the original OSError

    def _stat_path(path, dir_entry=None):
        """Get stat info for a path, using DirEntry cache if available.
        
        Falls back to \\?\\ long-path prefix when normal stat fails.
        Returns stat result or None on failure.
        """
        if dir_entry is not None:
            try:
                return dir_entry.stat()
            except (OSError, PermissionError):
                logger.debug("Suppressed File Explorer exception", exc_info=True)
        try:
            return path.stat()
        except (OSError, PermissionError):
            logger.debug("Suppressed File Explorer exception", exc_info=True)
        # Long-path fallback
        try:
            ext_prefix = os.sep + os.sep + '?' + os.sep
            return Path(ext_prefix + os.path.abspath(str(path))).stat()
        except (OSError, PermissionError):
            return None

    def create_file_item(self, path, dir_entry=None):
        """Create a row of items for a file.
        
        Args:
            path: Path to the file
            dir_entry: Optional os.DirEntry with cached stat data (for long-path support)
        """
        path = Path(path)
        
        # Get cached icon by extension (fast - avoids network round-trips)
        icon = self._get_cached_icon(path, is_directory=False)
        
        # Get suffix for type column
        suffix = path.suffix.lower()
        
        # Name column with system icon
        name_item = QStandardItem(icon, path.name)
        name_item.setData(str(path), Qt.ItemDataRole.UserRole)
        name_item.setEditable(True)  # Allow editing for F2 rename
        # Store sort data: 1 = file (sorts after folders), name in lowercase for case-insensitive sort
        name_item.setData(f"1_{path.name.lower()}", Qt.ItemDataRole.UserRole + 1)
        
        # Get stat info (uses DirEntry cache for long paths, falls back to \\?\\ prefix)
        stat_result = self._stat_path(path, dir_entry)
        
        # Size column
        if stat_result:
            size = stat_result.st_size
            size_bytes = size
            if size < 1024:
                size_str = f"{size} B"
            elif size < 1024 * 1024:
                size_str = f"{size / 1024:.1f} KB"
            elif size < 1024 * 1024 * 1024:
                size_str = f"{size / (1024 * 1024):.1f} MB"
            else:
                size_str = f"{size / (1024 * 1024 * 1024):.2f} GB"
        else:
            size_str = ""
            size_bytes = 0
        size_item = QStandardItem(size_str)
        size_item.setEditable(False)
        size_item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)  # Right-align
        # Store numeric size for proper sorting
        size_item.setData(size_bytes, Qt.ItemDataRole.UserRole + 1)
        
        # Type column
        type_item = QStandardItem(suffix.upper()[1:] if suffix else "File")
        type_item.setEditable(False)
        
        # Date modified
        if stat_result:
            mtime = stat_result.st_mtime
            date_str = datetime.fromtimestamp(mtime).strftime("%Y-%m-%d %H:%M")
        else:
            date_str = ""
            mtime = 0
        date_item = QStandardItem(date_str)
        date_item.setEditable(False)
        # Store timestamp for proper sorting
        date_item.setData(mtime, Qt.ItemDataRole.UserRole + 1)
        
        # Date accessed
        if stat_result:
            atime = stat_result.st_atime
            adate_str = datetime.fromtimestamp(atime).strftime("%Y-%m-%d %H:%M")
        else:
            adate_str = ""
            atime = 0
        adate_item = QStandardItem(adate_str)
        adate_item.setEditable(False)
        adate_item.setData(atime, Qt.ItemDataRole.UserRole + 1)
        
        return [name_item, size_item, type_item, date_item, adate_item]

    def on_item_expanded(self, index):
        """Load directory contents when expanded"""
        item = self.model.itemFromIndex(index)
        if not item:
            return
        
        # Check if this item has a placeholder child
        if item.rowCount() == 1 and item.child(0, 0).text() == "Loading...":
            path = item.data(Qt.ItemDataRole.UserRole)
            
            # SharePoint folders load asynchronously - keep placeholder until results arrive
            if is_sp_path(path):
                self.load_sharepoint_tree_children(item, path)
                return
            
            # Remove placeholder
            item.removeRow(0)
            
            # Load actual contents (folders only for tree)
            if path:
                self.load_tree_directory_contents(item, Path(path))

    def load_tree_directory_contents(self, parent_item, dir_path):
        """Load folder contents into the tree (folders only)"""
        try:
            dir_path = Path(dir_path)
            
            # Get only folders
            folders = [item for item in sorted(dir_path.iterdir(), key=lambda x: x.name.lower()) 
                      if item.is_dir()]
            
            for folder_path in folders:
                try:
                    item = self.create_tree_folder_item(folder_path)
                    parent_item.appendRow(item)
                except (PermissionError, OSError):
                    # Skip items we can't access
                    continue
                    
        except (PermissionError, OSError):
            # Show error message
            error_item = QStandardItem(f"❌ Access denied")
            error_item.setEnabled(False)
            parent_item.appendRow(error_item)

    def on_tree_item_clicked(self, index):
        """Handle click on tree item - load folder contents in details view"""
        # Block navigation if depth search is locked
        if self.depth_search_locked:
            QMessageBox.warning(self, "Navigation Locked", 
                "Folder navigation is locked while depth search is active.\n\n"
                "Turn off depth search to navigate to other folders.")
            return
        
        item = self.model.itemFromIndex(index)
        if not item:
            return
        
        path = item.data(Qt.ItemDataRole.UserRole)
        if is_sp_path(path):
            display_name = item.data(Qt.ItemDataRole.UserRole + 5) or item.text()
            self.load_sharepoint_contents_in_details(path, display_name)
            return
        if path:
            self.load_folder_contents_in_details(Path(path))

    def refresh_tree(self):
        """Refresh the tree view"""
        self.populate_tree_model()

