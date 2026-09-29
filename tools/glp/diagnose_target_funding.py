"""Read-only GLP target funding diagnostics, including the failed solve bracket."""
from __future__ import annotations

import argparse
import json
import sys
from datetime import date
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from suiteview.polview.services.policy_service import get_policy_info
from suiteview.polview.services import guideline_exception_adjustment as gea


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--policy", required=True)
    parser.add_argument("--company", default="01")
    parser.add_argument("--target", required=True)
    parser.add_argument("--quote", default=None, help="Quote date (default: today)")
    args = parser.parse_args()
    quote = date.fromisoformat(args.quote) if args.quote else date.today()
    source = get_policy_info(args.policy, company_code=args.company, use_cache=False)
    basis = gea._prepare_projection(source, date.fromisoformat(args.target), quote)
    policy, months = basis.policy, basis.months_to_target
    output = {
        "policy": {key: getattr(policy, key) for key in (
            "policy_number", "plancode", "issue_date", "valuation_date", "duration",
            "policy_year", "policy_month", "account_value", "billing_frequency",
            "modal_premium", "glp", "gsp", "accumulated_glp", "premiums_paid_to_date",
            "withdrawals_to_date", "regular_loan_principal",
        )},
        "interim": basis.interim,
        "interim_unavailable_reason": basis.interim_unavailable_reason,
        "months": months,
        "solves": [],
    }
    original_solve = gea.solve_level_to_exception

    def trace_solve(basis, **kwargs):
        engine = kwargs["engine"]
        original_project = engine.project
        trace = {
            "glp": basis.glp, "horizon": kwargs["horizon_months"],
            "single_premium": kwargs.get("single_premium", False),
            "floor": kwargs.get("first_month_premium_floor", 0),
            "forceouts": kwargs["base_options"].guideline_forceouts,
            "projections": [],
        }
        output["solves"].append(trace)

        def trace_project(*project_args, **project_kwargs):
            states = original_project(*project_args, **project_kwargs)
            future = project_kwargs["future_inputs"]
            trace["projections"].append({
                "scheduled": [t.amount for t in future.scheduled_transactions],
                "dated": [t.amount for t in future.dated_transactions],
                "rows": [{key: getattr(state, key) for key in (
                    "date", "lapsed", "av_after_premium", "av_end_of_month",
                    "ending_sv", "surrender_charge", "policy_debt", "total_deduction",
                    "applied_scheduled_premium", "applied_lumpsum", "gp_exception_prem",
                    "guideline_limit", "guideline_forceout",
                )} for state in states],
            })
            return states

        try:
            with patch.object(engine, "project", trace_project):
                solved = original_solve(basis, **kwargs)
            trace["premium"] = solved.premium
            return solved
        finally:
            trace["projection_count"] = len(trace["projections"])
            trace["projections"] = trace["projections"][:2] + trace["projections"][-1:]

    try:
        with patch.object(gea, "solve_level_to_exception", trace_solve):
            gea.project_guideline_exception_target_forecast(
                source, date.fromisoformat(args.target), quote_date=quote)
        output["all_ok"] = True
    except ValueError as exc:
        output["all_ok"] = False
        output["error"] = str(exc)
    print(json.dumps(output, indent=2, default=str))
    return 0 if output["all_ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
