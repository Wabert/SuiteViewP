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


class UnknownColumnError(SourceValidationError):
    """A loaded source table does not contain a requested column."""

    def __init__(
        self,
        table_name: str,
        column_name: str,
        *,
        available_columns: list[str] | tuple[str, ...] = (),
        policy_number: str | None = None,
    ) -> None:
        context = f" on policy {policy_number}" if policy_number else ""
        available = ", ".join(available_columns) if available_columns else "none"
        super().__init__(
            f"Column {table_name}.{column_name} is not present in the loaded table"
            f"{context}. Available columns: {available}"
        )
        self.table_name = table_name
        self.column_name = column_name
        self.available_columns = tuple(available_columns)
        self.policy_number = policy_number


class ExternalServiceUnavailable(ConnectionUnavailable):
    """A non-database external service such as FTP, Outlook, or SharePoint is unavailable."""


__all__ = [
    "ConnectionUnavailable",
    "ExternalServiceUnavailable",
    "QueryFailed",
    "ReadOnlyViolation",
    "SourceValidationError",
    "SuiteViewDataError",
    "UnknownColumnError",
]
