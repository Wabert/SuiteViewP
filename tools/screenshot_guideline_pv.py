"""Render the Guideline Monthly-PV dialog to a PNG for visual review.

Builds a real guideline basis (local data) for a policy, computes the
month-by-month GLP present-value detail, shows the dialog, and grabs it.

Usage:
    venv\\Scripts\\python.exe tools/screenshot_guideline_pv.py '{"policy":"U0688012","company":"01"}'
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def main() -> None:
    cmd = json.loads(sys.argv[1]) if len(sys.argv) > 1 else {"policy": "U0688012", "company": "01"}
    os.environ["SUITEVIEW_LOCAL_DATA"] = "1"

    from PyQt6.QtWidgets import QApplication

    app = QApplication.instance() or QApplication([])

    from suiteview.core.policy_service import clear_cache
    from suiteview.illustration.core.guideline_pv import guideline_glp_detail
    from suiteview.illustration.core.illustration_policy_service import build_illustration_data
    from suiteview.illustration.core.monthly_guideline import build_guideline_basis
    from suiteview.illustration.core.rate_loader import load_rates
    from suiteview.illustration.models.plancode_config import load_plancode
    from suiteview.illustration.ui.guideline_pv_view import GuidelinePvDetailView

    clear_cache()
    pd = build_illustration_data(
        cmd["policy"], region=cmd.get("region", "CKPR"), company_code=cmd.get("company"))
    config = load_plancode(pd.plancode)
    guar = load_rates(pd, config, coi_scale=0)
    basis = build_guideline_basis(
        pd, config, guar, attained_age=pd.issue_age, as_of=pd.issue_date)
    detail = guideline_glp_detail(basis)

    view = GuidelinePvDetailView()
    view.setWindowTitle(f"Guideline PV Detail — {cmd['policy']} at issue")
    view.resize(1240, 760)
    view.show_detail(detail)
    view.show()
    app.processEvents()
    app.processEvents()

    out_path = ROOT / "docs" / "Illustration_UL" / "guideline_pv_view.png"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    view.grab().save(str(out_path))
    print(json.dumps({"saved": str(out_path), "glp": detail["glp_rollup"]["premium"],
                      "rows": len(detail["glp_rows"])}))


if __name__ == "__main__":
    main()
