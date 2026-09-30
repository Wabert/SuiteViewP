"""List in-force, premium-paying ISWL policies (advanced, product line I), read-only.

Usage: venv\\Scripts\\python.exe tools\\rerun\\find_iswl_policies.py [--region CKPR] [--limit 60]
       [--output <csv>]

One row per policy: company, policy, base plancode, units, premium per unit, issue
date/age, modal premium, payment frequency, bill form, and the count of active
supplemental benefits, so roll-forward test cases with and without riders, on
each plancode and billing mode, can be picked.
"""
from __future__ import annotations

import argparse
import csv
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from suiteview.core.db2_connection import DB2Connection
from suiteview.core.db2_constants import DEFAULT_SCHEMA, REGION_DSN_MAP, REGION_SCHEMA_MAP


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--region", choices=sorted(REGION_DSN_MAP), default="CKPR")
    parser.add_argument("--limit", type=int, default=60)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    if os.environ.get("SUITEVIEW_LOCAL_DATA") == "1":
        raise RuntimeError("This helper reads live DB2 policy data only.")
    schema = REGION_SCHEMA_MAP.get(args.region, DEFAULT_SCHEMA)
    sql = f"""
SELECT POL.CK_CMP_CD, POL.CK_POLICY_NBR, COV.PLN_DES_SER_CD, COV.COV_UNT_QTY,
       COV.ANN_PRM_UNT_AMT, COV.ISSUE_DT, COV.INS_ISS_AGE, COV.INS_SEX_CD,
       POL.POL_PRM_AMT, POL.PMT_FQY_PER, POL.BIL_FRM_CD, POL.PRM_PAY_STA_REA_CD,
       (SELECT COUNT(*) FROM {schema}.LH_SPM_BNF BNF
         WHERE BNF.CK_SYS_CD = POL.CK_SYS_CD AND BNF.CK_CMP_CD = POL.CK_CMP_CD
           AND BNF.TCH_POL_ID = POL.TCH_POL_ID AND BNF.BNF_CEA_DT > CURRENT DATE) AS ACTIVE_BENEFITS,
       (SELECT COUNT(*) FROM {schema}.LH_COV_PHA C2
         WHERE C2.CK_SYS_CD = POL.CK_SYS_CD AND C2.CK_CMP_CD = POL.CK_CMP_CD
           AND C2.TCH_POL_ID = POL.TCH_POL_ID) AS COVERAGES
FROM {schema}.LH_BAS_POL POL
INNER JOIN {schema}.LH_COV_PHA COV
    ON COV.CK_SYS_CD = POL.CK_SYS_CD AND COV.CK_CMP_CD = POL.CK_CMP_CD
   AND COV.TCH_POL_ID = POL.TCH_POL_ID AND COV.COV_PHA_NBR = 1
WHERE POL.CK_SYS_CD = 'I'
  AND POL.NON_TRD_POL_IND = '1'
  AND COV.PRD_LIN_TYP_CD = 'I'
  AND POL.PRM_PAY_STA_REA_CD = '22'
ORDER BY POL.CK_CMP_CD, COV.PLN_DES_SER_CD, POL.CK_POLICY_NBR
FETCH FIRST {int(args.limit)} ROWS ONLY
"""
    db = DB2Connection(args.region)
    cursor = None
    try:
        cursor = db.connect().cursor()
        cursor.execute(sql)
        columns = [d[0] for d in cursor.description]
        rows = [
            [value.strip() if isinstance(value, str) else value for value in row]
            for row in cursor.fetchall()
        ]
    finally:
        if cursor is not None:
            cursor.close()
        db.close()
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        with args.output.open("w", newline="", encoding="utf-8-sig") as fh:
            writer = csv.writer(fh)
            writer.writerow(columns)
            writer.writerows(rows)
    for row in rows:
        print(json.dumps(dict(zip(columns, row)), default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
