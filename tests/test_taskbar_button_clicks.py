"""Real taskbar and FileNav buttons reach their handlers when clicked.

The collaborator forwarders on SuiteViewTaskbar and FileExplorerTab accept
``*args``, so PyQt passes ``clicked``/``triggered``'s ``checked`` flag to
them. Forwarding that flag to a no-argument handler raised TypeError, and the
PolView, Illustration, ABR, Audit, FileNav, screenshot, scratchpad, history,
maximize, close-to-tray and Quit controls did nothing. The Tools menu uses
``QMenu.addAction(text, slot)``, which passes no flag; it is covered as a guard.
"""

from __future__ import annotations

import os
from unittest.mock import Mock

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtWidgets import QApplication, QSystemTrayIcon


@pytest.fixture
def taskbar(monkeypatch, tmp_path):
    monkeypatch.setenv("SUITEVIEW_PROFILE_DIR", str(tmp_path / "profile"))
    app = QApplication.instance() or QApplication([])
    from suiteview.core import access_control
    from suiteview.core.access_control import APP_CODES, EffectiveAccess
    from suiteview.taskbar_launcher import taskbar_window
    from suiteview.taskbar_launcher.taskbar_window import SuiteViewTaskbar

    rights = EffectiveAccess("CLICK", "ADMIN", True, True, True,
                             apps=frozenset((*APP_CODES, "ADMINISTRATOR")), developer=True)
    monkeypatch.setattr(access_control, "guard_app_access", lambda _code: None)
    monkeypatch.setattr(access_control, "get_access", lambda refresh=False: rights)
    monkeypatch.setattr(access_control, "can_access_app", lambda _code: True)
    monkeypatch.setattr(QSystemTrayIcon, "show", lambda self: None)
    monkeypatch.setattr(taskbar_window, "get_access", lambda refresh=True: rights)
    monkeypatch.setattr(taskbar_window, "activation_message", lambda: 0)
    monkeypatch.setattr(SuiteViewTaskbar, "_register_appbar", lambda *a, **k: None)
    monkeypatch.setattr(SuiteViewTaskbar, "_unregister_appbar", lambda *a, **k: None)
    window = SuiteViewTaskbar()
    yield window
    window.hide()
    window.deleteLater()
    app.processEvents()


_COLLABORATORS = ("app_launcher", "system_tray", "modes", "tabs", "chrome")


def _spy_on(taskbar, monkeypatch, handler):
    """Replace ``handler`` on every collaborator that defines it with one spy."""
    spy = Mock()
    owners = [getattr(taskbar, name) for name in _COLLABORATORS
              if hasattr(getattr(taskbar, name), handler)]
    assert owners, handler
    for owner in owners:
        monkeypatch.setattr(owner, handler, spy)
    return spy


@pytest.mark.parametrize("button,handler", [
    ("polview_btn", "_polview_btn_clicked"),
    ("illustration_btn", "_illustration_btn_clicked"),
    ("abrquote_btn", "_abrquote_btn_clicked"),
    ("audit_btn", "_open_audit"),
    ("filenav_btn", "_open_file_nav"),
    ("quick_screenshot_btn", "_take_quick_screenshot"),
    ("scratchpad_window_btn", "_toggle_scratchpad_window"),
    ("file_history_btn", "_toggle_file_open_history"),
    ("maximize_btn", "_toggle_maximize"),
    ("close_btn", "_hide_to_tray"),
])
def test_header_button_click_reaches_handler(taskbar, monkeypatch, button, handler):
    spy = _spy_on(taskbar, monkeypatch, handler)
    widget = getattr(taskbar.chrome, button, None) or getattr(taskbar, button)
    widget.click()
    spy.assert_called_once_with()


def test_tray_quit_action_reaches_handler(taskbar, monkeypatch):
    spy = _spy_on(taskbar, monkeypatch, "_quit_application")
    taskbar.system_tray._quit_action.trigger()
    spy.assert_called_once_with()


@pytest.mark.parametrize("title,handler", [
    ("View Screenshots", "_open_screenshot"),
    ("Administrator", "_open_administrator"),
    ("Mainframe Navigator", "_open_mainframe"),
    ("Rate Manager", "_open_rate_manager"),
    ("DB2 Table Check", "_open_db2_table_check"),
    ("Email Attachments", "_open_email_attachments"),
    ("Refresh Permissions", "_refresh_permissions"),
    ("📁 App Data Location", "_open_app_data_location"),
])
def test_tools_menu_action_reaches_handler(taskbar, monkeypatch, title, handler):
    spy = _spy_on(taskbar, monkeypatch, handler)
    action = next(a for a in taskbar.chrome.tools_menu.actions() if a.text() == title)
    action.setEnabled(True)
    action.trigger()
    spy.assert_called_once_with()
