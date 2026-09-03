"""Reliable minimize / restore for SuiteView's frameless top-level windows.

``QWidget.showMinimized()`` opens with ``if (isMinimized() && isVisible())
return;`` and afterwards only talks to the OS when Qt believes the window state
actually changed.  SuiteView's frameless windows make that cached state easy to
drift out of step with Windows — they carry a native sizing frame, swallow
``WM_NCCALCSIZE``, get hidden and re-shown instead of closed, and are restored
by raw Win32 calls from the taskbar.  When the two disagree, clicking the
header's minimize button silently does nothing and a maximized window just
keeps filling the screen.

Mixing :class:`NativeMinimizeMixin` into a top-level window routes minimize and
restore through the OS, which has no such cached state, and falls back to Qt if
that ever fails.
"""

from __future__ import annotations

import logging
import sys
from typing import Optional

from PyQt6.QtCore import Qt

logger = logging.getLogger(__name__)

_IS_WINDOWS = sys.platform == "win32"

if _IS_WINDOWS:
    import ctypes
    from ctypes import wintypes

    _WM_SYSCOMMAND = 0x0112
    _SC_MINIMIZE = 0xF020
    _SW_MINIMIZE = 6
    _SW_RESTORE = 9

    def _configure_win32_signatures():
        """Declare argtypes/restype for every Win32 call used here.

        Without this, ctypes assumes 32-bit ints and truncates 64-bit window
        handles, corrupting the stack.
        """
        user32 = ctypes.windll.user32
        LONG_PTR = ctypes.c_longlong if ctypes.sizeof(ctypes.c_void_p) == 8 \
            else ctypes.c_long

        user32.IsIconic.restype = wintypes.BOOL
        user32.IsIconic.argtypes = [wintypes.HWND]
        user32.ShowWindow.restype = wintypes.BOOL
        user32.ShowWindow.argtypes = [wintypes.HWND, ctypes.c_int]
        user32.SendMessageW.restype = LONG_PTR
        user32.SendMessageW.argtypes = [
            wintypes.HWND, wintypes.UINT, ctypes.c_size_t, LONG_PTR,
        ]

    try:
        _configure_win32_signatures()
    except Exception:  # pragma: no cover - defensive
        logger.exception("Failed to configure Win32 signatures; "
                         "native minimize disabled")
        _IS_WINDOWS = False


class NativeMinimizeMixin:
    """Minimize/restore a frameless top-level window through the OS.

    Mix in *before* ``QWidget`` so the overrides win::

        class MyWindow(NativeMinimizeMixin, QWidget):
            ...
    """

    #: Window state captured on minimize so :meth:`restore_window` can bring the
    #: window back maximized/snapped instead of dropping it to normal size.
    _state_before_minimize: Optional[Qt.WindowState] = None

    def window_hwnd(self) -> Optional[int]:
        """Native handle, or None when there is nothing to drive natively."""
        if not (_IS_WINDOWS and self.isVisible()):
            return None
        try:
            return int(self.winId())
        except Exception:  # pragma: no cover - defensive
            return None

    def is_iconic(self) -> bool:
        """Whether Windows considers the window minimized (not what Qt thinks)."""
        hwnd = self.window_hwnd()
        if hwnd is None:
            return self.isMinimized()
        try:
            return bool(ctypes.windll.user32.IsIconic(hwnd))
        except Exception:  # pragma: no cover - defensive
            return self.isMinimized()

    def showMinimized(self):
        """Minimize reliably, even when Qt's cached window state has drifted."""
        hwnd = self.window_hwnd()
        if hwnd is None:
            super().showMinimized()
            return
        if self.is_iconic():
            return

        self._state_before_minimize = (
            self.windowState() & ~Qt.WindowState.WindowMinimized
        )

        user32 = ctypes.windll.user32
        try:
            user32.ShowWindow(hwnd, _SW_MINIMIZE)
            if not self.is_iconic():
                # Exactly what a native title bar's minimize button does.
                user32.SendMessageW(hwnd, _WM_SYSCOMMAND, _SC_MINIMIZE, 0)
        except Exception:  # pragma: no cover - defensive
            logger.debug("native minimize failed", exc_info=True)

        if not self.is_iconic():
            super().showMinimized()

    def restore_window(self):
        """Un-minimize and activate, preserving the pre-minimize state.

        Restoring with ``showNormal()`` throws away a maximized/snapped layout
        and leaves cached flags disagreeing with the real window state, so the
        maximize button then appears to do nothing.  Use this instead.
        """
        target = self._state_before_minimize
        if target is None:
            target = self.windowState() & ~Qt.WindowState.WindowMinimized
        self._state_before_minimize = None

        # Let Qt drive the transition so its cached state stays authoritative —
        # a raw SW_RESTORE first makes Qt clear the maximized bit on the way
        # back.  Only reach for the OS if Qt left the window iconic.
        self.setWindowState(target | Qt.WindowState.WindowActive)
        self.show()

        if self.is_iconic():
            hwnd = self.window_hwnd()
            if hwnd is not None:
                try:
                    ctypes.windll.user32.ShowWindow(hwnd, _SW_RESTORE)
                except Exception:  # pragma: no cover - defensive
                    logger.debug("native restore failed", exc_info=True)
            self.setWindowState(target | Qt.WindowState.WindowActive)

        self.raise_()
        self.activateWindow()
