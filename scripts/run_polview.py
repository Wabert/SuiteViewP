"""
Standalone launcher for PolView - Policy Viewer.

Usage:
    python scripts/run_polview.py [policy_number] [--region CKPR]

Examples:
    python scripts/run_polview.py
    python scripts/run_polview.py U0532652
    python scripts/run_polview.py U0532652 --region CKMO
"""

import sys
import os

# Add project root to path
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, project_root)

import argparse
from PyQt6.QtWidgets import QApplication
from PyQt6.QtGui import QFont


def main():
    parser = argparse.ArgumentParser(description="PolView - Policy Viewer")
    parser.add_argument("policy", nargs="?", default=None, help="Policy number to load")
    parser.add_argument("--region", "-r", default="CKPR",
                       choices=["CKPR", "CKMO", "CKAS", "CKSR", "CKCS"],
                       help="Region code (default: CKPR)")
    args = parser.parse_args()

    app = QApplication(sys.argv)
    app.setFont(QFont("Segoe UI", 9))
    app.setStyle("Fusion")

    from suiteview.polview.ui.main_window import GetPolicyWindow

    window = GetPolicyWindow()
    window.setWindowTitle("PolView - Policy Viewer")
    window.show()

    if args.policy:
        window.lookup_bar.policy_input.setText(args.policy)
        if args.region:
            window.lookup_bar.region_combo.setCurrentText(args.region)
        window.lookup_bar._on_get_policy()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
