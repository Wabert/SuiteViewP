"""Tray Quit must end the process or leave SuiteView visibly running, never neither."""

from types import SimpleNamespace
from unittest.mock import Mock

from PyQt6.QtWidgets import QWidget

from suiteview.taskbar_launcher import suiteview_taskbar as taskbar
from suiteview.taskbar_launcher.suiteview_taskbar import SuiteViewTaskbar


class _Vetoing(QWidget):
    def closeEvent(self, event):
        event.ignore()


def _bar(blocker=None):
    return SimpleNamespace(
        administrator_window=None,
        _close_windows_for_quit=Mock(return_value=blocker),
        _bring_to_front=Mock(),
        _unregister_appbar=Mock(),
        tray_icon=Mock(),
        close=Mock(),
    )


def test_quit_exits_the_event_loop_without_a_cancellable_quit(monkeypatch):
    app = Mock()
    monkeypatch.setattr(taskbar, "QApplication", app)
    bar = _bar()
    SuiteViewTaskbar._quit_application(bar)
    bar.tray_icon.hide.assert_called_once()
    bar.close.assert_called_once()
    app.exit.assert_called_once_with(0)
    app.quit.assert_not_called()


def test_window_that_stays_open_cancels_quit_but_keeps_tray_and_launcher(monkeypatch):
    app = Mock()
    monkeypatch.setattr(taskbar, "QApplication", app)
    blocker = Mock()
    bar = _bar(blocker)
    SuiteViewTaskbar._quit_application(bar)
    bar._bring_to_front.assert_called_once_with(blocker)
    bar.tray_icon.hide.assert_not_called()
    bar._unregister_appbar.assert_not_called()
    bar.close.assert_not_called()
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

    assert SuiteViewTaskbar._close_windows_for_quit(launcher) is vetoing
    assert launcher.isVisible()

    vetoing.hide()
    assert SuiteViewTaskbar._close_windows_for_quit(launcher) is None
    assert not plain.isVisible()
    assert not hides.isVisible()
    assert launcher.isVisible()
