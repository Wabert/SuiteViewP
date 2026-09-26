"""Source bypass and fail-closed live permissions for the single packaged edition."""

from dataclasses import replace
from unittest.mock import MagicMock, Mock

import pyodbc
import pytest

from suiteview.core import access_control as access
from suiteview.core import build_env


@pytest.fixture(autouse=True)
def packaged(monkeypatch):
    monkeypatch.setattr(build_env.sys, "frozen", True, raising=False)
    access.clear_access_cache()
    yield
    access.clear_access_cache()


@pytest.fixture
def database(monkeypatch):
    connection = MagicMock()
    cursor = connection.cursor.return_value
    cursor.execute.return_value = cursor
    cursor.fetchone.return_value = ("UL_RATES",)
    cursor.fetchall.return_value = [
        (True, "BUSINESS", False, False, True, "POLVIEW"),
        (True, "BUSINESS", False, False, True, "ABR"),
    ]
    connect = Mock(return_value=connection)
    monkeypatch.setattr(access, "connect_access_database", connect)
    monkeypatch.setattr(access, "current_network_id", lambda: "PERSON01")
    return connection, cursor, connect


def test_source_is_unrestricted_without_identity_or_database(monkeypatch):
    monkeypatch.delattr(build_env.sys, "frozen", raising=False)
    connect = Mock(side_effect=AssertionError("Source must not query permissions"))
    identity = Mock(side_effect=AssertionError("Source must not depend on identity"))
    monkeypatch.setattr(access, "connect_access_database", connect)
    monkeypatch.setattr(access, "current_network_id", identity)
    rights = access.get_access(refresh=True)
    assert rights.developer and build_env.has_developer_access()
    for code in (*access.APP_CODES, "ADMINISTRATOR", "FUTURE_APP"):
        access.guard_app_access(code)
    build_env.guard_data_writable()
    access.guard_support_files_writable()
    assert not build_env.is_data_read_only()
    assert access.can_write_support_files()
    connect.assert_not_called()
    identity.assert_not_called()


def test_packaged_developer_username_or_environment_is_not_a_bypass(database, monkeypatch):
    monkeypatch.setenv("USERNAME", "AB7Y02")
    monkeypatch.setenv("SUITEVIEW_DEV_MODE", "1")
    assert not build_env.has_developer_access()
    with pytest.raises(access.AccessDeniedError, match="RATEMANAGER"):
        access.guard_app_access("RATEMANAGER")


def test_live_roles_are_parameterized_and_closed(database):
    connection, cursor, _ = database
    rights = access.get_access()
    assert rights.actor_id == "PERSON01"
    assert rights.apps == frozenset({"POLVIEW", "ABR"})
    assert rights.can_write_support_files
    assert not rights.can_update_database
    assert cursor.execute.call_args.args[1:] == ("PERSON01",)
    assert "PERSON01" not in cursor.execute.call_args.args[0]
    connection.commit.assert_not_called()
    connection.rollback.assert_called_once()
    connection.close.assert_called_once()
    cursor.close.assert_called_once()


@pytest.mark.parametrize("rows", [[], [(False, "ADMIN", True, True, True, None)]])
def test_missing_or_disabled_user_is_denied(database, rows):
    _, cursor, _ = database
    cursor.fetchall.return_value = rows
    with pytest.raises(access.AccessDeniedError, match="not enabled"):
        access.get_access()


def test_all_apps_is_not_admin_and_does_not_grant_write_bits(database):
    _, cursor, _ = database
    cursor.fetchall.return_value = [(True, "READER", True, False, False, None)]
    rights = access.get_access()
    assert rights.allows_app("FUTURE_APP")
    assert not rights.allows_app("ADMINISTRATOR")
    with pytest.raises(build_env.ReadOnlyDataError, match="CanUpdateDatabase"):
        build_env.guard_data_writable()
    with pytest.raises(access.AccessDeniedError, match="CanWriteSupportFiles"):
        access.guard_support_files_writable()


def test_admin_entry_is_role_specific(database):
    _, cursor, _ = database
    cursor.fetchall.return_value = [(True, "ADMIN", True, True, True, None)]
    access.guard_app_access("ADMINISTRATOR")
    build_env.guard_data_writable()
    access.guard_support_files_writable()


def test_administrator_whitelist_cannot_grant_administration(database):
    _, cursor, _ = database
    cursor.fetchall.return_value = [(True, "SUPPORT", True, True, True, "ADMINISTRATOR")]
    with pytest.raises(access.AccessDeniedError, match="ADMINISTRATOR"):
        access.guard_app_access("ADMINISTRATOR")


def test_ui_snapshot_is_cached_but_action_rechecks_revocation(database):
    _, cursor, connect = database
    assert access.can_access_app("POLVIEW")
    assert access.can_access_app("ABR")
    assert connect.call_count == 1
    cursor.fetchall.return_value = []
    with pytest.raises(access.AccessDeniedError):
        access.guard_app_access("POLVIEW")
    assert connect.call_count == 2
    with pytest.raises(access.AccessDeniedError):
        access.can_access_app("POLVIEW")
    assert connect.call_count == 3


def test_write_permissions_recheck_changes(database):
    _, cursor, _ = database
    assert access.can_write_support_files()
    cursor.fetchall.return_value = [(True, "BUSINESS", False, False, False, "POLVIEW")]
    with pytest.raises(access.AccessDeniedError):
        access.guard_support_files_writable("copy a policy document")
    cursor.fetchall.return_value = [(True, "SUPPORT", False, True, True, "POLVIEW")]
    build_env.guard_data_writable("update rates")


def test_database_failure_clears_prior_allowed_snapshot(database):
    _, _, connect = database
    assert access.can_access_app("POLVIEW")
    connect.side_effect = pyodbc.Error("offline")
    with pytest.raises(access.AccessUnavailableError, match="network/VPN"):
        access.guard_app_access("POLVIEW")
    with pytest.raises(access.AccessUnavailableError):
        access.can_access_app("POLVIEW")


def test_wrong_database_fails_closed(database):
    _, cursor, _ = database
    cursor.fetchone.return_value = ("WRONG_DATABASE",)
    with pytest.raises(access.AccessUnavailableError, match="Expected UL_Rates"):
        access.get_access()


@pytest.mark.parametrize("operation", [
    "_open_polview", "_get_polview_window", "_open_abrquote", "_open_illustration",
    "_open_audit", "_open_mainframe", "_open_rate_manager", "_open_file_nav",
    "_open_agent_chat", "_open_email_attachments", "_open_screenshot",
    "_take_quick_screenshot", "_toggle_scratchpad_window", "_toggle_file_open_history",
    "_exit_compact_mode", "_open_db2_table_check",
])
def test_taskbar_direct_actions_deny_before_using_existing_window(monkeypatch, operation):
    from PyQt6.QtWidgets import QMessageBox
    from suiteview.taskbar_launcher.taskbar_window import SuiteViewTaskbar

    warning = Mock()
    monkeypatch.setattr(QMessageBox, "warning", warning)
    monkeypatch.setattr(access, "guard_app_access",
                        Mock(side_effect=access.AccessDeniedError("Access revoked")))
    # A bare object has no windows to reuse: the check must happen first.
    assert getattr(SuiteViewTaskbar, operation)(object()) is None
    warning.assert_called_once()
    assert "Access revoked" in warning.call_args.args[2]


def test_launcher_controls_follow_app_grants():
    from types import SimpleNamespace
    from suiteview.taskbar_launcher.taskbar_window import SuiteViewTaskbar

    bar = SimpleNamespace(polview_btn=Mock(), filenav_btn=Mock(), albert_btn=Mock(),
                          tab_widget=Mock(), _permission_actions=[("RATEMANAGER", Mock())])
    rights = access.EffectiveAccess("PERSON01", "BUSINESS", False, False, True,
                                   frozenset({"POLVIEW"}))
    SuiteViewTaskbar._apply_permissions(bar, rights)
    bar.polview_btn.setEnabled.assert_called_with(True)
    bar.polview_btn.setVisible.assert_called_with(True)
    bar.filenav_btn.setEnabled.assert_called_with(False)
    bar.filenav_btn.setVisible.assert_called_with(False)
    bar.albert_btn.setEnabled.assert_called_with(False)
    bar.albert_btn.setVisible.assert_called_with(False)
    bar.tab_widget.setEnabled.assert_called_with(False)
    bar._permission_actions[0][1].setEnabled.assert_called_with(False)
    bar._permission_actions[0][1].setVisible.assert_called_with(False)
    SuiteViewTaskbar._apply_permissions(bar, replace(rights, all_apps=True))
    bar.albert_btn.setEnabled.assert_called_with(False)
    bar.albert_btn.setVisible.assert_called_with(False)
    bar.filenav_btn.setVisible.assert_called_with(True)
    bar._permission_actions[0][1].setVisible.assert_called_with(True)
    SuiteViewTaskbar._apply_permissions(bar, None)
    bar.polview_btn.setEnabled.assert_called_with(False)
    bar.polview_btn.setVisible.assert_called_with(False)
    bar._permission_actions[0][1].setVisible.assert_called_with(False)


def test_startup_denial_precedes_launcher_construction(monkeypatch):
    from suiteview.taskbar_launcher import taskbar_window

    monkeypatch.setattr(taskbar_window, "get_access",
                        Mock(side_effect=access.AccessDeniedError("Disabled user")))
    with pytest.raises(access.AccessDeniedError, match="Disabled user"):
        taskbar_window.SuiteViewTaskbar.__init__(object())


def test_filenav_constructor_cannot_bypass_app_grant(monkeypatch):
    from suiteview.taskbar_launcher import file_nav_window

    monkeypatch.setattr(file_nav_window, "guard_app_access",
                        Mock(side_effect=access.AccessDeniedError("FILENAV denied")))
    with pytest.raises(access.AccessDeniedError, match="FILENAV denied"):
        file_nav_window.FileNavWindow.__init__(object())


def test_ui_decorator_preserves_qt_zero_argument_slots(monkeypatch):
    from PyQt6.QtWidgets import QApplication, QPushButton

    app = QApplication.instance() or QApplication([])
    monkeypatch.setattr(build_env.sys, "frozen", False)
    calls = []

    class Actions:
        @access.requires_app_access("POLVIEW")
        def open(self):
            calls.append("opened")

        @access.requires_app_access("POLVIEW")
        def toggle(self, checked):
            calls.append(checked)

    actions = Actions()
    button = QPushButton()
    button.clicked.connect(actions.open)
    button.clicked.connect(actions.toggle)
    button.click()
    assert calls == ["opened", False]
    button.deleteLater()
    app.processEvents()


def test_ui_decorator_reports_permission_change_inside_target(monkeypatch):
    from PyQt6.QtWidgets import QMessageBox

    monkeypatch.setattr(build_env.sys, "frozen", False)
    warning = Mock()
    monkeypatch.setattr(QMessageBox, "warning", warning)

    class Actions:
        @access.requires_app_access("POLVIEW")
        def open(self):
            raise access.AccessDeniedError("Revoked before construction")

    assert Actions().open() is None
    assert "Revoked before construction" in warning.call_args.args[2]
