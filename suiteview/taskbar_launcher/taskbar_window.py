"""SuiteView main application window class."""

import logging

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QWidget,
)

from suiteview.core.access_control import (
    get_access,
)
from suiteview.core.single_instance import activation_message
from suiteview.taskbar_launcher.app_launchers import register_default_launchers
from suiteview.ui.widgets.window_state import NativeMinimizeMixin

logger = logging.getLogger(__name__)
from suiteview.taskbar_launcher.taskbar_modes import TaskbarModesMixin
from suiteview.taskbar_launcher.taskbar_system import TaskbarSystemMixin
from suiteview.taskbar_launcher.taskbar_tabs import TaskbarTabsMixin
from suiteview.taskbar_launcher.taskbar_ui import TaskbarUiMixin


class SuiteViewTaskbar(TaskbarSystemMixin, TaskbarUiMixin, TaskbarTabsMixin, TaskbarModesMixin, NativeMinimizeMixin, QWidget):
    """
    SuiteView main application window and tool launcher.
    Features:
    - Multiple tabs for different folders
    - Breadcrumb navigation per tab
    - New tab, close tab, pin tab functionality
    - All FileExplorerCore features in each tab
    """
    
    _restore_requested = pyqtSignal()

    def __init__(self):
        access = get_access(refresh=True)
        register_default_launchers()
        super().__init__()
        self._permission_actions = []
        self._launcher_access = access
        self._restore_message = activation_message()
        self._restore_requested.connect(
            self._show_from_tray, Qt.ConnectionType.QueuedConnection)
        
        # Frameless window setup
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowMinMaxButtonsHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, False)
        
        # Set minimum size to allow collapsing to just header bar (38 + margins)
        # Min width: SuiteView label + screenshot btn + Tools + window buttons
        self.setMinimumSize(330, 40)
        
        # Enable mouse tracking for resize cursor updates
        self.setMouseTracking(True)
        
        # Drag tracking
        self._drag_pos = None
        self._is_maximized = False
        self._is_compact_mode = False  # Will be set True after init
        self._is_floating_mode = False  # Undocked floating mini-bar mode
        self._stored_geometry = None
        self._compact_bar_pos = None   # Last known compact bar position
        self._appbar_registered = False  # True when registered as Windows AppBar
        self._hidden_to_tray = False     # True while minimised to the system tray
        self._bar_refresh_pending = False
        self._ignore_screen_events_until = 0.0
        self._screen_signal_refs = []
        
        # Resize edge detection
        self._resize_margin = 6
        self._resizing = False
        self._resize_edge = None
        self._resize_start_pos = None
        self._start_geometry = None
        
        # Store references to opened app windows
        self.mainframe_window = None
        self.email_attachments_window = None
        self.screenshot_window = None
        self.polview_window = None
        self.audit_window = None
        self.db2_check_window = None
        self.ratemanager_window = None
        self.administrator_window = None
        self.abrquote_window = None
        self.illustration_window = None
        self.file_nav_window = None
        self.scratchpad_window = None
        self.agent_chat_window = None

        # PolView is created lazily the first time it is requested. Keeping it
        # lazy avoids a hidden native tool window flashing during taskbar startup.
        logger.info("PolView will be created on first use")

        # Shared splitter sizes across all tabs - loaded from saved settings
        self._shared_splitter_sizes = None  # Will be set from first tab or saved
        self._syncing_splitter = False  # Prevent recursive updates
        
        logger.info("Calling init_ui...")
        self.init_ui()
        logger.info("init_ui complete")
        
        # Add resize grips to corners
        self._add_resize_grips()
        
        # Setup system tray
        logger.info("Setting up system tray...")
        self._setup_system_tray()
        logger.info("System tray setup complete")

        self._connect_screen_change_handlers()

        # Create initial tab
        if access.allows_app("FILENAV"):
            self.add_new_tab()
        
        # Start in compact mini-bar mode at bottom-right corner
        self._enter_compact_mode(initial=True)
        self._apply_permissions(access)
