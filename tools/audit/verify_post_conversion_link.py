"""Read-only conversion-link verification; report checks, not policy identifiers."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from suiteview.core.db2_connection import DB2Connection
from suiteview.core.db2_constants import DEFAULT_SCHEMA, REGION_DSN_MAP, REGION_SCHEMA_MAP
from suiteview.core.local_dev import local_data_enabled


def verify_results(db: DB2Connection, schema: str, sources: list[tuple]) -> dict:
    from PyQt6.QtWidgets import QApplication
    from suiteview.audit.cyberlife_query import build_cyberlife_sql
    from suiteview.audit.tabs.adv_tab import AdvTab
    from suiteview.audit.tabs.benefits_tab import BenefitsTab
    from suiteview.audit.tabs.coverages_tab import CoveragesTab
    from suiteview.audit.tabs.display_tab import DisplayTab
    from suiteview.audit.tabs.plancode_tab import PlancodeTab
    from suiteview.audit.tabs.policy2_tab import Policy2Tab
    from suiteview.audit.tabs.policy_tab import PolicyTab

    app = QApplication.instance() or QApplication([])
    tabs = dict(
        policy_tab=PolicyTab(), display_tab=DisplayTab(), policy2_tab=Policy2Tab(),
        adv_tab=AdvTab(), coverages_tab=CoveragesTab(), plancode_tab=PlancodeTab(),
        benefits_tab=BenefitsTab(),
    )
    checks = {}
    try:
        for number, (system, company, policy_number, _, last_entry) in enumerate(sources):
            tabs["plancode_tab"].policies.set_values([policy_number.strip()])
            combo = tabs["policy_tab"].cmb_company
            index = next(
                index for index in range(combo.count())
                if combo.itemText(index).split(" - ")[0] == company.strip()
            )
            combo.setCurrentIndex(index)
            tabs["display_tab"].chk_post_conversion.setChecked(False)
            baseline_columns, baseline = db.execute_query_with_headers(
                build_cyberlife_sql(schema, system, "", **tabs))
            tabs["display_tab"].chk_post_conversion.setChecked(True)
            columns, rows = db.execute_query_with_headers(
                build_cyberlife_sql(schema, system, "", **tabs))
            checks[f"sample_{number}_base_rows_preserved"] = bool(baseline) and {
                tuple(row[columns.index(column)] for column in baseline_columns)
                for row in rows
            } == {tuple(row) for row in baseline}
            company_column = columns.index("POST_CONV_COMPANY")
            policy_column = columns.index("POST_CONV_POLICY")
            actual = {(row[company_column], row[policy_column]) for row in rows}
            if last_entry == "O":
                _, expected = db.execute_query_with_headers_isolated(f"""
                    SELECT DISTINCT P.CK_CMP_CD, P.CK_POLICY_NBR
                    FROM {schema}.LH_BAS_POL P
                    INNER JOIN {schema}.TH_USER_GENERIC G
                      ON P.CK_SYS_CD = G.CK_SYS_CD AND P.CK_CMP_CD = G.CK_CMP_CD
                     AND P.TCH_POL_ID = G.TCH_POL_ID
                    WHERE G.CK_SYS_CD = ? AND TRIM(G.SOURCE_CMP_CODE) = ?
                      AND TRIM(G.EXCH_POL_NUMBER) = ?""",
                    (system, company.strip(), policy_number.strip()))
                expected_pairs = {tuple(row) for row in expected} or {(None, None)}
            else:
                expected_pairs = {(None, None)}
            checks[f"sample_{number}_destinations_match"] = actual == expected_pairs
    finally:
        for widget in tabs.values():
            widget.close()
            widget.deleteLater()
        app.processEvents()
    return checks


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--region", choices=sorted(REGION_DSN_MAP), default="CKPR")
    args = parser.parse_args()
    if local_data_enabled():
        raise RuntimeError("Conversion-link verification requires live DB2.")
    db = DB2Connection(args.region)
    schema = REGION_SCHEMA_MAP.get(args.region, DEFAULT_SCHEMA)
    output = {}
    try:
        for table in ("LH_BAS_POL", "TH_BAS_POL", "TH_USER_GENERIC"):
            columns, _ = db.execute_query_with_headers(
                f"SELECT * FROM {schema}.{table} WHERE 1 = 0")
            output[f"{table}_reference_columns"] = [
                name for name in columns
                if any(part in name for part in ("CONV", "EXCH", "SOURCE", "REPLAC"))
                or name in ("CK_SYS_CD", "CK_CMP_CD", "CK_POLICY_NBR", "TCH_POL_ID")
            ]
        _, candidates = db.execute_query_with_headers(f"""
            SELECT G.CK_SYS_CD, G.CK_CMP_CD, G.TCH_POL_ID,
                   G.SOURCE_CMP_CODE, G.EXCH_POL_NUMBER
            FROM {schema}.TH_USER_GENERIC G
            WHERE G.SOURCE_CMP_CODE IS NOT NULL AND TRIM(G.SOURCE_CMP_CODE) <> ''
              AND G.EXCH_POL_NUMBER IS NOT NULL AND TRIM(G.EXCH_POL_NUMBER) <> ''
            FETCH FIRST 50 ROWS ONLY""")
        matched = []
        original_references = 0
        forward_references = 0
        for system, destination_company, destination_id, source_company, source_number in candidates:
            _, sources = db.execute_query_with_headers_isolated(f"""
                SELECT P.CK_SYS_CD, P.CK_CMP_CD, P.CK_POLICY_NBR, P.TCH_POL_ID
                FROM {schema}.LH_BAS_POL P
                WHERE P.CK_SYS_CD = ? AND P.CK_CMP_CD = ? AND P.CK_POLICY_NBR = ?
                  AND P.LST_ETR_CD = 'O'""",
                (system, source_company.strip(), source_number.strip()))
            if not sources:
                continue
            _, destinations = db.execute_query_with_headers_isolated(f"""
                SELECT P.CK_POLICY_NBR FROM {schema}.LH_BAS_POL P
                WHERE P.CK_SYS_CD = ? AND P.CK_CMP_CD = ? AND P.TCH_POL_ID = ?""",
                (system, destination_company, destination_id))
            if not destinations:
                continue
            for source in sources:
                matched.append((source, destination_company, destinations[0][0]))
                _, references = db.execute_query_with_headers_isolated(f"""
                    SELECT G.EXCH_POL_NUMBER, G.SOURCE_CMP_CODE
                    FROM {schema}.TH_USER_GENERIC G
                    WHERE G.CK_SYS_CD = ? AND G.CK_CMP_CD = ? AND G.TCH_POL_ID = ?""",
                    (source[0], source[1], source[3]))
                original_references += sum(bool(row[0] and row[0].strip()) for row in references)
                forward_references += sum(
                    bool(row[0] and row[1])
                    and row[0].strip() == destinations[0][0].strip()
                    and row[1].strip() == destination_company.strip()
                    for row in references
                )
            if len(matched) >= 5:
                break
        sources = list(dict.fromkeys(tuple(item[0]) + ("O",) for item in matched))
        _, controls = db.execute_query_with_headers(f"""
            SELECT CK_SYS_CD, CK_CMP_CD, CK_POLICY_NBR, TCH_POL_ID, LST_ETR_CD
            FROM {schema}.LH_BAS_POL WHERE LST_ETR_CD <> 'O'
            FETCH FIRST 1 ROWS ONLY""")
        sources.extend(tuple(row) for row in controls)
        checks = verify_results(db, schema, sources)
        output.update(
            sampled_destination_records=len(candidates),
            matched_terminated_conversion_links=len(matched),
            source_records_with_exchange_reference=original_references,
            source_references_pointing_forward=forward_references,
            checks=checks,
            all_ok=bool(matched) and bool(controls) and all(checks.values()),
        )
    finally:
        db.close()
    print(json.dumps(output, indent=2))
    return 0 if output["all_ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
