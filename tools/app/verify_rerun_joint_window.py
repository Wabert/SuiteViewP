r"""Live native check of RERUN on a joint survivor (second-to-die) UL policy.

Opens the real Illustration window on a live company-26 joint policy (read-only
DB2/UL_Rates), captures the Policy tab (joint insured, per-insured extras,
monthly-deduction check) and the policy badge strip, runs Run Values and captures the Values overview and
the Joint COI group, then enters a joint-insured table rating next year through
the input rows, re-runs and captures that recalc's Joint COI sheet.

    venv\Scripts\python.exe tools\app\verify_rerun_joint_window.py ^
        "{\"policy\": \"000335148\", \"out_dir\": \"<dir>\"}"

Keys: policy (required), company (26), region (CKPR), out_dir (default the
diagnostics folder). Prints JSON with the checked Policy-tab values and PNG paths.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from suiteview.core.local_dev import local_data_enabled  # noqa: E402
from suiteview.core.profile_paths import diagnostics_dir  # noqa: E402


def main() -> None:
    arg = sys.argv[1]
    cmd = json.loads(Path(arg[1:]).read_text(encoding="utf-8-sig")) if arg.startswith("@") else json.loads(arg)
    if local_data_enabled():
        raise RuntimeError("This verification requires live data, not SUITEVIEW_LOCAL_DATA.")
    policy = cmd["policy"]
    out_dir = Path(cmd.get("out_dir") or diagnostics_dir())
    out_dir.mkdir(parents=True, exist_ok=True)

    from PyQt6.QtWidgets import QApplication
    from suiteview.illustration.main import create_illustration_window

    app = QApplication.instance() or QApplication(sys.argv)
    window = create_illustration_window(
        policy_number=policy, region=cmd.get("region", "CKPR"),
        company_code=cmd.get("company", "26"))
    window.resize(1500, 950)
    app.processEvents()

    info = window.policy_tab.policy_info
    fields = {name: info._fields[name].text() for name in (
        "plancode_label", "joint_label", "joint_insured_label", "coi_basis_label",
        "sex", "rateclass", "issue_age", "table_rating", "flat_extra",
        "cyberlife_md", "calculated_md")}
    badges = window.summary_strip.chip_texts()
    outputs = {}

    def grab(name: str) -> None:
        path = out_dir / f"rerun_joint_{policy}_{name}.png"
        if not window.grab().save(str(path)):
            raise RuntimeError(f"Could not save {path}")
        outputs[name] = str(path)

    window.tabs.setCurrentWidget(window.policy_tab)
    app.processEvents()
    grab("policy")
    window._on_run_values()
    app.processEvents()
    window.tabs.setCurrentWidget(window.values_tab)
    app.processEvents()
    grab("values")
    results = getattr(window.values_tab, "_results", None) or []
    joint_grid = window.values_tab._tab_grids["Joint COI"]
    window.values_tab.content_stack.setCurrentWidget(joint_grid)
    app.processEvents()
    grab("values_joint_coi")
    joint_frame = joint_grid.model.get_original_data() if joint_grid.model is not None else None
    joint_group_ok = joint_frame is not None and any(
        str(c).startswith("Joint COI Cov") for c in joint_frame.columns)

    # A joint-insured table rating entered through the real input rows, next year.
    panel = window.inputs_tab.dynamic_panel
    row = panel.table_section.rows()[0]
    row.year_edit.setText(str(panel._ctx.forecast_year + 1))
    row._year_edited()
    row.value_combo.setCurrentIndex(next(
        i for i in range(row.value_combo.count())
        if str(row.value_combo.itemData(i)).startswith("01:")
        and not str(row.value_combo.itemData(i)).endswith(":0")))
    table_choice = row.value_combo.currentText()
    window._on_run_values()
    app.processEvents()
    recalc = window.values_tab.recalc_view
    window.values_tab.content_stack.setCurrentWidget(recalc)
    recalc.show_date(0)
    sheet = recalc.detail_views[0] if recalc.detail_views else None
    joint_sheet = {}
    if sheet is not None:
        sheet.tabs.setCurrentWidget(sheet.joint_page)
        app.processEvents()
        grab("recalc_joint_coi")
        joint_sheet = {"visible": sheet.tabs.isTabVisible(sheet.tabs.indexOf(sheet.joint_page)),
                       "info": sheet.joint_info.text(), "note": sheet.joint_note.text(),
                       "rows": sheet.joint_grid.model.rowCount() if sheet.joint_grid.model else 0}
    report = {
        "policy": policy, "fields": fields, "projected_months": len(results),
        "load_warnings": window.policy_tab.rate_warning_label.text(),
        "md_matches": fields["cyberlife_md"] == fields["calculated_md"],
        "joint_shown": fields["joint_label"] == "Joint Second to Die" and bool(fields["joint_insured_label"]),
        "joint_coi_group": joint_group_ok,
        "badges": badges,
        "table_change": table_choice, "recalc_joint_sheet": joint_sheet,
        "outputs": outputs,
    }
    report["all_ok"] = (report["md_matches"] and report["joint_shown"] and len(results) > 1
                        and joint_group_ok and joint_sheet.get("visible")
                        and joint_sheet.get("rows", 0) > 0
                        and "Joint Second to Die" in badges)
    print(json.dumps(report, indent=1))
    window.close()
    app.processEvents()


if __name__ == "__main__":
    main()
