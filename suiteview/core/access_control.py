"""Runtime authorization for packaged SuiteView; source runs remain unrestricted."""

from contextlib import closing
from dataclasses import dataclass
from functools import wraps
import inspect
import logging
from threading import RLock

import pyodbc

from suiteview.core.build_env import app_unavailable_reason, has_developer_access

logger = logging.getLogger(__name__)

APP_CODES = (
    "POLVIEW", "FILENAV", "ABR", "RERUN", "QUERY", "ALBERT",
    "SCRATCHPAD", "HISTORY", "SCREENSHOT", "MAINFRAMENAV",
    "RATEMANAGER", "EMAILATTACHMENTS",
)


class AccessDeniedError(PermissionError):
    """The current Windows user is not authorized for the requested operation."""


class AccessUnavailableError(RuntimeError):
    """Live permissions could not be verified; access must not be assumed."""


@dataclass(frozen=True)
class EffectiveAccess:
    actor_id: str
    role_code: str
    all_apps: bool
    can_update_database: bool
    can_write_support_files: bool
    apps: frozenset[str] = frozenset()
    developer: bool = False

    def allows_app(self, app_code: str) -> bool:
        if app_unavailable_reason(app_code):
            return False
        if app_code == "ADMINISTRATOR":
            return self.developer or self.role_code == "ADMIN"
        return self.developer or self.all_apps or app_code in self.apps


_DEVELOPER_ACCESS = EffectiveAccess("DEVELOPER", "DEVELOPER", True, True, True, developer=True)
_cached_access: EffectiveAccess | None = None
_access_lock = RLock()


def current_network_id() -> str:
    """Read the Windows security context, not an editable environment variable."""
    import win32api

    actor = win32api.GetUserName().strip().upper()
    if not actor:
        raise AccessDeniedError("Windows did not provide a network ID.")
    return actor


def connect_access_database() -> pyodbc.Connection:
    connection = pyodbc.connect("DSN=UL_Rates", autocommit=False, timeout=10)
    connection.timeout = 15
    return connection


def clear_access_cache() -> None:
    global _cached_access
    with _access_lock:
        _cached_access = None


def _load_access() -> EffectiveAccess:
    actor = current_network_id()
    try:
        with closing(connect_access_database()) as connection:
            try:
                with closing(connection.cursor()) as cursor:
                    database = cursor.execute("SELECT DB_NAME()").fetchone()[0]
                    if str(database).upper() != "UL_RATES":
                        raise AccessUnavailableError(
                            f"Expected UL_Rates for access checks, connected to {database!r}."
                        )
                    rows = cursor.execute(
                        "SELECT u.[Enabled], r.[RoleCode], r.[AllApps], "
                        "r.[CanUpdateDatabase], r.[CanWriteSupportFiles], a.[AppCode] "
                        "FROM [dbo].[SV_AccessUser] u "
                        "JOIN [dbo].[SV_AccessRole] r ON r.[RoleCode] = u.[RoleCode] "
                        "LEFT JOIN [dbo].[SV_AccessRoleApp] a ON a.[RoleCode] = r.[RoleCode] "
                        "WHERE u.[NetworkID] = ?", actor,
                    ).fetchall()
            finally:
                connection.rollback()
    except pyodbc.Error as error:
        logger.exception("Cannot verify SuiteView access for %s", actor)
        raise AccessUnavailableError(
            "Cannot verify SuiteView permissions in UL_Rates. "
            "Check your network/VPN and database connection, then try again."
        ) from error
    if not rows or not bool(rows[0][0]):
        raise AccessDeniedError(
            f"SuiteView access is not enabled for {actor}. "
            "Ask a SuiteView administrator to add or enable your user and assign a role."
        )
    row = rows[0]
    return EffectiveAccess(
        actor, row[1], bool(row[2]), bool(row[3]), bool(row[4]),
        frozenset(record[5] for record in rows if record[5] is not None),
    )


def get_access(*, refresh: bool = False) -> EffectiveAccess:
    """UI reads share a snapshot; startup, app entry and mutations revalidate it."""
    if has_developer_access():
        return _DEVELOPER_ACCESS
    global _cached_access
    with _access_lock:
        if refresh or _cached_access is None:
            _cached_access = None
            _cached_access = _load_access()
        return _cached_access


def can_access_app(app_code: str) -> bool:
    return get_access().allows_app(app_code)


def guard_app_access(app_code: str) -> None:
    unavailable = app_unavailable_reason(app_code)
    if unavailable:
        raise AccessDeniedError(unavailable)
    access = get_access(refresh=True)
    if not access.allows_app(app_code):
        raise AccessDeniedError(
            f"Your SuiteView role ({access.role_code}) does not permit {app_code}. "
            "Contact a SuiteView administrator."
        )


def can_write_support_files() -> bool:
    return get_access().can_write_support_files


def guard_support_files_writable(action: str = "modify policy support files") -> None:
    if not get_access(refresh=True).can_write_support_files:
        raise AccessDeniedError(
            f"Your SuiteView role does not permit you to {action} "
            "(CanWriteSupportFiles is off)."
        )


def requires_app_access(app_code: str):
    """Protect a callable by rechecking access and raising on denial.

    UI code should use :mod:`suiteview.ui.access_control` so presentation
    concerns (message boxes) stay out of the core authorization policy.
    """
    def decorate(method):
        accepts_positional = any(
            parameter.kind in (
                inspect.Parameter.POSITIONAL_ONLY,
                inspect.Parameter.POSITIONAL_OR_KEYWORD,
                inspect.Parameter.VAR_POSITIONAL,
            )
            for parameter in tuple(inspect.signature(method).parameters.values())[1:]
        )

        @wraps(method)
        def checked(self, *args, **kwargs):
            guard_app_access(app_code)
            # Qt forwards clicked(bool) to a variadic wrapper; retain the
            # original zero-argument slot's signal-argument trimming for callers
            # that deliberately use this core decorator at a non-UI boundary.
            if not accepts_positional and len(args) == 1 and isinstance(args[0], bool):
                args = ()
            return method(self, *args, **kwargs)
        return checked
    return decorate
