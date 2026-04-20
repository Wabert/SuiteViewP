"""
Shared Field Registry — SQL Server-backed storage for field definitions
and their unique values.

Tables: ABATBL_FIELD_REG, ABATBL_FIELD_VAL (created by
scripts/create_field_registry_tables.py).
"""
from __future__ import annotations

import getpass
import logging
from datetime import datetime

import pyodbc

logger = logging.getLogger(__name__)

_DSN = "UL_Rates"
_DATABASE = "UL_Rates"


def _connect() -> pyodbc.Connection:
    """Return a connection to the SQL Server registry database."""
    conn = pyodbc.connect(f"DSN={_DSN}")
    conn.autocommit = False
    return conn


def _user() -> str:
    """Return the current Windows username."""
    return getpass.getuser()


# ── Public API ───────────────────────────────────────────────────────


def _ensure_source_dsn_column() -> None:
    """Add source_dsn column to ABATBL_FIELD_REG if it doesn't exist yet."""
    conn = _connect()
    try:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT 1 FROM INFORMATION_SCHEMA.COLUMNS "
            "WHERE TABLE_NAME = 'ABATBL_FIELD_REG' AND COLUMN_NAME = 'source_dsn'"
        )
        if not cursor.fetchone():
            cursor.execute(
                "ALTER TABLE [ABATBL_FIELD_REG] ADD source_dsn VARCHAR(128) NULL"
            )
            conn.commit()
    except Exception:
        conn.rollback()
    finally:
        conn.close()


# Run once on import
_ensure_source_dsn_column()


def fetch_and_register(table_name: str, column_name: str,
                       display_name: str = "",
                       source_dsn: str = "") -> list[tuple[str, int]]:
    """Query unique values from the live database and store them.

    Parameters
    ----------
    source_dsn : str
        ODBC DSN to query the live data from.  When empty, defaults to
        the registry DSN (UL_Rates).  For DB2 tables, pass the DB2 DSN
        (e.g. "NEON_DSN").

    Upserts into ABATBL_FIELD_REG, then syncs ABATBL_FIELD_VAL:
      - New values are inserted (is_active=1, first_seen_at=now).
      - Existing values get updated counts, last_seen_at, is_active=1.
      - Values no longer found get is_active=0.

    Returns a list of (value, count) tuples sorted by count descending.
    """
    # 1. Query live unique values
    # Detect whether the target is DB2 (uses double-quote) or SQL Server
    # (uses [brackets]).  Heuristic: if source_dsn is set and differs from
    # the registry DSN we assume DB2.
    _is_db2 = bool(source_dsn) and source_dsn != _DSN

    def _q(name: str) -> str:
        """Quote an identifier for the target DBMS."""
        return f'"{name}"' if _is_db2 else f"[{name}]"

    if "." in table_name:
        parts = table_name.split(".")
        quoted_table = ".".join(_q(p) for p in parts)
    else:
        quoted_table = _q(table_name)
    sql = (
        f"SELECT {_q(column_name)} AS val, COUNT(*) AS cnt "
        f"FROM {quoted_table} "
        f"GROUP BY {_q(column_name)} "
        f"ORDER BY cnt DESC"
    )
    logger.info("Unique value query: %s (dsn=%s)", sql, source_dsn or _DSN)

    # Use source_dsn for the live query if provided, otherwise registry DSN
    live_dsn = source_dsn or _DSN
    live_conn = pyodbc.connect(f"DSN={live_dsn}", autocommit=True)
    try:
        cursor = live_conn.cursor()
        cursor.execute(sql)
        live_rows = [(str(r[0]) if r[0] is not None else "(NULL)", r[1])
                     for r in cursor.fetchall()]
    finally:
        live_conn.close()

    # 2. Store results in the registry (always on UL_Rates)
    conn = _connect()
    try:
        cursor = conn.cursor()

        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        user = _user()
        disp = display_name or column_name

        # Upsert ABATBL_FIELD_REG
        cursor.execute(
            "SELECT field_id FROM [ABATBL_FIELD_REG] "
            "WHERE database_name = ? AND table_name = ? AND column_name = ?",
            (_DATABASE, table_name, column_name),
        )
        row = cursor.fetchone()
        if row:
            field_id = row[0]
            cursor.execute(
                "UPDATE [ABATBL_FIELD_REG] SET "
                "  display_name = ?, last_scanned_at = ?, "
                "  source_dsn = ?, "
                "  updated_by = ?, updated_at = ? "
                "WHERE field_id = ?",
                (disp, now, source_dsn or None, user, now, field_id),
            )
        else:
            cursor.execute(
                "INSERT INTO [ABATBL_FIELD_REG] "
                "  (database_name, table_name, column_name, display_name, "
                "   last_scanned_at, source_dsn, "
                "   created_by, created_at, updated_by, updated_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (_DATABASE, table_name, column_name, disp,
                 now, source_dsn or None, user, now, user, now),
            )
            cursor.execute("SELECT @@IDENTITY")
            field_id = int(cursor.fetchone()[0])

        # 3. Sync ABATBL_FIELD_VAL
        # Get existing values for this field
        cursor.execute(
            "SELECT value_id, field_value FROM [ABATBL_FIELD_VAL] "
            "WHERE field_id = ?", (field_id,),
        )
        existing = {r[1]: r[0] for r in cursor.fetchall()}  # value → value_id

        live_values = set()
        for val, cnt in live_rows:
            live_values.add(val)
            if val in existing:
                # Update existing row
                cursor.execute(
                    "UPDATE [ABATBL_FIELD_VAL] SET "
                    "  occurrence_count = ?, is_active = 1, "
                    "  last_seen_at = ?, updated_by = ?, updated_at = ? "
                    "WHERE value_id = ?",
                    (cnt, now, user, now, existing[val]),
                )
            else:
                # Insert new value
                cursor.execute(
                    "INSERT INTO [ABATBL_FIELD_VAL] "
                    "  (field_id, field_value, occurrence_count, is_active, "
                    "   first_seen_at, last_seen_at, "
                    "   created_by, created_at, updated_by, updated_at) "
                    "VALUES (?, ?, ?, 1, ?, ?, ?, ?, ?, ?)",
                    (field_id, val, cnt, now, now, user, now, user, now),
                )

        # Mark values not found in this scan as inactive
        missing = set(existing.keys()) - live_values
        if missing:
            placeholders = ",".join("?" for _ in missing)
            cursor.execute(
                f"UPDATE [ABATBL_FIELD_VAL] SET is_active = 0, "
                f"  updated_by = ?, updated_at = ? "
                f"WHERE field_id = ? AND field_value IN ({placeholders})",
                [user, now, field_id] + list(missing),
            )

        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()

    return live_rows


def list_registrations() -> list[dict]:
    """Return all registered fields with metadata.

    Each dict has keys: field_id, database_name, table_name, column_name,
    display_name, last_scanned_at, value_count, source_dsn.
    """
    conn = _connect()
    try:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT r.field_id, r.database_name, r.table_name, r.column_name,
                   r.display_name, r.last_scanned_at, r.source_dsn,
                   (SELECT COUNT(*) FROM [ABATBL_FIELD_VAL] v
                    WHERE v.field_id = r.field_id AND v.is_active = 1) AS value_count
            FROM [ABATBL_FIELD_REG] r
            WHERE r.is_active = 1
            ORDER BY r.table_name, r.column_name
        """)
        cols = [d[0] for d in cursor.description]
        return [dict(zip(cols, row)) for row in cursor.fetchall()]
    finally:
        conn.close()


def get_values(field_id: int) -> list[tuple[str, int]]:
    """Return (value, count) pairs for a field, sorted by count desc.

    Only returns active values (is_active = 1).
    """
    conn = _connect()
    try:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT field_value, occurrence_count "
            "FROM [ABATBL_FIELD_VAL] "
            "WHERE field_id = ? AND is_active = 1 "
            "ORDER BY occurrence_count DESC",
            (field_id,),
        )
        return [(r[0], r[1]) for r in cursor.fetchall()]
    finally:
        conn.close()


def get_values_full(field_id: int, include_inactive: bool = False) -> list[dict]:
    """Return all value details for a field.

    Each dict has keys: value_id, field_value, value_description,
    is_active, occurrence_count, first_seen_at, last_seen_at, notes,
    created_by, created_at, updated_by, updated_at.
    """
    conn = _connect()
    try:
        cursor = conn.cursor()
        sql = (
            "SELECT value_id, field_value, value_description, is_active, "
            "  occurrence_count, first_seen_at, last_seen_at, notes, "
            "  created_by, created_at, updated_by, updated_at "
            "FROM [ABATBL_FIELD_VAL] "
            "WHERE field_id = ? "
        )
        if not include_inactive:
            sql += "AND is_active = 1 "
        sql += "ORDER BY occurrence_count DESC"
        cursor.execute(sql, (field_id,))
        cols = [d[0] for d in cursor.description]
        return [dict(zip(cols, row)) for row in cursor.fetchall()]
    finally:
        conn.close()


def update_value(value_id: int, *, value_description: str | None = ...,
                 notes: str | None = ...) -> None:
    """Update description and/or notes for a value row."""
    parts = []
    params = []
    sentinel = ...
    if value_description is not sentinel:
        parts.append("value_description = ?")
        params.append(value_description)
    if notes is not sentinel:
        parts.append("notes = ?")
        params.append(notes)
    if not parts:
        return
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    user = _user()
    parts.extend(["updated_by = ?", "updated_at = ?"])
    params.extend([user, now, value_id])
    conn = _connect()
    try:
        cursor = conn.cursor()
        cursor.execute(
            f"UPDATE [ABATBL_FIELD_VAL] SET {', '.join(parts)} "
            f"WHERE value_id = ?", params,
        )
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def add_value(field_id: int, field_value: str,
              value_description: str = "", notes: str = "") -> int:
    """Manually add a value entry. Returns the new value_id."""
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    user = _user()
    conn = _connect()
    try:
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO [ABATBL_FIELD_VAL] "
            "  (field_id, field_value, value_description, occurrence_count, "
            "   is_active, first_seen_at, last_seen_at, notes, "
            "   created_by, created_at, updated_by, updated_at) "
            "VALUES (?, ?, ?, 0, 1, ?, ?, ?, ?, ?, ?, ?)",
            (field_id, field_value, value_description or None,
             now, now, notes or None, user, now, user, now),
        )
        cursor.execute("SELECT @@IDENTITY")
        vid = int(cursor.fetchone()[0])
        conn.commit()
        return vid
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def deactivate_value(value_id: int) -> None:
    """Set a value to inactive (is_active = 0)."""
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    user = _user()
    conn = _connect()
    try:
        cursor = conn.cursor()
        cursor.execute(
            "UPDATE [ABATBL_FIELD_VAL] SET is_active = 0, "
            "  updated_by = ?, updated_at = ? "
            "WHERE value_id = ?",
            (user, now, value_id),
        )
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def get_field_id(table_name: str, column_name: str) -> int | None:
    """Return the field_id for a table/column combo, or None."""
    conn = _connect()
    try:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT field_id FROM [ABATBL_FIELD_REG] "
            "WHERE database_name = ? AND table_name = ? AND column_name = ?",
            (_DATABASE, table_name, column_name),
        )
        row = cursor.fetchone()
        return row[0] if row else None
    finally:
        conn.close()


def delete_registration(field_id: int):
    """Soft-delete a registration (set is_active = 0)."""
    conn = _connect()
    try:
        cursor = conn.cursor()
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        user = _user()
        cursor.execute(
            "UPDATE [ABATBL_FIELD_REG] SET is_active = 0, "
            "  updated_by = ?, updated_at = ? "
            "WHERE field_id = ?",
            (user, now, field_id),
        )
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def permanently_delete_field(field_id: int) -> None:
    """Permanently delete a field registration and all its values."""
    conn = _connect()
    try:
        cursor = conn.cursor()
        cursor.execute(
            "DELETE FROM [ABATBL_FIELD_VAL] WHERE field_id = ?",
            (field_id,),
        )
        cursor.execute(
            "DELETE FROM [ABATBL_FIELD_REG] WHERE field_id = ?",
            (field_id,),
        )
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def permanently_delete_table(table_name: str) -> None:
    """Permanently delete all field registrations and values for a table."""
    conn = _connect()
    try:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT field_id FROM [ABATBL_FIELD_REG] "
            "WHERE table_name = ? AND database_name = ?",
            (table_name, _DATABASE),
        )
        field_ids = [row[0] for row in cursor.fetchall()]
        for fid in field_ids:
            cursor.execute(
                "DELETE FROM [ABATBL_FIELD_VAL] WHERE field_id = ?",
                (fid,),
            )
        cursor.execute(
            "DELETE FROM [ABATBL_FIELD_REG] "
            "WHERE table_name = ? AND database_name = ?",
            (table_name, _DATABASE),
        )
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def list_table_columns(dsn: str, table_name: str) -> list[tuple[str, str, int, str]]:
    """Return all columns for a table from the ODBC driver.

    Parameters
    ----------
    dsn : str
        ODBC DSN name to connect to.
    table_name : str
        Fully-qualified table name (e.g. ``DB2TAB.LH_BAS_POL``).

    Returns a list of (column_name, type_name, column_size, nullable)
    tuples.
    """
    parts = table_name.split(".", 1)
    schema, table = (parts[0], parts[1]) if len(parts) == 2 else (None, parts[0])
    live_dsn = dsn or _DSN
    conn = pyodbc.connect(f"DSN={live_dsn}", autocommit=True, timeout=15)
    try:
        cursor = conn.cursor()
        columns = []
        for row in cursor.columns(table=table, schema=schema):
            columns.append((
                row.column_name,
                row.type_name,
                row.column_size,
                "Yes" if row.nullable else "No",
            ))
        return columns
    finally:
        conn.close()


def preview_table_rows(dsn: str, table_name: str,
                       max_rows: int = 1000) -> tuple[list[str], list[tuple]]:
    """Return the first *max_rows* rows from a table.

    Parameters
    ----------
    dsn : str
        ODBC DSN name.
    table_name : str
        Fully-qualified table name.
    max_rows : int
        Maximum number of rows to return.

    Returns ``(column_names, rows)`` where *rows* is a list of tuples.
    """
    from suiteview.core.odbc_utils import detect_dialect, DB2

    live_dsn = dsn or _DSN
    dialect = detect_dialect(live_dsn)

    # Quote identifiers per dialect
    if dialect == DB2:
        def _q(name: str) -> str:
            return f'"{name}"'
    else:
        def _q(name: str) -> str:
            return f"[{name}]"

    if "." in table_name:
        parts = table_name.split(".")
        quoted_table = ".".join(_q(p) for p in parts)
    else:
        quoted_table = _q(table_name)

    if dialect == DB2:
        sql = f"SELECT * FROM {quoted_table} FETCH FIRST {max_rows} ROWS ONLY"
    else:
        sql = f"SELECT TOP {max_rows} * FROM {quoted_table}"

    conn = pyodbc.connect(f"DSN={live_dsn}", autocommit=True, timeout=30)
    try:
        cursor = conn.cursor()
        cursor.execute(sql)
        col_names = [d[0] for d in cursor.description]
        rows = cursor.fetchall()
        return col_names, [tuple(r) for r in rows]
    finally:
        conn.close()
