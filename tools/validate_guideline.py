"""Validate the 7702 guideline calc locally using the GUARANTEED COI (scale 0).

Proves the guaranteed COI is in the local rates DB and usable: build guaranteed
rates (coi_scale=0), solve the GLP by endowment (calculate_glp_iterative) at the
policy's ISSUE age, and compare to the admin GLP loaded from DB2.

Usage:
    venv\\Scripts\\python.exe tools/validate_guideline.py '{"policy":"U0688012","company":"01","endowment_age":100}'
"""
from __future__ import annotations

import dataclasses
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

    from suiteview.core.policy_service import clear_cache
    from suiteview.illustration.core.illustration_policy_service import build_illustration_data
    from suiteview.illustration.core.rate_loader import load_rates
    from suiteview.illustration.models.plancode_config import load_plancode
    from suiteview.illustration.core.guideline_calc import calculate_glp_iterative

    policy = cmd["policy"]
    region = cmd.get("region", "CKPR")
    company = cmd.get("company")
    endow = int(cmd.get("endowment_age", 100))

    clear_cache()
    pd = build_illustration_data(policy, region=region, company_code=company)
    config = load_plancode(pd.plancode)

    # Guaranteed-COI rates (scale 0); loads/fees stay current (scale 1).
    guar = load_rates(pd, config, coi_scale=0)
    cur = load_rates(pd, config, coi_scale=1)
    g_first = guar.segment_coi.get(pd.base_segment.coverage_phase, [None, None])[1]
    c_first = cur.segment_coi.get(pd.base_segment.coverage_phase, [None, None])[1]

    # GLP is an issue-age value: rebuild a CLEAN issue-state policy (year 1,
    # valuation = issue date) so the endowment projection starts at issue, not at
    # the inforce valuation date.
    at_issue = dataclasses.replace(
        pd,
        attained_age=pd.issue_age,
        policy_year=1,
        policy_month=1,
        duration=1,
        valuation_date=pd.issue_date,
        account_value=0.0,
        premiums_paid_to_date=0.0,
        premiums_ytd=0.0,
    )
    res = calculate_glp_iterative(at_issue, guar, glp_rate=0.04, endowment_age=endow)

    # ── Closed-form commutation GLP/GSP from the guaranteed COI ──
    from suiteview.illustration.core.commutation import MortalityTable
    from suiteview.illustration.core.guideline_calc import (
        ExpenseAssumptions, GuidelinePremiumInputs, calculate_glp, calculate_gsp,
        calculate_7pay_premium,
    )

    def _lvl(arr, i=1, default=0.0):
        return arr[i] if arr and len(arr) > i and arr[i] is not None else default

    # Guaranteed COI (per 1000 / month) -> implied annual qx, by attained age.
    coi_sched = guar.segment_coi.get(pd.base_segment.coverage_phase, [])
    qx = []
    for d in range(1, len(coi_sched)):
        rate = coi_sched[d]
        if rate is None:
            break
        mq = float(rate) / 1000.0
        qx.append(min(1.0, 1.0 - (1.0 - mq) ** 12))
    mort = MortalityTable.from_rates(qx, start_age=pd.issue_age, name="guar-coi")

    exp = ExpenseAssumptions(
        premium_load_target=_lvl(cur.tpp),
        premium_load_excess=_lvl(cur.epp),
        target_premium=float(pd.ctp or 0.0),
        per_policy_fee_annual=12.0 * _lvl(cur.mfee),
        per_unit_charge_annual=12.0 * _lvl(cur.epu),
        units=pd.face_amount / 1000.0,
    )
    gi = GuidelinePremiumInputs(
        attained_age=pd.issue_age, mortality=mort, specified_amount=pd.face_amount,
        db_option="A", endowment_age=endow,
        guaranteed_rate=float(pd.guaranteed_interest_rate or 0.0),
        glp_rate=0.04, gsp_rate=0.06, expenses=exp,
    )
    comm_glp = calculate_glp(gi)
    comm_gsp = calculate_gsp(gi)
    comm_7pay = calculate_7pay_premium(gi)

    print(json.dumps({
        "policy": policy,
        "plancode": pd.plancode,
        "issue_age": pd.issue_age,
        "face": pd.face_amount,
        "endowment_age": endow,
        "coi_dur1_guaranteed_scale0": g_first,
        "coi_dur1_current_scale1": c_first,
        "admin_glp": pd.glp,
        "admin_gsp": pd.gsp,
        "iterative_glp_guaranteed": round(res.glp, 2),
        "iter_glp_pct_diff": (round((res.glp - pd.glp) / pd.glp * 100, 2) if pd.glp else None),
        "commutation_glp": round(comm_glp, 2),
        "comm_glp_pct_diff": (round((comm_glp - pd.glp) / pd.glp * 100, 2) if pd.glp else None),
        "commutation_gsp": round(comm_gsp, 2),
        "comm_gsp_pct_diff": (round((comm_gsp - pd.gsp) / pd.gsp * 100, 2) if pd.gsp else None),
        "commutation_7pay": round(comm_7pay, 2),
    }, indent=2, default=str))


if __name__ == "__main__":
    main()
