"""
ABR Quote — main entry point.

Usage (standalone):
    python scripts/run_abrquote.py

Usage (embedded from SuiteView):
    from suiteview.abrquote.main import create_abrquote_window
    window = create_abrquote_window()
"""

import sys

from PyQt6.QtWidgets import QApplication
from PyQt6.QtGui import QFont

from .ui.abr_window import ABRQuoteWindow


def create_abrquote_window(parent=None) -> ABRQuoteWindow:
    """
    Create and show the ABR Quote Tool window.

    If a QApplication already exists (host app), re-uses it;
    otherwise creates one.  Never calls sys.exit(), so control
    returns to the caller after the window is shown.

    Returns:
        The ABRQuoteWindow instance.
    """
    app = QApplication.instance()
    if app is None:
        app = QApplication(sys.argv)
        app.setFont(QFont("Segoe UI", 9))
        app.setStyle("Fusion")

    window = ABRQuoteWindow(parent=parent)
    window.show()
    return window
