"""Service helpers for DataForge run and script-export boundaries.

The widget owns PyQt state; this module owns the non-visual operations that
should stay identical across the Run button, runtime tests and generated
Python export.  The contract is the DuckDB engine in :mod:`forge_engine`.
"""
from __future__ import annotations

import pandas as pd

from .forge_engine import (
    AppendSpec,
    FilterSpec,
    ForgeResult,
    JoinSpec,
    OutputColumn,
    compile_forge_sql,
    registered_source_name,
    run_forge,
)


def run_visual_forge(
    datasets: dict[str, pd.DataFrame],
    joins: list[JoinSpec],
    *,
    filters: list[FilterSpec] = (),
    outputs: list[OutputColumn] | None = None,
    appends: list[AppendSpec] = (),
    limit: int | None = None,
) -> ForgeResult:
    """Run the visual design through the canonical DuckDB Forge executor."""
    result = run_forge(
        datasets,
        joins,
        filters=filters,
        outputs=outputs,
        appends=appends,
        limit=limit,
    )
    sql, column_sources = compile_forge_sql(
        {name: list(frame.columns) for name, frame in datasets.items()},
        joins,
        filters=filters,
        outputs=outputs,
        appends=appends,
        limit=limit,
    )
    result.sql = sql
    result.column_sources = column_sources
    return result


def generate_duckdb_script(
    load_lines: list[str],
    source_names: list[str],
    sql: str,
    *,
    print_preview_rows: int = 20,
) -> str:
    """Build standalone Python that loads Sources and runs the engine SQL.

    ``sql`` is the same DuckDB statement shown in the Forge SQL tab.  Source
    DataFrames are registered under both their user-facing names and the
    engine's physical names, so exported visual SQL reproduces the app run.
    """
    lines = list(load_lines)
    lines.extend([
        "",
        "# ── Run DataForge SQL with DuckDB ───────────────────────────",
        "con = duckdb.connect()",
    ])
    for name in source_names:
        var_name = f"df_{_var_name(name)}"
        lines.append(f"con.register({name!r}, {var_name})")
        physical = registered_source_name(name)
        if physical != name:
            lines.append(f"con.register({physical!r}, {var_name})")
    lines.extend([
        f"result = con.execute({sql!r}).df()",
        "con.close()",
        "",
        "print(f'Result: {result.shape[0]} rows x {result.shape[1]} columns')",
        f"print(result.head({int(print_preview_rows)}))",
    ])
    return "\n".join(lines)


def _var_name(name: str) -> str:
    """Convert a Source name to the same safe variable suffix the UI uses."""
    import re

    return re.sub(r"[^a-zA-Z0-9_]", "_", name).strip("_").lower() or "data"
