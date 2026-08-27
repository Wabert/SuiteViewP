"""Inspect a RERUN workbook: required defined names + populated Saved Cases slots.

Reads its JSON config from a FILE (path passed as the sole argument) to avoid
shell quoting problems with workbook paths that contain spaces/backslashes.

Usage:
    venv\\Scripts\\python.exe tools/rerun/inspect_rerun_workbook.py <config.json>
    config.json: {"workbook": "<path>"}
"""
from __future__ import annotations

import json
import sys

import openpyxl
from openpyxl.utils import get_column_letter

NAMES_OF_INTEREST = [
    "sCyberlifePolicyNumber", "sQueryRegion", "sDataSource", "sCompany",
    "sStorageNumber", "sPlancode", "sINPUT_CaseID", "sINPUT_Policy_Number",
]


def main() -> None:
    with open(sys.argv[1], "r", encoding="utf-8-sig") as fh:
        cfg = json.load(fh)
    workbook = cfg["workbook"]

    wb = openpyxl.load_workbook(workbook, read_only=False, data_only=True, keep_vba=True)

    defined = set(wb.defined_names.keys())
    names = {n: (n in defined) for n in NAMES_OF_INTEREST}

    ws = wb["Saved Cases"]
    populated = []
    for c in range(3, min(ws.max_column, 40) + 1):
        hdr = ws.cell(row=1, column=c).value
        if hdr is not None and str(hdr).strip() != "":
            populated.append({"col": get_column_letter(c), "header": hdr})

    # First 3 data columns' row-1 header to confirm empty
    first_cols = {get_column_letter(c): ws.cell(row=1, column=c).value for c in range(1, 6)}

    print(json.dumps({
        "workbook": workbook,
        "sheets_present": "Saved Cases" in wb.sheetnames and "INPUT" in wb.sheetnames,
        "names_present": names,
        "saved_cases_populated": populated,
        "saved_cases_max_col": get_column_letter(ws.max_column),
        "row1_first_cols": {k: str(v) for k, v in first_cols.items()},
    }, indent=2, default=str))
    wb.close()


if __name__ == "__main__":
    main()
