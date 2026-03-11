#!/usr/bin/env python
"""
Standalone launcher for the Rate File Converter.

Usage:
    python scripts/run_rate_manager.py
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
    win.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
