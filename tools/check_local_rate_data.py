from __future__ import annotations

import json
import os
import sqlite3
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

RATES_DB = ROOT / "bundled_data" / "dev" / "rates.sqlite"


def _first_row(conn: sqlite3.Connection, sql: str, params: tuple = ()) -> sqlite3.Row:
    row = conn.execute(sql, params).fetchone()
    if row is None:
        raise RuntimeError(f"No row found for validation query: {sql} {params}")
    return row


def _rate_args_from_row(row: sqlite3.Row) -> dict:
    return {
        "plancode": row["Plancode"],
        "issue_age": int(row["IssueAge"]),
        "sex": row["Sex"],
        "rateclass": row["Rateclass"],
        "scale": int(row["Scale"]),
        "band": int(row["Band"]),
    }


def main() -> None:
    os.environ["SUITEVIEW_LOCAL_DATA"] = "1"

    from suiteview.core.rates import Rates

    conn = sqlite3.connect(RATES_DB)
    conn.row_factory = sqlite3.Row
    try:
        rates = Rates()
        checks = []

        for plancode in ("1U143900", "CCV00100", "1U536C00"):
            row = _first_row(
                conn,
                "SELECT * FROM Select_RATE_COI WHERE Plancode = ? LIMIT 1",
                (plancode,),
            )
            args = _rate_args_from_row(row)
            coi = rates.get_rates("COI", **args)
            if not coi or len(coi) <= 1:
                raise RuntimeError(f"COI rates did not load for {plancode}: {args}")
            checks.append({
                "rate_type": "COI",
                "plancode": plancode,
                "sample_args": args,
                "rate_count": len(coi) - 1,
            })

        for benefit_type in ("76", "39"):
            row = _first_row(
                conn,
                "SELECT * FROM Select_RATE_BENCOI WHERE Plancode = ? AND BenefitType = ? LIMIT 1",
                ("1U143900", benefit_type),
            )
            args = _rate_args_from_row(row)
            ben_coi = rates.get_rates("BENCOI", benefit_type=benefit_type, **args)
            if not ben_coi or len(ben_coi) <= 1:
                raise RuntimeError(f"BENCOI rates did not load for benefit {benefit_type}: {args}")
            checks.append({
                "rate_type": "BENCOI",
                "plancode": "1U143900",
                "benefit_type": benefit_type,
                "sample_args": args,
                "rate_count": len(ben_coi) - 1,
            })

        band_specs = rates.get_rates("BANDSPECS", "1U143900")
        if not band_specs:
            raise RuntimeError("BANDSPECS did not load for 1U143900")
        checks.append({
            "rate_type": "BANDSPECS",
            "plancode": "1U143900",
            "rows": len(band_specs),
        })
    finally:
        conn.close()

    print(json.dumps({"checks": checks}, indent=2))


if __name__ == "__main__":
    main()