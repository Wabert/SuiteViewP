"""Reconstruct a segment's sample HTML from the master build spreadsheet.

``docs/Policy Record/Policy Record html.xls`` has one sheet per policy-record
segment.  The right-most **"Final HTML"** column holds, row by row, the exact
HTML fragments that were concatenated to produce that segment's ``Sample 62xx
screen.htm``.  For segments that never got a standalone HTM (e.g. 66 - Advanced
Product) this is the only rendered source.

This helper joins the non-empty ``Final HTML`` cells top-to-bottom and writes a
UTF-8 ``.htm`` file the existing ``extract_policy_record_screen.py`` can parse.

Usage:
    python tools/extract_xls_final_html.py "{\"path\": \"docs/Policy Record/Policy Record html.xls\", \"sheet\": \"66 - Advanced Product\", \"out\": \"C:/tmp/segjson/sample_6266.htm\"}"
    python tools/extract_xls_final_html.py workbook.xls "66 - Advanced Product" output.htm
"""

import json
import os
import sys

import pandas as pd


def main():
    if len(sys.argv) > 1 and sys.argv[1].lstrip().startswith("{"):
        cfg = json.loads(sys.argv[1])
    else:
        cfg = {
            "path": sys.argv[1],
            "sheet": sys.argv[2],
            "out": sys.argv[3],
            "wrap_table": True,
        }
    path = cfg["path"]
    sheet = cfg["sheet"]
    out = cfg["out"]
    column = cfg.get("column", "Final HTML")

    engine = "xlrd" if path.lower().endswith(".xls") else None
    df = pd.read_excel(path, sheet_name=sheet, engine=engine, dtype=str)
    df = df.fillna("")

    if column not in df.columns:
        print(json.dumps({"error": f"column {column!r} not found",
                          "columns": list(df.columns)}))
        return 2

    cells = [str(v) for v in df[column].tolist() if str(v).strip()]
    html = "\n".join(cells)
    if cfg.get("wrap_table"):
        html = "<table>\n" + html + "\n</table>"

    os.makedirs(os.path.dirname(out), exist_ok=True)
    with open(out, "w", encoding="utf-8") as fh:
        fh.write(html)

    print(json.dumps({
        "ok": True,
        "out": out,
        "cells": len(cells),
        "chars": len(html),
        "has_title": "title=" in html,
        "has_byte": ">Byte<" in html or ">Byte</" in html,
        "has_cobol": "COBOL:" in html,
        "has_db2": "DB2:" in html,
        "tables": html.lower().count("<table"),
    }))
    return 0


if __name__ == "__main__":
    sys.exit(main())
