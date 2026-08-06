"""Rebuild local Select_RATE_BANDSPECS from the live UL_Rates schema.

Rebuilds bundled_data/dev/rates.sqlite's Select_RATE_BANDSPECS table using the
live column list (e.g. after a schema change such as adding Issue_Date), for
the union of plancodes already present locally plus any extra plancodes given.

Usage:
    reload_local_bandspecs.py '<json>'

    {"dsn": "UL_Rates", "plancodes": ["1U144600", ...], "output": "..."}

All keys optional; "plancodes" are ADDED to those already in the local table.
"""
from __future__ import annotations

import json
import sqlite3
import sys
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

import pyodbc

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_OUTPUT = ROOT / "bundled_data" / "dev" / "rates.sqlite"
TABLE = "Select_RATE_BANDSPECS"


def _sqlite_value(value: Any) -> Any:
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, bytes):
        return value.hex()
    return value


def _quote(identifier: str) -> str:
    return '"' + identifier.replace('"', '""') + '"'


def main() -> None:
    cmd = json.loads(sys.argv[1]) if len(sys.argv) > 1 else {}
    dsn = cmd.get("dsn", "UL_Rates")
    output = Path(cmd.get("output", DEFAULT_OUTPUT))
    extra_plancodes = [str(code).strip() for code in cmd.get("plancodes", []) if str(code).strip()]

    target = sqlite3.connect(output)
    try:
        existing = [
            str(row[0])
            for row in target.execute(f"SELECT DISTINCT Plancode FROM {_quote(TABLE)}")
        ]
        plancodes = sorted(set(existing) | set(extra_plancodes))
        if not plancodes:
            raise RuntimeError("No plancodes to reload (local table empty and none provided)")

        source = pyodbc.connect(f"DSN={dsn}", autocommit=True, timeout=10)
        try:
            cursor = source.cursor()
            placeholders = ", ".join("?" for _ in plancodes)
            cursor.execute(
                f"SELECT * FROM {TABLE} WHERE Plancode IN ({placeholders})",
                plancodes,
            )
            columns = [desc[0] for desc in cursor.description]
            rows = [tuple(row) for row in cursor.fetchall()]
            cursor.close()
        finally:
            source.close()

        column_sql = ", ".join(_quote(column) for column in columns)
        target.execute(f"DROP TABLE IF EXISTS {_quote(TABLE)}")
        target.execute(f"CREATE TABLE {_quote(TABLE)} ({column_sql})")
        insert_placeholders = ", ".join("?" for _ in columns)
        target.executemany(
            f"INSERT INTO {_quote(TABLE)} ({column_sql}) VALUES ({insert_placeholders})",
            [[_sqlite_value(value) for value in row] for row in rows],
        )
        target.commit()
    finally:
        target.close()

    print(json.dumps({
        "output": str(output),
        "table": TABLE,
        "columns": columns,
        "plancodes": plancodes,
        "rows": len(rows),
    }, indent=2))


if __name__ == "__main__":
    main()
