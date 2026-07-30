r"""Probe LH_POL_MVRY_VAL: connectivity, schema, and last-monthliversary values.

Single-purpose helper used to validate the account-value batch approach before
running it over the full GLP workbook. It:

  1. Confirms DB2 connectivity for a region.
  2. Prints the column list of ``LH_POL_MVRY_VAL``.
  3. For an optional sample policy, resolves ``TCH_POL_ID`` from ``LH_BAS_POL``
     and lists that policy's monthliversary rows (MVRY_DT, CSV_AMT) ordered
     newest-first, so we can confirm the most-recent row (index 0) is the
     "last monthliversary" account value the Advanced Product tab shows.

Usage:
    venv\Scripts\python.exe tools/probe_mvry_schema.py [--region CKPR]
        [--policy UL020000] [--company 01]
"""
from __future__ import annotations

import argparse
import json
import sys

sys.path.insert(0, ".")
from suiteview.core.db2_connection import DB2Connection  # noqa: E402


def _sql_literal(value: str) -> str:
    return "'" + str(value).replace("'", "''") + "'"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--region", default="CKPR")
    ap.add_argument("--policy", default=None)
    ap.add_argument("--company", default=None)
    ap.add_argument("--system", default="I")
    args = ap.parse_args()

    out: dict = {"region": args.region}

    db = DB2Connection(region=args.region)

    # 1. Connectivity + schema.
    cols, _ = db.execute_query_with_headers(
        "SELECT * FROM DB2TAB.LH_POL_MVRY_VAL FETCH FIRST 1 ROWS ONLY"
    )
    out["mvry_columns"] = cols

    # 2. Sample policy.
    if args.policy:
        where = [
            f"CK_SYS_CD = {_sql_literal(args.system)}",
            f"CK_POLICY_NBR = {_sql_literal(args.policy)}",
        ]
        if args.company:
            where.append(f"CK_CMP_CD = {_sql_literal(args.company)}")
        sql = (
            "SELECT CK_CMP_CD, CK_POLICY_NBR, TCH_POL_ID, NON_TRD_POL_IND "
            "FROM DB2TAB.LH_BAS_POL WHERE " + " AND ".join(where)
        )
        _, rows = db.execute_query_with_headers(sql)
        out["bas_pol"] = [
            {"company": str(r[0]).strip(), "policy": str(r[1]).strip(),
             "tch_pol_id": str(r[2]), "non_trd_ind": str(r[3]).strip()}
            for r in rows
        ]
        if rows:
            tch = str(rows[0][2])
            msql = (
                "SELECT MVRY_DT, CSV_AMT, CINS_AMT, POL_DUR_NBR "
                "FROM DB2TAB.LH_POL_MVRY_VAL "
                f"WHERE TCH_POL_ID = {_sql_literal(tch)} "
                "ORDER BY MVRY_DT DESC "
                "FETCH FIRST 5 ROWS ONLY"
            )
            mcols, mrows = db.execute_query_with_headers(msql)
            out["mvry_sample_cols"] = mcols
            out["mvry_sample_rows"] = [
                [str(c) for c in r] for r in mrows
            ]

    print(json.dumps(out, indent=2, ensure_ascii=False, default=str))


if __name__ == "__main__":
    main()
