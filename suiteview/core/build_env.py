"""Build-environment detection — dev (running from source) vs distribution.

Single source of truth wrapping the exact mechanism the taskbar already uses
(``DEV_MODE = not getattr(sys, 'frozen', False)``): PyInstaller sets
``sys.frozen`` on the packaged EXE shipped to the business area, and never on a
source checkout. Wrapped as a function so gating logic can call one name and
tests can monkeypatch it.
"""
from __future__ import annotations

import sys


def is_distribution_build() -> bool:
    """True in the packaged (PyInstaller) EXE, False when running from source."""
    return bool(getattr(sys, "frozen", False))
