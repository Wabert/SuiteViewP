"""Connection Manager - Manages database connections"""

import logging
from typing import Dict, List, Optional, Tuple
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine

from suiteview.data.repositories import get_connection_repository
from suiteview.core.credential_manager import get_credential_manager

logger = logging.getLogger(__name__)


class ConnectionManager:
    """Manages database connections and credentials"""

    def __init__(self):
        self.repo = get_connection_repository()
        self.cred_manager = get_credential_manager()
        self._engines: Dict[int, Engine] = {}  # Cache of SQLAlchemy engines

    def add_connection(self, name: str, conn_type: str, server: str,
                      database: str, auth_type: str,
                      username: str = None, password: str = None) -> int:
        """
        Add new database connection

        Args:
            name: Connection name
            conn_type: Connection type (SQL_SERVER, DB2, ORACLE, etc.)
            server: Server name/host
            database: Database name
            auth_type: Authentication type (WINDOWS, SQL_AUTH)
            username: Username (for SQL_AUTH)
            password: Password (for SQL_AUTH)

        Returns:
            connection_id of the newly created connection
        """
        # Encrypt credentials
        encrypted_username, encrypted_password = self.cred_manager.encrypt_credentials(
            username, password
        )

        # Save to database
        connection_id = self.repo.create_connection(
            connection_name=name,
            connection_type=conn_type,
            server_name=server,
            database_name=database,
            auth_type=auth_type,
            encrypted_username=encrypted_username,
            encrypted_password=encrypted_password
        )

        logger.info(f"Added connection: {name} (ID: {connection_id})")
        return connection_id

    def get_connections(self) -> List[Dict]:
        """Get all active connections"""
        return self.repo.get_all_connections()

    def get_connection(self, connection_id: int) -> Optional[Dict]:
        """Get a specific connection by ID"""
        return self.repo.get_connection(connection_id)

    def update_connection(self, connection_id: int, **kwargs) -> bool:
        """
        Update a connection's details

        Args:
            connection_id: ID of connection to update
            **kwargs: Fields to update (name, server, database, etc.)
        """
        # If updating username/password, encrypt them first
        if 'username' in kwargs or 'password' in kwargs:
            username = kwargs.pop('username', None)
            password = kwargs.pop('password', None)

            encrypted_username, encrypted_password = self.cred_manager.encrypt_credentials(
                username, password
            )

            if encrypted_username is not None:
                kwargs['encrypted_username'] = encrypted_username
            if encrypted_password is not None:
                kwargs['encrypted_password'] = encrypted_password

        # Clear cached engine
        if connection_id in self._engines:
            self._engines[connection_id].dispose()
            del self._engines[connection_id]

        return self.repo.update_connection(connection_id, **kwargs)

    def delete_connection(self, connection_id: int) -> bool:
        """Delete a connection"""
        # Clear cached engine
        if connection_id in self._engines:
            self._engines[connection_id].dispose()
            del self._engines[connection_id]

        return self.repo.delete_connection(connection_id)

    def test_connection(self, connection_id: int) -> Tuple[bool, str]:
        """
        Test a database connection

        Args:
            connection_id: ID of connection to test

        Returns:
            Tuple of (success: bool, message: str)
        """
        try:
            connection = self.repo.get_connection(connection_id)
            if not connection:
                return False, "Connection not found"

            # Get engine and test connection
            engine = self._get_engine(connection_id)
            with engine.connect() as conn:
                # Execute a simple query to test connection
                result = conn.execute(text("SELECT 1"))
                result.fetchone()

            # Update last_tested timestamp
            self.repo.update_last_tested(connection_id)

            logger.info(f"Connection test successful: {connection['connection_name']}")
            return True, "Connection successful!"

        except Exception as e:
            error_msg = str(e)
            logger.error(f"Connection test failed: {error_msg}")
            return False, f"Connection failed: {error_msg}"

    def get_engine(self, connection_id: int) -> Engine:
        """
        Get SQLAlchemy engine for a connection

        Args:
            connection_id: ID of connection

        Returns:
            SQLAlchemy Engine instance
        """
        return self._get_engine(connection_id)

    def _get_engine(self, connection_id: int) -> Engine:
        """Internal method to get or create engine"""
        # Return cached engine if exists
        if connection_id in self._engines:
            return self._engines[connection_id]

        # Get connection details
        connection = self.repo.get_connection(connection_id)
        if not connection:
            raise ValueError(f"Connection {connection_id} not found")

        # Build connection string
        connection_string = self._build_connection_string(connection)

        # Create engine
        engine = create_engine(connection_string, echo=False)
        self._engines[connection_id] = engine

        logger.debug(f"Created engine for connection: {connection['connection_name']}")
        return engine

    def _build_connection_string(self, connection: Dict) -> str:
        """
        Build SQLAlchemy connection string from connection details

        Args:
            connection: Connection dictionary

        Returns:
            SQLAlchemy connection string
        """
        conn_type = connection['connection_type']
        server = connection['server_name']
        database = connection['database_name']
        auth_type = connection['auth_type']

        # Decrypt credentials if needed
        username, password = self.cred_manager.decrypt_credentials(
            connection.get('encrypted_username'),
            connection.get('encrypted_password')
        )

        # Build connection string based on type
        if conn_type == 'SQL_SERVER':
            if auth_type == 'WINDOWS':
                # Windows authentication
                return f"mssql+pyodbc://{server}/{database}?driver=ODBC+Driver+17+for+SQL+Server&trusted_connection=yes"
            else:
                # SQL Server authentication
                return f"mssql+pyodbc://{username}:{password}@{server}/{database}?driver=ODBC+Driver+17+for+SQL+Server"

        elif conn_type == 'SQLITE':
            # SQLite file path
            return f"sqlite:///{database}"

        elif conn_type == 'POSTGRESQL':
            return f"postgresql://{username}:{password}@{server}/{database}"

        elif conn_type == 'MYSQL':
            return f"mysql+pymysql://{username}:{password}@{server}/{database}"

        elif conn_type == 'ORACLE':
            return f"oracle+cx_oracle://{username}:{password}@{server}/{database}"

        elif conn_type == 'DB2':
            return f"ibm_db_sa://{username}:{password}@{server}/{database}"

        else:
            # Use custom connection string if provided
            if connection.get('connection_string'):
                return connection['connection_string']
            else:
                raise ValueError(f"Unsupported connection type: {conn_type}")

    def close_all_connections(self):
        """Close all cached engine connections"""
        for connection_id, engine in self._engines.items():
            try:
                engine.dispose()
                logger.debug(f"Disposed engine for connection {connection_id}")
            except Exception as e:
                logger.error(f"Error disposing engine {connection_id}: {e}")

        self._engines.clear()


# Singleton instance
_connection_manager: Optional[ConnectionManager] = None


def get_connection_manager() -> ConnectionManager:
    """Get or create singleton connection manager instance"""
    global _connection_manager
    if _connection_manager is None:
        _connection_manager = ConnectionManager()
    return _connection_manager
