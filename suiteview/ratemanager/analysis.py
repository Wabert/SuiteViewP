"""Database comparison analysis for Rate Manager packages."""

from __future__ import annotations

from collections import OrderedDict, defaultdict
from dataclasses import dataclass, field
from typing import Any, Callable, Mapping, Optional

from suiteview.ratemanager.package import TableData, WorkupPackage, _rows_digest



@dataclass(frozen=True)
class TableAnalysis:
    table_name: str
    file_rows: int
    existing_rows: tuple[tuple[Any, ...], ...] = ()
    # Stored rather than looked up, so an analysis is self-describing and
    # does not have to resolve its table name against a schema registry.
    is_pointer: bool = False
    new_indexes: frozenset[Any] = frozenset()
    identical_indexes: frozenset[Any] = frozenset()
    different_indexes: frozenset[Any] = frozenset()
    replaceable_indexes: frozenset[Any] = frozenset()
    blocked_indexes: Mapping[Any, tuple[str, ...]] = field(default_factory=dict)
    available_indexes: frozenset[Any] = frozenset()
    identical_pointer_keys: frozenset[tuple[Any, ...]] = frozenset()
    different_pointer_keys: frozenset[tuple[Any, ...]] = frozenset()

    @property
    def has_existing_pointer_rows(self) -> bool:
        return self.is_pointer and bool(self.existing_rows)



@dataclass(frozen=True)
class PackageAnalysis:
    plancode: str
    issue_version: int
    tables: "OrderedDict[str, TableAnalysis]"
    signature: str



def analyze_package(
    package: WorkupPackage,
    repository: Any,
    progress_callback: Optional[Callable[[str], None]] = None,
) -> PackageAnalysis:
    def progress(message: str) -> None:
        if progress_callback is not None:
            progress_callback(message)

    progress("Validating UL_Rates table schemas...")
    repository.validate_schema()
    schema = package.schema
    analyses: "OrderedDict[str, TableAnalysis]" = OrderedDict()
    state_rows: dict[str, list[tuple[Any, ...]]] = defaultdict(list)

    pointer_ref_indexes = _pointer_reference_indexes(package)

    table_count = len(package.tables)
    for table_number, (name, data) in enumerate(package.tables.items(), start=1):
        progress(
            f"Rechecking {name} ({table_number}/{table_count}) against UL_Rates..."
        )
        spec = data.spec
        if spec.is_pointer:
            analyses[name] = _analyze_pointer_table(
                package, repository, name, data,
            )
            state_rows[name].extend(
                repository.fetch_pointer_rows(name, package.plancode)
            )
            continue

        analysis, references = _analyze_rate_table(
            package, repository, name, data, pointer_ref_indexes[name],
        )
        analyses[name] = analysis
        existing_rows = analysis.existing_rows
        state_rows[name].extend(existing_rows)
        pointer_ref = schema.references.get(name)
        if pointer_ref:
            pointer_name, _column = pointer_ref
            for index, plancodes in sorted(references.items()):
                for plancode in sorted(plancodes):
                    state_rows[f"{pointer_name}->{name}"].append(
                        (index, plancode)
                    )

    return PackageAnalysis(
        package.plancode,
        package.issue_version,
        analyses,
        _rows_digest(state_rows),
    )


def _pointer_reference_indexes(package: WorkupPackage) -> dict[str, set[Any]]:
    pointer_ref_indexes: dict[str, set[Any]] = defaultdict(set)
    for pointer_name in package.schema.pointer_names:
        pointer_data = package.tables[pointer_name]
        for column, rate_table in pointer_data.spec.pointer_refs.items():
            pos = pointer_data.spec.column_index(column)
            pointer_ref_indexes[rate_table].update(
                row[pos] for row in pointer_data.rows if row[pos] is not None
            )
    return pointer_ref_indexes


def _analyze_pointer_table(
    package: WorkupPackage,
    repository: Any,
    name: str,
    data: TableData,
) -> TableAnalysis:
    spec = data.spec
    existing = tuple(repository.fetch_pointer_rows(name, package.plancode))
    incoming_scopes = {spec.scope(row) for row in data.rows}
    scoped_existing = tuple(row for row in existing if spec.scope(row) in incoming_scopes)
    incoming_by_key = data.rows_by_key()
    existing_by_key = {spec.key(row): row for row in scoped_existing}
    shared_keys = incoming_by_key.keys() & existing_by_key.keys()
    identical = frozenset(
        key for key in shared_keys if incoming_by_key[key] == existing_by_key[key]
    )
    return TableAnalysis(
        table_name=name,
        file_rows=len(data.rows),
        existing_rows=scoped_existing,
        is_pointer=True,
        identical_pointer_keys=identical,
        different_pointer_keys=frozenset(shared_keys - identical),
    )


def _analyze_rate_table(
    package: WorkupPackage,
    repository: Any,
    name: str,
    data: TableData,
    pointer_indexes: set[Any],
) -> tuple[TableAnalysis, Mapping[Any, set[str]]]:
    incoming_by_index = data.rows_by_index()
    requested_indexes = set(incoming_by_index) | pointer_indexes
    existing_indexes = repository.fetch_existing_indexes(name, requested_indexes)
    colliding = set(incoming_by_index) & existing_indexes
    existing_rows = tuple(repository.fetch_rate_rows(name, colliding))
    existing_by_index = TableData(data.spec, existing_rows).rows_by_index()
    identical_indexes, different_indexes = _compare_indexes(
        incoming_by_index, existing_by_index, colliding,
    )
    references = repository.fetch_index_references(name, different_indexes)
    blocked, replaceable = _replacement_sets(
        references, different_indexes, package.plancode,
    )
    analysis = TableAnalysis(
        table_name=name,
        file_rows=len(data.rows),
        existing_rows=existing_rows,
        new_indexes=frozenset(set(incoming_by_index) - existing_indexes),
        identical_indexes=frozenset(identical_indexes),
        different_indexes=frozenset(different_indexes),
        replaceable_indexes=frozenset(replaceable),
        blocked_indexes=blocked,
        available_indexes=frozenset(existing_indexes),
    )
    return analysis, references


def _compare_indexes(incoming_by_index, existing_by_index, colliding):
    identical_indexes: set[Any] = set()
    different_indexes: set[Any] = set()
    for index in colliding:
        if incoming_by_index[index] == existing_by_index.get(index, ()):
            identical_indexes.add(index)
        else:
            different_indexes.add(index)
    return identical_indexes, different_indexes


def _replacement_sets(references, different_indexes, plancode):
    blocked: dict[Any, tuple[str, ...]] = {}
    replaceable: set[Any] = set()
    for index in different_indexes:
        plancodes = {value.strip() for value in references.get(index, set()) if value}
        other_plancodes = tuple(sorted(plancodes - {plancode}))
        if other_plancodes:
            blocked[index] = other_plancodes
        else:
            replaceable.add(index)
    return blocked, replaceable
