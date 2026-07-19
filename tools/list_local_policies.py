"""List every policy in the local dev policy DB with a feature summary.

Read-only introspection of bundled_data/dev/policy_records.sqlite (does not
touch the SUITEVIEW_LOCAL_DATA gate). For each policy: company, policy number,
form number, DB option, and feature flags (loans, riders, benefits,
substandard). Column names verified against PolicyInformation:
  LH_BAS_POL.CK_CMP_CD / CK_POLICY_NBR
  LH_COV_PHA.POL_FRM_NBR / PLN_DES_SER_CD / COV_PHA_NBR (1 = base, >1 = rider)
  LH_NON_TRD_POL.DTH_BNF_PLN_OPT_CD
  LH_SPM_BNF.SPM_BNF_TYP_CD + SPM_BNF_SBY_CD
  LH_CSH_VAL_LOAN / LH_FND_VAL_LOAN.LN_PRI_AMT
  LH_SST_XTR_CRG.SST_XTR_TYP_CD / SST_XTR_RT_TBL_CD / XTR_PER_1000_AMT

Usage:
    venv\\Scripts\\python.exe tools/list_local_policies.py
"""
from __future__ import annotations

import json
import sqlite3
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
POLICY_DB = ROOT / "bundled_data" / "dev" / "policy_records.sqlite"

COMPANY_NAMES = {"01": "ANICO", "04": "ANTEX", "06": "SLAICO", "08": "GSL", "26": "ANICO NY"}
DBO_NAMES = {"1": "A - Level", "2": "B - Increasing", "3": "C - ROP"}


def _rows(conn: sqlite3.Connection, sql: str, params=()) -> list:
    try:
        return conn.execute(sql, params).fetchall()
    except sqlite3.Error:
        return []


def main() -> None:
    if not POLICY_DB.exists():
        print(json.dumps({"error": f"local policy DB not found: {POLICY_DB}"}))
        return

    conn = sqlite3.connect(POLICY_DB)
    conn.row_factory = sqlite3.Row

    policies = []
    for bas in _rows(conn, "SELECT * FROM LH_BAS_POL ORDER BY CK_CMP_CD, CK_POLICY_NBR"):
        pol_id = bas["TCH_POL_ID"]
        covs = _rows(
            conn,
            "SELECT COV_PHA_NBR, POL_FRM_NBR, PLN_DES_SER_CD FROM LH_COV_PHA "
            "WHERE TCH_POL_ID=? ORDER BY COV_PHA_NBR",
            (pol_id,),
        )
        base = next((c for c in covs if int(c["COV_PHA_NBR"] or 0) == 1), None)
        riders = [c for c in covs if int(c["COV_PHA_NBR"] or 0) > 1]

        dbo_rows = _rows(
            conn, "SELECT DTH_BNF_PLN_OPT_CD FROM LH_NON_TRD_POL WHERE TCH_POL_ID=?", (pol_id,)
        )
        dbo_code = str(dbo_rows[0]["DTH_BNF_PLN_OPT_CD"]).strip() if dbo_rows else ""

        benefits = [
            (str(r["SPM_BNF_TYP_CD"] or "").strip() + str(r["SPM_BNF_SBY_CD"] or "").strip())
            for r in _rows(
                conn,
                "SELECT SPM_BNF_TYP_CD, SPM_BNF_SBY_CD FROM LH_SPM_BNF WHERE TCH_POL_ID=?",
                (pol_id,),
            )
        ]

        loan_principal = 0.0
        for table in ("LH_CSH_VAL_LOAN", "LH_FND_VAL_LOAN"):
            for r in _rows(conn, f"SELECT LN_PRI_AMT FROM {table} WHERE TCH_POL_ID=?", (pol_id,)):
                loan_principal += float(r["LN_PRI_AMT"] or 0)

        substd = _rows(
            conn,
            "SELECT SST_XTR_TYP_CD, SST_XTR_RT_TBL_CD, XTR_PER_1000_AMT "
            "FROM LH_SST_XTR_CRG WHERE TCH_POL_ID=?",
            (pol_id,),
        )
        substd_bits = []
        for r in substd:
            table_cd = str(r["SST_XTR_RT_TBL_CD"] or "").strip()
            flat = float(r["XTR_PER_1000_AMT"] or 0)
            if table_cd and table_cd != "0":
                substd_bits.append(f"table {table_cd}")
            if flat:
                substd_bits.append(f"flat {flat:g}/1000")

        company = str(bas["CK_CMP_CD"] or "").strip()
        policies.append(
            {
                "company_code": company,
                "company": COMPANY_NAMES.get(company, company),
                "policy": str(bas["CK_POLICY_NBR"] or "").strip(),
                "form": str(base["POL_FRM_NBR"] or "").strip() if base else "",
                "plancode": str(base["PLN_DES_SER_CD"] or "").strip() if base else "",
                "db_option": DBO_NAMES.get(dbo_code, dbo_code or "(trad/none)"),
                "loan_principal": round(loan_principal, 2),
                "rider_plancodes": [str(r["PLN_DES_SER_CD"] or "").strip() for r in riders],
                "benefit_codes": sorted(set(benefits)),
                "substandard": sorted(set(substd_bits)),
            }
        )

    print(json.dumps({"db": str(POLICY_DB), "count": len(policies), "policies": policies}, indent=1))


if __name__ == "__main__":
    main()
