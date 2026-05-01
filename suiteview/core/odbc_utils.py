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


def _friendly_odbc_error(exc: Exception) -> str:
    """Extract a human-readable message from a pyodbc exception."""
    if hasattr(exc, 'args') and exc.args:
        # pyodbc.Error.args is typically (sqlstate, message)
        if len(exc.args) >= 2 and isinstance(exc.args[1], str):
            return exc.args[1]
        return str(exc.args[0]) if isinstance(exc.args[0], str) else str(exc)
    return str(exc)


def test_dsn_connection(dsn: str) -> tuple[bool, str]:
    """Test whether an ODBC DSN connection succeeds.

    Returns:
        (success, error_message) — *success* is True when the connection
        and a trivial query both succeed.  On failure *error_message*
        contains the driver/server error text.
    """
    try:
        conn = pyodbc.connect(f"DSN={dsn}", autocommit=True)
        conn.execute("SELECT 1 FROM SYSIBM.SYSDUMMY1")
        conn.close()
        return True, ""
    except pyodbc.Error as exc:
        return False, _friendly_odbc_error(exc)
    except Exception as exc:
        return False, str(exc)


def is_password_error(error_message: str) -> bool:
    """Heuristic: does the ODBC error look like a connection/auth failure?

    Intentionally broad — any ODBC connect failure against a DSN with
    stored credentials is almost always a stale password.
    """
    markers = [
        "08001",          # SQLSTATE: Unable to connect
        "08S01",          # Communication link failure
        "28000",          # SQLSTATE: Invalid authorization
        "SQL30082",       # DB2 security processing failure
        "password",
        "credential",
        "authentication",
        "not authorized",
        "logon denied",
        "signon",
        "failed to connect",   # DB2ConnectionError message
        "communication link",
        "connection failure",
        "pyodbc",              # raw pyodbc errors
        "odbc",                # general ODBC failures
    ]
    lower = error_message.lower()
    return any(m.lower() in lower for m in markers)


def update_dsn_password(dsn: str, new_password: str) -> tuple[bool, str]:
    """Update the password stored in an ODBC User/System DSN registry entry.

    Tries User DSN first (HKCU), then System DSN (HKLM).
    Returns (success, message).
    """
    import winreg

    reg_paths = [
        (winreg.HKEY_CURRENT_USER, rf"SOFTWARE\ODBC\ODBC.INI\{dsn}"),
        (winreg.HKEY_LOCAL_MACHINE, rf"SOFTWARE\ODBC\ODBC.INI\{dsn}"),
    ]

    for hive, path in reg_paths:
        try:
            with winreg.OpenKey(hive, path, 0, winreg.KEY_SET_VALUE) as key:
                winreg.SetValueEx(key, "Password", 0, winreg.REG_SZ, new_password)
                scope = "User DSN" if hive == winreg.HKEY_CURRENT_USER else "System DSN"
                return True, f"Password updated for {dsn} ({scope})"
        except PermissionError:
            continue
        except OSError:
            continue

    return False, f"Could not find or update registry entry for DSN '{dsn}'"
