import sqlite3
from pathlib import Path

# Use the correct database path
home = Path.home()
db_path = home / '.suiteview' / 'suiteview.db'

conn = sqlite3.connect(str(db_path))
cursor = conn.cursor()

cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
tables = cursor.fetchall()

print("Tables in database:")
for table in tables:
    print(f"  {table[0]}")

conn.close()
