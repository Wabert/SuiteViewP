"""CyberLife (DB2) query builder orchestrator."""
from __future__ import annotations

from collections.abc import Callable

from ..cyberlife_criteria import AuditCriteria
from .context import derive_audit_flags
from .ctes_policy import (
    add_policy_and_coverage_ctes,
    collect_coverage_context,
)
from .ctes_values import (
    add_cash_value_and_account_ctes,
    add_initial_display_selects,
    add_policy_year_and_grace_ctes,
    add_target_and_value_ctes,
)
from .joins import (
    add_core_joins,
    add_policy_value_joins,
    add_rider_and_custom_joins,
    add_transaction_and_people_joins,
)
from .select_display import (
    add_policy_joins,
    add_rider_selects_and_from,
    add_value_joins,
)
from .select_policy import (
    add_accumulator_selects,
    add_policy_selects,
    add_policy_value_selects,
)
from .state import QueryContext, SqlFragment, SqlParts
from .where_advanced import add_advanced_where, assemble_sql
from .where_policy import (
    add_base_where,
    add_coverage_and_benefit_where,
    add_policy_where,
)


SectionBuilder = Callable[[QueryContext, SqlParts], None]


def _run_fragment(
    ctx: QueryContext,
    parts: SqlParts,
    builder: SectionBuilder,
) -> SqlFragment:
    """Run a legacy section and return the immutable SQL delta it produced."""
    sql_start = len(parts.sql_parts)
    where_start = len(parts.wheres)
    order_start = len(parts.order_by)
    builder(ctx, parts)
    return SqlFragment(
        ctes=tuple(parts.sql_parts[sql_start:]),
        wheres=tuple(parts.wheres[where_start:]),
        order=tuple(parts.order_by[order_start:]),
        result=parts.result,
    )


def build_cyberlife_sql(criteria: AuditCriteria) -> str:
    """Build the CyberLife audit SQL from widget-free audit criteria."""
    derived = derive_audit_flags(criteria)
    ctx = QueryContext(derived)
    parts = SqlParts(sql_parts=list(derived.initial_ctes))
    fragments = [SqlFragment(ctes=derived.initial_ctes)]
    for builder in (
        collect_coverage_context,
        add_policy_and_coverage_ctes,
        add_policy_year_and_grace_ctes,
        add_target_and_value_ctes,
        add_cash_value_and_account_ctes,
        add_initial_display_selects,
        add_policy_selects,
        add_policy_value_selects,
        add_accumulator_selects,
        add_rider_selects_and_from,
        add_policy_joins,
        add_value_joins,
        add_core_joins,
        add_policy_value_joins,
        add_transaction_and_people_joins,
        add_rider_and_custom_joins,
        add_base_where,
        add_policy_where,
        add_coverage_and_benefit_where,
        add_advanced_where,
        assemble_sql,
    ):
        fragments.append(_run_fragment(ctx, parts, builder))
    # The final fragment carries the byte-identical concatenation produced in
    # the established section order.
    return fragments[-1].result
