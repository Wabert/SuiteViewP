"""Compare live Other Queries aggregates read-only; print no policy identifiers."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from suiteview.audit.other_queries import build_other_query, execute_other_query, OtherQuery
from suiteview.core.local_dev import local_data_enabled


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--plancode", required=True)
    parser.add_argument("--kind", choices=("riders", "bases"), default="riders")
    parser.add_argument("--region", default="CKPR")
    args = parser.parse_args()
    if local_data_enabled():
        raise RuntimeError("This verification requires live DB2, not local policy data.")
    query = build_other_query(args.kind, args.region, plancode=args.plancode)
    results = {"actual": execute_other_query(query, args.region).to_dict(orient="records")}
    for name, aggregate in (
        ("plancode_count", "COUNT(R.PLN_DES_SER_CD)"),
        ("row_count", "COUNT(*)"),
        ("policy_key_count", "COUNT(R.TCH_POL_ID)"),
        ("policy_record_sum", "SUM(CASE WHEN R.TCH_POL_ID IS NOT NULL THEN 1 ELSE 0 END)"),
        ("row_sum", "SUM(1)"),
    ):
        variant = OtherQuery(
            query.sql.replace("COUNT(*)", aggregate), query.params, query.columns,
        )
        results[name] = execute_other_query(variant, args.region).to_dict(orient="records")
    detailed = execute_other_query(build_other_query(
        args.kind, args.region, plancode=args.plancode, show_policies=True,
    ), args.region)
    keys = list(query.columns[:4])
    results["detail_row_count"] = (
        detailed.groupby(keys, dropna=False).size().reset_index(name="Rider Count")
        .to_dict(orient="records")
    )
    all_ok = (
        bool(results["actual"])
        and results["actual"] == results["row_count"] == results["row_sum"]
        == results["policy_record_sum"]
        == results["detail_row_count"]
    )
    print(json.dumps({
        "all_ok": all_ok, "region": args.region, "plancode": args.plancode,
        "matches_actual": {name: rows == results["actual"] for name, rows in results.items()},
        "actual": results["actual"],
    }, indent=2))
    return 0 if all_ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
