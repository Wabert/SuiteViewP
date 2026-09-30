r"""Live native check of RERUN on an indeterminate premium term policy.

Opens the real Illustration window on a live term policy (read-only DB2/UL_Rates),
confirms RERUN switched to the term workspace, captures the Policy, Illustration
Inputs and In-force Check pages, runs Run Values (optionally at another premium mode),
captures the Values pages and the Report, and prints the report to a landscape PDF.

    venv\Scripts\python.exe tools\app\verify_rerun_term_window.py ^
        "{\"policy\": \"D0194819\", \"company\": \"01\", \"frequency\": 12}"

Keys: policy (required), company, region (CKPR), frequency (12/6/3/1), out_dir
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
    workspace = window.term_workspace
    outputs = {}

    def grab(name: str) -> None:
        path = out_dir / f"rerun_term_{policy}_{name}.png"
        if not window.grab().save(str(path)):
            raise RuntimeError(f"Could not save {path}")
        outputs[name] = str(path)

    active = window._term_active()
    for name, page in (("policy", workspace.policy_view), ("inputs", workspace.inputs_tab),
                       ("checks", workspace.checks_view)):
        workspace.tabs.setCurrentWidget(page)
        app.processEvents()
        grab(name)
    if cmd.get("frequency"):
        combo = workspace.inputs_tab.mode_combo
        combo.setCurrentIndex(combo.findData(int(cmd["frequency"])))
    window._on_run_values()
    app.processEvents()
    grab("report")
    report_pdf = out_dir / f"rerun_term_{policy}_report.pdf"
    workspace.report_view.write_pdf(str(report_pdf))
    outputs["report_pdf"] = str(report_pdf)
    workspace.tabs.setCurrentWidget(workspace.values_tab)
    for row, name in enumerate(("premiums", "detail")):
        workspace.values_tab.navigator.setCurrentRow(row)
        app.processEvents()
        grab(f"values_{name}")
    result = workspace.result
    checks = workspace.checks_view.grid.model.get_original_data() if workspace.checks_view.grid.model else None
    print(json.dumps({
        "term_workspace_active": active,
        "status": window._status_label.text(),
        "messages": messages,
        "years": len(result.years) if result else 0,
        "first_years": [vars(y) for y in result.years[:3]] if result else [],
        "report_pages": len(workspace.report_view.pages),
        "report_status": workspace.report_view.status_label.text(),
        "check_counts": checks["Status"].value_counts().to_dict() if checks is not None and len(checks) else {},
        "screenshots": outputs,
    }, indent=1, default=str))
    window.close()


if __name__ == "__main__":
    main()
