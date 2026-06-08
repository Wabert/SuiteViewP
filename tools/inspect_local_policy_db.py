from __future__ import annotations

import argparse
import json
import sqlite3
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DB = ROOT / "bundled_data" / "dev" / "policy_records.sqlite"


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Inspect local policy SQLite rows.")
    parser.add_argument("policy_numbers", nargs="*", help="Policy numbers to inspect")
    parser.add_argument("--db", default=str(DEFAULT_DB), help="SQLite policy database path")
    return parser.parse_args()


def _table_columns(conn: sqlite3.Connection, table: str) -> list[str]:
    return [str(row[1]).upper() for row in conn.execute(f"PRAGMA table_info({table})")]


def main() -> None:
    args = _parse_args()
    db_path = Path(args.db).expanduser()
    conn = sqlite3.connect(f"file:{db_path.as_posix()}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    try:
        tables = [row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type = 'table' ORDER BY name")]
        result: dict[str, object] = {
            "db": str(db_path),
            "tables": len(tables),
            "has_lh_bas_pol": "LH_BAS_POL" in tables,
            "policies": [],
        }
        if "LH_BAS_POL" not in tables:
            print(json.dumps(result, indent=2))
            return

        columns = _table_columns(conn, "LH_BAS_POL")
        result["lh_bas_pol_columns"] = columns
        result["lh_bas_pol_count"] = conn.execute("SELECT COUNT(*) FROM LH_BAS_POL").fetchone()[0]
        select_columns = [column for column in ["CK_POLICY_NBR", "CK_CMP_CD", "CK_SYS_CD", "TCH_POL_ID"] if column in columns]
        if select_columns:
            sample_rows = conn.execute(
                f"SELECT {', '.join(select_columns)} FROM LH_BAS_POL ORDER BY TCH_POL_ID"
            ).fetchall()
            result["lh_bas_pol_key_rows"] = [dict(row) for row in sample_rows]
        for policy_number in args.policy_numbers:
            if "CK_POLICY_NBR" in columns:
                rows = conn.execute(
                    f"SELECT {', '.join(select_columns)} FROM LH_BAS_POL WHERE CK_POLICY_NBR = ?",
                    (policy_number,),
                ).fetchall()
            else:
                rows = []
            result["policies"].append({
                "policy_number": policy_number,
                "rows": [dict(row) for row in rows],
            })

        if "SUITEVIEW_LOCAL_EXPORTED_POLICIES" in tables:
            rows = conn.execute(
                "SELECT POLICY_NUMBER, COMPANY_CODE, SYSTEM_CODE, POLICY_ID, REGION, EXPORTED_AT "
                "FROM SUITEVIEW_LOCAL_EXPORTED_POLICIES ORDER BY POLICY_NUMBER"
            ).fetchall()
            result["exported_policies"] = [dict(row) for row in rows]
        print(json.dumps(result, indent=2, default=str))
    finally:
        conn.close()


if __name__ == "__main__":
    main()
