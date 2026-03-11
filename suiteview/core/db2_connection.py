"""
SuiteView - DB2 Connection Manager
Handles ODBC connections to DB2 database via DSN.

Shared infrastructure for PolView, Inforce Illustration, and any other
module that needs DB2 access. Provides connection pooling, Office 365
WITH clause compatibility, and auto-retry on link failures.

Originally from PolView, promoted to shared core.
"""

import pyodbc
from typing import Optional, List, Tuple, Any
from contextlib import contextmanager

from .db2_constants import REGION_DSN_MAP, DEFAULT_REGION, REGION_SCHEMA_MAP, DEFAULT_SCHEMA


class DB2ConnectionError(Exception):
    """Custom exception for DB2 connection errors."""
    pass


class DB2Connection:
    """
    Manages DB2 database connections via ODBC DSN.
    
    Uses connection pooling and handles the Office 365 WITH clause requirement.
    """
    
    # Class-level connection cache (region -> connection)
    _connections: dict = {}
    
    def __init__(self, region: str = DEFAULT_REGION):
        """
        Initialize connection manager for specified region.
        
        Args:
            region: Region code (CKPR, CKMO, CKAS, CKSR, CKCS)
        """
        self.region = region.upper()
        self._connection: Optional[pyodbc.Connection] = None
        
    @property
    def dsn(self) -> str:
        """Get the DSN name for the current region."""
        if self.region not in REGION_DSN_MAP:
            raise DB2ConnectionError(f"Unknown region: {self.region}")
        return REGION_DSN_MAP[self.region]
    
    def connect(self) -> pyodbc.Connection:
        """
        Establish connection to DB2 database.
        
        Returns:
            Active pyodbc Connection object
            
        Raises:
            DB2ConnectionError: If connection fails
        """
        # Check if we have a cached connection for this region
        if self.region in DB2Connection._connections:
            conn = DB2Connection._connections[self.region]
            try:
                # Test if connection is still alive
                conn.execute("SELECT 1 FROM SYSIBM.SYSDUMMY1")
                self._connection = conn
                return conn
            except Exception:
                # Connection is dead, remove from cache
                del DB2Connection._connections[self.region]
        
        # Create new connection
        try:
            connection_string = f"DSN={self.dsn}"
            self._connection = pyodbc.connect(connection_string, autocommit=True)
            
            # Cache the connection
            DB2Connection._connections[self.region] = self._connection
            
            return self._connection
            
        except pyodbc.Error as e:
            raise DB2ConnectionError(
                f"Failed to connect to {self.dsn}: {str(e)}"
            ) from e
    
    def close(self):
        """Close the connection."""
        if self._connection:
            try:
                self._connection.close()
            except Exception:
                pass
            finally:
                self._connection = None
                if self.region in DB2Connection._connections:
                    del DB2Connection._connections[self.region]
    
    @staticmethod
    def close_all():
        """Close all cached connections."""
        for region, conn in list(DB2Connection._connections.items()):
            try:
                conn.close()
            except Exception:
                pass
        DB2Connection._connections.clear()
    
    def _add_with_clause(self, sql: str) -> str:
        """
        Add WITH clause for Office 365 compatibility and apply
        region-specific schema replacement.
        
        All queries must have a WITH clause to avoid Automation Error.
        If the query doesn't already have one, add a benign WITH clause.
        
        Non-default regions (CKAS, CKCS, CKSR) use a different DB2 schema
        instead of 'DB2TAB'.  This method transparently rewrites the
        schema qualifier so callers can always write 'DB2TAB.<table>'.
        
        Args:
            sql: Original SQL query
            
        Returns:
            SQL with WITH clause prepended (if needed) and schema replaced
        """
        # Schema replacement (must happen first, before the WITH clause
        # is checked, so that the WITH dummy table also gets the right schema)
        schema = REGION_SCHEMA_MAP.get(self.region, DEFAULT_SCHEMA)
        if schema != DEFAULT_SCHEMA:
            # Case-insensitive replacement of 'DB2TAB.' with '<schema>.'
            import re
            sql = re.sub(r'(?i)DB2TAB\.', f'{schema}.', sql)

        sql_upper = sql.strip().upper()
        
        # If already has WITH clause, return as-is
        if sql_upper.startswith("WITH"):
            return sql
            
        # Add benign WITH clause
        return f"WITH DUMBY AS (SELECT 1 FROM SYSIBM.SYSDUMMY1) {sql}"
    
    def execute_query(self, sql: str, params: tuple = None) -> List[Tuple]:
        """
        Execute a query and return all results as a list of tuples.
        
        Args:
            sql: SQL query string
            params: Optional query parameters
            
        Returns:
            List of row tuples
        """
        conn = self.connect()
        sql = self._add_with_clause(sql)
        
        try:
            cursor = conn.cursor()
            if params:
                cursor.execute(sql, params)
            else:
                cursor.execute(sql)
            
            rows = cursor.fetchall()
            cursor.close()
            return rows
            
        except pyodbc.Error as e:
            # Check for communication link failure
            error_code = e.args[0] if e.args else ""
            if "08S01" in str(error_code) or "-2147467259" in str(e):
                # Refresh connection and retry once
                self.close()
                conn = self.connect()
                cursor = conn.cursor()
                if params:
                    cursor.execute(sql, params)
                else:
                    cursor.execute(sql)
                rows = cursor.fetchall()
                cursor.close()
                return rows
            raise
    
    def execute_query_with_headers(self, sql: str, params: tuple = None) -> Tuple[List[str], List[Tuple]]:
        """
        Execute a query and return column headers along with results.
        
        Args:
            sql: SQL query string
            params: Optional query parameters
            
        Returns:
            Tuple of (column_names, rows)
        """
        conn = self.connect()
        sql = self._add_with_clause(sql)
        
        try:
            cursor = conn.cursor()
            if params:
                cursor.execute(sql, params)
            else:
                cursor.execute(sql)
            
            # Get column names from cursor description
            columns = [desc[0] for desc in cursor.description] if cursor.description else []
            rows = cursor.fetchall()
            cursor.close()
            
            return columns, rows
            
        except pyodbc.Error as e:
            error_code = e.args[0] if e.args else ""
            if "08S01" in str(error_code) or "-2147467259" in str(e):
                self.close()
                conn = self.connect()
                cursor = conn.cursor()
                if params:
                    cursor.execute(sql, params)
                else:
                    cursor.execute(sql)
                columns = [desc[0] for desc in cursor.description] if cursor.description else []
                rows = cursor.fetchall()
                cursor.close()
                return columns, rows
            raise
    
    def execute_query_as_dict(self, sql: str, params: tuple = None) -> List[dict]:
        """
        Execute a query and return results as list of dictionaries.
        
        Args:
            sql: SQL query string
            params: Optional query parameters
            
        Returns:
            List of dictionaries with column names as keys
        """
        columns, rows = self.execute_query_with_headers(sql, params)
        return [dict(zip(columns, row)) for row in rows]
    
    def execute_scalar(self, sql: str, params: tuple = None) -> Any:
        """
        Execute a query and return single scalar value.
        
        Args:
            sql: SQL query string
            params: Optional query parameters
            
        Returns:
            First column of first row, or None if no results
        """
        rows = self.execute_query(sql, params)
        if rows and rows[0]:
            return rows[0][0]
        return None


@contextmanager
def db_connection(region: str = DEFAULT_REGION):
    """
    Context manager for database connections.
    
    Usage:
        with db_connection("CKPR") as db:
            results = db.execute_query("SELECT * FROM ...")
    """
    db = DB2Connection(region)
    try:
        db.connect()
        yield db
    finally:
        # Don't close - let the connection be reused
        pass


def test_connection(region: str = DEFAULT_REGION) -> bool:
    """
    Test if connection to region is working.
    
    Args:
        region: Region code to test
        
    Returns:
        True if connection successful, False otherwise
    """
    try:
        db = DB2Connection(region)
        db.connect()
        db.execute_query("SELECT 1 FROM SYSIBM.SYSDUMMY1")
        return True
    except Exception:
        return False


def get_available_dsns() -> List[str]:
    """
    Get list of available ODBC DSNs on the system.
    
    Returns:
        List of DSN names
    """
    try:
        return [x[0] for x in pyodbc.dataSources().items()]
    except Exception:
        return []


def sql_for_region(sql: str, region: str) -> str:
    """Apply region-specific schema replacement to a SQL string.

    Replaces occurrences of 'DB2TAB.' with the correct schema qualifier
    for the given region (e.g. 'CKSR.' for CKSR, 'UNIT.' for CKAS).
    Regions that use DB2TAB (CKPR, CKMO) are returned unchanged.

    This is the standalone equivalent of ``DB2Connection._add_with_clause``'s
    schema logic — useful when building SQL outside a ``DB2Connection``
    instance.

    Args:
        sql:    SQL string with 'DB2TAB.' table qualifiers.
        region: Region code (e.g. 'CKSR', 'CKAS').

    Returns:
        SQL with schema qualifiers replaced as needed.
    """
    schema = REGION_SCHEMA_MAP.get(region.upper(), DEFAULT_SCHEMA)
    if schema != DEFAULT_SCHEMA:
        import re
        sql = re.sub(r'(?i)DB2TAB\.', f'{schema}.', sql)
    return sql
