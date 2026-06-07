"""
DataForge engine — compiles a Forge (Sources + joins + filters + output
selection) into a single DuckDB SQL statement and runs it against in-memory
Snapshots.

This module is deliberately self-contained: it has **no PyQt / app
dependencies** and operates only on plain DataFrames and the small spec
dataclasses below. That keeps it unit-testable off the work laptop (no live
DB2/SQL Server needed) and makes it the reusable core that both the Visual
Builder (which compiles the canvas into these specs) and Manual mode (which
hands raw SQL straight to DuckDB) sit on top of.

Vocabulary (see DATAFORGE_DESIGN.md): a **Forge** combines several **Queries**
as **Sources**; each Source carries a **Snapshot** (the DataFrame passed here).
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

import duckdb
import pandas as pd

# How values map to DuckDB join keywords.
_JOIN_SQL = {
    "inner": "INNER JOIN",
    "left": "LEFT JOIN",
    "right": "RIGHT JOIN",
    "outer": "FULL OUTER JOIN",
    "full": "FULL OUTER JOIN",
    "cross": "CROSS JOIN",
}


@dataclass(frozen=True)
class JoinSpec:
    """One join between two Sources, by alias, on one or more key pairs.

    Multiple key pairs = a multi-column (AND-ed) join, e.g. join on both
    company_code and policy_number.
    """
    left_source: str
    right_source: str
    left_keys: tuple[str, ...]
    right_keys: tuple[str, ...]
    how: str = "inner"

    def __post_init__(self):
        if len(self.left_keys) != len(self.right_keys):
            raise ForgeEngineError(
                f"Join {self.left_source}->{self.right_source}: left_keys and "
                f"right_keys must be the same length "
                f"({len(self.left_keys)} != {len(self.right_keys)}).")
        if self.how not in _JOIN_SQL:
            raise ForgeEngineError(
                f"Unknown join type {self.how!r}; expected one of "
                f"{sorted(_JOIN_SQL)}.")


@dataclass(frozen=True)
class FilterSpec:
    """A filter on a single column.

    ``source`` names the Source whose (CTE) column this targets. Filters apply
    inside each Source's CTE, so they restrict a Source *before* it joins —
    which keeps outer-join semantics correct and mirrors the snapshot/pushdown
    model in the design doc (a Source filter shrinks that Source's Snapshot).

    Modes mirror the existing ForgeFilterTab: contains | regex | range | list,
    plus a convenience ``equals``.
    """
    source: str
    column: str
    mode: str = "contains"
    value: str = ""
    lo: str = ""
    hi: str = ""
    items: tuple[str, ...] = ()


@dataclass(frozen=True)
class OutputColumn:
    """One column in the Forge output, qualified by its Source alias."""
    source: str
    column: str
    alias: str | None = None  # output name; defaults to collision-safe name


@dataclass
class ForgeResult:
    """Result of running a Forge: the data plus the SQL that produced it."""
    dataframe: pd.DataFrame
    sql: str
    column_sources: dict[str, tuple[str, str]] = field(default_factory=dict)
    # output column name -> (source alias, original column)


class ForgeEngineError(Exception):
    """Raised for malformed Forge specs or SQL compilation problems."""


# ── Identifier / literal quoting ─────────────────────────────────────────

def _qi(identifier: str) -> str:
    """Quote a SQL identifier (double quotes, doubled internal quotes)."""
    return '"' + str(identifier).replace('"', '""') + '"'


def _ql(value: str) -> str:
    """Quote a SQL string literal (single quotes, doubled internal quotes)."""
    return "'" + str(value).replace("'", "''") + "'"


def _looks_numeric(text: str) -> bool:
    try:
        float(text)
        return True
    except (TypeError, ValueError):
        return False


# ── Filter compilation ───────────────────────────────────────────────────

def _filter_to_sql(filt: FilterSpec, table: str) -> str | None:
    """Compile a FilterSpec into a SQL predicate against ``table``.

    ``table`` is the already-quoted relation alias the column lives in.
    Returns None when the filter is effectively empty (no-op).
    """
    col = f"{table}.{_qi(filt.column)}"
    col_txt = f"CAST({col} AS VARCHAR)"
    mode = filt.mode

    if mode == "contains":
        if not filt.value:
            return None
        # Faithful to pandas str.contains(literal): substring, case-insensitive.
        # Escape LIKE wildcards so the value is matched literally.
        esc = filt.value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        return f"{col_txt} ILIKE {_ql('%' + esc + '%')} ESCAPE '\\'"

    if mode == "regex":
        if not filt.value:
            return None
        return f"regexp_matches({col_txt}, {_ql(filt.value)}, 'i')"

    if mode == "equals":
        if not filt.value:
            return None
        return f"{col_txt} = {_ql(filt.value)}"

    if mode == "range":
        parts = []
        if filt.lo:
            rhs = filt.lo if _looks_numeric(filt.lo) else _ql(filt.lo)
            parts.append(f"{col} >= {rhs}")
        if filt.hi:
            rhs = filt.hi if _looks_numeric(filt.hi) else _ql(filt.hi)
            parts.append(f"{col} <= {rhs}")
        return " AND ".join(parts) if parts else None

    if mode == "list":
        items = [i for i in filt.items if i != ""]
        if not items:
            return None
        joined = ", ".join(_ql(i) for i in items)
        return f"{col_txt} IN ({joined})"

    raise ForgeEngineError(f"Unknown filter mode {mode!r}.")


# ── Join ordering ─────────────────────────────────────────────────────────

def _ordered_joins(joins: list[JoinSpec], sources: list[str]
                   ) -> tuple[list[str], list[tuple[JoinSpec, str, str]]]:
    """Resolve join order into a left-deep sequence.

    Returns (placed_order, steps) where each step is
    (join, new_source, anchor_source): ``new_source`` gets joined onto the
    already-placed ``anchor_source``. Joins between two already-placed sources
    become extra ON predicates on that step's join (multi-path joins).

    Raises ForgeEngineError if a join references an unknown source or the graph
    is disconnected (a source that never connects to the placed set).
    """
    src_set = set(sources)
    for j in joins:
        for s in (j.left_source, j.right_source):
            if s not in src_set:
                raise ForgeEngineError(
                    f"Join references unknown Source {s!r}; "
                    f"known Sources: {sorted(src_set)}.")

    if not joins:
        return ([sources[0]] if sources else []), []

    remaining = list(joins)
    first = remaining.pop(0)
    placed = [first.left_source, first.right_source]
    steps: list[tuple[JoinSpec, str, str]] = [
        (first, first.right_source, first.left_source)]

    # Greedily attach remaining joins that connect to the placed set.
    progress = True
    while remaining and progress:
        progress = False
        for j in list(remaining):
            l_in = j.left_source in placed
            r_in = j.right_source in placed
            if l_in and r_in:
                # Extra predicate between two placed tables: attach to the
                # step that introduced the later of the two.
                steps.append((j, j.right_source, j.left_source))
                remaining.remove(j)
                progress = True
            elif l_in or r_in:
                new = j.right_source if l_in else j.left_source
                anchor = j.left_source if l_in else j.right_source
                steps.append((j, new, anchor))
                placed.append(new)
                remaining.remove(j)
                progress = True

    if remaining:
        bad = remaining[0]
        raise ForgeEngineError(
            f"Join {bad.left_source}->{bad.right_source} does not connect to "
            f"the rest of the Forge (disconnected join graph).")

    return placed, steps


def _swap_how(how: str) -> str:
    """Mirror a join type for a flipped attach order.

    ``A LEFT JOIN B`` is equivalent to ``B RIGHT JOIN A``. When the join chain
    attaches a join's *left* Source onto a chain that already holds its *right*
    Source, the LEFT/RIGHT keyword must be swapped or the null-padded side
    inverts. inner / full-outer / cross are symmetric and unchanged.
    """
    return {"left": "right", "right": "left"}.get(how, how)


def _join_on_clause(join: JoinSpec) -> str:
    """Build the ON predicate (multi-key AND-ed) for a JoinSpec."""
    left_t = _qi(join.left_source)
    right_t = _qi(join.right_source)
    conds = [
        f"{left_t}.{_qi(lk)} = {right_t}.{_qi(rk)}"
        for lk, rk in zip(join.left_keys, join.right_keys)
    ]
    return " AND ".join(conds)


# ── Output column resolution ──────────────────────────────────────────────

def _resolve_outputs(
    sources: list[str],
    schemas: dict[str, list[str]],
    outputs: list[OutputColumn] | None,
) -> tuple[list[str], dict[str, tuple[str, str]]]:
    """Return (select_exprs, column_sources).

    When ``outputs`` is None, select every column from every Source in join
    order, giving collision-safe output names (``col`` when unique so far,
    else ``col__alias``).
    """
    select_exprs: list[str] = []
    column_sources: dict[str, tuple[str, str]] = {}
    seen: dict[str, str] = {}  # output name -> source that claimed it

    def add(src: str, col: str, want: str | None):
        if want:
            out_name = want
        else:
            out_name = col if col not in seen else f"{col}__{src}"
            # In the unlikely event the suffixed name also collides, disambiguate.
            n = 2
            base = out_name
            while out_name in seen:
                out_name = f"{base}_{n}"
                n += 1
        if out_name in seen:
            raise ForgeEngineError(
                f"Duplicate output column name {out_name!r} "
                f"(from {src}.{col} and {seen[out_name]}).")
        seen[out_name] = f"{src}.{col}"
        column_sources[out_name] = (src, col)
        select_exprs.append(f"{_qi(src)}.{_qi(col)} AS {_qi(out_name)}")

    if outputs:
        for oc in outputs:
            if oc.source not in schemas:
                raise ForgeEngineError(
                    f"Output references unknown Source {oc.source!r}.")
            if oc.column not in schemas[oc.source]:
                raise ForgeEngineError(
                    f"Output column {oc.source}.{oc.column} not found in "
                    f"that Source's Snapshot.")
            add(oc.source, oc.column, oc.alias)
    else:
        for src in sources:
            for col in schemas[src]:
                add(src, col, None)

    return select_exprs, column_sources


# ── Main entry point ───────────────────────────────────────────────────────

_IDENT_RE = re.compile(r"\W+")


def compile_forge_sql(
    schemas: dict[str, list[str]],
    joins: list[JoinSpec],
    *,
    filters: list[FilterSpec] = (),
    result_filters: list[FilterSpec] = (),
    outputs: list[OutputColumn] | None = None,
    limit: int | None = None,
    physical_names: dict[str, str] | None = None,
) -> tuple[str, dict[str, tuple[str, str]]]:
    """Compile a Forge into one DuckDB SQL string. Pure (no execution).

    ``schemas`` maps Source alias -> ordered column names.
    ``filters`` are **Source-scope**: applied inside each Source's CTE (before
    the join). ``result_filters`` are **Result-scope**: applied to the joined,
    aliased output — each FilterSpec's ``column`` is an *output* column name
    (its ``source`` is ignored). ``physical_names`` maps Source alias -> the
    registered DuckDB table name; defaults to the alias itself.
    Returns (sql, column_sources).
    """
    sources = list(schemas.keys())
    if not sources:
        raise ForgeEngineError("A Forge needs at least one Source.")
    physical_names = physical_names or {s: s for s in sources}

    # Group filters by Source so each Source's CTE carries its own predicates.
    filters_by_source: dict[str, list[FilterSpec]] = {s: [] for s in sources}
    for f in filters:
        if f.source not in filters_by_source:
            raise ForgeEngineError(
                f"Filter references unknown Source {f.source!r}.")
        filters_by_source[f.source].append(f)

    # Build a CTE per Source: SELECT * FROM <physical> [WHERE <source filters>].
    ctes = []
    for src in sources:
        phys = _qi(physical_names[src])
        preds = [p for p in (_filter_to_sql(f, phys)
                             for f in filters_by_source[src]) if p]
        where = f" WHERE {' AND '.join(preds)}" if preds else ""
        ctes.append(f"{_qi(src)} AS (SELECT * FROM {phys}{where})")
    with_clause = "WITH " + ",\n     ".join(ctes)

    # FROM / JOIN chain.
    placed, steps = _ordered_joins(list(joins), sources)
    residual_preds: list[str] = []
    if not steps:
        from_clause = f"FROM {_qi(placed[0])}"
    else:
        first_join = steps[0][0]
        base = first_join.left_source
        lines = [f"FROM {_qi(base)}"]
        already_joined: set[str] = {base}
        for join, new, anchor in steps:
            if new in already_joined:
                # Multi-path join: both tables already joined, so there is no
                # new table to attach. Apply the extra key equality as a
                # residual WHERE predicate — only valid for inner joins, since
                # a top-level WHERE on the keys would filter out the null rows
                # an outer join is meant to keep.
                if join.how not in ("inner",):
                    raise ForgeEngineError(
                        f"Join {join.left_source}->{join.right_source} closes a "
                        f"join cycle (both Sources already joined) with "
                        f"how={join.how!r}; only inner joins are supported on "
                        f"such extra edges. Remove the redundant relationship "
                        f"or make it inner.")
                residual_preds.append(_join_on_clause(join))
                continue
            # If we are attaching the join's LEFT Source onto a chain that holds
            # its RIGHT Source, mirror LEFT/RIGHT so the correct side is kept.
            how = _swap_how(join.how) if new == join.left_source else join.how
            kw = _JOIN_SQL[how]
            lines.append(f"{kw} {_qi(new)} ON {_join_on_clause(join)}")
            already_joined.add(new)
        from_clause = "\n".join(lines)

    select_exprs, column_sources = _resolve_outputs(sources, schemas, outputs)
    select_clause = "SELECT\n  " + ",\n  ".join(select_exprs)

    sql = f"{with_clause}\n{select_clause}\n{from_clause}"
    if residual_preds:
        sql += "\nWHERE " + " AND ".join(residual_preds)

    # Result-scope filters apply to the joined, aliased output. WHERE cannot
    # reference SELECT aliases, so wrap the join in an outer SELECT whose
    # columns are the output names.
    if result_filters:
        outer = "_forge"
        preds = []
        for rf in result_filters:
            if rf.column not in column_sources:
                raise ForgeEngineError(
                    f"Result filter references unknown output column "
                    f"{rf.column!r}; available: {sorted(column_sources)}.")
            p = _filter_to_sql(rf, _qi(outer))
            if p:
                preds.append(p)
        if preds:
            sql = (f"SELECT * FROM (\n{sql}\n) AS {_qi(outer)}"
                   f"\nWHERE " + " AND ".join(preds))

    if limit is not None and int(limit) > 0:
        sql += f"\nLIMIT {int(limit)}"
    return sql, column_sources


def run_forge(
    sources: dict[str, pd.DataFrame],
    joins: list[JoinSpec],
    *,
    filters: list[FilterSpec] = (),
    result_filters: list[FilterSpec] = (),
    outputs: list[OutputColumn] | None = None,
    limit: int | None = None,
    connection: "duckdb.DuckDBPyConnection | None" = None,
) -> ForgeResult:
    """Execute a Forge against in-memory Snapshots and return a ForgeResult.

    ``sources`` maps Source alias -> Snapshot DataFrame. Each DataFrame is
    registered as a DuckDB virtual table, then the compiled SQL runs once.
    See :func:`compile_forge_sql` for the filter scopes.
    """
    if not sources:
        raise ForgeEngineError("A Forge needs at least one Source.")

    own_conn = connection is None
    con = connection or duckdb.connect()
    try:
        # Register each Snapshot under a safe physical name to avoid clashes
        # with the clean CTE aliases.
        physical_names: dict[str, str] = {}
        schemas: dict[str, list[str]] = {}
        for alias, df in sources.items():
            phys = "_src_" + _IDENT_RE.sub("_", alias)
            con.register(phys, df)
            physical_names[alias] = phys
            schemas[alias] = list(df.columns)

        sql, column_sources = compile_forge_sql(
            schemas, joins,
            filters=filters, result_filters=result_filters,
            outputs=outputs, limit=limit,
            physical_names=physical_names,
        )
        result_df = con.execute(sql).df()
        return ForgeResult(
            dataframe=result_df, sql=sql, column_sources=column_sources)
    finally:
        if own_conn:
            con.close()
