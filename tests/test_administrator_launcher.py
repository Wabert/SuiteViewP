import os
import sys
from types import SimpleNamespace
from unittest.mock import Mock
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PyQt6.QtWidgets import QApplication, QMenu

from suiteview.administrator import launcher


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


@pytest.mark.parametrize("allowed", [True, False])
def test_probe_returns_authorization_not_all_apps(monkeypatch, allowed):
    monkeypatch.setattr(launcher.AccessRepository, "is_admin", lambda self: allowed)
    probe = launcher._AdminProbe()
    result = []
    probe.signals.completed.connect(result.append)
    probe.run()
    assert result == [allowed]


def test_probe_failure_logs_and_denies(monkeypatch, caplog):
    def fail(self):
        raise RuntimeError("Connection unavailable")
    monkeypatch.setattr(launcher.AccessRepository, "is_admin", fail)
    probe = launcher._AdminProbe()
    result = []
    probe.signals.completed.connect(result.append)
    probe.run()
    assert result == [False]
    assert "Connection unavailable" in caplog.text


def test_menu_hidden_until_authorized_and_refreshed_each_open(app, monkeypatch):
    monkeypatch.setattr(launcher, "has_developer_access", lambda: False)
    started = []
    monkeypatch.setattr(launcher.QThreadPool, "globalInstance",
                        lambda: type("Pool", (), {"start": lambda self, probe: started.append(probe)})())
    menu = QMenu()
    action = menu.addAction("Administrator")
    access = launcher.AdministratorMenuAccess(menu, action)
    assert not action.isVisible()
    menu.aboutToShow.emit()
    assert not action.isVisible()
    assert len(started) == 1
    access.refresh()
    assert len(started) == 1
    started[0].signals.completed.emit(True)
    assert action.isVisible()
    menu.aboutToShow.emit()
    assert not action.isVisible()
    started[1].signals.completed.emit(False)
    assert not action.isVisible()


def test_source_menu_is_visible_without_database_probe(app, monkeypatch):
    monkeypatch.setattr(launcher, "has_developer_access", lambda: True)
    pool = Mock()
    monkeypatch.setattr(launcher.QThreadPool, "globalInstance", pool)
    menu = QMenu()
    action = menu.addAction("Administrator")
    access = launcher.AdministratorMenuAccess(menu, action)
    assert action.isVisible()
    menu.aboutToShow.emit()
    access.refresh()
    assert action.isVisible()
    pool.assert_not_called()


def test_taskbar_reuses_window_but_rechecks_admin(monkeypatch):
    from suiteview.administrator import service
    from suiteview.taskbar_launcher.suiteview_taskbar import SuiteViewTaskbar

    window = Mock()
    factory = Mock(return_value=window)
    monkeypatch.setitem(sys.modules, "suiteview.administrator.window",
                        SimpleNamespace(AdministratorWindow=factory))
    authorize = Mock()
    monkeypatch.setattr(service.AccessRepository, "load", authorize)
    bar = SimpleNamespace(
        administrator_window=None, _build_suiteview_icon=Mock(),
        _administrator_menu_access=SimpleNamespace(refresh=Mock()),
        _bring_to_front=Mock(), _refresh_permissions=Mock(),
    )
    SuiteViewTaskbar._open_administrator(bar)
    SuiteViewTaskbar._open_administrator(bar)
    assert authorize.call_count == 2
    factory.assert_called_once()
    assert bar.administrator_window is window
    assert bar._bring_to_front.call_count == 2
    window.permissions_changed.connect.assert_any_call(bar._administrator_menu_access.refresh)
    window.permissions_changed.connect.assert_any_call(bar._refresh_permissions)
    # The taskbar must not replace the editor's dirty-close guard.
    assert "closeEvent" not in window.__dict__


def test_taskbar_denial_hides_existing_window_and_reports(monkeypatch):
    from suiteview.administrator import service
    from suiteview.taskbar_launcher import suiteview_taskbar as taskbar

    monkeypatch.setattr(service.AccessRepository, "load",
                        Mock(side_effect=PermissionError("ADMIN access revoked")))
    warning = Mock()
    monkeypatch.setattr(taskbar.QMessageBox, "warning", warning)
    bar = SimpleNamespace(administrator_window=Mock(), _bring_to_front=Mock())
    taskbar.SuiteViewTaskbar._open_administrator(bar)
    bar.administrator_window.hide.assert_called_once()
    bar._bring_to_front.assert_not_called()
    assert "ADMIN access revoked" in warning.call_args.args[2]


def test_taskbar_quit_respects_cancelled_admin_close():
    from suiteview.taskbar_launcher.suiteview_taskbar import SuiteViewTaskbar

    bar = SimpleNamespace(administrator_window=Mock())
    bar.administrator_window.close.return_value = False
    SuiteViewTaskbar._quit_application(bar)
    bar.administrator_window.close.assert_called_once()
