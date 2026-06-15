"""Run the SuiteView illustration engine on a local policy and dump MonthlyState.

Uses local SQLite data (SUITEVIEW_LOCAL_DATA=1) so it works offline on the
minipc.  Output is one row per projected month (row 0 = inforce snapshot) with
the pipeline-ordered MonthlyState fields, matching the RERUN comparison.

Usage (single JSON arg):
    venv\\Scripts\\python.exe tools/run_engine_case.py '<json>'

    {"policy":"U0688012","region":"CKPR","company":"01","months":120,
     "out_csv":"out.csv",
     "tefra":false,"tamra":true,"exception":false,"exact_days":true,
     "premiums":[{"year":1,"amount":25000,"mode":"A"}],
     "withdrawals":[{"date":"2029-11-09","amount":1000}],
     "loans":[{"year":12,"amount":3000},{"year":16,"amount":0}]}

Scheduled premiums REPLACE the policy's billed premium from the given policy
year on (mirrors overriding RERUN's vINPUT_Premium_Amount/_Mode vectors); the
engine still caps at acceptance per the TEFRA/TAMRA toggles. Withdrawals are
dated (RERUN takes them at the anniversary — use the anniversary date).
Loans are annual schedules by policy year; a schedule persists until the next
entry, so end a finite run with a 0-amount year (RERUN vINPUT_Loans rows).

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


def run_engine_case(cmd: dict) -> dict:
    """Run the engine for one case; return {"summary", "fields", "rows"}.

    Sets SUITEVIEW_LOCAL_DATA=1 before importing engine modules so the local
    SQLite path is used.  Callers (e.g. tools/compare_rerun_vs_app.py) import and
    call this directly; main() wraps it for the CLI + CSV output.
    """
    os.environ["SUITEVIEW_LOCAL_DATA"] = "1"

    import datetime

    from suiteview.core.policy_service import clear_cache
    from suiteview.illustration.core.illustration_policy_service import build_illustration_data
    from suiteview.illustration.core.calc_engine import IllustrationEngine
    from suiteview.illustration.models.input_set import (
        DatedTransaction, IllustrationOptions, IllustrationInputSet,
        PolicyChangeEvent, PolicyChangeKind, ScheduledTransaction, TransactionKind,
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
    if "gp_search" in cmd:
        opt_kwargs["guideline_by_search"] = bool(cmd["gp_search"])
    options = IllustrationOptions(**opt_kwargs)

    # Optional policy changes: [{"kind":"face_amount"|"db_option","date":"YYYY-MM-DD","value":...,
    #   "metadata":{"new_glp":...,"new_gsp":...,"new_7pay":...}}]
    # metadata injects RERUN's recalculated guideline values so the AV/segment
    # mechanics validate independently of guideline-calc calibration.
    future_inputs = None
    if any(cmd.get(k) for k in ("changes", "premiums", "withdrawals", "loans")):
        evs = []
        for ch in cmd.get("changes") or []:
            kind = (PolicyChangeKind.FACE_AMOUNT if ch["kind"] == "face_amount"
                    else PolicyChangeKind.DB_OPTION)
            value = float(ch["value"]) if ch["kind"] == "face_amount" else ch["value"]
            evs.append(PolicyChangeEvent(
                kind=kind, effective_date=datetime.date.fromisoformat(ch["date"]),
                value=value, metadata=ch.get("metadata") or {}))
        # Scheduled premiums: [{"year":1,"amount":25000,"mode":"A"}] — replaces
        # the billed premium from that policy year on (RERUN premium-vector
        # override equivalent). Loans use the same year-schedule semantics.
        scheds = [
            ScheduledTransaction(
                kind=TransactionKind.PREMIUM,
                policy_year=int(p["year"]),
                amount=float(p["amount"]),
                mode=p.get("mode", "A"))
            for p in cmd.get("premiums") or []
        ] + [
            ScheduledTransaction(
                kind=TransactionKind.LOAN,
                policy_year=int(ln["year"]),
                amount=float(ln["amount"]),
                mode=ln.get("mode", "A"),
                metadata={"loan_type": ln["type"]} if ln.get("type") else {})
            for ln in cmd.get("loans") or []
        ]
        dated = [
            DatedTransaction(
                kind=TransactionKind.WITHDRAWAL,
                effective_date=datetime.date.fromisoformat(wd["date"]),
                amount=float(wd["amount"]))
            for wd in cmd.get("withdrawals") or []
        ]
        future_inputs = IllustrationInputSet(
            scheduled_transactions=scheds, dated_transactions=dated,
            policy_changes=evs)

    clear_cache()
    policy_data = build_illustration_data(policy, region=region, company_code=company)
    # Optional shadow seed override: the current shadow account value at the
    # valuation date.  Locally the DB2 source is unconfirmed (gav is null), so the
    # comparison feeds RERUN's sInput_CurrentShadowAV here so both sides start from
    # the same value.  In production this comes from policy_data.shadow_account_value.
    if cmd.get("shadow_av") is not None:
        policy_data.shadow_account_value = float(cmd["shadow_av"])
    states = IllustrationEngine().project(
        policy_data, months=months, options=options, future_inputs=future_inputs)

    # Guideline/target fields live on MonthlyState but aren't in the debug pipeline order.
    extra = [
        "glp", "gsp", "accumulated_glp", "guideline_limit", "guideline_forceout",
        "monthly_mtp", "ctp", "accumulated_mtp", "mtp_annual",
        "accumulated_7pay", "amount_in_7pay", "tamra_year", "tamra_7pay_level",
        "premium_cap", "premium_capped",
        # Withdrawal block (CalcEngine AX..BU)
        "input_withdrawal", "max_net_withdrawal", "applied_net_withdrawal",
        "withdrawals_ytd", "wd_corridor_amount", "wd_reduces_sa",
        "wd_partial_sc", "gross_withdrawal", "av_post_withdrawal",
        "wd_face_decrease", "cost_basis_after_wd",
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
        "has_shadow_account": policy_data.has_shadow_account,
        "shadow_account_value": policy_data.shadow_account_value,
        "base_total_face": policy_data.total_face,
        "riders": [
            {"plancode": r.plancode, "face": r.face_amount, "issue_age": r.issue_age,
             "sex": r.rate_sex, "maturity": str(r.maturity_date), "status": r.status,
             "cov_phase": r.coverage_phase}
            for r in policy_data.riders
        ],
        "states": len(states),
        "options": {
            "conform_to_tefra": options.conform_to_tefra,
            "conform_to_tamra": options.conform_to_tamra,
            "allow_exception_prems": options.allow_exception_prems,
            "exact_days_interest": options.exact_days_interest,
        },
        "out_csv": out_csv,
    }

    return {"summary": summary, "fields": fields, "rows": rows}


def main() -> None:
    if len(sys.argv) < 2:
        print(json.dumps({"error": "missing JSON arg"}))
        sys.exit(1)
    cmd = json.loads(sys.argv[1])
    result = run_engine_case(cmd)
    summary, fields, rows = result["summary"], result["fields"], result["rows"]
    out_csv = cmd.get("out_csv")

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
