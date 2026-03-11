"""
PolView - Main entry point.
Standalone application for policy lookup and display.

Usage (standalone):
    python scripts/run_polview.py [policy_number] [--region CKPR]

Usage (embedded from SuiteView):
    from suiteview.polview.main import create_viewer
    window = create_viewer("U0532652", region="CKPR")
"""

import sys
from typing import Optional

from PyQt6.QtWidgets import QApplication
from PyQt6.QtGui import QFont

from .ui.main_window import GetPolicyWindow
from suiteview.core.db2_constants import DEFAULT_REGION


def create_viewer(
    policy_number: Optional[str] = None,
    region: str = DEFAULT_REGION,
) -> GetPolicyWindow:
    """
    Create and show the policy viewer window.

    If a QApplication already exists (host app), re-uses it;
    otherwise creates one.  Never calls sys.exit(), so control
    returns to the caller after the window is shown.

    Args:
        policy_number: Optional policy number to load immediately.
        region: Region code (default CKPR).

    Returns:
        The GetPolicyWindow instance (caller can connect signals, etc.).
    """
    app = QApplication.instance()
    if app is None:
        app = QApplication(sys.argv)
        app.setFont(QFont("Segoe UI", 9))
        app.setStyle("Fusion")

    window = GetPolicyWindow()
    window.show()

    if policy_number:
        window.lookup_bar.policy_input.setText(policy_number)
        window.lookup_bar.region_input.setText(region)
        window.lookup_bar._on_get_policy()

    return window


def main(policy_number: Optional[str] = None, region: str = DEFAULT_REGION):
    """
    Run PolView as a standalone process.
    
    Args:
        policy_number: Optional policy number to load immediately
        region: Region code (default CKPR)
    """
    app = QApplication.instance()
    if app is None:
        app = QApplication(sys.argv)
        app.setFont(QFont("Segoe UI", 9))
        app.setStyle("Fusion")

    window = GetPolicyWindow()
    window.show()

    if policy_number:
        window.lookup_bar.policy_input.setText(policy_number)
        window.lookup_bar.region_input.setText(region)
        window.lookup_bar._on_get_policy()

    sys.exit(app.exec())


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="PolView - Policy Viewer")
    parser.add_argument("policy", nargs="?", default=None, help="Policy number to load")
    parser.add_argument("--region", "-r", default=DEFAULT_REGION,
                       choices=["CKPR", "CKMO", "CKAS", "CKSR", "CKCS"],
                       help="Region code")
    
    args = parser.parse_args()
    main(args.policy, args.region)
