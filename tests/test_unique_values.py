"""Test getting unique values from SQL Server table"""
from suiteview.core.schema_discovery import get_schema_discovery

schema_discovery = get_schema_discovery()

print("=== Testing Unique Values for CYBERLIFE_DRF ===\n")

# Get columns first to see what's available
try:
    columns = schema_discovery.get_columns(1, 'CYBERLIFE_DRF', 'dbo')
    print(f"Found {len(columns)} columns:\n")
    for col in columns[:10]:  # Show first 10
        print(f"  - {col['column_name']} ({col['data_type']})")
    
    if len(columns) > 10:
        print(f"  ... and {len(columns) - 10} more columns\n")
    
    # Try to get unique values from first column
    if columns:
        # Try a few different columns
        test_columns = ['Record_Type', 'UserDefined', 'IssueAge']
        
        for test_col in test_columns:
            # Check if column exists
            col_exists = any(c['column_name'] == test_col for c in columns)
            if not col_exists:
                continue
                
            print(f"\n=== Getting unique values for column: {test_col} ===\n")
            
            unique_vals = schema_discovery.get_unique_values(1, 'CYBERLIFE_DRF', test_col, 'dbo', limit=20)
            
            print(f"Found {len(unique_vals)} unique values:\n")
            for i, val in enumerate(unique_vals[:20], 1):
                print(f"{i}. {val}")
            
            if len(unique_vals) == 0:
                print("No unique values found (column might be all NULL)")
                
except Exception as e:
    print(f"Error: {e}")
    import traceback
    traceback.print_exc()
