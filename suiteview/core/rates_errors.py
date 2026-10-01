"""Rate lookup errors shared by the dbo ``Rates`` reader and the schema ``rates`` readers."""

from __future__ import annotations

from .data_access.errors import QueryFailed


class RatesError(QueryFailed):
    """Exception for rate lookup errors."""


def is_query_timeout(error: Exception) -> bool:
    """ODBC SQLSTATE HYT00 (query timeout expired)."""
    args = getattr(error, "args", ()) or ()
    return (bool(args) and str(args[0]).upper() == "HYT00") or "HYT00" in str(error)
