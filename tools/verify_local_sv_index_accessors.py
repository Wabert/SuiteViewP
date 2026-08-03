"""Exercise the IUL SV_INDEX Rates accessors against the LOCAL SQLite fixture.

Confirms the four index accessors on ``suiteview.core.rates.Rates`` actually run
against the local rates.sqlite (SUITEVIEW_LOCAL_DATA=1) — in particular that the
benchmark query works on SQLite (SQL Server ``TOP`` is not valid there). Uses a
real sample key drawn from each SV_INDEX table so a passing run means the data is
queryable, not just present.

Usage:
    venv\\Scripts\\python.exe tools/verify_local_sv_index_accessors.py
"""

from __future__ import annotations

import json
import os
import sqlite3
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
RATES_DB = ROOT / "bundled_data" / "dev" / "rates.sqlite"


def _sample(conn: sqlite3.Connection, sql: str) -> dict | None:
    row = conn.execute(sql).fetchone()
    return dict(row) if row else None


def main() -> None:
    os.environ["SUITEVIEW_LOCAL_DATA"] = "1"

    ro = sqlite3.connect(f"file:{RATES_DB.as_posix()}?mode=ro", uri=True)
    ro.row_factory = sqlite3.Row
    ill = _sample(ro, "SELECT Company, Plancode, FundID, EffDate FROM SV_INDEX_ILL_RATES LIMIT 1")
    par = _sample(ro, "SELECT Plancode, RGA_Ind, Fund_ID, [DATE] AS D FROM SV_INDEX_PARAMS LIMIT 1")
    ben = _sample(ro, "SELECT PLAN_ID, REIN_BLOCK_IND, FUND_ID, EFFECTIVE_DATE FROM SV_INDEX_BENCHMARK_MINMAX LIMIT 1")
    ro.close()

    from suiteview.core.rates import Rates

    rates = Rates()
    results: dict = {}

    # 1) Illustration rates.
    eff = str(ill["EffDate"])[:10]
    ir = rates.get_index_illustration_rates(
        ill["Company"], ill["Plancode"], date.fromisoformat(eff),
        "R" if str(par["RGA_Ind"]).upper() == "R" else "",
    )
    results["illustration_rates"] = {"sample_key": ill, "returned_funds": len(ir), "ok": len(ir) > 0}

    # 2) Strategy parameters.
    pd = str(par["D"])[:10]
    sp = rates.get_index_strategy_parameters(
        par["Plancode"], date.fromisoformat(pd),
        "R" if str(par["RGA_Ind"]).upper() == "R" else "",
    )
    results["strategy_parameters"] = {"sample_key": par, "returned_funds": len(sp), "ok": len(sp) > 0}

    # 3) Benchmark min/max — the SQL-Server TOP-1 query; must work on SQLite too.
    bd = str(ben["EFFECTIVE_DATE"])[:10]
    bm = rates.get_index_benchmark_minmax(
        ben["PLAN_ID"], date.fromisoformat(bd),
        "R" if str(ben["REIN_BLOCK_IND"]).upper() == "R" else "",
        ben["FUND_ID"],
    )
    results["benchmark_minmax"] = {"sample_key": ben, "returned": bm, "ok": bm is not None}

    # 4) Market returns.
    mr = rates.get_index_market_returns()
    results["market_returns"] = {"indices": sorted(mr.keys()), "ok": len(mr) > 0}

    all_ok = all(v["ok"] for v in results.values())
    print(json.dumps({"all_ok": all_ok, "results": results}, indent=2, default=str))
    raise SystemExit(0 if all_ok else 1)


if __name__ == "__main__":
    main()
