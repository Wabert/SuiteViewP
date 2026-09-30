"""Count ISWL policies' non-base coverages (rider plancodes), read-only.

Usage: venv\\Scripts\\python.exe tools\\rerun\\count_iswl_riders.py [--region CKPR]

For in-force premium-paying ISWL policies (advanced, product line I), counts the
coverage phases after phase 1 by plancode and product line, so rider support for
ISWL illustrations can be scoped against the real in-force population.
"""
from __future__ import annotations

import argparse
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
    args = parser.parse_args()
    if os.environ.get("SUITEVIEW_LOCAL_DATA") == "1":
        raise RuntimeError("This helper reads live DB2 policy data only.")
    schema = REGION_SCHEMA_MAP.get(args.region, DEFAULT_SCHEMA)
    sql = f"""
SELECT RID.PLN_DES_SER_CD, RID.PRD_LIN_TYP_CD, COUNT(*) AS PHASES,
       SUM(CASE WHEN RID.ADV_PRD_IND = '1' THEN 1 ELSE 0 END) AS ADVANCED_PHASES
FROM {schema}.LH_BAS_POL POL
INNER JOIN {schema}.LH_COV_PHA BASE
    ON BASE.CK_SYS_CD = POL.CK_SYS_CD AND BASE.CK_CMP_CD = POL.CK_CMP_CD
   AND BASE.TCH_POL_ID = POL.TCH_POL_ID AND BASE.COV_PHA_NBR = 1
INNER JOIN {schema}.LH_COV_PHA RID
    ON RID.CK_SYS_CD = POL.CK_SYS_CD AND RID.CK_CMP_CD = POL.CK_CMP_CD
   AND RID.TCH_POL_ID = POL.TCH_POL_ID AND RID.COV_PHA_NBR > 1
WHERE POL.CK_SYS_CD = 'I'
  AND POL.NON_TRD_POL_IND = '1'
  AND BASE.PRD_LIN_TYP_CD = 'I'
  AND POL.PRM_PAY_STA_REA_CD = '22'
GROUP BY RID.PLN_DES_SER_CD, RID.PRD_LIN_TYP_CD
ORDER BY PHASES DESC
"""
    db = DB2Connection(args.region)
    cursor = None
    try:
        cursor = db.connect().cursor()
        cursor.execute(sql)
        columns = [d[0] for d in cursor.description]
        for row in cursor.fetchall():
            print(json.dumps(dict(zip(columns, [v.strip() if isinstance(v, str) else v for v in row])),
                             default=str))
    finally:
        if cursor is not None:
            cursor.close()
        db.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
