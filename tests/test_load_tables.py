"""Test loading tables from UL_Rates connection"""
from suiteview.core.schema_discovery import get_schema_discovery

schema_discovery = get_schema_discovery()

print("=== Testing Table Discovery for UL_Rates (connection_id=1) ===\n")

try:
    tables = schema_discovery.get_tables(1)
    
    print(f"Found {len(tables)} tables:\n")
    
    if tables:
        for i, table in enumerate(tables[:20], 1):  # Show first 20
            print(f"{i}. {table.get('full_name', table.get('table_name'))}")
            print(f"   Schema: {table.get('schema_name', 'N/A')}")
            print(f"   Type: {table.get('type', 'N/A')}")
            print()
        
        if len(tables) > 20:
            print(f"... and {len(tables) - 20} more tables")
    else:
        print("No tables found!")
        
except Exception as e:
    print(f"Error loading tables: {e}")
    import traceback
    traceback.print_exc()
