"""Run a live ISWL policy through RERUN's Run Values pipeline and print its ledger, read-only.

Usage: venv\\Scripts\\python.exe tools\\rerun\\run_iswl_illustration.py <policy> [company]
       [--years 12] [--output ledger.json]

``execute_run`` (current projection, guaranteed projection and report) is called with the
billed premium at the billing mode to maturity, as the Inputs tab defaults. The annual
ledger is printed in the layout of CyberDoc B10's sample Interest Sensitive Life
Illustration: age, year, contract premium, then guaranteed and non-guaranteed
accumulated value, surrender value and death benefit (end-of-year values).
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from suiteview.core.local_dev import local_data_enabled

_MODE = {1: "M", 3: "Q", 6: "S", 12: "A"}


def _year_end(states) -> dict:
    """Annual rows keyed by policy year: premium paid in the year and year-end values."""
    rows: dict = {}
    for state in states[1:]:
        row = rows.setdefault(state.policy_year, {"age": state.attained_age, "premium": 0.0})
        row["premium"] += state.gross_premium
        row.update(av=state.av_end_of_month, sv=state.ending_sv, db=state.ending_db,
                   gcv=state.guaranteed_cash_value, lapsed=state.lapsed)
        row["age"] = state.attained_age + (1 if state.policy_month == 12 else 0)
    return rows


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("policy")
    parser.add_argument("company", nargs="?")
    parser.add_argument("--years", type=int, default=0, help="print only the first N years")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    if local_data_enabled():
        raise RuntimeError("This helper reads live data only.")
    from suiteview.illustration.api import load_policy_data
    from suiteview.illustration.core.calc_engine import projection_month_count
    from suiteview.illustration.core.run_service import (
        PolicyBasis, RunControls, RunRequest, SolveRequestSet, execute_run,
    )
    from suiteview.illustration.models.input_set import (
        IllustrationInputSet, IllustrationOptions, ScheduledTransaction, TransactionKind,
    )

    policy = load_policy_data(args.policy, company_code=args.company)
    mode = _MODE.get(int(policy.billing_frequency or 1), "M")
    inputs = IllustrationInputSet(scheduled_transactions=[ScheduledTransaction(
        TransactionKind.PREMIUM, policy.policy_year, float(policy.modal_premium), mode=mode)])
    request = RunRequest(
        basis=PolicyBasis(policy.policy_number, company_code=policy.company_code, policy_data=policy),
        inputs=inputs,
        controls=RunControls(options=IllustrationOptions(),
                             projection_months=projection_month_count(policy, None),
                             duration_label="Maturity", stop_on_lapse=True),
        solves=SolveRequestSet(),
    )
    result = execute_run(request)
    current, guaranteed = _year_end(result.current), _year_end(result.guaranteed or [])
    header = {
        "policy": policy.policy_number, "plancode": policy.plancode, "issue_age": policy.issue_age,
        "face": policy.face_amount, "billed_premium": policy.modal_premium, "mode": mode,
        "account_value": policy.account_value, "valuation_date": str(policy.valuation_date),
        "current_interest_rate": policy.current_interest_rate,
        "current_interest_rate_source": policy.current_interest_rate_source,
        "report_built": result.report.report is not None,
        "guaranteed_error": result.report.guaranteed_error, "status": result.status,
    }
    print(json.dumps(header, default=str))
    print(f"{'AGE':>4} {'YR':>3} {'PREMIUM':>9} | {'G AV':>10} {'G SV':>10} {'G DB':>10} | "
          f"{'C AV':>10} {'C SV':>10} {'C DB':>10}")
    ledger = []
    for year in sorted(current)[: args.years or None]:
        cur, gua = current[year], guaranteed.get(year, {})
        ledger.append({"year": year, "current": cur, "guaranteed": gua})
        print(f"{cur['age']:>4} {year:>3} {cur['premium']:>9,.2f} | "
              f"{gua.get('av', 0):>10,.0f} {gua.get('sv', 0):>10,.0f} {gua.get('db', 0):>10,.0f} | "
              f"{cur['av']:>10,.0f} {cur['sv']:>10,.0f} {cur['db']:>10,.0f}")
    if args.output:
        args.output.write_text(json.dumps({"header": header, "ledger": ledger}, indent=1, default=str),
                               encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
