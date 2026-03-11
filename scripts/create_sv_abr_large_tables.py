"""
Create and populate the two large SV_ABR tables in UL_Rates:
  - SV_ABR_TERM_RATES   (normalized: ~2.3M rows)
  - SV_ABR_VBT_2008     (mortality: ~48K rows)

This script is designed for resilience against network hiccups:
  - Uses fast_executemany for bulk inserts
  - Commits in batches of 50,000 rows
  - Reconnects and retries if the connection drops

Usage:
    python scripts/create_sv_abr_large_tables.py
"""

import os
import sys
import sqlite3
import time
import pyodbc

# ── Paths ───────────────────────────────────────────────────────────────
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SQLITE_DB = os.path.join(os.path.expanduser("~"), ".suiteview", "abr_quote.db")
ODBC_DSN = "UL_Rates"

sys.path.insert(0, PROJECT_ROOT)


def connect_odbc():
    """Connect to UL_Rates via ODBC with fast_executemany enabled."""
    print(f"  Connecting to ODBC DSN: {ODBC_DSN} ...")
    conn = pyodbc.connect(f"DSN={ODBC_DSN}")
    conn.autocommit = False
    return conn


def insert_batch(odbc_conn, sql, batch, retry_count=3):
    """Insert a batch of rows with retry logic."""
    for attempt in range(retry_count):
        try:
            cursor = odbc_conn.cursor()
            cursor.fast_executemany = True
            cursor.executemany(sql, batch)
            odbc_conn.commit()
            cursor.close()
            return True
        except (pyodbc.Error, pyodbc.OperationalError) as e:
            if attempt < retry_count - 1:
                print(f"    Network error, retrying ({attempt + 2}/{retry_count}): {e}")
                time.sleep(2)
                try:
                    odbc_conn.close()
                except:
                    pass
                odbc_conn = connect_odbc()
            else:
                raise
    return False


# ─────────────────────────────────────────────────────────────────────────
# SV_ABR_TERM_RATES
# ─────────────────────────────────────────────────────────────────────────
def create_term_rates():
    print("=" * 60)
    print("  SV_ABR_TERM_RATES")
    print("=" * 60)

    table = "SV_ABR_TERM_RATES"

    # Connect
    odbc_conn = connect_odbc()
    cursor = odbc_conn.cursor()

    # Drop and create
    print(f"  Dropping and recreating [{table}] ...")
    cursor.execute(f"""
        IF OBJECT_ID('{table}', 'U') IS NOT NULL
            DROP TABLE [{table}]
    """)
    cursor.execute(f"""
        CREATE TABLE [{table}] (
            plancode      VARCHAR(10)  NOT NULL,
            sex           VARCHAR(1)   NOT NULL,
            rate_class    VARCHAR(1)   NOT NULL,
            band          INT          NOT NULL,
            issue_age     INT          NOT NULL,
            policy_year   INT          NOT NULL,
            rate_per_1000 FLOAT        NOT NULL,
            PRIMARY KEY (plancode, sex, rate_class, band, issue_age, policy_year)
        )
    """)
    odbc_conn.commit()
    print(f"  Table created.")
    cursor.close()

    # Read all wide rows from SQLite
    print(f"  Loading from SQLite ...")
    sqlite_conn = sqlite3.connect(SQLITE_DB)
    sqlite_conn.row_factory = sqlite3.Row
    rate_cols = ", ".join(f"rate_{i}" for i in range(1, 83))
    sqlite_rows = sqlite_conn.execute(
        f"SELECT plancode, sex, rate_class, band, issue_age, {rate_cols} "
        f"FROM term_rates ORDER BY plancode, sex, rate_class, band, issue_age"
    ).fetchall()
    sqlite_conn.close()
    wide_count = len(sqlite_rows)
    print(f"  Read {wide_count:,} wide rows. Normalizing ...")

    # Normalize and insert in batches
    BATCH_SIZE = 50_000
    batch = []
    total_inserted = 0
    t0 = time.time()

    insert_sql = (
        f"INSERT INTO [{table}] "
        f"(plancode, sex, rate_class, band, issue_age, policy_year, rate_per_1000) "
        f"VALUES (?, ?, ?, ?, ?, ?, ?)"
    )

    for row_idx, r in enumerate(sqlite_rows):
        plancode = r["plancode"]
        sex = r["sex"]
        rate_class = r["rate_class"]
        band = r["band"]
        issue_age = r["issue_age"]

        for yr in range(1, 83):
            rate = r[f"rate_{yr}"]
            if rate is not None and rate > 0:
                batch.append((plancode, sex, rate_class, band, issue_age, yr, rate))

        if len(batch) >= BATCH_SIZE:
            insert_batch(odbc_conn, insert_sql, batch)
            total_inserted += len(batch)
            elapsed = time.time() - t0
            pct = (row_idx + 1) / wide_count * 100
            print(f"    {total_inserted:>10,} rows inserted  "
                  f"({pct:.0f}% of wide rows, {elapsed:.0f}s)")
            batch = []

    # Final batch
    if batch:
        insert_batch(odbc_conn, insert_sql, batch)
        total_inserted += len(batch)

    elapsed = time.time() - t0
    print(f"  Done: {total_inserted:,} rows in {elapsed:.1f}s")

    # Create index
    print(f"  Creating lookup index ...")
    cursor = odbc_conn.cursor()
    cursor.execute(f"""
        CREATE INDEX IX_{table}_lookup
        ON [{table}] (plancode, sex, rate_class, band, issue_age)
    """)
    odbc_conn.commit()
    print(f"  Index created.")

    # Verify
    cnt = cursor.execute(f"SELECT COUNT(*) FROM [{table}]").fetchone()[0]
    print(f"  Verify: {cnt:,} rows in SQL Server ({'✓' if cnt == total_inserted else '✗'})")

    cursor.close()
    odbc_conn.close()
    return total_inserted


# ─────────────────────────────────────────────────────────────────────────
# SV_ABR_VBT_2008
# ─────────────────────────────────────────────────────────────────────────
def create_vbt_2008():
    print()
    print("=" * 60)
    print("  SV_ABR_VBT_2008")
    print("=" * 60)

    table = "SV_ABR_VBT_2008"

    # Connect
    odbc_conn = connect_odbc()
    cursor = odbc_conn.cursor()

    # Drop and create
    print(f"  Dropping and recreating [{table}] ...")
    cursor.execute(f"""
        IF OBJECT_ID('{table}', 'U') IS NOT NULL
            DROP TABLE [{table}]
    """)
    cursor.execute(f"""
        CREATE TABLE [{table}] (
            block          VARCHAR(2)  NOT NULL,
            duration_year  INT         NOT NULL,
            issue_age      INT         NOT NULL,
            rate_per_1000  FLOAT       NOT NULL,
            PRIMARY KEY (block, duration_year, issue_age)
        )
    """)
    odbc_conn.commit()
    print(f"  Table created.")
    cursor.close()

    # Load VBT data from Python module
    print(f"  Loading VBT 2008 data from vbt_2008.py ...")
    from suiteview.abrquote.models.vbt_2008 import VBT_DATA

    # Build all rows
    all_rows = []
    for block, durations in VBT_DATA.items():
        for dur_idx, ages in enumerate(durations):
            duration_year = dur_idx + 1
            for issue_age, rate in enumerate(ages):
                if rate is not None and rate > 0:
                    all_rows.append((block, duration_year, issue_age, rate))

    print(f"  {len(all_rows):,} VBT rows to insert.")

    # Insert in one batch (small enough)
    insert_sql = (
        f"INSERT INTO [{table}] "
        f"(block, duration_year, issue_age, rate_per_1000) "
        f"VALUES (?, ?, ?, ?)"
    )

    BATCH_SIZE = 10_000
    total_inserted = 0
    t0 = time.time()

    for i in range(0, len(all_rows), BATCH_SIZE):
        batch = all_rows[i:i + BATCH_SIZE]
        insert_batch(odbc_conn, insert_sql, batch)
        total_inserted += len(batch)
        print(f"    {total_inserted:>10,} / {len(all_rows):,} rows inserted")

    elapsed = time.time() - t0
    print(f"  Done: {total_inserted:,} rows in {elapsed:.1f}s")

    # Create index
    print(f"  Creating lookup index ...")
    cursor = odbc_conn.cursor()
    cursor.execute(f"""
        CREATE INDEX IX_{table}_lookup
        ON [{table}] (block, duration_year, issue_age)
    """)
    odbc_conn.commit()
    print(f"  Index created.")

    # Verify
    cnt = cursor.execute(f"SELECT COUNT(*) FROM [{table}]").fetchone()[0]
    print(f"  Verify: {cnt:,} rows in SQL Server ({'✓' if cnt == total_inserted else '✗'})")

    # Show block counts
    block_counts = cursor.execute(
        f"SELECT block, COUNT(*) as cnt FROM [{table}] GROUP BY block ORDER BY block"
    ).fetchall()
    for bc in block_counts:
        print(f"    Block {bc.block}: {bc.cnt:,} rows")

    cursor.close()
    odbc_conn.close()
    return total_inserted


# ─────────────────────────────────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────────────────────────────────
def main():
    t_start = time.time()

    term_count = create_term_rates()
    vbt_count = create_vbt_2008()

    # Final summary of ALL tables
    print()
    print("=" * 60)
    print("  FINAL SUMMARY – All SV_ABR tables in UL_Rates")
    print("=" * 60)

    odbc_conn = connect_odbc()
    cursor = odbc_conn.cursor()

    all_tables = [
        "SV_ABR_INTEREST_RATES",
        "SV_ABR_PER_DIEM",
        "SV_ABR_STATE_VARIATIONS",
        "SV_ABR_MIN_FACE",
        "SV_ABR_MODAL_FACTORS",
        "SV_ABR_BAND_AMOUNTS",
        "SV_ABR_POLICY_FEES",
        "SV_ABR_TERM_RATES",
        "SV_ABR_VBT_2008",
    ]
    print(f"\n  {'Table':<30} {'Rows':>12}")
    print(f"  {'-'*30} {'-'*12}")
    for t in all_tables:
        try:
            cnt = cursor.execute(f"SELECT COUNT(*) FROM [{t}]").fetchone()[0]
            print(f"  {t:<30} {cnt:>12,}")
        except pyodbc.Error:
            print(f"  {t:<30} {'(missing)':>12}")

    elapsed = time.time() - t_start
    print(f"\n  Total time: {elapsed:.1f}s")

    cursor.close()
    odbc_conn.close()
    print("  Done.")


if __name__ == "__main__":
    main()
