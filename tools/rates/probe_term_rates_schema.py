r"""Report the TERM_* rate table schemas through an ODBC DSN.

Companion to probe_ul_rates_schema.py, for the Term (not UL) rate tables.

Usage:
    venv\Scripts\python.exe tools\rates\probe_term_rates_schema.py [DSN]
"""

from __future__ import annotations

import json
import sys

import pyodbc


TABLES = (
    "TERM_POINT_PV",
    "TERM_POINT_PVSRB",
    "TERM_POINT_BENEFIT",
    "TERM_RATE_MODEFACT",
    "TERM_RATE_BANDSPECS",
    "TERM_RATE_PREM",
    "TERM_RATE_BEN",
)


def main() -> None:
    dsn = sys.argv[1] if len(sys.argv) > 1 else "UL_Rates"
    connection = pyodbc.connect(f"DSN={dsn}", autocommit=True, timeout=10)
    result: dict = {}
    try:
        cursor = connection.cursor()
        for table_name in TABLES:
            try:
                rows = list(cursor.columns(table=table_name))
                if not rows:
                    result[table_name] = {"error": "table not found"}
                    continue
                result[table_name] = {
                    "columns": [
                        {
                            "name": str(row.column_name),
                            "type": str(row.type_name),
                            "size": row.column_size,
                            "nullable": bool(row.nullable),
                        }
                        for row in rows
                    ],
                }
                count = cursor.execute(
                    f"SELECT COUNT(*) FROM [{table_name}]").fetchone()[0]
                result[table_name]["row_count"] = int(count)
            except pyodbc.Error as exc:
                result[table_name] = {"error": str(exc)}
        cursor.close()
    finally:
        connection.close()
    print(json.dumps({"dsn": dsn, "tables": result}, indent=2))


if __name__ == "__main__":
    main()
