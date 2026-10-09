"""RERUN's plancode tables in UL_Rates (schema ``dbo``).

* ``dbo.SV_RERUN_Adv_Plancodes`` - the product rules ``load_plancode`` needs for each
  advanced-product (UL / IUL / ISWL) plancode that schema ``rates`` does not hold
  (formerly ``plancodes/plancode_table.json``). One row per plancode; a NULL column is
  "not set" and takes the engine's default.
* ``dbo.SV_RERUN_Plancode_Control`` - every in-force base plancode with its product
  type and whether it may be illustrated. It is the one control of what users without
  the ``RERUNANYPLAN`` permission may illustrate (``core.plancode_control``).

The runtime only reads them (one SELECT each). ``tools/rerun/rerun_plancode_tables.py``
creates, loads and refreshes them.
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from decimal import Decimal
from typing import Any, Iterable, Mapping, Sequence

from suiteview.core.data_access.connections import connection_factory
from suiteview.core.data_access.errors import ConnectionUnavailable
from suiteview.core.local_dev import local_data_enabled
from suiteview.core.rates_errors import RatesError

logger = logging.getLogger(__name__)

ADV_TABLE = "dbo.SV_RERUN_Adv_Plancodes"
CONTROL_TABLE = "dbo.SV_RERUN_Plancode_Control"
QUERY_TIMEOUT = 15

# Control-table product types (CHECK constraint). "Other" holds the few base
# coverages none of the others describe (annuity riders issued as a base).
PRODUCT_TYPES = ("IUL", "UL", "ISWL", "ParWL", "WL", "Term", "DI", "Other")


class PlancodeTableError(RatesError):
    """A RERUN plancode table could not be read or holds an invalid value."""


@dataclass(frozen=True)
class Column:
    name: str
    sql_type: str
    kind: str            # text / int / float / bool / float_list
    required: bool = False


# Column names are the engine's keys (``plancode_config.load_plancode``).
ADV_COLUMNS: tuple[Column, ...] = (
    Column("Plancode", "varchar(20)", "text", True),
    Column("LoanType", "varchar(10)", "text", True),
    Column("LapseTarget", "varchar(5)", "text", True),
    Column("AgeCalc", "varchar(5)", "text", True),
    Column("Interest_Method", "varchar(20)", "text", True),
    Column("SA_Basis", "varchar(20)", "text", True),
    Column("TableRatingFactor", "decimal(9,6)", "float", True),
    Column("PoAV_Table", "varchar(5)", "text", True),
    Column("DynamicBanding", "int", "int", True),
    Column("Rachet_Banding", "bit", "bool", True),
    Column("CompanySub", "varchar(10)", "text", True),
    Column("MinFaceAfterWD", "decimal(15,2)", "float"),
    Column("MinFaceEvidenced", "bit", "bool"),
    Column("COI_RateBasis", "varchar(10)", "text"),
    Column("PWoT_COI_Basis", "int", "int"),
    Column("SCR_PctOfSurrenderTarget", "varchar(400)", "float_list"),
    Column("PremiumAndChargeCeaseAge", "int", "int"),
    Column("IllustrationMaturityAgeOverride", "int", "int"),
    Column("IllustrationPremiumCeaseAgeOverride", "int", "int"),
    Column("ShadowAvailability", "varchar(10)", "text"),
    Column("ShadowCeaseAge", "int", "int"),
    Column("ShadowSABasis", "int", "int"),
    Column("ShadowMFEE", "decimal(9,2)", "float"),
    Column("ShadowLoanImpact", "varchar(10)", "text"),
    Column("ShadowLatePaymentForgiveness", "bit", "bool"),
    Column("ShadowMonthlyInterest", "bit", "bool"),
    Column("ShadowNPlus1Relief", "bit", "bool"),
    Column("ShadowWithdrawalGross", "bit", "bool"),
    Column("ShadowIssueBand", "bit", "bool"),
    Column("ShadowAPS205LoadRelief", "bit", "bool"),
    Column("ShadowTargetRateBasis", "varchar(5)", "text"),
    Column("ShadowTargetWaiverUplift", "bit", "bool"),
    Column("ShadowTargetAnnualFlat", "bit", "bool"),
    Column("ShadowFrozenAfterCease", "bit", "bool"),
    Column("ShadowDBBasis", "varchar(10)", "text"),
)
ADV_KEYS = tuple(column.name for column in ADV_COLUMNS)

CONTROL_COLUMNS: tuple[Column, ...] = (
    Column("Plancode", "varchar(20)", "text", True),
    Column("ProductType", "varchar(10)", "text", True),
    Column("CanIllustrate", "bit", "bool", True),
)

_AUDIT_COLUMNS = (
    "[UpdatedAt] datetime2(0) NOT NULL DEFAULT (SYSDATETIME())",
    "[UpdatedBy] nvarchar(128) NOT NULL DEFAULT (SUSER_SNAME())",
)


def _create_sql(table: str, columns: Sequence[Column], checks: Sequence[str]) -> str:
    name = table.split(".", 1)[1]
    lines = [f"[{c.name}] {c.sql_type} {'NOT NULL' if c.required else 'NULL'}" for c in columns]
    lines += list(_AUDIT_COLUMNS)
    lines.append(f"CONSTRAINT [PK_{name}] PRIMARY KEY ([Plancode])")
    lines += [f"CONSTRAINT [CK_{name}_{label}] CHECK ({expr})" for label, expr in checks]
    body = ",\n    ".join(lines)
    return f"CREATE TABLE {table} (\n    {body}\n)"


def _in_list(values: Iterable[str]) -> str:
    return ", ".join(f"'{value}'" for value in values)


ADV_CREATE_SQL = _create_sql(ADV_TABLE, ADV_COLUMNS, (
    ("LoanType", "[LoanType] IN ('Arrears', 'Advance')"),
    ("LapseTarget", "[LapseTarget] IN ('SV', 'AV')"),
    ("AgeCalc", "[AgeCalc] IN ('ANB', 'ALB')"),
    ("SA_Basis", "[SA_Basis] IN ('CurrentSA', 'OriginalSA')"),
))
CONTROL_CREATE_SQL = _create_sql(CONTROL_TABLE, CONTROL_COLUMNS, (
    ("ProductType", f"[ProductType] IN ({_in_list(PRODUCT_TYPES)})"),
))


def _select_sql(table: str, columns: Sequence[Column]) -> str:
    names = ", ".join(f"[{c.name}]" for c in columns)
    return f"SELECT {names} FROM {table} ORDER BY [Plancode]"


ADV_SELECT_SQL = _select_sql(ADV_TABLE, ADV_COLUMNS)
CONTROL_SELECT_SQL = _select_sql(CONTROL_TABLE, CONTROL_COLUMNS)


def _from_db(column: Column, value: Any) -> Any:
    if value is None:
        return None
    if column.kind == "text":
        return str(value).strip()
    if column.kind == "int":
        return int(value)
    if column.kind == "float":
        return float(value)
    if column.kind == "bool":
        return bool(value)
    if column.kind == "float_list":
        return [float(item) for item in json.loads(str(value))]
    raise ValueError(f"Unknown column kind {column.kind!r}")


def row_from_db(columns: Sequence[Column], record: Sequence[Any]) -> dict:
    """One table row as the engine's dict; a NULL column is left out ("not set")."""
    row = {}
    for column, value in zip(columns, record):
        converted = _from_db(column, value)
        if converted is not None:
            row[column.name] = converted
    return row


def _to_db(column: Column, value: Any, plancode: str) -> Any:
    if value is None:
        if column.required:
            raise ValueError(f"{plancode}: {column.name} is required.")
        return None
    bad = ValueError(f"{plancode}: {column.name} {value!r} is not a valid {column.kind}.")
    if column.kind == "text":
        if not isinstance(value, str):
            raise bad
        return value.strip()
    if column.kind == "bool":
        if not isinstance(value, bool):
            raise bad
        return value
    if column.kind == "int":
        if isinstance(value, bool) or not isinstance(value, (int, float)) or value != int(value):
            raise bad
        return int(value)
    if column.kind == "float":
        if isinstance(value, bool) or not isinstance(value, (int, float, Decimal)):
            raise bad
        return Decimal(str(value))
    if column.kind == "float_list":
        if not isinstance(value, list) or not all(
                isinstance(item, (int, float)) and not isinstance(item, bool) for item in value):
            raise bad
        return json.dumps(value)
    raise ValueError(f"Unknown column kind {column.kind!r}")


def row_to_db(columns: Sequence[Column], row: Mapping[str, Any]) -> tuple:
    """INSERT parameters (column order) for one row; unknown keys are an error."""
    plancode = str(row.get("Plancode") or "?")
    unknown = sorted(set(row) - {c.name for c in columns})
    if unknown:
        raise ValueError(f"{plancode}: unknown column(s) {', '.join(unknown)}.")
    return tuple(_to_db(column, row.get(column.name), plancode) for column in columns)


def insert_sql(table: str, columns: Sequence[Column]) -> str:
    names = ", ".join(f"[{c.name}]" for c in columns)
    marks = ", ".join("?" for _ in columns)
    return f"INSERT INTO {table} ({names}) VALUES ({marks})"


def _select(sql: str, connection: Any = None) -> list:
    from suiteview.core.sql_permissions import guard_query_sql

    guard_query_sql(sql)
    owns = connection is None
    if owns:
        if local_data_enabled():
            raise ConnectionUnavailable(
                "RERUN's plancode tables are not part of the local development data; "
                "unset SUITEVIEW_LOCAL_DATA to read them from UL_Rates.")
        connection = connection_factory.connect_ul_rates(
            autocommit=True, timeout=QUERY_TIMEOUT, readonly=True)
    try:
        cursor = connection.cursor()
        try:
            cursor.execute(sql)
            return cursor.fetchall()
        finally:
            cursor.close()
    except ConnectionUnavailable:
        raise
    except Exception as exc:
        logger.error("RERUN plancode table read failed: %s | SQL: %s", exc, sql)
        raise PlancodeTableError(f"Could not read RERUN's plancode table: {exc}") from exc
    finally:
        if owns:
            try:
                connection.close()
            except Exception:
                logger.debug("Closing the UL_Rates connection failed", exc_info=True)


def read_adv_plancode_rows(connection: Any = None) -> list[dict]:
    """Every ``SV_RERUN_Adv_Plancodes`` row as the engine's dict, ordered by plancode."""
    return [row_from_db(ADV_COLUMNS, record) for record in _select(ADV_SELECT_SQL, connection)]


@dataclass(frozen=True)
class ControlRow:
    plancode: str
    product_type: str
    can_illustrate: bool


def read_control_rows(connection: Any = None) -> dict[str, ControlRow]:
    """Every ``SV_RERUN_Plancode_Control`` row, keyed by plancode."""
    rows: dict[str, ControlRow] = {}
    for record in _select(CONTROL_SELECT_SQL, connection):
        row = row_from_db(CONTROL_COLUMNS, record)
        plancode = row["Plancode"].upper()
        rows[plancode] = ControlRow(plancode, row["ProductType"], bool(row["CanIllustrate"]))
    return rows


def table_exists(cursor, table: str) -> bool:
    return cursor.execute("SELECT OBJECT_ID(?, 'U')", table).fetchone()[0] is not None


__all__ = [
    "ADV_COLUMNS", "ADV_CREATE_SQL", "ADV_KEYS", "ADV_SELECT_SQL", "ADV_TABLE", "CONTROL_COLUMNS",
    "CONTROL_CREATE_SQL", "CONTROL_SELECT_SQL", "CONTROL_TABLE", "Column", "ControlRow",
    "PRODUCT_TYPES", "PlancodeTableError", "insert_sql", "read_adv_plancode_rows",
    "read_control_rows", "row_from_db", "row_to_db", "table_exists",
]
