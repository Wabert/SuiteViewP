"""Allowlisted SQL identifier formatting.

Values belong in query parameters. Only schema, table and column identifiers go
through these helpers, and callers should pass allowlisted names whenever they
come from UI or files.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Mapping

from suiteview.core.odbc_utils import ACCESS, DB2, DUCKDB, SQL_SERVER

_BRACKET_DIALECTS = {SQL_SERVER, ACCESS, "sqlserver", "sql_server", "mssql", "access"}
_DOUBLE_QUOTE_DIALECTS = {DB2, DUCKDB, "sqlite", "postgresql", "postgres", "duckdb"}


def _normalize_dialect(dialect: str | None) -> str:
    return (dialect or SQL_SERVER).lower()


def _validate_identifier(name: str) -> str:
    text = str(name or "").strip()
    if not text:
        raise ValueError("SQL identifier cannot be blank.")
    if "\x00" in text:
        raise ValueError("SQL identifier cannot contain NUL.")
    if "." in text:
        raise ValueError("Pass multipart identifiers to qualified_name().")
    return text


def quote_identifier(name: str, dialect: str | None = SQL_SERVER) -> str:
    """Quote a single schema, table or column identifier for *dialect*."""
    text = _validate_identifier(name)
    normalized = _normalize_dialect(dialect)
    if normalized in {value.lower() for value in _DOUBLE_QUOTE_DIALECTS}:
        return '"' + text.replace('"', '""') + '"'
    if normalized in {value.lower() for value in _BRACKET_DIALECTS}:
        return "[" + text.replace("]", "]]") + "]"
    return "[" + text.replace("]", "]]") + "]"


def qualified_name(
    schema: str | None,
    table: str,
    dialect: str | None = SQL_SERVER,
) -> str:
    """Return a quoted one- or two-part table name."""
    table_name = quote_identifier(table, dialect)
    if schema:
        return f"{quote_identifier(schema, dialect)}.{table_name}"
    return table_name


def limit_clause(limit: int, dialect: str | None = SQL_SERVER) -> str:
    """Return a dialect-specific trailing row-limit clause, where supported."""
    value = int(limit)
    if value < 1:
        raise ValueError("SQL row limit must be positive.")
    normalized = _normalize_dialect(dialect)
    if normalized in {"db2"}:
        return f"FETCH FIRST {value} ROWS ONLY"
    if normalized in {"db2_limit", "db2_shadow"}:
        return f"LIMIT {value}"
    if normalized in {"duckdb", "sqlite", "postgres", "postgresql"}:
        return f"LIMIT {value}"
    return ""


def top_clause(limit: int, dialect: str | None = SQL_SERVER) -> str:
    """Return a SQL Server/Access SELECT TOP clause fragment, including space."""
    value = int(limit)
    if value < 1:
        raise ValueError("SQL row limit must be positive.")
    normalized = _normalize_dialect(dialect)
    if normalized in {"sql_server", "sqlserver", "mssql", "access"}:
        return f"TOP {value} "
    return ""


@dataclass(frozen=True)
class IdentifierCatalog:
    """Allowlist for table and column identifiers."""

    tables: frozenset[str]
    columns_by_table: Mapping[str, frozenset[str]]
    dialect: str = SQL_SERVER

    @classmethod
    def from_tables(
        cls,
        tables: Iterable[str],
        columns_by_table: Mapping[str, Iterable[str]] | None = None,
        *,
        dialect: str = SQL_SERVER,
    ) -> "IdentifierCatalog":
        column_map = {
            table: frozenset(columns)
            for table, columns in (columns_by_table or {}).items()
        }
        return cls(frozenset(tables), column_map, dialect)

    def require_table(self, table: str) -> str:
        """Validate and return an allowlisted table name."""
        if table not in self.tables:
            raise ValueError(f"SQL table is not allowlisted: {table!r}")
        return table

    def require_column(self, table: str, column: str) -> str:
        """Validate and return an allowlisted column name for *table*."""
        self.require_table(table)
        columns = self.columns_by_table.get(table)
        if columns is not None and column not in columns:
            raise ValueError(f"SQL column is not allowlisted for {table}: {column!r}")
        return column

    def quote_table(self, table: str, schema: str | None = None) -> str:
        """Validate and quote a table name."""
        return qualified_name(schema, self.require_table(table), self.dialect)

    def quote_column(self, table: str, column: str) -> str:
        """Validate and quote a column name."""
        return quote_identifier(self.require_column(table, column), self.dialect)
