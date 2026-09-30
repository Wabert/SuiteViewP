"""Sample ISWL premium receipts (gross/net/charge) with coverage basics, read-only.

Usage: venv\\Scripts\\python.exe tools\\rerun\\sample_iswl_receipts.py --output <csv>
       [--region CKPR] [--limit 400] [--plancode 81335200] [--since 2026-01-01]

For in-force premium-paying ISWL policies (advanced, product line I), returns each
policy's most recent unreversed, processed PR receipt on or after ``--since`` with
units, premium per unit, issue age/date, modal premium, frequency, bill form and the
active benefit count. Used to derive how CyberLife splits a fixed ISWL premium into
premium load, policy fee, benefit premiums and the net amount credited to the account.
"""
from __future__ import annotations

import argparse
import csv
import os
import sys
from pathlib import Path

import pyodbc

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from suiteview.core.db2_connection import DB2Connection
from suiteview.core.db2_constants import DEFAULT_SCHEMA, REGION_DSN_MAP, REGION_SCHEMA_MAP


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--region", choices=sorted(REGION_DSN_MAP), default="CKPR")
    parser.add_argument("--limit", type=int, default=400)
    parser.add_argument("--plancode", default="")
    parser.add_argument("--since", default="2026-01-01")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if os.environ.get("SUITEVIEW_LOCAL_DATA") == "1":
        raise RuntimeError("This helper reads live DB2 policy data only.")
    schema = REGION_SCHEMA_MAP.get(args.region, DEFAULT_SCHEMA)
    plan_filter = "AND COV.PLN_DES_SER_CD = CAST(? AS CHAR(8))" if args.plancode else ""
    sql = f"""
WITH RECEIPTS AS (
    SELECT FH.CK_CMP_CD, FH.TCH_POL_ID, FH.ASOF_DT, FH.GROSS_AMT, FH.NET_AMT, FH.CHARGE_AMT,
           FH.DURATION,
           ROW_NUMBER() OVER (PARTITION BY FH.CK_CMP_CD, FH.TCH_POL_ID
                              ORDER BY FH.ASOF_DT DESC, FH.SEQ_NO DESC) AS RN
    FROM {schema}.FH_FIXED FH
    WHERE FH.TRANS = 'PR' AND FH.FCB0_REV_IND = '0' AND FH.FCB2_REV_APPL_IND = '0'
      AND FH.FBB3_PROCD_IND = '1' AND FH.ASOF_DT >= CAST(? AS DATE)
)
SELECT POL.CK_CMP_CD, POL.CK_POLICY_NBR, COV.PLN_DES_SER_CD, COV.COV_UNT_QTY,
       COV.ANN_PRM_UNT_AMT, COV.ISSUE_DT, COV.INS_ISS_AGE, COV.INS_SEX_CD,
       POL.POL_PRM_AMT, POL.PMT_FQY_PER, POL.BIL_FRM_CD,
       R.ASOF_DT, R.DURATION, R.GROSS_AMT, R.NET_AMT, R.CHARGE_AMT,
       (SELECT COUNT(*) FROM {schema}.LH_SPM_BNF BNF
         WHERE BNF.CK_SYS_CD = POL.CK_SYS_CD AND BNF.CK_CMP_CD = POL.CK_CMP_CD
           AND BNF.TCH_POL_ID = POL.TCH_POL_ID AND BNF.BNF_CEA_DT > R.ASOF_DT) AS ACTIVE_BENEFITS,
       (SELECT COUNT(*) FROM {schema}.LH_COV_PHA C2
         WHERE C2.CK_SYS_CD = POL.CK_SYS_CD AND C2.CK_CMP_CD = POL.CK_CMP_CD
           AND C2.TCH_POL_ID = POL.TCH_POL_ID) AS COVERAGES
FROM {schema}.LH_BAS_POL POL
INNER JOIN {schema}.LH_COV_PHA COV
    ON COV.CK_SYS_CD = POL.CK_SYS_CD AND COV.CK_CMP_CD = POL.CK_CMP_CD
   AND COV.TCH_POL_ID = POL.TCH_POL_ID AND COV.COV_PHA_NBR = 1
INNER JOIN RECEIPTS R
    ON R.CK_CMP_CD = POL.CK_CMP_CD AND R.TCH_POL_ID = POL.TCH_POL_ID AND R.RN = 1
WHERE POL.CK_SYS_CD = 'I'
  AND POL.NON_TRD_POL_IND = '1'
  AND COV.PRD_LIN_TYP_CD = 'I'
  AND POL.PRM_PAY_STA_REA_CD = '22'
  {plan_filter}
ORDER BY POL.CK_CMP_CD, COV.PLN_DES_SER_CD, POL.CK_POLICY_NBR
FETCH FIRST {int(args.limit)} ROWS ONLY
"""
    params = [args.since] + ([args.plancode] if args.plancode else [])
    db = DB2Connection(args.region)
    cursor = None
    try:
        cursor = db.connect().cursor()
        cursor.setinputsizes([(pyodbc.SQL_VARCHAR, 10, 0)] * len(params))
        cursor.execute(sql, params)
        columns = [d[0] for d in cursor.description]
        rows = [
            [value.strip() if isinstance(value, str) else value for value in row]
            for row in cursor.fetchall()
        ]
    finally:
        if cursor is not None:
            cursor.close()
        db.close()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("w", newline="", encoding="utf-8-sig") as fh:
        writer = csv.writer(fh)
        writer.writerow(columns)
        writer.writerows(rows)
    print(f"{len(rows)} rows -> {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
