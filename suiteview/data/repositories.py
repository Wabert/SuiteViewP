"""Data repositories for database access"""

import json
import logging
from datetime import datetime
from typing import List, Dict, Optional, Any
from suiteview.data.database import get_database

logger = logging.getLogger(__name__)


class ConnectionRepository:
    """Repository for managing database connections"""

    def __init__(self):
        self.db = get_database()

    def create_connection(self, connection_name: str, connection_type: str,
                         server_name: str = None, database_name: str = None,
                         auth_type: str = None, encrypted_username: bytes = None,
                         encrypted_password: bytes = None,
                         connection_string: str = None) -> int:
        """
        Create a new connection

        Returns:
            connection_id of the newly created connection
        """
        cursor = self.db.execute("""
            INSERT INTO connections (
                connection_name, connection_type, server_name, database_name,
                auth_type, encrypted_username, encrypted_password, connection_string,
                is_active
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 1)
        """, (connection_name, connection_type, server_name, database_name,
              auth_type, encrypted_username, encrypted_password, connection_string))

        connection_id = cursor.lastrowid
        logger.info(f"Created connection: {connection_name} (ID: {connection_id})")
        return connection_id

    def get_all_connections(self) -> List[Dict]:
        """Get all connections"""
        rows = self.db.fetchall("""
            SELECT connection_id, connection_name, connection_type, server_name,
                   database_name, auth_type, encrypted_username, encrypted_password,
                   connection_string, created_at, last_tested, is_active
            FROM connections
            WHERE is_active = 1
            ORDER BY connection_name
        """)

        connections = []
        for row in rows:
            connections.append({
                'connection_id': row[0],
                'connection_name': row[1],
                'connection_type': row[2],
                'server_name': row[3],
                'database_name': row[4],
                'auth_type': row[5],
                'encrypted_username': row[6],
                'encrypted_password': row[7],
                'connection_string': row[8],
                'created_at': row[9],
                'last_tested': row[10],
                'is_active': row[11]
            })

        return connections

    def get_connection(self, connection_id: int) -> Optional[Dict]:
        """Get a single connection by ID"""
        row = self.db.fetchone("""
            SELECT connection_id, connection_name, connection_type, server_name,
                   database_name, auth_type, encrypted_username, encrypted_password,
                   connection_string, created_at, last_tested, is_active
            FROM connections
            WHERE connection_id = ?
        """, (connection_id,))

        if not row:
            return None

        return {
            'connection_id': row[0],
            'connection_name': row[1],
            'connection_type': row[2],
            'server_name': row[3],
            'database_name': row[4],
            'auth_type': row[5],
            'encrypted_username': row[6],
            'encrypted_password': row[7],
            'connection_string': row[8],
            'created_at': row[9],
            'last_tested': row[10],
            'is_active': row[11]
        }

    def update_connection(self, connection_id: int, **kwargs) -> bool:
        """Update a connection's details"""
        # Build dynamic UPDATE query based on provided kwargs
        fields = []
        values = []

        for key, value in kwargs.items():
            if key in ['connection_name', 'connection_type', 'server_name', 'database_name',
                      'auth_type', 'encrypted_username', 'encrypted_password', 'connection_string']:
                fields.append(f"{key} = ?")
                values.append(value)

        if not fields:
            return False

        values.append(connection_id)
        query = f"UPDATE connections SET {', '.join(fields)} WHERE connection_id = ?"

        self.db.execute(query, tuple(values))
        logger.info(f"Updated connection ID: {connection_id}")
        return True

    def delete_connection(self, connection_id: int) -> bool:
        """
        Delete a connection (hard delete to avoid UNIQUE constraint issues)
        All related records (saved_tables, etc.) will be cascade deleted
        """
        self.db.execute("""
            DELETE FROM connections WHERE connection_id = ?
        """, (connection_id,))

        logger.info(f"Deleted connection ID: {connection_id}")
        return True

    def update_last_tested(self, connection_id: int):
        """Update the last_tested timestamp"""
        self.db.execute("""
            UPDATE connections SET last_tested = CURRENT_TIMESTAMP WHERE connection_id = ?
        """, (connection_id,))


class SavedTableRepository:
    """Repository for managing saved tables (My Data)"""

    def __init__(self):
        self.db = get_database()

    def save_table(self, connection_id: int, table_name: str, schema_name: str = None) -> int:
        """Save a table to My Data"""
        # Check if already saved
        existing = self.db.fetchone("""
            SELECT saved_table_id FROM saved_tables
            WHERE connection_id = ? AND table_name = ? AND
                  (schema_name = ? OR (schema_name IS NULL AND ? IS NULL))
        """, (connection_id, table_name, schema_name, schema_name))

        if existing:
            logger.debug(f"Table {table_name} already saved")
            return existing[0]

        cursor = self.db.execute("""
            INSERT INTO saved_tables (connection_id, schema_name, table_name)
            VALUES (?, ?, ?)
        """, (connection_id, schema_name, table_name))

        saved_table_id = cursor.lastrowid
        logger.info(f"Saved table: {table_name} (ID: {saved_table_id})")
        return saved_table_id

    def remove_table(self, connection_id: int, table_name: str, schema_name: str = None) -> bool:
        """Remove a table from My Data"""
        self.db.execute("""
            DELETE FROM saved_tables
            WHERE connection_id = ? AND table_name = ? AND
                  (schema_name = ? OR (schema_name IS NULL AND ? IS NULL))
        """, (connection_id, table_name, schema_name, schema_name))

        logger.info(f"Removed table: {table_name}")
        return True

    def get_saved_tables(self, connection_id: int = None) -> List[Dict]:
        """Get all saved tables, optionally filtered by connection"""
        if connection_id:
            rows = self.db.fetchall("""
                SELECT st.saved_table_id, st.connection_id, st.schema_name, st.table_name,
                       st.saved_at, c.connection_name
                FROM saved_tables st
                JOIN connections c ON st.connection_id = c.connection_id
                WHERE st.connection_id = ?
                ORDER BY st.table_name
            """, (connection_id,))
        else:
            rows = self.db.fetchall("""
                SELECT st.saved_table_id, st.connection_id, st.schema_name, st.table_name,
                       st.saved_at, c.connection_name
                FROM saved_tables st
                JOIN connections c ON st.connection_id = c.connection_id
                ORDER BY c.connection_name, st.table_name
            """)

        tables = []
        for row in rows:
            tables.append({
                'saved_table_id': row[0],
                'connection_id': row[1],
                'schema_name': row[2],
                'table_name': row[3],
                'saved_at': row[4],
                'connection_name': row[5]
            })

        return tables

    def get_all_saved_tables(self) -> List[Dict]:
        """Get all saved tables across all connections"""
        return self.get_saved_tables(connection_id=None)

    def delete_saved_table(self, connection_id: int, table_name: str, schema_name: str = None) -> bool:
        """Delete a saved table (alias for remove_table)"""
        return self.remove_table(connection_id, table_name, schema_name)

    def is_table_saved(self, connection_id: int, table_name: str, schema_name: str = None) -> bool:
        """Check if a table is already saved"""
        row = self.db.fetchone("""
            SELECT saved_table_id FROM saved_tables
            WHERE connection_id = ? AND table_name = ? AND
                  (schema_name = ? OR (schema_name IS NULL AND ? IS NULL))
        """, (connection_id, table_name, schema_name, schema_name))

        return row is not None


class MetadataCacheRepository:
    """Repository for managing table metadata and unique values cache"""

    def __init__(self):
        self.db = get_database()

    def get_or_create_metadata(self, connection_id: int, table_name: str, 
                               schema_name: str = None) -> int:
        """Get existing metadata_id or create new entry"""
        # Check if metadata already exists
        existing = self.db.fetchone("""
            SELECT metadata_id FROM table_metadata
            WHERE connection_id = ? AND table_name = ? AND
                  (schema_name = ? OR (schema_name IS NULL AND ? IS NULL))
        """, (connection_id, table_name, schema_name, schema_name))

        if existing:
            return existing[0]

        # Create new metadata entry
        cursor = self.db.execute("""
            INSERT INTO table_metadata (connection_id, schema_name, table_name)
            VALUES (?, ?, ?)
        """, (connection_id, schema_name, table_name))

        metadata_id = cursor.lastrowid
        logger.debug(f"Created metadata entry for {table_name} (ID: {metadata_id})")
        return metadata_id

    def cache_column_metadata(self, metadata_id: int, columns: List[Dict]):
        """Cache column metadata for a table"""
        # Delete existing columns for this table
        self.db.execute("""
            DELETE FROM column_metadata WHERE metadata_id = ?
        """, (metadata_id,))

        # Insert new column data
        for col in columns:
            self.db.execute("""
                INSERT INTO column_metadata (
                    metadata_id, column_name, data_type, is_nullable, 
                    is_primary_key, max_length
                )
                VALUES (?, ?, ?, ?, ?, ?)
            """, (
                metadata_id,
                col.get('name'),
                col.get('type'),
                col.get('nullable', False),
                col.get('primary_key', False),
                col.get('max_length')
            ))

        # Update table_metadata cached_at timestamp
        self.db.execute("""
            UPDATE table_metadata SET cached_at = CURRENT_TIMESTAMP
            WHERE metadata_id = ?
        """, (metadata_id,))

        logger.info(f"Cached {len(columns)} columns for metadata_id {metadata_id}")

    def get_cached_columns(self, metadata_id: int) -> Optional[List[Dict]]:
        """Get cached column metadata"""
        rows = self.db.fetchall("""
            SELECT column_name, data_type, is_nullable, is_primary_key, max_length
            FROM column_metadata
            WHERE metadata_id = ?
            ORDER BY column_id
        """, (metadata_id,))

        if not rows:
            return None

        columns = []
        for row in rows:
            columns.append({
                'name': row[0],
                'type': row[1],
                'nullable': bool(row[2]),
                'primary_key': bool(row[3]),
                'max_length': row[4]
            })

        return columns

    def cache_unique_values(self, metadata_id: int, column_name: str, 
                           unique_values: List[Any]):
        """Cache unique values for a specific column"""
        # Delete existing cache for this column
        self.db.execute("""
            DELETE FROM unique_values_cache 
            WHERE metadata_id = ? AND column_name = ?
        """, (metadata_id, column_name))

        # Convert unique values to JSON
        values_json = json.dumps(unique_values)
        value_count = len(unique_values)

        # Insert new cache entry
        self.db.execute("""
            INSERT INTO unique_values_cache (
                metadata_id, column_name, unique_values, value_count
            )
            VALUES (?, ?, ?, ?)
        """, (metadata_id, column_name, values_json, value_count))

        logger.info(f"Cached {value_count} unique values for column {column_name}")

    def get_cached_unique_values(self, metadata_id: int, 
                                 column_name: str) -> Optional[Dict]:
        """Get cached unique values for a column"""
        row = self.db.fetchone("""
            SELECT unique_values, value_count, cached_at
            FROM unique_values_cache
            WHERE metadata_id = ? AND column_name = ?
        """, (metadata_id, column_name))

        if not row:
            return None

        return {
            'unique_values': json.loads(row[0]),
            'value_count': row[1],
            'cached_at': row[2]
        }

    def get_metadata_id(self, connection_id: int, table_name: str, 
                       schema_name: str = None) -> Optional[int]:
        """Get metadata_id for a specific table"""
        row = self.db.fetchone("""
            SELECT metadata_id FROM table_metadata
            WHERE connection_id = ? AND table_name = ? AND
                  (schema_name = ? OR (schema_name IS NULL AND ? IS NULL))
        """, (connection_id, table_name, schema_name, schema_name))

        return row[0] if row else None

    def get_metadata_cached_at(self, metadata_id: int) -> Optional[str]:
        """Get the cached_at timestamp for metadata"""
        row = self.db.fetchone("""
            SELECT cached_at FROM table_metadata WHERE metadata_id = ?
        """, (metadata_id,))

        return row[0] if row else None

    def clear_column_cache(self, metadata_id: int):
        """Clear cached column metadata"""
        self.db.execute("""
            DELETE FROM column_metadata WHERE metadata_id = ?
        """, (metadata_id,))

        self.db.execute("""
            DELETE FROM unique_values_cache WHERE metadata_id = ?
        """, (metadata_id,))

        logger.info(f"Cleared cache for metadata_id {metadata_id}")


# Singleton instances
_connection_repo: Optional[ConnectionRepository] = None
_saved_table_repo: Optional[SavedTableRepository] = None
_metadata_cache_repo: Optional[MetadataCacheRepository] = None


def get_connection_repository() -> ConnectionRepository:
    """Get or create singleton connection repository"""
    global _connection_repo
    if _connection_repo is None:
        _connection_repo = ConnectionRepository()
    return _connection_repo


def get_saved_table_repository() -> SavedTableRepository:
    """Get or create singleton saved table repository"""
    global _saved_table_repo
    if _saved_table_repo is None:
        _saved_table_repo = SavedTableRepository()
    return _saved_table_repo


def get_metadata_cache_repository() -> MetadataCacheRepository:
    """Get or create singleton metadata cache repository"""
    global _metadata_cache_repo
    if _metadata_cache_repo is None:
        _metadata_cache_repo = MetadataCacheRepository()
    return _metadata_cache_repo


class QueryRepository:
    """Repository for managing saved queries"""

    def __init__(self):
        self.db = get_database()

    def save_query(self, query_name: str, query_type: str, query_definition: dict,
                   category: str = None) -> int:
        """
        Save a query definition
        
        Args:
            query_name: Name for the query
            query_type: 'DB' or 'XDB'
            query_definition: Query definition as dict
            category: Optional category for organization
            
        Returns:
            query_id of the saved query
        """
        query_json = json.dumps(query_definition)
        
        # Check if query name already exists
        existing = self.db.fetchone("""
            SELECT query_id FROM saved_queries WHERE query_name = ?
        """, (query_name,))
        
        if existing:
            # Update existing query
            self.db.execute("""
                UPDATE saved_queries
                SET query_definition = ?,
                    query_type = ?,
                    category = ?,
                    last_modified = CURRENT_TIMESTAMP
                WHERE query_name = ?
            """, (query_json, query_type, category, query_name))
            query_id = existing['query_id']
            logger.info(f"Updated query: {query_name} (ID: {query_id})")
        else:
            # Insert new query
            cursor = self.db.execute("""
                INSERT INTO saved_queries (
                    query_name, query_type, category, query_definition
                ) VALUES (?, ?, ?, ?)
            """, (query_name, query_type, category, query_json))
            query_id = cursor.lastrowid
            logger.info(f"Saved new query: {query_name} (ID: {query_id})")
        
        return query_id

    def get_all_queries(self, query_type: str = None) -> List[Dict]:
        """
        Get all saved queries
        
        Args:
            query_type: Optional filter by 'DB' or 'XDB'
            
        Returns:
            List of query dictionaries
        """
        if query_type:
            rows = self.db.fetchall("""
                SELECT query_id, query_name, query_type, category,
                       query_definition, created_at, last_modified,
                       last_executed, execution_duration_ms, record_count
                FROM saved_queries
                WHERE query_type = ?
                ORDER BY query_name
            """, (query_type,))
        else:
            rows = self.db.fetchall("""
                SELECT query_id, query_name, query_type, category,
                       query_definition, created_at, last_modified,
                       last_executed, execution_duration_ms, record_count
                FROM saved_queries
                ORDER BY query_name
            """)
        
        queries = []
        for row in rows:
            query = dict(row)
            # Parse JSON definition
            query['query_definition'] = json.loads(query['query_definition'])
            queries.append(query)
        
        return queries

    def get_query(self, query_id: int) -> Optional[Dict]:
        """Get a specific query by ID"""
        row = self.db.fetchone("""
            SELECT query_id, query_name, query_type, category,
                   query_definition, created_at, last_modified,
                   last_executed, execution_duration_ms, record_count
            FROM saved_queries
            WHERE query_id = ?
        """, (query_id,))
        
        if row:
            query = dict(row)
            query['query_definition'] = json.loads(query['query_definition'])
            return query
        return None

    def delete_query(self, query_id: int):
        """Delete a saved query"""
        self.db.execute("""
            DELETE FROM saved_queries WHERE query_id = ?
        """, (query_id,))
        logger.info(f"Deleted query ID: {query_id}")

    def update_execution_stats(self, query_id: int, duration_ms: int, record_count: int):
        """Update query execution statistics"""
        self.db.execute("""
            UPDATE saved_queries
            SET last_executed = CURRENT_TIMESTAMP,
                execution_duration_ms = ?,
                record_count = ?
            WHERE query_id = ?
        """, (duration_ms, record_count, query_id))


# Singleton instances
_query_repo: Optional[QueryRepository] = None


def get_query_repository() -> QueryRepository:
    """Get or create singleton query repository"""
    global _query_repo
    if _query_repo is None:
        _query_repo = QueryRepository()
    return _query_repo
