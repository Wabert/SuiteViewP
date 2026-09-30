"""Build the bundled CyberLife mortality table file used for par WL net single premiums.

CyberLife values paid-up additions and reduced paid-up insurance with a net single
premium calculated from the coverage's mortality table (CKAPTB32 code, e.g. ``N0`` =
1980 CSO male nonsmoker ANB) and interest rate (CyberDoc S45 ``CKISPUAV``). The official
source of those tables is the Life Product ``Mortality Tables (Cyberlife).xlsx``
workbook; this tool reads it with the RateManager parser and writes
``suiteview/illustration/plancodes/cyberlife_mortality.json``::

    {"source": ..., "sha256": ..., "tables": {"N0": {"description": ..., "first_age": 15,
     "last_age": 99, "qx": ["0.00076", ...]}}}

qx values are kept as the workbook's exact decimal strings.

Usage: venv\\Scripts\\python.exe tools\\rerun\\build_cyberlife_mortality.py [--workbook PATH]
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from decimal import Decimal
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))

from suiteview.ratemanager.mortality_loader import DEFAULT_WORKBOOK, parse_workbook  # noqa: E402

OUT = REPO / "suiteview" / "illustration" / "plancodes" / "cyberlife_mortality.json"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workbook", type=Path, default=DEFAULT_WORKBOOK)
    args = parser.parse_args()
    package = parse_workbook(args.workbook)
    rates: dict[str, dict[int, Decimal]] = {}
    for rate in package.rates:
        rates.setdefault(rate.code, {})[rate.attained_age] = rate.rate_per_1000 / Decimal(1000)
    tables = {}
    for table in package.tables:
        by_age = rates[table.code]
        tables[table.code] = {
            "description": table.description,
            "first_age": table.first_age,
            "last_age": table.last_age,
            "qx": [format(by_age[age].normalize(), "f") for age in range(table.first_age, table.last_age + 1)],
        }
    payload = {
        "source": str(args.workbook),
        "sha256": hashlib.sha256(Path(args.workbook).read_bytes()).hexdigest(),
        "warnings": list(package.warnings),
        "tables": dict(sorted(tables.items())),
    }
    OUT.write_text(json.dumps(payload, indent=1) + "\n", encoding="utf-8")
    print(json.dumps({"out": str(OUT), "tables": len(tables), "rates": len(package.rates)}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
