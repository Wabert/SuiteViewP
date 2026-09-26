"""ODBC repository and transaction helpers for Rate Manager loads."""

from __future__ import annotations

from collections import defaultdict
from pathlib import Path
from typing import Any, Callable, Iterable, Mapping, Optional

import pyodbc

from suiteview.core.build_env import guard_data_writable
from suiteview.core.data_access.connections import connection_factory
from suiteview.core.data_sources import UL_RATES_DSN
from suiteview.core.sql_identifiers import quote_identifier
from suiteview.ratemanager.analysis import analyze_package
from suiteview.ratemanager.backup import write_backup
from suiteview.ratemanager.package import (
    TableData,
    WorkupPackage,
    _database_row,
    _rows_digest,
    coerce_row,
)
from suiteview.ratemanager.plan import (
    ExecutionPlan,
    ExecutionResult,
    create_execution_plan,
    normalize_actions,
)
from suiteview.ratemanager.schema import (
    LoadAction,
    PackageValidationError,
    RateDatabaseError,
    RateSchema,
    StaleAnalysisError,
    TableSpec,
    UL_SCHEMA,
    UnsafeOperationError,
)



class ULRatesRepository:
    """Parameterized SQL Server access through the UL_Rates ODBC DSN.

    A repository is bound to one :class:`RateSchema`, so the same database
    connection serves the UL and Term table families without either being
    able to address the other's tables.
    """

    def __init__(self, dsn: str = UL_RATES_DSN, schema: RateSchema = UL_SCHEMA):
        self.dsn = dsn.strip() or UL_RATES_DSN
        self.schema = schema
        self._connection: Optional[pyodbc.Connection] = None

    def connect(self) -> pyodbc.Connection:
        if self._connection is None:
            self._connection = connection_factory.connect_dsn(
                self.dsn, autocommit=False, timeout=10, readonly=False,
            )
        return self._connection

    def close(self) -> None:
        if self._connection is not None:
            self._connection.close()
            self._connection = None

    def rollback(self) -> None:
        if self._connection is not None:
            self._connection.rollback()

    def commit(self) -> None:
        self.connect().commit()

    def begin_serializable(self) -> None:
        cursor = self.connect().cursor()
        try:
            cursor.execute("SET XACT_ABORT ON")
            cursor.execute("SET TRANSACTION ISOLATION LEVEL SERIALIZABLE")
        finally:
            cursor.close()

    def test_connection(self) -> str:
        cursor = self.connect().cursor()
        try:
            cursor.execute("SELECT DB_NAME()")
            row = cursor.fetchone()
            return str(row[0]) if row and row[0] is not None else self.dsn
        finally:
            cursor.close()

    def validate_schema(self) -> None:
        cursor = self.connect().cursor()
        try:
            for spec in self.schema.specs.values():
                columns = ", ".join(
                    quote_identifier(column)
                    for column in spec.columns
                )
                try:
                    cursor.execute(
                        f"SELECT {columns} FROM {quote_identifier(spec.name)} WHERE 1 = 0"
                    )
                except Exception as exc:
                    raise RateDatabaseError(
                        f"{spec.name} schema does not match the Rate Manager "
                        f"mapping. Expected database columns: {columns}. "
                        f"Database error: {exc}"
                    ) from exc
        finally:
            cursor.close()

    def fetch_pointer_rows(
        self, table_name: str, plancode: str
    ) -> list[tuple[Any, ...]]:
        spec = self.schema.specs[table_name]
        if not spec.is_pointer:
            raise ValueError(f"{table_name} is not a pointer table.")
        columns = ", ".join(
            quote_identifier(column) for column in spec.columns
        )
        cursor = self.connect().cursor()
        try:
            cursor.execute(
                f"SELECT {columns} FROM {quote_identifier(table_name)} "
                f"WHERE {quote_identifier('Plancode')} = ?",
                (plancode,),
            )
            return [
                coerce_row(spec, tuple(row), source="UL_Rates")
                for row in cursor.fetchall()
            ]
        finally:
            cursor.close()

    def fetch_existing_indexes(
        self, table_name: str, indexes: Iterable[Any]
    ) -> set[Any]:
        spec = self.schema.specs[table_name]
        index_column = spec.index_column
        found: set[Any] = set()
        for chunk in _chunks(sorted(set(indexes))):
            if not chunk:
                continue
            placeholders = ", ".join("?" for _ in chunk)
            cursor = self.connect().cursor()
            try:
                cursor.execute(
                    f"SELECT DISTINCT {quote_identifier(index_column)} "
                    f"FROM {quote_identifier(table_name)} "
                    f"WHERE {quote_identifier(index_column)} IN ({placeholders})",
                    chunk,
                )
                found.update(
                    spec.coerce_index(row[0]) for row in cursor.fetchall()
                )
            finally:
                cursor.close()
        return found

    def fetch_rate_rows(
        self, table_name: str, indexes: Iterable[Any]
    ) -> list[tuple[Any, ...]]:
        spec = self.schema.specs[table_name]
        columns = ", ".join(
            quote_identifier(column) for column in spec.columns
        )
        index_column = spec.index_column
        rows: list[tuple[Any, ...]] = []
        for chunk in _chunks(sorted(set(indexes))):
            if not chunk:
                continue
            placeholders = ", ".join("?" for _ in chunk)
            cursor = self.connect().cursor()
            try:
                cursor.execute(
                    f"SELECT {columns} FROM {quote_identifier(table_name)} "
                    f"WHERE {quote_identifier(index_column)} IN ({placeholders})",
                    chunk,
                )
                rows.extend(
                    coerce_row(spec, tuple(row), source="UL_Rates")
                    for row in cursor.fetchall()
                )
            finally:
                cursor.close()
        return rows

    def fetch_index_references(
        self, rate_table: str, indexes: Iterable[Any]
    ) -> dict[Any, set[str]]:
        pointer_ref = self.schema.references.get(rate_table)
        if not pointer_ref:
            return {}
        rate_spec = self.schema.specs[rate_table]
        pointer_table, pointer_column = pointer_ref
        references: dict[Any, set[str]] = defaultdict(set)
        for chunk in _chunks(sorted(set(indexes))):
            if not chunk:
                continue
            placeholders = ", ".join("?" for _ in chunk)
            cursor = self.connect().cursor()
            try:
                cursor.execute(
                    f"SELECT {quote_identifier(pointer_column)}, {quote_identifier('Plancode')} "
                    f"FROM {quote_identifier(pointer_table)} "
                    f"WHERE {quote_identifier(pointer_column)} IN ({placeholders})",
                    chunk,
                )
                for index, plancode in cursor.fetchall():
                    if index is not None and plancode is not None:
                        references[rate_spec.coerce_index(index)].add(
                            str(plancode).strip())
            finally:
                cursor.close()
        return references

    def apply_plan(
        self,
        plan: ExecutionPlan,
        progress_callback: Optional[Callable[[str], None]] = None,
    ) -> dict[str, int]:
        guard_data_writable("load rate data")

        def progress(message: str) -> None:
            if progress_callback is not None:
                progress_callback(message)

        if not plan.is_safe:
            raise UnsafeOperationError("Cannot execute a plan with safety issues.")
        cursor = self.connect().cursor()
        deleted: dict[str, int] = defaultdict(int)
        try:
            for table_name in self.schema.pointer_names:
                scopes = plan.delete_pointer_scopes.get(table_name)
                if not scopes:
                    continue
                spec = self.schema.specs[table_name]
                scope_columns = spec.collision_scope_columns
                where = " AND ".join(
                    f"{quote_identifier(column)} = ?" for column in scope_columns
                )
                progress(f"Removing existing {table_name} rows...")
                for scope_values in scopes:
                    cursor.execute(
                        f"DELETE FROM {quote_identifier(table_name)} WHERE {where}",
                        tuple(scope_values),
                    )
                    deleted[table_name] += max(cursor.rowcount, 0)

            for table_name, indexes in plan.delete_indexes.items():
                spec = self.schema.specs[table_name]
                index_column = spec.index_column
                progress(
                    f"Removing {len(indexes):,} selected index(es) from {table_name}..."
                )
                for chunk in _chunks(sorted(indexes)):
                    placeholders = ", ".join("?" for _ in chunk)
                    cursor.execute(
                        f"DELETE FROM {quote_identifier(table_name)} "
                        f"WHERE {quote_identifier(index_column)} IN ({placeholders})",
                        chunk,
                    )
                    deleted[table_name] += max(cursor.rowcount, 0)

            cursor.fast_executemany = True
            rate_tables = [
                name for name, spec in self.schema.specs.items()
                if not spec.is_pointer
            ]
            pointer_tables = [
                name for name, spec in self.schema.specs.items()
                if spec.is_pointer
            ]
            for table_name in rate_tables + pointer_tables:
                rows = plan.insert_rows.get(table_name, ())
                if not rows:
                    continue
                total_rows = len(rows)
                progress(f"Loading {total_rows:,} row(s) into {table_name}...")
                spec = self.schema.specs[table_name]
                columns = ", ".join(
                    quote_identifier(column)
                    for column in spec.columns
                )
                placeholders = ", ".join("?" for _ in spec.columns)
                try:
                    sql = (
                        f"INSERT INTO {quote_identifier(table_name)} ({columns}) "
                        f"VALUES ({placeholders})"
                    )
                    loaded = 0
                    for batch in _chunks(rows, size=10_000):
                        cursor.executemany(
                            sql,
                            [_database_row(spec, row) for row in batch],
                        )
                        loaded += len(batch)
                        progress(
                            f"Loading {table_name}: {loaded:,}/{total_rows:,} "
                            "row(s) staged..."
                        )
                except Exception as exc:
                    raise RateDatabaseError(
                        f"Could not insert {len(rows):,} row(s) into "
                        f"{table_name}: {exc}"
                    ) from exc
        finally:
            cursor.close()
        return dict(deleted)



def execute_package(
    package: WorkupPackage,
    dsn: str,
    actions: Mapping[str, LoadAction | str],
    expected_signature: str,
    backup_root: str | Path | None = None,
    progress_callback: Optional[Callable[[str], None]] = None,
) -> ExecutionResult:
    guard_data_writable("load rate data")

    def progress(message: str) -> None:
        if progress_callback is not None:
            progress_callback(message)

    repository = ULRatesRepository(dsn, package.schema)
    backup_path: Optional[Path] = None
    try:
        progress("Opening a serializable UL_Rates transaction...")
        repository.begin_serializable()
        fresh_analysis = analyze_package(package, repository, progress)
        if fresh_analysis.signature != expected_signature:
            raise StaleAnalysisError(
                "UL_Rates changed after the analysis. Analyze again before loading."
            )
        plan = create_execution_plan(package, fresh_analysis, actions)
        if not plan.is_safe:
            details = "\n".join(
                f"{issue.table_name}: {issue.message}" for issue in plan.issues
            )
            raise UnsafeOperationError(details)

        progress("Writing the pre-change backup...")
        backup_path = write_backup(plan, backup_root, package.schema)
        deleted = repository.apply_plan(plan, progress)
        progress("Committing the UL_Rates transaction...")
        repository.commit()
    except Exception:
        repository.rollback()
        raise
    finally:
        repository.close()

    verification_repository = ULRatesRepository(dsn, package.schema)
    try:
        progress("Transaction committed. Verifying the saved rows...")
        verify_package_state(
            package, verification_repository, actions, progress_callback
        )
    except Exception as exc:
        backup_note = str(backup_path) if backup_path else "No backup was required"
        raise RateDatabaseError(
            "The transaction COMMITTED, but post-commit verification failed. "
            f"Review UL_Rates before retrying. Backup: {backup_note}. "
            f"Verification error: {exc}"
        ) from exc
    finally:
        verification_repository.close()

    _clear_rate_cache()
    return ExecutionResult(
        str(backup_path) if backup_path else "",
        {
            table: len(rows)
            for table, rows in plan.insert_rows.items() if rows
        },
        deleted,
    )



def verify_package_state(
    package: WorkupPackage,
    repository: ULRatesRepository,
    actions: Mapping[str, LoadAction | str],
    progress_callback: Optional[Callable[[str], None]] = None,
) -> None:
    """Confirm selected package tables exactly match committed database rows."""
    normalized = normalize_actions(actions, package.schema)
    repository.validate_schema()
    for table_name, action in normalized.items():
        if action == LoadAction.SKIP:
            continue
        if progress_callback is not None:
            progress_callback(f"Verifying committed {table_name} rows...")
        data = package.tables[table_name]
        spec = data.spec
        if spec.is_pointer:
            incoming_scopes = {spec.scope(row) for row in data.rows}
            actual = tuple(
                row
                for row in repository.fetch_pointer_rows(
                    table_name, package.plancode
                )
                if spec.scope(row) in incoming_scopes
            )
            if _rows_digest({table_name: actual}) != _rows_digest(
                {table_name: data.rows}
            ):
                raise RateDatabaseError(
                    f"{table_name} does not exactly match the workup after commit."
                )
            continue

        indexes = data.index_values()
        if not indexes:
            continue
        actual = tuple(repository.fetch_rate_rows(table_name, indexes))
        if _rows_digest({table_name: actual}) != _rows_digest(
            {table_name: data.rows}
        ):
            raise RateDatabaseError(
                f"{table_name} does not exactly match the workup after commit."
            )



def load_pointer_rows(
    dsn: str, table_name: str, plancode: str,
    schema: RateSchema = UL_SCHEMA,
) -> TableData:
    spec = schema.specs.get(table_name)
    if spec is None or not spec.is_pointer:
        raise ValueError(f"Unsupported pointer table: {table_name}")
    repository = ULRatesRepository(dsn, schema)
    try:
        repository.validate_schema()
        return TableData(
            spec,
            tuple(repository.fetch_pointer_rows(table_name, plancode.strip())),
        )
    finally:
        repository.close()



def load_rate_index(dsn: str, table_name: str, index: Any,
                    schema: RateSchema = UL_SCHEMA) -> TableData:
    spec = schema.specs.get(table_name)
    if spec is None or spec.is_pointer:
        raise ValueError(f"Unsupported rate table: {table_name}")
    repository = ULRatesRepository(dsn, schema)
    try:
        repository.validate_schema()
        return TableData(
            spec,
            tuple(repository.fetch_rate_rows(
                table_name, {spec.coerce_index(index)})),
        )
    finally:
        repository.close()



def update_pointer_row(
    dsn: str,
    table_name: str,
    original_row: tuple[Any, ...],
    replacement_values: Iterable[Any],
    backup_root: str | Path | None = None,
    schema: RateSchema = UL_SCHEMA,
) -> str:
    guard_data_writable("edit rate pointers")
    spec = schema.specs[table_name]
    if not spec.is_pointer:
        raise ValueError(f"{table_name} is not a pointer table.")
    replacement = coerce_row(spec, replacement_values, source="edited row")
    missing_key_columns = [
        column for column, value in zip(spec.key_columns, spec.key(replacement))
        if value is None and column not in spec.nullable_key_columns
    ]
    if missing_key_columns:
        raise PackageValidationError(
            "Pointer key fields cannot be blank: "
            + ", ".join(missing_key_columns)
        )

    repository = ULRatesRepository(dsn, schema)
    try:
        repository.begin_serializable()
        plan_pos = spec.column_index("Plancode")
        current_rows = repository.fetch_pointer_rows(
            table_name, str(original_row[plan_pos])
        )
        if original_row not in current_rows:
            raise StaleAnalysisError(
                "The selected pointer row changed after it was loaded. Reload it."
            )
        new_key = spec.key(replacement)
        replacement_plan = str(replacement[plan_pos])
        destination_rows = (
            current_rows
            if replacement_plan == str(original_row[plan_pos])
            else repository.fetch_pointer_rows(table_name, replacement_plan)
        )
        for row in destination_rows:
            if (
                not (
                    replacement_plan == str(original_row[plan_pos])
                    and row == original_row
                )
                and spec.key(row) == new_key
            ):
                raise UnsafeOperationError(
                    f"The edited key already exists in {table_name}: {new_key}"
                )
        _validate_pointer_references(repository, spec, replacement)

        backup_plan = ExecutionPlan(
            str(original_row[plan_pos]),
            {table_name: LoadAction.REPLACE},
            {},
            {},
            {},
            {table_name: (original_row,)},
            (),
        )
        backup_path = write_backup(backup_plan, backup_root)
        _delete_exact_rows(repository, spec, (original_row,))
        _insert_rows(repository, spec, (replacement,))
        if replacement not in repository.fetch_pointer_rows(
            table_name, replacement_plan
        ):
            raise RateDatabaseError(
                f"{table_name} update verification failed before commit."
            )
        repository.commit()
        _clear_rate_cache()
        return str(backup_path) if backup_path else ""
    except Exception:
        repository.rollback()
        raise
    finally:
        repository.close()



def delete_pointer_rows(
    dsn: str,
    table_name: str,
    rows: Iterable[tuple[Any, ...]],
    backup_root: str | Path | None = None,
    schema: RateSchema = UL_SCHEMA,
) -> str:
    guard_data_writable("delete rate pointers")
    spec = schema.specs[table_name]
    selected = tuple(rows)
    if not spec.is_pointer:
        raise ValueError(f"{table_name} is not a pointer table.")
    if not selected:
        raise ValueError("No pointer rows were selected.")

    repository = ULRatesRepository(dsn, schema)
    try:
        repository.begin_serializable()
        plan_pos = spec.column_index("Plancode")
        current_by_plan: dict[str, list[tuple[Any, ...]]] = {}
        for plancode in {str(row[plan_pos]) for row in selected}:
            current_by_plan[plancode] = repository.fetch_pointer_rows(
                table_name, plancode
            )
        for row in selected:
            if row not in current_by_plan[str(row[plan_pos])]:
                raise StaleAnalysisError(
                    "A selected pointer row changed after it was loaded. Reload it."
                )

        backup_plan = ExecutionPlan(
            str(selected[0][plan_pos]),
            {table_name: LoadAction.REPLACE},
            {},
            {},
            {},
            {table_name: selected},
            (),
        )
        backup_path = write_backup(backup_plan, backup_root, schema)
        _delete_exact_rows(repository, spec, selected)
        for row in selected:
            remaining = repository.fetch_pointer_rows(
                table_name, str(row[plan_pos])
            )
            if row in remaining:
                raise RateDatabaseError(
                    f"{table_name} delete verification failed before commit."
                )
        repository.commit()
        _clear_rate_cache()
        return str(backup_path) if backup_path else ""
    except Exception:
        repository.rollback()
        raise
    finally:
        repository.close()



def delete_rate_index(
    dsn: str,
    table_name: str,
    index: Any,
    expected_rows: Iterable[tuple[Any, ...]],
    backup_root: str | Path | None = None,
    schema: RateSchema = UL_SCHEMA,
) -> str:
    guard_data_writable("delete rate indexes")
    spec = schema.specs[table_name]
    expected = tuple(expected_rows)
    if spec.is_pointer:
        raise ValueError(f"{table_name} is not a rate table.")
    if not expected:
        raise ValueError("The selected index contains no rows.")

    key = spec.coerce_index(index)
    repository = ULRatesRepository(dsn, schema)
    try:
        repository.begin_serializable()
        current = tuple(repository.fetch_rate_rows(table_name, {key}))
        if _rows_digest({table_name: current}) != _rows_digest(
            {table_name: expected}
        ):
            raise StaleAnalysisError(
                "The selected rate index changed after it was loaded. Reload it."
            )
        references = repository.fetch_index_references(table_name, {key})
        plancodes = sorted(references.get(key, set()))
        if plancodes:
            raise UnsafeOperationError(
                f"Index {index} is still referenced by: {', '.join(plancodes)}. "
                "Remove or repoint those pointer rows first."
            )

        backup_plan = ExecutionPlan(
            f"INDEX_{index}",
            {table_name: LoadAction.REPLACE},
            {},
            {},
            {table_name: frozenset({key})},
            {table_name: current},
            (),
        )
        backup_path = write_backup(backup_plan, backup_root, schema)
        guard_data_writable("delete rate indexes")
        cursor = repository.connect().cursor()
        try:
            cursor.execute(
                f"DELETE FROM {quote_identifier(table_name)} "
                f"WHERE "
                f"{quote_identifier(spec.index_column)} = ?",
                (key,),
            )
        finally:
            cursor.close()
        if repository.fetch_rate_rows(table_name, {key}):
            raise RateDatabaseError(
                f"{table_name} index {index} delete verification failed "
                "before commit."
            )
        repository.commit()
        _clear_rate_cache()
        return str(backup_path) if backup_path else ""
    except Exception:
        repository.rollback()
        raise
    finally:
        repository.close()



def _validate_pointer_references(
    repository: ULRatesRepository,
    spec: TableSpec,
    row: tuple[Any, ...],
) -> None:
    for column, rate_table in spec.pointer_refs.items():
        index = row[spec.column_index(column)]
        if index is None:
            continue
        found = repository.fetch_existing_indexes(rate_table, {index})
        if index not in found:
            raise UnsafeOperationError(
                f"{column} references missing {rate_table} index {index}."
            )



def _delete_exact_rows(
    repository: ULRatesRepository,
    spec: TableSpec,
    rows: Iterable[tuple[Any, ...]],
) -> None:
    guard_data_writable("delete rate data")
    cursor = repository.connect().cursor()
    try:
        for row in rows:
            clauses: list[str] = []
            params: list[Any] = []
            for column, value in zip(spec.key_columns, spec.key(row)):
                database_column = column
                if value is None:
                    clauses.append(f"{quote_identifier(database_column)} IS NULL")
                else:
                    clauses.append(f"{quote_identifier(database_column)} = ?")
                    params.append(value)
            cursor.execute(
                f"DELETE FROM {quote_identifier(spec.name)} WHERE {' AND '.join(clauses)}",
                params,
            )
            if cursor.rowcount != 1:
                raise StaleAnalysisError(
                    f"Expected to delete one {spec.name} row, deleted "
                    f"{cursor.rowcount}."
                )
    finally:
        cursor.close()



def _insert_rows(
    repository: ULRatesRepository,
    spec: TableSpec,
    rows: Iterable[tuple[Any, ...]],
) -> None:
    guard_data_writable("insert rate data")
    rows = tuple(rows)
    if not rows:
        return
    columns = ", ".join(
        quote_identifier(column) for column in spec.columns
    )
    placeholders = ", ".join("?" for _ in spec.columns)
    cursor = repository.connect().cursor()
    try:
        cursor.fast_executemany = True
        cursor.executemany(
            f"INSERT INTO {quote_identifier(spec.name)} ({columns}) "
            f"VALUES ({placeholders})",
            [_database_row(spec, row) for row in rows],
        )
    finally:
        cursor.close()



def _chunks(values, size: int = 500) -> Iterable[tuple]:
    for start in range(0, len(values), size):
        yield tuple(values[start:start + size])



def _clear_rate_cache() -> None:
    from suiteview.core.rates import Rates

    Rates().clear_cache()
    Rates._scr_state_plancodes = None
