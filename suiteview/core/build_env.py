"""Build-environment detection — dev (running from source) vs distribution.

Single source of truth wrapping the exact mechanism the taskbar already uses
(``DEV_MODE = not getattr(sys, 'frozen', False)``): PyInstaller sets
``sys.frozen`` on the packaged EXE shipped to the business area, and never on a
source checkout. Wrapped as a function so gating logic can call one name and
tests can monkeypatch it.
"""
from __future__ import annotations

import os
import sys


def is_distribution_build() -> bool:
    """True in the packaged (PyInstaller) EXE, False when running from source."""
    return bool(getattr(sys, "frozen", False))


def is_light_build() -> bool:
    """True in the SuiteViewLight edition — the read-only build shipped to the
    business area.

    Light is a deliberately trimmed, *read-only* edition: it omits the LLM Agent
    and Rate Manager, and must never modify the shared UL_Rates SQL Server
    database (rate tables, the audit unique-value registry, etc.).

    Detected from the packaged EXE name (``SuiteViewLight.exe``), or forced via
    ``SUITEVIEW_LIGHT=1`` so the Light behaviour can be exercised from source
    (manual QA and tests) without repackaging.
    """
    if os.environ.get("SUITEVIEW_LIGHT") == "1":
        return True
    if not is_distribution_build():
        return False
    exe = os.path.basename(sys.executable or "")
    return "SuiteViewLight" in exe


def is_data_read_only() -> bool:
    """True when the current edition must not write to the shared database.

    Gate every write against the shared UL_Rates SQL Server on this — registered
    unique values, ABR rate tables, and any future rate/registry writes. The
    Light edition is read-only; the full edition is writable.
    """
    return is_light_build()


class ReadOnlyDataError(RuntimeError):
    """Raised when a write to the shared database is attempted while the edition
    is read-only (SuiteViewLight). Acts as the last-line safety net beneath the
    UI gating so a stray call site can't silently mutate shared data."""


def guard_data_writable(action: str = "modify data") -> None:
    """Raise :class:`ReadOnlyDataError` when the edition is read-only.

    Call at the top of any function that writes to the shared UL_Rates database
    so the write is blocked even if a UI control was missed. ``action`` is folded
    into the message (e.g. ``"register unique values"``)."""
    if is_data_read_only():
        raise ReadOnlyDataError(
            f"SuiteView Light is read-only — cannot {action}."
        )
