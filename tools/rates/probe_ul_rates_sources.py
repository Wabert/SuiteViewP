"""Probe the live UL_Rates ODBC source (work-laptop only).

Read-only discovery helper used before exporting to the local SQLite fixture:
  * confirms the DSN connects,
  * lists all base tables whose name starts with 'SV_INDEX',
  * reports the row count for a given plancode across the standard
    Select_RATE_* plancode tables (default plancode: CCV48000).

Positional args (all optional):
    python tools/rates/probe_ul_rates_sources.py [PLANCODE] [DSN]

Defaults: PLANCODE=CCV48000, DSN=UL_Rates
Output: JSON summary to stdout.
"""

from __future__ import annotations

import json
import sys

import pyodbc

PLANCODE_RATE_TABLES = [
    "Select_RATE_EPP", "Select_RATE_TPP", "Select_RATE_FLATPREM", "Select_RATE_MFEE",
    "Select_RATE_DBD", "Select_RATE_GINT", "Select_RATE_CORR", "Select_RATE_BONUSAV",
    "Select_RATE_BONUSDUR", "Select_RATE_MTP", "Select_RATE_CTP", "Select_RATE_TBL1CTP",
    "Select_RATE_TBL1MTP", "Select_RATE_EPU", "Select_RATE_COI", "Select_RATE_SCR",
    "Select_RATE_BANDSPECS", "Select_RATE_PLNCRD", "Select_RATE_PLNCRG",
    "Select_RATE_RLNCRD", "Select_RATE_RLNCRG", "Select_RATE_SNETPERIOD",
]


def main() -> None:
    plancode = sys.argv[1] if len(sys.argv) > 1 else "CCV48000"
    dsn = sys.argv[2] if len(sys.argv) > 2 else "UL_Rates"

    conn = pyodbc.connect(f"DSN={dsn}", autocommit=True, timeout=15)
    out: dict = {"dsn": dsn, "plancode": plancode}
    try:
        cur = conn.cursor()

        # SV_INDEX_* base tables.
        cur.execute(
            "SELECT TABLE_NAME FROM INFORMATION_SCHEMA.TABLES "
            "WHERE TABLE_TYPE = 'BASE TABLE' AND TABLE_NAME LIKE 'SV_INDEX%' "
            "ORDER BY TABLE_NAME"
        )
        sv_index_tables = [str(r[0]) for r in cur.fetchall()]
        out["sv_index_tables"] = sv_index_tables

        # Row count per SV_INDEX table.
        sv_counts = {}
        for t in sv_index_tables:
            cur.execute(f"SELECT COUNT(*) FROM [dbo].[{t}]")
            sv_counts[t] = cur.fetchone()[0]
        out["sv_index_row_counts"] = sv_counts

        # Plancode presence across the standard rate tables.
        per_table = {}
        total = 0
        for t in PLANCODE_RATE_TABLES:
            try:
                cur.execute(f"SELECT COUNT(*) FROM [dbo].[{t}] WHERE Plancode = ?", (plancode,))
                n = cur.fetchone()[0]
            except Exception as exc:  # missing table/column — record and continue
                per_table[t] = f"ERROR: {exc}"
                continue
            per_table[t] = n
            total += n
        out["plancode_rate_counts"] = per_table
        out["plancode_total_rows"] = total
        out["plancode_found"] = total > 0

        # Distinct benefit types for this plancode (BEN* tables).
        ben = {}
        for t in ("Select_RATE_BENCOI", "Select_RATE_BENMTP", "Select_RATE_BENCTP"):
            try:
                cur.execute(
                    f"SELECT [BenefitType], COUNT(*) FROM [dbo].[{t}] "
                    "WHERE Plancode = ? GROUP BY [BenefitType] ORDER BY [BenefitType]",
                    (plancode,),
                )
                ben[t] = {str(r[0]): r[1] for r in cur.fetchall()}
            except Exception as exc:
                ben[t] = f"ERROR: {exc}"
        out["plancode_benefit_types"] = ben
        cur.close()
    finally:
        conn.close()

    print(json.dumps(out, indent=2, default=str))


if __name__ == "__main__":
    main()
