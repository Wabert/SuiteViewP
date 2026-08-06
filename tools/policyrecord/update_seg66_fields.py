"""Refresh ``seg_66.json``'s ``fields`` map so every live Segment 66 token hovers
to its authoritative source (COBOL name + DB2 column).

Segment 66 renders live from ``LH_NON_TRD_POL`` via
``policy_record_builder._build_segment_66``.  The builder replaces the screen's
``lines`` at runtime but keeps the bundled ``fields`` map for tooltips, so that
map must carry an entry for every field name the builder emits.  This tool:

  * reads the DB2-column -> COBOL-name mapping from the "Translation" sheet of
    ``docs/COBOLDB2translation.xls`` (filtered to ``LH_NON_TRD_POL`` so the
    seg-66 columns win over identically-named columns in other segments), and
  * rebuilds the ``fields`` map from the builder's ``_SEG66_FIELDS`` list --
    live fields get ``["COBOL: <name>", "DB2: LH_NON_TRD_POL.<col>"]``; the
    bit-packed flag bytes and the not-in-DB2 example fields get an explanatory
    note.  Existing chrome/reference keys are preserved.

Usage:
    venv\\Scripts\\python.exe tools/policyrecord/update_seg66_fields.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from suiteview.polview.models.policy_record_builder import (  # noqa: E402
    _SEG66_FIELDS, _SEG66_FLAG_BYTES, _SEG66_TABLE,
    _F_SCREEN, _F_POLICY, _F_SEG_ID, _F_SEG_LEN,
    _F_CUR_DATE, _F_USER, _F_REGION,
)

_SEG_PATH = ROOT / "suiteview" / "polview" / "data" / "policy_record_screens" / "seg_66.json"
_XLS_PATH = ROOT / "docs" / "COBOLDB2translation.xls"


def _db2_to_cobol() -> dict:
    """Map DB2 column -> COBOL name for LH_NON_TRD_POL (first match wins)."""
    df = pd.read_excel(_XLS_PATH, sheet_name="Translation", engine="xlrd", dtype=str).fillna("")
    out = {}
    for _, r in df.iterrows():
        if str(r.get("Table", "")).strip().upper() != _SEG66_TABLE:
            continue
        col = str(r.get("Field Name", "")).strip().upper()
        cobol = str(r.get("COBOL Name", "")).strip()
        if col and cobol and col not in out:
            out[col] = cobol
    return out


def main():
    with open(_SEG_PATH, "r", encoding="utf-8") as fh:
        screen = json.load(fh)

    cobol_map = _db2_to_cobol()
    fields = dict(screen.get("fields", {}))

    # Chrome / footer fields carry no source mapping.
    for name in (_F_SCREEN, _F_POLICY, _F_SEG_ID, _F_SEG_LEN,
                 _F_CUR_DATE, _F_USER, _F_REGION):
        fields.setdefault(name, [])

    for flag in _SEG66_FLAG_BYTES:
        fields[flag] = []

    resolved = 0
    for name, col, _fmt, _gs, _lb, _ex in _SEG66_FIELDS:
        if col is None:
            fields[name] = []
            continue
        entry = []
        cobol = cobol_map.get(col.upper())
        if cobol:
            entry.append(f"COBOL: {cobol}")
            resolved += 1
        entry.append(f"DB2: {_SEG66_TABLE}.{col}")
        fields[name] = entry

    screen["fields"] = fields
    with open(_SEG_PATH, "w", encoding="utf-8", newline="\n") as fh:
        json.dump(screen, fh, ensure_ascii=False, indent=2)
        fh.write("\n")

    live = [c for _n, c, *_ in _SEG66_FIELDS if c]
    print(json.dumps({
        "ok": True,
        "path": str(_SEG_PATH.relative_to(ROOT)),
        "live_fields": len(live),
        "cobol_resolved": resolved,
        "cobol_missing": sorted(c for c in live if c.upper() not in cobol_map),
        "total_field_keys": len(fields),
    }, indent=2))


if __name__ == "__main__":
    main()
