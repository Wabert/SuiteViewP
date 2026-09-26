"""Tray menu wiring without starting a launcher or registering an AppBar."""

import os
from types import SimpleNamespace
from unittest.mock import Mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PyQt6.QtGui import QIcon
from PyQt6.QtWidgets import QApplication, QSystemTrayIcon, QWidget

from suiteview.taskbar_launcher.collaborators import TaskbarState
from suiteview.taskbar_launcher.taskbar_system import SystemTray


@pytest.fixture
def tray(monkeypatch):
    app = QApplication.instance() or QApplication([])
    monkeypatch.setattr(QSystemTrayIcon, "show", lambda self: None)
    host = QWidget()
    callbacks = SimpleNamespace(_quit_application=Mock(), _show_from_tray=Mock())
    tray = SystemTray(host, TaskbarState(), callbacks=callbacks)
    tray._build_suiteview_icon = lambda size: QIcon()
    tray._setup_system_tray()
    yield SimpleNamespace(controller=tray, callbacks=callbacks)
    tray.state.tray_icon.hide()
    tray._tray_menu.close()
    tray._tray_menu.deleteLater()
    host.deleteLater()
    app.processEvents()


def test_context_menu_contains_only_enabled_quit(tray):
    actions = tray.controller.state.tray_icon.contextMenu().actions()
    assert [action.text() for action in actions] == ["Quit SuiteView"]
    assert actions[0].isEnabled()
    assert actions[0].isVisible()
    assert not actions[0].isSeparator()
    actions[0].trigger()
    tray.callbacks._quit_application.assert_called_once()
    tray.callbacks._show_from_tray.assert_not_called()


@pytest.mark.parametrize("reason", [
    QSystemTrayIcon.ActivationReason.Trigger,
    QSystemTrayIcon.ActivationReason.DoubleClick,
])
def test_tray_click_still_restores_launcher(tray, reason):
    tray.controller.state.tray_icon.activated.emit(reason)
    tray.callbacks._show_from_tray.assert_called_once_with()
    tray.callbacks._quit_application.assert_not_called()


def test_tray_context_click_does_not_restore_or_quit(tray):
    tray.controller.state.tray_icon.activated.emit(QSystemTrayIcon.ActivationReason.Context)
    tray.callbacks._show_from_tray.assert_not_called()
    tray.callbacks._quit_application.assert_not_called()
