"""Render the dynamic Input tab with "Min to Maturity" selected, offscreen.

Loads a real policy from the local SQLite data (SUITEVIEW_LOCAL_DATA=1), sets
the premium row's type to Min to Maturity, and saves a PNG so the section
enable/disable states can be eyeballed: Face Amount Change and Death Benefit
Option Change stay editable while withdrawals / loans / loan repayments (and
the rate-class / table-rating changes and riders) grey out.

Usage:
    venv\\Scripts\\python.exe tools/render_inputs_min_level.py [policy] [out.png]
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ["SUITEVIEW_LOCAL_DATA"] = "1"


def main():
    policy_num = sys.argv[1] if len(sys.argv) > 1 else "U0356726"
    out = Path(sys.argv[2]) if len(sys.argv) > 2 else (
        Path.home() / ".suiteview" / "inputs_min_level.png")

    from PyQt6.QtWidgets import QApplication

    app = QApplication(sys.argv[:1])

    from suiteview.core.policy_service import get_policy_info
    from suiteview.illustration.ui.inputs_tab import IllustrationInputsTab

    pi = get_policy_info(policy_num, region="CKPR")
    if pi is None or not pi.exists:
        print(f"policy {policy_num} not found in local data")
        return 1

    tab = IllustrationInputsTab()
    tab.load_data_from_policy(pi)
    panel = tab.dynamic_panel
    panel.premium_section.rows()[0].type_combo.setCurrentText("Min to Maturity")
    tab.input_tabs.setCurrentIndex(0)  # dynamic Input tab
    tab.resize(1300, 900)
    tab.show()
    app.processEvents()

    out.parent.mkdir(parents=True, exist_ok=True)
    tab.grab().save(str(out))
    states = {
        "face": panel.face_section.isEnabled(),
        "dbo": panel.dbo_section.isEnabled(),
        "loan": panel.loan_section.isEnabled(),
        "withdrawal": panel.withdrawal_section.isEnabled(),
        "repayment": panel.repayment_section.isEnabled(),
        "rateclass": panel.rateclass_section.isEnabled(),
        "table": panel.table_section.isEnabled(),
        "riders": panel.riders_panel.isEnabled(),
    }
    print(f"saved {out}  |  enabled: {states}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
