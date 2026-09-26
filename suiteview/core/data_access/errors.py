"""Shared exceptions for SuiteView data adapters.

Adapters and repositories raise these exceptions. UI, command-worker, and
background-task boundaries catch them, log detail, and show a user-facing status
or dialog. Lower layers should not swallow them and substitute empty data.
"""

from __future__ import annotations


class SuiteViewDataError(RuntimeError):
    """Base class for data access, validation, and source availability errors."""


class ConnectionUnavailable(SuiteViewDataError, ConnectionError):
    """A configured local or live data source cannot be reached."""


class QueryFailed(SuiteViewDataError):
    """A data source accepted the connection but a query or command failed."""


class ReadOnlyViolation(SuiteViewDataError, PermissionError):
    """A write was requested where SuiteView only permits read access."""


class SourceValidationError(SuiteViewDataError, ValueError):
    """Input data, source schema, or an allowlisted identifier is invalid."""


class ExternalServiceUnavailable(ConnectionUnavailable):
    """A non-database external service such as FTP, Outlook, or SharePoint is unavailable."""


__all__ = [
    "SuiteViewDataError",
    "ConnectionUnavailable",
    "QueryFailed",
    "ReadOnlyViolation",
    "SourceValidationError",
    "ExternalServiceUnavailable",
]
