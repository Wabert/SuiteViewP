"""Create and populate SV_INDEX_BENCHMARK_MINMAX in UL_Rates.

The table holds 25-year lookback minimum and maximum geometric averages for
benchmark index strategies. Rows are keyed by plan, reinsurance block, fund,
and effective date. Blank reinsurance block indicators are stored as empty
strings rather than NULL.

The supplied rates are percentages without percent signs. They are normalized
to decimal fractions (``7.56`` -> ``0.075600``) to match the other SV_INDEX_*
rate tables. Exact duplicate source rows are reported and collapsed; conflicting
rows for the same key fail validation.

Usage:
    # Parse and validate only:
    venv\\Scripts\\python.exe tools\\create_sv_index_benchmark_minmax.py

    # Create table if needed and upsert the validated rows:
    venv\\Scripts\\python.exe tools\\create_sv_index_benchmark_minmax.py --live
    venv\\Scripts\\python.exe tools\\create_sv_index_benchmark_minmax.py --dsn=UL_Rates
"""

from __future__ import annotations

import json
import sys
from datetime import date, datetime
from typing import List, Tuple


TABLE_NAME = "SV_INDEX_BENCHMARK_MINMAX"
DEFAULT_DSN = "UL_Rates"

Row = Tuple[str, str, str, date, float, float]
Key = Tuple[str, str, str, date]

RAW_DATA = """\
PLAN_ID|REIN_BLOCK_IND|FUND_ID|EFFECTIVE_DATE|MAX_GEOMETRIC_AVG|MIN_GEOMETRIC_AVG
1U144600||IX|09/01/2023|7.56|3.88
1U144600||IX|09/01/2022|7.71|3.93
1U144600||IX|02/01/2022|7.43|3.82
1U144600||IX|11/01/2019|7.41|3.82
1U144600||IX|06/01/2019|8.00|4.04
1U144600||IX|12/01/2018|8.30|4.16
1U144600||IX|07/01/2018|8.72|4.32
1U144600||IX|01/01/2017|9.13|4.49
1U144600||IX|01/01/1900|9.39|4.60
1U144600|R|IX|09/01/2023|7.56|3.88
1U144600|R|IX|09/01/2022|7.71|3.93
1U144600|R|IX|02/01/2022|7.43|3.82
1U144600|R|IX|11/01/2019|7.41|3.82
1U144600|R|IX|06/01/2019|8.00|4.04
1U144600|R|IX|12/01/2018|8.30|4.16
1U144600|R|IX|12/01/2018|8.30|4.16
1U144600|R|IX|07/01/2018|8.72|4.32
1U144600|R|IX|01/01/2017|9.13|4.49
1U144600|R|IX|01/01/1900|9.39|4.60
1U144700||IX|09/01/2023|7.56|3.88
1U144700||IX|09/01/2022|7.71|3.93
1U144700||IX|02/01/2022|7.43|3.82
1U144700||IX|11/01/2019|7.41|3.82
1U144700||IX|06/01/2019|8.00|4.04
1U144700||IX|12/01/2018|8.30|4.16
1U144700||IX|07/01/2018|8.72|4.32
1U144700||IX|01/01/2017|9.13|4.49
1U144700||IX|01/01/1900|9.39|4.60
1U144700|R|IX|09/01/2023|7.56|3.88
1U144700|R|IX|09/01/2022|7.71|3.93
1U144700|R|IX|02/01/2022|7.43|3.82
1U144700|R|IX|02/01/2022|7.43|3.82
1U144700|R|IX|11/01/2019|7.41|3.82
1U144700|R|IX|06/01/2019|8.00|4.04
1U144700|R|IX|12/01/2018|8.30|4.16
1U144700|R|IX|07/01/2018|8.72|4.32
1U144700|R|IX|01/01/2017|9.13|4.49
1U144700|R|IX|01/01/1900|9.39|4.60
1U144800||IX|09/01/2023|7.56|3.88
1U144800||IX|09/01/2022|7.71|3.93
1U144800||IX|02/01/2022|7.43|3.82
1U144800||IX|11/01/2019|7.41|3.82
1U144800||IX|06/01/2019|8.00|4.04
1U144800||IX|12/01/2018|8.30|4.16
1U144800||IX|07/01/2018|8.72|4.32
1U144800||IX|01/01/2017|9.13|4.49
1U144800||IX|01/01/1900|9.39|4.60
1U144800||IX|01/01/1900|9.39|4.60
1U144800|R|IX|09/01/2023|7.56|3.88
1U144800|R|IX|09/01/2022|7.71|3.93
1U144800|R|IX|02/01/2022|7.43|3.82
1U144800|R|IX|11/01/2019|7.41|3.82
1U144800|R|IX|06/01/2019|8.00|4.04
1U144800|R|IX|12/01/2018|8.30|4.16
1U144800|R|IX|07/01/2018|8.72|4.32
1U144800|R|IX|01/01/2017|9.13|4.49
1U144800|R|IX|01/01/1900|9.39|4.60
1U145500||IX|09/01/2023|7.56|3.88
1U145500||IX|09/01/2022|7.71|3.93
1U145500||IX|02/01/2022|7.43|3.82
1U145500||IX|11/01/2019|7.41|3.82
1U145500||IX|06/01/2019|8.00|4.04
1U145500||IX|12/01/2018|8.30|4.16
1U145500||IX|12/01/2018|8.30|4.16
1U145500||IX|07/01/2018|8.72|4.32
1U145500||IX|01/01/2017|9.13|4.49
1U145500||IX|01/01/1900|9.39|4.60
1U145500|R|IX|09/01/2023|7.56|3.88
1U145500|R|IX|09/01/2022|7.71|3.93
1U145500|R|IX|02/01/2022|7.43|3.82
1U145500|R|IX|11/01/2019|7.41|3.82
1U145500|R|IX|06/01/2019|8.00|4.04
1U145500|R|IX|12/01/2018|8.30|4.16
1U145500|R|IX|07/01/2018|8.72|4.32
1U145500|R|IX|01/01/2017|9.13|4.49
1U145500|R|IX|01/01/1900|9.39|4.60
1U145600||IX|02/01/2023|6.90|3.56
1U145600||IX|02/01/2022|6.90|3.55
1U145600||IX|03/01/2021|6.85|3.55
1U145600||IX|03/01/2021|6.85|3.55
1U145600||IX|03/01/2020|6.98|3.62
1U145600||IX|11/01/2019|7.26|3.75
1U145600||IX|09/01/2019|8.00|4.04
1U145600||IX|03/01/2019|8.44|4.21
1U145600||IX|07/01/2018|8.72|4.32
1U145600||IX|01/01/2017|9.13|4.49
1U145600||IX|01/01/1900|9.39|4.60
1U145600|R|IX|03/01/2026|7.04|3.97
1U145600|R|IX|02/01/2023|6.90|3.56
1U145600|R|IX|02/01/2022|6.90|3.55
1U145600|R|IX|03/01/2021|6.85|3.55
1U145600|R|IX|03/01/2020|6.98|3.62
1U145600|R|IX|11/01/2019|7.26|3.75
1U145600|R|IX|09/01/2019|8.00|4.04
1U145600|R|IX|03/01/2019|8.44|4.21
1U145600|R|IX|03/01/2019|8.44|4.21
1U145600|R|IX|07/01/2018|8.72|4.32
1U145600|R|IX|01/01/2017|9.13|4.49
1U145600|R|IX|01/01/1900|9.39|4.60
1U145800||IX|09/01/2023|6.09|3.22
1U145800||IX|02/01/2023|6.26|3.29
1U145800||IX|09/01/2022|6.26|3.28
1U145800||IX|02/01/2022|5.91|3.14
1U145800||IX|05/01/2020|5.88|3.14
1U145800||IX|02/01/2020|6.23|3.28
1U145800||IX|11/01/2019|6.09|3.28
1U145800||IX|06/01/2019|6.78|3.55
1U145800||IX|12/01/2018|7.10|3.69
1U145800||IX|07/01/2018|7.56|3.87
1U145800||IX|01/01/2017|7.86|3.99
1U145800||IX|01/01/1900|8.00|4.04
1U145800||IX|01/01/1900|8.00|4.04
1U145800|R|IX|09/01/2023|6.09|3.22
1U145800|R|IX|02/01/2023|6.26|3.29
1U145800|R|IX|09/01/2022|6.26|3.28
1U145800|R|IX|02/01/2022|5.91|3.14
1U145800|R|IX|05/01/2020|5.88|3.14
1U145800|R|IX|02/01/2020|6.23|3.28
1U145800|R|IX|11/01/2019|6.09|3.28
1U145800|R|IX|06/01/2019|6.78|3.55
1U145800|R|IX|12/01/2018|7.10|3.69
1U145800|R|IX|07/01/2018|7.56|3.87
1U145800|R|IX|01/01/2017|7.86|3.99
1U145800|R|IX|01/01/1900|8.00|4.04
1U145900||IX|03/01/2026|6.58|3.74
1U145900||IX|09/01/2023|6.43|3.36
1U145900||IX|02/01/2023|6.26|3.29
1U145900||IX|02/01/2023|6.26|3.29
1U145900||IX|02/01/2022|6.26|3.28
1U145900||IX|03/01/2020|6.23|3.28
1U145900||IX|02/01/2020|6.72|3.48
1U145900||IX|11/01/2019|6.60|3.48
1U145900||IX|09/01/2019|7.10|3.69
1U145900||IX|07/01/2018|7.56|3.87
1U145900||IX|01/01/2017|7.86|3.99
1U145900||IX|01/01/1900|8.00|4.04
1U145900|R|IX|03/01/2026|6.58|3.74
1U145900|R|IX|09/01/2023|6.43|3.36
1U145900|R|IX|02/01/2023|6.26|3.29
1U145900|R|IX|02/01/2022|6.26|3.28
1U145900|R|IX|03/01/2020|6.23|3.28
1U145900|R|IX|02/01/2020|6.72|3.48
1U145900|R|IX|11/01/2019|6.60|3.48
1U145900|R|IX|11/01/2019|6.60|3.48
1U145900|R|IX|09/01/2019|7.10|3.69
1U145900|R|IX|07/01/2018|7.56|3.87
1U145900|R|IX|01/01/2017|7.86|3.99
1U145900|R|IX|01/01/1900|8.00|4.04
1U146400||IX|09/01/2023|7.56|3.88
1U146400||IX|09/01/2022|7.71|3.93
1U146400||IX|02/01/2022|7.43|3.82
1U146400||IX|11/01/2019|7.41|3.82
1U146400||IX|06/01/2019|8.00|4.04
1U146400||IX|12/01/2018|8.30|4.16
1U146400||IX|07/01/2018|8.72|4.32
1U146400||IX|01/01/2017|9.13|4.49
1U146400|R|IX|09/01/2023|7.56|3.88
1U146400|R|IX|09/01/2022|7.71|3.93
1U146400|R|IX|02/01/2022|7.43|3.82
1U146400|R|IX|02/01/2022|7.43|3.82
1U146400|R|IX|11/01/2019|7.41|3.82
1U146400|R|IX|06/01/2019|8.00|4.04
1U146400|R|IX|12/01/2018|8.30|4.16
1U146400|R|IX|07/01/2018|8.72|4.32
1U146400|R|IX|01/01/2017|9.13|4.49
1U146500||IX|11/01/2019|7.26|3.75
1U146500||IX|09/01/2019|8.00|4.04
1U146500||IX|03/01/2019|8.44|4.21
1U146500||IX|07/01/2018|8.72|4.32
1U146500||IX|01/01/2017|9.13|4.49
1U146500|R|IX|11/01/2019|7.26|3.75
1U146500|R|IX|09/01/2019|8.00|4.04
1U146500|R|IX|03/01/2019|8.44|4.21
1U146500|R|IX|07/01/2018|8.72|4.32
1U146500|R|IX|01/01/2017|9.13|4.49
1U146500|R|IX|01/01/2017|9.13|4.49
1U146800||IP|02/01/2023|8.86|4.39
1U146800||IP|02/01/2022|8.86|4.38
1U146800||IP|02/01/2021|8.58|4.27
1U146800||IP|07/01/2020|8.58|4.27
1U146800||IP|01/01/2015|8.86|4.38
1U146800||IR|02/01/2023|8.86|4.39
1U146800||IR|02/01/2022|8.86|4.38
1U146800||IR|02/01/2021|8.58|4.27
1U146800||IR|07/01/2020|8.58|4.27
1U146800||IR|01/01/2015|8.86|4.38
1U146800||IX|09/01/2023|7.56|3.88
1U146800||IX|09/01/2022|7.71|3.93
1U146800||IX|02/01/2022|7.43|3.82
1U146800||IX|01/01/2015|7.41|3.82
1U146800|R|IP|02/01/2023|8.86|4.39
1U146800|R|IP|02/01/2023|8.86|4.39
1U146800|R|IP|02/01/2022|8.86|4.38
1U146800|R|IP|02/01/2021|8.58|4.27
1U146800|R|IP|07/01/2020|8.58|4.27
1U146800|R|IP|01/01/2015|8.86|4.38
1U146800|R|IR|02/01/2023|8.86|4.39
1U146800|R|IR|02/01/2022|8.86|4.38
1U146800|R|IR|02/01/2021|8.58|4.27
1U146800|R|IR|07/01/2020|8.58|4.27
1U146800|R|IR|01/01/2015|8.86|4.38
1U146800|R|IX|09/01/2023|7.56|3.88
1U146800|R|IX|09/01/2022|7.71|3.93
1U146800|R|IX|02/01/2022|7.43|3.82
1U146800|R|IX|01/01/2015|7.41|3.82
1U146900||IX|03/01/2025|6.90|3.90
1U146900||IX|02/01/2023|6.90|3.56
1U146900||IX|02/01/2023|6.90|3.56
1U146900||IX|02/01/2022|6.90|3.55
1U146900||IX|03/01/2021|6.85|3.55
1U146900||IX|01/02/2017|6.98|3.62
1U146900||IX|01/01/2015|6.98|3.62
1U146900|R|IX|03/01/2026|7.04|3.97
1U146900|R|IX|03/01/2025|6.90|3.90
1U146900|R|IX|02/01/2023|6.90|3.56
1U146900|R|IX|02/01/2022|6.90|3.55
1U146900|R|IX|03/01/2021|6.85|3.55
1U146900|R|IX|01/02/2017|6.98|3.62
1U146900|R|IX|01/01/2015|6.98|3.62
1U147400||IX|03/01/2025|7.30|4.13
1U147400||IX|09/01/2023|7.30|3.76
1U147400||IX|01/01/2023|7.43|3.82
1U147400||IX|09/01/2022|7.18|3.69
1U147400||IX|09/01/2022|7.18|3.69
1U147400||IX|02/01/2022|6.90|3.55
1U147400||IX|01/01/2017|6.85|3.55
1U147400|R|IX|03/01/2025|7.30|4.13
1U147400|R|IX|09/01/2023|7.30|3.76
1U147400|R|IX|01/01/2023|7.43|3.82
1U147400|R|IX|09/01/2022|7.18|3.69
1U147400|R|IX|02/01/2022|6.90|3.55
1U147400|R|IX|01/01/2017|6.85|3.55
1U147500||IX|03/01/2025|7.86|4.40
1U147500||IX|09/01/2023|7.86|3.99
1U147500||IX|02/01/2023|8.00|4.05
1U147500||IX|01/01/2023|8.00|4.04
1U147500||IX|09/01/2022|7.71|3.93
1U147500||IX|02/01/2022|7.43|3.82
1U147500||IX|01/02/2017|9.13|4.49
1U147500||IX|01/02/2017|9.13|4.49
1U147500|R|IX|03/01/2025|7.86|4.40
1U147500|R|IX|09/01/2023|7.86|3.99
1U147500|R|IX|02/01/2023|8.00|4.05
1U147500|R|IX|01/01/2023|8.00|4.04
1U147500|R|IX|09/01/2022|7.71|3.93
1U147500|R|IX|02/01/2022|7.43|3.82
1U147500|R|IX|01/02/2017|9.13|4.49
1U147800||IX|03/01/2025|7.71|4.33
1U147800||IX|09/01/2023|7.71|3.93
1U147800||IX|04/01/2023|7.86|3.99
1U147800||IX|01/01/2017|8.00|4.05
1U147800|R|IX|03/01/2025|7.71|4.33
1U147800|R|IX|09/01/2023|7.71|3.93
1U147800|R|IX|04/01/2023|7.86|3.99
1U147800|R|IX|01/01/2017|8.00|4.05
1U147800|R|IX|01/01/2017|8.00|4.05
1U147900||IX|03/01/2025|7.43|4.20
1U147900||IX|05/01/2024|7.43|3.82
1U147900||IX|01/01/2017|9.87|2.34
1U147900|R|IX|03/01/2025|7.43|4.20
1U147900|R|IX|05/01/2024|7.43|3.82
1U147900|R|IX|01/01/2017|9.87|2.34
1U148000||IX|03/01/2025|7.43|4.20
1U148000||IX|05/01/2024|7.43|3.82
1U148000||IX|01/01/2017|8.76|3.45
1U148000|R|IX|03/01/2025|7.43|4.20
1U148000|R|IX|05/01/2024|7.43|3.82
1U148000|R|IX|01/01/2017|8.76|3.45
1U148100||IX|03/01/2025|7.43|4.20
1U148100||IX|05/01/2024|7.43|3.82
1U148100||IX|01/01/2017|7.65|4.56
1U148100||IX|01/01/2017|7.65|4.56
1U148100|R|IX|03/01/2025|7.43|4.20
1U148100|R|IX|05/01/2024|7.43|3.82
1U148100|R|IX|01/01/2017|7.65|4.56
"""

CREATE_SQL = f"""
CREATE TABLE [dbo].[{TABLE_NAME}] (
    [PLAN_ID]           VARCHAR(10)  NOT NULL,
    [REIN_BLOCK_IND]    VARCHAR(2)   NOT NULL,
    [FUND_ID]           VARCHAR(4)   NOT NULL,
    [EFFECTIVE_DATE]    DATE         NOT NULL,
    [MAX_GEOMETRIC_AVG] DECIMAL(9, 6) NOT NULL,
    [MIN_GEOMETRIC_AVG] DECIMAL(9, 6) NOT NULL,
    CONSTRAINT [PK_{TABLE_NAME}] PRIMARY KEY CLUSTERED
        ([PLAN_ID], [REIN_BLOCK_IND], [FUND_ID], [EFFECTIVE_DATE])
)
""".strip()

EXISTS_SQL = (
    "SELECT COUNT(*) FROM sys.objects "
    "WHERE object_id = OBJECT_ID(?) AND type = 'U'"
)
DELETE_SQL = (
    f"DELETE FROM [dbo].[{TABLE_NAME}] "
    "WHERE [PLAN_ID] = ? AND [REIN_BLOCK_IND] = ? "
    "AND [FUND_ID] = ? AND [EFFECTIVE_DATE] = ?"
)
INSERT_SQL = (
    f"INSERT INTO [dbo].[{TABLE_NAME}] "
    "([PLAN_ID], [REIN_BLOCK_IND], [FUND_ID], [EFFECTIVE_DATE], "
    "[MAX_GEOMETRIC_AVG], [MIN_GEOMETRIC_AVG]) "
    "VALUES (?, ?, ?, ?, ?, ?)"
)


def parse_rate(token: str) -> float:
    """Convert a percentage number to the decimal rate stored in UL_Rates."""
    return round(float(token.strip().removesuffix("%")) / 100.0, 6)


def parse_rows() -> Tuple[List[Row], List[dict], List[dict]]:
    """Parse, normalize, and deduplicate the embedded source rows."""
    rows_by_key: dict[Key, Row] = {}
    errors: List[dict] = []
    duplicates: List[dict] = []
    lines = [line for line in RAW_DATA.splitlines() if line.strip()]

    for lineno, line in enumerate(lines[1:], start=2):
        parts = [part.strip() for part in line.split("|")]
        if len(parts) != 6:
            errors.append({
                "line": lineno,
                "text": line,
                "error": f"expected 6 fields, got {len(parts)}",
            })
            continue

        plan_id, rein_block_ind, fund_id, effective_s, max_s, min_s = parts
        try:
            effective_date = datetime.strptime(
                effective_s, "%m/%d/%Y"
            ).date()
            maximum = parse_rate(max_s)
            minimum = parse_rate(min_s)
        except ValueError as exc:
            errors.append({
                "line": lineno,
                "text": line,
                "error": str(exc),
            })
            continue
        if not plan_id or not fund_id:
            errors.append({
                "line": lineno,
                "text": line,
                "error": "PLAN_ID and FUND_ID are required",
            })
            continue
        if maximum < minimum:
            errors.append({
                "line": lineno,
                "text": line,
                "error": "MAX_GEOMETRIC_AVG cannot be below MIN_GEOMETRIC_AVG",
            })
            continue

        row = (
            plan_id.upper(),
            rein_block_ind.upper(),
            fund_id.upper(),
            effective_date,
            maximum,
            minimum,
        )
        key = row[:4]
        prior = rows_by_key.get(key)
        if prior is None:
            rows_by_key[key] = row
        elif prior == row:
            duplicates.append({"line": lineno, "key": list(key)})
        else:
            errors.append({
                "line": lineno,
                "text": line,
                "error": f"conflicting duplicate key {key}",
            })

    return list(rows_by_key.values()), errors, duplicates


def summarize(rows: List[Row], duplicates: List[dict]) -> dict:
    return {
        "source_row_count": len(rows) + len(duplicates),
        "unique_row_count": len(rows),
        "exact_duplicates_collapsed": len(duplicates),
        "distinct_plancodes": sorted({row[0] for row in rows}),
        "distinct_rein_block_ind": sorted({row[1] for row in rows}),
        "distinct_funds": sorted({row[2] for row in rows}),
        "effective_date_range": [
            min(row[3] for row in rows).isoformat(),
            max(row[3] for row in rows).isoformat(),
        ] if rows else [],
        "minimum_rate": min(row[5] for row in rows) if rows else None,
        "maximum_rate": max(row[4] for row in rows) if rows else None,
    }


def load_live(rows: List[Row], dsn: str) -> dict:
    """Create the table if missing and replace supplied keys atomically."""
    import pyodbc

    conn = pyodbc.connect(f"DSN={dsn}", autocommit=False, timeout=10)
    try:
        cur = conn.cursor()
        cur.execute(EXISTS_SQL, (f"dbo.{TABLE_NAME}",))
        created = cur.fetchone()[0] == 0
        if created:
            cur.execute(CREATE_SQL)

        cur.fast_executemany = True
        keys = [row[:4] for row in rows]
        cur.executemany(DELETE_SQL, keys)
        cur.executemany(INSERT_SQL, rows)
        conn.commit()
        return {"table_created": created, "rows_upserted": len(rows)}
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def verify_live(dsn: str) -> dict:
    """Read the table back and report schema and data-integrity checks."""
    import pyodbc

    conn = pyodbc.connect(f"DSN={dsn}", autocommit=True, timeout=10)
    try:
        cur = conn.cursor()
        schema = [
            {
                "column": str(column.column_name),
                "type": str(column.type_name),
                "size": column.column_size,
                "scale": column.decimal_digits,
                "nullable": bool(column.nullable),
            }
            for column in cur.columns(table=TABLE_NAME)
        ]

        cur.execute(f"SELECT COUNT(*) FROM [dbo].[{TABLE_NAME}]")
        row_count = cur.fetchone()[0]
        cur.execute(
            f"SELECT COUNT(*) FROM ("
            f"SELECT [PLAN_ID], [REIN_BLOCK_IND], [FUND_ID], [EFFECTIVE_DATE] "
            f"FROM [dbo].[{TABLE_NAME}] "
            f"GROUP BY [PLAN_ID], [REIN_BLOCK_IND], [FUND_ID], [EFFECTIVE_DATE] "
            f"HAVING COUNT(*) > 1"
            f") duplicate_keys"
        )
        duplicate_key_count = cur.fetchone()[0]

        null_counts = {}
        for column in (
            "PLAN_ID",
            "REIN_BLOCK_IND",
            "FUND_ID",
            "EFFECTIVE_DATE",
            "MAX_GEOMETRIC_AVG",
            "MIN_GEOMETRIC_AVG",
        ):
            cur.execute(
                f"SELECT COUNT(*) FROM [dbo].[{TABLE_NAME}] "
                f"WHERE [{column}] IS NULL"
            )
            null_counts[column] = cur.fetchone()[0]

        cur.execute(
            f"SELECT [PLAN_ID], COUNT(*) FROM [dbo].[{TABLE_NAME}] "
            f"GROUP BY [PLAN_ID] ORDER BY [PLAN_ID]"
        )
        rows_by_plan = {str(row[0]): row[1] for row in cur.fetchall()}

        cur.execute(
            f"SELECT MIN([EFFECTIVE_DATE]), MAX([EFFECTIVE_DATE]), "
            f"MIN([MIN_GEOMETRIC_AVG]), MAX([MAX_GEOMETRIC_AVG]) "
            f"FROM [dbo].[{TABLE_NAME}]"
        )
        ranges = cur.fetchone()

        checks = [
            ("1U145600", "R", "IX", "2026-03-01"),
            ("1U146800", "", "IP", "2023-02-01"),
            ("1U148100", "", "IX", "2017-01-01"),
        ]
        spot_checks = []
        for key in checks:
            cur.execute(
                f"SELECT [PLAN_ID], [REIN_BLOCK_IND], [FUND_ID], "
                f"[EFFECTIVE_DATE], [MAX_GEOMETRIC_AVG], [MIN_GEOMETRIC_AVG] "
                f"FROM [dbo].[{TABLE_NAME}] "
                f"WHERE [PLAN_ID] = ? AND [REIN_BLOCK_IND] = ? "
                f"AND [FUND_ID] = ? AND [EFFECTIVE_DATE] = ?",
                key,
            )
            row = cur.fetchone()
            spot_checks.append(None if row is None else {
                "PLAN_ID": row[0],
                "REIN_BLOCK_IND": row[1],
                "FUND_ID": row[2],
                "EFFECTIVE_DATE": str(row[3]),
                "MAX_GEOMETRIC_AVG": float(row[4]),
                "MIN_GEOMETRIC_AVG": float(row[5]),
            })

        return {
            "schema": schema,
            "row_count": row_count,
            "duplicate_key_count": duplicate_key_count,
            "null_counts": null_counts,
            "rows_by_plan": rows_by_plan,
            "effective_date_range": [str(ranges[0]), str(ranges[1])],
            "rate_range": [float(ranges[2]), float(ranges[3])],
            "spot_checks": spot_checks,
        }
    finally:
        conn.close()


def parse_config(args: List[str]) -> dict:
    """Parse JSON config or Windows-friendly live-load flags."""
    if not args:
        return {"dry_run": True, "dsn": DEFAULT_DSN}

    first = args[0]
    if first.startswith("{"):
        return json.loads(first)
    if first == "--live":
        return {"dry_run": False, "dsn": DEFAULT_DSN}
    if first.startswith("--dsn="):
        dsn = first.partition("=")[2].strip()
        if not dsn:
            raise ValueError("--dsn requires a non-empty DSN name")
        return {"dry_run": False, "dsn": dsn}
    raise ValueError(
        "Expected no arguments, JSON config, --live, or --dsn=<name>"
    )


def main() -> None:
    config = parse_config(sys.argv[1:])
    dry_run = bool(config.get("dry_run", True))
    dsn = str(config.get("dsn", DEFAULT_DSN))

    rows, errors, duplicates = parse_rows()
    result = {
        "table": TABLE_NAME,
        "dsn": dsn,
        "dry_run": dry_run,
        "parse_errors": errors,
        "duplicates": duplicates,
        "summary": summarize(rows, duplicates),
    }

    if errors:
        result["status"] = "parse_error"
    elif dry_run:
        result["status"] = "dry_run_ok"
    else:
        result.update(load_live(rows, dsn))
        result["verification"] = verify_live(dsn)
        result["status"] = "loaded"

    print(json.dumps(result, indent=2, default=str))
    if errors:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
