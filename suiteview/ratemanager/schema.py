"""Table specs, schemas and Rate Manager data-layer errors."""

from __future__ import annotations

from collections import OrderedDict
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Iterable, Mapping, Optional

from suiteview.core.data_access.errors import (
    QueryFailed,
    SourceValidationError,
    SuiteViewDataError,
)



class RateDatabaseError(SuiteViewDataError):
    """Base error for Rate Manager database operations."""



class PackageValidationError(SourceValidationError, RateDatabaseError):
    """A workup folder is incomplete or contains invalid data."""



class UnsafeOperationError(SourceValidationError, RateDatabaseError):
    """A requested database operation would violate a safety invariant."""



class StaleAnalysisError(QueryFailed, RateDatabaseError):
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
