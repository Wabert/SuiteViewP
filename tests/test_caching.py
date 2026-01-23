"""Test script to verify metadata caching functionality"""

import os
import sys

# Add project root to path
project_root = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, project_root)

from suiteview.data.repositories import get_metadata_cache_repository

def test_caching():
    """Test the metadata caching functionality"""
    print("=" * 60)
    print("Testing Metadata Caching")
    print("=" * 60)
    
    cache_repo = get_metadata_cache_repository()
    
    # Test with a sample table (assuming connection_id 1 exists)
    connection_id = 1
    table_name = "TestTable"
    schema_name = "dbo"
    
    # Create metadata entry
    print(f"\n1. Creating metadata entry for {schema_name}.{table_name}")
    metadata_id = cache_repo.get_or_create_metadata(connection_id, table_name, schema_name)
    print(f"   Metadata ID: {metadata_id}")
    
    # Cache some column data
    print(f"\n2. Caching column metadata")
    test_columns = [
        {'name': 'ID', 'type': 'int', 'nullable': False, 'primary_key': True, 'max_length': None},
        {'name': 'Name', 'type': 'varchar', 'nullable': True, 'primary_key': False, 'max_length': 100},
        {'name': 'Status', 'type': 'varchar', 'nullable': True, 'primary_key': False, 'max_length': 50}
    ]
    cache_repo.cache_column_metadata(metadata_id, test_columns)
    print(f"   Cached {len(test_columns)} columns")
    
    # Retrieve cached columns
    print(f"\n3. Retrieving cached columns")
    cached = cache_repo.get_cached_columns(metadata_id)
    if cached:
        print(f"   Retrieved {len(cached)} columns:")
        for col in cached:
            print(f"   - {col['name']}: {col['type']} (nullable={col['nullable']}, pk={col['primary_key']})")
    else:
        print("   No cached data found")
    
    # Cache unique values
    print(f"\n4. Caching unique values for 'Status' column")
    unique_values = ['Active', 'Inactive', 'Pending', 'Cancelled']
    cache_repo.cache_unique_values(metadata_id, 'Status', unique_values)
    print(f"   Cached {len(unique_values)} unique values")
    
    # Retrieve cached unique values
    print(f"\n5. Retrieving cached unique values")
    cached_unique = cache_repo.get_cached_unique_values(metadata_id, 'Status')
    if cached_unique:
        print(f"   Retrieved {cached_unique['value_count']} unique values:")
        print(f"   Values: {cached_unique['unique_values']}")
        print(f"   Cached at: {cached_unique['cached_at']}")
    else:
        print("   No cached unique values found")
    
    # Test metadata timestamp
    print(f"\n6. Getting metadata timestamp")
    timestamp = cache_repo.get_metadata_cached_at(metadata_id)
    print(f"   Last cached at: {timestamp}")
    
    # Clear cache
    print(f"\n7. Clearing cache")
    cache_repo.clear_column_cache(metadata_id)
    print("   Cache cleared")
    
    # Verify cache is cleared
    print(f"\n8. Verifying cache is cleared")
    cached_after_clear = cache_repo.get_cached_columns(metadata_id)
    if cached_after_clear:
        print(f"   WARNING: Still found {len(cached_after_clear)} cached columns")
    else:
        print("   ✓ Cache successfully cleared")
    
    print("\n" + "=" * 60)
    print("Test Complete!")
    print("=" * 60)

if __name__ == '__main__':
    test_caching()
