"""Generate the Segment 02 (Coverage) ordered field mapping from the worked-out
screen->layout alignment.

The screen's field order is the layout's life-primary byte order as a *monotonic
subset* (the layout has extra A&H/annuity/filler/cash-value-sub rows the screen
skips).  ``ALIGN`` encodes, for each screen field index, the matching row index
in ``seg_02_layout.json`` (or ``None`` when the field has no DB2 source and must
render as example data).

Emits ``seg_02_fields.json``: an ordered list of
``{name, role, db2, cobol, kind, line_break}`` -- consumed by the live builder
and to populate seg_02.json's tooltip ``fields`` map.  ``role`` is one of:
``chrome`` (segment id/length constants), ``flag`` (bit-packed flag byte, example),
``data`` (live DB2 value), ``example`` (no DB2 source).

Usage:
    venv\\Scripts\\python.exe tools/gen_seg02_fields.py '{"layout": "C:/tmp/seg02/seg_02_layout.json", "out": "C:/tmp/seg02/seg_02_fields.json"}'
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SEG_JSON = ROOT / "suiteview" / "polview" / "data" / "policy_record_screens" / "seg_02.json"

# These screen field indices START a new (indented) line -- i.e. the mainframe
# wraps *after* fields 16/33/56/81, so 17/34/57/82 begin lines 2..5.
LINE_BREAKS = {17, 34, 57, 82}

# screen field index -> layout row index in seg_02_layout.json (or None=example).
# 0-5 are chrome/flag (handled by role, not alignment).
ALIGN = {
    6: 6, 7: 7, 8: 8, 9: 9, 10: 10, 11: 11, 12: 12, 13: 13, 14: 14, 15: 15,
    16: 16, 17: 17, 18: 18, 19: 19, 20: 20,
    21: 22, 22: 24, 23: 25, 24: 26, 25: 27, 26: 28, 27: 29, 28: 30, 29: 31,
    30: 32, 31: 33, 32: 34, 33: 35, 34: 36, 35: 37, 36: 38,
    37: 41, 38: 42, 39: 44, 40: 45, 41: 46, 42: 47, 43: 48, 44: 49, 45: 50,
    46: 51, 47: 52, 48: 53, 49: 54, 50: 55, 51: 56, 52: 57, 53: 58, 54: 59, 55: 60,
    56: 65, 57: 66, 58: 70, 59: 75, 60: 76, 61: 77, 62: 78, 63: 79, 64: 80,
    65: 81, 66: 82, 67: 83, 68: 84, 69: 85, 70: 86, 71: 87, 72: 88, 73: 89,
    74: 90, 75: 91, 76: 92, 77: 93, 78: 94, 79: 95, 80: 96, 81: 97, 82: 98,
    83: 99, 84: 100, 85: 101, 86: 102,
    87: None,
    88: 103, 89: 104, 90: 105, 91: 106, 92: 107, 93: 108, 94: 109, 95: 110,
    96: 111, 97: 112,
    98: 114, 99: 115, 100: None,
}


# Per-index corrections applied after the automatic layout->Translation mapping.
# The layout's naive COBOL->DB2 (or a redefine row) is wrong or incomplete for a
# few screen fields; each was value-verified against img_002 (U0361148):
#   * 21 Death Benefit Effective Age -- stored 0 but the mainframe shows it blank.
#   * 47 Participation Type -- real column DIV_PTP_TYP_CD (COBOL had no Translation row).
#   * 55 Orig Spec Amount Units -- OGN_SPC_UNT_QTY (100.000/125.000), not a cash-value.
#   * 76 Premium Residence Code -- stored 0 but the mainframe shows it blank.
#   * 92 the screen shows the production PERCENT (PRD_PCT, 4dp), not the amount.
#   * 99 ANICO Product Indicator lives in TH_COV_PHA (a different table) -> example.
OVERRIDES = {
    21: {"blank_if_zero": True},
    47: {"role": "data", "db2": "LH_COV_PHA.DIV_PTP_TYP_CD", "kind": "char",
         "cobol": "FCVPAR-PAR-TYPE"},
    55: {"db2": "LH_COV_PHA.OGN_SPC_UNT_QTY", "kind": "decimal:3",
         "cobol": "FCVSPAMT-ORIG-UNITS"},
    76: {"blank_if_zero": True},
    92: {"name": "Production Control Data: Percent",
         "db2": "LH_COV_PHA.PRD_PCT", "kind": "decimal:4",
         "cobol": "FCVPRPCT-PRODUCTION-PERCENT"},
    99: {"role": "example", "db2": None},
}


def _spine(doc):
    lines = doc.get("lines", [])
    fields, seen = [], 0
    started = False
    for line in lines:
        for run in line:
            f = run.get("field")
            if not f:
                continue
            if f == "Segment Identification":
                seen += 1
                if seen == 1:
                    started = True
                elif seen == 2:
                    return fields
            if started:
                fields.append(f)
    return fields


def main():
    cfg = json.loads(sys.argv[1]) if len(sys.argv) > 1 and sys.argv[1].strip().startswith("{") else {}
    layout_path = Path(cfg.get("layout", r"C:/tmp/seg02/seg_02_layout.json"))
    out_path = Path(cfg.get("out", r"C:/tmp/seg02/seg_02_fields.json"))

    with open(SEG_JSON, "r", encoding="utf-8") as fh:
        doc = json.load(fh)
    with open(layout_path, "r", encoding="utf-8") as fh:
        specs = json.load(fh)["field_specs"]

    spine = _spine(doc)
    out = []
    for i, name in enumerate(spine):
        entry = {"name": name, "line_break": i in LINE_BREAKS}
        if i == 0:
            entry.update(role="chrome", const="02")
        elif i == 1:
            entry.update(role="chrome", const="0220")
        elif 2 <= i <= 5:
            entry.update(role="flag", const="00000000")
        else:
            j = ALIGN.get(i)
            lay = specs[j] if j is not None else {}
            db2 = lay.get("db2")
            if db2:
                entry.update(role="data", db2=db2, cobol=lay.get("cobol"),
                             kind=lay.get("kind"), byte=lay.get("byte"),
                             layout_label=lay.get("layout_label"))
            else:
                entry.update(role="example", cobol=lay.get("cobol"),
                             layout_label=lay.get("layout_label"))
        override = OVERRIDES.get(i)
        if override:
            entry.update(override)
            if entry.get("db2") is None:
                entry["role"] = "example"
                entry.pop("db2", None)
        out.append(entry)

    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as fh:
        json.dump(out, fh, indent=2)

    for i, e in enumerate(out):
        print("%3d | %-52s | %-8s | %-30s | %-10s | %s" % (
            i, e["name"][:52], e["role"], (e.get("db2") or "")[:30],
            e.get("kind") or "", "BREAK" if e["line_break"] else ""))
    print(f"\nwrote {out_path} ({len(out)} fields)")


if __name__ == "__main__":
    main()
