"""Diff the defined names (named ranges) of two workbooks.

Usage (single JSON arg):
    venv\\Scripts\\python.exe tools/office/compare_workbook_names.py '<json>'

    {"a": "<workbook A>", "b": "<workbook B>", "max_report": 40}

Named ranges drive RERUN's lookup targets, so a name that resolves to a
different range is a genuine calculation difference even when every formula
is byte-identical. Prints JSON: counts plus names only-in-A / only-in-B /
pointing at different refs.
"""
from __future__ import annotations

import json
import sys

import openpyxl


def _names(wb) -> dict:
    out = {}
    for name, defn in wb.defined_names.items():
        out[name] = str(getattr(defn, "value", ""))
    # sheet-local names
    for ws in wb.worksheets:
        local = getattr(ws, "defined_names", None)
        if not local:
            continue
        for name, defn in local.items():
            out[f"{ws.title}!{name}"] = str(getattr(defn, "value", ""))
    return out


def main() -> None:
    cmd = json.loads(sys.argv[1])
    cap = int(cmd.get("max_report", 40))

    wb_a = openpyxl.load_workbook(cmd["a"], data_only=False, read_only=True, keep_links=False)
    wb_b = openpyxl.load_workbook(cmd["b"], data_only=False, read_only=True, keep_links=False)
    try:
        na, nb = _names(wb_a), _names(wb_b)
    finally:
        wb_a.close()
        wb_b.close()

    only_a = sorted(set(na) - set(nb))
    only_b = sorted(set(nb) - set(na))
    differing = sorted(n for n in (set(na) & set(nb)) if na[n] != nb[n])

    print(json.dumps({
        "a": cmd["a"], "b": cmd["b"],
        "counts": {"names_a": len(na), "names_b": len(nb),
                   "only_in_a": len(only_a), "only_in_b": len(only_b),
                   "differing_refs": len(differing)},
        "only_in_a": only_a[:cap],
        "only_in_b": only_b[:cap],
        "differing": [{"name": n, "a": na[n][:160], "b": nb[n][:160]} for n in differing[:cap]],
    }, indent=2, default=str))


if __name__ == "__main__":
    main()
