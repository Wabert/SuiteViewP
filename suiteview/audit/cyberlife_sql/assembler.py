"""CyberLife (DB2) query builder orchestrator."""
from __future__ import annotations

from ..cyberlife_criteria import AuditCriteria
from .state import QueryContext, SqlParts
from .context import collect_base_display_context, collect_policy2_and_flag_context
from .ctes_policy import add_policy2_ctes, collect_coverage_context, add_policy_and_coverage_ctes
from .ctes_values import add_policy_year_and_grace_ctes, add_target_and_value_ctes, add_cash_value_and_account_ctes, add_initial_display_selects
from .select_policy import add_policy_selects, add_policy_value_selects, add_accumulator_selects
from .select_display import add_rider_selects_and_from, add_policy_joins, add_value_joins
from .joins import add_core_joins, add_policy_value_joins, add_transaction_and_people_joins, add_rider_and_custom_joins
from .where_policy import add_base_where, add_policy_where, add_coverage_and_benefit_where
from .where_advanced import add_advanced_where, assemble_sql


def build_cyberlife_sql(criteria: AuditCriteria) -> str:
    """Build the CyberLife audit SQL from widget-free audit criteria."""
    ctx = QueryContext(criteria)
    parts = SqlParts()
    collect_base_display_context(ctx, parts)
    collect_policy2_and_flag_context(ctx, parts)
    add_policy2_ctes(ctx, parts)
    collect_coverage_context(ctx, parts)
    add_policy_and_coverage_ctes(ctx, parts)
    add_policy_year_and_grace_ctes(ctx, parts)
    add_target_and_value_ctes(ctx, parts)
    add_cash_value_and_account_ctes(ctx, parts)
    add_initial_display_selects(ctx, parts)
    add_policy_selects(ctx, parts)
    add_policy_value_selects(ctx, parts)
    add_accumulator_selects(ctx, parts)
    add_rider_selects_and_from(ctx, parts)
    add_policy_joins(ctx, parts)
    add_value_joins(ctx, parts)
    add_core_joins(ctx, parts)
    add_policy_value_joins(ctx, parts)
    add_transaction_and_people_joins(ctx, parts)
    add_rider_and_custom_joins(ctx, parts)
    add_base_where(ctx, parts)
    add_policy_where(ctx, parts)
    add_coverage_and_benefit_where(ctx, parts)
    add_advanced_where(ctx, parts)
    assemble_sql(ctx, parts)
    return parts.result
