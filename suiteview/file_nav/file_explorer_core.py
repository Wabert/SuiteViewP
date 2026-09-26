"""Composed File Explorer widget.

Most feature areas live in focused mixins so this module stays importable for
existing FileNav callers while the behavior is organized by concern.
"""
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
from suiteview.file_nav.file_explorer_bookmarks import FileExplorerBookmarksMixin
from suiteview.file_nav.file_explorer_context_menus import FileExplorerContextMenuMixin
from suiteview.file_nav.file_explorer_details_io import FileExplorerDetailsIOMixin
from suiteview.file_nav.file_explorer_details_panel import FileExplorerDetailsPanelMixin
from suiteview.file_nav.file_explorer_details_search import FileExplorerDetailsSearchMixin
from suiteview.file_nav.file_explorer_export import FileExplorerExportMixin
from suiteview.file_nav.file_explorer_file_ops import FileExplorerFileOpsMixin
from suiteview.file_nav.file_explorer_layout import FileExplorerLayoutMixin
from suiteview.file_nav.file_explorer_sharepoint import FileExplorerSharePointMixin
from suiteview.file_nav.file_explorer_tree import FileExplorerTreeMixin

logger = logging.getLogger(__name__)


class FileExplorerCore(FileExplorerTreeMixin, FileExplorerDetailsPanelMixin, FileExplorerDetailsSearchMixin, FileExplorerDetailsIOMixin, FileExplorerContextMenuMixin, FileExplorerFileOpsMixin, FileExplorerBookmarksMixin, FileExplorerSharePointMixin, FileExplorerLayoutMixin, FileExplorerExportMixin, QWidget):
    """
    Core File Explorer with custom model showing OneDrive at top level
    Features:
    - OneDrive shortcuts at root level (like Windows Explorer)
    - System drives (C: D: etc.)
    - Lazy loading of directory contents
    - File operations (cut, copy, paste, rename, delete)
    - File preview pane with mainframe upload button
    """
    
    # Icon cache by extension - loaded once, reused for all files
    _icon_cache = {}
    _folder_icon = None
    
    # Extension to icon type mapping for fast lookups
    ICON_TYPES = {
        # Documents
        '.xlsx': 'excel', '.xls': 'excel', '.xlsm': 'excel', '.xlsb': 'excel',
        '.docx': 'word', '.doc': 'word', '.docm': 'word',
        '.pptx': 'powerpoint', '.ppt': 'powerpoint', '.pptm': 'powerpoint',
        '.pdf': 'pdf',
        '.txt': 'text', '.log': 'text', '.md': 'text', '.csv': 'text',
        # Data
        '.accdb': 'database', '.mdb': 'database', '.db': 'database', '.sqlite': 'database',
        '.laccdb': 'database',
        # Code
        '.py': 'code', '.js': 'code', '.java': 'code', '.cpp': 'code', '.c': 'code',
        '.html': 'code', '.css': 'code', '.json': 'code', '.xml': 'code',
        # Images
        '.jpg': 'image', '.jpeg': 'image', '.png': 'image', '.gif': 'image',
        '.bmp': 'image', '.ico': 'image', '.svg': 'image',
        # Archives
        '.zip': 'archive', '.rar': 'archive', '.7z': 'archive', '.tar': 'archive', '.gz': 'archive',
        # Executables
        '.exe': 'exe', '.msi': 'exe', '.bat': 'exe', '.cmd': 'exe', '.ps1': 'exe',
        # Shortcuts
        '.lnk': 'shortcut', '.url': 'shortcut',
    }
    def __init__(self):
        guard_app_access("FILENAV")
        super().__init__()
        
        # Allow widget to shrink so parent window can collapse to minimal size
        self.setMinimumSize(0, 0)
        
        # Initialize icon provider for Windows system icons (used sparingly)
        self.icon_provider = QFileIconProvider()
        
        # Pre-cache common icons on first instance
        self._init_icon_cache()
        
        self.current_file_path = None
        self.current_file_content = None
        self.current_details_folder = None  # Track current folder in details view
        self.clipboard = {"paths": [], "operation": None}
        
        # Depth search feature
        self.depth_search_enabled = False
        self.depth_search_cache = {}  # Cache: {folder_path: {depth_level: [items]}}
        self.depth_search_folder = None  # Folder where depth search was initiated
        self.depth_search_folder_name = None  # Display name of that folder (SharePoint)
        self.depth_search_locked = False  # True when depth search is active and locked
        self.depth_search_active_results = None  # Currently displayed depth results
        
        # Folder-specific search terms
        self.folder_search_terms = {}  # Cache: {folder_path: search_text}
        
        # Load custom quick links via centralized bookmark manager
        # Bar ID 1 = sidebar (by convention)
        self._bookmark_manager = get_bookmark_manager()
        self.custom_quick_links = self._bookmark_manager.get_bar_data(1)
        
        # Load hidden OneDrive paths
        self.hidden_onedrive_file = profile_path('hidden_onedrive.json')
        self.hidden_onedrive_paths = self.load_hidden_onedrive()
        
        # Load pinned folders for the Folders panel
        self.pinned_folders_file = profile_path('pinned_folders.json')
        self.pinned_folders = self.load_pinned_folders()
        
        # SharePoint document libraries (browsed live via Graph API - no OneDrive sync)
        self.sharepoint_libraries_file = profile_path('sharepoint_libraries.json')
        self.sharepoint_libraries = self.load_sharepoint_libraries()
        self._sp_workers = []             # keep refs so QThreads aren't GC'd mid-run
        self._sp_pending_tree = set()     # sp paths with an in-flight tree listing
        self._sp_details_generation = 0   # ignore stale async details results
        self._sp_current_name = None      # display name of current SP folder in details
        
        # Column width settings file
        self.column_widths_file = profile_path('column_widths.json')
        self.column_widths = self.load_column_widths()
        
        # Panel widths persistence
        self.panel_widths_file = profile_path('file_explorer_panel_widths.json')
        self.panel_widths = self.load_panel_widths()
        
        # Debounce timers for performance - avoid disk writes on every pixel
        self._column_resize_timer = None
        self._splitter_move_timer = None
        self._search_debounce_timer = None
        
        self.init_ui()

    def _init_icon_cache(self):
        """Initialize icon cache with common file type icons"""
        if FileExplorerCore._folder_icon is not None:
            return  # Already initialized
        
        # Get folder icon once
        FileExplorerCore._folder_icon = self.icon_provider.icon(QFileIconProvider.IconType.Folder)
        
        # Get standard icons from style for common types
        style = self.style()
        
        # Cache file icon as default
        FileExplorerCore._icon_cache['_default'] = self.icon_provider.icon(QFileIconProvider.IconType.File)

    def get_emoji_icon_for_path(self, path):
        """Get emoji icon based on file type - for Quick Links panel"""
        path = Path(path) if isinstance(path, str) else path
        
        if path.is_dir():
            # Check for special folder names
            folder_name = path.name.lower()
            if "onedrive" in folder_name:
                return "☁️"
            elif "desktop" in folder_name:
                return "🖥️"
            elif "documents" in folder_name:
                return "📄"
            elif "downloads" in folder_name:
                return "⬇️"
            elif "pictures" in folder_name or "photos" in folder_name:
                return "🖼️"
            elif "music" in folder_name:
                return "🎵"
            elif "videos" in folder_name:
                return "🎬"
            return "📁"
        
        # It's a file - get icon based on extension
        suffix = path.suffix.lower()
        
        # Map extensions to emoji icons
        emoji_map = {
            # Excel
            '.xlsx': '📊', '.xls': '📊', '.xlsm': '📊', '.xlsb': '📊', '.csv': '📊',
            # Word
            '.docx': '📝', '.doc': '📝', '.docm': '📝', '.rtf': '📝',
            # PowerPoint
            '.pptx': '📽️', '.ppt': '📽️', '.pptm': '📽️',
            # PDF
            '.pdf': '📕',
            # Database / Access
            '.accdb': '🗃️', '.mdb': '🗃️', '.db': '🗃️', '.sqlite': '🗃️', '.laccdb': '🗃️',
            # Text
            '.txt': '📄', '.log': '📄', '.md': '📄',
            # Code
            '.py': '🐍', '.js': '📜', '.java': '☕', '.cpp': '⚙️', '.c': '⚙️',
            '.html': '🌐', '.css': '🎨', '.json': '📋', '.xml': '📋',
            # Images
            '.jpg': '🖼️', '.jpeg': '🖼️', '.png': '🖼️', '.gif': '🖼️',
            '.bmp': '🖼️', '.ico': '🖼️', '.svg': '🖼️',
            # Archives
            '.zip': '📦', '.rar': '📦', '.7z': '📦', '.tar': '📦', '.gz': '📦',
            # Executables
            '.exe': '⚙️', '.msi': '⚙️', '.bat': '⚙️', '.cmd': '⚙️', '.ps1': '⚙️',
            # Shortcuts
            '.lnk': '🔗', '.url': '🔗',
        }
        
        return emoji_map.get(suffix, '📄')

    def _get_cached_icon(self, path: Path, is_directory: bool = False):
        """Get icon from cache or create it - fast path for common extensions"""
        if is_directory:
            return FileExplorerCore._folder_icon
        
        suffix = path.suffix.lower()
        
        # Check cache first
        if suffix in FileExplorerCore._icon_cache:
            return FileExplorerCore._icon_cache[suffix]
        
        # For local files, get the actual icon and cache it
        path_str = str(path)
        is_network = path_str.startswith('\\\\')
        
        if not is_network:
            # Local file - get real icon and cache by extension
            try:
                # If file exists, get its icon directly
                if path.exists():
                    file_info = QFileInfo(path_str)
                    icon = self.icon_provider.icon(file_info)
                    FileExplorerCore._icon_cache[suffix] = icon
                    return icon
                else:
                    # File doesn't exist - try to find another file with same extension
                    # to get the icon from Windows shell
                    temp_file = Path(tempfile.gettempdir()) / f"_icon_temp{suffix}"
                    try:
                        temp_file.touch()
                        file_info = QFileInfo(str(temp_file))
                        icon = self.icon_provider.icon(file_info)
                        FileExplorerCore._icon_cache[suffix] = icon
                        temp_file.unlink()
                        return icon
                    except Exception:
                        if temp_file.exists():
                            temp_file.unlink()
            except Exception:
                logger.debug("Suppressed File Explorer exception", exc_info=True)
        
        # Network file or error - use default file icon
        return FileExplorerCore._icon_cache.get('_default', FileExplorerCore._folder_icon)

    def init_ui(self):
        """Initialize the UI"""
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(4, 4, 4, 4)
        main_layout.setSpacing(2)
        
        # Apply light blue gradient background (PolView style)
        self.setStyleSheet("""
            FileExplorerCore {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    stop:0 #C8DCF8, stop:0.3 #A8C8F0, stop:1 #88B8E8);
            }
        """)
        
        # Create toolbar (hidden by default - buttons now in header bar)
        toolbar = self.create_toolbar()
        toolbar.hide()  # Hidden - functionality moved to header bar
        main_layout.addWidget(toolbar)
        
        # Create bookmark bar (browser-style) using BookmarkContainer directly
        self.bookmark_bar = BookmarkContainer(
            bar_id=0,
            orientation='horizontal',
            parent=self
        )
        # Apply horizontal bar styling (fixed height, border)
        self.bookmark_bar.setFixedHeight(36)
        self.bookmark_bar.setStyleSheet("""
            BookmarkContainer {
                background-color: #E8EEF5;
                border: 2px solid #6B8DC9;
                border-radius: 4px;
            }
        """)
        self.bookmark_bar.navigate_to_path.connect(self.navigate_to_bookmark_folder)
        # BookmarkContainer auto-refreshes in __init__, no manual refresh needed
        main_layout.addWidget(self.bookmark_bar)
        
        # Create splitter for tree (left) and details (right)
        self.main_splitter = QSplitter(Qt.Orientation.Horizontal)
        self.main_splitter.setChildrenCollapsible(True)  # Allow panels to collapse
        self.main_splitter.setStyleSheet("""
            QSplitter::handle {
                background-color: #6090C0;
                width: 3px;
            }
            QSplitter::handle:hover {
                background-color: #D4A017;
            }
        """)
        
        # Create tree panel (left side - folder navigation only)
        tree_panel = self.create_tree_panel()
        tree_panel.setMinimumSize(0, 0)  # Allow panel to shrink for window collapse
        self.main_splitter.addWidget(tree_panel)
        
        # Auto-expand the OneDrive folder
        self.expand_first_onedrive()
        
        # Create details panel (right side - folder contents with details)
        details_panel = self.create_details_panel()
        details_panel.setMinimumSize(0, 0)  # Allow panel to shrink for window collapse
        self.main_splitter.addWidget(details_panel)
        
        # Set initial sizes from saved values or defaults (30% tree, 70% details)
        saved_left = self.panel_widths.get('left_panel', 300)
        saved_middle = self.panel_widths.get('middle_panel', 700)
        self.main_splitter.setSizes([saved_left, saved_middle])
        
        # Connect splitter moved signal to save panel widths
        self.main_splitter.splitterMoved.connect(self.on_splitter_moved)
        
        main_layout.addWidget(self.main_splitter)

    def create_toolbar(self):
        """Create toolbar with file operations"""
        self.toolbar = QToolBar()
        self.toolbar.setMovable(False)
        self._apply_compact_toolbar_style(self.toolbar)
        
        # Add Bookmark (star icon) - first item on toolbar
        add_bookmark_action = QAction("⭐ Add Bookmark", self)
        add_bookmark_action.setToolTip("Add bookmark (Ctrl+D)")
        add_bookmark_action.triggered.connect(self._add_bookmark)
        self.toolbar.addAction(add_bookmark_action)
        
        # Print Directory to Excel
        print_dir_action = QAction("Print Directory", self)
        print_dir_action.setToolTip("Export directory structure to Excel")
        print_dir_action.triggered.connect(self.print_directory_to_excel)
        self.toolbar.addAction(print_dir_action)
        
        # Batch Rename
        batch_rename_action = QAction("Batch Rename", self)
        batch_rename_action.setToolTip("Rename multiple selected files")
        batch_rename_action.triggered.connect(self.batch_rename_files)
        self.toolbar.addAction(batch_rename_action)
        
        # Add spacer to push "Open in Explorer" to the right
        spacer = QWidget()
        spacer.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum)
        spacer.setStyleSheet("background: transparent;")
        self.toolbar.addWidget(spacer)
        
        # Open in Explorer (moved to far right)
        explorer_action = QAction("📂 Open in Explorer", self)
        explorer_action.triggered.connect(self.open_in_explorer)
        self.toolbar.addAction(explorer_action)
        
        return self.toolbar

    def _add_bookmark(self):
        """Show add bookmark dialog (called from toolbar button)"""
        if hasattr(self, 'bookmark_bar'):
            self.bookmark_bar.show_add_bookmark_dialog()

    def _apply_compact_toolbar_style(self, toolbar: QToolBar, locked: bool = False) -> None:
        """Apply toolbar styling with optional orange background when locked."""

        toolbar.setObjectName("fileExplorerToolbar")
        toolbar.setIconSize(QSize(16, 16))
        toolbar.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextOnly)
        
        bg_color = "#FFB366" if locked else "#E3EDFF"  # Orange when locked, blue otherwise
        
        toolbar.setStyleSheet(
            f"""
            QToolBar#fileExplorerToolbar {{
                padding: 0px 6px;
                spacing: 6px;
                min-height: 26px;
                background: {bg_color};
                border: none;
            }}
            QToolBar#fileExplorerToolbar QToolButton {{
                padding: 3px 10px;
                border: 1px solid #4A6FA5;
                border-bottom: 2px solid #3A5A8A;
                border-radius: 4px;
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                                            stop:0 #FFFFFF,
                                            stop:0.45 #F0F5FF,
                                            stop:1 #D0E3FF);
                color: #0A1E5E;
                font-weight: 600;
                font-size: 10px;
            }}
            QToolBar#fileExplorerToolbar QToolButton:hover {{
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                                            stop:0 #FFFFFF,
                                            stop:0.35 #E3EDFF,
                                            stop:1 #B8D0F0);
                border-color: #2563EB;
            }}
            QToolBar#fileExplorerToolbar QToolButton:pressed {{
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                                            stop:0 #B8D0F0,
                                            stop:1 #E3EDFF);
                border: 1px solid #3A5A8A;
                border-top: 2px solid #3A5A8A;
            }}
            """
        )

    def _apply_depth_search_locked_style(self, locked: bool = False) -> None:
        """Apply locked/unlocked style for depth search.
        
        Adds a red border around the main panels when locked.
        """
        if locked:
            self.main_splitter.setStyleSheet("""
                QSplitter::handle {
                    background-color: #6090C0;
                    width: 3px;
                }
                QSplitter {
                    border: 4px solid #DC2626;
                    border-radius: 2px;
                }
            """)
        else:
            self.main_splitter.setStyleSheet("""
                QSplitter::handle {
                    background-color: #6090C0;
                    width: 3px;
                }
                QSplitter::handle:hover {
                    background-color: #D4A017;
                }
            """)

    def _create_nav_button(self, icon: QIcon, tooltip: str, handler) -> QToolButton:
        """Build a breadcrumb-nav button with a clear icon."""

        button = QToolButton()
        button.setAutoRaise(True)
        button.setIcon(icon)
        button.setIconSize(QSize(16, 16))
        button.setToolTip(tooltip)
        button.setCursor(Qt.CursorShape.PointingHandCursor)
        button.setStyleSheet(
            """
            QToolButton {
                border: 1px solid #1A4A94;
                border-radius: 4px;
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    stop:0 #4A7DC4, stop:1 #2A5AA4);
                padding: 2px;
            }
            QToolButton:hover {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    stop:0 #5A8DD4, stop:1 #3A6AB4);
                border: 1px solid #D4A017;
            }
            """
        )
        button.clicked.connect(handler)
        return button
