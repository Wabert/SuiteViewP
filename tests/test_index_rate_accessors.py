"""UL_Rates accessors for IUL rates, parameters, and market returns."""
from datetime import date
from decimal import Decimal

import pytest

from suiteview.core.rates import Rates


def test_illustration_rates_select_rga_column_and_bonus_fund_aliases(monkeypatch):
    rates = Rates()
    captured = {}

    def fake_fetch(sql, params):
        captured["sql"] = sql
        captured["params"] = params
        return [
            ("1U145800", "IX", None, Decimal("0.0487")),
            ("1U145801", "IC", None, Decimal("0.0453")),
            ("1U145802", "IF", None, Decimal("0.0487")),
            ("1U145803", "IS", None, Decimal("0.0445")),
        ]

    monkeypatch.setattr(rates, "_fetch_rates", fake_fetch)
    result = rates.get_index_illustration_rates(
        "01", "1U145800", date(2026, 8, 15), "R")

    assert result == pytest.approx({
        "IX": 0.0487, "IC": 0.0453, "IF": 0.0487, "IS": 0.0445,
    })
    assert "MAX(r2.[EffDate])" in captured["sql"]
    assert "r2.[EffDate] <= ?" in captured["sql"]
    assert captured["params"][-1] == "2026-08-15"
    assert set(captured["params"][1:-1]) == {
        "1U145800", "1U145801", "1U145802", "1U145803",
    }


def test_illustration_rates_preserve_null_on_anico_basis(monkeypatch):
    rates = Rates()
    monkeypatch.setattr(
        rates,
        "_fetch_rates",
        lambda _sql, _params: [
            ("1U145800", "IX", None, Decimal("0.0487")),
        ],
    )

    assert rates.get_index_illustration_rates(
        "01", "1U145800", date(2026, 8, 31), "") == {"IX": None}


def test_strategy_parameters_select_effective_rga_rows(monkeypatch):
    rates = Rates()
    captured = {}

    def fake_fetch(sql, params):
        captured["sql"] = sql
        captured["params"] = params
        return [(
            "IP",
            Decimal("0"),
            Decimal("0.12"),
            Decimal("1"),
            Decimal("0"),
            Decimal("0"),
            Decimal("0.24"),
            Decimal("0.0215"),
        )]

    monkeypatch.setattr(rates, "_fetch_rates", fake_fetch)
    result = rates.get_index_strategy_parameters(
        "1U146800", date(2026, 7, 31), "R")

    assert result["IP"] == pytest.approx({
        "floor": 0.0,
        "cap": 0.12,
        "participation": 1.0,
        "int_rate_spread": 0.0,
        "specified_rate": 0.0,
        "multiplier": 0.24,
        "asset_fee": 0.0215,
    })
    assert "MAX(p2.[DATE])" in captured["sql"]
    assert captured["params"] == [
        "1U146800", "R", "2026-07-31"]


def test_benchmark_minmax_selects_latest_effective_ix_row(monkeypatch):
    rates = Rates()
    captured = {}

    def fake_fetch(sql, params):
        captured["sql"] = sql
        captured["params"] = params
        return [(Decimal("0.0440"), Decimal("0.0786"))]

    monkeypatch.setattr(rates, "_fetch_rates", fake_fetch)

    result = rates.get_index_benchmark_minmax(
        "1u147500", date(2026, 7, 31), "R")

    assert result == pytest.approx({"minimum": 0.044, "maximum": 0.0786})
    assert "SV_INDEX_BENCHMARK_MINMAX" in captured["sql"]
    assert "MAX(b2.[EFFECTIVE_DATE])" in captured["sql"]
    assert captured["params"] == [
        "1U147500", "R", "IX", "2026-07-31",
    ]


def test_market_returns_are_grouped_and_date_normalized(monkeypatch):
    rates = Rates()
    captured = {}

    def fake_fetch(sql, params):
        captured["sql"] = sql
        captured["params"] = params
        return [
            (date(2024, 12, 31), "SP500", Decimal("0.2331")),
            (date(2024, 12, 31), "NASDAQ100", Decimal("0.2488")),
            (date(2025, 12, 31), "SP500", Decimal("0.1639")),
        ]

    monkeypatch.setattr(rates, "_fetch_rates", fake_fetch)

    assert rates.get_index_market_returns() == {
        "SP500": [
            {"date": date(2024, 12, 31), "return": 0.2331},
            {"date": date(2025, 12, 31), "return": 0.1639},
        ],
        "NASDAQ100": [
            {"date": date(2024, 12, 31), "return": 0.2488},
        ],
    }
    assert "SV_INDEX_MARKET_RETURNS" in captured["sql"]
    assert captured["params"] == []
