"""Inspect illustration bonus-rate lookup for a plan/date."""
from __future__ import annotations

import json
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from suiteview.illustration.core import bonus_rates


def main() -> int:
    plancode = sys.argv[1] if len(sys.argv) > 1 else "1U135D00"
    valuation_date = date.fromisoformat(sys.argv[2]) if len(sys.argv) > 2 else date.today()
    table = bonus_rates._load_table()
    normalized = plancode.strip().upper()
    matches = [
        row for row in table
        if str(row.get("Plancode", "")).strip().upper() == normalized
    ]
    config = bonus_rates.load_bonus_config(plancode, valuation_date)
    print(json.dumps({
        "module_file": bonus_rates.__file__,
        "table_path": str(bonus_rates._TABLE_PATH),
        "row_count": len(table),
        "normalized_plancode": normalized,
        "matches": matches,
        "resolved": config.__dict__,
    }, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())