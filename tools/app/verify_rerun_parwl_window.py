r"""Live native check of RERUN on a participating whole life policy.

Opens the real Illustration window on a live par WL policy (read-only DB2/UL_Rates),
confirms RERUN switched to the par WL workspace, captures the Policy, Illustration
Inputs and In-force Check pages, runs Run Values (optionally with a reduced paid-up
year and a new loan entered through the input screen) and captures the Values
pages and the Report pages, and prints the report to a landscape PDF.

    venv\Scripts\python.exe tools\app\verify_rerun_parwl_window.py ^
        "{\"policy\": \"000282131\", \"company\": \"26\", \"rpu_year\": 30, \"loan_year\": 27, \"loan\": 1000}"

Keys: policy (required), company, region (CKPR), rpu_year, loan_year + loan, out_dir
(default the diagnostics folder). Prints JSON with the workspace facts and PNG paths.
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

    from PyQt6.QtWidgets import QApplication, QMessageBox
    from suiteview.illustration.main import create_illustration_window

    messages = []
    QMessageBox.warning = lambda *a, **k: messages.append(("warning", a[2] if len(a) > 2 else ""))
    QMessageBox.information = lambda *a, **k: messages.append(("information", a[2] if len(a) > 2 else ""))
    QMessageBox.critical = lambda *a, **k: messages.append(("critical", a[2] if len(a) > 2 else ""))

    app = QApplication.instance() or QApplication(sys.argv)
    window = create_illustration_window(
        policy_number=policy, region=cmd.get("region", "CKPR"), company_code=cmd.get("company", ""))
    window.resize(1500, 950)
    app.processEvents()
    workspace = window.parwl_workspace
    outputs = {}

    def grab(name: str) -> None:
        path = out_dir / f"rerun_parwl_{policy}_{name}.png"
        if not window.grab().save(str(path)):
            raise RuntimeError(f"Could not save {path}")
        outputs[name] = str(path)

    active = window._parwl_active()
    for name, page in (("policy", workspace.policy_view), ("inputs", workspace.inputs_tab),
                       ("checks", workspace.checks_view)):
        workspace.tabs.setCurrentWidget(page)
        app.processEvents()
        grab(name)
    inputs = workspace.inputs_tab
    if cmd.get("rpu_year"):
        inputs.rpu_check.setChecked(True)
        inputs.rpu_when.setText(str(cmd["rpu_year"]))
    if cmd.get("loan_year") and cmd.get("loan"):
        inputs.loan_table.item(0, 0).setText(str(cmd["loan_year"]))
        inputs.loan_table.item(0, 1).setText(str(cmd["loan"]))
    window._on_run_values()
    app.processEvents()
    grab("report")
    report_pdf = out_dir / f"rerun_parwl_{policy}_report.pdf"
    workspace.report_view.write_pdf(str(report_pdf))
    outputs["report_pdf"] = str(report_pdf)
    workspace.tabs.setCurrentWidget(workspace.values_tab)
    for row, name in enumerate(("summary", "premiums", "dividends", "additions")):
        workspace.values_tab.navigator.setCurrentRow(row)
        app.processEvents()
        grab(f"values_{name}")
    result = workspace.result
    checks = workspace.checks_view.grid.model.get_original_data() if workspace.checks_view.grid.model else None
    print(json.dumps({
        "parwl_workspace_active": active,
        "status": window._status_label.text(),
        "messages": messages,
        "months": len(result.months) if result else 0,
        "years": len(result.years) if result else 0,
        "report_pages": len(workspace.report_view.pages),
        "report_status": workspace.report_view.status_label.text(),
        "first_year": vars(result.years[0]) if result and result.years else None,
        "check_counts": checks["Status"].value_counts().to_dict() if checks is not None and len(checks) else {},
        "screenshots": outputs,
    }, indent=1, default=str))
    window.close()


if __name__ == "__main__":
    main()
