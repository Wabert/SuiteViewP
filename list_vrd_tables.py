"""Quick script to list all tables from VRD SQL Server connection"""

import sys
sys.path.insert(0, '.')

from suiteview.core.connection_manager import get_connection_manager
from suiteview.core.schema_discovery import get_schema_discovery

def main():
    conn_manager = get_connection_manager()
    schema_discovery = get_schema_discovery()
    
    # Get all connections
    connections = conn_manager.repo.get_all_connections()
    
    print("=" * 60)
    print("Available Connections:")
    print("=" * 60)
    
    vrd_connection_id = None
    for conn in connections:
        # Handle different formats - could be dict or tuple
        if isinstance(conn, dict):
            conn_id = conn.get('id') or conn.get('connection_id')
            conn_name = conn.get('connection_name', 'Unknown')
            conn_type = conn.get('connection_type', 'Unknown')
        else:
            # Assume it's a tuple/list
            print(f"  Raw connection data: {conn}")
            conn_id = conn[0] if len(conn) > 0 else None
            conn_name = conn[1] if len(conn) > 1 else 'Unknown'
            conn_type = conn[2] if len(conn) > 2 else 'Unknown'
        
        print(f"  ID: {conn_id}, Name: {conn_name}, Type: {conn_type}")
        # Look for VRD or SQL_SERVER connection
        if conn_name and ('VRD' in conn_name.upper() or 'SQL' in str(conn_type).upper()):
            vrd_connection_id = conn_id
            print(f"    ^ Selected this one for table listing")
    
    if not vrd_connection_id:
        print("\nNo VRD/SQL Server connection found!")
        return
    
    print("\n" + "=" * 60)
    print(f"Tables in connection ID {vrd_connection_id}:")
    print("=" * 60)
    
    try:
        tables = schema_discovery.get_tables(vrd_connection_id)
        
        # Group by schema
        by_schema = {}
        for table in tables:
            schema = table.get('schema_name', 'dbo')
            if schema not in by_schema:
                by_schema[schema] = []
            by_schema[schema].append(table.get('table_name', 'UNKNOWN'))
        
        # Print grouped
        for schema in sorted(by_schema.keys()):
            print(f"\nSchema: {schema}")
            print("-" * 40)
            for table_name in sorted(by_schema[schema]):
                # Highlight CENSUS tables
                if 'CENSUS' in table_name.upper():
                    print(f"  >>> {table_name} <<<")
                else:
                    print(f"  {table_name}")
        
        print(f"\nTotal: {len(tables)} tables")
        
    except Exception as e:
        print(f"Error getting tables: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    main()
