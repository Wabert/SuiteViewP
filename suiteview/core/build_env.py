"""Source/distribution detection and role-backed shared-database write guards.

PyInstaller sets sys.frozen on the packaged EXE. Source execution always has
developer access; packaged execution uses live access-control permissions.
"""
from __future__ import annotations

import sys


def is_distribution_build() -> bool:
    """True in the packaged (PyInstaller) EXE, False when running from source."""
    return bool(getattr(sys, "frozen", False))


def app_unavailable_reason(app_code: str) -> str:
    """Build capabilities are separate from grants stored in the access tables."""
    if app_code == "ALBERT" and is_distribution_build():
        return "Albert is not available in the packaged EXE. It remains available when running from source."
    return ""


def is_data_read_only() -> bool:
    """UI state for the current role's shared-database write permission."""
    from suiteview.core.access_control import get_access

    return not get_access().can_update_database


def has_developer_access() -> bool:
    """Source runs bypass all application permissions; packaged EXEs never do."""
    return not is_distribution_build()


class ReadOnlyDataError(PermissionError):
    """The user's role does not allow shared-database writes."""


def guard_data_writable(action: str = "modify data") -> None:
    """Recheck live permissions immediately before shared-database mutation."""
    from suiteview.core.access_control import get_access

    if not get_access(refresh=True).can_update_database:
        raise ReadOnlyDataError(
            f"Your SuiteView role does not permit you to {action} "
            "(CanUpdateDatabase is off)."
        )
