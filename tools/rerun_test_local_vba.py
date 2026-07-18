"""End-to-end test of RERUN's in-workbook Local data path (VBA + bridge).

Opens a TEMP COPY of the installed local workbook with macros ENABLED, sets
INPUT!sDataSource / policy number, runs the real macros
(GetPolicyFromCyberlife -> local branch, MainGetRates -> local branch),
recalcs, and dumps CalcEngine columns to CSV — the same shape as
tools/rerun_com.py run mode, so the result can be diffed against a Saved-Case
run of the same policy.  Also scans the dump for Excel error values.

Usage (single JSON arg):
    venv\\Scripts\\python.exe tools/rerun_test_local_vba.py '<json>'
    {"workbook": "docs/Illustration_UL/RERUN (v20.0) local.xlsm",
     "policy": "U0375726", "region": "CKPR",
     "data_source": "Local",              # or "Local (no benefits)"
     "out_csv": "<path>", "max_month": 360, "cols": ["B","C","D","G","AL","AM"]}
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from openpyxl.utils import column_index_from_string  # noqa: E402
from rerun_com import (  # noqa: E402
    _temp_copy, _enable_iteration, CALC_FIRST_ROW, DEFAULT_COLS, XL_CALC_MANUAL,
)

XL_ERR_MIN, XL_ERR_MAX = -2146826288, -2146826246  # xlErr* COM range


def _open_excel_macros_on(visible: bool = False):
    import win32com.client

    xl = win32com.client.DispatchEx("Excel.Application")
    xl.Visible = visible
    xl.DisplayAlerts = False
    xl.ScreenUpdating = False
    try:
        # Workbook/app event handlers off — mirrors rerun_com; interactive use
        # has them on, but automation must not stall on event side effects.
        # (Do NOT set Interactive=False — it deadlocks WScript.Shell waits.)
        xl.EnableEvents = False
    except Exception:
        pass
    # msoAutomationSecurityLow = 1 — macros run (this is the point of the test).
    xl.AutomationSecurity = 1
    return xl


def main():
    cmd = json.loads(sys.argv[1])
    workbook = Path(cmd.get("workbook")
                    or Path(__file__).resolve().parents[1] / "docs" / "Illustration_UL"
                    / "RERUN (v20.0) local.xlsm").resolve()
    cols = cmd.get("cols", DEFAULT_COLS)
    max_month = int(cmd.get("max_month", 360))
    out_csv = cmd.get("out_csv")

    tmp = _temp_copy(str(workbook))
    xl = _open_excel_macros_on(visible=bool(cmd.get("visible")))
    report = {"workbook": str(workbook), "policy": cmd["policy"],
              "data_source": cmd.get("data_source", "Local")}
    try:
        _enable_iteration(xl)
        wb = xl.Workbooks.Open(str(tmp), UpdateLinks=0, ReadOnly=False)
        xl.Calculation = XL_CALC_MANUAL

        wb.Names("sDataSource").RefersToRange.Value = cmd.get("data_source", "Local")
        wb.Names("sCyberlifePolicyNumber").RefersToRange.Value = cmd["policy"]
        wb.Names("sQueryRegion").RefersToRange.Value = cmd.get("region", "CKPR")

        xl.Run("GetPolicyFromCyberlife")
        report["policy_pulled"] = str(wb.Names("sPlancode").RefersToRange.Value)
        xl.Run("MainGetRates")
        report["plancodes_present"] = [
            str(v) for v in _flatten(wb.Names("vPlancodesPresent").RefersToRange.Value) if v]

        xl.CalculateFull()

        ce = wb.Worksheets("CalcEngine")
        col_idx = [column_index_from_string(c) for c in cols]
        c_lo, c_hi = min(col_idx), max(col_idx)
        r_lo, r_hi = CALC_FIRST_ROW, CALC_FIRST_ROW + max_month - 1
        block = ce.Range(ce.Cells(r_lo, c_lo), ce.Cells(r_hi, c_hi)).Value

        rows, n_errors = [], 0
        for r_off, row in enumerate(block):
            rec = {"month": r_off + 1}
            for c, ci in zip(cols, col_idx):
                v = row[ci - c_lo]
                if isinstance(v, int) and XL_ERR_MIN <= v <= XL_ERR_MAX:
                    n_errors += 1
                rec[c] = v
            rows.append(rec)
        report["rows_dumped"] = len(rows)
        report["excel_error_cells"] = n_errors

        if out_csv:
            import csv

            with open(out_csv, "w", newline="", encoding="utf-8") as fh:
                w = csv.writer(fh)
                w.writerow(["month"] + cols)
                for rec in rows:
                    w.writerow([rec["month"]] + [rec[c] for c in cols])
            report["out_csv"] = out_csv
        else:
            report["rows"] = rows[:12]

        wb.Close(SaveChanges=False)
    finally:
        xl.Quit()
        try:
            tmp.unlink()
        except OSError:
            pass
    print(json.dumps(report, indent=2, default=str))


def _flatten(v):
    if isinstance(v, tuple):
        out = []
        for x in v:
            out.extend(_flatten(x))
        return out
    return [v]


if __name__ == "__main__":
    main()
