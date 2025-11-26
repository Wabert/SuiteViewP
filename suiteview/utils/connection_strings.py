"""Connection String Builder - Centralized connection string construction

This module provides utility functions for building database connection strings.
By centralizing this logic, we avoid duplication and ensure consistent connection
string formats across the application.
"""

import logging
from typing import Optional

logger = logging.getLogger(__name__)


class ConnectionStringBuilder:
    """Builds connection strings for various database types"""

    @staticmethod
    def build_db2_dsn(dsn: str) -> str:
        """
        Build DB2 connection string from DSN name.

        Args:
            dsn: DSN name (may include "DSN=" prefix which will be stripped)

        Returns:
            Connection string in format "DSN=<dsn_name>"

        Raises:
            ValueError: If DSN is empty
        """
        if not dsn:
            raise ValueError("DB2 connection requires DSN")

        # Strip "DSN=" prefix if present
        clean_dsn = dsn.replace('DSN=', '').strip()
        if not clean_dsn:
            raise ValueError("DB2 connection requires DSN")

        return f"DSN={clean_dsn}"

    @staticmethod
    def build_access(file_path: str) -> str:
        """
        Build MS Access connection string.

        Args:
            file_path: Path to .mdb or .accdb file

        Returns:
            ODBC connection string for Access

        Raises:
            ValueError: If file_path is empty
        """
        if not file_path:
            raise ValueError("Access connection requires file path")

        return (
            r'DRIVER={Microsoft Access Driver (*.mdb, *.accdb)};'
            f'DBQ={file_path};'
        )

    @staticmethod
    def build_sql_server(
        server: str,
        database: str,
        auth_type: str = 'WINDOWS',
        username: Optional[str] = None,
        password: Optional[str] = None,
        driver: str = 'ODBC+Driver+17+for+SQL+Server'
    ) -> str:
        """
        Build SQL Server connection string.

        Args:
            server: Server hostname or IP
            database: Database name
            auth_type: 'WINDOWS' for Windows auth, 'SQL_AUTH' for SQL auth
            username: Username for SQL auth
            password: Password for SQL auth
            driver: ODBC driver name

        Returns:
            SQLAlchemy-compatible connection string

        Raises:
            ValueError: If required parameters are missing
        """
        if not server:
            raise ValueError("SQL Server connection requires server name")
        if not database:
            raise ValueError("SQL Server connection requires database name")

        if auth_type == 'WINDOWS':
            # Windows integrated authentication
            return (
                f"mssql+pyodbc://@{server}/{database}"
                f"?driver={driver}&trusted_connection=yes"
            )
        else:
            # SQL Server authentication
            if not username:
                raise ValueError("SQL authentication requires username")
            if not password:
                raise ValueError("SQL authentication requires password")

            # URL-encode special characters in password
            import urllib.parse
            encoded_password = urllib.parse.quote_plus(password)

            return (
                f"mssql+pyodbc://{username}:{encoded_password}@{server}/{database}"
                f"?driver={driver}"
            )

    @staticmethod
    def extract_dsn_from_connection_string(connection_string: str) -> str:
        """
        Extract DSN name from a connection string.

        Args:
            connection_string: Connection string that may contain "DSN=<name>"

        Returns:
            DSN name without the "DSN=" prefix
        """
        if not connection_string:
            return ""

        # Handle "DSN=<name>" format
        if connection_string.upper().startswith('DSN='):
            return connection_string[4:].strip()

        return connection_string.strip()

    @staticmethod
    def parse_ftp_connection_string(connection_string: str) -> dict:
        """
        Parse FTP connection string into components.

        Args:
            connection_string: Semicolon-delimited connection string
                              (e.g., "HOST=server;PORT=21;USER=user")

        Returns:
            Dictionary with parsed key-value pairs
        """
        params = {}
        if not connection_string:
            return params

        for param in connection_string.split(';'):
            param = param.strip()
            if '=' in param:
                key, value = param.split('=', 1)
                params[key.strip().upper()] = value.strip()

        return params


# Module-level convenience functions
def build_db2_connection(dsn: str) -> str:
    """Convenience function for DB2 connection strings"""
    return ConnectionStringBuilder.build_db2_dsn(dsn)


def build_access_connection(file_path: str) -> str:
    """Convenience function for Access connection strings"""
    return ConnectionStringBuilder.build_access(file_path)


def build_sql_server_connection(
    server: str,
    database: str,
    auth_type: str = 'WINDOWS',
    username: Optional[str] = None,
    password: Optional[str] = None
) -> str:
    """Convenience function for SQL Server connection strings"""
    return ConnectionStringBuilder.build_sql_server(
        server, database, auth_type, username, password
    )


def parse_ftp_params(connection_string: str) -> dict:
    """Convenience function for parsing FTP connection strings"""
    return ConnectionStringBuilder.parse_ftp_connection_string(connection_string)
