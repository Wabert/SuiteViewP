"""ADMIN/developer maintenance of SuiteView's live UL_Rates access-control tables.

Application-wide enforcement lives in core.access_control. SQL Server permissions
must separately protect these tables from direct external writes.
"""

from __future__ import annotations

from contextlib import closing, contextmanager
from dataclasses import dataclass, replace
import logging
import re
from collections.abc import Iterator

import pyodbc

from suiteview.core.build_env import guard_data_writable, has_developer_access
from suiteview.core.access_control import (
    APP_CODES, clear_access_cache, connect_access_database as _connect,
    current_network_id,
)

logger = logging.getLogger(__name__)

@dataclass(frozen=True)
class AccessUser:
    network_id: str
    name: str
    enabled: bool
    role_code: str


@dataclass(frozen=True)
class AccessRole:
    role_code: str
    description: str
    all_apps: bool
    can_update_database: bool
    can_write_support_files: bool
    apps: frozenset[str] = frozenset()


@dataclass(frozen=True)
class AccessSnapshot:
    users: tuple[AccessUser, ...]
    roles: tuple[AccessRole, ...]
    actor_id: str


def _require_admin(snapshot: AccessSnapshot) -> None:
    if has_developer_access():
        return
    if not any(
        user.network_id == snapshot.actor_id and user.enabled and user.role_code == "ADMIN"
        for user in snapshot.users
    ) or not any(role.role_code == "ADMIN" for role in snapshot.roles):
        raise PermissionError(
            f"{snapshot.actor_id} is not an enabled ADMIN. "
            "Administrator is available only to the ADMIN role."
        )


def _check_last_admin(users: tuple[AccessUser, ...]) -> None:
    if not any(user.enabled and user.role_code == "ADMIN" for user in users):
        raise ValueError("Keep at least one enabled ADMIN to avoid locking everyone out.")


def _check_original(current, original) -> None:
    if current != original:
        raise ValueError(
            "This record was changed by another administrator. "
            "Refresh and review the latest values before saving."
        )


def _code(value: str, label: str, max_length: int = 50) -> str:
    value = value.strip().upper()
    if not re.fullmatch(r"[A-Z0-9][A-Z0-9_.-]*", value) or len(value) > max_length:
        raise ValueError(
            f"{label} must contain 1-{max_length} letters, digits, underscores, dots or hyphens."
        )
    return value


def _text(value: str, label: str, max_length: int) -> str:
    value = value.strip()
    if not value or len(value.encode("utf-16-le")) // 2 > max_length:
        raise ValueError(f"{label} must contain 1-{max_length} characters.")
    return value


def _check_bits(*values: bool) -> None:
    if any(type(value) is not bool for value in values):
        raise ValueError("Permission values must be True or False.")


class AccessRepository:
    """Each operation checks source access or the packaged user's ADMIN role."""

    @contextmanager
    def _cursor(self, *, write: bool = False) -> Iterator[tuple[pyodbc.Connection, pyodbc.Cursor]]:
        if write:
            guard_data_writable("manage SuiteView access controls")
        with closing(_connect()) as connection:
            try:
                with closing(connection.cursor()) as cursor:
                    database = cursor.execute("SELECT DB_NAME()").fetchone()[0]
                    if str(database).upper() != "UL_RATES":
                        raise RuntimeError(f"Expected UL_Rates, connected to {database!r}.")
                    if write:
                        cursor.execute("SET XACT_ABORT ON")
                    yield connection, cursor
            finally:
                connection.rollback()

    def is_admin(self) -> bool:
        if has_developer_access():
            return True
        actor = current_network_id()
        with self._cursor() as (_, cursor):
            row = cursor.execute(
                "SELECT u.[Enabled], u.[RoleCode] FROM [dbo].[SV_AccessUser] u "
                "JOIN [dbo].[SV_AccessRole] r ON r.[RoleCode] = u.[RoleCode] "
                "WHERE u.[NetworkID] = ?", actor,
            ).fetchone()
            return row is not None and bool(row[0]) and row[1] == "ADMIN"

    def _snapshot(self, cursor: pyodbc.Cursor, *, write: bool = False) -> AccessSnapshot:
        # The small tables share a lock order; range locks serialize all admin writes,
        # including two admins trying to disable each other at the same time.
        lock = " WITH (UPDLOCK, HOLDLOCK)" if write else " WITH (HOLDLOCK)"
        roles = cursor.execute(
            "SELECT [RoleCode], [Description], [AllApps], [CanUpdateDatabase], "
            f"[CanWriteSupportFiles] FROM [dbo].[SV_AccessRole]{lock} ORDER BY [RoleCode]"
        ).fetchall()
        users = cursor.execute(
            "SELECT [NetworkID], [Name], [Enabled], [RoleCode] "
            f"FROM [dbo].[SV_AccessUser]{lock} ORDER BY [NetworkID]"
        ).fetchall()
        apps = cursor.execute(
            f"SELECT [RoleCode], [AppCode] FROM [dbo].[SV_AccessRoleApp]{lock} "
            "ORDER BY [RoleCode], [AppCode]"
        ).fetchall()
        snapshot = AccessSnapshot(
            users=tuple(AccessUser(row[0], row[1], bool(row[2]), row[3]) for row in users),
            roles=tuple(
                AccessRole(
                    row[0], row[1], bool(row[2]), bool(row[3]), bool(row[4]),
                    frozenset(app[1] for app in apps if app[0] == row[0]),
                )
                for row in roles
            ),
            actor_id=current_network_id(),
        )
        _require_admin(snapshot)
        return snapshot

    def load(self) -> AccessSnapshot:
        with self._cursor() as (_, cursor):
            return self._snapshot(cursor)

    def save_user(self, user: AccessUser, *, original: AccessUser | None) -> None:
        user = replace(
            user, network_id=_code(user.network_id, "Network ID", 128),
            name=_text(user.name, "Name", 200), role_code=_code(user.role_code, "Role"),
        )
        _check_bits(user.enabled)
        if original is not None and user.network_id != original.network_id:
            raise ValueError("Network ID cannot be renamed. Add a new user instead.")
        with self._cursor(write=True) as (connection, cursor):
            snapshot = self._snapshot(cursor, write=True)
            current = next((u for u in snapshot.users if u.network_id == user.network_id), None)
            _check_original(current, original)
            if not any(role.role_code == user.role_code for role in snapshot.roles):
                raise ValueError("The selected role no longer exists. Refresh and select a role.")
            _check_last_admin(
                tuple(u for u in snapshot.users if u.network_id != user.network_id) + (user,)
            )
            if original is None:
                cursor.execute(
                    "INSERT INTO [dbo].[SV_AccessUser] "
                    "([NetworkID], [Name], [Enabled], [RoleCode]) VALUES (?, ?, ?, ?)",
                    user.network_id, user.name, user.enabled, user.role_code,
                )
            else:
                cursor.execute(
                    "UPDATE [dbo].[SV_AccessUser] SET [Name] = ?, [Enabled] = ?, "
                    "[RoleCode] = ? WHERE [NetworkID] = ?",
                    user.name, user.enabled, user.role_code, user.network_id,
                )
            connection.commit()
            clear_access_cache()
            logger.info("Administrator %s saved user %s", snapshot.actor_id, user.network_id)

    def delete_user(self, original: AccessUser) -> None:
        with self._cursor(write=True) as (connection, cursor):
            snapshot = self._snapshot(cursor, write=True)
            current = next((u for u in snapshot.users if u.network_id == original.network_id), None)
            _check_original(current, original)
            _check_last_admin(tuple(u for u in snapshot.users if u.network_id != original.network_id))
            cursor.execute(
                "DELETE FROM [dbo].[SV_AccessUser] WHERE [NetworkID] = ?", original.network_id,
            )
            connection.commit()
            clear_access_cache()
            logger.info("Administrator %s deleted user %s", snapshot.actor_id, original.network_id)

    def save_role(self, role: AccessRole, *, original: AccessRole | None) -> None:
        role = replace(
            role, role_code=_code(role.role_code, "Role code"),
            description=_text(role.description, "Description", 500),
            apps=frozenset(_code(app, "App code") for app in role.apps),
        )
        _check_bits(role.all_apps, role.can_update_database, role.can_write_support_files)
        if original is not None and role.role_code != original.role_code:
            raise ValueError("Role code cannot be renamed. Add a new role instead.")
        if "ADMINISTRATOR" in role.apps:
            raise ValueError("Administrator is ADMIN-only; it cannot be granted by an app whitelist.")
        with self._cursor(write=True) as (connection, cursor):
            snapshot = self._snapshot(cursor, write=True)
            current = next((r for r in snapshot.roles if r.role_code == role.role_code), None)
            _check_original(current, original)
            unknown = role.apps - set(APP_CODES) - (original.apps if original else frozenset())
            if unknown:
                raise ValueError(f"Unknown app codes: {', '.join(sorted(unknown))}.")
            if original is None:
                cursor.execute(
                    "INSERT INTO [dbo].[SV_AccessRole] ([RoleCode], [Description], "
                    "[AllApps], [CanUpdateDatabase], [CanWriteSupportFiles]) VALUES (?, ?, ?, ?, ?)",
                    role.role_code, role.description, role.all_apps,
                    role.can_update_database, role.can_write_support_files,
                )
            else:
                cursor.execute(
                    "UPDATE [dbo].[SV_AccessRole] SET [Description] = ?, [AllApps] = ?, "
                    "[CanUpdateDatabase] = ?, [CanWriteSupportFiles] = ? WHERE [RoleCode] = ?",
                    role.description, role.all_apps, role.can_update_database,
                    role.can_write_support_files, role.role_code,
                )
            cursor.execute(
                "DELETE FROM [dbo].[SV_AccessRoleApp] WHERE [RoleCode] = ?", role.role_code,
            )
            if role.apps:
                cursor.executemany(
                    "INSERT INTO [dbo].[SV_AccessRoleApp] ([RoleCode], [AppCode]) VALUES (?, ?)",
                    [(role.role_code, app) for app in sorted(role.apps)],
                )
            connection.commit()
            clear_access_cache()
            logger.info("Administrator %s saved role %s and its apps", snapshot.actor_id, role.role_code)

    def delete_role(self, original: AccessRole) -> None:
        if original.role_code == "ADMIN":
            raise ValueError("The ADMIN role cannot be deleted.")
        with self._cursor(write=True) as (connection, cursor):
            snapshot = self._snapshot(cursor, write=True)
            current = next((r for r in snapshot.roles if r.role_code == original.role_code), None)
            _check_original(current, original)
            if any(user.role_code == original.role_code for user in snapshot.users):
                raise ValueError("Reassign all users of this role before deleting it, including disabled users.")
            cursor.execute(
                "DELETE FROM [dbo].[SV_AccessRoleApp] WHERE [RoleCode] = ?", original.role_code,
            )
            cursor.execute(
                "DELETE FROM [dbo].[SV_AccessRole] WHERE [RoleCode] = ?", original.role_code,
            )
            connection.commit()
            clear_access_cache()
            logger.info("Administrator %s deleted role %s", snapshot.actor_id, original.role_code)
