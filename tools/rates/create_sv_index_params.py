"""Create and populate SV_INDEX_PARAMS in the UL_Rates SQL Server DB.

SV_INDEX_PARAMS holds per-fund index account parameters (floor, cap,
participation, spread, specified rate, multiplier, asset fee) used by the RERUN
illustration app. Rows are keyed by (Plancode, RGA_Ind, Fund_ID); DATE is the
effective date. No column allows NULL — a blank RGA_Ind is stored as ''.

The source data below is embedded verbatim as pipe-delimited text so it stays
auditable against what was provided. Percent tokens are normalized to decimal
fractions (``9.75%`` -> ``0.0975``; ``220.00%`` -> ``2.2``; ``999.99%`` ->
``9.9999``).

This targets the live UL_Rates database (work laptop only — the minipc cannot
reach SQL Server). Use a dry run to verify parsing without touching the DB.

Usage:
    # Dry run (no DB connection) — verify parsing/normalization:
    venv\\Scripts\\python.exe tools\\create_sv_index_params.py
    venv\\Scripts\\python.exe tools\\create_sv_index_params.py "{\"dry_run\": true}"

    # Live: create table (if missing) + upsert rows, then commit:
    venv\\Scripts\\python.exe tools\\create_sv_index_params.py "{\"dsn\": \"UL_Rates\"}"

Output: a JSON summary written to stdout.
"""

from __future__ import annotations

import json
import sys
from datetime import date, datetime
from typing import List, Tuple

TABLE_NAME = "SV_INDEX_PARAMS"
DEFAULT_DSN = "UL_Rates"

Row = Tuple[date, str, str, str, float, float, float, float, float, float, float]

# DATE|Plancode|RGA_Ind|Fund_ID|FLOOR|CAP|PARTICIPATION|INT_RATE_SPREAD|SPECIFIED_RATE|MULTIPLIER|ASSET_FEE
# (blank RGA_Ind stays empty between two pipes; stored as '' — never NULL)
RAW_DATA = """\
DATE|Plancode|RGA_Ind|Fund_ID|FLOOR|CAP|PARTICIPATION|INT_RATE_SPREAD|SPECIFIED_RATE|MULTIPLIER|ASSET_FEE
9/1/2023|1U144600||IX|0.00%|9.75%|100.00%|0.00%|0.00%|0.00%|0.00%
9/1/2023|1U144600|R|IX|0.00%|9.75%|100.00%|0.00%|0.00%|0.00%|0.00%
9/1/2023|1U144700||IX|0.00%|9.75%|100.00%|0.00%|0.00%|0.00%|0.00%
9/1/2023|1U144700|R|IX|0.00%|9.75%|100.00%|0.00%|0.00%|0.00%|0.00%
9/1/2023|1U144800||IX|0.00%|9.75%|100.00%|0.00%|0.00%|0.00%|0.00%
9/1/2023|1U144800|R|IX|0.00%|9.75%|100.00%|0.00%|0.00%|0.00%|0.00%
9/1/2022|1U145500||IC|1.50%|8.50%|100.00%|0.00%|0.00%|0.00%|0.00%
8/1/2023|1U145500||IF|0.00%|999.99%|100.00%|8.00%|0.00%|0.00%|0.00%
9/1/2015|1U145500||IS|0.00%|999.99%|100.00%|0.00%|7.50%|0.00%|0.00%
9/1/2023|1U145500||IX|0.00%|9.75%|100.00%|0.00%|0.00%|0.00%|0.00%
9/1/2022|1U145500|R|IC|1.50%|8.50%|100.00%|0.00%|0.00%|0.00%|0.00%
8/1/2023|1U145500|R|IF|0.00%|999.99%|100.00%|8.00%|0.00%|0.00%|0.00%
9/1/2015|1U145500|R|IS|0.00%|999.99%|100.00%|0.00%|7.50%|0.00%|0.00%
9/1/2023|1U145500|R|IX|0.00%|9.75%|100.00%|0.00%|0.00%|0.00%|0.00%
1/1/2026|1U145600||IC|1.50%|7.75%|100.00%|0.00%|0.00%|0.00%|0.00%
1/1/2026|1U145600||IF|0.00%|999.99%|100.00%|8.50%|0.00%|0.00%|0.00%
1/1/2026|1U145600||IS|0.00%|999.99%|100.00%|0.00%|7.45%|0.00%|0.00%
1/1/2026|1U145600||IX|0.00%|9.50%|100.00%|0.00%|0.00%|0.00%|0.00%
9/1/2023|1U145600|R|IC|1.50%|7.00%|100.00%|0.00%|0.00%|0.00%|0.00%
1/1/2026|1U145600|R|IF|0.00%|999.99%|100.00%|9.20%|0.00%|0.00%|0.00%
12/1/2024|1U145600|R|IS|0.00%|999.99%|100.00%|0.00%|6.85%|0.00%|0.00%
3/1/2021|1U145600|R|IX|0.00%|8.50%|100.00%|0.00%|0.00%|0.00%|0.00%
9/1/2022|1U145800||IC|1.50%|6.00%|100.00%|0.00%|0.00%|0.00%|0.00%
8/1/2023|1U145800||IF|0.00%|999.99%|100.00%|9.00%|0.00%|0.00%|0.00%
6/1/2019|1U145800||IS|0.00%|999.99%|100.00%|0.00%|6.00%|0.00%|0.00%
9/1/2023|1U145800||IX|0.00%|7.25%|100.00%|0.00%|0.00%|0.00%|0.00%
9/1/2022|1U145800|R|IC|1.50%|6.00%|100.00%|0.00%|0.00%|0.00%|0.00%
8/1/2023|1U145800|R|IF|0.00%|999.99%|100.00%|9.00%|0.00%|0.00%|0.00%
6/1/2019|1U145800|R|IS|0.00%|999.99%|100.00%|0.00%|6.00%|0.00%|0.00%
9/1/2023|1U145800|R|IX|0.00%|7.25%|100.00%|0.00%|0.00%|0.00%|0.00%
9/1/2023|1U145900||IC|1.50%|5.75%|100.00%|0.00%|0.00%|0.00%|0.00%
9/1/2023|1U145900||IF|0.00%|999.99%|100.00%|8.70%|0.00%|0.00%|0.00%
12/1/2024|1U145900||IS|0.00%|999.99%|100.00%|0.00%|6.00%|0.00%|0.00%
9/1/2023|1U145900||IX|0.00%|7.75%|100.00%|0.00%|0.00%|0.00%|0.00%
9/1/2023|1U145900|R|IC|1.50%|5.75%|100.00%|0.00%|0.00%|0.00%|0.00%
1/1/2026|1U145900|R|IF|0.00%|999.99%|100.00%|10.30%|0.00%|0.00%|0.00%
12/1/2024|1U145900|R|IS|0.00%|999.99%|100.00%|0.00%|6.00%|0.00%|0.00%
9/1/2023|1U145900|R|IX|0.00%|7.75%|100.00%|0.00%|0.00%|0.00%|0.00%
9/1/2022|1U146400||IC|1.50%|8.50%|100.00%|0.00%|0.00%|0.00%|0.00%
8/1/2023|1U146400||IF|0.00%|999.99%|100.00%|8.00%|0.00%|0.00%|0.00%
9/1/2015|1U146400||IS|0.00%|999.99%|100.00%|0.00%|7.50%|0.00%|0.00%
9/1/2023|1U146400||IX|0.00%|9.75%|100.00%|0.00%|0.00%|0.00%|0.00%
9/1/2022|1U146400|R|IC|1.50%|8.50%|100.00%|0.00%|0.00%|0.00%|0.00%
8/1/2023|1U146400|R|IF|0.00%|999.99%|100.00%|8.00%|0.00%|0.00%|0.00%
9/1/2015|1U146400|R|IS|0.00%|999.99%|100.00%|0.00%|7.50%|0.00%|0.00%
9/1/2023|1U146400|R|IX|0.00%|9.75%|100.00%|0.00%|0.00%|0.00%|0.00%
11/1/2019|1U146500||IC|1.50%|7.25%|100.00%|0.00%|0.00%|0.00%|0.00%
11/1/2019|1U146500||IF|0.00%|999.99%|100.00%|7.25%|0.00%|0.00%|0.00%
11/1/2019|1U146500||IS|0.00%|999.99%|100.00%|0.00%|7.20%|0.00%|0.00%
11/1/2019|1U146500||IX|0.00%|9.25%|100.00%|0.00%|0.00%|0.00%|0.00%
11/1/2019|1U146500|R|IC|1.50%|7.25%|100.00%|0.00%|0.00%|0.00%|0.00%
11/1/2019|1U146500|R|IF|0.00%|999.99%|100.00%|7.25%|0.00%|0.00%|0.00%
11/1/2019|1U146500|R|IS|0.00%|999.99%|100.00%|0.00%|7.20%|0.00%|0.00%
11/1/2019|1U146500|R|IX|0.00%|9.25%|100.00%|0.00%|0.00%|0.00%|0.00%
8/1/2023|1U146800||IF|0.00%|999.99%|100.00%|8.00%|0.00%|0.00%|0.00%
4/1/2023|1U146800||IP|0.00%|12.00%|100.00%|0.00%|0.00%|24.00%|2.15%
4/1/2023|1U146800||IR|0.00%|12.00%|100.00%|0.00%|0.00%|60.00%|4.15%
9/1/2023|1U146800||IX|0.00%|9.75%|100.00%|0.00%|0.00%|0.00%|0.00%
8/1/2023|1U146800|R|IF|0.00%|999.99%|100.00%|8.00%|0.00%|0.00%|0.00%
4/1/2023|1U146800|R|IP|0.00%|12.00%|100.00%|0.00%|0.00%|24.00%|2.15%
4/1/2023|1U146800|R|IR|0.00%|12.00%|100.00%|0.00%|0.00%|60.00%|4.15%
9/1/2023|1U146800|R|IX|0.00%|9.75%|100.00%|0.00%|0.00%|0.00%|0.00%
1/1/2026|1U146900||IC|1.50%|7.75%|100.00%|0.00%|0.00%|0.00%|0.00%
1/1/2026|1U146900||IF|0.00%|999.99%|100.00%|8.50%|0.00%|0.00%|0.00%
1/1/2026|1U146900||IS|0.00%|999.99%|100.00%|0.00%|7.45%|0.00%|0.00%
1/1/2026|1U146900||IX|0.00%|9.50%|100.00%|0.00%|0.00%|0.00%|0.00%
9/1/2023|1U146900|R|IC|1.50%|7.00%|100.00%|0.00%|0.00%|0.00%|0.00%
1/1/2026|1U146900|R|IF|0.00%|999.99%|100.00%|9.20%|0.00%|0.00%|0.00%
12/1/2024|1U146900|R|IS|0.00%|999.99%|100.00%|0.00%|6.85%|0.00%|0.00%
3/1/2021|1U146900|R|IX|0.00%|8.50%|100.00%|0.00%|0.00%|0.00%|0.00%
8/1/2023|1U147400||IF|0.00%|999.99%|100.00%|9.00%|0.00%|0.00%|0.00%
9/1/2023|1U147400||IX|0.00%|9.25%|100.00%|0.00%|0.00%|0.00%|0.00%
4/1/2023|1U147400||M1|0.00%|999.99%|220.00%|0.00%|0.00%|0.00%|0.00%
9/1/2023|1U147400||NX|0.00%|9.25%|100.00%|0.00%|0.00%|0.00%|0.00%
8/1/2023|1U147400|R|IF|0.00%|999.99%|100.00%|9.00%|0.00%|0.00%|0.00%
9/1/2023|1U147400|R|IX|0.00%|9.25%|100.00%|0.00%|0.00%|0.00%|0.00%
4/1/2023|1U147400|R|M1|0.00%|999.99%|220.00%|0.00%|0.00%|0.00%|0.00%
9/1/2023|1U147400|R|NX|0.00%|9.25%|100.00%|0.00%|0.00%|0.00%|0.00%
8/1/2023|1U147500||IF|0.00%|999.99%|100.00%|8.00%|0.00%|0.00%|0.00%
4/1/2023|1U147500||IP|0.00%|12.00%|100.00%|0.00%|0.00%|24.00%|2.15%
4/1/2023|1U147500||IR|0.00%|12.00%|100.00%|0.00%|0.00%|60.00%|4.15%
9/1/2023|1U147500||IX|0.00%|10.25%|100.00%|0.00%|0.00%|0.00%|0.00%
4/1/2023|1U147500||M1|0.00%|999.99%|240.00%|0.00%|0.00%|0.00%|0.00%
9/1/2023|1U147500||NX|0.00%|10.25%|100.00%|0.00%|0.00%|0.00%|0.00%
8/1/2023|1U147500|R|IF|0.00%|999.99%|100.00%|8.00%|0.00%|0.00%|0.00%
4/1/2023|1U147500|R|IP|0.00%|12.00%|100.00%|0.00%|0.00%|24.00%|2.15%
4/1/2023|1U147500|R|IR|0.00%|12.00%|100.00%|0.00%|0.00%|60.00%|4.15%
9/1/2023|1U147500|R|IX|0.00%|10.25%|100.00%|0.00%|0.00%|0.00%|0.00%
4/1/2023|1U147500|R|M1|0.00%|999.99%|240.00%|0.00%|0.00%|0.00%|0.00%
9/1/2023|1U147500|R|NX|0.00%|10.25%|100.00%|0.00%|0.00%|0.00%|0.00%
8/1/2023|1U147800||IF|0.00%|999.99%|100.00%|8.00%|0.00%|0.00%|0.00%
4/1/2023|1U147800||IP|0.00%|12.00%|100.00%|0.00%|0.00%|24.00%|2.15%
4/1/2023|1U147800||IR|0.00%|12.00%|100.00%|0.00%|0.00%|60.00%|4.15%
9/1/2023|1U147800||IX|0.00%|10.00%|100.00%|0.00%|0.00%|0.00%|0.00%
4/1/2023|1U147800||M1|0.00%|999.99%|240.00%|0.00%|0.00%|0.00%|0.00%
9/1/2023|1U147800||NX|0.00%|10.00%|100.00%|0.00%|0.00%|0.00%|0.00%
8/1/2023|1U147800|R|IF|0.00%|999.99%|100.00%|8.00%|0.00%|0.00%|0.00%
4/1/2023|1U147800|R|IP|0.00%|12.00%|100.00%|0.00%|0.00%|24.00%|2.15%
4/1/2023|1U147800|R|IR|0.00%|12.00%|100.00%|0.00%|0.00%|60.00%|4.15%
9/1/2023|1U147800|R|IX|0.00%|10.00%|100.00%|0.00%|0.00%|0.00%|0.00%
4/1/2023|1U147800|R|M1|0.00%|999.99%|240.00%|0.00%|0.00%|0.00%|0.00%
9/1/2023|1U147800|R|NX|0.00%|10.00%|100.00%|0.00%|0.00%|0.00%|0.00%
5/1/2024|1U147900||IF|0.00%|999.99%|100.00%|9.00%|0.00%|0.00%|0.00%
5/1/2024|1U147900||IX|0.00%|9.50%|100.00%|0.00%|0.00%|0.00%|0.00%
5/1/2024|1U147900||M1|0.00%|999.99%|220.00%|0.00%|0.00%|0.00%|0.00%
5/1/2024|1U147900||NX|0.00%|9.50%|100.00%|0.00%|0.00%|0.00%|0.00%
5/1/2024|1U147900|R|IF|0.00%|999.99%|100.00%|9.00%|0.00%|0.00%|0.00%
5/1/2024|1U147900|R|IX|0.00%|9.50%|100.00%|0.00%|0.00%|0.00%|0.00%
5/1/2024|1U147900|R|M1|0.00%|999.99%|220.00%|0.00%|0.00%|0.00%|0.00%
5/1/2024|1U147900|R|NX|0.00%|9.50%|100.00%|0.00%|0.00%|0.00%|0.00%
5/1/2024|1U148000||IF|0.00%|999.99%|100.00%|9.00%|0.00%|0.00%|0.00%
5/1/2024|1U148000||IX|0.00%|9.50%|100.00%|0.00%|0.00%|0.00%|0.00%
5/1/2024|1U148000||M1|0.00%|999.99%|220.00%|0.00%|0.00%|0.00%|0.00%
5/1/2024|1U148000||NX|0.00%|9.50%|100.00%|0.00%|0.00%|0.00%|0.00%
5/1/2024|1U148000|R|IF|0.00%|999.99%|100.00%|9.00%|0.00%|0.00%|0.00%
5/1/2024|1U148000|R|IX|0.00%|9.50%|100.00%|0.00%|0.00%|0.00%|0.00%
5/1/2024|1U148000|R|M1|0.00%|999.99%|220.00%|0.00%|0.00%|0.00%|0.00%
5/1/2024|1U148000|R|NX|0.00%|9.50%|100.00%|0.00%|0.00%|0.00%|0.00%
5/1/2024|1U148100||IF|0.00%|999.99%|100.00%|9.00%|0.00%|0.00%|0.00%
5/1/2024|1U148100||IX|0.00%|9.50%|100.00%|0.00%|0.00%|0.00%|0.00%
5/1/2024|1U148100||M1|0.00%|999.99%|220.00%|0.00%|0.00%|0.00%|0.00%
5/1/2024|1U148100||NX|0.00%|9.50%|100.00%|0.00%|0.00%|0.00%|0.00%
5/1/2024|1U148100|R|IF|0.00%|999.99%|100.00%|9.00%|0.00%|0.00%|0.00%
5/1/2024|1U148100|R|IX|0.00%|9.50%|100.00%|0.00%|0.00%|0.00%|0.00%
5/1/2024|1U148100|R|M1|0.00%|999.99%|220.00%|0.00%|0.00%|0.00%|0.00%
5/1/2024|1U148100|R|NX|0.00%|9.50%|100.00%|0.00%|0.00%|0.00%|0.00%
"""

# Percent columns in positional order after the four key/date fields.
RATE_COLUMNS = (
    "FLOOR", "CAP", "PARTICIPATION", "INT_RATE_SPREAD",
    "SPECIFIED_RATE", "MULTIPLIER", "ASSET_FEE",
)

CREATE_SQL = f"""
CREATE TABLE [dbo].[{TABLE_NAME}] (
    [DATE]            DATE          NOT NULL,
    [Plancode]        VARCHAR(10)   NOT NULL,
    [RGA_Ind]         VARCHAR(2)    NOT NULL,
    [Fund_ID]         VARCHAR(4)    NOT NULL,
    [FLOOR]           DECIMAL(9, 6) NOT NULL,
    [CAP]             DECIMAL(9, 6) NOT NULL,
    [PARTICIPATION]   DECIMAL(9, 6) NOT NULL,
    [INT_RATE_SPREAD] DECIMAL(9, 6) NOT NULL,
    [SPECIFIED_RATE]  DECIMAL(9, 6) NOT NULL,
    [MULTIPLIER]      DECIMAL(9, 6) NOT NULL,
    [ASSET_FEE]       DECIMAL(9, 6) NOT NULL,
    CONSTRAINT [PK_{TABLE_NAME}] PRIMARY KEY CLUSTERED
        ([Plancode], [RGA_Ind], [Fund_ID])
)
""".strip()

EXISTS_SQL = "SELECT COUNT(*) FROM sys.objects WHERE object_id = OBJECT_ID(?) AND type = 'U'"

DELETE_SQL = (
    f"DELETE FROM [dbo].[{TABLE_NAME}] "
    "WHERE [Plancode] = ? AND [RGA_Ind] = ? AND [Fund_ID] = ?"
)

INSERT_SQL = (
    f"INSERT INTO [dbo].[{TABLE_NAME}] "
    "([DATE], [Plancode], [RGA_Ind], [Fund_ID], [FLOOR], [CAP], "
    "[PARTICIPATION], [INT_RATE_SPREAD], [SPECIFIED_RATE], [MULTIPLIER], "
    "[ASSET_FEE]) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)"
)


def parse_pct(token: str) -> float:
    """Normalize a percent token to a decimal fraction (no NULLs allowed)."""
    token = token.strip()
    if token.endswith("%"):
        return round(float(token[:-1]) / 100.0, 6)
    return round(float(token), 6)


def parse_rows() -> Tuple[List[Row], List[dict]]:
    """Parse the embedded pipe-delimited data into typed rows."""
    rows: List[Row] = []
    errors: List[dict] = []
    seen: set = set()
    lines = [line for line in RAW_DATA.splitlines() if line.strip()]
    for lineno, line in enumerate(lines[1:], start=2):  # skip header row
        parts = [part.strip() for part in line.split("|")]
        if len(parts) != 11:
            errors.append({"line": lineno, "text": line,
                           "error": f"expected 11 fields, got {len(parts)}"})
            continue
        date_s, plancode, rga_ind, fund = parts[0], parts[1], parts[2], parts[3]
        try:
            eff = datetime.strptime(date_s, "%m/%d/%Y").date()
        except ValueError as exc:
            errors.append({"line": lineno, "text": line, "error": f"bad DATE: {exc}"})
            continue
        try:
            rates = tuple(parse_pct(tok) for tok in parts[4:])
        except ValueError as exc:
            errors.append({"line": lineno, "text": line, "error": f"bad rate: {exc}"})
            continue

        key = (plancode, rga_ind, fund)
        if key in seen:
            errors.append({"line": lineno, "text": line,
                           "error": f"duplicate key {key}"})
            continue
        seen.add(key)
        rows.append((eff, plancode, rga_ind, fund, *rates))
    return rows, errors


def summarize(rows: List[Row]) -> dict:
    return {
        "row_count": len(rows),
        "distinct_plancodes": sorted({r[1] for r in rows}),
        "distinct_rga_ind": sorted({r[2] for r in rows}),
        "distinct_funds": sorted({r[3] for r in rows}),
        "blank_rga_ind_rows": sum(1 for r in rows if r[2] == ""),
    }


def load_live(rows: List[Row], dsn: str) -> dict:
    """Create the table if missing and upsert every row inside one transaction."""
    import pyodbc  # imported lazily so a dry run needs no driver/DSN

    conn = pyodbc.connect(f"DSN={dsn}", autocommit=False, timeout=10)
    try:
        cur = conn.cursor()
        cur.execute(EXISTS_SQL, (f"dbo.{TABLE_NAME}",))
        created = cur.fetchone()[0] == 0
        if created:
            cur.execute(CREATE_SQL)

        cur.fast_executemany = True
        keys = [(r[1], r[2], r[3]) for r in rows]
        cur.executemany(DELETE_SQL, keys)   # idempotent: replace matching keys
        cur.executemany(INSERT_SQL, rows)
        conn.commit()
        return {"table_created": created, "rows_upserted": len(rows)}
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def main() -> None:
    config = json.loads(sys.argv[1]) if len(sys.argv) > 1 else {}
    dry_run = bool(config.get("dry_run", len(sys.argv) <= 1))
    dsn = str(config.get("dsn", DEFAULT_DSN))

    rows, errors = parse_rows()
    result = {
        "table": TABLE_NAME,
        "dsn": dsn,
        "dry_run": dry_run,
        "parse_errors": errors,
        "summary": summarize(rows),
    }

    if errors:
        result["status"] = "parse_error"
    elif dry_run:
        result["status"] = "dry_run_ok"
    else:
        result.update(load_live(rows, dsn))
        result["status"] = "loaded"

    print(json.dumps(result, indent=2, default=str))


if __name__ == "__main__":
    main()
