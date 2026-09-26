"""Shared ledger column and cell specifications for illustration outputs."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Callable


@dataclass(frozen=True)
class ColumnSpec:
    """One visible ledger column."""

    heading: str
    numeric: bool = True


@dataclass(frozen=True)
class LedgerCellInput:
    """All values needed to render one annual or monthly ledger row."""

    year: int
    month: int
    age: int
    age_eoy: int
    when: date | None
    withdrawals: float = 0.0
    forceouts: float = 0.0
    loan_repay: float = 0.0
    premium: float = 0.0
    monthly_deduction: float = 0.0
    exception_prem: float = 0.0
    av: float = 0.0
    sv: float = 0.0
    interest: float = 0.0
    eav: float = 0.0
    sc: float = 0.0
    new_loan: float = 0.0
    loan_balance: float = 0.0
    esv: float = 0.0
    shadow_eav: float = 0.0
    death_benefit: float = 0.0
    status: str = ""
    glp: float = 0.0
    gsp: float = 0.0
    total_gp: float = 0.0
    subject_payments: float = 0.0


LEDGER_COLUMN_SPECS = [
    ColumnSpec("Year"),
    ColumnSpec("Month"),
    ColumnSpec("Age"),
    ColumnSpec("Age EOY"),
    ColumnSpec("Date", numeric=False),
    ColumnSpec("Distributions"),
    ColumnSpec("Contributions"),
    ColumnSpec("MD"),
    ColumnSpec("AV"),
    ColumnSpec("SV"),
    ColumnSpec("Interest"),
    ColumnSpec("EAV"),
    ColumnSpec("SC"),
    ColumnSpec("LN"),
    ColumnSpec("ESV"),
    ColumnSpec("Shadow EAV"),
    ColumnSpec("Death Benefit"),
    ColumnSpec("Status", numeric=False),
    ColumnSpec("", numeric=False),
    ColumnSpec("GLP"),
    ColumnSpec("GSP"),
    ColumnSpec("TotalGP"),
    ColumnSpec("SubjectPayments"),
    ColumnSpec("Withdrawals"),
    ColumnSpec("ForceOuts"),
    ColumnSpec("Loan Repay"),
    ColumnSpec("Prem"),
    ColumnSpec("Exception Prem"),
    ColumnSpec("New Loan"),
]


def ledger_columns() -> list[str]:
    return [spec.heading for spec in LEDGER_COLUMN_SPECS]


def numeric_ledger_indexes() -> set[int]:
    return {
        index for index, spec in enumerate(LEDGER_COLUMN_SPECS)
        if spec.numeric and spec.heading
    }


def ledger_cells_from_input(data: LedgerCellInput) -> list[str]:
    contributions = data.loan_repay + data.premium + data.exception_prem
    distributions = data.withdrawals + data.forceouts + data.new_loan
    return [
        str(data.year), str(data.month), str(data.age), str(data.age_eoy),
        _fmt_date(data.when),
        _fmt_money(distributions, 2), _fmt_money(contributions, 2),
        _fmt_money(data.monthly_deduction, 2), _fmt_money(data.av, 2),
        _fmt_money(data.sv, 2), _fmt_money(data.interest, 2),
        _fmt_money(data.eav, 2), _fmt_money(data.sc, 2),
        _fmt_money(data.loan_balance, 2), _fmt_money(data.esv, 2),
        _fmt_money(data.shadow_eav, 2),
        _fmt_money(data.death_benefit, 0), data.status,
        "",
        _fmt_money(data.glp, 2), _fmt_money(data.gsp, 2),
        _fmt_money(data.total_gp, 2), _fmt_money(data.subject_payments, 2),
        _fmt_money(data.withdrawals, 2), _fmt_money(data.forceouts, 2),
        _fmt_money(data.loan_repay, 2), _fmt_money(data.premium, 2),
        _fmt_money(data.exception_prem, 2), _fmt_money(data.new_loan, 2),
    ]


@dataclass(frozen=True)
class KpiSpec:
    """Declarative KPI row descriptor for comparison summaries."""

    key: str
    caption: str
    values: Callable
    lower_is_better: bool = False


@dataclass(frozen=True)
class ForecastSpec:
    """Declarative forecast descriptor shared by batch forecast flows."""

    key: str
    label: str
    run: Callable


def _fmt_date(when) -> str:
    return f"{when:%m/%d/%Y}" if when else ""


def _fmt_money(value: float, decimals: int = 2) -> str:
    return f"{float(value):,.{decimals}f}"
