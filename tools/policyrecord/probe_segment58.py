"""Probe the DB2 target tables behind Policy Record Segment 58 (screen 6258).

Dumps every row/column of LH_POL_TARGET, LH_COV_TARGET and LH_COM_TARGET for a
policy so we can (a) confirm DB2 is reachable, (b) see which table reproduces the
sample screen's target codes, and (c) learn the exact column names/values needed
to render Segment 58 live.

Run (needs live DB2):
    venv\\Scripts\\python.exe tools/policyrecord/probe_segment58.py '{"policy": "U0633187", "region": "CKPR"}'
    venv\\Scripts\\python.exe tools/policyrecord/probe_segment58.py U0633187 CKPR

Output: a single JSON object on stdout.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from suiteview.core.policy_service import get_policy_info, clear_cache

_TABLES = ["LH_POL_TARGET", "LH_COV_TARGET", "LH_COM_TARGET"]


def _jsonable(value):
    if value is None or isinstance(value, (bool, int, float, str)):
        return value
    return str(value)


def _parse_args(argv):
    if len(argv) >= 2 and argv[1].strip().startswith("{"):
        cfg = json.loads(argv[1])
        return cfg.get("policy"), cfg.get("region", "CKPR"), cfg.get("company")
    policy = argv[1] if len(argv) > 1 else "U0633187"
    region = argv[2] if len(argv) > 2 else "CKPR"
    company = argv[3] if len(argv) > 3 else None
    return policy, region, company


def run(policy_number: str, region: str, company) -> dict:
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
    for table in _TABLES:
        try:
            rows = pi.fetch_table(table)
            result["tables"][table] = {
                "count": len(rows),
                "columns": sorted({k for r in rows for k in r.keys()}),
                "rows": [{k: _jsonable(v) for k, v in r.items()} for r in rows],
            }
        except Exception as exc:  # pragma: no cover - diagnostic only
            result["tables"][table] = {"error": str(exc)}
    return result


if __name__ == "__main__":
    policy, region, company = _parse_args(sys.argv)
    print(json.dumps(run(policy, region, company), indent=2))
