"""IUL index assumptions from UL_Rates schema ``rates`` FUND rows."""

from __future__ import annotations

import logging
from datetime import date
from typing import Any, Dict, Iterable, List, Optional

from .rates_schema import FundAssignment, FundRate, RatesSchemaRepository

logger = logging.getLogger(__name__)

_MARKET_RETURN_PLAN = "MKTRETNS"
_INDEX_ASSUMPTION_TYPES = frozenset({
    "IDX_ILL",
    "IDX_BENCH_MIN",
    "IDX_BENCH_MAX",
    "MKT_RETURN",
})


def _norm(value: str) -> str:
    return (value or "").strip().upper()


def _rein(value: str) -> str:
    return "R" if _norm(value) == "R" else ""


def _latest_rate(
    rows: Iterable[FundRate],
    rate_type: str,
    as_of: date,
) -> Optional[FundRate]:
    candidates = [
        row for row in rows
        if row.rate_type == rate_type and row.scale == "C" and row.rate_start <= as_of
    ]
    if not candidates:
        return None
    return max(candidates, key=lambda row: row.rate_start)


class IndexAssumptionTables:
    """Read-only IUL illustration assumptions from schema ``rates``."""

    def __init__(self, repository: Any = None):
        self._repository = repository
        self._owns_repository = repository is None

    def __enter__(self) -> "IndexAssumptionTables":
        return self

    def __exit__(self, *exc) -> None:
        self.close()

    @property
    def repository(self):
        if self._repository is None:
            self._repository = RatesSchemaRepository()
        return self._repository

    def close(self) -> None:
        if self._repository is not None and self._owns_repository:
            try:
                self._repository.close()
            except Exception:
                logger.debug("Closing the rates-schema repository failed", exc_info=True)
            self._repository = None

    def _company_for_plan(self, plancode: str, company: str = "") -> str:
        plans = self.repository.plan_defs(plancode)
        if not plans:
            return ""
        company = (company or "").strip().zfill(2)
        if company:
            for plan in plans:
                if plan.company == company:
                    return plan.company
        for plan in plans:
            if plan.company == "00":
                return plan.company
        return plans[0].company

    def _assigned_fund_rates(
        self,
        company: str,
        plancode: str,
    ) -> tuple[list[FundAssignment], dict[str, list[FundRate]]]:
        assignments = self.repository.fund_assignments(company, plancode)
        fund_keys = [row.fund_key for row in assignments]
        rates: dict[str, list[FundRate]] = {key: [] for key in fund_keys}
        for row in self.repository.fund_rates(fund_keys):
            if row.rate_type in _INDEX_ASSUMPTION_TYPES:
                rates.setdefault(row.fund_key, []).append(row)
        return assignments, rates

    def get_index_illustration_rates(
        self,
        company: str,
        plancode: str,
        illustration_date: date,
        rga_indicator: str = "",
    ) -> Dict[str, Optional[float]]:
        """Current IUL illustrated rate by fund as of ``illustration_date``.

        The most recent ``IDX_ILL`` row on or before the illustration date is
        used for each fund. Reinsurance indicator ``R`` reads reinsurance block
        ``R``; other policies read the direct block. A missing direct value on a
        fund that is otherwise present remains ``None``.
        """
        plancode = _norm(plancode)
        if not company or not plancode or illustration_date is None:
            return {}
        rates_company = self._company_for_plan(plancode, company)
        if not rates_company:
            return {}

        wanted_block = _rein(rga_indicator)
        assignments, rates_by_key = self._assigned_fund_rates(rates_company, plancode)
        funds_with_ill = {
            row.fund
            for row in assignments
            if any(rate.rate_type == "IDX_ILL" for rate in rates_by_key.get(row.fund_key, []))
        }
        selected = {
            row.fund: row
            for row in assignments
            if row.rein_block == wanted_block and row.fund in funds_with_ill
        }

        out: Dict[str, Optional[float]] = {}
        for fund in sorted(funds_with_ill):
            assignment = selected.get(fund)
            latest = None if assignment is None else _latest_rate(
                rates_by_key.get(assignment.fund_key, []), "IDX_ILL", illustration_date,
            )
            out[fund] = None if latest is None else float(latest.rate)
        return out

    def get_index_benchmark_minmax(
        self,
        plancode: str,
        illustration_date: date,
        rga_indicator: str = "",
        fund_id: str = "IX",
    ) -> Optional[Dict[str, float]]:
        """Current benchmark geometric-average minimum and maximum."""
        plancode = _norm(plancode)
        fund_id = _norm(fund_id)
        if not plancode or not fund_id or illustration_date is None:
            return None
        rates_company = self._company_for_plan(plancode)
        if not rates_company:
            return None

        wanted_block = _rein(rga_indicator)
        assignments, rates_by_key = self._assigned_fund_rates(rates_company, plancode)
        assignment = next(
            (row for row in assignments if row.fund == fund_id and row.rein_block == wanted_block),
            None,
        )
        if assignment is None:
            return None
        rows = rates_by_key.get(assignment.fund_key, [])
        minimum = _latest_rate(rows, "IDX_BENCH_MIN", illustration_date)
        maximum = _latest_rate(rows, "IDX_BENCH_MAX", illustration_date)
        if minimum is None or maximum is None:
            return None
        return {"minimum": float(minimum.rate), "maximum": float(maximum.rate)}

    def get_index_market_returns(self) -> Dict[str, List[Dict[str, Any]]]:
        """Year-end returns used by the IUL historical lookback report."""
        assignments, rates_by_key = self._assigned_fund_rates("00", _MARKET_RETURN_PLAN)
        returns: Dict[str, List[Dict[str, Any]]] = {}
        for assignment in assignments:
            rows = [
                row for row in rates_by_key.get(assignment.fund_key, [])
                if row.rate_type == "MKT_RETURN" and row.scale == "C"
            ]
            for row in sorted(rows, key=lambda item: item.rate_start):
                returns.setdefault(assignment.fund, []).append({
                    "date": row.rate_start,
                    "return": float(row.rate),
                })
        return dict(sorted(returns.items()))
