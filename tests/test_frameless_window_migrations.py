import os

import pytest
from PyQt6.QtCore import pyqtSignal
from PyQt6.QtWidgets import QApplication, QWidget

from suiteview.ui.widgets.frameless_window import FramelessWindowBase

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


@pytest.fixture
def app():
    return QApplication.instance() or QApplication([])


def test_screenshot_manager_uses_frameless_base_with_preserved_header(
    app, monkeypatch, tmp_path
):
    from suiteview.core import access_control
    from suiteview.screenshot_manager import screenshot_manager_window as mod

    monkeypatch.setattr(access_control, "guard_app_access", lambda _code: None)
    monkeypatch.setattr(mod, "profile_path", lambda name: tmp_path / name)

    window = mod.ScreenShotManagerWindow()
    try:
        assert isinstance(window, FramelessWindowBase)
        assert window.title_label.text() == "SCREENSHOT MANAGER"
        assert window._header_colors == ("#1E5BA8", "#0D3A7A", "#082B5C")
        assert window._border_color == "#D4A017"
        assert window.minimumWidth() == 200
        assert window.minimumHeight() == 50
        assert window.size().width() == 900
        assert window.size().height() == 500
        assert window.grab_btn.objectName() == ""
        assert window.window_capture_btn.objectName() == ""
    finally:
        window.close()


class _FakeEmailRepo:
    def get_setting(self, _key, default):
        return default

    def get_attachments_since(self, _start):
        return []

    def set_setting(self, _key, _value):
        return None

    def clear_cache(self):
        return None


def test_email_attachments_uses_frameless_base_with_preserved_header(
    app, monkeypatch
):
    from suiteview.core import access_control
    from suiteview.ui import email_attachments_window as mod

    monkeypatch.setattr(access_control, "guard_app_access", lambda _code: None)
    monkeypatch.setattr(mod, "get_email_repository", lambda: _FakeEmailRepo())

    window = mod.EmailAttachmentsWindow()
    try:
        assert isinstance(window, FramelessWindowBase)
        assert window.title_label.text() == "📎 EMAIL ATTACHMENTS"
        assert window._header_colors == ("#1E5BA8", "#0D3A7A", "#082B5C")
        assert window._border_color == "#D4A017"
        assert window.minimumWidth() == 400
        assert window.minimumHeight() == 300
        assert window.size().width() == 1200
        assert window.size().height() == 600
        assert window.refresh_btn.objectName() == ""
    finally:
        window.close()


def test_filenav_uses_frameless_base_with_preserved_header(app, monkeypatch):
    from suiteview.core import access_control
    from suiteview.taskbar_launcher import file_nav_window as mod

    class FakeFileExplorerTab(QWidget):
        path_changed = pyqtSignal(str)

        def __init__(self, initial_path=None):
            super().__init__()
            self.current_details_folder = initial_path or ""

    monkeypatch.setattr(access_control, "guard_app_access", lambda _code: None)
    monkeypatch.setattr(mod, "guard_app_access", lambda _code: None)
    monkeypatch.setattr(mod, "FileExplorerTab", FakeFileExplorerTab)

    window = mod.FileNavWindow()
    try:
        assert isinstance(window, FramelessWindowBase)
        assert window.title_label.text() == "FileNav"
        assert window._header_colors == ("#1E5BA8", "#0D3A7A", "#082B5C")
        assert window._border_color == "#D4A017"
        assert window.minimumWidth() == 600
        assert window.minimumHeight() == 400
        assert window.size().width() == 1400
        assert window.size().height() == 800
        assert window.tools_menu_btn.objectName() == ""
    finally:
        window.close()


def test_mainframe_window_uses_frameless_base_with_preserved_header(app, monkeypatch):
    from suiteview.core import access_control
    from suiteview.mainframe_nav import mainframe_window as mod

    class FakeNavScreen(QWidget):
        def __init__(self, _conn_manager):
            super().__init__()

    class FakeTerminalScreen(QWidget):
        def __init__(self):
            super().__init__()
            self.terminal_left = type("TerminalSide", (), {})()
            self.terminal_right = type("TerminalSide", (), {})()
            self.disconnected = False

        def disconnect_all(self):
            self.disconnected = True

    monkeypatch.setattr(access_control, "guard_app_access", lambda _code: None)
    monkeypatch.setattr(mod, "ConnectionManager", lambda: object())
    monkeypatch.setattr(mod, "CredentialManager", lambda: object())
    monkeypatch.setattr(mod, "MainframeNavScreen", FakeNavScreen)
    monkeypatch.setattr(mod, "DualTerminalScreen", FakeTerminalScreen)

    window = mod.MainframeWindow()
    try:
        assert isinstance(window, FramelessWindowBase)
        assert window.title_label.text() == "SuiteView - Mainframe Tools"
        assert window._header_colors == ("#1E5BA8", "#0D3A7A", "#082B5C")
        assert window._border_color == "#D4A017"
        assert window.minimumWidth() == 600
        assert window.minimumHeight() == 400
        assert window.size().width() == 1400
        assert window.size().height() == 800
        assert window.tab_widget.count() == 2
        assert window.user_button.text() == "👤 User"
    finally:
        window.close()


def test_search_content_window_uses_frameless_and_filter_tables(app):
    from suiteview.mainframe_nav.search_content_window import SearchContentWindow
    from suiteview.ui.widgets.filter_table_view import FilterTableView

    class FakeFtp:
        pass

    window = SearchContentWindow(FakeFtp())
    try:
        assert isinstance(window, FramelessWindowBase)
        assert window.title_label.text() == "🔍 Search Dataset Content"
        assert window._header_colors == ("#1E5BA8", "#0D3A7A", "#082B5C")
        assert window._border_color == "#D4A017"
        assert isinstance(window.dataset_table, FilterTableView)
        assert isinstance(window.results_table, FilterTableView)
    finally:
        window.close()
