"""
Quick test to verify join field restoration
"""
from pathlib import Path
import sqlite3
import json

# Get the database path
home = Path.home()
db_path = home / '.suiteview' / 'suiteview.db'

print(f'Database: {db_path}')
print('='*80)

# Connect to database
conn = sqlite3.connect(str(db_path))
cursor = conn.cursor()

# Get all queries
cursor.execute('''
    SELECT query_id, query_name, query_definition, last_modified
    FROM saved_queries
    ORDER BY last_modified DESC
''')

results = cursor.fetchall()
print(f'\nFound {len(results)} saved queries:\n')

for row in results:
    query_id, query_name, query_def_str, last_modified = row
    print(f'Query: {query_name} (ID: {query_id})')
    print(f'Last modified: {last_modified}')

    try:
        query_def = json.loads(query_def_str)

        from_table = query_def.get('from_table', 'N/A')
        print(f'FROM: {from_table}')

        joins = query_def.get('joins', [])
        print(f'JOINs: {len(joins)}')

        for idx, join in enumerate(joins, 1):
            print(f'  JOIN #{idx}:')
            print(f'    Type: {join.get("join_type", "N/A")}')
            print(f'    Table: {join.get("table_name", "N/A")}')

            on_conds = join.get('on_conditions', [])
            print(f'    ON Conditions: {len(on_conds)}')

            for cond_idx, cond in enumerate(on_conds, 1):
                left = cond.get('left_field', 'N/A')
                op = cond.get('operator', 'N/A')
                right = cond.get('right_field', 'N/A')
                print(f'      #{cond_idx}: {left} {op} {right}')

        print()
    except json.JSONDecodeError as e:
        print(f'  ERROR: Could not parse query definition: {e}')
        print()

conn.close()
