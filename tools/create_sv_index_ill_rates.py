"""Create and populate the SV_INDEX_ILL_RATES table in the UL_Rates SQL Server DB.

SV_INDEX_ILL_RATES holds per-fund index illustration crediting rates used by the
RERUN illustration app. Rows are keyed by (Company, Plancode, FundID, EffDate);
the two rate columns (Rate_ANICO, Rate_RGA) allow NULLs.

The source data below is embedded verbatim as pipe-delimited text so it stays
auditable against what was provided. Rate tokens are normalized to decimal
fractions: a trailing ``%`` is divided by 100 (``6.10%`` -> ``0.061``); an empty
token becomes SQL NULL; anything else is parsed as a plain decimal.

This targets the live UL_Rates database (work laptop only — the minipc cannot
reach SQL Server). Use a dry run to verify parsing without touching the DB.

Usage:
    # Dry run (no DB connection) — verify parsing/normalization:
    venv\\Scripts\\python.exe tools\\create_sv_index_ill_rates.py
    venv\\Scripts\\python.exe tools\\create_sv_index_ill_rates.py "{\"dry_run\": true}"

    # Live: create table (if missing) + upsert rows, then commit:
    venv\\Scripts\\python.exe tools\\create_sv_index_ill_rates.py "{\"dsn\": \"UL_Rates\"}"

Output: a JSON summary written to stdout.
"""

from __future__ import annotations

import json
import sys
from datetime import date, datetime
from typing import List, Optional, Tuple

TABLE_NAME = "SV_INDEX_ILL_RATES"
DEFAULT_DSN = "UL_Rates"

Row = Tuple[str, str, str, date, Optional[float], Optional[float]]

# Company|Plancode|FundID|EffDate|Rate_ANICO|Rate_RGA  (empty rate token => NULL)
RAW_DATA = """\
Company|Plancode|FundID|EffDate|Rate_ANICO|Rate_RGA
01|1U147900|IX|7/1/2026|6.10%|6.10%
01|1U147900|IF|7/1/2026|4.52%|4.52%
01|1U147900|M1|7/1/2026|5.94%|5.94%
01|1U147900|NX|7/1/2026|5.83%|5.83%
01|1U148000|IX|7/1/2026|6.10%|6.10%
01|1U148000|IF|7/1/2026|4.52%|4.52%
01|1U148000|M1|7/1/2026|5.94%|5.94%
01|1U148000|NX|7/1/2026|5.83%|5.83%
01|1U148100|IX|7/1/2026|6.10%|6.10%
01|1U148100|IF|7/1/2026|4.52%|4.52%
01|1U148100|M1|7/1/2026|5.94%|5.94%
01|1U148100|NX|7/1/2026|5.83%|5.83%
01|1U147800|M1|7/1/2026|6.35%|6.35%
01|1U147800|NX|7/1/2026|6.09%|6.09%
01|1U147800|IX|7/1/2026|6.35%|6.35%
01|1U147800|IF|7/1/2026|5.10%|5.10%
01|1U147800|IR|7/1/2026|6.35%|6.35%
01|1U147800|IP|7/1/2026|6.35%|6.35%
01|1U147400|IX|7/1/2026|5.97%|5.97%
01|1U147400|IF|7/1/2026|4.80%|4.80%
01|1U147400|M1|7/1/2026|5.97%|5.97%
01|1U147400|NX|7/1/2026|5.69%|5.69%
01|1U147500|M1|7/1/2026|6.47%|6.47%
01|1U147500|NX|7/1/2026|6.22%|6.22%
01|1U147500|IX|7/1/2026|6.47%|6.47%
01|1U147500|IF|7/1/2026|5.11%|5.11%
01|1U147500|IR|7/1/2026|6.47%|6.47%
01|1U147500|IP|7/1/2026|6.39%|6.39%
01|1U146800|IX|7/1/2026|6.23%|6.23%
01|1U146800|IF|7/1/2026|6.23%|6.23%
01|1U146800|IR|7/1/2026|6.23%|6.23%
01|1U146800|IP|7/1/2026|6.23%|6.23%
01|1U145500|IX|7/1/2026|6.23%|6.23%
01|1U145500|IC|7/1/2026|5.99%|5.99%
01|1U145500|IF|7/1/2026|6.23%|6.23%
01|1U145500|IS|7/1/2026|5.56%|5.56%
01|1U146400|IX|7/1/2026|6.23%|6.23%
01|1U146400|IC|7/1/2026|5.99%|5.99%
01|1U146400|IF|7/1/2026|6.23%|6.23%
01|1U146400|IS|7/1/2026|5.56%|5.56%
01|1U145800|IX|7/1/2026||0.0487
01|1U145801|IC|7/1/2026||0.0453
01|1U145802|IF|7/1/2026||0.0487
01|1U145803|IS|7/1/2026||0.0445
01|1U144600|IX|7/1/2026|0.0623|0.0623
01|1U144800|IX|7/1/2026|0.0623|0.0623
01|1U144700|IX|7/1/2026|0.0623|0.0623
26|1U146900|IX|7/1/2026|0.0586|0.0554
26|1U146900|IC|7/1/2026|0.0505|0.0482
26|1U146900|IF|7/1/2026|0.0384|0.0348
26|1U146900|IS|7/1/2026|0.0508|0.0486
26|1U145600|IX|7/1/2026|0.061|0.0557
26|1U145600|IC|7/1/2026|0.0557|0.0514
26|1U145600|IF|7/1/2026|0.061|0.0557
26|1U145600|IS|7/1/2026|0.0552|0.0519
26|1U146500|IX|7/1/2026|0.061|0.0557
26|1U146500|IC|7/1/2026|0.0557|0.0514
26|1U146500|IF|7/1/2026|0.061|0.0557
26|1U146500|IS|7/1/2026|0.0552|0.0519
26|1U145900|IX|7/1/2026||0.0516
26|1U145900|IC|7/1/2026||0.0438
26|1U145900|IF|7/1/2026||0.0516
26|1U145900|IS|7/1/2026||0.0445
01|1U147900|IX|8/1/2026|0.061|0.061
01|1U147900|IF|8/1/2026|0.0452|0.0452
01|1U147900|M1|8/1/2026|0.0594|0.0594
01|1U147900|NX|8/1/2026|0.0583|0.0583
01|1U148000|IX|8/1/2026|0.061|0.061
01|1U148000|IF|8/1/2026|0.0452|0.0452
01|1U148000|M1|8/1/2026|0.0594|0.0594
01|1U148000|NX|8/1/2026|0.0583|0.0583
01|1U148100|IX|8/1/2026|0.061|0.061
01|1U148100|IF|8/1/2026|0.0452|0.0452
01|1U148100|M1|8/1/2026|0.0594|0.0594
01|1U148100|NX|8/1/2026|0.0583|0.0583
01|1U147800|M1|8/1/2026|0.0635|0.0635
01|1U147800|NX|8/1/2026|0.0609|0.0609
01|1U147800|IX|8/1/2026|0.0635|0.0635
01|1U147800|IF|8/1/2026|0.051|0.051
01|1U147800|IR|8/1/2026|0.0635|0.0635
01|1U147800|IP|8/1/2026|0.0635|0.0635
01|1U147400|IX|8/1/2026|0.0597|0.0597
01|1U147400|IF|8/1/2026|0.048|0.048
01|1U147400|M1|8/1/2026|0.0597|0.0597
01|1U147400|NX|8/1/2026|0.0569|0.0569
01|1U147500|M1|8/1/2026|0.0647|0.0647
01|1U147500|NX|8/1/2026|0.0622|0.0622
01|1U147500|IX|8/1/2026|0.0647|0.0647
01|1U147500|IF|8/1/2026|0.0511|0.0511
01|1U147500|IR|8/1/2026|0.0647|0.0647
01|1U147500|IP|8/1/2026|0.0639|0.0639
01|1U146800|IX|8/1/2026|0.0623|0.0623
01|1U146800|IF|8/1/2026|0.0623|0.0623
01|1U146800|IR|8/1/2026|0.0623|0.0623
01|1U146800|IP|8/1/2026|0.0623|0.0623
01|1U145500|IX|8/1/2026|0.0623|0.0623
01|1U145500|IC|8/1/2026|0.0599|0.0599
01|1U145500|IF|8/1/2026|0.0623|0.0623
01|1U145500|IS|8/1/2026|0.0556|0.0556
01|1U146400|IX|8/1/2026|0.0623|0.0623
01|1U146400|IC|8/1/2026|0.0599|0.0599
01|1U146400|IF|8/1/2026|0.0623|0.0623
01|1U146400|IS|8/1/2026|0.0556|0.0556
01|1U145800|IX|8/1/2026||0.0487
01|1U145801|IC|8/1/2026||0.0453
01|1U145802|IF|8/1/2026||0.0487
01|1U145803|IS|8/1/2026||0.0445
01|1U144600|IX|8/1/2026|0.0623|0.0623
01|1U144800|IX|8/1/2026|0.0623|0.0623
01|1U144700|IX|8/1/2026|0.0623|0.0623
26|1U146900|IX|8/1/2026|0.0586|0.0554
26|1U146900|IC|8/1/2026|0.0505|0.0482
26|1U146900|IF|8/1/2026|0.0384|0.0348
26|1U146900|IS|8/1/2026|0.0508|0.0486
26|1U145600|IX|8/1/2026|0.061|0.0557
26|1U145600|IC|8/1/2026|0.0557|0.0514
26|1U145600|IF|8/1/2026|0.061|0.0557
26|1U145600|IS|8/1/2026|0.0552|0.0519
26|1U146500|IX|8/1/2026|0.061|0.0557
26|1U146500|IC|8/1/2026|0.0557|0.0514
26|1U146500|IF|8/1/2026|0.061|0.0557
26|1U146500|IS|8/1/2026|0.0552|0.0519
26|1U145900|IX|8/1/2026||0.0516
26|1U145900|IC|8/1/2026||0.0438
26|1U145900|IF|8/1/2026||0.0516
26|1U145900|IS|8/1/2026||0.0445
01|1U147900|IX|9/1/2026|0.061|0.061
01|1U147900|IF|9/1/2026|0.0452|0.0452
01|1U147900|M1|9/1/2026|0.0594|0.0594
01|1U147900|NX|9/1/2026|0.0583|0.0583
01|1U148000|IX|9/1/2026|0.061|0.061
01|1U148000|IF|9/1/2026|0.0452|0.0452
01|1U148000|M1|9/1/2026|0.0594|0.0594
01|1U148000|NX|9/1/2026|0.0583|0.0583
01|1U148100|IX|9/1/2026|0.061|0.061
01|1U148100|IF|9/1/2026|0.0452|0.0452
01|1U148100|M1|9/1/2026|0.0594|0.0594
01|1U148100|NX|9/1/2026|0.0583|0.0583
01|1U147800|M1|9/1/2026|0.0635|0.0635
01|1U147800|NX|9/1/2026|0.0609|0.0609
01|1U147800|IX|9/1/2026|0.0635|0.0635
01|1U147800|IF|9/1/2026|0.051|0.051
01|1U147800|IR|9/1/2026|0.0635|0.0635
01|1U147800|IP|9/1/2026|0.0635|0.0635
01|1U147400|IX|9/1/2026|0.0597|0.0597
01|1U147400|IF|9/1/2026|0.048|0.048
01|1U147400|M1|9/1/2026|0.0597|0.0597
01|1U147400|NX|9/1/2026|0.0569|0.0569
01|1U147500|M1|9/1/2026|0.0647|0.0647
01|1U147500|NX|9/1/2026|0.0622|0.0622
01|1U147500|IX|9/1/2026|0.0647|0.0647
01|1U147500|IF|9/1/2026|0.0511|0.0511
01|1U147500|IR|9/1/2026|0.0647|0.0647
01|1U147500|IP|9/1/2026|0.0639|0.0639
01|1U146800|IX|9/1/2026|0.0623|0.0623
01|1U146800|IF|9/1/2026|0.0623|0.0623
01|1U146800|IR|9/1/2026|0.0623|0.0623
01|1U146800|IP|9/1/2026|0.0623|0.0623
01|1U145500|IX|9/1/2026|0.0623|0.0623
01|1U145500|IC|9/1/2026|0.0599|0.0599
01|1U145500|IF|9/1/2026|0.0623|0.0623
01|1U145500|IS|9/1/2026|0.0556|0.0556
01|1U146400|IX|9/1/2026|0.0623|0.0623
01|1U146400|IC|9/1/2026|0.0599|0.0599
01|1U146400|IF|9/1/2026|0.0623|0.0623
01|1U146400|IS|9/1/2026|0.0556|0.0556
01|1U145800|IX|9/1/2026||0.0487
01|1U145801|IC|9/1/2026||0.0453
01|1U145802|IF|9/1/2026||0.0487
01|1U145803|IS|9/1/2026||0.0445
01|1U144600|IX|9/1/2026|0.0623|0.0623
01|1U144800|IX|9/1/2026|0.0623|0.0623
01|1U144700|IX|9/1/2026|0.0623|0.0623
26|1U146900|IX|9/1/2026|0.0586|0.0554
26|1U146900|IC|9/1/2026|0.0505|0.0482
26|1U146900|IF|9/1/2026|0.0384|0.0348
26|1U146900|IS|9/1/2026|0.0508|0.0486
26|1U145600|IX|9/1/2026|0.061|0.0557
26|1U145600|IC|9/1/2026|0.0557|0.0514
26|1U145600|IF|9/1/2026|0.061|0.0557
26|1U145600|IS|9/1/2026|0.0552|0.0519
26|1U146500|IX|9/1/2026|0.061|0.0557
26|1U146500|IC|9/1/2026|0.0557|0.0514
26|1U146500|IF|9/1/2026|0.061|0.0557
26|1U146500|IS|9/1/2026|0.0552|0.0519
26|1U145900|IX|9/1/2026||0.0516
26|1U145900|IC|9/1/2026||0.0438
26|1U145900|IF|9/1/2026||0.0516
26|1U145900|IS|9/1/2026||0.0445
"""

CREATE_SQL = f"""
CREATE TABLE [dbo].[{TABLE_NAME}] (
    [Company]    VARCHAR(2)   NOT NULL,
    [Plancode]   VARCHAR(10)  NOT NULL,
    [FundID]     VARCHAR(4)   NOT NULL,
    [EffDate]    DATE         NOT NULL,
    [Rate_ANICO] DECIMAL(9, 6) NULL,
    [Rate_RGA]   DECIMAL(9, 6) NULL,
    CONSTRAINT [PK_{TABLE_NAME}] PRIMARY KEY CLUSTERED
        ([Company], [Plancode], [FundID], [EffDate])
)
""".strip()

EXISTS_SQL = "SELECT COUNT(*) FROM sys.objects WHERE object_id = OBJECT_ID(?) AND type = 'U'"

DELETE_SQL = (
    f"DELETE FROM [dbo].[{TABLE_NAME}] "
    "WHERE [Company] = ? AND [Plancode] = ? AND [FundID] = ? AND [EffDate] = ?"
)

INSERT_SQL = (
    f"INSERT INTO [dbo].[{TABLE_NAME}] "
    "([Company], [Plancode], [FundID], [EffDate], [Rate_ANICO], [Rate_RGA]) "
    "VALUES (?, ?, ?, ?, ?, ?)"
)


def parse_rate(token: str) -> Optional[float]:
    """Normalize a rate token to a decimal fraction, or None for a blank cell."""
    token = token.strip()
    if token == "":
        return None
    if token.endswith("%"):
        return round(float(token[:-1]) / 100.0, 6)
    return round(float(token), 6)


def parse_rows() -> Tuple[List[Row], List[dict]]:
    """Parse the embedded pipe-delimited data into typed rows."""
    rows: List[Row] = []
    errors: List[dict] = []
    lines = [line for line in RAW_DATA.splitlines() if line.strip()]
    for lineno, line in enumerate(lines[1:], start=2):  # skip header row
        parts = [part.strip() for part in line.split("|")]
        if len(parts) != 6:
            errors.append({"line": lineno, "text": line,
                           "error": f"expected 6 fields, got {len(parts)}"})
            continue
        company, plancode, fund, eff_s, anico_s, rga_s = parts
        try:
            eff = datetime.strptime(eff_s, "%m/%d/%Y").date()
        except ValueError as exc:
            errors.append({"line": lineno, "text": line, "error": f"bad EffDate: {exc}"})
            continue
        try:
            anico = parse_rate(anico_s)
            rga = parse_rate(rga_s)
        except ValueError as exc:
            errors.append({"line": lineno, "text": line, "error": f"bad rate: {exc}"})
            continue
        rows.append((company, plancode, fund, eff, anico, rga))
    return rows, errors


def summarize(rows: List[Row]) -> dict:
    return {
        "row_count": len(rows),
        "distinct_dates": sorted({r[3].isoformat() for r in rows}),
        "distinct_companies": sorted({r[0] for r in rows}),
        "distinct_plancodes": sorted({r[1] for r in rows}),
        "distinct_funds": sorted({r[2] for r in rows}),
        "null_rate_anico": sum(1 for r in rows if r[4] is None),
        "null_rate_rga": sum(1 for r in rows if r[5] is None),
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
        keys = [(r[0], r[1], r[2], r[3]) for r in rows]
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
