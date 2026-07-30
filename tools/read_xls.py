"""Dump a sheet of an ``.xls``/``.xlsx`` workbook to JSON (rows or a summary).

Auditable helper for reading reference spreadsheets such as
``docs/COBOLDB2translation.xls`` (the DB2 column <-> COBOL name mapping) without
a spreadsheet app, so mappings can be cross-referenced during policy-record
build-out.

Usage::

    venv\\Scripts\\python.exe tools/read_xls.py '{"path": "docs/COBOLDB2translation.xls"}'
    venv\\Scripts\\python.exe tools/read_xls.py '{"path": "...", "sheet": 0, "limit": 25}'
    venv\\Scripts\\python.exe tools/read_xls.py '{"path": "...", "sheet": "Sheet1", "find": "LST_ACT_TRS_DT"}'
    venv\\Scripts\\python.exe tools/read_xls.py path.xls Sheet1 SEARCH 25

Config keys:
    path   -- workbook path (required)
    sheet  -- sheet name or 0-based index (default: first sheet). Omit to list
              all sheet names + dimensions only.
    limit  -- max data rows to print (default: 20; use 0 for all)
    find   -- optional case-insensitive substring; only rows containing it in
              any cell are returned (ignores ``limit`` unless also set).
"""

import json
import os
import sys

import pandas as pd


def _read(path, sheet):
    ext = os.path.splitext(path)[1].lower()
    engine = "xlrd" if ext == ".xls" else None
    return pd.read_excel(path, sheet_name=sheet, engine=engine, dtype=str)


def main():
    if len(sys.argv) > 1 and sys.argv[1].lstrip().startswith("{"):
        cfg = json.loads(sys.argv[1])
    elif len(sys.argv) > 1:
        cfg = {"path": sys.argv[1]}
        if len(sys.argv) > 2:
            cfg["sheet"] = sys.argv[2]
        if len(sys.argv) > 3:
            cfg["find"] = sys.argv[3]
        if len(sys.argv) > 4:
            cfg["limit"] = int(sys.argv[4])
    else:
        cfg = {}
    path = cfg["path"]

    if "sheet" not in cfg:
        xl = pd.ExcelFile(path, engine="xlrd" if path.lower().endswith(".xls") else None)
        sheets = {}
        for name in xl.sheet_names:
            df = xl.parse(name, dtype=str, nrows=0)
            sheets[name] = list(df.columns)
        print(json.dumps({"ok": True, "path": path, "sheets": sheets}, indent=2))
        return

    sheet = cfg["sheet"]
    if isinstance(sheet, str) and sheet.isdigit():
        sheet = int(sheet)
    df = _read(path, sheet)
    df = df.fillna("")

    find = str(cfg.get("find") or "").strip().lower()
    if find:
        mask = df.apply(lambda r: any(find in str(v).lower() for v in r), axis=1)
        df = df[mask]

    limit = int(cfg.get("limit", 20))
    total = len(df)
    if limit and total > limit:
        df = df.head(limit)

    print(json.dumps({
        "ok": True,
        "path": path,
        "sheet": sheet,
        "columns": list(df.columns),
        "matched_rows": total,
        "shown_rows": len(df),
        "rows": df.to_dict(orient="records"),
    }, indent=2, default=str))


if __name__ == "__main__":
    main()
