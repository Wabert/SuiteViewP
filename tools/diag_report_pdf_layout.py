"""Diagnose illustration-report PDF pagination.

Rebuilds the exact QTextDocument write_pdf produces, lays it out against the
printer's page rect, and reports page height, font line spacing, and lines per
formatted page — to size LEDGER_ROWS_PER_PAGE / font so no page overflows.

Usage: venv\\Scripts\\python.exe tools/diag_report_pdf_layout.py
"""
from __future__ import annotations

import json
import sys
from html import escape
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from PyQt6.QtCore import QMarginsF, QSizeF  # noqa: E402
from PyQt6.QtGui import QFont, QFontMetricsF, QPageLayout, QPageSize, QTextDocument  # noqa: E402
from PyQt6.QtPrintSupport import QPrinter  # noqa: E402
from PyQt6.QtWidgets import QApplication  # noqa: E402

from suiteview.illustration.ui.report_tab import format_report_pages  # noqa: E402
from tools.verify_report_pdf_pages import build_report  # noqa: E402


def main() -> int:
    app = QApplication.instance() or QApplication(sys.argv)  # noqa: F841
    printer = QPrinter(QPrinter.PrinterMode.HighResolution)
    printer.setOutputFormat(QPrinter.OutputFormat.PdfFormat)
    printer.setOutputFileName("NUL")
    printer.setPageSize(QPageSize(QPageSize.PageSizeId.Letter))
    printer.setPageOrientation(QPageLayout.Orientation.Landscape)
    printer.setPageMargins(QMarginsF(0.6, 0.5, 0.6, 0.5), QPageLayout.Unit.Inch)

    page_rect = printer.pageRect(QPrinter.Unit.DevicePixel)
    dpi = printer.resolution()
    font = QFont("Courier New", 9)
    metrics = QFontMetricsF(font, printer)

    report = build_report()
    pages = format_report_pages(report)

    document = QTextDocument()
    document.setDefaultFont(font)
    parts = []
    for index, lines in enumerate(pages):
        style = ("font-family:'Courier New',monospace; font-size:9pt;"
                 " white-space:pre; margin:0;")
        if index < len(pages) - 1:
            style += " page-break-after:always;"
        body = "<br/>".join(escape(line) for line in lines)
        parts.append(f'<pre style="{style}">{body}</pre>')
    document.setHtml("".join(parts))
    document.setPageSize(QSizeF(page_rect.size()))

    result = {
        "dpi": dpi,
        "page_rect_px": [page_rect.width(), page_rect.height()],
        "page_height_pt": page_rect.height() / dpi * 72,
        "page_width_pt": page_rect.width() / dpi * 72,
        "line_spacing_pt": metrics.lineSpacing() / dpi * 72,
        "char_width_pt": metrics.horizontalAdvance("0") / dpi * 72,
        "line_width_112_pt": metrics.horizontalAdvance("0" * 112) / dpi * 72,
        "doc_margin_px": document.documentMargin(),
        "formatted_pages": len(pages),
        "lines_per_page": [len(p) for p in pages],
        "doc_page_count": document.pageCount(),
        "max_lines_that_fit": int(
            (page_rect.height() - 2 * document.documentMargin())
            // metrics.lineSpacing()),
    }
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    main()
