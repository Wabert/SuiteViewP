"""Initial access-control provisioning without changing existing permissions."""

from unittest.mock import MagicMock

import pytest

from suiteview.core.build_env import ReadOnlyDataError
from tools.admin import create_access_control as setup


def test_requested_roles_apps_and_users():
    assert setup.ROLES == (
        ("ADMIN", 1, 1, 1, "All access to all roles and apps, even experimental"),
        ("SUPPORT", 0, 1, 1, "All access except for some apps"),
        ("BUSINESS", 0, 0, 1, "Access to generate policy support folders"),
        ("NONBUSINESS", 0, 0, 0,
         "Cannot make updates to database or policy support folders"),
    )
    assert len(setup.APPS) == len(set(setup.APPS)) == 14
    assert len(setup.ROLE_APPS) == len(set(setup.ROLE_APPS)) == 25
    apps_by_role = {
        role[0]: {app for code, app in setup.ROLE_APPS if code == role[0]}
        for role in setup.ROLES
    }
    assert apps_by_role["ADMIN"] == set()
    assert apps_by_role["SUPPORT"] == set(setup.APPS) - {
        "ALBERT", "ATTENTIONALBERT", "PASSWORDMANAGER"}
    assert apps_by_role["BUSINESS"] == apps_by_role["NONBUSINESS"] == {
        "POLVIEW", "FILENAV", "ABR", "RERUN", "QUERY", "SCRATCHPAD", "SCREENSHOT",
    }
    assert len(setup.USERS) == len({row[0] for row in setup.USERS}) == 22
    assert {row[0] for row in setup.USERS if row[2]} == {"AB7Y02", "AC1Z42"}
    for network_id, name, enabled, role in setup.USERS:
        assert network_id == network_id.strip().upper()
        assert name == name.strip()
        assert enabled in (0, 1)
        assert role in apps_by_role
    assert setup.USERS[0][1] == "Rboert Haessly"


def connection_with_tables(monkeypatch, tables=()):
    connection = MagicMock()
    cursor = connection.cursor.return_value
    cursor.execute.return_value.fetchone.return_value = ("UL_Rates", "test-server")
    monkeypatch.setattr(setup, "existing_tables", lambda cursor: list(tables))
    cursor.execute.return_value.fetchall.side_effect = [
        list(reversed(rows)) for rows in setup.SEED.values()
    ]
    return connection, cursor


def test_check_does_not_create(monkeypatch):
    connection, cursor = connection_with_tables(monkeypatch)
    assert setup.provision(connection, apply=False)["state"] == "not_created"
    cursor.executemany.assert_not_called()
    connection.commit.assert_not_called()
    connection.rollback.assert_called_once()
    cursor.close.assert_called_once()


def test_create_all_tables_atomically(monkeypatch):
    connection, cursor = connection_with_tables(monkeypatch)
    assert setup.provision(connection, apply=True)["created"] is True
    connection.commit.assert_called_once()
    assert cursor.executemany.call_count == 3
    for call, rows in zip(cursor.executemany.call_args_list, setup.SEED.values()):
        assert call.args[0].count("?") == len(rows[0])
        assert call.args[1] == rows
    connection.rollback.assert_called_once()


def test_existing_seed_is_verified_without_writes(monkeypatch):
    connection, cursor = connection_with_tables(monkeypatch, setup.DDL)
    assert setup.provision(connection, apply=True)["state"] == "verified_existing"
    cursor.executemany.assert_not_called()
    connection.commit.assert_not_called()


def test_existing_different_values_are_not_overwritten(monkeypatch):
    connection, cursor = connection_with_tables(monkeypatch, setup.DDL)
    cursor.execute.return_value.fetchall.side_effect = [[
        ("ADMIN", 0, 1, 1, setup.ROLES[0][4]), *setup.ROLES[1:],
    ]]
    with pytest.raises(ValueError, match="does not match"):
        setup.provision(connection, apply=False)
    cursor.executemany.assert_not_called()
    connection.commit.assert_not_called()


def test_partial_setup_is_not_modified(monkeypatch):
    connection, cursor = connection_with_tables(monkeypatch, ["SV_AccessRole"])
    with pytest.raises(ValueError, match="Partial"):
        setup.provision(connection, apply=True)
    cursor.executemany.assert_not_called()
    connection.commit.assert_not_called()


def test_verification_failure_rolls_back_creation(monkeypatch):
    connection, cursor = connection_with_tables(monkeypatch)
    cursor.execute.return_value.fetchall.side_effect = [[]]
    with pytest.raises(ValueError, match="does not match"):
        setup.provision(connection, apply=True)
    connection.commit.assert_not_called()
    connection.rollback.assert_called_once()


def test_wrong_database_is_rejected(monkeypatch):
    connection, cursor = connection_with_tables(monkeypatch)
    cursor.execute.return_value.fetchone.return_value = ("WrongDatabase", "test-server")
    with pytest.raises(ValueError, match="Expected UL_Rates"):
        setup.provision(connection, apply=False)
    cursor.executemany.assert_not_called()


def test_read_only_role_cannot_create_tables(monkeypatch):
    from suiteview.core import access_control

    monkeypatch.setattr(access_control, "get_access", lambda **_: access_control.EffectiveAccess(
        "READER", "BUSINESS", False, False, False))
    connection = MagicMock()
    with pytest.raises(ReadOnlyDataError):
        setup.provision(connection, apply=True)
    connection.cursor.assert_not_called()
