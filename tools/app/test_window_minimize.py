"""Regression test for FramelessWindowBase minimize / restore.

Covers the failure users reported — clicking minimize on a maximized window
sometimes leaves it filling the screen — plus the window-state drift that
causes it.  For each scenario it checks that Windows really iconified the HWND
(``IsIconic``), that no pixel of the window is still painted on screen, and
that restoring brings the window back the way it was.

Usage:
    venv\\Scripts\\python.exe tools/app/test_window_minimize.py
"""

from __future__ import annotations

import ctypes
import json
import sys
from ctypes import wintypes
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from PyQt6.QtCore import Qt, QTimer, QEventLoop  # noqa: E402
from PyQt6.QtWidgets import QApplication, QLabel, QWidget  # noqa: E402
from PyQt6.QtTest import QTest  # noqa: E402

from suiteview.ui.widgets.frameless_window import FramelessWindowBase  # noqa: E402

user32 = ctypes.windll.user32
user32.IsIconic.restype = wintypes.BOOL
user32.IsIconic.argtypes = [wintypes.HWND]
user32.IsZoomed.restype = wintypes.BOOL
user32.IsZoomed.argtypes = [wintypes.HWND]
user32.GetWindowRect.restype = wintypes.BOOL
user32.GetWindowRect.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.RECT)]
user32.ShowWindow.restype = wintypes.BOOL
user32.ShowWindow.argtypes = [wintypes.HWND, ctypes.c_int]

_SW_RESTORE = 9
_MARKER = "#FF00FF"
_MARKER_RGB = (255, 0, 255)


class _Probe(FramelessWindowBase):
    def build_content(self) -> QWidget:
        body = QLabel("minimize probe")
        body.setAutoFillBackground(True)
        body.setStyleSheet(f"background-color: {_MARKER};")
        return body


def _pump(ms: int) -> None:
    loop = QEventLoop()
    QTimer.singleShot(ms, loop.quit)
    loop.exec()


def _marker_pixels(app: QApplication) -> int:
    """Sampled screen pixels still showing the probe's marker colour.  Non-zero
    after a minimize means the window is still visibly on screen."""
    img = app.primaryScreen().grabWindow(0).toImage()
    hits = 0
    for y in range(0, img.height(), 37):
        for x in range(0, img.width(), 37):
            c = img.pixelColor(x, y)
            if (c.red(), c.green(), c.blue()) == _MARKER_RGB:
                hits += 1
    return hits


def _state(win: _Probe, app: QApplication) -> dict:
    hwnd = int(win.winId())
    rect = wintypes.RECT()
    user32.GetWindowRect(hwnd, ctypes.byref(rect))
    return {
        "iconic": bool(user32.IsIconic(hwnd)),
        "zoomed": bool(user32.IsZoomed(hwnd)),
        "rect": [rect.left, rect.top, rect.right, rect.bottom],
        "qt_min": win.isMinimized(),
        "qt_max": win.isMaximized(),
        "flag_max": win._is_maximized,
        "marker_px": _marker_pixels(app),
    }


def _click_min(win: _Probe) -> None:
    """Click the header's minimize button the way a user would."""
    QTest.mouseClick(win.min_btn, Qt.MouseButton.LeftButton)


def _check_minimized(st: dict):
    if not st["iconic"]:
        return "window not iconified"
    if st["marker_px"]:
        return "iconified but window content still painted on screen"
    return None


def main() -> int:
    app = QApplication(sys.argv)
    results: dict = {}
    failures = []

    def record(name, st, problem=None):
        st["FAIL"] = problem
        results[name] = st
        if problem:
            failures.append(f"{name}: {problem}")

    win = _Probe(title="Minimize Probe", default_size=(900, 600))
    win.show()
    _pump(600)

    # 1. Minimize from the normal state.
    _click_min(win)
    _pump(800)
    st = _state(win, app)
    record("normal_minimize", st, _check_minimized(st))
    win.restore_window()
    _pump(600)

    # 2. Minimize from a maximized window (the reported failure).
    win._toggle_maximize()
    _pump(700)
    results["maximized"] = _state(win, app)
    _click_min(win)
    _pump(900)
    st = _state(win, app)
    record("maximized_minimize", st, _check_minimized(st))

    # 3. Restoring must bring the window back maximized, with the header's
    #    maximize button still offering "Restore".
    win.restore_window()
    _pump(800)
    st = _state(win, app)
    problem = None
    if st["iconic"]:
        problem = "still iconified after restore"
    elif not st["qt_max"]:
        problem = "restore dropped the maximized state"
    elif not st["flag_max"]:
        problem = "_is_maximized flag out of sync after restore"
    record("restore_keeps_maximized", st, problem)

    # 4. Window state changed behind Qt's back (native restore, Aero snap).
    #    Minimize must still work — this is what made the button silently do
    #    nothing before.
    _click_min(win)
    _pump(800)
    hwnd = int(win.winId())
    user32.ShowWindow(hwnd, _SW_RESTORE)
    _pump(800)
    _click_min(win)
    _pump(900)
    st = _state(win, app)
    record("minimize_after_native_restore", st, _check_minimized(st))
    win.restore_window()
    _pump(600)

    # 5. Hide/show cycle (SuiteView windows hide instead of closing).
    _click_min(win)
    _pump(700)
    win.hide()
    _pump(400)
    win.restore_window()
    _pump(800)
    st = _state(win, app)
    record("restore_after_hide", st,
           "still iconified after hide/show restore" if st["iconic"] else None)
    _click_min(win)
    _pump(900)
    st = _state(win, app)
    record("minimize_after_hide_cycle", st, _check_minimized(st))
    win.restore_window()
    _pump(600)

    # 6. An OS-driven maximize must update our own flags, so the header's
    #    restore button is not left doing nothing.
    win.showNormal()
    _pump(400)
    win.setWindowState(Qt.WindowState.WindowMaximized)
    _pump(700)
    st = _state(win, app)
    problem = None
    if not st["flag_max"]:
        problem = "_is_maximized not synced from an OS-driven maximize"
    elif win.max_btn.toolTip() != "Restore":
        problem = "maximize button glyph not synced"
    record("os_maximize_syncs_flags", st, problem)
    _click_min(win)
    _pump(900)
    st = _state(win, app)
    record("minimize_after_os_maximize", st, _check_minimized(st))

    win.restore_window()
    _pump(400)
    win.close()

    # 7. The same guarantee for a plain frameless window that only mixes in
    #    NativeMinimizeMixin (Screen Shot Manager, Email Attachments, FileNav).
    from suiteview.ui.widgets.window_state import NativeMinimizeMixin

    class _PlainProbe(NativeMinimizeMixin, QWidget):
        pass

    plain = _PlainProbe()
    plain.setWindowFlags(Qt.WindowType.FramelessWindowHint
                         | Qt.WindowType.WindowMinMaxButtonsHint)
    plain.resize(800, 500)
    lbl = QLabel(plain)
    lbl.setGeometry(0, 0, 800, 500)
    lbl.setAutoFillBackground(True)
    lbl.setStyleSheet(f"background-color: {_MARKER};")
    plain.show()
    _pump(600)
    plain.showMaximized()
    _pump(700)
    plain.showMinimized()
    _pump(900)
    p_hwnd = int(plain.winId())
    st = {
        "iconic": bool(user32.IsIconic(p_hwnd)),
        "zoomed": bool(user32.IsZoomed(p_hwnd)),
        "rect": [],
        "qt_min": plain.isMinimized(),
        "qt_max": plain.isMaximized(),
        "flag_max": None,
        "marker_px": _marker_pixels(app),
    }
    record("mixin_only_window_minimize", st, _check_minimized(st))
    plain.restore_window()
    _pump(500)
    plain.close()

    results["failures"] = failures
    results["all_ok"] = not failures
    print(json.dumps(results, indent=2))
    return 0 if not failures else 1


if __name__ == "__main__":
    raise SystemExit(main())
