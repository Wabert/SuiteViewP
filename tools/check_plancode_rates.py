"""Report how many rate rows exist for a given plancode in the local rates DB.

Read-only. Scans every Select_RATE_* table that has a Plancode column and prints
a JSON summary of row counts per table for the requested plancode, plus the
distinct (Sex, Rateclass, Band, Scale) combos present in RATE_COI.

Usage:
    python tools/check_plancode_rates.py CCV48000
"""

from __future__ import annotations

import json
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RATES_DB = ROOT / "bundled_data" / "dev" / "rates.sqlite"


def main() -> None:
    if len(sys.argv) != 2:
        print("usage: python tools/check_plancode_rates.py <PLANCODE>", file=sys.stderr)
        raise SystemExit(2)
    plancode = sys.argv[1]

    conn = sqlite3.connect(f"file:{RATES_DB.as_posix()}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row

    if plancode == "--list":
        try:
            plancodes = [
                r[0]
                for r in conn.execute(
                    "SELECT DISTINCT Plancode FROM Select_RATE_COI ORDER BY Plancode"
                ).fetchall()
            ]
        finally:
            conn.close()
        print(json.dumps({"plancodes_in_RATE_COI": plancodes, "count": len(plancodes)}, indent=2))
        return

    try:
        tables = [
            r[0]
            for r in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' "
                "AND name LIKE 'Select_RATE_%' ORDER BY name"
            ).fetchall()
        ]

        per_table: dict[str, int] = {}
        total = 0
        for t in tables:
            cols = [c[1] for c in conn.execute(f'PRAGMA table_info("{t}")').fetchall()]
            if "Plancode" not in cols:
                continue
            n = conn.execute(
                f'SELECT COUNT(*) FROM "{t}" WHERE Plancode = ?', (plancode,)
            ).fetchone()[0]
            per_table[t] = n
            total += n

        # Distinct COI keys, if any COI rows exist.
        coi_keys = []
        if per_table.get("Select_RATE_COI"):
            coi_keys = [
                dict(r)
                for r in conn.execute(
                    "SELECT DISTINCT Sex, Rateclass, Band, Scale "
                    "FROM Select_RATE_COI WHERE Plancode = ? "
                    "ORDER BY Sex, Rateclass, Band, Scale",
                    (plancode,),
                ).fetchall()
            ]
    finally:
        conn.close()

    tables_with_rows = {k: v for k, v in per_table.items() if v > 0}
    print(
        json.dumps(
            {
                "plancode": plancode,
                "loaded": total > 0,
                "total_rows": total,
                "tables_with_rows": tables_with_rows,
                "all_table_counts": per_table,
                "coi_distinct_keys": coi_keys,
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
