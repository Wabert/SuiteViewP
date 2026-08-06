"""Emit the two U0361148 LH_COV_PHA rows limited to the columns the Segment 02
builder reads -- a frozen fixture for the seg-02 live-build unit test.

Reads the live dump (C:/tmp/seg02/covpha_U0361148.json, UTF-16) and the
generated coverage-field mapping, prints ``{"cov1": {...}, "cov2": {...}}`` as
JSON so the values can be pasted into tests/test_policy_record_formatting.py.

Usage:
    venv\\Scripts\\python.exe tools/policyrecord/extract_seg02_fixture.py '{"dump": "C:/tmp/seg02/covpha_U0361148.json"}'
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FIELDS = ROOT / "suiteview" / "polview" / "data" / "policy_record_screens" / "seg_02_coverage_fields.json"


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
    r0, r1 = tbl["rows"][0], tbl["rows"][1]

    spec = json.loads(FIELDS.read_text(encoding="utf-8"))
    cols = sorted({
        f["db2"].split(".", 1)[1]
        for f in spec if f.get("role") == "data" and f.get("db2")
    })

    def pick(row):
        return {c: row.get(c) for c in cols}

    print(json.dumps({"cov1": pick(r0), "cov2": pick(r1)}, indent=2, default=str))


if __name__ == "__main__":
    main()
