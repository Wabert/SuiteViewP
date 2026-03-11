r"""
Launch ABR Quote, load a policy, navigate to the Output tab, and screenshot.

Usage:
    $env:PYTHONPATH = "C:\Users\ab7y02\Dev\SuiteViewP"
    venv\Scripts\python.exe tools/screenshot_abr_output.py [policy_number]
"""

import sys
from pathlib import Path

from PyQt6.QtWidgets import QApplication
from PyQt6.QtCore import QTimer


def main():
    policy_number = sys.argv[1] if len(sys.argv) > 1 else "15023651"

    app = QApplication(sys.argv)

    from suiteview.abrquote.ui.abr_window import ABRQuoteWindow

    win = ABRQuoteWindow()
    win.show()

    def load_policy():
        # Type the policy number and trigger retrieve
        pp = win.policy_panel
        pp.policy_input.setText(policy_number)
        pp._on_retrieve()
        # Wait for DB2 query to finish, then navigate
        QTimer.singleShot(6000, navigate_and_capture)

    def navigate_and_capture():
        # Navigate to Output tab (step index 2)
        win._set_step(2)
        # Take screenshot after rendering
        QTimer.singleShot(500, capture)

    def capture():
        screen = app.primaryScreen()
        if screen is None:
            print("ERROR: No screen found")
            app.quit()
            return
        output = str(Path.home() / ".suiteview" / "abr_output_screenshot.png")
        pixmap = screen.grabWindow(0)
        pixmap.save(output, "PNG")
        print(f"Screenshot saved to {output}")
        app.quit()

    # Wait for window to render, then load policy
    QTimer.singleShot(1000, load_policy)
    app.exec()


if __name__ == "__main__":
    main()
