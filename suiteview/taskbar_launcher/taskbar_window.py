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

    def init_ui(self, *args, **kwargs):
        try:
            collaborator = object.__getattribute__(self, "chrome")
        except (AttributeError, RuntimeError):
            collaborator = None
        if collaborator is not None:
            return collaborator.init_ui(*args, **kwargs)
        return TaskbarChrome.init_ui(self, *args, **kwargs)

    def _document_pending_keyboard_shortcuts(self, *args, **kwargs):
        try:
            collaborator = object.__getattribute__(self, "chrome")
        except (AttributeError, RuntimeError):
            collaborator = None
        if collaborator is not None:
            return collaborator._document_pending_keyboard_shortcuts(*args, **kwargs)
        return TaskbarChrome._document_pending_keyboard_shortcuts(self, *args, **kwargs)

    def show_tab_bar_context_menu(self, *args, **kwargs):
        try:
            collaborator = object.__getattribute__(self, "tabs")
        except (AttributeError, RuntimeError):
            collaborator = None
        if collaborator is not None:
            return collaborator.show_tab_bar_context_menu(*args, **kwargs)
        return TaskbarTabs.show_tab_bar_context_menu(self, *args, **kwargs)

    def duplicate_tab(self, *args, **kwargs):
        try:
            collaborator = object.__getattribute__(self, "tabs")
        except (AttributeError, RuntimeError):
            collaborator = None
        if collaborator is not None:
            return collaborator.duplicate_tab(*args, **kwargs)
        return TaskbarTabs.duplicate_tab(self, *args, **kwargs)

    def add_new_tab(self, *args, **kwargs):
        try:
            collaborator = object.__getattribute__(self, "tabs")
        except (AttributeError, RuntimeError):
            collaborator = None
        if collaborator is not None:
            return collaborator.add_new_tab(*args, **kwargs)
        return TaskbarTabs.add_new_tab(self, *args, **kwargs)

    def _connect_tab_splitter(self, *args, **kwargs):
        try:
            collaborator = object.__getattribute__(self, "tabs")
        except (AttributeError, RuntimeError):
            collaborator = None
        if collaborator is not None:
            return collaborator._connect_tab_splitter(*args, **kwargs)
        return TaskbarTabs._connect_tab_splitter(self, *args, **kwargs)

    def _on_tab_splitter_moved(self, *args, **kwargs):
        try:
            collaborator = object.__getattribute__(self, "tabs")
        except (AttributeError, RuntimeError):
            collaborator = None
        if collaborator is not None:
            return collaborator._on_tab_splitter_moved(*args, **kwargs)
        return TaskbarTabs._on_tab_splitter_moved(self, *args, **kwargs)

    def close_tab(self, *args, **kwargs):
        try:
            collaborator = object.__getattribute__(self, "tabs")
        except (AttributeError, RuntimeError):
            collaborator = None
        if collaborator is not None:
            return collaborator.close_tab(*args, **kwargs)
        return TaskbarTabs.close_tab(self, *args, **kwargs)

    def update_tab_title(self, *args, **kwargs):
        try:
            collaborator = object.__getattribute__(self, "tabs")
        except (AttributeError, RuntimeError):
            collaborator = None
        if collaborator is not None:
            return collaborator.update_tab_title(*args, **kwargs)
        return TaskbarTabs.update_tab_title(self, *args, **kwargs)

    def get_current_tab(self, *args, **kwargs):
        try:
            collaborator = object.__getattribute__(self, "tabs")
        except (AttributeError, RuntimeError):
            collaborator = None
        if collaborator is not None:
            return collaborator.get_current_tab(*args, **kwargs)
        return TaskbarTabs.get_current_tab(self, *args, **kwargs)

    def navigate_to_bookmark_folder(self, *args, **kwargs):
        try:
            collaborator = object.__getattribute__(self, "tabs")
        except (AttributeError, RuntimeError):
            collaborator = None
        if collaborator is not None:
            return collaborator.navigate_to_bookmark_folder(*args, **kwargs)
        return TaskbarTabs.navigate_to_bookmark_folder(self, *args, **kwargs)

    def _header_add_bookmark(self, *args, **kwargs):
        try:
            collaborator = object.__getattribute__(self, "tabs")
        except (AttributeError, RuntimeError):
            collaborator = None
        if collaborator is not None:
            return collaborator._header_add_bookmark(*args, **kwargs)
        return TaskbarTabs._header_add_bookmark(self, *args, **kwargs)

    def _header_print_directory(self, *args, **kwargs):
        try:
            collaborator = object.__getattribute__(self, "tabs")
        except (AttributeError, RuntimeError):
            collaborator = None
        if collaborator is not None:
            return collaborator._header_print_directory(*args, **kwargs)
        return TaskbarTabs._header_print_directory(self, *args, **kwargs)

    def _header_export_details(self, *args, **kwargs):
        try:
            collaborator = object.__getattribute__(self, "tabs")
        except (AttributeError, RuntimeError):
            collaborator = None
        if collaborator is not None:
            return collaborator._header_export_details(*args, **kwargs)
        return TaskbarTabs._header_export_details(self, *args, **kwargs)

    def _header_open_shortcuts_dialog(self, *args, **kwargs):
        try:
            collaborator = object.__getattribute__(self, "tabs")
        except (AttributeError, RuntimeError):
            collaborator = None
        if collaborator is not None:
            return collaborator._header_open_shortcuts_dialog(*args, **kwargs)
        return TaskbarTabs._header_open_shortcuts_dialog(self, *args, **kwargs)

    def _header_batch_rename(self, *args, **kwargs):
        try:
            collaborator = object.__getattribute__(self, "tabs")
        except (AttributeError, RuntimeError):
            collaborator = None
        if collaborator is not None:
            return collaborator._header_batch_rename(*args, **kwargs)
        return TaskbarTabs._header_batch_rename(self, *args, **kwargs)

    def _header_open_in_explorer(self, *args, **kwargs):
        try:
            collaborator = object.__getattribute__(self, "tabs")
        except (AttributeError, RuntimeError):
            collaborator = None
        if collaborator is not None:
            return collaborator._header_open_in_explorer(*args, **kwargs)
        return TaskbarTabs._header_open_in_explorer(self, *args, **kwargs)

    def update_footer_status(self, *args, **kwargs):
        try:
            collaborator = object.__getattribute__(self, "tabs")
        except (AttributeError, RuntimeError):
            collaborator = None
        if collaborator is not None:
            return collaborator.update_footer_status(*args, **kwargs)
        return TaskbarTabs.update_footer_status(self, *args, **kwargs)

    def _toggle_maximize(self, *args, **kwargs):
        try:
            collaborator = object.__getattribute__(self, "modes")
        except (AttributeError, RuntimeError):
            collaborator = None
        if collaborator is not None:
            return collaborator._toggle_maximize(*args, **kwargs)
        return TaskbarModes._toggle_maximize(self, *args, **kwargs)

    def _toggle_compact_mode(self, *args, **kwargs):
        try:
            collaborator = object.__getattribute__(self, "modes")
        except (AttributeError, RuntimeError):
            collaborator = None
        if collaborator is not None:
            return collaborator._toggle_compact_mode(*args, **kwargs)
        return TaskbarModes._toggle_compact_mode(self, *args, **kwargs)

    def _enter_floating_mode(self, *args, **kwargs):
        try:
            collaborator = object.__getattribute__(self, "modes")
        except (AttributeError, RuntimeError):
            collaborator = None
        if collaborator is not None:
            return collaborator._enter_floating_mode(*args, **kwargs)
        return TaskbarModes._enter_floating_mode(self, *args, **kwargs)

    def _exit_floating_mode(self, *args, **kwargs):
        try:
            collaborator = object.__getattribute__(self, "modes")
        except (AttributeError, RuntimeError):
            collaborator = None
        if collaborator is not None:
            return collaborator._exit_floating_mode(*args, **kwargs)
        return TaskbarModes._exit_floating_mode(self, *args, **kwargs)

    def _enter_compact_mode(self, *args, **kwargs):
        try:
            collaborator = object.__getattribute__(self, "modes")
        except (AttributeError, RuntimeError):
            collaborator = None
        if collaborator is not None:
            return collaborator._enter_compact_mode(*args, **kwargs)
        return TaskbarModes._enter_compact_mode(self, *args, **kwargs)

    def _register_appbar(self, *args, **kwargs):
        try:
            collaborator = object.__getattribute__(self, "modes")
        except (AttributeError, RuntimeError):
            collaborator = None
        if collaborator is not None:
            return collaborator._register_appbar(*args, **kwargs)
        return TaskbarModes._register_appbar(self, *args, **kwargs)

    def _notify_docking_failure(self, *args, **kwargs):
        try:
            collaborator = object.__getattribute__(self, "modes")
        except (AttributeError, RuntimeError):
            collaborator = None
        if collaborator is not None:
            return collaborator._notify_docking_failure(*args, **kwargs)
        return TaskbarModes._notify_docking_failure(self, *args, **kwargs)

    def _unregister_appbar(self, *args, **kwargs):
        try:
            collaborator = object.__getattribute__(self, "modes")
        except (AttributeError, RuntimeError):
            collaborator = None
        if collaborator is not None:
            return collaborator._unregister_appbar(*args, **kwargs)
        return TaskbarModes._unregister_appbar(self, *args, **kwargs)

    def _exit_compact_mode(self, *args, **kwargs):
        try:
            collaborator = object.__getattribute__(self, "modes")
        except (AttributeError, RuntimeError):
            collaborator = None
        if collaborator is not None:
            return collaborator._exit_compact_mode(*args, **kwargs)
        return TaskbarModes._exit_compact_mode(self, *args, **kwargs)

    def mousePressEvent(self, *args, **kwargs):
        try:
            collaborator = object.__getattribute__(self, "modes")
        except (AttributeError, RuntimeError):
            collaborator = None
        if collaborator is not None:
            return collaborator.mousePressEvent(*args, **kwargs)
        return TaskbarModes.mousePressEvent(self, *args, **kwargs)

    def _show_bookmark_bars_popup(self, *args, **kwargs):
        try:
            collaborator = object.__getattribute__(self, "modes")
        except (AttributeError, RuntimeError):
            collaborator = None
        if collaborator is not None:
            return collaborator._show_bookmark_bars_popup(*args, **kwargs)
        return TaskbarModes._show_bookmark_bars_popup(self, *args, **kwargs)

    def _on_popup_bookmark_activated(self, *args, **kwargs):
        try:
            collaborator = object.__getattribute__(self, "modes")
        except (AttributeError, RuntimeError):
            collaborator = None
        if collaborator is not None:
            return collaborator._on_popup_bookmark_activated(*args, **kwargs)
        return TaskbarModes._on_popup_bookmark_activated(self, *args, **kwargs)

    def _open_file_nav_at(self, *args, **kwargs):
        try:
            collaborator = object.__getattribute__(self, "modes")
        except (AttributeError, RuntimeError):
            collaborator = None
        if collaborator is not None:
            return collaborator._open_file_nav_at(*args, **kwargs)
        return TaskbarModes._open_file_nav_at(self, *args, **kwargs)

    def mouseMoveEvent(self, *args, **kwargs):
        try:
            collaborator = object.__getattribute__(self, "modes")
        except (AttributeError, RuntimeError):
            collaborator = None
        if collaborator is not None:
            return collaborator.mouseMoveEvent(*args, **kwargs)
        return TaskbarModes.mouseMoveEvent(self, *args, **kwargs)

    def mouseReleaseEvent(self, *args, **kwargs):
        try:
            collaborator = object.__getattribute__(self, "modes")
        except (AttributeError, RuntimeError):
            collaborator = None
        if collaborator is not None:
            return collaborator.mouseReleaseEvent(*args, **kwargs)
        return TaskbarModes.mouseReleaseEvent(self, *args, **kwargs)

    def mouseDoubleClickEvent(self, *args, **kwargs):
        try:
            collaborator = object.__getattribute__(self, "modes")
        except (AttributeError, RuntimeError):
            collaborator = None
        if collaborator is not None:
            return collaborator.mouseDoubleClickEvent(*args, **kwargs)
        return TaskbarModes.mouseDoubleClickEvent(self, *args, **kwargs)

    def paintEvent(self, *args, **kwargs):
        try:
            collaborator = object.__getattribute__(self, "modes")
        except (AttributeError, RuntimeError):
            collaborator = None
        if collaborator is not None:
            return collaborator.paintEvent(*args, **kwargs)
        return TaskbarModes.paintEvent(self, *args, **kwargs)

    def _apply_permissions(self, *args, **kwargs):
        try:
            collaborator = object.__getattribute__(self, "system_tray")
        except (AttributeError, RuntimeError):
            collaborator = None
        if collaborator is not None:
            return collaborator._apply_permissions(*args, **kwargs)
        return SystemTray._apply_permissions(self, *args, **kwargs)

    def _refresh_permissions(self, *args, **kwargs):
        try:
            collaborator = object.__getattribute__(self, "system_tray")
        except (AttributeError, RuntimeError):
            collaborator = None
        if collaborator is not None:
            return collaborator._refresh_permissions(*args, **kwargs)
        return SystemTray._refresh_permissions(self, *args, **kwargs)

    def _build_suiteview_icon(self, *args, **kwargs):
        try:
            collaborator = object.__getattribute__(self, "system_tray")
        except (AttributeError, RuntimeError):
            collaborator = None
        if collaborator is not None:
            return collaborator._build_suiteview_icon(*args, **kwargs)
        return SystemTray._build_suiteview_icon(self, *args, **kwargs)

    def _create_icon_pixmap(self, *args, **kwargs):
        try:
            collaborator = object.__getattribute__(self, "system_tray")
        except (AttributeError, RuntimeError):
            collaborator = None
        if collaborator is not None:
            return collaborator._create_icon_pixmap(*args, **kwargs)
        return SystemTray._create_icon_pixmap(self, *args, **kwargs)

    def _setup_system_tray(self, *args, **kwargs):
        try:
            collaborator = object.__getattribute__(self, "system_tray")
        except (AttributeError, RuntimeError):
            collaborator = None
        if collaborator is not None:
            return collaborator._setup_system_tray(*args, **kwargs)
        return SystemTray._setup_system_tray(self, *args, **kwargs)

    def _connect_screen_change_handlers(self, *args, **kwargs):
        try:
            collaborator = object.__getattribute__(self, "system_tray")
        except (AttributeError, RuntimeError):
            collaborator = None
        if collaborator is not None:
            return collaborator._connect_screen_change_handlers(*args, **kwargs)
        return SystemTray._connect_screen_change_handlers(self, *args, **kwargs)

    def _connect_screen_signals(self, *args, **kwargs):
        try:
            collaborator = object.__getattribute__(self, "system_tray")
        except (AttributeError, RuntimeError):
            collaborator = None
        if collaborator is not None:
            return collaborator._connect_screen_signals(*args, **kwargs)
        return SystemTray._connect_screen_signals(self, *args, **kwargs)

    def _on_screen_added(self, *args, **kwargs):
        try:
            collaborator = object.__getattribute__(self, "system_tray")
        except (AttributeError, RuntimeError):
            collaborator = None
        if collaborator is not None:
            return collaborator._on_screen_added(*args, **kwargs)
        return SystemTray._on_screen_added(self, *args, **kwargs)

    def _schedule_bar_refresh(self, *args, **kwargs):
        try:
            collaborator = object.__getattribute__(self, "system_tray")
        except (AttributeError, RuntimeError):
            collaborator = None
        if collaborator is not None:
            return collaborator._schedule_bar_refresh(*args, **kwargs)
        return SystemTray._schedule_bar_refresh(self, *args, **kwargs)

    def _run_scheduled_bar_refresh(self, *args, **kwargs):
        try:
            collaborator = object.__getattribute__(self, "system_tray")
        except (AttributeError, RuntimeError):
            collaborator = None
        if collaborator is not None:
            return collaborator._run_scheduled_bar_refresh(*args, **kwargs)
        return SystemTray._run_scheduled_bar_refresh(self, *args, **kwargs)

    def _refresh_bar_position(self, *args, **kwargs):
        try:
            collaborator = object.__getattribute__(self, "system_tray")
        except (AttributeError, RuntimeError):
            collaborator = None
        if collaborator is not None:
            return collaborator._refresh_bar_position(*args, **kwargs)
        return SystemTray._refresh_bar_position(self, *args, **kwargs)

    def _move_floating_bar_to_current_screen(self, *args, **kwargs):
        try:
            collaborator = object.__getattribute__(self, "system_tray")
        except (AttributeError, RuntimeError):
            collaborator = None
        if collaborator is not None:
            return collaborator._move_floating_bar_to_current_screen(*args, **kwargs)
        return SystemTray._move_floating_bar_to_current_screen(self, *args, **kwargs)

    def _on_tray_activated(self, *args, **kwargs):
        try:
            collaborator = object.__getattribute__(self, "system_tray")
        except (AttributeError, RuntimeError):
            collaborator = None
        if collaborator is not None:
            return collaborator._on_tray_activated(*args, **kwargs)
        return SystemTray._on_tray_activated(self, *args, **kwargs)

    def _show_from_tray(self, *args, **kwargs):
        try:
            collaborator = object.__getattribute__(self, "system_tray")
        except (AttributeError, RuntimeError):
            collaborator = None
        if collaborator is not None:
            return collaborator._show_from_tray(*args, **kwargs)
        return SystemTray._show_from_tray(self, *args, **kwargs)

    def nativeEvent(self, *args, **kwargs):
        try:
            collaborator = object.__getattribute__(self, "system_tray")
        except (AttributeError, RuntimeError):
            collaborator = None
        if collaborator is not None:
            return collaborator.nativeEvent(*args, **kwargs)
        return SystemTray.nativeEvent(self, *args, **kwargs)

    def _redock_appbar(self, *args, **kwargs):
        try:
            collaborator = object.__getattribute__(self, "system_tray")
        except (AttributeError, RuntimeError):
            collaborator = None
        if collaborator is not None:
            return collaborator._redock_appbar(*args, **kwargs)
        return SystemTray._redock_appbar(self, *args, **kwargs)

    def _apply_toolwindow_style(self, *args, **kwargs):
        try:
            collaborator = object.__getattribute__(self, "system_tray")
        except (AttributeError, RuntimeError):
            collaborator = None
        if collaborator is not None:
            return collaborator._apply_toolwindow_style(*args, **kwargs)
        return SystemTray._apply_toolwindow_style(self, *args, **kwargs)

    def _hide_to_tray(self, *args, **kwargs):
        try:
            collaborator = object.__getattribute__(self, "system_tray")
        except (AttributeError, RuntimeError):
            collaborator = None
        if collaborator is not None:
            return collaborator._hide_to_tray(*args, **kwargs)
        return SystemTray._hide_to_tray(self, *args, **kwargs)

    def _quit_application(self, *args, **kwargs):
        try:
            collaborator = object.__getattribute__(self, "system_tray")
        except (AttributeError, RuntimeError):
            collaborator = None
        if collaborator is not None:
            return collaborator._quit_application(*args, **kwargs)
        return SystemTray._quit_application(self, *args, **kwargs)

    def _close_windows_for_quit(self, *args, **kwargs):
        try:
            collaborator = object.__getattribute__(self, "system_tray")
        except (AttributeError, RuntimeError):
            collaborator = None
        if collaborator is not None:
            return collaborator._close_windows_for_quit(*args, **kwargs)
        return SystemTray._close_windows_for_quit(self, *args, **kwargs)

    def _add_resize_grips(self, *args, **kwargs):
        try:
            collaborator = object.__getattribute__(self, "system_tray")
        except (AttributeError, RuntimeError):
            collaborator = None
        if collaborator is not None:
            return collaborator._add_resize_grips(*args, **kwargs)
        return SystemTray._add_resize_grips(self, *args, **kwargs)

    def resizeEvent(self, *args, **kwargs):
        try:
            collaborator = object.__getattribute__(self, "system_tray")
        except (AttributeError, RuntimeError):
            collaborator = None
        if collaborator is not None:
            return collaborator.resizeEvent(*args, **kwargs)
        return SystemTray.resizeEvent(self, *args, **kwargs)

    def _take_quick_screenshot(self, *args, **kwargs):
        try:
            collaborator = object.__getattribute__(self, "app_launcher")
        except (AttributeError, RuntimeError):
            collaborator = None
        if collaborator is not None:
            return collaborator._take_quick_screenshot(*args, **kwargs)
        return AppLauncher._take_quick_screenshot(self, *args, **kwargs)

    def _capture_active_window(self, *args, **kwargs):
        try:
            collaborator = object.__getattribute__(self, "app_launcher")
        except (AttributeError, RuntimeError):
            collaborator = None
        if collaborator is not None:
            return collaborator._capture_active_window(*args, **kwargs)
        return AppLauncher._capture_active_window(self, *args, **kwargs)

    def _do_capture_excluding_suiteview(self, *args, **kwargs):
        try:
            collaborator = object.__getattribute__(self, "app_launcher")
        except (AttributeError, RuntimeError):
            collaborator = None
        if collaborator is not None:
            return collaborator._do_capture_excluding_suiteview(*args, **kwargs)
        return AppLauncher._do_capture_excluding_suiteview(self, *args, **kwargs)

    def _open_agent_chat(self, *args, **kwargs):
        try:
            collaborator = object.__getattribute__(self, "app_launcher")
        except (AttributeError, RuntimeError):
            collaborator = None
        if collaborator is not None:
            return collaborator._open_agent_chat(*args, **kwargs)
        return AppLauncher._open_agent_chat(self, *args, **kwargs)

    def _open_mainframe(self, *args, **kwargs):
        try:
            collaborator = object.__getattribute__(self, "app_launcher")
        except (AttributeError, RuntimeError):
            collaborator = None
        if collaborator is not None:
            return collaborator._open_mainframe(*args, **kwargs)
        return AppLauncher._open_mainframe(self, *args, **kwargs)

    def _open_screenshot(self, *args, **kwargs):
        try:
            collaborator = object.__getattribute__(self, "app_launcher")
        except (AttributeError, RuntimeError):
            collaborator = None
        if collaborator is not None:
            return collaborator._open_screenshot(*args, **kwargs)
        return AppLauncher._open_screenshot(self, *args, **kwargs)

    def _open_email_attachments(self, *args, **kwargs):
        try:
            collaborator = object.__getattribute__(self, "app_launcher")
        except (AttributeError, RuntimeError):
            collaborator = None
        if collaborator is not None:
            return collaborator._open_email_attachments(*args, **kwargs)
        return AppLauncher._open_email_attachments(self, *args, **kwargs)

    def _open_polview(self, *args, **kwargs):
        try:
            collaborator = object.__getattribute__(self, "app_launcher")
        except (AttributeError, RuntimeError):
            collaborator = None
        if collaborator is not None:
            return collaborator._open_polview(*args, **kwargs)
        return AppLauncher._open_polview(self, *args, **kwargs)

    def _wire_polview_launchers(self, *args, **kwargs):
        try:
            collaborator = object.__getattribute__(self, "app_launcher")
        except (AttributeError, RuntimeError):
            collaborator = None
        if collaborator is not None:
            return collaborator._wire_polview_launchers(*args, **kwargs)
        return AppLauncher._wire_polview_launchers(self, *args, **kwargs)

    def _wire_illustration_polview(self, *args, **kwargs):
        try:
            collaborator = object.__getattribute__(self, "app_launcher")
        except (AttributeError, RuntimeError):
            collaborator = None
        if collaborator is not None:
            return collaborator._wire_illustration_polview(*args, **kwargs)
        return AppLauncher._wire_illustration_polview(self, *args, **kwargs)

    def _get_polview_window(self, *args, **kwargs):
        try:
            collaborator = object.__getattribute__(self, "app_launcher")
        except (AttributeError, RuntimeError):
            collaborator = None
        if collaborator is not None:
            return collaborator._get_polview_window(*args, **kwargs)
        return AppLauncher._get_polview_window(self, *args, **kwargs)

    def _polview_btn_clicked(self, *args, **kwargs):
        try:
            collaborator = object.__getattribute__(self, "app_launcher")
        except (AttributeError, RuntimeError):
            collaborator = None
        if collaborator is not None:
            return collaborator._polview_btn_clicked(*args, **kwargs)
        return AppLauncher._polview_btn_clicked(self, *args, **kwargs)

    def _compact_policy(self, *args, **kwargs):
        try:
            collaborator = object.__getattribute__(self, "app_launcher")
        except (AttributeError, RuntimeError):
            collaborator = None
        if collaborator is not None:
            return collaborator._compact_policy(*args, **kwargs)
        return AppLauncher._compact_policy(self, *args, **kwargs)

    def _compact_region(self, *args, **kwargs):
        try:
            collaborator = object.__getattribute__(self, "app_launcher")
        except (AttributeError, RuntimeError):
            collaborator = None
        if collaborator is not None:
            return collaborator._compact_region(*args, **kwargs)
        return AppLauncher._compact_region(self, *args, **kwargs)

    def _clear_compact_policy(self, *args, **kwargs):
        try:
            collaborator = object.__getattribute__(self, "app_launcher")
        except (AttributeError, RuntimeError):
            collaborator = None
        if collaborator is not None:
            return collaborator._clear_compact_policy(*args, **kwargs)
        return AppLauncher._clear_compact_policy(self, *args, **kwargs)

    def _open_polview_with_policy(self, *args, **kwargs):
        try:
            collaborator = object.__getattribute__(self, "app_launcher")
        except (AttributeError, RuntimeError):
            collaborator = None
        if collaborator is not None:
            return collaborator._open_polview_with_policy(*args, **kwargs)
        return AppLauncher._open_polview_with_policy(self, *args, **kwargs)

    def _abrquote_btn_clicked(self, *args, **kwargs):
        try:
            collaborator = object.__getattribute__(self, "app_launcher")
        except (AttributeError, RuntimeError):
            collaborator = None
        if collaborator is not None:
            return collaborator._abrquote_btn_clicked(*args, **kwargs)
        return AppLauncher._abrquote_btn_clicked(self, *args, **kwargs)

    def _illustration_btn_clicked(self, *args, **kwargs):
        try:
            collaborator = object.__getattribute__(self, "app_launcher")
        except (AttributeError, RuntimeError):
            collaborator = None
        if collaborator is not None:
            return collaborator._illustration_btn_clicked(*args, **kwargs)
        return AppLauncher._illustration_btn_clicked(self, *args, **kwargs)

    def _launch_illustration_with_policy(self, *args, **kwargs):
        try:
            collaborator = object.__getattribute__(self, "app_launcher")
        except (AttributeError, RuntimeError):
            collaborator = None
        if collaborator is not None:
            return collaborator._launch_illustration_with_policy(*args, **kwargs)
        return AppLauncher._launch_illustration_with_policy(self, *args, **kwargs)

    def _launch_polview_with_policy(self, *args, **kwargs):
        try:
            collaborator = object.__getattribute__(self, "app_launcher")
        except (AttributeError, RuntimeError):
            collaborator = None
        if collaborator is not None:
            return collaborator._launch_polview_with_policy(*args, **kwargs)
        return AppLauncher._launch_polview_with_policy(self, *args, **kwargs)

    def _launch_switch_with_policy(self, *args, **kwargs):
        try:
            collaborator = object.__getattribute__(self, "app_launcher")
        except (AttributeError, RuntimeError):
            collaborator = None
        if collaborator is not None:
            return collaborator._launch_switch_with_policy(*args, **kwargs)
        return AppLauncher._launch_switch_with_policy(self, *args, **kwargs)

    def _open_passwords(self, *args, **kwargs):
        try:
            collaborator = object.__getattribute__(self, "app_launcher")
        except (AttributeError, RuntimeError):
            collaborator = None
        if collaborator is not None:
            return collaborator._open_passwords(*args, **kwargs)
        return AppLauncher._open_passwords(self, *args, **kwargs)

    def _open_audit(self, *args, **kwargs):
        try:
            collaborator = object.__getattribute__(self, "app_launcher")
        except (AttributeError, RuntimeError):
            collaborator = None
        if collaborator is not None:
            return collaborator._open_audit(*args, **kwargs)
        return AppLauncher._open_audit(self, *args, **kwargs)

    def _open_abrquote(self, *args, **kwargs):
        try:
            collaborator = object.__getattribute__(self, "app_launcher")
        except (AttributeError, RuntimeError):
            collaborator = None
        if collaborator is not None:
            return collaborator._open_abrquote(*args, **kwargs)
        return AppLauncher._open_abrquote(self, *args, **kwargs)

    def _open_illustration(self, *args, **kwargs):
        try:
            collaborator = object.__getattribute__(self, "app_launcher")
        except (AttributeError, RuntimeError):
            collaborator = None
        if collaborator is not None:
            return collaborator._open_illustration(*args, **kwargs)
        return AppLauncher._open_illustration(self, *args, **kwargs)

    def _open_rate_manager(self, *args, **kwargs):
        try:
            collaborator = object.__getattribute__(self, "app_launcher")
        except (AttributeError, RuntimeError):
            collaborator = None
        if collaborator is not None:
            return collaborator._open_rate_manager(*args, **kwargs)
        return AppLauncher._open_rate_manager(self, *args, **kwargs)

    def _open_administrator(self, *args, **kwargs):
        try:
            collaborator = object.__getattribute__(self, "app_launcher")
        except (AttributeError, RuntimeError):
            collaborator = None
        if collaborator is not None:
            return collaborator._open_administrator(*args, **kwargs)
        return AppLauncher._open_administrator(self, *args, **kwargs)

    def _open_db2_table_check(self, *args, **kwargs):
        try:
            collaborator = object.__getattribute__(self, "app_launcher")
        except (AttributeError, RuntimeError):
            collaborator = None
        if collaborator is not None:
            return collaborator._open_db2_table_check(*args, **kwargs)
        return AppLauncher._open_db2_table_check(self, *args, **kwargs)

    def _open_file_nav(self, *args, **kwargs):
        try:
            collaborator = object.__getattribute__(self, "app_launcher")
        except (AttributeError, RuntimeError):
            collaborator = None
        if collaborator is not None:
            return collaborator._open_file_nav(*args, **kwargs)
        return AppLauncher._open_file_nav(self, *args, **kwargs)

    def _open_app_data_location(self, *args, **kwargs):
        try:
            collaborator = object.__getattribute__(self, "app_launcher")
        except (AttributeError, RuntimeError):
            collaborator = None
        if collaborator is not None:
            return collaborator._open_app_data_location(*args, **kwargs)
        return AppLauncher._open_app_data_location(self, *args, **kwargs)

    def _toggle_scratchpad_window(self, *args, **kwargs):
        try:
            collaborator = object.__getattribute__(self, "app_launcher")
        except (AttributeError, RuntimeError):
            collaborator = None
        if collaborator is not None:
            return collaborator._toggle_scratchpad_window(*args, **kwargs)
        return AppLauncher._toggle_scratchpad_window(self, *args, **kwargs)

    def _toggle_file_open_history(self, *args, **kwargs):
        try:
            collaborator = object.__getattribute__(self, "app_launcher")
        except (AttributeError, RuntimeError):
            collaborator = None
        if collaborator is not None:
            return collaborator._toggle_file_open_history(*args, **kwargs)
        return AppLauncher._toggle_file_open_history(self, *args, **kwargs)

    def _bring_to_front(self, *args, **kwargs):
        try:
            collaborator = object.__getattribute__(self, "app_launcher")
        except (AttributeError, RuntimeError):
            collaborator = None
        if collaborator is not None:
            return collaborator._bring_to_front(*args, **kwargs)
        return AppLauncher._bring_to_front(self, *args, **kwargs)

    def _setup_child_window(self, *args, **kwargs):
        try:
            collaborator = object.__getattribute__(self, "app_launcher")
        except (AttributeError, RuntimeError):
            collaborator = None
        if collaborator is not None:
            return collaborator._setup_child_window(*args, **kwargs)
        return AppLauncher._setup_child_window(self, *args, **kwargs)
