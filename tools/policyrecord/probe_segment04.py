"""Read-only live Benefits (6204) source and capture verification."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from suiteview.polview.services.policy_service import get_policy_info
from suiteview.polview.config.policy_records import POLICY_RECORD_TABLES
from suiteview.polview.ui.policy_record_viewer import build_screen


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--policy", default="U0566833")
    parser.add_argument("--company", default="01")
    parser.add_argument("--region", default="CKPR")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--sources-only", action="store_true")
    parser.add_argument("--expect-u0566833", action="store_true")
    args = parser.parse_args()
    if args.sources_only and args.expect_u0566833:
        parser.error("--expect-u0566833 cannot be combined with --sources-only")
    if args.expect_u0566833 and (
        args.policy.strip().upper(), args.company.strip(), args.region.strip().upper()
    ) != ("U0566833", "01", "CKPR"):
        parser.error("Capture comparison is only valid for U0566833 / 01 / CKPR.")
    if os.environ.get("SUITEVIEW_LOCAL_DATA") == "1":
        raise RuntimeError("Live verification requires local data disabled.")
    pi = get_policy_info(
        args.policy.strip().upper(), region=args.region.strip().upper(),
        company_code=args.company.strip().upper(),
    )
    if pi is None or not pi.exists:
        raise RuntimeError(f"Policy {args.policy} was not found.")
    sources = {}
    for table in POLICY_RECORD_TABLES["Policy Record 04"]:
        sources[table] = pi.fetch_table(table)
        if error := pi.table_error(table):
            raise RuntimeError(f"{table}: {error}")
    result = {"policy": pi.policy_number, "sources": sources}
    if not args.sources_only:
        screen = build_screen("04", pi)
        if not screen or not screen.get("live"):
            raise RuntimeError(f"Benefits screen is not live: {screen}")
        result["text"] = ["".join(run["text"] for run in line) for line in screen["lines"]]
        result["screen"] = screen
        if args.expect_u0566833:
            expected = [
                "04 0081 00000000 00000100 1 A 0 00 1 05/28/2058 1 0 150 48 2 05/28/2006",
                "05/28/2058 1.00 .00 0 1000.000 1000.00 05/28/2058 X PPA 4.500 N",
                "04 0081 00001000 10000000 1 3 9 00 1 05/28/2018 0 1 150 48 2 05/28/2006",
                "05/28/2018 1.00 .01 0 1000.000 1000.00 05/28/2018 ULDW91 N",
            ]
            actual = []
            for line in screen["lines"][1:]:
                if not any(run.get("field") for run in line):
                    break
                actual.append(" ".join("".join(run["text"] for run in line).split()))
            if actual != expected:
                raise AssertionError(f"Capture mismatch:\nExpected: {expected}\nActual: {actual}")
            result["capture_match"] = True
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, default=str), encoding="utf-8")
    print(json.dumps({
        "output": str(args.output),
        "source_rows": {table: len(rows) for table, rows in sources.items()},
        "text": result.get("text"), "capture_match": result.get("capture_match"),
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
