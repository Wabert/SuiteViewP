"""The task-bar shortcut uses the existing no-email composer, not a second agent."""
import ast
from pathlib import Path
import sys

import pytest

from suiteview.taskbar_launcher import albert_launcher


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
    source = Path(albert_launcher.__file__).with_name("suiteview_taskbar.py").read_text(encoding="utf-8")
    tree = ast.parse(source)
    bar = next(node for node in tree.body if isinstance(node, ast.ClassDef)
               and node.name == "SuiteViewTaskbar")
    methods = {node.name: ast.unparse(node) for node in bar.body if isinstance(node, ast.FunctionDef)}
    assert "DEV_MODE" not in methods["init_ui"]
    assert "LIGHT_MODE" not in methods["init_ui"]
    assert "('ALBERT', 'albert_btn')" in methods["_apply_permissions"]
    assert "control.setEnabled(access is not None and access.allows_app(code))" in methods["_apply_permissions"]
    assert "self.albert_btn = AlbertButton(self)" in methods["init_ui"]
    assert "header_layout.addWidget(self.albert_btn)" in methods["init_ui"]
    assert "self.albert_btn.show()" in methods["_enter_floating_mode"]
    assert "36 if hasattr(self, 'albert_btn') else 0" in methods["_enter_floating_mode"]
