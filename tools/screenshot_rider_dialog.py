"""Screenshot the Illustration rider keep/change/drop dialog for visual review.

Opens the RiderButtonsPanel dialog with fake policy data, grabs a PNG in the
"Keep rider" state (Effective toggle should look disabled) and again after
clicking "Change rider" (toggle re-enabled), then closes.

Run: venv\Scripts\python.exe tools\screenshot_rider_dialog.py
Writes: ~/.suiteview/rider_dialog_keep.png and rider_dialog_change.png
"""
import json
import sys
from datetime import date
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from PyQt6.QtCore import QTimer
from PyQt6.QtWidgets import QApplication, QPushButton

from suiteview.illustration.ui.inputs_dynamic import DynamicInputsPanel

OUT_DIR = Path.home() / ".suiteview"


class _FakePolicy:
    issue_date = date(1998, 8, 1)
    base_issue_age = 24
    attained_age = 52
    valuation_date = date(2026, 7, 1)
    policy_year = 29
    maturity_age = 121
    billing_frequency = 1
    modal_premium = 150.0
    def_of_life_ins = "GPT"
    glp = 1200.0
    accumulated_glp = 5000.0
    premiums_paid_to_date = 10000.0
    withdrawals_to_date = 0.0
    base_rate_class = "N"
    base_table_rating = 0
    base_plancode = "1U135D00"
    status_code = "0"

    def get_coverages(self):
        return [SimpleNamespace(
            cov_pha_nbr=2, form_number="ULCTR91", plancode="1U538F00",
            issue_date=date(1998, 8, 1), face_amount=10000.0, issue_age=24,
            rate_class="N", cov_status="2", is_base=False, rate=0.5,
            annual_premium=20.0)]

    def get_benefits(self):
        return []


def main():
    app = QApplication(sys.argv)
    panel = DynamicInputsPanel()
    panel.load_from_policy(_FakePolicy())

    shots = {}

    def capture():
        dlg = app.activeModalWidget()
        if dlg is None:
            print(json.dumps({"ok": False, "error": "no modal dialog found"}))
            app.exit(1)
            return
        keep_path = OUT_DIR / "rider_dialog_keep.png"
        dlg.grab().save(str(keep_path))
        shots["keep"] = str(keep_path)

        change_btn = next(b for b in dlg.findChildren(QPushButton)
                          if b.text() == "Change rider")
        change_btn.click()
        change_path = OUT_DIR / "rider_dialog_change.png"
        dlg.grab().save(str(change_path))
        shots["change"] = str(change_path)
        dlg.accept()

    QTimer.singleShot(400, capture)
    panel.riders_panel._buttons["cov:2"].click()   # opens the modal dialog

    print(json.dumps({"ok": True, "shots": shots}))


if __name__ == "__main__":
    main()
