"""Populate seg_02.json's ``fields`` hover map from the coverage-field mapping.

For every coverage field we write ``["COBOL: <name>", "DB2: LH_COV_PHA.<col>"]``
(matching seg_66.json) so the viewer's tooltip shows each value's source.  Flag
bytes, chrome and no-source example fields keep an empty mapping (their amber
"example" note is carried on the run, not here).  A field renamed by an override
(e.g. Production Control Data: Percent) is added as a new key.

Usage:
    venv\\Scripts\\python.exe tools/policyrecord/update_seg02_fields.py
"""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "suiteview" / "polview" / "data" / "policy_record_screens"
SEG = DATA / "seg_02.json"
FIELDS = DATA / "seg_02_coverage_fields.json"


def main():
    with open(SEG, "r", encoding="utf-8") as fh:
        doc = json.load(fh)
    with open(FIELDS, "r", encoding="utf-8") as fh:
        spec = json.load(fh)

    fmap = doc.setdefault("fields", {})
    updated = 0
    for f in spec:
        name = f["name"]
        if f.get("role") == "data" and f.get("db2"):
            mapping = []
            if f.get("cobol"):
                mapping.append(f"COBOL: {f['cobol']}")
            mapping.append(f"DB2: {f['db2']}")
            fmap[name] = mapping
            updated += 1
        else:
            # Flag / chrome / example -> no source mapping (empty like seg_66).
            fmap.setdefault(name, [])

    with open(SEG, "w", encoding="utf-8") as fh:
        json.dump(doc, fh, indent=2)
    print(f"updated {updated} data-field hovers; fields map now {len(fmap)} keys")


if __name__ == "__main__":
    main()
