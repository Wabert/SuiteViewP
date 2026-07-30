"""Render Segment 02 (Coverage) live from the master field_specs and print it so
the output can be diffed against the ground-truth screenshot (img_002, U0361148).

For each coverage phase (row of ``LH_COV_PHA``) it walks the master ``field_specs``
in byte order, reads each field's DB2 source at that phase's row index, and
formats it using the authoritative CyberDoc ``kind`` (``decimal:N`` / ``date`` /
``packed_num`` / ``int`` / code).  This is a *verification* harness: compare the
printed per-phase token stream to the real mainframe screen before wiring a
builder, so a redefine/ordering mismatch can never silently ship wrong data.

Usage (needs live DB2):
    python tools/probe_segment02.py "{\"policy\": \"U0361148\", \"region\": \"CKPR\", \"layout\": \"C:/tmp/segjson/seg_02_layout.json\"}"
"""
from __future__ import annotations

import json
import os
import sys
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from suiteview.core.policy_service import get_policy_info, clear_cache

_IDX_PATH = ROOT / "suiteview" / "polview" / "data" / "policy_record_screens" / "cyberdoc_field_formats.json"


def _cyberdoc():
    with open(_IDX_PATH, "r", encoding="utf-8") as fh:
        return json.load(fh)


def _date_str(value):
    if value is None or str(value).strip() == "":
        return "**/**/****"
    if isinstance(value, (datetime, date)):
        m, d, y = value.month, value.day, value.year
    else:
        core = str(value).split(" ")[0].split("T")[0].split("-")
        if len(core) == 3 and len(core[0]) == 4:
            y, m, d = int(core[0]), int(core[1]), int(core[2])
        else:
            return str(value).strip()
    if y >= 9999 or y <= 1:
        return "**/**/****"
    return f"{m:02d}/{d:02d}/{y}"


def _decimal_str(value, decimals):
    try:
        d = Decimal(str(value)) if value not in (None, "") else Decimal(0)
    except (InvalidOperation, ValueError):
        return str(value).strip()
    text = f"{d:.{decimals}f}"
    if text.startswith("0."):
        return text[1:]
    if text.startswith("-0."):
        return "-" + text[2:]
    return text


def _fmt(value, kind):
    if kind and kind.startswith("decimal:"):
        return _decimal_str(value, int(kind.split(":", 1)[1]))
    if kind == "date":
        return _date_str(value)
    if kind in ("packed_num", "int", "date_packed"):
        if value is None or str(value).strip() == "":
            return "0"
        try:
            return str(int(Decimal(str(value))))
        except (InvalidOperation, ValueError):
            return str(value).strip()
    # code / char
    if value is None:
        return ""
    return str(value).strip()


def main():
    cfg = json.loads(sys.argv[1])
    policy = cfg["policy"]
    region = cfg.get("region", "CKPR")
    with open(cfg["layout"], "r", encoding="utf-8") as fh:
        layout = json.load(fh)
    specs = layout.get("field_specs", [])

    idx = _cyberdoc()
    kinds = {}
    for sp in specs:
        cobol = sp.get("cobol")
        meta = idx.get(cobol) if cobol else None
        kinds[sp.get("name")] = (meta or {}).get("kind")

    clear_cache()
    pi = get_policy_info(policy, region, cfg.get("company"))
    if pi is None or not getattr(pi, "exists", False):
        print(json.dumps({"found": False, "policy": policy}))
        return

    n = pi.data_item_count("LH_COV_PHA")
    print(f"policy={policy} region={region} LH_COV_PHA rows={n}")
    for i in range(n):
        print(f"\n===== PHASE index {i} =====")
        toks = []
        for sp in specs:
            name = sp.get("name")
            db2 = sp.get("db2")
            kind = kinds.get(name)
            if db2 and "." in db2:
                table, col = db2.split(".", 1)
                try:
                    raw = pi.data_item(table.strip(), col.strip(), index=i)
                except Exception as exc:
                    raw = f"<ERR {exc}>"
            else:
                raw = None
            val = _fmt(raw, kind)
            toks.append(val if val != "" else "_")
            print("  byte %-8s %-42s db2=%-28s kind=%-10s raw=%-20r => %r" % (
                sp.get("byte"), (name or "")[:42], db2, kind, raw, val))
        print("  --- token stream ---")
        print("  " + " ".join(toks))


if __name__ == "__main__":
    main()
