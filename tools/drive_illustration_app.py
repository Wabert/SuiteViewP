"""Drive the real Illustration app end-to-end: load a policy, Run Values, save PDF.

Opens IllustrationWindow, loads the requested policy through the same slot the
lookup bar fires, clicks the Run Values button, switches to the Report tab, and
writes out window screenshots plus the illustration PDF (via the Report tab's
own write_pdf). Uses local SQLite data (SUITEVIEW_LOCAL_DATA=1) so it works
offline on the minipc.

Usage (single JSON arg):
    venv\\Scripts\\python.exe tools/drive_illustration_app.py '<json>'

    {"policy": "U0656998", "region": "CKPR", "company": "01",
     "out_dir": "C:/temp/out"}

Writes to out_dir: <policy>_policy_tab.png, <policy>_report_tab.png,
<policy>_illustration.pdf.  Prints JSON results to stdout.
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
    policy = cmd.get("policy", "U0656998")
    region = cmd.get("region", "CKPR")
    company = cmd.get("company", "01")
    out_dir = Path(cmd.get("out_dir", "."))
    out_dir.mkdir(parents=True, exist_ok=True)

    os.environ["SUITEVIEW_LOCAL_DATA"] = "1"

    from PyQt6.QtWidgets import QApplication

    from suiteview.illustration.ui.main_window import IllustrationWindow
    from suiteview.illustration.ui.report_tab import IllustrationReportTab

    app = QApplication.instance() or QApplication(sys.argv)
    window = IllustrationWindow()
    window.show()
    app.processEvents()

    # Same slot the PolicyLookupBar's policy_requested signal drives.
    window._on_get_policy(policy, region, company)
    app.processEvents()

    result: dict = {"policy": policy, "region": region, "company": company}
    if not (window._policy and window._policy.exists):
        result.update(ok=False, error=f"Policy {policy} did not load")
        print(json.dumps(result))
        return 1
    result["status_after_load"] = window._status_label.text()

    policy_png = str(out_dir / f"{policy}_policy_tab.png")
    window.grab().save(policy_png)
    result["policy_tab_png"] = policy_png

    window.run_values_btn.click()
    app.processEvents()

    report = window.report_tab._report
    if report is None:
        result.update(ok=False, error="Run Values produced no report",
                      status=window._status_label.text())
        print(json.dumps(result))
        return 1

    window.tabs.setCurrentWidget(window.report_tab)
    app.processEvents()
    report_png = str(out_dir / f"{policy}_report_tab.png")
    window.grab().save(report_png)
    result["report_tab_png"] = report_png

    pdf_path = str(out_dir / f"{policy}_illustration.pdf")
    IllustrationReportTab.write_pdf(report, pdf_path)
    result.update(
        ok=True,
        pdf=pdf_path,
        ledger_years=len(report.ledger),
        status_after_run=window._status_label.text(),
    )
    print(json.dumps(result))
    return 0


if __name__ == "__main__":
    sys.exit(main())
