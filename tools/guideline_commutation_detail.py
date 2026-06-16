"""Closed-form 7702 guideline solve with every commutation vector exposed.

Reuses the policy -> GuidelinePremiumInputs bridge from tools/validate_guideline.py
(guaranteed COI per $1000/month -> implied annual qx; current loads/fees/EPU as
expenses), then rebuilds the commutation columns the closed-form calculate_glp /
calculate_gsp consume and shows the present-value roll-up year by year:

    GLP = [ SA·A_{x:n} + PV(expenses) + load$ ] / [ (1 − load)·ä_{x:n} ]
    GSP = [ SA·A_{x:n} + PV(expenses) ] / (1 − single_load)   (GSP interest floor)

Per attained age it prints qx, lx, dx, v^t, Dx, Cx, Mx, Nx and the running PV of
the death benefit, the premium-paying annuity, and the expense charges — so the
totals (term + pure endowment = A_{x:n}; ΣDx/Dx = ä_{x:n}) can be read straight
off the cumulative columns.

Usage (single JSON arg):
    venv\\Scripts\\python.exe tools/guideline_commutation_detail.py '<json>'

    {"policy":"U0688012","company":"01","region":"CKPR","endowment_age":100,
     "basis":"glp","csv":"/tmp/glp_vectors.csv","png":"/tmp/glp_vectors.png"}

"basis" selects which interest floor the vector grid is tabulated at:
  "glp" -> max(guar, 4%)   "gsp" -> max(guar, 6%).  The roll-up block always
reports both GLP and GSP.
"""
from __future__ import annotations

import csv as csvmod
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def build_inputs(policy: str, region: str, company, endow: int):
    """Policy -> (GuidelinePremiumInputs, context) using the shared core bridge.

    GLP/GSP are issue-age quantities, so the inputs are built at the policy's
    issue age (the same convention as the admin comparison).
    """
    os.environ["SUITEVIEW_LOCAL_DATA"] = "1"

    from suiteview.core.policy_service import clear_cache
    from suiteview.illustration.core.illustration_policy_service import build_illustration_data
    from suiteview.illustration.models.plancode_config import load_plancode
    from suiteview.illustration.core.guideline_calc import policy_to_guideline_inputs

    clear_cache()
    pd = build_illustration_data(policy, region=region, company_code=company)
    config = load_plancode(pd.plancode)
    gi = policy_to_guideline_inputs(pd, config, pd.issue_age, endowment_age=endow)
    ctx = {
        "policy": policy, "plancode": pd.plancode, "issue_age": pd.issue_age,
        "face": pd.face_amount, "endowment_age": endow, "admin_glp": pd.glp,
        "admin_gsp": pd.gsp, "guaranteed_rate": gi.guaranteed_rate,
    }
    return gi, ctx


def run(cmd: dict) -> dict:
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from suiteview.illustration.core.guideline_calc import commutation_vectors

    policy = cmd["policy"]
    gi, ctx = build_inputs(
        policy, cmd.get("region", "CKPR"), cmd.get("company"),
        int(cmd.get("endowment_age", 100)),
    )
    exp = gi.expenses

    glp_rows, glp_roll = commutation_vectors(gi, gi.glp_rate, single=False)
    gsp_rows, gsp_roll = commutation_vectors(gi, gi.gsp_rate, single=True)

    basis = cmd.get("basis", "glp").lower()
    rows = gsp_rows if basis == "gsp" else glp_rows

    csv_path = cmd.get("csv")
    if csv_path:
        _write_csv(rows, csv_path)
    png_path = cmd.get("png")
    if png_path:
        png_path = _render(rows, png_path, f"{policy} — {basis.upper()} commutation vectors")

    return {
        "context": {k: ctx[k] for k in ("policy", "plancode", "issue_age", "face",
                                        "endowment_age", "guaranteed_rate",
                                        "admin_glp", "admin_gsp")},
        "expenses": {
            "premium_load_target": exp.premium_load_target,
            "premium_load_excess": exp.premium_load_excess,
            "target_premium(ctp)": exp.target_premium,
            "fee_annual": exp.per_policy_fee_annual,
            "per_unit_annual": exp.per_unit_charge_annual,
            "units": exp.units,
        },
        "glp_rollup": glp_roll,
        "gsp_rollup": gsp_roll,
        "vector_rows": len(rows),
        "vectors_head": rows[:6],
        "vectors_tail": rows[-3:],
        "csv": csv_path,
        "png": png_path,
    }


def _write_csv(rows, path):
    out = Path(path)
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", newline="") as fh:
        w = csvmod.DictWriter(fh, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)


def _render(rows, path, title):
    import pandas as pd
    from PyQt6.QtWidgets import QApplication, QVBoxLayout, QLabel, QWidget
    from suiteview.ui.widgets.filter_table_view import FilterTableView

    app = QApplication.instance() or QApplication([])
    holder = QWidget()
    holder.setStyleSheet("background:#F3ECFC;")
    lay = QVBoxLayout(holder)
    lay.setContentsMargins(6, 6, 6, 6)
    head = QLabel(title)
    head.setStyleSheet("background:#2A1458;color:#FFD54F;font-weight:bold;"
                       "font-size:11px;padding:4px 8px;border-radius:4px;")
    lay.addWidget(head)
    grid = FilterTableView()
    grid.set_search_visible(False)
    grid.apply_ledger_style()
    grid.set_sort_enabled(False)
    lay.addWidget(grid, 1)
    grid.set_dataframe(pd.DataFrame(rows), limit_rows=False)
    grid.set_numeric_formatting(default_decimals=4)
    grid.autofit_columns_to_data()
    holder.resize(1180, min(40 + 22 * (len(rows) + 2), 1400))
    out = Path(path)
    out.parent.mkdir(parents=True, exist_ok=True)
    holder.grab().save(str(out))
    app.processEvents()
    return str(out)


def main() -> None:
    if len(sys.argv) < 2:
        print(json.dumps({"error": "missing JSON arg"}))
        sys.exit(1)
    print(json.dumps(run(json.loads(sys.argv[1])), indent=1, default=str))


if __name__ == "__main__":
    main()
