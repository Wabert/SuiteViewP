"""
Source tokens for Visual Query tables — one vocabulary for picker, canvas and runner.

A Visual Query table belongs to exactly one source:

* an ODBC DSN (``NEON_DSN``), whose tables are named ``SCHEMA.TABLE``;
* a saved File Source, identified by the token ``file:<id>``, whose member files
  are each a table named after the member; or
* a policy list pasted from the clipboard (``list:<table>``), stored inside the
  query itself.

The query keeps ``table_sources`` for file and list tables; every other table
belongs to the query's ODBC DSN. These helpers are the only place that knows the
token formats and how to read a File Source's stored schema.
"""
from __future__ import annotations

FILE_TOKEN_PREFIX = "file:"
# Pasted policy lists live inside the query config: ``list:<table>``.
LIST_TOKEN_PREFIX = "list:"
# Dragging table names out of SQL Assist (newline-separated names).
TABLE_DRAG_MIME = "application/x-audit-table-drag"


def is_file_token(source: str) -> bool:
    return str(source or "").startswith(FILE_TOKEN_PREFIX)


def is_list_token(source: str) -> bool:
    return str(source or "").startswith(LIST_TOKEN_PREFIX)


def is_local_token(source: str) -> bool:
    """File datasets and pasted lists — tables SuiteView loads itself (not ODBC)."""
    return is_file_token(source) or is_list_token(source)


def list_token(table: str) -> str:
    return f"{LIST_TOKEN_PREFIX}{table}"


def file_token(file_source) -> str:
    return f"{FILE_TOKEN_PREFIX}{file_source.id}"


def resolve_file_token(token: str):
    """The FileDataSource for ``file:<id>`` (None when missing or not a token)."""
    if not is_file_token(token):
        return None
    from suiteview.audit import file_query_runner

    return file_query_runner.resolve_file_source(token[len(FILE_TOKEN_PREFIX):])


def file_source_label(file_source) -> str:
    from suiteview.audit.file_source import datasource_label

    return f"{file_source.name} [{datasource_label(file_source)}]"


def file_source_badge(file_source) -> str:
    from suiteview.audit.file_source import datasource_label

    return datasource_label(file_source).upper()


def file_source_table_fields(file_source) -> dict[str, list[tuple[str, str]]]:
    """Map each File Source member table to its stored [(column, type), ...]."""
    return {
        member.resolved_table_name(): [(col.name, col.data_type) for col in file_source.columns]
        for member in file_source.members
    }


def list_file_tables() -> list[tuple[str, str, str]]:
    """Every saved File Source member as (source label, token, table name)."""
    from suiteview.audit import file_source_store

    rows: list[tuple[str, str, str]] = []
    for fds in file_source_store.list_file_sources():
        label = file_source_label(fds)
        token = file_token(fds)
        for table in file_source_table_fields(fds):
            rows.append((label, token, table))
    return rows
