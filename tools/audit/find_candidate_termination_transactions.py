"""Find terminated CKPR policies with candidate termination transactions."""
from __future__ import annotations

import argparse
import csv
import json
import os
import sys
from collections import Counter
from pathlib import Path

import pyodbc

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from suiteview.core.db2_connection import DB2Connection
from suiteview.core.db2_constants import DEFAULT_SCHEMA, REGION_DSN_MAP, REGION_SCHEMA_MAP


TRANSACTION_CODES = ("SJ", "SL", "T9", "TV")
TERMINATED_LAST_ENTRY_CODES = ("J", "L", "M", "N", "O", "P", "Q", "X")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--region", choices=sorted(REGION_DSN_MAP), default="CKPR")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if os.environ.get("SUITEVIEW_LOCAL_DATA") == "1":
        raise RuntimeError("Live termination verification requires local data disabled.")

    schema = REGION_SCHEMA_MAP.get(args.region, DEFAULT_SCHEMA)
    trans_params = ", ".join("CAST(? AS CHAR(2))" for _ in TRANSACTION_CODES)
    entry_params = ", ".join(
        "CAST(? AS CHAR(1))" for _ in TERMINATED_LAST_ENTRY_CODES
    )
    sql = f"""
WITH CANDIDATE_TRANS AS (
    SELECT FH.CK_CMP_CD, FH.TCH_POL_ID, FH.TRANS, FH.ENTRY_DT, FH.ASOF_DT,
           FH.ENTRY_TIME, FH.SEQ_NO,
           ROW_NUMBER() OVER (
               PARTITION BY FH.CK_CMP_CD, FH.TCH_POL_ID, FH.TRANS
               ORDER BY FH.ENTRY_DT DESC NULLS LAST,
                        FH.ENTRY_TIME DESC NULLS LAST,
                        FH.SEQ_NO DESC
           ) AS TRANS_ROW
    FROM {schema}.FH_FIXED FH
    WHERE FH.TRANS IN ({trans_params})
      AND FH.FCB0_REV_IND = '0'
      AND FH.FCB2_REV_APPL_IND = '0'
),
BASELINE_TERMINATION AS (
    SELECT FH.CK_CMP_CD, FH.TCH_POL_ID, MAX(FH.ENTRY_DT) AS BASELINE_ENTRY_DT
    FROM {schema}.FH_FIXED FH
    WHERE FH.TRANS IN ('SC', 'SI', 'SF', 'TD', 'TM', 'TN', 'TL', 'TO')
      AND FH.FCB0_REV_IND = '0'
      AND FH.FCB2_REV_APPL_IND = '0'
    GROUP BY FH.CK_CMP_CD, FH.TCH_POL_ID
)
SELECT POL.CK_POLICY_NBR AS POLICY_NUMBER,
       POL.CK_CMP_CD AS COMPANY_CODE,
       POL.LST_ETR_CD AS LAST_ENTRY_CODE,
       CT.TRANS AS TRANSACTION_CODE,
       CT.ENTRY_DT,
       CT.ASOF_DT AS EFFECTIVE_DATE,
       CT.ENTRY_TIME,
       CT.SEQ_NO,
       BT.BASELINE_ENTRY_DT,
       CASE
           WHEN CT.TRANS = 'SJ' AND POL.LST_ETR_CD = 'Q' THEN 'Y'
           WHEN CT.TRANS = 'SL' AND POL.LST_ETR_CD = 'X' THEN 'Y'
           WHEN CT.TRANS = 'T9' THEN 'Y'
           WHEN CT.TRANS = 'TV' AND POL.LST_ETR_CD = 'Q' THEN 'Y'
           ELSE 'N'
       END AS EXPECTED_STATUS_MATCH,
       CASE
           WHEN NOT (
               (CT.TRANS = 'SJ' AND POL.LST_ETR_CD = 'Q')
               OR (CT.TRANS = 'SL' AND POL.LST_ETR_CD = 'X')
               OR CT.TRANS = 'T9'
               OR (CT.TRANS = 'TV' AND POL.LST_ETR_CD = 'Q')
           ) THEN 'STATUS_MISMATCH'
           WHEN BT.BASELINE_ENTRY_DT IS NULL THEN 'ADDS_MISSING_DATE'
           WHEN CT.ENTRY_DT > BT.BASELINE_ENTRY_DT THEN 'REPLACES_WITH_LATER_DATE'
           ELSE 'NO_DATE_CHANGE'
       END AS CRITERION_69_IMPACT
FROM {schema}.LH_BAS_POL POL
INNER JOIN CANDIDATE_TRANS CT
    ON POL.CK_CMP_CD = CT.CK_CMP_CD
   AND POL.TCH_POL_ID = CT.TCH_POL_ID
   AND CT.TRANS_ROW = 1
LEFT OUTER JOIN BASELINE_TERMINATION BT
    ON POL.CK_CMP_CD = BT.CK_CMP_CD
   AND POL.TCH_POL_ID = BT.TCH_POL_ID
WHERE POL.CK_SYS_CD = 'I'
  AND POL.LST_ETR_CD IN ({entry_params})
ORDER BY CT.TRANS, CT.ENTRY_DT, POL.CK_CMP_CD, POL.CK_POLICY_NBR
"""

    db = DB2Connection(args.region)
    cursor = None
    try:
        cursor = db.connect().cursor()
        cursor.setinputsizes(
            [(pyodbc.SQL_VARCHAR, 2, 0)] * len(TRANSACTION_CODES)
            + [(pyodbc.SQL_VARCHAR, 1, 0)] * len(TERMINATED_LAST_ENTRY_CODES)
        )
        cursor.execute(sql, TRANSACTION_CODES + TERMINATED_LAST_ENTRY_CODES)
        columns = [description[0] for description in cursor.description]
        rows = [
            tuple(value.strip() if isinstance(value, str) else value for value in row)
            for row in cursor.fetchall()
        ]
    finally:
        if cursor is not None:
            cursor.close()
        db.close()

    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("w", newline="", encoding="utf-8-sig") as output_file:
        writer = csv.writer(output_file)
        writer.writerow(columns)
        writer.writerows(tuple(row) for row in rows)

    matching_rows = [row for row in rows if row[9] == "Y"]
    matching_output = args.output.with_name(
        f"{args.output.stem}_matching_status{args.output.suffix}"
    )
    with matching_output.open("w", newline="", encoding="utf-8-sig") as output_file:
        writer = csv.writer(output_file)
        writer.writerow(columns)
        writer.writerows(matching_rows)

    counts = Counter(str(row[3]) for row in rows)
    status_counts = Counter((str(row[3]), str(row[2])) for row in rows)
    impact_counts = Counter((str(row[3]), str(row[10])) for row in rows)
    entry_dates = {
        code: [str(row[4]) for row in rows if row[3] == code and row[4] is not None]
        for code in TRANSACTION_CODES
    }
    print(json.dumps({
        "region": args.region,
        "transaction_codes": list(TRANSACTION_CODES),
        "excluded_rpu_eti": True,
        "row_count": len(rows),
        "policy_count": len({(str(row[0]), str(row[1])) for row in rows}),
        "matching_status_policy_count": len({
            (str(row[0]), str(row[1])) for row in matching_rows
        }),
        "counts_by_transaction": {
            code: counts.get(code, 0) for code in TRANSACTION_CODES
        },
        "counts_by_transaction_and_last_entry": {
            code: {
                entry_code: status_counts.get((code, entry_code), 0)
                for entry_code in TERMINATED_LAST_ENTRY_CODES
                if status_counts.get((code, entry_code), 0)
            }
            for code in TRANSACTION_CODES
        },
        "entry_date_range_by_transaction": {
            code: {
                "first": min(entry_dates[code]) if entry_dates[code] else None,
                "last": max(entry_dates[code]) if entry_dates[code] else None,
            }
            for code in TRANSACTION_CODES
        },
        "criterion_69_impact_by_transaction": {
            code: {
                impact: impact_counts.get((code, impact), 0)
                for impact in (
                    "ADDS_MISSING_DATE",
                    "REPLACES_WITH_LATER_DATE",
                    "NO_DATE_CHANGE",
                    "STATUS_MISMATCH",
                )
                if impact_counts.get((code, impact), 0)
            }
            for code in TRANSACTION_CODES
        },
        "output": str(args.output.resolve()),
        "matching_status_output": str(matching_output.resolve()),
        "all_ok": True,
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
