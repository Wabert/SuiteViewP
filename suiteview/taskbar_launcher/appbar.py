"""Windows AppBar docking for the SuiteView mini-bar.

The compact mini-bar reserves desktop space by registering itself as a shell
*AppBar* (`SHAppBarMessage`) — the same mechanism the Windows taskbar uses.
This module owns the whole Win32 dance so the taskbar widget never has to
re-declare the structures, and so registration is **idempotent and verified**:

* :func:`register_bottom` always issues an ``ABM_REMOVE`` first, so a stale
  shell-side registration for our HWND can never make ``ABM_NEW`` fail and
  leave the desktop work area unreserved.
* :func:`space_reserved` reads the monitor work area back so callers can
  confirm the shell actually honoured the reservation and retry if it didn't.

All functions are safe no-ops off Windows.
"""

from __future__ import annotations

import ctypes
import ctypes.wintypes as wt
import logging
import sys
from typing import Optional, Tuple

logger = logging.getLogger(__name__)

IS_WINDOWS = sys.platform == "win32"

ABM_NEW = 0x00
ABM_REMOVE = 0x01
ABM_QUERYPOS = 0x02
ABM_SETPOS = 0x03
ABE_BOTTOM = 3

SWP_NOZORDER = 0x0004
SWP_NOACTIVATE = 0x0010
SWP_SHOWWINDOW = 0x0040

MONITOR_DEFAULTTONEAREST = 2

Rect = Tuple[int, int, int, int]


class RECT(ctypes.Structure):
    _fields_ = [('left', wt.LONG), ('top', wt.LONG),
                ('right', wt.LONG), ('bottom', wt.LONG)]


class APPBARDATA(ctypes.Structure):
    _fields_ = [
        ('cbSize', wt.DWORD),
        ('hWnd', wt.HWND),
        ('uCallbackMessage', wt.UINT),
        ('uEdge', wt.UINT),
        ('rc', RECT),
        ('lParam', ctypes.c_void_p),
    ]


class MONITORINFO(ctypes.Structure):
    _fields_ = [('cbSize', wt.DWORD), ('rcMonitor', RECT),
                ('rcWork', RECT), ('dwFlags', wt.DWORD)]


def _apis():
    user32 = ctypes.windll.user32
    shell32 = ctypes.windll.shell32
    shell32.SHAppBarMessage.restype = wt.ULONG
    user32.RegisterWindowMessageW.restype = wt.UINT
    return user32, shell32


def monitor_rects(hwnd: int) -> Optional[Tuple[Rect, Rect]]:
    """Return ``(monitor_rect, work_rect)`` in physical pixels for *hwnd*."""
    if not IS_WINDOWS:
        return None
    user32, _ = _apis()
    hmon = user32.MonitorFromWindow(hwnd, MONITOR_DEFAULTTONEAREST)
    mi = MONITORINFO()
    mi.cbSize = ctypes.sizeof(MONITORINFO)
    if not user32.GetMonitorInfoW(hmon, ctypes.byref(mi)):
        return None
    m, w = mi.rcMonitor, mi.rcWork
    return ((m.left, m.top, m.right, m.bottom),
            (w.left, w.top, w.right, w.bottom))


def unregister(hwnd: int) -> bool:
    """Drop any AppBar registration held for *hwnd*.

    Safe to call when nothing is registered — the shell simply reports failure,
    which we swallow. Always call this before re-registering.
    """
    if not IS_WINDOWS or not hwnd:
        return False
    try:
        _, shell32 = _apis()
        abd = APPBARDATA()
        abd.cbSize = ctypes.sizeof(APPBARDATA)
        abd.hWnd = hwnd
        return bool(shell32.SHAppBarMessage(ABM_REMOVE, ctypes.byref(abd)))
    except Exception as exc:
        logger.error(f"AppBar ABM_REMOVE failed: {exc}")
        return False


def register_bottom(hwnd: int, bar_h_phys: int,
                    callback_message: str = "SuiteView_AppBar") -> Optional[Rect]:
    """Dock *hwnd* to the bottom edge and reserve *bar_h_phys* physical pixels.

    Returns the approved rectangle (physical pixels), or ``None`` on failure.
    The window is moved into the approved rectangle via ``SetWindowPos``.
    """
    if not IS_WINDOWS or not hwnd:
        return None
    try:
        user32, shell32 = _apis()

        rects = monitor_rects(hwnd)
        if rects is None:
            return None
        (mon_left, _mon_top, mon_right, mon_bottom), _work = rects

        # Clear any registration the shell may still hold for this HWND.
        # Without this an ABM_NEW on an already-known window fails and the
        # work area is silently left unreserved.
        unregister(hwnd)

        abd = APPBARDATA()
        abd.cbSize = ctypes.sizeof(APPBARDATA)
        abd.hWnd = hwnd
        abd.uCallbackMessage = user32.RegisterWindowMessageW(callback_message)
        abd.uEdge = ABE_BOTTOM
        abd.rc.left = mon_left
        abd.rc.top = mon_bottom - bar_h_phys
        abd.rc.right = mon_right
        abd.rc.bottom = mon_bottom

        if not shell32.SHAppBarMessage(ABM_NEW, ctypes.byref(abd)):
            logger.warning("SHAppBarMessage ABM_NEW failed")
            return None

        # Let the shell negotiate the rectangle (e.g. above the taskbar), then
        # restore the height we asked for.
        shell32.SHAppBarMessage(ABM_QUERYPOS, ctypes.byref(abd))
        abd.rc.top = abd.rc.bottom - bar_h_phys
        shell32.SHAppBarMessage(ABM_SETPOS, ctypes.byref(abd))

        user32.SetWindowPos(
            hwnd, 0,
            abd.rc.left, abd.rc.top,
            abd.rc.right - abd.rc.left,
            abd.rc.bottom - abd.rc.top,
            SWP_NOZORDER | SWP_NOACTIVATE | SWP_SHOWWINDOW)

        return (abd.rc.left, abd.rc.top, abd.rc.right, abd.rc.bottom)

    except Exception as exc:
        logger.error(f"AppBar registration failed: {exc}")
        return None


def space_reserved(hwnd: int, bar_top_phys: int, tolerance: int = 2) -> bool:
    """True when the monitor work area actually stops at/above *bar_top_phys*.

    This is the read-back that tells us the shell honoured the reservation —
    ``SHAppBarMessage`` can report success while leaving the work area intact.
    """
    if not IS_WINDOWS or not hwnd:
        return True
    rects = monitor_rects(hwnd)
    if rects is None:
        return True
    _monitor, (_wl, _wt, _wr, work_bottom) = rects
    return work_bottom <= bar_top_phys + tolerance
