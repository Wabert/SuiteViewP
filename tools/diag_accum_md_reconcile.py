"""Reconcile the batch "Accum Level to MD" total with the RERUN "Premiums In"
KPI for one policy.

The batch tool (`run_glp_limit_batch2.py`) sums premium via `_future_premium`,
which iterates EVERY state returned by ``engine.project`` and adds
``applied_loan_repayment``. The RERUN Values Overview KPI
(``values_overview.display``) sums ``s.premium_outlay`` over ``results[1:]``
only — it drops the inforce snapshot row (``results[0]``) and does NOT add loan
repayment.

This script runs the exact "Billable to MD" scenario for a policy and prints
both summations side by side, plus the snapshot-row premium and the maturity
row, so the ~$100 discrepancy can be localized.

Usage:
    venv\\Scripts\\python.exe tools/diag_accum_md_reconcile.py POLICY [--company 01]
        [--region CKPR] [--lumpsum-to-next]
"""
from __future__ import annotations

import argparse
import json
import sys
from copy import deepcopy
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("policy")
    ap.add_argument("--company", default=None)
    ap.add_argument("--region", default="CKPR")
    ap.add_argument("--lumpsum-to-next", action="store_true")
    ap.add_argument("--dump-year", type=int, default=None,
                    help="print monthly detail for this policy year")
    args = ap.parse_args()

    from dataclasses import replace

    from suiteview.illustration.core.batch_runner import _billable_to_md_run
    from suiteview.illustration.core.calc_engine import IllustrationEngine
    from suiteview.illustration.core.illustration_policy_service import (
        build_illustration_data,
    )
    from suiteview.illustration.core.solve_lumpsum_to_next_premium import (
        LUMPSUM_SUBTYPE, solve_lumpsum_to_next_premium,
    )
    from suiteview.illustration.models.input_set import (
        DatedTransaction, IllustrationInputSet, TransactionKind,
    )

    engine = IllustrationEngine()
    policy = build_illustration_data(
        args.policy, region=args.region, company_code=args.company)

    future, options = _billable_to_md_run(policy)

    bridge_amount = None
    if args.lumpsum_to_next:
        lump = solve_lumpsum_to_next_premium(
            deepcopy(policy), base_future_inputs=future,
            base_options=options, engine=engine)
        if lump is not None and lump.lumpsum > 0:
            bridge_amount = lump.lumpsum
            future = IllustrationInputSet(
                scheduled_transactions=list(future.scheduled_transactions),
                dated_transactions=list(future.dated_transactions) + [
                    DatedTransaction(
                        kind=TransactionKind.PREMIUM,
                        effective_date=lump.forecast_date,
                        amount=lump.lumpsum, subtype=LUMPSUM_SUBTYPE)],
                policy_changes=list(future.policy_changes))
            options = replace(
                options, billable_to_md_no_latch_before=lump.next_premium_date)

    states = engine.project(
        deepcopy(policy), options=options, future_inputs=future,
        stop_on_lapse=True)

    snapshot = states[0]
    projected = states[1:]

    sum_all_outlay = sum(float(s.premium_outlay) for s in states)
    sum_proj_outlay = sum(float(s.premium_outlay) for s in projected)
    sum_all_loanrepay = sum(
        float(getattr(s, "applied_loan_repayment", 0.0) or 0.0) for s in states)
    batch_total = round(sum_all_outlay + sum_all_loanrepay, 2)   # _future_premium
    rerun_total = round(sum_proj_outlay, 2)                      # RERUN KPI

    last = states[-1]
    switch = next((s for s in states if getattr(s, "billable_md_switched", False)), None)
    first_exc = next((s for s in states if getattr(s, "gp_exception_prem", 0.0) > 0), None)

    # Annual premium_outlay by policy year, to compare against the RERUN
    # "Contributions" column row by row.
    by_year: dict[int, float] = {}
    for s in projected:
        by_year[s.policy_year] = by_year.get(s.policy_year, 0.0) + float(s.premium_outlay)
    annual = {yr: round(v, 2) for yr, v in sorted(by_year.items())}

    months_dump = None
    if args.dump_year is not None:
        months_dump = []
        for s in projected:
            if s.policy_year != args.dump_year:
                continue
            months_dump.append({
                "date": str(s.date), "mo": s.policy_month,
                "premium_outlay": round(float(s.premium_outlay), 2),
                "gross_premium": round(float(getattr(s, "gross_premium", 0.0)), 2),
                "md_premium": round(float(getattr(s, "md_premium", 0.0)), 2),
                "md_capped": bool(getattr(s, "md_premium_capped", False)),
                "gp_exception_prem": round(float(getattr(s, "gp_exception_prem", 0.0)), 2),
                "forceout": round(float(getattr(s, "guideline_forceout", 0.0)), 2),
                "switched": bool(getattr(s, "billable_md_switched", False)),
            })

    report = {
        "policy": args.policy,
        "region": args.region,
        "valuation_date": str(policy.valuation_date),
        "bridge_amount": bridge_amount,
        "n_states": len(states),
        "n_projected": len(projected),
        "snapshot_row": {
            "date": str(snapshot.date),
            "duration": snapshot.duration,
            "premium_outlay": round(float(snapshot.premium_outlay), 2),
            "loan_repay": round(float(getattr(snapshot, "applied_loan_repayment", 0.0) or 0.0), 2),
        },
        "maturity_row": {
            "date": str(last.date),
            "attained_age": last.attained_age,
            "matured": bool(getattr(last, "matured", False)),
            "lapsed": bool(last.lapsed),
            "premium_outlay": round(float(last.premium_outlay), 2),
        },
        "md_switch": None if switch is None else {
            "date": str(switch.date), "policy_year": switch.policy_year,
            "attained_age": switch.attained_age,
        },
        "first_gp_exception": None if first_exc is None else {
            "date": str(first_exc.date), "policy_year": first_exc.policy_year,
        },
        "annual_premium_outlay": annual,
        "months_dump": months_dump,
        "sums": {
            "batch _future_premium (all states + loan repay)": batch_total,
            "RERUN KPI (projected premium_outlay only)": rerun_total,
            "sum premium_outlay ALL states": round(sum_all_outlay, 2),
            "sum premium_outlay PROJECTED only": round(sum_proj_outlay, 2),
            "sum loan_repay ALL states": round(sum_all_loanrepay, 2),
            "diff (RERUN - batch)": round(rerun_total - batch_total, 2),
        },
    }
    print(json.dumps(report, indent=2, default=str))


if __name__ == "__main__":
    main()
