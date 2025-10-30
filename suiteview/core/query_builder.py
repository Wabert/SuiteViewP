"""Query Builder - Constructs query definitions from UI state"""

import logging
from typing import Dict, List, Any, Optional, Tuple

logger = logging.getLogger(__name__)


class Query:
    """Represents a database query with all its components"""

    def __init__(self, query_type: str = 'DB'):
        """
        Initialize a new query
        
        Args:
            query_type: 'DB' for single-database or 'XDB' for cross-database
        """
        self.query_type = query_type
        self.connection_id = None
        self.database_name = None
        
        # Query components
        self.from_table = None
        self.from_schema = None
        self.display_fields = []  # List of {table, schema, field, data_type}
        self.criteria = []  # List of filter configurations
        self.joins = []  # List of join configurations
        
        # Metadata
        self.query_name = None
        self.query_id = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert query to dictionary for JSON serialization"""
        return {
            'query_type': self.query_type,
            'connection_id': self.connection_id,
            'database_name': self.database_name,
            'from_table': self.from_table,
            'from_schema': self.from_schema,
            'display_fields': self.display_fields,
            'criteria': self.criteria,
            'joins': self.joins
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'Query':
        """Create query from dictionary"""
        query = cls(data.get('query_type', 'DB'))
        query.connection_id = data.get('connection_id')
        query.database_name = data.get('database_name')
        query.from_table = data.get('from_table')
        query.from_schema = data.get('from_schema')
        query.display_fields = data.get('display_fields', [])
        query.criteria = data.get('criteria', [])
        query.joins = data.get('joins', [])
        return query


class QueryBuilder:
    """Builds query definitions from UI state"""

    def __init__(self):
        pass

    def create_query(self, query_type: str = 'DB') -> Query:
        """
        Create a new empty query
        
        Args:
            query_type: 'DB' for single-database or 'XDB' for cross-database
            
        Returns:
            New Query object
        """
        return Query(query_type)

    def set_connection(self, query: Query, connection_id: int, database_name: str):
        """
        Set the connection for the query
        
        Args:
            query: Query object to modify
            connection_id: Database connection ID
            database_name: Database name
        """
        query.connection_id = connection_id
        query.database_name = database_name

    def set_from_table(self, query: Query, table_name: str, schema_name: Optional[str] = None):
        """
        Set the FROM table
        
        Args:
            query: Query object to modify
            table_name: Table name
            schema_name: Schema name (optional)
        """
        query.from_table = table_name
        query.from_schema = schema_name

    def add_display_field(self, query: Query, field_config: Dict[str, Any]):
        """
        Add a field to the SELECT list
        
        Args:
            query: Query object to modify
            field_config: Dictionary with field information:
                - field_name: Column name
                - table_name: Table name
                - schema_name: Schema name (optional)
                - data_type: Data type
        """
        # Check if already added
        for existing in query.display_fields:
            if (existing['field_name'] == field_config['field_name'] and
                existing['table_name'] == field_config['table_name']):
                logger.warning(f"Field {field_config['field_name']} already in display list")
                return

        query.display_fields.append({
            'field_name': field_config['field_name'],
            'table_name': field_config['table_name'],
            'schema_name': field_config.get('schema_name', ''),
            'data_type': field_config['data_type']
        })

        logger.info(f"Added display field: {field_config['table_name']}.{field_config['field_name']}")

    def remove_display_field(self, query: Query, field_name: str, table_name: str):
        """
        Remove a field from the SELECT list
        
        Args:
            query: Query object to modify
            field_name: Column name
            table_name: Table name
        """
        query.display_fields = [
            f for f in query.display_fields
            if not (f['field_name'] == field_name and f['table_name'] == table_name)
        ]

    def add_criteria(self, query: Query, filter_config: Dict[str, Any]):
        """
        Add a filter criterion to the WHERE clause
        
        Args:
            query: Query object to modify
            filter_config: Dictionary with filter information:
                - field_name: Column name
                - table_name: Table name
                - schema_name: Schema name (optional)
                - data_type: Data type
                - operator: Comparison operator (=, >, <, LIKE, IN, etc.)
                - value: Filter value(s)
                - match_type: For strings (exact, starts_with, contains, etc.)
        """
        query.criteria.append({
            'field_name': filter_config['field_name'],
            'table_name': filter_config['table_name'],
            'schema_name': filter_config.get('schema_name', ''),
            'data_type': filter_config['data_type'],
            'operator': filter_config.get('operator', '='),
            'value': filter_config.get('value'),
            'match_type': filter_config.get('match_type', 'exact')
        })

        logger.info(f"Added criteria: {filter_config['table_name']}.{filter_config['field_name']}")

    def remove_criteria(self, query: Query, field_name: str, table_name: str):
        """
        Remove a filter criterion
        
        Args:
            query: Query object to modify
            field_name: Column name
            table_name: Table name
        """
        query.criteria = [
            c for c in query.criteria
            if not (c['field_name'] == field_name and c['table_name'] == table_name)
        ]

    def add_join(self, query: Query, join_config: Dict[str, Any]):
        """
        Add a JOIN configuration
        
        Args:
            query: Query object to modify
            join_config: Dictionary with join information:
                - join_type: INNER, LEFT, RIGHT, FULL
                - table_name: Table to join to
                - schema_name: Schema name (optional)
                - on_conditions: List of {left_field, operator, right_field} dicts
        """
        query.joins.append({
            'join_type': join_config['join_type'],
            'table_name': join_config['table_name'],
            'schema_name': join_config.get('schema_name', ''),
            'on_conditions': join_config.get('on_conditions', [])
        })

        logger.info(f"Added join: {join_config['join_type']} {join_config['table_name']}")

    def remove_join(self, query: Query, index: int):
        """
        Remove a JOIN configuration
        
        Args:
            query: Query object to modify
            index: Index of join to remove
        """
        if 0 <= index < len(query.joins):
            removed = query.joins.pop(index)
            logger.info(f"Removed join: {removed['join_type']} {removed['table_name']}")

    def validate_query(self, query: Query) -> Tuple[bool, str]:
        """
        Validate query structure
        
        Args:
            query: Query object to validate
            
        Returns:
            Tuple of (is_valid, error_message)
        """
        # Must have display fields
        if not query.display_fields:
            return False, "Query must have at least one display field"

        # Must have a connection
        if not query.connection_id:
            return False, "Query must have a database connection"

        # Must have a FROM table (use first table from display fields if not set)
        if not query.from_table:
            # Auto-set from first display field
            if query.display_fields:
                query.from_table = query.display_fields[0]['table_name']
                query.from_schema = query.display_fields[0]['schema_name']

        # Get all tables involved
        tables = set()
        
        for field in query.display_fields:
            tables.add(field['table_name'])
            
        for criterion in query.criteria:
            tables.add(criterion['table_name'])

        # If multiple tables, validate joins
        if len(tables) > 1:
            # Should have len(tables)-1 joins (assuming all tables are connected)
            if len(query.joins) < len(tables) - 1:
                return False, f"Query has {len(tables)} tables but only {len(query.joins)} joins. You may need more joins to connect all tables."

        # All validations passed
        return True, ""

    def get_tables_involved(self, query: Query) -> List[str]:
        """
        Get list of all tables involved in the query
        
        Args:
            query: Query object
            
        Returns:
            List of table names
        """
        tables = set()
        
        for field in query.display_fields:
            tables.add(field['table_name'])
            
        for criterion in query.criteria:
            tables.add(criterion['table_name'])
            
        for join in query.joins:
            tables.add(join['table_name'])

        return sorted(list(tables))
