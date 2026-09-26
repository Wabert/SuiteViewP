"""Spec helpers for PolView rate matrices."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Callable, Iterable, Optional

from dateutil.relativedelta import relativedelta


@dataclass(frozen=True)
class DurationRow:
    index: int
    date_text: str
    age: int | str
    year: int


@dataclass(frozen=True)
class MatrixColumn:
    name: str
    value_fn: Callable[[DurationRow], object]
    missing_text: str = ""


def duration_rows(issue_date: date, issue_age: Optional[int], row_count: int) -> Iterable[DurationRow]:
    """Yield one-based policy-duration rows used by the rate displays."""
    for row in range(1, row_count + 1):
        try:
            dt = issue_date + relativedelta(years=row - 1)
            date_text = dt.strftime("%m/%d/%Y")
        except Exception:
            date_text = ""
        age = issue_age + row - 1 if issue_age is not None else ""
        yield DurationRow(index=row, date_text=date_text, age=age, year=row)


def rate_value_or_na(values, row: int, missing_text: str = "NA"):
    """Return a one-based rate value, blank beyond the schedule, or missing text."""
    if values and row < len(values):
        return values[row]
    return missing_text if values is None else ""


def metadata_value(values: list, row: int) -> object:
    """Return the metadata value for a one-based matrix row."""
    return values[row] if row < len(values) else ""


def build_rate_matrix(columns: list[MatrixColumn], rows: Iterable[DurationRow]) -> list[list]:
    """Evaluate matrix columns for each duration row."""
    matrix = [[column.name for column in columns]]
    for row in rows:
        matrix.append([column.value_fn(row) for column in columns])
    return matrix
