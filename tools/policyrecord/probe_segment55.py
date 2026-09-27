"""Read-only source and four-line capture verification for Individual Fund Control."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from suiteview.polview.services.policy_service import get_policy_info


TABLES = (
    "LH_COV_IVM_FND_CTL", "LH_COV_FXD_FND_CTL",
    "LH_AMT_TIERED_ITS", "LH_DUR_TIERED_ITS",
)
CAPTURE = [
    "55 0079 00100001 00000000 00000000 1 GP F 0 00 0 0 0 0 0 0 0 1 0 00 0 0",
    "**/**/**** .000 1 1 1 .000 2 999 0 0 1 .000 **/**/****",
    "55 0079 00000001 00000000 00000000 1 U1 F 0 00 0 0 1 0 1 1 1 1 1 00 0 0",
    "**/**/**** .000 2 3 1 1 4.000 0 0 0 0 ANICO1983 6.000 12/14/2000",
]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--policy", default="UL045809")
    parser.add_argument("--company", default="01")
    parser.add_argument("--region", default="CKPR")
    parser.add_argument("--output", type=Path)
    parser.add_argument("--sources-only", action="store_true")
    parser.add_argument("--expect-ul045809", action="store_true")
    args = parser.parse_args()
    if args.sources_only and args.expect_ul045809:
        parser.error("--expect-ul045809 cannot be combined with --sources-only")
    if os.environ.get("SUITEVIEW_LOCAL_DATA") == "1":
        raise RuntimeError("Live verification requires local data disabled.")
    pi = get_policy_info(
        args.policy.strip().upper(), region=args.region.strip().upper(),
        company_code=args.company.strip().upper(),
    )
    if pi is None or not pi.exists:
        raise RuntimeError(f"Policy {args.policy} was not found.")
    sources = {}
    for table in TABLES:
        sources[table] = pi.fetch_table(table)
        if error := pi.table_error(table):
            raise RuntimeError(f"{table}: {error}")
    result = {"policy": pi.policy_number, "sources": sources}
    if not args.sources_only:
        from suiteview.polview.models.policy_record_builder import build_segment_lines

        lines = build_segment_lines("55", pi)
        result["lines"] = lines
        result["text"] = ["".join(run["text"] for run in line) for line in (lines or [])]
        if args.expect_ul045809:
            if (args.policy.upper(), args.company, args.region.upper()) != ("UL045809", "01", "CKPR"):
                raise ValueError("Capture comparison is only valid for UL045809 / 01 / CKPR.")
            actual = []
            for line in (lines or [])[1:]:
                if not any(run.get("field") for run in line):
                    break
                actual.append(" ".join("".join(run["text"] for run in line).split()))
            if actual != CAPTURE:
                raise AssertionError(f"Capture mismatch:\nExpected: {CAPTURE}\nActual: {actual}")
            result["capture_match"] = True
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(result, indent=2, default=str), encoding="utf-8")
    print(json.dumps(result, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
