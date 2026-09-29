r"""Save a read-only .xlsm copy of an .xlsb workbook so openpyxl tools can read it.

Usage:
    venv\Scripts\python.exe tools\office\convert_xlsb_copy.py '{"source": "<xlsb>", "dest": "<new.xlsm>"}'

Opens the source in a new isolated Excel instance, read-only, with macros
force-disabled, events off and external links not updated, then saves a copy
(xlsm, VBA kept) to ``dest``. The source is never saved. ``dest`` must not
exist and must not be in the source's folder. Prints JSON.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "rerun"))

from rerun_com import _open_excel  # noqa: E402  (isolated instance, macros disabled)

XL_XLSM = 52


def main() -> None:
    arg = sys.argv[1]
    cfg = json.loads(Path(arg[1:]).read_text(encoding="utf-8-sig")) if arg.startswith("@") else json.loads(arg)
    source = Path(cfg["source"]).resolve()
    dest = Path(cfg["dest"]).resolve()
    if not source.is_file():
        raise SystemExit(f"Source not found: {source}")
    if dest.exists():
        raise SystemExit(f"Destination already exists: {dest}")
    if dest.parent == source.parent:
        raise SystemExit("Destination must not be in the source workbook's folder.")
    dest.parent.mkdir(parents=True, exist_ok=True)

    xl = _open_excel()
    try:
        wb = xl.Workbooks.Open(str(source), UpdateLinks=0, ReadOnly=True, IgnoreReadOnlyRecommended=True)
        try:
            sheets = [ws.Name for ws in wb.Worksheets]
            wb.SaveAs(str(dest), FileFormat=XL_XLSM)
        finally:
            wb.Close(SaveChanges=False)
    finally:
        xl.Quit()
    print(json.dumps({"source": str(source), "dest": str(dest), "sheets": sheets}, indent=1))


if __name__ == "__main__":
    main()
