"""Render the dynamic Input tab with a Loan Repayments "Pay-off" row, offscreen.

Loads a real policy from the local SQLite data (SUITEVIEW_LOCAL_DATA=1), sets
the loan-repayment row's type to Pay-off with a window, optionally fills a
solved amount the way Run Values does, and saves a PNG so the disabled amount
field and dropdown can be eyeballed.

Usage:
    venv\\Scripts\\python.exe tools/render_inputs_loan_payoff.py [policy] [out.png]
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
    policy_num = sys.argv[1] if len(sys.argv) > 1 else "S0503261"
    out = Path(sys.argv[2]) if len(sys.argv) > 2 else (
        Path.home() / ".suiteview" / "inputs_loan_payoff.png")

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
    row = panel.repayment_section.rows()[0]
    row.type_combo.setCurrentText("Pay-off")
    ctx = panel._ctx
    row.year_edit.set_value(ctx.forecast_year + 1)
    row._year_edited()
    row.mode_combo.setCurrentText("A")
    row.for_years_edit.set_value(5)
    row._for_years_edited()
    # Mimic the Run Values fill so the disabled solved amount shows.
    panel.set_loan_payoff_amounts([1292.79])
    tab.input_tabs.setCurrentIndex(0)  # dynamic Input tab
    tab.resize(1300, 900)
    tab.show()
    app.processEvents()

    out.parent.mkdir(parents=True, exist_ok=True)
    tab.grab().save(str(out))
    print(f"saved {out}  |  requests: {panel.loan_payoff_requests()}"
          f"  |  amount_enabled: {row.amount_edit.isEnabled()}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
