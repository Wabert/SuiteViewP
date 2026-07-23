"""Report Rate Manager target-table columns through an ODBC DSN.

Usage:
    venv\\Scripts\\python.exe tools\\probe_ul_rates_schema.py [DSN]
"""

from __future__ import annotations

import json
import sys

import pyodbc


TABLES = (
    "POINT_PVSRB",
    "RATE_COI",
    "RATE_TRGPREM",
    "RATE_SCR",
    "RATE_EPU",
    "POINT_BENEFIT",
    "RATE_BENCOI",
    "RATE_BENTRG",
)


def main() -> None:
    dsn = sys.argv[1] if len(sys.argv) > 1 else "UL_Rates"
    connection = pyodbc.connect(f"DSN={dsn}", autocommit=True, timeout=10)
    result = {}
    try:
        cursor = connection.cursor()
        for table_name in TABLES:
            try:
                rows = list(cursor.columns(table=table_name))
                result[table_name] = {
                    "columns": [str(row.column_name) for row in rows],
                    "types": {
                        str(row.column_name): {
                            "type": str(row.type_name),
                            "size": row.column_size,
                            "scale": row.decimal_digits,
                            "nullable": bool(row.nullable),
                        }
                        for row in rows
                    },
                }
            except Exception as exc:
                result[table_name] = {"error": str(exc)}
        cursor.close()
    finally:
        connection.close()
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
