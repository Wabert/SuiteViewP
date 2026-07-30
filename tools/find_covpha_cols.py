"""Find LH_COV_PHA columns whose (cov1, cov2) values match given targets.

Helps resolve Segment 02 field->column mappings by searching the live dump for
columns that hold specific screen values (e.g. Orig Spec Amount Units = 100/125).

Usage:
    venv\\Scripts\\python.exe tools/find_covpha_cols.py '{"dump": "C:/tmp/seg02/covpha_U0361148.json", "targets": ["100", "125"]}'
    venv\\Scripts\\python.exe tools/find_covpha_cols.py '{"dump": "...", "cols": ["PRD_AMT", "COV_UNT_QTY"]}'
"""
from __future__ import annotations

import json
import sys
from decimal import Decimal, InvalidOperation


def _num(v):
    try:
        return Decimal(str(v))
    except (InvalidOperation, ValueError, TypeError):
        return None


def _load(path):
    with open(path, "rb") as fh:
        raw = fh.read()
    for enc in ("utf-8-sig", "utf-16", "utf-8"):
        try:
            return json.loads(raw.decode(enc))
        except (UnicodeDecodeError, ValueError):
            continue
    raise ValueError(f"could not decode {path}")


def main():
    cfg = json.loads(sys.argv[1])
    dump = _load(cfg["dump"])
    tbl = dump["tables"]["LH_COV_PHA"]
    cols = tbl["columns"]
    r0, r1 = tbl["rows"][0], tbl["rows"][1]

    if cfg.get("cols"):
        for c in cfg["cols"]:
            print("%-26s cov1=%-14r cov2=%-14r" % (c, r0.get(c), r1.get(c)))
        return

    targets = [str(t) for t in cfg.get("targets", [])]
    tnums = [_num(t) for t in targets]
    print(f"columns where cov1 matches any of {targets}:")
    for c in cols:
        v0 = r0.get(c)
        n0 = _num(v0)
        hit = str(v0).strip() in targets or (n0 is not None and any(
            tn is not None and n0 == tn for tn in tnums))
        if hit:
            print("  %-26s cov1=%-14r cov2=%-14r" % (c, v0, r1.get(c)))


if __name__ == "__main__":
    main()
