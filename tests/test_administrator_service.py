from dataclasses import replace
from unittest.mock import MagicMock

import pyodbc
import pytest

from suiteview.administrator import service
from suiteview.administrator.service import AccessRole, AccessUser
from suiteview.core import build_env


ADMIN = AccessRole("ADMIN", "Administrator", True, True, True)
BUSINESS = AccessRole("BUSINESS", "Business", False, False, True, frozenset({"POLVIEW", "ABR"}))
ACTOR = AccessUser("AB7Y02", "Administrator", True, "ADMIN")
OTHER_ADMIN = AccessUser("AC1Z42", "Another admin", True, "ADMIN")
USER = AccessUser("AB8Y21", "A user", False, "BUSINESS")


@pytest.fixture(autouse=True)
def packaged_build(monkeypatch):
    monkeypatch.setattr(build_env.sys, "frozen", True, raising=False)


@pytest.fixture
def database(monkeypatch):
    monkeypatch.setattr(service, "current_network_id", lambda: ACTOR.network_id)
    monkeypatch.setattr(service, "guard_data_writable", MagicMock())
    connection = MagicMock()
    cursor = connection.cursor.return_value
    state = {"users": [ACTOR, OTHER_ADMIN, USER], "roles": [ADMIN, BUSINESS]}

    def execute(sql, *params):
        cursor.fetchone.return_value = None
        cursor.fetchall.return_value = []
        if sql == "SELECT DB_NAME()":
            cursor.fetchone.return_value = ("UL_RATES",)
        elif sql.startswith("SELECT u.[Enabled]"):
            user = next((u for u in state["users"] if u.network_id == params[0]), None)
            if user is not None:
                cursor.fetchone.return_value = (user.enabled, user.role_code)
        elif sql.startswith("SELECT [RoleCode], [Description]"):
            cursor.fetchall.return_value = [
                (r.role_code, r.description, r.all_apps, r.can_update_database,
                 r.can_write_support_files) for r in state["roles"]
            ]
        elif sql.startswith("SELECT [NetworkID]"):
            cursor.fetchall.return_value = [
                (u.network_id, u.name, u.enabled, u.role_code) for u in state["users"]
            ]
        elif sql.startswith("SELECT [RoleCode], [AppCode]"):
            cursor.fetchall.return_value = [
                (r.role_code, app) for r in state["roles"] for app in r.apps
            ]
        return cursor

    cursor.execute.side_effect = execute
    monkeypatch.setattr(service, "_connect", lambda: connection)
    return state, connection, cursor


def mutations(cursor):
    return [call for call in cursor.execute.call_args_list
            if call.args[0].startswith(("INSERT", "UPDATE", "DELETE"))]


def test_load_exact_snapshot_and_cleanup(database):
    state, connection, cursor = database
    snapshot = service.AccessRepository().load()
    assert snapshot.users == tuple(state["users"])
    assert snapshot.roles == tuple(state["roles"])
    assert snapshot.actor_id == "AB7Y02"
    connection.commit.assert_not_called()
    connection.rollback.assert_called_once()
    connection.close.assert_called_once()
    cursor.close.assert_called_once()


@pytest.mark.parametrize("actor", [
    None, replace(ACTOR, enabled=False), replace(ACTOR, role_code="BUSINESS"),
])
@pytest.mark.parametrize("operation", ["load", "save_user", "delete_user", "save_role", "delete_role"])
def test_every_operation_rejects_non_admin(database, actor, operation):
    state, connection, cursor = database
    state["users"] = [OTHER_ADMIN, USER] + ([actor] if actor else [])
    repo = service.AccessRepository()
    actions = {
        "load": lambda: repo.load(),
        "save_user": lambda: repo.save_user(replace(USER, enabled=True), original=USER),
        "delete_user": lambda: repo.delete_user(USER),
        "save_role": lambda: repo.save_role(replace(BUSINESS, all_apps=True), original=BUSINESS),
        "delete_role": lambda: repo.delete_role(BUSINESS),
    }
    with pytest.raises(PermissionError, match="enabled ADMIN"):
        actions[operation]()
    assert mutations(cursor) == []
    connection.commit.assert_not_called()
    connection.rollback.assert_called_once()


def test_allapps_and_database_writes_do_not_grant_administration(database):
    state, _, _ = database
    state["users"] = [replace(ACTOR, role_code="BUSINESS")]
    state["roles"] = [replace(BUSINESS, all_apps=True, can_update_database=True)]
    assert service.AccessRepository().is_admin() is False


def test_menu_is_admin_only_and_unknown_user_denied(database):
    state, _, _ = database
    assert service.AccessRepository().is_admin() is True
    state["users"] = []
    assert service.AccessRepository().is_admin() is False


def test_save_user_uses_parameters_and_locked_authorization(database):
    _, connection, cursor = database
    user = AccessUser(" new42 ", " O'Connor ", True, "business")
    service.AccessRepository().save_user(user, original=None)
    write = mutations(cursor)[0]
    assert write.args[1:] == ("NEW42", "O'Connor", True, "BUSINESS")
    assert "O'Connor" not in write.args[0]
    snapshot_queries = [c.args[0] for c in cursor.execute.call_args_list
                        if c.args[0].startswith("SELECT [")]
    assert len(snapshot_queries) == 3
    assert all("UPDLOCK, HOLDLOCK" in sql for sql in snapshot_queries)
    connection.commit.assert_called_once()


@pytest.mark.parametrize("change", ["disable", "reassign", "delete"])
def test_last_enabled_admin_protected(database, change):
    state, connection, cursor = database
    state["users"] = [ACTOR, USER, replace(OTHER_ADMIN, enabled=False)]
    repo = service.AccessRepository()
    with pytest.raises(ValueError, match="at least one enabled ADMIN"):
        if change == "delete":
            repo.delete_user(ACTOR)
        else:
            new = replace(ACTOR, enabled=False) if change == "disable" else replace(ACTOR, role_code="BUSINESS")
            repo.save_user(new, original=ACTOR)
    assert not mutations(cursor)
    connection.commit.assert_not_called()


def test_second_admin_allows_self_disable(database):
    _, connection, _ = database
    service.AccessRepository().save_user(replace(ACTOR, enabled=False), original=ACTOR)
    connection.commit.assert_called_once()


@pytest.mark.parametrize("operation", ["save_user", "delete_user", "save_role", "delete_role"])
def test_concurrent_edits_are_not_overwritten(database, operation):
    state, connection, cursor = database
    state["users"][2] = replace(USER, enabled=True)
    state["roles"][1] = replace(BUSINESS, apps=frozenset({"RERUN"}))
    repo = service.AccessRepository()
    actions = {
        "save_user": lambda: repo.save_user(USER, original=USER),
        "delete_user": lambda: repo.delete_user(USER),
        "save_role": lambda: repo.save_role(BUSINESS, original=BUSINESS),
        "delete_role": lambda: repo.delete_role(BUSINESS),
    }
    with pytest.raises(ValueError, match="another administrator"):
        actions[operation]()
    assert not mutations(cursor)
    connection.commit.assert_not_called()


def test_duplicate_user_not_replaced(database):
    _, connection, _ = database
    with pytest.raises(ValueError, match="another administrator"):
        service.AccessRepository().save_user(USER, original=None)
    connection.commit.assert_not_called()


def test_delete_user(database):
    _, connection, cursor = database
    service.AccessRepository().delete_user(USER)
    assert mutations(cursor)[0].args[1:] == (USER.network_id,)
    connection.commit.assert_called_once()


def test_delete_assigned_role_even_disabled_users_is_blocked(database):
    _, connection, cursor = database
    with pytest.raises(ValueError, match="including disabled users"):
        service.AccessRepository().delete_role(BUSINESS)
    assert not mutations(cursor)
    connection.commit.assert_not_called()


def test_delete_admin_role_is_blocked(database):
    with pytest.raises(ValueError, match="ADMIN role cannot"):
        service.AccessRepository().delete_role(ADMIN)


def test_delete_unassigned_role_removes_grants_before_role(database):
    state, connection, cursor = database
    state["users"] = [ACTOR]
    service.AccessRepository().delete_role(BUSINESS)
    writes = mutations(cursor)
    assert "SV_AccessRoleApp" in writes[0].args[0]
    assert "SV_AccessRole]" in writes[1].args[0]
    connection.commit.assert_called_once()


@pytest.mark.parametrize("original", [None, BUSINESS])
def test_role_and_grants_saved_atomically(database, original):
    _, connection, cursor = database
    role = replace(BUSINESS, role_code="NEW" if original is None else "BUSINESS",
                   apps=frozenset({"QUERY", "RERUN"}))
    service.AccessRepository().save_role(role, original=original)
    assert len(mutations(cursor)) == 2
    assert cursor.executemany.call_args.args[1] == [
        (role.role_code, "QUERY"), (role.role_code, "RERUN"),
    ]
    connection.commit.assert_called_once()


def test_failed_grant_insert_rolls_back_role_update(database):
    _, connection, cursor = database
    cursor.executemany.side_effect = pyodbc.IntegrityError("test failure")
    with pytest.raises(pyodbc.IntegrityError):
        service.AccessRepository().save_role(BUSINESS, original=BUSINESS)
    connection.commit.assert_not_called()
    connection.rollback.assert_called_once()


@pytest.mark.parametrize("app", ["ADMINISTRATOR", "UNKNOWN"])
def test_whitelist_cannot_grant_administrator_or_unknown_apps(database, app):
    _, connection, cursor = database
    with pytest.raises(ValueError):
        service.AccessRepository().save_role(replace(BUSINESS, apps=frozenset({app})), original=BUSINESS)
    connection.commit.assert_not_called()
    assert not mutations(cursor)


def test_preserves_existing_future_app_codes(database):
    state, connection, _ = database
    original = replace(BUSINESS, apps=BUSINESS.apps | {"FUTURE_APP"})
    state["roles"][1] = original
    service.AccessRepository().save_role(replace(original, description="Updated"), original=original)
    connection.commit.assert_called_once()


@pytest.mark.parametrize("changes", [
    {"name": " "}, {"name": "x" * 201}, {"network_id": "bad;sql"},
    {"enabled": "0"}, {"role_code": "MISSING"},
])
def test_user_input_validation(database, changes):
    _, connection, cursor = database
    with pytest.raises(ValueError):
        service.AccessRepository().save_user(replace(USER, **changes), original=None)
    assert not mutations(cursor)
    connection.commit.assert_not_called()


def test_denied_database_write_permission_never_connects(monkeypatch):
    from suiteview.core import access_control
    from suiteview.core.build_env import ReadOnlyDataError

    monkeypatch.setattr(access_control, "get_access", lambda **_: access_control.EffectiveAccess(
        ACTOR.network_id, "ADMIN", True, False, False))
    connect = MagicMock()
    monkeypatch.setattr(service, "_connect", connect)
    repo = service.AccessRepository()
    with pytest.raises(ReadOnlyDataError, match="CanUpdateDatabase"):
        repo.save_user(USER, original=USER)
    connect.assert_not_called()


def test_native_identity_ignores_environment(monkeypatch):
    import win32api
    monkeypatch.setenv("USERNAME", "SPOOFED")
    monkeypatch.setattr(win32api, "GetUserName", lambda: " ab7y02 ")
    assert service.current_network_id() == "AB7Y02"


def test_database_failure_propagates(monkeypatch):
    monkeypatch.setattr(service, "current_network_id", lambda: ACTOR.network_id)
    monkeypatch.setattr(service, "_connect", MagicMock(side_effect=pyodbc.Error("offline")))
    with pytest.raises(pyodbc.Error, match="offline"):
        service.AccessRepository().is_admin()


@pytest.mark.parametrize("actor", [
    None, replace(ACTOR, enabled=False), replace(ACTOR, role_code="BUSINESS"),
])
@pytest.mark.parametrize("operation", ["load", "save_user", "delete_user", "save_role", "delete_role"])
def test_source_operations_ignore_actor_access_record(database, monkeypatch, actor, operation):
    state, connection, _ = database
    monkeypatch.setattr(build_env.sys, "frozen", False)
    state["users"] = [OTHER_ADMIN, USER] + ([actor] if actor else [])
    unused = replace(BUSINESS, role_code="UNUSED")
    state["roles"].append(unused)
    repo = service.AccessRepository()
    actions = {
        "load": repo.load,
        "save_user": lambda: repo.save_user(replace(USER, enabled=True), original=USER),
        "delete_user": lambda: repo.delete_user(USER),
        "save_role": lambda: repo.save_role(replace(BUSINESS, all_apps=True), original=BUSINESS),
        "delete_role": lambda: repo.delete_role(unused),
    }
    actions[operation]()
    if operation == "load":
        connection.commit.assert_not_called()
    else:
        connection.commit.assert_called_once()


def test_source_menu_access_does_not_query_database_or_identity(monkeypatch):
    monkeypatch.setattr(build_env.sys, "frozen", False)
    connect = MagicMock(side_effect=AssertionError("Must not query access tables"))
    identity = MagicMock(side_effect=AssertionError("Must not depend on user ID"))
    monkeypatch.setattr(service, "_connect", connect)
    monkeypatch.setattr(service, "current_network_id", identity)
    assert service.AccessRepository().is_admin()
    connect.assert_not_called()
    identity.assert_not_called()


def test_source_can_recover_empty_access_tables(database, monkeypatch):
    state, connection, _ = database
    monkeypatch.setattr(build_env.sys, "frozen", False)
    state["users"] = []
    state["roles"] = []
    repo = service.AccessRepository()
    assert repo.load().users == ()
    repo.save_role(ADMIN, original=None)
    state["roles"] = [ADMIN]
    repo.save_user(ACTOR, original=None)
    assert connection.commit.call_count == 2


def test_source_does_not_hide_real_database_errors(monkeypatch):
    monkeypatch.setattr(build_env.sys, "frozen", False)
    monkeypatch.setattr(service, "_connect", MagicMock(side_effect=pyodbc.Error("offline")))
    with pytest.raises(pyodbc.Error, match="offline"):
        service.AccessRepository().load()


def test_source_preserves_last_admin_safeguard(database, monkeypatch):
    state, connection, _ = database
    monkeypatch.setattr(build_env.sys, "frozen", False)
    state["users"] = [ACTOR]
    with pytest.raises(ValueError, match="at least one enabled ADMIN"):
        service.AccessRepository().delete_user(ACTOR)
    connection.commit.assert_not_called()
