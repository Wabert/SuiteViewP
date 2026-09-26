"""Execution-plan construction for reviewed Rate Manager loads."""

from __future__ import annotations

from collections import OrderedDict
from dataclasses import dataclass
from typing import Any, Mapping

from suiteview.ratemanager.analysis import PackageAnalysis
from suiteview.ratemanager.package import WorkupPackage
from suiteview.ratemanager.schema import LoadAction, RateSchema, UL_SCHEMA



@dataclass(frozen=True)
class PlanIssue:
    table_name: str
    message: str



@dataclass(frozen=True)
class ExecutionPlan:
    plancode: str
    actions: Mapping[str, LoadAction]
    insert_rows: Mapping[str, tuple[tuple[Any, ...], ...]]
    delete_pointer_scopes: Mapping[str, tuple[tuple[Any, ...], ...]]
    delete_indexes: Mapping[str, frozenset[int]]
    backup_rows: Mapping[str, tuple[tuple[Any, ...], ...]]
    issues: tuple[PlanIssue, ...]

    @property
    def is_safe(self) -> bool:
        return not self.issues



@dataclass(frozen=True)
class ExecutionResult:
    backup_path: str
    inserted_rows: Mapping[str, int]
    deleted_rows: Mapping[str, int]
    verified: bool = True


@dataclass
class _PlanDraft:
    issues: list[PlanIssue]
    insert_rows: dict[str, tuple[tuple[Any, ...], ...]]
    delete_indexes: dict[str, frozenset[Any]]
    backup_rows: dict[str, tuple[tuple[Any, ...], ...]]
    delete_pointer_scopes: dict[str, tuple[tuple[Any, ...], ...]]



def normalize_actions(
    actions: Mapping[str, LoadAction | str],
    schema: RateSchema = UL_SCHEMA,
) -> "OrderedDict[str, LoadAction]":
    normalized: "OrderedDict[str, LoadAction]" = OrderedDict()
    for table_name in schema.specs:
        value = actions.get(table_name, LoadAction.SKIP)
        normalized[table_name] = (
            value if isinstance(value, LoadAction) else LoadAction(value)
        )
    return normalized


def _sample(values) -> str:
    ordered = sorted(values)
    sample = ", ".join(str(index) for index in ordered[:12])
    if len(ordered) > 12:
        sample += f", ... ({len(ordered):,} total)"
    return sample


def _plan_pointer_table(package, name, action, table_analysis, data, draft) -> None:
    spec = data.spec
    if action == LoadAction.INSERT and table_analysis.existing_rows:
        detail = spec.scope_detail(table_analysis.existing_rows)
        draft.issues.append(PlanIssue(
            name,
            f"{name} already has {len(table_analysis.existing_rows):,} "
            f"row(s) for {package.plancode}{detail}; "
            "explicitly choose Replace.",
        ))
        return
    if action == LoadAction.REPLACE:
        draft.delete_pointer_scopes[name] = tuple(
            sorted({spec.scope(row) for row in data.rows})
        )
        if table_analysis.existing_rows:
            draft.backup_rows[name] = table_analysis.existing_rows
    draft.insert_rows[name] = data.rows


def _plan_rate_replacement(schema, normalized, name, table_analysis, draft) -> bool:
    if table_analysis.blocked_indexes:
        details = "; ".join(
            f"{index}: {', '.join(plancodes)}"
            for index, plancodes in sorted(table_analysis.blocked_indexes.items())
        )
        draft.issues.append(PlanIssue(
            name,
            "Cannot replace index data used by other plancodes "
            f"({details}).",
        ))
        return False
    pointer_ref = schema.references.get(name)
    if table_analysis.different_indexes and pointer_ref:
        pointer_name, _column = pointer_ref
        if normalized[pointer_name] != LoadAction.REPLACE:
            draft.issues.append(PlanIssue(
                name,
                f"Replacing owned {name} indexes also requires "
                f"{pointer_name} to use Replace in the same transaction.",
            ))
            return False
    return True


def _plan_rate_table(schema, normalized, name, action, table_analysis, data, draft) -> None:
    spec = data.spec
    if action == LoadAction.INSERT and table_analysis.different_indexes:
        draft.issues.append(PlanIssue(
            name,
            f"{name} has different existing data at index(es) "
            f"{_sample(table_analysis.different_indexes)}; explicitly choose Replace.",
        ))
        return

    if action == LoadAction.REPLACE:
        if not _plan_rate_replacement(schema, normalized, name, table_analysis, draft):
            return
        replaced = table_analysis.replaceable_indexes
        if replaced:
            draft.delete_indexes[name] = replaced
            draft.backup_rows[name] = tuple(
                row for row in table_analysis.existing_rows
                if spec.index_value(row) in replaced
            )

    included_indexes = (
        table_analysis.new_indexes | table_analysis.replaceable_indexes
        if action == LoadAction.REPLACE
        else table_analysis.new_indexes
    )
    draft.insert_rows[name] = tuple(
        row for row in data.rows if spec.index_value(row) in included_indexes
    )


def _available_indexes(rate_action, rate_analysis) -> set[Any]:
    available = set(rate_analysis.available_indexes)
    if rate_action != LoadAction.SKIP:
        available.update(
            rate_analysis.new_indexes
            | rate_analysis.identical_indexes
            | rate_analysis.replaceable_indexes
        )
    return available


def _check_pointer_references(package, analysis, normalized, pointer_name, draft) -> None:
    pointer_data = package.tables[pointer_name]
    for column, rate_table in pointer_data.spec.pointer_refs.items():
        pos = pointer_data.spec.column_index(column)
        referenced = {row[pos] for row in pointer_data.rows if row[pos] is not None}
        if not referenced:
            continue
        rate_action = normalized[rate_table]
        rate_analysis = analysis.tables[rate_table]
        if rate_action == LoadAction.SKIP:
            mismatched = referenced & rate_analysis.different_indexes
            if mismatched:
                draft.issues.append(PlanIssue(
                    pointer_name,
                    f"{column} would use existing {rate_table} data that "
                    f"differs from this workup at index(es): {_sample(mismatched)}.",
                ))
        missing = referenced - _available_indexes(rate_action, rate_analysis)
        if missing:
            draft.issues.append(PlanIssue(
                pointer_name,
                f"{column} references missing {rate_table} index(es): {_sample(missing)}.",
            ))


def create_execution_plan(
    package: WorkupPackage,
    analysis: PackageAnalysis,
    actions: Mapping[str, LoadAction | str],
) -> ExecutionPlan:
    schema = package.schema
    normalized = normalize_actions(actions, schema)
    draft = _PlanDraft([], {}, {}, {}, {})

    for name, action in normalized.items():
        if action == LoadAction.SKIP:
            continue
        table_analysis = analysis.tables[name]
        data = package.tables[name]
        spec = data.spec

        if spec.is_pointer:
            _plan_pointer_table(package, name, action, table_analysis, data, draft)
            continue
        _plan_rate_table(
            schema, normalized, name, action, table_analysis, data, draft,
        )

    for pointer_name in schema.pointer_names:
        if normalized[pointer_name] != LoadAction.SKIP:
            _check_pointer_references(package, analysis, normalized, pointer_name, draft)

    return ExecutionPlan(
        package.plancode,
        normalized,
        draft.insert_rows,
        draft.delete_pointer_scopes,
        draft.delete_indexes,
        draft.backup_rows,
        tuple(draft.issues),
    )
