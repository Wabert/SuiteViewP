"""Load a RERUN Saved Case, recalc, and report the first Excel-error cells per column.

Excel error values surface through COM as large negative ints (xlErrNA =
-2146826246 etc.); this scans a CalcEngine block for them so a failing VLOOKUP
can be localized without opening Excel.

Usage (single JSON arg):
    venv\\Scripts\\python.exe tools/rerun_find_errors.py '<json>'
    {"workbook": "<path>", "case": 7, "max_month": 24,
     "first_col": "A", "last_col": "IZ", "sheet": "CalcEngine", "first_row": 6}
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from openpyxl.utils import get_column_letter, column_index_from_string  # noqa: E402
from rerun_com import (  # noqa: E402
    _open_excel, _temp_copy, _write_named_range, _enable_iteration,
    read_case_inputs, XL_CALC_MANUAL,
)

XL_ERRORS = {
    -2146826281: "#DIV/0!", -2146826246: "#N/A", -2146826259: "#NAME?",
    -2146826288: "#NULL!", -2146826252: "#NUM!", -2146826265: "#REF!",
    -2146826273: "#VALUE!",
}


def main():
    cmd = json.loads(sys.argv[1])
    workbook = str(Path(cmd["workbook"]).resolve())
    sheet = cmd.get("sheet", "CalcEngine")
    first_row = int(cmd.get("first_row", 6))
    max_month = int(cmd.get("max_month", 24))
    c_lo = column_index_from_string(cmd.get("first_col", "A"))
    c_hi = column_index_from_string(cmd.get("last_col", "IZ"))

    pairs, _src = read_case_inputs(workbook, cmd["case"])
    tmp = _temp_copy(workbook)
    xl = _open_excel()
    report = {"errors_by_col": {}, "input_failures": []}
    try:
        _enable_iteration(xl)
        wb = xl.Workbooks.Open(str(tmp), UpdateLinks=0, ReadOnly=False)
        xl.Calculation = XL_CALC_MANUAL
        for name, values in pairs:
            try:
                _write_named_range(wb, name, values)
            except Exception as exc:
                report["input_failures"].append({"name": name, "error": str(exc)})
        xl.CalculateFull()

        ws = wb.Worksheets(sheet)
        r_lo, r_hi = first_row, first_row + max_month - 1
        block = ws.Range(ws.Cells(r_lo, c_lo), ws.Cells(r_hi, c_hi)).Value
        for r_off, row in enumerate(block):
            for c_off, val in enumerate(row):
                if isinstance(val, int) and val in XL_ERRORS:
                    col = get_column_letter(c_lo + c_off)
                    if col not in report["errors_by_col"]:
                        report["errors_by_col"][col] = {
                            "first_month": r_off + 1, "error": XL_ERRORS[val]}
        wb.Close(SaveChanges=False)
    finally:
        xl.Quit()
        try:
            tmp.unlink()
        except OSError:
            pass
    print(json.dumps(report, indent=2, default=str))


if __name__ == "__main__":
    main()
