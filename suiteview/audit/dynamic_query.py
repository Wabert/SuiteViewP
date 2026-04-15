"""
Dynamic SQL builder — generates SELECT queries from dynamic field filters.

Builds SQL for user-created groups based on the FieldRow widgets on the
active tab. Supports contains, regex, range, list, and combo filter modes.
"""
from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


def _escape(val: str) -> str:
    """Escape single quotes for SQL."""
    return val.replace("'", "''")


def build_dynamic_sql(
    table_name: str,
    max_count: str,
    field_filters: list[dict],
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

    Returns:
        SQL string.
    """
    wheres: list[str] = []

    for filt in field_filters:
        col = filt["column"]
        mode = filt.get("mode", "contains")
        val = filt.get("value", "").strip()
        lo = filt.get("range_lo", "").strip()
        hi = filt.get("range_hi", "").strip()
        list_vals = filt.get("list_values", [])

        if mode == "contains" and val:
            wheres.append(f"{col} LIKE '%{_escape(val)}%'")
        elif mode == "regex" and val:
            wheres.append(f"{col} LIKE '{_escape(val)}'")
        elif mode == "combo" and val:
            wheres.append(f"{col} = '{_escape(val)}'")
        elif mode == "range":
            if lo:
                wheres.append(f"{col} >= '{_escape(lo)}'")
            if hi:
                wheres.append(f"{col} <= '{_escape(hi)}'")
        elif mode == "list" and list_vals:
            escaped = [f"'{_escape(v)}'" for v in list_vals]
            wheres.append(f"{col} IN ({', '.join(escaped)})")

    # Build the SELECT
    top_clause = ""
    if max_count:
        try:
            n = int(max_count)
            if n > 0:
                top_clause = f"TOP {n} "
        except ValueError:
            pass

    sql = f"SELECT {top_clause}*\nFROM {table_name}"
    if wheres:
        sql += "\nWHERE " + "\n  AND ".join(wheres)

    return sql


def collect_field_filters(field_grid) -> list[dict]:
    """Extract filter values from a FieldGrid's FieldRow widgets.

    Each FieldRow stores its column name in field_key (format: "table.column").
    """
    filters = []
    for row in field_grid._rows:
        mode = row.mode
        col_name = row.field_key
        # field_key may be "schema.table.column" — extract just column
        parts = col_name.split(".")
        actual_col = parts[-1] if parts else col_name

        filt = {"column": actual_col, "mode": mode}

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
