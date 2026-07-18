"""Compare mapped numeric columns between two CSVs on a shared key column.

Usage:
    venv\\Scripts\\python.exe tools/compare_csv_columns.py '<json>'

    {"left": "a.csv", "right": "b.csv",
     "left_key": "B", "right_key": "duration",
     "map": {"KT": "glp", "KS": "gsp", "KU": "accumulated_glp"},
     "tol": 0.01, "max_diffs": 10}

Prints, per mapped pair: rows compared, count out of tolerance, max |delta|
and its key, plus the first few offending rows. Rows missing on either side
are skipped (reported as a count).
"""
from __future__ import annotations

import csv
import json
import sys


def _num(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _load(path: str, key: str) -> dict:
    out = {}
    with open(path, newline="", encoding="utf-8-sig") as fh:
        for row in csv.DictReader(fh):
            k = _num(row.get(key))
            if k is not None:
                out[int(k)] = row
    return out


def main() -> None:
    cmd = json.loads(sys.argv[1])
    left = _load(cmd["left"], cmd["left_key"])
    right = _load(cmd["right"], cmd["right_key"])
    tol = float(cmd.get("tol", 0.01))
    max_diffs = int(cmd.get("max_diffs", 10))

    shared = sorted(set(left) & set(right))
    report = {
        "left_rows": len(left), "right_rows": len(right),
        "shared_rows": len(shared), "tol": tol, "columns": [],
    }
    for lcol, rcol in cmd["map"].items():
        n = bad = 0
        max_d = 0.0
        max_k = None
        diffs = []
        for k in shared:
            lv, rv = _num(left[k].get(lcol)), _num(right[k].get(rcol))
            if lv is None or rv is None:
                continue
            n += 1
            d = abs(lv - rv)
            if d > max_d:
                max_d, max_k = d, k
            if d > tol:
                bad += 1
                if len(diffs) < max_diffs:
                    diffs.append({"key": k, "left": lv, "right": rv, "delta": lv - rv})
        report["columns"].append({
            "left_col": lcol, "right_col": rcol, "rows": n,
            "out_of_tol": bad, "max_abs_delta": max_d, "max_at": max_k,
            "first_diffs": diffs,
        })
    print(json.dumps(report, indent=1))


if __name__ == "__main__":
    main()
