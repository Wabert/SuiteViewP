"""Application authorization precedes construction, launch and cached-window reuse."""

import importlib
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from suiteview.core import access_control as access


WINDOWS = [
    ("suiteview.polview.ui.main_window", "GetPolicyWindow", "POLVIEW"),
    ("suiteview.illustration.ui.main_window", "IllustrationWindow", "RERUN"),
    ("suiteview.abrquote.ui.abr_window", "ABRQuoteWindow", "ABR"),
    ("suiteview.file_nav.file_explorer_core", "FileExplorerCore", "FILENAV"),
    ("suiteview.agent_chat.window", "AgentChatWindow", "ALBERT"),
    ("suiteview.mainframe_nav.mainframe_window", "MainframeWindow", "MAINFRAMENAV"),
    ("suiteview.screenshot_manager.screenshot_manager_window",
     "ScreenShotManagerWindow", "SCREENSHOT"),
    ("suiteview.ui.email_attachments_window", "EmailAttachmentsWindow", "EMAILATTACHMENTS"),
    ("suiteview.scratchpad.scratchpad_panel", "ScratchPadPanel", "SCRATCHPAD"),
    ("suiteview.ui.widgets.file_open_history", "FileOpenHistoryPanel", "HISTORY"),
]


@pytest.fixture
def denied(monkeypatch):
    rights = access.EffectiveAccess("TEST", "RESTRICTED", False, False, False)
    check = Mock(return_value=rights)
    monkeypatch.setattr(access, "get_access", check)
    return check


@pytest.mark.parametrize("module_name,class_name,app_code", WINDOWS)
def test_constructor_denies_before_any_initialization(denied, module_name, class_name, app_code):
    cls = getattr(importlib.import_module(module_name), class_name)
    untouched = SimpleNamespace()
    with pytest.raises(access.AccessDeniedError, match=app_code):
        cls.__init__(untouched)
    assert vars(untouched) == {}
    denied.assert_called_once_with(refresh=True)


@pytest.mark.parametrize("module_name,class_name,app_code", WINDOWS)
def test_constructor_fails_closed_when_permissions_unavailable(
    denied, module_name, class_name, app_code,
):
    cls = getattr(importlib.import_module(module_name), class_name)
    denied.side_effect = access.AccessUnavailableError("Cannot verify permissions")
    untouched = SimpleNamespace()
    with pytest.raises(access.AccessUnavailableError, match="Cannot verify"):
        cls.__init__(untouched)
    assert vars(untouched) == {}


@pytest.mark.parametrize("module_name,function_name,app_code", [
    ("suiteview.polview.main", "create_viewer", "POLVIEW"),
    ("suiteview.polview.main", "main", "POLVIEW"),
    ("suiteview.illustration.main", "create_illustration_window", "RERUN"),
    ("suiteview.abrquote.main", "create_abrquote_window", "ABR"),
    ("suiteview.taskbar_launcher.albert_launcher", "launch_albert", "ALBERT"),
])
def test_standalone_launch_denies_before_side_effects(
    denied, monkeypatch, module_name, function_name, app_code,
):
    module = importlib.import_module(module_name)
    if hasattr(module, "QApplication"):
        application = Mock(side_effect=AssertionError("Must not initialize Qt"))
        application.instance.side_effect = AssertionError("Must not access Qt")
        monkeypatch.setattr(module, "QApplication", application)
    else:
        monkeypatch.setattr(module.subprocess, "Popen",
                            Mock(side_effect=AssertionError("Must not spawn Albert")))
    with pytest.raises(access.AccessDeniedError, match=app_code):
        getattr(module, function_name)()
    denied.assert_called_once_with(refresh=True)


def test_scratchpad_factory_denies_before_window_creation(denied):
    from suiteview.scratchpad.scratchpad_panel import ScratchPadWindow

    with pytest.raises(access.AccessDeniedError, match="SCRATCHPAD"):
        ScratchPadWindow.open()
    denied.assert_called_once_with(refresh=True)


@pytest.mark.parametrize("module_name,class_name,method_name,launcher_name,target", [
    ("suiteview.polview.ui.main_window", "GetPolicyWindow",
     "_open_in_illustrator", "_illustration_launcher", "RERUN"),
    ("suiteview.illustration.ui.main_window", "IllustrationWindow",
     "_open_in_polview", "_polview_launcher", "POLVIEW"),
])
def test_cross_app_cached_launcher_rechecks_access(
    monkeypatch, module_name, class_name, method_name, launcher_name, target,
):
    from PyQt6.QtWidgets import QMessageBox

    cls = getattr(importlib.import_module(module_name), class_name)
    allowed = access.EffectiveAccess("TEST", "RESTRICTED", False, False, False,
                                     frozenset({target}))
    denied = access.EffectiveAccess("TEST", "RESTRICTED", False, False, False)
    check = Mock(side_effect=[allowed, denied])
    monkeypatch.setattr(access, "get_access", check)
    warning = Mock()
    monkeypatch.setattr(QMessageBox, "warning", warning)
    launcher = Mock()
    existing_window = SimpleNamespace(
        _current_policy="TESTPOLICY", _current_region="CKPR",
        _policy_info={"CompanyCode": "01"},
        **{launcher_name: launcher},
    )

    getattr(cls, method_name)(existing_window, False)
    launcher.assert_called_once_with("TESTPOLICY", "CKPR", "01")
    getattr(cls, method_name)(existing_window, False)
    launcher.assert_called_once()
    warning.assert_called_once()
    assert target in warning.call_args.args[2]
    assert check.call_count == 2
    assert all(call.kwargs == {"refresh": True} for call in check.call_args_list)


@pytest.mark.parametrize("unavailable", [False, True])
def test_history_reopen_denies_before_refresh(denied, monkeypatch, unavailable):
    from PyQt6.QtWidgets import QMessageBox
    from suiteview.ui.widgets.file_open_history import FileOpenHistoryPanel

    if unavailable:
        denied.side_effect = access.AccessUnavailableError("Cannot verify HISTORY")
    warning = Mock()
    monkeypatch.setattr(QMessageBox, "warning", warning)
    untouched = SimpleNamespace()
    FileOpenHistoryPanel.show_under(untouched, None)
    warning.assert_called_once()
    assert "HISTORY" in warning.call_args.args[2]
    assert vars(untouched) == {}


def test_albert_button_denial_is_explicit_without_launch(denied, monkeypatch):
    from PyQt6.QtWidgets import QMessageBox
    from suiteview.taskbar_launcher import albert_launcher

    launch = Mock()
    monkeypatch.setattr(albert_launcher, "launch_albert", launch)
    warning = Mock()
    monkeypatch.setattr(QMessageBox, "warning", warning)
    albert_launcher.AlbertButton._open(SimpleNamespace())
    launch.assert_not_called()
    warning.assert_called_once()
    assert "ALBERT" in warning.call_args.args[2]
