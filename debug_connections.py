"""Debug script to check connection loading"""
from suiteview.core.connection_manager import get_connection_manager

# Get connection manager
conn_mgr = get_connection_manager()

# Get all connections
connections = conn_mgr.get_connections()

print(f"\n=== Found {len(connections)} connections ===\n")

for conn in connections:
    print(f"ID: {conn['connection_id']}")
    print(f"Name: {conn['connection_name']}")
    print(f"Type: {conn['connection_type']}")
    print(f"Server: {conn['server_name']}")
    print(f"Database: {conn['database_name']}")
    print(f"Active: {conn['is_active']}")
    print("-" * 50)

# Test grouping logic
type_groups = {
    'ODBC': [],
    'SQL_SERVER': [],
    'DB2': [],
    'EXCEL': [],
    'ACCESS': [],
    'CSV': [],
    'FIXED_WIDTH': []
}

# Group connections
for conn in connections:
    conn_type = conn['connection_type']
    if conn_type in type_groups:
        type_groups[conn_type].append(conn)
    else:
        print(f"WARNING: Unknown connection type: {conn_type}")

print("\n=== Grouped connections ===\n")
for group_type, group_conns in type_groups.items():
    if group_conns:
        print(f"{group_type}: {len(group_conns)} connections")
        for conn in group_conns:
            print(f"  - {conn['connection_name']}")

# Test ODBC combined logic
combined_conns = (type_groups.get('ODBC', []) +
                type_groups.get('SQL_SERVER', []) +
                type_groups.get('DB2', []))
print(f"\n=== Combined ODBC group: {len(combined_conns)} connections ===")
for conn in combined_conns:
    print(f"  - {conn['connection_name']}")
