"""Verify the par WL engine against live CyberLife in-force values (read-only).

For each policy: load it through PolicyInformation, load its schema ``rates``, run the
in-force checks (premium, cash values, RPU NSP, dividends, additions, loan) and a
projection, and print one line per check plus a summary.

Usage:
    venv\\Scripts\\python.exe tools\\rerun\\verify_parwl_inforce.py 000282131 15906121
    venv\\Scripts\\python.exe tools\\rerun\\verify_parwl_inforce.py --file policies.txt --summary-only
    venv\\Scripts\\python.exe tools\\rerun\\verify_parwl_inforce.py 000282131 --ledger 10

A policy argument may be ``COMPANY:POLICY`` (e.g. ``26:000282131``).
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import traceback
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from suiteview.illustration.core.parwl.service import load_parwl_basis  # noqa: E402
from suiteview.polview.models.policy_information import PolicyInformation  # noqa: E402


def _policies(args) -> list:
    items = list(args.policies)
    if args.file:
        items += [line.strip() for line in Path(args.file).read_text(encoding="utf-8").splitlines() if line.strip()]
    return items


def verify(item: str, region: str, ledger: int, summary_only: bool) -> dict:
    company, _, number = item.rpartition(":")
    pi = PolicyInformation(number, company_code=company or None, region=region)
    if pi.available_companies:
        return {"policy": item, "error": f"in companies {pi.available_companies}; use COMPANY:POLICY"}
    basis = load_parwl_basis(pi, region=region)
    policy = basis.policy
    checks = basis.checks()
    result = basis.run()
    counts = Counter(c.status for c in checks)
    if not summary_only:
        print(f"== {policy.company_code}:{policy.policy_number} {policy.base.plancode} "
              f"issue {policy.issue_date} age {policy.base.issue_age} {policy.base.rate_sex}/{policy.base.rate_class} "
              f"units {policy.base.units} status {policy.premium_status} option {policy.dividend_option}/"
              f"{policy.secondary_dividend_option} valuation {policy.valuation_date}")
        for check in checks:
            diff = "" if check.difference is None else f" diff {check.difference:+.4f}"
            print(f"   [{check.status:7}] {check.area:10} {check.item}: CyberLife {check.cyberlife} "
                  f"calc {check.calculated}{diff}  {check.detail}")
        for note in result.notes:
            print("   note:", note)
        for year in result.years[:ledger]:
            print(f"   yr {year.policy_year:3} age {year.age:3} prem {year.premium:10,.2f} div {year.dividend:9,.2f} "
                  f"adds {year.additions:11,.2f} csv {year.surrender_value:11,.2f} gcsv {year.guaranteed_cash_value:11,.2f} "
                  f"db {year.death_benefit:12,.2f} loan {year.loan_balance:10,.2f} dep {year.deposits:9,.2f}")
    return {"policy": item, "plancode": policy.base.plancode, "status": policy.premium_status,
            "option": policy.dividend_option, **{k: counts.get(k, 0) for k in ("match", "differs", "info")},
            "diff_items": [f"{c.area}: {c.item} ({c.cyberlife} vs {c.calculated})" for c in checks
                           if c.status == "differs"]}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("policies", nargs="*")
    parser.add_argument("--file")
    parser.add_argument("--region", default="CKPR")
    parser.add_argument("--ledger", type=int, default=5)
    parser.add_argument("--summary-only", action="store_true")
    parser.add_argument("--json-out")
    args = parser.parse_args()
    if os.environ.get("SUITEVIEW_LOCAL_DATA") == "1":
        raise RuntimeError("This helper reads live DB2 policy data only.")
    results = []
    for item in _policies(args):
        try:
            results.append(verify(item, args.region, args.ledger, args.summary_only))
        except Exception as exc:  # report every policy; one failure must not stop the batch
            results.append({"policy": item, "error": f"{type(exc).__name__}: {exc}"})
            if not args.summary_only:
                traceback.print_exc()
    print("\n== summary")
    for r in results:
        if "error" in r:
            print(f"   {r['policy']:14} ERROR {r['error']}")
        else:
            print(f"   {r['policy']:14} {r['plancode']:9} st {r['status']} opt {r['option']} "
                  f"match {r['match']:3} differs {r['differs']:3} info {r['info']:3}"
                  + ("" if not r["diff_items"] else "  | " + "; ".join(r["diff_items"][:4])))
    if args.json_out:
        Path(args.json_out).write_text(json.dumps(results, indent=1, default=str), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
