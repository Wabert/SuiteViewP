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
    
    def execute_query(
        self,
        source_configs: List[Dict],
        join_configs: List[Dict],
        limit: Optional[int] = None
    ) -> pd.DataFrame:
        """
        Execute flexible XDB query with N datasources
        
        Args:
            source_configs: List of source configurations, each with:
                - connection: Connection dict
                - table_name: Table name
                - schema_name: Schema name (optional)
                - alias: Datasource alias
                - columns: List of column names or ['*']
                - filters: List of filter dicts
            join_configs: List of join configurations (empty if single source)
            limit: Optional row limit
        
        Returns:
            DataFrame with query results
        """
        try:
            # Single datasource - no joins needed
            if len(source_configs) == 1:
                return self._execute_single_source(source_configs[0], limit)
            
            # Multiple datasources - use DuckDB for joins
            if self.duckdb_available:
                return self._execute_with_duckdb_flexible(source_configs, join_configs, limit)
            else:
                # Fallback to pandas (only supports 2-way joins currently)
                if len(source_configs) == 2 and len(join_configs) >= 1:
                    return self._execute_with_pandas(
                        source_configs[0],
                        source_configs[1],
                        join_configs[0],
                        limit
                    )
                else:
                    raise RuntimeError("Pandas backend only supports 2-way joins. Install DuckDB for N-way joins.")
        
        except Exception as e:
            logger.error(f"XDB query execution failed: {e}", exc_info=True)
            raise
    
    def _execute_single_source(self, source: Dict, limit: Optional[int]) -> pd.DataFrame:
        """Execute query on single datasource - just use standard QueryExecutor"""
        # For single source, no need for DuckDB complexity - use standard query executor
        return self.execute_single_source_query(source, limit)
    
    def _execute_with_duckdb_flexible(
        self,
        source_configs: List[Dict],
        join_configs: List[Dict],
        limit: Optional[int]
    ) -> pd.DataFrame:
        """Execute N-way join using DuckDB with pre-fetched data"""
        import duckdb
        
        conn = duckdb.connect(':memory:')
        
        try:
            # Configure memory
            conn.execute("SET memory_limit='2GB'")
            
            # Fetch data from all sources first
            source_dataframes = []
            source_aliases = []
            
            for i, source in enumerate(source_configs):
                alias = source.get('alias', f's{i}')
                source_aliases.append(alias)
                
                logger.info(f"Fetching data from source '{alias}'...")
                df = self.execute_single_source_query(source, None)  # No limit yet
                source_dataframes.append(df)
                
                # Register DataFrame in DuckDB
                conn.register(alias, df)
                logger.info(f"Registered {len(df)} rows as '{alias}'")
            
            # Build SELECT clause from all sources
            select_parts = []
            for i, source in enumerate(source_configs):
                alias = source_aliases[i]
                columns = source.get('columns', ['*'])
                
                if columns == []:
                    # No columns selected for this alias; skip
                    continue
                if columns and columns != ['*']:
                    for col in columns:
                        select_parts.append(f'{alias}."{col}"')
                else:
                    # columns is None or ['*'] -> select all from this alias
                    select_parts.append(f'{alias}.*')
            
            # If nothing explicitly selected, default to first alias all columns
            select_clause = ", ".join(select_parts) if select_parts else f"{source_aliases[0]}.*"
            
            # Build FROM clause
            first_alias = source_aliases[0]
            from_clause = f"FROM {first_alias}"
            
            # Build JOIN clauses
            join_clauses = []
            for i, join_config in enumerate(join_configs):
                # Join connects source i to source i+1
                left_alias = join_config.get('source_a_alias', source_aliases[i])
                right_alias = join_config.get('source_b_alias', source_aliases[i + 1])
                join_type = join_config.get('type', 'INNER')
                
                # Build ON conditions
                on_conditions = join_config.get('on_conditions', [])
                if not on_conditions:
                    # Fallback to keys_a/keys_b format
                    keys_a = join_config.get('keys_a', [])
                    keys_b = join_config.get('keys_b', [])
                    on_conditions = [{'field_a': ka, 'field_b': kb} for ka, kb in zip(keys_a, keys_b)]
                
                on_parts = []
                for cond in on_conditions:
                    field_a = cond.get('field_a', '')
                    field_b = cond.get('field_b', '')
                    if field_a and field_b:
                        on_parts.append(f'{left_alias}."{field_a}" = {right_alias}."{field_b}"')
                
                on_clause = " AND ".join(on_parts) if on_parts else "1=1"
                
                join_clause = f"{join_type} JOIN {right_alias} ON {on_clause}"
                join_clauses.append(join_clause)
            
            # Build complete SQL
            sql = f"SELECT {select_clause}\n{from_clause}"
            for jc in join_clauses:
                sql += f"\n{jc}"
            
            if limit:
                sql += f"\nLIMIT {limit}"
            
            logger.info(f"Flexible DuckDB query:\n{sql}")
            
            # Show query popup
            from PyQt6.QtWidgets import QMessageBox
            QMessageBox.information(None, "DuckDB Query", f"Executing:\n\n{sql}")
            
            # Execute
            result_df = conn.execute(sql).fetchdf()
            logger.info(f"Flexible query returned {len(result_df)} rows")
            
            return result_df
            
        finally:
            conn.close()
    
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
        logger.info(f"execute_cross_query called - DuckDB available: {self.duckdb_available}")
        
        try:
            if self.duckdb_available:
                logger.info("Attempting DuckDB execution...")
                return self._execute_with_duckdb(source_a, source_b, join_config, limit)
            else:
                logger.info("DuckDB not available, using pandas...")
                return self._execute_with_pandas(source_a, source_b, join_config, limit)
        except Exception as e:
            logger.error(f"DuckDB execution failed, trying pandas fallback: {e}", exc_info=True)
            if self.duckdb_available:
                # Fallback to pandas if DuckDB fails
                logger.info("Falling back to pandas execution...")
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
            
            # Show query in message box for debugging
            try:
                from PyQt6.QtWidgets import QMessageBox, QApplication
                app = QApplication.instance()
                if app:
                    msg = QMessageBox()
                    msg.setWindowTitle("DuckDB Query")
                    msg.setText("About to execute the following DuckDB query:")
                    msg.setDetailedText(final_query)
                    msg.setStandardButtons(QMessageBox.StandardButton.Ok | QMessageBox.StandardButton.Cancel)
                    msg.setDefaultButton(QMessageBox.StandardButton.Ok)
                    result = msg.exec()
                    
                    if result == QMessageBox.StandardButton.Cancel:
                        raise Exception("Query execution cancelled by user")
            except ImportError:
                pass  # PyQt6 not available, skip dialog
            
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
    
    def execute_single_source_query(self, source: Dict, limit: Optional[int] = None) -> pd.DataFrame:
        """Execute a query on a single datasource (no joins)"""
        from suiteview.core.query_builder import Query
        from suiteview.core.query_executor import QueryExecutor
        
        conn = source['connection']
        conn_id = conn['connection_id']
        table_name = source.get('table_name', '')
        schema_name = source.get('schema_name')
        columns = source.get('columns', ['*'])
        filters = source.get('filters', [])
        
        # Default schema for SQL Server if missing
        conn_type = conn.get('connection_type')
        if not schema_name and conn_type == 'SQL_SERVER':
            schema_name = 'dbo'
        
        # Build Query object
        query = Query()
        query.connection_id = conn_id
        query.from_table = table_name
        query.from_schema = schema_name
        
        # Set display fields
        if columns and columns != ['*']:
            query.display_fields = [{'field_name': col, 'table_name': table_name} for col in columns]
        else:
            query.display_fields = [{'field_name': '*', 'table_name': table_name}]
        
        # Set criteria filters
        query.criteria = []
        for f in filters:
            query.criteria.append({
                'field_name': f['column'],
                'operator': f['operator'],
                'value': f['value'],
                'table_name': table_name
            })
        
        logger.info(f"Executing single-source query on {table_name}")
        logger.info(f"Columns: {columns}")
        logger.info(f"Filters: {filters}")
        
        # Execute using standard QueryExecutor
        executor = QueryExecutor()
        result_df = executor.execute_db_query(query)
        
        # Apply limit if specified
        if limit:
            result_df = result_df.head(limit)
        
        logger.info(f"Single-source query returned {len(result_df)} rows")
        return result_df
    
    def _fetch_source_data(self, executor, source: Dict, limit: Optional[int]) -> pd.DataFrame:
        """Fetch data from a single source using existing QueryExecutor (internal helper for joins)"""
        from suiteview.core.query_builder import Query
        
        conn = source['connection']
        conn_id = conn['connection_id']
        table_name = source.get('table_name', '')
        schema_name = source.get('schema_name')
        columns = source.get('columns', ['*'])
        filters = source.get('filters', [])
        
        # Default schema for SQL Server if missing
        conn_type = conn.get('connection_type')
        if not schema_name and conn_type == 'SQL_SERVER':
            schema_name = 'dbo'
        
        # Build Query object
        query = Query()
        query.connection_id = conn_id
        query.from_table = table_name
        query.from_schema = schema_name
        
        # Set display fields
        if columns and columns != ['*']:
            query.display_fields = [{'field_name': col, 'table_name': table_name} for col in columns]
        else:
            query.display_fields = [{'field_name': '*', 'table_name': table_name}]
        
        # Set criteria filters
        query.criteria = []
        for f in filters:
            query.criteria.append({
                'field_name': f['column'],
                'operator': f['operator'],
                'value': f['value'],
                'table_name': table_name
            })
        
        logger.debug(f"Fetching source data from {table_name}")
        
        # Execute using standard QueryExecutor
        result_df = executor.execute_db_query(query)
        
        # Apply limit if specified
        if limit:
            result_df = result_df.head(limit)
        
        return result_df
    
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
