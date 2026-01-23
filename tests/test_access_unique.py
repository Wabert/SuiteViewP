"""Test script to check Access unique values functionality"""

import os
import sys
import logging
from pathlib import Path

# Add parent directory to path so we can import suiteview
sys.path.insert(0, str(Path(__file__).parent.parent))

# Set up logging
logging.basicConfig(level=logging.DEBUG)

from suiteview.core.schema_discovery import SchemaDiscovery
from suiteview.data.repositories import ConnectionRepository

def test_access_unique_values():
    """Test getting unique values from Access database"""
    print("=" * 60)
    print("Testing Access Unique Values")
    print("=" * 60)
    
    conn_repo = ConnectionRepository()
    schema_discovery = SchemaDiscovery()
    
    # Get all connections
    connections = conn_repo.get_all_connections()
    
    # Find the Access connection
    access_conn = None
    for conn in connections:
        if conn['connection_type'] == 'ACCESS':
            access_conn = conn
            break
    
    if not access_conn:
        print("❌ No Access connection found!")
        return
    
    print(f"\n✓ Found Access connection: {access_conn['connection_name']}")
    print(f"  Connection ID: {access_conn['connection_id']}")
    print(f"  File path: {access_conn['connection_string']}")
    
    # Check if file exists
    file_path = access_conn['connection_string']
    if not os.path.exists(file_path):
        print(f"❌ File does not exist: {file_path}")
        return
    
    print(f"  ✓ File exists")
    
    # Get tables
    print(f"\nFetching tables...")
    try:
        tables = schema_discovery.get_tables(access_conn['connection_id'])
        print(f"✓ Found {len(tables)} tables:")
        for table in tables[:5]:
            print(f"  - {table}")
        if len(tables) > 5:
            print(f"  ... and {len(tables) - 5} more")
    except Exception as e:
        print(f"❌ Error getting tables: {e}")
        return
    
    if not tables:
        print("❌ No tables found!")
        return
    
    # Pick first table
    test_table = tables[0]['table_name']  # Extract table name from dict
    print(f"\nTesting with table: {test_table}")
    
    # Get columns
    print(f"Fetching columns...")
    try:
        columns = schema_discovery.get_columns(access_conn['connection_id'], test_table)
        print(f"✓ Found {len(columns)} columns:")
        for col in columns[:5]:
            print(f"  - {col['column_name']} ({col['data_type']})")
        if len(columns) > 5:
            print(f"  ... and {len(columns) - 5} more")
    except Exception as e:
        print(f"❌ Error getting columns: {e}")
        import traceback
        traceback.print_exc()
        return
    
    if not columns:
        print("❌ No columns found!")
        return
    
    # Try to get unique values for first column
    test_column = columns[0]['column_name']
    print(f"\nTesting unique values for column: {test_column}")
    
    try:
        unique_values = schema_discovery.get_unique_values(
            access_conn['connection_id'],
            test_table,
            test_column
        )
        
        print(f"✓ Found {len(unique_values)} unique values:")
        for val in unique_values[:10]:
            print(f"  - {val}")
        if len(unique_values) > 10:
            print(f"  ... and {len(unique_values) - 10} more")
        
    except Exception as e:
        print(f"❌ Error getting unique values: {e}")
        import traceback
        traceback.print_exc()
        return
    
    print("\n" + "=" * 60)
    print("✓ Test Complete!")
    print("=" * 60)

if __name__ == '__main__':
    test_access_unique_values()
