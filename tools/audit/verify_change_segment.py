"""Read-only live schema and generated-SQL verification for segment 68."""

import argparse
import json
import os
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--region", default="CKPR")
    parser.add_argument("--describe-only", action="store_true")
    parser.add_argument("--sample", action="store_true", help="Also execute each query with Max Count 1.")
    args = parser.parse_args()
    if os.environ.get("SUITEVIEW_LOCAL_DATA") == "1":
        raise RuntimeError("Live verification must not use local policy data")

    from suiteview.core.db2_connection import DB2Connection
    from suiteview.core.db2_constants import DEFAULT_SCHEMA, REGION_SCHEMA_MAP

    schema = REGION_SCHEMA_MAP.get(args.region, DEFAULT_SCHEMA)
    db = DB2Connection(args.region)
    report = {"region": args.region, "columns": {}}
    try:
        for table in (
            "LH_COV_TMN", "LH_NT_COV_CHG", "LH_NT_COV_CHG_SCH", "LH_SPM_BNF_CHG_SCH",
        ):
            columns, rows = db.execute_query_with_headers(
                f"SELECT * FROM {schema}.{table} WHERE 1 = 0",
            )
            assert not rows
            report["columns"][table] = columns
        if not args.describe_only:
            from PyQt6.QtWidgets import QApplication
            from suiteview.audit.cyberlife_query import build_cyberlife_sql
            from suiteview.audit.tabs.adv_tab import AdvTab
            from suiteview.audit.tabs.benefits_tab import BenefitsTab
            from suiteview.audit.tabs.coverages_tab import CoveragesTab
            from suiteview.audit.tabs.display_tab import DisplayTab
            from suiteview.audit.tabs.plancode_tab import PlancodeTab
            from suiteview.audit.tabs.policy2_tab import Policy2Tab
            from suiteview.audit.tabs.policy_tab import PolicyTab
            from suiteview.audit.tabs.transaction_tab import TransactionTab

            app = QApplication.instance() or QApplication([])
            policy2 = Policy2Tab()
            policy2.chk_change_seq.setChecked(True)
            report["queries"] = {}
            for codes in (("4",), ("9",), ("4", "9")):
                for i in range(policy2.list_change_seq.count()):
                    item = policy2.list_change_seq.item(i)
                    item.setSelected(item.text().split(" - ", 1)[0] in codes)
                sql = build_cyberlife_sql(
                    schema, "I", "1", policy_tab=PolicyTab(), display_tab=DisplayTab(),
                    policy2_tab=policy2, adv_tab=AdvTab(), coverages_tab=CoveragesTab(),
                    plancode_tab=PlancodeTab(), benefits_tab=BenefitsTab(),
                    transaction_tab=TransactionTab(),
                )
                assert "\nWHERE " in sql
                columns, rows = db.execute_query_with_headers(
                    sql.replace("\nWHERE ", "\nWHERE 1 = 0 AND ", 1),
                )
                assert not rows
                result = {"generated_sql_compiles": True, "result_columns": columns}
                if args.sample:
                    _, rows = db.execute_query_with_headers(sql)
                    assert len(rows) <= 1
                    result["sample_row_count"] = len(rows)
                report["queries"][",".join(codes)] = result
    finally:
        db.close()
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
