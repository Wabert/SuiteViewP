"""Which plancodes a RERUN user may illustrate: ``dbo.SV_RERUN_Plancode_Control``.

The control table lists every in-force base plancode with its product type and a
``CanIllustrate`` flag. It is the one plancode control for RERUN (Robert Haessly,
10/8/2026): a user may illustrate a policy only when its base plancode is in the
table with ``CanIllustrate`` on, unless the user's role carries the ``RERUNANYPLAN``
permission (ADMIN through AllApps; SUPPORT by grant; any role an administrator
checks it for in Administrator). Source (developer) runs hold every permission;
``SUITEVIEW_ILLUSTRATION_BUSINESS_MODE=1`` takes it away so developers can test
the business scope.

The table is read once and cached; ``clear_control_cache`` (called on every policy
Get) picks up an administrator's edits. A table that cannot be read refuses the
plancode for users without the permission (fail closed).
"""
from __future__ import annotations

import logging
import os
import threading
from typing import Optional

from suiteview.core.access_control import can_access_app
from suiteview.illustration.core.business_mode import BUSINESS_MODE_ENV
from suiteview.illustration.models.rerun_plancode_tables import (
    CONTROL_TABLE,
    ControlRow,
    read_control_rows,
)

logger = logging.getLogger(__name__)

ILLUSTRATE_ANY_PLANCODE = "RERUNANYPLAN"

_lock = threading.Lock()
_rows: Optional[dict[str, ControlRow]] = None


def can_illustrate_any_plancode() -> bool:
    """True when the current user may ignore the control table."""
    if os.environ.get(BUSINESS_MODE_ENV) == "1":
        return False
    try:
        return can_access_app(ILLUSTRATE_ANY_PLANCODE)
    except Exception:
        logger.exception("Could not verify the %s permission; applying the control table",
                         ILLUSTRATE_ANY_PLANCODE)
        return False


def clear_control_cache() -> None:
    global _rows
    with _lock:
        _rows = None


def control_rows() -> dict[str, ControlRow]:
    """Every control row by plancode (cached until ``clear_control_cache``)."""
    global _rows
    with _lock:
        if _rows is None:
            _rows = read_control_rows()
        return _rows


def control_row(plancode: str) -> Optional[ControlRow]:
    return control_rows().get(str(plancode or "").strip().upper())


def plancode_refusal(plancode: str) -> Optional[str]:
    """Why the control table does not allow *plancode*, or None when it does."""
    code = str(plancode or "").strip().upper()
    try:
        row = control_row(code)
    except Exception as exc:
        logger.exception("Could not read %s", CONTROL_TABLE)
        return (f"RERUN could not read its plancode control table ({CONTROL_TABLE}), so "
                f"plancode {code or '(blank)'} can't be illustrated right now: {exc}")
    if row is None:
        return (f"Plancode {code or '(blank)'} is not set up for illustration (it is not in "
                "RERUN's plancode control table).")
    if not row.can_illustrate:
        return (f"Plancode {code} ({row.product_type}) is not enabled for in-force "
                "illustration in this release.")
    return None


def illustration_refusal(plancode: str, *, any_plancode: Optional[bool] = None) -> Optional[str]:
    """The refusal for the current user: none with the ``RERUNANYPLAN`` permission."""
    if any_plancode is None:
        any_plancode = can_illustrate_any_plancode()
    if any_plancode:
        return None
    return plancode_refusal(plancode)


__all__ = [
    "ILLUSTRATE_ANY_PLANCODE", "can_illustrate_any_plancode", "clear_control_cache",
    "control_row", "control_rows", "illustration_refusal", "plancode_refusal",
]
