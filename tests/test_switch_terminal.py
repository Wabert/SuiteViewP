"""Switch A/B terminals, the shared Passwords store and PolView's Switch A button."""

from __future__ import annotations

import json
import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtWidgets import QApplication, QMessageBox

from suiteview.core import access_control
from suiteview.core.profile_paths import profile_path
from suiteview.data import mainframe_credentials as creds
from suiteview.mainframe_nav import mainframe_terminal_screen as terminal_module
from suiteview.mainframe_nav import switch_sessions
from suiteview.mainframe_nav.switch_sessions import TerminalEndpoint

_REAL_GUARD_APP_ACCESS = access_control.guard_app_access
_QT_APP = None


@pytest.fixture
def app(monkeypatch):
    global _QT_APP
    monkeypatch.setattr(access_control, "guard_app_access", lambda _code: None)
    _QT_APP = QApplication.instance() or QApplication([])
    return _QT_APP


def _write_settings(data: dict):
    path = profile_path("terminal_settings.json")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data), encoding="utf-8")


def _read_settings() -> dict:
    return json.loads(profile_path("terminal_settings.json").read_text(encoding="utf-8"))


# ── Shared sign-on store ──────────────────────────────────────────────


def test_credentials_round_trip_and_update_in_place():
    assert creds.load_mainframe_credentials() == creds.MainframeCredentials()
    creds.save_mainframe_credentials(" AB7Y02 ", "first-secret")
    creds.save_mainframe_credentials("AB7Y02", "second-secret")

    saved = creds.load_mainframe_credentials()
    assert saved.userid == "AB7Y02"
    assert saved.password == "second-secret"
    assert saved.complete
    assert "second-secret" not in repr(saved)
    from suiteview.data.repositories import get_connection_repository
    rows = [row for row in get_connection_repository().get_all_connections()
            if row["connection_name"] == creds.MAINFRAME_USER_CONNECTION]
    assert len(rows) == 1
    assert b"second-secret" not in rows[0]["encrypted_password"]


@pytest.mark.parametrize("userid,password", [("", "secret"), ("AB7Y02", ""), ("  ", "x")])
def test_credentials_require_both_values(userid, password):
    with pytest.raises(ValueError):
        creds.save_mainframe_credentials(userid, password)


# ── Switch endpoints ──────────────────────────────────────────────────


def test_endpoints_default_then_fall_back_to_pre_switch_settings():
    assert switch_sessions.load_endpoint("A") == TerminalEndpoint()
    _write_settings({"host": "PRODESA", "port": 992, "ssl": True, "term_type": "IBM-3278-4-E"})
    legacy = TerminalEndpoint("PRODESA", 992, True, "IBM-3278-4-E")
    assert switch_sessions.load_endpoint("A") == legacy
    assert switch_sessions.load_endpoint("b") == legacy


def test_save_endpoint_keeps_the_other_side_and_drops_flat_keys():
    _write_settings({"host": "PRODESA", "port": 992, "ssl": True, "term_type": "IBM-3278-4-E"})
    switch_sessions.save_endpoint("A", TerminalEndpoint("PRODESA", 2023, False, "IBM-3278-2-E"))

    data = _read_settings()
    assert set(data) == {"switch_a", "switch_b"}
    assert switch_sessions.load_endpoint("A").port == 2023
    assert switch_sessions.load_endpoint("B") == TerminalEndpoint("PRODESA", 992, True, "IBM-3278-4-E")


def test_unknown_side_is_rejected():
    with pytest.raises(ValueError):
        switch_sessions.load_endpoint("C")


def test_plaintext_sign_on_moves_into_the_store_and_leaves_the_file():
    _write_settings({"host": "PRODESA", "port": 992, "ssl": True,
                     "term_type": "IBM-3278-4-E", "userid": "AB7Y02", "password": "clear-text"})
    switch_sessions.retire_plaintext_credentials()

    assert creds.load_mainframe_credentials() == creds.MainframeCredentials("AB7Y02", "clear-text")
    text = profile_path("terminal_settings.json").read_text(encoding="utf-8")
    assert "clear-text" not in text and "userid" not in text
    assert switch_sessions.load_endpoint("A").term_type == "IBM-3278-4-E"


def test_plaintext_sign_on_never_overwrites_a_saved_one():
    creds.save_mainframe_credentials("AB7Y02", "current")
    _write_settings({"userid": "OLDID", "password": "stale"})
    switch_sessions.retire_plaintext_credentials()
    assert creds.load_mainframe_credentials().password == "current"
    assert "stale" not in profile_path("terminal_settings.json").read_text(encoding="utf-8")


def test_plaintext_sign_on_is_kept_when_the_store_is_unreadable(monkeypatch):
    _write_settings({"userid": "AB7Y02", "password": "only-copy"})

    def _broken():
        raise RuntimeError("bad key")

    monkeypatch.setattr(switch_sessions, "load_mainframe_credentials", _broken)
    switch_sessions.retire_plaintext_credentials()
    assert _read_settings()["password"] == "only-copy"


# ── Passwords dialog ─────────────────────────────────────────────────


def test_passwords_dialog_loads_and_saves(app):
    from suiteview.ui.dialogs.passwords_dialog import PasswordsDialog

    creds.save_mainframe_credentials("AB7Y02", "old")
    dialog = PasswordsDialog()
    try:
        assert dialog.userid_input.text() == "AB7Y02"
        assert dialog.password_input.text() == "old"
        dialog.password_input.setText("new")
        assert dialog.save() is True
    finally:
        dialog.close()
    assert creds.load_mainframe_credentials().password == "new"


def test_passwords_dialog_refuses_blank_values(app):
    from suiteview.ui.dialogs.passwords_dialog import PasswordsDialog

    dialog = PasswordsDialog(reason="Needed for Switch A")
    try:
        dialog.userid_input.setText("AB7Y02")
        assert dialog.save() is False
        assert "both" in dialog.status_label.text()
    finally:
        dialog.close()
    assert not creds.load_mainframe_credentials().complete


# ── Terminal panes ────────────────────────────────────────────────────


def test_dual_terminal_is_switch_a_left_and_switch_b_right(app):
    switch_sessions.save_endpoint("B", TerminalEndpoint("PRODESA", 2024, True, "IBM-3278-2-E"))
    dual = terminal_module.DualTerminalScreen()
    try:
        assert dual.terminal_for("A") is dual.terminal_left
        assert dual.terminal_for("b") is dual.terminal_right
        assert dual.terminal_left.side == "A"
        assert dual.terminal_right.conn_port == 2024
        assert dual.terminal_left.conn_status_label.text().startswith("⚫ Switch A · ")
        assert "Switch B" in dual.terminal_right.conn_status_label.text()
    finally:
        dual.close()


def test_open_policy_fills_the_pane_and_runs_the_region_sequence(app, monkeypatch):
    screen = terminal_module.MainframeTerminalScreen("A")
    started = []
    monkeypatch.setattr(screen, "start_cics_sequence",
                        lambda region, option: started.append((region, option)))
    try:
        assert screen.open_policy(" u1234567 ", "03", "ckpr") is True
        assert screen.policy_input.text() == "U1234567"
        assert screen.company_combo.currentText() == "03"
        assert started == [("CKPR", terminal_module.CICS_REGION_OPTIONS["CKPR"])]
    finally:
        screen.close()


def test_open_policy_rejects_a_region_without_navigation(app, monkeypatch):
    screen = terminal_module.MainframeTerminalScreen("A")
    warnings = []
    monkeypatch.setattr(QMessageBox, "warning", lambda *a: warnings.append(a[2]))
    monkeypatch.setattr(screen, "start_cics_sequence",
                        lambda *a: pytest.fail("must not sign on"))
    try:
        assert screen.open_policy("U1234567", "01", "CKCS") is False
        assert "CKCS" in warnings[0]
    finally:
        screen.close()


def test_missing_sign_on_opens_passwords_then_continues(app, monkeypatch):
    screen = terminal_module.MainframeTerminalScreen("A")
    reasons = []

    def _fake_dialog(parent, reason=""):
        reasons.append(reason)
        creds.save_mainframe_credentials("AB7Y02", "secret")
        return True

    monkeypatch.setattr(terminal_module, "open_passwords_dialog", _fake_dialog)
    try:
        assert screen._ensure_cics_credentials("CKPR") is True
        assert screen.conn_userid == "AB7Y02"
        assert "CKPR" in reasons[0]
    finally:
        screen.close()


def test_cancelled_passwords_dialog_stops_the_sequence(app, monkeypatch):
    screen = terminal_module.MainframeTerminalScreen("A")
    monkeypatch.setattr(terminal_module, "open_passwords_dialog", lambda *a, **k: False)
    try:
        assert screen._ensure_cics_credentials("CKPR") is False
    finally:
        screen.close()


# ── Mainframe window + PolView button ─────────────────────────────────


def test_mainframe_window_routes_policy_to_the_requested_side(app, monkeypatch):
    from suiteview.mainframe_nav.mainframe_window import MainframeWindow

    opened = []
    monkeypatch.setattr(
        terminal_module.MainframeTerminalScreen, "open_policy",
        lambda self, policy, company, region: opened.append((self.side, policy, company, region)))
    window = MainframeWindow()
    try:
        window.tab_widget.setCurrentIndex(1)
        window.open_policy_in_switch("A", "U1234567", "01", "CKPR")
        assert window.tab_widget.currentWidget() is window.mainframe_terminal_screen
        app.processEvents()
        assert opened == [("A", "U1234567", "01", "CKPR")]
    finally:
        window.close()


def test_polview_switch_a_button_launches_current_policy(app):
    from suiteview.polview.ui.main_window import GetPolicyWindow

    win = GetPolicyWindow(enable_policy_list=False)
    launched = []
    win.set_switch_launcher(lambda *args: launched.append(args))
    try:
        assert win.open_switch_btn.isEnabled() is False
        assert win.open_switch_btn.text() == "🖥 Switch A"
        win._current_policy = None
        win._open_in_switch_a()
        assert launched == []
        win._current_policy = "U1234567"
        win._current_region = "CKMO"
        win._policy_info = {"CompanyCode": "04"}
        win._open_in_switch_a()
        assert launched == [("A", "U1234567", "CKMO", "04")]
    finally:
        win.close()


def test_taskbar_switch_launcher_reuses_the_mainframe_window(app):
    from types import SimpleNamespace

    from suiteview.taskbar_launcher.collaborators import TaskbarState
    from suiteview.taskbar_launcher.taskbar_system import AppLauncher

    state = TaskbarState()
    bar = AppLauncher(SimpleNamespace(), state, chrome=SimpleNamespace(),
                      callbacks=SimpleNamespace(_bring_to_front=lambda w: None))
    routed = []
    window = SimpleNamespace(open_policy_in_switch=lambda *args: routed.append(args))
    bar._open_mainframe = lambda: setattr(state, "mainframe_window", window)
    bar._launch_switch_with_policy("A", "U1234567", "CKPR", "01")
    assert routed == [("A", "U1234567", "01", "CKPR")]


# ── Role gating: ADMIN + MAINFRAMENAV shows Switch A, PASSWORDMANAGER shows Passwords ──


def _rights(role="SUPPORT", all_apps=False, apps=()):
    return access_control.EffectiveAccess(
        "TEST", role, all_apps, True, True, frozenset(apps))


def test_admin_all_apps_grants_password_manager_and_mainframe():
    admin = _rights("ADMIN", all_apps=True)
    support = _rights(apps=set(access_control.APP_CODES) - {"PASSWORDMANAGER"})
    assert "PASSWORDMANAGER" in access_control.APP_CODES
    assert admin.allows_app("PASSWORDMANAGER") and admin.allows_app("MAINFRAMENAV")
    assert not support.allows_app("PASSWORDMANAGER")


@pytest.mark.parametrize("role,all_apps,apps,visible", [
    ("SUPPORT", False, {"POLVIEW", "MAINFRAMENAV"}, False),
    ("SUPPORT", True, set(), False),
    ("ADMIN", False, {"POLVIEW"}, False),
    ("ADMIN", False, {"POLVIEW", "MAINFRAMENAV"}, True),
    ("ADMIN", True, set(), True),
])
def test_polview_switch_a_button_requires_admin_with_mainframenav(
        qapp_rights, role, all_apps, apps, visible):
    from suiteview.polview.ui.main_window import GetPolicyWindow

    rights = _rights(role, all_apps=all_apps, apps=apps)
    assert rights.shows_switch_a_button is visible
    qapp_rights(rights)
    win = GetPolicyWindow(enable_policy_list=False)
    try:
        assert win.open_switch_btn.isHidden() is (not visible)
    finally:
        win.close()


def test_switch_a_button_shown_for_source_runs():
    assert access_control._DEVELOPER_ACCESS.shows_switch_a_button


def test_polview_switch_a_click_rechecks_admin_role(qapp_rights, monkeypatch):
    from suiteview.polview.ui.main_window import GetPolicyWindow

    qapp_rights(_rights("ADMIN", apps={"POLVIEW", "MAINFRAMENAV"}))
    win = GetPolicyWindow(enable_policy_list=False)
    launched, warnings = [], []
    win.set_switch_launcher(lambda *args: launched.append(args))
    monkeypatch.setattr(QMessageBox, "warning", lambda *a: warnings.append(a[2]))
    try:
        win._current_policy = "U1234567"
        qapp_rights(_rights("SUPPORT", apps={"POLVIEW", "MAINFRAMENAV"}))
        win._open_in_switch_a()
        assert launched == []
        assert "ADMIN" in warnings[0] and "MAINFRAMENAV" in warnings[0]
    finally:
        win.close()


@pytest.mark.parametrize("apps,visible", [({"MAINFRAMENAV"}, False),
                                          ({"MAINFRAMENAV", "PASSWORDMANAGER"}, True)])
def test_mainframe_passwords_button_follows_password_manager_grant(qapp_rights, apps, visible):
    from suiteview.mainframe_nav.mainframe_window import MainframeWindow

    qapp_rights(_rights(apps=apps))
    window = MainframeWindow()
    try:
        assert window.passwords_button.isHidden() is (not visible)
    finally:
        window.close()


def test_passwords_dialog_denied_without_password_manager(qapp_rights, monkeypatch):
    from suiteview.ui.dialogs import passwords_dialog

    qapp_rights(_rights(apps={"MAINFRAMENAV"}))
    warnings = []
    monkeypatch.setattr(QMessageBox, "warning", lambda *a: warnings.append(a[2]))
    monkeypatch.setattr(passwords_dialog, "PasswordsDialog",
                        lambda *a, **k: pytest.fail("must not open"))
    assert passwords_dialog.open_passwords_dialog(None, reason="CKPR needs it") is False
    assert "PASSWORDMANAGER" in warnings[0] and "CKPR needs it" in warnings[0]


def test_taskbar_passwords_action_is_permission_gated():
    from pathlib import Path

    import suiteview.taskbar_launcher.taskbar_ui as taskbar_ui

    text = Path(taskbar_ui.__file__).read_text(encoding="utf-8")
    assert '"PASSWORDMANAGER", self.tools_menu.addAction("🔑 Passwords"' in text


@pytest.fixture
def qapp_rights(monkeypatch, app):
    monkeypatch.setattr(access_control, "guard_app_access", _REAL_GUARD_APP_ACCESS)

    def _apply(rights):
        monkeypatch.setattr(access_control, "get_access", lambda refresh=False: rights)

    return _apply
