"""Run an indeterminate premium term in-force illustration end to end (read-only).

Loads the policy through PolicyInformation and its rates from schema ``rates``, runs
the engine with the given inputs and prints the annual ledger (current and guaranteed
premiums); ``--pages`` prints the illustration pages and ``--pdf`` writes them to a
landscape PDF, reporting how much of the page width the text fills.

Usage:
    venv\\Scripts\\python.exe tools\\rerun\\run_term_illustration.py D0194819
    venv\\Scripts\\python.exe tools\\rerun\\run_term_illustration.py D0194819 --inputs "{\\"billing_frequency\\": 12}"
    venv\\Scripts\\python.exe tools\\rerun\\run_term_illustration.py D0194819 --pages --pdf out.pdf

``--inputs`` is JSON (or ``@file``) with any TermInputs field: ``billing_frequency``,
``drop_riders`` (coverage phases), ``drop_benefits`` (benefit codes), ``end_age``.
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
from suiteview.illustration.core.term.report import build_term_report  # noqa: E402
from suiteview.illustration.core.term.service import load_term_basis  # noqa: E402
from suiteview.illustration.models.term import TermInputs  # noqa: E402
from suiteview.polview.models.policy_information import PolicyInformation  # noqa: E402


def _inputs(text: str) -> TermInputs:
    if not text:
        return TermInputs()
    raw = json.loads(Path(text[1:]).read_text(encoding="utf-8") if text.startswith("@") else text)
    return TermInputs(**raw)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("policy", help="POLICY or COMPANY:POLICY")
    parser.add_argument("--region", default="CKPR")
    parser.add_argument("--inputs", default="")
    parser.add_argument("--years", type=int, default=100)
    parser.add_argument("--pages", action="store_true", help="print the illustration report pages")
    parser.add_argument("--pdf", help="write the illustration report to this landscape PDF")
    args = parser.parse_args()
    if os.environ.get("SUITEVIEW_LOCAL_DATA") == "1":
        raise RuntimeError("This helper reads live DB2 policy data only.")
    company, _, number = args.policy.rpartition(":")
    basis = load_term_basis(PolicyInformation(number, company_code=company or None, region=args.region),
                            region=args.region)
    result = basis.run(_inputs(args.inputs))
    p = result.policy
    print(f"{p.company_code}:{p.policy_number} {p.base.plancode} issue {p.issue_date} age {p.base.issue_age} "
          f"units {p.base.units} status {p.premium_status} valuation {p.valuation_date}")
    for note in result.notes:
        print("note:", note)
    for y in result.years[: args.years]:
        print(f"{y.policy_year:3} {y.age:3} {y.period:7} current {y.current_premium:12,.2f} "
              f"guaranteed {y.guaranteed_premium:12,.2f} db {y.death_benefit:12,.2f} riders {y.rider_death_benefit:10,.2f}")
    if args.pages or args.pdf:
        report = build_term_report(result, date.today())
        pages = format_ledger_pages(report)
        if args.pages:
            for page_no, lines in enumerate(pages, 1):
                print(f"\n{'=' * 20} page {page_no} (width {report.width}) {'=' * 20}")
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
