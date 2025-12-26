"""Cross-Database Query Executor - Joins data from multiple database sources

This module provides the XDBQueryExecutor class which orchestrates cross-database
queries using the XDBEngine for hybrid execution (filter pushdown + DuckDB joins).
"""

import logging
import re
from typing import Dict, List, Any, Optional, Tuple
import pandas as pd
from pathlib import Path

from suiteview.core.xdb_engine import XDBEngine, SourceConfig, JoinConfig, get_xdb_engine

logger = logging.getLogger(__name__)


def sanitize_alias(alias: str) -> str:
    """
    Sanitize an alias to be safe for SQL identifiers.
    Removes special characters that could break SQL parsing.
    """
    if not alias:
        return 'datasource'
    # Replace non-alphanumeric characters with underscores
    sanitized = re.sub(r'[^a-zA-Z0-9]', '_', alias)
    # Remove consecutive underscores
    sanitized = re.sub(r'_+', '_', sanitized)
    # Remove leading/trailing underscores
    sanitized = sanitized.strip('_')
    # Ensure doesn't start with a digit
    if sanitized and sanitized[0].isdigit():
        sanitized = 'ds_' + sanitized
    return sanitized if sanitized else 'datasource'


class XDBQueryExecutor:
    """
    Execute cross-database queries using the hybrid XDB Engine.
    
    Strategy:
    1. Push filters and column projections to source databases
    2. Fetch filtered data from each source
    3. Use DuckDB for in-memory joins
    4. Apply aggregations and final processing
    """
    
    def __init__(self, use_duckdb: bool = True):
        """
        Initialize XDB executor
        
        Args:
            use_duckdb: Use DuckDB for joins (recommended)
        """
        self.use_duckdb = use_duckdb
        self.engine = get_xdb_engine()
        self.last_execution_plan = None
    
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
            # Build alias mapping (original -> sanitized)
            alias_map = {}
            for sc in source_configs:
                original_alias = sc.get('alias', f"s{len(alias_map)}")
                sanitized = sanitize_alias(original_alias)
                # Ensure unique
                base = sanitized
                counter = 1
                while sanitized in alias_map.values():
                    sanitized = f"{base}_{counter}"
                    counter += 1
                alias_map[original_alias] = sanitized
            
            # Extract join columns needed for each datasource (by original alias)
            join_columns_needed = {}  # original_alias -> set of column names
            for jc in join_configs:
                for cond in jc.get('on_conditions', []):
                    left_alias = cond.get('left_datasource', cond.get('left_alias', ''))
                    right_alias = cond.get('right_datasource', cond.get('right_alias', ''))
                    left_field = cond.get('left_field', '')
                    right_field = cond.get('right_field', '')
                    
                    if left_alias and left_field:
                        if left_alias not in join_columns_needed:
                            join_columns_needed[left_alias] = set()
                        join_columns_needed[left_alias].add(left_field)
                    
                    if right_alias and right_field:
                        if right_alias not in join_columns_needed:
                            join_columns_needed[right_alias] = set()
                        join_columns_needed[right_alias].add(right_field)
            
            logger.info(f"Join columns needed by datasource: {join_columns_needed}")
            
            # Extract filter columns needed for each datasource
            filter_columns_needed = {}  # original_alias -> set of column names
            for sc in source_configs:
                original_alias = sc.get('alias', f"s{len(filter_columns_needed)}")
                for f in sc.get('filters', []):
                    col = f.get('column') or f.get('field_name')
                    if col:
                        if original_alias not in filter_columns_needed:
                            filter_columns_needed[original_alias] = set()
                        filter_columns_needed[original_alias].add(col)
            
            logger.info(f"Filter columns needed by datasource: {filter_columns_needed}")
            
            # Convert to SourceConfig objects
            sources = []
            for sc in source_configs:
                conn = sc['connection']
                original_alias = sc.get('alias', f"s{len(sources)}")
                
                # Get display columns
                columns = list(sc.get('columns', []))
                
                # Add join key columns if not already included
                if original_alias in join_columns_needed:
                    for jcol in join_columns_needed[original_alias]:
                        if jcol and jcol not in columns:
                            columns.append(jcol)
                            logger.info(f"Added join column '{jcol}' to datasource '{original_alias}'")
                
                # Add filter columns if not already included
                if original_alias in filter_columns_needed:
                    for fcol in filter_columns_needed[original_alias]:
                        if fcol and fcol not in columns:
                            columns.append(fcol)
                            logger.info(f"Added filter column '{fcol}' to datasource '{original_alias}'")
                
                source = SourceConfig(
                    alias=alias_map.get(original_alias, sanitize_alias(original_alias)),
                    connection_id=conn['connection_id'],
                    connection_type=conn.get('connection_type', 'SQL_SERVER'),
                    connection_name=conn.get('connection_name', ''),
                    table_name=sc.get('table_name', ''),
                    schema_name=sc.get('schema_name'),
                    columns=columns,
                    filters=sc.get('filters', []),
                    connection_string=conn.get('connection_string')
                )
                sources.append(source)
            
            # Convert to JoinConfig objects
            joins = []
            for jc in join_configs:
                # Handle both old and new join config formats
                on_conditions = jc.get('on_conditions', [])
                
                # Convert on_conditions to standard format with sanitized aliases
                converted_conditions = []
                for cond in on_conditions:
                    orig_left = cond.get('left_datasource', cond.get('left_alias', ''))
                    orig_right = cond.get('right_datasource', cond.get('right_alias', ''))
                    converted_conditions.append({
                        'left_alias': alias_map.get(orig_left, sanitize_alias(orig_left)),
                        'left_field': cond.get('left_field', ''),
                        'right_alias': alias_map.get(orig_right, sanitize_alias(orig_right)),
                        'right_field': cond.get('right_field', '')
                    })
                
                # Get right datasource info with sanitized alias
                right_ds = jc.get('right_datasource', {})
                orig_right_alias = right_ds.get('alias', '') if isinstance(right_ds, dict) else ''
                right_alias = alias_map.get(orig_right_alias, sanitize_alias(orig_right_alias))
                
                # Determine left alias - it should be different from right_alias
                # Look at all sources and pick the one that isn't the right side
                left_alias = None
                for src in sources:
                    if src.alias != right_alias:
                        left_alias = src.alias
                        break
                
                # Fallback to first source if no match found
                if not left_alias:
                    left_alias = sources[0].alias if sources else ''
                
                join = JoinConfig(
                    join_type=self._normalize_join_type(jc.get('join_type', 'INNER JOIN')),
                    left_alias=left_alias,
                    right_alias=right_alias,
                    on_conditions=converted_conditions
                )
                joins.append(join)
            
            # Determine final columns from source configs
            final_columns = []
            for sc in source_configs:
                cols = sc.get('columns', [])
                if cols and cols != ['*']:
                    final_columns.extend(cols)
            
            # Execute using engine
            result_df, plan = self.engine.execute(
                sources=sources,
                joins=joins,
                final_columns=final_columns if final_columns else None,
                limit=limit
            )
            
            # Store plan for inspection
            self.last_execution_plan = plan
            
            return result_df
            
        except Exception as e:
            logger.error(f"XDB query execution failed: {e}", exc_info=True)
            raise
    
    def _normalize_join_type(self, join_type: str) -> str:
        """Normalize join type string"""
        jt = join_type.upper().strip()
        
        # Map common variations
        if jt in ['INNER', 'INNER JOIN']:
            return 'INNER'
        elif jt in ['LEFT', 'LEFT JOIN', 'LEFT OUTER', 'LEFT OUTER JOIN']:
            return 'LEFT OUTER'
        elif jt in ['RIGHT', 'RIGHT JOIN', 'RIGHT OUTER', 'RIGHT OUTER JOIN']:
            return 'RIGHT OUTER'
        elif jt in ['FULL', 'FULL JOIN', 'FULL OUTER', 'FULL OUTER JOIN']:
            return 'FULL OUTER'
        else:
            return 'INNER'
    
    def execute_single_source_query(self, source: Dict, limit: Optional[int] = None) -> pd.DataFrame:
        """Execute a query on a single datasource (no joins)"""
        return self.execute_query([source], [], limit)
    
    def get_execution_plan_summary(self) -> str:
        """Get a human-readable summary of the last execution plan"""
        if not self.last_execution_plan:
            return "No execution plan available"
        
        plan = self.last_execution_plan
        lines = ["XDB Execution Plan:", "=" * 40]
        
        # Sources
        lines.append("\nSources:")
        for src in plan.sources:
            lines.append(f"  [{src.alias}] {src.connection_name}.{src.table_name}")
            lines.append(f"    -> {src.row_count} rows fetched in {src.fetch_time_ms}ms")
            if src.filters:
                lines.append(f"    -> {len(src.filters)} filter(s) pushed down")
        
        # Joins
        if plan.joins:
            lines.append("\nJoins:")
            for join in plan.joins:
                cond_str = ", ".join([
                    f"{c['left_alias']}.{c['left_field']} = {c['right_alias']}.{c['right_field']}"
                    for c in join.on_conditions
                ])
                lines.append(f"  {join.left_alias} {join.join_type} JOIN {join.right_alias}")
                lines.append(f"    ON {cond_str}")
        
        # Timing
        lines.append(f"\nTiming:")
        lines.append(f"  Total: {plan.total_time_ms}ms")
        if plan.duckdb_time_ms:
            lines.append(f"  DuckDB join: {plan.duckdb_time_ms}ms")
        
        return "\n".join(lines)
    
    def get_formatted_sql(self) -> str:
        """Get formatted SQL statements from the last execution"""
        if not self.last_execution_plan:
            return "No SQL statements available - no query has been executed."
        
        return self.engine.get_formatted_sql_statements(self.last_execution_plan)
    
    def export_to_parquet(self, df: pd.DataFrame, output_path: str):
        """Export result DataFrame to Parquet file"""
        df.to_parquet(output_path, index=False, engine='pyarrow')
        logger.info(f"Exported {len(df)} rows to {output_path}")
    
    def export_to_csv(self, df: pd.DataFrame, output_path: str):
        """Export result DataFrame to CSV file"""
        df.to_csv(output_path, index=False)
        logger.info(f"Exported {len(df)} rows to {output_path}")
