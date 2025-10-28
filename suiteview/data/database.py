"""Database initialization and connection management for SQLite"""

import os
import sqlite3
from pathlib import Path
from typing import Optional


class Database:
    """Manages SQLite database connection and initialization"""

    def __init__(self, db_path: Optional[str] = None):
        """
        Initialize database connection

        Args:
            db_path: Path to SQLite database file. If None, uses default in user home
        """
        if db_path is None:
            # Use ~/.suiteview/suiteview.db as default (cross-platform)
            home = Path.home()
            app_dir = home / '.suiteview'
            app_dir.mkdir(exist_ok=True)
            self.db_path = str(app_dir / 'suiteview.db')
        else:
            self.db_path = db_path

        self.connection: Optional[sqlite3.Connection] = None

    def connect(self) -> sqlite3.Connection:
        """Connect to database and return connection"""
        if self.connection is None:
            self.connection = sqlite3.connect(self.db_path)
            self.connection.row_factory = sqlite3.Row  # Access columns by name
        return self.connection

    def close(self):
        """Close database connection"""
        if self.connection:
            self.connection.close()
            self.connection = None

    def initialize_schema(self):
        """Create all database tables if they don't exist"""
        conn = self.connect()
        cursor = conn.cursor()

        # Connections table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS connections (
                connection_id INTEGER PRIMARY KEY AUTOINCREMENT,
                connection_name TEXT NOT NULL UNIQUE,
                connection_type TEXT NOT NULL,
                server_name TEXT,
                database_name TEXT,
                auth_type TEXT,
                encrypted_username BLOB,
                encrypted_password BLOB,
                connection_string TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                last_tested TIMESTAMP,
                is_active BOOLEAN DEFAULT 1
            )
        """)

        # Saved tables (My Data selections)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS saved_tables (
                saved_table_id INTEGER PRIMARY KEY AUTOINCREMENT,
                connection_id INTEGER NOT NULL,
                schema_name TEXT,
                table_name TEXT NOT NULL,
                saved_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (connection_id) REFERENCES connections(connection_id) ON DELETE CASCADE
            )
        """)

        # Cached metadata
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS table_metadata (
                metadata_id INTEGER PRIMARY KEY AUTOINCREMENT,
                connection_id INTEGER NOT NULL,
                schema_name TEXT,
                table_name TEXT NOT NULL,
                row_count INTEGER,
                last_modified TIMESTAMP,
                cached_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (connection_id) REFERENCES connections(connection_id) ON DELETE CASCADE
            )
        """)

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS column_metadata (
                column_id INTEGER PRIMARY KEY AUTOINCREMENT,
                metadata_id INTEGER NOT NULL,
                column_name TEXT NOT NULL,
                data_type TEXT NOT NULL,
                is_nullable BOOLEAN,
                is_primary_key BOOLEAN,
                max_length INTEGER,
                FOREIGN KEY (metadata_id) REFERENCES table_metadata(metadata_id) ON DELETE CASCADE
            )
        """)

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS unique_values_cache (
                cache_id INTEGER PRIMARY KEY AUTOINCREMENT,
                metadata_id INTEGER NOT NULL,
                column_name TEXT NOT NULL,
                unique_values TEXT,
                value_count INTEGER,
                cached_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (metadata_id) REFERENCES table_metadata(metadata_id) ON DELETE CASCADE
            )
        """)

        # Saved queries
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS saved_queries (
                query_id INTEGER PRIMARY KEY AUTOINCREMENT,
                query_name TEXT NOT NULL,
                query_type TEXT NOT NULL,
                category TEXT,
                query_definition TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                last_modified TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                last_executed TIMESTAMP,
                execution_duration_ms INTEGER,
                record_count INTEGER
            )
        """)

        # User preferences
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS user_preferences (
                preference_key TEXT PRIMARY KEY,
                preference_value TEXT
            )
        """)

        conn.commit()
        print(f"Database initialized at: {self.db_path}")

    def execute(self, query: str, params: tuple = ()):
        """Execute a query and return cursor"""
        conn = self.connect()
        cursor = conn.cursor()
        cursor.execute(query, params)
        conn.commit()
        return cursor

    def fetchall(self, query: str, params: tuple = ()):
        """Execute query and fetch all results"""
        cursor = self.execute(query, params)
        return cursor.fetchall()

    def fetchone(self, query: str, params: tuple = ()):
        """Execute query and fetch one result"""
        cursor = self.execute(query, params)
        return cursor.fetchone()


# Singleton instance
_db_instance: Optional[Database] = None


def get_database() -> Database:
    """Get or create singleton database instance"""
    global _db_instance
    if _db_instance is None:
        _db_instance = Database()
        _db_instance.initialize_schema()
    return _db_instance
