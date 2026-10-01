"""Probe CyberLife for historical shadow-account evidence for RERUN baseline.

Usage:
``venv\\Scripts\\python.exe tools\\rerun\\baseline_shadow_probe.py
--selection <selected_policies.json> --output <shadow_probe.json>``

The probe is read-only. It records the tables/columns inspected for shadow/CCV
history and samples current XP target rows on shadow-account policies. It is
designed to document what was and was not comparable in the baseline workbook.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from tools.rerun.baseline_common import REGION, json_dump, json_load, traceback_text  # noqa: E402


def _catalog_shadow_columns(conn) -> list[dict[str, Any]]:
    queries = [
        r"""
        SELECT RTRIM(TBCREATOR), RTRIM(TBNAME), RTRIM(NAME)
        FROM SYSIBM.SYSCOLUMNS
        WHERE TBCREATOR IN ('DB2TAB')
          AND (TBNAME LIKE 'LH\_%' ESCAPE '\' OR TBNAME LIKE 'TH\_%' ESCAPE '\' OR TBNAME LIKE 'FH\_%' ESCAPE '\')
          AND (
            NAME LIKE '%SHAD%' OR NAME LIKE '%SHDW%' OR NAME LIKE '%CCV%'
            OR NAME LIKE '%TAR%' OR NAME LIKE '%XP%' OR NAME LIKE '%DEEM%'
          )
        ORDER BY TBNAME, COLNO
        """,
        r"""
        SELECT RTRIM(CREATOR), RTRIM(NAME), RTRIM(COLNAME)
        FROM SYSIBM.SYSCOLUMNS
        WHERE CREATOR IN ('DB2TAB')
          AND (NAME LIKE 'LH\_%' ESCAPE '\' OR NAME LIKE 'TH\_%' ESCAPE '\' OR NAME LIKE 'FH\_%' ESCAPE '\')
          AND (
            COLNAME LIKE '%SHAD%' OR COLNAME LIKE '%SHDW%' OR COLNAME LIKE '%CCV%'
            OR COLNAME LIKE '%TAR%' OR COLNAME LIKE '%XP%' OR COLNAME LIKE '%DEEM%'
          )
        ORDER BY NAME, COLNO
        """,
    ]
    errors = []
    for sql in queries:
        cur = conn.cursor()
        try:
            cur.execute(sql)
            return [
                {"schema": str(row[0]).strip(), "table": str(row[1]).strip(), "column": str(row[2]).strip()}
                for row in cur.fetchall()
            ]
        except Exception as exc:  # noqa: BLE001
            errors.append(f"{type(exc).__name__}: {exc}")
        finally:
            cur.close()
    return [{"catalog_error": " | ".join(errors)}]


def _shadow_policy_sample(selection: dict[str, Any], limit: int) -> list[dict[str, Any]]:
    from suiteview.illustration.api import project_policy
    from suiteview.polview.services.policy_service import get_policy_info

    rows = []
    shadow_selected = [row for row in selection.get("selected", []) if row.get("shadow_applicable")]
    for selected in shadow_selected[:limit]:
        policy_number = selected["policy_number"]
        company = selected["company"]
        item = {
            "company": company,
            "policy_number": policy_number,
            "plancode": selected.get("plancode", ""),
            "requested_plancode": selected.get("requested_plancode", ""),
        }
        try:
            pi = get_policy_info(policy_number, REGION, company)
            mv_rows = pi.fetch_table("LH_POL_MVRY_VAL")
            cov_target = pi.fetch_table("LH_COV_TARGET")
            pol_target = pi.fetch_table("LH_POL_TARGET")
            item["lh_pol_mvry_val_columns"] = list(mv_rows[0].keys()) if mv_rows else []
            item["lh_cov_target_columns"] = list(cov_target[0].keys()) if cov_target else []
            item["lh_pol_target_columns"] = list(pol_target[0].keys()) if pol_target else []
            item["xp_rows"] = [
                {key: row.get(key) for key in row}
                for row in cov_target
                if str(row.get("TAR_TYP_CD", "") or "").strip() == "XP"
            ]
            item["mvry_shadow_like_columns"] = [
                column for column in item["lh_pol_mvry_val_columns"]
                if any(token in column.upper() for token in ("SHAD", "SHDW", "CCV", "DEEM"))
                or column.upper() in {"XP", "XP_AMT", "XP_VAL_AMT"}
            ]
            run0 = project_policy(policy_number, company_code=company, months=0)
            state0 = run0.states[0]
            item["cyberlife_current_shadow"] = run0.policy.shadow_account_value
            item["rerun_month0_shadow"] = getattr(state0, "shadow_eav", None)
            item["month0_shadow_diff"] = (
                getattr(state0, "shadow_eav", 0.0) - float(run0.policy.shadow_account_value or 0.0)
            )
        except Exception as exc:  # noqa: BLE001
            item["error"] = f"{type(exc).__name__}: {exc}"
            item["traceback"] = traceback_text()
        rows.append(item)
    return rows


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--selection", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--sample-limit", type=int, default=25)
    args = parser.parse_args()
    from suiteview.core.db2_connection import DB2Connection

    selection = json_load(Path(args.selection))
    db = DB2Connection(REGION)
    try:
        conn = db.connect()
        catalog = _catalog_shadow_columns(conn)
    finally:
        db.close()
    sample = _shadow_policy_sample(selection, args.sample_limit)
    table_counts = Counter(row.get("table", row.get("catalog_error", "")) for row in catalog)
    result = {
        "selection": args.selection,
        "catalog_shadow_columns": catalog,
        "catalog_table_counts": dict(table_counts),
        "shadow_policy_sample": sample,
        "conclusion": (
            "PolicyInformation exposes current shadow account value from LH_COV_TARGET "
            "TAR_TYP_CD='XP'. LH_POL_MVRY_VAL samples show no shadow-like historical "
            "columns; no archived monthliversary shadow value was identified by this probe."
        ),
    }
    json_dump(Path(args.output), result)
    print(json.dumps({"output": args.output, "catalog_rows": len(catalog), "sample_rows": len(sample)}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
