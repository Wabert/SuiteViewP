from __future__ import annotations

from decimal import Decimal, InvalidOperation

from suiteview.audit.db2_table_fields import CUSTOM_DISPLAY_TABLES, FIELD_KINDS, TABLE_FIELDS

from ..sql_helpers import esc, normalize_date, strict_range_predicates
from .helpers import name_match_predicate

# LH_BAS_POL (POLICY1) and LH_COV_PHA (result coverage) are already in the main
# query; every other catalog table gets its own join.
_MAIN_QUERY_TABLES = frozenset({'LH_BAS_POL', 'LH_COV_PHA'})
_LEGACY_JOIN_ALIASES = {'TH_BAS_POL': 'CUSTOM_THBAS', 'TH_COV_PHA': 'CUSTOM_THCOV'}
_NUMERIC_KINDS = frozenset({'integer', 'decimal'})


def _join_alias(table: str) -> str:
    return _LEGACY_JOIN_ALIASES.get(table, f'CUSTOM_{table}')


def _is_coverage_keyed(table: str) -> bool:
    return any(field == 'COV_PHA_NBR' for field, _desc in TABLE_FIELDS.get(table, ()))


def _join_lines(table: str, alias: str, result_cov_alias: str, schema: str) -> list[str]:
    """LEFT OUTER JOIN on the CyberLife policy key, plus COV_PHA_NBR for
    coverage-keyed tables (matched to the result coverage)."""
    key_alias = result_cov_alias if _is_coverage_keyed(table) else 'POLICY1'
    lines = [f'  LEFT OUTER JOIN {schema}.{table} {alias}']
    for i, column in enumerate(('CK_SYS_CD', 'CK_CMP_CD', 'TCH_POL_ID')):
        lines.append(f"    {'ON' if i == 0 else 'AND'} {key_alias}.{column} = {alias}.{column}")
    if key_alias == result_cov_alias:
        lines.append(f'    AND {result_cov_alias}.COV_PHA_NBR = {alias}.COV_PHA_NBR')
    return lines


def _clean_number(text: str) -> str:
    return text.strip().replace(',', '').replace('$', '')


def _exact_predicate(column: str, kind: str, value: str, label: str) -> str:
    """``=`` comparison using a literal of the column's DB2 type."""
    if kind in _NUMERIC_KINDS:
        try:
            number = Decimal(_clean_number(value))
        except InvalidOperation as exc:
            raise ValueError(f'{label}: enter a number (this field is numeric).') from exc
        if not number.is_finite():
            raise ValueError(f'{label}: enter a finite number.')
        if kind == 'integer' and number != number.to_integral_value():
            raise ValueError(f'{label}: enter a whole number.')
        return f"{column} = {format(number, 'f')}"
    if kind == 'date':
        parsed = normalize_date(value)
        if parsed is None:
            raise ValueError(f'{label}: use MM/DD/YYYY or YYYY-MM-DD (this field is a date).')
        return f"{column} = '{parsed}'"
    return name_match_predicate(column, 'Exact', value)


def _range_predicate(column: str, kind: str, lo: str, hi: str, label: str) -> str:
    """Inclusive range; numbers/dates compare by value, text by collation."""
    if kind in _NUMERIC_KINDS or kind == 'date':
        if kind != 'date':
            lo, hi = _clean_number(lo), _clean_number(hi)
        preds = strict_range_predicates(column, lo, hi, kind, label)
    else:
        text_col = f'UPPER(TRIM({column}))'
        preds = [f"{text_col} {op} '{esc(bound.strip().upper())}'"
                 for bound, op in ((lo, '>='), (hi, '<=')) if bound.strip()]
    return preds[0] if len(preds) == 1 else '(' + ' AND '.join(preds) + ')'


def criteria_predicate(column: str, kind: str, match_type: str, value: str,
                       value_to: str, label: str) -> str:
    """WHERE predicate for one Custom Display field.

    ``Contains`` is a case-insensitive text match.  ``Exact`` and ``Range``
    follow the column's DB2 kind: numeric columns compare numbers, date
    columns compare dates (MM/DD/YYYY or YYYY-MM-DD input), and text columns
    compare trimmed upper-case text.  Invalid input raises ``ValueError``.
    """
    if match_type == 'Range':
        return _range_predicate(column, kind, value, value_to, label)
    if match_type == 'Exact':
        return _exact_predicate(column, kind, value, label)
    return name_match_predicate(column, match_type, value)


def build_custom_display(custom_display_tab, result_cov_alias: str, schema: str) -> tuple[list[str], list[str], list[str]]:
    """Build SELECT column lines, JOIN lines, and WHERE conditions for the
    Custom Display tab.

    Returns ``(select_lines, join_lines, where_conditions)``.  LH_BAS_POL fields
    use the always-present POLICY1 alias and LH_COV_PHA fields use the result
    coverage alias.  Every other catalog table (TH_BAS_POL, TH_COV_PHA and the
    segment 35/66/72 tables) gets a dedicated LEFT OUTER JOIN so the columns are
    available regardless of which other filters are active.  Tables keyed by
    COV_PHA_NBR join to the result coverage; the rest join to POLICY1.  Tables
    with several rows per policy (e.g. segment 72 notes) yield one result row
    per matching row.  When a row supplies criteria (Contains / Exact / Range)
    it becomes a WHERE condition on each of the row's selected fields,
    OR-combined across those fields (see :func:`criteria_predicate`).
    """
    if custom_display_tab is None:
        return ([], [], [])
    selections = custom_display_tab.get_selected_fields()
    alias_map = {'LH_BAS_POL': 'POLICY1', 'LH_COV_PHA': result_cov_alias}
    for table in CUSTOM_DISPLAY_TABLES.values():
        alias_map.setdefault(table, _join_alias(table))
    select_lines: list[str] = []
    used_tables: set[str] = set()
    seen: set[tuple[str, str]] = set()
    output_names: set[str] = set()
    for table, field in selections:
        alias = alias_map.get(table)
        if not alias:
            continue
        key = (alias, field)
        if key in seen:
            continue
        seen.add(key)
        used_tables.add(table)
        # The same column picked from two tables (e.g. CK_CMP_CD) needs a unique header.
        name = field if field not in output_names else f'{table}_{field}'
        output_names.add(name)
        select_lines.append(f'  , {alias}.{field} {name}')
    where_conditions: list[str] = []
    criteria_filters = custom_display_tab.get_criteria_filters()
    for table, fields, match_type, value, value_to in criteria_filters:
        alias = alias_map.get(table)
        if not alias or not fields:
            continue
        used_tables.add(table)
        kinds = FIELD_KINDS.get(table, {})
        preds = [
            criteria_predicate(f'{alias}.{field}', kinds.get(field, 'text'), match_type,
                               value, value_to, f'Custom Display / {table}.{field}')
            for field in fields
        ]
        if len(preds) == 1:
            where_conditions.append(preds[0])
        else:
            where_conditions.append('(' + ' OR '.join(preds) + ')')
    join_lines: list[str] = []
    for table in CUSTOM_DISPLAY_TABLES.values():
        if table in used_tables and table not in _MAIN_QUERY_TABLES:
            join_lines.extend(_join_lines(table, alias_map[table], result_cov_alias, schema))
    return (select_lines, join_lines, where_conditions)
