"""Drive the real SuiteViewTaskbar through hide-to-tray / show-from-tray.

Prints the Windows desktop work area (and the bottom edge of every maximized
window) after each step so we can see whether the AppBar reservation is
restored when the mini-bar is brought back from the system tray.

Scenarios covered:
  1. launch                        -> space reserved
  2. hide to tray                  -> space released
  3. screen refresh while hidden   -> space stays released (no phantom bar)
  4. show from tray                -> space reserved again
  5. redundant re-registration     -> space stays reserved (stale-registration guard)

Usage:
    venv\\Scripts\\python.exe tools/app/test_taskbar_tray_cycle.py
"""

import ctypes
import ctypes.wintypes as wt
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from PyQt6.QtCore import QTimer
from PyQt6.QtWidgets import QApplication

STEP_DELAY_MS = 1500


class RECT(ctypes.Structure):
    _fields_ = [('left', wt.LONG), ('top', wt.LONG),
                ('right', wt.LONG), ('bottom', wt.LONG)]


def work_area():
    r = RECT()
    ctypes.windll.user32.SystemParametersInfoW(0x0030, 0, ctypes.byref(r), 0)
    return (r.left, r.top, r.right, r.bottom)


def maximized_bottoms():
    """Bottom edge of every visible maximized top-level window."""
    user32 = ctypes.windll.user32
    found = []

    WNDENUMPROC = ctypes.WINFUNCTYPE(ctypes.c_bool, wt.HWND, wt.LPARAM)

    def cb(hwnd, _lparam):
        if user32.IsWindowVisible(hwnd) and user32.IsZoomed(hwnd):
            r = RECT()
            user32.GetWindowRect(hwnd, ctypes.byref(r))
            found.append(r.bottom)
        return True

    user32.EnumWindows(WNDENUMPROC(cb), 0)
    return sorted(set(found))


def main():
    from suiteview.taskbar_launcher.suiteview_taskbar import SuiteViewTaskbar

    app = QApplication(sys.argv)
    bar = SuiteViewTaskbar()
    bar.show()

    state = {"undocked_bottom": None}
    steps = []

    def snap(label, expect_reserved):
        wa = work_area()
        steps.append({
            "step": label,
            "work_area": wa,
            "expect_reserved": expect_reserved,
            "reserved": wa[3] < state["undocked_bottom"],
            "visible": bar.isVisible(),
            "compact": bar._is_compact_mode,
            "appbar_registered": bar._appbar_registered,
            "geometry": (bar.x(), bar.y(), bar.width(), bar.height()),
            "maximized_window_bottoms": maximized_bottoms(),
        })

    # Each entry: (action, label_recorded_before_action, expected_reserved)
    def baseline():
        # Measure the un-docked work area so "reserved" is unambiguous.
        bar._unregister_appbar(force=True)

    def redock():
        state["undocked_bottom"] = work_area()[3]
        bar._register_appbar(bar.height() or 42)

    plan = [
        (baseline, None, None),
        (redock, None, None),
        (bar._hide_to_tray, "after_launch", True),
        (bar._refresh_bar_position, "after_hide_to_tray", False),
        (bar._show_from_tray, "after_screen_refresh_while_hidden", False),
        (lambda: bar._register_appbar(bar.height() or 42),
         "after_show_from_tray", True),
        (None, "after_redundant_register", True),
    ]

    def run(index):
        action, label, expect = plan[index]
        if label is not None:
            snap(label, expect)
        if action is not None:
            action()
        if index + 1 < len(plan):
            QTimer.singleShot(STEP_DELAY_MS, lambda: run(index + 1))
        else:
            finish()

    def finish():
        bar._unregister_appbar(force=True)
        failures = [s["step"] for s in steps
                    if s["reserved"] != s["expect_reserved"]]
        print(json.dumps({"steps": steps, "failures": failures,
                          "all_ok": not failures}, indent=2))
        app.quit()

    QTimer.singleShot(2500, lambda: run(0))
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
