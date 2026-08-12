"""Export the Values > Summary rows to a two-sheet debug workbook.

Testing Mode's "Export Summary" button writes a workbook with the authoritative
Summary projection (``core.summary_results``) for both the current-assumption
and guaranteed-assumption runs, one per sheet. Kept out of the UI so the
build/save/unique-name logic is testable without Qt.
"""
from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import Iterable, Optional

from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter
from openpyxl.worksheet.worksheet import Worksheet

from suiteview.illustration.core.summary_results import (
    ALL_COLUMNS,
    project_summary_rows,
)
from suiteview.illustration.models.calc_state import MonthlyState
from suiteview.illustration.models.policy_data import IllustrationPolicyData

CURRENT_SHEET = "SV_RERUN Debug (Cur)"
GUARANTEED_SHEET = "SV_RERUN Debug (Guar)"

_HEADER_FILL = PatternFill(start_color="2A1458", end_color="2A1458", fill_type="solid")
_HEADER_FONT = Font(color="FFFFFF", bold=True)
_DATE_FORMAT = "mm/dd/yyyy"


def _write_summary_sheet(
    ws: Worksheet,
    policy: IllustrationPolicyData,
    results: Optional[Iterable[MonthlyState]],
) -> None:
    """Write the Summary header + rows and freeze the header row and Date column."""
    ws.append(list(ALL_COLUMNS))
    for cell in ws[1]:
        cell.fill = _HEADER_FILL
        cell.font = _HEADER_FONT
        cell.alignment = Alignment(horizontal="center")

    rows = project_summary_rows(policy, results) if results else []
    date_column = ALL_COLUMNS.index("Date") + 1
    for row in rows:
        ws.append([row[column] for column in ALL_COLUMNS])
        ws.cell(row=ws.max_row, column=date_column).number_format = _DATE_FORMAT

    # Freeze the header row and the leading locator columns through Attained
    # Age: the top-left unfrozen cell is one row down and one column right.
    freeze_column = ALL_COLUMNS.index("Attained Age") + 1
    ws.freeze_panes = f"{get_column_letter(freeze_column + 1)}2"

    for index, column in enumerate(ALL_COLUMNS, start=1):
        ws.column_dimensions[get_column_letter(index)].width = max(10, len(column) + 2)


def build_summary_workbook(
    policy: IllustrationPolicyData,
    current_results: Optional[Iterable[MonthlyState]],
    guaranteed_results: Optional[Iterable[MonthlyState]],
) -> Workbook:
    """Build the two-sheet Summary workbook (Cur then Guar)."""
    wb = Workbook()
    ws_current = wb.active
    ws_current.title = CURRENT_SHEET
    _write_summary_sheet(ws_current, policy, current_results)

    ws_guaranteed = wb.create_sheet(GUARANTEED_SHEET)
    _write_summary_sheet(ws_guaranteed, policy, guaranteed_results)
    return wb


def summary_filename_base(policy: IllustrationPolicyData, when: Optional[date] = None) -> str:
    """Company / policy / date stem, e.g. ``01-S1362606-20260810``."""
    when = when or date.today()
    return f"{policy.company_code}-{policy.policy_number}-{when:%Y%m%d}"


def unique_workbook_path(folder: Path, base: str, ext: str = ".xlsx") -> Path:
    """Return a non-existing path, disambiguating collisions with ``(2)``, ``(3)``…"""
    candidate = folder / f"{base}{ext}"
    counter = 2
    while candidate.exists():
        candidate = folder / f"{base}({counter}){ext}"
        counter += 1
    return candidate


def export_summary_workbook(
    policy: IllustrationPolicyData,
    current_results: Optional[Iterable[MonthlyState]],
    guaranteed_results: Optional[Iterable[MonthlyState]],
    folder: str | Path,
    when: Optional[date] = None,
) -> Path:
    """Build and save the Summary workbook in *folder*; return the saved path."""
    wb = build_summary_workbook(policy, current_results, guaranteed_results)
    path = unique_workbook_path(Path(folder), summary_filename_base(policy, when))
    wb.save(path)
    return path
