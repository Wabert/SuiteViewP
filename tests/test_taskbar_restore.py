"""Launcher activation and verified AppBar reservation, without live data."""

from types import MethodType, SimpleNamespace
from unittest.mock import Mock

import pytest

from suiteview.taskbar_launcher import appbar, single_instance
from suiteview.taskbar_launcher.suiteview_taskbar import SuiteViewTaskbar


@pytest.fixture
def instance_apis(monkeypatch):
    kernel = SimpleNamespace(CreateMutexW=Mock(return_value=123), CloseHandle=Mock())
    user = SimpleNamespace(FindWindowW=Mock(return_value=456))
    monkeypatch.setattr(single_instance.sys, "platform", "win32")
    monkeypatch.setattr(single_instance.ctypes, "WinDLL", Mock(return_value=kernel))
    monkeypatch.setattr(single_instance.ctypes, "get_last_error", lambda: 183)
    monkeypatch.setattr(single_instance, "_user32", lambda: user)
    monkeypatch.setattr(single_instance, "_mutex_handles", [])
    activate = Mock()
    monkeypatch.setattr(single_instance, "request_activation", activate)
    return kernel, user, activate


def test_first_instance_retains_mutex(instance_apis, monkeypatch):
    kernel, user, activate = instance_apis
    monkeypatch.setattr(single_instance.ctypes, "get_last_error", lambda: 0)
    assert single_instance.acquire_or_activate()
    assert single_instance._mutex_handles == [123]
    kernel.CloseHandle.assert_not_called()
    user.FindWindowW.assert_not_called()
    activate.assert_not_called()


@pytest.mark.parametrize("title", ["SuiteView"])
def test_duplicate_launch_requests_qt_restore(instance_apis, title):
    kernel, user, activate = instance_apis
    user.FindWindowW.side_effect = lambda _, candidate: 456 if candidate == title else 0
    assert not single_instance.acquire_or_activate()
    activate.assert_called_once_with(456)
    kernel.CloseHandle.assert_called_once_with(123)
    assert single_instance._mutex_handles == []


def test_local_activation_cannot_target_live_instance(instance_apis):
    kernel, user, activate = instance_apis
    assert not single_instance.acquire_or_activate(
        "SuiteView_Local_SingleInstance_Mutex", ("SuiteView (LOCAL DATA)",))
    assert kernel.CreateMutexW.call_args.args[2] == "SuiteView_Local_SingleInstance_Mutex"
    user.FindWindowW.assert_called_once_with(None, "SuiteView (LOCAL DATA)")
    activate.assert_called_once_with(456)


def test_missing_window_does_not_start_or_kill_another_process(instance_apis, caplog):
    _, user, activate = instance_apis
    user.FindWindowW.return_value = 0
    assert not single_instance.acquire_or_activate()
    activate.assert_not_called()
    assert "launcher is not ready" in caplog.text


def test_mutex_error_is_not_treated_as_first_instance(instance_apis, monkeypatch):
    kernel, _, activate = instance_apis
    kernel.CreateMutexW.return_value = 0
    monkeypatch.setattr(single_instance.ctypes, "get_last_error", lambda: 5)
    with pytest.raises(OSError):
        single_instance.acquire_or_activate()
    activate.assert_not_called()


def test_activation_post_failure_is_reported(monkeypatch):
    user = SimpleNamespace(
        GetWindowThreadProcessId=Mock(return_value=0),
        PostMessageW=Mock(return_value=0),
    )
    monkeypatch.setattr(single_instance, "_user32", lambda: user)
    monkeypatch.setattr(single_instance, "activation_message", lambda: 0xC123)
    with pytest.raises(OSError):
        single_instance.request_activation(456)
    user.PostMessageW.assert_called_once_with(456, 0xC123, 0, 0)


@pytest.mark.parametrize("hwnd,rects", [(0, None), (123, None)])
def test_unreadable_work_area_is_not_success(monkeypatch, hwnd, rects):
    monkeypatch.setattr(appbar, "IS_WINDOWS", True)
    monkeypatch.setattr(appbar, "monitor_rects", lambda _: rects)
    assert not appbar.space_reserved(hwnd, 950)


@pytest.mark.parametrize("bottom,expected", [(950, True), (952, True), (992, False)])
def test_work_area_readback(monkeypatch, bottom, expected):
    monkeypatch.setattr(appbar, "IS_WINDOWS", True)
    monkeypatch.setattr(
        appbar, "monitor_rects",
        lambda _: ((0, 0, 1920, 1080), (0, 0, 1920, bottom)),
    )
    assert appbar.space_reserved(123, 950) == expected


@pytest.mark.parametrize("failed_message", [appbar.ABM_QUERYPOS, appbar.ABM_SETPOS])
def test_failed_shell_negotiation_removes_registration(monkeypatch, failed_message):
    monkeypatch.setattr(appbar, "IS_WINDOWS", True)
    user = SimpleNamespace(RegisterWindowMessageW=Mock(return_value=0xC123),
                           SetWindowPos=Mock(return_value=1))
    shell = SimpleNamespace(SHAppBarMessage=Mock(
        side_effect=lambda message, _: message != failed_message))
    monkeypatch.setattr(appbar, "_apis", lambda: (user, shell))
    monkeypatch.setattr(
        appbar, "monitor_rects",
        lambda _: ((0, 0, 1920, 1080), (0, 0, 1920, 1032)),
    )
    remove = Mock()
    monkeypatch.setattr(appbar, "unregister", remove)
    assert appbar.register_bottom(123, 42) is None
    assert remove.call_count == 2
    user.SetWindowPos.assert_not_called()


@pytest.mark.parametrize("rect", [None, (0, 950, 1920, 992)])
def test_failed_docking_retries_once_and_notifies(monkeypatch, rect):
    register = Mock(return_value=rect)
    monkeypatch.setattr(appbar, "register_bottom", register)
    monkeypatch.setattr(appbar, "space_reserved", Mock(return_value=False))
    monkeypatch.setattr(appbar, "unregister", Mock())
    bar = SimpleNamespace(
        winId=lambda: 123, devicePixelRatioF=lambda: 1.5,
        _appbar_registered=False, _notify_docking_failure=Mock(),
    )
    bar._register_appbar = MethodType(SuiteViewTaskbar._register_appbar, bar)
    bar._register_appbar(42)
    assert register.call_count == 2
    register.assert_called_with(123, 63)
    assert not bar._appbar_registered
    bar._notify_docking_failure.assert_called_once()


@pytest.mark.parametrize("hidden,visible,compact", [
    (True, False, True), (True, True, True), (False, False, True),
    (False, True, False),
])
def test_redock_does_not_reserve_for_hidden_or_undocked_bar(hidden, visible, compact):
    bar = SimpleNamespace(
        _hidden_to_tray=hidden, _is_compact_mode=compact,
        isVisible=lambda: visible, _register_appbar=Mock(),
    )
    SuiteViewTaskbar._redock_appbar(bar)
    bar._register_appbar.assert_not_called()
