"""Dump rows of a local-fixture DB2 table for a given policy.

Looks up the policy's TCH_POL_ID from LH_BAS_POL, then prints rows of the
requested table for that policy (or all rows if the table has no TCH_POL_ID).
Reusable for debugging RERUN-vs-engine data gaps.

Usage:
    venv\\Scripts\\python.exe tools/query_local_fixture.py '{"policy":"U0656998","table":"LH_SPM_BNF"}'
    venv\\Scripts\\python.exe tools/query_local_fixture.py '{"policy":"U0492070","table":"LH_COV_TARGET"}'
"""
from __future__ import annotations

import json
import sqlite3
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
POLICY_DB = ROOT / "bundled_data" / "dev" / "policy_records.sqlite"
RATES_DB = ROOT / "bundled_data" / "dev" / "rates.sqlite"


def _cols(conn, table):
    return [str(r[1]) for r in conn.execute(f"PRAGMA table_info('{table}')")]


def main():
    cmd = json.loads(sys.argv[1])
    policy = cmd.get("policy")
    table = cmd["table"]
    cols_filter = cmd.get("cols")     # optional list of columns to show
    where = cmd.get("where") or {}    # optional {col: value} equality filters
    limit = int(cmd.get("limit", 0))  # 0 = no limit
    db = RATES_DB if cmd.get("db") == "rates" else POLICY_DB

    conn = sqlite3.connect(f"file:{db.as_posix()}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    try:
        tch_id = None
        if policy and db is POLICY_DB:
            tch = conn.execute(
                "SELECT TCH_POL_ID FROM LH_BAS_POL WHERE CK_POLICY_NBR = ?", (policy,)
            ).fetchone()
            tch_id = tch[0] if tch else None
        table_cols = _cols(conn, table)
        if not table_cols:
            print(json.dumps({"error": f"table {table} not found or empty schema"}))
            return
        clauses, params = [], []
        if "TCH_POL_ID" in table_cols and tch_id is not None:
            clauses.append("TCH_POL_ID = ?")
            params.append(tch_id)
        for col, val in where.items():
            clauses.append(f'"{col}" = ?')
            params.append(val)
        sql = f"SELECT * FROM '{table}'"
        if clauses:
            sql += " WHERE " + " AND ".join(clauses)
        if limit:
            sql += f" LIMIT {limit}"
        rows = conn.execute(sql, tuple(params)).fetchall()

        def proj(d):
            return {k: d[k] for k in cols_filter} if cols_filter else dict(d)

        print(json.dumps({
            "policy": policy, "tch_pol_id": tch_id, "table": table,
            "row_count": len(rows),
            "rows": [proj(dict(r)) for r in rows],
        }, indent=2, default=str))
    finally:
        conn.close()


if __name__ == "__main__":
    main()
