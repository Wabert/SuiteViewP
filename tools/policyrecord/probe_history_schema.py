"""Describe live Policy Record 69 tables with zero-row queries; no policy data."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from suiteview.core.db2_connection import DB2Connection, _extract_odbc_message
from suiteview.core.db2_constants import REGION_DSN_MAP
from suiteview.polview.config.policy_records import POLICY_RECORD_TABLES


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--region", choices=sorted(REGION_DSN_MAP), default="CKPR")
    args = parser.parse_args()
    if os.environ.get("SUITEVIEW_LOCAL_DATA") == "1":
        raise RuntimeError("Live schema verification requires local data disabled.")
    db = DB2Connection(args.region)
    output = {}
    try:
        for table in POLICY_RECORD_TABLES["Policy Record 69"]:
            if not table.startswith("FH_"):
                continue
            try:
                columns, rows = db.execute_query_with_headers(
                    f"SELECT * FROM DB2TAB.{table} WHERE 1 = 0"
                )
                if rows:
                    raise RuntimeError("Metadata query unexpectedly returned rows.")
                columns = [column.upper() for column in columns]
                output[table] = {
                    "columns": columns,
                    "has_system_key": "CK_SYS_CD" in columns,
                    "has_policy_company_keys": {"TCH_POL_ID", "CK_CMP_CD"} <= set(columns),
                }
            except Exception as exc:
                output[table] = {"error": _extract_odbc_message(exc)}
    finally:
        db.close()
    all_ok = all("error" not in result for result in output.values())
    print(json.dumps({"region": args.region, "tables": output, "all_ok": all_ok}, indent=2))
    return 0 if all_ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
