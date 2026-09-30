"""Run a par whole life in-force illustration end to end and print the ledger (read-only).

Loads the policy through PolicyInformation, its rates from schema ``rates``, runs the
engine with the given inputs and prints the in-force checks, notes and the annual
ledger (and optionally the monthly rows).

Usage:
    venv\\Scripts\\python.exe tools\\rerun\\run_parwl_illustration.py 26:000282131
    venv\\Scripts\\python.exe tools\\rerun\\run_parwl_illustration.py 01:E0017485 --inputs "{\\"rpu_at\\": \\"2031-09-25\\"}"
    venv\\Scripts\\python.exe tools\\rerun\\run_parwl_illustration.py 01:E0017485 --inputs @inputs.json --months 24
    venv\\Scripts\\python.exe tools\\rerun\\run_parwl_illustration.py 26:000282131 --pages --pdf out.pdf

``--pages`` prints the illustration report pages; ``--pdf`` writes them to a landscape PDF.

``--inputs`` is JSON (or ``@file``) with any ParWLInputs field: ``dividends``,
``dividend_option``, ``secondary_option``, ``option_changes`` ([{"when", "option",
"secondary"}]), ``rpu_at``, ``loans`` / ``loan_repayments`` / ``rider_payments``
([{"when", "amount"}]), ``pay_loan_interest``, ``deposit_rate``, ``end_age``.
Dates are ISO (YYYY-MM-DD).
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from suiteview.illustration.core.ledger_report import format_ledger_pages  # noqa: E402
from suiteview.illustration.core.parwl.report import build_parwl_report  # noqa: E402
from suiteview.illustration.core.parwl.service import load_parwl_basis  # noqa: E402
from suiteview.illustration.models.parwl import DatedAmount, OptionChange, ParWLInputs  # noqa: E402
from suiteview.polview.models.policy_information import PolicyInformation  # noqa: E402


def _inputs(text: str) -> ParWLInputs:
    if not text:
        return ParWLInputs()
    raw = json.loads(Path(text[1:]).read_text(encoding="utf-8") if text.startswith("@") else text)
    day = date.fromisoformat
    kwargs = dict(raw)
    for key in ("loans", "loan_repayments", "rider_payments"):
        if key in kwargs:
            kwargs[key] = [DatedAmount(day(item["when"]), float(item["amount"])) for item in kwargs[key]]
    if "option_changes" in kwargs:
        kwargs["option_changes"] = [OptionChange(day(c["when"]), c["option"], c.get("secondary", ""))
                                    for c in kwargs["option_changes"]]
    if kwargs.get("rpu_at"):
        kwargs["rpu_at"] = day(kwargs["rpu_at"])
    return ParWLInputs(**kwargs)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("policy", help="POLICY or COMPANY:POLICY")
    parser.add_argument("--region", default="CKPR")
    parser.add_argument("--inputs", default="")
    parser.add_argument("--months", type=int, default=0, help="print this many monthly rows")
    parser.add_argument("--years", type=int, default=100)
    parser.add_argument("--pages", action="store_true", help="print the illustration report pages")
    parser.add_argument("--pdf", help="write the illustration report to this landscape PDF")
    args = parser.parse_args()
    if os.environ.get("SUITEVIEW_LOCAL_DATA") == "1":
        raise RuntimeError("This helper reads live DB2 policy data only.")
    company, _, number = args.policy.rpartition(":")
    basis = load_parwl_basis(PolicyInformation(number, company_code=company or None, region=args.region),
                             region=args.region)
    result = basis.run(_inputs(args.inputs))
    p = result.policy
    print(f"{p.company_code}:{p.policy_number} {p.base.plancode} issue {p.issue_date} age {p.base.issue_age} "
          f"units {p.base.units} status {p.premium_status} option {p.dividend_option} valuation {p.valuation_date}")
    for note in result.notes:
        print("note:", note)
    for m in result.months[: args.months]:
        print(f"  {m.when} y{m.policy_year:3} m{m.month_of_year:2} prem {m.premium_paid:9,.2f} div {m.dividend_total:9,.2f}"
              f" adds {m.additions:11,.2f} addcv {m.additions_cv:10,.2f} cv {m.base_cv:10,.2f} dep {m.deposits:9,.2f}"
              f" loan {m.loan_payoff:10,.2f} csv {m.surrender_value:11,.2f} db {m.death_benefit:12,.2f} {m.notes}")
    print(f"{'yr':>3} {'age':>3} {'premium':>10} {'dividend':>9} {'g csv':>11} {'g db':>12} {'additions':>11}"
          f" {'deposits':>10} {'loan':>10} {'csv':>11} {'db':>12}")
    for y in result.years[: args.years]:
        print(f"{y.policy_year:3} {y.age:3} {y.premium:10,.2f} {y.dividend:9,.2f} {y.guaranteed_cash_value:11,.2f}"
              f" {y.guaranteed_death_benefit:12,.2f} {y.additions:11,.2f} {y.deposits:10,.2f} {y.loan_balance:10,.2f}"
              f" {y.surrender_value:11,.2f} {y.death_benefit:12,.2f}{' RPU' if y.rpu else ''}")
    if args.pages or args.pdf:
        report = build_parwl_report(result, date.today())
        pages = format_ledger_pages(report)
        if args.pages:
            for number, lines in enumerate(pages, 1):
                print(f"\n{'=' * 20} page {number} (width {report.width}) {'=' * 20}")
                print("\n".join(lines))
        if args.pdf:
            from PyQt6.QtPrintSupport import QPrinter
            from PyQt6.QtWidgets import QApplication

            from suiteview.illustration.ui.report_pages import (
                fitting_font_pt,
                pages_document,
                pdf_printer,
                write_pages_pdf,
            )

            app = QApplication.instance() or QApplication([])  # noqa: F841 - fonts need an application
            font = fitting_font_pt(report.width)
            printer = pdf_printer(args.pdf)
            ratio = pages_document(pages, printer, font).idealWidth() / printer.pageRect(QPrinter.Unit.DevicePixel).width()
            write_pages_pdf(pages, args.pdf, font)
            print(f"PDF: {args.pdf} ({len(pages)} pages, {report.width} characters at {font}pt, "
                  f"text fills {ratio:.1%} of the page width)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
