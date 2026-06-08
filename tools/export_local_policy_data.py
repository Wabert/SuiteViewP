from __future__ import annotations

import argparse
import json
import os
import sqlite3
import sys
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

DEFAULT_OUTPUT = ROOT / "bundled_data" / "dev" / "policy_records.sqlite"
PLACEHOLDER_COLUMNS = [
    "CK_SYS_CD",
    "TCH_POL_ID",
    "CK_CMP_CD",
    "CK_POLICY_NBR",
    "COV_PHA_NBR",
    "PRS_CD",
    "PRS_SEQ_NBR",
    "SEG_IDX_NBR",
    "PRM_RT_TYP_CD",
    "JT_INS_IND",
    "SPM_BNF_TYP_CD",
    "SPM_BNF_SBY_CD",
    "TAR_TYP_CD",
    "MVRY_DT",
    "FND_ID_CD",
    "FND_VAL_PHA_NBR",
    "ERN_DT_MO_YR_NBR",
    "AGT_COM_PHA_NBR",
    "AGT_ITS_EFF_DT",
    "ASOF_DT",
    "SEQ_NO",
]
EXTRA_TABLES = {
    "LH_CSH_VAL_LOAN",
    "LH_FND_VAL_LOAN",
    "LH_CTT_CLIENT",
    "LH_LOC_CLT_ADR",
    "VH_POL_HAS_LOC_CLT",
}


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Export one policy's PolView Tables-panel data to local SQLite."
    )
    parser.add_argument("policy_number", help="Policy number, e.g. UE000576")
    parser.add_argument("--region", default="CKPR", help="DB2 region code. Default: CKPR")
    parser.add_argument("--company", default=None, help="Optional company code when policy exists in multiple companies")
    parser.add_argument("--system", default="I", help="CyberLife system code. Default: I")
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT), help="SQLite output path")
    parser.add_argument(
        "--no-placeholders",
        action="store_true",
        help="Only create exported data-bearing tables; skip empty mapped-table placeholders.",
    )
    return parser.parse_args()


def _mapped_tables() -> list[str]:
    from suiteview.polview.config.policy_records import POLICY_RECORD_TABLES, get_sorted_policy_records

    ordered = []
    seen = set()
    for policy_record in get_sorted_policy_records():
        for table in POLICY_RECORD_TABLES.get(policy_record, []):
            if table not in seen:
                ordered.append(table)
                seen.add(table)
    for table in sorted(EXTRA_TABLES - seen):
        ordered.append(table)
    return ordered


def _quote_identifier(value: str) -> str:
    return '"' + value.replace('"', '""') + '"'


def _sqlite_value(value: Any) -> Any:
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, bytes):
        return value.hex()
    return value


def _redacted_value(table: str, column: str, value: Any) -> Any:
    column_upper = column.upper()
    table_upper = table.upper()
    if table_upper == "LH_CTT_CLIENT" and (
        "DOB" in column_upper or "BIR" in column_upper or "BIRTH" in column_upper
    ):
        return None
    if table_upper == "VH_POL_HAS_LOC_CLT":
        name_tokens = ("FST_NM", "LST_NM", "MID_NM", "NM", "NAME", "FIRST", "LAST")
        phone_tokens = ("PHN", "PHONE", "TEL", "FAX")
        taxpayer_tokens = ("TAX", "TIN", "SSN", "SOC_SEC", "TPR", "TAXPAYER")
        if any(token in column_upper for token in name_tokens + phone_tokens + taxpayer_tokens):
            return None
    return value


def _create_empty_table(conn: sqlite3.Connection, table: str) -> None:
    column_sql = ", ".join(_quote_identifier(column) for column in PLACEHOLDER_COLUMNS)
    conn.execute(f"CREATE TABLE IF NOT EXISTS {_quote_identifier(table)} ({column_sql})")


def _write_table(
    conn: sqlite3.Connection,
    table: str,
    columns: list[str],
    rows: list[tuple],
) -> None:
    column_sql = ", ".join(_quote_identifier(column) for column in columns)
    conn.execute(f"DROP TABLE IF EXISTS {_quote_identifier(table)}")
    conn.execute(f"CREATE TABLE {_quote_identifier(table)} ({column_sql})")
    if not rows:
        return

    placeholders = ", ".join("?" for _ in columns)
    insert_sql = f"INSERT INTO {_quote_identifier(table)} ({column_sql}) VALUES ({placeholders})"
    redacted_rows = []
    for row in rows:
        redacted_rows.append([
            _sqlite_value(_redacted_value(table, column, value))
            for column, value in zip(columns, tuple(row))
        ])
    conn.executemany(insert_sql, redacted_rows)


def _resolve_policy(policy_number: str, region: str, company: str | None, system_code: str):
    from suiteview.polview.models.policy_information import PolicyInformation

    policy = PolicyInformation(
        policy_number,
        company_code=company,
        system_code=system_code,
        region=region,
    )
    if policy.available_companies:
        choices = ", ".join(policy.available_companies)
        raise RuntimeError(
            f"Policy {policy_number} exists in multiple companies ({choices}). "
            "Rerun with --company."
        )
    if not policy.exists:
        raise RuntimeError(f"Policy {policy_number} not found in {region}/{system_code}")
    return policy


def main() -> None:
    args = _parse_args()
    os.environ.pop("SUITEVIEW_LOCAL_DATA", None)

    from suiteview.core.db2_connection import DB2Connection

    policy = _resolve_policy(args.policy_number, args.region, args.company, args.system)
    policy_id = policy.policy_id
    company_code = policy.company_code
    system_code = policy.system_code
    where_clause = (
        f"CK_SYS_CD = '{system_code}' "
        f"AND TCH_POL_ID = '{policy_id}' "
        f"AND CK_CMP_CD = '{company_code}'"
    )
    fh_where_clause = f"TCH_POL_ID = '{policy_id}' AND CK_CMP_CD = '{company_code}'"

    output = Path(args.output).expanduser()
    output.parent.mkdir(parents=True, exist_ok=True)
    if output.exists():
        output.unlink()

    db = DB2Connection(args.region)
    out_conn = sqlite3.connect(output)
    exported = []
    skipped = []
    try:
        if not args.no_placeholders:
            for table in _mapped_tables():
                _create_empty_table(out_conn, table)

        for table in _mapped_tables():
            try:
                table_where = fh_where_clause if table.startswith("FH_") else where_clause
                sql = f"SELECT * FROM DB2TAB.{table} WHERE {table_where}"
                columns, rows = db.execute_query_with_headers(sql)
            except Exception as exc:
                skipped.append({"table": table, "reason": str(exc)})
                continue

            if not rows:
                continue

            columns = [str(column).upper() for column in columns]
            _write_table(out_conn, table, columns, rows)
            exported.append({"table": table, "rows": len(rows)})

        metadata_rows = [
            {"KEY": "policy_number", "VALUE": policy.policy_number},
            {"KEY": "company_code", "VALUE": company_code},
            {"KEY": "system_code", "VALUE": system_code},
            {"KEY": "policy_id", "VALUE": policy_id},
            {"KEY": "region", "VALUE": args.region.upper()},
            {"KEY": "exported_at", "VALUE": datetime.now().isoformat(timespec="seconds")},
            {"KEY": "redaction", "VALUE": "LH_CTT_CLIENT DOB/BIR/BIRTH; VH_POL_HAS_LOC_CLT names/phones/taxpayer identifiers"},
        ]
        _write_table(
            out_conn,
            "SUITEVIEW_LOCAL_EXPORT_METADATA",
            ["KEY", "VALUE"],
            [(row["KEY"], row["VALUE"]) for row in metadata_rows],
        )
        out_conn.commit()
    finally:
        out_conn.close()

    print(json.dumps({
        "output": str(output),
        "policy_number": policy.policy_number,
        "company_code": company_code,
        "system_code": system_code,
        "policy_id": policy_id,
        "exported_tables": exported,
        "skipped_tables": skipped,
        "redacted_tables": ["LH_CTT_CLIENT", "VH_POL_HAS_LOC_CLT"],
    }, indent=2))


if __name__ == "__main__":
    main()