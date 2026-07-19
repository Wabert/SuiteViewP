"""Normalize the CanIllustrate flag in the Illustration plancode table.

Rule (authoritative): a plancode is "IUL" iff it has an index-strategy row
(``index_strategies.is_iul_plan``) — the exact criterion the app uses to switch
on the IUL crediting UI. IUL plancodes get ``CanIllustrate = false``; every
other plancode gets ``CanIllustrate = true``.

Run:  venv\\Scripts\\python.exe tools/set_can_illustrate.py
Emits a JSON summary to stdout and rewrites plancode_table.json in place.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from suiteview.illustration.models.index_strategies import is_iul_plan

_TABLE = (
    _ROOT / "suiteview" / "illustration" / "plancodes" / "plancode_table.json"
)


def main() -> None:
    data = json.loads(_TABLE.read_text(encoding="utf-8"))
    rows = data.get("Plancodes", [])

    iul_flagged = []
    changed = 0
    for row in rows:
        plancode = str(row.get("Plancode", "")).strip()
        if not plancode:
            continue
        want = not is_iul_plan(plancode)  # IUL -> False, else True
        if row.get("CanIllustrate") != want:
            changed += 1
        row["CanIllustrate"] = want
        if not want:
            iul_flagged.append(plancode)

    _TABLE.write_text(
        json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )

    print(json.dumps({
        "total": len(rows),
        "iul_false": sorted(iul_flagged),
        "iul_count": len(iul_flagged),
        "rows_changed": changed,
    }, indent=2))


if __name__ == "__main__":
    main()
