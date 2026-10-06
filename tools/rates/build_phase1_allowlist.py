"""Build the phase-1 soft-launch plancode allow-list from the UL test-group CSV.

Business users (see ``suiteview/illustration/core/business_mode.py``) may
illustrate only these plancodes. The source is the phase-1 test grouping
(``UL_Test_Groups_2026-10-05.csv``, column ``Plancode``); the output is
``suiteview/illustration/plancodes/phase1_allowlist.json``.

Run:  venv\\Scripts\\python.exe -B tools/rates/build_phase1_allowlist.py <csv>
"""
from __future__ import annotations

import csv
import json
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]
_OUT = _ROOT / "suiteview" / "illustration" / "plancodes" / "phase1_allowlist.json"


def main() -> None:
    source = Path(sys.argv[1])
    with source.open(newline="", encoding="utf-8-sig") as handle:
        plancodes = sorted({
            row["Plancode"].strip().upper()
            for row in csv.DictReader(handle)
            if row.get("Plancode", "").strip()
        })
    payload = {
        "description": (
            "Phase-1 soft-launch UL plancodes business users may illustrate. "
            "Regenerate with tools/rates/build_phase1_allowlist.py."),
        "source": source.name,
        "plancodes": plancodes,
    }
    _OUT.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"written": str(_OUT), "count": len(plancodes)}))


if __name__ == "__main__":
    main()
