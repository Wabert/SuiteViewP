"""Process-local registry for cross-app launches without upward imports."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any


class AppLauncherError(RuntimeError):
    """A requested SuiteView application has no registered launcher."""


_launchers: dict[str, Callable[..., Any]] = {}


def register_app_launcher(app_id: str, factory: Callable[..., Any]) -> None:
    """Register *factory* as the launcher for *app_id*."""

    _launchers[app_id.upper()] = factory


def launch_app(app_id: str, *args, **kwargs):
    """Launch *app_id* through the shell-owned factory."""

    key = app_id.upper()
    try:
        factory = _launchers[key]
    except KeyError:
        raise AppLauncherError(f"No SuiteView launcher registered for {key}.") from None
    return factory(*args, **kwargs)


def clear_app_launchers() -> None:
    """Clear registrations for tests that need an isolated registry."""

    _launchers.clear()
