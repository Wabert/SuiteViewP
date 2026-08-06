"""Dump arbitrary DB2 tables for a policy (diagnostic for Policy Record segments).

Confirms DB2 is reachable and shows the exact column names/values behind a
segment so a live builder can be written and verified.  Fetches each requested
table via :meth:`PolicyInformation.fetch_table` (so schema/region rewriting and
caching are handled) and prints one JSON object.

Run (needs live DB2):
    venv\\Scripts\\python.exe tools/rates/probe_tables.py "{\"policy\": \"U0361148\", \"region\": \"CKPR\", \"tables\": [\"LH_COV_PHA\", \"TH_COV_PHA\"]}"
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from suiteview.core.policy_service import get_policy_info, clear_cache


def _jsonable(value):
    if value is None or isinstance(value, (bool, int, float, str)):
        return value
    return str(value)


def run(policy_number: str, region: str, company, tables, max_rows: int) -> dict:
    clear_cache()
    pi = get_policy_info(policy_number, region, company)
    if pi is None or not getattr(pi, "exists", False):
        return {"policy": policy_number, "region": region, "found": False}

    result = {
        "policy": policy_number,
        "region": region,
        "company": _jsonable(getattr(pi, "company_code", None)),
        "found": True,
        "tables": {},
    }
    for table in tables:
        try:
            rows = list(pi.fetch_table(table) or [])
            error = pi.table_error(table)
            table_result = {
                "count": len(rows),
                "columns": sorted({k for r in rows for k in r.keys()}),
                "rows": [{k: _jsonable(v) for k, v in r.items()}
                         for r in rows[:max_rows]],
            }
            if error:
                table_result["error"] = error
            result["tables"][table] = table_result
        except Exception as exc:  # pragma: no cover - diagnostic only
            result["tables"][table] = {"error": str(exc)}
    return result


def main():
    if len(sys.argv) > 1 and sys.argv[1].lstrip().startswith("{"):
        cfg = json.loads(sys.argv[1])
    else:
        if len(sys.argv) < 4:
            raise SystemExit(
                "usage: probe_tables.py <policy> <region> <table> [table ...]"
            )
        cfg = {
            "policy": sys.argv[1],
            "region": sys.argv[2],
            "tables": sys.argv[3:],
        }
    print(json.dumps(run(
        cfg.get("policy"),
        cfg.get("region", "CKPR"),
        cfg.get("company"),
        cfg.get("tables", []),
        int(cfg.get("max_rows", 25)),
    ), indent=2))


if __name__ == "__main__":
    main()
