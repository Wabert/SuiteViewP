"""Utilities for ODBC DSN introspection."""
from __future__ import annotations

import logging

import pyodbc

logger = logging.getLogger(__name__)

# Dialect constants (match ConnectionType values where applicable)
DB2 = "DB2"
SQL_SERVER = "SQL_SERVER"
ACCESS = "ACCESS"
UNKNOWN = "UNKNOWN"

# Driver-name substrings → dialect mapping (checked in order)
_DRIVER_HINTS: list[tuple[str, str]] = [
    ("db2", DB2),
    ("datadirect", DB2),
    ("data virtualization", DB2),
    ("shadow", DB2),
    ("sql server", SQL_SERVER),
    ("access", ACCESS),
]


def detect_dialect(dsn: str) -> str:
    """Return the SQL dialect for an ODBC DSN by inspecting its driver.

    Returns one of: ``DB2``, ``SQL_SERVER``, ``ACCESS``, ``UNKNOWN``.
    """
    try:
        sources = pyodbc.dataSources()
    except Exception:
        logger.warning("Could not read ODBC data sources")
        return UNKNOWN

    driver = sources.get(dsn, "")
    if not driver:
        logger.warning("DSN %r not found in ODBC data sources", dsn)
        return UNKNOWN

    driver_lower = driver.lower()
    for hint, dialect in _DRIVER_HINTS:
        if hint in driver_lower:
            return dialect

    logger.info("Unrecognised ODBC driver %r for DSN %r — defaulting to SQL_SERVER", driver, dsn)
    return SQL_SERVER
