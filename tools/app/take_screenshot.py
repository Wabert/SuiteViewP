"""
Take a screenshot of the entire desktop using PyQt6.

Usage:
    venv\\Scripts\\python.exe tools/app/take_screenshot.py [output_path]

Default output: ~/.suiteview/diagnostics/screenshot.png

This uses PyQt6's QScreen.grabWindow(0) to capture the full desktop — 
no extra dependencies needed since PyQt6 is already installed.
"""

import sys
from pathlib import Path

from PyQt6.QtWidgets import QApplication
from PyQt6.QtCore import QTimer

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from suiteview.core.profile_paths import diagnostics_dir


def main():
    output = sys.argv[1] if len(sys.argv) > 1 else str(
        diagnostics_dir() / "screenshot.png"
    )

    app = QApplication(sys.argv)

    def capture():
        screen = app.primaryScreen()
        if screen is None:
            print("ERROR: No screen found")
            app.quit()
            return
        pixmap = screen.grabWindow(0)  # 0 = entire desktop
        pixmap.save(output, "PNG")
        print(f"Screenshot saved to {output}")
        app.quit()

    # Small delay to let the event loop start
    QTimer.singleShot(100, capture)
    app.exec()


if __name__ == "__main__":
    main()
