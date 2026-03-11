import sqlite3

conn = sqlite3.connect(r'C:\Users\ab7y02\.suiteview\abr_quote.db')
cursor = conn.cursor()

cursor.execute("SELECT COUNT(*) FROM state_variations")
print("Row count in state_variations:", cursor.fetchone()[0])

cursor.execute("SELECT COUNT(*) FROM state_forms")
print("Row count in state_forms:", cursor.fetchone()[0])
