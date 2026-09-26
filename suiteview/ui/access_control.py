"""UI-facing wrappers for SuiteView runtime authorization."""

from __future__ import annotations

from functools import wraps
import inspect
import logging

from PyQt6.QtWidgets import QMessageBox, QWidget

from suiteview.core import access_control as core_access
from suiteview.core.access_control import AccessDeniedError, AccessUnavailableError

logger = logging.getLogger(__name__)


def requires_app_access(app_code: str):
    """Protect a Qt slot and report authorization failures to the user."""

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
            try:
                core_access.guard_app_access(app_code)
                if not accepts_positional and len(args) == 1 and isinstance(args[0], bool):
                    args = ()
                return method(self, *args, **kwargs)
            except (AccessDeniedError, AccessUnavailableError) as error:
                logger.warning("Blocked %s: %s", app_code, error)
                QMessageBox.warning(
                    self if isinstance(self, QWidget) else None,
                    "SuiteView Access",
                    str(error),
                )
                return None

        return checked

    return decorate
