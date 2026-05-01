"""
Dynamic SQL builder — generates SELECT queries from dynamic field filters.

Builds SQL for user-created groups based on the FieldRow widgets on the
active tab. Supports contains, regex, range, list, and combo filter modes.
Adapts SQL dialect (quoting, row limiting) based on the target backend.
"""
from __future__ import annotations

import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from suiteview.audit.common_table import CommonTable

logger = logging.getLogger(__name__)

# Dialect constants (re-exported from odbc_utils for convenience)
DB2 = "DB2"
SQL_SERVER = "SQL_SERVER"
ACCESS = "ACCESS"


def _escape(val: str) -> str:
    """Escape single quotes for SQL."""
    return val.replace("'", "''")


def _q(col: str, dialect: str = SQL_SERVER) -> str:
    """Quote a column identifier for the target dialect."""
    if dialect == DB2:
        return f'"{col}"'
    # SQL_SERVER and ACCESS both use square brackets
    return f"[{col}]"


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
        col = filt["column"]
        mode = filt.get("mode", "contains")
        val = filt.get("value", "").strip()
        lo = filt.get("range_lo", "").strip()
        hi = filt.get("range_hi", "").strip()
        list_vals = filt.get("list_values", [])

        if mode == "contains" and val:
            wheres.append(f"{q(col)} LIKE '%{_escape(val)}%'")
        elif mode == "regex" and val:
            wheres.append(f"{q(col)} LIKE '{_escape(val)}'")
        elif mode == "combo" and val:
            wheres.append(f"{q(col)} = '{_escape(val)}'")
        elif mode == "range":
            if lo:
                wheres.append(f"{q(col)} >= '{_escape(lo)}'")
            if hi:
                wheres.append(f"{q(col)} <= '{_escape(hi)}'")
        elif mode == "list" and list_vals:
            escaped = [f"'{_escape(v)}'" for v in list_vals]
            wheres.append(f"{q(col)} IN ({', '.join(escaped)})")

    # Build row-limit clause (dialect-specific)
    top_clause = ""
    fetch_clause = ""
    if max_count:
        try:
            n = int(max_count)
            if n > 0:
                if dialect == DB2:
                    fetch_clause = f"\nFETCH FIRST {n} ROWS ONLY"
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
                expr = f"{agg}({q(col)})"
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

    sql = f"SELECT {top_clause}{'DISTINCT ' if distinct else ''}{col_expr}\nFROM {table_name}"
    if wheres:
        sql += "\nWHERE " + "\n  AND ".join(wheres)
    if has_agg and plain_cols:
        sql += "\nGROUP BY " + ", ".join(plain_cols)
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
        # field_key may be "schema.table.column" — extract just column
        parts = col_name.split(".")
        actual_col = parts[-1] if parts else col_name

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

def _table_alias(table_name: str, alias: str) -> str:
    """Return 'table alias' or just 'table' if no alias."""
    if alias:
        return f"{table_name} {alias}"
    return table_name


def _col_ref(alias: str, col: str, dialect: str) -> str:
    """Return alias.col or just col (quoted)."""
    q = lambda c: _q(c, dialect)
    if alias:
        return f"{alias}.{q(col)}"
    return q(col)


def _resolve_field_key(field_key: str, alias_map: dict[str, str],
                       dialect: str) -> str:
    """Resolve a field_key like 'schema.table.column' to a qualified ref.

    Uses alias_map to find the alias/table prefix.  Returns alias.col or
    table.col (quoted appropriately).
    """
    q = lambda c: _q(c, dialect)
    parts = field_key.split(".")
    col = parts[-1]

    if len(parts) >= 2:
        # Try matching the full table name first (schema.table)
        if len(parts) == 3:
            table_name = f"{parts[0]}.{parts[1]}"
        else:
            table_name = parts[0]

        alias = alias_map.get(table_name, "")
        if alias:
            return f"{alias}.{q(col)}"
        if table_name in alias_map:
            return f"{table_name}.{q(col)}"

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
        return f"{primary_table}.{q(col)}"

    # ── WHERE clauses from field filters ─────────────────────────
    wheres: list[str] = []
    for filt in field_filters:
        col = filt["column"]
        fk = filt.get("field_key", "")
        mode = filt.get("mode", "contains")
        val = filt.get("value", "").strip()
        lo = filt.get("range_lo", "").strip()
        hi = filt.get("range_hi", "").strip()
        list_vals = filt.get("list_values", [])

        qcol = _qualify(fk, col)

        if mode == "contains" and val:
            wheres.append(f"{qcol} LIKE '%{_escape(val)}%'")
        elif mode == "regex" and val:
            wheres.append(f"{qcol} LIKE '{_escape(val)}'")
        elif mode == "combo" and val:
            wheres.append(f"{qcol} = '{_escape(val)}'")
        elif mode == "range":
            if lo:
                wheres.append(f"{qcol} >= '{_escape(lo)}'")
            if hi:
                wheres.append(f"{qcol} <= '{_escape(hi)}'")
        elif mode == "list" and list_vals:
            escaped = [f"'{_escape(v)}'" for v in list_vals]
            wheres.append(f"{qcol} IN ({', '.join(escaped)})")

    # ── Row limit ────────────────────────────────────────────────
    top_clause = ""
    fetch_clause = ""
    if max_count:
        try:
            n = int(max_count)
            if n > 0:
                if dialect == DB2:
                    fetch_clause = f"\nFETCH FIRST {n} ROWS ONLY"
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
                expr = f"{agg}({qcol})"
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
    from_expr = _table_alias(primary_table, primary_alias)

    join_clauses: list[str] = []
    joined_tables: set[str] = {primary_table}
    for ji in join_infos:
        jtype = ji["join_type"]
        lt = ji["left_table"]
        rt = ji["right_table"]
        al = ji["alias_left"]
        ar = ji["alias_right"]

        # If the right table is already in FROM scope (e.g. primary)
        # but the left table is not, swap so the new table gets JOINed.
        swapped = False
        if rt in joined_tables and lt not in joined_tables:
            lt, rt = rt, lt
            al, ar = ar, al
            swapped = True

        joined_tables.add(rt)
        join_target = _table_alias(rt, ar)

        # Build ON clause — use alias_map for globally consistent aliases
        al_eff = alias_map.get(lt, al)
        ar_eff = alias_map.get(rt, ar)

        on_parts = []
        for left_col, right_col in ji["on_pairs"]:
            if swapped:
                left_col, right_col = right_col, left_col
            l_ref = _col_ref(al_eff, left_col, dialect) if al_eff else f"{lt}.{q(left_col)}"
            r_ref = _col_ref(ar_eff, right_col, dialect) if ar_eff else f"{rt}.{q(right_col)}"
            on_parts.append(f"{l_ref} = {r_ref}")

        # Extra conditions go into ON clause
        for col, expr in ji.get("extra_conditions", []):
            on_parts.append(f"{q(col)} {expr}")

        on_clause = " AND ".join(on_parts) if on_parts else "1 = 1"
        join_clauses.append(f"  {jtype} {join_target}\n    ON {on_clause}")

    # ── Assemble SQL ─────────────────────────────────────────────
    sql = f"SELECT {top_clause}{'DISTINCT ' if distinct else ''}{col_expr}"
    sql += f"\nFROM {from_expr}"
    for jc in join_clauses:
        sql += f"\n{jc}"
    if wheres:
        sql += "\nWHERE " + "\n  AND ".join(wheres)
    if has_agg and plain_cols:
        sql += "\nGROUP BY " + ", ".join(plain_cols)
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

        if dialect == DB2:
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
