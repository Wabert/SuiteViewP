"""Scan a DB2 region for LH_/TH_ tables and report which ones are not accessible.

Lists every table in the DB2 catalog (SYSIBM.SYSTABLES) whose name starts with
``LH_`` or ``TH_`` under the region's schema, then attempts a lightweight
``SELECT`` against each one to see whether the current login actually has read
access.  Tables that raise an insufficient-privilege (SQLSTATE 42501) error --
or any other error -- are reported as "no access".

Run (needs live DB2):
    venv\\Scripts\\python.exe tools/policyrecord/scan_db2_table_access.py
    venv\\Scripts\\python.exe tools/policyrecord/scan_db2_table_access.py "{\"region\": \"CKPR\"}"
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from suiteview.core.db2_table_access import scan_table_access


def main() -> None:
    cfg = {}
    if len(sys.argv) > 1 and sys.argv[1].lstrip().startswith("{"):
        cfg = json.loads(sys.argv[1])
    region = cfg.get("region", "CKPR")
    result = scan_table_access(region)
    # Preserve the previous verbose key name for the catalog count.
    result["total_tables_in_catalog"] = result["total"]
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
