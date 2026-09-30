"""Illustration Report tab — renders the UL illustration pages.

Print-preview style: white fixed-width "sheets" stacked on the purple
Illustration background, formatted from the structured
``IllustrationReport`` (core/report_builder.py). Mirrors RERUN's
"UL - Illustration Pages" layout. Print to PDF renders the same fixed-width
pages in landscape through the shared ``report_pages`` printer, sized so the
112-character lines fill the page width.
"""
from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import List, Optional

from PyQt6.QtCore import Qt, QUrl
from PyQt6.QtGui import QDesktopServices, QTextDocument
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
    QVBoxLayout,
    QWidget,
)

from suiteview.core.json_store import read_json, write_json
from suiteview.illustration.core.abr_quote import ABR_TARGET_SV
from suiteview.illustration.core.report_specs import PageSpec
from suiteview.illustration.core.report_text import center_line, justified_paragraph, wrap_lines
from suiteview.illustration.core.report_builder import (
    ExpenseRow,
    IllustrationReport,
    IULStrategyRateRow,
    LedgerRow,
)
from .report_pages import (
    OUTPUT_FOLDER_EDIT_STYLE,
    OUTPUT_FOLDER_KEY,
    PRINT_BUTTON_STYLE,
    REPORT_BUTTON_STYLE,
    REPORT_LABEL_STYLE,
    default_pdf_name,
    pages_document,
    pdf_printer,
    report_settings_file,
    report_sheet,
)
from .styles import PURPLE_BG, apply_input_checkbox_style

# Persisted illustration UI settings (output folder for printed PDFs and the
# Add Expense Report toggle). Resolve the profile at call time; tests and
# isolated profiles can change the profile root after this module imports.
def _settings_file():
    return report_settings_file()


_EXPENSE_PAGE_KEY = "report_add_expense_page"

PAGE_WIDTH = 112          # characters
# Rows per ledger page — bounded by the landscape PDF page height (Letter
# landscape at 10pt Courier holds ~46 text lines inside the margins).
LEDGER_ROWS_PER_PAGE = 30
# Rows per Expense Report page — the intro paragraph on the first page eats
# into the row budget, so a single conservative count keeps every page fitting.
EXPENSE_ROWS_PER_PAGE = 25


def _center(text: str) -> str:
    return center_line(text, PAGE_WIDTH)


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
        if report.subtitle:
            self.lines.append(_center(report.subtitle))
        for line in report.basis_lines:
            self.lines.append(_center(line))
        self.lines.append(_center(report.prepared_for))
        self.lines.append("")

    def blank(self, count: int = 1):
        self.lines.extend([""] * count)

    def add(self, text: str = ""):
        self.lines.append(text[:PAGE_WIDTH])

    def add_centered(self, text: str):
        self.lines.append(_center(text))

    def add_wrapped(self, text: str):
        self.lines.extend(wrap_lines(text, PAGE_WIDTH))

    def add_block(self, lines: List[str]):
        """Render a paragraph, filling the page width. Consecutive non-empty
        fragments are joined and word-wrapped as ONE run (so the author's
        pre-split lines don't produce irregular short breaks); an "" entry is a
        hard blank-line break between runs."""
        run: List[str] = []

        def flush():
            if run:
                self.lines.extend(justified_paragraph(" ".join(run), PAGE_WIDTH))
                run.clear()

        for line in lines:
            if line == "":
                flush()
                self.lines.append("")
            else:
                run.append(line)
        flush()


# The AGE column header stacks "AGE / AT / EOY" over the three header rows to
# make explicit that the age shown is the end-of-year attained age; the YEAR
# column reads "END / OF / YEAR".
_LEDGER_HEADER = [
    f"{'AGE':>4}{'END':>5}{'':>12}{'':5}{'':>8}{'':>10}  "
    f"{'+- GUARANTEED VALUES -+':^32}  {'+ NON-GUARANTEED VALUES +':^32}",
    f"{'AT':>4}{'OF':>5}{'PREMIUM':>12}{'':5}{'':>8}{'LOAN':>10}  "
    f"{'ACCUM':>10} {'SURR':>10} {'DEATH':>10}  "
    f"{'ACCUM':>10} {'SURR':>10} {'DEATH':>10}",
    f"{'EOY':>4}{'YEAR':>5}{'OUTLAY':>12}{'':5}{'PROCEEDS':>8}{'BALANCE':>10}  "
    f"{'VALUE':>10} {'VALUE':>10} {'BENEFIT':>10}  "
    f"{'VALUE':>10} {'VALUE':>10} {'BENEFIT':>10}",
    "-" * PAGE_WIDTH,
]


def _ledger_header(loan_repayments_illustrated: bool) -> List[str]:
    if not loan_repayments_illustrated:
        return _LEDGER_HEADER
    return [
        f"{'AGE':>4}{'END':>5}{'PREMIUM +':>12}{'':5}{'':>8}{'':>10}  "
        f"{'+- GUARANTEED VALUES -+':^32}  {'+ NON-GUARANTEED VALUES +':^32}",
        f"{'AT':>4}{'OF':>5}{'LOAN REPAY':>17}{'':>8}{'LOAN':>10}  "
        f"{'ACCUM':>10} {'SURR':>10} {'DEATH':>10}  "
        f"{'ACCUM':>10} {'SURR':>10} {'DEATH':>10}",
        f"{'EOY':>4}{'YEAR':>5}{'OUTLAY':>12}{'':5}{'PROCEEDS':>8}{'BALANCE':>10}  "
        f"{'VALUE':>10} {'VALUE':>10} {'BENEFIT':>10}  "
        f"{'VALUE':>10} {'VALUE':>10} {'BENEFIT':>10}",
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
        f"{row.eoy_age:>4}{row.year:>5}{row.premium_outlay:>12,.2f}"
        f"{row.markers:>5}{row.cash_from_policy:>8,.0f}{row.loan_balance:>10,.0f}  "
        f"{_money(row.guar_accum):>10} {_money(row.guar_surr):>10} "
        f"{_money(row.guar_death):>10}  "
        f"{_money(row.accum_value):>10} {_money(row.surr_value):>10} "
        f"{_money(row.death_benefit):>10}"
    )


# ── Expense Report supplemental page (RERUN "Expense Report" J:Y) ───────────
# Column layout: (width, top header, bottom header, attribute). Widths sum to
# PAGE_WIDTH (112). Follows the sheet's J:Y order, with the non-premium expense
# components (P, Q, R, S) combined into one EXPENSES/FEES column and a
# POLICY DEBT column added to the Policy Values
# group (before Net Surr Value).
# Age-then-Year order matches the illustration ledger; the age column stacks
# "AGE / EOY" to flag it as the end-of-year attained age.
_EXPENSE_COLUMNS = [
    (4, "AGE", "EOY", "eoy_age"),                           # K — age at EOY
    (5, "", "YEAR", "year"),                                # J — End of Year (width matches the ledger)
    (12, "PREMIUM", "OUTLAY", "premium_outlay"),            # L — Assumed Premium Outlay
    (8, "CASH", "OUT", "distributions"),                    # M — Gross withdrawals + force-outs
    (8, "PREMIUM", "CHARGE", "premium_charge"),             # N — Premium Charge
    (8, "COI", "CHARGE", "coi_charge"),                     # O — Cost of Insurance
    (6, "RIDER", "CHG", "rider_charges"),                   # T — Other Rider Charges
    (10, "", "EXP/FEES", "expenses"),                       # P+Q+R+S
    (9, "INTEREST", "CREDITED", "interest_credited"),       # U — Interest Credited
    (9, "ACCUM", "VALUE", "accum_value"),                   # V — Accumulation Value
    (6, "SURR", "CHGS", "surrender_charges"),               # W — Surrender Charges
    (8, "POLICY", "DEBT", "policy_debt"),                   # EOY loan balance (ledger's)
    (9, "NET SURR", "VALUE", "net_surrender_value"),        # X — Net Surrender Value
    (10, "NET DEATH", "BENEFIT", "net_death_benefit"),      # Y — Net Death Benefit
]

_EXPENSE_INTRO = [
    "THIS SUPPLEMENTAL EXHIBIT BREAKS THE POLICY'S ANNUAL ACTIVITY INTO ITS EXPENSE "
    "CHARGES AND CREDITS. FOR EACH POLICY "
    "YEAR IT SHOWS THE PREMIUMS PAID, CASH OUT (GROSS WITHDRAWALS AND "
    "FORCED-OUT PREMIUM), THE CHARGES DEDUCTED FROM THE ACCUMULATION VALUE, AND THE "
    "INTEREST CREDITED. THE EXP/FEES COLUMN COMBINES THE ADMINISTRATIVE CHARGES "
    "(PER-1000, MONTHLY FEE, ASSET, AND ACCUMULATION VALUE CHARGES).",
    "CHARGES AND CREDITS ARE ANNUAL TOTALS ON THE ILLUSTRATED (CURRENT, NON-GUARANTEED) "
    "BASIS, CONSISTENT WITH THE ILLUSTRATION'S LEDGER PAGES. POLICY VALUES, INCLUDING ANY "
    "OUTSTANDING POLICY DEBT, ARE END-OF-YEAR AMOUNTS. YEARS AFTER THE POLICY TERMINATES "
    "SHOW ZERO.",
]


def _span_banner(label: str, width: int) -> str:
    """A ``+--- LABEL ---+`` bracket that fills the full group ``width``."""
    return "+" + f" {label} ".center(width - 2, "-") + "+"


def _expense_header_lines() -> List[str]:
    """Group banner + two stacked column-header rows + rule."""
    # Group banners fill their span: Deductions covers COI / Rider /
    # Expenses-Fees; Policy Values covers Accum Value through Net Death Benefit.
    deduction_width = sum(w for w, *_ in _EXPENSE_COLUMNS[5:8])
    values_width = sum(w for w, *_ in _EXPENSE_COLUMNS[9:14])
    groups = (
        f"{'':4}{'':5}{'PREMIUMS':>12}{'':8}{'':8}"
        f"{_span_banner('DEDUCTIONS', deduction_width)}"
        f"{'EARNINGS':>9}{_span_banner('POLICY VALUES', values_width)}"
    )
    top = "".join(f"{label:>{width}}" for width, label, _bottom, _attr in _EXPENSE_COLUMNS)
    bottom = "".join(f"{label:>{width}}" for width, _top, label, _attr in _EXPENSE_COLUMNS)
    return [groups.rstrip(), top, bottom, "-" * PAGE_WIDTH]


def _expense_line(row: ExpenseRow) -> str:
    parts = [f"{row.eoy_age:>4}", f"{row.year:>5}"]
    for width, _top, _bottom, attr in _EXPENSE_COLUMNS[2:]:
        decimals = 2 if attr == "premium_outlay" else 0
        parts.append(f"{getattr(row, attr):>{width},.{decimals}f}")
    return "".join(parts)


def _rate(value: Optional[float]) -> str:
    return "" if value is None else f"{value * 100:.2f}%"


def _iul_assumptions_page(page: _PageBuilder, report: IllustrationReport) -> None:
    if report.note_paragraphs:
        page.add_block(report.note_paragraphs[0])
        page.blank()
    if len(report.note_paragraphs) > 1:
        page.add_block(report.note_paragraphs[1])
        page.blank()

    page.add("NON-GUARANTEED CURRENT ASSUMPTIONS")
    page.blank()
    page.add("ILLUSTRATED RATES BY INDEX STRATEGY")
    page.add("-" * PAGE_WIDTH)
    for strategy in report.iul_strategy_rates:
        page.add(
            f"  {strategy.label[:88]:<88}{_rate(strategy.illustrated_rate):>22}"
        )
    if report.iul_fixed_rate is not None:
        page.add(
            f"  {'FIXED ACCOUNT CURRENT INTEREST RATE':<88}"
            f"{_rate(report.iul_fixed_rate):>22}"
        )
    page.blank()
    page.add_wrapped(
        "THE NON-GUARANTEED PROJECTION USES THE ILLUSTRATED RATES SHOWN ABOVE, "
        "CURRENT NON-GUARANTEED CHARGES, AND THE ALLOCATION PERCENTAGES SHOWN "
        "ON THE FIRST PAGE. THE RESULTING WEIGHTED RATE IS NOT GUARANTEED AND "
        "ACTUAL POLICY RESULTS MAY BE HIGHER OR LOWER."
    )
    page.blank()
    page.add_wrapped(
        "INDEXED UNIVERSAL LIFE ILLUSTRATIONS USE A BENCHMARK INDEX STRATEGY "
        "TO LIMIT THE RATE THAT MAY BE ILLUSTRATED. THE LIMIT IS BASED ON "
        "HISTORICAL GEOMETRIC AVERAGES AND APPLICABLE STRATEGY PARAMETERS; IT "
        "IS NOT A PREDICTION OF FUTURE RETURNS."
    )
    page.blank()
    page.add(
        f"{'BENCHMARK INDEX STRATEGY':<72}"
        f"{'AVERAGE MINIMUM':>20}{'AVERAGE MAXIMUM':>20}"
    )
    page.add("-" * PAGE_WIDTH)
    page.add(
        f"{'  ONE YEAR POINT TO POINT WITH CURRENT CAP AND FLOOR':<72}"
        f"{_rate(report.iul_benchmark_minimum):>20}"
        f"{_rate(report.iul_benchmark_maximum):>20}"
    )
    page.blank()
    page.add_wrapped(
        "INDEXED CREDITS DEPEND ON THE INDEX RETURN AND THE CAP, FLOOR, "
        "PARTICIPATION RATE, SPREAD, SPECIFIED RATE, MULTIPLIER, AND ASSET FEE "
        "THAT APPLY TO EACH STRATEGY. THESE NON-GUARANTEED PARAMETERS MAY "
        "CHANGE. THE POLICY DOES NOT DIRECTLY INVEST IN OR OWN AN INDEX."
    )


def _strategy_parameter_lines(
    strategy: IULStrategyRateRow,
) -> tuple[str, str, str]:
    values = strategy.parameters
    fund_id = strategy.fund_id
    if fund_id == "IF":
        return (
            f"SPRD {_rate(values.get('int_rate_spread'))}",
            f"FLR {_rate(values.get('floor'))}",
            "",
        )
    if fund_id == "IS":
        return (
            f"SPEC {_rate(values.get('specified_rate'))}",
            f"FLR {_rate(values.get('floor'))}",
            "",
        )
    if fund_id == "M1":
        return (
            f"PART {_rate(values.get('participation'))}",
            f"FLR {_rate(values.get('floor'))}",
            "",
        )
    if fund_id in {"IP", "IR"}:
        return (
            f"CAP {_rate(values.get('cap'))}",
            f"MULT {_rate(values.get('multiplier'))}",
            f"FEE {_rate(values.get('asset_fee'))}",
        )
    return (
        f"CAP {_rate(values.get('cap'))}",
        f"FLR {_rate(values.get('floor'))}",
        "",
    )


def _iul_historical_page(page: _PageBuilder, report: IllustrationReport) -> None:
    page.add_centered("HISTORICAL INDEX RATE LEDGER - CURRENT SCENARIO")
    page.blank()
    page.add_wrapped(
        "THE ANNUAL CREDITING RATES BELOW APPLY THE CURRENT NON-GUARANTEED "
        "STRATEGY PARAMETERS TO THE MOST RECENT 20 FULL CALENDAR YEARS OF EACH "
        "RELEVANT MARKET INDEX. PAST PERFORMANCE DOES NOT PREDICT FUTURE "
        "RESULTS, AND STRATEGY PARAMETERS MAY CHANGE."
    )
    page.blank()

    markets = list(dict.fromkeys(
        strategy.market_index for strategy in report.iul_strategy_rates
    ))
    groups = [
        (
            market,
            [
                strategy
                for strategy in report.iul_strategy_rates
                if strategy.market_index == market
            ],
        )
        for market in markets
    ]
    columns = [
        (kind, key)
        for market, strategies in groups
        for kind, key in [
            ("market", market),
            *((("strategy", strategy.fund_id) for strategy in strategies)),
        ]
    ]
    label_width = 12
    column_width = max(
        8, (PAGE_WIDTH - label_width) // max(len(columns), 1)
    )
    market_labels = {
        "SP500": "S&P 500",
        "NASDAQ100": "NASDAQ 100",
        "SPMARC5": "S&P MARC 5",
    }
    column_headers = {
        market: ["MARKET INDEX", market_labels.get(market, market), "RETURNS"]
        for market in markets
    }
    for strategy in report.iul_strategy_rates:
        first, second, third = _strategy_parameter_lines(strategy)
        header = [strategy.fund_id, first, second, third]
        while header and not header[-1]:
            header.pop()
        column_headers[strategy.fund_id] = header

    header_height = max(len(header) for header in column_headers.values())
    for row_index in range(header_height):
        cells = []
        for _kind, key in columns:
            header = column_headers[key]
            header_index = row_index - (header_height - len(header))
            text = header[header_index] if header_index >= 0 else ""
            cells.append(f"{text[:column_width]:>{column_width}}")
        page.add(
            f"{'YEAR ENDING' if row_index == header_height - 1 else '':>{label_width}}"
            + "".join(cells)
        )
    page.add(
        "-" * min(PAGE_WIDTH, label_width + column_width * len(columns))
    )

    def values_line(label: str, market_returns: dict, credited_rates: dict) -> str:
        values = []
        for kind, key in columns:
            value = market_returns[key] if kind == "market" else credited_rates[key]
            values.append(f"{_rate(value):>{column_width}}")
        return f"{label:>{label_width}}" + "".join(values)

    for row in report.iul_historical_rows:
        label = row.date_eoy.strftime("%m/%d/%Y") if row.date_eoy else ""
        page.add(values_line(label, row.market_returns, row.credited_rates))

    page.blank()
    for row in report.iul_compound_yields:
        page.add(values_line(
            f"{row.years}-YR YIELD",
            row.market_returns,
            row.credited_rates,
        ))


def _format_report_pages_from_specs(
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
    has_iul_history = report.is_iul and bool(report.iul_historical_rows)
    total = (
        2
        + len(ledger_chunks)
        + (1 if _has_rider_page(report) else 0)
        + (1 if has_iul_history else 0)
    )

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
        if report.iul_fund_values:
            for row in report.iul_fund_values:
                cover.add(f"    {row.label[:88]:<88}{f'${row.value:,.2f}':>20}")
        if report.loan_basis_line:
            cover.add_wrapped(report.loan_basis_line)
        cover.blank()
    if report.iul_allocations:
        cover.add("THE ALLOCATION PERCENTAGES USED IN THIS ILLUSTRATION ARE:")
        for row in report.iul_allocations:
            label = f"[{row.fund_id}] - {row.label}"
            cover.add(f"    {label[:88]:<88}{_rate(row.allocation):>20}")
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
        page.lines.extend(_ledger_header(report.loan_repayments_illustrated))
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
    if report.is_iul:
        _iul_assumptions_page(notes, report)
    else:
        for paragraph in report.note_paragraphs:
            notes.add_block(paragraph)
            notes.blank()
        if report.exception_section:
            notes.blank()
            notes.add_block(report.exception_section)
    pages.append(notes.lines)

    # ── Riders / regulatory page ──
    if _has_rider_page(report):
        rider_page_no = 3 + len(ledger_chunks)
        riders = _PageBuilder(report, rider_page_no, total)
        riders.add("POLICY RIDERS AND BENEFITS AND REGULATORY PREMIUM (IF APPLICABLE)")
        riders.blank()
        as_of = report.as_of_date.strftime("%m/%d/%Y") if report.as_of_date else ""
        riders.add(
            f"RIDERS AND BENEFITS INCLUDED IN THE MODELED ISSUE CONDITIONS ({as_of}):"
            if report.run_from_issue
            else f"RIDERS AND BENEFITS ACTIVE ON THE POLICY AS OF {as_of}:"
        )
        for line in report.rider_lines:
            riders.add(f"    {line}")
        if report.regulatory_lines:
            riders.blank()
            riders.add(
                f"MODELED ISSUE OPENING REGULATORY LIMITS ({as_of}):"
                if report.run_from_issue
                else f"REGULATORY LIMITS FOR PREMIUMS AS OF {as_of} ARE AS FOLLOWS:"
            )
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

    if has_iul_history:
        history = _PageBuilder(report, total, total)
        _iul_historical_page(history, report)
        pages.append(history.lines)

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
        if report.basis_lines:
            lines[3:3] = [_center(line) for line in report.basis_lines]
        if index == 0:
            for paragraph in _EXPENSE_INTRO:
                lines.extend(wrap_lines(paragraph, PAGE_WIDTH))
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


def format_abr_quote_pages(run, policy) -> List[List[str]]:
    """Explanation page(s) for an ABR Quote run (``core/abr_quote.AbrQuoteRun``).

    The Report tab shows THIS instead of illustration pages — the quote's
    deliverable is the solved premium plus a plain statement of every
    illustration parameter the run reshaped to get it."""
    lines: List[str] = []
    run_date = datetime.now().strftime("%m/%d/%Y")
    lines.append((run_date + "ABR QUOTE".center(PAGE_WIDTH - 2 * len(run_date))).rstrip())
    lines.append(_center("THEORETICAL ANNUAL LEVEL PREMIUM TO MATURITY"))
    header_bits = [f"POLICY {policy.policy_number}" if policy.policy_number else "",
                   f"PLAN {policy.plancode}" if policy.plancode else ""]
    lines.append(_center("   ".join(bit for bit in header_bits if bit)))
    lines.append("")
    lines.append("-" * PAGE_WIDTH)
    lines.append("")

    def paragraph(text: str):
        lines.extend(justified_paragraph(text, PAGE_WIDTH))
        lines.append("")

    def bullet(text: str):
        wrapped = wrap_lines(text, PAGE_WIDTH)
        for index, wrapped_line in enumerate(wrapped):
            prefix = "  * " if index == 0 else "    "
            lines.append((prefix + wrapped_line)[:PAGE_WIDTH])
        lines.append("")

    first_payment = (run.first_payment_date.strftime("%m/%d/%Y")
                     if run.first_payment_date else "the next policy anniversary")
    rate_pct = f"{run.illustrated_rate * 100.0:.3f}%"

    lines.append("WHAT THIS RUN SOLVED")
    lines.append("")
    if run.shadow_premium is not None:
        paragraph(
            f"This run independently solved for the theoretical annual level premium that "
            f"carries the regular account to a ${ABR_TARGET_SV:,.0f} surrender value at "
            f"maturity and the annual level premium that carries the shadow account to "
            f"${ABR_TARGET_SV:,.0f} at maturity. The lower result is the official ABR "
            f"premium. Both solves use maturity age {int(policy.maturity_age)} and the ABR "
            f"interest rate of {rate_pct}. It is not an inforce illustration — several "
            f"illustration safeguards were deliberately turned off so that nothing limits "
            f"the annual premium.")
    else:
        paragraph(
            f"This run solved for the theoretical annual level premium that carries the policy to "
            f"maturity (age {int(policy.maturity_age)}) with a surrender value of "
            f"${ABR_TARGET_SV:,.0f} at maturity, credited at the ABR interest rate of {rate_pct}. "
            f"It is not an inforce illustration — several illustration safeguards were deliberately "
            f"turned off so that nothing limits the annual premium.")

    lines.append("RESULT")
    lines.append("")
    if run.shadow_premium is not None:
        paragraph(
            f"Regular-account annual premium: ${run.regular_premium:,.2f}. Shadow-account "
            f"annual premium: ${run.shadow_premium:,.2f}. Official annual level premium: "
            f"${run.premium:,.2f} (the lower {run.premium_basis}-account solve), first payment "
            f"on {first_payment}, then paid on each policy anniversary through maturity. "
            f"Under the official premium, surrender value at maturity is "
            f"${run.achieved_sv:,.2f} and shadow account value at maturity is "
            f"${run.achieved_shadow:,.2f}.")
    else:
        paragraph(
            f"Solved annual level premium: ${run.premium:,.2f}, first payment on {first_payment}, "
            f"then paid on each policy anniversary through maturity. Under that premium the "
            f"surrender value at maturity is ${run.achieved_sv:,.2f}.")

    if run.max_partial is not None:
        partial = run.max_partial
        lines.append("MAXIMUM PARTIAL ACCELERATION — NEXT MONTHLY DEDUCTION")
        lines.append("")
        paragraph(
            f"Minimum Face Amount Allowed: ${partial.minimum_face_amount:,.2f}. The locked "
            f"level death benefit used by the ABR forecast is "
            f"${partial.locked_death_benefit:,.2f}, producing a reduction proportion of "
            f"{partial.reduction_ratio:.6f}. The current account value was reduced by that "
            f"same proportion to ${partial.proportional_account_value:,.2f}.")
        paragraph(
            f"At the next monthly anniversary, {partial.monthly_deduction_date:%m/%d/%Y}, "
            f"the forecast used Face Amount ${partial.minimum_face_amount:,.2f}, Account "
            f"Value ${partial.account_value_used:,.2f}, and rate Band {partial.band}. The "
            f"resulting monthly deduction is ${partial.monthly_deduction:,.2f}.")

    lines.append("HOW THE ILLUSTRATION WAS CONFIGURED")
    lines.append("")
    bullet(
        f"ILLUSTRATED RATE: {rate_pct}, the ABR interest rate as entered on the Input tab. "
        f"For an ABR Quote the entry is not limited to the policy's current credited rate.")
    bullet(
        "CONFORM TO TEFRA/DEFRA: OFF. The 7702 guideline premium limits were not enforced — "
        "no guideline force-out and no cap on accepted premiums. Guideline premiums are not "
        "calculated or used for an ABR quote.")
    bullet(
        "CONFORM TO TAMRA: OFF. The 7-pay (MEC) premium limit did not cap the premium.")
    bullet(
        "MINIMUM PREMIUM / LAPSE TEST: DISABLED. The policy is never lapsed for failing the "
        "minimum-premium (safety net) or surrender-value tests. The account value and "
        "surrender value are allowed to run negative until the first annual premium is paid.")
    bullet(
        f"PREMIUM MODE: switched to ANNUAL. The solved premium pays once each policy year on "
        f"the anniversary, starting {first_payment}. No premium is collected between the "
        f"forecast date and that first annual payment.")
    if run.loan_retired > 0:
        bullet(
            f"POLICY LOAN: the account value was immediately reduced by the current policy "
            f"debt of ${run.loan_retired:,.2f} and the policy debt was set to $0 — the "
            f"projection runs loan-free.")
    else:
        bullet("POLICY LOAN: the policy carries no loan — no adjustment was needed.")
    if run.db_option_switched:
        bullet(
            "DEATH BENEFIT OPTION: the policy's Option B (increasing) death benefit was "
            "switched to Option A (level) on the first forecast month. The death benefit is "
            "kept level at the switch, so the solve ran on a level death benefit equal to the "
            "specified amount plus the account value at the change.")
    else:
        bullet(
            "DEATH BENEFIT OPTION: the policy already has a level death benefit (Option A) — "
            "no change was needed.")

    lines.append("-" * PAGE_WIDTH)
    paragraph(
        "The monthly projection behind this solve is available on the Values tab. The "
        "illustration report pages are intentionally not produced for an ABR Quote.")
    return [lines]


class IllustrationReportTab(QWidget):
    """Scrollable print-preview of the UL illustration report."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._report: Optional[IllustrationReport] = None
        self._guaranteed_error: Optional[str] = None
        # ABR Quote explanation pages (display_abr_quote) — mutually exclusive
        # with _report; the tab shows one or the other.
        self._abr_pages: Optional[List[List[str]]] = None
        self.setStyleSheet(f"background-color: {PURPLE_BG};")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(6)

        top_row = QHBoxLayout()
        top_row.setSpacing(6)
        self.status_label = QLabel("")
        self.status_label.setStyleSheet(REPORT_LABEL_STYLE)
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
        self.print_pdf_btn.setStyleSheet(PRINT_BUTTON_STYLE)
        self.print_pdf_btn.clicked.connect(self._on_print_pdf)
        top_row.addWidget(self.print_pdf_btn)
        layout.addLayout(top_row)

        # ── Output folder row (persisted across sessions) ──
        folder_row = QHBoxLayout()
        folder_row.setSpacing(6)
        folder_label = QLabel("Output folder:")
        folder_label.setStyleSheet(REPORT_LABEL_STYLE)
        folder_row.addWidget(folder_label)
        self.output_folder_edit = QLineEdit()
        self.output_folder_edit.setPlaceholderText("Prompt for a folder each time (not set)")
        self.output_folder_edit.setToolTip(
            "Folder where illustration PDFs are saved. Saved across sessions.")
        self.output_folder_edit.setStyleSheet(OUTPUT_FOLDER_EDIT_STYLE)
        self.output_folder_edit.editingFinished.connect(self._on_output_folder_edited)
        folder_row.addWidget(self.output_folder_edit, 1)
        self.browse_folder_btn = QPushButton("Browse…")
        self.browse_folder_btn.setToolTip("Choose the folder illustration PDFs are saved to.")
        self.browse_folder_btn.setStyleSheet(REPORT_BUTTON_STYLE)
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
        self._abr_pages = None
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

    def capture_session_state(self) -> Optional[dict]:
        """Snapshot the displayed content (report pages OR an ABR Quote
        explanation) for the main window's per-policy session cache."""
        if self._abr_pages is not None:
            return {"kind": "abr", "pages": self._abr_pages}
        if self._report is not None:
            return {"kind": "report", "report": self._report,
                    "guaranteed_error": self._guaranteed_error}
        return None

    def restore_session_state(self, state: Optional[dict]) -> bool:
        """Re-render a captured snapshot; False leaves the tab for the caller
        to clear."""
        if not state:
            return False
        if state.get("kind") == "abr" and state.get("pages"):
            self.display_abr_quote(state["pages"])
            return True
        if state.get("kind") == "report" and state.get("report") is not None:
            self.display_report(state["report"], state.get("guaranteed_error"))
            return True
        return False

    def _add_sheet(self, lines: List[str]):
        self._sheet_layout.addWidget(report_sheet(lines))

    def display_abr_quote(self, pages: List[List[str]]):
        """Show the ABR Quote solve explanation instead of illustration pages
        (``format_abr_quote_pages``). Print to PDF stays disabled — there is
        no illustration report behind an ABR Quote."""
        self.clear("")
        self._abr_pages = pages
        for lines in pages:
            self._add_sheet(lines)
        self.status_label.setText(
            "ABR Quote — explanation of the premium solve (no illustration "
            "report is produced).")

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
            self._add_sheet(lines)
        guaranteed_note = (
            "" if report.has_guaranteed_values
            else "  Guaranteed columns are not projected."
        )
        self.status_label.setText(
            f"UL illustration report - {len(pages)} pages.{guaranteed_note}")

    # ── Add Expense Report toggle ───────────────────────────────────────

    @staticmethod
    def _load_expense_page_setting() -> bool:
        settings = read_json(_settings_file(), default={}) or {}
        return bool(settings.get(_EXPENSE_PAGE_KEY, False))

    def _on_expense_report_toggled(self, checked: bool) -> None:
        settings = read_json(_settings_file(), default={}) or {}
        settings[_EXPENSE_PAGE_KEY] = bool(checked)
        try:
            write_json(_settings_file(), settings)
        except OSError:
            pass  # cosmetic preference — never block the toggle on disk errors
        # Re-render the held report with/without the supplemental page; no
        # engine round trip needed.
        if self._report is not None:
            self.display_report(self._report, self._guaranteed_error)

    # ── Print to PDF ────────────────────────────────────────────────────

    @staticmethod
    def _load_output_folder() -> str:
        settings = read_json(_settings_file(), default={}) or {}
        folder = settings.get(OUTPUT_FOLDER_KEY, "")
        return folder if isinstance(folder, str) else ""

    def _save_output_folder(self, folder: str) -> None:
        settings = read_json(_settings_file(), default={}) or {}
        settings[OUTPUT_FOLDER_KEY] = folder
        try:
            write_json(_settings_file(), settings)
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
        policy = (getattr(report, "policy_number", "") or "") if report else ""
        plancode = (getattr(report, "plancode", "") or "") if report else ""
        return default_pdf_name(policy, plancode, datetime.now())

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
        return pdf_printer(path)

    @staticmethod
    def _print_document(
        report: IllustrationReport,
        printer: QPrinter,
        include_expense_report: bool = False,
    ) -> QTextDocument:
        """Lay the report out as a paginated QTextDocument for the printer."""
        pages = format_report_pages(report, include_expense_report=include_expense_report)
        return pages_document(pages, printer)

    @staticmethod
    def write_pdf(report: IllustrationReport, path: str, include_expense_report: bool = False):
        """Render the fixed-width report pages to a landscape PDF file."""
        printer = IllustrationReportTab._pdf_printer(path)
        document = IllustrationReportTab._print_document(
            report, printer, include_expense_report=include_expense_report)
        document.print(printer)


def format_report_pages(
    report: IllustrationReport,
    include_expense_report: bool = False,
) -> List[List[str]]:
    """Interpret the report page spec into fixed-width text pages."""
    spec = PageSpec(
        name="ul_report_pages",
        render=lambda rpt, include: _format_report_pages_from_specs(rpt, include),
    )
    pages = spec.interpret(report, include_expense_report)
    return [] if pages is None else pages
