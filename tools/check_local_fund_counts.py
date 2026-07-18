"""Report per-policy fund counts in the local dev SQLite policy DB.

For each policy, counts the distinct current fund buckets (LH_POL_FND_VAL_TOT
with MVRY_DT in 9999), the distinct impaired/loan funds (LH_FND_VAL_LOAN), and
the distinct premium-allocation funds (LH_FND_ALC). Used to pick a sensible
visible-row cap for the Policy tab's fund mini-tables.

Usage:
    venv\\Scripts\\python.exe tools/check_local_fund_counts.py
"""
from __future__ import annotations

import json
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DB = ROOT / "bundled_data" / "dev" / "policy_records.sqlite"


def _distinct_counts(conn: sqlite3.Connection, table: str, where: str = "") -> dict[str, int]:
    try:
        rows = conn.execute(
            f"SELECT TCH_POL_ID, COUNT(DISTINCT FND_ID_CD) FROM {table} "
            f"{where} GROUP BY TCH_POL_ID"
        ).fetchall()
    except sqlite3.OperationalError:
        return {}
    return {str(pol_id).strip(): int(count) for pol_id, count in rows}


def main() -> int:
    db_path = Path(sys.argv[1]).expanduser() if len(sys.argv) > 1 else DEFAULT_DB
    conn = sqlite3.connect(f"file:{db_path.as_posix()}?mode=ro", uri=True)
    try:
        policies = {
            str(pol_id).strip(): str(nbr).strip()
            for nbr, pol_id in conn.execute(
                "SELECT CK_POLICY_NBR, TCH_POL_ID FROM LH_BAS_POL")
        }
        current_funds = _distinct_counts(
            conn, "LH_POL_FND_VAL_TOT", "WHERE MVRY_DT LIKE '%9999%'")
        loan_funds = _distinct_counts(
            conn, "LH_FND_VAL_LOAN", "WHERE MVRY_DT LIKE '%9999%'")
        alloc_funds = _distinct_counts(conn, "LH_FND_ALC")
    finally:
        conn.close()

    out = []
    for pol_id, number in sorted(policies.items(), key=lambda kv: kv[1]):
        out.append({
            "policy": number,
            "current_funds": current_funds.get(pol_id, 0),
            "loan_funds": loan_funds.get(pol_id, 0),
            "alloc_funds": alloc_funds.get(pol_id, 0),
        })
    print(json.dumps({"db": str(db_path), "policies": out}, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
