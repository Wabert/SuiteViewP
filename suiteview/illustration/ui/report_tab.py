"""Illustration Report tab — renders the UL illustration pages.

Print-preview style: white fixed-width "sheets" stacked on the purple
Illustration background, formatted from the structured
``IllustrationReport`` (core/report_builder.py). Mirrors RERUN's
"UL - Illustration Pages" layout. Print to PDF renders the same fixed-width
pages through Qt's PDF printer in landscape, sized so the 112-character lines
fill the page width.
"""
from __future__ import annotations

from html import escape
from typing import List, Optional

from PyQt6.QtCore import QMarginsF, QSizeF, Qt, QUrl
from PyQt6.QtGui import QDesktopServices, QFont, QPageLayout, QPageSize, QTextDocument
from PyQt6.QtPrintSupport import QPrinter
from PyQt6.QtWidgets import (
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from suiteview.illustration.core.report_builder import IllustrationReport, LedgerRow
from .styles import PURPLE_BG, PURPLE_DARK, PURPLE_LIGHT

PAGE_WIDTH = 112          # characters
# Rows per ledger page — bounded by the landscape PDF page height (Letter
# landscape at 10pt Courier holds ~46 text lines inside the margins).
LEDGER_ROWS_PER_PAGE = 30


def _center(text: str) -> str:
    return text[:PAGE_WIDTH].center(PAGE_WIDTH).rstrip()


def _money(value: Optional[float]) -> str:
    """Ledger money: whole dollars, floored at 0 (RERUN); None renders blank."""
    return "" if value is None else f"{max(value, 0.0):,.0f}"


class _PageBuilder:
    """Accumulates fixed-width lines for one report page."""

    def __init__(self, report: IllustrationReport, page_no: int, total: int):
        self.lines: List[str] = []
        run = report.run_date.strftime("%m/%d/%Y") if report.run_date else ""
        left, right = run, f"Page {page_no} of {total}"
        middle = report.company_name
        pad = PAGE_WIDTH - len(left) - len(right)
        self.lines.append(left + middle.center(max(pad, len(middle))) + right)
        self.lines.append(_center(report.title))
        self.lines.append(_center(report.prepared_for))
        self.lines.append("")

    def blank(self, count: int = 1):
        self.lines.extend([""] * count)

    def add(self, text: str = ""):
        self.lines.append(text[:PAGE_WIDTH])

    def add_centered(self, text: str):
        self.lines.append(_center(text))

    def add_wrapped(self, text: str):
        words = text.split()
        line = ""
        for word in words:
            if line and len(line) + 1 + len(word) > PAGE_WIDTH:
                self.lines.append(line)
                line = word
            else:
                line = f"{line} {word}".strip()
        if line:
            self.lines.append(line)


_LEDGER_HEADER = [
    f"{'':4}{'END':>5}{'':>11}{'':5}{'CASH':>8}{'':>10}  "
    f"{'+- GUARANTEED VALUES -+':^32}  {'+ NON-GUARANTEED VALUES +':^32}",
    f"{'':4}{'OF':>5}{'PREMIUM':>11}{'':5}{'FROM':>8}{'LOAN':>10}  "
    f"{'ACCUM':>10}{'SURR':>10}{'DEATH':>12}  {'ACCUM':>10}{'SURR':>10}{'DEATH':>12}",
    f"{'AGE':>4}{'YEAR':>5}{'OUTLAY':>11}{'':5}{'POLICY':>8}{'BALANCE':>10}  "
    f"{'VALUE':>10}{'VALUE':>10}{'BENEFIT':>12}  {'VALUE':>10}{'VALUE':>10}{'BENEFIT':>12}",
    "-" * PAGE_WIDTH,
]


def _ledger_line(row: LedgerRow) -> str:
    return (
        f"{row.eoy_age:>4}{row.year:>5}{row.premium_outlay:>11,.0f}"
        f"{row.markers:>5}{row.cash_from_policy:>8,.0f}{row.loan_balance:>10,.0f}  "
        f"{_money(row.guar_accum):>10}{_money(row.guar_surr):>10}{_money(row.guar_death):>12}  "
        f"{_money(row.accum_value):>10}{_money(row.surr_value):>10}{_money(row.death_benefit):>12}"
    )


def _maturity_line(row: LedgerRow) -> str:
    """VALUES AT MATURITY strip — value columns aligned with the ledger."""
    return (
        f"{'VALUES AT MATURITY':<45}"
        f"{_money(row.guar_accum):>10}{_money(row.guar_surr):>10}{_money(row.guar_death):>12}  "
        f"{_money(row.accum_value):>10}{_money(row.surr_value):>10}{_money(row.death_benefit):>12}"
    )


def format_report_pages(report: IllustrationReport) -> List[List[str]]:
    """Format the structured report into pages of fixed-width text lines."""
    ledger_chunks: List[List[LedgerRow]] = []
    rows = report.ledger
    for start in range(0, len(rows), LEDGER_ROWS_PER_PAGE):
        ledger_chunks.append(rows[start:start + LEDGER_ROWS_PER_PAGE])
    if not ledger_chunks:
        ledger_chunks = [[]]
    total = 2 + len(ledger_chunks) + (1 if _has_rider_page(report) else 0)

    pages: List[List[str]] = []

    # ── Page 1: cover ──
    cover = _PageBuilder(report, 1, total)
    for line in report.disclaimer_lines:
        cover.add_wrapped(line)
    cover.blank()
    # Insured block on the left, agent block on the right (when present).
    insured = report.insured_lines or [""]
    left_lines = [f"  INSURED: {insured[0]}"]
    left_lines += [f"           {extra}" for extra in insured[1:]]
    agent = report.agent_lines
    right_lines = ([f"AGENT: {agent[0]}"] + [f"       {extra}" for extra in agent[1:]]) if agent else []
    for index in range(max(len(left_lines), len(right_lines))):
        left = left_lines[index] if index < len(left_lines) else ""
        right = right_lines[index] if index < len(right_lines) else ""
        cover.add(f"{left:<58}{right}".rstrip() if right else left)
    cover.blank()
    # Two-column policy block: ("", "") pairs are blank separator rows.
    for left, right in report.policy_block:
        if not left and not right:
            cover.blank()
        else:
            cover.add(f"  {left:<40}{right}".rstrip())
    cover.blank()
    if report.av_basis_line:
        cover.add_wrapped(report.av_basis_line)
        if report.loan_basis_line:
            cover.add_wrapped(report.loan_basis_line)
        cover.blank()
    for line in report.request_intro:
        cover.add_wrapped(line)
    cover.blank()
    for line in report.request_lines:
        cover.add(f"    {line}")
    if report.change_sections:
        cover.blank()
        for section in report.change_sections:
            when = section.effective_date.strftime("%m/%d/%Y") if section.effective_date else ""
            cover.add_wrapped(
                f"THE FOLLOWING POLICY CHANGES WERE FORECASTED ON {when} (YEAR {section.year})")
            for line in section.summary_lines:
                cover.add(f"    {line}")
            cover.blank()
    if report.mec_line:
        cover.blank()
        cover.add_wrapped(report.mec_line)
    pages.append(cover.lines)

    # ── Ledger pages ──
    for index, chunk in enumerate(ledger_chunks):
        page = _PageBuilder(report, 2 + index, total)
        page.lines.extend(_LEDGER_HEADER)
        base = index * LEDGER_ROWS_PER_PAGE
        for row_index, row in enumerate(chunk):
            page.add(_ledger_line(row))
            # RERUN groups the ledger into blocks of five rows.
            if (base + row_index + 1) % 5 == 0 and row_index + 1 < len(chunk):
                page.blank()
        if index == len(ledger_chunks) - 1:
            if report.maturity_row is not None:
                page.blank()
                page.add("-" * PAGE_WIDTH)
                page.add(_maturity_line(report.maturity_row))
                page.add("-" * PAGE_WIDTH)
            if report.footnote_legends:
                page.blank()
                for legend in report.footnote_legends:
                    page.add_wrapped(legend)
        pages.append(page.lines)

    # ── Notes page ──
    notes = _PageBuilder(report, 2 + len(ledger_chunks), total)
    for paragraph in report.note_paragraphs:
        for line in paragraph:
            notes.add_wrapped(line) if line else notes.blank()
        notes.blank()
    if report.exception_section:
        notes.blank()
        for line in report.exception_section:
            notes.add_wrapped(line) if line else notes.blank()
    pages.append(notes.lines)

    # ── Riders / regulatory page ──
    if _has_rider_page(report):
        riders = _PageBuilder(report, total, total)
        riders.add("POLICY RIDERS AND BENEFITS AND REGULATORY PREMIUM (IF APPLICABLE)")
        riders.blank()
        as_of = report.as_of_date.strftime("%m/%d/%Y") if report.as_of_date else ""
        riders.add(f"RIDERS AND BENEFITS ACTIVE ON THE POLICY AS OF {as_of}:")
        for line in report.rider_lines:
            riders.add(f"    {line}")
        if report.regulatory_lines:
            riders.blank()
            riders.add(f"REGULATORY LIMITS FOR PREMIUMS AS OF {as_of} ARE AS FOLLOWS:")
            for line in report.regulatory_lines:
                riders.add(f"    {line}")
        for section in report.change_sections:
            when = section.effective_date.strftime("%m/%d/%Y") if section.effective_date else ""
            # Visual break between the as-of block and each policy-change block.
            riders.blank()
            riders.add("-" * PAGE_WIDTH)
            riders.blank()
            if section.rider_lines:
                riders.add(f"RIDERS AND BENEFITS ASSUMED IN THIS ILLUSTRATION AS OF {when}:")
                for line in section.rider_lines:
                    riders.add(f"    {line}")
            if section.limit_lines:
                riders.blank()
                riders.add(
                    f"ESTIMATED REGULATORY LIMITS FOR PREMIUMS AS OF {when} ARE AS FOLLOWS:")
                for line in section.limit_lines:
                    riders.add(f"    {line}")
        pages.append(riders.lines)

    return pages


def _has_rider_page(report: IllustrationReport) -> bool:
    return bool(report.rider_lines or report.regulatory_lines or report.change_sections)


class IllustrationReportTab(QWidget):
    """Scrollable print-preview of the UL illustration report."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._report: Optional[IllustrationReport] = None
        self.setStyleSheet(f"background-color: {PURPLE_BG};")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(6)

        top_row = QHBoxLayout()
        top_row.setSpacing(6)
        self.status_label = QLabel("")
        self.status_label.setStyleSheet(
            f"color: {PURPLE_DARK}; background: transparent; font-size: 11px; font-weight: bold;")
        top_row.addWidget(self.status_label)
        top_row.addStretch(1)
        self.print_pdf_btn = QPushButton("Print to PDF")
        self.print_pdf_btn.setEnabled(False)
        self.print_pdf_btn.setToolTip("Save the illustration report as a PDF file.")
        self.print_pdf_btn.setStyleSheet(
            f"QPushButton {{ background-color: #F3ECFC; color: {PURPLE_DARK};"
            " border: 1px solid #7E57C2; border-radius: 4px; padding: 1px 10px;"
            " min-height: 18px; font-size: 10px; font-weight: bold; }"
            "QPushButton:disabled { color: #9E9E9E; border-color: #C5B3E0; }")
        self.print_pdf_btn.clicked.connect(self._on_print_pdf)
        top_row.addWidget(self.print_pdf_btn)
        layout.addLayout(top_row)

        self.scroll = QScrollArea(self)
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.scroll.setStyleSheet("QScrollArea { background: transparent; }")
        layout.addWidget(self.scroll, 1)

        self._sheet_host = QWidget()
        self._sheet_host.setStyleSheet("background: transparent;")
        self._sheet_layout = QVBoxLayout(self._sheet_host)
        self._sheet_layout.setContentsMargins(0, 0, 0, 12)
        self._sheet_layout.setSpacing(14)
        self._sheet_layout.setAlignment(Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop)
        self.scroll.setWidget(self._sheet_host)

        self.clear()

    def clear(self, message: str = "Run Values to build the illustration report."):
        self._report = None
        self.print_pdf_btn.setEnabled(False)
        self.status_label.setText(message)
        while self._sheet_layout.count():
            item = self._sheet_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()

    def display_report(self, report: IllustrationReport):
        self.clear("")
        self._report = report
        self.print_pdf_btn.setEnabled(True)
        pages = format_report_pages(report)
        for lines in pages:
            sheet = QLabel("\n".join(lines))
            sheet.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
            sheet.setStyleSheet(
                "QLabel {"
                " background-color: white;"
                f" border: 1px solid {PURPLE_LIGHT};"
                " border-radius: 2px;"
                " padding: 28px 34px;"
                " font-family: Consolas, 'Courier New', monospace;"
                " font-size: 11px;"
                " color: #1A1A2E;"
                "}"
            )
            sheet.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
            self._sheet_layout.addWidget(sheet)
        guaranteed_note = (
            "" if report.has_guaranteed_values
            else "  Guaranteed columns are not projected."
        )
        self.status_label.setText(
            f"UL illustration report - {len(pages)} pages.{guaranteed_note}")

    # ── Print to PDF ────────────────────────────────────────────────────

    def _on_print_pdf(self):
        if self._report is None:
            return
        default_name = (
            (self._report.prepared_for or "Illustration")
            .replace("PREPARED FOR ", "").strip().replace(" ", "_")
        )
        path, _ = QFileDialog.getSaveFileName(
            self, "Print to PDF", f"{default_name}_Illustration.pdf",
            "PDF Files (*.pdf)")
        if not path:
            return
        try:
            self.write_pdf(self._report, path)
        except Exception as exc:
            QMessageBox.critical(self, "Print to PDF", f"Failed to write PDF: {exc}")
            return
        self.status_label.setText(f"Saved {path}")
        QDesktopServices.openUrl(QUrl.fromLocalFile(path))

    @staticmethod
    def _pdf_printer(path: str) -> QPrinter:
        printer = QPrinter(QPrinter.PrinterMode.HighResolution)
        printer.setOutputFormat(QPrinter.OutputFormat.PdfFormat)
        printer.setOutputFileName(path)
        printer.setPageSize(QPageSize(QPageSize.PageSizeId.Letter))
        printer.setPageOrientation(QPageLayout.Orientation.Landscape)
        printer.setPageMargins(QMarginsF(0.6, 0.5, 0.6, 0.5), QPageLayout.Unit.Inch)
        return printer

    @staticmethod
    def _print_document(report: IllustrationReport, printer: QPrinter) -> QTextDocument:
        """Lay the report out as a paginated QTextDocument for the printer."""
        pages = format_report_pages(report)
        parts: List[str] = []
        for index, lines in enumerate(pages):
            style = (
                "font-family:'Courier New',monospace; font-size:9pt;"
                " white-space:pre; margin:0;"
            )
            if index < len(pages) - 1:
                style += " page-break-after:always;"
            # Join with <br/> instead of newlines: Qt splits a <pre> into a new
            # text block at every literal newline, and each block inherits
            # page-break-after:always — one line per PDF page. <br/> keeps the
            # whole page in a single block so the break fires once.
            body = "<br/>".join(escape(line) for line in lines)
            parts.append(f'<pre style="{style}">{body}</pre>')

        document = QTextDocument()
        # Lay out at the printer's DPI — without this the fonts are sized for
        # the 96dpi screen while the page rect below is in 1200dpi device
        # pixels, printing the text at ~1/12 scale.
        document.documentLayout().setPaintDevice(printer)
        document.setDefaultFont(QFont("Courier New", 9))
        document.setHtml("".join(parts))
        # Pre-paginate to the printer's page rect: an unpaginated document makes
        # QTextDocument.print() re-lay it out with hardcoded 2cm margins.
        document.setPageSize(QSizeF(printer.pageRect(QPrinter.Unit.DevicePixel).size()))
        return document

    @staticmethod
    def write_pdf(report: IllustrationReport, path: str):
        """Render the fixed-width report pages to a landscape PDF file."""
        printer = IllustrationReportTab._pdf_printer(path)
        document = IllustrationReportTab._print_document(report, printer)
        document.print(printer)
