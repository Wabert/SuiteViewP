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
            SELECT column_name, data_type, is_nullable, is_primary_key, is_common, max_length
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
                'is_common': bool(row[4]),
                'max_length': row[5]
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

        # Convert unique values to native Python types to handle numpy/pandas types
        def convert_to_native(val):
            """Convert numpy/pandas types to native Python types"""
            if val is None:
                return None
            # Handle pandas/numpy types
            if hasattr(val, 'item'):  # numpy scalar
                return val.item()
            if hasattr(val, 'to_pydatetime'):  # pandas Timestamp
                return val.to_pydatetime().isoformat()
            # Try to convert to native type
            try:
                if isinstance(val, (int, float, str, bool)):
                    return val
                return str(val)
            except:
                return str(val)
        
        # Convert all values to native types
        native_values = [convert_to_native(v) for v in unique_values]
        
        # Convert unique values to JSON
        values_json = json.dumps(native_values)
        value_count = len(native_values)

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

    def update_column_common_flag(self, metadata_id: int, column_name: str, is_common: bool):
        """Update the is_common flag for a specific column"""
        self.db.execute("""
            UPDATE column_metadata
            SET is_common = ?
            WHERE metadata_id = ? AND column_name = ?
        """, (is_common, metadata_id, column_name))
        
        logger.info(f"Updated common flag for {column_name} to {is_common}")

    def update_column_type(self, metadata_id: int, column_name: str, data_type: str):
        """Update the data type for a specific column (useful for CSV type overrides)"""
        self.db.execute("""
            UPDATE column_metadata
            SET data_type = ?
            WHERE metadata_id = ? AND column_name = ?
        """, (data_type, metadata_id, column_name))
        
        logger.info(f"Updated data type for {column_name} to {data_type}")


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
                   category: str = None, folder_id: int = None) -> int:
        """
        Save a query definition
        
        Args:
            query_name: Name for the query
            query_type: 'DB' or 'XDB'
            query_definition: Query definition as dict
            category: Optional category for organization
            folder_id: Optional folder to place query in
            
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
                    folder_id = ?,
                    last_modified = CURRENT_TIMESTAMP
                WHERE query_name = ?
            """, (query_json, query_type, category, folder_id, query_name))
            query_id = existing['query_id']
            logger.info(f"Updated query: {query_name} (ID: {query_id})")
        else:
            # Insert new query
            cursor = self.db.execute("""
                INSERT INTO saved_queries (
                    query_name, query_type, category, folder_id, query_definition
                ) VALUES (?, ?, ?, ?, ?)
            """, (query_name, query_type, category, folder_id, query_json))
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
                SELECT query_id, query_name, query_type, category, folder_id,
                       query_definition, created_at, last_modified,
                       last_executed, execution_duration_ms, record_count
                FROM saved_queries
                WHERE query_type = ?
                ORDER BY query_name
            """, (query_type,))
        else:
            rows = self.db.fetchall("""
                SELECT query_id, query_name, query_type, category, folder_id,
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
            SELECT query_id, query_name, query_type, category, folder_id,
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

    def update_query_name(self, query_id: int, new_name: str):
        """Update a query's name"""
        self.db.execute("""
            UPDATE saved_queries
            SET query_name = ?,
                last_modified = CURRENT_TIMESTAMP
            WHERE query_id = ?
        """, (new_name, query_id))
        logger.info(f"Updated query {query_id} name to: {new_name}")

    def update_execution_stats(self, query_id: int, duration_ms: int, record_count: int):
        """Update query execution statistics"""
        self.db.execute("""
            UPDATE saved_queries
            SET last_executed = CURRENT_TIMESTAMP,
                execution_duration_ms = ?,
                record_count = ?
            WHERE query_id = ?
        """, (duration_ms, record_count, query_id))

    def get_recent_queries(self, query_type: str = 'DB', limit: int = 10) -> List[Dict]:
        """Get recently executed queries ordered by last_executed timestamp

        Args:
            query_type: Type of queries to retrieve ('DB' or 'XDB')
            limit: Maximum number of queries to return (default 10)

        Returns:
            List of query dictionaries with execution metadata
        """
        rows = self.db.fetchall("""
            SELECT query_id, query_name, query_type, category, folder_id,
                   last_executed, execution_duration_ms, record_count
            FROM saved_queries
            WHERE query_type = ? AND last_executed IS NOT NULL
            ORDER BY last_executed DESC
            LIMIT ?
        """, (query_type, limit))

        return [dict(row) for row in rows]

    # Folder management methods
    def get_all_folders(self, query_type: str = None) -> List[Dict]:
        """Get all query folders"""
        if query_type:
            rows = self.db.fetchall("""
                SELECT folder_id, folder_name, query_type, parent_folder_id, display_order, created_at
                FROM query_folders
                WHERE query_type = ?
                ORDER BY display_order, folder_name
            """, (query_type,))
        else:
            rows = self.db.fetchall("""
                SELECT folder_id, folder_name, query_type, parent_folder_id, display_order, created_at
                FROM query_folders
                ORDER BY display_order, folder_name
            """)
        
        return [dict(row) for row in rows]
    
    def create_folder(self, folder_name: str, query_type: str, parent_folder_id: int = None) -> int:
        """Create a new query folder"""
        cursor = self.db.execute("""
            INSERT INTO query_folders (folder_name, query_type, parent_folder_id)
            VALUES (?, ?, ?)
        """, (folder_name, query_type, parent_folder_id))
        folder_id = cursor.lastrowid
        logger.info(f"Created folder: {folder_name} (ID: {folder_id})")
        return folder_id
    
    def delete_folder(self, folder_id: int):
        """Delete a folder and move its queries to General folder"""
        # Get the query type for this folder
        folder = self.db.fetchone("SELECT query_type FROM query_folders WHERE folder_id = ?", (folder_id,))
        if folder:
            # Get or create General folder
            general = self.db.fetchone("""
                SELECT folder_id FROM query_folders 
                WHERE folder_name = 'General' AND query_type = ?
            """, (folder['query_type'],))
            
            if general:
                # Move queries to General folder
                self.db.execute("""
                    UPDATE saved_queries SET folder_id = ? WHERE folder_id = ?
                """, (general['folder_id'], folder_id))
            
            # Delete the folder
            self.db.execute("DELETE FROM query_folders WHERE folder_id = ?", (folder_id,))
            logger.info(f"Deleted folder ID: {folder_id}")
    
    def rename_folder(self, folder_id: int, new_name: str):
        """Rename a folder"""
        self.db.execute("""
            UPDATE query_folders SET folder_name = ? WHERE folder_id = ?
        """, (new_name, folder_id))
        logger.info(f"Renamed folder {folder_id} to: {new_name}")
    
    def move_query_to_folder(self, query_id: int, folder_id: int):
        """Move a query to a different folder"""
        self.db.execute("""
            UPDATE saved_queries SET folder_id = ? WHERE query_id = ?
        """, (folder_id, query_id))
        logger.info(f"Moved query {query_id} to folder {folder_id}")
    
    def count_queries_in_folder(self, folder_id: int) -> int:
        """Count the number of queries in a specific folder"""
        result = self.db.fetchone("""
            SELECT COUNT(*) as count FROM saved_queries WHERE folder_id = ?
        """, (folder_id,))
        return result['count'] if result else 0
    
    def get_queries_in_folder(self, folder_id: int) -> List[Dict]:
        """Get all queries in a specific folder"""
        rows = self.db.fetchall("""
            SELECT query_id, query_name, query_type, category, folder_id,
                   query_definition, created_at, last_modified,
                   last_executed, execution_duration_ms, record_count
            FROM saved_queries
            WHERE folder_id = ?
            ORDER BY query_name
        """, (folder_id,))
        
        queries = []
        for row in rows:
            query = dict(row)
            query['query_definition'] = json.loads(query['query_definition'])
            queries.append(query)
        
        return queries


class DataMapRepository:
    """Repository for managing data mappings"""

    def __init__(self):
        self.db = get_database()

    # Folder operations
    def get_all_folders(self) -> List[Dict]:
        """Get all data map folders"""
        rows = self.db.fetchall("""
            SELECT folder_id, folder_name, parent_folder_id, created_at, display_order
            FROM data_map_folders
            ORDER BY display_order, folder_name
        """)
        return [dict(row) for row in rows]

    def create_folder(self, folder_name: str, parent_folder_id: int = None) -> int:
        """Create a new data map folder"""
        cursor = self.db.execute("""
            INSERT INTO data_map_folders (folder_name, parent_folder_id)
            VALUES (?, ?)
        """, (folder_name, parent_folder_id))
        folder_id = cursor.lastrowid
        logger.info(f"Created data map folder: {folder_name} (ID: {folder_id})")
        return folder_id

    def delete_folder(self, folder_id: int):
        """Delete a data map folder and move its maps to General folder"""
        # Get General folder
        general_folder = self.db.fetchone("""
            SELECT folder_id FROM data_map_folders WHERE folder_name = 'General'
        """)
        
        if general_folder:
            # Move all maps to General folder
            self.db.execute("""
                UPDATE data_maps SET folder_id = ? WHERE folder_id = ?
            """, (general_folder['folder_id'], folder_id))
        
        # Delete the folder
        self.db.execute("""
            DELETE FROM data_map_folders WHERE folder_id = ?
        """, (folder_id,))
        logger.info(f"Deleted data map folder {folder_id}")

    def rename_folder(self, folder_id: int, new_name: str):
        """Rename a data map folder"""
        self.db.execute("""
            UPDATE data_map_folders SET folder_name = ? WHERE folder_id = ?
        """, (new_name, folder_id))
        logger.info(f"Renamed data map folder {folder_id} to: {new_name}")

    def count_maps_in_folder(self, folder_id: int) -> int:
        """Count the number of data maps in a specific folder"""
        result = self.db.fetchone("""
            SELECT COUNT(*) as count FROM data_maps WHERE folder_id = ?
        """, (folder_id,))
        return result['count'] if result else 0

    # Data map operations
    def get_all_data_maps(self) -> List[Dict]:
        """Get all data maps"""
        rows = self.db.fetchall("""
            SELECT data_map_id, map_name, folder_id, key_data_type, value_data_type,
                   notes, created_at, last_modified
            FROM data_maps
            ORDER BY map_name
        """)
        return [dict(row) for row in rows]

    def get_data_map(self, data_map_id: int) -> Optional[Dict]:
        """Get a specific data map by ID"""
        row = self.db.fetchone("""
            SELECT data_map_id, map_name, folder_id, key_data_type, value_data_type,
                   notes, created_at, last_modified
            FROM data_maps
            WHERE data_map_id = ?
        """, (data_map_id,))
        return dict(row) if row else None

    def get_data_map_by_name(self, map_name: str) -> Optional[Dict]:
        """Get a specific data map by name"""
        row = self.db.fetchone("""
            SELECT data_map_id, map_name, folder_id, key_data_type, value_data_type,
                   notes, created_at, last_modified
            FROM data_maps
            WHERE map_name = ?
        """, (map_name,))
        return dict(row) if row else None

    def create_data_map(self, map_name: str, key_data_type: str = 'string',
                       value_data_type: str = 'string', notes: str = None,
                       folder_id: int = None) -> int:
        """Create a new data map"""
        cursor = self.db.execute("""
            INSERT INTO data_maps (map_name, folder_id, key_data_type, value_data_type, notes)
            VALUES (?, ?, ?, ?, ?)
        """, (map_name, folder_id, key_data_type, value_data_type, notes))
        data_map_id = cursor.lastrowid
        logger.info(f"Created data map: {map_name} (ID: {data_map_id})")
        return data_map_id

    def update_data_map(self, data_map_id: int, map_name: str = None,
                       key_data_type: str = None, value_data_type: str = None,
                       notes: str = None, folder_id: int = None):
        """Update a data map's metadata"""
        updates = []
        params = []
        
        if map_name is not None:
            updates.append("map_name = ?")
            params.append(map_name)
        if key_data_type is not None:
            updates.append("key_data_type = ?")
            params.append(key_data_type)
        if value_data_type is not None:
            updates.append("value_data_type = ?")
            params.append(value_data_type)
        if notes is not None:
            updates.append("notes = ?")
            params.append(notes)
        if folder_id is not None:
            updates.append("folder_id = ?")
            params.append(folder_id)
        
        updates.append("last_modified = CURRENT_TIMESTAMP")
        params.append(data_map_id)
        
        self.db.execute(f"""
            UPDATE data_maps SET {', '.join(updates)}
            WHERE data_map_id = ?
        """, tuple(params))
        logger.info(f"Updated data map {data_map_id}")

    def move_data_map_to_folder(self, data_map_id: int, folder_id: int):
        """Move a data map to a different folder"""
        self.db.execute("""
            UPDATE data_maps SET folder_id = ?, last_modified = CURRENT_TIMESTAMP
            WHERE data_map_id = ?
        """, (folder_id, data_map_id))
        logger.info(f"Moved data map {data_map_id} to folder {folder_id}")

    def delete_data_map(self, data_map_id: int):
        """Delete a data map and all its entries"""
        self.db.execute("""
            DELETE FROM data_maps WHERE data_map_id = ?
        """, (data_map_id,))
        logger.info(f"Deleted data map {data_map_id}")

    # Data map entry operations
    def get_map_entries(self, data_map_id: int) -> List[Dict]:
        """Get all entries for a data map"""
        rows = self.db.fetchall("""
            SELECT entry_id, data_map_id, key_value, mapped_value, comment,
                   created_at, last_updated
            FROM data_map_entries
            WHERE data_map_id = ?
            ORDER BY key_value
        """, (data_map_id,))
        return [dict(row) for row in rows]

    def add_map_entry(self, data_map_id: int, key_value: str,
                     mapped_value: str = None, comment: str = None) -> int:
        """Add a new entry to a data map"""
        cursor = self.db.execute("""
            INSERT INTO data_map_entries (data_map_id, key_value, mapped_value, comment)
            VALUES (?, ?, ?, ?)
        """, (data_map_id, key_value, mapped_value, comment))
        
        # Update data map's last_modified
        self.db.execute("""
            UPDATE data_maps SET last_modified = CURRENT_TIMESTAMP
            WHERE data_map_id = ?
        """, (data_map_id,))
        
        entry_id = cursor.lastrowid
        logger.info(f"Added entry to data map {data_map_id}: {key_value} -> {mapped_value}")
        return entry_id

    def update_map_entry(self, entry_id: int, key_value: str = None,
                        mapped_value: str = None, comment: str = None):
        """Update a data map entry"""
        updates = []
        params = []
        
        if key_value is not None:
            updates.append("key_value = ?")
            params.append(key_value)
        if mapped_value is not None:
            updates.append("mapped_value = ?")
            params.append(mapped_value)
        if comment is not None:
            updates.append("comment = ?")
            params.append(comment)
        
        updates.append("last_updated = CURRENT_TIMESTAMP")
        params.append(entry_id)
        
        self.db.execute(f"""
            UPDATE data_map_entries SET {', '.join(updates)}
            WHERE entry_id = ?
        """, tuple(params))
        
        # Also update the parent data map's last_modified
        self.db.execute("""
            UPDATE data_maps SET last_modified = CURRENT_TIMESTAMP
            WHERE data_map_id = (SELECT data_map_id FROM data_map_entries WHERE entry_id = ?)
        """, (entry_id,))
        
        logger.info(f"Updated data map entry {entry_id}")

    def delete_map_entry(self, entry_id: int):
        """Delete a data map entry"""
        # Get the data_map_id before deleting
        row = self.db.fetchone("""
            SELECT data_map_id FROM data_map_entries WHERE entry_id = ?
        """, (entry_id,))
        
        self.db.execute("""
            DELETE FROM data_map_entries WHERE entry_id = ?
        """, (entry_id,))
        
        # Update data map's last_modified
        if row:
            self.db.execute("""
                UPDATE data_maps SET last_modified = CURRENT_TIMESTAMP
                WHERE data_map_id = ?
            """, (row['data_map_id'],))
        
        logger.info(f"Deleted data map entry {entry_id}")

    def delete_map_entries(self, entry_ids: List[int]):
        """Delete multiple data map entries"""
        if not entry_ids:
            return
        
        placeholders = ','.join('?' * len(entry_ids))
        
        # Get affected data_map_ids
        rows = self.db.fetchall(f"""
            SELECT DISTINCT data_map_id FROM data_map_entries
            WHERE entry_id IN ({placeholders})
        """, tuple(entry_ids))
        
        # Delete entries
        self.db.execute(f"""
            DELETE FROM data_map_entries WHERE entry_id IN ({placeholders})
        """, tuple(entry_ids))
        
        # Update data maps' last_modified
        for row in rows:
            self.db.execute("""
                UPDATE data_maps SET last_modified = CURRENT_TIMESTAMP
                WHERE data_map_id = ?
            """, (row['data_map_id'],))
        
        logger.info(f"Deleted {len(entry_ids)} data map entries")

    # Field assignment operations
    def assign_data_map_to_field(self, connection_id: int, table_name: str,
                                 column_name: str, data_map_id: int,
                                 schema_name: str = None):
        """Assign a data map to a specific table field"""
        self.db.execute("""
            INSERT OR REPLACE INTO field_data_map_assignments
            (connection_id, schema_name, table_name, column_name, data_map_id)
            VALUES (?, ?, ?, ?, ?)
        """, (connection_id, schema_name, table_name, column_name, data_map_id))
        logger.info(f"Assigned data map {data_map_id} to {table_name}.{column_name}")

    def get_field_data_map(self, connection_id: int, table_name: str,
                          column_name: str, schema_name: str = None) -> Optional[int]:
        """Get the data map assigned to a specific field"""
        row = self.db.fetchone("""
            SELECT data_map_id FROM field_data_map_assignments
            WHERE connection_id = ? AND table_name = ? AND column_name = ?
            AND (schema_name = ? OR (schema_name IS NULL AND ? IS NULL))
        """, (connection_id, table_name, column_name, schema_name, schema_name))
        return row['data_map_id'] if row else None

    def remove_field_data_map(self, connection_id: int, table_name: str,
                             column_name: str, schema_name: str = None):
        """Remove data map assignment from a field"""
        self.db.execute("""
            DELETE FROM field_data_map_assignments
            WHERE connection_id = ? AND table_name = ? AND column_name = ?
            AND (schema_name = ? OR (schema_name IS NULL AND ? IS NULL))
        """, (connection_id, table_name, column_name, schema_name, schema_name))
        logger.info(f"Removed data map assignment from {table_name}.{column_name}")

    def get_all_field_assignments(self, connection_id: int, table_name: str,
                                  schema_name: str = None) -> List[Dict]:
        """Get all data map assignments for a table"""
        rows = self.db.fetchall("""
            SELECT assignment_id, connection_id, schema_name, table_name,
                   column_name, data_map_id, assigned_at
            FROM field_data_map_assignments
            WHERE connection_id = ? AND table_name = ?
            AND (schema_name = ? OR (schema_name IS NULL AND ? IS NULL))
        """, (connection_id, table_name, schema_name, schema_name))
        return [dict(row) for row in rows]


# Singleton instances
_query_repo: Optional[QueryRepository] = None
_data_map_repo: Optional[DataMapRepository] = None


def get_query_repository() -> QueryRepository:
    """Get or create singleton query repository"""
    global _query_repo
    if _query_repo is None:
        _query_repo = QueryRepository()
    return _query_repo


def get_data_map_repository() -> DataMapRepository:
    """Get or create singleton data map repository"""
    global _data_map_repo
    if _data_map_repo is None:
        _data_map_repo = DataMapRepository()
    return _data_map_repo

