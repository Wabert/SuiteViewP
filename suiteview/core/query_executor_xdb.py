"""Cross-Database Query Executor - Joins data from multiple database sources"""

import logging
from typing import Dict, List, Any, Optional, Tuple
import pandas as pd
from pathlib import Path

logger = logging.getLogger(__name__)


class XDBQueryExecutor:
    """
    Execute cross-database queries using DuckDB (primary) or pandas (fallback).
    
    DuckDB approach:
    - Single SQL joining odbc_query() subqueries for ODBC sources
    - Built-in file readers for CSV/Excel/Parquet
    - Columnar execution with spill-to-disk support
    - Push down filters and column projection
    
    Pandas fallback:
    - Execute queries per source, load to DataFrames
    - Join in memory with merge()
    - Memory-bound but universal
    """
    
    def __init__(self, use_duckdb: bool = True):
        """
        Initialize XDB executor
        
        Args:
            use_duckdb: Try DuckDB first (default), fall back to pandas on error
        """
        self.use_duckdb = use_duckdb
        self.duckdb_available = False
        
        if use_duckdb:
            try:
                import duckdb
                self.duckdb = duckdb
                self.duckdb_available = True
                logger.info("DuckDB backend available for XDB queries")
            except ImportError:
                logger.warning("DuckDB not installed, will use pandas backend")
                self.duckdb_available = False
    
    def execute_cross_query(
        self,
        source_a: Dict[str, Any],
        source_b: Dict[str, Any],
        join_config: Dict[str, Any],
        limit: Optional[int] = None
    ) -> pd.DataFrame:
        """
        Execute a cross-database query joining two sources
        
        Args:
            source_a: {
                'connection': connection dict from repo,
                'table_name': str,
                'schema_name': optional str,
                'columns': list of column names to select,
                'filters': list of filter dicts {'column': str, 'operator': str, 'value': Any}
            }
            source_b: same structure as source_a
            join_config: {
                'type': 'INNER'|'LEFT'|'RIGHT'|'FULL',
                'keys_a': list of column names from source A,
                'keys_b': list of column names from source B
            }
            limit: Optional row limit for preview
            
        Returns:
            pandas DataFrame with joined results
        """
        try:
            if self.duckdb_available:
                return self._execute_with_duckdb(source_a, source_b, join_config, limit)
            else:
                return self._execute_with_pandas(source_a, source_b, join_config, limit)
        except Exception as e:
            logger.error(f"DuckDB execution failed, trying pandas fallback: {e}")
            if self.duckdb_available:
                # Fallback to pandas if DuckDB fails
                return self._execute_with_pandas(source_a, source_b, join_config, limit)
            raise
    
    def _execute_with_duckdb(
        self,
        source_a: Dict,
        source_b: Dict,
        join_config: Dict,
        limit: Optional[int]
    ) -> pd.DataFrame:
        """Execute using DuckDB with odbc_query() and file readers"""
        import duckdb
        
        # Create in-memory DuckDB connection
        con = duckdb.connect(':memory:')
        
        try:
            # Install and load ODBC extension if needed
            try:
                con.execute("INSTALL odbc")
                con.execute("LOAD odbc")
                logger.debug("DuckDB ODBC extension loaded")
            except Exception as e:
                logger.debug(f"ODBC extension load info: {e}")
            
            # Configure memory and temp directory
            con.execute("SET memory_limit='2GB'")
            temp_dir = Path.home() / ".suiteview" / "duckdb_temp"
            temp_dir.mkdir(parents=True, exist_ok=True)
            con.execute(f"SET temp_directory='{temp_dir}'")
            
            # Build subqueries for each source
            subquery_a = self._build_source_subquery(source_a, "a")
            subquery_b = self._build_source_subquery(source_b, "b")
            
            # Build join clause
            join_type = join_config.get('type', 'INNER')
            keys_a = join_config.get('keys_a', [])
            keys_b = join_config.get('keys_b', [])
            
            if len(keys_a) != len(keys_b):
                raise ValueError("Join key counts must match")
            
            join_conditions = []
            for ka, kb in zip(keys_a, keys_b):
                join_conditions.append(f"a.{self._quote_identifier(ka)} = b.{self._quote_identifier(kb)}")
            
            join_clause = f"{join_type} JOIN" if join_type else "INNER JOIN"
            on_clause = " AND ".join(join_conditions) if join_conditions else "1=1"
            
            # Build final query
            limit_clause = f"LIMIT {limit}" if limit else ""
            
            final_query = f"""
            SELECT a.*, b.*
            FROM ({subquery_a}) a
            {join_clause} ({subquery_b}) b
            ON {on_clause}
            {limit_clause}
            """
            
            logger.info(f"Executing DuckDB cross-query:\n{final_query}")
            
            # Execute and fetch as DataFrame
            result_df = con.execute(final_query).fetchdf()
            
            logger.info(f"DuckDB query returned {len(result_df)} rows")
            return result_df
            
        finally:
            con.close()
    
    def _build_source_subquery(self, source: Dict, alias: str) -> str:
        """Build subquery SQL for a source (ODBC query or file reader)"""
        conn = source['connection']
        conn_type = conn.get('connection_type', 'SQL_SERVER')
        table_name = source.get('table_name', '')
        schema_name = source.get('schema_name')
        columns = source.get('columns', ['*'])
        filters = source.get('filters', [])
        
        # Handle file-based sources
        if conn_type == 'CSV':
            file_path = conn.get('connection_string', '')
            return self._build_csv_subquery(file_path, columns, filters)
        elif conn_type == 'EXCEL':
            file_path = conn.get('connection_string', '')
            return self._build_excel_subquery(file_path, table_name, columns, filters)
        elif conn_type == 'ACCESS':
            # For Access, use pandas fallback (no native DuckDB Access reader yet)
            raise NotImplementedError("Access files require pandas backend")
        
        # Handle ODBC sources (SQL_SERVER, DB2)
        dsn = conn.get('server_name') or conn.get('connection_string', '').replace('DSN=', '')
        
        # Build native SQL for the source database
        full_table = f"{self._quote_identifier(schema_name)}.{self._quote_identifier(table_name)}" if schema_name else self._quote_identifier(table_name)
        
        # Column list
        col_list = ", ".join([self._quote_identifier(c) for c in columns]) if columns and columns != ['*'] else "*"
        
        # Build WHERE clause
        where_clauses = []
        for f in filters:
            col = self._quote_identifier(f['column'])
            op = f['operator']
            val = f['value']
            
            # Simple string quoting (enhance as needed)
            if isinstance(val, str):
                val_str = f"'{val}'"
            else:
                val_str = str(val)
            
            where_clauses.append(f"{col} {op} {val_str}")
        
        where_clause = " AND ".join(where_clauses) if where_clauses else "1=1"
        
        # Build source SQL (pushdown to database)
        source_sql = f"SELECT {col_list} FROM {full_table} WHERE {where_clause}"
        
        # Wrap in DuckDB odbc_query()
        # Escape single quotes in SQL
        source_sql_escaped = source_sql.replace("'", "''")
        
        return f"SELECT * FROM odbc_query('DSN={dsn}', '{source_sql_escaped}')"
    
    def _build_csv_subquery(self, file_path: str, columns: List[str], filters: List[Dict]) -> str:
        """Build DuckDB read_csv_auto() subquery"""
        file_path_escaped = file_path.replace("'", "''")
        
        # DuckDB can apply filters after read
        subquery = f"SELECT * FROM read_csv_auto('{file_path_escaped}')"
        
        # Apply filters in WHERE clause
        if filters:
            where_clauses = []
            for f in filters:
                col = self._quote_identifier(f['column'])
                op = f['operator']
                val = f['value']
                val_str = f"'{val}'" if isinstance(val, str) else str(val)
                where_clauses.append(f"{col} {op} {val_str}")
            where_clause = " AND ".join(where_clauses)
            subquery = f"SELECT * FROM ({subquery}) WHERE {where_clause}"
        
        # Project columns
        if columns and columns != ['*']:
            col_list = ", ".join([self._quote_identifier(c) for c in columns])
            subquery = f"SELECT {col_list} FROM ({subquery})"
        
        return subquery
    
    def _build_excel_subquery(self, file_path: str, sheet_name: str, columns: List[str], filters: List[Dict]) -> str:
        """Build DuckDB read_excel() subquery - requires spatial extension"""
        # Note: DuckDB's spatial extension includes st_read which can read Excel
        # For now, use basic approach or fallback to pandas
        raise NotImplementedError("Excel requires pandas backend or DuckDB spatial extension")
    
    def _execute_with_pandas(
        self,
        source_a: Dict,
        source_b: Dict,
        join_config: Dict,
        limit: Optional[int]
    ) -> pd.DataFrame:
        """Execute using pandas in-memory joins"""
        from suiteview.core.query_executor import QueryExecutor
        executor = QueryExecutor()
        
        # Fetch data from each source
        df_a = self._fetch_source_data(executor, source_a, limit)
        df_b = self._fetch_source_data(executor, source_b, limit)
        
        # Perform join
        join_type = join_config.get('type', 'INNER').lower()
        keys_a = join_config.get('keys_a', [])
        keys_b = join_config.get('keys_b', [])
        
        if len(keys_a) != len(keys_b):
            raise ValueError("Join key counts must match")
        
        # Pandas merge
        how_map = {'INNER': 'inner', 'LEFT': 'left', 'RIGHT': 'right', 'FULL': 'outer'}
        how = how_map.get(join_type.upper(), 'inner')
        
        result_df = df_a.merge(
            df_b,
            left_on=keys_a,
            right_on=keys_b,
            how=how,
            suffixes=('_a', '_b')
        )
        
        # Apply limit if specified
        if limit:
            result_df = result_df.head(limit)
        
        logger.info(f"Pandas join returned {len(result_df)} rows")
        return result_df
    
    def _fetch_source_data(self, executor: 'QueryExecutor', source: Dict, limit: Optional[int]) -> pd.DataFrame:
        """Fetch data from a single source using existing QueryExecutor"""
        conn = source['connection']
        conn_id = conn['connection_id']
        table_name = source.get('table_name', '')
        schema_name = source.get('schema_name')
        columns = source.get('columns', ['*'])
        filters = source.get('filters', [])
        
        # Build simple SELECT query
        col_list = ", ".join(columns) if columns and columns != ['*'] else "*"
        full_table = f"{schema_name}.{table_name}" if schema_name else table_name
        
        # Build WHERE clause
        where_clauses = []
        for f in filters:
            col = f['column']
            op = f['operator']
            val = f['value']
            val_str = f"'{val}'" if isinstance(val, str) else str(val)
            where_clauses.append(f"{col} {op} {val_str}")
        
        where_clause = f" WHERE {' AND '.join(where_clauses)}" if where_clauses else ""
        limit_clause = f" LIMIT {limit}" if limit else ""
        
        query = f"SELECT {col_list} FROM {full_table}{where_clause}{limit_clause}"
        
        logger.debug(f"Fetching source data: {query}")
        
        # Execute using standard QueryExecutor
        result = executor.execute_query(conn_id, query)
        return pd.DataFrame(result['rows'], columns=result['columns'])
    
    def _quote_identifier(self, identifier: str) -> str:
        """Quote SQL identifier for safety"""
        if not identifier or identifier == '*':
            return identifier
        # Simple double-quote approach (works for most SQL dialects)
        return f'"{identifier}"'
    
    def export_to_parquet(self, df: pd.DataFrame, output_path: str):
        """Export result DataFrame to Parquet file"""
        df.to_parquet(output_path, index=False, engine='pyarrow')
        logger.info(f"Exported {len(df)} rows to {output_path}")
    
    def export_to_csv(self, df: pd.DataFrame, output_path: str):
        """Export result DataFrame to CSV file"""
        df.to_csv(output_path, index=False)
        logger.info(f"Exported {len(df)} rows to {output_path}")
