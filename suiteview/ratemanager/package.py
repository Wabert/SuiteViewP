"""CSV package validation and row coercion for Rate Manager loads."""

from __future__ import annotations

import csv
import hashlib
from collections import OrderedDict, defaultdict
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any, Iterable, Mapping, Optional

from suiteview.ratemanager.schema import (
    PackageValidationError,
    RateSchema,
    TableSpec,
    UL_SCHEMA,
)



def _parse_integer(value: Any, label: str) -> Optional[int]:
    if value is None or str(value).strip() == "":
        return None
    text = str(value).strip()
    try:
        number = Decimal(text)
    except InvalidOperation as exc:
        raise PackageValidationError(f"{label} must be a whole number, got {text!r}.") from exc
    if number != number.to_integral_value():
        raise PackageValidationError(f"{label} must be a whole number, got {text!r}.")
    return int(number)



def _parse_decimal(value: Any, label: str) -> Optional[Decimal]:
    if value is None or str(value).strip() == "":
        return None
    text = str(value).strip()
    try:
        number = Decimal(text)
    except InvalidOperation as exc:
        raise PackageValidationError(f"{label} must be numeric, got {text!r}.") from exc
    if not number.is_finite():
        raise PackageValidationError(
            f"{label} must be a finite number, got {text!r}."
        )
    return number



def coerce_row(
    spec: TableSpec,
    values: Iterable[Any],
    *,
    source: str = "database",
    row_number: Optional[int] = None,
) -> tuple[Any, ...]:
    values = tuple(values)
    if len(values) != len(spec.columns):
        where = f" row {row_number}" if row_number is not None else ""
        raise PackageValidationError(
            f"{source}{where}: {spec.name} has {len(values)} values; "
            f"expected {len(spec.columns)}."
        )

    coerced: list[Any] = []
    for column, value in zip(spec.columns, values):
        label = f"{source} {spec.name}.{column}"
        if row_number is not None:
            label += f" at row {row_number}"
        if column in spec.integer_columns:
            coerced.append(_parse_integer(value, label))
        elif column in spec.decimal_columns:
            coerced.append(_parse_decimal(value, label))
        elif value is None:
            coerced.append("" if column in spec.empty_string_columns else None)
        else:
            text = str(value).strip()
            coerced.append(
                text
                if text or column in spec.empty_string_columns
                else None
            )
    return tuple(coerced)



def _database_row(spec: TableSpec, row: Iterable[Any]) -> tuple[Any, ...]:
    """Convert validated values to the physical SQL Server parameter types."""
    return tuple(
        float(value)
        if column in spec.decimal_columns and isinstance(value, Decimal)
        else value
        for column, value in zip(spec.columns, row)
    )



def display_value(value: Any) -> Any:
    if value is None:
        return ""
    if isinstance(value, Decimal):
        return format(value, "f")
    return value



def _canonical_value(value: Any) -> str:
    if value is None:
        return "<NULL>"
    if isinstance(value, Decimal):
        return f"D:{format(value.normalize(), 'f')}"
    if isinstance(value, int):
        return f"I:{value}"
    return f"S:{str(value).strip()}"



def _rows_digest(rows_by_table: Mapping[str, Iterable[tuple[Any, ...]]]) -> str:
    digest = hashlib.sha256()
    for table_name in sorted(rows_by_table):
        digest.update(table_name.encode("utf-8"))
        canonical_rows = sorted(
            "\x1f".join(_canonical_value(value) for value in row)
            for row in rows_by_table[table_name]
        )
        for row in canonical_rows:
            digest.update(b"\x1e")
            digest.update(row.encode("utf-8"))
    return digest.hexdigest()



@dataclass(frozen=True)
class TableData:
    spec: TableSpec
    rows: tuple[tuple[Any, ...], ...]

    def rows_by_key(self) -> dict[tuple[Any, ...], tuple[Any, ...]]:
        return {self.spec.key(row): row for row in self.rows}

    def rows_by_index(self) -> dict[int, tuple[tuple[Any, ...], ...]]:
        grouped: dict[int, list[tuple[Any, ...]]] = defaultdict(list)
        for row in self.rows:
            index = self.spec.index_value(row)
            if index is not None:
                grouped[index].append(row)
        return {
            index: tuple(sorted(rows, key=lambda row: self.spec.key(row)))
            for index, rows in grouped.items()
        }

    def index_values(self) -> frozenset[int]:
        return frozenset(self.rows_by_index())

    def to_records(self) -> list[dict[str, Any]]:
        return [
            {
                column: display_value(value)
                for column, value in zip(self.spec.columns, row)
            }
            for row in self.rows
        ]



@dataclass(frozen=True)
class WorkupPackage:
    folder: Path
    plancode: str
    issue_version: int
    tables: "OrderedDict[str, TableData]"
    schema: RateSchema = UL_SCHEMA

    @classmethod
    def load(cls, folder: str | Path,
             schema: RateSchema = UL_SCHEMA) -> "WorkupPackage":
        root = Path(folder).expanduser()
        if not root.is_dir():
            raise PackageValidationError(f"Workup folder does not exist: {root}")

        present_pointers = _present_pointer_files(root, schema)
        tables = _load_package_tables(root, schema, present_pointers)
        plancode, issue_version = _package_identity(tables, schema, present_pointers)
        return cls(root, plancode, issue_version, tables, schema)


def _present_pointer_files(root: Path, schema: RateSchema) -> list[str]:
    # A group participates only when its pointer file is present.
    present = [
        pointer for pointer in schema.groups
        if (root / f"{pointer}.csv").is_file()
    ]
    if not present:
        expected = " or ".join(f"{p}.csv" for p in schema.groups)
        raise PackageValidationError(
            "No workup pointer file found. Provide at least one rate group "
            f"({expected})."
        )
    return present


def _load_package_tables(
    root: Path,
    schema: RateSchema,
    present_pointers: list[str],
) -> "OrderedDict[str, TableData]":
    tables: "OrderedDict[str, TableData]" = OrderedDict()
    for pointer in present_pointers:
        for name in schema.groups[pointer]:
            path = root / f"{name}.csv"
            if not path.is_file():
                raise PackageValidationError(
                    f"Missing required workup file: {path.name} "
                    f"(required by the {pointer} rate group)."
                )
            tables[name] = _read_csv_table(path, schema.specs[name])
    for name, spec in schema.specs.items():
        tables.setdefault(name, TableData(spec, ()))
    return OrderedDict((name, tables[name]) for name in schema.specs)


def _package_identity(
    tables: Mapping[str, TableData],
    schema: RateSchema,
    present_pointers: list[str],
) -> tuple[str, int]:
    identity: tuple[str, int] | None = None
    for pointer in present_pointers:
        pointer_identity = _pointer_identity(tables[pointer], schema.specs[pointer], pointer)
        if pointer_identity is None:
            continue
        if identity is None:
            identity = pointer_identity
        elif pointer_identity != identity:
            _fail_pointer_disagreement(pointer, pointer_identity, identity)
    if identity is None:
        raise PackageValidationError(
            "The workup pointer file(s) contain no rows to load."
        )
    return identity


def _pointer_identity(
    table: TableData,
    spec: TableSpec,
    pointer: str,
) -> tuple[str, int] | None:
    if not table.rows:
        return None
    plancode_pos = spec.column_index("Plancode")
    version_pos = spec.column_index("IssueVersion")
    plancodes = {row[plancode_pos] for row in table.rows}
    versions = {row[version_pos] for row in table.rows}
    if len(plancodes) != 1 or None in plancodes:
        raise PackageValidationError(
            f"{pointer}.csv must contain exactly one nonblank plancode."
        )
    if len(versions) != 1 or None in versions:
        raise PackageValidationError(
            f"{pointer}.csv must contain exactly one IssueVersion."
        )
    return str(next(iter(plancodes))), int(next(iter(versions)))


def _fail_pointer_disagreement(
    pointer: str,
    pointer_identity: tuple[str, int],
    expected_identity: tuple[str, int],
) -> None:
    this_plancode, this_version = pointer_identity
    plancode, issue_version = expected_identity
    raise PackageValidationError(
        "Workup pointer files disagree: "
        f"{pointer}.csv has plancode {this_plancode} / "
        f"IssueVersion {this_version}, but expected plancode "
        f"{plancode} / IssueVersion {issue_version}."
    )



def _read_csv_table(path: Path, spec: TableSpec) -> TableData:
    rows: list[tuple[Any, ...]] = []
    seen_keys: dict[tuple[Any, ...], int] = {}
    with path.open("r", newline="", encoding="utf-8-sig") as handle:
        reader = csv.reader(handle)
        try:
            header = tuple(column.strip() for column in next(reader))
        except StopIteration as exc:
            raise PackageValidationError(f"{path.name} is empty.") from exc
        if header != spec.columns:
            raise PackageValidationError(
                f"{path.name} has the wrong columns.\n"
                f"Expected: {', '.join(spec.columns)}\n"
                f"Found: {', '.join(header)}"
            )
        for row_number, values in enumerate(reader, start=2):
            if not values or not any(str(value).strip() for value in values):
                continue
            row = coerce_row(
                spec, values, source=path.name, row_number=row_number
            )
            key = spec.key(row)
            missing_key_columns = [
                column for column, value in zip(spec.key_columns, key)
                if value is None and column not in spec.nullable_key_columns
            ]
            if missing_key_columns:
                raise PackageValidationError(
                    f"{path.name} row {row_number} has blank key field(s): "
                    f"{', '.join(missing_key_columns)}."
                )
            previous = seen_keys.get(key)
            if previous is not None:
                raise PackageValidationError(
                    f"{path.name} has duplicate key {key} at rows "
                    f"{previous} and {row_number}."
                )
            seen_keys[key] = row_number
            rows.append(row)
    return TableData(spec, tuple(rows))
