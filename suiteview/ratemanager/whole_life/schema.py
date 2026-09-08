"""Physical, source-keyed Whole Life tables in SQL Server's UL_Rates database."""

from __future__ import annotations

from collections import OrderedDict
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from functools import cached_property
from typing import Any, Iterable, Mapping

from suiteview.ratemanager.database_loader import (
    PackageValidationError, TableData, TableSpec, coerce_row,
)


@dataclass(frozen=True)
class Column:
    name: str
    sql_type: str
    nullable: bool = False

    def validate(self, value: Any) -> None:
        if value is None:
            if not self.nullable:
                raise PackageValidationError(f"{self.name} cannot be NULL.")
            return
        if self.sql_type.startswith(("varchar(", "char(")):
            size = int(self.sql_type.split("(")[1].rstrip(")"))
            if len(value) > size or not value.isascii():
                raise PackageValidationError(
                    f"{self.name} must contain at most {size} ASCII characters."
                )
        elif self.sql_type == "smallint":
            if not -32768 <= value <= 32767:
                raise PackageValidationError(f"{self.name} is outside smallint range.")
        elif self.sql_type == "int":
            if not -2147483648 <= value <= 2147483647:
                raise PackageValidationError(f"{self.name} is outside int range.")
        elif self.sql_type == "date":
            date.fromisoformat(value)
        elif self.sql_type.startswith("decimal("):
            precision, scale = map(
                int, self.sql_type.removeprefix("decimal(").rstrip(")").split(",")
            )
            quantum = Decimal(1).scaleb(-scale)
            if abs(value) >= Decimal(10) ** (precision - scale) or value % quantum:
                raise PackageValidationError(
                    f"{self.name} does not fit {self.sql_type}: {value}."
                )


@dataclass(frozen=True)
class WholeLifeTable:
    name: str
    columns: tuple[Column, ...]
    keys: tuple[str, ...]
    create: bool = False

    @cached_property
    def spec(self) -> TableSpec:
        return TableSpec(
            self.name, tuple(c.name for c in self.columns), self.keys,
            integer_columns=frozenset(
                c.name for c in self.columns if c.sql_type in ("smallint", "int")
            ),
            decimal_columns=frozenset(
                c.name for c in self.columns
                if c.sql_type.startswith("decimal(") or c.sql_type == "float"
            ),
            empty_string_columns=frozenset(
                c.name for c in self.columns
                if c.sql_type.startswith(("varchar(", "char(")) and not c.nullable
            ),
        )

    def normalize(self, values: Iterable[Any]) -> tuple[Any, ...]:
        row = coerce_row(self.spec, values, source=self.name)
        for column, value in zip(self.columns, row):
            column.validate(value)
        return row

    def data(self, records: Iterable[Mapping[str, Any]]) -> TableData:
        spec = self.spec
        column_names = set(spec.columns)
        unique = {}
        for number, record in enumerate(records, 1):
            if set(record) != column_names:
                raise PackageValidationError(
                    f"{self.name} row {number}: expected columns {spec.columns}; "
                    f"received {tuple(record)}."
                )
            row = self.normalize(record[c] for c in spec.columns)
            key = spec.key(row)
            if key in unique and unique[key] != row:
                raise PackageValidationError(
                    f"{self.name}: conflicting source rows for key {key}."
                )
            unique[key] = row
        if not unique:
            raise PackageValidationError(f"{self.name}: source contains no rate rows.")
        return TableData(spec, tuple(unique.values()))

    def ddl(self, target: str | None = None) -> str:
        name = target or f"[dbo].[{self.name}]"
        definitions = []
        for column in self.columns:
            collation = (
                " COLLATE DATABASE_DEFAULT"
                if column.sql_type.startswith(("varchar(", "char(")) else ""
            )
            definitions.append(
                f"[{column.name}] {column.sql_type}{collation} "
                + ("NULL" if column.nullable else "NOT NULL")
            )
        definitions.append(
            "PRIMARY KEY (" + ", ".join(f"[{k}]" for k in self.keys) + ")"
        )
        return f"CREATE TABLE {name} (\n  " + ",\n  ".join(definitions) + "\n)"


def _columns(*items: tuple[str, str] | tuple[str, str, bool]) -> tuple[Column, ...]:
    return tuple(Column(*item) for item in items)


TABLES: OrderedDict[str, WholeLifeTable] = OrderedDict()

TABLES["WL_RATE_CV"] = WholeLifeTable(
    "WL_RATE_CV",
    _columns(
        ("USER_CODE", "varchar(2)"), ("RATE_KEY", "char(6)"),
        ("CLASS", "char(1)"), ("BASE_SERIES", "char(3)"), ("SUBSERIES", "char(2)"),
        ("USER_DEFINED", "varchar(8)"), ("ISSUE_AGE", "smallint"),
        ("PREMIUM_YEARS", "smallint"), ("BENEFIT_YEARS", "smallint"),
        ("FIRST_DURATION", "smallint"), ("LAST_DURATION", "smallint"),
        ("DURATION_ZERO_VALUE", "decimal(7,2)", True), ("DURATION", "smallint"),
        ("RATE", "decimal(7,2)"),
    ),
    ("USER_CODE", "RATE_KEY", "USER_DEFINED", "ISSUE_AGE", "DURATION"),
    create=True,
)
TABLES["WL_RATE_PUI"] = WholeLifeTable(
    "WL_RATE_PUI",
    _columns(
        ("USER_CODE", "varchar(2)"), ("PLANCODE", "varchar(11)"),
        ("SEX", "varchar(1)"), ("RATECLASS", "varchar(1)"),
        ("ATTAINED_AGE", "smallint"), ("TABLE_RATING", "varchar(2)"),
        ("RATE", "decimal(11,6)"), ("AUDIT_NUMBER", "varchar(6)"),
        ("CHANGED_DATE", "date"),
    ),
    ("USER_CODE", "PLANCODE", "SEX", "RATECLASS", "ATTAINED_AGE", "TABLE_RATING"),
    create=True,
)
TABLES["WL_RATE_NSP"] = WholeLifeTable(
    "WL_RATE_NSP",
    _columns(
        ("USER_CODE", "varchar(2)"), ("RATE_KEY", "varchar(32)"),
        ("BASIS_ID", "varchar(32)"), ("BASIS_DESCRIPTION", "varchar(500)"),
        ("SEX", "varchar(1)"), ("RATECLASS", "varchar(1)"),
        ("ISSUE_AGE", "smallint"), ("DURATION", "smallint"),
        ("EFFECTIVE_DATE", "date"), ("RATE_PER", "decimal(19,8)"),
        ("RATE", "decimal(19,8)"),
    ),
    (
        "USER_CODE", "RATE_KEY", "BASIS_ID", "SEX", "RATECLASS",
        "ISSUE_AGE", "DURATION", "EFFECTIVE_DATE",
    ),
    create=True,
)
TABLES["WL_RATE_PREM"] = WholeLifeTable(
    "WL_RATE_PREM",
    _columns(
        ("USER_CODE", "varchar(2)"), ("SOURCE_PLANCODE", "varchar(11)"),
        ("SOURCE_IAF_VERSION", "varchar(3)"), ("SOURCE_EFFECTIVE_DATE", "date"),
        ("PLANCODE", "varchar(11)"), ("IAF_VERSION", "varchar(3)"),
        ("EFFECTIVE_DATE", "date"), ("FIRST_AGE", "smallint"), ("LAST_AGE", "smallint"),
        ("IAR_USE", "smallint"), ("PAY_AGE", "smallint"), ("PAY_AGE_USE", "smallint"),
        ("ME_AGE", "smallint"), ("ME_AGE_USE", "smallint"),
        ("VALUE_PER_UNIT", "decimal(19,8)"), ("PRODUCTION_CREDIT", "decimal(19,8)"),
        ("PRODUCTION_CREDIT_USE", "smallint"), ("MDRT", "varchar(4)"),
        ("DEFICIENT", "smallint"), ("SPECIAL_BENEFITS", "varchar(15)"),
        ("R", "varchar(1)"), ("LV", "varchar(2)"), ("DUR", "varchar(10)"),
        ("RATE_TYPE", "char(1)"), ("SCALE_START", "date"), ("SCALE_STOP", "date", True),
        ("PREMIUM_IDENTIFIER", "char(7)"), ("DURATION_CODE", "char(2)"),
        ("SEX", "char(1)"), ("RATECLASS", "char(1)"), ("BAND", "char(1)"),
        ("PLAN_OPTION", "char(2)"), ("RATE", "decimal(19,8)"),
    ),
    (
        "USER_CODE", "SOURCE_PLANCODE", "SOURCE_IAF_VERSION", "SOURCE_EFFECTIVE_DATE",
        "PLANCODE", "IAF_VERSION", "EFFECTIVE_DATE", "FIRST_AGE", "LAST_AGE", "IAR_USE",
        "RATE_TYPE", "SCALE_START", "PREMIUM_IDENTIFIER",
    ),
    create=True,
)

TABLES["WL_DIV_HEADER"] = WholeLifeTable(
    "WL_DIV_HEADER",
    _columns(
        ("HEADER_ID", "varchar(45)"), ("MAINT_DT", "varchar(10)", True),
        ("RECORD_TYPE", "char(1)"), ("RECORD_TYPE_DESC", "varchar(50)"),
        ("USER_CODE", "varchar(2)"), ("DIV_KEY", "varchar(8)"),
        ("CLASS", "varchar(2)"), ("BASE_SERIES", "varchar(3)"),
        ("SUBSERIES", "varchar(2)"), ("CONTENT_CODE", "varchar(2)", True),
        ("USER_DEFINED", "varchar(6)", True), ("ISSUE_AGE", "smallint"),
        ("ISSUE_DATE", "varchar(10)", True), ("EFFECTIVE_DATE", "varchar(10)"),
        ("END_DATE", "varchar(10)", True), ("FIRST_DURATION", "smallint"),
        ("LAST_DURATION", "smallint"), ("PRO_RATA", "varchar(2)", True),
        ("EI_DEPOSIT", "varchar(2)", True), ("INTEREST_RATE", "float"),
        ("RESTRICT_CODE", "varchar(2)", True), ("EI_ADDITIONS", "varchar(2)", True),
        ("MORT_TABLE", "varchar(4)", True), ("INT_FUNCTION", "varchar(2)", True),
        ("PUA_INTEREST", "float"), ("PUA_CLASS", "varchar(2)", True),
        ("PUA_MATURE", "smallint", True), ("PUA_PARTICIPATING", "char(1)"),
        ("PUA_KEY", "varchar(8)", True), ("PUA_KEY_USER_DEFINED", "varchar(6)", True),
        ("GROSS_INTEREST", "float", True),
    ),
    ("HEADER_ID",),
)
TABLES["WL_RATE_DIV"] = WholeLifeTable(
    "WL_RATE_DIV",
    _columns(
        ("HEADER_ID", "varchar(45)"), ("RECORD_TYPE", "char(1)"),
        ("DURATION", "smallint"), ("CASH_RATE", "float"),
        ("PUA_RATE", "float"), ("OYT_RATE", "float"),
        ("PUA_DIV_CASH", "float", True), ("PUA_DIV_PUA", "float", True),
        ("PUA_DIV_OYT", "float", True),
    ),
    ("HEADER_ID", "DURATION"),
)
TABLES["WL_DIV_PLANKEY_MAP"] = WholeLifeTable(
    "WL_DIV_PLANKEY_MAP",
    _columns(
        ("PLANCODE", "char(8)"), ("SEX", "char(1)"), ("RATECLASS", "char(1)"),
        ("SUBSERIES", "char(2)"), ("USER_KEY", "varchar(2)", True),
        ("CV_DIV_KEY", "char(6)"),
    ),
    ("PLANCODE", "SEX", "RATECLASS"),
)

PDF_COLUMNS = (
    "UserID", "Plancode", "Version", "IAFVersion", "EffectiveDate",
    "EndDate", "FieldName", "FieldValue",
)
