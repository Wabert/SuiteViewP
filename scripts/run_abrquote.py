"""
ABR Quote Tool — standalone launcher.

Run from project root:
    python scripts/run_abrquote.py

Matches the pattern of scripts/run_polview.py.
"""

import sys
import os

# Ensure the project root is on the path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from PyQt6.QtWidgets import QApplication
from PyQt6.QtGui import QFont


def main():
    app = QApplication(sys.argv)
    app.setFont(QFont("Segoe UI", 9))
    app.setStyle("Fusion")

    from suiteview.abrquote.ui.abr_window import ABRQuoteWindow

    window = ABRQuoteWindow()
    window.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
