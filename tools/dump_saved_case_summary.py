"""Compact Saved Cases dump: scalars verbatim, vectors summarized.

For one or more cases, print every scalar (non-repeating) input name/value and,
for vector names (repeating rows, e.g. vINPUT_Premium_Amount), a run-length
summary like ``150 x121`` — so a case's full input picture fits on a screen.

Usage:
    venv\\Scripts\\python.exe tools/dump_saved_case_summary.py '<json>'
    {"workbook": "docs/Illustration_UL/RERUN (v20.0) local.xlsm", "cases": [7, 9, 12]}
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from rerun_com import read_case_inputs  # noqa: E402


def _rle(values: list) -> str:
    runs = []
    for v in values:
        s = "" if v is None else str(v)
        if runs and runs[-1][0] == s:
            runs[-1][1] += 1
        else:
            runs.append([s, 1])
    return ", ".join(f"{s or '(blank)'} x{n}" for s, n in runs)


def main() -> None:
    cmd = json.loads(sys.argv[1]) if len(sys.argv) > 1 else {}
    workbook = cmd.get("workbook") or "docs/Illustration_UL/RERUN (v20.0) local.xlsm"
    cases = cmd.get("cases") or [7]

    for case in cases:
        pairs, col = read_case_inputs(workbook, case)
        print(f"===== Case {case} (Saved Cases col {col}) =====")
        for name, values in pairs:
            if len(values) == 1:
                print(f"  {name} = {values[0]}")
            else:
                print(f"  {name} [{len(values)}] = {_rle(values)}")
        print()


if __name__ == "__main__":
    main()
