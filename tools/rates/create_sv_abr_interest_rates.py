"""
Create and populate SV_ABR_INTEREST_RATES in the UL_Rates SQL Server database.

This script:
  1. Connects to UL_Rates via ODBC
  2. Creates the SV_ABR_INTEREST_RATES table (drops if exists)
  3. Reads interest rate data from the local SQLite abr_quote.db
  4. Inserts all rows into the new SQL Server table
  5. Verifies the row count matches

Usage:
    python scripts/create_sv_abr_interest_rates.py
"""

import os
import sys
import sqlite3
import pyodbc

# ── Paths ───────────────────────────────────────────────────────────────
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SQLITE_DB = os.path.join(PROJECT_ROOT, "bundled_data", "abr_quote.db")
ODBC_DSN = "UL_Rates"


def main():
    # ── 1. Connect to UL_Rates via ODBC ─────────────────────────────────
    print(f"Connecting to ODBC DSN: {ODBC_DSN} ...")
    try:
        odbc_conn = pyodbc.connect(f"DSN={ODBC_DSN}")
        odbc_conn.autocommit = False
        print("  Connected to SQL Server.")
    except pyodbc.Error as e:
        print(f"  ERROR: Could not connect to {ODBC_DSN}: {e}")
        sys.exit(1)

    odbc_cursor = odbc_conn.cursor()

    # ── 2. Create the table (drop if exists) ────────────────────────────
    table_name = "SV_ABR_INTEREST_RATES"
    print(f"\nCreating table [{table_name}] ...")

    # Drop if exists
    odbc_cursor.execute(f"""
        IF OBJECT_ID('{table_name}', 'U') IS NOT NULL
            DROP TABLE [{table_name}]
    """)

    # Create table
    odbc_cursor.execute(f"""
        CREATE TABLE [{table_name}] (
            effective_date      VARCHAR(7)   NOT NULL PRIMARY KEY,
            rate                FLOAT        NOT NULL,
            iul_var_loan_rate   FLOAT        NULL
        )
    """)
    odbc_conn.commit()
    print(f"  Table [{table_name}] created.")

    # ── 3. Read data from local SQLite ──────────────────────────────────
    print(f"\nReading from SQLite: {SQLITE_DB} ...")
    if not os.path.exists(SQLITE_DB):
        print(f"  ERROR: SQLite database not found at {SQLITE_DB}")
        odbc_conn.close()
        sys.exit(1)

    sqlite_conn = sqlite3.connect(SQLITE_DB)
    sqlite_conn.row_factory = sqlite3.Row
    rows = sqlite_conn.execute(
        "SELECT date, rate, iul_var_loan_rate FROM interest_rates ORDER BY date"
    ).fetchall()
    sqlite_conn.close()
    print(f"  Read {len(rows)} rows from SQLite.")

    # ── 4. Insert into SQL Server ───────────────────────────────────────
    print(f"\nInserting {len(rows)} rows into [{table_name}] ...")
    insert_sql = f"""
        INSERT INTO [{table_name}] (effective_date, rate, iul_var_loan_rate)
        VALUES (?, ?, ?)
    """
    for row in rows:
        odbc_cursor.execute(insert_sql, (row["date"], row["rate"], row["iul_var_loan_rate"]))

    odbc_conn.commit()
    print("  Insert complete.")

    # ── 5. Verify ───────────────────────────────────────────────────────
    count = odbc_cursor.execute(f"SELECT COUNT(*) FROM [{table_name}]").fetchone()[0]
    print(f"\nVerification:")
    print(f"  SQLite rows:      {len(rows)}")
    print(f"  SQL Server rows:  {count}")

    if count == len(rows):
        print("  ✓ Row counts match!")
    else:
        print("  ✗ WARNING: Row count mismatch!")

    # Show first and last few rows
    print(f"\nFirst 3 rows:")
    sample = odbc_cursor.execute(
        f"SELECT TOP 3 * FROM [{table_name}] ORDER BY effective_date ASC"
    ).fetchall()
    for r in sample:
        print(f"  {r.effective_date}  rate={r.rate}  iul_var_loan_rate={r.iul_var_loan_rate}")

    print(f"\nLast 3 rows:")
    sample = odbc_cursor.execute(
        f"SELECT TOP 3 * FROM [{table_name}] ORDER BY effective_date DESC"
    ).fetchall()
    for r in sample:
        print(f"  {r.effective_date}  rate={r.rate}  iul_var_loan_rate={r.iul_var_loan_rate}")

    # ── Cleanup ─────────────────────────────────────────────────────────
    odbc_cursor.close()
    odbc_conn.close()
    print(f"\nDone. Table [{table_name}] is ready in {ODBC_DSN}.")


if __name__ == "__main__":
    main()
