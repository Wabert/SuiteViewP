"""Independent or date-linked transaction criteria for the CyberLife query builder."""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from enum import Enum

from .sql_helpers import esc, in_list, strict_range_predicates


class TransactionDateComparison(str, Enum):
    NONE = "none"
    AFTER_ENTRY = "After Trans1 Entry Date"
    BEFORE_ENTRY = "Before Trans1 Entry Date"
    EQUAL_ENTRY = "Equal Trans1 Entry Date"
    AFTER_EFFECTIVE = "After Trans1 Eff Date"
    BEFORE_EFFECTIVE = "Before Trans1 Eff Date"
    EQUAL_EFFECTIVE = "Equal Trans1 Eff Date"


_DATE_COMPARISON_SQL = {
    TransactionDateComparison.AFTER_ENTRY: (">", "ENTRY_DT"),
    TransactionDateComparison.BEFORE_ENTRY: ("<", "ENTRY_DT"),
    TransactionDateComparison.EQUAL_ENTRY: ("=", "ENTRY_DT"),
    TransactionDateComparison.AFTER_EFFECTIVE: (">", "ASOF_DT"),
    TransactionDateComparison.BEFORE_EFFECTIVE: ("<", "ASOF_DT"),
    TransactionDateComparison.EQUAL_EFFECTIVE: ("=", "ASOF_DT"),
}


def parse_date_comparison(value: str, label: str) -> TransactionDateComparison:
    try:
        return TransactionDateComparison(value)
    except ValueError as error:
        raise ValueError(f"{label}: select a listed transaction date comparison.") from error


@dataclass(frozen=True)
class TransactionCriteria:
    transaction_types: tuple[str, ...] = ()
    entry_date: tuple[str, str] = ("", "")
    effective_date: tuple[str, str] = ("", "")
    effective_month: tuple[str, str] = ("", "")
    effective_day: tuple[str, str] = ("", "")
    gross_amount: tuple[str, str] = ("", "")
    origin: str = ""
    fund_ids: str = ""
    on_issue_month: bool = False
    on_issue_day: bool = False
    exclude: bool = False
    is_reversal_values: tuple[str, ...] = ()
    reversed_values: tuple[str, ...] = ()
    entry_comparison: TransactionDateComparison = TransactionDateComparison.NONE
    effective_comparison: TransactionDateComparison = TransactionDateComparison.NONE


def _row_predicates(criteria: TransactionCriteria, number: int) -> list[str]:
    alias = f"TR{number}"
    label = f"Transaction {number}"
    predicates = []
    if criteria.transaction_types:
        predicates.append(f"{alias}.TRANS IN ({in_list(list(criteria.transaction_types))})")
    for column, bounds, name in (
        ("ENTRY_DT", criteria.entry_date, "Entry Dt"),
        ("ASOF_DT", criteria.effective_date, "Eff Dt"),
    ):
        predicates.extend(strict_range_predicates(
            f"{alias}.{column}", *bounds, "date", f"{label} - {name}",
        ))
    predicates.extend(strict_range_predicates(
        f"{alias}.GROSS_AMT", *criteria.gross_amount, "decimal", f"{label} - Gross Amt",
    ))
    for function, bounds, maximum, name in (
        ("MONTH", criteria.effective_month, 12, "Eff Mth"),
        ("DAY", criteria.effective_day, 31, "Eff Day"),
    ):
        predicates.extend(strict_range_predicates(
            f"{function}({alias}.ASOF_DT)", *bounds, "integer", f"{label} - {name}",
        ))
        if any(text.strip() and not 1 <= Decimal(text.strip()) <= maximum for text in bounds):
            raise ValueError(f"{label} - {name}: enter a value from 1 to {maximum}.")
    if criteria.on_issue_month:
        predicates.append(f"MONTH({alias}.ASOF_DT) = MONTH(COVERAGE1.ISSUE_DT)")
    if criteria.on_issue_day:
        predicates.append(f"DAY({alias}.ASOF_DT) = DAY(COVERAGE1.ISSUE_DT)")
    if criteria.origin.strip():
        predicates.append(f"{alias}.ORIGIN_OF_TRANS = '{esc(criteria.origin.strip())}'")
    if criteria.fund_ids.strip():
        funds = [value.strip() for value in criteria.fund_ids.split(",")]
        if not all(funds):
            raise ValueError(f"{label} - Fund ID List: enter comma-separated IDs without empty entries.")
        predicates.append(f"{alias}.FUND_ID IN ({in_list(funds)})")
    for column, values, name in (
        ("FCB0_REV_IND", criteria.is_reversal_values, "Is Reversal"),
        ("FCB2_REV_APPL_IND", criteria.reversed_values, "Reversed"),
    ):
        if any(value not in ("0", "1") for value in values):
            raise ValueError(f"{label} - {name}: select 0 or 1.")
        if values:
            predicates.append(f"{alias}.{column} IN ({in_list(list(values))})")
    return predicates


def _exists(
    schema: str, number: int, predicates: list[str], *, exclude: bool = False, indent: int = 0,
) -> str:
    alias = f"TR{number}"
    # FH_FIXED has no CK_SYS_CD; company and technical policy ID are its policy keys.
    conditions = [
        f"{alias}.CK_CMP_CD = POLICY1.CK_CMP_CD",
        f"{alias}.TCH_POL_ID = POLICY1.TCH_POL_ID",
        *predicates,
    ]
    operator = "NOT EXISTS" if exclude else "EXISTS"
    padding = " " * indent
    return (
        f"{operator} (SELECT 1 FROM {schema}.FH_FIXED {alias}\n"
        f"{padding}    WHERE " + f"\n{padding}      AND ".join(conditions) + ")"
    )


def transaction_predicates(
    first: TransactionCriteria, second: TransactionCriteria, schema: str,
) -> list[str]:
    """Match independent sections, or a single qualifying pair when dates are linked."""
    comparisons = []
    for number, criteria in enumerate((first, second), 1):
        for column, value, name in (
            ("ENTRY_DT", criteria.entry_comparison, "Entry Dt"),
            ("ASOF_DT", criteria.effective_comparison, "Eff Dt"),
        ):
            comparison = parse_date_comparison(value, f"Transaction {number} - {name}")
            if comparison == TransactionDateComparison.NONE:
                continue
            if number == 1:
                raise ValueError("Transaction 1 - date comparisons are only available in Transaction 2.")
            if first.exclude:
                raise ValueError("Transaction 2 - date comparisons require Transaction 1 Exclude to be off.")
            operator, reference = _DATE_COMPARISON_SQL[comparison]
            comparisons.append(f"TR2.{column} {operator} TR1.{reference}")

    first_rows = _row_predicates(first, 1)
    second_rows = _row_predicates(second, 2)
    if not comparisons:
        return [
            _exists(schema, number, rows, exclude=criteria.exclude)
            for number, criteria, rows in ((1, first, first_rows), (2, second, second_rows))
            if rows
        ]

    matching_second = _exists(schema, 2, [*second_rows, *comparisons], indent=6)
    matching_pair = _exists(schema, 1, [*first_rows, matching_second], exclude=second.exclude)
    if second.exclude:
        # Exclude every qualifying pair, not merely find an anchor with no partner.
        return [_exists(schema, 1, first_rows), matching_pair]
    return [matching_pair]
