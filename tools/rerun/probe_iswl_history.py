"""Dump the raw monthly history of a live ISWL (or any advanced) policy, read-only.

Usage: venv\\Scripts\\python.exe tools\\rerun\\probe_iswl_history.py <policy> [company|-] [months] [--brief]

Prints the coverage/benefit/billing basics, every ``LH_POL_MVRY_VAL`` row in the
last ``months`` (default 8) months and the ``FH_FIXED`` transactions in the same
window, so the monthly AV roll-forward mechanics can be read off real records.
``--brief`` keeps only the columns the roll-forward uses.
"""

import calendar
import json
import sys
from datetime import date, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from suiteview.core.local_dev import local_data_enabled
from suiteview.polview.services.policy_service import get_policy_info


def _as_date(value):
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    text = str(value or "").strip()[:10]
    try:
        return date.fromisoformat(text)
    except ValueError:
        return None


def _months_before(when: date, months: int) -> date:
    year, month = divmod(when.year * 12 + when.month - 1 - months, 12)
    month += 1
    return date(year, month, min(when.day, calendar.monthrange(year, month)[1]))


def _clean(row: dict) -> dict:
    out = {}
    for key, value in row.items():
        if value is None or (isinstance(value, str) and not value.strip()):
            continue
        out[key] = value if isinstance(value, (int, float, str)) else str(value)
    return out


def _rows(pi, table):
    rows = pi.fetch_table(table)
    error = pi.table_error(table)
    if error:
        print(json.dumps({"table": table, "error": str(error)}))
        return []
    return rows


_BRIEF_COLUMNS = {
    "LH_COV_PHA": ("COV_PHA_NBR", "PLN_DES_SER_CD", "COV_UNT_QTY", "ANN_PRM_UNT_AMT", "INS_ISS_AGE",
                   "INS_SEX_CD", "INS_CLS_CD", "COV_VPU_AMT", "ISSUE_DT", "PLN_TMN_DT", "PRM_PAY_STA_REA_CD"),
    "LH_SPM_BNF": ("COV_PHA_NBR", "SPM_BNF_TYP_CD", "SPM_BNF_SBY_CD", "BNF_UNT_QTY", "BNF_ANN_PPU_AMT",
                   "BNF_ISS_AGE", "BNF_CEA_DT", "BNF_RT_FCT"),
    "LH_BAS_POL": ("POL_PRM_AMT", "PMT_FQY_PER", "BIL_FRM_CD", "PRM_PAY_ST_CD", "PRM_PAID_TO_DT",
                   "POL_ISS_DT"),
    "LH_NON_TRD_POL": ("PRM_LD_TBL_CD", "PRM_LD_RLE_1_CD", "POL_GUA_ITS_RT", "CINS_RT_CLC_RLE_CD",
                       "PRM_REC_ITS_RLE_CD", "CSV_XPN_FQY_CD", "DTH_BNF_PLN_OPT_CD"),
    "LH_POL_MVRY_VAL": ("MVRY_DT", "POL_DUR_NBR", "CSV_AMT", "CINS_AMT", "EXP_CRG_AMT", "OTH_PRM_AMT",
                        "NAR_AMT", "TOT_CRE_ITS_AMT", "GUA_RT_ERN_ITS_AMT"),
    "FH_FIXED": ("SEQ_NO", "ASOF_DT", "TRANS", "GROSS_AMT", "NET_AMT", "CHARGE_AMT", "INT_RT",
                 "FCB0_REV_IND", "FBB3_PROCD_IND"),
}


def _emit(table: str, row: dict, brief: bool) -> None:
    data = _clean(row)
    if brief:
        data = {k: data[k] for k in _BRIEF_COLUMNS.get(table, ()) if k in data}
    print(json.dumps({"table": table, **data}, default=str))


def main() -> None:
    if local_data_enabled():
        raise RuntimeError("This helper reads live DB2 policy data only.")
    args = [a for a in sys.argv[1:] if a != "--brief"]
    brief = "--brief" in sys.argv
    policy = args[0]
    company = args[1] if len(args) > 1 and args[1] != "-" else None
    months = int(args[2]) if len(args) > 2 else 8
    pi = get_policy_info(policy, company_code=company, use_cache=False)
    if pi is None or not pi.exists:
        raise SystemExit(f"Policy {policy} not found or live access failed.")
    print(json.dumps({
        "policy": pi.policy_number, "company": pi.company_code,
        "product_type": pi.product.product_type,
    }))
    detail_tables = ("LH_COV_PHA", "LH_SPM_BNF", "LH_BAS_POL", "LH_NON_TRD_POL")
    if not brief:
        detail_tables += ("LH_POL_TOTALS", "LH_COV_INS_RNL_RT", "LH_POL_FND_VAL_TOT", "LH_FND_VAL_LOAN")
    for table in detail_tables:
        for row in _rows(pi, table):
            _emit(table, row, brief)
    mv_rows = _rows(pi, "LH_POL_MVRY_VAL")
    dates = [d for d in (_as_date(r.get("MVRY_DT")) for r in mv_rows) if d]
    if not dates:
        return
    earliest = _months_before(max(dates), months)
    for row in sorted(mv_rows, key=lambda r: _as_date(r.get("MVRY_DT")) or date.min):
        when = _as_date(row.get("MVRY_DT"))
        if when and when >= earliest:
            _emit("LH_POL_MVRY_VAL", row, brief)
    for row in sorted(_rows(pi, "FH_FIXED"), key=lambda r: (_as_date(r.get("ASOF_DT")) or date.min,
                                                            str(r.get("SEQ_NO")))):
        when = _as_date(row.get("ASOF_DT"))
        if when and when >= earliest:
            _emit("FH_FIXED", row, brief)


if __name__ == "__main__":
    main()
