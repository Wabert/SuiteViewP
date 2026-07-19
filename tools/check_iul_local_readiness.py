"""Report whether the local dev SQLite data can support an IUL RERUN comparison.

Read-only introspection of bundled_data/dev/rates.sqlite and
policy_records.sqlite (no engine fallback — does not touch the
SUITEVIEW_LOCAL_DATA gate): for each IUL plancode found in the RERUN local
Saved Cases, report whether local rate rows and local policies exist.

Usage:
    venv\\Scripts\\python.exe tools/check_iul_local_readiness.py '["1U145500","1U147500"]'
"""
from __future__ import annotations

import json
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RATES_DB = ROOT / "bundled_data" / "dev" / "rates.sqlite"
POLICY_DB = ROOT / "bundled_data" / "dev" / "policy_records.sqlite"


def main() -> None:
    plancodes = json.loads(sys.argv[1]) if len(sys.argv) > 1 else ["1U145500", "1U147500"]
    out: dict = {"rates_db": str(RATES_DB), "policy_db": str(POLICY_DB), "plancodes": {}}

    rates_conn = sqlite3.connect(RATES_DB) if RATES_DB.exists() else None
    pol_conn = sqlite3.connect(POLICY_DB) if POLICY_DB.exists() else None

    rate_tables = []
    if rates_conn is not None:
        rate_tables = [r[0] for r in rates_conn.execute(
            "SELECT name FROM sqlite_master WHERE type IN ('table','view')")]

    for plancode in plancodes:
        entry: dict = {"rate_rows_by_table": {}, "policies": []}
        if rates_conn is not None:
            for table in rate_tables:
                cols = [c[1] for c in rates_conn.execute(f"PRAGMA table_info([{table}])")]
                if "Plancode" not in cols:
                    continue
                n = rates_conn.execute(
                    f"SELECT COUNT(*) FROM [{table}] WHERE Plancode=?", (plancode,)
                ).fetchone()[0]
                if n:
                    entry["rate_rows_by_table"][table] = n
        if pol_conn is not None:
            # LH_COV_PHA carries the plancode per coverage (PLN_DES_SER_CD).
            try:
                # TRIM: local rows can carry DB2-style trailing padding.
                rows = pol_conn.execute(
                    "SELECT DISTINCT TCH_POL_ID FROM LH_COV_PHA WHERE TRIM(PLN_DES_SER_CD)=?",
                    (plancode,)).fetchall()
                entry["policies"] = [r[0] for r in rows]
            except sqlite3.Error as exc:
                entry["policies_error"] = str(exc)
        out["plancodes"][plancode] = entry

    print(json.dumps(out, indent=2))


if __name__ == "__main__":
    main()
