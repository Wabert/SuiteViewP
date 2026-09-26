from __future__ import annotations

from .helpers import name_match_predicate


def build_custom_display(custom_display_tab, result_cov_alias: str, schema: str) -> tuple[list[str], list[str], list[str]]:
    """Build SELECT column lines, JOIN lines, and WHERE conditions for the
    Custom Display tab.

    Returns ``(select_lines, join_lines, where_conditions)``.  Policy-level
    fields (LH_BAS_POL) use the always-present POLICY1 alias and coverage-level
    fields (LH_COV_PHA) use the result coverage alias.  The advanced tables
    (TH_BAS_POL / TH_COV_PHA) get dedicated LEFT OUTER JOINs so the columns are
    available regardless of which other filters are active.  When a row supplies
    a text criteria (Contains / Exact) it is turned into a WHERE condition on the
    row's selected fields (OR-combined across those fields).
    """
    if custom_display_tab is None:
        return ([], [], [])
    selections = custom_display_tab.get_selected_fields()
    alias_map = {'LH_BAS_POL': 'POLICY1', 'LH_COV_PHA': result_cov_alias, 'TH_BAS_POL': 'CUSTOM_THBAS', 'TH_COV_PHA': 'CUSTOM_THCOV'}
    select_lines: list[str] = []
    used_tables: set[str] = set()
    seen: set[tuple[str, str]] = set()
    for table, field in selections:
        alias = alias_map.get(table)
        if not alias:
            continue
        key = (alias, field)
        if key in seen:
            continue
        seen.add(key)
        used_tables.add(table)
        select_lines.append(f'  , {alias}.{field} {field}')
    where_conditions: list[str] = []
    criteria_filters = custom_display_tab.get_criteria_filters()
    for table, fields, match_type, value in criteria_filters:
        alias = alias_map.get(table)
        if not alias or not fields:
            continue
        used_tables.add(table)
        preds = [name_match_predicate(f'{alias}.{field}', match_type, value) for field in fields]
        if len(preds) == 1:
            where_conditions.append(preds[0])
        else:
            where_conditions.append('(' + ' OR '.join(preds) + ')')
    join_lines: list[str] = []
    if 'TH_BAS_POL' in used_tables:
        join_lines.append(f'  LEFT OUTER JOIN {schema}.TH_BAS_POL CUSTOM_THBAS')
        join_lines.append('    ON POLICY1.CK_SYS_CD = CUSTOM_THBAS.CK_SYS_CD')
        join_lines.append('    AND POLICY1.CK_CMP_CD = CUSTOM_THBAS.CK_CMP_CD')
        join_lines.append('    AND POLICY1.TCH_POL_ID = CUSTOM_THBAS.TCH_POL_ID')
    if 'TH_COV_PHA' in used_tables:
        join_lines.append(f'  LEFT OUTER JOIN {schema}.TH_COV_PHA CUSTOM_THCOV')
        join_lines.append(f'    ON {result_cov_alias}.CK_SYS_CD = CUSTOM_THCOV.CK_SYS_CD')
        join_lines.append(f'    AND {result_cov_alias}.CK_CMP_CD = CUSTOM_THCOV.CK_CMP_CD')
        join_lines.append(f'    AND {result_cov_alias}.TCH_POL_ID = CUSTOM_THCOV.TCH_POL_ID')
        join_lines.append(f'    AND {result_cov_alias}.COV_PHA_NBR = CUSTOM_THCOV.COV_PHA_NBR')
    return (select_lines, join_lines, where_conditions)
