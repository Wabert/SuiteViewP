"""Test script to debug DB2 table discovery for NEON_DSN"""
import sys
import os

# Add project root to path
project_root = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, project_root)

from suiteview.core.connection_manager import get_connection_manager
from suiteview.core.schema_discovery import get_schema_discovery
from sqlalchemy import text

def test_db2_tables():
    """Test different DB2 queries to find LH_BAS_POL table"""
    print("=" * 80)
    print("DB2 Table Discovery Debug")
    print("=" * 80)
    
    conn_mgr = get_connection_manager()
    schema_discovery = get_schema_discovery()
    
    # Find NEON_DSN connection
    connections = conn_mgr.get_connections()
    neon_conn = None
    for conn in connections:
        if 'NEON' in conn['connection_name'].upper():
            neon_conn = conn
            break
    
    if not neon_conn:
        print("❌ NEON_DSN connection not found!")
        print("\nAvailable connections:")
        for conn in connections:
            print(f"  - {conn['connection_name']} ({conn['connection_type']})")
        return
    
    print(f"✓ Found connection: {neon_conn['connection_name']}")
    print(f"  Connection ID: {neon_conn['connection_id']}")
    print(f"  Type: {neon_conn['connection_type']}")
    
    connection_id = neon_conn['connection_id']
    
    # Test 1: Use schema_discovery to get tables
    print("\n" + "=" * 80)
    print("Test 1: Getting tables via schema_discovery.get_tables()")
    print("=" * 80)
    
    try:
        tables = schema_discovery.get_tables(connection_id)
        print(f"✓ Found {len(tables)} tables")
        
        # Look for LH_BAS_POL
        found_target = False
        for table in tables:
            table_name = table['table_name']
            schema_name = table.get('schema_name', '')
            
            if 'LH_BAS_POL' in table_name:
                print(f"\n✓✓✓ FOUND TARGET TABLE: {schema_name}.{table_name}")
                found_target = True
                
            # Show tables starting with LH_
            if table_name.startswith('LH_'):
                print(f"  LH_ table: {schema_name}.{table_name}")
        
        if not found_target:
            print("\n❌ LH_BAS_POL not found in results")
            print("\nFirst 20 tables returned:")
            for i, table in enumerate(tables[:20], 1):
                print(f"  {i}. {table.get('schema_name', '')}.{table['table_name']}")
        else:
            print(f"\n✓✓✓ SUCCESS! LH_BAS_POL table was found!")
    
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()
    
    print("\n" + "=" * 80)
    print("Test Complete")
    print("=" * 80)

if __name__ == '__main__':
    test_db2_tables()
