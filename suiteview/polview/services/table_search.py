"""Find a table, field or value across the Policy Record tables loaded for a policy.

Powers the Tables panel search box. Only rows already fetched by the background
``tables`` stage are searched (never a new DB2 query on the GUI thread); a table
that is not in the cache is reported as not searched rather than silently skipped.
"""

from dataclasses import dataclass, field
from typing import Iterable

MAX_HITS = 2000
FIELD_VALUE_PREVIEW = 5

MATCH_TABLE = "Table"
MATCH_FIELD = "Field"
MATCH_VALUE = "Value"

# What the search box looks at: values only, field (column) names only, or
# everything (table names, field names and values).
SCOPE_VALUE = "Value"
SCOPE_FIELD = "Field"
SCOPE_ALL = "All"
SEARCH_SCOPES = (SCOPE_VALUE, SCOPE_FIELD, SCOPE_ALL)

_NO_MATCH_SUBJECT = {
    SCOPE_VALUE: "No value",
    SCOPE_FIELD: "No field",
    SCOPE_ALL: "No table, field or value",
}


def no_match_text(scope: str, term: str) -> str:
    return f"{_NO_MATCH_SUBJECT[scope]} contains “{term}”"


@dataclass(frozen=True)
class TableSearchHit:
    match: str      # MATCH_TABLE / MATCH_FIELD / MATCH_VALUE
    record: str     # Policy Record the table belongs to
    table: str
    field: str = ""
    row: int = 0    # 1-based row number; 0 when the hit is not row-specific
    value: str = ""


@dataclass
class TableSearchResult:
    term: str
    scope: str = SCOPE_ALL
    hits: list[TableSearchHit] = field(default_factory=list)
    tables_searched: int = 0
    not_searched: list[str] = field(default_factory=list)
    truncated: bool = False


def display_value(value) -> str:
    """Text a value is matched and shown as (DB2 CHAR columns are space-padded)."""
    return "" if value is None else str(value).strip()


def _field_values_preview(rows: list[tuple], column: int) -> str:
    values = list(dict.fromkeys(display_value(row[column]) for row in rows))
    shown = ", ".join(value or "(blank)" for value in values[:FIELD_VALUE_PREVIEW])
    extra = len(values) - FIELD_VALUE_PREVIEW
    return f"{shown}, … (+{extra} more)" if extra > 0 else shown


def search_policy_tables(
    policy,
    tables: Iterable[tuple[str, str]],
    term: str,
    limit: int = MAX_HITS,
    scope: str = SCOPE_ALL,
) -> TableSearchResult:
    """Case-insensitive substring search over table names, field names and values.

    *tables* is ``(policy_record, table_name)`` in display order. *scope* picks
    what is matched: ``SCOPE_VALUE`` (values only), ``SCOPE_FIELD`` (field names
    only) or ``SCOPE_ALL`` (table names, field names and values). In
    ``SCOPE_ALL`` a field whose name matches is listed once (with its values)
    instead of once per value hit.
    """
    if scope not in SEARCH_SCOPES:
        raise ValueError(f"Unknown table search scope: {scope!r}")
    needle = term.strip().lower()
    result = TableSearchResult(term=term.strip(), scope=scope)
    if not needle:
        return result
    match_tables = scope == SCOPE_ALL
    match_fields = scope in (SCOPE_FIELD, SCOPE_ALL)
    match_values = scope in (SCOPE_VALUE, SCOPE_ALL)

    seen = set()
    for record, table in tables:
        if table in seen:
            continue
        seen.add(table)
        cached = policy.cached_table(table)
        if cached is None:
            result.not_searched.append(table)
            continue
        columns, rows = cached
        result.tables_searched += 1

        hits = []
        if match_tables and needle in table.lower():
            count = len(rows)
            hits.append(TableSearchHit(
                MATCH_TABLE, record, table,
                value=f"{count} row{'s' if count != 1 else ''}",
            ))
        for column, name in enumerate(columns):
            if match_fields and needle in name.lower():
                if len(rows) == 1:
                    hits.append(TableSearchHit(
                        MATCH_FIELD, record, table, name, 1, display_value(rows[0][column]),
                    ))
                else:
                    hits.append(TableSearchHit(
                        MATCH_FIELD, record, table, name, 0, _field_values_preview(rows, column),
                    ))
                continue
            if not match_values:
                continue
            for index, row in enumerate(rows):
                text = display_value(row[column])
                if text and needle in text.lower():
                    hits.append(TableSearchHit(MATCH_VALUE, record, table, name, index + 1, text))

        room = limit - len(result.hits)
        if len(hits) > room:
            result.hits.extend(hits[:room])
            result.truncated = True
            return result
        result.hits.extend(hits)
    return result
