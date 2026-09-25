"""Read-only, evidence-recording connection for agent ABR rate retrieval.

Queries and mappings remain in ABROdbcDatabase; this layer only rejects unsafe
operations/missing inputs and records SQL, parameters and result fingerprints.
"""
from contextlib import contextmanager
from hashlib import sha256
import json
import logging
import threading


class _Cursor:
    def __init__(self, cursor, evidence, product_type):
        self._cursor = cursor
        self._evidence = evidence
        self._product_type = product_type
        self._entry = None
        self._digest = None

    def execute(self, sql, params=()):
        from .automation import QuoteError, _json_value
        if not sql.lstrip().upper().startswith("SELECT "):
            raise QuoteError("ABR agent rate connection permits SELECT only")
        self._entry = {"sql": sql, "parameters": _json_value(list(params)),
                       "row_count": 0, "rows_sha256": None}
        self._digest = sha256()
        self._evidence.append(self._entry)
        self._cursor.execute(sql, params)
        return self

    def _record(self, rows):
        from .automation import QuoteError, _json_value
        sql = self._entry["sql"].upper()
        required = "SV_ABR_STATE_VARIATIONS" in sql
        if self._product_type == "TERM":
            required = required or any(table in sql for table in (
                "[TERM_POINT_PV]", "[TERM_POINT_PVSRB]", "[TERM_RATE_BANDSPECS]",
                "[TERM_RATE_MODEFACT]", "[TERM_POINT_BENEFIT]",
            ))
        if required and not rows:
            raise QuoteError(f"Required ABR source rows missing: {self._entry['sql']}")
        if rows and "SV_ABR_STATE_VARIATIONS" in sql and rows[0][0] is None:
            raise QuoteError("State admin fee is null; no default fee permitted")
        if rows and self._product_type == "TERM" and "[TERM_POINT_PV]" in sql:
            if any(value is None for value in rows[0]):
                raise QuoteError("Term product pointer/fee is null; no fallback permitted")
        for row in rows:
            encoded = json.dumps(_json_value(list(row)), sort_keys=True,
                                 default=str, allow_nan=False).encode("utf-8")
            self._digest.update(encoded + b"\n")
        self._entry["row_count"] += len(rows)
        self._entry["rows_sha256"] = self._digest.hexdigest()
        return rows

    def fetchone(self):
        row = self._cursor.fetchone()
        self._record([] if row is None else [row])
        return row

    def fetchall(self):
        return self._record(self._cursor.fetchall())

    def __iter__(self):
        return iter(self.fetchall())

    def close(self):
        self._cursor.close()


class _Connection:
    def __init__(self, connection, evidence, product_type):
        self._connection = connection
        self._evidence = evidence
        self._product_type = product_type

    def cursor(self):
        return _Cursor(self._connection.cursor(), self._evidence, self._product_type)

    def close(self):
        self._connection.close()


def open_rate_database(product_type):
    """New per-request connection/caches; no reuse of stale rate singleton."""
    from suiteview.core.odbc_utils import connect_dsn
    from .models.abr_odbc_database import ABROdbcDatabase
    db = ABROdbcDatabase()
    evidence = []
    connection = connect_dsn(
        "UL_Rates", autocommit=False, timeout=None, readonly=True,
    )
    db._conn = _Connection(connection, evidence, product_type)
    return db, evidence


@contextmanager
def capture_lookup_warnings(logger_name):
    """Capture this thread's source diagnostics without installing file handlers."""
    thread_id = threading.get_ident()
    failures = []

    class Capture(logging.Handler):
        def emit(self, record):
            if record.thread == thread_id and record.levelno >= logging.WARNING:
                failures.append(record.getMessage())

    logger = logging.getLogger(logger_name)
    handler = Capture()
    logger.addHandler(handler)
    try:
        yield failures
    finally:
        logger.removeHandler(handler)


@contextmanager
def reject_lookup_warnings(logger_name):
    """Distinguish lookup failure from the UI's '(none)' fallback."""
    from .automation import QuoteError
    with capture_lookup_warnings(logger_name) as failures:
        yield
    if failures:
        raise QuoteError("Lookup failed; default result rejected: " + "; ".join(failures))
