"""Inspect a rerun_vs_app comparison workbook around failing months.

Reads a comparison workbook produced by tools/rerun/compare_rerun_vs_app.py and, for
one case sheet, prints the RERUN | App | Δ triplets for the requested fields
over a vid window — the drill-down step after the summary flags a field.

Usage (single JSON arg):
    venv\\Scripts\\python.exe tools/rerun/inspect_comparison_deltas.py '<json>'

    {"workbook": "C:/.../rerun_vs_app_....xlsx",
     "sheet": "Case30_UE002044",     # or "case": 30 (matches sheet prefix)
     "fields": ["Fee", "Loan Balance"],   # group labels; [] = all failing
     "vid_lo": 110, "vid_hi": 130}
"""
from __future__ import annotations

import json
import sys

import openpyxl


def main() -> None:
    cmd = json.loads(sys.argv[1])
    wb = openpyxl.load_workbook(cmd["workbook"], read_only=True, data_only=True)

    sheet = cmd.get("sheet")
    if not sheet:
        prefix = f"Case{cmd['case']}_"
        sheet = next(s for s in wb.sheetnames if s.startswith(prefix))
    ws = wb[sheet]

    # Map group label (row 2, triplet start col) -> (rerun, app, delta) columns.
    triplets: dict[str, tuple[int, int, int]] = {}
    for c in range(4, ws.max_column + 1):
        v = ws.cell(row=2, column=c).value
        if v not in (None, ""):
            label = str(v).replace(" (ref)", "").strip()
            triplets[label] = (c, c + 1, c + 2)

    want = cmd.get("fields") or list(triplets)
    missing = [f for f in want if f not in triplets]
    lo, hi = int(cmd.get("vid_lo", 1)), int(cmd.get("vid_hi", 10**9))

    rows_out = []
    for r in range(4, ws.max_row + 1):
        vid = ws.cell(row=r, column=1).value
        if vid is None:
            break
        vid = int(vid)
        if not lo <= vid <= hi:
            continue
        rec: dict[str, object] = {
            "vid": vid,
            "year": ws.cell(row=r, column=2).value,
            "month": ws.cell(row=r, column=3).value,
        }
        for f in want:
            if f not in triplets:
                continue
            rc, ac, dc = triplets[f]
            rec[f] = {"rerun": ws.cell(row=r, column=rc).value,
                      "app": ws.cell(row=r, column=ac).value,
                      "delta": ws.cell(row=r, column=dc).value}
        rows_out.append(rec)

    print(json.dumps({"sheet": sheet, "fields": want,
                      "missing_fields": missing, "rows": rows_out},
                     indent=1, default=str))


if __name__ == "__main__":
    main()
