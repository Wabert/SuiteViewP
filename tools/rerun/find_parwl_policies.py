"""Pick a representative sample of in-force par WL policies for verification (read-only).

Par WL = a traditional policy (NON_TRD_POL_IND blank/0) whose base coverage's plancode
is PAR_WL in UL_Rates schema ``rates`` PLAN_DEF and whose base coverage participates
(DIV_PTP_TYP_CD not blank/0). For each of the most common plancodes with loaded rates
it draws policies in each category that matters for illustration: every dividend
option, reduced paid-up, waiver, paid-up, loans in advance and in arrears, PUA riders,
term riders, supplemental benefits and every billing mode.

Usage:
    venv\\Scripts\\python.exe tools\\rerun\\find_parwl_policies.py --plancodes 12 --per-category 2 --output sample.txt
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

CATEGORIES = {
    "option 4 PUA": "POL.PRI_DIV_OPT_CD = '4' AND POL.PRM_PAY_STA_REA_CD = '22'",
    "option 3 deposit": "POL.PRI_DIV_OPT_CD = '3' AND POL.PRM_PAY_STA_REA_CD = '22'",
    "option 1 cash": "POL.PRI_DIV_OPT_CD = '1' AND POL.PRM_PAY_STA_REA_CD = '22'",
    "option 2 reduce premium": "POL.PRI_DIV_OPT_CD = '2' AND POL.PRM_PAY_STA_REA_CD = '22'",
    "option 8 loan reduction": "POL.PRI_DIV_OPT_CD = '8'",
    "option OYT": "POL.PRI_DIV_OPT_CD IN ('5', '6', '7')",
    "reduced paid-up": "POL.PRM_PAY_STA_REA_CD = '45'",
    "waiver": "POL.PRM_PAY_STA_REA_CD = '32'",
    "paid-up": "POL.PRM_PAY_STA_REA_CD IN ('41', '46', '47')",
    "loan in advance": ("EXISTS (SELECT 1 FROM {s}.LH_CSH_VAL_LOAN L WHERE L.CK_SYS_CD = POL.CK_SYS_CD "
                        "AND L.CK_CMP_CD = POL.CK_CMP_CD AND L.TCH_POL_ID = POL.TCH_POL_ID "
                        "AND L.MVRY_DT = '9999-12-31' AND L.LN_PRI_AMT > 0 AND L.LN_ITS_PBL_TYP_CD = '1')"),
    "loan in arrears": ("EXISTS (SELECT 1 FROM {s}.LH_CSH_VAL_LOAN L WHERE L.CK_SYS_CD = POL.CK_SYS_CD "
                        "AND L.CK_CMP_CD = POL.CK_CMP_CD AND L.TCH_POL_ID = POL.TCH_POL_ID "
                        "AND L.MVRY_DT = '9999-12-31' AND L.LN_PRI_AMT > 0 AND L.LN_ITS_PBL_TYP_CD = '2')"),
    "PUA rider": ("EXISTS (SELECT 1 FROM {s}.LH_COV_PHA R WHERE R.CK_SYS_CD = POL.CK_SYS_CD "
                  "AND R.CK_CMP_CD = POL.CK_CMP_CD AND R.TCH_POL_ID = POL.TCH_POL_ID "
                  "AND R.COV_PHA_NBR > 1 AND R.PRD_LIN_TYP_CD = 'C')"),
    "term rider": ("EXISTS (SELECT 1 FROM {s}.LH_COV_PHA R WHERE R.CK_SYS_CD = POL.CK_SYS_CD "
                   "AND R.CK_CMP_CD = POL.CK_CMP_CD AND R.TCH_POL_ID = POL.TCH_POL_ID "
                   "AND R.COV_PHA_NBR > 1 AND R.PRD_LIN_TYP_CD IN ('0', 'N') AND R.COV_MT_EXP_DT > CURRENT DATE)"),
    "benefit": ("POL.PRM_PAY_STA_REA_CD = '22' AND EXISTS (SELECT 1 FROM {s}.LH_SPM_BNF B "
                "WHERE B.CK_SYS_CD = POL.CK_SYS_CD AND B.CK_CMP_CD = POL.CK_CMP_CD "
                "AND B.TCH_POL_ID = POL.TCH_POL_ID AND B.BNF_CEA_DT > CURRENT DATE AND B.BNF_ANN_PPU_AMT > 0)"),
    "mode annual": "POL.PMT_FQY_PER = 12 AND POL.PRM_PAY_STA_REA_CD = '22'",
    "mode semiannual": "POL.PMT_FQY_PER = 6 AND POL.PRM_PAY_STA_REA_CD = '22'",
    "mode quarterly": "POL.PMT_FQY_PER = 3 AND POL.PRM_PAY_STA_REA_CD = '22'",
    "mode monthly": "POL.PMT_FQY_PER = 1 AND POL.PRM_PAY_STA_REA_CD = '22'",
}

POPULATION_SQL = """
SELECT TRIM(COV.PLN_DES_SER_CD) AS PLANCODE, COUNT(*) AS POLICIES
FROM {s}.LH_BAS_POL POL
JOIN {s}.LH_COV_PHA COV ON COV.CK_SYS_CD = POL.CK_SYS_CD AND COV.CK_CMP_CD = POL.CK_CMP_CD
 AND COV.TCH_POL_ID = POL.TCH_POL_ID AND COV.COV_PHA_NBR = 1
WHERE POL.CK_SYS_CD = 'I' AND COALESCE(TRIM(POL.NON_TRD_POL_IND), '') IN ('', '0')
  AND POL.PRM_PAY_STA_REA_CD IN ('22', '32', '41', '45', '46', '47')
  AND COALESCE(TRIM(COV.DIV_PTP_TYP_CD), '') NOT IN ('', '0')
GROUP BY TRIM(COV.PLN_DES_SER_CD)
ORDER BY 2 DESC
FETCH FIRST 80 ROWS ONLY
"""

SAMPLE_SQL = """
SELECT POL.CK_CMP_CD, TRIM(POL.CK_POLICY_NBR)
FROM {s}.LH_BAS_POL POL
JOIN {s}.LH_COV_PHA COV ON COV.CK_SYS_CD = POL.CK_SYS_CD AND COV.CK_CMP_CD = POL.CK_CMP_CD
 AND COV.TCH_POL_ID = POL.TCH_POL_ID AND COV.COV_PHA_NBR = 1
WHERE POL.CK_SYS_CD = 'I' AND COALESCE(TRIM(POL.NON_TRD_POL_IND), '') IN ('', '0')
  AND POL.PRM_PAY_STA_REA_CD IN ('22', '32', '41', '45', '46', '47')
  AND TRIM(COV.PLN_DES_SER_CD) = '{plancode}'
  AND NOT EXISTS (SELECT 1 FROM {s}.LH_COV_PHA BL WHERE BL.CK_SYS_CD = POL.CK_SYS_CD
      AND BL.CK_CMP_CD = POL.CK_CMP_CD AND BL.TCH_POL_ID = POL.TCH_POL_ID AND BL.PRD_LIN_TYP_CD = 'B')
  AND ({cond})
ORDER BY MOD(INTEGER(RIGHT(TRIM(POL.CK_POLICY_NBR), 3)), 97), POL.TCH_POL_ID
FETCH FIRST {n} ROWS ONLY
"""


def loaded_plancodes(candidates) -> dict:
    loaded = {}
    with RatesSchemaRepository() as repo:
        for plancode in candidates:
            defs = [d for d in repo.plan_defs(plancode) if d.product_family == "PAR_WL"]
            if not defs:
                continue
            cells = {a.rate_type for a in repo.cell_assignments(defs[0].company, plancode)}
            divs = repo.div_assignments(defs[0].company, plancode)
            if "CV" in cells and divs:
                loaded[plancode] = defs[0].company
    return loaded


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--region", default="CKPR")
    parser.add_argument("--plancodes", type=int, default=12)
    parser.add_argument("--per-category", type=int, default=1)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    if os.environ.get("SUITEVIEW_LOCAL_DATA") == "1":
        raise RuntimeError("This helper reads live DB2 policy data only.")
    schema = REGION_SCHEMA_MAP.get(args.region, DEFAULT_SCHEMA)
    db = DB2Connection(args.region)
    picked: dict = {}
    try:
        cursor = db.connect().cursor()
        cursor.execute(POPULATION_SQL.format(s=schema))
        population = [(r[0], int(r[1])) for r in cursor.fetchall()]
        loaded = loaded_plancodes([p for p, _ in population])
        chosen = [(p, n) for p, n in population if p in loaded][: args.plancodes]
        print("plancodes:", ", ".join(f"{p} ({n})" for p, n in chosen))
        for plancode, _count in chosen:
            if not re.fullmatch(r"[A-Z0-9]{8}", plancode):
                raise ValueError(f"Unexpected plancode {plancode!r}")
            for label, cond in CATEGORIES.items():
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
