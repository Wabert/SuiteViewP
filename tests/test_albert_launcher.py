"""The task-bar shortcut uses the existing no-email composer, not a second agent."""
import ast
from pathlib import Path
import sys

import pytest

from suiteview.taskbar_launcher import albert_launcher
from suiteview.core import access_control, build_env


@pytest.fixture
def app(monkeypatch):
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    from PyQt6.QtWidgets import QApplication
    application = QApplication.instance() or QApplication([])
    yield application
    application.processEvents()


def test_launch_uses_shared_bridge_without_capture_or_shell(monkeypatch):
    calls = []
    monkeypatch.setattr(albert_launcher.subprocess, "Popen",
                        lambda *args, **kwargs: calls.append((args, kwargs)) or "process")
    assert albert_launcher.launch_albert() == "process"
    args, kwargs = calls[0]
    assert args[0] == [sys.executable, "-B", str(albert_launcher.BRIDGE), "--new-task"]
    assert kwargs["cwd"] == str(albert_launcher.BRIDGE.parent)
    assert not kwargs.get("shell")
    assert albert_launcher.BRIDGE.is_file()


def test_missing_bridge_fails_explicitly(tmp_path, monkeypatch):
    monkeypatch.setattr(albert_launcher, "BRIDGE", tmp_path / "missing.py")
    with pytest.raises(FileNotFoundError, match="not found"):
        albert_launcher.launch_albert()


def test_packaged_launch_is_blocked_before_permissions_or_subprocess(monkeypatch):
    monkeypatch.setattr(build_env.sys, "frozen", True, raising=False)
    def unexpected(*args, **kwargs):
        pytest.fail("Unavailable Albert must not access the database or start a process")
    monkeypatch.setattr(access_control, "get_access", unexpected)
    monkeypatch.setattr(albert_launcher.subprocess, "Popen", unexpected)
    with pytest.raises(access_control.AccessDeniedError, match="not available in the packaged EXE"):
        albert_launcher.launch_albert()


@pytest.mark.parametrize("role,all_apps,apps", [
    ("ADMIN", True, frozenset()),
    ("BUSINESS", True, frozenset()),
    ("BUSINESS", False, frozenset({"ALBERT", "POLVIEW"})),
])
def test_packaged_badge_stays_hidden_after_refresh(app, monkeypatch, role, all_apps, apps):
    from types import SimpleNamespace
    from suiteview.taskbar_launcher.taskbar_window import SuiteViewTaskbar

    monkeypatch.setattr(build_env.sys, "frozen", True, raising=False)
    button = albert_launcher.AlbertButton()
    bar = SimpleNamespace(albert_btn=button, _permission_actions=[])
    rights = access_control.EffectiveAccess("PERSON", role, all_apps, True, True, apps)
    SuiteViewTaskbar._apply_permissions(bar, rights)
    assert not button.isEnabled()
    assert button.isHidden()
    assert "not available in the packaged EXE" in button.toolTip()
    assert not rights.allows_app("ALBERT")
    assert rights.allows_app("POLVIEW")
    button.close()


def test_badge_appearance_and_click(app, monkeypatch):
    calls = []
    monkeypatch.setattr(albert_launcher, "launch_albert", lambda: calls.append("opened"))
    button = albert_launcher.AlbertButton()
    assert button.text() == "Al"
    assert button.width() == button.height() == 28
    assert "Albert" in button.accessibleName()
    for color in ("#247C75", "#103F3C", "#D4A017", "#FFD700"):
        assert color in button.styleSheet()
    assert "border: 2px solid #D4A017" in button.styleSheet()
    assert "border-radius: 4px" in button.styleSheet()
    assert "border-top-color" not in button.styleSheet()
    button.click()
    assert calls == ["opened"]
    button.close()


def test_launch_error_is_visible_and_logged(app, monkeypatch, caplog):
    def fail():
        raise OSError("Synthetic launch failure")

    errors = []
    monkeypatch.setattr(albert_launcher, "launch_albert", fail)
    monkeypatch.setattr(albert_launcher.QMessageBox, "critical",
                        lambda *args: errors.append(args))
    button = albert_launcher.AlbertButton()
    button.click()
    assert "Synthetic launch failure" in errors[0][2]
    assert "Failed to open Albert" in caplog.text
    button.close()


def test_shortcut_is_wired_in_header_and_preserved_in_floating_mode():
    launcher_dir = Path(albert_launcher.__file__).parent
    sources = {
        path.stem: ast.parse(path.read_text(encoding="utf-8"))
        for path in (
            launcher_dir / "taskbar_ui.py",
            launcher_dir / "taskbar_system.py",
            launcher_dir / "taskbar_modes.py",
        )
    }

    methods = {}
    for tree in sources.values():
        for node in tree.body:
            if isinstance(node, ast.ClassDef):
                methods.update({
                    child.name: ast.unparse(child)
                    for child in node.body
                    if isinstance(child, ast.FunctionDef)
                })

    assert "DEV_MODE" not in methods["_build_primary_app_buttons"]
    assert "LIGHT_MODE" not in methods["_build_primary_app_buttons"]
    assert "('ALBERT', 'albert_btn')" in methods["_apply_permissions"]
    assert "control.setEnabled(allowed)" in methods["_apply_permissions"]
    assert "control.setVisible(" in methods["_apply_permissions"]
    assert "self.albert_btn = AlbertButton(self)" in methods["_build_primary_app_buttons"]
    assert "header_layout.addWidget(self.albert_btn)" in methods["_build_primary_app_buttons"]
    assert "self._apply_permissions(self._launcher_access)" in methods["_enter_floating_mode"]
    assert "bar_w = self.layout().sizeHint().width()" in methods["_enter_floating_mode"]
