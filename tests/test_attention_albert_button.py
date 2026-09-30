"""Attention Albert task-bar button: badge, timer ticks, alerts and settings menu (synthetic)."""
import ast
from pathlib import Path
import sys
from types import SimpleNamespace

import pytest

from suiteview.taskbar_launcher import attention_albert


@pytest.fixture
def app(monkeypatch):
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    from PyQt6.QtWidgets import QApplication
    application = QApplication.instance() or QApplication([])
    yield application
    application.processEvents()


@pytest.fixture
def home(tmp_path, monkeypatch):
    (tmp_path / "aai.py").write_text("# synthetic\n", encoding="utf-8")
    monkeypatch.setattr(attention_albert, "AAI_HOME", tmp_path)
    return tmp_path


@pytest.fixture(autouse=True)
def private_pipes(monkeypatch, tmp_path):
    # Never touch the real SuiteView/AAI window pipes of whoever runs the tests.
    suffix = tmp_path.name
    monkeypatch.setattr(attention_albert, "CONTROL_SERVER", "test-aai-control-" + suffix)
    monkeypatch.setattr(attention_albert, "WINDOW_SERVER", "test-aai-window-" + suffix)


def test_service_is_found_beside_a_checkout_or_worktree(tmp_path):
    service = tmp_path / "Email Manager" / "attention-albert" / "aai.py"
    service.parent.mkdir(parents=True)
    service.write_text("# synthetic\n", encoding="utf-8")
    for checkout in (("SuiteViewP",), ("SuiteViewP.worktrees", "feature")):
        module = tmp_path.joinpath(*checkout, "suiteview", "taskbar_launcher", "attention_albert.py")
        assert attention_albert._find_home(module) == service.parent


def test_missing_service_disables_the_button(app, tmp_path, monkeypatch):
    monkeypatch.setattr(attention_albert, "AAI_HOME", tmp_path / "missing")
    button = attention_albert.AttentionAlbertButton(start_timer=False)
    assert not button.isEnabled() and "not found" in button.toolTip()
    button.close()


def test_offscreen_instances_never_start_the_mailbox_timer(app, home):
    button = attention_albert.AttentionAlbertButton()
    assert not button.timer.isActive()
    button.close()


def test_tick_runs_the_service_and_updates_badge_and_tray(app, home, monkeypatch):
    from PyQt6.QtWidgets import QWidget
    messages = []
    tray = SimpleNamespace(showMessage=lambda *args: messages.append(args),
                           messageClicked=SimpleNamespace(connect=lambda slot: None))
    host = QWidget()
    host.state = SimpleNamespace(tray_icon=tray)
    button = attention_albert.AttentionAlbertButton(host, start_timer=False)
    calls = []
    monkeypatch.setattr(button, "_process", lambda arguments, finished: calls.append(arguments) or object())
    button.tick()
    assert calls == []  # nothing runs until permissions confirm the owner
    button.set_allowed(True)
    button.tick()
    assert calls == []  # ...and the owner opens the feature (closed by default)
    button.set_open(True)
    button.tick()
    button.tick()  # a running tick is not doubled
    assert calls == [["tick"]]
    button._tick_process = None
    button.tick(scan_now=True)
    assert calls[-1] == ["tick", "--scan-now"]
    button.apply_result({"ok": True, "summary": {"needs_attention": 3, "red": True, "enabled": True,
                                                 "interval_minutes": 5, "work_hours_only": True,
                                                 "working": 1, "last_scan_result": "1 new"},
                         "alerts": [{"aai_id": "AAI-0001", "kind": "captured", "text": "New request"}]})
    assert "3 need you" in button.toolTip() and "Watching inbox: on" in button.toolTip()
    assert button.property("watching") == "true"
    assert messages and messages[0][0] == "Attention Albert AAI-0001"
    assert button.last_alert_id == "AAI-0001"
    button.grab()  # paints the badge without error
    host.close()


def test_menu_settings_and_open(app, home, monkeypatch):
    button = attention_albert.AttentionAlbertButton(start_timer=False)
    button.set_allowed(True)
    button.set_open(True)
    actions = []
    monkeypatch.setattr(button, "_run_action", lambda arguments: actions.append(arguments))
    button.summary = {"enabled": False, "interval_minutes": 5, "work_hours_only": True}
    button.show_menu(button.rect().center())
    menu = button._menu
    watch = [action for action in menu.actions() if action.text().startswith("Watch inbox")][0]
    watch.setChecked(True)
    interval = [action for action in menu.actions() if action.text() == "Scan every"][0].menu()
    [action for action in interval.actions() if action.text() == "15 min"][0].trigger()
    assert actions == [["settings", "--enabled", "on"], ["settings", "--interval", "15"]]
    menu.close()
    launched = []
    monkeypatch.setattr(attention_albert.subprocess, "Popen",
                        lambda args, **kwargs: launched.append((args, kwargs)))
    button.open_list("AAI-0002")
    args, kwargs = launched[0]
    assert args == [sys.executable, "-B", str(home / "aai_window.py"), "--select", "AAI-0002"]
    assert kwargs["cwd"] == str(home) and not kwargs.get("shell")
    button.close()


def test_button_sits_right_of_the_spacer_and_is_owner_gated():
    launcher_dir = Path(attention_albert.__file__).parent
    ui = (launcher_dir / "taskbar_ui.py").read_text(encoding="utf-8")
    system = ast.unparse(ast.parse((launcher_dir / "taskbar_system.py").read_text(encoding="utf-8")))
    spacer = ui.index("header_layout.addWidget(self.header_spacer)")
    aai = ui.index("header_layout.addWidget(self.aai_btn)")
    assert ui.index("header_layout.addWidget(self.albert_btn)") < spacer < aai
    assert aai < ui.index("header_layout.addWidget(self.minimize_btn)")
    assert "'aai_btn')" not in system  # not tied to an app grant
    assert "aai_btn.set_allowed(access is not None and access.shows_aai_button)" in system


def test_only_the_owner_or_a_source_run_gets_the_button():
    from suiteview.core import access_control as access
    grant = frozenset({"ALBERT", "ATTENTIONALBERT"})
    other = access.EffectiveAccess("PERSON01", "ADMIN", True, True, True, grant)
    owner = access.EffectiveAccess("AB7Y02", "BUSINESS", False, False, False)
    assert access.AAI_BUTTON_OWNER == "AB7Y02"
    assert not other.shows_aai_button  # an ATTENTIONALBERT grant or AllApps is not enough
    assert owner.shows_aai_button
    assert access._DEVELOPER_ACCESS.shows_aai_button  # design mode: whoever runs it


def test_hidden_until_allowed_and_timer_only_for_the_owner(app, home, monkeypatch):
    button = attention_albert.AttentionAlbertButton()
    assert button.isHidden() and not button.timer.isActive()
    monkeypatch.setattr(attention_albert.QApplication, "platformName", staticmethod(lambda: "windows"))
    monkeypatch.setattr(attention_albert.QTimer, "singleShot", staticmethod(lambda *args: None))
    button.set_allowed(False)
    assert button.isHidden() and not button.isEnabled() and not button.timer.isActive()
    calls = []
    monkeypatch.setattr(button, "_process", lambda arguments, finished: calls.append(arguments) or object())
    button.tick()
    assert calls == []  # a non-owner never runs the mailbox service
    button.set_allowed(True)
    assert button.isHidden() and not button.timer.isActive()  # closed until the owner opens it
    button.set_open(True)
    assert not button.isHidden() and button.isEnabled() and button.timer.isActive()
    button.set_allowed(False)
    assert not button.timer.isActive() and not button.feature_open
    button.close()


def test_feature_starts_closed_and_opens_and_closes_from_tools(app, home, monkeypatch):
    from PyQt6.QtGui import QAction
    monkeypatch.setattr(attention_albert.QApplication, "platformName", staticmethod(lambda: "windows"))
    monkeypatch.setattr(attention_albert.QTimer, "singleShot", staticmethod(lambda *args: None))
    button = attention_albert.AttentionAlbertButton()
    action = QAction("Attention Albert")
    button.bind_tools_action(action)
    assert not action.isVisible()  # only the owner sees the Tools switch
    button.set_allowed(True)
    assert action.isVisible() and action.isCheckable() and not action.isChecked()
    assert button.isHidden() and not button.timer.isActive()
    action.setChecked(True)
    assert button.feature_open and not button.isHidden() and button.timer.isActive()
    button.set_allowed(True)  # a permissions refresh doesn't reopen or close it
    assert button.feature_open
    action.setChecked(False)
    assert button.isHidden() and not button.timer.isActive() and not button.feature_open
    action.setChecked(True)
    button.summary = {"enabled": True, "interval_minutes": 5, "work_hours_only": True}
    button.show_menu(button.rect().center())
    close = [item for item in button._menu.actions() if item.text() == "Close Attention Albert"][0]
    close.trigger()
    assert button.isHidden() and not action.isChecked() and not button.timer.isActive()
    button.close()


def test_list_window_close_button_closes_the_feature(app, home, monkeypatch):
    from PyQt6.QtNetwork import QLocalSocket
    monkeypatch.setattr(attention_albert.QApplication, "platformName", staticmethod(lambda: "windows"))
    monkeypatch.setattr(attention_albert.QTimer, "singleShot", staticmethod(lambda *args: None))
    button = attention_albert.AttentionAlbertButton()
    button.set_allowed(True)
    button.set_open(True)
    socket = QLocalSocket()
    socket.connectToServer(attention_albert.CONTROL_SERVER)
    assert socket.waitForConnected(1000)
    socket.write(b"close")
    socket.waitForBytesWritten(1000)
    for _ in range(50):
        app.processEvents()
        if not button.feature_open:
            break
    assert not button.feature_open and button.isHidden() and not button.timer.isActive()
    socket.disconnectFromServer()
    button.set_allowed(False)  # stops listening
    assert button._control_server is None
    button.close()


def test_click_is_rechecked_against_the_owner(app, home, monkeypatch):
    from suiteview.core import access_control as access
    button = attention_albert.AttentionAlbertButton(start_timer=False)
    warnings, opened = [], []
    monkeypatch.setattr(attention_albert.QMessageBox, "warning", lambda *args: warnings.append(args))
    monkeypatch.setattr(button, "open_list", lambda select=None: opened.append(select))
    monkeypatch.setattr(attention_albert, "guard_aai_button",
                        lambda: (_ for _ in ()).throw(access.AccessDeniedError("only AB7Y02")))
    button._open()
    assert opened == [] and "only AB7Y02" in warnings[0][2]
    monkeypatch.setattr(attention_albert, "guard_aai_button", lambda: None)
    button._open()
    assert opened == [None]
    button.close()


def test_attention_albert_is_an_administrator_app_code():
    from suiteview.core.access_control import APP_CODES
    assert "ATTENTIONALBERT" in APP_CODES


def test_packaged_exe_hides_the_button_even_for_the_owner(app, home, monkeypatch):
    from suiteview.core import build_env
    monkeypatch.setattr(build_env.sys, "frozen", True, raising=False)
    button = attention_albert.AttentionAlbertButton()
    button.set_allowed(True)
    button.set_open(True)
    assert button.isHidden() and not button.isEnabled() and not button.timer.isActive()
    button.close()


def test_tools_switch_is_wired_before_refresh_permissions():
    ui = (Path(attention_albert.__file__).parent / "taskbar_ui.py").read_text(encoding="utf-8")
    assert ui.index('self.aai_tools_action = self.tools_menu.addAction("Attention Albert")') \
        < ui.index('"Refresh Permissions"')
    assert "self.aai_btn.bind_tools_action(self.aai_tools_action)" in ui
