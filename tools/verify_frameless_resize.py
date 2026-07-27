"""Verify the FramelessWindowBase native-resize fix.

Launches the PolView window (no DB2 needed — no initial policy), confirms the
native DWM sizing frame installs, exercises a couple of programmatic resizes,
and grabs the OS-composited window image so the chrome/border can be inspected.

Usage:
    venv\\Scripts\\python.exe tools/verify_frameless_resize.py

Prints a JSON summary and saves a screenshot to
~/.suiteview/frameless_resize_check.png. Exits on its own.
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, ".")

from PyQt6.QtWidgets import QApplication  # noqa: E402
from PyQt6.QtCore import QTimer  # noqa: E402


def main():
    app = QApplication(sys.argv)

    from suiteview.polview.ui.main_window import GetPolicyWindow

    win = GetPolicyWindow(enable_policy_list=False)
    win.show()

    out = str(Path.home() / ".suiteview" / "frameless_resize_check.png")
    result = {}

    steps = []

    def record(tag):
        s = win.size()
        steps.append({"tag": tag, "w": s.width(), "h": s.height()})

    def step1():
        record("after_show")
        win.resize(1100, 720)
        QTimer.singleShot(150, step2)

    def step2():
        record("after_resize_1100x720")
        win.resize(1350, 880)
        QTimer.singleShot(150, step3)

    def step3():
        record("after_resize_1350x880")
        # Grab the OS-composited window (shows real client area + border)
        screen = app.primaryScreen()
        pm = screen.grabWindow(int(win.winId()))
        pm.save(out, "PNG")
        result["native_resize"] = getattr(win, "_native_resize", None)
        result["native_installed"] = getattr(win, "_native_installed", None)
        result["is_maximized_qt"] = win.isMaximized()
        result["steps"] = steps
        result["screenshot"] = out
        print(json.dumps(result, indent=2), flush=True)
        app.quit()

    QTimer.singleShot(300, step1)
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
