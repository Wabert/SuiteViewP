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


def get_dsn_details(dsn: str) -> dict[str, str]:
    """Read ODBC DSN connection properties from the Windows registry.

    Returns a dict with keys like Driver, Server, Database, Host,
    Port Number, Subsystem, Description, etc. — whatever the DSN has
    configured.  Returns ``{"DSN": dsn, "Error": ...}`` on failure.
    """
    import winreg

    details: dict[str, str] = {"DSN": dsn}

    # Try User DSN first, then System DSN
    reg_paths = [
        (winreg.HKEY_CURRENT_USER, rf"SOFTWARE\ODBC\ODBC.INI\{dsn}"),
        (winreg.HKEY_LOCAL_MACHINE, rf"SOFTWARE\ODBC\ODBC.INI\{dsn}"),
    ]

    for hive, path in reg_paths:
        try:
            with winreg.OpenKey(hive, path) as key:
                i = 0
                while True:
                    try:
                        name, value, _ = winreg.EnumValue(key, i)
                        if name and value:
                            details[name] = str(value)
                        i += 1
                    except OSError:
                        break
                if len(details) > 1:
                    details["Scope"] = (
                        "User DSN" if hive == winreg.HKEY_CURRENT_USER
                        else "System DSN")
                    return details
        except OSError:
            continue

    # Also attempt to read the driver name from pyodbc.dataSources()
    try:
        sources = pyodbc.dataSources()
        driver = sources.get(dsn, "")
        if driver:
            details["Driver"] = driver
    except Exception:
        pass

    if len(details) <= 1:
        details["Error"] = "DSN not found in ODBC registry"

    return details
