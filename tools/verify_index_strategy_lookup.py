r"""Verify live illustration-date index strategy lookups through core.Rates.

Usage:
    venv\Scripts\python.exe tools\verify_index_strategy_lookup.py ^
      "{\"company\":\"01\",\"plancode\":\"1U147900\",\"illustration_date\":\"2026-08-15\",\"rga_indicator\":\"\"}"
"""

from __future__ import annotations

import json
import sys
from datetime import date

sys.path.insert(0, ".")

from suiteview.core.rates import Rates  # noqa: E402


def main() -> None:
    if len(sys.argv) < 2:
        raise SystemExit("Pass a JSON config argument.")
    config = json.loads(sys.argv[1])
    illustration_date = date.fromisoformat(config["illustration_date"])
    rga_indicator = str(config.get("rga_indicator", ""))

    rates = Rates()
    try:
        market_returns = rates.get_index_market_returns()
        result = {
            "company": config["company"],
            "plancode": config["plancode"],
            "illustration_date": illustration_date.isoformat(),
            "rga_indicator": rga_indicator,
            "illustration_rates": rates.get_index_illustration_rates(
                config["company"],
                config["plancode"],
                illustration_date,
                rga_indicator,
            ),
            "strategy_parameters": rates.get_index_strategy_parameters(
                config["plancode"],
                illustration_date,
                rga_indicator,
            ),
            "benchmark_minmax": rates.get_index_benchmark_minmax(
                config["plancode"],
                illustration_date,
                rga_indicator,
            ),
            "market_returns": {
                market_index: {
                    "count": len(rows),
                    "first": rows[0] if rows else None,
                    "last": rows[-1] if rows else None,
                }
                for market_index, rows in market_returns.items()
            },
        }
    finally:
        rates.close()

    print(json.dumps(result, indent=2, sort_keys=True, default=str))


if __name__ == "__main__":
    main()
