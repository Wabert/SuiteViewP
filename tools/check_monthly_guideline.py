"""Validate the monthly guideline solver against admin and RERUN reference values.

Three checkpoints on U0688012 (all reference values captured previously):

1. AT ISSUE (age 50, face 100k):      admin GLP 2880.33 / GSP 31311.53 / 7-pay 6721.24
2. BEFORE the year-9 change (age 58): RERUN sGLP_Before1 4117.68 / sGSP_Before1 40911.67
3. AFTER a 100k->150k face increase:  RERUN sGLP_After1 6194.44 / sGSP_After1 61604.58
                                      / s7Pay_After1 11578.05 (starting AV 7312.75)

Usage:
    venv\\Scripts\\python.exe tools/check_monthly_guideline.py '{"policy":"U0688012","company":"01"}'
"""
from __future__ import annotations

import copy
import dataclasses
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


REFERENCES = {
    "at_issue": {"glp": 2880.33, "gsp": 31311.53, "seven_pay": 6721.24},
    "before_change": {"glp": 4117.6799753897585, "gsp": 40911.67047353367},
    "after_increase": {
        "glp": 6194.43955876932, "gsp": 61604.5820293184, "seven_pay": 11578.054672047016,
    },
}


def main() -> None:
    cmd = json.loads(sys.argv[1])
    os.environ["SUITEVIEW_LOCAL_DATA"] = "1"

    import datetime

    from suiteview.core.policy_service import clear_cache
    from suiteview.illustration.core.calc_engine import _append_face_increase_segment
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

    out = {"policy": policy_number, "plancode": pd.plancode, "issue_age": pd.issue_age}

    def solve(policy, attained_age, as_of, starting_av=0.0):
        guar = load_rates(policy, config, coi_scale=0)
        basis = build_guideline_basis(
            policy, config, guar, attained_age=attained_age, as_of=as_of)
        return solve_guideline_premiums(basis, starting_av=starting_av)

    def report(label, result, refs):
        rec = {}
        for key, ref in refs.items():
            got = getattr(result, key)
            rec[key] = {
                "computed": round(got, 2),
                "reference": round(ref, 2),
                "diff": round(got - ref, 2),
                "pct": round((got - ref) / ref * 100, 3) if ref else None,
            }
        out[label] = rec

    # ── 1. At issue ──
    report("at_issue", solve(pd, pd.issue_age, pd.issue_date), REFERENCES["at_issue"])

    # ── 2. Before the year-9 change (attained 58, unchanged coverage) ──
    change_date = datetime.date(2027, 11, 9)
    report("before_change", solve(pd, 58, change_date), REFERENCES["before_change"])

    # ── 3. After the 100k -> 150k increase (new segment at 58, recomputed targets) ──
    after = copy.deepcopy(pd)
    after_rates = load_rates(after, config, coi_scale=0)
    _append_face_increase_segment(after, after_rates, 50000.0, 58, change_date)
    targets = compute_target_premiums(after, config, as_of=change_date)
    after.mtp = targets.mtp_annual / 12.0
    after.ctp = targets.ctp_annual
    report(
        "after_increase",
        solve(after, 58, change_date, starting_av=7312.751508684311),
        REFERENCES["after_increase"],
    )

    print(json.dumps(out, indent=2, default=str))


if __name__ == "__main__":
    main()
