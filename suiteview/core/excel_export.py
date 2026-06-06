"""Shared "Dump to Excel" helper.

SuiteView's convention (see Agent.md) is that every "Excel"/"Export" button
opens a NEW unsaved workbook in a visible Excel instance via COM automation —
it never saves a file to disk. The COM lifecycle for that (dynamic dispatch,
disabling screen updating, bulk-writing a 2-D array, bolding/freezing the header,
auto-filter, auto-fit) was previously copy-pasted across many modules.

This module owns that fragile lifecycle in one place. Callers extract their own
data (from a DataFrame, a QTableWidget, etc.) into ``headers`` + ``rows`` and
delegate the Excel mechanics here.

Typical use::

    from suiteview.core.excel_export import dump_to_new_workbook, ExcelExportError

    try:
        excel, wb, ws = dump_to_new_workbook(headers, rows, sheet_name="Results")
        # optionally add more sheets via wb / format ws further...
    except ExcelExportError as e:
        QMessageBox.warning(self, "Excel Error", str(e))

Dynamic dispatch is used deliberately: it bypasses the ``win32com`` ``gen_py``
static cache, which is a frequent source of COM corruption errors. Because of
that, callers do NOT need to clear the gen_py cache themselves.
"""

from __future__ import annotations

from typing import Iterable, Sequence, Tuple


class ExcelExportError(Exception):
    """Raised when an Excel COM export cannot be completed."""


def open_excel(visible: bool = True):
    """Dispatch a (visible) Excel application via dynamic COM dispatch.

    Returns the Excel ``Application`` COM object. Raises ``ExcelExportError`` if
    ``win32com`` is unavailable or Excel cannot be started.
    """
    try:
        from win32com.client import dynamic
    except ImportError as e:
        raise ExcelExportError(
            "win32com is not available. Cannot export to Excel."
        ) from e

    try:
        excel = dynamic.Dispatch("Excel.Application")
        excel.Visible = visible
        return excel
    except Exception as e:  # COM / Excel launch failure
        raise ExcelExportError(f"Could not start Excel: {e}") from e


def write_table(
    ws,
    headers: Sequence,
    rows: Iterable[Sequence],
    *,
    bold_header: bool = True,
    freeze_header: bool = True,
    autofilter: bool = True,
    autofit: bool = True,
    text_col_indexes: Iterable[int] = None,
) -> int:
    """Write a single header+data table to an existing worksheet.

    ``rows`` is an iterable of row sequences; cell values should already be in
    their final form (the caller does any numeric cleaning / type coercion).
    ``text_col_indexes`` are 1-based column numbers to force to text format
    ("@") *before* writing — use this to preserve leading zeros in codes.

    Returns the total number of rows written (including the header).
    """
    headers = list(headers)
    col_count = len(headers)
    data_rows = [tuple(r) for r in rows]
    all_rows = [tuple(headers)] + data_rows
    total_rows = len(all_rows)

    if col_count == 0:
        return 0

    excel = ws.Application

    # Pre-format text columns before writing so Excel doesn't auto-convert them.
    for col_idx in (text_col_indexes or []):
        ws.Columns(col_idx).NumberFormat = "@"

    rng = ws.Range(ws.Cells(1, 1), ws.Cells(total_rows, col_count))
    rng.Value = all_rows

    if bold_header:
        ws.Range(ws.Cells(1, 1), ws.Cells(1, col_count)).Font.Bold = True

    if freeze_header:
        ws.Range("A2").Select()
        excel.ActiveWindow.FreezePanes = True

    if autofilter and total_rows > 1:
        ws.Range(ws.Cells(1, 1), ws.Cells(total_rows, col_count)).AutoFilter()

    if autofit:
        ws.Columns.AutoFit()

    return total_rows


def dump_to_new_workbook(
    headers: Sequence,
    rows: Iterable[Sequence],
    *,
    sheet_name: str = None,
    bold_header: bool = True,
    freeze_header: bool = True,
    autofilter: bool = True,
    autofit: bool = True,
    text_col_indexes: Iterable[int] = None,
    visible: bool = True,
) -> Tuple[object, object, object]:
    """Open a NEW unsaved Excel workbook and write a single table to sheet 1.

    Returns ``(excel, workbook, worksheet)`` so the caller can add more sheets,
    apply extra formatting, etc. The workbook is left unsaved and visible.

    Raises ``ExcelExportError`` on any failure (win32com missing, Excel launch
    failure, or a COM error while writing).
    """
    excel = open_excel(visible=visible)
    try:
        excel.ScreenUpdating = False
        wb = excel.Workbooks.Add()
        ws = wb.ActiveSheet
        if sheet_name:
            ws.Name = str(sheet_name)[:31]  # Excel sheet-name limit

        write_table(
            ws, headers, rows,
            bold_header=bold_header,
            freeze_header=freeze_header,
            autofilter=autofilter,
            autofit=autofit,
            text_col_indexes=text_col_indexes,
        )

        ws.Range("A1").Select()
        return excel, wb, ws
    except ExcelExportError:
        raise
    except Exception as e:
        raise ExcelExportError(f"Failed to dump to Excel: {e}") from e
    finally:
        try:
            excel.ScreenUpdating = True
        except Exception:
            pass
