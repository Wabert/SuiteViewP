"""Pick a representative sample of in-force indeterminate premium term policies (read-only).

Indeterminate premium term = a traditional policy with ``LH_BAS_POL.IDT_PRM_IND = '1'``
whose base plancode is a TERM family plan in UL_Rates schema ``rates`` with PREM loaded.
For the most common plancodes it draws policies in each category that matters for
illustration: in the level period, in the ART (annual renewable) period, one-year-level
plans, riders (children's term and other term riders), premium waiver and other
benefits with premiums, table ratings, flat extras, waiver of premium status, company
26 and every billing mode.

Usage:
    venv\\Scripts\\python.exe tools\\rerun\\find_term_policies.py --plancodes 8 --per-category 2 --output sample.txt
"""
from __future__ import annotations

import argparse
import os
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from suiteview.core.db2_connection import DB2Connection  # noqa: E402
from suiteview.core.db2_constants import DEFAULT_SCHEMA, REGION_SCHEMA_MAP  # noqa: E402
from suiteview.core.rates_schema import RatesSchemaRepository  # noqa: E402

_RIDER = ("EXISTS (SELECT 1 FROM {s}.LH_COV_PHA R WHERE R.CK_SYS_CD = POL.CK_SYS_CD "
          "AND R.CK_CMP_CD = POL.CK_CMP_CD AND R.TCH_POL_ID = POL.TCH_POL_ID AND R.COV_PHA_NBR > 1 "
          "AND R.COV_MT_EXP_DT > CURRENT DATE{extra})")
_BENEFIT = ("EXISTS (SELECT 1 FROM {s}.LH_SPM_BNF B WHERE B.CK_SYS_CD = POL.CK_SYS_CD "
            "AND B.CK_CMP_CD = POL.CK_CMP_CD AND B.TCH_POL_ID = POL.TCH_POL_ID "
            "AND B.BNF_CEA_DT > CURRENT DATE AND B.BNF_ANN_PPU_AMT > 0{extra})")
_EXTRA = ("EXISTS (SELECT 1 FROM {s}.LH_SST_XTR_CRG X WHERE X.CK_SYS_CD = POL.CK_SYS_CD "
          "AND X.CK_CMP_CD = POL.CK_CMP_CD AND X.TCH_POL_ID = POL.TCH_POL_ID AND X.SST_XTR_TYP_CD = '{code}')")

CATEGORIES = {
    "level period": "POL.PRM_PAY_STA_REA_CD = '22' AND COV.PAY_UP_DT > CURRENT DATE + 1 YEAR",
    "level period ending": "POL.PRM_PAY_STA_REA_CD = '22' AND COV.PAY_UP_DT BETWEEN CURRENT DATE AND CURRENT DATE + 1 YEAR",
    "ART period": "POL.PRM_PAY_STA_REA_CD = '22' AND COV.PAY_UP_DT <= CURRENT DATE",
    "children's term rider": _RIDER.replace("{extra}", " AND SUBSTR(R.PLN_DES_SER_CD, 3, 3) IN ('582', '5RG', '5RF')"),
    "other term rider": _RIDER.replace("{extra}", " AND SUBSTR(R.PLN_DES_SER_CD, 3, 3) NOT IN ('582', '5RG', '5RF')"),
    "premium waiver": _BENEFIT.replace("{extra}", " AND B.SPM_BNF_TYP_CD = '3'"),
    "other benefit": _BENEFIT.replace("{extra}", " AND B.SPM_BNF_TYP_CD NOT IN ('3', '#')"),
    "table rating": _EXTRA.replace("{code}", "1"),
    "flat extra": _EXTRA.replace("{code}", "3"),
    "substandard type 2": _EXTRA.replace("{code}", "2"),
    "substandard type 4": _EXTRA.replace("{code}", "4"),
    "waiver status": "POL.PRM_PAY_STA_REA_CD = '32'",
    "reduced paid-up / paid-up": "POL.PRM_PAY_STA_REA_CD IN ('41', '45', '46', '47')",
    "mode annual": "POL.PMT_FQY_PER = 12 AND POL.PRM_PAY_STA_REA_CD = '22'",
    "mode semiannual": "POL.PMT_FQY_PER = 6 AND POL.PRM_PAY_STA_REA_CD = '22'",
    "mode quarterly": "POL.PMT_FQY_PER = 3 AND POL.PRM_PAY_STA_REA_CD = '22'",
    "mode monthly direct": "POL.PMT_FQY_PER = 1 AND POL.BIL_FRM_CD = '0' AND POL.PRM_PAY_STA_REA_CD = '22'",
    "mode monthly PAC": "POL.PMT_FQY_PER = 1 AND POL.BIL_FRM_CD = 'G' AND POL.PRM_PAY_STA_REA_CD = '22'",
    "bill form H/F": "POL.BIL_FRM_CD IN ('H', 'F') AND POL.PRM_PAY_STA_REA_CD = '22'",
}

POPULATION_SQL = """
SELECT TRIM(COV.PLN_DES_SER_CD) AS PLANCODE, COUNT(*) AS POLICIES
FROM {s}.LH_BAS_POL POL
JOIN {s}.LH_COV_PHA COV ON COV.CK_SYS_CD = POL.CK_SYS_CD AND COV.CK_CMP_CD = POL.CK_CMP_CD
 AND COV.TCH_POL_ID = POL.TCH_POL_ID AND COV.COV_PHA_NBR = 1
WHERE POL.CK_SYS_CD = 'I' AND POL.IDT_PRM_IND = '1' AND COV.PRD_LIN_TYP_CD = 'N'
  AND POL.PRM_PAY_STA_REA_CD IN ('22', '32', '41', '45', '46', '47')
GROUP BY TRIM(COV.PLN_DES_SER_CD)
ORDER BY 2 DESC
FETCH FIRST 80 ROWS ONLY
"""

SAMPLE_SQL = """
SELECT POL.CK_CMP_CD, TRIM(POL.CK_POLICY_NBR)
FROM {s}.LH_BAS_POL POL
JOIN {s}.LH_COV_PHA COV ON COV.CK_SYS_CD = POL.CK_SYS_CD AND COV.CK_CMP_CD = POL.CK_CMP_CD
 AND COV.TCH_POL_ID = POL.TCH_POL_ID AND COV.COV_PHA_NBR = 1
WHERE POL.CK_SYS_CD = 'I' AND POL.IDT_PRM_IND = '1'
  AND POL.PRM_PAY_STA_REA_CD IN ('22', '32', '41', '45', '46', '47')
  AND TRIM(COV.PLN_DES_SER_CD) = '{plancode}'
  AND ({cond})
ORDER BY MOD(INTEGER(RIGHT(TRIM(POL.CK_POLICY_NBR), 3)), 97), POL.TCH_POL_ID
FETCH FIRST {n} ROWS ONLY
"""


def loaded_plancodes(candidates) -> dict:
    """TERM family plancodes whose PREM has both the current (C) and guaranteed (G) scale."""
    loaded = {}
    with RatesSchemaRepository() as repo:
        for plancode in candidates:
            defs = [d for d in repo.plan_defs(plancode) if str(d.product_family).startswith("TERM")]
            if not defs:
                continue
            prem = [a for a in repo.cell_assignments(defs[0].company, plancode) if a.rate_type == "PREM" and not a.benefit]
            if not prem:
                continue
            scales = {w.scale for w in repo.schedule_windows([prem[0].schedule_id])}
            if {"C", "G"} <= scales:
                loaded[plancode] = defs[0].company
    return loaded


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--region", default="CKPR")
    parser.add_argument("--plancodes", type=int, default=8)
    parser.add_argument("--per-category", type=int, default=1)
    parser.add_argument("--category", action="append", help="limit to these categories")
    parser.add_argument("--plancode", action="append", help="limit to these plancodes")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    if os.environ.get("SUITEVIEW_LOCAL_DATA") == "1":
        raise RuntimeError("This helper reads live DB2 policy data only.")
    schema = REGION_SCHEMA_MAP.get(args.region, DEFAULT_SCHEMA)
    categories = {k: v for k, v in CATEGORIES.items() if not args.category or k in args.category}
    db = DB2Connection(args.region)
    picked: dict = {}
    try:
        cursor = db.connect().cursor()
        cursor.execute(POPULATION_SQL.format(s=schema))
        population = [(r[0], int(r[1])) for r in cursor.fetchall()]
        if args.plancode:
            population = [(p, n) for p, n in population if p in args.plancode]
        loaded = loaded_plancodes([p for p, _ in population])
        chosen = [(p, n) for p, n in population if p in loaded][: args.plancodes]
        print("plancodes:", ", ".join(f"{p} ({n})" for p, n in chosen))
        for plancode, _count in chosen:
            if not re.fullmatch(r"[A-Z0-9]{8}", plancode):
                raise ValueError(f"Unexpected plancode {plancode!r}")
            for label, cond in categories.items():
                sql = SAMPLE_SQL.format(s=schema, cond=cond.format(s=schema), n=int(args.per_category),
                                        plancode=plancode)
                cursor.execute(sql)
                for company, number in cursor.fetchall():
                    key = f"{company.strip()}:{number}"
                    picked.setdefault(key, []).append(f"{plancode} {label}")
        cursor.close()
    finally:
        db.close()
    lines = [f"{key}  # {'; '.join(labels)}" for key, labels in picked.items()]
    for line in lines:
        print(line)
    if args.output:
        args.output.write_text("\n".join(k for k in picked) + "\n", encoding="utf-8")
        args.output.with_suffix(".labels.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
