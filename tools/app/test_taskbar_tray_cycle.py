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
  6. native Windows restore        -> Qt state and reservation restored
  7. shortcut (second process)     -> same restore path, including repeated clicks
  8. floating / full window       -> restored without an AppBar reservation

Usage:
    venv\\Scripts\\python.exe tools/app/test_taskbar_tray_cycle.py
"""

import argparse
import ctypes
import ctypes.wintypes as wt
import json
import os
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from PyQt6.QtCore import QTimer
from PyQt6.QtWidgets import QApplication, QWidget
from suiteview.taskbar_launcher.single_instance import acquire_or_activate

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
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--activate", nargs=2, metavar=("MUTEX", "TITLE"))
    args = parser.parse_args()
    if args.activate:
        mutex, title = args.activate
        return 1 if acquire_or_activate(mutex, (title,)) else 0

    from suiteview.taskbar_launcher.taskbar_window import SuiteViewTaskbar

    mutex = f"SuiteView_Restore_Test_{os.getpid()}"
    title = f"SuiteView Restore Test {os.getpid()}"
    assert acquire_or_activate(mutex, (title,))
    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)
    probe = QWidget()
    probe.setWindowTitle("SuiteView work-area regression probe")
    probe.showMaximized()
    bar = SuiteViewTaskbar()
    bar.setWindowTitle(title)
    bar.show()

    state = {"undocked_bottom": None}
    steps = []

    def snap(label, expect_reserved):
        wa = work_area()
        user32 = ctypes.windll.user32
        user32.IsWindowVisible.argtypes = [wt.HWND]
        user32.IsWindowVisible.restype = wt.BOOL
        user32.GetWindowRect.argtypes = [wt.HWND, ctypes.POINTER(RECT)]
        user32.GetWindowRect.restype = wt.BOOL
        rect = RECT()
        assert user32.GetWindowRect(int(bar.winId()), ctypes.byref(rect))
        probe_rect = RECT()
        assert user32.GetWindowRect(int(probe.winId()), ctypes.byref(probe_rect))
        expected_bottom = state["undocked_bottom"]
        if expect_reserved:
            expected_bottom -= round(bar.height() * bar.devicePixelRatioF())
        steps.append({
            "step": label,
            "work_area": wa,
            "expect_reserved": expect_reserved,
            "reserved": wa[3] < state["undocked_bottom"],
            "visible": bar.isVisible(),
            "native_visible": bool(user32.IsWindowVisible(int(bar.winId()))),
            "hidden_to_tray": bar._hidden_to_tray,
            "expected_work_bottom": expected_bottom,
            "bar_top": rect.top,
            "maximized_probe_bottom": probe_rect.bottom,
            "expected_probe_bottom": (
                state["undocked_probe_bottom"]
                - (state["undocked_bottom"] - expected_bottom)
            ),
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
        user32 = ctypes.windll.user32
        user32.GetWindowRect.argtypes = [wt.HWND, ctypes.POINTER(RECT)]
        user32.GetWindowRect.restype = wt.BOOL
        rect = RECT()
        assert user32.GetWindowRect(int(probe.winId()), ctypes.byref(rect))
        state["undocked_probe_bottom"] = rect.bottom
        bar._register_appbar(bar.height() or 42)

    def native_restore():
        # Reproduce the pinned shortcut's old single-instance activation path.
        user32 = ctypes.windll.user32
        user32.ShowWindow.argtypes = [wt.HWND, ctypes.c_int]
        user32.ShowWindow.restype = wt.BOOL
        user32.ShowWindow(int(bar.winId()), 9)

    def shortcut_restore():
        subprocess.run(
            [sys.executable, str(Path(__file__).resolve()), "--activate", mutex, title],
            check=True, capture_output=True, text=True, timeout=20,
        )

    def float_bar():
        bar._enter_floating_mode()

    def expand_bar():
        bar._exit_floating_mode()
        bar._exit_compact_mode()

    plan = [
        (baseline, None, None),
        (redock, None, None),
        (bar._hide_to_tray, "after_launch", True),
        (bar._refresh_bar_position, "after_hide_to_tray", False),
        (bar._show_from_tray, "after_screen_refresh_while_hidden", False),
        (lambda: bar._register_appbar(bar.height() or 42),
         "after_show_from_tray", True),
        (bar._hide_to_tray, "after_redundant_register", True),
        (native_restore, "before_native_restore", False),
        (bar._refresh_bar_position, "after_native_restore", True),
        (bar._show_from_tray, "after_native_restore_screen_refresh", True),
        (bar._hide_to_tray, "after_tray_restore_following_native_restore", True),
        (shortcut_restore, "before_shortcut_restore", False),
        (shortcut_restore, "after_shortcut_restore", True),
        (float_bar, "after_repeated_shortcut_restore", True),
        (bar._hide_to_tray, "after_float", False),
        (shortcut_restore, "before_floating_shortcut_restore", False),
        (expand_bar, "after_floating_shortcut_restore", False),
        (bar._hide_to_tray, "after_expand", False),
        (shortcut_restore, "before_full_shortcut_restore", False),
        (None, "after_full_shortcut_restore", False),
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
        bar.tray_icon.hide()
        bar.hide()
        probe.close()
        failures = [
            s["step"] for s in steps
            if (s["work_area"][3] != s["expected_work_bottom"]
                or s["visible"] != s["native_visible"]
                or s["visible"] == s["hidden_to_tray"]
                or s["maximized_probe_bottom"] != s["expected_probe_bottom"]
                or s["appbar_registered"] != s["expect_reserved"]
                or (s["expect_reserved"] and
                    (not s["visible"] or s["bar_top"] != s["work_area"][3])))
        ]
        report = json.dumps({"steps": steps, "failures": failures,
                             "all_ok": not failures}, indent=2)
        print(report)
        if args.output:
            args.output.write_text(report, encoding="utf-8")
        app.exit(1 if failures else 0)

    QTimer.singleShot(2500, lambda: run(0))
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
