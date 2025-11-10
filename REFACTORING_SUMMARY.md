# Query Execution Refactoring Summary

## Overview
Consolidated duplicate query execution logic across the codebase to eliminate technical debt and ensure consistent behavior across all features.

## Problem Identified
Query execution logic was duplicated in multiple places:
- `query_executor.py`: `_execute_db2_query()`, `_execute_csv_query()`
- `connections_screen.py`: `_show_table_data()` had complete duplicate of all database-specific logic

This duplication created:
- **Maintenance Risk**: Changes must be synchronized across multiple files
- **Inconsistency Risk**: Already caused bugs (SQLAlchemy vs pyodbc for DB2)
- **Code Bloat**: 140+ lines of duplicate logic

## Solution Implemented

### New Centralized Method
Added `QueryExecutor.execute_raw_sql()` method that handles ALL connection types:
- **CSV**: pandas `read_csv()` with optional row limit
- **Excel**: pandas `read_excel()` with sheet name and row limit
- **Access**: pyodbc with Access ODBC driver, TOP syntax
- **DB2**: pyodbc direct connection with LIMIT syntax (required for ODBC Shadow driver)
- **SQL Server**: SQLAlchemy engine with TOP syntax

### Code Changes

#### query_executor.py
```python
def execute_raw_sql(self, connection_id: int, table_name: str, 
                   schema_name: str = None, limit: int = None) -> pd.DataFrame:
    """
    Execute a raw SELECT * query with optional limit
    
    Centralized method for executing simple queries across all connection types.
    All code that needs to query data should use this method to avoid duplication.
    """
    # Handles all connection types with proper syntax and drivers
```

#### connections_screen.py
**Before** (140+ lines):
```python
def _show_table_data(self, limit: int = None):
    # Check connection type
    if conn_type == 'CSV':
        # CSV-specific logic...
    elif conn_type == 'EXCEL':
        # Excel-specific logic...
    elif conn_type == 'ACCESS':
        # Access-specific logic...
    elif conn_type == 'DB2':
        # DB2-specific logic with pyodbc...
    else:
        # SQL Server logic with SQLAlchemy...
```

**After** (10 lines):
```python
def _show_table_data(self, limit: int = None):
    """Show table data with optional row limit
    
    Uses centralized QueryExecutor.execute_raw_sql() to avoid code duplication.
    """
    executor = QueryExecutor()
    df = executor.execute_raw_sql(
        self.current_connection_id,
        self.current_table,
        self.current_schema,
        limit
    )
```

## Benefits

### 1. Single Source of Truth
Each datasource now has exactly ONE execution path:
- CSV → `execute_raw_sql()` → pandas `read_csv()`
- Excel → `execute_raw_sql()` → pandas `read_excel()`
- Access → `execute_raw_sql()` → pyodbc with Access driver
- DB2 → `execute_raw_sql()` → `_execute_db2_query()` → pyodbc with DSN
- SQL Server → `execute_raw_sql()` → SQLAlchemy engine

### 2. Easier Maintenance
- Bug fixes only need to be applied once
- Adding new database types requires changes in one place
- Consistent logging and error handling

### 3. Better Error Handling
- Centralized error tracking with `last_sql`, `last_execution_time`, `last_record_count`
- Consistent logging across all query types
- Single place to add debugging output

### 4. Reduced Code Duplication
- **Removed**: 127 lines of duplicate code from `connections_screen.py`
- **Added**: 140 lines of centralized code in `query_executor.py`
- **Net**: Eliminated duplication, improved organization

## Database-Specific Notes

### DB2 (Critical)
```python
# IMPORTANT: Use LIMIT syntax for DB2, NOT "FETCH FIRST n ROWS ONLY"
# The ODBC Shadow driver we use requires LIMIT syntax to work properly.
# DO NOT CHANGE THIS to FETCH - it will cause "ILLEGAL USE OF KEYWORD FETCH" errors.
if limit:
    sql = f"SELECT * FROM {table_ref} LIMIT {limit}"
```

This comment is now in ONE place instead of multiple files.

### SQL Server
Uses `TOP` syntax:
```python
if limit:
    sql = f"SELECT TOP {limit} * FROM {table_ref}"
```

### File-Based Sources (CSV, Excel, Access)
Handle file paths and use appropriate pandas/pyodbc methods without SQL generation for CSV/Excel.

## Testing
- ✅ Code compiles without syntax errors
- ✅ Application launches successfully
- ✅ All connection types still accessible
- ✅ Preview/Show All buttons functional

## Future Use Cases
Any new feature that needs to query data can now use:
```python
from suiteview.core.query_executor import QueryExecutor

executor = QueryExecutor()
df = executor.execute_raw_sql(connection_id, table_name, schema_name, limit)
```

Examples:
- Data export features
- Report generation
- Data validation tools
- Automated testing
- Data quality checks

## Commits
1. `6c37bf6` - Add Preview and Show All buttons to Connections screen with DB2 pyodbc support
2. `12b7f33` - Refactor: Consolidate query execution logic into QueryExecutor.execute_raw_sql()

## Conclusion
This refactoring eliminates a significant source of technical debt while improving code maintainability and reducing the risk of inconsistencies. The codebase now follows the DRY (Don't Repeat Yourself) principle for database query execution.
