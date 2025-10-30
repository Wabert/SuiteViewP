"""Query Executor - Executes queries and returns results"""

import logging
import os
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
            # Get connection info
            connection = self.conn_manager.repo.get_connection(query.connection_id)
            connection_type = connection.get('connection_type') if connection else None
            
            # Handle CSV files differently - no SQL, just pandas filtering
            if connection_type == 'CSV':
                df = self._execute_csv_query(query, connection)
                self.last_sql = "CSV File Query (no SQL generated)"
            elif connection_type == 'DB2':
                # Build SQL query
                sql = self._build_sql(query)
                self.last_sql = sql
                logger.info(f"Executing query:\n{sql}")
                df = self._execute_db2_query(sql, connection)
            else:
                # Build SQL query
                sql = self._build_sql(query)
                self.last_sql = sql
                logger.info(f"Executing query:\n{sql}")
                
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
            logger.error(f"SQL: {self.last_sql if hasattr(self, 'last_sql') and self.last_sql else 'N/A'}")
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

    def _execute_csv_query(self, query: Query, connection: dict) -> pd.DataFrame:
        """
        Execute query on CSV file using pandas filtering (no SQL)
        
        Args:
            query: Query object with query definition
            connection: Connection dictionary with folder path
            
        Returns:
            Pandas DataFrame with filtered results
        """
        try:
            # Get CSV folder path from connection
            folder_path = connection.get('connection_string', '')
            if not folder_path:
                raise ValueError("CSV connection requires folder path")
            
            # Get table name from query
            table_name = query.from_table
            
            # Construct the full file path: folder + table name + .csv
            csv_path = os.path.join(folder_path, f"{table_name}.csv")
            
            if not os.path.exists(csv_path):
                raise ValueError(f"CSV file not found: {csv_path}")
            
            logger.info(f"Loading CSV file: {csv_path}")
            
            # Load the entire CSV file
            df = pd.read_csv(csv_path)
            logger.info(f"Loaded {len(df)} rows from CSV")
            
            # Apply custom data type conversions from metadata cache
            from suiteview.data.repositories import get_metadata_cache_repository
            metadata_repo = get_metadata_cache_repository()
            
            # Get metadata_id
            metadata_id = metadata_repo.get_metadata_id(query.connection_id, table_name, query.from_schema)
            
            if metadata_id:
                # Get cached columns with custom types
                cached_columns = metadata_repo.get_cached_columns(metadata_id)
                if cached_columns:
                    for col_info in cached_columns:
                        col_name = col_info.get('name')
                        col_type = col_info.get('type', 'TEXT').upper()
                        
                        if col_name in df.columns:
                            # Apply type conversion based on cached type
                            try:
                                if col_type == 'INTEGER':
                                    df[col_name] = pd.to_numeric(df[col_name], errors='coerce').astype('Int64')
                                elif col_type == 'FLOAT':
                                    df[col_name] = pd.to_numeric(df[col_name], errors='coerce').astype('float64')
                                elif col_type == 'DECIMAL':
                                    df[col_name] = pd.to_numeric(df[col_name], errors='coerce')
                                elif col_type == 'DATE':
                                    df[col_name] = pd.to_datetime(df[col_name], errors='coerce').dt.date
                                elif col_type == 'DATETIME':
                                    df[col_name] = pd.to_datetime(df[col_name], errors='coerce')
                                elif col_type == 'BOOLEAN':
                                    df[col_name] = df[col_name].astype(str).str.lower().isin(['true', '1', 'yes', 't', 'y'])
                                # TEXT is default, no conversion needed
                                
                                logger.info(f"Converted column '{col_name}' to {col_type}")
                            except Exception as e:
                                logger.warning(f"Could not convert column '{col_name}' to {col_type}: {e}")
            
            # Apply WHERE criteria using pandas filtering
            if query.criteria:
                for criterion in query.criteria:
                    df = self._apply_csv_filter(df, criterion)
                    logger.info(f"After filter on {criterion['field_name']}: {len(df)} rows")
            
            # Select only display fields
            if query.display_fields:
                display_columns = [field['field_name'] for field in query.display_fields]
                # Only select columns that exist in the dataframe
                existing_columns = [col for col in display_columns if col in df.columns]
                if existing_columns:
                    df = df[existing_columns]
                else:
                    logger.warning(f"No matching columns found. Available: {list(df.columns)}")
            
            logger.info(f"CSV query complete: {len(df)} rows returned")
            return df
            
        except Exception as e:
            logger.error(f"Error executing CSV query: {e}")
            raise

    def _apply_csv_filter(self, df: pd.DataFrame, criterion: Dict[str, Any]) -> pd.DataFrame:
        """
        Apply a single filter criterion to a pandas DataFrame
        
        Args:
            df: Input DataFrame
            criterion: Dictionary with filter configuration
            
        Returns:
            Filtered DataFrame
        """
        field = criterion['field_name']
        value = criterion.get('value')
        operator = criterion.get('operator', '=')
        match_type = criterion.get('match_type', 'exact')
        
        # Handle null/empty values
        if value is None or value == '':
            return df
        
        # Check if column exists
        if field not in df.columns:
            logger.warning(f"Column '{field}' not found in CSV, skipping filter")
            return df
        
        # Convert value to match the column's dtype
        try:
            col_dtype = df[field].dtype
            if pd.api.types.is_integer_dtype(col_dtype):
                if isinstance(value, list):
                    value = [int(v) for v in value]
                elif isinstance(value, tuple):
                    value = tuple(int(v) for v in value)
                else:
                    value = int(value)
            elif pd.api.types.is_float_dtype(col_dtype):
                if isinstance(value, list):
                    value = [float(v) for v in value]
                elif isinstance(value, tuple):
                    value = tuple(float(v) for v in value)
                else:
                    value = float(value)
        except (ValueError, TypeError) as e:
            logger.warning(f"Could not convert filter value for {field}: {e}")
            # Continue with original value
        
        # Handle IN operator (checkbox list)
        if operator == 'IN':
            if isinstance(value, list) and value:
                return df[df[field].isin(value)]
            return df
        
        # Handle BETWEEN operator
        if operator == 'BETWEEN':
            if isinstance(value, tuple) and len(value) == 2:
                low, high = value
                return df[(df[field] >= low) & (df[field] <= high)]
            return df
        
        # String pattern matching
        if match_type == 'starts_with':
            return df[df[field].astype(str).str.startswith(str(value), na=False)]
        elif match_type == 'ends_with':
            return df[df[field].astype(str).str.endswith(str(value), na=False)]
        elif match_type == 'contains':
            return df[df[field].astype(str).str.contains(str(value), na=False, regex=False)]
        
        # Standard operators
        if operator == '=':
            return df[df[field] == value]
        elif operator == '!=':
            return df[df[field] != value]
        elif operator == '<':
            return df[df[field] < value]
        elif operator == '<=':
            return df[df[field] <= value]
        elif operator == '>':
            return df[df[field] > value]
        elif operator == '>=':
            return df[df[field] >= value]
        
        # Unknown operator, return unchanged
        logger.warning(f"Unknown operator '{operator}', no filter applied")
        return df

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
        # Get connection to determine type
        connection = self.conn_manager.repo.get_connection(query.connection_id)
        connection_type = connection.get('connection_type', '') if connection else ''
        
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
        
        # FROM clause - DON'T include schema for SQL Server (it uses database.owner.table syntax differently)
        from_table = query.from_table
        
        # Only add schema prefix for DB2, not for SQL_SERVER
        if query.from_schema and connection_type == 'DB2':
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
            
            # Only add schema prefix for DB2
            if join['schema_name'] and connection_type == 'DB2':
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
        
        # Add row limit - ONLY for DB2 (SQL Server doesn't need it)
        if connection_type == 'DB2':
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
