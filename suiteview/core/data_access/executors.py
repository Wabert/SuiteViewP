"""Small execution helpers for live data sources."""

from __future__ import annotations

from contextlib import closing
from typing import Any, Iterable

from suiteview.core.data_access.connections import ConnectionFactory, NamedSource, connection_factory
from suiteview.core.data_access.errors import QueryFailed


class ReadOnlyExecutor:
    """One-shot read executor for a named source."""

    def __init__(
        self,
        source: NamedSource | str,
        *,
        factory: ConnectionFactory = connection_factory,
        region: str | None = None,
        timeout: int | None = None,
    ):
        self.source = source
        self.factory = factory
        self.region = region
        self.timeout = timeout

    def fetchall(self, sql: str, params: Iterable[Any] = ()) -> tuple[list[str], list[tuple]]:
        """Execute a read-only query and return ``(columns, rows)``."""
        kwargs: dict[str, Any] = {
            "autocommit": True,
            "timeout": self.timeout,
            "readonly": True,
        }
        if self.region is not None:
            kwargs["region"] = self.region
        try:
            with closing(self.factory.connect_named(self.source, **kwargs)) as connection:
                cursor = connection.cursor()
                try:
                    cursor.execute(sql, tuple(params))
                    columns = [desc[0] for desc in cursor.description] if cursor.description else []
                    return columns, [tuple(row) for row in cursor.fetchall()]
                finally:
                    cursor.close()
        except Exception as exc:
            raise QueryFailed(f"Read-only query failed: {exc}") from exc


class WriteUnitOfWork:
    """Transactional write scope for a named source."""

    def __init__(
        self,
        source: NamedSource | str,
        *,
        factory: ConnectionFactory = connection_factory,
        region: str | None = None,
        timeout: int | None = None,
    ):
        self.source = source
        self.factory = factory
        self.region = region
        self.timeout = timeout
        self.connection = None

    def __enter__(self):
        kwargs: dict[str, Any] = {
            "autocommit": False,
            "timeout": self.timeout,
            "readonly": False,
        }
        if self.region is not None:
            kwargs["region"] = self.region
        self.connection = self.factory.connect_named(self.source, **kwargs)
        return self.connection

    def __exit__(self, exc_type, exc_value, traceback) -> None:
        if self.connection is None:
            return
        try:
            if exc_type is None:
                self.connection.commit()
            else:
                self.connection.rollback()
        finally:
            self.connection.close()
