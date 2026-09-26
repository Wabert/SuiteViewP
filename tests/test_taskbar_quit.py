"""Tray Quit must end the process or leave SuiteView visibly running, never neither."""

from types import SimpleNamespace
from unittest.mock import Mock

from PyQt6.QtWidgets import QWidget

from suiteview.taskbar_launcher import taskbar_system
from suiteview.taskbar_launcher.collaborators import TaskbarState
from suiteview.taskbar_launcher.taskbar_system import SystemTray


class _Vetoing(QWidget):
    def closeEvent(self, event):
        event.ignore()


def _bar(blocker=None):
    window = SimpleNamespace(close=Mock())
    state = TaskbarState(tray_icon=Mock())
    callbacks = SimpleNamespace(_unregister_appbar=Mock(), _bring_to_front=Mock())
    bar = SystemTray(window, state, callbacks=callbacks)
    bar._close_windows_for_quit = Mock(return_value=blocker)
    return SimpleNamespace(controller=bar, state=state, callbacks=callbacks, window=window)


def test_quit_exits_the_event_loop_without_a_cancellable_quit(monkeypatch):
    app = Mock()
    monkeypatch.setattr(taskbar_system, "QApplication", app)
    bar = _bar()
    bar.controller._quit_application()
    bar.state.tray_icon.hide.assert_called_once()
    bar.window.close.assert_called_once()
    app.exit.assert_called_once_with(0)
    app.quit.assert_not_called()


def test_window_that_stays_open_cancels_quit_but_keeps_tray_and_launcher(monkeypatch):
    app = Mock()
    monkeypatch.setattr(taskbar_system, "QApplication", app)
    blocker = Mock()
    bar = _bar(blocker)
    bar.controller._quit_application()
    bar.callbacks._bring_to_front.assert_called_once_with(blocker)
    bar.state.tray_icon.hide.assert_not_called()
    bar.callbacks._unregister_appbar.assert_not_called()
    bar.window.close.assert_not_called()
    app.exit.assert_not_called()


def test_close_windows_for_quit_reports_only_a_window_left_visible(qtbot):
    plain, hides, vetoing, hidden_vetoing = QWidget(), QWidget(), _Vetoing(), _Vetoing()
    for widget in (plain, hides, vetoing, hidden_vetoing):
        qtbot.addWidget(widget)

    def hide_on_close(event):  # SuiteViewTaskbar._setup_child_window pattern
        event.ignore()
        hides.hide()

    hides.closeEvent = hide_on_close
    launcher = QWidget()
    qtbot.addWidget(launcher)
    for widget in (plain, hides, vetoing, launcher):
        widget.show()

    assert SystemTray(launcher, TaskbarState())._close_windows_for_quit() is vetoing
    assert launcher.isVisible()

    vetoing.hide()
    assert SystemTray(launcher, TaskbarState())._close_windows_for_quit() is None
    assert not plain.isVisible()
    assert not hides.isVisible()
    assert launcher.isVisible()
