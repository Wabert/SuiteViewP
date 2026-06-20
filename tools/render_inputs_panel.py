"""Render the Illustration "Input" tab (DynamicInputsPanel) to a PNG offscreen.

Lets the layout be eyeballed without launching the full app. Loads a fake policy
so the rows/labels populate, sizes the panel, and grabs it to an image.

Usage:
    venv\\Scripts\\python.exe tools/render_inputs_panel.py [out.png]
"""
from __future__ import annotations

import os
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtWidgets import QApplication

from suiteview.illustration.ui.inputs_dynamic import DynamicInputsPanel
from suiteview.illustration.ui.styles import PURPLE_BG


class _FakePolicy:
    issue_date = date(1985, 7, 23)
    base_issue_age = 27
    attained_age = 41
    valuation_date = date(2026, 5, 23)
    policy_year = 41
    maturity_age = 121
    billing_frequency = 3
    modal_premium = 49.23
    def_of_life_ins = "GPT"
    glp = 2519.75
    accumulated_glp = 9275.88
    premiums_paid_to_date = 20000.0
    withdrawals_to_date = 0.0
    base_rate_class = "N"
    base_table_rating = 0
    base_plancode = "1S135M0X"
    status_code = "0"

    def get_coverages(self):
        return []

    def get_benefits(self):
        return []


def main() -> None:
    out = Path(sys.argv[1]) if len(sys.argv) > 1 else (Path.home() / ".suiteview" / "inputs_panel.png")
    out.parent.mkdir(parents=True, exist_ok=True)

    app = QApplication.instance() or QApplication([])
    panel = DynamicInputsPanel()
    panel.setStyleSheet(f"background-color: {PURPLE_BG};")
    panel.load_from_policy(_FakePolicy())
    panel.resize(1180, 760)
    app.processEvents()
    app.processEvents()
    panel.grab().save(str(out))
    print(str(out))


if __name__ == "__main__":
    main()
