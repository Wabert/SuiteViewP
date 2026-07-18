"""End-to-end check of the Loan Pay-off solver against a local policy.

Loads a policy from the local SQLite data (SUITEVIEW_LOCAL_DATA=1), builds the
modal repayment dates for a Pay-off window, solves the level repayment with
the real engine, then re-projects with the solved repayments layered in and
reports the loan balance at (and around) the window end — it should be zero
just before any new loan that follows.

Usage (single JSON arg):
    venv\\Scripts\\python.exe tools/check_loan_payoff_solve.py '<json>'

    {"policy":"S0503261","region":"CKPR","start_year":null,"years":5,
     "mode":"A","new_loan_year":null,"new_loan_amount":0}

start_year defaults to the policy year after the current one (no forecast
clamping needed). new_loan_year (optional) schedules a fixed loan starting
that policy year to demonstrate the payoff clearing the balance just before
new borrowing begins.
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

_MODE_INTERVALS = {"M": 1, "Q": 3, "S": 6, "A": 12}


def main() -> None:
    os.environ["SUITEVIEW_LOCAL_DATA"] = "1"
    cmd = json.loads(sys.argv[1]) if len(sys.argv) > 1 else {}

    from dateutil.relativedelta import relativedelta

    from suiteview.core.policy_service import clear_cache
    from suiteview.illustration.core.calc_engine import IllustrationEngine
    from suiteview.illustration.core.illustration_policy_service import build_illustration_data
    from suiteview.illustration.core.solve_loan_payoff import (
        PAYOFF_SUBTYPE, solve_loan_payoff,
    )
    from suiteview.illustration.models.input_set import (
        DatedTransaction, IllustrationInputSet, ScheduledTransaction, TransactionKind,
    )

    policy_number = cmd.get("policy", "S0503261")
    region = cmd.get("region", "CKPR")
    years = int(cmd.get("years", 5))
    mode = cmd.get("mode", "A")
    interval = _MODE_INTERVALS.get(mode, 12)

    clear_cache()
    policy = build_illustration_data(policy_number, region=region,
                                     company_code=cmd.get("company"))
    current_year = policy.duration // 12 + 1
    start_year = int(cmd.get("start_year") or current_year + 1)
    end_year = start_year + years - 1

    dates = []
    for year in range(start_year, end_year + 1):
        anniversary = policy.issue_date + relativedelta(years=year - 1)
        for k in range(0, 12, interval):
            dates.append(anniversary + relativedelta(months=k))
    check_date = policy.issue_date + relativedelta(years=end_year)

    base = None
    new_loan_year = cmd.get("new_loan_year")
    if new_loan_year and float(cmd.get("new_loan_amount") or 0) > 0:
        base = IllustrationInputSet(scheduled_transactions=[
            ScheduledTransaction(kind=TransactionKind.LOAN,
                                 policy_year=int(new_loan_year),
                                 amount=float(cmd["new_loan_amount"]), mode="A",
                                 metadata={"loan_type": "fixed"}),
        ])

    engine = IllustrationEngine()
    result = solve_loan_payoff(
        policy, repayment_dates=dates, check_date=check_date,
        base_future_inputs=base, base_options=None, engine=engine)

    # Re-project with the solved repayments layered in, past the check date.
    dated = [DatedTransaction(kind=TransactionKind.LOAN_REPAYMENT,
                              effective_date=d, amount=result.repayment,
                              subtype=PAYOFF_SUBTYPE) for d in dates]
    future = IllustrationInputSet(
        scheduled_transactions=list(base.scheduled_transactions) if base else [],
        dated_transactions=dated)
    horizon = (check_date.year - policy.issue_date.year) * 12 \
        + (check_date.month - policy.issue_date.month) - policy.duration + 13
    states = engine.project(policy, months=max(horizon, 1),
                            future_inputs=future, stop_on_lapse=False)

    def begin_balance(s):
        return round(s.rg_loan_princ + s.rg_loan_accrued + s.pf_loan_princ
                     + s.pf_loan_accrued + s.vbl_loan_princ + s.vbl_loan_accrued, 2)

    window = [s for s in states if s.date is not None
              and check_date + relativedelta(months=-2) <= s.date
              <= check_date + relativedelta(months=2)]
    print(json.dumps({
        "policy": policy_number,
        "plancode": policy.plancode,
        "starting_policy_debt": round(policy.total_loan_principal
                                      + policy.total_loan_accrued, 2)
        if hasattr(policy, "total_loan_principal") else None,
        "window": {"start_year": start_year, "end_year": end_year, "mode": mode,
                   "payments": len(dates), "first": str(dates[0]),
                   "last": str(dates[-1]), "check_date": str(check_date)},
        "solved_repayment": result.repayment,
        "residual_balance": result.residual_balance,
        "iterations": result.iterations,
        "months_around_check": [
            {"date": str(s.date),
             "begin_loan_after_repay": begin_balance(s),
             "applied_repayment": round(s.applied_loan_repayment, 2),
             "new_loan": round(s.applied_new_loan, 2),
             "end_policy_debt": round(s.policy_debt, 2)}
            for s in window],
    }, indent=2, default=str))


if __name__ == "__main__":
    main()
