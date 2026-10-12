"""Run an ISWL reduced paid-up in-force illustration end to end (read-only).

Loads the policy through PolicyInformation (the app's load path), runs the in-force
checks and the engine, and prints the starting cash value against PolView's NSP cash
value, the NSP schedule, the findings and the annual ledger; ``--pages`` prints the
illustration pages and ``--pdf`` writes them to a landscape PDF.

Usage:
    venv\\Scripts\\python.exe tools\\rerun\\run_iswl_rpu_illustration.py 11663262
    venv\\Scripts\\python.exe tools\\rerun\\run_iswl_rpu_illustration.py 01:12287387 --end-age 90 --pages
"""
from __future__ import annotations

import argparse
import os
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from suiteview.illustration.core.iswl_rpu.report import build_iswl_rpu_report  # noqa: E402
from suiteview.illustration.core.iswl_rpu.service import load_iswl_rpu_basis  # noqa: E402
from suiteview.illustration.core.ledger_report import format_ledger_pages  # noqa: E402
from suiteview.illustration.core.parwl.nsp import function_code_text  # noqa: E402
from suiteview.illustration.models.iswl_rpu import ISWLRPUInputs  # noqa: E402
from suiteview.polview.models.policy_information import PolicyInformation  # noqa: E402


def _money(value) -> str:
    return "n/a" if value is None else f"{value:,.2f}"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("policy", help="POLICY or COMPANY:POLICY")
    parser.add_argument("--region", default="CKPR")
    parser.add_argument("--end-age", type=int)
    parser.add_argument("--years", type=int, default=100)
    parser.add_argument("--pages", action="store_true", help="print the illustration report pages")
    parser.add_argument("--pdf", help="write the illustration report to this landscape PDF")
    args = parser.parse_args()
    if os.environ.get("SUITEVIEW_LOCAL_DATA") == "1":
        raise RuntimeError("This helper reads live DB2 policy data only.")
    company, _, number = args.policy.rpartition(":")
    basis = load_iswl_rpu_basis(PolicyInformation(number, company_code=company or "01", region=args.region),
                                region=args.region)
    p = basis.policy
    print(f"{p.company_code}:{p.policy_number} {p.plancode} issue {p.issue_date} age {p.issue_age} units {p.units} "
          f"VPU {p.value_per_unit} face {p.face_amount:,.2f} maturity {p.maturity_date} (age {p.maturity_age})")
    print(f"  NSP basis {p.nsp_table} (ETI {p.eti_table}) {p.nsp_interest:.4%}  "
          f"MTL_FUN_CD {function_code_text(p.mortality_function_code)}  LOW_DUR_PER {p.low_duration} "
          f"stored {p.stored_nsp}  valuation {p.valuation_date}  PolView NSP CV {_money(p.polview_cash_value)}")
    if p.run_block:
        print("  RUN REFUSED:", p.run_block)
    for check in basis.checks():
        diff = "" if check.difference is None else f" diff {check.difference:+.6f}"
        print(f"  [{check.status:7}] {check.area:13} {check.item}: CyberLife {check.cyberlife} "
              f"calc {check.calculated}{diff}")
    if p.run_block:
        return 1
    result = basis.run(ISWLRPUInputs(end_age=args.end_age))
    start = result.months[0]
    print(f"  start {start.when} CV {start.cash_value:,.2f} (PolView {_money(p.polview_cash_value)}), "
          f"comparison {_money(start.comparison_cash_value)}, DB {start.death_benefit:,.2f}")
    for note in result.notes:
        print("  note:", note)
    for warning in result.warnings:
        print("  WARNING:", warning)
    print("  NSP schedule (duration, age, source, carry, per $1,000 used, endowment NSP):")
    for v in result.schedule:
        print(f"    {v.duration:3} {v.age:3} {v.anniversary} {v.source:8} {v.carry:14,.6f} {v.per_unit:10,.2f} "
              f"{_money(v.comparison):>10}")
    print("  Year Age  End date    NSP/1000   CV (CyberLife)  Comparison CV  Difference  Death benefit  Frozen")
    for y in result.years[: args.years]:
        print(f"  {y.policy_year:4} {y.age:3} {y.end_date} {y.nsp:10,.2f} {y.cash_value:15,.2f} "
              f"{_money(y.comparison_cash_value):>14} {_money(y.difference):>11} {y.death_benefit:14,.2f}  "
              f"{'yes' if y.frozen else ''}")
    if args.pages or args.pdf:
        report = build_iswl_rpu_report(result, date.today())
        pages = format_ledger_pages(report)
        if args.pages:
            for page_no, lines in enumerate(pages, 1):
                print(f"\n{'=' * 20} page {page_no} (width {report.width}) {'=' * 20}")
                print("\n".join(lines))
        if args.pdf:
            from PyQt6.QtWidgets import QApplication

            from suiteview.illustration.ui.report_pages import fitting_font_pt, write_pages_pdf

            app = QApplication.instance() or QApplication([])  # noqa: F841 - fonts need an application
            write_pages_pdf(pages, args.pdf, fitting_font_pt(report.width))
            print(f"PDF: {args.pdf} ({len(pages)} pages)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
