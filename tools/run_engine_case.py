"""Run the SuiteView illustration engine on a local policy and dump MonthlyState.

Uses local SQLite data (SUITEVIEW_LOCAL_DATA=1) so it works offline on the
minipc.  Output is one row per projected month (row 0 = inforce snapshot) with
the pipeline-ordered MonthlyState fields, matching the RERUN comparison.

Usage (single JSON arg):
    venv\\Scripts\\python.exe tools/run_engine_case.py '<json>'

    {"policy":"U0688012","region":"CKPR","company":"01","months":120,
     "out_csv":"out.csv",
     "tefra":false,"tamra":true,"exception":false,"exact_days":true}

Option flags mirror the RERUN sINPUT_* booleans (omit to use engine defaults):
  tefra      -> IllustrationOptions.conform_to_tefra
  tamra      -> IllustrationOptions.conform_to_tamra
  exception  -> IllustrationOptions.allow_exception_prems
  exact_days -> IllustrationOptions.exact_days_interest
"""
from __future__ import annotations

import csv
import json
import os
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def main() -> None:
    if len(sys.argv) < 2:
        print(json.dumps({"error": "missing JSON arg"}))
        sys.exit(1)
    cmd = json.loads(sys.argv[1])
    os.environ["SUITEVIEW_LOCAL_DATA"] = "1"

    import datetime

    from suiteview.core.policy_service import clear_cache
    from suiteview.illustration.core.illustration_policy_service import build_illustration_data
    from suiteview.illustration.core.calc_engine import IllustrationEngine
    from suiteview.illustration.models.input_set import (
        IllustrationOptions, IllustrationInputSet, PolicyChangeEvent, PolicyChangeKind,
    )
    from suiteview.illustration.debug.excel_export import _PIPELINE_ORDER, _get_projection_value

    policy = cmd["policy"]
    region = cmd.get("region", "CKPR")
    company = cmd.get("company")
    months = int(cmd.get("months", 120))
    out_csv = cmd.get("out_csv")

    # Per-case option toggles (default to engine defaults when omitted).
    opt_kwargs = {}
    if "tefra" in cmd:
        opt_kwargs["conform_to_tefra"] = bool(cmd["tefra"])
    if "tamra" in cmd:
        opt_kwargs["conform_to_tamra"] = bool(cmd["tamra"])
    if "exception" in cmd:
        opt_kwargs["allow_exception_prems"] = bool(cmd["exception"])
    if "exact_days" in cmd:
        opt_kwargs["exact_days_interest"] = bool(cmd["exact_days"])
    options = IllustrationOptions(**opt_kwargs)

    # Optional policy changes: [{"kind":"face_amount"|"db_option","date":"YYYY-MM-DD","value":...,
    #   "metadata":{"new_glp":...,"new_gsp":...,"new_7pay":...}}]
    # metadata injects RERUN's recalculated guideline values so the AV/segment
    # mechanics validate independently of guideline-calc calibration.
    future_inputs = None
    if cmd.get("changes"):
        evs = []
        for ch in cmd["changes"]:
            kind = (PolicyChangeKind.FACE_AMOUNT if ch["kind"] == "face_amount"
                    else PolicyChangeKind.DB_OPTION)
            value = float(ch["value"]) if ch["kind"] == "face_amount" else ch["value"]
            evs.append(PolicyChangeEvent(
                kind=kind, effective_date=datetime.date.fromisoformat(ch["date"]),
                value=value, metadata=ch.get("metadata") or {}))
        future_inputs = IllustrationInputSet(policy_changes=evs)

    clear_cache()
    policy_data = build_illustration_data(policy, region=region, company_code=company)
    states = IllustrationEngine().project(
        policy_data, months=months, options=options, future_inputs=future_inputs)

    # Guideline/target fields live on MonthlyState but aren't in the debug pipeline order.
    extra = [
        "glp", "gsp", "accumulated_glp", "guideline_limit", "guideline_forceout",
        "monthly_mtp", "ctp", "accumulated_mtp",
        "accumulated_7pay", "amount_in_7pay", "tamra_year", "tamra_7pay_level",
    ]
    fields = list(_PIPELINE_ORDER) + [f for f in extra if f not in _PIPELINE_ORDER]

    def cell(state, fname):
        try:
            return _get_projection_value(state, fname)
        except Exception:
            return None

    rows = []
    for i, state in enumerate(states):
        rec = {"row": i}  # row 0 = inforce snapshot, row 1 = first projected month
        for f in fields:
            rec[f] = cell(state, f)
        rows.append(rec)

    summary = {
        "policy": policy,
        "company": policy_data.company_code,
        "plancode": policy_data.plancode,
        "valuation_date": str(policy_data.valuation_date),
        "issue_date": str(policy_data.issue_date),
        "attained_age": policy_data.attained_age,
        "account_value_start": policy_data.account_value,
        "states": len(states),
        "options": {
            "conform_to_tefra": options.conform_to_tefra,
            "conform_to_tamra": options.conform_to_tamra,
            "allow_exception_prems": options.allow_exception_prems,
            "exact_days_interest": options.exact_days_interest,
        },
        "out_csv": out_csv,
    }

    if out_csv:
        with open(out_csv, "w", newline="", encoding="utf-8") as fh:
            w = csv.writer(fh)
            w.writerow(["row"] + fields)
            for rec in rows:
                w.writerow([rec["row"]] + [rec[f] for f in fields])
    else:
        # Print a compact preview of headline fields for the first 14 rows.
        preview_fields = [
            "date", "policy_year", "duration", "attained_age",
            "gross_premium", "av_after_premium", "total_deduction",
            "av_after_deduction", "interest_credited", "av_end_of_month",
            "surrender_value", "ending_db",
        ]
        summary["preview"] = [
            {"row": r["row"], **{f: r.get(f) for f in preview_fields}}
            for r in rows[:14]
        ]

    print(json.dumps(summary, indent=2, default=str))


if __name__ == "__main__":
    main()
