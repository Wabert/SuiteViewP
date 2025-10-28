import sqlite3

db_path = r'C:\Users\ab7y02\.suiteview\suiteview.db'
conn = sqlite3.connect(db_path)
cursor = conn.cursor()

print("=== Connections in database ===")
cursor.execute('SELECT connection_id, connection_name, connection_type, server_name, database_name, is_active FROM connections')
for row in cursor.fetchall():
    print(f'ID: {row[0]}, Name: {row[1]}, Type: {row[2]}, Server: {row[3]}, Database: {row[4]}, Active: {row[5]}')

conn.close()
