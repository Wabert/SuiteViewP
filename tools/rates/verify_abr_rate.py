"""Verify effective rate lookup for today's date."""

import sqlite3
import sys
from pathlib import Path
from datetime import date

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from suiteview.core.profile_paths import profile_path

db_path = profile_path("abr_quote.db")
conn = sqlite3.connect(db_path.resolve().as_uri() + "?mode=ro", uri=True)
conn.row_factory = sqlite3.Row

today = date.today()
quote_month = today.strftime("%Y-%m")
print(f"Today: {today}")
print(f"Quote month: {quote_month}")

# What the new method returns (latest effective date <= quote month)
row = conn.execute(
    "SELECT date, iul_var_loan_rate FROM interest_rates "
    "WHERE date <= ? ORDER BY date DESC LIMIT 1", (quote_month,)
).fetchone()
print(f"\nEffective rate for {quote_month}:")
print(f"  Effective Date:  {row['date']}")
print(f"  ABR Rate:        {row['iul_var_loan_rate']}%")

# Show what the latest row is (which we should NOT use yet)
latest = conn.execute(
    "SELECT date, iul_var_loan_rate FROM interest_rates ORDER BY date DESC LIMIT 1"
).fetchone()
print(f"\nLatest row in DB (may be future):")
print(f"  Effective Date:  {latest['date']}")
print(f"  ABR Rate:        {latest['iul_var_loan_rate']}%")

conn.close()
