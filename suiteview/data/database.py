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

        # Bookmark icons cache - stores pre-fetched icons for fast loading
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS bookmark_icons (
                path TEXT PRIMARY KEY,
                icon_data BLOB NOT NULL,
                icon_type TEXT NOT NULL,
                last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # Task tracker tables (LEGACY — TaskTracker now uses JSON storage
        # at ~/.suiteview/tasktracker.json. These tables are kept for
        # backward compatibility but are no longer read or written.)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS tasks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                task_id TEXT NOT NULL UNIQUE,
                description TEXT NOT NULL DEFAULT '',
                assignee_name TEXT NOT NULL DEFAULT '',
                assignee_email TEXT NOT NULL DEFAULT '',
                priority TEXT NOT NULL DEFAULT 'Medium',
                due_date TEXT,
                status TEXT NOT NULL DEFAULT 'Open',
                created_date TEXT NOT NULL,
                updated_date TEXT NOT NULL,
                email_sent BOOLEAN DEFAULT 0,
                email_sent_date TEXT
            )
        """)

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS task_attachments (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                task_id TEXT NOT NULL,
                file_name TEXT NOT NULL,
                file_path TEXT NOT NULL,
                is_copy BOOLEAN DEFAULT 0,
                added_date TEXT NOT NULL,
                FOREIGN KEY (task_id) REFERENCES tasks(task_id) ON DELETE CASCADE
            )
        """)

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS task_id_sequence (
                current_value INTEGER NOT NULL DEFAULT 0
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

        # Migration 5: Add notes column to saved_queries if it doesn't exist
        try:
            cursor.execute("SELECT notes FROM saved_queries LIMIT 1")
        except:
            # Column doesn't exist, add it
            print("Running migration: Adding notes column to saved_queries")
            cursor.execute("""
                ALTER TABLE saved_queries ADD COLUMN notes TEXT
            """)
            conn.commit()
            print("Migration completed: notes column added")

        # Migration 6: Add database_type column to connections if it doesn't exist
        # This is used for UI grouping (DB2, SQL_SERVER, etc.) and can be user-defined.
        try:
            cursor.execute("SELECT database_type FROM connections LIMIT 1")
        except:
            print("Running migration: Adding database_type column to connections")
            cursor.execute("""
                ALTER TABLE connections ADD COLUMN database_type TEXT
            """)
            # Backfill existing rows so UI grouping stays consistent
            cursor.execute("""
                UPDATE connections
                SET database_type = connection_type
                WHERE database_type IS NULL OR database_type = ''
            """)
            conn.commit()
            print("Migration completed: database_type column added")

        # Migration 7: Create bookmark_icons table if it doesn't exist
        try:
            cursor.execute("SELECT 1 FROM bookmark_icons LIMIT 1")
        except:
            print("Running migration: Creating bookmark_icons table")
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS bookmark_icons (
                    path TEXT PRIMARY KEY,
                    icon_data BLOB NOT NULL,
                    icon_type TEXT NOT NULL,
                    last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            conn.commit()
            print("Migration completed: bookmark_icons table created")

        # Migration 8: Create task tracker tables (LEGACY — kept for DB compat)
        try:
            cursor.execute("SELECT 1 FROM tasks LIMIT 1")
        except:
            print("Running migration: Creating task tracker tables")
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS tasks (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    task_id TEXT NOT NULL UNIQUE,
                    description TEXT NOT NULL DEFAULT '',
                    assignee_name TEXT NOT NULL DEFAULT '',
                    assignee_email TEXT NOT NULL DEFAULT '',
                    priority TEXT NOT NULL DEFAULT 'Medium',
                    due_date TEXT,
                    status TEXT NOT NULL DEFAULT 'Open',
                    created_date TEXT NOT NULL,
                    updated_date TEXT NOT NULL,
                    email_sent BOOLEAN DEFAULT 0,
                    email_sent_date TEXT
                )
            """)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS task_attachments (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    task_id TEXT NOT NULL,
                    file_name TEXT NOT NULL,
                    file_path TEXT NOT NULL,
                    is_copy BOOLEAN DEFAULT 0,
                    added_date TEXT NOT NULL,
                    FOREIGN KEY (task_id) REFERENCES tasks(task_id) ON DELETE CASCADE
                )
            """)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS task_id_sequence (
                    current_value INTEGER NOT NULL DEFAULT 0
                )
            """)
            # Seed the sequence table
            cursor.execute("INSERT INTO task_id_sequence (current_value) VALUES (0)")
            conn.commit()
            print("Migration completed: task tracker tables created")

        # Ensure task_id_sequence has a row (for fresh installs)
        try:
            cursor.execute("SELECT current_value FROM task_id_sequence LIMIT 1")
            if cursor.fetchone() is None:
                cursor.execute("INSERT INTO task_id_sequence (current_value) VALUES (0)")
                conn.commit()
        except:
            pass

        # Migration 9: Create abr_email_recipients table for ABR Quote Email Print
        try:
            cursor.execute("SELECT 1 FROM abr_email_recipients LIMIT 1")
        except:
            print("Running migration: Creating abr_email_recipients table")
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS abr_email_recipients (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    email TEXT NOT NULL UNIQUE,
                    display_name TEXT,
                    organization TEXT DEFAULT 'AmericanNational',
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            # Seed with default recipients
            defaults = [
                ("Christie.Turner@AmericanNational.com", "Christie Turner", "AmericanNational"),
                ("Manny.Calero@AmericanNational.com", "Manny Calero", "AmericanNational"),
                ("Frenesa.Hall@AmericanNational.com", "Frenesa Hall", "AmericanNational"),
                ("David.Mason@AmericanNational.com", "David Mason", "AmericanNational"),
                ("Robert.Haessly@AmericanNational.com", "Robert Haessly", "AmericanNational"),
                ("Jordan.Carrillo@AmericanNational.com", "Jordan Carrillo", "AmericanNational"),
                ("Veronica.Tovar@AmericanNational.com", "Veronica Tovar", "AmericanNational"),
                ("Jacqueline.Barabino@AmericanNational.com", "Jacqueline Barabino", "AmericanNational"),
            ]
            cursor.executemany(
                "INSERT OR IGNORE INTO abr_email_recipients (email, display_name, organization) VALUES (?, ?, ?)",
                defaults,
            )
            conn.commit()
            print("Migration completed: abr_email_recipients table created with defaults")

        # Migration 10: Create abr_email_directory table (org-wide email directory for autocomplete)
        try:
            cursor.execute("SELECT 1 FROM abr_email_directory LIMIT 1")
        except:
            print("Running migration: Creating abr_email_directory table")
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS abr_email_directory (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    email TEXT NOT NULL UNIQUE,
                    display_name TEXT,
                    organization TEXT DEFAULT 'AmericanNational',
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            # Seed with known organizational emails
            defaults = [
                ("Christie.Turner@AmericanNational.com", "Christie Turner", "AmericanNational"),
                ("Manny.Calero@AmericanNational.com", "Manny Calero", "AmericanNational"),
                ("Frenesa.Hall@AmericanNational.com", "Frenesa Hall", "AmericanNational"),
                ("David.Mason@AmericanNational.com", "David Mason", "AmericanNational"),
                ("Robert.Haessly@AmericanNational.com", "Robert Haessly", "AmericanNational"),
                ("Jordan.Carrillo@AmericanNational.com", "Jordan Carrillo", "AmericanNational"),
                ("Veronica.Tovar@AmericanNational.com", "Veronica Tovar", "AmericanNational"),
                ("Jacqueline.Barabino@AmericanNational.com", "Jacqueline Barabino", "AmericanNational"),
            ]
            cursor.executemany(
                "INSERT OR IGNORE INTO abr_email_directory (email, display_name, organization) VALUES (?, ?, ?)",
                defaults,
            )
            conn.commit()
            print("Migration completed: abr_email_directory table created with defaults")

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
