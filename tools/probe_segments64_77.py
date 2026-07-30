r"""Probe the live DB2 rows behind Policy Record segments 64 and 77.

This diagnostic intentionally goes through ``policy_service.get_policy_info``
and ``PolicyInformation.fetch_table``.  It refuses to run when local-data mode
is enabled, so a successful result is auditable live-DB2 evidence.

Usage:
    venv\Scripts\python.exe tools\probe_segments64_77.py U0633187 CKPR
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from suiteview.core.local_dev import local_data_enabled
from suiteview.core.policy_service import clear_cache, get_policy_info


_FIELDS = {
    "LH_POL_CAL_YR_TOT": (
        "CK_SYS_CD", "CK_CMP_CD", "TCH_POL_ID",
        "CAL_YR_END_DT", "YR_END_ACT_BAL_IND", "RMD_NOT_IND",
        "RMD_REMINDER_IND", "RMD_CLC_IND", "RMD_DEFERRED_IND",
        "UNLOANED_CSV_AMT", "LOANED_CSV_AMT", "RQR_MIN_DTB_AMT",
        "REG_MIN_DTB_AMT", "CAL_YR_REG_PRM_AMT", "CAL_YR_ADD_PRM_AMT",
        "CAL_YR_NET_WTD_AMT", "CAL_YR_WTD_CRG_AMT", "INT_LIFE_FCT",
        "CAL_YR_NRG_PRM_AMT", "PV_ADDL_BENS",
    ),
    "LH_CSH_VAL_LOAN": (
        "CK_SYS_CD", "CK_CMP_CD", "TCH_POL_ID", "MVRY_DT",
        "GUA_VAL_IND", "LN_ITS_PBL_TYP_CD", "LN_ITS_PAY_TO_DT",
        "LN_CRG_ITS_RT", "LN_PRI_AMT", "LN_ITS_AMT_TYP_CD",
        "POL_LN_ITS_AMT", "LST_LN_ACY_TYP_CD", "LST_LN_ACY_DT",
        "LST_LN_DT", "CUL_LN_ITS_AMT", "TOT_CPZ_LN_ITS_AMT",
        "LN_LIEN_IND", "LN_CNV_IND", "NFO_CNV_IND", "PRF_LN_IND",
        "LN_ITS_OVR_IND", "TOT_CPZ_AMT_IND",
    ),
    "LH_FND_VAL_LOAN": (
        "CK_SYS_CD", "CK_CMP_CD", "TCH_POL_ID", "MVRY_DT",
        "COV_PHA_NBR", "FND_ID_CD", "FND_VAL_PHA_NBR",
        "LN_ITS_PBL_TYP_CD", "LN_ITS_PAY_TO_DT", "LN_CRG_ITS_RT",
        "LN_PRI_AMT", "LN_ITS_AMT_TYP_CD", "POL_LN_ITS_AMT",
        "LST_LN_ACY_TYP_CD", "LST_LN_ACY_DT", "LST_LN_DT",
        "CUL_LN_ITS_AMT", "TOT_CPZ_LN_ITS_AMT", "LN_LIEN_IND",
        "LN_CNV_IND", "NFO_CNV_IND", "PRF_LN_IND", "LN_ITS_OVR_IND",
        "TOT_CPZ_AMT_IND",
    ),
}


def _jsonable(value):
    if value is None or isinstance(value, (bool, int, float, str)):
        return value
    return str(value)


def _table_evidence(pi, table: str) -> dict:
    rows = pi.fetch_table(table)
    wanted = _FIELDS[table]
    available = sorted({key for row in rows for key in row})
    if not available:
        cache = getattr(getattr(pi, "_data", None), "_table_cache", {})
        available = sorted(cache.get(table, {}).get("columns", []))
    return {
        "count": len(rows),
        "policy_data_order": {
            "LH_POL_CAL_YR_TOT": "none",
            "LH_CSH_VAL_LOAN": "MVRY_DT DESC",
            "LH_FND_VAL_LOAN": "MVRY_DT DESC, FND_VAL_PHA_NBR DESC",
        }[table],
        "all_columns": available,
        "available_mapped_columns": [field for field in wanted if field in available],
        "missing_mapped_columns": [field for field in wanted if field not in available],
        "rows": [
            {
                "source_index": index,
                **{field: _jsonable(row.get(field)) for field in wanted},
            }
            for index, row in enumerate(rows)
        ],
    }


def main() -> int:
    policy = sys.argv[1] if len(sys.argv) > 1 else "U0633187"
    region = sys.argv[2] if len(sys.argv) > 2 else "CKPR"
    company = sys.argv[3] if len(sys.argv) > 3 else None

    if local_data_enabled():
        print(json.dumps({
            "ok": False,
            "error": "SUITEVIEW_LOCAL_DATA=1; refusing non-live verification",
        }, indent=2))
        return 2

    clear_cache()
    pi = get_policy_info(
        policy,
        region=region,
        company_code=company,
        use_cache=False,
    )
    if pi is None or not getattr(pi, "exists", False):
        print(json.dumps({
            "ok": False,
            "policy": policy,
            "region": region,
            "source": "live_db2",
            "found": False,
        }, indent=2))
        return 1

    result = {
        "ok": True,
        "source": "live_db2",
        "local_data_enabled": False,
        "policy": policy,
        "region": region,
        "company_code": _jsonable(getattr(pi, "company_code", None)),
        "system_code": _jsonable(getattr(pi, "system_code", None)),
        "product_type": _jsonable(getattr(pi, "product_type", None)),
        "is_advanced_product": _jsonable(
            getattr(pi, "is_advanced_product", None)
        ),
        "tables": {
            table: _table_evidence(pi, table)
            for table in _FIELDS
        },
    }
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
