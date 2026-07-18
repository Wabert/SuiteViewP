"""Verify per-policy session persistence in the real Illustration app.

Drives IllustrationWindow on local SQLite data (SUITEVIEW_LOCAL_DATA=1):
load policy A -> edit inputs -> Run Values -> load policy B -> load A again,
then asserts A's inputs AND previously computed values are back exactly,
without the engine re-projecting (a spy counts real projection runs).

Usage (single JSON arg, all keys optional):
    venv\\Scripts\\python.exe tools/drive_illustration_session.py '<json>'

    {"policy_a": "U0356726", "policy_b": "UL026332", "region": "CKPR",
     "company": "01", "out_dir": "C:/temp/out"}

Writes <policy_a>_restored_inputs.png / _restored_values.png to out_dir and
prints a JSON verdict to stdout.
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def main() -> int:
    cmd = json.loads(sys.argv[1]) if len(sys.argv) > 1 else {}
    policy_a = cmd.get("policy_a", "U0356726")
    policy_b = cmd.get("policy_b", "UL026332")
    region = cmd.get("region", "CKPR")
    company = cmd.get("company", "01")
    out_dir = Path(cmd.get("out_dir", "."))
    out_dir.mkdir(parents=True, exist_ok=True)

    os.environ["SUITEVIEW_LOCAL_DATA"] = "1"

    from PyQt6.QtWidgets import QApplication

    import suiteview.illustration.core.calc_engine as calc_engine
    from suiteview.illustration.ui.main_window import IllustrationWindow

    # Spy: count real projection runs (months > 0). Load checks project 0
    # months and are expected on every policy load; a session restore must
    # never trigger a real projection.
    projection_calls = {"count": 0}
    original_project = calc_engine.IllustrationEngine.project

    def project_spy(self, policy_data, months=0, *args, **kwargs):
        if months:
            projection_calls["count"] += 1
        return original_project(self, policy_data, months, *args, **kwargs)

    calc_engine.IllustrationEngine.project = project_spy

    app = QApplication.instance() or QApplication(sys.argv)
    window = IllustrationWindow()
    window.show()
    app.processEvents()

    result: dict = {"policy_a": policy_a, "policy_b": policy_b, "checks": {}}

    def check(name: str, ok: bool, detail: str = ""):
        result["checks"][name] = {"ok": bool(ok), **({"detail": detail} if detail else {})}

    # ── Load A and edit inputs ──
    window._on_get_policy(policy_a, region, company)
    app.processEvents()
    if not (window._policy and window._policy.exists):
        result.update(ok=False, error=f"Policy {policy_a} did not load")
        print(json.dumps(result))
        return 1
    tab_a = window.inputs_tab
    premium_row = tab_a.dynamic_panel.premium_section.rows()[0]
    premium_row.amount_edit.setText("123.45")
    tab_a.exact_days_check.setChecked(True)
    tab_a.unscheduled_premium_table.item(0, 0).setText("10/01/2027")
    tab_a.unscheduled_premium_table.item(0, 1).setText("500")

    # ── Run Values on A ──
    window.run_values_btn.click()
    app.processEvents()
    a_results_len = len(window.values_tab._results)
    a_status = window._status_label.text()
    a_report = window.report_tab.current_report()
    result["run_status_a"] = a_status
    result["projected_states_a"] = a_results_len
    if a_results_len <= 1 or "Values ready" not in a_status:
        result.update(ok=False, error="Run Values on policy A did not produce results")
        print(json.dumps(result))
        return 1

    # ── Switch to B ──
    window._on_get_policy(policy_b, region, company)
    app.processEvents()
    if not (window._policy and window._policy.exists):
        result.update(ok=False, error=f"Policy {policy_b} did not load")
        print(json.dumps(result))
        return 1
    check("b_gets_fresh_inputs", window.inputs_tab is not tab_a)
    check("b_starts_with_cleared_values", len(window.values_tab._results) == 0)
    check("b_premium_row_not_a",
          window.inputs_tab.dynamic_panel.premium_section.rows()[0].amount_edit.text() != "123.45")

    # ── Back to A: everything must restore with no real projection ──
    calls_before_restore = projection_calls["count"]
    window._on_get_policy(policy_a, region, company)
    app.processEvents()
    check("inputs_widget_restored", window.inputs_tab is tab_a)
    check("premium_amount_restored", premium_row.amount_edit.text() == "123.45",
          premium_row.amount_edit.text())
    check("exact_days_restored", tab_a.exact_days_check.isChecked())
    check("grid_date_restored",
          tab_a.unscheduled_premium_table.item(0, 0).text() == "10/01/2027")
    check("grid_amount_restored",
          tab_a.unscheduled_premium_table.item(0, 1).text() == "500")
    check("values_restored", len(window.values_tab._results) == a_results_len,
          f"{len(window.values_tab._results)} vs {a_results_len}")
    check("status_banner_restored", window._status_label.text() == a_status,
          window._status_label.text())
    check("report_restored", window.report_tab.current_report() is a_report)
    check("no_projection_on_restore",
          projection_calls["count"] == calls_before_restore,
          f"projection calls during restore: {projection_calls['count'] - calls_before_restore}")

    # ── Screenshots of the restored state ──
    window.tabs.setCurrentWidget(window._inputs_stack)
    app.processEvents()
    inputs_png = str(out_dir / f"{policy_a}_restored_inputs.png")
    window.grab().save(inputs_png)
    window.tabs.setCurrentWidget(window.values_tab)
    app.processEvents()
    values_png = str(out_dir / f"{policy_a}_restored_values.png")
    window.grab().save(values_png)
    result["inputs_png"] = inputs_png
    result["values_png"] = values_png

    result["ok"] = all(entry["ok"] for entry in result["checks"].values())
    print(json.dumps(result, indent=2))
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
