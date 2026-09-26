"""Validated Whole Life source imports, reviewable SQL loads and read-only browsing.

These are source-keyed rates, not pre-compiled illustration projections. Imports
never delete rates absent from an input file. CVF sign inference is an explicitly
enabled, audited assumption; other missing actuarial values are not synthesized.
"""

from __future__ import annotations

from suiteview.core.profile_paths import profile_path

import hashlib
import json
from collections import OrderedDict
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from decimal import Decimal
from pathlib import Path
import re
from typing import Any, Mapping
from uuid import uuid4

import pyodbc

from suiteview.core.build_env import guard_data_writable
from suiteview.core.data_sources import UL_RATES_DSN
from suiteview.core.json_store import write_json
from suiteview.core.sql_identifiers import IdentifierCatalog, quote_identifier, qualified_name
from suiteview.ratemanager.package import TableData, _rows_digest
from suiteview.ratemanager.repository import ULRatesRepository, _chunks
from suiteview.ratemanager.schema import (
    PackageValidationError,
    RateDatabaseError,
    StaleAnalysisError,
    UnsafeOperationError,
)
from suiteview.ratemanager.whole_life.schema import PDF_COLUMNS, TABLES, WholeLifeTable

SOURCE_KINDS = {
    "CVF": "Cash value print (CVF)",
    "NSP": "Verified NSP CSV (explicit actuarial basis and units required)",
    "PUI": "Paid-up insurance online table (CJUDTPUI)",
    "IAF": "Whole Life IAF premiums (company required)",
    "Dividend": "Dividend print (existing WL dividend tables)",
    "Dividend map": "Dividend plan-key map workbook",
}
BROWSE_TABLES = (
    "WL_RATE_CV", "WL_RATE_NSP", "WL_RATE_PUI", "WL_RATE_PREM",
    "WL_DIV_HEADER", "WL_RATE_DIV", "WL_DIV_PLANKEY_MAP", "CYBERLIFE_PDF",
)


def _source_info(path: Path) -> dict:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return {"path": str(path), "size": path.stat().st_size, "sha256": digest.hexdigest()}


def _backup_value(value: Any) -> Any:
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, date):
        return value.isoformat()
    return value


def _before_digest(table: str, rows: tuple[tuple[Any, ...], ...]) -> str:
    serialized = sorted(
        json.dumps([_backup_value(value) for value in row], separators=(",", ":"))
        for row in rows
    )
    payload = json.dumps([table, serialized], separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class WholeLifePackage:
    tables: OrderedDict[str, TableData]
    sources: tuple[dict, ...] = ()

    @property
    def row_counts(self) -> dict[str, int]:
        return {name: len(data.rows) for name, data in self.tables.items()}

    @property
    def digest(self) -> str:
        return _rows_digest({name: data.rows for name, data in self.tables.items()})


def parse_sources(
    kind: str, paths: list[str], user_code: str = "",
    *, infer_cvf_negatives: bool = False,
) -> WholeLifePackage:
    if kind not in SOURCE_KINDS:
        raise PackageValidationError(f"Unsupported Whole Life source kind: {kind}.")
    if not paths:
        raise PackageValidationError("Select at least one source file.")
    if not isinstance(infer_cvf_negatives, bool):
        raise PackageValidationError("CVF sign inference must be true or false.")
    if infer_cvf_negatives and kind != "CVF":
        raise PackageValidationError("CVF sign inference requires CVF source files.")
    if kind in ("Dividend", "Dividend map"):
        from suiteview.ratemanager.whole_life import dividend
    else:
        from suiteview.ratemanager.whole_life import parsers
    records: dict[str, list[dict]] = {}
    sources = []
    for filename in paths:
        path = Path(filename).expanduser().resolve(strict=True)
        before = _source_info(path)
        if kind == "Dividend":
            parsed = dividend.parse_dividend(path)
            for header in parsed["WL_DIV_HEADER"]:
                header["MAINT_DT"] = None
                for column in dividend.DATE_COLUMNS:
                    value = header[column]
                    if isinstance(value, date):
                        header[column] = f"{value.month:02d}/{value.day:02d}/{value.year:04d}"
        elif kind == "Dividend map":
            parsed = {"WL_DIV_PLANKEY_MAP": dividend.parse_plan_key_map(path)}
        elif kind == "CVF":
            adjustments = []
            parsed = {"WL_RATE_CV": parsers.parse_cvf(
                path, infer_early_negatives=infer_cvf_negatives,
                inference_audit=adjustments,
            )}
        elif kind == "NSP":
            parsed = {"WL_RATE_NSP": parsers.parse_nsp(path)}
        elif kind == "PUI":
            parsed = {"WL_RATE_PUI": parsers.parse_pui(path)}
        else:
            parsed = {"WL_RATE_PREM": parsers.parse_iaf(path, user_code)}
        if _source_info(path) != before:
            raise PackageValidationError(f"Source changed during parsing: {path}.")
        source = {**before, "kind": kind, "user_code": user_code.strip().upper()}
        if kind == "CVF":
            source["cvf_inference"] = {
                "enabled": infer_cvf_negatives,
                "rule": parsers.CVF_INFERENCE_RULE,
                "adjusted_rows": len(adjustments),
                "adjustments": adjustments,
            }
        sources.append(source)
        for name, rows in parsed.items():
            records.setdefault(name, []).extend(rows)
    tables = OrderedDict(
        (name, definition.data(records[name]))
        for name, definition in TABLES.items() if name in records
    )
    if not tables:
        raise PackageValidationError("No supported Whole Life records were found.")
    return WholeLifePackage(tables, tuple(sources))


def parse_workup(
    files_by_kind: Mapping[str, list[str]], user_code: str = "",
    *, infer_cvf_negatives: bool = False,
) -> WholeLifePackage:
    """Parse all selected source kinds as one reviewable, atomic load package."""
    unknown = set(files_by_kind) - SOURCE_KINDS.keys()
    if unknown:
        raise PackageValidationError(
            "Unsupported Whole Life source kinds: " + ", ".join(sorted(unknown))
        )
    selected = {kind: paths for kind, paths in files_by_kind.items() if paths}
    if not selected:
        raise PackageValidationError("Select at least one source file.")
    if not isinstance(infer_cvf_negatives, bool):
        raise PackageValidationError("CVF sign inference must be true or false.")
    if infer_cvf_negatives and not selected.get("CVF"):
        raise PackageValidationError("CVF sign inference requires CVF source files.")
    code = user_code.strip().upper()
    if selected.get("IAF") and not re.fullmatch(r"[0-9]{2}", code):
        raise PackageValidationError("IAF user/company code must be exactly two digits.")
    tables = {}
    sources = []
    for kind, paths in selected.items():
        package = parse_sources(
            kind, paths, code if kind == "IAF" else "",
            infer_cvf_negatives=infer_cvf_negatives if kind == "CVF" else False,
        )
        overlap = tables.keys() & package.tables.keys()
        if overlap:
            raise PackageValidationError(
                "Source kinds produced overlapping tables: " + ", ".join(sorted(overlap))
            )
        tables.update(package.tables)
        sources.extend(package.sources)
    return WholeLifePackage(
        OrderedDict((name, tables[name]) for name in TABLES if name in tables),
        tuple(sources),
    )


@dataclass(frozen=True)
class TableComparison:
    table: str
    incoming: int
    inserted: int
    unchanged: int
    changed: int
    fingerprint: str = ""
    before_rows: tuple[tuple[Any, ...], ...] = field(default=(), repr=False, compare=False)


@dataclass(frozen=True)
class WholeLifeAnalysis:
    package: WholeLifePackage
    tables: tuple[TableComparison, ...]
    package_digest: str
    database: str

    def summary_records(self) -> list[dict]:
        return [
            {
                "Table": row.table, "Incoming": row.incoming, "New": row.inserted,
                "Unchanged": row.unchanged, "Changed": row.changed,
            }
            for row in self.tables
        ]


def _aliased_column(alias: str, column: str) -> str:
    return f"{alias}.{quote_identifier(column)}"


def _join(definition: WholeLifeTable) -> str:
    return " AND ".join(
        f"{_aliased_column('d', key)} = {_aliased_column('s', key)}"
        for key in definition.keys
    )


def _different(definition: WholeLifeTable) -> str:
    columns = [
        c.name for c in definition.columns
        if c.name not in definition.keys and c.name != "MAINT_DT"
    ]
    return (
        "EXISTS (SELECT " + ", ".join(_aliased_column("d", c) for c in columns)
        + " EXCEPT SELECT " + ", ".join(_aliased_column("s", c) for c in columns) + ")"
    )


class WholeLifeRepository(ULRatesRepository):
    """Short-lived, thread-owned SQL Server repository; never a local fallback."""

    def __init__(self, dsn: str = UL_RATES_DSN, receipt_root: str | Path | None = None):
        super().__init__(dsn)
        self.receipt_root = (
            Path(receipt_root) if receipt_root is not None
            else profile_path('rate_manager_backups') / "whole_life"
        )
        self._stage_number = 0

    def __enter__(self) -> WholeLifeRepository:
        return self

    def __exit__(self, exc_type, exc_value, traceback) -> None:
        self.close()

    def columns(self, table: str) -> tuple[str, ...]:
        if table == "CYBERLIFE_PDF":
            return PDF_COLUMNS
        if table not in TABLES:
            raise PackageValidationError(f"Unsupported Whole Life table: {table}.")
        return TABLES[table].spec.columns

    def _validate_table(self, definition: WholeLifeTable) -> None:
        cursor = self.connect().cursor()
        try:
            actual = {
                row.column_name: row
                for row in cursor.columns(table=definition.name, schema="dbo")
            }
            if not actual:
                raise RateDatabaseError(
                    f"dbo.{definition.name} is missing. Create the Whole Life "
                    "tables first; existing dividend tables require their original schema."
                )
            for column in definition.columns:
                found = actual.get(column.name)
                if found is None:
                    raise RateDatabaseError(f"{definition.name}.{column.name} is missing.")
                type_name = found.type_name.lower()
                if type_name in ("varchar", "char"):
                    type_name += f"({found.column_size})"
                elif type_name in ("decimal", "numeric"):
                    type_name = f"decimal({found.column_size},{found.decimal_digits})"
                if type_name != column.sql_type or bool(found.nullable) != column.nullable:
                    raise RateDatabaseError(
                        f"{definition.name}.{column.name}: expected {column.sql_type}, "
                        f"nullable={column.nullable}; found {type_name}, "
                        f"nullable={bool(found.nullable)}. No schema was altered."
                    )
            keys = sorted(
                cursor.primaryKeys(table=definition.name, schema="dbo"),
                key=lambda row: row.key_seq,
            )
            if tuple(row.column_name for row in keys) != definition.keys:
                raise RateDatabaseError(
                    f"{definition.name}: primary key must be {definition.keys}."
                )
        finally:
            cursor.close()

    def create_tables(self) -> tuple[str, ...]:
        guard_data_writable("create Whole Life rate tables")
        cursor = self.connect().cursor()
        created = []
        committed = False
        try:
            cursor.execute("SET XACT_ABORT ON")
            for name, definition in TABLES.items():
                if not definition.create:
                    continue
                exists = cursor.execute(
                    "SELECT OBJECT_ID(?, 'U')", (f"dbo.{name}",)
                ).fetchone()[0]
                if exists is None:
                    cursor.execute(definition.ddl())
                    created.append(name)
                self._validate_table(definition)
            self.commit()
            committed = True
        finally:
            if not committed:
                self.rollback()
            cursor.close()
        return tuple(created)

    def _stage(self, package: WholeLifePackage) -> dict[str, str]:
        if not package.tables:
            raise PackageValidationError("Cannot load an empty Whole Life package.")
        stages = {}
        cursor = self.connect().cursor()
        try:
            for name, data in package.tables.items():
                if name not in TABLES or data.spec != TABLES[name].spec:
                    raise PackageValidationError(f"Invalid table definition: {name}.")
                definition = TABLES[name]
                self._validate_table(definition)
                if not data.rows:
                    raise PackageValidationError(f"{name} has no rows to load.")
                self._stage_number += 1
                stage = f"#wl_stage_{self._stage_number}"
                cursor.execute(definition.ddl(stage))
                stages[name] = stage
                stage_name = quote_identifier(stage)
                columns = ", ".join(quote_identifier(c) for c in data.spec.columns)
                placeholders = ", ".join(
                    "CONVERT(date, ?, 23)" if c.sql_type == "date" else "?"
                    for c in definition.columns
                )
                # Explicit types avoid SQL Server temp-table metadata discovery
                # failures in fast_executemany, and retain decimal precision.
                sizes = []
                for column in definition.columns:
                    sql_type = column.sql_type
                    if sql_type.startswith(("varchar(", "char(")):
                        sizes.append((pyodbc.SQL_VARCHAR, int(sql_type.split("(")[1][:-1]), 0))
                    elif sql_type.startswith("decimal("):
                        precision, scale = map(int, sql_type[8:-1].split(","))
                        sizes.append((pyodbc.SQL_DECIMAL, precision, scale))
                    elif sql_type == "float":
                        sizes.append((pyodbc.SQL_DOUBLE, 0, 0))
                    elif sql_type == "date":
                        # The legacy SQL Server ODBC driver cannot bind SQL_DATE
                        # in parameter arrays. Convert an exact ISO string in SQL.
                        sizes.append((pyodbc.SQL_VARCHAR, 10, 0))
                    else:
                        sizes.append((pyodbc.SQL_INTEGER, 0, 0))
                cursor.setinputsizes(sizes)
                cursor.fast_executemany = True
                sql = f"INSERT INTO {stage_name} ({columns}) VALUES ({placeholders})"
                for batch in _chunks(data.rows, size=5000):
                    bound = []
                    for row in batch:
                        normalized = definition.normalize(row)
                        bound.append(tuple(
                            float(value)
                            if column.sql_type == "float" and value is not None
                            else value
                            for column, value in zip(definition.columns, normalized)
                        ))
                    cursor.executemany(sql, bound)
                cursor.fast_executemany = False
                cursor.setinputsizes([])
            self.commit()
        finally:
            cursor.close()
        return stages

    def _compare(
        self, package: WholeLifePackage, stages: dict[str, str], *, locked: bool = False,
    ) -> tuple[TableComparison, ...]:
        comparisons = []
        cursor = self.connect().cursor()
        try:
            for name, data in package.tables.items():
                definition = TABLES[name]
                stage = quote_identifier(stages[name])
                target = qualified_name("dbo", name)
                hint = " WITH (UPDLOCK, HOLDLOCK)" if locked else ""
                joined = (
                    f"FROM {stage} s LEFT JOIN {target} d{hint} ON {_join(definition)}"
                )
                absent = f"{_aliased_column('d', definition.keys[0])} IS NULL"
                inserted, changed = cursor.execute(
                    f"SELECT COALESCE(SUM(CASE WHEN {absent} THEN 1 ELSE 0 END), 0), "
                    f"COALESCE(SUM(CASE WHEN {absent} THEN 0 WHEN diff.changed = 1 "
                    f"THEN 1 ELSE 0 END), 0) {joined} "
                    f"OUTER APPLY (SELECT CASE WHEN {_different(definition)} "
                    "THEN 1 ELSE 0 END AS changed) diff"
                ).fetchone()
                old_rows = ()
                if changed:
                    selected = ", ".join(_aliased_column("d", c) for c in data.spec.columns)
                    old_rows = tuple(
                        tuple(row)
                        for row in cursor.execute(
                            f"SELECT {selected} FROM {stage} s "
                            f"JOIN {target} d{hint} ON {_join(definition)} "
                            f"WHERE {_different(definition)}"
                        ).fetchall()
                    )
                unchanged = len(data.rows) - inserted - changed
                fingerprint = _before_digest(name, old_rows)
                comparisons.append(TableComparison(
                    name, len(data.rows), inserted, unchanged, changed,
                    fingerprint, old_rows,
                ))
        finally:
            cursor.close()
        return tuple(comparisons)

    def _validate_dividend_schedules(
        self, package: WholeLifePackage, stages: dict[str, str],
    ) -> None:
        group = {"WL_DIV_HEADER", "WL_RATE_DIV"}
        if not group.intersection(package.tables):
            return
        if not group.issubset(package.tables):
            raise PackageValidationError(
                "Dividend headers and their complete rate schedules must load together."
            )
        headers = package.tables["WL_DIV_HEADER"]
        rates = package.tables["WL_RATE_DIV"]
        header_records = {
            row[0]: dict(zip(headers.spec.columns, row)) for row in headers.rows
        }
        durations: dict[str, set[int]] = {}
        for row in rates.rows:
            header_id, record_type, duration = row[:3]
            header = header_records.get(header_id)
            if header is None or record_type != header["RECORD_TYPE"]:
                raise PackageValidationError(f"Dividend rate has no matching header: {header_id}.")
            durations.setdefault(header_id, set()).add(duration)
        for header_id, header in header_records.items():
            expected = set(range(header["FIRST_DURATION"], header["LAST_DURATION"] + 1))
            if durations.get(header_id, set()) != expected:
                raise PackageValidationError(
                    f"Dividend schedule {header_id} is incomplete. Load its full duration range."
                )
        cursor = self.connect().cursor()
        try:
            header_stage = stages["WL_DIV_HEADER"]
            rate_stage = stages["WL_RATE_DIV"]
            outside = cursor.execute(
                f"SELECT TOP (1) {_aliased_column('d', 'HEADER_ID')} "
                f"FROM {qualified_name('dbo', 'WL_RATE_DIV')} d "
                f"JOIN {quote_identifier(header_stage)} s "
                f"ON {_aliased_column('d', 'HEADER_ID')} = {_aliased_column('s', 'HEADER_ID')} "
                f"WHERE {_aliased_column('d', 'DURATION')} < {_aliased_column('s', 'FIRST_DURATION')} "
                f"OR {_aliased_column('d', 'DURATION')} > {_aliased_column('s', 'LAST_DURATION')}"
            ).fetchone()
            if outside:
                raise UnsafeOperationError(
                    f"Dividend {outside[0]} would retain rates outside its new duration "
                    "range. Range contraction requires a separately reviewed whole-schedule "
                    "replacement; this loader never deletes absent rates."
                )
            missing_parent = cursor.execute(
                f"SELECT TOP (1) other.{quote_identifier('HEADER_ID')} "
                f"FROM {quote_identifier(rate_stage)} s "
                f"JOIN {qualified_name('dbo', 'WL_RATE_DIV')} d "
                f"ON {_aliased_column('d', 'HEADER_ID')} = {_aliased_column('s', 'HEADER_ID')} "
                f"AND {_aliased_column('d', 'DURATION')} = {_aliased_column('s', 'DURATION')} "
                f"JOIN {quote_identifier(header_stage)} h "
                f"ON h.{quote_identifier('HEADER_ID')} = {_aliased_column('s', 'HEADER_ID')} "
                f"JOIN {qualified_name('dbo', 'WL_DIV_HEADER')} other "
                "ON other.[USER_CODE] = h.[USER_CODE] AND other.[PUA_KEY] = h.[PUA_KEY] "
                "AND other.[RECORD_TYPE] = h.[RECORD_TYPE] "
                "AND COALESCE(other.[PUA_KEY_USER_DEFINED], '') = "
                "COALESCE(h.[PUA_KEY_USER_DEFINED], '') "
                "WHERE h.[PUA_PARTICIPATING] = '2' "
                "AND other.[PUA_PARTICIPATING] = '2' AND EXISTS "
                "(SELECT d.[PUA_DIV_CASH], d.[PUA_DIV_PUA], d.[PUA_DIV_OYT] "
                "EXCEPT SELECT s.[PUA_DIV_CASH], s.[PUA_DIV_PUA], s.[PUA_DIV_OYT]) "
                f"AND NOT EXISTS (SELECT 1 FROM {header_stage} included "
                "WHERE included.[HEADER_ID] = other.[HEADER_ID])"
            ).fetchone()
            if missing_parent:
                raise UnsafeOperationError(
                    f"Shared PUA factors also affect dividend {missing_parent[0]}, which "
                    "is absent from this package. Supply the complete affected parent "
                    "schedules so their denormalized PUA values update together."
                )
        finally:
            cursor.close()

    def _validate_cvf_ranges(
        self, package: WholeLifePackage, stages: dict[str, str],
    ) -> None:
        if "WL_RATE_CV" not in package.tables:
            return
        keys = tuple(key for key in TABLES["WL_RATE_CV"].keys if key != "DURATION")
        selected = ", ".join(quote_identifier(key) for key in (*keys, "FIRST_DURATION", "LAST_DURATION"))
        joined = " AND ".join(
            f"{_aliased_column('d', key)} = {_aliased_column('s', key)}"
            for key in keys
        )
        cursor = self.connect().cursor()
        try:
            outside = cursor.execute(
                f"SELECT TOP (1) {_aliased_column('d', 'RATE_KEY')}, {_aliased_column('d', 'ISSUE_AGE')} "
                f"FROM {qualified_name('dbo', 'WL_RATE_CV')} d JOIN "
                f"(SELECT DISTINCT {selected} FROM {quote_identifier(stages['WL_RATE_CV'])}) s "
                f"ON {joined} WHERE {_aliased_column('d', 'DURATION')} < {_aliased_column('s', 'FIRST_DURATION')} "
                f"OR {_aliased_column('d', 'DURATION')} > {_aliased_column('s', 'LAST_DURATION')}"
            ).fetchone()
            if outside:
                raise UnsafeOperationError(
                    f"CV key {outside[0]}, age {outside[1]} would retain rates outside "
                    "the new duration range. Review a whole-schedule replacement "
                    "separately; this loader never deletes absent rates."
                )
        finally:
            cursor.close()

    def analyze(self, package: WholeLifePackage) -> WholeLifeAnalysis:
        try:
            stages = self._stage(package)
            self._validate_cvf_ranges(package, stages)
            self._validate_dividend_schedules(package, stages)
            return WholeLifeAnalysis(
                package, self._compare(package, stages), package.digest,
                self.test_connection(),
            )
        finally:
            self.rollback()

    def apply(self, analysis: WholeLifeAnalysis, replace_tables: set[str]) -> dict:
        guard_data_writable("load Whole Life rates")
        if analysis.package.digest != analysis.package_digest:
            raise StaleAnalysisError("Source package changed. Preview and analyze it again.")
        if not replace_tables.issubset(analysis.package.tables):
            raise UnsafeOperationError("Replacement approvals contain an unrelated table.")
        blocked = [
            row.table for row in analysis.tables
            if row.changed and row.table not in replace_tables
        ]
        if blocked:
            raise UnsafeOperationError(
                "Approve changed rows explicitly before loading: " + ", ".join(blocked)
            )
        cursor = self.connect().cursor()
        receipt_path = self.receipt_root / f"{uuid4().hex}.json"
        try:
            if self.test_connection() != analysis.database:
                raise StaleAnalysisError("Target database changed. Analyze again.")
            stages = self._stage(analysis.package)
            self.begin_serializable()
            cursor.execute("SET LOCK_TIMEOUT 15000")
            self._validate_cvf_ranges(analysis.package, stages)
            self._validate_dividend_schedules(analysis.package, stages)
            current = self._compare(analysis.package, stages, locked=True)
            if current != analysis.tables:
                raise StaleAnalysisError(
                    "Database rows changed after analysis. Analyze and review again."
                )
            receipt = {
                "status": "prepared; this is not proof of commit",
                "database": analysis.database,
                "created_at": datetime.now(timezone.utc).isoformat(),
                "package_sha256": analysis.package_digest,
                "sources": list(analysis.package.sources),
                "tables": analysis.summary_records(),
                "before_rows": {
                    row.table: [
                        {
                            column: _backup_value(value)
                            for column, value in zip(
                                TABLES[row.table].spec.columns, before_row
                            )
                        }
                        for before_row in row.before_rows
                    ]
                    for row in current if row.before_rows
                },
            }
            guard_data_writable("load Whole Life rates")
            write_json(receipt_path, receipt)
            for row in current:
                name = row.table
                definition = TABLES[name]
                stage = quote_identifier(stages[name])
                target = qualified_name("dbo", name)
                if row.changed:
                    assignments = ", ".join(
                        f"{_aliased_column('d', c.name)} = " + (
                            "CONVERT(varchar(10), GETDATE(), 101)"
                            if c.name == "MAINT_DT" else _aliased_column("s", c.name)
                        )
                        for c in definition.columns if c.name not in definition.keys
                    )
                    cursor.execute(
                        f"UPDATE d SET {assignments} FROM {target} d "
                        f"JOIN {stage} s ON {_join(definition)} "
                        f"WHERE {_different(definition)}"
                    )
                if row.inserted:
                    columns = ", ".join(quote_identifier(c.name) for c in definition.columns)
                    selected = ", ".join(
                        "CONVERT(varchar(10), GETDATE(), 101)"
                        if c.name == "MAINT_DT" else _aliased_column("s", c.name)
                        for c in definition.columns
                    )
                    cursor.execute(
                        f"INSERT INTO {target} ({columns}) SELECT {selected} "
                        f"FROM {stage} s WHERE NOT EXISTS "
                        f"(SELECT 1 FROM {target} d WHERE {_join(definition)})"
                    )
            verified = self._compare(analysis.package, stages, locked=True)
            if any(row.inserted or row.changed for row in verified):
                raise RateDatabaseError("Whole Life write verification failed; rolling back.")
            self.commit()
            persisted = self._compare(analysis.package, stages)
            if any(row.inserted or row.changed for row in persisted):
                raise RateDatabaseError(
                    f"Whole Life data committed but post-commit verification failed. "
                    f"Inspect the backup receipt: {receipt_path}"
                )
            receipt["status"] = "committed and verified"
            receipt["committed_at"] = datetime.now(timezone.utc).isoformat()
            try:
                write_json(receipt_path, receipt)
            except OSError as exc:
                raise RateDatabaseError(
                    f"Rates committed and verified, but receipt update failed: {receipt_path}"
                ) from exc
            return {
                "inserted": {row.table: row.inserted for row in current},
                "updated": {row.table: row.changed for row in current},
                "receipt": str(receipt_path),
            }
        finally:
            # Ends either the failed write transaction or the post-commit read.
            self.rollback()
            cursor.close()

    def browse(
        self, table: str, filters: dict[str, str], limit: int = 1000,
    ) -> list[dict]:
        columns = self.columns(table)
        catalog = IdentifierCatalog.from_tables(
            BROWSE_TABLES,
            {table: columns},
        )
        table_name = catalog.quote_table(table, "dbo")
        if not 1 <= limit <= 10000:
            raise PackageValidationError("Row limit must be between 1 and 10000.")
        if not set(filters).issubset(columns):
            raise PackageValidationError("Filters contain an unknown column.")
        where = " AND ".join(catalog.quote_column(table, column) + " = ?" for column in filters)
        selected = ", ".join(catalog.quote_column(table, column) for column in columns)
        keys = PDF_COLUMNS if table == "CYBERLIFE_PDF" else TABLES[table].keys
        order = ", ".join(catalog.quote_column(table, column) for column in keys)
        cursor = self.connect().cursor()
        try:
            cursor.execute(
                f"SELECT TOP (?) {selected} FROM {table_name} "
                + (f"WHERE {where} " if where else "")
                + f"ORDER BY {order}",
                (limit, *filters.values()),
            )
            return [dict(zip(columns, row)) for row in cursor.fetchall()]
        finally:
            self.rollback()
            cursor.close()
