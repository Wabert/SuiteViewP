"""Read-only probe of TH_NON_TRD_POL.DECR_CHRG_ALLOW (Decrease Charge Rule).

Reports the table's columns, the distribution of DECR_CHRG_ALLOW values by
company, a few sample policies per value, and optionally one policy's value
through PolicyInformation. Writes nothing.

Usage:
    venv\\Scripts\\python.exe tools/policyrecord/probe_decrease_charge_rule.py [--region CKPR]
        [--policy U0416030 --company 01] [--samples 3]
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from suiteview.core.db2_connection import DB2Connection
from suiteview.core.db2_constants import REGION_DSN_MAP


def _compare_sa_basis(by_plan: dict) -> dict:
    """Pair each configured illustration plancode's DB values with its SA_Basis."""
    table = json.loads(
        (ROOT / "suiteview" / "illustration" / "plancodes" / "plancode_table.json")
        .read_text(encoding="utf-8")
    )
    rows = next((v for v in table.values() if isinstance(v, list)), []) \
        if isinstance(table, dict) else table
    result = {}
    summary: dict = {}
    for row in rows:
        plan = str(row.get("Plancode", "")).strip()
        if plan in by_plan:
            basis = row.get("SA_Basis")
            result[plan] = {"sa_basis": basis, "values": by_plan[plan]}
            for value, count in by_plan[plan].items():
                key = f"{basis}|{value}"
                entry = summary.setdefault(key, {"policies": 0, "plancodes": []})
                entry["policies"] += count
                entry["plancodes"].append(plan)
    return {"summary": summary, "plans": result}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--region", choices=sorted(REGION_DSN_MAP), default="CKPR")
    parser.add_argument("--policy")
    parser.add_argument("--company")
    parser.add_argument("--samples", type=int, default=3)
    parser.add_argument("--by-plancode", action="store_true",
                        help="Also compare per-plancode values with illustration SA_Basis")
    parser.add_argument("--summary-only", action="store_true",
                        help="With --by-plancode, print only the SA_Basis/value summary")
    args = parser.parse_args()
    if os.environ.get("SUITEVIEW_LOCAL_DATA") == "1":
        raise RuntimeError("Live verification requires local data disabled.")

    output: dict = {"region": args.region}
    db = DB2Connection(args.region)
    try:
        columns, _ = db.execute_query_with_headers(
            "SELECT * FROM DB2TAB.TH_NON_TRD_POL WHERE 1 = 0"
        )
        output["columns"] = [c.upper() for c in columns]
        _, rows = db.execute_query_with_headers(
            "SELECT CK_CMP_CD, DECR_CHRG_ALLOW, COUNT(*) FROM DB2TAB.TH_NON_TRD_POL "
            "GROUP BY CK_CMP_CD, DECR_CHRG_ALLOW ORDER BY CK_CMP_CD, DECR_CHRG_ALLOW"
        )
        output["distribution"] = [
            {"company": r[0], "value": r[1], "count": int(r[2])} for r in rows
        ]
        samples = {}
        for value in sorted({r[1] for r in rows}, key=lambda v: (v is None, str(v))):
            # Values come from the distribution query above; quote-escaped literal
            # avoids DataDirect's HY004 on inferred parameter types.
            if value is None:
                where = "T.DECR_CHRG_ALLOW IS NULL"
            else:
                where = "T.DECR_CHRG_ALLOW = '" + str(value).replace("'", "''") + "'"
            params = None
            _, sample_rows = db.execute_query_with_headers(
                "SELECT B.CK_POLICY_NBR, B.CK_CMP_CD, C.PLN_DES_SER_CD "
                "FROM DB2TAB.TH_NON_TRD_POL T "
                "JOIN DB2TAB.LH_BAS_POL B ON B.CK_SYS_CD = T.CK_SYS_CD "
                "AND B.CK_CMP_CD = T.CK_CMP_CD AND B.TCH_POL_ID = T.TCH_POL_ID "
                "JOIN DB2TAB.LH_COV_PHA C ON C.CK_SYS_CD = T.CK_SYS_CD "
                "AND C.CK_CMP_CD = T.CK_CMP_CD AND C.TCH_POL_ID = T.TCH_POL_ID "
                f"AND C.COV_PHA_NBR = 1 WHERE {where} "
                f"FETCH FIRST {int(args.samples)} ROWS ONLY",
                params,
            )
            samples[repr(value)] = [
                {"policy": str(s[0]).strip(), "company": s[1], "plancode": str(s[2]).strip()}
                for s in sample_rows
            ]
        output["samples"] = samples
        if args.by_plancode:
            _, plan_rows = db.execute_query_with_headers(
                "SELECT C.PLN_DES_SER_CD, T.DECR_CHRG_ALLOW, COUNT(*) "
                "FROM DB2TAB.TH_NON_TRD_POL T "
                "JOIN DB2TAB.LH_COV_PHA C ON C.CK_SYS_CD = T.CK_SYS_CD "
                "AND C.CK_CMP_CD = T.CK_CMP_CD AND C.TCH_POL_ID = T.TCH_POL_ID "
                "AND C.COV_PHA_NBR = 1 "
                "GROUP BY C.PLN_DES_SER_CD, T.DECR_CHRG_ALLOW"
            )
            by_plan: dict = {}
            for plan, value, count in plan_rows:
                by_plan.setdefault(str(plan).strip(), {})[repr(value)] = int(count)
            output["by_plancode"] = _compare_sa_basis(by_plan)
    finally:
        db.close()

    if args.policy:
        from suiteview.polview.services.policy_service import get_policy_info

        pi = get_policy_info(args.policy, args.region, args.company)
        output["policy"] = {
            "policy": args.policy,
            "exists": bool(pi and pi.exists),
            "decrease_charge_rule": pi.support.decrease_charge_rule if pi and pi.exists else None,
            "decrease_charge_allowed": (
                pi.support.decrease_charge_allowed if pi and pi.exists else None
            ),
        }
    if args.summary_only and "by_plancode" in output:
        output = {"region": args.region, "summary": output["by_plancode"]["summary"],
                  "policy": output.get("policy")}
    print(json.dumps(output, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
