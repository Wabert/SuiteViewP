"""Inspect live Whole Life and plan-description schemas without writing data."""

from __future__ import annotations

import json

import pyodbc


def main() -> None:
    connection = pyodbc.connect("DSN=UL_Rates", autocommit=True, timeout=10)
    try:
        cursor = connection.cursor()
        tables = cursor.execute(
            "SELECT TABLE_NAME FROM INFORMATION_SCHEMA.TABLES "
            "WHERE TABLE_SCHEMA = 'dbo' AND "
            "(TABLE_NAME LIKE 'WL[_]%' OR TABLE_NAME = 'CYBERLIFE_PDF') "
            "ORDER BY TABLE_NAME"
        ).fetchall()
        result = {}
        for (table,) in tables:
            columns = list(cursor.columns(table=table, schema="dbo"))
            keys = list(cursor.primaryKeys(table=table, schema="dbo"))
            result[table] = {
                "columns": [
                    {
                        "name": row.column_name, "type": row.type_name,
                        "size": row.column_size, "scale": row.decimal_digits,
                        "nullable": bool(row.nullable),
                    }
                    for row in columns
                ],
                "primary_key": [row.column_name for row in keys],
            }
        print(json.dumps(result, indent=2))
    finally:
        connection.close()


if __name__ == "__main__":
    main()
