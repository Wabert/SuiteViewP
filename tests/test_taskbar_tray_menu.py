"""Tray menu wiring without starting a launcher or registering an AppBar."""

import os
from types import MethodType
from unittest.mock import Mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PyQt6.QtGui import QIcon
from PyQt6.QtWidgets import QApplication, QSystemTrayIcon, QWidget

from suiteview.taskbar_launcher.suiteview_taskbar import SuiteViewTaskbar


@pytest.fixture
def tray(monkeypatch):
    app = QApplication.instance() or QApplication([])
    monkeypatch.setattr(QSystemTrayIcon, "show", lambda self: None)
    host = QWidget()
    host._build_suiteview_icon = lambda size: QIcon()
    host._quit_application = Mock()
    host._show_from_tray = Mock()
    host._on_tray_activated = MethodType(SuiteViewTaskbar._on_tray_activated, host)
    SuiteViewTaskbar._setup_system_tray(host)
    yield host
    host.tray_icon.hide()
    host._tray_menu.close()
    host._tray_menu.deleteLater()
    host.deleteLater()
    app.processEvents()


def test_context_menu_contains_only_enabled_quit(tray):
    actions = tray.tray_icon.contextMenu().actions()
    assert [action.text() for action in actions] == ["Quit SuiteView"]
    assert actions[0].isEnabled()
    assert actions[0].isVisible()
    assert not actions[0].isSeparator()
    actions[0].trigger()
    tray._quit_application.assert_called_once()
    tray._show_from_tray.assert_not_called()


@pytest.mark.parametrize("reason", [
    QSystemTrayIcon.ActivationReason.Trigger,
    QSystemTrayIcon.ActivationReason.DoubleClick,
])
def test_tray_click_still_restores_launcher(tray, reason):
    tray.tray_icon.activated.emit(reason)
    tray._show_from_tray.assert_called_once_with()
    tray._quit_application.assert_not_called()


def test_tray_context_click_does_not_restore_or_quit(tray):
    tray.tray_icon.activated.emit(QSystemTrayIcon.ActivationReason.Context)
    tray._show_from_tray.assert_not_called()
    tray._quit_application.assert_not_called()
