"""Delete specific policies from the local dev policy DB, across all tables.

Resolves CK_POLICY_NBR -> TCH_POL_ID via LH_BAS_POL, then deletes matching
rows from every table that carries a TCH_POL_ID column. Read-only preview with
--dry-run. Local dev data only (bundled_data/dev/policy_records.sqlite).

Usage:
    venv\\Scripts\\python.exe tools/delete_local_policies.py '["DEV10001","DEV10002"]' [--dry-run]
"""
from __future__ import annotations

import json
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
POLICY_DB = ROOT / "bundled_data" / "dev" / "policy_records.sqlite"


def main() -> None:
    policy_numbers = json.loads(sys.argv[1])
    dry_run = "--dry-run" in sys.argv[2:]

    conn = sqlite3.connect(POLICY_DB, timeout=30)
    out: dict = {"db": str(POLICY_DB), "dry_run": dry_run, "policies": {}, "deleted_by_table": {}}

    pol_ids = []
    for nbr in policy_numbers:
        rows = conn.execute(
            "SELECT TCH_POL_ID FROM LH_BAS_POL WHERE TRIM(CK_POLICY_NBR)=?", (nbr,)
        ).fetchall()
        out["policies"][nbr] = [r[0] for r in rows]
        pol_ids.extend(r[0] for r in rows)

    if not pol_ids:
        out["error"] = "no matching policies found; nothing deleted"
        print(json.dumps(out, indent=1))
        return

    tables = [r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")]
    placeholders = ",".join("?" for _ in pol_ids)
    for table in tables:
        cols = [c[1] for c in conn.execute(f"PRAGMA table_info([{table}])")]
        if "TCH_POL_ID" not in cols:
            continue
        n = conn.execute(
            f"SELECT COUNT(*) FROM [{table}] WHERE TCH_POL_ID IN ({placeholders})", pol_ids
        ).fetchone()[0]
        if not n:
            continue
        out["deleted_by_table"][table] = n
        if not dry_run:
            conn.execute(f"DELETE FROM [{table}] WHERE TCH_POL_ID IN ({placeholders})", pol_ids)

    if not dry_run:
        conn.commit()
        conn.execute("VACUUM")
    remaining = conn.execute("SELECT COUNT(*) FROM LH_BAS_POL").fetchone()[0]
    out["remaining_policies_in_LH_BAS_POL"] = remaining
    print(json.dumps(out, indent=1))


if __name__ == "__main__":
    main()
