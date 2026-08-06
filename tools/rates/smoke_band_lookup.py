"""Live smoke test: band lookup through Rates against the real UL_Rates DSN.

Read-only. Confirms the BANDSPECS query now returns Issue_Date and that
get_band selects by the (policy) issue date. Does NOT enable local data.

Usage:
    venv\\Scripts\\python.exe tools/rates/smoke_band_lookup.py
    venv\\Scripts\\python.exe tools/rates/smoke_band_lookup.py '{"plancodes": ["1U145500", "1U143900"]}'
"""
from __future__ import annotations

import json
import os
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def main() -> None:
    # Ensure we hit the real DSN, never the local mirror.
    os.environ.pop("SUITEVIEW_LOCAL_DATA", None)
    cmd = json.loads(sys.argv[1]) if len(sys.argv) > 1 else {}
    plancodes = cmd.get("plancodes", ["1U145500", "1U143900"])
    faces = cmd.get("faces", [250000, 250001, 500000])
    issue_dates = ["2017-06-01", "2018-10-01", "2020-01-01"]

    from suiteview.core.rates import Rates

    rates = Rates()
    out = {}
    for pc in plancodes:
        specs = rates.get_rates("BANDSPECS", pc)
        entry = {
            "bandspecs_raw": [[s[0], s[1], str(s[2]) if len(s) > 2 else None] for s in (specs or [])],
            "distinct_issue_dates": sorted({str(s[2]) for s in (specs or []) if len(s) > 2 and s[2] is not None}),
            "bands": {},
        }
        for face in faces:
            entry["bands"][str(face)] = {
                "no_date": rates.get_band(pc, face),
                **{d: rates.get_band(pc, face, issue_date=date.fromisoformat(d)) for d in issue_dates},
            }
        out[pc] = entry

    print(json.dumps(out, indent=2, default=str))


if __name__ == "__main__":
    main()
