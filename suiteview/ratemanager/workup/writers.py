"""Output writers for the Rate Workup — CSV folder or one review workbook."""

from __future__ import annotations

import csv
import os
from typing import Dict, List, Tuple


def write_csv(path: str, headers: List[str], rows: List[list]) -> None:
    # utf-8-sig so Excel opens the CSVs with correct encoding detection.
    with open(path, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        w.writerow(headers)
        w.writerows(rows)


def write_workbook(path: str, sheets: "Dict[str, Tuple[List[str], List[list]]]") -> None:
    """One workbook, one sheet per table (write-only for large row counts)."""
    from openpyxl import Workbook
    from openpyxl.cell import WriteOnlyCell
    from openpyxl.styles import Alignment, Font

    header_font = Font(bold=True)
    center = Alignment(horizontal="center")

    wb = Workbook(write_only=True)
    for name, (headers, rows) in sheets.items():
        ws = wb.create_sheet(name[:31])
        header_cells = []
        for h in headers:
            cell = WriteOnlyCell(ws, value=h)
            cell.font = header_font
            cell.alignment = center
            header_cells.append(cell)
        ws.append(header_cells)
        for row in rows:
            ws.append(row)
    wb.save(path)


def write_summary(path: str, lines: List[str]) -> None:
    with open(path, "w", encoding="utf-8-sig") as f:
        f.write("\n".join(lines) + "\n")


def fmt_rate(value) -> str:
    """Uniform 6-decimal rate formatting for CSV output ('' for None)."""
    return f"{value:.6f}" if value is not None else ""


def ensure_dir(path: str) -> str:
    os.makedirs(path, exist_ok=True)
    return path
