"""Verify the indeterminate premium term engine against live CyberLife values (read-only).

For each policy: load it through PolicyInformation, load its schema ``rates``, run the
in-force checks (premium per unit, renewal rate, table extras, modal premium) and a
projection, and print one line per check plus a summary.

Usage:
    venv\\Scripts\\python.exe tools\\rerun\\verify_term_inforce.py D0194819 --ledger 40
    venv\\Scripts\\python.exe tools\\rerun\\verify_term_inforce.py --file policies.txt --summary-only --json-out out.json

A policy argument may be ``COMPANY:POLICY`` (e.g. ``26:NLP00116``).
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

from suiteview.illustration.core.term.service import load_term_basis  # noqa: E402
from suiteview.polview.models.policy_information import PolicyInformation  # noqa: E402


def _policies(args) -> list:
    items = list(args.policies)
    if args.file:
        items += [line.split("#")[0].strip() for line in Path(args.file).read_text(encoding="utf-8").splitlines()
                  if line.split("#")[0].strip()]
    return items


def verify(item: str, region: str, ledger: int, summary_only: bool) -> dict:
    company, _, number = item.rpartition(":")
    pi = PolicyInformation(number, company_code=company or None, region=region)
    if pi.available_companies:
        return {"policy": item, "error": f"in companies {pi.available_companies}; use COMPANY:POLICY"}
    basis = load_term_basis(pi, region=region)
    policy = basis.policy
    checks = basis.checks()
    try:
        result, run_error = basis.run(), ""
    except Exception as exc:  # a refused projection still reports its checks
        result, run_error = None, f"{type(exc).__name__}: {exc}"
    counts = Counter(c.status for c in checks)
    if not summary_only:
        base = policy.base
        print(f"== {policy.company_code}:{policy.policy_number} {base.plancode} {base.form_number} issue "
              f"{policy.issue_date} age {base.issue_age} {base.rate_sex}/{base.rate_class} units {base.units} "
              f"status {policy.premium_status} mode {policy.billing_frequency}/{policy.bill_form} billed "
              f"{policy.modal_premium} valuation {policy.valuation_date} paid to {policy.paid_to_date} "
              f"level {base.initial_renewal_period} next change {base.next_change_date}")
        for check in checks:
            diff = "" if check.difference is None else f" diff {check.difference:+.4f}"
            print(f"   [{check.status:7}] {check.area:11} {check.item}: CyberLife {check.cyberlife} "
                  f"calc {check.calculated}{diff}  {check.detail}")
        if run_error:
            print("   run refused:", run_error)
        for note in (result.notes if result else []):
            print("   note:", note)
        for year in (result.years[:ledger] if result else []):
            print(f"   yr {year.policy_year:3} age {year.age:3} {year.period:7} current {year.current_premium:12,.2f} "
                  f"guaranteed {year.guaranteed_premium:12,.2f} db {year.death_benefit:12,.2f} "
                  f"riders {year.rider_death_benefit:10,.2f}")
    return {"policy": item, "plancode": policy.base.plancode, "status": policy.premium_status,
            "mode": policy.billing_frequency, **{k: counts.get(k, 0) for k in ("match", "differs", "info")},
            "run_error": run_error,
            "diff_items": [f"{c.area}: {c.item} ({c.cyberlife} vs {c.calculated})" for c in checks
                           if c.status == "differs"],
            "info_items": [f"{c.area}: {c.item} ({c.cyberlife} vs {c.calculated}) {c.detail[:80]}" for c in checks
                           if c.status == "info"]}


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
            print(f"   {r['policy']:14} {r['plancode']:9} st {r['status']} mode {r['mode']:2} "
                  f"match {r['match']:3} differs {r['differs']:3} info {r['info']:3}"
                  + (" RUN REFUSED" if r.get("run_error") else "")
                  + ("" if not r["diff_items"] else "  | " + "; ".join(r["diff_items"][:4])))
    if args.json_out:
        Path(args.json_out).write_text(json.dumps(results, indent=1, default=str), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
