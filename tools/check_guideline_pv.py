"""Prove the month-by-month guideline PV (GLP) reconciles to the solver.

The new ``guideline_pv`` module re-expresses the Guideline Level Premium as a
survival-weighted present value (PVDB / PV Charges / PV Annuity). It must equal
``monthly_guideline.solve_guideline_premiums(basis).glp`` to the cent, because
both run off the same GuidelineBasis. This checks that on U0688012 at three
states (at issue, before the year-9 change, after a 100k->150k increase) — the
same checkpoints as tools/check_monthly_guideline.py.

Usage:
    venv\\Scripts\\python.exe tools/check_guideline_pv.py '{"policy":"U0688012","company":"01"}'
"""
from __future__ import annotations

import copy
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def main() -> None:
    cmd = json.loads(sys.argv[1])
    os.environ["SUITEVIEW_LOCAL_DATA"] = "1"

    import datetime

    from suiteview.core.policy_service import clear_cache
    from suiteview.illustration.core.calc_engine import _append_face_increase_segment
    from suiteview.illustration.core.guideline_pv import guideline_glp_detail
    from suiteview.illustration.core.illustration_policy_service import build_illustration_data
    from suiteview.illustration.core.monthly_guideline import (
        build_guideline_basis,
        solve_guideline_premiums,
    )
    from suiteview.illustration.core.rate_loader import load_rates
    from suiteview.illustration.core.target_premium import compute_target_premiums
    from suiteview.illustration.models.plancode_config import load_plancode

    policy_number = cmd["policy"]
    clear_cache()
    pd = build_illustration_data(
        policy_number, region=cmd.get("region", "CKPR"), company_code=cmd.get("company"))
    config = load_plancode(pd.plancode)

    out = {"policy": policy_number, "plancode": pd.plancode, "checks": {}}
    worst = 0.0

    def check(label, policy, attained_age, as_of, starting_av=0.0):
        nonlocal worst
        guar = load_rates(policy, config, coi_scale=0)
        basis = build_guideline_basis(
            policy, config, guar, attained_age=attained_age, as_of=as_of)
        solver_glp = solve_guideline_premiums(basis, starting_av=starting_av).glp
        detail = guideline_glp_detail(basis)
        pv_glp = detail["glp_rollup"]["premium"]
        diff = pv_glp - solver_glp
        worst = max(worst, abs(diff))
        out["checks"][label] = {
            "solver_glp": round(solver_glp, 2),
            "pv_glp": round(pv_glp, 2),
            "diff": round(diff, 4),
            "rows": len(detail["glp_rows"]),
            "rollup": detail["glp_rollup"],
        }

    check("at_issue", pd, pd.issue_age, pd.issue_date)

    change_date = datetime.date(2027, 11, 9)
    check("before_change", pd, 58, change_date)

    after = copy.deepcopy(pd)
    after_rates = load_rates(after, config, coi_scale=0)
    _append_face_increase_segment(after, after_rates, 50000.0, 58, change_date)
    targets = compute_target_premiums(after, config, as_of=change_date)
    after.mtp = targets.mtp_annual / 12.0
    after.ctp = targets.ctp_annual
    check("after_increase", after, 58, change_date, starting_av=7312.751508684311)

    out["worst_abs_diff"] = round(worst, 4)
    out["reconciles"] = worst < 0.01
    print(json.dumps(out, indent=2, default=str))


if __name__ == "__main__":
    main()
