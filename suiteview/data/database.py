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
                is_common BOOLEAN DEFAULT 0,
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
                folder_id INTEGER,
                query_definition TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                last_modified TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                last_executed TIMESTAMP,
                execution_duration_ms INTEGER,
                record_count INTEGER,
                FOREIGN KEY (folder_id) REFERENCES query_folders(folder_id) ON DELETE SET NULL
            )
        """)
        
        # Query folders for organization
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS query_folders (
                folder_id INTEGER PRIMARY KEY AUTOINCREMENT,
                folder_name TEXT NOT NULL,
                query_type TEXT NOT NULL,
                parent_folder_id INTEGER,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                display_order INTEGER DEFAULT 0,
                FOREIGN KEY (parent_folder_id) REFERENCES query_folders(folder_id) ON DELETE CASCADE
            )
        """)

        # Data map folders for organization
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS data_map_folders (
                folder_id INTEGER PRIMARY KEY AUTOINCREMENT,
                folder_name TEXT NOT NULL,
                parent_folder_id INTEGER,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                display_order INTEGER DEFAULT 0,
                FOREIGN KEY (parent_folder_id) REFERENCES data_map_folders(folder_id) ON DELETE CASCADE
            )
        """)

        # Data maps
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS data_maps (
                data_map_id INTEGER PRIMARY KEY AUTOINCREMENT,
                map_name TEXT NOT NULL UNIQUE,
                folder_id INTEGER,
                key_data_type TEXT DEFAULT 'string',
                value_data_type TEXT DEFAULT 'string',
                notes TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                last_modified TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (folder_id) REFERENCES data_map_folders(folder_id) ON DELETE SET NULL
            )
        """)

        # Data map entries (key-value pairs)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS data_map_entries (
                entry_id INTEGER PRIMARY KEY AUTOINCREMENT,
                data_map_id INTEGER NOT NULL,
                key_value TEXT NOT NULL,
                mapped_value TEXT,
                comment TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (data_map_id) REFERENCES data_maps(data_map_id) ON DELETE CASCADE
            )
        """)

        # Field to data map assignments
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS field_data_map_assignments (
                assignment_id INTEGER PRIMARY KEY AUTOINCREMENT,
                connection_id INTEGER NOT NULL,
                schema_name TEXT,
                table_name TEXT NOT NULL,
                column_name TEXT NOT NULL,
                data_map_id INTEGER NOT NULL,
                assigned_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (connection_id) REFERENCES connections(connection_id) ON DELETE CASCADE,
                FOREIGN KEY (data_map_id) REFERENCES data_maps(data_map_id) ON DELETE CASCADE,
                UNIQUE(connection_id, schema_name, table_name, column_name)
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
        
        # Run migrations
        self._run_migrations(conn)

    def _run_migrations(self, conn):
        """Run database migrations for schema updates"""
        cursor = conn.cursor()
        
        # Migration 1: Add is_common column to column_metadata if it doesn't exist
        try:
            cursor.execute("SELECT is_common FROM column_metadata LIMIT 1")
        except:
            # Column doesn't exist, add it
            print("Running migration: Adding is_common column to column_metadata")
            cursor.execute("""
                ALTER TABLE column_metadata ADD COLUMN is_common BOOLEAN DEFAULT 0
            """)
            conn.commit()
            print("Migration completed: is_common column added")
        
        # Migration 2: Add folder_id column to saved_queries if it doesn't exist
        try:
            cursor.execute("SELECT folder_id FROM saved_queries LIMIT 1")
        except:
            # Column doesn't exist, add it
            print("Running migration: Adding folder_id column to saved_queries")
            cursor.execute("""
                ALTER TABLE saved_queries ADD COLUMN folder_id INTEGER REFERENCES query_folders(folder_id) ON DELETE SET NULL
            """)
            conn.commit()
            print("Migration completed: folder_id column added")
        
        # Migration 3: Create default "General" folders if they don't exist
        cursor.execute("SELECT COUNT(*) FROM query_folders WHERE folder_name = 'General' AND query_type = 'DB'")
        if cursor.fetchone()[0] == 0:
            print("Running migration: Creating default folders")
            cursor.execute("""
                INSERT INTO query_folders (folder_name, query_type, display_order)
                VALUES ('General', 'DB', 0)
            """)
            cursor.execute("""
                INSERT INTO query_folders (folder_name, query_type, display_order)
                VALUES ('General', 'XDB', 0)
            """)
            
            # Move all existing queries to General folder
            cursor.execute("SELECT folder_id FROM query_folders WHERE folder_name = 'General' AND query_type = 'DB'")
            db_folder_id = cursor.fetchone()[0]
            cursor.execute("UPDATE saved_queries SET folder_id = ? WHERE query_type = 'DB' AND folder_id IS NULL", (db_folder_id,))
            
            cursor.execute("SELECT folder_id FROM query_folders WHERE folder_name = 'General' AND query_type = 'XDB'")
            xdb_folder_id = cursor.fetchone()[0]
            cursor.execute("UPDATE saved_queries SET folder_id = ? WHERE query_type = 'XDB' AND folder_id IS NULL", (xdb_folder_id,))
            
            conn.commit()
            print("Migration completed: Default folders created and queries migrated")
        
        # Migration 4: Create default "General" folder for data maps if it doesn't exist
        cursor.execute("SELECT COUNT(*) FROM data_map_folders WHERE folder_name = 'General'")
        if cursor.fetchone()[0] == 0:
            print("Running migration: Creating default data map folder")
            cursor.execute("""
                INSERT INTO data_map_folders (folder_name, display_order)
                VALUES ('General', 0)
            """)
            conn.commit()
            print("Migration completed: Default data map folder created")

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
