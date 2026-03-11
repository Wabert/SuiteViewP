"""
XDB Query Engine - Hybrid Cross-Database Query Execution

This module implements a smart query execution strategy that:
1. Parses unified SQL-like syntax with database.table references
2. Pushes filters and column projections to source databases
3. Uses DuckDB for in-memory joins of filtered results
4. Supports DB2, SQL Server, MS Access, Excel, CSV, Fixed-Width files

Architecture:
    User Query → Query Analyzer → Source Extractors → DuckDB Joiner → Results
"""

import logging
import time
from typing import Dict, List, Any, Optional, Tuple
from dataclasses import dataclass, field
from enum import Enum
import pandas as pd

logger = logging.getLogger(__name__)


class SourceType(Enum):
    """Supported data source types"""
    DB2 = "DB2"
    SQL_SERVER = "SQL_SERVER"
    ACCESS = "ACCESS"
    EXCEL = "EXCEL"
    CSV = "CSV"
    FIXED_WIDTH = "FIXED_WIDTH"
    PARQUET = "PARQUET"


@dataclass
class SourceConfig:
    """Configuration for a single data source in an XDB query"""
    alias: str
    connection_id: int
    connection_type: str
    connection_name: str
    table_name: str
    schema_name: Optional[str] = None
    columns: List[str] = field(default_factory=list)  # Empty = all columns
    filters: List[Dict] = field(default_factory=list)
    connection_string: Optional[str] = None
    
    # Execution metadata (populated after fetch)
    row_count: int = 0
    fetch_time_ms: int = 0
    estimated_rows: Optional[int] = None


@dataclass
class JoinConfig:
    """Configuration for a join between sources"""
    join_type: str  # INNER, LEFT, RIGHT, FULL
    left_alias: str
    right_alias: str
    on_conditions: List[Dict]  # [{left_field, right_field}, ...]


@dataclass
class ExecutionPlan:
    """Execution plan for an XDB query"""
    sources: List[SourceConfig]
    joins: List[JoinConfig]
    final_columns: List[str]  # Columns to select in final output
    aggregations: List[Dict] = field(default_factory=list)
    order_by: List[Dict] = field(default_factory=list)
    limit: Optional[int] = None
    
    # Execution stats
    total_time_ms: int = 0
    duckdb_time_ms: int = 0
    
    # Captured SQL statements for display
    source_sql_statements: List[Dict] = field(default_factory=list)  # [{alias, sql, connection_name}, ...]
    duckdb_join_sql: str = ""


class XDBEngine:
    """
    Cross-Database Query Engine
    
    Executes queries across multiple heterogeneous data sources by:
    1. Extracting filtered data from each source using native drivers
    2. Registering results in DuckDB
    3. Executing joins and aggregations in DuckDB
    4. Returning results as pandas DataFrame
    """
    
    def __init__(self):
        """Initialize the XDB Engine"""
        self.conn_manager = None
        self._captured_sql = []  # Track SQL statements for display
        self._duckdb_sql = ""  # Track DuckDB join SQL
        self._init_duckdb()
        self._init_connection_manager()
    
    def _init_duckdb(self):
        """Initialize DuckDB connection"""
        try:
            import duckdb
            self.duckdb = duckdb
            self.duckdb_available = True
            logger.info("DuckDB initialized for XDB Engine")
        except ImportError:
            self.duckdb = None
            self.duckdb_available = False
            logger.warning("DuckDB not available - install with 'pip install duckdb'")
    
    def _init_connection_manager(self):
        """Initialize connection manager"""
        try:
            from suiteview.core.connection_manager import get_connection_manager
            self.conn_manager = get_connection_manager()
        except Exception as e:
            logger.error(f"Failed to initialize connection manager: {e}")
    
    def execute(
        self,
        sources: List[SourceConfig],
        joins: List[JoinConfig],
        final_columns: Optional[List[str]] = None,
        aggregations: Optional[List[Dict]] = None,
        order_by: Optional[List[Dict]] = None,
        limit: Optional[int] = None
    ) -> Tuple[pd.DataFrame, ExecutionPlan]:
        """
        Execute an XDB query
        
        Args:
            sources: List of source configurations
            joins: List of join configurations
            final_columns: Columns to include in output (None = all)
            aggregations: Aggregation functions to apply
            order_by: Order by specifications
            limit: Row limit
            
        Returns:
            Tuple of (result DataFrame, execution plan)
        """
        start_time = time.time()
        
        # Clear captured SQL from previous executions
        self._captured_sql = []
        self._duckdb_sql = ""
        
        # Create execution plan
        plan = ExecutionPlan(
            sources=sources,
            joins=joins,
            final_columns=final_columns or [],
            aggregations=aggregations or [],
            order_by=order_by or [],
            limit=limit
        )
        
        try:
            # Single source - no need for DuckDB joins
            if len(sources) == 1:
                df = self._fetch_single_source(sources[0])
                plan.total_time_ms = int((time.time() - start_time) * 1000)
                # Populate captured SQL into plan for single source
                plan.source_sql_statements = self._captured_sql.copy()
                return df, plan
            
            # Multiple sources - use DuckDB for joins
            if not self.duckdb_available:
                raise RuntimeError("DuckDB required for multi-source queries. Install with 'pip install duckdb'")
            
            # SMART FETCH STRATEGY: Dependent joins
            # 1. Identify sources with filters vs without
            # 2. Fetch filtered sources first
            # 3. Use join key values from filtered sources to filter unfiltered sources
            
            source_dataframes = {}
            sources_by_alias = {s.alias: s for s in sources}
            
            # Build a map of join relationships: alias -> [(other_alias, my_field, their_field), ...]
            join_relationships = {}
            for join in joins:
                for cond in join.on_conditions:
                    left_alias = cond['left_alias']
                    right_alias = cond['right_alias']
                    left_field = cond['left_field']
                    right_field = cond['right_field']
                    
                    if left_alias not in join_relationships:
                        join_relationships[left_alias] = []
                    join_relationships[left_alias].append((right_alias, left_field, right_field))
                    
                    if right_alias not in join_relationships:
                        join_relationships[right_alias] = []
                    join_relationships[right_alias].append((left_alias, right_field, left_field))
            
            # Separate sources into filtered and unfiltered
            filtered_sources = [s for s in sources if s.filters]
            unfiltered_sources = [s for s in sources if not s.filters]
            
            logger.info(f"Filtered sources: {[s.alias for s in filtered_sources]}")
            logger.info(f"Unfiltered sources: {[s.alias for s in unfiltered_sources]}")
            
            # Step 1: Fetch filtered sources first
            for source in filtered_sources:
                logger.info(f"Fetching filtered source '{source.alias}' from {source.connection_name}.{source.table_name}...")
                df = self._fetch_source(source)
                source_dataframes[source.alias] = df
                source.row_count = len(df)
                logger.info(f"  -> Fetched {len(df)} rows in {source.fetch_time_ms}ms")
            
            # Step 2: For unfiltered sources, derive filters from join keys of already-fetched data
            for source in unfiltered_sources:
                derived_filters = []
                
                # Check if this source joins to any already-fetched source
                if source.alias in join_relationships:
                    for (other_alias, my_field, their_field) in join_relationships[source.alias]:
                        if other_alias in source_dataframes:
                            other_df = source_dataframes[other_alias]
                            if their_field in other_df.columns:
                                # Get unique non-null values from the join column
                                join_values = other_df[their_field].dropna().unique().tolist()
                                
                                if len(join_values) > 0 and len(join_values) <= 10000:
                                    # Use IN filter for reasonable number of values
                                    derived_filters.append({
                                        'column': my_field,
                                        'operator': 'IN',
                                        'value': join_values
                                    })
                                    logger.info(f"  -> Derived IN filter on '{my_field}' with {len(join_values)} values from {other_alias}.{their_field}")
                                elif len(join_values) > 10000:
                                    logger.warning(f"  -> Too many join values ({len(join_values)}) to push down, fetching all rows")
                
                # Add derived filters to source
                if derived_filters:
                    source.filters.extend(derived_filters)
                
                logger.info(f"Fetching source '{source.alias}' from {source.connection_name}.{source.table_name}...")
                df = self._fetch_source(source)
                source_dataframes[source.alias] = df
                source.row_count = len(df)
                logger.info(f"  -> Fetched {len(df)} rows in {source.fetch_time_ms}ms")
            
            # Step 3: Execute joins in DuckDB
            # First, debug log the join column values to help diagnose mismatches
            for join in joins:
                for cond in join.on_conditions:
                    left_alias = cond['left_alias']
                    right_alias = cond['right_alias']
                    left_field = cond['left_field']
                    right_field = cond['right_field']
                    
                    if left_alias in source_dataframes and right_alias in source_dataframes:
                        left_df = source_dataframes[left_alias]
                        right_df = source_dataframes[right_alias]
                        
                        if left_field in left_df.columns and right_field in right_df.columns:
                            left_vals = left_df[left_field].dropna().unique()[:5]
                            right_vals = right_df[right_field].dropna().unique()[:5]
                            logger.info(f"Join column sample - {left_alias}.{left_field}: {list(left_vals)}")
                            logger.info(f"Join column sample - {right_alias}.{right_field}: {list(right_vals)}")
                            
                            # Check for string columns and strip whitespace
                            if left_df[left_field].dtype == 'object':
                                left_df[left_field] = left_df[left_field].astype(str).str.strip()
                                logger.info(f"Stripped whitespace from {left_alias}.{left_field}")
                            if right_df[right_field].dtype == 'object':
                                right_df[right_field] = right_df[right_field].astype(str).str.strip()
                                logger.info(f"Stripped whitespace from {right_alias}.{right_field}")
            
            duckdb_start = time.time()
            result_df = self._execute_duckdb_join(
                source_dataframes,
                joins,
                final_columns,
                aggregations,
                order_by,
                limit
            )
            plan.duckdb_time_ms = int((time.time() - duckdb_start) * 1000)
            
            plan.total_time_ms = int((time.time() - start_time) * 1000)
            
            # Populate captured SQL into plan
            plan.source_sql_statements = self._captured_sql.copy()
            plan.duckdb_join_sql = self._duckdb_sql
            
            logger.info(f"XDB query completed: {len(result_df)} rows in {plan.total_time_ms}ms")
            return result_df, plan
            
        except Exception as e:
            logger.error(f"XDB query execution failed: {e}", exc_info=True)
            raise
    
    def _fetch_single_source(self, source: SourceConfig) -> pd.DataFrame:
        """Fetch data from a single source without DuckDB"""
        return self._fetch_source(source)
    
    def _fetch_source(self, source: SourceConfig) -> pd.DataFrame:
        """
        Fetch data from a source with filter pushdown
        
        This method routes to the appropriate fetcher based on source type
        and applies filters at the source level when possible.
        """
        start_time = time.time()
        
        try:
            conn_type = source.connection_type.upper()
            
            if conn_type == 'DB2':
                df = self._fetch_db2(source)
            elif conn_type == 'SQL_SERVER':
                df = self._fetch_sqlserver(source)
            elif conn_type == 'ACCESS':
                df = self._fetch_access(source)
            elif conn_type == 'EXCEL':
                df = self._fetch_excel(source)
            elif conn_type == 'CSV':
                df = self._fetch_csv(source)
            elif conn_type == 'FIXED_WIDTH':
                df = self._fetch_fixed_width(source)
            else:
                raise ValueError(f"Unsupported connection type: {conn_type}")
            
            source.fetch_time_ms = int((time.time() - start_time) * 1000)
            return df
            
        except Exception as e:
            logger.error(f"Failed to fetch from source '{source.alias}': {e}")
            raise
    
    def _fetch_db2(self, source: SourceConfig) -> pd.DataFrame:
        """Fetch from DB2 with filter pushdown"""
        import pyodbc
        
        # Build SQL with pushdown
        sql = self._build_sql_query(source, dialect='db2')
        logger.info(f"DB2 SQL: {sql}")
        
        # Capture SQL for display
        self._captured_sql.append({
            'alias': source.alias,
            'connection_name': source.connection_name,
            'connection_type': 'DB2',
            'table': source.table_name,
            'sql': sql
        })
        
        # Get connection
        connection = self.conn_manager.repo.get_connection(source.connection_id)
        dsn = connection.get('connection_string', '').replace('DSN=', '')
        
        if not dsn:
            raise ValueError(f"DB2 connection requires DSN for source '{source.alias}'")
        
        # Execute
        conn = pyodbc.connect(f"DSN={dsn}")
        try:
            df = pd.read_sql(sql, conn)
        finally:
            conn.close()
        
        return df
    
    def _fetch_sqlserver(self, source: SourceConfig) -> pd.DataFrame:
        """Fetch from SQL Server with filter pushdown"""
        from sqlalchemy import text
        
        # Build SQL with pushdown
        sql = self._build_sql_query(source, dialect='sqlserver')
        logger.info(f"SQL Server SQL: {sql}")
        
        # Capture SQL for display
        self._captured_sql.append({
            'alias': source.alias,
            'connection_name': source.connection_name,
            'connection_type': 'SQL Server',
            'table': source.table_name,
            'sql': sql
        })
        
        # Get engine
        engine = self.conn_manager.get_engine(source.connection_id)
        
        # Execute
        with engine.connect() as conn:
            df = pd.read_sql_query(text(sql), conn)
        
        return df
    
    def _fetch_access(self, source: SourceConfig) -> pd.DataFrame:
        """Fetch from MS Access with filter pushdown"""
        import pyodbc
        
        # Get connection info
        connection = self.conn_manager.repo.get_connection(source.connection_id)
        conn_string = connection.get('connection_string', '')
        
        if not conn_string:
            raise ValueError(f"Access connection requires connection string for source '{source.alias}'")
        
        # Build SQL (Access uses square brackets for identifiers)
        sql = self._build_sql_query(source, dialect='access')
        logger.info(f"Access SQL: {sql}")
        
        # Capture SQL for display
        self._captured_sql.append({
            'alias': source.alias,
            'connection_name': source.connection_name,
            'connection_type': 'MS Access',
            'table': source.table_name,
            'sql': sql
        })
        
        # Execute
        conn = pyodbc.connect(conn_string)
        try:
            df = pd.read_sql(sql, conn)
        finally:
            conn.close()
        
        return df
    
    def _fetch_excel(self, source: SourceConfig) -> pd.DataFrame:
        """Fetch from Excel file"""
        # Get connection info
        connection = self.conn_manager.repo.get_connection(source.connection_id)
        file_path = connection.get('connection_string', '')
        
        if not file_path:
            raise ValueError(f"Excel connection requires file path for source '{source.alias}'")
        
        # Read Excel (sheet name is table_name)
        sheet_name = source.table_name
        df = pd.read_excel(file_path, sheet_name=sheet_name)
        
        # Apply column selection
        if source.columns:
            available_cols = [c for c in source.columns if c in df.columns]
            if available_cols:
                df = df[available_cols]
        
        # Apply filters in pandas (no pushdown for Excel)
        df = self._apply_pandas_filters(df, source.filters)
        
        return df
    
    def _fetch_csv(self, source: SourceConfig) -> pd.DataFrame:
        """Fetch from CSV file"""
        import os
        
        # Get connection info
        connection = self.conn_manager.repo.get_connection(source.connection_id)
        folder_path = connection.get('connection_string', '')
        
        if not folder_path:
            raise ValueError(f"CSV connection requires folder path for source '{source.alias}'")
        
        # Build file path (table_name is the CSV filename)
        file_path = os.path.join(folder_path, source.table_name)
        if not file_path.endswith('.csv'):
            file_path += '.csv'
        
        # Read CSV
        df = pd.read_csv(file_path)
        
        # Apply column selection
        if source.columns:
            available_cols = [c for c in source.columns if c in df.columns]
            if available_cols:
                df = df[available_cols]
        
        # Apply filters in pandas (no pushdown for CSV)
        df = self._apply_pandas_filters(df, source.filters)
        
        return df
    
    def _fetch_fixed_width(self, source: SourceConfig) -> pd.DataFrame:
        """Fetch from fixed-width file"""
        import os
        
        # Get connection info
        connection = self.conn_manager.repo.get_connection(source.connection_id)
        folder_path = connection.get('connection_string', '')
        
        if not folder_path:
            raise ValueError(f"Fixed-width connection requires folder path for source '{source.alias}'")
        
        # Build file path
        file_path = os.path.join(folder_path, source.table_name)
        
        # Get column specifications from saved table metadata
        # For now, read as CSV fallback (would need column spec metadata)
        logger.warning(f"Fixed-width parsing not fully implemented, attempting CSV read for '{source.alias}'")
        df = pd.read_csv(file_path, sep=None, engine='python')
        
        # Apply filters
        df = self._apply_pandas_filters(df, source.filters)
        
        return df
    
    def _build_sql_query(self, source: SourceConfig, dialect: str = 'ansi') -> str:
        """
        Build SQL query with column projection and filter pushdown
        
        Args:
            source: Source configuration
            dialect: SQL dialect ('db2', 'sqlserver', 'access', 'ansi')
            
        Returns:
            SQL query string
        """
        # Quote function based on dialect
        def quote(identifier: str) -> str:
            if dialect == 'access':
                return f"[{identifier}]"
            else:
                return f'"{identifier}"'
        
        # Build column list
        if source.columns:
            cols = ", ".join([quote(c) for c in source.columns])
        else:
            cols = "*"
        
        # Build table reference
        if source.schema_name:
            table_ref = f"{quote(source.schema_name)}.{quote(source.table_name)}"
        else:
            table_ref = quote(source.table_name)
        
        # Build WHERE clause
        where_clauses = []
        for f in source.filters:
            col = quote(f['column'])
            op = f['operator']
            val = f['value']
            
            # Format value based on type
            if isinstance(val, str):
                # Escape single quotes
                val_escaped = val.replace("'", "''")
                val_str = f"'{val_escaped}'"
            elif val is None:
                if op == '=':
                    where_clauses.append(f"{col} IS NULL")
                    continue
                elif op == '!=':
                    where_clauses.append(f"{col} IS NOT NULL")
                    continue
                else:
                    val_str = 'NULL'
            else:
                val_str = str(val)
            
            # Handle IN operator
            if op.upper() == 'IN':
                # Value should be a list or comma-separated string
                if isinstance(val, list):
                    in_vals = ", ".join([f"'{v}'" if isinstance(v, str) else str(v) for v in val])
                else:
                    in_vals = val  # Assume already formatted
                where_clauses.append(f"{col} IN ({in_vals})")
            elif op.upper() == 'LIKE':
                where_clauses.append(f"{col} LIKE {val_str}")
            else:
                where_clauses.append(f"{col} {op} {val_str}")
        
        # Construct query
        sql = f"SELECT {cols} FROM {table_ref}"
        if where_clauses:
            sql += " WHERE " + " AND ".join(where_clauses)
        
        return sql
    
    def _apply_pandas_filters(self, df: pd.DataFrame, filters: List[Dict]) -> pd.DataFrame:
        """Apply filters to a pandas DataFrame (for non-SQL sources)"""
        if not filters:
            return df
        
        for f in filters:
            col = f['column']
            op = f['operator']
            val = f['value']
            
            if col not in df.columns:
                logger.warning(f"Filter column '{col}' not found in DataFrame")
                continue
            
            if op == '=':
                df = df[df[col] == val]
            elif op == '!=':
                df = df[df[col] != val]
            elif op == '>':
                df = df[df[col] > val]
            elif op == '<':
                df = df[df[col] < val]
            elif op == '>=':
                df = df[df[col] >= val]
            elif op == '<=':
                df = df[df[col] <= val]
            elif op.upper() == 'LIKE':
                # Convert SQL LIKE to regex
                pattern = val.replace('%', '.*').replace('_', '.')
                df = df[df[col].astype(str).str.match(pattern, case=False)]
            elif op.upper() == 'IN':
                if isinstance(val, str):
                    val = [v.strip() for v in val.split(',')]
                df = df[df[col].isin(val)]
        
        return df
    
    def _execute_duckdb_join(
        self,
        source_dataframes: Dict[str, pd.DataFrame],
        joins: List[JoinConfig],
        final_columns: Optional[List[str]],
        aggregations: Optional[List[Dict]],
        order_by: Optional[List[Dict]],
        limit: Optional[int]
    ) -> pd.DataFrame:
        """
        Execute joins and final query in DuckDB
        
        Args:
            source_dataframes: Dict mapping alias to DataFrame
            joins: Join configurations
            final_columns: Columns to select
            aggregations: Aggregation specs
            order_by: Order by specs
            limit: Row limit
            
        Returns:
            Result DataFrame
        """
        conn = self.duckdb.connect(':memory:')
        
        try:
            # Configure DuckDB
            conn.execute("SET memory_limit='2GB'")
            
            # Register all DataFrames
            for alias, df in source_dataframes.items():
                conn.register(alias, df)
                logger.debug(f"Registered '{alias}' with {len(df)} rows")
            
            # Build SQL query - pass source_dataframes to know which columns belong to which table
            sql = self._build_duckdb_query(
                source_dataframes,
                joins,
                final_columns,
                aggregations,
                order_by,
                limit
            )
            
            logger.info(f"DuckDB Query:\n{sql}")
            
            # Capture DuckDB join SQL for display
            self._duckdb_sql = sql
            
            # Execute
            result_df = conn.execute(sql).fetchdf()
            
            return result_df
            
        finally:
            conn.close()
    
    def _build_duckdb_query(
        self,
        source_dataframes: Dict[str, pd.DataFrame],
        joins: List[JoinConfig],
        final_columns: Optional[List[str]],
        aggregations: Optional[List[Dict]],
        order_by: Optional[List[Dict]],
        limit: Optional[int]
    ) -> str:
        """Build the DuckDB SQL query for joins and final processing"""
        
        aliases = list(source_dataframes.keys())
        
        # Build a map of column -> list of tables that have it
        column_to_tables = {}
        for alias, df in source_dataframes.items():
            for col in df.columns:
                if col not in column_to_tables:
                    column_to_tables[col] = []
                column_to_tables[col].append(alias)
        
        # Helper to qualify column if ambiguous
        def qualify_column(col: str, preferred_alias: str = None) -> str:
            """Return qualified column reference, using alias if column is ambiguous"""
            tables_with_col = column_to_tables.get(col, [])
            if len(tables_with_col) > 1:
                # Ambiguous - need to qualify
                if preferred_alias and preferred_alias in tables_with_col:
                    return f'"{preferred_alias}"."{col}"'
                else:
                    # Use first table that has this column
                    return f'"{tables_with_col[0]}"."{col}"'
            else:
                # Not ambiguous, can use unqualified
                return f'"{col}"'
        
        # Determine SELECT clause
        if aggregations:
            # Build aggregated select
            select_parts = []
            group_by_cols = []
            
            for agg in aggregations:
                col = agg.get('column', '*')
                func = agg.get('function', 'COUNT').upper()
                alias_name = agg.get('alias', f"{func}_{col}")
                source_alias = agg.get('source_alias', '')
                
                if func == 'NONE' or func == '':
                    # Non-aggregated column (for GROUP BY)
                    if source_alias:
                        col_ref = f'"{source_alias}"."{col}"'
                    else:
                        col_ref = qualify_column(col)
                    select_parts.append(f'{col_ref} AS "{alias_name}"')
                    group_by_cols.append(col_ref)
                else:
                    if source_alias:
                        col_ref = f'"{source_alias}"."{col}"'
                    else:
                        col_ref = qualify_column(col)
                    select_parts.append(f'{func}({col_ref}) AS "{alias_name}"')
            
            select_clause = ", ".join(select_parts)
        elif final_columns:
            # Explicit column list - qualify ambiguous columns
            select_parts = []
            for col in final_columns:
                select_parts.append(qualify_column(col))
            select_clause = ", ".join(select_parts)
        else:
            # Select all - explicitly list all columns with qualification to avoid ambiguity
            select_parts = []
            seen_cols = set()
            for alias in aliases:
                df = source_dataframes[alias]
                for col in df.columns:
                    if col not in seen_cols:
                        select_parts.append(qualify_column(col, alias))
                        seen_cols.add(col)
            select_clause = ", ".join(select_parts) if select_parts else "*"
        
        # Helper to quote alias names for DuckDB
        def quote_alias(alias: str) -> str:
            """Quote alias name to handle special characters"""
            # DuckDB uses double quotes for identifiers
            return f'"{alias}"'
        
        # Build FROM clause
        if not joins:
            # Single table
            from_clause = f"FROM {quote_alias(aliases[0])}"
        else:
            # Start with the LEFT side of the first join as the base table
            # This ensures we build: FROM left_table JOIN right_table ON ...
            base_alias = joins[0].left_alias
            from_clause = f"FROM {quote_alias(base_alias)}"
            
            # Track which aliases we've already added to the FROM clause
            added_aliases = {base_alias}
            
            # Add joins
            for join in joins:
                join_type = join.join_type.upper()
                if 'OUTER' not in join_type and join_type in ['LEFT', 'RIGHT', 'FULL']:
                    join_type = f"{join_type} OUTER"
                
                right_alias = join.right_alias
                
                # Skip if this alias was already added (shouldn't happen normally)
                if right_alias in added_aliases:
                    logger.warning(f"Skipping duplicate alias in join: {right_alias}")
                    continue
                
                added_aliases.add(right_alias)
                
                # Build ON clause
                on_parts = []
                for cond in join.on_conditions:
                    left_ref = f'{quote_alias(cond["left_alias"])}."{cond["left_field"]}"'
                    right_ref = f'{quote_alias(cond["right_alias"])}."{cond["right_field"]}"'
                    on_parts.append(f"{left_ref} = {right_ref}")
                
                on_clause = " AND ".join(on_parts) if on_parts else "1=1"
                
                from_clause += f"\n{join_type} JOIN {quote_alias(right_alias)} ON {on_clause}"
        
        # Build complete query
        sql = f"SELECT {select_clause}\n{from_clause}"
        
        # Add GROUP BY if aggregating
        if aggregations and group_by_cols:
            sql += f"\nGROUP BY {', '.join(group_by_cols)}"
        
        # Add ORDER BY
        if order_by:
            order_parts = []
            for o in order_by:
                col = o.get('column', '')
                direction = o.get('direction', 'ASC').upper()
                source_alias = o.get('source_alias', '')
                if source_alias:
                    order_parts.append(f'{quote_alias(source_alias)}."{col}" {direction}')
                else:
                    order_parts.append(f'"{col}" {direction}')
            if order_parts:
                sql += f"\nORDER BY {', '.join(order_parts)}"
        
        # Add LIMIT
        if limit:
            sql += f"\nLIMIT {limit}"
        
        return sql
    
    def get_source_preview(
        self,
        source: SourceConfig,
        limit: int = 100
    ) -> pd.DataFrame:
        """
        Get a preview of data from a single source
        
        Args:
            source: Source configuration
            limit: Number of rows to preview
            
        Returns:
            Preview DataFrame
        """
        # Temporarily add limit to source filters (if SQL-based)
        original_filters = source.filters.copy()
        
        try:
            df = self._fetch_source(source)
            return df.head(limit)
        finally:
            source.filters = original_filters
    
    def estimate_source_rows(self, source: SourceConfig) -> int:
        """
        Estimate row count for a source (without fetching all data)
        
        For SQL sources, uses COUNT(*) query
        For file sources, estimates from file size
        """
        conn_type = source.connection_type.upper()
        
        if conn_type in ['DB2', 'SQL_SERVER', 'ACCESS']:
            # Use COUNT(*) query
            try:
                sql = self._build_count_query(source)
                
                if conn_type == 'DB2':
                    import pyodbc
                    connection = self.conn_manager.repo.get_connection(source.connection_id)
                    dsn = connection.get('connection_string', '').replace('DSN=', '')
                    conn = pyodbc.connect(f"DSN={dsn}")
                    try:
                        cursor = conn.cursor()
                        cursor.execute(sql)
                        count = cursor.fetchone()[0]
                        return count
                    finally:
                        conn.close()
                        
                elif conn_type == 'SQL_SERVER':
                    from sqlalchemy import text
                    engine = self.conn_manager.get_engine(source.connection_id)
                    with engine.connect() as conn:
                        result = conn.execute(text(sql))
                        return result.scalar()
                        
                elif conn_type == 'ACCESS':
                    import pyodbc
                    connection = self.conn_manager.repo.get_connection(source.connection_id)
                    conn_string = connection.get('connection_string', '')
                    conn = pyodbc.connect(conn_string)
                    try:
                        cursor = conn.cursor()
                        cursor.execute(sql)
                        count = cursor.fetchone()[0]
                        return count
                    finally:
                        conn.close()
                        
            except Exception as e:
                logger.warning(f"Could not estimate rows for {source.alias}: {e}")
                return -1
        else:
            # File-based sources - would need to count rows in file
            return -1
    
    def _build_count_query(self, source: SourceConfig) -> str:
        """Build COUNT(*) query with filters"""
        dialect = 'access' if source.connection_type.upper() == 'ACCESS' else 'ansi'
        
        def quote(identifier: str) -> str:
            if dialect == 'access':
                return f"[{identifier}]"
            else:
                return f'"{identifier}"'
        
        # Build table reference
        if source.schema_name:
            table_ref = f"{quote(source.schema_name)}.{quote(source.table_name)}"
        else:
            table_ref = quote(source.table_name)
        
        sql = f"SELECT COUNT(*) FROM {table_ref}"
        
        # Add filters
        if source.filters:
            where_clauses = []
            for f in source.filters:
                col = quote(f['column'])
                op = f['operator']
                val = f['value']
                
                if isinstance(val, str):
                    val_str = f"'{val}'"
                else:
                    val_str = str(val)
                
                where_clauses.append(f"{col} {op} {val_str}")
            
            sql += " WHERE " + " AND ".join(where_clauses)
        
        return sql
    
    def get_formatted_sql_statements(self, plan: ExecutionPlan) -> str:
        """
        Format captured SQL statements for display.
        
        Returns a human-readable string showing all SQL statements executed
        including source queries and DuckDB join query.
        """
        lines = []
        lines.append("=" * 70)
        lines.append("XDB QUERY EXECUTION PLAN")
        lines.append("=" * 70)
        lines.append("")
        
        # Source queries
        if plan.source_sql_statements:
            lines.append("SOURCE QUERIES:")
            lines.append("-" * 70)
            for i, stmt in enumerate(plan.source_sql_statements, 1):
                lines.append(f"\n[{i}] {stmt.get('alias', 'Unknown')} ({stmt.get('connection_type', 'Unknown')})")
                lines.append(f"    Connection: {stmt.get('connection_name', 'Unknown')}")
                lines.append(f"    Table: {stmt.get('table', 'Unknown')}")
                lines.append("")
                # Format SQL with indentation
                sql = stmt.get('sql', '')
                for sql_line in sql.split('\n'):
                    lines.append(f"    {sql_line}")
                lines.append("")
        
        # DuckDB join query
        if plan.duckdb_join_sql:
            lines.append("-" * 70)
            lines.append("DUCKDB JOIN QUERY:")
            lines.append("-" * 70)
            lines.append("")
            for sql_line in plan.duckdb_join_sql.split('\n'):
                lines.append(f"    {sql_line}")
            lines.append("")
        
        # Execution stats
        lines.append("-" * 70)
        lines.append("EXECUTION STATS:")
        lines.append("-" * 70)
        lines.append(f"    Total Time: {plan.total_time_ms} ms")
        if plan.duckdb_time_ms > 0:
            lines.append(f"    DuckDB Time: {plan.duckdb_time_ms} ms")
        lines.append("")
        lines.append("=" * 70)
        
        return "\n".join(lines)


# Singleton instance
_engine_instance: Optional[XDBEngine] = None


def get_xdb_engine() -> XDBEngine:
    """Get the singleton XDB Engine instance"""
    global _engine_instance
    if _engine_instance is None:
        _engine_instance = XDBEngine()
    return _engine_instance
