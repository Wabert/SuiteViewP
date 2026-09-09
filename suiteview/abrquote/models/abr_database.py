"""
ABR Quote — database access for actuarial rate data.

All rate data is stored in the shared UL_Rates SQL Server database,
accessed via the UL_Rates ODBC DSN.  See abr_odbc_database.py for
the data access layer and table definitions.
"""

import logging
from contextlib import contextmanager
from contextvars import ContextVar

logger = logging.getLogger(__name__)

# ── Singleton ───────────────────────────────────────────────────────────

_abr_db = None
_quote_database = ContextVar("abr_quote_database", default=None)


@contextmanager
def using_quote_database(database):
    """Scope a read-only quote data source without replacing the UI singleton."""
    token = _quote_database.set(database)
    try:
        yield
    finally:
        _quote_database.reset(token)


def get_abr_database():
    """Get or create the singleton ABR database instance.

    Uses the UL_Rates ODBC DSN (shared SQL Server database).
    """
    scoped = _quote_database.get()
    if scoped is not None:
        return scoped
    global _abr_db
    if _abr_db is not None:
        return _abr_db

    from .abr_odbc_database import ABROdbcDatabase
    _abr_db = ABROdbcDatabase()
    logger.info("ABR database: using ODBC backend (UL_Rates DSN)")
    return _abr_db
