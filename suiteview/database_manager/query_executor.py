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

# SQL Server reserved keywords that need to be escaped with brackets
SQL_SERVER_RESERVED_WORDS = {
    'ADD', 'ALL', 'ALTER', 'AND', 'ANY', 'AS', 'ASC', 'AUTHORIZATION', 'BACKUP', 'BEGIN',
    'BETWEEN', 'BREAK', 'BROWSE', 'BULK', 'BY', 'CASCADE', 'CASE', 'CHECK', 'CHECKPOINT',
    'CLOSE', 'CLUSTERED', 'COALESCE', 'COLLATE', 'COLUMN', 'COMMIT', 'COMPUTE', 'CONSTRAINT',
    'CONTAINS', 'CONTAINSTABLE', 'CONTINUE', 'CONVERT', 'CREATE', 'CROSS', 'CURRENT',
    'CURRENT_DATE', 'CURRENT_TIME', 'CURRENT_TIMESTAMP', 'CURRENT_USER', 'CURSOR', 'DATABASE',
    'DBCC', 'DEALLOCATE', 'DECLARE', 'DEFAULT', 'DELETE', 'DENY', 'DESC', 'DISK', 'DISTINCT',
    'DISTRIBUTED', 'DOUBLE', 'DROP', 'DUMP', 'ELSE', 'END', 'ERRLVL', 'ESCAPE', 'EXCEPT',
    'EXEC', 'EXECUTE', 'EXISTS', 'EXIT', 'EXTERNAL', 'FETCH', 'FILE', 'FILLFACTOR', 'FOR',
    'FOREIGN', 'FREETEXT', 'FREETEXTTABLE', 'FROM', 'FULL', 'FUNCTION', 'GOTO', 'GRANT',
    'GROUP', 'HAVING', 'HOLDLOCK', 'IDENTITY', 'IDENTITY_INSERT', 'IDENTITYCOL', 'IF', 'IN',
    'INDEX', 'INNER', 'INSERT', 'INTERSECT', 'INTO', 'IS', 'JOIN', 'KEY', 'KILL', 'LEFT',
    'LIKE', 'LINENO', 'LOAD', 'MERGE', 'NATIONAL', 'NOCHECK', 'NONCLUSTERED', 'NOT', 'NULL',
    'NULLIF', 'OF', 'OFF', 'OFFSETS', 'ON', 'OPEN', 'OPENDATASOURCE', 'OPENQUERY', 'OPENROWSET',
    'OPENXML', 'OPTION', 'OR', 'ORDER', 'OUTER', 'OVER', 'PERCENT', 'PIVOT', 'PLAN', 'PRECISION',
    'PRIMARY', 'PRINT', 'PROC', 'PROCEDURE', 'PUBLIC', 'RAISERROR', 'READ', 'READTEXT',
    'RECONFIGURE', 'REFERENCES', 'REPLICATION', 'RESTORE', 'RESTRICT', 'RETURN', 'REVERT',
    'REVOKE', 'RIGHT', 'ROLLBACK', 'ROWCOUNT', 'ROWGUIDCOL', 'RULE', 'SAVE', 'SCHEMA',
    'SECURITYAUDIT', 'SELECT', 'SEMANTICKEYPHRASETABLE', 'SEMANTICSIMILARITYDETAILSTABLE',
    'SEMANTICSIMILARITYTABLE', 'SESSION_USER', 'SET', 'SETUSER', 'SHUTDOWN', 'SOME', 'STATISTICS',
    'SYSTEM_USER', 'TABLE', 'TABLESAMPLE', 'TEXTSIZE', 'THEN', 'TO', 'TOP', 'TRAN', 'TRANSACTION',
    'TRIGGER', 'TRUNCATE', 'TRY_CONVERT', 'TSEQUAL', 'UNION', 'UNIQUE', 'UNPIVOT', 'UPDATE',
    'UPDATETEXT', 'USE', 'USER', 'VALUES', 'VARYING', 'VIEW', 'WAITFOR', 'WHEN', 'WHERE',
    'WHILE', 'WITH', 'WITHIN GROUP', 'WRITETEXT'
}


def escape_identifier(name: str, connection_type: str = 'SQL_SERVER') -> str:
    """
    Escape a SQL identifier if it's a reserved word.
    
    Args:
        name: The identifier name (column, table, etc.)
        connection_type: The database type (SQL_SERVER, DB2, etc.)
        
    Returns:
        The escaped identifier if needed, otherwise the original name
    """
    if connection_type == 'SQL_SERVER':
        # Check if it's a reserved word (case-insensitive)
        if name.upper() in SQL_SERVER_RESERVED_WORDS:
            return f'[{name}]'
    return name


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
                
                # Use raw connection to avoid SQLAlchemy parameter parsing issues
                raw_conn = engine.raw_connection()
                try:
                    df = pd.read_sql_query(sql, raw_conn)
                finally:
                    raw_conn.close()
            
            # Update metadata
            self.last_execution_time = int((time.time() - start_time) * 1000)  # milliseconds
            self.last_record_count = len(df)
            
            logger.info(f"Query executed successfully: {self.last_record_count} rows in {self.last_execution_time}ms")
            
            return df
            
        except Exception as e:
            logger.error(f"Query execution failed: {e}")
            logger.error(f"SQL: {self.last_sql if hasattr(self, 'last_sql') and self.last_sql else 'N/A'}")
            raise

    def execute_sql(self, connection_id: int, sql: str) -> pd.DataFrame:
        """
        Execute an arbitrary SQL query string
        
        Args:
            connection_id: Connection ID
            sql: SQL query string
            
        Returns:
            Pandas DataFrame with query results
            
        Raises:
            Exception: If query execution fails
        """
        start_time = time.time()
        self.last_sql = sql
        
        try:
            # Get connection info
            connection = self.conn_manager.repo.get_connection(connection_id)
            connection_type = connection.get('connection_type') if connection else None
            
            logger.info(f"Executing arbitrary SQL (Type: {connection_type}):\n{sql}")
            
            if connection_type == 'DB2':
                df = self._execute_db2_query(sql, connection)
            else:
                # Get database engine for other connection types
                engine = self.conn_manager.get_engine(connection_id)
                
                # Use raw connection to avoid SQLAlchemy parameter parsing issues
                # This is safer for "Run Query" where user types arbitrary SQL
                # and we don't want % characters to be interpreted as placeholders
                raw_conn = engine.raw_connection()
                try:
                    df = pd.read_sql_query(sql, raw_conn)
                finally:
                    raw_conn.close()
            
            # Update metadata
            self.last_execution_time = int((time.time() - start_time) * 1000)  # milliseconds
            self.last_record_count = len(df)
            
            logger.info(f"Query executed successfully: {self.last_record_count} rows in {self.last_execution_time}ms")
            
            return df
            
        except Exception as e:
            logger.error(f"Query execution failed: {e}")
            logger.error(f"SQL: {sql}")
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
        Build SQL query string from Query object with nice formatting.
        
        Produces SQL formatted like:
        SELECT
           field1,
           field2
        FROM
           schema.table table
           INNER JOIN
              schema.other other
              ON table.id = other.id
        WHERE
           field = 'value'
        
        Args:
            query: Query object
            
        Returns:
            Formatted SQL query string
        """
        # Get connection to determine type
        connection = self.conn_manager.repo.get_connection(query.connection_id)
        connection_type = connection.get('connection_type', '') if connection else ''
        
        # Indentation settings
        indent = "   "  # 3 spaces for main indentation
        indent2 = "      "  # 6 spaces for nested indentation
        
        # SELECT clause - determine if we need to qualify field names
        # Qualify if: 1) there are JOINs, OR 2) multiple tables are involved
        select_fields = []
        has_joins = len(query.joins) > 0
        
        # Check for multiple tables in display fields and criteria
        tables_involved = set()
        for field in query.display_fields:
            # Expression fields don't have a table
            if not field.get('is_expression'):
                tables_involved.add(field['table_name'])
        for criterion in query.criteria:
            tables_involved.add(criterion.get('table_name', ''))
        
        # Qualify fields if there are JOINs OR multiple tables
        needs_qualification = has_joins or len(tables_involved) > 1
        
        has_aggregations = False
        group_by_fields = []
        
        for field in query.display_fields:
            # Check if this is an expression field
            if field.get('is_expression'):
                # Expression field - use the expression directly
                expression = field.get('expression', '')
                alias = field.get('alias', field.get('field_name', 'EXPR'))
                
                if expression:
                    select_expr = f"({expression}) AS {alias}"
                else:
                    # No expression provided, skip this field
                    continue
                select_fields.append(select_expr)
                continue
            
            table = field['table_name']
            col = field['field_name']
            alias = field.get('alias', col)
            aggregation = field.get('aggregation', 'None')
            
            # Escape column name if it's a reserved word
            escaped_col = escape_identifier(col, connection_type)
            
            # Build field reference - qualify if multiple tables involved
            if needs_qualification:
                field_ref = f'{table}.{escaped_col}'
            else:
                field_ref = escaped_col
            
            # Apply aggregation if specified
            if aggregation and aggregation != 'None':
                has_aggregations = True
                agg_upper = aggregation.upper()
                
                # Map UI aggregation names to SQL functions
                agg_map = {
                    'SUM': 'SUM',
                    'MAX': 'MAX',
                    'MIN': 'MIN',
                    'AVG': 'AVG',
                    'COUNT': 'COUNT',
                    'FIRST': 'MIN',  # Use MIN as approximation for FIRST
                    'LAST': 'MAX'    # Use MAX as approximation for LAST
                }
                
                sql_agg = agg_map.get(agg_upper, agg_upper)
                select_expr = f'{sql_agg}({field_ref})'
            else:
                select_expr = field_ref
                # If there are other aggregations, non-aggregated fields need to be in GROUP BY
                group_by_fields.append(field_ref)
            
            # Add alias if different from column name
            if alias != col:
                select_expr += f' AS {alias}'
            
            select_fields.append(select_expr)
        
        # Build SELECT clause with each field on its own line
        sql = "SELECT\n"
        for i, field_expr in enumerate(select_fields):
            if i < len(select_fields) - 1:
                sql += f"{indent}{field_expr},\n"
            else:
                sql += f"{indent}{field_expr} \n"
        
        # FROM clause - include schema prefix for all database types
        from_table = query.from_table
        
        # Add schema prefix if available
        if query.from_schema:
            from_table = f'{query.from_schema}.{query.from_table}'
        
        # Handle FROM clause based on whether we have explicit JOINs or multiple tables
        sql += "FROM\n"
        if has_joins:
            # Explicit JOINs - use primary table WITH alias so WHERE clause can reference it
            sql += f"{indent}{from_table} {query.from_table} \n"
        elif len(tables_involved) > 1:
            # Multiple tables without explicit JOINs - use comma-separated list (implicit cross join)
            table_list = []
            for table_name in sorted(tables_involved):
                if query.from_schema:
                    table_list.append(f'{query.from_schema}.{table_name} {table_name}')
                else:
                    table_list.append(f'{table_name} {table_name}')
            sql += f"{indent}{', '.join(table_list)} \n"
        elif needs_qualification and query.from_schema:
            # Single table with schema prefix and qualified field names - need alias
            # so that "table.column" references work (e.g., SELECT CENSUS_ADV.LOB FROM LIFE.CENSUS_ADV CENSUS_ADV)
            sql += f"{indent}{from_table} {query.from_table} \n"
        else:
            # Single table without schema or unqualified fields - no alias needed
            sql += f"{indent}{from_table} \n"
        
        # Indentation settings (define again for clarity in this section)
        indent = "   "  # 3 spaces for main indentation
        indent2 = "      "  # 6 spaces for nested indentation
        
        # JOIN clauses WITH aliases (use table name as alias)
        for join in query.joins:
            join_type = join['join_type']
            join_table_name = join['table_name']
            
            # Add schema prefix if available
            if join['schema_name']:
                join_table = f'{join["schema_name"]}.{join_table_name}'
            else:
                join_table = join_table_name
            
            # Add JOIN on its own indented line
            sql += f"{indent}{join_type}\n"
            # Add table on further indented line
            sql += f"{indent2}{join_table} {join_table_name} \n"
            
            # ON conditions - each on its own line with proper indentation
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
                
                # First condition gets ON, rest get AND
                for i, on_part in enumerate(on_parts):
                    if i == 0:
                        sql += f"{indent2}ON {on_part} \n"
                    else:
                        sql += f"{indent2}AND {on_part} \n"
        
        # WHERE clause
        if query.criteria:
            where_parts = []
            
            for criterion in query.criteria:
                where_clause = self._build_where_clause(criterion, needs_qualification, connection_type)
                if where_clause:
                    where_parts.append(where_clause)
            
            if where_parts:
                sql += "WHERE\n"
                for i, where_part in enumerate(where_parts):
                    if i == 0:
                        sql += f"{indent}{where_part}"
                    else:
                        sql += f"\n{indent}AND {where_part}"
                sql += " \n"
        
        # GROUP BY clause - only add if there are aggregations
        if has_aggregations and group_by_fields:
            sql += "GROUP BY\n"
            for i, gb_field in enumerate(group_by_fields):
                if i < len(group_by_fields) - 1:
                    sql += f"{indent}{gb_field},\n"
                else:
                    sql += f"{indent}{gb_field} \n"
        
        # HAVING clause - filter aggregated results
        having_conditions = []
        for field in query.display_fields:
            having_expr = field.get('having', '').strip()
            aggregation = field.get('aggregation', 'None')
            
            # Only add HAVING if there's an expression and the field has aggregation
            if having_expr and aggregation and aggregation != 'None':
                table = field['table_name']
                col = field['field_name']
                
                # Escape column name if reserved
                escaped_col = escape_identifier(col, connection_type)
                
                # Build field reference - qualify if multiple tables
                if needs_qualification:
                    field_ref = f'{table}.{escaped_col}'
                else:
                    field_ref = escaped_col
                
                # Build aggregation function
                agg_upper = aggregation.upper()
                agg_map = {
                    'SUM': 'SUM',
                    'MAX': 'MAX',
                    'MIN': 'MIN',
                    'AVG': 'AVG',
                    'COUNT': 'COUNT',
                    'FIRST': 'MIN',
                    'LAST': 'MAX'
                }
                sql_agg = agg_map.get(agg_upper, agg_upper)
                agg_field = f'{sql_agg}({field_ref})'
                
                # Check if having_expr starts with an operator, if not add =
                if not any(having_expr.upper().startswith(op) for op in 
                    ['=', '>', '<', '!', 'LIKE', 'IN', 'BETWEEN', 'IS', 'NOT']):
                    having_expr = f"= {having_expr}"
                
                having_conditions.append(f'{agg_field} {having_expr}')
        
        if having_conditions:
            sql += "HAVING\n"
            for i, having_part in enumerate(having_conditions):
                if i == 0:
                    sql += f"{indent}{having_part}"
                else:
                    sql += f"\n{indent}AND {having_part}"
            sql += " \n"
        
        # ORDER BY clause - collect fields with order specified
        order_by_fields = []
        for field in query.display_fields:
            order = field.get('order', 'None')
            if order and order != 'None':
                table = field['table_name']
                col = field['field_name']
                
                # Escape column name if reserved
                escaped_col = escape_identifier(col, connection_type)
                
                # Build field reference - qualify if multiple tables
                if needs_qualification:
                    field_ref = f'{table}.{escaped_col}'
                else:
                    field_ref = escaped_col
                
                # Add ASC or DESC
                if order == 'Ascend':
                    order_by_fields.append(f'{field_ref} ASC')
                elif order == 'Descend':
                    order_by_fields.append(f'{field_ref} DESC')
        
        if order_by_fields:
            sql += "ORDER BY\n"
            for i, ob_field in enumerate(order_by_fields):
                if i < len(order_by_fields) - 1:
                    sql += f"{indent}{ob_field},\n"
                else:
                    sql += f"{indent}{ob_field} \n"
        
        # Add row limit - ONLY for DB2 (SQL Server doesn't need it)
        if connection_type == 'DB2':
            sql += "LIMIT 10000000"
        
        # Remove trailing whitespace from each line and trailing newline
        sql = '\n'.join(line.rstrip() for line in sql.split('\n')).rstrip()
        
        return sql

    def _build_where_clause(self, criterion: Dict[str, Any], has_joins: bool = False, connection_type: str = '') -> str:
        """
        Build WHERE clause for a single criterion
        
        Args:
            criterion: Dictionary with filter configuration
            has_joins: Whether the query has JOINs (determines if we qualify fields)
            connection_type: Database type for identifier escaping
            
        Returns:
            WHERE clause string
        """
        table = criterion['table_name']
        field = criterion['field_name']
        data_type = criterion.get('data_type', '')
        value = criterion.get('value')
        operator = criterion.get('operator', '=')
        match_type = criterion.get('match_type', 'exact')
        
        # Escape field name if it's a reserved word
        escaped_field = escape_identifier(field, connection_type)
        
        # Handle null/empty values
        if value is None or value == '':
            return None
        
        # Build field reference - qualify with table name ONLY if there are JOINs
        if has_joins:
            field_ref = f'{table}.{escaped_field}'
        else:
            field_ref = escaped_field
        
        # Handle EXPRESSION operator (user-provided custom expression)
        if operator == 'EXPRESSION':
            # User provides the full expression (e.g., "= 100", "> 100", "LIKE 'A%'", "IN ('A', 'B')")
            expression = str(value).strip()
            
            # If expression doesn't start with an operator, assume equality
            if expression and not any(expression.upper().startswith(op) for op in 
                ['=', '>', '<', '!', 'LIKE', 'IN', 'BETWEEN', 'IS', 'NOT']):
                # Auto-add = operator - user is responsible for proper quoting
                expression = f"= {expression}"
            
            # Check for function wrapper (e.g., RTRIM, UPPER)
            function_wrapper = criterion.get('function_wrapper', '')
            if function_wrapper:
                # Wrap field in function: RTRIM(table.field) LIKE '%value'
                return f"{function_wrapper}({field_ref}) {expression}"
            else:
                return f"{field_ref} {expression}"
        
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

    def execute_raw_sql(self, connection_id: int, table_name: str, schema_name: str = None, limit: int = None) -> pd.DataFrame:
        """
        Execute a raw SELECT * query with optional limit
        
        This is a centralized method for executing simple queries across all connection types
        (CSV, Excel, Access, DB2, SQL Server). All code that needs to query data should use this
        method to avoid duplication.
        
        Args:
            connection_id: Connection ID
            table_name: Table/file name to query
            schema_name: Schema name (optional, for DB2)
            limit: Optional row limit
            
        Returns:
            Pandas DataFrame with results
            
        Raises:
            Exception: If query execution fails
        """
        import os
        import warnings
        
        start_time = time.time()
        
        try:
            # Get connection info
            connection = self.conn_manager.repo.get_connection(connection_id)
            conn_type = connection.get('connection_type', '')
            
            logger.info(f"Executing raw query - Type: {conn_type}, Table: {table_name}, Limit: {limit}")
            
            # Handle file-based connections (CSV, Excel, Access)
            if conn_type == 'CSV':
                folder_path = connection.get('connection_string', '')
                csv_path = os.path.join(folder_path, f"{table_name}.csv")
                
                if not os.path.exists(csv_path):
                    raise ValueError(f"CSV file not found: {csv_path}")
                
                logger.info(f"Loading CSV file: {csv_path}")
                
                if limit:
                    df = pd.read_csv(csv_path, nrows=limit)
                else:
                    df = pd.read_csv(csv_path)
                    
                self.last_sql = "CSV File Query (no SQL generated)"
            
            elif conn_type == 'EXCEL':
                file_path = connection.get('connection_string', '')
                
                if not os.path.exists(file_path):
                    raise ValueError(f"Excel file not found: {file_path}")
                
                logger.info(f"Loading Excel file: {file_path}, sheet: {table_name}")
                
                if limit:
                    df = pd.read_excel(file_path, sheet_name=table_name, nrows=limit)
                else:
                    df = pd.read_excel(file_path, sheet_name=table_name)
                    
                self.last_sql = "Excel File Query (no SQL generated)"
            
            elif conn_type == 'ACCESS':
                import pyodbc
                file_path = connection.get('connection_string', '')
                
                if not os.path.exists(file_path):
                    raise ValueError(f"Access file not found: {file_path}")
                
                logger.info(f"Loading Access table: {table_name}")
                
                # Build Access connection string
                conn_str = f"DRIVER={{Microsoft Access Driver (*.mdb, *.accdb)}};DBQ={file_path};"
                
                # Build SQL with limit
                if limit:
                    sql = f"SELECT TOP {limit} * FROM [{table_name}]"
                else:
                    sql = f"SELECT * FROM [{table_name}]"
                
                self.last_sql = sql
                logger.info(f"Executing SQL: {sql}")
                
                # Execute query
                with pyodbc.connect(conn_str) as access_conn:
                    df = pd.read_sql(sql, access_conn)
            
            else:
                # Database query (DB2, SQL Server, etc.)
                # Build table reference with schema if provided
                if schema_name and conn_type == 'DB2':
                    table_ref = f"{schema_name}.{table_name}"
                else:
                    table_ref = table_name
                
                # Build SQL with proper syntax for each database type
                if conn_type == 'DB2':
                    # IMPORTANT: Use LIMIT syntax for DB2, NOT "FETCH FIRST n ROWS ONLY"
                    # The ODBC Shadow driver we use requires LIMIT syntax to work properly.
                    # DO NOT CHANGE THIS to FETCH - it will cause "ILLEGAL USE OF KEYWORD FETCH" errors.
                    if limit:
                        sql = f"SELECT * FROM {table_ref} LIMIT {limit}"
                    else:
                        sql = f"SELECT * FROM {table_ref}"
                else:
                    # For SQL Server use TOP
                    if limit:
                        sql = f"SELECT TOP {limit} * FROM {table_ref}"
                    else:
                        sql = f"SELECT * FROM {table_ref}"
                
                self.last_sql = sql
                logger.info(f"Executing SQL: {sql}")
                
                # Execute query - use pyodbc directly for DB2, SQLAlchemy for others
                if conn_type == 'DB2':
                    df = self._execute_db2_query(sql, connection)
                else:
                    # For other databases, use SQLAlchemy engine
                    engine = self.conn_manager.get_engine(connection_id)
                    from sqlalchemy import text
                    
                    with engine.connect() as conn:
                        df = pd.read_sql_query(text(sql), conn)
            
            # Update metadata
            self.last_execution_time = int((time.time() - start_time) * 1000)
            self.last_record_count = len(df)
            
            logger.info(f"Query executed successfully: {self.last_record_count} rows in {self.last_execution_time}ms")
            
            return df
            
        except Exception as e:
            logger.error(f"Raw SQL execution failed: {e}")
            logger.error(f"SQL: {self.last_sql if hasattr(self, 'last_sql') and self.last_sql else 'N/A'}")
            raise
