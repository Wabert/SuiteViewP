"""Standalone FileNav window."""

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
from suiteview.taskbar_launcher.file_explorer_tab import FileExplorerTab

class FileNavWindow(FramelessWindowBase):
    """Standalone File Navigator window with classic Blue & Gold theme.
    
    This window provides the full file explorer experience (multi-tab,
    breadcrumb navigation, bookmarks) in a separate window launched from
    the SuiteView compact bar's [F] button.
    
    Color theme: Blue & Gold â€” same as the SuiteView bar
      - Header gradient: #1E5BA8 â†’ #082B5C  (blue)
      - Accent / border: #D4A017  (gold)
      - Text on headers: #D4A017  (gold on blue)
    """

    # --- Classic Blue & Gold palette (matches SuiteView bar) ---
    _BLUE_START  = "#1E5BA8"   # Blue gradient top
    _BLUE_MID    = "#0D3A7A"   # Blue gradient mid
    _BLUE_END    = "#082B5C"   # Blue gradient bottom
    _BLUE_LIGHT  = "#2A6FBF"   # Lighter blue accent / hover
    _GOLD_PRIMARY = "#D4A017"  # Primary gold (text, accents)
    _GOLD_BRIGHT  = "#FFD700"  # Bright gold (highlights, hover)
    _PANEL_BG     = "#CCE5F8"  # Light blue panel background

    def __init__(self, parent_bar=None):
        guard_app_access("FILENAV")
        self._parent_bar = parent_bar  # Reference to SuiteView compact bar

        # Shared splitter sizes
        self._shared_splitter_sizes = None
        self._syncing_splitter = False

        super().__init__(
            title="FileNav",
            default_size=(1400, 800),
            min_size=(600, 400),
            header_colors=(self._BLUE_START, self._BLUE_MID, self._BLUE_END),
            border_color=self._GOLD_PRIMARY,
            header_title_stretch=0,
        )
        self.setWindowTitle("SuiteView - FileNav")
        self.close_btn.clicked.disconnect()
        self.close_btn.clicked.connect(self.hide)

        # Create initial tab
        self.add_new_tab()

        # Position at center of screen
        screen = QApplication.primaryScreen().availableGeometry()
        w, h = 1400, 800
        x = screen.x() + (screen.width() - w) // 2
        y = screen.y() + (screen.height() - h) // 2
        self.setGeometry(x, y, w, h)

    # ------------------------------------------------------------------
    #  UI Construction
    # ------------------------------------------------------------------
    def header_title_style(self):
        return f"""
            QLabel {{
                color: {self._GOLD_PRIMARY};
                font-size: 18px;
                font-weight: bold;
                font-style: italic;
                background: transparent;
                padding-right: 4px;
            }}
        """

    def header_widgets(self):
        # ====== TOOLS DROPDOWN MENU ======
        self.tools_menu_btn = QPushButton("Tools")
        self.tools_menu_btn.setStyleSheet(f"""
            QPushButton {{
                background: transparent;
                border: none;
                padding: 4px 12px;
                color: {self._GOLD_PRIMARY};
                font-size: 12px;
                font-weight: 600;
            }}
            QPushButton:hover {{
                color: {self._GOLD_BRIGHT};
            }}
            QPushButton::menu-indicator {{
                image: none;
            }}
        """)

        self.tools_menu = QMenu(self)
        self.tools_menu.setStyleSheet(f"""
            QMenu {{
                background-color: {self._BLUE_START};
                border: 1px solid {self._GOLD_PRIMARY};
                border-radius: 4px;
                padding: 4px;
            }}
            QMenu::item {{
                background-color: transparent;
                color: white;
                padding: 6px 20px;
                font-size: 11px;
            }}
            QMenu::item:selected {{
                background-color: #3A7DC8;
            }}
        """)
        self.tools_menu.addAction("Print Directory", self._tools_print_directory)
        self.tools_menu.addAction("Batch Rename", self._tools_batch_rename)
        self.tools_menu_btn.setMenu(self.tools_menu)
        return [self.tools_menu_btn]

    def build_content(self):
        return self._init_ui()

    def _init_ui(self):
        """Build the FileNav window UI with classic Blue & Gold theme."""
        body = QWidget()
        layout = QVBoxLayout(body)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # Global scrollbar styling â€” blue-tinted (matching SuiteView bar)
        self.setStyleSheet("""
            QScrollBar:vertical {
                background: #E0ECFF;
                width: 12px;
                margin: 0;
                border-radius: 6px;
            }
            QScrollBar::handle:vertical {
                background: #1E5BA8;
                min-height: 20px;
                border-radius: 5px;
                margin: 1px;
            }
            QScrollBar::handle:vertical:hover {
                background: #2A6FBF;
            }
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
                height: 0; background: none;
            }
            QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {
                background: none;
            }
            QScrollBar:horizontal {
                background: #E0ECFF;
                height: 12px;
                margin: 0;
                border-radius: 6px;
            }
            QScrollBar::handle:horizontal {
                background: #1E5BA8;
                min-width: 20px;
                border-radius: 5px;
                margin: 1px;
            }
            QScrollBar::handle:horizontal:hover {
                background: #2A6FBF;
            }
            QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {
                width: 0; background: none;
            }
            QScrollBar::add-page:horizontal, QScrollBar::sub-page:horizontal {
                background: none;
            }
        """)

        # ====== TAB WIDGET (Blue & Gold themed tabs â€” same as SuiteView) ======
        self.tab_widget = QTabWidget()
        self.tab_widget.setTabsClosable(True)
        self.tab_widget.setMovable(True)
        self.tab_widget.setDocumentMode(True)
        self.tab_widget.setMinimumSize(0, 0)
        self.tab_widget.setStyleSheet(f"""
            QTabWidget::pane {{
                border: none;
                background: {self._PANEL_BG};
            }}
            QTabBar {{
                background: {self._PANEL_BG};
            }}
            QTabBar::tab {{
                padding: 6px 14px;
                margin-right: 2px;
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    stop:0 #4A7DC4, stop:1 #2A5AA4);
                color: white;
                font-weight: 600;
                font-size: 11px;
                border: 1px solid #1A4A94;
                border-bottom: none;
                border-top-left-radius: 4px;
                border-top-right-radius: 4px;
            }}
            QTabBar::tab:selected {{
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    stop:0 #5A9DE8, stop:1 #3A7DC8);
                border-bottom: 3px solid {self._GOLD_PRIMARY};
                color: white;
            }}
            QTabBar::tab:!selected {{
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    stop:0 #3A6AB4, stop:1 #1A4A94);
                color: #C8DCF8;
            }}
            QTabBar::tab:hover {{
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    stop:0 #5A8DD4, stop:1 #3A6AB4);
            }}
        """)
        self.tab_widget.tabBar().setContextMenuPolicy(
            Qt.ContextMenuPolicy.CustomContextMenu)
        self.tab_widget.tabBar().customContextMenuRequested.connect(
            self._show_tab_bar_context_menu)
        self.tab_widget.tabCloseRequested.connect(self.close_tab)
        self.tab_widget.currentChanged.connect(self._on_tab_switched)

        layout.addWidget(self.tab_widget)

        # ====== FOOTER BAR (Blue & Gold â€” same as SuiteView) ======
        self.footer_bar = QFrame()
        self.footer_bar.setMaximumHeight(24)
        self.footer_bar.setMinimumHeight(0)
        self.footer_bar.setStyleSheet(f"""
            QFrame {{
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    stop:0 {self._BLUE_START}, stop:0.5 {self._BLUE_MID},
                    stop:1 {self._BLUE_END});
                border: none;
                border-top: 1px solid {self._GOLD_PRIMARY};
            }}
        """)
        footer_layout = QHBoxLayout(self.footer_bar)
        footer_layout.setContentsMargins(12, 2, 12, 2)
        footer_layout.setSpacing(8)

        self.footer_status = QLabel("Ready")
        self.footer_status.setStyleSheet(f"""
            QLabel {{
                color: {self._GOLD_PRIMARY};
                font-size: 15px;
                background: transparent;
            }}
        """)
        footer_layout.addWidget(self.footer_status)

        # Register global footer callback so bookmark hover shows path in this footer
        set_footer_status_callback(
            lambda path: self.footer_status.setText(path if path else "Ready")
        )
        footer_layout.addStretch()

        self.footer_size = QLabel("")
        self.footer_size.setStyleSheet("""
            QLabel {
                color: #666666;
                font-size: 10px;
                background: transparent;
            }
        """)
        footer_layout.addWidget(self.footer_size)

        layout.addWidget(self.footer_bar)
        return body

    # ------------------------------------------------------------------
    #  Tab management
    # ------------------------------------------------------------------
    @requires_app_access("FILENAV")
    def add_new_tab(self, path=None, title=None):
        """Add a new file explorer tab."""
        tab = FileExplorerTab(initial_path=path)
        tab.path_changed.connect(
            lambda p, t=tab: self._update_tab_title(t, p))

        display_title = title or "OneDrive"
        index = self.tab_widget.addTab(tab, display_title)
        self.tab_widget.setCurrentIndex(index)
        self._style_close_button(index)
        self._connect_tab_splitter(tab)
        return tab

    def _connect_tab_splitter(self, tab):
        """Connect a tab's splitter to shared size management."""
        if hasattr(tab, 'main_splitter'):
            tab.main_splitter.splitterMoved.connect(
                lambda: self._on_tab_splitter_moved(tab))
            if self._shared_splitter_sizes:
                tab.main_splitter.setSizes(self._shared_splitter_sizes)

    def _on_tab_splitter_moved(self, source_tab):
        """Sync splitter sizes across all tabs."""
        if self._syncing_splitter:
            return
        self._syncing_splitter = True
        try:
            sizes = source_tab.main_splitter.sizes()
            self._shared_splitter_sizes = sizes
            for i in range(self.tab_widget.count()):
                other = self.tab_widget.widget(i)
                if other is not source_tab and hasattr(other, 'main_splitter'):
                    other.main_splitter.setSizes(sizes)
        finally:
            self._syncing_splitter = False

    def close_tab(self, index):
        """Close a tab (keep at least one)."""
        if self.tab_widget.count() > 1:
            widget = self.tab_widget.widget(index)

            # Disconnect signals to prevent crashes during cleanup
            if widget:
                try:
                    if hasattr(widget, 'depth_level_combo'):
                        widget.depth_level_combo.currentTextChanged.disconnect()
                    if hasattr(widget, 'path_changed'):
                        widget.path_changed.disconnect()
                    if hasattr(widget, 'details_search'):
                        widget.details_search.textChanged.disconnect()
                    if hasattr(widget, 'depth_search_enabled') and widget.depth_search_enabled:
                        widget.depth_search_enabled = False
                        widget.depth_search_locked = False
                        widget.depth_search_active_results = None
                    # Unregister BookmarkContainers from global registry
                    if hasattr(widget, 'bookmark_bar'):
                        BookmarkContainerRegistry.unregister(
                            widget.bookmark_bar.bar_id, widget.bookmark_bar)
                    if hasattr(widget, 'bookmark_container'):
                        BookmarkContainerRegistry.unregister(
                            widget.bookmark_container.bar_id, widget.bookmark_container)
                except Exception as e:
                    logger.error(f"Error during FileNav tab cleanup: {e}")

            self.tab_widget.removeTab(index)
            if widget:
                widget.deleteLater()
        elif self.tab_widget.count() == 1:
            # Last tab: just reset it
            tab = self.tab_widget.widget(0)
            if hasattr(tab, 'go_to_onedrive_home'):
                tab.go_to_onedrive_home()
            self.tab_widget.setTabText(0, "OneDrive")

    def _update_tab_title(self, tab, path):
        """Update tab title when path changes."""
        idx = self.tab_widget.indexOf(tab)
        if idx >= 0:
            p = Path(path)
            name = p.name or str(p)
            self.tab_widget.setTabText(idx, name)
            self.tab_widget.setTabToolTip(idx, str(p))

    def _on_tab_switched(self, index):
        """Handle tab switch â€” wrapped in try/except for crash diagnostics."""
        try:
            widget = self.tab_widget.widget(index)
            if widget and hasattr(widget, 'current_details_folder'):
                folder = widget.current_details_folder
                if folder:
                    self.footer_status.setText(folder)
        except Exception as e:
            tb = traceback.format_exc()
            logger.error(f"FileNav tab switch error (tab {index}): {e}\n{tb}")
            # Also write to crash log for diagnostics
            try:
                crash_file = profile_path('filenav_crash.log')
                crash_file.parent.mkdir(parents=True, exist_ok=True)
                with open(crash_file, 'a') as f:
                    f.write(f"\n{'='*60}\n")
                    f.write(f"FileNav tab switch crash at {datetime.now()}\n")
                    f.write(f"Tab index: {index}\n")
                    f.write(tb)
                    f.write(f"{'='*60}\n")
            except Exception:
                logger.debug("Could not write FileNav tab switch crash log", exc_info=True)

    def get_current_tab(self):
        """Get currently active tab."""
        return self.tab_widget.currentWidget()

    # ------------------------------------------------------------------
    #  Tools menu actions
    # ------------------------------------------------------------------
    def _tools_print_directory(self):
        """Delegate Print Directory to current tab."""
        current_tab = self.get_current_tab()
        if current_tab and hasattr(current_tab, 'print_directory_to_excel'):
            current_tab.print_directory_to_excel()

    def _tools_batch_rename(self):
        """Delegate Batch Rename to current tab."""
        current_tab = self.get_current_tab()
        if current_tab and hasattr(current_tab, 'batch_rename_files'):
            current_tab.batch_rename_files()

    def _show_tab_bar_context_menu(self, pos):
        """Tab bar right-click menu."""
        tab_bar = self.tab_widget.tabBar()
        index = tab_bar.tabAt(pos)
        menu = QMenu(self)
        menu.setStyleSheet(f"""
            QMenu {{
                background-color: {self._BLUE_START};
                border: 1px solid {self._GOLD_PRIMARY};
                border-radius: 4px;
                padding: 4px;
            }}
            QMenu::item {{
                background-color: transparent;
                color: {self._GOLD_PRIMARY};
                padding: 6px 20px;
                font-size: 11px;
            }}
            QMenu::item:selected {{
                background-color: {self._GOLD_BRIGHT};
            }}
        """)
        if index >= 0:
            menu.addAction("Duplicate Tab",
                           lambda: self._duplicate_tab(index))
        menu.addAction("New Tab", self.add_new_tab)
        menu.exec(tab_bar.mapToGlobal(pos))

    def _duplicate_tab(self, index):
        """Duplicate the given tab."""
        source = self.tab_widget.widget(index)
        if source and hasattr(source, 'current_details_folder'):
            folder = source.current_details_folder
            title = self.tab_widget.tabText(index)
            self.add_new_tab(path=folder, title=title)

    def _style_close_button(self, index):
        """Replace the platform-drawn close button with a QToolButton showing a subtle gold âœ•.

        Qt's built-in QTabBar close button is rendered by the platform style engine and
        ignores CSS color / icon overrides â€” so we swap it out entirely via setTabButton().

        Uses the same approach as SuiteViewTaskbar (QToolButton + tabCloseRequested)
        which is proven to work reliably across all tabs.
        """
        tab_bar = self.tab_widget.tabBar()

        close_btn = QToolButton(tab_bar)
        close_btn.setAutoRaise(True)
        close_btn.setText("âœ•")
        close_btn.setToolTip("Close Tab")
        close_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        close_btn.setStyleSheet(f"""
            QToolButton {{
                background: transparent;
                color: {self._GOLD_PRIMARY};
                border: none;
                font-size: 12px;
                font-weight: 700;
                padding: 0px;
                min-width: 14px;
            }}
            QToolButton:hover {{
                color: {self._GOLD_BRIGHT};
            }}
        """)
        close_btn.clicked.connect(lambda _: self._emit_close_for_button(close_btn))
        tab_bar.setTabButton(index, QTabBar.ButtonPosition.RightSide, close_btn)

    def _emit_close_for_button(self, button):
        """Map custom close button clicks to the correct tab index."""
        tab_bar = self.tab_widget.tabBar()
        for idx in range(tab_bar.count()):
            if tab_bar.tabButton(idx, QTabBar.ButtonPosition.RightSide) is button:
                self.tab_widget.tabCloseRequested.emit(idx)
                return

    def resizeEvent(self, event):
        """Collapse/expand FileNav content and update its footer size label."""
        super().resizeEvent(event)
        w, h = self.width(), self.height()

        if hasattr(self, 'footer_bar') and hasattr(self, 'tab_widget'):
            if h < 70:
                self.footer_bar.hide()
                self.tab_widget.hide()
            elif h < 100:
                self.footer_bar.hide()
                self.tab_widget.show()
            else:
                self.footer_bar.show()
                self.tab_widget.show()

        # Update footer size label
        if hasattr(self, 'footer_size'):
            self.footer_size.setText(f"{w} Ã— {h}")
