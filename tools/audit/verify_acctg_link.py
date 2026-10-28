"""Verify the FH_ACCTG -> FH_FIXED link keys with metadata and aggregate counts only.

Reads zero-row column metadata for both tables, then reports aggregate key
statistics over a bounded entry-date window. FH_ACCTG carries no dates or
CK_SYS_CD, so CK_CMP_CD + TCH_POL_ID + SEQ_NO is the only possible link.
No policy rows are printed.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from suiteview.audit.transaction_filters import TransactionCriteria, transaction_predicates
from suiteview.core.db2_connection import DB2Connection
from suiteview.core.db2_constants import DEFAULT_SCHEMA, REGION_DSN_MAP, REGION_SCHEMA_MAP


def _scalar_rows(connection, sql: str) -> list[tuple]:
    cursor = connection.cursor()
    try:
        cursor.execute(sql)
        return [tuple(row) for row in cursor.fetchall()]
    finally:
        cursor.close()


def _columns(connection, schema: str, table: str) -> list[dict]:
    cursor = connection.cursor()
    try:
        cursor.execute(f"SELECT * FROM {schema}.{table} WHERE 1 = 0")
        return [
            {"column": item[0], "python_type": item[1].__name__,
             "precision": item[4], "scale": item[5], "nullable": item[6]}
            for item in cursor.description
        ]
    finally:
        cursor.close()


def _predicate_smoke(connection, schema: str, from_date: str, to_date: str) -> dict:
    """Run the production Acct Number predicate; its policy count must equal a distinct join."""
    window = f"FX.ENTRY_DT BETWEEN '{from_date}' AND '{to_date}'"
    account = _scalar_rows(connection, (
        f"SELECT AC.ACCTG_NBR, COUNT(*) FROM {schema}.FH_FIXED FX INNER JOIN {schema}.FH_ACCTG AC"
        f" ON AC.CK_CMP_CD = FX.CK_CMP_CD AND AC.TCH_POL_ID = FX.TCH_POL_ID"
        f" AND AC.SEQ_NO = FX.SEQ_NO WHERE {window} AND AC.ACCTG_NBR IS NOT NULL"
        f" GROUP BY AC.ACCTG_NBR ORDER BY 2 DESC FETCH FIRST 1 ROW ONLY"
    ))[0][0].strip()
    criteria = TransactionCriteria(entry_date=(from_date, to_date), account_numbers=account)
    predicate = transaction_predicates(criteria, TransactionCriteria(), schema)[0]
    production = _scalar_rows(connection, (
        f"SELECT COUNT(*) FROM {schema}.LH_BAS_POL POLICY1 WHERE {predicate}"
    ))[0][0]
    distinct_join = _scalar_rows(connection, (
        f"SELECT COUNT(*) FROM (SELECT DISTINCT P.CK_SYS_CD, P.CK_CMP_CD, P.TCH_POL_ID"
        f" FROM {schema}.LH_BAS_POL P INNER JOIN {schema}.FH_FIXED FX"
        f" ON FX.CK_CMP_CD = P.CK_CMP_CD AND FX.TCH_POL_ID = P.TCH_POL_ID"
        f" INNER JOIN {schema}.FH_ACCTG AC ON AC.CK_CMP_CD = FX.CK_CMP_CD"
        f" AND AC.TCH_POL_ID = FX.TCH_POL_ID AND AC.SEQ_NO = FX.SEQ_NO"
        f" WHERE {window} AND AC.ACCTG_NBR = '{account}') D"
    ))[0][0]
    raw_join = _scalar_rows(connection, (
        f"SELECT COUNT(*) FROM {schema}.LH_BAS_POL P INNER JOIN {schema}.FH_FIXED FX"
        f" ON FX.CK_CMP_CD = P.CK_CMP_CD AND FX.TCH_POL_ID = P.TCH_POL_ID"
        f" INNER JOIN {schema}.FH_ACCTG AC ON AC.CK_CMP_CD = FX.CK_CMP_CD"
        f" AND AC.TCH_POL_ID = FX.TCH_POL_ID AND AC.SEQ_NO = FX.SEQ_NO"
        f" WHERE {window} AND AC.ACCTG_NBR = '{account}'"
    ))[0][0]
    return {
        "production_policy_count": production,
        "distinct_join_policy_count": distinct_join,
        "raw_join_row_count": raw_join,
        "no_duplicates": production == distinct_join,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--region", choices=sorted(REGION_DSN_MAP), default="CKPR")
    parser.add_argument("--from-date", default="2024-01-01",
                        help="Inclusive FH_FIXED.ENTRY_DT lower bound for aggregate checks.")
    parser.add_argument("--to-date", default="2024-01-02",
                        help="Inclusive FH_FIXED.ENTRY_DT upper bound for aggregate checks.")
    parser.add_argument("--describe-only", action="store_true")
    args = parser.parse_args()
    if os.environ.get("SUITEVIEW_LOCAL_DATA") == "1":
        raise RuntimeError("Live schema verification requires SUITEVIEW_LOCAL_DATA disabled.")
    db = DB2Connection(args.region)
    schema = REGION_SCHEMA_MAP.get(args.region, DEFAULT_SCHEMA)
    window = f"FX.ENTRY_DT BETWEEN '{args.from_date}' AND '{args.to_date}'"
    output: dict = {"region": args.region, "schema": schema}
    try:
        connection = db.connect()
        acctg = _columns(connection, schema, "FH_ACCTG")
        fixed = _columns(connection, schema, "FH_FIXED")
        output["FH_ACCTG_columns"] = acctg
        output["FH_FIXED_key_like_columns"] = [
            item for item in fixed
            if item["column"] in {"CK_SYS_CD", "CK_CMP_CD", "TCH_POL_ID", "SEQ_NO",
                                  "ENTRY_DT", "ASOF_DT", "ENTRY_TIME", "TRANS"}
        ]
        if not args.describe_only:
            checks = {
                "fixed_rows_in_window": (
                    f"SELECT COUNT(*) FROM {schema}.FH_FIXED FX WHERE {window}"
                ),
                "fixed_key_duplicates_cmp_pol_seq": (
                    f"SELECT COUNT(*) FROM (SELECT FX.CK_CMP_CD, FX.TCH_POL_ID, FX.SEQ_NO"
                    f" FROM {schema}.FH_FIXED FX WHERE {window}"
                    f" GROUP BY FX.CK_CMP_CD, FX.TCH_POL_ID, FX.SEQ_NO HAVING COUNT(*) > 1) D"
                ),
                "fixed_rows_with_acctg_cmp_pol_seq": (
                    f"SELECT COUNT(*) FROM {schema}.FH_FIXED FX WHERE {window}"
                    f" AND EXISTS (SELECT 1 FROM {schema}.FH_ACCTG AC"
                    f" WHERE AC.CK_CMP_CD = FX.CK_CMP_CD AND AC.TCH_POL_ID = FX.TCH_POL_ID"
                    f" AND AC.SEQ_NO = FX.SEQ_NO)"
                ),
                "acctg_rows_per_fixed_cmp_pol_seq": (
                    f"SELECT N, COUNT(*) FROM (SELECT COUNT(*) AS N"
                    f" FROM {schema}.FH_FIXED FX INNER JOIN {schema}.FH_ACCTG AC"
                    f" ON AC.CK_CMP_CD = FX.CK_CMP_CD AND AC.TCH_POL_ID = FX.TCH_POL_ID"
                    f" AND AC.SEQ_NO = FX.SEQ_NO WHERE {window}"
                    f" GROUP BY FX.CK_CMP_CD, FX.TCH_POL_ID, FX.SEQ_NO) G"
                    f" GROUP BY N ORDER BY N"
                ),
                "acctg_db_cr_per_fixed_cmp_pol_seq": (
                    f"SELECT DB_CR, COUNT(*) FROM (SELECT"
                    f" LISTAGG(AC.ACCTG_DB_CR_IND, ',') WITHIN GROUP (ORDER BY AC.ACCTG_SEQ) AS DB_CR"
                    f" FROM {schema}.FH_FIXED FX INNER JOIN {schema}.FH_ACCTG AC"
                    f" ON AC.CK_CMP_CD = FX.CK_CMP_CD AND AC.TCH_POL_ID = FX.TCH_POL_ID"
                    f" AND AC.SEQ_NO = FX.SEQ_NO WHERE {window}"
                    f" GROUP BY FX.CK_CMP_CD, FX.TCH_POL_ID, FX.SEQ_NO) G"
                    f" GROUP BY DB_CR ORDER BY 2 DESC FETCH FIRST 10 ROWS ONLY"
                ),
                "acctg_nbr_distinct_in_window": (
                    f"SELECT COUNT(DISTINCT AC.ACCTG_NBR) FROM {schema}.FH_FIXED FX"
                    f" INNER JOIN {schema}.FH_ACCTG AC"
                    f" ON AC.CK_CMP_CD = FX.CK_CMP_CD AND AC.TCH_POL_ID = FX.TCH_POL_ID"
                    f" AND AC.SEQ_NO = FX.SEQ_NO WHERE {window}"
                ),
            }
            results = {}
            for name, sql in checks.items():
                try:
                    results[name] = [list(map(str, row)) for row in _scalar_rows(connection, sql)]
                except Exception as error:  # report each check independently
                    results[name] = f"ERROR: {error}"
            output["checks"] = results
            output["predicate_smoke"] = _predicate_smoke(
                connection, schema, args.from_date, args.to_date,
            )
    finally:
        db.close()
    print(json.dumps(output, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
