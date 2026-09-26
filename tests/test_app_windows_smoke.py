"""Offscreen construction smoke tests for SuiteView top-level windows."""

from __future__ import annotations

import logging
import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtWidgets import QApplication, QSystemTrayIcon, QTabWidget


@pytest.fixture
def app(monkeypatch, tmp_path):
    monkeypatch.setenv("SUITEVIEW_PROFILE_DIR", str(tmp_path / "profile"))
    return QApplication.instance() or QApplication([])


@pytest.fixture(autouse=True)
def no_live_access(monkeypatch, app):
    from suiteview.core import access_control
    from suiteview.core.access_control import APP_CODES, EffectiveAccess

    rights = EffectiveAccess(
        "SMOKE",
        "ADMIN",
        True,
        True,
        True,
        apps=frozenset((*APP_CODES, "ADMINISTRATOR")),
        developer=True,
    )
    monkeypatch.setattr(access_control, "guard_app_access", lambda _code: None)
    monkeypatch.setattr(access_control, "get_access", lambda refresh=False: rights)
    monkeypatch.setattr(access_control, "can_access_app", lambda _code: True)
    monkeypatch.setattr(QSystemTrayIcon, "show", lambda self: None)
    return rights


def _exercise_window(window, app):
    window.show()
    app.processEvents()
    for tabs in window.findChildren(QTabWidget):
        if tabs.count() > 1:
            tabs.setCurrentIndex(1)
            tabs.setCurrentIndex(0)
    window.hide()
    app.processEvents()
    window.show()
    app.processEvents()


def _cleanup(window, app):
    try:
        window.close()
    except RuntimeError:
        return
    window.deleteLater()
    app.processEvents()


def _taskbar(monkeypatch, rights, tmp_path):
    from suiteview.taskbar_launcher import taskbar_window
    from suiteview.taskbar_launcher.taskbar_window import SuiteViewTaskbar

    monkeypatch.setattr(taskbar_window, "get_access", lambda refresh=True: rights)
    monkeypatch.setattr(taskbar_window, "activation_message", lambda: 0)
    monkeypatch.setattr(SuiteViewTaskbar, "_register_appbar", lambda *a, **k: None)
    monkeypatch.setattr(SuiteViewTaskbar, "_unregister_appbar", lambda *a, **k: None)
    return SuiteViewTaskbar()


def _filenav(monkeypatch, rights, tmp_path):
    from suiteview.taskbar_launcher.file_nav_window import FileNavWindow

    return FileNavWindow(parent_bar=None)


def _audit(monkeypatch, rights, tmp_path):
    from suiteview.audit.audit_window import AuditWindow

    return AuditWindow()


def _query_object_viewer(monkeypatch, rights, tmp_path):
    from suiteview.audit.query_object_viewer_window import QueryObjectViewerWindow

    return QueryObjectViewerWindow()


def _polview(monkeypatch, rights, tmp_path):
    from suiteview.polview.ui.main_window import GetPolicyWindow

    return GetPolicyWindow()


def _illustration(monkeypatch, rights, tmp_path):
    from suiteview.illustration.ui.main_window import IllustrationWindow

    return IllustrationWindow()


def _abr(monkeypatch, rights, tmp_path):
    from suiteview.abrquote.ui.abr_window import ABRQuoteWindow

    return ABRQuoteWindow()


def _rate_manager(monkeypatch, rights, tmp_path):
    from suiteview.ratemanager.ratemanager_window import RateManagerWindow

    return RateManagerWindow()


def _mainframe(monkeypatch, rights, tmp_path):
    from suiteview.mainframe_nav.mainframe_window import MainframeWindow

    return MainframeWindow()


def _screenshots(monkeypatch, rights, tmp_path):
    from suiteview.screenshot_manager.screenshot_manager_window import ScreenShotManagerWindow

    return ScreenShotManagerWindow()


def _email_attachments(monkeypatch, rights, tmp_path):
    import suiteview.ui.email_attachments_window as module

    class FakeEmailRepository:
        def get_setting(self, _name, default=None):
            return default

        def get_attachments_since(self, _start):
            return []

    monkeypatch.setattr(module, "get_email_repository", lambda: FakeEmailRepository())
    return module.EmailAttachmentsWindow()


def _administrator(monkeypatch, rights, tmp_path):
    from suiteview.administrator.service import AccessRole, AccessSnapshot, AccessUser
    from suiteview.administrator.window import AdministratorWindow

    class FakeRepository:
        def load(self):
            return AccessSnapshot(
                users=(AccessUser("SMOKE", "Smoke User", True, "ADMIN"),),
                roles=(
                    AccessRole(
                        "ADMIN",
                        "Administrators",
                        True,
                        True,
                        True,
                        frozenset(),
                    ),
                ),
                actor_id="SMOKE",
            )

    return AdministratorWindow(repository=FakeRepository())


def _agent_chat(monkeypatch, rights, tmp_path):
    pytest.importorskip("copilot")
    from suiteview.agent_chat.store import ConversationStore
    from suiteview.agent_chat.window import AgentChatWindow

    monkeypatch.setattr(AgentChatWindow, "_load_models", lambda self: None)
    return AgentChatWindow(store=ConversationStore(tmp_path / "agent-chat"))


def _scratchpad(monkeypatch, rights, tmp_path):
    from suiteview.scratchpad.scratchpad_panel import ScratchPadWindow

    return ScratchPadWindow.open()


WINDOW_FACTORIES = (
    ("SuiteViewTaskbar", _taskbar),
    ("FileNavWindow", _filenav),
    ("AuditWindow", _audit),
    ("QueryObjectViewerWindow", _query_object_viewer),
    ("PolView", _polview),
    ("IllustrationWindow", _illustration),
    ("ABRQuoteWindow", _abr),
    ("RateManagerWindow", _rate_manager),
    ("MainframeWindow", _mainframe),
    ("ScreenShotManagerWindow", _screenshots),
    ("EmailAttachmentsWindow", _email_attachments),
    ("AdministratorWindow", _administrator),
    ("AgentChatWindow", _agent_chat),
    ("ScratchPadWindow", _scratchpad),
)


@pytest.mark.parametrize("name,factory", WINDOW_FACTORIES, ids=[name for name, _ in WINDOW_FACTORIES])
def test_top_level_window_constructs_offscreen_without_logged_errors(
    name, factory, app, monkeypatch, no_live_access, tmp_path, caplog
):
    caplog.set_level(logging.ERROR)
    caplog.clear()
    window = factory(monkeypatch, no_live_access, tmp_path)
    try:
        _exercise_window(window, app)
        errors = [record for record in caplog.records if record.levelno >= logging.ERROR]
        assert errors == []
    finally:
        _cleanup(window, app)
