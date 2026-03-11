"""
Create and populate all SV_ABR_* tables in the UL_Rates SQL Server database.

Tables created:
  - SV_ABR_PER_DIEM            (per diem daily/annual limits by year)
  - SV_ABR_STATE_VARIATIONS    (state-specific forms + admin fees)
  - SV_ABR_MIN_FACE            (minimum face amount by plancode)
  - SV_ABR_MODAL_FACTORS       (billing-mode factors by plancode)
  - SV_ABR_BAND_AMOUNTS        (face-amount band breakpoints by plancode)
  - SV_ABR_POLICY_FEES         (annual policy fee by plancode)
  - SV_ABR_TERM_RATES          (normalized: one row per plancode/sex/class/band/age/year)
  - SV_ABR_VBT_2008            (2008 VBT Select mortality rates)

NOTE: SV_ABR_INTEREST_RATES was already created by create_sv_abr_interest_rates.py

Usage:
    python scripts/create_sv_abr_tables.py
"""

import os
import sys
import sqlite3
import time
import pyodbc

# ── Paths ───────────────────────────────────────────────────────────────
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
# Use the RUNTIME DB (~/.suiteview/) which has all migrated/seeded tables,
# not the bundled DB which only has the original pre-migration tables.
SQLITE_DB = os.path.join(os.path.expanduser("~"), ".suiteview", "abr_quote.db")
ODBC_DSN = "UL_Rates"

# Add project root to path so we can import vbt_2008
sys.path.insert(0, PROJECT_ROOT)


def connect_odbc():
    """Connect to UL_Rates via ODBC."""
    print(f"Connecting to ODBC DSN: {ODBC_DSN} ...")
    try:
        conn = pyodbc.connect(f"DSN={ODBC_DSN}")
        conn.autocommit = False
        print("  Connected to SQL Server.")
        return conn
    except pyodbc.Error as e:
        print(f"  ERROR: Could not connect to {ODBC_DSN}: {e}")
        sys.exit(1)


def connect_sqlite():
    """Connect to local SQLite database."""
    print(f"Connecting to SQLite: {SQLITE_DB} ...")
    if not os.path.exists(SQLITE_DB):
        print(f"  ERROR: SQLite database not found at {SQLITE_DB}")
        sys.exit(1)
    conn = sqlite3.connect(SQLITE_DB)
    conn.row_factory = sqlite3.Row
    print("  Connected.")
    return conn


def drop_and_create(odbc_cursor, odbc_conn, table_name, create_sql):
    """Drop table if exists and create it."""
    print(f"\n{'='*60}")
    print(f"  Creating table [{table_name}] ...")
    odbc_cursor.execute(f"""
        IF OBJECT_ID('{table_name}', 'U') IS NOT NULL
            DROP TABLE [{table_name}]
    """)
    odbc_cursor.execute(create_sql)
    odbc_conn.commit()
    print(f"  Table [{table_name}] created.")


def verify(odbc_cursor, table_name, expected_count):
    """Verify row count matches."""
    actual = odbc_cursor.execute(f"SELECT COUNT(*) FROM [{table_name}]").fetchone()[0]
    status = "✓" if actual == expected_count else "✗ MISMATCH"
    print(f"  Verify: expected={expected_count}, actual={actual}  {status}")
    return actual == expected_count


# ─────────────────────────────────────────────────────────────────────────
# Table: SV_ABR_PER_DIEM
# ─────────────────────────────────────────────────────────────────────────
def create_per_diem(odbc_cursor, odbc_conn, sqlite_conn):
    table = "SV_ABR_PER_DIEM"
    drop_and_create(odbc_cursor, odbc_conn, table, f"""
        CREATE TABLE [{table}] (
            year          INT    NOT NULL PRIMARY KEY,
            daily_limit   FLOAT  NOT NULL,
            annual_limit  FLOAT  NOT NULL
        )
    """)

    rows = sqlite_conn.execute(
        "SELECT year, daily_limit, annual_limit FROM per_diem ORDER BY year"
    ).fetchall()
    print(f"  Read {len(rows)} rows from SQLite.")

    for r in rows:
        odbc_cursor.execute(
            f"INSERT INTO [{table}] (year, daily_limit, annual_limit) VALUES (?, ?, ?)",
            (r["year"], r["daily_limit"], r["annual_limit"])
        )
    odbc_conn.commit()
    print(f"  Inserted {len(rows)} rows.")

    # Show all rows (small table)
    for r in rows:
        print(f"    {r['year']}:  daily={r['daily_limit']:.2f}  annual={r['annual_limit']:.2f}")

    verify(odbc_cursor, table, len(rows))


# ─────────────────────────────────────────────────────────────────────────
# Table: SV_ABR_STATE_VARIATIONS
# ─────────────────────────────────────────────────────────────────────────
def create_state_variations(odbc_cursor, odbc_conn, sqlite_conn):
    table = "SV_ABR_STATE_VARIATIONS"
    drop_and_create(odbc_cursor, odbc_conn, table, f"""
        CREATE TABLE [{table}] (
            state_abbr                  VARCHAR(2)    NOT NULL PRIMARY KEY,
            cl_state_code               INT           NULL,
            state_name                  VARCHAR(50)   NOT NULL,
            state_group                 VARCHAR(10)   NULL,
            admin_fee                   FLOAT         NOT NULL DEFAULT 250.0,
            election_form               VARCHAR(100)  NULL,
            disclosure_form_critical    VARCHAR(100)  NULL,
            disclosure_form_chronic     VARCHAR(100)  NULL,
            disclosure_form_terminal    VARCHAR(100)  NULL
        )
    """)

    rows = sqlite_conn.execute("""
        SELECT state_abbr, cl_state_code, state_name, state_group, admin_fee,
               election_form, disclosure_form_critical,
               disclosure_form_chronic, disclosure_form_terminal
        FROM state_variations ORDER BY state_abbr
    """).fetchall()
    print(f"  Read {len(rows)} rows from SQLite.")

    for r in rows:
        odbc_cursor.execute(
            f"INSERT INTO [{table}] (state_abbr, cl_state_code, state_name, state_group, "
            f"admin_fee, election_form, disclosure_form_critical, "
            f"disclosure_form_chronic, disclosure_form_terminal) "
            f"VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (r["state_abbr"], r["cl_state_code"], r["state_name"], r["state_group"],
             r["admin_fee"], r["election_form"], r["disclosure_form_critical"],
             r["disclosure_form_chronic"], r["disclosure_form_terminal"])
        )
    odbc_conn.commit()
    print(f"  Inserted {len(rows)} rows.")
    verify(odbc_cursor, table, len(rows))


# ─────────────────────────────────────────────────────────────────────────
# Table: SV_ABR_MIN_FACE
# ─────────────────────────────────────────────────────────────────────────
def create_min_face(odbc_cursor, odbc_conn, sqlite_conn):
    table = "SV_ABR_MIN_FACE"
    drop_and_create(odbc_cursor, odbc_conn, table, f"""
        CREATE TABLE [{table}] (
            plancode      VARCHAR(10)  NOT NULL PRIMARY KEY,
            min_face_amt  FLOAT        NOT NULL DEFAULT 50000.0
        )
    """)

    rows = sqlite_conn.execute(
        "SELECT plancode, min_face_amt FROM min_face ORDER BY plancode"
    ).fetchall()
    print(f"  Read {len(rows)} rows from SQLite.")

    for r in rows:
        odbc_cursor.execute(
            f"INSERT INTO [{table}] (plancode, min_face_amt) VALUES (?, ?)",
            (r["plancode"], r["min_face_amt"])
        )
    odbc_conn.commit()
    print(f"  Inserted {len(rows)} rows.")
    verify(odbc_cursor, table, len(rows))


# ─────────────────────────────────────────────────────────────────────────
# Table: SV_ABR_MODAL_FACTORS
# ─────────────────────────────────────────────────────────────────────────
def create_modal_factors(odbc_cursor, odbc_conn, sqlite_conn):
    table = "SV_ABR_MODAL_FACTORS"
    drop_and_create(odbc_cursor, odbc_conn, table, f"""
        CREATE TABLE [{table}] (
            plancode      VARCHAR(10)  NOT NULL,
            mode_code     INT          NOT NULL,
            mode_label    VARCHAR(20)  NOT NULL,
            factor        FLOAT        NOT NULL,
            PRIMARY KEY (plancode, mode_code)
        )
    """)

    rows = sqlite_conn.execute(
        "SELECT plancode, mode_code, mode_label, factor FROM modal_factors "
        "ORDER BY plancode, mode_code"
    ).fetchall()
    print(f"  Read {len(rows)} rows from SQLite.")

    for r in rows:
        odbc_cursor.execute(
            f"INSERT INTO [{table}] (plancode, mode_code, mode_label, factor) "
            f"VALUES (?, ?, ?, ?)",
            (r["plancode"], r["mode_code"], r["mode_label"], r["factor"])
        )
    odbc_conn.commit()
    print(f"  Inserted {len(rows)} rows.")
    verify(odbc_cursor, table, len(rows))


# ─────────────────────────────────────────────────────────────────────────
# Table: SV_ABR_BAND_AMOUNTS
# ─────────────────────────────────────────────────────────────────────────
def create_band_amounts(odbc_cursor, odbc_conn, sqlite_conn):
    table = "SV_ABR_BAND_AMOUNTS"
    drop_and_create(odbc_cursor, odbc_conn, table, f"""
        CREATE TABLE [{table}] (
            plancode      VARCHAR(10)  NOT NULL,
            band          INT          NOT NULL,
            min_face_amt  FLOAT        NOT NULL,
            PRIMARY KEY (plancode, band)
        )
    """)

    rows = sqlite_conn.execute(
        "SELECT plancode, band, min_face_amt FROM band_amounts "
        "ORDER BY plancode, band"
    ).fetchall()
    print(f"  Read {len(rows)} rows from SQLite.")

    for r in rows:
        odbc_cursor.execute(
            f"INSERT INTO [{table}] (plancode, band, min_face_amt) VALUES (?, ?, ?)",
            (r["plancode"], r["band"], r["min_face_amt"])
        )
    odbc_conn.commit()
    print(f"  Inserted {len(rows)} rows.")
    verify(odbc_cursor, table, len(rows))


# ─────────────────────────────────────────────────────────────────────────
# Table: SV_ABR_POLICY_FEES
# ─────────────────────────────────────────────────────────────────────────
def create_policy_fees(odbc_cursor, odbc_conn, sqlite_conn):
    table = "SV_ABR_POLICY_FEES"
    drop_and_create(odbc_cursor, odbc_conn, table, f"""
        CREATE TABLE [{table}] (
            plancode      VARCHAR(10)  NOT NULL PRIMARY KEY,
            annual_fee    FLOAT        NOT NULL DEFAULT 60.0
        )
    """)

    rows = sqlite_conn.execute(
        "SELECT plancode, annual_fee FROM policy_fees ORDER BY plancode"
    ).fetchall()
    print(f"  Read {len(rows)} rows from SQLite.")

    for r in rows:
        odbc_cursor.execute(
            f"INSERT INTO [{table}] (plancode, annual_fee) VALUES (?, ?)",
            (r["plancode"], r["annual_fee"])
        )
    odbc_conn.commit()
    print(f"  Inserted {len(rows)} rows.")
    verify(odbc_cursor, table, len(rows))


# ─────────────────────────────────────────────────────────────────────────
# Table: SV_ABR_TERM_RATES  (normalized from wide format)
# ─────────────────────────────────────────────────────────────────────────
def create_term_rates(odbc_cursor, odbc_conn, sqlite_conn):
    table = "SV_ABR_TERM_RATES"
    drop_and_create(odbc_cursor, odbc_conn, table, f"""
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

    # Read the wide-format rows from SQLite
    rate_cols = ", ".join(f"rate_{i}" for i in range(1, 83))
    sqlite_rows = sqlite_conn.execute(
        f"SELECT plancode, sex, rate_class, band, issue_age, {rate_cols} "
        f"FROM term_rates ORDER BY plancode, sex, rate_class, band, issue_age"
    ).fetchall()
    wide_count = len(sqlite_rows)
    print(f"  Read {wide_count} wide-format rows from SQLite.")
    print(f"  Normalizing to {wide_count} × 82 = {wide_count * 82} rows (skipping zero rates) ...")

    # Normalize: one row per policy year, skip zero/null rates
    BATCH_SIZE = 5000
    batch = []
    total_inserted = 0
    t0 = time.time()

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
                odbc_cursor.executemany(
                    f"INSERT INTO [{table}] "
                    f"(plancode, sex, rate_class, band, issue_age, policy_year, rate_per_1000) "
                    f"VALUES (?, ?, ?, ?, ?, ?, ?)",
                    batch
                )
                odbc_conn.commit()
                total_inserted += len(batch)
                batch = []

        # Progress update every 5000 wide rows
        if (row_idx + 1) % 5000 == 0:
            elapsed = time.time() - t0
            print(f"    ... processed {row_idx + 1}/{wide_count} wide rows "
                  f"({total_inserted:,} normalized rows, {elapsed:.1f}s)")

    # Final batch
    if batch:
        odbc_cursor.executemany(
            f"INSERT INTO [{table}] "
            f"(plancode, sex, rate_class, band, issue_age, policy_year, rate_per_1000) "
            f"VALUES (?, ?, ?, ?, ?, ?, ?)",
            batch
        )
        odbc_conn.commit()
        total_inserted += len(batch)

    elapsed = time.time() - t0
    print(f"  Inserted {total_inserted:,} normalized rows in {elapsed:.1f}s.")

    # Create index for fast lookups (the common query pattern)
    print(f"  Creating lookup index ...")
    odbc_cursor.execute(f"""
        CREATE INDEX IX_{table}_lookup
        ON [{table}] (plancode, sex, rate_class, band, issue_age)
    """)
    odbc_conn.commit()
    print(f"  Index created.")

    verify(odbc_cursor, table, total_inserted)


# ─────────────────────────────────────────────────────────────────────────
# Table: SV_ABR_VBT_2008  (from vbt_2008.py Python dict)
# ─────────────────────────────────────────────────────────────────────────
def create_vbt_2008(odbc_cursor, odbc_conn):
    table = "SV_ABR_VBT_2008"
    drop_and_create(odbc_cursor, odbc_conn, table, f"""
        CREATE TABLE [{table}] (
            block          VARCHAR(2)  NOT NULL,
            duration_year  INT         NOT NULL,
            issue_age      INT         NOT NULL,
            rate_per_1000  FLOAT       NOT NULL,
            PRIMARY KEY (block, duration_year, issue_age)
        )
    """)

    # Import VBT data from the Python module
    print(f"  Loading VBT 2008 data from vbt_2008.py ...")
    from suiteview.abrquote.models.vbt_2008 import VBT_DATA

    BATCH_SIZE = 5000
    batch = []
    total_inserted = 0
    t0 = time.time()

    for block, durations in VBT_DATA.items():
        for dur_idx, ages in enumerate(durations):
            duration_year = dur_idx + 1  # 1-indexed
            for issue_age, rate in enumerate(ages):
                if rate is not None and rate > 0:
                    batch.append((block, duration_year, issue_age, rate))

                if len(batch) >= BATCH_SIZE:
                    odbc_cursor.executemany(
                        f"INSERT INTO [{table}] "
                        f"(block, duration_year, issue_age, rate_per_1000) "
                        f"VALUES (?, ?, ?, ?)",
                        batch
                    )
                    odbc_conn.commit()
                    total_inserted += len(batch)
                    batch = []

    # Final batch
    if batch:
        odbc_cursor.executemany(
            f"INSERT INTO [{table}] "
            f"(block, duration_year, issue_age, rate_per_1000) "
            f"VALUES (?, ?, ?, ?)",
            batch
        )
        odbc_conn.commit()
        total_inserted += len(batch)

    elapsed = time.time() - t0
    print(f"  Inserted {total_inserted:,} VBT rows in {elapsed:.1f}s.")

    # Create index for the common lookup pattern
    print(f"  Creating lookup index ...")
    odbc_cursor.execute(f"""
        CREATE INDEX IX_{table}_lookup
        ON [{table}] (block, duration_year, issue_age)
    """)
    odbc_conn.commit()
    print(f"  Index created.")

    verify(odbc_cursor, table, total_inserted)

    # Show block counts
    block_counts = odbc_cursor.execute(
        f"SELECT block, COUNT(*) as cnt FROM [{table}] GROUP BY block ORDER BY block"
    ).fetchall()
    for bc in block_counts:
        print(f"    Block {bc.block}: {bc.cnt:,} rows")


# ─────────────────────────────────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────────────────────────────────
def main():
    t_start = time.time()

    odbc_conn = connect_odbc()
    odbc_cursor = odbc_conn.cursor()
    sqlite_conn = connect_sqlite()

    # Small reference tables first
    create_per_diem(odbc_cursor, odbc_conn, sqlite_conn)
    create_state_variations(odbc_cursor, odbc_conn, sqlite_conn)
    create_min_face(odbc_cursor, odbc_conn, sqlite_conn)
    create_modal_factors(odbc_cursor, odbc_conn, sqlite_conn)
    create_band_amounts(odbc_cursor, odbc_conn, sqlite_conn)
    create_policy_fees(odbc_cursor, odbc_conn, sqlite_conn)

    # Large tables
    create_term_rates(odbc_cursor, odbc_conn, sqlite_conn)
    create_vbt_2008(odbc_cursor, odbc_conn)

    # ── Summary ─────────────────────────────────────────────────────────
    print(f"\n{'='*60}")
    print(f"  ALL TABLES COMPLETE")
    print(f"{'='*60}")

    all_tables = [
        "SV_ABR_INTEREST_RATES",  # created earlier
        "SV_ABR_PER_DIEM",
        "SV_ABR_STATE_VARIATIONS",
        "SV_ABR_MIN_FACE",
        "SV_ABR_MODAL_FACTORS",
        "SV_ABR_BAND_AMOUNTS",
        "SV_ABR_POLICY_FEES",
        "SV_ABR_TERM_RATES",
        "SV_ABR_VBT_2008",
    ]
    print(f"\n  {'Table':<30} {'Rows':>10}")
    print(f"  {'-'*30} {'-'*10}")
    for t in all_tables:
        try:
            cnt = odbc_cursor.execute(f"SELECT COUNT(*) FROM [{t}]").fetchone()[0]
            print(f"  {t:<30} {cnt:>10,}")
        except pyodbc.Error:
            print(f"  {t:<30} {'(missing)':>10}")

    elapsed = time.time() - t_start
    print(f"\n  Total time: {elapsed:.1f}s")

    # Cleanup
    sqlite_conn.close()
    odbc_cursor.close()
    odbc_conn.close()
    print(f"\n  Done.")


if __name__ == "__main__":
    main()
