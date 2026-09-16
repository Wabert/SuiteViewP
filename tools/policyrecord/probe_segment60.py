"""Read-only Payment Accumulation source and live-screen verification."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from suiteview.core.policy_service import get_policy_info
from suiteview.polview.ui.policy_record_viewer import build_screen


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--policy", default="UL045809")
    parser.add_argument("--company", default="01")
    parser.add_argument("--region", default="CKPR")
    parser.add_argument("--output", type=Path)
    parser.add_argument("--expect-ul045809", action="store_true")
    args = parser.parse_args()
    if os.environ.get("SUITEVIEW_LOCAL_DATA") == "1":
        raise RuntimeError("Live verification requires local data disabled.")
    pi = get_policy_info(
        args.policy.strip().upper(), region=args.region.strip().upper(),
        company_code=args.company.strip().upper(),
    )
    if pi is None or not pi.exists:
        raise RuntimeError(f"Policy {args.policy} was not found.")
    sources = {}
    for table in ("LH_POL_TOTALS", "LH_MO_ADD_PMT"):
        sources[table] = pi.fetch_table(table)
        error = pi.table_error(table)
        if error:
            raise RuntimeError(f"{table}: {error}")
    screen = build_screen("60", pi)
    if screen.get("live_error"):
        raise RuntimeError(screen["live_error"])
    text = [
        "".join(run["text"] for run in line)
        for line in screen["lines"]
    ]
    result = {"policy": pi.policy_number, "sources": sources, "screen": screen, "text": text}
    if args.expect_ul045809:
        expected = [
            "60 0139 00000000 00000000 46726.00 1365.25 3 4458.28 2316.00 .00 .00 .00",
            "13987.30 .00 3 34103.95 .00 .00 **/**/**** **/**/**** .00 .00 .00 .00",
            ".00 0",
        ]
        actual = [" ".join(line.split()) for line in text[1:4]]
        if not screen.get("live") or actual != expected:
            raise AssertionError(f"Capture mismatch:\nExpected: {expected}\nActual: {actual}")
        result["capture_match"] = True
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(result, indent=2, default=str), encoding="utf-8")
    print(json.dumps({
        "output": str(args.output) if args.output else None,
        "live": bool(screen.get("live")), "sources": sources, "text": text,
        "capture_match": result.get("capture_match"),
    }, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
