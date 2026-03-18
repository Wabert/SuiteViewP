"""
Audit Tool — application entry point.
"""

import sys
from typing import Optional
from PyQt6.QtWidgets import QApplication
from PyQt6.QtGui import QFont
from suiteview.core.db2_constants import DEFAULT_REGION


def create_audit_window(region: str = DEFAULT_REGION):
    from .audit_window import AuditWindow

    app = QApplication.instance()
    if app is None:
        app = QApplication(sys.argv)
        app.setFont(QFont("Segoe UI", 9))
        app.setStyle("Fusion")

    window = AuditWindow(region=region)
    window.show()
    return window


def main(region: str = DEFAULT_REGION):
    app = QApplication.instance()
    if app is None:
        app = QApplication(sys.argv)
        app.setFont(QFont("Segoe UI", 9))
        app.setStyle("Fusion")

    window = create_audit_window(region)
    sys.exit(QApplication.instance().exec())


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--region", default=DEFAULT_REGION)
    args = parser.parse_args()
    main(args.region)
