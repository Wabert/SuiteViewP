"""List the policies available in the local dev SQLite database.

These are the policies you can load and test the Illustration app (and other
sub-apps) against while offline. Real exported policies are flagged; the
synthetic ``DEV1000x`` fixtures are marked as such.

Enriches each policy with its base-coverage plancode / issue date / issue age
so the list is actually useful for picking a test case.

Usage:
    venv\\Scripts\\python.exe tools/list_local_test_policies.py
    venv\\Scripts\\python.exe tools/list_local_test_policies.py --json
"""
from __future__ import annotations

import argparse
import json
import sqlite3
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DB = ROOT / "bundled_data" / "dev" / "policy_records.sqlite"


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="List local dev test policies.")
    parser.add_argument("--db", default=str(DEFAULT_DB), help="SQLite policy database path")
    parser.add_argument("--json", action="store_true", help="Emit JSON instead of a table")
    return parser.parse_args()


def _table_columns(conn: sqlite3.Connection, table: str) -> set[str]:
    return {str(row[1]).upper() for row in conn.execute(f"PRAGMA table_info('{table}')")}


def _base_coverage(conn: sqlite3.Connection, tch_pol_id: str) -> dict:
    cols = _table_columns(conn, "LH_COV_PHA")
    wanted = [c for c in ("PLN_DES_SER_CD", "ISSUE_DT", "INS_ISS_AGE") if c in cols]
    if not wanted or "TCH_POL_ID" not in cols:
        return {}
    row = conn.execute(
        f"SELECT {', '.join(wanted)} FROM LH_COV_PHA "
        "WHERE TCH_POL_ID = ? AND COV_PHA_NBR = 1",
        (tch_pol_id,),
    ).fetchone()
    return dict(row) if row else {}


def _collect(conn: sqlite3.Connection) -> list[dict]:
    conn.row_factory = sqlite3.Row
    cols = _table_columns(conn, "LH_BAS_POL")
    select = [c for c in ("CK_POLICY_NBR", "CK_CMP_CD", "CK_SYS_CD", "TCH_POL_ID",
                          "NON_TRD_POL_IND", "POL_PRM_AMT") if c in cols]
    exported = set()
    if _table_columns(conn, "SUITEVIEW_LOCAL_EXPORTED_POLICIES"):
        exported = {
            str(r[0]) for r in conn.execute(
                "SELECT POLICY_NUMBER FROM SUITEVIEW_LOCAL_EXPORTED_POLICIES")
        }

    policies = []
    for row in conn.execute(
        f"SELECT {', '.join(select)} FROM LH_BAS_POL ORDER BY CK_POLICY_NBR"
    ):
        row = dict(row)
        number = str(row.get("CK_POLICY_NBR", "") or "")
        base = _base_coverage(conn, str(row.get("TCH_POL_ID", "") or ""))
        plancode = str(base.get("PLN_DES_SER_CD", "") or "").strip()
        is_advanced = str(row.get("NON_TRD_POL_IND", "") or "") == "1"
        premium = row.get("POL_PRM_AMT")
        policies.append({
            "policy_number": number,
            "company_code": str(row.get("CK_CMP_CD", "") or ""),
            "region": "CKPR" if str(row.get("CK_CMP_CD", "")) not in ("AA", "BB") else "dev",
            "plancode": plancode,
            "product_type": "Advanced (UL)" if is_advanced else "Traditional",
            "issue_date": str(base.get("ISSUE_DT", "") or ""),
            "issue_age": base.get("INS_ISS_AGE"),
            "modal_premium": f"{float(premium):,.2f}" if premium not in (None, "") else "",
            "kind": "exported" if number in exported else "synthetic",
        })
    return policies


def _print_table(policies: list[dict]) -> None:
    real = [p for p in policies if p["kind"] == "exported"]
    synthetic = [p for p in policies if p["kind"] != "exported"]

    headers = ["Policy", "Co", "Plancode", "Product", "Issue Date", "Age", "Premium"]
    keys = ["policy_number", "company_code", "plancode", "product_type",
            "issue_date", "issue_age", "modal_premium"]

    def render(rows: list[dict]) -> None:
        table = [headers] + [[str(p.get(k, "") if p.get(k) is not None else "") for k in keys] for p in rows]
        widths = [max(len(r[c]) for r in table) for c in range(len(headers))]
        for i, r in enumerate(table):
            print("  ".join(cell.ljust(widths[c]) for c, cell in enumerate(r)))
            if i == 0:
                print("  ".join("-" * widths[c] for c in range(len(headers))))

    print(f"Local policy DB: {len(policies)} policies\n")
    print(f"== Real exported policies ({len(real)}) -- use these to test ==")
    render(real)
    if synthetic:
        print(f"\n== Synthetic dev fixtures ({len(synthetic)}) ==")
        render(synthetic)


def main() -> None:
    args = _parse_args()
    db_path = Path(args.db).expanduser()
    conn = sqlite3.connect(f"file:{db_path.as_posix()}?mode=ro", uri=True)
    try:
        policies = _collect(conn)
    finally:
        conn.close()

    if args.json:
        print(json.dumps({"db": str(db_path), "policies": policies}, indent=2, default=str))
    else:
        _print_table(policies)


if __name__ == "__main__":
    main()
