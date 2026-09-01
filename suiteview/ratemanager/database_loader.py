"""Safe UL_Rates loading and maintenance for Rate Workup output."""

from __future__ import annotations

import csv
import hashlib
import json
import re
from collections import OrderedDict, defaultdict
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal, InvalidOperation
from enum import Enum
from pathlib import Path
from typing import Any, Callable, Iterable, Mapping, Optional

import pyodbc


class RateDatabaseError(RuntimeError):
    """Base error for Rate Manager database operations."""


class PackageValidationError(RateDatabaseError):
    """A workup folder is incomplete or contains invalid data."""


class UnsafeOperationError(RateDatabaseError):
    """A requested database operation would violate a safety invariant."""


class StaleAnalysisError(RateDatabaseError):
    """The database changed after the user reviewed the analysis."""


class LoadAction(str, Enum):
    SKIP = "skip"
    INSERT = "insert"
    REPLACE = "replace"


@dataclass(frozen=True)
class TableSpec:
    name: str
    columns: tuple[str, ...]
    key_columns: tuple[str, ...]
    integer_columns: frozenset[str] = frozenset()
    decimal_columns: frozenset[str] = frozenset()
    nullable_key_columns: frozenset[str] = frozenset()
    empty_string_columns: frozenset[str] = frozenset()
    index_column: str = ""
    pointer_refs: Mapping[str, str] = field(default_factory=dict)
    scope_columns: tuple[str, ...] = ()

    @property
    def is_pointer(self) -> bool:
        return not self.index_column

    @property
    def collision_scope_columns(self) -> tuple[str, ...]:
        """Columns that define the ownership unit for a pointer table.

        Existing rows only conflict with an incoming workup when they share
        every one of these column values. Pointer tables default to
        ``Plancode`` so an entire plancode is managed together, but tables
        such as ``POINT_BENEFIT`` narrow the scope further (e.g. by
        ``BenefitType``) so unrelated benefit types never block each other.
        """
        if self.scope_columns:
            return self.scope_columns
        return ("Plancode",) if self.is_pointer else ()

    def column_index(self, column: str) -> int:
        return self.columns.index(column)

    def key(self, row: tuple[Any, ...]) -> tuple[Any, ...]:
        return tuple(row[self.column_index(column)] for column in self.key_columns)

    def scope(self, row: tuple[Any, ...]) -> tuple[Any, ...]:
        return tuple(
            row[self.column_index(column)]
            for column in self.collision_scope_columns
        )

    def scope_detail(self, rows: Iterable[tuple[Any, ...]]) -> str:
        """Human-readable description of the non-plancode scope values."""
        extra = [
            column for column in self.collision_scope_columns
            if column != "Plancode"
        ]
        rows = list(rows)
        if not extra or not rows:
            return ""
        parts = []
        for column in extra:
            pos = self.column_index(column)
            values = sorted({str(row[pos]) for row in rows})
            parts.append(f"{column} {', '.join(values)}")
        return " (" + "; ".join(parts) + ")"

    def index_value(self, row: tuple[Any, ...]) -> Optional[Any]:
        if not self.index_column:
            return None
        return row[self.column_index(self.index_column)]

    @property
    def index_is_integer(self) -> bool:
        """Whether this table's index is numeric rather than an identifier.

        UL rate tables key on integer indexes. The TERM_* tables key on
        varchar identifiers such as '1001_PL', where the suffix distinguishes
        otherwise-colliding index spaces, so they must never be coerced to
        numbers.
        """
        return bool(self.index_column) and self.index_column in self.integer_columns

    def coerce_index(self, value: Any) -> Any:
        """Normalize a database index value to match the in-memory rows."""
        if value is None:
            return None
        return int(value) if self.index_is_integer else str(value).strip()


PVSRB_COLUMNS = (
    "Plancode", "IssueVersion", "Sex", "Rateclass", "Band", "State",
    "Index(PREMLOAD)", "Index(TRGPREM)", "Index(MFEE)", "Index(SCR)",
    "Index(COI)", "Index(EPU)", "Index(GLP)", "MORTID", "Index(SHDINT)",
    "Index(TRAD_CV)",
)
BENEFIT_COLUMNS = (
    "Plancode", "BenefitType", "Benefit", "IssueVersion", "Sex", "Rateclass",
    "Band", "Index(BENCOI)", "Index(BENTRG)",
)

TABLE_SPECS: "OrderedDict[str, TableSpec]" = OrderedDict([
    ("POINT_PVSRB", TableSpec(
        name="POINT_PVSRB",
        columns=PVSRB_COLUMNS,
        key_columns=(
            "Plancode", "IssueVersion", "Sex", "Rateclass", "Band", "State",
        ),
        integer_columns=frozenset({
            "IssueVersion", "Band", "Index(PREMLOAD)", "Index(TRGPREM)",
            "Index(MFEE)", "Index(SCR)", "Index(COI)", "Index(EPU)",
            "Index(GLP)", "Index(SHDINT)", "Index(TRAD_CV)",
        }),
        pointer_refs={
            "Index(TRGPREM)": "RATE_TRGPREM",
            "Index(SCR)": "RATE_SCR",
            "Index(COI)": "RATE_COI",
            "Index(EPU)": "RATE_EPU",
        },
    )),
    ("RATE_COI", TableSpec(
        name="RATE_COI",
        columns=("Index(COI)", "Scale", "IssueAge", "Duration", "Rate"),
        key_columns=("Index(COI)", "Scale", "IssueAge", "Duration"),
        integer_columns=frozenset({
            "Index(COI)", "Scale", "IssueAge", "Duration",
        }),
        decimal_columns=frozenset({"Rate"}),
        index_column="Index(COI)",
    )),
    ("RATE_TRGPREM", TableSpec(
        name="RATE_TRGPREM",
        columns=(
            "Index(TRGPREM)", "IssueAge", "Rate(MTP)", "Rate(CTP)",
            "Rate(TBL4PREM)", "Rate(TBL1MTP)", "Rate(TBL1CTP)",
        ),
        key_columns=("Index(TRGPREM)", "IssueAge"),
        integer_columns=frozenset({"Index(TRGPREM)", "IssueAge"}),
        decimal_columns=frozenset({
            "Rate(MTP)", "Rate(CTP)", "Rate(TBL4PREM)", "Rate(TBL1MTP)",
            "Rate(TBL1CTP)",
        }),
        index_column="Index(TRGPREM)",
    )),
    ("RATE_SCR", TableSpec(
        name="RATE_SCR",
        columns=("Index(SCR)", "IssueAge", "Duration", "Rate"),
        key_columns=("Index(SCR)", "IssueAge", "Duration"),
        integer_columns=frozenset({"Index(SCR)", "IssueAge", "Duration"}),
        decimal_columns=frozenset({"Rate"}),
        index_column="Index(SCR)",
    )),
    ("RATE_EPU", TableSpec(
        name="RATE_EPU",
        columns=("Index(EPU)", "Scale", "IssueAge", "Duration", "Rate"),
        key_columns=("Index(EPU)", "Scale", "IssueAge", "Duration"),
        integer_columns=frozenset({
            "Index(EPU)", "Scale", "IssueAge", "Duration",
        }),
        decimal_columns=frozenset({"Rate"}),
        index_column="Index(EPU)",
    )),
    ("POINT_BENEFIT", TableSpec(
        name="POINT_BENEFIT",
        columns=BENEFIT_COLUMNS,
        key_columns=(
            "Plancode", "BenefitType", "Benefit", "IssueVersion", "Sex",
            "Rateclass", "Band",
        ),
        integer_columns=frozenset({
            "IssueVersion", "Band", "Index(BENCOI)", "Index(BENTRG)",
        }),
        nullable_key_columns=frozenset({"Benefit"}),
        empty_string_columns=frozenset({"Benefit"}),
        scope_columns=("Plancode", "BenefitType"),
        pointer_refs={
            "Index(BENCOI)": "RATE_BENCOI",
            "Index(BENTRG)": "RATE_BENTRG",
        },
    )),
    ("RATE_BENCOI", TableSpec(
        name="RATE_BENCOI",
        columns=("Index(BENCOI)", "Scale", "IssueAge", "Duration", "Rate"),
        key_columns=("Index(BENCOI)", "Scale", "IssueAge", "Duration"),
        integer_columns=frozenset({
            "Index(BENCOI)", "Scale", "IssueAge", "Duration",
        }),
        decimal_columns=frozenset({"Rate"}),
        index_column="Index(BENCOI)",
    )),
    ("RATE_BENTRG", TableSpec(
        name="RATE_BENTRG",
        columns=("Index(BENTRG)", "IssueAge", "Rate(MTP)", "Rate(CTP)"),
        key_columns=("Index(BENTRG)", "IssueAge"),
        integer_columns=frozenset({"Index(BENTRG)", "IssueAge"}),
        decimal_columns=frozenset({"Rate(MTP)", "Rate(CTP)"}),
        index_column="Index(BENTRG)",
    )),
])

TERM_POINT_PV_COLUMNS = (
    "Plancode", "IssueVersion", "Index(MODEFACT)", "Index(BANDSPEC)", "FEE",
)
TERM_POINT_PVSRB_COLUMNS = (
    "Plancode", "IssueVersion", "Sex", "Rateclass", "Band", "Index(PREM)",
)
TERM_POINT_BENEFIT_COLUMNS = (
    "Plancode", "IssueVersion", "BenefitType", "Benefit",
    "Sex", "Rateclass", "Band", "Index(BEN)",
)

# The Term family. Every Index(...) column here is varchar in SQL Server, so
# none of them appear in integer_columns — see TableSpec.index_is_integer.
TERM_TABLE_SPECS: "OrderedDict[str, TableSpec]" = OrderedDict([
    ("TERM_POINT_PV", TableSpec(
        name="TERM_POINT_PV",
        columns=TERM_POINT_PV_COLUMNS,
        key_columns=("Plancode", "IssueVersion"),
        integer_columns=frozenset({"IssueVersion"}),
        decimal_columns=frozenset({"FEE"}),
        pointer_refs={
            "Index(MODEFACT)": "TERM_RATE_MODEFACT",
            "Index(BANDSPEC)": "TERM_RATE_BANDSPECS",
        },
    )),
    ("TERM_RATE_MODEFACT", TableSpec(
        name="TERM_RATE_MODEFACT",
        columns=("Index(MODEFACT)", "PACS", "PACQ", "PACM",
                 "DIRS", "DIRQ", "DIRM", "PACS_FEE", "PACQ_FEE", "PACM_FEE",
                 "DIRS_FEE", "DIRQ_FEE", "DIRM_FEE"),
        key_columns=("Index(MODEFACT)",),
        decimal_columns=frozenset({
            "PACS", "PACQ", "PACM", "DIRS", "DIRQ", "DIRM",
            "PACS_FEE", "PACQ_FEE", "PACM_FEE",
            "DIRS_FEE", "DIRQ_FEE", "DIRM_FEE",
        }),
        index_column="Index(MODEFACT)",
    )),
    ("TERM_RATE_BANDSPECS", TableSpec(
        name="TERM_RATE_BANDSPECS",
        columns=("Index(BANDSPEC)", "SpecifiedAmount", "Band", "BandCode",
                 "Issue_Date"),
        key_columns=("Index(BANDSPEC)", "Issue_Date", "Band"),
        integer_columns=frozenset({"Band"}),
        decimal_columns=frozenset({"SpecifiedAmount"}),
        index_column="Index(BANDSPEC)",
    )),
    ("TERM_POINT_PVSRB", TableSpec(
        name="TERM_POINT_PVSRB",
        columns=TERM_POINT_PVSRB_COLUMNS,
        key_columns=("Plancode", "IssueVersion", "Sex", "Rateclass", "Band"),
        integer_columns=frozenset({"IssueVersion"}),
        pointer_refs={"Index(PREM)": "TERM_RATE_PREM"},
    )),
    ("TERM_RATE_PREM", TableSpec(
        name="TERM_RATE_PREM",
        columns=("Index(PREM)", "Scale", "IssueAge", "Duration", "Rate"),
        key_columns=("Index(PREM)", "Scale", "IssueAge", "Duration"),
        integer_columns=frozenset({"Scale", "IssueAge", "Duration"}),
        decimal_columns=frozenset({"Rate"}),
        index_column="Index(PREM)",
    )),
    ("TERM_POINT_BENEFIT", TableSpec(
        name="TERM_POINT_BENEFIT",
        columns=TERM_POINT_BENEFIT_COLUMNS,
        key_columns=(
            "Plancode", "IssueVersion", "BenefitType", "Benefit",
            "Sex", "Rateclass", "Band",
        ),
        integer_columns=frozenset({"IssueVersion"}),
        scope_columns=("Plancode", "BenefitType"),
        pointer_refs={"Index(BEN)": "TERM_RATE_BEN"},
    )),
    ("TERM_RATE_BEN", TableSpec(
        name="TERM_RATE_BEN",
        columns=("Index(BEN)", "Scale", "IssueAge", "Duration", "Rate"),
        key_columns=("Index(BEN)", "Scale", "IssueAge", "Duration"),
        integer_columns=frozenset({"Scale", "IssueAge", "Duration"}),
        decimal_columns=frozenset({"Rate"}),
        index_column="Index(BEN)",
    )),
])


def _build_references(
    specs: "OrderedDict[str, TableSpec]",
) -> dict[str, tuple[str, str]]:
    references: dict[str, tuple[str, str]] = {}
    for pointer_name, pointer_spec in specs.items():
        for column, rate_table in pointer_spec.pointer_refs.items():
            references[rate_table] = (pointer_name, column)
    return references


def _build_table_groups(
    specs: "OrderedDict[str, TableSpec]",
) -> "OrderedDict[str, tuple[str, ...]]":
    """Map each pointer table to the full set of files that load together.

    A workup folder is organized into independent rate *groups*, one per
    pointer table. The base-rate group (``POINT_PVSRB``) owns the general
    rate tables; the benefit group (``POINT_BENEFIT``) owns the benefit rate
    tables. Either group may be loaded on its own — deleting every file in a
    group simply means that group is not part of the workup.
    """
    groups: "OrderedDict[str, tuple[str, ...]]" = OrderedDict()
    for name, spec in specs.items():
        if spec.is_pointer:
            groups[name] = (name, *spec.pointer_refs.values())
    return groups


@dataclass(frozen=True)
class RateSchema:
    """One family of rate tables that is validated and loaded together.

    Rate Manager drives two independent families against the same UL_Rates
    database — the UL tables (integer indexes) and the TERM tables (varchar
    indexes). Every function below is parameterized by the schema it is
    handed so the two families never share state or leak into each other's
    load plans.
    """

    name: str
    specs: "OrderedDict[str, TableSpec]"
    groups: "OrderedDict[str, tuple[str, ...]]"
    references: Mapping[str, tuple[str, str]]
    pointer_names: tuple[str, ...]

    @classmethod
    def build(cls, name: str,
              specs: "OrderedDict[str, TableSpec]") -> "RateSchema":
        return cls(
            name=name,
            specs=specs,
            groups=_build_table_groups(specs),
            references=_build_references(specs),
            pointer_names=tuple(
                table for table, spec in specs.items() if spec.is_pointer
            ),
        )


UL_SCHEMA = RateSchema.build("UL", TABLE_SPECS)
TERM_SCHEMA = RateSchema.build("Term", TERM_TABLE_SPECS)

SCHEMAS: "OrderedDict[str, RateSchema]" = OrderedDict([
    (UL_SCHEMA.name, UL_SCHEMA),
    (TERM_SCHEMA.name, TERM_SCHEMA),
])

RATE_REFERENCES: Mapping[str, tuple[str, str]] = UL_SCHEMA.references
TABLE_GROUPS: "OrderedDict[str, tuple[str, ...]]" = UL_SCHEMA.groups


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

        # A group participates only when its pointer file is present. This lets
        # a folder hold just the benefit files (or just the base files) without
        # forcing the other group's CSVs to exist.
        present_pointers = [
            pointer for pointer in schema.groups
            if (root / f"{pointer}.csv").is_file()
        ]
        if not present_pointers:
            expected = " or ".join(f"{p}.csv" for p in schema.groups)
            raise PackageValidationError(
                "No workup pointer file found. Provide at least one rate group "
                f"({expected})."
            )

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

        # Absent groups are represented by empty tables so every downstream
        # consumer can address all table names uniformly (they simply load
        # nothing and default to Skip).
        for name, spec in schema.specs.items():
            tables.setdefault(name, TableData(spec, ()))
        tables = OrderedDict((name, tables[name]) for name in schema.specs)

        plancode: Optional[str] = None
        issue_version: Optional[int] = None
        for pointer in present_pointers:
            pointer_rows = tables[pointer].rows
            if not pointer_rows:
                # An empty pointer (header only) contributes no rows to load
                # and does not constrain the plancode/version.
                continue
            spec = schema.specs[pointer]
            plancode_pos = spec.column_index("Plancode")
            version_pos = spec.column_index("IssueVersion")
            plancodes = {row[plancode_pos] for row in pointer_rows}
            versions = {row[version_pos] for row in pointer_rows}
            if len(plancodes) != 1 or None in plancodes:
                raise PackageValidationError(
                    f"{pointer}.csv must contain exactly one nonblank plancode."
                )
            if len(versions) != 1 or None in versions:
                raise PackageValidationError(
                    f"{pointer}.csv must contain exactly one IssueVersion."
                )
            this_plancode = str(next(iter(plancodes)))
            this_version = int(next(iter(versions)))
            if plancode is None:
                plancode, issue_version = this_plancode, this_version
            elif this_plancode != plancode or this_version != issue_version:
                raise PackageValidationError(
                    "Workup pointer files disagree: "
                    f"{pointer}.csv has plancode {this_plancode} / "
                    f"IssueVersion {this_version}, but expected plancode "
                    f"{plancode} / IssueVersion {issue_version}."
                )

        if plancode is None or issue_version is None:
            raise PackageValidationError(
                "The workup pointer file(s) contain no rows to load."
            )

        return cls(root, plancode, issue_version, tables, schema)


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


def analyze_package(
    package: WorkupPackage,
    repository: "ULRatesRepository",
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

    pointer_ref_indexes: dict[str, set[Any]] = defaultdict(set)
    for pointer_name in schema.pointer_names:
        pointer_data = package.tables[pointer_name]
        for column, rate_table in pointer_data.spec.pointer_refs.items():
            pos = pointer_data.spec.column_index(column)
            pointer_ref_indexes[rate_table].update(
                row[pos] for row in pointer_data.rows if row[pos] is not None
            )

    table_count = len(package.tables)
    for table_number, (name, data) in enumerate(package.tables.items(), start=1):
        progress(
            f"Rechecking {name} ({table_number}/{table_count}) against UL_Rates..."
        )
        spec = data.spec
        if spec.is_pointer:
            existing = tuple(repository.fetch_pointer_rows(name, package.plancode))
            incoming_scopes = {spec.scope(row) for row in data.rows}
            scoped_existing = tuple(
                row for row in existing if spec.scope(row) in incoming_scopes
            )
            incoming_by_key = data.rows_by_key()
            existing_by_key = {spec.key(row): row for row in scoped_existing}
            shared_keys = incoming_by_key.keys() & existing_by_key.keys()
            identical = frozenset(
                key for key in shared_keys
                if incoming_by_key[key] == existing_by_key[key]
            )
            different = frozenset(shared_keys - identical)
            analyses[name] = TableAnalysis(
                table_name=name,
                file_rows=len(data.rows),
                existing_rows=scoped_existing,
                is_pointer=True,
                identical_pointer_keys=identical,
                different_pointer_keys=different,
            )
            state_rows[name].extend(existing)
            continue

        incoming_by_index = data.rows_by_index()
        requested_indexes = set(incoming_by_index) | pointer_ref_indexes[name]
        existing_indexes = repository.fetch_existing_indexes(name, requested_indexes)
        colliding = set(incoming_by_index) & existing_indexes
        existing_rows = tuple(repository.fetch_rate_rows(name, colliding))
        existing_by_index = TableData(spec, existing_rows).rows_by_index()

        identical_indexes: set[Any] = set()
        different_indexes: set[Any] = set()
        for index in colliding:
            if incoming_by_index[index] == existing_by_index.get(index, ()):
                identical_indexes.add(index)
            else:
                different_indexes.add(index)

        references = repository.fetch_index_references(name, different_indexes)
        blocked: dict[Any, tuple[str, ...]] = {}
        replaceable: set[Any] = set()
        for index in different_indexes:
            plancodes = {
                value.strip() for value in references.get(index, set()) if value
            }
            other_plancodes = tuple(sorted(plancodes - {package.plancode}))
            if other_plancodes:
                blocked[index] = other_plancodes
            else:
                replaceable.add(index)

        analyses[name] = TableAnalysis(
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


def create_execution_plan(
    package: WorkupPackage,
    analysis: PackageAnalysis,
    actions: Mapping[str, LoadAction | str],
) -> ExecutionPlan:
    schema = package.schema
    normalized = normalize_actions(actions, schema)
    issues: list[PlanIssue] = []
    insert_rows: dict[str, tuple[tuple[Any, ...], ...]] = {}
    delete_indexes: dict[str, frozenset[Any]] = {}
    backup_rows: dict[str, tuple[tuple[Any, ...], ...]] = {}
    delete_pointer_scopes: dict[str, tuple[tuple[Any, ...], ...]] = {}

    for name, action in normalized.items():
        if action == LoadAction.SKIP:
            continue
        table_analysis = analysis.tables[name]
        data = package.tables[name]
        spec = data.spec

        if spec.is_pointer:
            if action == LoadAction.INSERT and table_analysis.existing_rows:
                detail = spec.scope_detail(table_analysis.existing_rows)
                issues.append(PlanIssue(
                    name,
                    f"{name} already has {len(table_analysis.existing_rows):,} "
                    f"row(s) for {package.plancode}{detail}; "
                    "explicitly choose Replace.",
                ))
                continue
            if action == LoadAction.REPLACE:
                delete_pointer_scopes[name] = tuple(
                    sorted({spec.scope(row) for row in data.rows})
                )
                if table_analysis.existing_rows:
                    backup_rows[name] = table_analysis.existing_rows
            insert_rows[name] = data.rows
            continue

        if action == LoadAction.INSERT and table_analysis.different_indexes:
            indexes = ", ".join(
                str(index) for index in sorted(table_analysis.different_indexes)
            )
            issues.append(PlanIssue(
                name,
                f"{name} has different existing data at index(es) {indexes}; "
                "explicitly choose Replace.",
            ))
            continue

        if action == LoadAction.REPLACE:
            if table_analysis.blocked_indexes:
                details = "; ".join(
                    f"{index}: {', '.join(plancodes)}"
                    for index, plancodes in sorted(
                        table_analysis.blocked_indexes.items()
                    )
                )
                issues.append(PlanIssue(
                    name,
                    "Cannot replace index data used by other plancodes "
                    f"({details}).",
                ))
                continue
            pointer_ref = schema.references.get(name)
            if table_analysis.different_indexes and pointer_ref:
                pointer_name, _column = pointer_ref
                if normalized[pointer_name] != LoadAction.REPLACE:
                    issues.append(PlanIssue(
                        name,
                        f"Replacing owned {name} indexes also requires "
                        f"{pointer_name} to use Replace in the same transaction.",
                    ))
                    continue
            replaced = table_analysis.replaceable_indexes
            if replaced:
                delete_indexes[name] = replaced
                backup_rows[name] = tuple(
                    row for row in table_analysis.existing_rows
                    if spec.index_value(row) in replaced
                )

        included_indexes = (
            table_analysis.new_indexes | table_analysis.replaceable_indexes
            if action == LoadAction.REPLACE
            else table_analysis.new_indexes
        )
        insert_rows[name] = tuple(
            row for row in data.rows if spec.index_value(row) in included_indexes
        )

    for pointer_name in schema.pointer_names:
        if normalized[pointer_name] == LoadAction.SKIP:
            continue
        pointer_data = package.tables[pointer_name]
        for column, rate_table in pointer_data.spec.pointer_refs.items():
            pos = pointer_data.spec.column_index(column)
            referenced = {
                row[pos] for row in pointer_data.rows if row[pos] is not None
            }
            if not referenced:
                continue
            rate_action = normalized[rate_table]
            rate_analysis = analysis.tables[rate_table]
            if rate_action == LoadAction.SKIP:
                mismatched = sorted(
                    referenced & rate_analysis.different_indexes
                )
                if mismatched:
                    sample = ", ".join(str(index) for index in mismatched[:12])
                    if len(mismatched) > 12:
                        sample += f", ... ({len(mismatched):,} total)"
                    issues.append(PlanIssue(
                        pointer_name,
                        f"{column} would use existing {rate_table} data that "
                        f"differs from this workup at index(es): {sample}.",
                    ))
            available = set(rate_analysis.available_indexes)
            if rate_action != LoadAction.SKIP:
                available.update(
                    rate_analysis.new_indexes
                    | rate_analysis.identical_indexes
                    | rate_analysis.replaceable_indexes
                )
            missing = sorted(referenced - available)
            if missing:
                sample = ", ".join(str(index) for index in missing[:12])
                if len(missing) > 12:
                    sample += f", ... ({len(missing):,} total)"
                issues.append(PlanIssue(
                    pointer_name,
                    f"{column} references missing {rate_table} index(es): {sample}.",
                ))

    return ExecutionPlan(
        package.plancode,
        normalized,
        insert_rows,
        delete_pointer_scopes,
        delete_indexes,
        backup_rows,
        tuple(issues),
    )


class ULRatesRepository:
    """Parameterized SQL Server access through the UL_Rates ODBC DSN.

    A repository is bound to one :class:`RateSchema`, so the same database
    connection serves the UL and Term table families without either being
    able to address the other's tables.
    """

    def __init__(self, dsn: str = "UL_Rates", schema: RateSchema = UL_SCHEMA):
        self.dsn = dsn.strip() or "UL_Rates"
        self.schema = schema
        self._connection: Optional[pyodbc.Connection] = None

    def connect(self) -> pyodbc.Connection:
        if self._connection is None:
            self._connection = pyodbc.connect(
                f"DSN={self.dsn}", autocommit=False, timeout=10
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
                    _quote(column)
                    for column in spec.columns
                )
                try:
                    cursor.execute(
                        f"SELECT {columns} FROM {_quote(spec.name)} WHERE 1 = 0"
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
            _quote(column) for column in spec.columns
        )
        cursor = self.connect().cursor()
        try:
            cursor.execute(
                f"SELECT {columns} FROM {_quote(table_name)} "
                f"WHERE {_quote('Plancode')} = ?",
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
                    f"SELECT DISTINCT {_quote(index_column)} "
                    f"FROM {_quote(table_name)} "
                    f"WHERE {_quote(index_column)} IN ({placeholders})",
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
            _quote(column) for column in spec.columns
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
                    f"SELECT {columns} FROM {_quote(table_name)} "
                    f"WHERE {_quote(index_column)} IN ({placeholders})",
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
                    f"SELECT {_quote(pointer_column)}, {_quote('Plancode')} "
                    f"FROM {_quote(pointer_table)} "
                    f"WHERE {_quote(pointer_column)} IN ({placeholders})",
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
                    f"{_quote(column)} = ?" for column in scope_columns
                )
                progress(f"Removing existing {table_name} rows...")
                for scope_values in scopes:
                    cursor.execute(
                        f"DELETE FROM {_quote(table_name)} WHERE {where}",
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
                        f"DELETE FROM {_quote(table_name)} "
                        f"WHERE {_quote(index_column)} IN ({placeholders})",
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
                    _quote(column)
                    for column in spec.columns
                )
                placeholders = ", ".join("?" for _ in spec.columns)
                try:
                    sql = (
                        f"INSERT INTO {_quote(table_name)} ({columns}) "
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


def write_backup(
    plan: ExecutionPlan,
    backup_root: str | Path | None = None,
    schema: RateSchema = UL_SCHEMA,
) -> Optional[Path]:
    rows_to_backup = {
        table: rows for table, rows in plan.backup_rows.items() if rows
    }
    if not rows_to_backup:
        return None
    root = (
        Path(backup_root).expanduser()
        if backup_root is not None
        else Path.home() / ".suiteview" / "rate_manager_backups"
    )
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    safe_plancode = re.sub(r"[^A-Za-z0-9_.-]+", "_", plan.plancode).strip("._")
    folder = root / f"{timestamp}_{safe_plancode or 'rate_update'}"
    folder.mkdir(parents=True, exist_ok=False)

    manifest = {
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "plancode": plan.plancode,
        "purpose": (
            "Pre-commit backup of rows selected for removal or replacement. "
            "This file alone does not prove the database transaction committed."
        ),
        "actions": {name: action.value for name, action in plan.actions.items()},
        "tables": {},
    }
    for table_name, rows in rows_to_backup.items():
        spec = schema.specs[table_name]
        path = folder / f"{table_name}.csv"
        with path.open("w", newline="", encoding="utf-8-sig") as handle:
            writer = csv.writer(handle)
            writer.writerow(spec.columns)
            writer.writerows(
                [display_value(value) for value in row] for row in rows
            )
        manifest["tables"][table_name] = {
            "rows": len(rows),
            "file": path.name,
        }
    with (folder / "manifest.json").open("w", encoding="utf-8") as handle:
        json.dump(manifest, handle, indent=2)
    return folder


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
        cursor = repository.connect().cursor()
        try:
            cursor.execute(
                f"DELETE FROM {_quote(table_name)} "
                f"WHERE "
                f"{_quote(spec.index_column)} = ?",
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
    cursor = repository.connect().cursor()
    try:
        for row in rows:
            clauses: list[str] = []
            params: list[Any] = []
            for column, value in zip(spec.key_columns, spec.key(row)):
                database_column = column
                if value is None:
                    clauses.append(f"{_quote(database_column)} IS NULL")
                else:
                    clauses.append(f"{_quote(database_column)} = ?")
                    params.append(value)
            cursor.execute(
                f"DELETE FROM {_quote(spec.name)} WHERE {' AND '.join(clauses)}",
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
    rows = tuple(rows)
    if not rows:
        return
    columns = ", ".join(
        _quote(column) for column in spec.columns
    )
    placeholders = ", ".join("?" for _ in spec.columns)
    cursor = repository.connect().cursor()
    try:
        cursor.fast_executemany = True
        cursor.executemany(
            f"INSERT INTO {_quote(spec.name)} ({columns}) "
            f"VALUES ({placeholders})",
            [_database_row(spec, row) for row in rows],
        )
    finally:
        cursor.close()


def _quote(identifier: str) -> str:
    return "[" + identifier.replace("]", "]]") + "]"


def _chunks(values, size: int = 500) -> Iterable[tuple]:
    for start in range(0, len(values), size):
        yield tuple(values[start:start + size])


def _clear_rate_cache() -> None:
    from suiteview.core.rates import Rates

    Rates().clear_cache()
    Rates._scr_state_plancodes = None
