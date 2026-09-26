"""Core data-access helpers for live sources.

Profile SQLite storage remains under :mod:`suiteview.data`; this package owns
connections to live ODBC/File data sources and shared adapter exceptions.
"""

from suiteview.core.data_access.connections import (
    ConnectionFactory,
    NamedSource,
    connection_factory,
)
from suiteview.core.data_access.errors import (
    ConnectionUnavailable,
    ExternalServiceUnavailable,
    QueryFailed,
    ReadOnlyViolation,
    SourceValidationError,
    SuiteViewDataError,
)
from suiteview.core.data_access.executors import ReadOnlyExecutor, WriteUnitOfWork

__all__ = [
    "ConnectionFactory",
    "NamedSource",
    "connection_factory",
    "ReadOnlyExecutor",
    "WriteUnitOfWork",
    "SuiteViewDataError",
    "ConnectionUnavailable",
    "QueryFailed",
    "ReadOnlyViolation",
    "SourceValidationError",
    "ExternalServiceUnavailable",
]
