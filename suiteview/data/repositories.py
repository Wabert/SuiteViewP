"""Data repositories for database access"""

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


# Singleton instances
_connection_repo: Optional[ConnectionRepository] = None
_saved_table_repo: Optional[SavedTableRepository] = None


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
