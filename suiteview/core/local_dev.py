"""Local SQLite data sources for offline SuiteView development.

Enable only with ``SUITEVIEW_LOCAL_DATA=1``.  The local databases intentionally
keep the production table and field names so PolView and Illustration can
exercise the normal data-loading path without a work-network connection.
"""

from __future__ import annotations

import os
import sqlite3
from pathlib import Path


LOCAL_DATA_ENV = "SUITEVIEW_LOCAL_DATA"
LOCAL_POLICY_DB_ENV = "SUITEVIEW_LOCAL_POLICY_DB"
LOCAL_RATES_DB_ENV = "SUITEVIEW_LOCAL_RATES_DB"


def local_data_enabled() -> bool:
    """Return whether local SQLite data mode is explicitly enabled."""
    return os.environ.get(LOCAL_DATA_ENV) == "1"


def _require_local_data_enabled() -> None:
    if not local_data_enabled():
        raise RuntimeError(f"Local SuiteView data requires {LOCAL_DATA_ENV}=1")


def dev_data_dir() -> Path:
    """Default directory for generated local development databases."""
    return Path(__file__).resolve().parents[2] / "bundled_data" / "dev"


def local_policy_db_path() -> Path:
    """Path to the local policy-record SQLite database."""
    configured = os.environ.get(LOCAL_POLICY_DB_ENV)
    if configured:
        return Path(configured).expanduser()
    return dev_data_dir() / "policy_records.sqlite"


def local_rates_db_path() -> Path:
    """Path to the local UL rates SQLite database."""
    configured = os.environ.get(LOCAL_RATES_DB_ENV)
    if configured:
        return Path(configured).expanduser()
    return dev_data_dir() / "rates.sqlite"


def _sqlite_literal_path(path: Path) -> str:
    return "'" + str(path).replace("'", "''") + "'"


def connect_local_policy_database(region: str = "CKPR") -> sqlite3.Connection:
    """Return a SQLite connection shaped like the DB2 policy connection.

    The policy data file is attached as schema ``DB2TAB`` so existing SQL such
    as ``SELECT * FROM DB2TAB.LH_BAS_POL`` works unchanged.  A tiny in-memory
    ``SYSIBM.SYSDUMMY1`` schema supports the harmless DB2 WITH clause used by
    this codebase.
    """
    _require_local_data_enabled()
    path = local_policy_db_path()
    if not path.exists():
        raise FileNotFoundError(
            f"Local policy database not found: {path}. Run tools/create_local_dev_data.py."
        )

    conn = sqlite3.connect(":memory:")
    conn.execute(f"ATTACH DATABASE {_sqlite_literal_path(path)} AS DB2TAB")
    conn.execute("ATTACH DATABASE ':memory:' AS SYSIBM")
    conn.execute("CREATE TABLE IF NOT EXISTS SYSIBM.SYSDUMMY1 (IBMREQD TEXT)")
    conn.execute("DELETE FROM SYSIBM.SYSDUMMY1")
    conn.execute("INSERT INTO SYSIBM.SYSDUMMY1 (IBMREQD) VALUES ('Y')")
    conn.execute("PRAGMA foreign_keys = OFF")
    return conn


def connect_local_rates_database() -> sqlite3.Connection:
    """Return a SQLite connection for the local UL rates database."""
    _require_local_data_enabled()
    path = local_rates_db_path()
    if not path.exists():
        raise FileNotFoundError(
            f"Local rates database not found: {path}. Run tools/create_local_dev_data.py."
        )
    return sqlite3.connect(path)