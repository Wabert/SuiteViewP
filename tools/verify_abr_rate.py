"""Verify effective rate lookup for today's date."""

import sqlite3
from pathlib import Path
from datetime import date

db_path = Path.home() / ".suiteview" / "abr_quote.db"
conn = sqlite3.connect(str(db_path))
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
