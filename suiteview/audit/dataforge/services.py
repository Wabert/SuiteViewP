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
    run_manual_sql,
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
    """Run the visual design as the same DuckDB SQL shown/exported to users."""
    sql, column_sources = compile_forge_sql(
        {name: list(frame.columns) for name, frame in datasets.items()},
        joins,
        filters=filters,
        outputs=outputs,
        appends=appends,
        limit=limit,
    )
    result = run_manual_sql(datasets, sql)
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
    DataFrames are registered under their user-facing names, so compiled
    visual SQL and Manual-mode SQL use one execution path.
    """
    lines = list(load_lines)
    lines.extend([
        "",
        "# ── Run DataForge SQL with DuckDB ───────────────────────────",
        "con = duckdb.connect()",
    ])
    for name in source_names:
        safe = name.replace('"', '\\"')
        lines.append(f'con.register("{safe}", df_{_var_name(name)})')
    lines.extend([
        'result = con.execute("""',
        sql.replace('"""', '\\"""'),
        '""").df()',
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
