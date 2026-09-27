"""Read-only live annual-total source and screen verification."""

import argparse
import json
import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from suiteview.polview.services.policy_service import get_policy_info
from suiteview.polview.models.policy_record_annual_totals import (
    TABLES, build_segment_63, build_segment_64,
)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--policy", default="UL045809")
    parser.add_argument("--company", default="01")
    parser.add_argument("--region", default="CKPR")
    parser.add_argument("--output", type=Path)
    parser.add_argument("--reference", type=Path)
    args = parser.parse_args()
    if os.environ.get("SUITEVIEW_LOCAL_DATA") == "1":
        raise RuntimeError("Live verification requires local data disabled.")
    pi = get_policy_info(args.policy.strip().upper(), region=args.region.strip().upper(),
                         company_code=args.company.strip().upper())
    if pi is None or not pi.exists:
        raise ValueError(f"Policy {args.policy} not found")
    result = {"policy": pi.policy_number, "sources": {}, "text": {}, "lines": {}}
    for segment, builder in (("63", build_segment_63), ("64", build_segment_64)):
        lines = builder(pi)
        result["sources"][TABLES[segment]] = pi.fetch_table(TABLES[segment])
        result["lines"][segment] = lines
        result["text"][segment] = ["".join(run["text"] for run in line) for line in lines or []]
    if args.reference:
        expected = json.loads(args.reference.read_text(encoding="utf-8"))
        for segment in ("63", "64"):
            actual = []
            for line in (result["lines"][segment] or [])[1:]:
                if not any(run.get("field") for run in line):
                    break
                actual.append(" ".join("".join(run["text"] for run in line).split()))
            if actual != expected[segment]:
                raise AssertionError(f"Segment {segment} capture mismatch: {actual}")
        result["capture_match"] = True
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(result, indent=2, default=str), encoding="utf-8")
    summary = {key: value for key, value in result.items() if key not in ("lines", "sources")}
    summary["source_rows"] = {table: len(rows) for table, rows in result["sources"].items()}
    summary["output"] = str(args.output) if args.output else None
    if not args.output:
        summary["sources"] = result["sources"]
    print(json.dumps(summary, indent=2, default=str))


if __name__ == "__main__":
    main()
