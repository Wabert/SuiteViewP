"""Native regression check for FramelessWindowBase resizing and dragging (Windows).

Covers what RERUN users hit on an undocked laptop (10/23/2026):

* a window whose content has height-for-width (word-wrapped labels) must shrink to
  what the user drags - Qt's default layout constraint forced it back up to the
  content's height, growing it past a laptop's work area;
* a first-shown window larger than its screen's work area is fitted inside it;
* resizing from the top edge goes through Windows (``WM_NCHITTEST``) and keeps the
  bottom edge put;
* dragging the header moves the window natively (``startSystemMove``) with the
  cursor, and a header double-click still maximizes / restores.

It drives the real mouse (from a worker thread, since Windows runs its own
move/size loop), so leave the mouse alone for the few seconds it runs.

Usage:
    venv\\Scripts\\python.exe tools/app/verify_frameless_drag_resize.py
"""

from __future__ import annotations

import ctypes
import json
import sys
import threading
import time
from ctypes import wintypes
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from PyQt6.QtCore import QEventLoop, QTimer  # noqa: E402
from PyQt6.QtWidgets import QApplication, QLabel, QVBoxLayout, QWidget  # noqa: E402

from suiteview.ui.widgets.frameless_window import FramelessWindowBase  # noqa: E402

user32 = ctypes.windll.user32
user32.GetWindowRect.restype = wintypes.BOOL
user32.GetWindowRect.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.RECT)]
user32.SetCursorPos.argtypes = [ctypes.c_int, ctypes.c_int]
user32.GetCursorPos.argtypes = [ctypes.POINTER(wintypes.POINT)]
user32.mouse_event.argtypes = [wintypes.DWORD, wintypes.DWORD, wintypes.DWORD, wintypes.DWORD, ctypes.c_size_t]
user32.WindowFromPoint.restype = wintypes.HWND
user32.WindowFromPoint.argtypes = [wintypes.POINT]
user32.GetAncestor.restype = wintypes.HWND
user32.GetAncestor.argtypes = [wintypes.HWND, wintypes.UINT]

_LEFTDOWN, _LEFTUP = 0x0002, 0x0004
_GA_ROOT = 2


class _NotInFront(RuntimeError):
    """The probe window is not the window under the cursor: injecting input would hit another app."""


def _owns(hwnd: int, x: int, y: int) -> bool:
    under = user32.WindowFromPoint(wintypes.POINT(int(x), int(y)))
    return bool(under) and int(user32.GetAncestor(under, _GA_ROOT) or 0) == hwnd


class _Probe(FramelessWindowBase):
    """Content like RERUN's: word-wrapped text (height-for-width) with a tall minimum."""

    def build_content(self) -> QWidget:
        body = QWidget()
        layout = QVBoxLayout(body)
        for _ in range(12):
            label = QLabel("Word-wrapped content gives the window's layout a height-for-width. " * 3)
            label.setWordWrap(True)
            label.setMinimumHeight(60)
            layout.addWidget(label)
        return body


def _pump(ms: int) -> None:
    loop = QEventLoop()
    QTimer.singleShot(ms, loop.quit)
    loop.exec()


def _rect(hwnd: int):
    r = wintypes.RECT()
    user32.GetWindowRect(hwnd, ctypes.byref(r))
    return r.left, r.top, r.right, r.bottom


def _gesture(steps, done: threading.Event) -> None:
    """Run (kind, x, y) mouse steps from a worker thread so the GUI thread keeps pumping."""
    try:
        for kind, x, y in steps:
            user32.SetCursorPos(int(x), int(y))
            time.sleep(0.03)
            if kind == "down":
                user32.mouse_event(_LEFTDOWN, 0, 0, 0, 0)
            elif kind == "up":
                user32.mouse_event(_LEFTUP, 0, 0, 0, 0)
            time.sleep(0.03)
    finally:
        user32.mouse_event(_LEFTUP, 0, 0, 0, 0)
        done.set()


def _run(hwnd: int, steps, settle_ms: int = 400) -> None:
    _kind, x, y = steps[0]
    if not _owns(hwnd, x, y):
        raise _NotInFront(f"the probe window is not under ({x}, {y})")
    done = threading.Event()
    threading.Thread(target=_gesture, args=(steps, done), daemon=True).start()
    while not done.is_set():
        _pump(20)
    _pump(settle_ms)


def _drag(x0, y0, dx, dy, count=12):
    steps = [("move", x0, y0), ("down", x0, y0)]
    steps += [("move", x0 + dx * i / count, y0 + dy * i / count) for i in range(1, count + 1)]
    steps.append(("up", x0 + dx, y0 + dy))
    return steps


def main() -> int:
    app = QApplication.instance() or QApplication(sys.argv)
    results = {}
    saved = wintypes.POINT()
    user32.GetCursorPos(ctypes.byref(saved))
    window = _Probe(title="Frameless drag / resize probe", default_size=(900, 700), min_size=(400, 300))
    try:
        # 1. Fitted into the work area on first show.
        area = app.primaryScreen().availableGeometry()
        window.resize(area.width() + 200, area.height() + 200)
        window.move(area.left() + 40, area.top() + 40)
        window.show()
        _pump(400)
        geo = window.geometry()
        results["fits_work_area"] = area.contains(geo)

        # 2. Shrinks below the height-for-width content height.
        content_min = window.layout().totalMinimumSize().height()
        window.setGeometry(area.left() + 200, area.top() + 150, 800, 450)
        _pump(300)
        results["content_min_height"] = content_min
        results["shrinks_below_content"] = (window.width(), window.height()) == (800, 450)

        hwnd = int(window.winId())
        dpr = window.devicePixelRatioF()
        window.raise_()
        window.activateWindow()
        _pump(300)

        # 3. Native resize from the top edge: bottom stays, height follows the drag.
        left, top, right, bottom = _rect(hwnd)
        _run(hwnd, _drag((left + right) // 2, top + 2, 0, round(80 * dpr)))
        l2, t2, r2, b2 = _rect(hwnd)
        results["top_resize"] = {"bottom_kept": abs(b2 - bottom) <= 1,
                                 "height_change": (b2 - t2) - (bottom - top)}
        results["top_resize_ok"] = results["top_resize"]["bottom_kept"] and \
            abs(results["top_resize"]["height_change"] + round(80 * dpr)) <= 3

        # 4. Native header drag: the window follows the cursor exactly.
        left, top, right, bottom = _rect(hwnd)
        grab = (left + 60, top + round(20 * dpr))
        _run(hwnd, _drag(grab[0], grab[1], round(150 * dpr), round(90 * dpr)))
        l3, t3, _r3, _b3 = _rect(hwnd)
        results["drag_delta"] = [l3 - left, t3 - top]
        results["drag_ok"] = abs((l3 - left) - round(150 * dpr)) <= 2 and abs((t3 - top) - round(90 * dpr)) <= 2

        # 5. Header double-click still maximizes, then restores.
        left, top, _right, _bottom = _rect(hwnd)
        x, y = left + 60, top + round(20 * dpr)
        click = [("move", x, y), ("down", x, y), ("up", x, y)]
        _run(hwnd, click + click, settle_ms=600)
        # Qt maximizes a frameless window by geometry, so ask Qt rather than IsZoomed.
        results["double_click_maximizes"] = window.isMaximized()
        left, top, _right, _bottom = _rect(hwnd)
        x, y = left + 60, top + round(20 * dpr)
        click = [("move", x, y), ("down", x, y), ("up", x, y)]
        _run(hwnd, click + click, settle_ms=600)
        results["double_click_restores"] = not window.isMaximized()
    except _NotInFront as exc:
        results["error"] = f"input checks not run: {exc}"
    finally:
        user32.mouse_event(_LEFTUP, 0, 0, 0, 0)
        user32.SetCursorPos(saved.x, saved.y)
        window.close()
    results["all_ok"] = all(results.get(k) for k in (
        "fits_work_area", "shrinks_below_content", "top_resize_ok", "drag_ok",
        "double_click_maximizes", "double_click_restores"))
    print(json.dumps(results, indent=1))
    return 0 if results["all_ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
