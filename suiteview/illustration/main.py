"""Launch helpers for the Illustration app."""

import sys

from PyQt6.QtWidgets import QApplication

from .ui import IllustrationWindow


def create_illustration_window(policy_number=None, region="CKPR", company_code=""):
    app = QApplication.instance() or QApplication(sys.argv)
    window = IllustrationWindow()
    window.show()
    if policy_number:
        window.lookup_bar.region_input.setText(region)
        window.lookup_bar.company_input.setText(company_code or "")
        window.lookup_bar.policy_input.setText(policy_number)
        window.lookup_bar._on_get_policy()
    return window
