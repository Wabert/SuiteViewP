"""Scan a DB2 region for LH_/TH_ tables and detect which ones the current
login cannot ``SELECT`` from.

Lists every table in the DB2 catalog (``SYSIBM.SYSTABLES``) whose name starts
with ``LH_`` or ``TH_`` under the region's schema, then attempts a lightweight
one-row ``SELECT`` against each one to see whether the current login actually
has read access.  Tables that raise an insufficient-privilege error
(SQLCODE ``-551`` / SQLSTATE ``42501``) -- or any other error -- are reported as
not accessible.

Shared by the ``tools/policyrecord/scan_db2_table_access.py`` script and the taskbar's
"DB2 Table Check" window so the classification logic lives in exactly one place.
"""
from __future__ import annotations

from typing import Callable, Optional

from .db2_connection import DB2Connection
from .db2_constants import REGION_SCHEMA_MAP, DEFAULT_SCHEMA, DEFAULT_REGION

# Signature: progress(done: int, total: int, table: str) -> None
ProgressCallback = Callable[[int, int, str], None]


def _sqlstate(exc: BaseException) -> str:
    """Best-effort extraction of the ODBC SQLSTATE from a pyodbc error."""
    args = getattr(exc, "args", ())
    if args and isinstance(args[0], str):
        return args[0]
    return ""


def _clean_error(exc: BaseException) -> str:
    """Return a trimmed, NUL-free version of an ODBC driver message."""
    return str(exc).split("\x00", 1)[0].strip()


def list_lh_th_tables(db: DB2Connection, schema: str) -> list[str]:
    """Return sorted names of all LH_/TH_ base tables owned by *schema*.

    The schema is filtered via ``CREATOR`` (not a ``DB2TAB.`` prefix) so the
    connection's schema-rewrite logic leaves this catalog query untouched.
    """
    catalog_sql = (
        "SELECT NAME FROM SYSIBM.SYSTABLES "
        f"WHERE CREATOR = '{schema}' AND TYPE = 'T' "
        "AND (NAME LIKE 'LH\\_%' ESCAPE '\\' OR NAME LIKE 'TH\\_%' ESCAPE '\\') "
        "ORDER BY NAME"
    )
    rows = db.execute_query(catalog_sql)
    return [str(r[0]).strip() for r in rows]


def scan_table_access(
    region: str = DEFAULT_REGION,
    progress: Optional[ProgressCallback] = None,
) -> dict:
    """Scan *region* and classify every LH_/TH_ table as accessible or not.

    Args:
        region: Region code (CKPR, CKMO, CKAS, CKCS, CKSR).
        progress: Optional callback invoked as ``progress(done, total, table)``
            after each table is probed -- useful for a UI progress bar.

    Returns:
        A dict with keys: ``region``, ``schema``, ``total``,
        ``accessible_count``, ``no_access_count``, ``no_access`` (list of
        ``{table, sqlstate, error}``) and ``accessible`` (list of table names).
    """
    region = region.upper()
    schema = REGION_SCHEMA_MAP.get(region, DEFAULT_SCHEMA)
    db = DB2Connection(region)

    table_names = list_lh_th_tables(db, schema)
    total = len(table_names)

    accessible: list[str] = []
    no_access: list[dict] = []

    for i, name in enumerate(table_names, start=1):
        probe_sql = f"SELECT * FROM {schema}.{name} FETCH FIRST 1 ROW ONLY"
        try:
            db.execute_query(probe_sql)
            accessible.append(name)
        except Exception as exc:  # noqa: BLE001 - diagnostic classification
            no_access.append({
                "table": name,
                "sqlstate": _sqlstate(exc),
                "error": _clean_error(exc)[:300],
            })
        if progress is not None:
            progress(i, total, name)

    return {
        "region": region,
        "schema": schema,
        "total": total,
        "accessible_count": len(accessible),
        "no_access_count": len(no_access),
        "no_access": no_access,
        "accessible": accessible,
    }
