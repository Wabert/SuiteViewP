from __future__ import annotations

from .helpers import _name_match_predicate
from ..segment52_fields import SEGMENT52_FIELDS
from ..sql_helpers import strict_range_predicates

def _build_segment52(segment52_tab, show_all: bool) -> tuple[list[str], list[str]]:
    fields = segment52_tab.get_state()['fields'] if segment52_tab is not None else {}
    select_lines, wheres = ([], [])
    for field in SEGMENT52_FIELDS:
        values = fields.get(field.name, {})
        column = f'USERGEN.{field.name}'
        predicates = []
        if field.kind == 'text':
            value = values.get('value', '').strip().upper()
            if value:
                predicates.append(_name_match_predicate(column, values.get('match', 'Exact match'), value))
        else:
            predicates = strict_range_predicates(column, values.get('lo', ''), values.get('hi', ''), field.kind, f'52 Segment / {field.name}')
        wheres.extend(predicates)
        if show_all or values.get('display', False) or predicates:
            select_lines.append(f'  , {column} {field.name}')
    return (select_lines, wheres)
