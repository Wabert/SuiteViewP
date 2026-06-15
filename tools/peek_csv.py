"""Print selected columns of a CSV for rows where a key column is in a range.

Single-purpose debug helper for inspecting engine dumps (run_engine_case output).

Usage:
    venv\\Scripts\\python.exe tools/peek_csv.py '<json>'
    {"csv":"...","cols":["duration","coi_rate"],"key":"duration","min":538,"max":546}
"""
import csv
import json
import sys


def main():
    cmd = json.loads(sys.argv[1])
    cols = cmd["cols"]
    key = cmd.get("key")
    lo = cmd.get("min")
    hi = cmd.get("max")

    with open(cmd["csv"], newline="", encoding="utf-8") as fh:
        rows = list(csv.DictReader(fh))

    out = []
    for r in rows:
        if key is not None:
            try:
                k = float(r.get(key, ""))
            except ValueError:
                continue
            if (lo is not None and k < lo) or (hi is not None and k > hi):
                continue
        out.append({c: r.get(c) for c in cols})

    print(json.dumps(out, indent=2))


if __name__ == "__main__":
    main()
