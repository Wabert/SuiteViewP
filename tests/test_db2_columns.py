"""Test script to debug DB2 column discovery"""
import sys
import os
import pyodbc

# Add project root to path
project_root = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, project_root)

from suiteview.core.connection_manager import get_connection_manager

def test_db2_columns():
    """Test getting columns from LH_BAS_POL table"""
    print("=" * 80)
    print("DB2 Column Discovery Debug")
    print("=" * 80)
    
    conn_mgr = get_connection_manager()
    
    # Find NEON_DSN connection
    connections = conn_mgr.get_connections()
    neon_conn = None
    for conn in connections:
        if 'NEON' in conn['connection_name'].upper():
            neon_conn = conn
            break
    
    if not neon_conn:
        print("ERROR: NEON_DSN connection not found!")
        return
    
    print(f"Found connection: {neon_conn['connection_name']}")
    print(f"  Connection ID: {neon_conn['connection_id']}")
    
    # Get DSN
    dsn = neon_conn.get('connection_string', '').replace('DSN=', '')
    print(f"  DSN: {dsn}")
    
    # Connect
    conn_str = f"DSN={dsn}"
    conn = pyodbc.connect(conn_str)
    cursor = conn.cursor()
    
    # Query for LH_BAS_POL columns
    table_name = 'LH_BAS_POL'
    schema_name = 'DB2TAB'
    
    print(f"\nQuerying columns for {schema_name}.{table_name}...")
    
    # Simplified query without the complex primary key join
    query = f"""
        SELECT 
            NAME,
            COLTYPE,
            LENGTH,
            SCALE,
            NULLS
        FROM SYSIBM.SYSCOLUMNS
        WHERE TBNAME = '{table_name}'
            AND TBCREATOR = '{schema_name}'
        ORDER BY COLNO
        LIMIT 20
    """
    
    cursor.execute(query)
    
    print(f"\nFirst 10 columns:")
    print("-" * 80)
    
    for i, row in enumerate(cursor.fetchall()[:10], 1):
        col_name = row[0]
        col_type = row[1]
        length = row[2]
        scale = row[3]
        nullable = row[4]
        
        print(f"{i}. {col_name}")
        print(f"   COLTYPE raw value: {repr(col_type)} (type: {type(col_type).__name__})")
        print(f"   LENGTH: {length}")
        print(f"   SCALE: {scale}")
        print(f"   NULLS: {nullable}")
        print()
    
    conn.close()
    
    print("=" * 80)
    print("Test Complete")
    print("=" * 80)

if __name__ == '__main__':
    test_db2_columns()
