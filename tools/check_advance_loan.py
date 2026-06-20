"""Validate interest-in-advance loan handling on a local policy.

Projects the engine with an optional loan repayment and prints the RERUN
"Loan Capitalize and Repay" detail per month so the advance-loan mechanics
(anniversary capitalization + repayment gross-up) can be eyeballed against the
RERUN CalcEngine columns.

Usage:
    venv\\Scripts\\python.exe tools/check_advance_loan.py '{"policy":"S0503261","months":18,"repay":{"date":"2026-XX-XX","amount":600}}'
    venv\\Scripts\\python.exe tools/check_advance_loan.py '{"policy":"S0503261","months":18}'

If no repay date is given, a repayment is placed 3 monthliversaries after the
valuation date.
"""
from __future__ import annotations

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
    policy_num = cmd.get("policy", "S0503261")
    months = int(cmd.get("months", 18))

    from dateutil.relativedelta import relativedelta

    from suiteview.core.policy_service import clear_cache
    from suiteview.illustration.core.calc_engine import (
        IllustrationEngine, _advance_loan_factors, _days_to_next_anniversary)
    from suiteview.illustration.core.illustration_policy_service import build_illustration_data
    from suiteview.illustration.models.plancode_config import load_plancode
    from suiteview.illustration.models.input_set import (
        DatedTransaction, IllustrationInputSet, TransactionKind)

    clear_cache()
    policy = build_illustration_data(policy_num, region=cmd.get("region", "CKPR"),
                                     company_code=cmd.get("company"))
    config = load_plancode(policy.plancode)

    repay = cmd.get("repay") or {}
    if repay.get("date"):
        import datetime
        repay_date = datetime.date.fromisoformat(repay["date"])
    else:
        repay_date = (policy.valuation_date + relativedelta(months=3))
    repay_amount = float(repay.get("amount", 600.0))

    inputs = IllustrationInputSet(dated_transactions=[
        DatedTransaction(kind=TransactionKind.LOAN_REPAYMENT,
                         effective_date=repay_date, amount=repay_amount),
    ])

    states = IllustrationEngine().project(policy, months=months, future_inputs=inputs)

    header = {
        "policy": policy_num,
        "plancode": policy.plancode,
        "loan_type": config.loan_type,
        "lncrg": config.loan_charge_rate_guar,
        "pref_lncrg": config.pref_loan_charge_rate_guar,
        "issue_date": str(policy.issue_date),
        "valuation_date": str(policy.valuation_date),
        "seed_reg_loan_principal": policy.regular_loan_principal,
        "seed_pref_loan_principal": policy.preferred_loan_principal,
        "repay_date": str(repay_date),
        "repay_amount": repay_amount,
    }
    print(json.dumps(header, indent=2, default=str))

    cols = [
        ("date", "date"),
        ("LX RgPrincTot", "Advance - Rg Ln Princ/Total"),
        ("MD RegPayoff", "Advance - Adv Reg LN Payoff"),
        ("MF Payoff", "Advance - LoanPayoff"),
        ("MN Requested", "Arrears - Requested Loan Repayment"),
        ("MP RegRepay", "Advance - Adv Reg LN Repay"),
        ("MR TotRepay", "Advance - Adv Total Loan Repayment"),
        ("MZ TotReduc", "TotalLoanReduction"),
        ("MS RgPrinc", "Rg Ln Princ"),
        ("NA PolDebt", "PolicyDebtDisplay"),
    ]
    head = ["mo", "anniv", "daysNext", "X"] + [c[0] for c in cols[1:]]
    widths = [4, 6, 9, 8] + [15] * (len(cols) - 1)
    print("  ".join(h.ljust(w) for h, w in zip(head, widths)))

    for i, s in enumerate(states):
        d = dict(s.loan_cap_repay or {})
        days = _days_to_next_anniversary(policy.issue_date, s.date) if s.date else 0
        x = _advance_loan_factors(config, days)[0]
        vals = [
            str(i),
            "Y" if s.is_anniversary else "",
            str(days),
            f"{x:.5f}",
        ]
        for _label, key in cols[1:]:
            if key == "Rg Ln Princ":
                v = s.rg_loan_princ
            elif key == "PolicyDebtDisplay":
                # NA = sum of post-repay buckets (computed in the Values tab).
                v = (s.rg_loan_princ + s.rg_loan_accrued + s.pf_loan_princ
                     + s.pf_loan_accrued + s.vbl_loan_princ + s.vbl_loan_accrued)
            else:
                v = d.get(key, 0.0)
            try:
                vals.append(f"{float(v):,.2f}")
            except (TypeError, ValueError):
                vals.append(str(v))
        print("  ".join(val.ljust(w) for val, w in zip(vals, widths)))


if __name__ == "__main__":
    main()
