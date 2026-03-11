"""
Audit Tool - Main entry point.
Standalone application for building and executing audit queries.

Usage (standalone):
    python scripts/run_audit.py [--region CKPR]

Usage (embedded from SuiteView):
    from suiteview.audit.main import create_audit_window
    window = create_audit_window(region="CKPR")
"""

import sys
from typing import Optional

from PyQt6.QtWidgets import QApplication
from PyQt6.QtGui import QFont

from .ui.main_window import AuditWindow
from suiteview.core.db2_constants import DEFAULT_REGION


def create_audit_window(region: str = DEFAULT_REGION) -> AuditWindow:
    """
    Create and show the audit tool window.

    If a QApplication already exists (host app), re-uses it;
    otherwise creates one.  Never calls sys.exit(), so control
    returns to the caller after the window is shown.

    Args:
        region: Region code (default CKPR).

    Returns:
        The AuditWindow instance.
    """
    app = QApplication.instance()
    if app is None:
        app = QApplication(sys.argv)
        app.setFont(QFont("Segoe UI", 9))
        app.setStyle("Fusion")

    window = AuditWindow(region=region)
    window.show()
    return window


def main(region: str = DEFAULT_REGION):
    """
    Run Audit Tool as a standalone process.
    
    Args:
        region: Region code (default CKPR)
    """
    app = QApplication.instance()
    if app is None:
        app = QApplication(sys.argv)
        app.setFont(QFont("Segoe UI", 9))
        app.setStyle("Fusion")

    window = AuditWindow(region=region)
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Audit Tool - Cyberlife Policy Audit")
    parser.add_argument("--region", default=DEFAULT_REGION, help="DB2 region code")
    args = parser.parse_args()
    main(args.region)
