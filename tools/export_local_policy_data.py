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
        description="Export PolView Tables-panel data to local SQLite."
    )
    parser.add_argument("policy_numbers", nargs="+", help="Policy numbers, e.g. UE000576 U0688012")
    parser.add_argument("--region", default="CKPR", help="DB2 region code. Default: CKPR")
    parser.add_argument("--company", default=None, help="Optional company code when policy exists in multiple companies")
    parser.add_argument("--system", default="I", help="CyberLife system code. Default: I")
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT), help="SQLite output path")
    parser.add_argument(
        "--append",
        action="store_true",
        help="Append/update policies in the existing SQLite file instead of rebuilding it.",
    )
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


def _normalized_export_value(
    table: str,
    column: str,
    value: Any,
    policy_number: str,
    policy_id: str,
    company_code: str,
    system_code: str,
) -> Any:
    column_upper = column.upper()
    if column_upper == "CK_POLICY_NBR":
        value_text = "" if value is None else str(value).strip()
        return value_text or policy_number
    if column_upper == "TCH_POL_ID" and (value is None or str(value).strip() == ""):
        return policy_id
    if column_upper == "CK_CMP_CD" and (value is None or str(value).strip() == ""):
        return company_code
    if column_upper == "CK_SYS_CD" and (value is None or str(value).strip() == ""):
        return system_code
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


def _redacted_export_row(
    table: str,
    columns: list[str],
    row: tuple,
    policy_number: str,
    policy_id: str,
    company_code: str,
    system_code: str,
) -> list[Any]:
    return [
        _sqlite_value(
            _redacted_value(
                table,
                column,
                _normalized_export_value(
                    table,
                    column,
                    value,
                    policy_number,
                    policy_id,
                    company_code,
                    system_code,
                ),
            )
        )
        for column, value in zip(columns, tuple(row))
    ]


def _with_required_lookup_columns(
    table: str,
    columns: list[str],
    rows: list[tuple],
    policy_number: str,
    policy_id: str,
    company_code: str,
    system_code: str,
) -> tuple[list[str], list[tuple]]:
    if table.upper() != "LH_BAS_POL":
        return columns, rows

    additions = []
    required_values = {
        "CK_POLICY_NBR": policy_number,
        "TCH_POL_ID": policy_id,
        "CK_CMP_CD": company_code,
        "CK_SYS_CD": system_code,
    }
    for column, value in required_values.items():
        if column not in columns:
            additions.append((column, value))

    if not additions:
        return columns, rows

    widened_columns = list(columns) + [column for column, _ in additions]
    widened_rows = [
        tuple(row) + tuple(value for _, value in additions)
        for row in rows
    ]
    return widened_columns, widened_rows


def _table_exists(conn: sqlite3.Connection, table: str) -> bool:
    row = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?",
        (table,),
    ).fetchone()
    return row is not None


def _table_columns(conn: sqlite3.Connection, table: str) -> list[str]:
    return [str(row[1]).upper() for row in conn.execute(f"PRAGMA table_info({_quote_identifier(table)})")]


def _table_row_count(conn: sqlite3.Connection, table: str) -> int:
    return int(conn.execute(f"SELECT COUNT(*) FROM {_quote_identifier(table)}").fetchone()[0])


def _delete_policy_rows(
    conn: sqlite3.Connection,
    table: str,
    policy_id: str,
    company_code: str,
    system_code: str,
) -> None:
    if not _table_exists(conn, table):
        return
    columns = set(_table_columns(conn, table))
    if "TCH_POL_ID" not in columns or "CK_CMP_CD" not in columns:
        return

    clauses = ["TCH_POL_ID = ?", "CK_CMP_CD = ?"]
    values: list[Any] = [policy_id, company_code]
    if "CK_SYS_CD" in columns:
        clauses.insert(0, "CK_SYS_CD = ?")
        values.insert(0, system_code)

    conn.execute(
        f"DELETE FROM {_quote_identifier(table)} WHERE {' AND '.join(clauses)}",
        values,
    )


def _append_table(
    conn: sqlite3.Connection,
    table: str,
    columns: list[str],
    rows: list[tuple],
    policy_number: str,
    policy_id: str,
    company_code: str,
    system_code: str,
) -> None:
    if not rows:
        return

    columns, rows = _with_required_lookup_columns(
        table,
        columns,
        rows,
        policy_number,
        policy_id,
        company_code,
        system_code,
    )

    if _table_exists(conn, table):
        existing_columns = _table_columns(conn, table)
        if existing_columns != columns:
            row_count = _table_row_count(conn, table)
            if row_count == 0:
                conn.execute(f"DROP TABLE IF EXISTS {_quote_identifier(table)}")
            else:
                for column in columns:
                    if column not in existing_columns:
                        conn.execute(
                            f"ALTER TABLE {_quote_identifier(table)} "
                            f"ADD COLUMN {_quote_identifier(column)}"
                        )
                existing_columns = _table_columns(conn, table)
                missing_columns = [column for column in columns if column not in existing_columns]
                if missing_columns:
                    raise RuntimeError(
                        f"Cannot append {table}: missing columns after widening: {missing_columns}"
                    )

    if not _table_exists(conn, table):
        column_sql = ", ".join(_quote_identifier(column) for column in columns)
        conn.execute(f"CREATE TABLE {_quote_identifier(table)} ({column_sql})")

    _delete_policy_rows(conn, table, policy_id, company_code, system_code)

    column_sql = ", ".join(_quote_identifier(column) for column in columns)
    placeholders = ", ".join("?" for _ in columns)
    insert_sql = f"INSERT INTO {_quote_identifier(table)} ({column_sql}) VALUES ({placeholders})"
    redacted_rows = []
    for row in rows:
        redacted_rows.append(
            _redacted_export_row(
                table,
                columns,
                tuple(row),
                policy_number,
                policy_id,
                company_code,
                system_code,
            )
        )
    conn.executemany(insert_sql, redacted_rows)


def _metadata_dict(conn: sqlite3.Connection) -> dict[str, str]:
    if not _table_exists(conn, "SUITEVIEW_LOCAL_EXPORT_METADATA"):
        return {}
    columns = _table_columns(conn, "SUITEVIEW_LOCAL_EXPORT_METADATA")
    if "KEY" not in columns or "VALUE" not in columns:
        return {}
    rows = conn.execute('SELECT "KEY", "VALUE" FROM "SUITEVIEW_LOCAL_EXPORT_METADATA"').fetchall()
    return {str(key): str(value) for key, value in rows}


def _ensure_exported_policies_table(conn: sqlite3.Connection) -> None:
    conn.execute(
        "CREATE TABLE IF NOT EXISTS SUITEVIEW_LOCAL_EXPORTED_POLICIES ("
        "POLICY_NUMBER, COMPANY_CODE, SYSTEM_CODE, POLICY_ID, REGION, EXPORTED_AT)"
    )


def _seed_existing_metadata(conn: sqlite3.Connection) -> None:
    _ensure_exported_policies_table(conn)
    existing_count = conn.execute("SELECT COUNT(*) FROM SUITEVIEW_LOCAL_EXPORTED_POLICIES").fetchone()[0]
    if existing_count:
        return
    metadata = _metadata_dict(conn)
    if not metadata.get("policy_number"):
        return
    conn.execute(
        "INSERT INTO SUITEVIEW_LOCAL_EXPORTED_POLICIES "
        "(POLICY_NUMBER, COMPANY_CODE, SYSTEM_CODE, POLICY_ID, REGION, EXPORTED_AT) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        (
            metadata.get("policy_number"),
            metadata.get("company_code"),
            metadata.get("system_code"),
            metadata.get("policy_id"),
            metadata.get("region"),
            metadata.get("exported_at"),
        ),
    )


def _record_policy_export(
    conn: sqlite3.Connection,
    policy_number: str,
    company_code: str,
    system_code: str,
    policy_id: str,
    region: str,
    exported_at: str,
) -> None:
    _ensure_exported_policies_table(conn)
    conn.execute(
        "DELETE FROM SUITEVIEW_LOCAL_EXPORTED_POLICIES "
        "WHERE POLICY_NUMBER = ? AND COMPANY_CODE = ? AND SYSTEM_CODE = ?",
        (policy_number, company_code, system_code),
    )
    conn.execute(
        "INSERT INTO SUITEVIEW_LOCAL_EXPORTED_POLICIES "
        "(POLICY_NUMBER, COMPANY_CODE, SYSTEM_CODE, POLICY_ID, REGION, EXPORTED_AT) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        (policy_number, company_code, system_code, policy_id, region, exported_at),
    )


def _write_metadata_summary(conn: sqlite3.Connection) -> None:
    _ensure_exported_policies_table(conn)
    policies = [
        str(row[0])
        for row in conn.execute(
            "SELECT POLICY_NUMBER FROM SUITEVIEW_LOCAL_EXPORTED_POLICIES ORDER BY POLICY_NUMBER"
        )
    ]
    metadata_rows = [
        {"KEY": "policy_numbers", "VALUE": ",".join(policies)},
        {"KEY": "policy_count", "VALUE": str(len(policies))},
        {"KEY": "updated_at", "VALUE": datetime.now().isoformat(timespec="seconds")},
        {"KEY": "redaction", "VALUE": "LH_CTT_CLIENT DOB/BIR/BIRTH; VH_POL_HAS_LOC_CLT names/phones/taxpayer identifiers"},
    ]
    _write_table(
        conn,
        "SUITEVIEW_LOCAL_EXPORT_METADATA",
        ["KEY", "VALUE"],
        [(row["KEY"], row["VALUE"]) for row in metadata_rows],
    )


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

    output = Path(args.output).expanduser()
    output.parent.mkdir(parents=True, exist_ok=True)
    if output.exists() and not args.append:
        output.unlink()

    db = DB2Connection(args.region)
    out_conn = sqlite3.connect(output)
    policies_exported = []
    try:
        if not args.no_placeholders:
            for table in _mapped_tables():
                _create_empty_table(out_conn, table)

        if args.append:
            _seed_existing_metadata(out_conn)

        for policy_number in args.policy_numbers:
            policy = _resolve_policy(policy_number, args.region, args.company, args.system)
            policy_id = policy.policy_id
            company_code = policy.company_code
            system_code = policy.system_code
            where_clause = (
                f"CK_SYS_CD = '{system_code}' "
                f"AND TCH_POL_ID = '{policy_id}' "
                f"AND CK_CMP_CD = '{company_code}'"
            )
            fh_where_clause = f"TCH_POL_ID = '{policy_id}' AND CK_CMP_CD = '{company_code}'"

            exported = []
            skipped = []
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
                if args.append:
                    _append_table(out_conn, table, columns, rows, policy.policy_number, policy_id, company_code, system_code)
                else:
                    _append_table(out_conn, table, columns, rows, policy.policy_number, policy_id, company_code, system_code)
                exported.append({"table": table, "rows": len(rows)})

            exported_at = datetime.now().isoformat(timespec="seconds")
            _record_policy_export(
                out_conn,
                policy.policy_number,
                company_code,
                system_code,
                policy_id,
                args.region.upper(),
                exported_at,
            )
            policies_exported.append({
                "policy_number": policy.policy_number,
                "company_code": company_code,
                "system_code": system_code,
                "policy_id": policy_id,
                "exported_tables": exported,
                "skipped_tables": skipped,
            })

        _write_metadata_summary(out_conn)
        out_conn.commit()
    finally:
        out_conn.close()

    print(json.dumps({
        "output": str(output),
        "mode": "append" if args.append else "rebuild",
        "policies": policies_exported,
        "redacted_tables": ["LH_CTT_CLIENT", "VH_POL_HAS_LOC_CLT"],
    }, indent=2))


if __name__ == "__main__":
    main()