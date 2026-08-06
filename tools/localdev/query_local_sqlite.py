"""Run a read-only SELECT against a local dev SQLite DB and print JSON rows.

Usage:
    query_local_sqlite.py '<json>'

    {"db": "rates" | "policy" | "<path>", "sql": "SELECT ...", "limit": 50}

Read-only (mode=ro URI); only for inspecting the bundled_data/dev fixtures.
"""
from __future__ import annotations

import json
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DBS = {
    "rates": ROOT / "bundled_data" / "dev" / "rates.sqlite",
    "policy": ROOT / "bundled_data" / "dev" / "policy_records.sqlite",
}


def main():
    cmd = json.loads(sys.argv[1])
    db = cmd.get("db", "rates")
    path = DBS.get(db, Path(db))
    limit = int(cmd.get("limit", 50))

    conn = sqlite3.connect(f"file:{Path(path).as_posix()}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    try:
        rows = [dict(r) for r in conn.execute(cmd["sql"]).fetchmany(limit)]
    finally:
        conn.close()
    print(json.dumps({"db": str(path), "rows": rows, "count": len(rows)}, indent=2, default=str))


if __name__ == "__main__":
    main()
