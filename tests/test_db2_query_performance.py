"""
Test script to find the most efficient way to query DB2 with pyodbc
Simple baseline test: SELECT * FROM LH_BAS_POL LIMIT 100000
"""
import pyodbc
import time

# DB2 connection settings
DSN = "NEON_DSN"
SCHEMA = "DB2TAB"
TABLE = "LH_BAS_POL"
LIMIT = 100000

def test_basic_query():
    """Baseline: Most basic pyodbc query"""
    print("=" * 80)
    print("TEST: Basic pyodbc query")
    print("=" * 80)
    
    # Connect
    conn_start = time.perf_counter()
    conn_str = f"DSN={DSN}"
    conn = pyodbc.connect(conn_str)
    conn_time = time.perf_counter() - conn_start
    print(f"✓ Connection established in {conn_time:.3f}s")
    
    # Create cursor
    cursor = conn.cursor()
    
    # Execute query
    query = f"SELECT * FROM {SCHEMA}.{TABLE} FETCH FIRST {LIMIT} ROWS ONLY"
    print(f"Query: {query}")
    
    exec_start = time.perf_counter()
    cursor.execute(query)
    exec_time = time.perf_counter() - exec_start
    print(f"✓ Query executed in {exec_time:.3f}s")
    
    # Get column info
    col_start = time.perf_counter()
    columns = [column[0] for column in cursor.description]
    col_time = time.perf_counter() - col_start
    print(f"✓ Retrieved {len(columns)} column names in {col_time:.3f}s")
    
    # Fetch data
    fetch_start = time.perf_counter()
    data = cursor.fetchall()
    fetch_time = time.perf_counter() - fetch_start
    
    print(f"✓ Fetched {len(data):,} rows in {fetch_time:.2f}s")
    print(f"  Rate: {len(data) / fetch_time:.0f} rows/second")
    
    # Cleanup
    cursor.close()
    conn.close()
    
    total_time = conn_time + exec_time + col_time + fetch_time
    print(f"\n📊 TOTAL TIME: {total_time:.2f}s")
    print(f"   Overall rate: {len(data) / total_time:.0f} rows/second")
    print()
    
    return total_time


def test_with_arraysize(arraysize=10000):
    """Test with custom cursor.arraysize"""
    print("=" * 80)
    print(f"TEST: With cursor.arraysize = {arraysize}")
    print("=" * 80)
    
    conn_start = time.perf_counter()
    conn_str = f"DSN={DSN}"
    conn = pyodbc.connect(conn_str)
    conn_time = time.perf_counter() - conn_start
    print(f"✓ Connection established in {conn_time:.3f}s")
    
    cursor = conn.cursor()
    cursor.arraysize = arraysize
    print(f"✓ Set cursor.arraysize = {arraysize}")
    
    query = f"SELECT * FROM {SCHEMA}.{TABLE} FETCH FIRST {LIMIT} ROWS ONLY"
    
    exec_start = time.perf_counter()
    cursor.execute(query)
    exec_time = time.perf_counter() - exec_start
    print(f"✓ Query executed in {exec_time:.3f}s")
    
    columns = [column[0] for column in cursor.description]
    
    fetch_start = time.perf_counter()
    data = cursor.fetchall()
    fetch_time = time.perf_counter() - fetch_start
    
    print(f"✓ Fetched {len(data):,} rows in {fetch_time:.2f}s")
    print(f"  Rate: {len(data) / fetch_time:.0f} rows/second")
    
    cursor.close()
    conn.close()
    
    total_time = conn_time + exec_time + fetch_time
    print(f"\n📊 TOTAL TIME: {total_time:.2f}s")
    print(f"   Overall rate: {len(data) / total_time:.0f} rows/second")
    print()
    
    return total_time


def test_with_connection_options():
    """Test with optimized connection string"""
    print("=" * 80)
    print("TEST: With optimized connection string")
    print("=" * 80)
    
    conn_start = time.perf_counter()
    conn_str = f"DSN={DSN};BLOCKSIZE=65535;MAXLOBSIZE=0;DEFERREDPREPARE=1"
    conn = pyodbc.connect(conn_str, autocommit=True)
    conn_time = time.perf_counter() - conn_start
    print(f"✓ Connection established in {conn_time:.3f}s")
    print("  Options: BLOCKSIZE=65535, MAXLOBSIZE=0, DEFERREDPREPARE=1, autocommit=True")
    
    cursor = conn.cursor()
    cursor.arraysize = 10000
    
    query = f"SELECT * FROM {SCHEMA}.{TABLE} FETCH FIRST {LIMIT} ROWS ONLY WITH UR OPTIMIZE FOR {LIMIT} ROWS"
    print(f"  Query hints: WITH UR, OPTIMIZE FOR {LIMIT} ROWS")
    
    exec_start = time.perf_counter()
    cursor.execute(query)
    exec_time = time.perf_counter() - exec_start
    print(f"✓ Query executed in {exec_time:.3f}s")
    
    columns = [column[0] for column in cursor.description]
    
    fetch_start = time.perf_counter()
    data = cursor.fetchall()
    fetch_time = time.perf_counter() - fetch_start
    
    print(f"✓ Fetched {len(data):,} rows in {fetch_time:.2f}s")
    print(f"  Rate: {len(data) / fetch_time:.0f} rows/second")
    
    cursor.close()
    conn.close()
    
    total_time = conn_time + exec_time + fetch_time
    print(f"\n📊 TOTAL TIME: {total_time:.2f}s")
    print(f"   Overall rate: {len(data) / total_time:.0f} rows/second")
    print()
    
    return total_time


def test_chunked_fetch(chunksize=10000):
    """Test fetching in chunks"""
    print("=" * 80)
    print(f"TEST: Chunked fetch with chunksize={chunksize}")
    print("=" * 80)
    
    conn_start = time.perf_counter()
    conn_str = f"DSN={DSN}"
    conn = pyodbc.connect(conn_str)
    conn_time = time.perf_counter() - conn_start
    print(f"✓ Connection established in {conn_time:.3f}s")
    
    cursor = conn.cursor()
    cursor.arraysize = chunksize
    
    query = f"SELECT * FROM {SCHEMA}.{TABLE} FETCH FIRST {LIMIT} ROWS ONLY"
    
    exec_start = time.perf_counter()
    cursor.execute(query)
    exec_time = time.perf_counter() - exec_start
    print(f"✓ Query executed in {exec_time:.3f}s")
    
    columns = [column[0] for column in cursor.description]
    
    # Fetch in chunks
    fetch_start = time.perf_counter()
    all_data = []
    while True:
        chunk = cursor.fetchmany(chunksize)
        if not chunk:
            break
        all_data.extend(chunk)
        # Show progress
        if len(all_data) % (chunksize * 5) == 0:
            elapsed = time.perf_counter() - fetch_start
            rate = len(all_data) / elapsed if elapsed > 0 else 0
            print(f"  ... {len(all_data):,} rows ({rate:.0f} rows/sec)")
    
    fetch_time = time.perf_counter() - fetch_start
    
    print(f"✓ Fetched {len(all_data):,} rows in {fetch_time:.2f}s")
    print(f"  Rate: {len(all_data) / fetch_time:.0f} rows/second")
    
    cursor.close()
    conn.close()
    
    total_time = conn_time + exec_time + fetch_time
    print(f"\n📊 TOTAL TIME: {total_time:.2f}s")
    print(f"   Overall rate: {len(all_data) / total_time:.0f} rows/second")
    print()
    
    return total_time


if __name__ == "__main__":
    print("\n" + "="*80)
    print("DB2 QUERY PERFORMANCE TESTING")
    print(f"Target: {SCHEMA}.{TABLE} ({LIMIT:,} rows)")
    print("="*80 + "\n")
    
    results = {}
    
    # Test 1: Baseline
    try:
        results['Basic'] = test_basic_query()
    except Exception as e:
        print(f"❌ Basic test failed: {e}\n")
    
    # Test 2: With arraysize
    try:
        results['ArraySize=10000'] = test_with_arraysize(10000)
    except Exception as e:
        print(f"❌ ArraySize test failed: {e}\n")
    
    # Test 3: With connection options
    try:
        results['Optimized'] = test_with_connection_options()
    except Exception as e:
        print(f"❌ Optimized test failed: {e}\n")
    
    # Test 4: Chunked fetch
    try:
        results['Chunked'] = test_chunked_fetch(10000)
    except Exception as e:
        print(f"❌ Chunked test failed: {e}\n")
    
    # Summary
    print("\n" + "="*80)
    print("SUMMARY OF RESULTS")
    print("="*80)
    for test_name, time_taken in results.items():
        print(f"{test_name:20s}: {time_taken:6.2f}s")
    
    if results:
        fastest = min(results.items(), key=lambda x: x[1])
        print(f"\n🏆 FASTEST: {fastest[0]} ({fastest[1]:.2f}s)")
