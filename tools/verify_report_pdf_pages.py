"""Verify the illustration report PDF paginates and scales correctly.

Builds a synthetic IllustrationReport (60 ledger rows), writes it to a PDF via
IllustrationReportTab.write_pdf, and checks:
  - the number of /Page objects matches the formatted page count (guards the
    Qt <pre>-block page-break bug where every line got its own PDF page),
  - the MediaBox is landscape,
  - the laid-out text fills most of the printable width (guards the DPI
    mismatch where the document laid out at 96dpi against a 1200dpi page rect
    and printed at ~1/12 scale).

Usage: venv\\Scripts\\python.exe tools/verify_report_pdf_pages.py [out.pdf]
An optional output path keeps the generated PDF for visual inspection.
"""
from __future__ import annotations

import json
import re
import sys
import tempfile
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from PyQt6.QtWidgets import QApplication  # noqa: E402

from suiteview.illustration.core.report_builder import (  # noqa: E402
    IllustrationReport,
    LedgerRow,
)
from suiteview.illustration.ui.report_tab import (  # noqa: E402
    IllustrationReportTab,
    format_report_pages,
)


def build_report() -> IllustrationReport:
    report = IllustrationReport(
        company_name="AMERICAN NATIONAL INSURANCE COMPANY",
        prepared_for="PREPARED FOR JOHN DOE",
        run_date=date(2026, 7, 3),
        insured_lines=["JOHN DOE", "MALE ISSUE AGE 35"],
        agent_lines=["JANE AGENT", "AGENCY 123"],
        policy_block=[("POLICY NUMBER: U0000001", "PLAN: FLEX UL"),
                      ("", ""),
                      ("FACE AMOUNT: 100,000", "ISSUE DATE: 01/01/2000")],
        disclaimer_lines=["THIS ILLUSTRATION IS HYPOTHETICAL AND NOT A CONTRACT. " * 3],
        request_intro=["THIS ILLUSTRATION WAS PRODUCED AT YOUR REQUEST USING:"],
        request_lines=["ANNUAL PREMIUM OF 1,200.00 IN ALL YEARS"],
        footnote_legends=["* PREMIUM CHANGE"],
        note_paragraphs=[["NOTES ABOUT THE ILLUSTRATION. " * 5]],
        rider_lines=["WAIVER OF PREMIUM RIDER"],
        as_of_date=date(2026, 7, 3),
        regulatory_lines=["GUIDELINE ANNUAL PREMIUM: 2,000.00"],
        has_guaranteed_values=True,
    )
    for year in range(1, 61):
        report.ledger.append(LedgerRow(
            eoy_age=35 + year, year=year, premium_outlay=1200.0,
            cash_from_policy=0.0, loan_balance=0.0,
            guar_accum=1000.0 * year, guar_surr=900.0 * year,
            guar_death=100000.0,
            accum_value=1100.0 * year, surr_value=1000.0 * year,
            death_benefit=100000.0,
        ))
    report.maturity_row = LedgerRow(
        guar_accum=0.0, guar_surr=0.0, guar_death=0.0,
        accum_value=66000.0, surr_value=60000.0, death_benefit=60000.0)
    return report


def count_pdf_pages(pdf_bytes: bytes) -> int:
    # Count leaf page objects: /Type /Page not followed by 's' (i.e. not /Pages).
    return len(re.findall(rb"/Type\s*/Page(?![a-zA-Z])", pdf_bytes))


def main() -> int:
    app = QApplication.instance() or QApplication(sys.argv)  # noqa: F841
    report = build_report()
    expected = len(format_report_pages(report))
    with tempfile.TemporaryDirectory() as tmp:
        pdf_path = sys.argv[1] if len(sys.argv) > 1 else str(Path(tmp) / "illustration.pdf")

        # Layout-scale check on the same document write_pdf prints.
        from PyQt6.QtPrintSupport import QPrinter
        printer = IllustrationReportTab._pdf_printer(pdf_path)
        document = IllustrationReportTab._print_document(report, printer)
        page_width = printer.pageRect(QPrinter.Unit.DevicePixel).width()
        width_ratio = document.idealWidth() / page_width
        doc_pages = document.pageCount()

        IllustrationReportTab.write_pdf(report, pdf_path)
        pdf_bytes = Path(pdf_path).read_bytes()
        pdf_pages = count_pdf_pages(pdf_bytes)

    box = re.search(
        rb"/MediaBox\s*\[\s*[\d.]+\s+[\d.]+\s+([\d.]+)\s+([\d.]+)\s*\]", pdf_bytes)
    width, height = (float(box.group(1)), float(box.group(2))) if box else (0.0, 0.0)
    result = {
        "expected_pages": expected,
        "doc_pages": doc_pages,
        "pdf_pages": pdf_pages,
        "media_box": [width, height],
        "landscape": width > height,
        "width_ratio": round(width_ratio, 3),
        "ok": (pdf_pages == expected and doc_pages == expected
               and width > height and 0.6 < width_ratio <= 1.0),
    }
    print(json.dumps(result))
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
