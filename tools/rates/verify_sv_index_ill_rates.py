"""Read back SV_INDEX_ILL_RATES from UL_Rates to verify the load.

Usage:
    venv\\Scripts\\python.exe tools\\verify_sv_index_ill_rates.py
    venv\\Scripts\\python.exe tools\\verify_sv_index_ill_rates.py "{\"dsn\": \"UL_Rates\"}"

Output: a JSON summary (schema, counts, NULL counts, spot-check rows) to stdout.
"""

from __future__ import annotations

import json
import sys

import pyodbc

TABLE_NAME = "SV_INDEX_ILL_RATES"
DEFAULT_DSN = "UL_Rates"


def main() -> None:
    config = json.loads(sys.argv[1]) if len(sys.argv) > 1 else {}
    dsn = str(config.get("dsn", DEFAULT_DSN))

    conn = pyodbc.connect(f"DSN={dsn}", autocommit=True, timeout=10)
    result: dict = {"table": TABLE_NAME, "dsn": dsn}
    try:
        cur = conn.cursor()

        result["schema"] = [
            {
                "column": str(r.column_name),
                "type": str(r.type_name),
                "size": r.column_size,
                "scale": r.decimal_digits,
                "nullable": bool(r.nullable),
            }
            for r in cur.columns(table=TABLE_NAME)
        ]

        cur.execute(f"SELECT COUNT(*) FROM [dbo].[{TABLE_NAME}]")
        result["row_count"] = cur.fetchone()[0]

        cur.execute(
            f"SELECT COUNT(*) FROM [dbo].[{TABLE_NAME}] WHERE [Rate_ANICO] IS NULL"
        )
        result["null_rate_anico"] = cur.fetchone()[0]
        cur.execute(
            f"SELECT COUNT(*) FROM [dbo].[{TABLE_NAME}] WHERE [Rate_RGA] IS NULL"
        )
        result["null_rate_rga"] = cur.fetchone()[0]

        cur.execute(
            f"SELECT [EffDate], COUNT(*) FROM [dbo].[{TABLE_NAME}] "
            "GROUP BY [EffDate] ORDER BY [EffDate]"
        )
        result["rows_by_date"] = {str(r[0]): r[1] for r in cur.fetchall()}

        # Spot checks: a normalized-percentage row and a NULL-ANICO row.
        checks = [
            ("01", "1U147900", "IX", "2026-07-01"),  # 6.10% -> 0.061000
            ("01", "1U145800", "IX", "2026-07-01"),  # blank ANICO -> NULL, RGA 0.0487
            ("26", "1U146900", "IX", "2026-08-01"),  # asymmetric ANICO/RGA
        ]
        spot = []
        for company, plancode, fund, eff in checks:
            cur.execute(
                f"SELECT [Company], [Plancode], [FundID], [EffDate], "
                f"[Rate_ANICO], [Rate_RGA] FROM [dbo].[{TABLE_NAME}] "
                "WHERE [Company]=? AND [Plancode]=? AND [FundID]=? AND [EffDate]=?",
                (company, plancode, fund, eff),
            )
            row = cur.fetchone()
            spot.append(None if row is None else {
                "Company": row[0], "Plancode": row[1], "FundID": row[2],
                "EffDate": str(row[3]),
                "Rate_ANICO": None if row[4] is None else float(row[4]),
                "Rate_RGA": None if row[5] is None else float(row[5]),
            })
        result["spot_checks"] = spot
        cur.close()
    finally:
        conn.close()

    print(json.dumps(result, indent=2, default=str))


if __name__ == "__main__":
    main()
