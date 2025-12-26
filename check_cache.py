import sqlite3
import os

db_path = os.path.expanduser('~/.suiteview/suiteview.db')
print(f"Database: {db_path}")
conn = sqlite3.connect(db_path)
cursor = conn.cursor()

# List tables
cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
print("\nTables:")
for row in cursor.fetchall():
    print(f"  {row[0]}")

# Get table_metadata for LH_BAS_POL
cursor.execute("SELECT metadata_id, connection_id, table_name, schema_name FROM table_metadata WHERE table_name LIKE '%LH_BAS_POL%'")
print("\nTable metadata for LH_BAS_POL:")
for row in cursor.fetchall():
    print(f"  metadata_id={row[0]}, conn_id={row[1]}, table={row[2]}, schema='{row[3]}'")

# Get unique values cache
cursor.execute("SELECT metadata_id, column_name, substr(unique_values, 1, 50) as uv FROM unique_values_cache WHERE metadata_id IN (SELECT metadata_id FROM table_metadata WHERE table_name LIKE '%LH_BAS_POL%')")
print("\nUnique values cache for LH_BAS_POL:")
for row in cursor.fetchall():
    print(f"  metadata_id={row[0]}, column={row[1]}, values={row[2]}...")

conn.close()
