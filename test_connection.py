"""Test SQL Server connection"""
from suiteview.core.connection_manager import get_connection_manager

conn_mgr = get_connection_manager()

# Get connection ID 1 (UL_Rates)
connection = conn_mgr.repo.get_connection(1)

print("=== Connection Details ===")
print(f"Name: {connection['connection_name']}")
print(f"Type: {connection['connection_type']}")
print(f"Server: {connection['server_name']}")
print(f"Database: {connection['database_name']}")
print(f"Connection String: {connection['connection_string']}")
print(f"Auth Type: {connection['auth_type']}")

# Build connection string
conn_string = conn_mgr._build_connection_string(connection)
print(f"\n=== Built Connection String ===")
print(conn_string)

# Test connection
print(f"\n=== Testing Connection ===")
try:
    from sqlalchemy import text
    engine = conn_mgr.get_engine(1)
    with engine.connect() as conn:
        result = conn.execute(text("SELECT @@VERSION"))
        version = result.scalar()
        print(f"✓ Connected successfully!")
        print(f"SQL Server Version: {version}")
except Exception as e:
    print(f"✗ Connection failed: {e}")
    print(f"\nPossible issues:")
    print(f"1. SQL Server 'UL_Rates' is not running")
    print(f"2. DSN 'UL_Rates' is not configured correctly")
    print(f"3. Network/firewall blocking connection")
    print(f"4. SQL Server not configured for remote connections")
