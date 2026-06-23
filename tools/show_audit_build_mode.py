"""Screenshot the Audit window header and verify the Build Mode menu.

Confirms DataForge moved into the Build Mode dropdown (no separate header
button). Prints the menu's action labels and captures the window.

Usage:
    venv\\Scripts\\python.exe tools/show_audit_build_mode.py [output_png]
"""
import os
import sys
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from PyQt6.QtCore import QTimer  # noqa: E402
from PyQt6.QtWidgets import QApplication  # noqa: E402


def main():
    output = sys.argv[1] if len(sys.argv) > 1 else str(
        Path.home() / ".suiteview" / "audit_build_mode.png")

    app = QApplication(sys.argv)
    from suiteview.audit.main import create_audit_window

    win = create_audit_window()
    win.resize(1215, 720)
    win.show()

    def go():
        menu = win.btn_build_mode.menu()
        labels = [a.text() for a in menu.actions()] if menu else []
        print("Build Mode menu:", labels)
        print("btn_dataforge visible:", win.btn_dataforge.isVisible())
        QTimer.singleShot(300, capture)

    def capture():
        ok = win.grab().save(output, "PNG")
        print(f"{'Saved' if ok else 'FAILED to save'} {output}")
        app.quit()

    QTimer.singleShot(500, go)
    QTimer.singleShot(8000, app.quit)
    app.exec()


if __name__ == "__main__":
    main()
