"""Query Executor - Executes queries and returns results"""

import logging
import time
import pandas as pd
from sqlalchemy import text
from typing import Tuple, Dict, Any

from suiteview.core.connection_manager import get_connection_manager
from suiteview.core.query_builder import Query

logger = logging.getLogger(__name__)


class QueryExecutor:
    """Executes database queries and returns results as DataFrames"""

    def __init__(self):
        self.conn_manager = get_connection_manager()
        
        # Track execution metadata
        self.last_execution_time = 0
        self.last_record_count = 0
        self.last_sql = None

    def execute_db_query(self, query: Query) -> pd.DataFrame:
        """
        Execute a single-database query
        
        Args:
            query: Query object with query definition
            
        Returns:
            Pandas DataFrame with query results
            
        Raises:
            Exception: If query execution fails
        """
        start_time = time.time()
        
        try:
            # Build SQL query
            sql = self._build_sql(query)
            self.last_sql = sql
            
            logger.info(f"Executing query:\n{sql}")
            
            # Check if this is a DB2 connection - use pyodbc directly to avoid SQLAlchemy issues
            connection = self.conn_manager.repo.get_connection(query.connection_id)
            if connection and connection.get('connection_type') == 'DB2':
                df = self._execute_db2_query(sql, connection)
            else:
                # Get database engine for other connection types
                engine = self.conn_manager.get_engine(query.connection_id)
                
                # Execute query and load into DataFrame
                with engine.connect() as conn:
                    df = pd.read_sql_query(text(sql), conn)
            
            # Update metadata
            self.last_execution_time = int((time.time() - start_time) * 1000)  # milliseconds
            self.last_record_count = len(df)
            
            logger.info(f"Query executed successfully: {self.last_record_count} rows in {self.last_execution_time}ms")
            
            return df
            
        except Exception as e:
            logger.error(f"Query execution failed: {e}")
            logger.error(f"SQL: {sql if 'sql' in locals() else 'N/A'}")
            raise
    
    def _execute_db2_query(self, sql: str, connection: dict) -> pd.DataFrame:
        """
        Execute DB2 query using pyodbc directly (avoids SQLAlchemy issues)
        
        Args:
            sql: SQL query string
            connection: Connection dictionary with DSN info
            
        Returns:
            Pandas DataFrame with results
        """
        import pyodbc
        import warnings
        
        # Suppress pandas pyodbc warning (we know we're not using SQLAlchemy)
        warnings.filterwarnings('ignore', message='pandas only supports SQLAlchemy')
        
        try:
            # Get DSN from connection string
            dsn = connection.get('connection_string', '').replace('DSN=', '')
            if not dsn:
                raise ValueError("DB2 connection requires DSN")
            
            logger.info(f"Connecting to DB2 with DSN: {dsn}")
            conn_str = f"DSN={dsn}"
            
            # Connect - exactly like your working code
            logger.info(f"Connection string: {conn_str}")
            con = pyodbc.connect(conn_str)
            logger.info("DB2 connection established, executing query")
            
            # Execute query - exactly like your working code: pandas.read_sql(SqlString, con)
            logger.info("Calling pandas.read_sql...")
            data = pd.read_sql(sql, con)
            logger.info(f"pandas.read_sql completed, returned {len(data)} rows")
            
            logger.info("Closing connection...")
            con.close()
            logger.info("DB2 connection closed")
            
            return data
            
            return df
            
        except pyodbc.Error as e:
            logger.error(f"DB2 pyodbc error: {e}")
            raise Exception(f"Database error: {str(e)}")
        except Exception as e:
            logger.error(f"Error executing DB2 query: {e}")
            raise

    def execute_xdb_query(self, query: Query) -> pd.DataFrame:
        """
        Execute a cross-database query using application-level joins
        
        Args:
            query: Query object with XDB query definition
            
        Returns:
            Pandas DataFrame with query results
            
        Raises:
            Exception: If query execution fails
        """
        # TODO: Implement for Phase 5 (XDB Query Screen)
        raise NotImplementedError("Cross-database queries not yet implemented")

    def get_execution_metadata(self) -> Dict[str, Any]:
        """
        Get metadata about the last query execution
        
        Returns:
            Dictionary with execution_time_ms, record_count, sql
        """
        return {
            'execution_time_ms': self.last_execution_time,
            'record_count': self.last_record_count,
            'sql': self.last_sql
        }

    def _build_sql(self, query: Query) -> str:
        """
        Build SQL query string from Query object
        
        Args:
            query: Query object
            
        Returns:
            SQL query string
        """
        # SELECT clause - qualify with table names ONLY if there are JOINs
        select_fields = []
        has_joins = len(query.joins) > 0
        
        for field in query.display_fields:
            table = field['table_name']
            col = field['field_name']
            if has_joins:
                select_fields.append(f'{table}.{col}')  # Use alias for JOINs
            else:
                select_fields.append(f'{col}')  # Just column name for single table
        
        sql = f"SELECT {', '.join(select_fields)}\n"
        
        # FROM clause - use alias if there are JOINs
        from_table = query.from_table
        if query.from_schema:
            from_table = f'{query.from_schema}.{query.from_table}'
        
        if has_joins:
            # Use table name as alias
            sql += f"FROM {from_table} {query.from_table}"
        else:
            sql += f"FROM {from_table}"
        
        # JOIN clauses with aliases
        for join in query.joins:
            join_type = join['join_type']
            join_table_name = join['table_name']
            
            if join['schema_name']:
                join_table = f'{join["schema_name"]}.{join_table_name}'
            else:
                join_table = join_table_name
            
            # Add alias (the table name without schema)
            sql += f"\n{join_type} {join_table} {join_table_name}"
            
            # ON conditions
            if join['on_conditions']:
                on_parts = []
                for condition in join['on_conditions']:
                    left_field = condition['left_field']
                    right_field = condition['right_field']
                    op = condition.get('operator', '=')
                    
                    # If fields don't already include table name, add them
                    # Fields from UI should already be in "table.field" format
                    if '.' not in left_field:
                        left_field = f"{query.from_table}.{left_field}"
                    if '.' not in right_field:
                        right_field = f"{join_table_name}.{right_field}"
                    
                    on_parts.append(f"{left_field} {op} {right_field}")
                
                sql += f" ON {' AND '.join(on_parts)}"
        
        # WHERE clause
        if query.criteria:
            where_parts = []
            has_joins = len(query.joins) > 0
            
            for criterion in query.criteria:
                where_clause = self._build_where_clause(criterion, has_joins)
                if where_clause:
                    where_parts.append(where_clause)
            
            if where_parts:
                sql += f"\nWHERE {' AND '.join(where_parts)}"
        
        # Add row limit - USE LIMIT (not FETCH FIRST)
        sql += "\nLIMIT 10000000"
        
        return sql

    def _build_where_clause(self, criterion: Dict[str, Any], has_joins: bool = False) -> str:
        """
        Build WHERE clause for a single criterion
        
        Args:
            criterion: Dictionary with filter configuration
            has_joins: Whether the query has JOINs (determines if we qualify fields)
            
        Returns:
            WHERE clause string
        """
        table = criterion['table_name']
        field = criterion['field_name']
        data_type = criterion.get('data_type', '')
        value = criterion.get('value')
        operator = criterion.get('operator', '=')
        match_type = criterion.get('match_type', 'exact')
        
        # Handle null/empty values
        if value is None or value == '':
            return None
        
        # Build field reference - qualify with table name ONLY if there are JOINs
        if has_joins:
            field_ref = f'{table}.{field}'
        else:
            field_ref = field
        
        # Handle IN operator (checkbox list)
        if operator == 'IN':
            if isinstance(value, list) and value:
                # Escape single quotes in string values
                escaped_values = [str(v).replace("'", "''") for v in value]
                values_str = "', '".join(escaped_values)
                return f"{field_ref} IN ('{values_str}')"
            return None
        
        # Handle BETWEEN operator
        if operator == 'BETWEEN':
            if isinstance(value, tuple) and len(value) == 2:
                low, high = value
                # Check if date/string needs quotes
                if any(t in data_type.upper() for t in ['CHAR', 'VARCHAR', 'TEXT', 'DATE', 'TIME']):
                    return f"{field_ref} BETWEEN '{low}' AND '{high}'"
                else:
                    return f"{field_ref} BETWEEN {low} AND {high}"
            return None
        
        # String types with pattern matching
        if match_type in ['starts_with', 'ends_with', 'contains']:
            if match_type == 'starts_with':
                return f"{field_ref} LIKE '{value}%'"
            elif match_type == 'ends_with':
                return f"{field_ref} LIKE '%{value}'"
            elif match_type == 'contains':
                return f"{field_ref} LIKE '%{value}%'"
        
        # Regular operators with proper quoting
        # String types
        if any(t in data_type.upper() for t in ['CHAR', 'VARCHAR', 'TEXT', 'STRING']):
            escaped_value = str(value).replace("'", "''")
            return f"{field_ref} {operator} '{escaped_value}'"
        
        # Date/time types
        elif any(t in data_type.upper() for t in ['DATE', 'TIME', 'TIMESTAMP']):
            return f"{field_ref} {operator} '{value}'"
        
        # Numeric types (no quotes)
        else:
            return f"{field_ref} {operator} {value}"

    def preview_sql(self, query: Query) -> str:
        """
        Generate SQL without executing (for preview/debugging)
        
        Args:
            query: Query object
            
        Returns:
            SQL query string
        """
        return self._build_sql(query)
