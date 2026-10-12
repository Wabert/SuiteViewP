"""Check the ISWL RPU NSP roll-forward against every stored value on the record (read-only).

Pulls every company 01 interest sensitive whole life coverage (advanced, product line I)
on reduced paid-up (premium pay status 45) with its stored net single premiums
(``LOW_DUR_NSP_AMT``, ``LOW_DUR_1_NSP_AMT``, ``LOW_DUR_2_NSP_AMT`` at ``LOW_DUR_PER``)
and rolls the first and second values forward one year with the engine's own
``core/iswl_rpu/nsp_roll.roll_step`` and the coverage's mortality function code
(``MTL_FUN_CD``, which decides the claims factor). Reports match counts by NSP table with the fixed
tolerances (|step 1| <= 0.0115, |step 2| <= 0.0058) and with the rounding-propagation
tolerance of ``rounding_tolerance``, plus the population facts the workspace relies on
(value per unit, coverages per policy, loans, low duration against the last anniversary).

Usage:
    venv\\Scripts\\python.exe tools\\rerun\\verify_iswl_rpu_nsp.py [--region CKPR] [--company 01]
        [--misses 20] [--csv out.csv]
"""
from __future__ import annotations

import argparse
import csv
import os
import sys
from collections import Counter, defaultdict
from datetime import date, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from suiteview.core.db2_connection import DB2Connection  # noqa: E402
from suiteview.core.db2_constants import DEFAULT_SCHEMA, REGION_DSN_MAP, REGION_SCHEMA_MAP  # noqa: E402
from suiteview.illustration.core.iswl_rpu.nsp_roll import STEP_TOLERANCES, roll_step, rounding_tolerance  # noqa: E402
from suiteview.illustration.core.parwl.nsp import NSPError  # noqa: E402

FIXED_TOLERANCE_1, FIXED_TOLERANCE_2 = STEP_TOLERANCES


def _sql(schema: str, company: str) -> str:
    return f"""
SELECT POL.CK_CMP_CD, POL.CK_POLICY_NBR, COV.COV_PHA_NBR, COV.PLN_DES_SER_CD, COV.ISSUE_DT, COV.INS_ISS_AGE,
       COV.COV_UNT_QTY, COV.COV_VPU_AMT, COV.NSP_RPU_TBL_CD, COV.NSP_EI_TBL_CD, COV.NSP_ITS_RT, COV.RPU_BNF_CD,
       COV.MTL_FUN_CD,
       COV.LOW_DUR_PER, COV.LOW_DUR_NSP_AMT, COV.LOW_DUR_1_NSP_AMT, COV.LOW_DUR_2_NSP_AMT,
       POL.LST_ANV_DT, POL.PRM_PAID_TO_DT,
       (SELECT COUNT(*) FROM {schema}.LH_COV_PHA C2
         WHERE C2.CK_SYS_CD = POL.CK_SYS_CD AND C2.CK_CMP_CD = POL.CK_CMP_CD
           AND C2.TCH_POL_ID = POL.TCH_POL_ID) AS COVERAGES,
       (SELECT COALESCE(SUM(L.LN_PRI_AMT), 0) FROM {schema}.LH_CSH_VAL_LOAN L
         WHERE L.CK_SYS_CD = POL.CK_SYS_CD AND L.CK_CMP_CD = POL.CK_CMP_CD
           AND L.TCH_POL_ID = POL.TCH_POL_ID AND L.MVRY_DT = '9999-12-31' AND L.LN_PRI_AMT > 0) AS TRAD_LOAN,
       (SELECT MAX(F.MVRY_DT) FROM {schema}.LH_FND_VAL_LOAN F
         WHERE F.CK_SYS_CD = POL.CK_SYS_CD AND F.CK_CMP_CD = POL.CK_CMP_CD
           AND F.TCH_POL_ID = POL.TCH_POL_ID AND F.LN_PRI_AMT > 0) AS FUND_LOAN_DATE,
       (SELECT MAX(M.MVRY_DT) FROM {schema}.LH_POL_MVRY_VAL M
         WHERE M.CK_SYS_CD = POL.CK_SYS_CD AND M.CK_CMP_CD = POL.CK_CMP_CD
           AND M.TCH_POL_ID = POL.TCH_POL_ID) AS LAST_AV_DATE
FROM {schema}.LH_BAS_POL POL
INNER JOIN {schema}.LH_COV_PHA COV
    ON COV.CK_SYS_CD = POL.CK_SYS_CD AND COV.CK_CMP_CD = POL.CK_CMP_CD AND COV.TCH_POL_ID = POL.TCH_POL_ID
WHERE POL.CK_SYS_CD = 'I'
  AND POL.CK_CMP_CD = '{company}'
  AND POL.NON_TRD_POL_IND = '1'
  AND COV.PRD_LIN_TYP_CD = 'I'
  AND POL.PRM_PAY_STA_REA_CD = '45'
ORDER BY COV.NSP_RPU_TBL_CD, POL.CK_POLICY_NBR, COV.COV_PHA_NBR
"""


def _rider_sql(schema: str, company: str) -> str:
    """The other coverage phases on the same policies (riders the RPU conversion leaves on the record)."""
    return f"""
SELECT COV.PRD_LIN_TYP_CD, COV.CEA_REA_CD,
       CASE WHEN COALESCE(COV.LOW_DUR_NSP_AMT, 0) <> 0 OR COALESCE(COV.LOW_DUR_1_NSP_AMT, 0) <> 0
                 OR COALESCE(COV.LOW_DUR_2_NSP_AMT, 0) <> 0 THEN 'Y' ELSE 'N' END AS HAS_NSP,
       CASE WHEN COALESCE(COV.LOW_DUR_CSV_AMT, 0) <> 0 OR COALESCE(COV.LOW_DUR_1_CSV_AMT, 0) <> 0
                 THEN 'Y' ELSE 'N' END AS HAS_CV,
       CASE WHEN COV.COV_MT_EXP_DT > CURRENT DATE THEN 'Y' ELSE 'N' END AS NOT_MATURED,
       COUNT(*) AS N
FROM {schema}.LH_BAS_POL POL
INNER JOIN {schema}.LH_COV_PHA COV
    ON COV.CK_SYS_CD = POL.CK_SYS_CD AND COV.CK_CMP_CD = POL.CK_CMP_CD AND COV.TCH_POL_ID = POL.TCH_POL_ID
WHERE POL.CK_SYS_CD = 'I'
  AND POL.CK_CMP_CD = '{company}'
  AND POL.NON_TRD_POL_IND = '1'
  AND POL.PRM_PAY_STA_REA_CD = '45'
  AND COV.COV_PHA_NBR > 1
  AND EXISTS (SELECT 1 FROM {schema}.LH_COV_PHA B
               WHERE B.CK_SYS_CD = POL.CK_SYS_CD AND B.CK_CMP_CD = POL.CK_CMP_CD
                 AND B.TCH_POL_ID = POL.TCH_POL_ID AND B.COV_PHA_NBR = 1 AND B.PRD_LIN_TYP_CD = 'I')
GROUP BY COV.PRD_LIN_TYP_CD, COV.CEA_REA_CD,
       CASE WHEN COALESCE(COV.LOW_DUR_NSP_AMT, 0) <> 0 OR COALESCE(COV.LOW_DUR_1_NSP_AMT, 0) <> 0
                 OR COALESCE(COV.LOW_DUR_2_NSP_AMT, 0) <> 0 THEN 'Y' ELSE 'N' END,
       CASE WHEN COALESCE(COV.LOW_DUR_CSV_AMT, 0) <> 0 OR COALESCE(COV.LOW_DUR_1_CSV_AMT, 0) <> 0
                 THEN 'Y' ELSE 'N' END,
       CASE WHEN COV.COV_MT_EXP_DT > CURRENT DATE THEN 'Y' ELSE 'N' END
ORDER BY 6 DESC
"""


def _date(value):
    if value is None or isinstance(value, date):
        return value
    return datetime.strptime(str(value).strip()[:10], "%Y-%m-%d").date()


def _years(start: date, end: date) -> int:
    return end.year - start.year - ((end.month, end.day) < (start.month, start.day))


def _fetch(region: str, company: str) -> tuple:
    schema = REGION_SCHEMA_MAP.get(region, DEFAULT_SCHEMA)
    db = DB2Connection(region)
    cursor = None
    try:
        cursor = db.connect().cursor()
        results = []
        for sql in (_sql(schema, company), _rider_sql(schema, company)):
            cursor.execute(sql)
            columns = [d[0] for d in cursor.description]
            results.append([dict(zip(columns, [v.strip() if isinstance(v, str) else v for v in row]))
                            for row in cursor.fetchall()])
        return tuple(results)
    finally:
        if cursor is not None:
            cursor.close()
        db.close()


def check_row(row: dict) -> dict:
    """Roll the coverage's first and second stored values forward and compare."""
    table = str(row["NSP_RPU_TBL_CD"] or "").strip()
    function_code = str(row.get("MTL_FUN_CD") or "").strip() or None
    interest = float(row["NSP_ITS_RT"] or 0) / 100.0
    issue_age, low = int(row["INS_ISS_AGE"]), int(row["LOW_DUR_PER"] or 0)
    stored = [float(row[c]) if row[c] is not None else None
              for c in ("LOW_DUR_NSP_AMT", "LOW_DUR_1_NSP_AMT", "LOW_DUR_2_NSP_AMT")]
    out = {"table": table or "(blank)", "error": "", "d1": None, "d2": None,
           "fixed": False, "propagated": False, "step2_only": False}
    if None in stored or not table:
        out["error"] = "missing stored NSP or table"
        return out
    try:
        step1 = roll_step(stored[0], table, interest, issue_age, low, function_code)
        step2 = roll_step(stored[1], table, interest, issue_age, low + 1, function_code)
    except NSPError as exc:
        out["error"] = str(exc)
        return out
    d1, d2 = step1.value - stored[1], step2.value - stored[2]
    fixed1, fixed2 = abs(d1) <= FIXED_TOLERANCE_1, abs(d2) <= FIXED_TOLERANCE_2
    prop1 = abs(d1) <= rounding_tolerance(step1, True)
    prop2 = abs(d2) <= rounding_tolerance(step2, False)
    out.update(d1=d1, d2=d2, fixed=fixed1 and fixed2, propagated=prop1 and prop2,
               step2_only=prop2 and not prop1)
    return out


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--region", choices=sorted(REGION_DSN_MAP), default="CKPR")
    parser.add_argument("--company", default="01")
    parser.add_argument("--misses", type=int, default=15, help="list this many misses")
    parser.add_argument("--csv", type=Path, help="write one row per coverage")
    args = parser.parse_args()
    if os.environ.get("SUITEVIEW_LOCAL_DATA") == "1":
        raise RuntimeError("This helper reads live DB2 policy data only.")
    rows, riders = _fetch(args.region, args.company)
    by_table = defaultdict(Counter)
    misses, facts = [], Counter()
    policies = set()
    records = []
    for row in rows:
        result = check_row(row)
        tally = by_table[result["table"]]
        tally["coverages"] += 1
        tally["fixed"] += result["fixed"]
        tally["propagated"] += result["propagated"]
        tally["step2_only"] += result["step2_only"]
        tally["errors"] += bool(result["error"])
        if not result["propagated"]:
            misses.append((row, result))
        policies.add(row["CK_POLICY_NBR"])
        facts[f"VPU {float(row['COV_VPU_AMT'] or 0):,.2f}"] += 1
        facts[f"coverage phase {row['COV_PHA_NBR']}"] += 1
        facts[f"coverages on policy: {row['COVERAGES']}"] += 1
        facts[f"RPU_BNF_CD {row['RPU_BNF_CD'] or '(blank)'}"] += 1
        facts[f"MTL_FUN_CD {row['MTL_FUN_CD'] or '(blank)'} on table {row['NSP_RPU_TBL_CD'] or '(blank)'}"] += 1
        current_loan = float(row["TRAD_LOAN"] or 0) > 0
        if float(row["TRAD_LOAN"] or 0) > 0:
            facts["traditional loan (LH_CSH_VAL_LOAN current) > 0"] += 1
        if row["FUND_LOAN_DATE"] is not None:
            facts["UL loan rows (LH_FND_VAL_LOAN) on record"] += 1
            last_av = _date(row["LAST_AV_DATE"])
            if last_av is None or _date(row["FUND_LOAN_DATE"]) > last_av:
                facts["UL loan rows dated after the last account value (LH_POL_MVRY_VAL)"] += 1
                current_loan = True
        if current_loan:
            facts["current loan: the workspace refuses Run Values"] += 1
        issue, anniversary = _date(row["ISSUE_DT"]), _date(row["LST_ANV_DT"])
        if issue and anniversary and row["LOW_DUR_PER"] is not None:
            facts[f"LOW_DUR_PER - duration at LST_ANV_DT = {int(row['LOW_DUR_PER']) - _years(issue, anniversary)}"] += 1
        records.append({**{k: row[k] for k in ("CK_POLICY_NBR", "COV_PHA_NBR", "PLN_DES_SER_CD", "INS_ISS_AGE",
                                               "NSP_RPU_TBL_CD", "MTL_FUN_CD", "NSP_ITS_RT", "LOW_DUR_PER",
                                               "LOW_DUR_NSP_AMT", "LOW_DUR_1_NSP_AMT", "LOW_DUR_2_NSP_AMT")},
                        "d1": result["d1"], "d2": result["d2"], "fixed": result["fixed"],
                        "propagated": result["propagated"], "error": result["error"]})
    total = Counter()
    print(f"ISWL RPU coverages, company {args.company} {args.region}: {len(rows)} coverages on "
          f"{len(policies)} policies")
    print(f"{'Table':6} {'Coverages':>9} {'Fixed tol':>10} {'Propagated':>11} {'Step 2 only':>12} {'Errors':>7}")
    for table in sorted(by_table):
        t = by_table[table]
        total.update(t)
        print(f"{table:6} {t['coverages']:>9} {t['fixed']:>10} {t['propagated']:>11} {t['step2_only']:>12} "
              f"{t['errors']:>7}")
    print(f"{'Total':6} {total['coverages']:>9} {total['fixed']:>10} {total['propagated']:>11} "
          f"{total['step2_only']:>12} {total['errors']:>7}")
    print("\nPopulation facts:")
    for key in sorted(facts):
        print(f"  {key}: {facts[key]}")
    print("\nOther coverage phases on these policies (product line, cease reason, stored NSP, stored CV, "
          "not matured: count):")
    for rider in riders:
        print(f"  line {rider['PRD_LIN_TYP_CD'] or '(blank)'} cease {rider['CEA_REA_CD'] or '(blank)'} "
              f"NSP {rider['HAS_NSP']} CV {rider['HAS_CV']} not matured {rider['NOT_MATURED']}: {rider['N']}")
    if misses and args.misses:
        print(f"\nFirst {min(args.misses, len(misses))} of {len(misses)} misses (propagated tolerance):")
        for row, result in misses[: args.misses]:
            d1 = "n/a" if result["d1"] is None else f"{result['d1']:+.4f}"
            d2 = "n/a" if result["d2"] is None else f"{result['d2']:+.6f}"
            print(f"  {row['CK_POLICY_NBR']} ph {row['COV_PHA_NBR']} {row['PLN_DES_SER_CD']} {row['NSP_RPU_TBL_CD']} "
                  f"{row['NSP_ITS_RT']}% age {row['INS_ISS_AGE']} low {row['LOW_DUR_PER']} stored "
                  f"{row['LOW_DUR_NSP_AMT']}, {row['LOW_DUR_1_NSP_AMT']}, {row['LOW_DUR_2_NSP_AMT']} "
                  f"step1 {d1} step2 {d2} {result['error']}")
    if args.csv:
        args.csv.parent.mkdir(parents=True, exist_ok=True)
        with args.csv.open("w", newline="", encoding="utf-8-sig") as fh:
            writer = csv.DictWriter(fh, fieldnames=list(records[0]) if records else ["CK_POLICY_NBR"])
            writer.writeheader()
            writer.writerows(records)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
