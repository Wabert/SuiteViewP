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
from suiteview.taskbar_launcher.collaborators import TaskbarState
from suiteview.ui.widgets.window_state import NativeMinimizeMixin

logger = logging.getLogger(__name__)
from suiteview.taskbar_launcher.taskbar_modes import TaskbarModes
from suiteview.taskbar_launcher.taskbar_system import AppLauncher, SystemTray
from suiteview.taskbar_launcher.taskbar_tabs import TaskbarTabs
from suiteview.taskbar_launcher.taskbar_ui import TaskbarChrome


class SuiteViewTaskbar(NativeMinimizeMixin, QWidget):
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
        self.state = TaskbarState(
            launcher_access=access,
            restore_message=activation_message(),
        )
        self.chrome = TaskbarChrome(self, self.state, self)
        self.modes = TaskbarModes(self, self.state, self.chrome, self)
        self.tabs = TaskbarTabs(self, self.state, self.chrome, self)
        self.system_tray = SystemTray(self, self.state, self.chrome, self)
        self.app_launcher = AppLauncher(self, self.state, self.chrome, self)
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
        
        # PolView is created lazily the first time it is requested. Keeping it
        # lazy avoids a hidden native tool window flashing during taskbar startup.
        logger.info("PolView will be created on first use")
        
        logger.info("Calling init_ui...")
        self.chrome.init_ui()
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


def _delegate(collaborator_name: str, collaborator_type, method_name: str):
    def wrapper(self, *args, **kwargs):
        try:
            collaborator = object.__getattribute__(self, collaborator_name)
        except (AttributeError, RuntimeError):
            collaborator = None
        if collaborator is not None:
            return getattr(collaborator, method_name)(*args, **kwargs)
        return getattr(collaborator_type, method_name)(self, *args, **kwargs)

    wrapper.__name__ = method_name
    return wrapper


for _name in {
    "init_ui",
    "_document_pending_keyboard_shortcuts",
}:
    setattr(SuiteViewTaskbar, _name, _delegate("chrome", TaskbarChrome, _name))

for _name in {
    "show_tab_bar_context_menu",
    "duplicate_tab",
    "add_new_tab",
    "_connect_tab_splitter",
    "_on_tab_splitter_moved",
    "close_tab",
    "update_tab_title",
    "get_current_tab",
    "navigate_to_bookmark_folder",
    "_header_add_bookmark",
    "_header_print_directory",
    "_header_export_details",
    "_header_open_shortcuts_dialog",
    "_header_batch_rename",
    "_header_open_in_explorer",
    "update_footer_status",
}:
    setattr(SuiteViewTaskbar, _name, _delegate("tabs", TaskbarTabs, _name))

for _name in {
    "_toggle_maximize",
    "_toggle_compact_mode",
    "_enter_floating_mode",
    "_exit_floating_mode",
    "_enter_compact_mode",
    "_register_appbar",
    "_notify_docking_failure",
    "_unregister_appbar",
    "_exit_compact_mode",
    "mousePressEvent",
    "_show_bookmark_bars_popup",
    "_on_popup_bookmark_activated",
    "_open_file_nav_at",
    "mouseMoveEvent",
    "mouseReleaseEvent",
    "mouseDoubleClickEvent",
    "paintEvent",
}:
    setattr(SuiteViewTaskbar, _name, _delegate("modes", TaskbarModes, _name))

for _name in {
    "_apply_permissions",
    "_refresh_permissions",
    "_build_suiteview_icon",
    "_create_icon_pixmap",
    "_setup_system_tray",
    "_connect_screen_change_handlers",
    "_connect_screen_signals",
    "_on_screen_added",
    "_schedule_bar_refresh",
    "_run_scheduled_bar_refresh",
    "_refresh_bar_position",
    "_move_floating_bar_to_current_screen",
    "_on_tray_activated",
    "_show_from_tray",
    "nativeEvent",
    "_redock_appbar",
    "_apply_toolwindow_style",
    "_hide_to_tray",
    "_quit_application",
    "_close_windows_for_quit",
    "_take_quick_screenshot",
    "_capture_active_window",
    "_do_capture_excluding_suiteview",
    "_open_agent_chat",
    "_open_mainframe",
    "_open_screenshot",
    "_open_email_attachments",
    "_open_polview",
    "_wire_polview_illustrator",
    "_wire_illustration_polview",
    "_get_polview_window",
    "_polview_btn_clicked",
    "_compact_policy",
    "_compact_region",
    "_clear_compact_policy",
    "_open_polview_with_policy",
    "_abrquote_btn_clicked",
    "_illustration_btn_clicked",
    "_launch_illustration_with_policy",
    "_launch_polview_with_policy",
    "_open_audit",
    "_open_abrquote",
    "_open_illustration",
    "_open_rate_manager",
    "_open_administrator",
    "_open_db2_table_check",
    "_open_file_nav",
    "_open_app_data_location",
    "_toggle_scratchpad_window",
    "_toggle_file_open_history",
    "_bring_to_front",
    "_setup_child_window",
    "_add_resize_grips",
    "resizeEvent",
}:
    setattr(SuiteViewTaskbar, _name, _delegate("system_tray", SystemTray, _name))

for _name in {
    "_take_quick_screenshot",
    "_capture_active_window",
    "_do_capture_excluding_suiteview",
    "_open_agent_chat",
    "_open_mainframe",
    "_open_screenshot",
    "_open_email_attachments",
    "_open_polview",
    "_wire_polview_illustrator",
    "_wire_illustration_polview",
    "_get_polview_window",
    "_polview_btn_clicked",
    "_compact_policy",
    "_compact_region",
    "_clear_compact_policy",
    "_open_polview_with_policy",
    "_abrquote_btn_clicked",
    "_illustration_btn_clicked",
    "_launch_illustration_with_policy",
    "_launch_polview_with_policy",
    "_open_audit",
    "_open_abrquote",
    "_open_illustration",
    "_open_rate_manager",
    "_open_administrator",
    "_open_db2_table_check",
    "_open_file_nav",
    "_open_app_data_location",
    "_toggle_scratchpad_window",
    "_toggle_file_open_history",
    "_bring_to_front",
    "_setup_child_window",
}:
    setattr(SuiteViewTaskbar, _name, _delegate("app_launcher", AppLauncher, _name))
