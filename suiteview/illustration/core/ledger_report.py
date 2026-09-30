"""Annual-ledger illustration pages in RERUN's UL report style, for fixed-premium products.

A ``LedgerReport`` is everything printed on the pages: a header on every page (run date,
company, page x of y, title, optional subtitle, prepared-for line), a cover page (the
disclaimer, the insured, a two-column policy block and "THIS ILLUSTRATION ASSUMES THE
FOLLOWING"), annual ledger pages in five-row blocks under GUARANTEED / NON-GUARANTEED
banners with notes under the last one, and a notes page ending with OTHER COVERAGE.
``format_ledger_pages`` lays it out as fixed-width text lines; the page is as wide as
the ledger (at least the UL pages' 112 characters) and prints landscape
(``ui/report_pages.py``). Par whole life (``core/parwl/report.py``) and indeterminate
premium term (``core/term/report.py``) build their reports on it.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Callable, List, Optional, Sequence, Tuple

from suiteview.illustration.core.report_text import center_line, justified_paragraph, wrap_lines

MIN_PAGE_WIDTH = 112
LEDGER_ROWS_PER_PAGE = 30
GROUP_GAP = 2
GROUP_GUARANTEED = "GUARANTEED VALUES"
GROUP_NON_GUARANTEED = "NON-GUARANTEED VALUES"
MODE_LABELS = {12: "ANNUAL", 6: "SEMI-ANNUAL", 3: "QUARTERLY", 1: "MONTHLY"}
ILLUSTRATION_DISCLAIMER = (
    "THIS IS AN ILLUSTRATION ONLY. AN ILLUSTRATION IS NOT INTENDED TO PREDICT ACTUAL PERFORMANCE. "
    "ACTUAL RESULTS MAY DIFFER FROM THE ILLUSTRATED VALUES SHOWN IN THIS ILLUSTRATION AND MAY BE "
    "MORE OR LESS FAVORABLE. VALUES SET FORTH IN THE ILLUSTRATION ARE NOT GUARANTEED, EXCEPT FOR "
    "THOSE ITEMS CLEARLY LABELED AS GUARANTEED."
)


@dataclass(frozen=True)
class LedgerColumn:
    """One ledger column: three stacked header lines, width, decimals and banner group."""

    key: str
    headers: Tuple[str, str, str]
    width: int
    value: Callable[[object], float]
    decimals: int = 0
    group: str = ""
    integer: bool = False               # age / year: printed as a whole number


@dataclass
class LedgerReport:
    """Everything printed on a fixed-premium product's illustration pages."""

    run_date: date
    company_name: str
    title: str
    subtitle: str
    prepared_for: str
    policy_number: str
    plancode: str
    insured: str
    policy_block: List[Tuple[str, str]]
    assumption_lines: List[str]
    columns: Tuple[LedgerColumn, ...]
    rows: List[object]
    ledger_notes: List[str]
    note_paragraphs: List[str]
    other_coverage: List[str]
    disclaimer: str = ILLUSTRATION_DISCLAIMER
    width: int = MIN_PAGE_WIDTH


def long_date(when: Optional[date]) -> str:
    return f"{when:%B} {when.day}, {when.year}".upper() if when else ""


def short_date(when: Optional[date]) -> str:
    return f"{when:%m/%d/%Y}" if when else ""


def plain_name(text: str) -> str:
    """A name from a reference table in capitals with its spacing collapsed."""
    return " ".join((text or "").split()).upper()


def page_width(columns: Sequence[LedgerColumn]) -> int:
    """The page width a ledger needs: its columns and group gaps, at least ``MIN_PAGE_WIDTH``."""
    width, group = 0, None
    for column in columns:
        if group is not None and column.group != group:
            width += GROUP_GAP
        width += column.width
        group = column.group
    return max(MIN_PAGE_WIDTH, width)


def two_column_block(left: List[str], right: List[str]) -> List[Tuple[str, str]]:
    rows = max(len(left), len(right))
    return list(zip(left + [""] * (rows - len(left)), right + [""] * (rows - len(right))))


def _header(report: LedgerReport, page_no: int, total: int) -> List[str]:
    width = report.width
    left, right = short_date(report.run_date), f"Page {page_no} of {total}"
    middle = report.company_name
    pad = width - len(left) - len(right)
    lines = [left + middle.center(max(pad, len(middle))) + right, center_line(report.title, width)]
    if report.subtitle:
        lines.append(center_line(report.subtitle, width))
    lines += [center_line(report.prepared_for, width), ""]
    return lines


def ledger_header(columns: Sequence[LedgerColumn], width: int) -> List[str]:
    """Group banners (``+-- GUARANTEED VALUES --+``), three stacked header rows and a rule."""
    rows = ["", "", ""]
    spans: List[list] = []          # [group, start, end] of each run of same-group columns
    position = 0
    for column in columns:
        if spans and spans[-1][0] != column.group:
            position += GROUP_GAP
            rows = [row + " " * GROUP_GAP for row in rows]
        if not spans or spans[-1][0] != column.group:
            spans.append([column.group, position, position])
        rows = [row + f"{text:>{column.width}}" for row, text in zip(rows, column.headers)]
        position += column.width
        spans[-1][2] = position
    banner = ""
    for name, start, end in spans:
        if not name:
            continue
        span = end - start
        label = f" {name} "
        text = "+" + label.center(span - 2, "-") + "+" if span >= len(label) + 2 else name[:span]
        banner = banner.ljust(start) + text
    return [banner] + [row.rstrip() for row in rows] + ["-" * width]


def ledger_line(columns: Sequence[LedgerColumn], row: object) -> str:
    text, group = "", None
    for column in columns:
        if group is not None and column.group != group:
            text += " " * GROUP_GAP
        group = column.group
        value = column.value(row)
        if column.integer:
            cell = f"{int(value)}"
        elif column.decimals:
            cell = f"{max(value, 0.0):,.{column.decimals}f}"
        else:
            cell = f"{max(value, 0.0):,.0f}"
        text += f"{cell:>{column.width}}"
    return text.rstrip()


def format_ledger_pages(report: LedgerReport) -> List[List[str]]:
    """The report as pages of fixed-width text lines (cover, ledger pages, notes)."""
    width = report.width
    chunks = [report.rows[i:i + LEDGER_ROWS_PER_PAGE] for i in range(0, len(report.rows), LEDGER_ROWS_PER_PAGE)]
    chunks = chunks or [[]]
    total = 2 + len(chunks)
    pages: List[List[str]] = []

    cover = _header(report, 1, total)
    cover += justified_paragraph(report.disclaimer, width)
    cover.append("")
    cover.append(f"  INSURED:  {report.insured}")
    cover.append("")
    left_width = max(58, max((len(left) for left, _right in report.policy_block), default=0) + 4)
    for left, right in report.policy_block:
        cover.append(f"  {left:<{left_width}}{right}".rstrip()[:width])
    cover.append("")
    cover.append("THIS ILLUSTRATION ASSUMES THE FOLLOWING:")
    for line in report.assumption_lines:
        wrapped = wrap_lines(line, width - 6)
        cover.append(f"    {wrapped[0]}")
        cover += [f"      {rest}" for rest in wrapped[1:]]
    pages.append(cover)

    header = ledger_header(report.columns, width)
    for index, chunk in enumerate(chunks):
        page = _header(report, 2 + index, total) + header
        for row_index, row in enumerate(chunk):
            page.append(ledger_line(report.columns, row))
            if (row_index + 1) % 5 == 0 and row_index + 1 < len(chunk):
                page.append("")
        if index == len(chunks) - 1:
            for note in report.ledger_notes:
                page.append("")
                page += wrap_lines(note, width)
        pages.append(page)

    notes = _header(report, total, total)
    for paragraph in report.note_paragraphs:
        notes += justified_paragraph(paragraph, width)
        notes.append("")
    notes.append("OTHER COVERAGE:")
    for line in report.other_coverage:
        notes.append(f"    {line}"[:width])
    pages.append(notes)
    return pages
