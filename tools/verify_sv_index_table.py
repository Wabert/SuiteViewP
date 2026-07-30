"""Read back a SuiteView UL_Rates table to verify a load.

Generic verifier for the SV_INDEX_* illustration tables. Reports the schema,
row counts, per-group counts, NULL counts, and a few sample rows.

Usage:
    venv\\Scripts\\python.exe tools\\verify_sv_index_table.py "{\"table\": \"SV_INDEX_MARKET_RETURNS\"}"
    venv\\Scripts\\python.exe tools\\verify_sv_index_table.py "{\"table\": \"SV_INDEX_ILL_RATES\", \"dsn\": \"UL_Rates\"}"

Config keys:
    table    (required) — table name (without schema); assumed in [dbo].
    dsn      (optional) — ODBC DSN, default "UL_Rates".
    group_by (optional) — column to GROUP BY for a per-group count breakdown.

Output: a JSON summary to stdout.
"""

from __future__ import annotations

import json
import sys

import pyodbc

DEFAULT_DSN = "UL_Rates"


def _quote(identifier: str) -> str:
    return "[" + identifier.replace("]", "]]") + "]"


def main() -> None:
    if len(sys.argv) < 2:
        print(json.dumps({"error": "missing config; pass {\"table\": \"...\"}"}))
        raise SystemExit(1)
    config = json.loads(sys.argv[1])
    table = str(config["table"])
    dsn = str(config.get("dsn", DEFAULT_DSN))
    group_by = config.get("group_by")

    conn = pyodbc.connect(f"DSN={dsn}", autocommit=True, timeout=10)
    result: dict = {"table": table, "dsn": dsn}
    try:
        cur = conn.cursor()

        columns = list(cur.columns(table=table))
        result["schema"] = [
            {
                "column": str(r.column_name),
                "type": str(r.type_name),
                "size": r.column_size,
                "scale": r.decimal_digits,
                "nullable": bool(r.nullable),
            }
            for r in columns
        ]

        cur.execute(f"SELECT COUNT(*) FROM [dbo].{_quote(table)}")
        result["row_count"] = cur.fetchone()[0]

        # NULL counts per column.
        null_counts = {}
        for col in (str(r.column_name) for r in columns):
            cur.execute(
                f"SELECT COUNT(*) FROM [dbo].{_quote(table)} "
                f"WHERE {_quote(col)} IS NULL"
            )
            null_counts[col] = cur.fetchone()[0]
        result["null_counts"] = null_counts

        if group_by:
            cur.execute(
                f"SELECT {_quote(group_by)}, COUNT(*) FROM [dbo].{_quote(table)} "
                f"GROUP BY {_quote(group_by)} ORDER BY {_quote(group_by)}"
            )
            result["counts_by_" + group_by] = {str(r[0]): r[1] for r in cur.fetchall()}

        col_names = [str(r.column_name) for r in columns]
        cur.execute(f"SELECT TOP 5 * FROM [dbo].{_quote(table)}")
        samples = []
        for row in cur.fetchall():
            samples.append({
                name: (float(val) if isinstance(val, (int, float)) or
                       type(val).__name__ == "Decimal" else str(val)) if val is not None else None
                for name, val in zip(col_names, row)
            })
        result["sample_rows"] = samples
        cur.close()
    finally:
        conn.close()

    print(json.dumps(result, indent=2, default=str))


if __name__ == "__main__":
    main()
