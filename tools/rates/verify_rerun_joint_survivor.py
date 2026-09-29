"""Read-only check that RERUN illustrates the joint survivor (second-to-die) ULs.

For every in-force company-26 joint survivor policy (the 12 FFL plans), loads
the policy through RERUN's ``build_illustration_data`` and:

* runs the valuation month (month 0) and compares the engine's COI, expense
  and total monthly deduction with CyberLife's recorded LH_POL_MVRY_VAL charges;
* projects current and guaranteed values to maturity, recording failures.

Nothing is written to DB2 or UL_Rates. Stdout carries aggregates only;
``output`` writes per-policy detail.

Keys: ``policies`` (default: every in-force joint policy), ``region``, ``output``.
Single-phase policies also get an at-issue 7702 check: the from-issue GLP/GSP/
7-pay solved on the guaranteed joint COI basis vs CyberLife's recorded values
(comparable only when the face hasn't changed since issue).

Usage (venv\\Scripts\\python.exe):
    tools\\rates\\verify_rerun_joint_survivor.py '{"output": "<report.json>"}'
    tools\\rates\\verify_rerun_joint_survivor.py '{"policies": ["000335148"], "output": "..."}'
"""

from __future__ import annotations

import collections
import copy
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from suiteview.core.json_store import write_json  # noqa: E402
from suiteview.core.local_dev import local_data_enabled  # noqa: E402
from suiteview.illustration.core.calc_engine import IllustrationEngine  # noqa: E402
from suiteview.illustration.core.guaranteed_projection import (  # noqa: E402
    run_guaranteed_projection,
)
from suiteview.illustration.core.illustration_policy_service import (  # noqa: E402
    build_illustration_data,
)
from suiteview.illustration.core.scenario_builder import (  # noqa: E402
    prepare_policy_for_issue_projection,
)
from verify_polview_joint_survivor import in_force_phases  # noqa: E402

CENT = 0.005


def check_policy(number: str, company: str, region: str) -> dict:
    policy = build_illustration_data(number, region=region, company_code=company)
    if not policy.is_joint_survivor:
        raise RuntimeError("RERUN did not load the policy as joint survivor")
    engine = IllustrationEngine()
    month0 = engine.project(policy, months=0)[0]
    result = {
        "policy": number, "plancode": policy.plancode, "segments": len(policy.segments),
        "rated": any(seg.joint_lives.ratings for seg in policy.segments),
        "benefits": sorted({b.benefit_type + b.benefit_subtype for b in policy.benefits}),
        "valuation_date": str(policy.valuation_date),
        "system_coi": round(policy.system_coi_charge, 2),
        "calc_coi": round(month0.total_coi_charge, 2),
        "system_md": round(policy.system_monthly_deduction, 2),
        "calc_md": round(month0.md_check_calculated_deduction, 2),
        "system_expense": round(policy.system_expense_charge, 2),
        "calc_mfee": round(month0.mfee_charge, 2),
        "calc_benefits": round(month0.benefit_charges, 2),
    }
    result["coi_ok"] = abs(result["system_coi"] - result["calc_coi"]) < CENT
    result["md_ok"] = abs(result["system_md"] - result["calc_md"]) < CENT
    # CyberLife stores no surrender value for UL (MVRY CSV_AMT is the AV), so the
    # surrender charge is reported for review, not compared.
    result["calc_sc"] = round(month0.surrender_charge, 2)
    if len(policy.segments) == 1:
        # Unchanged since issue: the from-issue 7702 solve on the guaranteed
        # joint COI basis should reproduce CyberLife's recorded values.
        issue = prepare_policy_for_issue_projection(copy.deepcopy(policy))
        engine.project(issue, months=0)
        for name, record, calc in (("glp", policy.glp, issue.glp), ("gsp", policy.gsp, issue.gsp),
                                   ("7pay", policy.tamra_7pay_level, issue.tamra_7pay_level)):
            result[f"record_{name}"] = round(record, 2)
            result[f"issue_{name}"] = round(calc, 2)
        result["db_option"] = policy.db_option
        result["dli"] = policy.def_of_life_ins
        result["face"] = round(policy.segments[0].face_amount, 2)
        result["original_face"] = round(policy.segments[0].original_face_amount, 2)
    current = engine.project(policy)
    guaranteed = run_guaranteed_projection(policy, current, engine=engine)
    for label, states in (("current", current), ("guaranteed", guaranteed)):
        last = states[-1]
        result[f"{label}_months"] = len(states)
        result[f"{label}_last_date"] = str(last.date)
        result[f"{label}_last_av"] = round(float(last.av_end_of_month or 0.0), 2)
        result[f"{label}_lapsed"] = bool(last.lapsed)
    return result


def main() -> None:
    arg = sys.argv[1] if len(sys.argv) > 1 else "{}"
    config = json.loads(Path(arg[1:]).read_text(encoding="utf-8-sig")) if arg.startswith("@") else json.loads(arg)
    if local_data_enabled():
        raise RuntimeError("This verification requires live data, not SUITEVIEW_LOCAL_DATA.")
    region = config.get("region", "CKPR")
    wanted = set(config.get("policies") or [])
    policies = sorted({(number, company) for number, company, _, _ in in_force_phases(region)
                       if not wanted or number in wanted})
    details, stats, errors = [], collections.Counter(), collections.Counter()
    for number, company in policies:
        try:
            result = check_policy(number, company, region)
            stats["coi_ok" if result["coi_ok"] else "coi_differs"] += 1
            stats["md_ok" if result["md_ok"] else "md_differs"] += 1
        except Exception as exc:  # reported, never hidden
            result = {"policy": number, "error": f"{type(exc).__name__}: {exc}"}
            errors[f"{type(exc).__name__}: {str(exc)[:120]}"] += 1
        details.append(result)
    summary = {
        "policies": len(details), "stats": dict(stats), "errors": dict(errors),
        "md_differences": [
            {k: d.get(k) for k in ("plancode", "rated", "benefits", "system_coi", "calc_coi",
                                   "system_md", "calc_md", "system_expense", "calc_mfee",
                                   "calc_benefits")}
            for d in details if "error" not in d and not d["md_ok"]
        ][:30],
        "surrender_charges": [
            {k: d.get(k) for k in ("plancode", "calc_sc")}
            for d in details if d.get("calc_sc")
        ],
        "issue_7702": [
            {k: d.get(k) for k in ("plancode", "db_option", "dli", "record_glp", "issue_glp",
                                   "record_gsp", "issue_gsp", "record_7pay", "issue_7pay")}
            for d in details if "issue_glp" in d
        ],
    }
    print(json.dumps(summary, indent=2, default=str))
    if config.get("output"):
        write_json(config["output"], {"summary": summary, "details": details})


if __name__ == "__main__":
    main()
