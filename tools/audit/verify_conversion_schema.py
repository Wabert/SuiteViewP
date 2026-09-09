"""Read live 52/69 column metadata using zero-row queries; no policy data exported."""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from suiteview.audit.cyberlife_query import _conversion_sc_cte
from suiteview.audit.segment52_fields import SEGMENT52_FIELDS
from suiteview.core.db2_connection import DB2Connection
from suiteview.core.db2_constants import DEFAULT_SCHEMA, REGION_DSN_MAP, REGION_SCHEMA_MAP


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--region", choices=sorted(REGION_DSN_MAP), default="CKPR")
    parser.add_argument("--describe-only", action="store_true")
    args = parser.parse_args()
    if os.environ.get("SUITEVIEW_LOCAL_DATA") == "1":
        raise RuntimeError("Live schema verification requires SUITEVIEW_LOCAL_DATA disabled.")
    db = DB2Connection(args.region)
    schema = REGION_SCHEMA_MAP.get(args.region, DEFAULT_SCHEMA)
    queries = {
        "TH_USER_GENERIC": (
            f"SELECT * FROM {schema}.TH_USER_GENERIC WHERE 1 = 0"
        ),
        "FH_FIXED": (
            f"SELECT * FROM {schema}.FH_FIXED WHERE 1 = 0"
        ),
    }
    if not args.describe_only:
        queries["CONVERSION_SC"] = (
            "WITH " + _conversion_sc_cte(schema) + " SELECT * FROM CONVERSION_SC WHERE 1 = 0"
        )
    selected = {field.name for field in SEGMENT52_FIELDS} | {
        "CK_SYS_CD", "CK_CMP_CD", "TCH_POL_ID", "SEQ_NO", "ENTRY_DT", "ASOF_DT",
        "TRANS", "FCB0_REV_IND", "FCB2_REV_APPL_IND", "TYPE_SEQUENCE",
        "SEGMENT_TYPE", "SEGEMENT-TYPE",
    }
    output = {}
    try:
        connection = db.connect()
        for name, sql in queries.items():
            cursor = connection.cursor()
            try:
                cursor.execute(sql)
                metadata = [
                    {"column": item[0], "python_type": item[1].__name__,
                     "precision": item[4], "scale": item[5], "nullable": item[6]}
                    for item in cursor.description
                    if name == "CONVERSION_SC" or item[0] in selected
                    or "TIME" in item[0] or "SEQ" in item[0] or "_TM" in item[0]
                ]
                output[name] = {
                    "column_names": [item[0] for item in cursor.description],
                    "metadata": metadata,
                }
                if name == "TH_USER_GENERIC":
                    missing = {field.name for field in SEGMENT52_FIELDS} - set(
                        output[name]["column_names"])
                    if missing:
                        raise RuntimeError(f"TH_USER_GENERIC is missing: {sorted(missing)}")
            finally:
                cursor.close()
    finally:
        db.close()
    print(json.dumps({"region": args.region, "columns": output, "all_ok": True}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
