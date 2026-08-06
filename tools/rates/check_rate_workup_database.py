"""Run the Rate Manager's read-only database analysis for a workup folder.

Usage:
    venv\\Scripts\\python.exe tools\\check_rate_workup_database.py <folder> [DSN]
"""

from __future__ import annotations

import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from suiteview.ratemanager.database_loader import (  # noqa: E402
    ULRatesRepository,
    WorkupPackage,
    analyze_package,
)


def main() -> None:
    if len(sys.argv) < 2:
        raise SystemExit("Workup folder argument is required.")
    folder = sys.argv[1]
    dsn = sys.argv[2] if len(sys.argv) > 2 else "UL_Rates"
    package = WorkupPackage.load(folder)
    repository = ULRatesRepository(dsn)
    try:
        analysis = analyze_package(package, repository)
    finally:
        repository.close()

    tables = {}
    for name, table in analysis.tables.items():
        tables[name] = {
            "file_rows": table.file_rows,
            "existing_rows": len(table.existing_rows),
            "new_indexes": len(table.new_indexes),
            "identical_indexes": len(table.identical_indexes),
            "different_indexes": len(table.different_indexes),
            "blocked_indexes": {
                str(index): list(plancodes)
                for index, plancodes in table.blocked_indexes.items()
            },
        }
    print(json.dumps({
        "plancode": package.plancode,
        "issue_version": package.issue_version,
        "tables": tables,
    }, indent=2))


if __name__ == "__main__":
    main()
