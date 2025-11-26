"""XDB Data Source Abstraction Layer

This module provides a unified interface for accessing different data sources
(DB2, SQL Server, Access, CSV, Excel, and saved DB Queries) with intelligent
filter pushdown for efficient data retrieval.
"""

import logging
import re
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple, Union

import pandas as pd

from suiteview.core.connection_manager import get_connection_manager
from suiteview.core.credential_manager import get_credential_manager
from suiteview.core.schema_discovery import _validate_sql_identifier
from suiteview.data.repositories import (
    get_connection_repository,
    get_query_repository,
    get_metadata_cache_repository,
)
from suiteview.utils.connection_strings import (
    build_db2_connection,
    build_access_connection,
)

logger = logging.getLogger(__name__)


@dataclass
class FilterCriteria:
    """Represents a filter condition for a data source"""
    column: str
    operator: str  # 'eq', 'ne', 'lt', 'le', 'gt', 'ge', 'in', 'like', 'between', 'is_null', 'not_null'
    value: Any = None  # Single value, list (for 'in'), or tuple (for 'between')
    data_type: str = 'string'  # 'string', 'number', 'date', 'datetime'

    def to_sql_condition(self, param_prefix: str = 'p') -> Tuple[str, Dict[str, Any]]:
        """
        Convert filter to SQL WHERE clause fragment with parameterized values.

        Returns:
            Tuple of (sql_fragment, params_dict)
        """
        # Validate column name to prevent SQL injection
        safe_column = _validate_sql_identifier(self.column, "column")
        params = {}
        param_name = f"{param_prefix}_{safe_column.replace('.', '_')}"

        if self.operator == 'eq':
            return f"{safe_column} = :{param_name}", {param_name: self.value}
        elif self.operator == 'ne':
            return f"{safe_column} <> :{param_name}", {param_name: self.value}
        elif self.operator == 'lt':
            return f"{safe_column} < :{param_name}", {param_name: self.value}
        elif self.operator == 'le':
            return f"{safe_column} <= :{param_name}", {param_name: self.value}
        elif self.operator == 'gt':
            return f"{safe_column} > :{param_name}", {param_name: self.value}
        elif self.operator == 'ge':
            return f"{safe_column} >= :{param_name}", {param_name: self.value}
        elif self.operator == 'in':
            # For IN clause, need multiple params
            if not isinstance(self.value, (list, tuple)):
                return f"{safe_column} = :{param_name}", {param_name: self.value}
            placeholders = []
            for i, v in enumerate(self.value):
                p_name = f"{param_name}_{i}"
                placeholders.append(f":{p_name}")
                params[p_name] = v
            return f"{safe_column} IN ({', '.join(placeholders)})", params
        elif self.operator == 'like':
            return f"{safe_column} LIKE :{param_name}", {param_name: self.value}
        elif self.operator == 'between':
            if isinstance(self.value, (list, tuple)) and len(self.value) == 2:
                return (
                    f"{safe_column} BETWEEN :{param_name}_low AND :{param_name}_high",
                    {f"{param_name}_low": self.value[0], f"{param_name}_high": self.value[1]}
                )
            raise ValueError(f"'between' operator requires tuple of (low, high)")
        elif self.operator == 'is_null':
            return f"{safe_column} IS NULL", {}
        elif self.operator == 'not_null':
            return f"{safe_column} IS NOT NULL", {}
        else:
            raise ValueError(f"Unknown operator: {self.operator}")

    def apply_to_dataframe(self, df: pd.DataFrame) -> pd.DataFrame:
        """Apply this filter to a pandas DataFrame (for in-memory filtering)"""
        if self.column not in df.columns:
            logger.warning(f"Column {self.column} not found in DataFrame")
            return df

        col = df[self.column]

        if self.operator == 'eq':
            mask = col == self.value
        elif self.operator == 'ne':
            mask = col != self.value
        elif self.operator == 'lt':
            mask = col < self.value
        elif self.operator == 'le':
            mask = col <= self.value
        elif self.operator == 'gt':
            mask = col > self.value
        elif self.operator == 'ge':
            mask = col >= self.value
        elif self.operator == 'in':
            mask = col.isin(self.value if isinstance(self.value, (list, tuple)) else [self.value])
        elif self.operator == 'like':
            # Convert SQL LIKE pattern to regex
            pattern = self.value.replace('%', '.*').replace('_', '.')
            mask = col.astype(str).str.match(f"^{pattern}$", case=False, na=False)
        elif self.operator == 'between':
            if isinstance(self.value, (list, tuple)) and len(self.value) == 2:
                mask = (col >= self.value[0]) & (col <= self.value[1])
            else:
                return df
        elif self.operator == 'is_null':
            mask = col.isna()
        elif self.operator == 'not_null':
            mask = col.notna()
        else:
            return df

        return df[mask]


@dataclass
class SourceColumn:
    """Metadata for a column in a data source"""
    name: str
    data_type: str
    is_nullable: bool = True
    is_primary_key: bool = False
    max_length: Optional[int] = None

    @property
    def prefixed_name(self) -> str:
        """Get column name with source alias prefix"""
        return self.name


@dataclass
class DataSource(ABC):
    """Abstract base class for all XDB data sources"""

    alias: str  # User-defined alias for this source (e.g., 'src1', 'customers')
    columns: List[SourceColumn] = field(default_factory=list)
    filters: List[FilterCriteria] = field(default_factory=list)
    select_columns: List[str] = field(default_factory=list)  # Empty = select all

    @property
    @abstractmethod
    def source_type(self) -> str:
        """Return the type of data source (e.g., 'DB2', 'SQL_SERVER', 'CSV')"""
        pass

    @property
    @abstractmethod
    def display_name(self) -> str:
        """Human-readable name for this source (e.g., 'Production.CLAIMS')"""
        pass

    @property
    @abstractmethod
    def supports_filter_pushdown(self) -> bool:
        """Whether this source supports pushing filters to the database"""
        pass

    @abstractmethod
    def fetch_data(self, limit: Optional[int] = None) -> pd.DataFrame:
        """
        Fetch data from the source with filters applied.

        Args:
            limit: Optional row limit for testing/preview

        Returns:
            pandas DataFrame with the fetched data
        """
        pass

    @abstractmethod
    def get_columns(self) -> List[SourceColumn]:
        """Get column metadata for this source"""
        pass

    def add_filter(self, filter_criteria: FilterCriteria):
        """Add a filter to this source"""
        self.filters.append(filter_criteria)

    def clear_filters(self):
        """Remove all filters from this source"""
        self.filters.clear()

    def set_select_columns(self, columns: List[str]):
        """Set which columns to select (empty list = all columns)"""
        self.select_columns = columns

    def get_prefixed_columns(self) -> List[str]:
        """Get column names prefixed with the source alias"""
        columns = self.select_columns if self.select_columns else [c.name for c in self.get_columns()]
        return [f"{self.alias}.{col}" for col in columns]

    def _prefix_dataframe_columns(self, df: pd.DataFrame) -> pd.DataFrame:
        """Add source alias prefix to all DataFrame columns"""
        df = df.copy()
        df.columns = [f"{self.alias}.{col}" for col in df.columns]
        return df


@dataclass
class DB2Source(DataSource):
    """Data source for IBM DB2 databases via ODBC DSN"""

    connection_id: int = 0
    dsn: str = ''
    schema_name: str = ''
    table_name: str = ''

    @property
    def source_type(self) -> str:
        return 'DB2'

    @property
    def display_name(self) -> str:
        if self.schema_name:
            return f"{self.dsn}.{self.schema_name}.{self.table_name}"
        return f"{self.dsn}.{self.table_name}"

    @property
    def supports_filter_pushdown(self) -> bool:
        return True

    def fetch_data(self, limit: Optional[int] = None) -> pd.DataFrame:
        """Fetch data from DB2 with filter pushdown"""
        import pyodbc

        # Build connection string
        conn_str = build_db2_connection(self.dsn)

        # Build SELECT clause
        if self.select_columns:
            columns = ', '.join([_validate_sql_identifier(c) for c in self.select_columns])
        else:
            columns = '*'

        # Build FROM clause
        if self.schema_name:
            table_ref = f"{_validate_sql_identifier(self.schema_name)}.{_validate_sql_identifier(self.table_name)}"
        else:
            table_ref = _validate_sql_identifier(self.table_name)

        # Build WHERE clause with filter pushdown
        where_clauses = []
        params = {}
        for i, f in enumerate(self.filters):
            sql_frag, frag_params = f.to_sql_condition(f"p{i}")
            where_clauses.append(sql_frag)
            params.update(frag_params)

        # Construct query
        query = f"SELECT {columns} FROM {table_ref}"
        if where_clauses:
            query += " WHERE " + " AND ".join(where_clauses)
        if limit:
            query += f" FETCH FIRST {int(limit)} ROWS ONLY"

        logger.info(f"DB2 Query: {query}")

        # Execute query
        try:
            conn = pyodbc.connect(conn_str)

            # Convert named params to positional for pyodbc
            # pyodbc uses ? placeholders
            param_values = []
            for key in sorted(params.keys()):
                query = query.replace(f":{key}", "?")
                param_values.append(params[key])

            df = pd.read_sql(query, conn, params=param_values if param_values else None)
            conn.close()

            return self._prefix_dataframe_columns(df)

        except Exception as e:
            logger.error(f"DB2 query failed: {e}")
            raise

    def get_columns(self) -> List[SourceColumn]:
        """Get column metadata from cached metadata or fresh discovery"""
        if self.columns:
            return self.columns

        # Try to get from cache first
        cache_repo = get_metadata_cache_repository()
        metadata_id = cache_repo.get_metadata_id(
            self.connection_id, self.table_name, self.schema_name
        )

        if metadata_id:
            cached = cache_repo.get_cached_columns(metadata_id)
            if cached:
                self.columns = [
                    SourceColumn(
                        name=c['name'],
                        data_type=c['type'],
                        is_nullable=c.get('nullable', True),
                        is_primary_key=c.get('primary_key', False),
                        max_length=c.get('max_length')
                    )
                    for c in cached
                ]
                return self.columns

        # Fetch fresh from database
        import pyodbc
        conn_str = build_db2_connection(self.dsn)

        try:
            conn = pyodbc.connect(conn_str)
            cursor = conn.cursor()

            # Use DB2 catalog to get column info
            if self.schema_name:
                cursor.execute("""
                    SELECT COLNAME, TYPENAME, LENGTH, NULLS, KEYSEQ
                    FROM SYSCAT.COLUMNS
                    WHERE TABSCHEMA = ? AND TABNAME = ?
                    ORDER BY COLNO
                """, (self.schema_name, self.table_name))
            else:
                cursor.execute("""
                    SELECT COLNAME, TYPENAME, LENGTH, NULLS, KEYSEQ
                    FROM SYSCAT.COLUMNS
                    WHERE TABNAME = ?
                    ORDER BY COLNO
                """, (self.table_name,))

            self.columns = []
            for row in cursor.fetchall():
                self.columns.append(SourceColumn(
                    name=row[0],
                    data_type=row[1],
                    max_length=row[2],
                    is_nullable=(row[3] == 'Y'),
                    is_primary_key=(row[4] is not None and row[4] > 0)
                ))

            conn.close()
            return self.columns

        except Exception as e:
            logger.error(f"Failed to get DB2 columns: {e}")
            return []


@dataclass
class SQLServerSource(DataSource):
    """Data source for Microsoft SQL Server databases"""

    connection_id: int = 0
    server: str = ''
    database: str = ''
    schema_name: str = 'dbo'
    table_name: str = ''

    @property
    def source_type(self) -> str:
        return 'SQL_SERVER'

    @property
    def display_name(self) -> str:
        return f"{self.database}.{self.schema_name}.{self.table_name}"

    @property
    def supports_filter_pushdown(self) -> bool:
        return True

    def fetch_data(self, limit: Optional[int] = None) -> pd.DataFrame:
        """Fetch data from SQL Server with filter pushdown"""
        from sqlalchemy import text

        conn_mgr = get_connection_manager()
        engine = conn_mgr.get_engine(self.connection_id)

        # Build SELECT clause
        if self.select_columns:
            columns = ', '.join([f"[{_validate_sql_identifier(c)}]" for c in self.select_columns])
        else:
            columns = '*'

        # Build FROM clause
        table_ref = f"[{_validate_sql_identifier(self.schema_name)}].[{_validate_sql_identifier(self.table_name)}]"

        # Build WHERE clause with filter pushdown
        where_clauses = []
        params = {}
        for i, f in enumerate(self.filters):
            sql_frag, frag_params = f.to_sql_condition(f"p{i}")
            where_clauses.append(sql_frag)
            params.update(frag_params)

        # Construct query
        if limit:
            query = f"SELECT TOP {int(limit)} {columns} FROM {table_ref}"
        else:
            query = f"SELECT {columns} FROM {table_ref}"

        if where_clauses:
            query += " WHERE " + " AND ".join(where_clauses)

        logger.info(f"SQL Server Query: {query}")

        # Execute query
        try:
            with engine.connect() as conn:
                df = pd.read_sql(text(query), conn, params=params)

            return self._prefix_dataframe_columns(df)

        except Exception as e:
            logger.error(f"SQL Server query failed: {e}")
            raise

    def get_columns(self) -> List[SourceColumn]:
        """Get column metadata from cached metadata or fresh discovery"""
        if self.columns:
            return self.columns

        # Try to get from cache first
        cache_repo = get_metadata_cache_repository()
        metadata_id = cache_repo.get_metadata_id(
            self.connection_id, self.table_name, self.schema_name
        )

        if metadata_id:
            cached = cache_repo.get_cached_columns(metadata_id)
            if cached:
                self.columns = [
                    SourceColumn(
                        name=c['name'],
                        data_type=c['type'],
                        is_nullable=c.get('nullable', True),
                        is_primary_key=c.get('primary_key', False),
                        max_length=c.get('max_length')
                    )
                    for c in cached
                ]
                return self.columns

        # Fetch fresh from database using SQLAlchemy reflection
        from sqlalchemy import inspect

        conn_mgr = get_connection_manager()
        engine = conn_mgr.get_engine(self.connection_id)

        try:
            inspector = inspect(engine)
            columns_info = inspector.get_columns(self.table_name, schema=self.schema_name)
            pk_columns = inspector.get_pk_constraint(self.table_name, schema=self.schema_name)
            pk_column_names = pk_columns.get('constrained_columns', []) if pk_columns else []

            self.columns = []
            for col in columns_info:
                self.columns.append(SourceColumn(
                    name=col['name'],
                    data_type=str(col['type']),
                    is_nullable=col.get('nullable', True),
                    is_primary_key=(col['name'] in pk_column_names),
                    max_length=getattr(col['type'], 'length', None)
                ))

            return self.columns

        except Exception as e:
            logger.error(f"Failed to get SQL Server columns: {e}")
            return []


@dataclass
class AccessSource(DataSource):
    """Data source for Microsoft Access databases (.mdb, .accdb)"""

    connection_id: int = 0
    file_path: str = ''
    table_name: str = ''

    @property
    def source_type(self) -> str:
        return 'ACCESS'

    @property
    def display_name(self) -> str:
        import os
        db_name = os.path.basename(self.file_path)
        return f"{db_name}.{self.table_name}"

    @property
    def supports_filter_pushdown(self) -> bool:
        return True  # Access supports SQL queries

    def fetch_data(self, limit: Optional[int] = None) -> pd.DataFrame:
        """Fetch data from Access with filter pushdown"""
        import pyodbc

        conn_str = build_access_connection(self.file_path)

        # Build SELECT clause
        if self.select_columns:
            columns = ', '.join([f"[{_validate_sql_identifier(c)}]" for c in self.select_columns])
        else:
            columns = '*'

        # Build FROM clause
        table_ref = f"[{_validate_sql_identifier(self.table_name)}]"

        # Build WHERE clause with filter pushdown
        where_clauses = []
        params = {}
        for i, f in enumerate(self.filters):
            sql_frag, frag_params = f.to_sql_condition(f"p{i}")
            where_clauses.append(sql_frag)
            params.update(frag_params)

        # Construct query (Access uses TOP for limit)
        if limit:
            query = f"SELECT TOP {int(limit)} {columns} FROM {table_ref}"
        else:
            query = f"SELECT {columns} FROM {table_ref}"

        if where_clauses:
            query += " WHERE " + " AND ".join(where_clauses)

        logger.info(f"Access Query: {query}")

        # Execute query
        try:
            conn = pyodbc.connect(conn_str)

            # Convert named params to positional for pyodbc
            param_values = []
            for key in sorted(params.keys()):
                query = query.replace(f":{key}", "?")
                param_values.append(params[key])

            df = pd.read_sql(query, conn, params=param_values if param_values else None)
            conn.close()

            return self._prefix_dataframe_columns(df)

        except Exception as e:
            logger.error(f"Access query failed: {e}")
            raise

    def get_columns(self) -> List[SourceColumn]:
        """Get column metadata from Access database"""
        if self.columns:
            return self.columns

        import pyodbc
        conn_str = build_access_connection(self.file_path)

        try:
            conn = pyodbc.connect(conn_str)
            cursor = conn.cursor()

            # Get column info using cursor.columns()
            self.columns = []
            for row in cursor.columns(table=self.table_name):
                self.columns.append(SourceColumn(
                    name=row.column_name,
                    data_type=row.type_name,
                    max_length=row.column_size,
                    is_nullable=(row.nullable == 1)
                ))

            conn.close()
            return self.columns

        except Exception as e:
            logger.error(f"Failed to get Access columns: {e}")
            return []


@dataclass
class CSVSource(DataSource):
    """Data source for CSV/flat files"""

    file_path: str = ''
    delimiter: str = ','
    encoding: str = 'utf-8'
    has_header: bool = True

    _cached_df: Optional[pd.DataFrame] = field(default=None, repr=False)

    @property
    def source_type(self) -> str:
        return 'CSV'

    @property
    def display_name(self) -> str:
        import os
        return os.path.basename(self.file_path)

    @property
    def supports_filter_pushdown(self) -> bool:
        return False  # CSV files are read entirely into memory

    def fetch_data(self, limit: Optional[int] = None) -> pd.DataFrame:
        """Fetch data from CSV file with in-memory filtering"""
        try:
            # Read CSV file
            df = pd.read_csv(
                self.file_path,
                delimiter=self.delimiter,
                encoding=self.encoding,
                header=0 if self.has_header else None,
                nrows=limit if limit and not self.filters else None
            )

            # Apply filters in memory
            for f in self.filters:
                df = f.apply_to_dataframe(df)

            # Apply limit after filtering if we have filters
            if limit and self.filters and len(df) > limit:
                df = df.head(limit)

            # Select specific columns if requested
            if self.select_columns:
                available = [c for c in self.select_columns if c in df.columns]
                df = df[available]

            return self._prefix_dataframe_columns(df)

        except Exception as e:
            logger.error(f"CSV read failed: {e}")
            raise

    def get_columns(self) -> List[SourceColumn]:
        """Get column metadata by reading CSV header"""
        if self.columns:
            return self.columns

        try:
            # Read just the header
            df = pd.read_csv(
                self.file_path,
                delimiter=self.delimiter,
                encoding=self.encoding,
                header=0 if self.has_header else None,
                nrows=5  # Read a few rows to infer types
            )

            self.columns = []
            for col in df.columns:
                # Infer data type from pandas dtype
                dtype = df[col].dtype
                if pd.api.types.is_integer_dtype(dtype):
                    data_type = 'integer'
                elif pd.api.types.is_float_dtype(dtype):
                    data_type = 'float'
                elif pd.api.types.is_datetime64_any_dtype(dtype):
                    data_type = 'datetime'
                else:
                    data_type = 'string'

                self.columns.append(SourceColumn(
                    name=str(col),
                    data_type=data_type
                ))

            return self.columns

        except Exception as e:
            logger.error(f"Failed to get CSV columns: {e}")
            return []


@dataclass
class ExcelSource(DataSource):
    """Data source for Excel files (.xlsx, .xls)"""

    file_path: str = ''
    sheet_name: Union[str, int] = 0  # Sheet name or index

    @property
    def source_type(self) -> str:
        return 'EXCEL'

    @property
    def display_name(self) -> str:
        import os
        file_name = os.path.basename(self.file_path)
        sheet_display = self.sheet_name if isinstance(self.sheet_name, str) else f"Sheet{self.sheet_name + 1}"
        return f"{file_name}[{sheet_display}]"

    @property
    def supports_filter_pushdown(self) -> bool:
        return False  # Excel files are read entirely into memory

    def fetch_data(self, limit: Optional[int] = None) -> pd.DataFrame:
        """Fetch data from Excel file with in-memory filtering"""
        try:
            # Read Excel file
            df = pd.read_excel(
                self.file_path,
                sheet_name=self.sheet_name,
                nrows=limit if limit and not self.filters else None
            )

            # Apply filters in memory
            for f in self.filters:
                df = f.apply_to_dataframe(df)

            # Apply limit after filtering if we have filters
            if limit and self.filters and len(df) > limit:
                df = df.head(limit)

            # Select specific columns if requested
            if self.select_columns:
                available = [c for c in self.select_columns if c in df.columns]
                df = df[available]

            return self._prefix_dataframe_columns(df)

        except Exception as e:
            logger.error(f"Excel read failed: {e}")
            raise

    def get_columns(self) -> List[SourceColumn]:
        """Get column metadata by reading Excel header"""
        if self.columns:
            return self.columns

        try:
            # Read just the header rows
            df = pd.read_excel(
                self.file_path,
                sheet_name=self.sheet_name,
                nrows=5
            )

            self.columns = []
            for col in df.columns:
                dtype = df[col].dtype
                if pd.api.types.is_integer_dtype(dtype):
                    data_type = 'integer'
                elif pd.api.types.is_float_dtype(dtype):
                    data_type = 'float'
                elif pd.api.types.is_datetime64_any_dtype(dtype):
                    data_type = 'datetime'
                else:
                    data_type = 'string'

                self.columns.append(SourceColumn(
                    name=str(col),
                    data_type=data_type
                ))

            return self.columns

        except Exception as e:
            logger.error(f"Failed to get Excel columns: {e}")
            return []


@dataclass
class SavedDBQuerySource(DataSource):
    """Data source that wraps a saved DB Query as a virtual table"""

    query_id: int = 0
    query_name: str = ''
    _query_definition: Optional[Dict] = field(default=None, repr=False)

    @property
    def source_type(self) -> str:
        return 'DB_QUERY'

    @property
    def display_name(self) -> str:
        return f"Query: {self.query_name}"

    @property
    def supports_filter_pushdown(self) -> bool:
        # We can potentially push filters into the underlying query
        # but for simplicity, we'll execute the query then filter in memory
        return False

    def _load_query_definition(self):
        """Load the saved query definition from the repository"""
        if self._query_definition is None:
            query_repo = get_query_repository()
            query = query_repo.get_query(self.query_id)
            if query:
                self._query_definition = query['query_definition']
                self.query_name = query['query_name']
            else:
                raise ValueError(f"Saved query with ID {self.query_id} not found")

    def fetch_data(self, limit: Optional[int] = None) -> pd.DataFrame:
        """Execute the saved DB query and apply additional filters"""
        from suiteview.core.query_executor import QueryExecutor

        self._load_query_definition()

        # Execute the underlying DB query
        executor = QueryExecutor()
        df = executor.execute_query(self._query_definition)

        # Apply additional filters in memory
        for f in self.filters:
            df = f.apply_to_dataframe(df)

        # Apply limit after filtering
        if limit and len(df) > limit:
            df = df.head(limit)

        # Select specific columns if requested
        if self.select_columns:
            available = [c for c in self.select_columns if c in df.columns]
            df = df[available]

        return self._prefix_dataframe_columns(df)

    def get_columns(self) -> List[SourceColumn]:
        """Get column metadata from the saved query's display fields"""
        if self.columns:
            return self.columns

        self._load_query_definition()

        # Extract columns from query definition's display_fields
        display_fields = self._query_definition.get('display_fields', [])

        self.columns = []
        for field_def in display_fields:
            if isinstance(field_def, dict):
                col_name = field_def.get('field', field_def.get('column', ''))
                data_type = field_def.get('type', 'string')
            else:
                col_name = str(field_def)
                data_type = 'string'

            if col_name:
                self.columns.append(SourceColumn(
                    name=col_name,
                    data_type=data_type
                ))

        return self.columns


def create_source(
    source_type: str,
    alias: str,
    connection_id: Optional[int] = None,
    **kwargs
) -> DataSource:
    """
    Factory function to create the appropriate data source instance.

    Args:
        source_type: Type of source ('DB2', 'SQL_SERVER', 'ACCESS', 'CSV', 'EXCEL', 'DB_QUERY')
        alias: User-defined alias for this source
        connection_id: Connection ID for database sources
        **kwargs: Source-specific parameters

    Returns:
        Configured DataSource instance
    """
    source_type = source_type.upper()

    if source_type == 'DB2':
        # Get connection details
        conn_repo = get_connection_repository()
        conn = conn_repo.get_connection(connection_id)
        if not conn:
            raise ValueError(f"Connection {connection_id} not found")

        dsn = conn.get('connection_string', '').replace('DSN=', '')

        return DB2Source(
            alias=alias,
            connection_id=connection_id,
            dsn=dsn,
            schema_name=kwargs.get('schema_name', ''),
            table_name=kwargs.get('table_name', '')
        )

    elif source_type == 'SQL_SERVER':
        conn_repo = get_connection_repository()
        conn = conn_repo.get_connection(connection_id)
        if not conn:
            raise ValueError(f"Connection {connection_id} not found")

        return SQLServerSource(
            alias=alias,
            connection_id=connection_id,
            server=conn.get('server_name', ''),
            database=conn.get('database_name', ''),
            schema_name=kwargs.get('schema_name', 'dbo'),
            table_name=kwargs.get('table_name', '')
        )

    elif source_type == 'ACCESS':
        conn_repo = get_connection_repository()
        conn = conn_repo.get_connection(connection_id)
        if not conn:
            raise ValueError(f"Connection {connection_id} not found")

        # Access file path is stored in connection_string or database_name
        file_path = conn.get('connection_string') or conn.get('database_name', '')

        return AccessSource(
            alias=alias,
            connection_id=connection_id,
            file_path=file_path,
            table_name=kwargs.get('table_name', '')
        )

    elif source_type == 'CSV':
        return CSVSource(
            alias=alias,
            file_path=kwargs.get('file_path', ''),
            delimiter=kwargs.get('delimiter', ','),
            encoding=kwargs.get('encoding', 'utf-8'),
            has_header=kwargs.get('has_header', True)
        )

    elif source_type == 'EXCEL':
        return ExcelSource(
            alias=alias,
            file_path=kwargs.get('file_path', ''),
            sheet_name=kwargs.get('sheet_name', 0)
        )

    elif source_type in ('DB_QUERY', 'SAVED_QUERY'):
        return SavedDBQuerySource(
            alias=alias,
            query_id=kwargs.get('query_id', 0),
            query_name=kwargs.get('query_name', '')
        )

    else:
        raise ValueError(f"Unknown source type: {source_type}")
