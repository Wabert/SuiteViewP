"""Render the dynamic Illustration Input tab from a real local policy.

Saves ~/.suiteview/mock_illustration_inputs.png. Also smoke-tests the export:
adds a rate-class change row and runs a short projection through the engine.

Usage:
    venv\\Scripts\\python.exe tools/mock_illustration_inputs.py
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

os.environ["SUITEVIEW_LOCAL_DATA"] = "1"


def main() -> None:
    from PyQt6.QtWidgets import QApplication

    app = QApplication.instance() or QApplication(sys.argv)

    from suiteview.core.policy_service import clear_cache, get_policy_info
    from suiteview.illustration.core.calc_engine import IllustrationEngine
    from suiteview.illustration.core.illustration_policy_service import build_illustration_data
    from suiteview.illustration.models.input_set import IllustrationInputSet, IllustrationOptions
    from suiteview.illustration.ui.inputs_dynamic import DynamicInputsPanel

    clear_cache()
    policy_info = get_policy_info("U0688012", region="CKPR")
    panel = DynamicInputsPanel()
    panel.load_from_policy(policy_info)

    # Fill a few rows so the render shows real content.
    loan_row = panel.loan_section.rows()[0]
    loan_row.year_edit.set_value(12)
    loan_row._year_edited()
    loan_row.amount_edit.set_value(3000, decimals=2)
    loan_row.mode_combo.setCurrentText("A")
    loan_row.for_years_edit.set_value(4)
    loan_row._for_years_edited()

    rc_row = panel.rateclass_section.rows()[0]
    rc_row.year_edit.set_value(10)
    rc_row._year_edited()
    rc_row.value_combo.setCurrentIndex(1)

    panel.resize(1180, 640)
    panel.show()
    app.processEvents()
    out = Path.home() / ".suiteview" / "mock_illustration_inputs.png"
    out.parent.mkdir(parents=True, exist_ok=True)
    panel.grab().save(str(out))
    panel.hide()

    # Export + engine smoke: the rate-class change must apply without error.
    input_set = IllustrationInputSet()
    panel.collect_into(input_set)
    policy_data = build_illustration_data("U0688012", region="CKPR", company_code="01")
    results = IllustrationEngine().project(
        policy_data, months=60,
        options=IllustrationOptions(conform_to_tefra=False, exact_days_interest=True),
        future_inputs=input_set,
    )
    changes = [f"{c.kind.value}@{c.effective_date}" for c in input_set.policy_changes]
    print(f"saved {out}; exported {len(input_set.scheduled_transactions)} schedules, "
          f"{len(input_set.dated_transactions)} dated, changes={changes}; "
          f"projected {len(results) - 1} months, "
          f"AV@end={results[-1].av_end_of_month:,.2f}")


if __name__ == "__main__":
    main()
