"""
Dynamic SQL builder — generates SELECT queries from dynamic field filters.

Builds SQL for user-created groups based on the FieldRow widgets on the
active tab. Supports contains, regex, range, list, and combo filter modes.
Adapts SQL dialect (quoting, row limiting) based on the target backend.
"""
from __future__ import annotations

import logging
import re
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from suiteview.audit.common_table import CommonTable

logger = logging.getLogger(__name__)

# Dialect constants (re-exported from odbc_utils for convenience)
DB2 = "DB2"
SQL_SERVER = "SQL_SERVER"
ACCESS = "ACCESS"
DUCKDB = "DUCKDB"  # flat-file sources (File Source) run through DuckDB

# Dialects that quote identifiers with ANSI double quotes (vs square brackets).
_DOUBLE_QUOTE_DIALECTS = (DB2, DUCKDB)


def _escape(val: str) -> str:
    """Escape single quotes for SQL."""
    return val.replace("'", "''")


def _q(col: str, dialect: str = SQL_SERVER) -> str:
    """Quote a column identifier for the target dialect."""
    if dialect in _DOUBLE_QUOTE_DIALECTS:
        return f'"{col}"'
    # SQL_SERVER and ACCESS both use square brackets
    return f"[{col}]"


# A name safe to emit unquoted in any supported dialect.
_PLAIN_IDENT = re.compile(r"^[A-Za-z_][A-Za-z0-9_$#@]*$")


def _q_table(table_name: str, dialect: str = SQL_SERVER) -> str:
    """Quote a (possibly schema-qualified) table name for the target dialect.

    File Source tables are named after their files, so they can start with a
    digit or contain spaces (``07_2026_IUL_Fund_Values_RGA``) — DuckDB requires
    those to be double-quoted. Plain identifiers and already-quoted names pass
    through untouched, so existing DB2/SQL Server SQL is unchanged.
    """
    name = (table_name or "").strip()
    if not name or name.startswith('"') or name.startswith("["):
        return table_name
    if dialect == DUCKDB:
        # No schemas for file tables — the whole name is one identifier.
        return name if _PLAIN_IDENT.match(name) else _q(name, dialect)
    return ".".join(
        part if _PLAIN_IDENT.match(part) else _q(part, dialect)
        for part in name.split(".")
    )


def _alias(name: str, dialect: str = SQL_SERVER) -> str:
    """Quote a SELECT alias for the target dialect."""
    if dialect in _DOUBLE_QUOTE_DIALECTS:
        return f'"{name}"'
    return f"[{name}]"


def _aggregate_alias(aggregate: str, column: str) -> str:
    """Return a stable heading for aggregate result columns."""
    return f"{aggregate}_{column}"


def _order_by_clause(select_columns, expr_fn) -> str:
    """Build an ORDER BY clause from sorted select columns.

    Each spec may carry ``sort`` ("ASC"/"DESC") and ``sort_order`` (int).
    ``expr_fn(spec)`` returns the SQL expression to order by. Returns "" when
    no column requests a sort.
    """
    sortable = []
    for sc in (select_columns or []):
        direction = (sc.get("sort") or "").upper()
        if direction in ("ASC", "DESC"):
            sortable.append((sc.get("sort_order", 0) or 0, sc, direction))
    if not sortable:
        return ""
    sortable.sort(key=lambda t: t[0])
    terms = [f"{expr_fn(sc)} {direction}" for _, sc, direction in sortable]
    return "\nORDER BY " + ", ".join(terms)


def _select_prefix(top_clause: str, distinct: bool, dialect: str) -> str:
    if distinct and dialect != DB2:
        return f"DISTINCT {top_clause}"
    return f"{top_clause}{'DISTINCT ' if distinct else ''}"


def filter_conditions(filt: dict, qcol: str) -> list[str]:
    """Render one field filter as WHERE conditions against ``qcol``."""
    mode = filt.get("mode", "contains")
    val = str(filt.get("value", "") or "").strip()
    lo = str(filt.get("range_lo", "") or "").strip()
    hi = str(filt.get("range_hi", "") or "").strip()
    list_vals = filt.get("list_values", []) or []
    if mode == "not_null":
        # Federated queries: the filter already ran on the database table.
        return [f"{qcol} IS NOT NULL"]
    if mode == "contains" and val:
        return [f"{qcol} LIKE '%{_escape(val)}%'"]
    if mode == "regex" and val:
        return [f"{qcol} LIKE '{_escape(val)}'"]
    if mode == "combo" and val:
        return [f"{qcol} = '{_escape(val)}'"]
    if mode == "range":
        conds = []
        if lo:
            conds.append(f"{qcol} >= '{_escape(lo)}'")
        if hi:
            conds.append(f"{qcol} <= '{_escape(hi)}'")
        return conds
    if mode == "list" and list_vals:
        escaped = [f"'{_escape(str(v))}'" for v in list_vals]
        return [f"{qcol} IN ({', '.join(escaped)})"]
    return []


def split_field_key(field_key: str, known_tables=()) -> tuple[str, str]:
    """Split ``table.column`` into (table, column).

    Table names may be schema-qualified and file column names may contain dots
    (``SLR Output[Source.Name]``), so the longest known table prefix wins; the
    last dot is only a fallback when no table is known.
    """
    key = str(field_key or "")
    for table in sorted((t for t in known_tables if t), key=len, reverse=True):
        if key.startswith(table + "."):
            return table, key[len(table) + 1:]
    if "." not in key:
        return "", key
    table, column = key.rsplit(".", 1)
    return table, column


def _null_supplied(ji: dict) -> set[str]:
    """Tables on the optional (null-supplying) side of one join."""
    how = str(ji.get("join_type", "")).upper()
    if how.startswith("LEFT"):
        return {ji["right_table"]}
    if how.startswith("RIGHT"):
        return {ji["left_table"]}
    if how.startswith("FULL"):
        return {ji["left_table"], ji["right_table"]}
    return set()


def null_supplied_tables(join_infos: list[dict]) -> set[str]:
    tables: set[str] = set()
    for ji in join_infos:
        tables |= _null_supplied(ji)
    return tables


def find_outer_join_ambiguity(join_infos: list[dict]) -> tuple[str, str, str] | None:
    """(table, outer partner, inner partner) of an ambiguous outer join, if any.

    A table on the optional side of an outer join that is also INNER-joined to
    some other table (``A LEFT B``, ``B INNER C``) means ``A⟕(B⋈C)`` or
    ``(A⟕B)⋈C`` depending on which table the query starts from — different rows.
    """
    for outer in join_infos:
        for table in _null_supplied(outer):
            partner = outer["left_table"] if table == outer["right_table"] else outer["right_table"]
            for inner in join_infos:
                if inner is outer or not str(inner.get("join_type", "")).upper().startswith("INNER"):
                    continue
                if table in (inner["left_table"], inner["right_table"]):
                    other = inner["right_table"] if table == inner["left_table"] else inner["left_table"]
                    if other != partner:
                        return table, partner, other
    return None


def outer_join_ambiguity(join_infos: list[dict]) -> str:
    """Why the joins have no single meaning ("" when they do)."""
    found = find_outer_join_ambiguity(join_infos)
    if found is None:
        return ""
    table, partner, other = found
    return (
        f"{table} is on the optional side of its join with {partner} "
        f"but Inner-joined to {other}, so the result would depend on "
        f"which table the query starts from.\n\nOn the Joins tab, make "
        f"the join between {table} and {other} a Left join from "
        f"{table} (keep all {partner} rows), or make the join with "
        f"{partner} an Inner join.")


def choose_primary_table(used_tables: list[str], join_infos: list[dict],
                         fallback: str = "") -> str:
    """Pick the FROM table from the join graph.

    Prefer tables that are never on the optional side of an outer join (so the
    arrows on the canvas decide the result, not field order), then the first
    used table, then any joined table.
    """
    joined: list[str] = []
    for ji in join_infos:
        for table in (ji.get("left_table", ""), ji.get("right_table", "")):
            if table and table not in joined:
                joined.append(table)
    optional = null_supplied_tables(join_infos)
    preserved = [t for t in joined if t not in optional]
    for candidates in (preserved, joined):
        for table in used_tables:
            if table in candidates:
                return table
        if candidates:
            return candidates[0]
    if used_tables:
        return used_tables[0]
    return fallback


_FLIPPED_JOIN = {
    "LEFT JOIN": "RIGHT JOIN",
    "RIGHT JOIN": "LEFT JOIN",
    "LEFT OUTER JOIN": "RIGHT OUTER JOIN",
    "RIGHT OUTER JOIN": "LEFT OUTER JOIN",
}


def order_join_infos(primary_table: str, join_infos: list[dict]) -> list[dict]:
    """Orient joins so each one introduces a new table from the tables in scope.

    A join drawn from B to A (``B LEFT JOIN A``) with A already in the FROM
    scope is emitted as ``A RIGHT JOIN B`` — flipping the direction keeps the
    preserved side the user chose. A join whose two tables are both already in
    scope (a cycle) becomes extra ON conditions of the later join. Joins that
    cannot be reached from the primary table raise ``ValueError``.
    """
    in_scope = {primary_table}
    ordered: list[dict] = []
    pending = [dict(ji) for ji in join_infos]
    while pending:
        progressed = False
        for original in list(pending):
            ji = original
            lt, rt = ji["left_table"], ji["right_table"]
            if lt in in_scope and rt in in_scope:
                target = next(
                    (o for o in reversed(ordered)
                     if o["right_table"] in (lt, rt)), None)
                if target is None:
                    raise ValueError(
                        f"Join between {lt} and {rt} joins a table to itself.")
                target.setdefault("cross_pairs", []).extend(
                    (lt, lc, rt, rc) for lc, rc in ji.get("on_pairs", []))
            elif lt in in_scope or rt in in_scope:
                if rt in in_scope:
                    ji = {
                        **ji,
                        "left_table": rt,
                        "right_table": lt,
                        "alias_left": ji.get("alias_right", ""),
                        "alias_right": ji.get("alias_left", ""),
                        "join_type": _FLIPPED_JOIN.get(
                            ji.get("join_type", "INNER JOIN"),
                            ji.get("join_type", "INNER JOIN")),
                        "on_pairs": [(r, l) for l, r in ji.get("on_pairs", [])],
                    }
                ordered.append(ji)
                in_scope.add(ji["right_table"])
            else:
                continue
            pending.remove(original)
            progressed = True
        if not progressed:
            orphan = pending[0]
            raise ValueError(
                f"The join between {orphan['left_table']} and "
                f"{orphan['right_table']} is not connected to {primary_table}. "
                "Draw a join line that links every table on the Joins tab.")
    return ordered


def build_dynamic_sql(
    table_name: str,
    max_count: str,
    field_filters: list[dict],
    *,
    select_columns: list[dict] | None = None,
    display_all: bool = False,
    distinct: bool = False,
    dialect: str = DB2,
) -> str:
    """Build a SELECT statement for a dynamic group.

    Args:
        table_name: Fully qualified table name (schema.table or just table).
        max_count: Max rows to return (empty = no limit).
        field_filters: List of dicts with keys:
            - column: actual DB column name
            - mode: "contains" | "regex" | "range" | "list" | "combo"
            - value: str (for contains, regex, combo)
            - range_lo, range_hi: str (for range mode)
            - list_values: list[str] (for list mode)
        select_columns: List of dicts with keys:
            - column: actual DB column name
            - aggregate: "display" | "COUNT" | "SUM" | "MIN" | "MAX"
            - field_key: full qualified name (table.column)
        display_all: If True, SELECT * regardless of select_columns.
        dialect: SQL dialect — "DB2", "SQL_SERVER", or "ACCESS".

    Returns:
        SQL string.
    """
    q = lambda col: _q(col, dialect)
    wheres: list[str] = []

    for filt in field_filters:
        wheres.extend(filter_conditions(filt, q(filt["column"])))

    # Build row-limit clause (dialect-specific)
    top_clause = ""
    fetch_clause = ""
    if max_count:
        try:
            n = int(max_count)
            if n > 0:
                if dialect == DB2:
                    fetch_clause = f"\nFETCH FIRST {n} ROWS ONLY"
                elif dialect == DUCKDB:
                    fetch_clause = f"\nLIMIT {n}"
                else:
                    top_clause = f"TOP {n} "
        except ValueError:
            pass

    # Determine columns for SELECT
    if display_all or not select_columns:
        col_expr = "*"
    else:
        # Collect explicit select columns + any where-criteria columns
        seen: set[str] = set()
        parts: list[str] = []

        # Add explicit select columns (may have aggregates)
        for sc in (select_columns or []):
            col = sc["column"]
            agg = sc.get("aggregate", "display")
            if agg == "display":
                expr = q(col)
            else:
                expr = f"{agg}({q(col)}) AS {_alias(_aggregate_alias(agg, col), dialect)}"
            if expr not in seen:
                seen.add(expr)
                parts.append(expr)

        # Also include any where-criteria columns not already selected
        for filt in field_filters:
            col = filt["column"]
            qcol = q(col)
            if qcol not in seen:
                seen.add(qcol)
                parts.append(qcol)

        col_expr = ", ".join(parts) if parts else "*"

    # Check if we need GROUP BY (aggregates present)
    has_agg = False
    plain_cols: list[str] = []
    if select_columns and not display_all:
        for sc in select_columns:
            agg = sc.get("aggregate", "display")
            if agg != "display":
                has_agg = True
            else:
                plain_cols.append(q(sc["column"]))
        # Also include where-criteria plain columns for GROUP BY
        for filt in field_filters:
            qcol = q(filt["column"])
            if qcol not in plain_cols:
                plain_cols.append(qcol)

    sql = (f"SELECT {_select_prefix(top_clause, distinct, dialect)}{col_expr}"
           f"\nFROM {_q_table(table_name, dialect)}")
    if wheres:
        sql += "\nWHERE " + "\n  AND ".join(wheres)
    if has_agg and plain_cols:
        sql += "\nGROUP BY " + ", ".join(plain_cols)

    def _order_expr(sc):
        col = sc["column"]
        agg = sc.get("aggregate", "display")
        if agg == "display":
            return q(col)
        return _alias(_aggregate_alias(agg, col), dialect)

    sql += _order_by_clause(select_columns, _order_expr)
    sql += fetch_clause

    return sql


def collect_field_filters(field_grid) -> list[dict]:
    """Extract filter values from a FieldGrid's FieldRow widgets.

    Each FieldRow stores its column name in field_key (format: "table.column").
    Returns dicts with 'column' (bare name), 'field_key' (full key), and filter data.
    """
    filters = []
    for row in field_grid._rows:
        mode = row.mode
        col_name = row.field_key
        registry = getattr(row, "_registry_info", None)
        if registry and len(registry) > 1 and registry[1]:
            # The placed field knows its real column (may contain dots).
            actual_col = str(registry[1])
        else:
            actual_col = split_field_key(col_name)[1]

        filt = {"column": actual_col, "field_key": col_name, "mode": mode}

        if mode in ("contains", "regex", "combo"):
            val = row.get_value()
            if val:
                filt["value"] = val
                filters.append(filt)
        elif mode == "range":
            lo, hi = row.get_range()
            if lo or hi:
                filt["range_lo"] = lo
                filt["range_hi"] = hi
                filters.append(filt)
        elif mode == "list":
            vals = row.get_list_values()
            if vals:
                filt["list_values"] = vals
                filters.append(filt)

    return filters


# ── Join-aware SQL builder ───────────────────────────────────────────

def _table_alias(table_name: str, alias: str, dialect: str = SQL_SERVER) -> str:
    """Return 'table alias' or just 'table' if no alias."""
    quoted = _q_table(table_name, dialect)
    if alias:
        return f"{quoted} {alias}"
    return quoted


def _col_ref(alias: str, col: str, dialect: str) -> str:
    """Return alias.col or just col (quoted)."""
    q = lambda c: _q(c, dialect)
    if alias:
        return f"{alias}.{q(col)}"
    return q(col)


def _resolve_field_key(field_key: str, alias_map: dict[str, str],
                       dialect: str) -> str:
    """Resolve a field_key like 'schema.table.column' to a qualified ref.

    Uses alias_map to find the alias/table prefix (longest table name wins, so
    schema-qualified tables and dotted file column names both resolve).
    Returns alias.col or table.col (quoted appropriately).
    """
    q = lambda c: _q(c, dialect)
    table_name, col = split_field_key(field_key, alias_map.keys())
    if table_name in alias_map:
        alias = alias_map.get(table_name, "")
        if alias:
            return f"{alias}.{q(col)}"
        return f"{_q_table(table_name, dialect)}.{q(col)}"

    # Fallback: bare column (shouldn't happen with properly keyed fields)
    return q(col)


def build_join_sql(
    primary_table: str,
    max_count: str,
    field_filters: list[dict],
    *,
    join_infos: list[dict],
    select_columns: list[dict] | None = None,
    display_all: bool = False,
    distinct: bool = False,
    dialect: str = DB2,
) -> str:
    """Build a SELECT with JOIN clauses from join card info.

    Args:
        primary_table: The FROM table (first table in the group).
        max_count: Row limit.
        field_filters: WHERE filters from criteria tabs (include field_key).
        join_infos: List of dicts from JoinCard.get_join_info():
            - left_table, right_table, join_type
            - alias_left, alias_right
            - on_pairs: list of (left_col, right_col)
            - extra_conditions: list of (column, expression)
        select_columns: Display tab columns (include field_key).
        display_all: SELECT *.
        distinct: DISTINCT.
        dialect: SQL dialect.
    """
    q = lambda col: _q(col, dialect)
    ordered_joins = order_join_infos(primary_table, join_infos)

    # Build alias map: table → alias (or table short name)
    # Track which tables appear and their aliases
    alias_map: dict[str, str] = {}  # table_name → alias
    tables_seen: set[str] = {primary_table}

    # Primary table: check if any join references it with an alias
    primary_alias = ""
    for ji in join_infos:
        if ji["left_table"] == primary_table and ji["alias_left"]:
            primary_alias = ji["alias_left"]
            break
        if ji["right_table"] == primary_table and ji["alias_right"]:
            primary_alias = ji["alias_right"]
            break
    alias_map[primary_table] = primary_alias

    for ji in join_infos:
        lt = ji["left_table"]
        rt = ji["right_table"]
        al = ji["alias_left"]
        ar = ji["alias_right"]
        if lt not in alias_map:
            alias_map[lt] = al
        if rt not in alias_map:
            alias_map[rt] = ar
        tables_seen.add(lt)
        tables_seen.add(rt)

    # Helper to qualify a column from a field_key
    def _qualify(field_key: str, col: str) -> str:
        if field_key:
            return _resolve_field_key(field_key, alias_map, dialect)
        # No field_key — fall back to primary table qualification
        a = alias_map.get(primary_table, "")
        if a:
            return f"{a}.{q(col)}"
        return f"{_q_table(primary_table, dialect)}.{q(col)}"

    # ── WHERE clauses from field filters ─────────────────────────
    wheres: list[str] = []
    for filt in field_filters:
        qcol = _qualify(filt.get("field_key", ""), filt["column"])
        wheres.extend(filter_conditions(filt, qcol))

    # ── Row limit ────────────────────────────────────────────────
    top_clause = ""
    fetch_clause = ""
    if max_count:
        try:
            n = int(max_count)
            if n > 0:
                if dialect == DB2:
                    fetch_clause = f"\nFETCH FIRST {n} ROWS ONLY"
                elif dialect == DUCKDB:
                    fetch_clause = f"\nLIMIT {n}"
                else:
                    top_clause = f"TOP {n} "
        except ValueError:
            pass

    # ── SELECT columns ───────────────────────────────────────────
    if display_all or not select_columns:
        col_expr = "*"
    else:
        seen: set[str] = set()
        parts: list[str] = []
        for sc in (select_columns or []):
            col = sc["column"]
            fk = sc.get("field_key", "")
            agg = sc.get("aggregate", "display")
            qcol = _qualify(fk, col)
            if agg == "display":
                expr = qcol
            else:
                expr = f"{agg}({qcol}) AS {_alias(_aggregate_alias(agg, col), dialect)}"
            if expr not in seen:
                seen.add(expr)
                parts.append(expr)
        # Also include any where-criteria columns not already selected
        for filt in field_filters:
            col = filt["column"]
            fk = filt.get("field_key", "")
            qcol = _qualify(fk, col)
            if qcol not in seen:
                seen.add(qcol)
                parts.append(qcol)
        col_expr = ", ".join(parts) if parts else "*"

    # ── GROUP BY (if aggregates) ─────────────────────────────────
    has_agg = False
    plain_cols: list[str] = []
    if select_columns and not display_all:
        for sc in select_columns:
            agg = sc.get("aggregate", "display")
            fk = sc.get("field_key", "")
            col = sc["column"]
            if agg != "display":
                has_agg = True
            else:
                plain_cols.append(_qualify(fk, col))
        for filt in field_filters:
            fk = filt.get("field_key", "")
            col = filt["column"]
            qcol = _qualify(fk, col)
            if qcol not in plain_cols:
                plain_cols.append(qcol)

    # ── Build FROM + JOINs ───────────────────────────────────────
    from_expr = _table_alias(primary_table, primary_alias, dialect)

    def _ref(table: str, col: str) -> str:
        alias = alias_map.get(table, "")
        return (_col_ref(alias, col, dialect) if alias
                else f"{_q_table(table, dialect)}.{q(col)}")

    join_clauses: list[str] = []
    for ji in ordered_joins:
        lt = ji["left_table"]
        rt = ji["right_table"]
        join_target = _table_alias(rt, alias_map.get(rt, ji.get("alias_right", "")),
                                   dialect)
        on_parts = [f"{_ref(lt, left_col)} = {_ref(rt, right_col)}"
                    for left_col, right_col in ji["on_pairs"]]
        on_parts.extend(
            f"{_ref(ta, ca)} = {_ref(tb, cb)}"
            for ta, ca, tb, cb in ji.get("cross_pairs", []))

        # Extra conditions go into ON clause
        for col, expr in ji.get("extra_conditions", []):
            on_parts.append(f"{q(col)} {expr}")

        on_clause = " AND ".join(on_parts) if on_parts else "1 = 1"
        join_clauses.append(f"  {ji['join_type']} {join_target}\n    ON {on_clause}")

    # ── Assemble SQL ─────────────────────────────────────────────
    sql = f"SELECT {_select_prefix(top_clause, distinct, dialect)}{col_expr}"
    sql += f"\nFROM {from_expr}"
    for jc in join_clauses:
        sql += f"\n{jc}"
    if wheres:
        sql += "\nWHERE " + "\n  AND ".join(wheres)
    if has_agg and plain_cols:
        sql += "\nGROUP BY " + ", ".join(plain_cols)

    def _order_expr(sc):
        col = sc["column"]
        agg = sc.get("aggregate", "display")
        if agg == "display":
            return _qualify(sc.get("field_key", ""), col)
        return _alias(_aggregate_alias(agg, col), dialect)

    sql += _order_by_clause(select_columns, _order_expr)
    sql += fetch_clause

    return sql


# ── Common Table CTE generation ─────────────────────────────────────

def build_common_table_cte(
    tables: list[CommonTable],
    dialect: str = SQL_SERVER,
) -> str:
    """Render CommonTable objects as a WITH clause prefix.

    DB2 VALUES syntax:
        WITH TableName (col1, col2) AS (
            VALUES ('a', 'b'), ('c', 'd')
        )

    SQL Server VALUES syntax:
        WITH TableName (col1, col2) AS (
            SELECT * FROM (VALUES
                ('a', 'b'), ('c', 'd')
            ) AS t(col1, col2)
        )

    Returns empty string when *tables* is empty.
    """
    if not tables:
        return ""

    cte_parts: list[str] = []
    for ct in tables:
        col_names = ", ".join(c["name"] for c in ct.columns)

        # Format each row as a VALUES tuple
        row_strs: list[str] = []
        for row in ct.rows:
            vals: list[str] = []
            for i, col_def in enumerate(ct.columns):
                raw = row[i] if i < len(row) else ""
                ctype = col_def.get("type", "TEXT")
                if ctype in ("INTEGER", "DECIMAL") and raw != "":
                    vals.append(str(raw))
                else:
                    vals.append(f"'{_escape(str(raw))}'")
            row_strs.append(f"({', '.join(vals)})")

        values_block = ",\n        ".join(row_strs)

        if dialect in (DB2, DUCKDB):
            # DuckDB accepts the same `name (cols) AS (VALUES ...)` CTE form.
            cte = (
                f"{ct.name} ({col_names}) AS (\n"
                f"    VALUES {values_block}\n"
                f")"
            )
        else:
            # SQL Server / Access
            cte = (
                f"{ct.name} ({col_names}) AS (\n"
                f"    SELECT * FROM (VALUES\n"
                f"        {values_block}\n"
                f"    ) AS _t({col_names})\n"
                f")"
            )
        cte_parts.append(cte)

    return "WITH " + ",\n".join(cte_parts)
