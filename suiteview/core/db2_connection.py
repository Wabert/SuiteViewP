"""
SuiteView - DB2 Connection Manager
Handles ODBC connections to DB2 database via DSN.

Shared infrastructure for PolView, Inforce Illustration, and any other
module that needs DB2 access. Provides connection pooling, Office 365
WITH clause compatibility, and auto-retry on link failures.

Originally from PolView, promoted to shared core.
"""

from typing import Optional, List, Tuple, Any
from contextlib import contextmanager
import logging
import re
import sqlite3

from .db2_constants import REGION_DSN_MAP, DEFAULT_REGION, REGION_SCHEMA_MAP, DEFAULT_SCHEMA
from .data_access.connections import connection_factory
from .data_access.errors import ConnectionUnavailable
from .local_dev import local_data_enabled
from .sql_permissions import guard_query_sql
import pyodbc

logger = logging.getLogger(__name__)


class DB2ConnectionError(ConnectionUnavailable):
    """Custom exception for DB2 connection errors."""


def _clean_odbc_message(message: str) -> str:
    """Remove NUL-padded driver-buffer data from an ODBC message."""
    return message.split("\x00", 1)[0].strip()


def _extract_odbc_message(exc: BaseException) -> str:
    """Walk the exception chain and extract the real ODBC driver message.

    pyodbc sometimes triggers a SystemError that wraps the actual
    pyodbc.Error.  This function digs through __cause__ and __context__
    to find the most informative message.
    """
    # Collect all exceptions in the chain
    seen = []
    e = exc
    while e is not None:
        seen.append(e)
        e = getattr(e, '__cause__', None) or getattr(e, '__context__', None)
        if e in seen:
            break

    # Prefer pyodbc.Error with args[1] (driver message)
    for e in seen:
        if isinstance(e, pyodbc.Error) and len(getattr(e, 'args', ())) >= 2:
            msg = e.args[1]
            if isinstance(msg, str) and msg:
                msg = _clean_odbc_message(msg)
                state = e.args[0]
                if (isinstance(state, str) and re.fullmatch(r"[A-Z0-9]{5}", state)
                        and state not in msg):
                    msg = f"[{state}] {msg}"
                return msg

    # Fallback: any exception with a useful args[1]
    for e in seen:
        if len(getattr(e, 'args', ())) >= 2 and isinstance(e.args[1], str):
            return _clean_odbc_message(e.args[1])

    # Some DB2 ODBC failures provide the complete driver message as their only
    # argument while a SystemError supplies the unhelpful outer message.
    for e in seen:
        if isinstance(e, pyodbc.Error):
            for arg in getattr(e, "args", ()):
                if isinstance(arg, str) and arg:
                    return _clean_odbc_message(arg)

    # Last resort: str() of the original
    return _clean_odbc_message(str(exc))


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
        self._connection: Optional[Any] = None
        
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
        if local_data_enabled():
            if self.region in DB2Connection._connections:
                conn = DB2Connection._connections[self.region]
                try:
                    conn.execute("SELECT 1 FROM SYSIBM.SYSDUMMY1")
                    self._connection = conn
                    return conn
                except (pyodbc.Error, sqlite3.Error, OSError):
                    logger.debug("Discarding dead cached local DB2 connection for %s", self.region, exc_info=True)
                    del DB2Connection._connections[self.region]

            try:
                self._connection = connection_factory.connect_policy_db2(self.region)
                DB2Connection._connections[self.region] = self._connection
                return self._connection
            except ConnectionUnavailable as e:
                raise DB2ConnectionError(
                    str(e)
                ) from e

        # Check if we have a cached connection for this region
        if self.region in DB2Connection._connections:
            conn = DB2Connection._connections[self.region]
            try:
                # Test if connection is still alive
                conn.execute("SELECT 1 FROM SYSIBM.SYSDUMMY1")
                self._connection = conn
                return conn
            except (pyodbc.Error, SystemError, OSError):
                logger.debug("Discarding dead cached DB2 connection for %s", self.region, exc_info=True)
                # Connection is dead, remove from cache
                del DB2Connection._connections[self.region]
        
        # Create new connection
        try:
            self._connection = connection_factory.connect_policy_db2(
                self.region, autocommit=True,
            )
            
            # Cache the connection
            DB2Connection._connections[self.region] = self._connection
            
            return self._connection

        except ConnectionUnavailable as e:
            msg = _extract_odbc_message(e)
            raise DB2ConnectionError(
                f"Failed to connect to {self.dsn}: {msg}"
            ) from e

        except pyodbc.Error as e:
            # Direct pyodbc error — driver message is in args[1]
            msg = _extract_odbc_message(e)
            raise DB2ConnectionError(
                f"Failed to connect to {self.dsn}: {msg}"
            ) from e

        except SystemError as e:
            # pyodbc bug: sometimes raises SystemError wrapping the real error.
            # Try to dig the pyodbc.Error out of the exception context.
            msg = _extract_odbc_message(e)
            if "returned a result" in msg:
                # Could not extract real message — provide a helpful fallback
                msg = (
                    "The ODBC driver failed without a usable diagnostic. "
                    "Retry the connection or test the DSN in ODBC Manager."
                )
            raise DB2ConnectionError(
                f"Failed to connect to {self.dsn}: {msg}"
            ) from e

        except Exception as e:
            raise DB2ConnectionError(
                f"Failed to connect to {self.dsn}: {_extract_odbc_message(e)}"
            ) from e
    
    def close(self):
        """Close the connection."""
        if self._connection:
            try:
                self._connection.close()
            except (pyodbc.Error, sqlite3.Error, OSError, AttributeError):
                logger.debug("Ignoring DB2 connection close failure during cleanup", exc_info=True)
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
            except (pyodbc.Error, sqlite3.Error, OSError, AttributeError):
                logger.debug("Ignoring cached DB2 connection close failure during cleanup", exc_info=True)
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
    
    @staticmethod
    def _is_link_failure(e: pyodbc.Error) -> bool:
        """True if the error is a communication-link failure worth retrying once."""
        error_code = e.args[0] if e.args else ""
        return "08S01" in str(error_code) or "-2147467259" in str(e)

    def _run(self, sql: str, params: tuple = None) -> Tuple[List[str], List[Tuple]]:
        """Execute one statement and return (column_names, rows).

        The cursor is always closed (even on error) to avoid leaks.
        """
        guard_query_sql(sql)
        conn = self.connect()
        cursor = conn.cursor()
        try:
            if params:
                cursor.execute(sql, params)
            else:
                cursor.execute(sql)
            columns = [desc[0] for desc in cursor.description] if cursor.description else []
            rows = cursor.fetchall()
            return columns, rows
        finally:
            cursor.close()

    def _prepare_sql(self, sql: str) -> str:
        """Apply schema rewrite, WITH clause, and local-dev LIMIT rewrite."""
        sql = self._add_with_clause(sql)
        if local_data_enabled():
            sql = re.sub(
                r"\s+FETCH\s+FIRST\s+(\d+)\s+ROWS\s+ONLY\s*$",
                r" LIMIT \1",
                sql,
                flags=re.IGNORECASE,
            )
        return sql

    def _run_with_retry(self, sql: str, params: tuple = None) -> Tuple[List[str], List[Tuple]]:
        """Run a statement, refreshing the connection and retrying once on a
        communication-link failure (08S01)."""
        sql = self._prepare_sql(sql)
        try:
            return self._run(sql, params)
        except pyodbc.Error as e:
            if self._is_link_failure(e):
                self.close()
                return self._run(sql, params)
            raise

    def execute_query_with_headers_isolated(
        self, sql: str, params: tuple = None
    ) -> Tuple[List[str], List[Tuple]]:
        """Execute a query on a dedicated, one-shot connection.

        Unlike :meth:`execute_query_with_headers`, this does NOT use the shared
        class-level connection pool.  It opens its own connection, runs the
        query, and closes it.  This makes it safe to call from a background
        thread without corrupting a pooled connection that other parts of the
        app (PolView, Illustration, …) may use concurrently on another thread.
        """
        guard_query_sql(sql)
        sql = self._prepare_sql(sql)
        use_local_data = local_data_enabled()
        conn = connection_factory.connect_policy_db2(self.region, autocommit=True)
        try:
            cursor = conn.cursor()
            try:
                if params:
                    if not use_local_data:
                        # DataDirect DB2 rejects inferred Unicode string parameters (HY004).
                        cursor.setinputsizes([
                            (pyodbc.SQL_VARCHAR, max(len(value), 1), 0)
                            if isinstance(value, str) else None
                            for value in params
                        ])
                    cursor.execute(sql, params)
                else:
                    cursor.execute(sql)
                columns = [desc[0] for desc in cursor.description] if cursor.description else []
                rows = cursor.fetchall()
                return columns, rows
            finally:
                cursor.close()
        finally:
            try:
                conn.close()
            except (pyodbc.Error, sqlite3.Error, OSError, AttributeError):
                logger.debug("Ignoring one-shot DB2 connection close failure during cleanup", exc_info=True)

    def execute_query(self, sql: str, params: tuple = None) -> List[Tuple]:
        """
        Execute a query and return all results as a list of tuples.

        Args:
            sql: SQL query string
            params: Optional query parameters

        Returns:
            List of row tuples
        """
        _, rows = self._run_with_retry(sql, params)
        return rows

    def execute_query_with_headers(self, sql: str, params: tuple = None) -> Tuple[List[str], List[Tuple]]:
        """
        Execute a query and return column headers along with results.

        Args:
            sql: SQL query string
            params: Optional query parameters

        Returns:
            Tuple of (column_names, rows)
        """
        return self._run_with_retry(sql, params)

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
        logger.debug("DB2 test connection failed for region %s", region, exc_info=True)
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
        logger.debug("Could not enumerate ODBC data sources", exc_info=True)
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
    if local_data_enabled():
        return sql

    schema = REGION_SCHEMA_MAP.get(region.upper(), DEFAULT_SCHEMA)
    if schema != DEFAULT_SCHEMA:
        import re
        sql = re.sub(r'(?i)DB2TAB\.', f'{schema}.', sql)
    return sql
