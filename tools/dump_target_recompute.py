"""Dump MTP/CTP recompute detail around a policy change (local SQLite).

Prints, as JSON:
  * the DB2-sourced inforce MTP/CTP on the policy,
  * compute_target_premiums() run on the UNCHANGED policy (rates-derived
    "before" recompute, with per-coverage / per-benefit components), and
  * the engine's mtp_annual by month around the change (to see what the
    in-engine recompute produced after the mutation).

Usage:
    venv\\Scripts\\python.exe tools/dump_target_recompute.py '<json>'

    {"policy":"U0356726","region":"CKPR","company":"01","months":40,
     "change":{"kind":"db_option","date":"2027-10-01","value":"A"},
     "window":3}
"""
from __future__ import annotations

import datetime
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

os.environ["SUITEVIEW_LOCAL_DATA"] = "1"


def main() -> None:
    cmd = json.loads(sys.argv[1]) if len(sys.argv) > 1 else {}
    policy_num = cmd.get("policy", "U0356726")
    months = int(cmd.get("months", 40))
    window = int(cmd.get("window", 3))
    change = cmd.get("change") or {}

    from suiteview.core.policy_service import clear_cache
    from suiteview.illustration.core.calc_engine import IllustrationEngine
    from suiteview.illustration.core.illustration_policy_service import build_illustration_data
    from suiteview.illustration.core.target_premium import compute_target_premiums
    from suiteview.illustration.models.input_set import (
        IllustrationInputSet, PolicyChangeEvent, PolicyChangeKind,
    )
    from suiteview.illustration.models.plancode_config import load_plancode

    clear_cache()
    policy = build_illustration_data(
        policy_num, region=cmd.get("region", "CKPR"), company_code=cmd.get("company"))
    config = load_plancode(policy.plancode)

    out = {
        "policy": policy_num,
        "plancode": policy.plancode,
        "db2_mtp_annual": policy.mtp * 12.0,
        "db2_ctp_annual": policy.ctp,
        "riders": [
            {"phase": r.coverage_phase, "plancode": r.plancode, "cov_type": r.cov_type,
             "units": r.units, "face": r.face_amount, "active": r.is_active,
             "maturity": str(r.maturity_date), "cease_age_dur": r.cease_age_dur,
             "cease_use_code": r.cease_use_code}
            for r in policy.riders
        ],
        "benefits": [
            {"type": b.benefit_type, "sub": b.benefit_subtype, "units": b.units,
             "active": b.is_active, "cease": str(b.cease_date)}
            for b in policy.benefits
        ],
    }

    before = compute_target_premiums(policy, config, as_of=policy.valuation_date)
    out["recompute_before"] = {
        "mtp_annual": before.mtp_annual,
        "ctp_annual": before.ctp_annual,
        "mtp_by_coverage": before.mtp_by_coverage,
        "mtp_benefits": before.mtp_benefits,
        "mtp_riders": getattr(before, "mtp_riders", None),
        "mtp_wo_pw": before.mtp_wo_pw,
    }

    future = None
    if change:
        kind = (PolicyChangeKind.FACE_AMOUNT if change.get("kind") == "face_amount"
                else PolicyChangeKind.DB_OPTION)
        value = (float(change["value"]) if change.get("kind") == "face_amount"
                 else change["value"])
        eff = datetime.date.fromisoformat(change["date"])
        future = IllustrationInputSet(policy_changes=[
            PolicyChangeEvent(kind=kind, effective_date=eff, value=value)])

    states = IllustrationEngine().project(policy, months=months, future_inputs=future)
    rows = []
    change_idx = None
    if change:
        for i, s in enumerate(states):
            if s.guideline_recalc:
                change_idx = i
                break
    lo = max(0, (change_idx or 0) - window)
    hi = min(len(states), (change_idx or 0) + window + 1)
    for s in states[lo:hi]:
        rows.append({
            "duration": s.duration, "date": str(s.date),
            "mtp_annual": s.mtp_annual, "monthly_mtp": s.monthly_mtp,
            "accumulated_mtp": s.accumulated_mtp,
            "total_sa": getattr(s, "total_face", None),
        })
    out["months_around_change"] = rows
    print(json.dumps(out, indent=1, default=str))


if __name__ == "__main__":
    main()
