"""Read-only live Segment 67 source and rendered-screen verification."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from suiteview.core.policy_service import get_policy_info
from suiteview.polview.models.policy_record_builder import build_segment_lines
from suiteview.polview.ui.policy_record_viewer import load_screen


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--policy", default="UL045809")
    parser.add_argument("--company", default="01")
    parser.add_argument("--region", default="CKPR")
    parser.add_argument("--output", type=Path)
    parser.add_argument(
        "--expect-ul045809", action="store_true",
        help="Check the body against the supplied September 15, 2026 capture.",
    )
    args = parser.parse_args()
    if os.environ.get("SUITEVIEW_LOCAL_DATA") == "1":
        raise RuntimeError("Live verification requires SUITEVIEW_LOCAL_DATA disabled.")
    pi = get_policy_info(
        args.policy.strip().upper(), region=args.region.strip().upper(),
        company_code=args.company.strip().upper(),
    )
    if pi is None or not pi.exists:
        raise RuntimeError(f"Policy {args.policy} was not found.")
    tables = (
        "LH_COV_INS_RNL_PER", "LH_COV_INS_RNL_RT", "LH_BNF_INS_RNL_RT",
        "LH_SST_XTR_RNL_RT", "LH_COV_INS_GDL_PRM", "LH_BNF_INS_GDL_PRM",
        "TH_COV_INS_RNL_RT",
    )
    sources = {table: pi.fetch_table(table) for table in tables}
    lines = build_segment_lines("67", pi, load_screen("67"))
    result = {
        "policy": pi.policy_number,
        "sources": sources,
        "live": lines is not None,
        "lines": lines,
        "text": ["".join(run["text"] for run in line) for line in lines or []],
    }
    if args.expect_ul045809:
        expected = (
            "67 0110 1 1U130M29 C 00 1 8 "
            "C * * 1AA 000337971C C * * 1AB 000282184C "
            "T * * 1AA 000006430C T * * 1AB 000006430C "
            "M * * 1AA 000006430C M * * 1AB 000006430C "
            "A 00000000000C S 00002194914D"
        )
        # Footer is separate chrome; only the three captured record rows matter.
        actual = " ".join(" ".join(result["text"][1:4]).split())
        result["capture_match"] = actual == expected
        if not result["capture_match"]:
            raise AssertionError(f"Capture mismatch:\nExpected: {expected}\nActual: {actual}")
    text = json.dumps(result, indent=2, default=str)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(text, encoding="utf-8")
        print(json.dumps({
            "output": str(args.output), "live": result["live"],
            "source_rows": {table: len(rows) for table, rows in sources.items()},
            "text": result["text"],
            "capture_match": result.get("capture_match"),
        }, indent=2))
    else:
        print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
