"""
Unique Value Registry — SQLite-backed storage for discovered unique field values.

Stores unique values and their counts for table.column combinations,
allowing quick reference without re-querying the database.
"""
from __future__ import annotations

import logging
import sqlite3
from datetime import datetime
from pathlib import Path

import pyodbc

logger = logging.getLogger(__name__)

_DB_DIR = Path.home() / ".suiteview"
_DB_PATH = _DB_DIR / "unique_value_registry.db"

_DSN = "UL_Rates"


def _get_conn() -> sqlite3.Connection:
    """Return a connection to the registry database, creating tables if needed."""
    _DB_DIR.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(_DB_PATH))
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS registrations (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            table_name  TEXT    NOT NULL,
            column_name TEXT    NOT NULL,
            display_name TEXT,
            updated_at  TEXT    NOT NULL,
            UNIQUE(table_name, column_name)
        );
        CREATE TABLE IF NOT EXISTS unique_values (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            registration_id INTEGER NOT NULL,
            value           TEXT,
            count           INTEGER NOT NULL DEFAULT 0,
            FOREIGN KEY (registration_id) REFERENCES registrations(id)
                ON DELETE CASCADE
        );
        CREATE INDEX IF NOT EXISTS idx_uv_reg
            ON unique_values(registration_id);
    """)
    return conn


# ── Public API ───────────────────────────────────────────────────────────


def fetch_and_register(table_name: str, column_name: str,
                       display_name: str = "") -> list[tuple[str, int]]:
    """Query unique values from the live database and store them.

    Returns a list of (value, count) tuples sorted by count descending.
    """
    sql = (
        f"SELECT [{column_name}] AS val, COUNT(*) AS cnt "
        f"FROM [{table_name}] "
        f"GROUP BY [{column_name}] "
        f"ORDER BY cnt DESC"
    )
    logger.info("Unique value query: %s", sql)

    conn_odbc = pyodbc.connect(f"DSN={_DSN}")
    cursor = conn_odbc.cursor()
    cursor.execute(sql)
    rows = [(str(r[0]) if r[0] is not None else "(NULL)", r[1])
            for r in cursor.fetchall()]
    conn_odbc.close()

    # Store in SQLite
    now = datetime.now().isoformat(timespec="seconds")
    conn = _get_conn()
    try:
        # Upsert registration
        conn.execute(
            "INSERT INTO registrations (table_name, column_name, display_name, updated_at) "
            "VALUES (?, ?, ?, ?) "
            "ON CONFLICT(table_name, column_name) DO UPDATE SET "
            "  display_name=excluded.display_name, updated_at=excluded.updated_at",
            (table_name, column_name, display_name or column_name, now),
        )
        reg_id = conn.execute(
            "SELECT id FROM registrations WHERE table_name=? AND column_name=?",
            (table_name, column_name),
        ).fetchone()[0]

        # Replace all values
        conn.execute("DELETE FROM unique_values WHERE registration_id=?",
                     (reg_id,))
        conn.executemany(
            "INSERT INTO unique_values (registration_id, value, count) "
            "VALUES (?, ?, ?)",
            [(reg_id, v, c) for v, c in rows],
        )
        conn.commit()
    finally:
        conn.close()

    return rows


def list_registrations() -> list[dict]:
    """Return all registered table/column combos with metadata.

    Each dict has keys: id, table_name, column_name, display_name,
    updated_at, value_count (number of distinct values stored).
    """
    conn = _get_conn()
    try:
        cursor = conn.execute("""
            SELECT r.id, r.table_name, r.column_name, r.display_name,
                   r.updated_at, COUNT(uv.id) AS value_count
            FROM registrations r
            LEFT JOIN unique_values uv ON uv.registration_id = r.id
            GROUP BY r.id
            ORDER BY r.table_name, r.column_name
        """)
        cols = [d[0] for d in cursor.description]
        return [dict(zip(cols, row)) for row in cursor.fetchall()]
    finally:
        conn.close()


def get_values(registration_id: int) -> list[tuple[str, int]]:
    """Return (value, count) pairs for a registration, sorted by count desc."""
    conn = _get_conn()
    try:
        rows = conn.execute(
            "SELECT value, count FROM unique_values "
            "WHERE registration_id=? ORDER BY count DESC",
            (registration_id,),
        ).fetchall()
        return [(r[0], r[1]) for r in rows]
    finally:
        conn.close()


def delete_registration(registration_id: int):
    """Remove a registration and all its values."""
    conn = _get_conn()
    try:
        conn.execute("DELETE FROM registrations WHERE id=?",
                     (registration_id,))
        conn.commit()
    finally:
        conn.close()
