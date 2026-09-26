"""Explicit collaborator state and callback contracts for the SuiteView shell."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol

from PyQt6.QtCore import QObject
from PyQt6.QtWidgets import QWidget


class TaskbarCallbacks(Protocol):
    """Callbacks that taskbar collaborators ask the shell to perform."""

    def showMinimized(self) -> None: ...
    def show_tab_bar_context_menu(self, pos) -> None: ...
    def close_tab(self, index: int) -> None: ...
    def _apply_permissions(self, access) -> None: ...
    def _apply_toolwindow_style(self) -> None: ...
    def _register_appbar(self, bar_h: int, _retry: bool = True) -> None: ...
    def _unregister_appbar(self, force: bool = False) -> None: ...
    def _enter_compact_mode(self, initial: bool = False) -> None: ...
    def _show_from_tray(self) -> None: ...
    def _quit_application(self) -> None: ...
    def _setup_child_window(self, window, title: str) -> None: ...
    def _bring_to_front(self, window) -> None: ...
    def _toggle_compact_mode(self) -> None: ...
    def _take_quick_screenshot(self) -> None: ...
    def _open_polview_with_policy(self) -> None: ...
    def _polview_btn_clicked(self) -> None: ...
    def _open_file_nav(self) -> None: ...
    def _abrquote_btn_clicked(self) -> None: ...
    def _illustration_btn_clicked(self) -> None: ...
    def _open_audit(self) -> None: ...
    def _toggle_scratchpad_window(self) -> None: ...
    def _toggle_file_open_history(self) -> None: ...
    def _open_screenshot(self) -> None: ...
    def _open_administrator(self) -> None: ...
    def _open_mainframe(self) -> None: ...
    def _open_rate_manager(self) -> None: ...
    def _open_db2_table_check(self) -> None: ...
    def _open_email_attachments(self) -> None: ...
    def _refresh_permissions(self) -> None: ...
    def _open_app_data_location(self) -> None: ...
    def _toggle_maximize(self) -> None: ...
    def _hide_to_tray(self) -> None: ...


@dataclass
class TaskbarState:
    """Shared mutable taskbar values passed explicitly to collaborators."""

    launcher_access: object | None = None
    restore_message: int = 0
    drag_pos: object | None = None
    is_maximized: bool = False
    is_compact_mode: bool = False
    is_floating_mode: bool = False
    stored_geometry: object | None = None
    compact_bar_pos: object | None = None
    appbar_registered: bool = False
    hidden_to_tray: bool = False
    bar_refresh_pending: bool = False
    ignore_screen_events_until: float = 0.0
    screen_signal_refs: list = field(default_factory=list)
    resize_margin: int = 6
    resizing: bool = False
    resize_edge: object | None = None
    resize_start_pos: object | None = None
    start_geometry: object | None = None
    shared_splitter_sizes: object | None = None
    syncing_splitter: bool = False
    bookmark_popup: object | None = None
    resize_widgets: list = field(default_factory=list)
    file_open_history_panel: object | None = None
    tray_icon: object | None = None
    mainframe_window: object | None = None
    email_attachments_window: object | None = None
    screenshot_window: object | None = None
    polview_window: object | None = None
    audit_window: object | None = None
    db2_check_window: object | None = None
    ratemanager_window: object | None = None
    administrator_window: object | None = None
    abrquote_window: object | None = None
    illustration_window: object | None = None
    file_nav_window: object | None = None
    scratchpad_window: object | None = None
    agent_chat_window: object | None = None


class TaskbarCollaborator(QObject):
    """Base that stores explicit taskbar dependencies only."""

    def __init__(
        self,
        window: QWidget,
        state: TaskbarState,
        chrome=None,
        callbacks: TaskbarCallbacks | None = None,
    ) -> None:
        super().__init__(window if isinstance(window, QObject) else None)
        self.window = window
        self.state = state
        self.chrome = chrome
        self.callbacks = callbacks


@dataclass
class FileExplorerTabState:
    """Shared mutable tab values used by FileExplorerTab collaborators."""

    current_directory: str = ""
    starting_path: str = ""
    current_path_history: list = field(default_factory=list)
    current_path_index: int = -1
    full_history: list = field(default_factory=list)
    sp_display_names: dict = field(default_factory=dict)
    history_view_mode: str = "current_path"
    dual_pane_active: bool = False
    scratchpad_panel_active: bool = False
    pre_fs_sizes: object | None = None


class FileExplorerController(QObject):
    """Base that stores explicit FileExplorerTab dependencies only."""

    def __init__(self, tab: QWidget, state: FileExplorerTabState) -> None:
        super().__init__(tab)
        self.tab = tab
        self.state = state
