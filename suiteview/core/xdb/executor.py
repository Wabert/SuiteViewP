"""XDB Query Executor

This module provides the cross-database query execution engine that:
1. Fetches data from multiple sources with filter pushdown
2. Performs joins between sources using DuckDB (with Pandas fallback)
3. Applies final output column selection
4. Handles errors by aborting if any source fails
"""

import logging
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

import pandas as pd

from .sources import DataSource, FilterCriteria

logger = logging.getLogger(__name__)


# Try to import DuckDB for efficient joins
try:
    import duckdb
    HAS_DUCKDB = True
except ImportError:
    HAS_DUCKDB = False
    logger.warning("DuckDB not available, using Pandas for joins (slower for large datasets)")


@dataclass
class JoinConfig:
    """Configuration for a join between two data sources"""

    left_source_alias: str
    right_source_alias: str
    join_type: str  # 'INNER', 'LEFT', 'RIGHT', 'FULL'
    on_conditions: List[Tuple[str, str, str]]  # List of (left_col, operator, right_col)

    def to_sql(self) -> str:
        """Convert to SQL JOIN clause fragment"""
        conditions = []
        for left_col, op, right_col in self.on_conditions:
            conditions.append(f"{left_col} {op} {right_col}")

        join_type_sql = {
            'INNER': 'INNER JOIN',
            'LEFT': 'LEFT JOIN',
            'RIGHT': 'RIGHT JOIN',
            'FULL': 'FULL OUTER JOIN',
        }.get(self.join_type.upper(), 'INNER JOIN')

        return f"{join_type_sql} {self.right_source_alias} ON {' AND '.join(conditions)}"


@dataclass
class XDBQueryDefinition:
    """Complete definition of an XDB query"""

    sources: Dict[str, DataSource] = field(default_factory=dict)  # alias -> DataSource
    joins: List[JoinConfig] = field(default_factory=list)
    output_columns: List[str] = field(default_factory=list)  # List of "alias.column" names

    def add_source(self, source: DataSource):
        """Add a data source to the query"""
        self.sources[source.alias] = source

    def add_join(self, join_config: JoinConfig):
        """Add a join configuration"""
        self.joins.append(join_config)

    def set_output_columns(self, columns: List[str]):
        """Set which columns to include in the final output"""
        self.output_columns = columns

    def get_source_for_column(self, column_name: str) -> Optional[DataSource]:
        """
        Find the source that owns a given column.

        Args:
            column_name: Column name (with or without alias prefix)

        Returns:
            DataSource that contains this column, or None
        """
        # If column has alias prefix (e.g., "src1.CustomerID"), use that
        if '.' in column_name:
            alias = column_name.split('.')[0]
            return self.sources.get(alias)

        # Otherwise search all sources for this column name
        for alias, source in self.sources.items():
            for col in source.get_columns():
                if col.name == column_name:
                    return source

        return None

    def auto_assign_filter(self, filter_criteria: FilterCriteria) -> bool:
        """
        Automatically assign a filter to the correct source based on the column name.

        Args:
            filter_criteria: Filter to assign

        Returns:
            True if filter was assigned, False if no matching source found
        """
        # If column has alias prefix, use that directly
        if '.' in filter_criteria.column:
            alias, col_name = filter_criteria.column.split('.', 1)
            if alias in self.sources:
                # Create a new filter with just the column name (no alias prefix)
                source_filter = FilterCriteria(
                    column=col_name,
                    operator=filter_criteria.operator,
                    value=filter_criteria.value,
                    data_type=filter_criteria.data_type
                )
                self.sources[alias].add_filter(source_filter)
                logger.info(f"Assigned filter on {filter_criteria.column} to source {alias}")
                return True

        # Otherwise search all sources
        for alias, source in self.sources.items():
            for col in source.get_columns():
                if col.name == filter_criteria.column:
                    source.add_filter(filter_criteria)
                    logger.info(f"Assigned filter on {filter_criteria.column} to source {alias}")
                    return True

        logger.warning(f"Could not find source for filter column: {filter_criteria.column}")
        return False


class XDBQueryExecutor:
    """Executes cross-database queries with filter pushdown and join processing"""

    def __init__(self):
        self.last_execution_time_ms = 0
        self.last_record_count = 0
        self.last_source_stats: Dict[str, Dict[str, Any]] = {}

    def execute(
        self,
        query_def: XDBQueryDefinition,
        limit: Optional[int] = None
    ) -> pd.DataFrame:
        """
        Execute an XDB query and return results.

        Args:
            query_def: XDBQueryDefinition with sources, joins, and output columns
            limit: Optional row limit for the final result

        Returns:
            pandas DataFrame with the query results

        Raises:
            Exception: If any source fails to fetch (fail-fast behavior)
        """
        start_time = time.time()
        self.last_source_stats = {}

        if not query_def.sources:
            raise ValueError("XDB query has no data sources")

        try:
            # Step 1: Fetch data from all sources (with filter pushdown)
            source_dataframes = self._fetch_all_sources(query_def)

            # Step 2: Perform joins
            if len(source_dataframes) == 1:
                # Single source, no joins needed
                result_df = list(source_dataframes.values())[0]
            elif query_def.joins:
                # Perform explicit joins
                result_df = self._perform_joins(source_dataframes, query_def.joins)
            else:
                # Multiple sources but no joins defined - do cross join (Cartesian product)
                # This is usually not what users want, so warn them
                logger.warning("Multiple sources without joins - performing cross join")
                result_df = self._cross_join_all(source_dataframes)

            # Step 3: Select output columns
            if query_def.output_columns:
                available_cols = [c for c in query_def.output_columns if c in result_df.columns]
                if available_cols:
                    result_df = result_df[available_cols]
                else:
                    logger.warning(f"No output columns matched. Available: {list(result_df.columns)}")

            # Step 4: Apply limit
            if limit and len(result_df) > limit:
                result_df = result_df.head(limit)

            # Update stats
            self.last_execution_time_ms = int((time.time() - start_time) * 1000)
            self.last_record_count = len(result_df)

            logger.info(
                f"XDB query complete: {self.last_record_count} rows "
                f"in {self.last_execution_time_ms}ms"
            )

            return result_df

        except Exception as e:
            logger.error(f"XDB query execution failed: {e}")
            raise

    def _fetch_all_sources(
        self,
        query_def: XDBQueryDefinition
    ) -> Dict[str, pd.DataFrame]:
        """
        Fetch data from all sources with filter pushdown.

        This is a fail-fast operation - if any source fails, the entire
        query is aborted.

        Args:
            query_def: Query definition with sources

        Returns:
            Dictionary mapping source alias to DataFrame
        """
        results = {}

        for alias, source in query_def.sources.items():
            source_start = time.time()

            logger.info(f"Fetching source '{alias}' ({source.source_type}): {source.display_name}")

            try:
                df = source.fetch_data()

                source_time_ms = int((time.time() - source_start) * 1000)

                self.last_source_stats[alias] = {
                    'type': source.source_type,
                    'display_name': source.display_name,
                    'row_count': len(df),
                    'column_count': len(df.columns),
                    'execution_time_ms': source_time_ms,
                    'filter_pushdown': source.supports_filter_pushdown,
                    'filters_applied': len(source.filters)
                }

                logger.info(
                    f"  Source '{alias}': {len(df)} rows in {source_time_ms}ms "
                    f"({len(source.filters)} filters applied)"
                )

                results[alias] = df

            except Exception as e:
                logger.error(f"Source '{alias}' failed: {e}")
                raise RuntimeError(f"Failed to fetch source '{alias}': {e}") from e

        return results

    def _perform_joins(
        self,
        dataframes: Dict[str, pd.DataFrame],
        joins: List[JoinConfig]
    ) -> pd.DataFrame:
        """
        Perform joins between DataFrames.

        Uses DuckDB if available for better performance, otherwise falls back
        to Pandas merge operations.

        Args:
            dataframes: Dictionary mapping source alias to DataFrame
            joins: List of join configurations

        Returns:
            Joined DataFrame
        """
        if HAS_DUCKDB:
            return self._join_with_duckdb(dataframes, joins)
        else:
            return self._join_with_pandas(dataframes, joins)

    def _join_with_duckdb(
        self,
        dataframes: Dict[str, pd.DataFrame],
        joins: List[JoinConfig]
    ) -> pd.DataFrame:
        """Perform joins using DuckDB for better performance on large datasets"""
        try:
            # Create DuckDB connection
            conn = duckdb.connect(':memory:')

            # Register all DataFrames as tables
            for alias, df in dataframes.items():
                conn.register(alias, df)

            # Build SQL query
            # Start with the first source (find it from the first join's left side)
            first_alias = joins[0].left_source_alias if joins else list(dataframes.keys())[0]
            sql_parts = [f"SELECT * FROM {first_alias}"]

            # Add joins
            for join in joins:
                sql_parts.append(join.to_sql())

            sql = '\n'.join(sql_parts)
            logger.info(f"DuckDB join SQL:\n{sql}")

            # Execute and return
            result = conn.execute(sql).fetchdf()
            conn.close()

            return result

        except Exception as e:
            logger.warning(f"DuckDB join failed, falling back to Pandas: {e}")
            return self._join_with_pandas(dataframes, joins)

    def _join_with_pandas(
        self,
        dataframes: Dict[str, pd.DataFrame],
        joins: List[JoinConfig]
    ) -> pd.DataFrame:
        """Perform joins using Pandas merge operations"""
        if not joins:
            # No joins, return first (and only) DataFrame
            return list(dataframes.values())[0]

        # Start with the left side of the first join
        result = dataframes[joins[0].left_source_alias].copy()

        for join in joins:
            right_df = dataframes[join.right_source_alias]

            # Map join type to Pandas how parameter
            how_map = {
                'INNER': 'inner',
                'LEFT': 'left',
                'RIGHT': 'right',
                'FULL': 'outer',
            }
            how = how_map.get(join.join_type.upper(), 'inner')

            # Extract column names for merge (strip alias prefixes for matching)
            left_on = []
            right_on = []

            for left_col, op, right_col in join.on_conditions:
                if op != '=':
                    logger.warning(f"Pandas merge only supports '=' operator, ignoring condition with '{op}'")
                    continue
                left_on.append(left_col)
                right_on.append(right_col)

            if not left_on:
                logger.error("No valid join conditions found")
                continue

            logger.info(f"Pandas merge: {join.join_type} on {left_on} = {right_on}")

            result = result.merge(
                right_df,
                how=how,
                left_on=left_on,
                right_on=right_on,
                suffixes=('', '_dup')  # Handle column name collisions
            )

            # Drop duplicate columns created by the merge
            dup_cols = [c for c in result.columns if c.endswith('_dup')]
            if dup_cols:
                result = result.drop(columns=dup_cols)

        return result

    def _cross_join_all(self, dataframes: Dict[str, pd.DataFrame]) -> pd.DataFrame:
        """
        Perform cross join (Cartesian product) of all DataFrames.

        Warning: This can produce very large results!
        """
        dfs = list(dataframes.values())

        if len(dfs) == 1:
            return dfs[0]

        result = dfs[0]
        for df in dfs[1:]:
            # Create a temporary key for cross join
            result['_xjoin'] = 1
            df = df.copy()
            df['_xjoin'] = 1
            result = result.merge(df, on='_xjoin', suffixes=('', '_dup'))
            result = result.drop('_xjoin', axis=1)

            # Drop duplicate columns
            dup_cols = [c for c in result.columns if c.endswith('_dup')]
            if dup_cols:
                result = result.drop(columns=dup_cols)

        return result

    def get_execution_stats(self) -> Dict[str, Any]:
        """Get statistics from the last query execution"""
        return {
            'total_execution_time_ms': self.last_execution_time_ms,
            'total_record_count': self.last_record_count,
            'sources': self.last_source_stats
        }


def execute_xdb_query(
    sources: List[DataSource],
    joins: Optional[List[JoinConfig]] = None,
    filters: Optional[List[FilterCriteria]] = None,
    output_columns: Optional[List[str]] = None,
    limit: Optional[int] = None
) -> Tuple[pd.DataFrame, Dict[str, Any]]:
    """
    Convenience function to execute an XDB query.

    Args:
        sources: List of data sources to query
        joins: Optional list of join configurations
        filters: Optional list of filters to auto-assign to sources
        output_columns: Optional list of columns to include in output
        limit: Optional row limit

    Returns:
        Tuple of (result DataFrame, execution stats dict)
    """
    # Build query definition
    query_def = XDBQueryDefinition()

    for source in sources:
        query_def.add_source(source)

    if joins:
        for join in joins:
            query_def.add_join(join)

    if filters:
        for f in filters:
            query_def.auto_assign_filter(f)

    if output_columns:
        query_def.set_output_columns(output_columns)

    # Execute
    executor = XDBQueryExecutor()
    result = executor.execute(query_def, limit=limit)

    return result, executor.get_execution_stats()
