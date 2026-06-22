"""
Run queries against a FileDataSource via DuckDB.

This is the engine glue that lets the existing query builders treat a File
Source like a DSN: each member file is loaded into a DataFrame (reusing the
proven ``adhoc_source_intake`` readers — so fixed-width, delimited, and Excel
all work) and registered as a DuckDB table under its table name. The query —
whether hand-written (Manual) or compiled from the Visual designer with the
``DUCKDB`` dialect — then runs over those tables via the shared DataForge
engine (``forge_engine.run_manual_sql``). One engine, no new executor.

Each member is its OWN table (design decision 2026-06-22): a query references
``"CLAIMS"`` and ``"RGACLAIMS"`` separately and UNIONs them in SQL to combine.

Pure-ish: imports pandas/duckdb lazily through the readers and engine, so it
stays importable on the minipc; actual execution needs the local files only.
"""
from __future__ import annotations

from typing import TYPE_CHECKING

from suiteview.audit.adhoc_source_intake import dataframe_from_adhoc_metadata
from suiteview.audit.dataforge import forge_engine
from suiteview.audit.file_source import FileDataSource

if TYPE_CHECKING:
    import pandas as pd


def resolve_file_source(ref: str) -> FileDataSource | None:
    """Resolve a File Source by id (preferred) or name."""
    from suiteview.audit import file_source_store

    return (file_source_store.load_file_source_by_id(ref)
            or file_source_store.load_file_source(ref))


def load_source_tables(
    file_source: FileDataSource,
    table_names: list[str] | None = None,
) -> dict[str, "pd.DataFrame"]:
    """Load member files into DataFrames keyed by table name.

    ``table_names`` limits the load to specific member tables; None loads all.
    """
    wanted = set(table_names) if table_names is not None else None
    tables: dict[str, "pd.DataFrame"] = {}
    for member in file_source.members:
        name = member.resolved_table_name()
        if wanted is not None and name not in wanted:
            continue
        tables[name] = dataframe_from_adhoc_metadata(
            file_source.source_type, file_source.member_metadata(member))
    return tables


def run_sql(
    file_source: FileDataSource,
    sql: str,
    *,
    limit: int | None = 500,
    table_names: list[str] | None = None,
) -> forge_engine.ForgeResult:
    """Execute DuckDB SQL against a File Source's member tables.

    Returns a ``ForgeResult`` (``.dataframe`` + the executed ``.sql``). Raises
    ``ForgeEngineError`` if the source has no members or the SQL fails.
    """
    tables = load_source_tables(file_source, table_names)
    if not tables:
        raise forge_engine.ForgeEngineError(
            f"File Source {file_source.name!r} has no member files to query.")
    effective_limit = limit if (limit and int(limit) > 0) else None
    return forge_engine.run_manual_sql(tables, sql, limit=effective_limit)


def run_query(
    file_source: FileDataSource,
    sql: str,
    *,
    limit: int | None = 500,
    table_names: list[str] | None = None,
) -> tuple[list[str], list[tuple], dict[str, str]]:
    """Run a query and return an ODBC-shaped result for UI integration.

    Mirrors ``query_runner.execute_odbc_query_with_types``:
    ``(columns, rows, column_types)`` — so a File Source query can flow through
    the same result-rendering paths as a DB2 / SQL Server query.
    """
    df = run_sql(file_source, sql, limit=limit, table_names=table_names).dataframe
    columns = [str(c) for c in df.columns]
    column_types = {str(c): _dtype_label(df[c]) for c in df.columns}
    safe = df.astype(object).where(df.notnull(), None)
    rows = [tuple(row) for row in safe.to_numpy().tolist()]
    return columns, rows, column_types


def _dtype_label(series) -> str:
    """Map a pandas dtype to the TEXT/INTEGER/DECIMAL/DATE vocabulary."""
    import pandas as pd

    dtype = series.dtype
    if pd.api.types.is_bool_dtype(dtype):
        return "BOOLEAN"
    if pd.api.types.is_integer_dtype(dtype):
        return "INTEGER"
    if pd.api.types.is_float_dtype(dtype):
        return "DECIMAL"
    if pd.api.types.is_datetime64_any_dtype(dtype):
        return "DATE"
    return "TEXT"
