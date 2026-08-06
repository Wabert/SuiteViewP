r"""Validate or replace UL_Rates mortality tables from the CyberLife workbook.

Usage:
    venv\Scripts\python.exe tools\load_mortality_rates.py
    venv\Scripts\python.exe tools\load_mortality_rates.py --load
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from suiteview.ratemanager.mortality_loader import (
    DEFAULT_WORKBOOK,
    parse_workbook,
    replace_live,
    summarize,
)


def main() -> None:
    if len(sys.argv) > 1 and sys.argv[1] == "--load":
        config = {"load": True}
    else:
        config = json.loads(sys.argv[1]) if len(sys.argv) > 1 else {}
    workbook = config.get("workbook", str(DEFAULT_WORKBOOK))
    dsn = str(config.get("dsn", "UL_Rates"))
    should_load = bool(config.get("load", False))

    package = parse_workbook(workbook)
    result = {
        "status": "validated",
        "workbook": str(workbook),
        "dsn": dsn,
        "summary": summarize(package),
    }
    if should_load:
        result["database"] = replace_live(package, dsn)
        result["status"] = "loaded"
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()