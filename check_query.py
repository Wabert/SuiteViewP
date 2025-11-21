import sqlite3
import json
from pathlib import Path

# Use the correct database path
home = Path.home()
db_path = home / '.suiteview' / 'suiteview.db'

conn = sqlite3.connect(str(db_path))
cursor = conn.cursor()

# Find queries with Plancode_MRT in the name
cursor.execute("SELECT query_id, query_name, connection_id, query_definition FROM saved_queries WHERE query_name LIKE ?", ('%Plancode_MRT%',))
results = cursor.fetchall()

print('Query records:')
for r in results:
    print(f'\nID: {r[0]}, Name: {r[1]}, ConnID: {r[2]}')
    if r[3]:
        query_def = json.loads(r[3])
        print(f'  Connection ID in definition: {query_def.get("connection_id")}')
        print(f'  From Schema: {query_def.get("from_schema")}')
        print(f'  From Table: {query_def.get("from_table")}')
        
        # Check joins
        joins = query_def.get('joins', [])
        if joins:
            print(f'  Joins ({len(joins)}):')
            for join in joins:
                print(f'    - Table: {join.get("table_name")}, Schema: {join.get("schema_name")}')

# Get connection details for this query
cursor.execute("SELECT connection_id, connection_name, database_name, connection_type FROM connections WHERE connection_id IN (SELECT DISTINCT connection_id FROM saved_queries WHERE query_name LIKE ?)", ('%Plancode_MRT%',))
conn_results = cursor.fetchall()

print('\n\nConnection details:')
for c in conn_results:
    print(f'  ID: {c[0]}, Name: {c[1]}, Database: {c[2]}, Type: {c[3]}')

conn.close()
