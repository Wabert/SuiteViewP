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

import pyodbc


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

DEFAULT_OUTPUT = ROOT / "bundled_data" / "dev" / "rates.sqlite"
DEFAULT_PLANCODES = ["1U143900", "CCV00100", "1U536C00"]
DEFAULT_BENEFIT_TYPES = ["76", "39"]

PLANCODE_RATE_TABLES = [
    "Select_RATE_EPP",
    "Select_RATE_TPP",
    "Select_RATE_FLATPREM",
    "Select_RATE_MFEE",
    "Select_RATE_DBD",
    "Select_RATE_GINT",
    "Select_RATE_CORR",
    "Select_RATE_BONUSAV",
    "Select_RATE_BONUSDUR",
    "Select_RATE_MTP",
    "Select_RATE_CTP",
    "Select_RATE_TBL1CTP",
    "Select_RATE_TBL1MTP",
    "Select_RATE_EPU",
    "Select_RATE_COI",
    "Select_RATE_SCR",
    "Select_RATE_BANDSPECS",
    "Select_RATE_PLNCRD",
    "Select_RATE_PLNCRG",
    "Select_RATE_RLNCRD",
    "Select_RATE_RLNCRG",
    "Select_RATE_SNETPERIOD",
    "Select_SCALE_COI",
    "POINT_PVSRB",
]

BENEFIT_RATE_TABLES = [
    "Select_RATE_BENMTP",
    "Select_RATE_BENCTP",
    "Select_RATE_BENCOI",
]


def _parse_csv(value: str) -> list[str]:
    return [part.strip() for part in value.split(",") if part.strip()]


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Export selected UL_Rates tables to local SQLite for offline Illustration testing."
    )
    parser.add_argument(
        "--dsn",
        default="UL_Rates",
        help="ODBC DSN for the UL_Rates database. Default: UL_Rates",
    )
    parser.add_argument(
        "--plancodes",
        default=",".join(DEFAULT_PLANCODES),
        help="Comma-separated plancodes to export. Default: 1U143900,CCV00100,1U536C00",
    )
    parser.add_argument(
        "--base-plancode",
        default="1U143900",
        help="Plancode whose benefit rates should be exported. Default: 1U143900",
    )
    parser.add_argument(
        "--benefit-types",
        default=",".join(DEFAULT_BENEFIT_TYPES),
        help="Comma-separated benefit type codes for BEN* tables. Default: 76,39",
    )
    parser.add_argument(
        "--output",
        default=str(DEFAULT_OUTPUT),
        help="SQLite output path. Default: bundled_data/dev/rates.sqlite",
    )
    parser.add_argument(
        "--append",
        action="store_true",
        help="Append/update selected plancodes in the existing SQLite file instead of rebuilding it.",
    )
    return parser.parse_args()


def _quote_identifier(identifier: str) -> str:
    return '"' + identifier.replace('"', '""') + '"'


def _sqlite_value(value: Any) -> Any:
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, bytes):
        return value.hex()
    return value


def _where_in(column_name: str, values: list[str]) -> tuple[str, list[str]]:
    placeholders = ", ".join("?" for _ in values)
    return f"{column_name} IN ({placeholders})", list(values)


def _fetch_table(conn, table_name: str, where_sql: str, params: list[str]) -> tuple[list[str], list[tuple]]:
    cursor = conn.cursor()
    try:
        cursor.execute(f"SELECT * FROM {table_name} WHERE {where_sql}", params)
        columns = [desc[0] for desc in cursor.description] if cursor.description else []
        rows = [tuple(row) for row in cursor.fetchall()]
        return columns, rows
    finally:
        cursor.close()


def _write_table(conn: sqlite3.Connection, table_name: str, columns: list[str], rows: list[tuple]) -> None:
    column_sql = ", ".join(_quote_identifier(str(column)) for column in columns)
    table_sql = _quote_identifier(table_name)
    conn.execute(f"DROP TABLE IF EXISTS {table_sql}")
    if not columns:
        conn.execute(f"CREATE TABLE {table_sql} (_empty INTEGER)")
        return
    conn.execute(f"CREATE TABLE {table_sql} ({column_sql})")
    if not rows:
        return
    placeholders = ", ".join("?" for _ in columns)
    conn.executemany(
        f"INSERT INTO {table_sql} ({column_sql}) VALUES ({placeholders})",
        [[_sqlite_value(value) for value in row] for row in rows],
    )


def _table_exists(conn: sqlite3.Connection, table_name: str) -> bool:
    return conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?",
        (table_name,),
    ).fetchone() is not None


def _table_columns(conn: sqlite3.Connection, table_name: str) -> list[str]:
    return [str(row[1]) for row in conn.execute(f"PRAGMA table_info({_quote_identifier(table_name)})")]


def _table_row_count(conn: sqlite3.Connection, table_name: str) -> int:
    return int(conn.execute(f"SELECT COUNT(*) FROM {_quote_identifier(table_name)}").fetchone()[0])


def _append_table(
    conn: sqlite3.Connection,
    table_name: str,
    columns: list[str],
    rows: list[tuple],
    delete_sql: str,
    delete_params: list[str],
) -> None:
    if not columns:
        return

    table_sql = _quote_identifier(table_name)
    if _table_exists(conn, table_name):
        existing_columns = _table_columns(conn, table_name)
        if existing_columns != columns:
            if _table_row_count(conn, table_name) == 0:
                conn.execute(f"DROP TABLE IF EXISTS {table_sql}")
            else:
                raise RuntimeError(
                    f"Cannot append {table_name}: existing columns differ from source columns"
                )

    if not _table_exists(conn, table_name):
        column_sql = ", ".join(_quote_identifier(str(column)) for column in columns)
        conn.execute(f"CREATE TABLE {table_sql} ({column_sql})")

    conn.execute(f"DELETE FROM {table_sql} WHERE {delete_sql}", delete_params)
    if not rows:
        return

    column_sql = ", ".join(_quote_identifier(str(column)) for column in columns)
    placeholders = ", ".join("?" for _ in columns)
    conn.executemany(
        f"INSERT INTO {table_sql} ({column_sql}) VALUES ({placeholders})",
        [[_sqlite_value(value) for value in row] for row in rows],
    )


def _export_rates(
    source_conn,
    target_conn: sqlite3.Connection,
    plancodes: list[str],
    base_plancode: str,
    benefit_types: list[str],
    append: bool,
) -> dict:
    exported = []
    skipped = []

    plancode_where, plancode_params = _where_in("Plancode", plancodes)
    for table_name in PLANCODE_RATE_TABLES:
        try:
            columns, rows = _fetch_table(source_conn, table_name, plancode_where, plancode_params)
        except Exception as exc:
            skipped.append({"table": table_name, "reason": str(exc)})
            if not append:
                _write_table(target_conn, table_name, [], [])
            continue
        if append:
            _append_table(target_conn, table_name, columns, rows, plancode_where, plancode_params)
        else:
            _write_table(target_conn, table_name, columns, rows)
        exported.append({"table": table_name, "rows": len(rows)})

    if benefit_types:
        benefit_where, benefit_params = _where_in("BenefitType", benefit_types)
        benefit_sql = f"Plancode = ? AND {benefit_where}"
        for table_name in BENEFIT_RATE_TABLES:
            try:
                columns, rows = _fetch_table(source_conn, table_name, benefit_sql, [base_plancode, *benefit_params])
            except Exception as exc:
                skipped.append({"table": table_name, "reason": str(exc)})
                if not append:
                    _write_table(target_conn, table_name, [], [])
                continue
            if append:
                _append_table(target_conn, table_name, columns, rows, benefit_sql, [base_plancode, *benefit_params])
            else:
                _write_table(target_conn, table_name, columns, rows)
            exported.append({"table": table_name, "rows": len(rows)})

    _write_table(
        target_conn,
        "SUITEVIEW_LOCAL_RATE_EXPORT_METADATA",
        ["KEY", "VALUE"],
        [
            ("plancodes", ",".join(plancodes)),
            ("base_plancode", base_plancode),
            ("benefit_types", ",".join(benefit_types)),
            ("exported_at", datetime.now().isoformat(timespec="seconds")),
        ],
    )

    return {"exported_tables": exported, "skipped_tables": skipped}


def main() -> None:
    args = _parse_args()
    plancodes = _parse_csv(args.plancodes)
    benefit_types = _parse_csv(args.benefit_types)
    output = Path(args.output).expanduser()
    output.parent.mkdir(parents=True, exist_ok=True)
    temp_output = output.with_suffix(output.suffix + ".tmp")
    if args.append:
        temp_output = output
    elif temp_output.exists():
        temp_output.unlink()

    source_conn = pyodbc.connect(f"DSN={args.dsn}", autocommit=True)
    target_conn = sqlite3.connect(temp_output)
    try:
        result = _export_rates(source_conn, target_conn, plancodes, args.base_plancode.strip(), benefit_types, args.append)
        target_conn.commit()
    finally:
        target_conn.close()
        source_conn.close()

    if not args.append:
        os.replace(temp_output, output)

    print(json.dumps({
        "output": str(output),
        "mode": "append" if args.append else "rebuild",
        "dsn": args.dsn,
        "plancodes": plancodes,
        "base_plancode": args.base_plancode.strip(),
        "benefit_types": benefit_types,
        **result,
    }, indent=2))


if __name__ == "__main__":
    main()