"""Verify the GLP/GSP detail-sheet roll-ups reconcile to the recalc Summary.

Runs a real local policy through a guideline recalc (same driver as
tools/check_guideline_recalc.py) and, for each of GLP/GSP x Before/After,
compares three numbers that the Values-tab detail sheets must agree on:

  * summary   — the engine's solved value shown on the recalc Summary tab
                (glp_before / glp_after / gsp_before / gsp_after);
  * rollup    — the monthly-PV roll-up premium the detail sheet's bottom
                equation displays (guideline_pv rollup["premium"]);
  * row_sum   — the premium re-derived from the SHEET ROWS themselves:
                (S PVDB + S PV Charges + S PV Target Load Diff) / S PV Annuity,
                proving the visible grid arithmetic lands on the same number.

Usage (single JSON arg):
    venv\\Scripts\\python.exe tools/check_recalc_pv_reconcile.py '<json>'

    {"policy":"U0351626","region":"CKPR","company":"01","months":48,
     "change":{"kind":"face_amount","date":"2028-05-26","value":501000}}
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


def _row_sum_premium(detail: dict) -> dict:
    rows = detail.get("glp_rows") or []
    pv_db = sum(r.get("PVDB", 0.0) for r in rows)
    pv_chg = sum(r.get("PV Charges", 0.0) for r in rows)
    pv_load = sum(r.get("PV Target Load Diff", 0.0) for r in rows)
    pv_ann = sum(r.get("PV Annuity", 0.0) for r in rows)
    rollup = detail.get("glp_rollup") or {}
    av0 = rollup.get("starting AV offset") or 0.0
    premium = (pv_db + pv_chg + pv_load - av0) / pv_ann if pv_ann else 0.0
    return {
        "sum PVDB": round(pv_db, 2),
        "sum PV Charges": round(pv_chg, 2),
        "sum PV Target Load Diff": round(pv_load, 2),
        "sum PV Annuity": round(pv_ann, 6),
        "row_sum_premium": round(premium, 2),
    }


def run(cmd: dict) -> dict:
    os.environ["SUITEVIEW_LOCAL_DATA"] = "1"

    from suiteview.core.policy_service import clear_cache
    from suiteview.illustration.core.calc_engine import IllustrationEngine
    from suiteview.illustration.core.illustration_policy_service import build_illustration_data
    from suiteview.illustration.models.input_set import (
        IllustrationInputSet, PolicyChangeEvent, PolicyChangeKind,
    )

    policy = cmd["policy"]
    clear_cache()
    policy_data = build_illustration_data(
        policy, region=cmd.get("region", "CKPR"), company_code=cmd.get("company"))

    change = cmd["change"]
    kind = (PolicyChangeKind.FACE_AMOUNT if change["kind"] == "face_amount"
            else PolicyChangeKind.DB_OPTION)
    value = float(change["value"]) if change["kind"] == "face_amount" else change["value"]
    eff = datetime.date.fromisoformat(change["date"])

    states = IllustrationEngine().project(
        policy_data, months=int(cmd.get("months", 48)),
        future_inputs=IllustrationInputSet(policy_changes=[
            PolicyChangeEvent(kind=kind, effective_date=eff, value=value)]))

    recalc = next((s.guideline_recalc for s in states if s.guideline_recalc), None)
    if not recalc:
        return {
            "policy": policy,
            "error": "no guideline recalc captured",
            "valuation_date": str(policy_data.valuation_date),
            "issue_date": str(policy_data.issue_date),
            "total_face": policy_data.total_face,
            "db_option": policy_data.db_option,
            "projection_start": str(states[0].date) if states else None,
            "projection_end": str(states[-1].date) if states else None,
        }

    pv = recalc.get("monthly_pv_recalc") or {}
    out = {
        "policy": policy,
        "plancode": policy_data.plancode,
        "db_option": policy_data.db_option,
        "change": {"kind": kind.value, "date": eff.isoformat(), "value": value},
        "checks": {},
    }
    worst = 0.0
    for prem, side in (("glp", "before"), ("glp", "after"),
                       ("gsp", "before"), ("gsp", "after")):
        summary = recalc.get(f"{prem}_{side}")
        detail = (pv.get(side) or {}).get(prem) or {}
        rollup = (detail.get("glp_rollup") or {}).get("premium")
        row = _row_sum_premium(detail)
        diffs = [abs((rollup or 0.0) - (summary or 0.0)),
                 abs(row["row_sum_premium"] - (summary or 0.0))]
        worst = max(worst, *diffs)
        out["checks"][f"{prem}_{side}"] = {
            "summary": round(summary, 2) if summary is not None else None,
            "sheet_rollup": rollup,
            **row,
            "db_option": detail.get("db_option"),
        }
    out["worst_abs_diff"] = round(worst, 4)
    out["reconciles"] = worst < 0.01
    return out


def main() -> None:
    if len(sys.argv) < 2:
        print(json.dumps({"error": "missing JSON arg"}))
        sys.exit(1)
    print(json.dumps(run(json.loads(sys.argv[1])), indent=1, default=str))


if __name__ == "__main__":
    main()
