"""
Shift all interest_rates.date values forward by 3 months and
clean up floating-point noise in iul_var_loan_rate.

Usage:
    python tools/shift_interest_dates.py
"""

import sqlite3
from pathlib import Path


def main():
    db_path = Path.home() / ".suiteview" / "abr_quote.db"
    if not db_path.exists():
        print(f"ERROR: Database not found at {db_path}")
        return

    conn = sqlite3.connect(str(db_path))

    # 1. Read all rows
    rows = conn.execute(
        "SELECT date, rate, iul_var_loan_rate FROM interest_rates ORDER BY date"
    ).fetchall()
    print(f"Found {len(rows)} interest rate rows.")

    # 2. Compute new dates (+3 months) and round iul_var_loan_rate
    updated = []
    for dt_str, rate, iul_rate in rows:
        # Parse YYYY-MM
        year, month = int(dt_str[:4]), int(dt_str[5:7])
        # Add 3 months
        month += 3
        if month > 12:
            month -= 12
            year += 1
        new_dt = f"{year:04d}-{month:02d}"

        # Round rate and iul_var_loan_rate to 2 decimal places
        clean_rate = round(rate, 2)
        clean_iul = round(iul_rate, 2) if iul_rate is not None else None

        updated.append((new_dt, clean_rate, clean_iul, dt_str))
        if clean_rate != rate or (iul_rate is not None and clean_iul != iul_rate):
            print(f"  {dt_str} -> {new_dt}  rate: {rate}->{clean_rate}  iul: {iul_rate}->{clean_iul}")
        else:
            print(f"  {dt_str} -> {new_dt}")

    # 3. Delete all rows and re-insert with new dates
    #    (can't UPDATE in-place because date is the PK and shifts may collide)
    conn.execute("DELETE FROM interest_rates")
    conn.executemany(
        "INSERT INTO interest_rates (date, rate, iul_var_loan_rate) VALUES (?, ?, ?)",
        [(new_dt, r, iul) for new_dt, r, iul, _ in updated],
    )
    conn.commit()
    conn.close()

    print(f"\nDone — shifted {len(updated)} rows forward by 3 months and cleaned precision.")


if __name__ == "__main__":
    main()
