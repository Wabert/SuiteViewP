#!/usr/bin/env python
"""
Standalone launcher for Rate Manager.

Usage:
    venv\\Scripts\\python.exe scripts\\run_rate_manager.py [--database | --manage]
"""

import sys
import os

# Ensure the project root is on the path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from PyQt6.QtWidgets import QApplication
from suiteview.ratemanager.ratemanager_window import RateManagerWindow


def main():
    app = QApplication(sys.argv)
    win = RateManagerWindow()
    if "--database" in sys.argv or "--manage" in sys.argv:
        win._show_database()
    if "--manage" in sys.argv:
        win.database_panel.tabs.setCurrentWidget(win.database_panel.manage_tab)
    win.show()
    win.raise_()
    win.activateWindow()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
