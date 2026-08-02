"""Run a read-only SELECT against the UL_Rates ODBC DSN and print JSON rows.

Usage:
    query_ul_rates.py '<json>'

    {"sql": "SELECT ...", "params": [...], "dsn": "UL_Rates", "limit": 50}

Read-only inspection helper (companion to query_local_sqlite.py) for
verifying live UL_Rates schemas/data before exporting to local SQLite.
"""
from __future__ import annotations

import json
import sys

import pyodbc


def main() -> None:
    cmd = json.loads(sys.argv[1])
    dsn = cmd.get("dsn", "UL_Rates")
    params = cmd.get("params", [])
    limit = int(cmd.get("limit", 50))

    conn = pyodbc.connect(f"DSN={dsn}", autocommit=True, timeout=10)
    try:
        cursor = conn.cursor()
        cursor.execute(cmd["sql"], params)
        columns = [desc[0] for desc in cursor.description] if cursor.description else []
        rows = [
            {column: (None if value is None else str(value)) for column, value in zip(columns, row)}
            for row in cursor.fetchmany(limit)
        ]
        cursor.close()
    finally:
        conn.close()
    print(json.dumps({"dsn": dsn, "columns": columns, "rows": rows, "count": len(rows)}, indent=2))


if __name__ == "__main__":
    main()
