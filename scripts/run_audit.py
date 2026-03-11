"""
Standalone launcher for Audit Tool.

Usage:
    python scripts/run_audit.py [--region CKPR]

Examples:
    python scripts/run_audit.py
    python scripts/run_audit.py --region CKMO
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
    parser = argparse.ArgumentParser(description="Audit Tool - Policy Search")
    parser.add_argument("--region", "-r", default="CKPR",
                       choices=["CKPR", "CKMO", "CKAS", "CKSR", "CKCS"],
                       help="Region code (default: CKPR)")
    args = parser.parse_args()

    app = QApplication(sys.argv)
    app.setFont(QFont("Segoe UI", 9))
    app.setStyle("Fusion")

    from suiteview.audit.main import create_audit_window

    window = create_audit_window(region=args.region)
    window.setWindowTitle("SuiteView - Audit Tool")
    window.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
