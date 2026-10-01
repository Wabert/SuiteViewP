"""IUL index assumptions from schema ``rates`` FUND rows."""
from datetime import date
from decimal import Decimal

import pytest

from suiteview.core.index_rates import IndexAssumptionTables
from suiteview.core.rates_errors import RatesError
from suiteview.core.rates_schema import FundAssignment, FundRate, PlanDef
from suiteview.illustration.core.ul_rates import ULRates


class _IndexAssumptionRepo:
    """Schema ``rates`` stand-in for index illustration and benchmark assumptions."""

    def __init__(self):
        self.queries = []

    def plan_defs(self, plancode):
        self.queries.append(("plan_defs", plancode))
        if plancode in {"1U145800", "1U147500", "MKTRETNS"}:
            return [PlanDef("00", plancode, "00", "IUL", "BASE", f"{plancode} test", ())]
        return []

    def fund_assignments(self, company, plancode):
        self.queries.append(("fund_assignments", company, plancode))
        if plancode == "1U145800":
            rows = []
            for fund in ("IX", "IC", "IF", "IS"):
                rows.append(FundAssignment(fund, "", f"1U145800 {fund}", "INDEX", "", ""))
                rows.append(FundAssignment(fund, "R", f"1U145800 {fund} R", "INDEX", "", ""))
            return rows
        if plancode == "1U147500":
            return [FundAssignment("IX", "R", "1U147500 IX R", "INDEX", "", "")]
        if plancode == "MKTRETNS":
            return [
                FundAssignment("NASDAQ100", "", "MKT NASDAQ100", "MKT", "", ""),
                FundAssignment("SP500", "", "MKT SP500", "MKT", "", ""),
            ]
        return []

    def fund_rates(self, fund_keys):
        def rate(key, rate_type, value, start, scale="C"):
            return FundRate(key, rate_type, scale, start, 0, None, None, Decimal(value))

        rows = [
            rate("1U145800 IX R", "IDX_ILL", "0.0400", date(2026, 7, 1)),
            rate("1U145800 IX R", "IDX_ILL", "0.0487", date(2026, 8, 1)),
            rate("1U145800 IC R", "IDX_ILL", "0.0453", date(2026, 8, 1)),
            rate("1U145800 IF R", "IDX_ILL", "0.0487", date(2026, 8, 1)),
            rate("1U145800 IS R", "IDX_ILL", "0.0445", date(2026, 8, 1)),
            rate("1U147500 IX R", "IDX_BENCH_MIN", "0.0400", date(2023, 9, 1)),
            rate("1U147500 IX R", "IDX_BENCH_MAX", "0.0700", date(2023, 9, 1)),
            rate("1U147500 IX R", "IDX_BENCH_MIN", "0.0440", date(2026, 7, 1)),
            rate("1U147500 IX R", "IDX_BENCH_MAX", "0.0786", date(2026, 7, 1)),
            rate("1U147500 IX R", "IDX_BENCH_MIN", "0.0500", date(2027, 1, 1)),
            rate("MKT SP500", "MKT_RETURN", "0.2331", date(2024, 12, 31)),
            rate("MKT NASDAQ100", "MKT_RETURN", "0.2488", date(2024, 12, 31)),
            rate("MKT SP500", "MKT_RETURN", "0.1639", date(2025, 12, 31)),
        ]
        return [row for row in rows if row.fund_key in fund_keys]

    def close(self):
        pass


def test_illustration_rates_select_rga_block_and_bonus_funds():
    result = IndexAssumptionTables(repository=_IndexAssumptionRepo()).get_index_illustration_rates(
        "01", "1U145800", date(2026, 8, 15), "R")

    assert result == pytest.approx({
        "IX": 0.0487, "IC": 0.0453, "IF": 0.0487, "IS": 0.0445,
    })


def test_illustration_rates_preserve_null_on_anico_basis():
    assert IndexAssumptionTables(repository=_IndexAssumptionRepo()).get_index_illustration_rates(
        "01", "1U145800", date(2026, 8, 31), "") == {
            "IX": None, "IC": None, "IF": None, "IS": None,
        }


class _FundRepo:
    """Schema ``rates`` stand-in: one IUL plan with an RGA-block and an ANICO-block index fund."""

    def plan_defs(self, plancode):
        return [PlanDef("00", plancode, "00", "IUL", "BASE", "test IUL", ())]

    def fund_assignments(self, company, plancode):
        return [
            FundAssignment("IP", "R", "IP R", "INDEX", "", ""),
            FundAssignment("IP", "", "IP", "INDEX", "", ""),
            FundAssignment("FX", "R", "FX R", "FIXED", "", ""),
        ]

    def fund_rates(self, fund_keys):
        def rate(key, rate_type, value, start=date(2024, 5, 1), scale="C"):
            return FundRate(key, rate_type, scale, start, 0, None, None, Decimal(value))

        rows = [
            rate("IP R", "IDX_FLOOR", "0"), rate("IP R", "IDX_CAP", "0.12"),
            rate("IP R", "IDX_PART", "1"), rate("IP R", "IDX_SPREAD", "0"),
            rate("IP R", "IDX_SPEC", "0"), rate("IP R", "IDX_MULT", "0.24"),
            rate("IP R", "IDX_ASSET", "0.0215"),
            # Superseded, future-dated and guaranteed-scale rows are never used.
            rate("IP R", "IDX_CAP", "0.10", start=date(2020, 1, 1)),
            rate("IP R", "IDX_CAP", "0.20", start=date(2027, 1, 1)),
            rate("IP R", "IDX_CAP", "0.03", scale="G"),
            rate("IP", "IDX_CAP", "0.99"),
        ]
        return [row for row in rows if row.fund_key in fund_keys]


def test_strategy_parameters_read_schema_index_funds_for_the_rga_block():
    result = ULRates(repository=_FundRepo()).get_index_strategy_parameters(
        "1U146800", date(2026, 7, 31), "R")

    assert result == {"IP": pytest.approx({
        "floor": 0.0,
        "cap": 0.12,
        "participation": 1.0,
        "int_rate_spread": 0.0,
        "specified_rate": 0.0,
        "multiplier": 0.24,
        "asset_fee": 0.0215,
    })}


def test_strategy_parameters_refuse_a_partially_loaded_fund():
    with pytest.raises(RatesError, match="missing index parameters"):
        ULRates(repository=_FundRepo()).get_index_strategy_parameters(
            "1U146800", date(2026, 7, 31), "")


def test_benchmark_minmax_selects_latest_effective_ix_row():
    result = IndexAssumptionTables(repository=_IndexAssumptionRepo()).get_index_benchmark_minmax(
        "1u147500", date(2026, 7, 31), "R")

    assert result == pytest.approx({"minimum": 0.044, "maximum": 0.0786})


def test_market_returns_are_grouped_and_date_normalized():
    assert IndexAssumptionTables(repository=_IndexAssumptionRepo()).get_index_market_returns() == {
        "SP500": [
            {"date": date(2024, 12, 31), "return": 0.2331},
            {"date": date(2025, 12, 31), "return": 0.1639},
        ],
        "NASDAQ100": [
            {"date": date(2024, 12, 31), "return": 0.2488},
        ],
    }
