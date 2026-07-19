"""Dump BANDSPECS rows and get_band results for a plancode from the rates DB.

Usage:
    venv\\Scripts\\python.exe tools/dump_bandspecs.py '<json>'
    {"plancode": "1U145500", "faces": [250000, 250001], "issue_dates": ["2017-06-01", "2019-01-01"]}

Requires SUITEVIEW_LOCAL_DATA=1 for the local rates DB (set automatically here
for offline dev use, matching tools/check_local_rate_data.py).
"""
from __future__ import annotations

import json
import os
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def main() -> None:
    os.environ["SUITEVIEW_LOCAL_DATA"] = "1"
    cmd = json.loads(sys.argv[1]) if len(sys.argv) > 1 else {}
    plancode = cmd.get("plancode", "1U145500")
    faces = cmd.get("faces", [250000])
    issue_dates = [date.fromisoformat(d) for d in cmd.get("issue_dates", [])]

    from suiteview.core.rates import Rates

    rates = Rates()
    out = {
        "plancode": plancode,
        "bandspecs": rates.get_rates("BANDSPECS", plancode),
        "bands": {},
    }
    for face in faces:
        entry = {"no_issue_date": rates.get_band(plancode, face)}
        for d in issue_dates:
            try:
                entry[str(d)] = rates.get_band(plancode, face, issue_date=d)
            except TypeError:
                entry[str(d)] = "get_band has no issue_date parameter"
        out["bands"][str(face)] = entry
    print(json.dumps(out, indent=2, default=str))


if __name__ == "__main__":
    main()
