"""Create and populate SV_INDEX_MARKET_RETURNS in the UL_Rates SQL Server DB.

SV_INDEX_MARKET_RETURNS holds year-on-year (end-of-year) market index returns
used by the RERUN illustration app. Rows are keyed by (DateEOY, MarketIndex);
OneYrReturn allows NULLs.

The source data below is embedded verbatim as pipe-delimited text so it stays
auditable against what was provided. Return tokens are parsed as plain decimal
fractions; an empty token becomes SQL NULL.

This targets the live UL_Rates database (work laptop only — the minipc cannot
reach SQL Server). Use a dry run to verify parsing without touching the DB.

Usage:
    # Dry run (no DB connection) — verify parsing:
    venv\\Scripts\\python.exe tools\\create_sv_index_market_returns.py
    venv\\Scripts\\python.exe tools\\create_sv_index_market_returns.py "{\"dry_run\": true}"

    # Live: create table (if missing) + upsert rows, then commit:
    venv\\Scripts\\python.exe tools\\create_sv_index_market_returns.py "{\"dsn\": \"UL_Rates\"}"

Output: a JSON summary written to stdout.
"""

from __future__ import annotations

import json
import sys
from datetime import date, datetime
from typing import List, Optional, Tuple

TABLE_NAME = "SV_INDEX_MARKET_RETURNS"
DEFAULT_DSN = "UL_Rates"

Row = Tuple[date, str, Optional[float]]

# DateEOY|MarketIndex|OneYrReturn  (empty return token => NULL)
RAW_DATA = """\
DateEOY|MarketIndex|OneYrReturn
12/31/2006|SP500|0.1362
12/31/2007|SP500|0.0353
12/31/2008|SP500|-0.3849
12/31/2009|SP500|0.2345
12/31/2010|SP500|0.1278
12/31/2011|SP500|0
12/31/2012|SP500|0.1341
12/31/2013|SP500|0.296
12/31/2014|SP500|0.1139
12/31/2015|SP500|-0.0073
12/31/2016|SP500|0.0954
12/31/2017|SP500|0.1942
12/31/2018|SP500|-0.0624
12/31/2019|SP500|0.2888
12/31/2020|SP500|0.1626
12/31/2021|SP500|0.2689
12/31/2022|SP500|-0.1944
12/31/2023|SP500|0.2423
12/31/2024|SP500|0.2331
12/31/2025|SP500|0.1639
12/31/2006|NASDAQ100|0.067894527
12/31/2007|NASDAQ100|0.18670949
12/31/2008|NASDAQ100|-0.41885336
12/31/2009|NASDAQ100|0.535352637
12/31/2010|NASDAQ100|0.192199169
12/31/2011|NASDAQ100|0.027039564
12/31/2012|NASDAQ100|0.168186318
12/31/2013|NASDAQ100|0.349904015
12/31/2014|NASDAQ100|0.179365196
12/31/2015|NASDAQ100|0.084269749
12/31/2016|NASDAQ100|0.058857872
12/31/2017|NASDAQ100|0.315156153
12/31/2018|NASDAQ100|-0.010388578
12/31/2019|NASDAQ100|0.379638453
12/31/2020|NASDAQ100|0.475801729
12/31/2021|NASDAQ100|0.2663
12/31/2022|NASDAQ100|-0.3297
12/31/2023|NASDAQ100|0.5381
12/31/2024|NASDAQ100|0.2488
12/31/2025|NASDAQ100|0.2017
12/31/2006|SPMARC5|0.04689591
12/31/2007|SPMARC5|0.083977102
12/31/2008|SPMARC5|0.010715751
12/31/2009|SPMARC5|0.06914219
12/31/2010|SPMARC5|0.131761245
12/31/2011|SPMARC5|0.111809835
12/31/2012|SPMARC5|0.05953997
12/31/2013|SPMARC5|-0.030784014
12/31/2014|SPMARC5|0.064845414
12/31/2015|SPMARC5|-0.029241379
12/31/2016|SPMARC5|0.043194089
12/31/2017|SPMARC5|0.1071234
12/31/2018|SPMARC5|-0.033001169
12/31/2019|SPMARC5|0.137018543
12/31/2020|SPMARC5|0.082827492
12/31/2021|SPMARC5|0.0028
12/31/2022|SPMARC5|-0.092
12/31/2023|SPMARC5|0.0346
12/31/2024|SPMARC5|0.0387
12/31/2025|SPMARC5|0.103
"""

CREATE_SQL = f"""
CREATE TABLE [dbo].[{TABLE_NAME}] (
    [DateEOY]     DATE          NOT NULL,
    [MarketIndex] VARCHAR(20)   NOT NULL,
    [OneYrReturn] DECIMAL(12, 9) NULL,
    CONSTRAINT [PK_{TABLE_NAME}] PRIMARY KEY CLUSTERED
        ([MarketIndex], [DateEOY])
)
""".strip()

EXISTS_SQL = "SELECT COUNT(*) FROM sys.objects WHERE object_id = OBJECT_ID(?) AND type = 'U'"

DELETE_SQL = (
    f"DELETE FROM [dbo].[{TABLE_NAME}] "
    "WHERE [DateEOY] = ? AND [MarketIndex] = ?"
)

INSERT_SQL = (
    f"INSERT INTO [dbo].[{TABLE_NAME}] "
    "([DateEOY], [MarketIndex], [OneYrReturn]) "
    "VALUES (?, ?, ?)"
)


def parse_return(token: str) -> Optional[float]:
    """Parse a return token to a decimal fraction, or None for a blank cell."""
    token = token.strip()
    if token == "":
        return None
    if token.endswith("%"):
        return round(float(token[:-1]) / 100.0, 9)
    return round(float(token), 9)


def parse_rows() -> Tuple[List[Row], List[dict]]:
    """Parse the embedded pipe-delimited data into typed rows."""
    rows: List[Row] = []
    errors: List[dict] = []
    lines = [line for line in RAW_DATA.splitlines() if line.strip()]
    for lineno, line in enumerate(lines[1:], start=2):  # skip header row
        parts = [part.strip() for part in line.split("|")]
        if len(parts) != 3:
            errors.append({"line": lineno, "text": line,
                           "error": f"expected 3 fields, got {len(parts)}"})
            continue
        eff_s, market_index, ret_s = parts
        try:
            eff = datetime.strptime(eff_s, "%m/%d/%Y").date()
        except ValueError as exc:
            errors.append({"line": lineno, "text": line, "error": f"bad DateEOY: {exc}"})
            continue
        try:
            ret = parse_return(ret_s)
        except ValueError as exc:
            errors.append({"line": lineno, "text": line, "error": f"bad return: {exc}"})
            continue
        rows.append((eff, market_index, ret))
    return rows, errors


def summarize(rows: List[Row]) -> dict:
    return {
        "row_count": len(rows),
        "distinct_indexes": sorted({r[1] for r in rows}),
        "date_range": [
            min(r[0] for r in rows).isoformat(),
            max(r[0] for r in rows).isoformat(),
        ] if rows else [],
        "null_returns": sum(1 for r in rows if r[2] is None),
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
        keys = [(r[0], r[1]) for r in rows]
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
