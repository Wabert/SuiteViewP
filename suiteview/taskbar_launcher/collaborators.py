"""Explicit collaborators and shared state for the SuiteView shell."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol

from PyQt6.QtCore import QObject
from PyQt6.QtWidgets import QWidget


class TaskbarCallbacks(Protocol):
    """Named callbacks the chrome can wire to buttons and menus."""

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
    def show_tab_bar_context_menu(self, pos) -> None: ...
    def close_tab(self, index: int) -> None: ...
    def _apply_permissions(self, access) -> None: ...
    def _setup_child_window(self, window, title: str) -> None: ...
    def _bring_to_front(self, window) -> None: ...
    def _apply_toolwindow_style(self) -> None: ...
    def _register_appbar(self, bar_h: int, _retry: bool = True) -> None: ...
    def _unregister_appbar(self, force: bool = False) -> None: ...


@dataclass
class TaskbarState:
    """Shared mutable shell state passed explicitly to collaborators."""

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
    """Base with explicit Qt-window operations, state and chrome dependencies."""

    def __init__(
        self,
        window: QWidget,
        state: TaskbarState,
        chrome=None,
        callbacks: TaskbarCallbacks | None = None,
    ) -> None:
        super().__init__(window)
        self.window = window
        self.state = state
        self.chrome = chrome
        self.callbacks = callbacks

    # ---- explicit QWidget/QObject operations used by shell collaborators ----
    def setStyleSheet(self, stylesheet: str) -> None:
        self.window.setStyleSheet(stylesheet)

    def style(self):
        return self.window.style()

    def findChildren(self, *args, **kwargs):
        return self.window.findChildren(*args, **kwargs)

    def layout(self):
        return self.window.layout()

    def setWindowFlags(self, flags) -> None:
        self.window.setWindowFlags(flags)

    def setGeometry(self, *args) -> None:
        self.window.setGeometry(*args)

    def geometry(self):
        return self.window.geometry()

    def frameGeometry(self):
        return self.window.frameGeometry()

    def rect(self):
        return self.window.rect()

    def pos(self):
        return self.window.pos()

    def childAt(self, *args):
        return self.window.childAt(*args)

    def move(self, *args) -> None:
        self.window.move(*args)

    def resize(self, *args) -> None:
        self.window.resize(*args)

    def width(self) -> int:
        return self.window.width()

    def height(self) -> int:
        return self.window.height()

    def setMinimumSize(self, *args) -> None:
        self.window.setMinimumSize(*args)

    def setMaximumHeight(self, value: int) -> None:
        self.window.setMaximumHeight(value)

    def show(self) -> None:
        self.window.show()

    def hide(self) -> None:
        self.window.hide()

    def isVisible(self) -> bool:
        return self.window.isVisible()

    def showNormal(self) -> None:
        self.window.showNormal()

    def showMaximized(self) -> None:
        self.window.showMaximized()

    def showMinimized(self) -> None:
        self.window.showMinimized()

    def raise_(self) -> None:
        self.window.raise_()

    def activateWindow(self) -> None:
        self.window.activateWindow()

    def winId(self):
        return self.window.winId()

    def devicePixelRatioF(self) -> float:
        return self.window.devicePixelRatioF()

    def setWindowIcon(self, icon) -> None:
        self.window.setWindowIcon(icon)

    def setCursor(self, cursor) -> None:
        self.window.setCursor(cursor)

    def unsetCursor(self) -> None:
        self.window.unsetCursor()

    def close(self) -> bool:
        return self.window.close()


def _state_property(state_name: str):
    return property(
        lambda self: getattr(self.state, state_name),
        lambda self, value: setattr(self.state, state_name, value),
    )


def _chrome_property(chrome_name: str):
    def getter(self):
        if self.chrome is None and chrome_name in self.__dict__:
            return self.__dict__[chrome_name]
        if self.chrome is None or not hasattr(self.chrome, chrome_name):
            raise AttributeError(chrome_name)
        return getattr(self.chrome, chrome_name)

    def setter(self, value):
        if self.chrome is None:
            self.__dict__[chrome_name] = value
            return
        setattr(self.chrome, chrome_name, value)

    return property(getter, setter)


def _callback_method(callback_name: str):
    def method(self, *args, **kwargs):
        if self.callbacks is None:
            raise AttributeError(callback_name)
        return getattr(self.callbacks, callback_name)(*args, **kwargs)

    return method


for _public, _field in {
    "_launcher_access": "launcher_access",
    "_restore_message": "restore_message",
    "_drag_pos": "drag_pos",
    "_is_maximized": "is_maximized",
    "_is_compact_mode": "is_compact_mode",
    "_is_floating_mode": "is_floating_mode",
    "_stored_geometry": "stored_geometry",
    "_compact_bar_pos": "compact_bar_pos",
    "_appbar_registered": "appbar_registered",
    "_hidden_to_tray": "hidden_to_tray",
    "_bar_refresh_pending": "bar_refresh_pending",
    "_ignore_screen_events_until": "ignore_screen_events_until",
    "_screen_signal_refs": "screen_signal_refs",
    "_resize_margin": "resize_margin",
    "_resizing": "resizing",
    "_resize_edge": "resize_edge",
    "_resize_start_pos": "resize_start_pos",
    "_start_geometry": "start_geometry",
    "_shared_splitter_sizes": "shared_splitter_sizes",
    "_syncing_splitter": "syncing_splitter",
    "_bookmark_popup": "bookmark_popup",
    "_resize_widgets": "resize_widgets",
    "_file_open_history_panel": "file_open_history_panel",
    "tray_icon": "tray_icon",
    "mainframe_window": "mainframe_window",
    "email_attachments_window": "email_attachments_window",
    "screenshot_window": "screenshot_window",
    "polview_window": "polview_window",
    "audit_window": "audit_window",
    "db2_check_window": "db2_check_window",
    "ratemanager_window": "ratemanager_window",
    "administrator_window": "administrator_window",
    "abrquote_window": "abrquote_window",
    "illustration_window": "illustration_window",
    "file_nav_window": "file_nav_window",
    "scratchpad_window": "scratchpad_window",
    "agent_chat_window": "agent_chat_window",
}.items():
    setattr(TaskbarCollaborator, _public, _state_property(_field))

for _name in {
    "_permission_actions",
    "_administrator_menu_access",
    "header_bar",
    "title_label",
    "quick_screenshot_btn",
    "compact_region_combo",
    "compact_policy_input",
    "polview_btn",
    "filenav_btn",
    "abrquote_btn",
    "illustration_btn",
    "audit_btn",
    "albert_btn",
    "scratchpad_window_btn",
    "file_history_btn",
    "tools_menu_btn",
    "tools_menu",
    "administrator_action",
    "header_spacer",
    "minimize_btn",
    "maximize_btn",
    "close_btn",
    "tab_widget",
    "footer_bar",
    "footer_status",
    "footer_size",
}:
    setattr(TaskbarCollaborator, _name, _chrome_property(_name))

for _name in {
    "_toggle_compact_mode",
    "_take_quick_screenshot",
    "_open_polview_with_policy",
    "_polview_btn_clicked",
    "_open_file_nav",
    "_abrquote_btn_clicked",
    "_illustration_btn_clicked",
    "_open_audit",
    "_toggle_scratchpad_window",
    "_toggle_file_open_history",
    "_open_screenshot",
    "_open_administrator",
    "_open_mainframe",
    "_open_rate_manager",
    "_open_db2_table_check",
    "_open_email_attachments",
    "_refresh_permissions",
    "_open_app_data_location",
    "_toggle_maximize",
    "_hide_to_tray",
    "show_tab_bar_context_menu",
    "close_tab",
    "_apply_permissions",
    "_setup_child_window",
    "_bring_to_front",
    "_apply_toolwindow_style",
    "_register_appbar",
    "_unregister_appbar",
}:
    setattr(TaskbarCollaborator, _name, _callback_method(_name))


class FileExplorerController(QObject):
    """Base for FileExplorerTab collaborators with explicit tab dependencies."""

    def __init__(self, tab: QWidget) -> None:
        super().__init__(tab)
        self.tab = tab

    def findChildren(self, *args, **kwargs):
        return self.tab.findChildren(*args, **kwargs)

    def findChild(self, *args, **kwargs):
        return self.tab.findChild(*args, **kwargs)

    def layout(self):
        return self.tab.layout()

    def style(self):
        return self.tab.style()

    def sender(self):
        return self.tab.sender()

    def mapToGlobal(self, *args):
        return self.tab.mapToGlobal(*args)


def _tab_property(tab_name: str):
    return property(
        lambda self: getattr(self.tab, tab_name),
        lambda self, value: setattr(self.tab, tab_name, value),
    )


def _tab_method(method_name: str):
    def method(self, *args, **kwargs):
        return getattr(self.tab, method_name)(*args, **kwargs)

    method.__name__ = method_name
    return method


for _name in {
    "tree_view",
    "details_view",
    "main_splitter",
    "breadcrumb_frame",
    "back_btn",
    "up_btn",
    "refresh_btn",
    "breadcrumb_widget",
    "explorer_btn",
    "bookmarks_toggle_btn",
    "current_directory",
    "path_changed",
    "starting_path",
    "current_path_history",
    "current_path_index",
    "full_history",
    "history_panel",
    "current_path_btn",
    "full_history_btn",
    "history_list",
    "history_view_mode",
    "_sp_display_names",
    "current_details_folder",
    "details_model",
    "details_sort_proxy",
    "details_header",
    "panel_widths",
    "bookmark_bar",
    "quick_links_header",
    "quick_links_model",
    "bookmark_container",
    "sidebar_footer",
    "quick_links_items_layout",
    "quick_links_scroll_content",
    "tree_panel_2",
    "quick_links_panel",
    "dual_pane_active",
    "scratchpad_panel",
    "scratchpad_panel_active",
    "scratchpad_btn",
    "_pre_fs_sizes",
    "_bookmark_manager",
    "custom_quick_links",
}:
    setattr(FileExplorerController, _name, _tab_property(_name))

for _name in {
    "on_item_expanded",
    "on_tree_item_clicked",
    "show_tree_context_menu",
    "show_details_context_menu",
    "handle_dropped_files",
    "load_folder_contents_in_details",
    "load_sharepoint_contents_in_details",
    "open_sharepoint_file",
    "_resolve_shortcut",
    "_safe_startfile",
    "create_folder_item",
    "create_file_item",
    "get_onedrive_paths",
    "open_file",
    "_open_folder_location",
    "_remove_bookmark_from_quick_links",
    "rename_category_in_quick_links",
    "refresh_quick_links_list",
    "remove_category_from_quick_links",
    "save_quick_links",
    "is_path_in_quick_links",
    "add_to_quick_links",
    "add_category_to_quick_links",
    "_remove_category_from_bookmark_bar",
    "refresh_quick_links",
    "save_panel_widths",
    "_apply_depth_search_locked_style",
    "refresh_current_folder",
    "_create_nav_button",
    "open_in_explorer",
    "toggle_dual_pane",
}:
    setattr(FileExplorerController, _name, _tab_method(_name))
