"""Data repositories for database access"""

import json
import logging
import sqlite3
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
                         connection_string: str = None,
                         database_type: str = None) -> int:
        """
        Create a new connection

        Returns:
            connection_id of the newly created connection
        """
        cursor = self.db.execute("""
            INSERT INTO connections (
                connection_name, connection_type, server_name, database_name,
                auth_type, encrypted_username, encrypted_password, connection_string,
                database_type,
                is_active
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 1)
        """, (connection_name, connection_type, server_name, database_name,
              auth_type, encrypted_username, encrypted_password, connection_string,
              database_type))

        connection_id = cursor.lastrowid
        logger.info(f"Created connection: {connection_name} (ID: {connection_id})")
        return connection_id

    def get_all_connections(self) -> List[Dict]:
        """Get all connections"""
        rows = self.db.fetchall("""
            SELECT connection_id, connection_name, connection_type, server_name,
                   database_name, auth_type, encrypted_username, encrypted_password,
                   connection_string, database_type, created_at, last_tested, is_active
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
                'database_type': row[9],
                'created_at': row[10],
                'last_tested': row[11],
                'is_active': row[12]
            })

        return connections

    def get_connection(self, connection_id: int) -> Optional[Dict]:
        """Get a single connection by ID"""
        row = self.db.fetchone("""
            SELECT connection_id, connection_name, connection_type, server_name,
                   database_name, auth_type, encrypted_username, encrypted_password,
                   connection_string, database_type, created_at, last_tested, is_active
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
            'database_type': row[9],
            'created_at': row[10],
            'last_tested': row[11],
            'is_active': row[12]
        }

    def update_connection(self, connection_id: int, **kwargs) -> bool:
        """Update a connection's details"""
        # Build dynamic UPDATE query based on provided kwargs
        fields = []
        values = []

        for key, value in kwargs.items():
            if key in ['connection_name', 'connection_type', 'server_name', 'database_name',
                      'auth_type', 'encrypted_username', 'encrypted_password', 'connection_string',
                      'database_type']:
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
            except Exception:
                logger.debug("Could not convert cached unique value %r; using string fallback", val, exc_info=True)
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
_metadata_cache_repo: Optional[MetadataCacheRepository] = None


def get_connection_repository() -> ConnectionRepository:
    """Get or create singleton connection repository"""
    global _connection_repo
    if _connection_repo is None:
        _connection_repo = ConnectionRepository()
    return _connection_repo




def get_metadata_cache_repository() -> MetadataCacheRepository:
    """Get or create singleton metadata cache repository"""
    global _metadata_cache_repo
    if _metadata_cache_repo is None:
        _metadata_cache_repo = MetadataCacheRepository()
    return _metadata_cache_repo


class EmailRepository:
    """Repository for email metadata caching"""
    
    def __init__(self, db=None):
        self.db = db if db is not None else get_database()
        self._ensure_tables()
    
    def _ensure_tables(self):
        """Create email tables if they don't exist"""
        # Emails table
        self.db.execute("""
            CREATE TABLE IF NOT EXISTS emails (
                email_id TEXT PRIMARY KEY,
                subject TEXT,
                sender TEXT,
                sender_email TEXT,
                received_date TEXT,
                size INTEGER,
                unread INTEGER,
                has_attachments INTEGER,
                attachment_count INTEGER,
                folder_path TEXT,
                body_preview TEXT,
                last_synced TEXT
            )
        """)
        
        # Attachments table
        self.db.execute("""
            CREATE TABLE IF NOT EXISTS email_attachments (
                attachment_id INTEGER PRIMARY KEY AUTOINCREMENT,
                email_id TEXT,
                email_subject TEXT,
                email_sender TEXT,
                email_date TEXT,
                attachment_name TEXT,
                attachment_type TEXT,
                attachment_size INTEGER,
                attachment_index INTEGER,
                file_hash TEXT,
                last_synced TEXT,
                sender_name TEXT DEFAULT '',
                FOREIGN KEY (email_id) REFERENCES emails(email_id)
            )
        """)
        
        # Add sender_name column if missing (for existing databases)
        try:
            self.db.execute("ALTER TABLE email_attachments ADD COLUMN sender_name TEXT DEFAULT ''")
        except sqlite3.OperationalError as exc:
            if "duplicate column name" not in str(exc).lower():
                raise
            logger.debug("email_attachments.sender_name column already exists", exc_info=True)
        
        # Sync tracking table
        self.db.execute("""
            CREATE TABLE IF NOT EXISTS email_sync_status (
                sync_id INTEGER PRIMARY KEY AUTOINCREMENT,
                folder_path TEXT UNIQUE,
                last_sync_time TEXT,
                email_count INTEGER,
                attachment_count INTEGER,
                scan_complete INTEGER DEFAULT 0
            )
        """)
        
        # Settings table for email-related preferences
        self.db.execute("""
            CREATE TABLE IF NOT EXISTS email_settings (
                setting_key TEXT PRIMARY KEY,
                setting_value TEXT,
                updated_at TEXT
            )
        """)
        
        # Create indexes
        self.db.execute("""
            CREATE INDEX IF NOT EXISTS idx_emails_received_date 
            ON emails(received_date DESC)
        """)
        
        self.db.execute("""
            CREATE INDEX IF NOT EXISTS idx_emails_folder 
            ON emails(folder_path)
        """)
        
        self.db.execute("""
            CREATE INDEX IF NOT EXISTS idx_attachments_email_id 
            ON email_attachments(email_id)
        """)
        
        self.db.execute("""
            CREATE INDEX IF NOT EXISTS idx_attachments_hash 
            ON email_attachments(file_hash)
        """)
    
    def save_emails(self, emails: List[Dict]):
        """Save or update emails in cache"""
        for email in emails:
            self.db.execute("""
                INSERT OR REPLACE INTO emails (
                    email_id, subject, sender, sender_email, received_date,
                    size, unread, has_attachments, attachment_count,
                    folder_path, body_preview, last_synced
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                email['email_id'],
                email['subject'],
                email['sender'],
                email['sender_email'],
                email['received_date'].isoformat() if hasattr(email['received_date'], 'isoformat') else str(email['received_date']),
                email['size'],
                1 if email['unread'] else 0,
                1 if email['has_attachments'] else 0,
                email['attachment_count'],
                email['folder_path'],
                email.get('body_preview', ''),
                datetime.now().isoformat()
            ))
    
    def save_attachments(self, attachments: List[Dict]):
        """Save or update attachments in cache"""
        for attach in attachments:
            self.db.execute("""
                INSERT OR REPLACE INTO email_attachments (
                    email_id, email_subject, email_sender, email_date,
                    attachment_name, attachment_type, attachment_size,
                    attachment_index, file_hash, last_synced
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                attach['email_id'],
                attach['email_subject'],
                attach['email_sender'],
                attach['email_date'].isoformat() if hasattr(attach['email_date'], 'isoformat') else str(attach['email_date']),
                attach['attachment_name'],
                attach['attachment_type'],
                attach['attachment_size'],
                attach['attachment_index'],
                attach.get('file_hash'),
                datetime.now().isoformat()
            ))
    
    def get_all_emails(self, folder_path: str = None, unread_only: bool = False) -> List[Dict]:
        """Get emails from cache"""
        query = "SELECT * FROM emails WHERE 1=1"
        params = []
        
        if folder_path:
            query += " AND folder_path = ?"
            params.append(folder_path)
        
        if unread_only:
            query += " AND unread = 1"
        
        query += " ORDER BY received_date DESC"
        
        rows = self.db.fetchall(query, tuple(params))
        
        emails = []
        for row in rows:
            emails.append({
                'email_id': row[0],
                'subject': row[1],
                'sender': row[2],
                'sender_email': row[3],
                'received_date': row[4],
                'size': row[5],
                'unread': bool(row[6]),
                'has_attachments': bool(row[7]),
                'attachment_count': row[8],
                'folder_path': row[9],
                'body_preview': row[10],
                'last_synced': row[11]
            })
        
        return emails
    
    def get_all_attachments(self) -> List[Dict]:
        """Get all attachments from cache"""
        rows = self.db.fetchall("""
            SELECT attachment_id, email_id, email_subject, email_sender,
                   email_date, attachment_name, attachment_type, attachment_size,
                   attachment_index, file_hash, last_synced
            FROM email_attachments
            ORDER BY email_date DESC
        """)
        
        attachments = []
        for row in rows:
            attachments.append({
                'attachment_id': row[0],
                'email_id': row[1],
                'email_subject': row[2],
                'email_sender': row[3],
                'email_date': row[4],
                'attachment_name': row[5],
                'attachment_type': row[6],
                'attachment_size': row[7],
                'attachment_index': row[8],
                'file_hash': row[9],
                'last_synced': row[10]
            })
        
        return attachments
    
    def get_duplicate_attachments(self) -> List[Dict]:
        """Find duplicate attachments by file hash"""
        rows = self.db.fetchall("""
            SELECT file_hash, COUNT(*) as count,
                   GROUP_CONCAT(attachment_name) as names,
                   GROUP_CONCAT(email_subject) as subjects,
                   SUM(attachment_size) as total_size
            FROM email_attachments
            WHERE file_hash IS NOT NULL
            GROUP BY file_hash
            HAVING count > 1
            ORDER BY count DESC, total_size DESC
        """)
        
        duplicates = []
        for row in rows:
            duplicates.append({
                'file_hash': row[0],
                'count': row[1],
                'names': row[2],
                'subjects': row[3],
                'total_size': row[4]
            })
        
        return duplicates
    
    def get_attachments_by_hash(self, file_hash: str) -> List[Dict]:
        """Get all attachments with a specific hash"""
        rows = self.db.fetchall("""
            SELECT attachment_id, email_id, email_subject, email_sender,
                   email_date, attachment_name, attachment_type, attachment_size,
                   attachment_index, file_hash, last_synced
            FROM email_attachments
            WHERE file_hash = ?
            ORDER BY email_date DESC
        """, (file_hash,))
        
        attachments = []
        for row in rows:
            attachments.append({
                'attachment_id': row[0],
                'email_id': row[1],
                'email_subject': row[2],
                'email_sender': row[3],
                'email_date': row[4],
                'attachment_name': row[5],
                'attachment_type': row[6],
                'attachment_size': row[7],
                'attachment_index': row[8],
                'file_hash': row[9],
                'last_synced': row[10]
            })
        
        return attachments
    
    def update_sync_status(self, folder_path: str, email_count: int, attachment_count: int, scan_complete: bool = True):
        """Update sync status for a folder"""
        self.db.execute("""
            INSERT OR REPLACE INTO email_sync_status (
                folder_path, last_sync_time, email_count, attachment_count, scan_complete
            ) VALUES (?, ?, ?, ?, ?)
        """, (folder_path, datetime.now().isoformat(), email_count, attachment_count, 1 if scan_complete else 0))
    
    def get_sync_status(self, folder_path: str = None) -> List[Dict]:
        """Get sync status for folder(s)"""
        if folder_path:
            rows = self.db.fetchall("""
                SELECT sync_id, folder_path, last_sync_time, email_count,
                       attachment_count, scan_complete
                FROM email_sync_status
                WHERE folder_path = ?
            """, (folder_path,))
        else:
            rows = self.db.fetchall("""
                SELECT sync_id, folder_path, last_sync_time, email_count,
                       attachment_count, scan_complete
                FROM email_sync_status
                ORDER BY last_sync_time DESC
            """)
        
        statuses = []
        for row in rows:
            statuses.append({
                'sync_id': row[0],
                'folder_path': row[1],
                'last_sync_time': row[2],
                'email_count': row[3],
                'attachment_count': row[4],
                'scan_complete': bool(row[5])
            })
        
        return statuses
    
    def clear_cache(self, folder_path: str = None):
        """Clear email cache for folder or all"""
        if folder_path:
            self.db.execute("DELETE FROM emails WHERE folder_path = ?", (folder_path,))
            self.db.execute("""
                DELETE FROM email_attachments 
                WHERE email_id IN (SELECT email_id FROM emails WHERE folder_path = ?)
            """, (folder_path,))
            self.db.execute("DELETE FROM email_sync_status WHERE folder_path = ?", (folder_path,))
        else:
            self.db.execute("DELETE FROM emails")
            self.db.execute("DELETE FROM email_attachments")
            self.db.execute("DELETE FROM email_sync_status")
    
    def get_last_sync_time(self) -> Optional[datetime]:
        """Get timestamp of the last successful sync
        
        Returns:
            datetime of last sync, or None if never synced
        """
        try:
            rows = self.db.fetchall("""
                SELECT last_sync_time 
                FROM email_sync_status 
                ORDER BY last_sync_time DESC 
                LIMIT 1
            """)
            
            if rows and rows[0][0]:
                return datetime.fromisoformat(rows[0][0])
            
            return None
        
        except Exception as e:
            logger.error(f"Error getting last sync time: {e}")
            return None
    
    def record_sync_time(self):
        """Record that a sync was completed (for incremental sync tracking)"""
        # This is called after update_sync_status, so the timestamp is already recorded
        # Just log it for tracking
        last_sync = self.get_last_sync_time()
        if last_sync:
            logger.info(f"Sync completed at {last_sync}")
    
    def get_setting(self, key: str, default: str = None) -> Optional[str]:
        """Get a setting value by key"""
        try:
            row = self.db.fetchone(
                "SELECT setting_value FROM email_settings WHERE setting_key = ?",
                (key,)
            )
            return row[0] if row else default
        except Exception as e:
            logger.error(f"Error getting setting {key}: {e}")
            return default
    
    def set_setting(self, key: str, value: str):
        """Set a setting value"""
        try:
            self.db.execute("""
                INSERT OR REPLACE INTO email_settings (setting_key, setting_value, updated_at)
                VALUES (?, ?, ?)
            """, (key, value, datetime.now().isoformat()))
        except Exception as e:
            logger.error(f"Error setting {key}: {e}")
    
    def get_attachments_since(self, since_date: datetime) -> List[Dict]:
        """Get attachments from cache that are newer than a given date"""
        try:
            date_str = since_date.isoformat()
            rows = self.db.fetchall("""
                SELECT attachment_id, email_id, email_subject, email_sender,
                       email_date, attachment_name, attachment_type, attachment_size,
                       attachment_index, file_hash, last_synced, sender_name
                FROM email_attachments
                WHERE email_date >= ?
                ORDER BY email_date DESC
            """, (date_str,))
            
            attachments = []
            for row in rows:
                attachments.append({
                    'attachment_id': row[0],
                    'email_id': row[1],
                    'email_subject': row[2],
                    'email_sender': row[3],
                    'email_date': row[4],
                    'attachment_name': row[5],
                    'attachment_type': row[6],
                    'attachment_size': row[7],
                    'attachment_index': row[8],
                    'file_hash': row[9],
                    'last_synced': row[10],
                    'sender_name': row[11] if len(row) > 11 else ''
                })
            
            return attachments
        except Exception as e:
            logger.error(f"Error getting attachments since {since_date}: {e}")
            return []
    
    def get_oldest_attachment_date(self) -> Optional[datetime]:
        """Get the date of the oldest attachment in cache"""
        try:
            row = self.db.fetchone("""
                SELECT MIN(email_date) FROM email_attachments
            """)
            if row and row[0]:
                return datetime.fromisoformat(row[0])
            return None
        except Exception as e:
            logger.error(f"Error getting oldest attachment date: {e}")
            return None
    
    def get_newest_attachment_date(self) -> Optional[datetime]:
        """Get the date of the newest attachment in cache"""
        try:
            row = self.db.fetchone("""
                SELECT MAX(email_date) FROM email_attachments
            """)
            if row and row[0]:
                return datetime.fromisoformat(row[0])
            return None
        except Exception as e:
            logger.error(f"Error getting newest attachment date: {e}")
            return None
    
    def save_attachment_simple(self, attachment: Dict):
        """Save a single attachment to cache (simplified for attachment window)"""
        try:
            self.db.execute("""
                INSERT OR REPLACE INTO email_attachments (
                    email_id, email_subject, email_sender, email_date,
                    attachment_name, attachment_type, attachment_size,
                    attachment_index, file_hash, last_synced, sender_name
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                attachment['email_id'],
                attachment.get('email_subject', ''),
                attachment['sender'],
                attachment['date'].isoformat() if hasattr(attachment['date'], 'isoformat') else str(attachment['date']),
                attachment['attachment_name'],
                attachment.get('attachment_type', ''),
                attachment.get('attachment_size', 0),
                attachment['attachment_index'],
                attachment.get('file_hash'),
                datetime.now().isoformat(),
                attachment.get('sender_name', '')
            ))
        except Exception as e:
            logger.error(f"Error saving attachment: {e}")


# Singleton instances
_email_repo = None


def get_email_repository() -> EmailRepository:
    """Get or create singleton email repository"""
    global _email_repo
    if _email_repo is None:
        _email_repo = EmailRepository()
    return _email_repo
