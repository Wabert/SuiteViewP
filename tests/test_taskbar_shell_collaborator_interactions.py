"""Regression coverage for shell collaborators using explicit host objects."""

from __future__ import annotations

import os
import sys
import types
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from PyQt6.QtCore import QEvent, QPoint, Qt
from PyQt6.QtGui import QKeyEvent
from PyQt6.QtWidgets import (
    QApplication,
    QHBoxLayout,
    QMessageBox,
    QPushButton,
    QWidget,
)

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from suiteview.core import access_control as core_access
from suiteview.file_nav import file_explorer_core
from suiteview.taskbar_launcher import file_explorer_quick_links, taskbar_system
from suiteview.taskbar_launcher.collaborators import TaskbarState
from suiteview.taskbar_launcher.file_explorer_tab import FileExplorerTab
from suiteview.taskbar_launcher.taskbar_modes import TaskbarModes
from suiteview.taskbar_launcher.taskbar_system import AppLauncher, SystemTray


class _Signal:
    def __init__(self) -> None:
        self.callbacks: list[object] = []

    def connect(self, callback) -> None:
        self.callbacks.append(callback)


class _ChildWindow(QWidget):
    def __init__(self, *args, **kwargs) -> None:
        super().__init__()
        self.permissions_changed = _Signal()
        self.polview_provider = None
        self.illustration_launcher = None
        self.polview_launcher = None
        self.loaded_policy = None

    def set_polview_provider(self, callback) -> None:
        self.polview_provider = callback

    def set_illustration_launcher(self, callback) -> None:
        self.illustration_launcher = callback

    def set_polview_launcher(self, callback) -> None:
        self.polview_launcher = callback

    def load_policy(self, *args, **kwargs) -> None:
        self.loaded_policy = (args, kwargs)

    def has_policy_loaded(self, _policy) -> bool:
        return False

    def _load_existing_screenshots(self) -> None:
        return None


class _FakeRepository:
    def load(self) -> None:
        return None


class _ScratchPadWindow:
    @staticmethod
    def open(parent_bar=None):
        window = _ChildWindow()
        window.parent_bar = parent_bar
        return window


def _install_module(monkeypatch, name: str, **attrs) -> None:
    module = types.ModuleType(name)
    for attr_name, value in attrs.items():
        setattr(module, attr_name, value)
    monkeypatch.setitem(sys.modules, name, module)


@pytest.fixture
def qt_app(monkeypatch, tmp_path):
    monkeypatch.setenv("SUITEVIEW_PROFILE_DIR", str(tmp_path / "profile"))
    monkeypatch.setattr(core_access, "guard_app_access", lambda _code: None)
    monkeypatch.setattr(file_explorer_core, "guard_app_access", lambda _code: None)
    monkeypatch.setattr(QMessageBox, "warning", lambda *args, **kwargs: QMessageBox.StandardButton.Ok)
    monkeypatch.setattr(QMessageBox, "critical", lambda *args, **kwargs: QMessageBox.StandardButton.Ok)
    monkeypatch.setattr(QMessageBox, "information", lambda *args, **kwargs: QMessageBox.StandardButton.Ok)
    monkeypatch.setattr(QMessageBox, "question", lambda *args, **kwargs: QMessageBox.StandardButton.No)
    return QApplication.instance() or QApplication([])


@pytest.fixture
def app_launcher(qt_app, qtbot):
    host = QWidget()
    qtbot.addWidget(host)
    state = TaskbarState()
    chrome = SimpleNamespace(
        _administrator_menu_access=SimpleNamespace(refresh=Mock()),
        file_history_btn=QPushButton("H"),
    )
    launcher = AppLauncher(host, state, chrome=chrome)
    callbacks = SimpleNamespace()
    callbacks._setup_child_window = lambda window, title: launcher._setup_child_window(window, title)
    callbacks._bring_to_front = Mock()
    callbacks._refresh_permissions = Mock()
    launcher.callbacks = callbacks
    return launcher


@pytest.fixture
def app_launch_stubs(monkeypatch):
    _install_module(monkeypatch, "suiteview.agent_chat", AgentChatWindow=_ChildWindow)
    _install_module(
        monkeypatch,
        "suiteview.mainframe_nav.mainframe_window",
        MainframeWindow=_ChildWindow,
    )
    _install_module(
        monkeypatch,
        "suiteview.screenshot_manager.screenshot_manager_window",
        ScreenShotManagerWindow=_ChildWindow,
    )
    _install_module(
        monkeypatch,
        "suiteview.ui.email_attachments_window",
        EmailAttachmentsWindow=_ChildWindow,
    )
    _install_module(monkeypatch, "suiteview.polview.ui.main_window", GetPolicyWindow=_ChildWindow)
    _install_module(monkeypatch, "suiteview.audit", launch_audit=_ChildWindow)
    _install_module(monkeypatch, "suiteview.abrquote", launch_abrquote=_ChildWindow)
    _install_module(monkeypatch, "suiteview.illustration", launch_illustration=_ChildWindow)
    _install_module(
        monkeypatch,
        "suiteview.ratemanager.ratemanager_window",
        RateManagerWindow=_ChildWindow,
    )
    _install_module(monkeypatch, "suiteview.administrator.service", AccessRepository=_FakeRepository)
    _install_module(monkeypatch, "suiteview.administrator.window", AdministratorWindow=_ChildWindow)
    _install_module(
        monkeypatch,
        "suiteview.ui.db2_table_check_window",
        DB2TableCheckWindow=lambda region="CKPR": _ChildWindow(),
    )
    _install_module(monkeypatch, "suiteview.scratchpad.scratchpad_panel", ScratchPadWindow=_ScratchPadWindow)
    monkeypatch.setattr(taskbar_system, "FileNavWindow", lambda parent_bar=None: _ChildWindow())


@pytest.mark.parametrize(
    ("method_name", "state_attr"),
    [
        ("_open_agent_chat", "agent_chat_window"),
        ("_open_mainframe", "mainframe_window"),
        ("_open_screenshot", "screenshot_window"),
        ("_open_email_attachments", "email_attachments_window"),
        ("_open_polview", "polview_window"),
        ("_open_audit", "audit_window"),
        ("_open_abrquote", "abrquote_window"),
        ("_open_illustration", "illustration_window"),
        ("_open_rate_manager", "ratemanager_window"),
        ("_open_administrator", "administrator_window"),
        ("_open_db2_table_check", "db2_check_window"),
        ("_open_file_nav", "file_nav_window"),
        ("_toggle_scratchpad_window", "scratchpad_window"),
    ],
)
def test_app_launcher_open_paths_use_window_services(
    app_launch_stubs,
    app_launcher,
    method_name,
    state_attr,
):
    getattr(app_launcher, method_name)()

    launched = getattr(app_launcher.state, state_attr)
    assert launched is not None
    assert launched.windowTitle().startswith("SuiteView -") or method_name in {
        "_open_email_attachments",
        "_open_administrator",
    }
    if method_name == "_open_administrator":
        assert len(launched.permissions_changed.callbacks) == 2
    app_launcher.callbacks._bring_to_front.assert_called_with(launched)


def test_app_launcher_app_data_location_uses_current_tab(app_launcher, tmp_path, monkeypatch):
    navigated_tab = SimpleNamespace(navigate_to_path=Mock())
    app_launcher.window.get_current_tab = lambda: navigated_tab
    monkeypatch.setenv("SUITEVIEW_PROFILE_DIR", str(tmp_path / "profile"))

    app_launcher._open_app_data_location()

    navigated_tab.navigate_to_path.assert_called_once()
    assert "profile" in navigated_tab.navigate_to_path.call_args.args[0]


def test_tray_hide_and_show_restore_the_window(qt_app, qtbot, monkeypatch):
    host = QWidget()
    qtbot.addWidget(host)
    host.restore_window = Mock(side_effect=host.show)
    state = TaskbarState(
        is_compact_mode=True,
        hidden_to_tray=False,
        tray_icon=SimpleNamespace(showMessage=Mock()),
    )
    callbacks = SimpleNamespace(_unregister_appbar=Mock(), _register_appbar=Mock())
    tray = SystemTray(host, state, callbacks=callbacks)
    monkeypatch.setattr(SystemTray, "_apply_toolwindow_style", Mock())
    monkeypatch.setattr(taskbar_system.QTimer, "singleShot", lambda _ms, callback: callback())

    host.show()
    tray._hide_to_tray()
    assert state.hidden_to_tray
    assert not host.isVisible()
    callbacks._unregister_appbar.assert_called_once_with(force=True)

    tray._show_from_tray()
    host.restore_window.assert_called_once_with()
    callbacks._register_appbar.assert_called_once()
    assert not state.hidden_to_tray


def _chrome_with_mode_widgets(qtbot):
    chrome = SimpleNamespace()
    for name in (
        "tab_widget",
        "footer_bar",
        "sidebar_container",
        "minimize_btn",
        "maximize_btn",
        "header_spacer",
        "compact_region_combo",
        "compact_policy_input",
        "quick_screenshot_btn",
        "tools_menu_btn",
        "scratchpad_window_btn",
        "file_history_btn",
        "close_btn",
    ):
        widget = QPushButton(name)
        qtbot.addWidget(widget)
        setattr(chrome, name, widget)
    chrome.maximize_btn.setText("☐")
    return chrome


def test_compact_floating_docked_mode_transitions(qt_app, qtbot, monkeypatch):
    host = QWidget()
    qtbot.addWidget(host)
    QHBoxLayout(host).addWidget(QPushButton("SuiteView", host))
    host.show()
    state = TaskbarState(is_compact_mode=True, launcher_access=SimpleNamespace(allows_app=lambda _code: True))
    chrome = _chrome_with_mode_widgets(qtbot)
    callbacks = SimpleNamespace(
        _apply_permissions=Mock(),
        _apply_toolwindow_style=Mock(),
        _register_appbar=Mock(),
    )
    modes = TaskbarModes(host, state, chrome, callbacks)
    monkeypatch.setattr(TaskbarModes, "_unregister_appbar", lambda self, force=False: None)

    modes._toggle_compact_mode()
    assert state.is_floating_mode
    assert not state.is_compact_mode
    assert chrome.scratchpad_window_btn.isHidden()

    modes._toggle_compact_mode()
    assert state.is_compact_mode
    assert not state.is_floating_mode
    callbacks._register_appbar.assert_called()


@pytest.fixture
def explorer_tab(qt_app, qtbot, tmp_path):
    root = tmp_path / "root"
    child = root / "child"
    child.mkdir(parents=True)
    (child / "nested.txt").write_text("x", encoding="utf-8")
    other = tmp_path / "other"
    other.mkdir()
    tab = FileExplorerTab(initial_path=str(root))
    qtbot.addWidget(tab)
    tab.show()
    qt_app.processEvents()
    return SimpleNamespace(tab=tab, root=root, child=child, other=other)


def test_tree_click_double_click_and_root_load_use_tab_model(explorer_tab):
    tab = explorer_tab.tab

    tab.load_directory_contents_at_root(explorer_tab.root)
    assert tab.model.rowCount() == 1

    index = tab.model.index(0, 0)
    tab.on_tree_item_clicked(index)
    assert tab.current_details_folder == str(explorer_tab.child)

    tab.on_item_double_clicked(index)
    assert tab.current_details_folder == str(explorer_tab.child)


def test_refresh_f5_up_home_and_history_panel_use_tab_state(explorer_tab, monkeypatch):
    tab = explorer_tab.tab
    tab.current_details_folder = str(explorer_tab.child)
    tab.tab_state.current_directory = str(explorer_tab.other)

    load = Mock()
    monkeypatch.setattr(tab, "load_folder_contents_in_details", load)
    tab.refresh_current_folder()
    load.assert_called_once_with(explorer_tab.child)

    load.reset_mock()
    event = QKeyEvent(QEvent.Type.KeyPress, Qt.Key.Key_F5, Qt.KeyboardModifier.NoModifier)
    tab.keyPressEvent(event)
    load.assert_called_once_with(explorer_tab.child)

    navigate = Mock()
    monkeypatch.setattr(tab.navigation, "navigate_to_path", navigate)
    tab.go_up_one_level()
    navigate.assert_called_with(str(explorer_tab.root))

    navigate.reset_mock()
    tab.go_to_onedrive_home()
    navigate.assert_called_with(str(explorer_tab.root))

    tab.toggle_history_panel()
    assert not tab.navigation.history_panel.isHidden()
    assert tab.folders_history_btn.isChecked()


def test_folders_history_button_is_connected_to_history_panel(explorer_tab):
    tab = explorer_tab.tab

    tab.folders_history_btn.click()

    assert not tab.navigation.history_panel.isHidden()
    assert tab.folders_history_btn.isChecked()


def test_quick_links_footer_add_bookmark_and_moves_use_tab_state(explorer_tab, monkeypatch):
    tab = explorer_tab.tab
    tab.custom_quick_links = {
        "items": [
            {"type": "bookmark", "name": "A", "path": str(explorer_tab.child)},
            {
                "type": "category",
                "name": "Cat",
                "items": [{"type": "bookmark", "name": "B", "path": str(explorer_tab.root)}],
            },
        ]
    }

    tab._update_sidebar_footer()
    assert tab.sidebar_footer.text() == "2 bookmarks, 1 categories"

    captured_dialog: dict[str, object] = {}

    class _Field:
        def __init__(self) -> None:
            self.text = ""

        def setText(self, value) -> None:
            self.text = value

    class _Dialog:
        DialogCode = SimpleNamespace(Accepted=1, Rejected=0)

        def __init__(self, categories, parent) -> None:
            captured_dialog["categories"] = categories
            captured_dialog["parent"] = parent
            self.path_input = _Field()
            self.name_input = _Field()
            captured_dialog["dialog"] = self

        def exec(self):
            return self.DialogCode.Rejected

    monkeypatch.setattr(file_explorer_quick_links, "AddBookmarkDialog", _Dialog)
    tab.current_details_folder = str(explorer_tab.child)
    tab._add_bookmark_to_sidebar()
    dialog = captured_dialog["dialog"]
    assert captured_dialog["parent"] is tab
    assert captured_dialog["categories"] == ["Cat"]
    assert dialog.path_input.text == str(explorer_tab.child)
    assert dialog.name_input.text == explorer_tab.child.name

    fake_bar = SimpleNamespace(
        bookmarks_data={
            "bar_items": [{"type": "bookmark", "name": "Moved", "path": str(explorer_tab.child)}]
        },
        save_bookmarks=Mock(),
        refresh_bookmarks=Mock(),
        remove_category=Mock(),
    )
    tab.bookmark_bar = fake_bar
    tab.custom_quick_links = {"items": []}
    tab.on_bookmark_dropped_to_quick_links(
        {
            "name": "Moved",
            "path": str(explorer_tab.child),
            "_source_category": "__BAR__",
            "source_location": "bar",
        }
    )
    assert fake_bar.bookmarks_data["bar_items"] == []
    assert tab.custom_quick_links["items"][0]["path"] == str(explorer_tab.child)

    tab._bookmark_manager.find_category_by_name = Mock(return_value=None)
    tab.add_category_to_quick_links = Mock()
    tab.refresh_quick_links_list = Mock()
    tab.on_category_dropped_to_quick_links(
        {"name": "BarCat", "items": [], "source": "bookmark_bar"}
    )
    fake_bar.remove_category.assert_called_once_with("BarCat")


def test_quick_links_context_menus_and_warnings_are_parented_to_tab(
    explorer_tab,
    qtbot,
    monkeypatch,
):
    tab = explorer_tab.tab
    menu_parents: list[object] = []
    warning_parents: list[object] = []

    class _Menu:
        def __init__(self, parent=None) -> None:
            menu_parents.append(parent)

        def setStyleSheet(self, _style) -> None:
            return None

        def addAction(self, _action) -> None:
            return None

        def addSeparator(self) -> None:
            return None

        def exec(self, *_args) -> None:
            return None

    monkeypatch.setattr(file_explorer_quick_links, "QMenu", _Menu)
    monkeypatch.setattr(
        QMessageBox,
        "warning",
        lambda parent, *args, **kwargs: warning_parents.append(parent)
        or QMessageBox.StandardButton.Ok,
    )

    bookmark_btn = QWidget()
    qtbot.addWidget(bookmark_btn)
    bookmark_btn.bookmark_path = str(explorer_tab.child)
    category_widget = QWidget()
    qtbot.addWidget(category_widget)
    category_widget.category_name = "Cat"
    category_widget.category_items = []

    tab.quick_links._show_bookmark_context_menu(QPoint(0, 0), bookmark_btn)
    tab.quick_links._show_category_context_menu(QPoint(0, 0), category_widget)
    tab.quick_links._show_quick_links_panel_context_menu(QPoint(0, 0))
    tab.quick_links._on_bookmark_clicked(str(explorer_tab.root / "missing"))

    assert menu_parents == [tab, tab, tab]
    assert warning_parents == [tab]
