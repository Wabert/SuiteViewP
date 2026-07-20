"""Illustration Report tab — renders the UL illustration pages.

Print-preview style: white fixed-width "sheets" stacked on the purple
Illustration background, formatted from the structured
``IllustrationReport`` (core/report_builder.py). Mirrors RERUN's
"UL - Illustration Pages" layout. Print to PDF renders the same fixed-width
pages through Qt's PDF printer in landscape, sized so the 112-character lines
fill the page width.
"""
from __future__ import annotations

import re
from datetime import datetime
from html import escape
from pathlib import Path
from typing import List, Optional

from PyQt6.QtCore import QMarginsF, QSizeF, Qt, QUrl
from PyQt6.QtGui import QDesktopServices, QFont, QPageLayout, QPageSize, QTextDocument
from PyQt6.QtPrintSupport import QPrinter
from PyQt6.QtWidgets import (
    QCheckBox,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from suiteview.core.json_store import read_json, write_json
from suiteview.illustration.core.report_builder import (
    ExpenseRow,
    IllustrationReport,
    LedgerRow,
)
from .styles import PURPLE_BG, PURPLE_DARK, PURPLE_LIGHT, apply_input_checkbox_style

# Persisted illustration UI settings (output folder for printed PDFs and the
# Add Expense Report toggle).
_SETTINGS_FILE = Path.home() / ".suiteview" / "illustration_settings.json"
_OUTPUT_FOLDER_KEY = "report_output_folder"
_EXPENSE_PAGE_KEY = "report_add_expense_page"

PAGE_WIDTH = 112          # characters
# Rows per ledger page — bounded by the landscape PDF page height (Letter
# landscape at 10pt Courier holds ~46 text lines inside the margins).
LEDGER_ROWS_PER_PAGE = 30
# Rows per Expense Report page — the intro paragraph on the first page eats
# into the row budget, so a single conservative count keeps every page fitting.
EXPENSE_ROWS_PER_PAGE = 25


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
        self.lines.extend(_wrap_lines(text))

    def add_block(self, lines: List[str]):
        """Render a paragraph, filling the page width. Consecutive non-empty
        fragments are joined and word-wrapped as ONE run (so the author's
        pre-split lines don't produce irregular short breaks); an "" entry is a
        hard blank-line break between runs."""
        run: List[str] = []

        def flush():
            if run:
                self.lines.extend(_justify_lines(_wrap_lines(" ".join(run))))
                run.clear()

        for line in lines:
            if line == "":
                flush()
                self.lines.append("")
            else:
                run.append(line)
        flush()


def _wrap_lines(text: str) -> List[str]:
    """Word-wrap ``text`` to PAGE_WIDTH-character lines."""
    lines: List[str] = []
    line = ""
    for word in text.split():
        if line and len(line) + 1 + len(word) > PAGE_WIDTH:
            lines.append(line)
            line = word
        else:
            line = f"{line} {word}".strip()
    if line:
        lines.append(line)
    return lines


def _justify_line(line: str, width: int = PAGE_WIDTH) -> str:
    """Full-justify one line: pad the inter-word gaps with extra spaces so the
    line reaches ``width`` exactly, extra spaces going to the leftmost gaps.
    A single-word line (nothing to stretch against) is returned unchanged."""
    words = line.split()
    if len(words) < 2:
        return line
    slack = width - (sum(len(w) for w in words) + len(words) - 1)
    if slack <= 0:
        return " ".join(words)
    gaps = len(words) - 1
    base, extra = divmod(slack, gaps)
    out = ""
    for index, word in enumerate(words[:-1]):
        out += word + " " * (1 + base + (1 if index < extra else 0))
    return out + words[-1]


def _justify_lines(lines: List[str]) -> List[str]:
    """Full-justify a wrapped paragraph for a clean edge on BOTH margins —
    every line except the last is stretched to the page width. The last (and a
    single-line paragraph's only) line stays left-aligned/ragged, so short
    trailing lines and headings that don't span the width aren't stretched."""
    if len(lines) <= 1:
        return lines
    return [_justify_line(line) for line in lines[:-1]] + [lines[-1]]


# The AGE column header stacks "AGE / AT / EOY" over the three header rows to
# make explicit that the age shown is the end-of-year attained age; the YEAR
# column reads "END / OF / YEAR".
_LEDGER_HEADER = [
    f"{'AGE':>4}{'END':>5}{'':>11}{'':5}{'CASH':>8}{'':>10}  "
    f"{'+- GUARANTEED VALUES -+':^32}  {'+ NON-GUARANTEED VALUES +':^32}",
    f"{'AT':>4}{'OF':>5}{'PREMIUM':>11}{'':5}{'FROM':>8}{'LOAN':>10}  "
    f"{'ACCUM':>10}{'SURR':>10}{'DEATH':>12}  {'ACCUM':>10}{'SURR':>10}{'DEATH':>12}",
    f"{'EOY':>4}{'YEAR':>5}{'OUTLAY':>11}{'':5}{'POLICY':>8}{'BALANCE':>10}  "
    f"{'VALUE':>10}{'VALUE':>10}{'BENEFIT':>12}  {'VALUE':>10}{'VALUE':>10}{'BENEFIT':>12}",
    "-" * PAGE_WIDTH,
]

# Assumption note printed under the ledger: cash flows are beginning-of-period,
# the tabulated policy values (and the age) are end-of-year.
_LEDGER_ASSUMPTION_NOTE = (
    "PREMIUMS, WITHDRAWALS, AND LOANS ARE ASSUMED TO OCCUR AT THE BEGINNING OF "
    "THE APPLICABLE PERIOD. THE LEDGER VALUES SHOWN FOR AGE, LOAN BALANCE, "
    "ACCUMULATION VALUE, SURRENDER VALUE, AND DEATH BENEFIT ARE END-OF-YEAR "
    "(EOY) VALUES."
)


def _ledger_line(row: LedgerRow) -> str:
    return (
        f"{row.eoy_age:>4}{row.year:>5}{row.premium_outlay:>11,.0f}"
        f"{row.markers:>5}{row.cash_from_policy:>8,.0f}{row.loan_balance:>10,.0f}  "
        f"{_money(row.guar_accum):>10}{_money(row.guar_surr):>10}{_money(row.guar_death):>12}  "
        f"{_money(row.accum_value):>10}{_money(row.surr_value):>10}{_money(row.death_benefit):>12}"
    )


# ── Expense Report supplemental page (RERUN "Expense Report" J:Y) ───────────
# Column layout: (width, top header, bottom header, attribute). Widths sum to
# PAGE_WIDTH (112). Follows the sheet's J:Y order, with the non-premium expense
# components (P, Q, R, S) plus partial surrender charges combined into one
# EXPENSES/FEES column and a POLICY DEBT column added to the Policy Values
# group (before Net Surr Value).
# Age-then-Year order matches the illustration ledger; the age column stacks
# "AGE / EOY" to flag it as the end-of-year attained age.
_EXPENSE_COLUMNS = [
    (4, "AGE", "EOY", "eoy_age"),                           # K — age at EOY
    (5, "", "YEAR", "year"),                                # J — End of Year (width matches the ledger)
    (8, "PREMIUM", "OUTLAY", "premium_outlay"),             # L — Assumed Premium Outlay
    (8, "DISTRI-", "BUTIONS", "distributions"),             # M — Distributions
    (8, "PREMIUM", "CHARGE", "premium_charge"),             # N — Premium Charge
    (8, "COI", "CHARGE", "coi_charge"),                     # O — Cost of Insurance
    (6, "RIDER", "CHG", "rider_charges"),                   # T — Other Rider Charges
    (14, "", "EXPENSES/FEES", "expenses"),                  # P+Q+R+S + partial SC
    (9, "INTEREST", "CREDITED", "interest_credited"),       # U — Interest Credited
    (9, "ACCUM", "VALUE", "accum_value"),                   # V — Accumulation Value
    (6, "SURR", "CHGS", "surrender_charges"),               # W — Surrender Charges
    (8, "POLICY", "DEBT", "policy_debt"),                   # EOY loan balance (ledger's)
    (9, "NET SURR", "VALUE", "net_surrender_value"),        # X — Net Surrender Value
    (10, "NET DEATH", "BENEFIT", "net_death_benefit"),      # Y — Net Death Benefit
]

_EXPENSE_INTRO = [
    "THIS SUPPLEMENTAL EXHIBIT BREAKS THE POLICY'S ANNUAL ACTIVITY INTO ITS EXPENSE "
    "CHARGES AND CREDITS SO YOU CAN SEE WHERE EACH PREMIUM DOLLAR GOES. FOR EACH POLICY "
    "YEAR IT SHOWS THE PREMIUMS PAID, ANY DISTRIBUTIONS TAKEN (WITHDRAWALS, LOANS, AND "
    "FORCED-OUT PREMIUM), THE CHARGES DEDUCTED FROM THE ACCUMULATION VALUE, AND THE "
    "INTEREST CREDITED. THE EXPENSES/FEES COLUMN COMBINES THE ADMINISTRATIVE CHARGES "
    "(PER-1000, MONTHLY FEE, ASSET, AND ACCUMULATION VALUE CHARGES) WITH ANY PARTIAL "
    "SURRENDER CHARGES ASSESSED ON WITHDRAWALS.",
    "CHARGES AND CREDITS ARE ANNUAL TOTALS ON THE ILLUSTRATED (CURRENT, NON-GUARANTEED) "
    "BASIS, CONSISTENT WITH THE ILLUSTRATION'S LEDGER PAGES. POLICY VALUES, INCLUDING ANY "
    "OUTSTANDING POLICY DEBT, ARE END-OF-YEAR AMOUNTS. YEARS AFTER THE POLICY TERMINATES "
    "SHOW ZERO.",
]


def _expense_header_lines() -> List[str]:
    """Group banner + two stacked column-header rows + rule."""
    # Group spans over the sheet's row-2 headings: Deductions covers Premium
    # Charge / COI / Rider / Expenses-Fees, Policy Values the last five columns.
    deduction_width = sum(w for w, *_ in _EXPENSE_COLUMNS[4:8])
    values_width = sum(w for w, *_ in _EXPENSE_COLUMNS[9:14])
    groups = (
        f"{'':4}{'':5}{'PREMIUMS':>8}{'LOAN/WD':>8}"
        f"{'+- DEDUCTIONS -+':^{deduction_width}}"
        f"{'EARNINGS':>9}{'+- POLICY VALUES -+':^{values_width}}"
    )
    top = "".join(f"{label:>{width}}" for width, label, _bottom, _attr in _EXPENSE_COLUMNS)
    bottom = "".join(f"{label:>{width}}" for width, _top, label, _attr in _EXPENSE_COLUMNS)
    return [groups.rstrip(), top, bottom, "-" * PAGE_WIDTH]


def _expense_line(row: ExpenseRow) -> str:
    parts = [f"{row.eoy_age:>4}", f"{row.year:>5}"]
    for width, _top, _bottom, attr in _EXPENSE_COLUMNS[2:]:
        parts.append(f"{getattr(row, attr):>{width},.0f}")
    return "".join(parts)


def format_report_pages(
    report: IllustrationReport,
    include_expense_report: bool = False,
) -> List[List[str]]:
    """Format the structured report into pages of fixed-width text lines.

    ``include_expense_report`` appends the supplemental Expense Report page(s)
    (RERUN "Expense Report" columns J:Y) after the last standard page.
    """
    ledger_chunks: List[List[LedgerRow]] = []
    rows = report.ledger
    for start in range(0, len(rows), LEDGER_ROWS_PER_PAGE):
        ledger_chunks.append(rows[start:start + LEDGER_ROWS_PER_PAGE])
    if not ledger_chunks:
        ledger_chunks = [[]]
    expense_chunks: List[List[ExpenseRow]] = []
    if include_expense_report:
        expense_rows = report.expense_rows
        for start in range(0, len(expense_rows), EXPENSE_ROWS_PER_PAGE):
            expense_chunks.append(expense_rows[start:start + EXPENSE_ROWS_PER_PAGE])
        if not expense_chunks:
            expense_chunks = [[]]
    # The supplemental Expense Report is a separate exhibit — the illustration's
    # own page numbering excludes it.
    total = 2 + len(ledger_chunks) + (1 if _has_rider_page(report) else 0)

    pages: List[List[str]] = []

    # ── Page 1: cover ──
    cover = _PageBuilder(report, 1, total)
    cover.add_block(report.disclaimer_lines)
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
            if report.footnote_legends:
                page.blank()
                for legend in report.footnote_legends:
                    page.add_wrapped(legend)
            page.blank()
            page.add_wrapped(_LEDGER_ASSUMPTION_NOTE)
        pages.append(page.lines)

    # ── Notes page ──
    notes = _PageBuilder(report, 2 + len(ledger_chunks), total)
    for paragraph in report.note_paragraphs:
        notes.add_block(paragraph)
        notes.blank()
    if report.exception_section:
        notes.blank()
        notes.add_block(report.exception_section)
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

    # ── Expense Report supplemental exhibit — its own heading and its own
    #    page numbering, separate from the illustration pages above. ──
    run = report.run_date.strftime("%m/%d/%Y") if report.run_date else ""
    exhibit_title = (
        f"SUPPLEMENTAL EXHIBIT FOR POLICY {report.policy_number}"
        if report.policy_number else "SUPPLEMENTAL EXHIBIT"
    )
    for index, chunk in enumerate(expense_chunks):
        page_no = f"Page {index + 1} of {len(expense_chunks)}"
        lines: List[str] = [
            run + page_no.rjust(PAGE_WIDTH - len(run)),
            _center(exhibit_title),
            _center("EXPENSE REPORT"),
            "",
        ]
        if index == 0:
            for paragraph in _EXPENSE_INTRO:
                lines.extend(_wrap_lines(paragraph))
                lines.append("")
        lines.extend(_expense_header_lines())
        base = index * EXPENSE_ROWS_PER_PAGE
        for row_index, row in enumerate(chunk):
            lines.append(_expense_line(row))
            # Same five-row grouping as the ledger pages.
            if (base + row_index + 1) % 5 == 0 and row_index + 1 < len(chunk):
                lines.append("")
        pages.append(lines)

    return pages


def _has_rider_page(report: IllustrationReport) -> bool:
    return bool(report.rider_lines or report.regulatory_lines or report.change_sections)


class IllustrationReportTab(QWidget):
    """Scrollable print-preview of the UL illustration report."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._report: Optional[IllustrationReport] = None
        self._guaranteed_error: Optional[str] = None
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
        self.expense_report_check = QCheckBox("Add Expense Report")
        self.expense_report_check.setToolTip(
            "Append a supplemental Expense Report page (annual charges and "
            "credits) to the end of the illustration.")
        apply_input_checkbox_style(self.expense_report_check)
        self.expense_report_check.setChecked(self._load_expense_page_setting())
        self.expense_report_check.toggled.connect(self._on_expense_report_toggled)
        top_row.addWidget(self.expense_report_check)
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

        # ── Output folder row (persisted across sessions) ──
        folder_row = QHBoxLayout()
        folder_row.setSpacing(6)
        folder_label = QLabel("Output folder:")
        folder_label.setStyleSheet(
            f"color: {PURPLE_DARK}; background: transparent; font-size: 11px; font-weight: bold;")
        folder_row.addWidget(folder_label)
        self.output_folder_edit = QLineEdit()
        self.output_folder_edit.setPlaceholderText("Prompt for a folder each time (not set)")
        self.output_folder_edit.setToolTip(
            "Folder where illustration PDFs are saved. Saved across sessions.")
        self.output_folder_edit.setStyleSheet(
            "QLineEdit { background: white; color: #1A1A2E; border: 1px solid #7E57C2;"
            " border-radius: 4px; padding: 1px 6px; min-height: 18px; font-size: 10px; }")
        self.output_folder_edit.editingFinished.connect(self._on_output_folder_edited)
        folder_row.addWidget(self.output_folder_edit, 1)
        self.browse_folder_btn = QPushButton("Browse…")
        self.browse_folder_btn.setToolTip("Choose the folder illustration PDFs are saved to.")
        self.browse_folder_btn.setStyleSheet(
            f"QPushButton {{ background-color: #F3ECFC; color: {PURPLE_DARK};"
            " border: 1px solid #7E57C2; border-radius: 4px; padding: 1px 10px;"
            " min-height: 18px; font-size: 10px; font-weight: bold; }")
        self.browse_folder_btn.clicked.connect(self._on_browse_output_folder)
        folder_row.addWidget(self.browse_folder_btn)
        layout.addLayout(folder_row)

        self._output_folder = self._load_output_folder()
        if self._output_folder:
            self.output_folder_edit.setText(self._output_folder)

        # Guaranteed-run failure banner — shown when the guaranteed-basis
        # projection raised, so the report's blank GUARANTEED VALUES columns
        # are never mistaken for computed zeros. UI-only: the printed pages
        # are untouched.
        self.guaranteed_warning = QLabel("", self)
        self.guaranteed_warning.setWordWrap(True)
        self.guaranteed_warning.setStyleSheet(
            "background-color: #7A1020; color: #FFD54F; border: 1px solid #D4A017;"
            " border-radius: 4px; font-size: 12px; font-weight: bold; padding: 5px 9px;")
        self.guaranteed_warning.setVisible(False)
        layout.addWidget(self.guaranteed_warning)

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
        self._guaranteed_error = None
        self.print_pdf_btn.setEnabled(False)
        self.guaranteed_warning.setVisible(False)
        self.status_label.setText(message)
        while self._sheet_layout.count():
            item = self._sheet_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()

    def current_report(self) -> Optional[IllustrationReport]:
        """The report currently displayed (None when cleared) — used by the
        main window's per-policy session cache."""
        return self._report

    def display_report(self, report: IllustrationReport, guaranteed_error: Optional[str] = None):
        self.clear("")
        self._report = report
        self._guaranteed_error = guaranteed_error
        self.print_pdf_btn.setEnabled(True)
        if guaranteed_error and not report.has_guaranteed_values:
            self.guaranteed_warning.setText(
                "⚠ Guaranteed projection failed — the report's GUARANTEED VALUES "
                f"columns are blank: {guaranteed_error}")
            self.guaranteed_warning.setVisible(True)
        pages = format_report_pages(
            report, include_expense_report=self.expense_report_check.isChecked())
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

    # ── Add Expense Report toggle ───────────────────────────────────────

    @staticmethod
    def _load_expense_page_setting() -> bool:
        settings = read_json(_SETTINGS_FILE, default={}) or {}
        return bool(settings.get(_EXPENSE_PAGE_KEY, False))

    def _on_expense_report_toggled(self, checked: bool) -> None:
        settings = read_json(_SETTINGS_FILE, default={}) or {}
        settings[_EXPENSE_PAGE_KEY] = bool(checked)
        try:
            write_json(_SETTINGS_FILE, settings)
        except OSError:
            pass  # cosmetic preference — never block the toggle on disk errors
        # Re-render the held report with/without the supplemental page; no
        # engine round trip needed.
        if self._report is not None:
            self.display_report(self._report, self._guaranteed_error)

    # ── Print to PDF ────────────────────────────────────────────────────

    @staticmethod
    def _load_output_folder() -> str:
        settings = read_json(_SETTINGS_FILE, default={}) or {}
        folder = settings.get(_OUTPUT_FOLDER_KEY, "")
        return folder if isinstance(folder, str) else ""

    def _save_output_folder(self, folder: str) -> None:
        settings = read_json(_SETTINGS_FILE, default={}) or {}
        settings[_OUTPUT_FOLDER_KEY] = folder
        try:
            write_json(_SETTINGS_FILE, settings)
        except OSError as exc:
            QMessageBox.warning(
                self, "Output folder",
                f"Could not save the output folder setting: {exc}")

    def _set_output_folder(self, folder: str) -> None:
        self._output_folder = folder
        if self.output_folder_edit.text() != folder:
            self.output_folder_edit.setText(folder)
        self._save_output_folder(folder)

    def _on_output_folder_edited(self) -> None:
        self._set_output_folder(self.output_folder_edit.text().strip())

    def _on_browse_output_folder(self) -> None:
        start_dir = self._output_folder if self._output_folder and Path(self._output_folder).is_dir() else ""
        folder = QFileDialog.getExistingDirectory(
            self, "Choose output folder", start_dir)
        if folder:
            self._set_output_folder(folder)

    def _default_pdf_name(self) -> str:
        """policynumber - plancode - yyyy-mm-dd hh-mm (filesystem-safe)."""
        report = self._report
        policy = (getattr(report, "policy_number", "") or "").strip() if report else ""
        plancode = (getattr(report, "plancode", "") or "").strip() if report else ""
        stamp = datetime.now().strftime("%Y-%m-%d %H-%M")
        parts = [p for p in (policy, plancode, stamp) if p]
        name = " - ".join(parts) if parts else "Illustration"
        # Strip characters illegal in Windows filenames.
        name = re.sub(r'[<>:"/\\|?*]', "", name)
        return f"{name}.pdf"

    def _on_print_pdf(self):
        if self._report is None:
            return
        default_name = self._default_pdf_name()
        if self._output_folder and Path(self._output_folder).is_dir():
            start_path = str(Path(self._output_folder) / default_name)
        else:
            start_path = default_name
        path, _ = QFileDialog.getSaveFileName(
            self, "Print to PDF", start_path, "PDF Files (*.pdf)")
        if not path:
            return
        # Remember the folder the user actually saved to.
        chosen_dir = str(Path(path).resolve().parent)
        if chosen_dir != self._output_folder:
            self._set_output_folder(chosen_dir)
        try:
            self.write_pdf(
                self._report, path,
                include_expense_report=self.expense_report_check.isChecked())
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
    def _print_document(
        report: IllustrationReport,
        printer: QPrinter,
        include_expense_report: bool = False,
    ) -> QTextDocument:
        """Lay the report out as a paginated QTextDocument for the printer."""
        pages = format_report_pages(report, include_expense_report=include_expense_report)
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
    def write_pdf(report: IllustrationReport, path: str, include_expense_report: bool = False):
        """Render the fixed-width report pages to a landscape PDF file."""
        printer = IllustrationReportTab._pdf_printer(path)
        document = IllustrationReportTab._print_document(
            report, printer, include_expense_report=include_expense_report)
        document.print(printer)
