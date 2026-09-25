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
) -> TableSearchResult:
    """Case-insensitive substring search over table names, field names and values.

    *tables* is ``(policy_record, table_name)`` in display order. A field whose
    name matches is listed once (with its values) instead of once per value hit.
    """
    needle = term.strip().lower()
    result = TableSearchResult(term=term.strip())
    if not needle:
        return result

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
        if needle in table.lower():
            count = len(rows)
            hits.append(TableSearchHit(
                MATCH_TABLE, record, table,
                value=f"{count} row{'s' if count != 1 else ''}",
            ))
        for column, name in enumerate(columns):
            if needle in name.lower():
                if len(rows) == 1:
                    hits.append(TableSearchHit(
                        MATCH_FIELD, record, table, name, 1, display_value(rows[0][column]),
                    ))
                else:
                    hits.append(TableSearchHit(
                        MATCH_FIELD, record, table, name, 0, _field_values_preview(rows, column),
                    ))
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
